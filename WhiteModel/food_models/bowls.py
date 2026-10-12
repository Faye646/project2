"""碗菜：面、汤、冷菜和酒蟹: D02, D03, D04, D09, D11, D16, D17, D20, D20_spicy, D23."""
import json
import math
import os
import random

import bmesh
import bpy
import numpy as np
from mathutils import Matrix, Vector

from .core import *  # noqa: F401,F403
from .meat_fish import paint

PALETTE.update({
    'WontonFill': ('#e2b2a4', '#c48d80'),   # the pink filling seen through a wonton's thin wrapper
    'CucumberStrip': ('#c9dc8e', '#a3bb68'),   # julienned cucumber, its flesh light green
    'RadishStrip': ('#f8f3e2', '#e0d6bb'),   # julienned radish, a little translucent
    'PorkRind': ('#a8532f', '#7e3a1f'),   # the browned rind and edges of braised pork slices
    'BokStalk': ('#dfeab8', '#b9cc8a'),   # bok choy's pale green stalks
    'ColdDressing': ('#f1c27e', '#d49a55'),   # 冷淘's dressing pooled under the noodles: vinegar and sesame, no chilli
    'FishSlice': ('#fdf1d8', '#efd6b0'),   # 酸菜鱼's poached white fish, warm
    'SauerStalk': ('#f6e88e', '#d8c45e'),   # the pale yellow pieces of its pickled cabbage, lighter than the broth
    'SourBroth': ('#f2cc5e', '#d8a838'),    # and its broth, a deeper gold than they are (as the art)
    'SuanSkin': ('#86786a', '#5c5046'),     # the grey skin along an edge of its slices of fish
    'SuanLeaf': ('#7a6410', '#584608'),     # the dark olive leaves of its pickled cabbage
    'ChiliDrop': ('#d8301a', '#a82012'),    # drops of red chilli oil on the 辣味版's broth and fish
    'SpicyStalk': ('#d8b43a', '#ae8a1c'),   # its pickled cabbage's stalks, olive gold
    'SpicyBroth': ('#eca42c', '#cc8418'),   # and its broth, orange with the chilli oil
})
GLOSS.update({'CucumberStrip': 0.5, 'RadishStrip': 0.5, 'WontonFill': 0.3, 'PorkRind': 0.8, 'BokStalk': 0.5,
              'ColdDressing': 0.8, 'FishSlice': 0.5, 'SauerStalk': 0.5, 'SuanSkin': 0.4,
              'SuanLeaf': 0.5, 'ChiliDrop': 0.8, 'SpicyStalk': 0.5})
PALETTE.update({'DrunkCream': ('#f2d9ad', '#d9b986')})   # 酒蟹's cream: the pale undersides of its claws and legs
# 酒蟹's crabs as the art paints them, not toys: fibrous white meat, granular roe, blue-grey blotches on the olive
# shell, the colours kept soft.
DETAIL.update({'CrabMeat': ('food_fiber', 30, '#e8b878', 0.4, 0.3), 'CrabRoe': ('food_chopped', 45, '#ffb84a', 0.5, 0.4),
               'DrunkShell': ('food_shell', 22, '#748790', 0.55, 0.3)})
VIVID.update({'CrabMeat': 0.45, 'DrunkShell': 0.5, 'CrabClaw': 0.55, 'DrunkCream': 0.45})
# 酸菜鱼 as the art paints it: flaky white fish, its grey skin painted along one edge, veined leaves of pickled
# cabbage, pale pieces, the colours kept soft (trace_d20.py).
DETAIL.update({'FishSlice': ('food_fiber', 30, '#e8cbb8', 0.4, 0.3),
               'SauerLeaf': ('food_veins', 30, '#a8b46a', 0.45, 0.25),
               'SauerStalk': ('food_fiber', 30, '#c8a842', 0.3, 0.2),
               'SuanLeaf': ('food_veins', 30, '#a89040', 0.4, 0.25),
               'SuanSkin': ('food_scales', 40, '#a89a88', 0.35, 0.15)})
VIVID.update({'FishSlice': 0.4, 'SauerLeaf': 0.6, 'SauerStalk': 0.5, 'SourBroth': 0.4, 'SpicyBroth': 0.8,
              'SuanSkin': 0.3, 'SuanLeaf': 0.5})
VTINT.update(dict.fromkeys(('FishSlice', 'SauerStalk', 'SuanSkin', 'SuanLeaf', 'ChiliDrop', 'SpicyStalk'), 1.0))
VTINT.update(dict.fromkeys(('CrabMeat', 'CrabRoe', 'DrunkShell', 'DrunkCream', 'CrabClaw'), 1.0))   # inked edges


def round_bowl(p, rim_r=0.08, h=0.075, foot_r=0.033, foot_h=0.012, fill_z=0.07, fill='Broth', t=0.005, n=48,
               lean=1.0, shelf=1.12, deform=None, light=False, flare=None):
    """A rounded celadon bowl as the art draws it: a foot ring with soft edges, a full belly that leaves the foot
    almost level and turns up into a thick rolled lip (t), the inside following the wall down to the broth (or
    whatever `fill` is) at fill_z, which closes it. `lean` < 1 keeps the belly fuller low down; the belly starts on a
    small shelf `shelf` times the foot's radius, so the foot reads as its own ring. n round, so the rim is
    a smooth ellipse; `deform` (lobed()) shapes the wall and the fill alike so they still meet; `light` uses fewer
    rings up the profile (the same shape, a quarter fewer triangles). `flare` = (a0, a1, k) makes the wall a curve
    that leaves the foot at a0 degrees from level and meets the lip at a1 (a flared, more conical bowl), k setting how
    far each end keeps its direction. Returns fill_z and the inside radius there."""
    rb, zb = foot_r * shelf, foot_h + 0.0015
    if flare:
        a0, a1, kk = math.radians(flare[0]), math.radians(flare[1]), flare[2]
        P0, P3 = Vector((rb, zb)), Vector((rim_r, h - t))
        L = (P3 - P0).length * kk
        P1, P2 = P0 + L * Vector((math.cos(a0), math.sin(a0))), P3 - L * Vector((math.cos(a1), math.sin(a1)))

    def wall(th, off=0.0):   # a quarter ellipse from the top of the foot (th 0) to just under the lip (th pi/2)
        if flare:
            u = th / (math.pi / 2)
            q = (1 - u) ** 3 * P0 + 3 * (1 - u) ** 2 * u * P1 + 3 * (1 - u) * u * u * P2 + u ** 3 * P3
            return (q.x - off, q.y)
        return (rb + (rim_r - rb) * math.sin(th) ** lean - off, zb + (h - t - zb) * (1 - math.cos(th)))
    if light:
        prof = [(foot_r * 0.8, 0.0045), (foot_r * 0.87, 0.0), (foot_r * 0.98, 0.0006), (foot_r * 1.005, foot_h * 0.7),
                (foot_r * 1.04, foot_h), (rb, zb)]
        prof += [wall(math.pi / 2 * i / 7) for i in range(1, 8)]
        lip = (0.0, 0.8, 1.57, 2.35, 3.14)
    else:
        prof = [(foot_r * 0.8, 0.0045), (foot_r * 0.84, 0.001), (foot_r * 0.9, 0.0), (foot_r * 0.97, 0.0004),
                (foot_r, 0.0025), (foot_r * 1.005, foot_h * 0.75), (foot_r * 1.04, foot_h), (rb, zb)]
        prof += [wall(math.pi / 2 * i / 10) for i in range(1, 11)]
        lip = (0.0, 0.6, 1.2, 1.57, 1.95, 2.55, 3.14)
    c = (rim_r - t / 2, h - t / 2)   # the rolled lip: half a circle over the top
    prof += [(c[0] + t / 2 * math.cos(a), c[1] + t / 2 * math.sin(a)) for a in lip]
    inside = [wall(math.pi / 2 * i / 20, t) for i in range(20, -1, -1)]
    for (r0, z0), (r1, z1) in zip(inside, inside[1:]):   # down the inside to the fill
        if z1 <= fill_z:
            rf = r0 + (r1 - r0) * (fill_z - z0) / (z1 - z0)
            prof.append((rf, fill_z))
            break
        prof.append((r1, z1))
    p.lathe(prof, 'Celadon', n=n, close_ends=False, deform=deform)
    p.lathe([(foot_r * 0.8, 0.0045), (foot_r * 0.4, 0.0062), (0.0, 0.0065)], 'Celadon', n=n, close_ends=False,
            deform=deform)                                                                     # under the foot
    p.lathe([(rf, fill_z), (rf * 0.5, fill_z + 0.0004), (0.0, fill_z + 0.0005)], fill, n=n, close_ends=False,
            deform=deform)
    return fill_z, rf


