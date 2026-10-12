"""Helpers for tracing the plated dishes 胡饼 (D01), 水晶脍 (D05), 玉板鲊 (D14) and 北京烤鸭 (D19) on top of
trace_common.py: where a piece's outline is its own edge (against the dish) and where another piece hides it, how far
each point lies in from its own edges, the plane a stiff piece rests on, keeping what lies behind behind, and a
piece's surface mapped onto a solid it is fitted to (a cube of aspic, a disc of pancake).
"""
import math

import cv2
import numpy as np

from trace_common import disk, oriented, u8


def own_edges(pieces, pid, mask, reach=6):
    """The pixels of mask's outline that lie against the dish (or nothing), not against another piece: its own edge,
    seen in the art. A boolean image."""
    edge = mask & ~cv2.erode(u8(mask), disk(1)).astype(bool)
    others = cv2.dilate(u8((pieces > 0) & (pieces != pid)), disk(reach)).astype(bool)
    return edge & ~others


def level_distance(cam, mask, edges, at_uv):
    """How far each point at_uv (art pixels) lies in from the edge pixels `edges` of mask, in metres as on level
    ground (the art's rows stretched by 1/sin(el)), measured within mask."""
    H, W = mask.shape
    Hs = int(round(H / cam.se))
    m = cv2.resize(u8(mask), (W, Hs), interpolation=cv2.INTER_NEAREST).astype(bool)
    e = cv2.resize(u8(edges), (W, Hs), interpolation=cv2.INTER_NEAREST).astype(bool)
    e = cv2.dilate(u8(e), disk(1)).astype(bool) & m
    src = np.where(e, 0, 1).astype(np.uint8)
    if not e.any():
        src[:] = 1
        src[~m] = 0
    d = cv2.distanceTransform(src, cv2.DIST_L2, 5)
    iu = np.clip(np.round(at_uv[:, 0]).astype(int), 0, W - 1)
    iv = np.clip(np.round(at_uv[:, 1] / cam.se).astype(int), 0, Hs - 1)
    return d[iv, iu] / cam.k


def rest_plane(cam, mask, support, lift, iters=6, step=6, tilt=None):
    """The plane z = a + b·x + c·y + lift that a stiff piece seen at mask (art pixels) rests on: as low as it can lie
    while over the surface z = support(x, y) everywhere under it (its middle plane `lift` above that). Given tilt
    (b, c) only its height is found. Returns (a, b, c) of its underside."""
    vs, us = np.nonzero(mask[::step, ::step])
    us, vs = us * step + step / 2, vs * step + step / 2
    a, b, c = 0.0, 0.0, 0.0
    base = lambda x, y: a + b * x + c * y + lift
    for _ in range(iters):
        X, Y, _ = cam.backproject(us, vs, lambda x, y: a + b * x + c * y + lift, y0=-0.3, y1=0.3)
        S = support(X, Y)
        if tilt is not None:
            b, c = tilt
            a = float(np.max(S - b * X - c * Y))
            continue
        best = None
        for bb in np.linspace(-0.6, 0.6, 49):
            for cc in np.linspace(-0.6, 0.6, 49):
                aa = np.max(S - bb * X - cc * Y)
                m = aa + bb * X.mean() + cc * Y.mean()
                if best is None or m < best[0]:
                    best = (m, aa, bb, cc)
        _, a, b, c = best
    return float(a), float(b), float(c)


def behind(cam, P, zbuf, gap=0.0008, count=None):
    """Points of a piece that the art shows behind others (zbuf: their depths per art pixel) moved back along their
    lines of sight to just behind them, so that the art's view sees the others in front where it draws them in front.
    Only the first `count` points (its front surface) are tested; a skirt hangs from its outline's points and
    follows them."""
    P = np.array(P, float)
    n = len(P) if count is None else count
    H, W = zbuf.shape
    u, v = cam.project(P[:n, 0], P[:n, 1], P[:n, 2])
    iu = np.clip(np.round(u).astype(int), 0, W - 1)
    iv = np.clip(np.round(v).astype(int), 0, H - 1)
    zb = cv2.erode(np.where(np.isfinite(zbuf), zbuf, 1e3).astype(np.float32), disk(2))[iv, iu].astype(float)
    s = cam.depth(P[:n])
    need = (zb < 1e2) & (s < zb + gap)
    if need.any():
        Q = P[:n]
        Q[need] = cam.on_ray(u[need], v[need], zb[need] + gap)
        P[:n] = Q
    return P


