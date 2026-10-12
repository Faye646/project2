"""初始关卡（一级 · 1 桌）白模 for the 汴河两岸 三渲二 pipeline.

Built procedurally from the level art 初始1桌布局.jpg and its part sheets (厨房, 餐厅, 墙壁, 桌子,
板凳, 厨房地板, 饭堂地板), in the same style as 纹璃宫灯: every hard edge of the timber, stone and
furniture is rounded (Bevel modifier, 2 segments, hardened normals), turned parts are lathed, and
the bottoms of floor tiles / planks that nobody can see are left open.

Layout (meters, Z up, the kitchen's front-left corner at the origin):
    后厨 kitchen   x 0 – 4.2,    y 0 – 3.6
    走廊 corridor  x 4.2 – 7.2,  y 2.3 – 3.6   (走廊.png: stone-dado back wall, open front)
    前堂 hall      x 7.2 – 12.6, y 2.3 – 6.9   (built at x 4.9 / y 3.6, then its group is moved)
Back walls stand on the far sides (x = min, y = max); the near sides are open, as in the art.
Spot_Queue_1…4 empties mark where waiting guests stand.

Every prop is one object whose pivot sits at the middle of its footprint on the floor. The
object names are what the Unity side keys on (K_AnTai is the 案台 that opens the cooking screen).

Run with Blender 5.2:
    blender -b --factory-startup --python build_level1.py -- <out_dir> [--no-render]
Writes SM_Level1.blend / .fbx, palette.json and renders/ (clay, wire, toon) to <out_dir>.
"""
import json
import math
import os
import random
import sys

import bmesh  # noqa: F401
import bpy
from mathutils import Matrix, Vector  # noqa: F401

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import level_kit as K  # noqa: E402
from level_kit import (F, H, Prop, basket, bowl, curtain, group, railing, stool, steps, table,  # noqa: E402
                       wall, wall_lantern)

ARGS = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
OUT = os.path.abspath(ARGS[0]) if ARGS and not ARGS[0].startswith('--') else \
    os.path.join(os.path.dirname(os.path.abspath(__file__)), 'Level1')
RENDER = '--no-render' not in ARGS
WC = '--wc' in ARGS   # also render the approved style C (painted textures, watercolor light) to renders/wc.png
NAME = 'SM_Level1'
K.begin(NAME, 'level1', seed=7)


# ================================================================= build

# ---------------- 后厨 kitchen: plinth, stone floor, walls
KX, KY = 5.0, 4.2   # a little roomier than the art (4.2 × 3.6)
DX0, DX1, DY0, DY1 = 4.9, 10.3, 3.6, 8.2

p = Prop('K_Plinth', 'Kitchen', (KX / 2, KY / 2, 0), rmax=0.03)
p.bx(-0.1, KX + 0.1, -0.1, KY + 0.1, 0, 0.22, 'Stone')
p.bx(-0.08, KX + 0.08, -0.08, KY + 0.08, 0.22, F - 0.04, 'Stone')
for k in range(int(KX / 0.35)):  # kerb stones along the two open sides
    x0 = -0.1 + k * (KX + 0.2) / int(KX / 0.35)
    p.bx(x0 + 0.005, x0 + (KX + 0.2) / int(KX / 0.35) - 0.005, -0.1, 0.18, F - 0.05, F + 0.01, 'Stone')
for k in range(int((KY + 0.2) / 0.35)):
    n = int((KY + 0.2) / 0.35)
    y0 = 0.18 + k * (KY - 0.1) / n
    p.bx(KX - 0.18, KX + 0.1, y0 + 0.005, y0 + (KY - 0.1) / n - 0.005, F - 0.05, F + 0.01, 'Stone')
p.finish()

