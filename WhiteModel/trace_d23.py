"""Traces 酒蟹's art (新建文件夹/酒蟹.png) for D23, so that its crabs are modelled 1:1 (勾勒) as 番茄炒蛋's egg is
(trace_d06.py): writes food_models/traced_D23.json, which bowls.jiuxie builds the dish from, the colours of the pieces
as food_models/traced_D23_paint.png, and a tracing sheet.

    python WhiteModel/trace_d23.py [--sheet <out.png>]

1. The art's camera: an orthographic view from in front, EL up, K px a metre, the bowl's middle at (U0, V0), fitted
   so that the bowl jiuxie builds covers the art's silhouette best (IoU 0.965).
2. The pieces: a watershed of the art seeded by strokes inside each piece and in the wine (PIECES, WINE, read off the
   art by eye), its ink lines made walls and the ginger on top taken away first, so that each piece's outline follows
   the line the art draws round it: the top shell standing open at the back, the meat and roe inside it, five halves
   of crab, and the claws and legs round them.
3. Their colours by class (orange, olive, pale), smoothed into the paint map (R, G, B), which jiuxie paints onto the
   pieces (meat_fish.paint), so that each colour's edge runs where the art's does: the orange is roe on the halves
   and in the shell, the coral of the shell's toothed rim; the claws and legs are coral, their olive tops and cream
   undersides painted on.
4. The heap T over the pieces' footprint, standing BASE over the wine at its edge (the claws and legs float on it,
   as the art has them) and rising to PEAK.
5. Each piece a surface over its outline, so that from the art's camera it covers exactly what the art paints: a soft
   mound over T, round across like a tube or a plump dome (a circle's arc from its outline in, as wide as it is) and
   leaning a little to the eye, the art's shading in relief (the chambers of the meat, the beads of roe),
   its edges rounded down into a thin crease where it meets the next, and into the wine where it meets that. Its
   outline (the first `rim` vertices) is where jiuxie paints the art's ink line round it.
6. The ginger: the art's shreds found as straight strips (Hough), each a path lying over whatever is under it.
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from trace_d06 import disk, fill_holes, raster, u8

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '酒蟹.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D23.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D23_paint.png')

EL, K, U0, V0 = 35.11, 6913.2, 625.5, 963.9          # the art's camera (1)
SE, CE = math.sin(math.radians(EL)), math.cos(math.radians(EL))
Z_WINE = 0.065                                       # the wine's surface in the bowl (round_bowl's fill_z)
PEAK = 0.022                                         # the heap's top over the wine
BASE = 0.0045                                        # and how far it stands over the wine at its edge (floating)
GX = np.linspace(-0.1, 0.1, 201)                     # world grid for the heap, 1 mm
GSTEP = GX[1] - GX[0]

# (2) strokes inside each piece (art pixels), and what it is: its kind and the material it is built in; then strokes
# in the wine round and between them
PIECES = {
    'shell': ('shell', [(480, 370), (530, 335), (600, 315), (680, 320), (760, 345), (840, 380), (900, 420),
                        (930, 455)]),
    'shell_in': ('inside', [(600, 420), (640, 460), (700, 440), (760, 470), (720, 505)]),
    'body_l': ('body', [(260, 530), (320, 520), (380, 560), (330, 600), (280, 630)]),
    'body_cl': ('body', [(410, 690), (440, 750), (480, 770)]),
    'body_c': ('body', [(500, 640), (540, 700), (600, 780), (660, 760), (620, 650), (650, 700), (715, 680)]),
    'leg_c': ('leg', [(495, 540), (530, 560)]),
    'body_r': ('body', [(830, 610), (880, 640), (930, 620), (960, 680)]),
    'body_br': ('body', [(670, 820), (730, 800), (790, 840), (850, 800)]),
    'claw_ul': ('leg', [(170, 525), (230, 505), (290, 495)]),
    'leg_bl': ('leg', [(330, 440), (380, 430), (430, 440)]),
    'claw_l': ('leg', [(140, 680), (170, 720), (250, 640), (320, 660)]),
    'claw_bl': ('leg', [(250, 760), (330, 780), (300, 830), (430, 830), (500, 860)]),
    'claw_r': ('leg', [(1000, 500), (1060, 540), (1090, 600), (900, 520)]),
    'leg_r': ('leg', [(1050, 720), (1065, 760), (1080, 800), (1090, 840)]),
    'leg_ro': ('leg', [(950, 725), (1010, 730)]),
    'leg_rb': ('leg', [(935, 790), (960, 830), (1000, 860)]),
    'leg_r2': ('leg', [(1093, 705), (1100, 750), (1096, 790)]),
    'leg_rp': ('leg', [(1000, 800), (1025, 775), (1040, 750)]),
}
WINE = [[(235, 415), (280, 380), (330, 357), (390, 342), (440, 335)], [(250, 405), (300, 372), (350, 357), (420, 345)],
        [(380, 395), (405, 385), (430, 372)], [(215, 455), (240, 440)], [(1120, 690), (1125, 750)],
        [(622, 588), (628, 592)], [(688, 603), (694, 606)], [(745, 590), (750, 592)], [(798, 585), (804, 588)],
        [(1010, 400), (1050, 430), (1080, 465)], [(140, 790), (175, 830), (225, 870), (300, 905)],
        [(560, 900), (620, 905), (700, 905)], [(1130, 640), (1150, 700), (1150, 760), (1130, 820)],
        [(930, 860), (980, 865), (1030, 855)]]
# (5) by kind: mesh spacing inside, its relief, the most its mound rises over the heap, and the materials: what it is
# built in, and what is painted on it in turn from which channel of the paint map
KINDS = {
    'shell': dict(gap=0.0048, relief=0.0008, top=0.009, mat='DrunkShell',
                  paint=(('pale', 'DrunkCream'), ('orange', 'CrabClaw'))),
    'inside': dict(gap=0.0024, relief=0.0024, top=0.006, mat='CrabMeat', paint=(('orange', 'CrabRoe'),)),
    'body': dict(gap=0.0045, relief=0.0022, top=0.014, mat='CrabMeat',
                 paint=(('olive', 'DrunkShell'), ('orange', 'CrabRoe'))),
    'leg': dict(gap=0.004, relief=0.0006, top=0.008, mat='CrabClaw',
                paint=(('olive', 'DrunkShell'), ('pale', 'DrunkCream'))),
}
CHANNELS = {'orange': 0, 'olive': 1, 'pale': 2}
GB, RING = 0.0032, 0.0006       # spacing along the outline; the crease ring inside it
PUFF, TILT, EDGE_D = 0.9, 0.5, 0.001
EDGE_IN, EDGE_OUT = -0.0025, -0.005    # a piece's edge under T: against another piece, and into the wine
OVER = 3                                # px a piece reaches under its neighbours
BAND = (5.0, 18.0)                      # the art's shading as relief: band (px)
GINGER_R = 0.0011                       # the shreds' radius


class Camera:
    """Where the art's pixels lie: X = U0 + K·x, Y = V0 - K·(y·sin EL + z·cos EL)."""

    @staticmethod
    def project(x, y, z):
        return U0 + K * np.asarray(x), V0 - K * (np.asarray(y) * SE + np.asarray(z) * CE)

    @staticmethod
    def on_ray(u, v, s):
        """The world point seen at art pixel (u, v), s along the view (larger is further from the camera)."""
        x, q = (u - U0) / K, (V0 - v) / K
        return np.array([x, q * SE + s * CE, q * CE - s * SE])

    @staticmethod
    def depth(P):
        P = np.asarray(P)
        return P[..., 1] * CE - P[..., 2] * SE


