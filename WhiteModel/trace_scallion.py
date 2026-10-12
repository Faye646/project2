"""Traces 葱's art (新建文件夹/葱.png) for produce.scallion (勾勒, with trace_veg.py): writes
food_models/traced_scallion.json and, with --sheet <png>, a tracing sheet.

    python WhiteModel/trace_scallion.py [--sheet <out.png>]

Pieces cut along the art's ink lines: the four flat leaves fanning to the upper left (each lying over the one above
it, as the art overlaps them) running into their pale stalks, the three white bulbs to the lower right, each over the
one above it, and the string tied round the bunch. The root hairs are built by produce.scallion (SC_HAIRS); their
pixels here only keep the bulbs from taking them. Each piece is a lens facing the camera over its outline: the leaves
and the string thin, the bulbs round. Their colours are the art's, vertex by vertex (the leaves' dark green paling
into the stalks' light green, the bulbs' white); painted crisp on faces along them, what the art draws: the light
streaks down the leaves, the lines where one leaf lies over another, the strands of the string.
"""
import sys

import cv2
import numpy as np

from trace_veg import Item, cut, disk, fill_holes, hsv_of, join_paths, lines_of, skeleton_paths, tidy, u8

K, U0, V0 = 4800.0, 800.0, 640.0   # 48 px to the centimetre, the origin's pixel (as the scallion was built before)
STROKES = {
    1: [[(380, 90), (500, 150), (650, 270), (760, 370)]],                    # leaf A, top
    2: [[(300, 180), (450, 240), (600, 330), (750, 420)]],                   # leaf B
    3: [[(150, 300), (350, 340), (550, 400), (750, 480)], [(170, 260)]],    # leaf C
    4: [[(200, 420), (400, 450), (600, 520), (780, 580)]],                   # leaf D, lowest
    5: [[(1000, 600), (1150, 640), (1280, 670)]],                            # bulb, upper
    6: [[(1050, 700), (1150, 740), (1250, 770)]],                            # bulb, middle
    7: [[(1050, 790), (1130, 830), (1200, 860)]],                            # bulb, lower
    8: [],                                                                    # the string (found by its colour)
    10: [[(980, 572), (1080, 590), (1180, 615), (1260, 650)]],              # the strand over the upper bulb
    11: [],                                                                   # the strand between the bulbs
    9: [[(1350, 720), (1400, 760)], [(1300, 900), (1350, 880), (1420, 900)], [(1330, 950)], [(1250, 930)]],  # roots
}


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    it = Item('葱.png', K, U0, V0)
    h, s, v = hsv_of(it.rgb)
    yy, xx = np.mgrid[0:it.H, 0:it.W]
    tan = it.zone & (h > 22) & (h < 48) & (s > 0.28) & (v > 0.6) & (xx > 790) & (xx < 1110) & (yy > 480) & \
        (yy < 700)
    tan = cv2.morphologyEx(u8(tan), cv2.MORPH_OPEN, disk(2)).astype(bool)
    ys, xs = np.nonzero(cv2.erode(u8(tan), disk(3)))
    STROKES[8] = [[(int(x), int(y))] for x, y in zip(xs[::25], ys[::25])]
    # the root hairs, cream inside their brown lines: their middles, from the root plates out
    cream = it.zone & ((xx > 1255) | ((yy > 860) & (xx > 1140))) & (h > 20) & (h < 60) & (s > 0.14) & (s < 0.5)
    cream &= v > 0.74
    white = it.zone & (s < 0.16) & (v > 0.72) & (xx > 900)   # the bulbs' white, its shading lines closed over
    white = fill_holes(cv2.morphologyEx(u8(white), cv2.MORPH_CLOSE, disk(10)).astype(bool))
    cream &= ~cv2.dilate(u8(white), disk(3)).astype(bool)
    for pu, pv in ((1290, 700), (1245, 790), (1192, 866)):   # not the bulbs' rounded ends round their root plates
        cream &= (xx - pu) ** 2 + (yy - pv) ** 2 > 34 ** 2
    cream = cv2.morphologyEx(u8(cream), cv2.MORPH_OPEN, disk(1)).astype(bool)
    band = cream | (it.zone & (h > 18) & (h < 50) & (s > 0.3) & (v > 0.45))   # with their brown-tan lines
    band &= (xx > 1140) & ~cv2.dilate(u8(white), disk(3)).astype(bool)
    for pu, pv in ((1290, 700), (1245, 790), (1192, 866)):
        band &= (xx - pu) ** 2 + (yy - pv) ** 2 > 34 ** 2
    band = cv2.morphologyEx(u8(band), cv2.MORPH_CLOSE, disk(1)).astype(bool)
    hairs = join_paths(skeleton_paths(band, min_len=10.0, step=9.0), reach=10.0, max_turn=1.1)
    hairs = [hp for hp in hairs if len(hp) >= 3]
    for hp in hairs:   # each from its root end (nearer the plates, on the left) out to its tip
        if hp[0][0] > hp[-1][0]:
            hp.reverse()
    n_hair_tris = sum(6 * (len(hp) - 1) + 6 for hp in hairs)
    print(f'[trace] {len(hairs)} root hairs, {n_hair_tris} triangles', flush=True)
    STROKES[9] = STROKES[9] + [[(x, y) for x, y, _ in hp] for hp in hairs]
    lab = cut(it.rgb, it.zone, STROKES, it.ink, width=3)
    # what the roots and the string took that isn't hair or string goes to the nearest bulb or strand
    from trace_common import flood
    hairish = cv2.dilate(u8(cream | (it.zone & (xx > 1150) & (h > 20) & (h < 50) & (s > 0.3) & (v < 0.75))),
                         disk(2)).astype(bool)
    take = ((lab == 9) & ~hairish) | ((lab == 8) & ~cv2.dilate(u8(tan), disk(3)).astype(bool))
    mk = np.where(take, 0, -1).astype(np.int32)
    keep = np.isin(lab, (5, 6, 7, 10)) & ~take
    mk[keep] = lab[keep]
    got = flood(mk, cv2.GaussianBlur(it.ink.astype(np.float32), (0, 0), 1.0) * 100)
    lab = np.where(take & (got > 0), got, lab)
    yy2 = yy
    mid = (lab == 6) & (yy2 < 700) & (xx > 1000)   # the strip of the middle one's stalk over the bulbs
    a, b, c, d = (tidy(lab == i) for i in range(1, 5))
    b1, b2, b3 = (tidy(lab == i, 3) for i in range(5, 8))
    string = tidy(lab == 8)
    roots = lab == 9
    top = tidy(lab == 10)
    inner = lambda m, r: m & cv2.erode(u8(m), disk(r)).astype(bool)
    leaves = a | b | c | d
    streak = lines_of(it.rgb, inner(leaves, 5), dark=False, radius=5, thresh=12.0, min_area=30, min_len=25, fill=0.5)
    strands = lines_of(it.rgb, inner(string, 2), dark=True, radius=3, thresh=16.0, min_area=8, min_len=8, fill=1.0)
    it.remove |= streak | strands
    common = dict(gap=50.0, fine=21.0, gb=13.0, smooth=1.8, sigma=2.5, back_gap=90.0, mark_px=9.0)
    leaf = dict(mat='ScallionArtLeaf', puff=0.18, back=0.15, rim=0.35, **common)
    for i, (name, m) in enumerate((('leafA', a), ('leafB', b), ('leafC', c), ('leafD', d))):
        it.add(name, m, i, 'lens', marks=[(streak & m, None)], **leaf)
    for i, (name, m) in enumerate((('bulb1', b1), ('bulb2', b2), ('bulb3', b3))):
        it.add(name, m, 4 + i, 'lens', mat='ScallionArtBulb', puff=0.4, back=0.4, rim=0.6, inner_ink_min=80,
               **{**common, 'smooth': 3.5})
    it.add('top', top, 4, 'lens', mat='ScallionArtBulb', puff=0.3, back=0.3, rim=0.5, **common)
    it.add('string', string, 8, 'lens', mat='ScallionArtString', puff=0.25, back=0.2,
           marks=[(strands & string, None)], **{**common, 'fine': 14.0, 'gb': 9.0, 'mark_px': 8.0})
    it.add('roots', roots, 9, 'none')
    it.build(budget=7900, extra_tris=n_hair_tris + 950)   # and the matted root bases
    it.check()
    it.save('scallion', {'hairs': hairs})
    if sheet:
        it.sheet(sheet, ('原图上的描线', '四片葱叶、三个葱白、绳'), crop=(90, 40, 1480, 1010))


if __name__ == '__main__':
    main()
