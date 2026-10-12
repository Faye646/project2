"""Traces 土豆炖肉's art (新建文件夹/土豆炖肉.png) for D13, so that what is in its clay pot is modelled 1:1 (勾勒): writes
food_models/traced_D13.json and the colours of its pieces food_models/traced_D13_paint.npz, which
stirfry.tudou_dunrou builds the dish from, and a tracing sheet.

    python WhiteModel/trace_d13.py [--sheet <out.png>] [--labels <out.png>] [--at "x,y;x,y"] [--colours]

1. The art's camera and the clay pot (casserole: deeper, its lugs flatter and longer, the gravy higher than before)
   fitted together (potfit) so that the pot covers the art's (IoU 0.946) and its gravy, where the art sees it inside
   the rim, the art's (0.987): that is where the food is.
2. The pieces (trace_heap.cut): the potatoes, the radish and the scallion found automatically, each patch of their
   colour one seed; the pork belly from strokes (PORK: its lean, fat and skin are many colours); the gravy round
   them likewise; flooded out over the art to the ink lines between them.
3. Their colours: the art's own, painted on through the vertex tint (art_colours), the pork's pale fat layers and
   the radish's fine lines as they are; the scallion's light and dark green.
4. The gravy a surface over the whole of it, a little above the pot's; each piece a rounded mound over its outline
   rising out of the gravy, the potatoes and the pork high, the radish lower, so that from the art's camera it
   covers exactly what the art paints, the art's shading in its relief and shading normals.
"""
import os
import sys

import cv2
import numpy as np

from trace_common import Camera, dish_mesh, disk, raster, tracing_sheet, u8
from trace_heap import (art_rgb, channels_from, cut, kind_colours, label_sheet, load_art, mound, patches, report_at,
                        sauce_points, tone_channels, tone_map, write)

HERE = os.path.dirname(os.path.abspath(__file__))
ART = os.path.join(HERE, '..', '新建文件夹', '土豆炖肉.png')
OUT = os.path.join(HERE, 'food_models', 'traced_D13.json')
PAINT = os.path.join(HERE, 'food_models', 'traced_D13_paint.npz')
CAM = Camera(40.75, 5541.0, 638.4, 857.1)                                    # (1)
POT = ("from food_models.stirfry import casserole\nimport math\n"
       "casserole(tmp, 0.1, 0.0696, 0.0595, sx=0.933, rim=0.0045, lugs=(math.pi, 0.0), foot=0.643, "
       "belly=0.845, lug=(0.0103, 0.0281, 0.0075), lug_z=0.0043)")
ZG = 0.0595   # the gravy's surface in the pot

# (2) a stroke along each piece of pork belly (art pixels), by eye; what the art's colours don't part, by eye
PORK = []
FIX = []
JOIN = [('potato', [(520, 343), (614, 360), (553, 410), (487, 432)]), ('potato', [(837, 588), (937, 643)]),
        ('potato', [(481, 697), (517, 749), (450, 769), (590, 838)]), ('potato', [(370, 468), (387, 502), (237, 547)]),
        ('radish', [(437, 512), (540, 566)]), ('radish', [(809, 427), (948, 466)]), ('radish', [(776, 358)]),
        ('radish', [(937, 766)]), ('pork', [(398, 404)]), ('pork', [(664, 454)]), ('pork', [(292, 649)]),
        ('pork', [(748, 760), (876, 799)]), ('potato', [(1025, 604)])]
