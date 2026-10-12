"""蔬菜与姜、葱、蒜: tomato, chili, potato, radish, gourd, bamboo, perilla, mushroom, garlic, greens, scallion, ginger."""


import json
import math
import os
import random
import bmesh
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree
from .core import *  # noqa: F401,F403


def pv_vibrant(c, k=1.9, deepen=0.15):
    """WatercolorLit's Vibrant(): a linear colour's saturation raised along 1 - (1 - s)^k, the same hue and value,
    then deepened a little."""
    mx, mn = max(c), min(c)
    if mx - mn < 1e-4:
        return list(c)
    s = (mx - mn) / mx
    s2 = 1 - (1 - s) ** k
    return [mx * (1 - s2 * (1 - (x - mn) / (mx - mn))) * (1 - deepen * s2) for x in c]


def pv_unvivid(t, f):
    """The linear colour that the shader's food colour (_Vivid f: lerp(c, Vibrant(c), f)) turns into t: so that a
    colour taken from the art lights up as the art paints it, while its shade keeps the full, deep colour of the art
    (not the greyed one)."""
    if f <= 0:
        return list(t)
    c = list(t)
    for _ in range(40):
        v = pv_vibrant(c)
        g = [a + (b - a) * f for a, b in zip(c, v)]
        c = [min(max(x + (y - z), 0.0), 1.0) for x, y, z in zip(c, t, g)]
    return c


def pv_traced(p, key):
    """The pieces trace_<key>.py traced off the item's art (food_models/traced_<key>.json, made with trace_veg.py):
    each a surface in its material over its outline in the art, every corner of it the art's colour where it shows
    (Part's 'Tint' layer, so its material is in VTINT) with the art's ink line along its own margins, and the marks
    the art paints across it (veins, eyes, rings, streaks) the colour of the faces laid along them."""
    data = json.load(open(os.path.join(os.path.dirname(__file__), f'traced_{key}.json'), encoding='utf-8'))
    lay = p.bm.loops.layers.float_color.get('Tint') or p.bm.loops.layers.float_color.new('Tint')

    for piece in data['pieces']:
        f = VIVID.get(piece['mat'], 1.0)

        def tint(h, w, f=f):
            return (*pv_unvivid(linear(h), f), 1.0 - min(max(w, 0.0), 0.999))
        vs = [p.bm.verts.new(Vector(q)) for q in piece['verts']]
        mi = p._mi(piece['mat'])
        vc = [tint(h, w) for h, w in piece['vcol']]
        for (a, b, c), mark in zip(piece['tris'], piece['tcol']):
            try:
                f = p.bm.faces.new((vs[a], vs[b], vs[c]))
            except ValueError:   # the same triangle twice
                continue
            f.material_index = mi
            m = tint(*mark) if mark else None
            for loop, i in zip(f.loops, (a, b, c)):
                loop[lay] = m or vc[i]
    return data


# 笋 and 菌菇: the shades of their sheaths, cut faces, caps and gills, picked from 笋.png and 菌菇.png
PALETTE.update({
    'BambooHuskDark': ('#a5673a', '#7b4526'),       # the darker sheaths of the shoot
    'BambooHuskTan': ('#c98d4c', '#9e6535'),
    'BambooSheathYellow': ('#e8c95f', '#c3a03e'),   # yellow sheaths high on the shoot
    'BambooBud': ('#b3a144', '#867630'),            # the green bud at the top
    'BambooTipGreen': ('#937c2e', '#6c5a20'),       # its green sheaths
    'BambooCut': ('#fcf0c6', '#ecd59c'),            # the cut faces of the slices
    'BambooChamber': ('#f1c573', '#d8a44e'),        # the chambers showing in them
    'BambooRing': ('#efc47c', '#d6a157'),           # the lines where the peeled shoot's layers end
    'ShiitakeGill': ('#d8b688', '#b89266'),         # the lines between the gills
    'ShiitakeCut': ('#fbf0d8', '#e9d5ae'),          # the stem's cut end
})


GLOSS.update(dict.fromkeys(('BambooHuskDark', 'BambooHuskTan', 'BambooSheathYellow', 'BambooBud', 'BambooTipGreen'),
                           0.0))


PALETTE.update({
    'ScallionLeaf': ('#7c985d', '#5d7a45'),    # 葱's flat dark leaves, as the art paints them
    'ScallionStalk': ('#b9c96c', '#8fa046'),   # the pale green between the leaves and the white bulbs
    'ScallionRoot': ('#efd6a4', '#c9a06a'),    # its root hairs
    'GarlicRoot': ('#e4b477', '#b17b48'),      # 蒜's root nubs, its dry neck tip and the root scars of the cloves
    'GarlicCrease': ('#c9a27e', '#a47e5c'),    # the brown lines down the creases between its cloves
    'GingerSkin': ('#f9d394', '#dea25e'),      # 姜's skin, as the art paints it
    'GingerRing': ('#d9a463', '#b78046'),      # the rings round its knobs and inside its slices
    'PerillaOlive': ('#b3a46e', '#8a7a4a'),    # 紫苏's olive-green leaves and stalks, as the art paints them
    'PerillaCut': ('#e6c48e', '#c9a16a'),      # the pale cut ends of its stalks
})


GLOSS.update({'ScallionRoot': 0.0, 'GarlicRoot': 0.0, 'GarlicCrease': 0.0, 'GingerSkin': 0.0, 'GingerRing': 0.0})


PALETTE.update({
    'GreensArtLeaf': ('#b4c870', '#88a04a'),   # 时蔬 under the art's own colours (pv_traced)
})
GLOSS.update({'GreensArtLeaf': 0.15})
VIVID.update({'GreensArtLeaf': 0.5})
VTINT.update({'GreensArtLeaf': 1.0})
DETAIL.update({'GreensArtLeaf': ('food_leafvein', 20, '#eef4c8', 0.35, 0.3)})   # the fine veins between the art's


def art_px(S, u0, v0):
    """A function at(u, v, z): the point at height z that the art shows at pixel (u, v), for an art drawn at S
    pixels per metre with the model's origin (on the ground) at pixel (u0, v0)."""
    c, s = math.cos(ART_EL), math.sin(ART_EL)

    def at(u, v, z=0.0):
        return Vector(((u - u0) / S, ((v0 - v) / S - z * c) / s, z))
    return at


def art_uv(S, u0, v0):
    """The other way round from art_px(): the pixel (u, v) of the art where a point of the model shows."""
    c, s_ = math.cos(ART_EL), math.sin(ART_EL)

    def uv(q):
        return u0 + S * q.x, v0 - S * (q.z * c + q.y * s_)
    return uv


def frame_along(d, up=(0.0, 0.0, 1.0)):
    """Unit axes (along, across, normal) for something running along d whose broad face looks toward `up`."""
    d = Vector(d).normalized()
    a = Vector(up).cross(d)
    if a.length < 1e-6:
        a = Vector((0.0, 1.0, 0.0)).cross(d)
    a.normalize()
    return d, a, d.cross(a)


def ribbon(p, pts, widths, thick, mat, ups=None, sides=6):
    """A flat strand along the polyline pts (sepals, stalks, strap leaves): a cross-section `sides` round, widths[i]
    wide and thick (a number or a list) through, its broad face toward ups[i] (default up); both ends close to a
    point. Build it inside p.soft() and it comes out round-edged and smooth."""
    pts = [Vector(q) for q in pts]
    n = len(pts)
    ups = ups or [(0.0, 0.0, 1.0)] * n
    thick = thick if isinstance(thick, (list, tuple)) else [thick] * n
    tmp = bmesh.new()
    rings = []
    for i, q in enumerate(pts):
        t = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        _, a, b = frame_along(t, ups[i])
        rings.append([tmp.verts.new(q + a * widths[i] / 2 * math.cos(2 * math.pi * k / sides)
                                    + b * thick[i] / 2 * math.sin(2 * math.pi * k / sides)) for k in range(sides)])
    for ra, rb in zip(rings, rings[1:]):
        for k in range(sides):
            tmp.faces.new((ra[k], ra[(k + 1) % sides], rb[(k + 1) % sides], rb[k]))
    for ring, end, sgn in ((rings[0], pts[0] - (pts[1] - pts[0]).normalized() * thick[0] * 0.3, -1),
                           (rings[-1], pts[-1] + (pts[-1] - pts[-2]).normalized() * thick[-1] * 0.3, 1)):
        tip = tmp.verts.new(end)
        for k in range(sides):
            f = (ring[k], ring[(k + 1) % sides], tip)
            tmp.faces.new(f if sgn > 0 else f[::-1])
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)


def greens(col):
    """时蔬 traced off its art (trace_greens.py): a head of crinkly leafy greens lying on its side, its pale stalks
    gathered at the lower right with their cut ends, the leaves fanning out to the upper left, the light front leaves
    lying over the darker outer leaves that show round them. Every piece covers exactly what the art paints, in the
    art's own colours (the dark and light greens of the crinkles, the pale stalks running up into the midribs), the
    art's pale veins painted on, its shading in relief."""
    p = Part()
    pv_traced(p, 'greens')
    return pb_finish(p, 'SM_greens', col, pb_recentre(p))


SC_ART = (4800, 800, 640)   # 葱.png: px per metre, the origin's pixel (trace_scallion.py's camera)
SC_PLATES = ((1300, 700), (1255, 795), (1200, 870))   # the bulbs' root plates (art px), where the hairs grow from
SC_MATS = ((1332, 723, 0.008, 0.0052, -0.3), (1321, 809, 0.007, 0.0048, -0.5), (1227, 884, 0.009, 0.0056, -0.9),
           (1325, 770, 0.004, 0.0045, -0.6), (1268, 848, 0.004, 0.0048, -0.4))   # the matted root bases on the
                                                                                    # plates: art px, height, size, turn


PALETTE.update({
    'ScallionArtLeaf': ('#6f9050', '#4f7038'),     # 葱 under the art's own colours (pv_traced): its leaves
    'ScallionArtBulb': ('#f4f1df', '#d6d2b6'),     # its white bulbs
    'ScallionArtString': ('#dcc07a', '#b89a55'),   # the string round the bunch
    'ScallionArtRoot': ('#eed8a8', '#c4a474'),     # the root hairs, cream inside the art's brown lines
})
GLOSS.update({'ScallionArtLeaf': 0.2, 'ScallionArtBulb': 0.3, 'ScallionArtString': 0.0, 'ScallionArtRoot': 0.0})
VIVID.update({'ScallionArtLeaf': 0.5, 'ScallionArtBulb': 0.4, 'ScallionArtString': 0.4, 'ScallionArtRoot': 0.4})
VTINT.update(dict.fromkeys(('ScallionArtLeaf', 'ScallionArtBulb', 'ScallionArtString'), 1.0))
DETAIL.update({'ScallionArtLeaf': ('food_fiber', 20, '#a8c880', 0.3, 0.2),    # streaks along the leaves
               'ScallionArtBulb': ('food_garlic', 20, '#e8e2c0', 0.25, 0.1)})


def scallion(col):
    """葱 traced off its art (trace_scallion.py): a bunch of three spring onions lying on the table, tied with string,
    four flat dark-green leaves fanning to the upper left and paling into their light-green stalks, the white bulbs to
    the lower right with their tangles of root hairs. Every piece covers exactly what the art paints, in the art's own
    colours; the root hairs follow the art's, out from the root plates onto the table."""
    p = Part()
    data = pv_traced(p, 'scallion')
    S, u0, v0 = SC_ART
    at = art_px(S, u0, v0)
    with p.soft():
        for (u, v, z, rr, rot) in SC_MATS:
            p.blob(at(u, v, z), rr, 'ScallionArtRoot', squash=(1.5, 1.0, 0.7), segs=(6, 3), rot=rot)
    for hair in data['hairs']:   # the root hairs traced off the art, from the root plates out onto the table
        pu, pv = min(SC_PLATES, key=lambda q: math.hypot(hair[0][0] - q[0], hair[0][1] - q[1]))
        if math.hypot(hair[0][0] - pu, hair[0][1] - pv) < 70:   # grown from the plate it starts nearest
            hair = [[pu + (hair[0][0] - pu) * 0.5, pv + (hair[0][1] - pv) * 0.5, hair[0][2]]] + hair
        n = len(hair)
        out = [min(1.0, min(math.hypot(u - pu, v - pv) for pu, pv in SC_PLATES) / 160) for u, v, _ in hair]
        pts = [at(u, v, 0.0075 - 0.0067 * o ** 0.6) for (u, v, _), o in zip(hair, out)]   # down onto the table
        r = [max(min(w, 5.0), 3.0) / S for _, _, w in hair]   # as wide as the art draws them, brown lines and all
        pb_hair(p, pts, r[0], max(r[-1] * 0.7, 1.2 / S), 'ScallionArtRoot', sides=3)
    return pb_finish(p, 'SM_scallion', col, pb_recentre(p))


