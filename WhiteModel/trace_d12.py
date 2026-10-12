"""Traces 两熟紫苏鱼's art (新建文件夹/两熟紫苏鱼.png) for D12, so that its fish, perilla leaves and bamboo-shoot slices
are modelled 1:1 (勾勒): writes food_models/traced_D12.json and the colours of the pieces
food_models/traced_D12_paint.npz, which plates.liangshu_zisu_yu builds the dish from, and a tracing sheet.

    python WhiteModel/trace_d12.py [--sheet <out.png>]

1. The art's camera: fitted so that the dish liangshu_zisu_yu built before covered the art's silhouette best
   (IoU 0.976). The dish and its brown sauce, under the food, are built by Blender (DISH).
2. The pieces: a flood of the art seeded inside each and on the dish and sauce round them (DISH_STROKES), its ink
   lines and the edges of the leaves' purple and green made walls: the fish, its eye, its pectoral and dorsal fins
   and its tail (read off the art by eye; more seeds wherever the fish shows between the rest), and the 13 slices of
   bamboo shoot and 15 perilla leaves strewn over it (LEAVES, BAMBOO: each one's middle, kept to where the art has its
   colour). The fish's body is its whole outline (FISH_OUTLINE: the art's where it shows, its back and belly carried
   on under the leaves), so that what lies on it lies on it.
3. Their colours, as a painter would block them in, the art simplified to a few flat colours in clean shapes
   (posterize): the fish's orange, its brown flank, golden cheek, pale lips and lights and the dark of its crown,
   with the lines the art draws on it (its gill cover's arcs, its mouth, its score cuts: long strokes darker than
   round about); its eye an ellipse as the art draws it (a pale orbit, a dark rim, a golden-brown iris round a dark
   pupil); the fins' and the tail's dark rays and golden lights; the leaves' purple, their green rims, darker veins
   and lighter purple; the gold of the slits cut in the bamboo. liangshu_zisu_yu paints each onto the pieces, whose
   meshes have vertices along every colour's edge, with the art's ink line round each piece.
4. Each piece a surface over its outline, so that from the art's camera it covers exactly what the art paints: the
   fish's body lies on its side on the dish, its outline at its middle's height and its flank rounded up to the eye,
   closed underneath down to the dish; its pectoral fin lies on its flank; its tail and its dorsal fin stand up from
   its edge, the tail over the rim, in front of it; the bamboo slices and the leaves lie on whatever is under them
   (the fish, the sauce), running on gently off its edges (envelope), never down them, so that no underside shows
   from behind.
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

from trace_common import (Camera, Grid, above, before, contour_points, dish_mesh, disk, fill_holes, flood, largest,
                          lying, neighbours, on_top, oriented, outline_mesh, over, paint_channels, posterize, profile,
                          raster, shading_band, smooth_inner, standing, tracing_sheet, u8)

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '两熟紫苏鱼.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D12.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D12_paint.npz')
CAM = Camera(34.79, 4536.9, 627.4, 754.2)          # (1)
DISH = ("d = DISH12\n"
        "inside = oval_dish(p, d['A'], d['q'], d['yaw'], d['h'], d['foot'], floor=0.008, n=80, lobes=20, "
        "amount=0.018, rings=2)\n"
        "dish_sauce(p, 'Sauce', inside, d['A'], d['q'], d['yaw'], reach=0.74, n=40, seed=12, lift=0.0012)")

# (2) the fish, built first: name, kind, strokes inside it (art pixels)
FISH = [
    ('fish', 'body', [(150, 800), (200, 835), (260, 805), (300, 770), (350, 740), (330, 690), (400, 700), (420, 760),
                      (380, 840), (300, 870), (440, 650), (480, 610), (520, 585), (450, 880), (550, 868), (650, 830),
                      (800, 560), (990, 505), (1030, 525)]),
    ('eye', 'eye', [(234, 737), (237, 739)]),
    ('pectoral', 'flap', [(520, 785), (555, 765), (590, 750)]),
    ('tail', 'fin', [(1060, 280), (1080, 330), (1120, 360), (1170, 360), (1200, 365), (1050, 390), (1100, 420),
                     (1150, 410)]),
    ('dorsal', 'fin', [(560, 455), (590, 440), (620, 421), (642, 405)]),
]
# the perilla leaves (stalk end, tip) and the bamboo slices (outlines), as read off the art before: each one's seed is
# the middle of it, kept to where the art has its colour
LEAVES = [((335, 582), (366, 503)), ((380, 570), (440, 503)), ((470, 505), (478, 432)), ((500, 470), (570, 430)),
          ((560, 472), (800, 575)), ((777, 452), (918, 426)), ((875, 455), (1030, 500)),
          ((715, 610), (875, 715)), ((925, 600), (1100, 725)), ((610, 730), (530, 642)), ((555, 682), (790, 850)),
          ((690, 920), (865, 820)), ((870, 850), (960, 752)), ((310, 922), (517, 988)), ((300, 600), (243, 660))]
BAMBOO = [[(298, 642), (305, 615), (428, 562), (432, 588)], [(421, 528), (557, 478), (566, 518), (428, 552)],
          [(505, 548), (600, 505), (612, 535), (520, 568)], [(690, 452), (705, 405), (805, 395), (790, 455)],
          [(795, 440), (812, 393), (850, 383), (868, 415), (862, 440)],
          [(680, 452), (828, 476), (826, 497), (690, 502)], [(826, 500), (1075, 562), (1072, 622), (845, 528)],
          [(1075, 577), (1128, 572), (1124, 640), (1082, 662)], [(650, 620), (720, 614), (752, 700), (668, 690)],
          [(735, 655), (915, 745), (900, 768), (762, 766), (745, 718)],
          [(845, 766), (952, 744), (877, 862), (850, 836)],
          [(905, 730), (995, 714), (1025, 790), (1000, 802), (950, 752)],
          [(484, 934), (700, 858), (702, 925), (630, 967)]]
DISH_STROKES = [[(60, 700), (70, 800), (110, 900)], [(150, 985), (300, 1030), (500, 1050), (700, 1035), (900, 995),
                                                     (1050, 925)],
                [(1150, 650), (1175, 700), (1150, 800), (1100, 860)], [(1150, 500), (1200, 530)],
                [(250, 520), (300, 455), (400, 405), (500, 372), (600, 348), (700, 333), (800, 325), (900, 333),
                 (955, 345)],
                [(120, 640), (180, 580)], [(1180, 560), (1200, 620)]]
# the fish's whole outline, its back and belly where leaves lie over them carried on as the art's shows them
FISH_OUTLINE = [(100, 800), (125, 760), (170, 715), (230, 680), (300, 650), (370, 625), (440, 595), (480, 545),
                (530, 487), (600, 476), (660, 471), (720, 470), (790, 468), (860, 462), (930, 455), (985, 445),
                (1010, 440), (1050, 465),
                (1095, 480), (1075, 540), (1035, 600), (985, 665), (930, 725), (870, 775), (800, 815), (720, 845),
                (640, 870), (560, 890), (470, 905), (380, 908), (300, 895), (230, 875), (160, 850), (115, 825)]
# where each fin joins the body (art pixels): it stands in the plane through the body's surface there, facing the eye
ROOTS = {'tail': (1040, 470), 'dorsal': (595, 480)}
EYE = (234, 737), (32, 25), (236, 740), 7   # the eye: its middle and half-widths (an ellipse), its pupil's middle and
                                            # radius (art pixels)
CHANNELS = ['back', 'belly', 'glow', 'fdark', 'ray', 'orbit', 'erim', 'pupil', 'lgreen', 'ldeep', 'llight',
            'groove']
# the fish's colours in the art, blocked in as a painter would (posterize): the dark of its crown and of the lines
# drawn on it (its gill cover, its mouth, its score cuts), its brown flank, its orange (what it is built in), its
# golden cheek and the pale of its lips and lights; the fins' and the tail's dark rays and golden lights
FISH_PALETTE = {'dark': (80, 40, 14), 'brown': (143, 67, 13), 'orange': (200, 115, 40), 'gold': (245, 175, 85),
                'pale': (251, 220, 170)}
FIN_PALETTE = {'dark': (97, 51, 20), 'ray': (147, 81, 35), 'mid': (186, 103, 42), 'light': (210, 139, 74),
               'gold': (237, 185, 120)}
# the leaves' colours in the art, simplified to clean shapes (posterize): their purple, its deeper shade and the
# dark veins, their green rims and the lighter purple where the light catches them
LEAF_PALETTE = {'purple': (123, 62, 80), 'deep': (73, 32, 40), 'green': (95, 110, 37), 'light': (154, 90, 110)}
# (4) by kind: mesh spacing inside and along the outline (m), how high it rises (puff × its half-width, up to top),
# where its outline sits (edge, over what is under it), its relief, and its colours: what it is built in, what is
# painted on it from which channel (the mesh has vertices along each colour's edge), what is tinted in softly
KINDS = {
    'body': dict(gap=0.014, gb=0.0055, puff=0.9, top=0.016, edge=0.0, relief=0.002, mat='ZisuSkin',
                 paint=[('fdark', 'ZisuInk')],
                 tint=[('back', '#6a3c1c', 0.75), ('belly', '#f2c88c', 0.7), ('glow', '#fad08a', 0.75)]),
    'eye': dict(gap=0.0025, gb=0.0015, puff=0.3, top=0.0006, edge=0.0003, relief=0.0, mat='ZisuIris',
                paint=[('orbit', 'ZisuOrbit'), ('erim', 'FishEye'), ('pupil', 'ZisuPupil')], tint=[]),
    'flap': dict(gap=0.008, gb=0.0045, puff=0.5, top=0.0025, edge=0.0008, relief=0.0, mat='ZisuFin',
                 paint=[('ray', 'ZisuFinRay')], tint=[('glow', '#eab478', 0.5)]),
    'fin': dict(gap=0.012, gb=0.0055, puff=0.5, top=0.0025, edge=0.0, relief=0.0, mat='ZisuFin',
                paint=[('ray', 'ZisuFinRay')], tint=[('glow', '#eab478', 0.5)]),
    'bamboo': dict(gap=0.009, gb=0.0035, puff=0.6, top=0.0035, edge=0.0006, relief=0.0, mat='ZisuBamboo',
                   paint=[('groove', 'ZisuGroove')], tint=[]),
    'leaf': dict(gap=0.011, gb=0.0045, puff=0.3, top=0.0012, edge=0.0004, relief=0.0, mat='ZisuLeaf',
                 paint=[('lgreen', 'ZisuLeafGreen'), ('ldeep', 'ZisuLeafDeep')], tint=[]),
}
BODY_MID = 0.012            # the fish's outline sits this far over the dish: its middle, lying on its side
SLOPE = np.tan(np.radians(28))   # the steepest a leaf or a slice falls off the edge of what it lies on
RING = 0.0006
INK = [0.5, 2.2]   # the art's ink line round a piece: full to, gone by (art pixels), inside its ring of vertices
# the fish's ink line, clear and dark as the art draws it: full out to its first ring of vertices (2.7 px in), gone
# by the second (5.4 px)
FISH_RINGS, FISH_INK = (0.0006, 0.0012), [2.8, 2.6]


def groups_of(rgb):
    """Each art pixel's group: 1 a perilla leaf (its purple, its green, its dark veins), 0 anything else. The flood
    never crosses from one group to the other cheaply, so that a leaf's veins and its purple and green don't let its
    neighbours in."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    purple = ((h > 300) | (h < 5)) & (s > 0.25) & (v > 0.12) & (v < 0.78)
    green = (h > 50) & (h < 170) & (s > 0.4) & (v > 0.1) & (v < 0.62)
    leaf = cv2.morphologyEx(u8(purple | green), cv2.MORPH_CLOSE, disk(4))   # its veins and shadows too
    leaf = fill_holes(cv2.morphologyEx(leaf, cv2.MORPH_OPEN, disk(1)))
    g = np.zeros(h.shape, np.int8)
    g[leaf] = 1
    return g


