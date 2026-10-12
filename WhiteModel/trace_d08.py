"""Traces 可乐鸡翅's art (新建文件夹/可乐鸡翅.png) for D08, so that its wings, scallion and ginger are modelled 1:1 (勾勒):
writes food_models/traced_D08.json and the colours of its pieces food_models/traced_D08_paint.npz, which
stirfry.kele_jichi builds the dish from, and a tracing sheet.

    python WhiteModel/trace_d08.py [--sheet <out.png>] [--labels <out.png>] [--at "x,y;x,y"]

1. The art's camera: fitted so that the oval dish kele_jichi builds (round_dish, kept) covers the art's dish best
   (IoU 0.978).
2. The pieces (trace_heap.cut): the five wings from strokes along each (WINGS, read off the art by eye), the
   scallion lengths and ginger strips found automatically, each patch of their colour one seed, the dark sauce
   likewise; flooded out over the art to the ink lines between them.
3. Their colours: the wings' glossy amber with the art's paler lit skin and its deep brown folds tinted in, the
   glints and the dark cut ends (the bone in the meat) painted on; the scallion's light and dark green and pale cut
   ends; the ginger's paler middle.
4. The heap under them: the dark cola sauce over the whole food, a little raised under the wings; each piece a
   rounded mound over its outline lying on it, the wings plump, so that from the art's camera it covers exactly what
   the art paints.
"""
import os
import sys

import cv2
import numpy as np

from trace_common import Camera, disk, tracing_sheet, u8
from trace_heap import (heap_rgb, rim_guard, channels_from, tone_channels, kind_colours, sauce_points, art_rgb, cut, dish_view, food_zone, heap_height, label_sheet, load_art, mound,
                        patches, report_at, tone_map, write)

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '可乐鸡翅.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D08.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D08_paint.npz')
CAM = Camera(36.19, 6308.3, 632.2, 745.8)                                    # (1)
DISH = ("from food_models.stirfry import round_dish\n"
        "round_dish(p, 0.105, 0.026, sx=0.84, n=48, floor=0.01, yaw=-0.68)")

# (2) a stroke along each wing (art pixels), by eye; what the art's colours don't part, by eye
WINGS = [[(490, 340), (600, 400), (720, 470), (820, 530)], [(900, 420), (1000, 490), (1100, 570)],
         [(160, 640), (280, 590), (400, 545)], [(620, 640), (720, 690), (860, 730), (1000, 760)],
         [(300, 720), (420, 780), (560, 830), (680, 870)]]
FIX = []
JOIN = [('green', [(559, 456), (570, 466)]), ('green', [(906, 579), (937, 604)]),
        ('ginger', [(609, 685), (646, 701)]), ('green', [(227, 772)])]
CHANNELS = ['pale', 'deep', 'glint', 'end', 'cut', 'fold']
# (4) by kind: mesh spacing inside and along the outline (m), how high it rises (puff × its half-width, up to top),
# its relief from the art's shading, its colours: what it is built in, what is painted on it (the mesh has vertices
# along each colour's edge) and what is tinted into it softly
KINDS = {
    'wing': dict(gap=0.0075, gb=0.0042, puff=0.7, top=0.02, edge=0.0004, relief=0.0015, mat='ColaGlaze',
                 ring=(0.0004, 0.0008), ink=[2.0, 2.0],
                 paint=[('fold', 'ColaFold'), ('end', 'ColaWingEnd'), ('glint', 'ColaGlint')],
                 tint=[('pale', '#f69600', 0.8), ('deep', '#ad2300', 0.85)]),
    'green': dict(gap=0.005, gb=0.0032, puff=0.6, top=0.0055, edge=0.0004, relief=0.0, mat='ColaScallion',
                  ring=(0.0004, 0.0008), ink=[2.0, 2.0], paint=[('cut', 'GongbaoScallionCut')],
                  tint=[('pale', '#a7b500', 0.8), ('deep', '#747100', 0.85)]),
    'ginger': dict(gap=0.005, gb=0.0032, puff=0.5, top=0.0035, edge=0.0004, relief=0.0, mat='ColaGinger',
                   ink=[0.6, 1.8], paint=[], tint=[('pale', '#fddd77', 0.8), ('deep', '#d97400', 0.85)]),
    'sauce': None,
}
HEAP = dict(gap=0.014, gb=0.007, top=0.012, reach=0.03, mat='ColaPool', tint=[('pale', '#af6c00', 0.8), ('deep', '#410000', 0.85)])
INK = [0.5, 2.5]
TONE = {'wing': 50.0, 'green': 40.0, 'ginger': 35.0, 'sauce': 40.0}
RAMP = {'wing': (0.1, -0.15)}