p = Prop('K_Floor', 'Kitchen', (KX / 2, KY / 2, F), rmax=0.02)
cell = 0.42
nx, ny = int((KX - 0.3) / cell), int((KY - 0.3) / cell)
cx0, cy0 = 0.09, 0.2
cw, ch = (KX - 0.19 - cx0) / nx, (KY - 0.09 - cy0) / ny
g = 0.025
for i in range(nx):
    for j in range(ny):
        x0, y0 = cx0 + i * cw, cy0 + j * ch
        if random.random() < 0.22:  # a few cells split into four small stones, as in 厨房地板.jpg
            for a in range(2):
                for b in range(2):
                    p.bx(x0 + a * cw / 2 + g / 2, x0 + (a + 1) * cw / 2 - g / 2, y0 + b * ch / 2 + g / 2,
                         y0 + (b + 1) * ch / 2 - g / 2, F - 0.04, F + 0.012, 'Tile', open_bottom=True, top_only=True)
        else:
            p.bx(x0 + g / 2, x0 + cw - g / 2, y0 + g / 2, y0 + ch - g / 2, F - 0.04, F + 0.012 + random.uniform(0, 0.006),
                 'Tile', open_bottom=True, top_only=True)
p.finish()

p = Prop('K_Walls', 'Kitchen', (0, KY, F), rmax=0.03)
wall(p, 'y', (0, 0), 1, KY, [0.0, 1.8, KY], [(0.0, 1.8, 'plaster'), (1.8, KY, 'plaster')])
M, s = wall(p, 'x', (0, KY), -1, KX, [1.5, 2.4, 3.3, KX],
            [(0.0, 1.5, 'plaster'), (1.5, 2.4, 'plaster'), (2.4, 3.3, 'window'), (3.3, KX, 'plaster')])
curtain(p, M, s, 2.5, 3.2, F + H - 0.45, drop=0.3)
wall_lantern(p, 3.3, KY - 0.09, (0, -1))
p.finish()

# 灶台 stove (初等): brick body along the left wall, iron wok, fire mouth, chimney
p = Prop('K_ZaoTai', 'Kitchen', (0.55, 1.95, F), rmax=0.03, off=(0, 0.35))
p.bx(0.1, 1.02, 1.2, 2.7, F, F + 0.72, 'Brick')
p.bx(0.08, 1.05, 1.18, 2.72, F + 0.72, F + 0.8, 'Brick')          # top slab
p.bx(1.0, 1.08, 1.45, 1.8, F + 0.1, F + 0.38, 'Iron')              # fire mouth
p.blob((1.03, 1.625, F + 0.2), 0.1, 'Fire', (0.4, 1.2, 1.0))
p.lathe([(0.02, F + 0.66), (0.2, F + 0.72), (0.31, F + 0.83), (0.33, F + 0.86), (0.3, F + 0.86), (0.18, F + 0.76)],
        (0.58, 1.6, 0), 'Iron', n=16, cap_bottom=False, cap_top=False, rims=[3])
p.lathe([(0.2, F + 0.8), (0.21, F + 0.95), (0.19, F + 0.95)], (0.58, 2.2, 0), 'Straw', n=14, cap_top=False,
        rims=[0, 1])                                                # steamer on the second hole
p.lathe([(0.21, F + 0.95), (0.13, F + 1.02), (0.03, F + 1.05)], (0.58, 2.2, 0), 'Straw', n=14, cap_bottom=False)
p.bx(0.1, 0.52, 2.28, 2.7, F + 0.8, F + H + 0.55, 'Brick')         # chimney
p.bx(0.07, 0.55, 2.25, 2.73, F + H + 0.55, F + H + 0.65, 'Brick')
p.bx(1.02, 1.3, 2.25, 2.62, F, F + 0.3, 'Brick')                   # side step
stove = p.finish()

p = Prop('K_ChaiDui', 'Kitchen', (0.5, 0.65, F), rmax=0.02)       # firewood stack
for layer, n in enumerate((4, 3, 2)):
    for k in range(n):
        x = 0.28 + k * 0.17 + layer * 0.085
        p.lathe([(0.075, -0.3), (0.075, 0.3)], (0, 0, 0), 'Wood', n=8,
                M=Matrix.Translation((x, 0.65, F + 0.075 + layer * 0.14)) @ Matrix.Rotation(math.radians(90), 4, 'X'))
