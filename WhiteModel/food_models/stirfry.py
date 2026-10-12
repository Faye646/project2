"""炒菜与煲: D06, D07, D08, D13, D15, D21."""
import json
import math
import os
import random

import bmesh
import bpy
from mathutils import Matrix, Vector

from .core import *  # noqa: F401,F403
from .bowls import scallion_chunk
from mathutils.bvhtree import BVHTree

PALETTE.update({
    'LizhiGroove': ('#a63e1d', '#7a2a12'),   # the dark cuts between the raised squares of scored kidney
    'LizhiSlit': ('#e2ae62', '#bf8a45'),    # the slits through slices of bamboo shoot
    'LizhiGreens': ('#4a8c3c', '#31692b'),  # its deep green leaves of choy sum
    'BraisedShiitake': ('#6b3526', '#46211a'),   # 佛跳墙's shiitake, braised dark
    'BellyLean': ('#e3955a', '#c06f38'),   # the orange lean between the fat of braised pork belly
    'StewSkin': ('#fbd287', '#e3ac58'),    # the yellow skin of stewed chicken
    'ChickenFiber': ('#eca36b', '#c97d46'),   # the grain of stewed chicken meat
    'StewBreast': ('#fbd8ab', '#e6b282'),  # stewed chicken meat, peach
    'TomatoCut': ('#ea4824', '#bf2c16'),   # 番茄炒蛋's wedges' cut faces: as red as the skin in the art, a shade deeper
    'EggCrease': ('#f4ad3e', '#dc8a2c'),   # the deep gold showing in the creases between pieces of scrambled egg
    'ScallionPale': ('#e6edb4', '#c6d08c'),   # the white part of a scallion, cut
})
GLOSS.update({'LizhiGroove': 0.8, 'LizhiSlit': 0.3, 'LizhiGreens': 0.5, 'BraisedShiitake': 0.8, 'BellyLean': 0.6,
              'StewSkin': 0.6, 'ChickenFiber': 0.4, 'StewBreast': 0.5, 'TomatoCut': 0.6, 'EggCrease': 0.3})
VIVID.update({'EggCrease': 0.6})
DETAIL.update({'TomatoCut': ('food_seeds', 18, '#fcc050', 0.8, 0.2)})   # the seeds in their jelly


def round_dish(p, r, h, n=64, sx=1.0, rim=0.005, floor=0.01, foot=0.55, belly=0.82, yaw=0.0):
    """A 青瓷 dish or shallow bowl as the art draws them: a foot ring, a wall swelling out to a thick rolled rim (a
    bead of radius `rim`), and the inside sloping down to a flat floor at `floor`; sx stretches it across (an oval
    dish), yaw turns it. n segments keep its rim a smooth ellipse. Returns the floor height."""
    prof = [(0.0, 0.0), (foot * r - 0.004, 0.0), (foot * r, 0.003), (foot * r + 0.002, 0.007),
            (r * belly, h * 0.52), (r * 0.95, h * 0.84)]
    prof += [(r - rim + rim * math.cos(math.radians(a)), h - rim + rim * math.sin(math.radians(a)))
             for a in (-35, 0, 40, 90, 140, 180)]
    prof += [(r - 2 * rim - 0.003, h - rim - 0.006), (r * 0.7, floor + 0.004), (r * 0.6, floor), (0.0, floor)]
    p.lathe(prof, 'Celadon', n=n, close_ends=False, M=Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Diagonal((sx, 1.0, 1.0, 1.0)))
    return floor


def dish_rho(x, y, sx=1.0, yaw=0.0):
    """How far (x, y) is from the middle of round_dish(sx=sx, yaw=yaw), in the units of its radius r."""
    c, s_ = math.cos(-yaw), math.sin(-yaw)
    return math.hypot((c * x - s_ * y) / sx, s_ * x + c * y)


def tuck_in(p, R, sx=1.0, yaw=0.0, vessel=('Celadon', 'ClayPot')):
    """Food that passes out through its dish's wall, where it would show from behind or below as the dish turns in the
    game, is drawn back into the ceramic, where no side shows it: each vertex below the outside of the wall is lifted
    just inside it, and one past the rim (R across, before sx) but below its top is first drawn in to the rim. What
    shows inside the dish stays as it is."""
    bm = p.bm
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    ids = {p.mats.index(m) for m in vessel if m in p.mats}
    faces = [f for f in bm.faces if f.material_index in ids]
    wall = {v.index for f in faces for v in f.verts}
    tree = BVHTree.FromPolygons([v.co.copy() for v in bm.verts], [[v.index for v in f.verts] for f in faces])

    def column(x, y):   # the heights of the dish's surfaces straight above and below (x, y), lowest first
        zs, o = [], Vector((x, y, 1.0))
        for _ in range(12):
            hit = tree.ray_cast(o, Vector((0.0, 0.0, -1.0)))[0]
            if hit is None:
                break
            zs.append(hit.z)
            o = hit - Vector((0.0, 0.0, 1e-5))
        return zs[::-1]
    for v in bm.verts:
        if v.index in wall:
            continue
        x, y, z = v.co
        rho = dish_rho(x, y, sx, yaw)
        k = min(1.0, (R - 0.002) / rho) if rho > 1e-6 else 1.0
        zs = column(x * k, y * k)
        if not zs or (k < 1.0 and z > zs[-1]):   # nothing there, or lying over the rim
            continue
        lo = zs[0]
        hi = zs[1] if len(zs) > 1 else lo + 0.004
        m = min(0.0015, (hi - lo) / 2)   # well inside, so that the faces between stay in too
        if k < 1.0:
            v.co = Vector((x * k, y * k, min(max(z, lo + m), hi - m)))
        elif z < lo + m:
            v.co.z = lo + m


def flat_on(p, z=0.0):
    """Nothing below z: the bottoms of pieces sunk in a wok's pool of gravy, hidden in it, are flattened onto its floor."""
    for v in p.bm.verts:
        v.co.z = max(v.co.z, z)


def round_plate(p, r=0.1, h=0.022, n=64):
    """core's plate() made round and smooth: n segments keep it a circle, the foot is eased and the rim rolled into a
    round bead. The inside is plate()'s (the floor at 0.008 out to 0.62 r, the wall up to height h at r - 0.008), so
    plate_sauce() and onto_plate() fit it."""
    prof = [(0.0, 0.0), (r * 0.55, 0.0), (r * 0.585, 0.0012), (r * 0.6, 0.004), (r * 0.75, h * 0.42 + 0.0005),
            (r * 0.9, h * 0.8), (r - 0.0015, h - 0.0022)]
    prof += [(r - 0.004 + 0.004 * math.cos(math.radians(a)), h - 0.0002 + 0.0024 * math.sin(math.radians(a)))
             for a in (-10, 30, 70, 110, 150, 180)]
    prof += [(r * 0.62, 0.008), (0.0, 0.008)]
    p.lathe(prof, 'Celadon', n=n, close_ends=False)


def round_plate_inner(rho, r=0.1, h=0.034):
    """The height of round_plate(r, h)'s inside at a distance rho from its middle: the floor, then the wall's
    straight slope up to the rim."""
    f0, f1 = r * 0.62, r - 0.008
    return 0.008 + max(0.0, min(rho, f1) - f0) / (f1 - f0) * (h - 0.0082)


def round_wedge(p, M, r=0.03, w=0.5, edge=0.003, cut='TomatoFlesh'):
    """The first 番茄炒蛋's tomato wedge, for soft(): cut from a tomato along its axis (local z), the skin round the
    outside towards local x, the two cut faces (in `cut`) meeting at the core; placed by M. Every edge is chamfered `edge`
    wide first, so that the subdivision rounds it off (圆角) while the wedge keeps its shape."""
    tmp = bmesh.new()
    rings = [[tmp.verts.new(Vector((r * math.sin(t) * math.cos(f), r * math.sin(t) * math.sin(f),
                                    -0.85 * r * math.cos(t)))) for f in (-w, 0.0, w)]
             for t in (math.pi / 4, math.pi / 2, 3 * math.pi / 4)]
    bot, top = (tmp.verts.new(Vector((0.0, 0.0, s * 0.85 * r))) for s in (-1, 1))
    skin, cut = p._mi('TomatoRed'), p._mi(cut)
    for j in range(2):   # the skin, in two strips
        fs = [tmp.faces.new((bot, rings[0][j + 1], rings[0][j]))]
        fs += [tmp.faces.new((rings[i][j], rings[i][j + 1], rings[i + 1][j + 1], rings[i + 1][j])) for i in range(2)]
        fs.append(tmp.faces.new((rings[2][j], rings[2][j + 1], top)))
        for f in fs:
            f.material_index = skin
    for j in (0, 2):     # the cut faces
        tmp.faces.new([bot] + [rg[j] for rg in rings] + [top]).material_index = cut
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    new = set(bmesh.ops.bevel(tmp, geom=tmp.edges[:], offset=edge, offset_type='OFFSET', segments=1, profile=0.5,
                              affect='EDGES', clamp_overlap=True)['faces'])
    while new:   # the chamfers take the colour of the skin where they touch it, else of the cut face
        done = set()
        for f in new:
            near = {g.material_index for e in f.edges for g in e.link_faces if g not in new}
            if near:
                f.material_index = skin if skin in near else cut
                done.add(f)
        if not done:
            break
        new -= done
    vmap = {v: p.bm.verts.new(M @ v.co) for v in tmp.verts}
    for f in tmp.faces:
        p.bm.faces.new([vmap[v] for v in f.verts]).material_index = f.material_index
    tmp.free()


