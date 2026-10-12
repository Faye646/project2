"""Traces 馄饨's art (新建文件夹/馄饨.png) for D03, so that the wontons floating in its broth are modelled 1:1 (勾勒):
writes food_models/traced_D03.json and the colours of its pieces (traced_D03_paint.npz), which bowls.huntun builds
the food from, and a tracing sheet.

    python WhiteModel/trace_d03.py [--sheet <out.png>]

1. The art's camera: fitted together with the bowl huntun builds (a rounder foot and a flared wall, IoU 0.99 by
   the bowl's outline); the bowl and the broth in it built by Blender with huntun's own round_bowl. What floats is
   inside the lip: on the broth, and at the back on the bowl's inner wall where a wrapper's corner leans on it.
2. The six wontons, a flood of the art from strokes inside each (WONTONS, read off the art by eye) and from where
   the art is plainly broth (its olive gold), lowest change of colour first, the art's ink lines walls: each one's
   outline follows the brown line the art draws round it. The scallion rings and the yellow flecks in the broth are
   painted out first.
3. Their colours, as the art blocks them in: the pink filling through the wrapper (painted on, the mesh has vertices
   along its edge), the brown ink lines of the wrapper's folds (painted on), the folds' warm shadow and the
   wrapper's light (tinted in softly).
4. Each wonton a surface over its outline floating on the broth (lying on the bowl's wall at the back), so that from
   the art's camera it covers exactly what the art paints: a soft mound, the filling a dome in its middle, the art's
   shading as relief (the wrapper's folds and ridges).
5. The scallion rings, each where the art has one, its size and turn, lying flat on the broth; the yellow flecks
   (fried garlic), small flat bits.
"""
import json
import math
import os
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

from trace_common import (Camera, blobs, contour_points, dish_mesh, disk, fill_holes, flood, largest, neighbours,
                          outline_mesh, over, paint_channels, profile, raster, shading_band, smooth_inner,
                          tracing_sheet, u8)

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '馄饨.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D03.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D03_paint.npz')

# (1) the camera, and the bowl as huntun builds it (its broth at fill_z)
CAM = Camera(33.994, 6335.4, 764.64, 802.56)
FILL_Z = 0.063
BOWL = ("round_bowl(tmp, rim_r=0.0875, h=0.0792, foot_r=0.0435, foot_h=0.013, fill_z=0.063, fill='HuntunBroth', "
        "n=48, light=True, flare=(17.2, 81.7, 0.26), t=0.0076)")
LIP = (0.0875 - 0.0076, 0.0792)   # the lip's inside: radius and height

# (2) strokes inside each wonton (art pixels), read off the art by eye
WONTONS = {
    'W1': [[(660, 300), (770, 300), (880, 300)], [(775, 225), (775, 350)]],
    'W2': [[(390, 380), (470, 410), (580, 440)], [(470, 335), (470, 480)]],
    'W3': [[(960, 390), (1060, 425), (1160, 440)], [(1060, 355), (1060, 490)]],
    'W4': [[(700, 470), (810, 490), (900, 500)], [(800, 425), (800, 560)]],
    'W5': [[(420, 560), (520, 590), (640, 620)], [(510, 515), (510, 660)], [(400, 640), (520, 650), (640, 650)],
           [(345, 535), (420, 545)], [(560, 600), (680, 640)]],
    'W6': [[(870, 600), (960, 590), (1080, 590)], [(960, 535), (960, 670)], [(880, 670), (980, 680), (1100, 668)],
           [(1080, 610), (1170, 575)], [(820, 590), (870, 630), (900, 650)]],
}
BROTH = [[(722, 575), (745, 655)], [(1190, 560), (1215, 610)], [(303, 395), (316, 475)], [(330, 470), (345, 490)]]   # lines in the broth between them
CHANNELS = ['fill', 'ink', 'fold', 'light', 'shade', 'veil']

