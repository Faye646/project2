"""Traces 瓜齑萝卜's art (新建文件夹/瓜齑萝卜.png) for D04, so that its heap of julienned radish and cucumber is modelled
1:1 (勾勒): writes food_models/traced_D04.json and the colours of its pieces (traced_D04_paint.npz), which
bowls.guaji_luobo builds the food from, and a tracing sheet.

    python WhiteModel/trace_d04.py [--sheet <out.png>]

1. The art's camera: fitted together with the bowl guaji_luobo builds (eight lobes, a broad foot, a flared wall;
   IoU 0.97 by the bowl's outline); the bowl and the dressing in it built by Blender with guaji_luobo's own
   round_bowl. The heap is inside the lip.
2. The strips, found in the art itself: the cucumber where it is green, the radish the cream round it (the gold of
   the dressing between them left out), each cut into its strips along the art's creases (a watershed on its
   shading from each strip's bright middle, split) and grown back over all of it (grow), so that the strips pack
   the heap as the art paints them, each two meeting along the line between them.
3. Their colours: the cucumber's dark green skin along an edge (painted on, the mesh has vertices along it), its
   pale seedy middle; the radish's translucent shadows and its glints (tinted in softly).
4. Each strip a rounded bar over its outline lying on the heap (a mound rising from the dressing, kept inside the
   bowl's wall), so that from the art's camera it covers exactly what the art paints, its shading as relief; under
   them the heap itself, in the dressing's gold, where a gap between strips shows.
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

from trace_common import (Camera, contour_points, dish_mesh, disk, fill_holes, grow, largest, lying, neighbours,
                          outline_mesh, paint_channels, profile, raster, shading_band, smooth_inner, split,
                          tracing_sheet, u8)

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '瓜齑萝卜.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D04.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D04_paint.npz')

CAM = Camera(34.38, 6646.7, 625.4, 907.7)
FILL_Z = 0.036
RIM_R, H, T = 0.085, 0.0534, 0.0052
BOWL = ("round_bowl(tmp, rim_r=0.085, h=0.0534, foot_r=0.0485, foot_h=0.0209, fill_z=0.036, fill='GuajiDressing', "
        "n=40, light=True, flare=(24.0, 81.4, 0.412), t=0.0052, deform=scalloped(8, 0.089, 0.06, 0.086))")
HEAP = (0.0, 0.006, 0.072, 0.026)
# the cucumber strips, read off the art by eye: each from end to end along its middle (art px), and how wide
CUCUMBER = [((398, 435), (522, 412), 45), ((642, 352), (872, 668), 56), ((800, 483), (932, 491), 46),
            ((765, 437), (820, 430), 34), ((206, 678), (358, 492), 42), ((397, 602), (402, 515), 55),
            ((940, 535), (1000, 572), 34), ((595, 590), (892, 686), 46), ((922, 617), (1050, 741), 48),
            ((668, 711), (772, 719), 58), ((355, 757), (715, 885), 60), ((732, 747), (907, 823), 50),
            ((143, 690), (178, 677), 30), ((297, 726), (344, 694), 27)]   # the heap: its middle (x, y), how far it spreads, how high over the dressing
CHANNELS = ['skin', 'pale', 'shade', 'light']
KINDS = {
    'radish': dict(gap=0.0056, gb=0.003, ring=0.0005, puff=0.4, top=0.0024, edge=-0.002, relief=0.0004,
                   mat='GuajiRadish', paint=[], tint=[('shade', '#e2c894', 0.75), ('light', '#fffaee', 0.7)],
                   ink=[0.0, 0.0]),
    'cucumber': dict(gap=0.0056, gb=0.003, ring=0.0005, puff=0.4, top=0.0026, edge=-0.002, relief=0.0004,
                     mat='GuajiCucumber', paint=[('skin', 'GuajiCucumberSkin')],
                     tint=[('pale', '#eeeab4', 0.6), ('shade', '#a8a040', 0.5)], ink=[0.3, 1.5]),
}


def bowl_views(Hh, Ww):
    """The bowl as the art's camera sees it: depths, and which part shows at each pixel: 0 the dressing, 1 the
    inside of the wall, 2 the outside and the lip."""
    V, Tr = dish_mesh('from food_models.bowls import round_bowl, scalloped\ntmp = p\n' + BOWL)
    P = V[Tr]
    n = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    c = P.mean(1)
    radial = (n[:, 0] * c[:, 0] + n[:, 1] * c[:, 1]) / np.maximum(np.linalg.norm(n, axis=1) * np.hypot(c[:, 0], c[:, 1]),
                                                                   1e-12)
    ids = np.where(np.abs(c[:, 2] - FILL_Z) < 0.0008, 0, np.where(radial < -0.25, 1, 2))
    zb, zid = np.full((Hh, Ww), np.inf), np.full((Hh, Ww), -1, np.int32)
    u, v = CAM.project(V[:, 0], V[:, 1], V[:, 2])
    raster(np.stack([u, v], -1)[Tr], CAM.depth(V)[Tr], ids, Hh, Ww, zb, zid)
    return zb, zid


def wall_r(z):
    """The bowl's inside radius at height z (roughly: the flared wall, lobes aside), for keeping the heap in."""
    return 0.0505 + (RIM_R - T - 0.0505) * np.clip((z - 0.022) / (H - 0.022), 0, 1) ** 0.6


