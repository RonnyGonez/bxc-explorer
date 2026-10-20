"""Draw the link-preview card ("Now that's what I call BXC", with the live song count)."""
import os
import random

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.join(os.path.dirname(__file__), "..")
FONTS = os.path.join(ROOT, "assets", "fonts")
BG, INK, MUTED, HOT, DOT = "#F1F0F6", "#17142A", "#625E7C", "#D81F57", "#B9B5CC"


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def centred(d, y, text, f, fill, spacing=0):
    if spacing:   # letter-spaced line
        widths = [d.textlength(c, font=f) for c in text]
        x = (1200 - (sum(widths) + spacing * (len(text) - 1))) / 2
        for c, w in zip(text, widths):
            d.text((x, y), c, font=f, fill=fill)
            x += w + spacing
        return
    w = d.textlength(text, font=f)
    d.text(((1200 - w) / 2, y), text, font=f, fill=fill)


def draw(count, out):
    im = Image.new("RGB", (1200, 630), BG)
    d = ImageDraw.Draw(im)
    rnd = random.Random(7)
    for i in range(70):   # faint "mood map" dots in the margins
        x = 1145 + rnd.random() * 45 if i % 2 else 12 + rnd.random() * 45
        y, r = 40 + rnd.random() * 540, 4 + rnd.random() * 4
        d.ellipse((x - r, y - r, x + r, y + r), fill=HOT if rnd.random() < .22 else DOT)
    centred(d, 62, "NOW THAT'S WHAT I CALL", font("JetBrainsMono-Medium.ttf", 30), MUTED, spacing=7)
    title = font("DelaGothicOne.ttf", 62)
    parts = [("Bangers Xchange ", INK), ("Club", HOT), (" Music", INK)]
    x = (1200 - sum(d.textlength(t, font=title) for t, _ in parts)) / 2
    for t, c in parts:
        d.text((x, 118), t, font=title, fill=c)
        x += d.textlength(t, font=title)
    num = str(count)
    size = 250 if len(num) <= 3 else 205
    centred(d, 182, num, font("DelaGothicOne.ttf", size), HOT)
    centred(d, 535, "SONGS · PICK A MOOD · PRESS PLAY", font("JetBrainsMono-Medium.ttf", 26), INK, spacing=5)
    d.rectangle((0, 616, 1200, 630), fill=INK)
    im.save(out, quality=88, optimize=True, progressive=True)


if __name__ == "__main__":
    import sys
    draw(int(sys.argv[1]), sys.argv[2])
