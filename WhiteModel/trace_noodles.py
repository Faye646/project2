"""Traces the noodle dishes' art so that what is in the bowl is modelled 1:1 (勾勒): 菜面 (新建文件夹/菜面.png) for D02,
插肉面 (插肉面.png) for D09 and 冷淘 (冷淘.png) for D11. Writes food_models/traced_<ID>.json and the colours of its
pieces (traced_<ID>_paint.npz), which bowls.caimian, bowls.charou_mian and bowls.lengtao build the food from, and a
tracing sheet.

    python WhiteModel/trace_noodles.py D02|D09|D11 [--sheet <out.png>]

1. The art's camera and the bowl: fitted together (the bowl's shape too) so that the bowl covers the art's silhouette
   and its lip and its broth meet where the art draws them: the front of the lip where the food goes under it, the
   back of the broth where it meets the bowl's wall (BOWLS). The bowl and its broth are built by Blender with
   bowls.round_bowl; what the art's camera sees of the broth is where the food floats (冷淘: inside the lip, the
   nest of noodles heaped over the dressing).
2. What each pixel is: the art's colours blocked in (posterize), the noodles told from the broth by being lighter and
   less yellow, a flood from seeds of each over the change of colour. Then the pieces: every noodle cut out strand by
   strand along the dark lines the art draws where one lies over another (a flood from each strand's core, the
   lines high ground), and from the strokes laid along strands by eye (STRANDS) where the lines are faint; the
   leaves, slices of pork, heads of bok choy, strips of cucumber from strokes along each (read off the art by eye);
   the cut scallion and the drops of oil each a patch of their colour.
3. Their colours, as a painter would block them in: the noodles' shaded edges and the darker side of each strand
   tinted in; the leaves' dark green painted on, their pale veins and ribs tinted in; the pork's lean, fat and
   browned rind; the bok choy's dark blades and pale stalks; the cucumber's dark skin; the scallion's pale cut ends.
4. Each piece a surface floating on the broth (on the nest) over its outline, so that from the art's camera it
   covers exactly what the art paints: each noodle a round strand (its outline and a row of points along its middle,
   raised to a rounded ridge), the toppings rounded slabs and leaves with the art's shading in relief, lying on what
   is under them.
"""
import json
import os
import subprocess
import sys
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw

from trace_common import (HERE, Camera, contour_points, disk, ear_clip, fill_holes, flood, largest, neighbours,
                          outline_mesh,
                          over, paint_channels, posterize, profile, raster, shading_band, smooth_inner, tracing_sheet,
                          u8)

KEY = sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('--') else 'D02'
OUT = os.path.join(HERE, 'food_models', f'traced_{KEY}.json')
PAINT = os.path.join(HERE, 'food_models', f'traced_{KEY}_paint.npz')

# (1) the camera and the bowl, fitted to the art (bowl_fit in the report), and what the food lies on
BOWLS = {
    'D02': dict(art='菜面.png', cam=(39.08568, 6599.69789, 765.99293, 777.26594), n=40, fill='CaimianBroth',
                bowl="round_bowl(tmp, rim_r=0.08, h=0.07405, foot_r=0.04257, foot_h=0.01953, fill_z=0.05942, "
                     "lean=1.22844, t=0.00544, fill='CaimianBroth', n=40, light=True)"),
    'D09': dict(art='插肉面.png', cam=(38.75259, 7005.78904, 625.99808, 980.20352), n=48, fill='CharouBroth',
                bowl="round_bowl(tmp, rim_r=0.081, h=0.08282, foot_r=0.03628, foot_h=0.02145, fill_z=0.07121, "
                     "lean=1.23659, t=0.00344, fill='CharouBroth', n=48, light=True)"),
    'D11': dict(art='冷淘.png', cam=(36.07684, 6827.19709, 625.18172, 984.21408), n=40, fill='LengtaoDressing',
                bowl="round_bowl(tmp, rim_r=0.085, h=0.07309, foot_r=0.02966, foot_h=0.00746, fill_z=0.04281, "
                     "fill='LengtaoDressing', t=0.003, n=40, light=True, flare=(30, 75, 0.4))"),
}
CFG = BOWLS[KEY]
ART = os.path.join(HERE, '..', '新建文件夹', CFG['art'])
CAM = Camera(*CFG['cam'])
FILL_Z = float(CFG['bowl'].split('fill_z=')[1].split(',')[0])


