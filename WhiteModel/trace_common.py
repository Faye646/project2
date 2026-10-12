"""Shared tools for tracing a dish's art into its model (勾勒), used by trace_d10.py and trace_d18.py (trace_d06.py and
trace_d23.py came first and carry their own): the art's camera, the dish's surface under the food, cutting the art
into pieces, their colours, and each piece as a surface over its outline in the art, so that from the art's camera
it covers exactly what the art paints, its 3D shape a rounded mound (lying) or a rounded lens (standing).
"""
import heapq
import json
import math
import os
import subprocess
import tempfile

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
u8 = lambda m: m.astype(np.uint8)
disk = lambda r: cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * r + 1, 2 * r + 1))


def fill_holes(m):
    m = u8(m)
    ff = m.copy()
    cv2.floodFill(ff, np.zeros((m.shape[0] + 2, m.shape[1] + 2), np.uint8), (0, 0), 1)
    return (m | (1 - ff)).astype(bool)


def largest(m):
    n, cc, st, _ = cv2.connectedComponentsWithStats(u8(m))
    return cc == 1 + np.argmax(st[1:, cv2.CC_STAT_AREA]) if n > 1 else m.astype(bool)


class Camera:
    """The art as an orthographic view from straight in front, `el` degrees up, k px a metre, the world's origin
    at the art pixel (u0, v0): X = u0 + k·x, Y = v0 - k·(y·sin el + z·cos el)."""

    def __init__(self, el, k, u0, v0):
        self.el, self.k, self.u0, self.v0 = el, k, u0, v0
        self.se, self.ce = math.sin(math.radians(el)), math.cos(math.radians(el))
        self.toward = np.array([0.0, -self.ce, self.se])        # from the food towards the camera
        self.away = -self.toward

    def project(self, x, y, z):
        return (self.u0 + self.k * np.asarray(x),
                self.v0 - self.k * (np.asarray(y) * self.se + np.asarray(z) * self.ce))

    def on_ray(self, u, v, s):
        """The world points seen at art pixels (u, v), s along the view (larger further from the camera)."""
        u, v, s = np.broadcast_arrays(np.asarray(u, float), np.asarray(v, float), np.asarray(s, float))
        x, q = (u - self.u0) / self.k, (self.v0 - v) / self.k
        return np.stack([x, q * self.se + s * self.ce, q * self.ce - s * self.se], -1)

    def depth(self, P):
        P = np.asarray(P)
        return P[..., 1] * self.ce - P[..., 2] * self.se

    def plane_depth(self, u, v, anchor, normal):
        """How far along the view the rays through (u, v) meet the plane through anchor with the given normal."""
        P0 = self.on_ray(u, v, 0.0)
        return ((np.asarray(anchor) - P0) @ np.asarray(normal)) / (self.away @ np.asarray(normal))

    def backproject(self, u, v, height, lift=0.0, y0=-0.2, y1=0.2, steps=400):
        """Where the rays through (u, v) first meet z = height(x, y) + lift, coming from the camera: x, y, z."""
        u, v = np.asarray(u, float), np.asarray(v, float)
        lift = np.broadcast_to(np.asarray(lift, float), u.shape)
        x, q = (u - self.u0) / self.k, (self.v0 - v) / self.k
        se, ce = self.se, self.ce
        prev_y = np.full(u.shape, y0)
        prev_d = (q - y0 * se) / ce - height(x, prev_y) - lift
        found = np.zeros(u.shape, bool)
        lo, hi = np.full(u.shape, y0), np.full(u.shape, y1)
        for yy in np.linspace(y0, y1, steps)[1:]:
            yv = np.full(u.shape, yy)
            d = (q - yy * se) / ce - height(x, yv) - lift
            hit = (~found) & (prev_d > 0) & (d <= 0)
            lo[hit], hi[hit] = prev_y[hit], yy
            found |= hit
            prev_y, prev_d = yv, d
        for _ in range(30):
            mid = (lo + hi) / 2
            above = (q - mid * se) / ce - height(x, mid) - lift > 0
            lo, hi = np.where(above, mid, lo), np.where(above, hi, mid)
        y = (lo + hi) / 2
        return x, y, (q - y * se) / ce


