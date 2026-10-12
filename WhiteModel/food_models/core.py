"""What the food models share: the palette and its gloss, the Part mesh builder, vessels, sauces, cut pieces,
garnish, fish bodies, sacks and baskets, and the helpers for matching the art."""
import json
import math
import random
from contextlib import contextmanager

import bmesh
import bpy
from mathutils import Matrix, Vector


CLAY = (0.8, 0.8, 0.8)

# toon lit / shade (sRGB), picked from the dish art; merged into the Unity palette
PALETTE = {
    'Celadon':    ('#bcd5c1', '#93b39e'),   # 青瓷 bowl and plate
    'Broth':      ('#ecd997', '#cdb66c'),
    'Noodle':     ('#f7eed6', '#dfcfa3'),
    'Greens':     ('#a6cf73', '#77a24a'),
    'Scallion':   ('#7fb54e', '#5a8a33'),
    'Bread':      ('#f0d49a', '#d2a764'),
    'Char':       ('#c07a3a', '#95562a'),
    'WontonSkin': ('#f6ecd3', '#dccaa0'),
    'Meat':       ('#e3aaa0', '#c3847a'),
    # ingredients and seasonings
    'Burlap':     ('#e6d2a6', '#c5aa7b'),   # 面粉 sack
    'Flour':      ('#fbf7ee', '#e3dccd'),
    'LightWood':  ('#e2b37c', '#bf8a52'),   # scoops, spoons
    'Stem':       ('#eef0d2', '#cdd3a4'),   # pale stalks of the greens
    'Fat':        ('#f7e2d8', '#dcbcae'),
    'Salt':       ('#fdfbf6', '#e4e0d6'),
    'Jar':        ('#efe9d4', '#cfc6a8'),   # the cream salt jar
    'Clay':       ('#e4ab5d', '#c0843b'),   # oil jug
    'Oil':        ('#f5c93f', '#d9a520'),
    'ScallionWhite': ('#f6f4e6', '#d9d6bf'),
    'Twine':      ('#dcc07a', '#b89a55'),
    'Ginger':     ('#e6c48c', '#c49b5f'),
    'GingerFlesh': ('#f7e49c', '#dcc36c'),
    # plated meat, poultry, tofu and fish
    'ChickenMeat': ('#f8c0a6', '#e39a84'),   # raw breast and its cubes
    'WingSkin':   ('#fbd8c2', '#eab196'),
    'WingCut':    ('#e98a7e', '#c8665d'),   # pink meat at the cut joints
    'DuckSkin':   ('#fce4c4', '#efbd97'),
    'DuckBill':   ('#eeb25c', '#cc8a38'),
    'KidneyRed':  ('#bb4a4d', '#923338'),
    'TofuWhite':  ('#fcf0d6', '#e6cba4'),
    'PorkSkin':   ('#fad5ba', '#efb999'),
    'FishBack':   ('#a39d94', '#7e7870'),   # grey back of the carp and the big fish head
    'FishBelly':  ('#f2ebe2', '#d6c9ba'),
    'FishFin':    ('#f0c1a6', '#d69c80'),
    'FishIris':   ('#dcb460', '#b88c3e'),
    'FishEye':    ('#3d322b', '#2b231e'),   # pupils of fish, crab and duck
    'FishGill':   ('#efb6aa', '#d39488'),   # gills, mouths and the cut face of the fish head
    'MandarinSkin': ('#cdb46f', '#a68d4c'),
    'MandarinSpot': ('#4f4429', '#3b331f'),
    'MandarinFin': ('#e2c27e', '#c4a160'),
    'CrabShell':  ('#7f8f99', '#5e6d77'),
    'CrabBelly':  ('#efc690', '#cfa067'),   # underside and claw tips
    # sacks, parcels, pots and baskets
    'RiceGrain':  ('#fdf5e1', '#e9d3ab'),
    'Wicker':     ('#efc685', '#c8955a'),   # woven bamboo baskets and trays
    'WickerBind': ('#f7e6bd', '#d8c191'),   # the pale wraps round their rims
    'WickerBindGreen': ('#c5c27c', '#9c9a52'),   # green wraps of the rice basket
    'BundleCloth': ('#ece8d0', '#c8c2a0'),   # the sage-tinted cloth of the rice bundle
    'WrapPaper':  ('#f0d3a3', '#cfa572'),   # kraft paper of the parcels
    'Pickle':     ('#f5df8c', '#d5b552'),   # salted pickle shreds and 酸菜, with their dark leaves
    'PickleLeaf': ('#adab52', '#828034'),
    'Scallop':    ('#f9bb5c', '#e3973a'),   # dried scallops: fibrous sides, pale cut top
    'ScallopTop': ('#fde391', '#efc466'),
    'Shrimp':     ('#fa9c66', '#e26e42'),
    'StarchBag':  ('#fae09b', '#e4b866'),
    'CornCob':    ('#fcc54c', '#e9a02e'),
    'ClayPot':    ('#dc9a68', '#b6704b'),
    'Pancake':    ('#fcefcf', '#ead09d'),
    'EggShell':   ('#fde4cd', '#efbf9c'),
    # vegetables, seasoning vessels and drinks
    'RadishWhite': ('#f7efdd', '#dcc9a6'),
    'RadishFlesh': ('#fcf8ee', '#e6dcc6'),  # cut faces of the slices
    'RadishTop':  ('#e3df9c', '#bfbd68'),   # green shoulder and leaf stalks
    'RadishLeaf': ('#8db158', '#62863a'),
    'CucumberGreen': ('#6f8f41', '#4f6a2d'),
    'CucumberFlesh': ('#f4efc0', '#dcd38f'),
    'CucumberSeed': ('#e6dc8e', '#ccc06a'),
    'CalyxGreen': ('#99a346', '#6f7a2d'),   # tomato calyx, chilli and cucumber stalks, bamboo tips
    'BambooHusk': ('#d59b5f', '#a86b3a'),
    'BambooFlesh': ('#f9e6ae', '#e3c47c'),
    'PerillaPurple': ('#984a7a', '#6e3058'),
    'PerillaDeep': ('#7a3a68', '#562848'),  # the darker leaves of the bunch
    'PerillaGreen': ('#a3b065', '#7a8642'),
    'ShiitakeCap': ('#b06a3e', '#86492a'),
    'ShiitakeFlesh': ('#f6dfba', '#dcb98a'),  # gills, stem and the cross cut
    'TomatoRed':  ('#f1532f', '#c9301c'),
    'TomatoFlesh': ('#f8925c', '#e06c3e'),
    'TomatoSeed': ('#f8c45e', '#e0a040'),
    'ChiliRed':   ('#e5392a', '#b3221c'),
    'PotatoSkin': ('#e8b563', '#c4893f'),
    'PotatoFlesh': ('#faeaa6', '#e6cd78'),
    'PotatoEye':  ('#9e6532', '#764720'),
    'GarlicSkin': ('#f8eedf', '#dcc3b6'),
    'GarlicClove': ('#f9ecc8', '#e3cc97'),
    'GarlicPeel': ('#ebc4ad', '#c99782'),
    'GarlicStreak': ('#c99aa6', '#a57a86'),  # purple lines down the bulb
    'SugarWhite': ('#fbf1df', '#e6d2ae'),
    'RockSugar':  ('#f6c979', '#dca452'),
    'VinegarGlaze': ('#7d4129', '#552a19'),
    'VinegarDark': ('#6f2b13', '#4c1a0a'),
    'JugStopper': ('#b5714a', '#8a5233'),
    'RiceWine':   ('#efe2ab', '#d5c483'),
    'ColaDark':   ('#7a3018', '#541d0c'),
    'LabelRed':   ('#e0453a', '#b52e25'),   # cola label and bottle cap
    'BottleGlass': ('#e0e8d4', '#b5c5ae'),
    # the cooked dishes (D04–D23): shared sauces
    'ChiliOil':   ('#d8482c', '#a83020'),   # red chilli oil
    'Sauce':      ('#b5652e', '#8a4620'),   # soy-brown sauce and gravy
    # dishes: 碗菜与冷菜
    'Jelly':      ('#f9d896', '#efb565'),   # 水晶脍 aspic, pale amber
    'BokChoy':    ('#5f8f3c', '#406c27'),   # dark green leaves of bok choy
    'PorkLean':   ('#efc3a6', '#d39a7c'),   # sliced braised pork
    'ColdNoodle': ('#f7dcaa', '#e5b676'),   # 冷淘 noodles, dressed and a little orange
    'ClearBroth': ('#f2e5b8', '#d6c08a'),   # the pale broth of 文思豆腐
    'MapoTofu':   ('#fbdc9e', '#eeb062'),   # tofu stained by chilli oil
    'MincedPork': ('#a06038', '#734025'),
    'SourBroth':  ('#f3d36c', '#d8ae42'),   # 酸菜鱼 broth
    'SpicyBroth': ('#f0bc42', '#d39226'),   # the same with chilli in it
    'SauerLeaf':  ('#78883a', '#56652a'),   # the dark leaves of 酸菜 in the broth
    # dishes: 鱼蟹
    'FriedSkin':  ('#de7c2c', '#b85e1a'),   # the pan-fried fish of 煎鱼饭: its orange crust
    'FriedBelly': ('#f0c98a', '#d29f5e'),
    'FriedFin':   ('#f4b45a', '#d08c3a'),   # crisp golden fins and tails
    'FriedCut':   ('#f8e2b0', '#e2c07e'),   # pale flesh opening along the score marks
    'BraisedSkin': ('#c98445', '#9c5c2b'),  # the darker fish of 两熟紫苏鱼
    'SpinachGreen': ('#5c9443', '#3f6e2f'),  # dark leafy greens
    'RawFish':    ('#fbe5d8', '#e9c5b2'),   # 玉板鲊 slices
    'SilverSkin': ('#aeb4bc', '#848b95'),
    'ZhaRice':    ('#f4dcc2', '#dcb893'),   # the fermented rice of 玉板鲊
    'CrispPiece': ('#fea232', '#f07a14'),   # 松鼠鳜鱼's crisp pieces, golden orange
    'CrispHead':  ('#f2a04a', '#dc7e30'),
    'SweetSour':  ('#e8542e', '#c03a1d'),   # sweet-sour sauce
    'WineBroth':  ('#cdb36a', '#a88d48'),   # 酒蟹's wine, olive-gold
    'CrabMeat':   ('#f8e4bf', '#e2ba86'),   # milky, warm: the wine shows through it
    'CrabRoe':    ('#f7941e', '#d8711a'),
    'DrunkShell': ('#a08a4e', '#796838'),   # khaki-olive shells of the wine-soaked crabs
    'CrabClaw':   ('#f09a62', '#d27a44'),
    'ChiliOrange': ('#f2773a', '#cf5322'),   # orange bits among the chopped chilli
    # dishes: 炒菜、禽肉与煲
    'TomatoJuice': ('#ee7a3c', '#cc5a26'),   # the red-orange juice under 番茄炒蛋
    'EggYolk':    ('#ffe47c', '#f9c458'),   # scrambled egg, light gold as in 番茄炒蛋.png
    'GlazedChicken': ('#eaa462', '#c4793c'),   # 宫保鸡丁 chicken in its glaze
    'KungPaoSauce': ('#b8432a', '#8c2e1b'),
    'ColaWing':   ('#cd6934', '#9a421f'),   # cola-braised wings
    'WingKnob':   ('#efd2a8', '#cfa97c'),   # the cut joint at a wing's end
    'ColaSauce':  ('#93401d', '#6c2b13'),
    'StewGravy':  ('#e9a64a', '#c98330'),   # 土豆炖肉 gravy
    'StewPotato': ('#f7cb5c', '#dea53c'),   # braised potato, more golden than raw
    'BraisedPork': ('#a94a2b', '#7e331c'),  # the lean of braised pork belly
    'BraisedFat': ('#f3d3a6', '#d8ad7a'),
    'LizhiKidney': ('#dc7a4b', '#b05534'),  # scored, curled kidney
    'LizhiScore': ('#b9542f', '#8a3b20'),   # the darker squares of its scoring
    'DarkGreens': ('#3f7a34', '#2c5a25'),   # cooked leafy greens
    'LightSauce': ('#e3a465', '#c37f40'),   # the light glaze of 荔枝腰子
    'RoastDuck':  ('#c9512a', '#99381c'),   # lacquered roast-duck skin
    'DuckMeat':   ('#f5ddcb', '#dfbca4'),
    'Earthenware': ('#c4743f', '#97522a'),  # 佛跳墙 jar and lid
    'GoldenBroth': ('#f0c35a', '#d49c34'),
    'StewChicken': ('#f6e3c6', '#ddc29c'),  # chicken stewed pale
    # raw meats as the art paints them (sampled from 猪肉.png, 鸡肉.png), for the detail textures
    'RawPork':    ('#e28474', '#cb6457'),   # lean pork, marbled with fat
    'PorkFat':    ('#f9ddcb', '#edb9a1'),
    'RawChicken': ('#f8c6aa', '#e1856a'),   # pale peach-pink breast, fibrous
}

