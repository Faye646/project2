"""Collision and support check for a shop white model.

    blender -b <SM_ShopN.blend> --python WhiteModel/check_shop.py

For every pair of parts whose boxes meet, tests their triangles for real intersections (BVH overlap) and prints the
pairs that cut into each other. Floors and plinths are left out (everything stands on them by design, seated a
centimetre into the boards like the 初始 level); instead every piece that stands on a floor is checked to reach down to
it and not below it (nothing floats, nothing sinks). Pairs meant to share a joint are listed in ALLOW.
"""
import re
import sys

import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

FLOORS = re.compile(r'_(Floor|Plinth|Walkway)$')     # what things stand on
ALLOW = [
    # the passage's beam and back wall rest on the kitchen's and hall's end posts
    ('C_Walls', 'K_Walls'), ('C_Walls', 'D_Walls'),
    # the 二楼 slab rests on the posts and walls beneath it; stairs land on the floors they climb to
    ('U_Floor', 'D_Walls'), ('U_Slab', 'D_Walls'), ('U_Slab', 'U_Posts'), ('U_Slab', 'D_Stairs'), ('U_Slab', 'U_Stairs'),
    ('U_Floor', 'D_Stairs'), ('U_Floor', 'U_Stairs'), ('U_Slab', 'U_Walls'), ('U_Slab', 'Y_Screens'),
    ('U_Slab', 'U_Railings'), ('U_Slab', 'Y_Walls'), ('U_Slab', 'U_Base'),
]


def allowed(a, b):
    for x, y in ALLOW:
        if (a.startswith(x) and b.startswith(y)) or (a.startswith(y) and b.startswith(x)):
            return True
    return False


def world_tris(ob, dg):
    me = ob.evaluated_get(dg).to_mesh()
    M = ob.matrix_world
    verts = [M @ v.co for v in me.vertices]
    polys = [tuple(p.vertices) for p in me.polygons]
    ob.evaluated_get(dg).to_mesh_clear()
    return verts, polys


def main():
    dg = bpy.context.evaluated_depsgraph_get()
    obs = [o for o in bpy.data.objects if o.type == 'MESH' and not o.name.endswith('_outline')]
    data = {}
    for o in obs:
        v, p = world_tris(o, dg)
        if not v:
            continue
        lo = Vector((min(q.x for q in v), min(q.y for q in v), min(q.z for q in v)))
        hi = Vector((max(q.x for q in v), max(q.y for q in v), max(q.z for q in v)))
        data[o.name] = (BVHTree.FromPolygons(v, p, epsilon=0.0), lo, hi, v, p)
    names = sorted(data)
    bad = []
    for i, a in enumerate(names):
        if FLOORS.search(a):
            continue
        ta, la, ha = data[a][:3]
        for b in names[i + 1:]:
            if FLOORS.search(b) or allowed(a, b):
                continue
            tb, lb, hb = data[b][:3]
            if any(ha[k] < lb[k] - 1e-4 or hb[k] < la[k] - 1e-4 for k in range(3)):
                continue
            hits = ta.overlap(tb)
            if hits:
                va = data[a][3]
                pa = data[a][4]
                cs = [sum((va[i] for i in pa[h[0]]), Vector()) / len(pa[h[0]]) for h in hits[:200]]
                lo = Vector((min(c.x for c in cs), min(c.y for c in cs), min(c.z for c in cs)))
                hi = Vector((max(c.x for c in cs), max(c.y for c in cs), max(c.z for c in cs)))
                bad.append((a, b, len(hits), lo, hi))
    for a, b, n, lo, hi in bad:
        print(f'CUT  {a:<20} x {b:<20} {n} triangle pairs near x {lo.x:.2f}..{hi.x:.2f} y {lo.y:.2f}..{hi.y:.2f} '
              f'z {lo.z:.2f}..{hi.z:.2f}')
    print(f'CHECK {len(bad)} intersecting pairs among {len(names)} parts')

    # standing pieces: their lowest point must sit on a floor (top of boards ~F+0.01, or the ground)
    floors = {round(o.location.z, 3) for o in obs if FLOORS.search(o.name) and o.name.endswith('_Floor')}
    for n_ in names:
        if FLOORS.search(n_) or not re.match(r'(D_Table|D_Stool|K_|D_Cabinet|D_Bench|U_|Y_)', n_):
            continue
        if re.search(r'Walls|Railings|Lantern|Screens|Sieve|Hooks|Slab|Posts|Path|Base', n_):
            continue
        z = data[n_][1].z
        ok = any(-0.06 <= z - f <= 0.015 for f in floors)
        if not ok:
            print(f'FLOAT {n_:<20} bottom at z={z:.3f}, floors at {sorted(floors)}')


main()
