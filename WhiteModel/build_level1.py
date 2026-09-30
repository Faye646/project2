"""初始关卡（一级 · 1 桌）白模 for the 汴河两岸 三渲二 pipeline.

Built procedurally from the level art 初始1桌布局.jpg and its part sheets (厨房, 餐厅, 墙壁, 桌子,
板凳, 厨房地板, 饭堂地板), in the same style as 纹璃宫灯: every hard edge of the timber, stone and
furniture is rounded (Bevel modifier, 2 segments, hardened normals), turned parts are lathed, and
the bottoms of floor tiles / planks that nobody can see are left open.

Layout (meters, Z up, the kitchen's front-left corner at the origin):
    后厨 kitchen   x 0 – 4.2,    y 0 – 3.6
    走廊 corridor  x 4.2 – 7.2,  y 2.3 – 3.6   (走廊.png: stone-dado back wall, open front)
    前堂 hall      x 7.2 – 12.6, y 2.3 – 6.9   (built at x 4.9 / y 3.6, then its group is moved)
Back walls stand on the far sides (x = min, y = max); the near sides are open, as in the art.
Spot_Queue_1…4 empties mark where waiting guests stand.

Every prop is one object whose pivot sits at the middle of its footprint on the floor. The
object names are what the Unity side keys on (K_AnTai is the 案台 that opens the cooking screen).

Run with Blender 5.2:
    blender -b --factory-startup --python build_level1.py -- <out_dir> [--no-render]
Writes SM_Level1.blend / .fbx, palette.json and renders/ (clay, wire, toon) to <out_dir>.
"""
import json
import math
import os
import random
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = os.path.abspath(ARGS[0]) if ARGS and not ARGS[0].startswith('--') else \
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Level1')
RENDER = '--no-render' not in ARGS
NAME = 'SM_Level1'
CLAY = (0.8, 0.8, 0.8)
F = 0.45     # floor height (top of the stone plinth)
H = 2.0      # wall height above the floor; the walls are cut low like the art
random.seed(7)


def log(msg):
    print(f'[level1] {msg}', flush=True)


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

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.save_version = 0
scene = bpy.context.scene
COL = bpy.data.collections.new(NAME)
scene.collection.children.link(COL)
ROOT = bpy.data.objects.new(NAME, None)
ROOT.empty_display_type = 'PLAIN_AXES'
COL.objects.link(ROOT)
GROUPS = {}
PARTS = []
MATS = {}


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

def wall_lantern(p, x, y, face, z=F + 1.55):
    """Round paper lantern hung from a bracket on a post; `face` is the unit direction into the room."""
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


# ================================================================= build

# ---------------- 后厨 kitchen: plinth, stone floor, walls
KX, KY = 5.0, 4.2   # a little roomier than the art (4.2 × 3.6)
DX0, DX1, DY0, DY1 = 4.9, 10.3, 3.6, 8.2

p = Prop('K_Plinth', 'Kitchen', (KX / 2, KY / 2, 0), rmax=0.03)
p.bx(-0.1, KX + 0.1, -0.1, KY + 0.1, 0, 0.22, 'Stone')
p.bx(-0.08, KX + 0.08, -0.08, KY + 0.08, 0.22, F - 0.04, 'Stone')
for k in range(int(KX / 0.35)):  # kerb stones along the two open sides
    x0 = -0.1 + k * (KX + 0.2) / int(KX / 0.35)
    p.bx(x0 + 0.005, x0 + (KX + 0.2) / int(KX / 0.35) - 0.005, -0.1, 0.18, F - 0.05, F + 0.01, 'Stone')
for k in range(int((KY + 0.2) / 0.35)):
    n = int((KY + 0.2) / 0.35)
    y0 = 0.18 + k * (KY - 0.1) / n
    p.bx(KX - 0.18, KX + 0.1, y0 + 0.005, y0 + (KY - 0.1) / n - 0.005, F - 0.05, F + 0.01, 'Stone')
p.finish()

