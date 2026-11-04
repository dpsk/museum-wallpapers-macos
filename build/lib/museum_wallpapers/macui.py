"""The AppKit side of the menu bar app: the status item (left click opens the
card, right or Control-click the menu, middle click the next painting, as on
the Omarchy bar), the card in a popover (a WKWebView showing card.py's page),
and what macOS reports: another Space, waking from sleep, screens changing,
a second launch.

`MacUI` is plain Python and owns the windows; `Bridge` is the Objective-C
object AppKit and WebKit call, and only forwards to it. Everything here runs
on the main thread; MacUI's public methods may be called from any thread."""

import os
import sys
import traceback

import objc
from AppKit import (NSApp, NSApplication, NSApplicationActivationPolicyAccessory,
                    NSApplicationDidChangeScreenParametersNotification, NSControlStateValueOff,
                    NSControlStateValueOn, NSEvent, NSEventMaskLeftMouseUp, NSEventMaskOtherMouseUp,
                    NSEventMaskRightMouseUp, NSEventModifierFlagControl, NSEventTypeOtherMouseUp,
                    NSEventTypeRightMouseUp, NSImage, NSMenu, NSMenuItem, NSPopover, NSStatusBar,
                    NSVariableStatusItemLength, NSViewController, NSWorkspace,
                    NSWorkspaceActiveSpaceDidChangeNotification, NSWorkspaceDidWakeNotification)
from Foundation import (NSAppleEventManager, NSData, NSDistributedNotificationCenter, NSMakeRect, NSMakeSize,
                        NSNotificationCenter, NSObject)
from PyObjCTools import AppHelper
from WebKit import WKWebView, WKWebViewConfiguration

from . import APP_NAME, card, resources
from .app import SHOW_NOTIFICATION
from .platforms import macos

NS_MIN_Y_EDGE = 1  # the popover hangs below the status item
POPOVER_TRANSIENT = 1  # closes on a click elsewhere
NAVIGATION_CANCEL, NAVIGATION_ALLOW = 0, 1
SHOW_TIMEOUT = 0.6  # seconds to wait for the page to report its height


def fourcc(code):
    return int.from_bytes(code.encode("ascii"), "big")


def log_exception(where):
    print(f"museum-wallpapers: {where}: " + traceback.format_exc(), file=sys.stderr)


def ns_image(pil_image, points):
    data = resources.png_bytes(pil_image)
    image = NSImage.alloc().initWithData_(NSData.dataWithBytes_length_(data, len(data)))
    image.setSize_(NSMakeSize(points, points))
    image.setTemplate_(True)
    return image


def signal_running():
    """Ask the running app to open its card (from a second launch)."""
    NSDistributedNotificationCenter.defaultCenter().postNotificationName_object_userInfo_deliverImmediately_(
        SHOW_NOTIFICATION, None, None, True)