def dish_mesh(build):
    """The bowl built by Blender from `build` (python making Part p): its vertices and triangles. (trace_common's,
    with a file of its own, so that tracings run side by side don't read each other's bowls.)"""
    fd, path = tempfile.mkstemp(suffix='.json')
    os.close(fd)
    os.remove(path)
    script = '\n'.join([
        'import sys, json, bmesh', 'sys.path.insert(0, %r)' % HERE, 'from food_models.core import *',
        'from food_models.plates import *', 'p = Part()', build, 'bm = p.bm',
        'bmesh.ops.triangulate(bm, faces=bm.faces[:])', 'bm.verts.index_update()',
        "json.dump({'V': [list(v.co) for v in bm.verts], 'T': [[v.index for v in f.verts] for f in bm.faces]},"
        ' open(%r, "w"))' % path])
    subprocess.run(['E:/blender.exe', '-b', '--factory-startup', '--python-expr', script], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    if not os.path.exists(path):
        raise RuntimeError('Blender built no bowl: ' + build)
    d = json.load(open(path))
    os.remove(path)
    return np.array(d['V']), np.array(d['T'])


def bowl_view(H, W):
    """The bowl as the art's camera sees it: where its broth shows (and its depths there), where the inside of the
    bowl shows (the broth and the wall above it, inside the lip), and the depths of the whole bowl."""
    n = CFG['n']
    full = dish_mesh('from food_models.bowls import round_bowl\ntmp = p\n' + CFG['bowl'])
    broth = dish_mesh('from food_models.bowls import round_bowl\ntmp = Part()\nfz, rf = ' + CFG['bowl'] +
                      "\np.lathe([(rf, fz), (rf * 0.5, fz + 0.0004), (0.0, fz + 0.0005)], 'Broth', n=%d, "
                      "close_ends=False)" % n)
    V, T = full
    P = V[T]
    nrm = np.cross(P[:, 1] - P[:, 0], P[:, 2] - P[:, 0])
    c = P.mean(1)
    rad = c[:, :2] / np.maximum(np.linalg.norm(c[:, :2], axis=1, keepdims=True), 1e-9)
    inner = ((nrm[:, :2] * rad).sum(1) < 0) & (np.abs(nrm[:, 2]) < np.linalg.norm(nrm, axis=1) * 0.97)
    zb, zid = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
    for VV, TT, ids in ((broth[0], broth[1], np.zeros(len(broth[1]), int)), (V, T, np.where(inner, 2, 1))):
        u, v = CAM.project(VV[:, 0], VV[:, 1], VV[:, 2])
        raster(np.stack([u, v], -1)[TT], CAM.depth(VV)[TT], ids, H, W, zb, zid)
    inside = cv2.morphologyEx(u8((zid == 0) | (zid == 2)), cv2.MORPH_CLOSE, disk(2)).astype(bool)
    zdish = np.where(zid >= 0, zb, np.inf)
    return np.where(zid == 0, zb, np.inf), zid == 0, inside, zdish


LIFT = 0.0006   # the food floats this far over the broth's level (its surface domes 0.5 mm in the middle)


def plane_depth(u, v, z=FILL_Z + LIFT):
    """The depth along the line of sight of the level plane z (the broth) at art pixels (u, v)."""
    return CAM.plane_depth(np.asarray(u, float), np.asarray(v, float), np.array([0.0, 0.0, z]),
                           np.array([0.0, 0.0, 1.0]))


# ------------------------------------------------------------------ the noodles' strands

def thin(m):
    """Zhang-Suen thinning: the mask's middle line, one pixel wide."""
    img = np.pad(m.astype(np.uint8), 1)
    while True:
        changed = False
        for step in (0, 1):
            P = img
            p2, p3, p4, p5 = P[:-2, 1:-1], P[:-2, 2:], P[1:-1, 2:], P[2:, 2:]
            p6, p7, p8, p9 = P[2:, 1:-1], P[2:, :-2], P[1:-1, :-2], P[:-2, :-2]
            nb = [p2, p3, p4, p5, p6, p7, p8, p9]
            B = sum(x.astype(np.int32) for x in nb)
            seq = nb + [p2]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(np.int32) for i in range(8))
            if step == 0:
                cond = ((p2 * p4 * p6) == 0) & ((p4 * p6 * p8) == 0)
            else:
                cond = ((p2 * p4 * p8) == 0) & ((p2 * p6 * p8) == 0)
            rm = (P[1:-1, 1:-1] == 1) & (B >= 2) & (B <= 6) & (A == 1) & cond
            if rm.any():
                img[1:-1, 1:-1][rm] = 0
                changed = True
        if not changed:
            return img[1:-1, 1:-1].astype(bool)


def axis_points(mask, spacing, min_d=2.5):
    """Points about `spacing` art pixels apart along the middle of a strand (its thinned mask), each at least min_d
    in from its outline."""
    x0, y0, w, h = cv2.boundingRect(u8(mask))
    sub = mask[y0:y0 + h, x0:x0 + w]
    sk = thin(sub)
    dt = cv2.distanceTransform(u8(np.pad(sub, 1)), cv2.DIST_L2, 5)[1:-1, 1:-1]
    ys, xs = np.nonzero(sk & (dt >= min_d))
    if not len(xs):
        return np.zeros((0, 2))
    order = np.argsort(-dt[ys, xs])   # the widest first, then along it
    taken = []
    cell = {}
    for i in order:
        x, y = xs[i], ys[i]
        gx, gy = int(x // spacing), int(y // spacing)
        ok = True
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for (qx, qy) in cell.get((gx + dx, gy + dy), ()):
                    if (qx - x) ** 2 + (qy - y) ** 2 < spacing * spacing * 0.8:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            taken.append((x, y))
            cell.setdefault((gx, gy), []).append((x, y))
    return np.array(taken, float).reshape(-1, 2) + np.array([x0, y0])


def strand_cut(N, lum, strokes, R=5, TH=7.0, amin=120):
    """The noodles (mask N) cut into strands: the dark lines the art draws where one lies over another (black-hat
    over the light) are high ground; each strand's core (what the lines leave, in one piece) and the strokes laid
    along strands by eye (STRANDS: they replace the cores they cross) flood the noodles from the lowest ground.
    Returns strand numbers per pixel (0 elsewhere), the strokes' strands first."""
    H, W = N.shape
    bh = cv2.morphologyEx(lum, cv2.MORPH_BLACKHAT, disk(R))
    lines = (bh > TH) & N
    cores = N & ~cv2.dilate(u8(lines), disk(1)).astype(bool)
    cores = cv2.morphologyEx(u8(cores), cv2.MORPH_OPEN, disk(2))
    st_img = Image.new('I', (W, H), 0)
    d = ImageDraw.Draw(st_img)
    for k, line in enumerate(strokes, 1):
        d.line([tuple(q) for q in line], fill=k, width=5)
        for x, y in line:
            d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=k)
    st = np.asarray(st_img, np.int32) * N
    n, cc, stats, _ = cv2.connectedComponentsWithStats(cores)
    keep = np.zeros(n, bool)
    keep[1:] = stats[1:, cv2.CC_STAT_AREA] >= amin
    hit = np.unique(cc[(st > 0) & (cc > 0)])   # the cores a stroke crosses give way to it
    keep[hit] = False
    mk = np.where(N, 0, -1).astype(np.int32)
    lab = np.where(keep[cc], cc + len(strokes), 0)
    mk[lab > 0] = lab[lab > 0]
    mk[st > 0] = st[st > 0]
    got = flood(mk, bh)
    got[~N] = 0
    ids = [i for i in np.unique(got) if i > 0]
    remap = np.zeros(got.max() + 1, np.int32)
    remap[ids] = np.arange(1, len(ids) + 1)
    return remap[got], bh