def base(x, y):
    """The heap the strips lie on: a mound over the dressing, rising up the bowl's wall at its edge."""
    cx, cy, R0, hz = HEAP
    d = np.hypot(x - cx, y - cy)
    mound = FILL_Z + hz * np.clip(1 - (d / R0) ** 2, 0, 1) ** 0.7
    r = np.hypot(x, y)
    wall = np.where(r > wall_r(FILL_Z) - 0.004, FILL_Z + (r - wall_r(FILL_Z) + 0.004) * 2.5, FILL_Z)
    return np.maximum(mound, np.minimum(wall, H))


def pieces_of(rgb, food):
    """The strips: the cucumber where the art is green, the radish the cream round it, each cut along the art's
    creases into its strips and grown back over all of it."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.5), cv2.COLOR_RGB2LAB).astype(np.float32)
    a, b = lab[..., 1] - 128, lab[..., 2] - 128
    skin = (v < 0.62) & (h > 55) & (h < 140) & (s > 0.35)
    green = food & (((a < -4) & (b >= 22)) | skin)   # the cucumber: yellow-green flesh, dark green skin
    green = cv2.morphologyEx(u8(green), cv2.MORPH_CLOSE, disk(2))
    green = cv2.morphologyEx(green, cv2.MORPH_OPEN, disk(3)).astype(bool) & food
    dressing = food & ~green & (b > 32) & (v < 0.93)   # the gold of the dressing, and the warm shadows between
    dressing = cv2.morphologyEx(u8(dressing), cv2.MORPH_OPEN, disk(2)).astype(bool)
    radish = food & ~green & ~dressing
    radish = cv2.morphologyEx(u8(radish), cv2.MORPH_OPEN, disk(3)).astype(bool)
    out = np.zeros(food.shape, np.int32)
    kinds = []
    for kind, m, amin, amax in (('cucumber', green, 1200, 20000), ('radish', radish, 1200, 9000)):
        lab_ = split(m, lum, sig=3.0, tau=10.0, amin=amin, amax=amax, marker_r=7)
        lab_ = grow(lab_, m, lum, sig=3.0)
        for i in range(1, lab_.max() + 1):   # each strip one clean shape
            mm = cv2.morphologyEx(u8(lab_ == i), cv2.MORPH_OPEN, disk(4))
            mm = largest(cv2.morphologyEx(mm, cv2.MORPH_CLOSE, disk(3))) & m
            if mm.sum() < 250:
                continue
            kinds.append(kind)
            out[mm & (out == 0)] = len(kinds)
    return out, kinds, green, dressing


def as_bars(pieces, kinds, food, green):
    """Each strip as the art draws it, a straight bar with clean sides and rounded cut ends: the rectangle that
    best holds what the art shows of it, the pieces of one strip that another crosses joined again into one bar (in
    line, the same way, the gap between them covered), strips whose shape is no bar (two run together) kept as found;
    the bars stacked as the art has them (where two cross, the one the art shows there is on top), each pixel the
    topmost bar's."""
    Hh, Ww = pieces.shape
    frags, keep = [], []
    for pid in range(1, pieces.max() + 1):
        m = pieces == pid
        a = int(m.sum())
        if a < 250 or kinds[pid - 1] == 'cucumber':   # the cucumber is traced by hand (CUCUMBER)
            continue
        (cx, cy), (rw, rh), ang = cv2.minAreaRect(np.stack(np.nonzero(m)[::-1], -1).astype(np.float32))
        if rw < rh:
            rw, rh, ang = rh, rw, ang + 90
        if a < 0.55 * rw * rh or rw < 1.6 * rh:
            keep.append(pid)   # not a bar: as found
            continue
        th = math.radians(ang)
        d = np.array([math.cos(th), math.sin(th)])
        c = np.array([cx, cy])
        frags.append({'kind': kinds[pid - 1], 'ids': [pid], 'c': c, 'd': d, 'lo': -rw / 2, 'hi': rw / 2,
                      'w': min(rh, a / rw * 1.05), 'area': a})
    merged = True
    while merged:   # join pieces of one strip
        merged = False
        for i in range(len(frags)):
            for j in range(i + 1, len(frags)):
                A, B = frags[i], frags[j]
                if A['kind'] != B['kind'] or abs(A['d'] @ B['d']) < math.cos(math.radians(11)):
                    continue
                dB = B['d'] if A['d'] @ B['d'] > 0 else -B['d']
                off = B['c'] - A['c']
                perp = abs(off @ np.array([-A['d'][1], A['d'][0]]))
                if perp > 0.55 * max(A['w'], B['w']):
                    continue
                t0, t1 = off @ A['d'] + B['lo'] * (dB @ A['d']), off @ A['d'] + B['hi'] * (dB @ A['d'])
                b_lo, b_hi = min(t0, t1), max(t0, t1)
                gap = max(b_lo - A['hi'], A['lo'] - b_hi)
                if gap > 70:
                    continue
                wa, wb = A['area'], B['area']
                d = (A['d'] * wa + dB * wb) / (wa + wb)
                d /= np.linalg.norm(d)
                ends = [A['c'] + A['d'] * A['lo'], A['c'] + A['d'] * A['hi'], B['c'] + B['d'] * B['lo'],
                        B['c'] + B['d'] * B['hi']]
                c = (A['c'] * wa + B['c'] * wb) / (wa + wb)
                ts = [(e - c) @ d for e in ends]
                frags[i] = {'kind': A['kind'], 'ids': A['ids'] + B['ids'], 'c': c, 'd': d, 'lo': min(ts),
                            'hi': max(ts), 'w': (A['w'] * wa + B['w'] * wb) / (wa + wb), 'area': wa + wb}
                del frags[j]
                merged = True
                break
            if merged:
                break
    for p0, p1, w in CUCUMBER:
        p0, p1 = np.array(p0, float), np.array(p1, float)
        L_ = np.linalg.norm(p1 - p0)
        frags.append({'kind': 'cucumber', 'ids': [], 'c': (p0 + p1) / 2, 'd': (p1 - p0) / L_, 'lo': -L_ / 2,
                      'hi': L_ / 2, 'w': w, 'area': L_ * w})
    bars = []
    for f in frags:
        cnv = np.zeros((Hh, Ww), np.uint8)   # a rounded rectangle, its ends round as a cut strip's
        L_ = f['hi'] - f['lo']
        c = f['c'] + f['d'] * (f['hi'] + f['lo']) / 2
        ang = math.degrees(math.atan2(f['d'][1], f['d'][0]))
        w = f['w'] * 1.2 if f['ids'] else f['w'] * 1.1   # a little wider: neighbours meet under the top one
        r = w * 0.25
        for size in ((L_ - 2 * r, w), (L_, w - 2 * r)):
            box = cv2.boxPoints(((c[0], c[1]), size, ang)).astype(np.float32)
            cv2.fillPoly(cnv, [np.round(box * 4).astype(np.int32)], 1, shift=2)
        n_ = np.array([-f['d'][1], f['d'][0]])
        for sx in (-1, 1):
            for sy in (-1, 1):
                q = c + sx * (L_ / 2 - r) * f['d'] + sy * (w / 2 - r) * n_
                cv2.circle(cnv, (int(round(q[0] * 4)), int(round(q[1] * 4))), int(round(r * 4)), 1, -1, shift=2)
        bars.append((f['ids'], cnv.astype(bool) & food, f['kind']))
    shows = [(np.isin(pieces, ids) if ids else green) for ids, _, _ in bars]   # where the art shows each
    n = len(bars)
    above = np.zeros((n, n), int)
    for i in range(n):
        for j in range(i + 1, n):
            ov = bars[i][1] & bars[j][1]
            if ov.sum() < 30:
                continue
            ci, cj = int(shows[i][ov].sum()), int(shows[j][ov].sum())
            above[i, j], above[j, i] = (1, 0) if ci >= cj else (0, 1)
    order = sorted(range(n), key=lambda i: above[i].sum())   # the fewest above others first (lowest)
    out = np.zeros((Hh, Ww), np.int32)
    new_kinds = []
    for k in keep:
        if kinds[k - 1] == 'cucumber':
            continue
        new_kinds.append(kinds[k - 1])
        out[pieces == k] = len(new_kinds)
    kept = out > 0
    for i in order:
        new_kinds.append(bars[i][2])
        out[bars[i][1] & ~kept] = len(new_kinds)
    ids = sorted(set(np.unique(out)) - {0})
    remap = np.zeros(len(new_kinds) + 1, np.int32)
    remap[ids] = np.arange(1, len(ids) + 1)
    return remap[out], [new_kinds[i - 1] for i in ids]


