"""macOS: the wallpaper per screen through NSWorkspace, screens and the area
the menu bar and Dock cover from NSScreen, notifications with a Read more
button from UserNotifications (AppleScript's `display notification` when not
running as the app bundle), and Open at login through SMAppService (a
LaunchAgent in development).

AppKit wants screens touched on the main thread. Once the menu bar app runs
its event loop (`MAIN_LOOP` is set), calls from worker threads are handed to
the main thread and waited for; the command line calls straight through."""

import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

from .. import APP_ID, BUNDLE_ID
from .base import Monitor, Platform, language_code

# Set by the app once NSApplication runs: from then on, AppKit calls from
# other threads go through the main thread.
MAIN_LOOP = threading.Event()

NSImageScaleProportionallyUpOrDown = 3
SM_STATUS_ENABLED = 1
SM_STATUS_REQUIRES_APPROVAL = 2
UN_OPTION_ALERT = 1 << 2
UN_PRESENT_LIST = 1 << 3
UN_PRESENT_BANNER = 1 << 4
UN_ACTION_FOREGROUND = 1 << 2
NOTIFICATION_CATEGORY = "painting"
LOGIN_SECONDS = 180  # a start this soon after boot is a start at login
# macOS 26 reports a new wallpaper a second or two after it was set; until
# then reads answer with what was just set (or a cleanup would delete it).
SETTLE_SECONDS = 10


def on_main(work, timeout=20):
    """work() on the main thread (waiting for its result) while the app's
    event loop runs; directly otherwise."""
    from Foundation import NSThread
    if NSThread.isMainThread() or not MAIN_LOOP.is_set():
        return work()
    from PyObjCTools import AppHelper
    done, box = threading.Event(), {}

    def call():
        try:
            box["value"] = work()
        except BaseException as exc:  # noqa: BLE001 - re-raised on the caller's thread
            box["error"] = exc
        finally:
            done.set()

    AppHelper.callAfter(call)
    if not done.wait(timeout):
        raise TimeoutError("the main thread did not answer")
    if "error" in box:
        raise box["error"]
    return box.get("value")


def inset_of(frame, visible, scale):
    """Pixels the menu bar and Dock take from each edge, as (left, top,
    right, bottom), from NSScreen's frame and visibleFrame in points
    (((x, y), (width, height)), origin bottom left) and the backing scale."""
    (fx, fy), (fw, fh) = frame
    (vx, vy), (vw, vh) = visible
    edges = (vx - fx, (fy + fh) - (vy + vh), (fx + fw) - (vx + vw), vy - fy)
    return tuple(max(0, round(edge * scale)) for edge in edges)


def _rect(rect):
    return ((rect.origin.x, rect.origin.y), (rect.size.width, rect.size.height))


def _screens():
    """[(id, NSScreen, Monitor)] for every screen; main thread only."""
    from AppKit import NSScreen
    found = []
    for screen in NSScreen.screens() or []:
        number = screen.deviceDescription().get("NSScreenNumber")
        scale = float(screen.backingScaleFactor() or 1)
        frame, visible = _rect(screen.frame()), _rect(screen.visibleFrame())
        width, height = round(frame[1][0] * scale), round(frame[1][1] * scale)
        if width <= 0 or height <= 0:
            continue
        key = str(int(number)) if number is not None else f"screen-{len(found) + 1}"
        found.append((key, screen, Monitor(key, width, height, inset_of(frame, visible, scale))))
    return found


def _biggest(found):
    return max(found, key=lambda s: (s[2].width * s[2].height, s[2].width))


def mac_caption_fonts():
    """(title, body, *fallbacks): SF Mono Italic and SF Mono, like the
    Omarchy placard, then fonts for scripts they lack. Plain files, so this
    needs no AppKit (the development platform uses it on a Mac too)."""
    fonts = Path("/System/Library/Fonts")
    extra = fonts / "Supplemental"

    def first(*candidates):
        return next((p for p in candidates if p.exists()), None)

    title = first(fonts / "SFNSMonoItalic.ttf", extra / "Courier New Italic.ttf", extra / "Georgia Italic.ttf")
    body = first(fonts / "SFNSMono.ttf", extra / "Courier New.ttf", fonts / "Helvetica.ttc")
    fallbacks = [p for p in (fonts / "Hiragino Sans GB.ttc", fonts / "ヒラギノ角ゴシック W3.ttc",
                             fonts / "AppleSDGothicNeo.ttc", fonts / "Kohinoor.ttc", fonts / "ThonburiUI.ttc",
                             extra / "Arial Unicode.ttf", fonts / "Apple Symbols.ttf") if p.exists()]
    return (title, body, *fallbacks)


