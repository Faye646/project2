"""Shared by trace_d07.py, trace_d08.py, trace_d13.py and trace_d15.py (the stir-fries and the stew): a heaped dish's
art cut into its many small pieces and each one raised over its traced outline (勾勒), on top of trace_common.

The pieces are found from seeds (each a patch of one colour class, read off the art automatically, with strokes by
eye where the art's colours don't part them), flooded out over the art to its ink lines and creases (a watershed):
every piece's outline follows the line the art draws round it. Under them all lies the dish's food as one heap (the
sauce, the gravy), raised from the dish over the whole of the food, so that what shows between the pieces is the
art's sauce and every piece rests on something; each piece is a rounded mound over its outline on that heap (lying
on it, its outline sitting on it, its middle raised), so that from the art's camera it covers exactly what the art
paints, with the art's shading in relief.
"""
import json
import math

import cv2
import numpy as np
from PIL import Image, ImageDraw

from trace_common import (Grid, contour_points, dish_mesh, disk, fill_holes, flood, largest, lying, neighbours,
                          outline_mesh, profile, raster, shading_band, smooth_inner, u8)


def load_art(path):
    """The art: rgba, rgb, hue (degrees), saturation, value (0-1) and luminance (0-255)."""
    rgba = np.asarray(Image.open(path).convert('RGBA'))
    rgb = np.ascontiguousarray(rgba[..., :3])
    hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL).astype(np.float32)
    h, s, v = hsv[..., 0] * 360 / 256, hsv[..., 1] / 255, hsv[..., 2] / 255
    lum = rgb.astype(np.float32) @ np.array([0.3, 0.59, 0.11], np.float32)
    return rgba, rgb, h, s, v, lum


def dish_view(cam, build, H, W):
    """The dish as the art's camera sees it (built by Blender from `build`): the height of its inside under any
    (x, y) (a Grid), its depths per art pixel, and its vertices and triangles."""
    V, T = dish_mesh(build)
    zb = np.full((H, W), np.inf)
    u, v = cam.project(V[:, 0], V[:, 1], V[:, 2])
    raster(np.stack([u, v], -1)[T], cam.depth(V)[T], np.zeros(len(T), np.int32), H, W, zb,
           np.full((H, W), -1, np.int32))
    return Grid.top_of(V, T), zb, V, T


def patches(mask, erode, amin, open_r=1):
    """The separate patches of a mask, each shrunk by `erode` first (so that thin bridges part), those at least
    amin pixels: a list of masks."""
    m = cv2.morphologyEx(u8(mask), cv2.MORPH_OPEN, disk(open_r)) if open_r else u8(mask)
    if erode:
        m = cv2.erode(m, disk(erode))
    n, cc, st, _ = cv2.connectedComponentsWithStats(m)
    return [cc == i for i in range(1, n) if st[i, cv2.CC_STAT_AREA] >= amin]


def gradient(rgb, sig=1.0):
    """The change of colour (Lab), for the watershed's ground."""
    lab = cv2.cvtColor(cv2.GaussianBlur(rgb, (0, 0), sig), cv2.COLOR_RGB2LAB).astype(np.float32)
    return sum(np.abs(cv2.Sobel(lab[..., c], cv2.CV_32F, 1, 0)) + np.abs(cv2.Sobel(lab[..., c], cv2.CV_32F, 0, 1))
               for c in range(3))


