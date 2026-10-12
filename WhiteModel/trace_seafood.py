"""Traces 干贝海味包's art (新建文件夹/干贝海味包.png) so that the dried scallops and shrimp heaped in its paper bag are
modelled 1:1 (勾勒): writes food_models/traced_seafood.json and its colours (_paint.npz), which sacks.seafood builds the
item from, and a tracing sheet.

    python WhiteModel/trace_seafood.py [--sheet <out.png>]

1. The art's camera, at the icons' 35°, fitted so that the item built before covered the art's silhouette best
   (IoU 0.959); the bag and the heap closing it (sacks.seafood_bag, built by Blender) for what the pieces lie on.
2. The pieces: a flood of the art seeded by strokes inside each scallop and shrimp (read off the art by eye) and on
   the paper round them, the art's ink lines walls.
3. Each a solid over its outline lying on the heap: a scallop a squat drum, flat on top, steep down its sides; a
   shrimp round across like a tube; each closed down to the heap. Their colours the art's own (the colour map), the
   scallops' pale tops painted on; the paper's colours from the art too, its creases and folds as the art paints them.
"""
import sys

import cv2
import numpy as np

from trace_common import Camera, contour_points, dish_mesh, disk, lying, neighbours, profile, seeded_pieces, \
    shading_band, smooth_inner, u8
from trace_packs import Art, colour_map, mean_colour, piece_mesh, piece_record, sheet, write, zbuffer

ART = '干贝海味包.png'
CAM = Camera(35.0, 3639.3, 649.9, 944.2)
BAG = "from food_models.sacks import seafood_bag\nseafood_bag(p)"
SCALLOPS = {
    'S1': [(560, 250), (680, 262), (620, 340), (540, 330), (740, 300), (760, 360)],
    'S2': [(400, 470), (520, 450), (600, 500), (500, 560), (430, 540)],
    'S3': [(700, 480), (760, 510), (720, 540)],
    'S4': [(850, 520), (950, 540), (900, 620), (1000, 600)],
    'S5': [(560, 650), (640, 660)],
    'S6': [(360, 360), (430, 372)],
}
SHRIMP = {
    'P1': [(260, 560), (250, 500), (280, 440), (340, 412), (400, 402)],
    'P2': [(820, 302), (900, 312), (950, 360), (960, 430), (900, 452)],
    'P3': [(650, 597), (720, 602), (790, 640), (800, 700)],
    'P4': [(1030, 480), (1040, 530)],
}
PAPER = [[(230, 262), (300, 282)], [(200, 625), (300, 655)], [(450, 722), (550, 732)], [(900, 705), (1000, 695)],
         [(1085, 400), (1090, 360)], [(452, 232), (470, 222)], [(805, 250), (850, 222)], [(150, 500), (160, 600)],
         [(700, 160), (800, 175)], [(1100, 600), (1120, 650)]]
CHANNELS = ['top']