def wok_pool(p, r, z, mat, n=48, at=(0.0, 0.0), sx=1.0, wobble=0.0, seed=0):
    """The pool of broth or sauce a dish sits in in the wok: a smooth disc r across with its top at z, its edge a
    rounded bead that comes down to the wok at z = 0 (nothing below it); n round, so the edge is a smooth curve,
    stretched by sx along x and, with `wobble`, gently lobed. Returns z."""
    rnd = random.Random(seed)
    ph = [rnd.uniform(0, 6) for _ in range(3)]

    def edge(q):
        a = math.atan2(q.y, q.x)
        k = 1 + wobble * (0.6 * math.sin(3 * a + ph[0]) + 0.4 * math.sin(5 * a + ph[1]))
        return Vector((q.x * k, q.y * k, q.z))
    e = min(0.004, z * 0.6)
    p.lathe([(r, 0.0), (r + e * 0.25, z * 0.45), (r - e * 0.2, z * 0.9), (r - e, z), (r * 0.5, z + 0.0004), (0.0, z + 0.0005)],
            mat, n=n, M=Matrix.Translation((*at, 0.0)) @ Matrix.Diagonal((sx, 1.0, 1.0, 1.0)), close_ends=False,
            deform=edge if wobble else None)
    return z


def squeeze(d, r, soft=0.01):
    """A distance d from the bowl's middle pressed in so that it never passes r: unchanged up to r - soft, then eased
    in smoothly (never folding what it squeezes)."""
    r1 = r - soft
    return d if d <= r1 else r1 + soft * math.tanh((d - r1) / soft)


def keep_within(p, n0, r0, z0, slope=0.25, margin=0.002):
    """Presses whatever was added to p since it had n0 vertices in against the inside of the bowl instead of through
    it: the inside is r0 across at z0 (round_bowl's fill height and radius) and narrows by `slope` per metre lower
    down (widening above), and nothing may come within `margin` of it."""
    p.bm.verts.ensure_lookup_table()
    for v in p.bm.verts[n0:]:
        r = r0 - margin + slope * (v.co.z - z0)
        d = math.hypot(v.co.x, v.co.y)
        if d > r - 0.01:
            k = squeeze(d, r) / d
            v.co.x, v.co.y = v.co.x * k, v.co.y * k


def round_tube(p, pts, radius, mat, sides=6):
    """A smooth round tube along a polyline whose ends are rounded off like a fingertip, not cut flat: noodles,
    strands, shreds. Rings are oriented from the tangent × Z, so keep the path from turning vertical."""
    pts = [Vector(q) for q in pts]
    t0, t1 = (pts[1] - pts[0]).normalized(), (pts[-1] - pts[-2]).normalized()
    path = [(pts[0] - t0 * radius * 0.55, 0.62)] + [(q, 1.0) for q in pts] + [(pts[-1] + t1 * radius * 0.55, 0.62)]
    tmp = bmesh.new()
    rings = []
    for i, (q, k) in enumerate(path):
        a = path[min(i + 1, len(path) - 1)][0] - path[max(i - 1, 0)][0]
        a.normalize()
        u = a.cross(Vector((0, 0, 1)))
        if u.length < 1e-4:
            u = Vector((1, 0, 0))
        u.normalize()
        w = a.cross(u)
        rings.append([tmp.verts.new(q + radius * k * (math.cos(2 * math.pi * j / sides) * u +
                                                      math.sin(2 * math.pi * j / sides) * w)) for j in range(sides)])
    for ra, rb in zip(rings, rings[1:]):
        for j in range(sides):
            tmp.faces.new((ra[j], ra[(j + 1) % sides], rb[(j + 1) % sides], rb[j]))
    tips = (tmp.verts.new(pts[0] - t0 * radius * 0.95), tmp.verts.new(pts[-1] + t1 * radius * 0.95))
    for j in range(sides):
        tmp.faces.new((rings[0][(j + 1) % sides], rings[0][j], tips[0]))
        tmp.faces.new((rings[-1][j], rings[-1][(j + 1) % sides], tips[1]))
    p._commit(tmp, mat)


def wavy_noodles(p, z, rmax, rows, seed, radius=0.0042, mat='Noodle', amp=0.009, sides=6, npts=13):
    """Thick noodles lying in waves across the broth at height z (or on a heap: z(d) at a distance d from the middle),
    one strand per row of (y, x0, x1, phase): each
    runs across from x0 to x1 swinging `amp` either side of y, bobbing a little in and out of the broth, and stops
    short of the bowl's wall (rmax); `npts` points along each strand."""
    rnd = random.Random(seed)
    for (y, x0, x1, ph) in rows:
        pts = []
        waves = rnd.uniform(1.6, 2.4)   # swings across the bowl
        for j in range(npts):
            f = j / (npts - 1)
            x = x0 + (x1 - x0) * f
            yy = y + amp * math.sin(f * waves * 2 * math.pi + ph)
            d = math.hypot(x, yy)
            if d > rmax:
                x, yy = x * rmax / d, yy * rmax / d
            zz = z(math.hypot(x, yy)) if callable(z) else z
            pts.append((x, yy, zz + radius * (0.55 + 0.3 * math.sin(f * 7 + ph))))
        round_tube(p, pts, radius, mat, sides=sides)


def napa_leaf(p, base, yaw, length, width, lift=0.004, ruffle=0.0045, seed=0, thick=0.0035, rmax=None,
              colours=('Stem', 'Greens', 'BokChoy'), stalk=0.17, rib=0.62, pitch=0.0, cage=(6, 4)):
    """A leaf of napa cabbage lying flat from its stem end at base, turned `yaw`: a broad blade, round at the tip,
    its margin ruffled up and down; the pale stalk and midrib (Stem) widen into the light green blade (Greens), and
    the frilled tip is darker (BokChoy). A thick slab, rounded off by soft, so no edge is sharp; with rmax it is kept
    inside that radius of the bowl's middle (pressed against the wall rather than poking through). `colours` are the
    stalk, blade and tip colours, `stalk` and `rib` how far up the leaf the stalk and the midrib run, `pitch` tips the
    leaf up from its stalk end; `cage` is how many cage faces it has along and across."""
    rnd = random.Random(seed)
    nu, nv = cage
    R = Matrix.Translation(base) @ Matrix.Rotation(yaw, 4, 'Z')
    ph = rnd.uniform(0, 6)

    def point(i, j, side):
        u, v = i / nu, j / nv * 2 - 1   # u from stem (0) to tip (1), v across
        half = width / 2 * (0.32 + 0.68 * math.sin(math.pi * min(1.0, 0.18 + u * 0.95)) ** 0.7)
        z = lift * u + ruffle * abs(v) ** 1.5 * math.sin(u * 9 + v * 3 + ph) * u + side * thick / 2 +             math.sin(pitch) * u * length
        z += 0.003 * (1 - v * v) * math.sin(math.pi * u)   # the midrib arched a little
        q = R @ Vector((u * length, v * half, z))
        d = math.hypot(q.x, q.y)
        if rmax and d > rmax:
            q.x, q.y = q.x * rmax / d, q.y * rmax / d
        return q

    tmp = bmesh.new()
    top = [[tmp.verts.new(point(i, j, 1)) for j in range(nv + 1)] for i in range(nu + 1)]
    bot = [[tmp.verts.new(point(i, j, -1)) for j in range(nv + 1)] for i in range(nu + 1)]
    mats = []

    def colour(i, j):
        u, v = (i + 0.5) / nu, abs((j + 0.5) / nv * 2 - 1)
        st, bl, tp = colours
        return st if u < stalk or (v < 0.26 and u < rib) else (tp if u > 0.7 and v > 0.45 else bl)
    for i in range(nu):
        for j in range(nv):
            tmp.faces.new((top[i][j], top[i + 1][j], top[i + 1][j + 1], top[i][j + 1]))
            mats.append(colour(i, j))
            tmp.faces.new((bot[i][j + 1], bot[i + 1][j + 1], bot[i + 1][j], bot[i][j]))
            mats.append(colour(i, j))
    ring = [(i, 0) for i in range(nu)] + [(nu, j) for j in range(nv)] + [(i, nv) for i in range(nu, 0, -1)] + \
           [(0, j) for j in range(nv, 0, -1)]
    for (a, b) in zip(ring, ring[1:] + ring[:1]):   # the rim of the slab
        tmp.faces.new((top[a[0]][a[1]], bot[a[0]][a[1]], bot[b[0]][b[1]], top[b[0]][b[1]]))
        mats.append(colour(min(a[0], nu - 1), min(a[1], nv - 1)))
    with p.soft():
        piece_in_colours(p, tmp, mats)


