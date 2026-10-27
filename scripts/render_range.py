"""Render a frame range of claudaine.blend to renders/frames<TAG>/f_####.png|jpg, skipping frames already on disk
(safe to stop and restart). Run: Blender -b blend/claudaine.blend --python scripts/render_range.py -- eevee|cycles F0 F1
env: SAMPLES, PCT, RES=WxH (e.g. 1280x720, 3840x2160), FMT=PNG|JPEG, TAG (suffix of the frames dir and the log),
TEX8=0 keeps the float textures (by default the 8-bit copies from tex8.py stand in)"""
import bpy, os, sys, time
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import cycles_setup, tex8

CLIP = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
engine, f0, f1 = sys.argv[sys.argv.index('--') + 1:][:3]
TAG = os.environ.get('TAG', '')
scene = bpy.context.scene
if os.environ.get('TEX8', '1') == '1':
    tex8.use_8bit()
if engine == 'cycles':
    cycles_setup.use_cycles(scene, samples=int(os.environ.get('SAMPLES', '64')))
else:
    scene.eevee.taa_render_samples = int(os.environ.get('SAMPLES', '32'))
    scene.eevee.shadow_pool_size = '1024'   # 4K needs ~2300 shadow pages; the default 512 MB holds 2048 (shadows drop out)
if os.environ.get('RES'):
    scene.render.resolution_x, scene.render.resolution_y = map(int, os.environ['RES'].split('x'))
scene.render.resolution_percentage = int(os.environ.get('PCT', '100'))
img = scene.render.image_settings
if os.environ.get('FMT', 'PNG') == 'JPEG':
    img.file_format, img.color_mode, img.quality = 'JPEG', 'RGB', 95
scene.frame_start, scene.frame_end = int(f0), int(f1)
scene.render.filepath = os.path.join(CLIP, 'renders', 'frames' + TAG, 'f_')
scene.render.use_overwrite = False
scene.render.use_placeholder = True
log = open(os.path.join(CLIP, 'renders', f'render_{engine}{TAG}.log'), 'a')
state = {'t': time.time()}


def done(sc, *_):
    now = time.time()
    log.write(f'{sc.frame_current} {now - state["t"]:.1f}\n')
    log.flush()
    state['t'] = now


bpy.app.handlers.render_post.append(done)
bpy.ops.render.render(animation=True)
log.write('FINISHED\n')
log.close()