p.bx(0.18, 0.95, 0.3, 0.35, F, F + 0.05, 'Timber')
p.finish()

p = Prop('K_Crates', 'Kitchen', (0.4, 3.1, F), rmax=0.03, off=(0, 0.6))
p.bx(0.12, 0.62, 2.85, 3.45, F, F + 0.4, 'Wood')
p.bx(0.16, 0.56, 2.92, 3.4, F + 0.4, F + 0.72, 'Wood')
basket(p, 0.36, 3.16, F + 0.72, 0.13, 0.1, fill='Veg')
p.finish()

p = Prop('K_Counter', 'Kitchen', (1.6, 3.28, F), rmax=0.025, off=(0.1, 0.6))       # counter by the back wall
p.bx(0.75, 2.05, 3.0, 3.5, F, F + 0.72, 'Wood')
p.bx(0.72, 2.08, 2.96, 3.52, F + 0.72, F + 0.78, 'Wood')
for k in range(3):
    x0 = 0.8 + k * 0.415
    p.bx(x0 + 0.02, x0 + 0.395, 2.97, 3.0, F + 0.12, F + 0.62, 'Wood')
basket(p, 1.05, 3.24, F + 0.78, 0.15, 0.1, fill='Veg')
basket(p, 1.5, 3.24, F + 0.78, 0.14, 0.1, fill='Chili')
bowl(p, 1.85, 3.24, F + 0.78, 0.12)
p.bx(0.8, 2.0, 3.36, 3.52, F + 1.25, F + 1.29, 'Wood')             # wall shelf with jars
for x in (0.95, 1.25, 1.55, 1.85):
    p.lathe([(0.05, F + 1.29), (0.07, F + 1.36), (0.05, F + 1.45), (0.035, F + 1.47)], (x, 3.44, 0), 'Glaze', n=10)
for k in range(4):                                                   # hanging chilli string
    p.blob((2.02, 3.47, F + 1.62 - k * 0.1), 0.045, 'Chili', (1, 1, 1.4))
p.finish()

p = Prop('K_ShuiChi', 'Kitchen', (2.6, 3.26, F), rmax=0.03, off=(0.3, 0.6))       # wash stand under the window
p.bx(2.28, 2.92, 3.0, 3.5, F, F + 0.62, 'Stone')
p.bx(2.25, 2.95, 2.97, 3.52, F + 0.62, F + 0.8, 'Stone')
p.bx(2.33, 2.87, 3.04, 3.46, F + 0.74, F + 0.79, 'Water')
p.lathe([(0.1, F + 0.8), (0.13, F + 0.95), (0.11, F + 0.95)], (2.8, 3.1, 0), 'Wood', n=12, cap_top=False, rims=[0, 1])
p.finish()

p = Prop('K_WanGui', 'Kitchen', (3.6, 3.36, F), rmax=0.02, off=(0.55, 0.6))        # bowl shelf (碗柜)
for x in (3.2, 4.0):
    for y in (3.2, 3.5):
        p.box((x, y, F + 0.85), (0.06, 0.06, 1.7), 'Wood')
for k, z in enumerate((0.05, 0.45, 0.85, 1.25, 1.65)):
    p.bx(3.17, 4.03, 3.17, 3.53, F + z, F + z + 0.04, 'Wood')
    if 0 < k < 4:
        for j in range(3):
            x = 3.35 + j * 0.25
            for s_ in range(2 if (k + j) % 2 else 3):
                bowl(p, x, 3.35, F + z + 0.04 + s_ * 0.045, 0.09)
p.bx(3.17, 4.03, 3.17, 3.53, F, F + 0.05, 'Wood')
p.finish()

