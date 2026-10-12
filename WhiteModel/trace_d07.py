"""Traces 宫保鸡丁（简化版）'s art (新建文件夹/宫保鸡丁（简化版）.png) for D07, so that every piece of its heap is modelled
1:1 (勾勒): writes food_models/traced_D07.json and the colours of its pieces food_models/traced_D07_paint.npz, which
stirfry.gongbao_jiding builds the dish from, and a tracing sheet.

    python WhiteModel/trace_d07.py [--sheet <out.png>] [--labels <out.png>]

1. The art's camera: fitted so that the dish gongbao_jiding builds (round_dish, kept) covers the art's dish best
   (IoU 0.986).
2. The pieces, found automatically (trace_heap): seeds where the art is plainly one thing (golden chicken, red
   chilli, green scallion, pale scallion, dark sauce), each patch of its colour one seed, flooded out over the art
   to the ink lines and creases between the pieces; FIX adds or changes seeds where the art's colours don't part
   them. Each piece one clean region.
3. Their colours: the chicken's light and shade tinted in softly from the art, the red sauce on it painted on; the
   chilli's darker side tinted, its cut end's seeds and dark inside painted; the scallion's paler ends.
4. The heap under them: the sauce, raised over the whole food from the dish floor, highest in the middle; each piece
   a rounded mound over its outline lying on it, the art's shading as relief, so that from the art's camera it
   covers exactly what the art paints.
"""
import os
import sys

import cv2
import numpy as np

from trace_common import Camera, disk, fill_holes, largest, tracing_sheet, u8
from trace_heap import (heap_rgb, rim_guard, channels_from, tone_channels, kind_colours, sauce_points, art_rgb, tone_map, dish_view, gradient, heap_height, label_sheet, load_art, local_tone, mound,
                        patches,
                        strokes_canvas, tidy, watershed, write)

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '宫保鸡丁（简化版）.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D07.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D07_paint.npz')
CAM = Camera(37.38, 6283.1, 627.3, 772.4)                                    # (1)
DISH = "from food_models.stirfry import round_dish\nround_dish(p, 0.1, 0.03, sx=0.93, n=40)"
FLOOR = 0.01

# (2) by eye, where the art's colours don't part the pieces: seeds of pieces the automatic ones miss (kind, a stroke
# in art pixels: a pale scallion the green one next to it would take), and pieces the art draws in several colours,
# each joined into one (art pixels in each: a chilli and its cut end, a scallion ring and its pale heart)
FIX = [('white', [(795, 455), (862, 460)]), ('white', [(752, 580), (782, 600)]), ('chicken', [(400, 440), (425, 446)])]
JOIN = [('white', [(293, 525), (325, 587)]), ('white', [(560, 700), (598, 716)]),
        ('chili', [(812, 489), (787, 533), (843, 528)]), ('chili', [(593, 629), (629, 682), (662, 655), (680, 700)]),
        ('chili', [(494, 803), (538, 820)]), ('chili', [(756, 824), (794, 868), (742, 896)]),
        ('green', [(969, 732), (1025, 805)]), ('green', [(647, 403), (710, 442)]),
        ('green', [(843, 407), (920, 460)]), ('chicken', [(395, 408), (412, 443), (372, 440)]), ('white', [(480, 885)])]


