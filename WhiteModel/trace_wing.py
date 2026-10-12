"""Traces 鸡翅's art (新建文件夹/鸡翅.png) for the raw chicken wings, so that its three wingettes are modelled 1:1 (勾勒):
writes food_models/traced_wing.json and the colours of its pieces food_models/traced_wing_paint.npz, which
meat_fish.wing builds them from, and a tracing sheet.

    python WhiteModel/trace_wing.py [--sheet <out.png>] [--seg]

1. The art's camera: fitted so that the deep plate wing_plate builds covers the art's plate where no food hides it
   (plate-only IoU 0.957). The plate's inside, under the wings, is read off it.
2. The pieces: a flood of the art seeded by strokes inside each (PIECES, read off the art by eye) and on the plate
   round them (PLATE), its ink lines walls: the wing at the back right, the one at the back left lying over its end,
   and the one in front over both. Each is carried on under what lies in front of it (its outline's convex hull),
   so that it is whole from every side.
3. Their colours: the art's own, tinted in softly (meat_fish.art_colours: the pink skin, its cream edges, the light
   and shade the art paints), and painted on crisply where the art has them: the pink meat of the cut ends and its
   deeper red, the wet white glints along the skin's wrinkles, the ink line round each and the few inside them.
4. Each wingette a plump rounded lens over its outline: the outline on the plane where the silhouette of an
   ellipsoid as long, wide and high as the wingette lies (its lowest point just over the plate), its front bulging to
   the eye and its back away, rounder than a circle's arc, the art's shading in relief, its underside flattened onto
   the plate, and kept in front of the wingettes it lies over. From the art's camera each covers exactly what the
   art paints.
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

from trace_common import (Camera, Grid, above, contour_points, dish_mesh, disk, fill_holes, largest, neighbours,
                          outline_mesh, paint_channels, profile, raster, seeded_pieces, shading_band, smooth_inner,
                          standing, tracing_sheet, u8)

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '鸡翅.png')
DISH = "from food_models.meat_fish import wing_plate\nwing_plate(p)"
OUT = os.path.join(HERE, 'food_models', 'traced_wing.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_wing_paint.npz')
CAM = Camera(36.84, 5819.3, 629.4, 802.2)          # (1)

# (2) the pieces, built in this order: name, strokes inside it (art pixels)
PIECES = [
    ('right', [(800, 470), (880, 520), (960, 600), (1030, 680), (1060, 740), (900, 600), (760, 520)]),
    ('left', [(250, 620), (300, 560), (400, 470), (500, 390), (580, 330), (650, 330), (420, 560)]),
    ('front', [(400, 760), (500, 700), (600, 680), (700, 720), (800, 780), (880, 830), (500, 820), (650, 800)]),
]
PLATE = [[(x - 4, y), (x + 4, y)] for x, y in
         ((250, 450), (200, 820), (350, 900), (600, 960), (700, 920), (960, 880), (1000, 420), (800, 350),
          (1120, 620), (1100, 560), (130, 600), (160, 700), (180, 560), (1000, 820), (1050, 830), (450, 920))]
# each wingette: the half-height of the ellipsoid whose silhouette's plane its outline lies on, its lowest outline
# point this far over the plate's floor, how much rounder than a circle's arc it bulges, the art's shading in relief
SHAPE = dict(c=0.019, low=0.002, round=1.5, relief=0.003, gap=0.0095, gb=0.005)
CHANNELS = ['cut', 'deep', 'glint', 'ink']
PAINTS = [('cut', 'WingRawMeat'), ('deep', 'WingRawDeep'), ('glint', 'WingRawGlint'), ('ink', 'WingRawInk')]
INK, INKRING = [6.5, 3.0], (6, 10)   # the art's clear ink line round every piece (full to, gone by; its rings)


def classes(rgb, pieces):
    """The paint channels over the art: the cut ends' pink meat and its deeper red, the glints, the inner lines."""
    food = pieces > 0
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.5), cv2.COLOR_RGB2LAB).astype(np.float32)
    L, A = lab[..., 0], lab[..., 1] - 128
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    s, v = hsv[..., 1] / 255, hsv[..., 2] / 255
    rim = np.zeros(food.shape, bool)   # within a few pixels of any piece's outline: the ink line's, not paint
    for pid in range(1, pieces.max() + 1):
        rim |= cv2.dilate(u8(cv2.morphologyEx(u8(pieces == pid), cv2.MORPH_GRADIENT, disk(1))), disk(6)).astype(bool)
    cut = food & ~rim & (A > 24) & (L < 205) & (v > 0.45)
    deep = food & ~rim & (A > 36) & (L < 170) & (v > 0.4)
    gl = cv2.morphologyEx(u8(food & ~rim & (v > 0.94) & (s < 0.14)), cv2.MORPH_CLOSE, disk(2))
    n, cc, st, _ = cv2.connectedComponentsWithStats(gl)
    keep = np.zeros(n, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 90
    glint = keep[cc]
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    bh = cv2.morphologyEx(cv2.GaussianBlur(lum, (0, 0), 1.0), cv2.MORPH_BLACKHAT, disk(6))
    ink = cv2.morphologyEx(u8(food & ~rim & (bh > 50) & (v < 0.5) & (s > 0.35)), cv2.MORPH_CLOSE, disk(2))
    n, cc, st, _ = cv2.connectedComponentsWithStats(ink)
    keep = np.zeros(n, bool)
    keep[1:] = (st[1:, cv2.CC_STAT_AREA] > 50) & (np.maximum(st[1:, cv2.CC_STAT_WIDTH], st[1:, cv2.CC_STAT_HEIGHT]) > 20)
    ink = keep[cc]
    return np.concatenate([paint_channels([cut, deep], food, smooth=1.5, min_area=90, close=2),
                           paint_channels([glint], food, smooth=1.0, min_area=90, close=1),
                           paint_channels([ink], food, smooth=0.8, min_area=40, close=1)], -1)


def contour_plane(mk, floor, c):
    """The plane a wingette's outline lies on: through the middle of the ellipsoid as long and wide as its outline
    (seen at its middle's height) and 2c high, lying on the plate, where that ellipsoid's silhouette from the art's
    camera lies; and its half-depth along the line of sight at its middle."""
    ys, xs = np.nonzero(mk[::4, ::4])
    X, Y, _ = CAM.backproject(xs * 4.0, ys * 4.0, floor, lift=c)
    P = np.stack([X, Y], -1)
    mu = P.mean(0)
    w, V = np.linalg.eigh(np.cov((P - mu).T))
    a, b = 2 * math.sqrt(w[1]), 2 * math.sqrt(w[0])
    yaw = math.atan2(V[1, 1], V[0, 1])
    R = np.array([[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]])
    M = R @ np.diag([1 / a ** 2, 1 / b ** 2, 1 / c ** 2]) @ R.T
    t = CAM.toward
    n = M @ t
    n /= np.linalg.norm(n)
    anchor = np.array([mu[0], mu[1], float(floor(np.array([mu[0]]), np.array([mu[1]]))[0]) + c])
    return anchor, n, float(1 / math.sqrt(t @ M @ t)), (a, b, math.degrees(yaw))


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    H, W = alpha.shape
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    zone = alpha > 128
    walled = rgb.copy()
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    inkm = cv2.morphologyEx(u8((hsv[..., 2] < 0.45 * 255) & (hsv[..., 1] > 0.35 * 255)), cv2.MORPH_CLOSE, disk(2))
    walled[inkm.astype(bool) & zone] = (70, 34, 16)   # the art's ink lines, small gaps in them closed
    pieces = seeded_pieces(walled, zone, {i + 1: st for i, (_, st) in enumerate(PIECES)}, PLATE)
    names = [n for n, _ in PIECES]
    for pid in range(1, len(PIECES) + 1):   # each piece one clean region
        m = pieces == pid
        keep = fill_holes(largest(cv2.morphologyEx(u8(m), cv2.MORPH_OPEN, disk(2))))
        pieces[m & ~keep] = 0
        pieces[keep & (pieces == 0)] = pid
    print(f'[trace] {pieces.max()} pieces: ' + ', '.join(f'{n} {int((pieces == i + 1).sum())}'
                                                         for i, n in enumerate(names)), flush=True)
    tints = [(250, 200, 180), (245, 190, 170), (252, 214, 196)]
    if '--seg' in sys.argv:
        tracing_sheet(sheet, rgba, pieces, names, tints, crop=(120, 230, 1150, 940))
        return
    paint = classes(rgb, pieces)
    dish_V, dish_T = dish_mesh(DISH)
    floor = Grid.top_of(dish_V, dish_T)
    zb = np.full((H, W), np.inf)        # the wingettes built so far as the art's view sees them, nearest first
    zid = np.full((H, W), -1, np.int32)
    union = pieces > 0
    out = []
    for pid, (name, _) in enumerate(PIECES, 1):
        mk = largest(cv2.morphologyEx(u8(pieces == pid), cv2.MORPH_OPEN, disk(2)))
        later = np.isin(pieces, list(range(pid + 1, len(PIECES) + 1)))   # carried on under what lies in front
        hull = np.zeros((H, W), np.uint8)
        cs, _ = cv2.findContours(u8(mk), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.fillPoly(hull, [cv2.convexHull(max(cs, key=len))], 1)
        mk = mk | (hull.astype(bool) & later)
        mk = cv2.morphologyEx(u8(mk), cv2.MORPH_OPEN, disk(6)).astype(bool)
        mk = fill_holes(cv2.dilate(u8(mk), disk(3)).astype(bool) & union)   # a little under its neighbours
        mk = cv2.GaussianBlur(mk.astype(np.float32), (0, 0), 2.0) > 0.5
        edges = [(paint[..., CHANNELS.index(c)] > 127) & mk for c, _ in PAINTS]
        extra = contour_points(edges, 10.0).reshape(-1, 2)
        rings = [cv2.erode(u8(mk), disk(r)).astype(bool) for r in INKRING]
        extra = np.r_[extra, contour_points(rings, 15.0).reshape(-1, 2)]
        uv, tris, nb, d, R, _ = outline_mesh(CAM, mk, SHAPE['gap'], SHAPE['gb'], 0.0005, smooth_px=4.0, extra=extra,
                                             extra_margin=2.5)
        iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
        ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
        band = shading_band(lum, mk, 8.0, 40.0)
        anchor, nrm, h0, (a, b, yaw) = contour_plane(mk, floor, SHAPE['c'])
        rim = CAM.on_ray(uv[:nb, 0], uv[:nb, 1], CAM.plane_depth(uv[:nb, 0], uv[:nb, 1], anchor, nrm))
        gap = rim[:, 2] - floor(rim[:, 0], rim[:, 1]) - SHAPE['low']   # its lowest outline point just over the floor
        r_ = CAM.away
        anchor = anchor - np.array([0, 0, 1.0]) * gap.min() * (r_ @ nrm) / (nrm[2] * r_[2])
        L = h0 * profile(d, R, 1.0) ** SHAPE['round'] + SHAPE['relief'] * band[iy, ix] * np.clip(d / (0.3 * R), 0, 1)
        L = smooth_inner(L, nb, neighbours(len(uv), tris))
        ub, tb, nbb, db, Rb, _ = outline_mesh(CAM, mk, SHAPE['gap'] * 3.0, SHAPE['gb'], 0.0012, smooth_px=4.0)
        assert nbb == nb and np.allclose(ub[:nb], uv[:nb], atol=1e-3), 'the back must share the outline'
        Lb = h0 * 0.9 * profile(db, Rb, 1.0) ** SHAPE['round']
        P, T = standing(CAM, uv, tris, nb, L, Lb, anchor, normal=nrm, back=(ub, tb))
        # in front of the wingettes it lies over, each point along its own line of sight
        s = CAM.depth(P[:len(uv)])
        lim = zb[iy, ix] - 0.0015
        push = np.where(np.isfinite(lim), np.maximum(s - lim, 0.0), 0.0)
        if push.max() > 0:
            nbr = neighbours(len(uv), tris)
            for _ in range(3):   # spread a little, so that it rises over them rather than kinks
                push = np.maximum(push, 0.6 * np.array([max((push[j] for j in nbr[k]), default=0.0) for k in range(len(uv))]))
            P[:len(uv)] = CAM.on_ray(uv[:, 0], uv[:, 1], s - push)
        P = above(CAM, P, floor, front=len(uv), gap=0.0006)
        front = np.array([t for t in T if max(t) < len(uv)])
        pu, pv = CAM.project(P[:, 0], P[:, 1], P[:, 2])
        raster(np.stack([pu, pv], -1)[front], CAM.depth(P)[front], np.full(len(front), pid), H, W, zb, zid)
        out.append({'name': name, 'kind': 'wing', 'mat': 'WingRawSkin', 'rim': nb,
                    'paint': [(CHANNELS.index(c), m) for c, m in PAINTS], 'tint': [], 'ink': INK,
                    'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]})
        print(f'[trace] {name}: {len(T)} triangles, {a * 200:.1f} x {b * 200:.1f} cm at {yaw:.0f} deg, bulge '
              f'{h0 * 1000:.0f} mm, outline z {rim[:, 2].min() * 100:.1f}..{P[:nb, 2].max() * 100:.1f} cm, '
              f'top {P[:len(uv), 2].max() * 100:.1f} cm, pushed {push.max() * 1000:.1f} mm', flush=True)
    # the art's own colours over the food, its ink lines and glints taken out (meat_fish.art_colours tints them in)
    food = pieces > 0
    clean = food & (hsv[..., 2] > 0.5 * 255) & (paint[..., CHANNELS.index('glint')] < 64)
    clean = cv2.erode(u8(clean), disk(1)).astype(bool)
    m = clean.astype(np.float32)
    colour = np.stack([cv2.GaussianBlur(rgb[..., c].astype(np.float32) * m, (0, 0), 3.0) for c in range(3)], -1)
    colour /= np.maximum(cv2.GaussianBlur(m, (0, 0), 3.0), 1e-3)[..., None]
    np.savez_compressed(PAINT, paint=paint[::2, ::2], colour=np.clip(colour[::2, ::2], 0, 255).astype(np.uint8))
    data = {'camera': {'el': CAM.el, 'k': CAM.k, 'u0': CAM.u0, 'v0': CAM.v0}, 'paint_scale': 0.5, 'colour_scale': 0.5,
            'channels': CHANNELS, 'pieces': out, 'bits': []}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT} and {PAINT}', flush=True)
    if sheet:
        tracing_sheet(sheet, rgba, pieces, names, tints, crop=(120, 230, 1150, 940),
                      title=('原图上的描线（蓝：每一块）', f'描出的 {pieces.max()} 块鸡翅'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
