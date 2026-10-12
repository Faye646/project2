"""盘装的生肉、禽、豆腐和鱼蟹: chicken, duck, kidney, wing, tofu, skin, fish, mandarin_fish, fish_head, crab, pork."""


import math
import os
import random
import bmesh
from mathutils import Matrix, Vector, noise
from .core import *  # noqa: F401,F403


PALETTE.update({
    'KidneyFat': ('#f8c9a6', '#e3a582'),   # the peachy fat in a kidney's hilum
    'DuckCut':  ('#f6b896', '#e09474'),    # the pink cut ends of the duck's drumsticks (was DuckKnob, which plates.py also defines)
})


PALETTE.update({
    'CarpFin': ('#988b80', '#766a60'),   # the warm grey dorsal fin and tail of the carp
    'CarpSkin': ('#f2ebe2', '#d6c9ba'),  # the carp's silvery skin, its big scales plain to see (its back painted grey)
    'CarpHead': ('#f2ebe2', '#d6c9ba'),  # and its head, smooth, no scales
})


GLOSS.update({'CarpFin': 0.3})


PALETTE.update({
    'FishCrown': ('#686e76', '#4c5158'),   # the dark blue-grey edges of the big fish head's gill cover, and its fin
    'GillRed': ('#c4574c', '#9c3d34'),     # the red gills under its gill cover
    'MouthPink': ('#d98a7c', '#b46a5d'),   # the inside of a gaping mouth
})


GLOSS.update({'FishCrown': 0.5, 'GillRed': 0.6, 'MouthPink': 0.5})
# Fish as the art paints them, not toys: their greys and creams kept soft (little of the rich food colour), scales
# over the skin (food_scales), the gills' fine filaments (food_fiber), and the crown's grey, the eye's dark ring and
# the warm lips painted across the pale skin (yutou_colour).
VIVID.update({'FishBelly': 0.35, 'CarpSkin': 0.35, 'CarpHead': 0.35, 'FishBack': 0.3, 'FishCrown': 0.3,
              'CarpFin': 0.3, 'FishFin': 0.3, 'FishIris': 0.25, 'GillRed': 0.6, 'MouthPink': 0.6, 'FishGill': 0.5})
DETAIL.update({'FishBelly': ('food_scales', 18, '#4a4f57', 0.2, 0.15),
               'CarpSkin': ('food_scales', 9, '#454a52', 0.42, 0.3),
               'GillRed': ('food_fiber', 30, '#8a3028', 0.5, 0.2),
               'CarpFin': ('food_fiber', 45, '#6a6058', 0.35, 0.1),    # the fins' rays
               'FishFin': ('food_fiber', 45, '#cf8763', 0.3, 0.1)})
VTINT.update({'FishBelly': 1.0, 'CarpSkin': 1.0, 'CarpHead': 1.0, 'GuiyuSkin': 1.0, 'MandarinSpot': 1.0})
PALETTE.update({'GuiyuSkin': ('#f1e6c4', '#d6c69e')})   # 鳜鱼's pale yellowish skin (its olive back painted on)
VIVID.update({'GuiyuSkin': 0.4, 'MandarinSpot': 0.4, 'MandarinFin': 0.5})
DETAIL.update({'GuiyuSkin': ('food_shell', 24, '#7a6a40', 0.25, 0.2),   # its fine dark mottling
               'MandarinFin': ('food_fiber', 45, '#b08a48', 0.35, 0.1)})   # its fins' rays


def _tv(name, default):   # TUNING ONLY: numbers overridden from MEAT_TUNE while matching to the art
    import json
    import os
    return json.loads(os.environ.get('MEAT_TUNE', '{}')).get(name, default)


def dish(p, r, h, foot=0.56, sx=1.0, n=48, floor=0.01, floor_r=0.7, lip=0.0035, bulge=0.6, deform=None):
    """A 青瓷 plate or shallow dish like the art's: a rounded foot ring of radius foot·r, a curved outer wall (`bulge`
    0 straight, 1 round as a bowl) up to a rolled lip at height h, and inside, a curve down from the lip to a flat
    floor at height `floor` out to floor_r·r (a high floor makes the thick-based plates the art draws, food sitting
    up near the rim). sx stretches it along x, `deform` (lobed()) scallops it. No crease anywhere, so it shades
    smooth. Returns the floor height."""
    rf = foot * r
    prof = [(0.0, 0.0015), (rf - 0.004, 0.0015), (rf - 0.0025, 0.0), (rf + 0.0015, 0.0), (rf + 0.003, 0.002)]
    outer = [(rf + 0.003, 0.002)]
    for i in range(1, 6):   # the outer wall: low near the foot, turning up to the rim
        t = i / 6
        outer.append((rf + 0.003 + (r - lip - rf - 0.003) * (1 - (1 - t) ** (1 + bulge)),
                      0.002 + (h - lip - 0.002) * t ** (1 + bulge)))
    prof += outer[1:]
    for k in range(5):   # the rolled lip, from the outside over the top to the inside
        a = -0.4 * math.pi + k * 1.3 * math.pi / 4
        prof.append((r - lip + lip * math.cos(a), h - lip + lip * math.sin(a)))

    def z_out(x):   # the outer wall's height at radius x
        for (x0, z0), (x1, z1) in zip(outer, outer[1:]):
            if x0 <= x <= x1:
                return z0 + (z1 - z0) * (x - x0) / (x1 - x0)
        return 0.0 if x < outer[0][0] else h
    x0, z0, x1 = prof[-1][0], prof[-1][1], floor_r * r
    for i in range(1, 5):   # the inside: steep under the lip, levelling out into the floor
        t = i / 5
        x = x0 + (x1 - x0) * t
        prof.append((x, max(floor + (z0 - floor) * (1 - t) ** 2, z_out(x) + 0.004)))
    prof += [(x1, floor), (x1 * 0.5, floor), (0.0, floor)]
    p.lathe(prof, 'Celadon', n=n, close_ends=False, M=Matrix.Diagonal((sx, 1.0, 1.0, 1.0)), deform=deform)
    return floor


def footed_profile(r, h, foot, foot_h, lip, bulge):
    """The outside of footed_dish(): the underside, a short upright foot ring of radius foot·r and height foot_h, then
    the wall swelling out from just above it (`bulge` 0 straight, 1 round) up to the outer edge of the lip."""
    rf = foot * r
    prof = [(0.0, 0.0025), (rf - 0.004, 0.0025), (rf - 0.0028, 0.0004), (rf - 0.0012, 0.0), (rf + 0.0008, 0.0),
            (rf + 0.0022, 0.0012)]
    if foot_h > 0.004:
        prof += [(rf + 0.0026, foot_h * 0.55), (rf + 0.0032, foot_h - 0.0012)]
    x0, z0 = rf + 0.0048, max(foot_h, 0.003)
    prof.append((x0, z0))
    for i in range(1, 7):
        t = i / 7
        prof.append((x0 + (r - lip - x0) * (1 - (1 - t) ** (1 + bulge)), z0 + (h - lip - z0) * t ** (1 + bulge)))
    return prof


def footed_dish_profile(r, h, foot=0.6, foot_h=0.0, floor=0.012, floor_r=0.7, lip=0.004, bulge=0.6):
    """The whole lathe profile of footed_dish() and the index where its inside begins (under the lip)."""
    prof = footed_profile(r, h, foot, foot_h, lip, bulge)
    outer = prof[-7:]
    for k in range(1, 5):   # the rolled lip, from the outside over the top to the inside
        a = k * 1.3 * math.pi / 4 - 0.4 * math.pi
        prof.append((r - lip + lip * math.cos(a), h - lip + lip * math.sin(a)))
    i0 = len(prof) - 1

    def z_out(x):   # the outer wall's height at radius x
        for (xa, za), (xb, zb) in zip(outer, outer[1:]):
            if xa <= x <= xb:
                return za + (zb - za) * (x - xa) / (xb - xa)
        return 0.0 if x < outer[0][0] else h
    xa, za, xb = prof[-1][0], prof[-1][1], floor_r * r
    for i in range(1, 5):   # the inside: steep under the lip, levelling out into the floor
        t = i / 5
        x = xa + (xb - xa) * t
        prof.append((x, max(floor + (za - floor) * (1 - t) ** 2, z_out(x) + 0.004)))
    prof += [(xb, floor), (xb * 0.5, floor), (0.0, floor)]
    return prof, i0


def footed_dish(p, r, h, foot=0.6, foot_h=0.0, sx=1.0, n=48, floor=0.012, floor_r=0.7, lip=0.004, bulge=0.6,
                yaw=0.0):
    """A 青瓷 plate as the art draws it, fitted to its outline: standing on a foot ring foot_h tall (0: a plain rounded
    foot) at radius foot·r, its wall swelling out (`bulge`) to a rolled lip of radius `lip` at height h; inside, a
    curve down under the lip to a flat floor at `floor` out to floor_r·r. sx stretches it along x and yaw turns it.
    n segments keep the rim a smooth ellipse; no crease anywhere. Returns the floor height."""
    prof, _ = footed_dish_profile(r, h, foot, foot_h, floor, floor_r, lip, bulge)
    p.lathe(prof, 'Celadon', n=n, close_ends=False,
            M=Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Diagonal((sx, 1.0, 1.0, 1.0)))
    return floor


def dish_inner(plate_kw):
    """The height of the inside of footed_dish(**plate_kw) at (x, y): its floor, rising up the wall to the lip."""
    kw = dict(plate_kw)
    sx, yaw = kw.pop('sx', 1.0), kw.pop('yaw', 0.0)
    kw.pop('n', None)
    prof, i0 = footed_dish_profile(**kw)
    inside = sorted(prof[i0:])
    c, s_ = math.cos(-yaw), math.sin(-yaw)

    def z(x, y):
        rho = math.hypot((c * x - s_ * y) / sx, s_ * x + c * y)
        if rho >= inside[-1][0]:
            return inside[-1][1]
        for (ra, za), (rb, zb) in zip(inside, inside[1:]):
            if ra <= rho <= rb:
                return za + (zb - za) * (rho - ra) / max(rb - ra, 1e-9)
        return inside[0][1]
    return z


def settle(p, n0, plate_kw, lift=0.0):
    """Bends what was added to p since it had n0 vertices up over the inside of the footed_dish(**plate_kw) it lies
    in: each vertex rises by as much as the inside has risen above the floor where it is (plus `lift`), so food
    reaching past the floor rests on the wall instead of passing out through it."""
    z_in, floor = dish_inner(plate_kw), plate_kw.get('floor', 0.012)
    p.bm.verts.ensure_lookup_table()
    for v in p.bm.verts[n0:]:
        v.co.z += max(0.0, z_in(v.co.x, v.co.y) - floor) + lift


def paint(p, f0, mat, field):
    """Gives `mat` to the parts of the faces added to p since it had f0 faces where field(point) > 0: marbling, a
    fat rim, spots, painted into the surface instead of stuck on it, so they stay flush and follow it. Faces the
    boundary crosses are cut along it first, so its edge runs smooth rather than stepping from face to face."""
    bm = p.bm
    bm.faces.ensure_lookup_table()
    faces = list(bm.faces[f0:])
    val = {}
    for f in faces:
        for v in f.verts:
            if v not in val:
                val[v] = field(v.co)
    cross = {e for f in faces for e in f.edges if (val[e.verts[0]] > 0) != (val[e.verts[1]] > 0)}
    zero = set()
    for e in cross:   # a vertex where the boundary crosses each edge
        a, b = e.verts
        t = val[a] / (val[a] - val[b])
        _, nv = bmesh.utils.edge_split(e, a, t)
        val[nv] = 0.0
        zero.add(nv)
    for f in faces:   # cut each face between its two crossing points
        zs = [v for v in f.verts if v in zero]
        if len(zs) == 2 and not any(e for e in f.edges if set(e.verts) == set(zs)):
            bmesh.utils.face_split(f, zs[0], zs[1])
    bm.faces.ensure_lookup_table()
    mi = p._mi(mat)
    for f in bm.faces[f0:]:
        vs = [val.get(v, 0.0) for v in f.verts]
        if sum(vs) / len(vs) > 0:
            f.material_index = mi


def lattice_box(p, mat, F, us=(-1.0, 0.0, 1.0), vs=(-1.0, 0.0, 1.0), ws=(-1.0, 0.0, 1.0)):
    """A cage for soft(): the outside of the lattice us × vs × ws spanning the box [-1, 1]³, each lattice point (u, v,
    w) placed at F(u, v, w). All quads and no poles, so it subdivides into a clean rounded block; loops close to ±1
    keep its rounded edges tighter, loops further in make it rounder."""
    tmp = bmesh.new()
    vert = {}
    nu, nv, nw = len(us) - 1, len(vs) - 1, len(ws) - 1

    def V(i, j, k):
        if (i, j, k) not in vert:
            vert[i, j, k] = tmp.verts.new(F(us[i], vs[j], ws[k]))
        return vert[i, j, k]
    for a in range(nu):
        for b in range(nv):
            tmp.faces.new((V(a, b, 0), V(a, b + 1, 0), V(a + 1, b + 1, 0), V(a + 1, b, 0)))
            tmp.faces.new((V(a, b, nw), V(a + 1, b, nw), V(a + 1, b + 1, nw), V(a, b + 1, nw)))
        for c in range(nw):
            tmp.faces.new((V(a, 0, c), V(a + 1, 0, c), V(a + 1, 0, c + 1), V(a, 0, c + 1)))
            tmp.faces.new((V(a, nv, c), V(a, nv, c + 1), V(a + 1, nv, c + 1), V(a + 1, nv, c)))
    for b in range(nv):
        for c in range(nw):
            tmp.faces.new((V(0, b, c), V(0, b, c + 1), V(0, b + 1, c + 1), V(0, b + 1, c)))
            tmp.faces.new((V(nu, b, c), V(nu, b + 1, c), V(nu, b + 1, c + 1), V(nu, b, c + 1)))
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)


def lumps(u, v, w, bumps):
    """How far the lattice point (u, v, w) swells out for the bumps [(u0, v0, w0, radius, height)]: soft lobes of
    muscle, or the irregularity of a hand-cut piece."""
    return sum(h * math.exp(-((u - a) ** 2 + (v - b) ** 2 + (w - c) ** 2) / r ** 2) for a, b, c, r, h in bumps)


def outward(u, v, w):
    """The outward direction of the lattice box [-1, 1]³ at its surface point (u, v, w)."""
    n = Vector([t if abs(t) > 0.999 else 0.0 for t in (u, v, w)])
    return n.normalized() if n.length > 0 else n


def clear_of(p, n0, f_lo, f_hi, d, gap=0.0006):
    """Moves what was added to p since it had n0 vertices along d until none of it is inside the closed piece made of
    the faces f_lo to f_hi, `gap` clear of it: a slice leaning on the chunk it was cut from, touching it, not in it."""
    from mathutils.bvhtree import BVHTree
    bm = p.bm
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    vidx, polys = {}, []
    for fc in bm.faces[f_lo:f_hi]:
        polys.append([vidx.setdefault(v.index, len(vidx)) for v in fc.verts])
    co = [None] * len(vidx)
    for i, j in vidx.items():
        co[j] = bm.verts[i].co.copy()
    tree = BVHTree.FromPolygons(co, polys)
    d = Vector(d).normalized()
    verts = bm.verts[n0:]
    start = [v.co.copy() for v in verts]

    def clear(t):
        for c in start:
            loc, nrm, _, _ = tree.find_nearest(c + d * t)
            if loc is not None and (c + d * t - loc).dot(nrm) < gap:
                return False
        return True
    lo, hi = 0.0, 0.01
    while not clear(hi):
        lo, hi = hi, hi * 2
    for _ in range(14):   # the least move along d that leaves it clear
        mid = (lo + hi) / 2
        lo, hi = (lo, mid) if clear(mid) else (mid, hi)
    for v, c in zip(verts, start):
        v.co = c + d * hi


