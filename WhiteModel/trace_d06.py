"""Traces 番茄炒蛋's art (新建文件夹/番茄炒蛋.png) for D06, so that its loose, irregular scrambled egg is modelled 1:1
(勾勒): writes food_models/traced_D06.json, which stirfry.fanqie_chaodan builds the dish from, and a tracing sheet.

    python WhiteModel/trace_d06.py [--sheet <out.png>] [--blender <blender.exe>]

1. The art's camera. The art is an orthographic view of round_plate(r=0.1, h=0.034) from straight in front and
   38.3° up (its rim's ellipse fixes the angle), K px a metre, the plate's middle at (U0, V0): every art pixel is a
   ray, and a point on a surface z = f(x, y) is where the ray first meets it (backproject).
2. The art's pixels sorted by colour into egg, red (tomato or sauce), green (scallion) and the rest, the boundaries
   between egg and tomato settled by a watershed on the picture itself (its painted outlines).
3. The tomato wedges: round_wedge (the rounded wedge stirfry builds, dumped from Blender) fitted to each red patch,
   its silhouette seen from the art's camera against the patch, a cut face turned to the eye as the art paints them,
   lying on the heap inside the plate.
4. The heap T: the food's footprint (egg, wedges and scallion together) back-projected onto the plate, and inside it
   a membrane (Poisson) domed up to PEAK, on which every piece lies.
5. The egg split into its loose pieces along the art's creases: a watershed on the art's shading, neighbours with
   only a faint crease between them merged, small bits into a neighbour.
6. Each piece a surface over its outline in the art, so that from the art's camera it covers exactly what the art
   paints: raised over T, leaning a little to the eye, the art's shading in relief, its edge a thin crease (a ring of
   vertices just inside it), a little under its neighbours, the upper of two (the art shades the lower) lying higher.
7. Under it all a surface of deep gold a little under T (it shows in the creases), and the scallion lying on top
   where the art has it (the two pale pieces, 葱白, read off the art by eye).
"""
import json
import math
import os
import subprocess
import sys
import tempfile
import heapq

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '番茄炒蛋.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D06.json')

EL, K, U0, V0 = 38.3, 6046.0, 628.5, 773.3          # the art's camera (1)
SE, CE = math.sin(math.radians(EL)), math.cos(math.radians(EL))
VIEW = np.array([0.0, -CE, SE])                      # towards the camera
GX = np.linspace(-0.1, 0.1, 201)                     # world grid for the heap, 1 mm
GSTEP = GX[1] - GX[0]
# the tomatoes: a point inside each wedge and a box round it, read off the art
WEDGES = [(620, 318), (350, 410), (300, 560), (955, 520), (610, 660), (920, 770), (520, 850), (868, 378)]
ROI = [(515, 262, 732, 378), (272, 350, 428, 480), (158, 438, 515, 664), (803, 436, 1097, 618),
       (448, 566, 778, 768), (738, 646, 1082, 878), (372, 738, 688, 958), (798, 328, 942, 428)]
PALE = [(790, 430, 65, 44, 63), (561, 522, 64, 44, 120)]   # 葱白: centre, length, width (px), angle (degrees)
PEAK = 0.044            # the top of the heap
SINK = 0.003            # a wedge rests this far into the heap
# the egg's surfaces (6)
GAP, GB, RING = 0.0042, 0.0037, 0.0006   # mesh spacing inside and along the outline; the crease ring
LMAX, PUFF = 0.012, 0.9                  # a piece's height: PUFF × its half-width, up to LMAX
TILT, EDGE_D = 0.5, 0.001                # its front edge at 50% of its back's height; edge rounded over 1 mm
LAYER = 0.004                            # the topmost piece this much higher than the lowest
RELIEF, BAND = 0.0015, (8.0, 30.0)       # the art's shading as relief: amplitude, band (px)
OVER = 3                                 # px a piece reaches under its neighbours
EDGE_IN, EDGE_OUT = -0.0025, -0.0035     # a piece's edge under T: against another piece, and on the food's edge
DRAPE = 0.004                            # most a piece lifts to lie over a tomato; past that the tomato shows
FILL_SP, FILL_DEPTH = 0.011, 0.004       # the gold surface under the pieces: mesh spacing, depth under T

u8 = lambda m: m.astype(np.uint8)
disk = lambda r: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def fill_holes(m):
    m = u8(m)
    ff = m.copy()
    cv2.floodFill(ff, np.zeros((m.shape[0] + 2, m.shape[1] + 2), np.uint8), (0, 0), 1)
    return (m | (1 - ff)).astype(bool)


# ------------------------------------------------------------------ geometry (1)

def project(x, y, z):
    return U0 + K * np.asarray(x), V0 - K * (np.asarray(y) * SE + np.asarray(z) * CE)


def plate_in(rho):
    """round_plate's inside: the floor at 8 mm out to 62 mm, then the wall straight up to the rim."""
    rho = np.asarray(rho, float)
    return np.where(rho <= 0.062, 0.008, 0.008 + 0.86 * np.clip(rho - 0.062, 0, 0.03))


def sample(grid, x, y):
    """Bilinear sample of a world-grid array at (x, y)."""
    fx = np.clip((np.asarray(x) - GX[0]) / GSTEP, 0, len(GX) - 1.001)
    fy = np.clip((np.asarray(y) - GX[0]) / GSTEP, 0, len(GX) - 1.001)
    ix, iy = np.floor(fx).astype(int), np.floor(fy).astype(int)
    tx, ty = fx - ix, fy - iy
    g = grid
    return ((g[iy, ix] * (1 - tx) + g[iy, ix + 1] * tx) * (1 - ty)
            + (g[iy + 1, ix] * (1 - tx) + g[iy + 1, ix + 1] * tx) * ty)


def backproject(u, v, height, lift=0.0, y0=-0.13, y1=0.13, steps=260):
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


def on_ray(u, v, s):
    """The world point seen at art pixel (u, v), s along the view (larger is further from the camera)."""
    x, q = (u - U0) / K, (V0 - v) / K
    return np.array([x, q * SE + s * CE, q * CE - s * SE])


