"""Traces 米料备料's art (新建文件夹/米料备料.png) so that the rice heaped in its tub, the spoon in it and the cloth bundle
behind are modelled 1:1 (勾勒): writes food_models/traced_rice_prep.json and its colours (_paint.npz), which
sacks.rice_prep builds the item from, and a tracing sheet.

    python WhiteModel/trace_rice_prep.py [--sheet <out.png>]

1. The art's camera, at the icons' 35°, its scale fitted so that the item built before covered the art's silhouette
   best, its origin moved to the tub's middle; the tub as the art draws it (sacks.MI_TUB: its rim's ellipse, its
   foot, read off the art), squeezed front to back as the art draws it; the green wraps where the art has them.
2. The pieces: a flood of the art seeded by strokes inside the rice, the spoon and the bundle (read off the art by
   eye) and on the tub round them, the art's ink lines walls.
3. The rice a heap over its outline in the tub, the art's grains in relief, closed down to the rice's level; the
   spoon a thin rounded lens standing up out of the rice, facing the eye; the bundle a plump lens standing behind
   the tub on the left, leaning back to the right, closed behind; its rope round the neck and its two ends, each a
   twisted rope along the art's, on the cloth; the sage leaves printed on the cloth painted on. The colours the
   art's own.
"""
import math
import sys

import cv2
import numpy as np

from trace_common import Camera, contour_points, dish_mesh, disk, fill_holes, largest, lying, neighbours, profile, \
    shading_band, smooth_inner, standing, u8
from trace_packs import Art, colour_map, depth_at, mean_colour, piece_mesh, piece_record, sheet, write, zbuffer

ART = '米料备料.png'
CAM = Camera(35.0, 3553.2, 715.0, 982.5)   # 651.2, 927.8 before: the origin moved to the tub's middle
TUB = dict(wall=[(0.1149, 0.0), (0.127, 0.02), (0.1313, 0.045), (0.133, 0.07)], z_rim=0.072, rim=0.138,
           top=0.0996, inside=0.114, fill=0.08, sy=0.862)   # as sacks.MI_TUB
WRAPS_ART = [(468, 487), (839, 483), (271, 665), (315, 875), (581, 955), (1048, 907), (1161, 745)]
STROKES = {
    1: [(380, 720), (480, 640), (600, 580), (720, 560), (820, 570)],                        # the rice
    2: [(450, 820), (600, 860), (750, 860), (880, 820), (1000, 760), (1060, 700)],
    3: [(905, 700), (950, 722)],
    4: [(1210, 340), (1150, 420), (1080, 500), (1020, 570)],                                # the spoon
    5: [(200, 450), (300, 400), (400, 420)],                                                # the bundle
    6: [(100, 550), (150, 700), (200, 780)],
    7: [(560, 420), (620, 455)],
    8: [(250, 150), (350, 130), (450, 140), (300, 230)],
}
RICE, SPOON, BUNDLE = (1, 2, 3), (4,), (5, 6, 7, 8)
TUB_STROKES = [[(300, 690), (500, 950), (800, 1000), (1100, 800), (1150, 700)], [(400, 1100), (700, 1150), (1000, 1080)],
               [(600, 470), (800, 465), (1000, 520)]]
# the bundle's rope (art pixels along each, radius): round the neck, and its two ends from the knot
ROPES = [([(270, 285), (330, 286), (380, 288), (430, 281), (470, 266), (505, 255)], 0.0027),
         ([(398, 300), (400, 340), (395, 385), (392, 425), (397, 460), (402, 478)], 0.0025),
         ([(525, 282), (560, 310), (600, 332), (630, 362), (650, 402), (660, 445)], 0.0025)]
KNOTS = [((505, 262), 0.009), ((552, 222), 0.0065)]
BUNDLE_PLANE = ((-0.17, 0.065, 0.0), (0.57, -0.82, 0.0))   # through its foot at the left, leaning back to the right
CHANNELS = ['leaf']


def wrap_angle(X, Y):
    T = TUB
    rc, zc = (T['rim'] + T['inside']) / 2, (T['z_rim'] + T['top']) / 2
    a = np.radians(np.arange(0, 360, 0.5))
    u, v = CAM.project(rc * np.cos(a), T['sy'] * rc * np.sin(a), np.full_like(a, zc))
    front = np.sin(a) < 0.15
    d = np.hypot(u - X, v - Y) + np.where(front | (Y < 600), 0, 1e3)
    return float(np.degrees(a[np.argmin(d)]))


