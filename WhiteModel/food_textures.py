"""Seamless detail textures for the meat, the egg, the tomato, the fish and the crab in Unity's WatercolorLit
(R = pattern, G = height, B unused), painted rather than photographic: fat veins and seams, fibre strokes, follicle
dots, soft blotches, the creased folds of scrambled egg, the seeds of a cut tomato, fish scales, a crab's mottled
shell, a heap of chopped chilli, crisp fried batter, a leaf's veins and grains of rice, with soft edges and few
octaves so they still read at icon size. Everything tiles: the noise is filtered in the Fourier domain and the
strokes are painted wrapped round the tile.

    python WhiteModel/food_textures.py [--preview DIR]

writes Unity/Assets/Art/Textures/food_{marble,fiber,pores,mottle,curd,seeds,scales,shell,chopped,crisp,veins,
grains}.png (512², linear data; FoodSpritePostprocessor imports them repeated, not sRGB). --preview also writes a
lit, coloured swatch of each (2×2 tiles) to DIR.
Which colour uses which texture, at what scale, tint and relief: DETAIL in food_models/core.py.
"""
import math
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

N = 512
SS = 2   # strokes are painted at twice the size, then box-filtered down
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, '..', 'Unity', 'Assets', 'Art', 'Textures')


# ---------------------------------------------------------------- periodic helpers

def freqs(n=N):
    f = np.fft.fftfreq(n) * n   # cycles per tile
    return np.hypot(f[:, None], f[None, :])


def blur(a, sigma):
    """Gaussian blur that wraps round the tile."""
    if sigma <= 0:
        return a
    f = np.fft.fftfreq(a.shape[0])
    g = np.exp(-2 * (np.pi * sigma) ** 2 * (f[:, None] ** 2 + f[None, :] ** 2))
    return np.real(np.fft.ifft2(np.fft.fft2(a) * g))


def norm(a, lo=None, hi=None):
    lo = a.min() if lo is None else lo
    hi = a.max() if hi is None else hi
    return np.clip((a - lo) / max(hi - lo, 1e-9), 0, 1)


def noise(seed, centre, width=None):
    """Tileable band noise: white noise kept round `centre` cycles per tile (Gaussian band), mean 0.5, ~±0.5."""
    rng = np.random.default_rng(seed)
    r = freqs()
    width = width or centre * 0.5
    band = np.exp(-0.5 * ((r - centre) / width) ** 2)
    band[0, 0] = 0
    a = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((N, N))) * band))
    return 0.5 + a / (a.std() * 5)


def grain_noise(seed, angle, along, across):
    """Tileable noise drawn out along `angle` (radians, image x right, y down): few cycles per tile along the
    grain, more across it, so its contour lines run with the grain like the fat in a cut of pork."""
    rng = np.random.default_rng(seed)
    f = np.fft.fftfreq(N) * N
    fx, fy = f[None, :], f[:, None]
    fa = fx * math.cos(angle) + fy * math.sin(angle)       # frequency along the grain
    fc = -fx * math.sin(angle) + fy * math.cos(angle)      # and across it
    band = np.exp(-0.5 * ((fa / along) ** 2 + (fc / across) ** 2)) * (1 - np.exp(-0.5 * (fc / 1.5) ** 2))
    a = np.real(np.fft.ifft2(np.fft.fft2(rng.standard_normal((N, N))) * band))
    return 0.5 + a / (a.std() * 5)


def sample(a, x, y):
    """Bilinear lookup with wrap-round at float pixel coordinates."""
    n = a.shape[0]
    x, y = x % n, y % n
    x0, y0 = np.floor(x).astype(int), np.floor(y).astype(int)
    fx, fy = x - x0, y - y0
    x1, y1 = (x0 + 1) % n, (y0 + 1) % n
    return (a[y0, x0] * (1 - fx) * (1 - fy) + a[y0, x1] * fx * (1 - fy)
            + a[y1, x0] * (1 - fx) * fy + a[y1, x1] * fx * fy)


def smooth(e0, e1, x):
    t = np.clip((x - e0) / (e1 - e0), 0, 1)
    return t * t * (3 - 2 * t)


YY, XX = np.mgrid[0:N, 0:N].astype(np.float64)


def paint(strokes, soften=0.8):
    """Paints brush strokes wrapped round the tile and returns their coverage (0–1), the brighter one winning
    where they cross. A stroke is a list of (x, y, radius, value) dabs along its path, in tile pixels."""
    S = N * SS
    acc = np.zeros((S, S), np.float32)
    for dabs in strokes:
        xs = [d[0] for d in dabs]
        ys = [d[1] for d in dabs]
        rmax = max(d[2] for d in dabs)
        layer = Image.new('L', (S, S), 0)
        draw = ImageDraw.Draw(layer)
        for ox in (-N, 0, N):
            for oy in (-N, 0, N):
                if max(xs) + ox + rmax < 0 or min(xs) + ox - rmax > N or max(ys) + oy + rmax < 0 or min(ys) + oy - rmax > N:
                    continue
                for x, y, r, v in dabs:
                    X, Y, R = (x + ox) * SS, (y + oy) * SS, max(r * SS, 0.6)
                    draw.ellipse((X - R, Y - R, X + R, Y + R), fill=int(255 * v))
        acc = np.maximum(acc, np.asarray(layer, np.float32) / 255)
    a = acc.reshape(N, SS, N, SS).mean(axis=(1, 3)).astype(np.float64)
    return blur(a, soften)


def stroke(rng, x, y, angle, length, width, value, bend=0.25, taper=(0.25, 0.35), wobble=0.15):
    """Dabs of one tapered, slightly curved stroke from (x, y) along `angle`, as a brush would leave it."""
    steps = max(4, int(length / max(width * 0.35, 0.8)))
    curve = rng.uniform(-bend, bend)
    dabs = []
    a = angle
    for k in range(steps + 1):
        t = k / steps
        ramp = min(1.0, t / taper[0], (1 - t) / taper[1]) if t > 0 and t < 1 else 0.15
        r = width * 0.5 * (0.35 + 0.65 * ramp) * (1 + wobble * math.sin(7 * t + x))
        dabs.append((x, y, r, value * (0.55 + 0.45 * ramp)))
        a += curve / steps * 2.5
        x += math.cos(a) * length / steps
        y += math.sin(a) * length / steps
    return dabs


def striations(k, warp, warp_amp, sharp):
    """Fine parallel lines across the tile (wave vector k: integers, so they tile), wavy by a warp field."""
    phase = 2 * math.pi * (k[0] * XX + k[1] * YY) / N + warp * warp_amp
    c = 0.5 + 0.5 * np.cos(phase)
    return smooth(1 - sharp, 1.0, c)


# ---------------------------------------------------------------- the textures