def depth_of(P):
    P = np.asarray(P)
    return P[..., 1] * CE - P[..., 2] * SE


def raster(uv, s, ids, H, W, zbuf=None, idbuf=None):
    """Depth-buffers triangles given in art pixels (n,3,2) with depths (n,3) and ids (n,)."""
    if zbuf is None:
        zbuf, idbuf = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
    for (a, b, c), (sa, sb, sc), tid in zip(uv, s, ids):
        x0, x1 = int(max(min(a[0], b[0], c[0]), 0)), int(min(max(a[0], b[0], c[0]) + 1, W - 1))
        y0, y1 = int(max(min(a[1], b[1], c[1]), 0)), int(min(max(a[1], b[1], c[1]) + 1, H - 1))
        det = (b[1] - c[1]) * (a[0] - c[0]) + (c[0] - b[0]) * (a[1] - c[1])
        if x1 < x0 or y1 < y0 or abs(det) < 1e-9:
            continue
        xs, ys = np.meshgrid(np.arange(x0, x1 + 1) + 0.5, np.arange(y0, y1 + 1) + 0.5)
        l1 = ((b[1] - c[1]) * (xs - c[0]) + (c[0] - b[0]) * (ys - c[1])) / det
        l2 = ((c[1] - a[1]) * (xs - c[0]) + (a[0] - c[0]) * (ys - c[1])) / det
        l3 = 1 - l1 - l2
        z = l1 * sa + l2 * sb + l3 * sc
        upd = (l1 >= -1e-6) & (l2 >= -1e-6) & (l3 >= -1e-6) & (z < zbuf[y0:y1 + 1, x0:x1 + 1])
        zbuf[y0:y1 + 1, x0:x1 + 1][upd] = z[upd]
        idbuf[y0:y1 + 1, x0:x1 + 1][upd] = tid
    return zbuf, idbuf


# ------------------------------------------------------------------ colours (2)

def classify(rgb, alpha):
    """Labels: 1 egg, 2 red (tomato or sauce), 3 scallion, 4 the rest (plate, background)."""
    R, G, B = (rgb[..., i].astype(np.float32) for i in range(3))
    H, W = R.shape
    uu, vv = np.meshgrid(np.arange(W), np.arange(H))
    zone = (((uu - U0) / (K * 0.0875)) ** 2 + ((vv - (V0 - K * 0.031 * CE)) / (K * 0.0875 * SE)) ** 2) < 1
    zone &= alpha > 128                                   # inside the inner rim
    mx, mn = np.maximum(np.maximum(R, G), B), np.minimum(np.minimum(R, G), B)
    sat = (mx - mn) / np.maximum(mx, 1)
    gr = G / np.maximum(R, 1)
    green = zone & (G > R * 1.02) & (sat > 0.3)
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    # sure egg, sure tomato, sure plate; the rest settled by a watershed on the picture
    egg_core = zone & (h >= 31) & (h < 62) & (s > 0.2) & (v > 0.62) & ~green
    tom_core = zone & ((h < 19) | (h > 340)) & (s > 0.5)
    plate_core = zone & (s < 0.13) & ~green
    n, lab, st, _ = cv2.connectedComponentsWithStats(u8(egg_core))
    for j in range(1, n):   # egg-coloured islands in a tomato are its seeds
        if st[j, cv2.CC_STAT_AREA] < 1500:
            x, y, w, hh = st[j, :4]
            sl = (slice(max(y - 8, 0), y + hh + 8), slice(max(x - 8, 0), x + w + 8))
            m = lab[sl] == j
            ring = cv2.dilate(u8(m), disk(7)).astype(bool) & ~m
            if tom_core[sl][ring].mean() > 0.45:
                egg_core[sl][m] = False
    markers = np.zeros((H, W), np.int32)
    markers[~zone | plate_core] = 4
    markers[cv2.erode(u8(tom_core), disk(1)).astype(bool)] = 2
    markers[cv2.erode(u8(egg_core), disk(1)).astype(bool)] = 1
    markers[green] = 3
    ws = cv2.watershed(np.ascontiguousarray(rgb[..., ::-1]), markers)
    lab = np.where(ws < 0, 0, ws)
    for _ in range(2):   # the watershed's lines go to a neighbour
        for ax in (0, 1):
            z = lab == 0
            nb = np.roll(lab, 1, ax)
            lab[z & (nb > 0)] = nb[z & (nb > 0)]
    return lab, hsv


# ------------------------------------------------------------------ tomato wedges (3)

