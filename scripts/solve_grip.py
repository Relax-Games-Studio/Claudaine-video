"""Solve a static palm grip of the right hand on the mouse -> blend/mouse_grip.json.
The hand bone's matrix relative to the mouse and the finger rotations are found against the real meshes: the skin
around each hand / finger bone is snapshotted rigidly in that bone's space at a grip frame of the Typing loop,
then the hand is oriented and lowered until the palm rests on the shell, and each finger segment is rotated
about its flex axis until it lies on the shell (or the mat), from the knuckle out.
Run: Blender -b blend/claudaine.blend --python scripts/solve_grip.py   (claudaine.blend must hold the new mouse)"""
import bpy, sys, os, json, math
from mathutils import Vector, Matrix, Quaternion
from mathutils.bvhtree import BVHTree
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from lib_build import CLIP
import desk

F0 = 259                                   # Typing-loop frame with the hand on the mouse
MAT_Z = desk.DESK_TOP + 0.003
CONTACT = 0.0007                           # resting skin-to-surface gap
HB = 'mixamorig:RightHand'
FING = ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky')
FB = {f: [f'mixamorig:RightHand{f}{k}' for k in (1, 2, 3)] for f in FING}
NAMES = [HB] + [n for f in FING for n in FB[f]]

scene = bpy.context.scene
root, rig, body = bpy.data.objects['DESK_ROOT'], bpy.data.objects['HumanRig'], bpy.data.objects['Body']
for tr in rig.animation_data.nla_tracks:
    if tr.name == 'MouseGrip':
        tr.mute = True
for pb in rig.pose.bones:
    for c in pb.constraints:
        if c.name.startswith('Grip'):
            c.mute = True
scene.frame_set(F0)
dg = bpy.context.evaluated_depsgraph_get()
inv = root.matrix_world.inverted()
A = inv @ rig.matrix_world                # armature space -> DESK_ROOT space
P = rig.pose.bones


def basis_quat(pb):
    return pb.rotation_quaternion.copy() if pb.rotation_mode == 'QUATERNION' else pb.rotation_euler.to_quaternion()


# ---- rigid skin snapshot: each kept vertex goes to its dominant hand / finger bone
masks = [(body.vertex_groups[m.vertex_group].index, m.invert_vertex_group, m.threshold)
         for m in body.modifiers if m.type == 'MASK' and m.show_viewport]
kept = {}
for v in body.data.vertices:
    w = {g.group: g.weight for g in v.groups}
    if all((w.get(gi, 0.0) > th) != iv for gi, iv, th in masks):
        kept[v.index] = len(kept)
me = body.evaluated_get(dg).to_mesh()
assert len(me.vertices) == len(kept), (len(me.vertices), len(kept))
MB = inv @ body.matrix_world
gname = {body.vertex_groups[n].index: n for n in NAMES if n in body.vertex_groups}
deform = {g.index for g in body.vertex_groups if g.name.startswith('mixamorig:')}
Lb = {n: A @ P[n].matrix for n in NAMES}
Lbi = {n: m.inverted() for n, m in Lb.items()}
loc = {n: [] for n in NAMES}
for v in body.data.vertices:
    if v.index not in kept:
        continue
    best, bw = None, 0.0
    tot = sum(g.weight for g in v.groups if g.group in deform) or 1.0    # the Armature modifier normalises
    for g in v.groups:
        n = gname.get(g.group)
        if n and g.weight / tot > bw:
            best, bw = n, g.weight / tot
    if best and bw >= 0.45:
        loc[best].append(Lbi[best] @ (MB @ me.vertices[kept[v.index]].co))
body.evaluated_get(dg).to_mesh_clear()
print('points per bone', {n.split(':')[1]: len(p) for n, p in loc.items()})

