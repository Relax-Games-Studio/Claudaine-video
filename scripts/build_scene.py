"""Assemble the clip: env + workstation + screens + human (+ monsters) + IV + phone + camera + animation.
Run: Blender -b blend/env.blend --python scripts/build_scene.py   -> blend/claudaine.blend"""
import bpy
import numpy as np, sys, os, math, json, random
from mathutils import Vector, Matrix, Euler
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from lib_build import *
import desk, screens_rig, camera_rig, grip_rig, catheter, drop, hair, shirt, tremor_hands
from desk import HUMAN_OFFSET, DESK_TOP, IV_BASE

FPS = 24
FRAMES = 5254
T = lambda t: 1 + int(round(t * FPS))        # seconds -> frame
scene = bpy.context.scene
scene.frame_start, scene.frame_end = 1, FRAMES
R = random.Random(7)


def keys(owner, attr, pts, index=-1, interp='LINEAR'):
    """pts = [(seconds, value)]: sparse keyframes on owner.attr (an ID, or a struct inside one such as
    a node socket) with the given interpolation."""
    for t, v in pts:
        if attr.startswith('['):
            owner[attr[2:-2]] = v
        elif index >= 0:
            getattr(owner, attr)[index] = v
        else:
            setattr(owner, attr, v)
        owner.keyframe_insert(attr, index=index, frame=T(t))
    idb = owner.id_data
    path = attr if idb == owner else owner.path_from_id(attr)
    for fc in screens_rig.all_fcurves(idb.animation_data.action):
        if fc.data_path == path and (index < 0 or fc.array_index == index):
            for kp in fc.keyframe_points:
                kp.interpolation = interp


def hide_keys(ob, spans_hidden, default=False):
    """spans_hidden = [(t0, t1)] in which the object is hidden from render (constant keys)."""
    ob.hide_render = default
    ob.keyframe_insert('hide_render', frame=1)
    for t0, t1 in spans_hidden:
        ob.hide_render = True
        ob.keyframe_insert('hide_render', frame=max(1, T(t0)))
        ob.hide_render = default
        ob.keyframe_insert('hide_render', frame=T(t1))
    ob.hide_render = default


# ---------------------------------------------------------------- workstation + screens
C_DESK = coll('DESK')
C_DL = coll('DESK_LIGHTS')
root = bpy.data.objects.new('DESK_ROOT', None)
C_DESK.objects.link(root)
root.location = (-3.0, 2.4, -2.1)
root.rotation_euler = (0, 0, math.pi)
res = desk.build_all(root, C_DESK, C_DL)
bpy.context.view_layer.update()
M, B = res['M'], res['B']
mons = screens_rig.hook(res['screens'], C_DL)
W = lambda p: root.matrix_world @ Vector(p)
bounce = screens_rig.bounce(C_DL, W((0, -0.4, 2.3)), (0, 0, 0))
# light spilling from the basement up the stairwell (seen from the hall when the door opens)
spill = screens_rig.bounce(C_DL, Vector((-3.7, 4.3, -1.75)), (0, 0, 0), size=(1.2, 1.2), k=40.0, name='StairSpill')
look_at(spill, Vector((-0.9, 4.95, 0.9)), 'Y')

# dusty basement air: the screens get a halo, the dark reads as space
hz = box('BasementHaze', (11.8, 8.8, 2.38), (0, 4.5, -2.1), C_DESK, None, bottom=True)
hm, hnt = new_mat('BasementHazeVol')
for n in list(hnt.nodes):
    if n.type == 'BSDF_PRINCIPLED':
        hnt.nodes.remove(n)
v = hnt.nodes.new('ShaderNodeVolumePrincipled')
v.inputs['Density'].default_value = 0.03
v.inputs['Anisotropy'].default_value = 0.5
hnt.links.new(v.outputs[0], [n for n in hnt.nodes if n.type == 'OUTPUT_MATERIAL'][0].inputs['Volume'])
hz.data.materials.clear()
hz.data.materials.append(hm)

# ---------------------------------------------------------------- human
HUMAN_BLEND = os.path.join(CLIP, 'blend', 'human.blend')
with bpy.data.libraries.load(HUMAN_BLEND, link=False) as (src, dst):
    dst.collections = ['HUMAN']
    dst.actions = [a for a in src.actions if a in ('Typing', 'SeatedIdle', 'Tremor', 'SitToType')]
