"""Generate the Expenzo application icon (assets/expenzo.ico).

Draws a rounded-square blue gradient tile with a white "E" (matching the
sidebar brand mark) and writes a multi-size Windows .ico:
16, 32, 48, 64, 128, 256 px.

Run:  python packaging/make_icon.py
Requires: Pillow (present in the project venv).
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

BASE_DIR = Path(__file__).resolve().parent.parent
ASSETS_DIR = BASE_DIR / "assets"
ICON_PATH = ASSETS_DIR / "expenzo.ico"

# Brand colors (match config.py tokens)
COLOR_TOP = (59, 130, 246)      # COLOR_PRIMARY #3B82F6
COLOR_BOTTOM = (29, 78, 216)    # COLOR_PRIMARY_LIGHT #1D4ED8
COLOR_TEXT = (255, 255, 255)

ICON_SIZES = [16, 32, 48, 64, 128, 256]


def _gradient(size: int) -> Image.Image:
    """Vertical blue gradient image at the given size."""
    image = Image.new("RGB", (size, size))
    for y in range(size):
        t = y / max(size - 1, 1)
        color = tuple(
            round(COLOR_TOP[i] + (COLOR_BOTTOM[i] - COLOR_TOP[i]) * t)
            for i in range(3)
        )
        for x in range(size):
            image.putpixel((x, y), color)
    return image


def _rounded_mask(size: int, radius_ratio: float = 0.22) -> Image.Image:
    """L-shaped alpha mask rounding the tile corners (Windows-style tile)."""
    mask = Image.new("L", (size, size), 0)
    draw = ImageDraw.Draw(mask)
    radius = int(size * radius_ratio)
    draw.rounded_rectangle((0, 0, size - 1, size - 1), radius=radius, fill=255)
    return mask


def _letter_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Bold font sized so the "E" fills ~55% of the tile."""
    for name in ("segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"):
        try:
            return ImageFont.truetype(name, int(size * 0.62))
        except OSError:
            continue
    return ImageFont.load_default()


def _render_tile(size: int) -> Image.Image:
    tile = _gradient(size)
    tile.putalpha(_rounded_mask(size))
    draw = ImageDraw.Draw(tile)
    try:
        font = _letter_font(size)
    except Exception:
        font = ImageFont.load_default()
    text = "E"
    bbox = draw.textbbox((0, 0), text, font=font)
    text_w = bbox[2] - bbox[0]
    text_h = bbox[3] - bbox[1]
    # Vertical optical centering: shift up slightly for the glyph.
    x = (size - text_w) / 2 - bbox[0]
    y = (size - text_h) / 2 - bbox[1] - int(size * 0.03)
    draw.text((x, y), text, font=font, fill=COLOR_TEXT)
    return tile


def main() -> None:
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    tiles = [_render_tile(size) for size in ICON_SIZES]
    tiles[-1].save(  # save from the largest frame to embed all sizes
        ICON_PATH,
        format="ICO",
        sizes=[(size, size) for size in ICON_SIZES],
        append_images=tiles[:-1],
    )
    print(f"Wrote {ICON_PATH} ({len(ICON_SIZES)} sizes)")


if __name__ == "__main__":
    main()