class Grid:
    """Heights over a world grid (x, y), step metres apart, sampled bilinearly."""

    def __init__(self, z, x0, y0, step):
        self.z, self.x0, self.y0, self.step = z, x0, y0, step

    def __call__(self, x, y):
        n_y, n_x = self.z.shape
        fx = np.clip((np.asarray(x) - self.x0) / self.step, 0, n_x - 1.001)
        fy = np.clip((np.asarray(y) - self.y0) / self.step, 0, n_y - 1.001)
        ix, iy = np.floor(fx).astype(int), np.floor(fy).astype(int)
        tx, ty = fx - ix, fy - iy
        g = self.z
        return ((g[iy, ix] * (1 - tx) + g[iy, ix + 1] * tx) * (1 - ty)
                + (g[iy + 1, ix] * (1 - tx) + g[iy + 1, ix + 1] * tx) * ty)

    def xy(self):
        n_y, n_x = self.z.shape
        return np.meshgrid(self.x0 + np.arange(n_x) * self.step, self.y0 + np.arange(n_y) * self.step)

    @staticmethod
    def top_of(V, T, step=0.001, pad=0.01):
        """The topmost surface of the triangles (V, T) seen from above: a dish's inside where food lies on it."""
        V = np.asarray(V)
        lo, hi = V[:, :2].min(0) - pad, V[:, :2].max(0) + pad
        n_x, n_y = int((hi[0] - lo[0]) / step) + 2, int((hi[1] - lo[1]) / step) + 2
        z = np.full((n_y, n_x), -1.0, np.float32)
        S = 8   # sub-pixel bits for fillConvexPoly
        for t in np.asarray(T):
            P = V[t]
            px = (P[:, 0] - lo[0]) / step
            py = (P[:, 1] - lo[1]) / step
            x0, x1 = max(int(px.min()), 0), min(int(px.max()) + 2, n_x)
            y0, y1 = max(int(py.min()), 0), min(int(py.max()) + 2, n_y)
            if x1 <= x0 or y1 <= y0:
                continue
            m = np.zeros((y1 - y0, x1 - x0), np.uint8)
            cv2.fillConvexPoly(m, np.round(np.stack([px - x0, py - y0], -1) * (1 << S)).astype(np.int32), 1, shift=S)
            if not m.any():
                continue
            yy, xx = np.nonzero(m)
            # the plane of the triangle at the cells' centres
            a, b, c = P
            n = np.cross(b - a, c - a)
            if abs(n[2]) < 1e-12:
                continue
            wx, wy = lo[0] + (xx + x0) * step, lo[1] + (yy + y0) * step
            zz = np.clip(a[2] - (n[0] * (wx - a[0]) + n[1] * (wy - a[1])) / n[2], P[:, 2].min(), P[:, 2].max())
            cur = z[yy + y0, xx + x0]
            z[yy + y0, xx + x0] = np.maximum(cur, zz)
        hole = z < -0.5   # cells no triangle covers: the nearest covered height
        if hole.any() and (~hole).any():
            idx = cv2.distanceTransformWithLabels(u8(hole), cv2.DIST_L2, 5, labelType=cv2.DIST_LABEL_PIXEL)[1]
            src = np.zeros(idx.max() + 1, np.float32)
            src[idx[~hole]] = z[~hole]
            z = np.where(hole, src[idx], z)
        return Grid(z.astype(np.float64), lo[0], lo[1], step)