p = Prop('K_Floor', 'Kitchen', (KX / 2, KY / 2, F), rmax=0.02)
cell = 0.42
nx, ny = int((KX - 0.3) / cell), int((KY - 0.3) / cell)
cx0, cy0 = 0.09, 0.2
cw, ch = (KX - 0.19 - cx0) / nx, (KY - 0.09 - cy0) / ny
g = 0.025
for i in range(nx):
    for j in range(ny):
        x0, y0 = cx0 + i * cw, cy0 + j * ch
        if random.random() < 0.22:  # a few cells split into four small stones, as in 厨房地板.jpg
            for a in range(2):
                for b in range(2):
                    p.bx(x0 + a * cw / 2 + g / 2, x0 + (a + 1) * cw / 2 - g / 2, y0 + b * ch / 2 + g / 2,
                         y0 + (b + 1) * ch / 2 - g / 2, F - 0.04, F + 0.012, 'Tile', open_bottom=True, top_only=True)
        else:
            p.bx(x0 + g / 2, x0 + cw - g / 2, y0 + g / 2, y0 + ch - g / 2, F - 0.04, F + 0.012 + random.uniform(0, 0.006),
                 'Tile', open_bottom=True, top_only=True)
p.finish()

p = Prop('K_Walls', 'Kitchen', (0, KY, F), rmax=0.03)
wall(p, 'y', (0, 0), 1, KY, [0.0, 1.8, KY], [(0.0, 1.8, 'plaster'), (1.8, KY, 'plaster')])
M, s = wall(p, 'x', (0, KY), -1, KX, [1.5, 2.4, 3.3, KX],
            [(0.0, 1.5, 'plaster'), (1.5, 2.4, 'plaster'), (2.4, 3.3, 'window'), (3.3, KX, 'plaster')])
curtain(p, M, s, 2.5, 3.2, F + H - 0.45, drop=0.3)
wall_lantern(p, 3.3, KY - 0.09, (0, -1))
p.finish()

# 灶台 stove (初等): brick body along the left wall, iron wok, fire mouth, chimney
p = Prop('K_ZaoTai', 'Kitchen', (0.55, 1.95, F), rmax=0.03, off=(0, 0.35))
p.bx(0.1, 1.02, 1.2, 2.7, F, F + 0.72, 'Brick')
p.bx(0.08, 1.05, 1.18, 2.72, F + 0.72, F + 0.8, 'Brick')          # top slab
p.bx(1.0, 1.08, 1.45, 1.8, F + 0.1, F + 0.38, 'Iron')              # fire mouth
p.blob((1.03, 1.625, F + 0.2), 0.1, 'Fire', (0.4, 1.2, 1.0))
p.lathe([(0.02, F + 0.66), (0.2, F + 0.72), (0.31, F + 0.83), (0.33, F + 0.86), (0.3, F + 0.86), (0.18, F + 0.76)],
        (0.58, 1.6, 0), 'Iron', n=16, cap_bottom=False, cap_top=False, rims=[3])
p.lathe([(0.2, F + 0.8), (0.21, F + 0.95), (0.19, F + 0.95)], (0.58, 2.2, 0), 'Straw', n=14, cap_top=False,
        rims=[0, 1])                                                # steamer on the second hole
p.lathe([(0.21, F + 0.95), (0.13, F + 1.02), (0.03, F + 1.05)], (0.58, 2.2, 0), 'Straw', n=14, cap_bottom=False)
p.bx(0.1, 0.52, 2.28, 2.7, F + 0.8, F + H + 0.55, 'Brick')         # chimney
p.bx(0.07, 0.55, 2.25, 2.73, F + H + 0.55, F + H + 0.65, 'Brick')
p.bx(1.02, 1.3, 2.25, 2.62, F, F + 0.3, 'Brick')                   # side step
stove = p.finish()

p = Prop('K_ChaiDui', 'Kitchen', (0.5, 0.65, F), rmax=0.02)       # firewood stack
for layer, n in enumerate((4, 3, 2)):
    for k in range(n):
        x = 0.28 + k * 0.17 + layer * 0.085
        p.lathe([(0.075, -0.3), (0.075, 0.3)], (0, 0, 0), 'Wood', n=8,
                M=Matrix.Translation((x, 0.65, F + 0.075 + layer * 0.14)) @ Matrix.Rotation(math.radians(90), 4, 'X'))