# ---- the mouse shell as a BVH in DESK_ROOT space (signed distance; the mat is a floor)
sh = bpy.data.objects['Mouse_Shell']
sme = sh.evaluated_get(dg).to_mesh()
MS = inv @ sh.matrix_world
bvh = BVHTree.FromPolygons([MS @ v.co for v in sme.vertices], [list(p.vertices) for p in sme.polygons])
sh.evaluated_get(dg).to_mesh_clear()
MOUSE_M = inv @ bpy.data.objects['Mouse'].matrix_world


def sdist(p):
    hit, nor, i, d = bvh.find_nearest(p)
    s = d if (p - hit).dot(nor) >= 0 else -d
    return min(s, p.z - MAT_Z)


def min_d(pts):
    return min(sdist(p) for p in pts) if pts else 1.0


# ---- forward kinematics of the hand + fingers from a hand matrix and finger basis rotations
rest = {n: P[n].bone.matrix_local for n in NAMES}
par = {n: P[n].parent.name for n in NAMES if n != HB}
rel = {n: rest[par[n]].inverted() @ rest[n] for n in par}
tloc = {n: Matrix.Translation(P[n].location) for n in NAMES}


def fk(H, q):
    out = {HB: H}
    for f in FING:
        for n in FB[f]:
            out[n] = out[par[n]] @ rel[n] @ tloc[n] @ q[n].to_matrix().to_4x4()
    return out


q0 = {n: basis_quat(P[n]) for n in NAMES}
chk = fk(Lb[HB], q0)
err = max((chk[n].translation - Lb[n].translation).length for n in NAMES)
print('fk check', err)


def world_pts(mats, n):
    m = mats[n]
    return [m @ p for p in loc[n]]


# ---- 1. hand orientation + placement: palm resting on the hump, knuckles over the button seam
H0 = Lb[HB]
t0, r0, s0 = H0.decompose()
S = Matrix.Diagonal(s0.to_4d())
R0 = r0.to_matrix()
mcp_rel = {n: (rest[HB].inverted() @ rest[n]).translation for n in (FB['Index'][0], FB['Middle'][0])}
# palm skin: the hand bone's own verts + the knuckle-1 verts behind their joint (this rig gives the metacarpal
# skin to the proximal finger bones), all in hand space at the snapshot pose
palm_local = list(loc[HB])
for f in FING[1:]:
    n = FB[f][0]
    mr = rel[n] @ tloc[n] @ q0[n].to_matrix().to_4x4()
    palm_local += [mr @ p for p in loc[n] if p.y < 0]
print('palm points', len(palm_local))


pinky_rel = (rest[HB].inverted() @ rest[FB['Pinky'][0]]).translation


def frame_of(H):
    """anatomical frame (columns: forward, palm normal, side) of a hand matrix: forward = wrist -> middle
    knuckle, palm normal from the knuckle line (pinky -> index) crossed with it"""
    hd = H.translation
    fwd = (H @ mcp_rel[FB['Middle'][0]] - hd).normalized()
    across = (H @ mcp_rel[FB['Index'][0]] - H @ pinky_rel).normalized()
    n = across.cross(fwd).normalized()
    fwd = n.cross(across).normalized()
    return Matrix((fwd, n, fwd.cross(n))).transposed()


F0m = frame_of(H0)


def place(yaw, pitch, roll, target):
    """hand with its forward axis yawed / pitched (fingers up > 0) and rolled (pinky side, +X, down > 0) from
    'straight ahead, palm down', its index / middle knuckles moved over `target` and lowered until the palm rests
    on the shell"""
    D3 = Matrix.Rotation(yaw, 3, 'Z') @ Matrix.Rotation(pitch, 3, 'X') @ Matrix.Rotation(roll, 3, 'Y')
    Fd = D3 @ Matrix(((0, 0, -1), (1, 0, 0), (0, -1, 0)))    # columns: forward +Y, palm -Z, side = fwd x n = -X
    R = Fd @ F0m.transposed() @ R0
    H = R.to_4x4() @ S
    mid = sum((H @ mcp_rel[n] for n in mcp_rel), Vector()) / 2
    off = Vector((target.x - mid.x, target.y - mid.y, 0.835 - mid.z))
    palm = [H @ p for p in palm_local]
    for it in range(8):
        m = min(sdist(p + off) for p in palm)
        if abs(m - CONTACT) < 1e-4:
            break
        off.z -= m - CONTACT
    Hn = Matrix.Translation(off) @ H
    pp = [p + off for p in palm]
    nrm = Fd.col[1]
    ctr = sum(pp, Vector()) / len(pp)
    under = sorted(sdist(p) for p in pp if (p - ctr).dot(nrm) > 0)
    return Hn, under[int(len(under) * 0.3)], min(p.z for p in pp)