def dish_mesh(build, blender='E:/blender.exe'):
    """The dish the food lies on (its plate or bowl and its sauce), built by Blender from `build`: python making the
    Part `p` with food_models' helpers. Its vertices and triangles."""
    fd, path = tempfile.mkstemp(prefix='trace_dish_', suffix='.json')   # its own file: traces may run side by side
    os.close(fd)
    script = '\n'.join([
        'import sys, json, bmesh',
        'sys.path.insert(0, %r)' % HERE,
        'from food_models.core import *',
        'from food_models.plates import *',
        'p = Part()',
        build,
        'bm = p.bm',
        'bmesh.ops.triangulate(bm, faces=bm.faces[:])',
        'bm.verts.index_update()',
        "json.dump({'V': [list(v.co) for v in bm.verts], 'T': [[v.index for v in f.verts] for f in bm.faces]},"
        ' open(%r, "w"))' % path])
    subprocess.run([blender, '-b', '--factory-startup', '--python-expr', script], check=True,
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    with open(path) as fh:
        d = json.load(fh)
    os.remove(path)
    return np.array(d['V']), np.array(d['T'])


# ------------------------------------------------------------------ cutting the art into pieces

def flood(markers, elev):
    """A priority flood from the markers (> 0) over the elevation, lowest first: each pixel takes the label of the
    neighbour it is reached from. Pixels outside every region keep 0 where markers are -1."""
    H, W = markers.shape
    lab = markers.copy()
    ys, xs = np.nonzero(lab > 0)
    hq = [(float(elev[y, x]), int(y), int(x)) for y, x in zip(ys, xs)]
    heapq.heapify(hq)
    while hq:
        e, y, x = heapq.heappop(hq)
        l = lab[y, x]
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            yy, xx = y + dy, x + dx
            if 0 <= yy < H and 0 <= xx < W and lab[yy, xx] == 0:
                lab[yy, xx] = l
                heapq.heappush(hq, (max(float(elev[yy, xx]), e), yy, xx))
    return lab


def seeded_pieces(rgb, zone, strokes, background, remove=None, ink=(0.45, 0.35), widths=(7, 9)):
    """A flood of the art seeded by `strokes` {piece number: [art pixels]} inside each piece and `background`
    [lines of art pixels] outside them, lowest ground first: the ground is the change of colour, and the art's ink
    lines (value under ink[0] and saturation over ink[1]) stand high as walls, crossed last, so that each piece's
    outline follows the line the art draws round it; what lies on top (`remove`, a mask) is painted out first.
    Returns the piece numbers per pixel (0 outside them)."""
    H, W = zone.shape
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    s, v = hsv[..., 1] / 255, hsv[..., 2] / 255
    img = rgb.copy()
    gone = np.zeros((H, W), bool) if remove is None else cv2.dilate(u8(remove), disk(3)).astype(bool)
    if gone.any():
        img = cv2.inpaint(rgb, u8(gone), 6, cv2.INPAINT_TELEA)
    lab_ = cv2.cvtColor(cv2.GaussianBlur(img, (0, 0), 1.0), cv2.COLOR_RGB2LAB).astype(np.float32)
    grad = sum(np.abs(cv2.Sobel(lab_[..., c], cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(lab_[..., c], cv2.CV_32F, 0, 1))
               for c in range(3))
    wall = (v < ink[0]) & (s > ink[1]) & ~gone
    elev = grad + 2000.0 * cv2.GaussianBlur(wall.astype(np.float32), (0, 0), 1.5)
    mk = Image.new('I', (W, H), 0)
    d = ImageDraw.Draw(mk)
    for line in background:
        d.line(line, fill=1, width=widths[1])
    for pid, line in strokes.items():
        d.line(line, fill=pid + 1, width=widths[0])
        for x, y in line:
            d.ellipse((x - 5, y - 5, x + 5, y + 5), fill=pid + 1)
    markers = np.asarray(mk, np.int32).copy()
    markers[~zone] = 1
    if remove is not None:
        markers[remove & (markers > 1)] = 0
    lab = flood(markers, elev)
    lab[~zone] = 1
    return np.where(lab > 1, lab - 1, 0)


def split(mask, lum, sig=3.0, tau=20.0, amin=1500, amax=20000, marker_r=6):
    """A region cut into its pieces along the art's creases: a watershed on its shading (creases and edges high
    ground) from the bright middles of the pieces, then neighbours with only a faint crease between them merged and
    small bits into the neighbour they share most edge with. Returns piece numbers (0 outside)."""
    H, W = mask.shape
    m = mask.astype(np.float32)
    lb = cv2.GaussianBlur(lum * m, (0, 0), sig) / np.maximum(cv2.GaussianBlur(m, (0, 0), sig), 1e-3)
    dist = cv2.distanceTransform(u8(mask), cv2.DIST_L2, 5)
    elev = -(lb + np.minimum(dist, 12))
    elev[~mask] = 1e9
    mark = mask & (elev <= cv2.erode(elev.astype(np.float32), disk(marker_r)) + 1e-3) & (dist > 3)
    n, mlab = cv2.connectedComponents(u8(mark))
    lab = np.zeros((H, W), np.int32)
    lab[mark] = mlab[mark]
    hq = [(float(elev[y, x]), int(y), int(x)) for y, x in zip(*np.nonzero(mark))]
    heapq.heapify(hq)
    while hq:
        e, y, x = heapq.heappop(hq)
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            yy, xx = y + dy, x + dx
            if 0 <= yy < H and 0 <= xx < W and mask[yy, xx] and lab[yy, xx] == 0:
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


def grow(labels, mask, lum, sig=2.0):
    """Pieces (labels > 0) grown over the whole of mask, the art's brightest first and its darkest creases last, so
    that they pack it as the art paints them, each two meeting along the crease between them."""
    m = mask.astype(np.float32)
    lb = cv2.GaussianBlur(lum * m, (0, 0), sig) / np.maximum(cv2.GaussianBlur(m, (0, 0), sig), 1e-3)
    mk = np.where(mask, 0, -1).astype(np.int32)
    mk[(labels > 0) & mask] = labels[(labels > 0) & mask]
    lab = flood(mk, -lb)
    return np.where(mask & (lab > 0), lab, 0)


def posterize(rgb, mask, palette, passes=(6, 6, 5, 4), speck=1200):
    """The art within mask simplified to the nearest of the palette's colours (in Lab, after a little blur), each
    region smoothed by majority votes and specks under `speck` pixels given to their surroundings: clean shapes of
    flat colour, as the art's colours would be blocked in. Returns the palette index per pixel (-1 outside)."""
    n = len(palette)
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 2.5), cv2.COLOR_RGB2LAB).astype(np.float32)
    P = cv2.cvtColor(np.array([list(palette)], np.uint8), cv2.COLOR_RGB2LAB)[0].astype(np.float32)
    cl = np.argmin(((lab[..., None, :] - P[None, None]) ** 2).sum(-1), -1)
    cl[~mask] = -1
    for r in passes:
        votes = np.stack([cv2.boxFilter((cl == k).astype(np.float32), -1, (2 * r + 1, 2 * r + 1)) for k in range(n)],
                         -1)
        cl = np.where(mask, np.argmax(votes, -1), -1)
    for k in range(n):
        cc_n, cc, st, _ = cv2.connectedComponentsWithStats(u8(cl == k))
        small = np.zeros(cc_n, bool)
        small[1:] = st[1:, cv2.CC_STAT_AREA] < speck
        m = small[cc]
        if m.any():
            votes = np.stack([cv2.boxFilter(((cl == j) & ~m).astype(np.float32), -1, (25, 25)) for j in range(n)], -1)
            cl[m] = np.argmax(votes, -1)[m]
    return cl