PALETTE.update({
    'GingerArtSkin': ('#e2b06a', '#b98346'),    # 姜's skin under the art's own colours (pv_traced)
    'GingerArtFlesh': ('#f7dc8a', '#e0bc5e'),   # the cut flesh of its slices
})
GLOSS.update({'GingerArtSkin': 0.0, 'GingerArtFlesh': 0.35})
VIVID.update({'GingerArtSkin': 0.5, 'GingerArtFlesh': 0.5})
VTINT.update(dict.fromkeys(('GingerArtSkin', 'GingerArtFlesh'), 1.0))
DETAIL.update({'GingerArtSkin': ('food_ginger', 16, '#9a6a34', 0.35, 0.3),     # fibrous streaks and flecks
               'GingerArtFlesh': ('food_fiber', 22, '#f0c860', 0.25, 0.15)})


def ginger(col):
    """姜 traced off its art (trace_ginger.py): a knobbly hand of ginger lying on the table, ringed with brown lines,
    its cut ends showing the yellow flesh, and in front on the right two oval slices, the near one over the far one,
    each with a darker ring inside. Every piece covers exactly what the art paints, in the art's own colours."""
    p = Part()
    pv_traced(p, 'ginger')
    return pb_finish(p, 'SM_ginger', col, pb_recentre(p))


RADISH_ART = (4500, 650, 850)   # 萝卜.png: px per metre, the origin's pixel (trace_radish.py's camera)


RADISH_HAIRS = (   # the root hairs: art px and radius (px), from the tail out
    [[172, 918, 6], [130, 935, 5], [100, 962, 4], [80, 1005, 3]],
                [[162, 977, 6], [115, 1015, 5], [70, 1040, 4], [40, 1066, 3], [37, 1104, 2]],
                [[130, 1045, 6], [102, 1075, 5], [90, 1115, 4], [95, 1150, 3], [112, 1162, 2]],
                [[212, 1012, 4], [212, 1035, 3], [222, 1052, 2]],
                [[335, 1012, 5], [310, 1040, 4], [277, 1062, 2]])


PALETTE.update({
    'RadishArtSkin': ('#f6eedc', '#dccaa8'),    # 萝卜 under the art's own colours (pv_traced)
    'RadishArtFlesh': ('#fbf6ea', '#e6dac2'),   # the cut faces of its slices
    'RadishArtLeaf': ('#8db45a', '#62863a'),    # its leaves
    'RadishArtStalk': ('#d6dc94', '#b0b86a'),   # their pale stalks
    'RadishArtHair': ('#d8b98e', '#ae8a5e'),    # the root hairs
})
GLOSS.update({'RadishArtSkin': 0.15, 'RadishArtFlesh': 0.3, 'RadishArtLeaf': 0.15, 'RadishArtStalk': 0.15,
              'RadishArtHair': 0.0})
VIVID.update({'RadishArtSkin': 0.4, 'RadishArtFlesh': 0.4, 'RadishArtLeaf': 0.5, 'RadishArtStalk': 0.5,
              'RadishArtHair': 0.4})
VTINT.update(dict.fromkeys(('RadishArtSkin', 'RadishArtFlesh', 'RadishArtLeaf', 'RadishArtStalk'), 1.0))
DETAIL.update({'RadishArtLeaf': ('food_leafvein', 22, '#d4e6a0', 0.35, 0.25),   # the fine veins between the art's
               'RadishArtSkin': ('food_mottle', 12, '#efe2c4', 0.2, 0.15),
               'RadishArtFlesh': ('food_fiber', 26, '#ffffff', 0.3, 0.1)})


def radish(col):
    """萝卜 traced off its art (trace_radish.py): a long white radish lying on the table, turning green at its shoulder,
    four ruffled leaves fanning up behind its crown on pale stalks, a few root hairs at its tail, and in front of it two
    thick round slices with pale rayed cut faces, the near one over the far one. Every piece covers exactly what the
    art paints, in the art's own colours."""
    p = Part()
    pv_traced(p, 'radish')
    S, u0, v0 = RADISH_ART
    at = art_px(S, u0, v0)
    for hair in RADISH_HAIRS:   # from the tail out onto the table, tapering
        n = len(hair)
        pts = [at(u, v, 0.006 - 0.005 * i / (n - 1)) for i, (u, v, _) in enumerate(hair)]
        pb_hair(p, pts, hair[0][2] / S * 0.5, hair[-1][2] / S * 0.5, 'RadishArtHair')
    return pb_finish(p, 'SM_radish', col, pb_recentre(p))


