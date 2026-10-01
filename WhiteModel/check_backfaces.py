"""Finds inside-out faces and see-through gaps in the food models before they go to Unity, which culls
back faces (and its outline pass then fills the hole dark). Each SM_<id>.blend is rendered with and
without backface culling from four views, and the share of the item's pixels that change is reported;
anything above 0.5% shows in the game.

    blender -b --factory-startup --python check_backfaces.py -- <dir with SM_*.blend> [id1,id2,...] [--show <dir>]

--show writes bfc_<id>.png per item: no culling | culling | changed pixels in red (worst view).
"""
import glob
import math
import os
import sys

import bpy
import numpy as np
from mathutils import Vector

ARGS = sys.argv[sys.argv.index('--') + 1:]
SHOW = ARGS[ARGS.index('--show') + 1] if '--show' in ARGS else None
ARGS = [a for a in ARGS if a not in ('--show', SHOW)]
DIR = ARGS[0]
IDS = ARGS[1].split(',') if len(ARGS) > 1 else \
    sorted(os.path.basename(p)[3:-6] for p in glob.glob(os.path.join(DIR, 'SM_*.blend')))
TMP = os.path.join(os.environ.get('TEMP', '.'), f'bfc_{os.getpid()}_%d.png')   # per process: runs may overlap
VIEWS = ((20, 32), (20, 60), (-40, 25), (160, 30))   # (azimuth, elevation): the icon view, steeper, the sides
LIMIT = 0.005


def render(scene, cull):
    scene.display.shading.show_backface_culling = cull
    scene.render.filepath = TMP % int(cull)
    bpy.ops.render.render(write_still=True)
    im = bpy.data.images.load(scene.render.filepath)
    px = np.array(im.pixels[:]).reshape(-1, 4)
    bpy.data.images.remove(im)
    return px


report = []
for key in IDS:
    bpy.ops.wm.open_mainfile(filepath=os.path.join(DIR, f'SM_{key}.blend'))
    scene = bpy.context.scene
    ob = next(o for o in scene.objects if o.type == 'MESH' and o.name.startswith('SM_'))
    for o in list(scene.objects):
        if o != ob:
            bpy.data.objects.remove(o)
    vs = [ob.matrix_world @ v.co for v in ob.data.vertices]
    lo = Vector([min(v[i] for v in vs) for i in range(3)])
    hi = Vector([max(v[i] for v in vs) for i in range(3)])
    cam = bpy.data.objects.new('Cam', bpy.data.cameras.new('Cam'))
    cam.data.type = 'ORTHO'
    cam.data.ortho_scale = max(hi - lo) * 1.3
    scene.collection.objects.link(cam)
    scene.camera = cam
    scene.render.engine = 'BLENDER_WORKBENCH'
    scene.render.resolution_x = scene.render.resolution_y = 256
    scene.render.film_transparent = True
    sh = scene.display.shading
    sh.light, sh.color_type, sh.single_color = 'STUDIO', 'SINGLE', (0.8, 0.8, 0.8)
    worst, pair = 0.0, None
    for az, el in VIEWS:
        a, e = math.radians(az), math.radians(el)
        view = Vector((math.sin(a) * math.cos(e), -math.cos(a) * math.cos(e), math.sin(e)))
        cam.location = (lo + hi) / 2 + view * 3
        cam.rotation_euler = (-view).to_track_quat('-Z', 'Y').to_euler()
        off, on = render(scene, False), render(scene, True)
        share = (np.abs(off - on).max(axis=1) > 0.08).sum() / max((off[:, 3] > 0.5).sum(), 1)
        if pair is None or share > worst:
            worst, pair = share, (off, on)
    report.append((key, worst))
    if SHOW and worst > 0:
        off, on = pair
        n = int(math.sqrt(len(off)))
        vis = off.copy()
        vis[:, 3] = 1.0
        vis[np.abs(off - on).max(axis=1) > 0.08] = (1.0, 0.0, 0.0, 1.0)
        img = bpy.data.images.new('bfc', n * 3, n, alpha=True)
        img.pixels[:] = np.concatenate([off.reshape(n, n, 4), on.reshape(n, n, 4), vis.reshape(n, n, 4)], axis=1).ravel()
        img.filepath_raw = os.path.join(SHOW, f'bfc_{key}.png')
        img.file_format = 'PNG'
        img.save()
    print(f'[bfc] {key}: {worst * 100:.2f}% of pixels change with culling', flush=True)
print('[bfc] over 0.5%:', [k for k, w in report if w > LIMIT] or 'none', flush=True)