def paint_channels(masks, food, smooth=3.5, min_area=200, close=4):
    """Colour classes (masks) as smoothed channels over the food, for meat_fish.paint: specks dropped, gaps closed,
    the edges softened, so that a colour's edge on the model runs smooth where the art's does. uint8 H×W×C."""
    out = np.zeros(food.shape + (len(masks),), np.uint8)
    for c, m in enumerate(masks):
        m = cv2.morphologyEx(u8(m & food), cv2.MORPH_OPEN, disk(1))
        n, cc, st, _ = cv2.connectedComponentsWithStats(m)
        keep = np.zeros(n, bool)
        keep[1:] = st[1:, cv2.CC_STAT_AREA] >= min_area
        m = cv2.morphologyEx(u8(keep[cc]), cv2.MORPH_CLOSE, disk(close)) if close else u8(keep[cc])
        f = cv2.GaussianBlur(m.astype(np.float32), (0, 0), smooth)
        out[..., c] = np.clip(f * 255 + 0.5, 0, 255).astype(np.uint8)
    return out


def blobs(mask, min_area=80, max_area=5000):
    """Small things lying on the food (scallion, garlic): each one's middle, length, width and angle (art pixels)."""
    n, cc, st, _ = cv2.connectedComponentsWithStats(u8(mask))
    out = []
    for j in range(1, n):
        if min_area <= st[j, cv2.CC_STAT_AREA] <= max_area:
            (cu, cv_), (rw, rh), ang = cv2.minAreaRect(np.stack(np.nonzero(cc == j)[::-1], -1).astype(np.float32))
            if rw < rh:
                rw, rh, ang = rh, rw, ang + 90
            out.append((float(cu), float(cv_), float(rw), float(rh), float(ang)))
    return out


# ------------------------------------------------------------------ the pieces' surfaces

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


