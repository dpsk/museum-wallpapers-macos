# Handoff: Museum Wallpapers for macOS

What is left to ship 0.1.0, to do on your own Mac. The app was written and
tested on a work MacBook whose wallpaper is managed by the organisation, so
everything that changes the real desktop, asks macOS for a permission or
publishes something was left for here.

## Status — 2026-11-04

Done and pushed to `main`:

- The app: menu bar icon, the Omarchy-style card (WKWebView in a popover),
  the menu, wallpaper per screen through NSWorkspace, re-applied on Space
  changes, the SF Mono caption, notifications, Open at login, one instance.
- Language switch in the card (Auto / EN / RU; more in the menu). Picking
  never depends on the language; descriptions prefer the reader's language
  (painting article, then artist article) before English.
- The updater (`src/museum_wallpapers/updater.py`): daily check of the latest
  GitHub release, download verified by size and SHA-256, bundle id / version /
  signature checks, swap after quit, relaunch.
- Packaging: `python packaging/build.py` makes `dist/Museum Wallpapers.app`
  (ad-hoc signed, self-tested) and `dist/MuseumWallpapers-0.1.0-<arch>.dmg`.

Verified on the work Mac (Apple silicon, macOS 26):

- 162 unit tests pass, including a real WKWebView loading the card and a full
  update cycle with `hdiutil` and `codesign` on a throwaway Applications folder.
- The built app passes its self-test (`selftest` finds every module, the
  screen, fonts, framing).
- The menu bar app ran against the fake desktop (`MUSEUM_WALLPAPERS_PLATFORM=dev`):
  first painting, the card in English and Russian, the language switch
  re-describing and re-captioning the painting on screen, a second launch
  opening the card. Snapshots are in `screenshots/`.
- The real 0.1.0 .dmg goes through the updater's staging (mount, verify,
  copy) cleanly.

On the personal Mac (M1 Pro, macOS 26.5.2, one display), 2026-11-04 evening:

- 169 tests pass; the live wallpaper round trip passes.
- Found and fixed: macOS 26 reports a new wallpaper only a moment after it is
  set, so the cleanup deleted the framed copy it had just set and the desktop
  stayed default.
- Bundled painter lists: a wiped install shows its first painting in 15 s
  (was 77 s); both refreshes finish in the background.