CHANNELS = ['glaze', 'pale', 'deep', 'seed', 'cavity', 'cut', 'ring', 'glint']
# (4) by kind: mesh spacing inside and along the outline (m), how high it rises (puff × its half-width, up to top),
# its relief from the art's shading, its colours: what it is built in, what is painted on it (the mesh has vertices
# along each colour's edge) and what is tinted into it softly: the art's paler tops and deeper sides
KINDS = {
    'chicken': dict(gap=0.008, gb=0.0044, puff=0.6, top=0.012, edge=0.0004, relief=0.0015, mat='GongbaoChicken',
                    ring=(0.0004, 0.0008), ink=[2.0, 2.0],
                    paint=[('glaze', 'GongbaoGlaze'), ('glint', 'GongbaoGlint')],
                    tint=[('pale', '#ffc03e', 0.8), ('deep', '#dd3c00', 0.85)]),
    'chili': dict(gap=0.006, gb=0.0036, puff=0.6, top=0.008, edge=0.0004, relief=0.001, mat='GongbaoChili',
                  ring=(0.0004, 0.0008), ink=[2.0, 2.0],
                  paint=[('seed', 'GongbaoSeed'), ('cavity', 'GongbaoCavity'), ('glint', 'GongbaoChiliGlint')],
                  tint=[('pale', '#ec4a1c', 0.8), ('deep', '#890001', 0.85)]),
    'green': dict(gap=0.0055, gb=0.0034, puff=0.6, top=0.0075, edge=0.0004, relief=0.0012, mat='GongbaoScallion',
                  ring=(0.0004, 0.0008), ink=[2.0, 2.0],
                  paint=[('cut', 'GongbaoScallionCut'), ('glint', 'GongbaoGlint')],
                  tint=[('pale', '#929f00', 0.8), ('deep', '#5b6100', 0.85)]),
    'white': dict(gap=0.0055, gb=0.0034, puff=0.6, top=0.0075, edge=0.0004, relief=0.0012, mat='GongbaoWhite',
                  ring=(0.0004, 0.0008), ink=[2.0, 2.0],
                  paint=[('ring', 'GongbaoRing'), ('glint', 'GongbaoGlint')],
                  tint=[('pale', '#f5ebc3', 0.8), ('deep', '#d58e00', 0.85)]),
    'sauce': None,
}
HEAP = dict(gap=0.02, gb=0.007, top=0.02, reach=0.035, mat='GongbaoSauce', tint=[('pale', '#da5500', 0.8), ('deep', '#460002', 0.85)])
INK = [0.5, 2.5]
# the art's light and shade, painted into each piece's shading normals: the luminance a full step of light is, by
# kind, and how much lighter each piece is at its top and darker low down (the art's light from above)
TONE = {'chicken': 45.0, 'chili': 45.0, 'green': 40.0, 'white': 35.0, 'sauce': 40.0}
RAMP = {'chicken': (0.15, -0.2), 'chili': (0.1, -0.15), 'green': (0.1, -0.15), 'white': (0.1, -0.15)}


def seeds_of(rgb, h, s, v, zone):
    """Each patch of a plain colour one seed: (mask, kind)."""
    out = []
    sauce = zone & (v < 0.42) & ((h < 30) | (h > 330)) & (s > 0.5)
    out += [(m, 'sauce') for m in patches(sauce, 4, 120)]
    chicken = zone & (h > 16) & (h < 48) & (s > 0.35) & (v > 0.72)
    out += [(m, 'chicken') for m in patches(chicken, 5, 300)]
    chili = zone & ((h < 12) | (h > 340)) & (s > 0.75) & (v > 0.45)
    out += [(m, 'chili') for m in patches(chili, 3, 120)]
    green = zone & (h > 50) & (h < 130) & (s > 0.3) & (v > 0.2)
    out += [(m, 'green') for m in patches(green, 3, 80)]
    white = zone & (s < 0.42) & (v > 0.82) & (h > 35) & (h < 90)
    out += [(m, 'white') for m in patches(white, 4, 400)]
    return out


