"""Shared parts for the 汴河两岸 level white models: build_level1.py (初始 · 1 桌) and build_shop.py (the shop as it
grows, 一级 to 五级).

Every prop is one object whose pivot sits at the middle of its footprint on the floor, made of boxes, lathed parts and
blobs merged into one mesh, with its hard edges rounded (圆角, see Prop). The building parts (timber-framed walls,
railings, steps, lanterns, door curtains) and the furniture (方桌, 方凳) follow the level art's part sheets (墙壁, 桌子,
板凳…). Usage, in Blender:

    import level_kit as K
    K.begin('SM_Level1', 'level1')          # an empty scene, the level's root and collection
    p = K.Prop('D_Floor', 'Hall', (x, y, K.F)); p.bx(...); p.finish()
    K.table('Hall', 'D_Table_1', x, y).finish()
    K.marker('Spot_Queue_1', (x, y, 0.05), 'Hall')
    K.finish_level(out_dir, closeups=[('closeup_hall.png', 'D_Table_1')])

F is the height of the floor the props stand on (the top of the stone plinth); set_floor() changes it for what is
built next (an upper floor), since walls, railings, tables and stools stand on F and boxes standing on F leave their
unseen bottoms open.
"""
import json
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

CLAY = (0.8, 0.8, 0.8)
F = 0.45     # floor height (top of the stone plinth)
H = 2.0      # wall height above the floor; the walls are cut low like the art
NAME, TAG = 'SM_Level', 'level'
scene = COL = ROOT = None
GROUPS = {}
PARTS = []
MATS = {}
MARKERS = []


def log(msg):
    print(f'[{TAG}] {msg}', flush=True)


# ---------------------------------------------------------------- palette (toon lit / shade, sRGB)
# Picked from the level art; Unity builds its toon materials from palette.json.

PALETTE = {
    'Timber':    ('#c0823f', '#8d5a2b'),  # posts, beams, railings
    'Wood':      ('#dba35c', '#b27a3b'),  # furniture
    'WoodFloor': ('#d9a05e', '#b67d42'),
    'Plaster':   ('#f4e2ae', '#dcc38d'),
    'Paper':     ('#fff4d6', '#f0dcae'),  # window paper, lantern shades
    'Stone':     ('#ece0c9', '#cdbd9f'),  # plinth, steps
    'Tile':      ('#c8c3b2', '#a9a391'),  # kitchen floor
    'Brick':     ('#bdb5a6', '#968e80'),  # stove, chimney
    'Cloth':     ('#5d88b6', '#416992'),  # blue door curtains
    'Cushion':   ('#bccca2', '#96a87d'),
    'Leaf':      ('#8fae5e', '#63813d'),  # kept for the plants to come
    'Flower':    ('#f2d262', '#d2ab41'),
    'Veg':       ('#a8c95f', '#7d9d3f'),
    'Chili':     ('#d9573b', '#a8392a'),
    'Ceramic':   ('#e6ebec', '#bcc6cb'),
    'Glaze':     ('#6f8497', '#50647a'),  # blue-grey flower pots
    'Iron':      ('#55504b', '#35312e'),
    'Water':     ('#8cc2d8', '#6399b4'),
    'Fire':      ('#ffb347', '#ff8a2a'),
    'Straw':     ('#dcc07a', '#b89a55'),  # baskets, sieve
}
PALETTE_EMISSIVE = {'Fire': 1.0, 'Paper': 0.25}


# ---------------------------------------------------------------- scene

def begin(name, tag, seed=7):
    """A fresh empty scene holding the level `name` (its root empty and collection); random seeded."""
    global NAME, TAG, scene, COL, ROOT, F
    NAME, TAG, F = name, tag, 0.45
    random.seed(seed)
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0
    scene = bpy.context.scene
    COL = bpy.data.collections.new(NAME)
    scene.collection.children.link(COL)
    ROOT = bpy.data.objects.new(NAME, None)
    ROOT.empty_display_type = 'PLAIN_AXES'
    COL.objects.link(ROOT)
    GROUPS.clear()
    PARTS.clear()
    MATS.clear()
    MARKERS.clear()


def set_floor(f):
    """The floor height what is built next stands on (an upper floor's boards)."""
    global F
    F = f


def marker(name, loc, grp):
    """An empty the game keys on (Spot_Queue_n: where waiting guests stand), exported with the level."""
    m = bpy.data.objects.new(name, None)
    m.empty_display_size = 0.2
    m.location = loc
    COL.objects.link(m)
    m.parent = group(grp)
    MARKERS.append(m)
    return m


def material(name):
    if name not in MATS:
        mat = bpy.data.materials.new('M_' + name)
        mat.diffuse_color = (*CLAY, 1.0)
        MATS[name] = mat
    return MATS[name]


def group(name):
    if name not in GROUPS:
        ob = bpy.data.objects.new(name, None)
        ob.empty_display_size = 0.3
        COL.objects.link(ob)
        ob.parent = ROOT
        GROUPS[name] = ob
    return GROUPS[name]


