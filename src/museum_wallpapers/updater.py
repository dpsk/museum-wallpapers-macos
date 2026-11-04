"""Updates from the GitHub releases of this repository.

`check()` asks GitHub for the latest release at most once a day (or when
the user asks) and returns it when it is newer than this app and has a .dmg
for this Mac's architecture. `download()` fetches that .dmg and verifies its
size and the SHA-256 digest GitHub lists for it. `install()` mounts it,
checks the app inside (bundle identifier, version, signature), copies it next
to the running app and starts a small shell script that waits for this
process to quit, swaps the two bundles and opens the new one.

The app is not notarized: what vouches for an update is HTTPS to GitHub,
the release asset's digest, and the bundle identifier. Downloads made here
carry no quarantine flag, so Gatekeeper does not ask again after an update.
"""

import hashlib
import os
import platform
import plistlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

from . import BUNDLE_ID, REPO_URL, VERSION

REPO = "dpsk/museum-wallpapers-macos"
LATEST_API = os.environ.get("MUSEUM_WALLPAPERS_RELEASES_API", f"https://api.github.com/repos/{REPO}/releases/latest")
DOWNLOAD_PREFIX = f"https://github.com/{REPO}/releases/download/"
CHECK_EVERY = 24 * 3600
CHUNK = 1 << 16

# Waits (up to a minute) for the app to quit, puts the new bundle in place of
# the old one (putting the old one back if that fails), and opens it.
SWAP_SCRIPT = r'''
pid="$1"; app="$2"; new="$3"; launch="${4:-open}"; old="$app.old-$$"
i=0
while kill -0 "$pid" 2>/dev/null; do
  i=$((i + 1)); [ "$i" -gt 600 ] && exit 1; sleep 0.1
done
mv "$app" "$old" || exit 1
if mv "$new" "$app"; then rm -rf "$old"; else mv "$old" "$app"; exit 1; fi
xattr -dr com.apple.quarantine "$app" 2>/dev/null
"$launch" "$app"
'''


class UpdateError(Exception):
    """An update that could not be downloaded or installed."""


def parse_version(text):
    """(1, 2, 3) from "v1.2.3" or "1.2.3"; None for anything else."""
    match = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", str(text or "").strip())
    return tuple(int(part) for part in match.groups()) if match else None


def arch_name(machine=None):
    """The .dmg flavour for this process: apple-silicon or intel."""
    machine = machine or platform.machine()
    return {"arm64": "apple-silicon", "x86_64": "intel"}.get(machine, machine)


def asset_name(version, arch):
    return f"MuseumWallpapers-{version}-{arch}.dmg"


def release_from(data, arch):
    """What the app needs from GitHub's release JSON, or None when it is not a
    usable release. `asset` is '' when the release has no .dmg for `arch`
    (the user can still be sent to the release page)."""
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        return None
    version = parse_version(data.get("tag_name"))
    if not version:
        return None
    text = ".".join(str(part) for part in version)
    release = {"version": text, "page": data.get("html_url") or f"{REPO_URL}/releases", "asset": "", "size": 0,
               "sha256": ""}
    wanted = asset_name(text, arch)
    for asset in data.get("assets") or []:
        url = str(asset.get("browser_download_url") or "")
        if asset.get("name") == wanted and url.startswith(DOWNLOAD_PREFIX):
            digest = str(asset.get("digest") or "")
            release.update(asset=url, size=int(asset.get("size") or 0),
                           sha256=digest.split(":", 1)[1].lower() if digest.startswith("sha256:") else "")
    return release


def is_newer(release, current=VERSION):
    return bool(release) and (parse_version(release.get("version")) or ()) > (parse_version(current) or ())


def fetch_latest(http_json):
    """GitHub's latest release, or None when there is none (or the
    repository is not public)."""
    try:
        return http_json(LATEST_API, accept="application/vnd.github+json", timeout=30)
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise


def check(state_dir, http_json, read_json, write_json, force=False, now=None):
    """The newer release, or None. Asks GitHub at most once per CHECK_EVERY
    unless `force`; the answer is kept in update.json in `state_dir`."""
    now = time.time() if now is None else now
    path = Path(state_dir) / "update.json"
    saved = read_json(path, {}) or {}
    if not force and now - saved.get("checkedAt", 0) < CHECK_EVERY:
        latest = saved.get("latest")
    else:
        latest = release_from(fetch_latest(http_json), arch_name())
        write_json(path, {**saved, "checkedAt": now, "latest": latest})
    return latest if is_newer(latest) else None


def first_notice(state_dir, release, read_json, write_json):
    """True the first time a version is found, so the user hears of it once."""
    path = Path(state_dir) / "update.json"
    saved = read_json(path, {}) or {}
    if saved.get("notified") == release["version"]:
        return False
    write_json(path, {**saved, "notified": release["version"]})
    return True