def marble():
    """Pork lean marbled with fat (猪肉.png): broad soft seams of fat between the muscles, thin fat streaks along
    the grain, and fine fibre grooves in the lean. R = fat, G = fat raised a little over grooved lean."""
    rng = np.random.default_rng(11)
    grain = math.radians(-28)
    wx, wy = (noise(21, 2.5) - 0.5) * 60, (noise(22, 2.5) - 0.5) * 60
    # veins: contour lines of noise drawn out along the grain, wider in places, fading out in others
    base = sample(grain_noise(23, grain, 1.2, 5.0), XX + wx, YY + wy)
    width = 0.01 + 0.014 * smooth(0.35, 0.75, noise(24, 2))
    veins = smooth(width, width * 0.3, np.abs(base - 0.5)) * smooth(0.3, 0.5, noise(25, 1.6))
    base2 = sample(grain_noise(26, grain, 2.0, 10.0), XX + wx * 0.7, YY + wy * 0.7)
    thin = smooth(0.012, 0.003, np.abs(base2 - 0.5)) * smooth(0.4, 0.6, noise(27, 3))
    # short tapered streaks along the grain, like the painted fat lines inside the lean
    streaks = []
    for _ in range(80):
        ang = grain + math.radians(rng.normal(0, 7))
        streaks.append(stroke(rng, rng.uniform(0, N), rng.uniform(0, N), ang, rng.uniform(30, 110),
                              rng.uniform(3.0, 6.5), rng.uniform(0.5, 0.95), bend=0.3))
    s = paint(streaks, soften=0.9)
    fat = np.clip(blur(np.maximum(np.maximum(veins, thin * 0.8), s * 0.85), 0.6), 0, 1)
    # the lean: fine grooves along the grain, wavy
    groove = striations((10, 19), noise(28, 3) - 0.5, 8.0, 0.5)   # wave vector ⟂ the grain (−28°)
    lumpy = noise(29, 5)
    height = 0.5 + 0.3 * blur(fat, 2.5) - 0.08 * blur(groove, 2.0) * (1 - fat) + 0.16 * (lumpy - 0.5)
    return fat, norm(blur(height, 1.0), 0.25, 0.85)


def fiber():
    """Muscle fibres (鸡肉.png): long soft streaks along the grain over fine parallel striations. R = the paler
    streaks, G = ridges along the grain."""
    rng = np.random.default_rng(31)
    warp = noise(32, 3) - 0.5
    lines = striations((4, 19), warp, 10.0, 0.42)               # fine striations, ~19 a tile
    lines2 = striations((7, 37), warp, 14.0, 0.35) * 0.5        # and finer between them
    streaks = []
    for _ in range(46):
        ang = math.radians(-12 + rng.normal(0, 4))
        streaks.append(stroke(rng, rng.uniform(0, N), rng.uniform(0, N), ang, rng.uniform(120, 300),
                              rng.uniform(5.0, 12.0), rng.uniform(0.5, 1.0), bend=0.2, taper=(0.35, 0.45)))
    s = paint(streaks, soften=2.0)
    vary = smooth(0.3, 0.75, noise(33, 2.5))
    pattern = np.clip(s * (0.65 + 0.35 * vary) + 0.06 * lines * (0.4 + 0.6 * vary), 0, 1)
    height = 0.5 + 0.32 * blur(s, 2.5) + 0.14 * blur(lines, 2.0) + 0.02 * lines2 + 0.12 * (noise(34, 4) - 0.5)
    return pattern, norm(height, 0.25, 1.0)


def pores():
    """Poultry and pork skin (鸭.png, 猪肉皮.png): rows of small oval follicle dots, each on a soft bump, over a
    gently uneven skin. R = the dots, G = bumps with the pore sunk in their middle."""
    rng = np.random.default_rng(41)
    rows, cols = 13, 11                         # a staggered grid, ~43 px apart
    dots, bumps = [], []
    for j in range(rows):
        for i in range(cols):
            if rng.random() < 0.12:
                continue
            x = (i + 0.5 * (j % 2) + rng.uniform(-0.28, 0.28)) * N / cols
            y = (j + rng.uniform(-0.25, 0.25)) * N / rows
            r = rng.uniform(4.0, 6.5)
            ang = math.radians(rng.normal(-15, 18))
            ln = r * rng.uniform(1.2, 2.2)        # a little elongated, as the art paints them
            dx, dy = math.cos(ang) * ln * 0.5, math.sin(ang) * ln * 0.5
            v = rng.uniform(0.55, 1.0)
            dots.append([(x - dx, y - dy, r * 0.8, v), (x, y, r, v), (x + dx, y + dy, r * 0.8, v)])
            bumps.append([(x, y, r * 2.4, 1.0)])
    d = paint(dots, soften=0.9)
    b = paint(bumps, soften=6.0)
    uneven = noise(42, 3)
    pattern = np.clip(d * (0.7 + 0.3 * smooth(0.3, 0.7, noise(43, 2))), 0, 1)
    height = 0.5 + 0.45 * norm(b) - 0.15 * blur(d, 2.0) + 0.2 * (uneven - 0.5)
    return pattern, norm(height, 0.25, 1.0)


def mottle():
    """Kidney and liver (猪腰子.png): soft watercolour blotches, their edges a little darker where the pigment
    pooled, and a few pale streaks. R = the blotches, G = a gentle swell under them."""
    rng = np.random.default_rng(51)
    wx, wy = (noise(52, 3) - 0.5) * 45, (noise(53, 3) - 0.5) * 45
    field = sample(noise(54, 3.5, 1.8), XX + wx, YY + wy)
    blot = blur(smooth(0.45, 0.75, field), 5)                         # soft-edged pale clouds
    rim = np.exp(-((field - 0.5) / 0.025) ** 2) * smooth(0.3, 0.6, noise(55, 2))   # pooled edge, here and there
    gran = smooth(0.5, 0.75, sample(noise(56, 14, 5), XX + wx * 0.3, YY + wy * 0.3))   # fine granulation
    streaks = []
    for _ in range(16):
        ang = rng.uniform(0, math.pi)
        streaks.append(stroke(rng, rng.uniform(0, N), rng.uniform(0, N), ang, rng.uniform(40, 100),
                              rng.uniform(4, 8), rng.uniform(0.4, 0.8), bend=0.5))
    s = paint(streaks, soften=2.5)
    pattern = np.clip(0.7 * blot - 0.2 * rim + 0.1 * gran + 0.4 * s, 0, 1)
    height = 0.5 + 0.6 * (blur(field, 4) - 0.5) + 0.1 * blur(gran, 1.5) + 0.12 * blur(s, 2)
    return pattern, norm(height, 0.15, 0.85)


def cells(seed, n, warp=(0.0, 0.0)):
    """Tileable cellular pattern: n jittered points in the tile, and per pixel the gap between the distances to the
    nearest and the second nearest point (0 on the borders between cells, rising inside them), the pixel moved by
    `warp` first."""
    rng = np.random.default_rng(seed)
    k = int(round(math.sqrt(n)))
    pts = [((i + rng.uniform(0.1, 0.9)) * N / k, (j + rng.uniform(0.1, 0.9)) * N / k)
           for i in range(k) for j in range(k)]
    x, y = (XX + warp[0]) % N, (YY + warp[1]) % N
    d1 = np.full((N, N), 1e9)
    d2 = np.full((N, N), 1e9)
    for px, py in pts:
        dx = np.abs(x - px)
        dy = np.abs(y - py)
        d = np.hypot(np.minimum(dx, N - dx), np.minimum(dy, N - dy))
        d2 = np.minimum(d2, np.maximum(d1, d))
        d1 = np.minimum(d1, d)
    return (d2 - d1) / (N / k)


