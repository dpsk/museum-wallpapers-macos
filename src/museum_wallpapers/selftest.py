"""`museum-wallpapers selftest [--out FILE]`: checks that this build has
everything it needs (the libraries PyInstaller has to bundle, the macOS
APIs, the folders) without changing the wallpaper, and writes a JSON report.
CI runs it against the built app; it also helps on a Mac where the app
misbehaves. Exit code 0 when everything needed works."""

import importlib
import json
import platform
import sys
import traceback
from pathlib import Path

from . import VERSION

REQUIRED = ["PIL.Image", "PIL.ImageFilter", "fontTools.ttLib", "fontTools.ttLib.tables._c_m_a_p", "truststore"]
MAC_REQUIRED = ["objc", "Foundation", "AppKit", "WebKit", "UserNotifications", "ServiceManagement",
                "PyObjCTools.AppHelper", "museum_wallpapers.macui"]


def run(out=None):
    report = {"version": VERSION, "python": sys.version, "frozen": bool(getattr(sys, "frozen", False)),
              "os": platform.platform(), "modules": {}, "checks": {}, "ok": True}

    def check(name, work, required=True):
        try:
            report["checks"][name] = {"ok": True, "value": work()}
        except Exception as exc:  # noqa: BLE001 - reported, not raised
            report["checks"][name] = {"ok": False, "error": repr(exc), "trace": traceback.format_exc(limit=3)}
            if required:
                report["ok"] = False

    modules = REQUIRED + (MAC_REQUIRED if sys.platform == "darwin" else [])
    for name in modules:
        try:
            importlib.import_module(name)
            report["modules"][name] = "ok"
        except Exception as exc:  # noqa: BLE001
            report["modules"][name] = repr(exc)
            report["ok"] = False

    from . import card, core, framing, resources, updater
    check("platform", lambda: core.PLATFORM.name)
    check("setup", lambda: core.PLATFORM.setup() or "done")
    check("paths", lambda: {k: str(v) for k, v in core.PLATFORM.paths().items()})
    check("monitors", lambda: [m._asdict() for m in core.PLATFORM.monitors()])
    check("current_wallpaper", lambda: str(core.PLATFORM.current_wallpaper()), required=False)
    check("ui_language", lambda: core.PLATFORM.ui_language())
    check("fonts", lambda: [str(f) for f in core.PLATFORM.caption_fonts()])
    check("packaged", lambda: {"packaged": core.PLATFORM.packaged, "executable": sys.executable})
    check("log_file", lambda: str(core.PLATFORM.log_file(core.STATE)))
    check("autostart", lambda: core.PLATFORM.autostart_enabled())
    check("settings", lambda: {k: v for k, v in core.load_config().items() if k != "filters"})

    def frame():
        import tempfile
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp) / "painting.jpg"
            Image.new("RGB", (800, 500), (120, 90, 60)).save(src)
            out_path = framing.frame(src, Path(tmp) / "framed.jpg", "blur", (1920, 1080),
                                     {"title": "Test", "byline": "Painter · 1850", "museum": "Museum"},
                                     "bottom-right", (0, 48, 0, 0), core.PLATFORM.caption_fonts())
            return framing.image_size(out_path)

    check("framing", frame)
    check("icon", lambda: resources.icon_image(64).size)
    check("menu_bar_icon", lambda: resources.menu_bar_icon().size)
    check("updater", lambda: {"arch": updater.arch_name(), "bundle": str(updater.bundle_path()),
                              "cannot_install": updater.cannot_install(updater.bundle_path())}, required=False)
    check("seed", lambda: {level: len((core.seed(level) or {})["items"]) for level in core.FAME.values() if level})
    # A real request: a bundle whose Python cannot verify certificates
    # fails here rather than on a user's Mac.
    check("https", lambda: sorted(core.mw_api(core.COMMONS_API, action="query", meta="siteinfo")["query"])[:1])
    check("card", lambda: len(card.page(card.data(core.load_config(), {"active": False}))))

    text = json.dumps(report, ensure_ascii=False, indent=2)
    if out:
        Path(out).write_text(text, encoding="utf-8")
    elif sys.stdout is not None:
        print(text)
    return 0 if report["ok"] else 1