def scallion_rings2(p, spots, z, r=0.0042, seed=0):
    """Rings of chopped scallion lying flat at (x, y) on a surface at z (or z(x, y)): a green ring round a paler
    middle, rounded. The green runs from the middle of the underside out, up and over to the white, so its faces
    point outwards and the ring is closed (no inside-out or open faces for back-face culling to drop)."""
    rnd = random.Random(seed)
    for (x, y) in spots:
        h = z(x, y) if callable(z) else z
        a = rnd.uniform(0, math.pi)
        p.lathe([(0.0, h - r * 0.45), (r, h - r * 0.4), (r * 1.05, h), (r, h + r * 0.45), (r * 0.45, h + r * 0.55)],
                'Scallion', n=8,
                M=Matrix.Translation((x, y, 0.0)) @ Matrix.Rotation(a, 4, 'Z') @ Matrix.Diagonal((1.0, 0.85, 1.0, 1.0)),
                close_ends=False)
        p.lathe([(r * 0.45, h + r * 0.55), (0.0, h + r * 0.5)], 'ScallionWhite', n=8,
                M=Matrix.Translation((x, y, 0.0)) @ Matrix.Rotation(a, 4, 'Z') @ Matrix.Diagonal((1.0, 0.85, 1.0, 1.0)),
                close_ends=False)


def scalloped(lobes, depth, r0, r1, phase=0.0):
    """Deform for a flower-rimmed bowl: `lobes` round scallops with notches between them, `depth` of the radius deep,
    fading in from radius r0 to r1 so the foot stays round (lathe it with n a multiple of lobes, 8 or more each)."""
    def deform(q):
        f = min(1.0, max(0.0, (math.hypot(q.x, q.y) - r0) / (r1 - r0))) ** 1.5
        k = 1 + depth * (abs(math.cos(lobes * (math.atan2(q.y, q.x) + phase) / 2)) ** 0.6 - 0.75) * f
        return Vector((q.x * k, q.y * k, q.z))
    return deform


# 菜面 traced from its art (trace_noodles.py D02): its golden broth, the wide noodles, the napa cabbage's pale blades
# with white veins and dark green frills, the scallion's dark green and its pale cut ends
PALETTE.update({'CaimianBroth': ('#e6c460', '#c9a440'), 'CaimianNoodle': ('#fcefcc', '#ead6a4'),
                'CaimianLeaf': ('#cad35a', '#a6b03c'), 'CaimianLeafDark': ('#5c8c1e', '#406c12'),
                'CaimianScallion': ('#5f9620', '#437414'), 'CaimianScallionCut': ('#e2e48c', '#c2c866')})
GLOSS.update({'CaimianBroth': 0.8, 'CaimianNoodle': 0.35, 'CaimianLeaf': 0.3, 'CaimianLeafDark': 0.3,
              'CaimianScallion': 0.45, 'CaimianScallionCut': 0.3})
VIVID.update({'CaimianBroth': 0.5, 'CaimianNoodle': 0.3, 'CaimianLeaf': 1.0, 'CaimianLeafDark': 0.6,
              'CaimianScallion': 0.7, 'CaimianScallionCut': 0.5})
VTINT.update(dict.fromkeys(('CaimianNoodle', 'CaimianLeaf', 'CaimianLeafDark', 'CaimianScallion',
                            'CaimianScallionCut'), 1.0))
DETAIL.update({'CaimianLeaf': ('food_veins', 30, '#f2f6cc', 0.45, 0.25),
               'CaimianLeafDark': ('food_veins', 30, '#8ab846', 0.4, 0.25),
               'CaimianScallion': ('food_fiber', 30, '#94c856', 0.3, 0.2)})
TRACED_D02 = os.path.join(os.path.dirname(__file__), 'traced_D02.json')


def as_drawn(p, el):
    """The whole dish stretched so that the icons' view (from in front, 35° up) shows it as the art does, drawn from
    el° up: depth by sin(el) / sin(35°), height by cos(el) / cos(35°) (the bowl a little oval, a little lower)."""
    sy = math.sin(math.radians(el)) / math.sin(ART_EL)
    sz = math.cos(math.radians(el)) / math.cos(ART_EL)
    for v in p.bm.verts:
        v.co.y *= sy
        v.co.z *= sz


def traced_noodle_dish(p, path, lower, ink, noodle_ink='#c8a058'):
    """A noodle dish's traced food (trace_noodles.py): the noodles with the warm line the art draws round each
    strand, then the rest with its own darker line; lowered by lower(x, y) in the wok."""
    from .plates import traced_dish   # here: plates imports bowls
    pieces = json.load(open(path, encoding='utf-8'))['pieces']
    strands = [q['name'] for q in pieces if q['kind'] == 'strand']
    traced_dish(p, path, skip=[q['name'] for q in pieces if q['kind'] != 'strand'], ink=noodle_ink, lower=lower)
    traced_dish(p, path, skip=strands, ink=ink, lower=lower)


def caimian(col, wok=False):
    """菜面 traced from its art (trace_noodles.py D02 writes traced_D02.json): wide noodles strand by strand, each a
    round ridge over its outline in the art, floating in a golden broth among four leaves of napa cabbage (their
    pale blades veined white, dark green frills painted where the art has them) and pieces of cut scallion, in a
    deep, round-bellied celadon bowl on a foot ring whose lip and broth meet where the art draws them. In the wok
    the same, on the wok's pool of broth."""
    p = Part()
    zf = 0.05942   # the broth in the bowl, where the food floats (trace_noodles.py's BOWLS)
    if wok:
        bz = wok_pool(p, 0.078, 0.008, 'CaimianBroth')
    else:
        bz, _ = round_bowl(p, rim_r=0.08, h=0.07405, foot_r=0.04257, foot_h=0.01953, fill_z=zf, lean=1.22844,
                           t=0.00544, fill='CaimianBroth', n=40, light=True)
    traced_noodle_dish(p, TRACED_D02, (lambda x, y: zf - bz) if wok else None, '#3c4a1a')
    as_drawn(p, 39.08568)   # the art's view (trace_noodles.py's camera), seen at the icons' 35°
    return p.finish('SM_D02' + ('_wok' if wok else ''), col, sharp=None)


# 馄饨 as the art paints it (trace_d03.py): cream wrappers with warm shadows in their folds and the art's brown line
# round them, the minced filling pink-tan through the wrapper, in an olive-gold broth with green rings of scallion
# and slivers of fried garlic.
PALETTE.update({
    'HuntunSkin': ('#fff6e2', '#e2c290'),    # the thin wrapper, cream
    'HuntunFill': ('#ebbaa0', '#cc967c'),    # the filling seen through it, pink
    'HuntunInk': ('#8a5a34', '#6a4024'),     # the brown lines of the wrapper's folds
    'HuntunBroth': ('#e8d8a0', '#c4ae70'),   # the pale olive-gold broth
    'HuntunBit': ('#f3d98c', '#d6b864'),     # slivers of fried garlic in it
})
GLOSS.update({'HuntunSkin': 0.35, 'HuntunFill': 0.2, 'HuntunInk': 0.0, 'HuntunBroth': 0.7, 'HuntunBit': 0.2})
VIVID.update({'HuntunSkin': 0.35, 'HuntunFill': 0.35, 'HuntunInk': 0.5, 'HuntunBroth': 0.35, 'HuntunBit': 0.5})
VTINT.update(dict.fromkeys(('HuntunSkin', 'HuntunFill'), 1.0))   # fold shadows, the light, the ink line
DETAIL.update({'HuntunSkin': ('food_mottle', 18, '#fff4dc', 0.15, 0.12),
               'HuntunFill': ('food_chopped', 50, '#f6d8c6', 0.5, 0.35)})
TRACED_D03 = os.path.join(os.path.dirname(__file__), 'traced_D03.json')


def huntun_ring(p, c, r, mat='Scallion'):
    """A ring of scallion lying flat at c, r its outer radius: a hollow tube of green, its wall a fifth of r thick,
    rounded all round (the broth shows through its middle). 64 triangles."""
    a = r * 0.2
    prof = [(r - a + a * math.cos(t), a * 0.8 * math.sin(t)) for t in (0.0, 1.57, 3.14, 4.71, 6.28)]
    p.lathe([(rr, z) for rr, z in prof], mat, n=8, M=Matrix.Translation(c) @ Matrix.Diagonal((1.0, 1.0, 1.0, 1.0)),
            close_ends=False)


