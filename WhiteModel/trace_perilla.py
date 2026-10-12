"""Traces 紫苏's art (新建文件夹/紫苏.png) for produce.perilla (勾勒, with trace_veg.py): writes
food_models/traced_perilla.json and, with --sheet <png>, a tracing sheet.

    python WhiteModel/trace_perilla.py [--sheet <out.png>]

Pieces cut along the art's ink lines: the eleven serrated leaves of the bunch, from those at the back (the purple one
on top, the green ones behind it) to the big ones in front, the bundle of stalks with their cut ends at the lower left,
and the string tied round it. Each piece is a lens facing the camera over its outline: the leaves thin and a little
cupped, the stalks round, the string thin. Their colours are the art's, vertex by vertex: the leaves' purple with its
lighter and deeper washes and the olive green at their bases and edges, the stalks' green and purple; painted crisp on
faces along them, what the art draws: the pink midribs and veins, the lines where one leaf lies over another, the
strands of the string.
"""
import sys

import cv2
import numpy as np

from trace_veg import Item, cut, disk, hsv_of, ink_of, lines_of, load, settle, tidy, u8

K, U0, V0 = 5000.0, 640.0, 1100.0   # 50 px to the centimetre, the origin's pixel (as the perilla was built before)
LEAVES = [   # name, level, strokes from base to tip (art px), read off the art
    ('top', 0, [[(700, 330), (660, 230), (620, 150), (595, 100)], [(760, 300), (830, 330)], [(700, 160), (760, 220)]]),
    ('backleft', 0, [[(450, 300), (400, 270), (330, 240)]]),
    ('backright', 0, [[(940, 470), (950, 410), (960, 360)]]),
    ('lowleft', 0, [[(240, 640), (200, 580), (150, 520)]]),
    ('left', 1, [[(420, 600), (390, 520), (330, 420), (260, 320)], [(230, 420), (300, 500)]]),
    ('midleft', 1, [[(520, 540), (550, 450), (565, 360), (575, 270)], [(620, 330), (630, 420)]]),
    ('right', 1, [[(960, 560), (1050, 520), (1150, 490)], [(1000, 600), (1080, 600)]]),
    ('centre', 2, [[(520, 650), (600, 590), (700, 520), (800, 460), (870, 430)], [(620, 470), (700, 430)],
                   [(650, 640), (760, 600)]]),
    ('lowright', 2, [[(760, 720), (880, 730), (1000, 760), (1120, 800)], [(900, 640), (1000, 660)],
                     [(900, 830), (1000, 880)]]),
    ('front', 3, [[(620, 840), (700, 900), (780, 980), (850, 1080)], [(760, 880), (850, 900)],
                  [(700, 1000), (760, 1060)]]),
]
STALKS = [[(130, 1060), (250, 960), (350, 880), (450, 820)], [(100, 985), (200, 935)], [(180, 1090), (280, 1020),
          (380, 950)], [(470, 800), (560, 740), (620, 700)], [(420, 960), (520, 900)]]


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = load('紫苏.png')
    rgb, zone = rgba[..., :3].copy(), rgba[..., 3] > 128
    it = Item('紫苏.png', K, U0, V0, ink=ink_of(rgb, zone, vmax=0.34, smin=0.35, hues=(350.0, 40.0)))
    h, s, v = hsv_of(it.rgb)
    yy, xx = np.mgrid[0:it.H, 0:it.W]
    tan = zone & (h > 28) & (h < 46) & (s > 0.3) & (v > 0.72) & (xx < 520) & (yy > 720)   # the string
    tan = cv2.morphologyEx(u8(tan), cv2.MORPH_OPEN, disk(2)).astype(bool)
    ys, xs = np.nonzero(cv2.erode(u8(tan), disk(3)))
    strokes = {i + 1: st for i, (_, _, st) in enumerate(LEAVES)}
    n = len(LEAVES)
    near_tan = cv2.dilate(u8(tan), disk(8)).astype(bool)

    def off_string(lines, step=6.0):   # the stalks' strokes as dots, none on the string
        out = []
        for line in lines:
            for (x0, y0), (x1, y1) in zip(line, line[1:]):
                for t in np.arange(0, 1, step / max(np.hypot(x1 - x0, y1 - y0), 1)):
                    x, y = int(round(x0 + (x1 - x0) * t)), int(round(y0 + (y1 - y0) * t))
                    if not near_tan[y, x]:
                        out.append([(x, y)])
        return out
    strokes[n + 1] = off_string(STALKS)
    strokes[n + 2] = [[(int(x), int(y))] for x, y in zip(xs[::20], ys[::20])]
    lab = cut(it.rgb, it.zone, strokes, it.ink)
    # the string is only its tan rope: what its flood took beyond that goes to the nearest stalk or leaf
    from trace_common import flood
    rope = cv2.morphologyEx(u8(zone & (h > 25) & (h < 50) & (s > 0.2) & (v > 0.6) & (xx < 540) & (yy > 700)),
                            cv2.MORPH_CLOSE, disk(2)).astype(bool)
    take = (lab == n + 2) & ~rope
    mk = np.where(take, 0, -1).astype(np.int32)
    keep = (lab > 0) & (lab != n + 2)
    mk[keep] = lab[keep]
    got = flood(mk, cv2.GaussianBlur(it.ink.astype(np.float32), (0, 0), 1.0) * 100)
    lab = np.where(take & (got > 0), got, lab)
    lab = settle(lab, it.ink)
    if '--labels' in sys.argv:
        np.save(sys.argv[sys.argv.index('--labels') + 1], lab)
    inner = lambda m, r: m & cv2.erode(u8(m), disk(r)).astype(bool)
    masks = [tidy(lab == i + 1, 4) for i in range(n)]   # no hair-thin tips
    stalks, string = tidy(lab == n + 1, 4), tidy(lab == n + 2, 3)
    leaves = np.any(masks, 0)
    veins = lines_of(it.rgb, inner(leaves, 5), dark=False, radius=5, thresh=10.0, min_area=30, min_len=22, fill=0.5)
    strands = lines_of(it.rgb, inner(string, 2), dark=True, radius=3, thresh=16.0, min_area=8, min_len=8, fill=1.0)
    it.remove |= veins | strands
    common = dict(gap=56.0, fine=26.0, gb=14.0, smooth=1.5, sigma=2.5, back_gap=100.0, mark_px=11.0)
    for (name, level, _), m in zip(LEAVES, masks):
        it.add(name, m, level, 'lens', mat='PerillaArtLeaf', puff=0.12, back=0.1, rim=0.3, marks=[(veins & m, None)],
               one_ring=True, back_ring=True, **{**common, 'smooth': 3.0})
    it.add('stalks', stalks, 4, 'lens', mat='PerillaArtStalk', puff=0.35, back=0.35, rim=0.5, one_ring=True,
           **{**common, 'smooth': 2.5})
    it.add('string', string, 5, 'lens', mat='PerillaArtTwine', puff=0.25, back=0.2, marks=[(strands & string, None)],
           **{**common, 'fine': 14.0, 'gb': 9.0, 'mark_px': 8.0})
    it.build(budget=7900)
    it.check()
    it.save('perilla')
    if sheet:
        it.sheet(sheet, ('原图上的描线', '紫苏叶、叶柄、绳'), crop=(80, 50, 1230, 1190))


if __name__ == '__main__':
    main()
