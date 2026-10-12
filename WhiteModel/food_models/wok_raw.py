"""锅中生料: the main ingredients as the solid pieces they go into the wok as (a ball of dough, a dome of rice, chunks of
pork, cubes of chicken, a whole egg, the whole fish, wedges of tomato, …), for the cooking screen to toss about while a
dish cooks; build_raw.py builds them. They hop and tumble and flip right over, so unlike the display models (whose
traced pieces only look right from the art's view) every piece is closed and solid and looks right from every side:
rounded all over (soft cages, bevels), real size, resting on z = 0 in its natural pose with the middle of its
footprint over the origin, within 1500 triangles; in the display model's colours, and so its painted textures
(DETAIL). PIECES: id -> (builder, how many pieces go into the wok)."""
import math
import random

import bmesh
from mathutils import Matrix, Vector

from .core import *  # noqa: F401,F403
from .meat_fish import (CARP_BODY, CARP_DORSAL, CARP_GILL, CARP_TAIL, GUIYU_BODY, GUIYU_SOFT, GUIYU_TAIL, YUTOU_HEAD,
                        carp_colour, caster, crab_colour, crab_limb, guiyu_colour, hull, interp, lattice_box,
                        mix, paint, poly_field, ramp, shell, skin_sheet, slab, soft_block, soft_cube, yutou_colour)
from .produce import mu_cage, pa_canal, pa_normal_to, sector
from .sacks import crystal, sheet, soft_tube


def grounded(p):
    """Moves the piece to rest on z = 0 with the middle of its footprint over the origin (its pivot at its foot)."""
    vs = p.bm.verts
    lo = Vector([min(v.co[i] for v in vs) for i in range(3)])
    hi = Vector([max(v.co[i] for v in vs) for i in range(3)])
    d = Vector(((lo.x + hi.x) / 2, (lo.y + hi.y) / 2, lo.z))
    for v in vs:
        v.co -= d


def done(p, key, col):
    """The piece grounded and finished as RAW_<key>, shaded smooth all over. It always carries Part.tint's layer
    (white where nothing is painted: no tint), as the display models do."""
    bmesh.ops.dissolve_degenerate(p.bm, dist=2e-5, edges=p.bm.edges[:])   # slivers left where paint() cut a face
    grounded(p)
    p.bm.loops.layers.float_color.get('Tint') or p.bm.loops.layers.float_color.new('Tint')
    return p.finish('RAW_' + key, col, sharp=None)


def lattice(k):
    """k + 1 lattice values from -1 to 1 at even angles across a cube's face (for a ball)."""
    return tuple(math.tan(math.pi / 4 * (2 * i / k - 1)) for i in range(k + 1))


def ball(p, mat, shape, lat=lattice(4)):
    """A cage for soft(): a quad ball (a cube's faces, 4 x 4 quads each by default, no poles), the point towards
    each unit direction d placed at shape(d)."""
    lattice_box(p, mat, lambda u, v, w: shape(Vector((u, v, w)).normalized()), lat, lat, lat)


def wobble(d, amp, seed):
    """1 + a gentle unevenness over the unit direction d, about amp at most: dough, rice, a hand-cut chunk."""
    return 1 + amp * (0.55 * math.sin(3.1 * d.x + 2.3 * d.y + seed) + 0.45 * math.sin(4.7 * d.y - 3.3 * d.z + 2 * seed))


def jittered(F, amp, seed, flat_foot=True):
    """F(u, v, w) for lattice_box with every lattice point nudged up to amp at random, as a knife leaves a cut
    piece (the foot, w = -1, kept flat)."""
    rnd = random.Random(seed)
    cache = {}

    def G(u, v, w):
        if (u, v, w) not in cache:
            j = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * amp
            if flat_foot and w < -0.999:
                j.z = 0.0
            cache[u, v, w] = F(u, v, w) + j
        return cache[u, v, w]
    return G


def oval(c, a, b):
    """A field positive inside the ellipse about c = (x, y) with half axes a, b (on two coordinates)."""
    return lambda x, y: 1.0 - math.hypot((x - c[0]) / a, (y - c[1]) / b)


def leaf_cage(p, mid, thick, nu, nv, mat):
    """A closed sheet for soft(), built flat: over the grid of its middle surface mid(u, v) -> (x, y) for u, v in
    0..1 (nu x nv points), thick(u, v) through; both faces, and a rim round its edge, so that it comes out with round
    edges. Leaves, a pancake, pickled cabbage: bend it into shape afterwards (bent())."""
    P = [[mid(i / (nu - 1), j / (nv - 1)) for j in range(nv)] for i in range(nu)]
    tmp = bmesh.new()
    top, bot = [[[tmp.verts.new((P[i][j][0], P[i][j][1], s * thick(i / (nu - 1), j / (nv - 1)) / 2))
                  for j in range(nv)] for i in range(nu)] for s in (1, -1)]
    for i in range(nu - 1):
        for j in range(nv - 1):
            tmp.faces.new((top[i][j], top[i + 1][j], top[i + 1][j + 1], top[i][j + 1]))
            tmp.faces.new((bot[i][j], bot[i][j + 1], bot[i + 1][j + 1], bot[i + 1][j]))
    rim = ([(i, 0) for i in range(nu)] + [(nu - 1, j) for j in range(1, nv)] + [(i, nv - 1) for i in range(nu - 2, -1, -1)]
           + [(0, j) for j in range(nv - 2, 0, -1)])
    for (i0, j0), (i1, j1) in zip(rim, rim[1:] + rim[:1]):
        tmp.faces.new((top[i0][j0], top[i1][j1], bot[i1][j1], bot[i0][j0]))
    tmp.normal_update()
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    p._commit(tmp, mat)


def bent(p, n0, f):
    """Moves every vertex added to p since it had n0 of them to f(point): a piece built flat bent into shape."""
    p.bm.verts.ensure_lookup_table()
    for v in p.bm.verts[n0:]:
        v.co = f(v.co.copy())


def curled(R):
    """A bend rolling a flat piece's sides up round a line along x, R above it: y across becomes an arc of radius R
    (the thickness kept, the lower face outside)."""
    def f(q):
        a = q.y / R
        r = R - q.z
        return Vector((q.x, r * math.sin(a), R - r * math.cos(a)))
    return f


# ---------------------------------------------------------------- dough and rice

def raw_flour(col):
    """面粉 → a ball of dough: a little flattened and uneven, settled flat underneath where it rests, the flour's
    white."""
    p = Part()
    R = 0.034

    def shape(d):
        q = d * R * wobble(d, 0.05, 1.0)
        q.z *= 0.74
        if q.z < -0.38 * R:   # its underside settled flat
            q.z = -0.38 * R + (q.z + 0.38 * R) * 0.25
        return q
    with p.soft():
        ball(p, 'Flour', shape)
    return done(p, 'flour', col)


def rice_dome(p, mat, r, h, seed):
    """A small dome of rice r across and h high, as a scoop of it lies: a lumpy round top, the rim rounding under to a
    flat foot; the grains are the colour's painted texture (food_grains)."""
    def shape(d):
        k = wobble(d, 0.06, seed)
        if d.z >= 0:
            return Vector((d.x * r * k, d.y * r * k, d.z * h * (0.9 + 0.1 * k)))
        return Vector((d.x * r * k, d.y * r * k, d.z * h * 0.22))
    with p.soft():
        ball(p, mat, shape)


def raw_rice(col):
    """米 → a small dome of rice, its grains painted on (RiceGrain's food_grains)."""
    p = Part()
    rice_dome(p, 'RiceGrain', 0.036, 0.03, 1.0)
    return done(p, 'rice', col)


def raw_rice_prep(col):
    """米料备料 → a small dome of the prepared rice (MiRice, food_grains)."""
    p = Part()
    rice_dome(p, 'MiRice', 0.035, 0.028, 2.5)
    return done(p, 'rice_prep', col)


# ---------------------------------------------------------------- meat