# Gloss (0–1) of each colour in Unity's watercolor material, as in the dish art: sauces, glazes, broths and oil
# shine, glazed pots and porcelain and raw meat and fish less, dry things (flour, rice, bread, sacks, paper, wood,
# baskets, skins) not at all; any other colour has GLOSS_DEFAULT.
GLOSS_DEFAULT = 0.3

GLOSS = {
    **dict.fromkeys(('Sauce', 'ChiliOil', 'SweetSour', 'ColaSauce', 'ColaWing', 'KungPaoSauce', 'GlazedChicken',
                     'LightSauce', 'TomatoJuice', 'StewGravy', 'StewPotato', 'RoastDuck', 'BraisedPork', 'BraisedSkin',
                     'FriedSkin', 'CrispPiece', 'CrispHead', 'LizhiKidney', 'LizhiScore', 'KidneyRed', 'Oil', 'VinegarDark',
                     'Broth', 'SourBroth', 'SpicyBroth', 'ClearBroth', 'GoldenBroth', 'WineBroth', 'RiceWine', 'ColaDark',
                     'Jelly', 'MapoTofu', 'TomatoRed', 'ChiliRed', 'ChiliOrange', 'CrabRoe', 'FishEye', 'FishIris',
                     'BottleGlass', 'RockSugar'), 0.8),
    **dict.fromkeys(('Celadon', 'ClayPot', 'Earthenware', 'Jar', 'VinegarGlaze', 'Clay', 'Meat', 'Fat', 'PorkLean',
                     'BraisedFat', 'ChickenMeat', 'WingSkin', 'WingCut', 'DuckSkin', 'DuckMeat', 'PorkSkin', 'FishBack',
                     'FishBelly', 'MandarinSkin', 'RawFish', 'SilverSkin', 'CrabShell', 'DrunkShell', 'CrabMeat', 'Shrimp',
                     'CucumberGreen', 'EggYolk', 'Noodle', 'ColdNoodle', 'MincedPork', 'StewChicken',
                     'RawPork', 'PorkFat', 'RawChicken', 'DuckCut'), 0.5),
    **dict.fromkeys(('Flour', 'Burlap', 'RiceGrain', 'ZhaRice', 'Bread', 'Char', 'Pancake', 'WrapPaper', 'Twine',
                     'LightWood', 'Wicker', 'WickerBind', 'WickerBindGreen', 'BundleCloth', 'StarchBag', 'Salt',
                     'SugarWhite', 'PotatoSkin', 'PotatoEye', 'GarlicSkin', 'GarlicPeel', 'GarlicStreak', 'Ginger',
                     'BambooHusk', 'LabelRed', 'CornCob', 'JugStopper', 'Scallop', 'ScallopTop', 'EggShell'), 0.0),
}

