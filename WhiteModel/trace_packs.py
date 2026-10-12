"""What the traces of the packed ingredients share (trace_pancake.py, trace_sauerkraut.py, trace_seafood.py,
trace_pickle_base.py, trace_rice_prep.py), on top of trace_common: the art loaded, its colours as a map the model is
tinted from (the art's own colours, its broad light and shade taken out, for the shader puts its own back), each
piece's surface closed so that it can be seen from all round, and the traced data written for
sacks.traced_pack (food_models/traced_<id>.json and its _paint.npz: the paint channels and the colour map).
"""
import json
import os

import cv2
import numpy as np
from PIL import Image

from trace_common import (Camera, contour_points, disk, fill_holes, largest, neighbours, oriented, outline_mesh,
                          profile, raster, shading_band, smooth_inner, u8)

HERE = os.path.dirname(os.path.abspath(__file__))
ART_DIR = os.path.join(HERE, '..', '新建文件夹')


class Art:
    """The art: rgba, rgb, its alpha mask, hue (degrees), saturation and value (0-1) and luminance (0-255)."""

    def __init__(self, name):
        self.rgba = np.asarray(Image.open(os.path.join(ART_DIR, name)).convert('RGBA'))
        self.rgb = np.ascontiguousarray(self.rgba[..., :3])
        self.alpha = self.rgba[..., 3] > 128
        hsv = cv2.cvtColor(self.rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
        self.h, self.s, self.v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
        self.lum = self.rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
        self.H, self.W = self.alpha.shape
        self.yy, self.xx = np.mgrid[0:self.H, 0:self.W]


def colour_map(art, regions, flatten=0.75, sigma=40.0, fine=1.2, ink=None):
    """The art's colours within each region (a list of masks), its broad light and shade taken out (by `flatten`:
    each pixel's luminance, blurred over `sigma`, brought that far towards its region's lit level, the 70th
    percentile, for the shader puts the shade back), softened by `fine`;
    the art's ink lines (value under ink, if given) filled from round about first, so that a vertex near one is not
    tinted dark (the ink is drawn on its own). uint8 H×W×3."""
    rgb = art.rgb.astype(np.float32)
    if ink is not None:
        line = (art.v < ink) & art.alpha
        rgb = cv2.inpaint(art.rgb, u8(cv2.dilate(u8(line), disk(1))), 5, cv2.INPAINT_TELEA).astype(np.float32)
    lum = rgb @ np.array([0.3, 0.59, 0.11], np.float32)
    out = np.zeros_like(rgb)
    for m in regions:
        mf = m.astype(np.float32)
        big = cv2.GaussianBlur(lum * mf, (0, 0), sigma) / np.maximum(cv2.GaussianBlur(mf, (0, 0), sigma), 1e-3)
        mean = float(np.percentile(lum[m], 70)) if m.any() else 128.0   # its lit level: the shader shades it
        gain = ((mean + (big - mean) * (1 - flatten)) / np.maximum(big, 1.0))[..., None]
        c = np.clip(rgb * gain, 0, 255)
        cb = cv2.GaussianBlur(c * mf[..., None], (0, 0), fine) / np.maximum(cv2.GaussianBlur(mf, (0, 0), fine), 1e-3)[..., None]
        grow = cv2.dilate(u8(m), disk(6)).astype(bool)   # a little past the region: vertices on its edge
        out[grow & ~(out.sum(-1) > 0)] = cb[grow & ~(out.sum(-1) > 0)]
    return np.clip(out + 0.5, 0, 255).astype(np.uint8)


def mean_colour(art, m, lo=10, hi=90):
    """The art's middle colour over the mask (its pixels between the lo and hi luminance percentiles) as hex."""
    l = art.lum[m]
    if not len(l):
        return '(none)'
    a, b = np.percentile(l, lo), np.percentile(l, hi)
    c = art.rgb[m][(l >= a) & (l <= b)].mean(0)
    return '#%02x%02x%02x' % tuple(int(round(x)) for x in c)


def shade_hex(hexc, f=0.82, warm=(1.0, 0.95, 0.9)):
    c = [int(hexc[i:i + 2], 16) for i in (1, 3, 5)]
    return '#%02x%02x%02x' % tuple(int(min(255, x * f * w)) for x, w in zip(c, warm))


def zbuffer(cam, V, T, H, W, ids=None, zb=None, idb=None):
    """Depths (along the view) of the triangles (V, T) as the art's camera sees them, and which one is in front."""
    u, v = cam.project(V[:, 0], V[:, 1], V[:, 2])
    if zb is None:
        zb, idb = np.full((H, W), np.inf), np.full((H, W), -1, np.int32)
    raster(np.stack([u, v], -1)[T], cam.depth(V)[T], np.zeros(len(T), np.int32) if ids is None else ids, H, W, zb,
           idb)
    return zb, idb


def piece_mesh(cam, mask, gap, gb, ring=0.0006, smooth_px=3.0, extra=None, margin=None):
    """outline_mesh over the piece's mask (its largest part, holes filled, edge softened)."""
    mk = fill_holes(largest(cv2.morphologyEx(u8(mask), cv2.MORPH_OPEN, disk(1))))
    mk = cv2.GaussianBlur(mk.astype(np.float32), (0, 0), 1.2) > 0.5
    return (mk,) + outline_mesh(cam, mk, gap, gb, ring, smooth_px=smooth_px, extra=extra, extra_margin=margin)


def closed_over(cam, uv, tris, nb, L, s_base, back=0.0008):
    """A piece over a surface (s_base: its depth along the view at each point), closed: its front L towards the
    camera, its back `back` in front of the surface, the two meeting at its outline (where L is least), so that from
    any side it is a thin closed shell."""
    s_base = np.asarray(s_base, float)
    P = cam.on_ray(uv[:, 0], uv[:, 1], s_base - L)
    Lb = np.minimum(L, back)
    Q = cam.on_ray(uv[nb:, 0], uv[nb:, 1], s_base[nb:] - Lb[nb:])
    P2 = np.r_[P, Q]
    T = oriented(P, tris, cam.toward, True)
    m = lambda i: i if i < nb else i + len(P) - nb
    T2 = oriented(P2, [(m(a), m(b), m(c)) for a, b, c in tris], cam.toward, False)
    return P2, T + T2


def depth_at(zb, uv, fallback, r=2):
    """The depth of what is in the z-buffer at each point (the least over a small window), else fallback."""
    H, W = zb.shape
    zz = cv2.erode(np.where(np.isfinite(zb), zb, 1e3).astype(np.float32), disk(r)) if r else zb
    iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
    ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
    s = zz[iy, ix].astype(float)
    return np.where(s < 1e2, s, fallback)


def piece_record(name, kind, mat, nb, P, T, paint=(), ink=(0.5, 2.5), tint=0.8, extra=None):
    return {'name': name, 'kind': kind, 'mat': mat, 'rim': int(nb), 'paint': [list(x) for x in paint],
            'ink': list(ink), 'tint': tint, **(extra or {}),
            'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]}


def write(key, cam, pieces, paint, colour, channels, extra=None):
    out = os.path.join(HERE, 'food_models', f'traced_{key}.json')
    npz = os.path.join(HERE, 'food_models', f'traced_{key}_paint.npz')
    np.savez_compressed(npz, paint=paint[::2, ::2], colour=colour[::2, ::2])
    data = {'camera': {'el': cam.el, 'k': cam.k, 'u0': cam.u0, 'v0': cam.v0}, 'paint_scale': 0.5,
            'channels': channels, 'pieces': pieces, **(extra or {})}
    json.dump(data, open(out, 'w'), separators=(',', ':'))
    n = sum(len(p['tris']) for p in pieces)
    print(f'[trace] {key}: {len(pieces)} pieces, {n} triangles -> {os.path.basename(out)}', flush=True)


def sheet(path, art, labels, names, title, crop=None):
    """The tracing sheet: the art with each piece's outline in blue | the pieces as a colouring page."""
    from trace_common import tracing_sheet
    rng = np.random.default_rng(3)
    tints = [tuple(int(x) for x in rng.integers(120, 250, 3)) for _ in names]
    tracing_sheet(path, art.rgba, labels, names, tints, crop=crop, title=title)