def raw_pork(col):
    """猪肉 → a chunk of pork belly: marbled pink lean (RawPork) in two layers between white fat (PorkFat), the fat
    capping its top, the layers a little wavy; uneven as the knife leaves it, every edge rounded; lying on a cut face
    with its layers level."""
    p = Part()
    L, W, H = 0.037, 0.031, 0.029
    rnd = random.Random(4)
    lat = (-1.0, -0.62, 0.0, 0.62, 1.0)
    jit = {}

    def F(u, v, w):
        if (u, v, w) not in jit:
            jit[u, v, w] = Vector((rnd.uniform(-1, 1), rnd.uniform(-1, 1), rnd.uniform(-1, 1))) * 0.0012
        j = jit[u, v, w]
        if w < -0.999:
            j = Vector((j.x, j.y, 0.0))
        k = 1 - 0.06 * (w + 1) / 2   # a little narrower at the top
        return Vector((u * L / 2 * k, v * W / 2 * k, (w + 1) / 2 * H)) + j
    f0 = len(p.bm.faces)
    with p.soft():
        lattice_box(p, 'RawPork', F, lat, lat, lat)

    def fat(q):   # positive in the fat: a band through the middle and the cap on top, their edges wavy
        wave = 0.0018 * math.sin(140 * q.x + 1.0) + 0.0012 * math.sin(190 * q.y + 2.0)
        band = min(q.z - (0.36 * H + wave), (0.52 * H - wave * 0.6) - q.z)
        cap = q.z - (0.8 * H + wave * 0.8)
        return max(band, cap)
    paint(p, f0, 'PorkFat', fat)
    return done(p, 'pork', col)


def raw_chicken(col):
    """鸡肉 → a cube of raw breast (RawChicken, its fibres painted on), its edges and corners softly rounded, a little
    uneven as the knife leaves it."""
    p = Part()
    soft_block(p, Vector((0.0, 0.0, 0.0)), (0.027, 0.025, 0.022), 'RawChicken', 0.0, round_=0.42, seed=11,
               jitter=0.001, levels=1)
    return done(p, 'chicken', col)


def raw_tofu(col):
    """豆腐 → a cube of tofu, flat faces and softly rounded edges."""
    p = Part()
    soft_cube(p, (0.0, 0.0, 0.013), (0.027, 0.027, 0.026), 'TofuWhite', 0.0, r=0.0035)
    return done(p, 'tofu', col)


def raw_egg(col):
    """鸡蛋 → a whole egg in its shell, lying on its side, its far end a little narrower."""
    p = Part()
    a, b = 0.029, 0.0215

    def shape(v):
        k = 1 - 0.09 * v.x / a
        return Vector((v.x, v.y * k, v.z * k))
    p.blob((0.0, 0.0, 0.0), 1.0, 'EggShell', squash=(a, b, b), segs=(24, 12), deform=shape)
    return done(p, 'egg', col)


def raw_duck(col):
    """鸭 → a piece of raw duck as the cleaver chops it: a chunk with a domed top in the cream skin and its follicles
    (DuckRawSkin) coming a little way down its sides, the layer of fat under the skin showing at the cut sides
    (DuckRawLimb's warmer peach), the pink meat of the cut faces (DuckRawCut) below; skin up."""
    p = Part()
    L, W, H = 0.046, 0.032, 0.027
    lat = (-1.0, -0.62, 0.0, 0.62, 1.0)

    def top(x, y):
        return H * (1 - 0.2 * (2 * x / L) ** 2 - 0.28 * (2 * y / W) ** 2)

    def F(u, v, w):
        x, y = u * L / 2 * (1 - 0.05 * (w + 1) / 2), v * W / 2 * (1 - 0.1 * (w + 1) / 2)
        return Vector((x, y, (w + 1) / 2 * top(u * L / 2, v * W / 2)))
    f0 = len(p.bm.faces)
    with p.soft():
        lattice_box(p, 'DuckRawCut', jittered(F, 0.0011, 21), lat, lat, lat)

    def under_skin(q):   # how high the skin comes down: following the dome a little, wavy
        return (0.64 * H + 0.3 * (top(q.x, q.y) - H) + 0.0012 * math.sin(150 * q.x + 0.5)
                + 0.0008 * math.sin(210 * q.y + 1.5))
    paint(p, f0, 'DuckRawLimb', lambda q: q.z - (under_skin(q) - 0.0032))
    paint(p, f0, 'DuckRawSkin', lambda q: q.z - under_skin(q))
    return done(p, 'duck', col)


def raw_kidney(col):
    """猪腰子 → half a pork kidney as it is cut for the wok: a bean in outline, domed and dark red on top (KidneyRed,
    softly blotched), flat underneath where it was cut through lengthwise, the pale core (KidneyFat) showing there
    along its hollow side; lying on its cut face."""
    p = Part()
    L, W, H = 0.056, 0.032, 0.019

    def bean(d):
        q = Vector((d.x * L / 2, d.y * W / 2, d.z * H if d.z > 0 else d.z * H * 0.14))
        t = max(-1.0, min(1.0, q.x / (L / 2)))
        q.y -= 0.006 * (1 - t * t)                                                  # bowed round its hollow side
        q.y -= 0.0065 * math.exp(-(t / 0.38) ** 2) * max(0.0, d.y) ** 1.5           # and dented in the middle of it
        q.z *= 1 - 0.25 * t * t                                                       # its ends lower
        return q
    f0 = len(p.bm.faces)
    with p.soft():
        ball(p, 'KidneyRed', bean)
    zb = min(v.co.z for v in p.bm.verts)
    core = oval((0.0, -0.0035), 0.019, 0.0052)
    paint(p, f0, 'KidneyFat', lambda q: min(zb + 0.0012 - q.z, core(q.x, q.y + 0.0012 * math.sin(160 * q.x))))
    return done(p, 'kidney', col)


# the wingette along x from its broad joint end (t = 0) to its narrow one (t = 1): (t, half width, height of the
# dome, how far the skin flares out into a thin flap at its sides)
WING_PLAN = [(0.0, 0.0172, 0.0112, 0.0), (0.12, 0.0205, 0.0162, 0.75), (0.38, 0.022, 0.02, 1.0),
             (0.64, 0.0196, 0.0182, 1.0), (0.86, 0.0146, 0.0138, 0.65), (1.0, 0.011, 0.0104, 0.0)]


def wing_section(w, h, f, wave=(0.0, 0.0)):
    """The wingette's cross-section at one station, 14 points (y, z) round from the top of its middle: a low dome
    over a flat underside, rounder over its bones along -y, its sides falling to a skirt of skin that flares out
    thin (under 4 mm at its edge), widest along +y where the web of skin was (f = 1), or rounding down into its
    side (f = 0, at the ends); wave = (out, up) ruffles the skirt's edge."""
    def side(sg, f, bulge):
        def lerp(a, b):
            return a + (b - a) * f
        return [(sg * 0.36 * w, 0.84 * h), (sg * lerp(0.7, 0.6 + bulge) * w, lerp(0.5, 0.42 + bulge) * h),
                (sg * lerp(0.86, 0.72 + bulge) * w, lerp(0.28 * h, 0.0052 + wave[1] * 0.5)),
                (sg * lerp(0.965, 0.975 + wave[0]) * w, lerp(0.16 * h, 0.0031 + wave[1])),
                (sg * lerp(0.93, 1.0 + wave[0]) * w, lerp(0.05 * h, 0.001 + wave[1] * 0.6)), (sg * 0.55 * w, 0.0)]
    return [(0.0, h)] + side(1.0, f, 0.0) + [(0.0, 0.0)] + list(reversed(side(-1.0, f * 0.6, 0.08)))


