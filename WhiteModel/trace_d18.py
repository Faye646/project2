"""Traces 松鼠鳜鱼's art (新建文件夹/松鼠鳜鱼.png) for D18, so that its crisp pieces, head, fins and tail are modelled
1:1 (勾勒): writes food_models/traced_D18.json and its colours food_models/traced_D18_paint.npz, which
plates.songshu_guiyu builds the dish from, and a tracing sheet.

    python WhiteModel/trace_d18.py [--sheet <out.png>]

1. The art's camera: fitted so that the dish songshu_guiyu built before covered the art's silhouette best
   (IoU 0.986). The dish and its pool of sauce, and the body the crisp pieces stand on (the core: a long rounded
   body lying along the dish), are built by Blender with songshu_guiyu's own helpers.
2. The pieces: a flood of the art seeded by strokes (STROKES, read off the art by eye) and on the dish and sauce
   round them (DISH), its ink lines made walls: the head reared up with its gaping jaws, the three fins round its
   throat, the tail flicked up, and the body; the body's crisp pieces are found where the art's golden flesh is cut
   apart by its red sauce and dark lines (split), then grown over the whole body to the creases between them (grow),
   so that they pack it as the art paints them, a thin crease between each two.
3. Their colours: each crisp piece golden at its top and glazed red low down, as the art paints them all, with the
   art's own light, shade and glaze on top; the head's blocked in as a painter would (posterize: the pale of its jaws
   and throat, the red sauce running down it, its brown shade and dark lines, on its orange), the fins' and the
   tail's dark rays and red glaze likewise, the eye's dark pupil; songshu_guiyu paints each onto the pieces, whose
   meshes have vertices along every colour's edge.
4. Each piece a surface over its outline, so that from the art's camera it covers exactly what the art paints: the
   crisp pieces plump lenses standing out from the body under them, each turned part way with the body's surface
   (TURN: those over its back face up into the light, those low on its flank down), with only a cone behind; the
   head a thick rounded lens reared up over the dish, the art's shading in relief, its back a coarser lens; the fins
   and the tail thin ones, each where the art has it. Whatever would sink into the dish is moved up onto it along
   the line of sight, so that the art's view still sees it where it was.
"""
import json
import os
import sys

import cv2
import numpy as np
from PIL import Image

from trace_common import (Camera, Grid, above, contour_points, dish_mesh, disk, fill_holes, grow, largest, neighbours,
                          on_top, outline_mesh, over, paint_channels, posterize, profile, raster, seeded_pieces,
                          shading_band, smooth_inner, split, standing, tracing_sheet, u8)

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '松鼠鳜鱼.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D18.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D18_paint.npz')
CAM = Camera(34.95, 4385.6, 770.9, 665.8)          # (1)
FZ = 0.008                                          # the dish's floor
DISH = ("d = DISH18\n"
        "inside = oval_dish(p, d['A'], d['q'], d['yaw'], d['h'], d['foot'], floor=0.008, n=40, rings=2)\n"
        "dish_sauce(p, 'SweetSour', inside, d['A'], d['q'], d['yaw'], reach=0.86, n=40, seed=18, sy=0.7, "
        "wobble=0.05, lift=0.0012)")
CORE = ("zc = 0.026\n"
        "p.blob((0.029, 0.004, zc), 1.0, 'SauceShadow', squash=(0.079, 0.034, 0.032), segs=(12, 6), "
        "deform=lambda c: guiyu_core(c, 0.079, 0.008 + 0.002 - zc))")

# (2) the pieces, built in this order: name, kind, strokes inside it (art pixels)
PIECES = [
    ('body', 'body', [(600, 420), (700, 380), (800, 400), (900, 420), (1000, 440), (1100, 450), (1200, 470),
                      (620, 520), (700, 500), (800, 520), (900, 540), (1000, 560), (1100, 560), (1200, 560),
                      (600, 640), (700, 660), (800, 680), (900, 680), (1000, 660), (1100, 640), (1200, 620),
                      (560, 700), (650, 720), (750, 730), (850, 730)]),
    ('head', 'head', [(285, 175), (300, 240), (240, 300), (200, 280), (350, 320), (400, 400), (470, 420), (500, 350),
                      (430, 260), (300, 420), (330, 600), (505, 420), (535, 455), (520, 390)]),
    ('eye', 'eye', [(445, 290), (450, 295)]),
    ('fin_l', 'fin', [(200, 530), (230, 560), (260, 590)]),
    ('fin_r', 'fin', [(440, 520), (500, 530), (540, 560), (530, 600)]),
    ('fin_p', 'fin', [(420, 620), (432, 650), (445, 685), (460, 715), (468, 730)]),
    ('tail', 'tail', [(1170, 220), (1220, 260), (1280, 200), (1320, 170), (1360, 280), (1330, 360), (1290, 420)]),
]
DISH_STROKES = [[(80, 520), (70, 600), (100, 700), (200, 780)], [(300, 790), (500, 795), (700, 795), (900, 790),
                                                                 (1100, 785), (1300, 765), (1450, 700)],
                [(1500, 600), (1450, 500), (1400, 420)], [(600, 315), (800, 300), (1000, 320), (1100, 345)],
                [(560, 330), (580, 340)], [(130, 640), (160, 690)], [(1350, 620), (1400, 600)],
                [(330, 760), (380, 760)], [(1150, 330), (1100, 380)]]