def squash_onto(p, n0, plate_kw, top, lift=0.0):
    """Like settle(), but for a tall piece whose foot reaches up the wall of the footed_dish(**plate_kw) it stands
    in: each vertex added to p since it had n0 vertices rises by as much as the inside has risen where it is, less
    the higher it is, nothing at height `top`, so the foot lies on the wall while the top stays level, the meat
    squashed a little instead of tipped up."""
    z_in, floor = dish_inner(plate_kw), plate_kw.get('floor', 0.012)
    p.bm.verts.ensure_lookup_table()
    for v in p.bm.verts[n0:]:
        rise = max(0.0, z_in(v.co.x, v.co.y) - floor)
        v.co.z += rise * max(0.0, 1 - (v.co.z - floor) / (top - floor)) + lift


def rest_on_plate(p, n0, f_plate, gap=0.0005, reach=0.004):
    """Lifts any vertex added to p since it had n0 vertices that lies less than `gap` above the plate made of p's first
    f_plate faces up to that height over it, measured on the plate's own facets: settle() follows the smooth profile,
    which the lathe's flat facets cut across, so food lying on the lip could touch it."""
    from mathutils.bvhtree import BVHTree
    bm = p.bm
    bm.faces.ensure_lookup_table()
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    vidx, polys = {}, []
    for fc in bm.faces[:f_plate]:
        polys.append([vidx.setdefault(v.index, len(vidx)) for v in fc.verts])
    co = [None] * len(vidx)
    for i, j in vidx.items():
        co[j] = bm.verts[i].co.copy()
    tree = BVHTree.FromPolygons(co, polys)
    ring = [(0.0, 0.0)] + [(reach * math.cos(k * math.pi / 4), reach * math.sin(k * math.pi / 4)) for k in range(8)]
    for v in bm.verts[n0:]:   # the highest point of the plate within `reach`, so no ridge of it pokes up between
        hits = [tree.ray_cast(Vector((v.co.x + dx, v.co.y + dy, 1.0)), Vector((0.0, 0.0, -1.0)))[0] for dx, dy in ring]
        hits = [h.z for h in hits if h is not None]
        if hits and v.co.z < max(hits) + gap:
            v.co.z = max(hits) + gap


PORK_PLATE = dict(r=0.088, h=0.028, foot=0.78, foot_h=0.004, sx=1.18, floor=0.012, floor_r=0.82, bulge=0.4)


PK = dict(cx=-0.011, cy=0.018, yaw=-23.0, L=0.136, D=0.09, Ht=0.061, slope=0.25, dome=0.25, droop_l=0.01,
          droop_bl=0.006, round_b=0.12,
          taper_x=0.1, taper_y=0.22, shift_y=0.008,
          bumps=((-0.4, -1.0, 0.1, 0.5, 0.008), (0.35, -1.0, -0.1, 0.45, 0.007), (-1.0, -0.2, 0.2, 0.5, 0.008),
                 (-0.5, 0.1, 1.0, 0.4, 0.004), (0.25, 0.4, 1.0, 0.4, 0.005), (1.0, 0.3, 0.3, 0.5, 0.004),
                 (-0.75, -0.6, 0.6, 0.35, 0.005)),
          fat_v=0.2, fat_k=0.5, fat_u=0.3, fat_l=0.62,
          sx=0.05, sy=-0.026, yaw_s=28.0, lean_s=32.0, roll_s=14.0, SL=0.076, ST=0.022, SHl=0.082, SHr=0.064,
          shear=-0.012, oval=2.6, rim_t=0.4, rim_r=0.12, rim_b=0.08)


def pork(col):
    """猪肉 as the art has it: a low, wide chunk of raw pork filling a small oval celadon plate, a rounded mound whose
    top falls towards the viewer, soft lobes of muscle swelling its sides and no straight edge anywhere; its pink lean
    (the shader's detail texture marbles it) under an uneven band of white fat along the back left of the top and
    down its left end. A thick slice leans back on its front right, the marbled cut face turned to the viewer and to
    the right, a rim of fat round it, widest along its top edge."""
    K = PK
    p = Part()
    fz = footed_dish(p, **PORK_PLATE)
    L, D = K['L'], K['D']
    M = Matrix.Translation((K['cx'], K['cy'], fz)) @ Matrix.Rotation(math.radians(K['yaw']), 4, 'Z')

    def top(u, v):   # the height of the top: falling towards the front and to both ends, the left end lower, most
        # of all at the back, where that corner lies up on the wall of the plate
        return (K['Ht'] * (1 - K['slope'] * (1 - v) / 2) * (1 - K['dome'] * u * u)
                - (K['droop_l'] + K['droop_bl'] * max(0.0, v)) * max(0.0, -u) ** 2)

    def chunk(u, v, w):
        s = (w + 1) / 2   # 0 at the foot, 1 on top: the sides slope in as they rise, a mound rather than a box
        k = 1 - K['round_b'] * (max(0.0, v) * u) ** 2   # its back corners rounded off in plan
        q = Vector((u * L / 2 * (1 - K['taper_x'] * s) * k, v * D / 2 * (1 - K['taper_y'] * s) * k + K['shift_y'] * s,
                    s * top(u, v)))
        if w > -0.999:   # the foot stays flat on the plate
            q += outward(u, v, w) * lumps(u, v, w, K['bumps'])
        return M @ q
    n0, f0 = len(p.bm.verts), len(p.bm.faces)
    with p.soft(2):
        lattice_box(p, 'RawPork', chunk, us=(-1.0, -0.5, 0.0, 0.5, 1.0), vs=(-1.0, -0.4, 0.4, 1.0),
                    ws=(-1.0, -0.5, 0.4, 1.0))
    Mi = M.inverted()

    def chunk_fat(q):   # positive on the fat: a wavy band along the back of the top, widest at the left, and that end
        q = Mi @ q
        u, v = q.x / (L / 2), q.y / (D / 2)
        edge = K['fat_v'] + K['fat_k'] * (u + 1) / 2 + 0.1 * math.sin(5.0 * u + 1.0) + 0.05 * math.sin(11.0 * u)
        back = min(v - edge, K['fat_u'] + 0.15 * math.sin(7.0 * v) - u, q.z - 0.35 * K['Ht'])
        left = -u - K['fat_l'] - 0.08 * math.sin(6.0 * v + 0.5) - 0.05 * math.sin(40.0 * q.z)
        return max(back, left)
    paint(p, f0, 'PorkFat', chunk_fat)
    squash_onto(p, n0, PORK_PLATE, fz + K['Ht'] + 0.01, lift=0.0005)
    rest_on_plate(p, n0, f0)
    f1 = len(p.bm.faces)
    # the slice, built standing on its long bottom edge, cut face to -y, then leant back on the chunk, turned right
    SL, ST = K['SL'], K['ST']

    def height(u):   # taller at its left end
        return K['SHl'] + (K['SHr'] - K['SHl']) * (u + 1) / 2
    S = (Matrix.Translation((K['sx'], K['sy'], fz)) @ Matrix.Rotation(math.radians(K['yaw_s']), 4, 'Z') @
         Matrix.Rotation(-math.radians(K['lean_s']), 4, 'X') @ Matrix.Rotation(math.radians(K['roll_s']), 4, 'Y'))

    def slab(u, v, w):   # its outline an oblong with round corners (exponent `oval`), sheared to lean right
        r = (abs(u) ** K['oval'] + abs(w) ** K['oval']) ** (1 / K['oval'])
        if r > 1e-6:
            u, w = u * max(abs(u), abs(w)) / r, w * max(abs(u), abs(w)) / r
        return S @ Vector((u * SL / 2 + K['shear'] * (w + 1) / 2, v * ST / 2, (w + 1) / 2 * height(u)))
    n1 = len(p.bm.verts)
    with p.soft(2):
        lattice_box(p, 'RawPork', slab, us=(-1.0, -0.6, 0.0, 0.6, 1.0), vs=(-1.0, 1.0), ws=(-1.0, -0.4, 0.4, 1.0))
    Si = S.inverted()

    def slice_fat(q):   # positive on the rim of fat round its cut face, widest along its top edge and right end
        q = Si @ q
        t = max(0.0, min(1.0, q.z / height(0.0)))
        u = (q.x - K['shear'] * t) / (SL / 2)
        w = 2 * q.z / height(max(-1.0, min(1.0, u))) - 1
        r = (abs(u) ** K['oval'] + abs(w) ** K['oval']) ** (1 / K['oval'])
        rim = K['rim_b'] + (K['rim_t'] - K['rim_b']) * max(0.0, w) ** 1.5 + K['rim_r'] * max(0.0, u) ** 2
        return r - 1 + rim + 0.03 * math.sin(9.0 * u + 2.0 * w)
    paint(p, f1, 'PorkFat', slice_fat)
    drop_to(p, n1, fz + 0.0004)
    a = math.radians(K['yaw_s'])
    d = Vector((math.sin(a), -math.cos(a), 0.0))
    moved(p, n1, Matrix.Translation(-0.04 * d))   # into the chunk, then out along its face until it only touches
    clear_of(p, n1, f0, f1, d)
    settle(p, n1, PORK_PLATE, lift=0.0003)
    rest_on_plate(p, n1, f0)
    return p.finish('SM_pork', col, sharp=None)


def fish_eye(p, c, nrm, r, pupil=0.55):
    """A round eye set into the head at c, facing nrm: a golden iris domed out of the surface with a dark pupil
    domed out of it in turn, both smooth."""
    R = nrm.to_track_quat('Z', 'Y').to_matrix()
    p.blob(c - nrm * r * 0.12, 1.0, 'FishIris', segs=(14, 7),
           deform=lambda v: R @ Vector((v.x * r, v.y * r, v.z * r * 0.42)))
    rp = r * pupil
    p.blob(c + nrm * r * 0.2, 1.0, 'FishEye', segs=(12, 6),
           deform=lambda v: R @ Vector((v.x * rp, v.y * rp, v.z * rp * 0.4)))


def soft_cube(p, c, size, mat, yaw, tilt=0.0, r=0.006):
    """A cut block or cube (meat, tofu) keeping its shape but with every edge and corner rounded to radius r: a box
    bevelled in three round segments, shaded smooth."""
    p.box((0, 0, 0), size, mat, r=r, seg=3,
          M=Matrix.Translation(c) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(tilt, 4, 'X'))


def soft_block(p, c, size, mat, yaw, round_=0.5, seed=0, jitter=0.0012, levels=2):
    """A cut block of meat (a cube of breast) for the soft() pass: size (x, y, z), its edges and corners rounded off
    over `round_` of each half-size, a little irregular as a knife leaves it (`jitter`), standing on z = c.z, turned
    `yaw` about z."""
    rnd = random.Random(seed)
    M = Matrix.Translation(c) @ Matrix.Rotation(yaw, 4, 'Z')
    k = 1 - round_
    lat = (-1.0, -k, k, 1.0)
    cache = {}

    def F(u, v, w):
        if (u, v, w) not in cache:
            j = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * jitter
            if w < -0.999:
                j.z = 0.0   # the cut face it stands on stays flat
            cache[u, v, w] = M @ (Vector((u * size[0] / 2, v * size[1] / 2, (w + 1) / 2 * size[2])) + j)
        return cache[u, v, w]
    with p.soft(levels):
        lattice_box(p, mat, F, lat, lat, lat)


CHICKEN_PLATE = dict(r=0.1, h=0.045, foot=0.5, sx=0.97, floor=0.028, floor_r=0.72, bulge=0.5)


CK = dict(bx=-0.0118, by=0.0156, yaw=32.0, L=0.154, W=0.102, H=0.054, crown=0.3,
          hw=(0.13, 0.48, 0.8, 0.98, 1.0, 0.94, 0.72), hh=(0.3, 0.55, 0.79, 0.95, 1.0, 0.9, 0.62),
          bumps=((0.75, 0.6, 0.5, 0.35, 0.004),),
          c1=(0.0115, -0.035, 0.046, 0.038, 0.034, 52.7), c2=(0.0555, -0.0076, 0.038, 0.035, 0.031, 40.0),
          front_cut=0.25, back=0.03)


def chicken(col):
    """鸡肉 as the art has it: a plump raw chicken breast lying across a small deep celadon dish, a smooth teardrop,
    its narrow rounded tip to the left lying up the wall of the dish and its thick rounded end to the back right,
    domed across; two small cubes cut from it, each about a quarter as wide as the breast looks, stand on the dish
    in front of it at the right, their edges softly rounded."""
    K = CK
    p = Part()
    fz = footed_dish(p, **CHICKEN_PLATE)
    L, W, H = K['L'], K['W'], K['H']
    M = Matrix.Translation((K['bx'], K['by'], fz)) @ Matrix.Rotation(math.radians(K['yaw']), 4, 'Z')

    US = (-1.0, -0.7, -0.4, 0.0, 0.4, 0.7, 1.0)   # its rings from the tip to the thick end

    def plan(u):   # half-width and height at the ring u
        i = US.index(u)
        return W / 2 * K['hw'][i], H * K['hh'][i]

    def breast(u, v, w):
        hw, h = plan(u)
        if v < 0:   # its front side, where the cubes stand, a little slimmer towards the thick end
            hw *= 1 - K['front_cut'] * max(0.0, u)
        if w < -0.999:   # its underside, narrower so that its sides round under
            q = Vector((u * L / 2, v * hw * 0.78, 0.0))
        elif w < 0.999:   # its sides at mid height
            q = Vector((u * L / 2, v * hw, 0.42 * h))
        else:   # its domed top
            q = Vector((u * L / 2, v * hw * 0.8, h * (1 - K['crown'] * v * v)))
        if w > -0.999:
            q += outward(u, v, w) * lumps(u, v, w, K['bumps'])
        return M @ q
    n0, f0 = len(p.bm.verts), len(p.bm.faces)
    with p.soft(2):
        lattice_box(p, 'RawChicken', breast, us=US,
                    vs=(-1.0, -0.45, 0.45, 1.0), ws=(-1.0, 0.0, 1.0))
    settle(p, n0, CHICKEN_PLATE, lift=0.0005)
    rest_on_plate(p, n0, f0)
    f1 = len(p.bm.faces)
    for i, key in enumerate(('c1', 'c2')):   # the two cubes in front, standing on the floor of the dish
        x, y, a, b, c, deg = K[key]
        n1, f2 = len(p.bm.verts), len(p.bm.faces)
        soft_block(p, Vector((x, y + K['back'], fz)), (a, b, c), 'RawChicken', math.radians(deg), seed=7 + i,
                   levels=1)
        clear_of(p, n1, f0, f2, (0.0, -1.0, 0.0))   # from inside the breast out to the front, until it only touches
        drop_to(p, n1, fz + 0.0004)
        settle(p, n1, CHICKEN_PLATE, lift=0.0003)
        rest_on_plate(p, n1, f0)
        clear_of(p, n1, f0, f2, (0.0, -1.0, 0.0))
    return p.finish('SM_chicken', col, sharp=None)