def sample(grid, x, y):
    """Bilinear sample of a world-grid array at (x, y)."""
    fx = np.clip((np.asarray(x) - GX[0]) / GSTEP, 0, len(GX) - 1.001)
    fy = np.clip((np.asarray(y) - GX[0]) / GSTEP, 0, len(GX) - 1.001)
    ix, iy = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = fx - ix, fy - iy
    g = grid
    return ((g[iy, ix] * (1 - tx) + g[iy, ix + 1] * tx) * (1 - ty)
            + (g[iy + 1, ix] * (1 - tx) + g[iy + 1, ix + 1] * tx) * ty)


def backproject(u, v, height, lift=0.0, y0=-0.15, y1=0.15, steps=300):
    """Where the art's rays through pixels (u, v) first meet z = height(x, y) + lift: x, y, z arrays."""
    u, v = np.asarray(u, float), np.asarray(v, float)
    lift = np.broadcast_to(np.asarray(lift, float), u.shape)
    x, q = (u - U0) / K, (V0 - v) / K
    prev_y = np.full(u.shape, y0)
    prev_d = (q - y0 * SE) / CE - height(x, prev_y) - lift
    found = np.zeros(u.shape, bool)
    lo, hi = np.full(u.shape, y0), np.full(u.shape, y1)
    for yy in np.linspace(y0, y1, steps)[1:]:
        yv = np.full(u.shape, yy)
        d = (q - yy * SE) / CE - height(x, yv) - lift
        hit = (~found) & (prev_d > 0) & (d <= 0)
        lo[hit], hi[hit] = prev_y[hit], yy
        found |= hit
        prev_y, prev_d = yv, d
    for _ in range(30):
        mid = (lo + hi) / 2
        above = (q - mid * SE) / CE - height(x, mid) - lift > 0
        lo, hi = np.where(above, mid, lo), np.where(above, hi, mid)
    y = (lo + hi) / 2
    return x, y, (q - y * SE) / CE


