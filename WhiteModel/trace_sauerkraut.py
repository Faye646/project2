"""Traces 酸菜's art (新建文件夹/酸菜.png) so that the pickled cabbage packed in its crock and the big leaf hanging over
the rim are modelled 1:1 (勾勒): writes food_models/traced_sauerkraut.json and its colours (_paint.npz), which
jars.sauerkraut builds the item from, and a tracing sheet.

    python WhiteModel/trace_sauerkraut.py [--sheet <out.png>]

1. The art's camera, at the icons' 35°, fitted so that the item built before covered the art's silhouette best
   (IoU 0.973); the crock turned to the art's outline as before (CROCK, built by Blender for its depths).
2. The cabbage: the art's yellow and olive inside the crock's mouth and over its rim; the big leaf hanging over the
   rim down the right side seeded by strokes along it (read off the art by eye), the rest cut into its leaves along
   the art's creases (split, then grown to the creases between them).
3. Each leaf a surface over its outline: those in the mouth on a low mound of cabbage under them (MOUND), the art's
   folds in relief; the hanging leaf a thin closed shell over the rim and down the crock's wall. Their colours the
   art's own (the colour map: pale yellow, olive, the light on the folds), the dark leaves painted on.
"""
import math
import sys

import cv2
import numpy as np

from trace_common import Camera, contour_points, dish_mesh, disk, grow, neighbours, over, profile, seeded_pieces, \
    shading_band, smooth_inner, split, u8
from trace_packs import Art, closed_over, colour_map, depth_at, mean_colour, piece_mesh, piece_record, sheet, write, \
    zbuffer

ART = '酸菜.png'
CAM = Camera(35.0, 5067.5, 621.8, 945.9)
# the crock turned to the art's outline (its left side; the leaf hangs over the right): radii at heights fitted to the
# art's silhouette (IoU 0.994), its thick rolled lip 2.1 cm across, stretched SY front to back as the art draws it
OUTER = [(0.0438, 0.0), (0.0594, 0.008), (0.0736, 0.02), (0.0874, 0.04), (0.0996, 0.065), (0.0982, 0.085),
         (0.0865, 0.1), (0.0875, 0.112), (0.0868, 0.1236)]
T_WALL, SY = 0.0213, 1.11
LIP = OUTER[-1][1]                     # where the lip meets the inside
FZ = LIP - 0.03                        # the dark cabbage closing the mouth deep down
CROCK = (f"from food_models.jars import vessel" + chr(10) + f"vessel(p, {OUTER!r}, {T_WALL}, {FZ}, ('ClayPot',) * 4, n=40, per=2, "
         f"turn=7, deform=lambda q: Vector((q.x, q.y * {SY}, q.z)))")
RIN = OUTER[-1][0] - T_WALL            # the inside at the lip


def mound(x, y):
    """The cabbage under the leaves: low at the wall (as the art has it at the back), up a little in the middle."""
    r = np.hypot(x, np.asarray(y) / SY)
    return LIP - 0.008 + 0.016 * np.clip(1 - (r / RIN) ** 2, 0, 1)


HANG = {1: [(760, 470), (850, 452), (930, 470), (990, 540), (1040, 620), (1080, 720), (1100, 820), (1100, 880)],
        2: [(1150, 620), (1170, 700), (1160, 780)]}
CHANNELS = ['dark']


