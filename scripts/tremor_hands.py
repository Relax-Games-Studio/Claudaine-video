"""Hands closer to the keys while the Tremor loop plays.

The Tremor loop shakes the hands 2-6 cm above the keyboard, the index and middle fingers highest, which reads as
floating in the close-up of the hands. For every frame of the Tremor strip this measures how far the hand's lowest
point (usually the curled pinky) and each fingertip are above whatever lies under them (keys, case, desk mat).
The forearm bends at the elbow to lower the whole hand by up to DROP, then the index, middle and ring fingers bend
at the knuckle to lower their tips by up to CURL more; nothing comes closer than FLOOR at that frame or its
neighbours. The bends sit on a COMBINE NLA track above the others, so they add to whatever the strips below play.
While the right hand is on the mouse its grip takes over (scaled by 1 - grip).
build_scene calls lower() after grip_rig.setup()."""
import bpy
from mathutils import Vector, Quaternion
from mathutils.bvhtree import BVHTree
import screens_rig

DROP = 0.015            # the hand at most this much lower
CURL = 0.015            # each curled fingertip at most this much lower again
FLOOR = 0.005           # kept at least this far above the surface under it
HOLD = 4                # frames either side whose clearance also limits a frame's drop
SMOOTH = 2              # then a box average over 2 * SMOOTH + 1 frames (never exceeds the per-frame limit)
FINGERS = ('Thumb', 'Index', 'Middle', 'Ring', 'Pinky')
CURLED = ('Index', 'Middle', 'Ring')
SIDES = ('Left', 'Right')


def surfaces():
    dg = bpy.context.evaluated_depsgraph_get()
    vs, ps = [], []
    for ob in bpy.data.objects:
        if ob.type == 'MESH' and (ob.name.startswith('Keyboard') and 'Cable' not in ob.name or ob.name == 'Desk_Mat'):
            e = ob.evaluated_get(dg)
            me = e.to_mesh()
            n = len(vs)
            vs += [e.matrix_world @ v.co for v in me.vertices]
            ps += [tuple(i + n for i in p.vertices) for p in me.polygons]
            e.to_mesh_clear()
    return BVHTree.FromPolygons(vs, ps)


def group_verts(body, names):
    gi = {body.vertex_groups[n].index for n in names if n in body.vertex_groups}
    return [v.index for v in body.data.vertices if any(g.group in gi and g.weight > 0.5 for g in v.groups)]


def window(xs, i, r):
    return xs[max(0, i - r):i + r + 1]


def limited(room, most):
    """per-frame drop from per-frame clearance: at most `most`, held under the clearance of the neighbouring
    frames, then smoothed (the average of held values never exceeds the frame's own limit)"""
    raw = [0.0 if r is None else min(most, max(0.0, r)) for r in room]
    held = [min(window(raw, i, HOLD)) for i in range(len(raw))]
    return [sum(window(held, i, SMOOTH)) / len(window(held, i, SMOOTH)) for i in range(len(held))]


def lower(rig, body, strip, mouse):
    scene = bpy.context.scene
    f0, f1 = int(strip.frame_start), int(strip.frame_end)
    span = range(f0, f1 + 1)
    bvh = surfaces()
    P = rig.pose.bones
    # what moves: the forearm (whole hand) and the knuckle of each curled finger, each with the verts it carries
    # and the bone whose head it turns about
    joints = {}
    for s in SIDES:
        joints[(s, 'Hand')] = (f'mixamorig:{s}ForeArm', group_verts(body, [f'mixamorig:{s}Hand'] + [
            f'mixamorig:{s}Hand{f}{k}' for f in FINGERS for k in (1, 2, 3)]), group_verts(body, [f'mixamorig:{s}Hand{f}3' for f in FINGERS]))
        for f in CURLED:
            tip = group_verts(body, [f'mixamorig:{s}Hand{f}3'])
            joints[(s, f)] = (f'mixamorig:{s}Hand{f}1', tip, tip)
    saved = [(m, m.show_viewport) for m in body.modifiers if m.type != 'ARMATURE']
    for m, _ in saved:
        m.show_viewport = False
    gap = {j: [] for j in joints}
    pose = {j: [] for j in joints}          # (horizontal joint -> tips, the bone's orientation in armature space)
    down = Vector((0, 0, -1))
    for f in span:
        scene.frame_set(f)
        e = body.evaluated_get(bpy.context.evaluated_depsgraph_get())
        me = e.to_mesh()
        mw = e.matrix_world
        for j, (bone, verts, tips) in joints.items():
            g = None
            for i in verts:
                p = mw @ me.vertices[i].co
                hit = bvh.ray_cast(p - down * 0.05, down, 0.2)
                if hit[0] is not None and (g is None or p.z - hit[0].z < g):
                    g = p.z - hit[0].z
            gap[j].append(g)
            tip = sum((mw @ me.vertices[i].co for i in tips), Vector()) / len(tips)
            dh = tip - rig.matrix_world @ P[bone].head
            dh.z = 0
            pose[j].append((dh, P[bone].matrix.to_3x3().normalized()))
        e.to_mesh_clear()
    for m, v in saved:
        m.show_viewport = v

    def fade(f):
        k = 1.0
        if strip.blend_in:
            k = min(k, (f - f0) / strip.blend_in)
        if strip.blend_out:
            k = min(k, (f1 - f) / strip.blend_out)
        return max(0.0, min(1.0, k))

    grip = next(c for c in screens_rig.all_fcurves(mouse.animation_data.action) if c.data_path == '["grip"]')
    drop = {}
    for s in SIDES:
        drop[(s, 'Hand')] = limited([None if g is None else g - FLOOR for g in gap[(s, 'Hand')]], DROP)
        for f in CURLED:
            room = [None if g is None else g - FLOOR - d for g, d in zip(gap[(s, f)], drop[(s, 'Hand')])]
            drop[(s, f)] = limited(room, CURL)

    act = bpy.data.actions.new('TremorHands')
    ad = rig.animation_data
    ad.action = act
    to_arm = rig.matrix_world.inverted().to_3x3()
    most = {}
    for j, (bone, _, _) in joints.items():
        pb = P[bone]
        most[j] = 0.0
        for i, f in enumerate(span):
            d = drop[j][i] * fade(f) * (1.0 - grip.evaluate(f) if j[0] == 'Right' else 1.0)
            most[j] = max(most[j], round(d, 4))
            # world rotation about a horizontal axis through the joint, square to the joint -> tips line, that
            # drops the tips by d; as a rotation after the bone's own (what COMBINE multiplies in)
            dh, B = pose[j][i]
            axis = to_arm @ Vector((0, 0, 1)).cross(dh)
            pb.rotation_quaternion = Quaternion((B.inverted() @ axis).normalized(), d / max(dh.length, 0.02))
            pb.keyframe_insert('rotation_quaternion', frame=f, group=bone.split(':')[1])
    ad.action = None
    tr = ad.nla_tracks.new()
    tr.name = 'TremorHands'
    st = tr.strips.new('TremorHands', f0, act)
    st.blend_type, st.extrapolation = 'COMBINE', 'NOTHING'
    return most