def pa_warts(p, rings, mat, r, every=2, rows=(), view_min=-0.25, seed=0):
    """Round warts on a body given by rings: one at every `every`-th ring on each of the columns in rows (shifted a
    half step on alternate rings so they stagger), on the side the viewer can see, each a small bump r across
    standing half out of the skin."""
    view = Vector((0.0, -math.cos(ART_EL), math.sin(ART_EL)))
    rnd = random.Random(seed)
    n = len(rings[0])
    for i in range(2, len(rings) - 2, every):
        ring = rings[i]
        c = sum(ring, Vector()) / n
        for j in rows:
            k = (j + (i // every) % 2 * 0.5) % n
            a, b = ring[int(k) % n], ring[(int(k) + 1) % n]
            q = a.lerp(b, k - int(k))
            nrm = (q - c).normalized()
            if nrm.dot(view) < view_min:
                continue
            R = nrm.to_track_quat('Z', 'Y').to_matrix()
            rr = r * rnd.uniform(0.8, 1.15)
            p.blob(q + nrm * rr * 0.15, rr, mat, squash=(1.0, 1.0, 0.7), segs=(5, 2), deform=lambda w, R=R: R @ w)


GOURD_ART = (6000, 650, 760)   # 瓜菜.png: px per metre, the origin's pixel


GOURD_WHOLE = [0.0123, 0.0031, -0.6855, -0.0675, 0.0305, 0.1973, -0.035, 0.0413]   # x, y, yaw, pitch, R, L, taper, bend


GOURD_CUT = ([-0.0376, -0.0459, -0.606, -0.0075, 0.0335, 0.118, 0.035, -0.0275], (0.9375, 1.97))   # and the slant


GOURD_STALK = [[262, 330, 42, 0.0], [236, 292, 35, 0.005], [220, 264, 34, 0.011], [204, 246, 37, 0.017],
               [188, 232, 42, 0.021]]   # art px (u, v, r) and how far above the cucumber's end


GOURD_SEEDS = [(615, 737, 60, 65), (665, 728, 80, 55), (718, 782, 63, 25), (785, 825, 100, 40), (822, 880, 85, 40),
               (604, 795, 50, 65), (657, 838, 45, 75), (704, 885, 52, 80), (792, 922, 95, 35)]   # art px, and tip to tail


def pa_on_plane(at, u, v, c, n):
    """The point of the plane through c square to n that the art shows at pixel (u, v)."""
    o = at(u, v, 0.5)
    d = at(u, v, 0.0) - o
    return o + d * ((c - o).dot(n) / d.dot(n))


def gourd(col):
    """瓜菜 as the art has it: a whole cucumber lying behind with its curved stalk ending in a cut, and in front a
    second one sliced off on a long slant, its oval face turned up to the viewer showing the pale flesh and a fan
    of seeds round the middle; both thick, round-ended and warty. Laid out on 瓜菜.png (60 px to the centimetre)."""
    p = Part()
    S, u0, v0 = GOURD_ART
    at = art_px(S, u0, v0)
    with p.soft():
        rings, poles, _ = pa_cucumber(GOURD_WHOLE, nu=12, seg=6)
        pa_cage(p, rings, poles, 'CucumberGreen')
        fine, fpoles, _ = pa_cucumber(GOURD_WHOLE, nu=24, seg=14)
        pa_warts(p, fine, 'CucumberSeed', 0.0034, every=3, rows=(1, 5, 9, 13, 17, 21), seed=1)
        sd = pa_spline(GOURD_STALK)
        z0 = pa_on_ray(at, sd[0][0], sd[0][1], fpoles[0]).z
        scs = [at(u, v, z0 + dz) for (u, v, _, dz) in sd]
    f1 = len(p.bm.faces)
    with p.soft():   # the stalk, its end cut flat
        rings = pa_canal(p, scs, [q[2] / S for q in sd], 'CalyxGreen', sides=8, spacing=1.0, lo=0.003, hi=0.008,
                         ends=(True, 'flat'))
    tip, t_end = rings[-1][0], rings[-1][2]
    pa_paint(p, f1, 'CucumberFlesh', lambda q: (q - tip).dot(t_end) + 0.0005)
    f0 = len(p.bm.faces)
    with p.soft():
        rings, poles, (c, n, _) = pa_cucumber(GOURD_CUT[0], cut=GOURD_CUT[1], nu=16, seg=6)
        pa_cage(p, rings, poles, 'CucumberGreen')
    pa_paint(p, f0, 'CucumberFlesh', lambda q: (q - c).dot(n) + 0.0008)
    with p.soft():
        fine, _, _ = pa_cucumber(GOURD_CUT[0], cut=GOURD_CUT[1], nu=24, seg=12)
        pa_warts(p, fine[:-4], 'CucumberSeed', 0.0036, every=3, rows=(0, 4, 8, 12, 16, 20), seed=2)
        for (u, v, du, dv) in GOURD_SEEDS:   # seeds: flat round-ended drops fanning out from the middle of the face
            a = pa_on_plane(at, u - du / 2, v - dv / 2, c, n)
            b = pa_on_plane(at, u + du / 2, v + dv / 2, c, n)
            d = (b - a).normalized()
            R = Matrix((d, n.cross(d), n)).transposed()
            p.blob((a + b) / 2 + n * 0.0009, (b - a).length * 0.62, 'CucumberSeed', squash=(1.0, 0.55, 0.2), segs=(6, 2),
                   deform=lambda w, R=R: R @ w)
    return p.finish('SM_gourd', col, sharp=None)


BAMBOO_ART = (6500, 640, 1060)   # 笋.png: px per metre, the origin's pixel


BAMBOO_CORE = [[300, 935, 150], [342, 862, 248], [458, 714, 264], [575, 528, 229], [662, 350, 155], [741, 205, 85],
               [808, 77, 21], [826, 46, 5]]   # the sheathed shoot under its sheaths: centre line (u, v, r), art px


# The sheaths, outer to inner: colour, level (how many lie under it where it overlaps them), tip, and its two edges
# from the tip down (art px; along the silhouette where the art has it there, then on under the sheaths that hide
# it), rows and columns of its mesh.
BAMBOO_SHEATHS = (
    ('BambooHusk', 7, (290, 456),
     [(271, 512), (243, 565), (205, 615), (171, 664), (140, 725), (97, 809), (70, 880), (83, 910), (102, 932),
      (111, 993), (134, 1008), (162, 1038), (207, 1060), (250, 1078), (294, 1089), (305, 1100)],
     [(292, 467), (288, 527), (288, 551), (298, 570), (299, 606), (314, 622), (332, 630), (372, 670), (417, 710),
      (466, 762), (505, 808), (520, 826), (545, 840), (500, 868), (460, 890), (420, 915), (385, 945), (350, 980),
      (322, 1015), (310, 1050), (312, 1080), (318, 1100)], 8, 3),
    ('BambooHuskDark', 6, (832, 499),
     [(806, 506), (781, 525), (756, 538), (725, 550), (690, 561), (674, 570), (627, 570), (580, 570), (522, 578),
      (464, 590), (398, 610), (332, 630), (314, 648), (354, 688), (399, 728), (448, 780), (487, 826), (521, 850),
      (553, 840), (595, 822), (630, 860)],
     [(832, 511), (824, 533), (816, 555), (808, 577), (806, 601), (827, 615), (813, 647), (794, 675), (770, 701),
      (745, 739), (725, 767), (703, 796), (685, 825), (663, 853), (650, 875)], 8, 3),
    ('BambooHusk', 5, (488, 245),
     [(482, 248), (466, 278), (447, 308), (427, 336), (405, 366), (382, 393), (358, 419), (335, 446), (312, 474),
      (298, 494), (275, 520), (265, 550), (272, 575), (276, 605), (290, 630), (305, 645)],
     [(494, 257), (498, 268), (501, 276), (499, 293), (494, 317), (494, 329), (496, 340), (502, 350), (512, 370),
      (530, 386), (548, 402), (566, 418), (583, 436), (596, 456), (608, 475), (624, 493), (640, 511), (656, 530),
      (676, 544), (689, 550), (700, 585)], 7, 3),
    ('BambooHuskDark', 4, (836, 330),
     [(828, 329), (819, 334), (812, 342), (802, 349), (783, 360), (763, 372), (748, 382), (726, 390), (704, 396),
      (682, 402), (660, 408), (638, 416), (616, 424), (594, 432), (584, 436), (565, 455), (590, 490), (615, 520),
      (645, 550), (675, 575), (700, 580)],
     [(834, 342), (828, 364), (822, 386), (816, 408), (810, 444), (808, 480), (806, 504), (800, 535), (790, 560)],
     6, 2),
    ('BambooSheathYellow', 4, (598, 198),
     [(587, 202), (568, 214), (549, 230), (530, 245), (514, 262), (502, 276), (490, 300), (485, 320)],
     [(596, 211), (588, 220), (580, 230), (572, 239), (568, 249), (559, 260), (549, 266), (539, 272), (530, 279),
      (520, 286), (510, 293), (499, 294), (495, 315)], 4, 2),
    ('BambooHuskTan', 3, (700, 171),
     [(696, 176), (686, 182), (677, 188), (667, 196), (658, 202), (648, 208), (638, 216), (629, 222), (619, 228),
      (609, 234), (599, 238), (589, 244), (579, 248), (568, 252), (545, 257), (515, 275), (495, 290), (478, 310),
      (472, 335), (480, 360), (505, 392), (540, 425), (565, 452), (600, 458), (660, 432), (720, 415)],
     [(706, 178), (706, 190), (704, 202), (704, 214), (706, 226), (706, 238), (708, 250), (717, 258), (724, 262),
      (722, 275), (726, 286), (732, 296), (736, 306), (740, 317), (746, 327), (754, 334), (754, 345), (754, 357),
      (759, 368), (762, 371), (765, 397), (740, 415)], 6, 3),
    ('BambooSheathYellow', 1, (719, 76),
     [(712, 84), (700, 104), (686, 123), (670, 142), (652, 156), (632, 170), (614, 186), (598, 203), (585, 215),
      (580, 240), (610, 255), (650, 232), (690, 200)],
     [(726, 84), (728, 95), (728, 108), (723, 118), (714, 126), (710, 137), (708, 148), (704, 159), (700, 170),
      (697, 192)], 5, 2),
    ('BambooTipGreen', 2, (852, 186),
     [(836, 186), (827, 190), (820, 200), (810, 206), (800, 212), (790, 218), (780, 224), (770, 228), (760, 232),
      (750, 239), (742, 248), (734, 256), (725, 262), (707, 280), (710, 305), (722, 330), (735, 355), (745, 385),
      (770, 393), (795, 380)],
     [(850, 197), (846, 208), (841, 218), (836, 229), (832, 240), (828, 251), (826, 262), (823, 274), (822, 285),
      (822, 297), (822, 310), (820, 322), (820, 334), (817, 358), (805, 372)], 5, 2),
    ('BambooTipGreen', 1, (866, 93),
     [(858, 86), (848, 89), (836, 93), (829, 96), (822, 106), (818, 117), (818, 129), (818, 141), (820, 153),
      (826, 162), (831, 166), (830, 195)],
     [(860, 103), (855, 114), (850, 124), (844, 134), (838, 143), (834, 154), (832, 166), (830, 178), (836, 196)],
     4, 1),
    ('BambooBud', 0, (827, 42),
     [(802, 61), (782, 70), (762, 81), (745, 94), (728, 108), (708, 125), (695, 150), (688, 175), (690, 210),
      (690, 240), (702, 265), (725, 278), (760, 262), (800, 238), (838, 212)],
     [(828, 60), (829, 80), (829, 96), (840, 112), (838, 135), (842, 160), (848, 195), (845, 210)], 5, 2))


BAMBOO_PEEL = ((901, 1013), (1065, 350), 0.38)   # the peeled shoot: base centre and tip (art px), and how far its


BAMBOO_PEEL_PROFILE = [   # share of the way from the base to the tip, radius (art px), shift to the right (art px)
    (0.04, 251, 0), (0.08, 259, 0), (0.12, 274, -9), (0.16, 280, -12), (0.2, 273, -7), (0.24, 265, -5), (0.28, 256, -5),
    (0.32, 246, -2), (0.36, 239, 0), (0.4, 226, -2), (0.44, 217, -1), (0.48, 205, 2), (0.52, 195, 2), (0.56, 184, -2),
    (0.6, 174, -1), (0.64, 162, 1), (0.68, 148, -1), (0.72, 138, -1), (0.76, 124, 1), (0.8, 109, -1), (0.84, 97, -1),
    (0.88, 85, -1), (0.92, 62, 3), (0.96, 36, 2), (0.985, 16, 0)]


BAMBOO_PEEL_RINGS = (0.25, 0.38, 0.56, 0.71, 0.9)   # where each layer of the peeled shoot ends over the next


BAMBOO_SLICES = (   # two pieces of shoot cut along their axis: tip, the two sides of the cut face from the tip to
    # its broad end (art px), the cut face's tilt and which way (rad), how deep the rounded back is (times the half
    # width), and the chambers on the cut face (art px: centre, length, width, slant in degrees)
    ((296, 1070),
     [(286, 1047), (286, 1025), (298, 993), (326, 956), (361, 922), (399, 894), (439, 868), (480, 846), (520, 826),
      (553, 814), (595, 796), (604, 800)],
     [(420, 1062), (540, 1057), (620, 1050), (700, 1035)], 0.25, 1.69, 1.19,
     ((581, 913, 63, 22, 151), (523, 964, 72, 17, 142), (496, 898, 46, 19, 133), (392, 972, 61, 17, 130),
      (445, 925, 32, 15, 131))),
    ((957, 1127),
     [(938, 1089), (914, 1064), (888, 1040), (860, 1018), (832, 998), (802, 980), (772, 962), (742, 946), (712, 928),
      (682, 913), (662, 902), (639, 894)],
     [(879, 1140), (792, 1135), (705, 1122), (618, 1109), (544, 1083)], 0.0, 1.25, 1.11,
     ((724, 1039, 92, 29, 131), (674, 1015, 105, 24, 139), (771, 1071, 56, 22, 139), (632, 963, 73, 19, 122),
      (658, 978, 89, 18, 134), (808, 1089, 35, 18, 135))))


BB_STEP = 0.0008   # how much nearer the viewer each level of sheath lies than the one under it


BB_TIP = 0.07     # how far short of its tip (a share of its length) a sheath's cage ends: the tip comes out round


class BbCanal:
    """A canal (union of spheres) through art control points (u, v, r), its centre line at one depth, the lowest
    sphere resting on the table; and where on it, or on its silhouette carried on out sideways, the art shows a
    pixel."""

    def __init__(self, at, uv, S, ctrl):
        self.at, self.uv, self.S = at, uv, S
        dense = pa_spline(ctrl, step=5.0)
        c, s_ = math.cos(ART_EL), math.sin(ART_EL)
        u, v, r = dense[0]
        y_c = at(u, v, r / S).y
        self.cs = [at(u, v, (at(u, v, 0.0).y - y_c) * s_ / c) for u, v, _ in dense]
        self.rs = [r / S for _, _, r in dense]
        self.view = Vector((0.0, -c, s_))
        self.px = [uv(q) for q in self.cs]

    def surface(self, pix):
        """The point the art shows at pixel pix and the outward normal there: on the canal nearest the viewer, or,
        beyond its silhouette, level with the nearest point of the silhouette, as if it ran on out sideways."""
        o = self.at(pix[0], pix[1], 0.0)
        d = self.view
        best = None
        for k, (c, R) in enumerate(zip(self.cs, self.rs)):
            w = o - c
            b = d.dot(w)
            disc = b * b - (w.dot(w) - R * R)
            if disc >= 0 and (best is None or -b + math.sqrt(disc) > best[0]):
                best = (-b + math.sqrt(disc), k)
        if best is not None:
            P = o + d * best[0]
            return P, (P - self.cs[best[1]]).normalized()
        k = min(range(len(self.cs)), key=lambda k: math.hypot(pix[0] - self.px[k][0], pix[1] - self.px[k][1])
                - self.rs[k] * self.S)
        cx, cy = self.px[k]
        side = self.at(pix[0], pix[1], 0.0) - self.at(cx, cy, 0.0)   # that way in the picture, square to the view
        side = (side - d * side.dot(d)).normalized()
        Q = self.cs[k] + side * self.rs[k]
        return pa_on_ray(self.at, pix[0], pix[1], Q), side


def bb_core(p, C, mat, n=12, rings=18):
    """The shoot under its sheaths, a little inside them: the canal C as a finished smooth tube, rounded at both
    ends."""
    m = len(C.cs)
    idx = [round(i * (m - 1) / (rings - 1)) for i in range(rings)]
    tmp = bmesh.new()
    ring_vs = []
    for i in idx:
        k = max(1, min(m - 2, i))
        t = (C.cs[k + 1] - C.cs[k - 1]).normalized()
        a = pa_normal_to(t)
        b = t.cross(a)
        r = max(0.3 * C.rs[i], C.rs[i] * 0.95 - 0.0008)
        if i in (0, m - 1):   # the ends: a ring pulled in, then the pole
            r *= 0.75
        ring_vs.append([tmp.verts.new(C.cs[i] + (a * math.cos(2 * math.pi * j / n) + b * math.sin(2 * math.pi * j / n)) * r)
                        for j in range(n)])
    t0 = (C.cs[1] - C.cs[0]).normalized()
    t1 = (C.cs[-1] - C.cs[-2]).normalized()
    poles = [tmp.verts.new(C.cs[0] - t0 * C.rs[0] * 0.95), tmp.verts.new(C.cs[-1] + t1 * C.rs[-1] * 0.9)]
    for ra, rb in zip(ring_vs, ring_vs[1:]):
        for j in range(n):
            tmp.faces.new((ra[j], ra[(j + 1) % n], rb[(j + 1) % n], rb[j]))
    for pole, ring, flip in ((poles[0], ring_vs[0], True), (poles[1], ring_vs[-1], False)):
        for j in range(n):
            f = (ring[j], ring[(j + 1) % n], pole)
            tmp.faces.new(f[::-1] if flip else f)
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)


def bb_peeled(p, at, uv, S, n=20):
    """The peeled shoot as a finished lathe round its axis, leaning as the art draws it and standing on its flat
    base with a rounded rim; its layers end in shallow rounded grooves, as the art's lines across it."""
    (bu, bv), (tu, tv), cos_v = BAMBOO_PEEL
    view = Vector((0.0, -math.cos(ART_EL), math.sin(ART_EL)))
    r_base = BAMBOO_PEEL_PROFILE[0][1] / S

    def axis(zt, zb):
        B, T = at(bu, bv, zb), at(tu, tv, zt)
        return B, T, (T - B).normalized()
    zb = r_base
    lo, hi = 0.0, 0.5
    for _ in range(50):   # how high the tip stands: the axis leaning back until it faces the viewer as the art's does
        zt = (lo + hi) / 2
        lo, hi = (zt, hi) if axis(zt, zb)[2].dot(view) < cos_v else (lo, zt)
    for _ in range(3):    # the lowest point of the base rim on the table
        B, T, t = axis(zt, zb)
        zb += r_base * math.sqrt(max(0.0, 1 - t.z * t.z)) - zb + 0.0005
        B2, T2, t2 = axis(zt, zb)
    B, T, t = axis(zt, zb)
    H = (T - B).length
    side = t.cross(view).normalized()
    side = side if side.x > 0 else -side            # to the right in the picture, square to the axis
    a = pa_normal_to(t)
    b = t.cross(a)
    prof = [(0.0, 0.0, 0.0), (0.0, BAMBOO_PEEL_PROFILE[0][1] - 18, 0), (0.008, BAMBOO_PEEL_PROFILE[0][1] - 4, 0)]
    for f, r, sh in BAMBOO_PEEL_PROFILE:
        for fr in BAMBOO_PEEL_RINGS:   # a groove where a layer ends
            if prof[-1][0] < fr - 0.015 <= f:
                rr = r + (prof[-1][1] - r) * (f - fr) / max(f - prof[-1][0], 1e-9)
                prof += [(fr - 0.012, rr + 1, sh, 'BambooFlesh'), (fr - 0.004, rr - 7, sh, 'BambooRing'),
                         (fr + 0.006, rr + 3, sh, 'BambooRing')]
        if f > prof[-1][0] + 0.004:   # (a point the groove has passed would fold the surface back on itself)
            prof.append((f, r, sh))
    prof.append((1.0, 0.0, 0.0))
    tmp = bmesh.new()
    rings, mats = [], []
    for item in prof:
        f, r, sh = item[:3]
        c = B + t * (f * H) + side * (sh / S)
        if r <= 0:
            rings.append([tmp.verts.new(c)])
        else:
            rings.append([tmp.verts.new(c + (a * math.cos(2 * math.pi * j / n) + b * math.sin(2 * math.pi * j / n)) * (r / S))
                          for j in range(n)])
        mats.append(item[3] if len(item) > 3 else 'BambooFlesh')
    faces = {}
    for ra, rb, m in zip(rings, rings[1:], mats[1:]):
        for j in range(n):
            if len(ra) == 1:
                f_ = tmp.faces.new((ra[0], rb[(j + 1) % n], rb[j]))
            elif len(rb) == 1:
                f_ = tmp.faces.new((ra[j], ra[(j + 1) % n], rb[0]))
            else:
                f_ = tmp.faces.new((ra[j], ra[(j + 1) % n], rb[(j + 1) % n], rb[j]))
            faces[f_] = m
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    by_mat = [faces[f_] for f_ in tmp.faces]
    vmap = {v: p.bm.verts.new(v.co) for v in tmp.verts}
    for f_, m in zip(tmp.faces, by_mat):
        p.bm.faces.new([vmap[v] for v in f_.verts]).material_index = p._mi(m)
    tmp.free()


def bb_slice(p, at, tip, side_a, side_b, tilt, toward, depth, chambers, others=None, nr=6, nc=5, margin=0.003):
    """A piece of shoot cut along its axis, lying with the cut face up as the art has it: the art's outline of the
    cut face laid on a plane tilted `tilt` toward `toward`, a half-round back under it `depth` times its half-width
    deep, every edge rounded, resting on the table; the chambers as shallow darker ovals on the cut face. The art
    draws the slices in front of the shoots, so the slice is sheared along the line of sight (which the art cannot
    see) just enough that it leans up in front of everything in `others` (a BVHTree), as if propped against it.
    A soft cage: build it inside p.soft()."""
    view = Vector((0.0, -math.cos(ART_EL), math.sin(ART_EL)))
    n = Vector((math.sin(tilt) * math.sin(toward), -math.sin(tilt) * math.cos(toward), math.cos(tilt)))
    ea, eb = [tuple(tip)] + list(side_a), [tuple(tip)] + list(side_b)
    cu = sum(q[0] for q in ea + eb) / len(ea + eb)
    cv = sum(q[1] for q in ea + eb) / len(ea + eb)
    c = at(cu, cv, 0.02)
    F, Bk = [], []
    for j in range(nr + 1):   # rows from the broad end (j = 0) to just short of the tip
        b = 1 - j / nr * 0.97
        pa, pb = bb_polyline_at(ea, b), bb_polyline_at(eb, b)
        row = [pa_on_plane(at, pa[0] + (pb[0] - pa[0]) * i / nc, pa[1] + (pb[1] - pa[1]) * i / nc, c, n)
               for i in range(nc + 1)]
        hw = (row[-1] - row[0]).length / 2
        F.append(row)
        Bk.append([q - n * (depth * hw * (math.sin(math.pi * i / nc) ** 0.7 + 0.15)) for i, q in enumerate(row)])
    dz = -min(q.z for row in F + Bk for q in row)
    shift = view * (dz / math.sin(ART_EL))   # along the line of sight onto the table: the art still shows it so
    F = [[q + shift for q in row] for row in F]
    Bk = [[q + shift for q in row] for row in Bk]
    up = Vector((0.0, math.sin(ART_EL), math.cos(ART_EL)))   # up in the picture
    h0 = min(q.dot(up) for row in F + Bk for q in row)
    k = 0.0
    if others is not None:   # how far up the line of sight each point must come to lie in front of the others
        for q in [q for row in F for q in row]:
            hit = others.ray_cast(q + view * 0.5, -view)
            if hit[0] is not None and (hit[0] - q).dot(view) > -margin and q.dot(up) - h0 > 0.004:
                k = max(k, ((hit[0] - q).dot(view) + margin) / (q.dot(up) - h0))

    def lean(q):
        return q + view * (k * (q.dot(up) - h0))
    tmp = bmesh.new()
    Fv = [[tmp.verts.new(lean(q)) for q in row] for row in F]
    Bv = [[tmp.verts.new(lean(q)) for q in row] for row in Bk]
    mats = {}
    for j in range(nr):
        for i in range(nc):
            mats[tmp.faces.new((Fv[j][i], Fv[j][i + 1], Fv[j + 1][i + 1], Fv[j + 1][i]))] = 'BambooCut'
            mats[tmp.faces.new((Bv[j][i], Bv[j + 1][i], Bv[j + 1][i + 1], Bv[j][i + 1]))] = 'BambooFlesh'
    loop = ([(0, i) for i in range(nc)] + [(j, nc) for j in range(nr)] + [(nr, i) for i in range(nc, 0, -1)]
            + [(j, 0) for j in range(nr, 0, -1)])
    for (pj, pi), (qj, qi) in zip(loop, loop[1:] + loop[:1]):
        f_ = tmp.faces.new((Fv[pj][pi], Bv[pj][pi], Bv[qj][qi], Fv[qj][qi]))
        mats[f_] = 'BambooCut' if pj == qj == 0 else 'BambooFlesh'   # the broad end is cut too
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    pa_true(tmp, iters=8)
    order = [mats[f] for f in tmp.faces]
    vmap = {v: p.bm.verts.new(v.co) for v in tmp.verts}
    for f, m in zip(tmp.faces, order):
        p.bm.faces.new([vmap[v] for v in f.verts]).material_index = p._mi(m)
    tmp.free()
    face_c = c + shift
    for (u, v, ln, wd, ang) in chambers:   # flat ovals on the cut face, drawn as the art has them: soft cages
        a_ = math.radians(ang)
        ring = []
        for j in range(6):   # an oval of art pixels laid on the cut face, made true so softening keeps its size
            t = 2 * math.pi * j / 6
            du, dv = 0.8 * ln * math.cos(t), 0.8 * wd * math.sin(t)
            ring.append(lean(pa_on_plane(at, u + du * math.cos(a_) - dv * math.sin(a_),
                                         v + du * math.sin(a_) + dv * math.cos(a_), face_c, n)))
        m = sum(ring, Vector()) / 6
        nn = (ring[1] - ring[4]).cross(ring[0] - ring[3]).normalized()
        nn = nn if nn.dot(view) > 0 else -nn
        tmp = bmesh.new()
        # a low dome whose rim lies under the cut face, so only its top shows, as an oval the art's size; the outline
        # pass (a hull 1.2 mm out) then stays under the face instead of drawing a dark rim round it
        rv = [tmp.verts.new(q - nn * 0.0006) for q in ring]
        top, bot = tmp.verts.new(m + nn * 0.001), tmp.verts.new(m - nn * 0.0015)
        for j in range(6):
            tmp.faces.new((rv[j], rv[(j + 1) % 6], top))
            tmp.faces.new((rv[(j + 1) % 6], rv[j], bot))
        tmp.normal_update()
        bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
        pa_true(tmp, iters=8)
        p._commit(tmp, 'BambooChamber')


def bb_polyline_at(poly, b):
    """The point a share b of the way along the polyline poly (by length)."""
    L = pa_lengths([Vector((u, v, 0.0)) for u, v in poly])
    t = b * L[-1]
    j = next((i for i in range(len(L) - 1) if L[i + 1] >= t), len(L) - 2)
    f = (t - L[j]) / max(L[j + 1] - L[j], 1e-9)
    return (poly[j][0] + (poly[j + 1][0] - poly[j][0]) * f, poly[j][1] + (poly[j + 1][1] - poly[j][1]) * f)


def bb_inside(poly, q):
    """How far pixel q lies inside the closed polygon poly (px; negative outside)."""
    inside, d = False, None
    for (ax, ay), (bx, by) in zip(poly, poly[1:] + poly[:1]):
        if (ay > q[1]) != (by > q[1]) and q[0] < ax + (q[1] - ay) * (bx - ax) / (by - ay):
            inside = not inside
        ex, ey = bx - ax, by - ay
        f = max(0.0, min(1.0, ((q[0] - ax) * ex + (q[1] - ay) * ey) / max(ex * ex + ey * ey, 1e-9)))
        dd = math.hypot(q[0] - ax - ex * f, q[1] - ay - ey * f)
        d = dd if d is None else min(d, dd)
    return d if inside else -d


def bb_sheath(p, C, mat, tip, left, right, nr, nc, lift, covers=(), thick=0.0016):
    """A sheath with real thickness as a soft cage: the art's outline (the tip and its two edges down from it) laid
    on the canal C where the art shows it, brought `lift` nearer the viewer so that it lies over the sheaths under
    it; softened, its rim comes out rounded all round and its tip a rounded point. Where the sheaths over it (their
    outlines `covers`) hide it, it sinks well under them. Build it inside p.soft()."""
    edges = [[tuple(tip)] + list(e) for e in (left, right)]
    grid = []   # rows of art pixels from the bottom (j = 0) to just short of the tip (j = nr), columns left to right
    for j in range(nr + 1):
        b = 1 - j / nr * (1 - BB_TIP)
        a, c = bb_polyline_at(edges[0], b), bb_polyline_at(edges[1], b)
        grid.append([(a[0] + (c[0] - a[0]) * i / nc, a[1] + (c[1] - a[1]) * i / nc) for i in range(nc + 1)])
    tmp = bmesh.new()
    Ov, Iv = [], []
    for row in grid:
        Ov.append([])
        Iv.append([])
        for pix in row:
            P, nrm = C.surface(pix)
            hid = max([bb_inside(poly, pix) for poly in covers] + [-1.0])
            w = pa_smooth(hid / 25.0)
            P = P + C.view * (lift * (1 - w) - 0.0015 * w)
            Ov[-1].append(tmp.verts.new(P))
            Iv[-1].append(tmp.verts.new(P - nrm * thick))
    for j in range(nr):
        for i in range(nc):
            tmp.faces.new((Ov[j][i], Ov[j][i + 1], Ov[j + 1][i + 1], Ov[j + 1][i]))
            tmp.faces.new((Iv[j][i], Iv[j + 1][i], Iv[j + 1][i + 1], Iv[j][i + 1]))
    loop = ([(0, i) for i in range(nc)] + [(j, nc) for j in range(nr)] + [(nr, i) for i in range(nc, 0, -1)]
            + [(j, 0) for j in range(nr, 0, -1)])
    for (pj, pi), (qj, qi) in zip(loop, loop[1:] + loop[:1]):
        tmp.faces.new((Ov[pj][pi], Iv[pj][pi], Iv[qj][qi], Ov[qj][qi]))
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    pa_true(tmp, iters=8)
    p._commit(tmp, mat)


def bamboo(col):
    """笋 as the art has it: a fat bamboo shoot in its sheaths leaning to the right, the sheaths wrapping it in turn,
    brown below, yellow and green toward the bud, each with real thickness, rounded edges and a rounded point
    standing proud of the shoot; a peeled pale shoot in front on the right, its layers stepping out toward its base;
    and two half-moon slices in front. Laid out on 笋.png (65 px to the centimetre)."""
    p = Part()
    S, u0, v0 = BAMBOO_ART
    at, uv = art_px(S, u0, v0), art_uv(S, u0, v0)
    C = BbCanal(at, uv, S, BAMBOO_CORE)
    bb_core(p, C, 'BambooHuskDark')
    outlines = [(level, [tuple(tip)] + list(left) + list(reversed(right)))
                for _, level, tip, left, right, _, _ in BAMBOO_SHEATHS]
    with p.soft():
        for mat, level, tip, left, right, nr, nc in BAMBOO_SHEATHS:
            bb_sheath(p, C, mat, tip, left, right, nr, nc,
                      lift=0.0006 + level * BB_STEP, covers=[poly for lv, poly in outlines if lv > level])
    bb_peeled(p, at, uv, S)
    for tip, side_a, side_b, tilt, toward, depth, chambers in BAMBOO_SLICES:   # the back one first
        others = BVHTree.FromBMesh(p.bm)
        v1 = len(p.bm.verts)
        with p.soft():
            bb_slice(p, at, tip, side_a, side_b, tilt, toward, depth, chambers, others)
        pb_lift(p, v1)   # softened, its rounded back bulges under the table: up onto it
    return p.finish('SM_bamboo', col, sharp=None)


PALETTE.update({
    'PerillaArtLeaf': ('#a05a88', '#78406a'),    # 紫苏's leaves under the art's own colours (pv_traced)
    'PerillaArtStalk': ('#8a8a4a', '#666632'),   # the bundle of stalks
    'PerillaArtTwine': ('#e6c890', '#c0a068'),   # the string round it
})
GLOSS.update({'PerillaArtLeaf': 0.15, 'PerillaArtStalk': 0.1, 'PerillaArtTwine': 0.0})
VIVID.update({'PerillaArtLeaf': 0.5, 'PerillaArtStalk': 0.5, 'PerillaArtTwine': 0.4})
VTINT.update(dict.fromkeys(('PerillaArtLeaf', 'PerillaArtStalk', 'PerillaArtTwine'), 1.0))
DETAIL.update({'PerillaArtLeaf': ('food_leafvein', 22, '#d89ac0', 0.35, 0.25),   # the fine veins between the art's
               'PerillaArtStalk': ('food_fiber', 24, '#b0b070', 0.3, 0.15)})


def perilla(col):
    """紫苏 traced off its art (trace_perilla.py): a bunch of serrated perilla leaves, purple washed with olive green,
    fanning up and to the right from a bundle of stalks tied with string, their cut ends at the lower left. Every piece
    covers exactly what the art paints, in the art's own colours, with its pink midribs and veins painted on."""
    p = Part()
    pv_traced(p, 'perilla')
    return pb_finish(p, 'SM_perilla', col, pb_recentre(p))


MUSH_ART = (8000, 628, 811)   # 菌菇.png: px per metre, the origin's pixel (under the middle of the three)


# The three shiitake fitted to their outlines in the art (art px): where the centre of the cap's rim shows (u, v),
# the cap's radius, the dome's height, the axis's tilt from upright and its heading (rad, 0 = toward the viewer),
# how deep the rolled rim reaches under the dome, the gills' share of the radius, the stem's radius at the cap,
# its length, its bend off the axis (two ways), the cap's squash across, and the stem's radius at its cut end.
MUSH_FIT = {
    'back': [721.0, 442.4, 332.6, 165.4, 0.07, 0.94, 110, 0.9, 70, 140, 0.0, 0.0, 1.0, 70],
    'left': [376.4, 751.0, 335.0, 226.6, 1.52, -2.98, 46.3, 0.841, 95, 291.4, -0.487, -0.444, 0.97, 115],
    'right': [931.4, 818.0, 288.0, 227.6, 0.5, 0.84, 82.8, 0.917, 70, 140, 0.0, 0.0, 1.015, 70]}


MUSH_CUTS = {   # the cross cut in the cap: the art's ends of its two strokes (art px) and their width there (px)
    'back': (((598, 264), (932, 414)), ((802, 231), (640, 447)), 54),
    'right': (((878, 584), (1150, 862)), ((1072, 604), (863, 852)), 58)}


MU_GILL_LINES = 16   # the dark lines between the gills on the cap that lies tipped over


def mu_frame(th, ph):
    """The axis of a mushroom tilted th from upright toward heading ph, and two unit vectors square to it."""
    a = Vector((math.sin(th) * math.sin(ph), -math.sin(th) * math.cos(ph), math.cos(th)))
    t = Vector((0.0, 0.0, 1.0)).cross(a)
    t = t.normalized() if t.length > 1e-6 else Vector((1.0, 0.0, 0.0))
    return a, t, a.cross(t)


def mu_cage(p, rings, poles, mats):
    """Like pa_cage, but with a material for each band of faces: mats[0] for the fan round the first pole, mats[i]
    between rings i - 1 and i, mats[-1] for the last pole's fan; a list there gives one per column of faces."""
    tmp = bmesh.new()
    vr = [[tmp.verts.new(Vector(q)) for q in ring] for ring in rings]
    n = len(vr[0])
    fm = {}
    for i, (ra, rb) in enumerate(zip(vr, vr[1:])):
        for k in range(n):
            f = tmp.faces.new((ra[k], ra[(k + 1) % n], rb[(k + 1) % n], rb[k]))
            m = mats[i + 1]
            fm[f] = m[k] if isinstance(m, list) else m
    for pole, ring, m in ((poles[0], vr[0], mats[0]), (poles[1], vr[-1], mats[-1])):
        pv = tmp.verts.new(Vector(pole))
        for k in range(n):
            f = tmp.faces.new((ring[k], ring[(k + 1) % n], pv))
            fm[f] = m[k] if isinstance(m, list) else m
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    pa_true(tmp)
    order = [fm[f] for f in tmp.faces]
    vmap = {v: p.bm.verts.new(v.co) for v in tmp.verts}
    for f, m in zip(tmp.faces, order):
        p.bm.faces.new([vmap[v] for v in f.verts]).material_index = p._mi(m)
    tmp.free()


def mu_dome_hit(o, d, R, q2, H):
    """Where the ray o + s d (local coordinates of a cap) first meets its dome (x/R)^2 + (y/(R q2))^2 + (z/H)^2 = 1,
    z >= 0; None if it misses."""
    sc = Vector((1 / R, 1 / (R * q2), 1 / H))
    O, D = Vector(o) * sc, Vector(d) * sc
    a, b, c = D.dot(D), 2 * O.dot(D), O.dot(O) - 1
    disc = b * b - 4 * a * c
    if disc < 0:
        return None
    for s in sorted(((-b - math.sqrt(disc)) / (2 * a), (-b + math.sqrt(disc)) / (2 * a))):
        q = Vector(o) + Vector(d) * s
        if q.z >= 0:
            return q
    return None


def mushroom(col):
    """菌菇 as the art has it: three plump shiitake with rounded brown caps, their rims rolled under; the one at the
    back and the one in front on the right each scored on top with a cream cross, the one on the left tipped over
    to show its pale gills, lined from the stem out to the brown rim, and its thick stem with a pale cut end. Every
    piece a soft cage, rounded all over. Laid out on 菌菇.png (80 px to the centimetre)."""
    p = Part()
    S, u0, v0 = MUSH_ART
    at = art_px(S, u0, v0)
    view = Vector((0.0, -math.cos(ART_EL), math.sin(ART_EL)))
    pieces = {}
    for name in ('back', 'left', 'right'):
        u, v, R, H, th, ph, T, k, rs, Ls, b1, b2, q2, re = MUSH_FIT[name]
        R, H, T, rs, Ls, re = R / S, H / S, T / S, rs / S, Ls / S, re / S
        a, t, n = mu_frame(th, ph)
        C = at(u, v, 0.1)   # the rim's centre, somewhere on the line of sight through (u, v): moved onto the table below
        m_cap = 2 * MU_GILL_LINES if name == 'left' else 16
        even = [2 * math.pi * j / m_cap for j in range(m_cap)]
        step = 2 * math.pi / MU_GILL_LINES   # on the gills, the columns in pairs: a narrow one for each line between
        bunched = [i * step + f * step for i in range(MU_GILL_LINES) for f in (-0.1, 0.18)] if name == 'left' else even

        def ring(r, z, psis, sq=q2, C=C, a=a, t=t, n=n):
            return [C + t * (r * math.cos(s)) + n * (r * sq * math.sin(s)) + a * z for s in psis]
        prof = [(0.5 * R, 0.866 * H), (0.866 * R, 0.5 * H), (R, 0.0), (R * (k + 0.75 * (1 - k)), -0.55 * T),
                (R * k * 1.02, -T), (R * k * 0.9, -0.78 * T), (R * k * 0.84, -0.72 * T), (R * k * 0.55, -0.58 * T),
                (R * k * 0.2, -0.48 * T)]
        rings = [ring(r, z, even if i < 6 else bunched) for i, (r, z) in enumerate(prof)]
        poles = (C + a * H, C - a * (0.46 * T))
        gill = 'ShiitakeFlesh'
        if name == 'left':
            gill = [('ShiitakeFlesh' if j % 2 else 'ShiitakeGill') for j in range(m_cap)]
        mats = ['ShiitakeCap'] * 6 + ['ShiitakeFlesh'] + [gill] * 3   # the top's fan, 5 bands of dome and rolled
        # rim, a plain band where the columns close up in pairs, 2 bands of gills and their fan
        sd = (-a + t * b1 + n * b2).normalized()
        base = C - a * (0.6 * T)
        e1 = pa_normal_to(sd)
        e2 = sd.cross(e1)
        m_ = 12 if name == 'left' else 8
        sring = lambda c, r: [c + (e1 * math.cos(2 * math.pi * j / m_) + e2 * math.sin(2 * math.pi * j / m_)) * r
                              for j in range(m_)]
        srings = [sring(base + sd * (Ls * f), r) for f, r in ((0.0, rs * 0.9), (0.3, rs), (0.62, rs * 0.96),
                                                               (0.86, re * 0.88), (0.97, re), (1.0, re * 0.82))]
        spoles = (base - sd * (rs * 0.3), base + sd * (Ls * 1.0 + re * 0.03))
        smats = ['ShiitakeFlesh'] * 6 + ['ShiitakeCut']
        pieces[name] = (rings, poles, mats, srings, spoles, smats, (C, a, t, n, R, q2, H))
    for name, (rings, poles, mats, srings, spoles, smats, frame) in pieces.items():   # each onto the table
        low = min(q.z for ring in rings + srings for q in ring)
        low = min(low, min(q.z for q in poles + spoles))
        d = view * (-low / math.sin(ART_EL))
        rings = [[q + d for q in ring] for ring in rings]
        srings = [[q + d for q in ring] for ring in srings]
        poles = [q + d for q in poles]
        spoles = [q + d for q in spoles]
        C, a, t, n, R, q2, H = frame
        pieces[name] = (rings, poles, mats, srings, spoles, smats, (C + d, a, t, n, R, q2, H))
    with p.soft():
        for name, (rings, poles, mats, srings, spoles, smats, frame) in pieces.items():
            mu_cage(p, rings, poles, mats)
            mu_cage(p, srings, spoles, smats)
    p.bm.normal_update()
    caps = BVHTree.FromBMesh(p.bm)   # the cuts go on the caps as softened
    with p.soft():
        for name, cut in MUSH_CUTS.items():
            mu_cross(p, at, pieces[name][6], *cut, S, caps)
    return p.finish('SM_mushroom', col, sharp=None)


def mu_cross(p, at, frame, stroke_a, stroke_b, width, S, caps):
    """The cross cut on top of a cap: two cream strokes through the dome's top, each from one of the art's ends over
    the top to the other, widest where they cross and tapering to rounded points. Each stroke is a soft cage whose
    edges lie just under the cap and whose crest just over it (the cap as softened: the BVHTree caps), so only a band
    the art's width shows and the outline pass stays under the cap."""
    C, a, t, n, R, q2, H = frame
    view = Vector((0.0, -math.cos(ART_EL), math.sin(ART_EL)))
    M = Matrix((t, n, a)).transposed()   # local -> world rotation
    Mi = M.transposed()

    def local_end(px):
        o = Mi @ (at(px[0], px[1], 0.3) - C)
        d = Mi @ (-view)
        hit = mu_dome_hit(o, d, R, q2, H)
        if hit is None:   # beyond the dome as the art draws it: the nearest point of its rim
            q = o + d * (-o.dot(d) / d.dot(d))
            hit = Vector((q.x, q.y, 0.0))
        x, y = hit.x / R, hit.y / (R * q2)
        return math.atan2(y, x), math.acos(max(-1.0, min(1.0, hit.z / H)))

    def surf(psi, q, lift):   # the point of the cap over the dome's (heading psi, q from the top), lifted along its normal
        lp = Vector((R * math.sin(q) * math.cos(psi), R * q2 * math.sin(q) * math.sin(psi), H * math.cos(q)))
        nl = M @ Vector((lp.x / (R * R), lp.y / (R * q2) ** 2, lp.z / (H * H))).normalized()
        P = C + M @ lp
        hit = caps.ray_cast(P + nl * 0.01, -nl, 0.02)
        if hit[0] is not None:
            P, nl = hit[0], (hit[1] if hit[1].dot(nl) > 0 else -hit[1]).normalized()
        return P + nl * lift, nl
    w = width / S
    for e0, e1 in (stroke_a, stroke_b):
        (p0, q0), (p1, q1) = local_end(e0), local_end(e1)
        path = [(p0, q0 * f) for f in (1.0, 0.68, 0.36)] + [(p0, 0.0)] + [(p1, q1 * f) for f in (0.36, 0.68, 1.0)]
        rings = []
        for i, wf in zip(range(1, 6), (0.68, 0.92, 1.0, 0.92, 0.68)):   # the ends close to points just under the cap
            P, nl = surf(*path[i], 0.0)
            along = (surf(*path[i + 1], 0.0)[0] - surf(*path[i - 1], 0.0)[0]).normalized()
            side = along.cross(nl).normalized()
            hw = wf * w   # the edges reach about twice as wide as the band that shows
            rings.append([P - nl * 0.0006 - side * hw, P + nl * 0.0007, P - nl * 0.0006 + side * hw,
                          P - nl * 0.0018])
        ends = (surf(p0, q0 * 1.04, -0.0004)[0], surf(p1, q1 * 1.04, -0.0004)[0])
        mu_cage(p, rings, ends, ['ShiitakeFlesh'] * 6)


def tomato_body(p, M, r, h, lobes=0.035):
    """A whole tomato r round and h high, flattened, its shoulders faintly lobed and a dimple on top where the calyx
    sits; placed by M (its base at the origin, axis up). A soft cage."""
    def lobed_side(q):
        f = max(0.0, min(1.0, (q.z / h - 0.35) / 0.4))
        k = 1 + lobes * math.cos(5 * math.atan2(q.y, q.x)) * f
        return Vector((q.x * k, q.y * k, q.z))
    prof = [(0.0, 0.03), (0.45, 0.0), (0.8, 0.12), (0.98, 0.38), (1.0, 0.5), (0.95, 0.68), (0.78, 0.86), (0.48, 0.97),
            (0.2, 0.97), (0.0, 0.9)]
    p.lathe([(r * a, h * b) for a, b in prof], 'TomatoRed', n=16, M=M, deform=lobed_side, close_ends=False)


TOMATO_TOP = [(0.0, 0.9), (0.2, 0.97), (0.48, 0.97), (0.78, 0.86), (0.95, 0.68), (1.0, 0.5)]   # (radius/r, z/h)


def tomato_top(f):
    """Height (share of h) of tomato_body()'s top at a share f of its radius."""
    for (r0, z0), (r1, z1) in zip(TOMATO_TOP, TOMATO_TOP[1:]):
        if f <= r1:
            return z0 + (z1 - z0) * (f - r0) / (r1 - r0)
    return TOMATO_TOP[-1][1]


def sepals(p, M, r, h, uv, tips, width=0.009, thick=0.0026, lift=0.0018):
    """A calyx on tomato_body(p, M, r, h): a sepal to each tip (art pixel u, v and how far it curls up off the skin),
    lying along the skin from the stalk, wide at the base, round-ended. Each sepal's direction round the stalk
    and its reach are found so that its tip lands on the art's tip."""
    def path(phi, reach, curl, k_max=5):
        pts, ups = [], []
        for k in range(k_max + 1):
            f = k / k_max
            rho = r * (0.06 + (reach - 0.06) * f)
            z = h * tomato_top(rho / r) + lift + curl * f ** 3
            out = 0.5 * curl * f ** 3
            pts.append(M @ Vector(((rho + out) * math.cos(phi), (rho + out) * math.sin(phi), z)))
            ups.append(M.to_3x3() @ Vector((math.cos(phi) * 0.7 * rho / r, math.sin(phi) * 0.7 * rho / r, 1.0)))
        return pts, ups
    for (u, v, curl) in tips:
        best = None
        for a in range(0, 360, 3):
            for reach in [0.3 + 0.025 * i for i in range(29)]:
                q = uv(path(math.radians(a), reach, curl, 1)[0][-1])
                e = (q[0] - u) ** 2 + (q[1] - v) ** 2
                if best is None or e < best[0]:
                    best = (e, math.radians(a), reach)
        pts, ups = path(best[1], best[2], curl)
        ribbon(p, pts, [width * (1.0 - 0.72 * (k / 5) ** 1.3) for k in range(6)], thick, 'CalyxGreen', ups=ups,
               sides=4)


def sector(p, W, r, rz, span, skin, flesh, rows=10, rim=0.0):
    """A wedge cut from a spheroid r round and rz long about its core (local z, placed by W): the skin from the cut
    face along local x (phi = 0) round to phi = span, and the two flat cut faces, their outer `rim` (a share of the
    way out) in the skin's colour like a tomato's wall. Supporting loops close to every
    edge keep it its full size when p.soft() rounds those edges. Build it inside p.soft()."""
    tmp = bmesh.new()
    fr = [0.0, 0.05, 0.25, 0.5, 0.75, 0.95, 1.0]           # across the skin, as shares of span
    rad = [0.06, 0.5] + ([1 - rim] if rim else []) + [0.94]   # out across each cut face, shares of the way to the skin
    ths = [0.0, 0.05] + [0.05 + 0.9 * k / (rows - 2) for k in range(1, rows - 2)] + [0.95, 1.0]
    top = tmp.verts.new(W @ Vector((0.0, 0.0, rz)))
    bottom = tmp.verts.new(W @ Vector((0.0, 0.0, -rz)))
    ring = [[top] * len(fr)]
    for t in ths[1:-1]:
        th = math.pi * t
        ring.append([tmp.verts.new(W @ Vector((r * math.sin(th) * math.cos(span * f), r * math.sin(th) * math.sin(span * f),
                                                rz * math.cos(th)))) for f in fr])
    ring.append([bottom] * len(fr))
    core = [top] + [tmp.verts.new(W @ Vector((0.0, 0.0, rz * math.cos(math.pi * t)))) for t in ths[1:-1]] + [bottom]
    faces_of = {}

    def face(vs, mat):
        vs = [v for k, v in enumerate(vs) if v not in vs[:k]]
        if len(vs) >= 3:
            faces_of[tmp.faces.new(vs)] = mat
    for i in range(len(ths) - 1):
        for j in range(len(fr) - 1):
            face((ring[i][j], ring[i + 1][j], ring[i + 1][j + 1], ring[i][j + 1]), skin)
    for j_edge in (0, len(fr) - 1):
        cols = [core] + [[core[i] if i in (0, len(ths) - 1) else
                          tmp.verts.new(core[i].co.lerp(ring[i][j_edge].co, f)) for i in range(len(ths))] for f in rad]             + [[ring[i][j_edge] for i in range(len(ths))]]
        for i in range(len(ths) - 1):
            for c in range(len(cols) - 1):
                vs = (cols[c][i], cols[c][i + 1], cols[c + 1][i + 1], cols[c + 1][i])
                face(vs if j_edge == 0 else vs[::-1], skin if rim and c >= len(cols) - 3 else flesh)
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    mats = [faces_of[f] for f in tmp.faces]
    vmap = {v: p.bm.verts.new(v.co) for v in tmp.verts}
    for f, m in zip(tmp.faces, mats):
        p.bm.faces.new([vmap[v] for v in f.verts]).material_index = p._mi(m)
    tmp.free()


def tomato(col):
    """番茄 as the art has it: a big tomato in front on the left and another behind it on the right, both leaning a
    little toward the viewer with curly green calyxes and stalks, and a quarter wedge lying in front on the right,
    its cut face up showing the flesh and seeds. Laid out on 番茄.png (88 px to the centimetre); none of the three
    passes into another."""
    p = Part()
    at, uv = art_px(8800, 650, 900), art_uv(8800, 650, 900)
    bodies = []
    for (cu, cv, r, h, tilt, side, yaw) in ((452, 700, 0.0395, 0.064, 0.36, 0.08, 0.2),
                                            (917, 514, 0.0335, 0.054, 0.2, 0.2, 1.0)):   # just clear of the first
        c = at(cu, cv, h / 2)
        M = Matrix.Translation(c) @ Matrix.Rotation(side, 4, 'Y') @ Matrix.Rotation(tilt, 4, 'X') \
            @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Translation((0.0, 0.0, -h / 2))
        bodies.append((M, r, h))
    for k, (M, r, h) in enumerate(bodies):   # leaning toward the viewer, each would dip its front into the table: it
        v1 = len(p.bm.verts)                  # comes up the line of sight onto it, its calyx and stalk with it
        with p.soft():
            tomato_body(p, M, r, h)
        bodies[k] = (Matrix.Translation(pb_lift(p, v1)) @ M, r, h)
    with p.soft():
        (ML, rl, hl), (MR, rr, hr) = bodies
        sepals(p, ML, rl, hl, uv, ((255, 415, 0.004), (350, 352, 0.012), (522, 350, 0.014), (700, 442, 0.006),
                                    (688, 638, 0.004), (392, 690, 0.002), (172, 602, 0.004)))
        sepals(p, MR, rr, hr, uv, ((837, 204, 0.016), (1037, 282, 0.006), (1177, 382, 0.004), (1109, 444, 0.004),
                                    (967, 394, 0.0), (875, 394, 0.002), (895, 312, 0.008)), width=0.0085)
        for (M, h, path, rad) in ((ML, hl, ((470, 522, 0.005), (474, 496, 0.009), (478, 474, 0.012)), 0.0062),
                                  (MR, hr, ((955, 312, 0.008), (937, 262, 0.016), (917, 214, 0.022), (899, 187, 0.024)),
                                   0.0042)):   # stalks, from the dimple up
            b = M @ Vector((0.0, 0.0, h * 0.9))
            pts = [b] + [at(u, v, b.z + dz) for u, v, dz in path]
            ribbon(p, pts, [rad * 2] * len(pts), rad * 1.8, 'CalyxGreen', sides=6)

    # the wedge: a quarter of a tomato (a little less, 75°), its cut face to the viewer as the art draws it, the rest
    # of it behind the face. Square to the line of sight it would pass into the big tomato that it overlaps in the
    # art, so the face is turned 23° up about the core, the skin showing under it as in the art, and its left end
    # 26° towards the viewer (lengthened so that it still spans the art's face): the wedge lies propped against the
    # big tomato, just clear of it. Then it is slid along the line of sight until it rests on the ground.
    r, rz, yaw, tip = 0.039, 0.0314, -0.45, 0.4
    toward = Vector((0.0, -math.cos(ART_EL), math.sin(ART_EL)))

    def face_pt(u, v):   # the point at pixel (u, v) on the plane square to the line of sight through the origin
        return at(u, v, math.cos(ART_EL) * (900 - v) / 8800)
    a1, a2, far = face_pt(600, 877), face_pt(1078, 650), face_pt(855, 1083)
    axis = (a2 - a1).normalized()
    out = far - a1
    out = (out - axis * out.dot(axis)).normalized()          # from the core out to the skin, across the cut face
    turn = Matrix.Rotation(yaw, 3, out)
    axis, normal = turn @ axis, turn @ toward
    turn = Matrix.Rotation(-tip, 3, axis)
    out, normal = turn @ out, turn @ normal
    rz /= math.cos(yaw)
    mid = (a1 + a2) / 2
    W = Matrix((out, -normal, axis)).transposed().to_4x4()   # local x: out across the face, y: behind it, z: the core
    W.translation = mid
    n0 = len(p.bm.verts)
    with p.soft():
        sector(p, W, r, rz, 1.3, 'TomatoRed', 'TomatoFlesh', rim=0.13)
    p.bm.verts.ensure_lookup_table()
    lift = -min(v.co.z for v in p.bm.verts[n0:])
    shift = toward * (lift / math.sin(ART_EL))
    for v in p.bm.verts[n0:]:
        v.co += shift
    mid = mid + shift
    with p.soft():   # seeds in their jelly, in a crescent round the core on the upper face
        R = Matrix((out, normal.cross(out), normal)).transposed()
        for (u, v) in ((755, 925), (792, 893), (840, 930), (878, 903), (920, 950), (970, 930), (1008, 885), (1025, 840),
                       (1045, 800), (1070, 855)):
            q = at(u, v, 0.0)
            q += toward * ((mid - q).dot(normal) / toward.dot(normal)) + normal * 0.0012   # along the line of sight onto it
            p.blob(q, 0.0042, 'TomatoSeed', squash=(1.5, 0.85, 0.35), segs=(5, 2), deform=lambda v, R=R: R @ v)
    pb_lift(p, 0)   # on the table, not a hair's breadth in it
    return p.finish('SM_tomato', col, sharp=None)


PA_SHRINK = {n: (2 + math.cos(2 * math.pi / n)) / 3 for n in range(3, 33)}   # a cage ring on the soft limit surface


def pa_spline(ctrl, step=2.0):
    """Dense samples (u, v, r) along a centripetal Catmull-Rom through control points (u, v, r) in art pixels, the
    radius linear between them: the curve the 2D fit to the art's regions used."""
    P = [tuple(float(x) for x in c) for c in ctrl]
    if len(P) < 2:
        return P
    ext = [tuple(2 * a - b for a, b in zip(P[0], P[1]))] + P + [tuple(2 * a - b for a, b in zip(P[-1], P[-2]))]

    def gap(a, b):
        return max(math.hypot(b[0] - a[0], b[1] - a[1]), 1e-3) ** 0.5
    out = []
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1], ext[i], ext[i + 1], ext[i + 2]
        t0 = 0.0
        t1 = t0 + gap(p0, p1)
        t2 = t1 + gap(p1, p2)
        t3 = t2 + gap(p2, p3)
        m = max(2, int(math.hypot(p2[0] - p1[0], p2[1] - p1[1]) / step))
        for k in range(m):
            t = t1 + (t2 - t1) * k / m

            def lerp(a, b, ta, tb):
                return [((tb - t) * x + (t - ta) * y) / (tb - ta) for x, y in zip(a, b)]
            a1, a2, a3 = lerp(p0, p1, t0, t1), lerp(p1, p2, t1, t2), lerp(p2, p3, t2, t3)
            c = lerp(lerp(a1, a2, t0, t2), lerp(a2, a3, t1, t3), t1, t2)
            c[2] = p1[2] + (p2[2] - p1[2]) * k / m
            out.append(tuple(c))
    out.append(P[-1])
    return out


