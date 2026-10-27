"""Stage 3: corpse face shape keys, materials, glasses. Produces the final human.blend.

Run: Blender -b <stage2.blend> --python scripts/build_human_look.py -- <human.blend>

- Body shape keys `Sunken` and `MouthOpen` are built from MakeHuman targets; every fitted asset
  (eyes, teeth, tongue, brows, lashes, hair, clothes) gets matching shape keys computed with the
  asset's MHCLO binding and driven by the body keys.
- Skin material `HumanSkin`: custom property `dryness` (0 = pale sick skin, 1 = mummy) drives the
  value node `dryness` in the node tree; keyframe the material property.
- Glasses: MakeHuman `kwnet_at_optical_glasses`, frame `Glasses`, lenses `Lens_L` / `Lens_R`,
  all parented to the `mixamorig:Head` bone.
"""
import bpy, bmesh, sys, os
from mathutils import Vector

from bl_ext.blender_org.mpfb.services import HumanService, AssetService, TargetService, LocationService
from bl_ext.blender_org.mpfb.entities.clothes.mhclo import Mhclo
from bl_ext.blender_org.mpfb.entities.objectproperties import GeneralObjectProperties

OUT = sys.argv[sys.argv.index('--') + 1]
DATA = LocationService.get_user_data()
TGT = LocationService.get_mpfb_data('targets')
EXPR = os.path.join(TGT, 'expression', 'units', 'caucasian')

scene = bpy.context.scene
rig = bpy.data.objects['HumanRig']
body = bpy.data.objects['Body']
rig.data.pose_position = 'REST'
bpy.context.view_layer.update()

# ---------------------------------------------------------------- shape keys on Body
SUNKEN = [
    ('cheek/l-cheek-volume-decr', 1.8), ('cheek/r-cheek-volume-decr', 1.8),
    ('cheek/l-cheek-inner-decr', 1.4), ('cheek/r-cheek-inner-decr', 1.4),
    ('cheek/l-cheek-bones-incr', 1.0), ('cheek/r-cheek-bones-incr', 1.0),
    ('forehead/forehead-temple-decr', 1.8),
    ('eyes/l-eye-push1-in', 1.2), ('eyes/r-eye-push1-in', 1.2),
    ('eyes/l-eye-push2-in', 1.2), ('eyes/r-eye-push2-in', 1.2),
    ('eyes/l-eye-bag-in', 1.5), ('eyes/r-eye-bag-in', 1.5),
    ('head/head-fat-decr', 1.0),
    ('chin/chin-bones-incr', 0.8),
    ('mouth/mouth-upperlip-volume-decr', 1.4), ('mouth/mouth-lowerlip-volume-decr', 1.4),
    ('nose/nose-volume-decr', 0.8), ('nose/nose-flaring-decr', 0.6), ('nose/nose-scale-horiz-decr', 0.3),
    ('neck/neck-scale-horiz-decr', 0.8),
    ('EXPR/eye-left-closure', 0.2), ('EXPR/eye-right-closure', 0.26),
]
MOUTH = [
    ('EXPR/mouth-open', 1.0),
    ('EXPR/mouth-retraction', 1.0),
    ('EXPR/mouth-upward-retraction', 0.6),
    ('EXPR/mouth-elevation', 0.5),
    ('EXPR/mouth-depression', 0.6),
    ('EXPR/mouth-depression-retraction', 0.4),
]


def tpath(name):
    if name.startswith('EXPR/'):
        return os.path.join(EXPR, name[5:] + '.target.gz')
    return os.path.join(TGT, name + '.target.gz')


def make_combined_key(key_name, comps):
    kb = body.data.shape_keys.key_blocks
    basis = kb[0]
    loaded = []
    for name, w in comps:
        n0 = len(kb)
        TargetService.load_target(body, tpath(name), weight=0.0, name='tmp_' + os.path.basename(name))
        assert len(kb) == n0 + 1, name
        loaded.append((kb[-1].name, w))
    n = len(basis.data)
    co = [Vector(basis.data[i].co) for i in range(n)]
    for kname, w in loaded:
        k = kb[kname]
        rel = k.relative_key
        for i in range(n):
            d = k.data[i].co - rel.data[i].co
            if d.length_squared:
                co[i] += w * d
    for kname, _ in loaded:
        body.shape_key_remove(kb[kname])
    new = body.shape_key_add(name=key_name, from_mix=False)
    new.relative_key = body.data.shape_keys.key_blocks[0]
    for i in range(n):
        new.data[i].co = co[i]
    new.value = 0.0
    new.slider_min, new.slider_max = 0.0, 1.0


def body_coords(values):
    """Body object-space coordinates with the current MPFB keys plus the given key values."""
    kb = body.data.shape_keys.key_blocks
    saved = {k: kb[k].value for k in values}
    for k, v in values.items():
        kb[k].value = v
    tmp = body.shape_key_add(name='tmp_fit', from_mix=True)
    co = [Vector(d.co) for d in tmp.data]
    body.shape_key_remove(tmp)
    for k, v in saved.items():
        kb[k].value = v
    return co


make_combined_key('Sunken', SUNKEN)
make_combined_key('MouthOpen', MOUTH)

# ---------------------------------------------------------------- propagate keys to fitted assets
SUBDIRS = ['eyes', 'eyebrows', 'eyelashes', 'teeth', 'tongue', 'hair', 'clothes']


def load_mhclo(ob):
    frag = GeneralObjectProperties.get_value('asset_source', entity_reference=ob)
    if not frag:
        return None
    for sd in SUBDIRS:
        p = AssetService.find_asset_absolute_path(os.path.basename(frag), sd)
        if p:
            m = Mhclo()
            m.load(p)
            return m
    return None