class Bridge(NSObject, protocols=[objc.protocolNamed("WKScriptMessageHandler"),
                                  objc.protocolNamed("NSPopoverDelegate")]):
    """Receives AppKit and WebKit callbacks and passes them to `self.ui`.

    WKNavigationDelegate is implemented without being declared: declaring a
    protocol whose methods take blocks hides the blocks' signatures from
    PyObjC, and calling decisionHandler then crashes the app."""

    # -- application

    def applicationWillFinishLaunching_(self, _note):
        self.ui.check_launch_event()

    def applicationDidFinishLaunching_(self, _note):
        self.ui.did_launch()

    def applicationShouldHandleReopen_hasVisibleWindows_(self, _app, _visible):
        self.ui.call(self.ui.app.about)
        return True

    def applicationWillTerminate_(self, _note):
        self.ui.app.stop.set()

    # -- status item and menu

    def statusClicked_(self, _sender):
        self.ui.call(self.ui.status_clicked)

    def menuItemClicked_(self, sender):
        self.ui.call(self.ui.menu_item_clicked, int(sender.tag()))

    # -- card

    def userContentController_didReceiveScriptMessage_(self, _controller, message):
        self.ui.call(self.ui.card_message, message.body())

    def webView_didFinishNavigation_(self, _web, _navigation):
        self.ui.call(self.ui.card_loaded)

    def webView_decidePolicyForNavigationAction_decisionHandler_(self, _web, action, handler):
        # Only the card page itself: nothing navigates inside the popover.
        url = action.request().URL()
        allowed = url is None or str(url.absoluteString()) in ("", "about:blank")
        handler(NAVIGATION_ALLOW if allowed else NAVIGATION_CANCEL)

    def popoverDidClose_(self, _note):
        self.ui.call(self.ui.card_closed)

    # -- what macOS reports

    def spaceChanged_(self, _note):
        self.ui.call(self.ui.app.space_changed)

    def didWake_(self, _note):
        self.ui.call(self.ui.app.woke)

    def screensChanged_(self, _note):
        self.ui.call(self.ui.app.screens_changed)

    def showRequested_(self, _note):
        self.ui.call(self.ui.app.about)