TRACED_D06 = os.path.join(os.path.dirname(__file__), 'traced_D06.json')


def lean_normals(ob, mats, towards, k):
    """Leans the shading normals of the faces in `mats` toward `towards` by k (unit vectors added), so that the
    light from in front and above falls on them more fully: the scrambled egg reads light and soft as the art paints
    it, its shape and outline (from the geometry) unchanged. Bakes ob's modifiers first."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    ob.modifiers.clear()
    old, ob.data = ob.data, me
    name = old.name
    bpy.data.meshes.remove(old)
    me.name = name
    normals = [Vector(c.vector) for c in me.corner_normals]
    ids = {i for i, m in enumerate(me.materials) if m.name[2:] in mats}
    t = Vector(towards).normalized()
    for poly in me.polygons:
        if poly.material_index in ids:
            for li in poly.loop_indices:
                normals[li] = (normals[li] + t * k).normalized()
    me.normals_split_custom_set(normals)


def fanqie_chaodan(col, wok=False):
    """番茄炒蛋 traced from its art (trace_d06.py writes traced_D06.json): each loose, irregular piece of scrambled
    egg follows an outline traced in the art, raised as a soft fold leaning to the eye with the art's shading in
    relief, a thin crease where it meets the next; the tomato wedges are fitted to the art's, a seeded cut face turned
    to the eye as it paints them; chopped scallion, green and white, lies where the art has it. Under it all a heap
    of deep gold shows in the creases. On a deep round celadon plate (the first version's), or level on the wok's
    floor."""
    data = json.load(open(TRACED_D06, encoding='utf-8'))
    p = Part()
    if wok:
        pool(p, 0.066, 0.004, 'TomatoJuice', n=48, seed=6, wobble=0.08)
    else:
        round_plate(p, r=0.1, h=0.034, n=64)
        plate_sauce(p, 'TomatoJuice', h=0.034, n=64, seed=6, wobble=0.2)
    n0 = len(p.bm.verts)
    el = math.radians(data['camera']['el'])
    view = Vector((0.0, -math.cos(el), math.sin(el)))      # towards the camera the art was drawn from
    filler = data['filler']
    traced_surface(p, filler['verts'], filler['tris'], 'EggCrease',
                   lambda a, b, c: (b - a).cross(c - a).z)
    with p.soft():
        for M in data['wedges']:
            round_wedge(p, Matrix(M), r=1.0, w=0.5, edge=0.1, cut='TomatoCut')
    for piece in data['egg']:
        traced_surface(p, piece['verts'], piece['tris'], 'EggYolk',
                       lambda a, b, c: (b - a).cross(c - a).dot(view))
    for s in data['scallions']:
        scallion_chunk(p, Vector(s['c']), s['yaw'], r=s['r'], length=s['length'], lite=True, n=6,
                       mat='ScallionPale' if s['pale'] else 'Scallion')
    if wok:   # the food was traced lying in the plate, up its wall at the edge: on the wok's flat floor it lies level
        p.bm.verts.ensure_lookup_table()
        for v in p.bm.verts[n0:]:
            v.co.z -= round_plate_inner(math.hypot(v.co.x, v.co.y))
        flat_on(p)   # what dips below the wok's floor, hidden in the juice, flattened onto it
    else:
        tuck_in(p, 0.1)   # what reaches the wall stays inside it
    ob = p.finish('SM_D06' + ('_wok' if wok else ''), col, sharp=None)
    lean_normals(ob, {'EggYolk'}, (-0.15, -0.5, 0.85), 0.6)   # the egg lit as fully as the art paints it
    return ob


ICON_LIGHT = Vector((-0.3, -0.8, 0.52)).normalized()   # the sun the food images are rendered in (preview_wc's)


def lower_food(p, n0, dz, path=None):
    """The food added since p had n0 vertices lowered as one by dz (from the dish's floor onto the wok's), nothing
    of it under the wok's floor; the heap's closed underside (traced from path: the feet of its skirt and the floor
    between them) laid flat on the wok's floor, its skirt straight down from its edge (traced_dish's lowering
    would slide the feet away along the lines of sight, which turns the skirt's front in under the heap)."""
    p.bm.verts.ensure_lookup_table()
    for v in p.bm.verts[n0:]:
        v.co.z = max(v.co.z - dz, 0.0)
    if path:
        i = n0
        for piece in json.load(open(path, encoding='utf-8'))['pieces']:
            if piece.get('closed'):
                feet = set(p.bm.verts[i + piece['closed']:i + len(piece['verts'])])
                for v in feet:
                    v.co.z = 0.0
                rim = p.bm.verts[i:i + piece['rim']]
                order = {v: k for k, v in enumerate(rim)}
                n = len(rim)
                area = sum(a.co.x * b.co.y - b.co.x * a.co.y for a, b in zip(rim, rim[1:] + rim[:1]))
                for f in {f for v in feet for f in v.link_faces}:   # each face turned out again, the floor down
                    f.normal_update()
                    top = sorted(order[v] for v in f.verts if v in order)
                    if not top:
                        bad = f.normal.z > 0
                    else:   # out from the outline's edge it hangs from (the outline runs anticlockwise if area > 0)
                        a = top[0]
                        if len(top) == 2 and top[0] == 0 and top[1] == n - 1:
                            a = n - 1
                        e = rim[(a + 1) % n].co - rim[a].co
                        out = Vector((e.y, -e.x, 0.0)) if area > 0 else Vector((-e.y, e.x, 0.0))
                        bad = f.normal.x * out.x + f.normal.y * out.y < 0
                    if bad:
                        f.normal_flip()
            i += len(piece['verts'])


def traced_tones(path, n0, skip=()):
    """The art's light and shade (-1..1) at each front vertex of the pieces traced_dish(p, path) adds when p had n0
    vertices: {vertex index: tone}."""
    data = json.load(open(path, encoding='utf-8'))
    out, i = {}, n0
    for piece in data['pieces']:
        if piece['name'] in skip:
            continue
        for j, t in enumerate(piece.get('tone', [])):
            out[i + j] = t
        i += len(piece['verts'])
    return out


def art_shading(ob, tones, k=0.85, light=ICON_LIGHT, mid=0.62, span=0.33, span_dark=0.0):
    """Paints the art's light and shade into the shading normals of the vertices in `tones` ({index: -1..1}): each
    normal turned toward the light or away from it, in the plane through it and the light, until the light falls
    on it as fully as the art lights that spot (mid + span × tone of full; where the art is darker than the middle,
    only span_dark: its deep colours are tinted in), k of the way from where the surface itself would have it. The shape and the outline stay the geometry's; the food reads lit as the art paints it,
    its pale tops and deep sides, in the shader's own light steps. Bakes ob's modifiers first."""
    dg = bpy.context.evaluated_depsgraph_get()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(dg), preserve_all_data_layers=True, depsgraph=dg)
    ob.modifiers.clear()
    old, ob.data = ob.data, me
    name = old.name
    bpy.data.meshes.remove(old)
    me.name = name
    normals = [Vector(c.vector) for c in me.corner_normals]
    smooth = [Vector(v.vector) for v in me.vertex_normals]   # round, as the piece is: not the faces' own
    for li, loop in enumerate(me.loops):
        t = tones.get(loop.vertex_index)
        if t is None:
            continue
        n = smooth[loop.vertex_index]
        cg = n.dot(light)
        c = max(-0.95, min(0.99, cg + k * (mid + (span if t > 0 else span_dark) * t - cg)))
        perp = n - light * cg
        if perp.length < 1e-6:
            perp = light.orthogonal()
        perp.normalize()
        normals[li] = (light * c + perp * math.sqrt(max(0.0, 1.0 - c * c))).normalized()
    me.normals_split_custom_set(normals)


def _smooth01(e0, e1, x):
    t = min(max((x - e0) / (e1 - e0), 0.0), 1.0)
    return t * t * (3 - 2 * t)


def shade_affine(c, gloss):
    """How the watercolour shader (preview_wc, as Unity's WatercolorLit) turns a surface's colour into what shows,
    for a colour taking the vertex tint fully and none of the vivid boost, lit at n·L = c: per channel, linear, an
    affine map shown = A·colour + B (its light steps and bluish shadow, the warm wash of its lit side, the gloss's
    sheen and glint)."""
    lum = 0.25 + 0.75 * max(c, 0.0)
    steps = 0.45 * _smooth01(0.25, 0.42, lum) + 0.37 * _smooth01(0.42, 0.62, lum) + 0.18 * _smooth01(0.62, 0.9, lum)
    blue = (0.34, 0.36, 0.55)
    A = [(1 - steps) * 0.432 + steps] * 3
    B = [(1 - steps) * 0.2 * b for b in blue]
    f = min(max((steps - 0.85) * 5, 0.0), 1.0) * 0.6   # the wash of a tinted colour: itself, lighter
    A = [a_ * (1 - f) + k_ * f for a_, k_ in zip(A, (1.15, 1.07, 0.97))]
    B = [b_ * (1 - f) for b_ in B]
    if gloss > 0:
        dist = 2 * math.sin(abs(math.acos(max(-1.0, min(1.0, c))) - math.radians(8.8)) / 2)
        g1 = (1 - _smooth01(0.25, 0.6, dist)) * gloss * 0.5
        A = [a_ * (1 + 0.12 * g1) for a_ in A]
        B = [b_ * (1 + 0.12 * g1) + 0.04 * g1 for b_ in B]
        g2 = (1 - _smooth01(0.1, 0.16, dist)) * gloss * 0.85
        A = [a_ * (1 - g2) for a_ in A]
        B = [b_ * (1 - g2) + w_ * g2 for b_, w_ in zip(B, (1.0, 0.98, 0.92))]
    return A, B