def rrect_ring(hx, hy, r, z, nc=3):
    """Rounded rectangle at height z, counter-clockwise seen from above (from build_wenli_gongdeng)."""
    r = max(1e-4, min(r, hx - 1e-4, hy - 1e-4))
    centers = [(hx - r, hy - r), (r - hx, hy - r), (r - hx, r - hy), (hx - r, r - hy)]
    pts = []
    for i, (cx, cy) in enumerate(centers):
        for k in range(nc + 1):
            a = math.radians(90 * i + 90 * k / nc)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
    return pts


class Prop:
    """One game object: boxes, lathed parts and blobs merged into a single mesh.

    Rounding (圆角) is modelled into each part as it is added, sized to the part like the 500-face
    lantern: radius ≈ 16% of the part's thinnest side (capped by `rmax`), two segments on chunky parts
    and a single chamfer on thin ones, which Weighted Normals shade as a rounded edge. Faces that can
    never be seen (the bottoms of anything standing on the floor) are left out.
    `off` shifts everything the prop adds, so a group of props can be moved as one.
    """

    def __init__(self, name, grp, pivot, rmax=0.03, off=(0, 0), turn=0.0):
        self.name, self.grp, self.rmax, self.turn = name, grp, rmax, turn
        self.off = Matrix.Translation((off[0], off[1], 0))
        self.pivot = Vector(pivot) + Vector((off[0], off[1], 0))
        self.bm = bmesh.new()
        self.mats = []

    def _mi(self, mat):
        if mat not in self.mats:
            self.mats.append(mat)
        return self.mats.index(mat)

    def _commit(self, tmp, mat, edges=(), r=0.0, seg=1):
        if edges and r > 1e-4:
            bmesh.ops.bevel(tmp, geom=list(edges), offset=r, offset_type='OFFSET', segments=seg, profile=0.5,
                            affect='EDGES', clamp_overlap=True)
        mi = self._mi(mat)
        vmap = {v: self.bm.verts.new(v.co) for v in tmp.verts}
        for f in tmp.faces:
            nf = self.bm.faces.new([vmap[v] for v in f.verts])
            nf.material_index = mi
        tmp.free()

    def rounding(self, dims, r=None):
        r = min(self.rmax, 0.16 * min(dims)) if r is None else r
        return r, (2 if r >= 0.018 else 1)   # two segments only where the round is big enough to read

    def box(self, c, s, mat, open_bottom=None, rot=0.0, M=None, r=None, top_only=False):
        """Axis-aligned box centred at c with size s, optionally turned `rot` degrees about Z.

        open_bottom defaults to True when the box stands on the floor (z ≈ F). Parts on the ground (z = 0)
        keep their bottom: the inverted-hull outline draws the lower silhouette from it.
        top_only rounds just the top edges (floor tiles and planks)."""
        if open_bottom is None:
            z0 = c[2] - s[2] / 2
            open_bottom = abs(z0 - F) < 0.045
        hx, hy, hz = s[0] / 2, s[1] / 2, s[2] / 2
        T = self.off @ (M or Matrix()) @ Matrix.Translation(Vector(c)) @ Matrix.Rotation(math.radians(rot), 4, 'Z')
        tmp = bmesh.new()
        v = [tmp.verts.new(T @ Vector((sx * hx, sy * hy, sz * hz))) for sz in (-1, 1) for sy in (-1, 1) for sx in (-1, 1)]
        faces = [(4, 5, 7, 6), (0, 1, 5, 4), (1, 3, 7, 5), (3, 2, 6, 7), (2, 0, 4, 6)]
        if not open_bottom:
            faces.append((0, 2, 3, 1))
        top_face = tmp.faces.new([v[i] for i in faces[0]])
        for f in faces[1:]:
            tmp.faces.new([v[i] for i in f])
        top = set(top_face.edges)
        edges = [e for e in tmp.edges if len(e.link_faces) == 2 and (not top_only or e in top)]
        rr, seg = self.rounding(s, r)
        self._commit(tmp, mat, edges, rr, 1 if top_only else seg)

    def bx(self, x0, x1, y0, y1, z0, z1, mat, **kw):
        """Box from its extents."""
        self.box(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2), (x1 - x0, y1 - y0, z1 - z0), mat, **kw)

    def lathe(self, profile, c, mat, n=12, cap_bottom=True, cap_top=True, rims=None, M=None, r=None):
        """Surface of revolution about the local Z axis; profile is [(r, z)] from bottom to top.

        `rims` lists the profile rings whose edge gets rounded (default: the capped ends)."""
        T = self.off @ (M or Matrix()) @ Matrix.Translation(Vector(c))
        tmp = bmesh.new()
        rings = []
        for rad, z in profile:
            rings.append([tmp.verts.new(T @ Vector((rad * math.cos(2 * math.pi * k / n), rad * math.sin(2 * math.pi * k / n), z)))
                          for k in range(n)])
        for ra, rb in zip(rings, rings[1:]):
            for k in range(n):
                tmp.faces.new((ra[k], ra[(k + 1) % n], rb[(k + 1) % n], rb[k]))
        if cap_bottom:
            tmp.faces.new(list(reversed(rings[0])))
        if cap_top:
            tmp.faces.new(rings[-1])
        if rims is None:
            rims = ([0] if cap_bottom else []) + ([len(rings) - 1] if cap_top else [])
        edges = []
        for i in rims:
            ring = rings[i]
            for a, b in zip(ring, ring[1:] + ring[:1]):
                e = tmp.edges.get((a, b))
                if e and len(e.link_faces) == 2:
                    edges.append(e)
        size = max(p_[0] for p_ in profile)
        height = abs(profile[-1][1] - profile[0][1]) or size
        rr, seg = self.rounding((size, height), r)
        self._commit(tmp, mat, edges, min(rr, 0.02), seg)

    def soft_box(self, c, s, r, mat, nc=2):
        """Cushion: a box rounded all round by radius r, built from stacked rounded-rectangle rings."""
        hx, hy, hz = s[0] / 2, s[1] / 2, s[2] / 2
        prof = []
        for k in range(nc + 1):  # bottom quarter, then top quarter
            a = math.radians(-90 + 90 * k / nc)
            prof.append((r * math.cos(a), -hz + r + r * math.sin(a)))
        for k in range(nc + 1):
            a = math.radians(90 * k / nc)
            prof.append((r * math.cos(a), hz - r + r * math.sin(a)))
        T = self.off @ Matrix.Translation(Vector(c))
        tmp = bmesh.new()
        rings = [[tmp.verts.new(T @ Vector(p_)) for p_ in rrect_ring(hx - r + d, hy - r + d, max(1e-3, d + 0.02), z, nc=2)]
                 for d, z in prof]
        m = len(rings[0])
        for ra, rb in zip(rings, rings[1:]):
            for k in range(m):
                tmp.faces.new((ra[k], ra[(k + 1) % m], rb[(k + 1) % m], rb[k]))
        tmp.faces.new(list(reversed(rings[0])))
        tmp.faces.new(rings[-1])
        self._commit(tmp, mat)

    def blob(self, c, r, mat, squash=(1, 1, 1), segs=(6, 4)):
        """Low-poly sphere for vegetables and dough (smooth, never bevelled)."""
        M = self.off @ Matrix.Translation(Vector(c)) @ Matrix.Diagonal((r * squash[0], r * squash[1], r * squash[2], 1))
        tmp = bmesh.new()
        bmesh.ops.create_uvsphere(tmp, u_segments=segs[0], v_segments=segs[1], radius=1.0, matrix=M)
        self._commit(tmp, mat)

    def finish(self):
        bm = self.bm
        bm.normal_update()
        R = Matrix.Rotation(math.radians(self.turn), 3, 'Z')   # turn about the pivot (degrees)
        for v in bm.verts:
            v.co = R @ (v.co - self.pivot)
        me = bpy.data.meshes.new(self.name)
        bm.to_mesh(me)
        bm.free()
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(60))   # only unrounded folds stay hard
        for m in self.mats:
            me.materials.append(material(m))
        ob = bpy.data.objects.new(self.name, me)
        COL.objects.link(ob)
        ob.parent = group(self.grp)
        ob.location = self.pivot
        md = ob.modifiers.new('WeightedNormal', 'WEIGHTED_NORMAL')  # flat faces stay flat, the rounds take the curve
        md.mode = 'FACE_AREA'
        md.weight = 50
        md.keep_sharp = True
        PARTS.append(ob)
        return ob


