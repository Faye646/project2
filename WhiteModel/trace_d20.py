"""Traces 酸菜鱼's art (新建文件夹/酸菜鱼.png) for D20, and with --spicy its 辣味版's (酸菜鱼（辣味版）.png) for D20_spicy,
so that what floats in the broth is modelled 1:1 (勾勒): writes food_models/traced_D20.json (traced_D20_spicy.json)
and the colours of its pieces (…_paint.npz), which bowls.suancai_yu builds the food from, and a tracing sheet.

    python WhiteModel/trace_d20.py [--spicy] [--sheet <out.png>]

1. The art's camera: fitted so that the dish suancai_yu built before covered the art's silhouette best (IoU 0.984,
   the spicy one 0.986). The bowl and the flat broth in it are built by Blender with suancai_yu's own round_bowl;
   the broth as the art sees it, inside the bowl's lip, is where the food is.
2. The pieces, in two steps (pieces_of): first what each pixel is, a flood of the broth from seeds where the art is
   plainly broth, fish (its grey skin too), dark leaf or pale cabbage, and from the strokes; then each kind cut into
   its pieces, a flood of its own pixels from the strokes along each slice of fish and each pale piece of cabbage
   (FISH, PALE, read off the art by eye), the dark leaves each a patch of their own, (spicy) the chilli each red
   patch at a CHILI point, its seeds filled in. Nothing floats in a band along the bowl's lip (RIM); the broth's
   pale light near the lip is broth. Each piece's outline follows the art's.
3. Their colours, as a painter would block them in (posterize): the fish's grey skin along one edge, painted on,
   and the warm folds of its flesh tinted in; the dark leaves' lighter veins; the pale cabbage's deeper yellow;
   (spicy) the chilli's seeds and the drops of red oil on the fish and the cabbage.
4. Each piece a surface floating on the broth over its outline, so that from the art's camera it covers exactly
   what the art paints: the fish plump and rippled with the art's shading, the cabbage thinner, the leaves thin;
   (spicy) the chilli lying on the fish and the cabbage, a ring's red wall high round its seeds, and the drops of red
   oil on the bare broth, each a thin round pool.
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

from trace_common import (Camera, contour_points, dish_mesh, disk, fill_holes, flood, largest, neighbours,
                          outline_mesh, over, paint_channels, posterize, profile, raster, shading_band, smooth_inner,
                          tracing_sheet, u8)

HERE = os.path.dirname(os.path.abspath(__file__))
SPICY = '--spicy' in sys.argv
KEY = 'D20_spicy' if SPICY else 'D20'
ART = os.path.join(HERE, '..', '新建文件夹', '酸菜鱼（辣味版）.png' if SPICY else '酸菜鱼.png')
OUT = os.path.join(HERE, 'food_models', f'traced_{KEY}.json')
PAINT = os.path.join(HERE, 'food_models', f'traced_{KEY}_paint.npz')

# (1) the camera, and the bowl as suancai_yu builds it (its broth at fill_z)
if SPICY:
    CAM = Camera(34.18, 7097.1, 623.6, 1002.1)
    BOWL = ("round_bowl(tmp, rim_r=0.085, h=0.08, foot_r=0.035, foot_h=0.014, fill_z=0.072, fill='SpicyBroth', n=48, "
            "light=True, flare=(30, 78, 0.4), t=0.007)")
else:
    CAM = Camera(36.94, 6967.2, 623.6, 1007.8)
    BOWL = ("round_bowl(tmp, rim_r=0.085, h=0.082, foot_r=0.036, foot_h=0.013, fill_z=0.073, fill='SourBroth', n=48, "
            "light=True, flare=(30, 78, 0.4), t=0.007)")

# (2) strokes along each piece the art paints (art pixels), read off the art by eye
if SPICY:
    FISH = {
        'F1': [(500, 335), (580, 345)], 'F2': [(770, 360), (860, 385)],
        'F3': [(660, 430), (760, 450), (880, 480)], 'F4': [(180, 440), (290, 450)],
        'F5': [(330, 520), (430, 560), (520, 640)], 'F6': [(120, 545), (190, 570)],
        'F7': [(860, 540), (980, 560)], 'F8': [(780, 620), (900, 650), (1020, 680)],
        'F9': [(500, 780), (600, 800), (720, 790)], 'F10': [(610, 395), (660, 410)],
    }
    PALE = {
        'S1': [(320, 445), (470, 448)], 'S2': [(585, 420), (650, 485)], 'S3': [(520, 495), (600, 512), (700, 532)],
        'S4': [(720, 550), (770, 570)], 'S5': [(600, 570), (665, 610)], 'S6': [(860, 420), (950, 450)],
        'S7': [(1015, 500), (1110, 535)], 'S8': [(850, 750), (935, 770)], 'S9': [(610, 700), (695, 730)],
        'S10': [(1045, 585), (1130, 600)],
    }
    # the chilli: rings cut across it (C, their seeds in the middle) and pieces (K), each the red patch here
    CHILI = {'C1': (497, 462), 'C2': (255, 548), 'C3': (452, 375), 'C4': (982, 470), 'C5': (785, 530),
             'C6': (730, 340), 'C7': (440, 625), 'C8': (757, 722), 'C9': (828, 716), 'K1': (656, 360),
             'K2': (687, 504), 'K3': (311, 623)}
else:
    FISH = {
        'F1': [(330, 400), (430, 385), (520, 378)], 'F2a': [(470, 420), (530, 450), (575, 490)],
        'F11': [(625, 372), (735, 370)], 'F2b': [(650, 505), (730, 520), (810, 540), (850, 545)],
        'F3': [(825, 430), (900, 420), (965, 425)], 'F4': [(170, 590), (260, 580), (350, 585)],
        'F5a': [(240, 665), (300, 655), (350, 650)],
        'F5b': [[(440, 680), (530, 690), (620, 690), (700, 700)], [(372, 636), (382, 662), (388, 700), (380, 745)]],
        'F6': [(810, 600), (920, 625), (1050, 650)], 'F7': [(450, 780), (540, 790), (630, 800)],
        'F8': [(690, 790), (770, 805), (840, 815)], 'F9': [(970, 690), (1070, 705)], 'F10': [(820, 850), (885, 855)],
    }
    PALE = {
        'P1': [(240, 470), (310, 455)], 'P2': [(350, 462), (425, 440)], 'P3': [(420, 365), (490, 360)],
        'P4': [(615, 425), (690, 450)], 'P5': [(470, 520), (505, 535)], 'P6': [(455, 605), (570, 600)],
        'P8': [(690, 465), (750, 470)], 'P9': [(860, 490), (945, 500), (1000, 520)],
        'P11': [(960, 565), (1030, 575)], 'P12': [(260, 720), (320, 715)], 'P14': [(520, 860), (630, 850)],
        'P16': [(700, 640), (760, 680), (800, 700)], 'P17': [(840, 755), (930, 780), (990, 790)],
        'P18': [(625, 830), (720, 830)], 'Ptop': [(810, 365), (900, 370)],
    }
    CHILI = {}

# the colours inside the broth, blocked in as a painter would (posterize): the broth, the pale cabbage, the dark
# leaves and their lighter edges, the fish's white flesh and warm folds, its grey and dark skin; spicy: the red of
# the chilli and its oil, and the yellow of its seeds
CLASSES = {'broth': (215, 168, 46), 'pale': (240, 205, 95), 'dark': (115, 88, 18), 'mid': (172, 135, 53),
           'fish': (249, 238, 210), 'warm': (246, 217, 160), 'grey': (160, 160, 160), 'skin': (85, 90, 105)}
if SPICY:
    CLASSES = {'broth': (235, 180, 50), 'pale': (205, 157, 15), 'dark': (105, 63, 13), 'mid': (152, 104, 38),
               'fish': (249, 231, 187), 'warm': (244, 210, 134), 'grey': (180, 170, 150), 'skin': (90, 90, 100),
               'red': (224, 52, 15), 'deep': (174, 23, 7), 'orange': (209, 140, 26)}
CHANNELS = ['skin', 'warm', 'vein', 'deep', 'seed', 'oil']

# (4) by kind: mesh spacing inside and along the outline (m), how high it rises (puff × its half-width, up to top),
# where its outline sits (edge, over the broth), its relief from the art's shading, its colours: what it is built in,
# what is painted on it (the mesh has vertices along each colour's edge) and what is tinted into it softly
KINDS = {
    'fish': dict(gap=0.0048, gb=0.0035, puff=0.6, top=0.006, edge=0.0007, relief=0.006, mat='FishSlice',
                 paint=[('skin', 'SuanSkin'), ('oil', 'ChiliDrop')],
                 tint=[('warm', '#f0c49c', 0.7)]),
    'pale': dict(gap=0.007, gb=0.0035, puff=0.5, top=0.0035, edge=0.0006, relief=0.001,
                 mat='SpicyStalk' if SPICY else 'SauerStalk',
                 paint=[('oil', 'ChiliDrop')], tint=[('deep', '#e0bc48', 0.45)]),
    'leaf': dict(gap=0.008, gb=0.003, puff=0.35, top=0.0018, edge=0.0005, relief=0.0006, mat='SuanLeaf',
                 paint=[], tint=[('vein', '#a89040', 0.6)]),
    'chili': dict(gap=0.004, gb=0.0018, puff=0.5, top=0.003, edge=0.0006, relief=0.0, mat='ChiliRed',
                  paint=[('seed', 'TomatoSeed')], tint=[]),
    'drop': dict(gap=0.004, gb=0.0012, puff=0.4, top=0.0007, edge=0.0004, relief=0.0, mat='ChiliDrop',
                 paint=[], tint=[]),
}
RING = 0.0005
# the fish's skin: grey, or in the 辣味版's orange broth a brownish grey (most saturated, darkest it gets)
SKIN = (0.72, 0.8) if SPICY else (0.45, 0.72)
RIM = 20           # the band of bare broth along the bowl's lip, art pixels: nothing floats there
INK = [0.3, 2.5]   # the art's ink line round a piece: full to, gone by (art pixels), inside its ring of vertices
FISH_INK = [0.2, 1.2]   # the fish's own, fainter: the art draws its slices' edges soft


def broth_view(H, W):
    """The bowl and its broth as the art's camera sees them: the depths, and where the broth shows (inside the lip)."""
    full = dish_mesh('from food_models.bowls import round_bowl\ntmp = p\n' + BOWL)
    broth = dish_mesh('from food_models.bowls import round_bowl\ntmp = Part()\nfz, rf = ' + BOWL +
                      "\np.lathe([(rf, fz), (rf * 0.5, fz + 0.0004), (0.0, fz + 0.0005)], 'SourBroth', n=48, "
                      "close_ends=False)")
    zb, zid = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
    for k, (V, T) in enumerate((broth, full)):   # the broth first: where it shows, it is the broth
        u, v = CAM.project(V[:, 0], V[:, 1], V[:, 2])
        raster(np.stack([u, v], -1)[T], CAM.depth(V)[T], np.full(len(T), k), H, W, zb, zid)
    return zb, zid == 0


