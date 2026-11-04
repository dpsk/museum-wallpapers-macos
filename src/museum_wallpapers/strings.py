"""Interface text in English and Russian. The language follows the
`language` setting (the macOS language when it is "auto"); any other
language gets English."""

STRINGS = {
    "en": {
        "app": "Museum Wallpapers",
        "about_artist": "About the artist: ",
        "story_in": "In {language}",
        "about": "About this painting",
        "next": "Next painting",
        "next_short": "Next",
        "read_more": "Read more",
        "save": "Save to collection",
        "save_short": "Save",
        "saved": "Saved to your collection",
        "already_saved": "Already in your collection",
        "change_every": "Change every",
        "change_every_short": "Change every",
        "minutes": "{n} minutes",
        "hour": "1 hour",
        "hours": "{n} hours",
        "day": "1 day",
        "only_on_demand": "Only when I ask",
        "artists": "Artists",
        "fame_famous": "Famous (~280 painters)",
        "fame_known": "Known (~1200 painters)",
        "fame_any": "Any painter",
        "fame_famous_short": "Famous",
        "fame_known_short": "Known",
        "fame_any_short": "Any",
        "fit": "Paintings that are not widescreen",
        "fit_short": "Fit",
        "fit_blur": "Blurred frame",
        "fit_auto": "Fill, or blurred frame if cropping a lot",
        "fit_wall": "Dark wall",
        "fit_cover": "Fill the screen (crop)",
        "fit_blur_short": "Blur",
        "fit_auto_short": "Auto",
        "fit_wall_short": "Wall",
        "fit_cover_short": "Fill",
        "caption": "Caption on wallpaper",
        "caption_short": "Caption",
        "caption_off": "Off",
        "caption_bottom-right": "Bottom right",
        "caption_bottom-left": "Bottom left",
        "caption_top-right": "Top right",
        "caption_top-left": "Top left",
        "language": "Language",
        "language_short": "Language",
        "lang_auto_short": "Auto",
        "lang_auto": "Same as macOS",
        "notify_on_change": "Notify when it changes",
        "start_at_login": "Open at login",
        "autostart_blocked": "macOS needs your permission to open Museum Wallpapers at login: turn it on in System Settings → General → Login Items.",
        "open_collection": "Open collection folder",
        "settings": "Settings",
        "quit": "Quit Museum Wallpapers",
        "more_by": "More by {name}",
        "more_of": "More {name}",
        "showing_only": "Showing only: {name}",
        "filter": "Filter: {name}",
        "show_all": "Show all paintings again",
        "clear_filter": "Clear filter",
        "finding": "Finding a painting…",
        "loading": "Loading…",
        "no_painting": "No painting yet — the first one appears within a minute.",
        "not_ours": "The current background is not from Museum Wallpapers.",
        "started": "Museum Wallpapers is running. Click the frame icon in the menu bar for the painting and settings.",
        "close": "Close",
    },
    "ru": {
        "app": "Museum Wallpapers",
        "about_artist": "О художнике: ",
        "story_in": "На языке: {language}",
        "about": "Об этой картине",
        "next": "Следующая картина",
        "next_short": "Дальше",
        "read_more": "Подробнее",
        "save": "Сохранить в коллекцию",
        "save_short": "Сохранить",
        "saved": "Сохранено в коллекцию",
        "already_saved": "Уже есть в коллекции",
        "change_every": "Как часто менять",
        "change_every_short": "Менять каждые",
        "minutes": "{n} минут",
        "hour": "1 час",
        "hours": "{n} часов",
        "day": "1 день",
        "only_on_demand": "Только по запросу",
        "artists": "Художники",
        "fame_famous": "Знаменитые (~280)",
        "fame_known": "Известные (~1200)",
        "fame_any": "Любые",
        "fame_famous_short": "Знаменитые",
        "fame_known_short": "Известные",
        "fame_any_short": "Любые",
        "fit": "Картины не 16:9",
        "fit_short": "Вписать",
        "fit_blur": "Размытая рамка",
        "fit_auto": "Заполнить, или рамка при сильной обрезке",
        "fit_wall": "Тёмная стена",
        "fit_cover": "Заполнить экран (обрезать)",
        "fit_blur_short": "Размытие",
        "fit_auto_short": "Авто",
        "fit_wall_short": "Стена",
        "fit_cover_short": "Заполнить",
        "caption": "Подпись на обоях",
        "caption_short": "Подпись",
        "caption_off": "Выключена",
        "caption_bottom-right": "Справа внизу",
        "caption_bottom-left": "Слева внизу",
        "caption_top-right": "Справа вверху",
        "caption_top-left": "Слева вверху",
        "language": "Язык",
        "language_short": "Язык",
        "lang_auto_short": "Авто",
        "lang_auto": "Как в macOS",
        "notify_on_change": "Уведомлять о смене",
        "start_at_login": "Открывать при входе",
        "autostart_blocked": "macOS просит разрешения открывать Museum Wallpapers при входе: включите его в Системных настройках → Основные → Объекты входа.",
        "open_collection": "Открыть папку коллекции",
        "settings": "Настройки",
        "quit": "Завершить Museum Wallpapers",
        "more_by": "Ещё {name}",
        "more_of": "Ещё: {name}",
        "showing_only": "Только: {name}",
        "filter": "Фильтр: {name}",
        "show_all": "Снова показывать все картины",
        "clear_filter": "Сбросить фильтр",
        "finding": "Ищу картину…",
        "loading": "Загрузка…",
        "no_painting": "Картины пока нет — первая появится в течение минуты.",
        "not_ours": "Сейчас на рабочем столе не картина из Museum Wallpapers.",
        "started": "Museum Wallpapers запущен. Картина и настройки — по клику на значок-рамку в строке меню.",
        "close": "Закрыть",
    },
}