def fit(m, hv, sf):
    """Same binding as ClothesService.fit_clothes_to_human."""
    xs = ys = zs = sf
    if m.x_scale:
        xs = abs(hv[m.x_scale[0]][0] - hv[m.x_scale[1]][0]) / m.x_scale[2]
        ys = abs(hv[m.y_scale[0]][2] - hv[m.y_scale[1]][2]) / m.y_scale[2]
        zs = abs(hv[m.z_scale[0]][1] - hv[m.z_scale[1]][1]) / m.z_scale[2]
    out = []
    for i in range(len(m.verts)):
        vm = m.verts[i]
        a, b, c = vm['verts']
        w, o = vm['weights'], vm['offsets']
        out.append(w[0] * hv[a] + w[1] * hv[b] + w[2] * hv[c] + Vector((o[0] * xs, o[1] * zs, o[2] * ys)))
    return out


sf = GeneralObjectProperties.get_value('scale_factor', entity_reference=body) or 1.0
hv0 = body_coords({'Sunken': 0.0, 'MouthOpen': 0.0})
hvS = body_coords({'Sunken': 1.0, 'MouthOpen': 0.0})
hvM = body_coords({'Sunken': 0.0, 'MouthOpen': 1.0})


def add_driver(ob, key):
    fc = ob.data.shape_keys.key_blocks[key].driver_add('value')
    drv = fc.driver
    drv.type = 'AVERAGE'
    var = drv.variables.new()
    var.name = 'v'
    var.targets[0].id_type = 'KEY'
    var.targets[0].id = body.data.shape_keys
    var.targets[0].data_path = f'key_blocks["{key}"].value'


assets = [o for o in bpy.data.objects if o.type == 'MESH' and o.parent == rig and o is not body]
for ob in assets:
    m = load_mhclo(ob)
    if m is None or len(m.verts) != len(ob.data.vertices):
        print('skip keys for', ob.name)
        continue
    f0, fS, fM = fit(m, hv0, sf), fit(m, hvS, sf), fit(m, hvM, sf)
    err = max((f0[i] - ob.data.vertices[i].co).length for i in range(len(f0)))
    if not ob.data.shape_keys:
        ob.shape_key_add(name='Basis', from_mix=False)
    for key, fk in (('Sunken', fS), ('MouthOpen', fM)):
        k = ob.shape_key_add(name=key, from_mix=False)
        for i, v in enumerate(ob.data.vertices):
            k.data[i].co = v.co + (fk[i] - f0[i])
        add_driver(ob, key)
    print('keys ->', ob.name, 'fit err', round(err, 5))

# shrunken, sunken eyeballs (object space: the body faces -Y, so "back" is +Y)
eyes = next(o for o in assets if 'high-poly' in o.name)
ks = eyes.data.shape_keys.key_blocks['Sunken']
for side in (1, -1):
    idx = [i for i, p in enumerate(ks.data) if p.co.x * side > 0]
    c = sum((ks.data[i].co for i in idx), Vector()) / len(idx)
    for i in idx:
        ks.data[i].co = c + (ks.data[i].co - c) * 0.8 + Vector((0, 0.005, 0.0006))

# the tongue lies on the floor of the mouth: it drops with the jaw like the lower teeth
teeth = next(o for o in assets if 'teeth' in o.name)
tongue = next(o for o in assets if 'tongue' in o.name)
tk = teeth.data.shape_keys.key_blocks['MouthOpen']
zc = sum(v.co.z for v in teeth.data.vertices) / len(teeth.data.vertices)
low = [i for i, v in enumerate(teeth.data.vertices) if v.co.z < zc]
jaw = sum((tk.data[i].co - teeth.data.vertices[i].co for i in low), Vector()) / len(low)
# the retracted lower lip is tighter than the jaw helper: pull the lower jaw back so the gum
# does not poke through the chin, and the tongue back behind the lower teeth
for i in low:
    tk.data[i].co.y += 0.0035
gk = tongue.data.shape_keys.key_blocks['MouthOpen']
for i, v in enumerate(tongue.data.vertices):
    gk.data[i].co = v.co + jaw * 0.9 + Vector((0, 0.006, -0.003))
print('jaw drop', [round(x, 4) for x in jaw])

# ---------------------------------------------------------------- glasses
gpath = AssetService.find_asset_absolute_path('kwnet_at_optical_glasses.mhclo', 'clothes')
glasses = HumanService.add_mhclo_asset(gpath, body, asset_type='Clothes', subdiv_levels=0, material_type='MAKESKIN')
bpy.context.view_layer.update()
bm = bmesh.new()
bm.from_mesh(glasses.data)
bm.verts.ensure_lookup_table()
seen, comps = set(), []
for v in bm.verts:
    if v.index in seen:
        continue
    st, comp = [v], []
    while st:
        x = st.pop()
        if x.index in seen:
            continue
        seen.add(x.index)
        comp.append(x.index)
        st.extend(e.other_vert(x) for e in x.link_edges)
    comps.append(comp)
bm.free()
lens_comps = [c for c in comps if len(c) < 100]          # two flat 36-vertex lens discs
assert len(lens_comps) == 2, [len(c) for c in comps]
lens_idx = set(i for c in lens_comps for i in c)


def split_off(src, keep, name):
    me = src.data.copy()
    me.name = name
    ob = bpy.data.objects.new(name, me)
    scene.collection.objects.link(ob)
    ob.matrix_world = src.matrix_world
    bm = bmesh.new()
    bm.from_mesh(me)
    bm.verts.ensure_lookup_table()
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if v.index not in keep], context='VERTS')
    bm.to_mesh(me)
    bm.free()
    return ob


def cx(c):
    return sum(glasses.data.vertices[i].co.x for i in c) / len(c)


lens_comps.sort(key=cx)
# the body faces -Y in object space, so the character's left eye is at +X
lens_r = split_off(glasses, set(lens_comps[0]), 'Lens_R')
lens_l = split_off(glasses, set(lens_comps[1]), 'Lens_L')
frame = split_off(glasses, set(range(len(glasses.data.vertices))) - lens_idx, 'Glasses')
for m in list(body.modifiers):                            # glasses must not hide body parts
    if m.type == 'MASK' and 'glasses' in m.name.lower():
        body.modifiers.remove(m)