KIDNEY_PLATE = dict(r=0.1, h=0.0204, foot=0.895, sx=0.834, floor=0.009, floor_r=0.8, bulge=0.915, lip=0.004)


WING_PLATE = dict(r=0.1, h=0.035, foot=0.75, foot_h=0.006, sx=0.97, floor=0.012, floor_r=0.7, bulge=0.5)


DUCK_PLATE = dict(r=0.1, h=0.0203, foot=0.935, sx=1.509, floor=0.009, floor_r=0.8, bulge=0.675, lip=0.004)


DUCK_YAW = math.radians(-53.4)


SKIN_PLATE = dict(r=0.1, h=0.026, foot=0.82, foot_h=0.004, sx=0.885, floor=0.012, floor_r=0.7, bulge=2.7,
                  yaw=math.radians(-2))


def kidney_plate(p):
    return dish(p, **KIDNEY_PLATE)


def wing_plate(p):
    return footed_dish(p, **WING_PLATE)


def duck_plate(p):
    """The oval platter of 鸭, its long axis turned DUCK_YAW from x (back left to front right, as drawn)."""
    n0 = len(p.bm.verts)
    fz = dish(p, **DUCK_PLATE)
    moved(p, n0, Matrix.Rotation(DUCK_YAW, 4, 'Z'))
    return fz


def skin_plate(p):
    return footed_dish(p, **SKIN_PLATE)


TRACED_DUCK = os.path.join(os.path.dirname(__file__), 'traced_duck.json')
# 鸭 traced from its art (trace_duck.py): its pale skin cream on the breast, warmer and pinker on the wings and legs
# (tinted in softly from the art), the follicles over it all (food_pores, as fine as the art paints them), the pink
# cut faces of the knuckles, and the art's brown ink line round every piece
PALETTE.update({'DuckRawSkin': ('#fff0d8', '#f6caa6'),    # the body's cream skin
                'DuckRawLimb': ('#fedcc0', '#f2b494'),    # the wings and drumsticks, a warmer peach
                'DuckRawCut': ('#f2a088', '#d47e66'),     # the knuckles' pink cut faces
                'DuckRawBone': ('#dc7466', '#b85a4c'),    # and the deeper pink in their middles
                'DuckRawInk': ('#7a3a20', '#5a2814'),     # the few lines the art draws inside a piece
                'DuckRawGlint': ('#fffaf2', '#f8e8d8')})  # the wet white glints the art paints on the raw skin
GLOSS.update({'DuckRawSkin': 0.15, 'DuckRawLimb': 0.15, 'DuckRawCut': 0.4, 'DuckRawBone': 0.4, 'DuckRawInk': 0.1,
              'DuckRawGlint': 0.3})   # low: the shader's sun is behind the eye, its sheen would wash every bulge out
VIVID.update({'DuckRawSkin': 0.1, 'DuckRawLimb': 0.15, 'DuckRawCut': 0.5, 'DuckRawBone': 0.5, 'DuckRawInk': 0.3,
              'DuckRawGlint': 0.1})
VTINT.update(dict.fromkeys(('DuckRawSkin', 'DuckRawLimb', 'DuckRawCut', 'DuckRawBone', 'DuckRawInk',
                            'DuckRawGlint'), 1.0))
DETAIL.update({'DuckRawSkin': ('food_pores', 18, '#eba37f', 0.7, 0.6),
               'DuckRawLimb': ('food_pores', 18, '#e8957a', 0.65, 0.6),
               'DuckRawCut': ('food_fiber', 30, '#c8604c', 0.35, 0.3)})


SUN = Vector((-0.3, -0.8, 0.52)).normalized()   # the icon bake's sun, as preview_wc.py has it


def art_colours(p, f0, path, weight=0.85, lift=0.0, relight=True, ink='#5a2f10'):
    """Tints the faces added to p since it had f0 toward the art's own colour where the art's view sees each point
    (the colours a trace stores with its paint, its ink lines and glints taken out), softly, all over: the art's
    cream, peach and pink and its painted light and shade, as the watercolour light alone can't give them. The art's
    ink line that traced_dish drew round each piece stays where it is strong. `lift` takes each colour that part of
    the way to white first; with `relight`, each is lightened by as much as the watercolour light will darken it
    there (it shines from in front, the art's from above: what faces up is the art's lightest)."""
    import json
    import numpy as np
    data = json.load(open(path, encoding='utf-8'))
    col = np.load(path.replace('.json', '_paint.npz'))['colour'].astype(np.float32)
    cam, sc = data['camera'], data['colour_scale']
    se, ce = math.sin(math.radians(cam['el'])), math.cos(math.radians(cam['el']))
    H, W = col.shape[:2]
    lay = p.bm.loops.layers.float_color.get('Tint')
    ink_lin = linear(ink)
    inked = set()
    if lay is not None:
        for f in p.bm.faces[f0:]:
            for loop in f.loops:
                c = loop[lay]
                if c[3] < 0.55 and max(abs(c[i] - ink_lin[i]) for i in range(3)) < 0.01:   # traced_dish's ink
                    inked.add(tuple(loop.vert.co))

    def field(q, n):
        if tuple(q) in inked:
            return None
        x = (cam['u0'] + cam['k'] * q.x) * sc
        y = (cam['v0'] - cam['k'] * (q.y * se + q.z * ce)) * sc
        x0, y0 = min(max(int(x), 0), W - 2), min(max(int(y), 0), H - 2)
        tx, ty = min(max(x - x0, 0.0), 1.0), min(max(y - y0, 0.0), 1.0)
        g = col[y0:y0 + 2, x0:x0 + 2]
        c = (g[0, 0] * (1 - tx) + g[0, 1] * tx) * (1 - ty) + (g[1, 0] * (1 - tx) + g[1, 1] * tx) * ty
        c = c + (255.0 - c) * lift
        if relight:   # the icon's sun and the shader's four soft steps, undone
            lum = 0.25 + 0.75 * max(n.dot(SUN), 0.0)
            st = lambda e0, e1: min(max((lum - e0) / (e1 - e0), 0.0), 1.0) ** 2 * (3 - 2 * min(max((lum - e0) / (e1 - e0), 0.0), 1.0))
            steps = 0.45 * st(0.25, 0.42) + 0.37 * st(0.42, 0.62) + 0.18 * st(0.62, 0.9)
            lin = (c / 255.0) ** 2.2   # the shader: steps·base + (1 - steps)·(0.8·0.54·base + 0.2·blue)
            lin = (lin - 0.2 * (1 - steps) * np.array([0.34, 0.36, 0.55])) / (steps + 0.432 * (1 - steps))
            c = 255.0 * np.clip(lin, 0, 1) ** (1 / 2.2)
        return '#%02x%02x%02x' % tuple(int(min(max(v, 0), 255)) for v in c), weight
    p.tint(f0, field)


def duck(col):
    """鸭 traced from its art (trace_duck.py writes traced_duck.json): a whole plucked duck lying breast up along an
    oval celadon platter, its neck end at the back left, the far wing showing over its back, the near wing folded at
    its side with its pointed tip flap turned over, and the two drumsticks at the front right ending in knuckles cut
    pink. Every piece follows an outline traced in the art: the body a plump rounded lens, flat underneath on the
    platter, the rest draped over it and the platter; the colours where the art has them, the art's ink line round
    each."""
    from .plates import traced_dish
    p = Part()
    duck_plate(p)
    f0 = len(p.bm.faces)
    traced_dish(p, TRACED_DUCK, ink='#5a2f10')
    art_colours(p, f0, TRACED_DUCK, lift=0.1)
    return p.finish('SM_duck', col, sharp=None)


def kidney_bean(p, c, yaw, L, W, H, bow=0.011, dent=0.011, tilt=0.0):
    """A plump pork kidney for soft(): a bean L long, W wide and H high lying along yaw, curved round its hollow side
    (the hilum, local +y) with a dent in the middle of it; flat underneath. A 12 x 8 cage."""
    def bean(v):
        t = v.x / (L / 2)
        side = min(1.0, max(0.0, (v.y / (W / 2) + 0.3) / 1.0))   # 0 on the outer curve, 1 at the hollow, top and all
        y = v.y - bow * (1 - t * t) - dent * math.exp(-((t + 0.22) / 0.28) ** 2) * side ** 1.5
        q = Vector((v.x, y, v.z if v.z > 0 else max(v.z * 0.8, -H * 0.36)))
        return Matrix.Rotation(tilt, 3, 'X') @ q
    p.blob(c, 1.0, 'KidneyRed', squash=(L / 2, W / 2, H / 2), segs=(12, 8), rot=yaw, deform=bean)


def kidney_fat(p, c, yaw, size, seed):
    """The lump of pale fat tucked into a kidney's hilum, for soft(): a knobbly blob."""
    ph = random.Random(seed).uniform(0, 6)
    p.blob(c, size, 'KidneyFat', squash=(1.5, 0.85, 0.9), segs=(8, 5), rot=yaw,
           deform=lambda v: v * (1 + 0.14 * math.sin(3 * math.atan2(v.y, v.x) + ph) + 0.1 * math.cos(4 * v.z / size + ph)))


def kidney(col):
    """猪腰子: two plump dark-red pork kidneys side by side on a shallow celadon plate, the back one to the left, both
    lying from front left to back right with their hollow side to the back left, a lump of pale fat in each hollow.
    Placed from art_match's grid (cm, read at the plate floor)."""
    p = Part()
    fz = kidney_plate(p)
    L, W, H = _tv('kL', 0.143), _tv('kW', 0.080), _tv('kH', 0.073)
    with p.soft():
        for (x, y, deg, fat) in ((_tv('k1x', -0.0225), _tv('k1y', 0.017), _tv('k1a', 48.6), (-0.016, 0.012, 0.02)),
                                 (_tv('k2x', 0.013), _tv('k2y', -0.04), _tv('k2a', 47), (-0.016, 0.012, 0.02))):
            yaw = math.radians(deg)
            c = Vector((x, y, fz + H * 0.36 - 0.002))
            kidney_bean(p, c, yaw, L, W, H, bow=_tv('kbow', 0.01), dent=_tv('kdent', 0.02))
            kidney_fat(p, c + Matrix.Rotation(yaw, 3, 'Z') @ Vector(fat), yaw, 0.015, seed=deg)
    return p.finish('SM_kidney', col, sharp=None)


TRACED_WING = os.path.join(os.path.dirname(__file__), 'traced_wing.json')
# 鸡翅 traced from its art (trace_wing.py): the pink skin with its cream edges, the light and shade the art paints
# (tinted in from the art), fine wrinkles across it (food_wingskin), the wet glints along them, and the pink meat of
# the cut ends with its deeper red, and the art's brown ink line round every piece
PALETTE.update({'WingRawSkin': ('#fde2cc', '#f2b89c'),    # the raw skin, pale pink
                'WingRawMeat': ('#ec7a6d', '#c85a50'),    # the pink meat at the cut ends
                'WingRawDeep': ('#d0584e', '#a8443c'),    # its deeper red
                'WingRawGlint': ('#fffaf4', '#f6e4dc'),   # the wet white glints
                'WingRawInk': ('#7a3a20', '#5a2814')})    # the few lines the art draws inside a wingette
GLOSS.update({'WingRawSkin': 0.15, 'WingRawMeat': 0.4, 'WingRawDeep': 0.4, 'WingRawGlint': 0.3, 'WingRawInk': 0.1})
VIVID.update({'WingRawSkin': 0.15, 'WingRawMeat': 0.5, 'WingRawDeep': 0.5, 'WingRawGlint': 0.1, 'WingRawInk': 0.3})
VTINT.update(dict.fromkeys(('WingRawSkin', 'WingRawMeat', 'WingRawDeep', 'WingRawGlint', 'WingRawInk'), 1.0))
DETAIL.update({'WingRawSkin': ('food_wingskin', 18, '#fff6ee', 0.85, 0.35),
               'WingRawMeat': ('food_fiber', 30, '#b84c44', 0.35, 0.3)})


def wing(col):
    """鸡翅 traced from its art (trace_wing.py writes traced_wing.json): three plump raw wingettes on a deep celadon
    plate, one at the back right, one at the back left lying over its end, one in front over both, each rolling at
    its ends into cuts that show the pink meat. Every wingette follows its outline in the art: a plump rounded lens,
    flat underneath on the plate, kept in front of those it lies over; the colours where the art has them, the art's
    ink line round each."""
    from .plates import traced_dish
    p = Part()
    wing_plate(p)
    f0 = len(p.bm.faces)
    traced_dish(p, TRACED_WING, ink='#5a2f10')
    art_colours(p, f0, TRACED_WING, lift=0.1)
    return p.finish('SM_wing', col, sharp=None)


def tofu(col):
    """豆腐: a block of tofu on a thick-based celadon plate, turned so that one edge points at the viewer, and two
    small cubes cut from it at the front right, turned the same way; every edge softly rounded."""
    p = Part()
    fz = dish(p, 0.1, 0.045, foot=0.52, sx=0.953, floor=0.03, floor_r=0.74, bulge=0.5)
    soft_cube(p, (-0.005, 0.007, fz + 0.028), (0.088, 0.06, 0.0565), 'TofuWhite', 0.646, r=0.005)
    soft_cube(p, (0.02, -0.0456, fz + 0.016), (0.032, 0.032, 0.0323), 'TofuWhite', 0.69, r=0.004)
    soft_cube(p, (0.055, -0.0192, fz + 0.016), (0.032, 0.032, 0.032), 'TofuWhite', 0.5, r=0.004)
    return p.finish('SM_tofu', col, sharp=None)


def arc(cy, cz, r, a0, a1, n):
    """n points round the circle of radius r about (cy, cz) from angle a0 to a1 (degrees: 0 is +y, 90 is +z), the
    first left out: the turn of a fold in a sheet's profile."""
    return [(cy + r * math.cos(math.radians(a0 + (a1 - a0) * k / n)),
             cz + r * math.sin(math.radians(a0 + (a1 - a0) * k / n))) for k in range(1, n + 1)]


