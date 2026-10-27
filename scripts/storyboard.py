"""Render key moments of claudaine.blend at low quality to check framing.
Run: Blender -b blend/claudaine.blend --python scripts/storyboard.py -- [t1,t2,...]"""
import bpy, sys, os, time

CLIP = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
TIMES = [2.0, 8.0, 11.0, 12.6, 15.0, 18.5, 20.45, 23.0, 25.0, 28.6, 31.5, 37.0, 43.0, 48.0, 52.0, 54.3,
         58.0, 64.0, 74.0, 92.0, 98.0, 107.5, 112.0, 141.0, 151.5, 158.0, 163.0, 170.0, 174.0, 179.0,
         185.0, 193.0, 201.0, 210.0]
argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
if argv and argv[0]:
    TIMES = [float(x) for x in argv[0].split(',')]
pct = int(os.environ.get('PCT', '50'))
scene = bpy.context.scene
scene.render.resolution_percentage = pct
scene.eevee.taa_render_samples = int(os.environ.get('SAMPLES', '16'))
out = os.path.join(CLIP, 'renders', 'sb')
os.makedirs(out, exist_ok=True)
for t in TIMES:
    f = 1 + int(round(t * scene.render.fps))
    scene.frame_set(f)
    scene.render.filepath = os.path.join(out, f'sb_{t:07.2f}.png')
    t0 = time.time()
    bpy.ops.render.render(write_still=True)
    print('RENDERED', t, f, round(time.time() - t0, 1), 's', flush=True)
