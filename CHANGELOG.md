# Changelog

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
- Notifications with a Read more button (UserNotifications), Open at login
  (SMAppService), one instance only (opening it again opens the card).
- Settings in `~/Library/Application Support/MuseumWallpapers`, cache in
  `~/Library/Caches/MuseumWallpapers`, log in `~/Library/Logs/MuseumWallpapers`.
- PyInstaller app bundle with an ad-hoc signature and a self-test; .dmg for
  Apple silicon and Intel built on GitHub Actions.