# ------------------------------------------------------------------ the pieces (2) and their colours (3)

def segment(rgb, alpha):
    """The piece map (0 wine and outside, k + 1 the k-th piece of PIECES), the ginger, and the colour classes."""
    H, W = alpha.shape
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    zone = ((((uu - U0) / (K * 0.086)) ** 2 + ((vv - (V0 - K * 0.068 * CE)) / (K * 0.086 * SE)) ** 2 < 1)
            & (alpha > 128))                                          # inside the bowl's rim
    ginger = zone & (h >= 45) & (h < 60) & (v > 0.9) & (s > 0.22) & (s < 0.65)
    ginger = cv2.morphologyEx(u8(ginger), cv2.MORPH_OPEN, disk(2)).astype(bool)
    gwide = cv2.dilate(u8(ginger), disk(3)).astype(bool)
    img = cv2.inpaint(rgb, u8(gwide), 6, cv2.INPAINT_TELEA)            # the ginger taken away
    img[(v < 0.45) & (s > 0.35) & ~gwide] = 0                         # the ink lines made walls
    markers = np.zeros((H, W), np.int32)
    markers[~zone] = 1
    mk = Image.new('I', (W, H), 0)
    d = ImageDraw.Draw(mk)
    for line in WINE:
        d.line(line, fill=1, width=9)
    for i, (kind, stroke) in enumerate(PIECES.values()):
        d.line(stroke, fill=i + 2, width=7)
        for x, y in stroke:
            d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=i + 2)
    m = np.asarray(mk, np.int32)
    markers[m > 0] = m[m > 0]
    markers[ginger & (markers > 1)] = 0
    lab = cv2.watershed(np.ascontiguousarray(img[..., ::-1]), markers)
    lab[lab < 0] = 0
    for _ in range(3):   # the watershed's lines go to a neighbour
        for ax in (0, 1):
            z = lab == 0
            nb = np.roll(lab, 1, ax)
            lab[z & (nb > 0)] = nb[z & (nb > 0)]
    lab[~zone] = 1
    pieces = np.where(lab > 1, lab - 1, 0)
    orange = (s > 0.6) & (v > 0.85) & (h > 12) & (h < 46)           # roe, the claws' coral: bright and strong
    olive = (h > 32) & (h < 90) & (s > 0.4) & (v > 0.3) & (v < 0.8) & ~orange   # the shell: darker, greener
    pale = (v > 0.85) & (s < 0.45) & ~orange
    food = pieces > 0
    paint = np.zeros((H, W, 3), np.uint8)
    for c, m in enumerate((orange, olive, pale)):   # the order of CHANNELS: specks dropped, gaps closed, softened
        m = cv2.morphologyEx(u8(m & food), cv2.MORPH_OPEN, disk(2))
        n, cc, st, _ = cv2.connectedComponentsWithStats(m)
        keep = np.zeros(n, bool)
        keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 600
        m = cv2.morphologyEx(u8(keep[cc]), cv2.MORPH_CLOSE, disk(5))
        f = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 7.0)   # smooth beside the mesh's spacing: no zigzags
        paint[..., c] = np.clip(f * 255 + 0.5, 0, 255).astype(np.uint8)
    return pieces, ginger, paint


