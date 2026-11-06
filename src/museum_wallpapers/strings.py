"""Interface text in the ten languages of the Language menu. The language
follows the `language` setting (the macOS language when it is "auto").

English is here, in the code; the other nine are in data/strings.json, each
with exactly the keys and placeholders of English (a test checks this). A
language without a table, a missing or broken strings file, or a key a table
lacks all fall back to English: the interface is never left without text.
Wikipedia titles and stories still come in the chosen language."""

import json
import string
import sys
import threading
from pathlib import Path

ENGLISH = {
    "app": "Museum Wallpapers",
    "about_artist": "About the artist: ",
    "story_in": "Language: {language}",
    "about": "About this painting",
    "next": "Next painting",
    "next_short": "Next",
    "read_more": "Read more",
    "save": "Save to collection",
    "save_short": "Save",
    "saved": "Saved to your collection",
    "already_saved": "Already in your collection",
    "change_every": "Change every",
    "interval_15": "15 minutes",
    "interval_30": "30 minutes",
    "interval_60": "1 hour",
    "interval_180": "3 hours",
    "interval_360": "6 hours",
    "interval_720": "12 hours",
    "interval_1440": "1 day",
    "interval_0": "Only when I ask",
    "artists": "Artists",
    "fame_famous": "Famous (~280 painters)",
    "fame_known": "Known (~1200 painters)",
    "fame_any": "Any painter",
    "fit": "Paintings that are not widescreen",
    "fit_blur": "Blurred frame",
    "fit_auto": "Fill, or blurred frame if cropping a lot",
    "fit_wall": "Dark wall",
    "fit_cover": "Fill the screen (crop)",
    "caption": "Caption on wallpaper",
    "caption_off": "Off",
    "caption_bottom-right": "Bottom right",
    "caption_bottom-left": "Bottom left",
    "caption_top-right": "Top right",
    "caption_top-left": "Top left",
    "language": "Language",
    "lang_auto": "Same as macOS",
    "localized": "In my language",
    "loc_prefer": "Described ones first",
    "loc_only": "Only described ones",
    "loc_all": "No preference",
    "localized_by": "Described means",
    "by_title": "Has a title in my language",
    "by_article": "Has a Wikipedia article in my language",
    "notify_on_change": "Notify when it changes",
    "start_at_login": "Open at login",
    "autostart_blocked": "macOS needs your permission to open Museum Wallpapers at login: turn it on in System "
                         "Settings → General → Login Items.",
    "open_collection": "Open collection folder",
    "check_updates": "Check for Updates…",
    "check_updates_auto": "Check for updates automatically",
    "update_available": "Version {version} is available",
    "install_update": "Install and restart",
    "install_update_menu": "Install version {version} and restart",
    "updating": "Updating…",
    "up_to_date": "You have the latest version ({version}).",
    "update_check_failed": "Could not check for updates: {error}",
    "update_failed": "Could not update ({error}). The download page is open in your browser.",
    "update_manual": "Version {version} is available, but this copy cannot update itself ({reason}). The download "
                     "page is open in your browser.",
    "settings": "Settings",
    "quit": "Quit Museum Wallpapers",
    "more_by": "More by {name}",
    "more_of": "More {name}",
    "showing_only": "Showing only: {name}",
    "filter": "Filter: {name}",
    "show_all": "Show all paintings again",
    "clear_filter": "Clear filter",
    "loading": "Loading…",
    "no_painting": "No painting yet — the first one appears within a minute.",
    "not_ours": "The current background is not from Museum Wallpapers.",
    "started": "Museum Wallpapers is running. Click the frame icon in the menu bar for the painting and settings.",
    "close": "Close",
    "err_network": "Could not reach Wikimedia: {detail}",
    "err_filter": "Filter: {detail}; showing a random painting",
    "err_filter_nothing": "Filter: {detail}; and no other painting either: {inner}",
    "err_filter_network": "Filter: {detail}; and could not reach Wikimedia: {inner}",
    "err_background": "Could not set the background: {detail}",
    "nm_no_match": "no paintings match the filter",
    "nm_pool_small": "none of the {n} matching paintings is large enough for this screen",
    "nm_unknown": "unknown filter value: {names}",
    "nm_all_queued": "every matching painting is already queued",
    "nm_only_current": "the only matching painting is already showing",
    "nm_too_small": "no matching painting is large enough for this screen",
    "nm_years": "no painting from these years turned up among random scans",
    "nm_none": "no suitable painting found",
    "nm_localized": "no painting described in this language",
}

STRINGS_FILE = Path(__file__).resolve().parent / "data" / "strings.json"

# Names of the languages offered in the menu, in their own language.
LANGUAGE_NAMES = {
    "en": "English", "ru": "Русский", "uk": "Українська", "de": "Deutsch", "fr": "Français",
    "es": "Español", "it": "Italiano", "nl": "Nederlands", "pl": "Polski", "pt": "Português",
}

_tables = None
_tables_lock = threading.Lock()


def load_strings(path=None):
    """{language: table}, English always included. A missing or broken
    file (or table) leaves only what could be read."""
    tables = {"en": ENGLISH}
    try:
        data = json.loads(Path(path or STRINGS_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"museum-wallpapers: interface strings unavailable, using English: {exc}", file=sys.stderr)
        return tables
    for language, table in (data.items() if isinstance(data, dict) else ()):
        if language != "en" and isinstance(table, dict):
            tables[language] = {k: v for k, v in table.items() if isinstance(v, str)}
    return tables


def tables():
    global _tables
    with _tables_lock:
        if _tables is None:
            _tables = load_strings()
        return _tables


def placeholders(text):
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


def ui_language(config_or_language):
    language = config_or_language.get("language", "en") if isinstance(config_or_language, dict) \
        else str(config_or_language or "en")
    return language if language in tables() else "en"


def t(key, config_or_language="en", **values):
    table = tables()[ui_language(config_or_language)]
    text = table.get(key) or ENGLISH.get(key) or key
    try:
        return text.format(**values) if values else text
    except (KeyError, IndexError, ValueError):
        # A translation with a broken placeholder: say it in English.
        text = ENGLISH.get(key) or key
        return text.format(**values) if values else text


def interval_label(minutes, config_or_language="en"):
    """The menu's name for an interval; a hand-set one has no name: "45 min"."""
    key = f"interval_{minutes}"
    return t(key, config_or_language) if key in ENGLISH else f"{minutes} min"