- GitHub refused to make the private repository public (HTTP 422 "A previous
  repository operation is still in progress" for 35+ minutes), so it was
  deleted and created again as public; the CI workflow is in place.
- SSH pushes fail from this Mac (`Permission denied (publickey)`); HTTPS
  through `gh auth git-credential` works.

Not verified yet:

1. The real wallpaper on several displays and Spaces (one display works).
2. Notifications from the bundled app (permission prompt, banner, the Read
   more button, clicking the notification).
3. Open at login through SMAppService for an ad-hoc signed app (macOS may
   ask for approval in Login Items).
4. Gatekeeper on first start of the downloaded .dmg (Open Anyway).
5. The Intel build (CI builds it on `macos-15-intel`).
6. An update from a real release to a newer one.

## Steps

### 1. Clone and run the tests

```bash
git clone git@github.com:dpsk/museum-wallpapers-macos.git && cd museum-wallpapers-macos
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest -q          # expect 162 passed, 1 skipped (~45 s: the updater tests mount .dmg files)
```

### 4. Watch the first CI run

`gh run watch` or the Actions tab. Jobs:

- `test-linux`: core, card and app logic on the dev platform.
- `macos (macos-15, apple-silicon)` and `macos (macos-15-intel, intel)`:
  tests, a live wallpaper round trip on the runner (non-fatal; read its
  output, it prints the wallpaper before and after), build, self-test, .dmg.

If GitHub says the `macos-15-intel` label does not exist, use whatever Intel
macOS image is current, or drop that matrix entry and say in the README that
only Apple silicon is built.

### 5. Try the real app on your Mac

```bash
.venv/bin/python packaging/build.py
open dist/MuseumWallpapers-0.1.0-apple-silicon.dmg      # drag to Applications
```

A locally built .dmg is not quarantined, so Gatekeeper will not ask. To see
what users see, try the .dmg from the CI artifact or the release (step 6)
too, downloaded with a browser.

Checklist:

- [ ] First start: notification "Museum Wallpapers is running…", frame icon
      in the menu bar, first painting within about a minute (the first start
      fetches the painter list from Wikidata).
- [ ] Every display gets its painting; the caption sits clear of the menu bar
      and the Dock, in SF Mono.
- [ ] Switch Spaces: the other Space gets the painting too. Try with
      System Settings → Wallpaper → *Show on all Spaces* on and off.
- [ ] Click: the card opens under the icon, without an arrow (this uses
      NSPopover's private `shouldHideAnchor`; if a macOS version ignores it,
      the arrow simply stays). Click elsewhere: it closes. Light and dark mode.
- [ ] Card buttons: Next (shows Loading…), Read more (browser), Save (to
      `~/Pictures/Museum Wallpapers` with `CREDITS.md`), More by …, the ×
      that clears the filter, every settings row, Settings … (the menu).
- [ ] Language RU: the card switches at once; within a minute the caption on
      the wallpaper is redrawn in Russian.
- [ ] Right-click / Control-click: the menu; middle-click: next painting.
- [ ] Notifications: turn on *Notify when it changes*, press Next. macOS asks
      for permission once; the banner has the painting and a Read more
      button that opens the article; clicking the banner opens it too. If
      nothing appears and the log has no error, look in System Settings →
      Notifications → Museum Wallpapers.
- [ ] *Open at login*: on, log out and in. The app starts without opening the
      card (login detection: the launch Apple event, or uptime under three
      minutes). If macOS wants approval, the app opens Login Items for you.
- [ ] Open the app again from Applications while it runs: the card opens.
- [ ] Sleep and wake; unplug and plug a display; turn Wi-Fi off and press Next
      (a painting from the cache or `~/Pictures/Museum Wallpapers`, an error
      in the card).
- [ ] `Check for Updates…` before any release: "You have the latest version"
      (or, while the repository is private, nothing found).
- [ ] Log: `~/Library/Logs/MuseumWallpapers/museum-wallpapers.log`.

Fix what this finds, run the tests, push.

### 6. Release 0.1.0

Refresh the bundled painter lists first (about a minute; commit if they
changed):

```bash
.venv/bin/python packaging/seed.py && git add src/museum_wallpapers/data && git commit -m "data: painter lists"
git tag v0.1.0 && git push origin v0.1.0
```

CI attaches `MuseumWallpapers-0.1.0-apple-silicon.dmg` and
`MuseumWallpapers-0.1.0-intel.dmg` to the release. The asset names matter:
the updater looks for exactly `MuseumWallpapers-<version>-<arch>.dmg`.
Download one with a browser and walk the Gatekeeper steps in the README
(Open Anyway in Privacy & Security, or `xattr -dr com.apple.quarantine`).

### 7. Test the updater end to end

1. Install 0.1.0 from the release into `/Applications`.
2. Bump `VERSION` in `src/museum_wallpapers/__init__.py` to `0.1.1`, add a
   CHANGELOG entry, commit, tag `v0.1.1`, push; wait for the release.
3. In 0.1.0: `Check for Updates…` → notification "Version 0.1.1 is
   available" → Install and restart (card or menu). The app quits and comes
   back; the card or `selftest` shows 0.1.1.
4. Also try: running the app straight from the mounted .dmg (it should open
   the release page instead, because it cannot replace itself), and the
   daily check (delete `~/Library/Application Support/MuseumWallpapers/state/update.json`
   and wait a minute after start).

The update check uses the release's `digest` field (SHA-256) from the GitHub
API; if a release lacks it, only the size is checked. Bundle id, version and
`codesign --verify --deep --strict` are always checked.

## Later

- **Notarization.** A Developer ID ($99/year) plus `notarytool` removes the
  Gatekeeper step. Then the updater should also check the Team ID
  (`codesign -dv`) of the new app against the running one.
- **Universal build.** One .dmg for both architectures needs universal2
  wheels for every dependency (Pillow ships per-arch wheels), so two .dmg
  files are simpler for now.
- **Hotkeys.** Global shortcuts for Next and the card (off by default), as in
  the Omarchy plugin.

## Porting the updater to Windows

`updater.py` splits cleanly:

- Reusable as is: `parse_version`, `is_newer`, `release_from` (with an asset
  name like `MuseumWallpapers-Setup-<version>.exe`), `check` with its daily
  throttle and `update.json`, `first_notice`, `download` with size and
  SHA-256 checks, the `DOWNLOAD_PREFIX` rule.
- Windows-specific: instead of `stage`/`start_swap`, run the downloaded Inno
  Setup installer with `/VERYSILENT /SUPPRESSMSGBOXES /NORESTART` from a
  detached process and quit; `installer.iss` should have
  `CloseApplications=yes` and start the app at the end (a `[Run]` entry
  without `skipifsilent`). Check the installer's Authenticode status only if
  it gets signed.
- The Microsoft Store build must not update itself: the Store does it. Hide
  the menu items and skip the check when `platform.packaged` is true.
- App side: `app.py` here (`check_updates_due`, `check_updates`,
  `install_update`, the menu items, `card.data(update=…)`) maps onto the
  Windows tray menu and Tk card one to one; the strings are in `strings.py`.

## Gotchas found on the way

- **PyObjC and completion handlers.** A Python class that declares a formal
  protocol (`class X(NSObject, protocols=[...])`) loses the block signatures
  PyObjC has for that protocol's methods, and calling a `decisionHandler` or
  `completionHandler` then aborts the whole app ("cannot call block without a
  signature"). `macui.Bridge` therefore implements WKNavigationDelegate
  without declaring it, and the notification delegate declares nothing.
  `tests/test_macos.py` checks the signatures are visible.
- **Hidden web views do not run animation frames.** The card reports its
  height synchronously; with `requestAnimationFrame` the popover would wait
  for a message that never comes.
- **SF Mono is a variable font.** Pillow opens it at Light; `framing._regular`
  switches to Regular.
- **macOS redraws a wallpaper only when its path changes,** so the language
  is part of a framed copy's file name (`…bottom-right-ru…`).
- **The first start used to be slow** (77 s): two Wikidata queries, the painter
  list and its 38k paintings. They now ship in `src/museum_wallpapers/data`
  (`packaging/seed.py`), answered at once and refreshed behind (`refresh_later`
  in core.py); first painting in ~15 s. The same code ports to Windows as is.
- **macOS 26 reports a new wallpaper a second or two after it was set.** The
  cleanup after a switch used to delete the framed copy it had just set.
