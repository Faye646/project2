"""罐装、调料瓶罐和饮品: sauerkraut, stock, salt, oil, sugar, vinegar, wine, cola."""
import math
import random

import bmesh
from mathutils import Matrix, Vector

from .core import *  # noqa: F401,F403

TUNE = {}   # (tuning only) overrides of the fitted numbers, by item


PALETTE.update({
    'JugMouth': ('#4a2416', '#331810'),   # the dark inside of a jug's mouth, round the stopper
    'CeladonLip': ('#f1e8cc', '#d8cba4'),   # the cream rolled lip of the celadon cups and ewer
    'CeladonDeep': ('#8fae99', '#70907b'),   # deep down inside a celadon ewer's mouth
    'ColaGlass': ('#eef0dc', '#bcc4a6'),   # the clear glass of the cola bottle (see-through: GLASS)
    'ColaFoam': ('#e2b484', '#bc8c5c'),   # the line of foam on top of the cola
    'ColaGlassDeep': ('#d6d4bc', '#a6a688'),   # the inside of the bottle's neck, down from the lip (see-through)
    'ColaLiquid': ('#741a06', '#4a0e03'),   # the cola seen through the glass: dark red-brown, glowing amber at its
                                            # sides where the light comes through (tinted), with bubbles
    'CapRim': ('#f4a28c', '#d9776a'),   # the shining rolled edge round the top of the crown cap
    'CapSkirt': ('#d2352c', '#a51f19'),   # the cap's pleated skirt, a darker red than its top
})
GLOSS.update({'JugMouth': 0.0, 'CeladonLip': 0.5, 'CeladonDeep': 0.3, 'ColaGlass': 0.8, 'ColaFoam': 0.3,
              'ColaGlassDeep': 0.5, 'CapRim': 0.5, 'CapSkirt': 0.3, 'ColaLiquid': 0.7})
VIVID.update({'CeladonLip': 0.5, 'CeladonDeep': 0.5, 'ColaLiquid': 0.7})
VTINT.update({'ColaLiquid': 1.0})
DETAIL.update({'ColaLiquid': ('food_bubbles', 30, '#f4b088', 0.35, 0.15)})   # bubbles rising in it
# the bottle's glass, see-through: barely there where it faces the eye, fuller at its rims, its ink line inside its
# rim; the neck's far inside drawn before its near outside
GLASS.update({'ColaGlass': {'alpha': 0.07, 'edge': 0.55, 'gloss': 1.0, 'rim': 1.0, 'order': 0},
              'ColaGlassDeep': {'alpha': 0.2, 'edge': 0.45, 'gloss': 0.5, 'rim': 0.5, 'order': -1}})


# ---------------------------------------------------------------- turned vessels fitted to the art
# The profiles below come from fitting each vessel's silhouette in the art seen from the art view (35° up): a few
# radii at even heights, scaled to real size, then smoothed into many rings so no facet shows.