# ------------------------------------------------------------------ (2) what is where, per dish (art pixels)

# the kinds of piece, by number in the kind map (0 the broth, 1 the noodles)
KIND_CODES = {'leaf': 2, 'scallion': 3, 'pork': 4, 'bokleaf': 5, 'bokstalk': 6, 'cucumber': 7, 'herb': 8,
              'drop': 9}
STRANDS = []        # strokes along strands where the art's lines between them are faint
RIM = 12            # the band of bare broth along the lip (art pixels)
NOODLE = (46, -4, 6)   # a noodle's seed: L - 0.9 b over this, a* between these (Lab): lighter, less yellow
AUTO = []           # pieces found by their colour: (kind, test(L, a, b), area range, opening radius)
if KEY == 'D02':
    # the napa cabbage: a stroke along each leaf, its stalk end first; the cut scallion, each piece's middle
    TOPPINGS = {'Lback': ('leaf', [[(1170, 432), (1100, 385), (1030, 345), (960, 300), (880, 265), (800, 240),
                                    (720, 222)], [(990, 230), (1010, 275), (1040, 320)]]),
                'Lleft': ('leaf', [[(410, 410), (470, 395), (540, 385), (620, 395), (700, 410)]]),
                'Lmid': ('leaf', [[(400, 470), (470, 480), (550, 495), (640, 520), (720, 545), (790, 570),
                                   (845, 597)]]),
                'Lfront': ('leaf', [[(860, 662), (920, 652), (980, 640), (1030, 652)]])}
    SEEDS = {'scallion': [(718, 195), (606, 225), (595, 303), (462, 298), (485, 312), (705, 347), (810, 342),
                          (865, 400), (862, 432), (935, 417), (1197, 397), (1210, 425), (1047, 441), (1035, 485),
                          (352, 530), (1082, 575), (455, 610), (855, 313), (1080, 293), (720, 455), (775, 495),
                          (905, 550), (925, 525), (722, 620), (868, 625), (862, 580)]}
    # the colours in the bowl, blocked in as a painter would: the noodles' light, their shaded edges; the cabbage's
    # pale blade, its white veins and ribs, its mid and dark greens
    CLASSES = {'noodle': {'light': (249, 241, 214), 'shade': (238, 220, 160), 'deep': (222, 192, 116)},
               'leaf': {'pale': (214, 220, 120), 'vein': (238, 242, 205), 'mid': (160, 190, 60),
                        'dark': (88, 128, 22), 'deep': (60, 100, 15)}}
elif KEY == 'D09':
    # the braised pork, a stroke along each slice from back to front; the bok choy's leaves and stalks
    TOPPINGS = {'P1': ('pork', [[(450, 400), (520, 395), (580, 410)]]),
                'P2': ('pork', [[(280, 490), (340, 480), (400, 475), (450, 480)]]),
                'P3': ('pork', [[(250, 600), (310, 585), (370, 570)]]),
                'P4': ('pork', [[(420, 620), (480, 590), (540, 570)]]),
                'P5': ('pork', [[(560, 680), (650, 660), (750, 660), (850, 690)], [(620, 760), (720, 765)]]),
                'BL1': ('bokleaf', [[(690, 330), (760, 320), (830, 360)], [(700, 400), (780, 420), (850, 470)]]),
                'BS1': ('bokstalk', [[(890, 380), (900, 440), (915, 510), (930, 580), (945, 640)]]),
                'BL2': ('bokleaf', [[(990, 400), (1030, 430), (1070, 470)]]),
                'BS2': ('bokstalk', [[(1020, 480), (1050, 540), (1075, 600)]])}
    SEEDS = {}
    AUTO = [('scallion', lambda L, a, b: (a < -20) & (L > 50) & (b > 30), (150, 3500), 2)]
    CLASSES = {'noodle': {'light': (250, 243, 218), 'shade': (240, 222, 165), 'deep': (225, 196, 120)},
               'pork': {'fat': (246, 214, 200), 'lean': (222, 160, 140), 'rind': (176, 94, 62),
                        'deep': (128, 62, 36)},
               'bokleaf': {'vein': (130, 170, 80), 'leaf': (70, 120, 40), 'dark': (35, 75, 20)},
               'bokstalk': {'pale': (226, 236, 196), 'green': (180, 205, 120)}}
    RIM = 14
elif KEY == 'D11':
    # the nest of noodles heaped over the dressing: the cucumber strips, the herb leaves and the drops of dressing
    # found by their colours (AUTO), the noodles the peach-cream between them, the bowl's wall what is celadon
    TOPPINGS, SEEDS = {}, {}
    AUTO = [('cucumber', lambda L, a, b: (L > 60) & (a < -6) & (b > 32), (150, 9000), 2),
            ('herb', lambda L, a, b: (L <= 56) & (a < -8), (250, 20000), 6)]
    NOODLE = None
    CLASSES = {'noodle': {'light': (252, 238, 214), 'shade': (246, 210, 160), 'deep': (236, 160, 90)},
               'herb': {'light': (130, 175, 60), 'leaf': (70, 125, 35), 'dark': (35, 80, 15)},
               'cucumber': {'flesh': (205, 220, 130), 'pale': (230, 236, 180), 'skin': (60, 110, 30)}}
    RIM = 6
    NEST = dict(h=0.05, r=0.069, c=(0.0, 0.004), power=0.4)   # the heap the noodles lie on: its height over the
                                                               # dressing, its radius and middle, its roundness


