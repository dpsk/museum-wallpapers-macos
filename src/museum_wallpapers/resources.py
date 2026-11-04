"""The app icon (a small gilt frame around a landscape) and the menu bar
glyph, drawn with Pillow so the repository needs no binary art; packaging
writes the app icon out as icon.icns."""

import sys
from pathlib import Path

from PIL import Image, ImageDraw

GOLD = (201, 158, 72, 255)
GOLD_DARK = (128, 92, 34, 255)
GOLD_LIGHT = (240, 206, 128, 255)
SKY = (120, 168, 214, 255)
SKY_LOW = (236, 196, 140, 255)
HILL = (70, 112, 74, 255)
HILL_FAR = (112, 150, 110, 255)
SUN = (255, 236, 170, 255)


def icon_image(size=256):
    """The icon at `size` px, drawn at 4x and scaled down for smooth edges."""
    s = size * 4
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    u = s / 64
    # Frame: dark outer edge, gold body, light inner bevel.
    draw.rounded_rectangle((2 * u, 6 * u, 62 * u, 58 * u), radius=3 * u, fill=GOLD_DARK)
    draw.rounded_rectangle((4 * u, 8 * u, 60 * u, 56 * u), radius=2 * u, fill=GOLD)
    draw.rectangle((10 * u, 14 * u, 54 * u, 50 * u), fill=GOLD_LIGHT)
    # Canvas: a sky fading to evening light, a sun, two hills.
    top, bottom = 15 * u, 49 * u
    for y in range(int(top), int(bottom)):
        t = (y - top) / (bottom - top)
        color = tuple(int(a + (b - a) * t) for a, b in zip(SKY, SKY_LOW))
        draw.line((11 * u, y, 53 * u, y), fill=color)
    draw.ellipse((38 * u, 20 * u, 46 * u, 28 * u), fill=SUN)
    draw.polygon([(11 * u, 40 * u), (24 * u, 30 * u), (36 * u, 38 * u), (53 * u, 32 * u), (53 * u, 49 * u),
                  (11 * u, 49 * u)], fill=HILL_FAR)
    draw.polygon([(11 * u, 46 * u), (22 * u, 39 * u), (34 * u, 44 * u), (46 * u, 40 * u), (53 * u, 43 * u),
                  (53 * u, 49 * u), (11 * u, 49 * u)], fill=HILL)
    return image.resize((size, size), Image.Resampling.LANCZOS)


ICNS_SIZES = [(16, 16), (32, 32), (64, 64), (128, 128), (256, 256), (512, 512), (1024, 1024)]


def write_icns(path):
    """The app icon for the bundle (Contents/Resources/icon.icns)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    # A macOS icon sits inside a 1024 grid with a margin of about 10%.
    canvas = Image.new("RGBA", (1024, 1024), (0, 0, 0, 0))
    icon = icon_image(824)
    canvas.paste(icon, (100, 100), icon)
    canvas.save(path, format="ICNS", sizes=ICNS_SIZES)
    return path


def menu_bar_icon(points=18, scale=2, busy=False):
    """The menu bar glyph: a picture frame around hills and a sun, black on
    transparent (macOS tints a template image for light and dark menu bars).
    `points` is its size in points, `scale` the pixels per point."""
    s = points * scale * 4
    image = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    u = s / 18
    ink = (0, 0, 0, 255)
    draw.rounded_rectangle((1 * u, 3 * u, 17 * u, 15 * u), radius=1.6 * u, outline=ink, width=round(1.5 * u))
    draw.ellipse((11.2 * u, 5.6 * u, 13.8 * u, 8.2 * u), fill=ink)
    draw.polygon([(3 * u, 13.2 * u), (7 * u, 8.4 * u), (10 * u, 11.4 * u), (12 * u, 9.8 * u), (15 * u, 13.2 * u)],
                 fill=ink)
    if busy:
        image.putalpha(image.getchannel("A").point(lambda a: a // 2))
    return image.resize((points * scale, points * scale), Image.Resampling.LANCZOS)


def png_bytes(image):
    import io
    out = io.BytesIO()
    image.save(out, format="PNG")
    return out.getvalue()


if __name__ == "__main__":
    print(write_icns(sys.argv[1] if len(sys.argv) > 1 else "icon.icns"))
