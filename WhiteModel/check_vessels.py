"""Finds food that pokes out of its plate, bowl or pot, which check_backfaces.py can't see. Unity shows the dishes
from all round (on a table each one turns to face its guest), so food passing out through a plate's wall, hanging
past its rim or sinking below the base shows there.

    blender -b --factory-startup --python check_vessels.py -- <dir with SM_*.blend> [id1,id2,...]

Checks the dishes (SM_D*) unless ids are given. For each it reports, in mm and by material:
  under   food lying beneath its vessel: straight above it there is celadon or clay, but the food is below all of
          it, so it sticks out through the wall or under the foot;
  past    food beyond the vessel's outline seen from above (the rim);
  below   anything under the base (z = 0), which sinks into the table, tray or wok.
Over 2 mm shows in the game. A leg or tail resting over the rim, as in the art, is fine as "past"; the dishes'
onto_plate() lifts food that reaches past a plate's floor up its wall.
"""
import glob
import os
import re
import sys

import bmesh
import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

ARGS = sys.argv[sys.argv.index('--') + 1:]
DIR = ARGS[0]
IDS = ARGS[1].split(',') if len(ARGS) > 1 else \
    sorted(k for k in (os.path.basename(p)[3:-6] for p in glob.glob(os.path.join(DIR, 'SM_*.blend')))
           if re.match(r'D\d', k))   # the dishes (glob is case-blind on Windows: SM_D* finds SM_duck)
VESSEL = {'Celadon', 'ClayPot', 'Earthenware', 'Jar'}   # Jar: the cream lip and scrolls painted on 佛跳墙's jar
LIMIT = 0.002   # thinner slivers than this don't show at game size


def hull(pts):
    """Convex hull of 2D points, anticlockwise."""
    pts = sorted(set(pts))

    def half(seq):
        h = []
        for q in seq:
            while len(h) >= 2 and (h[-1][0] - h[-2][0]) * (q[1] - h[-2][1]) - (h[-1][1] - h[-2][1]) * (q[0] - h[-2][0]) <= 0:
                h.pop()
            h.append(q)
        return h
    return half(pts)[:-1] + half(list(reversed(pts)))[:-1]


def outside(poly, q):
    """How far q lies outside a convex anticlockwise polygon (0 inside)."""
    worst = 0.0
    for a, b in zip(poly, poly[1:] + poly[:1]):
        nrm = Vector((b[1] - a[1], a[0] - b[0])).normalized()
        worst = max(worst, (Vector(q) - Vector(a)).dot(nrm))
    return worst


report = []
for key in IDS:
    bpy.ops.wm.open_mainfile(filepath=os.path.join(DIR, f'SM_{key}.blend'))
    ob = next(o for o in bpy.data.objects if o.type == 'MESH' and o.name.startswith('SM_'))
    names = [m.name[2:] for m in ob.data.materials]
    bm = bmesh.new()
    bm.from_mesh(ob.data)
    bm.verts.ensure_lookup_table()
    food = {}    # vertex index -> a food material it belongs to
    vessel = bmesh.new()
    vmap = {}
    for f in bm.faces:
        if names[f.material_index] in VESSEL:
            vessel.faces.new([vmap.setdefault(v.index, vessel.verts.new(v.co)) for v in f.verts])
        else:
            for v in f.verts:
                food.setdefault(v.index, names[f.material_index])
    found = {}

    def note(kind, mat, mm):
        k = (kind, mat)
        found[k] = max(found.get(k, 0.0), mm)
    for i, mat in food.items():
        if bm.verts[i].co.z < -LIMIT / 2:
            note('below', mat, -bm.verts[i].co.z)
    if vmap:
        tree = BVHTree.FromBMesh(vessel)
        poly = hull([(v.co.x, v.co.y) for v in vessel.verts])
        for i, mat in food.items():
            v = bm.verts[i].co
            origin, lowest = Vector((v.x, v.y, 1.0)), None
            for _ in range(12):   # every surface of the vessel straight above and below the vertex
                hit = tree.ray_cast(origin, Vector((0.0, 0.0, -1.0)))[0]
                if hit is None:
                    break
                lowest = hit.z
                origin = hit - Vector((0.0, 0.0, 1e-5))
            if lowest is not None and v.z < lowest - LIMIT:
                note('under', mat, lowest - v.z)
            d = outside(poly, (v.x, v.y))
            if d > LIMIT * 1.5:
                note('past', mat, d)
    bm.free()
    vessel.free()
    worst = max(found.values(), default=0.0)
    report.append((key, worst, found))
    print(f'[vessel] {key}: ' + (', '.join(f'{kind} {mat} {mm * 1000:.1f}' for (kind, mat), mm in
                                         sorted(found.items(), key=lambda x: -x[1])) or 'clean'), flush=True)
print('[vessel] under or below by over 2 mm:',
      [k for k, w, f in report if any(kind != 'past' and mm > LIMIT for (kind, _), mm in f.items())] or 'none',
      flush=True)