p.bx(0.18, 0.95, 0.3, 0.35, F, F + 0.05, 'Timber')
p.finish()

p = Prop('K_Crates', 'Kitchen', (0.4, 3.1, F), rmax=0.03, off=(0, 0.6))
p.bx(0.12, 0.62, 2.85, 3.45, F, F + 0.4, 'Wood')
p.bx(0.16, 0.56, 2.92, 3.4, F + 0.4, F + 0.72, 'Wood')
basket(p, 0.36, 3.16, F + 0.72, 0.13, 0.1, fill='Veg')
p.finish()

p = Prop('K_Counter', 'Kitchen', (1.6, 3.28, F), rmax=0.025, off=(0.1, 0.6))       # counter by the back wall
p.bx(0.75, 2.05, 3.0, 3.5, F, F + 0.72, 'Wood')
p.bx(0.72, 2.08, 2.96, 3.52, F + 0.72, F + 0.78, 'Wood')
for k in range(3):
    x0 = 0.8 + k * 0.415
    p.bx(x0 + 0.02, x0 + 0.395, 2.97, 3.0, F + 0.12, F + 0.62, 'Wood')
basket(p, 1.05, 3.24, F + 0.78, 0.15, 0.1, fill='Veg')
basket(p, 1.5, 3.24, F + 0.78, 0.14, 0.1, fill='Chili')
bowl(p, 1.85, 3.24, F + 0.78, 0.12)
p.bx(0.8, 2.0, 3.36, 3.52, F + 1.25, F + 1.29, 'Wood')             # wall shelf with jars
for x in (0.95, 1.25, 1.55, 1.85):
    p.lathe([(0.05, F + 1.29), (0.07, F + 1.36), (0.05, F + 1.45), (0.035, F + 1.47)], (x, 3.44, 0), 'Glaze', n=10)
for k in range(4):                                                   # hanging chilli string
    p.blob((2.02, 3.47, F + 1.62 - k * 0.1), 0.045, 'Chili', (1, 1, 1.4))
p.finish()

p = Prop('K_ShuiChi', 'Kitchen', (2.6, 3.26, F), rmax=0.03, off=(0.3, 0.6))       # wash stand under the window
p.bx(2.28, 2.92, 3.0, 3.5, F, F + 0.62, 'Stone')
p.bx(2.25, 2.95, 2.97, 3.52, F + 0.62, F + 0.8, 'Stone')
p.bx(2.33, 2.87, 3.04, 3.46, F + 0.74, F + 0.79, 'Water')
p.lathe([(0.1, F + 0.8), (0.13, F + 0.95), (0.11, F + 0.95)], (2.8, 3.1, 0), 'Wood', n=12, cap_top=False, rims=[0, 1])
p.finish()

p = Prop('K_WanGui', 'Kitchen', (3.6, 3.36, F), rmax=0.02, off=(0.55, 0.6))        # bowl shelf (碗柜)
for x in (3.2, 4.0):
    for y in (3.2, 3.5):
        p.box((x, y, F + 0.85), (0.06, 0.06, 1.7), 'Wood')
for k, z in enumerate((0.05, 0.45, 0.85, 1.25, 1.65)):
    p.bx(3.17, 4.03, 3.17, 3.53, F + z, F + z + 0.04, 'Wood')
    if 0 < k < 4:
        for j in range(3):
            x = 3.35 + j * 0.25
            for s_ in range(2 if (k + j) % 2 else 3):
                bowl(p, x, 3.35, F + z + 0.04 + s_ * 0.045, 0.09)
p.bx(3.17, 4.03, 3.17, 3.53, F, F + 0.05, 'Wood')
p.finish()

# 案台 work table in the middle: the one the player taps to open the cooking screen
p = Prop('K_AnTai', 'Kitchen', (2.1, 1.75, F), rmax=0.025, off=(0.45, 0.35), turn=90)   # long side facing the camera's right
x0, x1, y0, y1 = 1.3, 2.9, 1.4, 2.1
p.bx(x0, x1, y0, y1, F + 0.74, F + 0.84, 'Wood')
for x in (x0 + 0.07, x1 - 0.07):
    for y in (y0 + 0.07, y1 - 0.07):
        p.box((x, y, F + 0.37), (0.1, 0.1, 0.74), 'Wood')