def art_colours(p, path, n0, mats, ink, w=0.92, k=0.85, light=ICON_LIGHT, mid=0.62, span=0.33, span_dark=0.0,
                skip=()):
    """Paints the art's own colour (the trace's 'rgb' at each front vertex) onto the pieces traced_dish(p, path) added
    when p had n0 vertices, through the vertex tint, so that what shows is the art's colour there: each corner's tint
    worked back through the shader (shade_affine) at the light its shading normal will have (art_shading's, from the
    trace's 'tone'), for the faces in `mats` (the colours taking the tint fully, with no vivid boost). The ink line
    traced_dish drew round each piece stays."""
    data = json.load(open(path, encoding='utf-8'))
    bm = p.bm
    bm.verts.ensure_lookup_table()
    bm.normal_update()
    lay = bm.loops.layers.float_color.get('Tint') or bm.loops.layers.float_color.new('Tint')
    ids = {p.mats.index(m): m for m in mats if m in p.mats}
    ink_lin = linear(ink)
    target = {}
    i = n0
    for piece in data['pieces']:
        if piece['name'] in skip:
            continue
        rgb, tone = piece.get('rgb'), piece.get('tone')
        if rgb:
            for j, c in enumerate(rgb):
                target[i + j] = (c, tone[j] if tone else 0.0)
        i += len(piece['verts'])
    for v in bm.verts[n0:]:
        got = target.get(v.index)
        if got is None:
            continue
        (r, g, b), t = got
        cg = v.normal.dot(light)
        c = max(-0.95, min(0.99, cg + k * (mid + (span if t > 0 else span_dark) * t - cg)))
        goal = linear('#%02x%02x%02x' % (r, g, b))
        for loop in v.link_loops:
            key = ids.get(loop.face.material_index)
            if key is None:
                continue
            cur = loop[lay]
            if cur[3] < 0.7 and all(abs(cur[ch] - ink_lin[ch]) < 1e-3 for ch in range(3)):   # the ink line: kept
                continue
            A, B = shade_affine(c, GLOSS.get(key, GLOSS_DEFAULT))
            lit = linear(PALETTE[key][0])
            col = []
            for ch in range(3):
                need = (goal[ch] - B[ch]) / max(A[ch], 1e-3)
                col.append(min(max((need - lit[ch] * (1 - w)) / w, 0.0), 1.0))
            loop[lay] = (col[0], col[1], col[2], 1.0 - w)


TRACED_D07 = os.path.join(os.path.dirname(__file__), 'traced_D07.json')
# 宫保鸡丁 traced from its art: the glazed chicken, the dried chillies, the scallion green and pale, the sauce under them
PALETTE.update({'GongbaoChicken': ('#fe8a29', '#d4721e'),   # the diced chicken, golden-orange in its glaze
                'GongbaoGlaze': ('#c4300e', '#921f09'),     # the red sauce caught on it
                'GongbaoGlint': ('#fff4dc', '#f0dcb4'),     # the glints of the glaze, as the art paints them
                'GongbaoChili': ('#c80a02', '#98190c'),     # the dried chillies, glossy red
                'GongbaoChiliGlint': ('#f6cfc4', '#e4a89c'),   # their glints, pink-white
                'GongbaoSeed': ('#f4c45a', '#d69a38'),      # their seeds, in a cut end
                'GongbaoCavity': ('#701606', '#4c0e04'),    # and the dark inside of a cut end
                'GongbaoScallion': ('#747f10', '#4e5a08'),  # the green scallion
                'GongbaoScallionCut': ('#e2e8a6', '#c2ca7e'),   # its cut ends, pale
                'GongbaoWhite': ('#f5d37c', '#dcb45a'),     # the pale scallion
                'GongbaoRing': ('#d6c04a', '#b49c2c'),      # its yellow-green heart and rings, end on
                'GongbaoSauce': ('#7f0c00', '#560800')})    # the dark red sauce under it all, deep in the creases
GLOSS.update({'GongbaoChicken': 0.6, 'GongbaoGlaze': 0.8, 'GongbaoGlint': 0.8, 'GongbaoChili': 0.8,
              'GongbaoChiliGlint': 0.8, 'GongbaoSeed': 0.3, 'GongbaoCavity': 0.5, 'GongbaoScallion': 0.6,
              'GongbaoScallionCut': 0.3, 'GongbaoWhite': 0.5, 'GongbaoRing': 0.3, 'GongbaoSauce': 0.5})
VIVID.update({'GongbaoChicken': 0.0, 'GongbaoGlint': 0.2, 'GongbaoChiliGlint': 0.2, 'GongbaoChili': 0.0,
              'GongbaoSauce': 0.0, 'GongbaoScallion': 0.0, 'GongbaoWhite': 0.0, 'GongbaoScallionCut': 0.4})
VTINT.update(dict.fromkeys(('GongbaoChicken', 'GongbaoGlaze', 'GongbaoGlint', 'GongbaoChili', 'GongbaoChiliGlint',
                            'GongbaoSeed', 'GongbaoCavity', 'GongbaoScallion', 'GongbaoScallionCut', 'GongbaoWhite',
                            'GongbaoRing', 'GongbaoSauce'), 1.0))


def gongbao_jiding(col, wok=False):
    """宫保鸡丁 (简化版) traced from its art (trace_d07.py writes traced_D07.json): a heap of glazed diced chicken, dried
    red chillies (some cut open, their seeds showing) and lengths of scallion, green and pale, in a dark red sauce on
    an oval celadon dish; every piece follows its outline in the art, a rounded mound on the heap of sauce under
    them, its colours painted where the art has them and the art's ink line round it. In the wok, the same heap on
    the wok's floor."""
    from .plates import traced_dish   # here: plates imports bowls
    p = Part()
    r, h, sx = 0.1, 0.03, 0.93
    if wok:
        pool(p, 0.07, 0.0035, 'GongbaoSauce', n=40, seed=7, wobble=0.06)
    else:
        round_dish(p, r, h, sx=sx, n=40)
    n0 = len(p.bm.verts)
    traced_dish(p, TRACED_D07, ink='#3c1006')
    if wok:
        lower_food(p, n0, 0.01, TRACED_D07)
    else:
        tuck_in(p, r, sx)
    art_colours(p, TRACED_D07, n0, ('GongbaoChicken', 'GongbaoChili', 'GongbaoScallion', 'GongbaoWhite',
                                    'GongbaoSauce'), '#3c1006')
    ob = p.finish('SM_D07' + ('_wok' if wok else ''), col, sharp=None)
    art_shading(ob, traced_tones(TRACED_D07, n0))
    return ob


TRACED_D08 = os.path.join(os.path.dirname(__file__), 'traced_D08.json')
# 可乐鸡翅 traced from its art: the cola-glazed wings, their cut ends, the scallion and ginger, the sauce under them
PALETTE.update({'ColaGlaze': ('#dc5d15', '#a8400c'),      # the wings' glossy amber glaze
                'ColaWingEnd': ('#5c2410', '#3e160a'),    # the dark cut end of a wing, the bone in the meat
                'ColaFold': ('#6e2008', '#4c1404'),       # the deep folds of the skin, dark red-brown
                'ColaGlint': ('#fbe6c8', '#ecc8a0'),      # the glints on the glaze
                'ColaPool': ('#712200', '#4c1600'),       # the dark cola sauce round them
                'ColaScallion': ('#8b9439', '#68702a'),   # the scallion lengths
                'ColaGinger': ('#ffd064', '#dcaa40')})    # the ginger strips
GLOSS.update({'ColaGlaze': 0.8, 'ColaFold': 0.6, 'ColaWingEnd': 0.5, 'ColaGlint': 0.8, 'ColaPool': 0.6, 'ColaScallion': 0.6,
              'ColaGinger': 0.3})
VIVID.update({'ColaGlaze': 0.0, 'ColaGlint': 0.2, 'ColaPool': 0.0, 'ColaScallion': 0.0, 'ColaGinger': 0.0})
VTINT.update(dict.fromkeys(('ColaGlaze', 'ColaFold', 'ColaWingEnd', 'ColaGlint', 'ColaPool', 'ColaScallion', 'ColaGinger'), 1.0))
DETAIL.update({'ColaGlaze': ('food_pores', 16, '#8a3410', 0.3, 0.5)})


