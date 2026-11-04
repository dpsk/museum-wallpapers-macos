"""Build "Museum Wallpapers.app" and a .dmg to install it from, on macOS:

  python packaging/build.py

1. the app icon (icon.icns) from resources.py;
2. PyInstaller with MuseumWallpapers.spec (an app bundle for this Mac's
   architecture: arm64 on Apple silicon, x86_64 on Intel);
3. an ad-hoc signature over the whole bundle (no Developer ID: Gatekeeper
   asks the user to allow it once, see README);
4. the built app's own self-test, in a throwaway home; the build fails if
   it fails;
5. dist/MuseumWallpapers-<version>-<apple-silicon|intel>.dmg with the app and
   an Applications link to drag it onto.
"""

import json
import os
import platform
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
BUILD = HERE / "build"
DIST = ROOT / "dist"
sys.path.insert(0, str(ROOT / "src"))

from museum_wallpapers import APP_NAME, VERSION, resources  # noqa: E402


def run(*command, **options):
    print("+", " ".join(str(c) for c in command), flush=True)
    subprocess.run([str(c) for c in command], check=True, **options)


def arch_name():
    return {"arm64": "apple-silicon", "x86_64": "intel"}.get(platform.machine(), platform.machine())


def main():
    if sys.platform != "darwin":
        sys.exit("The app bundle can only be built on macOS.")
    BUILD.mkdir(parents=True, exist_ok=True)
    resources.write_icns(BUILD / "icon.icns")

    app = DIST / f"{APP_NAME}.app"
    shutil.rmtree(app, ignore_errors=True)
    run(sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", DIST,
        "--workpath", BUILD / "work", HERE / "MuseumWallpapers.spec")

    run("codesign", "--force", "--deep", "--sign", "-", app)
    run("codesign", "--verify", "--deep", "--strict", "--verbose=2", app)

    report = BUILD / "selftest.json"
    report.unlink(missing_ok=True)
    with tempfile.TemporaryDirectory(prefix="museum-wallpapers-selftest-") as home:
        env = {**os.environ, "MUSEUM_WALLPAPERS_HOME": home}
        result = subprocess.run([str(app / "Contents" / "MacOS" / "MuseumWallpapers"), "selftest", "--out", str(report)],
                                env=env, timeout=300)
    if not report.exists():
        sys.exit(f"self-test wrote no report (exit code {result.returncode})")
    data = json.loads(report.read_text(encoding="utf-8"))
    failed = {k: v for k, v in data["modules"].items() if v != "ok"}
    failed.update({k: v.get("error") for k, v in data["checks"].items() if not v["ok"]})
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if result.returncode or not data["ok"]:
        sys.exit(f"self-test of the built app failed: {failed}")

    staging = BUILD / "dmg"
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)
    run("ditto", app, staging / app.name)
    (staging / "Applications").symlink_to("/Applications")
    dmg = DIST / f"MuseumWallpapers-{VERSION}-{arch_name()}.dmg"
    dmg.unlink(missing_ok=True)
    run("hdiutil", "create", "-volname", APP_NAME, "-srcfolder", staging, "-ov", "-format", "UDZO", dmg)
    print(f"built {dmg} ({dmg.stat().st_size / 1e6:.1f} MB)")


if __name__ == "__main__":
    main()
