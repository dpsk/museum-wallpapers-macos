"""The macOS layer: geometry anywhere; NSScreen, NSWorkspace and the
fonts only on a Mac; setting the real wallpaper only with
MUSEUM_WALLPAPERS_LIVE_WALLPAPER=1 (CI does it on its runner)."""

import os
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

import helpers  # noqa: F401 - the throwaway home

ON_MAC = sys.platform == "darwin"


class InsetTest(unittest.TestCase):
    def test_menu_bar_and_dock(self):
        from museum_wallpapers.platforms.macos import inset_of
        # 1728x1117 points at 2x: a 33 pt menu bar on top, a 60 pt Dock at the bottom.
        frame, visible = ((0, 0), (1728, 1117)), ((0, 60), (1728, 1024))
        self.assertEqual(inset_of(frame, visible, 2.0), (0, 66, 0, 120))

    def test_dock_on_the_left_of_a_second_screen(self):
        from museum_wallpapers.platforms.macos import inset_of
        frame, visible = ((1728, -200), (2560, 1440)), ((1798, -200), (2490, 1415))
        self.assertEqual(inset_of(frame, visible, 1.0), (70, 25, 0, 0))


@unittest.skipUnless(ON_MAC, "macOS only")
class MacPlatformTest(unittest.TestCase):
    def setUp(self):
        from museum_wallpapers.platforms.macos import MacPlatform
        self.platform = MacPlatform()

    def test_screens(self):
        found = self.platform.monitors()
        self.assertTrue(found)
        for monitor in found:
            self.assertGreater(monitor.width, 0)
            self.assertTrue(all(edge >= 0 for edge in monitor.inset))

    def test_fonts_exist(self):
        fonts = self.platform.caption_fonts()
        self.assertTrue(fonts[0] and Path(fonts[0]).exists())
        self.assertTrue(fonts[1] and Path(fonts[1]).exists())

    def test_language(self):
        self.assertRegex(self.platform.ui_language(), r"^[a-z]{2,3}$")

    def test_paths_in_library(self):
        with mock.patch.dict(os.environ, {"MUSEUM_WALLPAPERS_HOME": ""}):
            paths = self.platform.paths()
            log = self.platform.log_file(paths["state"])
        self.assertIn("Library/Application Support/MuseumWallpapers", str(paths["config"]))
        self.assertIn("Library/Caches/MuseumWallpapers", str(paths["cache"]))
        self.assertIn("Library/Logs/MuseumWallpapers", str(log))

    def test_launch_agent_in_development(self):
        with tempfile.TemporaryDirectory() as tmp, mock.patch("pathlib.Path.home", return_value=Path(tmp)):
            self.assertFalse(self.platform.autostart_enabled())
            self.assertTrue(self.platform.set_autostart(True))
            import plistlib
            plist = plistlib.loads(self.platform.launch_agent().read_bytes())
            self.assertEqual(plist["ProgramArguments"][-3:], ["-m", "museum_wallpapers", "--background"])
            self.assertTrue(self.platform.autostart_enabled())
            self.platform.set_autostart(False)
            self.assertFalse(self.platform.autostart_enabled())

    def test_card_ui_module_loads(self):
        from museum_wallpapers import macui
        self.assertEqual(macui.fourcc("lgit"), 0x6C676974)
        self.assertEqual(macui._python(60.0), 60)

    def test_delegates_can_call_their_completion_handlers(self):
        """PyObjC must see the block signatures, or calling a handler that
        WebKit or UserNotifications passes in crashes the whole app."""
        from museum_wallpapers import macui
        from museum_wallpapers.platforms import macos
        checks = ((macui.Bridge, "webView_decidePolicyForNavigationAction_decisionHandler_"),
                  (macos._notification_delegate(), "userNotificationCenter_willPresentNotification_withCompletionHandler_"),
                  (macos._notification_delegate(),
                   "userNotificationCenter_didReceiveNotificationResponse_withCompletionHandler_"))
        for cls, name in checks:
            block = getattr(cls, name).__metadata__()["arguments"][4]
            self.assertIn("callable", block, f"{cls.__name__}.{name}")

    def test_card_loads_in_a_web_view(self):
        """The real WKWebView: the page loads (navigation allowed) and
        reports its height through the script message handler."""
        from AppKit import NSApplication
        from Foundation import NSDate, NSRunLoop
        from museum_wallpapers import app as app_module, card, core, macui
        NSApplication.sharedApplication()
        ui = macui.MacUI(app_module.App())
        messages = []
        ui.card_message = messages.append
        ui._ensure_card()
        ui.web.loadHTMLString_baseURL_(card.page(card.data(core.load_config(), {"active": False})), None)
        deadline = NSDate.dateWithTimeIntervalSinceNow_(10)
        while not any(str(m["action"]) == "size" for m in messages) and NSDate.date().compare_(deadline) < 0:
            NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.1))
        self.assertTrue(ui.loaded)
        size = [m for m in messages if str(m["action"]) == "size"][0]
        self.assertGreater(int(size["args"][0]), 150)

    @unittest.skipUnless(os.environ.get("MUSEUM_WALLPAPERS_LIVE_WALLPAPER") == "1", "changes the real wallpaper")
    def test_live_wallpaper_round_trip(self):
        from helpers import make_jpeg
        before = self.platform.wallpapers()
        print("wallpapers before:", before)
        try:
            with tempfile.TemporaryDirectory() as tmp:
                images = {}
                for monitor in self.platform.monitors():
                    images[monitor.id] = make_jpeg(Path(tmp) / f"live-{monitor.id}.jpg",
                                                   size=(monitor.width // 4, monitor.height // 4))
                self.platform.set_wallpaper(images)
                # While macOS settles, reads answer with what was set; then ask macOS itself.
                self.assertEqual(self.platform.wallpapers(), {k: str(Path(v).resolve()) for k, v in images.items()})
                self.platform._set_at = float("-inf")
                deadline, shown = time.monotonic() + 10, {}
                while time.monotonic() < deadline:
                    shown = self.platform.wallpapers()
                    if all(os.path.realpath(shown.get(k) or "/") == os.path.realpath(v) for k, v in images.items()):
                        break
                    time.sleep(0.5)
                print("wallpapers after:", shown)
                for key, path in images.items():
                    self.assertEqual(os.path.realpath(shown[key]), os.path.realpath(path))
                self.assertEqual(os.path.realpath(self.platform.current_wallpaper()),
                                 os.path.realpath(images[max(self.platform.monitors(),
                                                             key=lambda m: m.width * m.height).id]))
        finally:
            restore = {key: path for key, path in before.items() if path and Path(path).exists()}
            if restore:
                self.platform.set_wallpaper(restore)


if __name__ == "__main__":
    unittest.main()