def pa_lengths(pts):
    s = [0.0]
    for a, b in zip(pts, pts[1:]):
        s.append(s[-1] + (Vector(b) - Vector(a)).length)
    return s


def pa_normal_to(t, prev=None):
    """A unit vector square to t: `prev` carried over (parallel transport) when given, so that rings don't twist."""
    a = prev - t * prev.dot(t) if prev is not None else Vector((0.0, 0.0, 1.0)).cross(t)
    if a.length < 1e-6:
        a = Vector((0.0, 1.0, 0.0)).cross(t)
    return a.normalized()


def pa_canal(p, cs, rs, mat, sides=10, spacing=0.8, lo=0.003, hi=0.016, cap=3, ends=(True, True)):
    """A canal surface through sphere centres cs (dense, in order) with radii rs, as a soft cage: rings on the
    envelope's characteristic circles, spaced `spacing` × the local radius (between lo and hi), and each end closed
    by the cap of its last sphere (`cap` rings and a pole), or cut flat with a rounded rim ('flat'), or left open. Ring radii are raised to make up for what one level of
    p.soft() takes off, so the smoothed surface keeps the fitted size. Build it inside p.soft()."""
    cs = [Vector(c) for c in cs]
    n = len(cs)
    s = pa_lengths(cs)
    st = [0]
    while st[-1] < n - 1:
        i = st[-1]
        want = s[i] + min(hi, max(lo, spacing * rs[i]))
        j = i + 1
        while j < n - 1 and s[j] < want:
            j += 1
        if n - 1 - j > 0 and s[-1] - s[j] < 0.5 * min(hi, max(lo, spacing * rs[j])):
            j = n - 1
        st.append(j)

    def at_s(target):   # index of the sample nearest arc length target
        lo_, hi_ = 0, n - 1
        while hi_ - lo_ > 1:
            mid = (lo_ + hi_) // 2
            lo_, hi_ = (mid, hi_) if s[mid] < target else (lo_, mid)
        return lo_ if abs(s[lo_] - target) <= abs(s[hi_] - target) else hi_
    k_ring = 1.0 / PA_SHRINK[sides]
    rings = []   # (centre, radius, tangent)
    for i in st:
        h = max(min(hi, max(lo, spacing * rs[i])) * 0.5, 1e-4)
        a, b = at_s(s[i] - h), at_s(s[i] + h)
        if a == b:
            a, b = max(i - 1, 0), min(i + 1, n - 1)
        t = (cs[b] - cs[a]).normalized()
        dr = max(-0.85, min(0.85, (rs[b] - rs[a]) / max(s[b] - s[a], 1e-9)))
        rings.append((cs[i] - t * rs[i] * dr, rs[i] * math.sqrt(1 - dr * dr), t, dr))
    poles = [None, None]
    for e, (idx, sg) in enumerate(((0, -1.0), (-1, 1.0))):
        if not ends[e]:
            continue
        if ends[e] == 'flat':   # cut square: a flat face, its rim rounded over a fifth of the radius
            c, r, t, _ = rings[idx]
            w = 0.2 * r
            flat = [(c + t * sg * w * 0.5, r * 0.97, t, 0.0), (c + t * sg * w, r - w * 0.8, t, 0.0),
                    (c + t * sg * w, (r - w) * 0.5, t, 0.0)]
            poles[e] = c + t * sg * w
            rings = (flat[::-1] + rings) if e == 0 else (rings + flat)
            continue
        c, r, t, dr = cs[st[idx]], rs[st[idx]], rings[idx][2], rings[idx][3]
        beta0 = math.acos(max(-0.85, min(0.85, -sg * dr)))   # the characteristic circle's angle from the pole
        extra = []
        for k in range(1, cap):
            beta = beta0 * (1 - k / cap)
            extra.append((c + t * sg * r * math.cos(beta) * 1.02, r * math.sin(beta), t, 0.0))
        poles[e] = c + t * sg * r * 1.04
        rings = (extra[::-1] + rings) if e == 0 else (rings + extra)
    grid = []
    prev = None
    for c, r, t, _ in rings:
        a = pa_normal_to(t, prev)
        prev = a
        b = t.cross(a)
        grid.append([c + (a * math.cos(2 * math.pi * k / sides) + b * math.sin(2 * math.pi * k / sides)) * r * k_ring
                     for k in range(sides)])
    grid = pa_unsmooth(grid, poles)
    tmp = bmesh.new()
    vrings = [[tmp.verts.new(q) for q in ring] for ring in grid]
    for ra, rb in zip(vrings, vrings[1:]):
        for k in range(sides):
            tmp.faces.new((ra[k], ra[(k + 1) % sides], rb[(k + 1) % sides], rb[k]))
    for e, ring in ((0, vrings[0]), (1, vrings[-1])):
        if poles[e] is None:
            tmp.faces.new(ring if e == 0 else ring[::-1])
            continue
        pole = tmp.verts.new(poles[e])
        for k in range(sides):
            f = (ring[k], ring[(k + 1) % sides], pole)
            tmp.faces.new(f[::-1] if e == 0 else f)
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)
    return rings