def nest_height(x, y):
    """冷淘's heap of noodles over its dressing: a round dome (NEST) the strands and toppings lie on."""
    c = NEST['c']
    q = 1 - ((np.asarray(x) - c[0]) ** 2 + (np.asarray(y) - c[1]) ** 2) / NEST['r'] ** 2
    return FILL_Z + NEST['h'] * np.clip(q, 0, 1) ** NEST['power']


def what_is_where(rgb, zone):
    """Each pixel's piece in the bowl: a flood of the art from seeds of each, over the change of colour: the broth's
    (where it is plainly broth, and in a band along the lip), the noodles' (the broth's lighter, less yellow pixels:
    NOODLE), each topping's strokes (TOPPINGS) and seed points (SEEDS, and the small pieces of AUTO's colour).
    Returns the flood (1 broth, 2 noodles, 10 on: the toppings) and {name: (number, kind)}."""
    H, W = zone.shape
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.0), cv2.COLOR_RGB2LAB).astype(np.float32)
    L, a, b = lab[..., 0] * 100 / 255, lab[..., 1] - 128, lab[..., 2] - 128
    grad = sum(np.abs(cv2.Sobel(lab[..., c], cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(lab[..., c], cv2.CV_32F, 0, 1))
               for c in range(3))
    green = zone & (a < -9) & (b > 18)
    if NOODLE is None:   # 冷淘: peach-cream noodles in the nest; the bowl's celadon wall round it is no food: the
        noodle = zone & (a > -1) & (a < 14) & (L > 74) & (b < 45) & (b > 18)   # band inside the lip at the back and
        broth = zone & (L > 78) & (b < 14)                                      # sides, and its palest celadon
        ys, xs = np.nonzero(zone)
        cy, ry = (ys.min() + ys.max()) / 2, (ys.max() - ys.min()) / 2
        yy = np.mgrid[0:H, 0:W][0]
        rim = zone & ~cv2.erode(u8(zone), disk(16)).astype(bool) & (yy < cy + 0.35 * ry)
    else:
        noodle = zone & (a > NOODLE[1]) & (a < NOODLE[2]) & (L - 0.9 * b > NOODLE[0])
    if NOODLE is not None:   # not the light on a pale stalk (the greens' region, holes and all), nor in a slice
        m = fill_holes(cv2.morphologyEx(u8(green), cv2.MORPH_CLOSE, disk(7)))   # of pork (its colour, closed)
        m = cv2.morphologyEx(u8(m), cv2.MORPH_OPEN, disk(5)).astype(bool)
        noodle &= ~cv2.dilate(u8(m), disk(3)).astype(bool)
        m = cv2.morphologyEx(u8(zone & (a > 9) & (b < 2.8 * a)), cv2.MORPH_CLOSE, disk(4))
        noodle &= ~cv2.dilate(m, disk(2)).astype(bool)
    if NOODLE is not None:
        broth = zone & ~green & (L - 0.9 * b < NOODLE[0] - 16) & (a < 8)
        rim = zone & ~cv2.erode(u8(zone), disk(RIM)).astype(bool)   # the broth's pale light along the lip is broth
    canvas = Image.new('I', (W, H), 0)
    d = ImageDraw.Draw(canvas)
    ids = {}
    for name, (kind, lines) in TOPPINGS.items():
        ids[name] = (len(ids) + 10, kind)
        for line in lines:
            d.line(line, fill=ids[name][0], width=9)
    seeds = {k: list(v) for k, v in SEEDS.items()}
    for kind, test, (amin, amax), r_open in AUTO:
        m = cv2.morphologyEx(u8(zone & test(L, a, b)), cv2.MORPH_OPEN, disk(r_open))
        n, cc, st, cen = cv2.connectedComponentsWithStats(m)
        g = cv2.morphologyEx(u8(green), cv2.MORPH_CLOSE, disk(3))   # not a bright patch on a leaf: the big greens
        gn, gcc, gst, _ = cv2.connectedComponentsWithStats(g)
        big = np.zeros(gn, bool)
        big[1:] = gst[1:, cv2.CC_STAT_AREA] > 6000
        leafy = cv2.dilate(u8(big[gcc]), disk(3)).astype(bool) if kind == 'scallion' else np.zeros_like(zone)
        seeds.setdefault(kind, [])
        seeds[kind] += [tuple(int(round(q)) for q in cen[i]) for i in range(1, n)
                        if amin <= st[i, 4] <= amax and not leafy[int(round(cen[i][1])), int(round(cen[i][0]))]]
    for kind, pts in seeds.items():
        for k, (x, y) in enumerate(pts):
            ids[f'{kind[0].upper()}{k}'] = (len(ids) + 10, kind)
            d.ellipse((x - 4, y - 4, x + 4, y + 4), fill=ids[f'{kind[0].upper()}{k}'][0])
    mk = np.asarray(canvas, np.int32).copy()
    if NOODLE is None:   # 冷淘: first the nest from the bowl's wall round it (a flood of the two), the toppings in it
        mw = np.zeros((H, W), np.int32)
        wall = zone & ~cv2.erode(u8(zone), disk(40)).astype(bool) & (yy < cy + 0.35 * ry)   # well inside the lip
        mw[(mk > 0) | cv2.erode(u8(noodle), disk(3)).astype(bool) | (zone & (L <= 56) & (a < -8))] = 2
        mw[cv2.erode(u8(broth), disk(2)).astype(bool) | wall | ~zone] = 1
        nest = flood(mw, grad) == 2
        nest = fill_holes(largest(cv2.morphologyEx(u8(nest), cv2.MORPH_OPEN, disk(3))))
        mk[~nest] = 1
    free = lambda m, r: cv2.erode(u8(m), disk(r)).astype(bool) & (mk == 0)
    mk[free(broth, 3)] = 1
    mk[free(noodle, 3)] = 2
    mk[~zone | rim] = 1
    if KEY == 'D09':   # the pork and the greens each a group of their own, their edges walls the flood crosses last,
        group = np.zeros((H, W), np.int8)   # and inside the pork the dark rind round each slice a wall too
        pork = zone & (a > 9) & (b < 2.8 * a) & (L > 25)   # pink and brown, not the noodles' orange shade
        pork = fill_holes(cv2.morphologyEx(u8(pork), cv2.MORPH_CLOSE, disk(4)))
        pork = cv2.morphologyEx(u8(pork), cv2.MORPH_OPEN, disk(4)).astype(bool)
        greens = cv2.morphologyEx(u8(green), cv2.MORPH_CLOSE, disk(3)).astype(bool)
        group[pork] = 1
        group[greens] = 2
        edge = np.zeros((H, W), bool)
        edge[:, 1:] |= group[:, 1:] != group[:, :-1]
        edge[1:, :] |= group[1:, :] != group[:-1, :]
        rind = pork & (L < 52) & (a > 10)
        grad = grad + 5000.0 * cv2.dilate(u8(edge), disk(1)) + 1500.0 * cv2.GaussianBlur(rind.astype(np.float32),
                                                                                           (0, 0), 1.2)
        mk[(mk == 2) & (group > 0)] = 0   # no noodle seed in them
    got = flood(mk, grad)
    got[~zone | rim] = 1
    return got, ids


def kinds_of(got, ids):
    """The kind map and the toppings' masks {name: (mask, kind)} from the flood."""
    kind = np.zeros(got.shape, np.int8)
    kind[got == 2] = 1
    pieces = {}
    for name, (i, k) in ids.items():
        m = got == i
        if m.any():
            kind[m] = KIND_CODES[k]
            pieces[name] = (m, k)
    return kind, pieces


# ------------------------------------------------------------------ (3) colours

def blocks(rgb, mask, classes, speck=60, passes=(2, 2)):
    """The art within mask blocked in to the nearest of `classes` (posterize): {name: mask}."""
    if not mask.any():
        return {k: np.zeros(mask.shape, bool) for k in classes}
    cl = posterize(rgb, mask, list(classes.values()), passes=passes, speck=speck)
    return {k: (cl == i) & mask for i, k in enumerate(classes)}


def colours(rgb, kind, strands, pieces):
    """The paint channels over the art (CHANNELS): what is painted on the pieces face by face, what is tinted in."""
    food = kind > 0
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.0), cv2.COLOR_RGB2LAB).astype(np.float32)
    L = lab[..., 0] * 100 / 255
    nb = blocks(rgb, strands > 0, CLASSES['noodle'])
    edge = np.zeros(kind.shape, bool)   # each strand's rim, which the art shades golden
    for i in range(1, strands.max() + 1):
        m = strands == i
        edge |= m & ~cv2.erode(u8(m), disk(4)).astype(bool)
    out = paint_channels([nb['deep'] | edge], food, smooth=1.2, min_area=20, close=0)
    of = lambda k: kind == KIND_CODES[k]
    if KEY == 'D11':
        a_, b_ = lab[..., 1] - 128, lab[..., 2] - 128
        drop = (kind == 1) & (a_ > 16) & (b_ > 40) & (L > 55)   # the drops of dressing on the noodles
        cb = blocks(rgb, of('cucumber'), CLASSES['cucumber'], speck=40)
        hb = blocks(rgb, of('herb'), CLASSES['herb'], speck=120)
        return np.concatenate([out, paint_channels([nb['shade'] | nb['deep']], food, smooth=1.5, min_area=40,
                                                   close=1),
                               paint_channels([cb['skin'], cb['pale']], food, smooth=1.0, min_area=30, close=1),
                               paint_channels([hb['dark'], hb['light']], food, smooth=1.5, min_area=80, close=1),
                               paint_channels([drop], food, smooth=1.5, min_area=30, close=1)], -1)
    cut = of('scallion') & (L > 74)   # the scallion's pale cut ends
    out = np.concatenate([out, paint_channels([cut], food, smooth=0.8, min_area=15, close=1)], -1)
    if KEY == 'D02':
        lb = blocks(rgb, of('leaf'), CLASSES['leaf'], speck=300)
        out = np.concatenate([out, paint_channels([lb['dark'] | lb['deep'], lb['mid'], lb['vein']], food,
                                                  smooth=1.5, min_area=150, close=2)], -1)
    elif KEY == 'D09':
        pb = blocks(rgb, of('pork'), CLASSES['pork'], speck=120, passes=(3, 3))
        band = np.zeros(kind.shape, bool)   # the browned rind runs round each slice's edge, not inside it
        for m, k in pieces.values():
            if k == 'pork':
                band |= m & ~cv2.erode(u8(m), disk(16)).astype(bool)
        pb['rind'] &= band
        pb['deep'] &= band
        bl = blocks(rgb, of('bokleaf'), CLASSES['bokleaf'], speck=200)
        bs = blocks(rgb, of('bokstalk'), CLASSES['bokstalk'], speck=200)
        out = np.concatenate([out, paint_channels([pb['rind'] | pb['deep'], pb['fat'], pb['deep']], food,
                                                  smooth=1.5, min_area=80, close=1),
                              paint_channels([bl['dark'], bl['vein'], bs['green']], food, smooth=1.5, min_area=120,
                                             close=2)], -1)
    return out


