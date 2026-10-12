"""面米与干货：袋装、纸包、筐装: flour, rice, rice_prep, pickle_base, seafood, starch, pancake, egg."""
import json
import math
import os
import random

import bmesh
from mathutils import Matrix, Vector

from .core import *  # noqa: F401,F403

PALETTE.update({
    'ToastSpot':  ('#e8b469', '#cc934a'),   # the light golden speckles on 薄饼
    'ClothLeaf':  ('#a9b993', '#87986f'),   # the sage leaves printed on the 米料 bundle
    'TwinePale':  ('#ece2bb', '#cbbd8e'),   # the pale twine of the 干贝海味包
    'CornHusk':   ('#b0b65d', '#7e8746'),   # the husk leaves printed on the 玉米淀粉 sack
    'CornGroove': ('#f4a430', '#d6861d'),   # the darker lines between the kernels of its corn cob
})
GLOSS.update({'ToastSpot': 0.0, 'TwinePale': 0.0, 'CornHusk': 0.0, 'CornGroove': 0.0})
VIVID.update({'TwinePale': 0.5, 'CornHusk': 0.75})


# ---------------------------------------------------------------- traced from the art (trace_packs.py and the traces)
# The packed ingredients traced from their art (trace_pancake.py, …): each piece a surface over its outline in the
# art, so that from the art's camera it covers exactly what the art paints, coloured from the art itself (a colour
# map with the art's broad light and shade taken out, for the shader puts its own back), the art's crisp marks
# painted on, its ink line round it; what holds them (trays, tubs, paper, crocks) turned or lofted to the art's
# outline and tinted from the art where the art's camera sees them.

TRACED = {k: os.path.join(os.path.dirname(__file__), f'traced_{k}.json')
          for k in ('pancake', 'sauerkraut', 'seafood', 'pickle_base', 'rice_prep')}


class ArtMaps:
    """A trace's camera and maps (trace_packs.write): where the art shows a point, its paint channels and colours."""

    def __init__(self, path):
        import numpy as np
        self.data = json.load(open(path, encoding='utf-8'))
        z = np.load(path.replace('.json', '_paint.npz'))
        self.paint = z['paint'].astype(np.float32) / 255
        self.colour = z['colour'].astype(np.float32) / 255
        cam = self.data['camera']
        self.sc = self.data['paint_scale']
        self.k, self.u0, self.v0 = cam['k'], cam['u0'], cam['v0']
        self.se, self.ce = math.sin(math.radians(cam['el'])), math.cos(math.radians(cam['el']))
        self.toward = Vector((0.0, -self.ce, self.se))   # towards the camera the art was drawn from

    def px(self, q):
        return Vector((self.u0 + self.k * q.x, self.v0 - self.k * (q.y * self.se + q.z * self.ce)))

    def at(self, arr, q):
        c = self.px(q) * self.sc
        H, W = arr.shape[:2]
        x0, y0 = min(max(int(c.x), 0), W - 2), min(max(int(c.y), 0), H - 2)
        tx, ty = min(max(c.x - x0, 0.0), 1.0), min(max(c.y - y0, 0.0), 1.0)
        g = arr[y0:y0 + 2, x0:x0 + 2]
        return (g[0, 0] * (1 - tx) + g[0, 1] * tx) * (1 - ty) + (g[1, 0] * (1 - tx) + g[1, 1] * tx) * ty

    def hex_at(self, q):
        return '#%02x%02x%02x' % tuple(int(min(255, max(0, round(float(x) * 255)))) for x in self.at(self.colour, q))


def traced_pack(p, path, ink='#5a3a20', skip=(), maps=None):
    """The pieces traced from the art (a trace_packs json): each one's surface in its material, the art's crisp
    marks painted on face by face (the trace put vertices along their edges), the art's colours tinted in (its
    `tint` weight) and its ink line round it (full to ink[0] art pixels in from its outline, gone by ink[1] more).
    Returns the maps, for art_colour()."""
    A = maps or ArtMaps(path)
    for piece in A.data['pieces']:
        if piece['name'] in skip:
            continue
        f0 = len(p.bm.faces)
        vs = [p.bm.verts.new(Vector(q)) for q in piece['verts']]
        mi = p._mi(piece['mat'])
        for a, b, c in piece['tris']:
            p.bm.faces.new((vs[a], vs[b], vs[c])).material_index = mi
        p.bm.faces.ensure_lookup_table()
        for ch, mat in piece['paint']:
            mi_ = p._mi(mat)
            for face in p.bm.faces[f0:]:
                if A.at(A.paint[..., ch], face.calc_center_median()) > 0.5:
                    face.material_index = mi_
        rim = [A.px(Vector(q)) for q in piece['verts'][:piece['rim']]]
        segs = [(a, b - a) for a, b in zip(rim, rim[1:] + rim[:1])]
        full, gone = piece['ink']
        w_col = piece['tint']

        def field(q, n, segs=segs, full=full, gone=gone, w_col=w_col):
            best = (A.hex_at(q), w_col) if w_col > 0 else None
            if gone > 0:
                c = A.px(q)
                d = min((c - (a + ab * min(max((c - a).dot(ab) / max(ab.length_squared, 1e-9), 0.0), 1.0))).length
                        for a, ab in segs)
                w = 0.9 * (1 - min(max((d - full) / gone, 0.0), 1.0))
                if w > 0.02 and (best is None or w >= best[1]):
                    best = (ink, w)
            return best
        p.tint(f0, field, piece.get('tint_mats', [piece['mat']]))   # painted marks keep their own colour
    return A


def keep_inside(p, f0, mats, axis=(0.0, 0.0), margin=0.002):
    """The food added since there were f0 faces kept inside what holds it (the faces in `mats`): any vertex beyond the
    container's inside, along a level line out from the axis, is drawn back in along that line to `margin` inside it,
    so that nothing pokes through a wall or a wrap seen from any side (the art's view sees such vertices, if at all,
    behind the food in front of them)."""
    from mathutils.bvhtree import BVHTree
    ids = {p.mats.index(m) for m in mats if m in p.mats}
    p.bm.faces.ensure_lookup_table()
    tmp = bmesh.new()
    vm = {}
    for f in p.bm.faces:
        if f.material_index in ids:
            try:
                tmp.faces.new([vm.setdefault(v, tmp.verts.new(v.co)) for v in f.verts])
            except ValueError:
                pass
    tree = BVHTree.FromBMesh(tmp)
    food = {v for f in p.bm.faces[f0:] if f.material_index not in ids for v in f.verts}
    n = 0
    for v in food:
        o = Vector((axis[0], axis[1], v.co.z))
        d = v.co - o
        dist = d.length
        if dist < 1e-6:
            continue
        d /= dist
        hit = tree.ray_cast(o, d, dist + margin)[0]
        if hit is not None and (hit - o).length - margin < dist:
            v.co = o + d * max((hit - o).length - margin, 0.0)
            n += 1
    tmp.free()
    log(f'kept inside its holder: {n} vertices')


def art_colour(p, A, f0=0, mats=None, weight=0.8):
    """Tints the faces added since f0 (those in `mats`) with the art's colours wherever the art's camera sees them
    (nothing of the model between them and it); what it can't see keeps its own colour."""
    from mathutils.bvhtree import BVHTree
    p.bm.normal_update()
    tree = BVHTree.FromBMesh(p.bm)

    def field(q, n):
        hit = tree.ray_cast(q + A.toward * 0.0003 + n * 0.0002, A.toward)
        return None if hit[0] is not None else (A.hex_at(q), weight)
    p.tint(f0, field, mats)


def round_basket(p, r, h, base, t=0.0065, bulge=1.0, rings=1, wraps=8, wrap='WickerBind', n=48, at=(0.0, 0.0),
                 floor=0.01, wrap_w=0.012, a0=0.0):
    """A woven bamboo basket or tray, smooth and round: a lathe from the base (its edge rounded) out to a hoop of
    tube radius t whose outside is at r + t, height h at the top; `bulge` < 1 rounds the wall like a bowl. The
    hoop is bound with `wraps` rounded bands wrap_w wide, the first at angle a0. Returns the inside floor height."""
    x, y = at
    prof = [(0.0, 0.0), (base - 0.004, 0.0), (base - 0.001, 0.0012), (base, 0.004)]
    for i in range(1, rings + 1):
        f = i / (rings + 1)
        prof.append((base + (r - base) * f ** bulge, 0.004 + (h - t * 2 - 0.004) * f))
    cx, cz = r, h - t
    prof += [(cx + t * math.cos(math.radians(a)), cz + t * math.sin(math.radians(a))) for a in range(-90, 211, 30)]
    prof += [(cx - t * 1.15, cz - t * 1.25), (base * 0.92 + (r - base) * 0.05, floor + 0.004), (base * 0.85, floor),
             (0.0, floor)]
    p.lathe(prof, 'Wicker', n=n, close_ends=False, M=Matrix.Translation((x, y, 0.0)))
    for j in range(wraps):
        a = a0 + 2 * math.pi * j / wraps
        p.blob((x + cx * math.cos(a), y + cx * math.sin(a), cz), 1.0, wrap, squash=(t * 1.35, wrap_w / 2, t * 1.35),
               segs=(12, 6), rot=a)
    return floor


def open_sack(p, prof, mat, fill, sx=1.0, n=48, seed=3, folds=0.03, corners=0.0, corner_z=0.06, corner_a=0.0,
              M=Matrix(), extra=None):
    """An open sack, soft and round: the lathe profile prof [(r, z)] runs up the outside, over its rolled rim and down
    the inside to the fill height, where `fill` closes it (the last point must be the fill ring); the section is
    stretched sx across, creased by gentle vertical folds, and below corner_z pushed out into pillowy corners at
    the left and right (turned corner_a from the x axis); `extra` shapes it first (a ruffled collar). Returns the
    deform, for things that must follow the cloth."""
    rnd = random.Random(seed)
    ph = [rnd.uniform(0, 2 * math.pi) for _ in range(4)]

    def cloth(v):
        if extra:
            v = extra(v)
        a = math.atan2(v.y, v.x)
        k = 1 + folds * (math.sin(5 * a + ph[0] + v.z * 9) * 0.6 + math.sin(9 * a + ph[1] - v.z * 14) * 0.4)
        c = corners * math.cos(a - corner_a) ** 6 * max(0.0, 1 - v.z / corner_z) ** 1.5 if corner_z else 0.0
        return Vector((v.x * (k + c) * sx, v.y * k, v.z))
    p.lathe(prof, mat, n=n, close_ends=False, deform=cloth, M=M)
    p.lathe([prof[-1], (0.0, prof[-1][1] + 0.0005)], fill, n=n, close_ends=False, deform=cloth, M=M)
    return cloth


def scoop(p, at, tip, width=0.06, length=0.1, mat='LightWood', knob=0.016):
    """A wooden flour scoop: a deep rounded scoop body at `at`, its open end down into what it is scooping, and a
    stout round handle rising to `tip` with a rounded knob; soft and rounded all over."""
    at, tip = Vector(at), Vector(tip)
    d = (tip - at).normalized()
    R = axes_to(d, (0.0, 0.0, 1.0)).to_3x3()
    with p.soft():
        p.blob((0, 0, 0), 1.0, mat, squash=(width * 0.38, width / 2, length / 2), segs=(10, 6),
               deform=lambda v: R @ Vector((v.x, v.y, v.z)) + at)
        neck = at + d * length * 0.45
        p.tube([neck, (neck + tip) / 2, tip], knob * 0.62, mat, sides=8)
        p.blob(tip, knob, mat, squash=(1.0, 1.0, 1.25), segs=(8, 4), deform=lambda v: R @ v)


def flour(col):
    """面粉 as the art has it: a squat burlap sack spreading into soft corners at the foot, its top rolled down into a
    wide band round a mound of flour, a wooden scoop standing in it at the back right."""
    p = Part()
    prof = [(0.0, 0.0), (0.1, 0.0), (0.122, 0.006), (0.136, 0.025), (0.138, 0.055), (0.128, 0.095), (0.118, 0.125),
            (0.121, 0.135), (0.13, 0.162), (0.132, 0.196), (0.126, 0.224), (0.116, 0.238), (0.105, 0.236),
            (0.098, 0.224), (0.096, 0.21)]
    open_sack(p, prof, 'Burlap', 'Flour', sx=1.2, seed=3, folds=0.025, corners=0.2, corner_z=0.075, corner_a=-0.25)
    heap(p, (0.0, 0.0), 0.097, 0.21, 0.04, 'Flour', n=48)
    scoop(p, (0.06, 0.02, 0.236), (0.133, 0.05, 0.297), width=0.068, length=0.105, knob=0.024)
    return p.finish('SM_flour', col, sharp=None)