def raw_wing(col):
    """鸡翅 → one of the art's raw mid-wings (中翅) made solid: broad and flattened, a rounded trapezoid in plan with
    its joint ends cut aslant, broad at one end and narrower at the other, widest a little toward the broad end; a
    low dome along its middle, rounder over the bones along one side, falling to thin edges of skin that flare out
    along both long sides as the skin drapes, widest where the web of skin was; flat underneath. At each end the
    skin rolls over into a soft lip round the cut face: the pink meat (WingRawMeat) with the darker end of the bone
    in it (WingRawDeep). The pale pink-cream skin (WingRawSkin) is finely wrinkled across, going pinker toward the
    ends and its thin edges as the art paints it. It lies along x, so the wrinkles of its texture (box-projected,
    slanting 50 degrees in the tile) cross it rather than run along it."""
    L = 0.064
    p = Part()

    def at(t):   # the plan at t: half width, height, flap
        return tuple(interp([(q[0], q[k]) for q in WING_PLAN], t) for k in (1, 2, 3))

    def ring(t, scale=1.0, wave=(0.0, 0.0), lump=0.0):
        w, h, f = at(t)
        zc = 0.42 * h
        pts = wing_section(w * (1 + lump), h * (1 + lump * 0.6), f, wave)
        slant = 0.22 if t < 0.5 else -0.16   # the joint ends cut aslant
        lean = (0.5 if t < 0.5 else -0.5) * (scale != 1.0)   # and the lips round them leaning back, face up
        x = t * L - L / 2
        out = []
        for y, z in pts:
            z = max(0.0, zc + (z - zc) * scale)
            out.append(Vector((x + slant * y * max(0.0, 1 - min(t, 1 - t) / 0.3) * scale + lean * max(0.0, z - zc),
                               y * scale, z)))
        return out
    # from the cut face at the broad end out over its lip (inner edge, crest, the roll of skin behind it), along the
    # body and over the lip at the narrow end to its cut face
    rings = [ring(0.024, 0.74), ring(0.0, 0.92), ring(0.04, 1.06),
             ring(0.15, wave=(0.04, 0.0008), lump=0.02), ring(0.32, wave=(-0.03, -0.0006), lump=-0.01),
             ring(0.5, wave=(0.05, 0.001), lump=0.015), ring(0.68, wave=(-0.02, 0.0), lump=-0.01),
             ring(0.86, wave=(0.04, 0.0008)), ring(0.96, 1.06), ring(1.0, 0.92), ring(0.976, 0.74)]
    poles = [sum(rings[0], Vector()) / len(rings[0]) + Vector((0.0004, 0.0, 0.0)),
             sum(rings[-1], Vector()) / len(rings[-1]) - Vector((0.0004, 0.0, 0.0))]
    mats = ['WingRawMeat'] + ['WingRawSkin'] * (len(rings) - 1) + ['WingRawMeat']
    f0 = len(p.bm.faces)
    with p.soft():
        mu_cage(p, rings, poles, mats)
    for c in poles:   # the end of the bone in the middle of each cut face
        paint(p, f0, 'WingRawDeep', lambda q, c=c: min(0.0024 - abs(q.x - c.x),
                                                         oval((c.y - 0.003, c.z), 0.0032, 0.0026)(q.y, q.z)))
    zt = max(v.co.z for v in p.bm.verts)

    def pink(q, n):   # the art's pink coming through the thin skin at its edges and toward the rolled ends
        t = min(max((q.x + L / 2) / L, 0.0), 1.0)
        edge = abs(q.y) / at(t)[0]
        end = ramp(0.62, 0.95, abs(q.x) / (L / 2))
        w = 0.5 * ramp(0.5, 0.95, edge) * ramp(0.6, 0.15, q.z / zt) + 0.55 * end
        return (mix('#f2a493', '#e8806f', end), min(w, 0.8)) if w > 0.02 else None
    p.tint(f0, pink, mats=('WingRawSkin',))
    lo = Vector([min(v.co[i] for v in p.bm.verts) for i in range(3)])
    hi = Vector([max(v.co[i] for v in p.bm.verts) for i in range(3)])
    S = Matrix.Diagonal((0.064 / (hi.x - lo.x), 0.044 / (hi.y - lo.y), 0.02 / (hi.z - lo.z), 1.0))
    moved(p, 0, S)   # 6.4 x 4.4 x 2.0 cm, as the art's wings
    return done(p, 'wing', col)


def raw_skin(col):
    """猪肉皮 → a strip of pork skin: the rind on top with its fine pores (PorkSkin), the pink inner side (Meat)
    under it and the fat showing along its cut edges (Fat), a little arched across, curling up at its ends and
    rippled along its length."""
    p = Part()
    prof = [(-0.0125, 0.0), (-0.006, 0.0016), (0.0, 0.0021), (0.006, 0.0016), (0.0125, 0.0)]

    def curl(q, u, s):
        return Vector((q.x, q.y + 0.0035 * math.sin(math.pi * u),
                       q.z + 0.008 * (2 * u - 1) ** 2 + 0.0016 * math.sin(3 * math.pi * u + 0.6)))
    with p.soft():
        skin_sheet(p, Matrix(), prof, 0.072, t=0.0065, nx=6, deform=curl)
    return done(p, 'skin', col)


# ---------------------------------------------------------------- vegetables

def raw_tomato(col):
    """番茄 → a wedge cut from a tomato, a sixth of it: the shiny red skin (TomatoRed) round its back, its two cut faces
    the orange-red flesh (TomatoFlesh) inside the red wall, with the seeds in their yellow jelly (TomatoSeed) in the
    hollow of each face between wall and core; lying on a cut face."""
    p = Part()
    r, rz, span = 0.037, 0.031, math.radians(62)
    W = Matrix(((1, 0, 0, 0), (0, 0, -1, 0), (0, 1, 0, 0), (0, 0, 0, 1)))   # local y up: the face at phi = 0 below
    f0 = len(p.bm.faces)
    with p.soft():
        sector(p, W, r, rz, span, 'TomatoRed', 'TomatoFlesh', rows=8, rim=0.13)
    Wi = W.inverted()
    locule = oval((0.5 * r, 0.0), 0.2 * r, 0.6 * rz)

    def seeds(q):   # the jelly of the seed hollow on each cut face, an oval along the core, its edge lobed
        q = Wi @ q
        best = -1.0
        for a in (0.0, span):   # each cut face: its plane through the core at angle a
            off = -math.sin(a) * q.x + math.cos(a) * q.y
            rho = math.cos(a) * q.x + math.sin(a) * q.y
            near = (0.0018 - off) if a == 0.0 else (0.0018 + off)
            best = max(best, min(near, locule(rho, q.z) + 0.12 * math.sin(9 * q.z / rz + 4 * a)))
        return best
    paint(p, f0, 'TomatoSeed', seeds)
    return done(p, 'tomato', col)


def raw_gourd(col):
    """瓜菜 → a chunk of cucumber cut across: the dark green skin (CucumberGreen) dotted with pale warts, both cut
    ends the pale flesh (CucumberFlesh) round the three-lobed core of seeds (CucumberSeed); lying on its side."""
    p = Part()
    R, L = 0.0165, 0.034
    cs = [Vector((-L / 2 + L * i / 24, 0.0, 0.0)) for i in range(25)]
    rs = [R * (1 + 0.02 * math.sin(7 * i / 24 + 0.5)) for i in range(25)]
    f0 = len(p.bm.faces)
    with p.soft():
        pa_canal(p, cs, rs, 'CucumberGreen', sides=10, spacing=0.8, lo=0.005, hi=0.01, ends=('flat', 'flat'))
    p.bm.verts.ensure_lookup_table()
    xe = max(abs(v.co.x) for v in p.bm.verts)
    paint(p, f0, 'CucumberFlesh', lambda q: abs(q.x) - (xe - 0.0009))

    def seeds(q):   # the seed core: a rounded three-lobed patch in the middle of each cut face
        a = math.atan2(q.z, q.y)
        return min(abs(q.x) - (xe - 0.0012), 0.5 * R * (1 + 0.22 * math.cos(3 * a + 0.5)) - math.hypot(q.y, q.z))
    paint(p, f0, 'CucumberSeed', seeds)
    rnd = random.Random(5)
    for k in range(9):   # warts, staggered round the skin
        a = 2 * math.pi * (k * 0.382 + rnd.uniform(-0.05, 0.05))
        x = -L / 2 + 0.006 + (L - 0.012) * ((k * 0.618) % 1.0)
        nrm = Vector((0.0, math.cos(a), math.sin(a)))
        R_ = nrm.to_track_quat('Z', 'Y').to_matrix()
        p.blob(Vector((x, 0.0, 0.0)) + nrm * (R - 0.0004), 0.0019, 'CucumberSeed', squash=(1.0, 1.0, 0.65), segs=(6, 2),
               deform=lambda w, R_=R_: R_ @ w)
    return done(p, 'gourd', col)