p.bx(x0 + 0.1, x1 - 0.1, y0 + 0.04, y0 + 0.08, F + 0.62, F + 0.72, 'Wood')
p.bx(x0 + 0.1, x1 - 0.1, y1 - 0.08, y1 - 0.04, F + 0.62, F + 0.72, 'Wood')
p.bx(x0 + 0.1, x1 - 0.1, y0 + 0.08, y1 - 0.08, F + 0.16, F + 0.2, 'Wood')      # low shelf
basket(p, 1.65, 1.75, F + 0.2, 0.17, 0.14, fill='Veg')
basket(p, 2.2, 1.75, F + 0.2, 0.17, 0.14)
p.lathe([(0.22, F + 0.84), (0.22, F + 0.91)], (1.75, 1.75, 0), 'Wood', n=16)  # chopping block
p.bx(1.85, 2.05, 1.62, 1.72, F + 0.91, F + 0.925, 'Iron', rot=0)              # cleaver
p.bx(2.05, 2.12, 1.65, 1.69, F + 0.905, F + 0.93, 'Wood')
p.blob((1.66, 1.78, F + 0.96), 0.06, 'Veg', (1.2, 1, 0.8))
p.blob((2.4, 1.6, F + 0.93), 0.09, 'Veg', (1, 1, 0.85))                       # cabbage
p.blob((2.52, 1.72, F + 0.92), 0.075, 'Veg', (1, 1, 0.85))
bowl(p, 2.6, 1.93, F + 0.84, 0.1)
bowl(p, 2.35, 1.95, F + 0.84, 0.08)
p.bx(2.7, 2.85, 1.45, 1.85, F + 0.84, F + 0.86, 'Straw')                      # tray with dough
p.blob((2.77, 1.55, F + 0.88), 0.03, 'Ceramic')
p.blob((2.77, 1.65, F + 0.88), 0.03, 'Ceramic')
p.blob((2.77, 1.75, F + 0.88), 0.03, 'Ceramic')
an_tai = p.finish()

p = Prop('K_Guizi', 'Kitchen', (1.75, 0.5, F), rmax=0.025, off=(0.35, 0))         # low cabinet at the front
p.bx(1.15, 2.35, 0.3, 0.72, F, F + 0.58, 'Wood')
p.bx(1.12, 2.38, 0.27, 0.75, F + 0.58, F + 0.63, 'Wood')
for k in range(2):
    p.bx(1.2 + k * 0.58, 1.72 + k * 0.58, 0.27, 0.3, F + 0.08, F + 0.52, 'Wood')
basket(p, 1.45, 0.5, F + 0.63, 0.13, 0.09, fill='Veg')
bowl(p, 1.95, 0.5, F + 0.63, 0.11)
p.finish()

p = Prop('K_ShuiGang', 'Kitchen', (2.95, 0.6, F), rmax=0.02, off=(0.85, 0.05))       # water tub
prof = [(0.3, F), (0.33, F + 0.08), (0.34, F + 0.08), (0.34, F + 0.12), (0.345, F + 0.3),
        (0.355, F + 0.3), (0.355, F + 0.36), (0.36, F + 0.5), (0.33, F + 0.5), (0.31, F + 0.12)]
p.lathe(prof, (2.95, 0.6, 0), 'Wood', n=14, cap_top=False, rims=[0, 8])
p.lathe([(0.315, F + 0.44)], (2.95, 0.6, 0), 'Water', n=14, cap_bottom=False)
p.finish()

p = Prop('K_Sieve', 'Kitchen', (0.1, 0.9, F + 1.35), rmax=0.01, off=(0, 0.35))   # sieve and ladle on the left wall
p.lathe([(0.2, -0.02), (0.2, 0.02), (0.17, 0.02)], (0, 0, 0), 'Straw', n=16, cap_top=False,
        M=Matrix.Translation((0.12, 0.8, F + 1.4)) @ Matrix.Rotation(math.radians(90), 4, 'Y'))
