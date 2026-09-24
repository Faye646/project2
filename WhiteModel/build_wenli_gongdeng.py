"""纹璃宫灯 white model (白模) for the 汴河两岸 三渲二 pipeline.

Built procedurally from the reference image 例子尝试.jpg, in two variants:
  high (default)  every hard edge carries a non-destructive Bevel modifier (圆角) with
                  hardened normals, so toon shading gets a clean edge highlight and
                  inverted-hull outlines stay unbroken at the corners.
  --low           game version of about 3000 faces, all quads. The same curves and rounded
                  edges are modelled straight into the topology, faces that can never be seen
                  are left out, and weighted normals keep the flat faces flat.
  --low500        the same idea squeezed to about 500 faces: every visible edge keeps at least
                  a chamfer, which weighted normals shade like a rounded edge.

Run with Blender 5.2:
    blender -b --factory-startup --python build_wenli_gongdeng.py -- <out_dir> [--low | --low500] [--quick | --no-render] [--watercolor]
Writes SM_WenliGongdeng[_Low|_500].blend / .fbx to <out_dir> and preview renders to <out_dir>/renders
(--quick renders only the clay view; --watercolor also renders the passes watercolor.py paints
from, into renders/passes). Units are meters, Z up, pivot at the ground center.
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Matrix, Vector

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = os.path.abspath(ARGS[0]) if ARGS and not ARGS[0].startswith('--') else os.path.dirname(os.path.abspath(__file__))
RENDER = '--no-render' not in ARGS
QUICK = '--quick' in ARGS
WATERCOLOR = '--watercolor' in ARGS
VARIANT = 'low' if '--low' in ARGS else '500' if '--low500' in ARGS else 'high'
NAME = 'SM_WenliGongdeng' + {'high': '', 'low': '_Low', '500': '_500'}[VARIANT]
TAG = {'high': '', 'low': '_low', '500': '_500'}[VARIANT]  # render file suffix
CLAY = (0.8, 0.8, 0.8)


def log(msg):
    print(f'[lantern] {msg}', flush=True)


# ---------------------------------------------------------------- geometry helpers

def rrect_ring(hx, hy, r, z, nc=4, m=0, sag=0.0):
    """Rounded rectangle at height z, counter-clockwise seen from above.

    nc segments per corner arc, m extra points per straight side, each side bowed
    inward by `sag`. Rings built with the same nc/m have the same vertex count.
    """
    r = max(1e-4, min(r, hx - 1e-4, hy - 1e-4))
    centers = [(hx - r, hy - r), (r - hx, hy - r), (r - hx, r - hy), (hx - r, r - hy)]
    pts = []
    for i, (cx, cy) in enumerate(centers):
        for k in range(nc + 1):
            a = math.radians(90 * i + 90 * k / nc)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a), z))
        a1 = math.radians(90 * (i + 1))  # outward normal of the side that follows
        nx, ny = centers[(i + 1) % 4]
        sx, sy = pts[-1][0], pts[-1][1]
        ex, ey = nx + r * math.cos(a1), ny + r * math.sin(a1)
        for j in range(1, m + 1):
            t = j / (m + 1)
            b = sag * math.sin(math.pi * t)
            pts.append((sx + (ex - sx) * t - b * math.cos(a1), sy + (ey - sy) * t - b * math.sin(a1), z))
    return pts


def loft(rings, cap_bottom=True, cap_top=True):
    bm = bmesh.new()
    vr = [[bm.verts.new(p) for p in ring] for ring in rings]
    n = len(vr[0])
    for lo, hi in zip(vr, vr[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    if cap_bottom:
        bm.faces.new(list(reversed(vr[0])))
    if cap_top:
        bm.faces.new(vr[-1])
    return bm


def profile_loft(profile, r_ratio, nc=4, m=0, sag=0.0):
    """Rounded-square solid from [(z, half_width), ...], bottom to top."""
    return loft([rrect_ring(w, w, w * r_ratio, z, nc, m, sag) for z, w in profile])


def smooth(profile, per_seg=3):
    """Catmull-Rom resample of a profile so lofted curves shade without facets."""
    pts = [profile[0], *profile, profile[-1]]
    out = []
    for i in range(1, len(pts) - 2):
        for k in range(per_seg):
            t = k / per_seg
            out.append(tuple(0.5 * (2 * b + (c - a) * t + (2 * a - 5 * b + 4 * c - d) * t * t
                                    + (3 * b - a - 3 * c + d) * t ** 3)
                             for a, b, c, d in zip(*pts[i - 1:i + 3])))
    out.append(profile[-1])
    return out


def resample(profile, k, bend=0.03):
    """k points along the smoothed profile, spaced by arc length plus `bend` meters per radian
    of turning, so a low-poly loft spends its edge loops where the curve bends."""
    pts = [Vector(p) for p in smooth(profile, 8)]
    turn = [0.0] * len(pts)
    for j in range(1, len(pts) - 1):
        a, b = pts[j] - pts[j - 1], pts[j + 1] - pts[j]
        if a.length > 1e-9 and b.length > 1e-9:
            turn[j] = a.angle(b)
    cum = [0.0]
    for j in range(1, len(pts)):
        cum.append(cum[-1] + (pts[j] - pts[j - 1]).length + bend * (turn[j - 1] + turn[j]) / 2)
    out = []
    for q in range(k):
        target = cum[-1] * q / (k - 1)
        j = next(i for i in range(1, len(cum)) if cum[i] >= target - 1e-12)
        f = (target - cum[j - 1]) / max(cum[j] - cum[j - 1], 1e-12)
        out.append(tuple(pts[j - 1].lerp(pts[j], f)))
    return out


def lathe(profile, n=24):
    """Round solid from [(radius, z), ...]; a zero radius at either end becomes a pole."""
    bm = bmesh.new()
    pts = list(profile)
    bottom = bm.verts.new((0, 0, pts.pop(0)[1])) if pts[0][0] == 0 else None
    top = bm.verts.new((0, 0, pts.pop()[1])) if pts[-1][0] == 0 else None
    rings = [[bm.verts.new((r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), z))
              for i in range(n)] for r, z in pts]
    for lo, hi in zip(rings, rings[1:]):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    for i in range(n):
        j = (i + 1) % n
        if bottom:
            bm.faces.new((bottom, rings[0][j], rings[0][i]))
        if top:
            bm.faces.new((rings[-1][i], rings[-1][j], top))
    return bm


def boxes(specs):
    """One mesh made of axis-aligned boxes: [((cx, cy, cz), (sx, sy, sz)), ...]."""
    bm = bmesh.new()
    for c, s in specs:
        bmesh.ops.create_cube(bm, size=1.0, matrix=Matrix.LocRotScale(Vector(c), None, Vector(s)))
    return bm


def roof(h_eave, h_top, z_eave, height, r_eave, r_top, lift, push, p, n=9, nc=3, m=6):
    """Hip roof with a concave profile and upturned, flared corners (飞檐翘角)."""
    rings = []
    for k in range(n):
        t = k / (n - 1)
        h = h_eave + (h_top - h_eave) * t
        w = (1 - t) ** 2  # the corner flare fades out toward the ridge
        ring = []
        for x, y, z in rrect_ring(h, h, r_eave + (r_top - r_eave) * t, z_eave + height * t ** p, nc, m):
            c = (min(abs(x), abs(y)) / h) ** 3  # 0 mid-side, ~1 at the corners
            s = 1 + push * w * c
            ring.append((x * s, y * s, z + lift * w * c))
        rings.append(ring)
    return loft(rings, cap_bottom=False)


# ---------------------------------------------------------------- low-poly helpers (quads only)

def band(bm, rings, cyclic=False):
    """Quad strips between consecutive rings of equal length; returns the ring verts."""
    vr = [[bm.verts.new(p) for p in ring] for ring in rings]
    n = len(vr[0])
    for lo, hi in list(zip(vr, vr[1:])) + ([(vr[-1], vr[0])] if cyclic else []):
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    return vr


def grid_cap(bm, ring, first, dome=0.0, flip=False):
    """Close a counter-clockwise ring of 4n verts with an n x n Coons grid of quads.

    `first` is the ring index of one patch corner; the other three follow every n verts.
    `dome` lifts the interior into a shallow dome for round tops; `flip` faces the cap down.
    """
    k = len(ring)
    n = k // 4
    at = lambda i: ring[(first + i) % k]
    B = [at(2 * n + i) for i in range(n + 1)]
    T = [at(n - i) for i in range(n + 1)]
    L = [at(2 * n - j) for j in range(n + 1)]
    R = [at(3 * n + j) for j in range(n + 1)]
    c00, c10, c01, c11 = B[0].co, B[n].co, T[0].co, T[n].co
    mid = sum((v.co for v in ring), Vector()) / k
    rad2 = max((v.co - mid).xy.length_squared for v in ring)
    V = [[None] * (n + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        V[i][0], V[i][n] = B[i], T[i]
        V[0][i], V[n][i] = L[i], R[i]
    for i in range(1, n):
        for j in range(1, n):
            s, t = i / n, j / n
            co = ((1 - t) * B[i].co + t * T[i].co + (1 - s) * L[j].co + s * R[j].co
                  - (1 - s) * (1 - t) * c00 - s * (1 - t) * c10 - (1 - s) * t * c01 - s * t * c11)
            co.z += dome * (1 - (co - mid).xy.length_squared / rad2)
            V[i][j] = bm.verts.new(co)
    for i in range(n):
        for j in range(n):
            quad = (V[i][j], V[i + 1][j], V[i + 1][j + 1], V[i][j + 1])
            bm.faces.new(quad[::-1] if flip else quad)


def pane_faces(bm, specs):
    """Thin boxes from boxes()-style specs, keeping only the two broad faces
    (the edges of a glass pane sit inside the frame)."""
    X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))
    for c, (sx, sy, sz) in specs:
        if sx < sy:  # thin along X
            u, v, w, a, b, t = Y, Z, X, sy / 2, sz / 2, sx / 2
        else:        # thin along Y
            u, v, w, a, b, t = Z, X, Y, sz / 2, sx / 2, sy / 2
        for side in (1, -1):
            o = Vector(c) + w * t * side
            quad = [bm.verts.new(o + u * a * i + v * b * j) for i, j in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
            bm.faces.new(quad if side > 0 else quad[::-1])


def roof_shell(h_eave, h_top, z_eave, height, r_eave, r_top, lift, push, p, thick, nc, m,
               ts=(0.1, 0.22, 0.36, 0.5, 0.64, 0.78, 0.9, 1.0), under=(0.85, 0.4), rim=(0.008, 0.006),
               arcs=(2, 2), open_top=False):
    """Closed all-quad roof: underside, rounded eave edge and top surface in one ring loop.

    Same surface as roof(); the thickness and the rounded eave edges are modelled
    instead of coming from Solidify + Bevel. `arcs` gives the segments on the eave's
    top and bottom edge (1 = chamfer, 0 = plain corner). `open_top` leaves out the fold
    that closes the top opening; with very few rings that fold throws outlines through
    the roof, and the finial / upper roof covers the opening anyway.
    """
    def surf(t):
        h = h_eave + (h_top - h_eave) * t
        w = (1 - t) ** 2
        ring = []
        for x, y, z in rrect_ring(h, h, r_eave + (r_top - r_eave) * t, z_eave + height * t ** p, nc, m):
            c = (min(abs(x), abs(y)) / h) ** 3
            s = 1 + push * w * c
            ring.append(Vector((x * s, y * s, z + lift * w * c)))
        return ring

    def frame(t, dt=1e-3):
        """Surface points at t with outward normals and down-slope directions."""
        P, lo, hi = surf(t), surf(max(t - dt, 0.0)), surf(min(t + dt, 1.0))
        k = len(P)
        N = [(P[(i + 1) % k] - P[i - 1]).cross(hi[i] - lo[i]).normalized() for i in range(k)]
        D = [(lo[i] - hi[i]).normalized() for i in range(k)]
        return P, N, D

    rings = []
    for t in under:  # thinner toward the top so the inset hips never fold over
        P, N, _ = frame(t)
        rings.append([P[i] - N[i] * thick * (1 - 0.7 * t) for i in range(len(P))])
    E, N, D = frame(0.0)
    (r1, r2), (k1, k2) = rim, arcs
    r1, r2 = (r1 if k1 else 0.0), (r2 if k2 else 0.0)
    idx = range(len(E))
    for q in range(k2 + 1):  # bottom edge of the eave, from the underside round to the rim
        a = math.radians(90 * (1 - q / k2)) if k2 else 0.0
        s, c = math.sin(a), math.cos(a)
        rings.append([E[i] - D[i] * r2 - N[i] * (thick - r2) + (D[i] * c - N[i] * s) * r2 for i in idx])
    for q in range(k1 + 1):  # top edge of the eave, from the rim round onto the top surface
        a = math.radians(90 * (1 - q / k1)) if k1 else 0.0
        s, c = math.sin(a), math.cos(a)
        rings.append([E[i] - D[i] * r1 - N[i] * r1 + (D[i] * s + N[i] * c) * r1 for i in idx])
    rings += [surf(t) for t in ts]
    bm = bmesh.new()
    band(bm, rings, cyclic=not open_top)
    return bm


# ---------------------------------------------------------------- scene

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.context.preferences.filepaths.save_version = 0  # no .blend1 backups on rebuild
scene = bpy.context.scene
COL = bpy.data.collections.new(NAME)
scene.collection.children.link(COL)
ROOT = bpy.data.objects.new(NAME, None)
ROOT.empty_display_type = 'PLAIN_AXES'
ROOT.empty_display_size = 0.25
COL.objects.link(ROOT)
PARTS = []


def material(name, rgb):
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*rgb, 1.0)
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    if bsdf:
        bsdf.inputs['Base Color'].default_value = (*rgb, 1.0)
        bsdf.inputs['Roughness'].default_value = 0.6
    return mat


def add_part(name, bm, mat, bevel=None, solidify=None, weighted=False):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    me.materials.append(mat)
    ob = bpy.data.objects.new(name, me)
    COL.objects.link(ob)
    ob.parent = ROOT
    if solidify:
        md = ob.modifiers.new('Thickness', 'SOLIDIFY')
        md.thickness = solidify
        md.offset = -1.0
        md.use_even_offset = True
        md.use_quality_normals = True
        md.thickness_clamp = 1.0  # thins the eave at the upturned tips instead of spiking there
        md.use_thickness_angle_clamp = True
    if bevel:
        md = ob.modifiers.new('Bevel', 'BEVEL')
        md.width, md.segments = bevel
        md.limit_method = 'ANGLE'
        md.angle_limit = math.radians(30)
        md.miter_outer = 'MITER_ARC'
        md.use_clamp_overlap = True
        md.harden_normals = True
    if weighted:  # big flat faces keep their own normal, the rounded strips take the curvature
        me.set_sharp_from_angle(angle=math.radians(60))  # only real folds, e.g. the roof's hidden top opening
        md = ob.modifiers.new('WeightedNormal', 'WEIGHTED_NORMAL')
        md.mode = 'FACE_AREA'
        md.weight = 50
        md.keep_sharp = True
    PARTS.append(ob)
    return ob


M_STONE = material('M_Stone', CLAY)  # base and post (beige in the reference)
M_WOOD = material('M_Wood', CLAY)    # frame, roofs, finial (brown)
M_GLASS = material('M_Glass', CLAY)  # 琉璃 panels (pale green)

# Shared dimensions: 灯框 frame (Z1 stays under the lower roof so the rails can't poke through),
# 琉璃 glass panes, and the post / base / finial profiles.
B, HALF, Z0, Z1 = 0.034, 0.16, 0.732, 1.20
C = HALF - B / 2
G, GT, GW, GZ0, GZ1 = C + 0.002, 0.006, 0.26, Z0 + 0.03, Z1 - 0.03
PANES = []
for _s in (1, -1):
    PANES.append(((0, _s * G, (GZ0 + GZ1) / 2), (GW, GT, GZ1 - GZ0)))
    PANES.append(((_s * G, 0, (GZ0 + GZ1) / 2), (GT, GW, GZ1 - GZ0)))
BASE_UPPER = [(0.085, 0.163), (0.1, 0.163), (0.115, 0.158), (0.13, 0.145), (0.15, 0.131), (0.175, 0.12),
              (0.2, 0.114)]
POST = [(0.215, 0.111), (0.28, 0.108), (0.35, 0.101), (0.42, 0.094), (0.49, 0.087), (0.55, 0.081),
        (0.6, 0.079), (0.63, 0.084), (0.655, 0.094), (0.672, 0.1), (0.695, 0.1)]
FINIAL = [(0.03, 1.455), (0.034, 1.465), (0.03, 1.475), (0.021, 1.482), (0.019, 1.492), (0.026, 1.505),
          (0.031, 1.525), (0.03, 1.545), (0.024, 1.562), (0.014, 1.574)]
ROOF_LOWER = (0.22, 0.105, 1.19, 0.14, 0.04, 0.012, 0.06, 0.08, 1.6)
ROOF_UPPER = (0.17, 0.025, 1.30, 0.17, 0.032, 0.01, 0.05, 0.08, 1.4)


def build_high():
    # 底座: wide slab with pinched sides, then a skirt that flows up into the post
    add_part('Base_Lower', loft([rrect_ring(0.19, 0.19, 0.065, 0.0, 5, 8, 0.02),
                                 rrect_ring(0.183, 0.183, 0.06, 0.09, 5, 8, 0.02)]), M_STONE, bevel=(0.022, 4))
    add_part('Base_Upper', profile_loft(smooth(BASE_UPPER + [(0.225, 0.111)]), 0.3, 5, 6, 0.01),
             M_STONE, bevel=(0.01, 3))
    # 灯柱: thick post tapering upward, with a short flare that carries the tray
    add_part('Post', profile_loft(smooth(POST), 0.3, 5, 2), M_STONE, bevel=(0.006, 2))
    # 灯座 tray, 灯框 frame and 琉璃 glass
    add_part('Tray', loft([rrect_ring(0.176, 0.176, 0.022, z, 3) for z in (0.687, 0.732)]), M_WOOD,
             bevel=(0.009, 3))
    bars = [((sx * C, sy * C, (Z0 + Z1) / 2), (B, B, Z1 - Z0)) for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1))]
    for zc in (Z0 + 0.016, Z1 - 0.016):
        for s in (1, -1):
            bars.append(((0, s * C, zc), (2 * C, 0.028, 0.032)))
            bars.append(((s * C, 0, zc), (0.028, 2 * C, 0.032)))
    add_part('Frame', boxes(bars), M_WOOD, bevel=(0.005, 2))
    add_part('Glass', boxes(PANES), M_GLASS, bevel=(0.0015, 1))
    # 重檐: double-eave roof (the upper eave sits straight on the lower one) and the 宝顶 finial
    add_part('Roof_Lower', roof(*ROOF_LOWER), M_WOOD, bevel=(0.008, 2), solidify=0.03)
    add_part('Roof_Upper', roof(*ROOF_UPPER), M_WOOD, bevel=(0.007, 2), solidify=0.028)
    add_part('Finial', lathe([(0, 1.455), *FINIAL, (0, 1.58)]), M_WOOD)


def build_low():
    """About 3000 faces, all quads. Faces that can never be seen (the underside, part
    ends buried in a neighbouring part, the tops under the finial) are left out."""
    def base_ring(d, z):  # the base footprint at height z, inset by d
        f = z / 0.09
        h, r = 0.19 - 0.007 * f, 0.065 - 0.005 * f
        return rrect_ring(h - d, h - d, max(r - d, 0.005), z, 4, 4, 0.02)

    rings = [base_ring(0.02 * (1 - math.sin(math.radians(a))), 0.02 * (1 - math.cos(math.radians(a))))
             for a in (0, 45, 90)]  # rounded bottom edge
    rings += [base_ring(0.022 * (1 - math.cos(math.radians(a))), 0.068 + 0.022 * math.sin(math.radians(a)))
              for a in (0, 22.5, 45, 67.5, 90)]  # wall top, then the soft rounded top edge
    rings.append(base_ring(0.035, 0.09))  # inner edge hides under Base_Upper
    bm = bmesh.new()
    # the underside is never seen, but closing it keeps the inverted-hull outline unbroken along the ground
    grid_cap(bm, band(bm, rings)[0], 2, flip=True)
    add_part('Base_Lower', bm, M_STONE, weighted=True)

    bm = bmesh.new()  # top tucks inside the post
    band(bm, [rrect_ring(w, w, 0.3 * w, z, 4, 2, 0.01) for z, w in resample(BASE_UPPER + [(0.228, 0.106)], 12)])
    add_part('Base_Upper', bm, M_STONE, weighted=True)

    bm = bmesh.new()  # bottom starts inside Base_Upper, top ends inside the tray
    band(bm, [rrect_ring(w, w, 0.3 * w, z, 4, 1) for z, w in resample([(0.19, 0.113)] + POST, 14)])
    add_part('Post', bm, M_STONE, weighted=True)

    def tray_ring(d, z):
        return rrect_ring(0.176 - d, 0.176 - d, max(0.022 - d, 0.004), z, 4, 1)

    rings = [tray_ring(0.081, 0.687)]  # underside ring, its hole covered by the post
    rings += [tray_ring(0.009 * (1 - math.sin(math.radians(a))), 0.687 + 0.009 * (1 - math.cos(math.radians(a))))
              for a in (0, 45, 90)]
    rings += [tray_ring(0.009 * (1 - math.cos(math.radians(a))), 0.723 + 0.009 * math.sin(math.radians(a)))
              for a in (0, 45, 90)]
    bm = bmesh.new()
    grid_cap(bm, band(bm, rings)[-1], 2)  # the top shows through the glass, so it is closed
    add_part('Tray', bm, M_WOOD, weighted=True)

    bm = bmesh.new()
    X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))

    def bar(a, b, u, v, hu, hv):  # rounded-rectangle tube; its ends sit inside other parts
        sec = rrect_ring(hu, hv, 0.006, 0.0, 3)
        band(bm, [[p + u * x + v * y for x, y, _ in sec] for p in (Vector(a), Vector(b))])

    for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        bar((sx * C, sy * C, Z0 - 0.005), (sx * C, sy * C, Z1), X, Y, B / 2, B / 2)
    for zc in (Z0 + 0.016, Z1 - 0.016):
        for s in (1, -1):
            bar((-C, s * C, zc), (C, s * C, zc), Y, Z, 0.014, 0.016)
            bar((s * C, -C, zc), (s * C, C, zc), Z, X, 0.016, 0.014)
    add_part('Frame', bm, M_WOOD, weighted=True)
    add_part('Glass', boxes(PANES), M_GLASS, weighted=True)

    add_part('Roof_Lower', roof_shell(*ROOF_LOWER, 0.03, 3, 7), M_WOOD, weighted=True)
    add_part('Roof_Upper', roof_shell(*ROOF_UPPER, 0.028, 3, 6), M_WOOD, weighted=True)

    n = 16  # the bottom sits inside the upper roof; the top closes with a domed quad grid
    bm = bmesh.new()
    vr = band(bm, [[(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), z) for i in range(n)]
                   for r, z in FINIAL])
    grid_cap(bm, vr[-1], 2, dome=0.006)
    add_part('Finial', bm, M_WOOD, weighted=True)


def build_500():
    """About 500 faces, all quads. Every visible edge keeps at least a chamfer, which weighted
    normals shade like a rounded edge; only edges against never-seen undersides stay plain.
    The base skirt and the post become one loft, the frame's top rails (fully under the
    roof) are dropped, and the roofs stay open at the top under the finial / upper roof."""
    def base_ring(d, z):
        f = z / 0.09
        h, r = 0.19 - 0.007 * f, 0.065 - 0.005 * f
        return rrect_ring(h - d, h - d, max(r - d, 0.005), z, 2, 1, 0.02)

    rings = [base_ring(0, 0)] + [base_ring(0.022 * (1 - math.cos(math.radians(a))),
                                           0.068 + 0.022 * math.sin(math.radians(a))) for a in (0, 45, 90)]
    bm = bmesh.new()  # the rounding's inner edge hides under the skirt; the bottom stays closed for the outline
    grid_cap(bm, band(bm, rings)[0], 1, flip=True)
    add_part('Base_Lower', bm, M_STONE, weighted=True)

    bm = bmesh.new()  # skirt + post: starts inside Base_Lower, ends inside the tray
    band(bm, [rrect_ring(w, w, 0.3 * w, z, 2) for z, w in ((0.085, 0.163), (0.108, 0.16), (0.145, 0.132),
                                                            (0.215, 0.111), (0.58, 0.08), (0.645, 0.089),
                                                            (0.695, 0.1))])
    add_part('Post', bm, M_STONE, weighted=True)

    def tray_ring(d, z):
        return rrect_ring(0.176 - d, 0.176 - d, max(0.022 - d, 0.004), z, 2)

    bm = bmesh.new()
    vr = band(bm, [tray_ring(0.08, 0.687), tray_ring(0, 0.687), tray_ring(0, 0.724), tray_ring(0.008, 0.732)])
    grid_cap(bm, vr[-1], 1)
    add_part('Tray', bm, M_WOOD, weighted=True)

    bm = bmesh.new()
    X, Y, Z = Vector((1, 0, 0)), Vector((0, 1, 0)), Vector((0, 0, 1))

    def bar(a, b, u, v, hu, hv):  # chamfered-rectangle tube; its ends sit inside other parts
        sec = rrect_ring(hu, hv, 0.006, 0.0, 1)
        band(bm, [[p + u * x + v * y for x, y, _ in sec] for p in (Vector(a), Vector(b))])

    for sx, sy in ((1, 1), (-1, 1), (-1, -1), (1, -1)):
        bar((sx * C, sy * C, Z0 - 0.005), (sx * C, sy * C, Z1), X, Y, B / 2, B / 2)
    for s in (1, -1):
        bar((-C, s * C, Z0 + 0.016), (C, s * C, Z0 + 0.016), Y, Z, 0.014, 0.016)
        bar((s * C, -C, Z0 + 0.016), (s * C, C, Z0 + 0.016), Z, X, 0.016, 0.014)
    add_part('Frame', bm, M_WOOD, weighted=True)
    bm = bmesh.new()
    pane_faces(bm, PANES)
    add_part('Glass', bm, M_GLASS, weighted=True)

    eave = dict(under=(0.5,), arcs=(1, 0), open_top=True)  # chamfered top edge, plain underside edge
    # the lower roof's upper half hides under the upper roof, so its rings go to the upper roof's curve
    add_part('Roof_Lower', roof_shell(*ROOF_LOWER, 0.03, 1, 2, ts=(0.35, 1.0), **eave), M_WOOD, weighted=True)
    add_part('Roof_Upper', roof_shell(*ROOF_UPPER, 0.028, 1, 2, ts=(0.3, 0.55, 0.78, 1.0), **eave), M_WOOD,
             weighted=True)

    n = 8  # the collar overhangs the roof so the seam with the chamfered hips stays out of sight
    bm = bmesh.new()
    vr = band(bm, [[(r * math.cos(2 * math.pi * i / n), r * math.sin(2 * math.pi * i / n), z) for i in range(n)]
                   for r, z in ((0.024, 1.45), (0.036, 1.468), (0.03, 1.48), (0.018, 1.492), (0.031, 1.528),
                                (0.026, 1.556), (0.013, 1.574))])
    grid_cap(bm, vr[-1], 1, dome=0.006)
    add_part('Finial', bm, M_WOOD, weighted=True)


{'high': build_high, 'low': build_low, '500': build_500}[VARIANT]()

# ---------------------------------------------------------------- stats

dg = bpy.context.evaluated_depsgraph_get()
total_faces = total_quads = total_tris = 0
zmin, zmax = 1e9, -1e9
part_stats = {}
for ob in PARTS:
    ev = ob.evaluated_get(dg)
    me = ev.to_mesh()
    faces = len(me.polygons)
    quads = sum(len(p.vertices) == 4 for p in me.polygons)
    tris = sum(len(p.vertices) - 2 for p in me.polygons)
    zs = [v.co.z for v in me.vertices]
    zmin, zmax = min(zmin, *zs), max(zmax, *zs)
    ev.to_mesh_clear()
    total_faces, total_quads, total_tris = total_faces + faces, total_quads + quads, total_tris + tris
    part_stats[ob.name] = {'faces': faces, 'quads': quads, 'tris': tris}
    log(f'{ob.name:<11} {faces:>5} faces ({faces - quads} not quads) {tris:>6} tris')
log(f'TOTAL {total_faces} faces ({total_faces - total_quads} not quads), {total_tris} tris, '
    f'height {zmax - zmin:.3f} m')
os.makedirs(os.path.join(OUT, 'renders'), exist_ok=True)
with open(os.path.join(OUT, 'renders', f'stats{TAG}.json'), 'w') as f:
    json.dump({'faces': total_faces, 'quads': total_quads, 'tris': total_tris, 'height': round(zmax - zmin, 3),
               'parts': part_stats}, f, indent=1)

# ---------------------------------------------------------------- camera, save, export

cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera'))
cam.data.type = 'ORTHO'
cam.data.ortho_scale = 1.9
scene.collection.objects.link(cam)
scene.camera = cam
target = Vector((0, 0, 0.8))
az, el = math.radians(45), math.radians(27)  # corner-on, from above, matching the reference drawing
cam.location = target + 8 * Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
cam.rotation_euler = (target - cam.location).to_track_quat('-Z', 'Y').to_euler()

scene.render.resolution_x, scene.render.resolution_y = 1000, 1400
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
    ob.select_set(ob in PARTS or ob == ROOT)
bpy.context.view_layer.objects.active = ROOT
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, NAME + '.fbx'), use_selection=True,
                         object_types={'EMPTY', 'MESH'}, apply_scale_options='FBX_SCALE_ALL',
                         axis_forward='-Z', axis_up='Y', bake_space_transform=True, use_mesh_modifiers=True,
                         mesh_smooth_type='OFF', add_leaf_bones=False, bake_anim=False)
log('exported ' + NAME + '.fbx')

# ---------------------------------------------------------------- preview renders

def render(name):
    scene.render.filepath = os.path.join(OUT, 'renders', name)
    bpy.ops.render.render(write_still=True)
    log('rendered renders/' + name)


def baked_copy(ob, suffix, mat):
    """Copy of `ob` with its modifiers applied, for overlays that must follow the final shape."""
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
    me.materials.clear()
    me.materials.append(mat)
    copy = bpy.data.objects.new(ob.name + suffix, me)
    copy.matrix_world = ob.matrix_world
    scene.collection.objects.link(copy)
    return copy


def srgb(hex_color):
    c = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


if RENDER:
    render(f'whitemodel{TAG}.png')

if RENDER and not QUICK:
    # 布线: the final topology drawn over the clay
    dg = bpy.context.evaluated_depsgraph_get()
    m_wire = material('M_Wire', (0.1, 0.1, 0.12))
    wires = []
    for ob in PARTS:
        w = baked_copy(ob, '_wire', m_wire)
        md = w.modifiers.new('Wire', 'WIREFRAME')
        md.thickness = 0.0016
        md.use_replace = True
        md.use_even_offset = True
        wires.append(w)
    setup_workbench('MATERIAL')
    render(f'whitemodel_wire{TAG}.png')
    for w in wires:
        bpy.data.objects.remove(w)

    # 三渲二 preview: two-tone ramp against a fixed light, plus inverted-hull outlines
    light = Vector((-0.3, -0.8, 0.52)).normalized()  # from the camera's upper left, as in the reference

    def toon(mat, lit, shade, alpha=1.0):
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
        ramp.color_ramp.elements[1].position = 0.01  # > 0 so the clamped negative side stays in shadow
        ramp.color_ramp.elements[1].color = (*srgb(lit), 1)
        emit = nt.nodes.new('ShaderNodeEmission')
        nt.links.new(geo.outputs['Normal'], dot.inputs[0])
        nt.links.new(dot.outputs['Value'], ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], emit.inputs['Color'])
        surface = emit.outputs[0]
        if alpha < 1:
            mix = nt.nodes.new('ShaderNodeMixShader')
            mix.inputs['Fac'].default_value = 1 - alpha
            nt.links.new(surface, mix.inputs[1])
            nt.links.new(nt.nodes.new('ShaderNodeBsdfTransparent').outputs[0], mix.inputs[2])
            surface = mix.outputs[0]
        nt.links.new(surface, out.inputs['Surface'])

    toon(M_STONE, '#f0dcb2', '#d6b484')
    toon(M_WOOD, '#9b634a', '#6e4130')
    toon(M_GLASS, '#d3eadf', '#a9cfc0', alpha=0.6)

    m_line = bpy.data.materials.new('M_Outline')
    m_line.use_backface_culling = True
    nt = m_line.node_tree
    nt.nodes.clear()
    emit = nt.nodes.new('ShaderNodeEmission')
    emit.inputs['Color'].default_value = (*srgb('#4a2e22'), 1)
    geo = nt.nodes.new('ShaderNodeNewGeometry')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(geo.outputs['Backfacing'], mix.inputs['Fac'])
    nt.links.new(emit.outputs[0], mix.inputs[1])
    nt.links.new(nt.nodes.new('ShaderNodeBsdfTransparent').outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], nt.nodes.new('ShaderNodeOutputMaterial').inputs['Surface'])

    dg = bpy.context.evaluated_depsgraph_get()
    hulls = []
    for ob in PARTS:
        if ob.name == 'Glass':
            continue
        hull = baked_copy(ob, '_outline', m_line)
        hulls.append(hull)
        bm = bmesh.new()
        bm.from_mesh(hull.data)
        bm.normal_update()
        for v in bm.verts:
            v.co += v.normal * 0.008
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        bm.to_mesh(hull.data)
        bm.free()

    try:
        scene.render.engine = 'CYCLES'
        scene.cycles.device = 'CPU'
        scene.cycles.samples = 32
        scene.cycles.use_denoising = False
        scene.cycles.filter_width = 1.0
    except TypeError:
        scene.render.engine = 'BLENDER_EEVEE'
    log('toon engine: ' + scene.render.engine)
    render(f'toon{TAG}.png')

if RENDER and not QUICK and WATERCOLOR:
    # 水彩 passes for watercolor.py: wash colours, ink lines, light/shadow, material ids, normals
    def surface(mat, make):
        """Rebuild `mat` as the single shader output returned by make(node_tree)."""
        nt = mat.node_tree
        nt.nodes.clear()
        nt.links.new(make(nt), nt.nodes.new('ShaderNodeOutputMaterial').inputs['Surface'])

    def emission(rgb):
        def make(nt):
            e = nt.nodes.new('ShaderNodeEmission')
            e.inputs['Color'].default_value = (*rgb, 1)
            return e.outputs[0]
        return make

    def camera_normal(nt):  # stored as 0.5 + 0.5 * n
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        vt = nt.nodes.new('ShaderNodeVectorTransform')
        vt.vector_type, vt.convert_from, vt.convert_to = 'NORMAL', 'WORLD', 'CAMERA'
        ma = nt.nodes.new('ShaderNodeVectorMath')
        ma.operation = 'MULTIPLY_ADD'
        ma.inputs[1].default_value = ma.inputs[2].default_value = (0.5, 0.5, 0.5)
        e = nt.nodes.new('ShaderNodeEmission')
        nt.links.new(geo.outputs['Normal'], vt.inputs['Vector'])
        nt.links.new(vt.outputs['Vector'], ma.inputs[0])
        nt.links.new(ma.outputs['Vector'], e.inputs['Color'])
        return e.outputs[0]

    def holdout(nt):
        return nt.nodes.new('ShaderNodeHoldout').outputs[0]

    def clear(nt):
        return nt.nodes.new('ShaderNodeBsdfTransparent').outputs[0]

    mats = (M_STONE, M_WOOD, M_GLASS)
    for h in hulls:
        h.hide_render = True
    render(f'passes/wc_fill{TAG}.png')  # toon colours without outlines
    if scene.render.engine == 'CYCLES':
        scene.cycles.samples = 16
    for mat, rgb in zip(mats, ((1, 0, 0), (0, 1, 0), (0, 0, 1))):
        surface(mat, emission(rgb))
    render(f'passes/wc_ids{TAG}.png')  # one colour channel per material
    for mat in mats:
        toon(mat, '#ffffff', '#000000')
    render(f'passes/wc_lit{TAG}.png')  # white on the lit side, black on the shadow side
    for mat in mats:
        surface(mat, camera_normal)
    render(f'passes/wc_normal{TAG}.png')
    for h in hulls:
        h.hide_render = False
    surface(M_STONE, holdout)
    surface(M_WOOD, holdout)
    surface(M_GLASS, holdout)
    render(f'passes/wc_lines{TAG}.png')  # alpha = ink lines in front of the glass
    surface(M_GLASS, clear)
    render(f'passes/wc_lines_all{TAG}.png')  # ... and also those seen through it
