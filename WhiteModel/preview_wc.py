"""Previews food models roughly as Unity's WatercolorLit draws their 3D food images (Resources/Food3D), without
Unity: the colour painted across them (Part.tint, VTINT), the full food colour (VIVID), the detail texture and its
relief (DETAIL: Unity/Assets/Art/Textures/food_*.png, box-projected in object space), the four soft light steps
of the warm top light, its wash and the gloss (GLOSS), and a dark outline, seen as the icons are: from in front,
35° up, framed on the model's bounds. Paper grain, stains and pigment pooling are left out.

    blender -b --factory-startup --python WhiteModel/preview_wc.py -- <dir with SM_*.blend> <out dir> id1,id2,...

reads <dir>/palette_food.json (what build_food.py writes next to the models) and writes <out dir>/<id>.png (512²,
transparent background). Close to Unity's look, not identical: check the real icon before calling a look done.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
ARGS = sys.argv[sys.argv.index('--') + 1:]
DIR, OUT, IDS = ARGS[0], ARGS[1], ARGS[2].split(',')
TEX = os.path.join(HERE, '..', 'Unity', 'Assets', 'Art', 'Textures')
PAL = json.load(open(os.path.join(DIR, 'palette_food.json'), encoding='utf-8'))['toon']
LIGHT = Vector((-0.3, -0.8, 0.52)).normalized()   # the icon bake's sun (Unity (x, y, z) = Blender (x, z, y))
EL = math.radians(35)
VIEW = Vector((0.0, -math.cos(EL), math.sin(EL)))  # towards the camera


def linear(hex_color):
    c = [int(hex_color[i:i + 2], 16) / 255 for i in (1, 3, 5)]
    return tuple(x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4 for x in c)


class Graph:
    """A material's node tree, with small helpers for maths on floats and colours."""

    def __init__(self, mat):
        mat.use_nodes = True
        self.nt = mat.node_tree
        self.nt.nodes.clear()

    def node(self, kind, **props):
        n = self.nt.nodes.new(kind)
        for k, v in props.items():
            setattr(n, k, v)
        return n

    def link(self, out, sock):
        self.nt.links.new(out, sock)

    def _in(self, node, name, typ):
        return next(s for s in node.inputs if s.name == name and s.type == typ and s.enabled)

    def math(self, op, a, b=None, clamp=False):
        n = self.node('ShaderNodeMath', operation=op, use_clamp=clamp)
        for i, v in enumerate((a, b)):
            if v is None:
                continue
            if isinstance(v, (int, float)):
                n.inputs[i].default_value = v
            else:
                self.link(v, n.inputs[i])
        return n.outputs[0]

    def smooth(self, x, e0, e1):
        n = self.node('ShaderNodeMapRange', interpolation_type='SMOOTHSTEP')
        self.link(x, n.inputs['Value'])
        n.inputs['From Min'].default_value, n.inputs['From Max'].default_value = e0, e1
        return n.outputs['Result']

    def mix(self, fac, a, b):
        n = self.node('ShaderNodeMix', data_type='RGBA', clamp_factor=True)
        for name, v in (('A', a), ('B', b)):
            s = self._in(n, name, 'RGBA')
            if isinstance(v, tuple):
                s.default_value = (*v, 1.0)
            else:
                self.link(v, s)
        f = self._in(n, 'Factor', 'VALUE')
        if isinstance(fac, (int, float)):
            f.default_value = fac
        else:
            self.link(fac, f)
        return next(o for o in n.outputs if o.type == 'RGBA' and o.enabled)

    def scale(self, col, k):
        """A colour times a number or a colour (per channel)."""
        n = self.node('ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY', clamp_factor=True)
        self._in(n, 'Factor', 'VALUE').default_value = 1.0
        self.link(col, self._in(n, 'A', 'RGBA'))
        self._in(n, 'B', 'RGBA').default_value = (*(k if isinstance(k, tuple) else (k, k, k)), 1.0)
        return next(o for o in n.outputs if o.type == 'RGBA' and o.enabled)

    def add(self, col, k):
        n = self.node('ShaderNodeMix', data_type='RGBA', blend_type='ADD', clamp_factor=True)
        self._in(n, 'Factor', 'VALUE').default_value = 1.0
        self.link(col, self._in(n, 'A', 'RGBA'))
        self._in(n, 'B', 'RGBA').default_value = (k, k, k, 1.0)
        return next(o for o in n.outputs if o.type == 'RGBA' and o.enabled)

    def vibrant(self, col, k, deepen):
        """The shader's Vibrant(): saturation raised along 1 - (1 - s)^k, the same hue and value, deepened."""
        sep = self.node('ShaderNodeSeparateColor', mode='HSV')
        self.link(col, sep.inputs[0])
        s2 = self.math('SUBTRACT', 1.0, self.math('POWER', self.math('SUBTRACT', 1.0, sep.outputs[1]), k))
        v2 = self.math('MULTIPLY', sep.outputs[2], self.math('SUBTRACT', 1.0, self.math('MULTIPLY', s2, deepen)))
        comb = self.node('ShaderNodeCombineColor', mode='HSV')
        self.link(sep.outputs[0], comb.inputs[0])
        self.link(s2, comb.inputs[1])
        self.link(v2, comb.inputs[2])
        return comb.outputs[0]