def skin_sheet(p, M, prof, L, t=0.006, nx=5, ends=None, deform=None):
    """A sheet of pork skin as a coarse cage for soft(), placed by M: its mid-line across it, prof [(y, z)] (folds and
    all), swept along local x from -L/2 to L/2, or between the ends (x0, x1) = ends(s, y, z) given for each profile
    point (s runs 0 to 1 along it), for slanted or shaped cut ends; t thick. deform(q, u, s) bends it, u running 0 to 1
    from one cut end to the other. The rind (to the left of the profile's direction) in PorkSkin, the meat side in Meat,
    the free edges along the profile's two ends and the cut faces across the sweep's ends in Fat."""
    n = len(prof)
    nrm = []
    for i in range(n):
        (ya, za), (yb, zb) = prof[max(i - 1, 0)], prof[min(i + 1, n - 1)]
        d = math.hypot(yb - ya, zb - za)
        nrm.append((-(zb - za) / d, (yb - ya) / d))
    tmp = bmesh.new()
    grid = []
    for j in range(nx):
        u = j / (nx - 1)
        row = []
        for i, ((y, z), (ny, nz)) in enumerate(zip(prof, nrm)):
            s = i / (n - 1)
            x0, x1 = ends(s, y, z) if ends else (-L / 2, L / 2)
            pair = []
            for side in (1, -1):
                q = Vector((x0 + (x1 - x0) * u, y + side * ny * t / 2, z + side * nz * t / 2))
                pair.append(tmp.verts.new(M @ (deform(q, u, s) if deform else q)))
            row.append(pair)
        grid.append(row)
    mats = []
    for j in range(nx - 1):
        for i in range(n - 1):
            tmp.faces.new((grid[j][i][0], grid[j + 1][i][0], grid[j + 1][i + 1][0], grid[j][i + 1][0]))
            tmp.faces.new((grid[j][i][1], grid[j][i + 1][1], grid[j + 1][i + 1][1], grid[j + 1][i][1]))
            mats += ['PorkSkin', 'Meat']
        for i in (0, n - 1):   # the free edges
            tmp.faces.new((grid[j][i][0], grid[j][i][1], grid[j + 1][i][1], grid[j + 1][i][0]))
            mats.append('Fat')
    for j in (0, nx - 1):      # the cut ends
        for i in range(n - 1):
            tmp.faces.new((grid[j][i][0], grid[j][i + 1][0], grid[j][i + 1][1], grid[j][i][1]))
            mats.append('Fat')
    piece_in_colours(p, tmp, mats)


def skin(col):
    """猪肉皮: sheets of pork skin folded and piled on a celadon plate, as drawn: on top a big sheet folded in a Z, the
    open end of its folds to the front right, where the pink inside shows, its upper layer drooping to the front left;
    a sheet folded over at the front left showing its curl, another folded at the right, and three sheets leaning up
    against the back of the plate. Placed from the art (cm, read off it at the plate floor and above)."""
    p = Part()
    fz = skin_plate(p)
    T = _tv
    t = T('t', 0.008)

    def place(x, y, deg):
        return Matrix.Translation((x, y, fz)) @ Matrix.Rotation(math.radians(deg), 4, 'Z')

    def lean(W, lift, k=4, p_=1.8):   # a single sheet across, rising to its far side by `lift`
        return [(W * i / k, t / 2 + lift * (i / k) ** p_) for i in range(k + 1)]

    def bent(amp=0.003, ph=0.0, bow=0.0, tilt=0.0):   # waves along it, the far side bowed back and tilted
        return lambda q, u, s: Vector((q.x, q.y + bow * (1 - (2 * u - 1) ** 2) * s,
                                       q.z + amp * math.sin(2 * math.pi * u + ph) * (0.4 + s) + tilt * (u - 0.5) * s))
    f_start = len(p.bm.faces)
    pieces = []   # (M, profile, L, deform, ends, drape over the pieces before it)
    # three sheets leaning up against the back: right, the middle one behind, whose corner is the highest point of the
    # pile, and in front of its lower left the left one
    pieces.append((place(T('d2x', 0.002), T('d2y', 0.03), T('d2a', -42)), lean(T('d2w', 0.045), T('d2l', 0.022)),
                   T('d2L', 0.085), bent(0.003, 0.5, T('d2b', 0.012), T('d2t', 0.0)), None, False))
    pieces.append((place(T('d1x', -0.012), T('d1y', 0.04), T('d1a', -20)), lean(T('d1w', 0.04), T('d1l', 0.03)),
                   T('d1L', 0.06), bent(0.003, 1.7, 0.0, T('d1t', -0.012)), None, True))
    pieces.append((place(T('ex', -0.03), T('ey', 0.022), T('ea', -12)), lean(T('ew', 0.033), T('el', 0.016)),
                   T('eL', 0.055), bent(0.002, 2.4, 0.0, T('et', 0.004)), None, True))
    # the sheet folded at the right: its folds to the right, its far end showing at the back
    R = T('cR', 0.009)
    prof = [(T('cW', 0.045), t / 2), (0.02, t / 2), (0.0, t / 2)] + arc(0.0, t / 2 + R, R, 270, 90, 4) +            [(0.02, t / 2 + 2 * R), (T('cW', 0.045), t / 2 + 2 * R + 0.003)]
    pieces.append((place(T('cx', 0.068), T('cy', -0.005), T('ca', 75)), prof, T('cL', 0.075), bent(0.003, 0.9), None,
                   True))
    # the sheet folded over at the front left: the top layer turned under at the left into a round curl, lying close
    # on the bottom layer beyond it; its open end to the front left
    R = T('bR', 0.008)
    Wb_ = T('bW', 0.08)
    prof = [(Wb_, t / 2), (Wb_ * 0.5, t / 2), (0.0, t / 2)] + arc(0.0, t / 2 + R, R, 270, 90, 4) +            [(0.014, t / 2 + 2 * R - 0.002), (0.03, t * 1.5 + 0.002), (Wb_ * 0.65, t * 1.5 + 0.001), (Wb_, t * 1.5)]
    Lb = T('bL', 0.06)
    pieces.append((place(T('bx', -0.069), T('by', -0.012), T('ba', -135)), prof, Lb, bent(0.002, 2.0),
                   lambda s, y, z: (-Lb + T('bs', 0.0) * y, 0.0), True))
    # the big sheet on top, folded in a Z: bottom layer, right fold, lower layer, left fold, middle layer, right fold,
    # and the top layer drooping to its free edge at the front left; its folds' open end at the front right, from its
    # right corner (the origin) to its front corner, the folds running back to its back corner, the top layer's free
    # edge to its left corner. The layers settle lower towards the back.
    R3, R2, R1 = T('aR3', 0.008), T('aR2', 0.006), T('aR1', 0.01)
    zl = t / 2 + 2 * R3
    zm = zl + 2 * R2
    zt = zm + 2 * R1
    Wb, Wl, Wt = T('aWb', 0.05), T('aWl', 0.035), T('aWt', 0.062)
    prof = ([(Wb, t / 2), (Wb * 0.5, t / 2), (0.0, t / 2)] + arc(0.0, t / 2 + R3, R3, 270, 90, 3)
            + [(Wl * 0.5, zl), (Wl, zl)] + arc(Wl, zl + R2, R2, -90, 90, 3) + [(Wl * 0.5, zm), (0.0, zm)]
            + arc(0.0, zm + R1, R1, 270, 90, 3)
            + [(Wt * 0.3, zt + 0.002), (Wt * 0.6, zt - T('ad1', 0.004)), (Wt * 0.85, zt - T('ad2', 0.012)),
               (Wt, zt - T('ad3', 0.022))])
    s0, s1, La = T('as0', 0.32), T('as1', 0.49), T('aL', 0.108)
    sink = T('asink', 0.25)
    pieces.append((place(T('ax', 0.06), T('ay', -0.056), T('aa', 125)), prof, La,
                   lambda q, u, s: Vector((q.x, q.y, q.z * (1 - sink * u) + 0.003 * math.sin(5 * u + 3 * s))),
                   lambda s, y, z: (s0 * y, La + s1 * y), True))
    for M, prof, L, deform, ends, _ in pieces:
        n0 = len(p.bm.verts)
        with p.soft():
            skin_sheet(p, M, prof, L, t=t, nx=5, ends=ends, deform=deform)
        settle(p, n0, SKIN_PLATE)
    return p.finish('SM_skin', col, sharp=None)


def carp(p, M, belly='CarpSkin', fins='FishFin', tail='CarpFin', floor=0.012):
    """The carp of 普通整鱼, smooth and rounded, built in its own frame (snout at the origin, x along the body, z to
    its back, the near flank to -y) and placed by M; then slid along the art's line of sight to lie on the plate
    floor at `floor`. Scaled skin (the head smooth), its back painted grey and dappled, shading down to the pale
    belly (carp_colour), a big round eye, pink lips, the gill cover's edge, a forked tail and a long dorsal fin with
    thickness and rounded edges, pink pectoral, pelvic and anal fins, and a pelvic fin flopped on the plate in
    front."""
    n0, f0 = len(p.bm.verts), len(p.bm.faces)
    st = refined(CARP_BODY)
    tops = [(x, t) for x, t, b, w in CARP_BODY]
    bots = [(x, b) for x, t, b, w in CARP_BODY]
    with p.soft():
        hull(p, st, belly)
    gill = sorted((z, x) for x, z in CARP_GILL)
    paint(p, f0, 'CarpHead', lambda q: interp(gill, q.z) - q.x)   # the head, in front of the gill cover: no scales
    nb = len(p.bm.verts) - n0
    view = M.to_3x3().inverted() @ VIEW   # the line of sight in the fish's frame
    cast = caster(p, f0, view)
    with p.soft():
        slab(p, CARP_TAIL, tail, 0.0045)
        slab(p, CARP_DORSAL, tail, 0.0035)
        slab(p, [(0.2, -0.039), (0.2078, -0.0357), (0.2234, -0.026), (0.2354, -0.0218), (0.2404, -0.0224),
                 (0.2414, -0.0267), (0.2369, -0.0318), (0.2224, -0.0384), (0.2062, -0.0405)], fins, 0.0035)   # anal
        slab(p, [(0.147, -0.043), (0.153, -0.0423), (0.1652, -0.0419), (0.1787, -0.0436), (0.182, -0.0439),
                 (0.1898, -0.051), (0.1774, -0.0515), (0.1622, -0.0503), (0.149, -0.047)], fins, 0.0035)      # pelvic
        inner, outer = [], []   # the pectoral fin, lying along the flank, its tip lifting off
        for (x, z) in ((0.088, -0.0202), (0.1018, -0.0203), (0.1146, -0.023), (0.1253, -0.0274), (0.1323, -0.0319),
                       (0.1355, -0.0353), (0.1266, -0.0381), (0.115, -0.0411), (0.1032, -0.0399), (0.0931, -0.0344),
                       (0.0867, -0.0277)):
            hit, nrm = cast((x, 0.0, z))
            lift = 0.0006 + 0.004 * max(0.0, (x - 0.09) / 0.045) ** 1.5
            inner.append(hit + nrm * lift)
            outer.append(hit + nrm * (lift + 0.0035))
        shell(p, inner, outer, fins)
        gill = []   # the gill cover's rounded edge
        for (x, z) in CARP_GILL:
            hit, nrm = cast((x, 0.0, z))
            gill.append(hit + nrm * 0.0006)
        p.tube(gill, 0.0017, tail, sides=4)
        for pts, r in ((((0.019, 0.0095, -0.0038), (0.011, 0.0088, -0.001), (0.0045, 0.0062, 0.0008), (0.0015, 0.0, 0.0014)),
                        0.0032),
                       (((0.017, 0.0098, -0.0115), (0.01, 0.009, -0.0088), (0.0045, 0.006, -0.0068), (0.0018, 0.0, -0.0062)),
                        0.0036)):   # the lips, rolled round the front of the snout
            p.tube([(x, -y, z) for x, y, z in pts] + [(x, y, z) for x, y, z in reversed(pts[:-1])], r, fins, sides=6)
    hit, nrm = cast((0.0373, 0.0, 0.0059))
    fish_eye(p, hit, nrm, 0.0084, pupil=0.55)
    hit, nrm = cast((0.0158, 0.0, 0.0072))
    p.blob(hit, 0.0016, 'FishEye', segs=(6, 4))   # nostril
    p.tint(f0, carp_colour(tops, bots))
    moved(p, n0, M)
    rest_on(p, n0, floor + 0.0003, nb=nb)
    with p.soft():   # the front pelvic fin, flopped on the plate in front of the belly
        lo = [M @ Vector((x, 0.0, zz)) for x, zz in ((0.0687, -0.0426), (0.0773, -0.044), (0.092, -0.0468),
                                                    (0.1068, -0.0491), (0.1086, -0.0583), (0.1115, -0.0646),
                                                    (0.1029, -0.0644), (0.0872, -0.0597), (0.0747, -0.0511))]
        flat = lay_flat(lo, floor + 0.0022)
        shell(p, [q - Vector((0, 0, 0.0018)) for q in flat], [q + Vector((0, 0, 0.0018)) for q in flat], fins)


# the edge of the carp's gill cover in its side view (x back from the snout, z up), top to bottom
CARP_GILL = [(0.0756, 0.0295), (0.0847, 0.0183), (0.0891, 0.0089), (0.0909, -0.0003), (0.09, -0.0062),
             (0.0878, -0.0137), (0.084, -0.0223), (0.0783, -0.0287), (0.0737, -0.0326), (0.0665, -0.0343)]


def carp_colour(tops, bots):
    """普通整鱼's carp painted across its pale skin as the art has it, for Part.tint: the back grey, dappled darker
    like scales, shading down through a bronze flank to the pale belly; tops and bots its back's and belly's
    heights along it."""
    GREY, DARK, BRONZE = '#6f757d', '#4c5159', '#c8ad84'

    def field(q, n):
        t, b = interp(tops, q.x), interp(bots, q.x)
        h = (q.z - b) / max(t - b, 1e-6)        # 0 along the belly, 1 along the back
        w = 0.9 * ramp(0.48, 0.8, h + 0.08 * (dab(q, 0.008) - 0.5))
        warm = 0.5 * ramp(0.12, 0.35, h) * ramp(0.75, 0.5, h) * (0.6 + 0.4 * dab(q, 0.01, 9.0))   # the bronze flank
        if warm > w:
            return BRONZE, warm
        return (mix(GREY, DARK, ramp(0.45, 0.75, dab(q, 0.006, 5.0))), w) if w > 0.02 else None
    return field


def guiyu_colour(tops, bots):
    """鳜鱼's skin painted across it as the art has it, for Part.tint: olive-brown along the back, dappled darker,
    its edge ragged, over the pale yellowish belly (its dark blotches are laid on by spots()); tops and bots its
    back's and belly's heights along it."""
    OLIVE, DARK = '#a08c4c', '#71623a'
    share = [(0.0, 0.36), (0.05, 0.4), (0.1, 0.55), (0.2, 0.55), (0.24, 0.5)]   # of the depth that is olive back

    def field(q, n):
        t, b = interp(tops, q.x), interp(bots, q.x)
        h = (t - q.z) / max(t - b, 1e-6) - interp(share, q.x)   # below the back's edge > 0
        w = 0.9 * ramp(0.06, -0.06, h + 0.1 * (dab(q, 0.007) - 0.5))
        return (mix(OLIVE, DARK, ramp(0.45, 0.75, dab(q, 0.005, 7.0))), w) if w > 0.02 else None
    return field


def fish(col):
    """普通整鱼: a whole carp lying diagonally across an oval celadon plate, head to the front left, its tail flicked
    up over the rim at the back right: grey back, pale belly, pink fins."""
    p = Part()
    inside = platter(p, 0.16, 0.772, 0.026, yaw=math.radians(52.5), foot=0.6, floor=0.012, floor_r=0.75, lip=0.0055,
                     bulge=0.5)
    n0 = len(p.bm.verts)
    carp(p, Matrix.Translation((-0.1243, -0.0291, 0.012)) @ Matrix.Rotation(math.radians(30), 4, 'Z')
         @ Matrix.Rotation(math.radians(-40), 4, 'X'))
    onto_platter(p, n0, inside)
    return p.finish('SM_fish', col, sharp=None)