def huntun(col, wok=False):
    """馄饨 traced from its art (trace_d03.py writes traced_D03.json): six wontons floating in an olive-gold broth in a
    deep celadon bowl with a flared wall on a broad foot ring, rings of scallion and slivers of fried garlic between
    them. Every wonton follows its outline in the art, a soft mound floating on the broth, its filling a dome in the
    middle painted where the art shows it through the wrapper, the folds' shadows and light tinted in and the art's
    brown line round it. In the wok, all of it on the wok's pool of broth."""
    from .plates import traced_dish   # here: plates imports bowls
    data = json.load(open(TRACED_D03, encoding='utf-8'))
    zf = data['fill_z']
    p = Part()
    if wok:
        bz = wok_pool(p, 0.08, 0.008, 'HuntunBroth')
    else:
        bz, _ = round_bowl(p, rim_r=0.0875, h=0.0792, foot_r=0.0435, foot_h=0.013, fill_z=zf, fill='HuntunBroth',
                           n=48, light=True, flare=(17.2, 81.7, 0.26), t=0.0076)
    dz = bz - zf
    traced_dish(p, TRACED_D03, ink='#7a4a26', lower=(lambda x, y: -dz) if wok else None)
    for ring in data['rings']:
        x, y, z = ring['c']
        huntun_ring(p, (x, y, z + dz + 0.0006), ring['r'])
    for f in data['flecks']:
        x, y, z = f['c']
        p.blob((x, y, z + dz + 0.0003), f['length'] / 2, 'HuntunBit',
               squash=(1.0, f['width'] / f['length'], 0.0012 / f['length']), segs=(6, 3), rot=f['yaw'])
    return p.finish('SM_D03' + ('_wok' if wok else ''), col, sharp=None)

# 瓜齑萝卜 as the art paints it (trace_d04.py): julienned radish, creamy white and glistening, and cucumber, pale
# yellow-green flesh with its dark green skin along an edge, heaped criss-cross over a golden dressing.
PALETTE.update({
    'GuajiRadish': ('#faeccb', '#dcc290'),        # the radish strips, cream
    'GuajiCucumber': ('#e0db8a', '#b8b24b'),      # the cucumber's flesh, pale yellow-green
    'GuajiCucumberSkin': ('#4f6416', '#38490c'),  # and its skin, dark olive green
    'GuajiDressing': ('#e8cf8e', '#c9aa62'),      # the dressing pooled under them
    'GuajiHeap': ('#c9a85e', '#a8873e'),          # the warm shadow between the strips
})
GLOSS.update({'GuajiRadish': 0.45, 'GuajiCucumber': 0.45, 'GuajiCucumberSkin': 0.5, 'GuajiDressing': 0.75,
              'GuajiHeap': 0.3})
VIVID.update({'GuajiRadish': 0.5, 'GuajiCucumber': 0.6, 'GuajiCucumberSkin': 0.7, 'GuajiDressing': 0.5,
              'GuajiHeap': 0.4})
VTINT.update(dict.fromkeys(('GuajiRadish', 'GuajiCucumber', 'GuajiCucumberSkin'), 1.0))
DETAIL.update({'GuajiRadish': ('food_frost', 28, '#ffffff', 0.75, 0.2),
               'GuajiCucumber': ('food_frost', 28, '#f6fadf', 0.55, 0.2),
               'GuajiCucumberSkin': ('food_mottle', 30, '#2f4a14', 0.35, 0.2)})
TRACED_D04 = os.path.join(os.path.dirname(__file__), 'traced_D04.json')


def guaji_luobo(col, wok=False):
    """瓜齑萝卜 traced from its art (trace_d04.py writes traced_D04.json): a heap of julienned radish and cucumber
    criss-crossing over a golden dressing in a flower-rimmed celadon bowl (eight lobes) with a flared wall on a broad
    foot ring. Every strip follows its outline in the art, a rounded bar lying on the heap, the cucumber's dark skin
    painted along its edge, the radish's shadows and glints tinted in, flecks of light all over them; under them the
    heap, gold where a gap shows. In the wok, the heap on the wok's pool of dressing."""
    from .plates import traced_dish   # here: plates imports bowls
    data = json.load(open(TRACED_D04, encoding='utf-8'))
    zf = data['fill_z']
    p = Part()
    if wok:
        bz = wok_pool(p, 0.07, 0.006, 'GuajiDressing')
    else:
        bz, _ = round_bowl(p, rim_r=0.085, h=0.0534, foot_r=0.0485, foot_h=0.0209, fill_z=zf, fill='GuajiDressing',
                           n=40, light=True, flare=(24.0, 81.4, 0.412), t=0.0052, deform=scalloped(8, 0.089, 0.06, 0.086))
    dz = bz - zf
    traced_dish(p, TRACED_D04, ink='#6a5a36', lower=(lambda x, y: -dz) if wok else None)
    return p.finish('SM_D04' + ('_wok' if wok else ''), col, sharp=None)


def soft_slab(p, M, length, width, thick, colour, nu=6, nv=3, sq=4.0, wobble=0.06, seed=0, warp=None, vmap=None):
    """A slab length × width × thick (a slice of meat, a sheet of tofu or jelly), its outline a rounded rectangle
    (a superellipse of power sq, wobbled), built as a cage and smoothed (soft), so every edge is rounded.
    colour(u, v, side) names each face's material: u, v from -1 to 1 along and across, side 'top', 'bottom' or
    'rim'. warp(Vector) -> Vector bends the slab in its own frame before M places it; vmap(v) moves the rows of the
    cage across it (v from -1 to 1), so that a narrow band of faces can take its own colour."""
    rnd = random.Random(seed)
    bumps = [rnd.uniform(-wobble, wobble) for _ in range(2 * (nu + nv))]

    def at(i, j, side):
        x, y = i / nu * 2 - 1, j / nv * 2 - 1
        if vmap:
            y = vmap(y)
        m = max(abs(x), abs(y))
        if m > 1e-6:   # square to rounded rectangle, the boundary rippled
            k = m / (abs(x) ** sq + abs(y) ** sq) ** (1 / sq)
            ring = (i + j) if j == 0 or i == nu else (nu + nv + (nu - i) + (nv - j))
            k *= 1 + bumps[ring % len(bumps)] * m ** 4
            x, y = x * k, y * k
        q = Vector((x * length / 2, y * width / 2, side * thick / 2))
        return M @ (warp(q) if warp else q)
    tmp = bmesh.new()
    top = [[tmp.verts.new(at(i, j, 1)) for j in range(nv + 1)] for i in range(nu + 1)]
    bot = [[tmp.verts.new(at(i, j, -1)) for j in range(nv + 1)] for i in range(nu + 1)]
    mats = []

    def uv(i, j):
        return (i + 0.5) / nu * 2 - 1, (j + 0.5) / nv * 2 - 1
    for i in range(nu):
        for j in range(nv):
            tmp.faces.new((top[i][j], top[i + 1][j], top[i + 1][j + 1], top[i][j + 1]))
            mats.append(colour(*uv(i, j), 'top'))
            tmp.faces.new((bot[i][j + 1], bot[i + 1][j + 1], bot[i + 1][j], bot[i][j]))
            mats.append(colour(*uv(i, j), 'bottom'))
    ring = [(i, 0) for i in range(nu)] + [(nu, j) for j in range(nv)] + [(i, nv) for i in range(nu, 0, -1)] + \
           [(0, j) for j in range(nv, 0, -1)]
    for (a, b) in zip(ring, ring[1:] + ring[:1]):
        tmp.faces.new((top[a[0]][a[1]], bot[a[0]][a[1]], bot[b[0]][b[1]], top[b[0]][b[1]]))
        mats.append(colour(*uv(min(a[0], nu - 1), min(a[1], nv - 1)), 'rim'))
    with p.soft():
        piece_in_colours(p, tmp, mats)


def pork_slice(p, c, yaw, length=0.058, width=0.03, thick=0.007, tilt=0.0, seed=0, cage=(6, 4), fat=True):
    """A slice of braised pork belly lying at c along yaw, its back edge lifted by `tilt` (resting on the slice behind):
    pink lean in the middle with a pale band of fat (unless not `fat`), the browned rind and edges all round. Rounded
    (soft); `cage` is how many cage faces it has along and across."""
    def colour(u, v, side):
        if side == 'rim' or abs(u) > 0.84 or v > 0.6:
            return 'PorkRind'
        return 'Fat' if fat and -0.25 < v < 0.05 else 'PorkLean'
    M = Matrix.Translation(c) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(tilt, 4, 'X')
    soft_slab(p, M, length, width, thick, colour, nu=cage[0], nv=cage[1], seed=seed,
              warp=lambda q: Vector((q.x, q.y, q.z + 0.0025 * math.sin(q.x / length * 6 + seed))))


