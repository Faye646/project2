"""Watercolor (水彩) materials for EEVEE: painted texture, soft multi-step light, cool shadows,
pigment in the crevices and dappled light, all ending in an Emission so the look is fully authored.

Used by build_cook_view.py --wc. `kind` picks the painted texture:
    wood, plaster, stone, cloth, iron, food, glass (flat).
"""
import bpy

WOOD = {'Timber', 'Counter', 'TrayWood', 'Floor', 'Straw', 'LightWood', 'Burlap', 'Twine'}
PLASTER = {'Plaster'}
STONE = {'Brick', 'Mortar', 'Jar', 'Porcelain', 'Celadon', 'Clay', 'BlueGlaze'}
CLOTH = {'Cloth', 'ClothPattern'}
IRON = {'Iron', 'Ember'}
DAPPLED = {'Plaster', 'Floor'}

COOL = (0.34, 0.36, 0.55)      # the blue-violet mixed into shadows
WARM = (1.0, 0.86, 0.62)       # sunlight tint
POOL = (0.36, 0.2, 0.11)       # pigment pooling in crevices


def kind_of(name):
    if name in WOOD:
        return 'wood'
    if name in PLASTER:
        return 'plaster'
    if name in STONE:
        return 'stone'
    if name in CLOTH:
        return 'cloth'
    if name in IRON:
        return 'iron'
    return 'food'


def _n(nt, t, **kw):
    n = nt.nodes.new(t)
    for k, v in kw.items():
        setattr(n, k, v)
    return n


def _mix(nt, a, b, fac, blend='MIX'):
    m = _n(nt, 'ShaderNodeMix', data_type='RGBA', blend_type=blend)
    nt.links.new(fac if not isinstance(fac, (int, float)) else _val(nt, fac), m.inputs[0])
    for sock, src in ((6, a), (7, b)):
        if isinstance(src, tuple):
            m.inputs[sock].default_value = (*src, 1) if len(src) == 3 else src
        else:
            nt.links.new(src, m.inputs[sock])
    return m.outputs[2]


def _val(nt, v):
    n = _n(nt, 'ShaderNodeValue')
    n.outputs[0].default_value = v
    return n.outputs[0]


def _math(nt, op, a, b=None, clamp=True):
    m = _n(nt, 'ShaderNodeMath', operation=op, use_clamp=clamp)
    for i, s in enumerate((a, b)):
        if s is None:
            continue
        if isinstance(s, (int, float)):
            m.inputs[i].default_value = s
        else:
            nt.links.new(s, m.inputs[i])
    return m.outputs[0]


def _ramp(nt, src, stops):
    r = _n(nt, 'ShaderNodeValToRGB')
    r.color_ramp.interpolation = 'EASE'
    els = r.color_ramp.elements
    while len(els) < len(stops):
        els.new(0.5)
    for e, (pos, col) in zip(els, stops):
        e.position = pos
        e.color = (*col, 1) if len(col) == 3 else col
    nt.links.new(src, r.inputs[0])
    return r.outputs[0]