EYE = (447, 292), 21, (446, 292), 15   # the eye's middle and radius, and its dark pupil's (art pixels)
CHANNELS = ['glaze', 'dark', 'pupil', 'ray', 'light', 'shade', 'brown', 'red', 'gold', 'pale']
# the head's colours in the art and the fins' and the tail's, blocked in as a painter would (posterize): the head's
# dark lines, its brown shade, the red glaze running down it, its orange, its gold and the pale of its jaws and
# throat; the fins' dark and brown rays, the red glaze on them, their orange and gold
HEAD_PALETTE = {'dark': (131, 56, 23), 'brown': (185, 77, 26), 'red': (227, 108, 31), 'orange': (239, 153, 66),
                'gold': (248, 189, 101), 'pale': (249, 215, 155)}
FIN_PALETTE = {'dark': (111, 59, 26), 'ray': (169, 89, 37), 'red': (226, 88, 15), 'mid': (206, 122, 53),
               'orange': (241, 152, 55), 'gold': (249, 192, 105)}
# (4) by kind: mesh spacing inside and along the outline (m), how far it stands out (puff × its half-width, up to
# top), its back (for standing ones), its relief, its colours (built in, painted from which channel)
KINDS = {
    'body': dict(gap=0.0075, gb=0.0045, puff=0.85, top=0.011, back=0.009, relief=0.0022, mat='CrispPiece',
                 paint=[], tint=[('light', '#ffd070', 0.6), ('shade', '#e8560c', 0.55), ('glaze', '#dc3c08', 0.85)]),
    'head': dict(gap=0.011, gb=0.005, puff=0.6, top=0.028, back=0.022, relief=0.007, mat='CrispHead',
                 paint=[('pale', 'HeadPale'), ('brown', 'HeadBrown'), ('red', 'HeadRed'), ('dark', 'GuiyuThroat')],
                 tint=[('gold', '#f8c068', 0.7)]),
    'eye': dict(gap=0.003, gb=0.002, puff=0.3, top=0.0008, relief=0.0, mat='EyeBrown', paint=[('pupil', 'FishEye')],
                tint=[]),
    'fin': dict(gap=0.008, gb=0.005, puff=0.4, top=0.0025, back=0.0025, relief=0.0, mat='FriedFin',
                paint=[('ray', 'GuiyuRay')], tint=[('glaze', '#e2580f', 0.6)]),
    'tail': dict(gap=0.013, gb=0.006, puff=0.4, top=0.004, back=0.004, relief=0.0, mat='GuiyuTail',
                 paint=[('ray', 'GuiyuRay')], tint=[('glaze', '#e2580f', 0.75)]),
}
TURN = 0.6         # how far each crisp piece turns with the body's surface under it (0: square to the eye)
INK = [0.3, 1.5]   # the art's ink line round a piece: full to, gone by (art pixels), inside its ring of vertices
# where each standing piece stands: the art pixel and height its plane passes through, and how far towards the eye
# it is moved from there (m), as the dish was built before
ANCHORS = {'head': ((360, 692), 0.014, 0.0), 'fin_l': ((360, 692), 0.014, -0.01), 'fin_p': ((360, 692), 0.014, 0.036),
           'fin_r': ((360, 692), 0.014, 0.046), 'tail': ((1300, 440), 0.038, 0.0)}