def raw_radish(col):
    """萝卜 → a roll-cut chunk of white radish (滚刀块): a wedge of the root between two slanting cuts, the creamy
    skin round its curved back (RadishArtSkin) washed pale green, as near the radish's shoulder, the pale juicy
    flesh (RadishArtFlesh, its fine rays painted on) on its cut faces, every edge rounded; lying on a cut face."""
    p = Part()
    R, span = 0.031, math.radians(100)
    lat = (-1.0, -0.66, 0.0, 0.66, 1.0)
    ends = (Vector((1.0, 0.0)), Vector((math.cos(span), math.sin(span))))   # each cut slants toward one side

    def F(u, v, w):
        th = span * (w + 1) / 2
        core = Vector((0.15 * R, 0.0)).lerp(0.15 * R * ends[1], (w + 1) / 2)   # a narrow flat face along the core
        q = core.lerp(Vector((R * math.cos(th), R * math.sin(th))), (v + 1) / 2)
        x0, x1 = -(0.0115 + 0.25 * q.dot(ends[0])), 0.0115 + 0.25 * q.dot(ends[1])   # two flat cuts
        return Vector((x0 + (x1 - x0) * (u + 1) / 2, q.x, q.y))
    f0 = len(p.bm.faces)
    with p.soft():
        lattice_box(p, 'RadishArtFlesh', jittered(F, 0.0004, 31, flat_foot=False), lat, lat, lat)
    paint(p, f0, 'RadishArtSkin', lambda q: math.hypot(q.y, q.z) - (R - 0.0024))
    p.tint(f0, lambda q, n: ('#cfd99c', 0.55 * min(1.0, max(0.0, (math.atan2(q.z, q.y) / span - 0.15) / 0.7))),
           mats=('RadishArtSkin',))
    return done(p, 'radish', col)


def raw_potato(col):
    """土豆 → a chunk of peeled potato as the knife leaves it: broad flat cuts and the peeler's narrow facets round a
    rounded lump, every edge softened, pale yellow (PotatoArtFlesh, softly mottled); lying on its broadest cut."""
    p = Part()
    a, b, c = 0.023, 0.019, 0.019
    planes = [((0.0, 0.0, -1.0), 0.0095), ((0.78, 0.15, 0.6), 0.0125), ((-0.62, 0.48, 0.55), 0.0135),
              ((0.05, -0.85, 0.42), 0.013), ((-0.85, -0.3, -0.1), 0.0185), ((0.3, 0.9, -0.1), 0.0155),
              ((0.55, -0.5, -0.4), 0.0165)]
    planes = [(Vector(n).normalized(), h) for n, h in planes]

    def shape(d):
        t = 1 / math.sqrt((d.x / a) ** 2 + (d.y / b) ** 2 + (d.z / c) ** 2)
        for n, h in planes:
            k = n.dot(d)
            if k > 1e-6:
                t = min(t, h / k)
        return d * t * wobble(d, 0.015, 3.0)
    with p.soft():
        ball(p, 'PotatoArtFlesh', shape, lat=lattice(5))
    return done(p, 'potato', col)


def raw_chili(col):
    """辣椒 → a whole red chilli (ChiliRed, glossy): a long pod, fat at the shoulder, tapering and bowing to a tip that
    curls up off the wok, its green calyx (CalyxGreen) gripping the shoulder in round lobes and a short stalk hooking
    up from it to a cut end; lying on its side."""
    p = Part()
    n = 30
    cs, rs = [], []
    for i in range(n + 1):
        t = i / n
        r = 0.0088 * (1 - t ** 1.7) ** 0.75 * (0.93 + 0.07 * math.sin(math.pi * min(1.0, t * 3))) + 0.0011
        lift = 0.009 * max(0.0, (t - 0.72) / 0.28) ** 2
        cs.append(Vector((-0.056 + 0.112 * t, 0.014 * math.sin(math.pi * t * 0.9) - 0.006 * t, r + lift)))
        rs.append(r)
    f0 = len(p.bm.faces)
    with p.soft():
        pa_canal(p, cs, rs, 'ChiliRed', sides=7, spacing=1.15, lo=0.0072, hi=0.016)
    T = (cs[3] - cs[0]).normalized()
    A = pa_normal_to(T)
    B = T.cross(A)
    c0 = cs[0] - T * rs[0]   # the shoulder's tip, where the stalk comes out

    def calyx(q):
        d = q - c0
        f = math.atan2(d.dot(B), d.dot(A))
        return 0.0068 * (1 + 0.28 * math.cos(5 * f + 0.4)) - d.dot(T)
    paint(p, f0, 'CalyxGreen', calyx)
    up = Vector((0.0, 0.0, 1.0))
    stalk = [c0 + T * 0.003, c0 - T * 0.003, c0 - T * 0.008 + up * 0.002, c0 - T * 0.011 + up * 0.0062 + A * 0.001,
             c0 - T * 0.012 + up * 0.0105 + A * 0.002]
    with p.soft():
        pa_canal(p, [stalk[0].lerp(stalk[1], k / 3) for k in range(3)] + stalk[1:],
                 [0.0027, 0.0027, 0.0026, 0.0025, 0.0024, 0.0023, 0.0023], 'CalyxGreen', sides=5, spacing=1.6,
                 lo=0.004, hi=0.007, ends=(True, 'flat'))
    return done(p, 'chili', col)


def raw_mushroom(col):
    """菌菇 → a whole shiitake standing on its stem: the brown domed cap (ShiitakeCap) scored on top with a cream
    cross (ShiitakeFlesh), its rim rolled under, the pale gills underneath lined from the stem out (ShiitakeGill
    between ShiitakeFlesh), the thick pale stem (ShiitakeFlesh) with its cut end (ShiitakeCut)."""
    p = Part()
    R, H, T, rs, Ls, z0 = 0.026, 0.017, 0.0085, 0.0062, 0.028, 0.028   # cap, dome, rim, stem; the cap's rim height
    G = 8   # gill lines
    step = 2 * math.pi / G
    even = [math.pi * j / G for j in range(2 * G)]
    bunched = [i * step + f * step for i in range(G) for f in (-0.12, 0.12)]   # on the gills, a narrow column a line

    def ring(r, z, psis):
        return [Vector((r * math.cos(s), r * math.sin(s), z0 + z)) for s in psis]
    prof = [(0.55 * R, 0.86 * H), (0.88 * R, 0.48 * H), (R, 0.02 * H), (0.95 * R, -0.42 * T), (0.82 * R, -0.62 * T),
            (0.6 * R, -0.56 * T), (0.32 * R, -0.46 * T)]
    rings = [ring(r, z, even if i < 5 else bunched) for i, (r, z) in enumerate(prof)]
    gill = [('ShiitakeGill' if j % 2 else 'ShiitakeFlesh') for j in range(2 * G)]
    mats = ['ShiitakeCap'] * 4 + ['ShiitakeFlesh', 'ShiitakeFlesh', gill, gill]
    f0 = len(p.bm.faces)
    with p.soft():
        mu_cage(p, rings, (Vector((0.0, 0.0, z0 + H)), Vector((0.0, 0.0, z0 - 0.42 * T))), mats)
        m = 8
        srings = []
        for f, r in ((0.0, rs * 0.92), (0.02, rs * 1.0), (0.35, rs * 1.04), (0.75, rs * 0.98), (1.0, rs * 0.86)):
            z = Ls * (1 - f) + 0.0015 * f
            srings.append([Vector((r * math.cos(2 * math.pi * j / m) + 0.0015 * f, r * math.sin(2 * math.pi * j / m),
                                   z)) for j in range(m)])
        mu_cage(p, srings, (Vector((0.0, 0.0, Ls + 0.003)), Vector((0.0015, 0.0, 0.0))),
                ['ShiitakeFlesh'] * 5 + ['ShiitakeCut'])

    def cross(q):   # the two cream strokes over the top, widest where they cross
        d = Vector((q.x, q.y))
        on_top = q.z - (z0 + 0.62 * H)
        best = -1.0
        for a in (0.5, 0.5 + math.pi / 2):
            along = abs(d.x * math.cos(a) + d.y * math.sin(a))
            across = abs(-d.x * math.sin(a) + d.y * math.cos(a))
            best = max(best, 0.0032 * (1 - along / (0.62 * R)) - across)
        return min(on_top, best)
    paint(p, f0, 'ShiitakeFlesh', cross)
    return done(p, 'mushroom', col)


