"""Traces 荔枝腰子's art (新建文件夹/荔枝腰子.png) for D15, so that every piece of it is modelled 1:1 (勾勒): writes
food_models/traced_D15.json and the colours of its pieces food_models/traced_D15_paint.npz, which
stirfry.lizhi_yaozi builds the dish from, and a tracing sheet.

    python WhiteModel/trace_d15.py [--sheet <out.png>] [--labels <out.png>] [--at "x,y;x,y"] [--colours]

1. The art's camera: fitted so that the deep celadon dish lizhi_yaozi builds (lizhi_dish, kept) covers the art's
   best (IoU 0.978).
2. The pieces (trace_heap.cut): the five scored kidneys from strokes (KIDNEYS, read off the art by eye), the slices
   of bamboo shoot, the dark leaves and the pale stalks of the greens found automatically, each patch of their
   colour one seed, the sauce at the edge of the food likewise; flooded out over the art to the ink lines between
   them. Then each kidney cut into the raised squares of its scoring along the dark cuts between them (split) and
   grown back over the whole kidney (grow): the art's cross-hatch, every square a piece.
3. Their colours: the art's own, painted on through the vertex tint (art_colours); the slits through the bamboo,
   the glints painted on crisply.
4. The heap under them: the sauce over the whole food, dark red-brown where it shows in the cuts between the
   kidney's squares, the kidneys raised on it; each piece a rounded mound over its outline lying on it, every
   square of a kidney plump, so that from the art's camera it covers exactly what the art paints.
"""
import os
import sys

import cv2
import numpy as np

from trace_common import Camera, disk, grow, split, tracing_sheet, u8
from trace_heap import (heap_rgb, rim_guard, art_rgb, channels_from, cut, dish_view, food_zone, heap_height, kind_colours, label_sheet,
                        load_art, mound, patches, report_at, sauce_points, tone_channels, tone_map, write)

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '荔枝腰子.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D15.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D15_paint.npz')
CAM = Camera(35.44, 6572.8, 626.9, 795.2)                                    # (1)
DISH = "from food_models.stirfry import lizhi_dish\nlizhi_dish(p, 0.877)"

# (2) a stroke along each kidney (art pixels), by eye; what the art's colours don't part, by eye
KIDNEYS = [[(470, 320), (533, 345), (600, 360)], [(300, 560), (379, 576), (450, 600)],
           [(660, 480), (738, 499), (810, 520)], [(480, 790), (558, 794), (640, 800)],
           [(880, 730), (956, 743), (1030, 760)]]
FIX = []
JOIN = [('kidney', [(573, 299), (431, 393), (533, 345)])]   # the top kidney, over the dish's rim
CHANNELS = ['pale', 'deep', 'glint', 'slit', 'vein']
# (4) by kind: mesh spacing inside and along the outline (m), how high it rises (puff × its half-width, up to top),
# its relief, its colours
KINDS = {
    'square': dict(gap=0.009, gb=0.0034, puff=0.8, top=0.005, edge=0.0004, relief=0.0, mat='LizhiSquare', ring=0.0,
                   ink=[0.0, 0.0], paint=[('glint', 'LizhiGlint')], tint=[]),
    'bamboo': dict(gap=0.0095, gb=0.0045, puff=0.5, top=0.005, edge=0.0004, relief=0.0008, mat='LizhiBamboo',
                   ring=(0.0004, 0.0008), ink=[2.0, 2.0], paint=[('slit', 'LizhiBambooSlit')], tint=[]),
    'leaf': dict(gap=0.009, gb=0.004, puff=0.4, top=0.003, edge=0.0004, relief=0.0008, mat='LizhiLeaf',
                 ink=[1.0, 2.0], paint=[], tint=[]),
    'stalk': dict(gap=0.0055, gb=0.0034, puff=0.6, top=0.005, edge=0.0004, relief=0.0, mat='LizhiStalk',
                  ink=[1.0, 2.0], paint=[], tint=[]),
    'kidney': None, 'sauce': None,
}
HEAP = dict(gap=0.014, gb=0.007, top=0.014, reach=0.03, mat='LizhiSauce', tint=[])
KIDNEY_LIFT = 0.012   # the kidneys' balls stand this much higher than the heap round them
INK = [0.5, 2.5]
CREASE = (106, 41, 19)   # the dark cuts between a kidney's squares, where the heap under them shows


