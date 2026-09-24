"""水彩 (watercolor) finish for the 三渲二 preview of the 纹璃宫灯 white model.

Paints from the passes that `build_wenli_gongdeng.py --watercolor` renders into renders/passes,
using screen-space steps only, so the same recipe can become a full-screen effect in Unity:
washes that drift a little against the ink, uneven pigment, darker pigment pooled at each
wash's edge, paper grain, bare paper on the lit rounded edges, and ink lines of varying
weight (outlines plus the front-corner lines a hand-drawn illustration adds).

    python watercolor.py [tag]        tag: _500 (default, the chosen model), _low (3000 faces), '' (high)
Writes renders/watercolor{tag}.png, and watercolor_card{tag}.png laid out like the
reference item card 例子尝试.jpg (same paper, lantern size and position, green title).
"""
import os
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
TAG = sys.argv[1] if len(sys.argv) > 1 else '_500'
PASSES = os.path.join(HERE, 'renders', 'passes')
PAPER = (250, 253, 224)  # paper colour of 例子尝试.jpg
INK = (74, 46, 34)       # the toon outline colour
rng = np.random.default_rng(7)


def load(name, mode):
    return np.asarray(Image.open(os.path.join(PASSES, f'{name}{TAG}.png')).convert(mode), dtype=np.float32) / 255


def to_lin(c):
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


def to_srgb(c):
    c = np.clip(c, 0, 1)
    return np.where(c <= 0.0031308, c * 12.92, 1.055 * c ** (1 / 2.4) - 0.055)