def raster_piece(cam, P, T, nfront, pid, zb, zid):
    """Adds a piece's front triangles to the depth buffer (art pixels)."""
    from trace_common import raster
    front = [t for t in T if max(t) < nfront]
    pu, pv = cam.project(P[:, 0], P[:, 1], P[:, 2])
    raster(np.stack([pu, pv], -1)[np.array(front)], cam.depth(P)[np.array(front)], np.full(len(front), pid),
           zb.shape[0], zb.shape[1], zb, zid)


def onto_solid(cam, uv, sdf, s0, s1, steps=160):
    """Each art pixel's point on the solid sdf(P) <= 0 (a signed distance, metres): where its line of sight first
    enters it; a line of sight that misses it (the art's outline a little wider than the solid) takes the depth of
    the nearest one that hits, so that the surface runs on flat to the art's outline without folding back.
    s0..s1: the stretch of the line of sight searched (depth, metres)."""
    ss = np.linspace(s0, s1, steps)
    P = cam.on_ray(uv[:, 0][:, None], uv[:, 1][:, None], ss[None, :])   # n × steps × 3
    D = sdf(P.reshape(-1, 3)).reshape(len(uv), steps)
    inside = D <= 0
    first = np.where(inside.any(1), np.argmax(inside, 1), np.argmin(D, 1))
    depth = np.full(len(uv), np.nan)
    for i, j in enumerate(first):
        if inside[i].any() and j > 0:   # refine the crossing between j-1 and j
            lo, hi = ss[j - 1], ss[j]
            for _ in range(24):
                mid = (lo + hi) / 2
                if sdf(cam.on_ray(uv[i, 0], uv[i, 1], mid)[None])[0] <= 0:
                    hi = mid
                else:
                    lo = mid
            depth[i] = hi
    hit = np.isfinite(depth)
    if hit.any() and (~hit).any():
        A, B = uv[~hit], uv[hit]
        nn = np.argmin(((A[:, None, :] - B[None, :, :]) ** 2).sum(-1), 1)
        depth[~hit] = depth[hit][nn]
    depth = np.where(np.isfinite(depth), depth, (s0 + s1) / 2)
    return cam.on_ray(uv[:, 0], uv[:, 1], depth)


def rounded_box_sdf(c, half, yaw, r, taper=0.0):
    """The signed distance to a box (half sizes, its middle at c, turned yaw about z) with edges rounded by r; taper
    narrows it toward its top (share of its half sizes lost at the top)."""
    c = np.asarray(c, float)
    cy, sy = math.cos(yaw), math.sin(yaw)

    def f(P):
        q = P - c
        x = cy * q[:, 0] + sy * q[:, 1]
        y = -sy * q[:, 0] + cy * q[:, 1]
        z = q[:, 2]
        k = 1 - taper * np.clip((z + half[2]) / (2 * half[2]), 0, 1)
        d = np.abs(np.stack([x / k, y / k, z], -1)) - (np.asarray(half) - r)
        return np.linalg.norm(np.maximum(d, 0), axis=1) + np.minimum(d.max(1), 0) - r
    return f


def detail_points(mask, field, r_min, r_max, g_ref, margin=8, seed=0, step=3):
    """Points over mask (art pixels) spread like a Poisson disk whose spacing shrinks where `field` (a colour's
    strength, 0..1) changes fast: r_max apart where it is flat, down to r_min where its gradient reaches g_ref per
    pixel, so that a mesh through them catches the art's small patches of colour without spending vertices on the
    plain. Kept `margin` pixels in from the mask's edge."""
    H, W = mask.shape
    f = cv2.GaussianBlur(field.astype(np.float32), (0, 0), 1.5)
    g = np.hypot(cv2.Sobel(f, cv2.CV_32F, 1, 0, ksize=3) / 8, cv2.Sobel(f, cv2.CV_32F, 0, 1, ksize=3) / 8)
    g = cv2.dilate(g, disk(3))
    r = r_max - (r_max - r_min) * np.clip(g / g_ref, 0, 1)
    inner = cv2.erode(u8(mask), disk(margin)).astype(bool)
    ys, xs = np.nonzero(inner[::step, ::step])
    ys, xs = ys * step, xs * step
    rng = np.random.default_rng(seed)
    order = np.argsort(r[ys, xs] + rng.uniform(0, 0.5, len(xs)))   # the busiest first
    cell = max(1, int(r_min))
    grid = {}
    out = []
    for i in order:
        x, y = int(xs[i]), int(ys[i])
        rr = r[y, x]
        cx, cy = x // cell, y // cell
        k = int(math.ceil(r_max / cell))
        ok = True
        for gx in range(cx - k, cx + k + 1):
            for gy in range(cy - k, cy + k + 1):
                for (px, py, pr) in grid.get((gx, gy), ()):
                    if (px - x) ** 2 + (py - y) ** 2 < min(rr, pr) ** 2:
                        ok = False
                        break
                if not ok:
                    break
            if not ok:
                break
        if ok:
            grid.setdefault((cx, cy), []).append((x, y, rr))
            out.append((x + 0.5, y + 0.5))
    return np.array(out, float).reshape(-1, 2)