def frames(pts):
    """Rotation-minimising frames (tangent, normal, binormal) along the polyline pts: they turn with the path and
    never flip, however it bends or turns upright."""
    n = len(pts)
    T = [(pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized() for i in range(n)]
    ref = Vector((0.0, 0.0, 1.0)) if abs(T[0].z) < 0.9 else Vector((1.0, 0.0, 0.0))
    N = (ref - T[0] * ref.dot(T[0])).normalized()
    out = []
    for i in range(n):
        if i:
            N = T[i - 1].rotation_difference(T[i]) @ N
            N = (N - T[i] * N.dot(T[i])).normalized()
        out.append((T[i], N, T[i].cross(N)))
    return out


def soft_tube(p, pts, r, mat, sides=6, ends=True):
    """A round tube of radius r along the polyline pts with rotation-minimising rings (it never twists), closed at
    both ends by rounded tips (or flat caps where ends=False, for ends buried in something)."""
    pts = [Vector(q) for q in pts]
    F = frames(pts)
    tmp = bmesh.new()
    rings = [[tmp.verts.new(q + r * (math.cos(a) * N + math.sin(a) * B)) for a in (2 * math.pi * k / sides for k in range(sides))]
             for q, (T, N, B) in zip(pts, F)]
    if ends:   # a rounded tip at each end: a smaller ring a little beyond, then a point
        T0, N0, B0 = F[0]
        T1, N1, B1 = F[-1]
        rings.insert(0, [tmp.verts.new(pts[0] - T0 * r * 0.55 + 0.72 * r * (math.cos(a) * N0 + math.sin(a) * B0))
                         for a in (2 * math.pi * k / sides for k in range(sides))])
        rings.append([tmp.verts.new(pts[-1] + T1 * r * 0.55 + 0.72 * r * (math.cos(a) * N1 + math.sin(a) * B1))
                      for a in (2 * math.pi * k / sides for k in range(sides))])
    for ra, rb in zip(rings, rings[1:]):
        for k in range(sides):
            tmp.faces.new((ra[k], ra[(k + 1) % sides], rb[(k + 1) % sides], rb[k]))
    if ends:
        t0 = tmp.verts.new(pts[0] - F[0][0] * r * 0.92)
        t1 = tmp.verts.new(pts[-1] + F[-1][0] * r * 0.92)
        for k in range(sides):
            tmp.faces.new((t0, rings[0][(k + 1) % sides], rings[0][k]))
            tmp.faces.new((t1, rings[-1][k], rings[-1][(k + 1) % sides]))
    else:
        tmp.faces.new(list(reversed(rings[0])))
        tmp.faces.new(rings[-1])
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)


def rope(p, path, r, mat='Twine', twist=110.0, sides=6, closed=False, step=None, ends=True):
    """A twisted rope along the polyline `path`: two strands of radius r winding round each other, `twist` radians a
    metre, resampled every `step` (by default r * 1.6); `closed` for a loop. Its frames never flip, so the path may
    turn any way; the strands end in rounded tips."""
    pts = [Vector(q) for q in path]
    if closed:
        pts = pts + pts[:1]
    step = step or r * 1.6
    acc = [0.0]
    for a, b in zip(pts, pts[1:]):
        acc.append(acc[-1] + (b - a).length)
    n = max(2, round(acc[-1] / step))
    dense, j = [], 0
    for i in range(n + 1):
        t = acc[-1] * i / n
        while j < len(pts) - 2 and acc[j + 1] < t:
            j += 1
        f = (t - acc[j]) / max(acc[j + 1] - acc[j], 1e-9)
        dense.append((pts[j].lerp(pts[j + 1], min(1.0, f)), t))
    F = frames([q for q, _ in dense])
    for strand in (0.0, math.pi):
        line = [q + (N * math.cos(strand + t * twist) + B * math.sin(strand + t * twist)) * r * 0.85
                for (q, t), (T, N, B) in zip(dense, F)]
        soft_tube(p, line, r, mat, sides=sides, ends=ends and not closed)


def grain(p, c, length, yaw, tilt=0.0, mat='RiceGrain', width=0.4, thick=0.32, segs=(8, 4)):
    """One big rice grain as the art draws them: a smooth plump oval `length` long, width and thick as shares of it,
    its points bunched towards the two ends so that they come out round, not pointed."""
    R = Matrix.Rotation(yaw, 3, 'Z') @ Matrix.Rotation(tilt, 3, 'Y')
    hl, hw = length / 2, length * width / 2

    def shape(v):
        u, w = v.x / hl, v.y / hw
        th, rho = math.atan2(w, u), math.hypot(u, w)
        th -= (0.262 if segs[0] <= 8 else 0.2) * math.sin(2 * th)   # with 8 sides: the points at 0, 30, 90, 150 degrees
        return R @ Vector((rho * math.cos(th) * hl, rho * math.sin(th) * hw, v.z))
    p.blob(c, 1.0, mat, squash=(hl, hw, length * thick / 2), segs=segs, deform=shape)


# ---------------------------------------------------------------- lofted cloth and paper, fitted to the art
# A sack or a parcel is lofted through a few control rings read off the art (the same number of points in each,
# going round anticlockwise seen from above): smooth Catmull-Rom curves run round each ring and from ring to ring,
# so the cloth comes out soft and round with no facets, and its outline follows the art's point for point.

def _cr(p0, p1, p2, p3, t):
    return 0.5 * (2 * p1 + (p2 - p0) * t + (2 * p0 - 5 * p1 + 4 * p2 - p3) * t * t + (3 * p1 - p0 - 3 * p2 + p3) * t ** 3)


def loop_curve(ctrl, per):
    """A smooth closed curve through the points ctrl, `per` points a span."""
    m = len(ctrl)
    return [_cr(ctrl[i - 1], ctrl[i], ctrl[(i + 1) % m], ctrl[(i + 2) % m], k / per) for i in range(m) for k in range(per)]


def path_curve(ctrl, per):
    """A smooth open curve through the points ctrl, `per` points a span (or one count per span), ending at the last."""
    P = [ctrl[0]] + list(ctrl) + [ctrl[-1]]
    out = []
    for i in range(1, len(P) - 2):
        k_n = per[i - 1] if isinstance(per, (list, tuple)) else per
        out += [_cr(P[i - 1], P[i], P[i + 1], P[i + 2], k / k_n) for k in range(k_n)]
    return out + [ctrl[-1]]


def skin(p, rings, mat):
    """Faces between consecutive rings (lists of points of one length, or one point for a closed end), as a lathe
    makes them: with the rings anticlockwise seen from above, the faces face out on the way up the outside."""
    tmp = bmesh.new()
    vs = [[tmp.verts.new(q) for q in ([r] if isinstance(r, Vector) else r)] for r in rings]
    n = max(len(r) for r in vs)
    for ra, rb in zip(vs, vs[1:]):
        for k in range(n):
            if len(ra) == 1:
                tmp.faces.new((ra[0], rb[(k + 1) % n], rb[k]))
            elif len(rb) == 1:
                tmp.faces.new((ra[k], ra[(k + 1) % n], rb[0]))
            else:
                tmp.faces.new((ra[k], ra[(k + 1) % n], rb[(k + 1) % n], rb[k]))
    p._commit(tmp, mat)


def loft(sections, per_ring, per_z):
    """The rings of a smooth loft through the control rings `sections` (each a list of Vectors, all one length)."""
    m = len(sections[0])
    cols = [path_curve([s[j] for s in sections], per_z) for j in range(m)]
    return [loop_curve([cols[j][i] for j in range(m)], per_ring) for i in range(len(cols[0]))]


def ring(pts):
    return [Vector(q) for q in pts]


def pulled(sec, centre, d, dz=0.0):
    """The control ring sec moved d in towards centre (x, y) and dz up: the inside of a rim, a lip."""
    c = Vector((centre[0], centre[1], 0.0))
    out = []
    for q in sec:
        h = Vector((q.x - c.x, q.y - c.y, 0.0))
        out.append(q - h.normalized() * d + Vector((0.0, 0.0, dz)))
    return out


def shrunk(sec, centre, f, z):
    """The control ring sec drawn in to a share f of its size about centre, at height z."""
    return [Vector((centre[0] + (q.x - centre[0]) * f, centre[1] + (q.y - centre[1]) * f, z)) for q in sec]


def twisted_rope(p, path, r, mat='Twine', pitch=0.03, sides=5, per_turn=6):
    """A rope of two strands of radius r twisting round each other along the smooth polyline `path`, a full turn
    every `pitch` metres: cheaper than rope() for long runs."""
    rope(p, path, r, mat, twist=2 * math.pi / pitch, sides=sides, step=pitch / per_turn)


def polar_fn(pairs):
    """A smooth periodic radius function of the angle (radians) through pairs [(degrees, radius)]."""
    pairs = sorted(pairs)
    A = [math.radians(d) for d, _ in pairs]
    R = [r for _, r in pairs]
    m = len(pairs)

    def f(a):
        a = a % (2 * math.pi)
        aa = a if a >= A[0] else a + 2 * math.pi
        for i in range(m):
            a0 = A[i]
            a1 = A[i + 1] if i < m - 1 else A[0] + 2 * math.pi
            if a0 <= aa <= a1:
                return _cr(R[i - 1], R[i], R[(i + 1) % m], R[(i + 2) % m], (aa - a0) / (a1 - a0))
        return R[0]
    return f


def polar_ring(centre, z, f, angles, dz=None):
    """Points at the given angles (radians) round centre (x, y) at height z (plus dz(angle)), f(angle) out."""
    return [Vector((centre[0] + f(a) * math.cos(a), centre[1] + f(a) * math.sin(a), z + (dz(a) if dz else 0.0)))
            for a in angles]


def crystal(p, c, size, mat='Salt', rot=0.0):
    """A coarse salt crystal: a soft little cube."""
    with p.soft():
        p.box(c, (size, size * 0.9, size * 0.8), mat, rot=rot)


def from_art(X, Y, z, S, X0, Y0):
    """The model point (x, y) at height z that the art's pixel (X, Y) shows, for art drawn S pixels a metre with the
    model's origin at the pixel (X0, Y0), seen from the art view (in front, 35 degrees up)."""
    return (X - X0) / S, (Y0 - Y - S * math.cos(ART_EL) * z) / (S * math.sin(ART_EL))