C_HUMAN = dst.collections[0]
scene.collection.children.link(C_HUMAN)
rig = bpy.data.objects['HumanRig']
rig.parent = root
rig.location = HUMAN_OFFSET
ad = rig.animation_data or rig.animation_data_create()
ad.action = None
acts = bpy.data.actions
trA = ad.nla_tracks.new()
trA.name = 'Typing'
st = trA.strips.new('Typing', 1, acts['Typing'])
st.action_frame_start, st.action_frame_end = 1, 382
st.repeat = (FRAMES + 10) / 381.0
trB = ad.nla_tracks.new()
trB.name = 'Override'


def over(name, act, t0, t1, a0, a1, blend=6):
    s = trB.strips.new(name, T(t0), acts[act])
    s.action_frame_start, s.action_frame_end = a0, a1
    span = T(t1) - T(t0)
    if act == 'Tremor':
        s.repeat = span / (a1 - a0)
    else:
        s.scale = span / (a1 - a0)
    s.blend_in = s.blend_out = blend
    s.extrapolation = 'NOTHING'
    return s


over('Tremor', 'Tremor', 139.1, 149.6, 1, 382)
over('FreezeDark', 'Typing', 157.3, 168.0, 191, 192, 4)
over('FreezeEnd', 'Typing', 188.6, FRAMES / FPS, 191, 192, 24)
grip_rig.setup(rig, bpy.data.objects['Mouse'], C_DESK, FRAMES)     # right hand lands on the mouse
body = bpy.data.objects['Body']
for kb in body.data.shape_keys.key_blocks:
    if kb.name in ('Sunken', 'MouthOpen'):
        kb.value = 1.0
shirt.setup(rig, body, bpy.data.objects['Clothes'])                 # skin stays under the shirt
print('tremor hands lowered by', tremor_hands.lower(rig, body, trB.strips['Tremor'], bpy.data.objects['Mouse']))
hair.build(rig, body, C_HUMAN)                                      # real strands instead of the cap
skin = bpy.data.materials['HumanSkin']
keys(skin, '["dryness"]', [(0.0, 0.55), (60.0, 0.62), (139.0, 0.85), (168.0, 1.0)])

# ---------------------------------------------------------------- IV line, bag, drips
iv, bag, bag_fill, iv_drop = res['iv']
chamber_bottom = IV_BASE + Vector((0.11, 0, 1.84 - 0.35))
# the cannula is built on the skin at a frame of the elbow close-up and rides on the arm from there
CATH_F = T(178.0)
cath = catheter.setup(rig, body, root, C_DESK, CATH_F, Vector((-0.48, 0.32, 1.02)))
tube, liq = desk.build_iv_tube(B, M, chamber_bottom, cath['tail'])
for ob in (tube, liq):
    catheter.bind_tube(ob, cath, rig)
camera_rig.ELB = camera_rig.L(*cath['hub_root'])
flow = liq.data.materials[0]
fill = flow.node_tree.nodes['FlowFill']
keys(fill.inputs[1], 'default_value', [(0.0, -0.01), (168.6, -0.01), (176.2, 1.01)])
keys(cath['hub_liquid'].node_tree.nodes['Principled BSDF'].inputs['Emission Strength'], 'default_value',
     [(0.0, 0.0), (176.0, 0.0), (176.6, 2.5)])
keys(cath['vein'].node_tree.nodes['VeinFront'].inputs[0], 'default_value', [(0.0, 0.0), (176.3, 0.0), (180.4, 1.15)])
bagmat = bag_fill.data.materials[0].copy()
bagmat.name = 'IVBagLiquid'
bag_fill.data.materials[0] = bagmat
mth = [n for n in bagmat.node_tree.nodes if n.type == 'MATH' and n.operation == 'MULTIPLY_ADD'][0]
keys(mth.inputs[2], 'default_value', [(0.0, 0.2), (168.0, 0.2), (170.5, 0.7), (176.0, 0.4)])
keys(mth.inputs[1], 'default_value', [(0.0, 0.28), (168.0, 0.28), (170.5, 0.9), (176.0, 0.5)])
# bag level (box of height 0.17 centred at z=-0.165 -> scale about its bottom at -0.25)
lvl = [(0.0, 0.45), (159.3, 0.45), (167.6, 0.06), (168.0, 0.06), (171.0, 1.0)]
for t, s_ in lvl:
    bag_fill.scale.z = s_
    bag_fill.location.z = -0.25 + 0.085 * s_
    bag_fill.keyframe_insert('scale', index=2, frame=T(t))
    bag_fill.keyframe_insert('location', index=2, frame=T(t))