CHANNELS = ['pale', 'deep', 'glint', 'fat', 'line', 'cut']
# (4) by kind: mesh spacing inside and along the outline (m), how high it rises (puff × its half-width, up to top),
# where its outline sits over the gravy (edge), its relief, its colours
KINDS = {
    'potato': dict(gap=0.0075, gb=0.0042, puff=0.7, top=0.016, edge=0.0005, relief=0.0015, mat='StewSpud',
                   ring=(0.0004, 0.0008), ink=[2.0, 2.0], paint=[('glint', 'StewGlint')], tint=[]),
    'radish': dict(gap=0.0075, gb=0.0042, puff=0.6, top=0.012, edge=0.0005, relief=0.001, mat='StewRadish',
                   ring=(0.0004, 0.0008), ink=[2.0, 2.0], paint=[('line', 'StewRadishLine')], tint=[]),
    'pork': dict(gap=0.007, gb=0.004, puff=0.7, top=0.016, edge=0.0005, relief=0.0015, mat='StewPork',
                 ring=(0.0004, 0.0008), ink=[2.0, 2.0], paint=[('fat', 'StewFat'), ('glint', 'StewGlint')], tint=[]),
    'green': dict(gap=0.004, gb=0.003, puff=0.6, top=0.004, edge=0.0004, relief=0.0, mat='StewScallion',
                  ink=[0.6, 1.8], paint=[('cut', 'GongbaoScallionCut')], tint=[]),
    'gravy': None,
}
GRAVY = dict(gap=0.02, gb=0.007, mat='StewGravyArt', tint=[])
INK = [0.5, 2.5]
RAMP = {'potato': (0.1, -0.15), 'pork': (0.1, -0.15), 'radish': (0.1, -0.15)}


def seeds_of(h, s, v, zone):
    """Each patch of the potato's yellow, the radish's pale cream, the scallion's green and the gravy's orange one
    seed: (mask, kind)."""
    out = []
    out += [(m, 'green') for m in patches(zone & (h > 60) & (h < 140) & (s > 0.4) & (v > 0.3), 2, 40)]
    out += [(m, 'potato') for m in patches(zone & (h > 42) & (h < 58) & (s > 0.52) & (v > 0.85), 6, 700)]
    out += [(m, 'radish') for m in patches(zone & (h > 28) & (h < 60) & (s > 0.12) & (s < 0.5) & (v > 0.86), 6, 700)]
    out += [(m, 'pork') for m in patches(zone & ((h < 22) | (h > 340)) & (s > 0.45) & (v > 0.2) & (v < 0.6), 5, 400)]
    out += [(m, 'gravy') for m in patches(zone & (h > 28) & (h < 42) & (s > 0.62) & (v > 0.55), 6, 300)]
    return out


def gravy_view(H, W):
    """Where the art sees the gravy's surface in the pot (inside its rim): the pot and its fill rasterized, the fill
    nearest."""
    full = dish_mesh('tmp = p\n' + POT)
    fill = dish_mesh("from mathutils import Matrix\ntmp = Part()\n" + POT +
                     "\np.lathe([(0.0849, 0.0595 + 0.0012), (0.0, 0.0595 + 0.0016)], 'StewGravy', n=48, "
                     "close_ends=False, M=Matrix.Diagonal((0.933, 1.0, 1.0, 1.0)))")
    zb, zid = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
    for k, (V, T) in enumerate((fill, full)):
        u, v = CAM.project(V[:, 0], V[:, 1], V[:, 2])
        raster(np.stack([u, v], -1)[T], CAM.depth(V)[T], np.full(len(T), k), H, W, zb, zid)
    return zid == 0