def raw_bamboo(col):
    """笋 → a slice of bamboo shoot cut along its length: a rounded triangle tapering from its broad base to the tip,
    both broad faces the pale cut flesh (BambooCut) crossed by the arcs of its chambers (BambooChamber), its rounded
    rim the yellow of the shoot (BambooFlesh); lying flat."""
    p = Part()
    Lb, W0, t = 0.052, 0.036, 0.0072

    def surf(u, v):   # u from the broad base to the tip, v across
        w = W0 * (1 - 0.86 * u ** 1.2)
        s = 2 * v - 1
        x = (u - 0.5) * Lb - 0.0045 * (1 - s * s) * (1 - u) ** 3   # the base bowed out
        return Vector((x, s * w / 2, 0.0015 * math.sin(math.pi * u)))
    f0 = len(p.bm.faces)
    with p.soft():
        sheet(p, surf, 12, 4, t, 'BambooFlesh')

    def face(q):   # how far into the band along either broad face
        return abs(q.z - 0.0015 * math.sin(math.pi * (q.x / Lb + 0.5))) - (t / 2 - 0.0013)
    paint(p, f0, 'BambooCut', face)

    def chambers(q):   # three arcs across the faces where the chambers are, bowed toward the tip
        u = q.x / Lb + 0.5 - 0.5 * (q.y / W0) ** 2
        return min(face(q) - 0.0002, max(0.034 - abs(u - k) for k in (0.25, 0.45, 0.63)))
    paint(p, f0, 'BambooChamber', chambers)
    return done(p, 'bamboo', col)


# ---------------------------------------------------------------- leaves, pickles, pancake

def greens_leaf(p, L, W, R, seed, M):
    """One leaf of raw_greens, built flat along x from its stalk's cut end, then curled and placed by M: a pale thick
    stalk running up into the midrib of a broad round-tipped blade with a crinkled margin; thicker than 3 mm all over.
    Its colours painted on (GreensArtLeaf takes them): the stalk and midrib pale, the margin a darker green."""
    hw = [(0.0, 0.0055), (0.28, 0.0085), (0.42, 0.015), (0.62, W / 2), (0.8, 0.92 * W / 2), (0.93, 0.6 * W / 2),
          (1.0, 0.004)]
    th = [(0.0, 0.0068), (0.28, 0.006), (0.45, 0.0044), (1.0, 0.0041)]

    def mid(u, v):
        return (u * L, (2 * v - 1) * interp(hw, u))

    def thick(u, v):
        return interp(th, u) * (1 - 0.2 * (2 * v - 1) ** 2)
    n0, f0 = len(p.bm.verts), len(p.bm.faces)
    with p.soft():
        leaf_cage(p, mid, thick, 8, 5, 'GreensArtLeaf')

    def colour(q, n):
        u = q.x / L
        edge = abs(q.y) / max(interp(hw, min(max(u, 0.0), 1.0)), 1e-4)
        stalk = ramp(0.42, 0.26, u)
        rib = 0.45 * ramp(0.0045, 0.0015, abs(q.y)) * ramp(0.95, 0.75, u)
        dark = 0.5 * ramp(0.45, 0.95, edge) * ramp(0.32, 0.5, u)
        if stalk > 0.05 or rib > 0.05:
            return ('#eef0d2', 0.85 * stalk) if stalk >= rib else ('#e2ecb4', rib)
        return ('#6f9a3e', dark) if dark > 0.02 else None
    p.tint(f0, colour, mats=('GreensArtLeaf',))
    curl = curled(R)

    def shape(q):
        u = q.x / L
        edge = abs(q.y) / max(interp(hw, min(max(u, 0.0), 1.0)), 1e-4)
        q = q + Vector((0.0, 0.0, 0.0032 * math.sin(470 * q.x + 230 * abs(q.y) + seed) * ramp(0.35, 0.55, u) * edge ** 2))
        q = curl(q)
        return M @ Vector((q.x, q.y, q.z + 0.016 * u * u - 0.004 * u))
    bent(p, n0, shape)


def raw_greens(col):
    """时蔬 → a small bunch of leafy greens: two leaves on thick pale stalks, the inner one nested in the outer, their
    broad round-tipped blades curled up at the sides and crinkled at the margin, each more than 3 mm thick and closed;
    the light yellow-green of the art (GreensArtLeaf, its veins painted on), pale up the stalks and midribs and darker
    at the margins; lying on the outer leaf's back."""
    p = Part()
    greens_leaf(p, 0.095, 0.058, 0.026, 0.0, Matrix())
    greens_leaf(p, 0.074, 0.042, 0.019, 1.7, Matrix.Translation((0.008, 0.0, 0.0052)) @ Matrix.Rotation(0.18, 4, 'Z'))
    return done(p, 'greens', col)


def perilla_leaf(p, L, W, seed, M, green=0.0):
    """One perilla leaf for raw_perilla, built flat along x from its stalk: ovate with a long point and a toothed
    margin, folded a little along its midrib, cupped and drooping, placed by M; 3 mm thick. Purple (PerillaArtLeaf)
    going olive green toward its margin as the art paints it (more of it by `green`), a deeper purple underneath."""
    nu, nv = 9, 3

    def half(u, v):
        w = W / 2 * math.sin(math.pi * min(1.0, 0.05 + 0.95 * u ** 0.7)) ** 1.1 + 0.0012
        i = round(u * (nu - 1))
        if v in (0.0, 1.0) and 0 < i < nu - 1:   # the toothed margin
            w *= 1.0 + (0.42 if i % 2 else -0.16)
        return w

    def mid(u, v):
        return (u * L, (2 * v - 1) * half(u, v))

    n0, f0 = len(p.bm.verts), len(p.bm.faces)
    with p.soft():
        leaf_cage(p, mid, lambda u, v: 0.0036 - 0.0005 * abs(2 * v - 1), nu, nv, 'PerillaArtLeaf')

    def colour(q, n):
        if n.z < -0.3:
            return '#6e3058', 0.35
        edge = abs(q.y) / max(half(min(max(q.x / L, 0.0), 1.0), 0.5), 1e-4)
        w = min(0.85, (0.55 + 0.4 * green) * ramp(0.45 - 0.3 * green, 1.0, edge) + 0.3 * green)
        return ('#8f9a52', w) if w > 0.02 else None
    p.tint(f0, colour, mats=('PerillaArtLeaf',))
    curl = curled(0.05)

    def shape(q):   # cupped, drooping toward the tip, a little wavy
        c = curl(q)
        return M @ Vector((c.x, c.y, c.z - 0.012 * (q.x / L) ** 2 + 0.003 * math.sin(seed + 90 * q.x)))
    bent(p, n0, shape)


def raw_perilla(col):
    """紫苏 → a small clump of perilla leaves: three serrated leaves fanning from a short bundle of stalks
    (PerillaArtStalk), cupped and drooping over each other, purple washed with olive green (PerillaArtLeaf, its veins
    painted on), each more than 3 mm thick and closed."""
    p = Part()
    for k, (yaw, z, L, W, green) in enumerate(((-0.48, 0.0, 0.064, 0.038, 0.0), (0.44, 0.0068, 0.058, 0.035, 0.45),
                                               (-0.02, 0.0136, 0.068, 0.04, 0.1))):
        perilla_leaf(p, L, W, 1.3 * k, Matrix.Translation((0.0, 0.0, z + 0.004)) @ Matrix.Rotation(yaw, 4, 'Z'),
                     green)
    soft_tube(p, [Vector((-0.024, 0.003, 0.003)), Vector((-0.016, 0.002, 0.0038)), Vector((-0.006, 0.001, 0.0058)),
                  Vector((0.004, 0.0, 0.0085))], 0.0026, 'PerillaArtStalk', sides=6)   # the stalks, bundled
    return done(p, 'perilla', col)


def raw_sauerkraut(col):
    """酸菜 → a long piece of pickled mustard green folded loosely over on itself, as it hangs over the crock's rim in
    the art: pale yellow-green along its thicker stem side (SauerPale), wavy and thinning to the darker olive leaf
    ruffled along its other edge (SauerDark), both veined and washed toward the art's colours; the upper layer
    turned a little aside and sagging toward its free end."""
    p = Part()
    L, W, Rf, beta = 0.1, 0.048, 0.0085, math.radians(150)

    def mid(u, v):
        return ((u - 0.4) * L, (v - 0.5) * W * (1 - 0.2 * (2 * u - 1) ** 2))

    n0, f0 = len(p.bm.verts), len(p.bm.faces)
    with p.soft():
        leaf_cage(p, mid, lambda u, v: 0.0039 - 0.0008 * v, 11, 4, 'SauerPale')
    paint(p, f0, 'SauerDark', lambda q: q.y - W * (0.04 + 0.1 * math.sin(120 * q.x + 0.7)))
    p.tint(f0, lambda q, n: ('#dedc9c', 0.78), mats=('SauerPale',))
    p.tint(f0, lambda q, n: ('#66743a', 0.45), mats=('SauerDark',))

    def fold(q):   # ruffle the leafy edge and wave it along, then fold the far part loosely over the near one
        ruffle = 0.0046 * math.sin(230 * q.x + 1.0) * ramp(-0.006, W * 0.5, q.y)
        x, z = q.x, q.z + ruffle + 0.0035 * math.sin(55 * q.x + 0.5)
        if x <= 0:
            return Vector((x, q.y, z))
        r = Rf - z
        phi = min(x / Rf, beta)
        P = Vector((r * math.sin(phi), q.y, Rf - r * math.cos(phi)))
        rest = x - Rf * beta
        if rest > 0:
            P += Vector((math.cos(beta), 0.0, math.sin(beta))) * rest
            P.z -= 0.12 * rest * rest / L   # sagging toward its free end
        turn = 0.5 * min(1.0, x / (Rf * beta + 0.02))   # the upper layer turned aside
        return Matrix.Rotation(turn, 3, 'Z') @ P
    bent(p, n0, fold)
    return done(p, 'sauerkraut', col)


