"""Test renders of the mummy + human_report.json. Never saves the .blend.

Run: Blender -b blend/human.blend --python scripts/build_human_test.py -- <renders dir> <report.json> [views]
views: comma list of face,face_alive,full,hands (default all), or 'none' for the report only.
"""
import bpy, bmesh, sys, os, json, math
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

args = sys.argv[sys.argv.index('--') + 1:]
RDIR, REPORT = args[0], args[1]
VIEWS = (args[2] if len(args) > 2 else 'face,face_alive,full,hands').split(',')

scene = bpy.context.scene
rig = bpy.data.objects['HumanRig']
body = bpy.data.objects['Body']
typing = bpy.data.actions['Typing']
rig.animation_data.action = typing
f0, f1 = (int(round(x)) for x in typing.frame_range)
MID = (f0 + f1) // 2
B = rig.pose.bones


def bone_head(name):
    return rig.matrix_world @ B[name].head


def bone_tail(name):
    return rig.matrix_world @ B[name].tail


def r(v, n=4):
    return [round(float(x), n) for x in v]


FINGERS = ('Index', 'Middle', 'Ring', 'Pinky')


def fingertips(side):
    return {f: bone_tail(f'mixamorig:{side}Hand{f}3') for f in FINGERS + ('Thumb',)}