# 案台 work table in the middle: the one the player taps to open the cooking screen
p = Prop('K_AnTai', 'Kitchen', (2.1, 1.75, F), rmax=0.025, off=(0.45, 0.35), turn=90)   # long side facing the camera's right
x0, x1, y0, y1 = 1.3, 2.9, 1.4, 2.1
p.bx(x0, x1, y0, y1, F + 0.74, F + 0.84, 'Wood')
for x in (x0 + 0.07, x1 - 0.07):
    for y in (y0 + 0.07, y1 - 0.07):
        p.box((x, y, F + 0.37), (0.1, 0.1, 0.74), 'Wood')
p.bx(x0 + 0.1, x1 - 0.1, y0 + 0.04, y0 + 0.08, F + 0.62, F + 0.72, 'Wood')
p.bx(x0 + 0.1, x1 - 0.1, y1 - 0.08, y1 - 0.04, F + 0.62, F + 0.72, 'Wood')
p.bx(x0 + 0.1, x1 - 0.1, y0 + 0.08, y1 - 0.08, F + 0.16, F + 0.2, 'Wood')      # low shelf
basket(p, 1.65, 1.75, F + 0.2, 0.17, 0.14, fill='Veg')
basket(p, 2.2, 1.75, F + 0.2, 0.17, 0.14)
p.lathe([(0.22, F + 0.84), (0.22, F + 0.91)], (1.75, 1.75, 0), 'Wood', n=16)  # chopping block
p.bx(1.85, 2.05, 1.62, 1.72, F + 0.91, F + 0.925, 'Iron', rot=0)              # cleaver
p.bx(2.05, 2.12, 1.65, 1.69, F + 0.905, F + 0.93, 'Wood')
p.blob((1.66, 1.78, F + 0.96), 0.06, 'Veg', (1.2, 1, 0.8))
p.blob((2.4, 1.6, F + 0.93), 0.09, 'Veg', (1, 1, 0.85))                       # cabbage
p.blob((2.52, 1.72, F + 0.92), 0.075, 'Veg', (1, 1, 0.85))
bowl(p, 2.6, 1.93, F + 0.84, 0.1)
bowl(p, 2.35, 1.95, F + 0.84, 0.08)
p.bx(2.7, 2.85, 1.45, 1.85, F + 0.84, F + 0.86, 'Straw')                      # tray with dough
p.blob((2.77, 1.55, F + 0.88), 0.03, 'Ceramic')
p.blob((2.77, 1.65, F + 0.88), 0.03, 'Ceramic')
p.blob((2.77, 1.75, F + 0.88), 0.03, 'Ceramic')
an_tai = p.finish()

p = Prop('K_Guizi', 'Kitchen', (1.75, 0.5, F), rmax=0.025, off=(0.35, 0))         # low cabinet at the front
p.bx(1.15, 2.35, 0.3, 0.72, F, F + 0.58, 'Wood')
p.bx(1.12, 2.38, 0.27, 0.75, F + 0.58, F + 0.63, 'Wood')
for k in range(2):
    p.bx(1.2 + k * 0.58, 1.72 + k * 0.58, 0.27, 0.3, F + 0.08, F + 0.52, 'Wood')
basket(p, 1.45, 0.5, F + 0.63, 0.13, 0.09, fill='Veg')
bowl(p, 1.95, 0.5, F + 0.63, 0.11)
p.finish()

p = Prop('K_ShuiGang', 'Kitchen', (2.95, 0.6, F), rmax=0.02, off=(0.85, 0.05))       # water tub
prof = [(0.3, F), (0.33, F + 0.08), (0.34, F + 0.08), (0.34, F + 0.12), (0.345, F + 0.3),
        (0.355, F + 0.3), (0.355, F + 0.36), (0.36, F + 0.5), (0.33, F + 0.5), (0.31, F + 0.12)]
