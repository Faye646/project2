"""Traces 姜's art (新建文件夹/姜.png) for produce.ginger (勾勒, with trace_veg.py): writes food_models/traced_ginger.json
and, with --sheet <png>, a tracing sheet.

    python WhiteModel/trace_ginger.py [--sheet <out.png>]

Three pieces cut along the art's ink lines: the hand of ginger (its knobs and fingers, the cut ends showing the yellow
flesh) and the two oval slices in front, the near one over the far one. Each is a solid, a lens facing the camera over
its outline, swelling most where it is widest, so that every knob and finger comes out round (and its lights swell
toward the eye, its creases sink); the slices thin. Their colours are the art's, vertex by vertex: the tan skin with
its olive and golden washes, the pale yellow flesh; painted crisp on faces along them, what the art draws: the brown
rings round the knobs and the lines where one knob lies over another, the white lights on the skin, the darker ring
inside each slice.
"""
import sys

import cv2

from trace_veg import Item, cut, disk, lines_of, tidy, u8

K, U0, V0 = 7000.0, 770.0, 900.0   # 70 px to the centimetre, the origin's pixel (as the ginger was built before)
STROKES = {
    1: [[(300, 650), (450, 560), (600, 470), (750, 420), (880, 330), (900, 220)], [(450, 330), (520, 420)],
        [(750, 420), (950, 400), (1100, 340), (1250, 380), (1310, 390)], [(650, 640), (720, 750), (700, 810)],
        [(250, 700), (300, 760)], [(1000, 520), (1100, 520)], [(600, 300), (480, 260)]],     # the hand
    2: [[(950, 620), (1080, 660), (1200, 720), (1280, 780)]],                                  # far slice
    3: [[(830, 760), (950, 790), (1080, 820), (1170, 860)]],                                   # near slice
}


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    it = Item('姜.png', K, U0, V0)
    lab = cut(it.rgb, it.zone, STROKES, it.ink)
    hand, far, near = (tidy(lab == i) for i in (1, 2, 3))
    inner = lambda m, r: m & cv2.erode(u8(m), disk(r)).astype(bool)
    rings = lines_of(it.rgb, inner(hand, 6), dark=True, radius=6, thresh=10.0, min_area=40, min_len=20,
                     fill=0.5) & ~it.ink
    lights = lines_of(it.rgb, inner(hand, 6), dark=False, radius=7, thresh=12.0, min_area=30, min_len=8, fill=1.0)
    slice_ring = lines_of(it.rgb, inner(far | near, 10), dark=True, radius=6, thresh=8.0, min_area=40, min_len=30,
                          fill=0.5)
    it.remove |= rings | lights | slice_ring
    common = dict(gap=44.0, fine=20.0, gb=13.0, smooth=2.0, sigma=2.5,
                  back_gap=80.0, mark_px=9.0)
    it.add('hand', hand, 0, 'lens', mat='GingerArtSkin', puff=0.6, back=0.6, relief=0.003, band=(8.0, 40.0),
           marks=[(rings & hand, None), (lights & hand, None)], **common)
    it.add('far', far, 1, 'lens', mat='GingerArtFlesh', puff=0.18, back=0.18, complete=True,
           marks=[(slice_ring & far, None)], **common)
    it.add('near', near, 2, 'lens', mat='GingerArtFlesh', puff=0.18, back=0.18, marks=[(slice_ring & near, None)],
           **common)
    it.build(budget=7900)
    it.check()
    it.save('ginger')
    if '--marks' in sys.argv:
        it.marks_image(sys.argv[sys.argv.index('--marks') + 1], (200, 90, 1340, 950))
    if sheet:
        it.sheet(sheet, ('原图上的描线', '姜块与两片姜'), crop=(200, 90, 1340, 950))


if __name__ == '__main__':
    main()
