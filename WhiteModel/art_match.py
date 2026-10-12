"""Compares a food model with its art, for matching shape and layout 1:1. Takes the renders art_views.py made
of one item, fits each onto the art's silhouette (same scale both ways, then moved), scores the overlap as IoU
(shared area / combined area) and writes a sheet for the best view: the art | the art with the model's outline and
the boundaries between its parts (wherever its colour changes) in red | the two blended half and half.

    python art_match.py <art.png> <renders_dir> <id> <out.png> [grid_z]

Prints the best few views with their IoU. Shape is right when the IoU is about 0.9 or more and the red lines follow
the art's edges. A fourth panel shows the art under a grid of the model's own coordinates on the level z = grid_z
(default 0.008, a plate's floor): lines every 1 cm, labelled every 5 cm, x across and y into the picture, so where
anything sits in the art can be read off in metres and given to the model.
"""
import glob
import os
import re
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

art_path, renders, key, out = sys.argv[1:5]
GRID_Z = float(sys.argv[5]) if len(sys.argv) > 5 else 0.008
N = 320   # matching canvas, long side


def load_mask(path, size=None):
    im = Image.open(path).convert('RGBA')
    if size:
        im = im.resize(size, Image.LANCZOS)
    return im, np.asarray(im)[..., 3] > 128


art_im = Image.open(art_path).convert('RGBA')
k = N / max(art_im.size)
canvas = (round(art_im.width * k), round(art_im.height * k))
art_small, A = load_mask(art_path, canvas)
ay, ax = np.nonzero(A)
a_area, a_cx, a_cy = A.sum(), ax.mean(), ay.mean()


def placed(mask_im, s, cx, cy):
    """The model's mask scaled by s about its own centroid, centred at (cx, cy) on the art canvas."""
    w, h = mask_im.size
    im = mask_im.resize((max(1, round(w * s)), max(1, round(h * s))), Image.BILINEAR)
    m = np.asarray(im) > 128
    my, mx = np.nonzero(m)
    out = np.zeros(A.shape, bool)
    ox, oy = round(cx - mx.mean()), round(cy - my.mean())
    ys, xs = my + oy, mx + ox
    ok = (ys >= 0) & (ys < A.shape[0]) & (xs >= 0) & (xs < A.shape[1])
    out[ys[ok], xs[ok]] = True
    return out, (s, ox, oy)


def fit(path):
    im = Image.open(path).convert('RGBA')
    alpha = im.split()[3]
    bbox = alpha.getbbox()
    alpha, im = alpha.crop(bbox), im.crop(bbox)
    fit.bbox[path] = bbox
    s0 = (a_area / max((np.asarray(alpha) > 128).sum(), 1)) ** 0.5
    best = (-1, None)
    s_c, cx_c, cy_c = s0, a_cx, a_cy
    for step in (0.06, 0.02, 0.007):   # coarse to fine search over scale and position
        for ds in (-2, -1, 0, 1, 2):
            for dx in (-2, -1, 0, 1, 2):
                for dy in (-2, -1, 0, 1, 2):
                    s, cx, cy = s_c * (1 + ds * step), cx_c + dx * step * 40, cy_c + dy * step * 40
                    m, tf = placed(alpha, s, cx, cy)
                    iou = (m & A).sum() / max((m | A).sum(), 1)
                    if iou > best[0]:
                        best = (iou, (s, cx, cy, tf, m))
        s_c, cx_c, cy_c = best[1][:3]
    return best[0], best[1], im


fit.bbox = {}
results = []
for path in glob.glob(os.path.join(renders, f'{key}_a*_e*.png')):
    m = re.search(r'_a(-?[\d.]+)_e(-?[\d.]+)\.png$', path)
    iou, fitted, im = fit(path)
    results.append((iou, float(m.group(1)), float(m.group(2)), fitted, im, path))
results.sort(key=lambda r: -r[0])
for iou, az, el, *_ in results[:5]:
    print(f'[match] {key}: az {az:g} el {el:g}  IoU {iou:.3f}')