def pa_unsmooth(grid, poles=(None, None), iters=24):
    """The cage rings whose soft limit surface passes through `grid` (rings of points along a tube): soft() averages
    each point with its neighbours along the tube by (1, 4, 1) / 6, which would pull a curved centre line in and
    shave the fat parts; this undoes it (the averaging round each ring is made up for by the ring's radius)."""
    G = [[Vector(q) for q in ring] for ring in grid]
    X = [[Vector(q) for q in ring] for ring in grid]
    n = len(G)
    for _ in range(iters):
        for i in range(n):
            for k in range(len(G[i])):
                lo_ = X[i - 1][k] if i > 0 else (poles[0] if poles[0] is not None else None)
                hi_ = X[i + 1][k] if i < n - 1 else (poles[1] if poles[1] is not None else None)
                if lo_ is None or hi_ is None:
                    continue
                X[i][k] = X[i][k] + (G[i][k] - (lo_ + 4 * X[i][k] + hi_) / 6)
    return X


def pa_front_point(at, cs, rs, u, v):
    """The point of a canal surface (the union of spheres cs, rs) that the art shows at pixel (u, v): the hit nearest
    the viewer along the line of sight; None if it misses."""
    o = at(u, v, 0.0)
    d = (at(u, v, 1.0) - o).normalized()
    best = None
    for c, r in zip(cs, rs):
        w = o - Vector(c)
        b = d.dot(w)
        disc = b * b - (w.dot(w) - r * r)
        if disc >= 0:
            t = -b + math.sqrt(disc)
            best = t if best is None else max(best, t)
    return None if best is None else o + d * best


