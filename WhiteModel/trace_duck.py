"""Traces 鸭's art (新建文件夹/鸭.png) for the raw duck, so that its body, wings and legs are modelled 1:1 (勾勒): writes
food_models/traced_duck.json and the colours of its pieces food_models/traced_duck_paint.npz, which meat_fish.duck
builds it from, and a tracing sheet.

    python WhiteModel/trace_duck.py [--sheet <out.png>]

1. The art's camera: fitted so that the oval platter duck_plate builds covers the art's plate where no food hides it
   (plate-only IoU 0.947: the art's oval is drawn freehand). The platter's inside, under the duck, is read off it.
2. The pieces: a flood of the art seeded by strokes inside each (PIECES, read off the art by eye) and on the plate
   round them (PLATE), its ink lines walls (and a few drawn in, WALLS, where the art only shades the join): the body
   with its neck end, the far wing showing over its back, the far and near drumsticks with their knuckles, and the
   near wing folded at its side, its lower and upper tubes and the pointed tip flap folded over them.
3. Their colours: the art's own, tinted in softly (meat_fish.art_colours: the skin's cream, warmer peach and pink,
   the light and shade the art paints), and painted on crisply where the art has them: the knuckles' pink cut faces
   and their deeper middles, the wet white glints, and the few lines the art draws inside a piece.
4. The body a thick rounded lens over its whole outline (where the legs and the near wing hide it too): its outline
   on the plane where a plump ellipsoid's silhouette lies (low at the front, high at the back), its front bulging to
   the eye and its back away, the underside flattened onto the platter. Every other piece drapes over what is
   already there (the platter, the body, the pieces before it), never receding faster than DRAPE, as a rounded
   mound over its outline, closed behind by a coarser lens resting on the platter. From the art's camera each covers exactly
   what the art paints.
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

from trace_common import (Camera, Grid, above, contour_points, dish_mesh, disk, fill_holes, largest,
                          neighbours, oriented, outline_mesh, paint_channels, profile, raster, seeded_pieces, shading_band,
                          smooth_inner, standing, tracing_sheet, u8)

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '鸭.png')
DISH = "from food_models.meat_fish import duck_plate\nduck_plate(p)"
OUT = os.path.join(HERE, 'food_models', 'traced_duck.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_duck_paint.npz')
CAM = Camera(35.09, 4724.1, 634.6, 722.3)          # (1)

# (2) the pieces, built in this order: name, kind, strokes inside it (art pixels)
PIECES = [
    ('body', 'body', [(300, 300), (340, 330), (290, 420), (420, 380), (520, 420), (620, 470), (720, 520), (820, 570),
                      (920, 610), (990, 640), (500, 560), (420, 470), (860, 690), (940, 700)]),
    ('farwing', 'farwing', [(662, 358), (700, 376), (740, 398), (780, 420), (820, 445), (860, 470), (888, 490)]),
    ('farleg', 'leg', [(1040, 700), (1060, 750), (1090, 800), (1110, 815)]),
    ('thigh', 'thigh', [(560, 700), (640, 740), (720, 780), (770, 830), (700, 860), (600, 820), (520, 700)]),
    ('nearleg', 'leg', [(650, 912), (720, 920), (800, 925), (880, 900), (910, 890), (930, 920), (950, 940),
                        (900, 950)]),
    ('wing', 'wing', [(200, 540), (200, 600), (230, 620), (260, 660), (290, 640), (320, 700), (340, 670), (380, 750),
                      (390, 700), (430, 735), (440, 795)]),
    ('wingtip', 'flap', [(260, 545), (310, 560), (350, 575), (385, 610)]),
]
PLATE = [[(x - 4, y), (x + 4, y)] for x, y in
         ((300, 790), (400, 850), (550, 900), (700, 975), (850, 990), (1000, 930), (1100, 880), (1160, 760),
          (1130, 640), (1060, 560), (980, 500), (920, 470), (140, 500), (130, 650), (200, 720), (210, 420),
          (1000, 890), (330, 820), (600, 930), (800, 975), (1120, 700), (940, 480), (110, 560), (180, 460))]
WALLS = [[(995, 712), (1048, 676)], [(252, 572), (236, 499)],
         [(612, 922), (628, 893), (700, 899), (780, 906), (840, 905), (852, 860)],
         [(470, 612), (530, 625), (600, 645), (650, 665), (700, 682), (750, 698), (795, 718), (812, 755),
          (803, 785)]]   # [(art pixels)...]: lines drawn into the art as ink, where pieces meet without one
DRAPE = 1.8         # a drape recedes from what is nearer by at most this many pixels' worth of depth a pixel
# the body: the ellipsoid whose silhouette's plane its outline lies on (half-length, -width, -height, its yaw)
BODY = dict(a=0.11, b=0.062, c=0.043, yaw=-50.0, low=0.003, round=1.8)
CHANNELS = ['cut', 'deep', 'ink', 'glint']
KINDS = {
    'body': dict(gap=0.011, gb=0.006, puff=1.0, top=0.06, edge=0.0, relief=0.004, mat='DuckRawSkin', ink=[6.5, 3.0], inkring=(6, 10),
                 paint=[('ink', 'DuckRawInk'), ('glint', 'DuckRawGlint')],
                 tint=[]),
    'thigh': dict(gap=0.012, gb=0.006, puff=0.6, top=0.024, edge=0.0, relief=0.003, mat='DuckRawSkin', ink=[0.0, 0.0],
                  inkring=(), paint=[('ink', 'DuckRawInk'), ('glint', 'DuckRawGlint')],
                  tint=[]),
    'farwing': dict(gap=0.007, gb=0.004, puff=0.7, top=0.008, edge=0.0, relief=0.0, mat='DuckRawLimb', ink=[4.5, 2.5], inkring=(4, 7),
                    paint=[('ink', 'DuckRawInk'), ('glint', 'DuckRawGlint')],
                    tint=[]),
    'leg': dict(gap=0.008, gb=0.0045, puff=0.85, top=0.016, edge=0.0, relief=0.0015, mat='DuckRawLimb', ink=[6.5, 3.0], inkring=(6, 10),
                paint=[('cut', 'DuckRawCut'), ('deep', 'DuckRawBone'), ('ink', 'DuckRawInk'), ('glint', 'DuckRawGlint')],
                tint=[]),
    'wing': dict(gap=0.008, gb=0.0045, puff=0.85, top=0.014, edge=0.0, relief=0.0015, mat='DuckRawLimb', ink=[6.5, 3.0], inkring=(6, 10),
                 paint=[('ink', 'DuckRawInk'), ('glint', 'DuckRawGlint')],
                 tint=[]),
    'flap': dict(gap=0.007, gb=0.004, puff=0.6, top=0.008, edge=0.0, relief=0.001, mat='DuckRawLimb', ink=[5.5, 3.0], inkring=(5, 9),
                 paint=[('ink', 'DuckRawInk'), ('glint', 'DuckRawGlint')],
                 tint=[]),
}
KNOBS = [((925, 915), 62), ((1100, 812), 52)]   # the knuckles at the drumsticks' ends: middle, reach (art px)


def classes(rgb, pieces, names):
    """The paint channels over the art (CHANNELS): the knuckles' pink cut faces and their deeper middles, the few
    lines the art draws inside a piece, and its wet white glints."""
    H, W = pieces.shape
    food = pieces > 0
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 2.0), cv2.COLOR_RGB2LAB).astype(np.float32)
    L, A = lab[..., 0], lab[..., 1] - 128
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    s, v = hsv[..., 1] / 255, hsv[..., 2] / 255
    inner = cv2.erode(u8(food), disk(5)).astype(bool)
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    edge = np.zeros((H, W), bool)   # every piece's outline: the ink line's, not paint
    for pid in range(1, pieces.max() + 1):
        edge |= cv2.morphologyEx(u8(pieces == pid), cv2.MORPH_GRADIENT, disk(1)).astype(bool)
    edge |= cv2.morphologyEx(u8(food), cv2.MORPH_GRADIENT, disk(1)).astype(bool)
    # the knuckles: their pink folds and deeper middles, within reach of each knuckle's middle, away from the outline
    yy, xx = np.mgrid[0:H, 0:W]
    near = np.zeros((H, W), bool)
    for (cx, cy), r in KNOBS:
        near |= (xx - cx) ** 2 + (yy - cy) ** 2 < r * r
    near &= food & ~cv2.dilate(u8(edge), disk(7)).astype(bool)
    cut = near & (A > 22) & (L < 212)
    deep = near & (A > 30) & (L < 192)
    # the lines the art draws inside a piece: dark brown, thin, long, away from every piece's outline
    away = ~cv2.dilate(u8(edge | ~food), disk(9)).astype(bool)
    bhl = cv2.morphologyEx(cv2.GaussianBlur(lum, (0, 0), 1.0), cv2.MORPH_BLACKHAT, disk(6))
    ink = cv2.morphologyEx(u8(away & (bhl > 45) & (v < 0.5) & (s > 0.35)), cv2.MORPH_CLOSE, disk(2))
    n, cc, st, _ = cv2.connectedComponentsWithStats(ink)
    keep = np.zeros(n, bool)
    keep[1:] = (st[1:, cv2.CC_STAT_AREA] > 60) & (np.maximum(st[1:, cv2.CC_STAT_WIDTH], st[1:, cv2.CC_STAT_HEIGHT]) > 25)
    ink = keep[cc]
    # the wet glints: the art's white streaks, big enough to show
    gl = cv2.morphologyEx(u8((v > 0.94) & (s < 0.14) & inner), cv2.MORPH_CLOSE, disk(2))
    n, cc, st, _ = cv2.connectedComponentsWithStats(gl)
    keep = np.zeros(n, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 120
    glint = keep[cc]
    return np.concatenate([paint_channels([cut, deep], food, smooth=1.5, min_area=80, close=2),
                           paint_channels([ink], food, smooth=0.8, min_area=40, close=1),
                           paint_channels([glint], food, smooth=1.0, min_area=120, close=1)], -1)


def drape_depth(zbuf, reach=160):
    """What a piece laid over the art's view drapes over, as depths per art pixel: the nearest surface there (zbuf),
    brought forward near anything nearer so that it never recedes faster than DRAPE per pixel: off the body's edge a
    piece runs on and down to the platter (or back over the far side) gently, not down a cliff."""
    s = np.where(np.isfinite(zbuf), zbuf, 1.0).astype(np.float32)
    rise = DRAPE / CAM.k
    for _ in range(reach):
        s = np.minimum(s, cv2.erode(s, np.ones((3, 3), np.uint8)) + rise)
    return s


def body_plane(anchor_px, floor):
    """The plane the body's outline lies on: through the middle of an ellipsoid (BODY) lying on the platter under
    the art pixel anchor_px, where its silhouette from the art's camera lies; and the ellipsoid's half-depth along
    the line of sight at its middle (how far the body bulges to the eye there)."""
    a, b, c, yaw = BODY['a'], BODY['b'], BODY['c'], math.radians(BODY['yaw'])
    R = np.array([[math.cos(yaw), -math.sin(yaw), 0], [math.sin(yaw), math.cos(yaw), 0], [0, 0, 1]])
    M = R @ np.diag([1 / a ** 2, 1 / b ** 2, 1 / c ** 2]) @ R.T
    t = CAM.toward
    n = M @ t
    n /= np.linalg.norm(n)
    u, v = anchor_px
    X, Y, Z = CAM.backproject(np.array([u]), np.array([v]), floor, lift=c)
    return np.array([X[0], Y[0], Z[0]]), n, float(1 / math.sqrt(t @ M @ t))


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
    if WALLS:
        im = Image.fromarray(walled)
        for line in WALLS:
            ImageDraw.Draw(im).line(line, fill=(70, 34, 16), width=4)
        walled = np.asarray(im).copy()
    strokes = {i + 1: st for i, (_, _, st) in enumerate(PIECES)}
    pieces = seeded_pieces(walled, zone, strokes, PLATE)
    names = [n for n, _, _ in PIECES]
    for pid in range(1, len(PIECES) + 1):   # each piece one clean region
        m = pieces == pid
        if m.any():
            keep = fill_holes(largest(cv2.morphologyEx(u8(m), cv2.MORPH_OPEN, disk(2))))
            pieces[m & ~keep] = 0
            pieces[keep & (pieces == 0)] = pid
    print(f'[trace] {pieces.max()} pieces: ' + ', '.join(f'{n} {int((pieces == i + 1).sum())}'
                                                         for i, n in enumerate(names)), flush=True)
    tints = {'body': (250, 226, 196), 'thigh': (250, 214, 186), 'farwing': (240, 190, 160), 'leg': (245, 180, 150), 'wing': (245, 200, 170),
             'flap': (235, 160, 140)}
    if '--seg' in sys.argv:   # only the cut into pieces, for checking the strokes
        tracing_sheet(sheet, rgba, pieces, names, [tints[k] for _, k, _ in PIECES], crop=(120, 230, 1200, 1010))
        return
    paint = classes(rgb, pieces, names)
    hsv_ = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL)
    for pid, n in enumerate(names, 1):   # the art's colours of each piece (no ink, no glints): for the palette
        m = cv2.erode(u8(pieces == pid), disk(6)).astype(bool) & (hsv_[..., 2] > 140) & (hsv_[..., 1] > 30)
        q = np.percentile(rgb[m], [25, 50, 75], axis=0).astype(int)
        print(f'[colour] {n}: ' + ' '.join('#%02x%02x%02x' % tuple(c) for c in q), flush=True)
    for (cx, cy), r in KNOBS:
        yy_, xx_ = np.mgrid[0:H, 0:W]
        m = ((xx_ - cx) ** 2 + (yy_ - cy) ** 2 < (r * 0.6) ** 2) & (paint[..., CHANNELS.index('cut')] > 127)
        if m.any():
            print('[colour] cut %d px: ' % m.sum() + ' '.join('#%02x%02x%02x' % tuple(c) for c in
                  np.percentile(rgb[m], [25, 50, 75], axis=0).astype(int)), flush=True)
    dish_V, dish_T = dish_mesh(DISH)
    floor = Grid.top_of(dish_V, dish_T)
    zb, zid = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)   # what the art's view sees, nearest first
    du, dv = CAM.project(dish_V[:, 0], dish_V[:, 1], dish_V[:, 2])
    raster(np.stack([du, dv], -1)[dish_T], CAM.depth(dish_V)[dish_T], np.zeros(len(dish_T), np.int32), H, W, zb, zid)
    union = pieces > 0
    front_ids = [names.index(n) + 1 for n in ('farleg', 'thigh', 'nearleg', 'wing', 'wingtip')]
    out = []
    for pid, (name, kind, _) in enumerate(PIECES, 1):
        kp = KINDS[kind]
        mk = largest(cv2.morphologyEx(u8(pieces == pid), cv2.MORPH_OPEN, disk(2)))
        if kind == 'body':   # its whole outline, carried on under what lies in front of it
            hull = np.zeros((H, W), np.uint8)
            cs, _ = cv2.findContours(u8(mk), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
            cv2.fillPoly(hull, [cv2.convexHull(max(cs, key=len))], 1)
            mk = mk | (hull.astype(bool) & np.isin(pieces, front_ids))
            mk = cv2.morphologyEx(u8(mk), cv2.MORPH_OPEN, disk(6)).astype(bool)
        if kind != 'farwing':   # a little under its neighbours (the far wing stays behind the body)
            mk = fill_holes(cv2.dilate(u8(mk), disk(3)).astype(bool) & union)
        mk = cv2.GaussianBlur(mk.astype(np.float32), (0, 0), 2.0) > 0.5
        edges = [(paint[..., CHANNELS.index(c)] > 127) & mk for c, _ in kp['paint']]
        extra = contour_points(edges, 10.0).reshape(-1, 2)
        rings = [cv2.erode(u8(mk), disk(r)).astype(bool) for r in kp['inkring']]   # the ink line's two edges, as
        extra = np.r_[extra, contour_points(rings, 13.0).reshape(-1, 2)]          # far in all round in the art
        uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, kp['gap'], kp['gb'], 0.0005, smooth_px=4.0, extra=extra,
                                                extra_margin=2.5)
        band = shading_band(lum, mk, 12.0, 60.0) if kind == 'body' else shading_band(lum, mk, 8.0, 40.0)
        iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
        ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
        if kind == 'body':
            ys, xs = np.nonzero(mk)
            anchor, nrm, h0 = body_plane((xs.mean(), ys.mean()), floor)
            rim = CAM.on_ray(uv[:nb, 0], uv[:nb, 1], CAM.plane_depth(uv[:nb, 0], uv[:nb, 1], anchor, nrm))
            gap = rim[:, 2] - floor(rim[:, 0], rim[:, 1]) - BODY['low']   # down (or up) until the lowest point of
            r_ = CAM.away                                                   # its outline is BODY['low'] over the floor
            anchor = anchor - np.array([0, 0, 1.0]) * gap.min() * (r_ @ nrm) / (nrm[2] * r_[2])
            top = min(h0, kp['top'])
            arc = profile(d, R, 1.0)   # round across, rounder still (no flat top): the arc raised to BODY['round']
            L = top * arc ** BODY['round'] + kp['relief'] * band[iy, ix] * np.clip(d / (0.3 * R), 0, 1)
            L = smooth_inner(L, nb, neighbours(len(uv), tris))
            ub, tb, nbb, db, Rb, _ = outline_mesh(CAM, mk, kp['gap'] * 2.4, kp['gb'], 0.0012, smooth_px=4.0)
            assert nbb == nb and np.allclose(ub[:nb], uv[:nb], atol=1e-3), 'the back must share the outline'
            Lb = profile(db, Rb, top * 0.9, 0.0)
            P, T = standing(CAM, uv, tris, nb, L, Lb, anchor, normal=nrm, back=(ub, tb))
            P = above(CAM, P, floor, front=len(uv), gap=0.0006)
            rim_z = P[:nb, 2]
            print(f'[trace] body: outline z {rim_z.min() * 100:.1f}..{rim_z.max() * 100:.1f} cm, '
                  f'top {P[:len(uv), 2].max() * 100:.1f} cm, bulge {top * 100:.1f} cm', flush=True)
            closed = None
        else:
            top = float(np.clip(kp['puff'] * R, 0.001, kp['top']))
            L = profile(d, R, top, kp['edge'], 0.0, None, kp['relief'], band[iy, ix])
            L = smooth_inner(L, nb, neighbours(len(uv), tris))
            sd = drape_depth(zb)
            P = CAM.on_ray(uv[:, 0], uv[:, 1], sd[iy, ix] - L)
            T = oriented(P, tris, CAM.toward, True)
            # its back: a coarser rounded lens just behind what it drapes over, sharing its outline, out of the plate
            ub, tb, nbb, db, Rb, _ = outline_mesh(CAM, mk, kp['gap'] * 2.5, kp['gb'], 0.0012, smooth_px=4.0)
            assert nbb == nb and np.allclose(ub[:nb], uv[:nb], atol=1e-3), 'the back must share the outline'
            iyb = np.clip(np.round(ub[:, 1]).astype(int), 0, H - 1)
            ixb = np.clip(np.round(ub[:, 0]).astype(int), 0, W - 1)
            Lb = profile(db, Rb, max(top * 0.8, 0.002))
            Q = CAM.on_ray(ub[nb:, 0], ub[nb:, 1], sd[iyb, ixb][nb:] + Lb[nb:])
            k0 = len(P)
            P = np.r_[P, Q]
            mp = lambda i: i if i < nb else i - nb + k0
            T = T + oriented(P, [(mp(a), mp(b), mp(c)) for a, b, c in tb], CAM.toward, False)
            P = above(CAM, P, floor, front=k0, gap=0.0006)
            closed = None
        front = np.array([t for t in T if max(t) < len(uv)])
        pu, pv = CAM.project(P[:, 0], P[:, 1], P[:, 2])
        raster(np.stack([pu, pv], -1)[front], CAM.depth(P)[front], np.full(len(front), pid), H, W, zb, zid)
        out.append({'name': name, 'kind': kind, 'mat': kp['mat'], 'rim': nb,
                    'paint': [(CHANNELS.index(c), m) for c, m in kp['paint']],
                    'tint': [(CHANNELS.index(c), col, w) for c, col, w in kp['tint']],
                    'ink': kp['ink'], **({'closed': closed} if closed else {}),
                    'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]})
        print(f'[trace] {name}: {len(T)} triangles, R {R * 100:.1f} cm, top {top * 1000:.1f} mm', flush=True)
    seen = cv2.erode(u8(pieces > 0), disk(4)).astype(bool)   # which piece the art's view sees: as the art has it?
    for pid, n in enumerate(names, 1):
        own = seen & (pieces == pid)
        wrong = own & (zid != pid) & (zid > 0)
        if wrong.sum() > 50:
            ys, xs = np.nonzero(wrong)
            print(f'[check] {n}: {int(wrong.sum())} px show ' + ', '.join(f'{names[j - 1]} {int((zid[wrong] == j).sum())}'
                  for j in np.unique(zid[wrong])) + f' (around {int(xs.mean())},{int(ys.mean())})', flush=True)
    # the art's own colours over the food, its ink lines and glints taken out (meat_fish.art_colours tints them in)
    hsv2 = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL)
    food = pieces > 0
    clean = food & (hsv2[..., 2] > 0.55 * 255) & (paint[..., CHANNELS.index('glint')] < 64)
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
        tracing_sheet(sheet, rgba, pieces, names, [tints[k] for _, k, _ in PIECES], crop=(120, 230, 1200, 1010),
                      title=('原图上的描线（蓝：每一块）', f'描出的 {pieces.max()} 块：身子、远翅、两腿、近翅三段'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
