"""盘菜：胡饼、冷盘、鱼和烤鸭: D01, D05, D10, D12, D14, D18, D19, D22."""


import json
import math
import os
import random
import bmesh
from mathutils import Matrix, Vector
from .core import *  # noqa: F401,F403


PALETTE.update({
    'DuojiaoOil': ('#efa040', '#d07a26'),   # the orange chilli oil round 剁椒鱼头
    'BraisedFin': ('#bd7a40', '#94572a'),   # the fins and tail of 两熟紫苏鱼's carp, darker than its skin
    'BreadCrumb': ('#fbf1db', '#e6d4ae'),   # the torn white crumb of a 胡饼
    'SkinCurl': ('#f8e4d2', '#e3c3ac'),     # curls of pork skin seen in 水晶脍's aspic
    'GreenStem': ('#c3da8c', '#9cba62'),    # pale green stems among cooked greens
})


GLOSS.update({'BreadCrumb': 0.0, 'SkinCurl': 0.6, 'DuojiaoOil': 0.8, 'BraisedFin': 0.5})


PALETTE.update({
    'ZhaFlesh': ('#fbdcb4', '#eebd8c'),     # 玉板鲊's slices of salted fish: peach flesh
    'ZhaCut': ('#f2b07e', '#d98a5a'),       # the darker meat by the skin, on their cut ends
    'ZhaGinger': ('#fbd574', '#e5ae48'),    # its shreds of pickled ginger
    'ZhaBrine': ('#ddd193', '#c0b16c'),     # the olive-gold brine round the foot of its rice
    'DuojiaoDark': ('#c9261b', '#9c1712'),  # the darker pieces among 剁椒鱼头's chopped chilli
    'DuojiaoBase': ('#b8261a', '#8c1810'),  # the oily red between them, deep in the heap
})


GLOSS.update({'ZhaFlesh': 0.5, 'ZhaCut': 0.5, 'ZhaGinger': 0.3, 'ZhaBrine': 0.8, 'DuojiaoDark': 0.8,
              'DuojiaoBase': 0.8})
DETAIL.update({'DuojiaoDark': ('food_chopped', 14, '#f28a3a', 0.7, 0.5)})   # the heap: chopped bits, red and orange
# 煎鱼饭 as the art paints it: the fish's skin fried crisp (food_crisp, its colours painted on: fried_colour), the
# rice in grains, the greens' veins.
DETAIL.update({'FriedSkin': ('food_crisp', 22, '#8a4a1a', 0.45, 0.4), 'RiceGrain': ('food_grains', 16, '#d8ccb0', 0.3, 0.4),
               'DarkGreens': ('food_veins', 30, '#a8cf7a', 0.5, 0.25), 'SpinachGreen': ('food_veins', 30, '#9fc878', 0.45, 0.25)})
VTINT.update({'FriedSkin': 1.0})
# the darker fish skin scaled, and the perilla's purple leaves with their veins drawn (the perilla bunch).
DETAIL.update({'BraisedSkin': ('food_scales', 16, '#4a2810', 0.35, 0.25), 'BraisedFin': ('food_fiber', 22, '#5a3014', 0.6, 0.15),
               'PerillaPurple': ('food_veins', 26, '#b07098', 0.35, 0.25), 'PerillaDeep': ('food_veins', 26, '#9a5a88', 0.35, 0.25)})
VTINT.update(dict.fromkeys(('BraisedSkin', 'PerillaPurple', 'PerillaDeep'), 1.0))
VIVID.update({'PerillaPurple': 0.75, 'PerillaDeep': 0.75})


def deep_plate(p, r, h, foot=0.6, floor=0.012, sx=1.0, n=64, lip=0.005, wall=0.005, deform=None):
    """A 青瓷 plate with a deep curved wall and a thick round lip: r is the rim's radius into the picture, sx widens it,
    the foot ring is `foot` of r, the inside floor at `floor`. Smooth: 64 sides and a lip of several rings. Returns
    the profile of its inside, [(radius, height)] from the floor to the lip, for onto_deep_plate()."""
    rf = r * foot
    out = [(rf * 0.9, 0.0), (rf, 0.002)]
    for k in range(1, 7):   # the outer wall, curving up and out
        u = k / 7
        out.append((rf + (r - rf) * math.sin(u * math.pi / 2) ** 1.4, h * u ** 1.25))
    lipr = [(r + lip * 0.15, h + lip * 0.25), (r - lip * 0.2, h + lip * 0.95), (r - lip * 0.9, h + lip * 0.75),
            (r - lip * 1.25, h + lip * 0.05)]
    inner = []
    for k in range(6, -1, -1):   # the inner wall, the outer one moved in by `wall`, down to the floor
        u = k / 7
        rad = rf + (r - rf) * math.sin(u * math.pi / 2) ** 1.4 - wall
        inner.append((max(rad, rf * 0.9), max(floor, h * u ** 1.25 - lip * 0.2)))
    prof = [(0.0, 0.0)] + out + lipr + inner + [(0.0, floor)]
    p.lathe(prof, 'Celadon', n=n, close_ends=False, M=Matrix.Diagonal((sx, 1.0, 1.0, 1.0)), deform=deform)
    return [q for q in reversed(inner)]


TRACED_D01 = os.path.join(os.path.dirname(__file__), 'traced_D01.json')
DISH01 = dict(A=0.092576, q=0.9506, yaw=-0.3934, h=0.0349, foot=0.689)   # fitted with the camera to the art's plate
# 胡饼 traced from its art: the crust cream, browned in patches (tinted: golden, orange, brown at the heart), the torn
# crumb pale and porous
PALETTE.update({'HubingCrust': ('#fbe3b2', '#e9c287'),   # 胡饼.png's crust where it is least browned
                'HubingCrumb': ('#fcf1d8', '#e9d3a6'),   # and its torn crumb
                'HubingChar': ('#b65c24', '#8e451a')})   # the dark heart of each browned patch
GLOSS.update({'HubingCrust': 0.1, 'HubingCrumb': 0.0, 'HubingChar': 0.1})
VIVID.update({'HubingCrust': 0.3, 'HubingCrumb': 0.2, 'HubingChar': 0.6})
VTINT.update({'HubingCrust': 1.0, 'HubingCrumb': 1.0})
DETAIL.update({'HubingCrust': ('food_crust', 10, '#e09a4c', 0.3, 0.3),   # toasted flecks and blisters
               'HubingCrumb': ('food_crumb', 16, '#d8b47a', 0.45, 0.4),     # its open pores
               'HubingChar': ('food_mottle', 30, '#d8843c', 0.5, 0.2)})     # and the brown, mottled


def hubing(col, wok=False):
    """胡饼 traced from its art (trace_d01.py writes traced_D01.json): three puffy flatbreads in a deep oval celadon
    plate, one at the back propped against the plate's wall, one on the left, and one in front lying over the left
    one's edge with a bite torn out of its near edge, showing the crumb; each follows its outline in the art, flat on
    top with a rounded rim, its browned patches tinted where the art paints them and the art's ink line round it. In
    the wok the breads alone, lowered by the plate's floor."""
    p = Part()
    if not wok:
        d = DISH01
        oval_dish(p, d['A'], d['q'], d['yaw'], d['h'], d['foot'], floor=0.012, n=48, rings=4)
    traced_dish(p, TRACED_D01, lower=(lambda x, y: 0.012) if wok else None, ink='#5a3418')
    if wok:
        for v in p.bm.verts:   # nothing below the wok's floor
            v.co.z = max(v.co.z, 0.0)
    return p.finish('SM_D01' + ('_wok' if wok else ''), col, sharp=None)


TRACED_D05 = os.path.join(os.path.dirname(__file__), 'traced_D05.json')
# 水晶脍 traced from its art: amber aspic, paler on top and deeper low down (tinted), the curls of pork skin in it
# painted pale, scallion and ginger shreds on top
PALETTE.update({'SjkJelly': ('#f8d898', '#e8b468'),        # 水晶脍.png's aspic, amber
                'SjkSkin': ('#fcf0dc', '#ecd4b6'),         # the curls of pork skin seen in it
                'SjkGinger': ('#fbe27e', '#e8c35a'),       # its shreds of ginger
                'SjkScallion': ('#6fa62c', '#4f8420'),     # its scallion
                'SjkScallionCut': ('#c8df8a', '#a3c264')})  # and the pale cut ends of the scallion
GLOSS.update({'SjkJelly': 0.6, 'SjkSkin': 0.4, 'SjkGinger': 0.2, 'SjkScallion': 0.4, 'SjkScallionCut': 0.3})
VIVID.update({'SjkJelly': 0.45, 'SjkSkin': 0.3, 'SjkGinger': 0.5, 'SjkScallion': 0.7, 'SjkScallionCut': 0.5})
VTINT.update({'SjkJelly': 1.0})
DETAIL.update({'SjkJelly': ('food_mottle', 14, '#e8a650', 0.3, 0.15),   # the aspic's watery depth
               'SjkSkin': ('food_pores', 26, '#e8c7a8', 0.3, 0.2)})


def shuijing_kuai(col, wok=False):
    """水晶脍 traced from its art (trace_d05.py writes traced_D05.json): five cubes of amber pork-skin aspic in a deep
    celadon plate with a softly scalloped rim, one at the back, two in the middle, two in front; each a box with well
    rounded edges fitted to its outline in the art and covering it exactly, the curls of skin painted where the art
    has them, the aspic's colour tinted from pale on top to deep amber low down, the art's ink line round each; the
    scallion and ginger shreds on top traced each where the art has it. In the wok the cubes alone, lowered."""
    p = Part()
    if not wok:
        oval_dish(p, 0.105, 1.0, 0.0, 0.032, 0.72, floor=0.012, n=54, lobes=18, amount=0.012, rings=3)
    n1 = len(p.bm.verts)
    traced_dish(p, TRACED_D05, ink='#6a3a16')
    if wok:   # lowered as one by the plate's floor, closed underneath as on the plate; nothing below the wok's floor
        p.bm.verts.ensure_lookup_table()
        for v in p.bm.verts[n1:]:
            v.co.z = max(v.co.z - 0.012, 0.0)
    return p.finish('SM_D05' + ('_wok' if wok else ''), col, sharp=None)


def prism(p, outline, mat, thick, M=Matrix()):
    """A flat piece as a cage: the outline [(x, z)] extruded thick across y, placed by M. Built inside p.soft() it
    comes out a rounded lens with no sharp rim: fins, tails, leaves."""
    tmp = bmesh.new()
    a = [tmp.verts.new(M @ Vector((x, -thick / 2, z))) for x, z in outline]
    b = [tmp.verts.new(M @ Vector((x, thick / 2, z))) for x, z in outline]
    tmp.faces.new(a)
    tmp.faces.new(list(reversed(b)))
    for i in range(len(outline)):
        tmp.faces.new((a[i], a[(i + 1) % len(a)], b[(i + 1) % len(b)], b[i]))
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)


def fish_stations(stations, sx, sz, sw, sub=2):
    """The stations of fish_body() scaled (length sx, height sz, width sw) and refined `sub` times between each pair
    by a Catmull-Rom curve, with a small cap ring added at each end, so that a cage made of them is smooth."""
    st = [(x * sx, t * sz, b * sz, w * sw) for x, t, b, w in stations]
    out = []
    for i in range(len(st) - 1):
        p0, p1, p2, p3 = st[max(i - 1, 0)], st[i], st[i + 1], st[min(i + 2, len(st) - 1)]
        for j in range(sub):
            u = j / sub
            out.append(tuple(0.5 * ((2 * b) + (-a + c) * u + (2 * a - 5 * b + 4 * c - d) * u * u
                                    + (-a + 3 * b - 3 * c + d) * u ** 3) for a, b, c, d in zip(p0, p1, p2, p3)))
    out.append(st[-1])
    x0, t0, b0, w0 = out[0]
    x1, t1, b1, w1 = out[-1]
    m0, m1 = (t0 + b0) / 2, (t1 + b1) / 2
    return [(x0 - 0.006, m0 + (t0 - b0) * 0.12, m0 - (t0 - b0) * 0.12, w0 * 0.35)] + out + \
        [(x1 + 0.004, m1 + (t1 - b1) * 0.3, m1 - (t1 - b1) * 0.3, w1 * 0.5)]


def fish_cage(p, st, back, belly, n=12, split=2.0):
    """A fish body as one connected cage from stations [(x, top, bottom, half_width)], snout first, rings of n round
    each section and the ends closed; faces within `split` radians of the top are `back`, the rest `belly`. Build it
    inside p.soft(): being one piece it rounds off with no seam between the colours."""
    tmp = bmesh.new()
    rings = [[tmp.verts.new((x, -hw * math.sin(2 * math.pi * k / n), (t + b) / 2 + (t - b) / 2 * math.cos(2 * math.pi * k / n)))
              for k in range(n)] for x, t, b, hw in st]
    mats = []
    for ra, rb in zip(rings, rings[1:]):
        for k in range(n):
            tmp.faces.new((ra[k], ra[(k + 1) % n], rb[(k + 1) % n], rb[k]))
            mats.append(back if math.cos(2 * math.pi * (k + 0.5) / n) > math.cos(split) else belly)
    tmp.faces.new(list(reversed(rings[0])))
    tmp.faces.new(rings[-1])
    mats += [belly, back]
    piece_in_colours(p, tmp, mats)


def on_body(st, x, a, lift=0.0):
    """Point on a fish_stations body at x, `a` radians round the section from the top towards the viewer (-y), lifted
    `lift` off it, and the surface's normal there."""
    for (x0, t0, b0, w0), (x1, t1, b1, w1) in zip(st, st[1:]):
        if x0 <= x <= x1:
            f = (x - x0) / (x1 - x0)
            t, b, hw = t0 + (t1 - t0) * f, b0 + (b1 - b0) * f, w0 + (w1 - w0) * f
            break
    else:
        x0, t, b, hw = st[-1]
    h = (t - b) / 2
    nrm = Vector((0.0, -math.sin(a) / hw, math.cos(a) / h)).normalized()
    return Vector((x, -hw * math.sin(a), (t + b) / 2 + h * math.cos(a))) + nrm * lift, nrm