if KEY == 'D02':
    CHANNELS = ['ndeep', 'scut', 'ldark', 'lmid', 'lvein']
    NOODLE_MAT = 'CaimianNoodle'
    TOP_KINDS = {
        'leaf': dict(gap=0.0075, gb=0.004, ring=(0.0006, 0.0012), puff=0.3, top=0.0022, edge=0.0004, relief=0.0012,
                     mat='CaimianLeaf', paint=[('ldark', 'CaimianLeafDark')],
                     tint=[('lvein', '#f4f6d8', 0.7), ('lmid', '#8cb83c', 0.55)], ink=[0.6, 2.2]),
        'scallion': dict(gap=0.0045, gb=0.0024, ring=0.0004, puff=0.7, top=0.0042, edge=0.0006, relief=0.0,
                         mat='CaimianScallion', paint=[('scut', 'CaimianScallionCut')], tint=[], ink=[0.5, 2.0])}
elif KEY == 'D09':
    CHANNELS = ['ndeep', 'scut', 'prind', 'pfat', 'pdeep', 'bdark', 'bvein', 'bgreen']
    NOODLE_MAT = 'CharouNoodle'
    TOP_KINDS = {
        'pork': dict(gap=0.007, gb=0.0035, ring=(0.0006, 0.0012), puff=0.45, top=0.0055, edge=0.0008,
                     relief=0.0015, mat='CharouPork', paint=[('prind', 'CharouRind')],
                     tint=[('pfat', '#f6dccb', 0.75), ('pdeep', '#7a3a1e', 0.6)], ink=[1.2, 2.4]),
        'bokleaf': dict(gap=0.008, gb=0.004, ring=(0.0006, 0.0012), puff=0.3, top=0.0025, edge=0.0004,
                        relief=0.0015, mat='CharouBokLeaf', paint=[('bdark', 'CharouBokDark')],
                        tint=[('bvein', '#8cba50', 0.6)], ink=[0.8, 2.2]),
        'bokstalk': dict(gap=0.008, gb=0.004, ring=(0.0006, 0.0012), puff=0.5, top=0.006, edge=0.0006,
                         relief=0.0015, mat='CharouBokStalk', paint=[], tint=[('bgreen', '#b6cc78', 0.6)],
                         ink=[0.6, 2.0]),
        'scallion': dict(gap=0.0045, gb=0.0024, ring=0.0004, puff=0.7, top=0.0045, edge=0.0006, relief=0.0,
                         mat='CharouScallion', paint=[('scut', 'CharouScallionCut')], tint=[], ink=[0.5, 2.0])}