def strokes_canvas(strokes, H, W, width=7):
    """{id: [points] or [[points], [points]]} drawn as an id map (0 elsewhere)."""
    canvas = Image.new('I', (W, H), 0)
    d = ImageDraw.Draw(canvas)
    for k, lines in strokes.items():
        for line in (lines if isinstance(lines[0][0], (list, tuple)) else [lines]):
            line = [tuple(q) for q in line]
            if len(line) > 1:
                d.line(line, fill=k, width=width)
            for x, y in line:
                d.ellipse((x - width // 2 - 1, y - width // 2 - 1, x + width // 2 + 1, y + width // 2 + 1), fill=k)
    return np.asarray(canvas, np.int32)


def watershed(zone, seeds, elev):
    """A flood of the zone from the seeds (an id map, 0 unseeded), lowest ground first; outside the zone 0."""
    mk = np.where(zone, seeds, -1).astype(np.int32)
    lab = flood(mk, elev)
    return np.where(zone & (lab > 0), lab, 0)


def tidy(labels, amin=0, open_r=2, holes=True):
    """Each piece one clean region: its largest part after a little opening, its holes filled (what the art draws
    inside it, seeds or a glint, is its own), what is cut off given to nobody (0)."""
    out = np.zeros_like(labels)
    for pid in range(1, labels.max() + 1):
        m = labels == pid
        if m.sum() < max(amin, 1):
            continue
        k = largest(cv2.morphologyEx(u8(m), cv2.MORPH_OPEN, disk(open_r)) if open_r else m)
        if holes:
            k = fill_holes(k)
        out[k & ((out == 0) | (labels == pid))] = pid
    return out


def heap_height(cam, food, top, reach, H, W, base=None, sauce=None):
    """How high the heap of food stands at each art pixel (m): rising from the edge of the food (food: a mask) to
    `top` `reach` metres in (a round shoulder), as a heap of pieces is piled; over the sauce round it (sauce: a mask)
    only a film. base adds a floor of height (m) everywhere in the food."""
    se, K = cam.se, cam.k
    hs = int(round(H / se))
    m = cv2.resize(u8(food), (W, hs), interpolation=cv2.INTER_NEAREST)
    d = cv2.distanceTransform(m, cv2.DIST_L2, 5) / K       # in from its edge, metres, as on level ground
    t = np.clip(d / reach, 0, 1)
    hgt = top * np.sqrt(np.clip(1 - (1 - t) ** 2, 0, 1))
    hgt = cv2.GaussianBlur(hgt.astype(np.float32), (0, 0), 0.25 * reach * K)
    hgt = cv2.resize(hgt, (W, H), interpolation=cv2.INTER_LINEAR)
    if base is not None:
        hgt = np.where(food, hgt + base, hgt)
    return hgt


def sample(img, uv):
    H, W = img.shape[:2]
    iy = np.clip(np.round(uv[:, 1]).astype(int), 0, H - 1)
    ix = np.clip(np.round(uv[:, 0]).astype(int), 0, W - 1)
    return img[iy, ix]


def mound(cam, name, kind, kp, mk, floor, hmap, lum, paint, channels, ring=0.0005, close=None, extra_px=None,
          band_px=(3.0, 14.0), ink=(0.5, 2.5), smooth_px=2.0, mat=None, extra=None, tone=None, colours=None,
          raised=None, backed=False, down=False):
    """One piece: a rounded mound over its outline (mk, art pixels) lying on the heap (hmap: the heap's height per
    art pixel over the dish's floor), its middle raised `puff` × its half-width up to `top`, its outline `edge` over
    the heap, the art's shading as relief; colours from kp ('paint': [(channel, key)], 'tint': [(channel, hex, w)]),
    the mesh with vertices along each painted colour's edge. Given close (a height function), closed underneath
    down to it (lying's skirt and floor)."""
    H, W = mk.shape
    edges = [(paint[..., channels.index(c)] > 127) & mk for c, _ in kp.get('paint', [])]
    pts = contour_points(edges, extra_px) if (edges and extra_px) else None
    tint_px = kp.get('tint_px')
    if tint_px:   # the soft colours' edges too, coarser
        tp = contour_points([(paint[..., channels.index(c)] > 127) & mk for c, _, _ in kp.get('tint', [])], tint_px)
        pts = tp if pts is None else np.r_[pts, tp]
    if extra is not None:
        pts = extra if pts is None else np.r_[pts, extra]
    ring = kp.get('ring', ring)
    uv, tris, nb, d, R, lean = outline_mesh(cam, mk, kp['gap'], kp['gb'], ring, smooth_px=smooth_px, extra=pts,
                                            extra_margin=kp.get('margin'))
    band = shading_band(lum, mk, *band_px)
    top = float(np.clip(kp['puff'] * R, kp.get('min_top', 0.0008), kp['top']))
    L = profile(d, R, top, kp.get('edge', 0.0), kp.get('tilt', 0.0), lean, kp.get('relief', 0.0), sample(band, uv))
    L = smooth_inner(L, nb, neighbours(len(uv), tris))
    lift = sample(hmap, uv) + L
    if close is not None and down:   # closed underneath by a skirt straight down from its outline and a floor
        P, T = lying(cam, uv, tris, nb, lift, floor)   # (lying's runs along the lines of sight: from a heap raised
        P, T = close_down(P, list(T), nb, close)       # over the back rim, it would show)
    else:
        P, T = lying(cam, uv, tris, nb, lift, floor, close=close)
    hm = sample(hmap, uv)
    size = max(np.ptp(uv[:, 0]), np.ptp(uv[:, 1])) / cam.k
    steep = np.ptp(hm) > 0.6 * size   # the heap under it rises as steeply as it is wide: it stands up
    if close is None and raised is not None and (float(sample(raised, uv).max()) > 0.002 or steep):
        # standing up over the back rim (rim_guard): a rounded lens square to the eye through the middle of where it
        # would lie, closed behind by a cone (as 松鼠鳜鱼's crisp pieces), so that from behind it shows no open back
        from trace_common import standing
        anchor = P[nb:].mean(0) if len(P) > nb else P.mean(0)
        P, T = standing(cam, uv, tris, nb, L, 0.4 * L, anchor, cone=True)
    elif backed and close is None and len(uv) > nb:
        # seen from the side or from behind, its steep slopes face away: closed underneath by a coarse back over the
        # same outline, a little under its front (as 松鼠鳜鱼's head)
        dirs = [np.array([math.sin(math.radians(a)) * math.cos(math.radians(e)),
                          -math.cos(math.radians(a)) * math.cos(math.radians(e)), math.sin(math.radians(e))])
                for a, e in ((20, 60), (-40, 25), (160, 30), (40, 25))]
        F = np.array([t for t in T if max(t) < len(uv)])
        nrm = np.cross(P[F[:, 1]] - P[F[:, 0]], P[F[:, 2]] - P[F[:, 0]])
        if any((nrm @ dvec < -1e-9).any() for dvec in dirs):
            from trace_common import oriented
            ub, tb, nbb, db, Rb, _ = outline_mesh(cam, mk, max(3 * kp['gap'], 0.012), kp['gb'], 0.0,
                                                  smooth_px=smooth_px)
            if nbb == nb and np.allclose(ub[:nb], uv[:nb], atol=1e-3):
                Lb = profile(db, Rb, 0.3 * top, kp.get('edge', 0.0))
                Pb, _ = lying(cam, ub, tb, nbb, sample(hmap, ub) + Lb, floor)
                k0 = len(P)
                P = np.r_[P, Pb[nb:]]
                mp = lambda i: i if i < nb else k0 + i - nb
                T = list(T) + oriented(P, [(mp(a), mp(b), mp(c)) for a, b, c in tb], cam.toward, False)
    out = {'name': name, 'kind': kind, 'mat': mat or kp['mat'], 'rim': nb,
           'paint': [(channels.index(c), m) for c, m in kp.get('paint', [])],
           'tint': [(channels.index(c), col, w) for c, col, w in kp.get('tint', [])],
           'ink': list(kp.get('ink', ink)),
           'verts': np.round(P, 6).tolist(), 'tris': [list(map(int, t)) for t in T]}
    if close is not None:
        out['closed'] = len(uv)
    if tone is not None:   # the art's light and shade at each of its front points, -1..1, for its shading normals,
        t = sample(tone, uv).astype(np.float64)   # evened out over the mesh a little, so that its light steps
        nbr = neighbours(len(uv), tris)            # don't follow the triangles
        for _ in range(2):
            t = 0.5 * t + 0.5 * np.array([np.mean(t[list(j)]) if j else t[i] for i, j in enumerate(nbr)])
        out['tone'] = np.round(t, 2).tolist()
    if colours is not None:   # the art's colour at each of its front points, to be painted on as it is
        out['rgb'] = sample(colours, uv).astype(int).tolist()
    return out, uv, R, top


def close_down(P, T, nb, close):
    """A lying surface (its first nb points its outline) closed underneath: a skirt from its outline straight down
    to the surface z = close(x, y) (+0.5 mm), facing out, and the outline filled flat there, facing down."""
    from trace_common import ear_clip
    k0 = len(P)
    xy = P[:nb, :2]
    feet = np.c_[xy, close(xy[:, 0], xy[:, 1]) + 0.0005]
    feet[:, 2] = np.minimum(feet[:, 2], P[:nb, 2])
    P2 = np.r_[P, feet]
    ccw = np.sum(xy[:, 0] * np.roll(xy[:, 1], -1) - np.roll(xy[:, 0], -1) * xy[:, 1]) > 0
    for i in range(nb):
        j = (i + 1) % nb
        e = xy[j] - xy[i]
        outside = np.array([e[1], -e[0]]) if ccw else np.array([-e[1], e[0]])
        for t in ((i, j, k0 + j), (i, k0 + j, k0 + i)):
            n = np.cross(P2[t[1]] - P2[t[0]], P2[t[2]] - P2[t[0]])
            T.append(t if n[:2] @ outside >= 0 else (t[0], t[2], t[1]))
    for a, b, c in ear_clip(xy):
        t = (k0 + a, k0 + b, k0 + c)
        n = np.cross(P2[t[1]] - P2[t[0]], P2[t[2]] - P2[t[0]])
        T.append(t if n[2] <= 0 else (t[0], t[2], t[1]))
    return P2, T


def channels_from(masks, food, smooth, min_area, close):
    """paint_channels, one call per group, as uint8 H×W×C."""
    from trace_common import paint_channels
    return paint_channels(masks, food, smooth=smooth, min_area=min_area, close=close)


def local_tone(lum, mask, sig=10.0, delta=14.0):
    """Where the art is lighter or darker than round about within the mask (its light and its shade)."""
    m = mask.astype(np.float32)
    local = cv2.GaussianBlur(lum * m, (0, 0), sig) / np.maximum(cv2.GaussianBlur(m, (0, 0), sig), 1e-3)
    return mask & (lum > local + delta), mask & (lum < local - delta)


def tone_map(lum, labels, kinds, scale=None, sig=3.0, ramp=None, pcts=(20, 85)):
    """The art's light and shade over each piece, -1 .. 1: its luminance (a little blurred) against the middle of
    its kind's, a full step down at the kind's pcts[0] percentile and up at its pcts[1] (as kind_colours reads its
    dark and light colours, so that the colours fitted to those come out where the art has them; `scale` is
    unused, kept for old callers); ramp[kind] = (top, bottom) leans each piece of that kind lighter at its top and
    darker low down, as the art lights them."""
    H, W = labels.shape
    out = np.zeros((H, W), np.float32)
    lb = cv2.GaussianBlur(lum, (0, 0), sig)
    yy = np.mgrid[0:H, 0:W][0]
    kind_of = np.array(['none'] + list(kinds))[labels]
    for k in set(kinds):
        m = kind_of == k
        if m.sum() < 50:
            continue
        lo, mid, hi = np.percentile(lb[m], [pcts[0], 50, pcts[1]])
        x = lb[m]
        out[m] = np.clip(np.where(x > mid, (x - mid) / max(hi - mid, 1.0), (x - mid) / max(mid - lo, 1.0)), -1, 1)
    if ramp:
        for pid in range(1, labels.max() + 1):
            k = kinds[pid - 1]
            if k not in ramp:
                continue
            m = labels == pid
            if not m.any():
                continue
            ys = yy[m]
            t = (ys - ys.min()) / max(ys.max() - ys.min(), 1)
            top, bottom = ramp[k]
            out[m] = np.clip(out[m] + top * (1 - t) + bottom * t, -1, 1)
    return out


def write(out_json, out_paint, cam, channels, pieces, paint, extra=None):
    np.savez_compressed(out_paint, paint=paint[::2, ::2])
    data = {'camera': {'el': cam.el, 'k': cam.k, 'u0': cam.u0, 'v0': cam.v0}, 'paint_scale': 0.5,
            'channels': channels, 'pieces': pieces, 'bits': []}
    if extra:
        data.update(extra)
    json.dump(data, open(out_json, 'w'), separators=(',', ':'))


def label_sheet(path, rgb, labels, kinds, tints, crop, scale=1.0):
    """The art dimmed with each piece's outline and number, for checking the cut by eye."""
    vis = (rgb.astype(np.float32) * 0.55 + 255 * 0.45).astype(np.uint8)
    for pid in range(1, labels.max() + 1):
        m = labels == pid
        if not m.any():
            continue
        col = tints.get(kinds[pid - 1], (200, 0, 200))
        vis[m] = (vis[m] * 0.5 + np.array(col) * 0.5).astype(np.uint8)
        c, _ = cv2.findContours(u8(m), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
        cv2.drawContours(vis, c, -1, (20, 20, 120), 2)
    x0, y0, x1, y1 = crop
    im = Image.fromarray(vis[y0:y1, x0:x1])
    d = ImageDraw.Draw(im)
    from PIL import ImageFont
    f = ImageFont.truetype('C:/Windows/Fonts/arialbd.ttf', 15)
    for pid in range(1, labels.max() + 1):
        ys, xs = np.nonzero(labels == pid)
        if len(xs):
            dt = cv2.distanceTransform(u8(labels == pid), cv2.DIST_L2, 3)
            j = np.argmax(dt[ys, xs])
            d.text((xs[j] - x0 - 8, ys[j] - y0 - 8), str(pid), fill=(0, 0, 0), font=f)
    if scale != 1.0:
        im = im.resize((round(im.width * scale), round(im.height * scale)), Image.LANCZOS)
    im.save(path)


def food_zone(h, s, v, alpha, erode=40, celadon=((0.3, 50, 220),), over_rim=None):
    """The food and its sauce: what in the dish's inside is not celadon (low saturation, green to blue) nor the
    white of its glaze; over_rim (a mask) adds what of the food reaches out over the dish's rim."""
    inside = cv2.erode(u8(alpha > 128), disk(erode)).astype(bool)
    if over_rim is not None:
        inside |= over_rim & (alpha > 128)
    pale = np.zeros_like(inside)
    for smax, h0, h1 in celadon:
        pale |= (s < smax) & (h > h0) & (h < h1)
    m = inside & ~pale & ~((s < 0.12) & (v > 0.9))
    m = cv2.morphologyEx(u8(m), cv2.MORPH_CLOSE, disk(4))
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, disk(6))
    return fill_holes(largest(m))


def cut(rgb, s, v, zone, seeds, fix=(), join=(), ink=(0.45, 0.35), wall=300.0, absorb=2500):
    """The pieces: a flood of the zone from the seeds ([(mask, kind)], each patch one piece) and the strokes by eye
    (fix: [(kind, [art pixels])]), lowest change of colour first, the art's thin dark ink lines walls; then the
    pieces in each `join` entry ((kind, [art pixels in each])) joined into one, each piece one clean region, and a
    small bit wholly inside one piece (a drop of sauce on it) given to it. Returns the piece numbers per pixel and
    each piece's kind."""
    H, W = zone.shape
    kinds = []
    mk = np.zeros((H, W), np.int32)
    for m, kind in seeds:
        kinds.append(kind)
        mk[m & (mk == 0)] = len(kinds)
    for kind, line in fix:
        kinds.append(kind)
        mk[strokes_canvas({1: line}, H, W) > 0] = len(kinds)
    dark = (v < ink[0]) & (s > ink[1])
    thin = dark & ~cv2.dilate(cv2.morphologyEx(u8(dark), cv2.MORPH_OPEN, disk(4)), disk(1)).astype(bool)
    elev = gradient(rgb) + wall * cv2.GaussianBlur(thin.astype(np.float32), (0, 0), 1.2)
    lab = watershed(zone, mk, elev)
    for kind, pts in join:
        ids = sorted({int(lab[y, x]) for x, y in pts} - {0})
        if not ids:
            continue
        for j in ids[1:]:
            lab[lab == j] = ids[0]
        kinds[ids[0] - 1] = kind
    lab = tidy(lab, amin=60, open_r=1)
    for pid in range(1, lab.max() + 1):
        m = lab == pid
        if 0 < m.sum() < absorb:
            ring = cv2.dilate(u8(m), disk(3)).astype(bool) & ~m
            around = lab[ring]
            if len(around) and np.all(around == around[0]) and around[0] > 0:
                lab[m] = around[0]
    return lab, kinds


def report_at(lab, kinds, arg):
    """Which piece is where: arg 'x,y;x,y' (art pixels)."""
    for q in arg.split(';'):
        x, y = map(int, q.split(','))
        print(f'  ({x},{y}): piece {lab[y, x]} {kinds[lab[y, x] - 1] if lab[y, x] else "-"}')


def tone_channels(tone, food, gamma=0.8, sig=1.5):
    """The art's light and shade as two paint channels (uint8): how much lighter (pale) or darker (deep) than the
    middle of its kind each spot is, for tinting the pieces paler and deeper by as much."""
    t = cv2.GaussianBlur(tone.astype(np.float32), (0, 0), sig)
    pale = np.clip(t, 0, 1) ** gamma * food
    deep = np.clip(-t, 0, 1) ** gamma * food
    return np.stack([np.round(pale * 255), np.round(deep * 255)], -1).astype(np.uint8)


def art_rgb(rgb, labels, sig=4.0, skip=None, dark=0.0):
    """The art's colours, each piece's own (blurred within its outline only, so that the next piece's and the ink
    line's don't bleed in, and without its glints: skip, a mask, painted on crisply instead), for art_colours."""
    out = np.zeros(rgb.shape, np.float32)
    f = rgb.astype(np.float32)
    if skip is None:   # its glints, and the dark of the ink lines and cuts in it
        hsv = cv2.cvtColor(rgb, cv2.COLOR_RGB2HSV_FULL)
        skip = ((hsv[..., 1] < 0.3 * 255) & (hsv[..., 2] > 0.88 * 255)) | (hsv[..., 2] < dark * 255)
    skip = cv2.dilate(u8(skip), disk(1)).astype(bool)
    for pid in range(1, labels.max() + 1):
        m = (labels == pid) & ~skip
        if not m.any():   # nothing but glints and ink: all of it
            m = labels == pid
        if not m.any():
            continue
        ys, xs = np.nonzero(m)
        y0, y1, x0, x1 = max(ys.min() - 8, 0), ys.max() + 9, max(xs.min() - 8, 0), xs.max() + 9
        mm = m[y0:y1, x0:x1].astype(np.float32)
        num = cv2.GaussianBlur(f[y0:y1, x0:x1] * mm[..., None], (0, 0), sig)
        den = cv2.GaussianBlur(mm, (0, 0), sig)[..., None]
        blk = num / np.maximum(den, 1e-3)
        full = (labels == pid)[y0:y1, x0:x1]
        out[y0:y1, x0:x1][full] = blk[full]
    rest = labels == 0
    out[rest] = f[rest]
    return np.clip(out, 0, 255).astype(np.uint8)


def kind_colours(rgb, lum, lab, kinds, pcts=(20, 50, 85), edge=3):
    """For each kind, the art's colour where its pieces are darkest, middling and lightest (the mean colour of the
    pixels round each luminance percentile, away from the ink line): '#rrggbb' triples, for fitting its palette."""
    inner = cv2.erode(u8(lab > 0), disk(edge)).astype(bool)
    edge_m = cv2.morphologyEx(u8(lab), cv2.MORPH_GRADIENT, disk(edge)) > 0
    kind_of = np.array(['none'] + list(kinds))[lab]
    out = {}
    for k in sorted(set(kinds)):
        m = (kind_of == k) & inner & ~edge_m
        if m.sum() < 50:
            continue
        lm, cm = lum[m], rgb[m].astype(np.float32)
        res = []
        for p in pcts:
            lo, hi = np.percentile(lm, max(p - 4, 0)), np.percentile(lm, min(p + 4, 100))
            sel = (lm >= lo) & (lm <= hi)
            c = cm[sel].mean(0)
            res.append('#%02x%02x%02x' % tuple(int(round(x)) for x in c))
        out[k] = res
    return out


def sauce_points(mask, spacing=28.0, edge_spacing=18.0, erode=3):
    """Points (art pixels) over where the sauce shows between the pieces (mask), for the heap's mesh to have its
    vertices there: along its edges and on a grid inside, so that its colours and light follow the art's there."""
    m = cv2.erode(u8(mask), disk(erode)).astype(bool)
    pts = [contour_points([m], edge_spacing)]
    ys, xs = np.nonzero(m)
    if len(xs):
        g = (xs % int(spacing) == 0) & (ys % int(spacing) == 0)
        pts.append(np.stack([xs[g], ys[g]], -1).astype(float))
    return np.concatenate([p.reshape(-1, 2) for p in pts], 0)


def heap_rgb(colours, kind_of, sauce='sauce', under=None):
    """The heap's colours: the art's where its sauce shows between the pieces, under them the sauce's middle colour
    (or what `under` gives: [(mask, rgb)]), so that its coarse faces carry no other piece's colours into the
    cracks between them."""
    out = colours.copy()
    m = kind_of == sauce
    mid = np.median(colours[m], 0) if m.any() else np.array([120, 40, 10])
    out[~m] = mid.astype(np.uint8)
    for mask, rgb in (under or []):
        out[mask] = rgb
    return out


def rim_guard(cam, hmap, zone, floor, V, margin=0.004, lift=0.002, blur=6.0):
    """The heap raised where the art shows food standing up over the dish's back rim: high enough at each pixel that
    its line of sight meets the food before it leaves the dish (margin inside the rim, read off the dish's
    vertices V: its rim, the highest of them), as tall food at the back stands; else what the art shows there would
    be laid out far behind the dish."""
    V = np.asarray(V)
    top = V[V[:, 2] > V[:, 2].max() - 0.004]
    xs = np.linspace(top[:, 0].min(), top[:, 0].max(), 41)
    ys = np.array([top[np.abs(top[:, 0] - x0) < 0.015, 1].max() for x0 in xs]) - margin   # its back rim
    H, W = hmap.shape
    vv, uu = np.nonzero(zone)
    x = (uu - cam.u0) / cam.k
    q = (cam.v0 - vv) / cam.k
    ymax = np.interp(x, xs, ys)
    need = (q - ymax * cam.se) / cam.ce - floor(x, ymax) + lift   # the height over the floor at the rim's margin
    out = hmap.copy()
    raise_ = np.zeros_like(hmap)
    raise_[vv, uu] = np.maximum(need - hmap[vv, uu], 0.0)
    raise_ = cv2.dilate(raise_.astype(np.float32), disk(int(blur)))
    raise_ = cv2.GaussianBlur(raise_, (0, 0), blur) * zone
    return out + raise_, raise_