def fried_fish(p, M, length=0.17, height=0.7, width=0.75, skin='FriedSkin', belly='FriedBelly', fins='FriedFin',
               cut='FriedCut', scores=5, scallion=7, seed=0):
    """A whole fried fish, smooth and rounded, built upright along x (snout first, its left flank towards -y) and
    placed by M: golden body paler at the belly, rounded fins and a fanned tail, the eye, lips and gill line, slanting
    score marks open on the flank, scallion bits over it. Returns the body's stations (in its own frame)."""
    rnd = random.Random(seed)
    k = length / 0.223
    st = fish_stations([(x + 0.125, t, b, w) for x, t, b, w in CARP], k, k * height, k * width)
    n0, f0 = len(p.bm.verts), len(p.bm.faces)
    L = st[-1][0]
    tb = (st[-1][1] + st[-1][2]) / 2
    with p.soft():
        fish_cage(p, st, skin, skin)   # one skin: its colours painted across it (fried_colour)
        prism(p, [(L - 0.004, tb - 0.012 * k), (L + 0.03 * k, tb - 0.036 * k), (L + 0.052 * k, tb - 0.046 * k),
                  (L + 0.047 * k, tb - 0.018 * k), (L + 0.036 * k, tb), (L + 0.047 * k, tb + 0.02 * k),
                  (L + 0.054 * k, tb + 0.05 * k), (L + 0.032 * k, tb + 0.04 * k), (L - 0.004, tb + 0.012 * k)],
              fins, 0.004)                                                                       # the tail, fanned
        top = [(x, on_body(st, x, 0.0)[0].z) for x in (0.07 * k, 0.1 * k, 0.13 * k, 0.16 * k, 0.185 * k)]
        prism(p, [(top[0][0] - 0.004, top[0][1] - 0.004)] + [(x, z + 0.018 * k * (0.6 + 0.4 * math.sin(j * 1.3)))
                                                            for j, (x, z) in enumerate(top)]
              + [(top[-1][0] + 0.006, top[-1][1] - 0.004)], fins, 0.0035)                       # dorsal
        for (x, a, ln, tilt) in ((0.055 * k, 1.6, 0.055 * k, -0.5), (0.1 * k, 2.6, 0.042 * k, -1.1),
                                 (0.155 * k, 2.6, 0.038 * k, -1.2)):                          # pectoral, pelvic, anal
            c, nrm = on_body(st, x, a, 0.002)
            prism(p, [(0.0, 0.005), (ln * 0.55, 0.008), (ln, -0.004), (ln * 0.85, -0.016), (ln * 0.3, -0.011), (0.0, -0.005)],
                  fins, 0.0035, M=Matrix.Translation(c) @ Matrix.Rotation(tilt, 4, 'X') @ Matrix.Rotation(-0.35, 4, 'Y'))
        c, nrm = on_body(st, 0.004, 1.3, 0.001)
        p.blob(c + Vector((-0.002, 0.0, -0.002)), 0.0065 * k / 0.75, 'FishBelly', squash=(0.9, 1.0, 0.7), segs=(8, 4))  # lips
        for j in range(scores):   # score marks, slanting down to the front
            x = (0.075 + 0.026 * j) * k
            c, nrm = on_body(st, x, 0.75, 0.0008)
            R = nrm.to_track_quat('Z', 'Y').to_matrix() @ Matrix.Rotation(-0.9, 3, 'Z')
            p.blob(c, 1.0, cut, squash=(0.0045, 0.022 * k / 0.75, 0.0025), segs=(4, 3), deform=lambda v, R=R: R @ v)
    ce, ne = on_body(st, 0.03 * k, 0.75, 0.0)
    R = ne.to_track_quat('Z', 'Y').to_matrix()
    e = 0.0072 * k / 0.75
    p.blob(ce, 1.0, 'FishIris', segs=(12, 6), deform=lambda v: R @ Vector((v.x * e, v.y * e, v.z * 0.004)))
    p.blob(ce + ne * 0.0025, 1.0, 'FishEye', segs=(10, 5),
           deform=lambda v: R @ Vector((v.x * e * 0.56, v.y * e * 0.56, v.z * 0.0025)))   # the eye
    gill = [on_body(st, (0.05 + 0.012 * math.sin(j / 5 * math.pi)) * k, 0.2 + 0.36 * j, 0.0008)[0] for j in range(6)]
    p.tube(gill[:3], 0.0016, 'BraisedSkin', sides=6)
    p.tube(gill[2:], 0.0016, 'BraisedSkin', sides=6)                                              # gill cover
    with p.soft():
        for j in range(scallion):   # scallion bits on the flank
            c, nrm = on_body(st, rnd.uniform(0.05, 0.17) * k, rnd.uniform(0.3, 1.1), 0.002)
            u = nrm.orthogonal().normalized() * 0.0035
            p.tube([c - u, c + u], 0.0038, 'Scallion', sides=4)
    p.tint(f0, fried_colour(st), mats=(skin,))
    moved(p, n0, M)
    return st


def fried_colour(st):
    """A pan-fried fish's skin painted as 煎鱼饭.png has it, for Part.tint: browned deep along the back, golden
    down the flank, pale gold at the belly, and darker crisp spots scattered over it; st its body's stations."""
    from .meat_fish import dab, mix, ramp
    BACK, FLANK, BELLY, SPOT = '#9a5a24', '#d8973e', '#f4cf8e', '#7a4418'

    def field(q, n):
        for (x0, t0, b0, w0), (x1, t1, b1, w1) in zip(st, st[1:]):
            if x0 <= q.x <= x1:
                f = (q.x - x0) / max(x1 - x0, 1e-9)
                t, b = t0 + (t1 - t0) * f, b0 + (b1 - b0) * f
                break
        else:
            t, b = (st[0][1], st[0][2]) if q.x < st[0][0] else (st[-1][1], st[-1][2])
        h = (q.z - b) / max(t - b, 1e-6) + 0.1 * (dab(q, 0.006) - 0.5)   # 0 at the belly, 1 along the back
        col = mix(BELLY, FLANK, ramp(0.15, 0.5, h))
        col = mix(col, BACK, ramp(0.62, 0.92, h))
        spot = ramp(0.7, 0.82, dab(q, 0.0018, 4.0))
        if spot > 0.05:
            col = mix(col, SPOT, 0.55 * spot)
        return col, 0.85
    return field


def rice_dome(p, at, R, H, z, seed=0, scallion=8):
    """A dome of steamed rice R across and H high at `at`, its outline bumpy with grains, scallion bits on top."""
    rnd = random.Random(seed)
    prof = [(R, z), (R * 0.99, z + H * 0.22), (R * 0.93, z + H * 0.48), (R * 0.8, z + H * 0.72), (R * 0.58, z + H * 0.9),
            (R * 0.3, z + H * 0.985), (0.0, z + H)]

    def grains(q):   # small bumps of grains, different at every vertex
        h = math.sin(math.atan2(q.y, q.x) * 977.0 + q.z * 5431.0) * 43758.5453
        b = (h - math.floor(h)) * 2 - 1
        k = 1 + 0.012 * b * min(1.0, (q.z - z) / (H * 0.3))
        return Vector((q.x * k, q.y * k, q.z + 0.0008 * b))
    p.lathe(prof, 'RiceGrain', n=40, M=Matrix.Translation((*at, 0.0)), deform=grains, close_ends=False)
    with p.soft():
        for j in range(scallion):
            d, a = R * 0.75 * math.sqrt((j + 0.5) / scallion), j * 2.4 + rnd.uniform(-0.3, 0.3)
            hz = z + H * math.sqrt(max(0.0, 1 - (d / R) ** 2)) - 0.001
            q = Vector((at[0] + d * math.cos(a), at[1] + d * math.sin(a), hz))
            u = Vector((math.cos(a + 1.3), math.sin(a + 1.3), 0.0)) * 0.004
            p.tube([q - u, q + u], 0.0042, 'Scallion', sides=4)


def greens_heap(p, at, r, z, hz, seed=0, garlic=6):
    """A heap of cooked leafy greens: a dark mound with wilted rounded leaves draped over it from the top, pointing out
    and down along its slope, a few pale green stems and bits of garlic on top."""
    rnd = random.Random(seed)
    height = heap(p, at, r * 0.85, z, hz, 'DarkGreens', n=24)
    slope = math.atan2(hz, r * 0.85)
    with p.soft():
        for j in range(11):   # two rings of leaves: the top one long, the lower one short
            ring = j // 7
            a = (j % 7) * 2 * math.pi / 7 + ring * 0.45 + rnd.uniform(-0.25, 0.25)
            d0 = r * (rnd.uniform(0.05, 0.25) if ring == 0 else rnd.uniform(0.45, 0.55))
            base = Vector((at[0] + d0 * math.cos(a), at[1] + d0 * math.sin(a), height(d0) + 0.003))
            ln = r * (rnd.uniform(0.75, 0.9) if ring == 0 else rnd.uniform(0.45, 0.55))
            leaf(p, base, ln, ln * 0.62, ('SpinachGreen', 'DarkGreens')[j % 2], yaw=a, pitch=-slope * 1.15,
                 fold=0.15, curl=0.2, widest=0.55, rings=4, thick=0.005)
        for j in range(2):   # pale stems
            a = rnd.uniform(0, 6.3)
            c = Vector((at[0] + r * 0.15 * math.cos(a), at[1] + r * 0.15 * math.sin(a), height(r * 0.15) + 0.005))
            u = Vector((math.cos(a), math.sin(a), -math.tan(slope))) * r * 0.55
            p.tube([c, c + u * 0.5, c + u], 0.0045, 'GreenStem', sides=4)
        for j in range(garlic):
            d, a = r * 0.55 * math.sqrt((j + 0.5) / garlic), j * 2.4 + 1.0
            p.box((at[0] + d * math.cos(a), at[1] + d * math.sin(a), height(d) + 0.008), (0.007, 0.006, 0.005),
                  'GarlicClove', rot=a)


def over_deep_rim(p, n0, inside, r, h, sx=1.0, lip=0.005, x0=0.06, clear=0.0015):
    """Bends what was added to p since it had n0 vertices up over the wall and rim of a deep_plate (r, h, sx, lip and
    its `inside` profile) beyond x = x0, as a fish's tail reaches up over the rim in the art: a lift growing smoothly
    from nothing at x0 to the far end, just enough that nothing lies under the plate's inside or its lip."""
    p.bm.verts.ensure_lookup_table()
    vs = p.bm.verts[n0:]
    x1 = max(v.co.x for v in vs)
    surf = inside + [(r - lip * 1.25, h + lip * 0.05), (r - lip * 0.9, h + lip * 0.75), (r + lip * 0.15, h + lip * 0.95)]

    def floor_at(v):   # the height of the plate's inside over v, or None where none is over it
        rad = math.hypot(v.co.x / sx, v.co.y)
        if rad < surf[0][0] or rad > surf[-1][0]:
            return None
        for (r0, z0), (r1, z1) in zip(surf, surf[1:]):
            if r0 <= rad <= r1 and r1 > r0:
                return z0 + (z1 - z0) * (rad - r0) / (r1 - r0)
        return None

    def w(x):
        t = max(0.0, min(1.0, (x - x0) / max(x1 - x0, 1e-6)))
        return t * t * (3 - 2 * t)
    need = 0.0
    for v in vs:
        z = floor_at(v)
        if z is not None and w(v.co.x) > 0.05:
            need = max(need, (z + clear - v.co.z) / w(v.co.x))
    for v in vs:
        v.co.z += need * w(v.co.x)


TRACED_D10 = os.path.join(os.path.dirname(__file__), 'traced_D10.json')
# 煎鱼饭 traced from its art: its greens, and every colour on it taking the tint (its browning, its ink lines)
PALETTE.update({'GreensMid': ('#6a9634', '#4c7224'),    # cooked greens, as 煎鱼饭.png paints them
                'GreensDeep': ('#24461a', '#173212'),   # the darkest leaves among them
                'EyeOlive': ('#8c8458', '#6a6440'),     # a fried fish's eye, grey-olive round its golden middle
                'FishInk': ('#5a3018', '#40200e'),      # the lines the art draws on a fish: its gill cover, its mouth
                'FinRay': ('#a0501c', '#7c3c12'),       # the darker rays of crisp fins
                'FriedFinOrange': ('#f0a035', '#d6721e'),   # 煎鱼饭's fins and tail, fried orange
                'PanFriedSkin': ('#e8963a', '#c47426'),     # and its golden-orange crust (as the art: lighter than
                                                            # FriedSkin, which the braised carp's flank keeps)
                'FriedGold': ('#f6bc5c', '#dc9a3c'),    # a pan-fried fish's golden flesh, open in its score cuts
                'FriedBack': ('#a8885a', '#806640')})   # and its grey-olive back and crown
GLOSS.update({'GreensMid': 0.5, 'GreensDeep': 0.4, 'EyeOlive': 0.8, 'FishInk': 0.3, 'FinRay': 0.1, 'FriedGold': 0.6,
              'FriedBack': 0.5, 'FriedFinOrange': 0.1, 'PanFriedSkin': 0.55})
VIVID.update({'FriedBack': 0.3, 'FriedCut': 0.4})
DETAIL.update({'GreensMid': ('food_veins', 30, '#b8d088', 0.4, 0.25)})
VTINT.update(dict.fromkeys(('FriedSkin', 'FriedCut', 'FriedFin', 'RiceGrain', 'GreensMid', 'BokStalk', 'FishIris',
                            'FishEye', 'GarlicClove', 'EyeOlive', 'GreensDeep', 'FishInk', 'FinRay', 'FriedGold',
                            'FriedBack', 'FriedFinOrange', 'PanFriedSkin'), 1.0))
# its skin as the art paints it: small scales under a crust of crisp grains, browned between them (food_fishskin)
DETAIL.update({'PanFriedSkin': ('food_fishskin', 20, '#7a3410', 0.7, 1.0)})