elif KEY == 'D11':
    CHANNELS = ['ndeep', 'nshade', 'cskin', 'cpale', 'hdark', 'hlight', 'drop']
    NOODLE_MAT = 'LengtaoNoodle'
    TOP_KINDS = {
        'cucumber': dict(gap=0.01, gb=0.0056, ring=(0.0005, 0.001), puff=0.55, top=0.0042, edge=0.0006,
                         relief=0.001, mat='LengtaoCucumber', paint=[('cskin', 'LengtaoCucumberSkin')],
                         tint=[('cpale', '#eef0c4', 0.5)], ink=[0.8, 2.0]),
        'herb': dict(gap=0.01, gb=0.0055, ring=(0.0005, 0.001), puff=0.3, top=0.0022, edge=0.0004, relief=0.0012,
                     mat='LengtaoHerb', paint=[('hdark', 'LengtaoHerbDark')], tint=[('hlight', '#8cbc48', 0.6)],
                     ink=[0.8, 2.2]),
        'drop': dict(gap=0.004, gb=0.0016, ring=0.0003, puff=0.35, top=0.0009, edge=0.0002, relief=0.0,
                     mat='LengtaoDrop', paint=[], tint=[], ink=[0.0, 0.0]),
        'bed': dict(gap=0.011, gb=0.005, ring=0.0, puff=0.0, top=0.0, edge=0.0, relief=0.0, mat='LengtaoNest',
                    paint=[], tint=[('drop', '#e8902e', 0.8)], ink=[0.0, 0.0])}

# (4) by kind: mesh spacing inside and along the outline (m), its rings, how high it rises (puff x its half-width, up
# to top), where its outline sits (edge, over what is under it), its relief from the art's shading, and its colours:
# what it is built in, what is painted on it (its mesh has vertices along each colour's edge), what is tinted in
KINDS = {
    'strand': dict(gb=0.0036, ring=(0.0004, 0.0011), axis=18.0, puff=0.55, top=0.003, edge=0.0003, shoulder=0.5,
                   mat=NOODLE_MAT, paint=[], tint=[('ndeep', '#e6bc6c', 0.6)], ink=[2.4, 2.4]),
    **TOP_KINDS}
if KEY == 'D09':   # thinner noodles, and many: one ring, the points further apart; their strands a texture
    KINDS['strand'].update(gb=0.0044, ring=0.0004, axis=22.0, puff=0.6, dirs=True)
if KEY == 'D11':   # thin noodles, packed close in the nest, in bundles; their strands a texture
    KINDS['strand'].update(gb=0.006, ring=0.0004, axis=30.0, puff=0.7, top=0.0022, dirs=True,
                           tint=[('drop', '#ec9a3c', 0.85), ('nshade', '#f4c48a', 0.45), ('ndeep', '#e8964a', 0.55)],
                           ink=[1.2, 1.6])
SPACING = {'leaf': 12.0, 'scallion': 6.0, 'bed': 12.0, 'pork': 9.0, 'bokleaf': 12.0, 'bokstalk': 12.0,
           'cucumber': 6.0, 'herb': 10.0, 'drop': 6.0}   # art pixels between the vertices along a colour's edge
LAYER = {'leaf': 1, 'pork': 1, 'bokleaf': 1, 'bokstalk': 1, 'cucumber': 1, 'herb': 2, 'scallion': 3, 'drop': 3}   # over what


# ------------------------------------------------------------------ (4) the surfaces

