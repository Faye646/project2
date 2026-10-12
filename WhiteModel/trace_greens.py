"""Traces 时蔬's art (新建文件夹/时蔬.png) for produce.greens (勾勒, with trace_veg.py): writes food_models/traced_greens.json
and, with --sheet <png>, a tracing sheet.

    python WhiteModel/trace_greens.py [--sheet <out.png>]

The head of leafy greens lying on its side: the whole head (its darker outer leaves showing all round) a solid, a lens
facing the camera over the art's outline, swelling up from its edges like a pillow; over it the four light front
leaves (LEAVES: their outlines traced off the art, as greens was laid out before), each a shell lying on what is under
it, its margins resting on it, its crinkles the art's shading in relief. Their colours are the art's, vertex by
vertex: the dark and light greens of the crinkled leaves, the pale stalks running up into their midribs, the cut ends
of the stalks; painted crisp on faces along them, what the art draws: the pale veins branching off the midribs and the
dark green where one leaf's margin lies over another.
"""
import sys

import cv2
import numpy as np
from PIL import Image, ImageDraw

from trace_veg import Item, disk, lines_of, u8

K, U0, V0 = 4000.0, 770.0, 950.0   # 40 px to the centimetre, the origin's pixel (as the greens were built before)
LEAVES = [   # the front leaves, back to front: name, level, outline (art px)
    ('F2', 1, [
        (465, 136), (447, 178), (447, 211), (455, 224), (476, 228), (469, 254), (490, 290), (485, 298), (467, 308),
        (462, 345), (434, 359), (433, 398), (443, 403), (470, 397), (479, 405), (486, 424), (515, 423), (541, 443),
        (542, 453), (529, 466), (524, 486), (528, 513), (510, 524), (511, 532), (547, 546), (601, 546), (617, 542),
        (638, 520), (690, 543), (746, 542), (770, 518), (788, 528), (811, 530), (824, 540), (834, 561), (846, 575),
        (880, 578), (890, 584), (894, 652), (914, 663), (918, 691), (923, 700), (966, 731), (1005, 746), (1056, 746),
        (1067, 741), (1080, 744), (1122, 784), (1142, 795), (1166, 799), (1200, 828), (1234, 856), (1267, 856),
        (1271, 836), (1301, 822), (1306, 812), (1323, 805), (1324, 786), (1302, 751), (1268, 708), (1233, 665),
        (1191, 628), (1152, 600), (1113, 572), (1075, 544), (1072, 494), (1060, 478), (1044, 474), (1035, 467),
        (1028, 450), (1027, 426), (1012, 412), (1004, 385), (965, 382), (926, 380), (907, 364), (904, 310),
        (888, 292), (883, 274), (836, 269), (844, 292), (838, 299), (829, 300), (813, 286), (785, 285), (771, 276),
        (768, 229), (753, 204), (726, 203), (698, 226), (692, 226), (670, 204), (663, 189), (656, 160), (658, 118),
        (632, 112), (606, 93), (584, 96), (564, 121), (526, 147), (508, 146), (478, 131)]),
    ('F3', 2, [
        (881, 181), (849, 208), (845, 235), (836, 249), (837, 278), (863, 301), (866, 319), (881, 336), (875, 365),
        (880, 386), (899, 402), (920, 406), (935, 420), (949, 419), (969, 404), (983, 405), (989, 425), (1008, 435),
        (1004, 473), (1012, 493), (1034, 502), (1048, 520), (1039, 545), (1042, 565), (1066, 579), (1077, 578),
        (1084, 570), (1091, 573), (1109, 592), (1130, 629), (1173, 666), (1215, 704), (1229, 704), (1235, 692),
        (1241, 693), (1247, 705), (1243, 721), (1252, 724), (1254, 668), (1248, 647), (1226, 600), (1205, 554),
        (1183, 507), (1158, 468), (1133, 429), (1129, 375), (1113, 356), (1108, 344), (1093, 341), (1086, 333),
        (1083, 312), (1071, 298), (1068, 249), (1052, 238), (1043, 243), (1036, 257), (1005, 264), (989, 257),
        (965, 255), (961, 249), (965, 215), (960, 204), (926, 201), (901, 179)]),
    ('F4', 3, [
        (1056, 224), (1039, 251), (1046, 286), (1043, 323), (1060, 338), (1063, 361), (1071, 368), (1074, 378),
        (1105, 403), (1103, 436), (1107, 451), (1137, 499), (1168, 547), (1188, 601), (1217, 650), (1245, 699),
        (1244, 733), (1269, 769), (1294, 806), (1318, 809), (1345, 775), (1344, 745), (1325, 701), (1305, 658),
        (1286, 614), (1258, 587), (1257, 568), (1271, 560), (1270, 531), (1293, 513), (1294, 497), (1287, 483),
        (1274, 473), (1258, 469), (1239, 475), (1227, 462), (1233, 451), (1261, 434), (1264, 422), (1241, 385),
        (1199, 377), (1215, 347), (1213, 312), (1200, 297), (1181, 304), (1151, 298), (1148, 285), (1157, 262),
        (1149, 244), (1135, 238), (1109, 241), (1075, 224)]),
    ('F1', 4, [
        (358, 501), (355, 518), (358, 542), (335, 573), (335, 593), (340, 600), (359, 604), (371, 620), (384, 620),
        (404, 610), (415, 617), (424, 649), (440, 672), (438, 684), (425, 700), (423, 713), (433, 750), (441, 758),
        (457, 759), (470, 751), (481, 757), (503, 756), (530, 775), (547, 777), (572, 760), (594, 759), (611, 751),
        (618, 767), (635, 786), (654, 789), (668, 800), (685, 803), (707, 791), (731, 751), (745, 749), (783, 763),
        (820, 777), (825, 798), (845, 821), (849, 844), (891, 839), (933, 834), (942, 828), (951, 828), (964, 839),
        (1001, 853), (1052, 885), (1104, 916), (1143, 931), (1179, 938), (1219, 937), (1223, 916), (1235, 894),
        (1268, 860), (1267, 846), (1243, 817), (1195, 783), (1162, 768), (1129, 753), (1071, 734), (1013, 714),
        (955, 682), (934, 678), (931, 670), (939, 658), (940, 641), (918, 626), (926, 590), (925, 575), (918, 561),
        (905, 552), (872, 553), (857, 534), (846, 511), (812, 503), (784, 479), (753, 478), (730, 511), (714, 519),
        (674, 503), (655, 476), (633, 475), (614, 488), (586, 526), (569, 533), (549, 518), (520, 518), (498, 532),
        (489, 533), (467, 510), (425, 508), (397, 470), (376, 475)]),
]