def contour_points(masks, spacing):
    """Points every `spacing` pixels along the edges of the masks (art pixels): where a colour's edge runs, for the
    mesh to have its vertices there, so that the colour can be painted on crisply."""
    out = []
    for m in masks:
        cs, _ = cv2.findContours(u8(m), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        for c in cs:
            c = c[:, 0, :].astype(float)
            if len(c) < 8:
                continue
            seg = np.r_[0, np.cumsum(np.hypot(*np.diff(np.r_[c, c[:1]], axis=0).T))]
            if seg[-1] < 2 * spacing:
                continue
            tt = np.arange(0, seg[-1], spacing)
            out += list(np.stack([np.interp(tt, seg, np.r_[c[:, i], c[:1, i]]) for i in range(2)], -1))
    return np.array(out).reshape(-1, 2)


def outline_mesh(cam, mask, gap, gb, ring, smooth_px=5.0, extra=None, extra_margin=None):
    """A mesh over a piece's outline in the art: the outline smoothed and resampled `gb` metres apart, a ring of
    vertices `ring` inside it (so that the dive at its edge stays a thin line), a hexagonal grid `gap` apart inside,
    triangulated, with `extra` points (art pixels: contour_points) inside it in place of the grid's near them, those
    at least `extra_margin` art pixels in from the outline (default 0.6 gb; less for a colour along the edge).
    Works in (u, w), w = v / sin(el), where distances are world-proportional on level ground.
    Returns the points (u, v) in art pixels, the triangles, how many points are the outline, and each point's
    distance in from the outline (metres, as on level ground) and the piece's half-width R."""
    H, W = mask.shape
    se, K = cam.se, cam.k
    mk = u8(mask)
    x0, y0, w0, h0 = cv2.boundingRect(mk)
    x0, y0 = max(x0 - 8, 0), max(y0 - 8, 0)
    x1, y1 = min(x0 + w0 + 16, W), min(y0 + h0 + 16, H)
    sub = mk[y0:y1, x0:x1]
    cnt, _ = cv2.findContours(sub, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    c = max(cnt, key=len)[:, 0, :].astype(float)
    c[:, 1] /= se
    r = int(3 * smooth_px)
    kk = np.exp(-0.5 * (np.arange(-r, r + 1) / smooth_px) ** 2)
    kk /= kk.sum()
    c = np.stack([np.convolve(np.r_[c[-r:, i], c[:, i], c[:r, i]], kk, 'valid') for i in range(2)], -1)
    seg = np.r_[0, np.cumsum(np.hypot(*np.diff(np.r_[c, c[:1]], axis=0).T))]
    tt = np.linspace(0, seg[-1], max(8, int(seg[-1] / (gb * K))), endpoint=False)
    bpts = np.stack([np.interp(tt, seg, np.r_[c[:, i], c[:1, i]]) for i in range(2)], -1)
    hs = int(round((y1 - y0) / se))
    sm = np.zeros((hs, x1 - x0), np.uint8)
    cv2.fillPoly(sm, [np.round(bpts * 16).astype(np.int32)], 1, shift=4)
    dst = cv2.distanceTransform(sm, cv2.DIST_L2, 5) / K
    poly = bpts.astype(np.float32).reshape(-1, 1, 2)
    tang = np.roll(bpts, -1, 0) - np.roll(bpts, 1, 0)
    nrm = np.stack([tang[:, 1], -tang[:, 0]], -1) / np.maximum(np.hypot(*tang.T), 1e-9)[:, None]
    probe = bpts[0] - nrm[0] * ring * K
    if cv2.pointPolygonTest(poly, (float(probe[0]), float(probe[1])), False) < 0:
        nrm = -nrm
    rg = np.concatenate([[q for q in bpts - nrm * r * K   # one ring or more (a tuple): an ink line's two edges
                          if cv2.pointPolygonTest(poly, (float(q[0]), float(q[1])), True) > 0.7 * r * K]
                         for r in (ring if isinstance(ring, (tuple, list)) else (ring,))]).reshape(-1, 2)
    G = gap * K
    grid = [(uu, wv) for k_, wv in enumerate(np.arange(0, hs, G * 0.866))
            for uu in np.arange((k_ % 2) * G / 2, x1 - x0, G)
            if int(round(uu)) < sm.shape[1] and dst[min(int(round(wv)), hs - 1), int(round(uu))] > 0.6 * gap]
    grid = np.array(grid).reshape(-1, 2)
    if extra is not None and len(extra):
        ex = np.asarray(extra, float) - np.array([x0, y0])
        ex[:, 1] /= se
        margin = 0.6 * gb * K if extra_margin is None else extra_margin
        keep = [cv2.pointPolygonTest(poly, (float(q[0]), float(q[1])), True) > margin for q in ex]
        ex = ex[np.array(keep, bool)]
        if len(ex):
            near = cv2.dilate(u8(np.zeros_like(sm)), disk(1))   # the grid points near an extra point give way
            ix = np.clip(np.round(ex[:, 0]).astype(int), 0, sm.shape[1] - 1)
            iw_ = np.clip(np.round(ex[:, 1]).astype(int), 0, hs - 1)
            near[iw_, ix] = 1
            near = cv2.dilate(near, disk(max(1, int(0.55 * G)))).astype(bool)
            gi = np.clip(np.round(grid[:, 0]).astype(int), 0, sm.shape[1] - 1)
            gw = np.clip(np.round(grid[:, 1]).astype(int), 0, hs - 1)
            grid = np.r_[grid[~near[gw, gi]], ex]
    pts = np.r_[bpts, rg.reshape(-1, 2), grid]
    pts = pts.astype(np.float32).astype(np.float64)   # as Subdiv2D keeps them, so that its triangles find their points
    _, first = np.unique(np.round(pts, 3), axis=0, return_index=True)
    pts = pts[np.sort(first)]                          # no point twice
    nb = len(bpts)
    sd = cv2.Subdiv2D((-50, -50, int(x1 - x0 + 100), int(hs + 100)))
    idx = {}
    for k_, p in enumerate(pts):
        idx[(round(float(p[0]), 3), round(float(p[1]), 3))] = k_
        sd.insert((float(p[0]), float(p[1])))
    def find(p):   # our point at a corner Subdiv2D gives back: by its key, else the nearest (it rounds differently)
        k_ = idx.get((round(float(p[0]), 3), round(float(p[1]), 3)))
        if k_ is None:
            dd = (pts[:, 0] - p[0]) ** 2 + (pts[:, 1] - p[1]) ** 2
            k_ = int(np.argmin(dd)) if dd.min() < 0.05 ** 2 else None
        return k_
    tris = []
    for t in sd.getTriangleList():
        a, b, c3 = (t[0], t[1]), (t[2], t[3]), (t[4], t[5])
        ia, ib, ic = (find(p) for p in (a, b, c3))
        if ia is None or ib is None or ic is None:   # a corner of Subdiv2D's own outer triangle
            continue
        if cv2.pointPolygonTest(poly, ((a[0] + b[0] + c3[0]) / 3, (a[1] + b[1] + c3[1]) / 3), False) >= 0 and \
                all(cv2.pointPolygonTest(poly, ((p[0] + q[0]) / 2, (p[1] + q[1]) / 2), True) >= -0.6
                    for p, q in ((a, b), (b, c3), (c3, a))):
            tris.append((ia, ib, ic))
    iw = np.clip(np.round(pts[:, 1]).astype(int), 0, hs - 1)
    iu = np.clip(np.round(pts[:, 0]).astype(int), 0, sm.shape[1] - 1)
    d = dst[iw, iu]
    d[:nb] = 0.0
    lean = np.zeros(len(pts))
    for k_ in range(len(pts)):   # 0 at its front edge (low in the art) .. 1 at its back
        col = sm[:, iu[k_]]
        r0 = r1 = iw[k_]
        while r0 > 0 and col[r0 - 1]:
            r0 -= 1
        while r1 < hs - 1 and col[r1 + 1]:
            r1 += 1
        lean[k_] = np.clip((r1 - pts[k_, 1]) / max(r1 - r0, 1.0), 0, 1)
    uv = np.stack([pts[:, 0] + x0, pts[:, 1] * se + y0], -1)
    return uv, np.array(tris).reshape(-1, 3), nb, d, float(dst.max()), lean


def profile(d, R, top, edge=0.0, tilt=0.0, lean=None, relief=0.0, band=None):
    """How far a piece's surface stands out over its base at each point d in from its outline: round across, a
    circle's arc as wide as the piece (narrow parts lower), from `edge` at the outline up to `top`, leaning to the
    eye by `tilt` (lower at its front edge), the art's shading `band` (-1..1) as relief."""
    dd = np.clip(d, 0, R)
    arc = np.sqrt(dd * (2 * R - dd)) / max(R, 1e-9)
    shape = arc * ((1 - tilt) + tilt * (lean ** 0.8 if lean is not None else 1.0))
    L = edge + (top - edge) * shape
    if band is not None and relief:
        L = L + relief * band * np.clip(d / max(0.3 * R, 1e-6), 0, 1)
    return L


def neighbours(n, tris):
    nbr = [set() for _ in range(n)]
    for a, b, c in tris:
        nbr[a] |= {b, c}
        nbr[b] |= {a, c}
        nbr[c] |= {a, b}
    return nbr


def smooth_inner(L, nb, nbr, passes=2):
    inner = [[j for j in s if j >= nb] for s in nbr]
    for _ in range(passes):
        avg = np.array([np.mean(L[j]) if j else L[k] for k, j in enumerate(inner)])
        L[nb:] = 0.5 * L[nb:] + 0.5 * avg[nb:]
    return L


def oriented(P, tris, toward, front=True):
    """The triangles wound so that their normals face the camera (front) or away from it."""
    out = []
    for a, b, c in tris:
        n = np.cross(P[b] - P[a], P[c] - P[a])
        ok = (n @ toward >= 0) == front
        out.append((a, b, c) if ok else (a, c, b))
    return out


def ear_clip(pts):
    """Triangles filling the simple polygon pts (2D, in order): ear clipping."""
    pts = np.asarray(pts, float)
    idx = list(range(len(pts)))
    area = 0.5 * np.sum(pts[:, 0] * np.roll(pts[:, 1], -1) - np.roll(pts[:, 0], -1) * pts[:, 1])
    if area < 0:
        idx.reverse()

    def cross(o, a, b):
        return (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    out, guard = [], 0
    while len(idx) > 3 and guard < 20 * len(pts):
        guard += 1
        n = len(idx)
        for k in range(n):
            i0, i1, i2 = idx[k - 1], idx[k], idx[(k + 1) % n]
            a, b, c = pts[i0], pts[i1], pts[i2]
            if cross(a, b, c) <= 1e-12:
                continue
            inside = False
            for j in idx:
                if j in (i0, i1, i2):
                    continue
                q = pts[j]
                if cross(a, b, q) >= 0 and cross(b, c, q) >= 0 and cross(c, a, q) >= 0:
                    inside = True
                    break
            if not inside:
                out.append((i0, i1, i2))
                idx.pop(k)
                break
        else:
            out.append((idx[-1], idx[0], idx[1]))   # nothing clips cleanly (a twist): cut one anyway
            idx.pop(0)
    if len(idx) == 3:
        out.append(tuple(idx))
    return out


def lying(cam, uv, tris, nb, L, base, close=None):
    """A piece lying on something: each point on its ray where it stands L over the surface z = base(x, y), so that
    the art's view sees it exactly where the art paints it. Given `close` (the surface under it, z = close(x, y)), it
    is closed underneath, hidden from the art's view: a skirt from its outline along the lines of sight down to that
    surface, and the outline there filled flat, so that from the side no gap shows under it. Returns points and
    triangles."""
    X, Y, Z = cam.backproject(uv[:, 0], uv[:, 1], base, lift=L)
    P = np.stack([X, Y, Z], -1)
    T = oriented(P, tris, cam.toward, True)
    if close is None:
        return P, T
    Xs, Ys, Zs = cam.backproject(uv[:nb, 0], uv[:nb, 1], close, lift=0.0005)
    k0 = len(P)
    P2 = np.r_[P, np.stack([Xs, Ys, Zs], -1)]
    xy = P[:nb, :2]   # the outline's turn seen from above: each edge's outside is to its right if it runs clockwise
    ccw = np.sum(xy[:, 0] * np.roll(xy[:, 1], -1) - np.roll(xy[:, 0], -1) * xy[:, 1]) > 0
    skirt = []
    for i in range(nb):
        j = (i + 1) % nb
        e = xy[j] - xy[i]
        outside = np.array([e[1], -e[0]]) if ccw else np.array([-e[1], e[0]])   # out from the outline, level
        for t in ((i, j, k0 + j), (i, k0 + j, k0 + i)):
            n = np.cross(P2[t[1]] - P2[t[0]], P2[t[2]] - P2[t[0]])
            skirt.append(t if n[:2] @ outside >= 0 else (t[0], t[2], t[1]))
    floor = []
    for a, b, c in ear_clip(P2[k0:, :2]):
        t = (k0 + a, k0 + b, k0 + c)
        n = np.cross(P2[t[1]] - P2[t[0]], P2[t[2]] - P2[t[0]])
        floor.append(t if n[2] <= 0 else (t[0], t[2], t[1]))   # facing down
    return P2, T + skirt + floor


def standing(cam, uv, tris, nb, L, Lb, anchor, normal=None, cone=False, back=None):
    """A piece standing up (a head, a fin, a tail): a rounded lens in the plane through anchor (normal to the line of
    sight unless given), its front L towards the camera and its back Lb away from it, front and back meeting at its
    outline, so that the art's view sees it exactly where the art paints it. With cone, its back is only a cone from
    its outline back to a point behind its middle (for pieces whose back is never seen: a few triangles); given
    back, a coarser mesh (its points and triangles, its first nb points the same outline), its back is that, Lb
    over it."""
    n = cam.toward if normal is None else np.asarray(normal)
    s0 = cam.plane_depth(uv[:, 0], uv[:, 1], anchor, n)
    P = cam.on_ray(uv[:, 0], uv[:, 1], s0 - L)
    if back is not None:
        ub, tb = back
        sb = cam.plane_depth(ub[nb:, 0], ub[nb:, 1], anchor, n)
        P2 = np.r_[P, cam.on_ray(ub[nb:, 0], ub[nb:, 1], sb + Lb[nb:])]
        m = lambda i: i if i < nb else i + len(P) - nb
        T2 = oriented(P2, [(m(a), m(b), m(c)) for a, b, c in tb], cam.toward, False)
        return P2, oriented(P, tris, cam.toward, True) + T2
    if cone:
        c = uv[nb:].mean(0) if len(uv) > nb else uv.mean(0)
        sc = cam.plane_depth(np.array([c[0]]), np.array([c[1]]), anchor, n)
        P2 = np.r_[P, cam.on_ray(np.array([c[0]]), np.array([c[1]]), sc + float(np.max(Lb)))]
        T2 = oriented(P2, [(i, (i + 1) % nb, len(P)) for i in range(nb)], cam.toward, False)
        return P2, oriented(P, tris, cam.toward, True) + T2
    Q = cam.on_ray(uv[nb:, 0], uv[nb:, 1], s0[nb:] + Lb[nb:])
    P2 = np.r_[P, Q]
    T = oriented(P, tris, cam.toward, True)
    m = lambda i: i if i < nb else i + len(P) - nb
    T2 = [(m(a), m(b), m(c)) for a, b, c in tris]
    T2 = oriented(P2, T2, cam.toward, False)
    return P2, T + T2


def above(cam, P, floor, front=None, gap=0.0006):
    """Points under the surface z = floor(x, y) + gap moved up onto it along their lines of sight (towards the
    camera), not straight up, so that the art's view still sees each where it was and nothing folds over. Given the
    number of a lens's front points (the first ones), its back's go a little lower, so as to stay behind them."""
    P = np.array(P, float)
    g = np.full(len(P), gap)
    if front is not None:
        g[front:] = gap * 0.4
    lo = P[:, 2] < floor(P[:, 0], P[:, 1]) + g
    if lo.any():
        u, v = cam.project(P[lo, 0], P[lo, 1], P[lo, 2])
        P[lo] = np.stack(cam.backproject(u, v, floor, lift=g[lo]), -1)
    return P


def before(cam, P, zdish, root, gap=0.002, reach=30):
    """A standing piece kept in front of the dish behind it (zdish: the dish's depths per art pixel): where the dish
    would come in front of it (a rim it crosses), the piece turns towards the camera about its root (an art pixel),
    as one, each point along its own line of sight, so that the art's view still sees it where it was. Each point
    keeps clear of the nearest the dish comes within `reach` art pixels of it (a rim's edge between its points)."""
    H, W = zdish.shape
    near = cv2.erode(np.where(np.isfinite(zdish), zdish, 1e3).astype(np.float32), disk(reach))
    u, v = cam.project(P[:, 0], P[:, 1], P[:, 2])
    s = cam.depth(P)
    sd = near[np.clip(np.round(v).astype(int), 0, H - 1), np.clip(np.round(u).astype(int), 0, W - 1)]
    sd = np.where(sd > 1e2, np.inf, sd)
    need = np.where(np.isfinite(sd), s - (sd - gap), 0.0)
    if need.max() <= 0:
        return P
    r = np.stack([u - root[0], v - root[1]], -1)
    d = (r * np.clip(need, 0, None)[:, None]).sum(0)
    d /= max(np.linalg.norm(d), 1e-9)
    t = r @ d                                   # how far out from the root, towards where it must come forward
    k = max(n / tt for n, tt in zip(need, t) if n > 0 and tt > 1e-6)
    return cam.on_ray(u, v, s - k * np.clip(t, 0, None))


def over(cam, uv, tris, L, zbuf, fallback):
    """A piece lying on what is already there in the art's view (zbuf: depths per art pixel), L towards the camera,
    or where nothing is, on fallback(u, v) (a depth)."""
    H, W = zbuf.shape
    iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
    ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
    s = zbuf[iy, ix]
    s = np.where(np.isfinite(s), s, fallback(uv[:, 0], uv[:, 1]))
    P = cam.on_ray(uv[:, 0], uv[:, 1], s - L)
    return P, oriented(P, tris, cam.toward, True)


def on_top(cam, zbuf, u, v, r=3):
    """The depth of the nearest surface at art pixel (u, v) (the least over a small window), or None."""
    H, W = zbuf.shape
    win = zbuf[max(int(v) - r, 0):min(int(v) + r + 1, H), max(int(u) - r, 0):min(int(u) + r + 1, W)]
    fin = np.isfinite(win)
    return float(np.min(win[fin])) if fin.any() else None


def shading_band(lum, mask, s1, s2, scale=22.0):
    """The art's shading within a mask as -1..1: its puffs and creases at the scale between s1 and s2 pixels."""
    m = mask.astype(np.float32)
    mb = lambda a, s: cv2.GaussianBlur(a * m, (0, 0), s) / np.maximum(cv2.GaussianBlur(m, (0, 0), s), 1e-3)
    return np.clip((mb(lum, s1) - mb(lum, s2)) / scale, -1, 1)


def tracing_sheet(path, rgba, pieces, names, tints, extra=(), crop=None, title=('', '')):
    """The art with what was traced drawn on it (勾勒), and beside it the pieces alone, as a colouring page."""
    a = rgba[..., 3:4].astype(np.float32) / 255
    rgb = (rgba[..., :3] * a + np.array((244, 237, 222)) * (1 - a)).astype(np.uint8)
    H, W = pieces.shape
    traced = (rgb * 0.75 + 255 * 0.25).astype(np.uint8)
    page = np.full((H, W, 3), 255, np.uint8)
    for pid in range(1, pieces.max() + 1):
        m = pieces == pid
        if not m.any():
            continue
        page[m] = tints[pid - 1]
        c, _ = cv2.findContours(u8(m), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(traced, c, -1, (30, 60, 190), 3)
        cv2.drawContours(page, c, -1, (150, 100, 40), 2)
    for cu, cv_, rw, rh, ang, col in extra:
        box = cv2.boxPoints(((cu, cv_), (rw, rh), ang)).astype(np.int32)
        cv2.polylines(traced, [box], True, col, 3)
        cv2.fillPoly(page, [box], col)
    crop = crop or (0, 0, W, H)
    A, B = Image.fromarray(traced).crop(crop), Image.fromarray(page).crop(crop)
    font = ImageFont.truetype('C:/Windows/Fonts/msyhbd.ttc', 26)
    sheet = Image.new('RGB', (A.width * 2 + 30, A.height + 60), (244, 237, 222))
    d = ImageDraw.Draw(sheet)
    d.text((10, 12), title[0], fill=(96, 62, 40), font=font)
    d.text((A.width + 40, 12), title[1], fill=(96, 62, 40), font=font)
    sheet.paste(A, (10, 55))
    sheet.paste(B, (A.width + 20, 55))
    sheet.save(path)
