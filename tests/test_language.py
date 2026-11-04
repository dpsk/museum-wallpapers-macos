"""The reader's language: it changes how paintings are described, never
which ones are picked."""

import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from helpers import FakePlatform, make_jpeg
from helpers import core as museum

PAGE = {"title": "File:X.jpg", "imageinfo": [{"descriptionurl": "https://commons/X", "extmetadata": {}}]}


def claim(prop, value):
    return {prop: [{"mainsnak": {"datavalue": {"value": value}}}]}


def describe(language, painting_links, artist_links, commons=""):
    """describe() with a painting and an artist that have Wikipedia articles
    in the given languages; every article's summary names its language."""
    painting = {"labels": {"en": {"value": "The Hay Wain"}, "ru": {"value": "Телега для сена"}},
                "sitelinks": {f"{lang}wiki": {"title": f"painting-{lang}"} for lang in painting_links},
                "claims": claim("P170", {"id": "Q159758"})}
    artist = {"labels": {"en": {"value": "John Constable"}},
              "sitelinks": {f"{lang}wiki": {"title": f"artist-{lang}"} for lang in artist_links}}
    page = {**PAGE, "imageinfo": [{**PAGE["imageinfo"][0],
                                   "extmetadata": {"ImageDescription": {"value": commons}} if commons else {}}]}

    def entities(ids, **_kwargs):
        return {i: {"Q1": painting, "Q159758": artist}[i] for i in ids if i in ("Q1", "Q159758")}

    def summary(language, title):
        return f"{title} text.", f"https://{language}.wikipedia.org/wiki/{title}"

    with mock.patch.object(museum, "entities", side_effect=entities), \
            mock.patch.object(museum, "wikipedia_summary", side_effect=summary):
        return museum.describe(page, "Q1", language)


class DescribeTest(unittest.TestCase):
    def test_painting_article_in_the_readers_language_comes_first(self):
        info = describe("ru", ["ru", "en"], ["ru", "en"])
        self.assertEqual((info["title"], info["summary"], info["summaryLanguage"]),
                         ("Телега для сена", "painting-ru text.", "ru"))

    def test_then_the_artist_in_the_readers_language(self):
        info = describe("ru", ["en"], ["ru", "en"])
        self.assertEqual(info["summary"], "О художнике: artist-ru text.")
        self.assertEqual((info["summaryLanguage"], info["url"]), ("ru", "https://ru.wikipedia.org/wiki/artist-ru"))

    def test_then_english_rather_than_nothing(self):
        info = describe("ru", ["en"], ["en"])
        self.assertEqual((info["summary"], info["summaryLanguage"]), ("painting-en text.", "en"))
        # Labels fall back too: an artist without a Russian label keeps the English one.
        self.assertEqual(info["artist"], "John Constable")

    def test_english_reader_order_is_unchanged(self):
        self.assertEqual(describe("en", ["en"], ["en"])["summary"], "painting-en text.")
        cart = "A hay wain crosses the river Stour beside Willy Lott's cottage."
        info = describe("en", [], ["en"], commons=cart)
        self.assertEqual((info["summary"], info["summaryLanguage"]), (cart, None))
        info = describe("en", [], ["en"])
        self.assertEqual(info["summary"], "About the artist: artist-en text.")

    def test_artist_known_only_in_english_still_gets_a_story_in_russian_mode(self):
        info = describe("ru", [], ["en"])
        self.assertEqual((info["summary"], info["summaryLanguage"]), ("About the artist: artist-en text.", "en"))

    def test_picking_does_not_depend_on_the_language(self):
        """The pools are SPARQL queries and Commons searches; the language
        is not in them, so a painter with no Russian article is still found."""
        query = museum.sparql_query(museum.normalize_filters({"movements": ["Q40415"]}))
        self.assertNotIn("wiki", query)
        self.assertNotIn("inLanguage", query)
        answer = {"results": {"bindings": [{"famed": {"value": "http://www.wikidata.org/entity/Q5582"}}]}}
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(museum, "CACHE", Path(tmp)), \
                mock.patch.object(museum, "http_json", return_value=answer) as http:
            self.assertEqual(museum.famous_painters(60), ["Q5582"])
        query = str(http.call_args)
        self.assertNotIn("ruwiki", query)
        self.assertNotIn('"ru"', query)


class LanguageChangeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(os.path.realpath(self.tmp.name))
        self.cache, self.state = root / "cache", root / "state"
        self.platform = FakePlatform()
        for patch in (mock.patch.object(museum, "CACHE", self.cache),
                      mock.patch.object(museum, "QUEUE", self.cache / "queue"),
                      mock.patch.object(museum, "DISPLAY", self.cache / "display"),
                      mock.patch.object(museum, "STATE", self.state),
                      mock.patch.object(museum, "PLATFORM", self.platform)):
            patch.start()
        self.saved = str(root / "saved")

    def tearDown(self):
        mock.patch.stopall()
        self.tmp.cleanup()

    def test_painting_on_screen_is_described_and_captioned_again(self):
        painting = make_jpeg(self.cache / "commons-77.jpg")
        museum.write_json(painting.with_suffix(".json"), {"id": "Q1", "title": "The Hay Wain", "artist": "Constable",
                                                          "language": "en", "filter": "k"})
        english = museum.normalize_config({"language": "en", "fit": "blur", "saveDir": self.saved})
        museum.record(museum.show(painting, english), original=painting, config=english)
        self.assertIn(".bottom-right-en.", self.platform.walls[-1]["m1"].name)

        russian = museum.normalize_config({"language": "ru", "fit": "blur", "saveDir": self.saved})
        fresh = {"id": "Q1", "title": "Телега для сена", "artist": "Констебл", "language": "ru"}
        with mock.patch.object(museum, "mw_api", return_value={"query": {"pages": [PAGE]}}) as api, \
                mock.patch.object(museum, "describe", return_value=fresh) as describe_again:
            museum.refit(russian)
        self.assertEqual(api.call_args.kwargs["pageids"], "77")
        describe_again.assert_called_once_with(PAGE, "Q1", "ru")
        self.assertIn(".bottom-right-ru.", self.platform.walls[-1]["m1"].name)
        sidecar = museum.read_json(painting.with_suffix(".json"))
        self.assertEqual((sidecar["title"], sidecar["filter"]), ("Телега для сена", "k"))
        self.assertEqual(museum.status(russian)["info"]["title"], "Телега для сена")

    def test_offline_keeps_the_old_description(self):
        painting = make_jpeg(self.cache / "commons-77.jpg")
        museum.write_json(painting.with_suffix(".json"), {"id": "Q1", "title": "The Hay Wain", "language": "en"})
        russian = museum.normalize_config({"language": "ru"})
        with mock.patch.object(museum, "mw_api", side_effect=OSError("offline")):
            museum.redescribe(painting, russian)
        self.assertEqual(museum.read_json(painting.with_suffix(".json"))["title"], "The Hay Wain")


if __name__ == "__main__":
    unittest.main()