def bok_choy_head(p, base, yaw, length=0.075, seed=0, rmax=None, cage=(6, 4), bulb=(8, 4)):
    """A head of bok choy lying from its base at `base` along yaw: three leaves fanned a little, each a pale green
    spoon-shaped stalk widening into a dark green, ruffled blade, the stalks gathered into a rounded bulb at the
    base. `cage` is each leaf's cage (along, across), `bulb` the bulb's segments."""
    d = Vector((math.cos(yaw), math.sin(yaw), 0.0))
    for k, (turn, lift, ln, wd) in enumerate(((-0.28, 0.0, 0.95, 0.5), (0.3, 0.002, 0.9, 0.48), (0.0, 0.006, 1.0, 0.56))):
        napa_leaf(p, base + Vector((0, 0, lift)) - d * 0.004, yaw + turn, length * ln, length * wd, lift=0.008,
                  ruffle=0.004, seed=seed * 3 + k, thick=0.0045, rmax=rmax, colours=('BokStalk', 'BokChoy', 'BokChoy'),
                  stalk=0.42, rib=0.8, pitch=0.12, cage=cage)
    with p.soft():
        p.blob(base + d * 0.012 + Vector((0, 0, 0.007)), 0.016, 'BokStalk', squash=(1.25, 0.85, 0.55), segs=bulb,
               rot=yaw)


def scallion_chunk(p, c, yaw, r=0.0042, length=0.009, tilt=0.0, lite=False, n=8, mat='Scallion'):
    """A cut length of scallion lying on its side at c: a bright green tube (mat: 'ScallionPale' for the white part),
    its cut ends pale. Rounded (soft); `lite` builds it without soft(), its edges rounded by a bevel ring instead (a
    small piece: 64 triangles, not 384)."""
    M = Matrix.Translation(c) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(math.pi / 2 + tilt, 4, 'Y')
    if lite:
        e, h = min(0.0013, length * 0.2), length / 2
        p.lathe([(r * 0.76, -h), (r, -h + e), (r, h - e), (r * 0.76, h)], mat, n=n, M=M, close_ends=False)
        p.lathe([(0.0, -h - 0.0002), (r * 0.76, -h)], 'ScallionWhite', n=n, M=M, close_ends=False)
        p.lathe([(r * 0.76, h), (0.0, h + 0.0002)], 'ScallionWhite', n=n, M=M, close_ends=False)
        return
    with p.soft():
        p.lathe([(0.0, -length / 2), (r * 0.8, -length / 2), (r, -length / 2 + 0.0012), (r, length / 2 - 0.0012),
                 (r * 0.8, length / 2), (0.0, length / 2)], mat, n=8, M=M, close_ends=False)
    with p.soft():   # the pale cut ends, a hair proud of the tube's ends
        for sgn in (-1, 1):
            prof = [(0.0, sgn * (length / 2 + 0.0004)), (r * 0.62, sgn * (length / 2 + 0.0002))]
            p.lathe(prof if sgn < 0 else prof[::-1], 'ScallionWhite', n=8, M=M, close_ends=False)

# 插肉面 traced from its art (trace_noodles.py D09): golden broth, round noodles, braised pork belly (pink lean, pale
# fat, the browned rind round each slice), bok choy (dark green blades, pale stalks), bright cut scallion
PALETTE.update({'CharouBroth': ('#e2b84e', '#c69a34'), 'CharouNoodle': ('#f9e4b2', '#e6c88a'),
                'CharouPork': ('#f2b890', '#d69670'), 'CharouRind': ('#b45c30', '#8a421e'),
                'CharouBokLeaf': ('#4e7e26', '#365e16'), 'CharouBokDark': ('#2e5212', '#1e3a0a'),
                'CharouBokStalk': ('#e0e6a6', '#bcc87c'), 'CharouScallion': ('#6a9c22', '#4a7814'),
                'CharouScallionCut': ('#d8e28c', '#b6c464')})
GLOSS.update({'CharouBroth': 0.8, 'CharouNoodle': 0.35, 'CharouPork': 0.5, 'CharouRind': 0.6, 'CharouBokLeaf': 0.45,
              'CharouBokDark': 0.4, 'CharouBokStalk': 0.4, 'CharouScallion': 0.45, 'CharouScallionCut': 0.3})
VIVID.update({'CharouBroth': 0.55, 'CharouNoodle': 0.35, 'CharouPork': 0.35, 'CharouRind': 0.6, 'CharouBokLeaf': 0.7,
              'CharouBokDark': 0.6, 'CharouBokStalk': 0.45, 'CharouScallion': 0.75, 'CharouScallionCut': 0.5})
VTINT.update(dict.fromkeys(('CharouNoodle', 'CharouPork', 'CharouRind', 'CharouBokLeaf', 'CharouBokDark',
                            'CharouBokStalk', 'CharouScallion', 'CharouScallionCut'), 1.0))
PALETTE.update({'CharouNoodleV': PALETTE['CharouNoodle']})   # the same noodles, their strands along the other way
GLOSS.update({'CharouNoodleV': GLOSS['CharouNoodle']})
VIVID.update({'CharouNoodleV': VIVID['CharouNoodle']})
VTINT.update({'CharouNoodleV': 1.0})
DETAIL.update({'CharouNoodle': ('food_noodles', 20, '#dcae62', 0.45, 0.3),
               'CharouNoodleV': ('food_noodles_v', 20, '#dcae62', 0.45, 0.3)})
DETAIL.update({'CharouPork': ('food_fiber', 22, '#f6d8c6', 0.45, 0.35), 'CharouRind': ('food_pores', 18, '#7a3418', 0.3, 0.3),
               'CharouBokLeaf': ('food_veins', 28, '#8cbc50', 0.45, 0.25),
               'CharouBokStalk': ('food_fiber', 26, '#c8d890', 0.3, 0.2),
               'CharouScallion': ('food_fiber', 30, '#9ccc5a', 0.3, 0.2)})
TRACED_D09 = os.path.join(os.path.dirname(__file__), 'traced_D09.json')


def charou_mian(col, wok=False):
    """插肉面 traced from its art (trace_noodles.py D09 writes traced_D09.json): round noodles strand by strand,
    floating in golden broth, five slices of braised pork belly fanned over them (pink lean with pale fat, the
    browned rind round each), two heads of bok choy on the right (dark green blades, pale stalks), bright cubes of
    cut scallion, each piece over its outline in the art; in a deep celadon bowl on a foot ring whose lip and broth
    meet where the art draws them. In the wok the same, on the wok's pool of broth."""
    p = Part()
    zf = 0.07121   # the broth in the bowl, where the food floats (trace_noodles.py's BOWLS)
    if wok:
        bz = wok_pool(p, 0.078, 0.008, 'CharouBroth')
    else:
        bz, _ = round_bowl(p, rim_r=0.081, h=0.08282, foot_r=0.03628, foot_h=0.02145, fill_z=zf, lean=1.23659,
                           t=0.00344, fill='CharouBroth', n=48, light=True)
    traced_noodle_dish(p, TRACED_D09, (lambda x, y: zf - bz) if wok else None, '#4a2a14')
    as_drawn(p, 38.75259)   # the art's view (trace_noodles.py's camera), seen at the icons' 35°
    return p.finish('SM_D09' + ('_wok' if wok else ''), col, sharp=None)


def mound(p, at, r, z, hz, mat, n=48, sx=1.0, sink=0.002, power=0.75):
    """A smooth rounded mound (a heap of noodles, a pile of shreds) r across, rising hz above z at its middle, its edge
    sunk `sink` into whatever it stands in; sx stretches it along x. n round and seven rings up, so its outline is a
    smooth curve. Returns its height at (x, y)."""
    def height_d(d):
        u = min(1.0, d / r)
        return z + hz * math.cos(u * math.pi / 2) ** power
    radii = (1.0, 0.94, 0.84, 0.7, 0.53, 0.34, 0.0)
    prof = [(r, z - sink)] + [(r * k, height_d(r * k)) for k in radii[1:]]
    p.lathe(prof, mat, n=n, close_ends=False, M=Matrix.Translation((*at, 0.0)) @ Matrix.Diagonal((sx, 1.0, 1.0, 1.0)))

    def height(x, y):
        return height_d(math.hypot((x - at[0]) / sx, y - at[1]))
    return height


def coil(p, height, at, rho, a0, a1, radius, mat='ColdNoodle', wob=0.003, seed=0, step=0.36, rmax=None, sides=5):
    """A noodle lying in an arc round `at` at a distance rho, from angle a0 to a1 (radians), wandering `wob` in and
    out, resting on a surface whose height at (x, y) is height(x, y), kept within rmax of the bowl's middle."""
    n = max(3, int(abs(a1 - a0) / step) + 1)
    pts = []
    for j in range(n):
        a = a0 + (a1 - a0) * j / (n - 1)
        rr = rho + wob * math.sin(2.3 * a + seed * 1.7)   # wandering slowly in and out along it
        x, y = at[0] + rr * math.cos(a), at[1] + rr * math.sin(a)
        if rmax and math.hypot(x, y) > rmax:
            x, y = x * rmax / math.hypot(x, y), y * rmax / math.hypot(x, y)
        pts.append((x, y, height(x, y) + radius * 0.7))
    round_tube(p, pts, radius, mat, sides=sides)