# Names of the languages offered in the menu, in their own language.
LANGUAGE_NAMES = {
    "en": "English", "ru": "Русский", "uk": "Українська", "de": "Deutsch", "fr": "Français",
    "es": "Español", "it": "Italiano", "nl": "Nederlands", "pl": "Polski", "pt": "Português",
}

# The card's "Change every" row, as in the Omarchy popup.
CARD_INTERVALS = (15, 30, 60, 180, 360, 1440, 0)
SHORT_UNITS = {"en": ("m", "h", "d", "Off"), "ru": ("м", "ч", "д", "Выкл")}
# Corners as arrows pointing where the caption goes.
CORNER_ARROWS = {"bottom-right": "↘", "bottom-left": "↙", "top-right": "↗", "top-left": "↖"}


def ui_language(config_or_language):
    language = config_or_language.get("language", "en") if isinstance(config_or_language, dict) \
        else str(config_or_language or "en")
    return language if language in STRINGS else "en"


def t(key, config_or_language="en", **values):
    table = STRINGS[ui_language(config_or_language)]
    text = table.get(key) or STRINGS["en"].get(key) or key
    return text.format(**values) if values else text


def interval_label(minutes, config_or_language="en"):
    if minutes == 0:
        return t("only_on_demand", config_or_language)
    if minutes < 60:
        return t("minutes", config_or_language, n=minutes)
    if minutes == 60:
        return t("hour", config_or_language)
    if minutes == 1440:
        return t("day", config_or_language)
    hours = minutes // 60
    text = t("hours", config_or_language, n=hours)
    if ui_language(config_or_language) == "ru" and hours in (2, 3, 4):
        text = f"{hours} часа"
    return text


def short_interval(minutes, config_or_language="en"):
    """15m, 1h, 1d, Off (15м, 1ч, 1д, Выкл) for the card."""
    minute, hour, day, off = SHORT_UNITS[ui_language(config_or_language)]
    if minutes == 0:
        return off
    if minutes % 1440 == 0:
        return f"{minutes // 1440}{day}"
    if minutes % 60 == 0:
        return f"{minutes // 60}{hour}"
    return f"{minutes}{minute}"
