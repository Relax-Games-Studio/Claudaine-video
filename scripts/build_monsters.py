"""The game creatures that crawl out of the monitors: six Mixamo characters at real scale, horror materials,
and the `MonsterGlitch` geometry-nodes materialise / glitch effect. Writes blend/monsters.blend.
Run: Blender -b --factory-startup --python scripts/build_monsters.py -- [test]

Per creature <name>: collection MON_<name>, armature <name>_Rig (feet on z=0, facing +Y, scale 1),
mesh <name>_Body parented to it, actions <name>_Idle (cyclic) and <name>_Roar.
Body modifiers: 'MG_Rest' (stores rest positions) -> 'Armature' -> 'MonsterGlitch' (inputs below).
"""
import bpy, sys, os, math, json
from mathutils import Vector, Matrix
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from lib_build import CLIP, ORANGE, srgb, coll

MIX = f'{CLIP}/assets/mixamo'
GLOW = (1.0, 0.22, 0.045, 1.0)            # saturated Claude orange for emission (AgX keeps it orange)
DARKEN = {'demon': 0.3, 'skeleton': 0.36}   # pale-skinned textures get pushed further down
# picked from the test renders (renders/monster_test_lineup.png, monster_test_face_*.png)
RECOMMENDED = {'110.3s': 'warrok', '119.9s': 'maw', '168s_chorus': ['mutant', 'parasite'],
               'spare': 'skeleton'}
SKIP = {'demon': 'reads as a pale bald man in a sash, the least monstrous; keep only as a last resort'}
VOXEL_GAIN, FRONT_GAIN = 0.8, 1.5         # emission strengths; much above ~2 AgX bleaches the orange to peach/white
# name: (roar fbx, target height in metres at idle frame 1)
CREATURES = {
    'mutant': ('mutant_roar', 2.15),
    'warrok': ('warrok_roar', 2.30),
    'parasite': ('parasite_scream', 2.15),
    'maw': ('maw_roar', 2.35),
    'demon': ('demon_roar', 2.30),
    'skeleton': ('skeleton_scream', 2.10),
}
# MonsterGlitch interface: (name, socket type, default, min, max)
GLITCH_INPUTS = [
    ('Reveal', 'NodeSocketFloat', 1.0, 0.0, 1.0),
    ('Source', 'NodeSocketVector', (0.0, 0.8, 1.2), None, None),
    ('Glitch', 'NodeSocketFloat', 0.0, 0.0, 1.0),
    ('VoxelSize', 'NodeSocketFloat', 0.04, 0.005, 0.5),
    ('Seed', 'NodeSocketInt', 0, 0, 10000),
]


# ---------------------------------------------------------------- small node DSL

