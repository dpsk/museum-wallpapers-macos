"""The .dmg's Finder window: the app, an arrow, Applications, and below them
how to allow the unnotarized app on its first start (macOS shows its own
dialog before any of the app's code runs, so this is the place to say it).

The background is drawn with Pillow at 1x and 2x and joined into one
Retina TIFF; dmgbuild writes the window layout straight into the image's
.DS_Store, without Finder, so it works on CI runners too."""

import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

WIDTH, HEIGHT = 640, 440
ICON_SIZE = 112
APP_AT = (170, 170)
APPLICATIONS_AT = (470, 170)

PAPER = (247, 242, 232)
INK = (52, 44, 34)
MUTED = (120, 106, 88)
GOLD = (201, 158, 72)
RULE = (226, 214, 190)

STEPS = [
    "First start",
    "macOS cannot verify the app (it is not notarized). Click Done,",
    "then System Settings → Privacy & Security → Open Anyway.",
]
HEADING = "Drag Museum Wallpapers to Applications"
TERMINAL = "Or install without this step, in Terminal: github.com/dpsk/museum-wallpapers-macos"

FONT = "/System/Library/Fonts/SFNS.ttf"


def _font(size, weight="Regular"):
    try:
        font = ImageFont.truetype(FONT, size)
        try:
            font.set_variation_by_name(weight)
        except (OSError, ValueError, AttributeError):
            pass
        return font
    except OSError:
        return ImageFont.load_default(size)


def background(scale):
    s = scale
    image = Image.new("RGB", (WIDTH * s, HEIGHT * s), PAPER)
    draw = ImageDraw.Draw(image)

    draw.text((WIDTH * s // 2, 48 * s), HEADING, font=_font(17 * s, "Semibold"), fill=INK, anchor="ma")

    # The arrow from the app to Applications, a little above the icons' centre.
    y = APP_AT[1] * s
    x0, x1 = (APP_AT[0] + ICON_SIZE // 2 + 28) * s, (APPLICATIONS_AT[0] - ICON_SIZE // 2 - 28) * s
    draw.line((x0, y, x1 - 10 * s, y), fill=GOLD, width=4 * s)
    draw.polygon([(x1, y), (x1 - 18 * s, y - 11 * s), (x1 - 18 * s, y + 11 * s)], fill=GOLD)

    # The first-start note, under a thin rule.
    top = 288
    draw.line((48 * s, top * s, (WIDTH - 48) * s, top * s), fill=RULE, width=s)
    title, body, small = _font(15 * s, "Semibold"), _font(13 * s), _font(11 * s)
    draw.text((WIDTH * s // 2, (top + 18) * s), STEPS[0], font=title, fill=INK, anchor="ma")
    for i, line in enumerate(STEPS[1:]):
        draw.text((WIDTH * s // 2, (top + 44 + i * 20) * s), line, font=body, fill=INK, anchor="ma")
    draw.text((WIDTH * s // 2, (top + 100) * s), TERMINAL, font=small, fill=MUTED, anchor="ma")
    return image


def write_background(folder):
    """background.tiff with 1x and 2x images, for sharp text on Retina."""
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    one, two = folder / "background.png", folder / "background@2x.png"
    background(1).save(one, dpi=(72, 72))
    background(2).save(two, dpi=(144, 144))
    tiff = folder / "background.tiff"
    subprocess.run(["tiffutil", "-cathidpicheck", str(one), str(two), "-out", str(tiff)],
                   check=True, capture_output=True)
    return tiff


def build(app, dmg, volume_name, folder):
    """dmg with `app`, an Applications link and the laid-out window."""
    import dmgbuild

    app = Path(app)
    dmgbuild.build_dmg(str(dmg), volume_name, settings={
        "format": "UDZO",
        "files": [str(app)],
        "symlinks": {"Applications": "/Applications"},
        "icon": str(app / "Contents" / "Resources" / "icon.icns"),
        "background": str(write_background(folder)),
        "window_rect": ((200, 120), (WIDTH, HEIGHT)),
        "default_view": "icon-view",
        "show_status_bar": False,
        "show_tab_view": False,
        "show_toolbar": False,
        "show_pathbar": False,
        "show_sidebar": False,
        "icon_size": ICON_SIZE,
        "text_size": 13,
        "icon_locations": {app.name: APP_AT, "Applications": APPLICATIONS_AT},
    })
