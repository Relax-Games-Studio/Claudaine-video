"""Open env.blend, drop in the workstation with stand-in screen lights, render desk test cameras.
Run: Blender -b blend/env.blend --python scripts/test_desk.py -- [full]"""
import bpy, sys, os, math, time
from mathutils import Vector
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from lib_build import *
import desk

scene = bpy.context.scene
C_DESK = coll('DESK')
C_DL = coll('DESK_LIGHTS')
root = bpy.data.objects.new('DESK_ROOT', None)
C_DESK.objects.link(root)
root.location = (-3.0, 2.4, -2.1)
root.rotation_euler = (0, 0, math.pi)
res = desk.build_all(root, C_DESK, C_DL)
bpy.context.view_layer.update()
import screens_rig
screens_rig.hook(res['screens'], C_DL)
screens_rig.bounce(C_DL, root.matrix_world @ Vector((0, -0.4, 2.3)), (0, 0, 0))
if os.environ.get('HAZE'):
    # dusty basement air: a bounded volume so the screens get a halo and the dark reads as space
    hz = box('BasementHaze', (11.8, 8.8, 2.38), (0, 4.5, -2.1), C_DESK, None, bottom=True)
    m, nt = new_mat('BasementHazeVol')
    out = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'][0]
    for n in list(nt.nodes):
        if n.type == 'BSDF_PRINCIPLED':
            nt.nodes.remove(n)
    v = nt.nodes.new('ShaderNodeVolumePrincipled')
    v.inputs['Density'].default_value = float(os.environ['HAZE'])
    v.inputs['Anisotropy'].default_value = 0.5
    nt.links.new(v.outputs[0], out.inputs['Volume'])
    hz.data.materials.clear()
    hz.data.materials.append(m)
for o in bpy.data.objects:
    if o.type == 'LIGHT' and o.name.startswith(('StreetLamp', 'PorchLamp', 'Moon', 'Hall_')):
        o.hide_render = True
scene.frame_set(int(os.environ.get('TEST_FRAME', '1801')))
for o in bpy.data.objects:
    if o.name.endswith('_Glow'):
        o.hide_render = True
# inside the basement nothing of the street is visible: drop it from the render
for cname in ('STREET',):
    bpy.data.collections[cname].hide_render = True
for o in bpy.data.collections['EXTERIOR'].objects:
    if o.name.startswith(('Neighbor_', 'pine', 'tree_small', 'StreetHaze')):
        o.hide_render = True
    for ch in o.children_recursive:
        if o.name.startswith(('pine', 'tree_small')):
            ch.hide_render = True

C_CAM = bpy.data.collections['TESTCAMS']
def cam(name, loc, target, lens=24):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.clip_start = 0.01
    ob = bpy.data.objects.new(name, cd)
    C_CAM.objects.link(ob)
    ob.location = loc
    look_at(ob, target, 'Y')
    return ob
W = lambda p: root.matrix_world @ Vector(p)
cam('TC_D_behind', W((0.3, -1.7, 1.05)), W((0, 0.6, 1.0)), 22)
cam('TC_D_floor', W((0.5, -1.0, 0.12)), W((0.1, -0.2, 0.0)), 24)
cam('TC_D_side', W((-1.5, 0.0, 1.3)), W((0.0, 0.7, 0.9)), 24)
cam('TC_D_front', W((0.0, 0.45, 1.25)), W((0.0, -0.6, 0.8)), 20)
cam('TC_D_stairs', (-3.6, 4.9, -0.9), W((0, 0.3, 0.9)), 24)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(CLIP, 'blend', 'desk_test.blend'), compress=True)

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
full = 'full' in argv
scene.render.resolution_percentage = 100 if full else 50
scene.eevee.taa_render_samples = 64 if full else 24
out = os.path.join(CLIP, 'renders')
for c in sorted((o for o in scene.objects if o.name.startswith('TC_D_')), key=lambda o: o.name):
    if full and c.name != 'TC_D_behind':
        continue
    if os.environ.get('CAMS') and c.name[5:] not in os.environ['CAMS'].split(','):
        continue
    scene.camera = c
    scene.render.filepath = os.path.join(out, f'desk{"_full" if full else ""}_{c.name}.png')
    t = time.time()
    bpy.ops.render.render(write_still=True)
    print('RENDERED', c.name, round(time.time() - t, 1), 's', flush=True)