p.lathe(prof, (2.95, 0.6, 0), 'Wood', n=14, cap_top=False, rims=[0, 8])
p.lathe([(0.315, F + 0.44)], (2.95, 0.6, 0), 'Water', n=14, cap_bottom=False)
p.finish()

p = Prop('K_Sieve', 'Kitchen', (0.1, 0.9, F + 1.35), rmax=0.01, off=(0, 0.35))   # sieve and ladle on the left wall
p.lathe([(0.2, -0.02), (0.2, 0.02), (0.17, 0.02)], (0, 0, 0), 'Straw', n=16, cap_top=False,
        M=Matrix.Translation((0.12, 0.8, F + 1.4)) @ Matrix.Rotation(math.radians(90), 4, 'Y'))
p.bx(0.1, 0.13, 1.13, 1.17, F + 1.0, F + 1.5, 'Wood')
p.lathe([(0.06, -0.02), (0.06, 0.02)], (0, 0, 0), 'Iron', n=10,
        M=Matrix.Translation((0.14, 1.15, F + 0.98)) @ Matrix.Rotation(math.radians(90), 4, 'Y'))
p.finish()


# ---------------- 走廊 corridor (走廊.png): kitchen → hall along the back line
# Runs along x behind the kitchen's back wall line: an open doorframe on the kitchen side, the hall's
# left wall (with a curtained opening) on the other, a stone-dado wall behind, the front left open.
CL, CW = 3.0, 1.3                  # length and width
CX0, CX1 = KX, KX + CL
CY0, CY1 = KY - CW, KY

p = Prop('C_Plinth', 'Corridor', ((CX0 + CX1) / 2, (CY0 + CY1) / 2, 0), rmax=0.03)
p.bx(CX0 + 0.1, CX1 - 0.1, CY0 - 0.1, CY1 + 0.1, 0, 0.22, 'Stone')
p.bx(CX0 + 0.1, CX1 - 0.1, CY0 - 0.08, CY1 + 0.08, 0.22, F - 0.04, 'Stone')
n = int((CL - 0.2) / 0.34)
for k in range(n):  # kerb stones along the open front
    x0 = CX0 + 0.1 + k * (CL - 0.2) / n
    p.bx(x0 + 0.005, x0 + (CL - 0.2) / n - 0.005, CY0 - 0.1, CY0 + 0.16, F - 0.05, F + 0.01, 'Stone')
p.finish()

p = Prop('C_Floor', 'Corridor', ((CX0 + CX1) / 2, (CY0 + CY1) / 2, F), rmax=0.02)
nx, ny = round((CL - 0.2) / 0.36), 3
cw, ch = (CL - 0.2) / nx, (CY1 - 0.08 - CY0 - 0.16) / ny
for i in range(nx):
    for j in range(ny):
        x0, y0 = CX0 + 0.1 + i * cw, CY0 + 0.16 + j * ch
        p.bx(x0 + 0.0125, x0 + cw - 0.0125, y0 + 0.0125, y0 + ch - 0.0125, F - 0.04, F + 0.012 + random.uniform(0, 0.006),
             'Tile', open_bottom=True, top_only=True)
p.finish()

p = Prop('C_Walls', 'Corridor', ((CX0 + CX1) / 2, CY1, F), rmax=0.03)
# back wall: its end posts are the kitchen's and the hall's corner posts
M, s_ = wall(p, 'x', (CX0, CY1), -1, CL, [1.0, 2.0], [(0.0, 1.0, 'dado'), (1.0, 2.0, 'dado'), (2.0, CL, 'dado')],
             brackets=[0.0, 1.0, 2.0, CL])
wall_lantern(p, CX0 + 1.0, CY1 - 0.09, (0, -1))
# kitchen-side doorframe across the corridor
wall(p, 'y', (CX0, CY0), 1, CW, [0.0], [(0.0, CW, 'opening')], brackets=[0.0, CW])
p.finish()

