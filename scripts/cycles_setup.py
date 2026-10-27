"""Switch the open claudaine.blend to Cycles on the Metal GPU for the outro (188.1 s - end).
Imported by the render scripts; run directly to time test frames:
Blender -b blend/claudaine.blend --python scripts/cycles_setup.py -- t1,t2,..."""
import bpy, os, sys, time

CLIP = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))


def use_cycles(scene, samples=96):
    prefs = bpy.context.preferences.addons['cycles'].preferences
    prefs.compute_device_type = 'METAL'
    prefs.get_devices()
    for d in prefs.devices:
        d.use = d.type != 'CPU'          # GPU alone is as fast here, and leaves the CPU to everyone else
    scene.render.engine = 'CYCLES'
    cy = scene.cycles
    cy.device = 'GPU'
    cy.samples = samples
    cy.use_adaptive_sampling = True
    cy.adaptive_threshold = 0.02
    cy.use_denoising = True
    cy.denoiser = 'OPENIMAGEDENOISE'
    cy.max_bounces = 6
    cy.glossy_bounces = 3
    cy.transmission_bounces = 6
    cy.volume_bounces = 0
    cy.caustics_reflective = cy.caustics_refractive = False
    cy.blur_glossy = 1.0
    scene.render.use_persistent_data = True
    hair, proxy = bpy.data.objects.get('HairCurves'), bpy.data.objects.get('HairShadowProxy')
    if hair and proxy:                   # the full hair shadows itself here; EEVEE's sparse stand-in goes
        hair.visible_shadow = True
        proxy.hide_render = True
    return [d.name for d in prefs.devices if d.use]


if __name__ == '__main__':
    scene = bpy.context.scene
    print('DEVICES', use_cycles(scene, samples=int(os.environ.get('SAMPLES', '96'))))
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else []
    times = [float(x) for x in argv[0].split(',')] if argv else [201.0, 210.0]
    scene.render.resolution_percentage = int(os.environ.get('PCT', '50'))
    out = os.path.join(CLIP, 'renders', 'sb')
    os.makedirs(out, exist_ok=True)
    for t in times:
        scene.frame_set(1 + int(round(t * 24)))
        scene.render.filepath = os.path.join(out, f'cy_{t:07.2f}.png')
        t0 = time.time()
        bpy.ops.render.render(write_still=True)
        print('RENDERED', t, round(time.time() - t0, 1), 's', flush=True)
