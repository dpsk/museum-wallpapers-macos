"""Updates from GitHub releases: finding, downloading, verifying, swapping."""

import hashlib
import io
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

from helpers import FakePlatform, app_module, core
from museum_wallpapers import BUNDLE_ID, VERSION, updater

PREFIX = updater.DOWNLOAD_PREFIX


def github_release(version="9.9.9", arch=None, digest=True, **extra):
    arch = arch or updater.arch_name()
    name = updater.asset_name(version, arch)
    return {"tag_name": f"v{version}", "html_url": f"https://github.com/{updater.REPO}/releases/tag/v{version}",
            "draft": False, "prerelease": False,
            "assets": [{"name": updater.asset_name(version, "other-arch"), "browser_download_url": PREFIX + "x/a.dmg"},
                       {"name": name, "browser_download_url": f"{PREFIX}v{version}/{name}", "size": 5,
                        **({"digest": "sha256:" + hashlib.sha256(b"12345").hexdigest()} if digest else {})}],
            **extra}


class ReleaseTest(unittest.TestCase):
    def test_versions(self):
        self.assertEqual(updater.parse_version("v0.10.2"), (0, 10, 2))
        self.assertIsNone(updater.parse_version("latest"))
        self.assertTrue(updater.is_newer({"version": "0.1.10"}, "0.1.9"))
        self.assertFalse(updater.is_newer({"version": VERSION}))
        self.assertFalse(updater.is_newer(None))

    def test_arch(self):
        self.assertEqual(updater.arch_name("arm64"), "apple-silicon")
        self.assertEqual(updater.arch_name("x86_64"), "intel")

    def test_picks_the_dmg_for_this_mac(self):
        release = updater.release_from(github_release(), updater.arch_name())
        self.assertEqual(release["version"], "9.9.9")
        self.assertTrue(release["asset"].endswith(updater.asset_name("9.9.9", updater.arch_name())))
        self.assertEqual((release["size"], release["sha256"]), (5, hashlib.sha256(b"12345").hexdigest()))

    def test_ignores_drafts_prereleases_and_foreign_urls(self):
        self.assertIsNone(updater.release_from(github_release(draft=True), "intel"))
        self.assertIsNone(updater.release_from(github_release(prerelease=True), "intel"))
        self.assertIsNone(updater.release_from({"tag_name": "nightly"}, "intel"))
        data = github_release(arch="intel")
        data["assets"][1]["browser_download_url"] = "https://evil.example/MuseumWallpapers.dmg"
        self.assertEqual(updater.release_from(data, "intel")["asset"], "")


class CheckTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.state = Path(self.tmp.name)
        self.calls = []

    def tearDown(self):
        self.tmp.cleanup()

    def check(self, answer, **kwargs):
        def http_json(url, **_kw):
            self.calls.append(url)
            if isinstance(answer, Exception):
                raise answer
            return answer
        return updater.check(self.state, http_json, core.read_json, core.write_json, **kwargs)

    def test_once_a_day_unless_asked(self):
        self.assertEqual(self.check(github_release())["version"], "9.9.9")
        self.assertEqual(self.check(github_release())["version"], "9.9.9")  # remembered
        self.assertEqual(len(self.calls), 1)
        self.check(github_release(), force=True)
        self.assertEqual(len(self.calls), 2)
        self.check(github_release(), now=time.time() + updater.CHECK_EVERY + 1)
        self.assertEqual(len(self.calls), 3)

    def test_same_or_older_is_no_update(self):
        self.assertIsNone(self.check(github_release(version=VERSION)))

    def test_no_release_or_private_repository(self):
        error = urllib.error.HTTPError(updater.LATEST_API, 404, "Not Found", {}, io.BytesIO())
        self.assertIsNone(self.check(error))

    def test_notifies_once_per_version(self):
        release = {"version": "9.9.9"}
        self.assertTrue(updater.first_notice(self.state, release, core.read_json, core.write_json))
        self.assertFalse(updater.first_notice(self.state, release, core.read_json, core.write_json))
        self.assertTrue(updater.first_notice(self.state, {"version": "9.9.10"}, core.read_json, core.write_json))


class DownloadTest(unittest.TestCase):
    def download(self, body, **release):
        release = {"version": "9.9.9", "asset": PREFIX + "v9.9.9/x.dmg", "size": len(b"12345"),
                   "sha256": hashlib.sha256(b"12345").hexdigest(), **release}
        opener = lambda request, timeout: io.BytesIO(body)  # noqa: E731
        with tempfile.TemporaryDirectory() as tmp:
            path = updater.download(release, tmp, "ua", opener=opener)
            return path.read_bytes(), sorted(p.name for p in Path(tmp).iterdir())

    def test_verified(self):
        body, files = self.download(b"12345")
        self.assertEqual(body, b"12345")
        self.assertEqual(files, [updater.asset_name("9.9.9", updater.arch_name())])

    def test_wrong_size_or_digest(self):
        with self.assertRaisesRegex(updater.UpdateError, "bytes"):
            self.download(b"1234")
        with self.assertRaisesRegex(updater.UpdateError, "SHA-256"):
            self.download(b"54321")

    def test_only_from_this_repositorys_releases(self):
        with self.assertRaises(updater.UpdateError):
            self.download(b"12345", asset="https://evil.example/x.dmg")