# (4) the wontons' surfaces: mesh spacing inside and along the outline (m), its rings of vertices along the outline
# (two: a clear ink line), how high it rises (puff × its half-width, up to top), where its outline sits (edge), the
# art's shading as relief, the filling's dome; what it is built in, painted and tinted with
KIND = dict(gap=0.0052, gb=0.0032, ring=(0.0006, 0.0012), puff=0.8, top=0.02, edge=0.0008, relief=0.007,
            dome=0.009, mat='HuntunSkin', paint=[('fill', 'HuntunFill'), ('ink', 'HuntunInk')],
            tint=[('fold', '#dcb06e', 0.75), ('light', '#ffffff', 0.8), ('shade', '#c48a70', 0.6),
                  ('veil', '#ebbca2', 0.8)])
INK = [3.5, 3.0]   # the art's ink line round a wonton: full to, gone by (art pixels)


def views(H, W):
    """The bowl and its broth as the art's camera sees them: the depths of the nearest surface, where the broth
    shows, and where food may float: inside the lip, on the broth or (at the back) against the inner wall."""
    full = dish_mesh('from food_models.bowls import round_bowl\ntmp = p\n' + BOWL)
    broth = dish_mesh('from food_models.bowls import round_bowl\ntmp = Part()\nfz, rf = ' + BOWL +
                      "\np.lathe([(rf, fz), (rf * 0.5, fz + 0.0004), (0.0, fz + 0.0005)], 'HuntunBroth', n=48, "
                      "close_ends=False)")
    zb, zid = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
    for k, (V, T) in enumerate((broth, full)):   # the broth first: where it shows, it is the broth
        u, v = CAM.project(V[:, 0], V[:, 1], V[:, 2])
        raster(np.stack([u, v], -1)[T], CAM.depth(V)[T], np.full(len(T), k), H, W, zb, zid)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    r, z = LIP
    cu, cv_ = CAM.project(0.0, 0.0, z)
    inside = ((xx - cu) / (CAM.k * r)) ** 2 + ((yy - cv_) / (CAM.k * r * CAM.se)) ** 2 < 1
    food = inside & ((zid == 0) | (yy < cv_))   # the front of the lip hides what is behind it
    return zb, zid == 0, food