def classes(rgb, pieces):
    """The colour classes of CHANNELS over the art."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    H, W = h.shape
    yy, xx = np.mgrid[0:H, 0:W]
    names = [n for n, _, _ in PIECES]
    food = pieces > 0
    eye = pieces == names.index('eye') + 1
    body = pieces == names.index('body') + 1
    fins = pieces > names.index('eye') + 1
    head = pieces == names.index('head') + 1
    inner = cv2.erode(u8(food), disk(5)).astype(bool)                # not the sauce round their edges
    hp = posterize(rgb, head, list(HEAD_PALETTE.values()), passes=(4, 4, 3), speck=400)
    dark, brown, red, gold, pale = (hp == list(HEAD_PALETTE).index(k) for k in ('dark', 'brown', 'red', 'gold', 'pale'))
    fp = posterize(rgb, fins, list(FIN_PALETTE.values()), passes=(2, 2), speck=150)
    ray = (fp == list(FIN_PALETTE).index('dark')) | (fp == list(FIN_PALETTE).index('ray'))   # the fins' rays
    glaze = inner & (fp == list(FIN_PALETTE).index('red'))           # the red sweet-sour sauce on the fins and tail
    glaze |= body & (h < 22) & (s > 0.75) & (v > 0.75)               # and the brightest of it on the pieces
    (ex, ey), er, (px, py), pr = EYE
    pupil = eye & ((xx - px) ** 2 + (yy - py) ** 2 < pr ** 2)
    # the art's light and shade on the pieces: brighter or darker than round about
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    m = body.astype(np.float32)
    local = cv2.GaussianBlur(lum * m, (0, 0), 10) / np.maximum(cv2.GaussianBlur(m, (0, 0), 10), 1e-3)
    light = body & (lum > local + 14)
    shade = body & (lum < local - 14) & ~glaze
    blocks = paint_channels([glaze, dark], food, smooth=2.0, min_area=150, close=2)
    eyes = paint_channels([pupil], food, smooth=0.8, min_area=10, close=0)
    rays = paint_channels([ray], food, smooth=1.5, min_area=60, close=1)
    tones = paint_channels([light, shade], food, smooth=4.0, min_area=80, close=2)
    heads = paint_channels([brown, red, gold, pale], food, smooth=2.5, min_area=100, close=1)
    return np.concatenate([blocks, eyes, rays, tones, heads], -1)


def crisp_pieces(rgb, body, lum):
    """The body's crisp pieces: its golden flesh, without the red sauce and dark lines running between the pieces,
    cut apart along those (split), each piece one region, then grown over the whole body to the creases between
    them (grow), so that they pack it as the art paints them."""
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    flesh = body & ~((h < 20) & (s > 0.8) & (v < 0.9)) & (v > 0.5)
    flesh = cv2.morphologyEx(u8(flesh), cv2.MORPH_OPEN, disk(3)).astype(bool)
    return grow(split(flesh, lum, sig=4.0, tau=26.0, amin=1800, amax=6500, marker_r=12), body, lum)


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = np.asarray(Image.open(ART).convert('RGBA'))
    rgb, alpha = np.ascontiguousarray(rgba[..., :3]), rgba[..., 3]
    H, W = alpha.shape
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    zone = alpha > 128
    strokes = {i + 1: st for i, (_, _, st) in enumerate(PIECES)}
    pieces = seeded_pieces(rgb, zone, strokes, DISH_STROKES)
    names = [n for n, _, _ in PIECES]
    head_id, eye_id = names.index('head') + 1, names.index('eye') + 1
    yy, xx = np.mgrid[0:H, 0:W]
    pieces[pieces == eye_id] = head_id   # the eye: a disc where the art draws it
    (ex, ey), er = EYE[:2]
    pieces[((xx - ex) ** 2 + (yy - ey) ** 2 < er ** 2) & (pieces == head_id)] = eye_id
    paint = classes(rgb, pieces)
    floor = Grid.top_of(*dish_mesh(DISH))
    core_V, core_T = dish_mesh(CORE)
    zb, zid = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
    cu, cv_ = CAM.project(core_V[:, 0], core_V[:, 1], core_V[:, 2])
    raster(np.stack([cu, cv_], -1)[core_T], CAM.depth(core_V)[core_T], np.full(len(core_T), 0), H, W, zb, zid)
    zbody = zb.copy()                     # the body alone, for setting the crisp pieces on it
    on_dish = lambda u, v: CAM.depth(np.stack(CAM.backproject(u, v, floor), -1))
    # the crisp pieces of the body
    body = pieces == names.index('body') + 1
    kernels = crisp_pieces(rgb, body, lum)
    print(f'[trace] {kernels.max()} crisp pieces', flush=True)
    # each piece golden at its top and glazed red low down, as the art paints them all, with the art's own on top
    light_c, glaze_c = CHANNELS.index('light'), CHANNELS.index('glaze')
    for k in range(1, kernels.max() + 1):
        ys = np.nonzero(kernels == k)[0]
        if len(ys):
            t = np.clip((yy - ys.min()) / max(ys.max() - ys.min(), 1), 0, 1)
            m = kernels == k
            ramp = lambda e0, e1: np.clip((t[m] - e0) / (e1 - e0), 0, 1) * 255
            paint[..., light_c][m] = np.maximum(paint[..., light_c][m], ramp(0.55, 0.1)).astype(np.uint8)
            paint[..., glaze_c][m] = np.maximum(paint[..., glaze_c][m], ramp(0.45, 0.9)).astype(np.uint8)
    out = []
    band = shading_band(lum, kernels > 0, 3.0, 12.0)
    kp = KINDS['body']

    def facing(u, v, r=8):   # the body's surface where the art shows (u, v): its normal, towards the camera
        u, v = int(round(u)), int(round(v))
        s = [zbody[min(max(v + dv, 0), H - 1), min(max(u + du, 0), W - 1)]
             for du, dv in ((-r, 0), (r, 0), (0, -r), (0, r))]
        if not np.all(np.isfinite(s)):
            return CAM.toward
        P = [CAM.on_ray(u + du, v + dv, z) for (du, dv), z in zip(((-r, 0), (r, 0), (0, -r), (0, r)), s)]
        n = np.cross(P[1] - P[0], P[3] - P[2])
        n = n / max(np.linalg.norm(n), 1e-9)
        return n if n @ CAM.toward > 0 else -n
    for k in range(1, kernels.max() + 1):
        mk = largest(kernels == k)
        if mk.sum() < 600:
            continue
        mk = cv2.GaussianBlur(cv2.erode(u8(mk), disk(1)).astype(np.float32), (0, 0), 1.5) > 0.5   # a thin crease
        uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, kp['gap'], kp['gb'], 0.0005, smooth_px=2.5)
        iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
        ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
        top = float(np.clip(kp['puff'] * R, 0.002, kp['top']))
        L = profile(d, R, top, 0.0, 0.0, None, kp['relief'], band[iy, ix])
        L = smooth_inner(L, nb, neighbours(len(uv), tris))
        Lb = profile(d, R, float(np.clip(kp['puff'] * R, 0.002, kp['back'])))
        # a plump lump standing out from the body: a rounded lens square to the eye, its middle on the body's surface
        # (where the body is behind it; else on the dish under its lowest point)
        under = zbody[mk]
        if np.isfinite(under).any():
            s0 = float(np.median(under[np.isfinite(under)]))
        else:
            ys, xs = np.nonzero(mk)
            j = np.argmax(ys)
            s0 = float(on_dish(np.array([float(xs[j])]), np.array([float(ys[j])]))[0]) - 0.004
        anchor = CAM.on_ray(float(uv[:, 0].mean()), float(uv[:, 1].mean()), s0)
        # turned part way with the body's surface under it, so that the pieces over its back face up into the light
        # and those low on its flank down, as round as the body
        n = CAM.toward + TURN * (facing(uv[:, 0].mean(), uv[:, 1].mean()) - CAM.toward)
        P, T = standing(CAM, uv, tris, nb, L, Lb, anchor, normal=n / np.linalg.norm(n), cone=True)
        P = above(CAM, P, floor, front=len(uv))
        front = [t for t in T if max(t) < len(uv)]
        pu, pv = CAM.project(P[:, 0], P[:, 1], P[:, 2])
        raster(np.stack([pu, pv], -1)[np.array(front)], CAM.depth(P)[np.array(front)], np.full(len(front), 100 + k),
               H, W, zb, zid)
        out.append({'name': f'piece{k}', 'kind': 'body', 'mat': kp['mat'], 'rim': nb, 'ink': INK,
                    'paint': [(CHANNELS.index(c), m) for c, m in kp['paint']],
                    'tint': [(CHANNELS.index(c), col, w) for c, col, w in kp['tint']],
                    'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]})
    print(f'[trace] body: {sum(len(o["tris"]) for o in out)} triangles in {len(out)} pieces', flush=True)
    # the head, its eye, the fins and the tail
    union = pieces > 0
    for pid, (name, kind, _) in enumerate(PIECES, 1):
        if kind == 'body':
            continue
        kp = KINDS[kind]
        mk = largest(cv2.morphologyEx(u8(pieces == pid), cv2.MORPH_OPEN, disk(2)))
        mk = fill_holes(cv2.dilate(u8(mk), disk(2)).astype(bool) & union)
        mk = cv2.GaussianBlur(mk.astype(np.float32), (0, 0), 2.0) > 0.5
        shown = [c for c, _ in kp['paint']]
        edges = [(paint[..., CHANNELS.index(c)] > 127) & mk for c in shown]   # where its colours change
        extra = None if kind == 'eye' else contour_points(edges, 16.0 if kind != 'head' else 20.0)
        uv, tris, nb, d, R, lean = outline_mesh(CAM, mk, kp['gap'], kp['gb'], 0.0005 if kind != 'eye' else 0.0002,
                                                smooth_px=2.5 if kind in ('fin', 'tail') else 1.5 if kind == 'eye'
                                                else 4.0, extra=extra)
        band_p = shading_band(lum, mk, 4.0, 16.0) if kind != 'head' else shading_band(lum, mk, 5.0, 28.0)
        iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
        ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
        top = float(np.clip(kp['puff'] * R, 0.001, kp['top']))
        L = profile(d, R, top, 0.0, 0.0, None, kp['relief'], band_p[iy, ix])
        L = smooth_inner(L, nb, neighbours(len(uv), tris))
        if kind == 'eye':
            P, T = over(CAM, uv, tris, L, zb, on_dish)
        else:
            (au, av), az, toward = ANCHORS[name]
            ax_, ay_, az_ = CAM.backproject(np.array([float(au)]), np.array([float(av)]),
                                           lambda x, y: np.full_like(x, az))
            anchor = np.array([ax_[0], ay_[0], az_[0]]) + CAM.toward * toward
            Lb = profile(d, R, float(np.clip(kp['puff'] * R, 0.001, kp['back'])))
            back = None
            if kind == 'head':   # its back, never seen: a coarser mesh over the same outline
                ub, tb, nbb, db, Rb, _ = outline_mesh(CAM, mk, 0.03, kp['gb'], 0.0, smooth_px=4.0)
                assert nbb == nb and np.allclose(ub[:nb], uv[:nb])
                Lb, back = profile(db, Rb, float(np.clip(kp['puff'] * Rb, 0.001, kp['back']))), (ub, tb)
            P, T = standing(CAM, uv, tris, nb, L, Lb, anchor, back=back)
            P = above(CAM, P, floor, front=len(uv))
        front = [t for t in T if max(t) < len(uv)]
        pu, pv = CAM.project(P[:, 0], P[:, 1], P[:, 2])
        raster(np.stack([pu, pv], -1)[np.array(front)], CAM.depth(P)[np.array(front)], np.full(len(front), pid),
               H, W, zb, zid)
        out.append({'name': name, 'kind': kind, 'mat': kp['mat'], 'rim': nb,
                    'ink': [0.0, 0.0] if kind in ('fin', 'tail', 'eye') else INK,
                    'paint': [(CHANNELS.index(c), m) for c, m in kp['paint']],
                    'tint': [(CHANNELS.index(c), col, w) for c, col, w in kp['tint']],
                    'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]})
        print(f'[trace] {name}: {len(T)} triangles, R {R * 100:.1f} cm, top {top * 1000:.1f} mm', flush=True)
    np.savez_compressed(PAINT, paint=paint[::2, ::2])
    data = {'camera': {'el': CAM.el, 'k': CAM.k, 'u0': CAM.u0, 'v0': CAM.v0}, 'paint_scale': 0.5,
            'channels': CHANNELS, 'pieces': out, 'bits': []}
    json.dump(data, open(OUT, 'w'), separators=(',', ':'))
    print(f'[trace] wrote {OUT} and {PAINT}', flush=True)
    if sheet:
        tints = {'body': (245, 170, 90), 'head': (240, 190, 120), 'eye': (120, 70, 40), 'fin': (245, 200, 130),
                 'tail': (245, 200, 130)}
        shown = pieces.copy()
        shown[body] = 0
        k0 = shown.max()
        shown = np.where(kernels > 0, kernels + k0, shown)
        tlist = [tints[k] for _, k, _ in PIECES] + [tints['body']] * kernels.max()
        tracing_sheet(sheet, rgba, shown, None, tlist, crop=(40, 100, 1500, 880),
                      title=('原图上的描线（蓝：每一块）', f'描出的 {kernels.max()} 块脆鱼肉，和鱼头、鱼眼、三片鱼鳍、鱼尾'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