def mandarin_fish(col):
    """鳜鱼: a mandarin fish lying across an oval celadon plate, its gaping head to the front left, spiny dorsal fin
    up and rounded tail at the back right: olive back and cream belly blotched dark all over."""
    p = Part()
    inside = platter(p, 0.155, 0.792, 0.0314, yaw=math.radians(43.6), foot=0.6, floor=0.013, floor_r=0.75, lip=0.0055,
                     bulge=0.5)
    n0 = len(p.bm.verts)
    guiyu(p, Matrix.Translation((-0.128, 0.013, 0.013)) @ Matrix.Rotation(math.radians(15), 4, 'Z')
          @ Matrix.Rotation(math.radians(-36), 4, 'X'))
    onto_platter(p, n0, inside)
    return p.finish('SM_mandarin_fish', col, sharp=None)


def fish_head(col):
    """大鱼头: a big fish head resting on its throat on a flower-rimmed celadon plate, its gaping mouth raised to the
    front left and the pink cut face at the back right: dark grey crown, pale cheek, a big eye, red gills."""
    p = Part()
    inside = platter(p, 0.125, 0.834, 0.0267, yaw=math.radians(-88.9), foot=0.6, floor=0.012, floor_r=0.75, lip=0.0055,
                     bulge=0.5, n=64)
    n0 = len(p.bm.verts)
    yutou(p, Matrix.Translation((-0.0818, 0.1247, 0.012)) @ Matrix.Rotation(math.radians(-15), 4, 'Z')
          @ Matrix.Rotation(math.radians(25), 4, 'Y') @ Matrix.Rotation(math.radians(-30), 4, 'X'))
    onto_platter(p, n0, inside)
    return p.finish('SM_fish_head', col, sharp=None)


# The crab as the art paints it, not a toy: its blue-grey kept grey (little of the rich food colour), mottled with
# olive (food_shell), its tan rims, orange-brown tips and cream-tan undersides painted across it (crab_colour).
VIVID.update({'CrabShell': 0.55, 'CrabBelly': 0.5})
DETAIL.update({'CrabShell': ('food_shell', 18, '#9a8d5a', 0.7, 0.3)})
VTINT.update({'CrabShell': 1.0})


CRAB_MAP = (639.0, 708.5, 6500.0)   # the art's px of x = 0 and of y = z = 0, and its px per metre (from its plate)
CRAB_PLATE = dict(r=0.1, h=0.0153, foot=0.94, foot_h=0.0004, sx=0.8027, lip=0.0023, bulge=1.38, floor=0.0085,
                  floor_r=0.8)


def crab_at(px, py, z):
    """The point at height z that the crab's art shows at pixel (px, py), seen from in front and 35° up."""
    cx, cy, s = CRAB_MAP
    return Vector(((px - cx) / s, ((cy - py) / s - z * math.cos(ART_EL)) / math.sin(ART_EL), z))


def crab_plate(p, n=48):
    """The crab's 青瓷 plate, fitted to the art: a broad flat base rounding up into a low wall and a rolled lip, and
    inside, a slope down to a flat floor; a lean profile, so the crab keeps most of the triangles. Returns
    inside(x, y): the height of its top surface under a point (None beyond the rim)."""
    k = CRAB_PLATE
    r, h, lip, fl, sx = k['r'], k['h'], k['lip'], k['floor'], k['sx']
    rf, fh, fr = k['foot'] * r, k['foot_h'], k['floor_r'] * r
    prof = [(0.0, 0.0025), (rf - 0.004, 0.0025), (rf - 0.0012, 0.0), (rf + 0.0008, 0.0), (rf + 0.0022, 0.0012)]
    x0, z0 = rf + 0.0048, max(fh, 0.003)
    prof.append((x0, z0))
    for t in (0.45, 0.8):   # the outer wall
        prof.append((x0 + (r - lip - x0) * (1 - (1 - t) ** (1 + k['bulge'])), z0 + (h - lip - z0) * t ** (1 + k['bulge'])))
    i0 = len(prof)
    for a in (-0.075, 0.25, 0.575, 0.9):   # the rolled lip, from the outside over the top to the inside
        prof.append((r - lip + lip * math.cos(a * math.pi), h - lip + lip * math.sin(a * math.pi)))
    xa, za = prof[-1]
    for t in (0.35, 0.7):   # the inside, steep under the lip and levelling out into the floor
        prof.append((xa + (fr - xa) * t, fl + (za - fl) * (1 - t) ** 2))
    prof += [(fr, fl), (fr * 0.5, fl), (0.0, fl)]
    p.lathe(prof, 'Celadon', n=n, close_ends=False, M=Matrix.Diagonal((sx, 1.0, 1.0, 1.0)))
    top = sorted(prof[i0:-2])

    def inside(x, y):
        rho = math.hypot(x / sx, y)
        if rho > r:
            return None
        if rho <= fr:
            return fl
        for (ra, za_), (rb, zb) in zip(top, top[1:]):
            if ra <= rho <= rb:
                return za_ + (zb - za_) * (rho - ra) / max(rb - ra, 1e-9)
        return top[-1][1]
    return inside


def crab_onto(p, n0, inside, clear=0.0008):
    """Lifts whatever was added to p since it had n0 vertices out of the plate: onto its top surface, `clear` above."""
    p.bm.verts.ensure_lookup_table()
    for v in p.bm.verts[n0:]:
        z = inside(v.co.x, v.co.y)
        if z is not None and v.co.z < z + clear:
            v.co.z = z + clear


def closed_curve(pts, n, density=lambda i: 1.0):
    """n points along the closed Catmull-Rom curve through pts (Vectors), spaced evenly but packed density(i) times
    closer on the stretch from point i, each with the index of the point its stretch starts from."""
    m, dense = len(pts), []
    for i in range(m):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[(i + 1) % m], pts[(i + 2) % m]
        for j in range(12):
            u = j / 12
            dense.append((0.5 * ((2 * p1) + (p2 - p0) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                                 + (3 * p1 - p0 - 3 * p2 + p3) * u ** 3), i))
    acc = [0.0]
    for (a, i), (b, _) in zip(dense, dense[1:] + dense[:1]):
        acc.append(acc[-1] + (b - a).length * density(i))
    out, k = [], 0
    for j in range(n):
        t = acc[-1] * j / n
        while acc[k + 1] < t:
            k += 1
        f = (t - acc[k]) / max(acc[k + 1] - acc[k], 1e-12)
        out.append((dense[k][0].lerp(dense[(k + 1) % len(dense)][0], f), dense[k][1]))
    return out


# the crab's carapace as the art draws it: its outline (px) round from the left tip over the back, at its rim, and
# the stretches of it (from point a up to b) edged with rounded teeth, big along the sides and small at the front
CRAB_SHELL = [(330, 523), (345, 478), (372, 445), (405, 418), (445, 397), (490, 380), (540, 360), (590, 345),
              (640, 338), (690, 340), (740, 347), (790, 360), (835, 380), (870, 405), (895, 432), (908, 462),
              (902, 495), (880, 520), (848, 540), (790, 555), (720, 572), (650, 590), (612, 600), (560, 605),
              (505, 600), (450, 588), (400, 568), (360, 548)]
CRAB_TEETH = ((0, 5, 1.0), (13, 18, 0.6), (19, 22, 0.4), (22, 28, 1.0))


def carapace(p, rim, dome, base, n=60, grow=1.04, tooth=0.0045, bumps=0.0018):
    """The crab's shell for soft(): one cage through the art's outline at height `rim` (grown by `grow` against
    the shrinking of the subdivision), domed `dome` above it with gentle bumps, rounded under the rim and closed
    underneath at `base` (CrabBelly). Its rim points crowd three times as close on the toothed stretches, where every
    third one stands out by `tooth` (times the stretch's size), rounding into blunt teeth."""
    def size(i):
        return next((k for a, b, k in CRAB_TEETH if a <= i < b), 0.0)
    outline = [crab_at(px, py, rim) for px, py in CRAB_SHELL]
    ring = closed_curve(outline, n, lambda i: 3.0 if size(i) else 1.0)
    even = closed_curve(outline, n)   # the inner rings keep evenly spaced points, so the dome shades smooth
    c = sum((q for q, _ in even), Vector()) / n
    tmp = bmesh.new()

    def loop(f, z, crowd, teeth=0.0, bump=0.0):
        out = []
        for j, (q, i) in enumerate(ring):
            d = even[j][0].lerp(q, crowd) - c
            d.z = 0.0
            t = ring[(j + 1) % n][0] - ring[j - 1][0]
            nrm = Vector((-t.y, t.x, 0.0)).normalized()
            if nrm.dot(d) < 0:
                nrm = -nrm
            off = teeth * size(i) * (1.0 if j % 3 == 0 else 0.0)
            lump = bump * math.cos(5 * math.atan2(d.y, d.x) + 0.6)
            out.append(tmp.verts.new(Vector((c.x, c.y, z + lump)) + d * f * grow + nrm * off))
        return out
    rings = [loop(0.45, rim + dome * 0.97, 0.0), loop(0.88, rim + dome * 0.5, 0.6, bump=bumps),
             loop(1.0, rim, 1.0, tooth), loop(0.97, rim - 0.0045, 1.0, tooth * 0.8), loop(0.72, base, 0.3)]
    mats = ['CrabShell', 'CrabShell', 'CrabShell', 'CrabBelly']
    fm = []
    tmp.faces.new(rings[0])
    fm.append('CrabShell')
    for ra, rb, m in zip(rings, rings[1:], mats):
        for j in range(n):
            tmp.faces.new((ra[j], ra[(j + 1) % n], rb[(j + 1) % n], rb[j]))
            fm.append(m)
    tmp.faces.new(list(reversed(rings[-1])))
    fm.append('CrabBelly')
    piece_in_colours(p, tmp, fm)


def ramp(e0, e1, x):
    """0 below e0, 1 above e1, smooth between (either way round)."""
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def mix(a, b, t):
    """The colour t of the way from hex a to hex b, as hex."""
    ca, cb = (int(a[i:i + 2], 16) for i in (1, 3, 5)), (int(b[i:i + 2], 16) for i in (1, 3, 5))
    return '#' + ''.join(f'{round(x + (y - x) * t):02x}' for x, y in zip(ca, cb))


def dab(q, size, seed=0.0):
    """Soft noise in 0-1 over the surface, blotches about `size` across: for colour that settles unevenly."""
    return 0.5 + 0.5 * noise.noise(Vector((q.x / size + seed, q.y / size, q.z / size)))


def limb_at(limbs, q):
    """Which limb [(kind, joints)] a point of the crab belongs to and where along it: (kind, segment index k, u
    along the segment 0-1, its joints, how far across from its axis in its half widths)."""
    best = None
    for kind, js in limbs:
        for k in range(len(js) - 1):
            (a, ra), (b, rb) = js[k], js[k + 1]
            ab = b - a
            u = min(max((q - a).dot(ab) / max(ab.length_squared, 1e-12), 0.0), 1.0)
            d = (q - (a + ab * u)).length / (ra + (rb - ra) * u)
            if best is None or d < best[4]:
                best = (kind, k, u, js, d)
    return best


def crab_colour(limbs, shell_rim):
    """The crab's colour across its surface, as the art paints it, for Part.tint: blue-grey on top, warming to a
    tan rim along the edges of every segment (where the surface turns down) and round the joints; each leg's last
    segment going over to orange-brown, darker at the tip; the claws cream-tan underneath, their fingers orange-tan
    with dark tips; the shell's toothed rim tan. shell_rim = (its middle (x, y), the height of its rim, how far out
    it reaches)."""
    TAN, RIM, TIP, CREAM = '#d9a466', '#cf9a5e', '#8f4f24', '#e6c99a'
    def joints(kind, last):                     # the real joints: a leg's knee and the rest, the arm's elbow
        return range(2, last, 2) if kind == 'leg' else (1,) if kind == 'arm' else ()

    def field(q, n):
        side = 1.0 - abs(n.z)                      # 0 facing up, 1 at the edges
        if q.z > shell_rim[1] - 0.008 and (q.xy - shell_rim[0]).length < shell_rim[2]:   # the shell
            if n.z < -0.2:
                return None
            w = 0.7 * ramp(0.5, 0.88, side) * ramp(0.0045, 0.001, q.z - shell_rim[1]) * (0.7 + 0.3 * dab(q, 0.004))
            return (RIM, w) if w > 0.02 else None
        hit = limb_at(limbs, q)
        if hit is None:
            return None
        kind, k, u, js, d = hit
        last = len(js) - 1
        s = k + u                                  # along the limb, in segments
        w_rim = 0.85 * ramp(0.5, 0.9, side)
        w_joint = max((math.exp(-((s - j) / 0.28) ** 2) for j in joints(kind, last)), default=0.0) * 0.65
        col, w = TAN, max(w_rim, w_joint)
        if kind == 'leg' and s > last - 2:         # the dactyl: tan to orange-brown, dark at the tip
            t = ramp(last - 2, last, s)
            col, w = mix(TAN, TIP, t ** 1.5), max(w, 0.55 + 0.4 * t)
        elif kind == 'palm':
            under = ramp(0.1, -0.5, n.z)
            if under > w_rim:
                col, w = CREAM, max(w, 0.8 * under)
            if s > last - 2:                       # its fixed finger
                t = ramp(last - 2, last, s)
                col, w = mix(TAN, TIP, t ** 1.6), max(w, 0.5 + 0.45 * t)
        elif kind == 'finger':
            t = ramp(0.0, last, s)
            col, w = mix(TAN, TIP, t ** 1.8), 0.6 + 0.35 * t
        return (col, min(w, 0.95)) if w > 0.02 else None
    return field


def crab_limb(p, joints, mats, flat=0.75):
    """A crab's leg, arm or pincer finger for soft(): a tube through joints [(point, half width)] with square rings
    (flattened top to bottom to `flat` of their width) that round off into flat oval segments, closed at both ends;
    the band from joint k to k + 1 in mats[k]."""
    tmp = bmesh.new()
    rings, w_prev, n = [], None, len(joints)
    for i, (q, a) in enumerate(joints):
        t = (joints[min(i + 1, n - 1)][0] - joints[max(i - 1, 0)][0]).normalized()
        w = t.cross(Vector((0.0, 0.0, 1.0)))
        if w.length < 0.25:
            w = w_prev if w_prev is not None else Vector((1.0, 0.0, 0.0))
        w = w.normalized()
        b = w.cross(t).normalized()
        w_prev = w
        rings.append([tmp.verts.new(q + w * (a * sw) + b * (a * flat * sb))
                      for sw, sb in ((1, 1), (-1, 1), (-1, -1), (1, -1))])
    fm = []
    for k, (ra, rb) in enumerate(zip(rings, rings[1:])):
        for j in range(4):
            tmp.faces.new((ra[j], ra[(j + 1) % 4], rb[(j + 1) % 4], rb[j]))
            fm.append(mats[k])
    tmp.faces.new(list(reversed(rings[0])))
    fm.append(mats[0])
    tmp.faces.new(rings[-1])
    fm.append(mats[-1])
    piece_in_colours(p, tmp, fm)


def crab_joints(px_joints, fat=1.6):
    """[(px, py, z, half width px)] of the art -> [(point, half width)] for crab_limb(), the widths grown by `fat`
    against the shrinking of the subdivision."""
    return [(crab_at(px, py, z), fat * hw / CRAB_MAP[2]) for px, py, z, hw in px_joints]