def mesh_world(ob, deps):
    ev = ob.evaluated_get(deps)
    me = ev.to_mesh()
    pts = [ev.matrix_world @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    return pts


# ---------------------------------------------------------------- report
# keyboard home row implied by the fingertips over the whole typing cycle
tips_all = []
for f in range(f0, f1 + 1, 2):
    scene.frame_set(f)
    for side in ('Left', 'Right'):
        t = fingertips(side)
        tips_all.extend(t[k] for k in FINGERS)
zs = sorted(p.z for p in tips_all)
home = sum(tips_all, Vector()) / len(tips_all)
key_top = zs[len(zs) // 10] - 0.007          # 10th-percentile fingertip bone tail minus finger pad

scene.frame_set(MID)
deps = bpy.context.evaluated_depsgraph_get()
lt, rt = fingertips('Left'), fingertips('Right')

# left elbow crease: the skin vertex on the inside of the bend, in the bend plane, nearest the joint
sh, el, wr = bone_head('mixamorig:LeftArm'), bone_head('mixamorig:LeftForeArm'), bone_head('mixamorig:LeftHand')
inner = ((sh - el).normalized() + (wr - el).normalized()).normalized()
bend_n = (sh - el).cross(wr - el).normalized()
ev = body.evaluated_get(deps)
me = ev.to_mesh()
nmat = ev.matrix_world.to_3x3().inverted().transposed()
best = None
for vx in me.vertices:
    p = ev.matrix_world @ vx.co
    d = p - el
    if d.length > 0.08:
        continue
    score = d.dot(inner) - 2.0 * abs(d.dot(bend_n))
    if best is None or score > best[0]:
        best = (score, p, (nmat @ vx.normal).normalized())
_, hit, nrm = best
ev.to_mesh_clear()
print('elbow crease: depth from joint', round((hit - el).length, 4), 'normal.inner', round(nrm.dot(inner), 3))

lens = {}
for nm in ('Lens_L', 'Lens_R'):
    pts = mesh_world(bpy.data.objects[nm], deps)
    lens[nm] = sum(pts, Vector()) / len(pts)
eye_pts = mesh_world(bpy.data.objects['Eyes'], deps)
eyes = {}
for nm, c in lens.items():
    side = [p for p in eye_pts if (p - c).length < (p - lens['Lens_R' if nm == 'Lens_L' else 'Lens_L']).length]
    eyes[nm[-1]] = sum(side, Vector()) / len(side)
head = bone_head('mixamorig:Head')
head_top = bone_head('mixamorig:HeadTop_End') if 'mixamorig:HeadTop_End' in B else bone_tail('mixamorig:Head')
face_fwd = ((lens['Lens_L'] + lens['Lens_R']) / 2 - (head + head_top) / 2)
face_fwd.z = 0

report = {
    'units': 'metres, Z up; origin = floor under seat centre (= DESK_ROOT); character faces +Y; '
             'character left = -X',
    'pose': {'action': 'Typing', 'frame': MID},
    'hips': r(bone_head('mixamorig:Hips')),
    'knee_L': r(bone_head('mixamorig:LeftLeg')), 'knee_R': r(bone_head('mixamorig:RightLeg')),
    'ankle_L': r(bone_head('mixamorig:LeftFoot')), 'ankle_R': r(bone_head('mixamorig:RightFoot')),
    'wrist_L': r(bone_head('mixamorig:LeftHand')), 'wrist_R': r(bone_head('mixamorig:RightHand')),
    'index_tip_L': r(lt['Index']), 'index_tip_R': r(rt['Index']),
    'fingertips_L': {k: r(v) for k, v in lt.items()}, 'fingertips_R': {k: r(v) for k, v in rt.items()},
    'keyboard_home_row_center': r((home.x, home.y, key_top)),
    'keyboard_note': 'x,y = mean of 8 non-thumb fingertips over the Typing cycle; z = key-top height '
                     '(10th percentile of fingertip z minus 7 mm pad)',
    'elbow_L_joint': r(el),
    'elbow_crease_L': {'position': r(hit), 'normal': r(nrm.normalized())},
    'shoulder_L': r(sh),
    'head': r(head), 'head_top': r(head_top), 'neck': r(bone_head('mixamorig:Neck')),
    'face_forward': r(face_fwd.normalized()),
    'lens_center_L': r(lens['Lens_L']), 'lens_center_R': r(lens['Lens_R']),
    'eye_center_L': r(eyes['L']), 'eye_center_R': r(eyes['R']),
    'eye_height': round((eyes['L'].z + eyes['R'].z) / 2, 4),
    'seat_contact_height': round(float(scene.get('seat_z', 0.0)), 4),
    'actions': {a.name: [int(round(a.frame_range[0])), int(round(a.frame_range[1]))]
                for a in bpy.data.actions if a.users or a.use_fake_user},
    'cyclic_actions': [a.name for a in bpy.data.actions if a.use_cyclic],
    'controls': {'skin_dryness': 'bpy.data.materials["HumanSkin"]["dryness"] (0..1)',
                 'shape_keys': 'Body key_blocks "Sunken", "MouthOpen" (assets follow by drivers)'},
}
with open(REPORT, 'w') as fh:
    json.dump(report, fh, indent=1)
print(json.dumps(report, indent=1))
if VIEWS == ['none']:
    raise SystemExit

# ---------------------------------------------------------------- test set: proxies, lights, cameras
def box(name, center, size, color):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    ob.location, ob.scale = center, size
    scene.collection.objects.link(ob)
    m = bpy.data.materials.new(name)
    m.diffuse_color = color
    m.use_nodes = True
    p = m.node_tree.nodes['Principled BSDF']
    p.inputs['Base Color'].default_value = color
    p.inputs['Roughness'].default_value = 0.6
    me.materials.append(m)
    return ob


sz = scene.get('seat_z', 0.49)
box('floor', (0, 0.5, -0.01), (6, 6, 0.02), (0.05, 0.045, 0.04, 1))
box('seat', (0, 0, sz - 0.04), (0.48, 0.48, 0.08), (0.03, 0.03, 0.03, 1))
box('backrest', (0, -0.26, sz + 0.32), (0.46, 0.05, 0.6), (0.03, 0.03, 0.03, 1))
desk_top = key_top - 0.03
box('desk', (0, 0.35 + 0.4, desk_top - 0.015), (2.4, 0.8, 0.03), (0.09, 0.06, 0.04, 1))
box('keyboard', (home.x, home.y, (desk_top + key_top) / 2), (0.44, 0.14, key_top - desk_top), (0.02, 0.02, 0.022, 1))

world = bpy.data.worlds.new('test') if not scene.world else scene.world
scene.world = world
world.use_nodes = True
bg = world.node_tree.nodes['Background']
bg.inputs['Color'].default_value = (0.012, 0.016, 0.024, 1)
bg.inputs['Strength'].default_value = 1.0


def light(name, kind, pos, target, color, energy, size=0.3):
    ld = bpy.data.lights.new(name, kind)
    ld.color, ld.energy = color, energy
    if kind == 'AREA':
        ld.size = size
    ob = bpy.data.objects.new(name, ld)
    ob.location = pos
    ob.rotation_euler = (Vector(target) - Vector(pos)).to_track_quat('-Z', 'Y').to_euler()
    scene.collection.objects.link(ob)
    return ob


cam_d = bpy.data.cameras.new('testcam')
cam = bpy.data.objects.new('testcam', cam_d)
scene.collection.objects.link(cam)
scene.camera = cam

eyes_mid = (lens['Lens_L'] + lens['Lens_R']) / 2
lights = []


def set_lights(specs):
    for ob in lights:
        bpy.data.objects.remove(ob, do_unlink=True)
    lights.clear()
    for s in specs:
        lights.append(light(*s))


def aim(pos, target, lens_mm):
    cam.location = pos
    cam.rotation_euler = (Vector(target) - Vector(pos)).to_track_quat('-Z', 'Y').to_euler()
    cam_d.lens = lens_mm
    cam_d.clip_start = 0.02


ORANGE, COOL, SCREEN = (1.0, 0.52, 0.22), (0.55, 0.72, 1.0), (0.75, 0.85, 1.0)
face_lights = [
    ('key', 'AREA', eyes_mid + Vector((0.45, 0.5, 0.15)), eyes_mid, ORANGE, 14, 0.25),
    ('rim', 'AREA', eyes_mid + Vector((-0.45, -0.55, 0.25)), eyes_mid, COOL, 40, 0.3),
    ('fill', 'AREA', eyes_mid + Vector((-0.3, 0.6, -0.4)), eyes_mid, SCREEN, 3.0, 0.3),
]
body_lights = [
    ('key', 'AREA', Vector((1.2, 1.3, 1.6)), Vector((0, 0.2, 0.9)), ORANGE, 120, 0.6),
    ('rim', 'AREA', Vector((-1.0, -1.2, 1.9)), Vector((0, 0.1, 1.0)), COOL, 160, 0.6),
    ('fill', 'AREA', Vector((0, 1.3, 1.1)), Vector((0, 0.2, 0.9)), SCREEN, 25, 1.0),
]

sc = scene.cycles
scene.render.engine = 'CYCLES'
try:
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL'
    prefs.get_devices()
    for d in prefs.devices:
        d.use = True
    sc.device = 'GPU'
except Exception as e:
    print('GPU setup failed', e)
sc.samples = 32
sc.use_denoising = True
scene.render.resolution_x, scene.render.resolution_y, scene.render.resolution_percentage = 960, 540, 100
scene.render.image_settings.file_format = 'PNG'

skin = bpy.data.materials['HumanSkin']


def render(name):
    scene.render.filepath = os.path.join(RDIR, f'human_test_{name}.png')
    bpy.ops.render.render(write_still=True)


fwd = Vector((0, 1, 0))
for view in VIEWS:
    skin['dryness'] = 0.0 if view == 'face_alive' else 1.0
    kb = body.data.shape_keys.key_blocks
    kb['Sunken'].value = kb['MouthOpen'].value = 0.0 if view == 'face_alive' else 1.0
    if view in ('face', 'face_alive'):
        set_lights(face_lights)
        aim(eyes_mid + Vector((0.05, 0.62, -0.03)), eyes_mid + Vector((0, 0, -0.04)), 70)
    elif view == 'eyes':                       # glasses hidden, to check lids and eyeballs
        set_lights(face_lights)
        aim(eyes_mid + Vector((0.03, 0.40, -0.02)), eyes_mid + Vector((0, 0, -0.005)), 85)
    elif view == 'mouth':                      # teeth, tongue, retracted lips
        set_lights(face_lights)
        aim(eyes_mid + Vector((0.02, 0.36, -0.07)), eyes_mid + Vector((0, 0, -0.09)), 85)
    elif view == 'head':
        set_lights(face_lights)
        aim(eyes_mid + Vector((-0.45, -0.35, 0.2)), eyes_mid + Vector((0, -0.08, 0.02)), 60)
    elif view == 'full':
        set_lights(body_lights)
        aim(Vector((1.7, 1.6, 0.95)), Vector((0, 0.1, 0.70)), 32)
    elif view == 'hands':
        set_lights(body_lights)
        aim(Vector((0.34, -0.30, 1.48)), Vector((home.x, home.y, key_top)), 45)
    for nm in ('Glasses', 'Lens_L', 'Lens_R'):
        bpy.data.objects[nm].hide_render = view == 'eyes'
    scene.frame_set(MID)
    render(view)