# drip chamber: drops form at the spike and fall into the chamber
z_spike, z_pool = -0.302, -0.330
zs, sc = [], []
for f in range(1, FRAMES + 1):
    t = (f - 1) / FPS
    if t < 159.3:
        P, ph = 1.3, (t % 1.3) / 1.3
    elif t < 168.0:
        P = None
        ph = (t - 163.0) / 2.6 if 163.0 <= t < 165.6 else -1    # the last drop
    else:
        P, ph = 0.35, (t % 0.35) / 0.35
    if ph < 0:
        zs.append(z_spike); sc.append(0.0); continue
    if ph < 0.8:                      # forming
        zs.append(z_spike); sc.append(0.4 + 0.6 * ph / 0.8)
    else:                             # falling
        u = (ph - 0.8) / 0.2
        zs.append(z_spike + (z_pool - z_spike) * u * u); sc.append(1.0 if u < 0.95 else 0.0)
screens_rig.key_series(iv_drop, 'location', 2, zs)
for i in range(3):
    screens_rig.key_series(iv_drop, 'scale', i, sc)

# ---------------------------------------------------------------- phone on the desk
PH_LOC = Vector((0.62, 0.42, DESK_TOP))
ph = B.empty('Phone', tuple(PH_LOC), (0, 0, math.radians(-12)))
B.box('Phone_Body', (0.074, 0.158, 0.008), (0, 0, 0.004), M['mon'], bevel=0.006, parent=ph)
import bmesh
bm = bmesh.new()
bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
bmesh.ops.scale(bm, vec=(0.068, 0.150, 1), verts=bm.verts)
pme = bpy.data.meshes.new('Phone_Screen')
bm.to_mesh(pme)
bm.free()
puv = pme.uv_layers.new(name='UVMap')
for li, lp in enumerate(pme.loops):
    co = pme.vertices[lp.vertex_index].co
    puv.data[li].uv = (co.x / 0.068 + 0.5, co.y / 0.150 + 0.5)
pme.materials.append(screens_rig.movie_material('PhoneScreen_Movie', os.path.join(CLIP, 'screens', 'phone.mp4'), 1.6))
pscr = bpy.data.objects.new('Phone_Screen', pme)
C_DESK.objects.link(pscr)
pscr.location = (0, 0, 0.0082)
B.adopt(pscr, ph)
# vibration: buzz bursts while "Mom calling..." (96.2 - 106)
pdata = json.load(open(os.path.join(CLIP, 'screens', 'mon_light.json')))['phone']
vx, vy, vr = [], [], []
for f in range(1, FRAMES + 1):
    t = (f - 1) / FPS
    on = 96.2 <= t < 106.2 and ((t - 96.2) % 2.0) < 0.9
    a = 0.0016 if on else 0.0
    vx.append(PH_LOC.x + a * math.sin(t * 2 * math.pi * 31))
    vy.append(PH_LOC.y + a * 0.7 * math.sin(t * 2 * math.pi * 23 + 1))
    vr.append(math.radians(-12) + (a * 9) * math.sin(t * 2 * math.pi * 27))
screens_rig.key_series(ph, 'location', 0, vx)
screens_rig.key_series(ph, 'location', 1, vy)
screens_rig.key_series(ph, 'rotation_euler', 2, vr)
pl = light('PhoneLight', 'AREA', (0, 0, 0.03), 0.0, (0.75, 0.85, 1.0), C_DL, rot=(math.pi, 0, 0), size=(0.07, 0.15))
B.adopt(pl, ph)          # area lights emit along -Z: flipped to shine up off the screen
pl.data.shadow_maximum_resolution = 0.02
screens_rig.key_series(pl.data, 'energy', -1, [6.0 * (0.2126 * r + 0.7152 * g + 0.0722 * b) for r, g, b in pdata])

