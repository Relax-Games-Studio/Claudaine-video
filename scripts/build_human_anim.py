"""Stage 2: retarget Mixamo X Bot animations onto HumanRig (MPFB, mixamorig:* bones).

Run: Blender -b <stage1.blend> --python scripts/build_human_anim.py -- <out.blend>

World-space retarget: for every bone the target gets the source's world rotation delta, applied
to the target rest pose after swinging the target bone onto the source rest direction (X Bot is in
T-pose, MPFB in A-pose). Hips translation is scaled by leg length and re-anchored so the character
sits on a seat at the origin, facing +Y (HumanRig object is rotated 180 deg about Z).
Actions are resampled from 30 fps to 24 fps.
"""
import bpy, os, sys, math, random
from mathutils import Matrix, Quaternion, Vector

OUT = sys.argv[sys.argv.index('--') + 1]
MIXAMO = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), 'assets', 'mixamo', '')
SRC_FPS, FPS = 30, 24
SEAT_BACK_TO_CENTER = 0.20   # seat centre is this far in front of the backmost point of the buttocks

scene = bpy.context.scene
scene.render.fps = FPS
rig = bpy.data.objects['HumanRig']
body = bpy.data.objects['Body']
rig.rotation_mode = 'XYZ'
rig.rotation_euler = (0, 0, math.pi)
rig.location = (0, 0, 0)
bpy.context.view_layer.update()

for pb in rig.pose.bones:
    pb.rotation_mode = 'QUATERNION'

order = []                                   # parents before children
def walk(b):
    order.append(b.name)
    for c in b.children:
        walk(c)
for b in rig.data.bones:
    if b.parent is None:
        walk(b)

G = Matrix.Rotation(math.pi, 4, 'Z')        # source faces -Y like the MPFB rest pose; the rig object adds the flip
rig_inv = rig.matrix_world.inverted()


def import_source(name):
    before = set(bpy.data.objects)
    bpy.ops.import_scene.fbx(filepath=MIXAMO + name + '.fbx', automatic_bone_orientation=False)
    new = [o for o in bpy.data.objects if o not in before]
    arm = next(o for o in new if o.type == 'ARMATURE')
    return arm, new


def rot3(m):
    return m.to_3x3().normalized()


def sample_source(src, bones, frames):
    """Per target frame: {bone: (world rotation 3x3, world head)} of the source with G applied."""
    out = []
    mw = G @ src.matrix_world
    for sf in frames:
        fi = int(math.floor(sf))
        scene.frame_set(fi, subframe=sf - fi)
        d = {}
        for n in bones:
            pb = src.pose.bones[n]
            m = mw @ pb.matrix
            d[n] = (rot3(m), m.translation.copy())
        out.append(d)
    return out


def retarget(src, frames):
    bones = [n for n in order if n in src.pose.bones]
    mw = G @ src.matrix_world
    S0 = {n: rot3(mw @ src.data.bones[n].matrix_local) for n in bones}
    T0 = {n: rot3(rig.matrix_world @ rig.data.bones[n].matrix_local) for n in bones}
    # Swing the target rest axis onto the source rest axis, keep the target's own roll.
    off = {}
    for n in bones:
        swing = (T0[n].col[1]).rotation_difference(S0[n].col[1]).to_matrix()
        off[n] = S0[n].inverted() @ swing @ T0[n]
    src_leg = (src.data.bones['mixamorig:Hips'].head_local - src.data.bones['mixamorig:LeftFoot'].head_local).length
    tgt_leg = (rig.data.bones['mixamorig:Hips'].head_local - rig.data.bones['mixamorig:LeftFoot'].head_local).length
    samples = sample_source(src, bones, frames)
    k_world = tgt_leg / (src_leg * src.matrix_world.to_scale()[0])   # source armature is in cm
    rest = {n: rig.data.bones[n].matrix_local for n in bones}
    rig_rot = rig_inv.to_3x3()
    keys = {n: [] for n in bones}
    hips_loc = []
    for d in samples:
        M = {}
        for n in bones:
            Rw = d[n][0] @ off[n]
            Ra = (rig_rot @ Rw).normalized()
            b = rig.data.bones[n]
            if b.parent is None:
                pos_w = d[n][1] * k_world
                Ma = Matrix.Translation(rig_inv @ pos_w) @ Ra.to_4x4()
                L = rest[n].inverted() @ Ma
                hips_loc.append(L.translation.copy())
                q = L.to_quaternion()
                M[n] = Ma
            else:
                p = b.parent.name
                base = M[p] @ rest[p].inverted() @ rest[n]
                q = (base.to_3x3().inverted() @ Ra).to_quaternion()
                M[n] = base @ q.to_matrix().to_4x4()
            keys[n].append(q)
    for n in bones:                          # quaternion sign continuity
        qs = keys[n]
        for i in range(1, len(qs)):
            if qs[i].dot(qs[i - 1]) < 0:
                qs[i] = -qs[i]
    return keys, hips_loc