class GN:
    """Thin helper for building node trees from Python: every call returns an output socket."""

    def __init__(self, tree):
        self.t = tree
        self.x = 0

    def node(self, typ, **props):
        n = self.t.nodes.new(typ)
        for k, v in props.items():
            setattr(n, k, v)
        n.location = (self.x, 0)
        self.x += 30
        return n

    def put(self, sock, v):
        if isinstance(v, bpy.types.NodeSocket):
            self.t.links.new(v, sock)
        elif v is not None:
            sock.default_value = v

    def inp(self, n, key):
        """Socket by identifier, falling back to the first enabled socket with that name."""
        for s in n.inputs:
            if s.identifier == key:
                return s
        for s in n.inputs:
            if s.name == key and s.enabled:
                return s
        raise KeyError(f'{n.bl_idname} has no input {key}')

    def out(self, n, key=None):
        if key is None:
            return [s for s in n.outputs if s.enabled][0]
        for s in n.outputs:
            if s.identifier == key or (s.name == key and s.enabled):
                return s
        raise KeyError(f'{n.bl_idname} has no output {key}')

    def m(self, op, a, b=None, c=None, clamp=False):
        n = self.node('ShaderNodeMath', operation=op, use_clamp=clamp)
        for key, v in (('Value', a), ('Value_001', b), ('Value_002', c)):
            self.put(self.inp(n, key), v)
        return n.outputs[0]

    def v(self, op, a, b=None, scale=None):
        n = self.node('ShaderNodeVectorMath', operation=op)
        self.put(self.inp(n, 'Vector'), a)
        if b is not None:
            self.put(self.inp(n, 'Vector_001'), b)
        if scale is not None:
            self.put(self.inp(n, 'Scale'), scale)
        return self.out(n, 'Value' if op in ('DISTANCE', 'LENGTH', 'DOT_PRODUCT') else 'Vector')

    def cmp(self, op, a, b):
        n = self.node('FunctionNodeCompare', data_type='FLOAT', operation=op)
        self.put(self.inp(n, 'A'), a)
        self.put(self.inp(n, 'B'), b)
        return self.out(n, 'Result')

    def bool(self, op, a, b=None):
        n = self.node('FunctionNodeBooleanMath', operation=op)
        self.put(n.inputs[0], a)
        if b is not None:
            self.put(n.inputs[1], b)
        return n.outputs[0]

    def switch(self, typ, cond, false, true):
        n = self.node('GeometryNodeSwitch', input_type=typ)
        self.put(self.inp(n, 'Switch'), cond)
        self.put(self.inp(n, 'False'), false)
        self.put(self.inp(n, 'True'), true)
        return self.out(n, 'Output')

    def rand(self, typ, lo, hi, ident, seed):
        n = self.node('FunctionNodeRandomValue', data_type=typ)
        self.put(self.inp(n, 'Min'), lo)
        self.put(self.inp(n, 'Max'), hi)
        self.put(self.inp(n, 'ID'), ident)
        self.put(self.inp(n, 'Seed'), seed)
        return self.out(n, 'Value')

    def hash(self, typ, value, seed=None):
        n = self.node('FunctionNodeHashValue', data_type=typ)
        self.put(self.inp(n, 'Value'), value)
        if seed is not None:
            self.put(self.inp(n, 'Seed'), seed)
        return n.outputs[0]

    def mix_v(self, fac, a, b):
        n = self.node('ShaderNodeMix', data_type='VECTOR', clamp_factor=True)
        self.put(self.inp(n, 'Factor_Float'), fac)
        self.put(self.inp(n, 'A_Vector'), a)
        self.put(self.inp(n, 'B_Vector'), b)
        return self.out(n, 'Result_Vector')

    def comb(self, x, y, z):
        n = self.node('ShaderNodeCombineXYZ')
        for s, v in zip(n.inputs, (x, y, z)):
            self.put(s, v)
        return n.outputs[0]

    def sep(self, vec):
        n = self.node('ShaderNodeSeparateXYZ')
        self.put(n.inputs[0], vec)
        return n.outputs

    def int_const(self, val):
        return self.node('FunctionNodeInputInt', integer=val).outputs[0]

    def attr(self, name, typ='FLOAT_VECTOR'):
        n = self.node('GeometryNodeInputNamedAttribute', data_type=typ)
        n.inputs['Name'].default_value = name
        return self.out(n, 'Attribute'), self.out(n, 'Exists')

    def store(self, geo, name, value, typ='FLOAT', domain='POINT', sel=None):
        n = self.node('GeometryNodeStoreNamedAttribute', data_type=typ, domain=domain)
        self.put(n.inputs['Geometry'], geo)
        self.put(n.inputs['Name'], name)
        self.put(self.inp(n, 'Value'), value)
        if sel is not None:
            self.put(n.inputs['Selection'], sel)
        return n.outputs[0]


# ---------------------------------------------------------------- geometry nodes

def rest_group():
    """Stores the undeformed position as 'mg_rest' (put before the Armature modifier)."""
    ng = bpy.data.node_groups.new('MonsterRestPos', 'GeometryNodeTree')
    ng.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    ng.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    g = GN(ng)
    gi, go = g.node('NodeGroupInput'), g.node('NodeGroupOutput')
    pos = g.node('GeometryNodeInputPosition').outputs[0]
    st = g.store(gi.outputs[0], 'mg_rest', pos, 'FLOAT_VECTOR', 'POINT')
    ng.links.new(st, go.inputs[0])
    return ng