# ---------------------------------------------------------------- the drop that falls from the desk syringe (slow-mo)
drop.build(B, M, C_DESK, C_DL)

# ---------------------------------------------------------------- Claude sparks in the glasses (198 s)
bpy.context.view_layer.update()
scene.frame_set(T(198.0))
for side, lens_name in (('L', 'Lens_L'), ('R', 'Lens_R')):
    lens = bpy.data.objects[lens_name]
    fwd = root.matrix_world.to_3x3() @ Vector((0, 1, 0))          # the way the face looks (world -Y)
    vs = [lens.matrix_world @ v.co for v in lens.data.vertices]
    cen = sum(vs, Vector()) / len(vs)
    c = cen + fwd * (max(v.dot(fwd) for v in vs) - cen.dot(fwd) + 0.0008)   # just in front of the glass
    sbm = desk.claude_star(f'GlassSpark_{side}', 0.0095, 0.0019, thick=0.0006)
    sp = obj_from_bm(f'GlassSpark_{side}', sbm, C_HUMAN, [emission_mat(f'GlassSparkGlow_{side}', ORANGE, 0.0)], uv=False)
    sp.matrix_world = Matrix.Translation(c)                         # the star faces -Y: towards the camera
    mw = sp.matrix_world.copy()
    sp.parent = lens
    sp.matrix_parent_inverse = lens.matrix_world.inverted()
    sp.matrix_world = mw
    em = [n for n in sp.data.materials[0].node_tree.nodes if n.type == 'EMISSION'][0]
    keys(em.inputs['Strength'], 'default_value', [(0.0, 0.0), (198.2, 0.0), (199.4, 1.6), (206.3, 1.6), (207.0, 3.0), (214.24, 3.0)])
    # spin about its own facing axis
    sp.rotation_mode = 'XYZ'
    base = sp.rotation_euler.copy()
    spin = [(198.0, 0.0), (214.24, math.radians(-200 if side == 'L' else 200))]
    for t, a in spin:
        sp.rotation_euler = base
        sp.rotation_euler.rotate_axis('Y', a)
        sp.keyframe_insert('rotation_euler', frame=T(t))
    sp.rotation_euler = base
scene.frame_set(1)

# the lally columns under the steel beam stood centred on the floor (half sunk, top at 1.08 m): stand them on it
jo = bpy.data.objects['Basement_Joists']
for cx in (-1.6, 2.4):
    col_v = [v for v in jo.data.vertices if math.hypot(v.co.x - cx, v.co.y - 3.2) < 0.05 and v.co.z < 0.0]
    if col_v and min(v.co.z for v in col_v) < -2.11:
        for v in col_v:
            v.co.z += 1.08
jo.data.update()

# ---------------------------------------------------------------- the creatures from his game
# They stream out of the screens as voxels (MonsterGlitch modifier, see blend/monster_report.json), loom by the
# desk through chorus 2, shatter in the bridge, vanish for the reset/blackout and all four come back for the last chorus.
with bpy.data.libraries.load(os.path.join(CLIP, 'blend', 'monsters.blend'), link=False) as (src, dst):
    dst.collections = ['MON_warrok', 'MON_maw', 'MON_mutant', 'MON_parasite']
    dst.actions = [a for a in src.actions if a.split('_')[0] in ('warrok', 'maw', 'mutant', 'parasite')]
C_MON = coll('MONSTERS')
for c in dst.collections:
    C_MON.children.link(c)
scr_c = {i: s.matrix_world.translation.copy() for i, s in res['screens'].items()}
SOCK = 'modifiers["MonsterGlitch"].properties.inputs.%s.value'


def face_to(p, target=(0.0, -0.1)):
    """root-local Z rotation so the rig's +Y faces from p towards target (the chair)."""
    d = Vector((target[0] - p[0], target[1] - p[1]))
    return math.atan2(-d.x, d.y)


def env(spans, f_t):
    """per-frame value from [(t0, t1, fn(t))] spans, 0 outside."""
    for t0, t1, fn in spans:
        if t0 <= f_t < t1:
            return fn(f_t)
    return 0.0


