"""One-off generator for gui/assets/icon.ico. Not imported at runtime by the
app; re-run manually (`python gui/assets/make_icon.py`) if you want to tweak
the icon, then rebuild the exe.
"""
import os

from PIL import Image, ImageDraw, ImageFont

CARD = (27, 29, 34, 255)
ACCENT = (139, 30, 40, 255)
VIVID = (251, 16, 28, 255)

SIZE = 256
HERE = os.path.dirname(os.path.abspath(__file__))


def build():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))

    mask = Image.new("L", (SIZE, SIZE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIZE - 1, SIZE - 1), radius=56, fill=255)

    base = Image.new("RGBA", (SIZE, SIZE), ACCENT)
    # Diagonal shading toward the card color, echoing the app's card gradient.
    shade = Image.new("L", (SIZE, SIZE), 0)
    shade_draw = ImageDraw.Draw(shade)
    for y in range(SIZE):
        v = int(90 * (y / SIZE))
        shade_draw.line((0, y, SIZE, y), fill=v)
    card_layer = Image.new("RGBA", (SIZE, SIZE), CARD)
    base = Image.composite(card_layer, base, shade)

    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((SIZE * 0.55, -SIZE * 0.35, SIZE * 1.35, SIZE * 0.45), fill=(*VIVID[:3], 90))
    glow = glow.filter(__import__("PIL.ImageFilter", fromlist=["GaussianBlur"]).GaussianBlur(28))
    base = Image.alpha_composite(base, glow)

    img = Image.composite(base, img, mask)

    draw = ImageDraw.Draw(img)
    font = ImageFont.truetype(r"C:\Windows\Fonts\segoeuib.ttf", 148)
    text = "Z"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    draw.text(((SIZE - tw) / 2 - bbox[0], (SIZE - th) / 2 - bbox[1] - 6), text, font=font, fill=(242, 243, 245, 255))

    out = os.path.join(HERE, "icon.ico")
    img.save(out, format="ICO", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote", out)


if __name__ == "__main__":
    build()
