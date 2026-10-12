"""Tools shared by the traces of produce.py's vegetables and seasonings (trace_greens.py, trace_perilla.py,
trace_radish.py, trace_potato.py, trace_ginger.py, trace_scallion.py, trace_garlic.py): each item traced off its art
(勾勒) into pieces, every one a surface over its outline in the art, so that from the art's camera it covers exactly
what the art paints, coloured as the art paints it.

- The camera: the art is an orthographic view from in front, 35° up, k px a metre, the model's origin on the table at
  the art pixel (u0, v0) (trace_common.Camera). Every art pixel is a ray; a point is placed by how far along its ray
  it lies (its depth, s: larger further from the camera).
- The pieces: a flood of the art from strokes inside each one (cut), the art's ink lines and any edges given standing
  high as walls, so that each piece's outline follows the line the art draws round it. Each piece has a level: those
  lower lie behind those higher, which is how the art overlaps them.
- Solids (lens): a rounded lens facing the camera, its front and its back meeting at its outline, as thick as it is
  wide (inflated off its outline: a Poisson dome, so that a disc comes out a ball and nothing has a ridge), set down
  on the table, or as near the camera as it needs to be to lie in front of what is behind it. A solid partly hidden
  is completed under what covers it (its outline carried on as an ellipse), so that it is whole from every side.
- Shells: leaves and stalks lying over a solid (the head of greens, the bunch of perilla): over its surface, higher
  for every level, rounded up from their own margins, which rest on whatever is under them (no gap under an edge,
  and the edge in front of what it lies on).
- Colours: every vertex the art's colour where it shows (the art with its ink lines and marks inpainted, blurred a
  little within the piece), the art's ink line along the piece's own margins (where it lies over something lower or
  over the paper: two rings of vertices just inside its outline), and the marks the art paints across it (veins,
  eyes, rings, streaks, lines) painted face by face on triangles laid along them (the mesh has vertices along both
  their edges). Each vertex carries its colour for produce.pv_traced (Part's 'Tint' layer, VTINT 1).
"""
import json
import math
import os

import cv2
import numpy as np
from PIL import Image, ImageDraw

from trace_common import (Camera, contour_points, disk, ear_clip, fill_holes, flood, largest, oriented, outline_mesh,
                          raster, tracing_sheet, u8)

HERE = os.path.dirname(os.path.abspath(__file__))
ART_DIR = os.path.join(HERE, '..', '新建文件夹')
MODELS = os.path.join(HERE, 'food_models')
EL = 35.0


def load(name):
    rgba = np.asarray(Image.open(os.path.join(ART_DIR, name)).convert('RGBA'))
    return rgba


def hsv_of(rgb):
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    return hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255


def lum_of(rgb):
    return rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)


def hexc(c):
    c = np.clip(np.round(np.asarray(c, float)), 0, 255).astype(int)
    return '#%02x%02x%02x' % tuple(c)


def masked_blur(img, mask, sigma):
    """img blurred within mask (each pixel the mask's weighted mean round it), and the mask's weight there."""
    m = mask.astype(np.float32)
    if img.ndim == 3:
        num = cv2.GaussianBlur(img.astype(np.float32) * m[..., None], (0, 0), sigma)
    else:
        num = cv2.GaussianBlur(img.astype(np.float32) * m, (0, 0), sigma)
    den = cv2.GaussianBlur(m, (0, 0), sigma)
    out = num / np.maximum(den, 1e-6)[..., None] if img.ndim == 3 else num / np.maximum(den, 1e-6)
    return out, den


def bilinear(img, u, v):
    """img sampled at art pixels (u, v) (pixel centres at +0.5)."""
    H, W = img.shape[:2]
    x = np.clip(np.asarray(u, float) - 0.5, 0, W - 1.001)
    y = np.clip(np.asarray(v, float) - 0.5, 0, H - 1.001)
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    tx, ty = x - x0, y - y0
    if img.ndim == 3:
        tx, ty = tx[:, None], ty[:, None]
    return ((img[y0, x0] * (1 - tx) + img[y0, x0 + 1] * tx) * (1 - ty)
            + (img[y0 + 1, x0] * (1 - tx) + img[y0 + 1, x0 + 1] * tx) * ty)


def ink_of(rgb, zone, vmax=0.5, smin=0.25, hues=(330.0, 50.0)):
    """The art's ink lines: dark, brown (hue past hues[0] or under hues[1])."""
    h, s, v = hsv_of(rgb)
    brown = (h > hues[0]) | (h < hues[1])
    return zone & (v < vmax) & (s > smin) & brown


def lines_of(rgb, mask, dark=True, radius=4, thresh=14.0, min_area=25, min_len=12, fill=0.55, chan=None):
    """Thin strokes the art paints (veins, rings, streaks): darker (or lighter) than round about within `radius` px
    by more than thresh (on luminance, or on the given channel), long ones, not blots."""
    lum = lum_of(rgb) if chan is None else chan.astype(np.float32)
    lum = cv2.GaussianBlur(lum, (0, 0), 0.8)
    th = cv2.morphologyEx(lum, cv2.MORPH_BLACKHAT if dark else cv2.MORPH_TOPHAT, disk(radius))
    m = u8(mask & (th > thresh))
    m = cv2.morphologyEx(m, cv2.MORPH_CLOSE, disk(1))
    n, cc, st, _ = cv2.connectedComponentsWithStats(m)
    keep = np.zeros(n, bool)
    w_, h_ = st[1:, cv2.CC_STAT_WIDTH], st[1:, cv2.CC_STAT_HEIGHT]
    keep[1:] = (st[1:, cv2.CC_STAT_AREA] >= min_area) & (np.hypot(w_, h_) >= min_len) & \
        (st[1:, cv2.CC_STAT_AREA] < fill * w_ * h_ + 40)
    return keep[cc]