def rice(col):
    """米 as the art has it: a squat burlap sack seen a little from its left, the foot spreading into a soft corner at
    the left and a rounder one at the front right, tied round the neck with a thin twisted rope knotted at the front
    right, its two ends hanging down the right side; above the rope the cloth flares into a wide collar with a rolled
    rim, dipping at the front, round a heap of big rice grains; five big grains spilled at the front left."""
    p = Part()
    # control rings read off the art: 12 points every 30 degrees from the right, anticlockwise seen from above
    B1 = ring([(0.158, -0.035, 0.015), (0.140, 0.075, 0.015), (0.090, 0.148, 0.015), (0.0, 0.168, 0.015),
               (-0.095, 0.152, 0.015), (-0.145, 0.100, 0.015), (-0.1945, 0.022, 0.016), (-0.1617, -0.0374, 0.015),
               (-0.080, -0.081, 0.015), (0.0, -0.111, 0.015), (0.095, -0.134, 0.015), (0.147, -0.131, 0.015)])
    B2 = ring([(0.152, -0.02, 0.045), (0.140, 0.08, 0.045), (0.088, 0.150, 0.045), (0.0, 0.168, 0.045),
               (-0.093, 0.154, 0.045), (-0.142, 0.098, 0.045), (-0.170, 0.030, 0.045), (-0.147, -0.032, 0.045),
               (-0.075, -0.071, 0.045), (0.0, -0.100, 0.045), (0.092, -0.124, 0.045), (0.146, -0.108, 0.045)])
    B3 = ring([(0.150, 0.0, 0.09), (0.142, 0.085, 0.09), (0.085, 0.150, 0.09), (0.0, 0.165, 0.09),
               (-0.090, 0.155, 0.09), (-0.145, 0.100, 0.09), (-0.175, 0.035, 0.09), (-0.142, -0.025, 0.09),
               (-0.073, -0.065, 0.09), (0.0, -0.088, 0.09), (0.085, -0.100, 0.09), (0.140, -0.075, 0.09)])
    B4 = ring([(0.158, 0.012, 0.115), (0.142, 0.083, 0.115), (0.082, 0.142, 0.115), (0.002, 0.156, 0.115),
               (-0.081, 0.144, 0.115), (-0.136, 0.098, 0.115), (-0.164, 0.040, 0.115), (-0.136, -0.015, 0.115),
               (-0.073, -0.054, 0.115), (0.002, -0.072, 0.115), (0.082, -0.071, 0.115), (0.140, -0.040, 0.115)])
    NZ = 0.135   # the neck, cinched by the rope
    N = ring([(0.144, 0.020, NZ), (0.132, 0.080, NZ), (0.078, 0.133, NZ), (0.003, 0.147, NZ), (-0.072, 0.133, NZ),
              (-0.124, 0.0965, NZ), (-0.146, 0.046, NZ), (-0.124, -0.0045, NZ), (-0.072, -0.0415, NZ),
              (0.003, -0.055, NZ), (0.0785, -0.0415, NZ), (0.128, -0.010, NZ)])
    C1 = ring([(0.173, 0.025, 0.17), (0.150, 0.11, 0.17), (0.085, 0.165, 0.17), (0.003, 0.178, 0.17),
               (-0.08, 0.163, 0.17), (-0.14, 0.11, 0.17), (-0.160, 0.040, 0.17), (-0.14, -0.012, 0.17),
               (-0.08, -0.048, 0.17), (0.0, -0.072, 0.17), (0.08, -0.048, 0.17), (0.150, 0.0, 0.17)])
    # the top of the rolled rim, every 15 degrees: its back half traced from the art's outline, its front from the
    # line where the rim meets the rice
    R = ring([(0.177, 0.012, 0.198), (0.166, 0.060, 0.203), (0.151, 0.097, 0.206), (0.124, 0.161, 0.212),
              (0.088, 0.182, 0.218), (0.047, 0.205, 0.227), (0.002, 0.203, 0.225), (-0.043, 0.196, 0.220),
              (-0.084, 0.158, 0.214), (-0.120, 0.148, 0.208), (-0.147, 0.110, 0.205), (-0.164, 0.080, 0.205),
              (-0.171, 0.046, 0.206), (-0.164, 0.032, 0.207), (-0.148, 0.022, 0.209), (-0.120, 0.009, 0.212),
              (-0.084, -0.032, 0.214), (-0.043, -0.078, 0.215), (0.002, -0.091, 0.215), (0.047, -0.076, 0.215),
              (0.088, -0.058, 0.214), (0.124, -0.014, 0.211), (0.145, -0.015, 0.205), (0.168, -0.005, 0.200)])
    B1, B2, B3, B4, N, C1 = (loop_curve(s, 2) for s in (B1, B2, B3, B4, N, C1))
    B1[11], B1[13] = Vector((-0.176, 0.062, 0.015)), Vector((-0.177, -0.008, 0.015))   # the left corner sticks out
    RC = (0.003, 0.055)   # the middle of the opening
    fz = 0.19             # where the rice meets the inside of the collar
    F0 = pulled([c.lerp(r_, (fz - c.z) / (r_.z - c.z)) for c, r_ in zip(C1, R)], RC, 0.012)
    base_c = (-0.005, 0.03)
    cloth_secs = [shrunk(B1, base_c, 0.5, 0.0), shrunk(B1, base_c, 0.86, 0.0015), B1, B2, B3, B4, N, C1,
                  pulled(R, RC, -0.0015, -0.007), R, pulled(R, RC, 0.009, -0.003), pulled(R, RC, 0.012, -0.014), F0]
    rings = loft(cloth_secs, 2, [1, 1, 2, 2, 1, 1, 2, 2, 1, 1, 1, 1])
    rnd = random.Random(5)
    ph = [rnd.uniform(0, 2 * math.pi) for _ in range(3)]
    for rg in rings[2:-5]:   # soft creases up the cloth, strongest on the body and the collar
        for q in rg:
            a = math.atan2(q.y - 0.04, q.x)
            w = math.sin(math.pi * min(1.0, q.z / 0.21)) ** 0.7
            k = 0.0025 * w * (math.sin(5 * a + ph[0] + q.z * 30) * 0.6 + math.sin(8 * a + ph[1] - q.z * 45) * 0.4)
            q.x += math.cos(a) * k
            q.y += math.sin(a) * k
    skin(p, [Vector((base_c[0], base_c[1], 0.0))] + rings, 'Burlap')
    # the heap of rice, from where it meets the cloth up to its top
    zs = [(0.0, 0.252), (0.15, 0.250), (0.42, 0.241), (0.72, 0.221), (1.0, fz)]

    def lumpy(sec, amt):
        return [q + Vector((0.0, 0.0, amt * math.sin(3 * math.atan2(q.y - RC[1], q.x - RC[0]) + 1.1))) for q in sec]
    heap_secs = [F0] + [lumpy(shrunk(F0, RC, s, z), 0.003) for s, z in reversed(zs[1:-1])]
    hrings = loft(heap_secs, 2, [1, 1, 1])
    skin(p, hrings + [Vector((RC[0], RC[1], zs[0][1]))], 'RiceGrain')
    edge = loop_curve(F0, 4)

    def heap_at(s, a):   # a point on the heap a share s of the way out from its middle, towards angle a
        e = min(edge, key=lambda q: abs(math.remainder(math.atan2(q.y - RC[1], q.x - RC[0]) - a, 2 * math.pi)))
        for (s0, z0), (s1, z1) in zip(zs, zs[1:]):
            if s0 <= s <= s1:
                z = z0 + (z1 - z0) * (s - s0) / (s1 - s0)
        return Vector((RC[0] + (e.x - RC[0]) * s, RC[1] + (e.y - RC[1]) * s, z))
    for k in range(60):   # big plump grains heaped all over
        s = 0.86 * math.sqrt((k + 0.5) / 60)
        a = k * 2.39996 + rnd.uniform(-0.2, 0.2)
        grain(p, heap_at(s, a) + Vector((0.0, 0.0, 0.005)), 0.035, rnd.uniform(0, math.pi), rnd.uniform(-0.3, 0.3),
              width=0.4, thick=0.34)
    # the rope round the neck, a little out from the cloth, knotted at the front right
    rr = 0.0036
    neck = loop_curve(N, 4)   # 96 points round the neck, from the right
    path = []
    for i, q in enumerate(neck):
        t = neck[(i + 1) % len(neck)] - neck[i - 1]
        out = Vector((t.y, -t.x, 0.0)).normalized()
        path.append(q + out * rr * 1.1)
    front = path[42:] + path[:3]    # from the left round the front and past the knot: in sight, twisted
    twisted_rope(p, front, rr, pitch=0.03, per_turn=5)
    soft_tube(p, path[0:47:3], rr * 1.6, 'Twine', sides=6)   # round the back, out of sight
    knot = Vector((0.127, -0.031, 0.133))
    p.blob(knot, 0.0125, 'Twine', squash=(1.0, 0.85, 1.15), segs=(10, 6), rot=math.radians(-36) + math.pi / 2)
    p.blob(knot + Vector((-0.009, -0.006, 0.007)), 0.0075, 'Twine', squash=(1.2, 0.8, 0.9), segs=(8, 4), rot=0.4)   # its loop
    re_ = 0.0052
    for end in ([(0.146, -0.034, 0.126), (0.1616, -0.035, 0.1162), (0.1759, -0.035, 0.0943), (0.1841, -0.035, 0.0745),
                 (0.1882, -0.035, 0.058), (0.190, -0.035, 0.051)],
                [(0.127, -0.045, 0.118), (0.1285, -0.06, 0.1108), (0.1397, -0.085, 0.0918), (0.1509, -0.095, 0.0668),
                 (0.1621, -0.1, 0.052)]):
        twisted_rope(p, [knot] + [Vector(e) for e in end], re_, pitch=0.03, per_turn=5)
    for (x, y, z, yaw, tilt, L) in ((-0.1878, -0.0379, 0.0065, -0.44, 0.0, 0.0435), (-0.1493, -0.052, 0.028, -0.47, 0.0, 0.038),
                                    (-0.1317, -0.062, 0.022, 0.30, 0.0, 0.039), (-0.1123, -0.082, 0.010, 0.79, -0.25, 0.05),
                                    (-0.0724, -0.1053, 0.0065, -0.23, 0.0, 0.0404)):   # spilled at the front left
        grain(p, (x, y, z), L, yaw, tilt, width=0.44, thick=0.3, segs=(12, 4))
    moved(p, 0, Matrix.Translation((0.005, -0.03, 0.0)))   # the middle of the foot to the origin
    return p.finish('SM_rice', col, sharp=None)


PALETTE.update({
    'MiTub':       ('#e4c07c', '#bf9552'),   # 米料备料's bamboo tub: broad strips woven round upright staves
    'MiTubRim':    ('#e8c27a', '#c29650'),   # its thick rim, one broad band of bamboo
    'MiTubIn':     ('#c9a060', '#a07a40'),   # inside, above the rice
    'MiWrap':      ('#b4b46a', '#8a8a46'),   # the green bindings round the rim
    'MiRice':      ('#fbf4e2', '#e6d6b2'),   # the heap of rice, grain on grain
    'MiRiceFill':  ('#d8c8a0', '#b8a47a'),   # the rice deep in the tub, in shadow
    'MiSpoon':     ('#d58a44', '#a8622c'),   # the wooden spoon
    'MiCloth':     ('#f1e9d6', '#cfc3a6'),   # the bundle's cloth, sage-tinted
    'MiLeafPrint': ('#a9b493', '#86916f'),   # the sage leaves printed on it
    'MiRope':      ('#c88a48', '#9e6630'),   # its twisted rope
})
GLOSS.update(dict.fromkeys(('MiTub', 'MiTubRim', 'MiTubIn', 'MiWrap', 'MiRice', 'MiRiceFill', 'MiCloth', 'MiLeafPrint',
                            'MiRope'), 0.0))
GLOSS['MiSpoon'] = 0.2
VIVID.update({'MiTub': 0.45, 'MiTubRim': 0.45, 'MiTubIn': 0.45, 'MiWrap': 0.5, 'MiRice': 0.3, 'MiRiceFill': 0.3,
              'MiSpoon': 0.6, 'MiCloth': 0.3, 'MiLeafPrint': 0.45, 'MiRope': 0.5})
VTINT.update(dict.fromkeys(('MiTub', 'MiTubRim', 'MiTubIn', 'MiWrap', 'MiRice', 'MiSpoon', 'MiCloth', 'MiRope'), 1.0))
DETAIL.update({
    'MiTub':    ('food_plait', 9, '#8a6428', 0.6, 0.5),
    'MiTubRim': ('food_wood', 22, '#9a7030', 0.4, 0.25),
    'MiTubIn':  ('food_plait', 9, '#7a5420', 0.5, 0.4),
    'MiWrap':   ('food_fiber', 30, '#7a7a3a', 0.35, 0.25),
    'MiRice':   ('food_grains', 15, '#c4ad84', 0.6, 0.9),
    'MiSpoon':  ('food_wood', 20, '#8a4a20', 0.45, 0.25),
    'MiCloth':  ('food_cloth', 30, '#a09878', 0.45, 0.3),
    'MiRope':   ('food_fiber', 40, '#7a4a20', 0.35, 0.2),
})
# the tub as the art draws it (trace_rice_prep.py reads it off the art): its foot, its wall up to the rim, the rim's
# band and its inside, the rice's level inside; stretched MI_SY front to back (the art is drawn from a little lower)
MI_TUB = dict(wall=[(0.1149, 0.0), (0.127, 0.02), (0.1313, 0.045), (0.133, 0.07)], z_rim=0.072, rim=0.138,
              top=0.0996, inside=0.114, fill=0.08, sy=0.862)   # the wall's radii fitted to the art's outline


