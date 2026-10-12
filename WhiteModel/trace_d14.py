"""Traces 玉板鲊's art (新建文件夹/玉板鲊.png) for D14, so that its slices of salted fish, its grains of fermented rice
and its shreds of ginger are modelled 1:1 (勾勒) and as cleanly as the art draws them: writes
food_models/traced_D14.json and the colours of the pieces food_models/traced_D14_paint.npz, which plates.yuban_zha
builds the dish from, and a tracing sheet.

    python WhiteModel/trace_d14.py [--sheet <out.png>]

1. The art's camera: fitted, 35° up as the icons are seen, so that the round celadon dish yuban_zha builds (with a
   little brine in it) covers the art's silhouette best.
2. The slices, nine of them fanned across the rice, back to front: each traced by its own two strokes, its back (the
   skin side) and its belly, from its cut end to its tip (SLICES); the back snapped onto the ink line the art draws
   along it, then each outline smoothed into one clean rounded shape. Each is its whole shape: the slices in front
   lie over it where the art shows them so.
3. On each slice its skin: one band along its back as wide as the art paints it there (measured along the slice and
   smoothed into one curve), silver-grey, with the art's dark line along the back edge; the flesh pale pink-white,
   lighter towards the cut end and greyer next to the skin. The mesh has vertices along the band's edge and the
   line's, so that each is painted on crisply.
4. Each slice a plump rounded lens lying over what is under it (the rice bed and the slices behind it), thickest
   along its back, thinning to its belly and its tip; the rice a low bed under all the food (its outline the food's
   outline in the art), and on it and on the slices the grains the art draws, each a small rounded grain where the art
   has it, turned as it is drawn; the shreds of ginger slim rounded sticks over all.
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

from trace_common import (Camera, Grid, contour_points, dish_mesh, disk, fill_holes, largest, lying, neighbours,
                          oriented, outline_mesh, over, profile, seeded_pieces, smooth_inner, tracing_sheet, u8)
from trace_kit_plates import closed_under, raster_piece

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '玉板鲊.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D14.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D14_paint.npz')
CAM = Camera(35.0, 6033.5, 625.7, 787.1)            # (1)
FZ = 0.008
DISH = ("d = DISH14\n"
        "inside = oval_dish(p, d['A'], d['q'], d['yaw'], d['h'], d['foot'], floor=0.008, n=48, lip=0.005, rings=3)\n"
        "dish_sauce(p, 'ZhaBrine', inside, d['A'], 1.0, 0.0, reach=0.74, n=32, seed=14, lift=0.0012, wobble=0.06)")

# (2) the slices, back to front: each one's back edge (the skin side) and belly edge (art pixels) from its cut end
# to its tip, read off the art by eye
SLICES = [
    ('s1', [(548, 343), (585, 358), (620, 374), (655, 398)], [(524, 375), (565, 400), (610, 415), (652, 405)]),
    ('s2', [(728, 358), (774, 376), (825, 392), (866, 400), (910, 418), (953, 443), (979, 469), (1000, 490)],
     [(712, 392), (760, 420), (820, 450), (880, 470), (940, 490), (985, 500), (1001, 494)]),
    ('s3', [(985, 652), (1025, 679), (1066, 697), (1097, 710), (1112, 715)],
     [(975, 718), (1015, 748), (1056, 763), (1082, 753), (1107, 728), (1113, 718)]),
    ('s4', [(690, 425), (723, 430), (789, 451), (846, 484), (897, 525), (933, 561), (969, 607), (999, 648),
            (1025, 689), (1046, 730), (1056, 766), (1058, 776)],
     [(680, 470), (720, 520), (760, 580), (800, 640), (840, 690), (880, 725), (917, 740), (953, 746), (1005, 766),
      (1056, 778)]),
    ('s5', [(830, 738), (870, 738), (902, 746), (953, 771), (999, 797), (1011, 808)],
     [(840, 830), (866, 843), (928, 838), (979, 828), (1011, 814)]),
    ('s6', [(179, 535), (230, 527), (290, 521), (350, 518), (407, 515), (450, 525), (490, 550)],
     [(186, 588), (240, 606), (300, 622), (360, 632), (420, 632), (470, 600), (492, 560)]),
    ('s7', [(450, 600), (520, 612), (600, 632), (680, 655), (760, 680), (815, 689), (835, 730), (851, 766),
            (861, 807), (866, 848), (869, 869)],
     [(450, 680), (530, 720), (610, 760), (680, 800), (740, 835), (800, 860), (840, 872), (869, 875)]),
    ('s8', [(412, 444), (448, 438), (489, 435), (540, 439), (592, 453), (638, 470), (690, 500), (748, 551),
            (789, 587), (815, 628), (830, 679), (832, 694), (830, 702)],
     [(417, 556), (470, 590), (545, 620), (610, 650), (680, 675), (755, 697), (830, 705)]),
    ('s9', [(148, 597), (202, 617), (253, 625), (299, 623), (345, 627), (400, 645), (456, 663), (508, 682),
            (560, 697), (605, 708), (660, 730), (705, 760), (740, 795), (765, 830), (776, 868), (780, 893)],
     [(197, 720), (240, 738), (290, 760), (340, 790), (397, 830), (450, 852), (489, 868), (540, 880), (592, 889),
      (650, 900), (700, 905), (745, 903), (778, 897)]),
]

# (5) where the food is (a flood seeded inside it and on the dish round it): its outline is the rice bed's
RICE = [[(250, 470), (300, 450)], [(470, 380), (540, 360), (600, 350)], [(660, 360), (700, 345)],
        [(960, 580), (1040, 600), (1090, 640)], [(200, 740), (260, 780), (320, 830)], [(420, 860), (520, 890)],
        [(840, 700), (900, 720)], [(330, 560), (400, 570)], [(620, 420), (650, 440)], [(780, 520), (800, 560)]]
DISH_STROKES = [[(120, 560), (110, 680), (160, 800), (260, 880), (400, 930), (600, 960), (800, 950), (1000, 890),
                 (1130, 780), (1160, 640), (1120, 520), (1020, 430), (900, 360), (760, 320), (600, 300), (450, 320),
                 (320, 380), (200, 460), (120, 560)]]
# shreds of ginger over them: the two ends of each (art pixels) and its width, read off the art by eye
GINGER = [((478, 365), (655, 490), 20), ((361, 433), (425, 462), 20), ((202, 643), (443, 525), 22),
          ((427, 627), (602, 735), 20), ((340, 833), (448, 735), 22), ((653, 417), (697, 587), 22),
          ((697, 515), (774, 633), 18), ((769, 433), (882, 397), 21), ((856, 479), (1051, 556), 21),
          ((851, 728), (1005, 799), 21)]
# single grains of rice lying on the slices, as the art draws them: middle (art pixels), direction (degrees), length
GRAINS_ON = [(465, 668, 10, 48), (304, 712, 160, 44), (352, 700, 20, 40), (612, 790, 150, 40), (742, 768, 120, 42),
             (875, 690, 100, 40), (930, 642, 60, 40)]
# where the art heaps the grains, over the slices too (art pixels): grains are looked for there as well
PILES = [[(420, 540), (600, 530), (610, 610), (560, 700), (440, 700), (410, 620)],
         [(440, 330), (720, 320), (730, 470), (600, 480), (450, 440)],
         [(600, 470), (720, 470), (740, 620), (640, 640), (600, 560)],
         [(930, 500), (1120, 520), (1120, 720), (980, 720), (940, 620)],
         [(160, 690), (340, 700), (340, 860), (170, 820)], [(300, 820), (580, 830), (580, 915), (300, 910)],
         [(230, 430), (430, 420), (430, 540), (240, 540)]]
BED_TOP = 0.012      # the rice bed's height over the dish (m)
BACK_T, BELLY_T = 0.008, 0.0035    # a slice's thickness along its back and its belly (m)
RIM_R = 0.004        # the rounding of a slice's edge (m)
EDGE_PX = 6.0        # the dark line along a slice's back, in from its edge (art pixels)
GRAINS_MAX = 86      # grains of rice modelled (the art's most distinct, each ~24 triangles)
CHANNELS = ['skin', 'edge', 'fade', 'cut']
RING, INK = (0.0006, 0.0012), [3.0, 3.0]


def resample(p, step=8.0):
    p = np.asarray(p, float)
    L = np.r_[0, np.cumsum(np.hypot(*np.diff(p, axis=0).T))]
    n = max(3, int(L[-1] / step) + 1)
    tt = np.linspace(0, L[-1], n)
    return np.stack([np.interp(tt, L, p[:, 0]), np.interp(tt, L, p[:, 1])], -1)


def snap(p, ink, reach=18, thr=10.0):
    """A stroke moved onto the ink line the art draws along it (the strongest within `reach` pixels across it, where
    there is one; elsewhere as its neighbours), the offsets smoothed along it."""
    H, W = ink.shape
    q = resample(p, 10.0)
    tg = np.gradient(q, axis=0)
    nrm = np.stack([-tg[:, 1], tg[:, 0]], -1) / np.maximum(np.linalg.norm(tg, axis=1, keepdims=True), 1e-9)
    ts = np.arange(-reach, reach + 1)
    off, ok = np.zeros(len(q)), np.zeros(len(q), bool)
    for i, (a, nn) in enumerate(zip(q, nrm)):
        pts = a[None] + ts[:, None] * nn[None]
        xs = np.clip(pts[:, 0].round().astype(int), 0, W - 1)
        ys = np.clip(pts[:, 1].round().astype(int), 0, H - 1)
        j = int(np.argmax(ink[ys, xs] - 0.15 * np.abs(ts)))
        if ink[ys[j], xs[j]] > thr:
            off[i], ok[i] = ts[j], True
    if ok.any():
        idx = np.arange(len(q))
        off = np.interp(idx, idx[ok], off[ok])
    off = np.convolve(np.r_[[off[0]] * 3, off, [off[-1]] * 3], np.ones(7) / 7, 'valid')
    return q + off[:, None] * nrm


def outline_of(back, belly, sig=2.0):
    """A slice's outline: its back from the cut end to the tip and its belly back again, smoothed round (its corners
    rounded off), as a closed polygon (art pixels)."""
    poly = resample(np.r_[back, belly[::-1]], 6.0)
    r = int(3 * sig) + 1
    k = np.exp(-0.5 * (np.arange(-r, r + 1) / sig) ** 2)
    k /= k.sum()
    return np.stack([np.convolve(np.r_[poly[-r:, i], poly[:, i], poly[:r, i]], k, 'valid') for i in range(2)], -1)


def slice_fields(mask, back, belly):
    """Over a slice's mask: f, how far across it each pixel lies from its back (0) to its belly (1), and s, how far
    along it from its cut end (0) to its tip (1)."""
    H, W = mask.shape
    lb, ll = np.zeros((H, W), np.uint8), np.zeros((H, W), np.uint8)
    cv2.polylines(lb, [np.round(back).astype(np.int32)], False, 1, 1)
    cv2.polylines(ll, [np.round(belly).astype(np.int32)], False, 1, 1)
    db = cv2.distanceTransform(1 - lb, cv2.DIST_L2, 5)
    dl = cv2.distanceTransform(1 - ll, cv2.DIST_L2, 5)
    f = db / np.maximum(db + dl, 1e-6)
    n = 40
    B, L = resample(back, 1.0), resample(belly, 1.0)
    mid = (B[np.linspace(0, len(B) - 1, n).astype(int)] + L[np.linspace(0, len(L) - 1, n).astype(int)]) / 2
    mk = np.ones((H, W), np.uint8)
    for k, (x, y) in enumerate(mid):
        mk[min(max(int(round(y)), 0), H - 1), min(max(int(round(x)), 0), W - 1)] = 0
    _, lab = cv2.distanceTransformWithLabels(mk, cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)
    ys, xs = np.nonzero(mk == 0)
    idx = np.zeros(lab.max() + 1, np.float32)
    order = {(int(round(y)), int(round(x))): k for k, (x, y) in enumerate(mid)}
    for yy, xx in zip(ys, xs):
        idx[lab[yy, xx]] = order.get((yy, xx), 0) / (n - 1)
    s = idx[lab]
    return f, s, db


def skin_curve(f, s, visible, grey):
    """How far across the slice its skin reaches from its back, along it (a smooth curve of s): where the art shows the
    slice, the grey of its skin in a run from its back edge, measured in steps along it and fitted with a gentle
    curve."""
    ss, ff, ww = [], [], []
    for k in range(12):
        band = visible & (s >= k / 12) & (s < (k + 1) / 12)
        if band.sum() < 300:
            continue
        fs = f[band]
        gs = grey[band]
        edge = 0.0
        for j in range(18):
            sel = (fs >= j / 20) & (fs < (j + 1) / 20)
            if sel.sum() < 15:
                if j * 0.05 > edge + 0.1:
                    break
                continue
            if gs[sel].mean() >= 0.35:
                edge = (j + 1) / 20
            elif j * 0.05 > edge + 0.06:
                break
        ss.append((k + 0.5) / 12)
        ff.append(edge)
        ww.append(min(band.sum(), 4000))
    if len(ss) < 2:
        return lambda x: np.full_like(np.asarray(x, float), 0.2)
    deg = 2 if len(ss) >= 5 else 1
    c = np.polyfit(ss, ff, deg, w=np.sqrt(ww))
    return lambda x: np.clip(np.polyval(c, np.asarray(x, float)), 0.14, 0.8)


def ginger_mask(rgb, food):
    """The ginger shreds: bright yellow, long and thin, with their ink line."""
    hsv = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.0), cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    g = cv2.morphologyEx(u8(food & (h > 38) & (h < 58) & (s > 0.5) & (v > 0.85)), cv2.MORPH_OPEN, disk(3))
    n, cc, st, _ = cv2.connectedComponentsWithStats(g)
    out = np.zeros(food.shape, bool)
    for j in range(1, n):
        if st[j, cv2.CC_STAT_AREA] < 150:
            continue
        ys, xs = np.nonzero(cc == j)
        (_, _), (rw, rh), _ = cv2.minAreaRect(np.stack([xs, ys], -1).astype(np.float32))
        if max(rw, rh) > 50 and max(rw, rh) / max(min(rw, rh), 1) > 2.5:
            out |= cc == j
    return cv2.dilate(u8(out), disk(3)).astype(bool) & food


def food_mask(rgb, zone):
    """The food as the art shows it: a flood from strokes in its rice and slices and on the dish round it."""
    st = {}
    for i, line in enumerate(RICE):
        st[i + 1] = line
    for k, (_, b, l) in enumerate(SLICES):   # along the middle of each slice
        B, L = resample(b, 1.0), resample(l, 1.0)
        mid = (B[np.linspace(0, len(B) - 1, 7).astype(int)] + L[np.linspace(0, len(L) - 1, 7).astype(int)]) / 2
        st[len(RICE) + k + 1] = [tuple(q) for q in mid[1:-1]]
    pieces = seeded_pieces(rgb, zone, st, DISH_STROKES)
    rice = (pieces > 0) & (pieces <= len(RICE))   # what the flood gives the rice: its grains, on the slices too
    return fill_holes(largest(cv2.morphologyEx(u8(pieces > 0), cv2.MORPH_OPEN, disk(3)))), rice


def find_grains(rgb, food, avoid, strict=None, ink=None):
    """The grains of rice the art draws: pale bright blobs (peaks of the art's light at the size of a grain), each
    measured (its middle, the way it lies, its length and width in pixels), the most distinct first, none on top of
    another. Within `strict` (the slices' pale flesh) only those the art outlines (ink round their edge)."""
    hsv = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.0), cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    beige = food & (h > 18) & (h < 52) & (s > 0.08) & (s < 0.5) & (v > 0.82) & ~avoid
    resp = np.zeros(lum.shape, np.float32)
    for sg in (5, 6.5, 8):
        resp = np.maximum(resp, -cv2.Laplacian(cv2.GaussianBlur(lum, (0, 0), sg), cv2.CV_32F, ksize=3) * sg * sg)
    peak = (resp == cv2.dilate(resp, np.ones((11, 11), np.uint8))) & (resp > 7) & beige
    if strict is not None:
        peak &= ~strict | (resp > 24)
    ys, xs = np.nonzero(peak)
    order = np.argsort(-resp[ys, xs])
    H, W = lum.shape
    sm = cv2.GaussianBlur(lum, (0, 0), 1.2)
    out = []
    for i in order:
        x, y = int(xs[i]), int(ys[i])
        x0, y0, x1, y1 = max(x - 30, 0), max(y - 30, 0), min(x + 31, W), min(y + 31, H)
        win = sm[y0:y1, x0:x1]
        blob = u8((win > sm[y, x] - 16) & beige[y0:y1, x0:x1])
        n, cc = cv2.connectedComponents(blob)
        lab = cc[y - y0, x - x0]
        if lab == 0:
            continue
        yy, xx = np.nonzero(cc == lab)
        if len(xx) < 60:
            continue
        if strict is not None and strict[y, x] and ink is not None:   # on a slice: a grain drawn round, not a light
            own = u8(cc == lab)
            ring = (cv2.dilate(own, disk(3)) > 0) & ~(own > 0)
            if ink[y0:y1, x0:x1][ring].mean() < 9.0:
                continue
        cov = np.cov(np.stack([xx, yy]))
        ev, evec = np.linalg.eigh(cov)
        major, minor = 4 * math.sqrt(max(ev[1], 1e-6)), 4 * math.sqrt(max(ev[0], 1e-6))
        ln, wd = float(np.clip(major, 24, 50)), float(np.clip(minor, 14, 30))
        wd = min(wd, ln * 0.78)
        ang = math.degrees(math.atan2(evec[1, 1], evec[0, 1]))
        cx, cy = x0 + float(xx.mean()), y0 + float(yy.mean())
        if any(math.hypot(cx - g[0], cy - g[1]) < 0.33 * (ln + g[3]) for g in out):
            continue
        out.append((cx, cy, ang, ln, wd))
        if len(out) >= GRAINS_MAX:
            break
    return out


def pile_grains(rgb, zone, have, n_max, step=27.0):
    """More grains where the art heaps them densely (zone): on a staggered grid `step` pixels apart, where the art is
    the pale peach of the rice and no grain is yet, each turned the way the art's shading runs there."""
    hsv = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.0), cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    gx, gy = cv2.Sobel(lum, cv2.CV_32F, 1, 0), cv2.Sobel(lum, cv2.CV_32F, 0, 1)
    jxx, jyy, jxy = (cv2.GaussianBlur(a, (0, 0), 6) for a in (gx * gx, gy * gy, gx * gy))
    rice = zone & (h > 18) & (h < 52) & (s > 0.08) & (s < 0.5) & (v > 0.86)
    ys, xs = np.nonzero(zone)
    out = []
    if not len(xs):
        return out
    for k, y in enumerate(np.arange(ys.min() + step / 2, ys.max(), step * 0.87)):
        for x in np.arange(xs.min() + step / 2 + (k % 2) * step / 2, xs.max(), step):
            xi, yi = int(x), int(y)
            if not rice[yi, xi] or any(math.hypot(x - g[0], y - g[1]) < 28 for g in have + out):
                continue
            ang = 0.5 * math.degrees(math.atan2(2 * jxy[yi, xi], jxx[yi, xi] - jyy[yi, xi])) + 90   # along the grain
            out.append((float(x), float(y), ang, 38.0, 23.0))
            if len(out) >= n_max:
                return out
    return out


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    H, W = alpha.shape
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    ink = cv2.GaussianBlur(cv2.morphologyEx(cv2.GaussianBlur(lum, (0, 0), 1.0), cv2.MORPH_BLACKHAT, disk(4)), (0, 0), 1.5)
    food, rice_px = food_mask(rgb, alpha > 128)
    ginger = ginger_mask(rgb, food)
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.5), cv2.COLOR_RGB2LAB).astype(np.float32)
    grey = (np.hypot(lab[..., 1] - 128, lab[..., 2] - 128) < 26) & (lab[..., 0] < 214)   # darker than the flesh
    grey = cv2.GaussianBlur(grey.astype(np.float32), (0, 0), 4.0) > 0.3    # the skin's light scales and all
    floor = Grid.top_of(*dish_mesh(DISH))
    # (2) the slices: their outlines, whole, and which one the art shows at each pixel
    shapes = []
    owner = np.zeros((H, W), np.int32)
    for k, (name, back, belly) in enumerate(SLICES, 1):
        B = snap(back, ink)
        L = resample(belly, 10.0)
        poly = outline_of(B, L)
        m = np.zeros((H, W), np.uint8)
        cv2.fillPoly(m, [np.round(poly * 16).astype(np.int32)], 1, shift=4)
        shapes.append((name, B, L, poly, m.astype(bool)))
        owner[m.astype(bool)] = k
    # (3) each slice's skin band, the dark line along its back, the flesh greyer by the skin and lighter by the cut
    paint = np.zeros((H, W, len(CHANNELS)), np.float32)
    bands = []
    for k, (name, B, L, poly, m) in enumerate(shapes, 1):
        x0, y0, w0, h0 = cv2.boundingRect(u8(m))
        x0, y0 = max(x0 - 10, 0), max(y0 - 10, 0)
        x1, y1 = min(x0 + w0 + 20, W), min(y0 + h0 + 20, H)
        sub = m[y0:y1, x0:x1]
        f, s, db = slice_fields(sub, B - [x0, y0], L - [x0, y0])
        f = cv2.GaussianBlur(f.astype(np.float32), (0, 0), 2.0)     # so that the band's edge runs smooth
        vis = (owner[y0:y1, x0:x1] == k) & ~ginger[y0:y1, x0:x1] & sub
        fsk = skin_curve(f, s, vis, grey[y0:y1, x0:x1])
        edge_f = fsk(s)
        band = sub & (f < edge_f)
        line = sub & (db < EDGE_PX) & (s > 0.02) & (s < 0.97)
        fade = sub & ~band & (f < edge_f + 0.16)
        fade_w = np.where(fade, 1 - (f - edge_f) / 0.16, 0.0)
        cut_w = np.where(sub & ~band, np.clip(1 - s / 0.3, 0, 1), 0.0)
        show = owner[y0:y1, x0:x1] == k
        for c, val in (('skin', band), ('edge', line), ('fade', fade_w), ('cut', cut_w)):
            ch = paint[y0:y1, x0:x1, CHANNELS.index(c)]
            ch[show] = np.asarray(val, np.float32)[show]
        full = np.zeros((H, W), bool)
        full[y0:y1, x0:x1] = band
        fl = np.zeros((H, W), bool)
        fl[y0:y1, x0:x1] = line
        bands.append((full, fl))
        print(f'[trace] {name}: skin reaches {float(edge_f[sub].min()):.2f}..{float(edge_f[sub].max()):.2f} across',
              flush=True)
    paint[..., CHANNELS.index('fade')] = cv2.GaussianBlur(paint[..., CHANNELS.index('fade')], (0, 0), 2.0)
    paint[..., CHANNELS.index('cut')] = cv2.GaussianBlur(paint[..., CHANNELS.index('cut')], (0, 0), 3.0)
    paint8 = np.clip(paint * 255 + 0.5, 0, 255).astype(np.uint8)
    out = []
    zb, zid = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
    on_dish = lambda u, v: CAM.depth(np.stack(CAM.backproject(u, v, floor), -1))
    # (4) the rice bed under all the food
    mk = cv2.GaussianBlur(food.astype(np.float32), (0, 0), 3.0) > 0.5
    uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, 0.026, 0.008, RING, smooth_px=4.0)
    L = profile(d, R, BED_TOP, 0.0, 0.2, lean)
    L = np.minimum(L, 0.6 * d)   # nowhere steeper than the line of sight at its front: no overhang
    P, T = lying(CAM, uv, tris, nb, L, floor)
    P, T = closed_under(CAM, P, T, nb, uv, floor)
    raster_piece(CAM, P, T, len(uv), 0, zb, zid)
    out.append({'name': 'rice', 'kind': 'rice', 'mat': 'YbzRice', 'rim': nb, 'paint': [], 'tint': [],
                'ink': [1.5, 2.5], 'closed': len(uv), 'verts': np.round(P, 6).tolist(),
                'tris': [list(map(int, t)) for t in T]})
    print(f'[trace] rice bed: {len(T)} triangles', flush=True)
    # (4) the slices, back to front, each a lens lying over what is there
    for k, ((name, B, Lb, poly, m), (band, line)) in enumerate(zip(shapes, bands), 1):
        extra = np.r_[contour_points([band], 14.0), contour_points([line], 16.0)]
        uv, tris, nb, d, R, lean = outline_mesh(CAM, m, 0.0095, 0.0045, RING, smooth_px=1.0, extra=extra,
                                                extra_margin=4.0)
        x0, y0, w0, h0 = cv2.boundingRect(u8(m))
        x0, y0 = max(x0 - 10, 0), max(y0 - 10, 0)
        x1, y1 = min(x0 + w0 + 20, W), min(y0 + h0 + 20, H)
        f, s, _ = slice_fields(m[y0:y1, x0:x1], B - [x0, y0], Lb - [x0, y0])
        iy = np.clip(np.round(uv[:, 1]).astype(int) - y0, 0, y1 - y0 - 1)
        ix = np.clip(np.round(uv[:, 0]).astype(int) - x0, 0, x1 - x0 - 1)
        fv, sv = f[iy, ix], s[iy, ix]
        top = (BACK_T + (BELLY_T - BACK_T) * np.clip(fv, 0, 1) ** 0.8) * (1 - 0.55 * sv ** 2)
        dd = np.clip(d, 0, RIM_R)
        L = top * np.sqrt(dd * (2 * RIM_R - dd)) / RIM_R
        L = smooth_inner(L, nb, neighbours(len(uv), tris), passes=1)
        gy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
        gx = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
        under = np.where(np.isfinite(zb), zb, np.nan)
        wgt = np.isfinite(under).astype(np.float32)
        sm = cv2.GaussianBlur(np.nan_to_num(under).astype(np.float32), (0, 0), 14) / \
            np.maximum(cv2.GaussianBlur(wgt, (0, 0), 14), 1e-3)
        base = np.where(wgt[gy, gx] > 0.05, sm[gy, gx], on_dish(uv[:, 0], uv[:, 1]))
        here = np.where(np.isfinite(zb[gy, gx]), zb[gy, gx], base)
        sd = np.minimum(base, here - 0.0005)
        P = CAM.on_ray(uv[:, 0], uv[:, 1], sd - L)
        T = oriented(P, [tuple(t) for t in np.asarray(tris)], CAM.toward, True)
        # its back: a cone from its outline to a point behind its middle, in what it lies on
        c = uv[nb:].mean(0) if len(uv) > nb else uv.mean(0)
        apex = CAM.on_ray(np.array([c[0]]), np.array([c[1]]), np.array([float(np.median(sd)) + 0.0015]))
        P = np.r_[P, apex]
        T += oriented(P, [(i, (i + 1) % nb, len(P) - 1) for i in range(nb)], CAM.toward, False)
        raster_piece(CAM, P, T, len(uv), k, zb, zid)
        out.append({'name': name, 'kind': 'slice', 'mat': 'YbzFlesh', 'rim': nb,
                    'paint': [(CHANNELS.index('skin'), 'YbzSkin'), (CHANNELS.index('edge'), 'YbzSkinEdge')],
                    'tint': [(CHANNELS.index('fade'), '#d8c2c0', 0.55), (CHANNELS.index('cut'), '#fff5ef', 0.6)],
                    'ink': INK, 'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]})
        print(f'[trace] {name}: {len(T)} triangles', flush=True)
    # (4) the grains, each on what it lies on where the art draws it (none under the ginger)
    grains = []
    gm = np.zeros((H, W), bool)
    for a, b, w in GINGER:
        mm = np.zeros((H, W), np.uint8)
        cv2.line(mm, a, b, 1, int(w) + 6)
        gm |= mm.astype(bool)
    piles = np.zeros((H, W), np.uint8)
    for poly in PILES:
        cv2.fillPoly(piles, [np.array(poly, np.int32)], 1)
    on_slices = cv2.erode(u8(owner > 0), disk(4)).astype(bool) & ~rice_px & ~piles.astype(bool)   # plain flesh
    found = find_grains(rgb, food, gm | on_slices)
    found += [(x, y, a, ln, ln * 0.62) for x, y, a, ln in GRAINS_ON
              if all(math.hypot(x - g[0], y - g[1]) > 0.42 * (ln + g[3]) for g in found)]
    found += pile_grains(rgb, piles.astype(bool) & ~gm, found, GRAINS_MAX - len(found))
    zs = cv2.erode(np.where(np.isfinite(zb), zb, 1e3).astype(np.float32), disk(3))

    def surf(u, v):   # the top of what is there (or the dish, where nothing is)
        z = float(zs[min(max(int(round(v)), 0), H - 1), min(max(int(round(u)), 0), W - 1)])
        if z > 1e2:
            z = float(on_dish(np.array([u]), np.array([v]))[0])
        return CAM.on_ray(u, v, z)
    for cu, cv_, ang, ln, wd in found:
        a = math.radians(ang)
        du, dv = math.cos(a), math.sin(a)
        p1, p2 = surf(cu - du * ln / 2, cv_ - dv * ln / 2), surf(cu + du * ln / 2, cv_ + dv * ln / 2)
        q1, q2 = surf(cu - dv * wd / 2, cv_ + du * wd / 2), surf(cu + dv * wd / 2, cv_ - du * wd / 2)
        axis = p2 - p1
        side = q2 - q1
        nrm = np.cross(axis, side)
        if nrm @ CAM.toward < 0:
            nrm = -nrm
        nrm /= max(np.linalg.norm(nrm), 1e-9)
        if nrm[2] < 0.35:   # on a steep side: as good as level
            nrm = np.array([0.0, 0.0, 1.0])
        axis = axis - nrm * (axis @ nrm)
        axis /= max(np.linalg.norm(axis), 1e-9)
        length = float(np.linalg.norm(p2 - p1)) * 1.2   # a little fuller: the art's outline round each is inside it
        width = wd / CAM.k * 1.25
        height = width * 0.8
        c = surf(cu, cv_) + nrm * height * 0.3
        grains.append([*np.round(c, 6).tolist(), *np.round(axis, 4).tolist(), *np.round(nrm, 4).tolist(),
                       round(length, 5), round(width, 5), round(height, 5)])
    print(f'[trace] {len(grains)} grains', flush=True)
    # (4) the ginger shreds over all
    for k, (a, b, w) in enumerate(GINGER):
        mm = np.zeros((H, W), np.uint8)
        cv2.line(mm, a, b, 1, int(w))
        mk = cv2.GaussianBlur(mm.astype(np.float32), (0, 0), 1.5) > 0.5
        uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, 0.004, 0.0025, 0.0003, smooth_px=1.0)
        L = profile(d, R, 0.0016)
        P, T = over(CAM, uv, tris, L + 0.0012, zb, on_dish)
        out.append({'name': f'ginger{k}', 'kind': 'bit', 'mat': 'YbzGinger', 'rim': nb, 'paint': [], 'tint': [],
                    'ink': [0.6, 2.0], 'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]})
    np.savez_compressed(PAINT, paint=paint8[::2, ::2])
    data = {'camera': {'el': CAM.el, 'k': CAM.k, 'u0': CAM.u0, 'v0': CAM.v0}, 'paint_scale': 0.5,
            'channels': CHANNELS, 'pieces': out, 'bits': [], 'grains': grains}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT}: {sum(len(o["tris"]) for o in out)} triangles and {len(grains)} grains', flush=True)
    if sheet:
        shown = np.where(food, len(SLICES) + 1, 0).astype(np.int32)
        shown[owner > 0] = owner[owner > 0]
        for cu, cv_, ang, ln, wd in found:
            cv2.ellipse(shown, (int(cu), int(cv_)), (int(ln / 2), int(wd / 2)), ang, 0, 360, len(SLICES) + 2, -1)
        tracing_sheet(sheet, rgba, shown, None, [(250, 215, 200)] * len(SLICES) + [(245, 228, 200), (252, 236, 214)],
                      crop=(100, 280, 1180, 980), title=('原图上的描线（蓝：每一块）', '描出的九片鱼、米饭和米粒'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