bpy.data.objects.remove(glasses, do_unlink=True)
head_bone = rig.data.bones['mixamorig:Head']
for ob in (frame, lens_l, lens_r):
    for m in list(ob.modifiers):
        ob.modifiers.remove(m)
    for vg in list(ob.vertex_groups):
        ob.vertex_groups.remove(vg)
    ob.data.materials.clear()
    mw = ob.matrix_world.copy()
    ob.parent = rig
    ob.parent_type = 'BONE'
    ob.parent_bone = head_bone.name
    bpy.context.view_layer.update()
    ob.matrix_world = mw
for ob in (lens_l, lens_r):
    sol = ob.modifiers.new('Thickness', 'SOLIDIFY')
    sol.thickness = 0.0012
    sol.offset = 0.0

# ---------------------------------------------------------------- material helpers
def new_mat(name):
    m = bpy.data.materials.get(name)
    if m:
        bpy.data.materials.remove(m)
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    out.location = (1400, 0)
    bsdf = nt.nodes.new('ShaderNodeBsdfPrincipled')
    bsdf.location = (1100, 0)
    nt.links.new(bsdf.outputs[0], out.inputs[0])
    return m, nt, bsdf


def node(nt, typ, loc, **kw):
    n = nt.nodes.new(typ)
    n.location = loc
    for k, v in kw.items():
        if k.startswith('in_'):
            n.inputs[k[3:].replace('_', ' ')].default_value = v
        else:
            setattr(n, k, v)
    return n


def img(nt, path, loc, colorspace='sRGB', alpha=False):
    n = nt.nodes.new('ShaderNodeTexImage')
    n.location = loc
    im = bpy.data.images.load(path, check_existing=True)
    im.colorspace_settings.name = colorspace
    if alpha:
        im.alpha_mode = 'CHANNEL_PACKED'
    n.image = im
    return n


def L(nt, a, b):
    nt.links.new(a, b)


def sock(coll, ident):
    return next(s for s in coll if s.identifier == ident)


def mix_col(nt, loc, blend='MIX', fac=1.0, b=None):
    """RGBA mix node; returns (node, A, B, Result)."""
    n = nt.nodes.new('ShaderNodeMix')
    n.data_type = 'RGBA'
    n.blend_type = blend
    n.location = loc
    sock(n.inputs, 'Factor_Float').default_value = fac
    if b is not None:
        sock(n.inputs, 'B_Color').default_value = b
    return n, sock(n.inputs, 'A_Color'), sock(n.inputs, 'B_Color'), sock(n.outputs, 'Result_Color')


def fac(n):
    return sock(n.inputs, 'Factor_Float')


def metric_coords(nt, ob, loc):
    """Generated (undeformed, rig-stable) coordinates scaled to metres."""
    tc = node(nt, 'ShaderNodeTexCoord', loc)
    mp = node(nt, 'ShaderNodeMapping', (loc[0] + 200, loc[1]))
    vs = [v.co for v in ob.data.vertices]
    mp.inputs['Scale'].default_value = [max(v[i] for v in vs) - min(v[i] for v in vs) for i in range(3)]
    L(nt, tc.outputs['Generated'], mp.inputs['Vector'])
    return mp.outputs[0]


def gray(nt, src, loc):
    cc = node(nt, 'ShaderNodeCombineColor', loc)
    for i in range(3):
        L(nt, src, cc.inputs[i])
    return cc.outputs[0]


# ---------------------------------------------------------------- skin
skin, nt, bsdf = new_mat('HumanSkin')
skin['dryness'] = 1.0
skin.id_properties_ui('dryness').update(min=0.0, max=1.0, soft_min=0.0, soft_max=1.0,
                                        description='0 = pale sickly skin, 1 = dried mummy')
dry = node(nt, 'ShaderNodeValue', (-1200, 700), name='dryness', label='dryness')
dry.outputs[0].default_value = 1.0
fc = dry.outputs[0].driver_add('default_value')
fc.driver.type = 'AVERAGE'
v = fc.driver.variables.new()
v.name = 'd'
v.targets[0].id_type = 'MATERIAL'
v.targets[0].id = skin
v.targets[0].data_path = '["dryness"]'
D = dry.outputs[0]

tex = img(nt, os.path.join(DATA, 'skins/young_caucasian_male/young_lightskinned_male_diffuse.png'), (-1500, 400))
# alive: pale, desaturated, greenish-grey pallor
hs = node(nt, 'ShaderNodeHueSaturation', (-1200, 400), in_Saturation=0.45, in_Value=0.92)
L(nt, tex.outputs[0], hs.inputs['Color'])
pal, a, b, pal_out = mix_col(nt, (-950, 400), 'MULTIPLY', 0.5, (0.84, 0.88, 0.72, 1))
L(nt, hs.outputs[0], a)

mc = metric_coords(nt, body, (-2400, -300))
# organic warp for every procedural pattern (no visible cell grid)
warp = node(nt, 'ShaderNodeTexNoise', (-2150, -700), in_Scale=25.0, in_Detail=3.0)
L(nt, mc, warp.inputs['Vector'])
wc = node(nt, 'ShaderNodeVectorMath', (-1950, -700), operation='MULTIPLY_ADD')
L(nt, warp.outputs['Color'], wc.inputs[0])
wc.inputs[1].default_value = (0.012, 0.012, 0.012)
L(nt, mc, wc.inputs[2])
W = wc.outputs[0]