# How much of the watercolor material's rich food colour (0–1) each colour takes: the food gets all of it, the
# sacks, paper, baskets, wood, twine and porcelain round it half, so that they don't outshine it. Raw meat and
# skin take little: the boost pushes their pale pinks toward orange and tan, and the art paints them pale. Scrambled
# egg takes some: all of it turns the yellow mustard, none leaves it beige.
VIVID = {**dict.fromkeys(('Burlap', 'WrapPaper', 'Twine', 'Wicker', 'WickerBind', 'WickerBindGreen', 'BundleCloth',
                          'LightWood', 'StarchBag', 'JugStopper', 'Celadon'), 0.5),
         'Greens': 0.75, 'RawPork': 0.5, 'PorkFat': 0.3, 'RawChicken': 0.4, 'ChickenMeat': 0.4, 'DuckCut': 0.4,
         'WingSkin': 0.3, 'DuckSkin': 0.15, 'PorkSkin': 0.3, 'Fat': 0.4, 'KidneyFat': 0.4, 'EggYolk': 0.6}

# Colours painted across the surface (Part.tint): each vertex of the model carries a colour that the material's
# own leans toward, for the gradients and blotches of the art that a flat colour can't give (a fish's dark crown
# fading into its pale cheek, a crab's legs warming to orange at the joints). Listed here they get Unity's
# _VertexTint 1; anything else ignores the vertex colours.
VTINT = {}

# Clear glass (the cola bottle): colour → how opaque it is where it faces the eye and at its edges, its highlights,
# its outline width and its draw order among transparent things (the far side lower), for Unity's
# WatercolorGlass; the colour itself is the palette's.
GLASS = {}

# The ink line round small things (grains of rice): colour → its width (px at 1080p; the default is 1.6), thinner, so
# that each little piece doesn't read as a dark-rimmed chip.
OUTLINE = {}

# Painted surface of the meat and the egg in the watercolor material: colour → (texture in Unity/Assets/Art/Textures,
# made by food_textures.py; tiles per metre; the colour its pattern tints toward; how far, 0–1; relief in mm). The
# texture is box-projected in object space, so it needs no UVs and suits any model. marble: fat veins through lean;
# fiber: muscle grain; pores: follicles of poultry and pork skin; mottle: soft blotches (kidney, fat); curd: the
# puffed folds of scrambled egg with golden creases between them.
DETAIL = {
    # raw pork: white fat marbling through pink lean, and the fat itself faintly mottled
    'RawPork':      ('food_marble', 13, '#f9ddcb', 0.9, 0.7),
    'Meat':         ('food_marble', 13, '#f7e2d8', 0.9, 0.7),
    'PorkFat':      ('food_mottle', 9, '#f2c2ad', 0.3, 0.25),
    'Fat':          ('food_mottle', 9, '#efc3b3', 0.3, 0.25),
    # raw chicken: paler streaks along the grain
    'RawChicken':   ('food_fiber', 10, '#fde8dc', 0.6, 0.8),
    'ChickenMeat':  ('food_fiber', 10, '#fde8dc', 0.6, 0.8),
    'WingCut':      ('food_fiber', 14, '#f5b8aa', 0.4, 0.3),
    'DuckCut':      ('food_fiber', 14, '#fbd6c4', 0.4, 0.3),
    # poultry skin, raw and roast: follicle dots
    'DuckSkin':     ('food_pores', 11, '#eba37f', 0.7, 0.8),
    'WingSkin':     ('food_pores', 13, '#e99a84', 0.6, 0.7),
    'RoastDuck':    ('food_pores', 7, '#8a2f15', 0.25, 0.9),
    'DuckKnob':     ('food_pores', 9, '#5e2410', 0.25, 0.6),
    'ColaWing':     ('food_pores', 8, '#7e2d0c', 0.25, 1.0),
    'StewSkin':     ('food_pores', 12, '#e3a24e', 0.3, 0.25),
    # pork skin and rind: finer pores
    'PorkSkin':     ('food_pores', 13, '#ecaa92', 0.55, 0.6),
    'SkinCurl':     ('food_pores', 15, '#eab9a0', 0.4, 0.4),
    'PorkRind':     ('food_pores', 12, '#73321a', 0.3, 0.5),
    # kidney: soft blotches
    'KidneyRed':    ('food_mottle', 9, '#d9787a', 0.35, 0.8),
    'KidneyFat':    ('food_mottle', 12, '#fbe2c8', 0.3, 0.2),
    'LizhiKidney':  ('food_mottle', 10, '#eea06c', 0.3, 0.3),
    'LizhiScore':   ('food_mottle', 10, '#d36e42', 0.3, 0.3),
    'LizhiGroove':  ('food_mottle', 10, '#c25a33', 0.2, 0.2),
    # cooked chicken and duck meat: the grain
    'GlazedChicken': ('food_fiber', 12, '#f8cf9a', 0.6, 1.0),
    'StewBreast':   ('food_fiber', 12, '#fdeacb', 0.4, 0.3),
    'ChickenFiber': ('food_fiber', 14, '#dc8d52', 0.3, 0.3),
    'StewChicken':  ('food_fiber', 12, '#fdf0dc', 0.4, 0.3),
    'DuckMeat':     ('food_fiber', 12, '#fcefe6', 0.4, 0.3),
    'KaoyaMeat':    ('food_fiber', 12, '#fbe6da', 0.5, 0.5),
    # cooked pork: the grain of the lean, mottled fat
    'PorkLean':     ('food_fiber', 13, '#f9dfcf', 0.4, 0.3),
    'BraisedPork':  ('food_fiber', 13, '#c86c42', 0.5, 1.0),
    'BellyLean':    ('food_fiber', 13, '#f0b582', 0.35, 0.3),
    'MincedPork':   ('food_fiber', 18, '#bd7f53', 0.4, 0.35),
    'BraisedFat':   ('food_mottle', 10, '#f9e4c4', 0.25, 0.2),
    'WontonFill':   ('food_mottle', 14, '#ecc6ba', 0.3, 0.2),
    'WingKnob':     ('food_mottle', 14, '#f7e4c4', 0.25, 0.2),
    # scrambled egg: puffed folds with golden creases between them
    'EggYolk':      ('food_curd', 14, '#f0a03a', 0.5, 0.35),
}


def log(msg):
    print(f'[dishes] {msg}', flush=True)


def new_scene():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.context.preferences.filepaths.save_version = 0

MATS = {}


def linear(hexc):
    """'#rrggbb' as linear RGB, the way Unity takes colours in its linear colour space."""
    return tuple(((c / 255) / 12.92) if c / 255 <= 0.04045 else ((c / 255 + 0.055) / 1.055) ** 2.4
                 for c in (int(hexc[i:i + 2], 16) for i in (1, 3, 5)))