# the legs as the art draws them, left side back to front, then the right: (px, py, z, half width px) at the base
# hidden under the shell, the middle of the merus, the knee, the middle of the propodus, the last joint, the dactyl and
# its tip (the far right leg shows its carpus too; the one hidden under the right claw is shorter)
CRAB_LEGS = [
    [(382, 462, 0.017, 17), (300, 392, 0.034, 26), (248, 345, 0.038, 14), (198, 368, 0.035, 23), (152, 400, 0.03, 12),
     (128, 442, 0.026, 14), (106, 486, 0.021, 3)],
    [(378, 518, 0.017, 17), (230, 490, 0.032, 28), (125, 495, 0.035, 15), (92, 565, 0.031, 26), (78, 636, 0.027, 12),
     (88, 695, 0.024, 17), (112, 755, 0.02, 3)],
    [(382, 584, 0.017, 17), (270, 565, 0.03, 27), (195, 560, 0.032, 14), (152, 610, 0.028, 25), (122, 664, 0.024, 12),
     (150, 730, 0.02, 17), (193, 800, 0.017, 3)],
    [(352, 615, 0.016, 17), (268, 650, 0.027, 26), (237, 718, 0.028, 13), (255, 775, 0.023, 24), (280, 830, 0.017, 10),
     (300, 853, 0.015, 10), (328, 878, 0.012, 3)],
    [(752, 388, 0.016, 17), (765, 262, 0.036, 25), (800, 205, 0.042, 14), (870, 225, 0.038, 24), (938, 252, 0.032, 13),
     (955, 282, 0.024, 9), (958, 305, 0.017, 3)],
    [(812, 402, 0.016, 17), (850, 320, 0.034, 27), (907, 292, 0.038, 14), (985, 318, 0.035, 28), (1050, 355, 0.03, 13),
     (1072, 374, 0.024, 8), (1082, 390, 0.018, 3)],
    [(868, 470, 0.017, 17), (945, 418, 0.03, 27), (1005, 388, 0.034, 14), (1055, 400, 0.033, 25), (1105, 412, 0.03, 12),
     (1150, 450, 0.028, 25), (1185, 500, 0.025, 11), (1186, 570, 0.022, 17), (1172, 645, 0.019, 3)],
    [(868, 530, 0.015, 16), (950, 525, 0.021, 22), (1010, 525, 0.023, 12), (1040, 585, 0.019, 18), (1050, 640, 0.013, 3)],
]


def crab_leg(p, px_joints, fat=2.45):
    """One walking leg for soft(), as the art draws it: a flat rounded paddle for each segment (the merus, the carpus
    and propodus, the dactyl), each from one joint to the next through the widest point of its middle, its ends a
    little past the joints, so that the segments overlap there in knuckles and each shows its own outline.
    Blue-grey; crab_colour paints the tan rims and knuckles and the orange-brown dactyl. Returns the leg's joints
    the whole way along, for crab_colour."""
    s = CRAB_MAP[2]
    for k in range(0, len(px_joints) - 2, 2):
        (a, wa), (m, wm), (b, wb) = ((crab_at(*q[:3]), q[3] / s) for q in px_joints[k:k + 3])
        tip = k + 2 == len(px_joints) - 1
        a = a - (m - a).normalized() * wa * 0.9
        if not tip:
            b = b + (b - m).normalized() * wb * 0.9
        crab_limb(p, [(a, wa * 2.1), (m, wm * fat), (b, wb * (1.2 if tip else 2.1))], ['CrabShell'] * 2,
                  flat=0.55 if tip else 0.42)
    return crab_joints(px_joints, 1.75)


def finger_teeth(p, line, other, widths, at=(0.28, 0.48, 0.68)):
    """Blunt cream teeth along the inner edge of a pincer's finger: line [points] from its base to its tip, the
    other finger's points (the teeth face it), and the finger's half widths along it in metres."""
    lengths = [0.0]
    for a, b in zip(line, line[1:]):
        lengths.append(lengths[-1] + (b - a).length)
    for t in at:
        d = t * lengths[-1]
        i = next(j for j in range(len(lengths) - 1) if lengths[j + 1] >= d)
        u = (d - lengths[i]) / max(lengths[i + 1] - lengths[i], 1e-9)
        q = line[i].lerp(line[i + 1], u)
        w = widths[i] + (widths[i + 1] - widths[i]) * u
        near = min(other, key=lambda o: (o - q).length)
        inward = near - q
        inward.z = 0.0
        if inward.length < 1e-6:
            continue
        inward.normalize()
        r = max(0.0022, 0.8 * w)
        p.blob(q + inward * (w * 1.05) + Vector((0.0, 0.0, w * 0.2)), r, 'CrabBelly', squash=(1.0, 1.0, 0.8),
               segs=(6, 3))


# the claws from the art, (px, py, z, half width px) along each: the arm from under the shell; the wrist (px, py, z),
# size, squash and yaw; the palm from the wrist out along its fixed finger to the tip; the movable finger
CRAB_CLAWS = [
    ([(585, 612, 0.017, 18), (525, 640, 0.019, 27), (468, 672, 0.021, 25)],
     ((405, 720, 0.024), 0.016, (1.0, 1.0, 0.7), 20),
     [(415, 795, 0.019, 72), (490, 802, 0.019, 115), (580, 806, 0.019, 115), (645, 820, 0.019, 92),
      (702, 864, 0.0135, 21), (750, 876, 0.012, 11), (783, 881, 0.0115, 3)],
     [(625, 745, 0.025, 25), (690, 748, 0.024, 23), (748, 774, 0.02, 17), (778, 815, 0.016, 11), (788, 862, 0.013, 3)]),
    ([(805, 578, 0.017, 18), (865, 572, 0.02, 27), (930, 540, 0.023, 28), (985, 515, 0.025, 26)],
     ((1040, 545, 0.026), 0.0165, (1.0, 1.1, 0.75), -20),
     [(1052, 608, 0.022, 60), (1022, 680, 0.02, 100), (990, 755, 0.019, 92), (955, 805, 0.016, 55),
      (905, 824, 0.0135, 20), (868, 842, 0.012, 11), (842, 858, 0.0115, 3)],
     [(915, 660, 0.024, 24), (878, 720, 0.022, 22), (846, 790, 0.018, 16), (825, 840, 0.014, 10), (818, 870, 0.0115, 3)]),
]


# the cream mouthparts under the front of the shell, between the claws: (px, py, z), size, squash, yaw
CRAB_FACE = [((672, 632, 0.019), 0.0065, (1.3, 0.75, 0.6), 22), ((712, 626, 0.0195), 0.007, (1.2, 0.8, 0.62), 22),
             ((752, 619, 0.02), 0.0068, (1.2, 0.8, 0.62), 22), ((790, 610, 0.02), 0.006, (1.2, 0.75, 0.6), 22)]


# the beady eyes, (px, py, z) and radius, set in the notches either side of the front of the shell
CRAB_EYES = [((590, 582, 0.036), 0.0031), ((820, 527, 0.036), 0.0030)]


def crab(col):
    """蟹: a blue-grey crab on a celadon plate, as the art lays it out: turned a little to its left, its rounded shell
    edged with blunt teeth along the front, two big claws held in front with open rounded pincers, four legs a side
    sprawled over the rim, and beady eyes. Every piece is placed from the art's pixels (crab_at) and rounded by
    subdivision; its colour is painted across it as the art has it (crab_colour): mottled blue-grey and olive,
    warming to tan along the edges of every segment and round the joints, orange-brown tips, cream-tan under the
    claws."""
    p = Part()
    inside = crab_plate(p, n=44)
    fl = CRAB_PLATE['floor']
    n0, f_shell = len(p.bm.verts), len(p.bm.faces)
    with p.soft():
        carapace(p, 0.03, 0.013, fl + 0.004, tooth=0.0085)
    with p.soft():
        limbs = [('leg', crab_leg(p, leg)) for leg in CRAB_LEGS]
    with p.soft():
        for arm, wrist, palm, finger in CRAB_CLAWS:
            js = crab_joints(arm)
            crab_limb(p, js, ['CrabShell'] * (len(arm) - 1), flat=0.8)
            limbs.append(('arm', js))
            c, r, sq, yaw = wrist
            p.blob(crab_at(*c), r, 'CrabShell', squash=sq, segs=(8, 4), rot=math.radians(yaw))
            limbs.append(('wrist', [(crab_at(*c), r * 1.2), (crab_at(*c) + Vector((0.0, 0.0, 0.001)), r * 1.2)]))
            js = crab_joints(palm, 1.35)
            crab_limb(p, js, ['CrabShell'] * (len(palm) - 1), flat=0.5)
            limbs.append(('palm', js))
            js = crab_joints(finger, 1.6)
            crab_limb(p, js, ['CrabShell'] * (len(finger) - 1), flat=0.75)
            limbs.append(('finger', js))
        for c, r, sq, yaw in CRAB_FACE:
            p.blob(crab_at(*c), r, 'CrabBelly', squash=sq, segs=(6, 4), rot=math.radians(yaw))
    for arm, wrist, palm, finger in CRAB_CLAWS:   # the pincers' teeth, facing each other
        fixed, moving = [crab_at(*q[:3]) for q in palm[4:]], [crab_at(*q[:3]) for q in finger]
        finger_teeth(p, fixed, moving, [q[3] / CRAB_MAP[2] for q in palm[4:]])
        finger_teeth(p, moving, fixed, [q[3] / CRAB_MAP[2] for q in finger])
    shell = [crab_at(px, py, 0.0).xy for px, py in CRAB_SHELL]
    middle = sum(shell, Vector((0.0, 0.0))) / len(shell)
    p.tint(f_shell, crab_colour(limbs, (middle, 0.03, max((q - middle).length for q in shell) * 1.04)))
    for c, r in CRAB_EYES:
        p.blob(crab_at(*c), r, 'FishEye', segs=(10, 6))
    crab_onto(p, n0, inside)
    return p.finish('SM_crab', col, sharp=None)


VIEW = Vector((0.0, -math.cos(ART_EL), math.sin(ART_EL)))   # from the food towards the art's camera


def refined(st, sub=2):
    """Stations [(x, top, bottom, half_width)] with `sub` steps between each pair along a Catmull-Rom curve, so that
    a cage made of them is smooth."""
    out = []
    for i in range(len(st) - 1):
        p0, p1, p2, p3 = st[max(i - 1, 0)], st[i], st[i + 1], st[min(i + 2, len(st) - 1)]
        for j in range(sub):
            u = j / sub
            out.append(tuple(0.5 * ((2 * b) + (-a + c) * u + (2 * a - 5 * b + 4 * c - d) * u * u
                                    + (-a + 3 * b - 3 * c + d) * u ** 3) for a, b, c, d in zip(p0, p1, p2, p3)))
    return out + [st[-1]]


def hull(p, st, mat, n=12):
    """A closed body along x as one cage: an elliptic ring of n through each station (x, top, bottom, half_width),
    the near side towards -y, the ends capped. Build it inside p.soft() for a smooth, rounded body."""
    tmp = bmesh.new()
    rings = [[tmp.verts.new((x, -hw * math.sin(2 * math.pi * k / n), (t + b) / 2 + (t - b) / 2 * math.cos(2 * math.pi * k / n)))
              for k in range(n)] for x, t, b, hw in st]
    for ra, rb in zip(rings, rings[1:]):
        for k in range(n):
            tmp.faces.new((ra[k], ra[(k + 1) % n], rb[(k + 1) % n], rb[k]))
    tmp.faces.new(list(reversed(rings[0])))
    tmp.faces.new(rings[-1])
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)


def slab(p, outline, mat, thick, M=Matrix()):
    """A flat piece as a cage: the outline [(x, z)] given `thick` across y, placed by M. Inside p.soft() it comes out
    a rounded lens with no sharp rim: fins, tails."""
    tmp = bmesh.new()
    a = [tmp.verts.new(M @ Vector((x, -thick / 2, z))) for x, z in outline]
    b = [tmp.verts.new(M @ Vector((x, thick / 2, z))) for x, z in outline]
    tmp.faces.new(a)
    tmp.faces.new(list(reversed(b)))
    for i in range(len(outline)):
        tmp.faces.new((a[i], a[(i + 1) % len(a)], b[(i + 1) % len(b)], b[i]))
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)


def shell(p, inner, outer, mat):
    """A cage between two matching outlines of points (a fin lying on a curved surface): its faces, its back and
    its rim. Inside p.soft() it rounds off."""
    tmp = bmesh.new()
    a = [tmp.verts.new(q) for q in inner]
    b = [tmp.verts.new(q) for q in outer]
    tmp.faces.new(a)
    tmp.faces.new(list(reversed(b)))
    for i in range(len(a)):
        tmp.faces.new((a[i], a[(i + 1) % len(a)], b[(i + 1) % len(b)], b[i]))
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)


def caster(p, f0, view):
    """Ray caster onto the faces added to p since it had f0 faces: cast(q) is the point of them that the camera
    looking along -view sees in front of q, and the surface normal there (None if it misses)."""
    from mathutils.bvhtree import BVHTree
    p.bm.faces.ensure_lookup_table()
    tmp = bmesh.new()
    vmap = {}
    for f in p.bm.faces[f0:]:
        vs = []
        for v in f.verts:
            if v not in vmap:
                vmap[v] = tmp.verts.new(v.co)
            vs.append(vmap[v])
        tmp.faces.new(vs)
    tmp.normal_update()
    tree = BVHTree.FromBMesh(tmp)
    tmp.free()

    def cast(q):
        hit, nrm, _, _ = tree.ray_cast(Vector(q) + view * 0.3, -view)
        if hit is not None and nrm.dot(view) < 0:
            nrm = -nrm
        return hit, nrm
    return cast


def interp(pts, x):
    """Linear interpolation in a list of (x, value) sorted by x, held level beyond its ends."""
    if x <= pts[0][0]:
        return pts[0][1]
    for (x0, v0), (x1, v1) in zip(pts, pts[1:]):
        if x <= x1:
            return v0 + (v1 - v0) * (x - x0) / (x1 - x0)
    return pts[-1][1]


def rest_on(p, n0, z, nb=None):
    """Slides what was added to p since it had n0 vertices along the art's line of sight, so that it looks the same
    from there, until its lowest point (of the first nb of those vertices) is at height z; returns the slide."""
    p.bm.verts.ensure_lookup_table()
    vs = p.bm.verts[n0:]
    low = min(v.co.z for v in (vs[:nb] if nb else vs))
    t = (z - low) / VIEW.z
    for v in vs:
        v.co += VIEW * t
    return Matrix.Translation(VIEW * t)


def lay_flat(pts, z):
    """Points slid along the art's line of sight to height z: what lies at z and looks the same from the art's view."""
    return [Vector(q) + VIEW * ((z - q[2]) / VIEW.z) for q in pts]


def side_point(q, view):
    """Where a point of a fish's surface (in the fish's own frame, mid-plane y = 0) shows on the mid-plane from the
    art's view (`view`, in the same frame): slid along the line of sight to y = 0, the far side mirrored first."""
    y = -abs(q.y)
    t = y / view.y
    return q.x - view.x * t, q.z - view.z * t