def cut(rgb, zone, strokes, walls, wall_weight=2000.0, width=7):
    """Each art pixel's piece (1..n; 0 off the art): a flood from strokes {n: [polyline, ...]} over the art, lowest
    ground first, the ground the change of colour and `walls` (a mask: the ink lines, any edges given) standing high,
    crossed last."""
    H, W = zone.shape
    lab_ = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 1.0), cv2.COLOR_RGB2LAB).astype(np.float32)
    grad = sum(np.abs(cv2.Sobel(lab_[..., c], cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(lab_[..., c], cv2.CV_32F, 0, 1))
               for c in range(3))
    elev = grad + wall_weight * cv2.GaussianBlur(walls.astype(np.float32), (0, 0), 1.2)
    mk = Image.new('I', (W, H), 0)
    d = ImageDraw.Draw(mk)
    for pid, lines in strokes.items():
        for line in lines:
            line = [tuple(map(float, q)) for q in line]
            if len(line) > 1:
                d.line(line, fill=pid + 1, width=width)
            for x, y in line:
                d.ellipse((x - 3, y - 3, x + 3, y + 3), fill=pid + 1)
    markers = np.asarray(mk, np.int32).copy()
    markers[~zone] = 1
    lab = flood(markers, elev)
    lab[~zone] = 1
    return np.where(lab > 1, lab - 1, 0)


def settle(lab, walls, keep=()):
    """Every piece one region: of each label only its largest part stays; its other bits, and specks, go to the
    pieces round them (a flood, the walls crossed last). Labels in `keep` keep all their parts."""
    out = lab.copy()
    take = np.zeros(lab.shape, bool)
    for i in np.unique(lab):
        if i <= 0 or i in keep:
            continue
        m = u8(lab == i)
        n, cc, st, _ = cv2.connectedComponentsWithStats(m)
        if n > 2:
            big = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
            take |= (cc > 0) & (cc != big)
    if not take.any():
        return out
    mk = np.where(take, 0, -1).astype(np.int32)
    mk[(lab > 0) & ~take] = lab[(lab > 0) & ~take]
    got = flood(mk, cv2.GaussianBlur(walls.astype(np.float32), (0, 0), 1.0) * 100)
    return np.where(take & (got > 0), got, out)


def tidy(mask, open_r=2):
    """A piece's region without specks: opened, its largest part, its holes filled."""
    m = cv2.morphologyEx(u8(mask), cv2.MORPH_OPEN, disk(open_r)) if open_r else u8(mask)
    if not m.any():
        return m.astype(bool)
    return fill_holes(largest(m))


def inflate(mask, cells=180.0):
    """How far a piece swells off its outline: sqrt(4h), h solving Δh = -1 inside mask and 0 on its outline (art px),
    for a disc of radius R a hemisphere's height (R at its middle), round and without a ridge for any shape. Solved
    by red-black SOR on a grid about `cells` across the piece."""
    H, W = mask.shape
    x, y, w, h = cv2.boundingRect(u8(mask))
    pad = 4
    x0, y0, x1, y1 = max(x - pad, 0), max(y - pad, 0), min(x + w + pad, W), min(y + h + pad, H)
    sub = mask[y0:y1, x0:x1]
    sc = max(1.0, max(x1 - x0, y1 - y0) / cells)
    hs, ws = max(int(round((y1 - y0) / sc)), 6), max(int(round((x1 - x0) / sc)), 6)
    m = cv2.resize(sub.astype(np.float32), (ws, hs), interpolation=cv2.INTER_AREA) > 0.5
    m[0, :] = m[-1, :] = m[:, 0] = m[:, -1] = False
    d = cv2.distanceTransform(u8(m), cv2.DIST_L2, 5).astype(np.float64)
    R = max(d.max(), 1.0)
    T = d * (2 * R - d) / 4   # a disc's solution, to start from
    ii, jj = np.mgrid[0:hs, 0:ws]
    red, black = m & ((ii + jj) % 2 == 0), m & ((ii + jj) % 2 == 1)
    for _ in range(int(3 * max(hs, ws)) + 60):
        for msk in (red, black):
            nb = (np.roll(T, 1, 0) + np.roll(T, -1, 0) + np.roll(T, 1, 1) + np.roll(T, -1, 1) + 1.0) / 4
            T[msk] += 1.9 * (nb[msk] - T[msk])
    full = np.zeros((H, W), np.float32)
    up = cv2.resize(T.astype(np.float32), (x1 - x0, y1 - y0), interpolation=cv2.INTER_LINEAR) * sc * sc
    full[y0:y1, x0:x1] = np.sqrt(np.maximum(4 * up, 0.0))
    return full * mask


def hex_grid(mask, spacing, margin):
    """Points of a hexagonal grid `spacing` px apart inside mask, at least `margin` px in from its edge."""
    inner = cv2.distanceTransform(u8(mask), cv2.DIST_L2, 5) > margin
    H, W = mask.shape
    ys = np.arange(spacing * 0.3, H, spacing * 0.866)
    pts = []
    for k, y in enumerate(ys):
        xs = np.arange((k % 2) * spacing / 2, W, spacing)
        ok = inner[int(y), np.clip(xs.astype(int), 0, W - 1)]
        pts.append(np.stack([xs[ok], np.full(ok.sum(), y)], -1))
    return np.concatenate(pts) if pts else np.zeros((0, 2))


def thin_out(pts, keep, r):
    """pts without those within r px of any of `keep`."""
    if not len(pts) or not len(keep):
        return pts
    keep = np.asarray(keep, float)
    out = []
    for q in pts:
        if np.min(np.hypot(keep[:, 0] - q[0], keep[:, 1] - q[1])) >= r:
            out.append(q)
    return np.array(out).reshape(-1, 2)


def spaced(pts, r):
    """pts thinned so that none is within r px of another kept before it."""
    out = []
    for q in pts:
        if all((q[0] - o[0]) ** 2 + (q[1] - o[1]) ** 2 >= r * r for o in out[-400:]):
            out.append(q)
    return np.array(out).reshape(-1, 2)


def ellipse_completion(vis, own, covered, grow=1.0):
    """A piece partly hidden carried on under what covers it: the ellipse through its own outline (own: its edge
    pixels that are its own, not those along what lies over it), kept to where something does cover it."""
    ys, xs = np.nonzero(own)
    if len(xs) < 20:
        return vis
    (cx, cy), (a, b), ang = cv2.fitEllipse(np.stack([xs, ys], -1).astype(np.float32))
    el = np.zeros(vis.shape, np.uint8)
    cv2.ellipse(el, ((cx, cy), (a * grow, b * grow), ang), 1, -1)
    return fill_holes(vis | (el.astype(bool) & covered))


def thin(mask):
    """Zhang-Suen thinning: the mask worn down to lines one pixel wide along its middles."""
    img = u8(mask).copy()
    img = np.pad(img, 1)
    while True:
        changed = False
        for step in (0, 1):
            P = [img[1:-1, 1:-1], img[:-2, 1:-1], img[:-2, 2:], img[1:-1, 2:], img[2:, 2:], img[2:, 1:-1],
                 img[2:, :-2], img[1:-1, :-2], img[:-2, :-2]]   # p1, then p2..p9 clockwise from north
            B = sum(P[1:]).astype(int)
            seq = P[1:] + [P[1]]
            A = sum(((seq[i] == 0) & (seq[i + 1] == 1)).astype(int) for i in range(8))
            if step == 0:
                c = (P[1] * P[3] * P[5] == 0) & (P[3] * P[5] * P[7] == 0)
            else:
                c = (P[1] * P[3] * P[7] == 0) & (P[1] * P[5] * P[7] == 0)
            rm = (P[0] == 1) & (B >= 2) & (B <= 6) & (A == 1) & c
            if rm.any():
                img[1:-1, 1:-1][rm] = 0
                changed = True
        if not changed:
            return img[1:-1, 1:-1].astype(bool)


def skeleton_paths(mask, min_len=20.0, step=8.0):
    """The strokes of a mask (root hairs) as polylines along their middles: its skeleton walked from end to end
    and from fork to fork, each path resampled every `step` px, with the stroke's half-width there (px)."""
    sk = thin(mask)
    dt = cv2.distanceTransform(u8(mask), cv2.DIST_L2, 5)
    H, W = sk.shape
    nbrs = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]
    pts = set(zip(*np.nonzero(sk)))
    ring = [(-1, 0), (-1, 1), (0, 1), (1, 1), (1, 0), (1, -1), (0, -1), (-1, -1)]

    def crossings(q):   # 1 at an end, 2 along a line, 3 or more at a fork (not fooled by staircase corners)
        on = [(q[0] + dy, q[1] + dx) in pts for dy, dx in ring]
        return sum(1 for i in range(8) if on[i] and not on[(i + 1) % 8])
    nodes = {q for q in pts if crossings(q) != 2}
    seen = set()
    paths = []
    for start in nodes:
        for dy, dx in nbrs:
            q = (start[0] + dy, start[1] + dx)
            if q not in pts or (start, q) in seen:
                continue
            path, prev, cur = [start], start, q
            while True:
                seen.add((prev, cur))
                seen.add((cur, prev))
                path.append(cur)
                if cur in nodes:
                    break
                nxt = [(cur[0] + a, cur[1] + b) for a, b in nbrs if (cur[0] + a, cur[1] + b) in pts
                       and (cur[0] + a, cur[1] + b) != prev and ((cur, (cur[0] + a, cur[1] + b)) not in seen)]
                if not nxt:
                    break
                prev, cur = cur, nxt[0]
            arr = np.array([(x, y) for y, x in path], float)
            seg = np.r_[0, np.cumsum(np.hypot(*np.diff(arr, axis=0).T))]
            if seg[-1] < min_len:
                continue
            tt = np.linspace(0, seg[-1], max(2, int(round(seg[-1] / step)) + 1))
            xy = np.stack([np.interp(tt, seg, arr[:, 0]), np.interp(tt, seg, arr[:, 1])], -1)
            r = [float(dt[int(round(y)), int(round(x))]) for x, y in xy]
            paths.append([[round(float(x), 1), round(float(y), 1), round(rr, 2)] for (x, y), rr in zip(xy, r)])
    return paths