def draped(height, lift, rmax=None):
    """Deform for a piece built round its own middle and already moved to its place: lays it over the surface whose
    height at (x, y) is height(x, y), `lift` above it, keeping its own thickness; with rmax, whatever reaches further
    than that from the bowl's middle is pulled in (pressed against the wall rather than through it)."""
    def deform(q):
        x, y = q.x, q.y
        d = math.hypot(x, y)
        if rmax and d > rmax - 0.01:
            k = squeeze(d, rmax) / d
            x, y = x * k, y * k
        return Vector((x, y, height(x, y) + lift + q.z))
    return deform


def lobed_leaf(p, c, yaw, length, width, mat='DarkGreens', lobes=5, depth=0.5, thick=0.0024, seed=0, deform=None,
               dome=0.003):
    """A soft leaf (coriander, celery) lying at c along yaw: an oval outline cut into `lobes` round lobes `depth`
    deep, a thin slab whose rim soft() rounds off, so no tip is sharp. `deform` (draped()) lays it over whatever it
    rests on, given points relative to the world (c already added); its middle is raised `dome` over its edge.
    4 x lobes x 10 triangles."""
    rnd = random.Random(seed)
    m = 2 * lobes
    R = Matrix.Rotation(yaw, 3, 'Z')
    tmp = bmesh.new()

    def put(x, y, z):
        q = Vector(c) + R @ Vector((x, y, 0.0))
        q = deform(q) if deform else q
        return tmp.verts.new(q + Vector((0.0, 0.0, z)))
    ring_t, ring_b = [], []
    for k in range(m):
        a = 2 * math.pi * k / m + rnd.uniform(-0.12, 0.12)
        k_r = (0.72 + 0.28 * math.cos(a)) * (1.0 if k % 2 == 0 else 1 - depth) * rnd.uniform(0.92, 1.08)   # tip lobe longest
        x, y = 0.5 * length * math.cos(a) * k_r, 0.5 * width * math.sin(a) * k_r
        curl = 0.0
        ring_t.append(put(x, y, thick / 2 + curl))
        ring_b.append(put(x, y, -thick / 2 + curl))
    ct, cb = put(0.0, 0.0, thick / 2 + dome), put(0.0, 0.0, -thick / 2 + dome)
    mats = []
    for k in range(m):
        k1 = (k + 1) % m
        tmp.faces.new((ct, ring_t[k], ring_t[k1]))
        tmp.faces.new((cb, ring_b[k1], ring_b[k]))
        tmp.faces.new((ring_t[k], ring_b[k], ring_b[k1], ring_t[k1]))
        mats += [mat] * 3
    with p.soft():
        piece_in_colours(p, tmp, mats)


def julienne_bar(p, a, b, w, t, flesh, skin, bend=0.0, stations=(0.0, 0.07, 0.5, 0.93, 1.0)):
    """A julienne strip (cucumber) from a to b, w wide and t thick, its broad face up, built as a soft cage so every
    edge and end comes out rounded: pale `flesh` with the dark `skin` down the side that faces the art's camera.
    Its cage has rings at `stations` along it (close to the ends, so they stay blunt), the middle raised by `bend` so
    it can arch over what it lies on. 32 x (len(stations) - 1) + 16 triangles."""
    a, b = Vector(a), Vector(b)
    x = (b - a).normalized()
    y = Vector((0.0, 0.0, 1.0)).cross(x).normalized()
    if y.y < 0:   # so the skin side (-y in its frame) faces the camera (-Y)
        y = -y
    up = x.cross(y)
    if up.z < 0:
        up = -up
    tmp = bmesh.new()
    rings = []
    for f in stations:
        o = a.lerp(b, f) + Vector((0.0, 0.0, bend * math.sin(math.pi * f)))
        rings.append([tmp.verts.new(o + y * sy * w / 2 + up * sz * t / 2)
                      for sy, sz in ((-1, -1), (1, -1), (1, 1), (-1, 1))])
    mats = []
    for i in range(len(stations) - 1):
        ra, rb = rings[i], rings[i + 1]
        for j in range(4):
            tmp.faces.new((ra[j], ra[(j + 1) % 4], rb[(j + 1) % 4], rb[j]))
            mats.append(skin if j == 3 else flesh)   # face 3 joins corners (-1, 1) and (-1, -1): the -y side
    tmp.faces.new(rings[0][::-1])
    tmp.faces.new(rings[-1])
    mats += [flesh, flesh]
    with p.soft():
        piece_in_colours(p, tmp, mats)


# 冷淘 traced from its art (trace_noodles.py D11): thin cold noodles, cream with peach shade, heaped high over the amber
# dressing, drops of it on them; julienned cucumber (pale yellow-green flesh, dark skin) and dark green herb leaves
PALETTE.update({'LengtaoDressing': ('#eeaa52', '#d08834'), 'LengtaoNoodle': ('#fdeccb', '#eccb98'),
                'LengtaoNest': ('#efc184', '#d49c5c'), 'LengtaoCucumber': ('#e2dc84', '#c0bc5c'),
                'LengtaoCucumberSkin': ('#5a7a14', '#3e5a0a'), 'LengtaoHerb': ('#4a7012', '#325208'),
                'LengtaoHerbDark': ('#2a4a06', '#1a3404')})
GLOSS.update({'LengtaoDressing': 0.8, 'LengtaoNoodle': 0.45, 'LengtaoNest': 0.3, 'LengtaoCucumber': 0.5,
              'LengtaoCucumberSkin': 0.45, 'LengtaoHerb': 0.35, 'LengtaoHerbDark': 0.3})
VIVID.update({'LengtaoDressing': 0.7, 'LengtaoNoodle': 0.2, 'LengtaoNest': 0.5, 'LengtaoCucumber': 0.55,
              'LengtaoCucumberSkin': 0.7, 'LengtaoHerb': 0.7, 'LengtaoHerbDark': 0.6})
VTINT.update(dict.fromkeys(('LengtaoNoodle', 'LengtaoNest', 'LengtaoCucumber', 'LengtaoCucumberSkin', 'LengtaoHerb',
                            'LengtaoHerbDark'), 1.0))
PALETTE.update({'LengtaoNoodleV': PALETTE['LengtaoNoodle']})   # the same noodles, their strands along the other way
GLOSS.update({'LengtaoNoodleV': GLOSS['LengtaoNoodle']})
VIVID.update({'LengtaoNoodleV': VIVID['LengtaoNoodle']})
VTINT.update({'LengtaoNoodleV': 1.0})
DETAIL.update({'LengtaoNoodle': ('food_noodles', 24, '#e89c50', 0.55, 0.35),
               'LengtaoNoodleV': ('food_noodles_v', 24, '#e89c50', 0.55, 0.35),
               'LengtaoNest': ('food_noodles', 24, '#d88438', 0.5, 0.3)})
DETAIL.update({'LengtaoCucumber': ('food_fiber', 30, '#f4f0b4', 0.35, 0.2),
               'LengtaoHerb': ('food_veins', 30, '#7aa83a', 0.45, 0.25),
               'LengtaoHerbDark': ('food_veins', 30, '#5a8a24', 0.4, 0.25)})
TRACED_D11 = os.path.join(os.path.dirname(__file__), 'traced_D11.json')


def lengtao(col, wok=False):
    """冷淘 traced from its art (trace_noodles.py D11 writes traced_D11.json): thin cold noodles strand by strand,
    coiled into a high nest over the amber dressing in a flared celadon bowl on a foot ring, drops of the dressing on
    them; the cucumber julienne laid across the top and the herb leaves round it, each piece over its outline in the
    art, lying on the nest. In the wok the nest on the wok's pool of dressing."""
    p = Part()
    zf = 0.04281   # the dressing in the bowl, which the nest stands in (trace_noodles.py's BOWLS)
    if wok:
        bz = wok_pool(p, 0.078, 0.006, 'LengtaoDressing')
    else:
        bz, rin = round_bowl(p, rim_r=0.085, h=0.07309, foot_r=0.02966, foot_h=0.00746, fill_z=zf,
                             fill='LengtaoDressing', t=0.003, n=40, light=True, flare=(30, 75, 0.4))
    n0 = len(p.bm.verts)
    traced_noodle_dish(p, TRACED_D11, (lambda x, y: zf - bz) if wok else None, '#2e4a10', noodle_ink='#d08a3c')
    if not wok:
        keep_within(p, n0, rin, bz, slope=0.45)
    as_drawn(p, 36.07684)   # the art's view (trace_noodles.py's camera), seen at the icons' 35°
    return p.finish('SM_D11' + ('_wok' if wok else ''), col, sharp=None)


