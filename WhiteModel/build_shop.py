"""汴河两岸 shop white models: the restaurant as it grows, 一级 (初出茅庐) to 五级 (名动一方).

Each level is its own building, laid out 1:1 from its art (the room shapes, and where every table, stool, stove,
counter, shelf, door, window and stair stands), in the vocabulary of the approved 初始 level (level_kit.py):

    一级 · 初出茅庐  大堂 3 桌                       初出茅庐·三桌食堂-2.png
    二级 · 市井买卖  大堂 4 桌                       餐厅增添第四张方桌-8.png
    三级 · 小有名气  一楼 4 · 二楼散座 1 · 雅间 1     水彩餐厅六桌布局改造-11.png
    四级 · 声名鹊起  一楼 4 · 二楼散座 3 · 雅间 1     扩建双层餐厅八桌水彩图-12.png
    五级 · 名动一方  一楼 4 · 二楼散座 6 · 雅间 2     楼上公共餐厅新增两桌-15.png

Positions were read off the art by fitting each room's floor (its four corners) and taking every piece's floor
contact as fractions of the room; each room is then sized so its tables keep the art's spacing with a 0.5 m walkway
between stool groups and from the walls (the art draws smaller furniture than the game's 1.0 m 方桌 and 方凳).

Conventions the game keys on (as in the 初始 level):
    groups      Kitchen, Hall (一楼大堂), Corridor, Upstairs (二楼散座), Yajian (雅间)
    K_AnTai     the kitchen's work table (案台) that opens the cooking screen; K_ZaoTai the stove range
    D_Table_n   in the order the design buys them: 1-4 downstairs (1 nearest the hall's door from the kitchen),
                5 the first upstairs, 6 雅间一, 7-8 upstairs (四级), 9-11 upstairs (五级), 12 雅间二
    D_Stool_n_k four round each table: k = 1 at (0, -0.78), 2 at (+0.78, 0), 3 at (0, +0.78), 4 at (-0.78, 0)
    Spot_Queue_1..4  where waiting guests stand, outside the entrance
The 二楼 stands behind and above the 一楼 hall (the art's cutaway): its slab sits over the back of the building and
the hall in front stays open to the sky, so the game's camera sees both floors and every table.

Run with Blender 5.2:
    blender -b --factory-startup --python build_shop.py -- [<out_dir>] --level N [--no-render]
Writes SM_Shop<N>.blend / .fbx, palette.json and renders/ (whitemodel.png from the game's camera, close-ups, toon)
to <out_dir>, by default WhiteModel/Shop<N>.
"""
import math
import os
import random
import re
import sys
from contextlib import contextmanager

import bpy
from mathutils import Matrix, Vector

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import level_kit as K  # noqa: E402
from level_kit import Prop  # noqa: E402

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
LEVEL = int(ARGS[ARGS.index('--level') + 1]) if '--level' in ARGS else 1
_pos = [a for i, a in enumerate(ARGS) if not a.startswith('--') and (i == 0 or ARGS[i - 1] != '--level')]
OUT = os.path.abspath(_pos[0]) if _pos else os.path.join(HERE, f'Shop{LEVEL}')
RENDER = '--no-render' not in ARGS
F0 = 0.45                    # the ground floor (top of the stone plinth), as in the 初始 level
WOKS = []                    # every wok set in a 灶台, for the counts
ROOMS = []                   # every room, for the walkway check
F2 = F0 + K.H + 0.5          # the 二楼's boards


# ================================================================= room shell

class Room:
    """A rectangular room: its group, its floor height and its extent in world metres. Local positions (u, v) are
    metres from its (x0, y0) corner, the corner nearest the left of the screen. Sides: 'L' (x = x0) and 'B' (y = y1)
    are the far walls, 'R' (x = x1) and 'F' (y = y0) the near ones, which the art cuts low."""

    def __init__(self, grp, x0, y0, w, d, f=F0):
        self.grp, self.f = grp, f
        self.x0, self.y0, self.x1, self.y1 = x0, y0, x0 + w, y0 + d
        self.w, self.d = w, d
        ROOMS.append(self)

    def at(self, u, v):
        return self.x0 + u, self.y0 + v

    def frame(self, side):
        """(axis, origin, inward, length) of a side, for level_kit.wall: u runs from x0 (B, F) or y0 (L, R)."""
        return {'L': ('y', (self.x0, self.y0), 1, self.d), 'R': ('y', (self.x1, self.y0), -1, self.d),
                'B': ('x', (self.x0, self.y1), -1, self.w), 'F': ('x', (self.x0, self.y0), 1, self.w)}[side]

    def on_side(self, side, u, off=0.0):
        """World point at u along a side, `off` metres into the room, and the side's inward normal."""
        n = {'L': (1, 0), 'R': (-1, 0), 'B': (0, -1), 'F': (0, 1)}[side]
        if side in 'LR':
            x, y = (self.x0 if side == 'L' else self.x1), self.y0 + u
        else:
            x, y = self.x0 + u, (self.y1 if side == 'B' else self.y0)
        return (x + n[0] * off, y + n[1] * off), n

    def against(self, side, u0, u1, depth, gap=0.12):
        """A piece standing against a side wall from u0 to u1, `depth` deep: (centre x, y, length, depth, turn) for a
        piece built along +x with its back at +y (see the prop builders). The default gap clears the wall's posts
        and their bases (柱础)."""
        (x, y), (nx, ny) = self.on_side(side, (u0 + u1) / 2, gap + depth / 2)
        turn = {'B': 0, 'L': 90, 'R': -90, 'F': 180}[side]
        return x, y, u1 - u0, depth, turn


def plinth(name, room, kerbs='FR', gaps=(), steps_=(), ext=(0.1, 0.1, 0.1, 0.1)):
    """Stone base under a room (as in the 初始 level): two courses up to the floor and kerb stones along the open
    sides. gaps: [(side, u0, u1)] where the kerb gives way to steps; steps_: [(side, u0, u1, n)] stone steps down.
    ext: how far it reaches past the room on the L, R, F, B sides (negative where a neighbour's plinth takes over)."""
    x0, x1, y0, y1, F = room.x0, room.x1, room.y0, room.y1, room.f
    el, er, ef, eb = ext
    p = Prop(name, room.grp, ((x0 + x1) / 2, (y0 + y1) / 2, 0), rmax=0.03)
    p.bx(x0 - el, x1 + er, y0 - ef, y1 + eb, 0, 0.22, 'Stone')
    p.bx(x0 - el + 0.02 * (el > 0), x1 + er - 0.02 * (er > 0), y0 - ef + 0.02 * (ef > 0), y1 + eb - 0.02 * (eb > 0),
         0.22, F - 0.04, 'Stone')
    for side in kerbs:
        L = room.w if side in 'FB' else room.d
        s0, s1 = (el, er) if side in 'FB' else (ef, eb)
        n = max(1, round((L + s0 + s1) / 0.36))
        cut = [(a, b) for s_, a, b in gaps if s_ == side]
        for k in range(n):
            a = -s0 + k * (L + s0 + s1) / n
            b = a + (L + s0 + s1) / n
            if any(c0 - 0.05 < (a + b) / 2 < c1 + 0.05 for c0, c1 in cut):
                continue
            a, b = a + 0.005, b - 0.005
            if side == 'F':
                p.bx(x0 + a, x0 + b, y0 - 0.1, y0 + 0.16, F - 0.05, F + 0.01, 'Stone')
            elif side == 'B':
                p.bx(x0 + a, x0 + b, y1 - 0.16, y1 + 0.1, F - 0.05, F + 0.01, 'Stone')
            elif side == 'R':
                p.bx(x1 - 0.16, x1 + 0.1, y0 + a, y0 + b, F - 0.05, F + 0.01, 'Stone')
            else:
                p.bx(x0 - 0.1, x0 + 0.16, y0 + a, y0 + b, F - 0.05, F + 0.01, 'Stone')
    for side, u0, u1, n in steps_:
        rise = F / (n + 1)
        for k in range(n):
            z1 = F - rise * (k + 1)
            e = 0.1 + 0.3 * (k + 1)
            if side == 'F':
                p.bx(x0 + u0, x0 + u1, y0 - e, y0 - 0.1, 0, z1, 'Stone')
            elif side == 'R':
                p.bx(x1 + 0.1, x1 + e, y0 + u0, y0 + u1, 0, z1, 'Stone')
            elif side == 'L':
                p.bx(x0 - e, x0 - 0.1, y0 + u0, y0 + u1, 0, z1, 'Stone')
            else:
                p.bx(x0 + u0, x0 + u1, y1 + 0.1, y1 + e, 0, z1, 'Stone')
    return p


def tile_floor(name, room, cell=0.5, split=0.2, mat='Tile', margin=(0.09, 0.19, 0.2, 0.09)):
    """Stone-flag floor (厨房地板): cells of about `cell` m, a few split into four. margin: L, R, F, B insets."""
    F = room.f
    p = Prop(name, room.grp, ((room.x0 + room.x1) / 2, (room.y0 + room.y1) / 2, F), rmax=0.02)
    ml, mr, mf, mb = margin
    X0, X1, Y0, Y1 = room.x0 + ml, room.x1 - mr, room.y0 + mf, room.y1 - mb
    nx, ny = max(1, round((X1 - X0) / cell)), max(1, round((Y1 - Y0) / cell))
    cw, ch = (X1 - X0) / nx, (Y1 - Y0) / ny
    g = 0.025
    for i in range(nx):
        for j in range(ny):
            x0, y0 = X0 + i * cw, Y0 + j * ch
            if random.random() < split:
                for a in range(2):
                    for b in range(2):
                        p.bx(x0 + a * cw / 2 + g / 2, x0 + (a + 1) * cw / 2 - g / 2, y0 + b * ch / 2 + g / 2,
                             y0 + (b + 1) * ch / 2 - g / 2, F - 0.04, F + 0.012, mat, open_bottom=True, top_only=True)
            else:
                p.bx(x0 + g / 2, x0 + cw - g / 2, y0 + g / 2, y0 + ch - g / 2, F - 0.04,
                     F + 0.012 + random.uniform(0, 0.006), mat, open_bottom=True, top_only=True)
    return p.finish()


def plank_floor(name, room, along='y', pw=0.22, length=1.8, margin=(0.06, 0.16, 0.16, 0.06), rugs=()):
    """Board floor (饭堂地板): planks `pw` wide running `along` x or y, joints staggered; rugs [(x0, x1, y0, y1)] lie
    on it (part of the floor, as furniture stands on them)."""
    F = room.f
    p = Prop(name, room.grp, ((room.x0 + room.x1) / 2, (room.y0 + room.y1) / 2, F), rmax=0.012)
    ml, mr, mf, mb = margin
    X0, X1, Y0, Y1 = room.x0 + ml, room.x1 - mr, room.y0 + mf, room.y1 - mb
    a0, a1, b0, b1 = (X0, X1, Y0, Y1) if along == 'x' else (Y0, Y1, X0, X1)
    row, bb = 0, b0
    while bb < b1 - 0.05:
        bn = min(bb + pw, b1)
        offs = [0.0, length / 2, length / 4, 3 * length / 4][row % 4]
        cuts = [a0] + [c for c in (a0 + offs + length * k for k in range(1, 40)) if a0 + 0.3 < c < a1 - 0.3] + [a1]
        for a, b in zip(cuts, cuts[1:]):
            if along == 'x':
                p.bx(a + 0.004, b - 0.004, bb + 0.005, bn - 0.005, F - 0.04, F + 0.008, 'WoodFloor', open_bottom=True,
                     top_only=True)
            else:
                p.bx(bb + 0.005, bn - 0.005, a + 0.004, b - 0.004, F - 0.04, F + 0.008, 'WoodFloor', open_bottom=True,
                     top_only=True)
        bb = bn
        row += 1
    for r_ in rugs:
        rug(p, *r_)
    return p.finish()