def join_paths(paths, reach=6.0, max_turn=0.9):
    """Skeleton paths (from skeleton_paths) joined end to end where one runs on into another (their ends within reach
    px, turning less than max_turn radians): whole hairs instead of the pieces between their crossings."""
    paths = [list(p) for p in paths]
    def ends(p):
        a, b = np.array(p[0][:2]), np.array(p[-1][:2])
        da = a - np.array(p[min(2, len(p) - 1)][:2])
        db = b - np.array(p[max(-3, -len(p))][:2])
        return (a, da / max(np.linalg.norm(da), 1e-6)), (b, db / max(np.linalg.norm(db), 1e-6))
    changed = True
    while changed:
        changed = False
        best = None
        for i in range(len(paths)):
            for j in range(len(paths)):
                if i == j:
                    continue
                (_, _), (bi, di) = ends(paths[i])          # the end of i ...
                (aj, dj), (_, _) = ends(paths[j])          # ... running on into the start of j
                gap = np.linalg.norm(bi - aj)
                turn = math.acos(float(np.clip(di @ -dj, -1, 1)))
                if gap <= reach and turn <= max_turn and (best is None or gap + 5 * turn < best[0]):
                    best = (gap + 5 * turn, i, j)
        if best:
            _, i, j = best
            paths[i] = paths[i] + paths[j][1:]
            del paths[j]
            changed = True
        else:   # try the other way round: a path reversed
            for i in range(len(paths)):
                for j in range(len(paths)):
                    if i != j:
                        (ai, _), (bi, _) = ends(paths[i])
                        (aj, _), (bj, _) = ends(paths[j])
                        if np.linalg.norm(bi - bj) <= reach or np.linalg.norm(ai - aj) <= reach:
                            q = paths[j][::-1]
                            if np.linalg.norm(bi - bj) <= reach:
                                cand = paths[i] + q[1:]
                            else:
                                cand = q + paths[i][1:]
                            paths[i] = cand
                            del paths[j]
                            changed = True
                            break
                if changed:
                    break
    return paths