# mummy colour: dark brown-grey leather, mottled, with the wrinkle detail of an old-skin texture
mottle = node(nt, 'ShaderNodeTexNoise', (-1500, 0), in_Scale=6.0, in_Detail=8.0, in_Roughness=0.62)
L(nt, W, mottle.inputs['Vector'])
ramp = node(nt, 'ShaderNodeValToRGB', (-1250, 0))
cr = ramp.color_ramp
cr.elements[0].position, cr.elements[0].color = 0.30, (0.020, 0.0145, 0.011, 1)
cr.elements[1].position, cr.elements[1].color = 0.75, (0.115, 0.098, 0.080, 1)
cr.elements.new(0.5).color = (0.052, 0.038, 0.028, 1)
L(nt, mottle.outputs['Fac'], ramp.inputs['Fac'])
old = img(nt, os.path.join(DATA, 'skins/old_caucasian_male/old_lightskinned_male_diffuse.png'), (-1500, 250))
obw = node(nt, 'ShaderNodeRGBToBW', (-1250, 250))
L(nt, old.outputs[0], obw.inputs[0])
omr = node(nt, 'ShaderNodeMapRange', (-1050, 250), in_From_Min=0.2, in_From_Max=0.7, in_To_Min=0.55, in_To_Max=1.2)
L(nt, obw.outputs[0], omr.inputs['Value'])
_, a, b, c_old = mix_col(nt, (-850, 0), 'MULTIPLY', 1.0)
L(nt, ramp.outputs[0], a)
L(nt, gray(nt, omr.outputs[0], (-850, 250)), b)
dust = node(nt, 'ShaderNodeTexNoise', (-1500, -300), in_Scale=18.0, in_Detail=6.0, in_Roughness=0.7)
L(nt, W, dust.inputs['Vector'])
dmr = node(nt, 'ShaderNodeMapRange', (-1250, -300), in_From_Min=0.56, in_From_Max=0.78, in_To_Max=0.55)
L(nt, dust.outputs['Fac'], dmr.inputs['Value'])
du, a, b, du_out = mix_col(nt, (-650, 0), 'MIX', 1.0, (0.20, 0.185, 0.16, 1))
L(nt, dmr.outputs[0], fac(du))
L(nt, c_old, a)


# relief: meandering shrinkage creases at two scales, wrinkle bands, pores
def crease(scale, width, loc, stretch=(1.0, 1.0, 1.0), detail=2.0):
    vec = W
    if stretch != (1.0, 1.0, 1.0):
        sm = node(nt, 'ShaderNodeVectorMath', (loc[0] - 200, loc[1]), operation='MULTIPLY')
        L(nt, W, sm.inputs[0])
        sm.inputs[1].default_value = stretch
        vec = sm.outputs[0]
    n = node(nt, 'ShaderNodeTexNoise', loc, in_Scale=scale, in_Detail=detail, in_Roughness=0.5)
    L(nt, vec, n.inputs['Vector'])
    # distance to the noise's 0.5 iso-line: a network of meandering grooves, not cells
    d = node(nt, 'ShaderNodeMath', (loc[0] + 200, loc[1]), operation='SUBTRACT')
    L(nt, n.outputs['Fac'], d.inputs[0])
    d.inputs[1].default_value = 0.5
    a = node(nt, 'ShaderNodeMath', (loc[0] + 350, loc[1]), operation='ABSOLUTE')
    L(nt, d.outputs[0], a.inputs[0])
    mr = node(nt, 'ShaderNodeMapRange', (loc[0] + 500, loc[1]), in_From_Min=0.0, in_From_Max=width)
    mr.interpolation_type = 'SMOOTHSTEP'
    L(nt, a.outputs[0], mr.inputs['Value'])
    return mr.outputs[0]                              # 0 in the groove, 1 on the skin between


# long shrinkage folds whose direction drifts between vertical and horizontal, + fine crepe
c1v = crease(45.0, 0.016, (-1500, -500), (1.0, 1.0, 0.18))
c1h = crease(45.0, 0.016, (-1500, -650), (0.18, 1.0, 1.0))
orient = node(nt, 'ShaderNodeTexNoise', (-1500, -350), in_Scale=3.5, in_Detail=2.0)
L(nt, mc, orient.inputs['Vector'])
orm = node(nt, 'ShaderNodeMapRange', (-1250, -350), in_From_Min=0.42, in_From_Max=0.58)
L(nt, orient.outputs['Fac'], orm.inputs['Value'])
c1m = nt.nodes.new('ShaderNodeMix')
c1m.data_type, c1m.location = 'FLOAT', (-1000, -550)
L(nt, orm.outputs[0], sock(c1m.inputs, 'Factor_Float'))
L(nt, c1v, sock(c1m.inputs, 'A_Float'))
L(nt, c1h, sock(c1m.inputs, 'B_Float'))
c1 = sock(c1m.outputs, 'Result_Float')
c2 = crease(160.0, 0.03, (-1500, -900), detail=1.0)
wv = node(nt, 'ShaderNodeTexWave', (-1500, -1150), in_Scale=30.0, in_Distortion=10.0, in_Detail=4.0,
          in_Detail_Scale=1.5, in_Detail_Roughness=0.7)
wv.wave_type = 'BANDS'
wv.bands_direction = 'Z'
L(nt, W, wv.inputs['Vector'])
pores = node(nt, 'ShaderNodeTexNoise', (-1500, -1400), in_Scale=600.0, in_Detail=2.0)
L(nt, mc, pores.inputs['Vector'])


def madd(x, k, y, loc):
    n = node(nt, 'ShaderNodeMath', loc, operation='MULTIPLY_ADD')
    L(nt, x, n.inputs[0])
    n.inputs[1].default_value = k
    if isinstance(y, float):
        n.inputs[2].default_value = y
    else:
        L(nt, y, n.inputs[2])
    return n.outputs[0]


