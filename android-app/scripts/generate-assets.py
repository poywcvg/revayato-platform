#!/usr/bin/env python3
"""
روایتو — local asset generator (banner + icon) using Pillow + bundled Vazirmatn.

Produces:
  android/app/src/main/res/drawable/tv_banner.png   (320x180, TV launcher banner)
  android/app/src/main/res/drawable/tv_banner_480.png (480x270, sharper TV banner)

Font: src/assets/fonts/Vazirmatn-Bold.ttf (OFL-1.1). Run: python generate-assets.py
"""

import os

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONT_PATH = os.path.join(ROOT, "src", "assets", "fonts", "Vazirmatn-Bold.ttf")
OUT_DIR = os.path.join(ROOT, "android", "app", "src", "main", "res", "drawable")

BG = "#1d1c21"
ACCENT = "#408a71"
BRIGHT = "#b0e4cc"
TEXT = "#f4f1ea"


def draw_banner(width: int, height: int) -> Image.Image:
    img = Image.new("RGB", (width, height), BG)
    draw = ImageDraw.Draw(img)

    # Centered wordmark. The play triangle sits on the start (right in RTL) of the text.
    font_size = max(28, int(height * 0.5))
    font = ImageFont.truetype(FONT_PATH, font_size)

    text = "روایتو"
    # bbox in pixels; Pillow anchors coordinates from top-left. Keep it centered.
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]

    # Place a small brand-accent play badge before the wordmark (mirror of the web logo).
    badge_d = int(height * 0.22)
    badge_x = (width - tw) // 2 - badge_d - int(width * 0.02)
    badge_y = (height - th) // 2 - bbox[1]
    draw.rounded_rectangle(
        (badge_x, badge_y, badge_x + badge_d, badge_y + badge_d),
        radius=badge_d // 3,
        fill=ACCENT,
    )
    tri = badge_d * 0.34
    draw.polygon(
        [
            (badge_x + badge_d * 0.42, badge_y + badge_d * 0.22),
            (badge_x + badge_d * 0.42, badge_y + badge_d * 0.78),
            (badge_x + badge_d * 0.72, badge_y + badge_d * 0.5),
        ],
        fill=BG,
    )

    draw.text((badge_d + int(width * 0.05), (height - th) // 2 - bbox[1]), text, font=font, fill=TEXT)

    # subtle accent underline
    draw.rectangle(
        [(width * 0.5 - tw * 0.28, height - int(height * 0.12)),
         (width * 0.5 + tw * 0.28, height - int(height * 0.115))],
        fill=BRIGHT,
    )
    return img


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    for size, name in ((320, 180), (480, 270)):
        out = os.path.join(OUT_DIR, f"tv_banner{'_480' if size == 480 else ''}.png")
        draw_banner(size, size * 9 // 16).save(out)
        print(f"wrote {out} ({size}x{size * 9 // 16})")


if __name__ == "__main__":
    main()