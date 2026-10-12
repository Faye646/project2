"""Renders food models the way their art is drawn, for matching shape and layout 1:1 (art_match.py does the
comparing).

    blender -b --factory-startup --python art_views.py -- <dir with SM_*.blend> <out_dir> <id> [views]

`views` is a list of az,el pairs in degrees, "0,30;0,35;10,35" (default: a grid of az -15..15 by 7.5 and el 20..50
by 5). Each view is an orthographic camera looking at the model's middle from in front (-Y), turned az to the right
and raised el; the model is drawn flat in its palette colours (palette_food.json next to the models) with a thin
outline on a transparent background, 1024², into <out_dir>/<id>_a<az>_e<el>.png, with the camera beside it in
a .json. The framing doesn't matter: art_match.py scales and moves each render onto the art.
"""
import json
import math
import os
import sys

import bpy
from mathutils import Vector

ARGS = sys.argv[sys.argv.index('--') + 1:]
DIR, OUT, KEY = ARGS[:3]
if len(ARGS) > 3:
    VIEWS = [tuple(float(x) for x in v.split(',')) for v in ARGS[3].split(';')]
else:
    VIEWS = [(az, el) for el in range(20, 51, 5) for az in (-15, -7.5, 0, 7.5, 15)]
os.makedirs(OUT, exist_ok=True)
pal = json.load(open(os.path.join(DIR, 'palette_food.json'), encoding='utf-8'))['toon']

bpy.ops.wm.open_mainfile(filepath=os.path.join(DIR, f'SM_{KEY}.blend'))
scene = bpy.context.scene
ob = next(o for o in scene.objects if o.type == 'MESH' and o.name.startswith('SM_'))
for o in list(scene.objects):
    if o != ob:
        bpy.data.objects.remove(o)
for m in ob.data.materials:
    h = pal.get(m.name[2:], {'lit': '#cccccc'})['lit']
    m.diffuse_color = (*[(int(h[i:i + 2], 16) / 255) ** 2.2 for i in (1, 3, 5)], 1)
dg = bpy.context.evaluated_depsgraph_get()
me = ob.evaluated_get(dg).to_mesh()
vs = [ob.matrix_world @ v.co for v in me.vertices]
lo = Vector([min(v[i] for v in vs) for i in range(3)])
hi = Vector([max(v[i] for v in vs) for i in range(3)])
ob.evaluated_get(dg).to_mesh_clear()
cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam'))
cam.data.type = 'ORTHO'
cam.data.ortho_scale = max(hi - lo) * 1.4
scene.collection.objects.link(cam)
scene.camera = cam
scene.render.engine = 'BLENDER_WORKBENCH'
scene.render.resolution_x = scene.render.resolution_y = 1024
scene.render.film_transparent = True
scene.view_settings.view_transform = 'Standard'
sh = scene.display.shading
sh.light, sh.color_type = 'FLAT', 'MATERIAL'
sh.show_object_outline = True
sh.object_outline_color = (0.25, 0.15, 0.1)
sh.show_cavity = False
for az, el in VIEWS:
    a, e = math.radians(az), math.radians(el)
    view = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
    cam.location = (lo + hi) / 2 + view * 3
    cam.rotation_euler = (-view).to_track_quat('-Z', 'Y').to_euler()
    scene.render.filepath = os.path.join(OUT, f'{KEY}_a{az:g}_e{el:g}.png')
    bpy.ops.render.render(write_still=True)
    q = cam.rotation_euler.to_quaternion()   # how world points land on the render, for art_match's grid
    with open(os.path.join(OUT, f'{KEY}_a{az:g}_e{el:g}.json'), 'w') as fh:
        json.dump({'centre': list((lo + hi) / 2), 'right': list(q @ Vector((1, 0, 0))), 'up': list(q @ Vector((0, 1, 0))),
                   'ortho_scale': cam.data.ortho_scale, 'resolution': 1024}, fh)
print(f'[views] {KEY}: {len(VIEWS)} views', flush=True)