# 文思豆腐 as the art paints it (trace_d16.py): hair-fine white threads of tofu swirling over the gold of the clear
# broth, curved shreds of shiitake dark on top and pale beneath, straight shreds of bamboo shoot, yellow-green
# scallion.
PALETTE.update({
    'WensiBroth': ('#e8d49a', '#c4ae6e'),          # the clear golden broth
    'WensiBase': ('#f0d38e', '#d4b068'),           # the gold between the threads
    'WensiSilk': ('#fcf1d8', '#e8d4a8'),           # the threads of tofu, white
    'WensiShiitake': ('#9a5e36', '#744222'),       # shreds of shiitake, brown on top
    'WensiShiitakeFlesh': ('#c08a5a', '#9a6a40'),  # and their pale flesh along an edge
    'WensiBamboo': ('#fad57e', '#dcb056'),         # shreds of bamboo shoot, pale yellow
    'WensiScallion': ('#a8c42e', '#7e9a14'),       # the cut scallion, yellow-green
})
GLOSS.update({'WensiBroth': 0.7, 'WensiBase': 0.4, 'WensiSilk': 0.3, 'WensiShiitake': 0.3, 'WensiShiitakeFlesh': 0.2,
              'WensiBamboo': 0.3, 'WensiScallion': 0.5})
VIVID.update({'WensiBroth': 0.45, 'WensiBase': 0.5, 'WensiSilk': 0.3, 'WensiShiitake': 0.5, 'WensiShiitakeFlesh': 0.4,
              'WensiBamboo': 0.6, 'WensiScallion': 0.8})
VTINT.update(dict.fromkeys(('WensiBase', 'WensiSilk', 'WensiShiitake', 'WensiShiitakeFlesh', 'WensiBamboo',
                            'WensiScallion'), 1.0))
DETAIL.update({'WensiSilk': ('food_fiber', 40, '#fffaf0', 0.25, 0.15),
               'WensiShiitake': ('food_fiber', 35, '#a87048', 0.35, 0.2),
               'WensiBamboo': ('food_fiber', 35, '#fff0c0', 0.35, 0.2)})
TRACED_D16 = os.path.join(os.path.dirname(__file__), 'traced_D16.json')


def wensi_doufu(col, wok=False):
    """文思豆腐 traced from its art (trace_d16.py writes traced_D16.json): in a clear golden broth in a deep, flared
    celadon bowl on a foot ring, the mass of tofu threads as the art outlines it, a low mound golden like the broth
    between the threads, and on it the threads themselves, white strands following the art's own flow line by line
    (straight across on the left, swirling on the right); on them the shreds of shiitake (dark, their pale flesh along
    an edge) and of bamboo shoot, and the cut scallion, each where and as the art has it, a rounded piece over its
    outline, its glints tinted in. In the wok, all of it on the wok's pool of broth."""
    from .plates import traced_dish   # here: plates imports bowls
    data = json.load(open(TRACED_D16, encoding='utf-8'))
    zf = data['fill_z']
    p = Part()
    if wok:
        bz = wok_pool(p, 0.078, 0.008, 'WensiBroth')
    else:
        bz, _ = round_bowl(p, rim_r=0.085, h=0.082, foot_r=0.035, foot_h=0.014, fill_z=zf, fill='WensiBroth',
                           n=48, light=True, flare=(32, 78, 0.4), t=0.007)
    dz = bz - zf
    traced_dish(p, TRACED_D16, ink='#4a2b18', lower=(lambda x, y: -dz) if wok else None)
    return p.finish('SM_D16' + ('_wok' if wok else ''), col, sharp=None)


def tofu_block(p, c, yaw, s, h, mat='MapoTofu', tilt=0.0):
    """A block of soft tofu for soft(): a box s square and h tall centred on c, turned yaw, its edges chamfered so
    soft() rounds them into the plump, soft-cornered block the art shows. 192 triangles."""
    p.box((0, 0, 0), (s, s, h), mat, r=min(0.0036, s * 0.15), seg=1,
          M=Matrix.Translation(c) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(tilt, 4, 'X'))


def mapo_doufu(col, wok=False):
    """麻婆豆腐（简化版） as the art has it: eight plump blocks of tofu stained orange, standing a centimetre proud of a
    deep red chilli sauce in a flared celadon bowl on a foot ring, clusters of minced pork all through the sauce and
    on the tofu, cut scallion (green and a few pale rings) and red chilli flakes over it all: tofu, pork and chilli
    all show. Placed from art_match's grid (cm) read at z = 0.07; panel pixels where noted."""
    p = Part()
    if wok:
        bz, rin = wok_pool(p, 0.078, 0.008, 'ChiliOil'), 0.078
        n0 = len(p.bm.verts)
    else:
        bz, rin = round_bowl(p, rim_r=0.085, h=0.08, foot_r=0.036, foot_h=0.013, fill_z=0.074, fill='ChiliOil',
                             n=48, light=True, flare=(28, 78, 0.4), t=0.006)
    n0 = len(p.bm.verts)
    dz = bz - 0.074   # the wok's dish is the bowl's, lower
    height = 0.022   # how tall the tofu is
    rise = 0.0095 if not wok else height - bz   # how far it stands out of the sauce (in the wok it rests on the wok)
    blocks = []
    for (u, v, yaw, s) in ((285, 232, -0.2, 0.03), (488, 237, 0.35, 0.034), (183, 300, 0.1, 0.03),
                           (390, 335, -0.15, 0.036), (633, 345, 0.3, 0.031), (180, 402, -0.25, 0.033),
                           (537, 436, 0.45, 0.03), (338, 480, 0.15, 0.031)):   # top faces' middles, panel px
        gx, gy = (u - 398.5) / 43.7, (380.5 - v) / 25.0
        top = 0.074 + 0.0095
        blocks.append((Vector((gx / 100, art_y(gy / 100, top, 0.07))), yaw, s / 2, bz + rise))

    def support(x, y):   # the top of a tofu block, or the sauce
        for (c, yaw, hs, top) in blocks:
            d = Matrix.Rotation(-yaw, 2) @ (Vector((x, y)) - c)
            if abs(d.x) < hs * 0.92 and abs(d.y) < hs * 0.92:
                return top
        return bz

    def seat(u, v, lift):   # a panel pixel to a point lift above whatever is there
        gx, gy = (u - 398.5) / 43.7, (380.5 - v) / 25.0
        x, y = gx / 100, gy / 100
        z = support(x, y) + lift
        for _ in range(4):
            y = art_y(gy / 100, z - dz, 0.07)
            z = support(x, y) + lift
        return Vector((x, y, z))
    rnd = random.Random(17)
    with p.soft():
        for (c, yaw, hs, top) in blocks:
            tofu_block(p, (c.x, c.y, top - height / 2), yaw, hs * 2, height)
    for (u, v) in ((380, 210), (330, 235), (345, 262), (590, 270), (620, 295), (565, 290), (520, 300), (440, 265),
                   (470, 300), (305, 320), (270, 345), (240, 335), (330, 395), (370, 410), (420, 440), (450, 480),
                   (480, 520), (440, 505), (240, 445), (200, 460), (150, 470), (100, 400), (560, 375), (580, 410),
                   (640, 440), (680, 470), (630, 480), (520, 380), (550, 530), (380, 540), (690, 420), (270, 240)):
        c = seat(u, v, 0.0)   # a cluster of minced pork: three crumbs
        for j in range(3):
            a = rnd.uniform(0, 2 * math.pi) + j * 2.1
            r = rnd.uniform(0.0024, 0.0031)
            q = c + Vector((0.0034 * math.cos(a), 0.0034 * math.sin(a), 0.0))
            z = support(q.x, q.y) + r * 0.45
            p.blob((q.x, q.y, z), r, 'MincedPork', squash=(1.0, 0.9, 0.75), segs=(6, 3), rot=rnd.uniform(0, 3))
    for k, (u, v, white) in enumerate(((293, 262, 0), (350, 280, 1), (385, 260, 0), (460, 290, 0), (430, 318, 0),
                                       (510, 310, 0), (390, 335, 0), (300, 300, 1), (250, 325, 0), (255, 293, 0),
                                       (290, 370, 1), (343, 410, 0), (440, 397, 1), (480, 375, 0), (520, 405, 0),
                                       (560, 380, 0), (540, 350, 1), (640, 415, 0), (470, 450, 0), (245, 455, 0))):
        c = seat(u, v, 0.0027)
        if white:   # a pale ring lying flat
            M = Matrix.Translation(c) @ Matrix.Rotation(rnd.uniform(0, 3), 4, 'Z')
            p.lathe([(0.002, -0.0018), (0.0032, -0.0013), (0.0034, 0.0011), (0.002, 0.0018)], 'ScallionWhite', n=10, M=M,
                    close_ends=False)
            p.lathe([(0.002, 0.0018), (0.0018, 0.0), (0.002, -0.0018)], 'Scallion', n=10, M=M, close_ends=False)
        else:
            scallion_chunk(p, c, rnd.uniform(0, math.pi), r=0.0026, length=0.0088, tilt=rnd.uniform(-0.2, 0.2), lite=True)
    for (u, v) in ((265, 220), (240, 245), (475, 215), (530, 240), (150, 285), (205, 305), (360, 305), (445, 345),
                   (595, 325), (645, 362), (130, 395), (215, 420), (500, 420), (565, 455), (300, 470), (360, 492),
                   (420, 540), (100, 440), (690, 380), (330, 200)):   # red chilli flakes
        c = seat(u, v, 0.0006)
        p.blob(c, 0.0028, 'ChiliRed', squash=(1.0, 0.7, 0.3), segs=(6, 2), rot=rnd.uniform(0, 3))
    keep_within(p, n0, rin, bz, slope=0.0 if wok else 0.25)
    return p.finish('SM_D17' + ('_wok' if wok else ''), col, sharp=None)