def pale_of(rgb):
    """The art's pale cream and gold of bamboo (and of the fish's lights, which is why it only places seeds)."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    return cv2.morphologyEx(u8((h > 25) & (h < 70) & (v > 0.84)), cv2.MORPH_OPEN, disk(2)).astype(bool)


def along(a, b, ok, n=28):
    """The art pixels along a -> b of the piece's own group (ok: a mask): its seed, as runs of points."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    runs, run = [], []
    for f in np.linspace(0.0, 1.0, n):
        p = a + (b - a) * f
        if ok[int(round(p[1])), int(round(p[0]))]:
            run.append((int(round(p[0])), int(round(p[1]))))
        elif run:
            runs.append(run)
            run = []
    if run:
        runs.append(run)
    return runs


def leaf_and_bamboo_seeds(groups, pale):
    """Each leaf's and bamboo slice's seed: along its middle (the middle of its stalk-to-tip line; its outline's long
    axis through its middle), wherever the art there is of its group."""
    out = []
    for k, (st, tip) in enumerate(LEAVES):
        st, tip = np.asarray(st, float), np.asarray(tip, float)
        out.append((f'leaf{k}', 'leaf', along(st + (tip - st) * 0.15, st + (tip - st) * 0.85, groups == 1)))
    for k, poly in enumerate(BAMBOO):
        q = np.asarray(poly, float)
        c0 = q.mean(0)
        ax = np.linalg.svd(q - c0)[2][0]
        ext = np.abs((q - c0) @ ax).max()
        out.append((f'bamboo{k}', 'bamboo', along(c0 - ax * ext * 0.65, c0 + ax * ext * 0.65, pale & (groups == 0))))
    for name, _, runs in out:
        if not runs:
            print(f'[trace] {name}: no seed where its colour is', flush=True)
    return [(n, k, runs) for n, k, runs in out if runs]