def food_material(mat, key):
    p = PAL.get(key, {'lit': '#c8c8c8', 'shade': '#a0a0a0'})
    g = Graph(mat)
    vivid, gloss, vtint = p.get('vivid', 1.0), p.get('gloss', 0.0), p.get('vtint', 0.0)
    # base: the colour painted across the surface, then the full food colour
    attr = g.node('ShaderNodeVertexColor', layer_name='Tint')
    fac = g.math('MULTIPLY', g.math('SUBTRACT', 1.0, attr.outputs['Alpha']), vtint)
    flat = g.mix(fac, linear(p['lit']), attr.outputs['Color'])
    flat = g.mix(vivid, flat, g.vibrant(flat, 1.9, 0.15))
    geo = g.node('ShaderNodeNewGeometry')
    normal, gnormal = geo.outputs['Normal'], geo.outputs['Normal']
    base = flat
    d = p.get('detail')
    path = d and os.path.join(TEX, d['tex'] + '.png')
    if path and os.path.exists(path):
        img = bpy.data.images.load(path, check_existing=True)
        img.colorspace_settings.name = 'Non-Color'
        co = g.node('ShaderNodeTexCoord')
        mp = g.node('ShaderNodeMapping')
        mp.inputs['Scale'].default_value = (d['scale'],) * 3
        g.link(co.outputs['Object'], mp.inputs['Vector'])
        tx = g.node('ShaderNodeTexImage', image=img, projection='BOX', projection_blend=0.15, extension='REPEAT')
        g.link(mp.outputs['Vector'], tx.inputs['Vector'])
        sep = g.node('ShaderNodeSeparateColor', mode='RGB')
        g.link(tx.outputs['Color'], sep.inputs[0])
        base = g.mix(g.math('MULTIPLY', sep.outputs[0], d['amount']), base, linear(d['color']))
        for half, name in ((1.0, 'n'), (0.5, 'g')):   # the gloss sees half the relief, as in the shader
            bump = g.node('ShaderNodeBump')
            bump.inputs['Strength'].default_value = 1.0
            bump.inputs['Distance'].default_value = d['bump'] * 0.001 * half
            g.link(sep.outputs[1], bump.inputs['Height'])
            if name == 'n':
                normal = bump.outputs['Normal']
            else:
                gnormal = bump.outputs['Normal']
    # light: diffuse painted into four soft steps
    dot = g.node('ShaderNodeVectorMath', operation='DOT_PRODUCT')
    g.link(normal, dot.inputs[0])
    dot.inputs[1].default_value = LIGHT
    lum = g.math('ADD', 0.25, g.math('MULTIPLY', g.math('MAXIMUM', dot.outputs['Value'], 0.0), 0.75))
    steps = g.math('ADD', g.math('ADD', g.math('MULTIPLY', g.smooth(lum, 0.25, 0.42), 0.45),
                                 g.math('MULTIPLY', g.smooth(lum, 0.42, 0.62), 0.37)),
                   g.math('MULTIPLY', g.smooth(lum, 0.62, 0.9), 0.18))
    shadow = g.mix(0.2, g.scale(base, 0.54), (0.34, 0.36, 0.55))
    shadow = g.mix(vivid, shadow, g.vibrant(g.scale(base, 0.58), 1.4, 0.0))
    col = g.mix(steps, shadow, base)
    hi = g.math('MULTIPLY', g.math('SUBTRACT', steps, 0.85), 5.0, clamp=True)
    wash = g.mix(vtint, g.mix(0.35, base, (1.0, 0.86, 0.62)), g.scale(base, (1.15, 1.07, 0.97)))
    col = g.mix(g.math('MULTIPLY', hi, 0.6 * (1 - 0.6 * vivid)), col, wash)
    # gloss: a sheen where it mirrors the light and a small white glint at its heart
    if gloss > 0:
        h = (LIGHT + VIEW).normalized()
        dist = g.node('ShaderNodeVectorMath', operation='DISTANCE')
        g.link(gnormal, dist.inputs[0])
        dist.inputs[1].default_value = h
        a = dist.outputs['Value']
        sheen = g.math('SUBTRACT', 1.0, g.smooth(a, 0.25, 0.6))
        glint = g.math('SUBTRACT', 1.0, g.smooth(a, 0.1, 0.16))
        col = g.mix(g.math('MULTIPLY', sheen, gloss * 0.5), col, g.add(g.scale(col, 1.12), 0.04))
        col = g.mix(g.math('MULTIPLY', glint, gloss * 0.85), col, (1.0, 0.98, 0.92))
    emit = g.node('ShaderNodeEmission')
    g.link(col, emit.inputs['Color'])
    g.link(emit.outputs[0], g.node('ShaderNodeOutputMaterial').inputs['Surface'])


