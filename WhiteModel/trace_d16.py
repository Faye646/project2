"""Traces 文思豆腐's art (新建文件夹/文思豆腐.png) for D16, so that the tofu threads and what lies on them are modelled
1:1 (勾勒): writes food_models/traced_D16.json and the colours of its pieces (traced_D16_paint.npz), which
bowls.wensi_doufu builds the food from, and a tracing sheet.

    python WhiteModel/trace_d16.py [--sheet <out.png>]

1. The art's camera: fitted so that the bowl wensi_doufu builds covers the art's outline (IoU 0.99); the bowl and the
   clear broth in it built by Blender with wensi_doufu's own round_bowl. Nothing floats in a band along the lip.
2. The mass of tofu threads: where the art is pale thread (and what lies on it), its outline smoothed, a low mound
   floating on the broth, golden like the broth between the threads (WensiBase).
3. The threads on it: strands of white tofu following the art's own flow, line by line, evenly spaced (streamlines of
   the threads' direction in the art, from its shading's structure), each a narrow ribbon a little over the mass,
   lighter or more golden where the art is; the gaps between them show the gold beneath, so at icon size the mass
   reads as the art's hair-fine threads, swirling where the art's swirl.
4. On top, each where the art has it and as the art outlines it: the shreds of shiitake (dark brown, their pale
   flesh along an edge painted on) and of bamboo shoot (pale yellow), surfaces over the threads; the cut scallion
   over them, each a small rounded mound over its outline, its glints and darker side tinted in.
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image

from trace_common import (Camera, blobs, contour_points, dish_mesh, disk, fill_holes, largest, neighbours, on_top,
                          oriented, outline_mesh, over, paint_channels, profile, raster, shading_band, smooth_inner,
                          tracing_sheet, u8)

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '文思豆腐.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D16.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D16_paint.npz')

CAM = Camera(34.98, 6781.3, 624.3, 974.8)
FILL_Z = 0.071
BOWL = ("round_bowl(tmp, rim_r=0.085, h=0.082, foot_r=0.035, foot_h=0.014, fill_z=0.071, fill='WensiBroth', n=48, "
        "light=True, flare=(32, 78, 0.4), t=0.007)")
RIM = 10                 # the band of bare broth along the lip (art pixels)
# the shreds of bamboo shoot: their middles (art px) and widths, read off the art by eye
BAMBOO = [([(195, 543), (300, 518), (405, 495)], 18), ([(630, 575), (720, 562), (800, 550)], 18),
          ([(885, 510), (918, 600), (955, 690)], 20), ([(535, 825), (660, 790), (795, 748)], 20),
          ([(705, 398), (780, 380), (860, 362)], 18), ([(950, 576), (1000, 606), (1045, 636)], 16)]
CHANNELS = ['flesh', 'gold', 'shade', 'light']
# the threads: their spacing (m), width, the step along them and between their points (m), how far over the mass
SEP, WIDTH, STEP, SEG, LIFT = 0.0026, 0.0014, 0.0006, 0.011, 0.0009
BEND = 1.7   # how far (art px) a thread may stray from its simplified line: points only where it bends
KINDS = {
    'base': dict(gap=0.009, gb=0.005, ring=0.0006, puff=0.3, top=0.003, edge=0.0004, relief=0.0, mat='WensiBase',
                 paint=[], tint=[('gold', '#d9b25a', 0.6)], ink=[0.0, 0.0]),
    'shiitake': dict(gap=0.006, gb=0.0024, ring=0.0004, puff=0.45, top=0.0016, edge=0.0004, relief=0.0004,
                     mat='WensiShiitake', paint=[('flesh', 'WensiShiitakeFlesh')], tint=[('light', '#a0705a', 0.5)],
                     ink=[0.4, 2.0]),
    'scallion': dict(gap=0.0035, gb=0.0016, ring=0.0004, puff=0.6, top=0.0024, edge=0.0004, relief=0.0004,
                     mat='WensiScallion', paint=[], tint=[('shade', '#6e8010', 0.6), ('light', '#e4ea9a', 0.75)],
                     ink=[0.4, 1.6]),
    'bamboo': dict(gap=0.0045, gb=0.0022, ring=0.0004, puff=0.45, top=0.0015, edge=0.0004, relief=0.0003,
                   mat='WensiBamboo', paint=[], tint=[('shade', '#d8b04a', 0.6), ('light', '#fff3c0', 0.5)],
                   ink=[0.3, 1.5]),
}


def views(H, W):
    """The bowl and its broth as the art's camera sees them: the depths of the nearest surface and where the broth
    shows (inside the lip)."""
    full = dish_mesh('from food_models.bowls import round_bowl\ntmp = p\n' + BOWL)
    broth = dish_mesh('from food_models.bowls import round_bowl\ntmp = Part()\nfz, rf = ' + BOWL +
                      "\np.lathe([(rf, fz), (rf * 0.5, fz + 0.0004), (0.0, fz + 0.0005)], 'WensiBroth', n=48, "
                      "close_ends=False)")
    zb, zid = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
    for k, (V, T) in enumerate((broth, full)):
        u, v = CAM.project(V[:, 0], V[:, 1], V[:, 2])
        raster(np.stack([u, v], -1)[T], CAM.depth(V)[T], np.full(len(T), k), H, W, zb, zid)
    return zb, zid == 0


def masks(rgb, zone):
    """What the art paints in the broth: the scallion, the shiitake, the bamboo, and the mass of threads under them."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    inner = cv2.erode(u8(zone), disk(RIM)).astype(bool)
    green = inner & (h > 60) & (h < 150) & (s > 0.35) & (v > 0.3)
    green = cv2.morphologyEx(u8(fill_holes(cv2.morphologyEx(u8(green), cv2.MORPH_CLOSE, disk(2)))), cv2.MORPH_OPEN,
                             disk(2)).astype(bool)
    brown = inner & ((h < 40) | (h > 330)) & (s > 0.28) & (v < 0.78) & ~green
    brown = cv2.morphologyEx(u8(brown), cv2.MORPH_CLOSE, disk(3))
    brown = cv2.morphologyEx(brown, cv2.MORPH_OPEN, disk(2)).astype(bool)
    pale = inner & (s < 0.36) & (v > 0.78)
    # the bamboo: pale yellow bands hardly lighter than the gold between the threads, traced along their middles by
    # eye (BAMBOO), as wide as the art paints them
    from PIL import ImageDraw
    canvas = Image.new('L', (zone.shape[1], zone.shape[0]), 0)
    d = ImageDraw.Draw(canvas)
    for line, w in BAMBOO:
        d.line(line, fill=255, width=w, joint='curve')
        for x, y in (line[0], line[-1]):
            d.ellipse((x - w / 2, y - w / 2, x + w / 2, y + w / 2), fill=255)
    bamboo = (np.asarray(canvas) > 0) & inner & ~green
    mass = cv2.morphologyEx(u8(pale | bamboo | brown | green), cv2.MORPH_CLOSE, disk(14))
    mass = cv2.morphologyEx(u8(fill_holes(mass)), cv2.MORPH_OPEN, disk(10)).astype(bool) & inner
    mass = largest(mass)
    return green, brown & mass, bamboo & mass, mass