def kele_jichi(col, wok=False):
    """可乐鸡翅 traced from its art (trace_d08.py writes traced_D08.json): five cola-braised wings, glossy amber, two
    rows on an oval celadon dish in their dark sauce, lengths of scallion and strips of ginger over them; every piece
    follows its outline in the art, the wings plump rounded mounds with the art's lit skin and deep folds, their cut
    ends dark, the art's ink line round each. In the wok, the same on the wok's floor."""
    from .plates import traced_dish   # here: plates imports bowls
    p = Part()
    r, h, sx, yaw = 0.105, 0.026, 0.84, -0.68   # an oval dish turned so its right end sits higher, as drawn
    if wok:
        pool(p, 0.075, 0.0035, 'ColaPool', n=40, seed=8, wobble=0.06)
    else:
        round_dish(p, r, h, sx=sx, n=48, floor=0.01, yaw=yaw)
    n0 = len(p.bm.verts)
    traced_dish(p, TRACED_D08, ink='#3a1606')
    if wok:
        lower_food(p, n0, 0.01, TRACED_D08)
    else:
        tuck_in(p, r, sx, yaw)
    art_colours(p, TRACED_D08, n0, ('ColaGlaze', 'ColaPool', 'ColaScallion', 'ColaGinger'), '#3a1606')
    ob = p.finish('SM_D08' + ('_wok' if wok else ''), col, sharp=None)
    art_shading(ob, traced_tones(TRACED_D08, n0))
    return ob


def casserole(p, r, h, fill_z, n=48, rim=0.007, sx=1.0, yaw=0.0, lugs=(math.pi, 0.0), mat='ClayPot', fill='StewGravy',
              foot=0.6, belly=0.86, lug=(0.0125, 0.021, 0.0075), lug_z=0.003):
    """A clay casserole (砂锅): a low foot, a wall swelling out to a thick rounded rim (a bead of radius `rim`), the
    inside down to the stew's surface at fill_z, which closes it; flat rounded lug handles at the angles `lugs`. n
    segments keep the rim a smooth ellipse; each lug lug (out, along the rim, thick: half sizes) lug_z under the rim's
    top. Returns the inside radius at the surface."""
    M = Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Diagonal((sx, 1.0, 1.0, 1.0))
    r_in = r - 2 * rim - 0.004
    prof = [(0.0, 0.0), (r * foot, 0.0), (r * foot + 0.004, 0.004), (r * foot + 0.007, 0.009), (r * belly, h * 0.32),
            (r * (belly + 2) / 3, h * 0.68)]
    prof += [(r - rim + rim * math.cos(math.radians(a)), h - rim + rim * math.sin(math.radians(a)))
             for a in (-40, 0, 45, 90, 135, 180)]
    prof += [(r_in, h - rim - 0.01), (r_in - 0.002, fill_z)]
    p.lathe(prof, mat, n=n, close_ends=False, M=M)
    p.lathe([(r_in - 0.002, fill_z), (0.0, fill_z + 0.001)], fill, n=n, close_ends=False, M=M)
    with p.soft():   # flat rounded lugs, level with the rim
        for a in lugs:
            c = M @ Vector((r * math.cos(a), r * math.sin(a), h - rim - lug_z))
            out = Vector((c.x, c.y, 0.0)).normalized()
            p.blob(c + out * 0.006, 1.0, mat, squash=lug, segs=(8, 4), rot=math.atan2(out.y, out.x))
    return r_in - 0.002


TRACED_D13 = os.path.join(os.path.dirname(__file__), 'traced_D13.json')
# 土豆炖肉 traced from its art: the potatoes, the radish, the braised pork belly and the scallion in the gravy
PALETTE.update({'StewSpud': ('#fbb427', '#dc8e18'),       # the braised potato, golden
                'StewRadish': ('#f1b96c', '#d4974c'),     # the radish, translucent cream-gold from the gravy
                'StewRadishLine': ('#e6a24e', '#c8843a'),   # the fine lines through its flesh
                'StewPork': ('#be4f1c', '#8e3410'),       # the braised pork belly's lean and skin, red-brown
                'StewFat': ('#f4c28a', '#d8a066'),        # the pale layers of fat between
                'StewGlint': ('#fff2d6', '#f0d8b0'),      # glints on the potato and the pork
                'StewScallion': ('#727a17', '#525a0c'),   # the scallion bits
                'StewGravyArt': ('#f2a84d', '#d48a30')})  # the golden gravy, as the art paints it
GLOSS.update({'StewSpud': 0.4, 'StewRadish': 0.5, 'StewRadishLine': 0.4, 'StewPork': 0.6, 'StewFat': 0.5,
              'StewGlint': 0.8, 'StewScallion': 0.5, 'StewGravyArt': 0.7})
VIVID.update(dict.fromkeys(('StewSpud', 'StewRadish', 'StewPork', 'StewScallion', 'StewGravyArt'), 0.0))
VIVID.update({'StewGlint': 0.2, 'StewFat': 0.4, 'StewRadishLine': 0.5})
VTINT.update(dict.fromkeys(('StewSpud', 'StewRadish', 'StewRadishLine', 'StewPork', 'StewFat', 'StewGlint',
                            'StewScallion', 'StewGravyArt'), 1.0))
D13_POT = dict(r=0.1, h=0.0696, fill_z=0.0595, sx=0.933, rim=0.0045, lugs=(math.pi, 0.0), foot=0.643, belly=0.845,
               lug=(0.0103, 0.0281, 0.0075), lug_z=0.0043)   # fitted with the camera to the art (trace_d13.py)


def tudou_dunrou(col, wok=False):
    """土豆炖肉 traced from its art (trace_d13.py writes traced_D13.json): chunks of potato, radish and braised pork
    belly with scallion bits in golden gravy in a deep clay pot with two flat lugs, fitted to the art; every piece
    follows its outline in the art, a rounded mound rising out of the gravy, the art's own colours painted on (the
    pork's pale fat layers, the radish's lines, the glints) and its ink line round each. In the wok, the same
    lowered onto the wok's floor in a pool of the gravy."""
    from .plates import traced_dish   # here: plates imports bowls
    p = Part()
    d = D13_POT
    if wok:
        zg = 0.008
        p.lathe([(0.075, 0.0), (0.075, zg), (0.0, zg + 0.001)], 'StewGravyArt', n=40, close_ends=False)
    else:
        casserole(p, d['r'], d['h'], d['fill_z'], sx=d['sx'], rim=d['rim'], lugs=d['lugs'], foot=d['foot'],
                  belly=d['belly'], lug=d['lug'], lug_z=d['lug_z'], fill='StewGravyArt')
    n0 = len(p.bm.verts)
    traced_dish(p, TRACED_D13, ink='#4a2008', lower=(lambda x, y: d['fill_z'] - 0.008) if wok else None)
    if wok:
        flat_on(p)
    else:
        tuck_in(p, d['r'], d['sx'], vessel=('ClayPot',))
    art_colours(p, TRACED_D13, n0, ('StewSpud', 'StewRadish', 'StewPork', 'StewScallion', 'StewGravyArt'), '#4a2008')
    ob = p.finish('SM_D13' + ('_wok' if wok else ''), col, sharp=None)
    art_shading(ob, traced_tones(TRACED_D13, n0))
    return ob


SIN_EL, COS_EL = math.sin(ART_EL), math.cos(ART_EL)


def from_art(m, u, v, z):
    """Model (x, y) of what the art shows at pixel (u, v) of its full-size image, if it lies at height z. m = (k, u0,
    v0) from fitting the model onto the art (fitmap.py): the origin shows at (u0, v0) and 1 m is k pixels."""
    k, u0, v0 = m
    return (u - u0) / k, ((v0 - v) / k - z * COS_EL) / SIN_EL


def art_seat(m, u, v, support, lift=0.0):
    """Where a piece the art shows centred at pixel (u, v) is, `lift` above the surface support(x, y): its depth and
    height worked out together, since a higher piece shows further up."""
    z = support(*from_art(m, u, v, 0.02)) + lift
    for _ in range(5):
        x, y = from_art(m, u, v, z)
        z = support(x, y) + lift
    return Vector((x, y, z))


def bvh_since(p, n0):
    """A BVH tree of what was added to p since it had n0 vertices (one piece), for laying things on its surface."""
    bm = p.bm
    bm.verts.ensure_lookup_table()
    bm.verts.index_update()
    verts = [v.co.copy() for v in bm.verts[n0:]]
    polys = [[v.index - n0 for v in f.verts] for f in bm.faces if f.verts[0].index >= n0]
    return BVHTree.FromPolygons(verts, polys)


def groove(p, tree, pts, width=0.0024, lift=0.0006, mat='LizhiGroove', keep=None):
    """A dark cut drawn on a surface (a BVH tree) through points near it: snapped onto it, a ribbon `width` wide and
    `lift` proud of it, facing out (nothing sees its back, which lies on the surface). Stretches where keep(point,
    normal) fails at both ends are left out."""
    snap = []
    for q in pts:
        loc, nrm, _, _ = tree.find_nearest(Vector(q))
        snap.append((loc, nrm.normalized()))
    ok = [keep is None or keep(q, n) for q, n in snap]
    runs, run = [], None
    for i in range(len(snap) - 1):   # runs of kept stretches
        if ok[i] or ok[i + 1]:
            run = run or [i]
            run.append(i + 1)
        elif run:
            runs.append(run)
            run = None
    if run:
        runs.append(run)
    for run in runs:
        if len(run) < 2:
            continue
        tmp = bmesh.new()
        sides = []
        for j, i in enumerate(run):
            q, n = snap[i]
            a = snap[run[min(j + 1, len(run) - 1)]][0] - snap[run[max(j - 1, 0)]][0]
            s = n.cross(a).normalized() * width / 2
            sides.append([tmp.verts.new(q + n * lift + s * k) for k in (1, -1)])
        for (a, b), (c, d) in zip(sides, sides[1:]):
            f = tmp.faces.new((a, b, d, c))
            f.normal_update()
            if f.normal.dot(snap[run[0]][1] + snap[run[-1]][1]) < 0:
                f.normal_flip()
        p._commit(tmp, mat)