def painted(name, lit, shade, srgb, emissive=False, image=None, tex=None, tex_scale=1.0, glow=False, sat=1.28, val=1.08):
    """lit/shade are hex colours; srgb() converts them to linear."""
    mat = bpy.data.materials.get('W_' + name) or bpy.data.materials.new('W_' + name)
    nt = mat.node_tree
    nt.nodes.clear()
    out = _n(nt, 'ShaderNodeOutputMaterial')
    emit = _n(nt, 'ShaderNodeEmission')
    nt.links.new(emit.outputs[0], out.inputs['Surface'])
    L, S = srgb(lit), srgb(shade)
    if image is not None:
        tex = _n(nt, 'ShaderNodeTexImage', image=image)
        nt.links.new(_n(nt, 'ShaderNodeTexCoord').outputs['UV'], tex.inputs[0])
        if glow:   # e.g. the painted fire mouth: slightly brighter than the lit scene
            bright = _n(nt, 'ShaderNodeMix', data_type='RGBA', blend_type='MULTIPLY')
            bright.inputs[0].default_value = 1.0
            nt.links.new(tex.outputs[0], bright.inputs[6])
            bright.inputs[7].default_value = (1.15, 1.08, 1.0, 1)
            nt.links.new(bright.outputs[2], emit.inputs['Color'])
        else:
            nt.links.new(tex.outputs[0], emit.inputs['Color'])
        # cut out along the picture's alpha (the round sieve, the towel)
        mix = _n(nt, 'ShaderNodeMixShader')
        nt.links.new(tex.outputs['Alpha'], mix.inputs[0])
        nt.links.new(_n(nt, 'ShaderNodeBsdfTransparent').outputs[0], mix.inputs[1])
        nt.links.new(emit.outputs[0], mix.inputs[2])
        nt.links.new(mix.outputs[0], out.inputs['Surface'])
        return mat
    if emissive:
        emit.inputs['Color'].default_value = (*L, 1)
        return mat

    kind = kind_of(name)
    tc = _n(nt, 'ShaderNodeTexCoord')
    obj = tc.outputs['Object']
    gen = _n(nt, 'ShaderNodeNewGeometry').outputs['Position']

    # --- painted base colour: two washes of the material's colour broken up by its texture
    mid = tuple(l * 0.55 + s * 0.45 for l, s in zip(L, S))
    if kind == 'wood':
        wave = _n(nt, 'ShaderNodeTexWave', wave_type='BANDS', bands_direction='X')
        wave.inputs['Scale'].default_value = 9.0
        wave.inputs['Distortion'].default_value = 4.0
        wave.inputs['Detail'].default_value = 3.0
        nt.links.new(obj, wave.inputs['Vector'])
        streak = _ramp(nt, wave.outputs['Fac'], [(0.0, L), (0.6, tuple(l * 0.8 + s * 0.2 for l, s in zip(L, S))), (1.0, mid)])
        grain = _n(nt, 'ShaderNodeTexNoise')
        grain.inputs['Scale'].default_value = 18
        nt.links.new(obj, grain.inputs['Vector'])
        base = _mix(nt, streak, L, _math(nt, 'MULTIPLY', grain.outputs['Fac'], 0.5))
    elif kind == 'plaster':
        n1 = _n(nt, 'ShaderNodeTexNoise')
        n1.inputs['Scale'].default_value = 1.6
        n1.inputs['Detail'].default_value = 6
        n1.inputs['Roughness'].default_value = 0.65
        nt.links.new(gen, n1.inputs['Vector'])
        stain = (min(1, L[0] * 0.95), L[1] * 0.82, L[2] * 0.62)   # warm water stains
        base = _ramp(nt, n1.outputs['Fac'], [(0.35, L), (0.62, stain), (0.8, mid)])
        # grime pooling toward the floor
        zfade = _n(nt, 'ShaderNodeSeparateXYZ')
        nt.links.new(gen, zfade.inputs[0])
        low = _math(nt, 'SUBTRACT', 1.0, _math(nt, 'MULTIPLY', zfade.outputs['Z'], 1.6))
        base = _mix(nt, base, mid, _math(nt, 'MULTIPLY', low, 0.45))
    elif kind == 'stone':
        n1 = _n(nt, 'ShaderNodeTexNoise')
        n1.inputs['Scale'].default_value = 9
        n1.inputs['Detail'].default_value = 5
        nt.links.new(obj, n1.inputs['Vector'])
        base = _ramp(nt, n1.outputs['Fac'], [(0.3, L), (0.55, mid), (0.75, L)])
    elif kind == 'iron':
        n1 = _n(nt, 'ShaderNodeTexNoise')
        n1.inputs['Scale'].default_value = 7
        nt.links.new(obj, n1.inputs['Vector'])
        base = _ramp(nt, n1.outputs['Fac'], [(0.35, S), (0.65, L)])
    else:
        n1 = _n(nt, 'ShaderNodeTexNoise')
        n1.inputs['Scale'].default_value = 25 if kind == 'food' else 12
        nt.links.new(obj, n1.inputs['Vector'])
        base = _ramp(nt, n1.outputs['Fac'], [(0.3, L), (0.7, tuple(l * 0.8 + s * 0.2 for l, s in zip(L, S)))])

    # --- a patch of the painted art projected onto the model (box projection, mirrored tiling)
    if tex is not None:
        mp = _n(nt, 'ShaderNodeMapping')
        mp.inputs['Scale'].default_value = (tex_scale, tex_scale, tex_scale)
        nt.links.new(obj, mp.inputs['Vector'])
        it = _n(nt, 'ShaderNodeTexImage', image=tex, projection='BOX', projection_blend=0.25, extension='MIRROR')
        nt.links.new(mp.outputs[0], it.inputs['Vector'])
        hs = _n(nt, 'ShaderNodeHueSaturation')
        hs.inputs['Saturation'].default_value = sat
        hs.inputs['Value'].default_value = val
        nt.links.new(it.outputs[0], hs.inputs['Color'])
        base = hs.outputs[0]

    # --- light: real diffuse lighting (with shadows) turned into soft painted steps
    diff = _n(nt, 'ShaderNodeBsdfDiffuse')
    diff.inputs['Color'].default_value = (1, 1, 1, 1)
    s2r = _n(nt, 'ShaderNodeShaderToRGB')
    nt.links.new(diff.outputs[0], s2r.inputs[0])
    bw = _n(nt, 'ShaderNodeRGBToBW')
    nt.links.new(s2r.outputs[0], bw.inputs[0])
    light = _ramp(nt, bw.outputs[0], [(0.25, (0.0, 0.0, 0.0)), (0.42, (0.45, 0.45, 0.45)), (0.62, (0.82, 0.82, 0.82)), (0.9, (1, 1, 1))])
    lv = _n(nt, 'ShaderNodeRGBToBW')
    nt.links.new(light, lv.inputs[0])
    shadow_col = _mix(nt, _mix(nt, base, (0, 0, 0), 0.46), COOL, 0.2)      # darker, cooler
    col = _mix(nt, shadow_col, base, lv.outputs[0])
    hi = _math(nt, 'MULTIPLY', _math(nt, 'SUBTRACT', lv.outputs[0], 0.85), 5.0)
    col = _mix(nt, col, _mix(nt, base, WARM, 0.35), _math(nt, 'MULTIPLY', hi, 0.6))

    # --- pigment pools in crevices and corners
    ao = _n(nt, 'ShaderNodeAmbientOcclusion', samples=16)
    ao.inputs['Distance'].default_value = 0.25
    occl = _math(nt, 'SUBTRACT', 1.0, ao.outputs['AO'])
    col = _mix(nt, col, POOL, _math(nt, 'MULTIPLY', occl, 0.55))

    # --- dappled sunlight (leaf shadows) on the walls, floor and counter
    if name in DAPPLED:
        d = _n(nt, 'ShaderNodeTexNoise')
        d.inputs['Scale'].default_value = 1.3
        d.inputs['Detail'].default_value = 4
        d.inputs['Roughness'].default_value = 0.7
        nt.links.new(gen, d.inputs['Vector'])
        spots = _n(nt, 'ShaderNodeValToRGB')
        spots.color_ramp.interpolation = 'EASE'
        spots.color_ramp.elements[0].position = 0.52
        spots.color_ramp.elements[1].position = 0.6
        nt.links.new(d.outputs['Fac'], spots.inputs[0])
        sp = _n(nt, 'ShaderNodeRGBToBW')
        nt.links.new(spots.outputs[0], sp.inputs[0])
        amount = _math(nt, 'MULTIPLY', _math(nt, 'MULTIPLY', sp.outputs[0], lv.outputs[0]), 0.35)
        col = _mix(nt, col, _mix(nt, base, WARM, 0.45), amount)
        # the leaf-shadowed parts of a lit wall sit a little darker, as in the painting
        col = _mix(nt, col, _mix(nt, base, COOL, 0.12), _math(nt, 'MULTIPLY', _math(nt, 'SUBTRACT', 1.0, sp.outputs[0]), 0.18))

    nt.links.new(col, emit.inputs['Color'])
    return mat