class InstallPlaceTest(unittest.TestCase):
    def test_reasons(self):
        self.assertIn("bundle", updater.cannot_install(None))
        self.assertIn("Applications", updater.cannot_install(
            Path("/private/var/folders/x/AppTranslocation/ABC/d/Museum Wallpapers.app")))
        with tempfile.TemporaryDirectory() as tmp:
            app = Path(tmp) / "Museum Wallpapers.app"
            app.mkdir()
            self.assertEqual(updater.cannot_install(app), "")
        self.assertEqual(updater.bundle_path("/Applications/Museum Wallpapers.app/Contents/MacOS/MuseumWallpapers"),
                         Path("/Applications/Museum Wallpapers.app"))


def fake_app(folder, version, bundle_id=BUNDLE_ID):
    app = Path(folder) / "Museum Wallpapers.app"
    (app / "Contents" / "MacOS").mkdir(parents=True)
    exe = app / "Contents" / "MacOS" / "MuseumWallpapers"
    exe.write_text("#!/bin/sh\nexit 0\n")
    exe.chmod(0o755)
    with open(app / "Contents" / "Info.plist", "wb") as handle:
        plistlib.dump({"CFBundleIdentifier": bundle_id, "CFBundleShortVersionString": version,
                       "CFBundleExecutable": "MuseumWallpapers", "CFBundlePackageType": "APPL"}, handle)
    subprocess.run(["codesign", "--force", "--sign", "-", str(app)], check=True, capture_output=True)
    return app


def fake_dmg(folder, app):
    dmg = Path(folder) / "update.dmg"
    subprocess.run(["hdiutil", "create", "-quiet", "-volname", "MW test", "-srcfolder", str(app.parent), "-ov",
                    "-format", "UDZO", str(dmg)], check=True, capture_output=True)
    return dmg


@unittest.skipUnless(sys.platform == "darwin", "macOS only: hdiutil, codesign")
class AttachTest(unittest.TestCase):
    BUSY = updater.UpdateError("hdiutil failed: hdiutil: attach failed - Resource temporarily unavailable")

    def test_a_busy_hdiutil_is_retried(self):
        with mock.patch.object(updater, "_run", side_effect=[self.BUSY, self.BUSY, ""]) as run, \
             mock.patch.object(updater.time, "sleep"):
            updater.attach("x.dmg", "/tmp/m")
        self.assertEqual(run.call_count, 3)

    def test_it_gives_up_after_a_few_tries(self):
        with mock.patch.object(updater, "_run", side_effect=self.BUSY) as run, \
             mock.patch.object(updater.time, "sleep"), self.assertRaises(updater.UpdateError):
            updater.attach("x.dmg", "/tmp/m")
        self.assertEqual(run.call_count, updater.ATTACH_TRIES)

    def test_other_errors_are_not_retried(self):
        broken = updater.UpdateError("hdiutil failed: image not recognized")
        with mock.patch.object(updater, "_run", side_effect=broken) as run, self.assertRaises(updater.UpdateError):
            updater.attach("x.dmg", "/tmp/m")
        self.assertEqual(run.call_count, 1)