def traced_dish(p, path, skip=(), lower=None, ink='#4a2b18', lower_by=None):
    """The food of a dish traced from its art (trace_d10.py and trace_d18.py write `path` and its paint): each piece a
    surface in its material, its colours where the art has them, painted on face by face (the trace put vertices
    along their edges) or tinted in softly (Part.tint), and the art's ink line round it, then what lies on top,
    scallion and garlic.
    Pieces named in `skip` and what lies on them are left out; every vertex is lowered by lower(x, y), if given
    (onto the wok's floor), or by lower_by[name](x, y) for the pieces named there."""
    import numpy as np
    from .bowls import scallion_chunk
    data = json.load(open(path, encoding='utf-8'))
    colours = np.load(path.replace('.json', '_paint.npz'))['paint'].astype(np.float32) / 255
    cam, sc = data['camera'], data['paint_scale']
    se, ce = math.sin(math.radians(cam['el'])), math.cos(math.radians(cam['el']))
    H, W = colours.shape[:2]

    def px(q):   # the art pixel a point shows at
        return Vector((cam['u0'] + cam['k'] * q.x, cam['v0'] - cam['k'] * (q.y * se + q.z * ce)))

    def field(channel):   # the paint channel where the art shows a point, less a half
        def f(q):
            c = px(q) * sc
            x0, y0 = min(max(int(c.x), 0), W - 2), min(max(int(c.y), 0), H - 2)
            tx, ty = min(max(c.x - x0, 0.0), 1.0), min(max(c.y - y0, 0.0), 1.0)
            g = colours[y0:y0 + 2, x0:x0 + 2, channel]
            return float((g[0, 0] * (1 - tx) + g[0, 1] * tx) * (1 - ty)
                         + (g[1, 0] * (1 - tx) + g[1, 1] * tx) * ty) - 0.5
        return f

    def colour(rim, tints, reach):   # its soft colours, and the art's ink line round it, dark within a few pixels
        segs = [(a, b - a) for a, b in zip(rim, rim[1:] + rim[:1])]   # of its outline (reach: full to, gone by)
        fields = [(field(channel), hexc, w) for channel, hexc, w in tints]

        def f(q, n):
            best = None
            for fl, hexc, wmax in fields:
                w = wmax * min(max(fl(q) + 0.5, 0.0), 1.0)
                if w > 0.02 and (best is None or w > best[1]):
                    best = (hexc, w)
            c = px(q)
            d = min((c - (a + ab * min(max((c - a).dot(ab) / max(ab.length_squared, 1e-9), 0.0), 1.0))).length
                    for a, ab in segs)
            w = 0.9 * (1 - min(max((d - reach[0]) / reach[1], 0.0), 1.0)) if reach[1] > 0 else 0.0
            if w > 0.02 and (best is None or w >= best[1]):
                best = (ink, w)
            return best
        return f
    n0 = len(p.bm.verts)
    rigid = []   # the vertices of the standing pieces (fins, tails, heads): lowered whole, not squashed
    skirts = []  # the feet of the skirts of pieces closed underneath, in the wok carried on down to its floor
    own = []     # the pieces lowered by their own function
    for piece in data['pieces']:
        if piece['name'] in skip:
            continue
        f0 = len(p.bm.faces)
        if piece['kind'] in ('fin', 'tail', 'head'):
            rigid.append((len(p.bm.verts), len(p.bm.verts) + len(piece['verts'])))
        if lower_by and piece['name'] in lower_by:
            own.append((len(p.bm.verts), len(p.bm.verts) + len(piece['verts']), lower_by[piece['name']]))
        tris, front = piece['tris'], piece.get('closed')
        if lower and front and any(min(t) >= front for t in tris):   # in the wok, no floor under it: its skirt
            tris = [t for t in tris if min(t) < front]                 # goes on along the lines of sight instead
            skirts.append((len(p.bm.verts) + front, len(p.bm.verts) + front + piece['rim']))
        vs = [p.bm.verts.new(Vector(q)) for q in piece['verts']]
        mi = p._mi(piece['mat'])
        for a, b, c in tris:
            p.bm.faces.new((vs[a], vs[b], vs[c])).material_index = mi
        p.bm.faces.ensure_lookup_table()
        for channel, mat in piece['paint']:   # the mesh has its vertices along the colours' edges: no cutting
            f, mi_ = field(channel), p._mi(mat)
            for face in p.bm.faces[f0:]:
                if f(face.calc_center_median()) > 0:
                    face.material_index = mi_
        p.tint(f0, colour([px(Vector(q)) for q in piece['verts'][:piece['rim']]], piece.get('tint', []),
                          piece.get('ink', (3.0, 6.0))))
    for bit in data['bits']:
        if bit['on'] in skip:
            continue
        c, k0 = Vector(bit['c']), len(p.bm.verts)
        if bit['kind'] == 'scallion':
            scallion_chunk(p, c, bit['yaw'], r=bit['r'], length=bit['length'], lite=True, n=6)
        else:
            s = bit['r']
            p.box(c, (s, s * 0.85, s * 0.7), 'GarlicClove', r=s * 0.25, rot=bit['yaw'], seg=1)
        if lower_by and bit['on'] in lower_by:   # with what it lies on, as one, by as much as under its middle
            fn = lower_by[bit['on']]
            own.append((k0, len(p.bm.verts), lambda x, y, d=fn(c.x, c.y): d))
    if lower:
        p.bm.verts.ensure_lookup_table()
        whole = set()
        for a, b in rigid:   # by as much as under its middle, but never under the floor
            vs = p.bm.verts[a:b]
            mid = sum((v.co for v in vs), Vector()) / len(vs)
            dz = lower(mid.x, mid.y)
            dz += min(min(v.co.z for v in vs) - dz, 0.0)
            for v in vs:
                v.co.z -= dz
            whole.update(range(a, b))
        for a, b, fn in own:
            for v in p.bm.verts[a:b]:
                v.co.z -= fn(v.co.x, v.co.y)
            whole.update(range(a, b))
        for i, v in enumerate(p.bm.verts[n0:], n0):
            if i not in whole:
                v.co.z -= lower(v.co.x, v.co.y)
        for a, b in skirts:   # each foot slid away along its line of sight down to the floor
            for v in p.bm.verts[a:b]:
                t = max(v.co.z - 0.0005, 0.0) / se
                v.co.y += t * ce
                v.co.z -= t * se


def jianyu_fan(col, wok=False):
    """煎鱼饭 traced from its art (trace_d10.py writes traced_D10.json): a golden pan-fried fish scored across its flank
    lying diagonally in front, head to the left and tail up over the rim, a dome of rice with scallion behind it and a
    heap of greens with garlic on the left, in a deep celadon plate; every piece follows an outline traced in the art,
    the fish's body lying on its side rounded up to the eye, its fins and tail standing up, the rice and the greens
    rounded mounds, the colours painted where the art has them and the art's ink line round each. In the wok the
    fish and the greens, lowered onto the wok's floor."""
    p = Part()
    inside = deep_plate(Part() if wok else p, 0.115, 0.042, foot=0.7, floor=0.012, sx=0.913, n=40)

    def under(x, y):   # the plate's inside under (x, y)
        rad = math.hypot(x / 0.913, y)
        for (r0, z0), (r1, z1) in zip(inside, inside[1:]):
            if r0 <= rad <= r1 and r1 > r0:
                return z0 + (z1 - z0) * (rad - r0) / (r1 - r0)
        return inside[-1][1] if rad > inside[-1][0] else inside[0][1]
    # in the wok, the fish lowered by the plate's floor as one (the sides the art's view sees edge-on stay so) and
    # the greens, heaped up the plate's side, down onto the wok's floor
    traced_dish(p, TRACED_D10, skip=('rice',) if wok else (), lower=(lambda x, y: 0.012) if wok else None,
                lower_by={'greens': under} if wok else None)
    if wok:
        for v in p.bm.verts:   # nothing below the wok's floor
            v.co.z = max(v.co.z, 0.0)
    return p.finish('SM_D10' + ('_wok' if wok else ''), col, sharp=None)


S35, C35 = math.sin(ART_EL), math.cos(ART_EL)


TOWARD = Vector((0.0, -C35, S35))   # from the food towards the art's camera


class ArtView:
    """Where the art's pixels lie in the model: the art is an orthographic picture from in front, 35° up, so a world
    point (x, y, z) lands on the art at X = x0 + s·x, Y = y0 - s·(y·sin35 + z·cos35). s, x0, y0 are read off the
    art_match fit of the finished dish."""

    def __init__(self, s, x0, y0):
        self.s, self.x0, self.y0 = s, x0, y0

    def ray(self, X, Y):
        """The line of sight through the art pixel (X, Y): a point high above the food on it, and its direction."""
        x = (X - self.x0) / self.s
        u = (self.y0 - Y) / self.s            # y·sin35 + z·cos35
        z = 0.4
        return Vector((x, (u - z * C35) / S35, z)), -TOWARD

    def at(self, X, Y, z):
        """The point at height z that the art shows at pixel (X, Y)."""
        o, d = self.ray(X, Y)
        return o + d * ((o.z - z) / -d.z)

    def px(self, q):
        """The art pixel of the world point q."""
        return (self.x0 + self.s * q[0], self.y0 - self.s * (q[1] * S35 + q[2] * C35))

    def onto(self, bvh, X, Y, lift=0.0):
        """Where the line of sight through (X, Y) first meets the mesh in bvh, and the surface's normal there (turned
        towards the camera); None if it misses."""
        o, d = self.ray(X, Y)
        hit, nrm, _, _ = bvh.ray_cast(o, d)
        if hit is None:
            return None
        if nrm.dot(TOWARD) < 0:
            nrm = -nrm
        return hit + nrm * lift, nrm

    def on_plane(self, X, Y, c, nrm):
        """Where the line of sight through (X, Y) meets the plane through c with normal nrm."""
        o, d = self.ray(X, Y)
        t = (Vector(c) - o).dot(nrm) / d.dot(nrm)
        return o + d * t


def surface(p):
    """A BVH of everything in p so far, for laying pieces on it."""
    from mathutils.bvhtree import BVHTree
    p.bm.normal_update()
    return BVHTree.FromBMesh(p.bm)


def scallops(lobes, amount, q, r0, r1):
    """Deform for a dish lathed round z and then squeezed to q across: its rings' points are spread evenly along the
    rim's ellipse rather than by angle, and from radius r0 out to r1 the rim swells into `lobes` round lobes
    `amount` of the radius deep with soft notches between them, all the same length round the rim (as the art's
    scalloped fish dish has them)."""
    N = 720
    th = [2 * math.pi * k / N for k in range(N + 1)]
    ds = [math.hypot(math.sin(t), q * math.cos(t)) for t in th]
    s = [0.0]
    for k in range(N):
        s.append(s[-1] + (ds[k] + ds[k + 1]) / 2)
    s = [v / s[-1] for v in s]

    def theta_at(u):   # the angle on the ellipse a share u of the way round it
        u %= 1.0
        lo, hi = 0, N
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if s[mid] <= u:
                lo = mid
            else:
                hi = mid
        return th[lo] + (th[hi] - th[lo]) * (u - s[lo]) / max(s[hi] - s[lo], 1e-12)

    def deform(v):
        rho = math.hypot(v.x, v.y)
        if rho < 1e-9:
            return v
        u = math.atan2(v.y, v.x) / (2 * math.pi)
        t = theta_at(u)
        f = min(1.0, max(0.0, (rho - r0) / (r1 - r0)))
        k = 1 + amount * (math.sqrt(math.cos(math.pi * lobes * u) ** 2 + 0.01) - 0.62) * f
        return Vector((rho * k * math.cos(t), rho * k * math.sin(t), v.z))
    return deform


def oval_dish(p, A, q=1.0, yaw=0.0, h=0.02, foot=0.65, floor=0.008, n=64, lip=0.005, wall=0.005, lobes=0,
              amount=0.0, rings=4):
    """A 青瓷 dish as the art draws them: a foot ring `foot` of the rim's size, a wall curving up and out `h` high to
    a thick rounded lip, and inside a flat floor at `floor`. Its rim is an ellipse A along `yaw` (from +x toward +y)
    by q·A across, scalloped into `lobes` round lobes by `amount` of the radius (n a multiple of lobes); n sides keep
    the rim a smooth ellipse. Returns inside(x, y): the height of the dish's inside at (x, y)."""
    r, rf = A, A * foot

    def wall_at(u):
        return rf + (r - rf) * math.sin(u * math.pi / 2) ** 1.4, 0.003 + (h - 0.003) * u ** 1.25
    prof = [(0.0, 0.0), (rf, 0.003)] + [wall_at(k / rings) for k in range(1, rings + 1)]
    prof += [(r + lip * 0.2, h + lip * 0.45), (r - lip * 0.35, h + lip), (r - lip * 1.1, h + lip * 0.55)]
    inner = []
    for k in range(rings - 1, 0, -1):
        rad, z = wall_at(k / rings)
        inner.append((rad - wall, max(floor, z - lip * 0.3)))
    inner.append((rf - wall, floor))
    prof += inner + [(0.0, floor)]
    M = Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Diagonal((1.0, q, 1.0, 1.0))
    p.lathe(prof, 'Celadon', n=n, close_ends=False, M=M,
            deform=scallops(lobes, amount, q, r * 0.8, r) if lobes else None)
    ins = [(0.0, floor)] + list(reversed(inner)) + [(r - lip * 1.1, h + lip * 0.55)]
    c, s = math.cos(yaw), math.sin(yaw)

    def inside(x, y):
        rad = math.hypot(c * x + s * y, (-s * x + c * y) / q)
        for (r0, z0), (r1, z1) in zip(ins, ins[1:]):
            if rad <= r1:
                return z0 + (z1 - z0) * max(0.0, rad - r0) / (r1 - r0)
        return ins[-1][1]
    return inside


def dish_sauce(p, mat, inside, A, q=1.0, yaw=0.0, reach=0.8, n=48, seed=0, wobble=0.06, lift=0.0012,
               at=(0.0, 0.0), sx=1.0, sy=1.0):
    """A pool of sauce lying on the dish's inside: an ellipse `reach` of the rim's size (stretched sx, sy along and
    across the dish, its middle at `at` in the dish's frame), its edge wavy by `wobble`. 3n faces."""
    rnd = random.Random(seed)
    ph = [rnd.uniform(0, 6.3) for _ in range(3)]

    def edge(v):
        a = math.atan2(v.y, v.x)
        k = 1 + wobble * (0.5 * math.sin(3 * a + ph[0]) + 0.3 * math.sin(5 * a + ph[1]) + 0.2 * math.sin(9 * a + ph[2]))
        return Vector((v.x * k, v.y * k, v.z))
    M = Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Translation((*at, 0.0)) \
        @ Matrix.Diagonal((A * reach * sx, A * reach * q * sy, 1.0, 1.0))
    n0 = len(p.bm.verts)
    p.lathe([(1.0, 0.0), (0.8, 0.0), (0.45, 0.0), (0.0, 0.0)], mat, n=n, M=M, deform=edge, close_ends=False)
    p.bm.verts.ensure_lookup_table()
    for i, v in enumerate(p.bm.verts[n0:]):
        v.co.z = inside(v.co.x, v.co.y) + lift * (0.25 if i < n else 1.0)


def offset_outline(pts, d):
    """The closed anticlockwise outline pts [Vector (x, y)] moved in by d."""
    out = []
    m = len(pts)
    for i in range(m):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % m]
        e1, e2 = (b - a).normalized(), (c - b).normalized()
        n1, n2 = Vector((-e1.y, e1.x)), Vector((-e2.y, e2.x))
        bis = n1 + n2
        bis = bis.normalized() if bis.length > 1e-6 else n1
        out.append(b + bis * d / max(0.35, bis.dot(n1)))
    return out


def as_built(p, tmp, mats):
    """Copies tmp into p as it was built, face k in mats[k] (or all in one colour): for pieces whose faces are
    already wound outwards. Thin bent shells (draped leaves) can fool recalc_face_normals into turning them inside out."""
    vmap = {v: p.bm.verts.new(v.co) for v in tmp.verts}
    for k, f in enumerate(tmp.faces):
        p.bm.faces.new([vmap[v] for v in f.verts]).material_index = p._mi(mats if isinstance(mats, str) else mats[k])
    tmp.free()


def signed_area(pts):
    return sum(a.x * b.y - b.x * a.y for a, b in zip(pts, pts[1:] + pts[:1])) / 2


def round_corners(pts, rad, k=3, sharp=2.6):
    """The closed anticlockwise outline pts [Vector (x, y)] with every corner sharper than `sharp` radians rounded
    off by an arc of k points of radius up to rad (and small enough to fit the edges beside it)."""
    out = []
    m = len(pts)
    for i in range(m):
        a, b, c = pts[i - 1], pts[i], pts[(i + 1) % m]
        e1, e2 = a - b, c - b
        l1, l2 = e1.length, e2.length
        if l1 < 1e-7 or l2 < 1e-7:
            continue
        e1n, e2n = e1 / l1, e2 / l2
        ang = math.acos(max(-0.9999, min(0.9999, e1n.dot(e2n))))
        convex = (b - a).x * (c - b).y - (b - a).y * (c - b).x > 0
        if ang > sharp or not convex:
            out.append(b)
            continue
        r = min(rad, 0.4 * min(l1, l2) * math.tan(ang / 2))
        d = r / math.tan(ang / 2)
        cen = b + (e1n + e2n).normalized() * (r / math.sin(ang / 2))
        p1, p2 = b + e1n * d - cen, b + e2n * d - cen
        a1, a2 = math.atan2(p1.y, p1.x), math.atan2(p2.y, p2.x)
        da = (a2 - a1 + math.pi) % (2 * math.pi) - math.pi
        out += [cen + Vector((math.cos(a1 + da * j / (k - 1)), math.sin(a1 + da * j / (k - 1)))) * r for j in range(k)]
    return out