LIZHI_DISH = [(0.0, 0.0), (0.067, 0.0), (0.0765, 0.0026), (0.0845, 0.0085), (0.0915, 0.0155), (0.098, 0.0207)]
LIZHI_IN = [(0.0935, 0.0228), (0.083, 0.0152), (0.066, 0.0111), (0.0, 0.0102)]


def lizhi_dish(p, sx, n=48, rim=0.0045, rc=(0.1, 0.0254)):
    """The deep celadon dish of 荔枝腰子 as the art draws it: a wide flat base rounding up into a full, low wall, a thick
    rolled rim (a bead of radius `rim` round rc), the inside sloping to a broad floor; stretched by sx across."""
    bead = [(rc[0] + rim * math.cos(math.radians(a)), rc[1] + rim * math.sin(math.radians(a)))
            for a in (-60, -15, 30, 75, 120, 165)]
    p.lathe(LIZHI_DISH + bead + LIZHI_IN, 'Celadon', n=n, close_ends=False, M=Matrix.Diagonal((sx, 1.0, 1.0, 1.0)))


TRACED_D15 = os.path.join(os.path.dirname(__file__), 'traced_D15.json')
# 荔枝腰子 traced from its art: every raised square of the scored kidneys, the bamboo shoot, the greens, the sauce
PALETTE.update({'LizhiSquare': ('#d66a2f', '#a84a1e'),    # a raised square of the scored kidney, glossy red-orange
                'LizhiGlint': ('#fde4c8', '#f0c8a0'),     # the glints on them
                'LizhiBamboo': ('#fcd689', '#e0b460'),    # the slices of bamboo shoot, cream-gold
                'LizhiBambooSlit': ('#c88c40', '#a06a28'),   # the slits through them
                'LizhiLeaf': ('#58671c', '#3c4a10'),      # the greens' dark leaves
                'LizhiStalk': ('#c6c947', '#a4a830'),     # and their pale stalks
                'LizhiSauce': ('#b45b20', '#86400f')})    # the sauce, dark in the cuts between the squares
GLOSS.update({'LizhiSquare': 0.8, 'LizhiGlint': 0.8, 'LizhiBamboo': 0.4, 'LizhiBambooSlit': 0.3, 'LizhiLeaf': 0.5,
              'LizhiStalk': 0.5, 'LizhiSauce': 0.7})
VIVID.update(dict.fromkeys(('LizhiSquare', 'LizhiBamboo', 'LizhiLeaf', 'LizhiStalk', 'LizhiSauce'), 0.0))
VIVID.update({'LizhiGlint': 0.2, 'LizhiBambooSlit': 0.5})
VTINT.update(dict.fromkeys(('LizhiSquare', 'LizhiGlint', 'LizhiBamboo', 'LizhiBambooSlit', 'LizhiLeaf', 'LizhiStalk',
                            'LizhiSauce'), 1.0))


def lizhi_yaozi(col, wok=False):
    """荔枝腰子 traced from its art (trace_d15.py writes traced_D15.json): five pieces of pork kidney scored in a
    cross-hatch and curled into lychee-like balls, every raised square of their scoring a plump piece of its own with
    the dark cuts between, slices of bamboo shoot with their slits, dark leaves and pale stalks of greens, in a light
    glaze on a deep celadon dish (named for the look: there is no lychee in it); every piece follows its outline in
    the art, the art's own colours painted on and its ink line round each. In the wok, the same on the wok's
    floor."""
    from .plates import traced_dish   # here: plates imports bowls
    p = Part()
    sx = 0.877
    if wok:
        pool(p, 0.078, 0.004, 'LizhiSauce', n=48, seed=15, wobble=0.07)
    else:
        lizhi_dish(p, sx)
    n0 = len(p.bm.verts)
    traced_dish(p, TRACED_D15, ink='#4a1a08')
    if wok:
        lower_food(p, n0, 0.0102, TRACED_D15)
    else:
        tuck_in(p, 0.1045, sx)
    art_colours(p, TRACED_D15, n0, ('LizhiSquare', 'LizhiBamboo', 'LizhiLeaf', 'LizhiStalk', 'LizhiSauce'), '#4a1a08')
    ob = p.finish('SM_D15' + ('_wok' if wok else ''), col, sharp=None)
    art_shading(ob, traced_tones(TRACED_D15, n0))
    return ob


def lathe_bands(p, prof, mats, n=56, M=Matrix(), place=None):
    """A surface of revolution about Z through the profile [(r, z)] in one piece, band k (between points k and k + 1)
    in mats[k], so the shading runs on smoothly where the colour changes; a ring of radius 0 is a single point.
    place(r, z, a) puts the point at radius r, height z and angle a: by default M @ (r cos a, r sin a, z)."""
    if place is None:
        def place(rad, z, a):
            return M @ Vector((rad * math.cos(a), rad * math.sin(a), z))
    tmp = bmesh.new()
    rings = []
    for rad, z in prof:
        if rad < 1e-6:
            rings.append([tmp.verts.new(place(0.0, z, 0.0))])
        else:
            rings.append([tmp.verts.new(place(rad, z, 2 * math.pi * k / n)) for k in range(n)])
    fm = []
    for (ra, rb), mat in zip(zip(rings, rings[1:]), mats):
        for k in range(n):
            if len(ra) == 1:
                tmp.faces.new((ra[0], rb[(k + 1) % n], rb[k]))
            elif len(rb) == 1:
                tmp.faces.new((ra[k], ra[(k + 1) % n], rb[0]))
            else:
                tmp.faces.new((ra[k], ra[(k + 1) % n], rb[(k + 1) % n], rb[k]))
            fm.append(mat)
    mi = [p._mi(m) for m in fm]
    vmap = {v: p.bm.verts.new(v.co) for v in tmp.verts}
    for f, m in zip(tmp.faces, mi):
        p.bm.faces.new([vmap[v] for v in f.verts]).material_index = m
    tmp.free()


def jar_r(prof, z):
    """The radius of a lathe profile [(r, z)] (going up) at height z."""
    for (r0, z0), (r1, z1) in zip(prof, prof[1:]):
        if z0 <= z <= z1 and z1 > z0:
            return r0 + (r1 - r0) * (z - z0) / (z1 - z0)
    return prof[-1][0] if z > prof[-1][1] else prof[0][0]


# 佛跳墙's jar, fitted to the art at 35°: radii across its depth (it is FTQ_SX as wide, as the art's view is a little
# steeper than the game's). The foot ring, round belly and shoulder; the cream rolled lip; the inside down to the
# broth. The shoulder and mouth are set back by up to FTQ_BACK, where the art draws the mouth.
FTQ_SX = 0.8
FTQ_BROTH = 0.0882
FTQ_BACK = 0.0075
FTQ_BODY = [(0.0, 0.004), (0.0435, 0.0), (0.047, 0.0028), (0.0488, 0.0115), (0.0535, 0.0138),
            (0.0615, 0.0172), (0.072, 0.0245), (0.0825, 0.036), (0.091, 0.0495), (0.097, 0.0615), (0.1006, 0.0725),
            (0.0985, 0.08), (0.0925, 0.0855), (0.087, 0.0888), (0.0812, 0.0903)]
FTQ_LIP = [(0.08, 0.0908), (0.0812, 0.0925), (0.0806, 0.0945), (0.0785, 0.0958), (0.0758, 0.0962), (0.0735, 0.0954),
           (0.0724, 0.0938)]
FTQ_INNER = [(0.072, FTQ_BROTH)]
FTQ_WALL = FTQ_BODY[3:]   # the outside from the foot ring up, which the scrolls are painted on
D21_ART = (6289.6, 560.9, 964.7)   # how the model maps onto 佛跳墙.png (fitmap.py): px per m, the origin's pixel


def ftq_back(z):
    """How far back the jar's wall is set at height z: not at all up to the shoulder, FTQ_BACK at the mouth."""
    s = min(1.0, max(0.0, (z - 0.078) / 0.0108))
    return FTQ_BACK * s * s * (3 - 2 * s)


def ftq_place(r, z, a):
    """Where the jar's lathe puts the radius r at height z and angle a."""
    return Vector((FTQ_SX * r * math.cos(a), r * math.sin(a) + ftq_back(z), z))


def jar_surface(a, z, lift=0.0):
    """The point of the jar's outside at angle a and height z, `lift` out along its normal, and that normal."""
    def at(a_, z_):
        return ftq_place(jar_r(FTQ_WALL, z_), z_, a_)
    q = at(a, z)
    nrm = (at(a + 1e-3, z) - at(a - 1e-3, z)).cross(at(a, z + 1e-3) - at(a, z - 1e-3)).normalized()
    if nrm.dot(Vector((q.x, q.y - ftq_back(z), 0.0))) < 0:
        nrm = -nrm
    return q + nrm * lift, nrm


FTQ_GRID = {}   # the front of the jar as the art sees it, per mapping: (angle, height, pixel)