# ------------------------------------------------------------------ the heap (4)

def heap(food):
    """The heap's surface over the pieces' footprint: the footprint back-projected onto the wine, and inside it a
    dome (Poisson) rising to PEAK over the wine."""
    foot = fill_holes(cv2.morphologyEx(u8(food), cv2.MORPH_CLOSE, disk(9)))
    cnt, _ = cv2.findContours(u8(foot), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cnt, key=len)[:, 0, :].astype(float)
    x, y, _ = backproject(c[:, 0], c[:, 1], lambda x, y: np.full_like(x, Z_WINE))
    N = len(GX)
    F = np.zeros((N, N), np.uint8)
    cv2.fillPoly(F, [np.round(np.stack([(x - GX[0]) / GSTEP, (y - GX[0]) / GSTEP], -1) * 16).astype(np.int32)], 1,
                 shift=4)
    F = F.astype(bool)
    inside = F.copy()
    inside[0, :] = inside[-1, :] = inside[:, 0] = inside[:, -1] = False
    ii, jj = np.meshgrid(np.arange(N), np.arange(N), indexing='ij')
    Wp = np.zeros((N, N))
    for parity in [0, 1] * 1500:   # red-black SOR
        msk = inside & ((ii + jj) % 2 == parity)
        nb = (np.roll(Wp, 1, 0) + np.roll(Wp, -1, 0) + np.roll(Wp, 1, 1) + np.roll(Wp, -1, 1) + GSTEP ** 2) / 4
        Wp[msk] += 1.94 * (nb[msk] - Wp[msk])
    Wp[~F] = 0
    return np.where(F, Z_WINE + BASE + (PEAK - BASE) * Wp / Wp.max(), Z_WINE)


# ------------------------------------------------------------------ the pieces' surfaces (5)

