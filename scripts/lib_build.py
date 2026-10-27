"""Shared helpers for building the CLAUDAINE scenes in Blender (meshes, UVs, materials, Poly Haven appends)."""
import bpy, bmesh, math, os, glob, random
from mathutils import Vector, Matrix, Euler

CLIP = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
PH = f'{CLIP}/assets/polyhaven'
ORANGE = (0.851, 0.467, 0.341)  # #D97757 in sRGB
R = random.Random(7)


def srgb(c):
    """sRGB 0..1 tuple -> linear (Blender colour inputs are linear)."""
    f = lambda x: x / 12.92 if x <= 0.04045 else ((x + 0.055) / 1.055) ** 2.4
    return tuple(f(x) for x in c[:3]) + ((c[3],) if len(c) > 3 else (1.0,))


ORANGE_LIN = srgb(ORANGE)


# ---------------------------------------------------------------- collections

def coll(name, parent=None):
    c = bpy.data.collections.get(name)
    if c is None:
        c = bpy.data.collections.new(name)
        (parent or bpy.context.scene.collection).children.link(c)
    return c


# ---------------------------------------------------------------- meshes

def cube_uv(me, swap=False):
    """World-scale box UVs: vertical faces get (horizontal, z), horizontal faces (x, y)."""
    if not me.uv_layers:
        me.uv_layers.new(name='UVMap')
    uv = me.uv_layers.active.data
    for p in me.polygons:
        n = p.normal
        for li in p.loop_indices:
            co = me.vertices[me.loops[li].vertex_index].co
            if abs(n.z) >= max(abs(n.x), abs(n.y)):
                u, v = co.x, co.y
            elif abs(n.x) >= abs(n.y):
                u, v = co.y, co.z
            else:
                u, v = co.x, co.z
            uv[li].uv = (v, u) if swap else (u, v)


def obj_from_bm(name, bm, col, mats=(), loc=(0, 0, 0), rot=(0, 0, 0), uv=True, smooth=False):
    me = bpy.data.meshes.new(name)
    bm.to_mesh(me)
    bm.free()
    if uv:
        cube_uv(me)
    for m in mats:
        me.materials.append(m)
    if smooth:
        me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = rot
    return ob