def ramp(a, b, v0=0.0, v1=1.0):
    return lambda t: v0 + (v1 - v0) * min(1.0, max(0.0, (t - a) / (b - a)))


def beat_glitch(base, peak):
    return lambda t: base + (peak - base) * math.exp(-(((t - 0.496) % 0.6) / 0.09))


MONS = {
    # name: (root-local spot, source screen, seed, reveal spans, glitch spans, roar start times)
    'warrok': ((-2.8, 0.2), 2, 3,
               [(110.3, 113.3, ramp(110.3, 113.3)), (113.3, 139.1, lambda t: 1.0), (139.1, 140.4, ramp(139.1, 140.4, 1, 0)),
                (168.0, 169.0, ramp(168.0, 169.0)), (169.0, 186.8, lambda t: 1.0), (186.8, 188.1, ramp(186.8, 188.1, 1, 0))],
               [(132.5, 139.1, beat_glitch(0.25, 0.7)), (139.1, 140.4, lambda t: 0.5), (168.0, 169.5, ramp(168.0, 169.5, 0.6, 0.1)),
                (169.5, 186.8, beat_glitch(0.05, 0.3)), (186.8, 188.1, lambda t: 0.7)],
               [115.0, 125.0, 175.5]),
    'maw': ((2.0, -0.2), 5, 7,
            [(119.9, 122.9, ramp(119.9, 122.9)), (122.9, 139.1, lambda t: 1.0), (139.1, 140.4, ramp(139.1, 140.4, 1, 0)),
             (168.0, 169.0, ramp(168.0, 169.0)), (169.0, 186.8, lambda t: 1.0), (186.8, 188.1, ramp(186.8, 188.1, 1, 0))],
            [(132.5, 139.1, beat_glitch(0.25, 0.7)), (139.1, 140.4, lambda t: 0.5), (168.0, 169.5, ramp(168.0, 169.5, 0.6, 0.1)),
             (169.5, 186.8, beat_glitch(0.05, 0.3)), (186.8, 188.1, lambda t: 0.7)],
            [124.5, 180.4]),
    'mutant': ((-3.8, -1.5), 1, 11,
               [(168.0, 170.6, ramp(168.0, 170.6)), (170.6, 186.8, lambda t: 1.0), (186.8, 188.1, ramp(186.8, 188.1, 1, 0))],
               [(168.0, 170.6, lambda t: 0.3), (170.6, 186.8, beat_glitch(0.05, 0.35)), (186.8, 188.1, lambda t: 0.7)],
               [172.0, 182.8]),
    'parasite': ((-2.2, -0.7), 3, 13,
                 [(168.4, 171.0, ramp(168.4, 171.0)), (171.0, 186.8, lambda t: 1.0), (186.8, 188.1, ramp(186.8, 188.1, 1, 0))],
                 [(168.4, 171.0, lambda t: 0.3), (171.0, 186.8, beat_glitch(0.05, 0.35)), (186.8, 188.1, lambda t: 0.7)],
                 [176.0, 181.6]),
}
SPOT2 = {'warrok': (-3.0, 1.2)}
# spots, turn and size from a sweep of every visible frame (roars included) against the desk, monitors, chair, IV stand,
# stair, walls, girder and the underside of the joists (2.37 m), and of the four against each other in the last chorus
YAW = {'maw': math.radians(20)}
YAW2 = {'warrok': math.radians(-20)}
SIZE = {'warrok': 0.8, 'maw': 0.761, 'mutant': 0.94, 'parasite': 0.94}
for name, (spot, src_i, seed, rev, gli, roars) in MONS.items():
    mrig = bpy.data.objects[f'{name}_Rig']
    mbody = bpy.data.objects[f'{name}_Body']
    # placement lives on a parent empty: the rig's own animation data belongs to the NLA below
    mspot = B.empty(f'{name}_Spot', (spot[0], spot[1], 0.0), (0, 0, face_to(spot) + YAW.get(name, 0.0)))
    if name in SPOT2:            # steps back for the last chorus: the camera follows the IV line through its first spot
        keys(mspot, 'location', [(0.0, spot[0]), (150.0, SPOT2[name][0])], index=0, interp='CONSTANT')
        keys(mspot, 'location', [(0.0, spot[1]), (150.0, SPOT2[name][1])], index=1, interp='CONSTANT')
        keys(mspot, 'rotation_euler', [(0.0, face_to(spot) + YAW.get(name, 0.0)), (150.0, face_to(SPOT2[name]) + YAW2.get(name, 0.0))],
             index=2, interp='CONSTANT')
    mrig.parent = mspot
    mrig.location = (0, 0, 0)
    mrig.rotation_euler = (0, 0, 0)
    mrig.scale = (SIZE[name],) * 3                     # roars stay under the joists
    mad = mrig.animation_data or mrig.animation_data_create()
    mad.action = None
    idle, roar = acts[f'{name}_Idle'], acts[f'{name}_Roar']
    tr_i = mad.nla_tracks.new()
    tr_i.name = 'Idle'
    si = tr_i.strips.new('Idle', 1, idle)
    si.repeat = (FRAMES + 10) / (idle.frame_range[1] - idle.frame_range[0])
    tr_r = mad.nla_tracks.new()
    tr_r.name = 'Roar'
    for k, t in enumerate(roars):
        sr = tr_r.strips.new(f'Roar{k}', T(t), roar)
        sr.blend_in = sr.blend_out = 6
        sr.extrapolation = 'NOTHING'
    mg = mbody.modifiers['MonsterGlitch'].properties.inputs
    mg.Socket_2.value = scr_c[src_i]
    mg.Socket_5.value = seed
    rv = [env(rev, (f - 1) / FPS) for f in range(1, FRAMES + 1)]
    gv = [env(gli, (f - 1) / FPS) for f in range(1, FRAMES + 1)]
    screens_rig.key_series(mbody, SOCK % 'Socket_1', -1, rv)
    screens_rig.key_series(mbody, SOCK % 'Socket_3', -1, gv)
    # the game's glow under it: the only thing that pulls the creature out of the basement dark
    ml = light(f'{name}_Uplight', 'AREA', (0, 0.55, 0.04), 0.0, (1.0, 0.32, 0.12), C_MON, rot=(math.pi, 0, 0), size=(0.6, 0.6))
    ml.parent = mspot
    ml.data.shadow_maximum_resolution = 0.02
    screens_rig.key_series(ml.data, 'energy', -1, [28.0 * v * (1.0 - 0.5 * g) for v, g in zip(rv, gv)])
    # nothing to evaluate while unrevealed: keep it out of the render entirely
    hidden, start = [], None
    for f, v in enumerate(rv, 1):
        if v <= 0.0 and start is None:
            start = f
        elif v > 0.0 and start is not None:
            hidden.append(((start - 1) / FPS, (f - 1) / FPS)); start = None
    if start is not None:
        hidden.append(((start - 1) / FPS, FRAMES / FPS + 1))
    hide_keys(mbody, hidden)
    # a stamp in the roar can put a foot through the floor: lift the creature by that much for those frames
    md = mbody.modifiers['MonsterGlitch']
    md.show_viewport = False
    floor_z = root.matrix_world.translation.z
    lift = [0.0] * FRAMES
    for t in roars:
        for f in range(T(t), min(FRAMES, T(t) + int(roar.frame_range[1]) + 6)):
            scene.frame_set(f)
            be = mbody.evaluated_get(bpy.context.evaluated_depsgraph_get())
            me = be.to_mesh()
            co = np.empty(len(me.vertices) * 3)
            me.vertices.foreach_get('co', co)
            mw = np.array(be.matrix_world)
            lift[f - 1] = max(0.0, floor_z - float((co.reshape(-1, 3) @ mw[2, :3] + mw[2, 3]).min()))
            be.to_mesh_clear()
    md.show_viewport = True
    if max(lift) > 0.0:
        lift = [max(lift[max(0, i - 2):i + 3]) for i in range(FRAMES)]
        lift = [sum(lift[max(0, i - 2):i + 3]) / len(lift[max(0, i - 2):i + 3]) for i in range(FRAMES)]
        screens_rig.key_series(mspot, 'location', 2, lift)

