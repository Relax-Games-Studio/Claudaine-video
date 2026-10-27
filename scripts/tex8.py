"""8-bit stand-ins for the float textures. The Poly Haven maps come as EXR and 16-bit PNG, which Blender holds as
float32 RGBA (12.5 GB for ~230 2K maps, then again on the GPU): one render process grew to ~22 GB. For renders the
8-bit copies in assets/tex8 look the same at a quarter of the memory.
Make them once: Blender -b blend/claudaine.blend --python scripts/tex8.py
render_range.py calls use_8bit() to point the scene's images at them (images without a copy stay as they are)."""
import bpy, hashlib, os
import numpy as np

TEX8 = os.path.join(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')), 'assets', 'tex8')
KEEP = ('_disp', '.hdr')                  # height for displacement and the sky keep their precision


def targets():
    for im in bpy.data.images:
        if im.type != 'IMAGE' or im.source != 'FILE' or not im.is_float or im.users == 0:
            continue
        if im.colorspace_settings.name not in ('Non-Color', 'sRGB') or any(k in im.filepath for k in KEEP):
            continue
        key = im.packed_file and im.name or bpy.path.abspath(im.filepath)
        yield im, os.path.join(TEX8, f'{bpy.path.clean_name(im.name)}_{hashlib.md5(key.encode()).hexdigest()[:8]}.png')


def to_srgb(x):
    return np.where(x <= 0.0031308, 12.92 * x, 1.055 * np.power(np.maximum(x, 0.0031308), 1 / 2.4) - 0.055)


def convert():
    os.makedirs(TEX8, exist_ok=True)
    n = 0
    for im, path in targets():
        if os.path.exists(path):
            continue
        w, h = im.size
        px = np.empty(w * h * 4, np.float32)
        im.pixels.foreach_get(px)       # float buffers: premultiplied, raw data for Non-Color, scene linear for sRGB
        px = px.reshape(-1, 4)
        a = px[:, 3]
        cut = (a > 0) & (a < 1)
        if cut.any():                   # PNG wants straight alpha
            px[cut, :3] /= a[cut, None]
            print('TEX8 alpha', im.name, f'{cut.mean():.3f}', flush=True)
        if im.colorspace_settings.name == 'sRGB':
            px[:, :3] = to_srgb(px[:, :3])
        px = px.ravel()
        out = bpy.data.images.new('tex8_tmp', w, h, alpha=True, float_buffer=False)
        out.colorspace_settings.name = 'Non-Color'          # byte pixels go in and out untouched
        out.pixels.foreach_set(np.clip(px, 0.0, 1.0))
        out.filepath_raw, out.file_format = path, 'PNG'
        out.save()
        bpy.data.images.remove(out)
        im.buffers_free()
        n += 1
        print('TEX8', n, im.name, '->', os.path.basename(path), flush=True)
    print('TEX8 done', n, 'new', flush=True)


def use_8bit():
    n = 0
    for im, path in list(targets()):
        if os.path.exists(path):
            cs = im.colorspace_settings.name
            if im.packed_file:
                im.unpack(method='REMOVE')  # drop the packed float copy, read the 8-bit file instead
            im.filepath = path
            im.colorspace_settings.name = cs
            im.reload()
            n += 1
    print('TEX8 remapped', n, flush=True)
    return n


if __name__ == '__main__':
    convert()
