import os
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

SIZE = (1080, 1080)

FONT_PATHS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-B.ttf",
]

FONT_PATHS_REGULAR = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
    "/usr/share/fonts/truetype/ubuntu/Ubuntu-R.ttf",
]


def _get_font(size: int, bold: bool = True) -> ImageFont.FreeTypeFont:
    paths = FONT_PATHS if bold else FONT_PATHS_REGULAR
    for path in paths:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                continue
    return ImageFont.load_default()


def _hex_to_rgb(hex_color: str) -> tuple:
    h = hex_color.lstrip("#")
    if len(h) == 3:
        h = "".join(c * 2 for c in h)
    return tuple(int(h[i : i + 2], 16) for i in (0, 2, 4))


def _draw_centered(
    draw: ImageDraw.Draw,
    text: str,
    y: int,
    font: ImageFont.FreeTypeFont,
    color: tuple,
    shadow: bool = True,
):
    bbox = draw.textbbox((0, 0), text, font=font)
    w = bbox[2] - bbox[0]
    x = (SIZE[0] - w) // 2
    if shadow:
        draw.text((x + 2, y + 2), text, font=font, fill=(0, 0, 0, 100))
    draw.text((x, y), text, font=font, fill=color)


def _paste_product(base: Image.Image, product: Image.Image, scale: float, cx: int, cy: int) -> Image.Image:
    prod = product.convert("RGBA")
    max_dim = int(SIZE[0] * scale)
    prod.thumbnail((max_dim, max_dim), Image.LANCZOS)
    x = cx - prod.width // 2
    y = cy - prod.height // 2
    result = base.convert("RGBA")
    result.paste(prod, (x, y), prod)
    return result