def material(name):
    mat = bpy.data.materials.get('M_' + name) or bpy.data.materials.new('M_' + name)
    mat.diffuse_color = (*CLAY, 1.0)
    return mat


class Part:
    """One dish = one mesh; geometry is added piece by piece, each piece with its material."""

    def __init__(self):
        self.bm = bmesh.new()
        self.mats = []

    def _mi(self, m):
        if m not in self.mats:
            self.mats.append(m)
        return self.mats.index(m)

    def _commit(self, tmp, mat, edges=(), r=0.0, seg=2):
        if edges and r > 1e-5:
            tmp.normal_update()   # the bevel goes by the face normals, which moving the vertices left stale
            bmesh.ops.bevel(tmp, geom=list(edges), offset=r, offset_type='OFFSET', segments=seg, profile=0.5,
                            affect='EDGES', clamp_overlap=True)
        mi = self._mi(mat)
        vmap = {v: self.bm.verts.new(v.co) for v in tmp.verts}
        for f in tmp.faces:
            self.bm.faces.new([vmap[v] for v in f.verts]).material_index = mi
        tmp.free()

    def lathe(self, profile, mat, n=16, M=Matrix(), close_ends=True, deform=None):
        """Surface of revolution about Z; profile [(r, z)] in order. A ring of radius 0 becomes a single
        point (a fan), so closed shapes like flatbreads need no caps."""
        tmp = bmesh.new()
        rings = []
        for rad, z in profile:
            if rad < 1e-6:
                rings.append([tmp.verts.new(M @ Vector((0, 0, z)))])
            else:
                pts = [Vector((rad * math.cos(2 * math.pi * k / n), rad * math.sin(2 * math.pi * k / n), z)) for k in range(n)]
                rings.append([tmp.verts.new(M @ (deform(q) if deform else q)) for q in pts])
        for ra, rb in zip(rings, rings[1:]):
            if len(ra) == 1 and len(rb) == 1:
                continue
            for k in range(n):
                if len(ra) == 1:
                    tmp.faces.new((ra[0], rb[(k + 1) % n], rb[k]))
                elif len(rb) == 1:
                    tmp.faces.new((ra[k], ra[(k + 1) % n], rb[0]))
                else:
                    tmp.faces.new((ra[k], ra[(k + 1) % n], rb[(k + 1) % n], rb[k]))
        if close_ends:
            if len(rings[0]) > 1:
                tmp.faces.new(list(reversed(rings[0])))
            if len(rings[-1]) > 1:
                tmp.faces.new(rings[-1])
        self._commit(tmp, mat)

    def blob(self, c, r, mat, squash=(1, 1, 1), segs=(8, 5), rot=0.0, deform=None):
        """Low-poly ellipsoid; `deform(v_local) -> v_local` shapes it before it is placed."""
        tmp = bmesh.new()
        bmesh.ops.create_uvsphere(tmp, u_segments=segs[0], v_segments=segs[1], radius=1.0)
        for v in tmp.verts:
            p = Vector((v.co.x * r * squash[0], v.co.y * r * squash[1], v.co.z * r * squash[2]))
            if deform:
                p = deform(p)
            v.co = Matrix.Translation(Vector(c)) @ Matrix.Rotation(rot, 4, 'Z') @ p
        self._commit(tmp, mat)

    def box(self, c, size, mat, r=0.0, rot=0.0, M=Matrix(), seg=2):
        """Box of full size (x, y, z) centred on c, turned `rot` about Z, then moved by M; edges rounded by r."""
        tmp = bmesh.new()
        bmesh.ops.create_cube(tmp, size=1.0)
        T = M @ Matrix.Translation(Vector(c)) @ Matrix.Rotation(rot, 4, 'Z') @ Matrix.Diagonal((*size, 1.0))
        for v in tmp.verts:
            v.co = T @ v.co
        self._commit(tmp, mat, edges=tmp.edges[:], r=min(r, 0.45 * min(size)), seg=seg)

    def tube(self, pts, radius, mat, sides=5):
        """A soft tube along a polyline (noodles), with rounded ends. Its rings are oriented from the
        tangent × Z, so a path that turns vertical or doubles back sideways twists inside out: split it."""
        tmp = bmesh.new()
        rings = []
        for i, p in enumerate(pts):
            p = Vector(p)
            t = (Vector(pts[min(i + 1, len(pts) - 1)]) - Vector(pts[max(i - 1, 0)])).normalized()
            a = t.cross(Vector((0, 0, 1)))
            if a.length < 1e-4:
                a = Vector((1, 0, 0))
            a.normalize()
            b = t.cross(a)
            rings.append([tmp.verts.new(p + radius * (math.cos(2 * math.pi * k / sides) * a + math.sin(2 * math.pi * k / sides) * b))
                          for k in range(sides)])
        for ra, rb in zip(rings, rings[1:]):
            for k in range(sides):
                tmp.faces.new((ra[k], ra[(k + 1) % sides], rb[(k + 1) % sides], rb[k]))
        tmp.faces.new(list(reversed(rings[0])))
        tmp.faces.new(rings[-1])
        self._commit(tmp, mat)

    @contextmanager
    def soft(self, levels=1):
        """Pieces added inside the block are rounded by Catmull-Clark subdivision: build them as coarse cages and
        they come out smooth, with rounded corners (圆角) and no facets or sharp points. Each level multiplies
        their faces by 4."""
        outer, self.bm = self.bm, bmesh.new()
        try:
            yield
        finally:
            cage, self.bm = self.bm, outer
            me = bpy.data.meshes.new('soft')
            cage.to_mesh(me)
            cage.free()
            ob = bpy.data.objects.new('soft', me)
            bpy.context.scene.collection.objects.link(ob)
            md = ob.modifiers.new('Subsurf', 'SUBSURF')
            md.levels = md.render_levels = levels
            dg = bpy.context.evaluated_depsgraph_get()
            tmp = bmesh.new()
            tmp.from_mesh(ob.evaluated_get(dg).to_mesh())
            ob.evaluated_get(dg).to_mesh_clear()
            vmap = {v: self.bm.verts.new(v.co) for v in tmp.verts}
            for f in tmp.faces:
                self.bm.faces.new([vmap[v] for v in f.verts]).material_index = f.material_index
            tmp.free()
            bpy.data.objects.remove(ob)
            bpy.data.meshes.remove(me)

    def tint(self, f0, field, mats=None):
        """Paints the faces added since there were f0 of them (only those in `mats`, if given) across their surface:
        field(point, normal) gives (hex colour, weight 0-1) for how far the material's own colour leans toward that
        one there (for colours in VTINT), or None to leave it. The colour is stored linear with alpha 1 - weight, so
        that white with alpha 1 (what Unity reads for a model without vertex colours) means no tint."""
        lay = self.bm.loops.layers.float_color.get('Tint') or self.bm.loops.layers.float_color.new('Tint')
        self.bm.normal_update()
        self.bm.faces.ensure_lookup_table()
        ids = None if mats is None else {self.mats.index(m) for m in mats if m in self.mats}
        seen = {}
        for f in self.bm.faces[f0:]:
            if ids is not None and f.material_index not in ids:
                continue
            for loop in f.loops:
                v = loop.vert
                if v not in seen:
                    seen[v] = field(v.co, v.normal)
                got = seen[v]
                if got is not None:
                    c = linear(got[0])
                    loop[lay] = (c[0], c[1], c[2], 1.0 - min(max(got[1], 0.0), 0.999))

    def finish(self, name, col, sharp=70):
        """The mesh as an object in col, shaded smooth; edges sharper than `sharp` degrees stay creased
        (None: none do, for the rounded models, so no facet edge shows)."""
        bm = self.bm
        bm.normal_update()
        lay = bm.loops.layers.float_color.get('Tint')
        if lay is not None:   # corners never painted (they read 0, 0, 0, 0) take no tint
            for f in bm.faces:
                for loop in f.loops:
                    if loop[lay][3] == 0.0:
                        loop[lay] = (1.0, 1.0, 1.0, 1.0)
        me = bpy.data.meshes.new(name)
        bm.to_mesh(me)
        bm.free()
        me.shade_smooth()
        if sharp is not None:
            me.set_sharp_from_angle(angle=math.radians(sharp))
        for m in self.mats:
            me.materials.append(material(m))
        ob = bpy.data.objects.new(name, me)
        col.objects.link(ob)
        md = ob.modifiers.new('WeightedNormal', 'WEIGHTED_NORMAL')
        md.mode = 'FACE_AREA'
        md.weight = 50
        md.keep_sharp = True
        return ob