def jar_from_art(m, u, v):
    """The angle and height on the front of the jar that the art shows at its pixel (u, v), or the nearest point of
    it that the art can see: the nearest of a grid over it, then Newton's method on the two pixel coordinates."""
    cam = Vector((0.0, -COS_EL, SIN_EL))
    if m not in FTQ_GRID:
        FTQ_GRID[m] = [(a, z, *to_art(m, q)) for a, z, (q, nrm) in
                       ((a, z, jar_surface(a, z)) for a in (-math.pi + math.pi * i / 64 for i in range(65))
                        for z in (0.013 + 0.077 * j / 44 for j in range(45))) if nrm.dot(cam) > 0]
    a, z = min(FTQ_GRID[m], key=lambda g: (g[2] - u) ** 2 + (g[3] - v) ** 2)[:2]
    for _ in range(12):
        pu, pv = to_art(m, jar_surface(a, z)[0])
        ua, va = to_art(m, jar_surface(a + 1e-4, z)[0])
        uz, vz = to_art(m, jar_surface(a, z + 1e-5)[0])
        j11, j12, j21, j22 = (ua - pu) / 1e-4, (uz - pu) / 1e-5, (va - pv) / 1e-4, (vz - pv) / 1e-5
        det = j11 * j22 - j12 * j21
        if abs(det) < 1e-6:
            break
        da, dz = ((u - pu) * j22 - (v - pv) * j12) / det, ((v - pv) * j11 - (u - pu) * j21) / det
        a = max(-math.pi, min(0.0, a + max(-0.15, min(0.15, da))))
        z = max(0.013, min(0.09, z + max(-0.006, min(0.006, dz))))
    return a, z


def to_art(m, q):
    """The pixel of the art where the model's point q shows."""
    k, u0, v0 = m
    return u0 + k * q.x, v0 - k * (q.y * SIN_EL + q.z * COS_EL)


def paint_path(p, pts, width, mat):
    """A brush line through points on a surface [(point, normal)], `width` wide (one, or one per point): a strip
    facing out, which is all anyone sees of it."""
    tmp = bmesh.new()
    sides = []
    for i, (q, nrm) in enumerate(pts):
        t = pts[min(i + 1, len(pts) - 1)][0] - pts[max(i - 1, 0)][0]
        w = width[i] if isinstance(width, (list, tuple)) else width
        sv = nrm.cross(t).normalized() * w / 2
        sides.append((tmp.verts.new(q + sv), tmp.verts.new(q - sv)))
    for i, ((a, b), (c, d)) in enumerate(zip(sides, sides[1:])):
        f = tmp.faces.new((a, b, d, c))
        f.normal_update()
        if f.normal.dot(pts[i][1] + pts[i + 1][1]) < 0:
            f.normal_flip()
    p._commit(tmp, mat)


def art_dab(p, put, u, v, r, mat, lift, n=14, step=0.009):
    """A round dab of paint r pixels across where the art shows (u, v), put onto a surface by put(u, v, lift) ->
    (point, normal): a disc facing out, round as the art sees it, in as many rings as keep each at most `step` across
    on the surface (where the art sees the surface edge-on, a pixel covers a lot of it)."""
    c, nc = put(u, v, lift)
    edge = [put(u + r * math.cos(2 * math.pi * j / n), v + r * math.sin(2 * math.pi * j / n), lift)[0]
            for j in range(n)]
    rings = max(1, math.ceil(max((q - c).length for q in edge) / step))
    tmp = bmesh.new()
    vc = tmp.verts.new(c)
    rs = [[tmp.verts.new(put(u + r * f * math.cos(2 * math.pi * j / n), v + r * f * math.sin(2 * math.pi * j / n),
                             lift)[0] if f < 1.0 else edge[j]) for j in range(n)]
          for f in ((i + 1) / rings for i in range(rings))]
    faces = [(vc, rs[0][j], rs[0][(j + 1) % n]) for j in range(n)]
    for ra, rb in zip(rs, rs[1:]):
        faces += [(ra[j], rb[j], rb[(j + 1) % n], ra[(j + 1) % n]) for j in range(n)]
    for fv in faces:
        f = tmp.faces.new(fv)
        f.normal_update()
        if f.normal.dot(nc) < 0:
            f.normal_flip()
    p._commit(tmp, mat)


def art_stroke(p, put, path, widths, mat, lift):
    """A brush line drawn in pixels of the art, path [(u, v)] and widths in pixels, put onto a surface by put(u, v,
    lift) -> (point, normal): a strip facing out, as wide as the art draws it."""
    tmp = bmesh.new()
    sides, nrms = [], []
    for i, (u, v) in enumerate(path):
        du = path[min(i + 1, len(path) - 1)][0] - path[max(i - 1, 0)][0]
        dv = path[min(i + 1, len(path) - 1)][1] - path[max(i - 1, 0)][1]
        ln = math.hypot(du, dv) or 1.0
        w = widths[i] / 2
        (qa, na), (qb, nb) = put(u - dv / ln * w, v + du / ln * w, lift), put(u + dv / ln * w, v - du / ln * w, lift)
        sides.append((tmp.verts.new(qa), tmp.verts.new(qb)))
        nrms.append(na + nb)
    for i, ((a, b), (c, d)) in enumerate(zip(sides, sides[1:])):
        f = tmp.faces.new((a, b, d, c))
        f.normal_update()
        if f.normal.dot(nrms[i] + nrms[i + 1]) < 0:
            f.normal_flip()
    p._commit(tmp, mat)


def spiral_path(cu, cv, r, turns, a0=0.0, ccw=True, n=None, inner=0.22):
    """A spiral curl of a cloud scroll in (u, v): from radius r at angle a0 inward to inner·r over `turns`."""
    n = n or max(8, round(turns * 14))
    sg = 1 if ccw else -1
    return [(cu + r * (1 - (1 - inner) * t) * math.cos(a0 + sg * 2 * math.pi * turns * t),
             cv + r * (1 - (1 - inner) * t) * math.sin(a0 + sg * 2 * math.pi * turns * t))
            for t in (i / (n - 1) for i in range(n))]


def cloud(p, put, lobes, curls, tails, lift=0.0009, cream='Jar', line='Earthenware'):
    """A cream 祥云 painted on a surface just as the art draws it, all in pixels of the art: lobes [(u, v, r)] of cream
    that make its bumpy outline, curls [(u, v, r, turns, start, ccw)] drawn on them in the glaze's brown, and tails
    [([(u, v), ...], width)] tapering off in cream. put(u, v, lift) -> (point, normal) puts a pixel onto the surface."""
    for u, v, r in lobes:
        art_dab(p, put, u, v, r, cream, lift)
    for path, w in tails:
        art_stroke(p, put, path, [w * (1.0 - 0.7 * i / (len(path) - 1)) for i in range(len(path))], cream, lift)
    for u, v, r, turns, a0, ccw in curls:
        path = spiral_path(u, v, r, turns, a0, ccw, inner=0.12)
        w = min(13.0, max(7.0, 0.24 * r))
        art_stroke(p, put, path, [w * (1.0 - 0.4 * i / (len(path) - 1)) for i in range(len(path))], line,
                   lift + 0.0004)


# 佛跳墙's lid (local z up its axis, from the bottom of its skirt): the underside, the cream skirt, the low dome; and the
# knob, a thick disc on a neck, turned on its own
FTQ_LID = [(0.0, 0.0075), (0.036, 0.005), (0.0408, 0.0), (0.0436, 0.0035), (0.0441, 0.0092), (0.0418, 0.0118),
           (0.034, 0.016), (0.0245, 0.0198), (0.0145, 0.0226), (0.0085, 0.0236), (0.0, 0.0239)]
FTQ_LID_MATS = ['Earthenware', 'Earthenware', 'Jar', 'Jar'] + ['ClayPot'] * 6   # its face catches the light
FTQ_KNOB = [(0.0, 0.021), (0.009, 0.0222), (0.0086, 0.0255), (0.0122, 0.0275), (0.0155, 0.0304), (0.0156, 0.0336),
            (0.0123, 0.0366), (0.0062, 0.0378), (0.0, 0.038)]
FTQ_DOME = FTQ_LID[2:10]   # its outside from the skirt's foot over the rim up to the knob, for painting on


def lid_frame(theta, phi, at=(0.0, 0.0, 0.0)):
    """A placement for the lid: its axis theta from the line of sight of the art's view, pointing phi up from the
    right of the picture; its local x level; its origin at `at`."""
    right, up, cam = Vector((1.0, 0.0, 0.0)), Vector((0.0, SIN_EL, COS_EL)), Vector((0.0, -COS_EL, SIN_EL))
    n = (math.sin(theta) * (math.cos(phi) * right + math.sin(phi) * up) + math.cos(theta) * cam).normalized()
    a = n.cross(Vector((0.0, 0.0, 1.0))).normalized()
    M = Matrix((a, n.cross(a), n)).transposed().to_4x4()
    M.translation = Vector(at)
    return M


def lid_standing(theta, phi, x, y):
    """The lid's placement with its axis as lid_frame() has it, at (x, y), standing on the table."""
    M = lid_frame(theta, phi)
    low = min((M @ Vector((r * math.cos(a), r * math.sin(a), z))).z for r, z in FTQ_LID[1:6]
              for a in (2 * math.pi * k / 96 for k in range(96)))
    return lid_frame(theta, phi, (x, y, -low))


def dome_rz(w):
    """Radius and height on the lid's outside w of the way from the foot of its skirt (0) to the knob (1)."""
    f = max(0.0, min(1.0, w)) * (len(FTQ_DOME) - 1)
    i = min(int(f), len(FTQ_DOME) - 2)
    (r0, z0), (r1, z1) = FTQ_DOME[i], FTQ_DOME[i + 1]
    return r0 + (r1 - r0) * (f - i), z0 + (z1 - z0) * (f - i)