def curd():
    """Scrambled egg (番茄炒蛋.png): soft-set egg folded on itself, puffed folds like little cushions drawn out every
    which way, with creases between them, soft golden patches and a spongy grain. R = the creases and patches,
    G = the folds puffed up with the creases sunk between them."""
    wx, wy = (noise(62, 3) - 0.5) * 70, (noise(63, 3) - 0.5) * 70
    e = cells(64, 49, (wx, wy))
    crease = smooth(0.13, 0.0, e) * smooth(0.35, 0.6, noise(66, 2.5))   # broken here and there, not a net
    patches = blur(smooth(0.5, 0.8, noise(67, 2.5)), 4)                 # soft golden patches
    sponge = smooth(0.55, 0.8, noise(68, 28, 10))                        # fine spongy grain
    pattern = np.clip(0.9 * blur(crease, 0.8) + 0.3 * patches + 0.12 * sponge, 0, 1)
    puff = np.sqrt(np.clip(e / 0.35, 0, 1))                              # rounded up from the creases
    height = puff + 0.04 * (sponge - 0.5)
    return pattern, norm(blur(height, 1.2))


def seeds():
    """A tomato cut through (番茄炒蛋.png): its seeds in clusters, one to each chamber, every seed a small drop lying
    in a soft patch of paler jelly. R = the seeds and their jelly, G = the jelly a little raised, the seeds on it."""
    rng = np.random.default_rng(71)
    drops, jelly = [], []
    k = 3                                         # chambers on a jittered 3 × 3 grid, ~170 px apart
    for i in range(k):
        for j in range(k):
            cx, cy = (i + rng.uniform(0.25, 0.75)) * N / k, (j + rng.uniform(0.25, 0.75)) * N / k
            ang0 = rng.uniform(0, math.pi)
            jelly.append([(cx + rng.uniform(-12, 12), cy + rng.uniform(-12, 12), rng.uniform(42, 58), 1.0)
                          for _ in range(3)])
            for _ in range(int(rng.integers(6, 9))):
                r, a = rng.uniform(4, 46), rng.uniform(0, 2 * math.pi)
                x = cx + r * math.cos(a) * math.cos(ang0) * 1.2 - r * math.sin(a) * math.sin(ang0) * 0.7
                y = cy + r * math.cos(a) * math.sin(ang0) * 1.2 + r * math.sin(a) * math.cos(ang0) * 0.7
                ang = ang0 + rng.normal(0, 0.45)
                ln, w = rng.uniform(20, 26), rng.uniform(10, 13)
                dx, dy = math.cos(ang) * ln * 0.3, math.sin(ang) * ln * 0.3
                v = rng.uniform(0.75, 1.0)
                drops.append([(x - dx, y - dy, w * 0.4, v), (x, y, w * 0.5, v), (x + dx, y + dy, w * 0.38, v)])
    d = paint(drops, soften=1.2)
    g = paint(jelly, soften=10.0)
    pattern = np.clip(0.4 * g + 0.85 * d, 0, 1)
    height = 0.35 * g + 0.4 * blur(d, 1.5) + 0.06 * (noise(72, 6) - 0.5)
    return pattern, norm(height)


def scales():
    """Fish skin (普通整鱼.png, 大鱼头.png): rows of overlapping scales, each a soft crescent darker at its free edge
    where the next overlaps it, a little domed, over broad dappled patches where the pigment settled darker, and a
    few silvery glints. R = the crescents and dapples, G = each scale domed, stepping down at its edge."""
    rng = np.random.default_rng(81)
    rows, cols = 10, 10                     # a staggered grid, ~51 px a scale
    pitch = N / cols
    crescents, domes = [], []
    for j in range(rows):
        for i in range(cols):
            x = (i + 0.5 * (j % 2) + rng.uniform(-0.08, 0.08)) * pitch
            y = (j + rng.uniform(-0.08, 0.08)) * N / rows
            r = pitch * rng.uniform(0.58, 0.66)
            v = rng.uniform(0.55, 1.0)
            # the free edge: an arc round the scale's back (toward +x), thick in the middle, tapering
            arc = []
            for t in np.linspace(-1.15, 1.15, 13):
                w = r * 0.16 * (1 - (t / 1.2) ** 2) + 0.8
                arc.append((x + r * 0.92 * math.cos(t), y + r * 0.92 * math.sin(t), w, v))
            crescents.append(arc)
            domes.append([(x + r * 0.25, y, r * 0.85, 1.0)])
    c = paint(crescents, soften=1.2)
    d = blur(paint(domes, soften=0.5), 5.0)
    wx, wy = (noise(82, 3) - 0.5) * 40, (noise(83, 3) - 0.5) * 40
    dapple = smooth(0.52, 0.8, sample(noise(84, 4, 2), XX + wx, YY + wy))   # where the colour settled darker
    gran = smooth(0.55, 0.8, noise(85, 22, 8))                               # fine granulation
    pattern = np.clip(0.75 * c * (0.55 + 0.45 * smooth(0.3, 0.7, noise(86, 2))) + 0.45 * blur(dapple, 2.0)
                      + 0.1 * gran, 0, 1)
    height = 0.6 * d - 0.35 * blur(c, 1.5) + 0.05 * (gran - 0.5)
    return pattern, norm(blur(height, 1.0))


def shell():
    """A crab's shell (蟹.png): blue-grey washed over with soft olive-ochre blotches, pitted with fine speckles where
    the pigment granulated, and pale wear here and there. R = the blotches and speckles, G = gentle swells, the
    speckles pitted into them."""
    wx, wy = (noise(91, 3) - 0.5) * 50, (noise(92, 3) - 0.5) * 50
    field = sample(noise(93, 5.0, 2.5), XX + wx, YY + wy)
    blot = blur(smooth(0.45, 0.8, field), 7.0)                                # soft olive patches
    small = blur(smooth(0.55, 0.8, sample(noise(97, 11, 4), XX + wx * 0.5, YY + wy * 0.5)), 3.0)
    edge = np.exp(-((field - 0.47) / 0.035) ** 2) * smooth(0.35, 0.65, noise(94, 2))   # their edges pooled darker
    speck = smooth(0.62, 0.78, noise(95, 40, 14))                             # fine speckles
    speck2 = smooth(0.66, 0.8, sample(noise(96, 18, 6), XX + wx * 0.3, YY + wy * 0.3))
    pattern = np.clip(0.65 * blot + 0.3 * small + 0.15 * edge + 0.3 * speck + 0.2 * speck2, 0, 1)
    height = 0.5 + 0.35 * (blur(field, 6) - 0.5) - 0.12 * blur(speck, 0.8) - 0.06 * speck2
    return pattern, norm(height, 0.2, 0.85)


def chopped():
    """Chopped chilli (剁椒鱼头.png): a heap of small squarish bits, some red, some orange or yellow, each a little
    domed, dark in the cracks between them. R = the orange and yellow bits, G = each bit raised, the cracks sunk."""
    rng = np.random.default_rng(101)
    k = 16                                        # 16 × 16 bits a tile, jittered
    pts = [((i + rng.uniform(0.15, 0.85)) * N / k, (j + rng.uniform(0.15, 0.85)) * N / k)
           for i in range(k) for j in range(k)]
    val = rng.random(len(pts))
    wx, wy = (noise(102, 6) - 0.5) * 10, (noise(103, 6) - 0.5) * 10
    x, y = (XX + wx) % N, (YY + wy) % N
    d1 = np.full((N, N), 1e9)
    d2 = np.full((N, N), 1e9)
    near = np.zeros((N, N), int)
    for idx, (px, py) in enumerate(pts):
        dx, dy = np.abs(x - px), np.abs(y - py)
        dx, dy = np.minimum(dx, N - dx), np.minimum(dy, N - dy)
        d = np.maximum(dx, dy) * 0.7 + np.hypot(dx, dy) * 0.3      # squarish cells
        closer = d < d1
        d2 = np.where(closer, d1, np.minimum(d2, d))
        near = np.where(closer, idx, near)
        d1 = np.where(closer, d, d1)
    edge = (d2 - d1) / (N / k)
    bits = np.where(val[near] > 0.62, 1.0, np.where(val[near] > 0.5, 0.55, 0.0))   # orange, a few yellowish
    crack = smooth(0.08, 0.0, edge)
    pattern = np.clip(bits * (1 - crack), 0, 1)
    height = np.sqrt(np.clip(edge / 0.25, 0, 1)) * (0.85 + 0.15 * val[near])
    return pattern, norm(blur(height, 0.8))