p.bx(0.1, 0.13, 1.13, 1.17, F + 1.0, F + 1.5, 'Wood')
p.lathe([(0.06, -0.02), (0.06, 0.02)], (0, 0, 0), 'Iron', n=10,
        M=Matrix.Translation((0.14, 1.15, F + 0.98)) @ Matrix.Rotation(math.radians(90), 4, 'Y'))
p.finish()


# ---------------- 走廊 corridor (走廊.png): kitchen → hall along the back line
# Runs along x behind the kitchen's back wall line: an open doorframe on the kitchen side, the hall's
# left wall (with a curtained opening) on the other, a stone-dado wall behind, the front left open.
CL, CW = 3.0, 1.3                  # length and width
CX0, CX1 = KX, KX + CL
CY0, CY1 = KY - CW, KY

p = Prop('C_Plinth', 'Corridor', ((CX0 + CX1) / 2, (CY0 + CY1) / 2, 0), rmax=0.03)
p.bx(CX0 + 0.1, CX1 - 0.1, CY0 - 0.1, CY1 + 0.1, 0, 0.22, 'Stone')
p.bx(CX0 + 0.1, CX1 - 0.1, CY0 - 0.08, CY1 + 0.08, 0.22, F - 0.04, 'Stone')
n = int((CL - 0.2) / 0.34)
for k in range(n):  # kerb stones along the open front
    x0 = CX0 + 0.1 + k * (CL - 0.2) / n
    p.bx(x0 + 0.005, x0 + (CL - 0.2) / n - 0.005, CY0 - 0.1, CY0 + 0.16, F - 0.05, F + 0.01, 'Stone')
p.finish()

p = Prop('C_Floor', 'Corridor', ((CX0 + CX1) / 2, (CY0 + CY1) / 2, F), rmax=0.02)
nx, ny = round((CL - 0.2) / 0.36), 3
cw, ch = (CL - 0.2) / nx, (CY1 - 0.08 - CY0 - 0.16) / ny
for i in range(nx):
    for j in range(ny):
        x0, y0 = CX0 + 0.1 + i * cw, CY0 + 0.16 + j * ch
        p.bx(x0 + 0.0125, x0 + cw - 0.0125, y0 + 0.0125, y0 + ch - 0.0125, F - 0.04, F + 0.012 + random.uniform(0, 0.006),
             'Tile', open_bottom=True, top_only=True)
p.finish()

p = Prop('C_Walls', 'Corridor', ((CX0 + CX1) / 2, CY1, F), rmax=0.03)
# back wall: its end posts are the kitchen's and the hall's corner posts
M, s_ = wall(p, 'x', (CX0, CY1), -1, CL, [1.0, 2.0], [(0.0, 1.0, 'dado'), (1.0, 2.0, 'dado'), (2.0, CL, 'dado')],
             brackets=[0.0, 1.0, 2.0, CL])
wall_lantern(p, CX0 + 1.0, CY1 - 0.09, (0, -1))
# kitchen-side doorframe across the corridor
wall(p, 'y', (CX0, CY0), 1, CW, [0.0], [(0.0, CW, 'opening')], brackets=[0.0, CW])
p.finish()

# ---------------- 前堂 hall
p = Prop('D_Plinth', 'Hall', ((DX0 + DX1) / 2, (DY0 + DY1) / 2, 0), rmax=0.03)
p.bx(DX0 - 0.1, DX1 + 0.1, DY0 - 0.1, DY1 + 0.1, 0, 0.22, 'Stone')
p.bx(DX0 - 0.08, DX1 + 0.08, DY0 - 0.08, DY1 + 0.08, 0.22, F - 0.04, 'Stone')
n = int((DX1 - DX0 + 0.2) / 0.36)
for k in range(n):
    x0 = DX0 - 0.1 + k * (DX1 - DX0 + 0.2) / n
    if 6.55 < x0 + 0.18 < 7.75:
        continue  # the steps take this bit
    p.bx(x0 + 0.005, x0 + (DX1 - DX0 + 0.2) / n - 0.005, DY0 - 0.1, DY0 + 0.16, F - 0.05, F + 0.005, 'Stone')