h = madd(c1, 0.3, 0.0, (-1000, -700))
h = madd(c2, 0.3, h, (-800, -750))
h = madd(wv.outputs['Fac'], 0.15, h, (-600, -800))
# anatomical wrinkles (forehead, crow's feet, nasolabial, neck) painted into the old-skin texture
h = madd(obw.outputs[0], 0.6, h, (-500, -650))
hm = node(nt, 'ShaderNodeMath', (-400, -800), operation='MULTIPLY')
L(nt, h, hm.inputs[0])
L(nt, D, hm.inputs[1])
h = madd(pores.outputs['Fac'], 0.1, hm.outputs[0], (-200, -900))
# real skin pores / fine lines from a photo-based normal map under the procedural relief
snm = img(nt, os.path.join(DATA, 'skins/mindfront_aksel_skin/Aksel_Skin_NRM.png'), (300, -900), 'Non-Color')
snmap = node(nt, 'ShaderNodeNormalMap', (550, -900), in_Strength=1.0)
L(nt, snm.outputs[0], snmap.inputs['Color'])
bump = node(nt, 'ShaderNodeBump', (800, -600), in_Strength=0.55, in_Distance=0.0018)
L(nt, h, bump.inputs['Height'])
L(nt, snmap.outputs[0], bump.inputs['Normal'])
L(nt, bump.outputs[0], bsdf.inputs['Normal'])

# shading of the relief into the colour: dirt in the grooves, cavities (AO), worn ridges (pointiness)
cdk = node(nt, 'ShaderNodeMapRange', (-1000, -500), in_To_Min=0.7, in_To_Max=1.0)
L(nt, c1, cdk.inputs['Value'])
ao = node(nt, 'ShaderNodeAmbientOcclusion', (-1250, -1650), samples=8, only_local=True, in_Distance=0.04)
aom = node(nt, 'ShaderNodeMapRange', (-1000, -1650), in_To_Min=0.2, in_To_Max=1.0)
L(nt, ao.outputs['AO'], aom.inputs['Value'])
geo = node(nt, 'ShaderNodeNewGeometry', (-1250, -1900))
pr = node(nt, 'ShaderNodeMapRange', (-1000, -1900), in_From_Min=0.45, in_From_Max=0.55, in_To_Min=0.75, in_To_Max=1.2)
L(nt, geo.outputs['Pointiness'], pr.inputs['Value'])
shade = node(nt, 'ShaderNodeMath', (-800, -1650), operation='MULTIPLY')
L(nt, aom.outputs[0], shade.inputs[0])
L(nt, pr.outputs[0], shade.inputs[1])
shade2 = node(nt, 'ShaderNodeMath', (-600, -1650), operation='MULTIPLY')
L(nt, shade.outputs[0], shade2.inputs[0])
L(nt, cdk.outputs[0], shade2.inputs[1])
_, a, b, mummy_out = mix_col(nt, (-300, 0), 'MULTIPLY', 1.0)
L(nt, du_out, a)
L(nt, gray(nt, shade2.outputs[0], (-450, -1650)), b)

base, a, b, base_out = mix_col(nt, (300, 200))
L(nt, D, fac(base))
L(nt, pal_out, a)
L(nt, mummy_out, b)
L(nt, base_out, bsdf.inputs['Base Color'])


def drive(inp, lo, hi, loc):
    m = nt.nodes.new('ShaderNodeMix')
    m.data_type = 'FLOAT'
    m.location = loc
    sock(m.inputs, 'A_Float').default_value = lo
    sock(m.inputs, 'B_Float').default_value = hi
    L(nt, D, sock(m.inputs, 'Factor_Float'))
    L(nt, sock(m.outputs, 'Result_Float'), inp)


# waxy glints on the taut skin between creases, rough grooves
mrough = node(nt, 'ShaderNodeMapRange', (500, 150), in_To_Min=0.8, in_To_Max=0.5)
L(nt, c2, mrough.inputs['Value'])
rmix = nt.nodes.new('ShaderNodeMix')
rmix.data_type, rmix.location = 'FLOAT', (800, 100)
L(nt, D, sock(rmix.inputs, 'Factor_Float'))
sock(rmix.inputs, 'A_Float').default_value = 0.40
L(nt, mrough.outputs[0], sock(rmix.inputs, 'B_Float'))
L(nt, sock(rmix.outputs, 'Result_Float'), bsdf.inputs['Roughness'])
drive(bsdf.inputs['Subsurface Weight'], 0.25, 0.02, (800, 0))
bsdf.inputs['Subsurface Radius'].default_value = (1.0, 0.35, 0.2)
bsdf.inputs['Subsurface Scale'].default_value = 0.008
drive(bsdf.inputs['Coat Weight'], 0.18, 0.05, (800, -100))
bsdf.inputs['Coat Roughness'].default_value = 0.35
drive(bsdf.inputs['Sheen Weight'], 0.0, 0.4, (800, -200))
bsdf.inputs['Sheen Roughness'].default_value = 0.55
bsdf.inputs['Sheen Tint'].default_value = (0.62, 0.52, 0.42, 1)
drive(bsdf.inputs['Specular IOR Level'], 0.5, 0.4, (800, -300))
body.data.materials.clear()
body.data.materials.append(skin)

