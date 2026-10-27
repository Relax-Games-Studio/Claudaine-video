"""Right hand on the mouse. Whenever the Typing loop sends the hand to the mouse, an IK on the forearm and a Copy
Rotation on the hand pull it onto the palm grip solved against the meshes (solve_grip.py -> blend/mouse_grip.json),
and a 'MouseGrip' NLA track on top lays the fingers on the shell. All three follow one grip weight, keyed per frame
as Mouse["grip"] (the constraints read it through drivers, the NLA strip copies it into its influence). The mouse
only moves while it is held, so it never slides on its own.
build_scene calls setup() once the human's Typing / Override tracks exist."""
import bpy, json, math, os
from mathutils import Vector
from lib_build import CLIP
import screens_rig

HB, FA = 'mixamorig:RightHand', 'mixamorig:RightForeArm'
CYCLE = 381                                  # the Typing loop's period (action frames 1..382)
# grip weight over one loop: holds 230..295 and 382(=1)..58, eased in / out while the hand travels
RAMPS = ((223, 230, 1), (295, 301, -1), (375, 382, 1), (58, 63, -1))
# mouse moves while held, in DESK_ROOT metres (+x = the typist's right, +y = away from them):
# (loop frame, dx, dy); the B grip starts at frame 375 of the previous loop, written as 375 - CYCLE
PATH_A = ((230, 0, 0), (244, -0.012, 0.006), (256, -0.009, 0.004), (270, 0.005, -0.003), (282, 0.003, 0.0),
          (294, 0, 0))
PATH_B = ((-6, 0, 0), (4, 0, 0), (24, -0.028, 0.008), (34, -0.026, 0.010), (46, -0.012, 0.004), (57, 0, 0))
YAW_PER_M = 1.5                              # the wrist pivots: a move to the left turns the nose left


def ease(x):
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def weight(c):
    """grip weight at loop frame c (1..381)"""
    for a, b, s in RAMPS:
        cc = c + CYCLE if b > CYCLE and c < a - CYCLE / 2 else c
        if a <= cc <= b:
            u = ease((cc - a) / (b - a))
            return u if s > 0 else 1 - u
    return 1.0 if 230 <= c <= 295 or c <= 58 else 0.0


def path_at(pts, u):
    if u <= pts[0][0] or u >= pts[-1][0]:
        return 0.0, 0.0
    for (u0, x0, y0), (u1, x1, y1) in zip(pts, pts[1:]):
        if u0 <= u <= u1:
            s = 0.5 - 0.5 * math.cos(math.pi * (u - u0) / (u1 - u0))
            return x0 + (x1 - x0) * s, y0 + (y1 - y0) * s


def offset(c):
    """mouse offset (dx, dy) the hand pushes it to at loop frame c"""
    if 230 <= c <= 296:
        return path_at(PATH_A, c)
    return path_at(PATH_B, c - CYCLE if c >= 375 else c)


def strip_influence(s, f):
    if f < s.frame_start or f > s.frame_end:
        return 0.0
    k = 1.0
    if s.blend_in:
        k = min(k, (f - s.frame_start) / s.blend_in)
    if s.blend_out:
        k = min(k, (s.frame_end - f) / s.blend_out)
    return max(0.0, min(1.0, k))


def series(override, frames):
    """per-frame (grip weight, desired dx, dy, tremor amount) from the loop the hand is actually playing: the
    Typing loop, the Tremor loop (own phase) where its strip blends in, released while a freeze holds the pose"""
    trem = override.strips['Tremor']
    freezes = [s for s in override.strips if s.name.startswith('Freeze')]
    out = []
    for f in range(1, frames + 1):
        c = (f - 1) % CYCLE + 1
        ct = (f - int(trem.frame_start)) % CYCLE + 1
        it = strip_influence(trem, f)
        w = (1 - it) * weight(c) + it * weight(ct)
        o, ot = offset(c), offset(ct)
        dx, dy = (1 - it) * o[0] + it * ot[0], (1 - it) * o[1] + it * ot[1]
        for s in freezes:
            w *= 1 - strip_influence(s, f)
        out.append((w, dx, dy, it))
    return out