def smoothstep(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


def box(a, r):
    """Box blur of radius r along both image axes, via cumulative sums."""
    k = 2 * r + 1
    rest = [(0, 0)] * (a.ndim - 2)
    a = np.pad(a, [(r + 1, r), (0, 0)] + rest, mode='edge').cumsum(0)
    a = (a[k:] - a[:-k]) / k
    a = np.pad(a, [(0, 0), (r + 1, r)] + rest, mode='edge').cumsum(1)
    return (a[:, k:] - a[:, :-k]) / k


def blur(a, sigma):
    """Three box passes, close to a Gaussian of the given sigma."""
    r = max(1, round((np.sqrt(4 * sigma * sigma + 1) - 1) / 2))
    for _ in range(3):
        a = box(a, r)
    return a


def noise(h, w, cell, octaves=3):
    """Fractal value noise in about [0, 1], with features about `cell` pixels across."""
    out, amp, norm = np.zeros((h, w), np.float32), 1.0, 0.0
    for o in range(octaves):
        c = max(1, cell >> o)
        g = rng.random((h // c + 3, w // c + 3)).astype(np.float32)
        out += amp * np.asarray(Image.fromarray(g).resize((g.shape[1] * c, g.shape[0] * c), Image.BICUBIC))[:h, :w]
        norm += amp
        amp *= 0.5
    return out / norm


def warp(a, dx, dy):
    """Sample `a` at (x + dx, y + dy) with bilinear filtering."""
    h, w = a.shape[:2]
    y, x = np.mgrid[0:h, 0:w].astype(np.float32)
    x = np.clip(x + dx, 0, w - 1.001)
    y = np.clip(y + dy, 0, h - 1.001)
    x0, y0 = x.astype(np.int32), y.astype(np.int32)
    fx, fy = x - x0, y - y0
    if a.ndim == 3:
        fx, fy = fx[..., None], fy[..., None]
    top = a[y0, x0] * (1 - fx) + a[y0, x0 + 1] * fx
    bottom = a[y0 + 1, x0] * (1 - fx) + a[y0 + 1, x0 + 1] * fx
    return top * (1 - fy) + bottom * fy


fill = load('wc_fill', 'RGBA')
H, W = fill.shape[:2]
alpha = fill[..., 3]
col = to_lin(fill[..., :3])
ids = load('wc_ids', 'RGB')
lit = load('wc_lit', 'L')
nrm = to_lin(load('wc_normal', 'RGB')) * 2 - 1
front = load('wc_lines', 'RGBA')[..., 3]
behind = np.clip(load('wc_lines_all', 'RGBA')[..., 3] - front - 0.1, 0, 1)  # the two passes differ by sampling noise
behind *= blur(ids[..., 2], 3) > 0.05                                         # so keep only what is behind the glass
paper = to_lin(np.float32(PAPER) / 255)
ink = to_lin(np.float32(INK) / 255)
inner = smoothstep(0.97, 1.0, blur(alpha, 2.0))  # away from the silhouette

# flat lit / shadow colour of the stone and wood, read back from the toon fill
flat = {}
for k in (0, 1):
    m = (alpha > 0.99) & (ids[..., k] > 0.99)
    flat[k] = (np.median(col[m & (lit > 0.99)], axis=0), np.median(col[m & (lit < 0.01)], axis=0))

# 1. the wash drifts a few pixels against the ink: gaps and overlaps like a hand-painted fill
dx, dy = ((noise(H, W, 90) - 0.5) * 6 for _ in range(2))
st = warp(np.dstack([col * alpha[..., None], alpha, ids, lit]), dx, dy)
a, ids_w, lit_w = smoothstep(0.15, 0.65, blur(st[..., 3], 1.2)), st[..., 4:7], st[..., 7]  # reaches under the ink
wash = st[..., :3] / np.maximum(st[..., 3:4], 1e-4)  # the glass keeps its see-through fill
lit_soft = blur(lit_w, 2.0)[..., None]                # a softer shadow edge than the toon ramp
for k, (c_lit, c_shade) in flat.items():
    m = ids_w[..., k:k + 1]
    c_shade = c_shade + 0.3 * (c_lit - c_shade)       # the drawing's shadows are a light glaze
    wash = wash * (1 - m) + m * (c_shade + (c_lit - c_shade) * lit_soft)

# 2. pigment density over the paper: uneven, pooled at each wash's edge, settling into the grain
dens = -np.log(np.clip(wash / paper, 0.03, 1))
shade = (1 - lit_w) * st[..., 3]
edge = sum(np.clip(ids_w[..., k] - blur(ids_w[..., k], 4), 0, 1) for k in range(3))
edge += np.clip(shade - blur(shade, 3), 0, 1)
g = sum((np.roll(nrm[..., c], -2, 1) - np.roll(nrm[..., c], 2, 1)) ** 2
        + (np.roll(nrm[..., c], -2, 0) - np.roll(nrm[..., c], 2, 0)) ** 2 for c in range(3))
spark = warp(smoothstep(0.35, 0.9, np.sqrt(g)) * smoothstep(0.5, 0.9, lit) * inner, dx, dy)  # lit rounded edges

# ink: outlines, plus a line where a left-facing surface turns into a right-facing one
nx = blur(nrm[..., 0], 1.0)
slope = (np.roll(nx, -1, 1) - np.roll(nx, 1, 1)) / 2
corner = (1 - smoothstep(1.5, 3.5, np.abs(nx) / np.maximum(slope, 1e-3))) * (slope > 0.008) * inner
near_ink = smoothstep(0.02, 0.2, blur(np.maximum(front, corner), 5))
edge *= 1 - near_ink    # where ink runs, it carries the edge
spark *= 1 - near_ink   # no bare-paper halo along the outlines

dens *= (1 + 0.3 * (noise(H, W, 110, 4) - 0.5))[..., None]
dens *= (1 + 1.6 * edge)[..., None]
dens *= (1 + 0.2 * (noise(H, W, 3, 2) - 0.5))[..., None]
dens *= (1 - 0.4 * blur(spark, 1.0))[..., None]
dens *= (1 - 0.3 * ids_w[..., 2])[..., None]  # the drawing's glass is a paler mint

grain = 1 + 0.05 * (noise(H, W, 4, 3) - 0.5) + 0.05 * (noise(H, W, 240, 3) - 0.5)
page = paper * grain[..., None]
out = page * (1 - a[..., None] + a[..., None] * np.exp(-dens))

# 3. brush the ink over the washes
lx, ly = ((noise(H, W, 70) - 0.5) * 4 for _ in range(2))
weight = 0.16 + 0.24 * (noise(H, W, 80) - 0.5) + 0.08 * (noise(H, W, 6) - 0.5)  # swelling strokes, rough edges
weight = np.maximum(weight, 0.12)  # keeps the stroke's soft edge off the bare paper


def stroke(m):
    """Wobbly brush line of varying weight from a line mask."""
    return smoothstep(weight - 0.11, weight + 0.11, blur(warp(m, lx, ly), 3.0))


lines = np.maximum(stroke(np.maximum(front, corner)), 0.45 * stroke(behind))[..., None]  # lighter behind the glass
tone = 0.85 + 0.3 * noise(H, W, 20)  # the ink is nearly opaque; only its tone varies along the stroke
out = out * (1 - lines) + ink * (tone * grain)[..., None] * lines

path = os.path.join(HERE, 'renders', f'watercolor{TAG}.png')
Image.fromarray((to_srgb(out) * 255 + 0.5).astype(np.uint8)).save(path)
print('saved', path)

# ---------------------------------------------------------------- item card like 例子尝试.jpg, at 2x its size
CARD_W, CARD_H = 1042, 1536
LANTERN_H, LANTERN_BOTTOM, CENTER_X = 814, 1122, 532  # the reference lantern: 407 px tall, bottom at y 561
TITLE, TITLE_FONT, TITLE_RGB, TITLE_Y = '纹璃宫灯', r'C:\Windows\Fonts\STXINWEI.TTF', (133, 156, 104), 1172


def resize(a, size):
    return np.dstack([np.asarray(Image.fromarray(np.ascontiguousarray(a[..., c], np.float32)).resize(size, Image.LANCZOS))
                      for c in range(a.shape[2])])


ys, xs = np.nonzero(alpha > 0.02)
x0, y0, x1, y1 = xs.min() - 16, ys.min() - 16, xs.max() + 17, ys.max() + 17
layer = (out / page)[y0:y1, x0:x1]  # what the painting does to the paper under it
s = LANTERN_H / (ys.max() - ys.min())
lw, lh = round(layer.shape[1] * s), round(layer.shape[0] * s)
layer = np.clip(resize(layer, (lw, lh)), 0, 1)

H, W = CARD_H, CARD_W
card = paper * (1 + 0.05 * (noise(H, W, 4, 3) - 0.5) + 0.05 * (noise(H, W, 240, 3) - 0.5))[..., None]
cx = CENTER_X - round(((xs.min() + xs.max()) / 2 - x0) * s)
cy = LANTERN_BOTTOM - round((ys.max() - y0) * s)
card[cy:cy + lh, cx:cx + lw] *= layer

# the title, painted as a green wash with pooled edges like the drawing's lettering
mask = Image.new('L', (W, H), 0)
d = ImageDraw.Draw(mask)
font = ImageFont.truetype(TITLE_FONT, 132)
d.text((W / 2 + 4, TITLE_Y - 8), TITLE, font=font, fill=255, anchor='mt', stroke_width=2, stroke_fill=255)
m = np.asarray(mask, dtype=np.float32) / 255
tx, ty = ((noise(H, W, 60) - 0.5) * 1.5 for _ in range(2))
m = blur(warp(m, tx, ty), 0.7)
tdens = -np.log(np.clip(to_lin(np.float32(TITLE_RGB) / 255) / paper, 0.03, 1))
t_edge = np.clip(m - blur(m, 3), 0, 1)
t = m * (1 + 0.35 * t_edge + 0.25 * (noise(H, W, 30) - 0.5))
card *= np.exp(-tdens * t[..., None])

path = os.path.join(HERE, f'watercolor_card{TAG}.png')
Image.fromarray((to_srgb(card) * 255 + 0.5).astype(np.uint8)).save(path)
print('saved', path)