def bundle_path():
    """The .app this process runs from, or None (python -m, tests)."""
    executable = Path(sys.executable).resolve()
    for parent in executable.parents:
        if parent.suffix == ".app":
            return parent
    return None


def _ns_bundle_id():
    try:
        from Foundation import NSBundle
        return NSBundle.mainBundle().bundleIdentifier()
    except Exception:  # noqa: BLE001
        return None


class MacPlatform(Platform):
    name = "macos"

    def __init__(self):
        self.packaged = bundle_path() is not None and _ns_bundle_id() == BUNDLE_ID
        self.last_images = {}  # what set_wallpaper applied, to re-apply on another Space
        self.launched_by_login = False  # set by the app from its launch event
        self._center = None
        self._delegate = None
        self._callbacks = {}
        self._notify_lock = threading.Lock()

    # -- setup and paths

    def setup(self):
        """Ask for permission to notify, once per install (macOS remembers)."""
        if not self.packaged:
            return
        try:
            center = self._notification_center()
            center.requestAuthorizationWithOptions_completionHandler_(
                UN_OPTION_ALERT, lambda granted, error: None)
        except Exception as exc:  # noqa: BLE001
            print(f"museum-wallpapers: notifications unavailable: {exc}", file=sys.stderr)

    def paths(self):
        if os.environ.get("MUSEUM_WALLPAPERS_HOME"):
            return super().paths()
        home = Path.home()
        support = home / "Library" / "Application Support" / APP_ID
        return {"config": support, "cache": home / "Library" / "Caches" / APP_ID, "state": support / "state",
                "pictures": home / "Pictures"}

    def log_file(self, state):
        if os.environ.get("MUSEUM_WALLPAPERS_HOME"):
            return super().log_file(state)
        return Path.home() / "Library" / "Logs" / APP_ID / "museum-wallpapers.log"

    # -- screens and wallpaper

    def monitors(self):
        return on_main(lambda: [monitor for _key, _screen, monitor in _screens()])

    def set_wallpaper(self, images):
        images = {key: str(Path(value).resolve()) for key, value in images.items()}

        def apply():
            from AppKit import (NSColor, NSWorkspace, NSWorkspaceDesktopImageAllowClippingKey,
                                NSWorkspaceDesktopImageFillColorKey, NSWorkspaceDesktopImageScalingKey)
            from Foundation import NSURL
            found = _screens()
            if not found:
                raise OSError("no screen found")
            fallback = None
            if not any(key in images for key, _s, _m in found):
                # The screens changed since the images were made: the biggest image everywhere.
                fallback = images.get(_biggest(found)[0]) or max(images.values(), key=len)
            options = {NSWorkspaceDesktopImageScalingKey: NSImageScaleProportionallyUpOrDown,
                       NSWorkspaceDesktopImageAllowClippingKey: True,
                       NSWorkspaceDesktopImageFillColorKey: NSColor.blackColor()}
            workspace, applied, errors = NSWorkspace.sharedWorkspace(), {}, []
            for key, screen, _monitor in found:
                path = images.get(key) or fallback
                if not path:
                    continue
                ok, error = workspace.setDesktopImageURL_forScreen_options_error_(
                    NSURL.fileURLWithPath_(path), screen, options, None)
                if ok:
                    applied[key] = path
                else:
                    errors.append(str(error.localizedDescription() if error else "unknown error"))
            if not applied:
                raise OSError("could not set the wallpaper: " + "; ".join(errors or ["no matching screen"]))
            return applied

        self.last_images = on_main(apply)
        self._set_at = time.monotonic()

    def _settling(self):
        return bool(self.last_images) and time.monotonic() - getattr(self, "_set_at", -SETTLE_SECONDS) < SETTLE_SECONDS

    def current_wallpaper(self):
        def read():
            from AppKit import NSWorkspace
            found = _screens()
            if not found:
                return None
            key, screen, _monitor = _biggest(found)
            if self._settling() and key in self.last_images:
                return self.last_images[key]
            url = NSWorkspace.sharedWorkspace().desktopImageURLForScreen_(screen)
            return url.path() if url is not None and url.isFileURL() else None

        path = on_main(read)
        return Path(path) if path else None

    def wallpapers(self):
        """{screen id: path} as macOS shows them on the current Space."""
        def read():
            from AppKit import NSWorkspace
            workspace, result, settling = NSWorkspace.sharedWorkspace(), {}, self._settling()
            for key, screen, _monitor in _screens():
                if settling and key in self.last_images:
                    result[key] = self.last_images[key]
                    continue
                url = workspace.desktopImageURLForScreen_(screen)
                result[key] = url.path() if url is not None and url.isFileURL() else ""
            return result

        return on_main(read)

    # -- notifications

    def _notification_center(self):
        if self._center is None:
            from UserNotifications import UNUserNotificationCenter
            center = UNUserNotificationCenter.currentNotificationCenter()
            self._delegate = _notification_delegate().alloc().init()
            self._delegate.platform = self
            center.setDelegate_(self._delegate)
            self._center = center
        return self._center

    def notify(self, title, body, actions=(), image=None, on_click=None):
        if self.packaged:
            try:
                self._notify_center(title, body, actions, image, on_click)
                return
            except Exception as exc:  # noqa: BLE001
                print(f"museum-wallpapers: notification failed ({exc}); using AppleScript", file=sys.stderr)
        self._notify_script(title, body)

    def _notify_center(self, title, body, actions, image, on_click):
        from UserNotifications import (UNMutableNotificationContent, UNNotificationAction,
                                       UNNotificationAttachment, UNNotificationCategory, UNNotificationRequest)
        with self._notify_lock:
            center = self._notification_center()
            content = UNMutableNotificationContent.alloc().init()
            content.setTitle_(title)
            content.setBody_(body)
            if actions:
                buttons = [UNNotificationAction.actionWithIdentifier_title_options_(f"action-{n}", label,
                                                                                   UN_ACTION_FOREGROUND)
                           for n, (label, _callback) in enumerate(actions)]
                category = UNNotificationCategory.categoryWithIdentifier_actions_intentIdentifiers_options_(
                    NOTIFICATION_CATEGORY, buttons, [], 0)
                center.setNotificationCategories_({category})
                content.setCategoryIdentifier_(NOTIFICATION_CATEGORY)
            if image and Path(image).exists():
                # The system moves an attachment into its own store: give it a copy.
                copy = Path(tempfile.mkdtemp(prefix="museum-wallpapers-")) / Path(image).name
                shutil.copy2(image, copy)
                from Foundation import NSURL
                attachment, _error = UNNotificationAttachment.attachmentWithIdentifier_URL_options_error_(
                    "painting", NSURL.fileURLWithPath_(str(copy)), None, None)
                if attachment is not None:
                    content.setAttachments_([attachment])
            identifier = str(uuid.uuid4())
            self._callbacks[identifier] = ({f"action-{n}": callback for n, (_l, callback) in enumerate(actions)},
                                           on_click)
            for old in list(self._callbacks)[:-10]:
                del self._callbacks[old]
            request = UNNotificationRequest.requestWithIdentifier_content_trigger_(identifier, content, None)

            def added(error):
                if error is not None:
                    print(f"museum-wallpapers: notification not shown: {error.localizedDescription()}",
                          file=sys.stderr)

            center.addNotificationRequest_withCompletionHandler_(request, added)

    def _respond(self, identifier, action):
        buttons, on_click = self._callbacks.get(identifier, ({}, None))
        callback = buttons.get(action)
        if callback is None and action == "com.apple.UNNotificationDefaultActionIdentifier":
            callback = on_click
        if callback:
            threading.Thread(target=callback, daemon=True).start()

    @staticmethod
    def _notify_script(title, body):
        script = ["-e", "on run argv", "-e", "display notification (item 2 of argv) with title (item 1 of argv)",
                  "-e", "end run"]
        subprocess.run(["osascript", *script, title, body[:400]], check=False, capture_output=True, timeout=20)

    # -- shell

    def open_url(self, url):
        subprocess.run(["open", url], check=False, timeout=20)

    def open_folder(self, path):
        Path(path).mkdir(parents=True, exist_ok=True)
        subprocess.run(["open", str(path)], check=False, timeout=20)

    def ui_language(self):
        try:
            from Foundation import NSLocale
            preferred = NSLocale.preferredLanguages()
            if preferred:
                return language_code(str(preferred[0])) or "en"
        except Exception:  # noqa: BLE001
            pass
        return super().ui_language()

    def caption_fonts(self):
        return mac_caption_fonts()

    # -- open at login

    def launched_at_startup(self):
        if self.launched_by_login:
            return True
        try:
            return time.clock_gettime(time.CLOCK_UPTIME_RAW) < LOGIN_SECONDS
        except (AttributeError, OSError):
            return False

    @staticmethod
    def _service():
        """SMAppService for this app bundle (macOS 13+), or None."""
        if bundle_path() is None:
            return None
        try:
            from ServiceManagement import SMAppService
        except ImportError:
            return None
        return SMAppService.mainAppService()

    @staticmethod
    def launch_agent():
        return Path.home() / "Library" / "LaunchAgents" / f"{BUNDLE_ID}.plist"

    @staticmethod
    def launch_command():
        bundle = bundle_path()
        if bundle is not None:
            return [str(Path(sys.executable).resolve()), "--background"]
        return [sys.executable, "-m", "museum_wallpapers", "--background"]

    def autostart_enabled(self):
        service = self._service()
        if service is not None:
            return service.status() == SM_STATUS_ENABLED
        return self.launch_agent().exists()

    def set_autostart(self, enabled):
        """Returns False when macOS keeps it off: the user has to allow it
        in System Settings → General → Login Items (opened for them)."""
        service = self._service()
        if service is not None:
            if not enabled:
                service.unregisterAndReturnError_(None)
                return True
            ok, error = service.registerAndReturnError_(None)
            if service.status() == SM_STATUS_REQUIRES_APPROVAL:
                from ServiceManagement import SMAppService
                SMAppService.openSystemSettingsLoginItems()
                return False
            if not ok:
                raise OSError(str(error.localizedDescription() if error else "could not register"))
            return True
        agent = self.launch_agent()
        if not enabled:
            agent.unlink(missing_ok=True)
            return True
        agent.parent.mkdir(parents=True, exist_ok=True)
        environment = {k: os.environ[k] for k in ("PYTHONPATH",) if os.environ.get(k)}
        plist = {"Label": BUNDLE_ID, "ProgramArguments": self.launch_command(), "RunAtLoad": True,
                 "ProcessType": "Interactive"}
        if environment:
            plist["EnvironmentVariables"] = environment
        agent.write_bytes(plistlib.dumps(plist))
        return True


_delegate_class = None


def _notification_delegate():
    """The UNUserNotificationCenter delegate class, defined once (an
    Objective-C class can be registered only once per process)."""
    global _delegate_class
    if _delegate_class is None:
        # Loads the completion handlers' block signatures, which PyObjC needs
        # to call them. The class must not declare the formal protocol
        # (protocols=[...]): that would replace those signatures with ones
        # without the blocks' arguments, and calling a handler would crash.
        import UserNotifications  # noqa: F401
        from Foundation import NSObject

        class MuseumNotificationDelegate(NSObject):
            def userNotificationCenter_willPresentNotification_withCompletionHandler_(self, _c, _n, handler):
                handler(UN_PRESENT_BANNER | UN_PRESENT_LIST)

            def userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler_(self, _c, response,
                                                                                            handler):
                try:
                    self.platform._respond(str(response.notification().request().identifier()),
                                           str(response.actionIdentifier()))
                finally:
                    handler()

        _delegate_class = MuseumNotificationDelegate
    return _delegate_class
