"""Traces 薄饼备料's art (新建文件夹/薄饼备料.png) so that its stack of pancakes and the one folded on top are modelled
1:1 (勾勒): writes food_models/traced_pancake.json and its colours (_paint.npz), which sacks.pancake builds the item
from, and a tracing sheet.

    python WhiteModel/trace_pancake.py [--sheet <out.png>]

1. The art's camera: fitted so that the item built before covered the art's silhouette best (IoU 0.984), its origin
   moved to the tray's middle. The tray as the art draws it: its rim's outside and inside edges and the top of its
   band read off the art (TRAY), stretched front to back as the art draws it; the wraps where the art has them.
2. The pieces: a flood of the art seeded by strokes inside the stack and the fold (read off the art by eye), the
   tray's rim and the floor round them, the ink lines walls: the stack and the folded pancake on it.
3. The stack: one surface over its outline, lying on the tray's floor, flat on top (the top pancake, its edge where
   the layers start) and falling away in front over the edges of the sheets under it down to the floor (a ramp read
   off the art, the art's light and dark lines in relief), closed down to the floor behind and under. The fold: a
   slab over the top pancake, rising towards its point at the back.
4. Their colours: the art's own (the colour map), the golden spots painted on, the stack's edges in their own colour
   (the sheets' edges in its texture); the tray's colours likewise from the art.
"""
import math
import sys

import cv2
import numpy as np

from trace_common import Camera, contour_points, disk, fill_holes, largest, lying, neighbours, oriented, profile, \
    seeded_pieces, shading_band, smooth_inner, u8
from trace_packs import Art, colour_map, mean_colour, piece_mesh, piece_record, sheet, write

ART = '薄饼备料.png'
CAM = Camera(35.0, 4762.1, 632.2, 705.5)   # at the icons' 35°, fitted to the item built before; origin at the tray's middle
# the tray (sacks.bing_tray): its rim's outside and inside radius, the top of its band, the floor, the stretch
TRAY = dict(ro=0.1242, ri=0.1097, zt=0.0238, floor=0.008, sy=1.172)
H_STACK = 0.044          # the top pancake over the floor
STROKES = {
    1: [(250, 400), (400, 330), (550, 300), (690, 292)],                        # the stack: its top
    2: [(205, 540), (300, 690), (450, 800), (640, 850), (820, 820), (1000, 760), (1075, 650)],   # its edges in front
    3: [(260, 480), (330, 560), (420, 600)],
    4: [(1075, 450), (1080, 560)],                                                 # its top right of the fold
    5: [(450, 880), (640, 915), (850, 880)],                                       # its lowest sheets
    6: [(450, 540), (600, 450), (750, 350), (860, 262)],                           # the fold
    7: [(470, 588), (560, 612), (680, 640), (800, 655), (920, 668), (1000, 672)],
    9: [(600, 560), (800, 600), (960, 620)],
    8: [(960, 420), (985, 560)],
    10: [(915, 300), (950, 380)],
}
FOLD = (6, 7, 8, 9, 10)
# the fold's outline as the art draws it (its edge along the stack is faint): the flood is kept within it
FOLD_POLY = [(390, 557), (878, 228), (905, 240), (935, 300), (975, 400), (1010, 500), (1035, 600), (1046, 690),
             (1000, 705), (900, 700), (800, 690), (700, 672), (600, 650), (500, 625), (430, 595), (395, 570)]
# the wraps round the rim, degrees anticlockwise from the right (read off the art against the rim's angles)
WRAPS = [10, 40, 77, 112, 145, 177, 202, 232, 270, 313, 345]
FLOOR_STROKES = [[(470, 962), (640, 970), (800, 960)]]
CHANNELS = ['spot', 'side']


def tray_zone(art):
    """Where the art shows the tray's rim (outside its inside edge) and its floor (inside it)."""
    se, ce = CAM.se, CAM.ce
    t = np.linspace(0, 2 * math.pi, 720)
    ri, zt, sy = TRAY['ri'], TRAY['zt'], TRAY['sy']
    u, v = CAM.project(ri * np.cos(t), sy * ri * np.sin(t), np.full_like(t, zt))
    inner = np.zeros((art.H, art.W), np.uint8)
    cv2.fillPoly(inner, [np.round(np.stack([u, v], -1) * 8).astype(np.int32)], 1, shift=3)
    return inner.astype(bool)