class StageAndSwapTest(unittest.TestCase):
    """The real install path on a throwaway "Applications" folder."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(os.path.realpath(self.tmp.name))
        self.applications = root / "Applications"
        self.applications.mkdir()
        self.installed = fake_app(self.applications, "0.1.0")
        (root / "src").mkdir()
        self.dmg = fake_dmg(root, fake_app(root / "src", "9.9.9"))

    def tearDown(self):
        self.tmp.cleanup()

    def version(self, app):
        with open(app / "Contents" / "Info.plist", "rb") as handle:
            return plistlib.load(handle)["CFBundleShortVersionString"]

    def test_update_replaces_the_app_after_it_quits(self):
        staged = updater.stage(self.dmg, "9.9.9", self.installed)
        self.assertEqual(staged.parent, self.applications)
        self.assertEqual(self.version(staged), "9.9.9")
        running = subprocess.Popen(["sleep", "0.5"])  # stands in for the running app
        marker = self.applications / "launched"
        launcher = self.applications / "launch.sh"
        launcher.write_text(f'#!/bin/sh\necho "$1" > "{marker}"\n')
        launcher.chmod(0o755)
        swap = updater.start_swap(self.installed, staged, pid=running.pid, launch=str(launcher))
        time.sleep(0.2)
        self.assertEqual(self.version(self.installed), "0.1.0")  # still running: untouched
        running.wait()
        self.assertEqual(swap.wait(10), 0)
        self.assertEqual(self.version(self.installed), "9.9.9")
        self.assertEqual(marker.read_text().strip(), str(self.installed))
        self.assertEqual(sorted(p.name for p in self.applications.iterdir()),
                         ["Museum Wallpapers.app", "launch.sh", "launched"])

    def test_wrong_version_or_app_is_refused(self):
        with self.assertRaisesRegex(updater.UpdateError, "version"):
            updater.stage(self.dmg, "9.9.8", self.installed)
        other = Path(self.tmp.name) / "other"
        other.mkdir()
        dmg = fake_dmg(other, fake_app(other / "x", "9.9.9", bundle_id="com.example.Other"))
        with self.assertRaisesRegex(updater.UpdateError, "another app"):
            updater.stage(dmg, "9.9.9", self.installed)

    def test_tampered_app_is_refused(self):
        root = Path(self.tmp.name) / "tampered"
        app = fake_app(root / "src", "9.9.9")
        (app / "Contents" / "MacOS" / "MuseumWallpapers").write_text("#!/bin/sh\necho changed\n")
        with self.assertRaisesRegex(updater.UpdateError, "codesign"):
            updater.stage(fake_dmg(root, app), "9.9.9", self.installed)


class AppUpdateTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        root = Path(os.path.realpath(self.tmp.name))
        self.platform = FakePlatform()
        for patch in (mock.patch.object(core, "STATE", root / "state"),
                      mock.patch.object(core, "CACHE", root / "cache"),
                      mock.patch.object(core, "SETTINGS", root / "settings.json"),
                      mock.patch.object(core, "PLATFORM", self.platform)):
            patch.start()
        self.app = app_module.App()
        self.app.platform = self.platform
        self.release = updater.release_from(github_release(), updater.arch_name())

    def tearDown(self):
        mock.patch.stopall()
        self.tmp.cleanup()

    def test_found_update_shows_in_menu_card_and_once_as_notification(self):
        with mock.patch.object(updater, "check", return_value=self.release):
            self.app.check_updates()
            self.app.check_updates()
        self.assertEqual([n for n in self.platform.notifications if "9.9.9" in n[1]],
                         [("Museum Wallpapers", "Version 9.9.9 is available", ["Install and restart"])])
        titles = [item.title for item in self.app.menu()]
        self.assertIn("Install version 9.9.9 and restart", titles)
        self.assertEqual(self.app.card_data()["update"]["button"], "Install and restart")

    def test_manual_check_says_when_up_to_date(self):
        with mock.patch.object(updater, "check", return_value=None):
            self.app.check_updates(manual=True)
        self.assertIn(f"latest version ({VERSION})", self.platform.notifications[-1][1])

    def test_automatic_check_can_be_turned_off(self):
        core.save_setting("checkForUpdates", False)
        with mock.patch.object(updater, "check") as check:
            self.app.check_updates_due()
        check.assert_not_called()

    def test_copy_that_cannot_update_itself_opens_the_page(self):
        self.app.update = self.release
        with mock.patch.object(updater, "bundle_path", return_value=None):
            self.app.install_update()
        self.assertIn("cannot update itself", self.platform.notifications[-1][1])
        deadline = time.monotonic() + 2
        while not self.platform.opened and time.monotonic() < deadline:
            time.sleep(0.02)
        self.assertEqual(self.platform.opened, [self.release["page"]])

    def test_install_downloads_stages_swaps_and_quits(self):
        self.app.update = self.release
        bundle = Path(self.tmp.name) / "Museum Wallpapers.app"
        bundle.mkdir()
        with mock.patch.object(updater, "bundle_path", return_value=bundle), \
                mock.patch.object(updater, "download", return_value=Path(self.tmp.name) / "u.dmg") as download, \
                mock.patch.object(updater, "stage", return_value=Path(self.tmp.name) / ".new.app") as stage, \
                mock.patch.object(updater, "start_swap") as swap, \
                mock.patch.object(self.app, "quit") as quit_app:
            self.app.install_update()
            deadline = time.monotonic() + 3
            while not quit_app.called and time.monotonic() < deadline:
                time.sleep(0.02)
        download.assert_called_once()
        stage.assert_called_once_with(Path(self.tmp.name) / "u.dmg", "9.9.9", bundle)
        swap.assert_called_once_with(bundle, Path(self.tmp.name) / ".new.app")
        quit_app.assert_called_once()

    def test_failed_install_explains_and_opens_the_page(self):
        self.app.update = self.release
        bundle = Path(self.tmp.name) / "Museum Wallpapers.app"
        bundle.mkdir()
        with mock.patch.object(updater, "bundle_path", return_value=bundle), \
                mock.patch.object(updater, "download", side_effect=updater.UpdateError("digest mismatch")):
            self.app.install_update()
            deadline = time.monotonic() + 3
            while not self.platform.opened and time.monotonic() < deadline:
                time.sleep(0.02)
        self.assertIn("digest mismatch", self.platform.notifications[-1][1])
        self.assertFalse(self.app.updating.locked())


if __name__ == "__main__":
    unittest.main()