def pieces_of(rgb, food, broth_zone):
    """Each wonton a flood of the art from its strokes, the broth one from where the art is plainly broth, lowest
    change of colour first, the art's ink lines walls; the scallion and the flecks painted out first."""
    H, W = food.shape
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    bits = scallion_and_flecks(h, s, v, food)
    gone = cv2.dilate(u8(bits[0] | bits[1]), disk(3)).astype(bool)
    img = cv2.inpaint(rgb, u8(gone), 6, cv2.INPAINT_TELEA)
    hsv2 = cv2.cvtColor(img, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    s2, v2 = hsv2[..., 1] / 255, hsv2[..., 2] / 255
    h2 = hsv2[..., 0] * 360 / 256
    lab = cv2.cvtColor(cv2.GaussianBlur(img, (0, 0), 1.6), cv2.COLOR_RGB2LAB).astype(np.float32)
    grad = sum(np.abs(cv2.Sobel(lab[..., c], cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(lab[..., c], cv2.CV_32F, 0, 1))
               for c in range(3))
    wall = (v2 < 0.56) & (s2 > 0.3)
    elev = grad + 2000.0 * cv2.GaussianBlur(wall.astype(np.float32), (0, 0), 1.5)
    # (a) what each pixel is: the broth (1) or a wonton (2), from where the art is plainly each
    brothy = food & (s2 > 0.46) & (v2 < 0.8) & (h2 > 30) & (h2 < 60)
    pale = food & (s2 < 0.2) & (v2 > 0.93)
    pinkish = food & (h2 < 32) & (s2 > 0.18) & (v2 > 0.6)

    def seeds(m, r, amin):
        e = cv2.erode(u8(m), disk(r))
        n, cc, st, _ = cv2.connectedComponentsWithStats(e)
        keep = np.zeros(n, bool)
        keep[1:] = st[1:, cv2.CC_STAT_AREA] >= amin
        return keep[cc]
    canvas = Image.new('I', (W, H), 0)
    d = ImageDraw.Draw(canvas)
    for k, lines in enumerate(WONTONS.values(), 1):
        for line in lines:
            d.line(line, fill=k, width=9)
    st_ = np.asarray(canvas, np.int32)
    canvas = Image.new('L', (W, H), 0)
    d = ImageDraw.Draw(canvas)
    for line in BROTH:
        d.line(line, fill=1, width=7)
    bl = np.asarray(canvas) > 0
    mk = np.zeros((H, W), np.int32)
    mk[seeds(brothy, 6, 150)] = 1
    mk[(seeds(pale, 3, 60) | seeds(pinkish, 3, 60)) & ~(mk == 1)] = 2
    mk[st_ > 0] = 2
    mk[bl] = 1
    mk[~food] = 1
    what = flood(mk, elev)
    what[~food] = 1
    # (b) the wontons' pixels shared among them: a flood from each one's strokes, the ink lines walls
    m = what == 2
    mk = np.where(m, 0, -1).astype(np.int32)
    mk[m & (st_ > 0)] = st_[m & (st_ > 0)]
    got = flood(mk, elev)
    pieces = np.where(m & (got > 0), got, 0)
    return pieces, bits, img


def scallion_and_flecks(h, s, v, food):
    """The scallion rings (green) and the yellow flecks in the broth."""
    green = food & (h > 54) & (h < 140) & (s > 0.5) & (v > 0.25) & (v < 0.85)
    green = fill_holes(cv2.morphologyEx(u8(green), cv2.MORPH_CLOSE, disk(2)))   # a ring and the broth in it
    green = cv2.morphologyEx(u8(green), cv2.MORPH_OPEN, disk(1)).astype(bool)
    fleck = food & (h > 38) & (h < 60) & (s > 0.36) & (v > 0.88)
    fleck = cv2.morphologyEx(u8(fleck), cv2.MORPH_OPEN, disk(1)).astype(bool)
    return green, fleck


def classes(rgb, pieces):
    """The colour classes of CHANNELS over the wontons."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    food = pieces > 0
    inner = cv2.erode(u8(food), disk(5)).astype(bool)
    # the filling: where the art is pinker than the wrapper (Lab a*), its highlights filled in, in each wonton the
    # largest such patch, rounded out to its hull (a mound of mince under the wrapper)
    a_ = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), 4), cv2.COLOR_RGB2LAB).astype(np.float32)[..., 1] - 128
    pinkish = fill_holes(cv2.morphologyEx(u8(food & (a_ > 5.5)), cv2.MORPH_CLOSE, disk(15)))
    pinkish = cv2.morphologyEx(u8(pinkish), cv2.MORPH_OPEN, disk(9)).astype(bool)
    fill = np.zeros_like(food)
    for pid in range(1, pieces.max() + 1):
        inn = cv2.erode(u8(pieces == pid), disk(10)).astype(bool)
        m = pinkish & inn
        if m.sum() < 2500:
            continue
        m = largest(m)
        hull = cv2.convexHull(np.stack(np.nonzero(m)[::-1], -1).astype(np.int32))
        hm = np.zeros(food.shape, np.uint8)
        cv2.fillPoly(hm, [hull], 1)
        fill |= hm.astype(bool) & inn
    loc = cv2.GaussianBlur(lum, (0, 0), 4)   # the brown lines along the wrapper's folds: darker than round them
    ink = cv2.morphologyEx(u8(inner & (loc - lum > 25)), cv2.MORPH_CLOSE, disk(2))
    n, cc, st, _ = cv2.connectedComponentsWithStats(ink)
    keep = np.zeros(n, bool)
    keep[1:] = st[1:, cv2.CC_STAT_AREA] >= 40
    ink = cv2.dilate(u8(keep[cc]), disk(1)).astype(bool) & inner
    mean = cv2.GaussianBlur(lum * food, (0, 0), 12) / np.maximum(cv2.GaussianBlur(food.astype(np.float32), (0, 0), 12),
                                                                  1e-3)
    lb = cv2.GaussianBlur(lum, (0, 0), 3.0)
    skin = food & ~fill
    # the wrapper's shadows, as dark as the art paints them (from its light cream down to the warm tan of a deep fold),
    # its light where it is lighter than round it, and the filling's darker side: soft, continuous
    fold = np.where(skin, np.clip((228.0 - lb) / 35.0, 0, 1), 0)
    light = np.clip((lb - mean - 6) / 12.0, 0, 1) * (s < 0.15) * food   # its light, and the filling's highlights
    shade = np.where(fill, np.clip((mean - lb) / 25.0, 0, 1), 0)
    core = cv2.erode(u8(fill), disk(7)).astype(bool)   # the mince plain to see; round it, seen through the wrapper
    veil = np.clip(cv2.GaussianBlur(cv2.dilate(u8(core), disk(4)).astype(np.float32), (0, 0), 6.0) * 1.3, 0, 1) *         (food & ~core)
    a = paint_channels([core], food, smooth=3.0, min_area=800, close=6)
    b = paint_channels([ink], food, smooth=0.7, min_area=40, close=0)
    c = np.stack([cv2.GaussianBlur(x.astype(np.float32), (0, 0), 2.0) for x in (fold, light, shade)] + [veil], -1)
    c = np.clip(c * 255 + 0.5, 0, 255).astype(np.uint8)
    return np.concatenate([a, b, c], -1)


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    H, W = alpha.shape
    zb, broth_zone, food = views(H, W)
    food &= alpha > 128
    pieces, (green, fleck), under = pieces_of(rgb, food, broth_zone)
    names = list(WONTONS)
    for pid in range(1, len(names) + 1):   # each one clean: its largest part, holes filled
        m = pieces == pid
        keep = fill_holes(largest(cv2.morphologyEx(u8(m), cv2.MORPH_OPEN, disk(3))))
        pieces[m & ~keep] = 0
        pieces[keep & (pieces == 0)] = pid
    paint = classes(under, pieces)
    lum = under.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    out, n_tris = [], 0
    zfood = zb.copy()
    for pid, name in enumerate(names, 1):
        m = pieces == pid
        mk = cv2.GaussianBlur(m.astype(np.float32), (0, 0), 1.5) > 0.5
        piece = surface(name, mk, paint, lum, zb)
        out.append(piece)
        P, T = np.array(piece['verts']), np.array(piece['tris'])
        pu, pv = CAM.project(P[:, 0], P[:, 1], P[:, 2])
        raster(np.stack([pu, pv], -1)[T], CAM.depth(P)[T], np.full(len(T), pid), H, W, zfood,
               np.full((H, W), -1, np.int32))
        n_tris += len(T)
        print(f'[trace] {name}: {len(T)} triangles', flush=True)
    # (5) the scallion rings and the flecks, lying on the broth
    rings, flecks = [], []
    for (cu, cv_, rw, rh, ang) in blobs(green & (pieces == 0), 120, 4000):
        r = float(np.clip(rw / 2 / CAM.k, 0.0025, 0.006))
        c = np.stack(CAM.backproject(np.array([cu]), np.array([cv_]), lambda x, y: np.full_like(x, FILL_Z)), -1)[0]
        rings.append({'c': np.round(c, 5).tolist(), 'r': round(r, 5), 'yaw': 0.0})
    for (cu, cv_, rw, rh, ang) in blobs(fleck & (pieces == 0), 60, 700):
        if rw < 2.0 * rh:   # a fleck is a sliver; round spots are the broth's light
            continue
        th = np.radians(ang)
        c = np.stack(CAM.backproject(np.array([cu]), np.array([cv_]), lambda x, y: np.full_like(x, FILL_Z)), -1)[0]
        ln = float(np.clip(np.hypot(rw * np.cos(th), rw * np.sin(th) / CAM.se) / CAM.k, 0.003, 0.009))
        wd = float(np.clip(rh / CAM.k / CAM.se * 0.8, 0.0012, 0.003))
        flecks.append({'c': np.round(c, 5).tolist(), 'yaw': round(float(np.arctan2(-np.sin(th) / CAM.se, np.cos(th))), 4),
                       'length': round(ln, 5), 'width': round(wd, 5)})
    print(f'[trace] {len(out)} wontons, {n_tris} triangles; {len(rings)} scallion rings, {len(flecks)} flecks',
          flush=True)
    np.savez_compressed(PAINT, paint=paint[::2, ::2])
    data = {'camera': {'el': CAM.el, 'k': CAM.k, 'u0': CAM.u0, 'v0': CAM.v0}, 'paint_scale': 0.5,
            'channels': CHANNELS, 'fill_z': FILL_Z, 'pieces': out, 'bits': [], 'rings': rings, 'flecks': flecks}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT} and {PAINT}', flush=True)
    if sheet:
        extra = ([(*b, (110, 190, 80)) for b in blobs(green & (pieces == 0), 120, 4000)]
                 + [(*b, (250, 210, 60)) for b in blobs(fleck & (pieces == 0), 60, 700) if b[2] >= 2.0 * b[3]])
        tints = [(250, 240, 215)] * len(names)
        vis = pieces.copy()
        tracing_sheet(sheet, rgba, vis, names, tints, extra, crop=(250, 150, 1350, 730),
                      title=('原图上的描线（蓝：每只馄饨，绿：葱圈，黄：蒜末）', f'描出的 {len(out)} 只馄饨'))
        print(f'[trace] sheet {sheet}', flush=True)


def surface(name, mk, paint, lum, zb):
    """One wonton as a surface floating on the broth over its outline (art pixels mk): a soft mound, the filling a
    dome in its middle, the art's shading as relief."""
    H, W = mk.shape
    kp = KIND
    edges = [(paint[..., CHANNELS.index(c)] > 127) & mk for c, _ in kp['paint']]
    extra = np.r_[contour_points(edges[:1], 12.0), contour_points(edges[1:], 5.0)]
    uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, kp['gap'], kp['gb'], kp['ring'], smooth_px=6.0, extra=extra,
                                            extra_margin=0.0013 * CAM.k)
    band = shading_band(lum, mk, 5.0, 28.0)   # the wrapper's broad folds, not every brush mark
    iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
    ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
    top = float(np.clip(kp['puff'] * R, 0.002, kp['top']))
    L = profile(d, R, top, kp['edge'], 0.0, lean, kp['relief'], band[iy, ix])
    fill = paint[..., CHANNELS.index('fill')].astype(np.float32) / 255
    fd = cv2.distanceTransform(u8(fill > 0.5), cv2.DIST_L2, 5) / CAM.k   # in from the filling's edge
    rf = max(float(fd[mk].max()), 1e-4)
    L = L + kp['dome'] * np.sqrt(np.clip(fd[iy, ix] / rf, 0, 1))
    L = smooth_inner(L, nb, neighbours(len(uv), tris))
    P, T = over(CAM, uv, tris, L, zb, lambda u, v: np.full_like(u, float(np.nanmin(zb[np.isfinite(zb)]))))
    return {'name': name, 'kind': 'wonton', 'mat': kp['mat'], 'rim': nb,
            'paint': [(CHANNELS.index(c), m) for c, m in kp['paint']],
            'tint': [(CHANNELS.index(c), col, w) for c, col, w in kp['tint']],
            'ink': INK, 'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]}


if __name__ == '__main__':
    main()