def knuckle_axis(n, H, q):
    """the knuckle line (pinky -> index) in bone n's space, signed so that a positive rotation curls; the sign is
    read off the finger's first bone, which lies flat enough for 'its tail moves to the palm side' to mean curl"""
    mats = fk(H, q)
    knuckles = (mats[FB['Index'][0]].translation - mats[FB['Pinky'][0]].translation).normalized()
    b1 = next(FB[f][0] for f in FING if n in FB[f])
    ax1 = (mats[b1].to_3x3().normalized().inverted() @ knuckles).normalized()
    qq = dict(q)
    qq[b1] = q[b1] @ Quaternion(ax1, 0.1)
    tail = lambda m: m[b1] @ Vector((0, P[b1].bone.length, 0))
    if (tail(fk(H, qq)) - tail(mats)).dot(frame_of(H).col[1]) < 0:
        knuckles = -knuckles
    return (mats[n].to_3x3().normalized().inverted() @ knuckles).normalized()


PRESET = (0.0, math.radians(22), math.radians(12))     # a relaxed curl the solve starts from (middle, tip)


def relaxed(H):
    q = dict(q0)
    for f in FING[1:]:
        for k in (1, 2):
            n = FB[f][k]
            q[n] = q[n] @ Quaternion(knuckle_axis(n, H, q), PRESET[k])
    return q


def hand_search(target):
    best = None
    for yaw in range(-10, 11, 5):
        for pitch in range(0, 31, 3):
            for roll in range(-6, 28, 3):
                H, gap, low = place(D(yaw), D(pitch), D(roll), target)
                score = -gap - 0.0003 * (abs(yaw) + abs(roll - 16) + abs(pitch - 12)) / 5 - (1.0 if low < MAT_Z + 0.003 else 0)
                if best is None or score > best[0]:
                    best = (score, yaw, pitch, roll, H, gap, low)
    return best


# the knuckles slide along the mouse until the relaxed middle fingertip ends just short of the nose
D = math.radians
NOSE = desk.M_LEN / 2 - 0.007           # mouse-local (unscaled)
MI = MOUSE_M.inverted()
cands = []
for ty in (-0.034, -0.028, -0.022, -0.016, -0.010, -0.004):
    b = hand_search(MOUSE_M @ Vector((-0.002, ty, 0.0)))
    tip = MI @ (fk(b[4], relaxed(b[4]))[FB['Middle'][2]] @ Vector((0, P[FB['Middle'][2]].bone.length, 0)))
    print('knuckles at y', ty, 'hand', b[1:4], 'gap %.2f mm' % (b[5] * 1000), 'tip y %.4f' % tip.y)
    cands.append((abs(tip.y - NOSE) + 0.5 * max(0.0, b[5] - 0.003), ty, b))
_, TY, best = min(cands, key=lambda c: c[0])
print('hand', best[1:4], 'knuckles y', TY, 'palm gap p30', round(best[5] * 1000, 2), 'mm, lowest skin', round(best[6], 4))
H = best[4]

# ---- 2. fingers: each segment rotates about its flex axis until it rests on the surface
log = {}