def fish_seeds(rgb, groups, avoid):
    """More seeds for the fish's body: wherever it shows between the leaves and the bamboo (fish-coloured, inside its
    outline, not by its eye, fins or tail), so that every glimpse of it is the fish's."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    poly = Image.new('L', rgb.shape[1::-1], 0)
    ImageDraw.Draw(poly).polygon(FISH_OUTLINE, fill=1)
    inside = cv2.erode(np.asarray(poly, np.uint8), disk(10)).astype(bool)
    pale = cv2.dilate(u8(pale_of(rgb)), disk(4)).astype(bool)   # not the bamboo's cream and gold
    fishy = inside & (groups == 0) & (h > 8) & (h < 50) & (s > 0.3) & (v > 0.25) & (v < 0.84) & ~pale & ~avoid
    return cv2.erode(u8(fishy), disk(6)).astype(bool)


def pieces_of(rgb, zone, seeds, groups, extra_fish):
    """The art cut into its pieces: a flood from the seeds ({piece: [runs of art pixels]}) and the dish's
    (DISH_STROKES), lowest ground first, the ground being the change of colour, the art's ink lines and the edges
    between groups standing high as walls. Returns the piece numbers per pixel (0: the dish)."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    s, v = hsv[..., 1] / 255, hsv[..., 2] / 255
    lab_ = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.0), cv2.COLOR_RGB2LAB).astype(np.float32)
    grad = sum(np.abs(cv2.Sobel(lab_[..., c], cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(lab_[..., c], cv2.CV_32F, 0, 1))
               for c in range(3))
    wall = (v < 0.45) & (s > 0.35)
    edge = np.zeros(groups.shape, bool)
    edge[:, 1:] |= groups[:, 1:] != groups[:, :-1]
    edge[1:, :] |= groups[1:, :] != groups[:-1, :]
    edge = cv2.dilate(u8(edge), disk(1)).astype(bool)
    # the edges between groups higher than the ink walls, which run inside leaves too (their deep purple)
    elev = grad + 2000.0 * cv2.GaussianBlur(wall.astype(np.float32), (0, 0), 1.5) + 5000.0 * edge
    H, W = groups.shape
    mk = Image.new('I', (W, H), 0)
    d = ImageDraw.Draw(mk)
    for line in DISH_STROKES:
        d.line(line, fill=1, width=9)
    for pid, runs in seeds.items():
        for run in runs:
            if len(run) > 1:
                d.line(run, fill=pid + 1, width=5)
            for x, y in run:
                d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=pid + 1)
    markers = np.asarray(mk, np.int32).copy()
    fish_pid = 1   # the fish's body is the first piece
    markers[extra_fish & (markers == 0)] = fish_pid + 1
    markers[~zone] = 1
    lab = flood(markers, elev)
    lab[~zone] = 1
    return np.where(lab > 1, lab - 1, 0)


