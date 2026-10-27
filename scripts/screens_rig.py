"""Hook the generated screen videos onto the monitor screens and drive one area light per monitor
from screens/mon_light.json (per-frame mean linear colour)."""
import bpy, json, math, os
from mathutils import Vector
from lib_build import *

FRAMES = 5254
SCREEN_STRENGTH = 2.2   # emission of the panels themselves
LIGHT_K = 26.0          # area-light watts per unit of mean screen luminance
BOUNCE_K = 30.0         # bounce-fill watts per unit of summed luminance of all six screens


def movie_material(name, path, strength=SCREEN_STRENGTH):
    m, nt = new_mat(name)
    if nt is None:
        return m
    out = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'][0]
    tex = nt.nodes.new('ShaderNodeTexImage')
    im = bpy.data.images.load(path, check_existing=True)
    im.source = 'MOVIE'
    tex.image = im
    tex.extension = 'EXTEND'
    iu = tex.image_user
    iu.frame_duration = FRAMES
    iu.frame_start = 1
    iu.frame_offset = 0
    iu.use_auto_refresh = True
    iu.use_cyclic = False
    em = nt.nodes.new('ShaderNodeEmission')
    em.name = 'ScreenEmission'
    em.inputs['Strength'].default_value = strength
    # a touch of glossy glass on top so the panels pick up reflections when dim
    gl = nt.nodes.new('ShaderNodeBsdfGlossy')
    gl.inputs['Roughness'].default_value = 0.15
    gl.inputs['Color'].default_value = (0.04, 0.04, 0.04, 1)
    add = nt.nodes.new('ShaderNodeAddShader')
    nt.links.new(tex.outputs['Color'], em.inputs['Color'])
    nt.links.new(em.outputs[0], add.inputs[0])
    nt.links.new(gl.outputs[0], add.inputs[1])
    nt.links.new(add.outputs[0], out.inputs[0])
    return m


def key_series(idblock, path, index, values):
    """Write one keyframe per frame (1..N) with linear interpolation, fast."""
    ad = idblock.animation_data or idblock.animation_data_create()
    if ad.action is None:
        ad.action = bpy.data.actions.new(idblock.name + '_Action')
    idblock.keyframe_insert(path, index=index, frame=1)
    fc = None
    for f in all_fcurves(ad.action):
        if f.data_path == path and f.array_index == max(index, 0):
            fc = f
    fc.keyframe_points.clear()
    n = len(values)
    fc.keyframe_points.add(n)
    co = []
    for i, v in enumerate(values):
        co += (i + 1, v)
    fc.keyframe_points.foreach_set('co', co)
    fc.keyframe_points.foreach_set('interpolation', [1] * n)  # LINEAR
    fc.update()
    return fc


def all_fcurves(action):
    if hasattr(action, 'fcurves') and len(getattr(action, 'fcurves', [])):
        return list(action.fcurves)
    out = []  # layered actions (Blender 4.4+)
    for layer in getattr(action, 'layers', []):
        for strip in layer.strips:
            for cb in strip.channelbags:
                out += list(cb.fcurves)
    return out


def hook(screens, light_col, clip=CLIP, shadow_res=0.01):
    data = json.load(open(os.path.join(clip, 'screens', 'mon_light.json')))
    lights = {}
    for idx, scr in screens.items():
        path = os.path.join(clip, 'screens', f'mon{idx}.mp4')
        scr.data.materials[0] = movie_material(f'Screen{idx}_Movie', path)
        mw = scr.matrix_world
        l = light(f'MonLight{idx}', 'AREA', mw @ Vector((0, -0.03, 0)), 10.0, (1, 1, 1), light_col, size=(0.597, 0.336))
        l.rotation_euler = mw.to_euler()
        l.rotation_euler.rotate_axis('X', -math.pi / 2)      # area lights emit along -Z; screens face local -Y
        l.data.shadow_maximum_resolution = shadow_res
        l.data.spread = math.radians(150)
        seq = data[f'mon{idx}']
        lum = [0.2126 * r + 0.7152 * g + 0.0722 * b for r, g, b in seq]
        key_series(l.data, 'energy', -1, [LIGHT_K * max(v, 0.002) for v in lum])
        for ch in range(3):
            key_series(l.data, 'color', ch, [min(1.0, c[ch] / max(1e-4, max(c))) if max(c) > 1e-4 else 1.0 for c in seq])
        lights[idx] = l
    return lights


def bounce(light_col, loc, rot, size=(3.0, 3.0), k=BOUNCE_K, clip=CLIP, name='ScreenBounce'):
    """Soft fill standing in for screen light bounced off ceiling/walls: one big area light whose energy
    and colour follow the summed luminance of all six monitors."""
    data = json.load(open(os.path.join(clip, 'screens', 'mon_light.json')))
    seqs = [data[f'mon{i}'] for i in range(1, 7)]
    tot = [[sum(s[f][ch] for s in seqs) for ch in range(3)] for f in range(len(seqs[0]))]
    l = light(name, 'AREA', loc, 1.0, (1, 1, 1), light_col, size=size, rot=rot)
    l.data.shadow_maximum_resolution = 0.02
    l.data.specular_factor = 0.3
    key_series(l.data, 'energy', -1, [k * max(0.002, 0.2126 * r + 0.7152 * g + 0.0722 * b) for r, g, b in tot])
    for ch in range(3):
        # bounce off a grey concrete ceiling: half-way between the screen tint and white
        key_series(l.data, 'color', ch, [0.5 + 0.5 * (c[ch] / max(c)) if max(c) > 1e-4 else 1.0 for c in tot])
    return l
