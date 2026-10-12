"""Traces 蒜's art (新建文件夹/蒜.png) for produce.garlic (勾勒, with trace_veg.py): writes food_models/traced_garlic.json
and, with --sheet <png>, a tracing sheet.

    python WhiteModel/trace_garlic.py [--sheet <out.png>]

Five pieces cut along the art's ink lines: the bulb (its cloves bulging between the creases, its dry neck on top),
the tuft of roots at its foot, the clove still in its pink skin on the right (its papery tip curling up), and the two
peeled cloves in front. Each is a solid, a lens facing the camera over its outline (the bulb's lobes swelling where
the art paints them light, sinking into its creases), set on the table in front of what is behind it. Their colours
are the art's, vertex by vertex: the bulb's white skin washed with purple-pink, the cloves' cream and their brown
root scars; painted crisp on faces along them, the lines the art draws: the purple streaks and the brown creases up
the bulb and the clove's skin, the dark lines of the roots.
"""
import sys

import cv2

from trace_veg import Item, cut, disk, lines_of, tidy, u8

K, U0, V0 = 10000.0, 640.0, 1000.0   # 100 px to the centimetre, the origin's pixel (as the garlic was built before)
STROKES = {
    1: [[(200, 650), (400, 600), (550, 500), (700, 600)], [(520, 420), (510, 300), (480, 210)], [(300, 820), (180, 520)],
        [(620, 300), (600, 220)], [(130, 700)]],                                                       # bulb
    2: [[(250, 920), (300, 935), (350, 925)]],                                                         # roots
    3: [[(870, 700), (950, 760), (1050, 760), (1150, 700)], [(1190, 640)]],                           # skin clove
    4: [[(620, 800), (550, 900), (480, 1000)], [(420, 1050)]],                                         # left peeled
    5: [[(760, 830), (850, 900), (950, 950), (1030, 1000)]],                                           # right peeled
}


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    it = Item('蒜.png', K, U0, V0)
    lab = cut(it.rgb, it.zone, STROKES, it.ink)
    bulb, roots, skin, left, right = (tidy(lab == i, 1 if i == 2 else 2) for i in range(1, 6))
    inner = lambda m, r: m & cv2.erode(u8(m), disk(r)).astype(bool)
    # the streaks and creases up the bulb and the skin clove, darker than round about
    streak = lines_of(it.rgb, inner(bulb | skin, 6), dark=True, radius=5, thresh=13.0, min_area=40, min_len=25,
                      fill=0.45) & ~it.ink
    rootline = lines_of(it.rgb, inner(roots, 1), dark=True, radius=3, thresh=18.0, min_area=8, min_len=6, fill=1.0)
    it.remove |= streak | rootline
    common = dict(gap=44.0, fine=20.0, gb=13.0, smooth=2.0, sigma=2.5,
                  back_gap=80.0, mark_px=11.0)
    it.add('bulb', bulb, 0, 'lens', mat='GarlicArtSkin', puff=0.55, back=0.6, relief=0.003, band=(8.0, 45.0), fine=23.0,
           marks=[(streak & bulb, None)], **{k: v for k, v in common.items() if k != 'fine'})
    it.add('roots', roots, 1, 'lens', mat='GarlicArtRoot', puff=0.3, back=0.3, complete=False,
           **{**common, 'fine': 12.0, 'gb': 9.0, 'mark_px': 6.0}, marks=[(rootline & roots, None)])
    it.add('skin', skin, 1, 'lens', mat='GarlicArtPeel', puff=0.5, back=0.5, complete=True, relief=0.0015,
           marks=[(streak & skin, None)], **common)
    it.add('right', right, 2, 'lens', mat='GarlicArtClove', puff=0.55, back=0.5, complete=True, **common)
    it.add('left', left, 3, 'lens', mat='GarlicArtClove', puff=0.55, back=0.5, **common)
    it.build(budget=7900)
    it.check()
    it.save('garlic')
    if sheet:
        it.sheet(sheet, ('原图上的描线', '蒜头、根须、带皮的蒜瓣、两瓣剥好的蒜'), crop=(40, 140, 1230, 1110))


if __name__ == '__main__':
    main()