# ---------------------------------------------------------------- clothes: yellowed, grimy, stained
clothes = next(o for o in assets if 'casualsuit' in o.name)
cl, nt, bsdf = new_mat('HumanClothes')
cdir = os.path.join(DATA, 'clothes/male_casualsuit06')
ct = img(nt, os.path.join(cdir, 'male_casualsuit06_diffuse.png'), (-1600, 300))
aot = img(nt, os.path.join(cdir, 'male_casualsuit06_ao.png'), (-1600, 0), 'Non-Color')
nm = img(nt, os.path.join(cdir, 'male_casualsuit06_normal.png'), (-500, -900), 'Non-Color')
# T-shirt = upper half of the UV layout; its printed logo is replaced by plain cotton
uv = node(nt, 'ShaderNodeUVMap', (-1900, 600))
sep = node(nt, 'ShaderNodeSeparateXYZ', (-1700, 600))
L(nt, uv.outputs[0], sep.inputs[0])
shirt = node(nt, 'ShaderNodeMapRange', (-1500, 600), in_From_Min=0.52, in_From_Max=0.535)
L(nt, sep.outputs['Y'], shirt.inputs['Value'])
SH = shirt.outputs[0]
_, a, b, base = mix_col(nt, (-1300, 300), 'MIX', 1.0, (0.40, 0.40, 0.38, 1))
L(nt, SH, fac(_))
L(nt, ct.outputs[0], a)
# old sweat yellowing of the cotton
yk = node(nt, 'ShaderNodeMath', (-1300, 550), operation='MULTIPLY')
L(nt, SH, yk.inputs[0])
yk.inputs[1].default_value = 1.0
_, a, b, yel = mix_col(nt, (-1100, 300), 'MULTIPLY', 1.0, (0.92, 0.87, 0.60, 1))
L(nt, yk.outputs[0], fac(_))
L(nt, base, a)
_, a, b, aom = mix_col(nt, (-900, 300), 'MULTIPLY', 0.85)
L(nt, yel, a)
L(nt, aot.outputs[0], b)
cmc = metric_coords(nt, clothes, (-2200, -300))
# dirt collected in folds (AO) + patchy grime
ao = node(nt, 'ShaderNodeAmbientOcclusion', (-1600, -300), samples=8, only_local=True, in_Distance=0.06)
aoi = node(nt, 'ShaderNodeMapRange', (-1400, -300), in_From_Min=1.0, in_From_Max=0.3, in_To_Max=0.9)
L(nt, ao.outputs['AO'], aoi.inputs['Value'])
_, a, b, fold = mix_col(nt, (-700, 300), 'MULTIPLY', 1.0, (0.36, 0.32, 0.25, 1))
L(nt, aoi.outputs[0], fac(_))
L(nt, aom, a)
g1 = node(nt, 'ShaderNodeTexNoise', (-1600, -550), in_Scale=5.0, in_Detail=10.0, in_Roughness=0.65)
L(nt, cmc, g1.inputs['Vector'])
gm = node(nt, 'ShaderNodeMapRange', (-1400, -550), in_From_Min=0.40, in_From_Max=0.72, in_To_Max=0.85)
L(nt, g1.outputs['Fac'], gm.inputs['Value'])
_, a, b, grime = mix_col(nt, (-550, 300), 'MULTIPLY', 1.0, (0.46, 0.42, 0.34, 1))
L(nt, gm.outputs[0], fac(_))
L(nt, fold, a)
# big soft yellow-brown sweat stains (T-shirt only)
s1 = node(nt, 'ShaderNodeTexNoise', (-1600, -800), in_Scale=3.0, in_Detail=6.0, in_Roughness=0.6)
L(nt, cmc, s1.inputs['Vector'])
s1m = node(nt, 'ShaderNodeMapRange', (-1400, -800), in_From_Min=0.42, in_From_Max=0.56, in_To_Max=0.9)
L(nt, s1.outputs['Fac'], s1m.inputs['Value'])
s1k = node(nt, 'ShaderNodeMath', (-1200, -800), operation='MULTIPLY')
L(nt, s1m.outputs[0], s1k.inputs[0])
L(nt, SH, s1k.inputs[1])
_, a, b, st1 = mix_col(nt, (-400, 300), 'MULTIPLY', 1.0, (0.70, 0.56, 0.22, 1))
L(nt, s1k.outputs[0], fac(_))
L(nt, grime, a)
# small darker spills (coffee, food)
s2 = node(nt, 'ShaderNodeTexNoise', (-1600, -1050), in_Scale=14.0, in_Detail=8.0, in_Roughness=0.7)
L(nt, cmc, s2.inputs['Vector'])
s2m = node(nt, 'ShaderNodeMapRange', (-1400, -1050), in_From_Min=0.60, in_From_Max=0.65, in_To_Max=0.85)
L(nt, s2.outputs['Fac'], s2m.inputs['Value'])
_, a, b, st2 = mix_col(nt, (-250, 300), 'MULTIPLY', 1.0, (0.30, 0.20, 0.10, 1))
L(nt, s2m.outputs[0], fac(_))
L(nt, st1, a)
L(nt, st2, bsdf.inputs['Base Color'])
bsdf.inputs['Roughness'].default_value = 0.92
bsdf.inputs['Sheen Weight'].default_value = 0.35
bsdf.inputs['Sheen Roughness'].default_value = 0.4
nmap = node(nt, 'ShaderNodeNormalMap', (-200, -900), in_Strength=1.6)
L(nt, nm.outputs[0], nmap.inputs['Color'])
# jersey knit + small crumples of a shirt slept in for weeks
knit = node(nt, 'ShaderNodeTexNoise', (-500, -1200), in_Scale=2500.0, in_Detail=1.0)
L(nt, cmc, knit.inputs['Vector'])
crum = node(nt, 'ShaderNodeTexNoise', (-500, -1450), in_Scale=40.0, in_Detail=6.0, in_Roughness=0.6)
L(nt, cmc, crum.inputs['Vector'])
kh = node(nt, 'ShaderNodeMath', (-300, -1300), operation='MULTIPLY_ADD')
L(nt, knit.outputs['Fac'], kh.inputs[0])
kh.inputs[1].default_value = 0.06
L(nt, crum.outputs['Fac'], kh.inputs[2])
# big creases running round the torso (ridges of a stretched noise, mostly horizontal)
fst = node(nt, 'ShaderNodeVectorMath', (-700, -1700), operation='MULTIPLY')
L(nt, cmc, fst.inputs[0])
fst.inputs[1].default_value = (0.35, 0.35, 1.0)
fn = node(nt, 'ShaderNodeTexNoise', (-500, -1700), in_Scale=14.0, in_Detail=3.0, in_Roughness=0.55)
L(nt, fst.outputs[0], fn.inputs['Vector'])
fd = node(nt, 'ShaderNodeMath', (-300, -1700), operation='SUBTRACT')
L(nt, fn.outputs['Fac'], fd.inputs[0])
fd.inputs[1].default_value = 0.5
fa = node(nt, 'ShaderNodeMath', (-150, -1700), operation='ABSOLUTE')
L(nt, fd.outputs[0], fa.inputs[0])
fold_h = node(nt, 'ShaderNodeMapRange', (0, -1700), in_From_Min=0.0, in_From_Max=0.08)
L(nt, fa.outputs[0], fold_h.inputs['Value'])
fbump = node(nt, 'ShaderNodeBump', (0, -1300), in_Strength=0.6, in_Distance=0.006)
L(nt, fold_h.outputs[0], fbump.inputs['Height'])
L(nt, nmap.outputs[0], fbump.inputs['Normal'])
cbump = node(nt, 'ShaderNodeBump', (200, -1000), in_Strength=0.35, in_Distance=0.002)
L(nt, kh.outputs[0], cbump.inputs['Height'])
L(nt, fbump.outputs[0], cbump.inputs['Normal'])
L(nt, cbump.outputs[0], bsdf.inputs['Normal'])
clothes.data.materials.clear()
clothes.data.materials.append(cl)