def rounded_slab(p, outline, t, mat, frame, corner=0.004, edge=None):
    """A flat piece (a slice of bamboo shoot) lying in the plane of `frame` (a 4x4 whose z is its normal): the outline
    [(u, v)] with its corners rounded by `corner`, t thick above the plane, the rim of its top rounded over by `edge`
    (t/2 by default): flat top, rounded edges, no corner anywhere. ~8 triangles per outline point."""
    pts = [Vector(q) for q in outline]
    if signed_area(pts) < 0:
        pts.reverse()
    pts = round_corners(pts, corner)
    perim = sum((a - b).length for a, b in zip(pts, pts[1:] + pts[:1]))
    e = min(t * 0.5 if edge is None else edge, 0.22 * 2 * signed_area(pts) / perim)   # never wider than the piece
    prof = [(0.0, 0.0), (0.0, t - e), (e * 0.29, t - e * 0.29), (e, t)]
    tmp = bmesh.new()
    rings = [[tmp.verts.new(frame @ Vector((q.x, q.y, z))) for q in offset_outline(pts, d)] for d, z in prof]
    m = len(pts)
    tmp.faces.new(list(reversed(rings[0])))
    for ra, rb in zip(rings, rings[1:]):
        for i in range(m):
            tmp.faces.new((ra[i], ra[(i + 1) % m], rb[(i + 1) % m], rb[i]))
    tmp.faces.new(rings[-1])
    as_built(p, tmp, mat)


def leaf_outline(length, width, widest=0.42, n=5, tip_r=None):
    """Outline [(x, y)] of an ovate leaf from its stalk end at x = 0 to its tip at x = length, `width` across at
    `widest` of its length, both ends blunt points rounded off; anticlockwise, 2n + 6 points."""
    a = math.log(0.5) / math.log(widest)
    us = [0.06 + 0.86 * (j + 0.5) / n for j in range(n)]

    def hw(u):
        return 0.5 * width * math.sin(math.pi * u ** a) ** 0.85
    right = [(u * length, -hw(u)) for u in us]
    left = [(u * length, hw(u)) for u in reversed(us)]
    rt = tip_r or 0.12 * width
    tip = [(length - rt * (1 - math.cos(t)), rt * 0.9 * math.sin(t)) for t in (-1.0, 0.0, 1.0)]
    rs = 0.16 * width
    stalk = [(rs * (1 + math.cos(t)), rs * 0.9 * math.sin(t)) for t in (2.2, math.pi, 4.08)]
    pts = right + tip + left + stalk
    return pts


def drape_fit(frame, pts, bvh, gap):
    """How far above the plane of `frame` a piece must lie at each (x, y) to rest `gap` above the surface in bvh: the
    surface's height under pts, looking down the frame's normal, fitted by a smooth quadratic so that the piece bends
    with the surface without crumpling over its small bumps."""
    import numpy as np
    nz = (frame.to_3x3() @ Vector((0.0, 0.0, 1.0))).normalized()
    rows, ds = [], []
    for q in pts:
        w = frame @ Vector((q.x, q.y, 0.0))
        hit = bvh.ray_cast(w + nz * 0.04, -nz)[0]
        if hit is not None:
            rows.append([1.0, q.x, q.y, q.x * q.x, q.x * q.y, q.y * q.y])
            ds.append((hit - w).dot(nz))
    if len(ds) < 6:
        return lambda x, y: gap
    a, b = np.array(rows), np.array(ds)
    c = np.linalg.lstsq(a, b, rcond=None)[0]
    xy = a[:, 1:3]
    grad = np.hypot(c[1] + 2 * c[3] * xy[:, 0] + c[4] * xy[:, 1], c[2] + c[4] * xy[:, 0] + 2 * c[5] * xy[:, 1]).max()
    if grad > 0.8:   # no steeper than this, or its thin rim would fold over
        c[1:] *= 0.8 / grad
        c[0] = float(np.mean(b - a[:, 1:] @ c[1:]))
    over = min(0.006, max(0.0, float(np.percentile(b - a @ c, 85))))   # up over the bumps it would cut through
    return lambda x, y: float(c[0] + c[1] * x + c[2] * y + c[3] * x * x + c[4] * x * y + c[5] * y * y) + over + gap


def flat_leaf(p, frame, outline, mats, t=0.0022, margin=0.13, fold=0.0, curl=0.0, bvh=None, gap=0.0012, edge=None):
    """A thin leaf blade lying in the plane of `frame` with the outline [(x, y)] (x along its midrib), its edge rounded,
    its face in mats[0] inside a margin in mats[1] (`margin` of the way in: perilla is purple edged with green); V-
    folded up by `fold` along its midrib and curled down by `curl` towards its tip; given bvh, draped over that
    surface `gap` above it. Given `edge` (a hex colour), the margin is not cut in: the whole blade is mats[0], shading
    softly into `edge` towards its rim (Part.tint), as a perilla leaf goes from purple to green. ~6 triangles per
    outline point."""
    pts = [Vector(q) for q in outline]
    if signed_area(pts) < 0:
        pts.reverse()
    xs = [q.x for q in pts]
    x0, x1 = min(xs), max(xs)
    cx = (x0 + x1) / 2
    cy = sum(q.y for q in pts) / len(pts)
    inner = [Vector((cx + (q.x - cx) * (1 - margin), cy + (q.y - cy) * (1 - margin * 1.6))) for q in pts]
    e = t * 0.5
    edge_in = offset_outline(pts, e * 0.8)
    nz = frame.to_3x3() @ Vector((0.0, 0.0, 1.0))
    nz.normalize()
    lift = drape_fit(frame, [q for q in pts] + [Vector((cx, cy))], bvh, gap) if bvh is not None else (lambda x, y: 0.0)
    tmp = bmesh.new()

    def put(q, z):
        u = (q.x - x0) / max(x1 - x0, 1e-6)
        zz = z + fold * abs(q.y - cy) - curl * (x1 - x0) * max(0.0, u - 0.3) ** 2
        return tmp.verts.new(frame @ Vector((q.x, q.y, zz + lift(q.x, q.y))))
    centre = put(Vector((cx, cy)), t)
    rows = [[put(q, t) for q in inner], [put(q, t) for q in edge_in], [put(q, e) for q in pts]]
    m = len(pts)
    fm = []
    for i in range(m):
        tmp.faces.new((centre, rows[0][i], rows[0][(i + 1) % m]))
        fm.append(mats[0])
    rim = mats[0] if edge else mats[1]
    for j in (0, 1):
        for i in range(m):
            tmp.faces.new((rows[j][i], rows[j + 1][i], rows[j + 1][(i + 1) % m], rows[j][(i + 1) % m]))
            fm.append(rim)
    tmp.faces.new(list(reversed(rows[2])))
    fm.append(rim)
    f0 = len(p.bm.faces)
    as_built(p, tmp, fm)
    if edge:
        Fi = frame.inverted()
        ax = max(max(abs(q.x - cx) for q in pts), 1e-6)
        ay = max(max(abs(q.y - cy) for q in pts), 1e-6)

        def field(q, n):
            lq = Fi @ q
            rho = math.hypot((lq.x - cx) / ax, (lq.y - cy) / ay)
            w = 0.9 * min(max((rho - 0.45) / 0.5, 0.0), 1.0)
            return (edge, w) if w > 0.02 else None
        p.tint(f0, field)


def tangent_frame(c, nrm, up=Vector((0.0, 0.0, 1.0))):
    """A 4x4 frame at c whose z is nrm."""
    z = Vector(nrm).normalized()
    x = up.cross(z) if abs(up.dot(z)) < 0.99 else Vector((1.0, 0.0, 0.0)).cross(z)
    x.normalize()
    return Matrix.Translation(c) @ Matrix((x, z.cross(x), z)).transposed().to_4x4()


def laid(view, bvh, art_pts, centre, lift=0.0, normal=None, origin=None):
    """Carries an outline drawn in the art's pixels onto the surface in bvh: the line of sight through `centre` finds
    the spot, and the outline is laid on the surface's tangent plane there (or the plane with `normal`). Returns the
    frame (z the normal, origin on the surface + lift) and the outline in its (x, y)."""
    hit = view.onto(bvh, *centre)
    if hit is None:   # nothing under it (a wok, where the dish was): it lies on the level 0.003
        hit = view.at(*centre, 0.003), Vector((0.0, 0.0, 1.0))
    c, nrm = hit
    if origin is not None:
        c = Vector(origin)
    if normal is not None:
        nrm = Vector(normal).normalized()
    elif nrm.z < 0.45:   # on the steep side of something: lie tipped no further than this
        nrm = (nrm + Vector((0.0, 0.0, 0.45 - nrm.z)) * 1.6).normalized()
    F = tangent_frame(c + nrm * lift, nrm)
    Fi = F.inverted()
    loc = []
    for X, Y in art_pts:
        q = Fi @ view.on_plane(X, Y, c + nrm * lift, nrm)
        loc.append((q.x, q.y))
    return F, loc


def tube_on(p, pts, radius, mat, ref, sides=6):
    """A round tube along pts whose rings are set square to `ref` (roughly the normal of the surface it lies on), so
    that it may turn any way along that surface; its ends taper."""
    tmp = bmesh.new()
    rings = []
    m = len(pts)
    for i, q in enumerate(pts):
        q = Vector(q)
        tg = (Vector(pts[min(i + 1, m - 1)]) - Vector(pts[max(i - 1, 0)])).normalized()
        a = Vector(ref).cross(tg).normalized()
        b = tg.cross(a)
        rr = radius * (0.55 if i in (0, m - 1) else 1.0)
        rings.append([tmp.verts.new(q + rr * (math.cos(2 * math.pi * k / sides) * a + math.sin(2 * math.pi * k / sides) * b))
                      for k in range(sides)])
    for ra, rb in zip(rings, rings[1:]):
        for k in range(sides):
            tmp.faces.new((ra[k], ra[(k + 1) % sides], rb[(k + 1) % sides], rb[k]))
    tmp.faces.new(list(reversed(rings[0])))
    tmp.faces.new(rings[-1])
    as_built(p, tmp, mat)


# 两熟紫苏鱼's carp, its side as the art draws it: (x, back, belly, half width) from the snout, in metres
def in_poly(X, Y, poly):
    """Whether the pixel (X, Y) lies inside the polygon [(X, Y)]."""
    inside = False
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        if (y0 > Y) != (y1 > Y) and X < x0 + (Y - y0) * (x1 - x0) / (y1 - y0):
            inside = not inside
    return inside


def art_points(view, bvh, path, lift=0.0):
    """The points on the surface in bvh that the art shows at the pixels `path`, lifted `lift` off it, and their mean
    normal."""
    hits = [view.onto(bvh, X, Y, lift) for X, Y in path]
    hits = [h for h in hits if h is not None]
    nrm = sum((n for _, n in hits), Vector()).normalized()
    return [q for q, _ in hits], nrm


DISH12 = dict(A=0.16, q=0.70, yaw=math.radians(52), h=0.016, foot=0.68)
TRACED_D12 = os.path.join(os.path.dirname(__file__), 'traced_D12.json')
# 两熟紫苏鱼 traced from its art, every colour sampled from it: the braised fish's orange skin, blocked in with its
# brown flank, golden cheek, pale lips and lights and the dark of its crown and of the lines drawn on it; its eye;
# its fins and tail with their rays; the perilla leaves' purple, their green rims, deep veins and light; the bamboo
# slices' cream and the gold of the slits cut in them
PALETTE.update({'ZisuSkin': ('#c8843f', '#9a5e2c'), 'ZisuInk': ('#4a2610', '#341a08'),
                'ZisuBrown': ('#8f430d', '#6e3008'), 'ZisuGold': ('#f4b058', '#d8903c'),
                'ZisuPale': ('#fad8a8', '#e6b884'), 'ZisuIris': ('#a87a3e', '#80582a'),
                'ZisuOrbit': ('#e8c890', '#c8a066'), 'ZisuPupil': ('#3a2010', '#28160a'),
                'ZisuFin': ('#bc7a40', '#8e5a2c'), 'ZisuFinRay': ('#7a3c16', '#5a2a0e'),
                'ZisuLeaf': ('#7b3e50', '#5a2a38'), 'ZisuLeafDeep': ('#4a2030', '#341420'),
                'ZisuLeafGreen': ('#5f7028', '#46541c'), 'ZisuLeafLight': ('#9a5a6e', '#7a4458'),
                'ZisuBamboo': ('#f6d89a', '#e8b868'), 'ZisuGroove': ('#d9a050', '#b88038')})
GLOSS.update({'ZisuSkin': 0.65, 'ZisuInk': 0.3, 'ZisuBrown': 0.5, 'ZisuGold': 0.6, 'ZisuPale': 0.5, 'ZisuIris': 0.8,
              'ZisuOrbit': 0.5, 'ZisuPupil': 0.8, 'ZisuFin': 0.3, 'ZisuFinRay': 0.2, 'ZisuLeaf': 0.4,
              'ZisuLeafDeep': 0.3, 'ZisuLeafGreen': 0.4, 'ZisuLeafLight': 0.4, 'ZisuBamboo': 0.3, 'ZisuGroove': 0.2})
VIVID.update({'ZisuSkin': 0.6, 'ZisuFin': 0.55, 'ZisuInk': 0.5, 'ZisuFinRay': 0.5, 'ZisuLeaf': 0.75, 'ZisuLeafDeep': 0.75, 'ZisuLeafGreen': 0.75, 'ZisuLeafLight': 0.75, 'ZisuBamboo': 0.6,
              'ZisuGroove': 0.6})
DETAIL.update({'ZisuSkin': ('food_scales', 30, '#5a2a10', 0.6, 0.8),   # rows of scales under the braised glaze
               'ZisuFin': ('food_fiber', 22, '#6a3414', 0.45, 0.15),
               'ZisuLeaf': ('food_veins', 26, '#b07098', 0.35, 0.25),
               'ZisuLeafGreen': ('food_veins', 30, '#9fc878', 0.35, 0.25)})
VTINT.update(dict.fromkeys(('ZisuSkin', 'ZisuInk', 'ZisuBrown', 'ZisuGold', 'ZisuPale', 'ZisuIris', 'ZisuOrbit',
                            'ZisuPupil', 'ZisuFin', 'ZisuFinRay', 'ZisuLeaf', 'ZisuLeafDeep', 'ZisuLeafGreen',
                            'ZisuLeafLight', 'ZisuBamboo', 'ZisuGroove'), 1.0))


