"""Builds the style comparison sheet for the kitchen screen vs. the hall.

A = 全三渲二: hall toon render + the 3D cooking view (build_cook_view.py).
B = 向手绘靠拢: hall toon render through paint_filter.py + the painted kitchen (背景.png, 案台 (2).png)
    with the food renders, also painted, placed where the game places them.
Writes StyleTest/A_cook.png, B_cook.png, B_hall.png and compare.png.
"""
import os

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

from paint_filter import paint

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(HERE, 'StyleTest')
ICONS = os.path.join(ROOT, 'Unity', 'Assets', 'Resources', 'Food3D')
os.makedirs(OUT, exist_ok=True)
PAPER = (244, 236, 217)


def painted_icon(key, size):
    ic = Image.open(os.path.join(ICONS, key + '.png')).convert('RGBA')
    ic.thumbnail(size, Image.LANCZOS)
    rgb = paint(ic, bg=(240, 220, 185), strength=0.55)
    alpha = ic.split()[3].filter(ImageFilter.GaussianBlur(0.6))
    rgb.putalpha(alpha)
    return rgb


def place(canvas, icon, rect, anchor_bottom=True):
    """rect = (x0, y0, x1, y1) as fractions, y from the bottom (as in CookingScreen.cs)."""
    W, H = canvas.size
    x0, y0, x1, y1 = rect
    bw, bh = int((x1 - x0) * W), int((y1 - y0) * H)
    ic = icon.copy()
    ic.thumbnail((bw, bh), Image.LANCZOS)
    px = int(x0 * W + (bw - ic.width) / 2)
    py = int((1 - y0) * H - ic.height) if anchor_bottom else int((1 - y1) * H + (bh - ic.height) / 2)
    canvas.alpha_composite(ic, (px, py))


# ---- B: painted kitchen with painted food
bg = Image.open(os.path.join(ROOT, '背景.png')).convert('RGBA')
counter = Image.open(os.path.join(ROOT, '案台 (2).png')).convert('RGBA')
cook = bg.copy()
cook.alpha_composite(counter)
place(cook, painted_icon('D02', (300, 300)), (0.064, 0.345, 0.16, 0.48))
bx0, by0, bx1, by1 = 0.388, 0.30, 0.652, 0.53
for i, k in enumerate(('flour', 'greens', 'pork')):
    w = (bx1 - bx0) / 3
    place(cook, painted_icon(k, (300, 300)), (bx0 + i * w, by0 + 0.1, bx0 + (i + 1) * w, by1 + 0.02))
for i, k in enumerate(('salt', 'oil', 'scallion', 'ginger')):
    w = (bx1 - bx0) / 4
    place(cook, painted_icon(k, (300, 300)), (bx0 + i * w, by0 + 0.0, bx0 + (i + 1) * w, by0 + 0.12))
place(cook, painted_icon('D01_wok', (300, 300)), (0.755, 0.44, 0.86, 0.55))
cook.convert('RGB').save(os.path.join(OUT, 'B_cook.png'))

# ---- B hall and A pieces
hall_toon = Image.open(os.path.join(HERE, 'Level1', 'renders', 'toon.png')).convert('RGBA')
flat = Image.new('RGBA', hall_toon.size, PAPER + (255,))
flat.alpha_composite(hall_toon)
paint(hall_toon, bg=PAPER).save(os.path.join(OUT, 'B_hall.png'))
Image.open(os.path.join(HERE, 'CookView', 'cook_view_toon.png')).convert('RGB').save(os.path.join(OUT, 'A_cook.png'))


def fit(im, w, h):
    im = im.convert('RGB')
    r = max(w / im.width, h / im.height)
    im = im.resize((int(im.width * r + 0.5), int(im.height * r + 0.5)), Image.LANCZOS)
    x, y = (im.width - w) // 2, (im.height - h) // 2
    return im.crop((x, y, x + w, y + h))


def crop_hall(im):   # the part of the overview the player mostly sees, 16:9
    w, h = im.size
    cw = w * 0.84
    ch = min(cw * 9 / 16, h * 0.96)
    cw = ch * 16 / 9
    x0, y0 = (w - cw) / 2, (h - ch) / 2
    return im.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch)))


CW, CH, PAD, TOP = 960, 540, 24, 70
sheet = Image.new('RGB', (PAD * 3 + CW * 2, TOP * 2 + PAD * 3 + CH * 2), (250, 246, 236))
d = ImageDraw.Draw(sheet)
font = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', 34)
small = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 24)
rows = [
    ('方案一  全部三渲二（做饭界面也做成 3D 白模）', fit(crop_hall(flat), CW, CH), fit(Image.open(os.path.join(OUT, 'A_cook.png')), CW, CH)),
    ('方案二  前堂加水彩后处理，做饭界面用手绘背景', fit(crop_hall(Image.open(os.path.join(OUT, 'B_hall.png'))), CW, CH),
     fit(Image.open(os.path.join(OUT, 'B_cook.png')), CW, CH)),
]
y = PAD
for title, a, b in rows:
    d.text((PAD, y), title, fill=(74, 51, 34), font=font)
    y += TOP - 10
    sheet.paste(a, (PAD, y))
    sheet.paste(b, (PAD * 2 + CW, y))
    d.text((PAD + 12, y + CH - 40), '前堂', fill=(74, 51, 34), font=small)
    d.text((PAD * 2 + CW + 12, y + CH - 40), '做饭界面', fill=(255, 255, 255), font=small)
    y += CH + PAD
sheet.save(os.path.join(OUT, 'compare.png'))
print('wrote', os.path.join(OUT, 'compare.png'))