def raw_pancake(col):
    """薄饼备料 → a thin pancake folded in four: a quarter round, its two folded edges plump and round, its curved edge
    where the layers show (BingSide), pale (BingCake) with golden spots where it browned (BingSpot) on both faces, a
    little domed and wavy."""
    p = Part()
    R = 0.088

    def mid(u, v):
        rho, a = R * (0.06 + 0.94 * u), v * math.pi / 2
        return (rho * math.cos(a), rho * math.sin(a))

    n0, f0 = len(p.bm.verts), len(p.bm.faces)
    with p.soft():
        leaf_cage(p, mid, lambda u, v: 0.0078 - 0.0018 * u, 6, 6, 'BingCake')
    paint(p, f0, 'BingSide', lambda q: math.hypot(q.x, q.y) - (R - 0.0038))
    rnd = random.Random(12)
    spots = []
    for k in range(9):
        rho, a = R * math.sqrt(rnd.uniform(0.08, 0.8)), rnd.uniform(0.15, math.pi / 2 - 0.15)
        spots.append((rho * math.cos(a), rho * math.sin(a), rnd.uniform(0.0045, 0.0075)))
    paint(p, f0, 'BingSpot', lambda q: min(R - 0.006 - math.hypot(q.x, q.y),
                                           max(rr - math.hypot(q.x - x, q.y - y) for x, y, rr in spots)))

    def shape(q):
        rho, a = math.hypot(q.x, q.y), math.atan2(q.y, q.x)
        return Vector((q.x, q.y, q.z + 0.006 * (1 - (rho / R) ** 2) + 0.0035 * math.sin(5 * a + 0.8) * (rho / R) ** 2))
    bent(p, n0, shape)
    return done(p, 'pancake', col)


def raw_pickle_base(col):
    """盐渍辅料包 → a clump of the salted pickles as the art heaps them: a low lumpy heap of the dark olive leaves
    (YanLeaf, veined) all but hidden under the pale yellow-green shreds of the salted stems (YanShred) lying crossed
    every way over it and down its sides, and a couple of coarse salt crystals (YanSalt)."""
    from mathutils.bvhtree import BVHTree
    p = Part()
    r, h = 0.029, 0.019

    def shape(d):
        k = wobble(d, 0.1, 4.0)
        return Vector((d.x * r * k, d.y * r * 0.88 * k, d.z * h * k if d.z > 0 else d.z * h * 0.2))
    with p.soft():
        ball(p, 'YanLeaf', shape, lat=lattice(3))
    tree = BVHTree.FromBMesh(p.bm)
    f1 = len(p.bm.faces)

    def on(x, y):   # the point of the heap over (x, y) and its normal, or None past its edge
        hit, nrm, _, _ = tree.ray_cast(Vector((x, y, 0.2)), Vector((0.0, 0.0, -1.0)))
        return (hit, nrm) if hit is not None else None
    rnd = random.Random(9)
    k = 0
    while k < 20:   # short shreds crossed every way over the heap and down its sides, a little sunk into it
        c = Vector((rnd.uniform(-0.8, 0.8) * r, rnd.uniform(-0.75, 0.75) * r * 0.88, 0.0))
        a, L, bend = rnd.uniform(0, math.pi), rnd.uniform(0.02, 0.03), rnd.uniform(-0.5, 0.5)
        hits = [on(c.x + t * L * math.cos(a + bend * t), c.y + t * L * math.sin(a + bend * t)) for t in (-0.5, 0.0, 0.5)]
        if any(hit is None for hit in hits):
            continue
        soft_tube(p, [hit + nrm * 0.0007 for hit, nrm in hits], 0.0017, 'YanShred', sides=4)
        k += 1
    p.tint(f1, lambda q, n: ('#e6e0a0', 0.6), mats=('YanShred',))
    for k, (x, y) in enumerate(((0.006, -0.004), (-0.011, 0.008))):
        hit, nrm = on(x, y)
        crystal(p, hit + nrm * 0.0028, 0.0042, mat='YanSalt', rot=0.7 * k)
    return done(p, 'pickle_base', col)


# ---------------------------------------------------------------- whole fish and the crab

def fish_eye(p, c, nrm, r):
    """A fish's round eye set into its head at c facing nrm: a golden iris domed out of the surface with a dark
    pupil domed out of it (FishIris, FishEye), cheaper than the display models' own."""
    R = nrm.to_track_quat('Z', 'Y').to_matrix()
    p.blob(c - nrm * r * 0.12, 1.0, 'FishIris', segs=(8, 4), deform=lambda v: R @ Vector((v.x * r, v.y * r, v.z * r * 0.42)))
    rp = r * 0.56
    p.blob(c + nrm * r * 0.18, 1.0, 'FishEye', segs=(6, 3),
           deform=lambda v: R @ Vector((v.x * rp, v.y * rp, v.z * rp * 0.42)))


def sides(p, f0):
    """Ray casters onto the faces added to p since it had f0 faces (a fish's body in its own frame), from its near
    flank (-y) and from its far one: cast((x, 0, z)) -> (point, normal) of the flank there."""
    return caster(p, f0, Vector((0.0, -1.0, 0.0))), caster(p, f0, Vector((0.0, 1.0, 0.0)))


def flank_fin(p, cast, outline, mat, thick=0.0035, rise=0.004, x0=None):
    """A fin lying along a flank (a pectoral fin) through the side view's outline [(x, z)], lifting off it toward its
    tip by up to `rise`: a rounded shell for soft()."""
    x0 = outline[0][0] if x0 is None else x0
    span = max(x for x, _ in outline) - x0
    inner, outer = [], []
    for x, z in outline:
        hit, nrm = cast((x, 0.0, z))
        lift = 0.0006 + rise * max(0.0, (x - x0) / span) ** 1.5
        inner.append(hit + nrm * lift)
        outer.append(hit + nrm * (lift + thick))
    shell(p, inner, outer, mat)


def lips(p, cast, pts, r, mat):
    """Rolled lips round the front of a fish's mouth: a tube from the near flank's points [(x, z)] round the front to
    the far flank's."""
    near = []
    for x, z in pts:
        hit, nrm = cast((x, 0.0, z))
        near.append(hit + nrm * r * 0.3 if hit is not None else Vector((x, -0.004, z)))
    front = Vector((pts[-1][0] - r * 0.6, 0.0, pts[-1][1]))
    p.tube(near + [front] + [Vector((q.x, -q.y, q.z)) for q in reversed(near)], r, mat, sides=4)


def on_its_side(p):
    """A fish built in its own frame (x along it, z to its back, y across) turned to lie on its side."""
    moved(p, 0, Matrix.Rotation(math.pi / 2, 4, 'X'))