iou, az, el, (s, cx, cy, (sc, ox, oy), mask), im, best_path = results[0]

# the sheet, at 2.5x the matching canvas
Z = 2.5
big = (round(canvas[0] * Z), round(canvas[1] * Z))
art_big = Image.new('RGBA', big, (245, 240, 230, 255))
art_big.alpha_composite(art_im.resize(big, Image.LANCZOS))
model_big = Image.new('RGBA', big, (0, 0, 0, 0))   # the render placed as fitted, at the sheet's scale
scaled = im.resize((max(1, round(im.width * sc * Z)), max(1, round(im.height * sc * Z))), Image.LANCZOS)
px, py = round(ox * Z), round(oy * Z)
model_big.alpha_composite(scaled, (max(px, 0), max(py, 0)), (max(-px, 0), max(-py, 0)))
m = np.asarray(model_big).astype(int)
inside = m[..., 3] > 128
lines = np.zeros(inside.shape, bool)
for dy, dx in ((0, 1), (1, 0), (1, 1)):   # the outline, and every change of colour inside it
    a, b = m[:m.shape[0] - dy, :m.shape[1] - dx], m[dy:, dx:]
    d = (np.abs(a[..., :3] - b[..., :3]).sum(-1) > 70) & (a[..., 3] > 128) & (b[..., 3] > 128)
    d |= (a[..., 3] > 128) != (b[..., 3] > 128)
    lines[:d.shape[0], :d.shape[1]] |= d
edge = Image.fromarray((lines * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(3))
outlined = art_big.copy()
outlined.paste((220, 30, 30, 255), (0, 0), edge)
blend = Image.blend(art_big, Image.alpha_composite(Image.new('RGBA', big, (245, 240, 230, 255)), model_big), 0.5)
# the art under a grid of model coordinates on the level z = GRID_Z
import json   # noqa: E402
cam = json.load(open(best_path[:-4] + '.json'))
bx0, by0 = fit.bbox[best_path][:2]


def to_sheet(x, y, z):
    p = [x - cam['centre'][0], y - cam['centre'][1], z - cam['centre'][2]]
    u = sum(a * b for a, b in zip(p, cam['right'])) / cam['ortho_scale'] * cam['resolution'] + cam['resolution'] / 2
    v = cam['resolution'] / 2 - sum(a * b for a, b in zip(p, cam['up'])) / cam['ortho_scale'] * cam['resolution']
    return ((u - bx0) * sc + ox) * Z, ((v - by0) * sc + oy) * Z


gridded = art_big.copy()
g = ImageDraw.Draw(gridded)
small = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 15)
R = range(-30, 31)   # cm
for i in R:
    for pts in ([to_sheet(i / 100, j / 100, GRID_Z) for j in (R[0], R[-1])], [to_sheet(j / 100, i / 100, GRID_Z) for j in (R[0], R[-1])]):
        g.line(pts, fill=(40, 90, 200, 255) if i % 5 == 0 else (120, 150, 220, 110), width=2 if i % 5 == 0 else 1)
for i in range(-30, 31, 5):
    for j in range(-30, 31, 5):
        x, y = to_sheet(i / 100, j / 100, GRID_Z)
        if 0 < x < big[0] - 40 and 0 < y < big[1] - 20:
            g.text((x + 2, y + 1), f'{i},{j}', fill=(20, 50, 160, 255), font=small)
sheet = Image.new('RGB', (big[0] * 4 + 60, big[1] + 50), (255, 255, 255))
for i, panel in enumerate((art_big, outlined, blend, gridded)):
    sheet.paste(panel.convert('RGB'), (i * (big[0] + 20), 50))
font = ImageFont.truetype('C:/Windows/Fonts/msyh.ttc', 24)
ImageDraw.Draw(sheet).text((10, 10), f'{key}   best view az {az:g}° el {el:g}°   IoU {iou:.3f}   '
                           f'(art | red = the model: outline and parts | half and half | grid in cm at z = {GRID_Z:g} m: x, y)', fill=(40, 30, 25), font=font)
sheet.save(out)
print(f'[match] wrote {out}')