def pieces_of(rgb, zone, cl):
    """The pieces, in two steps. First what each pixel is (the broth, a fish, a dark leaf, pale cabbage, a chilli): a
    flood of the broth from seeds where the art is plainly each (and from the strokes), lowest change of colour first,
    the fish's grey skin a fish's. Then each kind cut into its pieces: a flood of its pixels alone from the strokes
    along each piece, what no stroke reaches its own piece; the leaves each a patch of their own."""
    H, W = zone.shape
    keys = list(CLASSES)
    K = {k: cl == i for i, k in enumerate(keys)}
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.0), cv2.COLOR_RGB2LAB).astype(np.float32)
    grad = sum(np.abs(cv2.Sobel(lab[..., c], cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(lab[..., c], cv2.CV_32F, 0, 1))
               for c in range(3))

    def seeds(m, r, amin):
        e = cv2.erode(u8(m), disk(r))
        n, cc, st, _ = cv2.connectedComponentsWithStats(e)
        keep = np.zeros(n, bool)
        keep[1:] = st[1:, cv2.CC_STAT_AREA] >= amin
        return keep[cc] & zone

    def strokes_of(group):
        from PIL import ImageDraw
        canvas = Image.new('I', (W, H), 0)
        d = ImageDraw.Draw(canvas)
        for k, lines in enumerate(group.values(), 1):
            for line in (lines if isinstance(lines[0], list) else [lines]):   # one stroke or more
                d.line(line, fill=k, width=7)
                for x, y in line:
                    d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=k)
        return np.asarray(canvas, np.int32)
    # (a) what each pixel is: 1 broth, 2 fish, 3 leaf, 4 pale cabbage, 5 chilli
    leafy = (K['dark'] | K['mid']) & (s > 0.55)
    skin = zone & (s < SKIN[0]) & (v < SKIN[1]) & (v > 0.15) & ~leafy & ~(K['dark'] & (s > 0.85))
    chili = chili_patches(h, s, v, zone)   # on top of all: each red patch at a CHILI point, its seeds and all
    fishy = K['fish'] | K['warm'] | K['grey'] | K['skin']
    inner = cv2.erode(u8(zone), disk(45)).astype(bool)   # away from the lip, where the broth's light is pale too
    mk = np.zeros((H, W), np.int32)
    if SPICY:   # its broth is orange, its stalks the yellower gold (hue, and Lab's b)
        mk[seeds((K['broth'] | K['orange']) & (h < 41.5), 6, 300)] = 1
    else:
        mk[seeds(K['broth'], 6, 300)] = 1
    mk[(seeds(fishy, 5, 200) | seeds(skin, 1, 30)) & inner] = 2
    mk[seeds(K['dark'] & (s > 0.55), 2, 25)] = 3
    if SPICY:
        mk[seeds((h >= 43.5) & (h < 52) & (s > 0.6) & (v > 0.62) & (lab[..., 2] > 188), 3, 60) & inner] = 4
    else:
        mk[seeds(K['pale'], 5, 250) & inner] = 4
    near_lip = zone & ~inner & (K['broth'] | K['pale'] | K['mid'] | K.get('orange', K['broth']))   # near the
                                                                                    # lip, the broth's gold is broth
    mk[near_lip & (mk == 0)] = 1
    for group, c in ((FISH, 2), (PALE, 4)):
        if group:
            mk[strokes_of(group) > 0] = c
    mk[chili > 0] = 5
    rim = zone & ~cv2.erode(u8(zone), disk(RIM)).astype(bool)   # the broth along the lip, bare, and the bowl's
    mk[rim | ~zone] = 1                                          # pale wall over it
    what = flood(mk, grad)
    what[rim | ~zone] = 1
    # (b) each kind's pieces
    pieces = np.zeros((H, W), np.int32)
    names, kinds = [], []

    def add(m, name, kind):
        names.append(name)
        kinds.append(kind)
        pieces[m] = len(names)
    for group, c, kind in ((FISH, 2, 'fish'), (PALE, 4, 'pale')):
        m = what == c
        if not group:   # no strokes: each patch its own piece
            n, cc, stt, _ = cv2.connectedComponentsWithStats(u8(cv2.morphologyEx(u8(m), cv2.MORPH_OPEN, disk(2))))
            for i in range(1, n):
                if stt[i, cv2.CC_STAT_AREA] >= 700:
                    add(cc == i, f'{kind}{i}', kind)
            continue
        st = strokes_of(group)
        mk = np.where(m, 0, -1).astype(np.int32)
        mk[m & (st > 0)] = st[m & (st > 0)]
        got = flood(mk, grad)
        for k, name in enumerate(group, 1):   # what no stroke reaches is the broth's light: left out
            add(m & (got == k), name, kind)
    for k, name in enumerate(CHILI, 1):
        add(chili == k, name, 'chili')
    m = cv2.morphologyEx(u8(what == 3), cv2.MORPH_OPEN, disk(1))
    n, cc, stt, _ = cv2.connectedComponentsWithStats(m)
    for i in range(1, n):   # the dark leaves, each patch one leaf
        if stt[i, cv2.CC_STAT_AREA] >= 120:
            add(cc == i, f'L{i}', 'leaf')
    return pieces, names, kinds


