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

    def test_settings_are_not_in_the_card(self):
        data = card.data(CONFIG, {"active": False})
        self.assertNotIn("rows", data)
        self.assertEqual(data["buttons"]["settings"], "Settings")
        self.assertIn('post("settings")', card.PAGE)
        self.assertNotIn('post("set"', card.PAGE)

    def test_a_longer_story(self):
        story = " ".join(f"Sentence number {i} is here." for i in range(40))
        data = card.data(CONFIG, {"active": True, "info": {**INFO, "summary": story}})
        self.assertLessEqual(len(data["summary"]), card.SUMMARY_LIMIT + 1)
        self.assertGreater(len(data["summary"]), 1000)
        self.assertIn("-webkit-line-clamp: 14", card.PAGE)

    def test_every_language(self):
        status = {"active": True, "info": INFO, "image": "", "fromCache": True, "filter": {"artists": [
            {"id": "Q42207", "label": "Caravaggio"}]}}
        for language in core.LANGUAGES[1:]:
            data = card.data(core.normalize_config({"language": language}), status,
                             update={"version": "9.9.9"})
            texts = [data["title"], data["filter"], data["update"]["text"], data["update"]["button"],
                     *data["buttons"].values(), *(m["label"] for m in data["more"])]
            for text in texts:
                self.assertNotRegex(text, r"^[a-z_]+$|\{", f"{language}: {text}")

    def test_russian_card_says_when_the_story_is_in_english(self):
        russian = core.normalize_config({"language": "ru"})
        data = card.data(russian, {"active": True, "info": {**INFO, "summaryLanguage": "en"}})
        self.assertEqual(data["summaryNote"], "На языке: English")
        self.assertEqual(data["buttons"]["next"], "Дальше")
        same = card.data(russian, {"active": True, "info": {**INFO, "summaryLanguage": "ru"}})
        self.assertEqual(same["summaryNote"], "")

    def test_not_ours_and_first_run(self):
        self.assertIn("first one", card.data(CONFIG, {"active": False})["title"])
        self.assertIn("not from", card.data(CONFIG, {"active": False, "setAt": 1})["title"])

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
