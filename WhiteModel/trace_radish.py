"""Traces 萝卜's art (新建文件夹/萝卜.png) for produce.radish (勾勒, with trace_veg.py): writes food_models/traced_radish.json
and, with --sheet <png>, a tracing sheet.

    python WhiteModel/trace_radish.py [--sheet <out.png>]

Pieces cut along the art's ink lines: the four leaves fanning up behind the radish's crown and the pale stalks
between them, the radish (its root hairs are built by produce.radish from RADISH_HAIRS) and the two slices in front of
it, the near one over the far one. Each is a lens facing the camera over its outline: the radish as thick as it is
wide, the leaves and the stalks thin, the slices flat discs. Their colours are the art's, vertex by vertex: the
radish's white turning green at its shoulder, the leaves' greens light and dark, the slices' pale cut faces; painted
crisp on faces along them, what the art draws: the leaves' pale midribs and veins and the lines where one leaf lies
over another, the short brown lines across the radish, the pale rays and the ring of the cut faces.
"""
import sys

import cv2

from trace_veg import Item, cut, disk, ink_of, lines_of, load, tidy, u8

K, U0, V0 = 4500.0, 650.0, 850.0   # 45 px to the centimetre, the origin's pixel (RADISH_ART, as built before)
STROKES = {
    1: [[(650, 200), (700, 250), (750, 280)]],                                   # leaf, top left
    2: [[(850, 120), (900, 200), (870, 280)], [(950, 250)]],                     # leaf, top middle
    3: [[(1050, 220), (1100, 300), (1020, 350)]],                                # leaf, right, up
    4: [[(1100, 450), (1150, 520), (1120, 620), (1060, 560)]],                   # leaf, right, low
    5: [[(850, 350), (880, 380)], [(910, 385), (960, 380)]],                     # the stalks
    6: [[(150, 900), (300, 750), (500, 620), (700, 520), (820, 480), (880, 520)], [(400, 850), (600, 700)]],  # radish
    7: [[(950, 760), (1080, 820), (1140, 930)]],                                 # far slice
    8: [[(560, 950), (700, 900), (850, 980), (700, 1080)]],                      # near slice
}


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    rgba = load('萝卜.png')
    it = Item('萝卜.png', K, U0, V0, ink=ink_of(rgba[..., :3].copy(), rgba[..., 3] > 128, vmax=0.62, smin=0.3))
    lab = cut(it.rgb, it.zone, STROKES, it.ink)
    l1, l2, l3, l4, stalks, body, far, near = (tidy(lab == i, 8 if i == 6 else 3) for i in range(1, 9))   # no hairs
    inner = lambda m, r: m & cv2.erode(u8(m), disk(r)).astype(bool)
    leaves = l1 | l2 | l3 | l4
    veins = lines_of(it.rgb, inner(leaves, 5), dark=False, radius=5, thresh=12.0, min_area=30, min_len=20, fill=0.5)
    lines = lines_of(it.rgb, inner(body, 8), dark=True, radius=5, thresh=10.0, min_area=20, min_len=12, fill=0.6) & \
        ~it.ink
    rays = lines_of(it.rgb, inner(far | near, 10), dark=False, radius=4, thresh=5.0, min_area=25, min_len=20,
                    fill=0.5)
    it.remove |= veins | lines | rays
    common = dict(gap=50.0, fine=22.0, gb=14.0, smooth=2.0, sigma=2.5, back_gap=90.0, mark_px=9.0)
    leaf = dict(mat='RadishArtLeaf', puff=0.12, back=0.1, rim=0.3, **common)
    it.add('leaf1', l1, 0, 'lens', complete=False, marks=[(veins & l1, None)], **leaf)
    it.add('leaf3', l3, 0, 'lens', complete=False, marks=[(veins & l3, None)], **leaf)
    it.add('leaf2', l2, 1, 'lens', complete=False, marks=[(veins & l2, None)], **leaf)
    it.add('leaf4', l4, 1, 'lens', complete=False, marks=[(veins & l4, None)], **leaf)
    it.add('stalks', stalks, 2, 'lens', mat='RadishArtStalk', puff=0.3, back=0.2, **common)
    it.add('body', body, 3, 'lens', mat='RadishArtSkin', puff=0.55, back=0.6, marks=[(lines & body, None)], **common)
    it.add('far', far, 4, 'lens', mat='RadishArtFlesh', puff=0.15, back=0.15, rim=0.7, complete=True,
           marks=[(rays & far, None)], **common)
    it.add('near', near, 5, 'lens', mat='RadishArtFlesh', puff=0.15, back=0.15, rim=0.7,
           marks=[(rays & near, None)], **common)
    it.build(budget=7900, extra_tris=700)
    it.check()
    it.save('radish')
    if '--marks' in sys.argv:
        it.marks_image(sys.argv[sys.argv.index('--marks') + 1], (20, 50, 1240, 1200))
    if sheet:
        it.sheet(sheet, ('原图上的描线', '四片叶、叶柄、萝卜、两片萝卜'), crop=(20, 50, 1240, 1200))


if __name__ == '__main__':
    main()
