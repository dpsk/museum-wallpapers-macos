#!/bin/bash
# Install or update Museum Wallpapers from the latest GitHub release:
#
#   curl -fsSL https://raw.githubusercontent.com/dpsk/museum-wallpapers-macos/main/install.sh | bash
#
# A file curl downloads is not quarantined, so macOS does not stop the
# unnotarized app on first start. The .dmg is checked against the release's
# size and SHA-256, and the app inside against its bundle id and signature,
# before it replaces anything.
#
# MUSEUM_WALLPAPERS_VERSION=0.1.0 picks a release; MUSEUM_WALLPAPERS_DIR
# installs somewhere other than /Applications.

set -euo pipefail

REPO="dpsk/museum-wallpapers-macos"
APP="Museum Wallpapers.app"
BUNDLE_ID="io.github.dpsk.MuseumWallpapers"

say() { printf '\033[1m==>\033[0m %s\n' "$*"; }
die() { printf '\033[31mError:\033[0m %s\n' "$*" >&2; exit 1; }

# Everything runs from main, so a download cut short runs nothing.
main() {
    [ "$(uname -s)" = Darwin ] || die "Museum Wallpapers is a macOS app."
    local major
    major=$(sw_vers -productVersion | cut -d. -f1)
    [ "$major" -ge 13 ] || die "macOS 13 Ventura or later is needed (this is $(sw_vers -productVersion))."

    # hw.optional.arm64 is 1 on Apple silicon, also from a shell under Rosetta.
    local arch=intel
    [ "$(sysctl -n hw.optional.arm64 2>/dev/null || echo 0)" = 1 ] && arch=apple-silicon

    local api="https://api.github.com/repos/$REPO/releases/latest"
    [ -n "${MUSEUM_WALLPAPERS_VERSION:-}" ] && api="https://api.github.com/repos/$REPO/releases/tags/v${MUSEUM_WALLPAPERS_VERSION#v}"

    tmp=$(mktemp -d -t museum-wallpapers)
    mount=""
    trap cleanup EXIT

    say "Looking up the release"
    curl -fsSL -H "Accept: application/vnd.github+json" "$api" -o "$tmp/release.json" \
        || die "no such release, or GitHub cannot be reached ($api)."
    # JavaScript for Automation reads the JSON: no jq or Python on a fresh Mac.
    local fields version url size digest
    fields=$(osascript -l JavaScript - "$tmp/release.json" "$arch" <<'JS'
function run(argv) {
    const text = $.NSString.stringWithContentsOfFileEncodingError(argv[0], $.NSUTF8StringEncoding, null).js;
    const release = JSON.parse(text);
    const version = String(release.tag_name || "").replace(/^v/, "");
    const name = `MuseumWallpapers-${version}-${argv[1]}.dmg`;
    const asset = (release.assets || []).find(a => a.name === name);
    if (!asset) return "";
    return [version, asset.browser_download_url, asset.size, asset.digest || ""].join("\n");
}
JS
    ) || true
    [ -n "$fields" ] || die "the release has no .dmg for $arch Macs."
    { read -r version; read -r url; read -r size; read -r digest; } <<<"$fields"

    say "Downloading Museum Wallpapers $version ($arch)"
    curl -fL --progress-bar "$url" -o "$tmp/app.dmg" || die "the download failed."
    [ "$(stat -f %z "$tmp/app.dmg")" = "$size" ] || die "the download has the wrong size."
    if [ -n "$digest" ]; then
        [ "sha256:$(shasum -a 256 "$tmp/app.dmg" | cut -d' ' -f1)" = "$digest" ] \
            || die "the download does not match the release's SHA-256."
    fi

    mount="$tmp/mount"
    mkdir "$mount"
    hdiutil attach -nobrowse -readonly -noautoopen -quiet -mountpoint "$mount" "$tmp/app.dmg" \
        || die "could not open the .dmg."
    local new="$mount/$APP"
    [ -d "$new" ] || die "the .dmg has no $APP."
    [ "$(defaults read "$new/Contents/Info" CFBundleIdentifier)" = "$BUNDLE_ID" ] \
        || die "the .dmg holds a different app."
    codesign --verify --deep --strict "$new" 2>/dev/null || die "the app's signature does not verify."

    local dir="${MUSEUM_WALLPAPERS_DIR:-/Applications}"
    local sudo=""
    mkdir -p "$dir" 2>/dev/null || true
    if [ ! -w "$dir" ] || { [ -e "$dir/$APP" ] && [ ! -w "$dir/$APP" ]; }; then
        say "$dir needs an administrator password"
        sudo="sudo"
    fi

    if pgrep -xq MuseumWallpapers; then
        say "Quitting the running Museum Wallpapers"
        osascript -e "tell application id \"$BUNDLE_ID\" to quit" >/dev/null 2>&1 || true
        local i
        for i in $(seq 1 20); do pgrep -xq MuseumWallpapers || break; sleep 0.5; done
        pkill -x MuseumWallpapers 2>/dev/null || true
    fi

    say "Installing to $dir"
    # Copy beside the old app, then swap: a failed copy leaves the old one.
    $sudo rm -rf "$dir/.$APP.new"
    $sudo ditto "$new" "$dir/.$APP.new"
    $sudo rm -rf "$dir/$APP"
    $sudo mv "$dir/.$APP.new" "$dir/$APP"
    $sudo xattr -dr com.apple.quarantine "$dir/$APP" 2>/dev/null || true

    say "Starting Museum Wallpapers $version"
    open "$dir/$APP"
    echo "The frame icon is in the menu bar; the first painting follows in a few seconds."
    echo "It updates itself from now on (menu: Check for Updates…)."
}

cleanup() {
    if [ -n "${mount:-}" ] && [ -d "$mount" ]; then
        hdiutil detach -quiet "$mount" 2>/dev/null || hdiutil detach -quiet -force "$mount" 2>/dev/null || true
    fi
    rm -rf "${tmp:-}"
}

main "$@"