class Wedge:
    """round_wedge(r=1, w=0.5, edge=0.1) after soft(), as stirfry builds it, for fitting."""
    CUTN = [np.array([-math.sin(0.5), math.cos(0.5), 0.0]), np.array([-math.sin(0.5), -math.cos(0.5), 0.0])]

    def __init__(self, blender):
        path = os.path.join(tempfile.gettempdir(), 'trace_d06_wedge.json')
        script = ("import sys, json; sys.path.insert(0, %r)\n"
                  "from mathutils import Matrix\n"
                  "from food_models.core import Part\n"
                  "from food_models.stirfry import round_wedge\n"
                  "p = Part()\n"
                  "with p.soft():\n"
                  "    round_wedge(p, Matrix(), r=1.0, w=0.5, edge=0.1)\n"
                  "bm = p.bm; bm.normal_update(); bm.verts.index_update()\n"
                  "json.dump({'verts': [list(v.co) for v in bm.verts],"
                  " 'faces': [[v.index for v in f.verts] for f in bm.faces],"
                  " 'skin': [p.mats[f.material_index] == 'TomatoRed' for f in bm.faces],"
                  " 'normals': [list(f.normal) for f in bm.faces]}, open(%r, 'w'))\n") % (HERE, path)
        subprocess.run([blender, '-b', '--factory-startup', '--python-expr', script], check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        c = json.load(open(path))
        self.V, self.N = np.array(c['verts']), np.array(c['normals'])
        self.F, self.skin = c['faces'], np.array(c['skin'])

    @staticmethod
    def rot(psi, alpha, phi):
        """Local z (the tomato's axis) to direction (psi, alpha); local x (the skin) rolled phi about it."""
        d = np.array([math.cos(psi) * math.cos(alpha), math.sin(psi) * math.cos(alpha), math.sin(alpha)])
        ref = np.array([0.0, 0.0, 1.0]) if abs(d[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
        a = np.cross(ref, d)
        a /= np.linalg.norm(a)
        b = np.cross(d, a)
        x = math.cos(phi) * b + math.sin(phi) * a
        return np.stack([x, np.cross(d, x), d], 1)

    def linear(self, p):
        """The 3×3 map from the canonical wedge to a fitted one: p = (u, v, r, psi, alpha, phi, sa, sb, sc)."""
        return self.rot(*p[3:6]) @ np.diag([p[6] * p[2], p[7] * p[2], p[8] * p[2]])

    def place(self, p, T):
        """Its centre on the ray through its screen centre, as deep as lets it rest SINK into the heap T."""
        Lm = self.linear(p)
        rel = self.V @ Lm.T

        def f(s):
            Pw = on_ray(p[0], p[1], s) + rel
            return np.min(Pw[:, 2] - sample(T, Pw[:, 0], Pw[:, 1]))
        lo, hi = -0.25, 0.25
        for _ in range(60):
            mid = (lo + hi) / 2
            lo, hi = (mid, hi) if f(mid) > -SINK else (lo, mid)
        return on_ray(p[0], p[1], (lo + hi) / 2), Lm

    def tris(self, C, Lm, wid):
        """Its front-facing triangles in the art: (uv, depth, id = wid * 2 + skin)."""
        Pw = C + self.V @ Lm.T
        u, v = project(*Pw.T)
        s = depth_of(Pw)
        Nw = self.N @ np.linalg.inv(Lm)
        uv, ss, ids = [], [], []
        for k, f in enumerate(self.F):
            if Nw[k] @ VIEW > 0:
                for j in range(1, len(f) - 1):
                    t = (f[0], f[j], f[j + 1])
                    uv.append([(u[i], v[i]) for i in t])
                    ss.append([s[i] for i in t])
                    ids.append(wid * 2 + int(self.skin[k]))
        return np.array(uv), np.array(ss), np.array(ids)

    def render(self, p, box, scale=0.5):
        """Its silhouette in a box of the art: 2 skin, 1 cut face, 0 nothing."""
        D = np.array(p[6:9])
        R = self.rot(*p[3:6])
        P = ((self.V * D) @ R.T) * p[2]
        x0, y0, x1, y1 = box
        pu = (p[0] + K * P[:, 0] - x0) * scale
        pv = (p[1] - K * (P[:, 1] * SE + P[:, 2] * CE) - y0) * scale
        front = ((self.N / D) @ R.T) @ VIEW > 0
        im = Image.new('L', (int((x1 - x0) * scale) + 1, int((y1 - y0) * scale) + 1), 0)
        dr = ImageDraw.Draw(im)
        for k in np.nonzero(front)[0]:
            dr.polygon([(pu[j], pv[j]) for j in self.F[k]], fill=2 if self.skin[k] else 1)
        return np.asarray(im)


def fit_wedges(wedge, rgb, lab, hsv, T):
    """Each wedge's pose and size, so that from the art's camera it covers its red patch and little else."""
    H, W = lab.shape
    red = cv2.morphologyEx(u8(lab == 2), cv2.MORPH_CLOSE, disk(4)).astype(bool)
    markers = np.zeros((H, W), np.int32)
    for i, (x, y) in enumerate(WEDGES):
        cv2.circle(markers, (x, y), 14, i + 1, -1)
    img = rgb.copy()
    img[~red] = (0, 0, 255)   # a wall of colour: the flood keeps to the red, and crosses elsewhere last
    ws = cv2.watershed(np.ascontiguousarray(img[..., ::-1]), markers)
    targets = []
    for i, (x0, y0, x1, y1) in enumerate(ROI):
        box = np.zeros((H, W), bool)
        box[y0:y1, x0:x1] = True
        t = fill_holes(cv2.morphologyEx(u8((ws == i + 1) & box & red), cv2.MORPH_CLOSE, disk(4)))   # seeds, glints
        targets.append(cv2.morphologyEx(u8(t), cv2.MORPH_OPEN, disk(3)).astype(bool))
    egg, green, outside = lab == 1, lab == 3, lab == 4
    sauce = red & ~np.any(targets, 0)
    deg = hsv[..., 0] * 360 / 256
    hh = np.where(deg > 300, deg - 360, deg)
    s, v = hsv[..., 1] / 255, hsv[..., 2] / 255
    seeds = np.where((s < 0.35) & (v > 0.88), -1.0, np.where((hh >= 17) & (s > 0.35), 1.0, 0.0)).astype(np.float32)
    LO, HI = np.array([0.8, 0.85, 0.85]), np.array([1.25, 1.4, 1.2])   # near a real wedge's proportions

    def physics(p):
        """0 for a wedge lying on the heap in the plate, a cut face to the eye; more the further from that."""
        C, Lm = wedge.place(p, T)
        Pw = C + wedge.V @ Lm.T
        rho = np.hypot(Pw[:, 0], Pw[:, 1])
        out = np.clip(rho - 0.088, 0, None).max() / 0.01
        low = np.clip(plate_in(rho) + 0.001 - Pw[:, 2], 0, None).max() / 0.005
        tilt = max(0.0, abs(p[4]) - math.radians(18)) / math.radians(10)
        size = max(0.0, 2 * p[2] * max(p[6], p[7]) - 0.07) / 0.01
        R, D = wedge.rot(*p[3:6]), np.array(p[6:9])
        best = max(float((R @ (n / D)) @ VIEW / np.linalg.norm(R @ (n / D))) for n in Wedge.CUTN)
        face = max(0.0, math.cos(math.radians(32)) - best) / 0.15
        return out ** 2 + low ** 2 + tilt ** 2 + size ** 2 + face ** 2

    rng = np.random.default_rng(1)
    fits = []
    for i in range(len(WEDGES)):
        x0, y0, x1, y1 = ROI[i]
        box = (max(x0 - 70, 0), max(y0 - 70, 0), min(x1 + 70, W), min(y1 + 70, H))
        sl = (slice(box[1], box[3]), slice(box[0], box[2]))
        small = lambda m: cv2.resize(u8(m[sl]), None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA).astype(bool)
        tgt, oth = small(targets[i]), small(np.any([t for j, t in enumerate(targets) if j != i], 0))
        eg, gn, sa, ou = small(egg), small(green), small(sauce), small(outside)
        fl = cv2.resize(seeds[sl], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)

        def score(p):
            Lr = wedge.render(p, box)[:tgt.shape[0], :tgt.shape[1]]
            S_ = Lr > 0
            pen = (1.2 * (S_ & eg).sum() + 0.6 * (S_ & gn).sum() + (S_ & oth).sum() + 0.6 * (S_ & sa).sum()
                   + 1.5 * (S_ & ou).sum())   # over egg, scallion, another wedge, sauce, plate
            face = (fl[(Lr == 1) & tgt].sum() - fl[(Lr == 2) & tgt].sum()) * 0.8
            return ((S_ & tgt).sum() - (tgt & ~S_).sum() - pen + face) / max(tgt.sum(), 1) - 0.2 * physics(p)

        def search(p, sc, step, its, decay):
            for _ in range(its):
                cand = p + rng.normal(0, 1, (8, 9)) * step
                cand[:, 6:] = np.clip(cand[:, 6:], LO, HI)
                cand[:, 2] = np.clip(cand[:, 2], 0.012, 0.05)
                cand[:, 4] = np.clip(cand[:, 4], -1.2, 1.2)
                scs = [score(c) for c in cand]
                j = int(np.argmax(scs))
                if scs[j] > sc:
                    p, sc = cand[j], scs[j]
                else:
                    step = step * decay
            return p, sc
        ys, xs = np.nonzero(targets[i])
        ev, evec = np.linalg.eigh(np.cov(np.stack([xs, ys])))
        ang = math.atan2(evec[1, 1], evec[0, 1])   # the patch's long axis
        r0 = 0.024 * math.sqrt(len(xs) / 18000)
        best = (-1e9, None)
        for phi in np.linspace(0, 2 * math.pi, 8, endpoint=False):
            for psi in (-ang, -ang + math.pi / 2):
                p0 = np.array([xs.mean(), ys.mean(), r0, psi, 0.0, phi, 1.0, 1.0, 1.0])
                p, sc = search(p0, score(p0), np.array([12.0, 12.0, 0.004, 0.35, 0.3, 0.5, 0.12, 0.12, 0.12]), 90, 0.93)
                if sc > best[0]:
                    best = (sc, p)
        p, sc = search(best[1], best[0], np.array([3.0, 3.0, 0.001, 0.08, 0.08, 0.12, 0.04, 0.04, 0.04]), 250, 0.97)
        Sr = wedge.render(p, box)[:tgt.shape[0], :tgt.shape[1]] > 0
        print(f'[trace] wedge {i + 1}: IoU {(Sr & tgt).sum() / max((Sr | tgt).sum(), 1):.3f}', flush=True)
        fits.append([float(x) for x in p])
    return fits


# ------------------------------------------------------------------ the heap (4)

def heap(foot):
    """The footprint's outline back-projected onto the plate (2.5 mm over it), and the heap's surface inside it."""
    cnt, _ = cv2.findContours(u8(foot), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cnt, key=len)[:, 0, :].astype(float)
    k = np.exp(-0.5 * (np.arange(-12, 13) / 4.0) ** 2)
    k /= k.sum()
    c = np.stack([np.convolve(np.r_[c[-12:, i], c[:, i], c[:12, i]], k, 'valid') for i in range(2)], -1)
    x, y, _ = backproject(c[:, 0], c[:, 1], lambda x, y: plate_in(np.hypot(x, y)), lift=0.0025)
    N = len(GX)
    F = np.zeros((N, N), np.uint8)
    cv2.fillPoly(F, [np.round(np.stack([(x - GX[0]) / GSTEP, (y - GX[0]) / GSTEP], -1) * 16).astype(np.int32)], 1,
                 shift=4)
    F = F.astype(bool)
    XX, YY = np.meshgrid(GX, GX)
    base = plate_in(np.hypot(XX, YY)) + 0.0025
    inside = F.copy()
    inside[0, :] = inside[-1, :] = inside[:, 0] = inside[:, -1] = False
    ii, jj = np.meshgrid(np.arange(N), np.arange(N), indexing='ij')

    def solve(rhs, T):   # red-black SOR
        for parity in [0, 1] * 1500:
            msk = inside & ((ii + jj) % 2 == parity)
            nb = (np.roll(T, 1, 0) + np.roll(T, -1, 0) + np.roll(T, 1, 1) + np.roll(T, -1, 1) + rhs * GSTEP ** 2) / 4
            T[msk] += 1.94 * (nb[msk] - T[msk])
        return T
    Hm = solve(np.zeros((N, N)), base.copy())        # the outline's heights carried in
    Wp = solve(np.ones((N, N)), np.zeros((N, N)))    # and a dome
    Wp[~F] = 0
    A = (PEAK - Hm[np.unravel_index(np.argmax(Wp), Wp.shape)]) / Wp.max()
    return np.where(F, Hm + A * Wp, base), np.stack([x, y], -1)


def footprint(*masks):
    foot = cv2.morphologyEx(u8(np.any(masks, 0)), cv2.MORPH_CLOSE, disk(9))
    n, cc, st, _ = cv2.connectedComponentsWithStats(foot)
    return fill_holes(cc == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA]))


# ------------------------------------------------------------------ egg pieces (5)

def egg_mask(lab, sil):
    """The egg: its colours, less islands in the tomatoes (seeds), plus scallion lying on it, small holes filled."""
    egg = lab == 1
    green = lab == 3
    n, cc, st, _ = cv2.connectedComponentsWithStats(u8(green))
    for j in range(1, n):
        m = cc == j
        if st[j, cv2.CC_STAT_AREA] >= 80 and egg[cv2.dilate(u8(m), disk(6)).astype(bool) & ~m].mean() > 0.4:
            egg |= cv2.dilate(u8(m), disk(2)).astype(bool)
    eo = cv2.morphologyEx(u8(egg), cv2.MORPH_OPEN, disk(3)).astype(bool)
    n, cc, st, _ = cv2.connectedComponentsWithStats(u8(eo))
    for j in range(1, n):
        if sil[cc == j].mean() > 0.6 or st[j, cv2.CC_STAT_AREA] < 700:
            eo[cc == j] = False
    n, cc, st, _ = cv2.connectedComponentsWithStats(u8(~eo), connectivity=4)
    small = np.zeros(n, bool)
    small[1:] = st[1:, cv2.CC_STAT_AREA] < 600
    egg = eo | small[cc]
    d = cv2.distanceTransform(u8(egg), cv2.DIST_L2, 5)
    n, cc, st, _ = cv2.connectedComponentsWithStats(u8(egg))
    for j in range(1, n):
        if d[cc == j].max() < 6:
            egg[cc == j] = False
    return egg


def split_egg(egg, lum, sig=3.0, tau=20.0, amin=3500, amax=45000):
    """Pieces: a watershed on the art's shading (creases and edges high ground), then neighbours with only a faint
    crease between them merged, small bits into the neighbour they share most edge with."""
    H, W = egg.shape
    m = egg.astype(np.float32)
    lb = cv2.GaussianBlur(lum * m, (0, 0), sig) / np.maximum(cv2.GaussianBlur(m, (0, 0), sig), 1e-3)
    dist = cv2.distanceTransform(u8(egg), cv2.DIST_L2, 5)
    elev = -(lb + np.minimum(dist, 12))
    elev[~egg] = 1e9
    mark = egg & (elev <= cv2.erode(elev.astype(np.float32), disk(6)) + 1e-3) & (dist > 3)
    n, mlab = cv2.connectedComponents(u8(mark))
    lab = np.zeros((H, W), np.int32)
    lab[mark] = mlab[mark]
    hq = [(float(elev[y, x]), int(y), int(x)) for y, x in zip(*np.nonzero(mark))]
    heapq.heapify(hq)
    while hq:
        e, y, x = heapq.heappop(hq)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            yy, xx = y + dy, x + dx
            if 0 <= yy < H and 0 <= xx < W and egg[yy, xx] and lab[yy, xx] == 0:
                lab[yy, xx] = lab[y, x]
                heapq.heappush(hq, (max(float(elev[yy, xx]), e), yy, xx))
    area = np.bincount(lab.ravel()).astype(float).tolist()
    lsum = np.bincount(lab.ravel(), weights=lb.ravel()).tolist()
    adj = {}
    for a, b, la, lb2 in ((lab[:, :-1], lab[:, 1:], lb[:, :-1], lb[:, 1:]),
                          (lab[:-1, :], lab[1:, :], lb[:-1, :], lb[1:, :])):
        msk = (a > 0) & (b > 0) & (a != b)
        pa, pb = np.minimum(a[msk], b[msk]), np.maximum(a[msk], b[msk])
        uk, inv = np.unique(pa.astype(np.int64) * 100000 + pb, return_inverse=True)
        s_, c_ = np.bincount(inv, weights=np.minimum(la[msk], lb2[msk])), np.bincount(inv)
        for k, ss, cc in zip(uk, s_, c_):
            ka, kb = int(k // 100000), int(k % 100000)
            e = adj.setdefault(ka, {}).setdefault(kb, [0.0, 0])
            e[0] += ss
            e[1] += cc
            adj.setdefault(kb, {})[ka] = e
    parent = list(range(len(area)))

    def find(a):
        while parent[a] != a:
            parent[a] = parent[parent[a]]
            a = parent[a]
        return a

    def cost(a, b):
        s_, c_ = adj[a][b]
        depth = 0.5 * (lsum[a] / area[a] + lsum[b] / area[b]) - s_ / c_
        if min(area[a], area[b]) < amin:
            return -1e6 + depth - c_ * 0.01
        if area[a] + area[b] > amax or depth > tau:
            return None
        return depth
    hq = [(c, a, b) for a in adj for b in adj[a] if a < b for c in [cost(a, b)] if c is not None]
    heapq.heapify(hq)
    alive = set(adj)
    while hq:
        c, a, b = heapq.heappop(hq)
        if a not in alive or b not in alive or b not in adj.get(a, {}):
            continue
        c2 = cost(a, b)
        if c2 is None or abs(c2 - c) > 1e-9:
            if c2 is not None:
                heapq.heappush(hq, (c2, a, b))
            continue
        parent[b] = a
        area[a] += area[b]
        lsum[a] += lsum[b]
        for nb, e in adj[b].items():
            if nb == a:
                continue
            if nb in adj[a]:
                adj[a][nb][0] += e[0]
                adj[a][nb][1] += e[1]
            else:
                adj[a][nb] = e
            adj[nb][a] = adj[a][nb]
            del adj[nb][b]
        del adj[a][b]
        del adj[b]
        alive.discard(b)
        for nb in adj[a]:
            c3 = cost(min(a, nb), max(a, nb))
            if c3 is not None:
                heapq.heappush(hq, (c3, min(a, nb), max(a, nb)))
    root = np.array([find(i) for i in range(len(parent))])
    pl = np.where(lab > 0, root[lab], 0)
    ids = [i for i in np.unique(pl) if i > 0]
    remap = np.zeros(pl.max() + 1, np.int32)
    remap[ids] = np.arange(1, len(ids) + 1)
    return remap[pl]


# ------------------------------------------------------------------ the egg's surfaces (6)

def egg_surfaces(pieces, sil, lab, lum, T, wz):
    H, W = pieces.shape
    over = (pieces > 0) & sil   # egg over a tomato kept only where it is a sheet, not a sliver along its edge
    pieces = np.where(over & ~cv2.morphologyEx(u8(over), cv2.MORPH_OPEN, disk(6)).astype(bool), 0, pieces)
    union = pieces > 0
    open_side = cv2.dilate(u8(~(cv2.dilate(u8(union), disk(2)).astype(bool) | sil | (lab == 3))), disk(5)).astype(bool)
    m = union.astype(np.float32)
    mblur = lambda x, s: cv2.GaussianBlur(x * m, (0, 0), s) / np.maximum(cv2.GaussianBlur(m, (0, 0), s), 1e-3)
    band = np.clip((mblur(lum, BAND[0]) - mblur(lum, BAND[1])) / 22.0, -1, 1)   # the art's puffs (+), creases (-)
    # which lies on which: where two pieces meet the art shades the lower, so each scores how much brighter it is
    lb = mblur(lum, 2.0)
    near = {}
    for pid in range(1, pieces.max() + 1):
        mk = pieces == pid
        if mk.any():
            for q in np.unique(pieces[cv2.dilate(u8(mk), disk(3)).astype(bool) & ~mk & union]):
                side = cv2.dilate(u8(pieces == q), disk(8)).astype(bool) & mk
                if side.sum() > 30:
                    near[(pid, int(q))] = (float(lb[side].mean()), int(side.sum()))
    score = {}
    for (a, b), (la, na) in near.items():
        if (b, a) in near:
            w = min(na, near[(b, a)][1])
            s_, ww = score.get(a, (0.0, 0.0))
            score[a] = (s_ + w * (la - near[(b, a)][0]), ww + w)
    order = sorted((a for a in score if score[a][1] > 0), key=lambda a: score[a][0] / score[a][1])
    lift = {a: LAYER * k / max(len(order) - 1, 1) for k, a in enumerate(order)}
    G = GAP * K
    out = []
    for pid in range(1, pieces.max() + 1):
        mk = cv2.morphologyEx(u8(pieces == pid), cv2.MORPH_OPEN, disk(4))
        n, cc, st, _ = cv2.connectedComponentsWithStats(mk)
        if n < 2:
            continue
        mk = u8(cc == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA]))
        if mk.sum() < 600:
            continue
        mk = u8(fill_holes(cv2.dilate(mk, disk(OVER)).astype(bool) & union))   # under the neighbours a little
        x0, y0, w0, h0 = cv2.boundingRect(mk)
        x0, y0 = max(x0 - 8, 0), max(y0 - 8, 0)
        x1, y1 = min(x0 + w0 + 16, W), min(y0 + h0 + 16, H)
        sub = mk[y0:y1, x0:x1]
        # its outline, smoothed and resampled, in (u, w), w = v / SE: world-proportional on level ground
        cnt, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        c = max(cnt, key=len)[:, 0, :].astype(float)
        c[:, 1] /= SE
        kk = np.exp(-0.5 * (np.arange(-15, 16) / 5.0) ** 2)
        kk /= kk.sum()
        c = np.stack([np.convolve(np.r_[c[-15:, i], c[:, i], c[:15, i]], kk, 'valid') for i in range(2)], -1)
        seg = np.r_[0, np.cumsum(np.hypot(*np.diff(np.r_[c, c[:1]], axis=0).T))]
        tt = np.linspace(0, seg[-1], max(8, int(seg[-1] / (GB * K))), endpoint=False)
        bpts = np.stack([np.interp(tt, seg, np.r_[c[:, i], c[:1, i]]) for i in range(2)], -1)
        hs = int(round((y1 - y0) / SE))
        sm = np.zeros((hs, x1 - x0), np.uint8)
        cv2.fillPoly(sm, [np.round(bpts * 16).astype(np.int32)], 1, shift=4)
        dst = cv2.distanceTransform(sm, cv2.DIST_L2, 5) / K     # metres from the edge
        top = float(np.clip(PUFF * dst.max(), 0.006, LMAX)) + lift.get(pid, 0.0)
        poly = bpts.astype(np.float32).reshape(-1, 1, 2)
        # a ring just inside the outline (the dive into the heap a thin line, the crease), and a hexagonal grid
        tang = np.roll(bpts, -1, 0) - np.roll(bpts, 1, 0)
        nrm = np.stack([tang[:, 1], -tang[:, 0]], -1) / np.maximum(np.hypot(*tang.T), 1e-9)[:, None]
        probe = bpts[0] - nrm[0] * RING * K
        if cv2.pointPolygonTest(poly, (float(probe[0]), float(probe[1])), False) < 0:
            nrm = -nrm
        ring = bpts - nrm * RING * K
        ring = ring[[cv2.pointPolygonTest(poly, (float(q[0]), float(q[1])), True) > 0.7 * RING * K for q in ring]]
        grid = [(uu, wv) for k_, wv in enumerate(np.arange(0, hs, G * 0.866))
                for uu in np.arange((k_ % 2) * G / 2, x1 - x0, G)
                if int(round(uu)) < sm.shape[1] and dst[min(int(round(wv)), hs - 1), int(round(uu))] > 0.6 * GAP]
        pts = np.r_[bpts, ring.reshape(-1, 2), np.array(grid).reshape(-1, 2)]
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
        # leaning to the eye: low at its front edge (low in the art), rising to the back, where it drops behind
        lean = np.zeros(len(pts))
        for k_ in range(len(pts)):
            col = sm[:, iu[k_]]
            r0 = r1 = iw[k_]
            while r0 > 0 and col[r0 - 1]:
                r0 -= 1
            while r1 < hs - 1 and col[r1 + 1]:
                r1 += 1
            lean[k_] = np.clip((r1 - pts[k_, 1]) / max(r1 - r0, 1.0), 0, 1)
        shape = np.sqrt(np.clip(d / EDGE_D, 0, 1)) * ((1 - TILT) + TILT * lean ** 0.8)
        L = edge + (top - edge) * shape + RELIEF * band[iy, ix] * np.clip(d / (2 * EDGE_D), 0, 1)
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
        P = np.stack([X, Y, Z], -1)
        # a tomato in front: the egg comes over it (1.2 mm proud, its edge tucked in) if that is a small lift;
        # where the tomato stands well in front, the egg is left out and the tomato shows
        s_e, s_w = depth_of(P), wz[iy, ix]
        fin = np.isfinite(s_w)
        need = np.where(fin, np.maximum(0.0, s_e - (s_w - 0.0012)), 0.0)
        need[:nbnd] = np.where(fin[:nbnd], np.maximum(0.0, s_e[:nbnd] - (s_w[:nbnd] + 0.001)), 0.0)
        if (need > DRAPE).any():
            tris = tris[~(need > DRAPE)[tris].any(1)]
            if len(tris) == 0:
                continue
            used = np.unique(tris)
            remap = -np.ones(len(pts), int)
            remap[used] = np.arange(len(used))
            tris = remap[tris]
            X, uu, vv, need, s_e = (a[used] for a in (X, uu, vv, need, s_e))
            P = P[used]
            nbr = [set() for _ in range(len(used))]
            for a, b, c3 in tris:
                nbr[a] |= {b, c3}
                nbr[b] |= {a, c3}
                nbr[c3] |= {a, b}
        if need.max() > 0:
            lift_ = need.copy()
            for _ in range(6):   # spread onto the neighbours, so that it rises as a slope
                avg = np.array([np.mean(lift_[list(nb)]) if nb else 0.0 for nb in nbr])
                lift_ = np.maximum(need, 0.5 * lift_ + 0.5 * avg)
            s_new = s_e - lift_
            q = (V0 - vv) / K
            P = np.stack([X, q * SE + s_new * CE, q * CE - s_new * SE], -1)
        out.append({'verts': np.round(P, 6).tolist(), 'tris': tris.tolist(), 'uv': np.stack([uu, vv], -1)})
    return out


