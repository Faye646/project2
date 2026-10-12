"""Traces 煎鱼饭's art (新建文件夹/煎鱼饭.png) for D10, so that its fish, rice and greens are modelled 1:1 (勾勒): writes
food_models/traced_D10.json and the colours of the pieces food_models/traced_D10_paint.npz, which plates.jianyu_fan
builds the dish from, and a tracing sheet.

    python WhiteModel/trace_d10.py [--sheet <out.png>]

1. The art's camera: fitted so that the dish jianyu_fan built before covered the art's silhouette best (IoU 0.968).
   The plate's inside, under the food, is read off the plate jianyu_fan builds (DISH, built by Blender).
2. The pieces: a watershed of the art seeded by strokes inside each (STROKES, read off the art by eye) and on the
   plate round them (PLATE), its ink lines made walls, the scallion and garlic on top painted out first: the fish's
   body with its head, its dorsal, pectoral, pelvic and anal fins and its tail, the rice and the greens.
3. Their colours, as a painter would block them in: the fish's back browned and its belly pale (tinted in softly
   from its back down to its belly), its score cuts cream edged with gold (the art's palest flesh, drawn out along
   the cuts), the lines the art draws on its head (its gill cover's arcs, its mouth, its jaw: long strokes darker than
   round about) and its fins' rays; its eye an ellipse as the art draws it, a dark rim round a golden ring and an
   olive middle with a golden heart; the greens' pale stalks and darkest leaves. jianyu_fan paints each onto the
   pieces, whose meshes have vertices along every colour's edge (contour_points), so that it runs where the art's
   does, and the art's ink line round each piece, thin, just inside its outline.
4. Each piece a surface over its outline, so that from the art's camera it covers exactly what the art paints: the
   rice and the greens lie on the plate as rounded mounds, the art's shading in relief (the grains, the folds of the
   leaves); the fish's body lies on its side on the plate, its outline at its middle's height and its flank rounded
   up to the eye, closed underneath down to the plate; its fins and tail stand up, thin rounded lenses facing the
   eye from where they join the body, and the pectoral fin lies on its flank.
5. The scallion on the fish and the rice and the garlic on the greens, each where the art has it, lying on top.
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

from trace_common import (Camera, Grid, above, before, blobs, contour_points, dish_mesh, disk, fill_holes, largest,
                          lying, neighbours, on_top, outline_mesh, over, paint_channels, posterize, profile, raster,
                          seeded_pieces, shading_band, smooth_inner, standing, tracing_sheet, u8)

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '煎鱼饭.png')
DISH = "deep_plate(p, 0.115, 0.042, foot=0.7, floor=0.012, sx=0.913, n=40)"   # jianyu_fan's plate
OUT = os.path.join(HERE, 'food_models', 'traced_D10.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D10_paint.npz')
CAM = Camera(36.22, 5625.9, 619.1, 814.3)          # (1)

# (2) the pieces, built in this order: name, kind, strokes inside it (art pixels)
PIECES = [
    ('rice', 'rice', [(620, 340), (700, 330), (800, 330), (900, 400), (950, 480), (700, 470), (600, 500), (860, 540)]),
    ('greens', 'greens', [(150, 600), (250, 500), (350, 450), (450, 400), (200, 420), (300, 360), (480, 330),
                          (120, 650), (400, 560), (470, 520), (500, 505)]),
    ('fish', 'body', [(235, 800), (260, 760), (330, 730), (420, 720), (520, 690), (640, 670), (760, 655), (880, 650),
                      (980, 650), (1030, 650), (420, 835), (520, 845), (700, 822), (800, 805), (900, 770), (980, 720)]),
    ('eye', 'eye', [(318, 732), (324, 728)]),
    ('dorsal', 'fin', [(560, 556), (620, 548), (680, 552), (740, 562), (800, 574), (860, 584)]),
    ('tail', 'fin', [(1075, 600), (1110, 520), (1150, 470), (1170, 580), (1200, 560), (1110, 650)]),
    ('pelvic', 'fin', [(560, 890), (600, 910), (640, 935), (668, 950)]),
    ('anal', 'fin', [(720, 900), (780, 905), (840, 897), (880, 885)]),
    ('anal2', 'fin', [(920, 822), (980, 816), (1040, 806)]),
    ('pectoral', 'flap', [(500, 782), (560, 768), (620, 756)]),
]
PLATE = [[(30, 600), (40, 700), (60, 780)], [(115, 740), (140, 800), (160, 860)],
         [(70, 420), (90, 560), (80, 700)], [(120, 330), (200, 290), (300, 268)],
         [(170, 380), (230, 345), (290, 325), (360, 305)], [(420, 285), (445, 280)], [(100, 890), (160, 920)],
         [(90, 820), (150, 870)], [(70, 700), (85, 780)], [(60, 520), (75, 470)],
         [(250, 925), (500, 975), (800, 985), (1000, 940)], [(1100, 770), (1150, 830)], [(1185, 680), (1170, 760)],
         [(200, 300), (400, 245), (600, 235), (800, 235), (1000, 285)], [(1050, 380), (1100, 430)],
         [(1000, 470), (1020, 520)], [(470, 300), (500, 290)]]
# where each fin joins the body (art pixels): it stands in the plane through the body's surface there, facing the eye
ROOTS = {'dorsal': (700, 590), 'tail': (1040, 650), 'pelvic': (600, 872), 'anal': (790, 868), 'anal2': (930, 790)}
EYE = (306, 726), (35, 30), (310, 727), 11   # the fish's eye: its middle and half-widths (an ellipse, its dark rim
                                             # and all), and its golden middle's middle and radius (art pixels)
CUT_ANGLE = 55.0                          # the score cuts run down the flank this many degrees from level, in the art
CHANNELS = ['back', 'belly', 'gold', 'cream', 'dark', 'iris', 'ring', 'light', 'deep', 'band', 'shine', 'crisp']
# the fish's dark lines in the art, simplified to a few flat colours in clean shapes (posterize), as a painter would
# block them in: the orange crust, the grey-olive back, its gold and cream flesh and the dark lines
FISH_PALETTE = {'crust': (214, 118, 38), 'back': (160, 128, 76), 'gold': (240, 184, 92), 'cream': (247, 224, 172),
                'dark': (96, 48, 16)}
# (4) by kind: mesh spacing inside and along the outline (m), how high it rises (puff × its half-width, up to top),
# where its outline sits (edge, over its base), how far it leans to the eye, its relief, and its colours: what it is
# built in, what is painted on it in turn from which channel (the mesh has vertices along each colour's edge), and
# what is tinted into it softly (Part.tint: the back's grey and the belly's cream, shading in from its edges)
KINDS = {
    'rice': dict(gap=0.0065, gb=0.0045, puff=0.9, top=0.045, edge=0.0, tilt=0.15, relief=0.0018, mat='RiceGrain',
                 paint=[], tint=[]),
    'greens': dict(gap=0.0115, gb=0.0055, puff=0.9, top=0.028, edge=0.0, tilt=0.25, relief=0.004, mat='GreensMid',
                   paint=[('light', 'BokStalk'), ('deep', 'GreensDeep')], tint=[]),
    'body': dict(gap=0.011, gb=0.005, puff=0.9, top=0.013, edge=0.0, tilt=0.0, relief=0.0016, mat='PanFriedSkin',
                 paint=[('gold', 'FriedGold'), ('cream', 'FriedCut'), ('dark', 'FishInk')],
                 tint=[('back', '#a8642a', 0.6), ('belly', '#f6dcaa', 0.85), ('shine', '#ffe4a4', 0.55),
                       ('crisp', '#9a4412', 0.5)]),
    'eye': dict(gap=0.0022, gb=0.0016, puff=0.3, top=0.0006, edge=0.0003, tilt=0.0, relief=0.0, mat='EyeOlive',
                paint=[('band', 'FriedGold'), ('iris', 'FishIris'), ('ring', 'FishEye')], tint=[]),
    'fin': dict(gap=0.01, gb=0.005, puff=0.5, top=0.0022, edge=0.0, tilt=0.0, relief=0.0, mat='FriedFinOrange',
                paint=[('dark', 'FinRay')], tint=[]),
    'flap': dict(gap=0.008, gb=0.0045, puff=0.5, top=0.0025, edge=0.0008, tilt=0.0, relief=0.0, mat='FriedFinOrange',
                 paint=[('dark', 'FinRay')], tint=[]),
}
BODY_MID = 0.011            # the fish's outline sits this far over the plate: its middle, lying on its side
RING = 0.0006
INK = [0.5, 2.5]   # the art's ink line round a piece: full to, gone by (art pixels), inside its ring of vertices
# the fish's ink line, clear and dark as the art draws it round its body, fins and tail: full out to its first ring
# of vertices (3.4 px in), gone by the second (6.8 px)
FISH_RINGS, FISH_INK = (0.0006, 0.0012), [3.5, 3.0]


def cut_bands(rgb, body, angle):
    """The score cuts across a fried fish's flank: the art's palest flesh, smoothed along the cuts' direction (angle
    degrees from level, down to the right) so that each comes out one long clean band."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    pale = ((v > 0.9) & (s < 0.62) & (h > 25) & (h < 62)).astype(np.float32)
    L = 45
    k = np.zeros((L, L), np.float32)
    a = np.radians(angle)
    for t in np.linspace(-(L // 2), L // 2, 4 * L):
        k[int(round(L // 2 + t * np.sin(a))), int(round(L // 2 + t * np.cos(a)))] = 1
    k = cv2.GaussianBlur(k, (0, 0), 1.5)
    along = cv2.filter2D(pale, -1, k / k.sum())
    bands = cv2.morphologyEx(u8((along > 0.5) & cv2.erode(u8(body), disk(10)).astype(bool)), cv2.MORPH_OPEN, disk(3))
    n, cc, st, _ = cv2.connectedComponentsWithStats(bands)
    keep = np.zeros(n, bool)
    keep[1:] = (st[1:, cv2.CC_STAT_AREA] > 900) & (st[1:, cv2.CC_STAT_HEIGHT] > 60)
    return keep[cc]


def classes(rgb, pieces):
    """The colour classes of CHANNELS over the art (rgb with what lies on top painted out)."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    H, W = h.shape
    yy, xx = np.mgrid[0:H, 0:W]
    names = [n for n, _, _ in PIECES]
    body = pieces == names.index('fish') + 1
    eye = pieces == names.index('eye') + 1
    fins = pieces > names.index('eye') + 1
    greens = pieces == names.index('greens') + 1
    # the back's grey and the belly's cream: how far down the body each pixel is, from its back to its belly
    whole = body | eye
    rows = np.where(whole.any(0), np.argmax(whole, 0), 0), np.where(whole.any(0), H - 1 - np.argmax(whole[::-1], 0), 0)
    t = (yy - rows[0][None, :]) / np.maximum(rows[1] - rows[0], 1)[None, :]
    ramp = lambda e0, e1, x: np.clip((x - e0) / (e1 - e0), 0, 1)
    back = np.where(whole, ramp(0.36, 0.04, t), 0.0)
    belly = np.where(whole, ramp(0.55, 0.88, t), 0.0)
    soft = lambda m: np.clip(cv2.GaussianBlur(m.astype(np.float32), (0, 0), 6.0) * 255 + 0.5, 0, 255).astype(np.uint8)
    # the cuts: cream, edged with gold
    cuts = cut_bands(rgb, body, CUT_ANGLE)
    cream = cv2.dilate(u8(cuts), disk(5)).astype(bool) & body
    gold = cv2.dilate(u8(cuts), disk(12)).astype(bool) & body & ~cream
    # the lines the art draws on the head (its gill cover's arcs, its mouth, its jaw): strokes darker than round
    # about, long ones (not the crown's speckles), and the fins' rays, blocked in from the art
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    bh = cv2.morphologyEx(cv2.GaussianBlur(lum, (0, 0), 1.5), cv2.MORPH_BLACKHAT, disk(8))
    inner = cv2.erode(u8(body | eye), disk(6)).astype(bool)
    head = body & inner & (xx < 470) & ((yy > 700) | (xx > 420))
    strokes = cv2.morphologyEx(u8(head & (bh > 38) & (v < 0.75)), cv2.MORPH_CLOSE, disk(2))
    n, cc, st, _ = cv2.connectedComponentsWithStats(strokes)
    keep = np.zeros(n, bool)
    long = np.maximum(st[1:, cv2.CC_STAT_WIDTH], st[1:, cv2.CC_STAT_HEIGHT])
    keep[1:] = (st[1:, cv2.CC_STAT_AREA] > 150) & (long > 45)
    poster = posterize(rgb, body | fins, list(FISH_PALETTE.values()))
    dark = keep[cc] | ((poster == list(FISH_PALETTE).index('dark')) & fins)
    (ex, ey), (rx, ry), (ix, iy), ir = EYE
    rr = np.sqrt(((xx - ex) / rx) ** 2 + ((yy - ey) / ry) ** 2)   # 1 at the eye's rim
    iris = eye & ((xx - ix) ** 2 + (yy - iy) ** 2 < ir ** 2)
    ring = eye & (rr > 0.84)                                     # its dark rim
    band = eye & (rr > 0.68) & (rr <= 0.84)                      # and the golden ring inside it
    light = greens & (h > 60) & (h < 110) & (s < 0.55) & (v > 0.62)
    deep = greens & (v < 0.3)
    food = pieces > 0
    blocks = paint_channels([gold, cream, dark], food, smooth=1.5, min_area=60, close=1)
    eyes = paint_channels([iris, ring], food, smooth=0.8, min_area=10, close=0)
    leaves = paint_channels([light, deep], food, smooth=3.0, min_area=150, close=3)
    bands = paint_channels([band], food, smooth=0.8, min_area=10, close=0)
    # the art's light and shade over the fish: its bright crisp skin and its browned patches, brighter or darker
    # than round about, as soft washes (the crisp grain itself is the skin's texture, food_fishskin)
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    m = body.astype(np.float32)
    local = cv2.GaussianBlur(lum * m, (0, 0), 16) / np.maximum(cv2.GaussianBlur(m, (0, 0), 16), 1e-3)
    tone = cv2.GaussianBlur(lum, (0, 0), 3)
    shine = body & ~cuts & (tone > local + 12)
    crisp = body & (tone < local - 12) & ~(xx < 470)   # not the head, whose dark lines are drawn
    return np.concatenate([soft(back)[..., None], soft(belly)[..., None], blocks, eyes, leaves, bands,
                           soft(shine)[..., None], soft(crisp)[..., None]], -1)


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    H, W = alpha.shape
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    zone = alpha > 128
    strokes = {i + 1: st for i, (_, _, st) in enumerate(PIECES)}
    # (2) a first cut finds the scallion and garlic on top; the second paints them out
    pieces = seeded_pieces(rgb, zone, strokes, PLATE)
    on_fish_rice = np.isin(pieces, [1, 3])
    scallion = cv2.morphologyEx(u8(on_fish_rice & (h > 70) & (h < 125) & (s > 0.45) & (v > 0.45)), cv2.MORPH_OPEN,
                                disk(2)).astype(bool)
    garlic = cv2.morphologyEx(u8((pieces == 2) & (h > 30) & (h < 70) & (s > 0.12) & (s < 0.6) & (v > 0.8)),
                              cv2.MORPH_OPEN, disk(3)).astype(bool)
    pieces = seeded_pieces(rgb, zone, strokes, PLATE, remove=scallion | garlic)
    names = [n for n, _, _ in PIECES]
    fish_id, eye_id = names.index('fish') + 1, names.index('eye') + 1
    yy, xx = np.mgrid[0:H, 0:W]
    pieces[pieces == eye_id] = fish_id   # the eye: a disc where the art draws it, its ring and all
    (ex, ey), (rx, ry) = EYE[:2]
    pieces[(((xx - ex) / rx) ** 2 + ((yy - ey) / ry) ** 2 < 1) & (pieces == fish_id)] = eye_id
    print(f'[trace] {pieces.max()} pieces', flush=True)
    under = cv2.inpaint(rgb, u8(cv2.dilate(u8(scallion | garlic), disk(3))), 6, cv2.INPAINT_TELEA)
    paint = classes(under, pieces)
    dish_V, dish_T = dish_mesh(DISH)
    floor = Grid.top_of(dish_V, dish_T)
    zdish = np.full((H, W), np.inf)   # the dish's depths as the art sees it, for keeping the fins in front of it
    du, dv = CAM.project(dish_V[:, 0], dish_V[:, 1], dish_V[:, 2])
    raster(np.stack([du, dv], -1)[dish_T], CAM.depth(dish_V)[dish_T], np.zeros(len(dish_T), np.int32), H, W, zdish,
           np.full((H, W), -1, np.int32))
    # (4) the surfaces, each piece in turn over what is there already
    zb, zid = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
    union = pieces > 0
    out = []
    for pid, (name, kind, _) in enumerate(PIECES, 1):
        kp = KINDS[kind]
        mk = cv2.morphologyEx(u8(pieces == pid), cv2.MORPH_OPEN, disk(2))
        mk = largest(mk)
        mk = fill_holes(cv2.dilate(u8(mk), disk(3)).astype(bool) & union)   # a little under its neighbours
        mk = cv2.GaussianBlur(mk.astype(np.float32), (0, 0), 2.0) > 0.5
        edges = [(paint[..., CHANNELS.index(c)] > 127) & mk for c, _ in kp['paint']]   # where its colours change
        if kind == 'eye':
            extra = None
        else:
            extra = contour_points(edges, 15.0)
        fishy = kind in ('body', 'fin', 'flap')
        uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, kp['gap'], kp['gb'],
                                                FISH_RINGS if fishy else RING if kind != 'eye' else 0.0002,
                                                smooth_px=3.0 if kind in ('fin', 'flap') else 1.5 if kind == 'eye'
                                                else 5.0, extra=extra)
        band = shading_band(lum, mk, 4.0, 18.0)
        iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
        ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
        top = float(np.clip(kp['puff'] * R, 0.001, kp['top']))
        L = profile(d, R, top, kp['edge'], kp['tilt'], lean, kp['relief'], band[iy, ix])
        L = smooth_inner(L, nb, neighbours(len(uv), tris))
        if kind in ('rice', 'greens'):
            P, T = lying(CAM, uv, tris, nb, L, floor)
        elif kind == 'body':
            P, T = lying(CAM, uv, tris, nb, L, lambda x, y: floor(x, y) + BODY_MID, close=floor)
        elif kind == 'fin':
            ru, rv = ROOTS[name]
            s_root = on_top(CAM, zb, ru, rv, r=6)
            if s_root is None:   # off the body: at the height of its middle over the plate
                s_root = float(CAM.depth(np.stack(CAM.backproject(np.array([ru]), np.array([rv]),
                                                                  lambda x, y: floor(x, y) + BODY_MID), -1))[0])
            anchor = CAM.on_ray(ru, rv, s_root)
            P, T = standing(CAM, uv, tris, nb, L, L, anchor)
            P = above(CAM, P, floor, front=len(uv))
            P = before(CAM, P, zdish, (ru, rv))   # in front of the rim it crosses (the tail)
        else:   # a flap or the eye, lying on what is there
            P, T = over(CAM, uv, tris, L, zb, lambda u, v: CAM.depth(np.stack(CAM.backproject(u, v, floor), -1)))
        front = [t for t in T if max(t) < len(uv)]
        pu, pv = CAM.project(P[:, 0], P[:, 1], P[:, 2])
        raster(np.stack([pu, pv], -1)[np.array(front)], CAM.depth(P)[np.array(front)], np.full(len(front), pid),
               H, W, zb, zid)
        out.append({'name': name, 'kind': kind, 'mat': kp['mat'], 'rim': nb,
                    'paint': [(CHANNELS.index(c), m) for c, m in kp['paint']],
                    'tint': [(CHANNELS.index(c), col, w) for c, col, w in kp['tint']],
                    'ink': FISH_INK if fishy else [0.0, 0.0] if kind == 'eye' else INK,
                    **({'closed': len(uv)} if kind == 'body' else {}),   # its front's points; then skirt and floor
                    'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]})
        print(f'[trace] {name}: {len(T)} triangles, R {R * 100:.1f} cm, top {top * 1000:.1f} mm', flush=True)
    # (5) scallion and garlic on top
    bits = []
    for (cu, cv_, rw, rh, ang), kind in [(b, 'scallion') for b in blobs(scallion, 110, 3000)] + \
                                         [(b, 'garlic') for b in blobs(garlic, 120, 4000)]:
        s0 = on_top(CAM, zb, cu, cv_)
        if s0 is None:
            continue
        if kind == 'scallion':
            r = float(np.clip(rh / CAM.k / 2, 0.0025, 0.0045))
        else:
            r = float(np.clip(rh / CAM.k, 0.004, 0.009))
        c = CAM.on_ray(cu, cv_, s0 - (0.7 * r if kind == 'scallion' else 0.4 * r))
        th = np.radians(ang)
        under = zid[min(max(int(cv_), 0), H - 1), min(max(int(cu), 0), W - 1)]
        bits.append({'kind': kind, 'on': PIECES[under - 1][0] if under > 0 else None, 'c': np.round(c, 5).tolist(),
                     'yaw': round(float(np.arctan2(-np.sin(th) / CAM.se, np.cos(th))), 4), 'r': round(r, 5),
                     'length': round(float(np.clip(rw / CAM.k, 0.005, 0.012)), 5)})
    n_s = sum(b['kind'] == 'scallion' for b in bits)
    print(f'[trace] {n_s} scallion, {len(bits) - n_s} garlic', flush=True)
    np.savez_compressed(PAINT, paint=paint[::2, ::2])   # half the art's size: the classes are smooth
    data = {'camera': {'el': CAM.el, 'k': CAM.k, 'u0': CAM.u0, 'v0': CAM.v0}, 'paint_scale': 0.5,
            'channels': CHANNELS, 'pieces': out, 'bits': bits}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT} and {PAINT}', flush=True)
    if sheet:
        tints = {'rice': (250, 244, 228), 'greens': (120, 170, 90), 'body': (240, 170, 90), 'fin': (245, 190, 120),
                 'flap': (245, 190, 120), 'eye': (230, 190, 90)}
        extra = ([(*b, (110, 190, 80)) for b in blobs(scallion, 60, 3000)]
                 + [(*b, (250, 235, 170)) for b in blobs(garlic, 120, 4000)])
        tracing_sheet(sheet, rgba, pieces, [n for n, _, _ in PIECES], [tints[k] for _, k, _ in PIECES], extra,
                      crop=(0, 180, 1254, 1010),
                      title=('原图上的描线（蓝：每一块，绿：葱花，黄：蒜粒）', f'描出的 {pieces.max()} 块：鱼身、鱼鳍、鱼尾、米饭、青菜'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
