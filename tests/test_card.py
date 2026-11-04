"""The card's data and page."""

import json
import re
import unittest

from helpers import core, make_jpeg  # noqa: F401 - sets up the test home
from museum_wallpapers import card

CONFIG = core.normalize_config({"language": "en"})
INFO = {"title": "The Fortune Teller", "artist": "Caravaggio", "artistId": "Q42207", "year": "1594",
        "museum": "Capitoline Museums", "movement": "Baroque", "movementId": "Q37853",
        "summary": "About the artist: Michelangelo Merisi da Caravaggio was an Italian painter.",
        "summaryLanguage": "en"}


class CardDataTest(unittest.TestCase):
    def test_painting(self):
        data = card.data(CONFIG, {"active": True, "info": INFO, "image": "", "fromCache": True})
        self.assertEqual((data["title"], data["byline"], data["place"]),
                         ("The Fortune Teller", "Caravaggio · 1594", "Capitoline Museums · Baroque"))
        self.assertEqual([m["label"] for m in data["more"]], ["More by Caravaggio", "More Baroque"])
        self.assertTrue(data["canSave"])
        self.assertEqual(data["summaryNote"], "")

    def test_rows_are_the_omarchy_settings_plus_caption_and_language(self):
        rows = card.data(CONFIG, {"active": False})["rows"]
        self.assertEqual([r["key"] for r in rows], ["intervalMinutes", "fame", "fit", "caption", "language"])
        self.assertEqual([c["label"] for c in rows[0]["choices"]], ["15m", "30m", "1h", "3h", "6h", "1d", "Off"])
        self.assertEqual([c["label"] for c in rows[2]["choices"]], ["Blur", "Auto", "Wall", "Fill"])
        self.assertEqual([c["label"] for c in rows[4]["choices"]], ["Auto", "EN", "RU"])
        self.assertEqual(rows[0]["current"], 60)
        self.assertEqual(rows[4]["current"], "en")
        self.assertEqual(card.rows(core.normalize_config({}))[4]["current"], "auto")

    def test_russian_card_says_when_the_story_is_in_english(self):
        russian = core.normalize_config({"language": "ru"})
        data = card.data(russian, {"active": True, "info": {**INFO, "summaryLanguage": "en"}})
        self.assertEqual(data["summaryNote"], "На языке: English")
        self.assertEqual(data["buttons"]["next"], "Дальше")
        self.assertEqual([c["label"] for c in data["rows"][0]["choices"]][:3], ["15м", "30м", "1ч"])
        same = card.data(russian, {"active": True, "info": {**INFO, "summaryLanguage": "ru"}})
        self.assertEqual(same["summaryNote"], "")

    def test_not_ours_and_first_run(self):
        self.assertIn("first one", card.data(CONFIG, {"active": False})["title"])
        self.assertIn("not from", card.data(CONFIG, {"active": False, "setAt": 1})["title"])

    def test_setting_validation(self):
        self.assertEqual(card.setting(["intervalMinutes", 60.0]), ("intervalMinutes", 60))
        self.assertEqual(card.setting(["caption", "top-left"]), ("caption", "top-left"))
        for bad in (["intervalMinutes", 7], ["intervalMinutes", True], ["saveDir", "/"], ["fit"], ["language", "de"]):
            with self.assertRaises(ValueError):
                card.setting(bad)

    def test_preview(self):
        import tempfile
        from pathlib import Path
        with tempfile.TemporaryDirectory() as tmp:
            image = make_jpeg(Path(tmp) / "p.jpg", size=(1200, 700))
            url = card.preview_url(image)
        self.assertTrue(url.startswith("data:image/jpeg;base64,"))
        self.assertEqual(card.preview_url("/nonexistent.jpg"), "")


class CardPageTest(unittest.TestCase):
    def test_data_cannot_close_the_script(self):
        evil = {**INFO, "title": "</script><img src=x onerror=alert(1)> "}
        page = card.page(card.data(CONFIG, {"active": True, "info": evil}))
        script = page.split("<script>", 1)[1]
        self.assertEqual(script.count("</script>"), 1)
        self.assertNotIn(" ", page)
        initial = re.search(r"const initial = (.*);\n", script).group(1)
        self.assertEqual(json.loads(initial)["title"], evil["title"])

    def test_page_sets_text_only_through_text_content(self):
        # innerHTML only for the constant icons.
        self.assertEqual(card.PAGE.count("innerHTML"), 1)
        self.assertIn("svg.innerHTML = ICONS[name]", card.PAGE)


if __name__ == "__main__":
    unittest.main()