def food_zone(h, s, v, alpha, floor_zb):
    """The food and its sauce: what in the dish's inside is not celadon."""
    celadon = (s < 0.3) & (h > 50) & (h < 220)
    inside = cv2.erode(u8(alpha > 128), disk(40)).astype(bool)
    m = inside & ~celadon & ~((s < 0.12) & (v > 0.9))
    m = cv2.morphologyEx(u8(m), cv2.MORPH_CLOSE, disk(4))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, disk(6))
    return fill_holes(largest(m))


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    labels_out = sys.argv[sys.argv.index('--labels') + 1] if '--labels' in sys.argv else None
    rgba, rgb, h, s, v, lum = load_art(ART)
    H, W = h.shape
    zone = food_zone(h, s, v, rgba[..., 3], None)
    seeds = seeds_of(rgb, h, s, v, zone)
    kinds = []
    mk = np.zeros((H, W), np.int32)
    for m, kind in seeds:
        kinds.append(kind)
        mk[m & (mk == 0)] = len(kinds)
    dark = (v < 0.45) & (s > 0.35)
    ink = dark & ~cv2.dilate(cv2.morphologyEx(u8(dark), cv2.MORPH_OPEN, disk(4)), disk(1)).astype(bool)
    elev = gradient(rgb) + 300.0 * cv2.GaussianBlur(ink.astype(np.float32), (0, 0), 1.2)
    for kind, line in FIX:   # the seeds by eye
        kinds.append(kind)
        mk[strokes_canvas({1: line}, H, W) > 0] = len(kinds)
    lab = watershed(zone, mk, elev)
    for kind, pts in JOIN:   # the pieces joined by eye
        ids = sorted({int(lab[y, x]) for x, y in pts} - {0})
        for j in ids[1:]:
            lab[lab == j] = ids[0]
        kinds[ids[0] - 1] = kind
    lab = tidy(lab, amin=60, open_r=1)
    for pid in range(1, lab.max() + 1):   # a small bit inside one piece (a drop of sauce on the chicken) is its own
        m = lab == pid
        if 0 < m.sum() < 2500:
            ring = cv2.dilate(u8(m), disk(3)).astype(bool) & ~m
            around = lab[ring]
            if len(around) and np.all(around == around[0]) and around[0] > 0:
                lab[m] = around[0]
    print(f'[trace] {len(kinds)} seeds: ' + ', '.join(f'{k} {kinds.count(k)}' for k in sorted(set(kinds))), flush=True)
    if '--at' in sys.argv:   # which piece is where (art pixels x,y ...)
        for q in sys.argv[sys.argv.index('--at') + 1].split(';'):
            x, y = map(int, q.split(','))
            print(f'  ({x},{y}): piece {lab[y, x]} {kinds[lab[y, x] - 1] if lab[y, x] else "-"}')
    if labels_out:
        tints = {'chicken': (250, 170, 60), 'chili': (230, 30, 20), 'green': (90, 170, 60), 'white': (250, 250, 210),
                 'sauce': (90, 20, 10)}
        label_sheet(labels_out, rgb, lab, kinds, tints, (60, 260, 1200, 1000), scale=1.0)
        print(f'[trace] labels {labels_out}', flush=True)
    if '--colours' in sys.argv:   # the art's dark, middle and light colour of each kind
        for k, c in kind_colours(rgb, lum, lab, kinds).items():
            print(f'  {k}: {" ".join(c)}')
    if '--labels-only' in sys.argv:
        return
    kind_of = np.array(['none'] + kinds)[lab]
    paint = classes(rgb, h, s, v, lum, lab, kind_of)
    tone = tone_map(lum, lab, kinds, TONE, ramp=RAMP)
    paint[..., CHANNELS.index('pale'):CHANNELS.index('pale') + 2] = tone_channels(tone, lab > 0)
    floor, zdish, dish_V, _ = dish_view(CAM, DISH, H, W)
    # (4) the heap: the sauce over the whole of the food, rising from the dish to its middle
    hmap = heap_height(CAM, zone, HEAP['top'], HEAP['reach'], H, W)
    hmap, raised = rim_guard(CAM, hmap, zone, floor, dish_V)   # what stands up over the back rim
    colours = art_rgb(rgb, lab)
    out, n_tris = [], {}
    mk = cv2.GaussianBlur(zone.astype(np.float32), (0, 0), 2.0) > 0.5
    sunk = np.maximum(hmap - 0.0012, 0.0009)   # a little under the pieces' feet, so that its coarse faces stay under them
    heap, _, _, _ = mound(CAM, 'heap', 'heap', dict(HEAP, puff=0.0, top=0.0), mk, floor, sunk, lum, paint, CHANNELS,
                          ring=0.0008, close=floor, ink=(0.0, 0.0), smooth_px=3.0, tone=tone, colours=heap_rgb(colours, kind_of),
                          extra=sauce_points(kind_of == 'sauce'))
    out.append(heap)
    n_tris['heap'] = len(heap['tris'])
    for pid in range(1, lab.max() + 1):
        kind = kinds[pid - 1]
        m = lab == pid
        if KINDS.get(kind) is None or m.sum() < 150:
            continue
        kp = KINDS[kind]
        mk = cv2.GaussianBlur(cv2.erode(u8(m), disk(1)).astype(np.float32), (0, 0), 1.5) > 0.5   # a thin crease
        if mk.sum() < 100:
            continue
        piece, uv, R, top = mound(CAM, f'{kind}{pid}', kind, kp, mk, floor, hmap, lum, paint, CHANNELS,
                                  extra_px=12.0, ink=INK, smooth_px=2.0, tone=tone, colours=colours, raised=raised)
        out.append(piece)
        n_tris[kind] = n_tris.get(kind, 0) + len(piece['tris'])
    print(f'[trace] {len(out)} pieces, triangles by kind {n_tris}, all {sum(n_tris.values())}', flush=True)
    write(OUT, PAINT, CAM, CHANNELS, out, paint)
    print(f'[trace] wrote {OUT} and {PAINT}', flush=True)
    if sheet:
        tints = {'chicken': (245, 170, 80), 'chili': (220, 40, 30), 'green': (110, 170, 70), 'white': (245, 240, 200),
                 'sauce': (120, 30, 15)}
        shown = np.where(np.isin(kind_of, ['sauce', 'none']), 0, lab)
        tracing_sheet(sheet, rgba, shown, None, [tints[k] for k in kinds], crop=(60, 260, 1200, 1000),
                      title=('原图上的描线（蓝：每一块）', f'描出的 {len(out) - 1} 块：鸡丁、干辣椒、葱段'))
        print(f'[trace] sheet {sheet}', flush=True)