def pa_paint(p, f0, mat, field):
    """Gives `mat` to the parts of the faces added to p since it had f0 faces where field(point) > 0, cutting the
    faces the boundary crosses along it first so that its edge runs smooth (as meat_fish.paint)."""
    bm = p.bm
    bm.faces.ensure_lookup_table()
    faces = list(bm.faces[f0:])
    val = {}
    for f in faces:
        for v in f.verts:
            if v not in val:
                val[v] = field(v.co)
    cross = {e for f in faces for e in f.edges if (val[e.verts[0]] > 0) != (val[e.verts[1]] > 0)}
    zero = set()
    for e in cross:
        a, b = e.verts
        t = val[a] / (val[a] - val[b])
        _, nv = bmesh.utils.edge_split(e, a, t)
        val[nv] = 0.0
        zero.add(nv)
    for f in faces:
        zs = [v for v in f.verts if v in zero]
        if len(zs) == 2 and not any(e for e in f.edges if set(e.verts) == set(zs)):
            bmesh.utils.face_split(f, zs[0], zs[1])
    bm.faces.ensure_lookup_table()
    mi = p._mi(mat)
    for f in bm.faces[f0:]:
        vs = [val.get(v, 0.0) for v in f.verts]
        if sum(vs) / len(vs) > 0:
            f.material_index = mi