def lid_surface(L):
    """The lid's outside placed by L as a surface for painting: (a, w, lift) -> (point, normal), a round its axis and
    w from the foot of its skirt to the knob."""
    def surf(a, w, lift=0.0):
        def at(a_, w_):
            r, z = dome_rz(w_)
            return L @ Vector((r * math.cos(a_), r * math.sin(a_), z))
        q = at(a, w)
        nrm = (at(a + 1e-3, w) - at(a - 1e-3, w)).cross(at(a, w + 1e-3) - at(a, w - 1e-3)).normalized()
        if nrm.dot(L.to_3x3() @ Vector((0.0, 0.0, 1.0))) < 0:
            nrm = -nrm
        return q + nrm * lift, nrm
    return surf


def lid_from_art(m, L):
    """For the lid's dome as the art draws it (placed by L): a function (u, v) -> (a, w), where on the dome the art
    shows its pixel (u, v)."""
    def px(a, w):
        r, z = dome_rz(w)
        return to_art(m, L @ Vector((r * math.cos(a), r * math.sin(a), z)))
    surf = lid_surface(L)
    cam = Vector((0.0, -COS_EL, SIN_EL))
    grid = [(a, w, *px(a, w)) for a, w in ((2 * math.pi * i / 96, j / 16) for i in range(96) for j in range(17))
            if surf(a, w)[1].dot(cam) > 0]

    def find(u, v):
        a, w = min(grid, key=lambda g: (g[2] - u) ** 2 + (g[3] - v) ** 2)[:2]
        for _ in range(10):   # then Newton's method on the two pixel coordinates
            pu, pv = px(a, w)
            ua, va = px(a + 1e-4, w)
            uw, vw = px(a, w + 1e-4)
            j11, j12, j21, j22 = (ua - pu) / 1e-4, (uw - pu) / 1e-4, (va - pv) / 1e-4, (vw - pv) / 1e-4
            det = j11 * j22 - j12 * j21
            if abs(det) < 1e-9:
                break
            da, dw = ((u - pu) * j22 - (v - pv) * j12) / det, ((v - pv) * j11 - (u - pu) * j21) / det
            a, w = a + max(-0.2, min(0.2, da)), max(0.0, min(1.0, w + max(-0.2, min(0.2, dw))))
        return a, w
    return find


FTQ_PORK = ((0.16, 'BraisedPork'), (0.14, 'BellyLean'), (0.32, 'BraisedFat'), (0.14, 'BellyLean'),
            (0.24, 'BraisedPork'))


def pork_block(p, c, size, yaw, tilt=0.0, roll=0.0, bands=FTQ_PORK, chamfer=0.14, inset=0.72):
    """A block of braised pork belly for soft(): an eight-sided cage, its upright edges chamfered and its top inset,
    so that it comes out square with softly rounded edges; banded round its sides from the top in layers [(share of
    the height, colour)], the browned rind on top, then lean and fat."""
    L, D, H = size
    d = chamfer * min(L, D)
    ring = [(L / 2 - d, -D / 2), (L / 2, -D / 2 + d), (L / 2, D / 2 - d), (L / 2 - d, D / 2), (-L / 2 + d, D / 2),
            (-L / 2, D / 2 - d), (-L / 2, -D / 2 + d), (-L / 2 + d, -D / 2)]
    M = Matrix.Translation(c) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(tilt, 4, 'X') \
        @ Matrix.Rotation(roll, 4, 'Y')
    zs = [H / 2]
    for f, _ in bands:
        zs.append(zs[-1] - f * H)
    tmp = bmesh.new()
    rings = [[tmp.verts.new(M @ Vector((x, y, z))) for x, y in ring] for z in zs]
    top = [tmp.verts.new(M @ Vector((x * inset, y * inset, H / 2))) for x, y in ring]
    mats = []
    tmp.faces.new(top)
    mats.append(bands[0][1])
    for k in range(8):
        tmp.faces.new((top[k], top[(k + 1) % 8], rings[0][(k + 1) % 8], rings[0][k]))
        mats.append(bands[0][1])
    for (ra, rb), (_, mat) in zip(zip(rings, rings[1:]), bands):
        for k in range(8):
            tmp.faces.new((ra[k], rb[k], rb[(k + 1) % 8], ra[(k + 1) % 8]))
            mats.append(mat)
    tmp.faces.new(list(reversed(rings[-1])))
    mats.append(bands[-1][1])
    piece_in_colours(p, tmp, mats)


def shiitake(p, c, axis, r, h):
    """A braised shiitake cap for soft(): a dark glossy dome r across and h high on its axis, its rim rounded under to
    the pale gills. Returns its placement."""
    M = Matrix.Translation(c) @ Vector(axis).normalized().to_track_quat('Z', 'Y').to_matrix().to_4x4()
    lathe_bands(p, [(0.0, -0.18 * h), (0.7 * r, -0.14 * h), (0.98 * r, 0.02 * h), (1.0 * r, 0.42 * h),
                    (0.62 * r, 0.9 * h), (0.0, h)],   # from under it up and over, so that its faces look out
                ['ShiitakeFlesh'] * 2 + ['BraisedShiitake'] * 3, n=8, M=M)
    return M


def star_cut(p, tree, M, r, h, count=3, a0=0.3):
    """`count` knife cuts through the middle of a shiitake's cap (placed by M, r across, h high) that open its pale
    flesh in a star: cream ribbons on the cap, widest in the middle and tapering to points."""
    up = M.to_3x3() @ Vector((0.0, 0.0, 1.0))
    for j in range(count):
        a = a0 + math.pi * j / count
        d = Vector((math.cos(a), math.sin(a), 0.0))
        pts = []
        for t in (-0.66, -0.44, -0.22, 0.0, 0.22, 0.44, 0.66):
            q = M @ (d * r * t + Vector((0.0, 0.0, h * 2.0)))
            hit, nrm, _, _ = tree.ray_cast(q, -up)
            if hit is not None:
                pts.append((hit + nrm.normalized() * (0.0005 + 0.0001 * j), nrm.normalized(), t))
        if len(pts) > 1:
            paint_path(p, [(q, n) for q, n, _ in pts], [r * (0.2 - 0.25 * abs(t)) for _, _, t in pts], 'ShiitakeFlesh')


def scallop_disc(p, c, axis, r=0.0135, h=0.02, lines=9):
    """A dried scallop, soaked plump: a squat round column standing in the broth, its pale top rounded off at the edge
    and scored with fine radial lines, its sides golden."""
    Z = Vector(axis).normalized()
    M = Matrix.Translation(c) @ Z.to_track_quat('Z', 'Y').to_matrix().to_4x4()
    lathe_bands(p, [(r * 0.9, -h / 2), (r, -h / 2 + 0.002), (r * 1.01, h / 2 - r * 0.24), (r * 0.93, h / 2 - r * 0.05),
                    (r * 0.66, h / 2), (0.0, h / 2 + 0.0004)],
                ['Scallop', 'Scallop', 'ScallopTop', 'ScallopTop', 'ScallopTop'], n=20, M=M)
    tmp = bmesh.new()
    up = M.to_3x3() @ Vector((0.0, 0.0, 1.0))
    for k in range(lines):   # fine radial lines across the top
        a = 2 * math.pi * k / lines + 0.2
        d, sd = Vector((math.cos(a), math.sin(a), 0.0)), Vector((-math.sin(a), math.cos(a), 0.0)) * 0.00055
        q0, q1 = d * r * 0.12, d * r * 0.8
        z = Vector((0.0, 0.0, h / 2 + 0.0008))
        f = tmp.faces.new([tmp.verts.new(M @ (q + z + sv)) for q, sv in ((q0, sd), (q0, -sd), (q1, -sd), (q1, sd))])
        f.normal_update()
        if f.normal.dot(up) < 0:
            f.normal_flip()
    p._commit(tmp, 'Scallop')


def chicken_piece(p, c, size, yaw, seed, skin=None, tilt=0.0, roll=0.0, segs=(8, 4)):
    """A piece of stewed chicken for soft(): a knobbly lump size (x, y, z) across, flattened underneath, its meat
    peach; past `skin` along its local x (a share of its half-length; -1: all of it) it is the yellow skin. Returns
    its placement."""
    rnd = random.Random(seed)
    ph = [rnd.uniform(0, 6) for _ in range(3)]
    L, D, H = size
    M = Matrix.Translation(c) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(tilt, 4, 'X') \
        @ Matrix.Rotation(roll, 4, 'Y')
    tmp = bmesh.new()
    bmesh.ops.create_uvsphere(tmp, u_segments=segs[0], v_segments=segs[1], radius=1.0)
    mats = ['StewSkin' if skin is not None and f.calc_center_median().x > skin else 'StewBreast' for f in tmp.faces]
    for v in tmp.verts:
        a = math.atan2(v.co.y, v.co.x)
        k = 1 + 0.12 * math.sin(3 * a + ph[0]) + 0.07 * math.sin(5 * a + ph[1])
        v.co = M @ Vector((v.co.x * k * L / 2, v.co.y * k * D / 2,
                           max(v.co.z, -0.35) * H / 2 * (1 + 0.08 * math.sin(4 * a + ph[2]))))
    piece_in_colours(p, tmp, mats)
    return M