TRACED_D20 = {spicy: os.path.join(os.path.dirname(__file__), f'traced_D20{"_spicy" if spicy else ""}.json')
              for spicy in (False, True)}


def suancai_yu(col, wok=False, spicy=False):
    """酸菜鱼 traced from its art (trace_d20.py writes traced_D20.json): slices of white fish, rippled, the grey skin
    along an edge, among dark leaves and pale pieces of pickled cabbage, all floating in a sour yellow broth (no
    chilli), in a deep, flared celadon bowl on a foot ring. The 辣味版 (spicy), from its own art (traced_D20_spicy):
    a deeper orange broth, fewer and bigger slices, rings of red chilli with their seeds, drops of red chilli oil all
    over. Every piece follows an outline traced in the art, a surface floating on the broth, its colours painted
    where the art has them. In the wok, all of it floats on the wok's pool of broth instead."""
    from .plates import traced_dish   # here: plates imports bowls
    p = Part()
    broth = 'SpicyBroth' if spicy else 'SourBroth'
    zf = 0.072 if spicy else 0.073   # the broth in the bowl, where the food floats (trace_d20.py's BOWL)
    if wok:
        bz = wok_pool(p, 0.078, 0.008, broth)
    elif spicy:
        bz, _ = round_bowl(p, rim_r=0.085, h=0.08, foot_r=0.035, foot_h=0.014, fill_z=zf, fill=broth,
                           n=48, light=True, flare=(30, 78, 0.4), t=0.007)
    else:
        bz, _ = round_bowl(p, rim_r=0.085, h=0.082, foot_r=0.036, foot_h=0.013, fill_z=zf, fill=broth,
                           n=48, light=True, flare=(30, 78, 0.4), t=0.007)
    traced_dish(p, TRACED_D20[spicy], ink='#6a5a30', lower=(lambda x, y: zf - bz) if wok else None)
    return p.finish('SM_D20' + ('_spicy' if spicy else '') + ('_wok' if wok else ''), col, sharp=None)


TRACED_D23 = os.path.join(os.path.dirname(__file__), 'traced_D23.json')
PAINT_D23 = os.path.join(os.path.dirname(__file__), 'traced_D23_paint.png')


def paint_map(path):
    """trace_d23's paint map as an array (rows from the top, as the art's), values 0-1."""
    img = bpy.data.images.load(path)
    img.colorspace_settings.name = 'Non-Color'
    w, h = img.size
    px = np.empty(w * h * 4, np.float32)
    img.pixels.foreach_get(px)
    bpy.data.images.remove(img)
    return px.reshape(h, w, 4)[::-1]


def jiuxie(col, wok=False):
    """酒蟹 traced from its art (trace_d23.py writes traced_D23.json): in pale golden wine in a flower-rimmed celadon
    bowl (ten lobes) on a foot ring, every piece follows an outline traced in the art and is raised as a soft mound
    with the art's shading in relief: the crab's top shell standing open at the back, the white meat and beads of
    roe inside it, five halves of crab with their white chambers and roe, and the claws and legs round them, lying
    low in the wine; each piece's colours (roe, olive shell, cream, the coral of the claws) painted where the art has
    them (traced_D23_paint.png), and the art's ink line round it; shreds of ginger over the top. In the wok the same,
    on the wok's pool."""
    data = json.load(open(TRACED_D23, encoding='utf-8'))
    p = Part()
    if wok:
        bz, rin = wok_pool(p, 0.08, 0.008, 'WineBroth'), 0.08
    else:
        bz, rin = round_bowl(p, rim_r=0.087, h=0.073, foot_r=0.042, foot_h=0.009, fill_z=0.065, fill='WineBroth',
                             n=50, light=True, flare=(26, 72, 0.42), t=0.006,
                             deform=scalloped(10, 0.05, 0.06, 0.088, phase=0.0))
    n0 = len(p.bm.verts)
    dz = bz - data['wine']
    cam = data['camera']
    se, ce = math.sin(math.radians(cam['el'])), math.cos(math.radians(cam['el']))
    view = Vector((0.0, -ce, se))                                     # towards the camera the art was drawn from
    colours = paint_map(PAINT_D23)
    H, W = colours.shape[:2]

    def field(channel):   # the paint map at the art pixel a point shows at, less a half
        def f(q):
            u = cam['u0'] + cam['k'] * q.x
            v = cam['v0'] - cam['k'] * (q.y * se + (q.z - dz) * ce)
            x0, y0 = min(max(int(u), 0), W - 2), min(max(int(v), 0), H - 2)
            tx, ty = min(max(u - x0, 0.0), 1.0), min(max(v - y0, 0.0), 1.0)
            c = colours[y0:y0 + 2, x0:x0 + 2, channel]
            return float((c[0, 0] * (1 - tx) + c[0, 1] * tx) * (1 - ty) + (c[1, 0] * (1 - tx) + c[1, 1] * tx) * ty) - 0.5
        return f
    f_food = len(p.bm.faces)
    def px(q):
        return Vector((cam['u0'] + cam['k'] * q.x, cam['v0'] - cam['k'] * (q.y * se + (q.z - dz) * ce)))

    def ink(rim):   # the art's ink line round a piece: dark within a few pixels of its outline in the art
        segs = [(a, b - a) for a, b in zip(rim, rim[1:] + rim[:1])]

        def f(q, n):
            c = px(q)
            d = min((c - (a + ab * min(max((c - a).dot(ab) / max(ab.length_squared, 1e-9), 0.0), 1.0))).length
                    for a, ab in segs)
            w = 0.9 * (1 - min(max((d - 3.0) / 6.0, 0.0), 1.0))
            return ('#4a2b18', w) if w > 0.02 else None
        return f
    for piece in data['pieces']:
        f0 = len(p.bm.faces)
        verts = [(x, y, z + dz) for x, y, z in piece['verts']]
        traced_surface(p, verts, piece['tris'], piece['mat'], lambda a, b, c: (b - a).cross(c - a).dot(view))
        for channel, mat in piece['paint']:
            paint(p, f0, mat, field(channel))
        p.tint(f0, ink([px(Vector(q)) for q in verts[:piece['rim']]]))
    for shred in data['ginger']:
        round_tube(p, [(x, y, z + dz) for x, y, z in shred['pts']], data['ginger_r'], 'GingerFlesh', sides=4)
    keep_within(p, n0, rin, bz, slope=0.0 if wok else 0.25)
    if wok:   # nothing below the wok's floor
        p.bm.verts.ensure_lookup_table()
        for v in p.bm.verts[n0:]:
            v.co.z = max(v.co.z, 0.0)
    return p.finish('SM_D23' + ('_wok' if wok else ''), col, sharp=None)


ITEMS = [('D02', caimian),
         ('D03', huntun),
         ('D02_wok', lambda c: caimian(c, True)),
         ('D03_wok', lambda c: huntun(c, True)),
         ('D04', guaji_luobo),
         ('D04_wok', lambda c: guaji_luobo(c, True)),
         ('D09', charou_mian),
         ('D09_wok', lambda c: charou_mian(c, True)),
         ('D11', lengtao),
         ('D11_wok', lambda c: lengtao(c, True)),
         ('D16', wensi_doufu),
         ('D16_wok', lambda c: wensi_doufu(c, True)),
         ('D17', mapo_doufu),
         ('D17_wok', lambda c: mapo_doufu(c, True)),
         ('D20', suancai_yu),
         ('D20_wok', lambda c: suancai_yu(c, True)),
         ('D20_spicy', lambda c: suancai_yu(c, spicy=True)),
         ('D20_spicy_wok', lambda c: suancai_yu(c, True, spicy=True)),
         ('D23', jiuxie),
         ('D23_wok', lambda c: jiuxie(c, True))]