# ------------------------------------------------------------------ under it all, and on top (7)

def filler(outline, T):
    """A surface FILL_DEPTH under the heap's top over the footprint, its edge just inside the plate."""
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(np.r_[outline, outline[:1]], axis=0).T))]
    tt = np.linspace(0, seg[-1], int(seg[-1] / FILL_SP), endpoint=False)
    bpts = np.stack([np.interp(tt, seg, np.r_[outline[:, i], outline[:1, i]]) for i in range(2)], -1)
    poly = (bpts * 1e4).astype(np.float32).reshape(-1, 1, 2)
    ipts = [(x, y) for k, y in enumerate(np.arange(-0.1, 0.1, FILL_SP * 0.866))
            for x in np.arange(-0.1 + (k % 2) * FILL_SP / 2, 0.1, FILL_SP)
            if cv2.pointPolygonTest(poly, (x * 1e4, y * 1e4), True) > 0.5 * FILL_SP * 1e4]
    pts = np.r_[bpts, np.array(ipts)]
    sd = cv2.Subdiv2D((-1200, -1200, 2400, 2400))
    idx = {}
    for k, p in enumerate(pts):
        q = (float(p[0] * 1e4), float(p[1] * 1e4))
        idx[(round(q[0], 2), round(q[1], 2))] = k
        sd.insert(q)
    tris = []
    for t in sd.getTriangleList():
        a, b, c = (t[0], t[1]), (t[2], t[3]), (t[4], t[5])
        try:
            ids = [idx[(round(float(p[0]), 2), round(float(p[1]), 2))] for p in (a, b, c)]
        except KeyError:
            continue
        if cv2.pointPolygonTest(poly, ((a[0] + b[0] + c[0]) / 3, (a[1] + b[1] + c[1]) / 3), False) >= 0:
            tris.append(ids)
    z = sample(T, pts[:, 0], pts[:, 1]) - FILL_DEPTH
    z[:len(bpts)] = plate_in(np.hypot(bpts[:, 0], bpts[:, 1])) - 0.0005
    return {'verts': np.round(np.c_[pts, z], 6).tolist(), 'tris': tris}