def strand_surface(name, m, zbuf, base):
    """A noodle: its outline, a ring of points a little in from it and a row along its middle, raised to a round
    strand (a circle's arc as wide as the strand is there, puff x its half-width high), floating on what is under it
    (zbuf, else the base's depth)."""
    kp = KINDS['strand']
    H, W = m.shape
    m = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 1.0) > 0.5
    pts = axis_points(m, kp['axis'], min_d=2.5)
    try:
        uv, tris, nb, d, R, lean = outline_mesh(CAM, m, 0.012, kp['gb'], kp['ring'], smooth_px=1.5, extra=pts,
                                                extra_margin=2.0)
    except ValueError:   # too narrow for the inner ring (outline_mesh can't stack an empty ring): the outer one
        uv, tris, nb, d, R, lean = outline_mesh(CAM, m, 0.012, kp['gb'], kp['ring'][0], smooth_px=1.5, extra=pts,
                                                extra_margin=2.0)
    x0, y0, bw, bh = cv2.boundingRect(u8(m))   # its half-width round about each point, measured as outline_mesh
    x0, y0 = max(x0 - 4, 0), max(y0 - 4, 0)       # measures d: on level ground (v stretched by 1 / sin el), in m
    sub = u8(m[y0:y0 + bh + 8, x0:x0 + bw + 8])
    hs = max(int(round(sub.shape[0] / CAM.se)), 1)
    dt = cv2.distanceTransform(cv2.resize(sub, (sub.shape[1], hs), interpolation=cv2.INTER_NEAREST), cv2.DIST_L2, 5)
    hw = cv2.dilate(dt, disk(int(kp['axis']))) / CAM.k
    iy = np.clip(np.round((uv[:, 1] - y0) / CAM.se).astype(int), 0, hs - 1)
    ix = np.clip(np.round(uv[:, 0] - x0).astype(int), 0, sub.shape[1] - 1)
    w = np.maximum(hw[iy, ix], 1e-4)
    rise = np.clip(d / (kp['shoulder'] * w), 0, 1)   # up from its edge to a broad, round top
    L = kp['edge'] + np.minimum(kp['puff'] * w, kp['top']) * (1 - (1 - rise) ** 2)
    P, T = over(CAM, uv, tris, L, zbuf, base)
    return uv, P, T, nb


def piece_surface(kind, m, zbuf, base, paint, lum):
    """A topping as a surface over its outline, floating on what is under it, the art's shading in relief."""
    kp = KINDS[kind]
    H, W = m.shape
    edges = [(paint[..., CHANNELS.index(c)] > 127) & m for c, _ in kp['paint']]
    extra = contour_points(edges, SPACING[kind]) if edges else None
    ring = kp['ring']
    r0 = ring[-1] if isinstance(ring, tuple) else ring
    try:
        uv, tris, nb, d, R, lean = outline_mesh(CAM, m, kp['gap'], kp['gb'], ring, smooth_px=1.5, extra=extra,
                                                extra_margin=r0 * CAM.k + 2.0)
    except ValueError:   # too narrow for the inner ring: the outer one
        r1 = ring[0] if isinstance(ring, tuple) else ring
        uv, tris, nb, d, R, lean = outline_mesh(CAM, m, kp['gap'], kp['gb'], r1, smooth_px=1.5, extra=extra,
                                                extra_margin=r1 * CAM.k + 2.0)
    band = shading_band(lum, m, 3.0, 16.0)
    iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
    ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
    top = float(np.clip(kp['puff'] * R, 0.0006, kp['top']))
    L = profile(d, R, top, kp['edge'], 0.0, lean, kp['relief'], band[iy, ix])
    L = smooth_inner(L, nb, neighbours(len(uv), tris))
    P, T = over(CAM, uv, tris, L, zbuf, base)
    return uv, P, T, nb


def strand_mat(P, T, mat):
    """A strand's material: its own, textured with strands along the box projection's u, or the one along v
    (mat + 'V'), whichever its length runs along more, in the projection its surface takes (by its mean normal)."""
    P, T = np.asarray(P), np.asarray(T)
    n = np.cross(P[T[:, 1]] - P[T[:, 0]], P[T[:, 2]] - P[T[:, 0]]).sum(0)
    axis = int(np.argmax(np.abs(n)))
    u, v = {0: (1, 2), 1: (0, 2), 2: (0, 1)}[axis]   # x-facing: (y, z); y-facing: (x, z); z-facing: (x, y)
    Q = P - P.mean(0)
    d = np.linalg.svd(Q, full_matrices=False)[2][0]   # along it
    return mat if abs(d[u]) >= abs(d[v]) else mat + 'V'


def close_under(P, T, nb, zfloor):
    """A surface closed underneath, hidden from the art's view behind the heap it lies on: a skirt from its outline
    (its first nb points) straight down to z = zfloor, and the outline there filled flat, facing down."""
    P = np.asarray(P, float)
    k0 = len(P)
    feet = P[:nb].copy()
    feet[:, 2] = np.minimum(feet[:, 2], zfloor)
    P2 = np.r_[P, feet]
    xy = P[:nb, :2]
    ccw = np.sum(xy[:, 0] * np.roll(xy[:, 1], -1) - np.roll(xy[:, 0], -1) * xy[:, 1]) > 0
    skirt = []
    for i in range(nb):
        j = (i + 1) % nb
        e = xy[j] - xy[i]
        outside = np.array([e[1], -e[0]]) if ccw else np.array([-e[1], e[0]])
        for t in ((i, j, k0 + j), (i, k0 + j, k0 + i)):
            n = np.cross(P2[t[1]] - P2[t[0]], P2[t[2]] - P2[t[0]])
            skirt.append(t if n[:2] @ outside >= 0 else (t[0], t[2], t[1]))
    floor = []
    for a, b, c in ear_clip(P2[k0:, :2]):
        t = (k0 + a, k0 + b, k0 + c)
        n = np.cross(P2[t[1]] - P2[t[0]], P2[t[2]] - P2[t[0]])
        floor.append(t if n[2] <= 0 else (t[0], t[2], t[1]))
    return P2, list(map(tuple, T)) + skirt + floor