def poly_field(poly):
    """Signed distance to a polygon [(x, z)], positive inside: a field for paint() with smooth edges."""
    def field(x, z):
        d, inside = 1.0, False
        for (x0, z0), (x1, z1) in zip(poly, poly[1:] + poly[:1]):
            ex, ez = x1 - x0, z1 - z0
            t = min(1.0, max(0.0, ((x - x0) * ex + (z - z0) * ez) / (ex * ex + ez * ez)))
            d = min(d, math.hypot(x - x0 - t * ex, z - z0 - t * ez))
            if (z0 > z) != (z1 > z) and x < x0 + (z - z0) * ex / ez:
                inside = not inside
        return d if inside else -d
    return field


def flank_or_plate(p, cast, place, outline, mat, floor, thick=0.003, lift=0.0008, out=0.0):
    """A fin lying on the near flank where the art shows it over the body and flat on the plate where it reaches past
    the body: each outline point (x, z) of the fish's mid-plane is cast onto the body from the art's view and placed
    by `place` (the fish's final placement), or, missing the body, laid flat on the plate at `floor`. `out` lifts
    the outline's points off the flank more the further they are from the first one. Built as a rounded shell."""
    inner, outer = [], []
    R = place.to_3x3()
    x0 = outline[0][0]
    for x, z in outline:
        hit, nrm = cast((x, 0.0, z))
        if hit is not None:
            n = (R @ nrm).normalized()
            h = lift + out * abs(x - x0) / 0.04
            inner.append(place @ hit + n * h)
            outer.append(place @ hit + n * (h + thick))
        else:
            q = lay_flat([place @ Vector((x, 0.0, z))], floor + 0.0004)[0]
            inner.append(q)
            outer.append(q + Vector((0.0, 0.0, thick)))
    with p.soft():
        shell(p, inner, outer, mat)


def spots(p, cast, blots, mat, n=8, lift=0.0003, fade=None):
    """Round blotches [(x, z, r)] of a fish's mid-plane, as the art's view shows them, laid onto whatever `cast` hits
    (the body or its fins): each a flat fan whose rings are cast onto the surface from the art's view, so it follows
    the surface and shows round in the art's view, lobed a little so they look painted, not stamped. With `fade`
    (point -> the hex colour of the surface under it), each is painted soft as a watercolour blot: dark in the
    middle, fading at its rim into the colour round it (`mat` must be in VTINT); the bigger ones get a second ring,
    so that they stay dark a little way out before they fade."""
    for k, (x, z, r) in enumerate(blots):
        c, nc = cast((x, 0.0, z))
        if c is None:
            continue
        rings = []
        for f in ((0.55, 1.0) if fade and r >= 0.0042 else (1.0,)):
            ring = []
            for j in range(n):
                a = 2 * math.pi * j / n
                rr = f * r * (1 + 0.16 * math.sin(3 * a + k * 1.7))
                hit, nrm = cast((x + rr * math.cos(a), 0.0, z + rr * math.sin(a)))
                if hit is None or (hit - c).length > 2.5 * r:
                    break
                ring.append(hit + nrm * lift)
            rings.append(ring)
        if any(len(ring) < n for ring in rings):
            continue
        tmp = bmesh.new()
        cv = tmp.verts.new(c + nc * lift * 1.6)
        vs = [[tmp.verts.new(q) for q in ring] for ring in rings]
        for j in range(n):
            tmp.faces.new((cv, vs[0][j], vs[0][(j + 1) % n]))
            if len(vs) > 1:
                tmp.faces.new((vs[0][j], vs[1][j], vs[1][(j + 1) % n], vs[0][(j + 1) % n]))
        tmp.normal_update()
        if sum((f.normal.dot(nc) for f in tmp.faces)) < 0:
            bmesh.ops.reverse_faces(tmp, faces=tmp.faces[:])
        f0 = len(p.bm.faces)
        p._commit(tmp, mat)
        if fade:
            p.tint(f0, lambda q, nn, c=c, r=r: (fade(q), 0.9 * ramp(0.6, 1.0, (q - c).length / r)), mats=(mat,))


# the carp of 普通整鱼 in its own frame: x from the snout along the body, z towards the back, the near flank to -y
CARP_BODY = [(0.007, 0.0084, -0.0164, 0.0077), (0.016, 0.0141, -0.0215, 0.0101), (0.03, 0.0219, -0.0288, 0.014),
             (0.048, 0.0281, -0.0362, 0.0176), (0.07, 0.036, -0.0446, 0.0204), (0.095, 0.0416, -0.0488, 0.0214),
             (0.12, 0.0426, -0.051, 0.0211), (0.145, 0.0407, -0.0462, 0.0194), (0.17, 0.0354, -0.0451, 0.0166),
             (0.192, 0.0271, -0.045, 0.0133), (0.21, 0.0188, -0.0366, 0.0103), (0.225, 0.0148, -0.0272, 0.0079),
             (0.238, 0.0144, -0.0232, 0.0063), (0.25, 0.015, -0.021, 0.005)]


CARP_TAIL = [(0.226, 0.012), (0.2411, 0.0167), (0.2489, 0.0237), (0.2564, 0.0298), (0.2637, 0.0354), (0.2701, 0.0385),
             (0.2761, 0.0408), (0.2817, 0.0419), (0.287, 0.0422), (0.2915, 0.0414), (0.2938, 0.0377), (0.293, 0.0296),
             (0.2882, 0.021), (0.2828, 0.0135), (0.2793, 0.0073), (0.2828, 0.0009), (0.2858, -0.0051), (0.2882, -0.013),
             (0.2915, -0.0185), (0.2938, -0.0238), (0.2889, -0.0276), (0.2823, -0.0278), (0.2721, -0.0268),
             (0.2581, -0.0224), (0.2486, -0.0197), (0.2404, -0.0208), (0.226, -0.022)]


CARP_DORSAL = [(0.114, 0.037), (0.1187, 0.042), (0.1261, 0.0451), (0.1326, 0.0486), (0.1388, 0.0513), (0.1449, 0.0535),
               (0.1508, 0.0553), (0.1565, 0.0567), (0.1618, 0.0567), (0.1662, 0.0548), (0.1712, 0.0539), (0.1742, 0.048),
               (0.1779, 0.0437), (0.1809, 0.0378), (0.185, 0.0346), (0.1894, 0.0326), (0.194, 0.0309), (0.1984, 0.0287),
               (0.2034, 0.0279), (0.2083, 0.0271), (0.2124, 0.0239), (0.2161, 0.0199), (0.2192, 0.0164), (0.218, 0.011),
               (0.17, 0.028), (0.12, 0.034)]


def platter(p, A, q, h, yaw=0.0, at=(0.0, 0.0), foot=0.56, n=48, floor=0.01, floor_r=0.7, lip=0.004, bulge=0.6,
            deform=None):
    """An oval 青瓷 plate like dish() (rounded foot ring, bulging outer wall, rolled lip, curved inside down to a flat
    floor), its rim A across along its long axis and q·A along the short one, the long axis turned `yaw` from +x
    towards +y, centred at `at`; `deform` (lobed()) scallops its rim. Returns inside(x, y): the height of the plate's
    inner surface (floor, wall or rim) under a point, for lying food on it (ignoring the scallops)."""
    r, sx = q * A, 1.0 / q
    rf = foot * r
    prof = [(0.0, 0.0015), (rf - 0.003, 0.0015), (rf, 0.0), (rf + 0.003, 0.002)]
    outer = [(rf + 0.003, 0.002)]
    for i in range(1, 6):   # the outer wall: low near the foot, turning up to the rim
        t = i / 6
        outer.append((rf + 0.003 + (r - lip - rf - 0.003) * (1 - (1 - t) ** (1 + bulge)),
                      0.002 + (h - lip - 0.002) * t ** (1 + bulge)))
    prof += outer[1:]
    for k in range(5):   # the rolled lip, from the outside over the top to the inside
        a = -0.4 * math.pi + k * 1.3 * math.pi / 4
        prof.append((r - lip + lip * math.cos(a), h - lip + lip * math.sin(a)))

    def z_out(x):   # the outer wall's height at radius x
        for (x0, z0), (x1, z1) in zip(outer, outer[1:]):
            if x0 <= x <= x1:
                return z0 + (z1 - z0) * (x - x0) / (x1 - x0)
        return 0.0 if x < outer[0][0] else h
    x0, z0, x1 = prof[-1][0], prof[-1][1], floor_r * r
    inner = [(x0, z0)]
    for i in range(1, 5):   # the inside: steep under the lip, levelling out into the floor
        t = i / 5
        x = x0 + (x1 - x0) * t
        inner.append((x, max(floor + (z0 - floor) * (1 - t) ** 2, z_out(x) + 0.004)))
    prof += inner[1:] + [(x1, floor), (x1 * 0.5, floor), (0.0, floor)]
    R = Matrix.Translation((*at, 0.0)) @ Matrix.Rotation(yaw, 4, 'Z')
    p.lathe(prof, 'Celadon', n=n, close_ends=False, M=R @ Matrix.Diagonal((sx, 1.0, 1.0, 1.0)), deform=deform)
    inner = list(reversed(inner)) + [(x1, floor)]
    inner.sort()
    Rinv = R.inverted()

    def inside(x, y):
        v = Rinv @ Vector((x, y, 0.0))
        rho = math.hypot(v.x / sx, v.y)
        if rho <= x1:
            return floor
        for (ra, za), (rb, zb) in zip(inner, inner[1:]):
            if ra <= rho <= rb:
                return za + (zb - za) * (rho - ra) / (rb - ra)
        return h
    return inside


def onto_platter(p, n0, inside, clear=0.0):
    """Keeps what was added to p since it had n0 vertices above the inside of the plate: a vertex below it (where
    food reaches past the floor onto the wall) is lifted onto it."""
    p.bm.verts.ensure_lookup_table()
    for v in p.bm.verts[n0:]:
        v.co.z = max(v.co.z, inside(v.co.x, v.co.y) + clear)


# the mandarin fish of 鳜鱼 in its own frame: x from the mouth along the body, z towards the back, the near flank to -y
GUIYU_BODY = [(0.0, 0.0105, -0.0175, 0.0085), (0.008, 0.0135, -0.0242, 0.0122), (0.022, 0.0177, -0.0312, 0.0161),
              (0.04, 0.0245, -0.0373, 0.021), (0.064, 0.0372, -0.0445, 0.024), (0.09, 0.047, -0.05, 0.0253),
              (0.118, 0.0503, -0.0519, 0.025), (0.145, 0.048, -0.049, 0.0225), (0.17, 0.0405, -0.0425, 0.0187),
              (0.192, 0.0298, -0.0366, 0.0146), (0.21, 0.0198, -0.0284, 0.011), (0.224, 0.0184, -0.019, 0.0083),
              (0.234, 0.0195, -0.0136, 0.0067)]


GUIYU_TAIL = [(0.214, 0.012), (0.2222, 0.0182), (0.2308, 0.0279), (0.2399, 0.0369), (0.2487, 0.0433), (0.2572, 0.0472),
              (0.2636, 0.0482), (0.2698, 0.0443), (0.2756, 0.0389), (0.279, 0.0303), (0.2823, 0.0205), (0.284, 0.0113),
              (0.2839, 0.0006), (0.2811, -0.0071), (0.2752, -0.0113), (0.2667, -0.0135), (0.2525, -0.0143),
              (0.2405, -0.0139), (0.2331, -0.0135), (0.214, -0.012)]


GUIYU_SPINY = [(0.079, 0.040), (0.0812, 0.0452), (0.0928, 0.0652), (0.0945, 0.0657), (0.0962, 0.0575), (0.1098, 0.0753),
               (0.1118, 0.0758), (0.1136, 0.0668), (0.1258, 0.0785), (0.1279, 0.0788), (0.1287, 0.0690), (0.1398, 0.0784),
               (0.1418, 0.0784), (0.1421, 0.0660), (0.1540, 0.0728), (0.1559, 0.0726), (0.1561, 0.0614), (0.1652, 0.0618),
               (0.1668, 0.0614), (0.1676, 0.0523), (0.1720, 0.0563), (0.1735, 0.0560), (0.1761, 0.0466), (0.1822, 0.0494),
               (0.1838, 0.0488), (0.1800, 0.0345), (0.16, 0.040), (0.12, 0.046)]


GUIYU_SOFT = [(0.1765, 0.034), (0.1772, 0.0365), (0.1948, 0.0432), (0.2045, 0.0425), (0.2115, 0.0345), (0.2133, 0.0274),
              (0.211, 0.0186), (0.206, 0.016), (0.19, 0.024)]


MANDARIN_SPOTS = [(0.0298, 0.0126, 0.0062), (0.0535, 0.0191, 0.0038), (0.0550, 0.0262, 0.0040),
                  (0.0658, 0.0281, 0.0045), (0.0673, 0.0073, 0.0043), (0.0685, 0.0132, 0.0041),
                  (0.0703, 0.0343, 0.0031), (0.0774, 0.0305, 0.0039), (0.0787, 0.0232, 0.0030),
                  (0.0824, 0.0358, 0.0037), (0.0840, 0.0121, 0.0059), (0.0878, 0.0223, 0.0029),
                  (0.0894, 0.0357, 0.0040), (0.0907, 0.0468, 0.0031), (0.0918, -0.0006, 0.0034),
                  (0.0946, 0.0124, 0.0047), (0.0980, 0.0384, 0.0041), (0.0985, 0.0492, 0.0036),
                  (0.0986, 0.0056, 0.0032), (0.1037, 0.0395, 0.0034), (0.1043, 0.0104, 0.0041),
                  (0.1067, 0.0569, 0.0031), (0.1074, 0.0457, 0.0029), (0.1111, 0.0185, 0.0031),
                  (0.1124, 0.0506, 0.0026), (0.1163, -0.0462, 0.0054), (0.1169, 0.0589, 0.0043),
                  (0.1199, 0.0463, 0.0025), (0.1203, 0.0381, 0.0051), (0.1219, 0.0229, 0.0032),
                  (0.1227, 0.0142, 0.0037), (0.1245, 0.0509, 0.0030), (0.1270, 0.0362, 0.0034),
                  (0.1299, 0.0283, 0.0061), (0.1325, 0.0469, 0.0044), (0.1331, 0.0579, 0.0049),
                  (0.1385, 0.0085, 0.0032), (0.1385, 0.0175, 0.0037), (0.1386, 0.0345, 0.0026),
                  (0.1420, 0.0212, 0.0034), (0.1426, 0.0449, 0.0043), (0.1444, 0.0258, 0.0037),
                  (0.1477, 0.0549, 0.0053), (0.1480, 0.0472, 0.0030), (0.1500, 0.0353, 0.0040),
                  (0.1515, 0.0405, 0.0025), (0.1548, 0.0381, 0.0029), (0.1581, 0.0483, 0.0045),
                  (0.1582, 0.0109, 0.0061), (0.1607, 0.0347, 0.0030), (0.1653, 0.0319, 0.0039),
                  (0.1655, 0.0379, 0.0032), (0.1658, 0.0208, 0.0060), (0.1673, 0.0106, 0.0034),
                  (0.1715, 0.0084, 0.0026), (0.1719, -0.0044, 0.0033), (0.1753, -0.0007, 0.0037),
                  (0.1758, 0.0343, 0.0026), (0.1778, 0.0161, 0.0026), (0.1811, 0.0223, 0.0029),
                  (0.1817, 0.0292, 0.0033), (0.1846, 0.0120, 0.0033), (0.1864, 0.0070, 0.0034),
                  (0.1869, 0.0256, 0.0041), (0.1907, 0.0327, 0.0025), (0.1928, -0.0366, 0.0033),
                  (0.1940, 0.0033, 0.0051), (0.1976, 0.0228, 0.0025), (0.1992, 0.0176, 0.0029),
                  (0.1993, -0.0310, 0.0046), (0.1999, 0.0096, 0.0061), (0.2005, 0.0308, 0.0032),
                  (0.2042, -0.0044, 0.0038), (0.2044, 0.0279, 0.0025), (0.2108, -0.0211, 0.0051),
                  (0.2133, 0.0074, 0.0034), (0.2210, 0.0125, 0.0060), (0.2235, 0.0030, 0.0048),
                  (0.2350, 0.0204, 0.0028), (0.2381, 0.0148, 0.0037), (0.2398, 0.0071, 0.0061),
                  (0.2423, -0.0006, 0.0041), (0.2429, -0.0071, 0.0032), (0.2458, 0.0316, 0.0044),
                  (0.2526, 0.0273, 0.0037), (0.2543, -0.0075, 0.0031), (0.2548, 0.0206, 0.0053),
                  (0.2552, 0.0079, 0.0036), (0.2559, -0.0021, 0.0036), (0.2560, 0.0144, 0.0044),
                  (0.2589, 0.0036, 0.0051), (0.2602, 0.0377, 0.0026), (0.2673, 0.0291, 0.0028),
                  (0.2681, -0.0079, 0.0029), (0.2712, -0.0029, 0.0038), (0.2713, 0.0185, 0.0041)]