def mi_tub(p, wraps=(), n=48):
    """米料备料's tall bamboo tub as the art draws it: a wall of broad strips woven round upright staves, a thick rim
    of one broad band of bamboo over it, bound with green wraps where the art has them (degrees round from the
    right), the rice's level closing it inside; stretched front to back as the art draws it."""
    T = MI_TUB
    S = Matrix.Diagonal((1.0, T['sy'], 1.0, 1.0))
    zr, r, top, ri, fz = T['z_rim'], T['rim'], T['top'], T['inside'], T['fill']
    f, w = T['wall'][0][0], T['wall'][-1][0]
    p.lathe([(0.0, 0.0), (f - 0.005, 0.0), (f - 0.0012, 0.0012), (f + 0.001, 0.005)] + [tuple(q) for q in T['wall'][1:]]
            + [(w + 0.002, zr)], 'MiTub', n=n, close_ends=False, M=S)
    rr = (r - ri) / 2
    prof = [(w + 0.002, zr), (r - 0.0015, zr + 0.0005), (r, zr + 0.003), (r, top - rr)]
    prof += [((r + ri) / 2 + rr * math.cos(math.radians(d)), top - rr + rr * math.sin(math.radians(d))) for d in (40, 90, 140)]
    prof += [(ri, top - rr)]
    p.lathe(prof, 'MiTubRim', n=n, close_ends=False, M=S)
    p.lathe([(ri, top - rr), (ri - 0.001, fz + 0.006), (ri - 0.004, fz)], 'MiTubIn', n=n, close_ends=False, M=S)
    p.lathe([(ri - 0.004, fz), (ri * 0.5, fz + 0.0004), (0.0, fz + 0.0005)], 'MiRiceFill', n=n, close_ends=False, M=S)
    for d in wraps:   # each a soft band round the rim, doubled as the art draws them
        a = math.radians(d)
        rc = (r + ri) / 2
        tang = math.atan2(T['sy'] * math.cos(a), -math.sin(a))
        for off in (-0.0065, 0.0065):
            c = Vector((rc * math.cos(a), T['sy'] * rc * math.sin(a), (zr + top) / 2)) +                 Vector((math.cos(tang), math.sin(tang), 0.0)) * off
            p.blob(c, 1.0, 'MiWrap', squash=(rr + 0.004, 0.0052, (top - zr) / 2 + 0.003), segs=(8, 4),
                   rot=tang - math.pi / 2)


def rice_prep(col):
    """米料备料 traced from its art (trace_rice_prep.py writes traced_rice_prep.json): a tall woven bamboo tub with a
    thick rim bound with green wraps, heaped with rice, a wooden spoon standing in it at the right; behind on the left
    a big cloth bundle printed with sage leaves, its top gathered into a puffy knot and tied with a twisted rope, its
    ends hanging. Every piece follows its outline in the art and takes the art's colours; the tub, its wraps and the
    rope coloured from the art."""
    p = Part()
    A = ArtMaps(TRACED['rice_prep'])
    mi_tub(p, A.data['wraps'])
    f0 = len(p.bm.faces)
    traced_pack(p, TRACED['rice_prep'], ink='#5a3a1a', maps=A, skip=('spoon', 'bundle'))
    keep_inside(p, f0, ('MiTub', 'MiTubRim', 'MiTubIn', 'MiWrap'), margin=0.0025)
    traced_pack(p, TRACED['rice_prep'], ink='#5a3a1a', maps=A, skip=('rice',))
    for path, r in A.data['ropes']:
        twisted_rope(p, [Vector(q) for q in path], r, 'MiRope', pitch=0.03, per_turn=4, sides=4)
    k0 = len(p.bm.verts)
    for c, r in A.data['knots']:
        p.blob(Vector(c), r, 'MiRope', squash=(1.0, 0.8, 1.0), segs=(8, 5))
    art_colour(p, A, 0, ('MiTub', 'MiTubRim', 'MiTubIn', 'MiWrap', 'MiRope'), 0.75)
    return p.finish('SM_rice_prep', col, sharp=None)


def ellipse_fn(a, b):
    """The radius towards angle t of an ellipse a across and b deep."""
    return lambda t: a * b / math.hypot(b * math.cos(t), a * math.sin(t))


def art_point(X, Y, y, S, X0, Y0):
    """The model point at depth y that shows at the art's pixel (X, Y) (art drawn as in from_art())."""
    return Vector(((X - X0) / S, y, (Y0 - Y - S * math.sin(ART_EL) * y) / (S * math.cos(ART_EL))))


def sheet(p, surf, nu, nv, thick, mat):
    """A closed sheet `thick` through along its normal over the surface surf(u, v) -> Vector for u, v in 0..1, sampled
    nu × nv times (a paper flap, standing or lying); built inside p.soft() its edges come out round."""
    tmp = bmesh.new()
    P = [[surf(i / (nu - 1), j / (nv - 1)) for j in range(nv)] for i in range(nu)]

    def nrm(i, j):
        du = P[min(i + 1, nu - 1)][j] - P[max(i - 1, 0)][j]
        dv = P[i][min(j + 1, nv - 1)] - P[i][max(j - 1, 0)]
        return du.cross(dv).normalized()
    top, bot = [[[tmp.verts.new(P[i][j] + nrm(i, j) * s * thick / 2) for j in range(nv)] for i in range(nu)]
                for s in (1, -1)]
    for i in range(nu - 1):
        for j in range(nv - 1):
            tmp.faces.new((top[i][j], top[i + 1][j], top[i + 1][j + 1], top[i][j + 1]))
            tmp.faces.new((bot[i][j], bot[i][j + 1], bot[i + 1][j + 1], bot[i + 1][j]))
    rim = ([(i, 0) for i in range(nu)] + [(nu - 1, j) for j in range(1, nv)] + [(i, nv - 1) for i in range(nu - 2, -1, -1)]
           + [(0, j) for j in range(nv - 2, 0, -1)])
    for (i0, j0), (i1, j1) in zip(rim, rim[1:] + rim[:1]):
        tmp.faces.new((top[i0][j0], top[i1][j1], bot[i1][j1], bot[i0][j0]))
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)


def ellipse_fn(a, b):
    """The radius towards angle t of an ellipse a across and b deep."""
    return lambda t: a * b / math.hypot(b * math.cos(t), a * math.sin(t))


def art_point(X, Y, y, S, X0, Y0):
    """The model point at depth y that shows at the art's pixel (X, Y) (art drawn as in from_art())."""
    return Vector(((X - X0) / S, y, (Y0 - Y - S * math.sin(ART_EL) * y) / (S * math.cos(ART_EL))))


def dome(p, edge, apex, mat, rings=((0.75, 0.55), (0.45, 0.86), (0.15, 0.985)), lumps=None):
    """A heap closing the ring `edge` (contents meeting the inside of a sack or parcel), rising to `apex`: each ring
    a share s of the way out from the apex, a share f of the way up from the edge, raised by lumps(x, y) inside the
    edge if given; returns height(x, y) over it."""
    lump = lumps or (lambda x, y: 0.0)
    secs = [edge] + [[Vector((apex.x + (q.x - apex.x) * s, apex.y + (q.y - apex.y) * s, q.z + (apex.z - q.z) * f))
                      for q in edge] for s, f in rings]
    for sec in secs[1:]:
        for q in sec:
            q.z += lump(q.x, q.y)
    skin(p, loft(secs, 2, [1] * len(rings)) + [apex + Vector((0.0, 0.0, lump(apex.x, apex.y)))], mat)
    dense = loop_curve(edge, 2)
    prof = [(0.0, 1.0)] + [(s, f) for s, f in reversed(rings)] + [(1.0, 0.0), (9.0, 0.0)]

    def height(x, y):
        a = math.atan2(y - apex.y, x - apex.x)
        e = min(dense, key=lambda q: abs(math.remainder(math.atan2(q.y - apex.y, q.x - apex.x) - a, 2 * math.pi)))
        s = math.hypot(x - apex.x, y - apex.y) / max(1e-6, math.hypot(e.x - apex.x, e.y - apex.y))
        for (s0, f0), (s1, f1) in zip(prof, prof[1:]):
            if s0 <= s <= s1:
                f = f0 + (f1 - f0) * (s - s0) / (s1 - s0)
                return e.z + (apex.z - e.z) * f + (lump(x, y) * min(1.0, (1.0 - s) / 0.25) if s < 1.0 else 0.0)
        return e.z
    return height