def surfaces(pieces, lum, T):
    H, W = pieces.shape
    union = pieces > 0
    open_side = cv2.dilate(u8(~cv2.dilate(u8(union), disk(2)).astype(bool)), disk(5)).astype(bool)   # by the wine
    m = union.astype(np.float32)
    mblur = lambda a, s: cv2.GaussianBlur(a * m, (0, 0), s) / np.maximum(cv2.GaussianBlur(m, (0, 0), s), 1e-3)
    band = np.clip((mblur(lum, BAND[0]) - mblur(lum, BAND[1])) / 22.0, -1, 1)
    out = []
    for pid, (name, (kind, _)) in enumerate(PIECES.items(), 1):
        kp = KINDS[kind]
        G = kp['gap'] * K
        mk = cv2.morphologyEx(u8(pieces == pid), cv2.MORPH_OPEN, disk(3))
        n, cc, st, _ = cv2.connectedComponentsWithStats(mk)
        if n < 2:
            continue
        mk = u8(cc == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA]))
        mk = u8(fill_holes(cv2.dilate(mk, disk(OVER)).astype(bool) & union))
        mk = u8(cv2.GaussianBlur(mk.astype(np.float32), (0, 0), 3.0) > 0.5)   # the watershed's ragged edge smoothed
        x0, y0, w0, h0 = cv2.boundingRect(mk)
        x0, y0 = max(x0 - 8, 0), max(y0 - 8, 0)
        x1, y1 = min(x0 + w0 + 16, W), min(y0 + h0 + 16, H)
        sub = mk[y0:y1, x0:x1]
        cnt, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        c = max(cnt, key=len)[:, 0, :].astype(float)
        c[:, 1] /= SE                       # (u, w), w = v / SE: world-proportional on level ground
        kk = np.exp(-0.5 * (np.arange(-15, 16) / 5.0) ** 2)
        kk /= kk.sum()
        c = np.stack([np.convolve(np.r_[c[-15:, i], c[:, i], c[:15, i]], kk, 'valid') for i in range(2)], -1)
        seg = np.r_[0, np.cumsum(np.hypot(*np.diff(np.r_[c, c[:1]], axis=0).T))]
        tt = np.linspace(0, seg[-1], max(8, int(seg[-1] / (min(GB, kp['gap']) * K))), endpoint=False)
        bpts = np.stack([np.interp(tt, seg, np.r_[c[:, i], c[:1, i]]) for i in range(2)], -1)
        hs = int(round((y1 - y0) / SE))
        sm = np.zeros((hs, x1 - x0), np.uint8)
        cv2.fillPoly(sm, [np.round(bpts * 16).astype(np.int32)], 1, shift=4)
        dst = cv2.distanceTransform(sm, cv2.DIST_L2, 5) / K
        R = dst.max()                                            # its half-width where it is widest
        top = float(np.clip(PUFF * R, 0.002, kp['top']))
        poly = bpts.astype(np.float32).reshape(-1, 1, 2)
        tang = np.roll(bpts, -1, 0) - np.roll(bpts, 1, 0)
        nrm = np.stack([tang[:, 1], -tang[:, 0]], -1) / np.maximum(np.hypot(*tang.T), 1e-9)[:, None]
        probe = bpts[0] - nrm[0] * RING * K
        if cv2.pointPolygonTest(poly, (float(probe[0]), float(probe[1])), False) < 0:
            nrm = -nrm
        ring = bpts - nrm * RING * K
        ring = ring[[cv2.pointPolygonTest(poly, (float(q[0]), float(q[1])), True) > 0.7 * RING * K for q in ring]]
        grid = [(uu, wv) for k_, wv in enumerate(np.arange(0, hs, G * 0.866))
                for uu in np.arange((k_ % 2) * G / 2, x1 - x0, G)
                if int(round(uu)) < sm.shape[1] and dst[min(int(round(wv)), hs - 1), int(round(uu))] > 0.6 * kp['gap']]
        pts = np.r_[bpts, ring.reshape(-1, 2), np.array(grid).reshape(-1, 2)]
        pts = pts.astype(np.float32).astype(np.float64)   # as Subdiv2D keeps them, so its triangles find their points
        nbnd = len(bpts)
        sd = cv2.Subdiv2D((-50, -50, int(x1 - x0 + 100), int(hs + 100)))
        idx = {}
        for k_, p in enumerate(pts):
            idx[(round(float(p[0]), 3), round(float(p[1]), 3))] = k_
            sd.insert((float(p[0]), float(p[1])))
        tris = []
        for t in sd.getTriangleList():
            a, b, c3 = (t[0], t[1]), (t[2], t[3]), (t[4], t[5])
            try:
                ia, ib, ic = (idx[(round(float(p[0]), 3), round(float(p[1]), 3))] for p in (a, b, c3))
            except KeyError:
                continue
            if cv2.pointPolygonTest(poly, ((a[0] + b[0] + c3[0]) / 3, (a[1] + b[1] + c3[1]) / 3), False) >= 0 and \
                    all(cv2.pointPolygonTest(poly, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2), True) >= -0.6
                        for p, q in ((a, b), (b, c3), (c3, a))):
                tris.append((ia, ib, ic))
        tris = np.array(tris)
        if len(tris) == 0:
            continue
        iw = np.clip(np.round(pts[:, 1]).astype(int), 0, hs - 1)
        iu = np.clip(np.round(pts[:, 0]).astype(int), 0, sm.shape[1] - 1)
        d = dst[iw, iu]
        uu, vv = pts[:, 0] + x0, pts[:, 1] * SE + y0
        iy, ix = np.clip(np.round(vv).astype(int), 0, H - 1), np.clip(np.round(uu).astype(int), 0, W - 1)
        edge = np.where(open_side[iy, ix], EDGE_OUT, EDGE_IN)
        lean = np.zeros(len(pts))
        for k_ in range(len(pts)):   # low at its front edge (low in the art), rising to the back
            col = sm[:, iu[k_]]
            r0 = r1 = iw[k_]
            while r0 > 0 and col[r0 - 1]:
                r0 -= 1
            while r1 < hs - 1 and col[r1 + 1]:
                r1 += 1
            lean[k_] = np.clip((r1 - pts[k_, 1]) / max(r1 - r0, 1.0), 0, 1)
        dd = np.clip(d, 0, R)
        arc = np.sqrt(dd * (2 * R - dd)) / R   # round across, like a tube or a plump dome: narrower parts lower
        shape = arc * ((1 - TILT) + TILT * lean ** 0.8)
        L = edge + (top - edge) * shape + kp['relief'] * band[iy, ix] * np.clip(d / (2 * EDGE_D), 0, 1)
        L[:nbnd] = edge[:nbnd]
        nbr = [set() for _ in range(len(pts))]
        for a, b, c3 in tris:
            nbr[a] |= {b, c3}
            nbr[b] |= {a, c3}
            nbr[c3] |= {a, b}
        inner = [[j for j in nb if j >= nbnd] for nb in nbr]
        for _ in range(2):
            avg = np.array([np.mean(L[j]) if j else L[k_] for k_, j in enumerate(inner)])
            L[nbnd:] = 0.5 * L[nbnd:] + 0.5 * avg[nbnd:]
        X, Y, Z = backproject(uu, vv, lambda x, y: sample(T, x, y), lift=L)
        out.append({'name': name, 'kind': kind, 'mat': kp['mat'], 'rim': nbnd,
                    'paint': [(CHANNELS[c], mat) for c, mat in kp['paint']],
                    'verts': np.round(np.stack([X, Y, Z], -1), 6).tolist(), 'tris': tris.tolist(),
                    'uv': np.stack([uu, vv], -1)})
    return out