def glitch_group(voxel_mat):
    """MonsterGlitch: Reveal 0..1 builds the body out of voxels flying from Source (world point) that snap
    into place and turn into the skinned mesh, with an orange glow at the reveal front; Glitch 0..1 adds block
    jitter, slice shifts, see-through flicker. Pure function of the inputs + frame (no caches).
    Writes face attributes mg_glow / mg_fade on the mesh and point attribute mg_heat on the voxels."""
    ng = bpy.data.node_groups.new('MonsterGlitch', 'GeometryNodeTree')
    ng.interface.new_socket('Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    for name, typ, dflt, lo, hi in GLITCH_INPUTS:
        s = ng.interface.new_socket(name, in_out='INPUT', socket_type=typ)
        s.default_value = dflt
        if lo is not None:
            s.min_value, s.max_value = lo, hi
    ng.interface.new_socket('Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    g = GN(ng)
    gi, go = g.node('NodeGroupInput'), g.node('NodeGroupOutput')
    GEO, R, SRC, G, VS, SEED = (gi.outputs[k] for k in ('Geometry', 'Reveal', 'Source', 'Glitch', 'VoxelSize', 'Seed'))

    W, A_END, GLOW_FADE = 0.16, 0.86, 0.08      # travel time, last arrival, glow decay (all in Reveal units)

    # ---- shared fields / values
    frame = g.out(g.node('GeometryNodeInputSceneTime'), 'Frame')
    fr_i = g.m('FLOOR', frame)
    fr_half = g.m('FLOOR', g.m('MULTIPLY', frame, 0.5))
    oi = g.node('GeometryNodeObjectInfo', transform_space='ORIGINAL')
    g.put(oi.inputs['Object'], g.node('GeometryNodeSelfObject').outputs[0])
    M = g.out(oi, 'Transform')
    inv = g.node('FunctionNodeInvertMatrix')
    g.put(inv.inputs['Matrix'], M)
    Minv = g.out(inv, 'Matrix')
    tp = g.node('FunctionNodeTransformPoint')
    g.put(tp.inputs['Vector'], SRC)
    g.put(tp.inputs['Transform'], Minv)
    S_loc = tp.outputs[0]

    def world(vec):
        n = g.node('FunctionNodeTransformPoint')
        g.put(n.inputs['Vector'], vec)
        g.put(n.inputs['Transform'], M)
        return n.outputs[0]

    pos = g.node('GeometryNodeInputPosition').outputs[0]
    rest_a, rest_ok = g.attr('mg_rest')
    rest = g.switch('VECTOR', rest_ok, pos, rest_a)

    def snap(vec, size):
        n = g.node('ShaderNodeVectorMath', operation='SNAP')
        g.put(n.inputs[0], vec)
        g.put(n.inputs[1], g.comb(size, size, size))
        return n.outputs[0]

    cell = g.m('MULTIPLY', VS, 1.5)
    rest_snap = snap(rest, cell)
    d = g.v('DISTANCE', world(rest_snap), SRC)
    stat = g.node('GeometryNodeAttributeStatistic', data_type='FLOAT', domain='POINT')
    g.put(stat.inputs['Geometry'], GEO)
    g.put(g.inp(stat, 'Attribute'), g.v('DISTANCE', world(rest), SRC))
    dmin, dmax = g.out(stat, 'Min'), g.out(stat, 'Max')
    u0 = g.m('DIVIDE', g.m('SUBTRACT', d, dmin), g.m('ADD', g.m('SUBTRACT', dmax, dmin), 1e-4), clamp=True)
    nz = g.node('ShaderNodeTexNoise')
    g.put(nz.inputs['Vector'], rest_snap)
    nz.inputs['Scale'].default_value = 2.5
    nz.inputs['Detail'].default_value = 1.0
    n01 = g.node('ShaderNodeMapRange', clamp=True)
    g.put(n01.inputs['Value'], g.out(nz, 'Fac'))
    n01.inputs['From Min'].default_value = 0.3
    n01.inputs['From Max'].default_value = 0.7
    u = g.m('MULTIPLY_ADD', u0, 0.75, g.m('MULTIPLY', n01.outputs[0], 0.25))
    a = g.m('MULTIPLY', u, A_END - W)                                   # departure time
    p = g.m('DIVIDE', g.m('SUBTRACT', R, a), W, clamp=True)            # travel progress 0..1
    arrived = g.cmp('GREATER_EQUAL', g.m('SUBTRACT', R, a), W)
    since = g.m('SUBTRACT', g.m('SUBTRACT', R, a), W)                   # Reveal units since arrival

    # glitch cells (coarser blocks), random per cell, re-rolled every 2 frames
    gcell = snap(rest, g.m('MULTIPLY', VS, 2.5))
    h_g = g.hash('VECTOR', gcell, SEED)
    r_g = g.rand('FLOAT', 0.0, 1.0, h_g, fr_half)
    gsel = g.cmp('LESS_THAN', r_g, g.m('MULTIPLY', G, 0.16))
    gflash = g.bool('AND', g.bool('NOT', gsel), g.cmp('LESS_THAN', r_g, g.m('MULTIPLY', G, 0.3)))

    # ---- mesh branch
    keep_face = g.bool('AND', arrived, g.bool('NOT', gsel))
    dl = g.node('GeometryNodeDeleteGeometry', domain='FACE', mode='ALL')
    g.put(dl.inputs['Geometry'], GEO)
    g.put(dl.inputs['Selection'], g.bool('NOT', keep_face))
    glow = g.m('SUBTRACT', 1.0, g.m('DIVIDE', since, GLOW_FADE), clamp=True)
    glow = g.m('MAXIMUM', glow, g.m('MULTIPLY', g.switch('FLOAT', gflash, 0.0, 0.6), G))
    mesh = g.store(dl.outputs[0], 'mg_glow', glow, 'FLOAT', 'FACE')
    r_f = g.rand('FLOAT', 0.0, 1.0, h_g, g.m('ADD', fr_i, 77.0))
    fade = g.m('MULTIPLY', G, g.m('MULTIPLY_ADD', r_f, 0.7, 0.3))
    mesh = g.store(mesh, 'mg_fade', fade, 'FLOAT', 'FACE')
    # slice shift: horizontal bands slide sideways for a frame
    pz = g.sep(pos)[2]
    band = g.m('FLOOR', g.m('DIVIDE', pz, g.m('MULTIPLY', VS, 3.0)))
    h_b = g.hash('INT', band, SEED)
    r1 = g.rand('FLOAT', 0.0, 1.0, h_b, fr_i)
    r2 = g.rand('FLOAT', -1.0, 1.0, h_b, g.m('ADD', fr_i, 1000.0))
    sp = g.node('GeometryNodeSetPosition')
    g.put(sp.inputs['Geometry'], mesh)
    g.put(sp.inputs['Selection'], g.cmp('LESS_THAN', r1, g.m('MULTIPLY', G, 0.3)))
    g.put(sp.inputs['Offset'], g.comb(g.m('MULTIPLY', r2, g.m('MULTIPLY', G, 0.14)), 0.0, 0.0))
    mesh = sp.outputs[0]

    # ---- voxel branch
    dist = g.node('GeometryNodeDistributePointsOnFaces', distribute_method='RANDOM')
    g.put(dist.inputs['Mesh'], GEO)
    g.put(dist.inputs['Density'], g.m('DIVIDE', 2.2, g.m('MULTIPLY', VS, VS)))
    g.put(dist.inputs['Seed'], SEED)
    half = g.m('MULTIPLY', VS, 0.5)
    target = g.v('ADD', snap(pos, VS), g.comb(half, half, half))
    sp1 = g.node('GeometryNodeSetPosition')
    g.put(sp1.inputs['Geometry'], g.out(dist, 'Points'))
    g.put(sp1.inputs['Position'], target)
    mg = g.node('GeometryNodeMergeByDistance')
    g.put(mg.inputs['Geometry'], sp1.outputs[0])
    g.put(mg.inputs['Distance'], g.m('MULTIPLY', VS, 0.4))
    travel = g.bool('AND', g.cmp('GREATER_THAN', p, 0.002), g.bool('NOT', arrived))
    gcube = g.bool('AND', arrived, gsel)
    keep = g.bool('OR', travel, gcube)
    dl2 = g.node('GeometryNodeDeleteGeometry', domain='POINT', mode='ALL')
    g.put(dl2.inputs['Geometry'], mg.outputs[0])
    g.put(dl2.inputs['Selection'], g.bool('NOT', keep))
    pts = dl2.outputs[0]
    # positions: fly from the screen (Source, spread over a screen-sized patch) with an ease-out, jitter, quantised
    h_c = g.hash('VECTOR', snap(rest, VS), SEED)
    spread = g.rand('FLOAT_VECTOR', (-0.28, -0.05, -0.16), (0.28, 0.05, 0.16), h_c, g.m('ADD', SEED, 5.0))
    start = g.v('ADD', S_loc, spread)
    e = g.m('SUBTRACT', 1.0, g.m('POWER', g.m('SUBTRACT', 1.0, p), 2.2))
    fly = g.mix_v(e, start, pos)
    jn = g.node('ShaderNodeTexNoise')
    g.put(jn.inputs['Vector'], g.v('ADD', g.v('SCALE', pos, scale=5.0), g.comb(0.0, 0.0, g.m('MULTIPLY', frame, 0.21))))
    jn.inputs['Scale'].default_value = 1.0
    jit = g.v('SCALE', g.v('SUBTRACT', g.out(jn, 'Color'), (0.5, 0.5, 0.5)),
              scale=g.m('MULTIPLY', g.m('MULTIPLY', VS, 4.0), g.m('SUBTRACT', 1.0, p)))
    quart = g.m('MULTIPLY', VS, 0.25)
    flyq = g.v('ADD', snap(g.v('ADD', fly, jit), g.m('MULTIPLY', VS, 0.5)), g.comb(quart, quart, quart))
    goff = g.rand('FLOAT_VECTOR', (-1, -1, -1), (1, 1, 1), h_g, g.m('ADD', fr_half, 31.0))
    gpos = g.v('ADD', pos, g.v('SCALE', goff, scale=g.m('MULTIPLY', VS, g.m('MULTIPLY', G, 5.0))))
    sp2 = g.node('GeometryNodeSetPosition')
    g.put(sp2.inputs['Geometry'], pts)
    g.put(sp2.inputs['Position'], g.switch('VECTOR', travel, gpos, flyq))
    smooth = g.m('MULTIPLY', g.m('MULTIPLY', p, p), g.m('SUBTRACT', 3.0, g.m('MULTIPLY', p, 2.0)))
    scl = g.switch('FLOAT', travel, g.m('MULTIPLY', VS, 0.9), g.m('MULTIPLY', VS, g.m('MULTIPLY_ADD', smooth, 0.65, 0.25)))
    heat = g.switch('FLOAT', travel, g.rand('FLOAT', 0.2, 0.7, h_g, fr_half), g.m('MULTIPLY_ADD', p, -0.7, 1.0))
    pts = g.store(sp2.outputs[0], 'mg_heat', heat, 'FLOAT', 'POINT')
    cube = g.node('GeometryNodeMeshCube')
    cube.inputs['Size'].default_value = (1, 1, 1)
    iop = g.node('GeometryNodeInstanceOnPoints')
    g.put(iop.inputs['Points'], pts)
    g.put(iop.inputs['Instance'], cube.outputs['Mesh'])
    g.put(iop.inputs['Scale'], g.comb(scl, scl, scl))
    rz = g.node('GeometryNodeRealizeInstances')
    g.put(rz.inputs['Geometry'], iop.outputs[0])
    smat = g.node('GeometryNodeSetMaterial')
    g.put(smat.inputs['Geometry'], rz.outputs[0])
    smat.inputs['Material'].default_value = voxel_mat
    vox = smat.outputs[0]

    join = g.node('GeometryNodeJoinGeometry')
    ng.links.new(vox, join.inputs[0])
    ng.links.new(mesh, join.inputs[0])
    built = join.outputs[0]

    # ---- switches (single values: only the chosen branch is evaluated)
    full = g.bool('AND', g.cmp('GREATER_EQUAL', R, 0.999), g.cmp('LESS_EQUAL', G, 0.001))
    res = g.switch('GEOMETRY', full, built, GEO)
    gone = g.cmp('LESS_EQUAL', R, 0.001)
    flick = g.cmp('LESS_THAN', g.rand('FLOAT', 0.0, 1.0, g.int_const(0), g.m('ADD', fr_i, g.m('MULTIPLY', SEED, 31.0))),
                  g.m('MULTIPLY', G, 0.18))
    empty = g.node('GeometryNodeJoinGeometry').outputs[0]
    res = g.switch('GEOMETRY', g.bool('OR', gone, flick), res, empty)
    ng.links.new(res, go.inputs[0])
    return ng


# ---------------------------------------------------------------- materials

def voxel_material():
    m = bpy.data.materials.new('MonsterVoxel')
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (0.012, 0.01, 0.01, 1)
    b.inputs['Roughness'].default_value = 0.45
    b.inputs['Metallic'].default_value = 0.5
    b.inputs['Emission Color'].default_value = GLOW
    at = nt.nodes.new('ShaderNodeAttribute')
    at.attribute_name = 'mg_heat'
    mul = nt.nodes.new('ShaderNodeMath')
    mul.name = mul.label = 'HeatGain'      # overall voxel emission; lower it if voxels bleach to white
    mul.operation = 'MULTIPLY'
    mul.inputs[1].default_value = VOXEL_GAIN
    nt.links.new(at.outputs['Fac'], mul.inputs[0])
    nt.links.new(mul.outputs[0], b.inputs['Emission Strength'])
    return m


def horrify(m, eye_glow=None, value=0.5):
    """Dark, wet, desaturated version of a Mixamo material + the glitch hooks (mg_glow emission, mg_fade alpha)."""
    nt = m.node_tree
    b = [n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'][0]
    out = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'][0]
    bc = b.inputs['Base Color']
    if bc.is_linked:
        src = bc.links[0].from_socket
        hs = nt.nodes.new('ShaderNodeHueSaturation')
        hs.inputs['Saturation'].default_value = 0.55
        hs.inputs['Value'].default_value = value
        nt.links.new(src, hs.inputs['Color'])
        nt.links.new(hs.outputs[0], bc)
    else:
        c = bc.default_value
        bc.default_value = (c[0] * 0.4, c[1] * 0.4, c[2] * 0.4, 1)
    # wet: low, mottled roughness and a thin clear coat
    for l in list(b.inputs['Roughness'].links):
        nt.links.remove(l)
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 9.0
    mr = nt.nodes.new('ShaderNodeMapRange')
    mr.inputs['From Min'].default_value = 0.35
    mr.inputs['From Max'].default_value = 0.65
    mr.inputs['To Min'].default_value = 0.16
    mr.inputs['To Max'].default_value = 0.5
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    nt.links.new(nz.outputs['Fac'], mr.inputs['Value'])
    nt.links.new(mr.outputs[0], b.inputs['Roughness'])
    b.inputs['Coat Weight'].default_value = 0.35
    b.inputs['Coat Roughness'].default_value = 0.12
    b.inputs['Metallic'].default_value = 0.0
    # existing glow maps (maw, skeleton) -> faint orange
    ec = b.inputs['Emission Color']
    if ec.is_linked:
        src = ec.links[0].from_socket
        mx = nt.nodes.new('ShaderNodeMix')
        mx.data_type = 'RGBA'
        mx.blend_type = 'MULTIPLY'
        mx.inputs['Factor'].default_value = 1.0
        nt.links.new(src, mx.inputs['A'])
        mx.inputs['B'].default_value = GLOW
        nt.links.new(mx.outputs['Result'], ec)
        b.inputs['Emission Strength'].default_value = eye_glow or 2.5
    else:
        b.inputs['Emission Strength'].default_value = 0.0
    # glitch hooks
    ag = nt.nodes.new('ShaderNodeAttribute')
    ag.attribute_name = 'mg_glow'
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = GLOW
    gm = nt.nodes.new('ShaderNodeMath')
    gm.name = gm.label = 'GlowGain'        # reveal-front emission on the body
    gm.operation = 'MULTIPLY'
    gm.inputs[1].default_value = FRONT_GAIN
    nt.links.new(ag.outputs['Fac'], gm.inputs[0])
    nt.links.new(gm.outputs[0], em.inputs['Strength'])
    add = nt.nodes.new('ShaderNodeAddShader')
    nt.links.new(b.outputs[0], add.inputs[0])
    nt.links.new(em.outputs[0], add.inputs[1])
    af = nt.nodes.new('ShaderNodeAttribute')
    af.attribute_name = 'mg_fade'
    fm = nt.nodes.new('ShaderNodeMath')
    fm.operation = 'MULTIPLY_ADD'
    fm.inputs[1].default_value = -0.9
    fm.inputs[2].default_value = 1.0
    nt.links.new(af.outputs['Fac'], fm.inputs[0])
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(fm.outputs[0], mix.inputs['Fac'])
    nt.links.new(tr.outputs[0], mix.inputs[1])
    nt.links.new(add.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs['Surface'])
    m.surface_render_method = 'DITHERED'
    return m


def eye_material(name):
    m = bpy.data.materials.new(name)
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (0.05, 0.01, 0.003, 1)
    b.inputs['Roughness'].default_value = 0.1
    b.inputs['Emission Color'].default_value = GLOW
    b.inputs['Emission Strength'].default_value = 2.0
    return m


# ---------------------------------------------------------------- import + normalise

def all_fcurves(action):
    out = []
    for layer in action.layers:
        for strip in layer.strips:
            for cb in strip.channelbags:
                out += list(cb.fcurves)
    return out


def scale_locations(action, k):
    """Pose-bone locations are in armature units: rescale them when the armature's scale is applied."""
    for fc in all_fcurves(action):
        if fc.data_path.endswith('.location'):
            for kp in fc.keyframe_points:
                kp.co.y *= k
                kp.handle_left.y *= k
                kp.handle_right.y *= k
            fc.update()


def import_new(path):
    before_o, before_a = set(bpy.data.objects), set(bpy.data.actions)
    bpy.ops.import_scene.fbx(filepath=path)
    return ([o for o in bpy.data.objects if o not in before_o], [a for a in bpy.data.actions if a not in before_a])


def assign(rig, act):
    ad = rig.animation_data or rig.animation_data_create()
    ad.action = act
    if act.slots and ad.action_slot is None:
        ad.action_slot = act.slots[0]


def mesh_bbox(ob, depsgraph):
    ev = ob.evaluated_get(depsgraph)
    me = ev.to_mesh()
    vs = [ev.matrix_world @ v.co for v in me.vertices]
    ev.to_mesh_clear()
    lo = Vector((min(v.x for v in vs), min(v.y for v in vs), min(v.z for v in vs)))
    hi = Vector((max(v.x for v in vs), max(v.y for v in vs), max(v.z for v in vs)))
    return lo, hi


def build_creature(name, roar_file, height, root_col, glitch_ng, rest_ng, voxel_mat):
    scene = bpy.context.scene
    col = coll(f'MON_{name}', root_col)
    objs, acts = import_new(f'{MIX}/{name}_idle_skin.fbx')
    rig = [o for o in objs if o.type == 'ARMATURE'][0]
    meshes = [o for o in objs if o.type == 'MESH']
    idle = acts[0]
    robjs, racts = import_new(f'{MIX}/{roar_file}.fbx')
    roar = racts[0]
    for o in robjs:
        bpy.data.objects.remove(o, do_unlink=True)
    for o in objs:
        for c in list(o.users_collection):
            c.objects.unlink(o)
        col.objects.link(o)
    rig.name = rig.data.name = f'{name}_Rig'
    idle.name, roar.name = f'{name}_Idle', f'{name}_Roar'
    roar.use_fake_user = True
    idle.use_fake_user = True

    # demon: its eye ring gets its own emissive material before the parts are joined
    if name == 'demon':
        for o in meshes:
            if 'Eyes' in o.name:
                o.data.materials.clear()
                o.data.materials.append(eye_material('demon_EyeGlow'))
    # one body mesh per creature (consistent glitch progression across parts)
    bpy.ops.object.select_all(action='DESELECT')
    for o in meshes:
        o.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    body = bpy.context.view_layer.objects.active
    body.name = body.data.name = f'{name}_Body'

    # measure the raw height at idle frame 1, then bake scale (to target height) + face +Y into the data
    assign(rig, idle)
    scene.frame_set(1)
    dg = bpy.context.evaluated_depsgraph_get()
    lo, hi = mesh_bbox(body, dg)
    k = height / (hi.z - lo.z)
    # unparent the body (keeping its world matrix), move rig + body by the same change, bake both separately
    old = rig.matrix_world.copy()
    bmw = body.matrix_world.copy()
    body.parent = None
    body.matrix_world = bmw
    rig.rotation_euler = (math.pi / 2, 0, math.pi)
    rig.scale = (0.01 * k,) * 3
    bpy.context.view_layer.update()
    body.matrix_world = rig.matrix_world @ old.inverted() @ bmw

    def apply(ob, loc, rot, scl):
        bpy.ops.object.select_all(action='DESELECT')
        ob.select_set(True)
        bpy.context.view_layer.objects.active = ob
        bpy.ops.object.transform_apply(location=loc, rotation=rot, scale=scl)

    apply(rig, False, True, True)
    apply(body, True, True, True)
    scale_locations(idle, 0.01 * k)
    scale_locations(roar, 0.01 * k)
    # feet on the floor, centred on the hips
    scene.frame_set(1)
    dg = bpy.context.evaluated_depsgraph_get()
    lo, hi = mesh_bbox(body, dg)
    hips = rig.matrix_world @ rig.pose.bones['mixamorig:Hips'].head
    shift = Vector((-hips.x, -hips.y, -lo.z))
    rig.location += shift
    body.location += shift
    bpy.context.view_layer.update()
    apply(rig, True, False, False)
    apply(body, True, False, False)

    # actions: idle loops, both get a slot named after the rig so they auto-bind when assigned
    for act in (idle, roar):
        for s in act.slots:
            try:
                s.name_display = rig.name
            except Exception:
                pass
    idle.use_frame_range = True
    idle.frame_start, idle.frame_end = idle.frame_range
    idle.use_cyclic = True
    for fc in all_fcurves(idle):
        if not any(md.type == 'CYCLES' for md in fc.modifiers):
            fc.modifiers.new('CYCLES')
    assign(rig, idle)

    # materials
    for slot in body.material_slots:
        if slot.material and slot.material.name != 'demon_EyeGlow':
            horrify(slot.material, value=DARKEN.get(name, 0.5))
    # modifiers: rest positions -> armature -> glitch
    arm_md = [md for md in body.modifiers if md.type == 'ARMATURE'][0]
    arm_md.object = rig
    rmd = body.modifiers.new('MG_Rest', 'NODES')
    rmd.node_group = rest_ng
    try:
        body.modifiers.move(len(body.modifiers) - 1, 0)
    except Exception:
        with bpy.context.temp_override(object=body, active_object=body):
            bpy.ops.object.modifier_move_to_index(modifier='MG_Rest', index=0)
    gmd = body.modifiers.new('MonsterGlitch', 'NODES')
    gmd.node_group = glitch_ng
    body.parent = rig
    body.matrix_parent_inverse = Matrix()
    return rig, body, idle, roar


def roar_peak(rig, roar):
    """Frame where the head is furthest from its first-frame position (the scream apex)."""
    scene = bpy.context.scene
    assign(rig, roar)
    rig.animation_data.action_slot = roar.slots[0]
    f0, f1 = int(roar.frame_range[0]), int(roar.frame_range[1])
    scene.frame_set(f0)
    h0 = rig.matrix_world @ rig.pose.bones['mixamorig:Head'].head
    best, bf = -1, f0
    for f in range(f0, f1 + 1):
        scene.frame_set(f)
        dd = (rig.matrix_world @ rig.pose.bones['mixamorig:Head'].head - h0).length
        if dd > best:
            best, bf = dd, f
    return bf, best


def root_motion(rig, idle, roar):
    """Hips travel in the floor plane: idle loop seam, and how far the roar steps out from its start."""
    scene = bpy.context.scene
    out = {}
    for key, act in (('idle', idle), ('roar', roar)):
        assign(rig, act)
        rig.animation_data.action_slot = act.slots[0]
        f0, f1 = int(act.frame_range[0]), int(act.frame_range[1])
        pts = []
        for f in range(f0, f1 + 1):
            scene.frame_set(f)
            h = rig.matrix_world @ rig.pose.bones['mixamorig:Hips'].head
            pts.append(Vector((h.x, h.y, 0)))
        if key == 'idle':
            out['idle_loop_seam_m'] = round((pts[-1] - pts[0]).length, 3)
        else:
            far = max(pts, key=lambda q: (q - pts[0]).length)
            out['roar_root_max_offset_m'] = [round(c, 3) for c in (far - pts[0])[:2]]
            out['roar_root_end_offset_m'] = [round(c, 3) for c in (pts[-1] - pts[0])[:2]]
    return out


def main():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    scene.render.engine = 'BLENDER_EEVEE'
    scene.render.fps = 24
    root = coll('MONSTERS')
    voxel_mat = voxel_material()
    voxel_mat.use_fake_user = True
    rest_ng = rest_group()
    glitch_ng = glitch_group(voxel_mat)
    report = {'units': 'metres; rig origin at feet z=0, facing +Y, scale 1; 24 fps',
              'modifier': {'name': 'MonsterGlitch', 'object': '<name>_Body', 'sockets': {},
                           'stack': ['MG_Rest (stores rest positions)', 'Armature', 'MonsterGlitch'],
                           'set_value': 'body.modifiers["MonsterGlitch"].properties.inputs.<Socket_N>.value = v'
                                        '   (Blender 5.2: md["Socket_N"] item access raises TypeError)',
                           'keyframe': 'body.keyframe_insert(\'modifiers["MonsterGlitch"].properties.inputs.<Socket_N>.value\', frame=f)',
                           'semantics': {
                               'Reveal': '0 = nothing, 1 = full skinned mesh. Voxels leave Source and land nearest-first; '
                                         'the last part lands at Reveal 0.86, the glow band dies out by ~0.95. '
                                         'Animating 1 -> 0 plays the dissolve back into Source.',
                               'Source': 'world-space point the voxels stream from (centre of the monitor screen)',
                               'Glitch': '0..1 block swaps, slice shifts, see-through faces, whole-body dropout frames '
                                         '(~0.2-0.4 for a nervous idle, 0.7+ for a hard glitch); re-rolls every 2 frames',
                               'VoxelSize': 'cube edge in metres (0.04 default; 0.03 finer/slower, 0.06 chunkier)',
                               'Seed': 'int, decorrelates two creatures revealed at the same time'},
                           'fast_path': 'Reveal >= 0.999 and Glitch <= 0.001 passes the mesh through untouched; '
                                        'Reveal <= 0.001 outputs nothing',
                           'attributes': {'mg_glow': 'face float, body emission at the reveal front',
                                          'mg_fade': 'face float, glitch see-through',
                                          'mg_heat': 'point float on voxel cubes',
                                          'mg_rest': 'point vector, rest position (from MG_Rest)'},
                           'emission_gains': {'MonsterVoxel material node "HeatGain"': VOXEL_GAIN,
                                              '<creature> material node "GlowGain"': FRONT_GAIN,
                                              'note': 'tuned for AgX Medium High Contrast, exposure 0.8'}},
              'creatures': {}}
    gmd_sockets = None
    for name, (roar_file, height) in CREATURES.items():
        rig, body, idle, roar = build_creature(name, roar_file, height, root, glitch_ng, rest_ng, voxel_mat)
        pk, amp = roar_peak(rig, roar)
        rm = root_motion(rig, idle, roar)
        assign(rig, idle)
        rig.animation_data.action_slot = idle.slots[0]
        scene.frame_set(1)
        dg = bpy.context.evaluated_depsgraph_get()
        lo, hi = mesh_bbox(body, dg)
        tris = sum(len(p.vertices) - 2 for p in body.data.polygons)
        gmd = body.modifiers['MonsterGlitch']
        if gmd_sockets is None:
            gmd_sockets = {it.name: it.identifier for it in glitch_ng.interface.items_tree
                           if it.item_type == 'SOCKET' and it.in_out == 'INPUT' and it.socket_type != 'NodeSocketGeometry'}
        report['creatures'][name] = {
            'rig': rig.name, 'mesh_objects': [body.name], 'collection': f'MON_{name}',
            'height': round(hi.z - lo.z, 3), 'bbox_min': [round(c, 3) for c in lo], 'bbox_max': [round(c, 3) for c in hi],
            'tris': tris,
            'actions': {idle.name: [int(idle.frame_range[0]), int(idle.frame_range[1])],
                        roar.name: [int(roar.frame_range[0]), int(roar.frame_range[1])]},
            'roar_peak_frame': pk, 'roar_head_travel_m': round(amp, 3),
            **rm,
            'materials': [s.material.name for s in body.material_slots if s.material],
        }
        print('BUILT', name, report['creatures'][name], flush=True)
    report['modifier']['sockets'] = gmd_sockets
    report['recommended'] = RECOMMENDED
    report['skip'] = SKIP
    for im in bpy.data.images:
        if im.packed_file is None and im.source == 'FILE' and im.filepath:
            try:
                im.pack()
            except Exception as e:
                print('PACK FAIL', im.name, e)
    scene.frame_set(1)
    out = f'{CLIP}/blend/monsters.blend'
    bpy.ops.wm.save_as_mainfile(filepath=out, compress=True)
    json.dump(report, open(f'{CLIP}/blend/monster_report.json', 'w'), indent=1)
    print('SAVED', out, flush=True)
    return report


if __name__ == '__main__':
    main()