class Item:
    """One item traced off its art: its pieces (masks over the art, levels), built back to front into surfaces."""

    def __init__(self, art, k, u0, v0, ink=None, w_tint=0.95):
        self.rgba = load(art)
        self.rgb = np.ascontiguousarray(self.rgba[..., :3])
        self.alpha = self.rgba[..., 3]
        self.zone = self.alpha > 128
        self.H, self.W = self.zone.shape
        self.cam = Camera(EL, k, u0, v0)
        self.mcam = Camera(90.0, k, u0, v0)   # meshes are spaced evenly in the art's pixels, not on the ground
        self.k = k
        self.ink = ink_of(self.rgb, self.zone) if ink is None else ink
        self.ink_hex = hexc(np.median(self.rgb[self.ink], 0)) if self.ink.any() else '#4a2b18'
        # how wide the art draws its ink line round the silhouette (px): twice the ridge of its distance map
        edge = self.zone & ~cv2.erode(u8(self.zone), disk(2)).astype(bool)
        band = self.ink & cv2.dilate(u8(edge), disk(14)).astype(bool)
        dt = cv2.distanceTransform(u8(band), cv2.DIST_L2, 5)
        ridge = band & (dt >= cv2.dilate(dt, np.ones((3, 3), np.uint8)) - 1e-3) & (dt > 0.9)
        self.ink_w = float(2 * np.median(dt[ridge]) - 1) if ridge.any() else 6.0
        print(f'[trace] ink line {self.ink_w:.1f} px, {self.ink_hex}', flush=True)
        self.zb = np.full((self.H, self.W), np.inf)
        self.zid = np.full((self.H, self.W), -1, np.int32)
        self.labels = np.zeros((self.H, self.W), np.int32)
        self.specs = []        # (name, kind, level, options)
        self.out = []
        self.built = {}
        self.w_tint = w_tint
        self.verbose = False
        self.remove = self.ink.copy()   # what the soft colours leave out (inpainted): ink lines, marks

    # ---------------------------------------------------------------- the pieces
    def add(self, name, mask, level, kind='lens', **opt):
        """A piece: its region in the art (what of it shows), its level (higher lies in front), how it is built."""
        pid = len(self.specs) + 1
        self.labels[mask & (self.labels == 0)] = pid
        self.specs.append(dict(name=name, kind=kind, level=level, pid=pid, _marks0=list(opt.pop('marks', [])), **opt))
        return pid

    def level_map(self):
        lv = np.full(len(self.specs) + 1, -1e9)
        for s in self.specs:
            lv[s['pid']] = s['level']
        return lv[self.labels]

    def regions(self, spec):
        """A piece's visible region, the pixels just outside it that are lower or paper (its own margins lie along
        them), and what covers its neighbourhood (higher pieces)."""
        vis = self.labels == spec['pid']
        lv = self.level_map()
        lower = (self.labels == 0) | ((lv < spec['level']) & (self.labels != spec['pid']))
        higher = (lv > spec['level']) & (self.labels > 0)
        own = vis & cv2.dilate(u8(lower), np.ones((3, 3), np.uint8)).astype(bool)
        return vis, own, higher

    # ---------------------------------------------------------------- colours
    def soft_colour(self, vis, sigma):
        """The art's colour over a piece, its ink lines and marks inpainted, blurred within it (filled from further
        round where it doesn't show)."""
        x, y, w, h = cv2.boundingRect(u8(cv2.dilate(u8(vis), disk(40))))
        sl = (slice(y, y + h), slice(x, x + w))
        clean, rem, m = self.rgb[sl], self.remove[sl] & vis[sl], vis[sl]
        a, da = masked_blur(clean, m & ~rem, sigma)
        b, db = masked_blur(clean, m & ~rem, 6 * sigma + 10)
        mean = clean[m & ~rem].mean(0) if (m & ~rem).any() else clean[m].mean(0)
        out = np.where((da > 0.25)[..., None], a, np.where((db > 0.02)[..., None], b, mean[None, None]))
        full = np.zeros((self.H, self.W, 3), np.float32)
        full[sl] = out
        return full

    # ---------------------------------------------------------------- building
    def mesh(self, mask, gap, gb, ring, smooth_px, extra, extra_margin=None):
        return outline_mesh(self.mcam, mask, gap / self.k, gb / self.k, ring, smooth_px, extra, extra_margin)

    def build(self, budget=None, extra_tris=0):
        """Builds the pieces back to front; given a budget (triangles, less extra_tris for what the builder adds), again
        with every spacing a little wider until they fit in it."""
        import copy
        base = copy.deepcopy([{k: v for k, v in sp.items() if k not in ('marks', '_marks0', 'edges', 'shape')}
                              for sp in self.specs])
        scale = 1.0
        while True:
            self.zb[:] = np.inf
            self.zid[:] = -1
            self.out, self.built = [], {}
            for sp, b in zip(self.specs, base):
                for key in ('gap', 'fine', 'gb', 'mark_px', 'edge_px', 'coarse'):
                    if key in b:
                        sp[key] = b[key] * scale
                sp['marks'] = list(sp['_marks0'])
            for spec in sorted(self.specs, key=lambda s: (s['level'], s['pid'])):
                if spec['kind'] == 'none':   # only there to take its pixels (what the builder makes itself)
                    continue
                if spec['kind'] == 'lens':
                    self.lens(spec)
                else:
                    self.shell(spec)
            total = sum(len(o['tris']) for o in self.out) + extra_tris
            if budget is None or total <= budget or scale > 2.0:
                print(f'[trace] spacing x{scale:.2f}: {total} triangles', flush=True)
                for o in self.out:
                    print(f"[trace]   {o['name']}: {len(o['tris'])}", end='', flush=True)
                print(flush=True)
                return self.out
            scale *= 1.0 + min(0.25, max(0.03, 0.5 * (total / budget - 1)))

    def _extras(self, spec, vis, region, gap):
        """The mesh's points inside: its marks' edges, and an even grid where it shows (if the region is larger)."""
        spec['marks'] = [(cv2.dilate(u8(m), disk(1)).astype(bool) & vis, how) for m, how in spec.get('marks', [])]
        marks = [m & region for m, _ in spec.get('marks', [])]
        mpts = contour_points([m for m in marks if m.any()], spec.get('mark_px', 9.0)) if marks else np.zeros((0, 2))
        epts = contour_points([m & region for m in spec.get('edges', []) if (m & region).any()],
                              spec.get('edge_px', 12.0)) if spec.get('edges') else np.zeros((0, 2))
        pts = [mpts, thin_out(epts, mpts, 0.5 * spec.get('mark_px', 9.0))]
        if spec.get('fine') and spec['fine'] < gap:
            g = hex_grid(vis, spec['fine'], 0.6 * spec['fine'])
            pts.append(thin_out(g, np.r_[mpts, epts], 0.55 * spec['fine']))
        return np.concatenate([q.reshape(-1, 2) for q in pts])

    def _inner_ink(self, spec, vis, own):
        """The art's ink lines inside a piece (a crease, a fold, a leaf's edge over itself), away from its own margins:
        painted on it as marks."""
        if not spec.get('inner_ink', True):
            return
        d_own = cv2.distanceTransform(u8(~own), cv2.DIST_L2, 5) if own.any() else np.full(vis.shape, 1e3, np.float32)
        m = self.ink & vis & (d_own > spec.get('inner_ink_gap', 7.0))
        m = cv2.morphologyEx(u8(m), cv2.MORPH_OPEN, disk(1)).astype(bool)
        n, cc, st, _ = cv2.connectedComponentsWithStats(u8(m))
        keep = np.zeros(n, bool)
        keep[1:] = st[1:, cv2.CC_STAT_AREA] >= spec.get('inner_ink_min', 30)
        m = keep[cc]
        if m.any():
            spec['marks'] = list(spec.get('marks', [])) + [(m, None)]

    def _ring(self, spec):
        """The rings of vertices inside its outline (m): given (mm), or round the art's own ink line (its inner edge
        and a little further in), so that the line comes out as wide and as crisp as the art draws it."""
        if 'ring' in spec:
            r = spec['ring']
            return tuple(x / 1000 for x in r) if isinstance(r, (tuple, list)) else r / 1000
        w = spec.get('ink_w', self.ink_w)
        if spec.get('one_ring'):   # cheaper: one ring at the ink line's inner edge
            return 0.9 * w / self.k
        return (0.75 * w / self.k, (w + 3.0) / self.k)

    def lens(self, spec):
        """A solid: a lens facing the camera over its outline (completed under what covers it)."""
        vis, own, higher = self.regions(spec)
        self._inner_ink(spec, vis, own)
        region = vis
        if spec.get('full') is not None:   # its whole outline given (under what lies over it too)
            region = spec['full'] | vis
        elif spec.get('complete') and higher.any():
            region = ellipse_completion(vis, own, higher, spec.get('grow', 1.0))
        over = spec.get('over', 2)
        if over:   # a little under the pieces over it, so that no crack shows between them
            region = region | (cv2.dilate(u8(vis), disk(over)).astype(bool) & higher)
        region = cv2.GaussianBlur(region.astype(np.float32), (0, 0), 1.0) > 0.5
        gap, gb = spec.get('gap', 22.0), spec.get('gb', 12.0)
        coarse = spec.get('coarse', gap)
        extra = self._extras(spec, vis, region, coarse)
        uv, tris, nb, d, R, _ = self.mesh(region, coarse, gb, self._ring(spec), spec.get('smooth', 2.0), extra,
                                          spec.get('extra_margin', 4.0))
        back_ring = (spec.get('ink_w', self.ink_w) + 2.0) / self.k if spec.get('back_ring') else 0.0   # a ring keeps
        if spec.get('back_same'):   # its back the front's own mesh: for hair-thin pieces, closed exactly
            ub, tb, nbb = uv, tris, nb
        else:
            ub, tb, nbb, _, _, _ = self.mesh(region, spec.get('back_gap', 60.0), gb, back_ring,   # it to a notched rim
                                             spec.get('smooth', 2.0), None)
        assert nbb == nb and np.allclose(ub[:nb], uv[:nb]), (spec['name'], nb, nbb)
        infl = inflate(region) / self.k                  # m
        R = max(float(infl.max()), 1e-6)
        rim = spec.get('rim', 0.5)   # 1: round to its rim (a ball's), 0: meeting the back at a slant (a paraboloid's)
        field = spec.get('puff', 0.7) * (rim * infl + (1 - rim) * infl * infl / R)   # its front's swell, per art px
        if spec.get('relief'):   # the art's shading as relief: lighter swells toward the eye, fading out toward the
            base_f = field         # rim (never sinking the front behind its back there)
            ramp = np.clip(infl / (0.3 * R), 0, 1)
            field = np.maximum(base_f + spec['relief'] * self.band(vis, spec)[1] * ramp, 0.6 * base_f)
        if spec.get('shape'):    # anything else the piece's form needs (facets, knobs)
            field = spec['shape'](field, region, vis)
        F = bilinear(field, uv[:, 0], uv[:, 1])
        F = np.maximum(F, spec.get('f_min', 0.0004))   # never so thin that its back shows through (narrow tips)
        F[:nb] = 0.0
        ib = bilinear(infl, ub[nb:, 0], ub[nb:, 1])
        B = np.maximum(spec.get('back', 0.7) * (rim * ib + (1 - rim) * ib * ib / R), spec.get('b_min', 0.0008))
        s0 = 0.0
        P = self.cam.on_ray(uv[:, 0], uv[:, 1], s0 - F)
        Q = self.cam.on_ray(ub[nb:, 0], ub[nb:, 1], s0 + B)
        allp = np.r_[P, Q]
        # set down on the table (its lowest point on it), then as far toward the camera as it must be to lie in
        # front of what is behind it where it shows (and in front of `before`, if given)
        t = -allp[:, 2].min() / self.cam.se if spec.get('settle', True) else 0.0
        if spec.get('lift') is not None:
            t += spec['lift'] / self.cam.se
        s_front = self.cam.depth(P) - t
        iy = np.clip(np.round(uv[:, 1]).astype(int), 0, self.H - 1)
        ix = np.clip(np.round(uv[:, 0]).astype(int), 0, self.W - 1)
        behind = cv2.erode(np.where(np.isfinite(self.zb), self.zb, 1e3).astype(np.float32), disk(3))[iy, ix]
        gap_s = spec.get('clear', 0.0015)
        need = s_front - (behind - gap_s)
        ok = (behind < 1e2) & vis[iy, ix]
        if ok.any() and need[ok].max() > 0:
            t += need[ok].max()
        P = P + self.cam.toward * t
        Q = Q + self.cam.toward * t
        self.built[spec['name']] = {'front': (-t - field).astype(np.float64)}   # its front's depth per art pixel
        T = oriented(P, [tuple(x) for x in tris], self.cam.toward, True)
        if spec.get('slab'):   # hair-thin: no knife edge, its front and back apart all over, a wall round its rim
            n = len(P)
            Pf = P + self.cam.toward * spec.get('f_min', 0.0004) * (np.arange(n) < nb)[:, None]
            ib_all = bilinear(infl, uv[:, 0], uv[:, 1])
            B_all = np.maximum(spec.get('back', 0.7) * (rim * ib_all + (1 - rim) * ib_all * ib_all / R),
                               spec.get('b_min', 0.0008))
            Qb = self.cam.on_ray(uv[:, 0], uv[:, 1], s0 + B_all) + self.cam.toward * t
            V = np.r_[Pf, Qb]
            T = oriented(V, [tuple(x) for x in tris], self.cam.toward, True)
            T2 = oriented(V, [(a + n, b + n, c + n) for a, b, c in tris], self.cam.toward, False)
            side = []
            for i in range(nb):
                j = (i + 1) % nb
                e = uv[j] - uv[i]
                nrm = np.array([e[1], -e[0]]) / max(np.hypot(*e), 1e-9)
                mid = (uv[i] + uv[j]) / 2 + nrm * 1.5
                if region[int(np.clip(mid[1], 0, self.H - 1)), int(np.clip(mid[0], 0, self.W - 1))]:
                    nrm = -nrm   # out of the piece
                out3 = np.array([nrm[0], -nrm[1] * self.cam.se, -nrm[1] * self.cam.ce])
                for tri in ((i, j, n + j), (i, n + j, n + i)):
                    q = np.cross(V[tri[1]] - V[tri[0]], V[tri[2]] - V[tri[0]])
                    side.append(tri if q @ out3 >= 0 else (tri[0], tri[2], tri[1]))
            self._finish(spec, vis, own, region, V, T + T2 + side, np.r_[uv, uv], n, nb, T)
            return
        m = lambda i: i if i < nb else i + len(P) - nb
        T2 = oriented(np.r_[P, Q], [(m(a), m(b), m(c)) for a, b, c in tb], self.cam.toward, False)
        uvb = np.r_[uv, ub[nb:]]
        self._finish(spec, vis, own, region, np.r_[P, Q], T + T2, uvb, len(P), nb, T)

    def band(self, vis, spec):
        """The art's shading over a piece as -1..1 (its lights and shades at the scale of its forms)."""
        lum = lum_of(cv2.inpaint(self.rgb, u8(self.remove & vis), 3, cv2.INPAINT_TELEA))
        s1, s2 = spec.get('band', (6.0, 40.0))
        a, _ = masked_blur(lum, vis, s1)
        b, _ = masked_blur(lum, vis, s2)
        f = np.clip((a - b) / spec.get('band_scale', 25.0), -1, 1) * vis
        return (lambda uv: bilinear(f, uv[:, 0], uv[:, 1])), f

    def shell(self, spec):
        """A leaf or a stalk over a solid (spec['on']): over its surface, `off` nearer the camera (more for every
        level), rounded up `top` from its own margins, which rest on what is under them."""
        vis, own, higher = self.regions(spec)
        self._inner_ink(spec, vis, own)
        over = spec.get('over', 3)
        region = vis | (cv2.dilate(u8(vis), disk(over)).astype(bool) & higher) if over else vis
        region = tidy(cv2.GaussianBlur(region.astype(np.float32), (0, 0), 1.0) > 0.5, 0)
        gap, gb = spec.get('gap', 20.0), spec.get('gb', 12.0)
        extra = self._extras(spec, vis, region, gap)
        uv, tris, nb, d, R, _ = self.mesh(region, gap, gb, self._ring(spec), spec.get('smooth', 1.5), extra,
                                          spec.get('extra_margin', 4.0))
        base = self.built[spec['on']]['front']       # depth of the solid's surface per art pixel
        S = bilinear(base, uv[:, 0], uv[:, 1])
        d_own = cv2.distanceTransform(u8(~own), cv2.DIST_L2, 5)
        dv = bilinear(d_own, uv[:, 0], uv[:, 1])
        wid = spec.get('round_px', 14.0)
        L = spec.get('top', 0.0015) * np.sqrt(np.clip(dv / wid, 0, 1) * (2 - np.clip(dv / wid, 0, 1)))
        if spec.get('relief'):
            L = L + spec['relief'] * self.band(vis, spec)[0](uv)
        s = S - spec.get('off', 0.002) - L
        iy = np.clip(np.round(uv[:, 1]).astype(int), 0, self.H - 1)
        ix = np.clip(np.round(uv[:, 0]).astype(int), 0, self.W - 1)
        zb = cv2.erode(np.where(np.isfinite(self.zb), self.zb, 1e3).astype(np.float32), disk(2))
        under = zb[iy, ix]
        eps = spec.get('eps', 0.0004)
        rim = np.arange(len(uv)) < nb
        own_rim = rim & (dv < 3.0)
        s = np.where(own_rim, np.where(under < 1e2, under - eps, S), s)   # its own margins rest on what is under
        s = np.where(under < 1e2, np.minimum(s, under - eps), s)          # and all of it lies in front of it
        P = self.cam.on_ray(uv[:, 0], uv[:, 1], s)
        T = oriented(P, [tuple(x) for x in tris], self.cam.toward, True)
        self._finish(spec, vis, own, region, P, T, uv, len(P), nb, T)

    def _finish(self, spec, vis, own, region, V, T, uv, nfront, nb, front):
        """Its colours, its record, and its front drawn into the depth buffer."""
        Pf = V[:nfront]
        fr = np.array(front)
        pu, pv = self.cam.project(Pf[:, 0], Pf[:, 1], Pf[:, 2])
        raster(np.stack([pu, pv], -1)[fr], self.cam.depth(Pf)[fr], np.full(len(fr), spec['pid']), self.H, self.W,
               self.zb, self.zid)
        # colours
        soft = self.soft_colour(vis, spec.get('sigma', 3.0))
        col = bilinear(soft, uv[:, 0], uv[:, 1])
        if spec.get('ink_on') == 'paper':   # the art's ink only along the silhouette, not over what is under it
            own = vis & cv2.dilate(u8(~self.zone | (self.labels == 0)), np.ones((3, 3), np.uint8)).astype(bool)
        d_own = cv2.distanceTransform(u8(~own), cv2.DIST_L2, 5) if own.any() else np.full(vis.shape, 1e3, np.float32)
        dv = bilinear(d_own, uv[:, 0], uv[:, 1])
        w = spec.get('ink_w', self.ink_w)
        r0, r1 = spec.get('ink', (0.8 * w, 0.45 * w + 1.0))
        w_ink = 0.92 * (1 - np.clip((dv - r0) / max(r1, 1e-6), 0, 1)) if r1 > 0 else np.zeros(len(uv))
        w_ink[nfront:] = 0.0
        ink = np.array([int(self.ink_hex[i:i + 2], 16) for i in (1, 3, 5)], float)
        col = col * (1 - w_ink[:, None]) + ink * w_ink[:, None]
        vcol = [[hexc(c), self.w_tint] for c in col]
        tcol = [None] * len(T)
        for mask, how in spec.get('marks', []):
            mcol, _ = masked_blur(self.rgb, mask, 1.5) if how is None else (None, None)
            for i, t in enumerate(T):
                if max(t) >= nfront:
                    continue
                c = uv[list(t)].mean(0)
                x, y = int(c[0]), int(c[1])
                if 0 <= x < self.W and 0 <= y < self.H and mask[y, x]:
                    rgb = mcol[y, x] if how is None else np.array([int(how[j:j + 2], 16) for j in (1, 3, 5)])
                    tcol[i] = [hexc(rgb), self.w_tint]
        self.out.append({'name': spec['name'], 'mat': spec['mat'], 'verts': np.round(V, 6).tolist(),
                         'tris': [list(map(int, t)) for t in T], 'vcol': vcol, 'tcol': tcol})
        nm = sum(c is not None for c in tcol)
        if self.verbose:
            print(f"[trace] {spec['name']}: {len(T)} triangles ({len(front)} front, rim {nb}), {nm} painted",
                  flush=True)

    # ---------------------------------------------------------------- checks and output
    def check(self):
        """How much of each piece's region the built surfaces show as that piece, from the art's camera."""
        ok = self.zone & (self.labels > 0)
        inner = cv2.erode(u8(ok), disk(3)).astype(bool)
        bad = inner & (self.zid != self.labels)
        print(f'[trace] seen as traced: {1 - bad.sum() / max(inner.sum(), 1):.4f}'
              f' (covered {(self.zid >= 0).sum() / max(self.zone.sum(), 1):.4f} of the art)', flush=True)
        for s in self.specs:
            m = inner & (self.labels == s['pid'])
            if m.any():
                frac = (bad & m).sum() / m.sum()
                if frac > 0.01:
                    print(f"[trace]   {s['name']}: {frac:.3f} of it shows something else", flush=True)
        return bad

    def save(self, key, extra=None):
        """Writes food_models/traced_<key>.json: the camera, the pieces, and whatever else the builder needs."""
        data = {'camera': {'el': self.cam.el, 'k': self.cam.k, 'u0': self.cam.u0, 'v0': self.cam.v0},
                'pieces': self.out, **(extra or {})}
        path = os.path.join(MODELS, f'traced_{key}.json')
        json.dump(data, open(path, 'w'), separators=(',', ':'))
        print(f'[trace] wrote {path}: {sum(len(o["tris"]) for o in self.out)} triangles', flush=True)

    def marks_image(self, path, crop=None):
        """The art with every piece's marks over it in red (what is painted crisp)."""
        out = self.rgb.copy()
        for sp in self.specs:
            for m, _ in sp.get('marks', []):
                out[m] = (255, 0, 0)
        im = Image.fromarray(out)
        if crop:
            im = im.crop(crop)
        im.save(path)

    def sheet(self, path, title, crop=None, tints=None):
        n = len(self.specs)
        rng = np.random.default_rng(3)
        tints = tints or [tuple(int(x) for x in rng.integers(90, 240, 3)) for _ in range(n)]
        tracing_sheet(path, self.rgba, self.labels, [s['name'] for s in self.specs], tints, (), crop=crop,
                      title=title)
        print(f'[trace] sheet {path}', flush=True)
