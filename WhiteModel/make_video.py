"""三渲二 style video for the teacher: the hall and kitchen (Level1) and the 3D cooking view.

Shot 1 (level1_toon.blend): the whole shop, a slow pan, then a push in to the kitchen and its 案台.
Shot 2 (cook_view.blend): the cooking view, a slow push in, the dish in the wok bobbing and the fire
flickering. Both are rendered to PNG frames, then joined in the sequencer into one MP4 (H.264).

    blender -b --factory-startup --python make_video.py -- <out.mp4>
Needs WhiteModel/Level1/renders/level1_toon.blend (build_level1.py) and WhiteModel/CookView/cook_view.blend
(build_cook_view.py).
"""
import math
import os
import shutil
import sys

import bpy
from mathutils import Vector

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.abspath(ARGS[0]) if ARGS and not ARGS[0].startswith('--') else os.path.join(HERE, 'StyleTest', '水彩样片.mp4' if '--wc' in ARGS else '三渲二样片.mp4')
FRAMES = os.path.join(HERE, 'StyleTest', 'frames')
W, H, FPS = 1280, 720, 30
PAPER = (244 / 255, 236 / 255, 217 / 255)


def setup_render(scene, samples=8):
    if WCV:   # keep the file's own sun and fill; paper behind the shop comes from a backdrop plane
        scene.render.resolution_x, scene.render.resolution_y = W, H
        scene.render.resolution_percentage = 100
        scene.render.fps = FPS
        scene.render.film_transparent = False
        scene.eevee.taa_render_samples = 24
        scene.render.image_settings.file_format = 'PNG'
        return
    scene.render.resolution_x, scene.render.resolution_y = W, H
    scene.render.resolution_percentage = 100
    scene.render.fps = FPS
    scene.render.film_transparent = False
    scene.view_settings.view_transform = 'Standard'
    scene.render.engine = 'BLENDER_EEVEE'   # emission-only toon: EEVEE matches Cycles here and is far faster
    scene.eevee.taa_render_samples = 16
    scene.render.image_settings.file_format = 'PNG'
    if scene.world is None:
        scene.world = bpy.data.worlds.new('World')
    scene.world.use_nodes = True
    bg = scene.world.node_tree.nodes.get('Background')
    bg.inputs['Color'].default_value = (*[c ** 2.2 for c in PAPER], 1)
    bg.inputs['Strength'].default_value = 1.0


def ease(t):
    return t * t * (3 - 2 * t)


def key_camera(cam, frames):
    """frames: [(frame, location, ortho_scale or lens)]"""
    for f, loc, size in frames:
        cam.location = loc
        cam.keyframe_insert('location', frame=f)
        if cam.data.type == 'ORTHO':
            cam.data.ortho_scale = size
            cam.data.keyframe_insert('ortho_scale', frame=f)
        else:
            cam.data.lens = size
            cam.data.keyframe_insert('lens', frame=f)
    for fc in (cam.animation_data.action.fcurves if hasattr(cam.animation_data.action, 'fcurves') else []):
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.easing = 'EASE_IN_OUT'


def render_frames(scene, name, n):
    d = os.path.join(FRAMES, name)
    os.makedirs(d, exist_ok=True)
    scene.frame_start, scene.frame_end = 1, n
    scene.render.filepath = os.path.join(d, '')
    bpy.ops.render.render(animation=True)
    print(f'[video] {name}: {n} frames', flush=True)
    return d


JOIN_ONLY = '--join-only' in ARGS
WCV = '--wc' in ARGS   # the approved 水彩 style: level1_wc.blend and cook_view_wc.blend
if not JOIN_ONLY:
    shutil.rmtree(FRAMES, ignore_errors=True)