def ftq_wok_pool(p, r, z, mat, n=48, sx=1.0, wobble=0.0, seed=0):
    """The pool of broth the food sits in in the wok: a smooth disc r across with its top at z, its edge a rounded
    bead that comes down to the wok at z = 0 (nothing below it); stretched by sx along x, gently lobed by `wobble`."""
    rnd = random.Random(seed)
    ph = [rnd.uniform(0, 6) for _ in range(2)]

    def edge(q):
        a = math.atan2(q.y, q.x)
        k = 1 + wobble * (0.6 * math.sin(3 * a + ph[0]) + 0.4 * math.sin(5 * a + ph[1]))
        return Vector((q.x * k, q.y * k, q.z))
    e = min(0.004, z * 0.6)
    p.lathe([(r, 0.0), (r + e * 0.25, z * 0.45), (r - e * 0.2, z * 0.9), (r - e, z), (r * 0.5, z + 0.0004),
             (0.0, z + 0.0005)], mat, n=n, M=Matrix.Diagonal((sx, 1.0, 1.0, 1.0)), close_ends=False, deform=edge)


# where the lid stands: its axis 62° from the line of sight, pointing a little down to the right, its skirt on the
# table and its rim leaning on the jar's belly (pressing 2 mm into it). The art draws it higher up, which would put
# it inside the jar; this is as near to that as it can stand.
FTQ_LID_POSE = (math.radians(62), math.radians(-11), 0.074, -0.046)
FTQ_LID_ART = (math.radians(56), 0.0, 0.065, -0.0275)   # where the art draws it, for reading its scroll off


def fotiaoqiang(col, wok=False):
    """佛跳墙 as the art has it: a round glazed clay jar on a foot ring, cream cloud scrolls painted on its belly and a
    cream rolled lip, full of golden broth with braised pork belly, shiitake, dried scallops and stewed chicken in
    it; its domed lid with a big knob and a scroll of its own leans against its right front. Every piece is placed
    from where the art shows it (pixels of the art)."""
    p = Part()
    m = D21_ART
    zb = FTQ_BROTH
    if not wok:
        lathe_bands(p, FTQ_BODY + FTQ_LIP + FTQ_INNER,
                    ['Earthenware'] * len(FTQ_BODY) + ['Jar'] * (len(FTQ_LIP) - 1) + ['ClayPot'] * len(FTQ_INNER),
                    n=48, place=ftq_place)
        lathe_bands(p, [(FTQ_INNER[-1][0], zb), (0.0, zb + 0.0004)], ['GoldenBroth'], n=48, place=ftq_place)

        def on_jar(u, v, lift):   # the scrolls go where the art paints them
            return jar_surface(*jar_from_art(m, u, v), lift)
        cloud(p, on_jar,   # on the left of the belly
              lobes=((128, 745, 58), (110, 625, 32), (168, 676, 38), (98, 684, 26), (202, 742, 30), (176, 815, 32),
                     (250, 872, 30)),
              curls=((128, 748, 46, 1.6, 3.6, False), (110, 627, 24, 1.2, 2.0, True), (166, 678, 30, 1.2, 1.0, True),
                     (250, 873, 23, 1.2, 0.5, False)),
              tails=(([(215, 750), (250, 762), (282, 771), (310, 765)], 22), ([(195, 840), (225, 856), (258, 850)], 16)))
        cloud(p, on_jar,   # at the front right
              lobes=((735, 950, 64), (652, 967, 44), (603, 988, 27), (576, 1000, 16), (690, 912, 33), (745, 900, 30),
                     (795, 925, 26), (803, 983, 28), (768, 990, 30)),
              curls=((735, 958, 50, 1.6, 2.6, True), (615, 978, 32, 1.4, 0.3, False), (574, 1000, 14, 1.1, 0.0, False)),
              tails=(([(566, 1003), (530, 1004), (490, 1003), (445, 1001)], 16),))
        L = lid_standing(*FTQ_LID_POSE)
        lathe_bands(p, FTQ_LID, FTQ_LID_MATS, n=48, M=L)
        lathe_bands(p, FTQ_KNOB, ['Earthenware'] * (len(FTQ_KNOB) - 1), n=24, M=L)
        find, dome = lid_from_art(m, lid_standing(*FTQ_LID_ART)), lid_surface(L)

        def on_lid(u, v, lift):   # read off the lid as the art draws it, painted on the lid where it stands
            return dome(*find(u, v), lift)
        cloud(p, on_lid,
              lobes=((918, 990, 25), (935, 1033, 32), (990, 1000, 33)),
              curls=((935, 1030, 24, 1.3, 0.5, True), (992, 990, 17, 1.0, 3.5, False), (992, 1026, 15, 1.0, 2.5, False)),
              tails=(([(926, 902), (922, 925), (930, 950)], 14),
                     ([(964, 1065), (1006, 1086), (1058, 1092), (1092, 1080)], 13)))
    floor = 0.006 if wok else zb
    if wok:
        ftq_wok_pool(p, 0.074, floor, 'GoldenBroth', sx=0.85, wobble=0.04, seed=21)
    n_food = len(p.bm.verts)
    shift = Vector((0.0, -FTQ_BACK if wok else 0.0, floor - zb))   # the wok's food: centred, on its pool

    def place(u, v, lift):   # on the broth's surface in the jar, where the art shows it
        return art_seat(m, u, v, lambda x, y: zb, lift) + shift

    def keep(q, n):
        return n.z > -0.3 and q.z > floor + 0.002
    with p.soft():   # braised pork belly, the layered cut faces to the front
        for (u, v), size, yaw, lift in (((340, 452), (0.036, 0.026, 0.028), -0.15, 0.008),
                                        ((512, 376), (0.03, 0.024, 0.026), 0.35, 0.007),
                                        ((679, 610), (0.035, 0.024, 0.028), -0.12, 0.008)):
            pork_block(p, place(u, v, lift), size, yaw, tilt=-0.4)
        pork_block(p, place(712, 262, 0.003), (0.013, 0.011, 0.013), 0.4, tilt=-0.3,
                   bands=((0.3, 'BraisedPork'), (0.4, 'BraisedFat'), (0.3, 'BellyLean')))
    n0 = len(p.bm.verts)
    with p.soft():   # stewed chicken: the big piece with its skin to the right, two behind, scraps of skin
        chickens = [(chicken_piece(p, place(755, 482, 0.009), (0.058, 0.036, 0.031), 0.12, 1, skin=0.0), 0.058, 0.036,
                     (-0.44, -0.04)),
                    (chicken_piece(p, place(490, 282, 0.006), (0.046, 0.024, 0.021), 0.22, 2), 0.046, 0.024, (-0.4, 0.4)),
                    (chicken_piece(p, place(640, 276, 0.007), (0.038, 0.027, 0.023), -0.3, 3), 0.038, 0.027,
                     (-0.4, 0.4))]
        chicken_piece(p, place(355, 335, 0.003), (0.018, 0.013, 0.012), 0.3, 4, skin=-1.0, segs=(6, 3))
        chicken_piece(p, place(286, 334, 0.002), (0.013, 0.0095, 0.009), -0.4, 5, skin=-1.0, segs=(6, 3))
    tree = bvh_since(p, n0)
    for M, L_, D_, (t0, t1) in chickens:   # the grain of the meat, in fine lines running across it
        for j in range(4):
            off = (j - 1.5) * D_ * 0.2
            pts = [M @ Vector((L_ * t, off + D_ * 0.25 * t, 0.03)) for t in (t0 + (t1 - t0) * i / 3 for i in range(4))]
            groove(p, tree, pts, width=0.0013, lift=0.0005, mat='ChickenFiber', keep=keep)
    for (u, v), r, h, axis, lift, star in (((492, 488), 0.0205, 0.013, (-0.25, -0.05, 0.97), 0.008, False),   # middle
                                           ((772, 348), 0.0175, 0.0115, (0.05, -0.3, 0.95), 0.006, True)):   # cut
        n0 = len(p.bm.verts)
        with p.soft():   # shiitake
            M = shiitake(p, place(u, v, lift), axis, r, h)
        if star:
            star_cut(p, bvh_since(p, n0), M, r, h)
    for (u, v), r, h in (((405, 568), 0.0122, 0.022), ((530, 645), 0.0142, 0.024)):   # dried scallops
        scallop_disc(p, place(u, v, 0.005), (0.0, -0.2, 1.0), r=r, h=h)
    if wok:   # nothing below the wok's floor
        p.bm.verts.ensure_lookup_table()
        low = min(v.co.z for v in p.bm.verts[n_food:])
        if low < 0.0005:
            for v in p.bm.verts[n_food:]:
                v.co.z += 0.0005 - low
    return p.finish('SM_D21' + ('_wok' if wok else ''), col, sharp=None)


ITEMS = [('D06', fanqie_chaodan),
         ('D06_wok', lambda c: fanqie_chaodan(c, True)),
         ('D07', gongbao_jiding),
         ('D07_wok', lambda c: gongbao_jiding(c, True)),
         ('D08', kele_jichi),
         ('D08_wok', lambda c: kele_jichi(c, True)),
         ('D13', tudou_dunrou),
         ('D13_wok', lambda c: tudou_dunrou(c, True)),
         ('D15', lizhi_yaozi),
         ('D15_wok', lambda c: lizhi_yaozi(c, True)),
         ('D21', fotiaoqiang),
         ('D21_wok', lambda c: fotiaoqiang(c, True))]