# ---------------------------------------------------------------- building parts

def along(axis, origin, inward):
    """Matrix taking wall-local (u along the wall, v into the room, z up) to world."""
    ox, oy = origin
    if axis == 'x':
        u, v = Vector((1, 0, 0)), Vector((0, inward, 0))
    else:
        u, v = Vector((0, 1, 0)), Vector((inward, 0, 0))
    M = Matrix.Identity(4)
    M.col[0][:3] = u
    M.col[1][:3] = v
    M.col[3][:3] = (ox, oy, 0)
    if M.to_3x3().determinant() < 0:  # keep faces facing outward
        M.col[1][:3] = -v
        return M, -1
    return M, 1


def wall(p, axis, origin, inward, length, posts, segs, wood_trim=True, brackets=()):
    """A timber-framed wall like 墙壁.jpg.

    posts: u positions of the columns. segs: (u0, u1, kind) with kind 'plaster', 'window', 'door',
    'opening' (an open doorway: beam and plaster above, nothing below) or 'dado' (the 走廊 wall:
    stone-block wainscot under plaster). brackets: u positions that get 雀替 under the beam.
    The wall's centre plane is at v = 0; +v faces the room."""
    M, sgn = along(axis, origin, inward)
    s = sgn  # local v sign after the handedness fix
    top = F + H
    for u in posts:
        p.box((u, 0, F + (H + 0.08) / 2), (0.17, 0.17, H + 0.08), 'Timber', M=M)
        p.box((u, 0, top + 0.08), (0.21, 0.21, 0.07), 'Timber', M=M)  # post cap
        p.box((u, 0.0, F + 0.09), (0.21, 0.21, 0.18), 'Timber', M=M, r=0.016)  # plinth block (柱础)
    p.box((length / 2, 0, top - 0.07), (length, 0.14, 0.14), 'Timber', M=M)  # top beam
    for u in brackets:  # 雀替: small corbels on both sides of a post, under the beam
        for d in (-1, 1):
            if 0 < u + d * 0.16 < length:
                p.box((u + d * 0.14, 0, top - 0.19), (0.12, 0.1, 0.1), 'Timber', M=M)
                p.box((u + d * 0.11, 0, top - 0.27), (0.06, 0.1, 0.07), 'Timber', M=M)
    for u0, u1, kind in segs:
        a, b = u0 + 0.085, u1 - 0.085
        w = b - a
        if kind != 'opening':  # sill
            p.box(((u0 + u1) / 2, 0, F + 0.05), (u1 - u0, 0.11, 0.1), 'Timber', M=M)
        if kind == 'opening':
            z_head = top - 0.36
            p.box(((a + b) / 2, -0.01 * s, (z_head + top - 0.14) / 2), (w, 0.06, top - 0.14 - z_head), 'Plaster', M=M)
            p.box(((a + b) / 2, 0.0, z_head), (w, 0.12, 0.08), 'Timber', M=M)  # door head
        elif kind == 'dado':
            z_dado = F + 0.5
            p.box(((a + b) / 2, -0.01 * s, (z_dado + top - 0.14) / 2), (w, 0.06, top - 0.14 - z_dado), 'Plaster', M=M)
            rows, bw = 3, 0.3
            for r in range(rows):  # stone blocks, courses offset by half a block
                z0 = F + 0.1 + r * (z_dado - F - 0.1) / rows
                z1 = z0 + (z_dado - F - 0.1) / rows
                n = max(1, round(w / bw))
                off = 0.5 if r % 2 else 0.0
                edges = sorted({a, b, *[a + (k + off) * w / n for k in range(n + 1) if a < a + (k + off) * w / n < b]})
                for e0, e1 in zip(edges, edges[1:]):
                    p.box(((e0 + e1) / 2, 0.0, (z0 + z1) / 2), (e1 - e0 - 0.012, 0.09, z1 - z0 - 0.012), 'Stone', M=M, r=0.014)
            p.box(((a + b) / 2, 0.02 * s, z_dado + 0.02), (w, 0.1, 0.04), 'Stone', M=M)  # coping
        elif kind == 'plaster':
            p.box(((a + b) / 2, -0.01 * s, F + H / 2), (w, 0.06, H - 0.2), 'Plaster', M=M)
            if wood_trim:  # wainscot rail
                p.box(((a + b) / 2, 0.035 * s, F + 0.62), (w, 0.05, 0.06), 'Timber', M=M)
        elif kind in ('window', 'door'):
            z_sill = F + (0.62 if kind == 'window' else 0.1)
            z_head = top - 0.42
            if kind == 'window':  # boarded wainscot under the window
                p.box(((a + b) / 2, 0.0, (F + 0.1 + z_sill) / 2), (w, 0.07, z_sill - F - 0.1), 'Timber', M=M)
                for k in range(1, 3):
                    uu = a + w * k / 3
                    p.box((uu, 0.04 * s, (F + 0.1 + z_sill) / 2), (0.04, 0.03, z_sill - F - 0.14), 'Timber', M=M)
            p.box(((a + b) / 2, -0.01 * s, (z_head + top - 0.14) / 2), (w, 0.06, top - 0.14 - z_head), 'Plaster', M=M)
            p.box(((a + b) / 2, 0.0, z_sill), (w, 0.1, 0.06), 'Timber', M=M)  # frame bottom
            p.box(((a + b) / 2, 0.0, z_head), (w, 0.1, 0.06), 'Timber', M=M)  # frame head
            p.box(((a + b) / 2, -0.03 * s, (z_sill + z_head) / 2), (w, 0.02, z_head - z_sill), 'Paper', M=M)
            # lattice (格子窗): verticals and a few rails, two leaves
            nv = max(2, round(w / 0.22))
            for k in range(1, nv):
                uu = a + w * k / nv
                p.box((uu, 0.0, (z_sill + z_head) / 2), (0.035 if k != nv // 2 else 0.06, 0.05, z_head - z_sill), 'Timber', M=M)
            for zz in ([0.4, 0.7] if kind == 'window' else [0.3, 0.65]):
                p.box(((a + b) / 2, 0.0, z_sill + (z_head - z_sill) * zz), (w, 0.045, 0.03), 'Timber', M=M)
    return M, s


def curtain(p, M, s, u0, u1, z_top, drop=0.34, strips=2):
    """Blue door curtain (门帘) on a rod, split into strips, hanging in front of an opening."""
    p.box(((u0 + u1) / 2, 0.09 * s, z_top + 0.03), (u1 - u0 + 0.12, 0.035, 0.035), 'Timber', M=M)
    for uu in (u0 - 0.03, u1 + 0.03):
        p.box((uu, 0.06 * s, z_top + 0.03), (0.05, 0.08, 0.1), 'Timber', M=M)
    gap = 0.02
    w = (u1 - u0 - gap * (strips - 1)) / strips
    for k in range(strips):
        a = u0 + k * (w + gap)
        p.box((a + w / 2, 0.1 * s, z_top - drop / 2), (w, 0.02, drop), 'Cloth', M=M)


def railing(p, x0, y0, x1, y1, posts=None):
    """Timber railing (栏杆) from (x0, y0) to (x1, y1) on the plinth edge."""
    L = math.hypot(x1 - x0, y1 - y0)
    rot = math.degrees(math.atan2(y1 - y0, x1 - x0))
    d = Vector(((x1 - x0) / L, (y1 - y0) / L, 0))
    o = Vector((x0, y0, 0))
    posts = posts or max(1, round(L / 1.0))
    for k in range(posts + 1):
        c = o + d * (L * k / posts)
        big = k in (0, posts)
        s = 0.13 if big else 0.1
        h = 0.85 if big else 0.75
        p.box((c.x, c.y, F + h / 2), (s, s, h), 'Timber', rot=rot)
        p.box((c.x, c.y, F + h + 0.035), (s + 0.04, s + 0.04, 0.07), 'Timber', rot=rot)
        p.box((c.x, c.y, F + h + 0.1), (s - 0.02, s - 0.02, 0.06), 'Timber', rot=rot)
    mid = o + d * (L / 2)
    p.box((mid.x, mid.y, F + 0.66), (L, 0.06, 0.06), 'Timber', rot=rot)
    p.box((mid.x, mid.y, F + 0.12), (L, 0.06, 0.05), 'Timber', rot=rot)
    nb = max(2, round(L / 0.2))
    for k in range(1, nb):
        c = o + d * (L * k / nb)
        p.box((c.x, c.y, F + 0.39), (0.035, 0.035, 0.5), 'Timber', rot=rot)


def steps(p, x0, x1, y_edge, n, run, direction, axis='y'):
    """Stone steps going down from the plinth edge, `direction` = -1 toward -axis."""
    rise = F / (n + 1)
    for k in range(n):
        z1 = F - rise * (k + 1)
        e0, e1 = y_edge, y_edge + direction * run * (k + 1)
        lo, hi = min(e0, e1), max(e0, e1)
        if axis == 'y':
            p.bx(x0, x1, lo, hi, 0, z1, 'Stone')
        else:
            p.bx(lo, hi, x0, x1, 0, z1, 'Stone')


# ---------------------------------------------------------------- props

def wall_lantern(p, x, y, face, z=None):
    """Round paper lantern hung from a bracket on a post; `face` is the unit direction into the room."""
    z = F + 1.55 if z is None else z
    fx, fy = face
    arm = 0.2
    p.box((x + fx * arm / 2, y + fy * arm / 2, z + 0.32), (0.04 + abs(fx) * arm, 0.04 + abs(fy) * arm, 0.04), 'Timber')
    cx, cy = x + fx * arm, y + fy * arm
    p.lathe([(0.03, z + 0.24), (0.03, z + 0.31)], (cx, cy, 0), 'Timber', n=8)
    p.lathe([(0.06, z - 0.2), (0.075, z - 0.17), (0.075, z - 0.14)], (cx, cy, 0), 'Timber', n=8, cap_top=False)
    p.lathe([(0.075, z - 0.14), (0.11, z - 0.08), (0.12, z), (0.11, z + 0.08), (0.075, z + 0.14)],
            (cx, cy, 0), 'Paper', n=8, cap_bottom=False, cap_top=False)
    p.lathe([(0.075, z + 0.14), (0.075, z + 0.17), (0.06, z + 0.24)], (cx, cy, 0), 'Timber', n=8, cap_bottom=False)


def bowl(p, x, y, z, r, mat='Ceramic', h=None):
    h = h or r * 0.55
    p.lathe([(r * 0.5, z), (r * 0.9, z + h * 0.5), (r, z + h), (r * 0.85, z + h), (r * 0.45, z + h * 0.15)],
            (x, y, 0), mat, n=8, cap_top=False, rims=[0, 2])


def basket(p, x, y, z, r, h, fill=None):
    p.lathe([(r * 0.85, z), (r, z + h), (r * 0.9, z + h)], (x, y, 0), 'Straw', n=12, cap_top=False, rims=[0, 1])
    if fill:
        rnd = random.Random(int(x * 100 + y * 10))
        for k in range(5):
            a = 2 * math.pi * k / 5
            p.blob((x + r * 0.45 * math.cos(a), y + r * 0.45 * math.sin(a), z + h * 0.95), r * 0.42, fill,
                   (1, 1, 0.85))
        p.blob((x, y, z + h * 1.15), r * 0.45, fill)


def table(grp, name, x, y):
    """方桌 as in 桌子.jpg: framed top with a breadboard edge, square legs, aprons and corner spandrels."""
    p = Prop(name, grp, (x, y, F), rmax=0.02)
    W, Ht, T = 1.0, 0.78, 0.07
    h = W / 2
    top = F + Ht
    for sx, sy in ((1, 0), (0, 1)):  # frame
        for sgn in (-1, 1):
            if sx:
                p.bx(x - h, x + h, y + sgn * h - 0.09 * (sgn > 0), y + sgn * h + 0.09 * (sgn < 0), top - T, top, 'Wood')
            else:
                p.bx(x + sgn * h - 0.09 * (sgn > 0), x + sgn * h + 0.09 * (sgn < 0), y - h + 0.09, y + h - 0.09,
                     top - T, top, 'Wood')
    for k in range(4):  # top boards, a hair lower than the frame
        y0 = y - h + 0.09 + (W - 0.18) * k / 4
        p.bx(x - h + 0.09, x + h - 0.09, y0 + 0.004, y0 + (W - 0.18) / 4 - 0.004, top - T, top - 0.006, 'Wood')
    for sx in (-1, 1):
        for sy in (-1, 1):
            lx, ly = x + sx * (h - 0.075), y + sy * (h - 0.075)
            p.box((lx, ly, F + (Ht - T) / 2), (0.085, 0.085, Ht - T), 'Wood')
    for sgn in (-1, 1):  # aprons (牙板) and spandrels
        p.bx(x - h + 0.1, x + h - 0.1, y + sgn * (h - 0.075) - 0.02, y + sgn * (h - 0.075) + 0.02, top - T - 0.08, top - T, 'Wood')
        p.bx(x + sgn * (h - 0.075) - 0.02, x + sgn * (h - 0.075) + 0.02, y - h + 0.1, y + h - 0.1, top - T - 0.08, top - T, 'Wood')
        for s2 in (-1, 1):
            p.bx(x + s2 * (h - 0.16) - 0.04, x + s2 * (h - 0.16) + 0.04, y + sgn * (h - 0.075) - 0.015,
                 y + sgn * (h - 0.075) + 0.015, top - T - 0.17, top - T - 0.08, 'Wood')
            p.bx(x + sgn * (h - 0.075) - 0.015, x + sgn * (h - 0.075) + 0.015, y + s2 * (h - 0.16) - 0.04,
                 y + s2 * (h - 0.16) + 0.04, top - T - 0.17, top - T - 0.08, 'Wood')
    return p


def stool(grp, name, x, y):
    """方凳 as in 板凳.jpg: four legs, a seat frame, low stretchers and a green cushion."""
    p = Prop(name, grp, (x, y, F), rmax=0.02)
    W, Hs = 0.44, 0.46
    h = W / 2
    top = F + Hs
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.box((x + sx * (h - 0.035), y + sy * (h - 0.035), F + (Hs + 0.02) / 2), (0.07, 0.07, Hs + 0.02), 'Wood')
    for sgn in (-1, 1):
        p.bx(x - h + 0.07, x + h - 0.07, y + sgn * (h - 0.035) - 0.025, y + sgn * (h - 0.035) + 0.025, top - 0.08, top - 0.01, 'Wood')
        p.bx(x + sgn * (h - 0.035) - 0.025, x + sgn * (h - 0.035) + 0.025, y - h + 0.07, y + h - 0.07, top - 0.08, top - 0.01, 'Wood')
        p.bx(x - h + 0.07, x + h - 0.07, y + sgn * (h - 0.035) - 0.02, y + sgn * (h - 0.035) + 0.02, F + 0.12, F + 0.16, 'Wood')
        p.bx(x + sgn * (h - 0.035) - 0.02, x + sgn * (h - 0.035) + 0.02, y - h + 0.07, y + h - 0.07, F + 0.12, F + 0.16, 'Wood')
    p.soft_box((x, y, top + 0.02), (W - 0.1, W - 0.1, 0.07), 0.03, 'Cushion')
    return p.finish()


# ---------------------------------------------------------------- stats, camera, save, export, renders

def finish_level(OUT, render_all=True, WC=False, closeups=()):
    """Writes <OUT>/<NAME>.blend and .fbx (the level, its markers), palette.json and renders/stats.json; with
    render_all also renders/whitemodel.png, the close-ups [(file, object name)], and toon.png or (WC) wc.png."""
    # ---------------------------------------------------------------- stats

    dg = bpy.context.evaluated_depsgraph_get()
    stats, total_f, total_t = {}, 0, 0
    for ob in PARTS:
        me = ob.evaluated_get(dg).to_mesh()
        f = len(me.polygons)
        t = sum(len(pl.vertices) - 2 for pl in me.polygons)
        q = sum(len(pl.vertices) == 4 for pl in me.polygons)
        ob.evaluated_get(dg).to_mesh_clear()
        stats[ob.name] = {'faces': f, 'quads': q, 'tris': t}
        total_f, total_t = total_f + f, total_t + t
        log(f'{ob.name:<16} {f:>6} faces  {t:>6} tris  ({f - q} not quads)')
    log(f'TOTAL {total_f} faces, {total_t} tris, {len(PARTS)} objects')
    os.makedirs(os.path.join(OUT, 'renders'), exist_ok=True)
    with open(os.path.join(OUT, 'renders', 'stats.json'), 'w') as fh:
        json.dump({'faces': total_f, 'tris': total_t, 'parts': stats}, fh, indent=1)
    with open(os.path.join(OUT, 'palette.json'), 'w', encoding='utf-8') as fh:
        json.dump({'toon': {k: {'lit': v[0], 'shade': v[1], 'emission': PALETTE_EMISSIVE.get(k, 0.0)}
                            for k, v in PALETTE.items()}}, fh, indent=1)

    # ---------------------------------------------------------------- camera, save, export

    cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera'))
    cam.data.type = 'ORTHO'
    scene.collection.objects.link(cam)
    scene.camera = cam
    az, el = math.radians(45), math.radians(30)  # the art is a 2:1 isometric view
    view = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    right = Vector((0, 0, 1)).cross(view).normalized()
    up = view.cross(right)
    pts = [ob.matrix_world @ Vector(c) for ob in PARTS for c in ob.bound_box]
    us, vs = [p_.dot(right) for p_ in pts], [p_.dot(up) for p_ in pts]
    cu, cv = (min(us) + max(us)) / 2, (min(vs) + max(vs)) / 2
    target = right * cu + up * cv
    aspect = 2.0
    cam.data.ortho_scale = 1.04 * max(max(us) - min(us), (max(vs) - min(vs)) * aspect)
    cam.location = target + 40 * view
    cam.rotation_euler = (-view).to_track_quat('-Z', 'Y').to_euler()
    cam.data.clip_end = 100
    scene.render.resolution_x, scene.render.resolution_y = 2000, 1000
    scene.render.film_transparent = True
    scene.view_settings.view_transform = 'Standard'


    def setup_workbench(color_type):  # noqa: E306
        scene.render.engine = 'BLENDER_WORKBENCH'
        sh = scene.display.shading
        sh.light = 'STUDIO'
        sh.color_type = color_type
        sh.single_color = CLAY
        sh.show_cavity = True
        sh.cavity_type = 'BOTH'
        sh.show_object_outline = True
        sh.object_outline_color = (0.15, 0.15, 0.15)
        sh.show_specular_highlight = False
        scene.display.render_aa = '16'


    setup_workbench('SINGLE')
    os.makedirs(OUT, exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, NAME + '.blend'))
    log('saved ' + NAME + '.blend')

    for ob in bpy.data.objects:
        ob.select_set(ob in PARTS or ob in MARKERS or ob == ROOT or ob in GROUPS.values())
    bpy.context.view_layer.objects.active = ROOT
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, NAME + '.fbx'), use_selection=True,
                             object_types={'EMPTY', 'MESH'}, apply_scale_options='FBX_SCALE_ALL',
                             axis_forward='-Z', axis_up='Y', bake_space_transform=False, use_mesh_modifiers=True,
                             mesh_smooth_type='OFF', add_leaf_bones=False, bake_anim=False)
    log('exported ' + NAME + '.fbx')

    if not render_all:
        return


    def render(name):  # noqa: E306
        scene.render.filepath = os.path.join(OUT, 'renders', name)
        bpy.ops.render.render(write_still=True)
        log('rendered renders/' + name)


    render('whitemodel.png')

    # close-ups to check the rounding (圆角) at game zoom
    saved = (cam.location.copy(), cam.data.ortho_scale, scene.render.resolution_x, scene.render.resolution_y)
    scene.render.resolution_x, scene.render.resolution_y = 1400, 1000
    for name, obj in closeups:
        t = bpy.data.objects[obj].matrix_world.translation + Vector((0, 0, 0.6))
        cam.location = t + 40 * view
        cam.data.ortho_scale = 3.2
        render(name)
    cam.location, cam.data.ortho_scale, scene.render.resolution_x, scene.render.resolution_y = saved

    # 三渲二 preview: two-tone ramp against a fixed light plus inverted-hull outlines (as for the lantern)
    light = Vector((-0.3, -0.8, 0.52)).normalized()


    def srgb(hex_color):  # noqa: E306
        c = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
        return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


    for key, mat in MATS.items():
        lit, shade = PALETTE[key]
        nt = mat.node_tree
        nt.nodes.clear()
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        dot = nt.nodes.new('ShaderNodeVectorMath')
        dot.operation = 'DOT_PRODUCT'
        dot.inputs[1].default_value = light
        ramp = nt.nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.interpolation = 'CONSTANT'
        ramp.color_ramp.elements[0].color = (*srgb(shade), 1)
        ramp.color_ramp.elements[1].position = 0.01
        ramp.color_ramp.elements[1].color = (*srgb(lit), 1)
        emit = nt.nodes.new('ShaderNodeEmission')
        nt.links.new(geo.outputs['Normal'], dot.inputs[0])
        nt.links.new(dot.outputs['Value'], ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], emit.inputs['Color'])
        nt.links.new(emit.outputs[0], out.inputs['Surface'])

    m_line = bpy.data.materials.new('M_Outline')
    m_line.use_backface_culling = True
    nt = m_line.node_tree
    nt.nodes.clear()
    emit = nt.nodes.new('ShaderNodeEmission')
    emit.inputs['Color'].default_value = (*srgb('#6b4630' if WC else '#5a3a26'), 1)
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(geo.outputs['Backfacing'], mix.inputs['Fac'])
    nt.links.new(emit.outputs[0], mix.inputs[1])
    nt.links.new(nt.nodes.new('ShaderNodeBsdfTransparent').outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], nt.nodes.new('ShaderNodeOutputMaterial').inputs['Surface'])

    dg = bpy.context.evaluated_depsgraph_get()
    for ob in list(PARTS):
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
        me.materials.clear()
        me.materials.append(m_line)
        hull = bpy.data.objects.new(ob.name + '_outline', me)
        hull.matrix_world = ob.matrix_world
        scene.collection.objects.link(hull)
        bm = bmesh.new()
        bm.from_mesh(me)
        bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-4)
        bm.normal_update()
        for v in bm.verts:
            v.co += v.normal * (0.009 if WC else 0.012)
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        bm.to_mesh(me)
        bm.free()

    if WC:
        # ---- style C: the same scene with painted materials and real sunlight (see wc_materials.py)
        sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
        import wc_materials
        TEXDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'CookView', 'tex')
        TEX = {'Plaster': ('plaster', 0.5), 'Timber': ('post', 1.2, 1.05, 0.98), 'Wood': ('countertop', 1.2, 1.0, 0.95),
               'WoodFloor': ('floor', 0.3, 0.9, 0.95), 'Tile': ('brick', 0.9, 0.55, 1.3),
               'Brick': ('brick', 1.8), 'Straw': ('basket', 5.0), 'Glaze': ('glaze', 6.0)}
        WC_COL = {'Cloth': ('#4a619a', '#35477a'), 'Cushion': ('#a9bf8a', '#7f9763')}
        imgs = {}
        new = {}
        for key in MATS:
            lit, shade = WC_COL.get(key, PALETTE[key])
            t = TEX.get(key)
            kw = {}
            if t:
                if t[0] not in imgs:
                    imgs[t[0]] = bpy.data.images.load(os.path.join(TEXDIR, t[0] + '.png'))
                kw = dict(tex=imgs[t[0]], tex_scale=t[1], **dict(zip(('sat', 'val'), t[2:])))
            new[MATS[key].name] = wc_materials.painted(key, lit, shade, srgb, key == 'Fire', **kw)
        for ob in PARTS:
            for i, m in enumerate(ob.data.materials):
                if m and m.name in new:
                    ob.data.materials[i] = new[m.name]
        with open(os.path.join(OUT, 'wc_materials.json'), 'w', encoding='utf-8') as fh:   # for the Unity shader
            json.dump({k: {'lit': WC_COL.get(k, PALETTE[k])[0], 'shade': WC_COL.get(k, PALETTE[k])[1],
                           'tex': TEX[k][0] if k in TEX else None, 'scale': TEX[k][1] if k in TEX else 1.0,
                           'sat': TEX[k][2] if k in TEX and len(TEX[k]) > 2 else 1.28,
                           'val': TEX[k][3] if k in TEX and len(TEX[k]) > 3 else 1.08,
                           'kind': wc_materials.kind_of(k), 'dappled': k in wc_materials.DAPPLED,
                           'emissive': k == 'Fire'} for k in MATS}, fh, indent=1, ensure_ascii=False)
        sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN'))
        sun.data.energy = 3.2
        sun.data.angle = 0.1
        sun.rotation_euler = (-light).to_track_quat('-Z', 'Y').to_euler()
        scene.collection.objects.link(sun)
        scene.world = bpy.data.worlds.new('World')
        scene.world.use_nodes = True
        scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.35, 0.33, 0.3, 1)
        scene.render.film_transparent = True
        scene.render.engine = 'BLENDER_EEVEE'
        scene.eevee.taa_render_samples = 32
        render('wc.png')
        bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'renders', TAG + '_wc.blend'))
        return
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 16
    scene.cycles.use_denoising = False
    scene.cycles.filter_width = 1.0
    render('toon.png')
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'renders', TAG + '_toon.blend'))   # for make_video.py
    log('saved renders/' + TAG + '_toon.blend')