def main():
    art = Art(ART)
    H, W = art.H, art.W
    V, T = dish_mesh(BAG)
    zb, _ = zbuffer(CAM, V, T, H, W)
    names = list(SCALLOPS) + list(SHRIMP)
    strokes = {i + 1: st for i, st in enumerate(list(SCALLOPS.values()) + list(SHRIMP.values()))}
    edge = art.alpha & ~cv2.erode(u8(art.alpha), disk(40)).astype(bool)
    zone = art.alpha & ~edge                     # the bag's outside edge is paper
    labels = seeded_pieces(art.rgb, zone, strokes, PAPER)
    items = labels > 0
    scal = np.isin(labels, range(1, len(SCALLOPS) + 1))
    lum_s = cv2.GaussianBlur(art.lum, (0, 0), 4.0)
    top = scal & (lum_s > 182) & (cv2.GaussianBlur(art.s, (0, 0), 4.0) < 0.8)   # the pale cut tops
    top = cv2.morphologyEx(u8(top), cv2.MORPH_OPEN, disk(3))
    top = cv2.morphologyEx(top, cv2.MORPH_CLOSE, disk(4)).astype(bool)
    nn, cc, st, _ = cv2.connectedComponentsWithStats(u8(top))
    keep = np.zeros(nn, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 600
    top = keep[cc]
    paint = np.clip(cv2.GaussianBlur(top.astype(np.float32), (0, 0), 1.5) * 255 + 0.5, 0, 255).astype(np.uint8)[..., None]
    paper = art.alpha & ~items
    colour = np.maximum(colour_map(art, [items], flatten=0.3, sigma=40, ink=0.3),
                        colour_map(art, [paper], flatten=0.55, sigma=45, ink=0.35) * (~items)[..., None])
    print('[trace] colours: scallop side', mean_colour(art, scal & ~top), 'top', mean_colour(art, top),
          'shrimp', mean_colour(art, items & ~scal), 'paper', mean_colour(art, paper & (art.v > 0.5)), flush=True)
    heap = lambda u, v: None
    # the heap the pieces lie on: what the bag's model shows there (its heap, or its paper where a piece runs over it)
    s_floor = float(np.nanmin(zb[np.isfinite(zb)]))
    pieces = []
    lab = np.zeros((H, W), np.int32)
    for k, name in enumerate(names, 1):
        m = labels == k
        if m.sum() < 800:
            continue
        is_s = name.startswith('S')
        extra = contour_points([top & m], 16.0) if is_s else None
        mk, uv, tris, nb, d, R, lean = piece_mesh(CAM, m, 0.015 if is_s else 0.011, 0.005, ring=0.0007,
                                                  smooth_px=3.0, extra=extra, margin=2.5)
        iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
        ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
        band = shading_band(art.lum, mk, 2.5, 12.0)[iy, ix]
        if is_s:   # a squat drum: flat on top (its pale top and all behind it), its side falling to its foot in front
            tm = top & mk
            yb = np.where(mk.any(0), H - 1 - np.argmax(mk[::-1], 0), 0).astype(float)
            yf = np.where(mk.any(0), np.argmax(mk, 0), 0).astype(float)
            yt = np.where(tm.any(0), H - 1 - np.argmax(tm[::-1], 0), yb - 0.4 * (yb - yf)).astype(float)
            cols = mk.any(0) & tm.any(0)
            hgt = float(np.clip(np.median((yb - yt)[cols]) / (CAM.k * CAM.ce) if cols.any() else 0.02, 0.012, 0.032))
            tt = np.clip((yb[ix] - uv[:, 1]) / np.maximum(yb[ix] - yt[ix], 4.0), 0, 1)
            L = 0.001 + hgt * tt ** 0.8 + 0.0012 * band * (tt > 0.98) + 0.0015 * np.clip(d / (0.2 * R), 0, 1) * (tt > 0.98)
        else:      # round across, like a tube
            L = profile(d, R, float(np.clip(0.8 * R, 0.004, 0.012)), 0.0008, 0.0, lean, 0.0015, band)
        L = smooth_inner(L, nb, neighbours(len(uv), tris))
        # what it lies on: the heap under it, read from the bag's depths along each ray (a height field from them)
        from trace_common import Grid
        P0 = CAM.on_ray(uv[:, 0], uv[:, 1], np.where(np.isfinite(zb[iy, ix]), zb[iy, ix], s_floor))
        zmin = float(np.percentile(P0[:, 2], 20))
        base = lambda x, y, z=zmin: np.full_like(np.asarray(x, float), z)
        P, Tt = lying(CAM, uv, tris, nb, L, base, close=lambda x, y, z=zmin: np.full_like(np.asarray(x, float), z - 0.004))
        pieces.append(piece_record(name, 'scallop' if is_s else 'shrimp', 'HaiScallop' if is_s else 'HaiShrimp', nb,
                                   P, Tt, paint=[(0, 'HaiScallopTop')] if is_s else [], ink=(1.8, 3.0), tint=0.85,
                                   extra={'closed': len(uv),
                                          'tint_mats': ['HaiScallop', 'HaiScallopTop'] if is_s else ['HaiShrimp']}))
        lab[mk & (lab == 0)] = len(pieces)
    print(f'[trace] {len(pieces)} pieces, {sum(len(p["tris"]) for p in pieces)} triangles', flush=True)
    write('seafood', CAM, pieces, paint, colour, CHANNELS)
    if '--sheet' in sys.argv:
        sheet(sys.argv[sys.argv.index('--sheet') + 1], art, lab, [p['name'] for p in pieces],
              ('原图上的描线（蓝：每一块）', f'描出的 {len(pieces)} 块：干贝、虾'), crop=(100, 120, 1200, 800))


if __name__ == '__main__':
    main()
