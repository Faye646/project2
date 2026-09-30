"""Style test B: a painterly (水彩手绘) finish for 三渲二 renders, to bring the 3D hall closer to the
painted kitchen art (背景.png / 案台.png). Screen-space only, so it can become a full-screen effect
in Unity later: the wash drifts a little against the ink, pigment granulates and pools at the edges
of each colour area, the ink softens and warms, dappled light falls across the picture, and it is
all printed on warm paper.

    python paint_filter.py <in.png> <out.png> [--bg #f3e6cc] [--strength 1.0]
RGBA input is composited over the background colour first.
"""
import sys

import numpy as np
from PIL import Image

rng = np.random.default_rng(11)


def box(a, r):
    k = 2 * r + 1
    rest = [(0, 0)] * (a.ndim - 2)
    a = np.pad(a, [(r + 1, r), (0, 0)] + rest, mode='edge').cumsum(0)
    a = (a[k:] - a[:-k]) / k
    a = np.pad(a, [(0, 0), (r + 1, r)] + rest, mode='edge').cumsum(1)
    return (a[:, k:] - a[:, :-k]) / k


def blur(a, sigma):
    r = max(1, round((np.sqrt(4 * sigma * sigma + 1) - 1) / 2))
    for _ in range(3):
        a = box(a, r)
    return a


def noise(h, w, scale, seed):
    g = np.random.default_rng(seed).random((h // scale + 2, w // scale + 2)).astype(np.float32)
    im = Image.fromarray((g * 255).astype(np.uint8)).resize((w + 2 * scale, h + 2 * scale), Image.BICUBIC)
    return np.asarray(im, dtype=np.float32)[scale:scale + h, scale:scale + w] / 255


def paint(img, bg=(243, 230, 204), strength=1.0):
    im = img.convert('RGBA')
    base = Image.new('RGBA', im.size, bg + (255,))
    base.alpha_composite(im)
    a = np.asarray(base.convert('RGB'), dtype=np.float32) / 255
    h, w, _ = a.shape
    s = strength * max(1.0, w / 1920)

    lum = a @ np.array([0.3, 0.59, 0.11], dtype=np.float32)
    ink = np.clip((0.33 - lum) / 0.12, 0, 1)                      # the dark outline pixels
    ink = np.maximum(ink, 0.0)

    # colour wash: lines painted out, then a soft, slightly wobbling wash
    wash = a.copy()
    fill = blur(a * (1 - ink[..., None]), 2.5 * s) / np.maximum(blur(1 - ink, 2.5 * s), 1e-3)[..., None]
    wash = wash * (1 - ink[..., None]) + fill * ink[..., None]
    dx = (noise(h, w, int(90 * s), 1) - 0.5) * 5 * s
    dy = (noise(h, w, int(90 * s), 2) - 0.5) * 5 * s
    yy, xx = np.mgrid[0:h, 0:w].astype(np.float32)
    xi = np.clip((xx + dx).round().astype(int), 0, w - 1)
    yi = np.clip((yy + dy).round().astype(int), 0, h - 1)
    wash = wash[yi, xi]
    wash = blur(wash, 1.2 * s)

    # pigment pools at the edge of each colour area, and granulates
    soft = blur(wash, 6 * s)
    edge = np.clip(np.abs(wash - soft).sum(-1) * 2.2, 0, 1)
    wash = wash * (1 - 0.22 * edge[..., None])
    gran = noise(h, w, max(2, int(3 * s)), 3) * 0.6 + noise(h, w, int(18 * s), 4) * 0.4
    wash = wash * (0.93 + 0.1 * gran[..., None])

    # dappled sunlight from the upper left, like the leaf shadows in the painting
    dapple = noise(h, w, int(60 * s), 5)
    dapple = np.clip((dapple - 0.45) * 3, 0, 1)
    ramp = np.clip(1.2 - (xx / w) * 0.7 - (yy / h) * 0.5, 0, 1)
    wash = wash * (1 + 0.1 * (dapple * ramp)[..., None]) + np.array([0.035, 0.02, 0.0]) * (dapple * ramp)[..., None]

    # warm the whole picture a touch, like the kitchen art
    wash = wash * np.array([1.03, 1.0, 0.94])

    # ink: softened, a little broken, warm brown
    ink_soft = np.clip(blur(ink, 0.8 * s) * 1.25, 0, 1) * (0.8 + 0.2 * noise(h, w, int(6 * s), 6))
    ink_col = np.array([0.33, 0.22, 0.15], dtype=np.float32)
    out = wash * (1 - ink_soft[..., None] * 0.9) + ink_col * ink_soft[..., None] * 0.9

    # paper grain over everything
    paper = noise(h, w, 2, 7) * 0.5 + noise(h, w, 7, 8) * 0.5
    out = out * (0.95 + 0.07 * paper[..., None])
    return Image.fromarray((np.clip(out, 0, 1) * 255).astype(np.uint8))


if __name__ == '__main__':
    args = sys.argv[1:]
    bg = (243, 230, 204)
    strength = 1.0
    if '--bg' in args:
        h_ = args[args.index('--bg') + 1].lstrip('#')
        bg = tuple(int(h_[i:i + 2], 16) for i in (0, 2, 4))
    if '--strength' in args:
        strength = float(args[args.index('--strength') + 1])
    paint(Image.open(args[0]), bg, strength).save(args[1])
    print('wrote', args[1])