def crisp():
    """Batter fried crisp (松鼠鳜鱼.png, 煎鱼饭.png): a crust of knobbly nodules and bubbles of every size, golden on
    their tops and browned in the hollows between them, with a few darker scorched flecks. R = the browned hollows and
    flecks, G = the nodules raised."""
    wx, wy = (noise(111, 4) - 0.5) * 40, (noise(112, 4) - 0.5) * 40
    big = cells(113, 100, (wx, wy))                                # nodules ~51 px across
    small = cells(114, 324, (wx * 0.6, wy * 0.6))                  # and bubbles on them
    nod = np.sqrt(np.clip(big / 0.35, 0, 1))
    bub = np.sqrt(np.clip(small / 0.3, 0, 1))
    height = 0.65 * nod + 0.3 * bub + 0.12 * (noise(115, 10) - 0.5)
    hollow = smooth(0.6, 0.25, blur(height, 1.0)) * (0.6 + 0.4 * noise(116, 2.5))   # broken, not a net
    fleck = smooth(0.74, 0.86, noise(117, 26, 9))
    pattern = np.clip(0.9 * hollow + 0.45 * fleck, 0, 1)
    return pattern, norm(blur(height, 0.8))


def veins():
    """A leaf (紫苏, 青菜, 酸菜): a net of fine pale veins round small puckered patches (areoles), every way alike, so
    it reads as leafy whichever way a leaf lies, with a few stronger veins through it. R = the veins, G = the blade
    puckered up between them."""
    wx, wy = (noise(123, 3) - 0.5) * 50, (noise(124, 3) - 0.5) * 50
    e = cells(125, 196, (wx, wy))                                  # patches ~37 px across
    fine = smooth(0.1, 0.0, e) * (0.5 + 0.5 * noise(126, 4))       # their veins, broken here and there
    big = cells(127, 16, (wx * 1.5, wy * 1.5))                     # and the stronger veins round bigger fields
    strong = smooth(0.06, 0.0, big)
    pattern = np.clip(0.6 * blur(fine, 0.7) + 0.9 * blur(strong, 1.0), 0, 1)
    height = 0.6 * np.sqrt(np.clip(e / 0.35, 0, 1)) - 0.4 * blur(strong, 1.5) + 0.1 * (noise(122, 9) - 0.5)
    return pattern, norm(blur(height, 1.0))


def grains():
    """Steamed rice (米.png, 煎鱼饭.png): a heap of plump oval grains every which way, packed close, each its own
    dome, so that where they touch a seam of shadow runs between them. R = the seams, G = the grains raised."""
    rng = np.random.default_rng(131)
    height = np.zeros((N, N))
    for _ in range(300):
        x, y = rng.uniform(0, N), rng.uniform(0, N)
        ang = rng.uniform(0, math.pi)
        a, b = rng.uniform(26, 32), rng.uniform(11, 13)          # half length, half width
        h = rng.uniform(0.8, 1.0)
        r = int(a) + 2
        for ox in (-N, 0, N):                                     # wrapped round the tile
            for oy in (-N, 0, N):
                cx, cy = x + ox, y + oy
                if cx + r < 0 or cx - r > N or cy + r < 0 or cy - r > N:
                    continue
                x0, x1, y0, y1 = max(int(cx - r), 0), min(int(cx + r) + 1, N), max(int(cy - r), 0), min(int(cy + r) + 1, N)
                yy, xx = np.mgrid[y0:y1, x0:x1]
                u = ((xx - cx) * math.cos(ang) + (yy - cy) * math.sin(ang)) / a
                v = (-(xx - cx) * math.sin(ang) + (yy - cy) * math.cos(ang)) / b
                dome = h * np.sqrt(np.clip(1 - u * u - v * v, 0, 1))
                height[y0:y1, x0:x1] = np.maximum(height[y0:y1, x0:x1], dome)
    height = blur(height, 0.8)
    seam = smooth(0.45, 0.05, height)
    return np.clip(seam * 0.9, 0, 1), norm(height)


def fishskin():
    """A cooked fish's skin (煎鱼饭.png, 两熟紫苏鱼.png): rows of small scales under a crust of fine knobbly grains,
    browned in the hollows between the grains and along the scales' free edges, in broad browner patches, with
    scorched flecks; the grains raised, so that the light catches their tops in bright specks as the art paints
    them. R = the browned hollows, edges, patches and flecks, G = the grains and the scales raised."""
    rng = np.random.default_rng(141)
    rows, cols = 12, 12                     # a staggered grid, ~43 px a scale
    pitch = N / cols
    crescents, domes = [], []
    for j in range(rows):
        for i in range(cols):
            x = (i + 0.5 * (j % 2) + rng.uniform(-0.1, 0.1)) * pitch
            y = (j + rng.uniform(-0.1, 0.1)) * N / rows
            r = pitch * rng.uniform(0.58, 0.66)
            v = rng.uniform(0.5, 1.0)
            crescents.append([(x + r * 0.92 * math.cos(t), y + r * 0.92 * math.sin(t),
                               r * 0.14 * (1 - (t / 1.2) ** 2) + 0.7, v) for t in np.linspace(-1.15, 1.15, 11)])
            domes.append([(x + r * 0.25, y, r * 0.85, 1.0)])
    c = paint(crescents, soften=1.0)
    d = blur(paint(domes, soften=0.5), 3.0)
    wx, wy = (noise(142, 4) - 0.5) * 30, (noise(143, 4) - 0.5) * 30
    grain = smooth(0.0, 0.32, cells(144, 400, (wx, wy)))                # grains ~26 px across, each a dome
    hollow = 1 - blur(grain, 1.0)                                        # browned round and between them
    patch = smooth(0.45, 0.75, noise(146, 3, 1.5))                      # broad browner patches
    fleck = smooth(0.72, 0.86, noise(145, 30, 10))                      # scorched flecks
    pattern = np.clip(0.35 * c + 0.5 * hollow * (0.4 + 0.6 * patch) + 0.35 * fleck, 0, 1)
    height = 0.35 * d - 0.15 * blur(c, 1.2) + 0.6 * grain
    return pattern, norm(blur(height, 0.7))


def bubbles():
    """Bubbles in cola (可乐.png): round bubbles of a few sizes scattered through it, each a bright ring round a
    clear middle with a glint at its upper left, as the art dots them. R = the rings and glints, G = each raised."""
    rng = np.random.default_rng(151)
    rings, glints = [], []
    for _ in range(70):
        x, y = rng.uniform(0, N), rng.uniform(0, N)
        r = rng.choice([8, 10, 12, 15, 18]) * rng.uniform(0.85, 1.15)
        v = rng.uniform(0.7, 1.0)
        rings.append([(x + r * math.cos(t), y + r * math.sin(t), max(1.0, r * 0.2), v)
                      for t in np.linspace(0, 2 * math.pi, 20)])
        glints.append([(x - r * 0.35, y - r * 0.35, r * 0.28, 1.0)])
    ring, glint = paint(rings, soften=0.7), paint(glints, soften=0.6)
    return np.clip(0.8 * ring + 0.9 * glint, 0, 1), norm(blur(ring + glint, 1.2))