# ---------------------------------------------------------------- doors, flap, exterior light gags
flap = bpy.data.objects['DogFlap']
keys(flap, 'rotation_euler', [(0.0, 0.0), (20.30, 0.0), (20.45, 1.25), (20.75, 1.25), (21.05, -0.55), (21.35, 0.32),
                              (21.65, -0.16), (21.95, 0.07), (22.3, 0.0)], index=0, interp='BEZIER')
bdoor = bpy.data.objects['BasementDoor']
keys(bdoor, 'rotation_euler', [(0.0, 0.0), (26.6, 0.0), (28.4, 0.42), (29.3, 0.45), (30.5, 1.45)], index=2, interp='BEZIER')
# the AI voice: street lamps stutter on the syllables 5.3 - 11.5, porch light dies at 10.9
lamps = [o for o in bpy.data.objects if o.type == 'LIGHT' and o.name.startswith('StreetLamp_L')]
bulb_mat = next((m for m in bpy.data.materials if m.name.startswith('street_lamp_01_bulb')), None)
flick = [(0.0, 1.0), (5.3, 1.0)]
t = 5.35
while t < 11.5:
    flick += [(t, 1.0), (t + 0.04, R.uniform(0.05, 0.35)), (t + 0.12, R.uniform(0.6, 1.0))]
    t += R.choice((0.3, 0.3, 0.6, 0.45))
