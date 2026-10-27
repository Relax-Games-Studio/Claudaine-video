"""Test renders for blend/monsters.blend (never saves): lineup, materialise strip, glitch frame.
Run: Blender -b blend/monsters.blend --python scripts/test_monsters.py -- [lineup] [reveal] [glitch]"""
import bpy, sys, os, math, time
from mathutils import Vector
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from lib_build import CLIP, ORANGE, coll, light, look_at, flat

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
todo = set(argv) or {'lineup', 'reveal', 'glitch'}   # + 'faces' on request
scene = bpy.context.scene
OUT = f'{CLIP}/renders'
NAMES = ['mutant', 'warrok', 'parasite', 'maw', 'demon', 'skeleton']

# ---- room + lights
C = coll('TEST_ROOM')
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, 0, 0))
floor = bpy.context.active_object
floor.data.materials.append(flat('TestFloor', (0.05, 0.05, 0.05), rough=0.6))
bpy.ops.mesh.primitive_plane_add(size=30, location=(0, -3.5, 5), rotation=(math.pi / 2, 0, 0))
wall = bpy.context.active_object
wall.data.materials.append(flat('TestWall', (0.04, 0.04, 0.045), rough=0.85))
world = bpy.data.worlds.new('TestWorld')
world.use_nodes = True
world.node_tree.nodes['Background'].inputs['Color'].default_value = (0.002, 0.002, 0.003, 1)
scene.world = world
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
scene.render.resolution_percentage = 100
scene.eevee.taa_render_samples = 32
scene.eevee.use_raytracing = True
scene.view_settings.view_transform = 'AgX'
try:
    scene.view_settings.look = 'AgX - Medium High Contrast'
except Exception:
    pass
scene.view_settings.exposure = 0.8
cam_d = bpy.data.cameras.new('TestCam')
cam = bpy.data.objects.new('TestCam', cam_d)
C.objects.link(cam)
scene.camera = cam


def set_lights(center, front=Vector((0, 1, 0))):
    for o in list(C.objects):
        if o.type == 'LIGHT':
            bpy.data.objects.remove(o)
    k = light('Key_Screens', 'AREA', center + front * 2.0 + Vector((0.6, 0, -0.3)) + Vector((0, 0, 1.0)), 260, ORANGE, C,
              size=(1.4, 0.8))
    look_at(k, center + Vector((0, 0, 1.2)))
    r = light('Rim_Blue', 'AREA', center - front * 2.0 + Vector((-1.2, 0, 2.6)), 160, (0.45, 0.6, 1.0), C, size=(1.0, 1.0))
    look_at(r, center + Vector((0, 0, 1.4)))


rigs = {n: bpy.data.objects[f'{n}_Rig'] for n in NAMES}
bodies = {n: bpy.data.objects[f'{n}_Body'] for n in NAMES}
mod = lambda n: bodies[n].modifiers['MonsterGlitch']
ng = bpy.data.node_groups['MonsterGlitch']
SID = {it.name: it.identifier for it in ng.interface.items_tree if it.item_type == 'SOCKET' and it.in_out == 'INPUT'}


def setm(n, **kw):
    # Blender 5.2: modifier inputs live at md.properties.inputs.<Socket_N>.value (no md["Socket_N"])
    for k, v in kw.items():
        getattr(mod(n).properties.inputs, SID[k]).value = v
    bodies[n].update_tag()


def keym(n, k, frame, v):
    setm(n, **{k: v})
    bodies[n].keyframe_insert(f'modifiers["MonsterGlitch"].properties.inputs.{SID[k]}.value', frame=frame)


def render(path):
    scene.render.filepath = path
    t = time.time()
    bpy.ops.render.render(write_still=True)
    dt = time.time() - t
    print('RENDERED', os.path.basename(path), round(dt, 2), 's', flush=True)
    return dt


scene.frame_set(40)
if 'lineup' in todo:
    for i, n in enumerate(NAMES):
        rigs[n].location = ((i - 2.5) * 1.75, 0, 0)
        setm(n, Reveal=1.0, Glitch=0.0)
    set_lights(Vector((0, 0, 0)))
    for o in C.objects:
        if o.type == 'LIGHT':
            o.data.size *= 4
            o.data.size_y *= 2
            o.data.energy *= 5
            o.location = Vector((o.location.x * 2, o.location.y * 2.2, o.location.z))
            look_at(o, Vector((0, 0, 1.2)))
    cam.location = (0, 10.5, 1.35)
    cam_d.lens = 32
    look_at(cam, Vector((0, 0, 1.15)))
    render(f'{OUT}/monster_test_lineup.png')

# materialise strip on one creature, Source = a 'monitor' in front-right of it
HERO = os.environ.get('HERO', 'warrok')
for i, n in enumerate(NAMES):
    rigs[n].location = (0, 0, 0) if n == HERO else (100 + i * 5, 0, 0)
src = Vector((1.1, 1.2, 1.15))
bpy.ops.mesh.primitive_plane_add(size=1, location=src)
mon = bpy.context.active_object
mon.scale = (0.6, 0.34, 1)
look_at(mon, Vector((-1.2, 3.0, 1.15)))       # face the test camera so the 'screen' reads
from lib_build import emission_mat
mon.data.materials.append(emission_mat('TestMonitor', ORANGE, 3.0))
set_lights(Vector((0, 0, 0)))
cam.location = (-2.6, 4.3, 1.5)
cam_d.lens = 30
look_at(cam, Vector((0.25, 0.3, 1.15)))
times = []
if 'reveal' in todo:
    # driven through keyframes (Reveal 0 at f100 -> 1 at f200, linear) to prove the animated path works
    setm(HERO, Glitch=0.0, Source=tuple(src))
    keym(HERO, 'Reveal', 100, 0.0)
    keym(HERO, 'Reveal', 200, 1.0)
    for fc in bodies[HERO].animation_data.action.layers[0].strips[0].channelbags[0].fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'LINEAR'
    for r in (0.0, 0.25, 0.5, 0.75, 1.0):
        scene.frame_set(100 + int(r * 100))
        times.append(render(f'{OUT}/monster_test_reveal_{int(r * 100):03d}.png'))
    bodies[HERO].animation_data_clear()
if 'glitch' in todo:
    setm(HERO, Reveal=1.0, Glitch=0.7, Source=tuple(src))
    for f in (40, 41):
        scene.frame_set(f)
        render(f'{OUT}/monster_test_glitch70_f{f}.png')
if 'faces' in todo:
    # head close-ups of every creature, Reveal=1 (material / eye check)
    scene.render.resolution_x, scene.render.resolution_y = 640, 360
    for n in NAMES:
        for m in NAMES:
            rigs[m].location = (0, 0, 0) if m == n else (100, 0, 0)
        setm(n, Reveal=1.0, Glitch=0.0)
        scene.frame_set(40)
        head = rigs[n].matrix_world @ rigs[n].pose.bones['mixamorig:Head'].head
        set_lights(Vector((head.x, head.y, 0)))
        cam.location = head + Vector((0.35, 1.5, 0.05))
        cam_d.lens = 50
        look_at(cam, head + Vector((0, 0, 0.05)))
        render(f'{OUT}/monster_test_face_{n}.png')
print('TIMES', times)
