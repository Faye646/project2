"""Traces 胡饼's art (新建文件夹/胡饼.png) for D01, so that its three flatbreads are modelled 1:1 (勾勒): writes
food_models/traced_D01.json and the colours of the pieces food_models/traced_D01_paint.npz, which plates.hubing
builds the dish from, and a tracing sheet.

    python WhiteModel/trace_d01.py [--sheet <out.png>]

1. The art's camera and its plate: an oval celadon plate with a deep curved wall, turned a little (its right side
   further back), fitted together with the camera to the art's outline of the plate (2-3 px off all round).
2. The pieces: a flood of the art seeded by strokes inside each bread (PIECES, read off the art by eye) and on the
   plate round them (PLATE), the art's ink lines made walls: the bread at the back, propped against the plate's wall,
   the one on the left, and the one in front, its near edge torn open (the crumb).
3. Their colours: the crust cream, browned in patches as the art paints them, golden at the edges of each patch,
   orange and then brown at its heart (soft tints, each patch where the art has it: the mesh has vertices along the
   patches' edges), the torn crumb pale and porous, the art's ink line round each bread.
4. Each bread a puffy cushion over its outline, so that from the art's camera it covers exactly what the art paints:
   flat on top with a round rim where its edge shows against the plate, running on under the bread in front of it
   where that hides it; each rests as a stiff disc where it lies, on the plate's floor and wall, or on the bread
   under it (the one in front on the one on the left); the crumb a rough face falling from the crust to the torn
   edge. Each is closed underneath down to what it rests on.
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

from trace_common import (Camera, Grid, above, contour_points, dish_mesh, disk, fill_holes, largest, lying, neighbours,
                          outline_mesh, paint_channels, seeded_pieces, shading_band, smooth_inner, tracing_sheet, u8)
from trace_kit_plates import (behind, closed_under, detail_points, level_distance, own_edges, raster_piece,
                               rest_plane)

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '胡饼.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D01.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D01_paint.npz')
CAM = Camera(35.0, 6577.0, 769.2, 695.7)            # (1)
FZ = 0.012
DISH = "oval_dish(p, 0.092576, 0.9506, -0.3934, 0.0349, 0.689, floor=0.012, n=48, rings=4)"   # hubing's plate

# (2) the pieces, back to front: name, strokes inside it (art pixels)
PIECES = [
    ('back', [(600, 250), (700, 200), (850, 160), (1000, 200), (1100, 270), (1140, 330), (950, 250), (760, 270)]),
    ('left', [(300, 450), (350, 380), (450, 330), (560, 320), (300, 560), (400, 650), (550, 700), (650, 700),
              (500, 500), (580, 450), (600, 600)]),
    ('front', [(720, 420), (800, 380), (950, 340), (1100, 400), (1250, 520), (1200, 650), (1050, 720), (950, 600),
               (850, 520), (1100, 550), (700, 500), (720, 580), (800, 610), (870, 680), (920, 720)]),
]
PLATE = [[(190, 420), (200, 520), (250, 640), (330, 730), (470, 790), (650, 790), (850, 805), (1050, 790),
          (1240, 740)], [(1240, 740), (1345, 600), (1352, 450), (1290, 330), (1210, 260)],
         [(560, 205), (450, 240), (330, 300), (250, 360)], [(500, 860), (800, 900), (1100, 860)],
         [(180, 470), (175, 600)]]
# the torn crumb of the front bread: its border with the crust above, drawn out past the bread's edge below
CRUMB = [(665, 565), (720, 540), (750, 538), (800, 555), (850, 590), (890, 620), (930, 670), (945, 720), (952, 760),
         (965, 800), (900, 800), (840, 760), (760, 700), (690, 640), (640, 590)]
T = 0.024            # a bread's thickness (m)
LAP = 70             # how far a bread runs on under the one lying over it (art pixels)
LEANED_ON = ('left',)
RIM = 0.016          # the rounding of its rim, in from its edge (m)
DOME = 0.012         # how much it swells in the middle (m)
LEVELS = {'gold': (0.42, '#f2b45e', 0.65), 'orange': (0.6, '#e8903a', 0.8),
          'toast': (0.76, '#d4742a', 0.9)}   # the art's colour at each level of browning (below: the crust's own)
DETAIL_R = (11.0, 30.0)   # the mesh's spacing where the browning changes fast .. where it is plain (art px)
CHAR = 0.8           # browner than this: the dark heart of a patch, painted on (HubingChar)
CHANNELS = list(LEVELS) + ['char', 'crumb', 'pocket']
# the browning in the art runs from the crust's cream to the brown at the heart of each patch (k-means: cream
# #f5e0ae, light gold #f5c87e, golden #ecaa58, orange #da863b, brown #b2602a): how far along that each pixel is,
# and the levels of it tinted in (from, to: the share of the way along over which the tint comes in)
CREAM, BROWN = (245, 224, 174), (178, 96, 42)
TINT = [(c, col, w) for c, (_, col, w) in LEVELS.items()]
RING, INK = (0.0006, 0.0012), [3.5, 3.0]


def browning(rgb):
    """How far each pixel of the art is from the crust's cream toward the brown at a patch's heart (0..1, in Lab)."""
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.5), cv2.COLOR_RGB2LAB).astype(np.float32)
    c0, c1 = (cv2.cvtColor(np.array([[c]], np.uint8), cv2.COLOR_RGB2LAB)[0, 0].astype(np.float32) for c in (CREAM, BROWN))
    ax = c1 - c0
    return np.clip(((lab - c0) @ ax) / (ax @ ax), 0, 1)


def classes(rgb, pieces, crumb):
    """The browning's levels (gold, toast, char) as soft channels, and the crumb."""
    food = pieces > 0
    crust = food & ~crumb
    B = cv2.GaussianBlur(browning(rgb), (0, 0), 2.0)
    out = np.zeros(food.shape + (len(CHANNELS),), np.uint8)
    for c, (b0, _, _) in LEVELS.items():   # each level's tint comes in as the browning nears it (the nearest wins)
        bump = np.clip(1 - np.abs(B - b0) / 0.16, 0, 1)
        if c == 'toast':
            bump = np.clip((B - b0 + 0.16) / 0.16, 0, 1)
        # drawn out a little, so that the few vertices in a small patch carry its colour to its edge
        bump = cv2.dilate(bump.astype(np.float32), disk(4))
        out[..., CHANNELS.index(c)] = np.where(crust, bump * 255 + 0.5, 0).astype(np.uint8)
    out[..., CHANNELS.index('char')] = paint_channels([crust & (B > CHAR)], food, smooth=1.2, min_area=150, close=1)[..., 0]
    out[..., CHANNELS.index('crumb')] = paint_channels([crumb], food, smooth=1.5, min_area=200, close=3)[..., 0]
    # the crumb's pockets, shadowed: darker than round about
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    m = crumb.astype(np.float32)
    local = cv2.GaussianBlur(lum * m, (0, 0), 8) / np.maximum(cv2.GaussianBlur(m, (0, 0), 8), 1e-3)
    pocket = np.clip((local - cv2.GaussianBlur(lum, (0, 0), 1.5) - 4) / 14, 0, 1) * cv2.erode(u8(crumb), disk(2))
    out[..., CHANNELS.index('pocket')] = (pocket * 255 + 0.5).astype(np.uint8)
    return out, B


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    H, W = alpha.shape
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    zone = alpha > 128
    strokes = {i + 1: st for i, (_, st) in enumerate(PIECES)}
    pieces = seeded_pieces(rgb, zone, strokes, PLATE)
    names = [n for n, _ in PIECES]
    front_id = names.index('front') + 1
    cm = np.zeros((H, W), np.uint8)
    cv2.fillPoly(cm, [np.array(CRUMB, np.int32)], 1)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    s, v = hsv[..., 1] / 255, hsv[..., 2] / 255
    crumb = cm.astype(bool) & (pieces == front_id)
    crumb = cv2.morphologyEx(u8(crumb), cv2.MORPH_OPEN, disk(4)).astype(bool)
    print(f'[trace] {pieces.max()} pieces, crumb {crumb.sum()} px', flush=True)
    paint, B = classes(rgb, pieces, crumb)
    dish_V, dish_T = dish_mesh(DISH)
    floor = Grid.top_of(dish_V, dish_T)
    union = pieces > 0
    built = []
    supports = []   # the breads others lean on: (where the art shows it, its plane)
    for pid, (name, _) in enumerate(PIECES, 1):
        own = largest(cv2.morphologyEx(u8(pieces == pid), cv2.MORPH_OPEN, disk(2)))
        mk = fill_holes(cv2.dilate(u8(own), disk(3)).astype(bool) & union)
        mk = cv2.GaussianBlur(mk.astype(np.float32), (0, 0), 2.0) > 0.5
        edges = own_edges(pieces, pid, mk)
        # what it rests on: the plate, and the bread it lies over where it hides that one's edge (that one's edge
        # drawn on a little way under it)
        under = [(cv2.dilate(u8(m), disk(LAP)).astype(bool) & own, pl) for m, pl in supports]

        def support(x, y, under=under):
            z = floor(x, y)
            for m, (a, b, c) in under:
                u, v = CAM.project(x, y, a + b * x + c * y + T)
                hit = m[np.clip(np.round(v).astype(int), 0, H - 1), np.clip(np.round(u).astype(int), 0, W - 1)]
                z = np.where(hit, np.maximum(z, a + b * x + c * y + T), z)
            return z
        a, b, c = rest_plane(CAM, own, support, T / 2)
        X, Y, _ = CAM.backproject(np.array([float(np.nonzero(own)[1].mean())]), np.array([float(np.nonzero(own)[0].mean())]),
                                  lambda x, y: a + b * x + c * y + T / 2)
        print(f'[trace] {name}: middle at ({X[0]:.3f}, {Y[0]:.3f}), rests at {(a + b * X[0] + c * Y[0]) * 1000:.1f} mm, '
              f'tilt {np.degrees(np.arctan(b)):.1f} {np.degrees(np.arctan(c)):.1f} deg', flush=True)
        if name in LEANED_ON:
            supports.append((own, (a, b, c)))
        # the mesh: vertices along the edges of the browned patches and the crumb
        # vertices along the browning's levels (in the patches, so that each takes its colour) and the crumb's edge
        lv = lambda t: (B > t) & mk & ~crumb
        ch = lambda c: (paint[..., CHANNELS.index(c)] > 127) & mk
        edge_pts = np.r_[contour_points([ch('char')], 12.0), contour_points([ch('crumb')], 16.0)]
        dots = detail_points(mk & ~cv2.dilate(u8(ch('char') | ch('crumb')), disk(3)).astype(bool) | (mk & crumb),
                             np.where(crumb, 0.0, B), DETAIL_R[0], DETAIL_R[1], 0.03, margin=9, seed=pid)
        extra = np.r_[edge_pts, dots]
        uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, 0.0065, 0.0042, RING, smooth_px=4.0, extra=extra,
                                                extra_margin=9.0)
        de = level_distance(CAM, mk, edges, uv)          # in from its own edges, not from those of the breads over it
        de[:nb] = np.where(edges[np.clip(np.round(uv[:nb, 1]).astype(int), 0, H - 1),
                                 np.clip(np.round(uv[:nb, 0]).astype(int), 0, W - 1)], 0.0, de[:nb])
        rim = np.clip(de / RIM, 0, 1)
        L = (T / 2) * np.sqrt(1 - (1 - rim) ** 2) + DOME * np.clip(de / (3 * RIM), 0, 1) ** 1.5
        iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
        ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
        if name == 'front':   # the crumb falls from the crust to the torn edge, rough as the art shades it
            inc = crumb[iy, ix]
            dc = level_distance(CAM, mk, mk & ~cv2.dilate(u8(crumb), disk(2)).astype(bool) & ~edges, uv)
            f = np.clip(de / np.maximum(de + dc, 1e-6), 0, 1) ** 0.8
            band = shading_band(lum, crumb, 2.0, 9.0, scale=30.0)
            L = np.where(inc, (T / 2 + DOME) * f + 0.0016 * band[iy, ix] * np.clip(de / 0.002, 0, 1), L)
        L = smooth_inner(L, nb, neighbours(len(uv), tris), passes=1)
        base = lambda x, y, a=a, b=b, c=c: a + b * x + c * y + T / 2
        P, Tr = lying(CAM, uv, tris, nb, L, base)
        P, Tr = closed_under(CAM, P, Tr, nb, uv, lambda x, y, a=a, b=b, c=c: np.maximum(a + b * x + c * y, floor(x, y)),
                             lift=0.0004)
        built.append([name, uv, nb, P, Tr])
        print(f'[trace] {name}: {len(Tr)} triangles, {len(uv)} points', flush=True)
    # the breads in front kept in front of those behind them, where the art draws them so
    out = []
    for i, (name, uv, nb, P, Tr) in enumerate(built):
        zb, zid = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
        for j in range(i + 1, len(built)):
            raster_piece(CAM, built[j][3], built[j][4], len(built[j][1]), j, zb, zid)
        if i + 1 < len(built):
            P = behind(CAM, P, zb, count=len(uv))
            P[:len(uv)] = above(CAM, P[:len(uv)], floor, gap=0.0008)   # but never through the plate
        out.append({'name': name, 'kind': 'bread', 'mat': 'HubingCrust', 'rim': nb,
                    'paint': [(CHANNELS.index('char'), 'HubingChar'), (CHANNELS.index('crumb'), 'HubingCrumb')],
                    'tint': [(CHANNELS.index(ch), col, w) for ch, col, w in TINT + [('pocket', '#c49a5c', 0.8)]],
                    'ink': INK, 'closed': len(uv),
                    'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in Tr]})
    np.savez_compressed(PAINT, paint=paint[::2, ::2])
    data = {'camera': {'el': CAM.el, 'k': CAM.k, 'u0': CAM.u0, 'v0': CAM.v0}, 'paint_scale': 0.5,
            'channels': CHANNELS, 'pieces': out, 'bits': []}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT}: {sum(len(o["tris"]) for o in out)} triangles', flush=True)
    if sheet:
        tracing_sheet(sheet, rgba, pieces, names, [(250, 225, 170), (245, 205, 140), (240, 190, 120)],
                      crop=(150, 90, 1390, 940), title=('原图上的描线（蓝：每一块）', '描出的三块胡饼'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