flick += [(11.6, 1.0)]
for l in lamps:
    keys(l.data, 'energy', [(tt, 220.0 * v) for tt, v in flick], interp='CONSTANT')
# once the porch light dies the eye adapts: open up through the yard, hall and stairs, close down for the screens
keys(scene.view_settings, 'exposure', [(0.0, 0.8), (10.9, 0.8), (12.5, 1.45), (38.0, 1.45), (43.0, 0.8)])
bpy.data.objects['Hall_Moonfill'].data.energy *= 4.0
# moonlight from the window at the end of the hall rakes the walls and the basement door
hm2 = light('Hall_Moonfill2', 'AREA', (0.3, 6.1, 2.3), 24.0, (0.55, 0.65, 1.0), bpy.data.collections['LIGHTS'], size=(0.8, 0.8))
look_at(hm2, Vector((-0.4, 3.6, 0.8)), 'Y')
if bulb_mat:
    bsdf = [n for n in bulb_mat.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'][0]
    keys(bsdf.inputs['Emission Strength'], 'default_value', [(tt, 40.0 * v) for tt, v in flick], interp='CONSTANT')
porch = bpy.data.objects['PorchLamp_L']
e0 = porch.data.energy
keys(porch.data, 'energy', [(0.0, e0), (10.85, e0), (10.9, e0 * 0.2), (10.95, e0), (11.0, 0.0)], interp='CONSTANT')
pem = [n for n in bpy.data.materials['PorchLampGlow'].node_tree.nodes if n.type == 'EMISSION'][0]
e0 = pem.inputs['Strength'].default_value
keys(pem.inputs['Strength'], 'default_value', [(0.0, e0), (10.85, e0), (10.9, e0 * 0.2), (10.95, e0), (11.0, 0.0)], interp='CONSTANT')

# ---------------------------------------------------------------- what renders when (saves a lot of shadow work)
T_INSIDE, T_BELOW, T_DESK = 20.6, 34.0, 30.0
END = FRAMES / FPS + 1
for o in list(bpy.data.objects):
    n = o.name
    if any(c.name in ('STREET', 'EXTERIOR') for c in o.users_collection):     # yard, street, neighbours, trees
        hide_keys(o, [(T_BELOW, END)])
    elif o.type == 'LIGHT' and n.startswith(('StreetLamp', 'PorchLamp', 'Moon', 'Hall_')):
        hide_keys(o, [(T_BELOW, END)])
    elif n.endswith('_Glow'):
        hide_keys(o, [(T_INSIDE, END)])
for c in (C_DESK, C_DL, C_HUMAN):
    for o in c.all_objects:
        if o.type in ('MESH', 'CURVE', 'LIGHT', 'VOLUME') and o.name not in ('StairSpill', 'BasementHaze'):
            hide_keys(o, [(0.0, T_DESK)])
# no screen light during the blackout 157.3 - 168 is already in the per-frame light keys

# ---------------------------------------------------------------- camera
C_CAM = coll('CAMERA')
cam = camera_rig.build(scene, C_CAM)
# the arm sways under the shallow elbow close-ups: pull focus onto the cannula itself, frame by frame
fdist = [fc for fc in screens_rig.all_fcurves(cam.data.animation_data.action) if fc.data_path == 'dof.focus_distance'][0]
for f in range(T(174.0), T(180.4)):
    scene.frame_set(f)
    hub = cath['frame'].matrix_world @ catheter.HUB_C
    depth = (hub - cam.matrix_world.translation).dot(cam.matrix_world.to_3x3() @ Vector((0, 0, -1)))
    kp = fdist.keyframe_points[f - 1]
    u = min(1.0, (f - T(174.0)) / (T(175.5) - T(174.0)))
    kp.co[1] += (depth - kp.co[1]) * u * u * (3 - 2 * u)
fdist.update()

# ---------------------------------------------------------------- render settings
ee = scene.eevee
ee.taa_render_samples = 32
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
scene.render.resolution_percentage = 100
scene.render.fps = FPS
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGB'
scene.render.filepath = os.path.join(CLIP, 'renders', 'frames', 'f_')

# shadow maps are redrawn every TAA sample, so they were ~85% of a frame: trim what doesn't show
for m in bpy.data.materials:                          # only cut-out leaves etc. need the hashed shadow pass
    if m.use_transparent_shadow and not (m.node_tree and any(l.to_socket.name == 'Alpha' for l in m.node_tree.links)):
        m.use_transparent_shadow = False
for o in bpy.data.objects:
    if o.type == 'MESH' and 'tree' in o.name.lower():  # 350k-poly canopies; their shadows barely read at night
        o.visible_shadow = False
    if o.type != 'LIGHT':
        continue
    if o.name in ('ScreenBounce', 'StairSpill', 'PhoneLight') or o.name.endswith('_Uplight'):   # fills
        o.data.use_shadow = False
    else:
        o.data.shadow_maximum_resolution = max(o.data.shadow_maximum_resolution, 0.03 if o.data.type == 'AREA' else 0.005)

# ---------------------------------------------------------------- compositor: bloom + lens dispersion that kicks on hits
# (grain, vignette, glitch slices and the title go on in the ffmpeg pass: no re-render to tweak them)
ng = bpy.data.node_groups.new('ClipPost', 'CompositorNodeTree')
ng.interface.new_socket('Image', in_out='OUTPUT', socket_type='NodeSocketColor')
rl = ng.nodes.new('CompositorNodeRLayers')
gl = ng.nodes.new('CompositorNodeGlare')
gl.name = 'Bloom'
gl.inputs['Type'].default_value = 'Bloom'
gl.inputs['Quality'].default_value = 'High'
gl.inputs['Threshold'].default_value = 0.9
gl.inputs['Strength'].default_value = 0.35
gl.inputs['Size'].default_value = 0.6
ld = ng.nodes.new('CompositorNodeLensdist')
ld.name = 'Lens'
ld.inputs['Distortion'].default_value = -0.015
ld.inputs['Fit'].default_value = True
go = ng.nodes.new('NodeGroupOutput')
ng.links.new(rl.outputs['Image'], gl.inputs['Image'])
ng.links.new(gl.outputs['Image'], ld.inputs['Image'])
ng.links.new(ld.outputs['Image'], go.inputs[0])
scene.compositing_node_group = ng
scene.render.use_compositing = True
HITS = [12.0, 20.45, 30.4, 45.9, 60.0, 100.0, 110.3, 119.9, 124.5, 149.896, 151.096, 152.296, 153.496, 154.696,
        155.896, 168.0, 180.4, 206.3, 214.24]
disp = []
for f in range(1, FRAMES + 1):
    t = (f - 1) / FPS
    v = 0.006
    for h in HITS:
        if 0 <= t - h < 0.5:
            v = max(v, 0.006 + 0.05 * math.exp(-(t - h) / 0.09))
    disp.append(v)
screens_rig.key_series(ng, 'nodes["Lens"].inputs[3].default_value', -1, disp)   # Dispersion
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(CLIP, 'blend', 'claudaine.blend'), compress=True)
print('SAVED claudaine.blend', flush=True)