def seeds_of(h, s, v, zone):
    """Each patch of the bamboo's cream, the leaves' dark green, the stalks' pale green and the sauce's brown at the
    food's edge one seed: (mask, kind)."""
    out = []
    out += [(m, 'bamboo') for m in patches(zone & (h > 33) & (h < 58) & (s > 0.12) & (s < 0.62) & (v > 0.84), 6, 800)]
    out += [(m, 'leaf') for m in patches(zone & (h > 48) & (h < 120) & (s > 0.45) & (v < 0.56), 3, 150)]
    out += [(m, 'stalk') for m in patches(zone & (h > 55) & (h < 100) & (s > 0.28) & (s < 0.7) & (v > 0.56), 4, 300)]
    rim = zone & ~cv2.erode(u8(zone), disk(60)).astype(bool)
    out += [(m, 'sauce') for m in patches(rim & (h > 15) & (h < 38) & (s > 0.45) & (v > 0.45) & (v < 0.88), 4, 200)]
    return out


def squares(lab, kinds, lum, h, s, v):
    """Each kidney cut into the raised squares of its scoring: its lit flesh, without the dark cuts between, split
    along those and grown back over the whole kidney. Returns the squares' numbers per pixel (0 elsewhere)."""
    out = np.zeros(lab.shape, np.int32)
    for pid in range(1, lab.max() + 1):
        if kinds[pid - 1] != 'kidney':
            continue
        m = lab == pid
        flesh = m & (v > 0.5)
        flesh = cv2.morphologyEx(u8(flesh), cv2.MORPH_OPEN, disk(2)).astype(bool)
        sq = grow(split(flesh, lum, sig=2.0, tau=18.0, amin=500, amax=2600, marker_r=7), m, lum)
        out[sq > 0] = sq[sq > 0] + out.max()
    return out