# ------------------------------------------------------------------ the ginger (6)

def ginger_strips(ginger, zb):
    """The ginger's shreds as paths: straight strips found in its mask (Hough), near-duplicates merged, each sampled
    along its length and laid over whatever the art shows under it (zb: the pieces' depth in the art's view), or on
    the wine."""
    H, W = ginger.shape
    lines = cv2.HoughLinesP(u8(ginger) * 255, 1, math.pi / 180, 40, minLineLength=60, maxLineGap=10)
    segs = [] if lines is None else [tuple(map(float, l)) for l in np.asarray(lines).reshape(-1, 4)]
    segs.sort(key=lambda s: -math.hypot(s[2] - s[0], s[3] - s[1]))
    kept = []
    for x0, y0, x1, y1 in segs:
        a = math.atan2(y1 - y0, x1 - x0)
        dup = False
        for X0, Y0, X1, Y1 in kept:
            A = math.atan2(Y1 - Y0, X1 - X0)
            if abs(math.sin(a - A)) > 0.14:
                continue
            nx, ny = -math.sin(A), math.cos(A)
            if all(abs((px - X0) * nx + (py - Y0) * ny) < 15 for px, py in ((x0, y0), (x1, y1))):   # the same shred
                dup = True
                break
        if not dup:
            kept.append((x0, y0, x1, y1))
    paths = []
    for x0, y0, x1, y1 in kept:
        n = max(2, int(math.hypot(x1 - x0, y1 - y0) / 45))
        pts = []
        for t in np.linspace(0, 1, n + 1):
            u, v = x0 + (x1 - x0) * t, y0 + (y1 - y0) * t
            win = zb[int(v) - 2:int(v) + 3, int(u) - 2:int(u) + 3]
            if np.isfinite(win).any():
                s = float(np.min(win[np.isfinite(win)]))
            else:   # on the wine: where the ray meets z = Z_WINE
                s = ((V0 - v) / K * CE - Z_WINE) / SE
            pts.append(Camera.on_ray(u, v, s - GINGER_R * 1.1))
        paths.append({'pts': np.round(np.array(pts), 6).tolist(), 'uv': [x0, y0, x1, y1]})
    return paths