def liangshu_zisu_yu(col, wok=False):
    """两熟紫苏鱼 traced from its art (trace_d12.py writes traced_D12.json): a braised fish lying diagonally across a
    scalloped oval celadon dish in brown sauce, its gaping head at the front left and its tail up over the rim at the
    back right, purple perilla leaves and pale slices of bamboo shoot strewn over and round it. Every piece follows an
    outline traced in the art: the fish's body lying on its side rounded up to the eye, its tail and dorsal fin
    standing up, its pectoral fin on its flank, the leaves and slices lying on what is under them, the colours painted
    where the art has them and the art's ink line round each. In the wok the food, lowered onto the wok's floor as
    one, in a pool of the sauce."""
    p = Part()
    d = DISH12
    if not wok:
        inside = oval_dish(p, d['A'], d['q'], d['yaw'], d['h'], d['foot'], floor=0.008, n=80, lobes=20, amount=0.018,
                           rings=2)
        dish_sauce(p, 'Sauce', inside, d['A'], d['q'], d['yaw'], reach=0.74, n=40, seed=12, lift=0.0012)
    else:   # the sauce low enough for the leaves that lay on the dish's to show over it
        dish_sauce(p, 'Sauce', lambda x, y: 0.0, d['A'], d['q'], d['yaw'], reach=0.95, n=40, seed=12, lift=0.001)
    traced_dish(p, TRACED_D12, lower=(lambda x, y: 0.008) if wok else None, ink='#3a1c0c')
    if wok:
        for v in p.bm.verts:   # nothing below the wok's floor
            v.co.z = max(v.co.z, 0.0)
    return p.finish('SM_D12' + ('_wok' if wok else ''), col, sharp=None)


def zha_closed(p, tmp, mats):
    """Copies the closed piece tmp into p, face k in mats[k] (or all in one colour), its faces all wound one way and
    turned outwards by the sign of its volume: thin bent slabs fool recalc_face_normals into turning them inside out."""
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])   # consistent winding; outwards is settled below
    vol = 0.0
    for f in tmp.faces:
        vs = [v.co for v in f.verts]
        for i in range(1, len(vs) - 1):
            vol += vs[0].dot(vs[i].cross(vs[i + 1]))
    flip = vol < 0
    vmap = {v: p.bm.verts.new(v.co) for v in tmp.verts}
    for k, f in enumerate(tmp.faces):
        vs = [vmap[v] for v in f.verts]
        p.bm.faces.new(list(reversed(vs)) if flip else vs).material_index =             p._mi(mats if isinstance(mats, str) else mats[k])
    tmp.free()


def zha_path(pts, ss):
    """The points at the shares ss (0 = first point, 1 = last) of the way along the polyline pts [(X, Y)]."""
    pts = [Vector(q) for q in pts]
    seg = [(b - a).length for a, b in zip(pts, pts[1:])]
    tot = sum(seg)
    out = []
    for s in ss:
        d = tot * s
        for k, l in enumerate(seg):
            if d <= l or k == len(seg) - 1:
                out.append(pts[k] + (pts[k + 1] - pts[k]) * min(1.0, d / max(l, 1e-9)))
                break
            d -= l
    return out


def zha_depth(q):
    return -q.dot(TOWARD)   # how far a point lies from the art's camera, along its line of sight


def zha_on(view, bvh, X, Y):
    """Where the line of sight through the art pixel (X, Y) meets the surface in bvh, the normal there and the face it
    hits (None where it misses: then the level 0.003 under the pixel)."""
    o, d = view.ray(X, Y)
    hit, nrm, idx, _ = bvh.ray_cast(o, d)
    if hit is None:
        return view.at(X, Y, 0.003), Vector((0.0, 0.0, 1.0)), None
    if nrm.dot(TOWARD) < 0:
        nrm = -nrm
    return hit, nrm, idx


DISH14 = dict(A=0.0975, q=1.0, yaw=0.0, h=0.0315, foot=0.78)


def zha_without(p, n0):
    """Takes out of p what was added before it had n0 vertices (the dish the food was laid out on), and its colour."""
    p.bm.verts.ensure_lookup_table()
    gone = set(p.bm.verts[:n0])
    used = {f.material_index for f in p.bm.faces if not any(v in gone for v in f.verts)}
    bmesh.ops.delete(p.bm, geom=list(gone), context='VERTS')
    keep = [m for i, m in enumerate(p.mats) if i in used]
    remap = {i: keep.index(m) for i, m in enumerate(p.mats) if i in used}
    for f in p.bm.faces:
        f.material_index = remap[f.material_index]
    p.mats = keep


TRACED_D14 = os.path.join(os.path.dirname(__file__), 'traced_D14.json')
# 玉板鲊 traced from its art: the slices' pale pink-white flesh, greyer by the skin and lighter by the cut, wet; their
# skin one silver-grey band along the back, scaled, with a dark line along the edge; plump grains of fermented rice on
# a low pale bed of it; shreds of pickled ginger
PALETTE.update({'YbzRice': ('#fdf0dc', '#f2d8b4'),       # 玉板鲊.png's bed of fermented rice, pale
                'YbzGrain': ('#fff3e2', '#f8dcc0'),      # its grains, pale cream, a little peach in their shade
                'YbzFlesh': ('#fde4d0', '#f3c6a6'),      # the slices' flesh, pale pink-white
                'YbzSkin': ('#bcbab8', '#8e8d90'),       # their skin, silver-grey
                'YbzSkinEdge': ('#4c4e5a', '#3a3c48'),   # the dark line along its edge
                'YbzGinger': ('#f9d66c', '#e6b544')})    # the shreds of ginger
GLOSS.update({'YbzRice': 0.1, 'YbzGrain': 0.25, 'YbzFlesh': 0.55, 'YbzSkin': 0.65, 'YbzSkinEdge': 0.4,
              'YbzGinger': 0.2})
VIVID.update({'YbzRice': 0.3, 'YbzGrain': 0.2, 'YbzFlesh': 0.45, 'YbzSkin': 0.12, 'YbzSkinEdge': 0.25,
              'YbzGinger': 0.6})
VTINT.update(dict.fromkeys(('YbzFlesh',), 1.0))
OUTLINE.update({'YbzGrain': 0.4})   # a faint line round each grain, not a dark rim
DETAIL.update({'YbzRice': ('food_grains', 17, '#e4bf8e', 0.4, 0.5),       # more grains, as big as the others
               'YbzFlesh': ('food_fiber', 18, '#efc9b6', 0.18, 0.12),     # a few soft flake lines
               'YbzSkin': ('food_scales', 34, '#5c606e', 0.5, 0.15)})     # fine scales, on the skin only


def ybz_grain(p, c, axis, nrm, length, width, height):
    """A plump grain of fermented rice lying at c, its length along axis, nrm up from what it lies on: a small rounded
    capsule, 24 triangles."""
    z = Vector(nrm).normalized()
    x = Vector(axis) - z * Vector(axis).dot(z)
    x = x.normalized() if x.length > 1e-9 else z.orthogonal().normalized()
    y = z.cross(x)
    R = Matrix((x, y, z)).transposed()
    p.blob(Vector(c), 1.0, 'YbzGrain', segs=(6, 3),
           deform=lambda v: R @ Vector((v.x * length / 2, v.y * width / 2, v.z * height / 2)))


def yuban_zha(col, wok=False):
    """玉板鲊 traced from its art (trace_d14.py writes traced_D14.json): nine slices of salted fish fanned over a low bed
    of fermented rice in a round celadon dish, each its own clean rounded outline as the art draws it, a plump lens of
    pale pink-white flesh with one band of silver scaled skin along its back; grains of the rice on and between them,
    each where the art draws it; shreds of pickled ginger across them; a little brine round the foot of the rice. In
    the wok the food lowered onto the wok's floor, with its brine."""
    p = Part()
    d = DISH14
    inside = oval_dish(Part() if wok else p, d['A'], d['q'], d['yaw'], d['h'], d['foot'], floor=0.008, n=48, lip=0.005,
                       rings=3)
    n0 = len(p.bm.verts)
    dish_sauce(p, 'ZhaBrine', inside, d['A'], 1.0, 0.0, reach=0.66 if wok else 0.74, n=32, seed=14, lift=0.0012,
               wobble=0.04 if wok else 0.06)
    traced_dish(p, TRACED_D14, ink='#6a4a3a')
    for g in json.load(open(TRACED_D14, encoding='utf-8'))['grains']:
        ybz_grain(p, g[0:3], g[3:6], g[6:9], *g[9:12])
    if wok:   # the dish's inside laid flat onto the wok's floor, the food and its brine with it (all of it low)
        p.bm.verts.ensure_lookup_table()
        for v in p.bm.verts[n0:]:
            v.co.z = max(v.co.z - inside(v.co.x, v.co.y), 0.0)
    return p.finish('SM_D14' + ('_wok' if wok else ''), col, sharp=None)

def stem_loft(p, pts, half_w, half_d, mat, nrm=TOWARD, sides=6):
    """A tube for soft() along the points pts, its ends closed, each cross-section an ellipse half_w[i] across and
    half_d[i] through along nrm (the line of sight): the stem that carries 松鼠鳜鱼's tail up out of its body."""
    tmp = bmesh.new()
    rings = []
    for i, q in enumerate(pts):
        t = (Vector(pts[min(i + 1, len(pts) - 1)]) - Vector(pts[max(i - 1, 0)])).normalized()
        d = (nrm - t * nrm.dot(t)).normalized()
        w = t.cross(d)
        rings.append([tmp.verts.new(Vector(q) + w * half_w[i] * math.cos(2 * math.pi * k / sides)
                                    + d * half_d[i] * math.sin(2 * math.pi * k / sides)) for k in range(sides)])
    for ra, rb in zip(rings, rings[1:]):
        for k in range(sides):
            tmp.faces.new((ra[k], ra[(k + 1) % sides], rb[(k + 1) % sides], rb[k]))
    tmp.faces.new(list(reversed(rings[0])))
    tmp.faces.new(rings[-1])
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)


TRACED_D18 = os.path.join(os.path.dirname(__file__), 'traced_D18.json')
PALETTE.update({'EyeBrown': ('#8a5a34', '#6a4224')})   # 松鼠鳜鱼's eye round its dark pupil
GLOSS.update({'EyeBrown': 0.8})
VTINT.update(dict.fromkeys(('CrispPiece', 'CrispHead', 'GuiyuGlaze', 'GuiyuThroat', 'EyeBrown', 'FriedFin',
                            'FinRay'), 1.0))


def songshu_guiyu(col, wok=False):
    """松鼠鳜鱼 traced from its art (trace_d18.py writes traced_D18.json): a mandarin fish on a long oval celadon plate
    in a pool of red sweet-sour sauce, its body a pine cone of plump crisp pieces, each traced from the art and
    lumpy as it paints them, bristling out from the body under them (red with sauce where they part), its head reared
    up at the left with the jaws gaping and the eye, a fan of fins round its throat and the tail flicked up at the
    right, the sauce's glaze and the dark rays painted where the art has them, the art's ink line round each piece."""
    p = Part()
    fz = 0.008
    d = DISH18
    if not wok:
        inside = oval_dish(p, d['A'], d['q'], d['yaw'], d['h'], d['foot'], floor=fz, n=40, rings=2)
    else:
        def inside(x, y):
            return fz
    nf = len(p.bm.verts)   # the food from here on: in the wok it is lowered onto the wok's floor at the end
    dish_sauce(p, 'SweetSour', inside, d['A'], d['q'], d['yaw'], reach=0.86, n=40, seed=18, sy=0.7, wobble=0.05,
               lift=0.0012)
    zc = fz + 0.018   # the body under the pieces: the sauce deep in the shadows between them
    p.blob((0.029, 0.004, zc), 1.0, 'SauceShadow', squash=(0.079, 0.034, 0.032), segs=(12, 6),
           deform=lambda c: guiyu_core(c, 0.079, fz + 0.002 - zc))
    traced_dish(p, TRACED_D18, ink='#6a2410')
    if wok:
        p.bm.verts.ensure_lookup_table()
        for q in p.bm.verts[nf:]:
            q.co.z = max(q.co.z - fz, 0.0)   # down onto the floor of the wok
    return p.finish('SM_D18' + ('_wok' if wok else ''), col, sharp=None)


