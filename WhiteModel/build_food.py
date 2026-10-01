"""Dishes, ingredients and seasonings as 3D white models for 三渲二: the opening dishes 胡饼 (D01),
菜面 (D02), 馄饨 (D03), and every ingredient and seasoning in the design data except the six wines.
The opening seven come first (面粉 flour, 时蔬 greens, 猪肉 pork, 盐 salt, 油 oil, 葱 scallion,
姜 ginger), then the meat, poultry, tofu and fish on plates, the sacks, parcels, pots and baskets, and
the vegetables, seasoning vessels and drinks. `wine` is a generic celadon ewer (酒_待定.png) until each
wine gets its own. Ids match the design data.

Built procedurally from the art in 新建文件夹/ (胡饼.png, 面粉.png, …) in the style of the
纹璃宫灯 low model: turned parts are lathed with rounded rims, food is made of soft low-poly shapes,
and Weighted Normals keep the flat faces flat. Each dish is its own FBX, pivot at the centre of the
base, real size (a bowl is ~16 cm across), and stays within the 500-face budget for small props.
Unity culls back faces, so lathe profiles run up the outside and down the inside, and every opening is
closed at its fill height: no inside face may show past the contents.

Run with Blender 5.2:
    blender -b --factory-startup --python build_food.py -- <out_dir> [--no-render] [--only id1,id2]
Writes SM_<id>.blend + .fbx, palette_food.json and renders/ (clay + toon preview) to <out_dir>;
--only builds just those ids.
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
ONLY = set(ARGS[ARGS.index('--only') + 1].split(',')) if '--only' in ARGS else None
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
    # plated meat, poultry, tofu and fish
    'ChickenMeat': ('#f8c0a6', '#e39a84'),   # raw breast and its cubes
    'WingSkin':   ('#fbd8c2', '#eab196'),
    'WingCut':    ('#e98a7e', '#c8665d'),   # pink meat at the cut joints
    'DuckSkin':   ('#fce4c4', '#efbd97'),
    'DuckBill':   ('#eeb25c', '#cc8a38'),
    'KidneyRed':  ('#bb4a4d', '#923338'),
    'TofuWhite':  ('#fcf0d6', '#e6cba4'),
    'PorkSkin':   ('#fad5ba', '#efb999'),
    'FishBack':   ('#a39d94', '#7e7870'),   # grey back of the carp and the big fish head
    'FishBelly':  ('#f6ead2', '#dccaa8'),
    'FishFin':    ('#eeb28f', '#cf8f6d'),
    'FishIris':   ('#f3dc98', '#d6b86c'),
    'FishEye':    ('#3d322b', '#2b231e'),   # pupils of fish, crab and duck
    'FishGill':   ('#ec9a8c', '#cc786d'),   # gills, mouths and the cut face of the fish head
    'MandarinSkin': ('#cdb46f', '#a68d4c'),
    'MandarinSpot': ('#76683f', '#594d2f'),
    'MandarinFin': ('#e9c47f', '#cba05e'),
    'CrabShell':  ('#8fa0a8', '#6b7c86'),
    'CrabBelly':  ('#efc690', '#cfa067'),   # underside and claw tips
    # sacks, parcels, pots and baskets
    'RiceGrain':  ('#fdf5e1', '#e9d3ab'),
    'Wicker':     ('#efc685', '#c8955a'),   # woven bamboo baskets and trays
    'WickerBind': ('#f7e6bd', '#d8c191'),   # the pale wraps round their rims
    'WickerBindGreen': ('#c5c27c', '#9c9a52'),   # green wraps of the rice basket
    'BundleCloth': ('#ece8d0', '#c8c2a0'),   # the sage-tinted cloth of the rice bundle
    'WrapPaper':  ('#f0d3a3', '#cfa572'),   # kraft paper of the parcels
    'Pickle':     ('#f5df8c', '#d5b552'),   # salted pickle shreds and 酸菜, with their dark leaves
    'PickleLeaf': ('#adab52', '#828034'),
    'Scallop':    ('#f9bb5c', '#e3973a'),   # dried scallops: fibrous sides, pale cut top
    'ScallopTop': ('#fde391', '#efc466'),
    'Shrimp':     ('#fa9c66', '#e26e42'),
    'StarchBag':  ('#fae09b', '#e4b866'),
    'CornCob':    ('#fcc54c', '#e9a02e'),
    'ClayPot':    ('#dc9a68', '#b6704b'),
    'Pancake':    ('#fcefcf', '#ead09d'),
    'EggShell':   ('#fde4cd', '#efbf9c'),
    # vegetables, seasoning vessels and drinks
    'RadishWhite': ('#f7efdd', '#dcc9a6'),
    'RadishFlesh': ('#fcf8ee', '#e6dcc6'),  # cut faces of the slices
    'RadishTop':  ('#e3df9c', '#bfbd68'),   # green shoulder and leaf stalks
    'RadishLeaf': ('#8db158', '#62863a'),
    'CucumberGreen': ('#6f8f41', '#4f6a2d'),
    'CucumberFlesh': ('#f4efc0', '#dcd38f'),
    'CucumberSeed': ('#e6dc8e', '#ccc06a'),
    'CalyxGreen': ('#99a346', '#6f7a2d'),   # tomato calyx, chilli and cucumber stalks, bamboo tips
    'BambooHusk': ('#d59b5f', '#a86b3a'),
    'BambooFlesh': ('#f9e6ae', '#e3c47c'),
    'PerillaPurple': ('#a85a7c', '#7d3b58'),
    'PerillaDeep': ('#8a4466', '#632f4a'),  # the darker leaves of the bunch
    'PerillaGreen': ('#a3b065', '#7a8642'),
    'ShiitakeCap': ('#b06a3e', '#86492a'),
    'ShiitakeFlesh': ('#f6dfba', '#dcb98a'),  # gills, stem and the cross cut
    'TomatoRed':  ('#f1532f', '#c9301c'),
    'TomatoFlesh': ('#f8925c', '#e06c3e'),
    'TomatoSeed': ('#f8c45e', '#e0a040'),
    'ChiliRed':   ('#e5392a', '#b3221c'),
    'PotatoSkin': ('#e8b563', '#c4893f'),
    'PotatoFlesh': ('#faeaa6', '#e6cd78'),
    'PotatoEye':  ('#9e6532', '#764720'),
    'GarlicSkin': ('#f8eedf', '#dcc3b6'),
    'GarlicClove': ('#f9ecc8', '#e3cc97'),
    'GarlicPeel': ('#ebc4ad', '#c99782'),
    'GarlicStreak': ('#c99aa6', '#a57a86'),  # purple lines down the bulb
    'SugarWhite': ('#fbf1df', '#e6d2ae'),
    'RockSugar':  ('#f6c979', '#dca452'),
    'VinegarGlaze': ('#7d4129', '#552a19'),
    'VinegarDark': ('#6f2b13', '#4c1a0a'),
    'JugStopper': ('#b5714a', '#8a5233'),
    'RiceWine':   ('#efe2ab', '#d5c483'),
    'ColaDark':   ('#7a3018', '#541d0c'),
    'LabelRed':   ('#e0453a', '#b52e25'),   # cola label and bottle cap
    'BottleGlass': ('#e0e8d4', '#b5c5ae'),
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

    def box(self, c, size, mat, r=0.0, rot=0.0, M=Matrix(), seg=2):
        """Box of full size (x, y, z) centred on c, turned `rot` about Z, then moved by M; edges rounded by r."""
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1.0)
        T = M @ Matrix.Translation(Vector(c)) @ Matrix.Rotation(rot, 4, 'Z') @ Matrix.Diagonal((*size, 1.0))
        for v in tmp.verts:
            v.co = T @ v.co
        self._commit(tmp, mat, edges=tmp.edges[:], r=min(r, 0.45 * min(size)), seg=seg)

    def tube(self, pts, radius, mat, sides=5):
        """A soft tube along a polyline (noodles), with rounded ends. Its rings are oriented from the
        tangent × Z, so a path that turns vertical or doubles back sideways twists inside out: split it."""
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


def plate(p, r=0.1, h=0.022, n=12, sx=1.0):
    """青瓷盘; sx > 1 stretches it into the oval plate that whole fish and poultry lie on."""
    prof = [(0, 0.0), (r * 0.55, 0.0), (r * 0.6, 0.004), (r * 0.9, h * 0.8), (r, h), (r - 0.004, h + 0.002),
            (r - 0.008, h), (r * 0.62, 0.008), (0, 0.008)]
    p.lathe(prof, 'Celadon', n=n, close_ends=False, M=Matrix.Diagonal((sx, 1.0, 1.0, 1.0)))


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


# ---------------------------------------------------------------- plated meat, poultry, tofu and fish

def moved(p, n0, M):
    """Moves what was added to p since it had n0 vertices by M: a fish is built upright, then laid down."""
    p.bm.verts.ensure_lookup_table()
    for v in p.bm.verts[n0:]:
        v.co = M @ v.co


def fin(p, outline, mat, thick=0.002, M=Matrix()):
    """A thin fin or tail in the XZ plane: a lens through the outline [(x, z)], which goes anticlockwise
    round the origin as seen from the front, puffed out by `thick` in the middle; then placed by M."""
    n = len(outline)
    p.lathe([(0, -thick), (1, 0), (0, thick)], mat, n=n, M=M @ Matrix.Rotation(math.pi / 2, 4, 'X'),
            deform=lambda q: Vector((*outline[round(math.atan2(q.y, q.x) / (2 * math.pi) * n) % n], 0.0)))


def fish_body(p, stations, back, belly, split=2.1, nb=9, nl=5):
    """A fish body along X, snout first, from stations [(x, top, bottom, half_width)]. Two lathes share the
    sections with their rings spread over complementary arcs, so the dark back meets the pale belly along the
    near flank, `split` radians round from the top."""
    st = {round(x, 5): (top, bot, hw) for x, top, bot, hw in stations}

    def section(q, n, a0, a1):
        top, bot, hw = st[round(q.z, 5)]
        a = a0 + (a1 - a0) * (round(math.atan2(q.y, q.x) / (2 * math.pi) * n) % n) / (n - 1)
        return Vector((q.z, -hw * math.sin(a), (top + bot) / 2 + (top - bot) / 2 * math.cos(a)))
    prof = [(1.0, x) for x, *_ in stations]
    p.lathe(prof, back, n=nb, deform=lambda q: section(q, nb, -split, split))
    p.lathe(prof, belly, n=nl, deform=lambda q: section(q, nl, split, 2 * math.pi - split))


def flank(stations, x, a):
    """Point on a fish body at x, `a` radians round the section from the top towards the camera, and its normal."""
    for (x0, t0, b0, w0), (x1, t1, b1, w1) in zip(stations, stations[1:]):
        if x0 <= x <= x1:
            f = (x - x0) / (x1 - x0)
            top, bot, hw = t0 + (t1 - t0) * f, b0 + (b1 - b0) * f, w0 + (w1 - w0) * f
            break
    h = (top - bot) / 2
    return (Vector((x, -hw * math.sin(a), (top + bot) / 2 + h * math.cos(a))),
            Vector((0.0, -math.sin(a) / hw, math.cos(a) / h)).normalized())


def patch(p, stations, x, a, r, mat, squash=(1, 1, 0.35), segs=(6, 3), rot=0.0, lift=0.0, wobble=0.0):
    """A flattened blob lying on the fish body at (x, a): an eye, a blotch, the gills; `wobble` makes it lobed."""
    c, nrm = flank(stations, x, a)
    R = nrm.to_track_quat('Z', 'Y').to_matrix() @ Matrix.Rotation(rot, 3, 'Z')
    p.blob(c + nrm * lift, r, mat, squash=squash, segs=segs,
           deform=lambda v: R @ (v * (1 + wobble * math.sin(3 * math.atan2(v.y, v.x)))))


def fish_eye(p, stations, x, a, r):
    """A round eye on the flank: a pale ring round a dark pupil."""
    patch(p, stations, x, a, r, 'FishIris', squash=(1, 1, 0.45), segs=(8, 3))
    patch(p, stations, x, a, r * 0.58, 'FishEye', squash=(1, 1, 0.45), segs=(6, 3), lift=r * 0.3)


def low_fins(p, stations, mat, xs):
    """Pelvic and anal fins under the belly at xs, swept back and splayed towards the camera."""
    for x in xs:
        c, nrm = flank(stations, x, 2.6)
        fin(p, [(0.026, -0.003), (0.004, 0.004), (-0.004, 0.0), (0.002, -0.005), (0.02, -0.013)], mat,
            M=Matrix.Translation(c) @ Matrix.Rotation(-1.2, 4, 'X'))


def folded_sheet(p, M, length, depth, h=0.009, t=0.0035, wave=0.006, droop=0.0, ph=0.0):
    """A sheet of skin folded over on itself, the fold towards -Y: a C-section band lathed along X that thins to an
    edge at both ends, where the fold stays open and the pink inside shows; wavy, with rounded corners, the fold
    sagging by `droop`; placed by M."""
    yc = -depth + h                      # the fold goes round (yc, 0)
    arc = [math.radians(90 + 45 * i) for i in range(5)]
    mid = ([(depth, h), ((depth + yc) / 2, h)] + [(yc + h * math.cos(f), h * math.sin(f)) for f in arc]
           + [(depth, -h)])              # middle of the band; the top layer has a middle row so that it can sag
    out = [(0, 1), (0, 1)] + [(math.cos(f), math.sin(f)) for f in arc] + [(0, -1)]
    n = 2 * len(mid)

    def section(k, x):   # point k round the band: out along the outer face, back along the inner one
        i, side = (k, 1) if k < n // 2 else (n - 1 - k, -1)
        d = side * t / 2 * (1 - (2 * x / length) ** 8)
        return mid[i][0] + out[i][0] * d, mid[i][1] + out[i][1] * d

    def place(x, y, z):   # wavy open edge, corners rounded off, the fold sagging; waves along and across
        e = (2 * x / length) ** 2
        y = yc + (y - yc) * (1 + 0.12 * math.sin(x / length * 9 + ph)) * (1 - 0.3 * e) + 0.005 * e
        z += wave * (math.sin(x / length * 2 * math.pi + ph) + 0.4 * math.sin(y / depth * 4.7 + ph))
        return Vector((x, y, z - droop * ((depth - y) / (2 * depth)) ** 2))
    xs = [length * (i / 4 - 0.5) for i in range(5)]
    p.lathe([(1, x) for x in xs], 'PorkSkin', n=n, M=M, close_ends=False,
            deform=lambda q: place(q.z, *section(round(math.atan2(q.y, q.x) / (2 * math.pi) * n) % n, q.z)))
    ri = h - t / 2
    p.lathe([(1, x * 0.99) for x in xs], 'Meat', n=6, M=M,
            deform=lambda q: place(q.z, (yc + 0.88 * depth) / 2 + (0.88 * depth - yc) / 2 * q.x, 0.8 * ri * q.y))


def chicken(col):
    """鸡肉: a raw chicken breast with two cubes cut from it on a celadon plate."""
    p = Part()
    plate(p, n=14)

    def teardrop(v):   # full and high at the +x end, narrowing to a low tip at -x, flat underneath
        k = 0.75 + 0.25 * v.x / 0.088
        return Vector((v.x, v.y * k, max(v.z * k, -0.017)))
    p.blob((-0.022, 0.012, 0.027), 0.08, 'ChickenMeat', squash=(1.1, 0.5, 0.5), segs=(12, 6), rot=0.95,
           deform=teardrop)
    p.blob((-0.012, -0.008, 0.02), 0.062, 'ChickenMeat', squash=(1.1, 0.3, 0.3), segs=(10, 4), rot=0.92,
           deform=teardrop)                                                                      # the tenderloin
    for (x, y, a) in ((0.03, -0.054, 0.35), (0.07, -0.026, -0.15)):
        p.box((x, y, 0.025), (0.034, 0.034, 0.032), 'ChickenMeat', r=0.005, rot=a)
    return p.finish('SM_chicken', col)


def duck(col):
    """鸭: a whole plucked duck breast-up on an oval celadon plate, drumsticks to the right, head and bill in front."""
    p = Part()
    plate(p, r=0.105, sx=1.55, n=14)
    p.blob((0.004, 0.008, 0.05), 0.082, 'DuckSkin', squash=(1.2, 0.82, 0.68), segs=(12, 6),
           deform=lambda v: Vector((v.x, v.y, max(v.z, -0.04))))                                  # body, breast up
    for (y, z, a) in ((-0.062, 0.042, 0.1), (0.07, 0.048, -0.1)):                                 # folded wings
        p.blob((-0.03, y, z), 0.044, 'DuckSkin', squash=(1.3, 0.32, 0.55), segs=(8, 4), rot=a)
    for (x, y, z, a) in ((0.066, -0.046, 0.05, -0.6), (0.078, 0.036, 0.056, -0.25)):            # thighs, drumsticks
        d = Vector((math.cos(a), math.sin(a), -0.3))
        c = Vector((x, y, z))
        p.blob(c, 0.034, 'DuckSkin', squash=(1.3, 0.85, 0.8), segs=(8, 4), rot=a)
        p.blob(c + d * 0.044, 0.023, 'DuckSkin', squash=(1.5, 0.7, 0.7), segs=(8, 4), rot=a)
        p.blob(c + d * 0.068, 0.013, 'DuckSkin', squash=(1, 1.2, 1), segs=(6, 3), rot=a)
    p.tube([(-0.09, -0.014, 0.054), (-0.106, -0.038, 0.035), (-0.11, -0.056, 0.025)], 0.0125, 'DuckSkin', sides=6)
    p.blob((-0.112, -0.064, 0.024), 0.02, 'DuckSkin', squash=(1.2, 0.95, 0.85), segs=(8, 4), rot=0.45)   # head
    p.blob((-0.135, -0.076, 0.02), 0.018, 'DuckBill', squash=(1.45, 0.72, 0.32), segs=(6, 3), rot=0.45)  # bill
    p.blob((-0.109, -0.082, 0.031), 0.0036, 'FishEye', segs=(4, 3))
    return p.finish('SM_duck', col)


def kidney(col):
    """猪腰子: two dark-red pork kidneys side by side on a celadon plate, pale fat in their notches."""
    p = Part()
    plate(p, n=14)

    def bean(v):   # bow the long axis and dent the hollow side in the middle
        t = v.x / 0.066
        dent = 0.014 * math.exp(-(t / 0.4) ** 2) if v.y > 0 else 0.0
        return Vector((v.x, v.y - 0.026 * (1 - t * t) - dent, max(v.z, -0.026)))
    for (x, y, a) in ((-0.03, 0.016, 1.13), (0.028, -0.014, 1.13)):
        R = Matrix.Rotation(a, 3, 'Z')
        p.blob((x, y, 0.036), 0.066, 'KidneyRed', squash=(1.0, 0.66, 0.48), segs=(12, 6), rot=a, deform=bean)
        p.blob(Vector((x, y, 0.05)) + R @ Vector((0.0, 0.004, 0.0)), 0.015, 'Fat', squash=(1.3, 0.85, 0.6),
               segs=(6, 4), rot=a)
    return p.finish('SM_kidney', col)


def wing(col):
    """鸡翅: three plump raw chicken wings on a celadon plate, pink meat showing where they are cut at the joint."""
    p = Part()
    plate(p, h=0.026, n=14)

    def body(v):   # widest at the cut joint (+x), cut off blunt there, tapering to a knuckle, bowed, flat underneath
        t = v.x / 0.05
        k = 0.8 + 0.2 * max(t, -0.7) + 0.1 * math.exp(-((t - 0.7) / 0.25) ** 2)
        return Vector((min(v.x, 0.04), v.y * k - 2.2 * v.x * v.x, max(v.z * k, -0.014)))
    for (x, y, z, a) in ((-0.04, 0.03, 0.028, -2.5), (0.046, 0.024, 0.028, -0.64), (0.0, -0.038, 0.036, -0.1)):
        R = Matrix.Rotation(a, 3, 'Z')
        c = Vector((x, y, z))
        p.blob(c, 0.046, 'WingSkin', squash=(1.08, 0.72, 0.46), segs=(10, 5), rot=a, deform=body)
        p.blob(c + R @ Vector((0.002, 0.03, -0.006)), 0.042, 'WingSkin', squash=(0.95, 0.5, 0.2), segs=(8, 3), rot=a,
               deform=lambda v: Vector((v.x, v.y - 2.2 * v.x * v.x, v.z)))                     # web of skin
        p.blob(c + R @ Vector((0.041, -0.003, 0.003)), 0.017, 'WingCut', squash=(0.35, 1.1, 0.95), segs=(6, 3), rot=a)
        p.blob(c + R @ Vector((-0.046, -0.004, -0.002)), 0.011, 'WingSkin', squash=(1.1, 1.1, 0.9), segs=(6, 3),
               rot=a)                                                                            # knuckle
    return p.finish('SM_wing', col)


def tofu(col):
    """豆腐: a block of tofu and two small cubes cut from it on a celadon plate."""
    p = Part()
    plate(p, n=14)
    p.box((-0.02, 0.018, 0.034), (0.1, 0.066, 0.052), 'TofuWhite', r=0.006, rot=0.1)
    for (x, y, a) in ((0.032, -0.05, 0.3), (0.07, -0.022, 0.15)):
        p.box((x, y, 0.024), (0.032, 0.032, 0.032), 'TofuWhite', r=0.004, rot=a)
    return p.finish('SM_tofu', col)


def skin(col):
    """猪肉皮: sheets of pork skin folded over and piled up on a celadon plate, pink showing in the folds."""
    p = Part()
    plate(p, h=0.026, n=12)
    for (x, y, z, a, tilt, length, depth, droop, ph) in ((0.0, 0.04, 0.024, 0.05, 0.2, 0.08, 0.022, 0.0, 0.0),
                                                        (-0.032, 0.0, 0.026, -1.7, -0.15, 0.085, 0.03, 0.0, 1.5),
                                                        (0.034, 0.0, 0.027, 1.45, -0.15, 0.085, 0.03, 0.0, 2.5),
                                                        (0.0, -0.01, 0.046, -1.5, 0.0, 0.1, 0.045, 0.016, 4.5)):
        M = Matrix.Translation((x, y, z)) @ Matrix.Rotation(a, 4, 'Z') @ Matrix.Rotation(tilt, 4, 'X')
        folded_sheet(p, M, length, depth, droop=droop, ph=ph)
    return p.finish('SM_skin', col)


CARP = [(-0.125, 0.038, 0.018, 0.01), (-0.116, 0.052, 0.01, 0.016), (-0.1, 0.064, 0.004, 0.019),
        (-0.072, 0.078, 0.0, 0.022), (-0.035, 0.086, 0.0, 0.023), (0.01, 0.084, 0.005, 0.02),
        (0.048, 0.072, 0.019, 0.014), (0.076, 0.06, 0.031, 0.008), (0.098, 0.054, 0.038, 0.006)]


def fish(col):
    """普通整鱼: a whole carp on an oval celadon plate, grey back, pale belly, forked tail."""
    p = Part()
    plate(p, r=0.105, sx=1.55, n=14)
    n0 = len(p.bm.verts)
    fish_body(p, CARP, 'FishBack', 'FishBelly')
    fin(p, [(0.036, 0.0), (0.07, 0.05), (0.035, 0.034), (0.005, 0.014), (-0.012, 0.0), (0.005, -0.014),
            (0.035, -0.032), (0.068, -0.046)], 'FishBack', M=Matrix.Translation((0.098, 0.0, 0.046)))    # tail
    ox, oz = 0.01, 0.07
    top = [(x - ox, flank(CARP, x, 0.0)[0].z + h - oz)
           for x, h in ((0.058, 0.002), (0.046, 0.008), (0.03, 0.01), (0.008, 0.012), (-0.014, 0.014), (-0.03, 0.017),
                        (-0.042, 0.003))]
    fin(p, top + [(-0.03, -0.01), (0.03, -0.01)], 'FishBack', M=Matrix.Translation((ox, 0.0, oz)))     # dorsal
    c, nrm = flank(CARP, -0.08, 2.1)
    fin(p, [(0.03, 0.0), (0.005, 0.006), (-0.004, 0.0), (0.004, -0.006), (0.03, -0.022), (0.042, -0.012)],
        'FishFin', M=Matrix.Translation(c) @ Matrix.Rotation(-0.3, 4, 'Z') @ Matrix.Rotation(-0.5, 4, 'X'))  # pectoral
    low_fins(p, CARP, 'FishFin', (-0.025, 0.05))
    fish_eye(p, CARP, -0.1, 0.9, 0.0078)
    p.blob((-0.126, 0.0, 0.026), 0.0085, 'FishFin', squash=(0.8, 1.1, 0.75), segs=(6, 3))           # lips
    gill = []
    for k in range(5):
        c, nrm = flank(CARP, -0.091 + 0.01 * math.sin(k / 4 * math.pi), 0.35 + 0.5 * k)
        gill.append(c + nrm * 0.0008)
    p.tube(gill, 0.0016, 'FishBack', sides=4)
    moved(p, n0, Matrix.Translation((0.004, 0.0, 0.01)) @ Matrix.Rotation(-0.35, 4, 'X'))
    return p.finish('SM_fish', col)


GUIYU = [(-0.126, 0.034, 0.01, 0.01), (-0.114, 0.05, 0.003, 0.016), (-0.094, 0.068, 0.0, 0.021),
         (-0.066, 0.083, 0.0, 0.024), (-0.03, 0.09, 0.0, 0.024), (0.006, 0.087, 0.005, 0.021),
         (0.042, 0.075, 0.017, 0.016), (0.07, 0.062, 0.029, 0.01), (0.092, 0.056, 0.036, 0.007)]


def mandarin_fish(col):
    """鳜鱼: a mandarin fish on an oval celadon plate: olive body with dark blotches, spiny dorsal fin, big mouth."""
    p = Part()
    plate(p, r=0.105, sx=1.55, n=12)
    n0 = len(p.bm.verts)
    fish_body(p, GUIYU, 'MandarinSkin', 'FishBelly', split=2.2, nb=8)
    fin(p, [(0.05, 0.0), (0.047, 0.024), (0.034, 0.042), (0.004, 0.016), (-0.012, 0.0), (0.004, -0.016),
            (0.034, -0.042), (0.047, -0.024)], 'MandarinSkin', M=Matrix.Translation((0.092, 0.0, 0.046)))  # round tail
    ox, oz = -0.004, 0.07
    top = [(x - ox, flank(GUIYU, x, 0.0)[0].z + h - oz)
           for x, h in ((0.064, 0.004), (0.054, 0.02), (0.04, 0.03), (0.022, 0.028), (0.004, 0.02), (-0.03, 0.022),
                        (-0.06, 0.018), (-0.074, 0.002))]
    fin(p, top + [(-0.04, -0.012), (0.04, -0.012)], 'MandarinFin', M=Matrix.Translation((ox, 0.0, oz)))  # dorsal
    for k in range(6):                                                                                # its spines
        x = -0.068 + 0.012 * k
        fin(p, [(0.005, -0.008), (0.007, 0.034 - 0.0025 * k), (-0.004, -0.008)], 'MandarinFin', thick=0.0015,
            M=Matrix.Translation((x, 0.0, flank(GUIYU, x, 0.0)[0].z + 0.004)))
    c, nrm = flank(GUIYU, -0.07, 1.9)
    fin(p, [(0.036, 0.0), (0.03, 0.016), (0.008, 0.01), (-0.005, 0.0), (0.006, -0.012), (0.026, -0.022)],
        'MandarinFin', M=Matrix.Translation(c) @ Matrix.Rotation(-0.3, 4, 'Z') @ Matrix.Rotation(-0.35, 4, 'X'))
    low_fins(p, GUIYU, 'MandarinFin', (-0.035, 0.045))
    rnd = random.Random(7)
    for (x, a) in ((-0.074, 0.6), (-0.052, 1.3), (-0.032, 0.45), (-0.012, 1.05), (0.01, 0.35), (0.026, 1.4),
                   (0.044, 0.8), (0.066, 1.2), (-0.055, 0.1), (0.05, 0.15)):
        patch(p, GUIYU, x, a, rnd.uniform(0.0055, 0.009), 'MandarinSpot', squash=(1.3, 1, 0.25), segs=(5, 2),
              rot=rnd.uniform(0, 3), wobble=0.3)
    fish_eye(p, GUIYU, -0.104, 0.85, 0.0068)
    p.blob((-0.127, 0.0, 0.022), 0.014, 'FishGill', squash=(0.7, 0.95, 0.85), segs=(6, 3))           # mouth
    p.blob((-0.132, 0.0, 0.01), 0.017, 'FishBelly', squash=(1.15, 1.0, 0.45), segs=(6, 3),
           deform=lambda v: Matrix.Rotation(-0.3, 3, 'Y') @ v)                                  # jutting lower jaw
    moved(p, n0, Matrix.Translation((0.006, 0.0, 0.01)) @ Matrix.Rotation(-0.35, 4, 'X'))
    return p.finish('SM_mandarin_fish', col)


YUTOU = [(-0.082, 0.058, 0.036, 0.012), (-0.072, 0.074, 0.02, 0.021), (-0.055, 0.091, 0.008, 0.031),
         (-0.028, 0.105, 0.001, 0.04), (0.005, 0.112, 0.0, 0.045), (0.035, 0.11, 0.003, 0.044),
         (0.05, 0.104, 0.007, 0.041)]


def fish_head(col):
    """大鱼头: a big fish head on a celadon plate: grey crown, gaping mouth, big eye, pink gills and cut face."""
    p = Part()
    plate(p, n=14)
    n0 = len(p.bm.verts)
    fish_body(p, YUTOU, 'FishBack', 'FishBelly', split=1.95)
    p.blob((0.051, 0.0, 0.0565), 0.05, 'FishGill', squash=(0.12, 0.76, 0.9), segs=(10, 4))        # cut face
    gill = []
    for k in range(5):                                                                        # gill cover edge
        c, nrm = flank(YUTOU, 0.008 + 0.012 * math.sin(k / 4 * math.pi), 0.5 + 0.5 * k)
        gill.append(c + nrm * 0.001)
    p.tube(gill, 0.0022, 'FishBack', sides=4)
    patch(p, YUTOU, 0.027, 1.6, 0.03, 'FishGill', squash=(0.3, 1, 0.2), segs=(6, 3))              # gills
    fish_eye(p, YUTOU, -0.045, 0.85, 0.013)
    p.blob((-0.084, 0.0, 0.05), 0.018, 'FishGill', squash=(0.7, 0.9, 1.0), segs=(6, 3))            # mouth
    p.blob((-0.088, 0.0, 0.035), 0.022, 'FishBelly', squash=(0.9, 0.95, 0.6), segs=(8, 3),
           deform=lambda v: Matrix.Rotation(-0.4, 3, 'Y') @ v)                                   # lower lip
    p.blob((-0.082, 0.0, 0.064), 0.016, 'FishBack', squash=(0.75, 0.9, 0.62), segs=(6, 3),
           deform=lambda v: Matrix.Rotation(0.4, 3, 'Y') @ v)                                    # upper lip
    moved(p, n0, Matrix.Translation((0.008, 0.0, 0.016)) @ Matrix.Rotation(-0.4, 4, 'X') @ Matrix.Rotation(0.3, 4, 'Y'))
    return p.finish('SM_fish_head', col)


def crab(col):
    """蟹: a blue-grey crab on a celadon plate: two big claws held in front, four legs a side, beady eyes."""
    p = Part()
    plate(p, n=12)
    n0 = len(p.bm.verts)
    p.blob((0.0, 0.008, 0.026), 0.048, 'CrabBelly', squash=(1.25, 0.9, 0.36), segs=(8, 3))        # underside
    p.blob((0.0, 0.01, 0.038), 0.05, 'CrabShell', squash=(1.34, 0.94, 0.4), segs=(12, 5),
           deform=lambda v: Vector((v.x * (1 - 2.5 * v.y), v.y, v.z)))                             # carapace
    for s in (-1, 1):
        for k, (bx, by) in enumerate(((0.056, -0.006), (0.06, 0.01), (0.056, 0.025), (0.047, 0.038))):  # legs
            a = math.radians(-28 + 26 * k)
            d = Vector((s * math.cos(a), math.sin(a), 0.0))
            b = Vector((s * bx, by, 0.032))
            ankle = b + d * 0.052 + Vector((0, 0, 0.004))
            p.tube([b, b + d * 0.026 + Vector((0, 0, 0.018)), ankle], 0.0072, 'CrabShell', sides=4)
            p.tube([ankle, b + d * 0.07 + Vector((0, 0, -0.02))], 0.006, 'CrabBelly', sides=4)   # orange tips
        p.tube([(s * 0.042, -0.026, 0.03), (s * 0.068, -0.05, 0.038), (s * 0.058, -0.074, 0.034)], 0.011,
               'CrabShell', sides=5)                                                             # claw arm
        u = Vector((-s * math.cos(0.5), -math.sin(0.5), 0.0))                                     # claw points inwards
        palm = Vector((s * 0.04, -0.088, 0.034))
        p.blob(palm, 0.028, 'CrabShell', squash=(1.4, 0.82, 0.72), segs=(7, 4), rot=s * 0.5)
        for (turn, dz) in ((0.3, -0.006), (-0.3, 0.008)):                                        # open pincer
            f = Matrix.Rotation(s * turn, 3, 'Z') @ u
            p.blob(palm + u * 0.036 + f * 0.016 + Vector((0, 0, dz)), 0.018, 'CrabBelly', squash=(1.5, 0.42, 0.4),
                   segs=(5, 3), rot=math.atan2(f.y, f.x))
        p.blob((s * 0.014, -0.037, 0.056), 0.005, 'FishEye', segs=(4, 3))
    moved(p, n0, Matrix.Translation((0.0, 0.012, 0.0)))                                         # claws onto the plate
    return p.finish('SM_crab', col)

# ---------------------------------------------------------------- sacks, parcels, pots and baskets
# Sacks, bundles and paper parcels are lathes dented by a deform and tied with twine that follows the same
# deform; baskets and trays are lathes whose ribbed wall rolls into a hoop rim bound with wraps.

def sacking(n, seed, dent=0.04, square=0.0, corner=0.0, top=None, flare=0.0, lift=0.0, waves=None):
    """Deform for sacks, bundles and parcels lathed with n sides: every side is dented by its own amount that
    changes with height, `square` pulls the section towards a square with corners at `corner` radians, and
    between the heights top = (z0, z1) the opening flares out in `waves` ruffles round the rim (by default a
    point on every other side), the first at `corner`, each a little different."""
    rnd = random.Random(seed)
    sides = [(rnd.uniform(-dent, dent), rnd.uniform(0, 2 * math.pi), rnd.uniform(-0.5, 0.5)) for _ in range(n)]

    def deform(v):
        a = math.atan2(v.y, v.x)
        d, ph, w = sides[round(a * n / (2 * math.pi)) % n]
        u = min(1.0, max(0.0, (v.z - top[0]) / (top[1] - top[0]))) ** 2 if top else 0.0
        tip = math.cos((waves or n / 2) * (a - corner)) + w
        k = 1 + d * math.sin(v.z * 40 + ph) + square * math.cos(4 * (a - corner)) + u * flare * (0.6 + 0.4 * tip)
        return Vector((v.x * k, v.y * k, v.z + u * lift * tip))
    return deform


def twine(p, r, z, deform, at, M=Matrix(), n=12, th=0.007, loops=2,
          ends=(((0.008, -0.01, -0.03), (0.013, -0.018, -0.065)), ((0.008, 0.01, -0.028), (0.012, 0.02, -0.06)))):
    """String tied round a neck of radius r at height z: a band that follows the sack's deform, a knot at angle
    `at`, a bow of up to two loops and the hanging ends, given as polylines of (out, along, up) offsets."""
    p.lathe([(r, z - th), (r + th, z), (r, z + th)], 'Twine', n=n, close_ends=False, deform=deform, M=M)
    out, side = Vector((math.cos(at), math.sin(at), 0.0)), Vector((-math.sin(at), math.cos(at), 0.0))
    knot = deform(out * (r + th) + Vector((0.0, 0.0, z)))

    def off(o, s, u):
        return M @ (knot + out * o + side * s + Vector((0.0, 0.0, u)))
    p.blob(off(th * 0.5, 0, 0), th * 1.8, 'Twine', segs=(6, 3), rot=at)
    for sg in (1, -1)[:loops]:   # bow loops, flopped outwards (a loop in an upright plane would twist the tube)
        loop = [(0.02, 0.016), (0.042, 0.013), (0.047, -0.005), (0.022, -0.008)]
        p.tube([off(0, 0, 0)] + [off(0.006 + 0.8 * w, sg * s, 0.6 * w) for s, w in loop] + [off(0, 0, 0)], th * 0.8,
               'Twine', sides=4)
    for e in ends:
        p.tube([off(0, 0, 0)] + [off(*q) for q in e], th * 0.8, 'Twine', sides=4)


def heap(p, at, r, z, hz, mat, n=12):
    """A rounded heap r wide rising hz above z (rice, pickles, cabbage); returns its height at a distance d from
    the middle, for laying things on it."""
    prof = [(r, z), (r * 0.75, z + hz * 0.55), (r * 0.4, z + hz * 0.9), (0.0, z + hz)]
    p.lathe(prof, mat, n=n, close_ends=False, M=Matrix.Translation((*at, 0.0)))

    def height(d):
        for (r0, z0), (r1, z1) in zip(prof, prof[1:]):
            if d >= r1:
                return z0 + (z1 - z0) * (r0 - min(d, r0)) / (r0 - r1)
    return height


def rice_heap(p, at, r, z, hz, grains, seed):
    """A heap of raw rice with a scatter of grains lying on it."""
    height = heap(p, at, r, z, hz, 'RiceGrain')
    rnd = random.Random(seed)
    for k in range(grains):
        d = r * 0.8 * math.sqrt((k + 0.5) / grains)
        a = k * 2.4 + rnd.uniform(-0.3, 0.3)
        p.blob((at[0] + d * math.cos(a), at[1] + d * math.sin(a), height(d) + 0.003), 0.01, 'RiceGrain',
               squash=(1.8, 0.8, 0.55), segs=(5, 3), rot=rnd.uniform(0, math.pi))


def wicker(p, r, h, base, t=0.008, bulge=1.0, rings=1, wraps=8, wrap='WickerBind', n=16, at=(0.0, 0.0), floor=0.01):
    """A woven bamboo basket or tray: a lathe from the base radius out to the rim radius r (`bulge` < 1 rounds the
    wall like a bowl), rolled into a hoop at the rim that is bound with `wraps` wraps; returns the inside floor height."""
    x, y = at
    prof = [(0.0, 0.0), (base, 0.0)]
    for i in range(1, rings + 1):
        f = i / (rings + 1)
        prof.append((base + (r - base) * f ** bulge, (h - t * 2.2) * f))
    cx, cz = r + t * 0.2, h - t
    prof += [(cx + t * math.cos(a), cz + t * math.sin(a)) for a in (-1.3, -0.3, 0.6, 1.5, 2.5)]
    prof += [(r - t * 1.3, h - t * 2.2), (base * 0.9, floor), (0.0, floor)]
    p.lathe(prof, 'Wicker', n=n, close_ends=False, M=Matrix.Translation((x, y, 0.0)))
    for j in range(wraps):
        a = 2 * math.pi * (j + 0.5) / wraps
        c = Vector((x + cx * math.cos(a), y + cx * math.sin(a), cz))
        d = Vector((-math.sin(a), math.cos(a), 0.0)) * t * 0.6
        p.tube([c - d, c + d], t * 1.2, wrap, sides=6)
    return floor


def parcel(p, r, h, tie, seed, inside, n=14, corner=math.pi / 4, flare=0.5, lift=0.03, fill=0.8):
    """An open paper parcel: a squarish crumpled bag tied with twine at height `tie`, the paper above opening out
    into flaps of different sizes at its corners, low at the front; the opening is closed at the fill height by a
    floor of the contents (`inside`) crumpled like the paper, so nothing shows past them; returns that height."""
    paper = sacking(n, seed, dent=0.07, square=0.08, corner=corner, top=(tie, h), flare=flare, lift=lift, waves=4)
    fz = h * fill
    p.lathe([(0.0, 0.0), (r * 0.85, 0.0), (r, h * 0.06), (r * 1.03, tie * 0.6), (r * 0.94, tie),
             (r * 0.97, tie + (h - tie) * 0.45), (r, h), (r * 0.96, h - 0.003), (r * 0.88, fz)],
            'WrapPaper', n=n, deform=paper, close_ends=False)
    p.lathe([(r * 0.88, fz), (0.0, fz)], inside, n=n, deform=paper, close_ends=False)
    twine(p, r * 0.94, tie, paper, at=-0.5, n=n)
    return fz


def clay_pot(p, r, h, mouth, belly=0.45, fill=0.88, n=16, at=(0.0, 0.0)):
    """陶罐: a round-bellied clay pot of radius r with a rolled rim round its mouth; returns the fill height and the
    inside radius there, where the contents should start so that they close the pot."""
    t = 0.009
    fz = h * fill
    p.lathe([(0.0, 0.0), (r * 0.6, 0.0), (r * 0.68, h * 0.03), (r * 0.92, h * belly * 0.45), (r, h * belly),
             (r * 0.96, h * (belly + 1) / 2), (mouth + t * 0.4, h - t * 1.8), (mouth + t, h - t), (mouth + t * 0.8, h),
             (mouth, h + t * 0.15), (mouth - t * 0.6, h - t * 0.6), (mouth - t * 0.8, fz)],
            'ClayPot', n=n, close_ends=False, M=Matrix.Translation((*at, 0.0)))
    return fz, mouth - t * 0.8


def drape(x0, rho, beta, wave=0.0):
    """Deform for a flat blob made long in z, so that its rings run across it: lays it along x and beyond x0
    bends it down over an edge (a rim) through `beta` radians round a bend of radius rho, to hang on straight;
    `wave` ripples it across."""
    def deform(v):
        v = Vector((v.z, v.y, -v.x + wave * math.sin(v.y * 150 + v.z * 60)))
        s = v.x - x0
        if s <= 0:
            return v
        th = min(s / rho, beta)
        q = Vector((x0 + (rho + v.z) * math.sin(th), v.y, -rho + (rho + v.z) * math.cos(th)))
        if s > rho * beta:
            q += Vector((math.cos(beta), 0.0, -math.sin(beta))) * (s - rho * beta)
        return q
    return deform


def rice(col):
    """米: a burlap sack of rice tied at the neck with rope, its mouth turned open, a few grains spilled in front."""
    p = Part()
    sack = sacking(12, 3, dent=0.045, top=(0.2, 0.28), flare=0.08, lift=0.014, waves=4)
    p.lathe([(0.0, 0.0), (0.12, 0.0), (0.152, 0.025), (0.165, 0.075), (0.158, 0.12), (0.135, 0.158), (0.118, 0.18),
             (0.13, 0.2), (0.152, 0.228), (0.172, 0.252), (0.178, 0.27), (0.166, 0.284), (0.15, 0.278),
             (0.14, 0.258)], 'Burlap', n=12, deform=sack, close_ends=False)
    p.lathe([(0.14, 0.258), (0.0, 0.258)], 'RiceGrain', n=12, deform=sack, close_ends=False)   # closes the mouth
    rice_heap(p, (0.0, 0.0), 0.146, 0.258, 0.065, 9, seed=3)
    twine(p, 0.118, 0.18, sack, at=-0.3, n=12, th=0.015, loops=0,
          ends=(((0.03, -0.01, -0.04), (0.06, -0.016, -0.1)), ((0.03, 0.016, -0.035), (0.058, 0.03, -0.085))))
    rnd = random.Random(4)
    for (x, y) in ((-0.13, -0.15), (-0.09, -0.18), (-0.16, -0.11), (-0.05, -0.2), (-0.12, -0.19)):
        p.blob((x, y, 0.006), 0.013, 'RiceGrain', squash=(1.7, 0.75, 0.45), segs=(5, 3), rot=rnd.uniform(0, math.pi))
    return p.finish('SM_rice', col)


def rice_prep(col):
    """米料备料: a bamboo basket heaped with rice and a wooden spoon in it, a cloth bundle tied up behind."""
    p = Part()
    sack = sacking(10, 7, dent=0.06, top=(0.14, 0.192), flare=0.12, lift=0.01)

    def cloth(v):   # gathered into pleats at the neck
        q = sack(v)
        k = 1 + 0.12 * math.cos(5 * math.atan2(v.y, v.x)) * min(1.0, v.z / 0.132) ** 2
        return Vector((q.x * k, q.y * k, q.z))
    M = Matrix.Translation((-0.075, 0.075, 0.0))
    p.lathe([(0.0, 0.0), (0.075, 0.0), (0.097, 0.018), (0.102, 0.05), (0.09, 0.09), (0.058, 0.118), (0.034, 0.132),
             (0.042, 0.142), (0.053, 0.158), (0.055, 0.176), (0.04, 0.19), (0.018, 0.198), (0.0, 0.199)],
            'BundleCloth', n=10, M=M, deform=cloth, close_ends=False)
    twine(p, 0.034, 0.132, cloth, at=-0.6, M=M, n=10, loops=0, ends=(((0.012, 0.0, -0.03), (0.03, 0.006, -0.065)),))
    wicker(p, 0.112, 0.085, 0.1, t=0.01, wraps=6, wrap='WickerBindGreen', n=12, at=(0.035, -0.035), floor=0.02)
    rice_heap(p, (0.035, -0.035), 0.104, 0.076, 0.045, 5, seed=5)
    p.tube([(0.088, -0.01, 0.118), (0.12, 0.028, 0.163), (0.15, 0.065, 0.213)], 0.011, 'LightWood', sides=6)
    p.blob((0.075, -0.022, 0.115), 0.032, 'LightWood', squash=(1.3, 1.0, 0.42), segs=(8, 4), rot=0.8)
    return p.finish('SM_rice_prep', col)


def pickle_base(col):
    """盐渍辅料包: an open paper parcel tied with twine, heaped with salted pickle shreds."""
    p = Part()
    fz = parcel(p, 0.115, 0.18, 0.095, seed=5, inside='Pickle', flare=0.45, lift=0.025, fill=0.75)
    height = heap(p, (0.0, 0.0), 0.1, fz, 0.055, 'Pickle')
    rnd = random.Random(6)
    for k in range(12):   # wavy shreds, pale and dark, all over the heap
        d, a, b = 0.085 * math.sqrt((k + 0.5) / 12), k * 2.4, rnd.uniform(0, math.pi)
        c = Vector((d * math.cos(a), d * math.sin(a), 0.0))
        along, across = Vector((math.cos(b), math.sin(b), 0.0)), Vector((-math.sin(b), math.cos(b), 0.0))
        pts = [c + along * (j - 1.5) * 0.03 + across * 0.008 * math.sin(j * 1.8 + k) for j in range(4)]
        pts = [q * min(1.0, 0.088 / max(q.length, 1e-6)) for q in pts]
        p.tube([(q.x, q.y, height(q.length) + 0.005) for q in pts], 0.006, 'PickleLeaf' if k % 2 else 'Pickle', sides=4)
    for k in range(5):
        a, d = rnd.uniform(0, 2 * math.pi), rnd.uniform(0.0, 0.06)
        p.blob((d * math.cos(a), d * math.sin(a), height(d) + 0.011), 0.006, 'Salt', segs=(4, 2))
    return p.finish('SM_pickle_base', col)


def seafood(col):
    """干贝海味包: an open paper bag tied with twine, full of dried scallops and curled shrimp."""
    p = Part()
    fz = parcel(p, 0.12, 0.15, 0.08, seed=8, inside='Scallop', flare=0.35, lift=0.025, fill=0.68)
    for (x, y, z, tilt, a) in ((-0.045, -0.032, 0.004, 0.5, 0.3), (0.038, -0.04, 0.002, 0.45, -0.4),
                               (-0.012, 0.035, 0.022, 0.3, 0.1), (0.055, 0.035, 0.015, 0.35, -0.3)):
        M = Matrix.Translation((x, y, fz + z)) @ Matrix.Rotation(a, 4, 'Z') @ Matrix.Rotation(tilt, 4, 'X')
        p.lathe([(0.0, 0.0), (0.028, 0.0), (0.03, 0.022), (0.027, 0.042)], 'Scallop', n=8, M=M, close_ends=False)
        p.lathe([(0.027, 0.042), (0.0, 0.044)], 'ScallopTop', n=8, M=M, close_ends=False)
    for (x, y, z, a) in ((0.004, -0.068, 0.036, 0.3), (-0.068, 0.012, 0.042, 0.5), (0.068, -0.008, 0.045, 0.1)):
        # a curled shrimp lying back, so that its tube never turns upright (where a tube's rings would flip)
        R = Matrix.Translation((x, y, fz + z)) @ Matrix.Rotation(a, 4, 'Z') @ Matrix.Rotation(-1.0, 4, 'X')
        arc = [R @ Vector((0.024 * math.cos(t), 0.0, 0.024 * math.sin(t))) for t in (0.8, 1.7, 2.6, 3.5, 4.4, 5.3)]
        p.tube(arc, 0.011, 'Shrimp', sides=5)
        p.blob(arc[-1] + R.to_3x3() @ Vector((0.008, 0.0, -0.004)), 0.012, 'Shrimp', squash=(1, 0.4, 0.8),
               segs=(4, 2), rot=a)
    return p.finish('SM_seafood', col)


def starch(col):
    """玉米淀粉: a yellow paper sack of corn starch with its top rolled down, a wooden scoop and a corn cob on the front."""
    p = Part()
    bag = sacking(16, 9, dent=0.06, square=0.08, corner=math.pi / 4, top=(0.19, 0.272), flare=0.06, lift=0.012,
                  waves=3)
    M = Matrix.Diagonal((1.0, 0.85, 1.0, 1.0))
    p.lathe([(0.0, 0.0), (0.105, 0.0), (0.124, 0.02), (0.128, 0.06), (0.124, 0.1), (0.12, 0.14), (0.117, 0.17),
             (0.118, 0.19), (0.125, 0.208), (0.142, 0.228), (0.15, 0.25), (0.144, 0.267), (0.13, 0.272), (0.12, 0.264),
             (0.115, 0.248)], 'StarchBag', n=16, deform=bag, M=M, close_ends=False)
    p.lathe([(0.115, 0.248), (0.0, 0.248)], 'Flour', n=16, deform=bag, M=M, close_ends=False)   # closes the mouth
    p.lathe([(0.116, 0.248), (0.09, 0.27), (0.045, 0.285), (0.0, 0.29)], 'Flour', n=16, M=M, close_ends=False)
    p.tube([(0.035, 0.03, 0.28), (0.07, 0.055, 0.33), (0.095, 0.075, 0.38)], 0.011, 'LightWood', sides=6)
    p.blob((0.025, 0.02, 0.282), 0.034, 'LightWood', squash=(1.25, 0.95, 0.45), segs=(8, 4), rot=0.6)
    tilt = Matrix.Rotation(0.6, 3, 'Y')
    p.blob((-0.005, -0.106, 0.118), 0.066, 'CornCob', squash=(0.38, 0.13, 1.0), segs=(8, 5), deform=lambda v: tilt @ v)
    for s in (-1, 1):
        lean = Matrix.Rotation(0.6 + s * 0.5, 3, 'Y')
        p.blob((-0.026 + s * 0.017, -0.108, 0.08), 0.06, 'Greens', squash=(0.2, 0.08, 1.0), segs=(6, 3),
               deform=lambda v, lean=lean: lean @ v)
    return p.finish('SM_starch', col)


def sauerkraut(col):
    """酸菜: a round clay pot packed with yellow-green pickled cabbage, one leaf hanging over the rim."""
    p = Part()
    fz, rin = clay_pot(p, 0.13, 0.18, 0.095, belly=0.42, fill=0.9, n=14)
    height = heap(p, (0.0, 0.0), rin, fz, 0.03, 'Pickle', n=14)
    for k, a in enumerate((0.4, 1.7, 2.9, 4.2, 5.5)):
        x, y = 0.035 * math.cos(a), 0.035 * math.sin(a)
        p.blob((x, y, height(0.035) + 0.008), 0.06, 'PickleLeaf' if k % 2 else 'Pickle', squash=(0.08, 0.42, 1.0),
               segs=(6, 6), rot=a + 0.3, deform=drape(0.0, 0.03, 0.5, wave=0.006))
    for (at, z, r, mat) in ((-0.6, 0.192, 0.12, 'Pickle'), (-0.32, 0.188, 0.105, 'PickleLeaf')):
        p.blob((0.07 * math.cos(at), 0.07 * math.sin(at), z), r, mat, squash=(0.055, 0.36, 1.0), segs=(6, 8), rot=at,
               deform=drape(0.035, 0.012, 1.2, wave=0.004))
    return p.finish('SM_sauerkraut', col)


def stock(col):
    """肉汤备料: a clay pot of golden broth with two lug handles, its lid leaning against the side."""
    p = Part()
    x0 = -0.04
    fz, rin = clay_pot(p, 0.115, 0.1, 0.098, belly=0.42, fill=0.8, at=(x0, 0.0))
    p.lathe([(rin, fz), (0.0, fz + 0.001)], 'Broth', n=16, close_ends=False, M=Matrix.Translation((x0, 0.0, 0.0)))
    for (x, y, r) in ((-0.03, -0.02, 0.012), (0.02, 0.025, 0.009), (0.035, -0.03, 0.007), (-0.01, 0.04, 0.006)):
        p.lathe([(r, fz + 0.0015), (0.0, fz + 0.002)], 'Oil', n=6, close_ends=False,
                M=Matrix.Translation((x0 + x, y, 0.0)))
    for s in (-1, 1):
        p.blob((x0 + s * 0.12, 0.0, 0.072), 0.026, 'ClayPot', squash=(1.2, 1.1, 0.55), segs=(8, 4))
    M = Matrix.Translation((0.118, 0.035, 0.098)) @ Matrix.Rotation(0.2, 4, 'Z') @ Matrix.Rotation(1.12, 4, 'Y')
    p.lathe([(0.0, 0.004), (0.096, -0.004), (0.104, -0.001), (0.1, 0.003), (0.07, 0.013), (0.03, 0.021), (0.01, 0.024),
             (0.018, 0.03), (0.017, 0.035), (0.0, 0.036)], 'ClayPot', n=14, M=M, close_ends=False)
    return p.finish('SM_stock', col)


def pancake(col):
    """薄饼备料: a stack of thin pancakes with browned spots on a round bamboo tray, one folded on top."""
    p = Part()
    fz = wicker(p, 0.14, 0.03, 0.13, t=0.009, wraps=8, floor=0.006)
    prof = [(0.0, fz), (0.085, fz)]
    for i in range(6):
        prof += [(0.093, fz + 0.008 * i + 0.004), (0.086, fz + 0.008 * (i + 1))]
    prof += [(0.0, fz + 0.05)]
    top = fz + 0.05

    def layers(v):
        k = 1 + 0.03 * math.sin(3 * math.atan2(v.y, v.x) + v.z * 300)
        return Vector((v.x * k, v.y * k, v.z))
    p.lathe(prof, 'Pancake', n=12, M=Matrix.Translation((-0.006, -0.01, 0.0)), close_ends=False, deform=layers)
    M = Matrix.Translation((0.065, 0.06, top + 0.025)) @ Matrix.Rotation(-2.4, 4, 'Z') \
        @ Matrix.Rotation(math.pi / 2, 4, 'Y') @ Matrix.Diagonal((0.45, 1.0, 1.0, 1.0))
    p.lathe([(0.0, 0.0), (0.02, 0.015), (0.045, 0.06), (0.058, 0.1), (0.06, 0.112), (0.054, 0.116), (0.0, 0.11)],
            'Pancake', n=10, M=M, close_ends=False)   # one folded into a cone, its open end to the front
    for (x, y, z, r) in ((-0.05, -0.03, top, 0.007), (-0.02, -0.062, top, 0.005), (-0.068, 0.012, top, 0.005),
                         (0.002, -0.04, top, 0.006), (-0.04, 0.035, top, 0.004), (-0.075, -0.035, top, 0.004),
                         (0.022, 0.012, top + 0.046, 0.006), (0.0, -0.012, top + 0.051, 0.005)):
        p.lathe([(r, z + 0.0005), (0.0, z + 0.001)], 'Char', n=5, close_ends=False, M=Matrix.Translation((x, y, 0.0)))
    return p.finish('SM_pancake', col)


def egg(col):
    """鸡蛋: three eggs in a shallow woven bamboo basket bound at the rim."""
    p = Part()
    fz = wicker(p, 0.08, 0.05, 0.05, t=0.011, bulge=0.55, rings=3, wraps=8, floor=0.012)

    def shape(tilt):
        R = Matrix.Rotation(-tilt, 3, 'Y')
        return lambda v: R @ Vector((v.x, v.y * (1 - 0.1 * v.x / 0.035), v.z * (1 - 0.1 * v.x / 0.035)))
    for (x, y, z, a, tilt) in ((0.0, 0.03, 0.042, 1.4, 0.55), (-0.033, -0.017, 0.03, 0.4, 0.2),
                               (0.034, -0.022, 0.031, -0.5, 0.25)):
        p.blob((x, y, fz + z), 0.027, 'EggShell', squash=(1.3, 1.0, 1.0), segs=(12, 6), rot=a, deform=shape(tilt))
    return p.finish('SM_egg', col)


# ---------------------------------------------------------------- vegetables, seasoning vessels and drinks

def leaf(p, base, length, width, mat, yaw=0.0, pitch=0.0, roll=0.0, fold=0.3, curl=0.0, widest=0.4, teeth=0.0,
         rings=6, thick=0.003):
    """A pointed leaf blade from `base`, its midrib turned `yaw` about Z, tipped up by `pitch` and rolled by `roll`;
    V-folded along the midrib (fold < 0 arches it instead), the tip curled down by `curl`, widest at `widest` of its
    length, the margin alternating by `teeth` ring to ring for serrated or lobed leaves. A four-sided sphere keeps
    it cheap: margin, midrib, margin, underside."""
    R = Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(-pitch, 4, 'Y') @ Matrix.Rotation(roll, 4, 'X')
    a = math.log(0.5) / math.log(widest)

    def shape(v):   # sphere z runs base to tip, x across, y through the blade (y = -x keeps the faces outward)
        th = math.acos(max(-1.0, min(1.0, v.z)))
        t, s = th / math.pi, math.sin(th)
        y = 0.0 if s < 1e-6 else \
            -v.x / s * 0.5 * width * math.sin(math.pi * t ** a) * (1 + teeth * (-1) ** round(t * rings))
        return R @ Vector((t * length, y, v.y * thick + fold * abs(y) - curl * length * t * t))
    p.blob(base, 1.0, mat, segs=(4, rings), deform=shape)


def cup(p, x, y, r, h, fill, fill_z, n=12):
    """A small 青瓷 cup on a foot ring at (x, y), rim radius r and height h, filled with `fill` up to fill_z."""
    M = Matrix.Translation((x, y, 0.0))
    p.lathe([(r * 0.42, 0.0), (r * 0.55, 0.0), (r * 0.57, h * 0.16), (r * 0.86, h * 0.5), (r, h), (r - 0.0025, h + 0.002),
             (r - 0.005, h), (r * 0.8, fill_z)], 'Celadon', n=n, M=M, close_ends=False)
    p.lathe([(0.0, 0.003), (r * 0.42, 0.0)], 'Celadon', n=n, M=M, close_ends=False)   # underside
    p.lathe([(r * 0.8, fill_z), (0.0, fill_z + 0.001)], fill, n=n, M=M, close_ends=False)


def radish(col):
    """萝卜: a white radish lying on its side with its leafy green top, two round slices leaning in front."""
    p = Part()
    yaw, tilt = 0.8, 0.23
    d = Vector((math.cos(yaw) * math.cos(tilt), math.sin(yaw) * math.cos(tilt), math.sin(tilt)))   # tip to crown
    tip = Vector((-0.115, -0.075, 0.026))
    M = Matrix.Translation(tip) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(math.pi / 2 - tilt, 4, 'Y')
    p.lathe([(0.0, 0.0), (0.016, 0.008), (0.03, 0.03), (0.04, 0.065), (0.046, 0.1), (0.048, 0.15)], 'RadishWhite',
            n=10, M=M, close_ends=False)
    p.lathe([(0.048, 0.15), (0.049, 0.18), (0.046, 0.2), (0.037, 0.216), (0.02, 0.225), (0.0, 0.227)], 'RadishTop',
            n=10, M=M, close_ends=False)
    p.tube([tip + d * 0.006, tip - d * 0.02 - Vector((0, 0, 0.01)), Vector((tip.x - 0.04, tip.y - 0.03, 0.003))],
           0.002, 'RadishWhite', sides=4)                                                       # root tail
    crown = tip + d * 0.215
    for (a, pitch, ln, wd) in ((2.5, 0.75, 0.1, 0.066), (1.9, 1.0, 0.12, 0.075), (1.3, 1.05, 0.12, 0.075),
                               (0.75, 0.85, 0.11, 0.07), (0.15, 0.6, 0.1, 0.065)):
        out = Vector((math.cos(a) * math.cos(pitch), math.sin(a) * math.cos(pitch), math.sin(pitch)))
        p.tube([crown, crown + out * 0.018 + Vector((0, 0, 0.005)), crown + out * 0.034], 0.005, 'RadishTop', sides=4)
        leaf(p, crown + out * 0.03, ln, wd, 'RadishLeaf', yaw=a, pitch=pitch - 0.2, fold=0.25, curl=0.2, teeth=0.18,
             rings=7, thick=0.004)
    for (x, y, z, n) in ((0.055, -0.055, 0.04, (0.2, -0.85, 0.45)), (0.112, -0.02, 0.04, (0.75, -0.5, 0.45))):  # slices
        S = Matrix.Translation((x, y, z)) @ Vector(n).to_track_quat('Z', 'Y').to_matrix().to_4x4()
        p.lathe([(0.0, 0.0), (0.038, 0.0), (0.042, 0.0065), (0.038, 0.013), (0.033, 0.0133)], 'RadishWhite', n=12,
                M=S, close_ends=False)
        p.lathe([(0.033, 0.0133), (0.0, 0.0138)], 'RadishFlesh', n=12, M=S, close_ends=False)
    return p.finish('SM_radish', col)


def gourd(col):
    """瓜菜: a whole cucumber with its curled stalk, a cut one in front sliced on the bias to show the pale flesh."""
    p = Part()
    R = Matrix.Rotation(-0.42, 4, 'Z') @ Matrix.Rotation(math.pi / 2, 4, 'Y')   # lying along X, local x points down
    whole = Matrix.Translation((-0.08, 0.07, 0.027)) @ R
    p.lathe([(0.0, 0.0), (0.012, 0.004), (0.021, 0.014), (0.026, 0.035), (0.027, 0.08), (0.026, 0.15), (0.022, 0.19),
             (0.013, 0.207), (0.0, 0.212)], 'CucumberGreen', n=10, M=whole, close_ends=False)
    p.tube([whole @ Vector((0.0, 0.0, 0.003)), whole @ Vector((-0.004, 0.0, -0.012)),
            whole @ Vector((-0.014, 0.001, -0.021))], 0.005, 'CalyxGreen', sides=5)               # stalk

    def bias(q):   # the cut end is sliced on a slant that turns it toward the viewer
        return Vector((q.x, q.y, q.z + (0.75 * q.x + 0.9 * q.y if q.z > 0.1299 else 0.0)))
    cut = Matrix.Translation((-0.11, 0.0, 0.028)) @ R
    p.lathe([(0.0, 0.0), (0.012, 0.004), (0.022, 0.014), (0.027, 0.035), (0.028, 0.08), (0.028, 0.13), (0.024, 0.13)],
            'CucumberGreen', n=10, M=cut, deform=bias, close_ends=False)
    p.lathe([(0.024, 0.13), (0.014, 0.1302)], 'CucumberFlesh', n=10, M=cut, deform=bias, close_ends=False)
    p.lathe([(0.014, 0.1302), (0.0, 0.1306)], 'CucumberSeed', n=10, M=cut, deform=bias, close_ends=False)
    for M, rows in ((whole, 6), (cut, 4)):   # warts in staggered rows along the side the viewer sees
        for i in range(rows):
            for th in ((3.4, 4.2), (3.8, 4.6))[i % 2]:
                p.blob(M @ Vector((0.027 * math.cos(th), 0.027 * math.sin(th), 0.035 + 0.024 * i)), 0.0028, 'CalyxGreen',
                       segs=(4, 2))
    return p.finish('SM_gourd', col)


def bamboo(col):
    """笋: a bamboo shoot in pointed brown sheaths with green tips, a peeled pale one beside it, two half-moon slices."""
    p = Part()
    H = Matrix.Translation((-0.045, 0.02, 0.0))
    p.lathe([(0.012, 0.09), (0.007, 0.13), (0.0, 0.16)], 'CalyxGreen', n=8, M=H, close_ends=False)   # the bud
    for tier, (prof, tips, mat) in enumerate((   # each sheath sleeve: up the outside, over the rim, down the inside
            ([(0.043, 0.0), (0.047, 0.02), (0.042, 0.045), (0.038, 0.043), (0.043, 0.02)], 0.045, 'BambooHusk'),
            ([(0.036, 0.015), (0.039, 0.045), (0.033, 0.075), (0.029, 0.073), (0.035, 0.045)], 0.04, 'BambooHusk'),
            ([(0.028, 0.045), (0.03, 0.075), (0.023, 0.1), (0.019, 0.098), (0.026, 0.075)], 0.035, 'BambooHusk'),
            ([(0.019, 0.075), (0.02, 0.1), (0.013, 0.12), (0.009, 0.118), (0.016, 0.1)], 0.03, 'CalyxGreen'))):
        z0, z1 = prof[0][1], prof[2][1]

        def sheaths(q, a0=0.3 + tier * math.pi / 3, tips=tips, z0=z0, z1=z1):   # the rim rises into three points
            f = abs(math.cos(1.5 * (math.atan2(q.y, q.x) - a0))) ** 3 * min(1.0, max(0.0, (q.z - z0) / (z1 - z0))) ** 2
            return Vector((q.x * (1 - 0.15 * f), q.y * (1 - 0.15 * f), q.z + tips * f))
        p.lathe(prof, mat, n=12, M=H, deform=sheaths, close_ends=False)
    p.lathe([(0.0, 0.0), (0.034, 0.0), (0.037, 0.006), (0.032, 0.034), (0.0345, 0.036), (0.027, 0.064), (0.029, 0.066),
             (0.02, 0.092), (0.022, 0.094), (0.011, 0.118), (0.0125, 0.12), (0.0, 0.148)], 'BambooFlesh', n=10,
            M=Matrix.Translation((0.045, 0.0, 0.0)), close_ends=False)                          # the peeled shoot
    for (x, y, rot, lean) in ((-0.02, -0.065, 0.45, 0.35), (0.028, -0.072, 0.15, 0.3)):        # half-moon slices
        L = Matrix.Rotation(-lean, 4, 'X')   # resting on the curved edge, the straight cut edge up
        p.blob((x, y, 0.0), 0.032, 'BambooFlesh', squash=(1.0, 1.0, 0.3), segs=(12, 3), rot=rot,
               deform=lambda v, L=L: L @ Vector((v.x, -v.z, min(v.y, 0.0) + 0.032)))
    return p.finish('SM_bamboo', col)


def perilla(col):
    """紫苏: a bunch of purple perilla leaves, two greener ones among them, their stalks tied with twine."""
    p = Part()
    tie = Vector((-0.065, -0.05, 0.012))
    d = Vector((math.cos(0.75), math.sin(0.75), 0.0))
    for k, (yaw, pitch, roll, ln, wd, mat, reach) in enumerate((
            (2.05, 0.5, -0.2, 0.11, 0.075, 'PerillaGreen', 0.03), (1.6, 0.62, 0.0, 0.13, 0.085, 'PerillaDeep', 0.045),
            (1.15, 0.58, 0.2, 0.14, 0.09, 'PerillaGreen', 0.06), (0.8, 0.5, 0.35, 0.14, 0.09, 'PerillaPurple', 0.05),
            (0.45, 0.42, 0.5, 0.135, 0.088, 'PerillaDeep', 0.065), (0.1, 0.3, 0.65, 0.12, 0.08, 'PerillaPurple', 0.045),
            (-0.25, 0.2, 0.75, 0.1, 0.07, 'PerillaDeep', 0.03))):
        end = tie - d * 0.05 + Vector((0.0, (k - 3) * 0.004, 0.0))
        base = tie + d * reach + Vector((math.cos(yaw), math.sin(yaw), 0.0)) * 0.01 + Vector((0, 0, 0.005 * k))
        p.tube([end, tie, base], 0.0032, 'PerillaGreen', sides=4)
        leaf(p, base, ln, wd, mat, yaw=yaw, pitch=pitch, roll=roll, fold=0.32, curl=0.2, widest=0.35, teeth=0.07,
             rings=9)
    band = Matrix.Translation(tie) @ Matrix.Rotation(0.75, 4, 'Z') @ Matrix.Rotation(math.pi / 2, 4, 'Y') \
        @ Matrix.Diagonal((0.6, 1.0, 1.0, 1.0))
    p.lathe([(0.013, -0.005), (0.015, 0.0), (0.013, 0.005), (0.011, 0.0), (0.013, -0.005)], 'Twine', n=10,
            close_ends=False, M=band)                                                          # a closed ring of twine
    knot = tie + Vector((0.0, -0.004, 0.009))
    p.blob(knot, 0.005, 'Twine', segs=(5, 3))
    for e in (Vector((0.012, -0.024, -0.01)), Vector((-0.006, -0.026, -0.012))):                  # loose ends
        p.tube([knot, knot + e * 0.5 + Vector((0, 0, 0.002)), knot + e], 0.0018, 'Twine', sides=4)
    return p.finish('SM_perilla', col)


def mushroom(col):
    """菌菇: three shiitake, two showing brown caps scored with a cross, one tipped over to show gills and stem."""
    p = Part()
    gills = [(0.0, 0.007), (0.026, 0.002), (0.032, -0.001)]
    cap = [(0.032, -0.001), (0.036, 0.004), (0.035, 0.012), (0.028, 0.024), (0.016, 0.033), (0.0, 0.036)]
    stem = [(0.0, -0.039), (0.013, -0.037), (0.012, -0.033), (0.0105, -0.016), (0.011, 0.005)]
    for k, (pos, axis) in enumerate((((0.012, 0.04, 0.044), (0.05, -0.45, 0.89)),
                                     ((0.055, -0.02, 0.042), (0.2, -0.4, 0.9)),
                                     ((-0.045, -0.015, 0.039), (-0.45, 0.85, 0.27)))):   # the last one tipped over
        M = Matrix.Translation(pos) @ Vector(axis).to_track_quat('Z', 'Y').to_matrix().to_4x4()
        p.lathe(cap, 'ShiitakeCap', n=12, M=M, close_ends=False)
        p.lathe(gills, 'ShiitakeFlesh', n=12, M=M, close_ends=False)
        p.lathe(stem, 'ShiitakeFlesh', n=8, M=M, close_ends=False)
        if k < 2:
            for a in (0.75, -0.75):   # the cross cut, bent over the dome
                p.blob((0, 0, 0), 0.019, 'ShiitakeFlesh', squash=(1.0, 0.22, 0.12), segs=(6, 2),
                       deform=lambda v, a=a, M=M: M @ Matrix.Rotation(a, 4, 'Z') @
                       Vector((v.x, v.y, v.z + 0.0365 - 13 * (v.x ** 2 + v.y ** 2))))
    return p.finish('SM_mushroom', col)


def tomato(col):
    """番茄: two red tomatoes with green star calyxes and stalks, and a half showing the flesh and seeds."""
    p = Part()

    def lobes(q):
        k = 1 + 0.03 * math.cos(5 * math.atan2(q.y, q.x))
        return Vector((q.x * k, q.y * k, q.z))
    for (x, y, s, rot) in ((-0.038, -0.012, 1.05, 0.2), (0.035, 0.045, 1.0, 1.1)):
        M = Matrix.Translation((x, y, 0.0)) @ Matrix.Rotation(rot, 4, 'Z') @ Matrix.Scale(s, 4)
        p.lathe([(0.0, 0.003), (0.02, 0.0), (0.034, 0.01), (0.041, 0.03), (0.038, 0.05), (0.027, 0.062), (0.012, 0.0655),
                 (0.0, 0.062)], 'TomatoRed', n=12, M=M, deform=lobes, close_ends=False)
        for k in range(5):   # the calyx: a star of sepals drooping over the shoulder
            leaf(p, M @ Vector((0.0, 0.0, 0.067)), 0.042 * s, 0.013 * s, 'CalyxGreen', yaw=rot + k * 2 * math.pi / 5,
                 pitch=-0.05, fold=0.1, curl=0.3, widest=0.3, rings=3, thick=0.002)
        top = M @ Vector((0.0, 0.0, 0.064))
        p.tube([top, top + Vector((0.001, 0.0, 0.012)), top + Vector((0.006, 0.002, 0.018))], 0.0032, 'CalyxGreen',
               sides=5)
    H = Matrix.Translation((0.055, -0.05, 0.034)) @ \
        Vector((0.3, -0.85, 0.45)).to_track_quat('Z', 'Y').to_matrix().to_4x4()   # the half, cut face to the viewer
    r = 0.034
    p.lathe([(0.0, -r * 0.95), (r * 0.55, -r * 0.8), (r * 0.88, -r * 0.45), (r, -r * 0.1), (r, 0.0), (r * 0.84, 0.0005)],
            'TomatoRed', n=12, M=H, close_ends=False)
    p.lathe([(r * 0.84, 0.0005), (0.0, 0.001)], 'TomatoFlesh', n=12, M=H, close_ends=False)
    for k in range(5):   # seeds in their jelly, in a ring
        p.blob((0, 0, 0), 0.0045, 'TomatoSeed', squash=(1.6, 0.8, 0.3), segs=(5, 2),
               deform=lambda v, a=0.3 + k * 2 * math.pi / 5: H @ Matrix.Rotation(a, 4, 'Z') @
               Vector((v.x + 0.016, v.y, v.z + 0.001)))
    return p.finish('SM_tomato', col)


def chili(col):
    """辣椒: three long red chilli peppers curving to a point, with green caps and hooked stalks."""
    p = Part()
    body = [(0.0, 0.0), (0.014, 0.0045), (0.018, 0.017), (0.0175, 0.045), (0.016, 0.078), (0.012, 0.107),
            (0.007, 0.128), (0.0032, 0.142), (0.0006, 0.15)]
    for (x, y, z, yaw, bend) in ((-0.088, 0.012, 0.0195, -0.72, 0.055), (-0.081, 0.045, 0.035, -0.65, 0.05),
                                 (-0.066, 0.078, 0.0195, -0.58, 0.055)):
        M = Matrix.Translation((x, y, z)) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(math.pi / 2, 4, 'Y')

        def curve(q, bend=bend):   # sweeps sideways along the length, the tip hooking up
            u = q.z / 0.15
            return Vector((q.x - 0.02 * max(0.0, u - 0.6) ** 2 / 0.16, q.y + bend * u * u, q.z))
        p.lathe(body, 'ChiliRed', n=8, M=M, deform=curve)
        p.lathe([(0.0, -0.002), (0.014, 0.0), (0.019, 0.008), (0.0185, 0.015), (0.016, 0.0165)], 'CalyxGreen', n=8,
                M=M, close_ends=False)                                                          # cap, its rim tucked in
        p.tube([M @ Vector((0.0, 0.0, 0.0)), M @ Vector((-0.003, 0.0, -0.013)), M @ Vector((-0.012, -0.002, -0.023)),
                M @ Vector((-0.025, -0.005, -0.025))], 0.0036, 'CalyxGreen', sides=5)          # hooked stalk
    return p.finish('SM_chili', col)


def potato(col):
    """土豆: two lumpy potatoes with dark eyes and a peeled half lying on its cut face, pale and faceted by the knife."""
    p = Part()
    for (x, y, r, sq, rot, ph, eyes) in ((-0.043, 0.012, 0.047, (1.3, 0.92, 0.75), 0.35, 0.0,
                                          ((-0.5, -0.6, 0.6), (0.35, -0.8, 0.45), (-0.95, -0.2, 0.3), (0.1, -0.2, 1.0))),
                                         (0.04, 0.038, 0.042, (1.25, 0.95, 0.78), -0.55, 2.0,
                                          ((0.1, -0.6, 0.8), (0.8, -0.4, 0.45), (0.5, 0.1, 0.9)))):
        def lumps(v, ph=ph, r=r):
            return v * (1 + 0.07 * math.sin(2.2 * v.x / r + ph) * math.cos(1.7 * v.y / r - ph)
                        + 0.04 * math.sin(3 * v.z / r + ph))
        c = Vector((x, y, r * sq[2] * 0.97))
        p.blob(c, r, 'PotatoSkin', squash=sq, segs=(10, 6), rot=rot, deform=lumps)
        for e in eyes:   # set on the lumpy surface, in directions the viewer sees
            u = Matrix.Rotation(-rot, 3, 'Z') @ Vector(e).normalized()
            p.blob(c + Matrix.Rotation(rot, 3, 'Z') @ lumps(Vector((u.x * r * sq[0], u.y * r * sq[1], u.z * r * sq[2]))),
                   0.004, 'PotatoEye', segs=(4, 2))
    rnd = random.Random(5)

    def facets(q):
        k = rnd.uniform(0.9, 1.08)
        return Vector((q.x * k, q.y * k, q.z * rnd.uniform(0.92, 1.06)))
    M = Matrix.Translation((0.002, -0.045, 0.0)) @ Matrix.Rotation(0.3, 4, 'Z') @ Matrix.Diagonal((1.25, 0.95, 1.0, 1.0))
    p.lathe([(0.0, 0.0), (0.036, 0.0), (0.038, 0.012), (0.03, 0.028), (0.016, 0.037), (0.0, 0.039)], 'PotatoFlesh', n=7,
            M=M, deform=facets, close_ends=False)
    return p.finish('SM_potato', col)


def garlic(col):
    """蒜: a garlic bulb of bulging cloves streaked along the creases, two peeled cloves and one still in its skin."""
    p = Part()
    B = Matrix.Translation((-0.012, 0.02, 0.0))
    prof = [(0.0, 0.002), (0.02, 0.0), (0.04, 0.01), (0.049, 0.028), (0.046, 0.047), (0.034, 0.064), (0.017, 0.078),
            (0.01, 0.092), (0.0055, 0.106), (0.0045, 0.115), (0.0, 0.114)]

    def cloves(q):   # eight cloves bulge between creases
        k = 1 - 0.1 * (1 - abs(math.cos(4 * math.atan2(q.y, q.x)))) * min(1.0, math.hypot(q.x, q.y) / 0.03)
        return Vector((q.x * k, q.y * k, q.z))
    p.lathe(prof, 'GarlicSkin', n=16, M=B, deform=cloves, close_ends=False)
    for a in (-157.5, -112.5, -67.5, -22.5, 22.5):   # purple streaks down the creases the viewer sees
        a = math.radians(a)
        pts = [B @ Vector(((r * (1 - 0.1 * min(1.0, r / 0.03)) + 0.0005) * math.cos(a),
                           (r * (1 - 0.1 * min(1.0, r / 0.03)) + 0.0005) * math.sin(a), z)) for (r, z) in prof[2:7]]
        for run in (pts[:2], pts[1:]):   # split at the widest ring so neither tube turns back on itself
            p.tube(run, 0.0016, 'GarlicStreak', sides=4)

    def clove(v, tilt):   # poles become the ends: a plump back, a pointed tip, a flat underside, a crescent
        k = 1 - 0.55 * ((v.z + 1) / 2) ** 1.5
        x, y, z = v.z * 0.02, v.x * 0.0135 * k + 0.006 * v.z * v.z, (max(v.y, -0.4) + 0.4) * 0.016 * k
        return Vector((x * math.cos(tilt) - z * math.sin(tilt), y,
                       x * math.sin(tilt) + z * math.cos(tilt) + 0.02 * math.sin(tilt)))
    for (x, y, rot, tilt, mat) in ((-0.028, -0.04, math.pi + 0.45, 0.15, 'GarlicClove'),
                                   (0.018, -0.045, -0.5, 0.15, 'GarlicClove'), (0.055, -0.004, 0.7, 0.35, 'GarlicPeel')):
        p.blob((x, y, 0.0), 1.0, mat, segs=(8, 6), rot=rot, deform=lambda v, tilt=tilt: clove(v, tilt))
    return p.finish('SM_garlic', col)


def sugar(col):
    """糖: a celadon bowl with a scalloped rim heaped with white sugar, two lumps of rock sugar and a wooden spoon."""
    p = Part()

    def scallop(q):
        k = 1 + 0.04 * math.cos(6 * math.atan2(q.y, q.x)) * min(1.0, max(0.0, (math.hypot(q.x, q.y) - 0.055) / 0.021))
        return Vector((q.x * k, q.y * k, q.z))
    p.lathe([(0.03, 0.0), (0.036, 0.0), (0.037, 0.01), (0.056, 0.03), (0.072, 0.056), (0.076, 0.064), (0.073, 0.067),
             (0.069, 0.063), (0.064, 0.052)], 'Celadon', n=16, deform=scallop, close_ends=False)
    p.lathe([(0.0, 0.004), (0.03, 0.0)], 'Celadon', n=16, close_ends=False)                     # underside
    p.lathe([(0.064, 0.052), (0.045, 0.064), (0.02, 0.071), (0.0, 0.073)], 'SugarWhite', n=16, deform=scallop,
            close_ends=False)
    rnd = random.Random(6)
    crystals = 0
    while crystals < 12:   # coarse crystals on the heap, where the rock sugar and the spoon leave it bare
        a, d = rnd.uniform(0, 2 * math.pi), rnd.uniform(0.008, 0.056)
        x, y = d * math.cos(a), d * math.sin(a)
        if (x - 0.037) ** 2 + (y + 0.005) ** 2 < 0.04 ** 2 or (x + 0.02) ** 2 + y ** 2 < 0.025 ** 2:
            continue
        crystals += 1
        p.box((0, 0, 0), (0.008, 0.008, 0.008), 'SugarWhite', rot=rnd.uniform(0, 1.5),
              M=Matrix.Translation((x, y, 0.075 - 5 * d * d)) @ Matrix.Rotation(rnd.uniform(0.3, 0.9), 4, 'X'))
    for (x, y, z, r, rot) in ((0.03, 0.019, 0.08, 0.027, 0.4), (0.046, -0.026, 0.076, 0.024, 1.3)):   # rock sugar
        p.blob((x, y, z), r, 'RockSugar', squash=(1.1, 0.95, 0.85), segs=(5, 3), rot=rot,
               deform=lambda v: v * rnd.uniform(0.7, 1.25))
    p.tube([(-0.022, 0.0, 0.074), (-0.05, 0.012, 0.096), (-0.08, 0.024, 0.116)], 0.0055, 'LightWood', sides=6)
    p.blob((-0.018, -0.002, 0.073), 0.021, 'LightWood', squash=(1.3, 1.0, 0.4), segs=(8, 4), rot=0.4)
    return p.finish('SM_sugar', col)


def vinegar(col):
    """醋: a round dark-glazed jug with a spout and a stopper, a small celadon cup of dark vinegar in front of it."""
    p = Part()
    M = Matrix.Translation((0.015, 0.025, 0.0))
    p.lathe([(0.0, 0.0), (0.045, 0.0), (0.054, 0.006), (0.068, 0.03), (0.071, 0.055), (0.065, 0.083), (0.05, 0.103),
             (0.034, 0.114), (0.029, 0.121), (0.037, 0.125), (0.038, 0.136), (0.033, 0.14), (0.028, 0.136),
             (0.024, 0.13)], 'VinegarGlaze', n=14, M=M, close_ends=False)                       # body, neck and collar
    p.lathe([(0.024, 0.13), (0.026, 0.142), (0.032, 0.145), (0.034, 0.151), (0.031, 0.16), (0.019, 0.167), (0.0, 0.169)],
            'JugStopper', n=14, M=M, close_ends=False)                                         # stopper
    S = M @ Matrix.Translation((-0.05, -0.012, 0.085)) @ \
        Vector((-0.78, -0.25, 0.58)).to_track_quat('Z', 'Y').to_matrix().to_4x4()
    p.lathe([(0.015, 0.0), (0.012, 0.02), (0.009, 0.04), (0.0105, 0.046), (0.008, 0.049)], 'VinegarGlaze', n=10, M=S,
            close_ends=False)                                                                  # spout
    p.lathe([(0.008, 0.049), (0.0, 0.044)], 'VinegarDark', n=10, M=S, close_ends=False)
    cup(p, -0.037, -0.07, 0.036, 0.03, 'VinegarDark', 0.023)
    return p.finish('SM_vinegar', col)


def wine(col):
    """酒: a celadon ewer with a lobed flaring mouth, a curved spout and a loop handle, a small cup of pale wine."""
    p = Part()
    M = Matrix.Translation((0.02, 0.03, 0.0))

    def lip(q):   # the mouth opens into four soft lobes
        a = math.atan2(q.y, q.x)
        f = min(1.0, max(0.0, (q.z - 0.178) / 0.02))
        return Vector((q.x * (1 + 0.05 * math.cos(4 * a) * f), q.y * (1 + 0.05 * math.cos(4 * a) * f),
                       q.z + 0.003 * math.cos(4 * a) * f))
    p.lathe([(0.0, 0.0), (0.033, 0.0), (0.035, 0.008), (0.032, 0.012), (0.046, 0.025), (0.056, 0.048), (0.054, 0.073),
             (0.042, 0.098), (0.029, 0.122), (0.022, 0.143), (0.021, 0.16), (0.026, 0.18), (0.036, 0.197), (0.034, 0.2),
             (0.022, 0.184), (0.0, 0.178)], 'Celadon', n=16, M=M, deform=lip, close_ends=False)
    for arc in ((100, 60, 25, 0), (0, -35, -65)):   # ear-shaped handle, in two runs so no tube turns back on itself
        p.tube([M @ Vector((0.03 + 0.042 * math.cos(math.radians(a)), 0.0, 0.118 + 0.05 * math.sin(math.radians(a))))
                for a in arc], 0.0065, 'Celadon', sides=6)
    S = M @ Matrix.Translation((-0.044, 0.0, 0.045)) @ \
        Vector((-0.75, 0.0, 0.66)).to_track_quat('Z', 'Y').to_matrix().to_4x4()                # spout, curving up
    p.lathe([(0.013, 0.0), (0.01, 0.035), (0.0075, 0.07), (0.0065, 0.095), (0.0078, 0.098), (0.006, 0.1),
             (0.0025, 0.097)], 'Celadon', n=8, M=S, deform=lambda q: Vector((q.x, q.y + 0.035 * (q.z / 0.1) ** 2, q.z)))
    cup(p, -0.035, -0.068, 0.034, 0.028, 'RiceWine', 0.021)
    return p.finish('SM_wine', col)


def cola(col):
    """可乐: a glass contour bottle of dark cola with a red label band round its belly, its crimped red cap beside it."""
    p = Part()
    M = Matrix.Translation((-0.012, 0.01, 0.0))
    p.lathe([(0.0, 0.0), (0.025, 0.0), (0.029, 0.004), (0.031, 0.02), (0.028, 0.045), (0.027, 0.06), (0.03, 0.078)],
            'ColaDark', n=14, M=M, close_ends=False)
    p.lathe([(0.03, 0.078), (0.0328, 0.081), (0.0335, 0.1), (0.0328, 0.118), (0.031, 0.121)], 'LabelRed', n=14, M=M,
            close_ends=False)
    p.lathe([(0.031, 0.121), (0.027, 0.134), (0.021, 0.146)], 'ColaDark', n=14, M=M, close_ends=False)
    p.lathe([(0.021, 0.146), (0.015, 0.162), (0.0135, 0.18), (0.0138, 0.19), (0.0152, 0.193), (0.0152, 0.199),
             (0.0125, 0.201), (0.0105, 0.196)], 'BottleGlass', n=14, M=M, close_ends=False)
    p.lathe([(0.0105, 0.196), (0.0, 0.19)], 'ColaDark', n=14, M=M, close_ends=False)

    def crimp(q):   # the skirt of the crown cap, pleated
        k = 1 + 0.05 * math.cos(8 * math.atan2(q.y, q.x)) if q.z < 0.0045 else 1.0
        return Vector((q.x * k, q.y * k, q.z))
    C = Matrix.Translation((0.052, -0.05, 0.007)) @ \
        Vector((0.12, -0.3, 0.95)).to_track_quat('Z', 'Y').to_matrix().to_4x4()                # the cap, tipped up
    p.lathe([(0.0, 0.0015), (0.0145, 0.0005), (0.018, 0.0), (0.0172, 0.004), (0.0145, 0.007), (0.0, 0.007)], 'LabelRed',
            n=16, M=C, deform=crimp, close_ends=False)
    return p.finish('SM_cola', col)


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


ITEMS = [('D01', hubing), ('D02', caimian), ('D03', huntun),
         ('D01_wok', lambda c: hubing(c, True)), ('D02_wok', lambda c: caimian(c, True)),
         ('D03_wok', lambda c: huntun(c, True)), ('flour', flour), ('greens', greens),
         ('pork', pork), ('salt', salt), ('oil', oil), ('scallion', scallion), ('ginger', ginger),
         # plated meat, poultry, tofu and fish
         ('chicken', chicken), ('duck', duck), ('kidney', kidney), ('wing', wing), ('tofu', tofu), ('skin', skin),
         ('fish', fish), ('mandarin_fish', mandarin_fish), ('fish_head', fish_head), ('crab', crab),
         # sacks, parcels, pots and baskets
         ('rice', rice), ('rice_prep', rice_prep), ('pickle_base', pickle_base), ('seafood', seafood),
         ('starch', starch), ('sauerkraut', sauerkraut), ('stock', stock), ('pancake', pancake), ('egg', egg),
         # vegetables, seasoning vessels and drinks
         ('radish', radish), ('gourd', gourd), ('bamboo', bamboo), ('perilla', perilla), ('mushroom', mushroom),
         ('tomato', tomato), ('chili', chili), ('potato', potato), ('garlic', garlic), ('sugar', sugar),
         ('vinegar', vinegar), ('wine', wine), ('cola', cola)]

os.makedirs(os.path.join(OUT, 'renders'), exist_ok=True)
STATS = os.path.join(OUT, 'renders', 'stats.json')
stats = json.load(open(STATS)) if ONLY and os.path.exists(STATS) else {}
for key, build in ITEMS:
    if ONLY and key not in ONLY:
        continue
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
with open(STATS, 'w') as fh:
    json.dump(stats, fh, indent=1)
log('done')