def bowl(p, rim_r=0.08, h=0.07, foot_r=0.035, broth_z=0.055, n=14, fill='Broth', deform=None):
    """青瓷碗 with a foot ring and a rolled rim; the inside ends at the broth (or whatever `fill` is), which caps
    it. `deform` (lobed() for a flower-shaped rim) shapes the wall and the fill alike, so they still meet."""
    prof = [(foot_r * 0.8, 0.0), (foot_r, 0.0), (foot_r * 1.08, 0.011),
            (rim_r * 0.72, h * 0.45), (rim_r * 0.94, h * 0.87), (rim_r, h), (rim_r - 0.004, h + 0.003),
            (rim_r - 0.008, h), (rim_r * 0.84, broth_z)]
    p.lathe(prof, 'Celadon', n=n, close_ends=False, deform=deform)
    p.lathe([(foot_r * 0.8, 0.0), (0, 0.004)], 'Celadon', n=n, close_ends=False, deform=deform)   # underside
    p.lathe([(rim_r * 0.84, broth_z), (0, broth_z + 0.001)], fill, n=n, close_ends=False, deform=deform)
    return broth_z


def plate(p, r=0.1, h=0.022, n=12, sx=1.0, deform=None):
    """青瓷盘; sx > 1 stretches it into the oval plate that whole fish and poultry lie on, `deform` (lobed())
    scallops its rim. Its floor is at 0.008."""
    prof = [(0, 0.0), (r * 0.55, 0.0), (r * 0.6, 0.004), (r * 0.9, h * 0.8), (r, h), (r - 0.004, h + 0.002),
            (r - 0.008, h), (r * 0.62, 0.008), (0, 0.008)]
    p.lathe(prof, 'Celadon', n=n, close_ends=False, M=Matrix.Diagonal((sx, 1.0, 1.0, 1.0)), deform=deform)


def onto_plate(p, n0, r, h=0.022, sx=1.0, edge=0.62):
    """Lifts what was added to p since it had n0 vertices by how far the inside of plate(r, h, sx) has risen where it
    lies (`edge`: where the floor ends, as a share of r), so that food reaching past the floor rests on the wall
    instead of passing out through it; beyond the wall it stays at rim height."""
    p.bm.verts.ensure_lookup_table()
    f0, f1 = edge * r, r - 0.008
    for v in p.bm.verts[n0:]:
        v.co.z += (h - 0.008) * min(1.0, max(0.0, (math.hypot(v.co.x / sx, v.co.y) - f0) / (f1 - f0)))


def lobed(lobes, amount, r0, r1, phase=0.0):
    """Deform for a lathed bowl or plate: a flower-shaped rim of `lobes` scallops, `amount` of the radius deep,
    fading in from radius r0 to r1 so that the foot stays round. Lathe it with n a multiple of `lobes`."""
    def deform(q):
        f = min(1.0, max(0.0, (math.hypot(q.x, q.y) - r0) / (r1 - r0)))
        k = 1 + amount * math.cos(lobes * math.atan2(q.y, q.x) + phase) * f
        return Vector((q.x * k, q.y * k, q.z))
    return deform

ART_EL = math.radians(35)   # the art is drawn from in front, 35° up: the camera the models are matched to


def art_y(y, z, z_read=0.008):
    """Depth y of something at height z that the art_match grid (drawn at z_read) shows at y: at 35° a point
    1 cm higher looks 1.43 cm further back."""
    return y - (z - z_read) / math.tan(ART_EL)


def pool(p, r, z, mat, at=(0.0, 0.0), sx=1.0, rot=0.0, n=10, wobble=0.15, seed=0, depth=0.002):
    """A thin puddle of sauce, gravy or chilli oil r across with its top at height z, the open underside sunk
    `depth` into whatever it lies on: a disc with a wavy edge, stretched by sx along x, turned by rot, moved to
    `at`. 2n faces. On a plate keep it within the floor (0.62 of the plate's radius), or its edge pokes out through
    the wall: plate_sauce() covers floor and wall."""
    rnd = random.Random(seed)
    bumps = [rnd.uniform(-wobble, wobble) for _ in range(n)]

    def edge(q):
        k = 1 + bumps[round(math.atan2(q.y, q.x) * n / (2 * math.pi)) % n]
        return Vector((q.x * k, q.y * k, q.z))
    M = Matrix.Translation((*at, 0.0)) @ Matrix.Rotation(rot, 4, 'Z') @ Matrix.Diagonal((sx, 1.0, 1.0, 1.0))
    p.lathe([(r, z - depth), (r * 0.9, z), (0.0, z + 0.0005)], mat, n=n, M=M, deform=edge, close_ends=False)


def axes_to(z_dir, x_dir):
    """Rotation taking local z to z_dir and local x as near to x_dir as it can go."""
    z = Vector(z_dir).normalized()
    y = z.cross(Vector(x_dir)).normalized()
    return Matrix((y.cross(z), y, z)).transposed().to_4x4()


def piece_in_colours(p, tmp, mats):
    """Copies tmp into p, face k in material mats[k], after turning its normals outwards: closed pieces whose faces
    differ in colour (a tomato wedge's skin and cut faces) are built in one go."""
    tmp.normal_update()   # recalc_face_normals goes by the stored normals, stale once the vertices have moved
    bmesh.ops.recalc_face_normals(tmp, faces=tmp.faces[:])
    vmap = {v: p.bm.verts.new(v.co) for v in tmp.verts}
    for f, m in zip(tmp.faces, mats):
        p.bm.faces.new([vmap[v] for v in f.verts]).material_index = p._mi(m)
    tmp.free()


def traced_surface(p, verts, tris, mat, facing):
    """A surface traced from the art (verts, triangles) into p, every triangle turned to face the way facing(a, b, c)
    says is out (> 0): an egg piece faces the camera it was traced from, the heap's surface the sky."""
    vs = [p.bm.verts.new(Vector(v)) for v in verts]
    mi = p._mi(mat)
    for a, b, c in tris:
        f = p.bm.faces.new((vs[a], vs[b], vs[c]) if facing(vs[a].co, vs[b].co, vs[c].co) >= 0 else (vs[a], vs[c], vs[b]))
        f.material_index = mi