# ------------------------------------------------------------------ the sheet

def tracing_sheet(path, rgba, pieces, strips):
    a = rgba[..., 3:4].astype(np.float32) / 255
    rgb = (rgba[..., :3] * a + np.array((244, 237, 222)) * (1 - a)).astype(np.uint8)
    H, W = pieces.shape
    traced = (rgb * 0.75 + 255 * 0.25).astype(np.uint8)
    page = np.full((H, W, 3), 255, np.uint8)
    tint = {'shell': (150, 160, 110), 'inside': (250, 200, 140), 'body': (245, 236, 218), 'leg': (240, 170, 120)}
    for pid, (name, (kind, _)) in enumerate(PIECES.items(), 1):
        m = pieces == pid
        if not m.any():
            continue
        page[m] = tint[kind]
        c, _ = cv2.findContours(u8(m), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(traced, c, -1, (30, 60, 190), 3)
        cv2.drawContours(page, c, -1, (150, 100, 40), 2)
    for s in strips:
        x0, y0, x1, y1 = (int(round(q)) for q in s['uv'])
        cv2.line(traced, (x0, y0), (x1, y1), (220, 180, 0), 4)
        cv2.line(page, (x0, y0), (x1, y1), (230, 200, 90), 6)
    crop = (60, 230, 1200, 960)
    A, B = Image.fromarray(traced).crop(crop), Image.fromarray(page).crop(crop)
    font = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', 26)
    sheet = Image.new('RGB', (A.width * 2 + 30, A.height + 60), (244, 237, 222))
    d = ImageDraw.Draw(sheet)
    d.text((10, 12), '原图上的描线（蓝：每块蟹，黄：姜丝）', fill=(96, 62, 40), font=font)
    d.text((A.width + 40, 12), f'描出的 {pieces.max()} 块：蟹壳、壳里的肉和蟹黄、半只蟹身、蟹钳蟹腿', fill=(96, 62, 40),
           font=font)
    sheet.paste(A, (10, 55))
    sheet.paste(B, (A.width + 20, 55))
    sheet.save(path)


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    H, W = alpha.shape
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    pieces, ginger, paint = segment(rgb, alpha)
    print(f'[trace] {pieces.max()} pieces', flush=True)
    T = heap(pieces > 0)
    surf = surfaces(pieces, lum, T)
    print(f'[trace] surfaces: {sum(len(s["tris"]) for s in surf)} triangles', flush=True)
    zb, ib = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
    for s in surf:
        P = np.array(s['verts'])
        tr = np.array(s['tris'])
        raster(s['uv'][tr], Camera.depth(P)[tr], np.zeros(len(tr), int), H, W, zb, ib)
    strips = ginger_strips(ginger, zb)
    print(f'[trace] {len(strips)} ginger shreds', flush=True)
    Image.fromarray(paint).save(PAINT)
    data = {'camera': {'el': EL, 'k': K, 'u0': U0, 'v0': V0}, 'wine': Z_WINE,
            'pieces': [{k: v for k, v in s.items() if k != 'uv'} for s in surf],
            'ginger': [{'pts': g['pts']} for g in strips], 'ginger_r': GINGER_R}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT} and {PAINT}', flush=True)
    if sheet:
        tracing_sheet(sheet, rgba, pieces, strips)
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
