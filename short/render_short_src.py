"""Render the Short's shots straight from the scene in 9:16, instead of cropping them out of the 16:9 clip: the
camera keeps its move, lens and focus, and its sensor is cut down to the crop edit.py describes and shifted onto
it, so a frame here is that crop of the clip frame, only rendered at full resolution.
Frames go to OUTDIR/<piece id>/f_###.png (k-th frame of the piece); frames already on disk are skipped, so it is
safe to stop and restart. EEVEE pieces are rendered first, then the Cycles ones (the outro, from frame 4515).
Run: Blender -b blend/claudaine.blend --python short/render_short_src.py -- OUTDIR [IDS, e.g. ABK]
env: PCT (100), EEVEE_SAMPLES (24), CYCLES_SAMPLES (64), SEL=ends (only the first, middle and last frame of each
piece) or SEL=N (every N-th frame and the last): a quick look, TEX8=0 keeps the float textures"""
import bpy, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path += [HERE, os.path.join(os.path.dirname(HERE), 'scripts')]
import cycles_setup, tex8
from edit import FPS, OW, OH, PIECES, crop_centre

CYCLES_FROM = 4515                     # first Cycles frame of the clip (render_all.sh)
SX = 36.0                              # the clip camera's sensor (fit AUTO on a 16:9 frame: 36 mm wide)
SY = SX * 9 / 16


def frame(p, k):
    return 1 + round(p['src'] * FPS) + k


def aim(cam, p, k):
    """Point camera data cam at the crop of piece p's k-th frame: a vertical sensor as tall as the crop and
    shifted onto its centre. Shift is in units of the larger render side, here the height = the sensor height."""
    x, y, w, h = crop_centre(p, k)
    cam.sensor_fit = 'VERTICAL'
    cam.sensor_height = SY * h
    cam.shift_x = (x - 0.5) * SX / (SY * h)
    cam.shift_y = (0.5 - y) / h


def frames_of(p):
    n, sel = p['n'], os.environ.get('SEL', '1')
    return sorted({0, n // 2, n - 1}) if sel == 'ends' else sorted(set(range(0, n, int(sel))) | {n - 1})


if __name__ == '__main__':
    argv = sys.argv[sys.argv.index('--') + 1:]
    out = os.path.abspath(argv[0])
    ids = argv[1] if len(argv) > 1 else ''.join(p['id'] for p in PIECES)
    scene = bpy.context.scene
    cam = scene.camera.data
    if os.environ.get('TEX8', '1') == '1':
        tex8.use_8bit()
    r = scene.render
    r.resolution_x, r.resolution_y = OW, OH
    r.resolution_percentage = int(os.environ.get('PCT', '100'))
    img = r.image_settings
    img.file_format, img.color_mode, img.color_depth, img.compression = 'PNG', 'RGB', '8', 15
    scene.eevee.taa_render_samples = int(os.environ.get('EEVEE_SAMPLES', '24'))
    todo = [p for p in PIECES if p['id'] in ids]
    todo.sort(key=lambda p: frame(p, p['n'] - 1) >= CYCLES_FROM)          # EEVEE first: Cycles is one-way
    os.makedirs(out, exist_ok=True)
    log = open(os.path.join(out, 'render.log'), 'a')
    for p in todo:
        if frame(p, 0) < CYCLES_FROM <= frame(p, p['n'] - 1):
            sys.exit(f"piece {p['id']} straddles the EEVEE/Cycles switch")
        if frame(p, 0) >= CYCLES_FROM and r.engine != 'CYCLES':
            cycles_setup.use_cycles(scene, samples=int(os.environ.get('CYCLES_SAMPLES', '64')))
        os.makedirs(os.path.join(out, p['id']), exist_ok=True)
        for k in frames_of(p):
            path = os.path.join(out, p['id'], f'f_{k:03d}.png')
            if os.path.exists(path):
                continue
            scene.frame_set(frame(p, k))
            aim(cam, p, k)
            r.filepath = path
            t0 = time.time()
            bpy.ops.render.render(write_still=True)
            print(f"{p['id']} {k} {frame(p, k)} {r.engine} {time.time() - t0:.1f}", file=log, flush=True)
    print('FINISHED', file=log, flush=True)