def crossfade_loop(keys, hips_loc, W):
    """Overlap the last W frames onto the first W; result loops seamlessly (length n - W)."""
    n = len(hips_loc)
    def s(x):
        return x * x * (3 - 2 * x)
    nk = {}
    for b, qs in keys.items():
        out = []
        for i in range(n - W):
            if i < W:
                w = s(i / W)
                a, c = qs[n - W + i], qs[i]
                if a.dot(c) < 0:
                    c = -c
                out.append(a.slerp(c, w))
            else:
                out.append(qs[i])
        for i in range(1, len(out)):
            if out[i].dot(out[i - 1]) < 0:
                out[i] = -out[i]
        nk[b] = out
    nh = []
    for i in range(n - W):
        nh.append(hips_loc[n - W + i].lerp(hips_loc[i], s(i / W)) if i < W else hips_loc[i])
    return nk, nh


def write_action(name, keys, hips_loc, cyclic):
    act = bpy.data.actions.get(name) or bpy.data.actions.new(name)
    act.use_fake_user = True
    rig.animation_data_create()
    rig.animation_data.action = act
    n = len(hips_loc)
    frames = list(range(1, n + 1))
    def put(path, idx, vals, group):
        fc = act.fcurve_ensure_for_datablock(rig, path, index=idx, group_name=group)
        fc.keyframe_points.clear()
        fc.keyframe_points.add(n)
        co = [0.0] * (2 * n)
        co[0::2] = frames
        co[1::2] = vals
        fc.keyframe_points.foreach_set('co', co)
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR' if not cyclic else 'BEZIER'
            kp.handle_left_type = kp.handle_right_type = 'AUTO_CLAMPED'
        fc.update()
        if cyclic and not any(m.type == 'CYCLES' for m in fc.modifiers):
            fc.modifiers.new('CYCLES')
    for b, qs in keys.items():
        path = f'pose.bones["{b}"].rotation_quaternion'
        for i in range(4):
            put(path, i, [q[i] for q in qs], b)
    hb = 'mixamorig:Hips'
    for i in range(3):
        put(f'pose.bones["{hb}"].location', i, [v[i] for v in hips_loc], hb)
    act.frame_range = (1, n)
    act.use_frame_range = True
    act.use_cyclic = cyclic
    return act