def coarse_fill(outline, G):
    """A coarse triangulation of the simple polygon `outline` (art pixels, in order): its own points first, then a
    grid of points G pixels apart inside it (at least G/2 in from it). Returns the points and the triangles."""
    poly = np.asarray(outline, float)
    pc = poly.astype(np.float32).reshape(-1, 1, 2)
    x0, y0 = poly.min(0) - 2
    x1, y1 = poly.max(0) + 2
    grid = [(x, y) for k, y in enumerate(np.arange(y0 + G / 2, y1, G * 0.866))
            for x in np.arange(x0 + G / 2 + (k % 2) * G / 2, x1, G)
            if cv2.pointPolygonTest(pc, (float(x), float(y)), True) > 0.5 * G]
    pts = np.r_[poly, np.array(grid, float).reshape(-1, 2)].astype(np.float32).astype(np.float64)
    sd = cv2.Subdiv2D((int(x0) - 60, int(y0) - 60, int(x1 - x0) + 120, int(y1 - y0) + 120))
    idx = {}
    for k, q in enumerate(pts):
        idx.setdefault((round(float(q[0]), 3), round(float(q[1]), 3)), k)
        sd.insert((float(q[0]), float(q[1])))

    def find(q):
        k = idx.get((round(float(q[0]), 3), round(float(q[1]), 3)))
        if k is None:
            dd = ((pts - np.array(q)) ** 2).sum(1)
            k = int(np.argmin(dd)) if dd.min() < 0.05 ** 2 else None
        return k
    tris = []
    for t in sd.getTriangleList():
        a_, b_, c_ = (t[0], t[1]), (t[2], t[3]), (t[4], t[5])
        ia, ib, ic = find(a_), find(b_), find(c_)
        if ia is None or ib is None or ic is None or len({ia, ib, ic}) < 3:
            continue
        cen = ((a_[0] + b_[0] + c_[0]) / 3, (a_[1] + b_[1] + c_[1]) / 3)
        if cv2.pointPolygonTest(pc, cen, False) >= 0 and \
                all(cv2.pointPolygonTest(pc, ((p_[0] + q_[0]) / 2, (p_[1] + q_[1]) / 2), True) >= -0.6
                    for p_, q_ in ((a_, b_), (b_, c_), (c_, a_))):
            tris.append((ia, ib, ic))
    return pts, tris