def classes(rgb, pieces, kinds):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    kind_of = np.array(['none'] + kinds)[pieces]
    cuc, rad = kind_of == 'cucumber', kind_of == 'radish'
    food = pieces > 0
    skin = cuc & (v < 0.68) & (s > 0.45)   # the dark green skin
    skin = cv2.morphologyEx(u8(skin), cv2.MORPH_CLOSE, disk(2)).astype(bool) & cuc
    pale = cuc & (v > 0.85) & (s < 0.35)  # the pale seedy middle
    lb = cv2.GaussianBlur(lum, (0, 0), 2.0)
    mean = cv2.GaussianBlur(lum * food, (0, 0), 10) / np.maximum(cv2.GaussianBlur(food.astype(np.float32), (0, 0), 10),
                                                                  1e-3)
    shade = np.where(rad, np.clip((236.0 - lb) / 40.0, 0, 1), np.where(cuc, np.clip((mean - lb) / 30.0, 0, 1), 0))
    light = np.where(food, np.clip((lb - mean - 5) / 12.0, 0, 1) * (s < 0.2), 0)
    a = paint_channels([skin], food, smooth=1.2, min_area=40, close=2)
    b = paint_channels([pale], food, smooth=2.0, min_area=80, close=2)
    c = np.stack([cv2.GaussianBlur(x.astype(np.float32), (0, 0), 1.5) for x in (shade, light)], -1)
    return np.concatenate([a, b, np.clip(c * 255 + 0.5, 0, 255).astype(np.uint8)], -1)


