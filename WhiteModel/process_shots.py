"""Blender screenshots of the 500-face 纹璃宫灯 for a 白模 → 三渲二 → 水彩 process figure.

The three looks are set up the way they would be worked on in Blender:
  白模    Layout workspace, Solid shading with the wireframe overlay and scene statistics.
  三渲二  Shading workspace, EEVEE rendered view through the render camera. Each material is a
          two-tone ramp against a fixed light; the outlines are inverted hulls (collection "Outline").
  水彩    Compositing workspace. The node tree "Watercolor" is the recipe of watercolor.py rebuilt
          from compositor nodes, painting over the passes in renders/passes; the Viewer shows its result.

    blender --factory-startup -p 0 0 2560 1440 --no-window-focus SM_WenliGongdeng_500.blend --python process_shots.py -- [out_dir] [white,toon,watercolor]
Opens a Blender window, takes 2560x1440 screenshots 纹璃宫灯_1_白模.png ... into out_dir (default the project2 folder) and quits; the UI
scale is set for 150 % Windows scaling (env SHOT_UI_SCALE overrides it). The passes come from
build_wenli_gongdeng.py --low500 --watercolor. In the background (-b) it only builds the compositor tree
and renders it to <out_dir>/watercolor_comp.png, to compare with renders/watercolor_500.png.
The .blend itself is never saved.
"""
import math
import os
import sys
import traceback

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = os.path.abspath(ARGS[0]) if ARGS else os.path.dirname(HERE)  # the project2 folder
SHOTS = ARGS[1].split(',') if len(ARGS) > 1 else ['white', 'toon', 'watercolor']
PASSES = os.path.join(HERE, 'renders', 'passes')
TAG = '_500'


def log(msg):
    print(f'[process] {msg}', flush=True)


def to_lin(c):
    return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def srgb(hex_color):
    return tuple(to_lin(int(hex_color[i:i + 2], 16) / 255) for i in (1, 3, 5))


# the colours of build_wenli_gongdeng.py's toon preview and watercolor.py
STONE, WOOD, GLASS = ('#f0dcb2', '#d6b484'), ('#9b634a', '#6e4130'), ('#d3eadf', '#a9cfc0')
LINE = '#4a2e22'
PAPER, INK = srgb('#fafde0'), srgb(LINE)
LIGHT = Vector((-0.3, -0.8, 0.52)).normalized()
BLUR_K = 3.03  # Blender's Gaussian blur size per sigma (measured)
NOISE_K = 1.5  # widens Blender's Perlin fBm to the spread of watercolor.py's value noise (std 0.105 -> 0.155)


# ---------------------------------------------------------------- compositor: watercolor.py as nodes

