"""Traces 盐渍辅料包's art (新建文件夹/盐渍辅料包.png) so that the salted pickles heaped in its paper parcel are
modelled 1:1 (勾勒): writes food_models/traced_pickle_base.json and its colours (_paint.npz), which sacks.pickle_base
builds the item from, and a tracing sheet.

    python WhiteModel/trace_pickle_base.py [--sheet <out.png>]

1. The art's camera, at the icons' 35°, fitted so that the item built before covered the art's silhouette best
   (IoU 0.970); the parcel and the heap closing it (sacks.pickle_bag, built by Blender) for what the pickles lie on.
2. The heap of pickles: a flood of the art seeded by strokes inside it and on the paper round it (read off the art
   by eye), the art's ink lines walls.
3. One mound over its outline lying in the parcel, the art's shading in relief (the shreds raised, the gaps between
   them sunk), closed down to the heap under it; the pale shreds painted on where the art has them (vertices along
   their edges), over the dark leaves; its colours the art's own. The coarse salt: each white cluster of the art a
   crystal on the mound.
"""
import sys

import cv2
import numpy as np

from trace_common import Camera, contour_points, dish_mesh, disk, lying, neighbours, profile, raster, seeded_pieces, \
    shading_band, smooth_inner, u8
from trace_packs import Art, closed_over, colour_map, depth_at, mean_colour, piece_mesh, piece_record, sheet, write, \
    zbuffer

ART = '盐渍辅料包.png'
CAM = Camera(35.0, 3583.0, 647.5, 957.0)
BAG = "from food_models.sacks import pickle_bag\npickle_bag(p)"
HEAP = [[(400, 450), (500, 400), (600, 350), (700, 330), (800, 350), (900, 420), (950, 500), (900, 600), (800, 650),
         (650, 650), (500, 620), (380, 560), (600, 500), (750, 500)], [(320, 520), (350, 600)], [(980, 560), (1000, 600)]]
PAPER = [[(350, 250), (500, 228), (650, 200), (800, 228), (950, 268)], [(230, 450), (255, 560)],
         [(350, 722), (500, 762), (700, 772), (900, 742)], [(1065, 450), (1068, 600)], [(150, 420), (100, 450)],
         [(1080, 330), (1120, 380)]]
CHANNELS = ['shred']


def main():
    art = Art(ART)
    H, W = art.H, art.W
    V, T = dish_mesh(BAG)
    zb, _ = zbuffer(CAM, V, T, H, W)
    edge = art.alpha & ~cv2.erode(u8(art.alpha), disk(40)).astype(bool)
    labels = seeded_pieces(art.rgb, art.alpha & ~edge, {1: HEAP[0], 2: HEAP[1], 3: HEAP[2]}, PAPER)
    heap = labels > 0
    salt = heap & (art.s < 0.16) & (art.v > 0.88)
    salt = cv2.morphologyEx(u8(salt), cv2.MORPH_CLOSE, disk(2)).astype(bool)
    shred = heap & (art.h > 38) & (art.h < 60) & (art.s > 0.25) & (art.s < 0.62) & (art.v > 0.84)
    shred = cv2.morphologyEx(u8(shred | salt), cv2.MORPH_CLOSE, disk(3))
    shred = cv2.morphologyEx(shred, cv2.MORPH_OPEN, disk(3)).astype(bool) & heap
    nn, cc, st, _ = cv2.connectedComponentsWithStats(u8(shred))
    keep = np.zeros(nn, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 300
    shred = keep[cc]
    paint = np.clip(cv2.GaussianBlur(shred.astype(np.float32), (0, 0), 1.5) * 255 + 0.5, 0, 255).astype(np.uint8)[..., None]
    paper = art.alpha & ~heap
    clean = cv2.inpaint(art.rgb, u8(cv2.dilate(u8(salt), disk(2))), 5, cv2.INPAINT_TELEA)   # the salt is its own
    art2 = Art.__new__(Art)
    art2.__dict__.update(art.__dict__)
    art2.rgb = clean
    colour = np.maximum(colour_map(art2, [heap], flatten=0.2, sigma=40, ink=0.3),
                        colour_map(art, [paper], flatten=0.55, sigma=45, ink=0.35) * (~heap)[..., None])
    print('[trace] colours: shred', mean_colour(art, shred & ~salt), 'leaf', mean_colour(art, heap & ~shred & ~salt),
          'paper', mean_colour(art, paper & (art.v > 0.5)), flush=True)
    extra = contour_points([shred], 13.0)
    mk, uv, tris, nb, d, R, lean = piece_mesh(CAM, heap, 0.014, 0.0045, ring=0.0007, smooth_px=3.0, extra=extra,
                                              margin=2.5)
    iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
    ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
    band = shading_band(art.lum, mk, 2.5, 14.0)[iy, ix]
    sh = (paint[iy, ix, 0] > 127).astype(float)
    L = profile(d, R, 0.008, 0.001, 0.0, lean, 0.003, band) + 0.0025 * sh
    L = smooth_inner(L, nb, neighbours(len(uv), tris), passes=1)
    s_floor = float(np.nanmin(zb[np.isfinite(zb)]))
    s0 = depth_at(zb, uv, s_floor, r=3)        # on the heap that closes the parcel, a thin shell over it
    P, Tt = closed_over(CAM, uv, tris, nb, L, s0, back=0.0008)
    pieces = [piece_record('heap', 'heap', 'YanLeaf', nb, P, Tt, paint=[(0, 'YanShred')], ink=(1.0, 2.5), tint=0.85,
                           extra={'tint_mats': ['YanLeaf']})]
    # the salt: each white cluster a crystal lying on the mound
    zbh, _ = zbuffer(CAM, P, np.array([t for t in Tt if max(t) < len(uv)]), H, W)
    n2, cc2, st2, cen = cv2.connectedComponentsWithStats(u8(salt))
    order = np.argsort(-st2[1:, cv2.CC_STAT_AREA])[:12] + 1
    crystals = []
    rng = np.random.default_rng(5)
    for j in order:
        a = st2[j, cv2.CC_STAT_AREA]
        if a < 40:
            continue
        u, v = cen[j]
        size = float(np.clip(np.sqrt(a) / CAM.k * 1.1, 0.005, 0.012))
        s0 = zbh[int(v), int(u)]
        if not np.isfinite(s0):
            continue
        c = CAM.on_ray(np.array([u]), np.array([v]), np.array([s0 - size * 0.3]))[0]
        crystals.append([np.round(c, 5).tolist(), round(size, 5), round(float(rng.uniform(0, 1.5)), 3)])
    print(f'[trace] heap {len(Tt)} triangles, {len(crystals)} salt crystals', flush=True)
    write('pickle_base', CAM, pieces, paint, colour, CHANNELS, extra={'salt': crystals})
    if '--sheet' in sys.argv:
        lab = np.where(shred, 2, np.where(heap, 1, 0))
        lab[salt] = 3
        sheet(sys.argv[sys.argv.index('--sheet') + 1], art, lab, ['leaf', 'shred', 'salt'],
              ('原图上的描线（蓝：咸菜堆、菜梗、盐粒）', '描出的：一堆咸菜（深绿叶上铺着浅黄菜梗）、粗盐粒'),
              crop=(150, 150, 1150, 850))


if __name__ == '__main__':
    main()