def box(name, size, loc=(0, 0, 0), col=None, mat=None, rot=(0, 0, 0), bevel=0.0, bottom=False):
    """Axis-aligned box of `size` centred at `loc` (or standing on it when bottom=True)."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=size, verts=bm.verts)
    if bottom:
        bmesh.ops.translate(bm, vec=(0, 0, size[2] / 2), verts=bm.verts)
    ob = obj_from_bm(name, bm, col, [mat] if mat else [], loc, rot)
    if bevel:
        bev(ob, bevel)
    return ob


def bev(ob, width, segments=2):
    m = ob.modifiers.new('Bevel', 'BEVEL')
    m.width = width
    m.segments = segments
    m.limit_method = 'ANGLE'
    m.harden_normals = False
    return m


def cyl(name, r, h, loc=(0, 0, 0), col=None, mat=None, rot=(0, 0, 0), seg=24, r2=None, bottom=True, cap=True):
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=cap, segments=seg, radius1=r, radius2=r if r2 is None else r2, depth=h)
    if bottom:
        bmesh.ops.translate(bm, vec=(0, 0, h / 2), verts=bm.verts)
    ob = obj_from_bm(name, bm, col, [mat] if mat else [], loc, rot, smooth=True)
    return ob


def wall(name, x0, x1, z0, z1, thick, holes=(), col=None, mat=None, mat_in=None, axis='X', at=0.0, face=-1):
    """Straight wall from x0..x1 (along `axis`) at offset `at`, z0..z1, with rectangular holes
    [(h0, h1, zb, zt), ...]. Built from solid pieces so no booleans are needed.
    `face` = -1 means the exterior side is toward negative of the other axis."""
    bm = bmesh.new()
    holes = sorted(holes)
    def piece(a0, a1, b0, b1):
        if a1 - a0 < 1e-4 or b1 - b0 < 1e-4:
            return
        g = bmesh.ops.create_cube(bm, size=1.0)
        vs = g['verts']
        bmesh.ops.scale(bm, vec=(a1 - a0, thick, b1 - b0), verts=vs)
        bmesh.ops.translate(bm, vec=((a0 + a1) / 2, 0, (b0 + b1) / 2), verts=vs)
    # vertical strips between holes, full height, plus pieces above/below each hole
    cur = x0
    for h0, h1, zb, zt in holes:
        piece(cur, h0, z0, z1)
        piece(h0, h1, z0, zb)
        piece(h0, h1, zt, z1)
        cur = h1
    piece(cur, x1, z0, z1)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-5)
    if axis == 'X':
        bmesh.ops.translate(bm, vec=(0, at, 0), verts=bm.verts)
    else:  # wall runs along Y: rotate so local X -> world Y
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'Z'), verts=bm.verts)
        bmesh.ops.translate(bm, vec=(at, 0, 0), verts=bm.verts)
    mats = [m for m in (mat, mat_in) if m]
    ob = obj_from_bm(name, bm, col, mats)
    if mat_in:  # interior faces (normal pointing away from exterior side) get the second material
        me = ob.data
        for p in me.polygons:
            n = p.normal
            comp = n.y if axis == 'X' else n.x
            p.material_index = 1 if comp * face < -0.5 else 0
    return ob


# ---------------------------------------------------------------- materials

_img_cache = {}


def img(path, non_color=False):
    key = (path, non_color)
    if key not in _img_cache:
        im = bpy.data.images.load(path, check_existing=True)
        if non_color:
            im.colorspace_settings.name = 'Non-Color'
        _img_cache[key] = im
    return _img_cache[key]


def new_mat(name):
    m = bpy.data.materials.get(name)
    if m:
        return m, None
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        if n.type != 'OUTPUT_MATERIAL':
            nt.nodes.remove(n)
    return m, nt


def principled(nt):
    out = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'][0]
    b = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(b.outputs[0], out.inputs[0])
    return b, out


def pbr(name, tex, tile=2.0, tint=None, rot90=False, rough_mul=1.0, rough_add=0.0, normal=1.0, ao=0.6,
        sat=1.0, bright=1.0, coord='UV'):
    """Poly Haven texture set -> Principled. tile = metres covered by one texture repeat."""
    m, nt = new_mat(name)
    if nt is None:
        return m
    d = f'{PH}/textures/{tex}'
    b, out = principled(nt)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    mp = nt.nodes.new('ShaderNodeMapping')
    mp.inputs['Scale'].default_value = (1 / tile, 1 / tile, 1 / tile)
    if rot90:
        mp.inputs['Rotation'].default_value = (0, 0, math.pi / 2)
    nt.links.new(tc.outputs[coord], mp.inputs[0])
    def tx(kind, nc):
        f = glob.glob(f'{d}/{tex}_{kind}_2k.*')
        if not f:
            return None
        t = nt.nodes.new('ShaderNodeTexImage')
        t.image = img(f[0], nc)
        if coord != 'UV':
            t.projection = 'BOX'
            t.projection_blend = 0.2
        nt.links.new(mp.outputs[0], t.inputs[0])
        return t
    dif = tx('diff', False)
    col = dif.outputs[0]
    if sat != 1.0 or bright != 1.0:
        hsv = nt.nodes.new('ShaderNodeHueSaturation')
        hsv.inputs['Saturation'].default_value = sat
        hsv.inputs['Value'].default_value = bright
        nt.links.new(col, hsv.inputs['Color'])
        col = hsv.outputs[0]
    if tint:
        mix = nt.nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        nt.links.new(col, mix.inputs['A'])
        mix.inputs['B'].default_value = srgb(tint)
        col = mix.outputs['Result']
    a = tx('ao', True)
    if a and ao > 0:
        mix = nt.nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = ao
        nt.links.new(col, mix.inputs['A'])
        nt.links.new(a.outputs[0], mix.inputs['B'])
        col = mix.outputs['Result']
    nt.links.new(col, b.inputs['Base Color'])
    r = tx('rough', True)
    if r:
        mth = nt.nodes.new('ShaderNodeMath')
        mth.operation = 'MULTIPLY_ADD'
        mth.use_clamp = True
        mth.inputs[1].default_value = rough_mul
        mth.inputs[2].default_value = rough_add
        nt.links.new(r.outputs[0], mth.inputs[0])
        nt.links.new(mth.outputs[0], b.inputs['Roughness'])
    n = tx('nor_gl', True)
    if n:
        nm = nt.nodes.new('ShaderNodeNormalMap')
        nm.inputs['Strength'].default_value = normal
        nt.links.new(n.outputs[0], nm.inputs['Color'])
        nt.links.new(nm.outputs[0], b.inputs['Normal'])
    return m


def flat(name, color, rough=0.5, metal=0.0, emit=None, emit_strength=0.0, spec=0.5, alpha=1.0, transmission=0.0,
         coat=0.0):
    m, nt = new_mat(name)
    if nt is None:
        return m
    b, out = principled(nt)
    b.inputs['Base Color'].default_value = srgb(color)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    b.inputs['Specular IOR Level'].default_value = spec
    if coat:
        b.inputs['Coat Weight'].default_value = coat
    if transmission:
        b.inputs['Transmission Weight'].default_value = transmission
    if emit:
        b.inputs['Emission Color'].default_value = srgb(emit)
        b.inputs['Emission Strength'].default_value = emit_strength
    if alpha < 1.0:
        b.inputs['Alpha'].default_value = alpha
        m.surface_render_method = 'BLENDED'
    return m


def emission_mat(name, color, strength):
    m, nt = new_mat(name)
    if nt is None:
        return m
    out = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'][0]
    e = nt.nodes.new('ShaderNodeEmission')
    e.inputs['Color'].default_value = srgb(color)
    e.inputs['Strength'].default_value = strength
    nt.links.new(e.outputs[0], out.inputs[0])
    return m


def grunge(m, amount=0.35, scale=3.0, dark=0.55):
    """Multiply a procedural dirt layer into an existing Principled base colour."""
    nt = m.node_tree
    b = [n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'][0]
    src = b.inputs['Base Color'].links[0].from_socket if b.inputs['Base Color'].is_linked else None
    base = b.inputs['Base Color'].default_value[:]
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = scale
    nz.inputs['Detail'].default_value = 8
    nz.inputs['Roughness'].default_value = 0.65
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].position = 0.45
    ramp.color_ramp.elements[0].color = (dark, dark * 0.95, dark * 0.85, 1)
    ramp.color_ramp.elements[1].position = 0.7
    nt.links.new(nz.outputs['Fac'], ramp.inputs['Fac'])
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    mix.blend_type = 'MULTIPLY'
    mix.inputs['Factor'].default_value = amount
    if src:
        nt.links.new(src, mix.inputs['A'])
    else:
        mix.inputs['A'].default_value = base
    nt.links.new(ramp.outputs[0], mix.inputs['B'])
    nt.links.new(mix.outputs['Result'], b.inputs['Base Color'])
    return m


# ---------------------------------------------------------------- Poly Haven models

def ph_append(asset, col, names=None, pattern=None):
    """Append objects from a Poly Haven model .blend into `col`. Returns list of new objects."""
    path = glob.glob(f'{PH}/models/{asset}/*.blend')[0]
    with bpy.data.libraries.load(path, link=False) as (src, dst):
        want = list(src.objects)
        if names:
            want = [n for n in want if n in names]
        if pattern:
            import fnmatch
            want = [n for n in want if fnmatch.fnmatch(n, pattern)]
        dst.objects = want
    objs = [o for o in dst.objects if o]
    for o in objs:
        col.objects.link(o)
    # Poly Haven rigs/widgets are not needed
    for o in list(objs):
        if o.type == 'ARMATURE' or o.name.startswith('wdg_'):
            objs.remove(o)
            bpy.data.objects.remove(o)
    for o in objs:
        for m in list(o.modifiers):
            if m.type == 'ARMATURE':
                o.modifiers.remove(m)
    return objs


def ph_group(asset, col, names=None, pattern=None):
    """Append an asset and put its objects under one empty so it can be placed as a unit."""
    objs = ph_append(asset, col, names, pattern)
    root = bpy.data.objects.new(f'{asset}_root', None)
    col.objects.link(root)
    for o in objs:
        if o.parent is None or o.parent not in objs:
            o.parent = root
    return root, objs


def instance_group(root, objs, col, name, loc, rot_z=0.0, scale=1.0):
    """Linked-data copy of an appended group (shares meshes, cheap on memory)."""
    r2 = bpy.data.objects.new(name, None)
    col.objects.link(r2)
    mapping = {root: r2}
    for o in objs:
        c = o.copy()  # shares mesh data
        col.objects.link(c)
        mapping[o] = c
    for o in objs:
        c = mapping[o]
        c.parent = mapping.get(o.parent, r2)
        c.matrix_parent_inverse = o.matrix_parent_inverse.copy()
    r2.location = loc
    r2.rotation_euler = (0, 0, rot_z)
    r2.scale = (scale,) * 3
    return r2


def place(root, loc, rot_z=0.0, scale=1.0):
    root.location = loc
    root.rotation_euler = (0, 0, rot_z)
    root.scale = (scale,) * 3
    return root


def light(name, kind, loc, energy, color=(1, 1, 1), col=None, radius=0.1, rot=(0, 0, 0), size=None, spot=None):
    ld = bpy.data.lights.new(name, kind)
    ld.energy = energy
    ld.color = srgb(color)[:3]
    if kind in ('POINT', 'SPOT'):
        ld.shadow_soft_size = radius
    if kind == 'AREA' and size:
        ld.shape = 'RECTANGLE'
        ld.size, ld.size_y = size
    if kind == 'SPOT' and spot:
        ld.spot_size = spot
        ld.spot_blend = 0.6
    ob = bpy.data.objects.new(name, ld)
    col.objects.link(ob)
    ob.location = loc
    ob.rotation_euler = rot
    return ob


def look_at(ob, target, up='Y'):
    d = Vector(target) - ob.location
    ob.rotation_euler = d.to_track_quat('-Z', up).to_euler()
