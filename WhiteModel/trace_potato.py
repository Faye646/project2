"""Traces 土豆's art (新建文件夹/土豆.png) for produce.potato (勾勒, with trace_veg.py): writes
food_models/traced_potato.json and, with --sheet <png>, a tracing sheet.

    python WhiteModel/trace_potato.py [--sheet <out.png>]

Three pieces cut along the art's ink lines: the whole potato behind on the right, the big one on the left in front of
it and the peeled one in front of both. Each is a solid: a lens facing the camera over its outline, as thick as a
potato (the hidden parts of the two whole ones carried on under what covers them), set on the table, each in front
of the one behind. Their colours are the art's, vertex by vertex: the skin's golden tan with its brown blotches and
its pale light, the peeled one's pale yellow facets; painted crisp on faces along them, the marks the art draws: the
eyes (a dark slit with a lighter lip) and the darker specks on the skins, and the light and dark edges between the
peeled one's facets.
"""
import sys

import cv2
import numpy as np

from trace_veg import Item, cut, disk, lines_of, tidy, u8

K, U0, V0 = 6500.0, 640.0, 800.0   # 65 px to the centimetre, the origin's pixel (as the potato was built before)
# the peeled one's knife facets: a point in each (art px), read off the art with its contrast raised
FACETS = [(644, 700), (790, 640), (900, 640), (600, 775), (700, 735), (640, 850), (520, 820), (550, 960),
          (720, 1000), (780, 870), (885, 750), (980, 740), (1075, 740), (990, 865), (1070, 870), (1040, 960),
          (900, 885), (890, 1000)]
STROKES = {   # inside each piece (art px)
    1: [[(800, 330), (950, 420), (1060, 520), (1120, 640)], [(700, 330), (760, 300)]],             # back, right
    2: [[(200, 560), (380, 450), (600, 470)], [(300, 800), (450, 700), (560, 640)], [(120, 700), (140, 640)]],  # left
    3: [[(600, 850), (800, 760), (950, 900), (1060, 820)], [(700, 1000), (900, 1010)], [(520, 880)]],          # peeled
}