def plate_sauce(p, mat, r=0.1, h=0.022, sx=1.0, reach=0.4, n=12, seed=0, wobble=0.3):
    """Sauce or juice over the floor of a plate(r, h, sx) and `reach` of the way up its wall, the edge wavy: it lies
    just over the plate's inside, so unlike a pool() it never shows through the outside of the plate. 2n faces."""
    f0, f1 = 0.62 * r, r - 0.008   # where the floor ends, where the inside of the wall meets the rim
    bumps = [random.Random(seed + k).uniform(-1.0, 1.0) for k in range(n)]

    def edge(q):
        rho = math.hypot(q.x, q.y)
        if rho < f0 * 1.01:
            return q
        rho2 = f0 + (rho - f0) * (1 + wobble * bumps[round(math.atan2(q.y, q.x) * n / (2 * math.pi)) % n])
        return Vector((q.x * rho2 / rho, q.y * rho2 / rho,
                       0.0088 + max(0.0, rho2 - f0) / (f1 - f0) * (h - 0.008)))
    p.lathe([(f0 + reach * (f1 - f0), 0.0), (f0, 0.0088), (0.0, 0.0089)], mat, n=n, close_ends=False, deform=edge,
            M=Matrix.Diagonal((sx, 1.0, 1.0, 1.0)))


def stick(p, a, b, w, t, mat, up=(0.0, 0.0, 1.0)):
    """A thin bar from a to b, w wide and t thick, its broad face turned towards `up` as far as the direction
    allows: julienne strips, shreds, cut scallion. 6 faces."""
    a, b = Vector(a), Vector(b)
    x = (b - a).normalized()
    y = Vector(up).cross(x)
    if y.length < 1e-6:
        y = Vector((0.0, 1.0, 0.0)).cross(x)
    y.normalize()
    R = Matrix((x, y, x.cross(y))).transposed().to_4x4()
    p.box((0, 0, 0), ((b - a).length, w, t), mat, M=Matrix.Translation((a + b) / 2) @ R)


def bits(p, at, spread, z, count, size, mat, seed, height=None, squash=(1.0, 1.0, 0.6), segs=(4, 2)):
    """`count` small chopped pieces (scallion, chilli, garlic) spread evenly within `spread` of `at`, lying at
    height z, or on a surface whose height at a distance d from `at` is height(d) (heap() returns one).
    2 × segs[0] faces each with the default segs."""
    rnd = random.Random(seed)
    for k in range(count):
        d = spread * math.sqrt((k + 0.5) / count)
        a = k * 2.4 + rnd.uniform(-0.4, 0.4)
        h = height(d) if height else z
        p.blob((at[0] + d * math.cos(a), at[1] + d * math.sin(a), h + size * squash[2] * 0.5), size, mat,
               squash=squash, segs=segs, rot=rnd.uniform(0, math.pi))


def in_wok_broth(p, r=0.075, z=0.008):
    p.lathe([(r, 0.0), (r, z), (0, z + 0.001)], 'Broth', n=14, close_ends=False)
    return z


def noodle_loops(p, z, rnd, loops=5, rmin=0.018, rmax=0.05, radius=0.005, mat='Noodle'):
    """Loops of noodle lying in broth (or on a heap) at height z, each an arc round the middle of the bowl."""
    for k in range(loops):
        a0 = rnd.uniform(0, 2 * math.pi)
        rad = rnd.uniform(rmin, rmax)
        pts = []
        for j in range(7):
            a = a0 + j * 0.55
            rr = rad + 0.008 * math.sin(j * 1.3 + k)
            pts.append((rr * math.cos(a), rr * math.sin(a), z + 0.004 + 0.003 * math.sin(j * 0.9 + k)))
        p.tube(pts, radius, mat, sides=4)


def moved(p, n0, M):
    """Moves what was added to p since it had n0 vertices by M: a fish is built upright, then laid down."""
    p.bm.verts.ensure_lookup_table()
    for v in p.bm.verts[n0:]:
        v.co = M @ v.co


def fin(p, outline, mat, thick=0.002, M=Matrix()):
    """A thin fin or tail in the XZ plane: a lens through the outline [(x, z)], which goes anticlockwise
    round the origin as seen from the front, puffed out by `thick` in the middle; then placed by M."""
    n = len(outline)
    p.lathe([(0, -thick), (1, 0), (0, thick)], mat, n=n, M=M @ Matrix.Rotation(math.pi / 2, 4, 'X'),
            deform=lambda q: Vector((*outline[round(math.atan2(q.y, q.x) / (2 * math.pi) * n) % n], 0.0)))


def fish_body(p, stations, back, belly, split=2.1, nb=9, nl=5):
    """A fish body along X, snout first, from stations [(x, top, bottom, half_width)]. Two lathes share the
    sections with their rings spread over complementary arcs, so the dark back meets the pale belly along the
    near flank, `split` radians round from the top."""
    st = {round(x, 5): (top, bot, hw) for x, top, bot, hw in stations}

    def section(q, n, a0, a1):
        top, bot, hw = st[round(q.z, 5)]
        a = a0 + (a1 - a0) * (round(math.atan2(q.y, q.x) / (2 * math.pi) * n) % n) / (n - 1)
        return Vector((q.z, -hw * math.sin(a), (top + bot) / 2 + (top - bot) / 2 * math.cos(a)))
    prof = [(1.0, x) for x, *_ in stations]
    p.lathe(prof, back, n=nb, deform=lambda q: section(q, nb, -split, split))
    p.lathe(prof, belly, n=nl, deform=lambda q: section(q, nl, split, 2 * math.pi - split))


def flank(stations, x, a):
    """Point on a fish body at x, `a` radians round the section from the top towards the camera, and its normal."""
    for (x0, t0, b0, w0), (x1, t1, b1, w1) in zip(stations, stations[1:]):
        if x0 <= x <= x1:
            f = (x - x0) / (x1 - x0)
            top, bot, hw = t0 + (t1 - t0) * f, b0 + (b1 - b0) * f, w0 + (w1 - w0) * f
            break
    h = (top - bot) / 2
    return (Vector((x, -hw * math.sin(a), (top + bot) / 2 + h * math.cos(a))),
            Vector((0.0, -math.sin(a) / hw, math.cos(a) / h)).normalized())


def patch(p, stations, x, a, r, mat, squash=(1, 1, 0.35), segs=(6, 3), rot=0.0, lift=0.0, wobble=0.0):
    """A flattened blob lying on the fish body at (x, a): an eye, a blotch, the gills; `wobble` makes it lobed."""
    c, nrm = flank(stations, x, a)
    R = nrm.to_track_quat('Z', 'Y').to_matrix() @ Matrix.Rotation(rot, 3, 'Z')
    p.blob(c + nrm * lift, r, mat, squash=squash, segs=segs,
           deform=lambda v: R @ (v * (1 + wobble * math.sin(3 * math.atan2(v.y, v.x)))))


def low_fins(p, stations, mat, xs):
    """Pelvic and anal fins under the belly at xs, swept back and splayed towards the camera."""
    for x in xs:
        c, nrm = flank(stations, x, 2.6)
        fin(p, [(0.026, -0.003), (0.004, 0.004), (-0.004, 0.0), (0.002, -0.005), (0.02, -0.013)], mat,
            M=Matrix.Translation(c) @ Matrix.Rotation(-1.2, 4, 'X'))

CARP = [(-0.125, 0.038, 0.018, 0.01), (-0.116, 0.052, 0.01, 0.016), (-0.1, 0.064, 0.004, 0.019),
        (-0.072, 0.078, 0.0, 0.022), (-0.035, 0.086, 0.0, 0.023), (0.01, 0.084, 0.005, 0.02),
        (0.048, 0.072, 0.019, 0.014), (0.076, 0.06, 0.031, 0.008), (0.098, 0.054, 0.038, 0.006)]

YUTOU = [(-0.082, 0.058, 0.036, 0.012), (-0.072, 0.074, 0.02, 0.021), (-0.055, 0.091, 0.008, 0.031),
         (-0.028, 0.105, 0.001, 0.04), (0.005, 0.112, 0.0, 0.045), (0.035, 0.11, 0.003, 0.044),
         (0.05, 0.104, 0.007, 0.041)]