def eval_body_points(frame, action):
    """Deformed Body vertex positions (world) at a frame with only the armature modifier."""
    rig.animation_data.action = action
    saved = [(m, m.show_viewport) for m in body.modifiers]
    for m, _ in saved:
        m.show_viewport = (m.type == 'ARMATURE')
    scene.frame_set(frame)
    dg = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(dg)
    me = ev.to_mesh()
    mw = body.matrix_world
    pts = [mw @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    for m, s in saved:
        m.show_viewport = s
    return pts


# Region masks from the rest shape (MPFB "body" group excludes helper geometry): buttocks/thighs, feet.
hip_h = rig.data.bones['mixamorig:Hips'].head_local.z
gi = body.vertex_groups['body'].index
body_vis = set(v.index for v in body.data.vertices if any(g.group == gi and g.weight > 0.5 for g in v.groups))
mix = body.shape_key_add(name='tmp_mix', from_mix=True)
rest_pts = [Vector(p.co) for p in mix.data]
body.shape_key_remove(mix)
seat_region = [i for i in body_vis if 0.72 * hip_h < rest_pts[i].z < 1.08 * hip_h and abs(rest_pts[i].x) < 0.2]
foot_region = [i for i in body_vis if rest_pts[i].z < 0.12]


def anchor(action, hips_loc, ref=None):
    """Shift hips so feet touch z=0 (or match `ref` seat contact) and the seat centre sits at the origin."""
    mid = 1 + len(hips_loc) // 2
    pts = eval_body_points(mid, action)
    seat_z = min(pts[i].z for i in seat_region)
    foot_z = min(pts[i].z for i in foot_region)
    back_y = min(pts[i].y for i in seat_region if pts[i].z < seat_z + 0.12)   # facing +Y: back is min y
    cx = sum(pts[i].x for i in seat_region) / len(seat_region)
    if ref is None:
        dz = -foot_z
    else:
        dz = ref['seat_z'] - seat_z
    shift_w = Vector((-cx, -(back_y + SEAT_BACK_TO_CENTER), dz))
    # hips location keys are in the hips bone rest frame; convert the world shift
    hb = rig.data.bones['mixamorig:Hips']
    shift_l = (rig.matrix_world.to_3x3() @ hb.matrix_local.to_3x3()).inverted() @ shift_w
    new = [v + shift_l for v in hips_loc]
    return new, {'seat_z': seat_z + dz, 'foot_z': foot_z + dz}


def bake(name, fbx, cyclic, loop_w=0, ref=None):
    src, new = import_source(fbx)
    a = src.animation_data.action
    f0, f1 = a.frame_range
    n = int((f1 - f0) * FPS / SRC_FPS) + 1
    frames = [f0 + i * SRC_FPS / FPS for i in range(n)]
    keys, hips = retarget(src, frames)
    for o in new:
        bpy.data.objects.remove(o, do_unlink=True)
    if loop_w:
        keys, hips = crossfade_loop(keys, hips, loop_w)
    act = write_action(name, keys, hips, cyclic)
    hips, info = anchor(act, hips, ref)
    act = write_action(name, keys, hips, cyclic)
    print(name, 'frames', len(hips), info)
    return act, keys, hips, info


typing, tkeys, thips, tinfo = bake('Typing', 'human_typing', True, loop_w=14)
idle, _, _, _ = bake('SeatedIdle', 'human_seated_idle', True, loop_w=10, ref=tinfo)
sit, _, _, _ = bake('SitToType', 'human_sit_to_type', False, ref=tinfo)

# Tremor: Typing plus withdrawal shaking (frequencies snapped to the loop so it stays cyclic).
rnd = random.Random(7)
n = len(thips)
T = n / FPS
SHAKE = {}
for side in ('Left', 'Right'):
    SHAKE[f'mixamorig:{side}Arm'] = 0.6
    SHAKE[f'mixamorig:{side}ForeArm'] = 1.4
    SHAKE[f'mixamorig:{side}Hand'] = 3.2
    for f in ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky'):
        for j in (1, 2, 3):
            SHAKE[f'mixamorig:{side}Hand{f}{j}'] = 4.5 if j > 1 else 3.0
SHAKE['mixamorig:Head'] = 0.8
SHAKE['mixamorig:Neck'] = 0.5
tr_keys = {}
for b, qs in tkeys.items():
    amp = math.radians(SHAKE.get(b, 0.0))
    if amp == 0:
        tr_keys[b] = qs
        continue
    comps = []
    for axis in range(3):
        for _ in range(3):
            f = round(rnd.uniform(4.5, 10.5) * T) / T
            comps.append((axis, f, rnd.uniform(0, 2 * math.pi), rnd.uniform(0.4, 1.0)))
    out = []
    for i, q in enumerate(qs):
        t = i / FPS
        e = [0.0, 0.0, 0.0]
        for axis, f, ph, w in comps:
            e[axis] += amp * w * math.sin(2 * math.pi * f * t + ph) / 2.2
        # occasional jerk: a slow envelope modulating amplitude
        env = 0.7 + 0.5 * math.sin(2 * math.pi * (round(0.7 * T) / T) * t + 1.3)
        out.append(q @ Quaternion((1, 0, 0), e[0] * env) @ Quaternion((0, 1, 0), e[1] * env) @ Quaternion((0, 0, 1), e[2] * env))
    tr_keys[b] = out
write_action('Tremor', tr_keys, thips, True)

rig.animation_data.action = typing
scene.frame_start, scene.frame_end = 1, len(thips)
scene['seat_z'] = tinfo['seat_z']
bpy.ops.wm.save_as_mainfile(filepath=OUT)
print('saved', OUT)