def classes(rgb, h, s, v, lum, lab, kind_of):
    """The colour classes of CHANNELS over the art, each kind's own: the chicken's pale gold tops and deeper orange
    sides, the red sauce on it and its white glints; the chilli's dark red side, its glints, and in a cut end its
    seeds and dark inside; the scallion's light and dark green and its pale cut end; the pale scallion's yellow
    heart; the sauce's lighter red."""
    food = lab > 0
    chicken, chili, green, white, sauce = (kind_of == k for k in ('chicken', 'chili', 'green', 'white', 'sauce'))
    edge = cv2.morphologyEx(u8(lab), cv2.MORPH_GRADIENT, disk(2)) > 0   # the ink line round each piece
    red = (h < 16) | (h > 340)
    glaze = chicken & ~edge & red & (s > 0.7) & (v > 0.35) & (v < 0.92)
    glint = ~edge & (s < 0.3) & (v > 0.92) & (chicken | green | white | chili)
    glint |= chili & ~edge & (s < 0.45) & (v > 0.85)
    pale = (chicken & (v > 0.94) & (s < 0.74) & (h > 30)) | (chili & red & (v > 0.8) & (s > 0.6)) |            (green & (v > 0.72) & (s > 0.3)) | (sauce & (v > 0.55) & (s > 0.6))
    deep = (chicken & ((h < 27) | (v < 0.8))) | (chili & (v < 0.55)) | (green & (v < 0.5)) |            (white & (s > 0.35) & (v < 0.85))
    seed = chili & ~edge & (h > 28) & (h < 62) & (s > 0.4) & (v > 0.6)
    cavity = chili & ~edge & (v < 0.36)
    cut = green & ~edge & (s < 0.5) & (v > 0.72)
    ring = white & ~edge & (h > 38) & (h < 75) & (s > 0.5) & (v > 0.55)
    a = channels_from([glaze], food, 1.2, 40, 1)
    b = channels_from([pale, deep], food, 2.5, 60, 2)
    H, W = lab.shape
    yy = np.mgrid[0:H, 0:W][0]
    for pid in range(1, lab.max() + 1):   # each piece of chicken paler at its top and deeper low down, as the art
        m = (lab == pid) & chicken         # paints them all, with the art's own on top
        if not m.any():
            continue
        ys = yy[m]
        t = (ys - ys.min()) / max(ys.max() - ys.min(), 1)
        b[..., 0][m] = np.maximum(b[..., 0][m], np.clip((0.35 - t) / 0.3, 0, 1) * 200).astype(np.uint8)
        b[..., 1][m] = np.maximum(b[..., 1][m], np.clip((t - 0.7) / 0.25, 0, 1) * 220).astype(np.uint8)
    c = channels_from([seed, cavity, cut, ring], food, 1.2, 25, 1)
    d = channels_from([glint & ~glaze], food, 0.8, 30, 1)
    return np.concatenate([a, b, c, d], -1)


if __name__ == '__main__':
    main()
