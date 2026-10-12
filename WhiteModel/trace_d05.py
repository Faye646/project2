"""Traces 水晶脍's art (新建文件夹/水晶脍.png) for D05, so that its five cubes of aspic are modelled 1:1 (勾勒): writes
food_models/traced_D05.json and the colours of the pieces food_models/traced_D05_paint.npz, which plates.shuijing_kuai
builds the dish from, and a tracing sheet.

    python WhiteModel/trace_d05.py [--sheet <out.png>]

1. The art's camera: fitted, 35° up as the icons are seen, so that the scalloped celadon dish shuijing_kuai
   builds covers the art's plate best.
2. The pieces: a flood of the art seeded by strokes inside each cube (PIECES, read off the art by eye) and on the
   plate round them (PLATE), the art's ink lines made walls; the scallion and ginger on their tops found by colour.
3. Each cube fitted with a box with well rounded edges (its middle, size and turn), standing on the plate's floor, so
   that the box seen from the art's camera covers the cube's outline where the art shows it (and not the plate); the
   cube's surface is then the art's outline of it laid onto that box along the lines of sight, so that it covers
   exactly what the art paints and is flat on top with upright sides, closed underneath down to the plate.
4. Their colours: the amber aspic, paler on top, the curls of pork skin in it pale where the art paints them (painted
   on: the mesh has vertices along their edges), the bright light along the cubes' edges; the scallion and the
   ginger shreds on top traced as small pieces lying on the cubes, each with the art's ink line round it.
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

from trace_common import (Camera, Grid, contour_points, dish_mesh, disk, fill_holes, largest, lying, neighbours, oriented,
                          outline_mesh, over, paint_channels, profile, raster, seeded_pieces, smooth_inner,
                          tracing_sheet, u8)
from trace_kit_plates import (behind, closed_under, fit_box, onto_solid, own_edges, raster_piece,
                               rounded_box_sdf)

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '水晶脍.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D05.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D05_paint.npz')
CAM = Camera(35.0, 5902.4, 633.8, 808.5)            # (1)
FZ = 0.012
DISH = "oval_dish(p, 0.105, 1.0, 0.0, 0.032, 0.72, floor=0.012, n=54, lobes=18, amount=0.012, rings=3)"

# (2) the cubes, back to front: name, strokes inside it (art pixels)
PIECES = [
    ('back', [(520, 300), (620, 280), (700, 330), (540, 420), (650, 440), (720, 420)]),
    ('left', [(300, 470), (400, 430), (500, 480), (250, 600), (350, 650), (390, 700), (300, 720)]),
    ('right', [(850, 420), (950, 400), (1030, 450), (820, 540), (920, 560), (1020, 540)]),
    ('mid', [(560, 580), (650, 560), (740, 600), (480, 720), (560, 800), (660, 780), (520, 880)]),
    ('front', [(820, 650), (950, 620), (1050, 680), (780, 780), (900, 800), (1030, 760), (850, 880)]),
]
PLATE = [[(147, 483), (113, 650), (180, 780), (247, 850), (400, 940), (580, 985), (760, 990), (947, 967),
          (1080, 900), (1135, 860), (1162, 760), (1166, 650), (1165, 560), (1160, 480), (1113, 400)],
         [(313, 350), (200, 420)], [(830, 300), (1000, 330)], [(420, 330), (380, 340)], [(300, 830), (380, 860)]]


R_EDGE = 0.0055      # the rounding of a cube's edges (m)
# the cubes the art shows only in part (the others hide them) are given the size of those it shows whole: half sizes
SIZES = {'back': (0.0265, 0.0245, 0.022), 'right': (0.0265, 0.0245, 0.022)}
YAWS = {'right': math.radians(54)}   # and the turn of the others
# the aspic's colours (k-means): pale on top #f9d89c, amber #f1c174, deeper #e3a757, darkest #d28937; how far each
# pixel is from pale toward the darkest, and the levels tinted in: (middle of the level, colour, weight)
PALE, DEEP = (249, 216, 156), (210, 137, 55)
LEVELS = {'pale': (0.0, '#fbe2b0', 0.6), 'amber': (0.45, '#f0bc6c', 0.55), 'deep': (0.85, '#dc9442', 0.8)}
CHANNELS = list(LEVELS) + ['skin', 'cut']
RING, INK = (0.0006, 0.0012), [3.5, 3.0]
BIT_INK = [0.5, 2.5]


def amber(rgb):
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.5), cv2.COLOR_RGB2LAB).astype(np.float32)
    c0, c1 = (cv2.cvtColor(np.array([[c]], np.uint8), cv2.COLOR_RGB2LAB)[0, 0].astype(np.float32) for c in (PALE, DEEP))
    ax = c1 - c0
    return np.clip(((lab - c0) @ ax) / (ax @ ax), 0, 1)


def classes(rgb, cubes, scallion, ginger):
    """The aspic's levels of amber (soft), the curls of skin in it and the scallion's pale cut ends (painted)."""
    hsv = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.0), cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    A = cv2.GaussianBlur(amber(rgb), (0, 0), 2.0)
    out = np.zeros(cubes.shape + (len(CHANNELS),), np.uint8)
    jelly = cubes & ~cv2.dilate(u8(scallion | ginger), disk(2)).astype(bool)
    for c, (a0, _, _) in LEVELS.items():
        if c == 'amber':
            bump = np.clip(1 - np.abs(A - a0) / 0.3, 0, 1)
        elif c == 'pale':
            bump = np.clip(1 - (A - a0) / 0.3, 0, 1)
        else:
            bump = np.clip((A - a0 + 0.3) / 0.3, 0, 1)
        out[..., CHANNELS.index(c)] = np.where(jelly, bump * 255 + 0.5, 0).astype(np.uint8)
    # the curls of skin: paler and less amber than the aspic round about
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.5), cv2.COLOR_RGB2LAB).astype(np.float32)
    L, C = lab[..., 0] * 100 / 255, np.hypot(lab[..., 1] - 128, lab[..., 2] - 128)
    m = cubes.astype(np.float32)
    local = lambda a: cv2.GaussianBlur(a * m, (0, 0), 12) / np.maximum(cv2.GaussianBlur(m, (0, 0), 12), 1e-3)
    skin = jelly & (L - local(L) > 3) & (local(C) - C > 4) & (C < 45)
    skin = cv2.morphologyEx(u8(skin), cv2.MORPH_OPEN, disk(2))
    skin = cv2.dilate(skin, disk(2)).astype(bool) & jelly       # their whole width, the art's soft edges and all
    out[..., CHANNELS.index('skin')] = paint_channels([skin], cubes, smooth=1.5, min_area=160, close=2)[..., 0]
    cut = scallion & (v > 0.62) & (s < 0.55)   # the pale green inside a piece of scallion, at its cut end
    out[..., CHANNELS.index('cut')] = paint_channels([cut], scallion, smooth=0.8, min_area=15, close=1)[..., 0]
    return out


def garnish(rgb, pieces):
    """The scallion (green) and the ginger shreds (pale yellow, long and thin) on the cubes' tops."""
    hsv = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.0), cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    cubes = pieces > 0
    scallion = cv2.morphologyEx(u8(cubes & (h > 60) & (h < 170) & (s > 0.3)), cv2.MORPH_CLOSE, disk(2))
    scallion = cv2.morphologyEx(scallion, cv2.MORPH_OPEN, disk(2)).astype(bool)
    g = cv2.morphologyEx(u8(cubes & (h > 40) & (h < 58) & (s > 0.22) & (s < 0.62) & (v > 0.93)), cv2.MORPH_OPEN,
                         np.ones((3, 3), np.uint8))
    n, cc, st, _ = cv2.connectedComponentsWithStats(g)
    ginger = np.zeros_like(cubes)
    sc_n, sc_cc, sc_st, sc_c = cv2.connectedComponentsWithStats(u8(scallion))
    centres = [sc_c[j] for j in range(1, sc_n) if sc_st[j, cv2.CC_STAT_AREA] > 150]
    for j in range(1, n):
        if st[j, cv2.CC_STAT_AREA] < 60:
            continue
        ys, xs = np.nonzero(cc == j)
        (cu, cv_), (rw, rh), _ = cv2.minAreaRect(np.stack([xs, ys], -1).astype(np.float32))
        ln, wd = max(rw, rh), max(min(rw, rh), 1.0)
        near = min((np.hypot(cu - c[0], cv_ - c[1]) for c in centres), default=1e9)
        if ln > 45 and ln / wd > 3.2 and near < 150:
            ginger |= cc == j
    ginger = cv2.dilate(u8(ginger), disk(3)).astype(bool) & cubes & ~scallion   # with its ink line
    return scallion, ginger


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    H, W = alpha.shape
    zone = alpha > 128
    pieces = seeded_pieces(rgb, zone, {i + 1: st for i, (_, st) in enumerate(PIECES)}, PLATE)
    scallion, ginger = garnish(rgb, pieces)
    paint = classes(rgb, pieces > 0, scallion, ginger)
    dish_V, dish_T = dish_mesh(DISH)
    floor = Grid.top_of(dish_V, dish_T)
    union = pieces > 0
    built = []
    boxes = []
    for pid, (name, _) in enumerate(PIECES, 1):
        own = largest(cv2.morphologyEx(u8(pieces == pid), cv2.MORPH_OPEN, disk(2)))
        later = np.isin(pieces, list(range(pid + 1, len(PIECES) + 1)))   # the cubes in front of it
        ys, xs = np.nonzero(own)
        X, Y, _ = CAM.backproject(np.array([xs.mean()]), np.array([ys.mean() + 30.0]),
                                  lambda x, y: x * 0 + FZ + 0.02)
        (x, y, hx, hy, hz, yaw), miss = fit_box(CAM, own, own | later, FZ, (X[0], Y[0], 0.026, 0.026, 0.024, 0.3),
                                                seed=pid, size=SIZES.get(name), yaw=YAWS.get(name))
        boxes.append((x, y, hx, hy, hz, yaw))
        print(f'[trace] {name}: box at ({x:.3f}, {y:.3f}), {2 * hx * 100:.1f} x {2 * hy * 100:.1f} x '
              f'{2 * hz * 100:.1f} cm, turned {math.degrees(yaw):.0f} deg, off by {miss:.3f}', flush=True)
        mk = fill_holes(cv2.dilate(u8(own), disk(3)).astype(bool) & union)
        mk = cv2.GaussianBlur(mk.astype(np.float32), (0, 0), 2.0) > 0.5
        skin = (paint[..., CHANNELS.index('skin')] > 127) & mk
        extra = contour_points([skin], 16.0)
        uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, 0.0095, 0.004, RING, smooth_px=3.0, extra=extra,
                                                extra_margin=8.0)
        sdf = rounded_box_sdf((x, y, FZ + hz), (hx, hy, hz), yaw, R_EDGE)
        s_c = float(CAM.depth(np.array([x, y, FZ + hz])))
        P = onto_solid(CAM, uv, sdf, s_c - 0.12, s_c + 0.12)
        T = oriented(P, [tuple(t) for t in np.asarray(tris)], CAM.toward, True)
        P, T = closed_under(CAM, P, T, nb, uv, lambda xx, yy: floor(xx, yy))
        built.append([name, uv, nb, P, T])
        print(f'[trace] {name}: {len(T)} triangles', flush=True)
    out = []
    zb_all, zid_all = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
    for i, (name, uv, nb, P, T) in enumerate(built):
        zb, zid = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
        for j in range(i + 1, len(built)):
            raster_piece(CAM, built[j][3], built[j][4], len(built[j][1]), j, zb, zid)
        if i + 1 < len(built):
            P = behind(CAM, P, zb, count=len(uv))
        raster_piece(CAM, P, T, len(uv), i + 1, zb_all, zid_all)
        out.append({'name': name, 'kind': 'cube', 'mat': 'SjkJelly', 'rim': nb,
                    'paint': [(CHANNELS.index('skin'), 'SjkSkin')],
                    'tint': [(CHANNELS.index(c), col, w) for c, (_, col, w) in LEVELS.items()],
                    'ink': INK, 'closed': len(uv),
                    'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]})
    # the scallion and the ginger on top, each a small piece lying on its cube
    on_dish = lambda u, v: CAM.depth(np.stack(CAM.backproject(u, v, floor), -1))
    nbits = 0
    for kind, mask, mat, top, gap, gb in (('ginger', ginger, 'SjkGinger', 0.0016, 0.004, 0.0022),
                                          ('scallion', scallion, 'SjkScallion', 0.0032, 0.0035, 0.002)):
        n, cc, st, _ = cv2.connectedComponentsWithStats(u8(mask))
        for j in range(1, n):
            if st[j, cv2.CC_STAT_AREA] < 60:
                continue
            mk = cv2.GaussianBlur((cc == j).astype(np.float32), (0, 0), 1.2) > 0.5
            ex = contour_points([(paint[..., CHANNELS.index('cut')] > 127) & mk], 6.0) if kind == 'scallion' else None
            uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, gap, gb, 0.0003, smooth_px=1.5, extra=ex,
                                                    extra_margin=3.0)
            L = profile(d, R, float(np.clip(0.8 * R, 0.0008, top)))
            P, T = over(CAM, uv, tris, L, zb_all, on_dish)
            out.append({'name': f'{kind}{j}', 'kind': 'bit', 'mat': mat, 'rim': nb,
                        'paint': [(CHANNELS.index('cut'), 'SjkScallionCut')] if kind == 'scallion' else [],
                        'tint': [], 'ink': BIT_INK,
                        'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]})
            nbits += 1
    print(f'[trace] {nbits} bits of scallion and ginger', flush=True)
    np.savez_compressed(PAINT, paint=paint[::2, ::2])
    data = {'camera': {'el': CAM.el, 'k': CAM.k, 'u0': CAM.u0, 'v0': CAM.v0}, 'paint_scale': 0.5,
            'channels': CHANNELS, 'pieces': out, 'bits': [], 'boxes': [list(map(float, b)) for b in boxes]}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT}: {sum(len(o["tris"]) for o in out)} triangles', flush=True)
    if sheet:
        shown = pieces.copy()
        k0 = shown.max()
        shown[ginger] = k0 + 1
        shown[scallion] = k0 + 2
        tracing_sheet(sheet, rgba, shown, None, [(250, 205, 130)] * len(PIECES) + [(250, 235, 160), (110, 180, 70)],
                      crop=(80, 150, 1180, 1060), title=('原图上的描线（蓝：每一块）', '描出的五块水晶脍、葱和姜丝'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