def main():
    art = Art(ART)
    H, W = art.H, art.W
    V, T = dish_mesh("from food_models.sacks import mi_tub\nmi_tub(p)")
    zb_tub, _ = zbuffer(CAM, V, T, H, W)
    # where the tub is (its model seen by the camera), and inside its rim's inside edge
    tub_sil = np.isfinite(zb_tub) & art.alpha
    a = np.linspace(0, 2 * math.pi, 360)
    u, v = CAM.project(TUB['inside'] * np.cos(a), TUB['sy'] * TUB['inside'] * np.sin(a), np.full_like(a, TUB['top']))
    inner = np.zeros((H, W), np.uint8)
    cv2.fillPoly(inner, [np.round(np.stack([u, v], -1)).astype(np.int32)], 1)
    inner = cv2.erode(inner, disk(3)).astype(bool)
    wood = art.alpha & (art.h > 10) & (art.h < 36) & (art.s > 0.38) & (art.v > 0.22) & (art.v < 0.98)
    zone = np.zeros((H, W), np.uint8)   # round the spoon in the art: its handle over the rim, its bowl in the rice
    cv2.fillPoly(zone, [np.array([(830, 600), (860, 560), (1000, 480), (1150, 330), (1210, 290), (1250, 330),
                                  (1180, 450), (1060, 560), (1010, 640), (1000, 810), (940, 800), (840, 660)], np.int32)], 1)
    spoon = wood & zone.astype(bool)
    spoon = cv2.morphologyEx(u8(spoon), cv2.MORPH_CLOSE, disk(3))
    n_, cc_ = cv2.connectedComponents(spoon)
    spoon = fill_holes(cc_ == cc_[420, 1150])                 # what joins the handle
    spoon = cv2.morphologyEx(u8(spoon), cv2.MORPH_OPEN, disk(3)).astype(bool)
    rice = fill_holes(cv2.morphologyEx(u8(inner & art.alpha & ~spoon), cv2.MORPH_OPEN, disk(3)).astype(bool)) & ~spoon
    rice = largest(rice)
    bundle = largest(fill_holes(cv2.morphologyEx(u8(art.alpha & ~tub_sil & ~spoon & (art.xx < 830)), cv2.MORPH_OPEN,
                                                 disk(4)).astype(bool)))
    rg = art.rgb[..., 0].astype(int) - art.rgb[..., 1].astype(int)
    leaf = bundle & (rg < 16) & (art.lum < 215) & (art.lum > 90) & (art.s > 0.1)    # the sage prints: greyer, greener
    leaf = cv2.morphologyEx(u8(leaf), cv2.MORPH_OPEN, disk(2))
    leaf = cv2.morphologyEx(leaf, cv2.MORPH_CLOSE, disk(4)).astype(bool)
    nn, cc, st, _ = cv2.connectedComponentsWithStats(u8(leaf))
    keep = np.zeros(nn, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 150
    leaf = keep[cc]
    paint = np.clip(cv2.GaussianBlur(leaf.astype(np.float32), (0, 0), 1.5) * 255 + 0.5, 0, 255).astype(np.uint8)[..., None]
    tub = art.alpha & ~(rice | spoon | bundle)
    print('[trace] px: rice', rice.sum(), 'spoon', spoon.sum(), 'bundle', bundle.sum(), 'leaf', leaf.sum(), flush=True)
    colour = np.zeros((H, W, 3), np.uint8)
    for m, fl in ((rice, 0.5), (spoon, 0.4), (bundle, 0.6), (tub, 0.55)):
        c = colour_map(art, [m], flatten=fl, sigma=40, ink=0.3)
        colour[m | (cv2.dilate(u8(m), disk(6)).astype(bool) & (colour.sum(-1) == 0))] = \
            c[m | (cv2.dilate(u8(m), disk(6)).astype(bool) & (colour.sum(-1) == 0))]
    print('[trace] colours: rice', mean_colour(art, rice), 'spoon', mean_colour(art, spoon), 'cloth',
          mean_colour(art, bundle & ~leaf), 'leaf', mean_colour(art, leaf), 'tub', mean_colour(art, tub & (art.v > 0.4)),
          flush=True)
    wraps = [round(wrap_angle(X, Y), 1) for X, Y in WRAPS_ART]
    pieces = []
    # the rice: a heap over the rice's level
    mk, uv, tris, nb, d, R, lean = piece_mesh(CAM, rice, 0.012, 0.0045, ring=0.0006, smooth_px=3.0)
    iy, ix = (np.clip(np.round(uv[:, i]).astype(int), 0, n - 1) for i, n in ((1, H), (0, W)))
    band = shading_band(art.lum, mk, 2.0, 10.0)[iy, ix]
    L = profile(d, R, 0.045, 0.012, 0.3, lean, 0.006, band)
    L = smooth_inner(L, nb, neighbours(len(uv), tris), passes=1)
    fz = TUB['fill']
    base = lambda x, y: np.full_like(np.asarray(x, float), fz)
    # closed a little under its outline (a short skirt, so that it stays inside the tub's wall all round)
    P, Tt = lying(CAM, uv, tris, nb, L, base, close=lambda x, y: np.full_like(np.asarray(x, float), fz + 0.008))
    pieces.append(piece_record('rice', 'rice', 'MiRice', nb, P, Tt, ink=(0.8, 2.0), tint=0.7, extra={'closed': len(uv)}))
    zb_rice, _ = zbuffer(CAM, P, np.array([t for t in Tt if max(t) < len(uv)]), H, W)
    # the spoon: a thin lens standing out of the rice, facing the eye
    mk, uv, tris, nb, d, R, lean = piece_mesh(CAM, spoon, 0.009, 0.004, ring=0.0006, smooth_px=2.0)
    Ls = profile(d, R, 0.005, 0.0008)
    s_anchor = float(depth_at(zb_rice, np.array([[870.0, 640.0]]), float(np.nanmin(zb_rice[np.isfinite(zb_rice)])), r=6)[0])
    anchor = CAM.on_ray(870.0, 640.0, s_anchor - 0.004)
    P, Tt = standing(CAM, uv, tris, nb, Ls, Ls * 0.8, anchor)
    pieces.append(piece_record('spoon', 'spoon', 'MiSpoon', nb, P, Tt, ink=(1.0, 2.5), tint=0.8))
    # the bundle: a plump lens standing behind the tub on the left, leaning back to the right
    extra = contour_points([leaf], 14.0)
    mk, uv, tris, nb, d, R, lean = piece_mesh(CAM, bundle, 0.016, 0.006, ring=0.0008, smooth_px=3.0, extra=extra,
                                              margin=2.5)
    iy, ix = (np.clip(np.round(uv[:, i]).astype(int), 0, n - 1) for i, n in ((1, H), (0, W)))
    band = shading_band(art.lum, mk, 3.0, 20.0)[iy, ix]
    Lf = profile(d, R, 0.04, 0.001, 0.0, lean, 0.006, band)
    Lb = profile(d, R, 0.04, 0.001)
    Lf = smooth_inner(Lf, nb, neighbours(len(uv), tris), passes=1)
    a0, n0 = (np.array(v) for v in BUNDLE_PLANE)
    P, Tt = standing(CAM, uv, tris, nb, Lf, Lb, a0, normal=n0 / np.linalg.norm(n0))
    P[:, 2] = np.maximum(P[:, 2], 0.0005)
    pieces.append(piece_record('bundle', 'bundle', 'MiCloth', nb, P, Tt, paint=[(0, 'MiLeafPrint')], ink=(1.0, 2.5),
                               tint=0.7))
    zb_b, _ = zbuffer(CAM, P, np.array([t for t in Tt if max(t) < len(uv)]), H, W)
    fall = float(np.nanmin(zb_b[np.isfinite(zb_b)]))
    ropes = []
    for path, r in ROPES:
        q = np.array(path, float)
        s = depth_at(zb_b, q, fall, r=4)
        ropes.append([np.round(CAM.on_ray(q[:, 0], q[:, 1], s - r * 1.4), 5).tolist(), r])
    knots = []
    for (X, Y), r in KNOTS:
        s = float(depth_at(zb_b, np.array([[X, Y]], float), fall, r=6)[0])
        knots.append([np.round(CAM.on_ray(X, Y, s - r * 0.7), 5).tolist(), r])
    print(f'[trace] wraps at {wraps}; triangles: ' + ', '.join(f"{p['name']} {len(p['tris'])}" for p in pieces), flush=True)
    write('rice_prep', CAM, pieces, paint, colour, CHANNELS, extra={'wraps': wraps, 'ropes': ropes, 'knots': knots})
    if '--sheet' in sys.argv:
        lab = np.where(rice, 1, np.where(spoon, 2, np.where(bundle, 3, 0)))
        lab[leaf] = 4
        sheet(sys.argv[sys.argv.index('--sheet') + 1], art, lab, ['rice', 'spoon', 'bundle', 'leaf'],
              ('原图上的描线（蓝：每一块）', '描出的：米堆、木勺、布包（印着叶子）'), crop=(0, 60, 1254, 1200))


if __name__ == '__main__':
    main()
