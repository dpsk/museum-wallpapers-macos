"""The card about the painting, shown in a popover under the menu bar icon,
laid out like the Omarchy plugin's popup: preview, title, artist, museum,
story, Next / Read more / Save, More by … / More …, and the interval,
artists, fit and caption settings as rows of choices.

It is a small HTML page in a WKWebView (macui.py). Python sends it data
(`data()`, as JSON) and the page posts button presses back as
{"action": name, "args": [...]}. Text from Wikimedia is only ever set with
textContent, never parsed as HTML."""

import base64
import functools
import io
import json
from pathlib import Path

from . import core, strings

WIDTH = 380  # points
PREVIEW_SIZE = (760, 428)  # pixels: 16:9 at 2x
SUMMARY_LIMIT = 900

# What the card's rows may set, and to which values.
CARD_SETTINGS = {
    "intervalMinutes": set(core.INTERVALS),
    "fame": {"famous", "known", "any"},
    "fit": {"blur", "auto", "wall", "cover"},
    "caption": set(core.CAPTIONS),
    # The other languages are in the menu; the card offers the app's own two.
    "language": {"auto", "en", "ru"},
}


def setting(args):
    """(key, value) from a row button's arguments; ValueError for anything
    the card does not offer."""
    if len(args) != 2:
        raise ValueError(f"bad setting: {args!r}")
    key, value = str(args[0]), args[1]
    if key == "intervalMinutes" and isinstance(value, float) and value.is_integer():
        value = int(value)
    if key not in CARD_SETTINGS or isinstance(value, bool) or value not in CARD_SETTINGS[key]:
        raise ValueError(f"bad setting: {args!r}")
    return key, value


def filter_label(override):
    names = [x.get("label") or x.get("id") for key in ("artists", "movements", "genres")
             for x in override.get(key, []) if isinstance(x, dict)]
    years = ""
    if override.get("yearFrom") is not None or override.get("yearTo") is not None:
        years = f"{override.get('yearFrom') or ''}–{override.get('yearTo') or ''}"
    return ", ".join(x for x in names + [years] if x)