def pickle_bag(p, paper='YanPaper', heap='YanHeap', twine='YanTwine'):
    """盐渍辅料包's parcel as the art has it: crumpled kraft paper gathered round the heap of pickles (closed by
    `heap`) and tied at the neck with thin twine, a bow with one loop and two hanging ends at the front right;
    above the twine the thick paper opens into big rounded flaps, the biggest pointing out to the left, one
    standing up at the back, one out to the right, a front flap folded down over the neck; below the twine the bag
    spreads into a soft fold at the left. Its rim traced from the art (`A`: the art pixel and the depth chosen)."""
    S, X0, Y0 = 3620.0, 650.0, 965.0   # how the art is drawn: pixels a metre, and where the origin shows

    def A(X, Y, y):
        return art_point(X, Y, y, S, X0, Y0)
    # the paper's top edge, anticlockwise from the right flap's tip: the outline traced from the art, its depth chosen
    rim = [A(1170, 510, -0.02), A(1056, 425, 0.01), A(1019, 375, 0.035), A(998, 300, 0.05), A(962, 222, 0.07),
           A(848, 232, 0.085), A(754, 175, 0.10), A(679, 150, 0.105), A(530, 115, 0.105), A(462, 175, 0.10),
           A(400, 250, 0.09), A(370, 310, 0.075), A(245, 350, 0.055), A(126, 400, 0.035), A(40, 462, 0.015),
           A(103, 525, -0.005), A(167, 600, -0.025), A(215, 650, -0.05), A(330, 620, -0.085), A(550, 690, -0.11),
           A(800, 740, -0.115), A(1020, 670, -0.09), A(1120, 650, -0.07), A(1114, 600, -0.055), A(1139, 550, -0.035)]
    ang = [math.atan2(q.y, q.x) for q in rim]
    base = polar_fn([(165, 0.128), (178, 0.143), (189.3, 0.127), (203.8, 0.115), (214.4, 0.1118), (222.7, 0.1108), (231.7, 0.1111),
                     (244.6, 0.1099), (262.9, 0.1121), (279.4, 0.1186), (298.5, 0.1129), (316.4, 0.109),
                     (341.3, 0.1216), (350, 0.133), (20, 0.125), (60, 0.112), (90, 0.112), (120, 0.113), (150, 0.118)])
    side = polar_fn([(0, 0.117), (45, 0.112), (90, 0.108), (135, 0.11), (160, 0.118), (178, 0.13), (200, 0.118),
                     (240, 0.108), (270, 0.106), (300, 0.108), (330, 0.113)])
    bc = (0.0, 0.005)
    B1 = polar_ring(bc, 0.012, base, ang)
    B2 = polar_ring(bc, 0.04, lambda t: min(base(t), side(t)), ang)
    B3 = polar_ring((0.0, 0.0), 0.075, polar_fn([(0, 0.114), (90, 0.106), (180, 0.1155), (270, 0.104)]), ang)
    N = polar_ring((0.0, 0.0), 0.105, ellipse_fn(0.112, 0.098), ang)
    U1 = polar_ring((0.0, 0.0), 0.128, ellipse_fn(0.118, 0.104), ang)
    t = 0.004   # the paper's thickness
    # where the pickles meet the inside of the paper: traced from the art round the back, hidden at the front
    F0 = polar_ring((0.0, 0.0), 0.0, polar_fn([(0, 0.1077), (39, 0.1106), (82, 0.099), (134.6, 0.0989), (180, 0.0994),
                                                (225, 0.1026), (270, 0.095), (315, 0.1026)]), ang,
                    dz=polar_fn([(0, 0.137), (39, 0.1315), (82, 0.158), (134.6, 0.152), (180, 0.150), (225, 0.135),
                                 (270, 0.13), (315, 0.13)]))
    Ri = pulled(rim, (0.0, 0.0), t, -t * 0.8)
    secs = [shrunk(B1, bc, 0.5, 0.0), shrunk(B1, bc, 0.88, 0.001), B1, B2, B3, N, U1,
            pulled(rim, (0.0, 0.0), -t / 2, -t * 0.8), rim, Ri, [a.lerp(b, 0.5) for a, b in zip(Ri, F0)], F0]
    rings = loft(secs, 2, [1, 1, 2, 2, 1, 1, 2, 1, 1, 1, 1])
    rnd = random.Random(7)
    ph = [rnd.uniform(0, 2 * math.pi) for _ in range(4)]
    for rg in rings[3:-5]:   # the paper crumpled into soft folds, deepest on the front of the bag below the twine
        for q in rg:
            a = math.atan2(q.y, q.x)
            amp = 0.0075 if q.z < 0.085 else 0.0075 - 0.006 * min(1.0, (q.z - 0.085) / 0.04)
            amp *= 0.3 + 0.7 * abs(math.sin(a))
            k = amp * (math.sin(6 * a + ph[0] + q.z * 25) * 0.65 + math.sin(10 * a + ph[1] - q.z * 50) * 0.35)
            q.x += math.cos(a) * k
            q.y += math.sin(a) * k
    skin(p, [Vector((bc[0], bc[1], 0.0))] + rings, paper)
    # the front flap, folded over the rim and hanging down the front of the neck under the twine

    WALL = [(0.08, 0.116, 0.1), (0.105, 0.112, 0.098), (0.128, 0.118, 0.104), (0.17, 0.122, 0.111)]

    def wall_y(x, z):   # the front of the paper between the neck and the rim
        z = min(max(z, WALL[0][0]), WALL[-1][0])
        for (z0, a0, b0), (z1, a1, b1) in zip(WALL, WALL[1:]):
            if z0 <= z <= z1:
                f = (z - z0) / (z1 - z0)
                a_, b_ = a0 + (a1 - a0) * f, b0 + (b1 - b0) * f
                return -b_ * math.sqrt(max(0.0, 1 - (x / a_) ** 2))
    top = [A(360, 707, -0.105), A(500, 683, -0.112), A(650, 712, -0.116), A(800, 745, -0.115), A(887, 775, -0.108)]

    edge_top = path_curve(top, 4)

    def flap(u, v):   # u across, v down: a trapezoid narrowing to the twine, its top left corner peeling out
        q = edge_top[min(16, round(u * 16))]
        z = q.z + 0.003 - (q.z + 0.003 - 0.097) * v
        x = q.x + (-0.058 + 0.104 * u - q.x) * v ** 1.3
        peel = 0.008 * (1 - u) ** 2 * (1 - v) ** 2
        return Vector((x, wall_y(x, z) - 0.0045 - 0.003 * math.sin(math.pi * u) * (1 - v) - peel, z + peel * 0.5))
    with p.soft():
        sheet(p, flap, 6, 4, 0.0035, paper)
    # the heap of pickles closing the paper
    dome(p, F0, Vector((0.0, 0.045, 0.194)), heap)
    # the twine round the neck, a bow at the front right: one loop out to the right and two hanging ends
    tw = 0.0024
    TA, TB, TZ = 0.112 + 0.0055, 0.111, 0.105

    def neck(deg):
        a = math.radians(deg)
        return Vector((TA * math.cos(a), TB * math.sin(a), TZ))
    twisted_rope(p, [neck(d) for d in range(160, 345, 4)], tw, twine, pitch=0.04, per_turn=3, sides=4)
    soft_tube(p, [neck(d) for d in range(-25, 171, 12)], tw * 1.6, twine, sides=6)
    knot = A(985, 812, -0.08)
    p.blob(knot, 0.0075, twine, squash=(1.0, 0.8, 1.1), segs=(10, 6))
    loop = [knot, A(1060, 775, -0.08), A(1130, 785, -0.08), A(1165, 830, -0.08), A(1145, 878, -0.08),
            A(1085, 875, -0.08)]
    rope(p, loop_curve(loop, 4), tw * 1.05, twine, twist=2 * math.pi / 0.04, closed=True, step=0.0095, sides=4)
    for end in ([A(930, 900, -0.095), A(920, 1000, -0.11), A(945, 1140, -0.12)],
                [A(1000, 880, -0.09), A(1020, 980, -0.1), A(1010, 1090, -0.105)]):
        twisted_rope(p, path_curve([knot] + end, 4), tw * 1.05, twine, pitch=0.04, per_turn=3, sides=4)


PALETTE.update({
    'YanPaper':  ('#f2d6a8', '#cfa676'),   # 盐渍辅料包's kraft paper, crumpled, stained olive by the pickles
    'YanHeap':   ('#6e6420', '#4c4412'),   # the pickles deep in the parcel, in shadow
    'YanTwine':  ('#dcae6c', '#b48448'),   # its twisted twine
    'YanLeaf':   ('#9a9238', '#6e6824'),   # the dark olive leaves of the salted greens
    'YanShred':  ('#f4dc8e', '#d8b85c'),   # the pale shreds of the salted stems
    'YanSalt':   ('#fbfaf6', '#d8dce0'),   # the coarse salt over them
})
GLOSS.update({'YanPaper': 0.0, 'YanHeap': 0.0, 'YanTwine': 0.0, 'YanLeaf': 0.2, 'YanShred': 0.25, 'YanSalt': 0.1})
VIVID.update({'YanPaper': 0.3, 'YanHeap': 0.5, 'YanTwine': 0.45, 'YanLeaf': 0.6, 'YanShred': 0.55, 'YanSalt': 0.2})
VTINT.update(dict.fromkeys(('YanPaper', 'YanTwine', 'YanLeaf', 'YanShred'), 1.0))
DETAIL.update({
    'YanPaper':  ('food_crumple', 5, '#a07c50', 0.3, 0.8),
    'YanTwine':  ('food_fiber', 40, '#a87838', 0.35, 0.2),
    'YanLeaf':   ('food_veins', 18, '#4e4a14', 0.35, 0.25),
    'YanShred':  ('food_fiber', 16, '#e2c060', 0.3, 0.25),
})


def pickle_base(col):
    """盐渍辅料包 traced from its art (trace_pickle_base.py writes traced_pickle_base.json): crumpled kraft paper
    gathered round a heap of salted pickles and tied at the neck with twine in a bow; the heap traced from the art,
    pale shreds crossing over dark olive leaves (painted on where the art has them, raised where it lights them),
    coarse salt crystals where the art has them; the paper and twine coloured from the art, stains and creases too."""
    p = Part()
    A = ArtMaps(TRACED['pickle_base'])
    pickle_bag(p)
    traced_pack(p, TRACED['pickle_base'], ink='#4a4010', maps=A)
    for c, size, rot in A.data['salt']:
        crystal(p, Vector(c), size, mat='YanSalt', rot=rot)
    art_colour(p, A, 0, ('YanPaper', 'YanTwine'), 0.8)
    return p.finish('SM_pickle_base', col, sharp=None)


def seafood_bag(p, paper='HaiPaper', heap='HaiHeap', twine='HaiTwine'):
    """干贝海味包's bag as the art has it: a box-like kraft paper bag seen corner on, its open top crumpled into
    rounded flaps (the tallest at the back left, others out to the left and the right), closed inside by the heap
    the scallops and shrimp lie on, tied at the neck with pale twine in a bow of two loops and two hanging ends at
    the front right. Its rim traced from the art (`A`: the art pixel and the depth chosen)."""
    S, X0, Y0 = 3700.0, 650.0, 958.0   # how the art is drawn: pixels a metre, and where the origin shows

    def A(X, Y, y):
        return art_point(X, Y, y, S, X0, Y0)
    rim = [A(1162, 435, 0.0), A(1149, 400, 0.02), A(1100, 365, 0.04), A(1050, 349, 0.055), A(1000, 257, 0.07),
           A(950, 241, 0.08), A(850, 205, 0.095), A(800, 217, 0.10), A(750, 172, 0.10), A(650, 141, 0.10),
           A(550, 107, 0.095), A(450, 219, 0.085), A(350, 255, 0.07), A(250, 346, 0.05), A(150, 385, 0.03),
           A(108, 437, 0.01), A(119, 500, -0.01), A(140, 575, -0.03), A(164, 625, -0.045), A(240, 600, -0.06),
           A(400, 615, -0.085), A(520, 655, -0.10), A(630, 730, -0.115), A(740, 715, -0.11), A(900, 680, -0.095),
           A(1060, 630, -0.065), A(1100, 590, -0.045), A(1151, 612, -0.03), A(1140, 525, -0.01)]
    ang = [math.atan2(q.y, q.x) for q in rim]
    # the foot: a box corner on, its corners at the left, the front, the right and the back, rounded
    bc = (-0.008, -0.005)
    corners = [(-0.134, -0.01), (0.027, -0.11), (0.118, 0.001), (-0.044, 0.10)]
    foot = polar_fn([(math.degrees(math.atan2(y - bc[1], x - bc[0])) % 360, math.hypot(x - bc[0], y - bc[1]))
                     for x, y in corners] +
                    [(math.degrees(math.atan2((y0 + y1) / 2 - bc[1], (x0 + x1) / 2 - bc[0])) % 360,
                      math.hypot((x0 + x1) / 2 - bc[0], (y0 + y1) / 2 - bc[1]) * 1.04)
                     for (x0, y0), (x1, y1) in zip(corners, corners[1:] + corners[:1])])
    B1 = polar_ring(bc, 0.01, foot, ang)
    B2 = polar_ring(bc, 0.045, lambda t: foot(t) * 1.03, ang)
    B3 = polar_ring((0.0, 0.0), 0.078, lambda t: foot(t) * 1.02, ang)
    N = polar_ring((0.0, 0.0), 0.1, ellipse_fn(0.12, 0.1), ang)
    U1 = polar_ring((0.0, 0.0), 0.12, ellipse_fn(0.126, 0.106), ang)
    t = 0.004
    F0 = pulled([u.lerp(r, 0.25) for u, r in zip(U1, rim)], (0.0, 0.0), t * 1.1)
    Ri = pulled(rim, (0.0, 0.0), t, -t * 0.8)
    secs = [shrunk(B1, bc, 0.5, 0.0), shrunk(B1, bc, 0.9, 0.001), B1, B2, B3, N, U1,
            pulled(rim, (0.0, 0.0), -t / 2, -t * 0.8), rim, Ri, [a.lerp(b, 0.5) for a, b in zip(Ri, F0)], F0]
    rings = loft(secs, 2, [1, 1, 1, 1, 1, 1, 2, 1, 1, 1, 1])
    rnd = random.Random(8)
    ph = [rnd.uniform(0, 2 * math.pi) for _ in range(4)]
    for rg in rings[3:-5]:   # the paper crumpled into soft folds
        for q in rg:
            a = math.atan2(q.y, q.x)
            amp = (0.006 if q.z < 0.085 else 0.006 - 0.0045 * min(1.0, (q.z - 0.085) / 0.04)) * (0.3 + 0.7 * abs(math.sin(a)))
            k = amp * (math.sin(5 * a + ph[0] + q.z * 25) * 0.65 + math.sin(9 * a + ph[1] - q.z * 50) * 0.35)
            q.x += math.cos(a) * k
            q.y += math.sin(a) * k
    skin(p, [Vector((bc[0], bc[1], 0.0))] + rings, paper)
    dome(p, F0, Vector((0.0, 0.04, 0.142)), heap, rings=((0.6, 0.7),))
    # the twine round the neck and its bow: two loops and two hanging ends at the front right
    tw = 0.0027
    TA, TB, TZ = 0.12 + 0.006, 0.1 + 0.006, 0.1

    def neck(deg):
        a = math.radians(deg)
        return Vector((TA * math.cos(a), TB * math.sin(a), TZ))
    twisted_rope(p, [neck(d) for d in range(160, 345, 4)], tw, twine, pitch=0.042, per_turn=3, sides=4)
    soft_tube(p, [neck(d) for d in range(-25, 171, 12)], tw * 1.6, twine, sides=6)
    knot = A(990, 790, -0.075)
    p.blob(knot, 0.009, twine, squash=(1.0, 0.8, 1.1), segs=(10, 6))
    for loop in ([knot, A(1060, 760, -0.07), A(1150, 765, -0.065), A(1185, 800, -0.065), A(1160, 840, -0.07),
                  A(1080, 830, -0.08)],
                 [knot, A(930, 820, -0.09), A(840, 870, -0.105), A(770, 930, -0.115), A(760, 980, -0.12),
                  A(800, 1010, -0.12), A(870, 990, -0.11), A(930, 920, -0.095)]):
        rope(p, loop_curve(loop, 3), tw, twine, twist=2 * math.pi / 0.042, closed=True, step=0.012, sides=4)
    for end in ([A(975, 880, -0.09), A(985, 980, -0.1), A(990, 1060, -0.105), A(980, 1125, -0.11)],
                [A(1030, 850, -0.08), A(1070, 920, -0.08), A(1092, 1000, -0.08)]):
        twisted_rope(p, path_curve([knot] + end, 3), tw, twine, pitch=0.042, per_turn=3, sides=4)