def guiyu(p, M, floor=0.013):
    """The mandarin fish of 鳜鱼, smooth and rounded, built in its own frame (mouth at the origin, x along the body, z
    to its back, the near flank to -y) and placed by M, then slid along the art's line of sight to lie on the plate at
    `floor`: an olive back over a cream belly, dark blotches over body, fins and tail, the gaping pink mouth between a
    pale upper lip and a jutting lower jaw, a big eye, the gill cover's edge, a spiny dorsal fin with rounded spines,
    a rounded soft dorsal, tail and pectoral fin, and pelvic and anal fins reaching down onto the plate."""
    n0, f0 = len(p.bm.verts), len(p.bm.faces)
    view = M.to_3x3().inverted() @ VIEW   # the line of sight in the fish's frame
    with p.soft():
        hull(p, refined(GUIYU_BODY), 'GuiyuSkin', n=12)
    tops = [(x, t) for x, t, b, w in GUIYU_BODY]
    bots = [(x, b) for x, t, b, w in GUIYU_BODY]
    skin = guiyu_colour(tops, bots)
    nb = len(p.bm.verts) - n0
    cast = caster(p, f0, view)
    with p.soft():
        slab(p, GUIYU_TAIL, 'MandarinFin', 0.0045)
        slab(p, GUIYU_SPINY, 'MandarinFin', 0.0032)
        slab(p, GUIYU_SOFT, 'MandarinFin', 0.0035)
        inner, outer = [], []   # the pectoral fin, a fan standing off the flank towards its rounded edge
        for (x, z) in ((0.1004, -0.0105), (0.113, -0.0062), (0.1284, -0.0046), (0.14, -0.0066), (0.1442, -0.0104),
                       (0.1453, -0.0169), (0.1417, -0.0255), (0.1354, -0.0358), (0.1257, -0.0377), (0.1085, -0.0334),
                       (0.1019, -0.0279)):
            hit, nrm = cast((x, 0.0, z))
            lift = 0.0008 + 0.006 * max(0.0, (x - 0.103) / 0.042) ** 1.3
            inner.append(hit + nrm * lift)
            outer.append(hit + nrm * (lift + 0.0035))
        shell(p, inner, outer, 'MandarinFin')
    def under(q):   # the colour of the skin under a spot's rim, or of the fin it lies on
        x, z = side_point(q, view)
        hit, _ = cast((x, 0.0, z))
        if hit is None or (hit - q).length > 0.0008:
            return PALETTE['MandarinFin'][0]
        got = skin(q, None)
        return mix(PALETTE['GuiyuSkin'][0], *got) if got else PALETTE['GuiyuSkin'][0]
    spots(p, caster(p, f0, view), MANDARIN_SPOTS, 'MandarinSpot', fade=under)
    mouth = poly_field([(-0.004, 0.004), (0.0053, 0.0063), (0.0111, 0.0092), (0.0227, 0.0061), (0.0325, -0.0004),
                        (0.0384, -0.0081), (0.0399, -0.0142), (0.0318, -0.0123), (0.02, -0.0105), (0.0081, -0.0095),
                        (-0.004, -0.009)])
    paint(p, f0, 'FishGill', lambda q: mouth(*side_point(q, view)))   # the gaping mouth
    with p.soft():
        for pts, r in ((((0.0425, -0.0095), (0.036, 0.0035), (0.0225, 0.0094), (0.0045, 0.0094)), 0.0036),
                       (((0.0412, -0.0118), (0.0281, -0.0134), (0.0079, -0.0124), (-0.0012, -0.0128)), 0.0048)):
            # the pale upper lip and the jutting lower jaw, round the front of the mouth
            near = []
            for x, z in pts:
                hit, nrm = cast((x, 0.0, z))
                near.append(hit + nrm * r * 0.25 if hit is not None else Vector((x, -0.004, z)))
            front = Vector((pts[-1][0] - r * 0.4, 0.0, pts[-1][1]))
            p.tube(near + [front] + [Vector((q.x, -q.y, q.z)) for q in reversed(near)], r, 'GuiyuSkin', sides=4)
        gill = []   # the gill cover's rounded edge, a rounded spine at its top
        for (x, z) in ((0.0922, 0.0203), (0.0976, 0.0206), (0.104, 0.0121), (0.1015, 0.0055), (0.0969, -0.0023),
                       (0.09, -0.0095), (0.0832, -0.0144), (0.0755, -0.0175), (0.0668, -0.0187)):
            hit, nrm = cast((x, 0.0, z))
            gill.append(hit + nrm * 0.0006)
        p.tube(gill, 0.0017, 'MandarinSpot', sides=4)
    hit, nrm = cast((0.0413, 0.0, 0.0133))
    fish_eye(p, hit, nrm, 0.0076, pupil=0.52)
    hit, nrm = cast((0.0269, 0.0, 0.0136))
    p.blob(hit, 0.0016, 'FishEye', segs=(6, 4))   # nostril
    p.tint(f0, skin, mats=('GuiyuSkin',))
    moved(p, n0, M)
    T = rest_on(p, n0, floor + 0.0003, nb=nb)
    place = T @ M
    flank_or_plate(p, cast, place, [(0.0951, -0.0503), (0.1016, -0.0362), (0.1232, -0.0385), (0.1424, -0.0419),
                                    (0.1505, -0.0455), (0.1466, -0.0492), (0.15, -0.0556), (0.1443, -0.0616),
                                    (0.1307, -0.0618), (0.1095, -0.0577)], 'MandarinFin', floor, out=0.002)   # pelvic
    flank_or_plate(p, cast, place, [(0.1799, -0.0404), (0.1804, -0.0389), (0.1911, -0.0381), (0.2031, -0.0163),
                                    (0.2147, -0.0127), (0.2262, -0.0131), (0.2345, -0.0193), (0.2362, -0.0288),
                                    (0.2318, -0.0353), (0.2197, -0.0378), (0.2088, -0.0382), (0.1908, -0.041)],
                   'MandarinFin', floor, out=0.002)   # anal


# the big fish head of 大鱼头 in its own frame: x from the mouth back to the cut, z to the crown, the near side to -y
YUTOU_HEAD = [(-0.005, 0.0188, -0.0155, 0.0128), (0.004, 0.0253, -0.0283, 0.02), (0.015, 0.0306, -0.0404, 0.027),
              (0.03, 0.0395, -0.0489, 0.034), (0.05, 0.0472, -0.0572, 0.04), (0.07, 0.0533, -0.066, 0.044),
              (0.09, 0.0577, -0.0675, 0.046), (0.11, 0.0609, -0.0647, 0.047), (0.13, 0.0603, -0.0586, 0.046),
              (0.148, 0.0554, -0.0509, 0.0433), (0.163, 0.0512, -0.0415, 0.0395), (0.174, 0.0408, -0.0293, 0.0348),
              (0.181, 0.0237, -0.0251, 0.0305)]


def yutou(p, M, floor=0.012):
    """The big fish head of 大鱼头, smooth and rounded, built in its own frame (mouth at the origin, x back to the cut,
    z to the crown, the near side to -y) and placed by M, then slid along the art's line of sight to rest on the plate
    at `floor`: dark grey crown over a pale cheek and throat, the gaping mouth between pale rolled lips, a big round
    eye, the gill cover's rounded edges over the red gills, the pink cut face at the back and a stub of dark fin."""
    n0, f0 = len(p.bm.verts), len(p.bm.faces)
    view = M.to_3x3().inverted() @ VIEW   # the line of sight in the head's frame
    with p.soft():
        hull(p, refined(YUTOU_HEAD), 'FishBelly', n=14)
    for mat, poly in (('GillRed', [(0.1354, 0.0298), (0.1353, 0.0225), (0.1313, 0.0082), (0.1186, 0.0047),
                                   (0.1061, -0.0183), (0.1043, -0.0277), (0.0968, -0.0382), (0.0863, -0.0411),
                                   (0.0927, -0.0418), (0.1111, -0.0387), (0.1339, -0.0294), (0.1433, -0.0203),
                                   (0.1479, -0.0078), (0.1481, 0.0114), (0.1446, 0.0191)]),
                      ('FishGill', [(0.1527, 0.0522), (0.1662, 0.0489), (0.1766, 0.0389), (0.1827, 0.0225),
                                    (0.19, 0.005), (0.19, -0.0113), (0.1866, -0.0207), (0.1797, -0.0127),
                                    (0.1711, 0.0003), (0.1631, 0.0156), (0.156, 0.0314), (0.1518, 0.0439)]),   # cut face
                      ('MouthPink', [(-0.008, 0.0092), (0.0059, 0.0042), (0.0176, -0.0015), (0.0285, -0.0078),
                                     (0.0349, -0.013), (0.0284, -0.0119), (0.0203, -0.0085), (0.0125, -0.0031),
                                     (0.0057, -0.0018), (0.0006, -0.004), (-0.008, -0.0077)])):
        field = poly_field(poly)
        paint(p, f0, mat, lambda q, field=field: field(*side_point(q, view)))
    nb = len(p.bm.verts) - n0
    cast = caster(p, f0, view)
    with p.soft():
        for pts, r in ((((0.0393, -0.0117), (0.0317, -0.0051), (0.0225, 0.0046), (0.0136, 0.0135), (0.0064, 0.0203),
                         (-0.0005, 0.0203)), 0.0038),
                       (((0.0372, -0.0144), (0.0284, -0.0119), (0.0203, -0.0085), (0.0125, -0.0049), (0.0056, -0.0024),
                         (-0.0004, -0.0046)), 0.005)):   # the pale lips rolled round the gaping mouth
            near = []
            for x, z in pts:
                hit, nrm = cast((x, 0.0, z))
                if hit is not None:
                    near.append(hit + nrm * r * 0.3)
            front = Vector((pts[-1][0] - r * 1.2, 0.0, pts[-1][1] - (0.006 if r < 0.004 else 0.005)))
            p.tube(near + [front] + [Vector((q.x, -q.y, q.z)) for q in reversed(near)], r, 'FishBelly', sides=4)
        for pts in (((0.1214, 0.0398), (0.1318, 0.0317), (0.1402, 0.0206), (0.1444, 0.0052), (0.1432, -0.0102),
                     (0.1379, -0.0201)),
                    ((0.1353, 0.0218), (0.1291, 0.0101), (0.1178, 0.0023), (0.1072, -0.0174), (0.1035, -0.0284),
                     (0.0938, -0.0391))):   # the gill cover's rounded edges
            edge = []
            for x, z in pts:
                hit, nrm = cast((x, 0.0, z))
                if hit is not None:
                    edge.append(hit + nrm * 0.0008)
            p.tube(edge, 0.0021, 'FishBelly', sides=4)
        slab(p, [(0.1217, 0.0587), (0.1321, 0.0613), (0.1445, 0.067), (0.1399, 0.0595), (0.1527, 0.0625),
                 (0.1476, 0.0551), (0.1612, 0.0575), (0.1545, 0.0507), (0.1471, 0.0481), (0.134, 0.0507)],
             'FishCrown', 0.004)   # a stub of dark fin
    hit, nrm = cast((0.0574, 0.0, 0.0127))
    fish_eye(p, hit, nrm, 0.0122, pupil=0.56)
    hit, nrm = cast((0.0303, 0.0, 0.0165))
    p.blob(hit, 0.0022, 'FishEye', segs=(6, 4))   # nostril
    p.tint(f0, yutou_colour(view))
    moved(p, n0, M)
    rest_on(p, n0, floor + 0.0003, nb=nb)


# the dark grey crown of the big fish head, in its side view (x back from the mouth, z up)
YUTOU_CROWN = [(-0.0092, 0.0166), (0.1462, 0.0674), (0.1707, 0.0159), (0.1785, -0.0193), (0.1702, -0.0308),
               (0.1586, -0.0205), (0.1498, 0.0043), (0.1378, 0.0243), (0.1263, 0.0257), (0.1117, 0.0097),
               (0.0902, 0.0027), (0.0689, -0.0012), (0.0541, -0.0025), (0.039, 0.0), (0.0264, 0.0087),
               (0.0117, 0.0184), (0.0039, 0.0229)]


def yutou_colour(view):
    """The big fish head's colour across its pale skin, as 大鱼头.png paints it, for Part.tint: the crown grey,
    dappled darker, fading through a ragged edge into the silvery cheek; a dark ring round the eye; the lips and
    throat warm pink-cream."""
    crown = poly_field(YUTOU_CROWN)
    GREY, DARK, SOCKET, PEACH = '#565c65', '#3a3f46', '#4a4e55', '#f0c3ae'

    def field(q, n):
        x, z = side_point(q, view)
        edge = crown(x, z) + 0.006 * (dab(q, 0.006) - 0.5)   # the crown's edge, ragged
        w = 0.95 * ramp(-0.008, 0.004, edge)
        col = mix(GREY, DARK, ramp(0.45, 0.75, dab(q, 0.005, 3.0)))   # dappled darker, like scales
        e = math.hypot(x - 0.0574, z - 0.0127)
        socket = 0.85 * ramp(0.0225, 0.0138, e)
        if socket > w:
            col, w = SOCKET, socket
        warm = max(0.4 * ramp(-0.032, -0.05, z) * ramp(0.12, 0.08, x), 0.5 * ramp(0.035, 0.015, x))
        if warm > w:
            col, w = PEACH, warm
        return (col, w) if w > 0.02 else None
    return field


ITEMS = [('pork', pork),
         ('chicken', chicken),
         ('duck', duck),
         ('kidney', kidney),
         ('wing', wing),
         ('tofu', tofu),
         ('skin', skin),
         ('fish', fish),
         ('mandarin_fish', mandarin_fish),
         ('fish_head', fish_head),
         ('crab', crab)]