n = int((DY1 - DY0) / 0.36)
for k in range(n):
    y0 = DY0 + 0.16 + k * (DY1 - DY0 - 0.06) / n
    p.bx(DX1 - 0.16, DX1 + 0.1, y0 + 0.005, y0 + (DY1 - DY0 - 0.06) / n - 0.005, F - 0.05, F + 0.005, 'Stone')
steps(p, 6.6, 7.7, DY0 - 0.1, 3, 0.27, -1)
p.finish()

p = Prop('D_Floor', 'Hall', ((DX0 + DX1) / 2, (DY0 + DY1) / 2, F), rmax=0.012)
pw = 0.2
yy = DY0 + 0.16
row = 0
while yy < DY1 - 0.08:
    y1 = min(yy + pw, DY1 - 0.06)
    xx = DX0 + 0.06
    offs = [0.0, 0.9, 0.45, 1.35][row % 4]
    cuts = [xx] + [c for c in (DX0 + 0.06 + offs + 1.8 * k for k in range(1, 5)) if xx + 0.3 < c < DX1 - 0.46] + [DX1 - 0.16]
    for a, b in zip(cuts, cuts[1:]):
        p.bx(a + 0.004, b - 0.004, yy + 0.005, y1 - 0.005, F - 0.04, F + 0.008, 'WoodFloor', open_bottom=True, top_only=True)
    yy = y1
    row += 1
p.finish()

p = Prop('D_Walls', 'Hall', (DX0, DY1, F), rmax=0.03)
L1 = DY1 - DY0
DOOR_U0, DOOR_U1 = 0.0, CW   # the opening onto the corridor: the front end of the hall's left wall
M1, s1 = wall(p, 'y', (DX0, DY0), 1, L1, [DOOR_U0, DOOR_U1, 2.5, 3.6, L1],
              [(DOOR_U0, DOOR_U1, 'opening'), (DOOR_U1, 2.5, 'window'), (2.5, 3.6, 'window'), (3.6, L1, 'plaster')],
              brackets=[DOOR_U0, DOOR_U1])
curtain(p, M1, s1, DOOR_U0 + 0.1, DOOR_U1 - 0.1, F + H - 0.42, drop=0.62, strips=2)   # 门帘 at the corridor's end
curtain(p, M1, s1, DOOR_U1 + 0.1, 2.4, F + H - 0.45)
curtain(p, M1, s1, 2.6, 3.5, F + H - 0.45)
L2 = DX1 - DX0
M2, s2 = wall(p, 'x', (DX0, DY1), -1, L2, [1.1, 2.45, 3.2, 4.45, L2],
              [(0.0, 1.1, 'plaster'), (1.1, 2.45, 'window'), (2.45, 3.2, 'plaster'), (3.2, 4.45, 'window'),
               (4.45, L2, 'plaster')])
curtain(p, M2, s2, 1.2, 2.35, F + H - 0.45)
curtain(p, M2, s2, 3.3, 4.35, F + H - 0.45)
for (x, y, face) in ((DX0, DY0 + 3.6, (1, 0)), (DX0 + 2.45, DY1, (0, -1)),
                     (DX0 + 3.2, DY1, (0, -1))):
    wall_lantern(p, x + face[0] * 0.09, y + face[1] * 0.09, face)
# scroll painting (挂画) on the right-hand plaster panel
p.bx(DX0 + 4.7, DX0 + 5.2, DY1 - 0.06, DY1 - 0.045, F + 0.85, F + 1.7, 'Paper')
p.bx(DX0 + 4.66, DX0 + 5.24, DY1 - 0.08, DY1 - 0.04, F + 1.7, F + 1.74, 'Timber')
p.bx(DX0 + 4.66, DX0 + 5.24, DY1 - 0.08, DY1 - 0.04, F + 0.81, F + 0.85, 'Timber')
p.finish()

p = Prop('D_Railings', 'Hall', ((DX0 + DX1) / 2, DY0, F), rmax=0.02)
railing(p, DX0 + 0.05, DY0 - 0.02, 6.55, DY0 - 0.02, posts=2)
railing(p, 7.75, DY0 - 0.02, 9.6, DY0 - 0.02, posts=2)
railing(p, DX1 - 0.02, DY1 - 1.3, DX1 - 0.02, DY1 - 0.05, posts=1)
p.finish()