def classes(rgb, pieces, names, body_all):
    """The colour classes of CHANNELS over the art."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    H, W = h.shape
    yy, xx = np.mgrid[0:H, 0:W]
    kinds = [k for _, k, _ in names]
    of = lambda kind: np.isin(pieces, [i + 1 for i, k in enumerate(kinds) if k == kind])
    body, eye = of('body'), of('eye')
    fins = of('flap') | of('fin')
    leaves, bamboo = of('leaf'), of('bamboo')
    # the back's grey-brown and the belly's pale gold: how far down the whole fish each pixel is
    # its colours as soft washes, as the art shades it, not blocks: the brown back fading into the pale gold belly
    # (how far down the whole fish each pixel is) and the golden lights where the art is brighter than round about
    whole = body | eye
    rows = np.where(whole.any(0), np.argmax(whole, 0), 0), np.where(whole.any(0), H - 1 - np.argmax(whole[::-1], 0), 0)
    t = (yy - rows[0][None, :]) / np.maximum(rows[1] - rows[0], 1)[None, :]
    ramp = lambda e0, e1, x: np.clip((x - e0) / (e1 - e0), 0, 1)
    back = np.where(whole, ramp(0.4, 0.05, t), 0.0)
    belly = np.where(whole, ramp(0.6, 0.92, t), 0.0)
    lum_ = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    m_ = (body | fins).astype(np.float32)
    local = cv2.GaussianBlur(lum_ * m_, (0, 0), 14) / np.maximum(cv2.GaussianBlur(m_, (0, 0), 14), 1e-3)
    glow = (body | fins) & (lum_ > local + 16)
    soft = lambda m, sg: np.clip(cv2.GaussianBlur(m.astype(np.float32), (0, 0), sg) * 255 + 0.5, 0,
                                 255).astype(np.uint8)
    np_ = posterize(rgb, fins, list(FIN_PALETTE.values()), passes=(2, 2), speck=120)
    # the lines the art draws on the fish (its gill cover's arcs, its mouth, its score cuts) and the fins' rays:
    # strokes darker than round about, long ones (not specks)
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    bh = cv2.morphologyEx(cv2.GaussianBlur(lum, (0, 0), 1.5), cv2.MORPH_BLACKHAT, disk(8))

    def strokes(region, th, min_area, min_len, fill=1.0):
        m = cv2.morphologyEx(u8(region & (bh > th) & (v < 0.75)), cv2.MORPH_CLOSE, disk(2))
        n, cc, st, _ = cv2.connectedComponentsWithStats(m)
        keep = np.zeros(n, bool)
        w_, h_ = st[1:, cv2.CC_STAT_WIDTH], st[1:, cv2.CC_STAT_HEIGHT]
        keep[1:] = (st[1:, cv2.CC_STAT_AREA] > min_area) & (np.maximum(w_, h_) > min_len) & \
            (st[1:, cv2.CC_STAT_AREA] < fill * w_ * h_)   # lines, not blots
        return keep[cc]
    # not the speckles over its crown, above its eye (the art's lines there are long arcs)
    crown = (yy < EYE[0][1] - 20) & (xx < 520)
    fdark = strokes(body & ~crown & cv2.erode(u8(body | eye), disk(6)).astype(bool), 32, 160, 50, fill=0.4)
    fdark = cv2.dilate(u8(fdark), disk(2)).astype(bool) & body   # as thick as the art's brush lines
    ray = strokes(fins & cv2.erode(u8(fins), disk(3)).astype(bool), 30, 80, 35, fill=0.4) | \
        (np_ == list(FIN_PALETTE).index('dark'))
    groove = cv2.morphologyEx(u8(bamboo & cv2.erode(u8(bamboo), disk(4)).astype(bool) & (s > 0.62)), cv2.MORPH_OPEN,
                              disk(1)).astype(bool)   # the slits cut in it, gold against its cream
    (ex, ey), (rx, ry), (px, py), pr = EYE
    rr = np.sqrt(((xx - ex) / rx) ** 2 + ((yy - ey) / ry) ** 2)   # 1 at the eye's outline
    orbit = eye & (rr > 0.88)                                    # its pale orbit
    erim = eye & (rr > 0.72) & (rr <= 0.88)                      # its dark rim
    pupil = eye & ((xx - px) ** 2 + (yy - py) ** 2 < pr ** 2)
    poster = posterize(rgb, leaves, list(LEAF_PALETTE.values()), passes=(4, 4, 3), speck=250)
    lgreen, ldeep, llight = (poster == list(LEAF_PALETTE).index(k) for k in ('green', 'deep', 'light'))
    food = pieces > 0
    tones = np.stack([soft(back, 6.0), soft(belly, 6.0), soft(glow, 4.0)], -1)
    blocks = paint_channels([fdark, ray], food, smooth=1.2, min_area=40, close=1)
    eyes = paint_channels([orbit, erim, pupil], food, smooth=0.8, min_area=10, close=0)
    leafy = paint_channels([lgreen, ldeep, llight], food, smooth=2.0, min_area=160, close=2)
    grooves = paint_channels([groove], food, smooth=1.0, min_area=25, close=1)
    return np.concatenate([tones, blocks, eyes, leafy, grooves], -1)


def envelope(depth):
    """What the leaves and the slices lie on, as heights per art pixel: the surface the art shows there (depth: its
    depths), raised where something higher is near so that nothing they lie on falls away more steeply than SLOPE: a
    leaf off the fish's back runs on from it and down to the dish gently, as a leaf would, not down its side (where
    its underside would show from behind)."""
    H, W = depth.shape
    yy = np.mgrid[0:H, 0:W][0].astype(np.float32)
    q = (CAM.v0 - yy) / CAM.k
    z = np.where(np.isfinite(depth), q * CAM.ce - depth * CAM.se, -1.0).astype(np.float32)
    fall = SLOPE * 1.2 / CAM.k   # over one pixel's worth of ground
    for _ in range(240):
        z = np.maximum(z, cv2.dilate(z, np.ones((3, 3), np.uint8)) - fall)
    return z


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    H, W = alpha.shape
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    zone = alpha > 128
    groups = groups_of(rgb)
    # the fish's seeds dots, not lines: its strokes jump from glimpse to glimpse of it, over leaves and bamboo
    pieces_def = [(n, k, [[q] for q in st]) for n, k, st in FISH] + leaf_and_bamboo_seeds(groups, pale_of(rgb))
    seeds = {i + 1: runs for i, (_, _, runs) in enumerate(pieces_def)}
    (ex, ey), (rx, ry) = EYE[:2]
    yy, xx = np.mgrid[0:H, 0:W]
    avoid = ((((xx - ex) / (rx + 12)) ** 2 + ((yy - ey) / (ry + 12)) ** 2) < 1) | \
        ((xx > 465) & (xx < 640) & (yy > 710) & (yy < 830)) | (xx > 980) | (yy < 478)   # the eye, the fins, the tail
    pieces = pieces_of(rgb, zone, seeds, groups, fish_seeds(rgb, groups, avoid))
    names = [n for n, _, _ in pieces_def]
    fish_id, eye_id = names.index('fish') + 1, names.index('eye') + 1
    pieces[pieces == eye_id] = fish_id   # the eye: an ellipse where the art draws it, its rim and all
    pieces[(((xx - ex) / rx) ** 2 + ((yy - ey) / ry) ** 2 < 1) & (pieces == fish_id)] = eye_id
    print(f'[trace] {pieces.max()} pieces', flush=True)
    # the fish's whole body: its outline, under the leaves too (but not what lies off it on the dish)
    poly = Image.new('L', (W, H), 0)
    ImageDraw.Draw(poly).polygon(FISH_OUTLINE, fill=1)
    tail_id = names.index('tail') + 1
    body_all = ((np.asarray(poly) > 0) & (pieces > 0) & (pieces != tail_id)) | (pieces == fish_id)
    body_all = fill_holes(cv2.morphologyEx(u8(body_all), cv2.MORPH_OPEN, disk(3)))
    paint = classes(rgb, pieces, pieces_def, body_all)
    dish_V, dish_T = dish_mesh(DISH)
    print(f'[trace] the dish and its sauce: {len(dish_T)} triangles', flush=True)
    floor = Grid.top_of(dish_V, dish_T)
    zdish = np.full((H, W), np.inf)   # the dish's depths as the art sees it
    du, dv = CAM.project(dish_V[:, 0], dish_V[:, 1], dish_V[:, 2])
    raster(np.stack([du, dv], -1)[dish_T], CAM.depth(dish_V)[dish_T], np.zeros(len(dish_T), np.int32), H, W, zdish,
           np.full((H, W), -1, np.int32))
    on_dish = lambda u, v: CAM.depth(np.stack(CAM.backproject(u, v, floor), -1))
    # (4) the surfaces, each piece in turn over what is there already
    zb, zid = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
    union = pieces > 0
    out = []
    base = None
    for pid, (name, kind, _) in enumerate(pieces_def, 1):
        kp = KINDS[kind]
        if kind == 'body':
            mk = body_all
        else:
            mk = cv2.morphologyEx(u8(pieces == pid), cv2.MORPH_OPEN, disk(2))
            if not mk.any():
                continue
            mk = largest(mk)
            mk = fill_holes(cv2.dilate(u8(mk), disk(2)).astype(bool) & union)   # a little under its neighbours
        mk = cv2.GaussianBlur(mk.astype(np.float32), (0, 0), 2.0) > 0.5
        if mk.sum() < 150:
            continue
        edges = [(paint[..., CHANNELS.index(c)] > 127) & mk for c, _ in kp['paint']]   # where its colours change
        extra = contour_points(edges, {'body': 30.0, 'fin': 16.0, 'leaf': 18.0, 'eye': 10.0}.get(kind, 14.0))
        fishy = kind in ('body', 'fin', 'flap')
        uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, kp['gap'], kp['gb'],
                                                FISH_RINGS if kind in ('body', 'leaf') else RING if kind != 'eye'
                                                else 0.0002,
                                                smooth_px=1.5 if kind in ('eye', 'leaf') else 2.5 if kind != 'body'
                                                else 5.0, extra=extra)
        band = shading_band(lum, mk, 4.0, 18.0)
        iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
        ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
        top = float(np.clip(kp['puff'] * R, 0.0008, kp['top']))
        L = profile(d, R, top, kp['edge'], 0.0, lean, kp['relief'], band[iy, ix])
        L = smooth_inner(L, nb, neighbours(len(uv), tris))
        if kind == 'body':
            P, T = lying(CAM, uv, tris, nb, L, lambda x, y: floor(x, y) + BODY_MID, close=floor)
        elif kind == 'fin':
            ru, rv = ROOTS[name]
            s_root = on_top(CAM, zb, ru, rv, r=8)
            if s_root is None:
                s_root = float(CAM.depth(np.stack(CAM.backproject(np.array([float(ru)]), np.array([float(rv)]),
                                                                  lambda x, y: floor(x, y) + BODY_MID), -1))[0])
            anchor = CAM.on_ray(ru, rv, s_root)
            ub, tb, nbb, db, Rb, _ = outline_mesh(CAM, mk, 0.03, kp['gb'], 0.0, smooth_px=2.5)
            assert nbb == nb and np.allclose(ub[:nb], uv[:nb])
            P, T = standing(CAM, uv, tris, nb, L, profile(db, Rb, float(np.clip(kp['puff'] * Rb, 0.0008, kp['top']))),
                            anchor, back=(ub, tb))
            P = above(CAM, P, floor, front=len(uv))
            P = before(CAM, P, zdish, (ru, rv))   # in front of the rim it crosses (the tail)
        elif kind in ('eye', 'flap'):   # lying on the fish
            P, T = over(CAM, uv, tris, L, zb, on_dish)
        else:   # a bamboo slice or a leaf: on what is under it, draped over its edges
            if base is None:
                base = envelope(np.where(np.isfinite(zb), zb, zdish))
            q = (CAM.v0 - uv[:, 1]) / CAM.k   # each point on its line of sight, L over the envelope
            P = CAM.on_ray(uv[:, 0], uv[:, 1], (q * CAM.ce - (base[iy, ix] + L)) / CAM.se)
            T = oriented(P, tris, CAM.toward, True)
            P = above(CAM, P, floor, gap=0.0004)
        front = [t for t in T if max(t) < len(uv)]
        pu, pv = CAM.project(P[:, 0], P[:, 1], P[:, 2])
        raster(np.stack([pu, pv], -1)[np.array(front)], CAM.depth(P)[np.array(front)], np.full(len(front), pid),
               H, W, zb, zid)
        out.append({'name': name, 'kind': kind, 'mat': kp['mat'], 'rim': nb,
                    'paint': [(CHANNELS.index(c), m) for c, m in kp['paint']],
                    'tint': [(CHANNELS.index(c), col, w) for c, col, w in kp['tint']],
                    'ink': FISH_INK if kind in ('body', 'leaf') else [0.0, 0.0] if kind == 'eye' else INK,
                    **({'closed': len(uv)} if kind == 'body' else {}),   # its front's points; then skirt and floor
                    'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]})
        print(f'[trace] {name}: {len(T)} triangles, R {R * 100:.1f} cm, top {top * 1000:.1f} mm', flush=True)
    print(f'[trace] all: {sum(len(o["tris"]) for o in out)} triangles', flush=True)
    np.savez_compressed(PAINT, paint=paint[::2, ::2])   # half the art's size: the classes are smooth
    data = {'camera': {'el': CAM.el, 'k': CAM.k, 'u0': CAM.u0, 'v0': CAM.v0}, 'paint_scale': 0.5,
            'channels': CHANNELS, 'pieces': out, 'bits': []}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT} and {PAINT}', flush=True)
    if sheet:
        tints = {'body': (200, 130, 70), 'eye': (230, 190, 90), 'flap': (220, 150, 90), 'fin': (220, 150, 90),
                 'bamboo': (250, 225, 160), 'leaf': (140, 80, 120)}
        shown = pieces.copy()
        shown[body_all & (pieces == fish_id)] = fish_id
        n_leaf = sum(k == 'leaf' for _, k, _ in pieces_def)
        n_bam = sum(k == 'bamboo' for _, k, _ in pieces_def)
        tracing_sheet(sheet, rgba, shown, names, [tints[k] for _, k, _ in pieces_def], (),
                      crop=(20, 200, 1250, 1080),
                      title=('原图上的描线（蓝：每一块）', f'描出的 {pieces.max()} 块：鱼身、鱼眼、胸鳍、背鳍、鱼尾、'
                                                    f'{n_bam} 片笋、{n_leaf} 片紫苏'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