def main():
    art = Art(ART)
    H, W = art.H, art.W
    V, T = dish_mesh(CROCK)
    zb_crock, _ = zbuffer(CAM, V, T, H, W)
    t = np.linspace(0, 2 * math.pi, 64, endpoint=False)
    rings = [np.stack([RIN * f * np.cos(t), SY * RIN * f * np.sin(t)], -1) for f in (1.0, 0.8, 0.6, 0.4, 0.2)]
    MV = np.concatenate([np.c_[rg, mound(rg[:, 0], rg[:, 1])] for rg in rings] + [[[0, 0, float(mound(0, 0))]]])
    MT = []
    for i in range(len(rings) - 1):
        for k in range(64):
            a, b, c, d = i * 64 + k, i * 64 + (k + 1) % 64, (i + 1) * 64 + (k + 1) % 64, (i + 1) * 64 + k
            MT += [(a, b, c), (a, c, d)]
    MT += [(4 * 64 + k, 4 * 64 + (k + 1) % 64, 5 * 64) for k in range(64)]
    zb_base, _ = zbuffer(CAM, MV, np.array(MT), H, W, zb=zb_crock.copy(), idb=np.full((H, W), -1, np.int32))
    cab = art.alpha & (art.h > 32) & (art.h < 110)
    cab = cv2.morphologyEx(u8(cab), cv2.MORPH_CLOSE, disk(3)).astype(bool) & art.alpha
    n, cc, st, _ = cv2.connectedComponentsWithStats(u8(cab))
    big = np.zeros(n, bool)
    big[1:] = st[1:, cv2.CC_STAT_AREA] > 3000
    cab = big[cc]
    # (2) the hanging leaf and the rest, then the rest cut into its leaves
    heap_strokes = {3: [(450, 330), (600, 300)], 4: [(350, 470), (450, 520)], 5: [(600, 450), (700, 500)]}
    labels = seeded_pieces(art.rgb, cab, {**HANG, **heap_strokes}, [])
    hang = np.isin(labels, (1, 2))
    rest = cab & ~hang
    parts = split(rest, art.lum, sig=3.0, tau=18.0, amin=2500, amax=40000, marker_r=8)
    parts = grow(parts, rest, art.lum)
    ids = [i for i in np.unique(parts) if i > 0 and (parts == i).sum() > 900]
    print(f'[trace] hanging leaf {hang.sum()} px, {len(ids)} leaves in the mouth', flush=True)
    dark = cab & (art.v < 0.62) & (art.s > 0.5)
    dark = cv2.morphologyEx(u8(dark), cv2.MORPH_OPEN, disk(2))
    dark = cv2.morphologyEx(dark, cv2.MORPH_CLOSE, disk(3)).astype(bool)
    nn, cc2, st2, _ = cv2.connectedComponentsWithStats(u8(dark))
    keep = np.zeros(nn, bool)
    keep[1:] = st2[1:, cv2.CC_STAT_AREA] >= 250
    dark = keep[cc2]
    paint = np.clip(cv2.GaussianBlur(dark.astype(np.float32), (0, 0), 1.2) * 255 + 0.5, 0, 255).astype(np.uint8)[..., None]
    clay = art.alpha & ~cab
    colour = np.maximum(colour_map(art, [cab], flatten=0.15, sigma=40, ink=0.3),
                        colour_map(art, [clay], flatten=0.5, sigma=40, ink=0.3) * (~cab)[..., None])
    print('[trace] colours: pale', mean_colour(art, cab & ~dark), 'dark', mean_colour(art, dark),
          'clay', mean_colour(art, clay & (art.v > 0.35)), flush=True)
    pieces = []
    lab = np.zeros((H, W), np.int32)
    names = []
    for k, i in enumerate(ids, 1):
        m = parts == i
        extra = contour_points([dark & m], 18.0)
        mk, uv, tris, nb, d, Rr, lean = piece_mesh(CAM, m, 0.012, 0.004, ring=0.0006, smooth_px=2.5, extra=extra,
                                                   margin=2.5)
        iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
        ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
        band = shading_band(art.lum, mk, 3.0, 16.0)[iy, ix]
        L = profile(d, Rr, float(np.clip(0.5 * Rr, 0.002, 0.009)), 0.0005, 0.0, lean, 0.004, band)
        L = smooth_inner(L, nb, neighbours(len(uv), tris))
        s0 = depth_at(zb_base, uv, float(np.nanmin(zb_base[np.isfinite(zb_base)])), r=0)
        P, Tt = closed_over(CAM, uv, tris, nb, L, s0, back=0.0004)   # closed: a thin shell over what is under it
        pieces.append(piece_record(f'leaf{k}', 'leaf', 'SauerPale', nb, P, Tt, paint=[(0, 'SauerDark')],
                                   ink=(0.6, 2.2), tint=0.85, extra={'tint_mats': ['SauerPale', 'SauerDark']}))
        lab[mk & (lab == 0)] = k
        names.append(f'leaf{k}')
    # the hanging leaf: a thin closed shell over the rim and the crock's wall
    extra = contour_points([dark & hang], 14.0)
    mk, uv, tris, nb, d, Rr, lean = piece_mesh(CAM, hang, 0.01, 0.0035, ring=0.0007, smooth_px=3.0, extra=extra,
                                               margin=2.5)
    iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
    ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
    band = shading_band(art.lum, mk, 3.0, 18.0)[iy, ix]
    L = profile(d, Rr, 0.006, 0.0012, 0.0, lean, 0.003, band)
    L = smooth_inner(L, nb, neighbours(len(uv), tris))
    s0 = depth_at(zb_base, uv, float(np.nanmin(zb_base[np.isfinite(zb_base)])), r=2)
    P, Tt = closed_over(CAM, uv, tris, nb, L, s0, back=0.001)
    pieces.append(piece_record('hang', 'leaf', 'SauerPale', nb, P, Tt, paint=[(0, 'SauerDark')], ink=(1.0, 2.5),
                               tint=0.85, extra={'tint_mats': ['SauerPale', 'SauerDark']}))
    lab[mk] = len(names) + 1
    names.append('hang')
    for pc in pieces:
        pass
    print(f'[trace] triangles: leaves {sum(len(p["tris"]) for p in pieces[:-1])}, hanging {len(pieces[-1]["tris"])}',
          flush=True)
    write('sauerkraut', CAM, pieces, paint, colour, CHANNELS,
          extra={'crock': {'outer': OUTER, 't': T_WALL, 'fz': FZ, 'sy': SY}})
    if '--sheet' in sys.argv:
        sheet(sys.argv[sys.argv.index('--sheet') + 1], art, lab, names,
              ('原图上的描线（蓝：每一片）', f'描出的 {len(names)} 片：罐口里的酸菜叶、搭在罐沿上的一大片'),
              crop=(150, 150, 1230, 1000))


if __name__ == '__main__':
    main()