def seeds_of(h, s, v, zone):
    """Each patch of the scallion's green, the ginger's pale yellow and the dark sauce one seed: (mask, kind)."""
    out = []
    out += [(m, 'green') for m in patches(zone & (h > 60) & (h < 135) & (s > 0.35) & (v > 0.3), 3, 80)]
    out += [(m, 'ginger') for m in patches(zone & (h > 38) & (h < 66) & (s > 0.25) & (s < 0.78) & (v > 0.8), 3, 120)]
    out += [(m, 'sauce') for m in patches(zone & (v < 0.33) & (s > 0.5), 4, 150)]
    return out


def classes(rgb, h, s, v, lum, lab, kind_of):
    """The colour classes of CHANNELS over the art: the wings' paler lit skin and deep brown folds, their glints and
    the dark cut ends; the scallion's light and dark green and pale cut ends; the ginger's paler middle and deeper
    edges; the sauce's lighter amber."""
    food = lab > 0
    wing, green, ginger, sauce = (kind_of == k for k in ('wing', 'green', 'ginger', 'sauce'))
    edge = cv2.morphologyEx(u8(lab), cv2.MORPH_GRADIENT, disk(2)) > 0
    pale = (wing & (v > 0.86) & (s > 0.45)) | (green & (v > 0.72) & (s > 0.3)) | (ginger & (v > 0.93)) | \
           (sauce & (v > 0.5))
    deep = (wing & (v < 0.55)) | (green & (v < 0.5)) | (ginger & (v < 0.85))
    glint = ~edge & (s < 0.32) & (v > 0.9) & (wing | green)
    end = wing & ~edge & (v < 0.42) & (h > 5) & (h < 40)
    end = cv2.morphologyEx(u8(end), cv2.MORPH_OPEN, disk(3)).astype(bool)   # the dark cut ends, not the thin folds
    cutc = green & ~edge & (s < 0.5) & (v > 0.75)
    fold = wing & ~edge & ~end & (v < 0.52)   # the deep folds of its skin, dark red-brown
    a = channels_from([pale, deep], food, 2.5, 60, 2)
    b = channels_from([glint], food, 0.8, 30, 1)
    c = channels_from([end, cutc], food, 1.5, 150, 2)
    d = channels_from([fold], food, 1.0, 50, 1)
    return np.concatenate([a, b, c, d], -1)


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    labels_out = sys.argv[sys.argv.index('--labels') + 1] if '--labels' in sys.argv else None
    rgba, rgb, h, s, v, lum = load_art(ART)
    H, W = h.shape
    zone = food_zone(h, s, v, rgba[..., 3], over_rim=(h < 40) & (s > 0.4) & (v > 0.45))   # the back wing's top
    lab, kinds = cut(rgb, s, v, zone, seeds_of(h, s, v, zone), [('wing', w) for w in WINGS] + FIX, JOIN)
    print(f'[trace] {len(kinds)} seeds: ' + ', '.join(f'{k} {kinds.count(k)}' for k in sorted(set(kinds))), flush=True)
    if '--at' in sys.argv:
        report_at(lab, kinds, sys.argv[sys.argv.index('--at') + 1])
    if labels_out:
        tints = {'wing': (200, 90, 30), 'green': (90, 170, 60), 'ginger': (250, 230, 140), 'sauce': (70, 25, 10)}
        label_sheet(labels_out, rgb, lab, kinds, tints, (40, 260, 1240, 1020), scale=0.8)
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
    floor, _, dish_V, _ = dish_view(CAM, DISH, H, W)
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
        mk = cv2.GaussianBlur(cv2.erode(u8(m), disk(1)).astype(np.float32), (0, 0), 1.5) > 0.5
        if mk.sum() < 100:
            continue
        piece, uv, R, top = mound(CAM, f'{kind}{pid}', kind, KINDS[kind], mk, floor, hmap, lum, paint, CHANNELS,
                                  extra_px=10.0, ink=INK, smooth_px=2.0, tone=tone, colours=colours, raised=None,
                                  band_px=(4.0, 24.0) if kind == 'wing' else (3.0, 14.0))
        out.append(piece)
        n_tris[kind] = n_tris.get(kind, 0) + len(piece['tris'])
    print(f'[trace] {len(out)} pieces, triangles by kind {n_tris}, all {sum(n_tris.values())}', flush=True)
    write(OUT, PAINT, CAM, CHANNELS, out, paint)
    print(f'[trace] wrote {OUT}', flush=True)
    if sheet:
        tints = {'wing': (220, 120, 50), 'green': (110, 170, 70), 'ginger': (250, 230, 150), 'sauce': (100, 40, 15)}
        shown = np.where(np.isin(kind_of, ['sauce', 'none']), 0, lab)
        tracing_sheet(sheet, rgba, shown, None, [tints[k] for k in kinds], crop=(40, 260, 1240, 1020),
                      title=('原图上的描线（蓝：每一块）', f'描出的 {len(out) - 1} 块：鸡翅、葱段、姜丝'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