def scallions(lab, T, zb):
    """The art's scallion: each green piece (two touching ones split) and the pale ones, lying on whatever is
    under its middle in the art's view. Also returns where each is in the art, for the sheet."""
    H, W = lab.shape
    green = cv2.morphologyEx(u8(lab == 3), cv2.MORPH_OPEN, disk(2))
    n, cc, st, _ = cv2.connectedComponentsWithStats(green)
    items = []
    food = (lab == 1) | (lab == 2)
    for j in range(1, n):
        a = st[j, cv2.CC_STAT_AREA]
        m = cc == j
        if a < 300 or food[cv2.dilate(u8(m), disk(6)).astype(bool) & ~m].mean() < 0.5:
            continue   # too small, or a green-tinged wash on the plate, not a piece lying on the food
        pts = np.stack(np.nonzero(m)[::-1], -1).astype(np.float32)
        groups = [pts]
        if a > 3500:   # two pieces touching
            _, lbl, _ = cv2.kmeans(pts, 2, None, (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 50, 0.1), 5,
                                   cv2.KMEANS_PP_CENTERS)
            groups = [pts[lbl[:, 0] == k] for k in (0, 1)]
        for g in groups:
            (cu, cv_), (rw, rh), ang = cv2.minAreaRect(g)
            if rw < rh:
                rw, rh, ang = rh, rw, ang + 90
            items.append((cu, cv_, rw, rh, ang, False))
    items += [(u, v, l, w, a, True) for u, v, l, w, a in PALE]
    out = []
    for cu, cv_, rw, rh, ang, pale in items:
        win = zb[int(cv_) - 3:int(cv_) + 4, int(cu) - 3:int(cu) + 4]
        if np.isfinite(win).any():
            s0 = float(np.min(win[np.isfinite(win)]))
        else:   # over a gap: the heap
            X, Y, Z = backproject(np.array([cu]), np.array([cv_]), lambda x, y: sample(T, x, y), lift=-0.002)
            s0 = float(depth_of(np.array([X[0], Y[0], Z[0]])))
        r = float(np.clip(rh / K / 2 * 0.95, 0.0031, 0.0042))
        th = math.radians(ang)
        out.append({'c': np.round(on_ray(cu, cv_, s0 - 0.7 * r), 5).tolist(),
                    'yaw': round(math.atan2(-math.sin(th) / SE, math.cos(th)), 4), 'r': round(r, 5),
                    'length': round(float(np.clip(rw / K * 0.95, 0.007, 0.013)), 5), 'pale': bool(pale)})
    return out, [it[:5] for it in items]


