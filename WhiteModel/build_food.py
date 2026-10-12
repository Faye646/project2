"""Dishes, ingredients and seasonings as 3D models for 三渲二: all 23 dishes in the design data plus 酸菜鱼（辣味版）
D20_spicy, each with a 锅中 _wok variant (松鼠鳜鱼（淀粉脆皮版）D18_crisp has the same art as D18 and shares its
model), and every ingredient and seasoning except the six wines; `wine` is a generic celadon ewer (酒_待定.png)
until each wine gets its own. Ids match the design data.

The models are made in food_models/: core.py holds what they share (the palette and its gloss, the Part mesh
builder, vessels, sauces, garnish, fish bodies, sacks and baskets, and the helpers for matching the art), and each
other module one group with its ITEMS: bowls, plates, stirfry (the dishes), meat_fish, produce, sacks, jars (the
ingredients and seasonings). This script builds, exports and previews them.

Built procedurally from the art in 新建文件夹/ (胡饼.png, 面粉.png, …), matched to it 1:1 in shape and layout
from the art's own view (straight in front, 35° up) with art_views.py and art_match.py. Everything is rounded
(圆角, no sharp points): turned parts are lathed with enough segments for smooth rims, food pieces are coarse
cages rounded by subdivision (Part.soft), and the shading is smooth all over, so no facet edge shows. Each item is
its own FBX, pivot at the centre of the base, real size (a bowl is ~16 cm across), within about 8000 triangles.
Unity culls back faces, so lathe profiles run up the outside and down the inside, and every opening is closed at
its fill height: no inside face may show past the contents.

Run with Blender 5.2:
    blender -b --factory-startup --python build_food.py -- <out_dir> [--no-render] [--only id1,id2]
Writes SM_<id>.blend + .fbx, palette_food.json and renders/ (clay + toon preview) to <out_dir>;
--only builds just those ids.
"""
import json
import math
import os
import sys

import bmesh
import bpy
from mathutils import Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from food_models.core import (ART_EL, CLAY, DETAIL, GLASS, GLOSS, GLOSS_DEFAULT, OUTLINE, PALETTE, VIVID,  # noqa: E402
                              VTINT, log, new_scene)
from food_models import bowls, jars, meat_fish, plates, produce, sacks, stirfry  # noqa: E402

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = os.path.abspath(ARGS[0]) if ARGS and not ARGS[0].startswith('--') else os.path.join(HERE, 'Food')
RENDER = '--no-render' not in ARGS
ONLY = set(ARGS[ARGS.index('--only') + 1].split(',')) if '--only' in ARGS else None


def setup_camera(scene, target_h, extent=0.2):
    cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera'))
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = extent * 1.25
    scene.collection.objects.link(cam)
    scene.camera = cam
    az, el = 0.0, ART_EL   # straight in front, 35° up: the view the art is drawn from
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


ITEMS = (plates.ITEMS + bowls.ITEMS + stirfry.ITEMS + meat_fish.ITEMS + produce.ITEMS + sacks.ITEMS
         + jars.ITEMS)

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
                             add_leaf_bones=False, bake_anim=False, colors_type='LINEAR')   # Part.tint's colours
    if RENDER:
        setup_camera(scene, zmax * 0.45, extent)
        scene.render.engine = 'BLENDER_WORKBENCH'
        sh = scene.display.shading
        sh.light, sh.color_type, sh.single_color = 'STUDIO', 'SINGLE', CLAY
        sh.show_cavity, sh.show_object_outline = True, True
        scene.render.filepath = os.path.join(OUT, 'renders', f'{key}_whitemodel.png')
        bpy.ops.render.render(write_still=True)
        toon_preview(scene, ob, os.path.join(OUT, 'renders', f'{key}_toon.png'))


def detail(k):
    """The meat's painted surface (DETAIL), for Unity's _DetailTex/_DetailScale/_DetailColor/_DetailAmount/_BumpAmount."""
    if k not in DETAIL:
        return {}
    tex, scale, color, amount, bump = DETAIL[k]
    return {'detail': {'tex': tex, 'scale': scale, 'color': color, 'amount': amount, 'bump': bump}}


for k in sorted(set(DETAIL) - set(PALETTE)):
    log(f'DETAIL has {k}, which is not in the palette')
with open(os.path.join(OUT, 'palette_food.json'), 'w', encoding='utf-8') as fh:
    json.dump({'toon': {k: {'lit': v[0], 'shade': v[1], 'emission': 0.0, 'gloss': GLOSS.get(k, GLOSS_DEFAULT),
                            'vivid': VIVID.get(k, 1.0), **detail(k), **({'vtint': VTINT[k]} if k in VTINT else {}),
                            **({'glass': GLASS[k]} if k in GLASS else {}),
                            **({'outline': OUTLINE[k]} if k in OUTLINE else {})}
                   for k, v in PALETTE.items()}}, fh, indent=1)
with open(STATS, 'w') as fh:
    json.dump(stats, fh, indent=1)
log('done')