# ---------------- 前堂 hall
p = Prop('D_Plinth', 'Hall', ((DX0 + DX1) / 2, (DY0 + DY1) / 2, 0), rmax=0.03)
p.bx(DX0 - 0.1, DX1 + 0.1, DY0 - 0.1, DY1 + 0.1, 0, 0.22, 'Stone')
p.bx(DX0 - 0.08, DX1 + 0.08, DY0 - 0.08, DY1 + 0.08, 0.22, F - 0.04, 'Stone')
n = int((DX1 - DX0 + 0.2) / 0.36)
for k in range(n):
    x0 = DX0 - 0.1 + k * (DX1 - DX0 + 0.2) / n
    if 6.55 < x0 + 0.18 < 7.75:
        continue  # the steps take this bit
    p.bx(x0 + 0.005, x0 + (DX1 - DX0 + 0.2) / n - 0.005, DY0 - 0.1, DY0 + 0.16, F - 0.05, F + 0.005, 'Stone')
n = int((DY1 - DY0) / 0.36)
for k in range(n):
    y0 = DY0 + 0.16 + k * (DY1 - DY0 - 0.06) / n
    p.bx(DX1 - 0.16, DX1 + 0.1, y0 + 0.005, y0 + (DY1 - DY0 - 0.06) / n - 0.005, F - 0.05, F + 0.005, 'Stone')
steps(p, 6.6, 7.7, DY0 - 0.1, 3, 0.27, -1)
p.finish()

p = Prop('D_Floor', 'Hall', ((DX0 + DX1) / 2, (DY0 + DY1) / 2, F), rmax=0.012)
pw = 0.2
yy = DY0 + 0.16
row = 0
while yy < DY1 - 0.08:
    y1 = min(yy + pw, DY1 - 0.06)
    xx = DX0 + 0.06
    offs = [0.0, 0.9, 0.45, 1.35][row % 4]
    cuts = [xx] + [c for c in (DX0 + 0.06 + offs + 1.8 * k for k in range(1, 5)) if xx + 0.3 < c < DX1 - 0.46] + [DX1 - 0.16]
    for a, b in zip(cuts, cuts[1:]):
        p.bx(a + 0.004, b - 0.004, yy + 0.005, y1 - 0.005, F - 0.04, F + 0.008, 'WoodFloor', open_bottom=True, top_only=True)
    yy = y1
    row += 1
p.finish()

p = Prop('D_Walls', 'Hall', (DX0, DY1, F), rmax=0.03)
L1 = DY1 - DY0
DOOR_U0, DOOR_U1 = 0.0, CW   # the opening onto the corridor: the front end of the hall's left wall
M1, s1 = wall(p, 'y', (DX0, DY0), 1, L1, [DOOR_U0, DOOR_U1, 2.5, 3.6, L1],
              [(DOOR_U0, DOOR_U1, 'opening'), (DOOR_U1, 2.5, 'window'), (2.5, 3.6, 'window'), (3.6, L1, 'plaster')],
              brackets=[DOOR_U0, DOOR_U1])
curtain(p, M1, s1, DOOR_U0 + 0.1, DOOR_U1 - 0.1, F + H - 0.42, drop=0.62, strips=2)   # 门帘 at the corridor's end
curtain(p, M1, s1, DOOR_U1 + 0.1, 2.4, F + H - 0.45)
curtain(p, M1, s1, 2.6, 3.5, F + H - 0.45)
L2 = DX1 - DX0
M2, s2 = wall(p, 'x', (DX0, DY1), -1, L2, [1.1, 2.45, 3.2, 4.45, L2],
              [(0.0, 1.1, 'plaster'), (1.1, 2.45, 'window'), (2.45, 3.2, 'plaster'), (3.2, 4.45, 'window'),
               (4.45, L2, 'plaster')])
curtain(p, M2, s2, 1.2, 2.35, F + H - 0.45)
curtain(p, M2, s2, 3.3, 4.35, F + H - 0.45)
for (x, y, face) in ((DX0, DY0 + 3.6, (1, 0)), (DX0 + 2.45, DY1, (0, -1)),
                     (DX0 + 3.2, DY1, (0, -1))):
    wall_lantern(p, x + face[0] * 0.09, y + face[1] * 0.09, face)