def main():
    art = Art(ART)
    H, W = art.H, art.W
    inner = tray_zone(art)
    zone = art.alpha & cv2.erode(u8(inner), disk(4)).astype(bool)
    labels = seeded_pieces(art.rgb, zone, {k: v for k, v in STROKES.items()}, FLOOR_STROKES)
    fold = np.isin(labels, FOLD)
    poly = np.zeros((H, W), np.uint8)
    cv2.fillPoly(poly, [np.array(FOLD_POLY, np.int32)], 1)
    fold = (fold & cv2.dilate(poly, disk(8)).astype(bool)) | cv2.erode(poly, disk(8)).astype(bool)
    stack = (labels > 0) & ~fold
    # the stack goes on under the fold, back to its own back edge (carried across the fold from either side of it)
    cols = np.nonzero(stack.any(0))[0]
    first = np.where(stack.any(0), np.argmax(stack, 0), H).astype(float)
    hid = fold.any(0) & (np.argmax(fold, 0) <= first + 3)          # columns where the fold hides the stack's back
    ok = np.isin(np.arange(W), cols) & ~hid
    back = np.interp(np.arange(W), np.nonzero(ok)[0], first[ok])
    under = (stack | fold) & (art.yy >= back[None, :] + 2)
    stack = largest(fill_holes(stack | under))
    print(f'[trace] stack {stack.sum()} px, fold {fold.sum()} px', flush=True)
    wraps = WRAPS
    # (3) the stack: flat on top, a ramp in front down over the sheets' edges to its outline on the floor
    xs = np.nonzero(stack.any(0))[0]
    bottom = np.where(stack.any(0), H - 1 - np.argmax(stack[::-1], 0), 0)        # its lowest row, column by column
    xc, half = (xs.min() + xs.max()) / 2, (xs.max() - xs.min()) / 2
    band = 110 + 200 * np.sqrt(np.clip(1 - ((np.arange(W) - xc) / half) ** 2, 0, 1))   # the ramp's height in the art
    t_map = np.clip((bottom[None, :] - art.yy) / band[None, :], 0, 1)
    side = stack & (t_map < 0.97) & ~fold
    spot = (stack | fold) & (art.s > 0.5) & (art.v > 0.72) & (art.h < 46)
    spot = cv2.morphologyEx(u8(spot), cv2.MORPH_CLOSE, disk(2))
    spot = cv2.morphologyEx(spot, cv2.MORPH_OPEN, disk(2)).astype(bool) & ~side
    n, cc, st, _ = cv2.connectedComponentsWithStats(u8(spot))
    keep = np.zeros(n, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 45
    spot = keep[cc]
    soft = lambda m, s=1.2: np.clip(cv2.GaussianBlur(m.astype(np.float32), (0, 0), s) * 255 + 0.5, 0, 255).astype(np.uint8)
    paint = np.stack([soft(spot), soft(side, 0.8)], -1)
    rim = art.alpha & ~inner
    floor_zone = art.alpha & inner & ~(stack | fold)
    # the colours: the pancakes' own soft (the spots are painted), the edges' fine (their lines run between the
    # vertices traced along them), the tray's from the art
    clean = art.rgb.copy()
    clean[:] = cv2.inpaint(art.rgb, u8(cv2.dilate(u8(spot), disk(3))), 7, cv2.INPAINT_TELEA)
    from trace_packs import Art as _A
    soft_art = _A.__new__(_A)
    soft_art.__dict__.update(art.__dict__)
    soft_art.rgb = cv2.GaussianBlur(clean, (0, 0), 6.0)
    top = colour_map(soft_art, [(stack & ~side) | fold], flatten=0.6, sigma=45)
    edge_c = colour_map(art, [side], flatten=0.5, sigma=30, fine=0.8)
    tray_c = colour_map(art, [rim, floor_zone], flatten=0.6, sigma=40, ink=0.4)
    sw = cv2.GaussianBlur(side.astype(np.float32), (0, 0), 3.0)[..., None]
    colour = np.where(((stack | fold) & ~side)[..., None], top, np.where(side[..., None], edge_c, tray_c))
    colour = np.clip(colour * (1 - sw) * ((stack | fold)[..., None]) + edge_c * sw * (stack | fold)[..., None]
                     + tray_c * (~(stack | fold))[..., None], 0, 255).astype(np.uint8)
    print('[trace] colours: pancake', mean_colour(art, stack & ~side & ~spot), 'side', mean_colour(art, side),
          'spot', mean_colour(art, spot), 'rim', mean_colour(art, rim & (art.s > 0.45)),
          'floor', mean_colour(art, floor_zone & (art.v > 0.3)), flush=True)
    floor = lambda x, y: np.full_like(np.asarray(x, float), TRAY['floor'])
    pieces = []
    # the stack
    # vertices along the sheets' edges: the art's dark lines and the pale rims between them, column by column
    sm = cv2.GaussianBlur(art.lum, (0, 0), 1.6)
    lines = []
    for x in range(int(xs.min()) + 8, int(xs.max()) - 8, 19):
        col = np.nonzero(side[:, x])[0]
        if len(col) < 12:
            continue
        prof_ = sm[col, x]
        for i in range(2, len(col) - 2):
            if (prof_[i] <= prof_[i - 2:i + 3].min() and prof_[i - 2:i + 3].max() - prof_[i] > 5) or                     (prof_[i] >= prof_[i - 2:i + 3].max() and prof_[i] - prof_[i - 2:i + 3].min() > 5):
                lines.append((float(x), float(col[i])))
    lines = np.array(lines).reshape(-1, 2)
    print(f'[trace] {len(lines)} points along the edges of the sheets', flush=True)
    extra = np.r_[contour_points([spot & stack, side], 12.0), lines]
    mk, uv, tris, nb, d, R, lean = piece_mesh(CAM, stack, 0.015, 0.005, ring=0.0007, smooth_px=3.0, extra=extra, margin=3.0)
    iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
    ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
    t = t_map[iy, ix]
    rel = shading_band(art.lum, mk, 1.5, 8.0, scale=14.0)[iy, ix]
    L = H_STACK * np.clip(t, 0, 1) ** 0.85 + 0.0016 * rel * (t < 0.97) + 0.0015 * np.sqrt(np.clip(d / 0.03, 0, 1)) * (t >= 0.97)
    L[:nb] = np.where(t[:nb] > 0.9, L[:nb], 0.0007)
    L = smooth_inner(L, nb, neighbours(len(uv), tris), passes=1)
    P, T = lying(CAM, uv, tris, nb, L, floor, close=floor)
    pieces.append(piece_record('stack', 'stack', 'BingCake', nb, P, T, paint=[(0, 'BingSpot'), (1, 'BingSide')],
                               ink=(1.0, 2.5), tint=0.85, extra={'closed': len(uv), 'tint_mats': ['BingCake', 'BingSide']}))
    # the fold: a slab over the top pancake, its point at the back lifted
    tip, foot = np.array([878.0, 228.0]), np.array([700.0, 690.0])
    extra = contour_points([spot & fold], 12.0)
    mk, uv, tris, nb, d, R, lean = piece_mesh(CAM, fold, 0.017, 0.005, ring=0.0006, smooth_px=6.0, extra=extra)
    ax = (tip - foot) / np.linalg.norm(tip - foot)
    s = np.clip(((uv - foot) @ ax) / np.linalg.norm(tip - foot), 0, 1)
    top = H_STACK + 0.0016
    lift = 0.0185 * s ** 1.6
    Lt = profile(d, R, 0.0045, 0.0012) + lift
    Lb = lift + 0.0004
    Lt[:nb], Lb[:nb] = lift[:nb] + 0.0012, lift[:nb] + 0.0012
    base = lambda x, y: np.full_like(np.asarray(x, float), TRAY['floor'] + top)
    Pt, Tt = lying(CAM, uv, tris, nb, Lt, base)
    Pb, _ = lying(CAM, uv[nb:], np.zeros((0, 3), int), 0, Lb[nb:], base)
    P = np.r_[Pt, Pb]
    m = lambda i: i if i < nb else i + len(uv) - nb
    Tb = oriented(P, [(m(a), m(b), m(c)) for a, b, c in tris], CAM.toward, False)
    pieces.append(piece_record('fold', 'fold', 'BingCake', nb, P, Tt + Tb, paint=[(0, 'BingSpot')], ink=(0.3, 2.0),
                               tint=0.85))
    for pc in pieces:
        print(f"[trace] {pc['name']}: {len(pc['tris'])} triangles", flush=True)
    write('pancake', CAM, pieces, paint, colour, CHANNELS, extra={'wraps': wraps, 'tray': TRAY})
    if '--sheet' in sys.argv:
        lab = np.where(fold, 2, np.where(stack, 1, 0))
        lab[side] = 3
        sheet(sys.argv[sys.argv.index('--sheet') + 1], art, lab, ['top', 'fold', 'edges'],
              ('原图上的描线（蓝：每一块）', '描出的：一摞薄饼（顶面、边）、折起的一张'), crop=(0, 150, 1254, 1120))


if __name__ == '__main__':
    main()