d1, d2 = os.path.join(FRAMES, 'shot1'), os.path.join(FRAMES, 'shot2')
if not JOIN_ONLY:
    # ---------------------------------------------------------------- shot 1: the shop
    bpy.ops.wm.open_mainfile(filepath=os.path.join(HERE, 'Level1', 'renders', 'level1_wc.blend' if WCV else 'level1_toon.blend'))
    scene = bpy.context.scene
    setup_render(scene)
    if WCV:
        import bmesh
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=200)
        me = bpy.data.meshes.new('Paper')
        bm.to_mesh(me)
        bm.free()
        m = bpy.data.materials.new('Paper')
        nt = m.node_tree
        nt.nodes.clear()
        em = nt.nodes.new('ShaderNodeEmission')
        em.inputs['Color'].default_value = (0.9, 0.83, 0.7, 1)
        nt.links.new(em.outputs[0], nt.nodes.new('ShaderNodeOutputMaterial').inputs['Surface'])
        me.materials.append(m)
        paper = bpy.data.objects.new('Paper', me)
        paper.location.z = -0.05
        scene.collection.objects.link(paper)
    cam = scene.camera
    view = (cam.matrix_world.to_quaternion() @ Vector((0, 0, 1))).normalized()   # from the target toward the camera
    right = (cam.matrix_world.to_quaternion() @ Vector((1, 0, 0))).normalized()
    up = (cam.matrix_world.to_quaternion() @ Vector((0, 1, 0))).normalized()
    home = cam.location.copy()
    home_scale = cam.data.ortho_scale
    table = bpy.data.objects['K_AnTai'].matrix_world.translation + Vector((0, 0, 0.6))
    table_cam = table + view * 40
    N1 = int(os.environ.get('N1', 7 * FPS))
    key_camera(cam, [
        (1, home - right * 0.6, home_scale * 0.98),
        (int(N1 * 0.45), home + right * 0.6, home_scale * 0.98),
        (N1, table_cam + up * 0.2, 4.2),
    ])
    d1 = render_frames(scene, 'shot1', N1)

    # ---------------------------------------------------------------- shot 2: the cooking view
    bpy.ops.wm.open_mainfile(filepath=os.path.join(HERE, 'CookView', 'cook_view_wc.blend' if WCV else 'cook_view.blend'))
    scene = bpy.context.scene
    setup_render(scene)
    cam = scene.camera
    start = cam.location.copy()
    N2 = int(os.environ.get('N2', 6 * FPS))
    L0 = cam.data.lens
    key_camera(cam, [(1, start, L0), (N2, start + Vector((0.3, 0.55, -0.12)), L0 * 1.12)])
    wok_food = next((o for o in scene.objects if o.name.startswith('SM_D01_wok') and not o.name.endswith('_line')), None)
    wok_line = next((o for o in scene.objects if o.name.startswith('SM_D01_wok') and o.name.endswith('_line')), None)
    flames = [o for o in scene.objects if o.name.startswith('Flame') and not o.name.endswith('_line')]
    z0 = wok_food.location.z if wok_food else 0
    for f in range(1, N2 + 1, 3):   # the dish tossed in the wok, the fire flickering
        t = f / FPS
        hop = abs(math.sin(t * 5.5)) * 0.035
        if wok_food:
            wok_food.location.z = z0 + hop
            wok_food.keyframe_insert('location', frame=f)
        if wok_line:
            wok_line.location.z = hop
            wok_line.keyframe_insert('location', frame=f)
        for i, fl in enumerate(flames):
            s = 1 + 0.18 * math.sin(t * 11 + i * 1.7)
            fl.scale = (1, 1, s)
            fl.keyframe_insert('scale', frame=f)
    d2 = render_frames(scene, 'shot2', N2)


# ---------------------------------------------------------------- join into one MP4
bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.resolution_x, scene.render.resolution_y = W, H
scene.render.fps = FPS
seq = scene.sequence_editor_create()
strips = seq.strips if hasattr(seq, 'strips') else seq.sequences
frame = 1
for i, d in enumerate((d1, d2)):
    files = sorted(f for f in os.listdir(d) if f.endswith('.png'))
    st = strips.new_image(name=f'shot{i}', filepath=os.path.join(d, files[0]), channel=1 + i, frame_start=frame)
    for f in files[1:]:
        st.elements.append(f)
    if i > 0:   # a short cross-fade between the shots
        st.frame_start = frame - 12
        try:
            st.blend_type = 'CROSS'
        except (TypeError, AttributeError):
            pass
    frame = st.frame_final_end
scene.frame_start, scene.frame_end = 1, frame - 1
if hasattr(scene.render.image_settings, 'media_type'):   # Blender 5: pick video output first
    scene.render.image_settings.media_type = 'VIDEO'
scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.ffmpeg.constant_rate_factor = 'HIGH'
scene.render.filepath = OUT
os.makedirs(os.path.dirname(OUT), exist_ok=True)
bpy.ops.render.render(animation=True)
print('[video] wrote', OUT, flush=True)