def shorten(text, limit):
    text = " ".join((text or "").split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


@functools.lru_cache(maxsize=4)
def _preview(path, _mtime):
    from PIL import Image, ImageOps
    with Image.open(path) as image:
        image.draft("RGB", PREVIEW_SIZE)
        thumb = ImageOps.fit(image.convert("RGB"), PREVIEW_SIZE, Image.Resampling.LANCZOS)
    out = io.BytesIO()
    thumb.save(out, "JPEG", quality=84)
    return "data:image/jpeg;base64," + base64.b64encode(out.getvalue()).decode("ascii")


def preview_url(path):
    """The painting as a small 16:9 JPEG data URL, or '' when it cannot be read."""
    try:
        path = Path(path)
        return _preview(str(path), path.stat().st_mtime)
    except Exception:  # noqa: BLE001 - the card works without a preview
        return ""


def rows(config):
    t = lambda key, **values: strings.t(key, config, **values)  # noqa: E731
    return [
        {"key": "intervalMinutes", "title": t("change_every_short"), "current": config["intervalMinutes"],
         "choices": [{"value": m, "label": strings.short_interval(m, config),
                      "hint": strings.interval_label(m, config)} for m in strings.CARD_INTERVALS]},
        {"key": "fame", "title": t("artists"), "current": config["fame"],
         "choices": [{"value": f, "label": t(f"fame_{f}_short"), "hint": t(f"fame_{f}")}
                     for f in ("famous", "known", "any")]},
        {"key": "fit", "title": t("fit_short"), "current": config["fit"],
         "choices": [{"value": f, "label": t(f"fit_{f}_short"), "hint": t(f"fit_{f}")}
                     for f in ("blur", "auto", "wall", "cover")]},
        {"key": "caption", "title": t("caption_short"), "current": config["caption"],
         "choices": [{"value": "off", "label": t("caption_off"), "hint": t("caption_off")}]
         + [{"value": c, "label": arrow, "hint": t(f"caption_{c}")} for c, arrow in strings.CORNER_ARROWS.items()]},
        {"key": "language", "title": t("language_short"), "current": config["languageSetting"],
         "choices": [{"value": "auto", "label": t("lang_auto_short"), "hint": t("lang_auto")},
                     {"value": "en", "label": "EN", "hint": strings.LANGUAGE_NAMES["en"]},
                     {"value": "ru", "label": "RU", "hint": strings.LANGUAGE_NAMES["ru"]}]},
    ]


def data(config, status, busy=False, update=None, updating=False):
    """Everything the card shows, from core.load_config() and core.status();
    `update` is a newer release (updater.check()), `updating` while it installs."""
    t = lambda key, **values: strings.t(key, config, **values)  # noqa: E731
    info = status.get("info") if status.get("active") else None
    result = {
        "lang": strings.ui_language(config),
        "active": bool(status.get("active")),
        "busy": bool(busy),
        "hasInfo": bool(info),
        "canSave": bool(info) and status.get("fromCache") is True,
        "preview": "",
        "title": "",
        "byline": "",
        "place": "",
        "summary": "",
        "summaryNote": "",
        "error": status.get("error") or "",
        "more": [],
        "rows": rows(config),
        "filter": "",
        "buttons": {"next": t("next_short"), "loading": t("loading"), "open": t("read_more"),
                    "save": t("save_short"), "settings": t("settings"), "clear": t("clear_filter")},
    }
    if info:
        result.update({
            "preview": preview_url(status["image"]) if status.get("image") else "",
            "title": info.get("title") or "",
            "byline": core.byline(info),
            "place": " · ".join(x for x in (info.get("museum"), info.get("movement")) if x),
            "summary": shorten(info.get("summary"), SUMMARY_LIMIT),
        })
        story = info.get("summaryLanguage")
        if result["summary"] and story and story != config["language"]:
            # Wikipedia has nothing about this painting or painter in the
            # reader's language: say which language the story is in.
            result["summaryNote"] = t("story_in", language=strings.LANGUAGE_NAMES.get(story, story))
        if info.get("artistId") and info.get("artist"):
            result["more"].append({"label": t("more_by", name=info["artist"]), "action": "more_by",
                                   "args": [info["artistId"], info["artist"]]})
        if info.get("movementId") and info.get("movement"):
            result["more"].append({"label": t("more_of", name=info["movement"]), "action": "more_of",
                                   "args": [info["movementId"], info["movement"]]})
    else:
        result["title"] = t("not_ours") if status.get("setAt") else t("no_painting")
    override = status.get("filter")
    if override:
        result["filter"] = t("filter", name=filter_label(override))
    result["update"] = None
    if update:
        result["update"] = {"text": t("update_available", version=update["version"]),
                            "button": t("updating") if updating else t("install_update"), "busy": bool(updating)}
    return result


def script_json(value):
    """JSON safe to put inside a <script> element."""
    return json.dumps(value, ensure_ascii=False).replace("</", "<\\/").replace(" ", "\\u2028") \
        .replace(" ", "\\u2029")


def page(initial):
    """The whole card page, rendering `initial` (from data()) right away."""
    return PAGE.replace("/*INITIAL*/null", script_json(initial))


PAGE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="color-scheme" content="light dark">
<style>
:root {
  --bg: #f4f0e8; --fg: #2b2722; --fg2: #4d463d; --dim: #877e70;
  --line: rgba(43, 39, 34, .14); --hover: rgba(43, 39, 34, .07); --on: rgba(43, 39, 34, .13);
  --frame: rgba(43, 39, 34, .28); --accent: #a8741f;
}
@media (prefers-color-scheme: dark) {
  :root {
    --bg: #262522; --fg: #ddd3c2; --fg2: #c2b8a7; --dim: #8e8576;
    --line: rgba(221, 211, 194, .14); --hover: rgba(221, 211, 194, .08); --on: rgba(221, 211, 194, .15);
    --frame: rgba(221, 211, 194, .3); --accent: #d9a75a;
  }
}
* { box-sizing: border-box; margin: 0; }
html, body { background: var(--bg); color: var(--fg); overflow: hidden; cursor: default;
  font: 12px/1.4 ui-monospace, "SF Mono", Menlo, monospace; -webkit-user-select: none; }
#card { padding: 14px 14px 8px; display: flex; flex-direction: column; gap: 7px; }
.preview { width: 100%; aspect-ratio: 16 / 9; border: 1px solid var(--frame); border-radius: 7px; padding: 2px; }
.preview img { width: 100%; height: 100%; object-fit: cover; border-radius: 5px; display: block; }
h1 { font-size: 15px; font-weight: 700; line-height: 1.3; margin-top: 3px;
  display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 3; overflow: hidden; }
.byline { font-size: 13px; color: var(--fg2); }
.place { color: var(--dim); }
.byline, .place, .filter span { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.summary { line-height: 1.5; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 9;
  overflow: hidden; -webkit-user-select: text; cursor: auto; }
.error { color: var(--accent); font-size: 11px; }
.note { color: var(--dim); font-size: 10px; text-transform: uppercase; letter-spacing: .06em; margin-bottom: -4px; }
hr { border: 0; border-top: 1px solid var(--line); margin: 3px 0 1px; }
.buttons { display: flex; flex-wrap: wrap; gap: 2px; margin-left: -7px; }
button { font: inherit; color: inherit; background: none; border: 0; border-radius: 5px; padding: 6px 8px;
  display: inline-flex; align-items: center; gap: 7px; white-space: nowrap; }
button:hover:not(:disabled) { background: var(--hover); }
button:active:not(:disabled) { background: var(--on); }
button:disabled { opacity: .5; }
button.big { font-size: 13px; }
button svg { width: 14px; height: 14px; fill: none; stroke: currentColor; stroke-width: 2;
  stroke-linecap: round; stroke-linejoin: round; }
.rows { display: grid; grid-template-columns: max-content 1fr; column-gap: 8px; row-gap: 3px;
  align-items: center; margin-top: 2px; }
.rows .label { color: var(--dim); font-size: 11px; }
.choices { display: flex; flex-wrap: wrap; gap: 1px; }
.choices button { font-size: 11px; padding: 5px 6px; }
.choices button.on { background: var(--on); font-weight: 700; }
.filter { display: flex; align-items: center; gap: 6px; color: var(--dim); font-size: 11px; }
.filter span { flex: 1; }
.update { display: flex; align-items: center; gap: 6px; color: var(--accent); font-size: 11px;
  border-top: 1px solid var(--line); padding-top: 6px; margin-top: 2px; }
.update span { flex: 1; }
.update button { color: var(--accent); font-weight: 700; font-size: 11px; padding: 4px 6px; margin-right: -6px; }
.footer { display: flex; justify-content: flex-end; border-top: 1px solid var(--line); padding-top: 4px; margin-top: 2px; }
.footer button { color: var(--dim); font-size: 11px; padding: 4px 6px; margin-right: -6px; }
</style>
</head>
<body>
<div id="card"></div>
<script>
"use strict";
const ICONS = {
  next: '<path d="M6 5l9 7-9 7z"/><path d="M18 5v14"/>',
  open: '<path d="M14 4h6v6"/><path d="M20 4l-9 9"/><path d="M18 14v5a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h5"/>',
  save: '<path d="M12 20s-7.5-4.6-7.5-10.2A4.2 4.2 0 0 1 12 7.2a4.2 4.2 0 0 1 7.5 2.6C19.5 15.4 12 20 12 20z"/>',
  close: '<path d="M7 7l10 10M17 7L7 17"/>',
};
function post(action, ...args) {
  if (window.webkit && webkit.messageHandlers && webkit.messageHandlers.museum)
    webkit.messageHandlers.museum.postMessage({action: action, args: args});
}
function el(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text !== undefined) node.textContent = text;
  return node;
}
function icon(name) {
  const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  svg.setAttribute("viewBox", "0 0 24 24");
  svg.innerHTML = ICONS[name];  // constant markup above, never data
  return svg;
}
function button(label, iconName, onClick, cls) {
  const node = el("button", cls);
  if (iconName) node.append(icon(iconName));
  if (label) node.append(el("span", null, label));
  node.addEventListener("click", onClick);
  return node;
}
function reportSize() {
  // Measured right away (this lays the page out): animation frames do not
  // run while the popover is still hidden, and it waits for this height.
  post("size", Math.ceil(document.getElementById("card").getBoundingClientRect().height));
}
function render(d) {
  document.documentElement.lang = d.lang;
  const card = document.getElementById("card");
  card.replaceChildren();
  if (d.preview) {
    const frame = el("div", "preview"), img = el("img");
    img.src = d.preview;
    img.alt = "";
    frame.append(img);
    card.append(frame);
  }
  if (d.title) card.append(el("h1", null, d.title));
  if (d.byline) card.append(el("div", "byline", d.byline));
  if (d.place) card.append(el("div", "place", d.place));
  if (d.summary && d.summaryNote) card.append(el("div", "note", d.summaryNote));
  if (d.summary) card.append(el("div", "summary", d.summary));
  if (d.error) card.append(el("div", "error", d.error));
  card.append(el("hr"));

  const main = el("div", "buttons");
  const next = button(d.busy ? d.buttons.loading : d.buttons.next, "next", () => post("next"), "big");
  next.disabled = d.busy;
  main.append(next);
  if (d.hasInfo) main.append(button(d.buttons.open, "open", () => post("open"), "big"));
  if (d.canSave) main.append(button(d.buttons.save, "save", () => post("save"), "big"));
  card.append(main);

  if (d.more.length) {
    const more = el("div", "buttons");
    for (const item of d.more) {
      const node = button(item.label, null, () => post(item.action, ...item.args));
      node.disabled = d.busy;
      more.append(node);
    }
    card.append(more);
  }

  const rows = el("div", "rows");
  for (const row of d.rows) {
    rows.append(el("div", "label", row.title));
    const choices = el("div", "choices");
    for (const choice of row.choices) {
      const node = button(choice.label, null, () => {
        for (const other of choices.children) other.classList.toggle("on", other === node);
        post("set", row.key, choice.value);
      }, choice.value === row.current ? "on" : "");
      if (choice.hint) node.title = choice.hint;
      choices.append(node);
    }
    rows.append(choices);
  }
  card.append(rows);

  if (d.filter) {
    const filter = el("div", "filter");
    filter.append(el("span", null, d.filter));
    const clear = button(null, "close", () => post("show_all"));
    clear.title = d.buttons.clear;
    clear.disabled = d.busy;
    filter.append(clear);
    card.append(filter);
  }

  if (d.update) {
    const update = el("div", "update");
    update.append(el("span", null, d.update.text));
    const install = button(d.update.button, null, () => post("update"));
    install.disabled = d.update.busy;
    update.append(install);
    card.append(update);
  }

  const footer = el("div", "footer");
  footer.append(button(d.buttons.settings + " …", null, () => post("settings")));
  card.append(footer);
  reportSize();
}
window.render = render;
const initial = /*INITIAL*/null;
if (initial) render(initial);
</script>
</body>
</html>
"""
