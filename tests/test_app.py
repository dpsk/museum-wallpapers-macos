"""The menu bar app's logic: menu, tooltip, card data and actions, with a
stand-in view (no AppKit needed)."""

import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from helpers import FakePlatform, app_module, core, make_jpeg, strings


class FakeView(app_module.NullView):
    def __init__(self):
        self.statuses = []
        self.cards = []
        self.card_open = False
        self.quit_called = False

    def update_status(self, tooltip, active, busy):
        self.statuses.append((tooltip, active, busy))

    def show_card(self, data):
        self.card_open = True
        self.cards.append(data)

    def update_card(self, data):
        self.cards.append(data)

    def quit(self):
        self.quit_called = True


def flatten(items, depth=0):
    for item in items:
        if item.separator:
            continue
        yield depth, item
        if item.submenu:
            yield from flatten(item.submenu, depth + 1)


def wait_for(condition, seconds=3):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        if condition():
            return True
        time.sleep(0.02)
    return condition()


class WallPlatform(FakePlatform):
    """FakePlatform that, like macOS, reports wallpapers per screen."""

    def __init__(self):
        super().__init__()
        self.last_images = {}

    def set_wallpaper(self, images):
        super().set_wallpaper(images)
        self.last_images = {key: str(value) for key, value in images.items()}

    def wallpapers(self):
        return {"m1": str(self.current) if self.current else ""}


class AppTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(os.path.realpath(self.tmp.name))
        self.cache, self.state = root / "cache", root / "state"
        self.platform = WallPlatform()
        for patch in (mock.patch.object(core, "CACHE", self.cache),
                      mock.patch.object(core, "QUEUE", self.cache / "queue"),
                      mock.patch.object(core, "DISPLAY", self.cache / "display"),
                      mock.patch.object(core, "STATE", self.state),
                      mock.patch.object(core, "SETTINGS", root / "settings.json"),
                      mock.patch.object(core, "PLATFORM", self.platform),
                      mock.patch.object(core, "RUNNER", lambda command: None)):
            patch.start()
        core.save_setting("saveDir", str(root / "saved"))
        self.view = FakeView()
        self.app = app_module.App(view=self.view)
        self.app.platform = self.platform

    def tearDown(self):
        mock.patch.stopall()
        self.tmp.cleanup()

    def show_painting(self):
        painting = make_jpeg(self.cache / "commons-5.jpg")
        core.write_json(painting.with_suffix(".json"), {
            "id": "Q1", "title": "The Ninth Wave", "artist": "Ivan Aivazovsky", "artistId": "Q186212",
            "year": "1850", "museum": "Russian Museum", "movement": "Romanticism", "movementId": "Q37068",
            "summary": "A storm at sea.", "url": "https://en.wikipedia.org/wiki/The_Ninth_Wave",
            "language": "en", "summaryLanguage": "en"})
        self.platform.current = painting
        core.record(painting)
        return painting

    def items(self):
        return {item.title: item for _, item in flatten(self.app.menu())}

    def test_menu_without_a_painting(self):
        titles = [item.title for _, item in flatten(self.app.menu())]
        self.assertEqual(titles[:4], ["About this painting", "Next painting", "Read more", "Save to collection"])
        self.assertFalse(self.items()["Read more"].enabled)
        self.assertIn("Open at login", titles)
        self.assertEqual(titles[-1], "Quit Museum Wallpapers")

    def test_settings_from_the_menu(self):
        items = self.items()
        self.assertTrue(items["1 hour"].checked)
        items["15 minutes"].action()
        items = self.items()
        self.assertTrue(items["15 minutes"].checked)
        self.assertFalse(items["1 hour"].checked)
        items["Dark wall"].action()
        items["Top left"].action()
        items["Notify when it changes"].action()
        config = core.load_config()
        self.assertEqual((config["intervalMinutes"], config["fit"], config["caption"], config["notifyOnChange"]),
                         (15, "wall", "top-left", True))
        self.assertTrue(self.app.wake.is_set())

    def test_menu_in_russian(self):
        core.save_setting("language", "ru")
        titles = [item.title for _, item in flatten(self.app.menu())]
        self.assertIn("Следующая картина", titles)
        self.assertIn("Открывать при входе", titles)
        self.assertIn("3 часа", titles)
        self.assertTrue(self.items()["Русский"].checked)

    def test_language_preference_from_the_menu(self):
        items = self.items()
        self.assertTrue(items["Only described ones"].checked)
        self.assertTrue(items["Has a Wikipedia article in my language"].checked)
        items["Described ones first"].action()
        items["Has a title in my language"].action()
        config = core.load_config()
        self.assertEqual((config["localized"], config["localizedBy"]), ("prefer", "title"))
        titles = [item.title for _, item in flatten(self.app.menu())]
        self.assertLess(titles.index("Language"), titles.index("In my language"))
        self.assertLess(titles.index("In my language"), titles.index("Described means"))

    def test_menu_in_every_language(self):
        english = set(item.title for _, item in flatten(self.app.menu()))
        for language in core.LANGUAGES[1:]:
            core.save_setting("language", language)
            titles = [item.title for _, item in flatten(self.app.menu())]
            for title in titles:
                self.assertNotRegex(title, r"^[a-z_]+$|\{", f"{language}: {title}")
            if language != "en":
                # Everything but names (painters, languages, the app) is translated.
                same = set(titles) & english - set(strings.LANGUAGE_NAMES.values()) - {"Museum Wallpapers"}
                self.assertLessEqual(len(same), 3, f"{language}: {sorted(same)}")

    def test_open_at_login_toggles(self):
        self.platform.autostart = False
        self.platform.autostart_enabled = lambda: self.platform.autostart
        self.platform.set_autostart = lambda wanted: setattr(self.platform, "autostart", wanted) or True
        self.items()["Open at login"].action()
        self.assertTrue(self.items()["Open at login"].checked)

    def test_blocked_login_item_explains_where_to_allow_it(self):
        self.platform.autostart_enabled = lambda: False
        self.platform.set_autostart = lambda wanted: False
        self.app.toggle_autostart()
        self.assertIn("Login Items", self.platform.notifications[-1][1])

    def test_tooltip_and_card_for_a_painting(self):
        self.show_painting()
        self.view.card_open = True
        self.app.refresh()
        self.assertEqual(self.view.statuses[-1], ("The Ninth Wave — Ivan Aivazovsky", True, False))
        data = self.view.cards[-1]
        self.assertEqual(data["byline"], "Ivan Aivazovsky · 1850")
        self.assertEqual(data["place"], "Russian Museum · Romanticism")
        self.assertTrue(data["preview"].startswith("data:image/jpeg;base64,"))
        self.assertEqual(data["more"][0], {"label": "More by Ivan Aivazovsky", "action": "more_by",
                                           "args": ["Q186212", "Ivan Aivazovsky"]})
        self.assertTrue(data["canSave"])
        self.assertTrue(self.items()["Read more"].enabled)

    def test_long_titles_fit_the_tooltip(self):
        painting = self.show_painting()
        core.write_json(painting.with_suffix(".json"), {"title": "T" * 200, "artist": "A"})
        self.app.refresh()
        self.assertLessEqual(len(self.view.statuses[-1][0]), 120)

    def test_temporary_filter_shows_in_menu_and_card(self):
        self.show_painting()
        core.write_json(self.state / "filter.json", {"artists": [{"id": "Q186212", "label": "Ivan Aivazovsky"}],
                                                     "movements": [], "genres": []})
        self.assertIn("Showing only: Ivan Aivazovsky", self.items())
        self.assertIn("Show all paintings again", self.items())
        self.assertEqual(self.app.card_data()["filter"], "Filter: Ivan Aivazovsky")

    def test_card_buttons(self):
        self.show_painting()
        with mock.patch.object(core, "cmd_next") as cmd_next:
            self.app.card_action("more_by", ["Q186212", "Ivan Aivazovsky"])
            self.assertTrue(wait_for(lambda: cmd_next.called))
        self.assertEqual(core.read_json(self.state / "filter.json")["artists"],
                         [{"id": "Q186212", "label": "Ivan Aivazovsky"}])
        self.assertTrue(wait_for(lambda: not self.app.switching.locked()))
        # Settings are not changed from the card any more.
        self.app.card_action("set", ["intervalMinutes", 180.0])
        self.assertEqual(core.load_config()["intervalMinutes"], 60)

    def test_next_ignores_presses_while_switching(self):
        with mock.patch.object(core, "cmd_next", side_effect=lambda *_: time.sleep(0.2)) as cmd_next:
            self.app.next()
            self.app.next()
            self.assertTrue(self.view.statuses[0][2])  # busy right away
            self.assertTrue(wait_for(lambda: not self.app.switching.locked()))
        cmd_next.assert_called_once()

    def test_first_tick_shows_a_painting_with_its_caption(self):
        """The whole path the scheduler takes, with Wikimedia replaced by a
        fetch that drops one painting into the queue."""
        def fetch(_config, unfiltered=False, note=None):
            image = make_jpeg(self.cache / "queue" / "commons-9.jpg", size=(800, 500))
            core.write_json(image.with_suffix(".json"), {"title": "Poppies", "artist": "Claude Monet", "year": "1873",
                                                         "filter": core.queue_key(core.load_config())})
            return image

        with mock.patch.object(core, "fetch_next", side_effect=fetch), \
                mock.patch.object(self.app, "run_command") as run_command, \
                mock.patch.object(core, "RUNNER", lambda command: self.app.run_command(command)):
            self.app.tick()
        wall = self.platform.walls[-1]["m1"]
        self.assertEqual(wall.parent, self.cache / "display")
        self.assertIn(".blur.bottom-right-en.384x216.", wall.name)
        self.assertEqual(self.view.statuses[-1][0], "Poppies — Claude Monet")
        run_command.assert_called_with("prefetch")
        with mock.patch.object(core, "fetch_next") as fetch_again, mock.patch.object(self.app, "run_command"):
            self.app.tick()
        fetch_again.assert_not_called()

    def test_another_space_gets_the_painting(self):
        painting = self.show_painting()
        config = core.load_config()
        shown = core.show(painting, config)
        core.record(shown, original=painting, config=config)
        self.platform.current = Path("/System/Library/Desktop Pictures/Sonoma.heic")  # what the new Space shows
        self.app.reapply()
        self.assertEqual(self.platform.current, shown)
        count = len(self.platform.walls)
        self.app.reapply()  # already showing it: nothing to do
        self.assertEqual(len(self.platform.walls), count)

    def test_helper_commands_run_on_threads(self):
        with mock.patch.object(core, "cmd_prefetch") as prefetch:
            self.app.run_command("prefetch")
            self.assertTrue(wait_for(lambda: prefetch.called))

    def test_quit(self):
        self.app.quit()
        self.assertTrue(self.view.quit_called)
        self.assertTrue(self.app.stop.is_set())


if __name__ == "__main__":
    unittest.main()