PALETTE.update({
    'HaiPaper':      ('#ecc890', '#c9a06a'),   # 干贝海味包's kraft paper, crumpled
    'HaiHeap':       ('#7e4c22', '#5a3416'),   # the heap under the scallops and shrimp, in shadow between them
    'HaiTwine':      ('#e6dcb0', '#c4b888'),   # its pale twine
    'HaiScallop':    ('#f6b84e', '#de9330'),   # the dried scallops' fibrous sides
    'HaiScallopTop': ('#fcdc8c', '#efc062'),   # their pale cut tops
    'HaiShrimp':     ('#f59a6a', '#e0704a'),   # the dried shrimp, coral with pale flesh
})
GLOSS.update({'HaiPaper': 0.0, 'HaiHeap': 0.0, 'HaiTwine': 0.0, 'HaiScallop': 0.15, 'HaiScallopTop': 0.1,
              'HaiShrimp': 0.3})
VIVID.update({'HaiPaper': 0.3, 'HaiHeap': 0.5, 'HaiTwine': 0.4, 'HaiScallop': 0.75, 'HaiScallopTop': 0.6,
              'HaiShrimp': 0.7})
VTINT.update(dict.fromkeys(('HaiPaper', 'HaiTwine', 'HaiScallop', 'HaiScallopTop', 'HaiShrimp'), 1.0))
DETAIL.update({
    'HaiPaper':      ('food_crumple', 5, '#a07c50', 0.3, 0.8),
    'HaiTwine':      ('food_fiber', 40, '#b8a878', 0.35, 0.2),
    'HaiScallop':    ('food_fibrous', 12, '#c86e1e', 0.55, 0.5),
    'HaiScallopTop': ('food_mottle', 18, '#f2b85c', 0.25, 0.15),
    'HaiShrimp':     ('food_pores', 18, '#fde8d8', 0.35, 0.25),
})


def seafood(col):
    """干贝海味包 traced from its art (trace_seafood.py writes traced_seafood.json): a box-like kraft paper bag seen
    corner on, its open top crumpled into flaps, tied at the neck with pale twine in a bow; heaped with big dried
    scallops, squat drums with fibrous sides and pale tops, and curled coral shrimp, each following its outline in
    the art and taking the art's colours; the paper and twine coloured from the art, the paper's creases with them."""
    p = Part()
    A = ArtMaps(TRACED['seafood'])
    seafood_bag(p)
    f0 = len(p.bm.faces)
    traced_pack(p, TRACED['seafood'], ink='#7a3a14', maps=A)
    keep_inside(p, f0, ('HaiPaper',), margin=0.005)
    art_colour(p, A, 0, ('HaiPaper', 'HaiTwine'), 0.8)
    return p.finish('SM_seafood', col, sharp=None)


def flat_bar(p, pts, radii, wdir, mat, squash=2.0, sides=10):
    """A straight bar (a scoop's handle) through the points pts, its oval section radii[i] thick and squash times as
    wide along wdir, closed by rounded tips; taper the last radii for a round end."""
    pts = [Vector(q) for q in pts]
    T = (pts[-1] - pts[0]).normalized()
    Wd = (Vector(wdir) - T * Vector(wdir).dot(T)).normalized()
    Nd = T.cross(Wd)
    tmp = bmesh.new()
    angs = [2 * math.pi * k / sides for k in range(sides)]
    rings = [[tmp.verts.new(q + r * (math.cos(a) * Nd + squash * math.sin(a) * Wd)) for a in angs]
             for q, r in zip(pts, radii)]
    t0, t1 = tmp.verts.new(pts[0] - T * radii[0] * 0.9), tmp.verts.new(pts[-1] + T * radii[-1] * 0.9)
    for ra, rb in zip(rings, rings[1:]):
        for k in range(sides):
            tmp.faces.new((ra[k], ra[(k + 1) % sides], rb[(k + 1) % sides], rb[k]))
    for k in range(sides):
        tmp.faces.new((t0, rings[0][(k + 1) % sides], rings[0][k]))
        tmp.faces.new((t1, rings[-1][k], rings[-1][(k + 1) % sides]))
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)


def art_line(pts):
    """The art's row Y along a drawn line [(X, Y)] (X rising) at column X, held level past its ends."""
    def f(X):
        if X <= pts[0][0]:
            return pts[0][1]
        for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
            if X <= x1:
                return y0 + (y1 - y0) * (X - x0) / max(x1 - x0, 1e-9)
        return pts[-1][1]
    return f