def dj_head(p, view, bvh, dorsal, ventral, mat_at, H=0.026, D=0.012, elev=48, gap=0.001,
            ss=(0.0, 0.07, 0.3, 0.55, 0.78, 0.93, 1.0)):
    """Half a big fish head for soft(), its skin side towards the art's camera as the art draws it: the outline runs
    along the pixels `dorsal` (the back of the head, from the nape to the top of the snout) and `ventral` (from the
    nape down the cut to the throat and on to the jaw), its side lies in a plane raised `elev` degrees towards the camera and bulges H out of it, the
    cut face D behind; it is slid along the line of sight to rest on bvh. mat_at(s, k) colours the strip k (0-4 over the
    skin side from the back of the head to the jaw, 5-7 behind) of the stretch s (0 nape .. 1 snout)."""
    B, L = zha_path(dorsal, ss), zha_path(ventral, ss)
    el = math.radians(elev)
    nrm = Vector((0.0, -math.cos(el), math.sin(el)))
    c0 = view.at(*((B[len(ss) // 2] + L[len(ss) // 2]) / 2), 0.04)
    PB = [view.on_plane(q.x, q.y, c0, nrm) for q in B]
    PL = [view.on_plane(q.x, q.y, c0, nrm) for q in L]
    e = 0.08

    ring = [(-e, 0.15), (0.12, 0.62), (0.36, 0.95), (0.6, 1.0), (0.82, 0.78), (1 + e, 0.22), (0.8, -1.0), (0.2, -1.0)]
    pts = []
    for i, s in enumerate(ss):
        w = (PL[i] - PB[i]).length   # thinner where it narrows (to the nape), fullest a little behind the middle
        hh, dd = min(H, 0.42 * w), min(D, 0.2 * w)
        pts.append([PB[i] + (PL[i] - PB[i]) * v + nrm * (h * (hh if h > 0 else dd)) for v, h in ring])
    slide = None   # along the line of sight, until it rests on what is under it
    for row in pts:
        for q in row[5:]:
            X, Y = view.px(q)
            hit = view.onto(bvh, X, Y)
            if hit is not None:
                d = zha_depth(q) - zha_depth(hit[0]) + gap
                slide = d if slide is None else max(slide, d)
    tmp = bmesh.new()
    rings = [[tmp.verts.new(q + TOWARD * (slide or 0.0)) for q in row] for row in pts]
    mats = []
    for i, (ra, rb) in enumerate(zip(rings, rings[1:])):
        sm = (ss[i] + ss[i + 1]) / 2
        for k in range(8):
            tmp.faces.new((ra[k], ra[(k + 1) % 8], rb[(k + 1) % 8], rb[k]))
            mats.append(mat_at(sm, k))
    tmp.faces.new(list(reversed(rings[0])))
    tmp.faces.new(rings[-1])
    zha_closed(p, tmp, mats + [mat_at(0.0, 0), mat_at(1.0, 4)])


def dj_decal(p, bvh, c, nrm, rx, ry, t, mat, lift=0.0004, segs=(14, 3)):
    """A thin flat patch (an eye, the dark skin round it) rx by ry across and t thick lying on the surface in bvh at c
    (normal nrm): its points are carried down onto the surface under them, so that it follows the curve of the head."""
    R = nrm.to_track_quat('Z', 'Y').to_matrix()
    n0 = len(p.bm.verts)
    p.blob(c, 1.0, mat, segs=segs, deform=lambda v: R @ Vector((v.x * rx, v.y * ry, v.z * t / 2)))
    p.bm.verts.ensure_lookup_table()
    for v in p.bm.verts[n0:]:
        h = (v.co - c).dot(nrm)
        base = v.co - nrm * h
        hit = bvh.ray_cast(base + nrm * 0.03, -nrm)[0]
        if hit is not None:
            v.co = hit + nrm * (lift + t / 2 + h)


def dj_eye(p, view, bvh, X, Y, r_iris, r_pupil, r_ring=0.0):
    """A fish's big eye where the art draws it: a gold iris lying on the head in a ring of dark skin r_ring across
    (none if 0), the dark pupil and a spark of light, all following the curve of the head."""
    c, nrm = view.onto(bvh, X, Y)
    if r_ring:
        dj_decal(p, bvh, c, nrm, r_ring, r_ring * 0.85, 0.0016, 'FishBack', lift=0.0003)
    dj_decal(p, bvh, c, nrm, r_iris, r_iris, 0.0018, 'FishIris', lift=0.0012, segs=(14, 3))
    dj_decal(p, bvh, c, nrm, r_pupil, r_pupil, 0.0014, 'FishEye', lift=0.0026, segs=(12, 3))
    R = nrm.to_track_quat('Z', 'Y').to_matrix()
    up, side = R @ Vector((0.0, 1.0, 0.0)), R @ Vector((1.0, 0.0, 0.0))
    dj_decal(p, bvh, c + (up * 0.35 - side * 0.3) * r_pupil, nrm, r_pupil * 0.3, r_pupil * 0.3, 0.0008, 'Salt',
             lift=0.0036, segs=(8, 2))


def dj_tube(p, view, bvh, path, radius, mat, lift=0.0, sides=6):
    """A rounded tube lying on the surface in bvh along the art pixels `path` (lips, the line of a mouth)."""
    pts, nrm = art_points(view, bvh, path, lift + radius * 0.5)
    tube_on(p, pts, radius, mat, nrm, sides=sides)


def dj_wavy(outline, n, amp, waves, seed=0):
    """The closed outline (pixels) drawn smooth through its points (Catmull-Rom), n points evenly along it, its edge
    rippled `amp` pixels in and out `waves` times round (the frilly margin of a wilted leaf)."""
    P = [Vector(q) for q in outline]
    m = len(P)
    dense = []
    for i in range(m):
        p0, p1, p2, p3 = P[i - 1], P[i], P[(i + 1) % m], P[(i + 2) % m]
        for j in range(12):
            u = j / 12
            dense.append(0.5 * (2 * p1 + (p2 - p0) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                                + (3 * p1 - p0 - 3 * p2 + p3) * u ** 3))
    seg = [(dense[(i + 1) % len(dense)] - dense[i]).length for i in range(len(dense))]
    tot = sum(seg)
    rnd = random.Random(seed)
    ph = rnd.uniform(0, 6.3)
    out, acc, k = [], 0.0, 0
    for j in range(n):
        d = tot * j / n
        while acc + seg[k] < d:
            acc += seg[k]
            k += 1
        a, b = dense[k], dense[(k + 1) % len(dense)]
        q = a + (b - a) * ((d - acc) / max(seg[k], 1e-9))
        tg = (b - a).normalized()
        out.append(q + Vector((-tg.y, tg.x)) * amp * math.sin(2 * math.pi * waves * j / n + ph))
    return [(q.x, q.y) for q in out]


def dj_leaf(p, view, bvh, outline, mats=('Greens', 'BokChoy'), lift=0.0015, t=0.0026, margin=0.16, fold=0.0, curl=0.0,
            n=16, seed=0):
    """A wilted leaf of bok choy whose outline the art draws at `outline` (pixels): drawn smooth with a frilly edge,
    laid on what is under it and draped over it, its face light green inside a darker margin."""
    outline = dj_wavy(outline, n, 3.5, n // 2 - 1, seed)
    cx = sum(x for x, _ in outline) / len(outline)
    cy = sum(y for _, y in outline) / len(outline)
    F, loc = laid(view, bvh, outline, (cx, cy), 0.0)
    flat_leaf(p, F, loc, mats, t=t, margin=margin, fold=fold, curl=curl, bvh=bvh, gap=lift)


VIEW22 = ArtView(4773.0, 627.0, 790.0)


DISH22 = dict(A=0.15, q=0.786, yaw=math.radians(54.2), h=0.0366, foot=0.814)


# the two halves of the head (pixels): the back of the head from the nape to the snout, and the throat to the jaw
HEAD22 = [([(160, 523), (209, 509), (260, 498), (330, 500), (420, 525), (510, 570), (600, 630), (680, 685), (740, 718),
            (790, 745), (802, 765)],
           [(162, 531), (172, 590), (182, 640), (192, 688), (226, 748), (256, 796), (290, 843), (330, 878), (378, 906),
            (426, 928), (480, 944), (554, 950), (651, 952), (743, 952), (795, 920)]),
          ([(777, 234), (811, 271), (851, 306), (891, 334), (926, 357), (960, 405), (989, 460), (1040, 517), (1086, 563),
            (1131, 609), (1160, 643), (1168, 662)],
           [(774, 242), (765, 330), (752, 430), (745, 520), (770, 600), (810, 660), (860, 705), (920, 735), (966, 751),
            (1040, 735), (1109, 711), (1143, 690), (1162, 674)])]


# leaves of bok choy under the heads: pixel outlines and their colours (face, margin)
DARK22, LIGHT22 = ('SpinachGreen', 'BokChoy'), ('Greens', 'SpinachGreen')


PALETTE.update({
    'GuiyuDark': ('#a0602f', '#7a4220'),    # the dark skin over 松鼠鳜鱼's head and the rays of its fins and tail
    'GuiyuMouth': ('#c4582a', '#983c18'),   # the inside of its gaping mouth
    'GuiyuGlaze': ('#f7862c', '#d6611a'),   # crisp pieces under a coat of sweet-sour sauce
})


GLOSS.update({'GuiyuDark': 0.5, 'GuiyuMouth': 0.6, 'GuiyuGlaze': 0.8})
# 松鼠鳜鱼 as the art paints it, not a toy: a crust of knobbly fried batter on every piece and over the head
# (food_crisp), the fins' rays (food_fiber), the colours painted across them (crisp_colour, head_colour).
DETAIL.update({'CrispPiece': ('food_crisp', 18, '#b04a10', 0.4, 0.6), 'CrispHead': ('food_crisp', 18, '#a8521a', 0.4, 0.5),
               'GuiyuGlaze': ('food_crisp', 18, '#a8340e', 0.45, 0.4), 'FriedFin': ('food_fiber', 22, '#8a4214', 0.45, 0.2)})
VTINT.update(dict.fromkeys(('CrispPiece', 'GuiyuGlaze', 'CrispHead'), 1.0))


PALETTE.update({'GuiyuThroat': ('#94351a', '#6e2410'),   # deep in 松鼠鳜鱼's gaping mouth, where the jaws part
               'SauceShadow': ('#a82e0e', '#7a1e08'),   # its sweet-sour sauce deep between the crisp pieces
               'GuiyuTail': ('#f39a3c', '#d27a30'),     # its tail, fried orange
               'GuiyuRay': ('#a85a28', '#844420'),      # and the brown rays of its tail and fins
               'HeadPale': ('#fadc9e', '#e6b47a'),      # its head as the art paints it: the pale of its jaws and throat,
               'HeadRed': ('#e2581a', '#b8400e'),       # the red sauce running down it
               'HeadBrown': ('#b04a18', '#86340e')})    # and its brown shade


# the head and the fins: no big white glints over them (fried batter, dry fins)
GLOSS.update({'GuiyuThroat': 0.6, 'SauceShadow': 0.2, 'CrispHead': 0.3, 'FriedFin': 0.1, 'GuiyuTail': 0.1,
              'GuiyuRay': 0.1, 'HeadPale': 0.2, 'HeadBrown': 0.3, 'HeadRed': 0.8})
DETAIL.update({'GuiyuTail': ('food_fiber', 22, '#8a4214', 0.45, 0.2), 'HeadPale': ('food_crisp', 18, '#c88a4a', 0.4, 0.5),
               'HeadBrown': ('food_crisp', 18, '#7a3010', 0.3, 0.4)})
VTINT.update(dict.fromkeys(('GuiyuTail', 'GuiyuRay', 'HeadPale', 'HeadRed', 'HeadBrown', 'GuiyuThroat'), 1.0))


PALETTE.update({'DuckKnob': ('#8e3c1e', '#66280f'),     # the dark knobbly end of the roast duck's drumstick
                'KaoyaMeat': ('#f4cdb6', '#dda48a')})   # the pink cut face of its slices


GLOSS.update({'DuckKnob': 0.6, 'KaoyaMeat': 0.4})


LEAVES22 = [([(100, 660), (120, 635), (160, 640), (195, 665), (210, 700), (215, 740), (205, 770), (175, 775), (140, 765),
              (110, 735), (95, 700)], DARK22),
            ([(105, 760), (140, 770), (190, 790), (240, 800), (290, 812), (330, 840), (345, 862), (300, 885), (250, 872),
              (200, 850), (160, 832), (125, 808), (105, 785)], LIGHT22),
            ([(320, 840), (370, 880), (420, 905), (470, 915), (510, 930), (510, 960), (470, 972), (420, 965), (370, 945),
              (320, 915), (280, 885), (285, 860)], DARK22),
            ([(510, 922), (590, 922), (665, 930), (724, 937), (769, 948), (747, 963), (665, 967), (590, 963),
              (524, 955)], DARK22),
            ([(924, 762), (980, 748), (1030, 746), (1066, 758), (1050, 778), (1000, 784), (950, 784)], LIGHT22),
            ([(799, 878), (806, 833), (828, 804), (880, 785), (939, 774), (999, 770), (1043, 774), (1058, 796),
              (1036, 819), (991, 841), (939, 859), (880, 878), (828, 893)], DARK22),
            ([(1140, 632), (1135, 590), (1140, 545), (1150, 505), (1165, 478), (1180, 500), (1182, 560), (1170, 610),
              (1155, 635)], LIGHT22),
            ([(940, 345), (970, 335), (1010, 350), (1050, 365), (1085, 385), (1080, 415), (1045, 420), (1000, 405),
              (960, 385), (942, 365)], LIGHT22),
            ([(150, 505), (165, 480), (195, 470), (230, 478), (240, 500), (215, 515), (180, 518)], DARK22)]


# the lips and the line of each mouth (pixels), their radius (pixels) and colour
MOUTHS22 = [([(560, 900), (612, 905), (665, 910), (712, 920), (742, 930)], 21, 'FishBelly'),
            ([(552, 840), (618, 843), (678, 851), (716, 866), (738, 884)], 15, 'FishBelly'),
            ([(552, 866), (622, 870), (669, 876), (707, 892), (731, 908)], 7, 'FishEye'),
            ([(1000, 704), (1060, 707), (1110, 698), (1146, 683)], 16, 'FishBelly'),
            ([(1036, 655), (1088, 651), (1130, 646), (1158, 652)], 12, 'FishBelly'),
            ([(1038, 678), (1080, 678), (1120, 673), (1154, 664)], 6, 'FishEye')]


def dj_skin(view):
    """The heads' colour across their pale skin as the art paints it, for Part.tint: dark grey-brown over the back
    of each head and down round the eye, dappled darker like scales, through a ragged edge into the pale cheek and
    jaw. Where a point lies between a head's back (its dorsal outline) and its jaw (the ventral one) is measured
    in the art's pixels."""
    from .meat_fish import dab, mix, ramp
    DARK, DEEP = '#524f4a', '#38352f'
    heads = []
    for dorsal, ventral in HEAD22:
        B, L = [Vector(q) for q in dorsal], [Vector(q) for q in ventral]
        heads.append((B, L, B + L[::-1]))

    def dist(q, line):
        best = 1e9
        for a, b in zip(line, line[1:]):
            ab = b - a
            t = min(max((q - a).dot(ab) / max(ab.length_squared, 1e-9), 0.0), 1.0)
            best = min(best, (q - (a + ab * t)).length)
        return best

    def field(q, n):
        X, Y = view.px(q)
        P = Vector((X, Y))
        B, L, poly = min(heads, key=lambda h: 0.0 if in_poly(X, Y, h[2]) else min(dist(P, h[0]), dist(P, h[1])))
        db, dl = dist(P, B), dist(P, L)
        t = db / max(db + dl, 1e-6) + 0.12 * (dab(q, 0.006) - 0.5)   # 0 along the back of the head, 1 at the jaw
        w = 0.92 * ramp(0.9, 0.62, t)
        return (mix(DARK, DEEP, ramp(0.45, 0.75, dab(q, 0.005, 3.0))), w) if w > 0.02 else None
    return field


def dj_heap(p, view, bvh, outline, centre, thick=(0.002, 0.012, 0.022), rings=(0.0, 0.4), mat='ChiliRed',
            grow=5.0):
    """A heap for soft() lying over whatever bvh holds, its outline where the art draws it (pixels, pushed out `grow`
    for what rounding takes off): each ring of it (rings: the share of the way in towards the art pixel `centre`) lies
    thick[i] in front of what is under it along the art's lines of sight, bridging the gaps behind what is under it;
    its top over `centre` is thick[-1] in front."""
    pts = [Vector(q) for q in outline]
    if signed_area(pts) < 0:
        pts.reverse()
    pts = offset_outline(pts, -grow)
    C = Vector(centre)

    def depth_at(q):
        o, d = view.ray(q.x, q.y)
        hit = bvh.ray_cast(o, d)[0]
        return zha_depth(hit if hit is not None else view.at(q.x, q.y, 0.01)), o, d
    rows = []
    for a, t in zip(rings, thick):
        row = []
        for q in pts:
            px = q + (C - q) * a
            dep, o, d = depth_at(px)
            row.append([dep - t, o, d])
        if a > 0:   # no deeper than the points beside it: it spans the dips and gaps under it
            for _ in range(3):
                m = len(row)
                for i in range(m):
                    row[i][0] = min(row[i][0], (row[i - 1][0] + row[(i + 1) % m][0]) / 2 + 0.003)
        rows.append(row)
    for ra, rb in zip(rows, rows[1:]):   # inner rings no deeper than the ring outside them
        for qa, qb in zip(ra, rb):
            qb[0] = min(qb[0], qa[0] + 0.002)
    tmp = bmesh.new()
    vs = [[tmp.verts.new(o + d * (dep - zha_depth(o))) for dep, o, d in row] for row in rows]
    dep, o, d = depth_at(C)
    top = tmp.verts.new(o + d * (min(dep - thick[-1], min(q[0] for q in rows[-1]) - 0.003) - zha_depth(o)))
    bot = [tmp.verts.new(q.co - TOWARD * 0.004) for q in vs[0]]
    m = len(pts)
    faces = [tmp.faces.new(list(reversed(bot)))]
    for ra, rb in zip([bot] + vs, vs):
        faces += [tmp.faces.new((ra[i], ra[(i + 1) % m], rb[(i + 1) % m], rb[i])) for i in range(m)]
    faces += [tmp.faces.new((vs[-1][i], vs[-1][(i + 1) % m], top)) for i in range(m)]
    zha_closed(p, tmp, mat)


def dj_cube(p, c, nrm, size, mat, yaw, tilt=0.25, sunk=False):
    """A diced piece of chilli resting on a surface at c (normal nrm), turned yaw about it and tipped a little: a
    cube with its edges and corners bevelled round, its faces flat (44 triangles). `sunk`: half sunk into a heap, whose
    inside hides its bottom, which is left off (30 triangles)."""
    z = nrm.normalized()
    x = z.orthogonal().normalized()
    y = z.cross(x)
    R = (Matrix((x, y, z)).transposed() @ Matrix.Rotation(yaw, 3, 'Z') @ Matrix.Rotation(tilt, 3, 'X')).to_4x4()
    if not sunk:
        p.box((0.0, 0.0, 0.0), (size, size, size * 0.85), mat, r=size * 0.15, seg=1,
              M=Matrix.Translation(c + z * size * 0.36) @ R)
        return
    tmp = bmesh.new()
    bmesh.ops.create_cube(tmp, size=1.0)
    for v in tmp.verts:
        v.co = Vector((v.co.x * size, v.co.y * size, v.co.z * size * 0.85))
    tmp.normal_update()
    bmesh.ops.bevel(tmp, geom=tmp.edges[:], offset=size * 0.15, offset_type='OFFSET', segments=1, profile=0.5,
                    affect='EDGES', clamp_overlap=True)
    bmesh.ops.delete(tmp, geom=[f for f in tmp.faces if f.calc_center_median().z < -size * 0.3], context='FACES_ONLY')
    M = Matrix.Translation(c + z * size * 0.18) @ R
    for v in tmp.verts:
        v.co = M @ v.co
    as_built(p, tmp, mat)


def dj_scallion(p, c, axis, r, length, mat='Scallion', inner='ScallionWhite', sides=6):
    """A cut piece of scallion at c along `axis`: a short tube with rounded rims, its ends pale where the hollow shows.
    48 triangles."""
    Z = Vector(axis).normalized()
    X = Z.orthogonal().normalized()
    Y = Z.cross(X)
    tmp = bmesh.new()
    rings = []
    for rad, z in ((0.6 * r, length / 2), (r, length / 2 - 0.0012), (r, -length / 2 + 0.0012), (0.6 * r, -length / 2)):
        rings.append([tmp.verts.new(c + (X * math.cos(2 * math.pi * k / sides) + Y * math.sin(2 * math.pi * k / sides)) * rad
                                    + Z * z) for k in range(sides)])
    mats = []
    for ra, rb in zip(rings, rings[1:]):
        for k in range(sides):
            tmp.faces.new((ra[(k + 1) % sides], ra[k], rb[k], rb[(k + 1) % sides]))
            mats.append(mat)
    for ring, z, rev in ((rings[0], length / 2, False), (rings[-1], -length / 2, True)):
        ctr = tmp.verts.new(c + Z * z)
        for k in range(sides):
            a, b = ring[k], ring[(k + 1) % sides]
            tmp.faces.new((ctr, a, b) if not rev else (ctr, b, a))
            mats.append(inner)
    as_built(p, tmp, mats)


def dj_on(view, bvh, X, Y):
    """Where the line of sight through (X, Y) first meets the surface in bvh, and the normal there (towards the
    camera, and never steeper than the ground allows a piece to lie)."""
    c, nrm, _ = zha_on(view, bvh, X, Y)
    if nrm.z < 0.35:
        nrm = (nrm + Vector((0.0, 0.0, 0.35 - nrm.z)) * 1.6).normalized()
    return c, nrm


def dj_edge_px(poly, X, Y):
    """How far the pixel (X, Y) lies from the outline of the pixel polygon poly."""
    best = 1e9
    for (x0, y0), (x1, y1) in zip(poly, poly[1:] + poly[:1]):
        dx, dy = x1 - x0, y1 - y0
        t = max(0.0, min(1.0, ((X - x0) * dx + (Y - y0) * dy) / max(dx * dx + dy * dy, 1e-9)))
        best = min(best, math.hypot(x0 + dx * t - X, y0 + dy * t - Y))
    return best


def dj_chilli(p, view, bvh, poly, step, seed, size=(40, 58), orange=0.38, dark=0.17, heap=None):
    """Diced chilli strewn over the art's pixel polygon `poly`, about `step` pixels apart, each resting on what is
    under it: red, some orange and some dark red; those well inside the outline of `heap` (pixels) are sunk into it."""
    rnd = random.Random(seed)
    xs, ys = [q[0] for q in poly], [q[1] for q in poly]
    y, row, n = min(ys) + step * 0.4, 0, 0
    while y < max(ys):
        x = min(xs) + step * (0.3 + 0.5 * (row % 2))
        while x < max(xs):
            X, Y = x + rnd.uniform(-0.3, 0.3) * step, y + rnd.uniform(-0.3, 0.3) * step
            if in_poly(X, Y, poly):
                c, nrm = dj_on(view, bvh, X, Y)
                sz = rnd.uniform(*size)
                r = rnd.random()
                mat = 'ChiliOrange' if r < orange else ('DuojiaoDark' if r < orange + dark else 'ChiliRed')
                sunk = heap is not None and in_poly(X, Y, heap) and dj_edge_px(heap, X, Y) > sz * 0.9
                dj_cube(p, c, nrm, sz / view.s * 0.85, mat, rnd.uniform(0, 1.6), rnd.uniform(-0.35, 0.35), sunk=sunk)
                n += 1
            x += step
        y += step * 0.87
        row += 1
    return n


# the heap of chopped chilli over the heads (pixels), the chilli between them, and pieces fallen on the leaves:
# (X, Y, size in pixels)
HEAP22 = [(250, 505), (310, 432), (390, 392), (500, 368), (576, 348), (650, 305), (757, 296), (790, 268), (825, 300),
          (822, 360), (925, 378), (1006, 393), (1086, 410), (1040, 482), (960, 535), (880, 563), (790, 595), (760, 660),
          (713, 735), (636, 688), (544, 676), (500, 640), (440, 690), (400, 775), (350, 790), (305, 708), (260, 610)]


BETWEEN22 = [(790, 620), (830, 650), (870, 700), (920, 725), (955, 745), (945, 770), (900, 780), (850, 800), (810, 790),
             (790, 740), (780, 680)]


LOOSE22 = [(210, 690, 42), (255, 735, 55), (222, 762, 36), (272, 772, 40), (325, 830, 46), (360, 860, 36), (395, 872, 40),
           (1090, 500, 40), (1118, 540, 44), (790, 905, 42), (830, 915, 36), (530, 928, 46), (215, 506, 30),
           (685, 873, 24)]


# the cut scallion over the heap: (X, Y, direction of its length in the art in degrees, how far it points at the
# camera 0..1, length and radius in pixels, pale)
SCALLION22 = [(480, 360, 15, 0.1, 46, 18, 0), (535, 345, -25, 0.1, 44, 18, 0), (725, 288, 5, 0.1, 46, 18, 0),
              (693, 385, 0, 0.9, 38, 19, 0), (837, 363, 30, 0.2, 40, 19, 1),
              (570, 410, 0, 0.9, 36, 18, 0), (620, 415, 75, 0.2, 44, 18, 0), (665, 415, 60, 0.2, 44, 19, 1),
              (607, 465, 20, 0.15, 54, 21, 1), (738, 425, 70, 0.25, 44, 18, 0), (815, 448, 25, 0.2, 44, 19, 1),
              (490, 518, -10, 0.15, 46, 18, 0), (700, 512, 25, 0.2, 56, 21, 1),
              (802, 496, 0, 0.85, 36, 18, 0), (500, 660, -20, 0.15, 44, 18, 0)]


def duojiao_yutou(col, wok=False):
    """剁椒鱼头 as the art has it: a big fish head split in two, the halves lying skin up on bok choy in a deep oval
    celadon dish, one in front and one behind on the right, eyes up and mouths to the right, under a dense heap of
    chopped red chilli with garlic and scallion, orange chilli oil round them. In the wok the food is laid out the same
    way and the dish taken away from under it."""
    p = Part()
    fz = 0.0095
    d = DISH22
    v = VIEW22
    inside = oval_dish(p, d['A'], d['q'], d['yaw'], d['h'], d['foot'], floor=fz, n=48, lip=0.006, rings=3)
    n_dish = len(p.bm.verts)
    dish_sauce(p, 'DuojiaoOil', inside, d['A'], d['q'], d['yaw'], reach=0.74 if wok else 0.8, n=32, seed=22, lift=0.0015)
    bvh = surface(p)
    for k, (outline, mats) in enumerate(LEAVES22):
        dj_leaf(p, v, bvh, outline, mats, seed=k, n=14 if len(outline) > 10 else 12)
    bvh = surface(p)
    f_heads = len(p.bm.faces)
    for dorsal, ventral in HEAD22:
        with p.soft():
            dj_head(p, v, bvh, dorsal, ventral, lambda s, k: 'FishBelly')
    p.tint(f_heads, dj_skin(v), mats=('FishBelly',))
    bvh = surface(p)
    dj_eye(p, v, bvh, 580, 797, 45 / v.s, 18 / v.s, 78 / v.s)
    dj_eye(p, v, bvh, 1057, 614, 40 / v.s, 15 / v.s, 64 / v.s)
    for path, r, mat in MOUTHS22:
        dj_tube(p, v, bvh, path, r / v.s, mat)
    bvh = surface(p)
    with p.soft():
        dj_heap(p, v, bvh, HEAP22, (600, 470), mat='DuojiaoDark')
    bvh = surface(p)
    rnd = random.Random(22)
    n = dj_chilli(p, v, bvh, HEAP22, 66, 22, heap=HEAP22) + dj_chilli(p, v, bvh, BETWEEN22, 62, 23)
    for X, Y, sz in LOOSE22:
        c, nrm = dj_on(v, bvh, X, Y)
        dj_cube(p, c, nrm, sz / v.s * 0.85, 'ChiliRed', rnd.uniform(0, 1.6), rnd.uniform(-0.3, 0.3), sunk=True)
    log(f'D22: {n + len(LOOSE22)} pieces of chilli')
    bvh = surface(p)
    for X, Y, ang, face, ln, r, pale in SCALLION22:
        c, nrm = dj_on(v, bvh, X, Y)
        a = math.radians(ang)
        along = Vector((math.cos(a), 0.0, 0.0)) - Vector((0.0, S35, C35)) * math.sin(a)   # in the picture's plane
        axis = (along * (1 - face) + TOWARD * face).normalized()
        dj_scallion(p, c + nrm * r / v.s * 0.8, axis, r / v.s, ln / v.s,
                    mat='GreenStem' if pale else 'Scallion', inner='ScallionWhite' if pale else 'GreenStem')
    bvh = surface(p)
    for k in range(36):   # bits of garlic and seeds
        while True:
            X, Y = rnd.uniform(240, 1080), rnd.uniform(280, 790)
            if in_poly(X, Y, HEAP22):
                break
        c, nrm = dj_on(v, bvh, X, Y)
        p.blob(c + nrm * 0.0012, 1.0, 'TomatoSeed', segs=(6, 2), rot=rnd.uniform(0, 3),
               deform=lambda q: Vector((q.x * 0.0033, q.y * 0.0027, q.z * 0.0016)))
    if wok:
        zha_without(p, n_dish)
        drop_to(p, 0, 0.0)
    return p.finish('SM_D22' + ('_wok' if wok else ''), col, sharp=None)


TRACED_D19 = os.path.join(os.path.dirname(__file__), 'traced_D19.json')
# 北京烤鸭 traced from its art: the lacquered skin red-brown with its glints, the slices' pale pink cut faces, the
# pancakes, the julienned scallion and cucumber, the leaves under the duck
PALETTE.update({'KaoyaSkin': ('#ec6a1e', '#bc3c0e'),          # 北京烤鸭.png's lacquered skin
                'KaoyaCut': ('#f4d6cc', '#e2b0a2'),           # the slices' cut faces, pale pink
                'KaoyaPancake': ('#f9e8c4', '#ead0a0'),       # the pancakes
                'KaoyaPancakeRim': ('#9a7048', '#7a5232'),    # their edges, one under another
                'KaoyaScallion': ('#e2e09a', '#c4c474'),      # the julienned scallion, pale yellow-green
                'KaoyaScallionWhite': ('#f7f4dc', '#e2dcc0'),  # its white
                'KaoyaGreen': ('#a8bc52', '#86983a'),         # its green
                'KaoyaCucumber': ('#5a7424', '#435a18'),      # the cucumber's dark green skin
                'KaoyaLeaf': ('#6aa63c', '#4a8228')})         # the leaves under the duck
GLOSS.update({'KaoyaSkin': 0.8, 'KaoyaCut': 0.3, 'KaoyaPancake': 0.0, 'KaoyaPancakeRim': 0.0, 'KaoyaScallion': 0.4,
              'KaoyaGreen': 0.4,
              'KaoyaScallionWhite': 0.3, 'KaoyaCucumber': 0.4, 'KaoyaLeaf': 0.4})
VIVID.update({'KaoyaSkin': 0.85, 'KaoyaCut': 0.3, 'KaoyaPancake': 0.3, 'KaoyaPancakeRim': 0.3, 'KaoyaScallion': 0.5,
              'KaoyaGreen': 0.6,
              'KaoyaScallionWhite': 0.2, 'KaoyaCucumber': 0.7, 'KaoyaLeaf': 0.7})
VTINT.update(dict.fromkeys(('KaoyaSkin', 'KaoyaCut'), 1.0))
DETAIL.update({'KaoyaSkin': ('food_pores', 18, '#8a2a0c', 0.45, 0.5),     # the crisp skin's pores
               'KaoyaCut': ('food_fiber', 16, '#e8b2a2', 0.4, 0.3),       # the meat's grain
               'KaoyaPancake': ('food_mottle', 16, '#dcb070', 0.4, 0.15),
               'KaoyaScallion': ('food_fiber', 30, '#a8c878', 0.4, 0.2),
               'KaoyaLeaf': ('food_veins', 30, '#a8d080', 0.4, 0.25)})


def beijing_kaoya(col, wok=False):
    """北京烤鸭 traced from its art (trace_d19.py writes traced_D19.json): on an oval celadon plate, the roast leg
    lying at the back with its drumstick raised, slices of the breast fanned in front of it, red-brown lacquered skin
    over pale pink meat, a stack of thin pancakes at the back on the right and a bundle of julienned scallion and
    cucumber in front of them, leaves showing under the duck; every piece follows its outline in the art. In the wok
    the duck alone (leg, slices, leaves), lowered onto the wok's floor."""
    p = Part()
    d = DISH19
    if not wok:
        oval_dish(p, d['A'], d['q'], d['yaw'], d['h'], d['foot'], floor=0.008, n=48, rings=3)
    traced_dish(p, TRACED_D19, skip=('pancakes', 'julienne') if wok else (),
                lower=(lambda x, y: 0.008) if wok else None, ink='#4a1c0c')
    if wok:
        for v in p.bm.verts:   # nothing below the wok's floor
            v.co.z = max(v.co.z, 0.0)
    return p.finish('SM_D19' + ('_wok' if wok else ''), col, sharp=None)


VIEW18 = ArtView(4403.0, 772.0, 668.0)


STEM_PTS = [(0.076, 0.006, 0.03), (0.1, 0.013, 0.035)]
STEM_PX = [(1295, 455), (1300, 405)]
STEM_W = [0.017, 0.017, 0.016, 0.0145]
STEM_D = [0.016, 0.015, 0.011, 0.008]


DISH18 = dict(A=0.164, q=0.67, yaw=math.radians(-4.7), h=0.0225, foot=0.9)


def art_lobe(p, view, path, widths, anchor, thick, mat_of, sides=6):
    """A rounded lobe for soft() (a jaw) along the path the art shows (pixels), widths[i] pixels across at path[i] and
    thick[i] through (metres), laid in the plane through anchor square to the line of sight, both ends closed by a
    point a little beyond the path. mat_of(k) colours the faces on side k of it (0: on the path's left, in the plane,
    then round towards the camera)."""
    cs = [view.on_plane(X, Y, anchor, TOWARD) for X, Y in path]
    tmp = bmesh.new()
    rings, n = [], len(cs)
    for i, c in enumerate(cs):
        tg = (cs[min(i + 1, n - 1)] - cs[max(i - 1, 0)]).normalized()
        u = TOWARD.cross(tg).normalized()
        w = widths[i] / view.s / 2
        rings.append([tmp.verts.new(c + u * w * math.cos(2 * math.pi * k / sides)
                                    + TOWARD * thick[i] * math.sin(2 * math.pi * k / sides)) for k in range(sides)])
    t0 = (cs[1] - cs[0]).normalized()
    t1 = (cs[-1] - cs[-2]).normalized()
    a = tmp.verts.new(cs[0] - t0 * widths[0] / view.s * 0.3)
    b = tmp.verts.new(cs[-1] + t1 * widths[-1] / view.s * 0.3)
    mats = []
    for ra, rb in zip(rings, rings[1:]):
        for k in range(sides):
            tmp.faces.new((ra[k], ra[(k + 1) % sides], rb[(k + 1) % sides], rb[k]))
            mats.append(mat_of(k))
    for k in range(sides):
        tmp.faces.new((a, rings[0][(k + 1) % sides], rings[0][k]))
        mats.append(mat_of(k))
        tmp.faces.new((rings[-1][k], rings[-1][(k + 1) % sides], b))
        mats.append(mat_of(k))
    piece_in_colours(p, tmp, mats)


def art_fin(p, view, outline, root, anchor, thick, rays, base=None, hub=0.0, grow=None):
    """A fanned fin or tail for soft(): its outline as the art shows it (pixels) round its root (a pixel inside it),
    laid in the plane through anchor square to the line of sight, `thick` through with a rounded rim, grown by `grow`
    about the root as the subdivision draws the rim in. Its front is a fan from the root, the faces in
    rays[k % len(rays)] in turn, stripes running out from the root; given a `hub` (a share of the way out), the faces
    within it are `base` (the tail's sauce-coated stem)."""
    r0 = view.on_plane(*root, anchor, TOWARD)
    g = grow or (1.0 + 0.11 * (1 - hub))
    rim = [r0 + (view.on_plane(X, Y, anchor, TOWARD) - r0) * g for X, Y in outline]
    h = TOWARD * thick / 2
    tmp = bmesh.new()
    F = [tmp.verts.new(q + h) for q in rim]
    B = [tmp.verts.new(q - h) for q in rim]
    H = [tmp.verts.new(r0 + (q - r0) * hub + h * 1.15) for q in rim] if hub else F
    cf, cb = tmp.verts.new(r0 + h * 1.2), tmp.verts.new(r0 - h)
    m = len(rim)
    mats = []
    for i in range(m):
        j = (i + 1) % m
        ray = rays[i % len(rays)]
        tmp.faces.new((cf, H[i], H[j]))
        mats.append(base if hub else ray)
        if hub:
            tmp.faces.new((H[i], F[i], F[j], H[j]))
            mats.append(ray)
        tmp.faces.new((F[i], B[i], B[j], F[j]))
        mats.append(ray)
        tmp.faces.new((cb, B[j], B[i]))
        mats.append(rays[0])
    piece_in_colours(p, tmp, mats)


def guiyu_core(q, a, low):
    """The body under 松鼠鳜鱼's crisp pieces, from a point q of an ellipsoid a long: squared off towards its ends
    (a superellipse along its length) so that it carries the pieces as far as the art draws them, and flat on the
    floor `low` below its middle."""
    xn = min(1.0, abs(q.x) / a)
    k = min(3.0, (max(0.0, 1 - xn ** 4) ** 0.25) / math.sqrt(max(1e-6, 1 - xn * xn)))
    return Vector((q.x, q.y * k, max(q.z * k, low)))


def art_line(line, X):
    """The pixel height (Y) of the pixel polyline `line` at X, held level beyond its ends."""
    if X <= line[0][0]:
        return line[0][1]
    for (x0, y0), (x1, y1) in zip(line, line[1:]):
        if X <= x1:
            return y0 + (y1 - y0) * (X - x0) / (x1 - x0)
    return line[-1][1]


def crisp_colour(floor):
    """松鼠鳜鱼's crisp pieces painted as the art has them, for Part.tint: a deeper red-orange where the sauce runs
    down to the plate, golden higher up, browned here and there where they fried darker."""
    from .meat_fish import dab, mix, ramp
    SAUCE, GOLD, BROWN = '#e04a1e', '#fba744', '#b8582a'

    def field(q, n):
        h = q.z - floor
        col = mix(SAUCE, GOLD, ramp(0.012, 0.045, h))
        w = 0.45
        b = ramp(0.62, 0.78, dab(q, 0.004, 1.0))
        if b > 0.05:
            col, w = mix(col, BROWN, 0.6 * b), max(w, 0.55 + 0.25 * b)
        return col, w
    return field


def head_colour(view):
    """松鼠鳜鱼's head painted as the art has it, for Part.tint: the dark brown skin over its crown and down behind
    the eye fading softly into the golden crisp, a glaze of red-orange sauce over its cheek, darker flecks."""
    from .meat_fish import dab, mix, ramp

    def sd(poly):
        def f(X, Y):
            P = Vector((X, Y))
            d = min((P - (Vector(a) + (Vector(b) - Vector(a)) * min(max((P - Vector(a)).dot(Vector(b) - Vector(a))
                    / max((Vector(b) - Vector(a)).length_squared, 1e-9), 0.0), 1.0))).length
                    for a, b in zip(poly, poly[1:] + poly[:1]))
            return d if in_poly(X, Y, poly) else -d
        return f
    dark, glaze = sd(DARK18), sd(GLAZE18)

    def field(q, n):
        X, Y = view.px(q)
        wd = 0.85 * ramp(-14.0, 18.0, dark(X, Y) + 10.0 * (dab(q, 0.003) - 0.5))
        wg = 0.6 * ramp(-12.0, 16.0, glaze(X, Y))
        if wd >= wg and wd > 0.02:
            return mix('#9a5a28', '#6e3a18', ramp(0.45, 0.75, dab(q, 0.0025, 2.0))), wd
        if wg > 0.02:
            return '#e8642c', wg
        return None
    return field


def crisp_kernel(p, c, d, L, W, T, mat):
    """One crisp piece of 松鼠鳜鱼's flesh, as the art draws them: a plump lozenge L long along d, W wide across the
    picture and T through, widest a little behind its middle and drawn to a blunt point at its tip, flatter towards
    the edges than a sausage. 80 triangles."""
    z = d.normalized()
    x = TOWARD.cross(z)
    x = (x if x.length > 1e-4 else z.orthogonal()).normalized()
    R = Matrix((x, z.cross(x), z)).transposed()

    def shape(q):
        k = (1.0 - 0.42 * max(q.z, 0.0) ** 1.4) * (1.0 - 0.12 * max(-q.z, 0.0))   # pointed at the tip
        flat = 1.0 - 0.18 * abs(q.x)                                            # a lozenge's flatter sides
        return R @ Vector((q.x * W / 2 * k, q.y * T / 2 * k * flat, q.z * L / 2))
    p.blob(c, 1.0, mat, segs=(8, 6), deform=shape)


# the tips of 松鼠鳜鱼's top row of crisp pieces and where its lowest dip into the sauce (pixels)
TOP18 = [(540, 384), (600, 348), (760, 340), (900, 346), (1000, 360), (1100, 385), (1180, 405), (1240, 425)]
BOTTOM18 = [(540, 722), (700, 738), (900, 738), (1050, 718), (1150, 692), (1240, 640)]


# its rows of pieces, top to bottom: the share of the way from the top row's bases to the bottom row's, the direction
# they point in the art at the middle of the body (degrees, 90 up the picture), how far they lean out towards the
# camera (degrees), their length and width (pixels) and the share of them coated in sauce. Like the art's they point
# towards the head, up or down, splaying out towards the tail.
CONE18 = [(0.0, 96, 4, 136, 70, 0.25), (0.27, 112, 24, 136, 72, 0.4), (0.53, 126, 46, 128, 72, 0.55),
          (0.78, 232, 34, 134, 72, 0.75), (1.0, 252, 14, 132, 70, 0.9)]


def crisp_lattice(p, view, bvh, floor, seed, step=76.0, x0=578.0, x1=1236.0, splay=36.0):
    """The body of 松鼠鳜鱼 as the art draws it: rows of plump crisp pieces over the core in bvh, each row a half step
    along from the one above, packed so that the core hardly shows. Those in the upper rows stand up the picture from
    bases on the core, the top row's tips along TOP18; the lower ones hang down into the sauce to BOTTOM18; they lean
    out towards the camera more the further down the front they sit."""
    rnd = random.Random(seed)
    UP = Vector((0.0, S35, C35))   # up the picture

    def angle(row, dx):
        up = CONE18[row][1] < 180
        return math.radians(CONE18[row][1] + (-splay if up else splay) * dx * (0.55 if row == 0 else 1.0))

    def reach(row, dx):   # how far up (or down) the picture a piece of the row reaches from its base, in pixels
        return CONE18[row][3] * 0.86 * abs(math.sin(angle(row, dx))) * math.cos(math.radians(CONE18[row][2]))
    for k, (f, deg, lean, Lp, Wp, glaze) in enumerate(CONE18):
        up = deg < 180
        X = x0 + (step / 2 if k % 2 else 0.0)
        while X <= x1 + 1:
            Xj = X + rnd.uniform(-6, 6)
            L, W = Lp / view.s * rnd.uniform(0.93, 1.07), Wp / view.s * rnd.uniform(0.94, 1.06)
            a = math.radians(lean + rnd.uniform(-6, 6))
            dx = max(-1.0, min(1.0, (Xj - 905) / 330))
            top = art_line(TOP18, Xj) + reach(0, dx)
            bot = art_line(BOTTOM18, Xj) - reach(len(CONE18) - 1, dx)
            Y = top + (bot - top) * f + rnd.uniform(-5, 5)
            ang = angle(k, dx) + rnd.uniform(-0.1, 0.1)
            hit = None
            for dy in range(0, 200, 8):   # the base: where the line of sight meets the core, or nearest it
                hit = view.onto(bvh, Xj, Y + (dy if up else -dy))
                if hit:
                    break
            X += step
            if not hit:
                continue
            base, nrm = hit
            d = (Vector((math.cos(ang), 0.0, 0.0)) + UP * math.sin(ang)) * math.cos(a) + TOWARD * math.sin(a)
            if d.dot(nrm) < 0.2:
                d += nrm * (0.2 - d.dot(nrm)) * 1.4
            d.normalize()
            lo = floor + W * 0.42 + 0.0008   # no lower than this at the tip, over the sauce
            if base.z + d.z * L * 0.9 < lo:
                d.z = (lo - base.z) / (L * 0.9)
                d.normalize()
            crisp_kernel(p, base + d * L * 0.4, d, L, W, W * 0.82,
                         'GuiyuGlaze' if rnd.random() < glaze else 'CrispPiece')


HEAD18 = [(322, 140), (345, 152), (366, 176), (400, 202), (446, 240), (484, 284), (522, 332), (553, 378), (564, 440),
          (550, 492), (518, 540), (478, 588), (440, 632), (412, 676), (370, 692), (330, 684), (298, 662), (278, 625),
          (258, 570), (240, 510), (224, 445), (210, 385), (198, 338), (185, 300), (170, 271), (166, 251), (190, 241),
          (222, 249), (248, 263), (266, 281), (276, 262), (281, 232), (286, 196), (296, 156)]


DARK18 = [(320, 140), (345, 148), (372, 176), (430, 220), (480, 260), (520, 310), (550, 355), (566, 400), (560, 432),
          (532, 420), (505, 366), (480, 336), (440, 342), (395, 332), (368, 296), (345, 255), (335, 200)]


MOUTH18 = [(300, 170), (325, 178), (341, 210), (338, 255), (327, 305), (314, 320), (297, 302), (287, 250), (291, 200)]


THROAT18 = [(244, 272), (262, 284), (274, 276), (282, 250), (288, 214), (298, 222), (300, 256), (294, 288), (280, 304),
            (258, 300), (240, 288)]   # the corner of the gaping mouth, deep between the jaws


JAWIN18 = [(172, 262), (200, 252), (232, 262), (258, 280), (276, 306), (280, 336), (258, 342), (230, 326), (204, 302),
           (184, 282)]   # the pale inside of the lower jaw


GLAZE18 = [(334, 338), (380, 336), (440, 344), (490, 370), (505, 425), (488, 472), (440, 488), (385, 470), (348, 430),
           (334, 385)]


LIPS18 = [[(168, 246), (200, 236), (236, 250), (272, 264), (268, 276), (234, 264), (200, 254), (170, 260)],
          [(290, 146), (306, 154), (298, 200), (290, 250), (284, 292), (270, 292), (276, 240), (284, 190)]]


FIN_L18 = [(285, 500), (240, 492), (205, 498), (179, 517), (184, 540), (179, 556), (205, 580), (229, 602), (262, 612),
           (290, 590)]


FIN_R18 = [(412, 515), (450, 499), (505, 497), (556, 508), (572, 536), (566, 561), (576, 586), (564, 614), (537, 638),
           (504, 655), (468, 640), (432, 600), (414, 560)]


FIN_P18 = [(408, 615), (440, 610), (478, 635), (492, 685), (474, 728), (454, 742), (438, 722), (420, 682), (404, 645)]


TAIL18 = [(1240, 430), (1236, 380), (1203, 333), (1165, 275), (1138, 225), (1135, 185), (1150, 170), (1203, 207),
          (1237, 170), (1256, 174), (1268, 190), (1287, 137), (1302, 130), (1330, 152), (1350, 194), (1381, 212),
          (1400, 262), (1416, 315), (1405, 370), (1390, 430), (1360, 460), (1290, 460)]


DISH19 = dict(A=0.149, q=0.831, yaw=math.radians(-52.2), h=0.0116, foot=0.88)


ITEMS = [('D01', hubing),
         ('D01_wok', lambda c: hubing(c, True)),
         ('D05', shuijing_kuai),
         ('D05_wok', lambda c: shuijing_kuai(c, True)),
         ('D10', jianyu_fan),
         ('D10_wok', lambda c: jianyu_fan(c, True)),
         ('D12', liangshu_zisu_yu),
         ('D12_wok', lambda c: liangshu_zisu_yu(c, True)),
         ('D14', yuban_zha),
         ('D14_wok', lambda c: yuban_zha(c, True)),
         ('D18', songshu_guiyu),
         ('D18_wok', lambda c: songshu_guiyu(c, True)),
         ('D22', duojiao_yutou),
         ('D22_wok', lambda c: duojiao_yutou(c, True)),
         ('D19', beijing_kaoya),
         ('D19_wok', lambda c: beijing_kaoya(c, True))]