def chili_patches(h, s, v, zone):
    """The chilli (spicy): the red patch at each CHILI point, the seeds in a ring's middle and its dark edge filled
    in. Numbered as CHILI (0 elsewhere)."""
    H, W = zone.shape
    out = np.zeros((H, W), np.int32)
    if not CHILI:
        return out
    red = zone & ((h < 20) | (h > 340)) & (s > 0.55) & (v > 0.28)
    red = cv2.morphologyEx(u8(red), cv2.MORPH_CLOSE, disk(2))
    n, cc = cv2.connectedComponents(red)
    for k, (x, y) in enumerate(CHILI.values(), 1):
        win = cc[y - 12:y + 13, x - 12:x + 13]   # the patch at the point (a ring's point is on its seeds: the
        ids = win[win > 0]                        # red round them)
        if not len(ids):
            continue
        m = fill_holes(cc == np.bincount(ids).argmax())
        m = cv2.morphologyEx(u8(m), cv2.MORPH_OPEN, disk(2)).astype(bool) & zone
        out[m & (out == 0)] = k
    return out


def classes(rgb, pieces, kinds, cl):
    """The colour classes of CHANNELS over the art."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    keys = list(CLASSES)
    K = {k: cl == i for i, k in enumerate(keys)}
    kind_of = np.array(['none'] + kinds)[pieces]
    fish, pale, leaf, chili = (kind_of == k for k in ('fish', 'pale', 'leaf', 'chili'))
    skin = fish & (((s < SKIN[0]) & (v < SKIN[1] - 0.02)) | ((s < 0.3) & (v < 0.88)))   # the fish's grey skin
    skin = cv2.morphologyEx(u8(skin), cv2.MORPH_CLOSE, disk(2)).astype(bool) & fish
    warm = fish & K['warm']                                  # the warm folds of its flesh
    vein = leaf & (v > 0.62)                                 # the leaves' lighter veins and edges
    deep = pale & (K['broth'] | K['mid'])                    # the pale cabbage's deeper yellow
    seed = chili & (h > 30) & (h < 70) & (v > 0.6)           # the chilli's seeds
    oil = (fish | pale) & (((h < 20) | (h > 340)) & (s > 0.6))   # drops of red oil on the fish and cabbage
    food = pieces > 0
    a = paint_channels([skin], food, smooth=1.8, min_area=80, close=2)
    b = paint_channels([warm, vein, deep], food, smooth=3.0, min_area=120, close=2)
    c = paint_channels([seed, oil], food, smooth=1.0, min_area=12, close=1)
    return np.concatenate([a, b, c], -1)


def drops(rgb, zone, pieces):
    """The drops of red chilli oil on the bare broth (spicy): round red specks, each its outline."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    red = zone & (pieces == 0) & ((h < 18) | (h > 340)) & (s > 0.6) & (v > 0.35)
    red = cv2.morphologyEx(u8(red), cv2.MORPH_OPEN, disk(1))
    n, cc, st, _ = cv2.connectedComponentsWithStats(red)
    out = []
    for i in range(1, n):
        a = st[i, cv2.CC_STAT_AREA]
        if 30 <= a <= 1500:
            out.append(cc == i)
    return out


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    H, W = alpha.shape
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    zb_broth, zone = broth_view(H, W)
    zone &= alpha > 128
    cl = posterize(rgb, zone, list(CLASSES.values()), passes=(3, 3, 2), speck=150)
    pieces, names, kinds = pieces_of(rgb, zone, cl)
    # each piece one clean region: its largest part, specks given back to the broth
    for pid in range(1, len(names) + 1):
        m = pieces == pid
        if not m.any():
            continue
        keep = largest(cv2.morphologyEx(u8(m), cv2.MORPH_OPEN, disk(2)))
        pieces[m & ~keep] = 0
    paint = classes(rgb, pieces, kinds, cl)
    print(f'[trace] {KEY}: {len(names)} seeds, '
          f'{sum((pieces == i + 1).any() for i in range(len(names)))} pieces', flush=True)
    out = []
    n_tris = {}
    zb_food = zb_broth.copy()   # the broth and what floats on it, for what lies on top of that (the chilli)
    order = sorted(range(1, len(names) + 1), key=lambda i: kinds[i - 1] == 'chili')
    for pid in order:
        name, kind = names[pid - 1], kinds[pid - 1]
        kp = KINDS[kind]
        m = pieces == pid
        amin = {'fish': 1500, 'pale': 700, 'leaf': 260, 'chili': 400}[kind]
        if m.sum() < amin:
            continue
        mk = fill_holes(m)   # a fish goes on under the chilli on it
        mk = cv2.GaussianBlur(mk.astype(np.float32), (0, 0), 1.5) > 0.5
        out.append(surface(name, kind, kp, mk, paint, lum, zb_food if kind == 'chili' else zb_broth))
        P, T = np.array(out[-1]['verts']), np.array(out[-1]['tris'])
        pu, pv = CAM.project(P[:, 0], P[:, 1], P[:, 2])
        raster(np.stack([pu, pv], -1)[T], CAM.depth(P)[T], np.full(len(T), pid), H, W, zb_food,
               np.full((H, W), -1, np.int32))
        n_tris[kind] = n_tris.get(kind, 0) + len(T)
    if SPICY:   # the drops of red oil on the bare broth
        for k, m in enumerate(drops(rgb, zone, pieces)):
            mk = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 0.8) > 0.5
            if mk.sum() < 25:
                continue
            out.append(surface(f'oil{k}', 'drop', KINDS['drop'], mk, paint, lum, zb_broth))
            n_tris['drop'] = n_tris.get('drop', 0) + len(out[-1]['tris'])
    print(f'[trace] {len(out)} pieces, triangles by kind {n_tris}, all {sum(n_tris.values())}', flush=True)
    np.savez_compressed(PAINT, paint=paint[::2, ::2])
    data = {'camera': {'el': CAM.el, 'k': CAM.k, 'u0': CAM.u0, 'v0': CAM.v0}, 'paint_scale': 0.5,
            'channels': CHANNELS, 'pieces': out, 'bits': []}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT} and {PAINT}', flush=True)
    if sheet:
        tints = {'fish': (250, 244, 232), 'pale': (238, 214, 110), 'leaf': (110, 120, 50), 'chili': (220, 50, 30)}
        tracing_sheet(sheet, rgba, pieces, names, [tints[k] for k in kinds], crop=(60, 250, 1190, 910),
                      title=('原图上的描线（蓝：每一块）',
                             f'描出的 {len(out)} 块：鱼片、酸菜叶、酸菜梗' + ('、辣椒圈、红油' if SPICY else '')))
        print(f'[trace] sheet {sheet}', flush=True)


