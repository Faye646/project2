"""Raw ingredients for the wok: each main ingredient the recipes put in the wok, as the solid pieces it goes in as (a
ball of dough, a dome of rice, chunks of pork, cubes of chicken, a whole egg, a whole fish, wedges of tomato, …),
built by food_models/wok_raw.py. The cooking screen drops `count` of them into the wok and tosses them about while
the dish cooks, hopping and tumbling and now and then flipping right over, until it is done and the dish's own wok
model (SM_<dish>_wok) takes their place. So, unlike the ingredients' display models (whose traced pieces only look
right from the art's view), every piece is closed and solid and looks right from every side: rounded all over, real
size, resting on z = 0 in its natural pose with the middle of its footprint over the origin (its pivot at its
foot), in the same colours and painted textures as the ingredient's display model, within 1500 triangles.

    blender -b --factory-startup --python WhiteModel/build_raw.py -- [<out_dir>] [--only id1,id2]

Writes RAW_<id>.blend + RAW_<id>.fbx to <out_dir> (default WhiteModel/Food), and raw_pieces.json there: for each
id, how many pieces of it go into the wok (count) and the piece's longest side across, seen from above (size, in
metres); --only builds just those ids and updates their entries. Liquids (stock, cola, the wines) have nothing to
show in the wok and get no raw piece, nor do the seasonings, which go in by the pinch.
"""
import json
import os
import sys

import bpy

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from food_models.core import log, new_scene  # noqa: E402
from food_models.wok_raw import PIECES  # noqa: E402

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = os.path.abspath(ARGS[0]) if ARGS and not ARGS[0].startswith('--') else os.path.join(HERE, 'Food')
ONLY = ARGS[ARGS.index('--only') + 1].split(',') if '--only' in ARGS else None
unknown = sorted(set(ONLY or ()) - set(PIECES))
if unknown:
    raise SystemExit(f'[raw] no raw piece for {unknown}')

os.makedirs(OUT, exist_ok=True)
JSON = os.path.join(OUT, 'raw_pieces.json')
table = json.load(open(JSON, encoding='utf-8')) if ONLY and os.path.exists(JSON) else {}
for key, (build, count) in PIECES.items():
    if ONLY and key not in ONLY:
        continue
    new_scene()
    scene = bpy.context.scene
    col = bpy.data.collections.new('RAW_' + key)
    scene.collection.children.link(col)
    ob = build(col)
    me = ob.data
    xs, ys, zs = ([v.co[i] for v in me.vertices] for i in range(3))
    size = max(max(xs) - min(xs), max(ys) - min(ys))
    tris = sum(len(pl.vertices) - 2 for pl in me.polygons)
    table[key] = {'count': count, 'size': round(size, 4)}
    bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, f'RAW_{key}.blend'))
    for o in bpy.data.objects:
        o.select_set(o == ob)
    bpy.context.view_layer.objects.active = ob
    bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, f'RAW_{key}.fbx'), use_selection=True, object_types={'MESH'},
                             apply_scale_options='FBX_SCALE_ALL', axis_forward='-Z', axis_up='Y',
                             bake_space_transform=False, use_mesh_modifiers=True, mesh_smooth_type='OFF',
                             add_leaf_bones=False, bake_anim=False, colors_type='LINEAR')   # Part.tint's colours
    log(f'RAW_{key}: {tris} tris, {(max(xs) - min(xs)) * 100:.1f} x {(max(ys) - min(ys)) * 100:.1f} x '
        f'{(max(zs) - min(zs)) * 100:.1f} cm, {count} in the wok')
order = [k for k in PIECES if k in table] + sorted(k for k in table if k not in PIECES)
with open(JSON, 'w', encoding='utf-8') as fh:
    json.dump({k: table[k] for k in order}, fh, indent=1)
log('done')