def flow(lum, mask, sig=9.0):
    """The threads' direction at each pixel (radians, in the art's u, v), from the structure of the art's shading:
    across its strongest change of light."""
    g = cv2.GaussianBlur(lum, (0, 0), 1.2)
    gx, gy = cv2.Sobel(g, cv2.CV_32F, 1, 0), cv2.Sobel(g, cv2.CV_32F, 0, 1)
    m = mask.astype(np.float32)
    J = [cv2.GaussianBlur(a * m, (0, 0), sig) / np.maximum(cv2.GaussianBlur(m, (0, 0), sig), 1e-3)
         for a in (gx * gx, gx * gy, gy * gy)]
    phi = 0.5 * np.arctan2(2 * J[1], J[0] - J[2])   # the gradient's direction
    return phi + np.pi / 2


def streamlines(theta, mask, sep_px, step_px, se):
    """Evenly spaced lines along the direction field theta over mask (Jobard and Lefer): each traced both ways from a
    seed until it leaves the mask or comes within half the spacing of a line already there, new seeds a spacing to
    either side of each line. Worked in (u, w = v / se), where distances are as on level ground. Lines in art px."""
    H, W = mask.shape
    cell = sep_px / 2
    grid = {}

    def near(p, dmin, own=None):
        cx, cy = int(p[0] // cell), int(p[1] // cell)
        for gx in range(cx - 2, cx + 3):
            for gy in range(cy - 2, cy + 3):
                for q, lid in grid.get((gx, gy), ()):
                    if lid != own and (q[0] - p[0]) ** 2 + (q[1] - p[1]) ** 2 < dmin * dmin:
                        return True
        return False

    def inside(p):
        u, v = p[0], p[1] * se
        return 0 <= u < W - 1 and 0 <= v < H - 1 and mask[int(v), int(u)]

    def direction(p, prev):
        u, v = p[0], p[1] * se
        t = theta[min(max(int(v), 0), H - 1), min(max(int(u), 0), W - 1)]
        d = np.array([math.cos(t), math.sin(t) / se])
        d /= np.linalg.norm(d)
        if prev is not None and d @ prev < 0:
            d = -d
        return d

    def trace(seed, lid):
        halves = []
        for sgn in (1, -1):
            p, prev, pts = np.array(seed, float), None, []
            for _ in range(4000):
                d = direction(p, prev)
                if prev is None:
                    d = d * sgn
                d2 = direction(p + d * step_px / 2, d)   # midpoint (RK2)
                q = p + d2 * step_px
                if not inside(q) or near(q, sep_px * 0.5, lid):
                    break
                pts.append(q)
                prev, p = d2, q
            halves.append(pts)
        return halves[1][::-1] + [np.array(seed, float)] + halves[0]

    lines = []
    ys, xs = np.nonzero(cv2.erode(u8(mask), disk(3)))
    order = np.argsort((xs - xs.mean()) ** 2 + (ys - ys.mean()) ** 2)
    first = (float(xs[order[0]]), float(ys[order[0]]) / se)
    queue = [first]
    tried = 0
    while queue or tried < len(order):
        if queue:
            seed = queue.pop(0)
        else:   # fill what the seeds left: the next free point of the mask
            k = order[tried]
            tried += 37
            seed = (float(xs[k]), float(ys[k]) / se)
        if not inside(seed) or near(seed, sep_px * 0.9):
            continue
        lid = len(lines)
        line = trace(seed, lid)
        if len(line) < 6:
            continue
        lines.append(line)
        for q in line:
            grid.setdefault((int(q[0] // cell), int(q[1] // cell)), []).append((q, lid))
        for i in range(0, len(line), 4):   # new seeds a spacing to either side
            j = min(i + 1, len(line) - 1)
            t = line[j] - line[max(j - 1, 0)]
            if np.linalg.norm(t) < 1e-9:
                continue
            n = np.array([-t[1], t[0]]) / np.linalg.norm(t)
            queue += [tuple(line[i] + n * sep_px), tuple(line[i] - n * sep_px)]
    return [np.array([(q[0], q[1] * se) for q in line]) for line in lines]


def classes(rgb, lum, kinds_px):
    """The colour channels: the shiitake's pale flesh, the gold between the threads (how much darker than the
    threads the art is there), the bamboo's deeper yellow, and the light."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    shii, bamb, mass, scal = kinds_px['shiitake'], kinds_px['bamboo'], kinds_px['mass'], kinds_px['scallion']
    flesh = shii & (v > 0.55) & (s < 0.45)
    lb = cv2.GaussianBlur(lum, (0, 0), 2.0)
    gold = np.where(mass, np.clip((246.0 - lb) / 40.0, 0, 1), 0)
    tops = bamb | shii | scal
    mean = cv2.GaussianBlur(lum * tops, (0, 0), 8) / np.maximum(cv2.GaussianBlur(tops.astype(np.float32), (0, 0), 8), 1e-3)
    shade = np.where(bamb | scal, np.clip((mean - lb) / 25.0, 0, 1), 0)   # darker than round it
    light = np.where(tops, np.clip((lb - mean - 6) / 15.0, 0, 1), 0)        # lighter: its glints
    a = paint_channels([flesh], shii, smooth=1.0, min_area=25, close=1)
    c = np.stack([cv2.GaussianBlur(x.astype(np.float32), (0, 0), 1.0) for x in (gold, shade, light)], -1)
    return np.concatenate([a, np.clip(c * 255 + 0.5, 0, 255).astype(np.uint8)], -1)


def piece(name, kind, mk, paint, lum, zbuf):
    """A piece as a surface over its outline (art pixels mk), floating on what is under it (zbuf)."""
    H, W = mk.shape
    kp = KINDS[kind]
    edges = [(paint[..., CHANNELS.index(c)] > 127) & mk for c, _ in kp['paint']]
    extra = contour_points(edges, 5.0) if edges else None
    uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, kp['gap'], kp['gb'], kp['ring'],
                                            smooth_px=4.0 if kind == 'base' else 1.5, extra=extra,
                                            extra_margin=kp['ring'] * CAM.k + 1.5)
    band = shading_band(lum, mk, 2.0, 8.0)
    iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
    ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
    top = float(np.clip(kp['puff'] * R, 0.0005, kp['top']))
    L = profile(d, R, top, kp['edge'], 0.0, lean, kp['relief'], band[iy, ix])
    L = smooth_inner(L, nb, neighbours(len(uv), tris))
    P, T = over(CAM, uv, tris, L, zbuf, lambda u, v: np.full_like(u, float(np.nanmin(zbuf[np.isfinite(zbuf)]))))
    return {'name': name, 'kind': kind, 'mat': kp['mat'], 'rim': nb,
            'paint': [(CHANNELS.index(c), m) for c, m in kp['paint']],
            'tint': [(CHANNELS.index(c), col, w) for c, col, w in kp['tint']],
            'ink': kp['ink'], 'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]}


def ribbons(lines, zbuf, mask):
    """The threads: each line a narrow ribbon WIDTH wide a little over what is there (zbuf), its points SEG apart,
    its ends tapered. One piece."""
    H, W = zbuf.shape
    V, T = [], []
    seg_px = SEG * CAM.k
    for line in lines:
        dl = np.r_[0, np.cumsum(np.hypot(np.diff(line[:, 0]), np.diff(line[:, 1]) / CAM.se))]
        if dl[-1] < 2.0 * WIDTH * CAM.k:
            continue
        lw = np.stack([line[:, 0], line[:, 1] / CAM.se], -1).astype(np.float32)
        keep = cv2.approxPolyDP(lw.reshape(-1, 1, 2), BEND, False)[:, 0, :]   # points where it bends
        pts = [keep[0]]
        for q in keep[1:]:   # and at least every SEG
            gap_ = np.linalg.norm(q - pts[-1])
            m = int(gap_ // seg_px)
            base_ = pts[-1]
            for k in range(1, m + 1):
                pts.append(base_ + (q - base_) * k / (m + 1))
            pts.append(q)
        pts = np.array(pts)
        u, v = pts[:, 0], pts[:, 1] * CAM.se
        n = len(u)
        iy = np.clip(np.round(v).astype(int), 0, H - 1)
        ix = np.clip(np.round(u).astype(int), 0, W - 1)
        s = zbuf[iy, ix]
        if not np.all(np.isfinite(s)):
            continue
        C = CAM.on_ray(u, v, s - LIFT)
        tan = np.gradient(C, axis=0)
        side = np.stack([-tan[:, 1], tan[:, 0], np.zeros(n)], -1)
        side /= np.maximum(np.linalg.norm(side, axis=1, keepdims=True), 1e-9)
        w = np.full(n, WIDTH / 2)
        w[0] = w[-1] = WIDTH * 0.2
        k0 = len(V)
        V += list(C + side * w[:, None]) + list(C - side * w[:, None])
        for i in range(n - 1):
            a, b, c, d = k0 + i, k0 + i + 1, k0 + n + i + 1, k0 + n + i
            T += [(a, b, c), (a, c, d)]
    V = np.array(V)
    T = oriented(V, T, CAM.toward, True)
    return V, T


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    H, W = alpha.shape
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    zb, zone = views(H, W)
    zone &= alpha > 128
    green, brown, bamboo, mass = masks(rgb, zone)
    # the pieces on top, each a patch of its colour
    pieces = np.zeros((H, W), np.int32)
    names, kinds = [], []
    for kind, m, amin in (('bamboo', bamboo, 300), ('shiitake', brown & ~bamboo, 150), ('scallion', green, 120)):
        n, cc, st, _ = cv2.connectedComponentsWithStats(u8(m))
        for i in range(1, n):
            if st[i, cv2.CC_STAT_AREA] >= amin:
                names.append(f'{kind}{len(names) + 1}')
                kinds.append(kind)
                pieces[(cc == i) & (pieces == 0)] = len(names)
    of = lambda kind: np.isin(pieces, [i + 1 for i, k in enumerate(kinds) if k == kind])   # noqa: E731
    paint = classes(rgb, lum, {'shiitake': of('shiitake'), 'bamboo': of('bamboo'), 'mass': mass,
                               'scallion': of('scallion')})
    out, n_tris = [], {}
    # (2) the mass, (3) the threads on it
    base = piece('mass', 'base', cv2.GaussianBlur(mass.astype(np.float32), (0, 0), 2.0) > 0.5, paint, lum, zb)
    out.append(base)
    zfood = zb.copy()

    def lay(pc, pid):
        P, T = np.array(pc['verts']), np.array(pc['tris'])
        pu, pv = CAM.project(P[:, 0], P[:, 1], P[:, 2])
        raster(np.stack([pu, pv], -1)[T], CAM.depth(P)[T], np.full(len(T), pid), H, W, zfood,
               np.full((H, W), -1, np.int32))
        n_tris[pc['kind']] = n_tris.get(pc['kind'], 0) + len(T)
    lay(base, 0)
    tops = cv2.dilate(u8(green | brown | bamboo), disk(6)).astype(bool)
    theta = flow(lum, mass & ~tops)   # the threads' own flow, not round the shreds on them
    lines = streamlines(theta, cv2.erode(u8(mass), disk(3)).astype(bool), SEP * CAM.k, STEP * CAM.k, CAM.se)
    V, T = ribbons(lines, zfood, mass)
    threads = {'name': 'threads', 'kind': 'threads', 'mat': 'WensiSilk', 'rim': 2, 'paint': [],
               'tint': [(CHANNELS.index('gold'), '#f0dca8', 0.3)], 'ink': [0.0, 0.0],
               'verts': np.round(V, 6).tolist(), 'tris': [list(map(int, t)) for t in T]}
    out.append(threads)
    n_tris['threads'] = len(T)
    zthreads = zfood.copy()   # what lies on the threads goes over them and the mass
    pu, pv = CAM.project(V[:, 0], V[:, 1], V[:, 2])
    raster(np.stack([pu, pv], -1)[np.array(T)], CAM.depth(V)[np.array(T)], np.zeros(len(T), np.int32), H, W, zthreads,
           np.full((H, W), -1, np.int32))
    zfood = zthreads
    # (4) the shiitake and the bamboo on them
    for pid, (name, kind) in enumerate(zip(names, kinds), 1):
        m = pieces == pid
        mk = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 1.0) > 0.5
        if mk.sum() < 120:
            continue
        pc = piece(name, kind, mk, paint, lum, zfood)
        out.append(pc)
        lay(pc, pid)
    print(f'[trace] D16: {len(lines)} threads, {len(out) - 2} pieces on them ({kinds.count("scallion")} scallion); '
          f'triangles '
          f'{n_tris}, all {sum(n_tris.values())}', flush=True)
    np.savez_compressed(PAINT, paint=paint[::2, ::2])
    data = {'camera': {'el': CAM.el, 'k': CAM.k, 'u0': CAM.u0, 'v0': CAM.v0}, 'paint_scale': 0.5,
            'channels': CHANNELS, 'fill_z': FILL_Z, 'pieces': out, 'bits': []}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT}', flush=True)
    if sheet:
        vis = pieces.copy()
        vis[(vis == 0) & mass] = len(names) + 1
        tints = {'shiitake': (110, 60, 30), 'bamboo': (240, 210, 110), 'scallion': (140, 190, 40)}
        page_tints = [tints[k] for k in kinds] + [(250, 244, 230)]
        tracing_sheet(sheet, rgba, vis, names + ['mass'], page_tints, crop=(100, 300, 1160, 900),
                      title=('原图上的描线（蓝：豆腐丝、香菇丝、笋丝，绿：葱段）', f'描出的 {len(lines)} 缕豆腐丝和 {len(names)} 条香菇丝、笋丝'))
        img = rgb.copy()
        for line in lines:
            cv2.polylines(img, [np.round(line).astype(np.int32)], False, (40, 40, 220), 1)
        Image.fromarray(img[300:900, 100:1160]).save(sheet.replace('.png', '_threads.png'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