def classes(rgb, h, s, v, lum, lab, kind_of):
    """The colour classes of CHANNELS over the art: the glints on the potatoes and the pork, the pork's pale fat
    layers, the radish's fine lines, the scallion's pale cut ends."""
    food = lab > 0
    potato, radish, pork, green = (kind_of == k for k in ('potato', 'radish', 'pork', 'green'))
    edge = cv2.morphologyEx(u8(lab), cv2.MORPH_GRADIENT, disk(2)) > 0
    glint = ~edge & (s < 0.25) & (v > 0.93) & (potato | pork)
    fat = pork & ~edge & (s < 0.45) & (v > 0.68)
    line = radish & ~edge & (v < 0.8) & (s > 0.2)
    cutc = green & ~edge & (s < 0.5) & (v > 0.75)
    a = np.zeros(lab.shape + (2,), np.uint8)
    b = channels_from([glint], food, 0.8, 25, 1)
    c = channels_from([fat, line, cutc], food, 1.0, 40, 1)
    return np.concatenate([a, b, c], -1)


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    labels_out = sys.argv[sys.argv.index('--labels') + 1] if '--labels' in sys.argv else None
    rgba, rgb, h, s, v, lum = load_art(ART)
    H, W = h.shape
    zone = gravy_view(H, W) & (rgba[..., 3] > 128)
    zone = cv2.morphologyEx(u8(zone), cv2.MORPH_OPEN, disk(3)).astype(bool)
    lab, kinds = cut(rgb, s, v, zone, seeds_of(h, s, v, zone), [('pork', w) for w in PORK] + FIX, JOIN)
    print(f'[trace] {len(kinds)} seeds: ' + ', '.join(f'{k} {kinds.count(k)}' for k in sorted(set(kinds))), flush=True)
    if '--at' in sys.argv:
        report_at(lab, kinds, sys.argv[sys.argv.index('--at') + 1])
    if labels_out:
        tints = {'potato': (250, 200, 60), 'radish': (250, 250, 230), 'pork': (150, 60, 40), 'green': (90, 170, 60),
                 'gravy': (220, 150, 50)}
        label_sheet(labels_out, rgb, lab, kinds, tints, (120, 260, 1120, 920), scale=0.9)
        print(f'[trace] labels {labels_out}', flush=True)
    if '--colours' in sys.argv:
        for k, c in kind_colours(rgb, lum, lab, kinds).items():
            print(f'  {k}: {" ".join(c)}')
    if '--labels-only' in sys.argv:
        return
    kind_of = np.array(['none'] + kinds)[lab]
    paint = classes(rgb, h, s, v, lum, lab, kind_of)
    tone = tone_map(lum, lab, kinds, ramp=RAMP)
    paint[..., 0:2] = tone_channels(tone, lab > 0)
    colours = art_rgb(rgb, lab)
    floor = lambda x, y: np.full_like(np.asarray(x, float), ZG)
    hmap = np.full((H, W), 0.0008, np.float32)
    out, n_tris = [], {}
    mk = cv2.GaussianBlur(zone.astype(np.float32), (0, 0), 2.0) > 0.5
    gravy, _, _, _ = mound(CAM, 'gravy', 'gravy', dict(GRAVY, puff=0.0, top=0.0), mk, floor, hmap, lum, paint,
                           CHANNELS, ring=0.0008, ink=(0.0, 0.0), smooth_px=3.0, tone=tone, colours=colours,
                           extra=sauce_points(kind_of == 'gravy'))
    out.append(gravy)
    n_tris['gravy'] = len(gravy['tris'])
    for pid in range(1, lab.max() + 1):
        kind = kinds[pid - 1]
        m = lab == pid
        if KINDS.get(kind) is None or m.sum() < 100:
            continue
        mk = cv2.GaussianBlur(cv2.erode(u8(m), disk(1)).astype(np.float32), (0, 0), 1.5) > 0.5
        if mk.sum() < 80:
            continue
        piece, uv, R, top = mound(CAM, f'{kind}{pid}', kind, KINDS[kind], mk, floor, hmap, lum, paint, CHANNELS,
                                  extra_px=10.0, ink=INK, smooth_px=2.0, tone=tone, colours=colours,
                                  band_px=(4.0, 24.0))
        out.append(piece)
        n_tris[kind] = n_tris.get(kind, 0) + len(piece['tris'])
    print(f'[trace] {len(out)} pieces, triangles by kind {n_tris}, all {sum(n_tris.values())}', flush=True)
    write(OUT, PAINT, CAM, CHANNELS, out, paint)
    print(f'[trace] wrote {OUT}', flush=True)
    if sheet:
        tints = {'potato': (250, 200, 70), 'radish': (250, 248, 230), 'pork': (170, 80, 50), 'green': (110, 170, 70),
                 'gravy': (230, 160, 60)}
        shown = np.where(np.isin(kind_of, ['gravy', 'none']), 0, lab)
        tracing_sheet(sheet, rgba, shown, None, [tints[k] for k in kinds], crop=(120, 260, 1120, 920),
                      title=('原图上的描线（蓝：每一块）', f'描出的 {len(out) - 1} 块：土豆、萝卜、五花肉、葱花'))
        print(f'[trace] sheet {sheet}', flush=True)


if __name__ == '__main__':
    main()
