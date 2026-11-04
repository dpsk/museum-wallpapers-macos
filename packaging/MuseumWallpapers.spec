# PyInstaller spec: "Museum Wallpapers.app", a menu bar app (LSUIElement:
# no Dock icon). Run through packaging/build.py, which writes icon.icns first.
# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

HERE = Path(SPECPATH)
ROOT = HERE.parent
BUILD = HERE / "build"
sys.path.insert(0, str(ROOT / "src"))
from museum_wallpapers import APP_NAME, BUNDLE_ID, VERSION  # noqa: E402

hiddenimports = (
    ["museum_wallpapers.app", "museum_wallpapers.macui", "museum_wallpapers.selftest",
     "museum_wallpapers.platforms.macos", "PyObjCTools.AppHelper",
     "WebKit", "UserNotifications", "ServiceManagement"]
    # fontTools loads its table modules by name (cmap for the caption fonts).
    + collect_submodules("fontTools.ttLib.tables")
)

a = Analysis(
    [str(HERE / "launcher.py")],
    pathex=[str(ROOT / "src")],
    hiddenimports=hiddenimports,
    # The bundled painter lists (packaging/seed.py).
    datas=[(str(ROOT / "src" / "museum_wallpapers" / "data"), "museum_wallpapers/data")],
    excludes=["pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="MuseumWallpapers",
    console=False,
    upx=False,
    argv_emulation=False,
)
coll = COLLECT(exe, a.binaries, a.datas, name="MuseumWallpapers", upx=False)
app = BUNDLE(
    coll,
    name=f"{APP_NAME}.app",
    icon=str(BUILD / "icon.icns"),
    bundle_identifier=BUNDLE_ID,
    version=VERSION,
    info_plist={
        "CFBundleName": APP_NAME,
        "CFBundleDisplayName": APP_NAME,
        "CFBundleShortVersionString": VERSION,
        "CFBundleVersion": VERSION,
        "LSUIElement": True,
        "LSMinimumSystemVersion": "13.0",
        "LSApplicationCategoryType": "public.app-category.lifestyle",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "© 2026 dpsk. MIT License.",
    },
)