def wingskin():
    """Raw chicken-wing skin (鸡翅.png): the art's short slanting streaks where the skin's fine wrinkles catch the
    light, soft and broken, over a few small follicle dots. R = the light streaks, G = the ridges under them."""
    rng = np.random.default_rng(57)
    streaks = []
    for _ in range(110):
        ang = math.radians(WINGSKIN_ANGLE + rng.normal(0, 7))
        streaks.append(stroke(rng, rng.uniform(0, N), rng.uniform(0, N), ang, rng.uniform(50, 130),
                              rng.uniform(4.0, 8.0), rng.uniform(0.45, 1.0), bend=0.3, taper=(0.35, 0.45)))
    st = paint(streaks, soften=1.6)
    dots = []
    for _ in range(60):
        x, y, r = rng.uniform(0, N), rng.uniform(0, N), rng.uniform(2.5, 3.5)
        dots.append([(x, y, r, rng.uniform(0.4, 0.8))])
    d = paint(dots, soften=0.9)
    vary = smooth(0.25, 0.75, noise(58, 2.5))
    pattern = np.clip(st * (0.55 + 0.45 * vary), 0, 1)
    height = 0.5 + 0.38 * blur(st, 2.0) - 0.12 * blur(d, 1.5) + 0.1 * (noise(59, 3) - 0.5)
    return pattern, norm(height, 0.2, 1.0)


WINGSKIN_ANGLE = 50.0   # the streaks' slant in the tile (degrees)


def crust():
    """The crust of a baked flatbread (胡饼.png): small toasted blotches strewn every which way over a gently mottled
    bake, each darker at its heart, and fine flecks between them. R = the blotches, the flecks and the mottling,
    G = the crust puffed a little between the blotches, which lie a touch lower."""
    rng = np.random.default_rng(141)
    blots, flecks = [], []
    for _ in range(70):
        x, y = rng.uniform(0, N), rng.uniform(0, N)
        r = rng.uniform(9.0, 20.0)
        v = rng.uniform(0.45, 0.9)
        dabs = []
        for _ in range(int(rng.integers(3, 6))):
            a, d = rng.uniform(0, 2 * math.pi), rng.uniform(0.2, 0.8) * r
            dabs.append((x + d * math.cos(a), y + d * math.sin(a) * 0.8, r * rng.uniform(0.45, 0.75), v))
        blots.append(dabs)
    for _ in range(220):
        x, y = rng.uniform(0, N), rng.uniform(0, N)
        flecks.append([(x, y, rng.uniform(2.0, 4.5), rng.uniform(0.3, 0.8))])
    bl = paint(blots, soften=3.5)
    core = smooth(0.55, 0.95, bl)                                   # darker at their hearts
    f = paint(flecks, soften=1.0)
    wx, wy = (noise(142, 3) - 0.5) * 40, (noise(143, 3) - 0.5) * 40
    mott = smooth(0.45, 0.8, sample(noise(144, 4, 2), XX + wx, YY + wy))
    gran = smooth(0.55, 0.8, noise(145, 30, 10))
    pattern = np.clip(0.6 * bl + 0.4 * core + 0.35 * f + 0.2 * blur(mott, 2.0) + 0.1 * gran, 0, 1)
    height = 0.5 - 0.3 * blur(bl, 2.0) + 0.25 * (blur(noise(146, 6), 1.0) - 0.5) - 0.1 * f
    return pattern, norm(blur(height, 0.8))


def crumb():
    """The torn crumb of bread (胡饼.png): an open sponge of round pores of every size, their walls pale and their
    hollows shadowed. R = the hollows, G = the walls standing between them, the pores sunk."""
    rng = np.random.default_rng(151)
    pores = []
    for _ in range(170):
        x, y = rng.uniform(0, N), rng.uniform(0, N)
        r = rng.uniform(4.0, 11.0) if rng.random() < 0.8 else rng.uniform(12.0, 20.0)
        ang = rng.uniform(0, math.pi)
        ln = r * rng.uniform(0.2, 0.9)
        dx, dy = math.cos(ang) * ln * 0.5, math.sin(ang) * ln * 0.5
        pores.append([(x - dx, y - dy, r * 0.85, 1.0), (x + dx, y + dy, r * 0.85, 1.0)])
    h = paint(pores, soften=1.2)
    shade = np.clip(h - 0.6 * np.roll(np.roll(h, 3, 0), 3, 1), 0, 1)   # each pore darker on the side away from the light
    gran = smooth(0.55, 0.8, noise(152, 26, 9))
    pattern = np.clip(0.55 * h + 0.45 * shade + 0.1 * gran, 0, 1)
    height = 1.0 - 0.8 * blur(h, 1.5) + 0.08 * (gran - 0.5)
    return pattern, norm(height)


def frost():
    """Julienned radish and cucumber, crisp and wet (瓜齑萝卜.png): small bright flecks of light scattered over the
    flesh, some alone, some in little clusters, each a short soft dab every way alike, so they glisten whichever way
    a strip lies. R = the flecks, G = each a tiny raised bead over a faintly uneven flesh."""
    rng = np.random.default_rng(141)
    dabs = []
    centres = [(rng.uniform(0, N), rng.uniform(0, N)) for _ in range(70)]
    for cx, cy in centres:   # clusters
        for _ in range(rng.integers(3, 8)):
            x, y = cx + rng.normal(0, 14), cy + rng.normal(0, 14)
            dabs.append(stroke(rng, x, y, rng.uniform(0, math.pi), rng.uniform(6, 16), rng.uniform(4.0, 7.5),
                               rng.uniform(0.6, 1.0), bend=0.4, taper=(0.4, 0.4)))
    for _ in range(140):     # and alone
        dabs.append(stroke(rng, rng.uniform(0, N), rng.uniform(0, N), rng.uniform(0, math.pi), rng.uniform(4, 12),
                           rng.uniform(3.0, 6.0), rng.uniform(0.45, 0.9), bend=0.4, taper=(0.4, 0.4)))
    flecks = np.clip(paint(dabs, soften=0.7), 0, 1)
    height = 0.5 + 0.35 * blur(flecks, 1.2) + 0.15 * (noise(142, 5) - 0.5)
    return flecks, norm(height, 0.3, 0.9)


def noodle_strands(n=24, seed=141):
    """Noodles lying side by side (面条, 冷淘): round strands running along the tile's x, each wavering gently and a
    little wider or narrower than the next, a thin shadow where two meet and here and there a gap where the sauce
    shows through. Box-projected on a heap of noodles, the strands run round it (along x on its top and front, along
    y on its sides), as noodles coiled in a bowl do. R = the shadow between strands, G = each strand's round top."""
    rng = np.random.default_rng(seed)
    pitch = N / n
    xs = XX[0]
    height = np.zeros((N, N))
    owner = np.full((N, N), -1, np.int32)
    for k in range(n):
        y0 = (k + 0.5) * pitch + rng.uniform(-0.12, 0.12) * pitch
        w = pitch * rng.uniform(0.42, 0.52)                      # half-width: they touch, some overlap a little
        yc = y0 + sum(rng.uniform(1.0, 2.6) * np.sin(2 * math.pi * m * xs / N + rng.uniform(0, 6))
                      for m in (1, 2, 3))                          # its line, wavering (whole waves: it tiles)
        d = (YY - yc[None, :] + N / 2) % N - N / 2                  # across it, wrapped round the tile
        dome = np.sqrt(np.clip(1 - (d / w) ** 2, 0, 1)) * rng.uniform(0.85, 1.0)
        top = dome > height
        height = np.where(top, dome, height)
        owner = np.where(top, k, owner)
    seam = np.zeros((N, N), bool)                                  # where one strand's edge meets the next
    seam[:, :] = (owner != np.roll(owner, 1, 0)) | (owner != np.roll(owner, -1, 0))
    gap = smooth(0.35, 0.0, height)                                 # and the low ground between them
    pattern = np.clip(0.75 * blur(seam.astype(float), 0.8) + 0.9 * gap, 0, 1)
    pattern *= 0.75 + 0.25 * noise(142, 3)                          # not all equally dark
    return pattern, norm(blur(height, 0.8))