# scroll painting (挂画) on the right-hand plaster panel
p.bx(DX0 + 4.7, DX0 + 5.2, DY1 - 0.06, DY1 - 0.045, F + 0.85, F + 1.7, 'Paper')
p.bx(DX0 + 4.66, DX0 + 5.24, DY1 - 0.08, DY1 - 0.04, F + 1.7, F + 1.74, 'Timber')
p.bx(DX0 + 4.66, DX0 + 5.24, DY1 - 0.08, DY1 - 0.04, F + 0.81, F + 0.85, 'Timber')
p.finish()

p = Prop('D_Railings', 'Hall', ((DX0 + DX1) / 2, DY0, F), rmax=0.02)
railing(p, DX0 + 0.05, DY0 - 0.02, 6.55, DY0 - 0.02, posts=2)
railing(p, 7.75, DY0 - 0.02, 9.6, DY0 - 0.02, posts=2)
railing(p, DX1 - 0.02, DY1 - 1.3, DX1 - 0.02, DY1 - 0.05, posts=1)
p.finish()

p = Prop('D_Path', 'Hall', (6.4, 2.4, 0), rmax=0.02)             # stepping stones toward the street
for i, (x, y, w, d) in enumerate(((7.1, 2.35, 0.9, 0.42), (6.7, 1.85, 0.7, 0.4), (7.35, 1.8, 0.45, 0.38),
                                   (6.35, 1.35, 0.6, 0.38), (6.95, 1.3, 0.5, 0.36), (6.0, 0.85, 0.55, 0.4))):
    p.box((x, y, 0.02), (w, d, 0.06), 'Stone', rot=random.uniform(-4, 4))
p.finish()

TX, TY = 7.75, 6.0
p = table('Hall', 'D_Table_1', TX, TY)
for dx, dy in ((0.22, -0.2), (-0.2, 0.22)):
    p.lathe([(0.03, F + 0.78), (0.045, F + 0.84), (0.04, F + 0.84)], (TX + dx, TY + dy, 0), 'Ceramic', n=10, cap_top=False)
p.finish()
for i, (dx, dy) in enumerate(((0, -0.78), (0.78, 0), (0, 0.78), (-0.78, 0))):
    stool('Hall', f'D_Stool_{i + 1}', TX + dx, TY + dy)

p = Prop('D_Cabinet', 'Hall', (9.6, 7.95, F), rmax=0.025)         # side cabinet
p.bx(9.05, 10.15, 7.72, 8.1, F, F + 0.75, 'Wood')
p.bx(9.02, 10.18, 7.69, 8.12, F + 0.75, F + 0.8, 'Wood')
for k in range(2):
    p.bx(9.1 + k * 0.53, 9.6 + k * 0.53, 7.69, 7.72, F + 0.1, F + 0.68, 'Wood')
p.finish()
# potted plants and flowers are left out until their own reference art arrives

# where guests queue when the table is taken: on the stepping stones in front of the hall steps
for i, (x, y) in enumerate(((7.1, 2.35), (6.7, 1.85), (7.35, 1.8), (6.35, 1.35))):
    K.marker(f'Spot_Queue_{i + 1}', (x, y, 0.05), 'Hall')

# The hall was laid out with its left wall at x = 4.9 and its front at y = 3.6; slide it so the
# opening in that wall meets the corridor's far end.
group('Hall').location = (CX1 - DX0, CY0 - (DY0 + DOOR_U0), 0)
bpy.context.view_layer.update()


K.finish_level(OUT, RENDER, WC, closeups=(('closeup_kitchen.png', 'K_AnTai'), ('closeup_hall.png', 'D_Table_1'),
                                         ('closeup_corridor.png', 'C_Walls')))