def classes(rgb, h, s, v, lum, lab, kind_of):
    """The colour classes of CHANNELS over the art: glints on the kidneys, the slits through the bamboo, the leaves'
    lighter veins."""
    food = lab > 0
    edge = cv2.morphologyEx(u8(lab), cv2.MORPH_GRADIENT, disk(2)) > 0
    glint = ~edge & (s < 0.3) & (v > 0.9) & (kind_of == 'square')
    slit = (kind_of == 'bamboo') & ~edge & (v < 0.78) & (s > 0.35)
    slit = cv2.morphologyEx(u8(slit), cv2.MORPH_OPEN, disk(2)).astype(bool)
    vein = (kind_of == 'leaf') & (v > 0.5)
    a = np.zeros(lab.shape + (2,), np.uint8)
    b = channels_from([glint], food, 0.8, 20, 1)
    c = channels_from([slit], food, 1.0, 60, 1)
    d = channels_from([vein], food, 1.0, 30, 1)
    return np.concatenate([a, b, c, d], -1)


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    labels_out = sys.argv[sys.argv.index('--labels') + 1] if '--labels' in sys.argv else None
    rgba, rgb, h, s, v, lum = load_art(ART)
    H, W = h.shape
    zone = food_zone(h, s, v, rgba[..., 3], over_rim=(h < 40) & (s > 0.4) & (v > 0.45))
    lab, kinds = cut(rgb, s, v, zone, seeds_of(h, s, v, zone), [('kidney', k) for k in KIDNEYS] + FIX, JOIN)
    kidney = np.isin(lab, [i + 1 for i, k in enumerate(kinds) if k == 'kidney'])
    sq = squares(lab, kinds, lum, h, s, v)
    n_sq = sq.max()
    lab = np.where(sq > 0, sq + lab.max(), lab)   # the squares, numbered after the pieces
    kinds = kinds + ['square'] * n_sq
    print(f'[trace] {len(kinds)} pieces: ' + ', '.join(f'{k} {kinds.count(k)}' for k in sorted(set(kinds))), flush=True)
    if '--at' in sys.argv:
        report_at(lab, kinds, sys.argv[sys.argv.index('--at') + 1])
    if labels_out:
        tints = {'square': (220, 110, 60), 'bamboo': (250, 240, 200), 'leaf': (50, 90, 30), 'stalk': (160, 200, 100),
                 'sauce': (150, 70, 30), 'kidney': (120, 40, 20)}
        label_sheet(labels_out, rgb, lab, kinds, tints, (20, 230, 1240, 1090), scale=0.75)
        print(f'[trace] labels {labels_out}', flush=True)
    if '--colours' in sys.argv:
        for k, c in kind_colours(rgb, lum, lab, kinds).items():
            print(f'  {k}: {" ".join(c)}')
    if '--labels-only' in sys.argv:
        return
    kind_of = np.array(['none'] + kinds)[lab]
    paint = classes(rgb, h, s, v, lum, lab, kind_of)
    tone = tone_map(lum, lab, kinds)
    paint[..., 0:2] = tone_channels(tone, lab > 0)
    colours = art_rgb(rgb, lab, dark=0.47)
    heap_colours = heap_rgb(colours, kind_of, under=[(kidney, CREASE)])   # dark in the cuts between the squares
    floor, _, dish_V, _ = dish_view(CAM, DISH, H, W)
    hmap = heap_height(CAM, zone, HEAP['top'], HEAP['reach'], H, W)
    hmap = hmap + KIDNEY_LIFT * cv2.GaussianBlur(kidney.astype(np.float32), (0, 0), 25.0)
    hmap, raised = rim_guard(CAM, hmap, zone, floor, dish_V, margin=0.0)   # the top kidney, standing up over the back rim
    out, n_tris = [], {}
    mk = cv2.GaussianBlur(zone.astype(np.float32), (0, 0), 2.0) > 0.5
    sunk = np.maximum(hmap - 0.0006, 0.0009)   # a little under the pieces' feet, so that its coarse faces stay under them
    heap, _, _, _ = mound(CAM, 'heap', 'heap', dict(HEAP, puff=0.0, top=0.0), mk, floor, sunk, lum, paint, CHANNELS,
                          ring=0.0008, close=floor, ink=(0.0, 0.0), smooth_px=3.0, tone=tone, colours=heap_colours,
                          extra=sauce_points(kind_of == 'sauce', spacing=36.0), down=True)
    out.append(heap)
    n_tris['heap'] = len(heap['tris'])
    for pid in range(1, lab.max() + 1):
        kind = kinds[pid - 1]
        m = lab == pid
        if KINDS.get(kind) is None or m.sum() < 80:
            continue
        er = 1 if kind != 'square' else 2   # the squares part along the cut between them
        mk = cv2.GaussianBlur(cv2.erode(u8(m), disk(er)).astype(np.float32), (0, 0), 1.2) > 0.5
        if mk.sum() < 60:
            continue
        inner = None
        if kind == 'square':   # a point or a few inside it, for it to rise round
            e = cv2.erode(u8(mk), disk(6)).astype(bool)
            ys, xs = np.nonzero(e if e.any() else mk)
            g = (xs % 22 == 11) & (ys % 22 == 11)
            inner = np.stack([xs[g], ys[g]], -1).astype(float) if g.sum() else np.array([[xs.mean(), ys.mean()]])
        piece, uv, R, top = mound(CAM, f'{kind}{pid}', kind, KINDS[kind], mk, floor, hmap, lum, paint, CHANNELS,
                                  extra_px=10.0, ink=INK, smooth_px=1.5 if kind == 'square' else 2.0, tone=tone,
                                  colours=colours, extra=inner, raised=raised)
        out.append(piece)
        n_tris[kind] = n_tris.get(kind, 0) + len(piece['tris'])
    print(f'[trace] {len(out)} pieces, triangles by kind {n_tris}, all {sum(n_tris.values())}', flush=True)
    write(OUT, PAINT, CAM, CHANNELS, out, paint)
    print(f'[trace] wrote {OUT}', flush=True)
    if sheet:
        tints = {'square': (225, 120, 70), 'bamboo': (250, 240, 200), 'leaf': (60, 100, 40), 'stalk': (170, 205, 110),
                 'sauce': (150, 70, 30), 'kidney': (120, 40, 20)}
        shown = np.where(np.isin(kind_of, ['sauce', 'none', 'kidney']), 0, lab)
        tracing_sheet(sheet, rgba, shown, None, [tints[k] for k in kinds], crop=(20, 230, 1240, 1090),
                      title=('原图上的描线（蓝：每一块）', f'描出的 {len(out) - 1} 块：腰花的每一格、笋片、菜叶、菜梗'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
