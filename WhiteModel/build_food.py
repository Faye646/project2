"""The opening dishes, ingredients and seasonings as 3D white models for 三渲二:
dishes 胡饼 (D01), 菜面 (D02), 馄饨 (D03); ingredients 面粉 (flour), 时蔬 (greens), 猪肉 (pork);
seasonings 盐 (salt), 油 (oil), 葱 (scallion), 姜 (ginger). Ids match the design data.

Built procedurally from the art in 新建文件夹/ (胡饼.png, 面粉.png, …) in the style of the
纹璃宫灯 low model: turned parts are lathed with rounded rims, food is made of soft low-poly shapes,
and Weighted Normals keep the flat faces flat. Each dish is its own FBX, pivot at the centre of the
base, real size (a bowl is ~16 cm across), and stays within the 500-face budget for small props.

Run with Blender 5.2:
    blender -b --factory-startup --python build_food.py -- <out_dir> [--no-render]
Writes SM_<id>.blend + .fbx, palette_food.json and renders/ (clay + toon preview) to <out_dir>.
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
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Food')
RENDER = '--no-render' not in ARGS
CLAY = (0.8, 0.8, 0.8)

# toon lit / shade (sRGB), picked from the dish art; merged into the Unity palette
PALETTE = {
    'Celadon':    ('#bcd5c1', '#93b39e'),   # 青瓷 bowl and plate
    'Broth':      ('#ecd997', '#cdb66c'),
    'Noodle':     ('#f7eed6', '#dfcfa3'),
    'Greens':     ('#a6cf73', '#77a24a'),
    'Scallion':   ('#7fb54e', '#5a8a33'),
    'Bread':      ('#f0d49a', '#d2a764'),
    'Char':       ('#c07a3a', '#95562a'),
    'WontonSkin': ('#f6ecd3', '#dccaa0'),
    'Meat':       ('#e3aaa0', '#c3847a'),
    # ingredients and seasonings
    'Burlap':     ('#e6d2a6', '#c5aa7b'),   # 面粉 sack
    'Flour':      ('#fbf7ee', '#e3dccd'),
    'LightWood':  ('#e2b37c', '#bf8a52'),   # scoops, spoons
    'Stem':       ('#eef0d2', '#cdd3a4'),   # pale stalks of the greens
    'Fat':        ('#f7e2d8', '#dcbcae'),
    'Salt':       ('#fdfbf6', '#e4e0d6'),
    'Jar':        ('#efe9d4', '#cfc6a8'),   # the cream salt jar
    'Clay':       ('#e4ab5d', '#c0843b'),   # oil jug
    'Oil':        ('#f5c93f', '#d9a520'),
    'ScallionWhite': ('#f6f4e6', '#d9d6bf'),
    'Twine':      ('#dcc07a', '#b89a55'),
    'Ginger':     ('#e6c48c', '#c49b5f'),
    'GingerFlesh': ('#f7e49c', '#dcc36c'),
}


def log(msg):
    print(f'[dishes] {msg}', flush=True)


def new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0


MATS = {}


def material(name):
    mat = bpy.data.materials.get('M_' + name) or bpy.data.materials.new('M_' + name)
    mat.diffuse_color = (*CLAY, 1.0)
    return mat


class Part:
    """One dish = one mesh; geometry is added piece by piece, each piece with its material."""

    def __init__(self):
        self.bm = bmesh.new()
        self.mats = []

    def _mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def _commit(self, tmp, mat, edges=(), r=0.0, seg=2):
        if edges and r > 1e-5:
            bmesh.ops.bevel(tmp, geom=list(edges), offset=r, offset_type='OFFSET', segments=seg, profile=0.5,
                            affect='EDGES', clamp_overlap=True)
        mi = self._mi(mat)
        vmap = {v: self.bm.verts.new(v.co) for v in tmp.verts}
        for f in tmp.faces:
            self.bm.faces.new([vmap[v] for v in f.verts]).material_index = mi
        tmp.free()

    def lathe(self, profile, mat, n=16, M=Matrix(), close_ends=True, deform=None):
        """Surface of revolution about Z; profile [(r, z)] in order. A ring of radius 0 becomes a single
        point (a fan), so closed shapes like flatbreads need no caps."""
        tmp = bmesh.new()
        rings = []
        for rad, z in profile:
            if rad < 1e-6:
                rings.append([tmp.verts.new(M @ Vector((0, 0, z)))])
            else:
                pts = [Vector((rad * math.cos(2 * math.pi * k / n), rad * math.sin(2 * math.pi * k / n), z)) for k in range(n)]
                rings.append([tmp.verts.new(M @ (deform(q) if deform else q)) for q in pts])
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
        if close_ends:
            if len(rings[0]) > 1:
                tmp.faces.new(list(reversed(rings[0])))
            if len(rings[-1]) > 1:
                tmp.faces.new(rings[-1])
        self._commit(tmp, mat)

    def blob(self, c, r, mat, squash=(1, 1, 1), segs=(8, 5), rot=0.0, deform=None):
        """Low-poly ellipsoid; `deform(v_local) -> v_local` shapes it before it is placed."""
        tmp = bmesh.new()
        bmesh.ops.create_uvsphere(tmp, u_segments=segs[0], v_segments=segs[1], radius=1.0)
        for v in tmp.verts:
            p = Vector((v.co.x * r * squash[0], v.co.y * r * squash[1], v.co.z * r * squash[2]))
            if deform:
                p = deform(p)
            v.co = Matrix.Translation(Vector(c)) @ Matrix.Rotation(rot, 4, 'Z') @ p
        self._commit(tmp, mat)

    def tube(self, pts, radius, mat, sides=5):
        """A soft tube along a polyline (noodles), with rounded ends."""
        tmp = bmesh.new()
        rings = []
        for i, p in enumerate(pts):
            p = Vector(p)
            t = (Vector(pts[min(i + 1, len(pts) - 1)]) - Vector(pts[max(i - 1, 0)])).normalized()
            a = t.cross(Vector((0, 0, 1)))
            if a.length < 1e-4:
                a = Vector((1, 0, 0))
            a.normalize()
            b = t.cross(a)
            rings.append([tmp.verts.new(p + radius * (math.cos(2 * math.pi * k / sides) * a + math.sin(2 * math.pi * k / sides) * b))
                          for k in range(sides)])
        for ra, rb in zip(rings, rings[1:]):
            for k in range(sides):
                tmp.faces.new((ra[k], ra[(k + 1) % sides], rb[(k + 1) % sides], rb[k]))
        tmp.faces.new(list(reversed(rings[0])))
        tmp.faces.new(rings[-1])
        self._commit(tmp, mat)

    def finish(self, name, col):
        bm = self.bm
        bm.normal_update()
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.shade_smooth()
        me.set_sharp_from_angle(angle=math.radians(70))
        for m in self.mats:
            me.materials.append(material(m))
        ob = bpy.data.objects.new(name, me)
        col.objects.link(ob)
        md = ob.modifiers.new('WeightedNormal', 'WEIGHTED_NORMAL')
        md.mode = 'FACE_AREA'
        md.weight = 50
        md.keep_sharp = True
        return ob


# ---------------------------------------------------------------- vessels

def bowl(p, rim_r=0.08, h=0.07, foot_r=0.035, broth_z=0.055, n=14):
    """青瓷碗 with a foot ring and a rolled rim; the inside ends at the broth, which caps it."""
    prof = [(foot_r * 0.8, 0.0), (foot_r, 0.0), (foot_r * 1.08, 0.011),
            (rim_r * 0.72, h * 0.45), (rim_r * 0.94, h * 0.87), (rim_r, h), (rim_r - 0.004, h + 0.003),
            (rim_r - 0.008, h), (rim_r * 0.84, broth_z)]
    p.lathe(prof, 'Celadon', n=n, close_ends=False)
    p.lathe([(foot_r * 0.8, 0.0), (0, 0.004)], 'Celadon', n=n, close_ends=False)   # underside
    p.lathe([(rim_r * 0.84, broth_z), (0, broth_z + 0.001)], 'Broth', n=n, close_ends=False)
    return broth_z


def plate(p, r=0.1, h=0.022, n=12):
    prof = [(0, 0.0), (r * 0.55, 0.0), (r * 0.6, 0.004), (r * 0.9, h * 0.8), (r, h), (r - 0.004, h + 0.002),
            (r - 0.008, h), (r * 0.62, 0.008), (0, 0.008)]
    p.lathe(prof, 'Celadon', n=n, close_ends=False)


# ---------------------------------------------------------------- dishes
# Each dish also has a 锅中 variant (wok=True): the food without its bowl or plate, shown in the
# wok while it cooks; soups keep a round pool of broth.

def in_wok_broth(p, r=0.075, z=0.008):
    p.lathe([(r, 0.0), (r, z), (0, z + 0.001)], 'Broth', n=14, close_ends=False)
    return z


def hubing(col, wok=False):
    """胡饼: three baked flatbreads on a shallow celadon plate, browned spots on top."""
    p = Part()
    if not wok:
        plate(p)
    rnd = random.Random(1)
    for (x, y, z, r, tilt) in ((-0.028, 0.025, 0.012, 0.052, 0.0), (0.03, 0.028, 0.013, 0.05, 0.0),
                               (0.004, -0.028, 0.03, 0.052, 0.12)):
        th = 0.018
        prof = [(0, 0), (r * 0.7, 0), (r * 0.95, th * 0.2), (r, th * 0.55), (r * 0.95, th * 0.9),
                (r * 0.7, th * 1.12), (0, th * 1.2)]
        M = Matrix.Translation((x, y, z)) @ Matrix.Rotation(tilt, 4, 'X')
        p.lathe(prof, 'Bread', n=12, M=M)
        for k in range(4):   # 焦斑 as low bumps on the top
            a = rnd.uniform(0, 2 * math.pi)
            d = rnd.uniform(0.1, 0.6) * r
            q = M @ Vector((d * math.cos(a), d * math.sin(a), th * 1.12 - (d / r) ** 2 * th * 0.3))
            p.blob(q, rnd.uniform(0.008, 0.012), 'Char', squash=(1, 0.8, 0.25), segs=(5, 3), rot=a)
    return p.finish('SM_D01' + ('_wok' if wok else ''), col)


def caimian(col, wok=False):
    """菜面: noodles in broth with greens and chopped scallion, in a celadon bowl."""
    p = Part()
    bz = in_wok_broth(p) if wok else bowl(p)
    rnd = random.Random(2)
    for k in range(5):   # loops of noodle lying in the broth
        a0 = rnd.uniform(0, 2 * math.pi)
        rad = rnd.uniform(0.018, 0.05)
        pts = []
        for j in range(7):
            a = a0 + j * 0.55
            rr = rad + 0.008 * math.sin(j * 1.3 + k)
            pts.append((rr * math.cos(a), rr * math.sin(a), bz + 0.004 + 0.003 * math.sin(j * 0.9 + k)))
        p.tube(pts, 0.005, 'Noodle', sides=4)
    for (x, y, a) in ((-0.03, 0.012, 0.4), (0.022, -0.018, 2.2), (0.012, 0.032, 1.2)):   # greens
        p.blob((x, y, bz + 0.007), 0.024, 'Greens', squash=(1.2, 0.55, 0.14), segs=(6, 3), rot=a,
               deform=lambda v: Vector((v.x, v.y, v.z + 0.004 * math.sin(v.x * 180))))
    for k in range(7):   # scallion bits
        a = rnd.uniform(0, 2 * math.pi)
        d = rnd.uniform(0.005, 0.05)
        p.blob((d * math.cos(a), d * math.sin(a), bz + 0.009), 0.0045, 'Scallion', squash=(1, 1, 0.7), segs=(4, 3))
    return p.finish('SM_D02' + ('_wok' if wok else ''), col)


def huntun(col, wok=False):
    """馄饨: six wontons with ruffled skirts floating in broth, scallion rings."""
    p = Part()
    bz = in_wok_broth(p) if wok else bowl(p)
    rnd = random.Random(3)
    spots = [(0.0, 0.004)] + [(0.037 * math.cos(a), 0.037 * math.sin(a)) for a in (0.5, 2.0, 3.6, 5.1)]
    for i, (x, y) in enumerate(spots):
        rot = rnd.uniform(0, math.pi)

        def skirt(v, ph=rnd.uniform(0, 6)):
            ang = math.atan2(v.y, v.x)
            return Vector((v.x * (1 + 0.25 * math.cos(3 * ang + ph)), v.y * (1 + 0.25 * math.cos(3 * ang + ph)),
                           v.z + 0.003 * math.cos(3 * ang + ph)))
        p.blob((x, y, bz + 0.004), 0.022, 'WontonSkin', squash=(1, 0.9, 0.16), segs=(7, 3), rot=rot, deform=skirt)
        p.blob((x, y, bz + 0.011), 0.013, 'WontonSkin', squash=(1.05, 0.9, 0.85), segs=(6, 4), rot=rot)   # the filled pouch
        p.blob((x, y + 0.001, bz + 0.016), 0.008, 'Meat', squash=(1, 0.9, 0.6), segs=(4, 3), rot=rot)
    for k in range(5):   # scallion rings
        a = rnd.uniform(0, 2 * math.pi)
        d = rnd.uniform(0.018, 0.058)
        p.blob((d * math.cos(a), d * math.sin(a), bz + 0.003), 0.005, 'Scallion', squash=(1, 1, 0.35), segs=(5, 3))
    return p.finish('SM_D03' + ('_wok' if wok else ''), col)


# ---------------------------------------------------------------- ingredients and seasonings

def flour(col):
    """面粉: an open burlap sack with a rolled rim, a heap of flour and a wooden scoop."""
    p = Part()

    def folds(v):
        k = 1 + 0.05 * math.cos(3 * math.atan2(v.y, v.x)) * math.sin(v.z * 22)
        return Vector((v.x * k, v.y * k, v.z))
    p.lathe([(0.0, 0.0), (0.12, 0.0), (0.155, 0.04), (0.165, 0.12), (0.15, 0.2), (0.132, 0.235), (0.158, 0.25),
             (0.162, 0.272), (0.14, 0.286), (0.12, 0.27), (0.116, 0.235)], 'Burlap', n=12, deform=folds, close_ends=False)
    p.lathe([(0.117, 0.236), (0.08, 0.262), (0.0, 0.282)], 'Flour', n=12, close_ends=False)
    p.tube([(0.03, 0.02, 0.27), (0.07, 0.05, 0.33), (0.1, 0.07, 0.38)], 0.012, 'LightWood', sides=6)
    p.blob((0.02, 0.012, 0.268), 0.036, 'LightWood', squash=(1.25, 0.95, 0.45), segs=(8, 4), rot=0.6)
    return p.finish('SM_flour', col)


def greens(col):
    """时蔬: a bunch of crinkled leafy greens lying on its side, pale stalks gathered at one end."""
    p = Part()
    base = Vector((0.09, -0.06, 0.012))
    for k, ang in enumerate((-0.55, -0.25, 0.05, 0.35, 0.62)):
        d = Vector((-math.cos(ang), math.sin(ang) + 0.6, 0)).normalized()
        tip = base + d * 0.17
        mid = base + d * 0.09
        p.tube([base, base + d * 0.05 + Vector((0, 0, 0.01)), mid + Vector((0, 0, 0.018))], 0.011, 'Stem', sides=5)

        def wav(v, ph=k):
            return Vector((v.x, v.y, v.z + 0.008 * math.sin(v.x * 70 + ph) + 0.006 * math.sin(v.y * 90)))
        p.blob(tip * 0.55 + mid * 0.45 + Vector((0, 0, 0.022 + 0.006 * (k % 2))), 0.075, 'Greens',
               squash=(1.45, 0.72, 0.16), segs=(8, 4), rot=math.atan2(d.y, d.x), deform=wav)
    return p.finish('SM_greens', col)


def pork(col):
    """猪肉: a marbled chunk of pork and one thick slice on a celadon plate."""
    p = Part()
    plate(p)
    p.blob((-0.012, 0.01, 0.034), 0.06, 'Meat', squash=(1.2, 0.9, 0.62), segs=(10, 5), rot=0.3,
           deform=lambda v: Vector((v.x, v.y, max(v.z, -0.018))))
    p.blob((-0.012, 0.01, 0.052), 0.058, 'Fat', squash=(1.1, 0.8, 0.28), segs=(8, 4), rot=0.3)   # fat cap
    p.blob((0.055, -0.03, 0.02), 0.034, 'Meat', squash=(1.2, 0.75, 0.3), segs=(8, 4), rot=-0.4)  # the slice
    p.blob((0.055, -0.03, 0.026), 0.03, 'Fat', squash=(1.25, 0.6, 0.15), segs=(6, 3), rot=-0.4)
    return p.finish('SM_pork', col)


def salt(col):
    """盐: a round cream glazed jar full of coarse salt, a wooden spoon standing in it."""
    p = Part()
    p.lathe([(0.0, 0.0), (0.045, 0.0), (0.056, 0.006), (0.072, 0.04), (0.07, 0.066), (0.056, 0.082),
             (0.058, 0.09), (0.052, 0.093), (0.049, 0.084)], 'Jar', n=14, close_ends=False)
    p.lathe([(0.05, 0.082), (0.03, 0.097), (0.0, 0.103)], 'Salt', n=14, close_ends=False)
    p.tube([(0.012, 0.004, 0.096), (0.04, 0.022, 0.13), (0.07, 0.04, 0.165)], 0.0075, 'LightWood', sides=6)
    p.blob((0.004, 0.0, 0.097), 0.02, 'LightWood', squash=(1.3, 1.0, 0.4), segs=(8, 4), rot=0.55)
    return p.finish('SM_salt', col)


def oil(col):
    """油: a round clay jug with a pouring lip and a loop handle, oil showing at the mouth."""
    p = Part()
    p.lathe([(0.0, 0.0), (0.04, 0.0), (0.05, 0.006), (0.07, 0.045), (0.066, 0.08), (0.042, 0.105), (0.033, 0.12),
             (0.038, 0.136), (0.034, 0.142), (0.029, 0.132)], 'Clay', n=14, close_ends=False)
    p.lathe([(0.029, 0.128), (0.0, 0.129)], 'Oil', n=14, close_ends=False)
    p.blob((-0.036, 0.0, 0.137), 0.018, 'Clay', squash=(1.3, 0.75, 0.35), segs=(6, 3))        # pouring lip
    p.tube([(0.03, 0.0, 0.125), (0.07, 0.0, 0.122), (0.086, 0.0, 0.095), (0.078, 0.0, 0.065), (0.06, 0.0, 0.05)],
           0.008, 'Clay', sides=6)                                                               # handle
    return p.finish('SM_oil', col)


def scallion(col):
    """葱: four spring onions tied with twine; white bulbs at one end, green leaves at the other."""
    p = Part()
    rot = Matrix.Rotation(0.5, 4, 'Z')
    for k in range(4):
        off = Vector((0, (k - 1.5) * 0.017, 0.012 + 0.006 * (k % 2)))

        def pt(x, z=0.0, off=off):
            return rot @ (Vector((x, 0, z)) + off)
        p.blob(pt(0.1), 0.016, 'ScallionWhite', squash=(1.8, 1, 1), segs=(6, 4))              # bulb
        p.tube([pt(0.1), pt(0.04), pt(-0.02)], 0.009, 'ScallionWhite', sides=5)
        p.tube([pt(-0.02), pt(-0.09, 0.004), pt(-0.16, 0.012 * (k % 2))], 0.009, 'Scallion', sides=5)
        p.blob(pt(-0.19, 0.01), 0.03, 'Scallion', squash=(1.4, 0.35, 0.3), segs=(6, 3))        # leaf tips
    band = Matrix.Translation((0.0, 0.0, 0.016)) @ rot @ Matrix.Rotation(math.pi / 2, 4, 'Y') \
        @ Matrix.Diagonal((0.45, 1.0, 1.0, 1.0))
    p.lathe([(0.042, -0.006), (0.044, 0.0), (0.042, 0.006)], 'Twine', n=10, close_ends=False, M=band)
    return p.finish('SM_scallion', col)


def ginger(col):
    """姜: a knobbly ginger root with two slices beside it."""
    p = Part()
    p.blob((0.0, 0.0, 0.024), 0.05, 'Ginger', squash=(1.7, 0.72, 0.55), segs=(10, 5), rot=0.25)
    for (x, y, z, r, a) in ((-0.075, 0.02, 0.03, 0.024, 0.9), (0.075, -0.012, 0.028, 0.026, -0.3),
                            (0.02, 0.04, 0.042, 0.02, 1.4), (-0.03, -0.035, 0.036, 0.018, -1.2)):
        p.blob((x, y, z), r, 'Ginger', squash=(1.4, 1, 0.9), segs=(6, 4), rot=a)                # knobs
    for (x, y, a) in ((0.05, -0.065, 0.3), (0.085, -0.05, 0.6)):
        M = Matrix.Translation((x, y, 0.012)) @ Matrix.Rotation(a, 4, 'Z') @ Matrix.Rotation(0.5, 4, 'X') \
            @ Matrix.Diagonal((1.25, 0.85, 1.0, 1.0))
        p.lathe([(0.0, 0.0), (0.024, 0.0), (0.026, 0.004), (0.024, 0.008), (0.0, 0.008)], 'GingerFlesh', n=10,
                M=M, close_ends=False)
    return p.finish('SM_ginger', col)


# ---------------------------------------------------------------- build, export, preview

def setup_camera(scene, target_h, extent=0.2):
    cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera'))
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = extent * 1.25
    scene.collection.objects.link(cam)
    scene.camera = cam
    az, el = math.radians(20), math.radians(32)   # front, a little from the left, like the dish art
    view = Vector((math.sin(az) * math.cos(el), -math.cos(az) * math.cos(el), math.sin(el)))
    t = Vector((0, 0, target_h))
    cam.location = t + 2 * view
    cam.rotation_euler = (-view).to_track_quat('-Z', 'Y').to_euler()
    scene.render.resolution_x = scene.render.resolution_y = 700
    scene.render.film_transparent = True
    scene.view_settings.view_transform = 'Standard'


def srgb(hex_color):
    c = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


def toon_preview(scene, ob, path):
    light = Vector((-0.3, -0.8, 0.52)).normalized()
    for mat in ob.data.materials:
        key = mat.name[2:]
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
    line = bpy.data.materials.new('M_Outline')
    line.use_backface_culling = True
    nt = line.node_tree
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
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
    me.materials.clear()
    me.materials.append(line)
    hull = bpy.data.objects.new(ob.name + '_outline', me)
    scene.collection.objects.link(hull)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bm.normal_update()
    for v in bm.verts:
        v.co += v.normal * 0.0012
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 16
    scene.cycles.use_denoising = False
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


stats = {}
os.makedirs(os.path.join(OUT, 'renders'), exist_ok=True)
for key, build in (('D01', hubing), ('D02', caimian), ('D03', huntun),
                   ('D01_wok', lambda c: hubing(c, True)), ('D02_wok', lambda c: caimian(c, True)),
                   ('D03_wok', lambda c: huntun(c, True)), ('flour', flour), ('greens', greens),
                   ('pork', pork), ('salt', salt), ('oil', oil), ('scallion', scallion), ('ginger', ginger)):
    new_scene()
    scene = bpy.context.scene
    col = bpy.data.collections.new('SM_' + key)
    scene.collection.children.link(col)
    ob = build(col)
    dg = bpy.context.evaluated_depsgraph_get()
    me = ob.evaluated_get(dg).to_mesh()
    faces, tris = len(me.polygons), sum(len(pl.vertices) - 2 for pl in me.polygons)
    zmax = max(v.co.z for v in me.vertices)
    extent = max(max(v.co.x for v in me.vertices) - min(v.co.x for v in me.vertices),
                 max(v.co.y for v in me.vertices) - min(v.co.y for v in me.vertices), zmax)
    ob.evaluated_get(dg).to_mesh_clear()
    stats[key] = {'faces': faces, 'tris': tris}
    log(f'SM_{key}: {faces} faces, {tris} tris')
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, f'SM_{key}.blend'))
    for o in bpy.data.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, f'SM_{key}.fbx'), use_selection=True, object_types={'MESH'},
                             apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y',
                             bake_space_transform=False, use_mesh_modifiers=True, mesh_smooth_type='OFF',
                             add_leaf_bones=False, bake_anim=False)
    if RENDER:
        setup_camera(scene, zmax * 0.45, extent)
        scene.render.engine = 'BLENDER_WORKBENCH'
        sh = scene.display.shading
        sh.light, sh.color_type, sh.single_color = 'STUDIO', 'SINGLE', CLAY
        sh.show_cavity, sh.show_object_outline = True, True
        scene.render.filepath = os.path.join(OUT, 'renders', f'{key}_whitemodel.png')
        bpy.ops.render.render(write_still=True)
        toon_preview(scene, ob, os.path.join(OUT, 'renders', f'{key}_toon.png'))
with open(os.path.join(OUT, 'palette_food.json'), 'w', encoding='utf-8') as fh:
    json.dump({'toon': {k: {'lit': v[0], 'shade': v[1], 'emission': 0.0} for k, v in PALETTE.items()}}, fh, indent=1)
with open(os.path.join(OUT, 'renders', 'stats.json'), 'w') as fh:
    json.dump(stats, fh, indent=1)
log('done')