def facets_of(rgb, peeled):
    """The peeled one cut into its facets: a flood from a point in each over its contrast-raised shading, the edges
    between facets (where its tone steps) high ground."""
    from trace_common import flood
    from PIL import Image, ImageDraw
    lab = cv2.cvtColor(rgb, cv2.COLOR_RGB2LAB)
    cl = cv2.createCLAHE(clipLimit=6.0, tileGridSize=(8, 8)).apply(lab[..., 0]).astype(np.float32)
    cl = cv2.GaussianBlur(cl, (0, 0), 2.0)
    grad = np.abs(cv2.Sobel(cl, cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(cl, cv2.CV_32F, 0, 1))
    H, W = peeled.shape
    mk = Image.new('I', (W, H), 0)
    d = ImageDraw.Draw(mk)
    for i, (x, y) in enumerate(FACETS):
        d.ellipse((x - 6, y - 6, x + 6, y + 6), fill=i + 2)
    markers = np.asarray(mk, np.int32).copy()
    markers[~peeled] = 1
    lab_ = flood(markers, grad)
    return np.where(peeled, lab_ - 1, 0)


def faceted(facets, n_f, lam=4.0, round_px=3.0):
    """A shape function for Item.lens: the piece's swelling made flat over each facet, every facet a plane (in the
    art's pixels and the depth toward the eye, so a plane in the world too) fitted to the round swelling over it and
    meeting its neighbours' along the edges between them (least squares, the meeting weighted lam), the creases
    softened over round_px, the rim still round (no plane stands out past the round swelling there)."""
    def shape(field, region, vis):
        H, W = field.shape
        yy, xx = np.mgrid[0:H, 0:W].astype(np.float64)
        n = n_f
        A = np.zeros((3 * n, 3 * n))
        b = np.zeros(3 * n)
        f = field.astype(np.float64)
        for i in range(n):
            m = facets == i + 1
            if not m.any():
                A[3 * i:3 * i + 3, 3 * i:3 * i + 3] += np.eye(3)
                continue
            X = np.stack([xx[m] / 100, yy[m] / 100, np.ones(m.sum())], -1)
            A[3 * i:3 * i + 3, 3 * i:3 * i + 3] += X.T @ X
            b[3 * i:3 * i + 3] += X.T @ f[m]
        for dy, dx in ((0, 1), (1, 0)):   # neighbours meet along their shared edges
            a_ = facets[:H - dy, :W - dx]
            c_ = facets[dy:, dx:]
            e = (a_ > 0) & (c_ > 0) & (a_ != c_)
            ys, xs = np.nonzero(e)
            for y, x in zip(ys[::2], xs[::2]):
                i, j = a_[y, x] - 1, c_[y, x] - 1
                r = np.array([x / 100, y / 100, 1.0])
                R = lam * np.outer(r, r)
                A[3 * i:3 * i + 3, 3 * i:3 * i + 3] += R
                A[3 * j:3 * j + 3, 3 * j:3 * j + 3] += R
                A[3 * i:3 * i + 3, 3 * j:3 * j + 3] -= R
                A[3 * j:3 * j + 3, 3 * i:3 * i + 3] -= R
        coef = np.linalg.solve(A + 1e-9 * np.eye(3 * n), b).reshape(n, 3)
        planes = np.zeros((H, W))
        wsum = np.zeros((H, W))
        for i in range(n):
            w = cv2.GaussianBlur((facets == i + 1).astype(np.float32), (0, 0), round_px).astype(np.float64)
            planes += w * (coef[i, 0] * xx / 100 + coef[i, 1] * yy / 100 + coef[i, 2])
            wsum += w
        planes = np.where(wsum > 1e-3, planes / np.maximum(wsum, 1e-3), field)
        return np.where(region, np.minimum(planes, field * 1.25), 0.0)
    return shape


def main():
    sheet = sys.argv[sys.argv.index('--sheet') + 1] if '--sheet' in sys.argv else None
    it = Item('土豆.png', K, U0, V0)
    lab = cut(it.rgb, it.zone, STROKES, it.ink)
    back, left, peeled = (tidy(lab == i) for i in (1, 2, 3))
    skin = back | left
    inner = lambda m, r: m & cv2.erode(u8(m), disk(r)).astype(bool)
    # the skins' marks: eyes and specks, darker brown than round about (not the ink round the pieces)
    dark = lines_of(it.rgb, inner(skin, 7), dark=True, radius=7, thresh=22.0, min_area=12, min_len=5, fill=1.0) & \
        ~it.ink
    dark = cv2.morphologyEx(u8(dark), cv2.MORPH_OPEN, disk(1)).astype(bool)
    it.remove |= dark
    common = dict(gap=44.0, fine=20.0, gb=13.0, smooth=2.0, sigma=2.5,
                  back_gap=80.0, mark_px=8.0)
    it.add('back', back, 0, 'lens', mat='PotatoArtSkin', puff=0.55, back=0.55, complete=True, grow=1.0,
           marks=[(dark & back, None)], **common)
    it.add('left', left, 1, 'lens', mat='PotatoArtSkin', puff=0.55, back=0.55, complete=True, grow=1.0,
           marks=[(dark & left, None)], **common)
    facets = facets_of(it.rgb, peeled)
    fmasks = [facets == i + 1 for i in range(len(FACETS))]
    it.add('peeled', peeled, 2, 'lens', mat='PotatoArtFlesh', puff=0.5, back=0.5, shape=faceted(facets, len(FACETS)),
           edges=fmasks, edge_px=24.0, **common)
    if '--marks' in sys.argv:
        out = it.rgb.copy()
        out[dark] = (255, 0, 0)
        for i in range(len(FACETS)):
            e = (facets == i + 1) & ~cv2.erode(u8(facets == i + 1), disk(1)).astype(bool)
            out[e] = (0, 0, 255)
        cv2.imwrite(sys.argv[sys.argv.index('--marks') + 1], out[..., ::-1])
    it.build(budget=7900)
    it.check()
    it.save('potato')
    if sheet:
        it.sheet(sheet, ('原图上的描线', '三个土豆'), crop=(40, 190, 1220, 1100),
                 tints=[(200, 150, 80), (220, 170, 90), (250, 230, 150)])


if __name__ == '__main__':
    main()