def spline(pts, per=4):
    """A smooth Catmull-Rom curve through pts [(r, z)], `per` points per span, ending at the last point."""
    P = [pts[0]] + list(pts) + [pts[-1]]
    out = []
    for i in range(1, len(P) - 2):
        p0, p1, p2, p3 = P[i - 1], P[i], P[i + 1], P[i + 2]
        for k in range(per):
            t = k / per
            out.append(tuple(0.5 * (2 * p1[j] + (p2[j] - p0[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t * t
                                    + (3 * p1[j] - p0[j] - 3 * p2[j] + p3[j]) * t ** 3) for j in (0, 1)))
    out.append(tuple(pts[-1]))
    return out


def shell(p, outer, t, fill_z, mat, fill, n=64, M=Matrix(), deform=None, per=4):
    """A glazed vessel turned from its outer profile [(r, z)] going up from the foot: a softly rounded foot, the
    outside, a lip rolled over by a half round t thick, the inside t in from the outside down to fill_z, closed there
    by `fill`, and the underside. Returns the inside radius at fill_z."""
    curve = spline(outer, per)
    r0 = curve[0][0]
    rt, zt = curve[-1]
    lip = [(rt - t / 2 + t / 2 * math.cos(a), zt + t / 2 * math.sin(a)) for a in
           (math.radians(d) for d in (30, 60, 90, 120, 150, 180))]
    inner = [(r - t, z) for r, z in reversed(curve[:-1]) if z > fill_z + t]
    r_fill = next(r for r, z in zip([r for r, _ in reversed(curve)], [z for _, z in reversed(curve)]) if z <= fill_z) - t
    prof = [(0.0, 0.0), (r0 * 0.86, 0.0), (r0 * 0.97, 0.0015), (r0, 0.005)] + [q for q in curve if q[1] > 0.005] + lip         + inner + [(r_fill, fill_z)]
    p.lathe(prof, mat, n=n, M=M, deform=deform, close_ends=False)
    p.lathe([(r_fill, fill_z), (0.0, fill_z + 0.0005)], fill, n=n, M=M, deform=deform, close_ends=False)
    return r_fill


def loop(p, pts, radius, mat, sides=10, M=Matrix(), per=4, squash=1.0):
    """A round tube along a smooth curve through pts [(x, z)] in the local XZ plane, placed by M: handles, spouts
    bent in one plane. Its rings keep the plane's normal as a fixed side, so they never twist however the curve
    turns; the ends are capped, so bury them in what they join. `squash` flattens it across the plane."""
    curve = spline(pts, per)
    tmp = bmesh.new()
    rings = []
    for i, (x, z) in enumerate(curve):
        x0, z0 = curve[max(i - 1, 0)]
        x1, z1 = curve[min(i + 1, len(curve) - 1)]
        t = Vector((x1 - x0, 0.0, z1 - z0)).normalized()
        nrm = Vector((-t.z, 0.0, t.x))   # in the plane, square to the curve
        rings.append([tmp.verts.new(M @ (Vector((x, 0.0, z)) + radius * (math.cos(a) * nrm + squash * math.sin(a) * Vector((0, 1, 0)))))
                      for a in (2 * math.pi * k / sides for k in range(sides))])
    for ra, rb in zip(rings, rings[1:]):
        for k in range(sides):
            tmp.faces.new((ra[k], ra[(k + 1) % sides], rb[(k + 1) % sides], rb[k]))
    tmp.faces.new(list(reversed(rings[0])))
    tmp.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)


def ribbon(p, path, widths, t, mats, up=(0.0, 0.0, 1.0), wave=0.0, ph=0.0, fold=0.0):
    """A thick leaf strip along path [points] (soft-cage it): across it, len(mats) strips of the given materials (dark
    edges round a pale middle), `widths` per point (or one), t thick, its face towards `up` (one, or one per point:
    a leaf hanging down faces outwards); the two long edges ripple by `wave` and droop by `fold` of the width."""
    if len(path) > 2:   # smooth the path: two points per span
        xs = spline([(q[0], q[1]) for q in path], 2)
        zs = spline([(q[2], 0.0) for q in path], 2)
        path = [(x, y, z) for (x, y), (z, _) in zip(xs, zs)]
        if not isinstance(widths, (int, float)):
            widths = [w for w, _ in spline([(w, 0.0) for w in widths], 2)]
        if isinstance(up[0], (tuple, list, Vector)):
            ups = [Vector(u) for u in up]
            up = [tuple(ups[min(i // 2, len(ups) - 1)].lerp(ups[min(i // 2 + 1, len(ups) - 1)], (i % 2) / 2))
                  for i in range(len(path))]
    P = [Vector(q) for q in path]
    n = len(P)
    cols = len(mats) + 1
    tmp = bmesh.new()
    top, bot = [], []
    for i, q in enumerate(P):
        T = (P[min(i + 1, n - 1)] - P[max(i - 1, 0)]).normalized()
        S = Vector(up[i] if isinstance(up[0], (tuple, list, Vector)) else up).cross(T)
        S = S.normalized() if S.length > 1e-6 else Vector((1, 0, 0))
        N = T.cross(S)
        w = widths[i] if isinstance(widths, (list, tuple)) else widths
        rt, rb = [], []
        for j in range(cols):
            u = j / (cols - 1) - 0.5
            edge = abs(u) * 2
            c = q + S * (u * w) + N * (wave * edge ** 2 * math.sin(i * 1.9 + ph + u * 3) - fold * w * edge ** 2)
            rt.append(tmp.verts.new(c + N * t / 2 * (1 - 0.6 * edge ** 4)))
            rb.append(tmp.verts.new(c - N * t / 2 * (1 - 0.6 * edge ** 4)))
        top.append(rt)
        bot.append(rb)
    faces = []
    for i in range(n - 1):
        for j in range(cols - 1):
            faces.append((tmp.faces.new((top[i][j], top[i][j + 1], top[i + 1][j + 1], top[i + 1][j])), mats[j]))
            faces.append((tmp.faces.new((bot[i][j + 1], bot[i][j], bot[i + 1][j], bot[i + 1][j + 1])), mats[j]))
        faces.append((tmp.faces.new((top[i][0], top[i + 1][0], bot[i + 1][0], bot[i][0])), mats[0]))
        faces.append((tmp.faces.new((top[i][-1], bot[i][-1], bot[i + 1][-1], top[i + 1][-1])), mats[-1]))
    for i, sgn in ((0, 1), (n - 1, -1)):
        for j in range(cols - 1):
            q = (top[i][j], bot[i][j], bot[i][j + 1], top[i][j + 1])
            faces.append((tmp.faces.new(q if sgn > 0 else tuple(reversed(q))), mats[j]))
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    vmap = {v: p.bm.verts.new(v.co) for v in tmp.verts}
    for f, m in faces:
        p.bm.faces.new([vmap[v] for v in f.verts]).material_index = p._mi(m)
    tmp.free()


def paddle(p, a, b, w0, w1, t, mat, up=(0.0, -0.3, 1.0)):
    """A flat wooden handle from a to b as one soft cage: w0 wide at a widening to a round end w1 wide at b, t thick,
    its flat side turned towards `up`."""
    a, b = Vector(a), Vector(b)
    x = (b - a).normalized()
    y = Vector(up).cross(x).normalized()
    R = Matrix((x, y, x.cross(y))).transposed()
    L = (b - a).length

    def shape(v):   # v: unit sphere scaled to the half sizes; widen towards +x, the end
        f = (v.x / (L / 2) + 1) / 2
        return R @ Vector((v.x, v.y * (w0 + (w1 - w0) * f ** 1.5) / w1, v.z))
    with p.soft():
        p.blob((a + b) / 2, 1.0, mat, squash=(L / 2, w1 / 2, t / 2), segs=(10, 4), deform=shape)


class Curve:
    """A smooth curve through 3D points (Catmull-Rom) with rotation-minimising frames, so that rings swept along it
    never twist: spouts, handles. Beyond its ends it runs on straight."""

    def __init__(self, pts, per=8, side=(0.0, 0.0, 1.0)):
        xy = spline([(q[0], q[1]) for q in pts], per)
        zz = spline([(q[2], 0.0) for q in pts], per)
        P = [Vector((x, y, z)) for (x, y), (z, _) in zip(xy, zz)]
        self.P, self.s = P, [0.0]
        for a, b in zip(P, P[1:]):
            self.s.append(self.s[-1] + (b - a).length)
        self.L = self.s[-1]
        T = [(P[min(i + 1, len(P) - 1)] - P[max(i - 1, 0)]).normalized() for i in range(len(P))]
        u = Vector(side)
        nrm = u - T[0] * u.dot(T[0])
        N = [nrm.normalized()]
        for t in T[1:]:
            nrm = N[-1] - t * N[-1].dot(t)
            N.append(nrm.normalized())
        self.T, self.N = T, N

    def at(self, d):
        """Point, tangent and normal at the distance d along the curve."""
        if d <= 0.0:
            return self.P[0] + self.T[0] * d, self.T[0], self.N[0]
        if d >= self.L:
            return self.P[-1] + self.T[-1] * (d - self.L), self.T[-1], self.N[-1]
        i = max(0, min(len(self.s) - 2, next(k for k, s in enumerate(self.s) if s > d) - 1))
        f = (d - self.s[i]) / max(self.s[i + 1] - self.s[i], 1e-9)
        t = self.T[i].lerp(self.T[i + 1], f).normalized()
        nrm = self.N[i].lerp(self.N[i + 1], f)
        return self.P[i].lerp(self.P[i + 1], f), t, (nrm - t * nrm.dot(t)).normalized()


def sweep(p, curve, prof, mat, n=24, squash=1.0):
    """A lathe turned about a curve instead of a straight axis: profile [(r, d)], d the distance along the curve; a
    ring of radius 0 is a single point. Profiles that run along the curve face outwards. `squash` flattens the
    rings across the curve's normal."""
    tmp = bmesh.new()
    rings = []
    for r, d in prof:
        q, t, nrm = curve.at(d)
        b = t.cross(nrm)
        if r < 1e-7:
            rings.append([tmp.verts.new(q)])
        else:
            rings.append([tmp.verts.new(q + r * (math.cos(a) * nrm + squash * math.sin(a) * b))
                          for a in (2 * math.pi * k / n for k in range(n))])
    for ra, rb in zip(rings, rings[1:]):
        if len(ra) == 1 and len(rb) == 1:
            continue
        for k in range(n):
            if len(ra) == 1:
                tmp.faces.new((ra[0], rb[(k + 1) % n], rb[k]))
            elif len(rb) == 1:
                tmp.faces.new((ra[k], ra[(k + 1) % n], rb[0]))
            else:
                tmp.faces.new((ra[k], ra[(k + 1) % n], rb[(k + 1) % n], rb[k]))
    p._commit(tmp, mat)


def spout(p, pts, radii, mat, hole, t=0.003, n=24, depth=None, per=6):
    """A pouring spout: a tapering tube along the curve through pts, radii[i] thick at pts[i] (its first point buried
    in the vessel), its mouth a lip rolled over by a half round t thick, the inside going down `depth` to a floor
    of `hole` (the dark of the opening)."""
    c = Curve(pts, per)
    marks = [0.0]
    for a, b in zip(pts, pts[1:]):
        marks.append(marks[-1] + (Vector(b) - Vector(a)).length)
    k = c.L / marks[-1]
    marks = [m * k for m in marks]
    steps = max(8, len(pts) * per)
    prof = [(0.0, -0.002), (radii[0] * 0.7, 0.0)]
    for i in range(steps + 1):
        d = c.L * i / steps
        j = min(len(marks) - 2, next((m for m, s in enumerate(marks) if s > d), len(marks)) - 1)
        f = (d - marks[j]) / max(marks[j + 1] - marks[j], 1e-9)
        f = f * f * (3 - 2 * f)
        prof.append((radii[j] + (radii[j + 1] - radii[j]) * f, d))
    re = radii[-1]
    prof += [(re - t / 2 + t / 2 * math.cos(a), c.L + t / 2 * math.sin(a)) for a in
             (math.radians(v) for v in (30, 60, 90, 120, 150, 180))]
    depth = depth or re * 2.5
    prof += [(re - t, c.L - depth * f) for f in (0.3, 0.7, 1.0)]
    sweep(p, c, prof, mat, n=n)
    sweep(p, c, [(re - t, c.L - depth), (0.0, c.L - depth - 0.001)], hole, n=n)
    return c


def ewer_spout(p, pts, radii, mat, hole, t=0.0025, n=16, steps=20, level=0.35, depth=None):
    """A pouring spout whose mouth is cut level, as on an ewer: a tapering tube along the curve through pts, radii[i]
    thick at pts[i] (its first point buried in the vessel), its rings turning from square to the curve to level over
    the last `level` of its length, so that the mouth is a level ellipse; the mouth a lip rolled over by a half round
    t thick, the inside going down `depth` to a floor of `hole` (the dark of the opening)."""
    c = Curve(pts, 6)
    marks = [0.0]
    for a, b in zip(pts, pts[1:]):
        marks.append(marks[-1] + (Vector(b) - Vector(a)).length)
    marks = [m * c.L / marks[-1] for m in marks]
    up = Vector((0.0, 0.0, 1.0))

    def ring(r, d, k):
        q, tg, nrm = c.at(d)
        w = min(1.0, max(0.0, (d - (1 - level) * c.L) / (level * c.L)))
        w = w * w * (3 - 2 * w)
        m = (tg * (1 - w) + up * w).normalized()   # the plane the ring lies in
        b = tg.cross(nrm)
        out = []
        for a in (2 * math.pi * i / k for i in range(k)):
            u = math.cos(a) * nrm + math.sin(a) * b
            out.append(q + r * u - tg * (r * u.dot(m) / tg.dot(m)))   # the tube's side line meeting the plane
        return out
    rd = spline(list(zip(marks, radii)), 8)   # the radius along the curve, smooth through the given ones

    def radius(d):
        for (d0, r0), (d1, r1) in zip(rd, rd[1:]):
            if d <= d1:
                return r0 + (r1 - r0) * min(1.0, max(0.0, (d - d0) / max(d1 - d0, 1e-9)))
        return rd[-1][1]
    prof = [(radii[0] * 0.7, 0.0)] + [(radius(c.L * i / steps), c.L * i / steps) for i in range(steps + 1)]
    re = radii[-1]
    prof += [(re - t / 2 + t / 2 * math.cos(a), c.L + t / 2 * math.sin(a)) for a in
             (math.radians(v) for v in (40, 90, 140, 180))]
    depth = depth or re * 2.5
    prof += [(re - t, c.L - depth * f) for f in (0.4, 1.0)]
    tmp = bmesh.new()
    rings = [[tmp.verts.new(c.at(-0.002)[0])]] + [[tmp.verts.new(v) for v in ring(r, d, n)] for r, d in prof]
    for ra, rb in zip(rings, rings[1:]):
        for k in range(n):
            if len(ra) == 1:
                tmp.faces.new((ra[0], rb[(k + 1) % n], rb[k]))
            else:
                tmp.faces.new((ra[k], ra[(k + 1) % n], rb[(k + 1) % n], rb[k]))
    p._commit(tmp, mat)
    tmp = bmesh.new()
    last = [tmp.verts.new(v) for v in ring(re - t, c.L - depth, n)]
    mid = tmp.verts.new(sum(ring(re - t, c.L - depth, n), Vector()) / n - Vector((0.0, 0.0, 0.0005)))
    for k in range(n):
        tmp.faces.new((last[k], last[(k + 1) % n], mid))
    p._commit(tmp, hole)
    return c


def belly(outer, z):
    """The radius of a turned vessel's outer profile [(r, z)] at height z (straight between the points)."""
    for (r0, z0), (r1, z1) in zip(outer, outer[1:]):
        if z0 <= z <= z1:
            return r0 + (r1 - r0) * (z - z0) / max(z1 - z0, 1e-9)
    return outer[0][0] if z < outer[0][1] else outer[-1][0]


def cup_outline(rim_r, h, foot_r, foot_h=0.007, t=0.005, lean=1.0, shelf=1.1, rings=7):
    """The outside of tea_cup() from the foot up to the lip, [(r, z)]."""
    rb, zb = foot_r * shelf, foot_h + 0.0015
    prof = [(foot_r * 0.78, 0.004), (foot_r * 0.88, 0.0), (foot_r * 0.98, 0.0006), (foot_r * 1.005, foot_h * 0.6),
            (foot_r * 1.04, foot_h), (rb, zb)]
    prof += [(rb + (rim_r - rb) * math.sin(th) ** lean, zb + (h - t / 2 - zb) * (1 - math.cos(th)))
             for th in (math.pi / 2 * i / rings for i in range(1, rings + 1))]
    return prof


def along(pts, curve, radii):
    """The radius at a distance d along `curve` (a Curve through pts) as a function, smooth through radii[i] at
    pts[i]."""
    marks = [0.0]
    for a, b in zip(pts, pts[1:]):
        marks.append(marks[-1] + (Vector(b) - Vector(a)).length)
    rd = spline([(m * curve.L / marks[-1], r) for m, r in zip(marks, radii)], 8)

    def radius(d):
        for (d0, r0), (d1, r1) in zip(rd, rd[1:]):
            if d <= d1:
                return r0 + (r1 - r0) * min(1.0, max(0.0, (d - d0) / max(d1 - d0, 1e-9)))
        return rd[-1][1]
    return radius


def strap(p, pts, r, mat, squash=1.0, n=12, per=6):
    """A handle: a round tube along the smooth curve through pts, r thick (or r[i] at pts[i], smoothly between),
    flattened across its bend by `squash`, both ends rounded off like fingertips."""
    c = Curve(pts, per)
    steps = max(8, len(pts) * per)
    radius = along(pts, c, r) if isinstance(r, (list, tuple)) else (lambda d: r)
    r0, r1 = radius(0.0), radius(c.L)
    prof = [(math.sin(a) * r0, -math.cos(a) * r0) for a in (0.0, 0.5, 0.95, 1.3)] +         [(radius(c.L * i / steps), c.L * i / steps) for i in range(steps + 1)] +         [(math.sin(a) * r1, c.L + math.cos(a) * r1) for a in (1.3, 0.95, 0.5, 0.0)]
    sweep(p, c, prof, mat, n=n, squash=squash)


def thinned(curve, turn=6.0, step=0.016):
    """The points of a dense profile [(r, z)] that it needs: one wherever it has turned `turn` degrees or gone `step`
    since the last one kept, and the ends."""
    out = [curve[0]]
    for i in range(1, len(curve) - 1):
        a, b, c = out[-1], curve[i], curve[i + 1]
        t0 = math.atan2(b[1] - a[1], b[0] - a[0])
        t1 = math.atan2(c[1] - b[1], c[0] - b[0])
        bend = abs((t1 - t0 + math.pi) % (2 * math.pi) - math.pi)
        if math.degrees(bend) > turn or math.hypot(c[0] - a[0], c[1] - a[1]) > step:
            out.append(b)
    return out + [curve[-1]]


def smoothed(curve, passes=8):
    """A dense profile [(r, z)] with its kinks eased out: each point moved halfway towards the middle of its
    neighbours, `passes` times, the ends kept."""
    c = list(curve)
    for _ in range(passes):
        c = [c[0]] + [(b[0] + 0.5 * ((a[0] + d[0]) / 2 - b[0]), b[1] + 0.5 * ((a[1] + d[1]) / 2 - b[1]))
                      for a, b, d in zip(c, c[1:], c[2:])] + [c[-1]]
    return c


def vessel(p, outer, t, fill_z, mats, n=48, per=2, deform=None, foot=None, turn=None):
    """shell() with its parts in their own colours, mats = (outside, lip, inside, floor): the outside turned from the
    profile [(r, z)] going up from the foot (a softly rounded one, or `foot` [(r, z)] from the middle of the
    underside out and up), a lip rolled over by a half round t thick, the inside t in from the outside down to fill_z,
    closed there by the floor; `turn` thins the profile to a ring every `turn` degrees of bend. Returns the inside
    radius at fill_z."""
    out_m, lip_m, in_m, floor_m = mats
    curve = spline(outer, per)
    if turn:   # thinned to where it bends
        curve = thinned(curve, turn)
    r0 = curve[0][0]
    rt, zt = curve[-1]
    lip = [(rt - t / 2 + t / 2 * math.cos(a), zt + t / 2 * math.sin(a)) for a in
           (math.radians(d) for d in (0, 30, 60, 90, 120, 150, 180))]
    inner = [(r - t, z) for r, z in reversed(curve[:-1]) if z > fill_z + t]
    r_fill = next(r for r, z in reversed(curve) if z <= fill_z) - t
    foot = foot or [(0.0, 0.0), (r0 * 0.86, 0.0), (r0 * 0.97, 0.0015), (r0, 0.005)]
    p.lathe(foot + [q for q in curve if q[1] > foot[-1][1] + 1e-6], out_m, n=n, deform=deform, close_ends=False)
    p.lathe(lip, lip_m, n=n, deform=deform, close_ends=False)
    p.lathe([lip[-1]] + inner + [(r_fill, fill_z)], in_m, n=n, deform=deform, close_ends=False)
    p.lathe([(r_fill, fill_z), (r_fill * 0.5, fill_z + 0.0003), (0.0, fill_z + 0.0004)], floor_m, n=n, deform=deform,
            close_ends=False)
    return r_fill


def level_spout(p, base, tip, radii, mat, hole, t=0.003, n=20, depth=None):
    """A straight pouring spout from `base` (buried in the vessel) to `tip`, its mouth cut level as on a teapot and
    rolled over by a half round t thick, the inside going down `depth` to a floor of `hole`. It is turned in a
    sheared frame whose level rings are its true round sections tilted, so the mouth is a level ellipse; `radii` are
    [(f, r)]: the round radius r at the share f of the way up."""
    b, e = Vector(base), Vector(tip)
    d = e - b
    h = d.z
    th = math.atan2(math.hypot(d.x, d.y), h)
    M = (Matrix.Translation(b) @ Matrix.Rotation(math.atan2(d.y, d.x), 4, 'Z')
         @ Matrix(((1.0, 0.0, math.tan(th), 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0)))
         @ Matrix.Diagonal((1 / math.cos(th), 1.0, 1.0, 1.0)))
    curve = spline([(r, f * h) for f, r in radii], 3)
    re = curve[-1][0]
    depth = depth or re * 2.0
    prof = [(0.0, -0.003), (curve[0][0] * 0.7, -0.002)] + curve
    prof += [(re - t / 2 + t / 2 * math.cos(a), h + t / 2 * math.sin(a)) for a in
             (math.radians(v) for v in (30, 60, 90, 120, 150, 180))]
    prof += [(re - t, h - depth * f) for f in (0.35, 0.7, 1.0)]
    p.lathe(prof, mat, n=n, M=M, close_ends=False)
    p.lathe([(re - t, h - depth), (0.0, h - depth - 0.0005)], hole, n=n, M=M, close_ends=False)


def tea_cup(p, at, rim_r, h, foot_r, fill, fill_z, foot_h=0.007, t=0.005, n=48, lean=1.0, shelf=1.1, mat='Celadon',
            lip=None, rings=7, inner=10):
    """A small round cup or bowl on a foot ring at `at`: a foot with soft edges, a belly that leaves the foot almost
    level and turns up into a lip rolled over by a half round t thick, the inside following the wall down to the
    drink (`fill`) at fill_z, which closes it. `lean` > 1 keeps the belly slimmer low down; `lip` colours the rolled
    lip; `rings` and `inner` are the rings up the outside and down the inside (fewer for a tighter budget)."""
    rb, zb = foot_r * shelf, foot_h + 0.0015
    prof = cup_outline(rim_r, h, foot_r, foot_h, t, lean, shelf, rings)
    cx, cz = rim_r - t / 2, h - t / 2
    rim = [(cx + t / 2 * math.cos(a), cz + t / 2 * math.sin(a)) for a in
           ((0.0, 0.6, 1.2, 1.57, 1.95, 2.55, 3.14) if rings >= 7 else (0.0, 0.8, 1.57, 2.35, 3.14))]
    if lip:   # the rolled lip in its own colour
        p.lathe(rim, lip, n=n, M=Matrix.Translation((at[0], at[1], 0.0)), close_ends=False)
        p.lathe(prof, mat, n=n, M=Matrix.Translation((at[0], at[1], 0.0)), close_ends=False)
        prof = [rim[-1]]
    else:
        prof += rim[1:]
    inside = [(rb + (rim_r - rb) * math.sin(th) ** lean - t, zb + (h - t / 2 - zb) * (1 - math.cos(th)))
              for th in (math.pi / 2 * i / inner for i in range(inner, -1, -1))]
    rf = inside[-1][0]
    for (r0, z0), (r1, z1) in zip(inside, inside[1:]):   # down the inside to the drink
        if z1 <= fill_z:
            rf = r0 + (r1 - r0) * (fill_z - z0) / (z1 - z0)
            prof.append((rf, fill_z))
            break
        prof.append((r1, z1))
    M = Matrix.Translation((at[0], at[1], 0.0))
    p.lathe(prof, mat, n=n, M=M, close_ends=False)
    p.lathe([(foot_r * 0.78, 0.004), (foot_r * 0.4, 0.0058), (0.0, 0.006)], mat, n=n, M=M, close_ends=False)
    p.lathe([(rf, fill_z), (rf * 0.5, fill_z + 0.0004), (0.0, fill_z + 0.0005)], fill, n=n, M=M, close_ends=False)


def clear_spot(outer, axis, cup, x, y, gap=0.0015):
    """Where a cup with the outline `cup` [(r, z)] can stand at x without touching a turned vessel of outline `outer`
    whose axis at height z is at axis(z): y, or as much further forward (-y) as it takes."""
    for r, z in cup:
        need = r + belly(outer, z) + gap
        dx = x - axis(z)
        if need > abs(dx):
            y = min(y, -math.sqrt(need * need - dx * dx))
    return y


def centred(p):
    """Moves the whole item so that the middle of its footprint is at the origin (the pivot)."""
    p.bm.verts.ensure_lookup_table()
    xs = [v.co.x for v in p.bm.verts]
    ys = [v.co.y for v in p.bm.verts]
    d = (-(min(xs) + max(xs)) / 2, -(min(ys) + max(ys)) / 2)
    moved(p, 0, Matrix.Translation((*d, 0.0)))
    log(f'centred by {d[0]:.4f}, {d[1]:.4f}')


def salt(col):
    """盐 as the art has it: a squat cream-glazed jar, its rolled collar wide open, heaped with coarse salt, a short
    wooden scoop sunk in the salt at the right with its paddle handle leaning out over the rim."""
    p = Part()
    R = 0.07   # the jar's widest radius
    outer = [(R * r, R * z) for r, z in ((0.782, 0.0), (0.805, 0.116), (0.936, 0.233), (0.983, 0.349), (1.0, 0.465),
                                         (0.952, 0.582), (0.79, 0.69), (0.847, 0.79), (0.809, 0.931))]
    fz = 0.05
    rin = shell(p, outer, 0.006, fz, 'Jar', 'Salt', n=48, per=3)
    top = R * 0.931

    def lumps(q):   # the coarse crystals as a lumpy surface
        rr = math.hypot(q.x, q.y)
        a = math.atan2(q.y, q.x)
        return Vector((q.x, q.y, q.z + 0.0016 * math.sin(a * 7 + rr * 260) * math.cos(rr * 330) * min(1.0, max(0.0, rr / 0.012 - 0.6))))
    p.lathe([(rin, fz + 0.0005)] + [(rin * f, top + 0.013 - 0.016 * f * f) for f in (0.85, 0.7, 0.55, 0.4, 0.25, 0.1)]
            + [(0.0, top + 0.013)], 'Salt', n=48, close_ends=False, deform=lumps)   # the heap, over the lip in the middle
    rnd = random.Random(3)
    with p.soft():
        for k in range(6):   # a few big crystals at the front
            a = -1.1 - 0.35 * k + rnd.uniform(-0.15, 0.15)
            d = rin * rnd.uniform(0.35, 0.75)
            p.box((d * math.cos(a), d * math.sin(a), top + 0.011 - 0.016 * (d / rin) ** 2), (0.011, 0.01, 0.007), 'Salt',
                  rot=rnd.uniform(0, 3))
    with p.soft():   # the scoop's round bowl, sunk in the salt at the right
        S = Matrix.Translation((0.03, 0.004, top + 0.002)) @ Matrix.Rotation(0.4, 4, 'Z') @ Matrix.Rotation(-0.3, 4, 'Y')
        p.lathe([(0.0, -0.008), (0.012, -0.007), (0.019, -0.003), (0.021, 0.002), (0.018, 0.003), (0.011, -0.002),
                 (0.0, -0.003)], 'LightWood', n=12, M=S @ Matrix.Diagonal((1.25, 1.0, 1.0, 1.0)), close_ends=False)
    paddle(p, (0.042, 0.006, top + 0.006), (0.071, 0.015, top + 0.034), 0.011, 0.019, 0.007, 'LightWood',
           up=(-0.6, -0.25, 0.75))
    return p.finish('SM_salt', col, sharp=None)

def oil(col):
    """油 as the art has it: a round ochre-glazed jug on a foot ring, a narrow neck flaring to a wide mouth with a
    pinched pouring lip to the left, golden oil showing inside, a thick loop handle to the right."""
    p = Part()
    T = TUNE.get('oil', {})
    R = 0.07   # the belly's radius
    fh = T.get('fh', 0.012)   # how much taller the foot ring is than it was first drawn
    outer = [(R * r, R * z + (fh if i >= 2 else fh * 0.6 if i else 0.0)) for i, (r, z) in enumerate(
        ((0.64, 0.0), (0.68, 0.05), (0.85, 0.11), (0.97, 0.25), (1.0, 0.45), (0.92, 0.66), (0.7, 0.85), (0.57, 1.03),
         (0.55, 1.21), (0.55, 1.38), (0.6, 1.53), (0.548, 1.729)))]
    top = outer[-1][1]
    lip, lz = T.get('lip', 0.35), T.get('lz', 0.002)

    def spout(q):   # the left of the rim pulled out and up into a pouring lip
        a = math.atan2(q.y, q.x)
        u = min(1.0, max(0.0, (q.z - (top - 0.009)) / 0.009))
        f = u * u * (3 - 2 * u) * math.exp(-((abs(a) - math.pi) / 0.32) ** 2)
        return Vector((q.x * (1 + lip * f), q.y * (1 - 0.3 * f), q.z + lz * f))
    shell(p, outer, 0.006, top - 0.02, 'Clay', 'Oil', n=56, per=3, deform=spout)
    # the handle: a thick loop from under the rim out to the right and down onto the shoulder
    hx, hz = T.get('hx', -0.004), T.get('hz', 0.0)
    loop(p, [(x + (hx if i else 0.0), z + (hz if i else 0.0)) for i, (x, z) in enumerate(
        ((0.039, top - 0.013), (0.056, top - 0.003), (0.075, top - 0.01), (0.084, top - 0.03), (0.082, top - 0.05),
         (0.075, top - 0.064), (0.062, top - 0.071)))], T.get('hr', 0.009), 'Clay')
    return p.finish('SM_oil', col, sharp=None)

PALETTE.update({
    'SauerCrock':   ('#c27852', '#94523a'),   # 酸菜's terracotta crock, mottled darker where it fired
    'SauerLip':     ('#dc9c74', '#b07454'),   # its thick rolled lip, lighter
    'SauerCrockIn': ('#a55c3c', '#733d27'),   # the inside of its mouth
    'SauerFill':    ('#6a5a1c', '#4a3e12'),   # the cabbage deep in the mouth, in shadow
    'SauerPale':    ('#efca5c', '#cba13a'),   # the pale yellow pickled leaves
    'SauerDark':    ('#7a641c', '#55450e'),   # their dark olive ruffled edges and the dark leaves
})
GLOSS.update({'SauerCrock': 0.08, 'SauerLip': 0.12, 'SauerCrockIn': 0.05, 'SauerFill': 0.0, 'SauerPale': 0.35,
              'SauerDark': 0.3})
VIVID.update({'SauerCrock': 0.5, 'SauerLip': 0.45, 'SauerCrockIn': 0.5, 'SauerFill': 0.5, 'SauerPale': 0.75,
              'SauerDark': 0.6})
VTINT.update(dict.fromkeys(('SauerCrock', 'SauerLip', 'SauerCrockIn', 'SauerPale', 'SauerDark'), 1.0))
DETAIL.update({
    'SauerCrock':   ('food_clay', 10, '#7a3a24', 0.45, 0.35),
    'SauerLip':     ('food_clay', 10, '#9a5a3a', 0.35, 0.25),
    'SauerCrockIn': ('food_clay', 10, '#6a3220', 0.35, 0.25),
    'SauerPale':    ('food_veins', 16, '#c49a32', 0.3, 0.2),
    'SauerDark':    ('food_veins', 16, '#4a3a08', 0.3, 0.2),
})


def sauerkraut(col):
    """酸菜 traced from its art (trace_sauerkraut.py writes traced_sauerkraut.json): a round terracotta crock with a
    short neck and a thick rolled lip, mottled darker where it fired, packed to the lip with pickled cabbage, pale
    yellow leaves and dark olive ones folded in among each other, one big leaf hanging over the lip down the right
    side; every leaf follows its outline in the art and takes the art's colours, the crock its colours too."""
    from .sacks import TRACED, ArtMaps, art_colour, traced_pack
    p = Part()
    A = ArtMaps(TRACED['sauerkraut'])
    c = A.data['crock']
    sy = c['sy']
    vessel(p, [tuple(q) for q in c['outer']], c['t'], c['fz'], ('SauerCrock', 'SauerLip', 'SauerCrockIn', 'SauerFill'),
           n=40, per=2, turn=7, deform=lambda q: Vector((q.x, q.y * sy, q.z)))   # as the trace's
    traced_pack(p, TRACED['sauerkraut'], ink='#4a3008', maps=A)
    art_colour(p, A, 0, ('SauerCrock', 'SauerLip', 'SauerCrockIn'), 0.75)
    return p.finish('SM_sauerkraut', col, sharp=None)


def stock(col):
    """肉汤备料 as the art has it: a wide terracotta casserole with a flared rim and two lug handles, full of golden
    broth with drops of fat on it, its domed lid with a knob leaning up against the right side."""
    p = Part()
    R = 0.1   # the rim's radius
    outer = [(R * r, R * z) for r, z in ((0.42, 0.0), (0.72, 0.17), (0.9, 0.34), (0.975, 0.52), (0.95, 0.7), (0.92, 0.86),
                                         (1.0, 0.98), (0.99, 1.035))]
    top = R * 1.035
    fz = top - 0.02
    shell(p, outer, 0.009, fz, 'ClayPot', 'Broth', n=56, per=3)
    for (x, y, r) in ((-0.045, -0.03, 0.013), (-0.025, -0.04, 0.008), (-0.06, -0.012, 0.007), (0.03, 0.0, 0.009),
                      (0.045, -0.02, 0.007), (0.01, 0.03, 0.006), (-0.012, 0.005, 0.005), (0.055, 0.02, 0.005),
                      (-0.035, 0.03, 0.005), (0.02, -0.045, 0.006)):   # drops of fat on the broth
        pool(p, r, fz + 0.0012, 'Oil', at=(x, y), n=16, wobble=0.05, seed=int(x * 1000), depth=0.001)
    with p.soft():
        for sgn in (-1, 1):   # lug handles under the rim
            p.blob((sgn * (R * 0.98 + 0.012), 0.0, top - 0.017), 1.0, 'ClayPot', squash=(0.02, 0.026, 0.011), segs=(8, 4))
    # the lid, propped against the right side: its low edge on the table, leaning on the rim (3 mm clear of it), the
    # dome and its big knob turned right and a little up towards the viewer; the pose that best fits the art's outline
    rl = 0.085
    n = Vector((0.912, -0.168, 0.373)).normalized()
    L = Matrix.Translation((0.12, 0.0336, 0.0809)) @ n.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    p.lathe([(0.0, 0.003), (rl - 0.012, 0.004), (rl - 0.004, 0.0), (rl, 0.003), (rl - 0.002, 0.008), (rl - 0.014, 0.017),
             (rl * 0.55, 0.025), (0.02, 0.028), (0.016, 0.03), (0.017, 0.036), (0.021, 0.042), (0.019, 0.047), (0.01, 0.049),
             (0.0, 0.049)], 'ClayPot', n=48, M=L, close_ends=False)   # underside, flange, dome and knob in one turn
    return p.finish('SM_stock', col, sharp=None)

def rock(p, c, size, mat, seed, rot=0.0):
    """A lump of rock sugar: a box with every corner pushed about, as a soft cage, so it comes out a chunky rounded
    stone with broad soft facets."""
    rnd = random.Random(seed)
    tmp = bmesh.new()
    bmesh.ops.create_cube(tmp, size=1.0)
    bmesh.ops.subdivide_edges(tmp, edges=tmp.edges[:], cuts=1, use_grid_fill=True)
    T = Matrix.Translation(Vector(c)) @ Matrix.Rotation(rot, 4, 'Z') @ Matrix.Diagonal((*size, 1.0))
    for v in tmp.verts:
        v.co = T @ (v.co * rnd.uniform(0.82, 1.12) + Vector((rnd.uniform(-0.08, 0.08) for _ in range(3))))
    with p.soft():
        p._commit(tmp, mat)


def sugar(col):
    """糖 as the art has it: a cream bowl with a scalloped rim on a foot ring, heaped with coarse white sugar, two big
    golden lumps of rock sugar at the right, a wooden spoon in the sugar at the left, its handle up over the rim."""
    p = Part()
    T = TUNE.get('sugar', {})
    R = 0.08   # the rim's radius
    fh = T.get('fh', 0.012)   # how much taller the foot ring is than it was first drawn
    outer = [(R * r, R * z + (fh if i >= 2 else fh * 0.6 if i else 0.0)) for i, (r, z) in enumerate(
        ((0.45, 0.0), (0.47, 0.06), (0.5, 0.1), (0.62, 0.15), (0.767, 0.245), (0.853, 0.367), (0.901, 0.489),
         (0.925, 0.612), (1.0, 0.734)))]
    top = outer[-1][1]
    fz = top - 0.012
    rin = shell(p, outer, 0.0055, fz, 'Jar', 'SugarWhite', n=60, per=3, deform=lobed(6, 0.035, R * 0.85, R * 0.98))

    def lumps(q):   # the crystals as a lumpy surface
        a, rr = math.atan2(q.y, q.x), math.hypot(q.x, q.y)
        return Vector((q.x, q.y, q.z + 0.0018 * math.sin(a * 8 + rr * 300) * math.cos(rr * 380) * min(1.0, max(0.0, rr / 0.012 - 0.6))))
    p.lathe([(rin, fz + 0.0005)] + [(rin * f, top + 0.009 - 0.012 * f * f) for f in (0.85, 0.7, 0.55, 0.4, 0.25, 0.1)]
            + [(0.0, top + 0.009)], 'SugarWhite', n=48, close_ends=False, deform=lumps)   # the heap
    rnd = random.Random(6)
    with p.soft():
        for k in range(10):   # a few coarse crystals standing out of it
            a = rnd.uniform(0, 2 * math.pi)
            d = rin * rnd.uniform(0.2, 0.8)
            p.box((d * math.cos(a), d * math.sin(a), top + 0.008 - 0.012 * (d / rin) ** 2), (0.008, 0.008, 0.006), 'SugarWhite',
                  rot=rnd.uniform(0, 3))
    rock(p, (0.034, 0.024, top + 0.012), (0.042, 0.034, 0.03), 'RockSugar', seed=1, rot=0.5)   # rock sugar, at the back
    rock(p, (0.043, -0.012, top + 0.006), (0.04, 0.032, 0.026), 'RockSugar', seed=2, rot=-0.3)   # and in front of it
    with p.soft():   # the spoon's oval bowl in the sugar at the left
        sb = T.get('sb', 1.3)
        S = Matrix.Translation((-0.02, 0.006, top + 0.006)) @ Matrix.Rotation(-0.6, 4, 'Z') @ Matrix.Rotation(0.25, 4, 'Y')
        p.lathe([(0.0, -0.007), (0.011, -0.006), (0.017, -0.003), (0.019, 0.002), (0.016, 0.003), (0.01, -0.002),
                 (0.0, -0.003)], 'LightWood', n=12, M=S @ Matrix.Diagonal((1.3 * sb, sb, 1.0, 1.0)), close_ends=False)
    ha, hb, hw = T.get('ha', (-0.036, 0.016, 0.012)), T.get('hb', (-0.088, 0.036, 0.064)), T.get('hw', (0.012, 0.022))
    paddle(p, (ha[0], ha[1], top + ha[2]), (hb[0], hb[1], top + hb[2]), hw[0], hw[1], 0.007, 'LightWood',
           up=(0.5, -0.4, 0.75))
    return p.finish('SM_sugar', col, sharp=None)

def vinegar(col):
    """醋 as the art has it: a squat round jug in a dark brown glaze on a wide foot, its narrow neck flaring into a
    thick collar that holds a mushroom-shaped stopper, a tapering spout rising from its left shoulder, and in front
    of it at the left a celadon cup of dark vinegar."""
    p = Part()
    outer = [(0.0602, 0.0), (0.0642, 0.0175), (0.0698, 0.04), (0.066, 0.058), (0.056, 0.073), (0.042, 0.088),
             (0.031, 0.105), (0.0303, 0.116), (0.0335, 0.127), (0.0398, 0.134), (0.039, 0.141), (0.0376, 0.1445)]
    top, t = 0.1445, 0.0045
    fz = top - 0.016
    shell(p, outer, t, fz, 'VinegarGlaze', 'JugMouth', n=48, per=2)
    p.bm.verts.ensure_lookup_table()
    for f in p.bm.faces:   # the inside of the collar in the dark of the mouth
        if all(v.co.z > fz - 1e-4 and math.hypot(v.co.x, v.co.y) < 0.0376 - t + 1e-4 for v in f.verts):
            f.material_index = p._mi('JugMouth')
    lip = top + t / 2
    p.lathe([(0.0, fz + 0.001), (0.019, fz + 0.001), (0.022, fz + 0.004), (0.0225, lip - 0.005), (0.0262, lip - 0.0015),
             (0.0298, lip + 0.0008), (0.0318, lip + 0.0042), (0.032, lip + 0.0068), (0.0306, lip + 0.0089),
             (0.026, lip + 0.0099), (0.013, lip + 0.0104), (0.0, lip + 0.0105)], 'JugStopper', n=48,
            close_ends=False)   # the stopper: a plug down the collar under a cap with a rounded edge and a low dome

    def axis(z):   # the art draws the jug leaning a little to the left, most of it low down
        return belly([(0.0005, 0.0), (-0.003, 0.039), (-0.0068, 0.117), (-0.0068, 1.0)], z)
    p.bm.verts.ensure_lookup_table()
    for v in p.bm.verts:
        v.co.x += axis(v.co.z)
    level_spout(p, (-0.0385, -0.016, 0.08), (-0.0801, -0.012, 0.134),
                [(0.0, 0.023), (0.3, 0.0175), (0.65, 0.0137), (0.9, 0.0119), (1.0, 0.0123)], 'VinegarGlaze',
                'VinegarDark')
    # the cup: the art draws it from lower down than 35 degrees, so that at the art's spot it would cut into the
    # belly; it stands as far back as it can with its rim clear of the jug, a little taller and slimmer low down
    # than drawn, so that its outline still covers the art's
    rim, h, foot, lean, x = 0.054, 0.06, 0.018, 2.2, -0.0862
    y = clear_spot(outer, axis, cup_outline(rim, h, foot, lean=lean), x, -0.0693)
    tea_cup(p, (x, y), rim, h, foot, 'VinegarDark', 0.041, lean=lean, lip='CeladonLip')
    centred(p)
    return p.finish('SM_vinegar', col, sharp=None)


WINE_OUTER = [(0.0302, 0.0072), (0.044, 0.0085), (0.0515, 0.015), (0.0575, 0.0276), (0.0635, 0.0414), (0.0693, 0.0552),
              (0.072, 0.069), (0.0668, 0.0828), (0.059, 0.0966), (0.0497, 0.1104), (0.036, 0.1242), (0.0256, 0.1381),
              (0.0214, 0.1519), (0.0207, 0.1657), (0.0213, 0.1795), (0.0248, 0.1933), (0.0285, 0.2071), (0.0435, 0.2279)]
WINE_HANDLE = [(0.0215, 0.1915), (0.0255, 0.187), (0.025, 0.18), (0.0205, 0.1758), (0.0158, 0.1785), (0.0145, 0.188),
               (0.016, 0.1975), (0.0215, 0.202), (0.029, 0.2),
               (0.0363, 0.1935), (0.0447, 0.193), (0.0532, 0.1897), (0.0606, 0.1863), (0.0649, 0.1794),
               (0.0685, 0.1704), (0.0716, 0.16), (0.0722, 0.1471), (0.0718, 0.1342), (0.0701, 0.1239), (0.0675, 0.1149),
               (0.0637, 0.1072), (0.0626, 0.1048), (0.0647, 0.0945), (0.0689, 0.0881), (0.071, 0.0803), (0.0689, 0.0752)]
WINE_HANDLE_R = [0.0025, 0.0028, 0.0031, 0.0034, 0.0037, 0.004, 0.0045, 0.0051, 0.0058,
                 0.0064, 0.0064, 0.0064, 0.0063, 0.0062, 0.0061, 0.006, 0.006, 0.006, 0.006, 0.006, 0.006, 0.0058, 0.0054,
                 0.0049, 0.0043, 0.0037]
WINE_SPOUT = [(-0.043, 0.075), (-0.066, 0.094), (-0.066, 0.125), (-0.068, 0.159), (-0.076, 0.187), (-0.092, 0.203)]
WINE_SPOUT_R = [0.019, 0.018, 0.017, 0.0135, 0.0105, 0.0075]


def wine(col):
    """酒 as the art has it, turned true: a pear-shaped celadon ewer on a foot ring, its narrow neck flaring into a wide
    mouth of four even lobes with a cream rolled lip, rising a little at the sides and dipping front and back, a long
    S-curved spout rising from the left of the belly and a strap handle with scrolled ends on the right, the two
    opposite each other in one plane through the axis; in front of it at the left a small celadon cup of pale wine."""
    p = Part()
    T = TUNE.get('wine', {})
    outer = [tuple(q) for q in T.get('outer', WINE_OUTER)]
    top = outer[-1][1]
    fr = T.get('fr', 0.0297)   # the foot ring
    foot = [(0.0, 0.0035), (fr * 0.724, 0.0035), (fr * 0.822, 0.0005), (fr * 0.896, 0.0), (fr * 0.96, 0.0008),
            (fr, 0.0035)]
    curve = smoothed(spline(outer, 4), T.get('smooth', 8))
    m4, mz2, mzn, mw, mz0 = T.get('m4', 0.07), T.get('mz2', 0.006), T.get('mzn', 0.003), T.get('mw', 0.32), \
        T.get('mz0', 0.178)

    def mouth(q):   # four even lobes (towards the spout, the handle, the front and the back) parted by narrow, soft
        a = math.atan2(q.y, q.x)                       # notches, the rim rising a little over the spout and the handle
        f = min(1.0, max(0.0, (q.z - mz0) / (top - mz0))) ** 2   # and dipping at the notches: symmetric both ways
        notch = sum(math.exp(-((((a - math.pi / 4 - j * math.pi / 2) + math.pi) % (2 * math.pi) - math.pi) / mw) ** 2)
                    for j in range(4))
        k = 1 + f * m4 * (1 - 2 * notch)
        return Vector((q.x * k, q.y * k, q.z + f * (mz2 * math.cos(2 * a) - mzn * notch)))
    vessel(p, curve, 0.0045, top - 0.036, ('Celadon', 'CeladonLip', 'Celadon', 'CeladonDeep'), n=48, per=1,
           deform=mouth, foot=foot, turn=T.get('turn', 5.0))
    sx = T.get('sx', -0.002)   # the axis, upright, where the art's leaning ewer stands at its belly
    moved(p, 0, Matrix.Translation((sx, 0.0, 0.0)))

    def axis(z):
        return sx

    def drawn(z):   # how far left of upright the art draws the ewer at height z: the handle and spout were read off it
        return belly([(0.0016, 0.0), (-0.0017, 0.069), (-0.008, 0.165), (-0.0096, 0.225), (-0.0096, 1.0)], z)
    # the handle: from the eye of a round scroll on the neck under the mouth (thin there, so the curl reads), out over
    # the top, round and down to the belly, ending in a small curl
    hx, hz = T.get('hx', 0.0), T.get('hz', 0.0)
    path = [(x + hx + sx - drawn(z), 0.0, z + hz) for x, z in T.get('handle', WINE_HANDLE)]
    strap(p, path, [r * T.get('hk', 1.1) for r in WINE_HANDLE_R], 'Celadon', squash=T.get('hsq', 1.55), n=10, per=2)
    # the spout: out of the left of the belly opposite the handle, up along it, then away to the upper left; it was
    # read off the art 12 mm in front of this plane, so it comes down 8 mm to show where the art has it
    spout_pts = T.get('spout', WINE_SPOUT)
    dx = sx - drawn(spout_pts[0][1])
    ewer_spout(p, [(x + dx, 0.0, z - 0.012 * math.tan(ART_EL)) for x, z in spout_pts], T.get('spr', WINE_SPOUT_R), 'Celadon',
               'CeladonDeep', t=0.0025, n=14, steps=T.get('sp_steps', 16), level=T.get('sp_level', 0.35))
    # the cup at the art's spot, pushed forward just far enough to clear the belly
    cs = T.get('cs', 1.0)
    rim, h, foot_r, cl, x = T.get('crim', 0.04) * cs, T.get('ch', 0.0505) * cs, T.get('cfoot', 0.0147) * cs, \
        T.get('clean', 1.1), T.get('cx', -0.105)
    y = clear_spot(outer, axis, cup_outline(rim, h, foot_r, lean=cl), x, T.get('cy', -0.0202))
    tea_cup(p, (x, y), rim, h, foot_r, 'RiceWine', h - 0.012, lean=cl, lip='CeladonLip', rings=4, inner=6)
    centred(p)
    return p.finish('SM_wine', col, sharp=None)


def cut(prof, levels, gap=0.0006):
    """Splits a profile [(r, z)] that goes up into pieces at the heights `levels` (the cut points interpolated, the
    profile's own points closer than `gap` to a cut dropped), each piece starting where the last one ended."""
    lv = sorted(levels)
    prof = [q for q in prof if all(abs(q[1] - z) >= gap for z in lv)]
    pieces, cur = [], [prof[0]]
    for a, b in zip(prof, prof[1:]):
        while lv and a[1] < lv[0] < b[1]:
            f = (lv[0] - a[1]) / (b[1] - a[1])
            c = (a[0] + (b[0] - a[0]) * f, lv.pop(0))
            cur.append(c)
            pieces.append(cur)
            cur = [c]
        cur.append(b)
    pieces.append(cur)
    return pieces


# the contour bottle's outside fitted to the art: radii every 6 mm up from the foot to the neck
COLA_R = [0.0316, 0.0340, 0.0333, 0.0314, 0.0298, 0.0287, 0.0281, 0.0282, 0.0291, 0.0310, 0.0327, 0.0336, 0.0336,
          0.0336, 0.0334, 0.0326, 0.0324, 0.0324, 0.0320, 0.0299, 0.0276, 0.0252, 0.0228, 0.0209, 0.0193, 0.0178]


def cola(col):
    """可乐 as the art has it: a clear glass contour bottle, open, full of dark cola up into its shoulder with a line of
    foam on top, a plain red band round its belly, a thick rolled lip over a bead at the mouth; its crimped red crown
    cap lies beside it at the right, tipped up at its left so that its top faces right. The glass is see-through
    (GLASS: Unity's WatercolorGlass) over the cola inside it, which glows amber at its sides where the light comes
    through, with bubbles rising in it."""
    p = Part()
    T = TUNE.get('cola', {})
    rs = [r * T.get('rk', 1.0) for r in COLA_R]
    foot = [(0.0, 0.0028), (0.018, 0.0015), (rs[0] * 0.84, 0.0), (rs[0] * 0.97, 0.0011), (rs[1] * 0.985, 0.0042)]
    body = [(r, 0.006 * i) for i, r in enumerate(rs) if i >= 2 and i not in (12, 14, 16, 20, 22)]
    top = T.get('top', 0.1835)
    neck = [(0.0168, 0.156), (0.0168, 0.1605), (0.0182, 0.1638), (0.0184, 0.1668), (0.017, 0.17),
            (0.0186, 0.1728), (0.0195, 0.1762), (0.0195, 0.1796), (0.0191, top - 0.0016)]
    lip = [(0.0186, top - 0.0006), (0.0172, top - 0.0001), (0.0156, top), (0.0142, top - 0.0004), (0.0134, top - 0.0016),
           (0.0131, top - 0.0034)]
    inside = [(0.0128, top - 0.009), (0.0126, top - 0.015), (0.0126, top - 0.019)]
    z_glass, z_lo, z_hi = T.get('z_glass', 0.014), T.get('z_lo', 0.08), T.get('z_hi', 0.11)
    z_liq, foam = T.get('z_liq', 0.147), 0.0035
    outside = foot + body + neck
    # the glass: the whole outside up over the lip and down inside the neck to the cola, both see-through
    p.lathe(outside + lip, 'ColaGlass', n=44, close_ends=False)
    p.lathe(lip[-1:] + inside + [(0.0124, z_liq + 0.004)], 'ColaGlassDeep', n=48, close_ends=False)
    # the red band round its belly, just outside the glass
    band = cut(outside, [z_lo, z_hi])[1]   # its edges tucked into the glass, so no gap shows its inside
    band = [band[0]] + [(r + 0.0006, z) for r, z in band[1:-1]] + [band[-1]] if len(band) > 2 else band
    p.lathe(band, 'LabelRed', n=44, close_ends=False)
    # the cola inside, the glass's thickness in from it, a line of foam on top, its surface seen down the neck
    wall = 0.0018
    inner = [(belly(outside, z) - wall, z)   # every other ring of the outside: it is seen through the glass
             for z in [z_glass] + [z for _, z in outside if z_glass < z < z_liq][1::2] + [z_liq]]
    liquid, top_foam = cut(inner, [z_liq - foam])
    f0 = len(p.bm.faces)
    p.lathe([(0.0, z_glass)] + liquid, 'ColaLiquid', n=40, close_ends=False)
    p.lathe(top_foam + [(0.0, z_liq + 0.0004)], 'ColaFoam', n=40, close_ends=False)
    view = Vector((0.0, -math.cos(ART_EL), math.sin(ART_EL)))
    # amber where it is seen edge-on and low down (the light through more of it), deep red-brown facing the eye
    p.tint(f0, lambda q, n: ('#e0702a', min(0.95, 0.95 * max(0.0, (0.62 - abs(n.dot(view))) / 0.4)
                                       + 0.35 * max(0.0, 1 - (q.z - z_glass) / 0.05))), mats=['ColaLiquid'])
    # the crown cap: a low domed top in a shining rolled edge over a darker skirt pleated into 21 round flutes,
    # deeper towards its rolled edge, and the inside; tipped up at the back left, its lowest point on the table
    rt, rb, h = T.get('cap_rt', 0.0143), T.get('cap_rb', 0.0165), T.get('cap_h', 0.0083)

    def crimp(q):   # the flutes, and the edge between them lifted into notches, so that it ends in round lobes
        f = min(1.0, max(0.0, (h - 0.0024 - q.z) / (h - 0.0024))) ** 0.7
        a = (21 * math.atan2(q.y, q.x) + math.pi) % (2 * math.pi) - math.pi   # 0 down the middle of a flute
        k = 1 + T.get('fl', 0.06) * f * math.cos(a)
        lift = T.get('sc', 0.0016) * (1 - math.sqrt(max(0.0, 1 - (a / math.pi) ** 2))) * max(0.0, 1 - q.z / 0.003)
        return Vector((q.x * k, q.y * k, q.z + lift))
    R = Matrix.Rotation(T.get('cap_turn', -0.53), 4, 'Z') @ Matrix.Rotation(T.get('cap_tilt', 0.306), 4, 'Y')
    top_c = [(0.0, h + 0.0004), (rt * 0.5, h + 0.0003), (rt - 0.0022, h)]
    rim = [top_c[-1], (rt - 0.0004, h - 0.0006), (rt + 0.0002, h - 0.0022)]
    skirt = [rim[-1], (rb - 0.0006, 0.0018), (rb - 0.0002, 0.0005), (rb - 0.0011, 0.0), (rb - 0.0016, 0.0016),
             (rt - 0.0008, h - 0.0026), (0.0, h - 0.0012)]
    n0 = len(p.bm.verts)
    for prof, mat in ((top_c, 'LabelRed'), (rim, 'CapRim'), (skirt, 'CapSkirt')):   # traced out from the middle and
        p.lathe(prof[::-1], mat, n=168, deform=crimp, close_ends=False)   # down, so turned round to face outwards
    moved(p, n0, R)
    drop_to(p, n0, 0.0)
    at = Vector((T.get('cap_x', 0.0505), T.get('cap_y', 0.002), 0.0))
    moved(p, n0, Matrix.Translation(at))
    for _ in range(3):   # nudged straight out from the bottle until it stands 1.5 mm clear of it
        p.bm.verts.ensure_lookup_table()
        gap = min(math.hypot(v.co.x, v.co.y) - belly(outside, v.co.z) for v in p.bm.verts[n0:])
        if gap >= 0.0015:
            break
        moved(p, n0, Matrix.Translation(at.normalized() * (0.0015 - gap + 0.0001)))
    return p.finish('SM_cola', col, sharp=None)


ITEMS = [('salt', salt),
         ('oil', oil),
         ('sauerkraut', sauerkraut),
         ('stock', stock),
         ('sugar', sugar),
         ('vinegar', vinegar),
         ('wine', wine),
         ('cola', cola)]