def closed_under(cam, P, T, nb, uv, close, lift=0.0005, G=110.0):
    """A piece's front surface (points P, triangles T over the art pixels uv, its first nb points its outline) closed
    underneath, hidden from the art's view: a skirt from its outline along the lines of sight down to the surface
    z = close(x, y) + lift, and a floor there: a coarse fill of the outline as the art sees it (coarse_fill, G
    pixels), each point carried along its line of sight onto that surface, facing down. The art's view sees the
    skirt edge-on and the floor behind the front, and since every point keeps its own line of sight nothing folds;
    each skirt face is turned outwards (away from the piece's inside as the art's view sees it). Returns points and
    triangles; the front's points come first, then the outline's feet (in its order), then the floor's."""
    P = np.asarray(P, float)
    n = len(P)
    fpts, ftris = coarse_fill(uv[:nb], G)
    Xs, Ys, Zs = cam.backproject(fpts[:, 0], fpts[:, 1], close, lift=lift, y0=-0.3, y1=0.3)
    Q = np.stack([Xs, Ys, Zs], -1)
    sQ, sP = cam.depth(Q[:nb]), cam.depth(P[:nb])   # an outline already on the floor stays where it is
    Q[:nb] = np.where((sQ < sP)[:, None], P[:nb], Q[:nb])
    P2 = np.r_[P, Q]
    T = [tuple(t) for t in T]
    floor = []
    for a_, b_, c_ in ftris:
        t = (a_ + n, b_ + n, c_ + n)
        nn = np.cross(P2[t[1]] - P2[t[0]], P2[t[2]] - P2[t[0]])
        floor.append(t if nn[2] <= 0 else (t[0], t[2], t[1]))   # facing down
    poly = uv[:nb]
    area = np.sum(poly[:, 0] * np.roll(poly[:, 1], -1) - np.roll(poly[:, 0], -1) * poly[:, 1])
    skirt = []
    for i in range(nb):
        j = (i + 1) % nb
        e = poly[j] - poly[i]
        o = np.array([e[1], -e[0]]) if area > 0 else np.array([-e[1], e[0]])   # outward, in pixels
        ow = np.array([o[0], -o[1] * cam.se, -o[1] * cam.ce])                 # and in the world
        for t in ((i, j, n + j), (i, n + j, n + i)):
            nn = np.cross(P2[t[1]] - P2[t[0]], P2[t[2]] - P2[t[0]])
            if np.linalg.norm(nn) < 1e-14:
                continue
            skirt.append(t if nn @ ow >= 0 else (t[0], t[2], t[1]))
    return P2, T + skirt + floor


def box_outline(cam, c, half, yaw):
    """The art pixels of a box's outline (its corners' convex hull): middle c, half sizes, turned yaw about z."""
    cy, sy = math.cos(yaw), math.sin(yaw)
    pts = []
    for dx in (-1, 1):
        for dy in (-1, 1):
            for dz in (-1, 1):
                x, y = dx * half[0], dy * half[1]
                pts.append((c[0] + cy * x - sy * y, c[1] + sy * x + cy * y, c[2] + dz * half[2]))
    pts = np.array(pts)
    u, v = cam.project(pts[:, 0], pts[:, 1], pts[:, 2])
    return cv2.convexHull(np.stack([u, v], -1).astype(np.float32))[:, 0, :]


def fit_box(cam, own, allowed, z0, start, iters=1500, scale=0.25, seed=0, size=None, yaw=None):
    """A box standing on z = z0 fitted so that, seen from the art's camera, it covers the art's mask `own` and
    nothing outside `allowed` (own and what hides it): its middle (x, y), half sizes and turn. start: (x, y, hx, hy,
    hz, yaw); given size (hx, hy, hz) only where it stands and its turn are found. Returns those and how far its
    outline is off (the area wrong, as a share of own's)."""
    H, W = own.shape
    sh = (int(W * scale), int(H * scale))
    o = cv2.resize(u8(own), sh, interpolation=cv2.INTER_AREA) > 0
    al = cv2.resize(u8(allowed), sh, interpolation=cv2.INTER_AREA) > 0

    def cost(p):
        x, y, hx, hy, hz, turn = p
        if size is not None:
            hx, hy, hz = size
        if yaw is not None:
            turn = yaw
        if min(hx, hy, hz) < 0.005:
            return 1e9
        poly = box_outline(cam, (x, y, z0 + hz), (hx, hy, hz), turn) * scale
        m = np.zeros((sh[1], sh[0]), np.uint8)
        cv2.fillPoly(m, [np.round(poly * 8).astype(np.int32)], 1, shift=3)
        m = m.astype(bool)
        return float((m & ~al).sum() * 1.0 + (o & ~m).sum() * 1.0)
    rng = np.random.default_rng(seed)
    best = (cost(np.array(start)), np.array(start, float))
    step = np.array([0.004, 0.004, 0.003, 0.003, 0.003, 0.08])
    for it in range(iters):
        cand = best[1] + rng.normal(0, 1, 6) * step
        cc = cost(cand)
        if cc < best[0]:
            best = (cc, cand)
        if it % 150 == 149:
            step *= 0.7
    p = best[1].copy()
    if size is not None:
        p[2:5] = size
    if yaw is not None:
        p[5] = yaw
    return p, best[0] / max(o.sum(), 1)