def starch(col):
    """玉米淀粉 as the art has it: a squat yellow paper sack seen a little from its right, its front turned to the
    left, the foot spreading into soft ears at the left and right; its top is rolled down outside into a thick round
    cuff that dips at the front and rises to its corners, round a heap of white starch reaching back to the inside of
    the far wall; a wooden scoop lies in the starch at the back right, its handle resting on the rim and rising to the
    right; on the front, a corn cob in its husk leaves."""
    p = Part()
    S, X0, Y0 = 3600.0, 611.0, 1008.0   # how the art is drawn: pixels a metre, and where the origin shows
    ce, se = math.cos(ART_EL), math.sin(ART_EL)
    phi = math.radians(-25.7)           # the sack's front faces this far to the left of straight on
    E = Vector((math.cos(phi), math.sin(phi), 0.0))     # along the front, to the right
    N = Vector((-math.sin(phi), math.cos(phi), 0.0))    # into the sack
    c = Vector((0.025, -0.01, 0.0))     # the middle of the opening, seen from above

    def L(u, v, z=0.0):   # the sack's own frame: u along its front, v into it
        return E * u + N * v + Vector((0.0, 0.0, z))

    def at_z(X, Y, z):    # the point at height z that the art's pixel (X, Y) shows
        x, y = from_art(X, Y, z, S, X0, Y0)
        return Vector((x, y, z))

    def on_wall(X, Y, a, b):   # the point the art's pixel shows on the upright plane through the local points a, b
        A_, B_ = L(*a), L(*b)
        n = Vector((A_.y - B_.y, B_.x - A_.x, 0.0))
        x = (X - X0) / S
        return art_point(X, Y, A_.y - n.x * (x - A_.x) / n.y, S, X0, Y0)

    def ang(q):
        return math.atan2(q.y - c.y, q.x - c.x) % (2 * math.pi)

    def polar(pts):   # radius and height round c as smooth functions of the angle, through the points pts
        out = [(math.degrees(ang(q)), math.hypot(q.x - c.x, q.y - c.y), q.z) for q in pts]
        return polar_fn([(a, r) for a, r, _ in out]), polar_fn([(a, z) for a, _, z in out])

    def lin(pairs):   # a periodic piecewise-linear function of the angle through [(degrees, value)]
        pairs = sorted(pairs)
        segs = list(zip(pairs, pairs[1:] + [(pairs[0][0] + 360, pairs[0][1])]))

        def f(a):
            d = math.degrees(a) % 360
            for (d0, v0), (d1, v1) in segs:
                dd = d if d >= d0 else d + 360
                if d0 <= dd <= d1:
                    return v0 + (v1 - v0) * (dd - d0) / (d1 - d0)
            return pairs[0][1]
        return f

    def poly_r(pts):   # the radius towards each angle of a closed outline round c
        P = [(q.x - c.x, q.y - c.y) for q in pts]

        def f(a):
            dx, dy = math.cos(a), math.sin(a)
            best = 0.0
            for (x0, y0), (x1, y1) in zip(P, P[1:] + P[:1]):
                ex, ey = x1 - x0, y1 - y0
                den = dx * ey - dy * ex
                if abs(den) > 1e-12:
                    t_, s_ = (x0 * ey - y0 * ex) / den, (x0 * dy - y0 * dx) / den
                    if 0.0 <= s_ <= 1.0 and t_ > best:
                        best = t_
            return best
        return f

    def outline(corners, sides):   # a soft four-sided section through the local corners (anticlockwise from the
        pts = []                   # front right), each side bowed out by its profile [(share along, metres out)]
        for (u0, v0), (u1, v1), prof in zip(corners, corners[1:] + corners[:1], sides):
            du, dv = u1 - u0, v1 - v0
            ln = math.hypot(du, dv)
            for i in range(16):
                t_ = i / 16
                b = next(b0 + (b1 - b0) * (t_ - s0) / (s1 - s0) for (s0, b0), (s1, b1) in zip(prof, prof[1:])
                         if s0 <= t_ <= s1)
                pts.append(L(u0 + du * t_ + dv / ln * b, v0 + dv * t_ - du / ln * b))
        return poly_r(pts)

    def bow(b):
        return [(0.0, 0.0), (0.25, b * 0.7), (0.5, b), (0.75, b * 0.7), (1.0, 0.0)]

    def ring_of(rf, zf):
        return [Vector((c.x + rf(a) * math.cos(a), c.y + rf(a) * math.sin(a), zf(a))) for a in TH]

    # the top of the rolled cuff, traced from the art: round the back its outline (level), across the front and up
    # the right side where it meets the starch
    FRONT, RIGHT = ((-0.12, -0.06), (0.13, -0.06)), ((0.13, -0.06), (0.152, 0.02))
    fold_pts = ([at_z(X, Y, 0.222) for X, Y in (
                    (1146, 470), (1110, 425), (1070, 381), (1030, 341), (960, 296), (890, 256), (850, 241), (810, 228),
                    (770, 220), (730, 214), (690, 196), (650, 179), (610, 169), (570, 178), (530, 189), (490, 198),
                    (450, 207), (410, 220), (370, 244), (350, 267), (310, 281), (270, 300), (230, 327))]
                + [on_wall(X, Y, *FRONT) for X, Y in (
                    (205, 425), (240, 428), (273, 431), (313, 442), (353, 464), (373, 482), (393, 509), (413, 536),
                    (453, 553), (493, 571), (533, 594), (573, 600), (613, 606), (653, 612), (693, 622), (733, 633),
                    (773, 625), (813, 617), (853, 611), (893, 592), (933, 576), (973, 565), (993, 559))]
                + [on_wall(X, Y, *RIGHT) for X, Y in ((1013, 536), (1033, 514), (1053, 497), (1073, 482), (1100, 476))])
    r_fold, z_fold = polar(fold_pts)
    a_left, a_right = ang(fold_pts[23]), ang(fold_pts[0])   # the ends of the cuff's front
    a_fr = ang(L(0.12, -0.05))                               # the sack's front corner
    a_br, a_fl = ang(L(0.12, 0.035)), ang(L(-0.11, -0.05))   # its right and left outlines
    TH = ([a_left + (a_fr - a_left) * i / 16 for i in range(16)] +
          [a_fr + (a_right - a_fr) * i / 6 for i in range(6)] + [a_right] +
          [a_br + (a_fl - 0.1 + 2 * math.pi - a_br) * i / 15 for i in range(15)] + [a_fl - 0.1, a_fl])
    span = (a_right - a_left) % (2 * math.pi)

    def is_front(a):
        return ((a - a_left) % (2 * math.pi)) < span + 1e-6

    # the cuff hangs from the roll to its hem, traced across the front, hidden round the back; it flares out at the
    # left and tucks in under the roll at the right
    hem_art = art_line([(180, 494), (200, 515), (220, 529), (240, 540), (260, 552), (280, 566), (300, 573), (320, 584),
                        (340, 595), (360, 604), (380, 618), (400, 628), (420, 640), (440, 649), (460, 658), (480, 662),
                        (500, 664), (520, 667), (540, 673), (560, 675), (580, 681), (600, 688), (620, 696), (640, 701),
                        (660, 708), (680, 713), (700, 721), (720, 726), (740, 732), (760, 738), (780, 736), (800, 732),
                        (820, 728), (840, 724), (860, 719), (880, 713), (900, 708), (920, 702), (940, 692), (960, 682),
                        (980, 674), (1000, 664), (1020, 654), (1040, 646), (1060, 641), (1080, 636), (1100, 626)])
    t = 0.006   # the radius of the roll
    fo_off = lin([(20, 0.003), (150, 0.003), (175, 0.003), (190, 0.004), (200, 0.006), (300, 0.006), (330, 0.004),
                  (345, 0.002)])
    mid_off = lin([(20, 0.0), (170, 0.005), (181, 0.006), (195, 0.007), (300, 0.007), (325, 0.0), (339, -0.0075),
                   (355, -0.005)])
    hem_off = lin([(20, -0.004), (170, 0.009), (181, 0.0115), (195, 0.009), (300, 0.009), (325, -0.002), (339, -0.0125),
                   (355, -0.009)])
    bh = []
    for a in TH:
        r = r_fold(a) + hem_off(a)
        q = Vector((c.x + r * math.cos(a), c.y + r * math.sin(a)))
        z = ((Y0 - hem_art(X0 + S * q.x)) / S - se * q.y) / ce
        bh.append((math.degrees(a), min(0.06, max(0.018, z_fold(a) - z)) if is_front(a) else 0.04))
    band_h = lin(bh)
    z_hem = lambda a: z_fold(a) - band_h(a)
    # the body, from the soft ears of the foot up to under the cuff, its outline traced from the art: the bottom
    # edge, the left and right outlines and the front corner's crease
    front = [(0.0, 0.0), (0.044, 0.0081), (0.115, 0.0133), (0.206, 0.0161), (0.298, 0.0187), (0.393, 0.021),
             (0.486, 0.0236), (0.603, 0.0233), (0.707, 0.0193), (0.788, 0.0125), (0.866, 0.0038), (0.922, 0.0004),
             (1.0, 0.0)]
    front_k = lambda k: [(s_, b * k) for s_, b in front]
    foot = outline([(0.116, -0.041), (0.1304, 0.0429), (-0.11, 0.085), (-0.129, -0.0445)],
                   [bow(0.002), bow(0.02), bow(0.01), front])
    body = [(0.016, outline([(0.128, -0.05), (0.129, 0.04), (-0.108, 0.085), (-0.124, -0.05)],
                            [bow(0.003), bow(0.02), bow(0.01), front_k(0.7)])),
            (0.045, outline([(0.12, -0.05), (0.121, 0.035), (-0.106, 0.085), (-0.118, -0.05)],
                            [bow(0.004), bow(0.02), bow(0.008), front_k(0.6)])),
            (0.08, outline([(0.117, -0.05), (0.12, 0.035), (-0.104, 0.085), (-0.109, -0.05)],
                           [bow(0.004), bow(0.02), bow(0.008), bow(0.012)])),
            (0.115, outline([(0.12, -0.05), (0.129, 0.035), (-0.104, 0.085), (-0.112, -0.05)],
                            [bow(0.004), bow(0.02), bow(0.008), bow(0.011)]))]
    top = outline([(0.126, -0.052), (0.12, 0.035), (-0.1, 0.085), (-0.097, -0.052)],
                  [bow(0.003), bow(0.02), bow(0.006), bow(0.009)])
    B0 = [q + L(0.0037, -0.0077) for q in ring_of(foot, lambda a: 0.006)]   # the outline traced at z = 0, lifted
    secs = ([shrunk(B0, c, 0.5, 0.0), shrunk(B0, c, 0.93, 0.0), B0] + [ring_of(f, lambda a, z=z: z) for z, f in body] +
            [ring_of(top, lambda a: z_hem(a) - 0.014),
            ring_of(lambda a: top(a) - 0.001, lambda a: z_hem(a) + 0.004),                       # under the cuff
            ring_of(lambda a: r_fold(a) + hem_off(a) - 0.004, lambda a: z_hem(a) - 0.0015),      # its hem, rounded
            ring_of(lambda a: r_fold(a) + hem_off(a), lambda a: z_hem(a) + 0.003),
            ring_of(lambda a: r_fold(a) + mid_off(a), lambda a: z_hem(a) + band_h(a) * 0.5),   # up the cuff
            ring_of(lambda a: r_fold(a) + fo_off(a), lambda a: z_fold(a) - t),
            ring_of(r_fold, z_fold),                                                            # over the roll
            ring_of(lambda a: r_fold(a) - t, lambda a: z_fold(a) - t)])
    # inside, down to where the starch meets the paper: just under the roll in front, lower round the back as the
    # art's line along the far wall has it, and well in at the cuff's left end, where the paper shows behind the roll
    starch_art = art_line([(300, 438), (321, 414), (341, 394), (361, 374), (381, 362), (401, 356), (421, 350),
                           (441, 338), (481, 330), (521, 316), (561, 302), (581, 296), (621, 284), (688, 289),
                           (735, 307), (800, 340), (870, 385), (940, 430), (980, 470), (1020, 523)])
    inset = lin([(40, 0.012), (120, 0.008), (150, 0.02), (165, 0.03), (182, 0.03), (188, 0.004), (322, 0.004),
                 (330, 0.014), (339, 0.034), (351, 0.03), (10, 0.02)])
    r_f0 = lambda a: r_fold(a) - t - inset(a)
    zf0 = []
    for a in TH:
        q = Vector((c.x + r_f0(a) * math.cos(a), c.y + r_f0(a) * math.sin(a)))
        z_art = ((Y0 - starch_art(X0 + S * q.x)) / S - se * q.y) / ce
        zf0.append((math.degrees(a), z_fold(a) - 0.016 if 187 < math.degrees(a) % 360 < 322
                    else min(z_fold(a) - 0.016, z_art)))
    z_f0 = lin(zf0)
    F0 = ring_of(r_f0, z_f0)
    secs += [ring_of(lambda a: r_fold(a) - t - 0.002, lambda a: (z_fold(a) - t + z_f0(a)) / 2), F0,
             ring_of(r_f0, lambda a: z_f0(a) - 0.012)]   # on down a little past it, so the heap tucks in behind paper
    rings = loft(secs, 2, [1] * 12 + [2, 2, 1, 1, 1])
    rnd = random.Random(4)
    ph = [rnd.uniform(0, 2 * math.pi) for _ in range(3)]
    for i, k in ((3, 0.6), (4, 1.0), (5, 1.0), (6, 0.8), (7, 0.45)):   # the paper softly crumpled up the body
        for q in rings[i]:
            a = math.atan2(q.y - c.y, q.x - c.x)
            f = 0.0028 * k * (math.sin(6 * a + ph[0] + q.z * 30) * 0.6 + math.sin(11 * a + ph[1] - q.z * 55) * 0.4)
            q.x += math.cos(a) * f
            q.y += math.sin(a) * f
    skin(p, [Vector((c.x, c.y, 0.0))] + rings, 'StarchBag')
    # the heap of starch, rising gently from where it meets the paper so that it never hides that line, lumpy all over
    apex = Vector((0.0, -0.02, 0.222))
    rnd = random.Random(12)
    clumps = [(rnd.uniform(-0.1, 0.12), rnd.uniform(-0.08, 0.07), rnd.uniform(0.012, 0.024), rnd.uniform(0.0022, 0.005))
              for _ in range(30)]
    clumps.append((0.092, -0.042, 0.026, -0.011))   # where the scoop has dug in, beside its right wall

    def lump(x, y):   # soft clumps of starch all over the heap
        return sum(h * math.exp(-((x - cx) ** 2 + (y - cy) ** 2) / (r * r)) for cx, cy, r, h in clumps)
    edge = rings[-2]   # where the starch meets the paper, all round
    rim_ = []
    for j in range(64):   # spokes evenly round the top, out to that line, a little into the paper and under it
        a = 2 * math.pi * j / 64
        dx, dy = math.cos(a), math.sin(a)
        best = (0.0, apex.z)
        for q0, q1 in zip(edge, edge[1:] + edge[:1]):
            ex, ey, x0, y0 = q1.x - q0.x, q1.y - q0.y, q0.x - apex.x, q0.y - apex.y
            den = dx * ey - dy * ex
            if abs(den) > 1e-12:
                t_, s_ = (x0 * ey - y0 * ex) / den, (x0 * dy - y0 * dx) / den
                if 0.0 <= s_ <= 1.0 and t_ > best[0]:
                    best = (t_, q0.z + (q1.z - q0.z) * s_)
        rim_.append((dx, dy, best[0] + 0.002, best[1] - 0.0015))
    smooth = [sum(rim_[(k + j) % 64][2] for j in range(-12, 13)) / 25 for k in range(64)]
    z_mean = sum(e[3] for e in rim_) / 64
    hs = []
    for sh in (1.0, 0.93, 0.84, 0.73, 0.61, 0.48, 0.35, 0.22, 0.1):
        f = 1.0 - sh ** 1.6
        env = min(1.0, (1.0 - sh) / 0.25) ** 0.7
        w_ = sh ** 3                                 # the rim's corners and tilt die away towards the top
        ring_ = []
        for (dx, dy, r0, z_), r1 in zip(rim_, smooth):
            r = sh * (w_ * r0 + (1.0 - w_) * r1)
            x, y = apex.x + dx * r, apex.y + dy * r
            z0 = z_ * w_ + z_mean * (1.0 - w_)
            ring_.append(Vector((x, y, z0 + (apex.z - z0) * f + lump(x, y) * env)))
        hs.append(ring_)
    skin(p, hs + [apex + Vector((0.0, 0.0, lump(apex.x, apex.y)))], 'Flour')
    # the scoop, straight from end to end: a big oval bowl lying in the starch at the back right, its open front
    # buried, its mouth turned up to us and rolled a little to the left so that its right wall stands out of the
    # starch, darker inside; the broad oval handle rises on along its axis, over the rim, to a round end
    view = Vector((0.0, ce, -se))
    B, T = Vector((0.0911, 0.009, 0.2315)), Vector((0.1358, 0.0498, 0.2605))   # the back of the mouth, the handle's end
    B, T = B - view * 0.012, T - view * 0.012          # sitting up out of the starch (the art shows it the same)
    D = (T - B).normalized()                           # along the scoop, towards its handle
    W0 = view.cross(D).normalized()                    # square to our view: the mouth would face us full on
    if W0.cross(D).z < 0:
        W0 = -W0
    roll = math.radians(-20)                           # rolled to the left: its right wall stands out of the starch
    W = W0 * math.cos(roll) - W0.cross(D) * math.sin(roll)   # across it, to the right
    m = W.cross(D)                                     # out of the mouth, up and to the left, towards us
    al, aw, bd = 0.051, 0.036, 0.03                    # the bowl's half-length, half-width and depth, outside
    Mc = B - D * al * 0.92
    Mb = Matrix(((D.x * al, -W.x * aw, m.x, Mc.x), (D.y * al, -W.y * aw, m.y, Mc.y), (D.z * al, -W.z * aw, m.z, Mc.z),
                 (0.0, 0.0, 0.0, 1.0)))
    if Mb.to_3x3().determinant() < 0:
        Mb = Mb @ Matrix.Diagonal((1.0, -1.0, 1.0, 1.0))
    p.lathe([(0.0, -bd), (0.55, -0.85 * bd), (0.85, -0.55 * bd), (0.98, -0.2 * bd), (1.0, -0.004), (0.99, 0.0015),
             (0.96, 0.0035), (0.93, 0.0015)], 'LightWood', n=48, M=Mb, close_ends=False)   # outside, over the rim
    p.lathe([(0.93, 0.0015), (0.905, -0.004), (0.86, -0.25 * bd), (0.7, -0.55 * bd), (0.4, -0.78 * bd),
             (0.0, -0.86 * bd)], 'JugStopper', n=48, M=Mb, close_ends=False)                  # and inside
    J = B + D * 0.012 - m * 0.012                      # the handle grows out of the bowl's back, under its rim
    flat_bar(p, [J - D * 0.009, J, J + (T - J) * 0.5, T, T + D * 0.007, T + D * 0.012, T + D * 0.0155],
             [0.006, 0.0075, 0.0082, 0.0085, 0.0077, 0.0056, 0.0027], W, 'LightWood', squash=2.1)
    # on the front, a corn cob in its husk leaves, raised a little off the paper: each piece is laid where the art
    # draws it, dropped onto what is under it along our line of sight
    from mathutils.bvhtree import BVHTree

    def dropper():
        tree = BVHTree.FromBMesh(p.bm)

        def put(X, Y, h):
            hit, n, _, _ = tree.ray_cast(art_point(X, Y, -0.4, S, X0, Y0), view)
            if n.dot(view) > 0:
                n = -n
            return hit - view * (h / max(0.35, -n.dot(view)))
        return put

    def relief(put, frame, us, vs, mat):   # frame(u, v) -> art (X, Y) and the height off the surface, over the
        tmp = bmesh.new()                  # parameters us × vs; mat a colour, or one for each cell (i, j)
        us = [i / us for i in range(us + 1)] if isinstance(us, int) else us
        vs = [j / vs for j in range(vs + 1)] if isinstance(vs, int) else vs
        grid = [[tmp.verts.new(put(*frame(u, v))) for v in vs] for u in us]
        mats = []
        for i in range(len(us) - 1):
            for j in range(len(vs) - 1):
                tmp.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
                mats.append(mat(i, j) if callable(mat) else mat)
        tmp.normal_update()
        if sum(f.normal.dot(view) * f.calc_area() for f in tmp.faces) > 0:
            bmesh.ops.reverse_faces(tmp, faces=tmp.faces[:])
        vmap = {v: p.bm.verts.new(v.co) for v in tmp.verts}
        for f, m_ in zip(tmp.faces, mats):
            p.bm.faces.new([vmap[v] for v in f.verts]).material_index = p._mi(m_)
        tmp.free()

    sink = 0.0012

    def leaf_frame(st, hmax):   # stations [(X, Y, half-width)] from the base to the tip, along the midrib
        n_ = len(st) - 1

        def f(u, v):
            x_ = u * n_
            i = min(int(x_), n_ - 1)
            g = x_ - i
            (Xa, Ya, wa), (Xb, Yb, wb) = st[i], st[i + 1]
            Xm, Ym, hw = Xa + (Xb - Xa) * g, Ya + (Yb - Ya) * g, wa + (wb - wa) * g
            i0, i1 = max(0, i - 1 if g < 0.5 else i), min(n_, i + 1 if g < 0.5 else i + 2)
            tx, ty = st[i1][0] - st[i0][0], st[i1][1] - st[i0][1]
            ln = math.hypot(tx, ty)
            sv = 2 * v - 1
            h = (hmax * min(1.0, hw / 14.0) ** 0.5 + sink) * math.sqrt(max(0.0, 1 - sv * sv)) - sink
            return Xm - ty / ln * hw * sv, Ym + tx / ln * hw * sv, h
        return f

    put = dropper()
    for st in ([(383, 840, 10), (390, 812, 12.5), (400, 795, 13), (410, 780, 13.5), (421, 765, 13), (436, 750, 12),
                (456, 736, 9), (469, 729, 5), (478, 726, 1.5)],                                    # behind, left
               [(560, 872, 14), (590, 848, 19), (612, 835, 23), (630, 822, 18), (645, 812, 12.5), (660, 804, 8),
                (674, 800, 4.5), (686, 796, 1.5)]):                                                # behind, right
        relief(put, leaf_frame(st, 0.0028), 2 * len(st), 4, 'CornHusk')
    P0, P1 = (385.0, 975.0), (580.0, 712.0)
    ax, ay = P1[0] - P0[0], P1[1] - P0[1]
    al_ = math.hypot(ax, ay)
    ax, ay = ax / al_, ay / al_

    def kernel(x):   # the rise of a kernel along one way across it, 0 in the groove before it
        f_ = x % 1.0
        return math.sin(math.pi * (f_ - 0.22) / 0.78) if f_ > 0.22 else 0.0

    def cob(u, v):   # u along the cob, nine kernels; v across it, six
        t_, sv = 0.004 + 0.992 * u, 2 * v - 1
        hw = 79.0 * math.sin(math.pi * t_) ** 0.6
        X, Y = P0[0] + ax * al_ * t_ - ay * hw * sv, P0[1] + ay * al_ * t_ + ax * hw * sv
        kern = kernel(u * 9 + 1e-6) * kernel(v * 6 + 1e-6)
        h = (0.0075 * math.sin(math.pi * t_) ** 0.35 + 0.0014 * kern + sink) * math.sqrt(max(0.0, 1 - sv * sv)) - sink
        return X, Y, h
    cuts = lambda n: [0.0] + [(k + f_) / n for k in range(n) for f_ in (0.22, 0.61, 1.0)]
    relief(put, cob, cuts(9), cuts(6), lambda i, j: 'CornGroove' if i % 3 == 0 or j % 3 == 0 else 'CornCob')
    put = dropper()
    for st, hm in (([(368, 985, 15), (357, 960, 21.5), (349, 945, 25), (343, 930, 27.5), (341, 915, 29.5),
                     (344, 900, 33), (345, 885, 33), (344, 870, 30.5), (348, 855, 29.5), (352, 840, 28),
                     (355, 825, 25.5), (357, 810, 24.5), (357, 795, 22.5), (354, 780, 20.5), (348, 765, 17.5),
                     (340, 750, 15.5), (331, 736, 11.5), (322, 723, 6.5), (315, 713, 2.5), (312, 709, 0.8)],
                    0.003),                                                                         # left
                   ([(366, 1000, 24), (390, 1000, 23), (420, 988, 20), (450, 983, 28), (480, 970, 38),
                     (510, 955, 45), (540, 938, 43), (570, 912, 35), (600, 893, 24), (630, 887, 16),
                     (655, 893, 13), (672, 908, 12), (681, 928, 9), (685, 946, 4), (686, 955, 1.2)],
                    0.0035)):                                                                       # in front
        relief(put, leaf_frame(st, hm), 2 * len(st) - 2, 5, 'CornHusk')
    return p.finish('SM_starch', col, sharp=None)