def surface(name, kind, mk, paint, lum):
    Hh, Ww = mk.shape
    kp = KINDS[kind]
    edges = [(paint[..., CHANNELS.index(c)] > 127) & mk for c, _ in kp['paint']]
    extra = contour_points(edges, 6.0) if edges else None
    uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, kp['gap'], kp['gb'], kp['ring'], smooth_px=4.0, extra=extra,
                                            extra_margin=kp['ring'] * CAM.k + 1.0)   # the skin along the edge
    band = shading_band(lum, mk, 2.0, 10.0)
    iy = np.clip(np.round(uv[:, 1]).astype(int), 0, Hh - 1)
    ix = np.clip(np.round(uv[:, 0]).astype(int), 0, Ww - 1)
    top = float(np.clip(kp['puff'] * R, 0.0008, kp['top']))
    L = profile(d, R, top, 0.0, 0.0, lean, 0.0)
    L = kp['edge'] + (top - kp['edge']) * np.clip(L / top, 0, 1) ** 0.45   # a stick's flat top, its sides rounded
    L = L + kp['relief'] * band[iy, ix] * np.clip(d / max(0.3 * R, 1e-6), 0, 1)
    L = smooth_inner(L, nb, neighbours(len(uv), tris))
    P, Tr = lying(CAM, uv, tris, nb, L, base)
    return {'name': name, 'kind': kind, 'mat': kp['mat'], 'rim': nb,
            'paint': [(CHANNELS.index(c), m) for c, m in kp['paint']],
            'tint': [(CHANNELS.index(c), col, w) for c, col, w in kp['tint']],
            'ink': kp['ink'], 'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in Tr]}


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    Hh, Ww = alpha.shape
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    zb, zid = bowl_views(Hh, Ww)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.5), cv2.COLOR_RGB2LAB).astype(np.float32)
    celadon = (lab[..., 1] - 128 < -3) & (lab[..., 2] - 128 < 22) & (lab[..., 0] > 140)   # the bowl's pale green
    inside = (zid == 0) | (zid == 1)
    food = inside & (alpha > 128) & ~cv2.morphologyEx(u8(celadon), cv2.MORPH_OPEN, disk(3)).astype(bool)
    food = cv2.morphologyEx(u8(food), cv2.MORPH_OPEN, disk(2)).astype(bool)
    food = largest(cv2.morphologyEx(u8(food), cv2.MORPH_CLOSE, disk(3)))
    pieces, kinds, green, dressing = pieces_of(rgb, food)
    pieces, kinds = as_bars(pieces, kinds, food, green)
    for _ in range(4):   # the strips grown over what is left of them in the art (not the dressing's gold gaps)
        free = food & (pieces == 0) & ~dressing
        grown = cv2.dilate(pieces.astype(np.float32), disk(2)).astype(np.int32)
        pieces[free & (grown > 0)] = grown[free & (grown > 0)]
    names = [f'{k[0].upper()}{i}' for i, k in enumerate(kinds, 1)]
    paint = classes(rgb, pieces, kinds)
    print(f'[trace] D04: strips cover {(pieces > 0).sum() / food.sum():.2f} of the food', flush=True)
    np.save(os.path.join(HERE, '..', 's', 'd04', 'final_pieces.npy'), pieces)
    out = []
    n_tris = {}
    heap_mk = fill_holes(food & ~dressing)
    heap_mk = largest(cv2.morphologyEx(u8(heap_mk), cv2.MORPH_OPEN, disk(4)))
    uv, tris, nb, d, R, lean = outline_mesh(CAM, cv2.erode(u8(heap_mk), disk(3)).astype(bool), 0.015, 0.007, 0.0006,
                                            smooth_px=4.0)
    P, Tr = lying(CAM, uv, tris, nb, np.full(len(uv), -0.0012), base,
                  close=lambda x, y: np.full_like(x, FILL_Z + 0.0003))   # closed under it: no back face shows
    foot = P[len(uv):]   # its skirt's feet kept inside the bowl (the lines of sight at the back go out through it)
    r = np.hypot(foot[:, 0], foot[:, 1])
    k = np.minimum(1.0, 0.063 / np.maximum(r, 1e-9))
    P[len(uv):, 0], P[len(uv):, 1] = foot[:, 0] * k, foot[:, 1] * k
    out.append({'name': 'heap', 'kind': 'heap', 'mat': 'GuajiHeap', 'rim': nb, 'paint': [], 'tint': [],
                'ink': [0.0, 0.0], 'closed': len(uv),
                'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in Tr]})
    n_tris['heap'] = len(Tr)
    for pid, (name, kind) in enumerate(zip(names, kinds), 1):
        m = pieces == pid
        mk = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 1.2) > 0.5
        if mk.sum() < 250:
            continue
        pc = surface(name, kind, mk, paint, lum)
        out.append(pc)
        n_tris[kind] = n_tris.get(kind, 0) + len(pc['tris'])
    print(f'[trace] D04: {len(out) - 1} strips ({kinds.count("radish")} radish, {kinds.count("cucumber")} cucumber); '
          f'triangles {n_tris}, all {sum(n_tris.values())}', flush=True)
    np.savez_compressed(PAINT, paint=paint[::2, ::2])
    data = {'camera': {'el': CAM.el, 'k': CAM.k, 'u0': CAM.u0, 'v0': CAM.v0}, 'paint_scale': 0.5,
            'channels': CHANNELS, 'fill_z': FILL_Z, 'pieces': out, 'bits': []}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT}', flush=True)
    if sheet:
        tints = {'radish': (250, 246, 232), 'cucumber': (150, 200, 90)}
        tracing_sheet(sheet, rgba, pieces, names, [tints[k] for k in kinds], crop=(60, 280, 1200, 980),
                      title=('原图上的描线（蓝：每一条）', f'描出的 {kinds.count("radish")} 条萝卜丝、{kinds.count("cucumber")} 条瓜条'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