# ----------------------------------------------------------------- download


def download(release, folder, user_agent, opener=urllib.request.urlopen):
    """The release's .dmg in `folder`, verified against its size and digest."""
    if not release.get("asset", "").startswith(DOWNLOAD_PREFIX):
        raise UpdateError("the release has no download for this Mac")
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / asset_name(release["version"], arch_name())
    part = dest.with_name(dest.name + ".part")
    digest, size = hashlib.sha256(), 0
    request = urllib.request.Request(release["asset"], headers={"User-Agent": user_agent})
    try:
        with opener(request, timeout=60) as response, open(part, "wb") as out:
            while True:
                chunk = response.read(CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
                size += len(chunk)
                out.write(chunk)
        if release.get("size") and size != release["size"]:
            raise UpdateError(f"download is {size} bytes, expected {release['size']}")
        if release.get("sha256") and digest.hexdigest() != release["sha256"]:
            raise UpdateError("download does not match its SHA-256 digest")
        part.replace(dest)
    finally:
        part.unlink(missing_ok=True)
    return dest


# ----------------------------------------------------------------- install


def bundle_path(executable=None):
    """The .app this process runs from, or None."""
    executable = Path(executable or sys.executable).resolve()
    return next((parent for parent in executable.parents if parent.suffix == ".app"), None)


def cannot_install(bundle):
    """Why the running app cannot replace itself, or '' when it can."""
    if bundle is None:
        return "not running from the app bundle"
    if "/AppTranslocation/" in str(bundle):
        return "macOS runs the app from a temporary copy; move it to Applications first"
    if not os.access(bundle.parent, os.W_OK) or not os.access(bundle, os.W_OK):
        return f"no permission to change {bundle.parent}"
    return ""


def _run(*command):
    result = subprocess.run([str(c) for c in command], capture_output=True, text=True, timeout=300)
    if result.returncode:
        raise UpdateError(f"{Path(str(command[0])).name} failed: {(result.stderr or result.stdout).strip()[:300]}")
    return result.stdout


# hdiutil sometimes answers "Resource temporarily unavailable" while it is
# busy with another image (seen on CI and on a Mac right after a .dmg was
# opened); it attaches a moment later.
ATTACH_TRIES = 5
ATTACH_WAIT = 2.0


def attach(dmg, mount, tries=ATTACH_TRIES, wait=ATTACH_WAIT):
    for attempt in range(tries):
        try:
            _run("hdiutil", "attach", "-nobrowse", "-readonly", "-noautoopen", "-mountpoint", mount, dmg)
            return
        except UpdateError as exc:
            if "temporarily unavailable" not in str(exc) or attempt == tries - 1:
                raise
            time.sleep(wait * (attempt + 1))


def verify_app(app, version):
    """The app inside the .dmg is this app, at the advertised version, with an
    intact signature."""
    try:
        with open(Path(app) / "Contents" / "Info.plist", "rb") as handle:
            info = plistlib.load(handle)
    except (OSError, plistlib.InvalidFileException) as exc:
        raise UpdateError(f"no app in the update: {exc}") from exc
    if info.get("CFBundleIdentifier") != BUNDLE_ID:
        raise UpdateError(f"the update is another app ({info.get('CFBundleIdentifier')})")
    if info.get("CFBundleShortVersionString") != version:
        raise UpdateError(f"the update is version {info.get('CFBundleShortVersionString')}, expected {version}")
    _run("codesign", "--verify", "--deep", "--strict", app)


def stage(dmg, version, bundle):
    """Copy the verified app out of the .dmg to a hidden folder beside
    `bundle` (same volume, so the swap is a rename); returns its path."""
    mount = Path(tempfile.mkdtemp(prefix="museum-wallpapers-update-"))
    attach(dmg, mount)
    try:
        apps = sorted(mount.glob("*.app"))
        if len(apps) != 1:
            raise UpdateError(f"expected one app in the update, found {len(apps)}")
        verify_app(apps[0], version)
        staged = bundle.parent / f".{bundle.stem}-{version}.app"
        shutil.rmtree(staged, ignore_errors=True)
        _run("ditto", apps[0], staged)
        verify_app(staged, version)
        return staged
    finally:
        if subprocess.run(["hdiutil", "detach", str(mount), "-quiet"], capture_output=True).returncode:
            subprocess.run(["hdiutil", "detach", str(mount), "-force", "-quiet"], capture_output=True)
        shutil.rmtree(mount, ignore_errors=True)


def start_swap(bundle, staged, pid=None, launch="open"):
    """Start the script that replaces `bundle` with `staged` once process
    `pid` (this one) has quit, and opens the new app with `launch`."""
    return subprocess.Popen(["/bin/sh", "-c", SWAP_SCRIPT, "museum-wallpapers-update", str(pid or os.getpid()),
                             str(bundle), str(staged), launch],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                            start_new_session=True)