# ---------------------------------------------------------------- what holds the ingredients: baskets, cloth, paper, clay

def weave():
    """A woven bamboo tray's floor (薄饼备料.png): broad flat strips crossing on the diagonal, over one and under
    one, each strip a little domed and streaked along its length, the gaps between them dark and each strip shaded
    where it dips under the next. R = the gaps and the dips, G = the strips raised, the dips sunk."""
    n, w = 8, 0.78                                      # strips a tile each way, the share of a pitch a strip fills
    u, v = (XX + YY) * n / N, (XX - YY) * n / N         # across the two sets of strips
    i, j = np.floor(u), np.floor(v)
    fu, fv = u - i, v - j
    in_a, in_b = fu < w, fv < w
    dome = lambda f: np.sqrt(np.sin(np.pi * np.clip(f / w, 0, 1)))
    over = lambda ph: np.clip(1.6 * np.cos(np.pi * (ph - 0.5)), -1, 1)   # up over one, down under the next
    ha = 0.55 + 0.3 * over(i + v) + 0.15 * dome(fu)
    hb = 0.55 - 0.3 * over(j + u) + 0.15 * dome(fv)
    height = np.maximum(np.where(in_a, ha, 0.0), np.where(in_b, hb, 0.0))
    streak_a = sample(grain_noise(141, math.radians(-45), 1.5, 22.0), XX, YY)   # fibres along each set
    streak_b = sample(grain_noise(142, math.radians(45), 1.5, 22.0), XX, YY)
    top_a = np.where(in_a, ha, 0.0) >= np.where(in_b, hb, 0.0)
    streak = np.where(top_a, streak_a, streak_b)
    gap = smooth(0.25, 0.05, height)
    dip = smooth(0.62, 0.3, height) * (1 - gap)
    pattern = np.clip(0.95 * gap + 0.45 * dip + 0.25 * smooth(0.5, 0.75, streak) * (1 - gap), 0, 1)
    return blur(pattern, 0.7), norm(blur(height + 0.04 * (streak - 0.5), 1.0))


def plait():
    """A bamboo tub's wall (米料备料.png): broad strips laid level round it, three to a tile, woven through upright
    staves, so that the wall is a grid of flat panels, each a little domed, a shade lighter or darker than the next,
    streaked along the strip, with dark seams between them. R = the seams and the darker panels, G = the panels
    raised, the seams sunk. (Box-projected: its rows run level on any upright face.)"""
    rng = np.random.default_rng(151)
    rows, cols = 3, 4
    ph, pw = N / rows, N / cols
    r = np.floor(YY / ph)
    stagger = (r % 2) * pw / 2                          # the staves in every other row half a panel along
    c = np.floor((XX + stagger) / pw) % cols
    fy, fx = (YY % ph) / ph, ((XX + stagger) % pw) / pw
    tone = rng.uniform(0, 1, (rows, cols))[r.astype(int), c.astype(int)]
    seam_y = smooth(0.06, 0.0, np.minimum(fy, 1 - fy))
    seam_x = smooth(0.035, 0.0, np.minimum(fx, 1 - fx))
    seam = np.maximum(seam_y, seam_x * 0.9)
    streak = sample(grain_noise(152, 0.0, 1.2, 26.0), XX, YY)       # fibres along the strips, level
    dome = np.sqrt(np.clip(np.sin(np.pi * fy), 0, 1)) * 0.6 + np.sqrt(np.clip(np.sin(np.pi * fx), 0, 1)) * 0.4
    pattern = np.clip(0.9 * seam + 0.35 * smooth(0.3, 0.9, tone) * (1 - seam) + 0.22 * smooth(0.5, 0.78, streak), 0, 1)
    height = dome * (1 - 0.8 * seam) + 0.05 * (streak - 0.5)
    return blur(pattern, 0.8), norm(blur(height, 1.0))


def wood():
    """Turned and carved wood, a bamboo rim (米料备料.png's spoon, 薄饼备料.png's tray): long soft grain lines, level
    across the tile, wavering, a few darker streaks among them. R = the grain, G = the grain a little sunk."""
    rng = np.random.default_rng(161)
    warp = noise(162, 2.5) - 0.5
    lines = striations((0, 14), warp, 9.0, 0.3)                      # ~14 grain lines a tile, level
    fine = striations((1, 37), warp, 12.0, 0.25) * 0.5
    streaks = []
    for _ in range(24):
        streaks.append(stroke(rng, rng.uniform(0, N), rng.uniform(0, N), rng.normal(0, 0.04), rng.uniform(150, 380),
                              rng.uniform(3.0, 7.0), rng.uniform(0.4, 0.9), bend=0.05, taper=(0.4, 0.4)))
    s = paint(streaks, soften=1.5)
    pattern = np.clip(0.45 * lines + 0.15 * fine + 0.55 * s, 0, 1)
    height = 0.5 - 0.25 * blur(lines, 1.2) - 0.1 * blur(s, 2) + 0.1 * (noise(163, 5) - 0.5)
    return pattern, norm(height, 0.2, 0.75)


def cloth():
    """Coarse cotton (米料备料.png's bundle): a plain weave of soft threads, the crossings each a small bump, with
    slubs and broad faint blotches where the dye took unevenly. R = the hollows between threads and the blotches,
    G = the threads raised."""
    n = 32                                             # threads a tile each way
    u, v = XX * n / N, YY * n / N
    i, j = np.floor(u), np.floor(v)
    over = ((i + j) % 2 == 0)
    tu = np.sin(np.pi * (u - i)) ** 2                  # each thread rounded across
    tv = np.sin(np.pi * (v - j)) ** 2
    height = np.where(over, 0.55 + 0.45 * tv, 0.55 + 0.45 * tu) * (0.75 + 0.25 * np.maximum(tu, tv))
    slub = smooth(0.6, 0.85, sample(grain_noise(171, 0.0, 2.0, 30.0), XX, YY))
    blot = blur(smooth(0.5, 0.8, noise(172, 3, 1.5)), 4)
    pattern = np.clip(0.45 * (1 - height) + 0.35 * blot + 0.2 * slub, 0, 1)
    return blur(pattern, 0.6), norm(blur(height + 0.15 * slub, 0.8))