def raw_fish(col):
    """普通整鱼 → the whole carp, lying on its side: its silvery scaled skin (CarpSkin) painted grey along the back and
    bronze down the flank to the pale belly (carp_colour), the smooth head (CarpHead) in front of the gill cover, a
    big golden eye and a pink pectoral fin on each side, the grey forked tail and long dorsal fin (CarpFin) and the
    pink pelvic and anal fins (FishFin), every fin thick enough to be closed and rounded, and rolled pink lips."""
    p = Part()
    f0 = len(p.bm.faces)
    with p.soft():
        hull(p, [CARP_BODY[i] for i in (0, 2, 3, 4, 5, 7, 9, 11, 13)], 'CarpSkin', n=8)
    gill = sorted((z, x) for x, z in CARP_GILL)
    paint(p, f0, 'CarpHead', lambda q: interp(gill, q.z) - q.x)
    near, far = sides(p, f0)
    with p.soft():
        slab(p, CARP_TAIL[::2], 'CarpFin', 0.0055)
        slab(p, [CARP_DORSAL[i] for i in (0, 3, 6, 9, 12, 15, 18, 21, 23, 24, 25)], 'CarpFin', 0.005)
        slab(p, [(0.2, -0.039), (0.2234, -0.026), (0.2404, -0.0224), (0.2414, -0.0267), (0.2224, -0.0384),
                 (0.2062, -0.0405)], 'FishFin', 0.0045)   # anal
        slab(p, [(0.147, -0.043), (0.1652, -0.0419), (0.182, -0.0439), (0.1898, -0.051), (0.1622, -0.0503),
                 (0.149, -0.047)], 'FishFin', 0.0045)     # pelvic
        for cast in (near, far):
            flank_fin(p, cast, [(0.088, -0.0202), (0.1146, -0.023), (0.1323, -0.0319), (0.1355, -0.0353),
                                (0.115, -0.0411), (0.0931, -0.0344)], 'FishFin')
    lips(p, near, ((0.019, -0.0038), (0.011, -0.001), (0.0045, 0.0008)), 0.003, 'FishFin')
    for cast in (near, far):
        hit, nrm = cast((0.0373, 0.0, 0.0059))
        fish_eye(p, hit, nrm, 0.0084)
    tops = [(x, t) for x, t, b, w in CARP_BODY]
    bots = [(x, b) for x, t, b, w in CARP_BODY]
    p.tint(f0, carp_colour(tops, bots), mats=('CarpSkin', 'CarpHead'))
    on_its_side(p)
    return done(p, 'fish', col)


# the spiny dorsal of the mandarin fish with one point a spine and its valleys, and its pectoral fin
GUIYU_SPINES = [(0.079, 0.040), (0.0812, 0.0452), (0.0937, 0.0655), (0.0962, 0.0575), (0.1108, 0.0756),
                (0.1136, 0.0668), (0.1268, 0.0787), (0.1287, 0.069), (0.1408, 0.0784), (0.1421, 0.066),
                (0.155, 0.0727), (0.1561, 0.0614), (0.166, 0.0616), (0.1761, 0.0466), (0.18, 0.0345), (0.12, 0.046)]
GUIYU_PECTORAL = [(0.1004, -0.0105), (0.1284, -0.0046), (0.1442, -0.0104), (0.1417, -0.0255), (0.1257, -0.0377),
                  (0.1019, -0.0279)]


def raw_mandarin_fish(col):
    """鳜鱼 → the whole mandarin fish, lying on its side: its pale yellowish skin (GuiyuSkin, finely mottled) olive
    along the back (guiyu_colour) and blotched dark all over (MandarinSpot), the gaping pink mouth under a jutting
    lower jaw, a big eye on each side, the spiny dorsal fin with rounded spines, the soft dorsal, the rounded tail,
    the pectoral, pelvic and anal fins (MandarinFin), every one thick enough to be closed and rounded."""
    p = Part()
    f0 = len(p.bm.faces)
    with p.soft():
        hull(p, [GUIYU_BODY[i] for i in (0, 1, 3, 5, 6, 8, 10, 12)], 'GuiyuSkin', n=8)
    near, far = sides(p, f0)
    mouth = poly_field([(-0.004, 0.004), (0.0111, 0.0092), (0.0227, 0.0061), (0.0325, -0.0004), (0.0399, -0.0142),
                        (0.02, -0.0105), (-0.004, -0.009)])
    paint(p, f0, 'FishGill', lambda q: mouth(q.x, q.z))
    rnd = random.Random(14)
    blots = []
    for cast in (near, far):   # dark blotches over both flanks, each two overlapping rounds
        for k in range(9):
            x = 0.045 + 0.17 * (k + rnd.uniform(0.1, 0.9)) / 9
            z = rnd.uniform(-0.025, 0.03) * (1 - abs(x - 0.12) / 0.2)
            hit, _ = cast((x, 0.0, z))
            if hit is not None:
                rr = rnd.uniform(0.0055, 0.0085)
                d = Vector((rnd.uniform(-1, 1), 0.0, rnd.uniform(-1, 1))).normalized() * rr * 0.7
                blots += [(hit, rr), (hit + d, rr * 0.7)]
    paint(p, f0, 'MandarinSpot', lambda q: max(rr - (q - c).length for c, rr in blots))
    with p.soft():
        slab(p, GUIYU_TAIL[::2], 'MandarinFin', 0.0055)
        slab(p, GUIYU_SPINES, 'MandarinFin', 0.0045)
        slab(p, [GUIYU_SOFT[i] for i in (0, 2, 3, 4, 6, 8)], 'MandarinFin', 0.0045)
        slab(p, [(0.1799, -0.0404), (0.1911, -0.0381), (0.2147, -0.0127), (0.2345, -0.0193), (0.2318, -0.0353),
                 (0.2088, -0.0382)], 'MandarinFin', 0.0045)   # anal
        slab(p, [(0.0951, -0.0453), (0.1232, -0.0385), (0.1505, -0.0455), (0.15, -0.0556), (0.1307, -0.0618),
                 (0.1095, -0.0577)], 'MandarinFin', 0.0045)   # pelvic
        for cast in (near, far):
            flank_fin(p, cast, GUIYU_PECTORAL, 'MandarinFin', rise=0.005)
    lips(p, near, ((0.0412, -0.0118), (0.0281, -0.0134), (0.0079, -0.0124)), 0.0042, 'GuiyuSkin')   # the lower jaw
    for cast in (near, far):
        hit, nrm = cast((0.0413, 0.0, 0.0133))
        fish_eye(p, hit, nrm, 0.0078)
    tops = [(x, t) for x, t, b, w in GUIYU_BODY]
    bots = [(x, b) for x, t, b, w in GUIYU_BODY]
    p.tint(f0, guiyu_colour(tops, bots), mats=('GuiyuSkin',))
    on_its_side(p)
    return done(p, 'mandarin_fish', col)


def raw_fish_head(col):
    """大鱼头 → the big fish head, lying on its side: dark grey crown fading into the pale silvery cheek and the warm
    throat (FishBelly painted by yutou_colour), the gaping pink mouth (MouthPink) between pale rolled lips, a big
    eye on each side in its dark ring, the gill cover's rounded edge over the red gills (GillRed), the pink cut face at
    the back (FishGill) and a stub of dark fin (FishCrown)."""
    p = Part()
    f0 = len(p.bm.faces)
    with p.soft():
        hull(p, [YUTOU_HEAD[i] for i in (0, 1, 2, 3, 5, 7, 9, 11, 12)], 'FishBelly', n=10)
    for mat, poly in (('GillRed', [(0.1354, 0.0298), (0.1353, 0.0225), (0.1313, 0.0082), (0.1186, 0.0047),
                                   (0.1061, -0.0183), (0.0968, -0.0382), (0.0863, -0.0411), (0.1081, -0.0377),
                                   (0.1259, -0.0254), (0.1329, -0.0133), (0.1374, 0.0012), (0.1386, 0.0171)]),
                      ('FishGill', [(0.1527, 0.0522), (0.1766, 0.0389), (0.19, 0.005), (0.19, -0.03), (0.17, -0.032),
                                    (0.1631, 0.0156), (0.156, 0.0314)]),   # the cut face
                      ('MouthPink', [(-0.012, 0.0092), (0.0059, 0.0042), (0.0285, -0.0078), (0.0349, -0.013),
                                     (0.0203, -0.0085), (0.0057, -0.0018), (-0.012, -0.0077)])):
        field = poly_field(poly)
        paint(p, f0, mat, lambda q, field=field: field(q.x, q.z))
    near, far = sides(p, f0)
    for cast in (near, far):   # the gill covers' rounded edges
        for pts in (((0.1214, 0.0398), (0.1318, 0.0317), (0.1402, 0.0206), (0.1444, 0.0052), (0.1432, -0.0102),
                     (0.1379, -0.0201)),
                    ((0.1353, 0.0218), (0.1178, 0.0023), (0.1072, -0.0174), (0.0938, -0.0391))):
            edge = [cast((x, 0.0, z)) for x, z in pts]
            soft_tube(p, [hit + nrm * 0.0008 for hit, nrm in edge if hit is not None], 0.0019, 'FishBelly', sides=5)
    with p.soft():
        slab(p, [(0.1217, 0.0587), (0.1445, 0.067), (0.1399, 0.0595), (0.1612, 0.0575), (0.1471, 0.0481),
                 (0.134, 0.0507)], 'FishCrown', 0.0045)   # a stub of dark fin
    lips(p, near, ((0.0393, -0.0117), (0.0225, 0.0046), (0.0064, 0.0203)), 0.0028, 'FishBelly')
    lips(p, near, ((0.0372, -0.0144), (0.0203, -0.0085), (0.0056, -0.0034)), 0.0034, 'FishBelly')
    for cast in (near, far):
        hit, nrm = cast((0.0574, 0.0, 0.0127))
        fish_eye(p, hit, nrm, 0.0122)
    p.tint(f0, yutou_colour(Vector((0.0, -1.0, 0.0))), mats=('FishBelly',))
    on_its_side(p)
    return done(p, 'fish_head', col)