class Graph:
    """Wires nodes into `tree` like expressions; arguments are sockets or constants."""

    def __init__(self, tree, ref=None):
        self.tree = tree
        self.ref = ref  # an image socket that gives procedural textures their size

    def new(self, kind, **props):
        n = self.tree.nodes.new(kind)
        n.select = False  # new nodes start selected, which would outline the whole tree in the screenshot
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def put(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.tree.links.new(v, sock)
        else:
            sock.default_value = v

    def math(self, op, a, b=0.0, c=0.0, clamp=False):
        n = self.new('ShaderNodeMath', operation=op, use_clamp=clamp)
        for s, v in zip(n.inputs, (a, b, c)):
            self.put(s, v)
        return n.outputs[0]

    def vec(self, op, a, b=(0.0, 0.0, 0.0), c=(0.0, 0.0, 0.0), scale=1.0):
        n = self.new('ShaderNodeVectorMath', operation=op)
        for s, v in zip(n.inputs, (a, b, c, scale)):
            self.put(s, v)
        return n.outputs['Value' if op == 'DOT_PRODUCT' else 'Vector']

    def smooth(self, e0, e1, x):
        n = self.new('ShaderNodeMapRange', data_type='FLOAT', interpolation_type='SMOOTHSTEP', clamp=True)
        for s, v in zip(n.inputs, (x, e0, e1, 0.0, 1.0)):
            self.put(s, v)
        return n.outputs['Result']

    def mix(self, fac, a, b, kind='RGBA'):
        n = self.new('ShaderNodeMix', data_type=kind, clamp_factor=False)
        ia, ib, o = {'FLOAT': (2, 3, 0), 'VECTOR': (4, 5, 1), 'RGBA': (6, 7, 2)}[kind]
        self.put(n.inputs[0], fac)
        self.put(n.inputs[ia], a)
        self.put(n.inputs[ib], b)
        return n.outputs[o]

    def blur(self, img, sigma):
        """Gaussian matching watercolor.py's blur(a, sigma) (three box passes)."""
        r = max(1, round((math.sqrt(4 * sigma * sigma + 1) - 1) / 2))
        size = BLUR_K * math.sqrt(((2 * r + 1) ** 2 - 1) / 4)
        n = self.new('CompositorNodeBlur')
        n.inputs['Size'].default_value = (size, size)
        self.put(n.inputs['Image'], img)
        return n.outputs['Image']

    def shift(self, img, x, y):
        n = self.new('CompositorNodeTranslate')
        n.inputs['X'].default_value, n.inputs['Y'].default_value = x, y
        self.put(n.inputs['Image'], img)
        return n.outputs['Image']

    def displace(self, img, d):
        n = self.new('CompositorNodeDisplace')
        self.put(n.inputs['Image'], img)
        self.put(n.inputs['Displacement'], d)
        return n.outputs['Image']

    def sep(self, img):
        n = self.new('CompositorNodeSeparateColor')
        self.put(n.inputs['Image'], img)
        return n.outputs

    def xyz(self, x, y, z=0.0):
        n = self.new('ShaderNodeCombineXYZ')
        for s, v in zip(n.inputs, (x, y, z)):
            self.put(s, v)
        return n.outputs[0]

    def noise(self, cell, octaves, seed):
        """Fractal noise in about [0, 1] with features about `cell` pixels across."""
        co = self.new('CompositorNodeImageCoordinates')
        self.put(co.inputs['Image'], self.ref)
        p = self.vec('MULTIPLY_ADD', co.outputs['Pixel'], (1 / cell,) * 3, (seed * 17.31, seed * 29.73, 0.0))
        n = self.new('ShaderNodeTexNoise', noise_dimensions='2D', normalize=True)
        for k, v in (('Scale', 1.0), ('Detail', octaves - 1.0), ('Roughness', 0.5), ('Lacunarity', 2.0)):
            n.inputs[k].default_value = v
        self.put(n.inputs['Vector'], p)
        return self.math('MULTIPLY_ADD', n.outputs['Factor'], NOISE_K, 0.5 - 0.5 * NOISE_K)


SOCKET = {'color': 'NodeSocketColor', 'float': 'NodeSocketFloat', 'vector': 'NodeSocketVector'}
HEIGHT = {'CompositorNodeBlur': 200, 'ShaderNodeMapRange': 250, 'ShaderNodeTexNoise': 300, 'ShaderNodeMix': 210,
          'CompositorNodeTranslate': 230, 'CompositorNodeDisplace': 210, 'ShaderNodeVectorMath': 190,
          'CompositorNodeSeparateColor': 170}


def arrange(tree):
    """Columns by longest path from the inputs, so a group opens as a readable left-to-right flow."""
    preds = {n: [] for n in tree.nodes}
    for link in tree.links:
        preds[link.to_node].append(link.from_node)
    depth = {}

    def d(n):
        if n not in depth:
            depth[n] = max((d(p) + 1 for p in preds[n]), default=0)
        return depth[n]

    for n in tree.nodes:
        d(n)
    last = max(depth.values()) + 1
    for n in tree.nodes:
        if n.bl_idname == 'NodeGroupOutput':
            depth[n] = last
    cols = {}
    for n in tree.nodes:
        cols.setdefault(depth[n], []).append(n)
    for k, col in cols.items():
        heights = [HEIGHT.get(n.bl_idname, 160) for n in col]
        y = (sum(heights) + 40 * (len(col) - 1)) / 2
        for n, h in zip(col, heights):
            n.location = (k * 240, y)
            y -= h + 40


def group(name, inputs, outputs, body, ref=None):
    """Node group `name` whose outputs are body(graph, input sockets)."""
    tree = bpy.data.node_groups.new(name, 'CompositorNodeTree')
    for key, kind in inputs:
        tree.interface.new_socket(key, in_out='INPUT', socket_type=SOCKET[kind])
    for key, kind in outputs:
        tree.interface.new_socket(key, in_out='OUTPUT', socket_type=SOCKET[kind])
    g = Graph(tree)
    gi, go = g.new('NodeGroupInput'), g.new('NodeGroupOutput')
    ins = {key: gi.outputs[key] for key, _ in inputs}
    g.ref = ins.get(ref)
    res = body(g, ins)
    for key, _ in outputs:
        tree.links.new(res[key], go.inputs[key])
    arrange(tree)
    return tree


def paper(g, i):
    """Paper grain: fine tooth plus large, faint unevenness."""
    grain = g.math('ADD', g.math('MULTIPLY_ADD', g.noise(4, 3, 1), 0.05, 1 - 0.025),
                   g.math('MULTIPLY_ADD', g.noise(240, 3, 2), 0.05, -0.025))
    return {'Paper': g.vec('SCALE', PAPER, scale=grain), 'Grain': grain}


def wash_drift(g, i):
    """The wash drifts a few pixels against the ink, and takes the drawing's flat lit / shadow colours."""
    drift = g.xyz(g.math('MULTIPLY_ADD', g.noise(90, 3, 3), 6.0, -3.0),
                  g.math('MULTIPLY_ADD', g.noise(90, 3, 4), 6.0, -3.0))
    fill = g.displace(i['Fill'], drift)
    alpha = g.sep(fill)['Alpha']
    ids = g.displace(i['IDs'], drift)
    lit = g.displace(i['Lit'], drift)
    wash = g.vec('DIVIDE', fill, g.math('MAXIMUM', alpha, 1e-4))  # the glass keeps its see-through fill
    lit_soft = g.blur(lit, 2.0)
    m = g.sep(ids)
    for k, (c_lit, c_shade) in (('Red', STONE), ('Green', WOOD)):
        c_lit, c_shade = srgb(c_lit), srgb(c_shade)
        c_shade = tuple(s + 0.3 * (l - s) for l, s in zip(c_lit, c_shade))  # shadows are a light glaze
        wash = g.mix(m[k], wash, g.mix(lit_soft, (*c_shade, 1.0), (*c_lit, 1.0)))
    return {'Wash': wash, 'Coverage': g.smooth(0.15, 0.65, g.blur(alpha, 1.2)),
            'IDs': ids, 'Lit': lit, 'Alpha': alpha, 'Drift': drift}


def ink_lines(g, i):
    """Outlines, plus a line where a left-facing surface turns into a right-facing one."""
    inner = g.smooth(0.97, 1.0, g.blur(i['Alpha'], 2.0))
    n = g.new('ShaderNodeSeparateXYZ')
    g.put(n.inputs[0], g.vec('MULTIPLY_ADD', i['Normal'], (2.0,) * 3, (-1.0,) * 3))
    nx = g.blur(n.outputs['X'], 1.0)
    slope = g.math('MULTIPLY', g.math('SUBTRACT', g.shift(nx, -1, 0), g.shift(nx, 1, 0)), 0.5)
    ratio = g.math('DIVIDE', g.math('ABSOLUTE', nx), g.math('MAXIMUM', slope, 1e-3))
    corner = g.math('MULTIPLY', g.math('MULTIPLY', g.math('SUBTRACT', 1.0, g.smooth(1.5, 3.5, ratio)),
                                       g.math('GREATER_THAN', slope, 0.008)), inner)
    ink = g.math('MAXIMUM', i['Lines'], corner)
    glass = g.math('GREATER_THAN', g.sep(g.blur(i['IDs'], 3.0))['Blue'], 0.05)
    behind = g.math('MULTIPLY', g.math('SUBTRACT', g.math('SUBTRACT', i['Lines All'], i['Lines']), 0.1, clamp=True), glass)
    return {'Ink': ink, 'Behind': behind, 'Near Ink': g.smooth(0.02, 0.2, g.blur(ink, 5.0)), 'Inner': inner}


def edge_darkening(g, i):
    """Pigment pools where each wash, and each shadow, ends."""
    ids = g.vec('DOT_PRODUCT', g.vec('MAXIMUM', g.vec('SUBTRACT', i['IDs'], g.blur(i['IDs'], 4.0))), (1.0,) * 3)
    shade = g.math('MULTIPLY', g.math('SUBTRACT', 1.0, i['Lit']), i['Alpha'])
    edge = g.math('ADD', ids, g.math('MAXIMUM', g.math('SUBTRACT', shade, g.blur(shade, 3.0)), 0.0))
    return {'Edge': g.math('MULTIPLY', edge, g.math('SUBTRACT', 1.0, i['Near Ink']))}  # ink carries the edge


def lit_edges(g, i):
    """Bare paper left along the lit rounded edges."""
    n = g.vec('MULTIPLY_ADD', i['Normal'], (2.0,) * 3, (-1.0,) * 3)
    gx = g.vec('SUBTRACT', g.shift(n, -2, 0), g.shift(n, 2, 0))
    gy = g.vec('SUBTRACT', g.shift(n, 0, -2), g.shift(n, 0, 2))
    grad = g.math('SQRT', g.math('ADD', g.vec('DOT_PRODUCT', gx, gx), g.vec('DOT_PRODUCT', gy, gy)))
    spark = g.math('MULTIPLY', g.math('MULTIPLY', g.smooth(0.35, 0.9, grad), g.smooth(0.5, 0.9, i['Lit'])), i['Inner'])
    spark = g.displace(spark, i['Drift'])
    return {'Spark': g.math('MULTIPLY', spark, g.math('SUBTRACT', 1.0, i['Near Ink']))}


def pigment(g, i):
    """Pigment over paper: out = paper * (1 - a + a * (wash / paper) ^ density)."""
    ratio = g.vec('MINIMUM', g.vec('MAXIMUM', g.vec('DIVIDE', i['Wash'], PAPER), (0.03,) * 3), (1.0,) * 3)
    dens = g.math('MULTIPLY_ADD', g.noise(110, 4, 5), 0.3, 1 - 0.15)            # uneven pigment
    dens = g.math('MULTIPLY', dens, g.math('MULTIPLY_ADD', i['Edge'], 1.6, 1.0))  # pooled at the edges
    dens = g.math('MULTIPLY', dens, g.math('MULTIPLY_ADD', g.noise(3, 2, 6), 0.2, 1 - 0.1))  # settles in the grain
    dens = g.math('MULTIPLY', dens, g.math('MULTIPLY_ADD', g.blur(i['Spark'], 1.0), -0.4, 1.0))
    dens = g.math('MULTIPLY', dens, g.math('MULTIPLY_ADD', g.sep(i['IDs'])['Blue'], -0.3, 1.0))  # paler glass
    wash = g.mix(i['Coverage'], (1.0, 1.0, 1.0), g.vec('POWER', ratio, dens), 'VECTOR')
    return {'Painting': g.vec('MULTIPLY', i['Paper'], wash)}


def brush_ink(g, i):
    """Wobbly, nearly opaque ink of swelling weight over the washes; lighter behind the glass."""
    wobble = g.xyz(g.math('MULTIPLY_ADD', g.noise(70, 3, 7), 4.0, -2.0),
                   g.math('MULTIPLY_ADD', g.noise(70, 3, 8), 4.0, -2.0))
    weight = g.math('ADD', g.math('MULTIPLY_ADD', g.noise(80, 3, 9), 0.24, 0.16 - 0.12),
                    g.math('MULTIPLY_ADD', g.noise(6, 3, 10), 0.08, -0.04))
    weight = g.math('MAXIMUM', weight, 0.12)
    lo, hi = g.math('SUBTRACT', weight, 0.11), g.math('ADD', weight, 0.11)

    def stroke(mask):
        return g.smooth(lo, hi, g.blur(g.displace(mask, wobble), 3.0))

    lines = g.math('MAXIMUM', stroke(i['Ink']), g.math('MULTIPLY', stroke(i['Behind']), 0.45))
    tone = g.math('MULTIPLY', g.math('MULTIPLY_ADD', g.noise(20, 3, 11), 0.3, 0.85), i['Grain'])
    return {'Image': g.mix(lines, i['Painting'], g.vec('SCALE', INK, scale=tone), 'VECTOR')}


def load_pass(name, colorspace, packed):
    img = bpy.data.images.load(os.path.join(PASSES, f'{name}{TAG}.png'), check_existing=True)
    img.colorspace_settings.name = colorspace
    img.alpha_mode = 'CHANNEL_PACKED' if packed else 'STRAIGHT'  # packed: colour kept apart from alpha
    return img


def build_watercolor(scene):
    tree = bpy.data.node_groups.new('Watercolor', 'CompositorNodeTree')
    tree.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
    g = Graph(tree)
    passes = {}
    frame = g.new('NodeFrame', label='Render Passes', label_size=24, shrink=False)
    frame.location, frame.width, frame.height = (-1530, 770), 360, 930  # the thumbnails sit above their nodes
    for k, (name, label, cs, packed) in enumerate((('wc_fill', 'Fill', 'sRGB', False),
                                                   ('wc_ids', 'IDs', 'Non-Color', True),
                                                   ('wc_lit', 'Lit', 'Non-Color', True),
                                                   ('wc_normal', 'Normal', 'sRGB', True),
                                                   ('wc_lines', 'Lines', 'Non-Color', False),
                                                   ('wc_lines_all', 'Lines All', 'Non-Color', False))):
        n = g.new('CompositorNodeImage', image=load_pass(name, cs, packed), parent=frame, label=label)
        n.location_absolute = (-1500 + 160 * (k % 2), 560 - 285 * (k // 2))  # two columns of thumbnails
        n.show_options, n.show_preview = False, True
        passes[name] = n
    fill = passes['wc_fill']

    def use(tree_, loc, links):
        n = g.new('CompositorNodeGroup', node_tree=tree_, location=loc, width=165)
        for key, v in links.items():
            g.put(n.inputs[key], v)
        return n.outputs

    ref = [('Image', 'color')]
    pap = use(group('Paper', ref, [('Paper', 'color'), ('Grain', 'float')], paper, 'Image'),
              (-1110, 600), {'Image': fill.outputs['Image']})
    wash = use(group('Wash Drift', [('Fill', 'color'), ('IDs', 'color'), ('Lit', 'color')],
                     [('Wash', 'color'), ('Coverage', 'float'), ('IDs', 'color'), ('Lit', 'float'), ('Alpha', 'float'),
                      ('Drift', 'vector')], wash_drift, 'Fill'),
               (-1110, 440), {'Fill': fill.outputs['Image'], 'IDs': passes['wc_ids'].outputs['Image'],
                              'Lit': passes['wc_lit'].outputs['Image']})
    ink = use(group('Ink Lines', [('Normal', 'color'), ('Alpha', 'float'), ('Lines', 'float'), ('Lines All', 'float'),
                                  ('IDs', 'color')],
                    [('Ink', 'float'), ('Behind', 'float'), ('Near Ink', 'float'), ('Inner', 'float')], ink_lines),
              (-1110, 20), {'Normal': passes['wc_normal'].outputs['Image'], 'Alpha': fill.outputs['Alpha'],
                           'Lines': passes['wc_lines'].outputs['Alpha'],
                           'Lines All': passes['wc_lines_all'].outputs['Alpha'],
                           'IDs': passes['wc_ids'].outputs['Image']})
    edge = use(group('Edge Darkening', [('IDs', 'color'), ('Lit', 'float'), ('Alpha', 'float'), ('Near Ink', 'float')],
                     [('Edge', 'float')], edge_darkening),
               (-880, 470), {'IDs': wash['IDs'], 'Lit': wash['Lit'], 'Alpha': wash['Alpha'], 'Near Ink': ink['Near Ink']})
    spark = use(group('Lit Edges', [('Normal', 'color'), ('Lit', 'float'), ('Inner', 'float'), ('Drift', 'vector'),
                                    ('Near Ink', 'float')], [('Spark', 'float')], lit_edges),
                (-880, 170), {'Normal': passes['wc_normal'].outputs['Image'], 'Lit': passes['wc_lit'].outputs['Image'],
                              'Inner': ink['Inner'], 'Drift': wash['Drift'], 'Near Ink': ink['Near Ink']})
    paint = use(group('Pigment', [('Wash', 'color'), ('Coverage', 'float'), ('Edge', 'float'), ('Spark', 'float'),
                                  ('IDs', 'color'), ('Paper', 'color')], [('Painting', 'color')], pigment, 'Wash'),
                (-650, 520), {'Wash': wash['Wash'], 'Coverage': wash['Coverage'], 'Edge': edge['Edge'],
                              'Spark': spark['Spark'], 'IDs': wash['IDs'], 'Paper': pap['Paper']})
    out = use(group('Brush Ink', [('Painting', 'color'), ('Ink', 'float'), ('Behind', 'float'), ('Grain', 'float')],
                    [('Image', 'color')], brush_ink, 'Painting'),
              (-420, 400), {'Painting': paint['Painting'], 'Ink': ink['Ink'], 'Behind': ink['Behind'],
                         'Grain': pap['Grain']})
    go = g.new('NodeGroupOutput', location=(-200, 420))
    tree.links.new(out['Image'], go.inputs['Image'])
    viewer = g.new('CompositorNodeViewer', location=(-200, 280))
    tree.links.new(out['Image'], viewer.inputs['Image'])
    tree.nodes.active = viewer
    scene.compositing_node_group = tree
    scene.render.use_compositing = True
    scene.render.compositor_precision = 'FULL'
    return tree


# ---------------------------------------------------------------- 三渲二: toon ramp + inverted-hull outlines

ROOT = 'SM_WenliGongdeng_500'


def toon(mat, lit, shade, alpha=1.0):
    """Two-tone ramp against a fixed light, as in build_wenli_gongdeng.py's toon preview."""
    nt = mat.node_tree
    nt.nodes.clear()

    def node(kind, x, y, label=''):
        n = nt.nodes.new(kind)
        n.location, n.label, n.select = (x, y), label, False
        return n

    geo = node('ShaderNodeNewGeometry', -820, 80)
    dot = node('ShaderNodeVectorMath', -600, 60, 'Light Direction')
    dot.operation = 'DOT_PRODUCT'
    dot.inputs[1].default_value = LIGHT
    ramp = node('ShaderNodeValToRGB', -380, 80, 'Toon Ramp')
    ramp.color_ramp.interpolation = 'CONSTANT'
    ramp.color_ramp.elements[0].color = (*srgb(shade), 1)
    ramp.color_ramp.elements[1].position = 0.01  # > 0 so the clamped negative side stays in shadow
    ramp.color_ramp.elements[1].color = (*srgb(lit), 1)
    emit = node('ShaderNodeEmission', -80, 40)
    out = node('ShaderNodeOutputMaterial', 380 if alpha < 1 else 160, 40)
    nt.links.new(geo.outputs['Normal'], dot.inputs[0])
    nt.links.new(dot.outputs['Value'], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], emit.inputs['Color'])
    surface = emit.outputs[0]
    if alpha < 1:
        mix = node('ShaderNodeMixShader', 160, 40)
        mix.inputs['Fac'].default_value = 1 - alpha
        nt.links.new(surface, mix.inputs[1])
        nt.links.new(node('ShaderNodeBsdfTransparent', -80, -120).outputs[0], mix.inputs[2])
        surface = mix.outputs[0]
    nt.links.new(surface, out.inputs['Surface'])


def outline_material():
    """Front faces of the flipped hull are drawn, so only the rim around each part shows."""
    mat = bpy.data.materials.new('M_Outline')
    mat.use_backface_culling = True
    mat.diffuse_color = (*srgb(LINE), 1)
    nt = mat.node_tree
    nt.nodes.clear()
    geo, emit = nt.nodes.new('ShaderNodeNewGeometry'), nt.nodes.new('ShaderNodeEmission')
    clear, mix = nt.nodes.new('ShaderNodeBsdfTransparent'), nt.nodes.new('ShaderNodeMixShader')
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    for n, xy in ((geo, (-500, 120)), (emit, (-260, 0)), (clear, (-260, -140)), (mix, (-20, 40)), (out, (200, 40))):
        n.location, n.select = xy, False
    emit.inputs['Color'].default_value = (*srgb(LINE), 1)
    nt.links.new(geo.outputs['Backfacing'], mix.inputs['Fac'])
    nt.links.new(emit.outputs[0], mix.inputs[1])
    nt.links.new(clear.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])
    return mat


def build_toon(scene):
    toon(bpy.data.materials['M_Stone'], *STONE)
    toon(bpy.data.materials['M_Wood'], *WOOD)
    toon(bpy.data.materials['M_Glass'], *GLASS, alpha=0.6)
    bpy.data.materials['M_Glass'].surface_render_method = 'BLENDED'  # smooth see-through glass in EEVEE
    line = outline_material()
    col = bpy.data.collections.new('Outline')
    scene.collection.children.link(col)
    dg = bpy.context.evaluated_depsgraph_get()
    for ob in [o for o in bpy.data.objects if o.parent and o.parent.name == ROOT and o.name != 'Glass']:
        me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
        me.materials.clear()
        me.materials.append(line)
        bm = bmesh.new()
        bm.from_mesh(me)
        bm.normal_update()
        for v in bm.verts:
            v.co += v.normal * 0.008
        bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
        bm.to_mesh(me)
        bm.free()
        hull = bpy.data.objects.new(ob.name + '_Outline', me)
        hull.matrix_world = ob.matrix_world
        col.objects.link(hull)
    world = bpy.data.worlds.new('Paper')
    scene.world = world
    world.color = PAPER
    if world.node_tree:
        world.node_tree.nodes['Background'].inputs['Color'].default_value = (*PAPER, 1)
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.film_transparent = False


# ---------------------------------------------------------------- screenshots

STEPS = []


def window():
    return bpy.context.window_manager.windows[0]


def areas(kind):
    return sorted((a for a in window().screen.areas if a.type == kind), key=lambda a: -a.width * a.height)


def override(area=None):
    w = window()
    ctx = {'window': w, 'screen': w.screen}
    if area is not None:
        ctx['area'] = area
        ctx['region'] = next(r for r in area.regions if r.type == 'WINDOW')
    return bpy.context.temp_override(**ctx)


def screenshot(name):
    def step():
        path = os.path.join(OUT, name)
        with override():
            bpy.ops.screen.screenshot(filepath=path, check_existing=False)
        log('saved ' + path)
    return step


def until_idle(*jobs, settle=1.5):
    def step():
        if any(bpy.app.is_job_running(j) for j in jobs):
            STEPS.insert(0, step)
            return 0.5
        return settle
    return step


def workspace(name):
    def step():
        window().workspace = bpy.data.workspaces[name]
        return 1.0
    return step


def select_only(active):
    for ob in bpy.context.view_layer.objects:
        ob.select_set(False)
    bpy.context.view_layer.objects.active = bpy.data.objects[active]


def white():
    v = areas('VIEW_3D')[0]
    sp = v.spaces.active
    sp.shading.type = 'SOLID'
    ov = sp.overlay
    ov.show_wireframes, ov.wireframe_threshold, ov.show_stats = True, 1.0, True
    ov.show_cursor = ov.show_object_origins = False
    r3d = sp.region_3d
    cam = bpy.data.objects['Camera']
    target = Vector((0, 0, 0.83))
    r3d.view_perspective = 'PERSP'
    r3d.view_rotation = (target - cam.location).to_track_quat('-Z', 'Y')
    r3d.view_location = target
    tan_v = 36 / sp.lens * min(1.0, v.height / v.width)  # the viewport's 72 mm sensor fits the longer side
    r3d.view_distance = 1.62 / 0.8 / (2 * tan_v)        # lantern about 80% of the viewport height
    select_only('Roof_Upper')
    return 1.0


def white_panels():
    areas('PROPERTIES')[0].spaces.active.context = 'MODIFIER'
    with override(areas('OUTLINER')[0]):
        bpy.ops.outliner.show_one_level(open=True)
    return 1.5


def join(kind, into):
    """The largest `kind` area grows over the largest `into` area (area_move would need the mouse on the edge)."""
    a, b = areas(kind)[0], areas(into)[0]
    with override():
        bpy.ops.screen.area_join(source_xy=(a.x + a.width // 2, a.y + a.height // 2),
                                 target_xy=(b.x + b.width // 2, b.y + b.height // 2))
    return 0.5


def split(kind, direction, factor, side, new_type, ui_type=None):
    """Split the largest `kind` area at `factor` (the bottom / left share); the part on `side`
    ('first' = bottom / left, 'second' = top / right) becomes `new_type`."""
    def step():
        with override(areas(kind)[0]):
            bpy.ops.screen.area_split(direction=direction, factor=factor)
        return 0.5

    def retype():
        pos = (lambda a: a.y) if direction == 'HORIZONTAL' else (lambda a: a.x)
        a = (min if side == 'first' else max)(areas(kind), key=pos)
        a.type = new_type
        if ui_type:
            a.ui_type = ui_type
        return 0.5
    return [step, retype]


def shading_layout():
    """Shading workspace with a taller viewport: shader editor on the bottom 35 %."""
    return [lambda: join('VIEW_3D', 'NODE_EDITOR'), *split('VIEW_3D', 'HORIZONTAL', 0.35, 'first', 'NODE_EDITOR', 'ShaderNodeTree')]


def compositing_layout():
    """Compositing workspace as node tree on the left, the Viewer as a tall image editor on the right."""
    steps = [lambda: join('IMAGE_EDITOR', 'PROPERTIES'), lambda: join('NODE_EDITOR', 'IMAGE_EDITOR')]
    steps += split('NODE_EDITOR', 'VERTICAL', 0.61, 'second', 'IMAGE_EDITOR')
    return steps


def toon_view():
    v = areas('VIEW_3D')[0]
    sp = v.spaces.active
    sp.shading.type = 'RENDERED'
    sp.overlay.show_cursor = sp.overlay.show_extras = False  # no axes of the root empty in the look-dev view
    fb = areas('FILE_BROWSER')[0]
    try:
        fb.spaces.active.params.directory = (HERE + os.sep).encode()
    except TypeError:
        fb.spaces.active.params.directory = HERE + os.sep
    ie = areas('IMAGE_EDITOR')[0]
    ie.spaces.active.image = bpy.data.images.load(os.path.join(os.path.dirname(HERE), '例子尝试.jpg'),
                                                  check_existing=True)
    sp.region_3d.view_perspective = 'CAMERA'
    with override(v):
        bpy.ops.view3d.view_center_camera()
    select_only('Roof_Upper')
    return 1.0


def toon_panels():
    areas('PROPERTIES')[0].spaces.active.context = 'MATERIAL'
    areas('NODE_EDITOR')[0].spaces.active.show_region_ui = False
    with override(areas('IMAGE_EDITOR')[0]):
        bpy.ops.image.view_all(fit_view=True)
    with override(areas('FILE_BROWSER')[0]):
        bpy.ops.file.refresh()
    for ne in areas('NODE_EDITOR'):
        with override(ne):
            bpy.ops.node.view_all()
    return 2.0


def watercolor_frame():
    ne = areas('NODE_EDITOR')[0]
    sp = ne.spaces.active
    sp.show_region_ui = False
    sp.show_region_asset_shelf = False
    sp.show_backdrop = True  # the editor only composites while something shows the result
    with override(ne):
        bpy.ops.node.view_all()
    return 1.0


def watercolor_image():
    img = bpy.data.images.get('Viewer Node')
    if img is None or not img.has_data:
        watercolor_image.tries = getattr(watercolor_image, 'tries', 0) + 1
        if watercolor_image.tries > 20:
            raise RuntimeError('the compositor never produced the Viewer image')
        STEPS.insert(0, watercolor_image)
        return 1.0
    ie = areas('IMAGE_EDITOR')[0]
    ie.spaces.active.image = img
    with override(ie):
        bpy.ops.image.view_all(fit_view=True)
    ne = areas('NODE_EDITOR')[0]
    ne.spaces.active.show_backdrop = False  # the result is in the image editor instead
    with override(ne):
        bpy.ops.node.view_all()
        bpy.ops.view2d.zoom_in(zoomfacx=0.06, zoomfacy=0.06)  # view_all leaves wide margins
    return 1.5


def gui():
    prefs = bpy.context.preferences
    prefs.view.ui_scale = float(os.environ.get('SHOT_UI_SCALE', '0.8'))  # x1.5 Windows scaling = 1.2
    prefs.view.smooth_view = 0
    prefs.view.use_save_prompt = False
    os.makedirs(OUT, exist_ok=True)
    scene = bpy.context.scene
    if 'white' in SHOTS:
        STEPS.extend([workspace('Layout'), white, white_panels, screenshot('纹璃宫灯_1_白模.png')])

    def toon_look():
        build_toon(scene)

    def watercolor_look():
        build_watercolor(scene)

    if 'toon' in SHOTS or 'watercolor' in SHOTS:
        STEPS.append(toon_look)
    if 'toon' in SHOTS:
        STEPS.extend([workspace('Shading'), *shading_layout(), toon_view, toon_panels,
                      until_idle('SHADER_COMPILATION', settle=3.0), screenshot('纹璃宫灯_2_三渲二.png')])
    if 'watercolor' in SHOTS:
        STEPS.extend([watercolor_look, workspace('Compositing'), *compositing_layout(), watercolor_frame,
                      until_idle('COMPOSITE', settle=1.0), watercolor_image, screenshot('纹璃宫灯_3_水彩.png')])

    def runner():
        try:
            if not STEPS:
                bpy.ops.wm.quit_blender()
                return None
            delay = STEPS.pop(0)()
            return 0.3 if delay is None else delay
        except Exception:
            traceback.print_exc()
            STEPS.clear()
            bpy.ops.wm.quit_blender()
            return None

    bpy.app.timers.register(runner, first_interval=2.0)


# ---------------------------------------------------------------- run

if bpy.app.background:
    scene = bpy.context.scene
    build_watercolor(scene)
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.filepath = os.path.join(OUT, 'watercolor_comp.png')
    bpy.ops.render.render(write_still=True)
    log('rendered ' + scene.render.filepath)
else:
    gui()