def assign(sub, mat):
    for o in assets:
        if sub in o.name:
            o.data.materials.clear()
            o.data.materials.append(mat)


def card_material(name, path, tint, rough, dusty=0.0):
    m, nt, bsdf = new_mat(name)
    t = img(nt, path, (-700, 200), alpha=True)
    _, a, b, tinted = mix_col(nt, (-400, 200), 'MULTIPLY', 1.0, tint)
    L(nt, t.outputs[0], a)
    _, a, b, out = mix_col(nt, (-200, 200), 'MIX', dusty, (0.36, 0.34, 0.31, 1))
    L(nt, tinted, a)
    L(nt, out, bsdf.inputs['Base Color'])
    L(nt, t.outputs[1], bsdf.inputs['Alpha'])
    bsdf.inputs['Roughness'].default_value = rough
    m.surface_render_method = 'DITHERED'
    return m


# the MakeHuman hair cap is only a dark, lumpy base layer under the particle strands
assign('short02', card_material('HumanHair', os.path.join(DATA, 'hair/short02/short02_diffuse.png'),
                                (0.17, 0.145, 0.12, 1), 0.5, 0.06))
hair = next(o for o in assets if 'short02' in o.name)
ht = bpy.data.textures.new('HairTousle', 'CLOUDS')
ht.noise_scale, ht.noise_depth = 0.035, 2
dm = hair.modifiers.new('Tousle', 'DISPLACE')
dm.texture, dm.texture_coords, dm.direction = ht, 'LOCAL', 'NORMAL'
dm.strength, dm.mid_level = 0.012, 0.5
hair.modifiers.move(len(hair.modifiers) - 1, 0)

# messy, unwashed strands: particle hair on the scalp (where the cap sits), after the armature
from mathutils.kdtree import KDTree
to_body = body.matrix_world.inverted() @ hair.matrix_world
kd = KDTree(len(hair.data.vertices))
for i, hv in enumerate(hair.data.vertices):
    kd.insert(to_body @ hv.co, i)
kd.balance()
gvis = body.vertex_groups['body'].index
scalp = body.vertex_groups.new(name='scalp')
for v in body.data.vertices:
    if not any(g.group == gvis for g in v.groups):
        continue
    d = kd.find(hv0[v.index])[2]
    if d < 0.03:
        scalp.add([v.index], 1.0 if d < 0.018 else (0.03 - d) / 0.012, 'REPLACE')
pm_mod = body.modifiers.new('HairStrands', 'PARTICLE_SYSTEM')
body.modifiers.move(len(body.modifiers) - 1, 1)
psys = pm_mod.particle_system
psys.vertex_group_density = 'scalp'
psys.vertex_group_length = 'scalp'
ps = psys.settings
ps.name = 'HairStrands'
ps.type = 'HAIR'
ps.count = 9000
ps.hair_length = 0.06
ps.length_random = 0.45 if hasattr(ps, 'length_random') else 0.0
ps.emit_from = 'FACE'
ps.use_advanced_hair = True                          # strand length = 4 x velocity (metres)
ps.normal_factor = 0.0075
ps.object_align_factor = (0.0, 0.0055, -0.0075)      # body object space: +Y = back, -Z = down
ps.factor_random = 0.003
ps.hair_step = 6
ps.display_step, ps.render_step = 3, 4
ps.child_type = 'INTERPOLATED'
ps.child_percent = 4
ps.rendered_child_count = 25
ps.clump_factor, ps.clump_shape = 1.0, 0.2           # greasy clumps
ps.roughness_1, ps.roughness_1_size = 0.001, 1.0
ps.roughness_endpoint, ps.roughness_end_shape = 0.003, 1.0
ps.roughness_2, ps.roughness_2_size, ps.roughness_2_threshold = 0.0, 1.0, 0.7
ps.kink = 'WAVE'
ps.kink_amplitude, ps.kink_frequency = 0.004, 2.0
ps.root_radius, ps.tip_radius, ps.radius_scale = 1.0, 0.4, 0.00012
hs_mat, nt, _b = new_mat('HumanHairStrands')
nt.nodes.remove(_b)
hb = node(nt, 'ShaderNodeBsdfHairPrincipled', (1100, 0))
hb.parametrization = 'MELANIN'
for k, val in (('Melanin', 0.93), ('Melanin Redness', 0.2), ('Roughness', 0.3), ('Radial Roughness', 0.45),
               ('Coat', 0.1), ('Random Color', 0.15), ('Random Roughness', 0.3)):
    if k in hb.inputs:
        hb.inputs[k].default_value = val
if 'Tint' in hb.inputs:
    hb.inputs['Tint'].default_value = (0.85, 0.80, 0.72, 1)        # dusty
L(nt, hb.outputs[0], nt.nodes['Material Output'].inputs['Surface'])
body.data.materials.append(hs_mat)
ps.material = len(body.data.materials)
assign('eyebrow', card_material('HumanBrows', os.path.join(DATA, 'eyebrows/eyebrow001/eyebrow001.png'),
                                (0.7, 0.65, 0.6, 1), 0.7, 0.15))
assign('eyelashes', card_material('HumanLashes', os.path.join(DATA, 'eyelashes/eyelashes01/eyelashes01.png'),
                                  (0.7, 0.65, 0.6, 1), 0.7, 0.15))