def crab_shell(p, a, b, front, rim, dome, base, n=12, tooth=0.003):
    """The crab's carapace for soft(): an oval a across and b deep (flatter at the front, -y, `front` deep there),
    domed `dome` above its rim at height `rim`, blunt teeth along the front of its sides, rounding under the rim to
    the belly (CrabBelly) closing it at `base`."""
    tmp = bmesh.new()

    def loop(f, z, teeth=0.0, bump=0.0):
        out = []
        for j in range(n):
            t = 2 * math.pi * j / n
            bb = b if math.sin(t) >= 0 else front
            q = Vector((a * math.cos(t), bb * math.sin(t), 0.0))
            fr = math.sin(t) < -0.15 and abs(math.cos(t)) > 0.3   # the front of the sides
            k = f * (1 + (teeth if fr and j % 2 == 0 else 0.0) / a)
            out.append(tmp.verts.new((q.x * k, q.y * k, z + bump * math.cos(3 * t + 0.6))))
        return out
    rings = [loop(0.45, rim + dome * 0.97), loop(0.86, rim + dome * 0.55, bump=0.0012), loop(1.0, rim, tooth),
             loop(0.96, rim - 0.004, tooth * 0.7), loop(0.7, base)]
    fm = []
    tmp.faces.new(rings[0])
    fm.append('CrabShell')
    for ra, rb, m in zip(rings, rings[1:], ('CrabShell', 'CrabShell', 'CrabShell', 'CrabBelly')):
        for j in range(n):
            tmp.faces.new((ra[j], ra[(j + 1) % n], rb[(j + 1) % n], rb[j]))
            fm.append(m)
    tmp.faces.new(list(reversed(rings[-1])))
    fm.append('CrabBelly')
    piece_in_colours(p, tmp, fm)


def finer(js, k=3):
    """A limb's joints [(point, half width)] with k steps along each segment: crab_colour finds its knuckles and
    darker tips by the count of joints along a limb, which the display crab's legs have more of."""
    out = []
    for (a, wa), (b, wb) in zip(js, js[1:]):
        out += [(a.lerp(b, i / k), wa + (wb - wa) * i / k) for i in range(k)]
    return out + [js[-1]]


def raw_crab(col):
    """蟹 → the whole crab, standing low on its legs: the rounded blue-grey shell edged with blunt teeth along the
    front of its sides (CrabShell, mottled olive), four legs a side splayed out and down, flat and jointed at the
    knee, two big claws held in front with plump palms and closed pincers, beady eyes, the cream-tan belly
    (CrabBelly); its colour painted across it as the display crab's (crab_colour): warming to tan along the edges of
    every segment and round the joints, orange-brown toward the tips, cream under the claws."""
    p = Part()
    rim, base = 0.02, 0.009
    f0 = len(p.bm.faces)
    with p.soft():
        crab_shell(p, 0.042, 0.032, 0.026, rim, 0.013, base, n=10)
    limbs = []
    with p.soft():
        for sx in (1, -1):
            for k, (y0, dy, reach) in enumerate(((-0.012, -0.004, 0.05), (-0.002, 0.003, 0.054), (0.009, 0.01, 0.052),
                                                 (0.018, 0.017, 0.046))):
                a0 = Vector((sx * 0.03, y0, 0.012))
                knee = Vector((sx * (0.03 + reach * 0.55), y0 + dy, 0.02))
                tip = Vector((sx * (0.03 + reach), y0 + dy * 1.8, 0.0015))
                js = [(a0, 0.0045), (knee, 0.0043), (tip, 0.0011 if k < 3 else 0.0026)]
                crab_limb(p, js, ['CrabShell'] * 2, flat=0.55 if k < 3 else 0.35)
                limbs.append(('leg', finer(js)))
            shoulder = Vector((sx * 0.024, -0.019, 0.012))
            wrist = Vector((sx * 0.043, -0.04, 0.016))
            arm = [(shoulder, 0.0052), (wrist, 0.0058)]
            crab_limb(p, arm, ['CrabShell'], flat=0.8)
            limbs.append(('arm', arm))
            palm = [(wrist + Vector((-sx * 0.001, -0.002, 0.0)), 0.0085), (Vector((sx * 0.032, -0.061, 0.017)), 0.0115),
                    (Vector((sx * 0.009, -0.079, 0.012)), 0.0019)]
            crab_limb(p, palm, ['CrabShell'] * 2, flat=0.6)
            limbs.append(('palm', finer(palm)))
            finger = [(Vector((sx * 0.03, -0.064, 0.0245)), 0.0048), (Vector((sx * 0.017, -0.075, 0.0225)), 0.0032),
                      (Vector((sx * 0.008, -0.081, 0.017)), 0.0014)]
            crab_limb(p, finger, ['CrabShell'] * 2, flat=0.75)
            limbs.append(('finger', finger))
    p.tint(f0, crab_colour(limbs, (Vector((0.0, 0.0)), rim, 0.044)), mats=('CrabShell',))
    for sx in (1, -1):
        p.blob((sx * 0.0085, -0.026, rim + 0.007), 0.0028, 'FishEye', segs=(6, 3))
    return done(p, 'crab', col)


# ---------------------------------------------------------------- dried goods

def raw_seafood(col):
    """干贝海味包 → a dried scallop: a squat drum, its sides fibrous (HaiScallop), its top and bottom the pale cut
    faces (HaiScallopTop), a little oval and uneven, the rims rounded."""
    p = Part()
    r, h = 0.0125, 0.0165

    def uneven(q):
        a = math.atan2(q.y, q.x)
        k = 1 + 0.05 * math.cos(2 * a + 0.4) + 0.025 * math.sin(3 * a + 1.0)
        return Vector((q.x * k, q.y * k, q.z + 0.0007 * math.sin(2 * a) * (q.z / h - 0.5) * 2))
    prof = [(0.0, 0.0), (0.55 * r, 0.0), (0.88 * r, 0.0006), (r, 0.0035), (1.03 * r, h * 0.5), (r, h - 0.0035),
            (0.88 * r, h - 0.0006), (0.55 * r, h), (0.0, h)]
    f0 = len(p.bm.faces)
    with p.soft():
        p.lathe(prof, 'HaiScallop', n=12, close_ends=False, deform=uneven)
    paint(p, f0, 'HaiScallopTop', lambda q: abs(q.z - h / 2) - (h / 2 - 0.0016))
    return done(p, 'seafood', col)


PIECES = {
    'flour': (raw_flour, 1),
    'rice': (raw_rice, 1),
    'rice_prep': (raw_rice_prep, 1),
    'pork': (raw_pork, 3),
    'chicken': (raw_chicken, 4),
    'duck': (raw_duck, 3),
    'egg': (raw_egg, 2),
    'kidney': (raw_kidney, 3),
    'fish': (raw_fish, 1),
    'mandarin_fish': (raw_mandarin_fish, 1),
    'crab': (raw_crab, 1),
    'fish_head': (raw_fish_head, 1),
    'wing': (raw_wing, 3),
    'radish': (raw_radish, 3),
    'gourd': (raw_gourd, 3),
    'greens': (raw_greens, 3),
    'tofu': (raw_tofu, 3),
    'bamboo': (raw_bamboo, 3),
    'perilla': (raw_perilla, 3),
    'mushroom': (raw_mushroom, 3),
    'skin': (raw_skin, 3),
    'pickle_base': (raw_pickle_base, 1),
    'sauerkraut': (raw_sauerkraut, 3),
    'pancake': (raw_pancake, 2),
    'seafood': (raw_seafood, 4),
    'tomato': (raw_tomato, 3),
    'chili': (raw_chili, 3),
    'potato': (raw_potato, 3),
}