def outline(scene, ob):
    """An inverted hull a little out along the normals, seen only from inside: the dark line round the model."""
    import bmesh
    line = bpy.data.materials.new('M_Outline')
    line.use_backface_culling = True
    g = Graph(line)
    geo = g.node('ShaderNodeNewGeometry')
    emit = g.node('ShaderNodeEmission')
    emit.inputs['Color'].default_value = (*linear('#4a2e1c'), 1)
    mix = g.node('ShaderNodeMixShader')
    g.link(geo.outputs['Backfacing'], mix.inputs['Fac'])
    g.link(emit.outputs[0], mix.inputs[1])
    g.link(g.node('ShaderNodeBsdfTransparent').outputs[0], mix.inputs[2])
    g.link(mix.outputs[0], g.node('ShaderNodeOutputMaterial').inputs['Surface'])
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), depsgraph=dg)
    me.materials.clear()
    me.materials.append(line)
    bm = bmesh.new()
    bm.from_mesh(me)
    bmesh.ops.remove_doubles(bm, verts=bm.verts[:], dist=1e-5)
    bm.normal_update()
    w = max(ob.dimensions) * 0.0045
    for v in bm.verts:
        v.co += v.normal * w
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(me)
    bm.free()
    hull = bpy.data.objects.new(ob.name + '_outline', me)
    hull.matrix_world = ob.matrix_world
    scene.collection.objects.link(hull)


os.makedirs(OUT, exist_ok=True)
for key in IDS:
    path = os.path.join(DIR, f'SM_{key}.blend')
    if not os.path.exists(path):
        print(f'[preview] {key}: no {path}', flush=True)
        continue
    bpy.ops.wm.open_mainfile(filepath=path)
    scene = bpy.context.scene
    for o in list(scene.objects):
        if o.type != 'MESH' or not o.name.startswith('SM_'):
            bpy.data.objects.remove(o)
    ob = next(o for o in scene.objects if o.type == 'MESH')
    for slot in ob.material_slots:
        if slot.material:
            food_material(slot.material, slot.material.name[2:])
    outline(scene, ob)
    vs = [ob.matrix_world @ v.co for v in ob.data.vertices]
    lo = Vector([min(v[i] for v in vs) for i in range(3)])
    hi = Vector([max(v[i] for v in vs) for i in range(3)])
    cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam'))
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = max(hi - lo) * 1.2   # as the icon bake: orthographic size 0.6 × the largest side
    cam.data.clip_start, cam.data.clip_end = 0.001, 10
    scene.collection.objects.link(cam)
    scene.camera = cam
    cam.location = (lo + hi) / 2 + VIEW * 2
    cam.rotation_euler = (-VIEW).to_track_quat('-Z', 'Y').to_euler()
    scene.render.engine = 'CYCLES'
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 12
    scene.cycles.use_denoising = False
    scene.render.resolution_x = scene.render.resolution_y = 512
    scene.render.film_transparent = True
    scene.view_settings.view_transform = 'Standard'
    scene.render.filepath = os.path.join(OUT, f'{key}.png')
    bpy.ops.render.render(write_still=True)
    print(f'[preview] {key}: {scene.render.filepath}', flush=True)