# teeth: dried, yellow-brown
tm, nt, bsdf = new_mat('HumanTeeth')
t = img(nt, os.path.join(DATA, 'teeth/teeth_base/teeth.png'), (-900, 200))
ths = node(nt, 'ShaderNodeHueSaturation', (-600, 200), in_Saturation=0.15, in_Value=0.8)
L(nt, t.outputs[0], ths.inputs['Color'])
_, a, b, out = mix_col(nt, (-300, 200), 'MULTIPLY', 1.0, (0.22, 0.16, 0.09, 1))
L(nt, ths.outputs[0], a)
tao = node(nt, 'ShaderNodeAmbientOcclusion', (-600, -100), samples=8, in_Distance=0.006)
_, a, b, out2 = mix_col(nt, (-100, 200), 'MULTIPLY', 1.0)
L(nt, out, a)
L(nt, tao.outputs['Color'], b)
L(nt, out2, bsdf.inputs['Base Color'])
bsdf.inputs['Roughness'].default_value = 0.5
assign('teeth', tm)

tg, nt, bsdf = new_mat('HumanTongue')
bsdf.inputs['Base Color'].default_value = (0.008, 0.0045, 0.003, 1)
bsdf.inputs['Roughness'].default_value = 0.8
bsdf.inputs['Specular IOR Level'].default_value = 0.3
assign('tongue', tg)

# dead eyes: dark, dull, slightly clouded
em, nt, bsdf = new_mat('HumanEyes')
t = img(nt, os.path.join(DATA, 'eyes/materials/brown_eye.png'), (-700, 200))
hs = node(nt, 'ShaderNodeHueSaturation', (-450, 200), in_Saturation=0.3, in_Value=0.55)
L(nt, t.outputs[0], hs.inputs['Color'])
_, a, b, out = mix_col(nt, (-200, 200), 'MIX', 0.96, (0.012, 0.010, 0.008, 1))
L(nt, hs.outputs[0], a)
L(nt, out, bsdf.inputs['Base Color'])
bsdf.inputs['Roughness'].default_value = 0.6                        # dried film, no wet glint
bsdf.inputs['Specular IOR Level'].default_value = 0.3
assign('high-poly', em)

# glasses: dark plastic with fingerprints; lenses: thin glass with smudge roughness
gfm, nt, bsdf = new_mat('GlassesFrame')
bsdf.inputs['Base Color'].default_value = (0.018, 0.014, 0.012, 1)
nz = node(nt, 'ShaderNodeTexNoise', (-500, 0), in_Scale=180.0, in_Detail=4.0)
rr = node(nt, 'ShaderNodeMapRange', (-250, 0), in_To_Min=0.12, in_To_Max=0.45)
L(nt, nz.outputs['Fac'], rr.inputs['Value'])
L(nt, rr.outputs[0], bsdf.inputs['Roughness'])
frame.data.materials.append(gfm)

lm, nt, bsdf = new_mat('GlassesLens')
bsdf.inputs['Base Color'].default_value = (0.98, 0.98, 0.98, 1)
bsdf.inputs['Transmission Weight'].default_value = 1.0
bsdf.inputs['IOR'].default_value = 1.52
sn = node(nt, 'ShaderNodeTexNoise', (-500, 0), in_Scale=900.0, in_Detail=3.0)
smr = node(nt, 'ShaderNodeMapRange', (-250, 0), in_From_Min=0.55, in_From_Max=0.75, in_To_Min=0.0, in_To_Max=0.05)
L(nt, sn.outputs['Fac'], smr.inputs['Value'])
L(nt, smr.outputs[0], bsdf.inputs['Roughness'])
for ob in (lens_l, lens_r):
    ob.data.materials.append(lm)

# ---------------------------------------------------------------- face state, collection, cleanup
kb = body.data.shape_keys.key_blocks
kb['Sunken'].value = 1.0
kb['MouthOpen'].value = 1.0

for ob in [body] + assets:                                # lean viewport, smooth render
    for m in ob.modifiers:
        if m.type == 'SUBSURF':
            m.levels, m.render_levels = 0, 1

coll = bpy.data.collections.get('HUMAN') or bpy.data.collections.new('HUMAN')
if coll.name not in scene.collection.children:
    scene.collection.children.link(coll)
for ob in [rig, body, frame, lens_l, lens_r] + assets:
    for c in list(ob.users_collection):
        c.objects.unlink(ob)
    coll.objects.link(ob)
for ob in list(bpy.data.objects):
    if ob.name not in coll.objects:
        bpy.data.objects.remove(ob, do_unlink=True)
for c in list(bpy.data.collections):
    if c is not coll and not c.objects and not c.children:
        bpy.data.collections.remove(c)
NAMES = (('eyebrow', 'Eyebrows'), ('eyelashes', 'Eyelashes'), ('high-poly', 'Eyes'), ('teeth', 'Teeth'),
         ('tongue', 'Tongue'), ('short02', 'Hair'), ('casualsuit', 'Clothes'))
for ob in assets:
    for sub, nm_ in NAMES:
        if sub in ob.name:
            ob.name = ob.data.name = nm_
for act in list(bpy.data.actions):                        # leftovers of the Mixamo FBX imports
    if act.name not in ('Typing', 'SeatedIdle', 'Tremor', 'SitToType'):
        bpy.data.actions.remove(act)
for _ in range(3):
    for coll_ in (bpy.data.materials, bpy.data.node_groups, bpy.data.images, bpy.data.meshes):
        for d in list(coll_):
            if d.users == 0:
                coll_.remove(d)

rig.data.pose_position = 'POSE'
rig.animation_data.action = bpy.data.actions['Typing']
bpy.ops.file.pack_all()
bpy.ops.wm.save_as_mainfile(filepath=OUT, compress=True)
print('saved', OUT, sorted(o.name for o in coll.objects))
print('body modifiers', [(m.name, m.type) for m in body.modifiers])