def poly(pts, H, W):
    im = Image.new('L', (W, H), 0)
    ImageDraw.Draw(im).polygon([tuple(q) for q in pts], fill=1)
    return np.asarray(im).astype(bool)


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    it = Item('时蔬.png', K, U0, V0)
    H, W = it.H, it.W
    masks = [poly(pts, H, W) & it.zone for _, _, pts in LEAVES]
    vis = []
    for i, m in enumerate(masks):   # what of each shows: not under the leaves in front of it
        v = m.copy()
        for m2 in masks[i + 1:]:
            v &= ~m2
        vis.append(cv2.morphologyEx(u8(v), cv2.MORPH_OPEN, disk(3)).astype(bool))
    head = it.zone & ~np.any(vis, 0)
    inner = lambda m, r: m & cv2.erode(u8(m), disk(r)).astype(bool)
    veins = lines_of(it.rgb, inner(it.zone, 6), dark=False, radius=5, thresh=11.0, min_area=30, min_len=24, fill=0.5)
    crinkle = lines_of(it.rgb, inner(it.zone, 8), dark=True, radius=7, thresh=16.0, min_area=60, min_len=30,
                       fill=0.6) & ~it.ink   # the dark green where a margin's crinkles fold over
    it.remove |= veins | crinkle
    common = dict(gap=52.0, fine=24.0, gb=13.0, smooth=1.5, sigma=2.5, back_gap=100.0, mark_px=10.0)
    it.add('head', head, 0, 'lens', full=it.zone.copy(), mat='GreensArtLeaf', puff=0.35, back=0.25, rim=0.4, relief=0.003, band=(6.0, 40.0),
           marks=[(veins & head, None), (crinkle & head, None)], one_ring=True, **common)
    for (name, level, _), m in zip(LEAVES, vis):
        it.add(name, m, level, 'shell', on='head', mat='GreensArtLeaf', off=0.0015, top=0.0015, round_px=14.0,
               relief=0.002, band=(6.0, 40.0), marks=[(veins & m, None), (crinkle & m, None)], inner_ink=False,
               one_ring=True, ink_on='paper', **common)
    it.build(budget=7900)
    it.check()
    it.save('greens')
    if sheet:
        it.sheet(sheet, ('原图上的描线', '菜头与四片前叶'), crop=(190, 40, 1360, 970))


if __name__ == '__main__':
    main()