def flex_axis(n, toward):
    """thumb: local axis (+/-X or +/-Z) whose positive rotation moves the bone's tail most along `toward`"""
    base = fk(H, q)
    tail0 = base[n] @ Vector((0, P[n].bone.length, 0))
    best = None
    for ax in (Vector((1, 0, 0)), Vector((-1, 0, 0)), Vector((0, 0, 1)), Vector((0, 0, -1))):
        qq = dict(q)
        qq[n] = q[n] @ Quaternion(ax, 0.1)
        tail = fk(H, qq)[n] @ Vector((0, P[n].bone.length, 0))
        g = (tail - tail0).dot(toward)
        if best is None or g > best[0]:
            best = (g, ax)
    return best[1]


q = relaxed(H)
# close the finger spread of the snapshot pose a little: each finger turns about the palm normal toward the middle
mats = fk(H, q)
nrm = frame_of(H).col[1]
flat_dir = lambda m: (m.col[1].xyz - nrm * m.col[1].xyz.dot(nrm)).normalized()
dm = flat_dir(mats[FB['Middle'][0]])
for f in ('Index', 'Ring', 'Pinky'):
    n = FB[f][0]
    d = flat_dir(mats[n])
    ang = math.atan2(nrm.dot(d.cross(dm)), d.dot(dm))
    q[n] = q[n] @ Quaternion((mats[n].to_3x3().normalized().inverted() @ nrm).normalized(), 0.6 * ang)
    print('spread', f, round(math.degrees(ang), 1))

for f in FING:
    for k, n in enumerate(FB[f]):
        mats = fk(H, q)
        if f == 'Thumb':
            tip = mats[FB[f][-1]] @ Vector((0, P[FB[f][-1]].bone.length, 0))
            hit, nor, i, d = bvh.find_nearest(tip)
            ax = flex_axis(n, (hit - tip).normalized())
        else:                           # fingers curl about the knuckle line (pinky -> index), in bone space
            ax = knuckle_axis(n, H, q)
        lo_, hi_ = ((-0.35, 1.2) if k else (-0.4, 0.8)) if f != 'Thumb' else ((-0.35, 1.4) if k else (-0.5, 1.3))
        segs = FB[f][k:]                # the bone and everything it carries must stay out of the surface

        def g(a):
            qq = dict(q)
            qq[n] = q[n] @ Quaternion(ax, a)
            mm = fk(H, qq)
            # knuckle-1 bones: only their skin in front of the joint (this rig gives them the metacarpal skin,
            # which belongs to the palm that is already resting)
            return min(min_d([mm[s] @ p for p in loc[s] if s != FB[f][0] or f == 'Thumb' or p.y > 0.002])
                       for s in segs)
        if g(hi_) > CONTACT:            # never reaches anything (hanging over the side): a relaxed curl
            a = min(hi_, 0.45)
        elif g(lo_) < CONTACT:          # buried even fully extended
            a = lo_
        else:
            lo, hi = lo_, hi_
            for it in range(30):
                mid = (lo + hi) / 2
                if g(mid) > CONTACT:
                    lo = mid
                else:
                    hi = mid
            a = lo
        q[n] = q[n] @ Quaternion(ax, a)
        log[n] = (round(math.degrees(a), 1), tuple(round(x) for x in ax))
mats = fk(H, q)
report = {n.split(':')[1]: round(min_d(world_pts(mats, n)) * 1000, 2) for n in NAMES}
print('flex', {n.split(':')[1]: v for n, v in log.items()})
print('min gap mm', report)

Hm = MOUSE_M.inverted() @ H
tl, rq, sc = Hm.decompose()
out = {'frame': F0, 'hand_loc': list(tl), 'hand_quat': list(rq), 'hand_scale': list(sc),
       'fingers': {n: list(q[n]) for f in FING for n in FB[f]}, 'gaps_mm': report,
       'hand_offsets_deg': best[1:4], 'knuckles_y': TY}
json.dump(out, open(os.path.join(CLIP, 'blend', 'mouse_grip.json'), 'w'), indent=1)
print('GRIP saved')