def crumple():
    """Crumpled kraft paper (盐渍辅料包.png, 干贝海味包.png): flat facets of every size, each tilted its own way, meeting
    in creases, a few of them sharp and dark, the paper's fibres faintly mottled. R = the creases and a mottle,
    G = the facets, each a plane at its own tilt (so the light picks them out one by one)."""
    rng = np.random.default_rng(181)
    k = 6
    pts = np.array([((i + rng.uniform(0.1, 0.9)) * N / k, (j + rng.uniform(0.1, 0.9)) * N / k)
                    for i in range(k) for j in range(k)])
    tilt = rng.normal(0, 1, (len(pts), 2))
    wx, wy = (noise(182, 3) - 0.5) * 30, (noise(183, 3) - 0.5) * 30
    x, y = (XX + wx) % N, (YY + wy) % N
    d1 = np.full((N, N), 1e9)
    d2 = np.full((N, N), 1e9)
    near = np.zeros((N, N), int)
    for idx, (px, py) in enumerate(pts):
        dx, dy = x - px, y - py
        dx = (dx + N / 2) % N - N / 2
        dy = (dy + N / 2) % N - N / 2
        d = np.hypot(dx, dy)
        closer = d < d1
        d2 = np.where(closer, d1, np.minimum(d2, d))
        near = np.where(closer, idx, near)
        d1 = np.where(closer, d, d1)
    edge = (d2 - d1) / (N / k)
    px, py = pts[near, 0], pts[near, 1]
    dx, dy = (x - px + N / 2) % N - N / 2, (y - py + N / 2) % N - N / 2
    plane = (tilt[near, 0] * dx + tilt[near, 1] * dy) / (N / k)     # each facet a plane through its seed
    crease = smooth(0.06, 0.0, edge)
    sharp = crease * smooth(0.45, 0.7, noise(184, 2.5))
    fibre = smooth(0.5, 0.8, noise(185, 20, 8))
    pattern = np.clip(0.75 * sharp + 0.25 * crease + 0.25 * blur(smooth(0.45, 0.75, noise(186, 3)), 3) + 0.1 * fibre, 0, 1)
    height = 0.5 + 0.22 * plane * smooth(0.0, 0.12, edge) + 0.03 * (fibre - 0.5)
    return blur(pattern, 0.7), norm(blur(height, 1.2))


def clay():
    """Unglazed terracotta (酸菜.png): broad soft blotches where it fired darker, finer mottling within them, and
    grit: small dark and pale specks. R = the blotches, the mottle and the dark specks, G = gentle swells, the grit
    a little raised."""
    wx, wy = (noise(191, 2.5) - 0.5) * 60, (noise(192, 2.5) - 0.5) * 60
    field = sample(noise(193, 2.5, 1.2), XX + wx, YY + wy)
    blot = blur(smooth(0.5, 0.78, field), 6)
    mott = blur(smooth(0.5, 0.8, sample(noise(194, 9, 4), XX + wx * 0.5, YY + wy * 0.5)), 2)
    dark = smooth(0.7, 0.8, noise(195, 45, 15))
    pale = smooth(0.72, 0.82, noise(196, 40, 14))
    pattern = np.clip(0.6 * blot + 0.25 * mott + 0.45 * dark - 0.2 * pale, 0, 1)
    height = 0.5 + 0.3 * (blur(field, 5) - 0.5) + 0.12 * blur(dark + pale, 0.8)
    return pattern, norm(height, 0.25, 0.8)


def fibrous():
    """Dried scallop's sides (干贝海味包.png): close upright fibres, wavering, some paler, some darker, with soft
    breaks across them. R = the darker fibres, G = the fibres rounded (ridges), so that the sides read as torn
    muscle. (Box-projected: the fibres stand upright on any upright face.)"""
    warp = noise(201, 3) - 0.5
    lines = striations((26, 0), warp, 10.0, 0.45)                   # ~26 fibres a tile, upright
    lines2 = striations((53, 1), warp, 14.0, 0.4)
    breaks = smooth(0.55, 0.75, sample(grain_noise(202, math.radians(90), 1.0, 12.0), XX, YY))
    pattern = np.clip(0.55 * lines + 0.2 * lines2 + 0.3 * breaks, 0, 1)
    height = 0.5 + 0.3 * blur(lines, 1.0) + 0.1 * lines2 - 0.15 * blur(breaks, 2)
    return pattern, norm(height, 0.2, 1.0)


def layers():
    """The edge of a stack of thin pancakes (薄饼备料.png): level wavy lines, ten to a tile, each a thin dark line
    under a pale rim, wavering and now and then pinching out, as each sheet's edge lies on the next. R = the dark
    lines, G = each sheet's edge rounded, the line between two sunk. (Box-projected: level on any upright face.)"""
    warp = noise(211, 2.0) - 0.5
    warp2 = noise(212, 4.0) - 0.5
    ph = 10 * YY / N + warp * 1.1 + warp2 * 0.35          # ten sheets a tile, each line wavering
    f = ph - np.floor(ph)
    line = smooth(0.12, 0.0, np.minimum(f, 1 - f)) * smooth(0.25, 0.5, noise(213, 3))
    rim = smooth(0.35, 0.1, np.abs(f - 0.2)) * 0.5
    height = np.sin(np.pi * f) ** 0.5
    pattern = np.clip(0.95 * line - 0.25 * rim + 0.1 * smooth(0.5, 0.8, noise(214, 12, 4)), 0, 1)
    return blur(pattern, 0.6), norm(blur(height, 0.8))


def potato_skin():
    """A potato's skin (土豆.png): irregular brown blotches where the earth stained it, small dark specks scattered
    over it and a fine dry grain. R = the blotches and specks, G = the skin a little lumpy, the specks sunk."""
    rng = np.random.default_rng(141)
    wx, wy = (noise(142, 3) - 0.5) * 50, (noise(143, 3) - 0.5) * 50
    field = sample(noise(144, 6, 3), XX + wx, YY + wy)
    blot = smooth(0.58, 0.7, field) * (0.6 + 0.4 * smooth(0.4, 0.7, noise(145, 2)))   # patches with soft edges
    dots = []
    for _ in range(70):
        x, y, r = rng.uniform(0, N), rng.uniform(0, N), rng.uniform(2.5, 6.0)
        dots.append([(x, y, r, rng.uniform(0.6, 1.0)), (x + rng.uniform(-3, 3), y + rng.uniform(-2, 2), r * 0.7, 0.8)])
    d = paint(dots, soften=0.8)
    grain = smooth(0.55, 0.8, noise(146, 40, 12))
    pattern = np.clip(0.55 * blur(blot, 1.5) + 0.9 * d + 0.12 * grain, 0, 1)
    height = 0.5 + 0.25 * (noise(147, 4) - 0.5) - 0.3 * blur(d, 1.5) + 0.06 * grain
    return pattern, norm(blur(height, 0.8))