def sacking(n, seed, dent=0.04, square=0.0, corner=0.0, top=None, flare=0.0, lift=0.0, waves=None):
    """Deform for sacks, bundles and parcels lathed with n sides: every side is dented by its own amount that
    changes with height, `square` pulls the section towards a square with corners at `corner` radians, and
    between the heights top = (z0, z1) the opening flares out in `waves` ruffles round the rim (by default a
    point on every other side), the first at `corner`, each a little different."""
    rnd = random.Random(seed)
    sides = [(rnd.uniform(-dent, dent), rnd.uniform(0, 2 * math.pi), rnd.uniform(-0.5, 0.5)) for _ in range(n)]

    def deform(v):
        a = math.atan2(v.y, v.x)
        d, ph, w = sides[round(a * n / (2 * math.pi)) % n]
        u = min(1.0, max(0.0, (v.z - top[0]) / (top[1] - top[0]))) ** 2 if top else 0.0
        tip = math.cos((waves or n / 2) * (a - corner)) + w
        k = 1 + d * math.sin(v.z * 40 + ph) + square * math.cos(4 * (a - corner)) + u * flare * (0.6 + 0.4 * tip)
        return Vector((v.x * k, v.y * k, v.z + u * lift * tip))
    return deform


def twine(p, r, z, deform, at, M=Matrix(), n=12, th=0.007, loops=2,
          ends=(((0.008, -0.01, -0.03), (0.013, -0.018, -0.065)), ((0.008, 0.01, -0.028), (0.012, 0.02, -0.06)))):
    """String tied round a neck of radius r at height z: a band that follows the sack's deform, a knot at angle
    `at`, a bow of up to two loops and the hanging ends, given as polylines of (out, along, up) offsets."""
    p.lathe([(r, z - th), (r + th, z), (r, z + th)], 'Twine', n=n, close_ends=False, deform=deform, M=M)
    out, side = Vector((math.cos(at), math.sin(at), 0.0)), Vector((-math.sin(at), math.cos(at), 0.0))
    knot = deform(out * (r + th) + Vector((0.0, 0.0, z)))

    def off(o, s, u):
        return M @ (knot + out * o + side * s + Vector((0.0, 0.0, u)))
    p.blob(off(th * 0.5, 0, 0), th * 1.8, 'Twine', segs=(6, 3), rot=at)
    for sg in (1, -1)[:loops]:   # bow loops, flopped outwards (a loop in an upright plane would twist the tube)
        loop = [(0.02, 0.016), (0.042, 0.013), (0.047, -0.005), (0.022, -0.008)]
        p.tube([off(0, 0, 0)] + [off(0.006 + 0.8 * w, sg * s, 0.6 * w) for s, w in loop] + [off(0, 0, 0)], th * 0.8,
               'Twine', sides=4)
    for e in ends:
        p.tube([off(0, 0, 0)] + [off(*q) for q in e], th * 0.8, 'Twine', sides=4)


def heap(p, at, r, z, hz, mat, n=12):
    """A rounded heap r wide rising hz above z (rice, pickles, cabbage); returns its height at a distance d from
    the middle, for laying things on it."""
    prof = [(r, z), (r * 0.75, z + hz * 0.55), (r * 0.4, z + hz * 0.9), (0.0, z + hz)]
    p.lathe(prof, mat, n=n, close_ends=False, M=Matrix.Translation((*at, 0.0)))

    def height(d):
        for (r0, z0), (r1, z1) in zip(prof, prof[1:]):
            if d >= r1:
                return z0 + (z1 - z0) * (r0 - min(d, r0)) / (r0 - r1)
    return height


def rice_heap(p, at, r, z, hz, grains, seed):
    """A heap of raw rice with a scatter of grains lying on it."""
    height = heap(p, at, r, z, hz, 'RiceGrain')
    rnd = random.Random(seed)
    for k in range(grains):
        d = r * 0.8 * math.sqrt((k + 0.5) / grains)
        a = k * 2.4 + rnd.uniform(-0.3, 0.3)
        p.blob((at[0] + d * math.cos(a), at[1] + d * math.sin(a), height(d) + 0.003), 0.01, 'RiceGrain',
               squash=(1.8, 0.8, 0.55), segs=(5, 3), rot=rnd.uniform(0, math.pi))


def wicker(p, r, h, base, t=0.008, bulge=1.0, rings=1, wraps=8, wrap='WickerBind', n=16, at=(0.0, 0.0), floor=0.01):
    """A woven bamboo basket or tray: a lathe from the base radius out to the rim radius r (`bulge` < 1 rounds the
    wall like a bowl), rolled into a hoop at the rim that is bound with `wraps` wraps; returns the inside floor height."""
    x, y = at
    prof = [(0.0, 0.0), (base, 0.0)]
    for i in range(1, rings + 1):
        f = i / (rings + 1)
        prof.append((base + (r - base) * f ** bulge, (h - t * 2.2) * f))
    cx, cz = r + t * 0.2, h - t
    prof += [(cx + t * math.cos(a), cz + t * math.sin(a)) for a in (-1.3, -0.3, 0.6, 1.5, 2.5)]
    prof += [(r - t * 1.3, h - t * 2.2), (base * 0.9, floor), (0.0, floor)]
    p.lathe(prof, 'Wicker', n=n, close_ends=False, M=Matrix.Translation((x, y, 0.0)))
    for j in range(wraps):
        a = 2 * math.pi * (j + 0.5) / wraps
        c = Vector((x + cx * math.cos(a), y + cx * math.sin(a), cz))
        d = Vector((-math.sin(a), math.cos(a), 0.0)) * t * 0.6
        p.tube([c - d, c + d], t * 1.2, wrap, sides=6)
    return floor


def parcel(p, r, h, tie, seed, inside, n=14, corner=math.pi / 4, flare=0.5, lift=0.03, fill=0.8):
    """An open paper parcel: a squarish crumpled bag tied with twine at height `tie`, the paper above opening out
    into flaps of different sizes at its corners, low at the front; the opening is closed at the fill height by a
    floor of the contents (`inside`) crumpled like the paper, so nothing shows past them; returns that height."""
    paper = sacking(n, seed, dent=0.07, square=0.08, corner=corner, top=(tie, h), flare=flare, lift=lift, waves=4)
    fz = h * fill
    p.lathe([(0.0, 0.0), (r * 0.85, 0.0), (r, h * 0.06), (r * 1.03, tie * 0.6), (r * 0.94, tie),
             (r * 0.97, tie + (h - tie) * 0.45), (r, h), (r * 0.96, h - 0.003), (r * 0.88, fz)],
            'WrapPaper', n=n, deform=paper, close_ends=False)
    p.lathe([(r * 0.88, fz), (0.0, fz)], inside, n=n, deform=paper, close_ends=False)
    twine(p, r * 0.94, tie, paper, at=-0.5, n=n)
    return fz


def clay_pot(p, r, h, mouth, belly=0.45, fill=0.88, n=16, at=(0.0, 0.0)):
    """陶罐: a round-bellied clay pot of radius r with a rolled rim round its mouth; returns the fill height and the
    inside radius there, where the contents should start so that they close the pot."""
    t = 0.009
    fz = h * fill
    p.lathe([(0.0, 0.0), (r * 0.6, 0.0), (r * 0.68, h * 0.03), (r * 0.92, h * belly * 0.45), (r, h * belly),
             (r * 0.96, h * (belly + 1) / 2), (mouth + t * 0.4, h - t * 1.8), (mouth + t, h - t), (mouth + t * 0.8, h),
             (mouth, h + t * 0.15), (mouth - t * 0.6, h - t * 0.6), (mouth - t * 0.8, fz)],
            'ClayPot', n=n, close_ends=False, M=Matrix.Translation((*at, 0.0)))
    return fz, mouth - t * 0.8


