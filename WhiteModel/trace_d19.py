"""Traces 北京烤鸭's art (新建文件夹/北京烤鸭.png) for D19, so that its roast duck, pancakes, julienne and leaves are
modelled 1:1 (勾勒): writes food_models/traced_D19.json and the colours of the pieces food_models/traced_D19_paint.npz,
which plates.beijing_kaoya builds the dish from, and a tracing sheet.

    python WhiteModel/trace_d19.py [--sheet <out.png>]

1. The art's camera: fitted, 35° up as the icons are seen, so that the oval dish beijing_kaoya built before covers
   the art's silhouette best.
2. The pieces: a flood of the art seeded by strokes inside each (read off the art by eye: along the middle of each
   slice of the breast, from the edges it was hand-traced along before) and on the dish round them (DISH_STROKES), the
   art's ink lines made walls: the leg with its drumstick raised at the back, the slices fanned in front of it, the
   stack of pancakes, the bundle of julienned scallion and cucumber and the leaves under the duck.
3. Each piece a surface over its outline in the art, so that from the art's camera it covers exactly what the art
   paints: the breast a low mound under the slices, each slice a plump rounded slab lying on it, back to front, the
   leg a thick rounded lump, the pancakes a flat stack, the julienne a low bundle, the leaves thin; each closed
   underneath down to the dish.
4. Their colours: the lacquered skin red-brown, deeper in its shade and with the art's white glints, the slices' cut
   faces pale pink with the white of the fat under the skin (painted on: the mesh has vertices along their edges),
   the pancakes' edges drawn where the art draws them, the julienne's white, pale green and dark green strips.
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

from trace_common import (Camera, Grid, contour_points, dish_mesh, disk, fill_holes, largest, lying, neighbours,
                          oriented, outline_mesh, over, paint_channels, profile, seeded_pieces, shading_band,
                          smooth_inner, tracing_sheet, u8)
from trace_kit_plates import behind, closed_under, detail_points, raster_piece

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '北京烤鸭.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D19.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D19_paint.npz')
CAM = Camera(35.0, 4453.3, 636.8, 711.6)            # (1)
FZ = 0.008
DISH = ("d = DISH19\n"
        "oval_dish(p, d['A'], d['q'], d['yaw'], d['h'], d['foot'], floor=0.008, n=48, rings=3)")

# the slices as they were hand-traced before, in the order they are laid: (left edge, meat line, right edge), top to
# bottom (art pixels): the strokes run along the middle of each
SLICES19 = [
    ([(175, 545), (125, 590), (100, 610), (85, 627), (110, 655), (147, 680)], None,
     [(254, 566), (200, 604), (167, 631), (153, 656), (163, 684)]),                                                 # B0
    ([(270, 552), (238, 570), (184, 600), (165, 613), (151, 627), (137, 652), (147, 680), (135, 725), (160, 745)],
     [(270, 552), (238, 570), (180, 654), (148, 677), (135, 725), (160, 745)],
     [(406, 544), (375, 551), (311, 562), (282, 580), (278, 617), (259, 648), (257, 679), (241, 719), (221, 762)]),  # S25
    ([(390, 540), (359, 547), (335, 555), (295, 558), (266, 576), (262, 613), (249, 627), (243, 644), (241, 675),
      (225, 715), (205, 758)],
     [(390, 540), (359, 547), (298, 596), (264, 641), (251, 668), (241, 675), (225, 715), (205, 758)],
     [(556, 549), (520, 560), (441, 587), (402, 619), (346, 714), (335, 743), (335, 767), (318, 782), (309, 807),
      (307, 821)]),                                                                                                 # S22
    ([(540, 545), (504, 556), (476, 561), (425, 583), (386, 615), (330, 710), (319, 739), (319, 763), (302, 778),
      (293, 803), (291, 817)],
     [(540, 545), (504, 556), (455, 604), (447, 628), (416, 644), (391, 686), (366, 718), (346, 740), (330, 760),
      (309, 792), (293, 803), (291, 817)],
     [(611, 592), (577, 611), (532, 637), (495, 679), (468, 728), (456, 763), (454, 786), (452, 824), (463, 871)]),  # S23
    ([(595, 588), (561, 607), (516, 633), (479, 675), (452, 724), (440, 759), (438, 782), (436, 820), (447, 867)],
     [(595, 588), (561, 607), (525, 646), (533, 669), (510, 682), (462, 758), (438, 782), (436, 820), (447, 867)],
     [(681, 632), (652, 649), (621, 669), (588, 712), (567, 751), (553, 765), (547, 801), (546, 844), (552, 921)]),   # S27
    ([(665, 628), (636, 645), (605, 665), (572, 708), (551, 747), (537, 761), (531, 797), (528, 840), (530, 885),
      (536, 917)],
     [(665, 628), (636, 645), (599, 691), (577, 733), (556, 801), (548, 811), (543, 863), (534, 885), (536, 917)],
     [(793, 645), (765, 626), (732, 620), (687, 626), (648, 651), (620, 695), (601, 767), (598, 862), (607, 945)]),   # S33
    ([(777, 641), (749, 622), (716, 616), (671, 622), (632, 647), (604, 691), (585, 763), (582, 858), (591, 941)],
     [(777, 641), (760, 636), (716, 634), (680, 640), (650, 660), (625, 700), (607, 763), (604, 858), (603, 941)],
     [(790, 659), (770, 659), (743, 667), (715, 690), (696, 728), (684, 764), (679, 795), (683, 844), (684, 884),
      (684, 945)]),                                                                                                 # R3a
    ([(774, 655), (754, 655), (727, 663), (699, 686), (680, 724), (668, 760), (663, 791), (667, 840), (668, 880),
      (668, 941)],
     [(774, 655), (750, 668), (731, 699), (732, 728), (722, 762), (720, 788), (705, 815), (697, 843), (680, 870),
      (668, 900), (668, 941)],
     [(776, 616), (787, 627), (800, 647), (808, 662), (852, 690), (869, 726), (882, 767), (894, 816), (870, 900),
      (840, 945)]),                                                                                                 # R3b
    ([(760, 612), (771, 623), (784, 643), (792, 658), (836, 686), (853, 722), (861, 727), (870, 770), (878, 812)],
     [(760, 612), (771, 623), (784, 625), (802, 636), (826, 658), (854, 703), (861, 727), (870, 770), (878, 812)],
     [(790, 610), (850, 633), (895, 668), (930, 712), (952, 760), (958, 800), (945, 822)]),                           # R4
    ([(775, 900), (853, 822), (933, 814), (972, 833), (984, 865)], None,
     [(782, 942), (845, 940), (905, 930), (960, 912), (984, 887)]),                                                  # R5
    ([(102, 527), (130, 545), (170, 560), (201, 571), (274, 544), (326, 515), (360, 505), (420, 495), (480, 495),
      (530, 515)],
     [(102, 527), (170, 556), (203, 559), (211, 552), (266, 525), (337, 511), (380, 503), (480, 494), (530, 514)],
     [(110, 514), (150, 505), (200, 500), (260, 488), (350, 462), (440, 446), (535, 470)]),                           # A2
    ([(140, 511), (187, 514), (205, 518), (224, 503), (254, 501), (279, 489), (355, 471), (387, 457), (443, 455),
      (471, 460), (520, 482)],
     [(140, 511), (187, 512), (195, 500), (222, 481), (251, 467), (284, 458), (328, 433), (413, 432), (433, 437),
      (471, 456), (520, 480)],
     [(146, 499), (160, 490), (185, 478), (210, 464), (235, 451), (260, 441), (290, 434), (320, 429), (360, 426),
      (400, 424), (440, 427), (480, 439), (530, 464)]),                                                               # A1
]


LEG = [(270, 262), (320, 290), (390, 320), (460, 350), (530, 380), (590, 420), (630, 470), (660, 510)]
PANCAKES = [(760, 520), (800, 440), (880, 410), (980, 430), (1080, 460), (1150, 540), (1120, 600), (950, 560)]
JULIENNE = [(860, 630), (940, 660), (1040, 700), (1110, 740), (1060, 820), (980, 780), (1000, 870)]
LEAVES = [[(70, 575), (95, 610)], [(225, 425), (250, 440)]]
DISH_STROKES = [[(60, 700), (110, 800), (250, 900), (450, 960), (650, 1000), (850, 990), (1050, 930), (1180, 830),
                 (1230, 700), (1225, 620)], [(700, 330), (640, 320), (560, 300)], [(150, 480), (200, 450)],
                [(40, 640), (45, 700)], [(45, 660), (62, 720), (100, 790), (180, 850), (300, 910), (450, 945)],
                [(110, 470), (160, 430)], [(600, 960), (760, 958)]]
# (3) by kind: mesh spacing inside and along the outline (m), height (m), its colours: built in, painted from which
# channels, tinted from which
KINDS = {
    'leg': dict(gap=0.015, gb=0.0065, top=0.03, mat='KaoyaSkin', paint=[],
                tint=[('orange', '#f8a048', 0.8), ('dark', '#7a240a', 0.6), ('glint', '#fff2dc', 0.85)]),
    'slice': dict(gap=0.014, gb=0.0075, top=0.011, mat='KaoyaSkin', paint=[('meat', 'KaoyaCut')],
                  tint=[('orange', '#f8a048', 0.8), ('dark', '#7a240a', 0.6), ('glint', '#fff2dc', 0.85),
                        ('fat', '#fdf6ee', 0.8)]),
    'pancakes': dict(gap=0.021, gb=0.008, top=0.012, mat='KaoyaPancake', paint=[('rim', 'KaoyaPancakeRim')],
                     tint=[]),
    'julienne': dict(gap=0.015, gb=0.007, top=0.012, mat='KaoyaScallion', paint=[('green', 'KaoyaGreen'),
                                                                                ('cucumber', 'KaoyaCucumber'),
                                                                                ('white', 'KaoyaScallionWhite')],
                     tint=[]),
    'leaves': dict(gap=0.012, gb=0.007, top=0.003, mat='KaoyaLeaf', paint=[], tint=[]),
}
CHANNELS = ['dark', 'glint', 'meat', 'fat', 'rim', 'cucumber', 'white', 'orange', 'green']
RING, INK = (0.0006, 0.0012), [3.5, 3.0]
MOUND_TOP = 0.018   # the breast under the slices (m)


def midline(left, right, n=7):
    def res(p):
        p = np.array(p, float)
        L = np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]
        t = np.linspace(0, L[-1], n)
        return np.stack([np.interp(t, L, p[:, 0]), np.interp(t, L, p[:, 1])], -1)
    return [tuple(q) for q in ((res(left) + res(right)) / 2)[1:-1]]


def pieces_list():
    """name, kind, strokes: the leg, the slices (in the order they are laid), the pancakes, the julienne, the leaves."""
    out = [('leg', 'leg', LEG)]
    for k, (left, meat, right) in enumerate(SLICES19):
        out.append((f'slice{k}', 'slice', midline(left, right)))
    out += [('pancakes', 'pancakes', PANCAKES), ('julienne', 'julienne', JULIENNE)]
    out += [(f'leaves{k}', 'leaves', st) for k, st in enumerate(LEAVES)]
    return out


def classes(rgb, pieces, kinds):
    hsv = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.0), cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.5), cv2.COLOR_RGB2LAB).astype(np.float32)
    food = pieces > 0
    of = lambda kind: np.isin(pieces, [i + 1 for i, k in enumerate(kinds) if k == kind])
    duck = of('leg') | of('slice')
    meat = of('slice') & (s < 0.42) & (v > 0.62)                        # the cut faces, pale pink
    cut = np.zeros(food.shape, np.uint8)                                # and as they were hand-traced
    for left, line, right in SLICES19:
        if line is not None:
            cv2.fillPoly(cut, [np.array(list(left) + list(reversed(line)), np.int32)], 1)
    meat = (meat | cv2.erode(cut, disk(3)).astype(bool)) & of('slice')
    meat = cv2.morphologyEx(u8(meat), cv2.MORPH_OPEN, disk(3)).astype(bool)
    fat = meat & (s < 0.16) & (v > 0.9)                                 # the white fat under the skin
    dark = duck & ~meat & (v < 0.6)                                     # the lacquer in its shade
    orange = duck & ~meat & (v > 0.86) & (s > 0.6) & (h > 18) & (h < 40)  # and where the light catches it
    glint = duck & (s < 0.25) & (v > 0.93) & ~cv2.dilate(u8(meat), disk(4)).astype(bool)
    pan = of('pancakes')
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    m = pan.astype(np.float32)
    local = cv2.GaussianBlur(lum * m, (0, 0), 5) / np.maximum(cv2.GaussianBlur(m, (0, 0), 5), 1e-3)
    rim = pan & ((lum < local - 16) | (v < 0.62))                       # the pancakes' edges, drawn darker
    rim = cv2.dilate(u8(rim), disk(1)).astype(bool) & pan
    jul = of('julienne')
    cucumber = jul & (h > 60) & (h < 170) & (s > 0.5) & (v < 0.62)      # the cucumber's dark green skin
    green = jul & ~cucumber & (h > 60) & (h < 170) & (s > 0.4)          # the scallion's green
    white = jul & (s < 0.2) & (v > 0.88)                                # and its white
    sharp = paint_channels([meat, rim, cucumber, white, green], food, smooth=1.2, min_area=60, close=1)
    soft = paint_channels([dark, glint, fat, orange], food, smooth=2.0, min_area=30, close=1)
    out = np.zeros(food.shape + (len(CHANNELS),), np.uint8)
    for c, src in (('meat', sharp[..., 0]), ('rim', sharp[..., 1]), ('cucumber', sharp[..., 2]),
                   ('white', sharp[..., 3]), ('green', sharp[..., 4]), ('dark', soft[..., 0]), ('glint', soft[..., 1]),
                   ('fat', soft[..., 2]), ('orange', soft[..., 3])):
        out[..., CHANNELS.index(c)] = src
    return out


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    H, W = alpha.shape
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    plist = pieces_list()
    kinds = [k for _, k, _ in plist]
    pieces = seeded_pieces(rgb, alpha > 128, {i + 1: st for i, (_, _, st) in enumerate(plist)}, DISH_STROKES)
    paint = classes(rgb, pieces, kinds)
    floor = Grid.top_of(*dish_mesh(DISH))
    union = pieces > 0
    zb, zid = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
    on_dish = lambda u, v: CAM.depth(np.stack(CAM.backproject(u, v, floor), -1))
    out = []
    # the breast under the slices: a low mound over all of them (seen only between them)
    slices = np.isin(pieces, [i + 1 for i, k in enumerate(kinds) if k == 'slice'])
    mk = cv2.GaussianBlur(fill_holes(largest(u8(slices))).astype(np.float32), (0, 0), 3.0) > 0.5
    uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, 0.026, 0.009, 0.0008, smooth_px=4.0)
    L = profile(d, R, MOUND_TOP, 0.0, 0.2, lean)
    P, T = lying(CAM, uv, tris, nb, L, floor)
    P, T = closed_under(CAM, P, T, nb, uv, floor)
    raster_piece(CAM, P, T, len(uv), 0, zb, zid)
    out.append({'name': 'breast', 'kind': 'mound', 'mat': 'KaoyaCut', 'rim': nb, 'paint': [], 'tint': [],
                'ink': [0.0, 0.0], 'closed': len(uv), 'verts': np.round(P, 6).tolist(),
                'tris': [list(map(int, t)) for t in T]})
    print(f'[trace] breast: {len(T)} triangles', flush=True)
    for pid, (name, kind, _) in enumerate(plist, 1):
        kp = KINDS[kind]
        own = cv2.morphologyEx(u8(pieces == pid), cv2.MORPH_OPEN, disk(2))
        if own.sum() < 300:
            continue
        own = largest(own)
        mk = fill_holes(cv2.dilate(u8(own), disk(3)).astype(bool) & union)
        mk = cv2.GaussianBlur(mk.astype(np.float32), (0, 0), 2.0) > 0.5
        edges = [(paint[..., CHANNELS.index(c)] > 127) & mk for c, _ in kp['paint']]
        extra = contour_points(edges, {'julienne': 17.0, 'pancakes': 24.0}.get(kind, 22.0)) if edges else None
        uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, kp['gap'], kp['gb'], RING if kind != 'leaves' else 0.0005,
                                                smooth_px=3.0, extra=extra, extra_margin=7.0)
        iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
        ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
        if kind == 'slice':   # a plump slab, its skin side up: the meat face sloping down from it
            L = profile(d, R, float(np.clip(0.9 * R, 0.002, kp['top'])))
            L = L * np.where(paint[iy, ix, CHANNELS.index('meat')] > 127, 0.75, 1.0)
            L = smooth_inner(L, nb, neighbours(len(uv), tris), passes=2)
            here = zb[iy, ix]
            base = np.where(np.isfinite(here), here, on_dish(uv[:, 0], uv[:, 1]))
            P = CAM.on_ray(uv[:, 0], uv[:, 1], base - 0.0004 - L)
            T = oriented(P, [tuple(t) for t in np.asarray(tris)], CAM.toward, True)
            P, T = closed_under(CAM, P, T, nb, uv, lambda x, y: floor(x, y))
        elif kind == 'leg':
            band = shading_band(lum, mk, 6.0, 30.0)
            L = profile(d, R, float(np.clip(0.8 * R, 0.002, kp['top'])), 0.0, 0.0, None, 0.004, band[iy, ix])
            L = smooth_inner(L, nb, neighbours(len(uv), tris), passes=1)
            P, T = lying(CAM, uv, tris, nb, L, floor)
            P, T = closed_under(CAM, P, T, nb, uv, floor)
        else:
            L = profile(d, R, float(np.clip(0.8 * R, 0.001, kp['top'])))
            if kind == 'pancakes':   # flat on top, a rounded rim
                L = kp['top'] * np.sqrt(np.clip(d / 0.008, 0, 1) * (2 - np.clip(d / 0.008, 0, 1)))
            L = smooth_inner(L, nb, neighbours(len(uv), tris), passes=1)
            P, T = lying(CAM, uv, tris, nb, L, floor)
            P, T = closed_under(CAM, P, T, nb, uv, floor)
        raster_piece(CAM, P, T, len(uv), pid, zb, zid)
        out.append({'name': name, 'kind': kind, 'mat': kp['mat'], 'rim': nb,
                    'paint': [(CHANNELS.index(c), m) for c, m in kp['paint']],
                    'tint': [(CHANNELS.index(c), col, w) for c, col, w in kp['tint']],
                    'ink': INK if kind != 'leaves' else [0.8, 2.0], 'closed': len(uv),
                    'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]})
        print(f'[trace] {name}: {len(T)} triangles', flush=True)
    np.savez_compressed(PAINT, paint=paint[::2, ::2])
    data = {'camera': {'el': CAM.el, 'k': CAM.k, 'u0': CAM.u0, 'v0': CAM.v0}, 'paint_scale': 0.5,
            'channels': CHANNELS, 'pieces': out, 'bits': []}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT}: {sum(len(o["tris"]) for o in out)} triangles', flush=True)
    if sheet:
        tints = {'leg': (200, 90, 50), 'slice': (220, 110, 60), 'pancakes': (245, 230, 190), 'julienne': (200, 230, 160),
                 'leaves': (100, 170, 80)}
        tracing_sheet(sheet, rgba, pieces, None, [tints[k] for k in kinds], crop=(40, 200, 1240, 1000),
                      title=('原图上的描线（蓝：每一块）', '描出的鸭腿、鸭片、薄饼、葱丝和叶子'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