def setup(rig, mouse, col, frames):
    g = json.load(open(os.path.join(CLIP, 'blend', 'mouse_grip.json')))
    ad = rig.animation_data
    data = series(ad.nla_tracks['Override'], frames)

    # the solved hand pose rides on the mouse
    mh = bpy.data.objects.new('MouseHand', None)
    mh.empty_display_size = 0.03
    col.objects.link(mh)
    mh.parent = mouse
    mh.location = g['hand_loc']
    mh.rotation_mode = 'QUATERNION'
    mh.rotation_quaternion = g['hand_quat']

    # the mouse: held, it goes where the hand pushes it (plus the tremor's shake); let go, it stays put
    home = mouse.location.copy()
    yaw0 = mouse.rotation_euler.z
    pos = Vector((0.0, 0.0))
    xs, ys, rs, grip = [], [], [], []
    for i, (w, dx, dy, it) in enumerate(data):
        f = i + 1
        sh = it * w
        jx = sh * 0.0015 * (math.sin(f * 1.63) + 0.6 * math.sin(f * 2.71 + 1.0))
        jy = sh * 0.0012 * (math.sin(f * 1.37 + 2.0) + 0.5 * math.sin(f * 3.11))
        pos += w * (Vector((dx + jx, dy + jy)) - pos)
        xs.append(home.x + pos.x)
        ys.append(home.y + pos.y)
        rs.append(yaw0 - YAW_PER_M * pos.x + sh * 0.012 * math.sin(f * 2.23 + 0.5))
        grip.append(w)
    screens_rig.key_series(mouse, 'location', 0, xs)
    screens_rig.key_series(mouse, 'location', 1, ys)
    screens_rig.key_series(mouse, 'rotation_euler', 2, rs)
    mouse['grip'] = 0.0
    screens_rig.key_series(mouse, '["grip"]', -1, grip)

    # arm: forearm IK to the hand's place on the mouse, hand rotation copied from it; both follow Mouse["grip"]
    P = rig.pose.bones
    ik = P[FA].constraints.new('IK')
    ik.name = 'GripIK'
    # 3 bones: in the second grip of the loop the typist sits back, and only the clavicle gives the last 5 cm
    ik.target, ik.chain_count, ik.use_tail, ik.use_stretch = mh, 3, True, False
    cr = P[HB].constraints.new('COPY_ROTATION')
    cr.name = 'GripRot'
    cr.target = mh
    cr.target_space = cr.owner_space = 'WORLD'
    for c in (ik, cr):
        d = c.driver_add('influence').driver
        d.type = 'AVERAGE'
        v = d.variables.new()
        v.type = 'SINGLE_PROP'
        v.targets[0].id_type = 'OBJECT'
        v.targets[0].id = mouse
        v.targets[0].data_path = '["grip"]'

    # fingers: one held pose on a top NLA track, its influence = the grip weight
    act = bpy.data.actions.new('MouseGrip')
    ad.action = act
    for n, qv in g['fingers'].items():
        P[n].rotation_quaternion = qv
        P[n].keyframe_insert('rotation_quaternion', frame=1, group=n.split(':')[1])
    ad.action = None
    tr = ad.nla_tracks.new()
    tr.name = 'MouseGrip'
    s = tr.strips.new('MouseGrip', 1, act)
    s.action_frame_start, s.action_frame_end = 1, 2
    s.scale = frames + 10
    s.blend_type, s.extrapolation = 'REPLACE', 'NOTHING'
    s.use_animated_influence = True
    fc = s.fcurves.find('influence')
    if fc is None:
        s.keyframe_insert('influence', frame=1)
        fc = s.fcurves.find('influence')
    fc.keyframe_points.clear()
    fc.keyframe_points.add(len(grip))
    co = []
    for i, w in enumerate(grip):
        co += (i + 1, w)
    fc.keyframe_points.foreach_set('co', co)
    fc.keyframe_points.foreach_set('interpolation', [1] * len(grip))
    fc.update()
    return mh