# ---------------------------------------------------------------------------
# Slide 1 — Hero: product on AI background + brand bar at bottom
# ---------------------------------------------------------------------------
def _slide_hero(background: Image.Image, product: Image.Image, metadata: dict) -> Image.Image:
    img = background.copy().resize(SIZE, Image.LANCZOS).convert("RGBA")

    # Composite product centered, slightly above midpoint
    img = _paste_product(img, product, scale=0.62, cx=SIZE[0] // 2, cy=SIZE[1] // 2 - 30)

    # Dark gradient bar at bottom
    gradient = Image.new("RGBA", SIZE, (0, 0, 0, 0))
    gd = ImageDraw.Draw(gradient)
    bar_height = 230
    for i in range(bar_height):
        alpha = int((i / bar_height) ** 1.5 * 210)
        gd.rectangle(
            [(0, SIZE[1] - bar_height + i), (SIZE[0], SIZE[1] - bar_height + i + 1)],
            fill=(0, 0, 0, alpha),
        )
    img = Image.alpha_composite(img, gradient)

    draw = ImageDraw.Draw(img)
    accent = _hex_to_rgb(metadata.get("accent_color", "#c9a96e")) + (255,)
    white = (255, 255, 255, 255)

    _draw_centered(draw, metadata["brand_name"].upper(), SIZE[1] - 185, _get_font(56), white)
    _draw_centered(draw, metadata["product_name"], SIZE[1] - 115, _get_font(34, bold=False), accent)

    if metadata.get("tagline"):
        _draw_centered(draw, metadata["tagline"], SIZE[1] - 68, _get_font(24, bold=False), (210, 210, 210, 255))

    return img.convert("RGB")


# ---------------------------------------------------------------------------
# Slide 2 — Feature: solid bg, product left, text right
# ---------------------------------------------------------------------------
def _slide_feature(product: Image.Image, metadata: dict) -> Image.Image:
    primary = _hex_to_rgb(metadata.get("primary_color", "#1a1a1a"))
    accent = _hex_to_rgb(metadata.get("accent_color", "#c9a96e"))

    img = Image.new("RGB", SIZE, primary)
    draw = ImageDraw.Draw(img)

    # Subtle diagonal lines for texture
    for i in range(-SIZE[1], SIZE[0], 22):
        draw.line([(i, 0), (i + SIZE[1], SIZE[1])], fill=tuple(min(255, c + 12) for c in primary), width=1)

    # Accent left bar
    draw.rectangle([(0, 0), (7, SIZE[1])], fill=accent)

    # Product on left half
    prod = product.convert("RGBA")
    prod.thumbnail((490, 490), Image.LANCZOS)
    px = 70 + (460 - prod.width) // 2
    py = (SIZE[1] - prod.height) // 2
    img_rgba = img.convert("RGBA")
    img_rgba.paste(prod, (px, py), prod)
    img = img_rgba.convert("RGB")
    draw = ImageDraw.Draw(img)

    # Divider line
    draw.rectangle([(580, 160), (582, SIZE[1] - 160)], fill=tuple(min(255, c + 40) for c in primary))

    # Text block on right
    tx = 610
    white = (255, 255, 255)
    gray = (180, 180, 180)

    draw.text((tx, 260), metadata["brand_name"].upper(), font=_get_font(26), fill=accent)

    # Word-wrap product name at max width 420px
    words = metadata["product_name"].split()
    lines, line = [], ""
    name_font = _get_font(58)
    for word in words:
        test = f"{line} {word}".strip()
        bbox = draw.textbbox((0, 0), test, font=name_font)
        if bbox[2] - bbox[0] > 420 and line:
            lines.append(line)
            line = word
        else:
            line = test
    lines.append(line)

    y_text = 320
    for ln in lines:
        draw.text((tx, y_text), ln, font=name_font, fill=white)
        y_text += 68

    if metadata.get("tagline"):
        draw.text((tx, y_text + 24), metadata["tagline"], font=_get_font(27, bold=False), fill=gray)

    return img


# ---------------------------------------------------------------------------
# Slide 3 — CTA: radial glow, small product, brand + CTA button
# ---------------------------------------------------------------------------
def _slide_cta(product: Image.Image, metadata: dict) -> Image.Image:
    primary = _hex_to_rgb(metadata.get("primary_color", "#1a1a1a"))
    accent = _hex_to_rgb(metadata.get("accent_color", "#c9a96e"))

    img = Image.new("RGB", SIZE, primary)
    draw = ImageDraw.Draw(img)

    # Radial glow behind product area
    cx, cy = SIZE[0] // 2, 380
    for r in range(320, 0, -1):
        ratio = r / 320
        c = tuple(int(primary[i] + (accent[i] - primary[i]) * (1 - ratio) * 0.55) for i in range(3))
        draw.ellipse([(cx - r, cy - r), (cx + r, cy + r)], fill=c)

    # Product small, top-center
    img = _paste_product(img.convert("RGBA"), product, scale=0.38, cx=SIZE[0] // 2, cy=290)
    img = img.convert("RGB")
    draw = ImageDraw.Draw(img)

    white = (255, 255, 255)
    gray = (200, 200, 200)

    # Brand name
    _draw_centered(draw, metadata["brand_name"].upper(), 560, _get_font(76), white, shadow=True)

    if metadata.get("tagline"):
        _draw_centered(draw, metadata["tagline"], 660, _get_font(30, bold=False), gray, shadow=False)

    # CTA button
    cta_font = _get_font(38)
    btn_text = "Shop Now"
    bbox = draw.textbbox((0, 0), btn_text, font=cta_font)
    bw = bbox[2] - bbox[0] + 90
    bh = bbox[3] - bbox[1] + 36
    bx = (SIZE[0] - bw) // 2
    by = 760
    draw.rounded_rectangle([(bx, by), (bx + bw, by + bh)], radius=10, fill=accent)
    btx = bx + (bw - (bbox[2] - bbox[0])) // 2
    bty = by + (bh - (bbox[3] - bbox[1])) // 2
    draw.text((btx, bty), btn_text, font=cta_font, fill=primary)

    return img


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------
def compose_slides(product_png: str, background_png: str, output_dir: str, metadata: dict) -> None:
    product = Image.open(product_png).convert("RGBA")
    background = Image.open(background_png).convert("RGBA")

    slides = [
        ("slide_01_hero.png", _slide_hero(background, product, metadata)),
        ("slide_02_feature.png", _slide_feature(product, metadata)),
        ("slide_03_cta.png", _slide_cta(product, metadata)),
    ]

    out = Path(output_dir)
    for filename, slide in slides:
        slide.save(str(out / filename), "PNG", optimize=True)
