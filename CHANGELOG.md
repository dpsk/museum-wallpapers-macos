# Changelog

## 0.2.1 — 2026-11-06

- **By default only paintings with a Wikipedia article in your language**
  (In my language → Only described ones; Described means → Has a Wikipedia
  article in my language), so the card tells the painting's own story. A
  search round still takes ~6–10 s (measured for Russian and English). The
  queue is refilled once after the update, since it was fetched for the old
  default; a setting chosen in the menu stays as it was.

## 0.2.0 — 2026-11-06

From the Omarchy plugin 0.1.3–0.1.4 (#2):

- **The card is for the painting.** The settings rows are gone from it; a
  gear in the card opens the menu, where every setting is. With the room,
  the story is longer: six sentences of Wikipedia (was four), 600
  characters of a Commons description (was 400), 14 lines in the card.
- **Ten interface languages:** English, Русский, Українська, Deutsch,
  Français, Español, Italiano, Nederlands, Polski, Português. Error
  messages are translated too. A language without a table gets an English
  interface (titles and stories still come in it); a broken strings file
  falls back to English.
- **In my language** (menu): paintings described in your language first
  (default), only those, or no preference; **Described means** a title in
  your language (default) or a Wikipedia article. For Russian only ~21% of
  the famous painters' works have a Russian title and ~12% an article.
  Paintings already queued stay queued after the update.

## 0.1.5 — 2026-11-06

Speed fixes found in the Omarchy plugin (#1):

- A painting is found ~5x faster: the search asks Commons for sizes and
  URLs only, and the file's title, artist and date fields only for the one
  painting picked (50 files: 0.85 s instead of 11 s). One fetch on a first
  start: 7 s instead of 34 s.
- Threads that need the same uncached pool run one Wikidata query between
  them instead of one each.
- A Next no longer waits up to a minute for a download claimed by a process
  that was killed.
- The bundled painter lists and pools are refreshed.

## 0.1.4 — 2026-11-04

0.1.2 and 0.1.3 were tagged but never released: their builds failed on the
hdiutil problem fixed here.

- The .dmg opens as a laid-out window: the app, an arrow to Applications,
  and how to allow the app on its first start (Done, then System Settings →
  Privacy & Security → Open Anyway), with the one-line Terminal install as
  the way around it.
- Updates wait for up to a minute while `hdiutil` is busy with the
  downloaded .dmg ("Resource temporarily unavailable") instead of failing.

## 0.1.1 — 2026-11-04

- Fixed: the released 0.1.0 could not reach Wikimedia or GitHub
  (`CERTIFICATE_VERIFY_FAILED`), so it showed no painting and could not check
  for updates. HTTPS is now verified with the macOS Keychain. 0.1.0 cannot
  update itself to this version: download it again, or install with
  `curl -fsSL https://raw.githubusercontent.com/dpsk/museum-wallpapers-macos/main/install.sh | bash`.
- Install with that one line in Terminal, without the Open Anyway step.

## 0.1.0 — 2026-11-04

First macOS version, built on the core of museum-wallpapers-windows 0.1.2 (its
faster Next, prefetch queue and framing ahead) with the Omarchy plugin's
popup card.

- Menu bar app: click the frame icon for the card, right-click for the menu,
  middle-click for the next painting.
- The card, laid out like the plugin's popup: preview, title, artist,
  museum, story, Next / Read more / Save, More by … / More …, and rows for
  the interval, artists, fit, caption and language. Follows light and dark
  mode.
- Language switch in the card (Auto, EN, RU; more in the menu). It changes the
  interface and the description of the painting on screen at once, caption
  included. Descriptions now prefer the reader's language: the painting's
  article, then the artist's article in that language, before falling back to
  English; the card says when the story is in another language. "About the
  artist" is translated. Which paintings are picked never depends on the
  language.
- Wallpaper per display through NSWorkspace, sized for each screen's Retina
  resolution, re-applied when another Space comes up, re-framed when screens
  or the Dock change and after waking from sleep.
- Caption in the style of the plugin's placard: SF Mono italic title, then
  artist, year and museum on one line, clear of the menu bar and Dock.
- Fast first start: the "known" and "famous" painter lists and their
  paintings ship with the app, so the first painting appears in about 15 s
  instead of over a minute. They, and a cache older than a week, are used at
  once and refreshed from Wikidata in the background.
- Updates from GitHub releases: checked once a day (or from the menu),
  offered in the card and the menu, installed with one click after checking
  the download's size and SHA-256 digest and the app's bundle identifier,
  version and signature; the app restarts as the new version.
- Notifications with a Read more button (UserNotifications), Open at login
  (SMAppService), one instance only (opening it again opens the card).
- Settings in `~/Library/Application Support/MuseumWallpapers`, cache in
  `~/Library/Caches/MuseumWallpapers`, log in `~/Library/Logs/MuseumWallpapers`.
- PyInstaller app bundle with an ad-hoc signature and a self-test; .dmg for
  Apple silicon and Intel built on GitHub Actions.