def surface(name, kind, kp, mk, paint, lum, zbuf):
    """One piece as a surface floating on the broth over its outline (art pixels mk)."""
    H, W = mk.shape
    edges = [(paint[..., CHANNELS.index(c)] > 127) & mk for c, _ in kp['paint']]
    extra = contour_points(edges, 7.0 if kind == 'fish' else 10.0) if edges else None   # the skin's edge: fine
    uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, kp['gap'], kp['gb'], RING if kind != 'drop' else 0.0002,
                                            smooth_px=2.0 if kind in ('fish', 'pale') else 1.2, extra=extra,
                                            extra_margin=RING * CAM.k + 2.5)   # the skin runs along the edge
    band = shading_band(lum, mk, 3.0, 20.0) if kind == 'fish' else shading_band(lum, mk, 3.0, 14.0)
    iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
    ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
    top = float(np.clip(kp['puff'] * R, 0.0005, kp['top']))
    L = profile(d, R, top, kp['edge'], 0.0, lean, kp['relief'], band[iy, ix])
    if kind == 'chili':   # a ring: its red wall high, the seeds inside it lower
        wall = np.clip(d / max(0.42 * R, 1e-6), 0, 1)
        L = kp['edge'] + (top - kp['edge']) * np.where(wall < 1, np.sin(wall * np.pi / 2), 0.45)
    L = smooth_inner(L, nb, neighbours(len(uv), tris))
    P, T = over(CAM, uv, tris, L, zbuf, lambda u, v: np.full_like(u, float(np.nanmin(zbuf[np.isfinite(zbuf)]))))
    return {'name': name, 'kind': kind, 'mat': kp['mat'], 'rim': nb,
            'paint': [(CHANNELS.index(c), m) for c, m in kp['paint']],
            'tint': [(CHANNELS.index(c), col, w) for c, col, w in kp['tint']],
            'ink': [0.0, 0.0] if kind in ('drop', 'chili') else FISH_INK if kind == 'fish' else INK,
            'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]}


if __name__ == '__main__':
    main()