def leaf_veins():
    """A leaf's veins as the vegetables' art paints them (时蔬, 紫苏, 萝卜): small feathered vein patterns every which
    way, a thin midrib each with side veins running off it at a slant, and the fine net between, over soft watercolour
    blotches. Its midribs and main veins are painted on the leaves from the art; this is the finer veining between
    them, so that no part of a leaf is empty. R = the veins (paler), G = the blade puckered up between them."""
    rng = np.random.default_rng(151)
    strokes = []
    for _ in range(26):   # little feathered vein systems
        x, y = rng.uniform(0, N), rng.uniform(0, N)
        ang = rng.uniform(0, 2 * math.pi)
        ln = rng.uniform(70, 130)
        strokes.append(stroke(rng, x, y, ang, ln, rng.uniform(3.0, 4.2), rng.uniform(0.75, 1.0), bend=0.25))
        for k in range(1, 6):
            t = k / 6
            bx, by = x + math.cos(ang) * ln * t, y + math.sin(ang) * ln * t
            for side in (-1, 1):
                a2 = ang + side * rng.uniform(0.6, 0.95)
                strokes.append(stroke(rng, bx, by, a2, ln * rng.uniform(0.22, 0.36), rng.uniform(1.6, 2.4),
                                      rng.uniform(0.45, 0.8), bend=0.35, taper=(0.1, 0.6)))
    v = paint(strokes, soften=0.7)
    wx, wy = (noise(152, 3) - 0.5) * 40, (noise(153, 3) - 0.5) * 40
    net = smooth(0.08, 0.0, cells(154, 144, (wx, wy))) * (0.4 + 0.6 * noise(155, 4))
    blot = blur(smooth(0.5, 0.72, sample(noise(156, 5, 2.5), XX + wx, YY + wy)), 3)
    pattern = np.clip(0.85 * v + 0.35 * blur(net, 0.7) + 0.15 * blot, 0, 1)
    height = 0.5 + 0.35 * blur(blot, 2) - 0.25 * blur(v, 1.5) - 0.1 * blur(net, 1.0) + 0.1 * (noise(157, 9) - 0.5)
    return pattern, norm(height)


def ginger_skin():
    """Ginger's skin (姜.png): fine fibrous streaks and short scratches over a dry, faintly blotched skin, with a few
    darker flecks. R = the darker streaks and flecks, G = the skin's fine ridges."""
    rng = np.random.default_rng(161)
    strokes = []
    for _ in range(140):
        strokes.append(stroke(rng, rng.uniform(0, N), rng.uniform(0, N), rng.uniform(0, math.pi) * 2,
                              rng.uniform(18, 55), rng.uniform(2.0, 3.6), rng.uniform(0.35, 0.8), bend=0.5))
    st = paint(strokes, soften=0.8)
    flecks = []
    for _ in range(40):
        x, y = rng.uniform(0, N), rng.uniform(0, N)
        flecks.append([(x, y, rng.uniform(2.0, 4.0), rng.uniform(0.7, 1.0))])
    f = paint(flecks, soften=0.7)
    blot = blur(smooth(0.5, 0.75, noise(162, 4, 2)), 4)
    pattern = np.clip(0.6 * st + 0.9 * f + 0.25 * blot, 0, 1)
    height = 0.5 + 0.3 * blur(st, 1.2) + 0.2 * (noise(163, 6) - 0.5) - 0.2 * blur(f, 1.0)
    return pattern, norm(height)


def garlic_streaks():
    """A garlic bulb's papery skin (蒜.png): fine streaks running up it (the texture's v, the model's height in every
    view of the box projection), wavering, some darker and pinker, over a faint grain. R = the streaks, G = fine
    ridges along them."""
    rng = np.random.default_rng(171)
    strokes = []
    for _ in range(90):
        x, y = rng.uniform(0, N), rng.uniform(0, N)
        strokes.append(stroke(rng, x, y, math.pi / 2 + rng.normal(0, 0.06), rng.uniform(90, 260),
                              rng.uniform(1.8, 3.6), rng.uniform(0.3, 1.0), bend=0.12, taper=(0.3, 0.4)))
    st = paint(strokes, soften=0.8)
    lines = striations((23, 0), noise(172, 3) - 0.5, 9.0, 0.3)
    pattern = np.clip(0.85 * st + 0.12 * lines, 0, 1)
    height = 0.5 + 0.3 * blur(st, 1.2) + 0.12 * lines + 0.1 * (noise(173, 5) - 0.5)
    return pattern, norm(height)


TEXTURES = {'food_marble': marble, 'food_fiber': fiber, 'food_pores': pores, 'food_mottle': mottle, 'food_curd': curd,
            'food_seeds': seeds, 'food_scales': scales, 'food_shell': shell, 'food_chopped': chopped,
            'food_crisp': crisp, 'food_veins': veins, 'food_grains': grains, 'food_fishskin': fishskin,
            'food_bubbles': bubbles, 'food_wingskin': wingskin, 'food_crust': crust, 'food_crumb': crumb,
            'food_frost': frost, 'food_noodles': noodle_strands,
            'food_noodles_v': lambda: tuple(a.T.copy() for a in noodle_strands())}   # the same, along the tile's y
TEXTURES.update({'food_weave': weave, 'food_plait': plait, 'food_wood': wood, 'food_cloth': cloth,
                 'food_crumple': crumple, 'food_clay': clay, 'food_fibrous': fibrous, 'food_layers': layers})
TEXTURES.update({'food_potato': potato_skin, 'food_leafvein': leaf_veins, 'food_ginger': ginger_skin,
                 'food_garlic': garlic_streaks})


# ---------------------------------------------------------------- preview (roughly the shader's look)

def preview(pattern, height, lit, tint, amount, bump_mm, scale, px_per_m=1800):
    """Lit swatch of 2×2 tiles: colour tinted by the pattern, lambert from the height's normals, at icon size."""
    rgb = lambda h: np.array([int(h[i:i + 2], 16) / 255 for i in (1, 3, 5)])
    tile_px = px_per_m / scale
    k = bump_mm * 0.001 * scale * N   # height units → metres over a texel step, in texels per metre
    gy, gx = np.gradient(np.tile(height, (2, 2)) * k / N)
    n = np.dstack([-gx * N, -gy * N, np.ones_like(gx)])
    n /= np.linalg.norm(n, axis=2, keepdims=True)
    l = np.array([-0.4, -0.5, 0.75]); l /= np.linalg.norm(l)
    d = np.clip((n * l).sum(2), 0, 1)
    lum = 0.25 + 0.75 * d
    base = rgb(lit) * (1 - np.tile(pattern, (2, 2))[..., None] * amount) + rgb(tint) * np.tile(pattern, (2, 2))[..., None] * amount
    col = base * (0.55 + 0.45 * lum[..., None] / lum.mean())
    im = Image.fromarray((np.clip(col, 0, 1) * 255).astype(np.uint8))
    return im.resize((max(8, int(tile_px * 2)),) * 2, Image.LANCZOS)


if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    out = {}
    for name, make in TEXTURES.items():
        pattern, height = make()
        out[name] = (pattern, height)
        rgb = np.dstack([pattern, height, np.zeros_like(pattern)])
        Image.fromarray((np.clip(rgb, 0, 1) * 255 + 0.5).astype(np.uint8)).save(os.path.join(OUT, name + '.png'))
        print(f'{name}: pattern mean {pattern.mean():.2f}, height {height.min():.2f}–{height.max():.2f}')
    if '--preview' in sys.argv:
        pdir = sys.argv[sys.argv.index('--preview') + 1]
        os.makedirs(pdir, exist_ok=True)
        for name, (pattern, height) in out.items():
            Image.fromarray((np.dstack([pattern, height, pattern * 0]) * 255).astype(np.uint8)).save(
                os.path.join(pdir, name + '_rg.png'))
            for tag, (lit, tint, amount, bump, scale) in {
                'pork': ('#e28474', '#f9ddcb', 0.8, 0.4, 12), 'chicken': ('#f8c6aa', '#fde6d6', 0.5, 0.35, 10),
                'duck': ('#fce4c4', '#efb08e', 0.5, 0.3, 12), 'kidney': ('#bb4a4d', '#d47070', 0.4, 0.4, 9),
            }.items():
                preview(pattern, height, lit, tint, amount, bump, scale).save(os.path.join(pdir, f'{name}_{tag}.png'))