p = Prop('D_Path', 'Hall', (6.4, 2.4, 0), rmax=0.02)             # stepping stones toward the street
for i, (x, y, w, d) in enumerate(((7.1, 2.35, 0.9, 0.42), (6.7, 1.85, 0.7, 0.4), (7.35, 1.8, 0.45, 0.38),
                                   (6.35, 1.35, 0.6, 0.38), (6.95, 1.3, 0.5, 0.36), (6.0, 0.85, 0.55, 0.4))):
    p.box((x, y, 0.02), (w, d, 0.06), 'Stone', rot=random.uniform(-4, 4))
p.finish()

TX, TY = 7.75, 6.0
p = table('Hall', 'D_Table_1', TX, TY)
for dx, dy in ((0.22, -0.2), (-0.2, 0.22)):
    p.lathe([(0.03, F + 0.78), (0.045, F + 0.84), (0.04, F + 0.84)], (TX + dx, TY + dy, 0), 'Ceramic', n=10, cap_top=False)
p.finish()
for i, (dx, dy) in enumerate(((0, -0.78), (0.78, 0), (0, 0.78), (-0.78, 0))):
    stool('Hall', f'D_Stool_{i + 1}', TX + dx, TY + dy)

p = Prop('D_Cabinet', 'Hall', (9.6, 7.95, F), rmax=0.025)         # side cabinet
p.bx(9.05, 10.15, 7.72, 8.1, F, F + 0.75, 'Wood')
p.bx(9.02, 10.18, 7.69, 8.12, F + 0.75, F + 0.8, 'Wood')
for k in range(2):
    p.bx(9.1 + k * 0.53, 9.6 + k * 0.53, 7.69, 7.72, F + 0.1, F + 0.68, 'Wood')
p.finish()
# potted plants and flowers are left out until their own reference art arrives

# where guests queue when the table is taken: on the stepping stones in front of the hall steps
MARKERS = []
for i, (x, y) in enumerate(((7.1, 2.35), (6.7, 1.85), (7.35, 1.8), (6.35, 1.35))):
    m = bpy.data.objects.new(f'Spot_Queue_{i + 1}', None)
    m.empty_display_size = 0.2
    m.location = (x, y, 0.05)
    COL.objects.link(m)
    m.parent = group('Hall')
    MARKERS.append(m)

# The hall was laid out with its left wall at x = 4.9 and its front at y = 3.6; slide it so the
# opening in that wall meets the corridor's far end.
group('Hall').location = (CX1 - DX0, CY0 - (DY0 + DOOR_U0), 0)
bpy.context.view_layer.update()


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


def setup_workbench(color_type):
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

if not RENDER:
    sys.exit(0)


def render(name):
    scene.render.filepath = os.path.join(OUT, 'renders', name)
    bpy.ops.render.render(write_still=True)
    log('rendered renders/' + name)


render('whitemodel.png')

# close-ups to check the rounding (圆角) at game zoom
saved = (cam.location.copy(), cam.data.ortho_scale, scene.render.resolution_x, scene.render.resolution_y)
scene.render.resolution_x, scene.render.resolution_y = 1400, 1000
for name, obj in (('closeup_kitchen.png', 'K_AnTai'), ('closeup_hall.png', 'D_Table_1'), ('closeup_corridor.png', 'C_Walls')):
    t = bpy.data.objects[obj].matrix_world.translation + Vector((0, 0, 0.6))
    cam.location = t + 40 * view
    cam.data.ortho_scale = 3.2
    render(name)
cam.location, cam.data.ortho_scale, scene.render.resolution_x, scene.render.resolution_y = saved

# 三渲二 preview: two-tone ramp against a fixed light plus inverted-hull outlines (as for the lantern)
light = Vector((-0.3, -0.8, 0.52)).normalized()


def srgb(hex_color):
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
emit.inputs['Color'].default_value = (*srgb('#5a3a26'), 1)
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
        v.co += v.normal * 0.012
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()

scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 16
scene.cycles.use_denoising = False
scene.cycles.filter_width = 1.0
render('toon.png')
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, 'renders', 'level1_toon.blend'))   # for make_video.py
log('saved renders/level1_toon.blend')
