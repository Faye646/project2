"""做饭界面 as a 三渲二 3D set (style test A), built after 背景.png and 案台 (2).png.

A fixed front camera looks at the kitchen counter: plaster wall with timber frame, a window with
the blue 门帘, shelves with jars on the right; the counter with three small trays (放置区) and one
big tray (食材与调味); the brick stove with the fire mouth and the wok (灶台). The food models from
build_food.py are placed on it. Same toon look as the hall: two-tone ramp + inverted-hull outlines.

    blender -b --factory-startup --python build_cook_view.py -- <out_png>
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
HERE = os.path.dirname(os.path.abspath(__file__))
WC = '--wc' in ARGS   # 水彩 version: painted materials, soft light, cast shadows (EEVEE)
ARGS = [a for a in ARGS if a != '--wc']
OUT = os.path.abspath(ARGS[0]) if ARGS else os.path.join(HERE, 'CookView', 'cook_view_wc.png' if WC else 'cook_view_toon.png')
FOOD = os.path.join(HERE, 'Food')
random.seed(3)

PALETTE = {
    'Plaster':  ('#f1e3c6', '#d9c29c'),
    'Timber':   ('#b8814a', '#8c5e33'),
    'Counter':  ('#d49a5c', '#ad733d'),
    'TrayWood': ('#c78b52', '#9c6535'),
    'CounterTop': ('#d8995a', '#ad733d'),
    'Brick':    ('#c4bcb0', '#9d948a'),
    'Mortar':   ('#8f877d', '#6f685f'),
    'Iron':     ('#4a4541', '#2e2a27'),
    'Cloth':    ('#526fa8', '#3c5588'),
    'ClothPattern': ('#dfe4ee', '#b9c2d4'),
    'Sky':      ('#c7e4f0', '#c7e4f0'),
    'Hill':     ('#a3bda8', '#a3bda8'),
    'Roof':     ('#7a8595', '#7a8595'),
    'Leaf':     ('#a2c17a', '#789a55'),
    'Blossom':  ('#fbf6ea', '#e3dccb'),
    'Floor':    ('#c48a52', '#9d6836'),
    'Porcelain': ('#eef1f2', '#c7d0d6'),
    'BlueGlaze': ('#5a7bb0', '#46629a'),
    'Straw':    ('#dcbf7c', '#b39556'),
    'Chili':    ('#d24a34', '#a33427'),
    'Fire':     ('#ffc15a', '#ff8f2a'),
    'Ember':    ('#6b3a22', '#4a2616'),
}
EMISSIVE = {'Sky', 'Hill', 'Roof', 'Fire'}
LIGHT = Vector((-0.35, -0.75, 0.55)).normalized()   # from the upper left, as the sun in the painting


def srgb(h):
    c = [int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
MATS = {}


def toon(name, lit, shade, emissive=False):
    mat = bpy.data.materials.get('T_' + name) or bpy.data.materials.new('T_' + name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    emit = nt.nodes.new('ShaderNodeEmission')
    if emissive:
        emit.inputs['Color'].default_value = (*srgb(lit), 1)
    else:
        geo = nt.nodes.new('ShaderNodeNewGeometry')
        dot = nt.nodes.new('ShaderNodeVectorMath')
        dot.operation = 'DOT_PRODUCT'
        dot.inputs[1].default_value = LIGHT
        ramp = nt.nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.interpolation = 'CONSTANT'
        ramp.color_ramp.elements[0].color = (*srgb(shade), 1)
        ramp.color_ramp.elements[1].position = 0.02
        ramp.color_ramp.elements[1].color = (*srgb(lit), 1)
        nt.links.new(geo.outputs['Normal'], dot.inputs[0])
        nt.links.new(dot.outputs['Value'], ramp.inputs['Fac'])
        nt.links.new(ramp.outputs['Color'], emit.inputs['Color'])
    nt.links.new(emit.outputs[0], out.inputs['Surface'])
    return mat


if WC:   # richer, warmer colours like the painted kitchen
    PALETTE.update({
        'Plaster': ('#ecd6ae', '#cfae82'), 'Timber': ('#9a5c30', '#6a3a19'), 'Counter': ('#b0672f', '#7d431c'),
        'TrayWood': ('#a35f2e', '#784018'), 'Floor': ('#a86c3a', '#7c4a22'), 'Brick': ('#cfc8bf', '#a39a90'),
        'Mortar': ('#9d958b', '#7a736b'), 'Cloth': ('#4a619a', '#35477a'), 'Straw': ('#d6b36c', '#a8864a'),
    })
    sys.path.insert(0, HERE)
    import wc_materials
    TEXDIR = os.path.join(HERE, 'CookView', 'tex')   # patches cut from 背景.png / 案台 (2).png
    TEX = {'Plaster': ('plaster', 0.55), 'Floor': ('floor', 0.35), 'Timber': ('post', 1.2), 'Counter': ('wood', 1.1),
           'TrayWood': ('countertop', 1.4, 1.15, 0.92), 'CounterTop': ('countertop', 0.8, 1.15, 0.92), 'Brick': ('brick', 2.2), 'Mortar': ('brick', 2.2),
           'Porcelain': ('bluewhite', 6.0), 'BlueGlaze': ('glaze', 6.0), 'Straw': ('basket', 5.0)}
    _imgs = {}

    def _img(key):
        if key not in _imgs:
            _imgs[key] = bpy.data.images.load(os.path.join(TEXDIR, key + '.png'))
        return _imgs[key]

    def toon(name, lit, shade, emissive=False):
        t = TEX.get(name)
        if not t:
            return wc_materials.painted(name, lit, shade, srgb, emissive)
        extra = dict(zip(('sat', 'val'), t[2:]))
        return wc_materials.painted(name, lit, shade, srgb, emissive, tex=_img(t[0]), tex_scale=t[1], **extra)

    def image_card(name, key, x0, x1, y, z0, z1, glow=False):
        """A flat card carrying a piece of the painting, facing the camera (-y)."""
        bm = bmesh.new()
        vs = [bm.verts.new(v) for v in ((x0, y, z0), (x1, y, z0), (x1, y, z1), (x0, y, z1))]
        f = bm.faces.new(vs)
        uvl = bm.loops.layers.uv.new()
        for loop, uv in zip(f.loops, ((0, 0), (1, 0), (1, 1), (0, 1))):
            loop[uvl].uv = uv
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.materials.append(wc_materials.painted(name, '#ffffff', '#ffffff', srgb, image=_img(key), glow=glow))
        ob = bpy.data.objects.new(name, me)
        scene.collection.objects.link(ob)
        return ob
for k, (a, b) in PALETTE.items():
    MATS[k] = toon(k, a, b, k in EMISSIVE)
food_pal = json.load(open(os.path.join(FOOD, 'palette_food.json'), encoding='utf-8'))['toon']
for k, v in food_pal.items():
    MATS.setdefault(k, toon(k, v['lit'], v['shade']))

OBJS = []


def mesh_obj(name, bm, mat, outline=0.006):
    me = bpy.data.meshes.new(name)
    bm.normal_update()
    bm.to_mesh(me)
    bm.free()
    me.shade_smooth()
    me.set_sharp_from_angle(angle=math.radians(50))
    me.materials.append(MATS[mat])
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    OBJS.append((ob, outline))
    return ob


def box(name, x0, x1, y0, y1, z0, z1, mat, r=0.012, outline=0.006):
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector(((x0 + x1) / 2 + v.co.x * (x1 - x0), (y0 + y1) / 2 + v.co.y * (y1 - y0), (z0 + z1) / 2 + v.co.z * (z1 - z0)))
    if r > 0:
        r = min(r, 0.45 * min(x1 - x0, y1 - y0, z1 - z0))
        bmesh.ops.bevel(bm, geom=bm.edges[:], offset=r, offset_type='OFFSET', segments=2, profile=0.5, affect='EDGES', clamp_overlap=True)
    return mesh_obj(name, bm, mat, outline)


def lathe(name, prof, c, mat, n=20, outline=0.004, M=None):
    bm = bmesh.new()
    rings = []
    for rad, z in prof:
        if rad < 1e-6:
            rings.append([bm.verts.new(Vector((0, 0, z)))])
        else:
            rings.append([bm.verts.new(Vector((rad * math.cos(2 * math.pi * k / n), rad * math.sin(2 * math.pi * k / n), z))) for k in range(n)])
    for ra, rb in zip(rings, rings[1:]):
        for k in range(n):
            if len(ra) == 1:
                bm.faces.new((ra[0], rb[(k + 1) % n], rb[k]))
            elif len(rb) == 1:
                bm.faces.new((ra[k], ra[(k + 1) % n], rb[0]))
            else:
                bm.faces.new((ra[k], ra[(k + 1) % n], rb[(k + 1) % n], rb[k]))
    T = Matrix.Translation(Vector(c)) @ (M or Matrix())
    for v in bm.verts:
        v.co = T @ v.co
    return mesh_obj(name, bm, mat, outline)


def blob(name, c, r, mat, squash=(1, 1, 1), outline=0.003):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=10, v_segments=6, radius=1.0)
    for v in bm.verts:
        v.co = Vector(c) + Vector((v.co.x * r * squash[0], v.co.y * r * squash[1], v.co.z * r * squash[2]))
    return mesh_obj(name, bm, mat, outline)


# ---------------------------------------------------------------- room (y grows away from the camera)
WALL_Y = 1.35
box('Floor', -6, 6, -5, WALL_Y, -0.04, 0.0, 'Floor', r=0, outline=0)
for k in range(-24, 25):   # plank seams
    box(f'Seam{k}', k * 0.25 - 0.004, k * 0.25 + 0.004, -5, WALL_Y, 0.0, 0.002, 'Timber', r=0, outline=0)
for x in (-3.6, -2.4, -1.35, 0.45, 1.45, 2.55, 3.4):   # posts
    box(f'Post{x}', x - 0.07, x + 0.07, WALL_Y - 0.08, WALL_Y, 0, 3.2, 'Timber', r=0.02)
for z in (0.1, 0.95, 3.0):                 # sill, dado rail, head beam
    box(f'Rail{z}', -6, 6, WALL_Y - 0.06, WALL_Y, z - 0.05, z + 0.05, 'Timber', r=0.015)
# window between the posts at -1.35 and 0.45
wx0, wx1, wz0, wz1 = -1.2, 0.3, 1.45, 2.55
for (a0, a1, b0, b1) in ((-6, wx0, 0, 3.4), (wx1, 6, 0, 3.4), (wx0, wx1, 0, wz0), (wx0, wx1, wz1, 3.4)):   # wall around the window
    box(f'Wall{a0}{b0}', a0, a1, WALL_Y, WALL_Y + 0.1, b0, b1, 'Plaster', r=0, outline=0)
sky = box('Sky', wx0, wx1, WALL_Y + 0.4, WALL_Y + 0.41, wz0, wz1, 'Sky', r=0, outline=0)
if WC:   # the view out of the window is the one painted in 背景.png
    img = bpy.data.images.load(os.path.join(os.path.dirname(HERE), '背景.png'))
    view_mat = wc_materials.painted('WindowView', '#ffffff', '#ffffff', srgb, image=img)
    me = sky.data
    uv = me.uv_layers.new()
    # crop of the window in the painting, in UV space (x 390–1000, y 130–345 of 1672 × 941, v from the bottom)
    u0, u1, v0, v1 = 390 / 1672, 1000 / 1672, 1 - 345 / 941, 1 - 130 / 941
    xs = [v.co.x for v in me.vertices]
    zs = [v.co.z for v in me.vertices]
    for poly in me.polygons:
        for li in poly.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            uv.data[li].uv = (u0 + (co.x - min(xs)) / (max(xs) - min(xs)) * (u1 - u0),
                              v0 + (co.z - min(zs)) / (max(zs) - min(zs)) * (v1 - v0))
    me.materials[0] = view_mat
if not WC:
    box('Hills', wx0, wx1, WALL_Y + 0.35, WALL_Y + 0.36, wz0, wz0 + 0.45, 'Hill', r=0, outline=0)
if not WC:
    box('Roofs', wx0, wx1, WALL_Y + 0.3, WALL_Y + 0.31, wz0, wz0 + 0.25, 'Roof', r=0, outline=0)
for z in (wz0, wz1):
    box(f'WinH{z}', wx0 - 0.08, wx1 + 0.08, WALL_Y - 0.1, WALL_Y, z - 0.05, z + 0.05, 'Timber', r=0.015)
for x in (wx0, wx0 + (wx1 - wx0) * 0.2, wx1):
    box(f'WinV{x}', x - 0.04, x + 0.04, WALL_Y - 0.1, WALL_Y, wz0, wz1, 'Timber', r=0.012)
for i in range(4):   # 门帘 with a white flower
    x0 = wx0 - 0.05 + i * (wx1 - wx0 + 0.1) / 4
    x1 = x0 + (wx1 - wx0 + 0.1) / 4 - 0.02
    box(f'Curtain{i}', x0, x1, WALL_Y - 0.14, WALL_Y - 0.12, 2.28, 2.75, 'Cloth', r=0.006, outline=0.004)
    blob(f'Flower{i}', ((x0 + x1) / 2, WALL_Y - 0.145, 2.5), 0.05, 'ClothPattern', squash=(1, 0.08, 1), outline=0)
box('CurtainRod', wx0 - 0.1, wx1 + 0.1, WALL_Y - 0.15, WALL_Y - 0.1, 2.75, 2.8, 'Timber', r=0.01)
for i in range(0 if WC else 6):   # blossom branch outside
    blob(f'Blossom{i}', (wx1 - 0.25 + 0.08 * math.cos(i * 1.7), WALL_Y + 0.2, wz0 + 0.65 + 0.2 * math.sin(i * 1.3)), 0.07,
         'Leaf' if i % 2 else 'Blossom', squash=(1, 0.05, 1), outline=0)
# right: two shelves with jars, a woven sieve and a hanging chili string
for z in (1.35, 2.25):
    box(f'Shelf{z}', 0.65, 1.95, WALL_Y - 0.3, WALL_Y - 0.08, z - 0.03, z + 0.03, 'Timber', r=0.01)
    for j, x in enumerate((0.8, 1.05, 1.3, 1.6, 1.8)):
        mat = ('Porcelain', 'Straw', 'BlueGlaze', 'Porcelain', 'Straw')[(j + int(z)) % 5]
        h = 0.14 + 0.05 * ((j * 7 + int(z * 10)) % 3)
        lathe(f'Jar{z}{j}', [(0.0, 0), (0.07, 0), (0.09, h * 0.4), (0.07, h * 0.9), (0.045, h), (0.0, h)], (x, WALL_Y - 0.19, z + 0.03), mat, n=14)
if WC:
    image_card('Sieve', 'sieve', 1.97, 2.53, WALL_Y - 0.03, 2.05, 2.72)
else:
    lathe('Sieve', [(0.0, 0), (0.28, 0), (0.28, 0.03), (0.0, 0.03)], (2.25, WALL_Y - 0.05, 2.35), 'Straw', n=24,
          M=Matrix.Rotation(math.pi / 2, 4, 'X'))
if WC:
    image_card('ChiliString', 'chili', 1.88, 2.22, WALL_Y - 0.06, 1.55, 2.12)
else:
    for k in range(5):
        blob(f'Chili{k}', (2.05, WALL_Y - 0.08, 2.1 - k * 0.1), 0.045, 'Chili', squash=(0.8, 0.8, 1.5))
# left: a small shelf with bowls
box('ShelfL', -2.95, -2.1, WALL_Y - 0.3, WALL_Y - 0.08, 1.35, 1.41, 'Timber', r=0.01)
for j in range(3):
    lathe(f'Bowl{j}', [(0.0, 0), (0.06, 0), (0.1, 0.06), (0.0, 0.06)], (-2.7, WALL_Y - 0.19, 1.41 + j * 0.045), 'Porcelain', n=14)

# more of the clutter the painted kitchen has
if WC:
    image_card('Scroll', 'scroll', -2.07, -1.7, WALL_Y - 0.03, 1.68, 2.52)
else:
  box('ScrollPaper', -2.05, -1.72, WALL_Y - 0.03, WALL_Y - 0.02, 1.75, 2.45, 'ClothPattern', r=0, outline=0.003)
if not WC:
  box('ScrollTop', -2.09, -1.68, WALL_Y - 0.05, WALL_Y - 0.02, 2.45, 2.49, 'Timber', r=0.01, outline=0.003)
if not WC:
  box('ScrollBottom', -2.09, -1.68, WALL_Y - 0.05, WALL_Y - 0.02, 1.71, 1.75, 'Timber', r=0.01, outline=0.003)
if not WC:
  blob('ScrollInk', (-1.885, WALL_Y - 0.035, 2.1), 0.09, 'Timber', squash=(0.6, 0.05, 1.8), outline=0)
lathe('ChopCup', [(0.0, 0), (0.06, 0), (0.065, 0.16), (0.0, 0.16)], (-2.35, WALL_Y - 0.19, 1.41), 'LightWood', n=12)
for k in range(5):
    box(f'Chop{k}', -2.39 + k * 0.018, -2.38 + k * 0.018, WALL_Y - 0.2, WALL_Y - 0.19, 1.45, 1.72, 'Timber', r=0.003, outline=0.002)
lathe('Ladle', [(0.0, 0), (0.07, 0.01), (0.075, 0.05), (0.0, 0.05)], (0.6, WALL_Y - 0.1, 1.55), 'Iron', n=12,
      M=Matrix.Rotation(math.pi / 2, 4, 'X'))
box('LadleHandle', 0.585, 0.615, WALL_Y - 0.12, WALL_Y - 0.09, 1.6, 2.05, 'Timber', r=0.008, outline=0.003)
for k in range(6):   # firewood beside the stove
    lathe(f'Wood{k}', [(0.055, -0.22), (0.055, 0.22)], (0, 0, 0), 'LightWood', n=8,
          M=Matrix.Translation((2.45 + (k % 3) * 0.12 + (k // 3) * 0.06, 0.25, 0.055 + (k // 3) * 0.1)) @ Matrix.Rotation(math.pi / 2, 4, 'X'))
lathe('Basket', [(0.0, 0), (0.16, 0), (0.2, 0.22), (0.18, 0.22), (0.0, 0.02)], (-3.1, 0.35, 0), 'Straw', n=16)
for k in range(3):
    blob(f'BasketVeg{k}', (-3.12 + k * 0.08, 0.35, 0.22), 0.07, 'Greens' if 'Greens' in MATS else 'Leaf')

# ---------------------------------------------------------------- counter (放置区 + 食材与调味)
CY0, CY1, CZ = 0.0, 0.75, 0.85
box('CounterBody', -2.75, 0.85, CY0 + 0.05, CY1, 0, CZ - 0.06, 'Counter', r=0.02)
box('CounterTop', -2.8, 0.9, CY0 - 0.02, CY1, CZ - (0.11 if WC else 0.07), CZ, 'CounterTop' if WC else 'Counter', r=0.025)   # a thick top slab
for i, (x0, x1) in enumerate(((-2.6, -2.0), (-1.9, -1.4), (-1.3, -0.8))):
    box(f'Door{i}', x0, x1, CY0 + 0.02, CY0 + 0.05, 0.12, CZ - 0.16, 'Counter', r=0.01)
box('Drawer1', -0.65, 0.65, CY0 + 0.02, CY0 + 0.05, 0.45, CZ - 0.16, 'Counter', r=0.01)
box('Drawer2', -0.65, 0.65, CY0 + 0.02, CY0 + 0.05, 0.12, 0.4, 'Counter', r=0.01)
TRAYS = [(-2.62, -2.07), (-2.0, -1.45), (-1.38, -0.83)]
for i, (x0, x1) in enumerate(TRAYS):   # 放置区: three small trays
    y0, y1 = 0.18, 0.6
    box(f'Tray{i}', x0, x1, y0, y1, CZ, CZ + 0.012, 'TrayWood', r=0.006, outline=0.003)
    for (a0, a1, b0, b1) in ((x0, x1, y0, y0 + 0.03), (x0, x1, y1 - 0.03, y1), (x0, x0 + 0.03, y0, y1), (x1 - 0.03, x1, y0, y1)):
        box(f'TrayRim{i}{a0}{b0}', a0, a1, b0, b1, CZ, CZ + 0.035, 'TrayWood', r=0.01, outline=0.003)
BX0, BX1, BY0, BY1 = -0.65, 0.78, 0.14, 0.66      # 食材与调味: the big tray
box('Board', BX0, BX1, BY0, BY1, CZ, CZ + 0.012, 'TrayWood', r=0.006, outline=0.003)
for (a0, a1, b0, b1) in ((BX0, BX1, BY0, BY0 + 0.03), (BX0, BX1, BY1 - 0.03, BY1), (BX0, BX0 + 0.03, BY0, BY1), (BX1 - 0.03, BX1, BY0, BY1)):
    box(f'BoardRim{a0}{b0}', a0, a1, b0, b1, CZ, CZ + 0.035, 'TrayWood', r=0.01, outline=0.003)
if WC:
    image_card('Towel', 'towel', -2.72, -2.38, -0.035, 0.28, CZ + 0.02)
else:
    box('Towel', -2.86, -2.62, -0.02, 0.02, 0.35, CZ - 0.02, 'Cloth', r=0.008)

# ---------------------------------------------------------------- stove (灶台)
SX0, SX1, SY0, SY1, SZ = 0.95, 2.3, 0.0, 1.0, 0.95
for (a0, a1, b0, b1, y0) in ((SX0 + 0.02, 1.3, 0, SZ, SY0 + 0.02), (1.95, SX1 - 0.02, 0, SZ, SY0 + 0.02),
                              (1.3, 1.95, 3 * SZ / 6, SZ, SY0 + 0.02), (1.3, 1.95, 0, 3 * SZ / 6, SY0 + 0.32)):
    box(f'StoveCore{a0}{b0}', a0, a1, y0, SY1, b0, b1, 'Mortar', r=0, outline=0.006)   # hollow behind the fire mouth
rows, bh = 6, SZ / 6
for r_ in range(rows):   # brick courses on the front and the top ring
    z0 = r_ * bh
    n = 4
    off = 0.5 if r_ % 2 else 0
    xs = sorted({SX0, SX1, *[SX0 + (k + off) * (SX1 - SX0) / n for k in range(n + 1) if SX0 < SX0 + (k + off) * (SX1 - SX0) / n < SX1]})
    for a, b in zip(xs, xs[1:]):
        if r_ < 3 and 1.3 < (a + b) / 2 < 1.95:
            continue   # the fire mouth
        box(f'Brick{r_}{a:.2f}', a + 0.006, b - 0.006, SY0, SY0 + 0.06, z0 + 0.006, z0 + bh - 0.006, 'Brick', r=0.02, outline=0.004)
box('StoveTop', SX0, SX1, SY0, SY1, SZ - 0.02, SZ + 0.06, 'Brick', r=0.03)
if not WC:
    box('MouthBack', 1.35, 1.9, SY0 + 0.25, SY0 + 0.3, 0.0, 3 * bh, 'Ember', r=0, outline=0)
for k in range(0 if WC else 4):
    blob(f'Log{k}', (1.45 + k * 0.12, SY0 + 0.15, 0.08), 0.05, 'Ember', squash=(1.6, 0.8, 0.8))
for k in range(0 if WC else 5):
    blob(f'Flame{k}', (1.42 + k * 0.1, SY0 + 0.14, 0.2 + 0.05 * (k % 2)), 0.08, 'Fire', squash=(0.8, 0.5, 1.8), outline=0)
if WC:   # the painted arched fire mouth with its fire, set into the brick face
    image_card('FireMouth', 'firemouth', 1.2, 2.05, -0.004, 0.0, 0.66, glow=True)
WOK = Vector(((SX0 + SX1) / 2, 0.5, SZ + 0.06))
lathe('Wok', [(0.0, -0.02), (0.18, 0.0), (0.33, 0.1), (0.36, 0.15), (0.345, 0.155), (0.31, 0.11), (0.16, 0.02), (0.0, 0.0)],
      WOK, 'Iron', n=28, outline=0.005)
for s in (-1, 1):
    lathe(f'WokHandle{s}', [(0.035, -0.012), (0.045, 0.0), (0.035, 0.012), (0.025, 0.0), (0.035, -0.012)],
          WOK + Vector((s * 0.39, 0, 0.14)), 'Iron', n=12, M=Matrix.Rotation(math.pi / 2, 4, 'Y'))

# ---------------------------------------------------------------- food from build_food.py


def place(key, pos, scale=1.0, rot=0.0):
    path = os.path.join(FOOD, f'SM_{key}.blend')
    with bpy.data.libraries.load(path) as (src, dst):
        dst.objects = [n for n in src.objects if n.startswith('SM_')]
    for ob in dst.objects:
        scene.collection.objects.link(ob)
        ob.location = Vector(pos)
        ob.rotation_euler = (0, 0, rot)
        ob.scale = (scale, scale, scale)
        ob.data = ob.data.copy()
        for i, m in enumerate(ob.data.materials):
            key_ = (m.name[2:] if m.name.startswith('M_') else m.name).split('.')[0]
            if key_ in MATS:
                ob.data.materials[i] = MATS[key_]
        OBJS.append((ob, 0.0018 * scale))


S = 2.0   # food is shown a little larger than life so it reads at phone size
top = CZ + 0.012
for i, (key, k) in enumerate((('flour', 0.75), ('greens', 1.0), ('pork', 1.0))):
    place(key, (BX0 + 0.27 + i * 0.47, 0.56, top), S * k, rot=0.2)
for i, (key, k) in enumerate((('salt', 1.1), ('oil', 1.0), ('scallion', 0.85), ('ginger', 1.0))):
    place(key, (BX0 + 0.2 + i * 0.35, 0.24, top), S * k * 0.9, rot=0.3)
place('D02', ((TRAYS[0][0] + TRAYS[0][1]) / 2, 0.38, top), S)
place('D01_wok', (WOK.x, WOK.y, WOK.z + 0.04), S * 1.2)

# ---------------------------------------------------------------- outlines, camera, render
line = bpy.data.materials.new('T_Line')
line.use_backface_culling = True
nt = line.node_tree
nt.nodes.clear()
em = nt.nodes.new('ShaderNodeEmission')
em.inputs['Color'].default_value = (*srgb('#6b4630' if WC else '#4e321f'), 1)
geo = nt.nodes.new('ShaderNodeNewGeometry')
mix = nt.nodes.new('ShaderNodeMixShader')
nt.links.new(geo.outputs['Backfacing'], mix.inputs['Fac'])
nt.links.new(em.outputs[0], mix.inputs[1])
nt.links.new(nt.nodes.new('ShaderNodeBsdfTransparent').outputs[0], mix.inputs[2])
nt.links.new(mix.outputs[0], nt.nodes.new('ShaderNodeOutputMaterial').inputs['Surface'])
dg = bpy.context.evaluated_depsgraph_get()
for ob, w in OBJS:
    if w <= 0:
        continue
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
    me.transform(ob.matrix_world)
    me.materials.clear()
    me.materials.append(line)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bm.normal_update()
    for v in bm.verts:
        v.co += v.normal * (w * 0.75 if WC else w)
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    scene.collection.objects.link(bpy.data.objects.new(ob.name + '_line', me))

cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera'))
scene.collection.objects.link(cam)
scene.camera = cam
cam.data.lens = 30
cam.location = (-0.3, -4.1, 2.0)
cam.rotation_euler = (math.radians(80), 0, 0)
if WC:   # a little from above, like the painting: the counter top and trays read clearly
    cam.data.lens = 26
    cam.data.lens = 22
    cam.location = (-0.35, -2.75, 2.4)
    cam.rotation_euler = (math.radians(68), 0, 0)
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
scene.view_settings.view_transform = 'Standard'
if WC:   # sunlight from the upper left, a soft sky fill; EEVEE for Shader-to-RGB
    sun = bpy.data.objects.new('Sun', bpy.data.lights.new('Sun', 'SUN'))
    sun.data.energy = 3.2
    sun.data.angle = 0.12
    sun.rotation_euler = Vector((0.5, 0.65, -0.6)).normalized().to_track_quat('-Z', 'Y').to_euler()   # from front-left-up
    scene.collection.objects.link(sun)
    scene.world = bpy.data.worlds.new('World')
    scene.world.use_nodes = True
    scene.world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.35, 0.33, 0.3, 1)
    scene.render.engine = 'BLENDER_EEVEE'
    scene.eevee.taa_render_samples = 32
    scene.render.filepath = OUT
    bpy.ops.render.render(write_still=True)
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.dirname(OUT), 'cook_view_wc.blend'))
    print('[cookview] rendered', OUT, flush=True)
    sys.exit(0)
scene.render.engine = 'CYCLES'
scene.cycles.device = 'CPU'
scene.cycles.samples = 16
scene.cycles.use_denoising = False
scene.cycles.filter_width = 1.0
os.makedirs(os.path.dirname(OUT), exist_ok=True)
scene.render.filepath = OUT
bpy.ops.render.render(write_still=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(os.path.dirname(OUT), 'cook_view.blend'))
print('[cookview] rendered', OUT, flush=True)