def pa_calyx_field(at, cs, rs, rim, lobes=5, amp=0.22, ph=0.0):
    """A field for pa_paint(): positive on the calyx over the shoulder end of a pod (cs, rs: its spheres from that
    end), up to a rim square to the pod's axis there, in `lobes` round lobes `amp` of its reach deep. The rim's
    reach is where the art draws it: the median over its pixels `rim`, found on the pod along the line of sight.
    Returns the field and the top of the shoulder, where the stalk comes out."""
    c0 = Vector(cs[0])
    j = next((i for i in range(len(cs)) if (Vector(cs[i]) - c0).length > rs[0] * 0.5), len(cs) - 1)
    T = (Vector(cs[j]) - c0).normalized()
    A = pa_normal_to(T)
    B = T.cross(A)
    x0 = -rs[0]
    xs = sorted((q - c0).dot(T) for q in (pa_front_point(at, cs, rs, u, v) for u, v in rim) if q is not None)
    reach = xs[len(xs) // 2] - x0

    def field(q):
        d = q - c0
        f = math.atan2(d.dot(B), d.dot(A))
        return x0 + reach * (1 + amp * math.cos(lobes * f + ph)) - d.dot(T)
    return field, c0 - T * rs[0]


def pa_on_ray(at, u, v, q):
    """The point the art shows at pixel (u, v) that is nearest to q: where a stalk drawn there meets a pod."""
    a, b = at(u, v, 0.0), at(u, v, 1.0)
    d = b - a
    return a + d * ((q - a).dot(d) / d.dot(d))


def pa_smooth(t):
    t = max(0.0, min(1.0, t))
    return t * t * (3 - 2 * t)


CHILI_ART = (6500, 650, 900)   # 辣椒.png: px per metre, and the pixel where the origin is


CHILI_PODS = (   # centre lines (u, v, r) in art pixels from the shoulder to the tip, fitted to the art's regions
    [[308, 681, 123], [347, 738, 145], [406, 810, 145], [476, 870, 127], [556, 927, 112], [644, 981, 90],
     [729, 1017, 71], [818, 1037, 56], [899, 1025, 42], [940, 991, 32], [951, 959, 18]],
    [[487, 496, 144], [531, 543, 145], [588, 630, 135], [668, 724, 122], [765, 795, 101], [872, 843, 81],
     [981, 862, 56], [1082, 874, 38], [1148, 904, 28], [1171, 938, 16]],
    [[722, 573, 60], [795, 608, 67], [861, 656, 67], [935, 709, 65], [1035, 752, 61], [1125, 748, 47],
     [1183, 714, 30], [1210, 675, 16]])


CHILI_RIMS = (   # where the art draws the lobed rims of the calyxes
    [(186, 699), (213, 676), (238, 653), (268, 641), (289, 612), (319, 603), (349, 602), (379, 596)],
    [(348, 486), (376, 491), (390, 468), (414, 441), (441, 429), (463, 402), (491, 391), (516, 377)],
    None)


CHILI_STALKS = (   # from the calyx to the cut end, and how much higher the cut end stands than the calyx top
    ([[247, 588, 46], [233, 537, 30], [213, 482, 26], [184, 435, 25], [150, 410, 26], [114, 409, 27]], 0.012),
    ([[427, 375, 46], [381, 313, 32], [368, 241, 26], [398, 179, 26], [430, 153, 28], [450, 151, 23]], 0.015),
    None)


def pa_true(tmp, iters=10):
    """Moves the vertices of the cage tmp until one level of p.soft() (Blender's subdivision onto its limit surface)
    puts each where it is now: a cage built on the surface it should have keeps its size and shape when softened,
    instead of shrinking into it."""
    target = [v.co.copy() for v in tmp.verts]
    me = bpy.data.meshes.new('pa_true')
    ob = bpy.data.objects.new('pa_true', me)
    bpy.context.scene.collection.objects.link(ob)
    md = ob.modifiers.new('Subsurf', 'SUBSURF')
    md.levels = md.render_levels = 1
    for _ in range(iters):
        tmp.to_mesh(me)
        me.update()
        bpy.context.view_layer.update()
        ev = ob.evaluated_get(bpy.context.evaluated_depsgraph_get())
        em = ev.to_mesh()
        lim = [em.vertices[i].co.copy() for i in range(len(target))]
        ev.to_mesh_clear()
        for v, t, q in zip(tmp.verts, target, lim):
            v.co += t - q
    bpy.data.objects.remove(ob)
    bpy.data.meshes.remove(me)


def pa_cage(p, rings, poles, mat, true=True):
    """A closed soft cage from rings of points (each the same count, in order along the piece) capped by the two
    pole points (None leaves that end open: close it yourself), made true (pa_true) so that softening keeps it on the
    surface the rings were taken from. Build it inside p.soft()."""
    tmp = bmesh.new()
    vr = [[tmp.verts.new(Vector(q)) for q in ring] for ring in rings]
    n = len(vr[0])
    for ra, rb in zip(vr, vr[1:]):
        for k in range(n):
            tmp.faces.new((ra[k], ra[(k + 1) % n], rb[(k + 1) % n], rb[k]))
    for pole, ring in ((poles[0], vr[0]), (poles[1], vr[-1])):
        if pole is None:
            continue
        pv = tmp.verts.new(Vector(pole))
        for k in range(n):
            tmp.faces.new((ring[k], ring[(k + 1) % n], pv))
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    if true:
        pa_true(tmp)
    p._commit(tmp, mat)


def pa_place(rings, poles, M, ground=True):
    """rings and poles moved by M, then (ground) lifted or lowered to rest on the table at z = 0."""
    rings = [[M @ q for q in ring] for ring in rings]
    poles = [None if q is None else M @ q for q in poles]
    if ground:
        dz = -min(min(q.z for ring in rings for q in ring), min(q.z for q in poles if q is not None))
        rings = [[q + Vector((0.0, 0.0, dz)) for q in ring] for ring in rings]
        poles = [None if q is None else q + Vector((0.0, 0.0, dz)) for q in poles]
    return rings, poles


def pa_pose(x, y, yaw, pitch=0.0, roll=0.0, z=0.0):
    """Placing matrix: turned `roll` about the piece's own x, tipped up by `pitch`, turned `yaw` about Z, moved to
    (x, y, z)."""
    return (Matrix.Translation((x, y, z)) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(-pitch, 4, 'Y')
            @ Matrix.Rotation(roll, 4, 'X'))


def pa_cucumber(prm, cut=None, nu=12, seg=6, edge=0.003):
    """A cucumber from its fitted parameters (x, y, yaw, pitch, R, L, taper, bend[, end]): a long body of radius R, L long
    from end to end along its own x, swelling toward +x by `taper`, bowed up by `bend` (a share of L), both ends
    round; or, given cut = (gamma, psi), sliced off at +x on a slant: the cut face's normal leans gamma from the axis
    toward psi round it, its edge rounded over `edge`. Returns (rings, poles, face): rings and poles resting on the
    table, and for a cut one (the face's centre, its normal, its outer ring), else None."""
    x0, y0, yaw, pitch, R, L, taper, bend = prm[:8]
    h = L / 2
    e = min((prm[8] if len(prm) > 8 else 0.95) * R, 0.45 * L)   # how far the round ends reach in

    def radius(x):
        k = R * (1 + taper * x / h)
        d = abs(x) - (h - e)
        return k * math.sqrt(max(0.0, 1 - (d / e) ** 2)) if d > 0 else k

    def lift(x):
        return bend * L * (1 - (x / h) ** 2)

    def ring(x, f_list=None, rr=None):
        return [Vector((x, (rr or radius(x)) * math.cos(f), lift(x) + (rr or radius(x)) * math.sin(f)))
                for f in (f_list or [2 * math.pi * j / nu for j in range(nu)])]
    cap = [-h + e * (1 - math.cos(a)) for a in (0.45, 0.9, 1.3, math.pi / 2)]
    if cut is None:
        mid = [-h + e + (L - 2 * e) * i / seg for i in range(1, seg)]
        xs = cap + mid + [-x for x in reversed(cap)]
        rings = [ring(x) for x in xs]
        poles = [Vector((-h, 0.0, lift(-h))), Vector((h, 0.0, lift(h)))]
        face = None
    else:
        gamma, psi = cut
        n = Vector((math.cos(gamma), math.sin(gamma) * math.cos(psi), math.sin(gamma) * math.sin(psi)))
        rc = R * (1 + taper)
        c = Vector((h, 0.0, lift(h)))
        cols = []
        for j in range(nu):
            f = 2 * math.pi * j / nu
            x_end = h - rc * math.tan(gamma) * math.cos(f - psi)
            col = [ring(x, [f])[0] for x in cap]
            for i in range(1, seg + 1):
                x = cap[-1] + (x_end - edge - cap[-1]) * i / seg
                col.append(Vector((x, rc * math.cos(f) * (1 + taper * x / h) / (1 + taper),
                                   lift(x) + rc * math.sin(f) * (1 + taper * x / h) / (1 + taper))))
            rho = rc - 1.6 * edge
            xf = h - rho * math.tan(gamma) * math.cos(f - psi)
            q = Vector((xf, rho * math.cos(f), lift(h) + rho * math.sin(f)))
            col += [c + (q - c) * k for k in (1.0, 0.62, 0.28)]
            cols.append(col)
        rings = [[cols[j][i] for j in range(nu)] for i in range(len(cols[0]))]
        poles = [Vector((-h, 0.0, lift(-h))), c]
    M = pa_pose(x0, y0, yaw, pitch)
    rings, poles = pa_place(rings, poles, M)
    if cut is not None:
        face = (poles[1], (M.to_3x3() @ n).normalized(), rings[-3])
    return rings, poles, face


def chili(col):
    """辣椒 as the art has it: three long, fat red chillies lying side by side from the top left to the bottom right,
    the front one lowest, their tips curling up; the two in front have green calyxes with round lobes gripping their
    shoulders and thick hooked stalks with cut ends. Laid out on 辣椒.png (65 px to the centimetre): each pod is the
    envelope of the discs fitted to the art."""
    p = Part()
    S, u0, v0 = CHILI_ART
    at = art_px(S, u0, v0)
    for ctrl, stalk, rim in zip(CHILI_PODS, CHILI_STALKS, CHILI_RIMS):
        dense = pa_spline(ctrl)
        s2 = pa_lengths([(u, v, 0.0) for u, v, _ in dense])
        rs = [r / S for _, _, r in dense]
        # each pod lies on its belly, bowed: the tip curls up off the table, and the shoulder rises until its axis
        # runs square to the line of sight, so that the calyx is seen from the side as the art draws it
        j = next(i for i, s in enumerate(s2) if s > 40)
        dv, dr = (dense[j][1] - dense[0][1]) / s2[j], (dense[j][2] - dense[0][2]) / s2[j]
        reach = 0.3 * s2[-1]
        rise = reach * (dv * math.cos(ART_EL) + dr) / (2 * S)
        cs = [at(u, v, r + 0.006 * pa_smooth((s / s2[-1] - 0.78) / 0.22) + rise * max(0.0, 1 - s / reach) ** 2)
              for (u, v, _), r, s in zip(dense, rs, s2)]
        f0 = len(p.bm.faces)
        with p.soft():
            pa_canal(p, cs, rs, 'ChiliRed', sides=10, spacing=0.8, lo=0.004, hi=0.014)
        if stalk:
            field, top = pa_calyx_field(at, cs, rs, rim)
            pa_paint(p, f0, 'CalyxGreen', field)
            ctrl_s, dz = stalk
            sd = pa_spline(ctrl_s)
            ss = pa_lengths([(u, v, 0.0) for u, v, _ in sd])
            z0 = pa_on_ray(at, sd[0][0], sd[0][1], top).z
            scs = [at(u, v, z0 + dz * pa_smooth(s / ss[-1]) ** 0.8) for (u, v, _), s in zip(sd, ss)]
            with p.soft():
                pa_canal(p, scs, [r / S for _, _, r in sd], 'CalyxGreen', sides=8, spacing=1.4, lo=0.003, hi=0.008)
    return p.finish('SM_chili', col, sharp=None)


PALETTE.update({
    'PotatoArtSkin': ('#d9a45e', '#b07c3c'),    # 土豆's skin, under the art's own colours (pv_traced)
    'PotatoArtFlesh': ('#f6e29a', '#e0c56c'),   # the peeled one
})
GLOSS.update({'PotatoArtSkin': 0.0, 'PotatoArtFlesh': 0.25})
VIVID.update({'PotatoArtSkin': 0.5, 'PotatoArtFlesh': 0.5})
VTINT.update(dict.fromkeys(('PotatoArtSkin', 'PotatoArtFlesh'), 1.0))
DETAIL.update({'PotatoArtSkin': ('food_potato', 14, '#8a5428', 0.35, 0.3),   # blotches, specks, its dry grain
               'PotatoArtFlesh': ('food_mottle', 10, '#f2cf72', 0.25, 0.15)})


def potato(col):
    """土豆 traced off its art (trace_potato.py): a big egg-shaped potato on the left and a smaller one behind it on the
    right, in their golden skins with brown blotches, dark eyes and specks, and in front a peeled one, pale yellow,
    cut into broad knife facets. Every piece covers exactly what the art paints, in the art's own colours."""
    p = Part()
    pv_traced(p, 'potato')
    return pb_finish(p, 'SM_potato', col, pb_recentre(p))


PALETTE.update({
    'GarlicArtSkin': ('#f3e6e2', '#cdb7b8'),    # 蒜's bulb under the art's own colours (pv_traced): white, pink-washed
    'GarlicArtRoot': ('#b98a5a', '#8a6038'),    # its roots
    'GarlicArtPeel': ('#dcb0a0', '#b08070'),    # the clove in its pink skin
    'GarlicArtClove': ('#f7e8bc', '#e2c98e'),   # the peeled cloves
})
GLOSS.update({'GarlicArtSkin': 0.1, 'GarlicArtRoot': 0.0, 'GarlicArtPeel': 0.1, 'GarlicArtClove': 0.35})
VIVID.update(dict.fromkeys(('GarlicArtSkin', 'GarlicArtRoot', 'GarlicArtPeel', 'GarlicArtClove'), 0.5))
VTINT.update(dict.fromkeys(('GarlicArtSkin', 'GarlicArtRoot', 'GarlicArtPeel', 'GarlicArtClove'), 1.0))
DETAIL.update({'GarlicArtSkin': ('food_garlic', 18, '#b48ea0', 0.3, 0.2),    # papery streaks up the bulb
               'GarlicArtPeel': ('food_garlic', 22, '#9a6656', 0.3, 0.2),
               'GarlicArtClove': ('food_mottle', 14, '#f0d48e', 0.2, 0.15)})


def garlic(col):
    """蒜 traced off its art (trace_garlic.py): a round bulb of cloves bulging between brown creases, washed with
    purple-pink streaks, its dry neck on top and a tuft of roots at its foot; in front of it two peeled cream cloves
    with brown root scars, and on the right a clove still in its pink skin, its papery tip curling up. Every piece
    covers exactly what the art paints, in the art's own colours."""
    p = Part()
    pv_traced(p, 'garlic')
    return pb_finish(p, 'SM_garlic', col, pb_recentre(p))


def pb_hair(p, pts, r0, r1, mat, sides=4):
    """A root hair or a strand along the points pts (3D), tapering from radius r0 to r1, blunt at both ends; not
    subdivided (it is too thin to show facets)."""
    n = len(pts)
    rings = []
    for i, q in enumerate(pts):
        tan = (pts[min(i + 1, n - 1)] - pts[max(i - 1, 0)]).normalized()
        a = tan.cross(Vector((0.0, 0.0, 1.0)))
        a = a.normalized() if a.length > 1e-6 else Vector((1.0, 0.0, 0.0))
        b = a.cross(tan).normalized()
        r = r0 + (r1 - r0) * i / (n - 1)
        rings.append([q + (a * math.cos(2 * math.pi * (k + 0.5) / sides) + b * math.sin(2 * math.pi * (k + 0.5) / sides)) * r
                      for k in range(sides)])
    tmp = bmesh.new()
    vs = [[tmp.verts.new(q) for q in r] for r in rings]
    for i in range(n - 1):
        for k in range(sides):
            tmp.faces.new((vs[i][k], vs[i][(k + 1) % sides], vs[i + 1][(k + 1) % sides], vs[i + 1][k]))
    tmp.faces.new(list(reversed(vs[0])))
    tmp.faces.new(vs[-1])
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)