PALETTE.update({
    'BingCake':      ('#fae4b5', '#e9c78c'),   # 薄饼: the pale pancakes, from the art
    'BingSide':      ('#f0cd8e', '#d8ad68'),   # the stack's edges, sheet on sheet
    'BingSpot':      ('#f2bd62', '#d99c42'),   # the golden spots where they browned
    'BingTrayRim':   ('#c98848', '#9c6130'),   # the tray's rim: one broad bamboo band, its top rounded
    'BingTrayWeave': ('#d6a060', '#a8743c'),   # the woven floor
    'BingTrayWrap':  ('#f6e4b8', '#dbc28e'),   # the pale wraps binding the rim
})
GLOSS.update(dict.fromkeys(('BingCake', 'BingSide', 'BingSpot', 'BingTrayRim', 'BingTrayWeave', 'BingTrayWrap'), 0.0))
VIVID.update({'BingCake': 0.35, 'BingSide': 0.4, 'BingSpot': 0.5, 'BingTrayRim': 0.45, 'BingTrayWeave': 0.45,
              'BingTrayWrap': 0.35})
VTINT.update(dict.fromkeys(('BingCake', 'BingSide', 'BingSpot', 'BingTrayRim', 'BingTrayWeave', 'BingTrayWrap'), 1.0))
DETAIL.update({
    'BingCake':      ('food_mottle', 10, '#efca86', 0.2, 0.15),
    'BingSide':      ('food_mottle', 12, '#e9be78', 0.2, 0.15),
    'BingTrayRim':   ('food_wood', 24, '#7a4420', 0.45, 0.25),
    'BingTrayWeave': ('food_weave', 16, '#5a3010', 0.8, 0.6),
    'BingTrayWrap':  ('food_fiber', 30, '#c9a46a', 0.35, 0.25),
})


def bing_tray(p, ro, ri, zt, floor, sy, wraps, n=40):
    """The round bamboo tray of 薄饼备料 as the art draws it: a woven floor, a rim of one broad band of bamboo (its
    outside upright, its top rounded over, ro and ri its outside and inside), bound with pale wraps where the art has
    them (degrees round from the right); stretched sy front to back, as the art draws it."""
    rr, rc = (ro - ri) / 2, (ro + ri) / 2
    zc = zt - rr
    S = Matrix.Diagonal((1.0, sy, 1.0, 1.0))
    prof = [(0.0, 0.0), (ro - 0.004, 0.0), (ro - 0.0012, 0.0008), (ro, 0.004), (ro, zc * 0.55), (ro, zc)]
    prof += [(rc + rr * math.cos(math.radians(d)), zc + rr * math.sin(math.radians(d))) for d in (35, 70, 110, 145)]
    prof += [(ri, zc), (ri, (zc + floor) / 2), (ri - 0.001, floor + 0.0025), (ri - 0.004, floor)]
    p.lathe(prof, 'BingTrayRim', n=n, close_ends=False, M=S)
    p.lathe([(ri - 0.004, floor), (ri * 0.5, floor + 0.0003), (0.0, floor + 0.0004)], 'BingTrayWeave', n=n,
            close_ends=False, M=S)
    for d in wraps:   # each wrap a soft band round the rim, top to foot
        a = math.radians(d)
        c = Vector((rc * math.cos(a), sy * rc * math.sin(a), zt * 0.5 + 0.0006))
        tang = math.atan2(sy * math.cos(a), -math.sin(a))   # along the rim there
        p.blob(c, 1.0, 'BingTrayWrap', squash=(rr + 0.0042, 0.0075, zt * 0.5 + 0.0012), segs=(8, 4),
               rot=tang - math.pi / 2)


def pancake(col):
    """薄饼备料 traced from its art (trace_pancake.py writes traced_pancake.json): a stack of thin pancakes on a round
    woven bamboo tray, the top one flat and spotted gold, the sheets' wavy edges stepping down in front to the floor,
    and one pancake folded in four lying on top, its point lifted at the back right; every piece follows its outline
    in the art and takes the art's colours. The tray: a woven floor, a rim of one broad bamboo band, eleven pale
    wraps where the art has them, coloured from the art."""
    p = Part()
    A = ArtMaps(TRACED['pancake'])
    tray = A.data['tray']
    bing_tray(p, tray['ro'], tray['ri'], tray['zt'], tray['floor'], tray['sy'], A.data['wraps'])
    f0 = len(p.bm.faces)
    traced_pack(p, TRACED['pancake'], ink='#8a5a2a', maps=A)
    keep_inside(p, f0, ('BingTrayRim', 'BingTrayWrap'))
    art_colour(p, A, 0, ('BingTrayRim', 'BingTrayWeave', 'BingTrayWrap'), 0.75)
    return p.finish('SM_pancake', col, sharp=None)

def egg(col):
    """鸡蛋 as the art has it: three big eggs heaped in a round woven basket, one at the back leaning on the two in
    front, the thick rolled rim bound with pale wraps."""
    p = Part()
    fz = round_basket(p, 0.073, 0.058, 0.055, t=0.0065, bulge=0.55, rings=3, wraps=10, n=48, floor=0.012,
                      a0=math.radians(-117))
    s = 0.878   # the eggs' size: as the art draws them, so that the three lie in the basket without crossing

    def shape(v):   # an egg: the far end (+x) a little narrower
        k = 1 - 0.09 * v.x / (0.039 * s)
        return Vector((v.x, v.y * k, v.z * k))
    # each one's pose fitted to its outline in the art, the three clear of each other, the basket and its wraps
    # (each resting on the basket), the two in front lying low, the one behind leaning on them
    for (x, y, z, yaw, pitch) in ((-0.0348, -0.0101, 0.0492, 0.717, 2.079), (0.0297, -0.0196, 0.0485, 0.2907, 0.4525),
                                  (0.0004, 0.0355, 0.0585, 2.7906, -0.4606)):   # front left, front right, back
        R = Matrix.Rotation(yaw, 3, 'Z') @ Matrix.Rotation(-pitch, 3, 'Y')
        p.blob((x, y, z), 1.0, 'EggShell', squash=(0.039 * s, 0.0315 * s, 0.0315 * s), segs=(24, 12),
               deform=lambda v, R=R: R @ shape(v))
    return p.finish('SM_egg', col, sharp=None)


ITEMS = [('flour', flour),
         ('rice', rice),
         ('rice_prep', rice_prep),
         ('pickle_base', pickle_base),
         ('seafood', seafood),
         ('starch', starch),
         ('pancake', pancake),
         ('egg', egg)]