# ------------------------------------------------------------------ the sheet

def tracing_sheet(path, rgba, pieces, fits, wedge, scal_items):
    """The art with what was traced drawn on it (勾勒): each piece of egg outlined in blue, the wedges in red, the
    scallion in green; beside it the pieces alone, as a colouring page."""
    a = rgba[..., 3:4].astype(np.float32) / 255
    rgb = (rgba[..., :3] * a + np.array((244, 237, 222)) * (1 - a)).astype(np.uint8)   # on paper
    H, W = pieces.shape
    traced = (rgb * 0.75 + 255 * 0.25).astype(np.uint8)
    page = np.full((H, W, 3), 255, np.uint8)
    rng = np.random.default_rng(7)
    for pid in range(1, pieces.max() + 1):
        m = cv2.morphologyEx(u8(pieces == pid), cv2.MORPH_OPEN, disk(4)).astype(bool)   # as egg_surfaces has it
        if not m.any():
            continue
        page[m] = np.clip(np.array((250, 230, 150)) + rng.integers(-15, 15, 3), 0, 255)
        c, _ = cv2.findContours(u8(m), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(traced, c, -1, (30, 60, 190), 3)
        cv2.drawContours(page, c, -1, (150, 100, 40), 2)
    for i, p in enumerate(fits):
        sil = wedge.render(p, (0, 0, W, H), scale=1.0)[:H, :W] > 0
        c, _ = cv2.findContours(u8(sil), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(traced, c, -1, (200, 30, 30), 3)
        cv2.drawContours(page, c, -1, (230, 120, 110), 2)
    for cu, cv_, rw, rh, ang in scal_items:
        box = cv2.boxPoints(((cu, cv_), (rw, rh), ang)).astype(np.int32)
        cv2.polylines(traced, [box], True, (40, 150, 40), 3)
        cv2.polylines(page, [box], True, (110, 180, 110), 2)
    crop = (60, 210, 1200, 990)
    a = Image.fromarray(traced).crop(crop)
    b = Image.fromarray(page).crop(crop)
    font = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', 26)
    sheet = Image.new('RGB', (a.width * 2 + 30, a.height + 60), (244, 237, 222))
    d = ImageDraw.Draw(sheet)
    d.text((10, 12), '原图上的描线（蓝：鸡蛋，红：番茄，绿：葱）', fill=(96, 62, 40), font=font)
    d.text((a.width + 40, 12), f'描出的 {pieces.max()} 块松散鸡蛋', fill=(96, 62, 40), font=font)
    sheet.paste(a, (10, 55))
    sheet.paste(b, (a.width + 20, 55))
    sheet.save(path)


# ------------------------------------------------------------------ all together

def main():
    blender = sys.argv[sys.argv.index('--blender') + 1] if '--blender' in sys.argv else 'E:/blender.exe'
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    H, W = alpha.shape
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    lab, hsv = classify(rgb, alpha)
    print('[trace] classified', flush=True)
    wedge = Wedge(blender)
    # a first heap from the egg, the red and the scallion, for fitting the wedges onto; then the heap proper
    T0, _ = heap(footprint(lab == 1, cv2.morphologyEx(u8(lab == 2), cv2.MORPH_OPEN, disk(10)).astype(bool), lab == 3))
    fits = fit_wedges(wedge, rgb, lab, hsv, T0)
    sil = np.zeros((H, W), bool)
    for i, p in enumerate(fits):
        uv, s, ids = wedge.tris(on_ray(p[0], p[1], 0.0), wedge.linear(p), i)
        sil |= raster(uv, s, ids, H, W)[1] >= 0
    egg = egg_mask(lab, sil)
    T, outline = heap(footprint(egg, sil, lab == 3))
    print(f'[trace] heap: top {T.max():.4f} m', flush=True)
    wz, wid = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)   # the wedges' depth in the art's view
    wedges = []
    for i, p in enumerate(fits):
        C, Lm = wedge.place(p, T)
        M = np.eye(4)
        M[:3, :3], M[:3, 3] = Lm, C
        wedges.append(np.round(M, 6).tolist())
        uv, s, ids = wedge.tris(C, Lm, i)
        raster(uv, s, ids, H, W, wz, wid)
    pieces = split_egg(egg, lum)
    surfaces = egg_surfaces(pieces, sil, lab, lum, T, wz)
    print(f'[trace] egg: {len(surfaces)} pieces, {sum(len(p["tris"]) for p in surfaces)} triangles', flush=True)
    zb, zid = wz.copy(), wid.copy()   # and of everything, for laying the scallion on top
    for p in surfaces:
        P = np.array(p['verts'])
        tr = np.array(p['tris'])
        raster(p['uv'][tr], depth_of(P)[tr], np.zeros(len(tr), int), H, W, zb, zid)
    scal, scal_items = scallions(lab, T, zb)
    data = {'camera': {'el': EL, 'k': K, 'u0': U0, 'v0': V0}, 'wedges': wedges,
            'egg': [{'verts': p['verts'], 'tris': p['tris']} for p in surfaces], 'filler': filler(outline, T),
            'scallions': scal}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT}: {len(wedges)} wedges, {len(scal)} scallions', flush=True)
    if sheet:
        tracing_sheet(sheet, rgba, pieces, fits, wedge, scal_items)
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