def drape(x0, rho, beta, wave=0.0):
    """Deform for a flat blob made long in z, so that its rings run across it: lays it along x and beyond x0
    bends it down over an edge (a rim) through `beta` radians round a bend of radius rho, to hang on straight;
    `wave` ripples it across."""
    def deform(v):
        v = Vector((v.z, v.y, -v.x + wave * math.sin(v.y * 150 + v.z * 60)))
        s = v.x - x0
        if s <= 0:
            return v
        th = min(s / rho, beta)
        q = Vector((x0 + (rho + v.z) * math.sin(th), v.y, -rho + (rho + v.z) * math.cos(th)))
        if s > rho * beta:
            q += Vector((math.cos(beta), 0.0, -math.sin(beta))) * (s - rho * beta)
        return q
    return deform


def leaf(p, base, length, width, mat, yaw=0.0, pitch=0.0, roll=0.0, fold=0.3, curl=0.0, widest=0.4, teeth=0.0,
         rings=6, thick=0.003):
    """A pointed leaf blade from `base`, its midrib turned `yaw` about Z, tipped up by `pitch` and rolled by `roll`;
    V-folded along the midrib (fold < 0 arches it instead), the tip curled down by `curl`, widest at `widest` of its
    length, the margin alternating by `teeth` ring to ring for serrated or lobed leaves. A four-sided sphere keeps
    it cheap: margin, midrib, margin, underside."""
    R = Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(-pitch, 4, 'Y') @ Matrix.Rotation(roll, 4, 'X')
    a = math.log(0.5) / math.log(widest)

    def shape(v):   # sphere z runs base to tip, x across, y through the blade (y = -x keeps the faces outward)
        th = math.acos(max(-1.0, min(1.0, v.z)))
        t, s = th / math.pi, math.sin(th)
        y = 0.0 if s < 1e-6 else \
            -v.x / s * 0.5 * width * math.sin(math.pi * t ** a) * (1 + teeth * (-1) ** round(t * rings))
        return R @ Vector((t * length, y, v.y * thick + fold * abs(y) - curl * length * t * t))
    p.blob(base, 1.0, mat, segs=(4, rings), deform=shape)


def cup(p, x, y, r, h, fill, fill_z, n=12):
    """A small 青瓷 cup on a foot ring at (x, y), rim radius r and height h, filled with `fill` up to fill_z."""
    M = Matrix.Translation((x, y, 0.0))
    p.lathe([(r * 0.42, 0.0), (r * 0.55, 0.0), (r * 0.57, h * 0.16), (r * 0.86, h * 0.5), (r, h), (r - 0.0025, h + 0.002),
             (r - 0.005, h), (r * 0.8, fill_z)], 'Celadon', n=n, M=M, close_ends=False)
    p.lathe([(0.0, 0.003), (r * 0.42, 0.0)], 'Celadon', n=n, M=M, close_ends=False)   # underside
    p.lathe([(r * 0.8, fill_z), (0.0, fill_z + 0.001)], fill, n=n, M=M, close_ends=False)


def drop_to(p, n0, z):
    """Moves everything added to p since it had n0 vertices up or down so that its lowest point is at z; returns
    that move."""
    p.bm.verts.ensure_lookup_table()
    dz = z - min(v.co.z for v in p.bm.verts[n0:])
    for v in p.bm.verts[n0:]:
        v.co.z += dz
    return Matrix.Translation((0.0, 0.0, dz))


def petal_plate(p, r, h, lobes, depth, sx=1.0, n=None):
    """A flower-rimmed 青瓷盘 with fewer rings than plate(): `lobes` round scallops `depth` deep with sharp notches
    between them; sx stretches it oval. Floor at 0.008, 6n faces."""
    n = n or 4 * lobes

    def scallops(q):
        f = min(1.0, max(0.0, (math.hypot(q.x, q.y) - r * 0.7) / (r * 0.3)))
        k = 1 + depth * (abs(math.cos(lobes * math.atan2(q.y, q.x) / 2)) - 0.6) * f
        return Vector((q.x * k, q.y * k, q.z))
    p.lathe([(0, 0.0), (r * 0.58, 0.0), (r * 0.9, h * 0.8), (r, h), (r - 0.006, h + 0.0015), (r * 0.64, 0.008),
             (0, 0.008)], 'Celadon', n=n, close_ends=False, M=Matrix.Diagonal((sx, 1.0, 1.0, 1.0)), deform=scallops)


def petal_bowl(p, rim_r, h, foot_r, fill_z, fill, lobes, depth):
    """A flower-rimmed 青瓷碗 with fewer rings than bowl(): `lobes` round scallops with notches between them, closed
    by `fill` at fill_z. 8 × 4·lobes faces."""
    n = 4 * lobes

    def scallops(q):
        f = min(1.0, max(0.0, (math.hypot(q.x, q.y) - rim_r * 0.75) / (rim_r * 0.25)))
        k = 1 + depth * (abs(math.cos(lobes * math.atan2(q.y, q.x) / 2)) - 0.6) * f
        return Vector((q.x * k, q.y * k, q.z))
    p.lathe([(foot_r * 0.8, 0.0), (foot_r, 0.0), (foot_r * 1.06, 0.012), (rim_r * 0.8, h * 0.6), (rim_r, h),
             (rim_r - 0.006, h + 0.0015), (rim_r * 0.86, fill_z)], 'Celadon', n=n, close_ends=False, deform=scallops)
    p.lathe([(foot_r * 0.8, 0.0), (0, 0.004)], 'Celadon', n=n, close_ends=False)                     # underside
    p.lathe([(rim_r * 0.86, fill_z), (0, fill_z + 0.001)], fill, n=n, close_ends=False, deform=scallops)


def ring_of(n, radius, z, a0=0.0):
    """n spots evenly round a circle of `radius` at height z, starting at angle a0: (position, angle) pairs."""
    return [(Vector((radius * math.cos(a), radius * math.sin(a), z)), a)
            for a in (a0 + k * 2 * math.pi / n for k in range(n))]


def diced(p, c, size, mat, yaw, tilt=0.0, r=0.004):
    """A diced piece (chicken): a box with chamfered edges, turned yaw about Z and tipped by tilt. 26 faces."""
    p.box((0, 0, 0), size, mat, r=r, seg=1,
          M=Matrix.Translation(c) @ Matrix.Rotation(yaw, 4, 'Z') @ Matrix.Rotation(tilt, 4, 'X'))


def chili_piece(p, a, b, r=0.0065):
    """A length of red chilli from its cut end at a, tapering to the tip at b. 16 faces."""
    d = Vector(b) - Vector(a)
    p.lathe([(r * 0.9, 0.0), (r, d.length * 0.3), (r * 0.75, d.length * 0.7), (0.0, d.length)], 'ChiliRed', n=5,
            M=Matrix.Translation(a) @ axes_to(d, (0, 0, 1)))


def scallion_piece(p, a, b, mat='Scallion', r=0.0045):
    """A length of scallion cut from a to b. 8 faces."""
    d = Vector(b) - Vector(a)
    p.lathe([(r, 0.0), (r, d.length)], mat, n=6, M=Matrix.Translation(a) @ axes_to(d, (0, 0, 1)))