def piece_dict(name, kind, P, T, nb):
    kp = KINDS[kind]
    mat = strand_mat(P, T, kp['mat']) if kind == 'strand' and kp.get('dirs') else kp['mat']
    return {'name': name, 'kind': kind, 'mat': mat, 'rim': int(nb),
            'paint': [(CHANNELS.index(c), mk) for c, mk in kp['paint']],
            'tint': [(CHANNELS.index(c), col, w) for c, col, w in kp['tint']],
            'ink': kp['ink'], 'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]}


def clean(m, r=1):
    """A piece's mask as one clean region: its largest part, holes filled."""
    m = cv2.morphologyEx(u8(m), cv2.MORPH_OPEN, disk(r))
    if not m.any():
        return None
    return fill_holes(largest(m))


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    H, W = alpha.shape
    lum = cv2.GaussianBlur(rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32), (0, 0), 1.0)
    zb_broth, broth, inside, zdish = bowl_view(H, W)
    zone = (inside if KEY == 'D11' else broth) & (alpha > 128)
    got, ids = what_is_where(rgb, zone)
    kind, pieces = kinds_of(got, ids)
    strands, _ = strand_cut(kind == 1, lum, STRANDS)
    paint = colours(rgb, kind, strands, pieces)
    base = lambda u, v: plane_depth(u, v)
    ground = np.full((H, W), np.inf)   # what the food lies on, where it is not the broth's level: 冷淘's heap
    if KEY == 'D11':
        ys, xs = np.nonzero(zone)
        X, Y, Z = CAM.backproject(xs + 0.5, ys + 0.5, lambda x, y: nest_height(x, y) + LIFT, y0=-0.12, y1=0.12,
                                  steps=240)
        ground[ys, xs] = CAM.depth(np.stack([X, Y, Z], -1))
        miss = np.zeros((H, W), bool)   # past the heap's outline (the art's nest a little bigger than it): on
        miss[ys, xs] = (Z < FILL_Z + LIFT + 2e-4) & (Y > NEST['c'][1])   # upright ground at the depth of its edge
        for v in range(H - 2, -1, -1):
            row = miss[v] & np.isfinite(ground[v + 1])
            ground[v, row] = ground[v + 1, row]
        base = lambda u, v: ground[np.clip(np.round(v).astype(int), 0, H - 1), np.clip(np.round(u).astype(int), 0,
                                                                                         W - 1)]
    zb = np.full((H, W), np.inf)
    zid = np.full((H, W), -1, np.int32)
    out, n_tris, shown, names = [], {}, np.zeros((H, W), np.int32), []

    def add(name, kind_, m, P, T, nb):
        out.append(piece_dict(name, kind_, P, T, nb))
        pu, pv = CAM.project(P[:, 0], P[:, 1], P[:, 2])
        raster(np.stack([pu, pv], -1)[np.array(T)], CAM.depth(P)[np.array(T)], np.full(len(T), len(out)), H, W,
               zb, zid)
        n_tris[kind_] = n_tris.get(kind_, 0) + len(T)
        names.append((name, kind_))
        shown[m & (shown == 0)] = len(names)
    if KEY == 'D11':   # the heap itself, the shade between strands where they part a little
        nest = fill_holes(cv2.morphologyEx(u8(kind > 0), cv2.MORPH_CLOSE, disk(4)))
        nest = largest(cv2.morphologyEx(u8(nest), cv2.MORPH_OPEN, disk(3)))
        uv, P, T, nb = piece_surface('bed', nest, np.full((H, W), np.inf), base, paint, lum)
        P, T = close_under(P, T, nb, FILL_Z)   # closed underneath (in the wok its skirt runs on to the floor)
        add('nest', 'bed', np.zeros_like(nest), P, T, nb)
        out[-1]['closed'] = len(uv)
    for i in range(1, strands.max() + 1):   # the noodles, on the broth
        m = clean(strands == i)
        if m is None or m.sum() < (700 if KEY == 'D11' else 150):   # (冷淘: its heap shows where a bit is left out)
            continue
        uv, P, T, nb = strand_surface(f'N{i}', m, np.full((H, W), np.inf), lambda u, v: base(u, v) - 0.0004)
        add(f'N{i}', 'strand', m, P, T, nb)
    for name in sorted(pieces, key=lambda n: (LAYER[pieces[n][1]], n)):   # the toppings, what lies on top last
        m, k = pieces[name]
        m = clean(m, 1)
        if m is None or m.sum() < 60:
            continue
        uv, P, T, nb = piece_surface(k, m, zb if LAYER[k] > 1 else np.full((H, W), np.inf), base, paint, lum)
        add(name, k, m, P, T, nb)
    if KEY == 'D11':
        shown[nest & (shown == 0)] = 1
    print(f'[trace] {KEY}: {len(out)} pieces, triangles by kind {n_tris}, all {sum(n_tris.values())}', flush=True)
    np.savez_compressed(PAINT, paint=paint[::2, ::2])
    data = {'camera': {'el': CAM.el, 'k': CAM.k, 'u0': CAM.u0, 'v0': CAM.v0}, 'paint_scale': 0.5,
            'channels': CHANNELS, 'fill_z': FILL_Z, 'pieces': out, 'bits': []}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT} and {PAINT}', flush=True)
    if sheet:
        tints = {'strand': (250, 240, 214), 'leaf': (150, 190, 70), 'scallion': (70, 150, 40),
                 'bed': (230, 210, 160), 'pork': (220, 150, 130), 'bokleaf': (60, 110, 40),
                 'bokstalk': (210, 230, 170), 'cucumber': (150, 190, 90), 'herb': (60, 120, 40),
                 'drop': (240, 140, 40)}
        ys, xs = np.nonzero(zone)
        tracing_sheet(sheet, rgba, shown, [n for n, _ in names], [tints[k] for _, k in names],
                      crop=(int(xs.min()) - 10, int(ys.min()) - 10, int(xs.max()) + 10, int(ys.max()) + 10),
                      title=('原图上的描线（蓝：每一块）', f'描出的 {len(out)} 块'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
