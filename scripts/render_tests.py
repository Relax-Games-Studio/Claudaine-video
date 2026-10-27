"""Render every TC_* test camera of the open .blend at reduced quality.
Run: Blender -b blend/env.blend --python scripts/render_tests.py -- [prefix] [cam names...]"""
import bpy, sys, os

argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
prefix = argv[0] if argv else 'env'
only = set(argv[1:])
scene = bpy.context.scene
out = os.path.join(os.path.dirname(bpy.data.filepath), '..', 'renders')
os.makedirs(out, exist_ok=True)
scene.render.resolution_percentage = 50
scene.eevee.taa_render_samples = 24
scene.render.image_settings.file_format = 'PNG'
for cam in sorted((o for o in scene.objects if o.type == 'CAMERA' and o.name.startswith('TC_')), key=lambda o: o.name):
    if only and cam.name not in only:
        continue
    scene.camera = cam
    scene.render.filepath = os.path.join(out, f'{prefix}_{cam.name}.png')
    bpy.ops.render.render(write_still=True)
    print('RENDERED', scene.render.filepath, flush=True)