def cut_wall(p, axis, origin, inward, length, posts, segs, h, tall=None):
    """A near wall cut low at h, as the art draws the walls facing the camera: posts, plaster panels or
    lattice windows (a boarded wainscot and the lattice up to the cut), a timber cap along the cut. 'opening' leaves a
    gap. tall: {u: height} for posts that carry something higher (a door beam, a passage roof)."""
    M, s = K.along(axis, origin, inward)
    F = K.F
    top = F + h
    tall = tall or {}
    for u in posts:
        hh = tall.get(u, h)
        p.box((u, 0, F + (hh + 0.04) / 2), (0.17, 0.17, hh + 0.04), 'Timber', M=M)
        p.box((u, 0, F + hh + 0.07), (0.21, 0.21, 0.06), 'Timber', M=M)          # post cap
        p.box((u, 0.0, F + 0.07), (0.21, 0.21, 0.22), 'Timber', M=M, r=0.016)  # 柱础, down onto the plinth
    for u0, u1, kind in segs:
        a, b = u0 + 0.085, u1 - 0.085
        w = b - a
        if kind == 'opening' or w < 0.05:
            continue
        p.box(((u0 + u1) / 2, 0, F + 0.03), (u1 - u0, 0.11, 0.14), 'Timber', M=M)   # sill, seated on the plinth
        if kind == 'plaster':
            p.box(((a + b) / 2, -0.01 * s, (F + 0.1 + top - 0.05) / 2), (w, 0.06, top - 0.05 - F - 0.1), 'Plaster', M=M)
            if h > 0.95:
                p.box(((a + b) / 2, 0.035 * s, F + 0.55), (w, 0.05, 0.05), 'Timber', M=M)
        elif kind == 'window':
            zs = F + min(0.5, h - 0.3)
            p.box(((a + b) / 2, 0.0, (F + 0.1 + zs) / 2), (w, 0.07, zs - F - 0.1), 'Timber', M=M)
            p.box(((a + b) / 2, 0.0, zs), (w, 0.1, 0.06), 'Timber', M=M)
            p.box(((a + b) / 2, -0.03 * s, (zs + top - 0.05) / 2), (w, 0.02, top - 0.05 - zs), 'Paper', M=M)
            nv = max(2, round(w / 0.22))
            for k in range(1, nv):
                uu = a + w * k / nv
                p.box((uu, 0.0, (zs + top - 0.05) / 2), (0.035 if k != nv // 2 else 0.06, 0.05, top - 0.05 - zs),
                      'Timber', M=M)
            p.box(((a + b) / 2, 0.0, zs + (top - zs) * 0.55), (w, 0.045, 0.03), 'Timber', M=M)
        p.box(((u0 + u1) / 2, 0, top - 0.025), (u1 - u0, 0.13, 0.05), 'Timber', M=M)     # cap along the cut
    return M, s


def side(p, room, which, breaks, kinds, h=None, skip=(), curtains=(), lanterns=(), brackets=(), tall=None,
         scrolls=()):
    """One side of a room. breaks: u of the segment ends (0 … length), each with a post unless listed in `skip`
    (corners another wall already stands on); kinds: the segments' kinds ('plaster', 'window', 'door', 'opening',
    'dado'; None for no wall). h=None builds a full wall (level_kit.wall), else one cut low at h.
    curtains: [(u0, u1)] blue 门帘 valances; lanterns: u of posts with a lantern; scrolls: [(u, width)] hung paintings."""
    axis, origin, inward, length = room.frame(which)
    posts = [u for u in breaks if not any(abs(u - s_) < 1e-6 for s_ in skip)]
    segs = [(a, b, k) for a, b, k in zip(breaks, breaks[1:], kinds) if k]
    if h is None:
        M, s = K.wall(p, axis, origin, inward, length, posts, segs, brackets=brackets)
        ztop = K.F + K.H
    else:
        M, s = cut_wall(p, axis, origin, inward, length, posts, segs, h, tall)
        ztop = K.F + h
    for a, b in curtains:
        K.curtain(p, M, s, a + 0.1, b - 0.1, ztop - 0.45)
    for u in lanterns:
        (x, y), (nx, ny) = room.on_side(which, u, 0.09)
        K.wall_lantern(p, x, y, (nx, ny))
    for u, w in scrolls:
        hang_scroll(p, room, which, u, w)
    return M, s


def hang_scroll(p, room, which, u, w, z0=None, z1=None):
    """挂画: a paper scroll with timber rods, flat on a wall."""
    F = K.F
    z0 = F + 0.8 if z0 is None else z0
    z1 = F + 1.65 if z1 is None else z1
    (x, y), (nx, ny) = room.on_side(which, u, 0.05)
    if which in 'LR':
        p.bx(x - 0.008, x + 0.008, y - w / 2, y + w / 2, z0, z1, 'Paper')
        for z in (z0, z1):
            p.bx(x - 0.02, x + 0.02, y - w / 2 - 0.04, y + w / 2 + 0.04, z - 0.02, z + 0.02, 'Timber')
    else:
        p.bx(x - w / 2, x + w / 2, y - 0.008, y + 0.008, z0, z1, 'Paper')
        for z in (z0, z1):
            p.bx(x - w / 2 - 0.04, x + w / 2 + 0.04, y - 0.02, y + 0.02, z - 0.02, z + 0.02, 'Timber')


def door_frame(p, room, which, u0, u1, ztop, curtain=True, drop=0.75, strips=4, lantern_out=False):
    """A doorway in a near wall cut low: two posts up to ztop, a head beam, a threshold stone and the blue 门帘."""
    axis, origin, inward, length = room.frame(which)
    M, s = K.along(axis, origin, inward)
    F = K.F
    for u in (u0, u1):
        p.box((u, 0, F + (ztop - F) / 2), (0.17, 0.17, ztop - F), 'Timber', M=M)
        p.box((u, 0, ztop + 0.03), (0.21, 0.21, 0.06), 'Timber', M=M)
        p.box((u, 0.0, F + 0.09), (0.21, 0.21, 0.18), 'Timber', M=M, r=0.016)
    p.box(((u0 + u1) / 2, 0, ztop - 0.07), (u1 - u0, 0.14, 0.14), 'Timber', M=M)     # head beam
    p.box(((u0 + u1) / 2, 0, F - 0.015), (u1 - u0 - 0.17, 0.11, 0.05), 'Stone', M=M)   # threshold
    if curtain:
        K.curtain(p, M, s, u0 + 0.12, u1 - 0.12, ztop - 0.16, drop=drop, strips=strips)
    if lantern_out:
        for u in (u0, u1):
            (x, y), (nx, ny) = room.on_side(which, u, -0.09)
            K.wall_lantern(p, x, y, (-nx, -ny), z=ztop - 0.45)
    return M, s


# ================================================================= furniture and props
# Wall-backed pieces are built along +x with their back at +y, centred on the prop's pivot, then turned
# (Room.against gives the centre, size and turn).

def jar(p, x, y, z, r, h, mat='Glaze', lid=True):
    """坛子: a glazed jar with a shoulder and a small mouth."""
    p.lathe([(r * 0.62, z), (r * 0.95, z + h * 0.35), (r, z + h * 0.55), (r * 0.8, z + h * 0.82), (r * 0.5, z + h * 0.9),
             (r * 0.5, z + h)], (x, y, 0), mat, n=8, cap_top=not lid)
    if lid:
        p.lathe([(r * 0.56, z + h), (r * 0.12, z + h + 0.045)], (x, y, 0), 'Wood', n=8, cap_bottom=False)


def teapot(p, x, y, z, r=0.06):
    p.lathe([(r * 0.6, z), (r, z + r * 0.6), (r * 0.95, z + r * 1.1), (r * 0.5, z + r * 1.4), (r * 0.3, z + r * 1.5)],
            (x, y, 0), 'Ceramic', n=8)
    p.box((x + r * 1.1, y, z + r * 0.9), (r * 0.7, r * 0.22, r * 0.22), 'Ceramic', rot=0)   # spout


def cup(p, x, y, z, r=0.03):
    p.lathe([(r * 0.75, z), (r, z + r * 1.4), (r * 0.88, z + r * 1.4)], (x, y, 0), 'Ceramic', n=8, cap_top=False)


def dining(n, grp, x, y, turn=0.0):
    """A 方桌 with its runner and tea tray (no flowers: the 花草 art comes separately) and its four 方凳."""
    F = K.F
    p = K.table(grp, f'D_Table_{n}', x, y)
    top = F + 0.78
    ry = y + 0.16                                                                      # runner (桌旗) along x
    p.bx(x - 0.5, x + 0.5, ry - 0.13, ry + 0.13, top, top + 0.004, 'Cushion', r=0.002)
    for sg in (-1, 1):                                                                 # its ends hang over the edges
        xe = x + sg * 0.503
        p.bx(xe - 0.003, xe + 0.003, ry - 0.13, ry + 0.13, top - 0.11, top + 0.004, 'Cushion', r=0.002)
    p.bx(x - 0.2, x + 0.06, y - 0.24, y - 0.04, top - 0.006, top + 0.012, 'Wood', r=0.006)      # tea tray
    teapot(p, x - 0.12, y - 0.14, top + 0.012, 0.055)
    cup(p, x - 0.01, y - 0.09, top + 0.012)
    cup(p, x - 0.01, y - 0.19, top + 0.012)
    p.turn = turn
    p.finish()
    for k, (dx, dy) in enumerate(((0, -0.78), (0.78, 0), (0, 0.78), (-0.78, 0))):
        K.stool(grp, f'D_Stool_{n}_{k + 1}', x + dx, y + dy)


def stove(p, cx, cy, L, D, woks, h=0.8, chimney=None, steamers=(), step=None, back=0.0):
    """灶台: a brick range, its back at +y; an iron wok at each local u in `woks` (from the centre), a fire mouth
    under each in the front face, an optional chimney (u) at the back and straw steamers (u) on spare holes.
    step: (u0, h2) raises the part from u0 on to h2 (the art's back block); back: a brick backsplash that high along
    the back edge (a range standing free of the wall)."""
    F = K.F
    x0, x1, y0, y1 = cx - L / 2, cx + L / 2, cy - D / 2, cy + D / 2
    if back > 0:
        p.bx(x0, x1, y1 - 0.12, y1, F + h, F + h + back, 'Brick')
    parts = [(x0, x1, h)] if not step else [(x0, cx + step[0], h), (cx + step[0], x1, step[1])]
    for a, b, hh in parts:
        p.bx(a, b, y0, y1, F, F + hh - 0.07, 'Brick')
        p.bx(a - 0.02, b + 0.02, y0 - 0.02, y1 + 0.02, F + hh - 0.07, F + hh, 'Brick')    # top slab
    WOKS.extend(woks)
    for u in list(woks) + list(steamers):
        hh = parts[-1][2] if step and u >= step[0] else h
        cx_ = cx + u
        if u in steamers:
            p.lathe([(0.2, F + hh), (0.21, F + hh + 0.16), (0.19, F + hh + 0.16)], (cx_, cy, 0), 'Straw', n=14,
                    cap_top=False, rims=[0, 1])
            p.lathe([(0.21, F + hh + 0.16), (0.13, F + hh + 0.23), (0.03, F + hh + 0.26)], (cx_, cy, 0), 'Straw',
                    n=14, cap_bottom=False)
            continue
        z = F + hh
        p.lathe([(0.02, z - 0.14), (0.2, z - 0.08), (0.31, z + 0.03), (0.33, z + 0.06), (0.3, z + 0.06),
                 (0.18, z - 0.04), (0.03, z - 0.1)], (cx_, cy - 0.02, 0), 'Iron', n=16, cap_bottom=False, cap_top=False,
                rims=[3])                                                   # the bowl closed down to its bottom
        for sg in (-1, 1):                                                   # wok ears
            p.bx(cx_ + sg * 0.33 - 0.03, cx_ + sg * 0.33 + 0.03, cy - 0.04, cy, z + 0.04, z + 0.07, 'Iron')
        p.bx(cx_ - 0.17, cx_ + 0.17, y0 - 0.06, y0 + 0.02, F + 0.1, F + 0.4, 'Iron')         # fire mouth
        p.blob((cx_, y0 - 0.03, F + 0.2), 0.11, 'Fire', (1.2, 0.4, 1.0))
    if chimney is not None:
        a = cx + chimney
        p.bx(a - 0.22, a + 0.22, y1 - 0.44, y1, F + h, F + K.H + 0.55, 'Brick')
        p.bx(a - 0.25, a + 0.25, y1 - 0.47, y1 + 0.03, F + K.H + 0.55, F + K.H + 0.65, 'Brick')


def work_table(p, cx, cy, L, D, h=0.84, legs=None):
    """案台: a long timber work table with a low shelf (baskets) and the day's work on top."""
    F = K.F
    x0, x1, y0, y1 = cx - L / 2, cx + L / 2, cy - D / 2, cy + D / 2
    top = F + h
    p.bx(x0, x1, y0, y1, top - 0.1, top, 'Wood')
    nl = legs or (3 if L > 1.9 else 2)
    for i in range(nl):
        x = x0 + 0.08 + (L - 0.16) * i / (nl - 1)
        for y in (y0 + 0.08, y1 - 0.08):
            p.box((x, y, F + (h - 0.1) / 2), (0.1, 0.1, h - 0.1), 'Wood')
    for y in (y0 + 0.04, y1 - 0.08):
        p.bx(x0 + 0.1, x1 - 0.1, y, y + 0.04, top - 0.22, top - 0.1, 'Wood')
    p.bx(x0 + 0.1, x1 - 0.1, y0 + 0.08, y1 - 0.08, F + 0.16, F + 0.2, 'Wood')                # low shelf
    for k in range(2):
        bx_ = x0 + L * (0.3 if k == 0 else 0.7)
        K.basket(p, bx_, cy, F + 0.2, 0.16, 0.14, fill='Veg' if k == 0 else None)
    # on top: chopping block and cleaver, greens, a big bowl of vegetables, bottles, bowls, a tray of dough
    a = x0 + L * 0.42
    p.bx(a - 0.25, a + 0.25, cy - 0.22, cy + 0.12, top, top + 0.05, 'Wood')                  # chopping board
    p.bx(a - 0.02, a + 0.18, cy - 0.12, cy - 0.04, top + 0.05, top + 0.062, 'Iron')         # cleaver
    p.bx(a + 0.18, a + 0.26, cy - 0.1, cy - 0.06, top + 0.05, top + 0.075, 'Wood')
    for k in range(3):                                                                      # bok choy, white stems out
        bx_ = x0 + L * 0.6 + k * 0.17
        p.blob((bx_, cy - D * 0.2, top + 0.045), 0.065, 'Veg', (0.85, 1.5, 0.65))
        p.blob((bx_, cy - D * 0.2 - 0.12, top + 0.035), 0.04, 'Ceramic', (0.9, 1.3, 0.8))
    K.bowl(p, x0 + L * 0.2, cy + D * 0.2, top, 0.2, 'Straw', h=0.12)                          # big bowl of greens
    for k in range(4):
        p.blob((x0 + L * 0.2 + 0.08 * math.cos(k * 1.6), cy + D * 0.2 + 0.08 * math.sin(k * 1.6), top + 0.12), 0.07,
               'Veg', (1, 1, 0.8))
    for k, (u, mat) in enumerate(((0.3, 'Glaze'), (0.36, 'Ceramic'), (0.55, 'Glaze'))):         # bottles and jars
        jar(p, x0 + L * u, cy + D * 0.25, top, 0.06, 0.18, mat, lid=False)
    K.bowl(p, x0 + L * 0.72, cy + D * 0.22, top, 0.1)
    K.bowl(p, x0 + L * 0.82, cy + D * 0.18, top, 0.09, 'Glaze')
    p.bx(x0 + L * 0.86, x0 + L * 0.96, cy - 0.2, cy + 0.15, top, top + 0.02, 'Straw')        # tray with dough
    for k in range(3):
        p.blob((x0 + L * 0.91, cy - 0.1 + k * 0.1, top + 0.045), 0.03, 'Ceramic')


def shelf_unit(p, cx, cy, L, D, Ht=1.9, base=0.75, tiers=3, fill='mixed'):
    """碗柜: a cabinet base with drawers and open shelves above with jars and bowls, its back at +y."""
    F = K.F
    x0, x1, y0, y1 = cx - L / 2, cx + L / 2, cy - D / 2, cy + D / 2
    p.bx(x0, x1, y0, y1, F, F + base, 'Wood')
    p.bx(x0 - 0.02, x1 + 0.02, y0 - 0.02, y1 + 0.01, F + base, F + base + 0.04, 'Wood')
    nd = max(2, round(L / 0.45))
    for k in range(nd):
        a = x0 + 0.05 + k * (L - 0.1) / nd
        p.bx(a + 0.02, a + (L - 0.1) / nd - 0.02, y0 - 0.025, y0, F + base - 0.3, F + base - 0.06, 'Wood')
        p.bx(a + 0.02, a + (L - 0.1) / nd - 0.02, y0 - 0.025, y0, F + 0.08, F + base - 0.34, 'Wood')
    for x in (x0 + 0.03, x1 - 0.03):
        p.bx(x - 0.03, x + 0.03, y0 + 0.02, y1, F + base + 0.04, F + Ht, 'Wood')
    p.bx(x0 + 0.06, x1 - 0.06, y1 - 0.03, y1, F + base + 0.04, F + Ht, 'Wood')                  # back board
    zs = [F + base + 0.04 + (Ht - base - 0.04) * k / tiers for k in range(1, tiers + 1)]
    for z in zs:
        p.bx(x0, x1, y0 + 0.02, y1, z - 0.035, z, 'Wood')
    rnd = random.Random(int(cx * 31 + cy * 17))
    levels = [F + base + 0.04] + zs[:-1]
    for i, z in enumerate(levels):
        n = max(2, int((L - 0.15) / 0.3))
        for k in range(n):
            x = x0 + 0.14 + k * (L - 0.28) / max(1, n - 1)
            if fill == 'bowls' or (fill == 'mixed' and i == 0):
                for s_ in range(rnd.choice((2, 3))):
                    K.bowl(p, x, cy, z + s_ * 0.045, 0.085)
            else:
                jar(p, x, cy, z, 0.075, rnd.choice((0.16, 0.2, 0.22)), rnd.choice(('Glaze', 'Ceramic', 'Glaze')))


def cabinet(p, cx, cy, L, D, h=0.78, doors=2, top=()):
    """A low cabinet (柜) with doors, its back at +y; `top` lists what stands on it."""
    F = K.F
    x0, x1, y0, y1 = cx - L / 2, cx + L / 2, cy - D / 2, cy + D / 2
    p.bx(x0, x1, y0, y1, F, F + h - 0.05, 'Wood')
    p.bx(x0 - 0.03, x1 + 0.03, y0 - 0.03, y1 + 0.01, F + h - 0.05, F + h, 'Wood')
    for k in range(doors):
        a = x0 + 0.06 + k * (L - 0.12) / doors
        p.bx(a + 0.02, a + (L - 0.12) / doors - 0.02, y0 - 0.025, y0, F + 0.1, F + h - 0.12, 'Wood')
    z = F + h
    for kind, u, r in top:
        x = cx + u
        if kind == 'steamer':
            for lay in range(2):
                p.lathe([(r, z + lay * 0.13), (r, z + lay * 0.13 + 0.12)], (x, cy, 0), 'Straw', n=16,
                        cap_top=False, rims=[0])
            p.lathe([(r + 0.01, z + 0.25), (r * 0.7, z + 0.32), (0.04, z + 0.35)], (x, cy, 0), 'Straw', n=16)
        elif kind == 'jar':
            jar(p, x, cy, z, r, r * 2.4, 'Glaze')
        elif kind == 'pale':
            jar(p, x, cy, z, r, r * 2.6, 'Ceramic', lid=False)
        elif kind == 'basket':
            K.basket(p, x, cy, z, r, 0.1, fill='Veg')
        elif kind == 'bowls':
            for s_ in range(3):
                K.bowl(p, x, cy, z + s_ * 0.045, r)


def open_rack(p, cx, cy, L, D, h=0.9, tiers=2, fill='bowls'):
    """An open timber rack (碗架) with bowls or jars on its shelves, its back at +y."""
    F = K.F
    x0, x1, y0, y1 = cx - L / 2, cx + L / 2, cy - D / 2, cy + D / 2
    for x in (x0 + 0.03, x1 - 0.03):
        for y in (y0 + 0.03, y1 - 0.03):
            p.box((x, y, F + h / 2), (0.06, 0.06, h), 'Wood')
    zs = [F + 0.12 + (h - 0.16) * k / tiers for k in range(tiers + 1)]
    rnd = random.Random(int(cx * 13 + cy * 7))
    for i, z in enumerate(zs):
        p.bx(x0, x1, y0, y1, z - 0.03, z, 'Wood')
        if i == len(zs) - 1 and fill in ('bowls', 'baskets'):
            continue
        n = max(2, int((L - 0.1) / (0.45 if fill == 'baskets' else 0.26)))
        for k in range(n):
            x = x0 + (0.22 if fill == 'baskets' else 0.15) + k * (L - (0.44 if fill == 'baskets' else 0.3)) / max(1, n - 1)
            if fill == 'bowls':
                for s_ in range(rnd.choice((2, 3))):
                    K.bowl(p, x, cy, z + s_ * 0.045, 0.09)
            elif fill == 'baskets':
                K.basket(p, x, cy, z, 0.17, 0.13, fill='Veg' if (i + k) % 2 == 0 else None)
            else:
                jar(p, x, cy, z, 0.08, rnd.choice((0.18, 0.22)), rnd.choice(('Glaze', 'Ceramic')))


def water_jar(p, x, y, r=0.4, h=0.75, mat='Stone'):
    """水缸: a big stone water jar."""
    F = K.F
    prof = [(r * 0.72, F), (r * 0.95, F + h * 0.35), (r, F + h * 0.7), (r * 0.95, F + h * 0.93), (r * 0.98, F + h),
            (r * 0.86, F + h), (r * 0.82, F + h * 0.8)]
    p.lathe(prof, (x, y, 0), mat, n=20, cap_top=False, rims=[0, 4])
    p.lathe([(r * 0.82, F + h * 0.8)], (x, y, 0), 'Water', n=20, cap_bottom=False)


def firewood(p, cx, cy, L, D, rows=None):
    """柴堆: logs from the wall into the room (local y), their cut ends facing out, stacked in a pyramid."""
    F = K.F
    n0 = max(2, round((L - 0.04) / 0.15))
    rows = rows or [n0 - i for i in range(min(n0, 4))]
    for layer, n in enumerate(rows):
        for k in range(n):
            x = cx - L / 2 + 0.08 + (L - 0.16) * (k + 0.5 * layer) / max(1, rows[0] - 1)
            p.lathe([(0.072, -D / 2), (0.072, D / 2)], (0, 0, 0), 'Wood', n=8,
                    M=Matrix.Translation((x, cy, F + 0.072 + layer * 0.13)) @ Matrix.Rotation(math.radians(90), 4, 'X'))


def bench(p, cx, cy, L, D, h=0.42, jars=2):
    """A low bench (矮几) against a wall with a few jars on it."""
    F = K.F
    x0, x1, y0, y1 = cx - L / 2, cx + L / 2, cy - D / 2, cy + D / 2
    p.bx(x0, x1, y0, y1, F + h - 0.05, F + h, 'Wood')
    for x in (x0 + 0.06, x1 - 0.06):
        p.bx(x - 0.035, x + 0.035, y0 + 0.03, y1 - 0.03, F, F + h - 0.05, 'Wood')
    p.bx(x0 + 0.06, x1 - 0.06, y0 + 0.08, y0 + 0.11, F + 0.1, F + 0.14, 'Wood')
    for k in range(jars):
        x = x0 + (k + 0.5) * L / jars
        jar(p, x, cy, F + h, 0.09 if k % 2 else 0.11, 0.22 if k % 2 else 0.26, 'Glaze' if k % 2 else 'Ceramic')


def stair(name, grp, x, y, d, width, run, rise, rail=+1, newel=True, closed=True, landing=0.0, wall_side=None):
    """A straight timber stair. (x, y): the middle of the bottom step's front edge; d: unit climb direction along
    x or y; it climbs `rise` over `run`. rail: the side (+1 left of the climb, -1 right, 0 none) with a handrail and
    balusters; wall_side gets a plain stringer. Solid steps (closed underneath). landing: a platform that long at
    the top."""
    F = K.F
    n = max(3, round(rise / 0.18))
    tr, rr = run / n, rise / n
    yaw = math.atan2(d[1], d[0])
    p = Prop(name, grp, (x + d[0] * run / 2, y + d[1] * run / 2, F), rmax=0.02)
    B = Matrix.Translation((x, y, 0)) @ Matrix.Rotation(yaw, 4, 'Z')   # local: X up the stair, Y to its left
    w2 = width / 2
    for k in range(n):
        z1 = F + rr * (k + 1)
        p.box((tr * (k + 0.5), 0, (F + z1) / 2 if closed else z1 - 0.03), (tr + 0.002, width, (z1 - F) if closed else 0.06),
              'Wood', M=B, r=0.012)
        p.box((tr * (k + 0.5) - 0.01, 0, z1 + 0.012), (tr + 0.03, width + 0.04, 0.024), 'Wood', M=B, r=0.008)   # tread
    if landing > 0:
        p.box((run + landing / 2, 0, (F + F + rise) / 2), (landing, width, rise), 'Wood', M=B, r=0.012)
        p.box((run + landing / 2, 0, F + rise + 0.012), (landing + 0.03, width + 0.04, 0.024), 'Wood', M=B, r=0.008)
    L = math.hypot(run, rise)
    pitch = math.atan2(rise, run)
    slope = rise / run
    t0 = (0.13 / math.cos(pitch) - 0.07) / slope + 0.02          # where the stringer's lower edge meets the floor
    t1 = run + 0.05
    for sg in (+1, -1):
        if sg != rail and sg != wall_side:
            continue
        tc = (t0 + t1) / 2
        S = B @ Matrix.Translation((tc, sg * (w2 + 0.03), F + 0.07 + tc * slope)) @ Matrix.Rotation(-pitch, 4, 'Y')
        p.box((0, 0, 0), ((t1 - t0) / math.cos(pitch), 0.06, 0.26), 'Timber', M=S)          # stringer
        if sg == rail:
            R = B @ Matrix.Translation((run / 2, sg * (w2 + 0.03), F + rise / 2 + 0.85)) @ \
                Matrix.Rotation(-pitch, 4, 'Y')
            p.box((0, 0, 0), (L, 0.07, 0.07), 'Timber', M=R)                                  # handrail
            nb = max(2, round(run / 0.3))
            for k in range(1, nb):
                t = run * k / nb
                z0 = F + rise * k / nb + 0.1
                p.box((t, sg * (w2 + 0.03), z0 + 0.37), (0.04, 0.04, 0.74), 'Timber', M=B)
            if newel:
                for t, z in ((0.05, F), (run + landing - 0.05, F + rise)):
                    p.box((t, sg * (w2 + 0.03), z + 0.5), (0.12, 0.12, 1.0), 'Timber', M=B)
                    p.box((t, sg * (w2 + 0.03), z + 1.03), (0.16, 0.16, 0.06), 'Timber', M=B)
    return p


def stair_wall(p, x_top, x_foot, y, z_top, z_foot, h=1.1, bays=3, lanterns=()):
    """The tall outer wall beside a straight stair running along x (the art's 四级 stair): timber posts, plaster
    panels and a timber cap, sloping with the stair's line from (x_top, z_top) to (x_foot, z_foot) and standing h
    above it; wall lanterns facing -y on the posts listed (indices)."""
    slope = (z_top - z_foot) / (x_top - x_foot)
    S = Matrix.Translation((x_foot, y, z_foot)) @ Matrix(((1, 0, 0, 0), (0, 1, 0, 0), (slope, 0, 1, 0), (0, 0, 0, 1)))
    L = x_top - x_foot
    us = [L * k / bays for k in range(bays + 1)]
    for k, u in enumerate(us):
        p.box((u, 0, (h + 0.15) / 2), (0.13, 0.13, h + 0.75), 'Timber', M=S)   # posts stand above the cap
        if k in lanterns:
            K.wall_lantern(p, x_foot + u, y - 0.09, (0, -1), z=z_foot + slope * u + h + 0.05)
    for a, b in zip(us, us[1:]):
        w = abs(b - a) - 0.13
        p.box(((a + b) / 2, 0, (0.22 + h - 0.06) / 2), (w, 0.05, h - 0.28), 'Plaster', M=S)
        p.box(((a + b) / 2, 0, 0.2), (w, 0.08, 0.06), 'Timber', M=S)
    p.box((L / 2, 0, h), (abs(L) + 0.2, 0.17, 0.08), 'Timber', M=S)                     # cap


def stones(name, grp, pts, seed=3):
    """Stepping stones (x, y, w, d) on the ground."""
    rnd = random.Random(seed)
    cx = sum(q[0] for q in pts) / len(pts)
    cy = sum(q[1] for q in pts) / len(pts)
    p = Prop(name, grp, (cx, cy, 0), rmax=0.02)
    for x, y, w, d in pts:
        p.box((x, y, 0.02), (w, d, 0.06), 'Stone', rot=rnd.uniform(-4, 4))
    return p.finish()


def corridor(c, steps, back='plaster', breaks=None, lanterns=(0.0,), floor_left=0.02, posts=(),
             ext=(-0.1, -0.1, 0.1, 0.1)):
    """走廊 (as the 初始 level's, after 走廊.png): a covered passage from the kitchen to the hall on its own plinth, a
    stone floor, a back wall, and its open front: a beam with the blue 门帘 hanging from it (as the art draws it) and
    stone steps down at steps = (u0, u1). posts: u of extra full-height front posts (where no wall stands)."""
    a, b = steps
    plinth('C_Plinth', c, kerbs='F', gaps=[('F', a - 0.05, b + 0.05)], steps_=[('F', a, b, 3)], ext=ext).finish()
    tile_floor('C_Floor', c, cell=0.42, split=0.0, margin=(floor_left, 0.02, 0.16, 0.08))
    p = Prop('C_Walls', 'Corridor', (c.x0 + c.w / 2, c.y1, K.F), rmax=0.03)
    breaks = breaks or [0, c.w / 3, 2 * c.w / 3, c.w]
    side(p, c, 'B', breaks, [back] * (len(breaks) - 1), skip=[0, c.w], brackets=breaks)
    M, s = K.along(*c.frame('F')[:3])
    for u in posts:
        p.box((u, 0, K.F + (K.H + 0.08) / 2), (0.17, 0.17, K.H + 0.08), 'Timber', M=M)
        p.box((u, 0, K.F + K.H + 0.08), (0.21, 0.21, 0.07), 'Timber', M=M)
        p.box((u, 0.0, K.F + 0.07), (0.21, 0.21, 0.22), 'Timber', M=M, r=0.016)
    p.box((c.w / 2, 0, K.F + K.H - 0.07), (c.w, 0.14, 0.14), 'Timber', M=M)              # front beam
    K.curtain(p, M, s, 0.15, c.w - 0.15, K.F + K.H - 0.2, drop=0.62, strips=4)
    for u in lanterns:
        K.wall_lantern(p, c.x0 + u, c.y0 - 0.09, (0, -1), z=K.F + 1.45)
    return p


def threshold(p, room, which, u0, u1):
    """A stone threshold across a doorway, bridging the two floors."""
    axis, origin, inward, length = room.frame(which)
    M, s = K.along(axis, origin, inward)
    p.box(((u0 + u1) / 2, 0, K.F - 0.015), (u1 - u0 - 0.17, 0.2, 0.05), 'Stone', M=M, r=0.012)


def lantern_post(p, x, y, h=1.05):
    """立灯: a square paper lantern box on a timber post."""
    F = K.F
    p.box((x, y, F + 0.06), (0.26, 0.26, 0.12), 'Timber', r=0.02)
    p.box((x, y, F + h / 2), (0.1, 0.1, h), 'Timber')
    z0 = F + h
    p.box((x, y, z0 + 0.02), (0.34, 0.34, 0.04), 'Timber')
    p.box((x, y, z0 + 0.22), (0.25, 0.25, 0.36), 'Paper')
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.box((x + sx * 0.135, y + sy * 0.135, z0 + 0.22), (0.04, 0.04, 0.4), 'Timber')
    p.box((x, y, z0 + 0.44), (0.4, 0.4, 0.05), 'Timber')
    p.box((x, y, z0 + 0.5), (0.18, 0.18, 0.07), 'Timber')


# ================================================================= the 二楼 and the 雅间

def under_floor(name, grp, x0, x1, y0, y1, ztop, runs=(), ext_r=0.1):
    """The ground storey under the 二楼 (the back of the building): its plinth and timber-framed plaster walls up to
    the slab on the stretches the camera can see. runs: [(face, a, b)], face F (along y = y0 + 0.1, a/b in x) or R
    (along x = x1, a/b in y)."""
    F = K.F
    p = Prop(name, grp, ((x0 + x1) / 2, (y0 + y1) / 2, 0), rmax=0.03)
    p.bx(x0 - 0.1, x1 + ext_r, y0 - 0.02, y1 + 0.1, 0, 0.22, 'Stone')
    p.bx(x0 - 0.08, x1 + ext_r - 0.02 * (ext_r > 0), y0, y1 + 0.08, 0.22, F - 0.04, 'Stone')
    for face, a0, b0 in runs:
        if face == 'F':
            M, s = K.along('x', (a0, y0 + 0.1), 1)
        else:
            M, s = K.along('y', (x1, a0), -1)
        L = b0 - a0
        n = max(1, round(L / 1.8))
        for k in range(n + 1):
            p.box((L * k / n, 0, F - 0.04 + (ztop - F + 0.04) / 2), (0.17, 0.17, ztop - F + 0.04), 'Timber', M=M)
        for k in range(n):
            a, b = L * k / n + 0.085, L * (k + 1) / n - 0.085
            p.box(((a + b) / 2, -0.01 * s, (F + ztop) / 2), (b - a, 0.06, ztop - F), 'Plaster', M=M)
            p.box(((a + b) / 2, 0, F + 0.03), (b - a, 0.11, 0.14), 'Timber', M=M)
            p.box(((a + b) / 2, 0, ztop - 0.08), (b - a, 0.12, 0.12), 'Timber', M=M)
    return p


def slab(name, room, thick=0.3, ext=0.1):
    """The 二楼's deck: a stone-faced slab (the art's pale band along its edges) the boards lie on."""
    z1 = room.f - 0.04
    p = Prop(name, room.grp, ((room.x0 + room.x1) / 2, (room.y0 + room.y1) / 2, room.f - thick), rmax=0.03)
    p.bx(room.x0 - ext, room.x1 + ext, room.y0 - ext, room.y1 + ext, room.f - thick, z1, 'Stone', open_bottom=False)
    p.bx(room.x0 - ext - 0.03, room.x1 + ext + 0.03, room.y0 - ext - 0.03, room.y1 + ext + 0.03, room.f - thick - 0.08,
         room.f - thick, 'Timber', open_bottom=False)                     # the beam it rests on
    return p


def rug(p, x0, x1, y0, y1, border=0.12):
    """地毯: a flat cloth on the boards with a darker border band."""
    F = K.F
    p.bx(x0, x1, y0, y1, F + 0.008, F + 0.016, 'Cushion', open_bottom=True, top_only=True, r=0.004)
    for a0, a1, b0, b1 in ((x0, x1, y0, y0 + border), (x0, x1, y1 - border, y1), (x0, x0 + border, y0 + border, y1 - border),
                           (x1 - border, x1, y0 + border, y1 - border)):
        p.bx(a0 + 0.01, a1 - 0.01, b0 + 0.01, b1 - 0.01, F + 0.016, F + 0.02, 'Leaf', open_bottom=True, top_only=True,
             r=0.002)


def screen_wall(p, x0, y0, x1, y1, h=1.85, door=None, step=1.05, mat='Cushion', drapes=True):
    """屏风墙: a straight run of timber-framed painted screens from (x0, y0) to (x1, y1), along x or y. door: (t0, t1),
    metres along the run, left open under a head beam with tied-back drapes (the art's 雅间 doorway)."""
    F = K.F
    L = math.hypot(x1 - x0, y1 - y0)
    yaw = math.atan2(y1 - y0, x1 - x0)
    M = Matrix.Translation((x0, y0, 0)) @ Matrix.Rotation(yaw, 4, 'Z')     # local u along the run
    stops = [0.0, L]
    if door:
        stops += list(door)
    stops = sorted(set(round(t, 4) for t in stops))
    spans = [(a, b) for a, b in zip(stops, stops[1:]) if not (door and abs(a - door[0]) < 1e-4)]
    posts = set(stops)
    for a, b in spans:
        n = max(1, round((b - a) / step))
        for k in range(1, n):
            posts.add(a + (b - a) * k / n)
    for t in sorted(posts):
        p.box((t, 0, F + (h + 0.06) / 2), (0.08, 0.08, h + 0.06), 'Timber', M=M)
        p.box((t, 0, F + h + 0.08), (0.11, 0.11, 0.04), 'Timber', M=M)
    ps = sorted(posts)
    for a, b in zip(ps, ps[1:]):
        if door and a >= door[0] - 1e-4 and b <= door[1] + 1e-4:
            continue
        w = b - a - 0.08
        c = (a + b) / 2
        p.box((c, 0, F + 0.08), (w, 0.05, 0.08), 'Timber', M=M)                         # bottom rail
        p.box((c, 0, F + h - 0.04), (w, 0.05, 0.07), 'Timber', M=M)                     # top rail
        p.box((c, 0, F + 0.33), (w, 0.04, 0.04), 'Timber', M=M)
        p.box((c, 0, (F + 0.35 + F + h - 0.075) / 2), (w, 0.025, h - 0.43), mat, M=M)   # the painted panel
        p.box((c, 0, F + 0.22), (w, 0.03, 0.18), 'Wood', M=M)                          # base board
    if door:
        a, b = door
        p.box(((a + b) / 2, 0, F + h - 0.04), (b - a, 0.08, 0.08), 'Timber', M=M)      # head beam
        if drapes:
            for t, sg in ((a + 0.04, 1), (b - 0.04, -1)):
                for k in range(3):                                                    # gathered, tied back
                    z0 = F + 0.05 + k * 0.55
                    wid = 0.26 - 0.08 * k if k < 2 else 0.16
                    p.box((t + sg * (0.04 + wid / 2), 0.06, z0 + 0.27), (wid, 0.05, 0.56), 'Paper', M=M, r=0.012)
                p.box((t + sg * 0.12, 0.06, F + h - 0.2), (0.24, 0.05, 0.3), 'Paper', M=M, r=0.012)
    return M


def tile_hood(p, cx, cy, L, D, z_top, z_stove, drop=0.3):
    """瓦檐: a small tiled roof over a stove, along +x with the wall at +y: rafters on two brackets and rows of
    grey tiles sloping down toward the room."""
    y1 = cy + D / 2
    run = D
    pitch = math.atan2(drop, run)
    S = Matrix.Translation((cx, y1 - run / 2, z_top - drop / 2)) @ Matrix.Rotation(pitch, 4, 'X')
    p.box((0, 0, -0.03), (L, math.hypot(run, drop), 0.05), 'Timber', M=S)              # roof boards
    nt = max(4, round(L / 0.2))
    for k in range(nt):                                                              # tile courses (筒瓦)
        u = -L / 2 + (k + 0.5) * L / nt
        p.box((u, 0, 0.03), (L / nt - 0.03, math.hypot(run, drop) + 0.02, 0.06), 'Iron', M=S, r=0.025)
    p.box((0, -math.hypot(run, drop) / 2, 0.05), (L + 0.08, 0.1, 0.08), 'Iron', M=S)  # eave
    p.box((0, math.hypot(run, drop) / 2 - 0.05, 0.1), (L + 0.08, 0.12, 0.1), 'Iron', M=S)   # ridge against the wall
    for sg in (-1, 1):                                                              # posts on the stove's top
        x = cx + sg * (L / 2 - 0.2)
        p.bx(x - 0.04, x + 0.04, y1 - run + 0.04, y1 - run + 0.12, z_stove, z_top - drop - 0.02, 'Timber')


def crate(p, cx, cy, L, D, h=0.62, fill='Straw'):
    """A slatted timber crate with a heaped sack (rice) in it."""
    F = K.F
    x0, x1, y0, y1 = cx - L / 2, cx + L / 2, cy - D / 2, cy + D / 2
    for x in (x0 + 0.03, x1 - 0.03):
        for y in (y0 + 0.03, y1 - 0.03):
            p.box((x, y, F + h / 2), (0.06, 0.06, h), 'Wood')
    for z in (F + 0.12, F + h * 0.55, F + h - 0.05):
        p.bx(x0, x1, y0 + 0.01, y0 + 0.04, z - 0.04, z + 0.04, 'Wood')
        p.bx(x0, x1, y1 - 0.04, y1 - 0.01, z - 0.04, z + 0.04, 'Wood')
        p.bx(x0 + 0.01, x0 + 0.04, y0 + 0.04, y1 - 0.04, z - 0.04, z + 0.04, 'Wood')
        p.bx(x1 - 0.04, x1 - 0.01, y0 + 0.04, y1 - 0.04, z - 0.04, z + 0.04, 'Wood')
    p.bx(x0 + 0.04, x1 - 0.04, y0 + 0.04, y1 - 0.04, F + 0.05, F + 0.09, 'Wood')
    p.blob((cx, cy, F + h - 0.05), min(L, D) * 0.42, fill, (L / min(L, D), D / min(L, D), 0.7), segs=(10, 6))


# ================================================================= pieces for the larger shops (四级, 五级)

@contextmanager
def turned(p, x, y, deg):
    """Everything added to p inside the block is turned `deg` degrees about (x, y): one prop built of parts facing
    different ways (an L-shaped stove)."""
    saved = p.off
    p.off = saved @ Matrix.Translation((x, y, 0)) @ Matrix.Rotation(math.radians(deg), 4, 'Z') @ \
        Matrix.Translation((-x, -y, 0))
    try:
        yield
    finally:
        p.off = saved


def walkway(name, grp, x0, x1, y0, y1, steps_=()):
    """A raised stone walkway at floor height along the outside of a building (to an outside stair), with kerb
    stones and steps down [(side, u0, u1, n)] as for a room's plinth."""
    r = Room(grp, x0, y0, x1 - x0, y1 - y0)
    ROOMS.remove(r)                                  # not a room for the walkway check
    p = plinth(name, r, kerbs='RF', steps_=steps_, ext=(-0.02, 0.1, 0.1, 0.1),
               gaps=[(s_, a - 0.05, b + 0.05) for s_, a, b, _ in steps_])
    p.bx(x0 + 0.02, x1 - 0.17, y0 + 0.17, y1 - 0.02, K.F - 0.04, K.F + 0.008, 'Tile', open_bottom=True,
         top_only=True)                                                  # its paving
    return p


def outside_stair(name, grp, x, y0, run, rise, width=0.85, landing=0.9, deck_x=None):
    """An outside stair climbing +y from (x, y0) (the middle of its bottom step), the handrail on its outer (+x) side
    and a plain stringer against the building; its top landing reaches over to the deck's edge at deck_x."""
    p = stair(name, grp, x, y0, (0, 1), width, run, rise, rail=-1, wall_side=+1, landing=landing)
    if deck_x is not None:                                                    # plank bridging to the deck
        p.bx(deck_x + 0.02, x - width / 2 + 0.02, y0 + run + 0.03, y0 + run + landing - 0.03, K.F + rise - 0.05,
             K.F + rise + 0.024, 'Wood', open_bottom=False)
    return p


def wall_shelf(p, room, which, u0, u1, z, items=(), depth=0.26):
    """A plank shelf on two brackets against a wall, with jars, bowls and baskets [(kind, u, r)] on it."""
    (x0, y0), (nx, ny) = room.on_side(which, u0, 0.09)
    (x1, y1), _ = room.on_side(which, u1, 0.09)
    if which in 'LR':
        xa, xb = sorted((x0, x0 + nx * depth))
        p.bx(xa, xb, min(y0, y1), max(y0, y1), z - 0.04, z, 'Wood')
        for yy in (min(y0, y1) + 0.12, max(y0, y1) - 0.12):
            p.bx(xa, xb, yy - 0.02, yy + 0.02, z - 0.22, z - 0.04, 'Wood')
    else:
        ya, yb = sorted((y0, y0 + ny * depth))
        p.bx(min(x0, x1), max(x0, x1), ya, yb, z - 0.04, z, 'Wood')
        for xx in (min(x0, x1) + 0.12, max(x0, x1) - 0.12):
            p.bx(xx - 0.02, xx + 0.02, ya, yb, z - 0.22, z - 0.04, 'Wood')
    for kind, u, r in items:
        (x, y), _ = room.on_side(which, u, 0.09 + depth / 2)
        if kind == 'jar':
            jar(p, x, y, z, r, r * 2.3, 'Glaze')
        elif kind == 'pale':
            jar(p, x, y, z, r, r * 2.4, 'Ceramic', lid=False)
        elif kind == 'bowls':
            for s_ in range(2):
                K.bowl(p, x, y, z + s_ * 0.045, r)
        elif kind == 'basket':
            K.basket(p, x, y, z, r, 0.1, fill='Veg')


def hang_strings(p, room, which, us, z, mats=('Chili', 'Straw', 'Chili')):
    """Strings of chillies and garlic hung on a wall from a rail."""
    for u, mat in zip(us, mats):
        (x, y), _ = room.on_side(which, u, 0.06)
        for j in range(5):
            p.blob((x, y, z - j * 0.1), 0.045, mat, (1, 1, 1.4))
    (xa, ya), _ = room.on_side(which, min(us) - 0.12, 0.05)
    (xb, yb), _ = room.on_side(which, max(us) + 0.12, 0.05)
    p.bx(min(xa, xb) - 0.02, max(xa, xb) + 0.02, min(ya, yb) - 0.02, max(ya, yb) + 0.02, z + 0.05, z + 0.09,
         'Timber')


def pingfeng(p, x0, y0, x1, y1, h=1.6):
    """屏风: a free-standing folding screen (painted panels in timber frames) from (x0, y0) to (x1, y1)."""
    screen_wall(p, x0, y0, x1, y1, h=h, step=0.6, drapes=False)


def stand(p, x, y, w=0.45, d=0.4, h=0.7, top=None):
    """A small square stand (花几 / 茶几) with a teapot and cups, or a basket of greens."""
    F = K.F
    p.bx(x - w / 2, x + w / 2, y - d / 2, y + d / 2, F + h - 0.04, F + h, 'Wood')
    for sx in (-1, 1):
        for sy in (-1, 1):
            p.box((x + sx * (w / 2 - 0.04), y + sy * (d / 2 - 0.04), F + (h - 0.04) / 2), (0.05, 0.05, h - 0.04), 'Wood')
    p.bx(x - w / 2 + 0.04, x + w / 2 - 0.04, y - d / 2 + 0.04, y + d / 2 - 0.04, F + 0.1, F + 0.13, 'Wood')
    if top == 'tea':
        teapot(p, x - 0.06, y, F + h, 0.055)
        cup(p, x + 0.1, y - 0.05, F + h)
        cup(p, x + 0.1, y + 0.07, F + h)
    elif top == 'basket':
        K.basket(p, x, y, F + h, min(w, d) * 0.4, 0.1, fill='Veg')
    elif top == 'jar':
        jar(p, x, y, F + h, min(w, d) * 0.3, min(w, d) * 0.7, 'Glaze')


def queue(spots, grp):
    for i, (x, y, z) in enumerate(spots):
        K.marker(f'Spot_Queue_{i + 1}', (x, y, z), grp)


# ================================================================= 一级 · 初出茅庐 (大堂 3 桌)

def level_1():
    """初出茅庐·三桌食堂-2.png. The kitchen (left) and the hall (right) are joined by a short covered passage with a
    blue 门帘 along its front, behind the kitchen's lantern post. Read at about 0.014 m per art unit."""
    # ---------------- 后厨: 6.8 × 6.4, walls on the far sides, the right side cut low, the front open
    k = Room('Kitchen', 0.0, 0.0, 6.8, 6.4)
    plinth('K_Plinth', k, kerbs='F').finish()
    tile_floor('K_Floor', k, cell=0.56, split=0.15, margin=(0.09, 0.09, 0.2, 0.09))
    p = Prop('K_Walls', 'Kitchen', (0.0, k.y1, K.F), rmax=0.03)
    side(p, k, 'L', [0, 0.95, 2.9, 4.5, 6.4], ['plaster', 'plaster', 'window', 'plaster'],
         curtains=[(2.9, 4.5)], lanterns=[0.95])
    round_window(p, k, 'L', 2.0)
    side(p, k, 'B', [0, 2.65, 3.25, 5.0, 6.8], ['plaster', 'window', 'plaster', 'plaster'], skip=[0])
    for u, z in ((0.9, 1.3), (1.05, 1.25)):                       # strings of chillies and garlic by the corner
        for j in range(4):
            (x, y), _ = k.on_side('B', u, 0.06)
            p.blob((x, y, K.F + z + 0.3 - j * 0.1), 0.045, 'Chili' if u < 1 else 'Straw', (1, 1, 1.4))
    for j, u in enumerate((1.3, 1.5, 1.7)):                       # ladles and a strainer on a rail
        (x, y), _ = k.on_side('B', u, 0.05)
        p.bx(x - 0.015, x + 0.015, y - 0.02, y + 0.01, K.F + 1.1, K.F + 1.55, 'Wood')
        p.lathe([(0.05, -0.015), (0.05, 0.015)], (0, 0, 0), 'Iron' if j != 1 else 'Wood', n=10,
                M=Matrix.Translation((x, y - 0.02, K.F + 1.08)) @ Matrix.Rotation(math.radians(90), 4, 'X'))
    (x, y), _ = k.on_side('B', 1.25, 0.04)
    p.bx(x - 0.55, x + 0.55, y - 0.03, y + 0.01, K.F + 1.58, K.F + 1.62, 'Timber')
    (x, y), _ = k.on_side('B', 2.0, 0.03)                          # round sieve hung on the wall
    p.lathe([(0.24, -0.02), (0.24, 0.02), (0.21, 0.02)], (0, 0, 0), 'Straw', n=16, cap_top=False,
            M=Matrix.Translation((x, y - 0.02, K.F + 1.35)) @ Matrix.Rotation(math.radians(90), 4, 'X'))
    side(p, k, 'R', [0, 0.45, 1.85, 2.7, 4.6, 5.9, 6.4], ['plaster', 'window', 'plaster', 'window', 'opening',
                                                          'plaster'], h=1.25, skip=[6.4], tall={4.6: K.H, 5.9: K.H})
    p.finish()
    rails = Prop('K_Railings', 'Kitchen', (3.4, 0.0, K.F), rmax=0.02)
    K.railing(rails, 0.65, -0.02, 1.4, -0.02, posts=1)
    K.railing(rails, 6.0, -0.02, 6.55, -0.02, posts=1)
    rails.finish()

    x, y, L, D, t = k.against('L', 2.7, 6.28, 0.72)                    # 灶台 along the left wall: three woks
    p = Prop('K_ZaoTai', 'Kitchen', (x, y, K.F), rmax=0.03, turn=t)
    stove(p, x, y, L, D, woks=[-0.95, 0.1, 1.3])
    p.finish()
    p = Prop('K_ShuiGang', 'Kitchen', (0.5, 1.0, K.F), rmax=0.02)     # stone water jar in the corner
    water_jar(p, 0.5, 1.0, 0.4, 0.78)
    p.finish()
    x, y, L, D, t = k.against('L', 1.6, 2.6, 0.55)                     # firewood between the jar and the stove
    p = Prop('K_ChaiDui', 'Kitchen', (x, y, K.F), rmax=0.02, turn=t)
    firewood(p, x, y, L, D)
    p.finish()
    p = Prop('K_AnTai', 'Kitchen', (3.8, 3.55, K.F), rmax=0.025)       # 案台: long, along x, in the middle
    work_table(p, 3.8, 3.55, 2.8, 1.25)
    p.finish()
    x, y, L, D, t = k.against('B', 1.3, 2.45, 0.42)                    # low counter with jars by the back corner
    p = Prop('K_Counter', 'Kitchen', (x, y, K.F), rmax=0.025, turn=t)
    cabinet(p, x, y, L, D, h=0.72, doors=2, top=[('jar', -0.35, 0.09), ('pale', -0.12, 0.08), ('basket', 0.25, 0.15)])
    p.finish()
    x, y, L, D, t = k.against('B', 3.3, 4.5, 0.42)                     # 碗柜: jars and bowls
    p = Prop('K_WanGui', 'Kitchen', (x, y, K.F), rmax=0.02, turn=t)
    shelf_unit(p, x, y, L, D, Ht=1.95, base=0.6, tiers=3)
    p.finish()
    x, y, L, D, t = k.against('B', 4.6, 5.85, 0.45)                    # cabinet with two steamers (蒸笼)
    p = Prop('K_ZhengLong', 'Kitchen', (x, y, K.F), rmax=0.025, turn=t)
    cabinet(p, x, y, L, D, h=0.8, doors=2, top=[('steamer', -0.3, 0.26), ('steamer', 0.32, 0.24)])
    p.finish()
    x, y, L, D, t = k.against('F', 3.25, 4.6, 0.42, gap=0.1)            # bowl rack along the open front
    p = Prop('K_WanJia', 'Kitchen', (x, y, K.F), rmax=0.02, turn=t)
    open_rack(p, x, y, L, D, h=0.85, tiers=2)
    p.finish()
    x, y, L, D, t = k.against('F', 4.7, 5.95, 0.42, gap=0.1)            # stand with jars
    p = Prop('K_TanJia', 'Kitchen', (x, y, K.F), rmax=0.02, turn=t)
    open_rack(p, x, y, L, D, h=0.75, tiers=2, fill='jars')
    p.finish()
    stones('K_Path', 'Kitchen', [(2.1, -0.45, 0.6, 0.4), (1.5, -0.95, 0.55, 0.4), (2.25, -1.1, 0.45, 0.36),
                                 (1.0, -1.5, 0.5, 0.38), (1.65, -1.65, 0.5, 0.36)])

    # ---------------- 走廊: 3.4 × 1.3 covered passage behind the kitchen's lantern post, from the kitchen's door to the
    # hall's; its 门帘 hangs along the open front, whose steps come down into the nook between the two buildings
    c = Room('Corridor', k.x1, 4.6, 3.4, 1.3)
    corridor(c, (0.7, 2.7), breaks=[0, 1.15, 2.25, 3.4]).finish()

    # ---------------- 前堂: 6.8 × 7.5, its front 1.3 m ahead of the passage; the door from the passage in its left wall
    h = Room('Hall', c.x1, 3.3, 6.8, 7.5)
    plinth('D_Plinth', h, kerbs='', steps_=[('F', 2.65, 4.55, 3)]).finish()
    plank_floor('D_Floor', h, along='y', margin=(0.06, 0.06, 0.06, 0.06))
    p = Prop('D_Walls', 'Hall', (h.x0, h.y1, K.F), rmax=0.03)
    side(p, h, 'L', [0, 1.3, 2.6, 4.5, 6.6, 7.5], ['plaster', 'opening', 'plaster', 'window', 'plaster'],
         curtains=[(4.5, 6.6)], lanterns=[1.3, 4.5, 6.6], brackets=[1.3, 2.6], scrolls=[(0.65, 0.5)])
    M, s = K.along(*h.frame('L')[:3])
    K.curtain(p, M, s, 1.4, 2.5, K.F + K.H - 0.42, drop=0.62, strips=2)                  # 门帘 on the passage door
    side(p, h, 'B', [0, 1.2, 3.25, 5.7, 6.8], ['plaster', 'plaster', 'plaster', 'plaster'], skip=[0],
         scrolls=[(0.6, 0.5), (2.55, 0.62), (4.7, 0.55)])
    side(p, h, 'F', [0, 1.1, 2.6, 4.6, 6.8], ['plaster', 'plaster', None, 'plaster'], h=0.85, skip=[0, 2.6, 4.6])
    side(p, h, 'R', [0, 2.2, 4.65, 7.5], ['plaster', 'plaster', 'plaster'], h=0.85, skip=[0, 7.5])
    door_frame(p, h, 'F', 2.6, 4.6, K.F + 1.75, drop=0.85, lantern_out=True)
    p.finish()
    x, y, L, D, t = h.against('B', 1.45, 3.65, 0.4)                     # sideboard with jars
    p = Prop('D_Cabinet', 'Hall', (x, y, K.F), rmax=0.025, turn=t)
    cabinet(p, x, y, L, D, h=0.8, doors=4, top=[('jar', -0.8, 0.1), ('pale', -0.45, 0.08), ('jar', 0.55, 0.11),
                                                ('pale', 0.85, 0.07)])
    p.finish()
    for i, (u0, u1) in enumerate(((2.8, 4.3), (6.25, 7.3))):              # low benches along the left wall
        x, y, L, D, t = h.against('L', u0, u1, 0.36)
        p = Prop(f'D_Bench_{i + 1}', 'Hall', (x, y, K.F), rmax=0.02, turn=t)
        bench(p, x, y, L, D, jars=3)
        p.finish()
    x0, y0 = h.at(6.15, 6.88)                                           # stair up along the back wall's right end
    stair('D_Stairs', 'Hall', x0, y0, (-1, 0), 0.85, 2.0, 2.0, rail=+1, wall_side=-1, landing=0.3).finish()
    for n, (u, v) in ((1, (2.3, 2.4)), (2, (1.6, 5.45)), (3, (4.6, 4.7))):
        dining(n, 'Hall', *h.at(u, v))
    stones('D_Path', 'Hall', [(h.x0 + 3.6, h.y0 - 1.35, 0.95, 0.45), (h.x0 + 3.1, h.y0 - 1.9, 0.7, 0.42),
                              (h.x0 + 3.85, h.y0 - 2.0, 0.5, 0.4), (h.x0 + 2.7, h.y0 - 2.5, 0.6, 0.4),
                              (h.x0 + 3.35, h.y0 - 2.6, 0.5, 0.38), (h.x0 + 2.3, h.y0 - 3.1, 0.55, 0.4)])
    queue([(h.x0 + 3.6, h.y0 - 1.35, 0.05), (h.x0 + 3.1, h.y0 - 1.9, 0.05), (h.x0 + 3.85, h.y0 - 2.0, 0.05),
           (h.x0 + 2.7, h.y0 - 2.5, 0.05)], 'Hall')
    return [('closeup_kitchen.png', 'K_AnTai'), ('closeup_hall.png', 'D_Table_1'), ('closeup_stairs.png', 'D_Stairs'),
            ('closeup_corridor.png', 'C_Walls')]


# ================================================================= 二级 · 市井买卖 (大堂 4 桌)

def tub(p, x, y, r=0.32, h=0.62, fill='Water'):
    """木桶: a staved wooden tub with hoops."""
    F = K.F
    prof = [(r * 0.9, F), (r, F + h * 0.14), (r * 1.03, F + h * 0.14), (r * 1.03, F + h * 0.22), (r * 1.06, F + h * 0.62),
            (r * 1.09, F + h * 0.62), (r * 1.09, F + h * 0.72), (r * 1.12, F + h), (r * 1.02, F + h),
            (r * 0.98, F + h * 0.2)]
    p.lathe(prof, (x, y, 0), 'Wood', n=16, cap_top=False, rims=[0, 8])
    p.lathe([(r * 1.0, F + h * 0.86)], (x, y, 0), fill, n=16, cap_bottom=False)


def level_2():
    """餐厅增添第四张方桌-8.png. The kitchen (left, open on its near sides) has a five-wok range with a chimney along its
    left wall; a covered passage with a 门帘 front joins its back-right corner to the hall's left wall, as in the 初始
    level; the hall (right) has its tables on a 2 x 2 grid, open railed sides with steps up on both. About 0.016 m per
    art unit; the front row stands 0.5 m further from the railing than the art draws it, to keep a walkway."""
    # ---------------- 后厨: 6.8 x 6.3, walls on the far sides, the near sides open over a stone kerb
    k = Room('Kitchen', 0.0, 0.0, 6.8, 6.3)
    plinth('K_Plinth', k, kerbs='FR', gaps=[('R', 5.0, 6.3)]).finish()
    tile_floor('K_Floor', k, cell=0.63, split=0.15, margin=(0.09, 0.19, 0.2, 0.09))
    p = Prop('K_Walls', 'Kitchen', (0.0, k.y1, K.F), rmax=0.03)
    side(p, k, 'L', [0, 1.0, 2.6, 4.3, 5.9, 6.3], ['plaster', 'plaster', 'plaster', 'window', 'plaster'],
         curtains=[(4.3, 5.9)])
    side(p, k, 'B', [0, 0.35, 1.6, 3.25, 4.45, 6.0, 6.8], ['plaster', 'window', 'plaster', 'plaster', 'plaster',
                                                          'plaster'], skip=[0], curtains=[(0.35, 1.6)],
         lanterns=[0.35, 6.0])
    for j, u in enumerate((1.75, 1.95, 2.15)):                      # ladles on a rail
        (x, y), _ = k.on_side('B', u, 0.05)
        p.bx(x - 0.015, x + 0.015, y - 0.02, y + 0.01, K.F + 1.1, K.F + 1.55, 'Wood')
        p.lathe([(0.05, -0.015), (0.05, 0.015)], (0, 0, 0), 'Iron' if j != 1 else 'Wood', n=10,
                M=Matrix.Translation((x, y - 0.02, K.F + 1.08)) @ Matrix.Rotation(math.radians(90), 4, 'X'))
    (x, y), _ = k.on_side('B', 1.95, 0.04)
    p.bx(x - 0.35, x + 0.35, y - 0.03, y + 0.01, K.F + 1.58, K.F + 1.62, 'Timber')
    (x, y), _ = k.on_side('B', 2.75, 0.03)                          # round sieve
    p.lathe([(0.24, -0.02), (0.24, 0.02), (0.21, 0.02)], (0, 0, 0), 'Straw', n=16, cap_top=False,
            M=Matrix.Translation((x, y - 0.02, K.F + 1.35)) @ Matrix.Rotation(math.radians(90), 4, 'X'))
    for j, v in enumerate((2.75, 3.0, 3.25)):                       # pans and a string of chillies on the left wall
        (x, y), _ = k.on_side('L', v, 0.04)
        if j == 1:
            for i in range(5):
                p.blob((x + 0.02, y, K.F + 1.7 - i * 0.1), 0.045, 'Chili', (1, 1, 1.4))
        else:
            p.lathe([(0.13, -0.015), (0.13, 0.015), (0.11, 0.015)], (0, 0, 0), 'Iron', n=14, cap_top=False,
                    M=Matrix.Translation((x + 0.03, y, K.F + 1.4)) @ Matrix.Rotation(math.radians(90), 4, 'Y'))
            p.bx(x + 0.02, x + 0.05, y - 0.02, y + 0.02, K.F + 1.53, K.F + 1.8, 'Wood')
    p.finish()

    x, y, L, D, t = k.against('L', 1.25, 6.05, 0.85)                   # 灶台: five woks and a chimney at its end
    p = Prop('K_ZaoTai', 'Kitchen', (x, y, K.F), rmax=0.03, turn=t)
    stove(p, x, y, L, D, woks=[v - y for v in (2.15, 3.05, 3.95, 4.85, 5.7)], chimney=1.5 - y)
    p.finish()
    p = Prop('K_ShuiGang', 'Kitchen', (0.55, 0.55, K.F), rmax=0.02)
    water_jar(p, 0.55, 0.55, 0.42, 0.8)
    p.finish()
    p = Prop('K_ChaiDui', 'Kitchen', (1.35, 0.68, K.F), rmax=0.02)   # firewood beside the jar, cut ends to the front
    firewood(p, 1.35, 0.68, 0.6, 0.8)
    p.finish()
    p = Prop('K_AnTai', 'Kitchen', (4.8, 3.45, K.F), rmax=0.025)
    work_table(p, 4.8, 3.45, 2.8, 1.4)
    p.finish()
    x, y, L, D, t = k.against('F', 3.25, 5.85, 0.48, gap=0.18)          # long cabinet along the open front
    p = Prop('K_Guizi', 'Kitchen', (x, y, K.F), rmax=0.025, turn=t)
    cabinet(p, x, y, L, D, h=0.78, doors=4, top=[('basket', -0.95, 0.14), ('bowls', -0.45, 0.1), ('pale', 0.0, 0.07),
                                                ('jar', 0.4, 0.08), ('bowls', 0.9, 0.09)])
    p.finish()
    p = Prop('K_MuTong', 'Kitchen', (6.25, 1.25, K.F), rmax=0.02)     # wooden tub by the front corner
    tub(p, 6.25, 1.25)
    p.finish()
    x, y, L, D, t = k.against('B', 1.75, 3.15, 0.45)                    # low counter with bowls
    p = Prop('K_Counter', 'Kitchen', (x, y, K.F), rmax=0.025, turn=t)
    cabinet(p, x, y, L, D, h=0.75, doors=2, top=[('basket', -0.45, 0.14), ('bowls', 0.0, 0.1), ('bowls', 0.42, 0.1)])
    p.finish()
    x, y, L, D, t = k.against('B', 3.3, 4.25, 0.52)                     # stone sink
    p = Prop('K_ShuiChi', 'Kitchen', (x, y, K.F), rmax=0.03, turn=t)
    p.bx(x - L / 2 + 0.04, x + L / 2 - 0.04, y - D / 2 + 0.03, y + D / 2 - 0.03, K.F, K.F + 0.6, 'Stone')
    p.bx(x - L / 2, x + L / 2, y - D / 2, y + D / 2, K.F + 0.6, K.F + 0.8, 'Stone')
    p.bx(x - L / 2 + 0.07, x + L / 2 - 0.07, y - D / 2 + 0.07, y + D / 2 - 0.07, K.F + 0.74, K.F + 0.79, 'Water')
    p.finish()
    x, y, L, D, t = k.against('B', 4.4, 5.85, 0.45)                     # 碗柜
    p = Prop('K_WanGui', 'Kitchen', (x, y, K.F), rmax=0.02, turn=t)
    shelf_unit(p, x, y, L, D, Ht=1.95, base=0.6, tiers=3)
    p.finish()
    x, y, L, D, t = k.against('B', 6.08, 6.66, 0.5)                     # a big steamer on its stand
    p = Prop('K_ZhengLong', 'Kitchen', (x, y, K.F), rmax=0.025, turn=t)
    cabinet(p, x, y, L, D, h=0.62, doors=1, top=[('steamer', 0.0, 0.23)])
    p.finish()
    stones('K_Path', 'Kitchen', [(1.3, -0.5, 0.6, 0.42), (2.0, -0.6, 0.5, 0.4), (1.1, -1.1, 0.55, 0.4),
                                 (1.75, -1.2, 0.5, 0.38), (1.45, -1.75, 0.55, 0.4)])

    # ---------------- 走廊: 2.0 x 1.3 from the kitchen's back-right corner to the hall's left wall
    c = Room('Corridor', k.x1, 5.0, 2.0, 1.3)
    corridor(c, (0.3, 1.7), breaks=[0, 1.0, 2.0], lanterns=(0.0, 2.0), floor_left=-0.17, posts=[0.0]).finish()

    # ---------------- 前堂: 8.0 x 6.6, railed front sides with steps up on both
    h = Room('Hall', c.x1, 5.0, 8.0, 6.6)
    plinth('D_Plinth', h, kerbs='FR', gaps=[('F', 1.7, 4.3), ('R', 3.7, 5.35)],
           steps_=[('F', 1.75, 4.25, 3), ('R', 3.75, 5.3, 3)]).finish()
    plank_floor('D_Floor', h, along='y', margin=(0.06, 0.16, 0.16, 0.06))
    p = Prop('D_Walls', 'Hall', (h.x0, h.y1, K.F), rmax=0.03)
    side(p, h, 'L', [0, 1.3, 2.0, 3.6, 4.1, 5.7, 6.6], ['opening', 'plaster', 'window', 'plaster', 'window', 'plaster'],
         curtains=[(2.0, 3.6), (4.1, 5.7)], lanterns=[2.0, 5.7], brackets=[0, 1.3])
    M, s = K.along(*h.frame('L')[:3])
    K.curtain(p, M, s, 0.1, 1.2, K.F + K.H - 0.42, drop=0.62, strips=2)                  # 门帘 on the passage door
    threshold(p, h, 'L', 0.0, 1.3)
    side(p, h, 'B', [0, 0.6, 2.8, 4.0, 6.0, 8.0], ['plaster', 'window', 'plaster', 'window', 'plaster'], skip=[0],
         curtains=[(0.6, 2.8), (4.0, 6.0)], lanterns=[0.6, 2.8, 6.0], scrolls=[(7.0, 0.55)])
    p.finish()
    p = Prop('D_Railings', 'Hall', (h.x0 + 4.0, h.y0, K.F), rmax=0.02)
    K.railing(p, h.x0 + 0.25, h.y0 - 0.02, h.x0 + 1.62, h.y0 - 0.02, posts=1)
    K.railing(p, h.x0 + 4.38, h.y0 - 0.02, h.x0 + 7.6, h.y0 - 0.02, posts=3)
    K.railing(p, h.x1 - 0.02, h.y0 + 0.45, h.x1 - 0.02, h.y0 + 3.62, posts=3)
    K.railing(p, h.x1 - 0.02, h.y0 + 5.43, h.x1 - 0.02, h.y1 - 0.2, posts=1)
    lantern_post(p, h.x1 - 0.25, h.y0 + 0.25)                       # 立灯 at the front corner
    p.finish()
    x, y, L, D, t = h.against('B', 3.6, 6.3, 0.42)                     # sideboard with jars
    p = Prop('D_Cabinet', 'Hall', (x, y, K.F), rmax=0.025, turn=t)
    cabinet(p, x, y, L, D, h=0.8, doors=4, top=[('jar', -1.0, 0.1), ('pale', -0.65, 0.07), ('jar', 0.2, 0.09),
                                                ('pale', 0.75, 0.08), ('jar', 1.1, 0.1)])
    p.finish()
    # the 2 x 2 grid: 1 front-left (nearest the passage door), 2 back-left, 3 back-right, 4 front-right (the new one)
    for n, (u, v) in ((1, (3.15, 1.7)), (2, (2.28, 4.3)), (3, (5.39, 4.5)), (4, (5.66, 1.95))):
        dining(n, 'Hall', *h.at(u, v))
    pts = [(h.x0 + 2.5, h.y0 - 1.5, 0.95, 0.45), (h.x0 + 1.85, h.y0 - 2.05, 0.7, 0.42), (h.x0 + 2.75, h.y0 - 2.15, 0.5, 0.4),
           (h.x0 + 1.4, h.y0 - 2.65, 0.6, 0.4), (h.x0 + 2.15, h.y0 - 2.75, 0.5, 0.38), (h.x0 + 1.0, h.y0 - 3.25, 0.55, 0.4)]
    stones('D_Path', 'Hall', pts)
    queue([(x_, y_, 0.05) for x_, y_, _, _ in pts[:4]], 'Hall')
    return [('closeup_kitchen.png', 'K_ZaoTai'), ('closeup_hall.png', 'D_Table_1'), ('closeup_antai.png', 'K_AnTai'),
            ('closeup_corridor.png', 'C_Walls')]


# ================================================================= 三级 · 小有名气 (一楼 4 · 二楼散座 1 · 雅间 1)

def level_3():
    """水彩餐厅六桌布局改造-11.png. The hall at the front (left of the picture), with a 门帘 door in each near side and
    a stair up its back wall; the 二楼 behind it and above, its 散座 table on the left and the 雅间 closed by painted
    screens on the right; the kitchen to the right, its three woks under a tiled hood along its left wall, reached
    from the hall's back-right corner by a short corridor (as the art's 门帘 passage). About 0.022 m per art unit."""
    # ---------------- 一楼大堂: 7.4 × 7.35
    h = Room('Hall', 0.0, 0.0, 7.4, 7.35)
    plinth('D_Plinth', h, kerbs='', steps_=[('F', 2.8, 4.75, 3), ('R', 2.9, 4.85, 3)],
           ext=(0.1, 0.1, 0.1, -0.02)).finish()
    plank_floor('D_Floor', h, along='y', margin=(0.06, 0.06, 0.06, 0.06))
    p = Prop('D_Walls', 'Hall', (h.x0, h.y1, K.F), rmax=0.03)
    side(p, h, 'L', [0, 1.1, 3.5, 4.1, 5.9, 7.35], ['plaster', 'window', 'plaster', 'window', 'plaster'],
         curtains=[(1.1, 3.5), (4.1, 5.9)], lanterns=[1.1, 5.9])
    side(p, h, 'B', [0, 0.95, 3.6, 4.0, 5.1, 6.45, 7.4], ['plaster', 'plaster', 'plaster', 'plaster', 'plaster',
                                                          'plaster'], skip=[0], scrolls=[(4.55, 0.55)],
         lanterns=[4.0])
    side(p, h, 'F', [0, 1.4, 2.75, 4.8, 6.1, 7.4], ['plaster', 'plaster', None, 'plaster', 'plaster'], h=0.9,
         skip=[0, 2.75, 4.8])
    side(p, h, 'R', [0, 1.4, 2.85, 4.9, 6.05, 7.35], ['plaster', 'plaster', None, 'plaster', 'opening'], h=0.9,
         skip=[0, 2.85, 4.9, 7.35], tall={6.05: K.H})
    door_frame(p, h, 'F', 2.75, 4.8, K.F + 1.75, drop=0.85, lantern_out=True)
    door_frame(p, h, 'R', 2.85, 4.9, K.F + 1.75, drop=0.85, lantern_out=True)
    threshold(p, h, 'R', 6.05, 7.35)
    p.finish()
    x, y, L, D, t = h.against('B', 4.1, 5.0, 0.42)                       # cabinet with jars
    p = Prop('D_Cabinet', 'Hall', (x, y, K.F), rmax=0.025, turn=t)
    cabinet(p, x, y, L, D, h=0.78, doors=2, top=[('jar', -0.25, 0.09), ('pale', 0.2, 0.07)])
    p.finish()
    x, y, L, D, t = h.against('B', 5.2, 6.35, 0.42)                      # tall shelf of bowls and jars
    p = Prop('D_WanGui', 'Hall', (x, y, K.F), rmax=0.02, turn=t)
    shelf_unit(p, x, y, L, D, Ht=1.9, base=0.55, tiers=3, fill='bowls')
    p.finish()
    # stair up the back wall to the 二楼: climbs toward the back-left corner, then a landing bridges the wall top
    p = stair('D_Stairs', 'Hall', 3.5, 6.75, (-1, 0), 0.85, 2.6, F2 - F0, rail=+1, wall_side=-1, landing=0.8)
    p.bx(0.1, 0.9, 7.17, 7.25, F2 - 0.15, F2 + 0.02, 'Wood', open_bottom=False)      # onto the 二楼's slab edge
    p.finish()
    # tables: 1 back-right (nearest the corridor door), then by distance: 2 front-right, 3 back-left, 4 front-left
    for n, (u, v) in ((1, (5.4, 4.78)), (2, (5.33, 2.06)), (3, (2.44, 4.7)), (4, (2.37, 2.13))):
        dining(n, 'Hall', *h.at(u, v))
    pts = [(3.75, -1.45, 0.9, 0.45), (3.15, -2.0, 0.7, 0.42), (4.1, -2.1, 0.5, 0.4), (2.75, -2.6, 0.6, 0.4),
           (3.5, -2.7, 0.5, 0.38), (2.35, -3.15, 0.55, 0.4)]
    stones('D_Path', 'Hall', pts + [(8.85, 3.6, 0.45, 0.8), (9.4, 3.1, 0.42, 0.7), (9.95, 3.7, 0.4, 0.6)])
    queue([(x_, y_, 0.05) for x_, y_, _, _ in pts[:4]], 'Hall')

    # ---------------- 走廊: 1.6 × 1.3 at the hall's back-right corner, into the kitchen's left wall
    c = Room('Corridor', h.x1, h.y1 - 1.3, 1.6, 1.3)
    corridor(c, (0.15, 1.45), breaks=[0, 1.6], lanterns=(1.6,), ext=(-0.1, -0.1, 0.1, -0.02)).finish()

    # ---------------- 后厨: 8.9 × 7.6, to the right; door with 门帘 in its near right wall
    k = Room('Kitchen', c.x1, c.y0, 8.9, 7.6)
    plinth('K_Plinth', k, kerbs='F', steps_=[('R', 3.45, 4.85, 3)], ext=(-0.1, 0.1, 0.1, 0.1)).finish()
    tile_floor('K_Floor', k, cell=0.66, split=0.12, margin=(0.09, 0.09, 0.2, 0.09))
    p = Prop('K_Walls', 'Kitchen', (k.x0, k.y1, K.F), rmax=0.03)
    side(p, k, 'L', [0, 1.3, 2.2, 4.3, 6.4, 7.6], ['opening', 'plaster', 'plaster', 'plaster', 'plaster'],
         brackets=[0, 1.3], lanterns=[1.3])
    threshold(p, k, 'L', 0.0, 1.3)
    side(p, k, 'B', [0, 1.5, 3.3, 4.9, 6.5, 8.9], ['plaster', 'plaster', 'plaster', 'plaster', 'plaster'], skip=[0],
         lanterns=[1.5])
    for i in range(6):                                                     # rack of drying chillies over the counter
        (x, y), _ = k.on_side('B', 2.0 + i * 0.22, 0.05)
        for j in range(4):
            p.blob((x, y, K.F + 1.55 - j * 0.1), 0.045, 'Chili', (1, 1, 1.4))
    (x, y), _ = k.on_side('B', 2.55, 0.04)
    p.bx(x - 0.75, x + 0.75, y - 0.03, y + 0.01, K.F + 1.62, K.F + 1.67, 'Timber')
    side(p, k, 'R', [0, 1.6, 3.4, 4.9, 6.3, 7.6], ['plaster', 'plaster', None, 'plaster', 'plaster'], h=1.0,
         skip=[3.4, 4.9, 7.6])
    door_frame(p, k, 'R', 3.4, 4.9, K.F + 1.75, drop=0.8, strips=2, lantern_out=True)
    p.finish()
    p = Prop('K_Railings', 'Kitchen', (k.x0 + 4.0, k.y0, K.F), rmax=0.02)
    K.railing(p, k.x0 + 0.25, k.y0 - 0.02, k.x0 + 3.75, k.y0 - 0.02, posts=3)
    K.railing(p, k.x0 + 7.05, k.y0 - 0.02, k.x1 - 0.2, k.y0 - 0.02, posts=1)
    p.finish()
    x, y, L, D, t = k.against('L', 2.3, 6.35, 0.85)                       # 灶台 under its tiled hood: three woks
    p = Prop('K_ZaoTai', 'Kitchen', (x, y, K.F), rmax=0.03, turn=t)
    stove(p, x, y, L, D, woks=[k.y0 + v - y for v in (3.05, 4.3, 5.55)])
    tile_hood(p, x, y, L + 0.3, D - 0.04, K.F + 1.85, K.F + 0.8)
    p.finish()
    x, y, L, D, t = k.against('L', 1.45, 2.2, 0.6)                        # firewood by the stove's end
    p = Prop('K_ChaiDui', 'Kitchen', (x, y, K.F), rmax=0.02, turn=t)
    firewood(p, x, y, L, D)
    p.finish()
    p = Prop('K_AnTai', 'Kitchen', (k.x0 + 4.9, k.y0 + 3.3, K.F), rmax=0.025)
    work_table(p, k.x0 + 4.9, k.y0 + 3.3, 2.6, 1.6)
    p.finish()
    x, y, L, D, t = k.against('B', 1.6, 3.2, 0.5)                         # counter with a basin of greens
    p = Prop('K_Counter', 'Kitchen', (x, y, K.F), rmax=0.025, turn=t)
    cabinet(p, x, y, L, D, h=0.8, doors=3, top=[('basket', -0.45, 0.2), ('bowls', 0.2, 0.1), ('pale', 0.55, 0.07)])
    p.finish()
    x, y, L, D, t = k.against('B', 3.45, 4.65, 0.55)                      # stone sink
    p = Prop('K_ShuiChi', 'Kitchen', (x, y, K.F), rmax=0.03, turn=t)
    p.bx(x - L / 2 + 0.04, x + L / 2 - 0.04, y - D / 2 + 0.03, y + D / 2 - 0.03, K.F, K.F + 0.6, 'Stone')
    p.bx(x - L / 2, x + L / 2, y - D / 2, y + D / 2, K.F + 0.6, K.F + 0.8, 'Stone')
    p.bx(x - L / 2 + 0.07, x + L / 2 - 0.07, y - D / 2 + 0.07, y + D / 2 - 0.07, K.F + 0.74, K.F + 0.79, 'Water')
    p.finish()
    for i, (u0, u1, fill) in enumerate(((5.0, 6.4, 'mixed'), (6.6, 8.0, 'jars'))):   # shelves of jars and bowls
        x, y, L, D, t = k.against('B', u0, u1, 0.45)
        p = Prop('K_WanGui' if i == 0 else 'K_TanGui', 'Kitchen', (x, y, K.F), rmax=0.02, turn=t)
        shelf_unit(p, x, y, L, D, Ht=1.95, base=0.55, tiers=3, fill=fill)
        p.finish()
    x, y, L, D, t = k.against('R', 5.55, 6.85, 0.9)                       # rice crate in the back-right corner
    p = Prop('K_MiXiang', 'Kitchen', (x, y, K.F), rmax=0.02, turn=t)
    crate(p, x, y, L, D)
    p.finish()
    x, y, L, D, t = k.against('F', 3.95, 6.85, 0.42, gap=0.1)             # jar stand along the open front
    p = Prop('K_TanJia', 'Kitchen', (x, y, K.F), rmax=0.02, turn=t)
    open_rack(p, x, y, L, D, h=0.8, tiers=2, fill='jars')
    p.finish()
    p = Prop('K_MuTong', 'Kitchen', (k.x0 + 7.6, k.y0 + 1.0, K.F), rmax=0.02)
    tub(p, k.x0 + 7.6, k.y0 + 1.0)
    p.finish()
    stones('K_Path', 'Kitchen', [(k.x1 + 1.35, k.y0 + 4.1, 0.6, 0.45), (k.x1 + 1.85, k.y0 + 3.5, 0.5, 0.42),
                                 (k.x1 + 2.3, k.y0 + 4.2, 0.45, 0.4)])

    # ---------------- 二楼 behind and above the hall: 9.05 × 6.55, the 散座 on the left, the 雅间 on the right
    K.set_floor(F2)
    u = Room('Upstairs', -1.45, h.y1, 9.05, 6.55, f=F2)
    K.set_floor(F0)
    under_floor('U_Base', 'Upstairs', u.x0, u.x1, u.y0, u.y1, F2 - 0.38,
                runs=[('F', u.x0, h.x0 - 0.25), ('R', u.y0 + 0.2, u.y1)]).finish()
    K.set_floor(F2)
    slab('U_Slab', u).finish()
    plank_floor('U_Floor', u, along='y', margin=(0.06, 0.06, 0.06, 0.06),
                rugs=[(u.x0 + 0.65, u.x0 + 3.25, u.y0 + 1.75, u.y0 + 3.75),
                      (u.x0 + 4.75, u.x0 + 8.65, u.y0 + 0.45, u.y0 + 1.75)])
    p = Prop('U_Walls', 'Upstairs', (u.x0, u.y1, F2), rmax=0.03)
    side(p, u, 'L', [0, 1.0, 2.5, 3.0, 4.55, 5.05, 6.55], ['plaster', 'window', 'plaster', 'window', 'plaster', 'plaster'],
         curtains=[(1.0, 2.5), (3.0, 4.55)], lanterns=[1.0, 5.05])
    side(p, u, 'B', [0, 2.2, 4.5, 6.75, 9.05], ['plaster', 'plaster', 'plaster', 'plaster'], skip=[0],
         scrolls=[(6.25, 0.55)])
    p.finish()
    p = Prop('U_Railings', 'Upstairs', ((u.x0 + u.x1) / 2, u.y0, F2), rmax=0.02)
    K.railing(p, u.x0 + 0.25, u.y0 + 0.08, u.x0 + 1.42, u.y0 + 0.08, posts=1)
    K.railing(p, u.x0 + 2.45, u.y0 + 0.08, u.x1 - 0.3, u.y0 + 0.08, posts=6)
    K.railing(p, u.x1 - 0.08, u.y0 + 0.3, u.x1 - 0.08, u.y0 + 1.95, posts=2)
    lantern_post(p, u.x0 + 0.5, u.y0 + 0.5)
    p.finish()
    dining(5, 'Upstairs', u.x0 + 1.9, u.y0 + 2.75)
    # 雅间: painted screens on three sides, the 二楼's back wall behind; doorway with drapes in the front screen
    p = Prop('Y_Screens', 'Yajian', (u.x0 + 6.8, u.y0 + 2.1, F2), rmax=0.015)
    screen_wall(p, u.x0 + 4.5, u.y0 + 2.1, u.x1 - 0.12, u.y0 + 2.1, door=(0.35, 1.75))
    screen_wall(p, u.x0 + 4.5, u.y0 + 2.1, u.x0 + 4.5, u.y1 - 0.22)
    screen_wall(p, u.x1 - 0.12, u.y0 + 2.1, u.x1 - 0.12, u.y1 - 0.22)
    p.finish()
    x, y, L, D, t = (u.x0 + 7.45, u.y0 + 2.48, 0.9, 0.42, 0)                 # side table with a tea set
    p = Prop('Y_Side', 'Yajian', (x, y, F2), rmax=0.02)
    bench(p, x, y, L, D, h=0.62, jars=0)
    teapot(p, x - 0.15, y, F2 + 0.62, 0.06)
    for dx in (0.1, 0.25):
        cup(p, x + dx, y, F2 + 0.62)
    p.finish()
    dining(6, 'Yajian', u.x0 + 6.2, u.y0 + 4.5)
    K.set_floor(F0)
    return [('closeup_kitchen.png', 'K_ZaoTai'), ('closeup_hall.png', 'D_Table_1'), ('closeup_stairs.png', 'D_Stairs'),
            ('closeup_upstairs.png', 'D_Table_5'), ('closeup_yajian.png', 'D_Table_6')]


# ================================================================= 四级 · 声名鹊起 (一楼 4 · 二楼散座 3 · 雅间 1)

def level_4():
    """扩建双层餐厅八桌水彩图-12.png. The kitchen at the front left (three woks and a chimney along its left wall),
    its back-right corner meeting the hall's front-left corner as the art draws them, joined there by a covered
    passage with a 门帘 front into the front of the hall's left wall; the hall with its four tables on a staggered
    2 x 2 grid (read from their floor contact), a 门帘 entrance in its front facing the gap between the front tables
    and a door with steps in its right side; right of the hall's back-right corner a straight stair rising toward
    the building (-x, the art's flight) to the 二楼's front-right corner, its tall outer wall behind it; the 二楼
    behind the hall: three 散座 tables, and the 雅间 in its back closed by painted screens. About 0.014 m per art
    unit downstairs."""
    # ---------------- 一楼大堂: 8.4 x 7.6
    h = Room('Hall', 0.0, 0.0, 8.4, 7.6)
    plinth('D_Plinth', h, kerbs='FR', steps_=[('F', 4.25, 6.15, 3), ('R', 3.55, 4.85, 3)],
           gaps=[('F', 4.2, 6.2), ('R', 3.5, 4.9)], ext=(0.1, 0.1, 0.1, -0.02)).finish()
    plank_floor('D_Floor', h, along='y', margin=(0.06, 0.06, 0.06, 0.06))
    p = Prop('D_Walls', 'Hall', (h.x0, h.y1, K.F), rmax=0.03)
    side(p, h, 'L', [0, 1.3, 2.2, 3.9, 4.7, 6.4, 7.6], ['opening', 'plaster', 'window', 'plaster', 'window',
                                                        'plaster'], curtains=[(2.2, 3.9), (4.7, 6.4)],
         lanterns=[2.2, 6.4], brackets=[0, 1.3])
    M, s = K.along(*h.frame('L')[:3])
    K.curtain(p, M, s, 0.1, 1.2, K.F + K.H - 0.42, drop=0.62, strips=2)                 # 门帘 on the passage door
    threshold(p, h, 'L', 0.0, 1.3)
    side(p, h, 'B', [0, 0.9, 2.6, 3.4, 5.1, 7.3, 8.4], ['plaster', 'window', 'plaster', 'window', 'plaster',
                                                        'window'], skip=[0],
         curtains=[(0.9, 2.6), (3.4, 5.1), (7.3, 8.4)], lanterns=[2.6, 5.1])
    hang_scroll(p, h, 'B', 6.2, 0.55, z0=K.F + 1.15, z1=K.F + 1.85)
    side(p, h, 'F', [0, 1.4, 2.8, 4.2, 6.2, 7.3, 8.4], ['plaster', 'plaster', 'plaster', None, 'plaster', 'plaster'],
         h=0.9, skip=[0, 4.2, 6.2])
    side(p, h, 'R', [0, 1.75, 3.5, 4.9, 6.25, 7.6], ['plaster', 'plaster', None, 'plaster', 'plaster'], h=0.9,
         skip=[0, 3.5, 4.9, 7.6])
    door_frame(p, h, 'F', 4.2, 6.2, K.F + 1.75, drop=0.85, lantern_out=True)
    door_frame(p, h, 'R', 3.5, 4.9, K.F + 1.75, drop=0.8, strips=2, lantern_out=True)
    p.finish()
    x, y, L, D, t = h.against('B', 5.5, 7.1, 0.42)                       # sideboard with jars
    p = Prop('D_Cabinet', 'Hall', (x, y, K.F), rmax=0.025, turn=t)
    cabinet(p, x, y, L, D, h=0.8, doors=3, top=[('jar', -0.55, 0.1), ('pale', -0.15, 0.07), ('jar', 0.3, 0.09),
                                                ('pale', 0.6, 0.07)])
    p.finish()
    # the staggered 2 x 2, read from the tables' floor contact: 1 front-left (nearest the passage door), 2 back-left,
    # 3 front-right, 4 back-right
    for n, (x, y) in ((1, (3.96, 2.59)), (2, (4.17, 5.61)), (3, (6.6, 1.6)), (4, (6.8, 5.05))):
        dining(n, 'Hall', x, y)
    pts = [(5.3, -1.45, 0.9, 0.45), (4.75, -2.0, 0.7, 0.42), (5.7, -2.1, 0.5, 0.4), (4.35, -2.6, 0.6, 0.4),
           (5.1, -2.7, 0.5, 0.38), (3.95, -3.15, 0.55, 0.4)]
    stones('D_Path', 'Hall', pts + [(9.85, 4.0, 0.42, 0.75), (10.35, 3.45, 0.42, 0.7)])
    queue([(x_, y_, 0.05) for x_, y_, _, _ in pts[:4]], 'Hall')

    # ---------------- 走廊: 1.6 x 1.3 from the kitchen's back-right corner into the front of the hall's left wall
    c = Room('Corridor', -1.6, 0.0, 1.6, 1.3)
    corridor(c, (0.15, 1.45), breaks=[0, 1.6], lanterns=(0.0,)).finish()

    # ---------------- 后厨: 5.6 x 6.8 at the front left, open (railed) on its near sides
    k = Room('Kitchen', -7.2, -5.5, 5.6, 6.8)
    plinth('K_Plinth', k, kerbs='FR', gaps=[('R', 5.4, 6.9)]).finish()
    tile_floor('K_Floor', k, cell=0.6, split=0.15, margin=(0.09, 0.19, 0.2, 0.09))
    p = Prop('K_Walls', 'Kitchen', (k.x0, k.y1, K.F), rmax=0.03)
    side(p, k, 'L', [0, 1.3, 3.2, 5.0, 6.8], ['plaster', 'plaster', 'plaster', 'plaster'], lanterns=[1.3])
    side(p, k, 'B', [0, 1.7, 2.7, 4.2, 5.6], ['plaster', 'window', 'plaster', 'plaster'], skip=[0], lanterns=[1.7])
    hang_strings(p, k, 'B', (0.55, 0.7, 0.85), K.F + 1.75)
    (x, y), _ = k.on_side('B', 1.25, 0.03)                                   # round sieve
    p.lathe([(0.24, -0.02), (0.24, 0.02), (0.21, 0.02)], (0, 0, 0), 'Straw', n=16, cap_top=False,
            M=Matrix.Translation((x, y - 0.02, K.F + 1.4)) @ Matrix.Rotation(math.radians(90), 4, 'X'))
    p.finish()
    p = Prop('K_Railings', 'Kitchen', (k.x0 + 2.8, k.y0, K.F), rmax=0.02)
    K.railing(p, k.x0 + 0.25, k.y0 - 0.02, k.x0 + 2.45, k.y0 - 0.02, posts=2)
    K.railing(p, k.x0 + 4.95, k.y0 - 0.02, k.x1 - 0.02, k.y0 - 0.02, posts=1)
    K.railing(p, k.x1 - 0.02, k.y0 + 0.12, k.x1 - 0.02, k.y0 + 5.3, posts=4)
    p.finish()
    x, y, L, D, t = k.against('L', 2.35, 6.05, 0.85)                     # 灶台: three woks, the chimney at its front end
    p = Prop('K_ZaoTai', 'Kitchen', (x, y, K.F), rmax=0.03, turn=t)
    stove(p, x, y, L, D, woks=[k.y0 + v - y for v in (3.2, 4.25, 5.3)], chimney=-L / 2 + 0.28)
    p.finish()
    p = Prop('K_ChaiDui', 'Kitchen', (k.x0 + 0.75, k.y0 + 0.75, K.F), rmax=0.02)   # firewood in the front corner
    firewood(p, k.x0 + 0.75, k.y0 + 0.75, 0.6, 0.8)
    p.finish()
    p = Prop('K_Stand', 'Kitchen', (k.x0 + 0.45, k.y0 + 1.75, K.F), rmax=0.02)     # stand with a jar
    stand(p, k.x0 + 0.45, k.y0 + 1.75, 0.5, 0.5, 0.7, top='jar')
    p.finish()
    p = Prop('K_AnTai', 'Kitchen', (k.x0 + 2.9, k.y0 + 3.4, K.F), rmax=0.025, turn=90)   # long side to the camera
    work_table(p, k.x0 + 2.9, k.y0 + 3.4, 2.8, 1.4)
    p.finish()
    x, y, L, D, t = k.against('F', 2.6, 4.8, 0.45, gap=0.18)             # cabinet along the open front
    p = Prop('K_Guizi', 'Kitchen', (x, y, K.F), rmax=0.025, turn=t)
    cabinet(p, x, y, L, D, h=0.78, doors=3, top=[('basket', -0.75, 0.14), ('bowls', -0.25, 0.1), ('jar', 0.25, 0.08),
                                                ('bowls', 0.7, 0.09)])
    p.finish()
    p = Prop('K_MuTong', 'Kitchen', (k.x0 + 4.25, k.y0 + 1.75, K.F), rmax=0.02)   # big water tub
    tub(p, k.x0 + 4.25, k.y0 + 1.75, r=0.42, h=0.6)
    p.finish()
    x, y, L, D, t = k.against('B', 0.15, 1.6, 0.5)                       # counter in the back corner
    p = Prop('K_Counter', 'Kitchen', (x, y, K.F), rmax=0.025, turn=t)
    cabinet(p, x, y, L, D, h=0.8, doors=2, top=[('bowls', -0.4, 0.1), ('basket', 0.2, 0.15)])
    p.finish()
    x, y, L, D, t = k.against('B', 1.75, 2.65, 0.5)                      # baskets stacked under the window
    p = Prop('K_Baskets', 'Kitchen', (x, y, K.F), rmax=0.02, turn=t)
    for i, (dx, r_, z_) in enumerate(((-0.2, 0.2, 0.0), (0.22, 0.18, 0.0), (0.0, 0.17, 0.3))):
        K.basket(p, x + dx, y, K.F + z_, r_, 0.3 if z_ == 0 else 0.22, fill='Veg' if i == 2 else None)
    p.finish()
    x, y, L, D, t = k.against('B', 2.75, 3.5, 0.52)                      # stone sink
    p = Prop('K_ShuiChi', 'Kitchen', (x, y, K.F), rmax=0.03, turn=t)
    p.bx(x - L / 2 + 0.04, x + L / 2 - 0.04, y - D / 2 + 0.03, y + D / 2 - 0.03, K.F, K.F + 0.6, 'Stone')
    p.bx(x - L / 2, x + L / 2, y - D / 2, y + D / 2, K.F + 0.6, K.F + 0.8, 'Stone')
    p.bx(x - L / 2 + 0.07, x + L / 2 - 0.07, y - D / 2 + 0.07, y + D / 2 - 0.07, K.F + 0.74, K.F + 0.79, 'Water')
    p.finish()
    x, y, L, D, t = k.against('B', 3.6, 5.0, 0.45)                       # 碗柜
    p = Prop('K_WanGui', 'Kitchen', (x, y, K.F), rmax=0.02, turn=t)
    shelf_unit(p, x, y, L, D, Ht=1.95, base=0.6, tiers=3)
    p.finish()
    stones('K_Path', 'Kitchen', [(k.x0 + 1.4, k.y0 - 0.55, 0.6, 0.42), (k.x0 + 2.1, k.y0 - 0.65, 0.5, 0.4),
                                 (k.x0 + 1.2, k.y0 - 1.15, 0.55, 0.4), (k.x0 + 1.85, k.y0 - 1.25, 0.5, 0.38)])

    # ---------------- 二楼 behind and above the hall: 10.6 x 7.8, reaching left over the passage
    u = Room('Upstairs', -2.2, 7.6, 10.6, 7.8, f=F2)
    under_floor('U_Base', 'Upstairs', u.x0, u.x1, u.y0, u.y1, F2 - 0.38,
                runs=[('F', u.x0, h.x0 - 0.25), ('R', u.y0 + 0.25, u.y1)]).finish()
    K.set_floor(F2)
    slab('U_Slab', u).finish()
    plank_floor('U_Floor', u, along='y', margin=(0.06, 0.06, 0.06, 0.06),
                rugs=[(u.x0 + 1.6, u.x0 + 6.6, u.y0 + 2.4, u.y0 + 4.1)])
    p = Prop('U_Walls', 'Upstairs', (u.x0, u.y1, F2), rmax=0.03)
    side(p, u, 'L', [0, 0.7, 2.5, 3.3, 5.1, 7.8], ['plaster', 'window', 'plaster', 'window', 'plaster'],
         curtains=[(0.7, 2.5), (3.3, 5.1)], lanterns=[2.5, 5.1])
    side(p, u, 'B', [0, 1.9, 4.2, 6.6, 8.6, 10.6], ['plaster', 'plaster', 'plaster', 'plaster', 'plaster'], skip=[0],
         scrolls=[(3.0, 0.55), (5.4, 0.62), (9.6, 0.55)], lanterns=[8.6])
    p.finish()
    p = Prop('U_Railings', 'Upstairs', ((u.x0 + u.x1) / 2, u.y0, F2), rmax=0.02)
    K.railing(p, u.x0 + 0.25, u.y0 + 0.08, u.x1 - 0.3, u.y0 + 0.08, posts=8)
    K.railing(p, u.x1 - 0.08, u.y0 + 1.2, u.x1 - 0.08, u.y1 - 0.25, posts=6)
    lantern_post(p, u.x0 + 0.45, u.y0 + 0.5)
    p.finish()
    # the stair right of the hall's back-right corner: a straight flight rising toward the building (-x), as the art
    # draws it, to the 二楼's front-right corner; a stone base under it with steps at its foot, the tall outer wall
    # behind it
    K.set_floor(F0)
    sy, x_top, run = 8.22, u.x1 + 0.22, 3.5
    p = stair('D_Stairs', 'Hall', x_top + run, sy, (-1, 0), 0.85, run, F2 - F0, rail=+1, wall_side=-1)
    xb0, xb1, yb0, yb1 = u.x1 + 0.12, x_top + run + 0.75, 7.62, 8.85
    p.bx(xb0, xb1, yb0, yb1, 0, 0.22, 'Stone')
    p.bx(xb0 + 0.02, xb1 - 0.02, yb0 + 0.02, yb1 - 0.02, 0.22, F0 - 0.005, 'Stone')
    for k_ in range(2):                                                      # steps down at its foot
        z1 = F0 - F0 / 3 * (k_ + 1)
        p.bx(x_top + run - 0.35, x_top + run + 0.7, yb0 - 0.3 * (k_ + 1), yb0, 0, z1, 'Stone')
    p.bx(u.x1 - 0.02, x_top + 0.02, sy - 0.4, sy + 0.4, F2 - 0.05, F2 + 0.024, 'Wood')   # onto the deck
    stair_wall(p, x_top, x_top + run, sy + 0.425 + 0.09, F2, F0, lanterns=(1, 3))
    p.finish()
    K.set_floor(F2)
    # the tables: 5 by the stair's top, 7 in front of the 雅间, 8 on the left
    dining(5, 'Upstairs', u.x0 + 8.3, u.y0 + 3.97)
    dining(7, 'Upstairs', u.x0 + 5.7, u.y0 + 1.75)
    dining(8, 'Upstairs', u.x0 + 2.4, u.y0 + 1.75)
    # 雅间: painted screens on three sides, the doorway at the front's right end; the 二楼's back wall behind
    y_ = Room('Yajian', u.x0 + 1.9, u.y0 + 4.4, 4.7, 3.4, f=F2)
    p = Prop('Y_Screens', 'Yajian', ((y_.x0 + y_.x1) / 2, y_.y0, F2), rmax=0.015)
    screen_wall(p, y_.x0, y_.y0, y_.x1, y_.y0, door=(3.1, 4.4))
    screen_wall(p, y_.x0, y_.y0, y_.x0, u.y1 - 0.22)
    screen_wall(p, y_.x1, y_.y0, y_.x1, u.y1 - 0.22)
    p.finish()
    p = Prop('Y_Side', 'Yajian', (y_.x0 + 0.5, y_.y1 - 0.45, F2), rmax=0.02)
    stand(p, y_.x0 + 0.5, y_.y1 - 0.45, 0.5, 0.45, 0.72, top='tea')
    p.finish()
    dining(6, 'Yajian', y_.x0 + 2.6, u.y0 + 6.2)
    K.set_floor(F0)
    return [('closeup_kitchen.png', 'K_ZaoTai'), ('closeup_hall.png', 'D_Table_1'), ('closeup_stairs.png', 'D_Stairs'),
            ('closeup_upstairs.png', 'D_Table_7'), ('closeup_yajian.png', 'D_Table_6')]


# ================================================================= 五级 · 名动一方 (一楼 4 · 二楼散座 6 · 雅间 2)

def level_5():
    """楼上公共餐厅新增两桌-15.png (drawn front-on; -4, -10 and -13 for what it hides). The kitchen on the left with an
    L-shaped range (five woks, two steamers, a chimney) in its back-left corner, racks along its left wall; the paved
    lane between the kitchen and the hall (the Corridor group), open at the front, a 门帘 doorway in its back wall,
    the kitchen and the hall opening onto its back end; the hall with its four tables on a 2 x 2 grid, the entrance
    in the middle of its front and painted screens in its front corners; an outside stair along its right side up to
    the 二楼 behind it: six 散座 tables in three rows of two, and at the back two 雅间 behind a low partition with a
    door each and a small corridor between them."""
    # ---------------- 一楼大堂: 8.4 x 7.6
    h = Room('Hall', 0.0, 0.0, 8.4, 7.6)
    plinth('D_Plinth', h, kerbs='F', steps_=[('F', 3.25, 5.15, 3)], gaps=[('F', 3.2, 5.2)],
           ext=(0.1, 0.0, 0.1, -0.02)).finish()
    plank_floor('D_Floor', h, along='y', pw=0.28, length=2.4, margin=(0.06, 0.06, 0.06, 0.06))
    p = Prop('D_Walls', 'Hall', (h.x0, h.y1, K.F), rmax=0.03)
    side(p, h, 'L', [0, 1.4, 3.1, 4.7, 6.3, 7.6], ['plaster', 'window', 'plaster', 'plaster', 'opening'],
         curtains=[(1.4, 3.1)], lanterns=[1.4, 4.7], brackets=[6.3, 7.6], scrolls=[(3.9, 0.55)])
    M, s = K.along(*h.frame('L')[:3])
    K.curtain(p, M, s, 6.4, 7.5, K.F + K.H - 0.42, drop=0.62, strips=2)                 # 门帘 on the passage door
    threshold(p, h, 'L', 6.3, 7.6)
    side(p, h, 'B', [0, 1.1, 2.9, 3.5, 4.9, 5.5, 7.3, 8.4], ['plaster', 'window', 'plaster', 'plaster', 'plaster',
                                                             'window', 'plaster'], skip=[0],
         curtains=[(1.1, 2.9), (5.5, 7.3)], lanterns=[2.9, 5.5], scrolls=[(0.55, 0.5), (7.85, 0.5)])
    side(p, h, 'F', [0, 1.6, 3.2, 5.2, 6.8, 8.4], ['plaster', 'plaster', None, 'plaster', 'plaster'], h=0.85,
         skip=[0, 3.2, 5.2])
    side(p, h, 'R', [0, 1.9, 3.8, 5.7, 7.6], ['plaster', 'plaster', 'plaster', 'plaster'], h=0.85, skip=[0, 7.6])
    door_frame(p, h, 'F', 3.2, 5.2, K.F + 1.75, drop=0.85, lantern_out=True)
    p.finish()
    p = Prop('D_Screens', 'Hall', (h.x0 + 4.2, h.y0 + 0.5, K.F), rmax=0.015)  # 屏风 in the front corners and at the back
    pingfeng(p, h.x0 + 0.35, h.y0 + 0.45, h.x0 + 1.55, h.y0 + 0.45)
    pingfeng(p, h.x1 - 1.55, h.y0 + 0.45, h.x1 - 0.35, h.y0 + 0.45)
    pingfeng(p, h.x0 + 3.6, h.y1 - 0.3, h.x0 + 4.8, h.y1 - 0.3, h=1.7)
    p.finish()
    x, y, L, D, t = h.against('L', 3.5, 4.4, 0.4)                       # small cabinet by the left wall
    p = Prop('D_Cabinet', 'Hall', (x, y, K.F), rmax=0.025, turn=t)
    cabinet(p, x, y, L, D, h=0.75, doors=2, top=[('jar', -0.2, 0.08), ('pale', 0.2, 0.07)])
    p.finish()
    # the 2 x 2 grid: 1 back-left (nearest the passage door), 2 front-left, 3 back-right, 4 front-right
    for n, (x, y) in ((1, (2.7, 5.2)), (2, (2.7, 2.6)), (3, (6.1, 5.2)), (4, (6.1, 2.6))):
        dining(n, 'Hall', x, y)
    walkway('D_Walkway', 'Hall', 8.4, 9.85, 0.6, 9.0, steps_=[('F', 0.15, 1.3, 3)]).finish()
    pts = [(4.2, -1.45, 0.9, 0.45), (3.65, -2.0, 0.7, 0.42), (4.6, -2.1, 0.5, 0.4), (3.25, -2.6, 0.6, 0.4),
           (4.0, -2.7, 0.5, 0.38), (2.85, -3.15, 0.55, 0.4)]
    stones('D_Path', 'Hall', pts + [(9.05, -1.0, 0.6, 0.42), (9.3, -1.6, 0.5, 0.4)])
    queue([(x_, y_, 0.05) for x_, y_, _, _ in pts[:4]], 'Hall')

    # ---------------- 走廊: the paved lane between the kitchen and the hall (the art's stone-floored passage), open at
    # the front with steps, a 门帘 doorway in its back wall; the kitchen and the hall open onto its back end
    c = Room('Corridor', -2.4, 0.0, 2.4, 7.6)
    plinth('C_Plinth', c, kerbs='F', gaps=[('F', 0.3, 2.1)], steps_=[('F', 0.35, 2.05, 3)],
           ext=(-0.1, -0.1, 0.1, -0.02)).finish()
    tile_floor('C_Floor', c, cell=0.78, split=0.1, margin=(0.02, 0.02, 0.16, 0.08))
    p = Prop('C_Walls', 'Corridor', (c.x0 + c.w / 2, c.y1, K.F), rmax=0.03)
    side(p, c, 'B', [0, 0.65, 1.75, 2.4], ['plaster', 'opening', 'plaster'], skip=[0, 2.4], brackets=[0.65, 1.75],
         lanterns=[0.65])
    M, s = K.along(*c.frame('B')[:3])
    K.curtain(p, M, s, 0.75, 1.65, K.F + K.H - 0.42, drop=0.62, strips=2)
    p.box((1.2, 0, K.F), (0.93, 0.2, 0.06), 'Stone', M=M, r=0.012)       # threshold, resting on the plinth
    p.finish()

    # ---------------- 后厨: 7.4 x 7.6
    k = Room('Kitchen', -9.8, 0.0, 7.4, 7.6)
    plinth('K_Plinth', k, kerbs='FR', gaps=[('R', 6.2, 7.7)]).finish()
    tile_floor('K_Floor', k, cell=0.8, split=0.12, margin=(0.09, 0.19, 0.2, 0.09))
    p = Prop('K_Walls', 'Kitchen', (k.x0, k.y1, K.F), rmax=0.03)
    side(p, k, 'L', [0, 1.4, 3.3, 5.3, 7.6], ['plaster', 'plaster', 'plaster', 'plaster'], lanterns=[5.3])
    side(p, k, 'B', [0, 0.5, 1.5, 3.3, 5.6, 7.4], ['plaster', 'window', 'plaster', 'plaster', 'plaster'], skip=[0],
         lanterns=[1.5])
    wall_shelf(p, k, 'B', 1.7, 2.4, K.F + 1.45, items=[('jar', 1.9, 0.08), ('jar', 2.2, 0.07)])
    wall_shelf(p, k, 'B', 5.75, 6.4, K.F + 1.5, items=[('bowls', 5.9, 0.09), ('pale', 6.2, 0.06)])
    hang_strings(p, k, 'B', (6.6, 6.8, 7.0), K.F + 1.75, mats=('Straw', 'Straw', 'Chili'))
    side(p, k, 'R', [0, 2.0, 4.1, 6.2, 7.6], ['plaster', 'plaster', 'plaster', 'opening'], h=0.85, skip=[7.6],
         tall={6.2: K.H})
    p.finish()
    # the L-shaped range: a leg along the back wall (two woks, a chimney, a steamer) and a leg coming forward from it
    # (three woks and pots, their fire mouths facing the room)
    p = Prop('K_ZaoTai', 'Kitchen', (k.x0 + 3.6, k.y0 + 6.2, K.F), rmax=0.03)
    bx0, bx1 = k.x0 + 1.4, k.x0 + 5.9
    by = k.y1 - 0.12 - 0.44
    stove(p, (bx0 + bx1) / 2, by, bx1 - bx0, 0.88, woks=[k.x0 + v - (bx0 + bx1) / 2 for v in (2.6, 3.8)],
          chimney=k.x0 + 3.2 - (bx0 + bx1) / 2, steamers=[k.x0 + v - (bx0 + bx1) / 2 for v in (4.75, 5.4)], h=0.79)
    lx, ly0, ly1 = k.x0 + 1.75, k.y0 + 3.5, k.y1 - 0.12
    ly = (ly0 + ly1) / 2
    with turned(p, lx, ly, 90):                          # built along x, turned so its back faces the left wall
        stove(p, lx, ly, ly1 - ly0, 0.9, woks=[k.y0 + v - ly for v in (4.15, 5.15, 6.15)], back=0.5)
    p.finish()
    x, y, L, D, t = k.against('L', 0.6, 3.2, 0.5)                        # rack of baskets and greens on the left
    p = Prop('K_CaiJia', 'Kitchen', (x, y, K.F), rmax=0.02, turn=t)
    open_rack(p, x, y, L, D, h=1.15, tiers=2, fill='baskets')
    p.finish()
    x, y, L, D, t = k.against('L', 3.6, 6.3, 0.45)                       # low cabinet of jars behind the stove leg
    p = Prop('K_TanGui', 'Kitchen', (x, y, K.F), rmax=0.025, turn=t)
    cabinet(p, x, y, L, D, h=0.75, doors=3, top=[('jar', -0.9, 0.09), ('pale', -0.45, 0.07), ('jar', 0.1, 0.1),
                                                ('bowls', 0.6, 0.09), ('jar', 1.0, 0.08)])
    p.finish()
    p = Prop('K_AnTai', 'Kitchen', (k.x0 + 5.0, k.y0 + 3.3, K.F), rmax=0.025)
    work_table(p, k.x0 + 5.0, k.y0 + 3.3, 2.4, 1.3)
    p.finish()
    p = Prop('K_CaiTai', 'Kitchen', (k.x0 + 6.75, k.y0 + 3.3, K.F), rmax=0.02)    # side table with baskets
    stand(p, k.x0 + 6.75, k.y0 + 3.3, 0.7, 1.0, 0.72, top='basket')
    p.finish()
    p = Prop('K_MuTong', 'Kitchen', (k.x0 + 3.1, k.y0 + 1.25, K.F), rmax=0.02)    # the big wooden tub
    tub(p, k.x0 + 3.1, k.y0 + 1.25, r=0.55, h=0.6)
    p.finish()
    p = Prop('K_ShiTai', 'Kitchen', (k.x0 + 1.8, k.y0 + 1.3, K.F), rmax=0.03)     # stone stand
    p.bx(k.x0 + 1.5, k.x0 + 2.1, k.y0 + 1.0, k.y0 + 1.6, K.F, K.F + 0.55, 'Stone')
    p.bx(k.x0 + 1.46, k.x0 + 2.14, k.y0 + 0.96, k.y0 + 1.64, K.F + 0.55, K.F + 0.62, 'Stone')
    p.finish()
    p = Prop('K_Stand', 'Kitchen', (k.x0 + 4.4, k.y0 + 0.75, K.F), rmax=0.02)     # small stand with a basket
    stand(p, k.x0 + 4.4, k.y0 + 0.75, 0.5, 0.45, 0.6, top='basket')
    p.finish()
    x, y, L, D, t = k.against('R', 0.6, 1.9, 0.45)                       # water trough by the open side
    p = Prop('K_ShuiCao', 'Kitchen', (x, y, K.F), rmax=0.03, turn=t)
    p.bx(x - L / 2, x + L / 2, y - D / 2, y + D / 2, K.F, K.F + 0.55, 'Stone')
    p.bx(x - L / 2 + 0.06, x + L / 2 - 0.06, y - D / 2 + 0.06, y + D / 2 - 0.06, K.F + 0.5, K.F + 0.53, 'Water')
    p.finish()
    stones('K_Path', 'Kitchen', [(k.x0 + 1.4, -0.55, 0.6, 0.42), (k.x0 + 2.1, -0.65, 0.5, 0.4),
                                 (k.x0 + 1.2, -1.15, 0.55, 0.4), (k.x0 + 1.85, -1.25, 0.5, 0.38)])

    # ---------------- 二楼 behind and above the hall: 9.6 x 12.0 (散座 8.6 deep, the two 雅间 3.4 deep behind)
    deck = Room('Upstairs', -1.2, 7.6, 9.6, 12.0, f=F2)
    under_floor('U_Base', 'Upstairs', deck.x0, deck.x1, deck.y0, deck.y1, F2 - 0.38,
                runs=[('R', deck.y0 + 0.25, deck.y1)], ext_r=0.0).finish()
    K.set_floor(F2)
    u = Room('Upstairs', -1.2, 7.6, 9.6, 8.6, f=F2)                         # the 散座
    slab('U_Slab', deck).finish()
    plank_floor('U_Floor', deck, along='y', pw=0.34, length=2.4, margin=(0.06, 0.06, 0.06, 0.06),
                rugs=[(u.x0 + 1.7, u.x0 + 7.9, u.y0 + 3.4, u.y0 + 5.3)])
    p = Prop('U_Walls', 'Upstairs', (deck.x0, deck.y1, F2), rmax=0.03)
    side(p, deck, 'L', [0, 0.9, 2.7, 5.4, 7.2, 8.6, 10.3, 12.0], ['plaster', 'window', 'plaster', 'window', 'plaster',
                                                                  'plaster', 'plaster'],
         curtains=[(0.9, 2.7), (5.4, 7.2)], lanterns=[2.7, 7.2, 10.3])
    side(p, deck, 'B', [0, 0.6, 2.1, 4.4, 5.0, 5.6, 7.1, 9.6], ['plaster', 'window', 'plaster', 'plaster',
                                                                'plaster', 'window', 'plaster'], skip=[0],
         curtains=[(0.6, 2.1), (5.6, 7.1)], scrolls=[(3.25, 0.6), (8.35, 0.6)], lanterns=[2.1, 5.0, 7.1])
    # the 雅间's low lattice front (the 散座's back) with a door into each, and the 雅间二 near side cut low
    side(p, u, 'B', [0, 1.8, 3.4, 4.4, 5.6, 6.6, 8.0, 9.6], ['plaster', 'plaster', None, 'plaster', None, 'plaster',
                                                               'plaster'], h=1.0, skip=[0, 3.4, 4.4, 5.6, 6.6])
    side(p, u, 'R', [1.35, 3.2, 5.0, 6.8, 8.6], ['plaster', 'plaster', 'plaster', 'plaster'], h=1.0, skip=[8.6])
    for a, b in ((3.4, 4.4), (5.6, 6.6)):
        door_frame(p, u, 'B', a, b, F2 + 1.9, drop=0.45, strips=2)
    y2 = Room('Yajian', 4.4, u.y1, 4.0, 3.4, f=F2)
    side(p, y2, 'R', [0, 1.7, 3.4], ['plaster', 'plaster'], h=1.0, skip=[0, 3.4])
    p.finish()
    p = Prop('U_Railings', 'Upstairs', ((u.x0 + u.x1) / 2, u.y0, F2), rmax=0.02)
    K.railing(p, u.x0 + 0.25, u.y0 + 0.08, u.x1 - 0.3, u.y0 + 0.08, posts=8)
    lantern_post(p, u.x0 + 0.45, u.y0 + 0.5)
    p.finish()
    p = Prop('U_Screens', 'Upstairs', (u.x0 + 0.5, u.y0 + 4.3, F2), rmax=0.015)   # 屏风 along the left wall
    pingfeng(p, u.x0 + 0.45, u.y0 + 3.0, u.x0 + 0.45, u.y0 + 5.0)
    p.finish()
    K.set_floor(F0)
    outside_stair('D_Stairs', 'Hall', u.x1 + 0.66, 3.0, 4.9, F2 - F0, deck_x=u.x1, landing=0.95).finish()
    K.set_floor(F2)
    # 散座, three rows of two: by the stair's top first
    cols, rows = (u.x0 + 3.35, u.x0 + 6.65), (u.y0 + 1.6, u.y0 + 4.3, u.y0 + 7.0)
    for n, (ci, ri) in ((5, (1, 0)), (7, (1, 1)), (8, (0, 0)), (9, (1, 2)), (10, (0, 1)), (11, (0, 2))):
        dining(n, 'Upstairs', cols[ci], rows[ri])
    # the two 雅间: 一 on the right (nearer the stair), 二 on the left, a tall painted screen between them
    y1_ = Room('Yajian', u.x0, u.y1, 4.4, 3.4, f=F2)
    p = Prop('Y_Screens', 'Yajian', (y2.x0, y2.y0 + 1.7, F2), rmax=0.015)
    for x_ in (y1_.x1, y2.x0):                       # the two 雅间 walls, a small corridor between them (as the art)
        screen_wall(p, x_, y2.y0 + 0.22, x_, deck.y1 - 0.22)
    pingfeng(p, y1_.x0 + 0.45, y1_.y0 + 0.9, y1_.x0 + 0.45, y1_.y0 + 2.5)
    pingfeng(p, y2.x1 - 0.5, y2.y0 + 0.9, y2.x1 - 0.5, y2.y0 + 2.5)
    p.finish()
    for i, (x, y) in enumerate(((y2.x1 - 0.55, y2.y1 - 0.45), (y1_.x0 + 0.5, y1_.y1 - 0.45))):
        p = Prop(f'Y_Side_{i + 1}', 'Yajian', (x, y, F2), rmax=0.02)
        stand(p, x, y, 0.5, 0.45, 0.72, top='tea')
        p.finish()
    dining(6, 'Yajian', y2.x0 + 1.95, y2.y0 + 1.7)
    dining(12, 'Yajian', y1_.x0 + 2.25, y1_.y0 + 1.7)
    K.set_floor(F0)
    return [('closeup_kitchen.png', 'K_ZaoTai'), ('closeup_hall.png', 'D_Table_1'), ('closeup_stairs.png', 'D_Stairs'),
            ('closeup_upstairs.png', 'D_Table_10'), ('closeup_yajian.png', 'D_Table_6')]


def round_window(p, room, which, u, r=0.28, z=None):
    """圆窗: a round lattice window on a wall."""
    z = K.F + 1.3 if z is None else z
    (x, y), (nx, ny) = room.on_side(which, u, 0.0)
    # the lathe axis (local z) points into the room
    rot = {'L': Matrix.Rotation(math.radians(90), 4, 'Y'), 'R': Matrix.Rotation(math.radians(-90), 4, 'Y'),
           'B': Matrix.Rotation(math.radians(90), 4, 'X'), 'F': Matrix.Rotation(math.radians(-90), 4, 'X')}[which]
    T = Matrix.Translation((x, y, z)) @ rot
    p.lathe([(r, -0.03), (r, 0.06), (r - 0.06, 0.06), (r - 0.06, 0.0)], (0, 0, 0), 'Timber', n=20, cap_bottom=False,
            cap_top=False, M=T)
    p.lathe([(r - 0.06, 0.028), (0.0, 0.028)], (0, 0, 0), 'Paper', n=20, cap_bottom=False, cap_top=False, M=T)
    for a in (0, 90):
        q = Matrix.Rotation(math.radians(a), 4, 'Z')
        p.box((0, 0, 0.042), (2 * r - 0.1, 0.03, 0.03), 'Timber', M=T @ q)


# ================================================================= main

LEVELS = {1: level_1, 2: level_2, 3: level_3, 4: level_4, 5: level_5}

def xy_box(ob):
    pts = [ob.matrix_world @ Vector(c) for c in ob.bound_box]
    return min(p_.x for p_ in pts), max(p_.x for p_ in pts), min(p_.y for p_ in pts), max(p_.y for p_ in pts),         min(p_.z for p_ in pts), max(p_.z for p_ in pts)


def gap(a, b):
    """Clear distance between two boxes (x0, x1, y0, y1) in plan."""
    dx = max(0.0, max(a[0], b[0]) - min(a[1], b[1]))
    dy = max(0.0, max(a[2], b[2]) - min(a[3], b[3]))
    return math.hypot(dx, dy)


def walkways():
    """Smallest walkway from each table group (table and stools) to the other groups, its room's walls and the other
    pieces standing on the same floor; returns [(table, what, metres)] for the ones under 0.5 m."""
    groups = {}
    for ob in K.PARTS:
        m = re.match(r'D_(Table|Stool)_(\d+)', ob.name)
        if m:
            groups.setdefault(m.group(2), []).append(xy_box(ob))
    others = [(ob.name, xy_box(ob)) for ob in K.PARTS if not re.match(r'D_(Table|Stool)_', ob.name)
              and not re.search(r'_(Floor|Plinth|Walls|Path|Slab|Posts|Railings|Screens)', ob.name)]
    low = []
    for n, boxes in sorted(groups.items(), key=lambda kv: int(kv[0])):
        z = boxes[0][4]
        for m, bb in groups.items():
            if int(m) > int(n):
                g = min(gap(a, b) for a in boxes for b in bb)
                if g < 0.5 and abs(bb[0][4] - z) < 0.5:
                    low.append((f'D_Table_{n}', f'D_Table_{m}', round(g, 2)))
        cx = (boxes[0][0] + boxes[0][1]) / 2
        cy = (boxes[0][2] + boxes[0][3]) / 2
        rooms = [r for r in ROOMS if r.x0 < cx < r.x1 and r.y0 < cy < r.y1 and abs(r.f - z) < 0.3]
        room = min(rooms, key=lambda r: r.w * r.d) if rooms else None      # the smallest room it stands in
        if room:
            x0, x1 = min(b[0] for b in boxes), max(b[1] for b in boxes)
            y0, y1 = min(b[2] for b in boxes), max(b[3] for b in boxes)
            for what, g in (('wall L', x0 - room.x0 - 0.085), ('wall R', room.x1 - 0.085 - x1),
                            ('wall F', y0 - room.y0 - 0.085), ('wall B', room.y1 - 0.085 - y1)):
                if g < 0.5:
                    low.append((f'D_Table_{n}', f'{room.grp} {what}', round(g, 2)))
        for name, bb in others:
            if bb[5] < z + 0.05 or bb[4] > z + 1.8:
                continue                                   # on another floor, or overhead
            g = min(gap(a, bb) for a in boxes)
            if g < 0.5:
                low.append((f'D_Table_{n}', name, round(g, 2)))
    for t, what, g in low:
        K.log(f'WALKWAY {t} to {what}: {g} m')
    return low


def counts():
    """Tables (per group), stools, woks and queue spots, checked against the conventions."""
    tables = sorted((ob for ob in K.PARTS if ob.name.startswith('D_Table_')), key=lambda o: int(o.name.split('_')[2]))
    by_group = {}
    for ob in tables:
        by_group[ob.parent.name] = by_group.get(ob.parent.name, 0) + 1
    stools = [ob for ob in K.PARTS if ob.name.startswith('D_Stool_')]
    for ob in tables:
        n = ob.name.split('_')[2]
        assert sum(s.name.startswith(f'D_Stool_{n}_') for s in stools) == 4, ob.name
    assert sum(ob.name == 'K_AnTai' for ob in K.PARTS) == 1
    return {'level': LEVEL, 'tables': len(tables), 'tables_by_group': by_group, 'table_names': [o.name for o in tables],
            'stools': len(stools), 'woks': len(WOKS), 'queue': sum(m.name.startswith('Spot_Queue_') for m in K.MARKERS),
            'walkways_under_0.5m': walkways()}


if __name__ == '__main__':
    K.begin(f'SM_Shop{LEVEL}', f'shop{LEVEL}', seed=7)
    closeups = LEVELS[LEVEL]()
    bpy.context.view_layer.update()
    c = counts()
    K.finish_level(OUT, RENDER, closeups=closeups)
    import json
    with open(os.path.join(OUT, 'renders', 'stats.json')) as fh:
        c['tris'] = json.load(fh)['tris']
    with open(os.path.join(OUT, 'renders', 'counts.json'), 'w', encoding='utf-8') as fh:
        json.dump(c, fh, indent=1, ensure_ascii=False)
    K.log(f'counts {c}')