class MacUI:
    """The app's view (see app.NullView): status item, menu and card."""

    def __init__(self, app):
        self.app = app
        self.bridge = Bridge.alloc().init()
        self.bridge.ui = self
        self.item = None
        self.icons = {}
        self.callbacks = []
        self.popover = None
        self.web = None
        self.loaded = False
        self.pending = None  # data to render once the page has loaded
        self.presenting = False  # waiting for the page's height to show the popover
        self.card_open = False

    @staticmethod
    def call(work, *args):
        """Run a callback, logging instead of letting an exception reach AppKit."""
        try:
            work(*args)
        except Exception:  # noqa: BLE001
            log_exception(getattr(work, "__name__", "callback"))

    # -- the view interface (any thread)

    def update_status(self, tooltip, active, busy):
        AppHelper.callAfter(self.call, self._update_status, tooltip, active, busy)

    def show_card(self, data):
        AppHelper.callAfter(self.call, self._show_card, data)

    def update_card(self, data):
        AppHelper.callAfter(self.call, self._render, data)

    def quit(self):
        AppHelper.callAfter(NSApp.terminate_, None)

    # -- launch

    def check_launch_event(self):
        """Opened at login (a login item) rather than by the user?"""
        try:
            event = NSAppleEventManager.sharedAppleEventManager().currentAppleEvent()
            if event is not None and event.eventID() == fourcc("oapp"):
                prop = event.paramDescriptorForKeyword_(fourcc("prdt"))
                if prop is not None and prop.enumCodeValue() == fourcc("lgit"):
                    self.app.platform.launched_by_login = True
        except Exception:  # noqa: BLE001
            log_exception("launch event")

    def did_launch(self):
        self._edit_menu()
        self.icons = {False: ns_image(resources.menu_bar_icon(), 18),
                      True: ns_image(resources.menu_bar_icon(busy=True), 18)}
        self.item = NSStatusBar.systemStatusBar().statusItemWithLength_(NSVariableStatusItemLength)
        self.item.setAutosaveName_("MuseumWallpapers")
        button = self.item.button()
        button.setImage_(self.icons[False])
        button.setToolTip_(APP_NAME)
        button.setTarget_(self.bridge)
        button.setAction_("statusClicked:")
        button.sendActionOn_(NSEventMaskLeftMouseUp | NSEventMaskRightMouseUp | NSEventMaskOtherMouseUp)

        workspace = NSWorkspace.sharedWorkspace().notificationCenter()
        workspace.addObserver_selector_name_object_(self.bridge, "spaceChanged:",
                                                    NSWorkspaceActiveSpaceDidChangeNotification, None)
        workspace.addObserver_selector_name_object_(self.bridge, "didWake:", NSWorkspaceDidWakeNotification, None)
        NSNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self.bridge, "screensChanged:", NSApplicationDidChangeScreenParametersNotification, None)
        NSDistributedNotificationCenter.defaultCenter().addObserver_selector_name_object_(
            self.bridge, "showRequested:", SHOW_NOTIFICATION, None)

        macos.MAIN_LOOP.set()
        self.app.started()

    def _edit_menu(self):
        """A main menu nobody sees, so ⌘C and ⌘A work in the card's text."""
        main = NSMenu.alloc().init()
        for title, items in ((APP_NAME, [("Quit", "terminate:", "q")]),
                             ("Edit", [("Copy", "copy:", "c"), ("Select All", "selectAll:", "a")])):
            holder = NSMenuItem.alloc().init()
            submenu = NSMenu.alloc().initWithTitle_(title)
            for label, action, key in items:
                submenu.addItemWithTitle_action_keyEquivalent_(label, action, key)
            holder.setSubmenu_(submenu)
            main.addItem_(holder)
        NSApp.setMainMenu_(main)

    # -- status item

    def _update_status(self, tooltip, active, busy):
        if self.item is None:
            return
        button = self.item.button()
        button.setImage_(self.icons[bool(busy)])
        button.setAppearsDisabled_(not active)
        button.setToolTip_(tooltip)

    def status_clicked(self):
        event = NSApp.currentEvent()
        kind = event.type() if event is not None else None
        if kind == NSEventTypeRightMouseUp or (event is not None
                                               and event.modifierFlags() & NSEventModifierFlagControl):
            self.show_menu()
        elif kind == NSEventTypeOtherMouseUp:
            self.app.next()
        elif self.popover is not None and self.popover.isShown():
            self.popover.performClose_(None)
        else:
            self.app.about()

    # -- menu

    def build_menu(self, items, top=True):
        if top:
            self.callbacks = []
        menu = NSMenu.alloc().initWithTitle_(APP_NAME)
        menu.setAutoenablesItems_(False)
        for entry in items:
            if entry.separator:
                menu.addItem_(NSMenuItem.separatorItem())
                continue
            item = NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                entry.title, "menuItemClicked:" if entry.action else None, "")
            if entry.action:
                item.setTarget_(self.bridge)
                item.setTag_(len(self.callbacks))
                self.callbacks.append(entry.action)
            item.setEnabled_(entry.enabled)
            item.setState_(NSControlStateValueOn if entry.checked else NSControlStateValueOff)
            if entry.submenu:
                item.setSubmenu_(self.build_menu(entry.submenu, top=False))
            menu.addItem_(item)
        return menu

    def show_menu(self, at_mouse=False):
        menu = self.build_menu(self.app.menu())
        if at_mouse:
            menu.popUpMenuPositioningItem_atLocation_inView_(None, NSEvent.mouseLocation(), None)
            return
        # The standard way to drop a menu from a status item that also has a click action.
        self.item.setMenu_(menu)
        self.item.button().performClick_(None)
        self.item.setMenu_(None)

    def menu_item_clicked(self, tag):
        if 0 <= tag < len(self.callbacks):
            self.callbacks[tag]()

    # -- card

    def _ensure_card(self):
        if self.popover is not None:
            return
        configuration = WKWebViewConfiguration.alloc().init()
        configuration.userContentController().addScriptMessageHandler_name_(self.bridge, "museum")
        web = WKWebView.alloc().initWithFrame_configuration_(NSMakeRect(0, 0, card.WIDTH, 560), configuration)
        web.setValue_forKey_(False, "drawsBackground")
        web.setNavigationDelegate_(self.bridge)
        controller = NSViewController.alloc().init()
        controller.setView_(web)
        popover = NSPopover.alloc().init()
        popover.setContentViewController_(controller)
        popover.setBehavior_(POPOVER_TRANSIENT)
        popover.setAnimates_(True)
        popover.setDelegate_(self.bridge)
        popover.setContentSize_(NSMakeSize(card.WIDTH, 560))
        try:
            popover.setValue_forKeyPath_(True, "shouldHideAnchor")  # a panel under the bar, like Omarchy's
        except Exception:  # noqa: BLE001 - an older or newer AppKit without it: the arrow stays
            pass
        self.popover, self.web = popover, web

    def _show_card(self, data):
        self._ensure_card()
        if self.popover.isShown():
            self._render(data)
            return
        self.presenting = True
        if self.loaded:
            self._render(data)
        else:
            self.pending = data
            self.web.loadHTMLString_baseURL_(card.page(data), None)
        AppHelper.callLater(SHOW_TIMEOUT, self.call, self._present)

    def _render(self, data):
        if self.web is None:
            return
        if not self.loaded:
            self.pending = data
            return
        self.web.evaluateJavaScript_completionHandler_(f"render({card.script_json(data)})", None)

    def card_loaded(self):
        self.loaded = True
        if self.pending is not None:
            data, self.pending = self.pending, None
            self._render(data)

    def _present(self):
        if not self.presenting or self.item is None:
            return
        self.presenting = False
        button = self.item.button()
        try:
            NSApp.activate()
        except AttributeError:  # macOS 13
            NSApp.activateIgnoringOtherApps_(True)
        self.popover.showRelativeToRect_ofView_preferredEdge_(button.bounds(), button, NS_MIN_Y_EDGE)
        button.highlight_(True)
        self.card_open = True
        # The card may have changed while it was hidden (a switch in the meantime).
        self.app.refresh()
        if os.environ.get("MUSEUM_WALLPAPERS_SNAPSHOT"):
            AppHelper.callLater(2.0, self.call, self.snapshot, os.environ["MUSEUM_WALLPAPERS_SNAPSHOT"])

    def snapshot(self, path):
        """Development aid: the card as a PNG (only the card's own pixels)."""
        def done(image, error):
            if image is None:
                print(f"museum-wallpapers: snapshot failed: {error}", file=sys.stderr)
                return
            from AppKit import NSBitmapImageFileTypePNG, NSBitmapImageRep
            rep = NSBitmapImageRep.imageRepWithData_(image.TIFFRepresentation())
            rep.representationUsingType_properties_(NSBitmapImageFileTypePNG, {}).writeToFile_atomically_(path, True)
            print(f"museum-wallpapers: snapshot written to {path}", file=sys.stderr)

        self.web.takeSnapshotWithConfiguration_completionHandler_(None, done)

    def _resize(self, height):
        screen = self.item.button().window().screen() if self.item is not None else None
        limit = int(screen.visibleFrame().size.height) - 24 if screen is not None else 900
        self.popover.setContentSize_(NSMakeSize(card.WIDTH, max(120, min(int(height), limit))))
        if self.presenting:
            self._present()

    def card_message(self, body):
        action = str(body["action"])
        args = [_python(x) for x in (body["args"] or [])]
        if action == "size":
            self._resize(args[0])
        elif action == "settings":
            self.show_menu(at_mouse=True)
        elif action == "open":
            self.popover.performClose_(None)
            self.app.card_action("open", args)
        else:
            self.app.card_action(action, args)

    def card_closed(self):
        self.card_open = False
        if self.item is not None:
            self.item.button().highlight_(False)


def _python(value):
    """An NSString or NSNumber from the page as a plain Python value."""
    if isinstance(value, str):
        return str(value)
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return int(value) if value.is_integer() else float(value)
    return value


def run(app):
    """Start the menu bar app; returns when it quits."""
    application = NSApplication.sharedApplication()
    ui = MacUI(app)
    app.view = ui
    application.setDelegate_(ui.bridge)
    application.setActivationPolicy_(NSApplicationActivationPolicyAccessory)
    interactive = bool(sys.stdin) and sys.stdin.isatty()
    AppHelper.runEventLoop(installInterrupt=interactive)
    return 0