def pb_recentre(p):
    """Moves everything so that the middle of its footprint is at the origin (it stays on the ground)."""
    xs = [v.co.x for v in p.bm.verts]
    ys = [v.co.y for v in p.bm.verts]
    d = Vector(((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2, 0.0))
    for v in p.bm.verts:
        v.co -= d
    return d


def pb_finish(p, name, col, d):
    """p.finish(name, col, sharp=None), the object remembering in 'pb_shift' how far pb_recentre() moved it (d), so
    that its art camera can be found again."""
    ob = p.finish(name, col, sharp=None)
    ob['pb_shift'] = (d.x, d.y)
    return ob


PB_TOWARD = Vector((0.0, -math.cos(ART_EL), math.sin(ART_EL)))   # from the model toward the art's camera


def pb_settle(p, v0, floor=0.0):
    """Slides what was added to p since it had v0 vertices along the art's line of sight until its lowest point is at
    `floor`: it comes down onto the table (or up out of it) without moving in the art's view. Returns the move."""
    p.bm.verts.ensure_lookup_table()
    vs = p.bm.verts[v0:]
    shift = PB_TOWARD * ((floor - min(v.co.z for v in vs)) / PB_TOWARD.z)
    for v in vs:
        v.co += shift
    return shift


def pb_lift(p, v0, floor=1e-5):
    """pb_settle() only for what dips under `floor`: what was added to p since it had v0 vertices comes up the art's
    line of sight onto the table (the art still shows it just so); what already clears it stays. Returns the move."""
    p.bm.verts.ensure_lookup_table()
    if min(v.co.z for v in p.bm.verts[v0:]) >= floor:
        return Vector()
    return pb_settle(p, v0, floor)


ITEMS = [('greens', greens),
         ('scallion', scallion),
         ('ginger', ginger),
         ('radish', radish),
         ('gourd', gourd),
         ('bamboo', bamboo),
         ('perilla', perilla),
         ('mushroom', mushroom),
         ('tomato', tomato),
         ('chili', chili),
         ('potato', potato),
         ('garlic', garlic)]
