"""IV cannula in the crook of the left arm, built on the posed body's skin so that it stays on it.
At a reference frame of the catheter close-up the skin of the left forearm is sampled (rays cast out from the
forearm bone axis, so the patches wrap round the arm): the film dressing, tapes, bruises and the vein glow are
skin patches carrying the skin's own bone weights, un-posed to the rest pose and deformed by the rig like the
body itself; the rigid plastic parts (cannula, hub, wings, port, luer) ride on an empty vertex-parented to a
skin-bound triangle; where the IV tube lies on the arm it takes the skin's weights too and fades back to a free
line where it leaves it.
build_scene: cath = setup(...) before the tube, then bind_tube() on the tube meshes."""
import bpy, bmesh, math
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from lib_build import srgb, new_mat, principled, ORANGE

S0 = 0.030                  # insertion point: metres down the forearm from the elbow joint
TUBE_R = 0.0021             # IV tube radius (desk.build_iv_tube)
HUB_C = Vector((0.0, -0.015, 0.003))   # middle of the hub in the catheter frame (camera target, focus)
LIFT_Y = -0.108             # where the tube leaves the skin (local +Y = up the arm, toward the shoulder)


# ---------------------------------------------------------------- skin sampling at the reference frame

class Skin:
    def __init__(self, rig, body, dg):
        self.rig = rig
        masks = [(body.vertex_groups[m.vertex_group].index, m.invert_vertex_group, m.threshold)
                 for m in body.modifiers if m.type == 'MASK' and m.show_viewport]
        orig = []
        for v in body.data.vertices:
            w = {g.group: g.weight for g in v.groups}
            if all((w.get(gi, 0.0) > th) != iv for gi, iv, th in masks):
                orig.append(v.index)
        me = body.evaluated_get(dg).to_mesh()
        assert len(me.vertices) == len(orig), (len(me.vertices), len(orig))
        Mrb = rig.matrix_world.inverted() @ body.matrix_world      # body -> armature space
        R = Mrb.to_3x3()
        self.co = [Mrb @ v.co for v in me.vertices]
        self.no = [(R @ v.normal).normalized() for v in me.vertices]
        self.polys = [list(p.vertices) for p in me.polygons]
        body.evaluated_get(dg).to_mesh_clear()
        self.bvh = BVHTree.FromPolygons(self.co, self.polys)
        deform = {g.index: g.name for g in body.vertex_groups if g.name.startswith('mixamorig:')}
        bdata = body.data.vertices
        self.w = []
        for oi in orig:
            ws = {deform[g.group]: g.weight for g in bdata[oi].groups if g.group in deform and g.weight > 1e-4}
            tot = sum(ws.values()) or 1.0
            self.w.append({k: v / tot for k, v in ws.items()})
        P, bones = rig.pose.bones, rig.data.bones
        self.skin_m = {b.name: P[b.name].matrix @ b.matrix_local.inverted() for b in bones}

    def sample(self, origin, direction):
        """first skin hit going out from inside the limb: (point, smooth normal, bone weights)"""
        hit, nor, fi, d = self.bvh.ray_cast(origin, direction)
        if hit is None:
            return None
        return self.interp(hit, fi)

    def nearest(self, p):
        """closest skin point to p: (point, smooth normal, bone weights, distance)"""
        hit, nor, fi, d = self.bvh.find_nearest(p)
        return self.interp(hit, fi) + (d,)

    def interp(self, hit, fi):
        vs = self.polys[fi]
        iw = [1.0 / max((self.co[i] - hit).length, 1e-5) ** 2 for i in vs]
        t = sum(iw)
        n = sum((self.no[i] * (k / t) for i, k in zip(vs, iw)), Vector()).normalized()
        w = {}
        for i, k in zip(vs, iw):
            for b, x in self.w[i].items():
                w[b] = w.get(b, 0.0) + x * k / t
        return hit, n, w

    def unpose(self, p, w, k=1.0):
        """rest-pose position of a point that the rig's skinning with weights w, blended in by k (the Armature
        modifier's mask weight), puts at p (armature space)"""
        M = Matrix.Diagonal((1.0 - k,) * 4)
        for b, x in w.items():
            M = M + self.skin_m[b] * (x * k)
        return M.inverted() @ p


class ArmSurface:
    """(x, y) -> skin of the forearm: y metres up the arm from the insertion point, x metres of arc round it"""
    def __init__(self, skin, rig, cam_rig):
        P = rig.pose.bones
        self.skin = skin
        sh, el, wr = P['mixamorig:LeftArm'].head, P['mixamorig:LeftForeArm'].head, P['mixamorig:LeftHand'].head
        self.el = el
        self.f = (wr - el).normalized()                 # down the forearm
        up = (sh - el).normalized()
        d_in = (up + self.f).normalized()               # into the crook of the elbow
        d_in = (d_in - self.f * d_in.dot(self.f)).normalized()
        c = cam_rig - (el + self.f * S0)                # turn a little toward the close-up camera
        c = (c - self.f * c.dot(self.f)).normalized()
        self.d0 = (d_in + 0.6 * c).normalized()
        self.Y = -self.f                                # local +Y: up the arm (the cannula points to the heart)
        p0, n0, w0 = self.at(0.0, 0.0, raw=True)
        self.p0, self.n0 = p0, n0
        self.R = (p0 - self.axis(0.0)).length
        Yt = (self.Y - n0 * self.Y.dot(n0)).normalized()
        self.frame = Matrix((Yt.cross(n0), Yt, n0)).transposed().to_4x4()
        self.frame.translation = p0

    def axis(self, y):
        return self.el + self.f * (S0 - y)

    def at(self, x, y, raw=False):
        d = self.d0 if raw else Matrix.Rotation(x / self.R, 3, self.Y) @ self.d0
        r = self.skin.sample(self.axis(y), d)
        assert r is not None, ('arm surface miss', x, y)
        return r

    def local(self, p):
        return self.frame.inverted() @ p


# ---------------------------------------------------------------- materials

def film_mat():
    """transparent polyurethane film: glossy, nearly clear, a milky reinforced border and a white label tab"""
    m, nt = new_mat('IVFilm')
    if nt is None:
        return m
    b, out = principled(nt)
    b.inputs['Base Color'].default_value = (0.8, 0.8, 0.78, 1)
    b.inputs['Roughness'].default_value = 0.12
    b.inputs['Specular IOR Level'].default_value = 0.7
    uv = nt.nodes.new('ShaderNodeUVMap')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(uv.outputs[0], sep.inputs[0])
    # distance to the nearest edge in UV, ~0.07 = the 3.5 mm border
    edge = None
    for comp in ('X', 'Y'):
        a = nt.nodes.new('ShaderNodeMath'); a.operation = 'PINGPONG'; a.inputs[1].default_value = 0.5
        nt.links.new(sep.outputs[comp], a.inputs[0])
        if edge is None:
            edge = a
        else:
            mn = nt.nodes.new('ShaderNodeMath'); mn.operation = 'MINIMUM'
            nt.links.new(edge.outputs[0], mn.inputs[0]); nt.links.new(a.outputs[0], mn.inputs[1])
            edge = mn
    border = nt.nodes.new('ShaderNodeMapRange')
    border.inputs['From Min'].default_value, border.inputs['From Max'].default_value = 0.075, 0.06
    nt.links.new(edge.outputs[0], border.inputs['Value'])
    alpha = nt.nodes.new('ShaderNodeMapRange')
    alpha.inputs['To Min'].default_value, alpha.inputs['To Max'].default_value = 0.08, 0.22
    nt.links.new(border.outputs[0], alpha.inputs['Value'])
    nt.links.new(alpha.outputs[0], b.inputs['Alpha'])
    rough = nt.nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value, rough.inputs['To Max'].default_value = 0.08, 0.6
    nt.links.new(border.outputs[0], rough.inputs['Value'])
    nt.links.new(rough.outputs[0], b.inputs['Roughness'])
    m.surface_render_method = 'BLENDED'
    m.use_backface_culling = False
    return m


def tape_mat():
    """white fabric surgical tape: rough, a woven grain, slightly translucent at the frayed edges"""
    m, nt = new_mat('IVTape')
    if nt is None:
        return m
    b, out = principled(nt)
    b.inputs['Base Color'].default_value = srgb((0.93, 0.92, 0.88))
    b.inputs['Roughness'].default_value = 0.85
    b.inputs['Subsurface Weight'].default_value = 0.15
    tc = nt.nodes.new('ShaderNodeTexCoord')
    wave = nt.nodes.new('ShaderNodeTexWave')
    wave.inputs['Scale'].default_value = 900.0
    wave.inputs['Distortion'].default_value = 1.5
    nt.links.new(tc.outputs['Object'], wave.inputs['Vector'])
    noise = nt.nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 1500.0
    nt.links.new(tc.outputs['Object'], noise.inputs['Vector'])
    mix = nt.nodes.new('ShaderNodeMath'); mix.operation = 'ADD'
    nt.links.new(wave.outputs['Fac'], mix.inputs[0]); nt.links.new(noise.outputs['Fac'], mix.inputs[1])
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.25
    bump.inputs['Distance'].default_value = 0.0002
    nt.links.new(mix.outputs[0], bump.inputs['Height'])
    nt.links.new(bump.outputs[0], b.inputs['Normal'])
    return m


def decal_mat(name, inner, outer, alpha, soft=0.5):
    """round skin mark: colour from inner (centre) to outer (rim), alpha fading out over the outer `soft` part"""
    m, nt = new_mat(name)
    if nt is None:
        return m
    b, out = principled(nt)
    b.inputs['Roughness'].default_value = 0.55
    uv = nt.nodes.new('ShaderNodeUVMap')
    vm = nt.nodes.new('ShaderNodeVectorMath'); vm.operation = 'SUBTRACT'
    vm.inputs[1].default_value = (0.5, 0.5, 0.0)
    nt.links.new(uv.outputs[0], vm.inputs[0])
    noise = nt.nodes.new('ShaderNodeTexNoise')
    noise.inputs['Scale'].default_value = 7.0
    noise.inputs['Detail'].default_value = 4.0
    nt.links.new(uv.outputs[0], noise.inputs['Vector'])
    ln = nt.nodes.new('ShaderNodeVectorMath'); ln.operation = 'LENGTH'
    nt.links.new(vm.outputs[0], ln.inputs[0])
    r = nt.nodes.new('ShaderNodeMath'); r.operation = 'MULTIPLY_ADD'      # radius 0..0.5, wobbled by the noise
    r.inputs[1].default_value = 2.0
    nt.links.new(ln.outputs['Value'], r.inputs[0])
    wob = nt.nodes.new('ShaderNodeMath'); wob.operation = 'MULTIPLY_ADD'
    wob.inputs[1].default_value = 0.5
    wob.inputs[2].default_value = -0.25
    nt.links.new(noise.outputs['Fac'], wob.inputs[0])
    nt.links.new(wob.outputs[0], r.inputs[2])
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = srgb(inner)
    ramp.color_ramp.elements[1].color = srgb(outer)
    nt.links.new(r.outputs[0], ramp.inputs['Fac'])
    nt.links.new(ramp.outputs['Color'], b.inputs['Base Color'])
    fade = nt.nodes.new('ShaderNodeMapRange')
    fade.inputs['From Min'].default_value, fade.inputs['From Max'].default_value = 1.0 - soft, 1.0
    fade.inputs['To Min'].default_value, fade.inputs['To Max'].default_value = alpha, 0.0
    nt.links.new(r.outputs[0], fade.inputs['Value'])
    nt.links.new(fade.outputs[0], b.inputs['Alpha'])
    m.surface_render_method = 'BLENDED'
    return m


def vein_mat():
    """the drug creeping up the vein under the skin: a soft orange glow behind a front ('VeinFront', keyed)"""
    m, nt = new_mat('IVVeinGlow')
    if nt is None:
        return m
    out = [n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL'][0]
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Color'].default_value = srgb((1.0, 0.36, 0.12))
    tr = nt.nodes.new('ShaderNodeBsdfTransparent')
    mix = nt.nodes.new('ShaderNodeMixShader')
    nt.links.new(tr.outputs[0], mix.inputs[1]); nt.links.new(em.outputs[0], mix.inputs[2])
    nt.links.new(mix.outputs[0], out.inputs[0])
    uv = nt.nodes.new('ShaderNodeUVMap')
    sep = nt.nodes.new('ShaderNodeSeparateXYZ')
    nt.links.new(uv.outputs[0], sep.inputs[0])
    across = nt.nodes.new('ShaderNodeMath'); across.operation = 'PINGPONG'; across.inputs[1].default_value = 0.5
    nt.links.new(sep.outputs['X'], across.inputs[0])
    edge = nt.nodes.new('ShaderNodeMapRange')                           # soft across the vein
    edge.inputs['From Min'].default_value, edge.inputs['From Max'].default_value = 0.0, 0.45
    nt.links.new(across.outputs[0], edge.inputs['Value'])
    front = nt.nodes.new('ShaderNodeMath'); front.operation = 'SUBTRACT'; front.name = 'VeinFront'
    front.inputs[0].default_value = 0.0
    nt.links.new(sep.outputs['Y'], front.inputs[1])
    ahead = nt.nodes.new('ShaderNodeMapRange')                          # fades in just behind the front
    ahead.inputs['From Min'].default_value, ahead.inputs['From Max'].default_value = 0.0, 0.12
    nt.links.new(front.outputs[0], ahead.inputs['Value'])
    tail = nt.nodes.new('ShaderNodeMapRange')                           # dimmer far up the arm
    tail.inputs['To Min'].default_value, tail.inputs['To Max'].default_value = 1.0, 0.35
    nt.links.new(sep.outputs['Y'], tail.inputs['Value'])
    a = nt.nodes.new('ShaderNodeMath'); a.operation = 'MULTIPLY'
    nt.links.new(edge.outputs[0], a.inputs[0]); nt.links.new(ahead.outputs[0], a.inputs[1])
    a2 = nt.nodes.new('ShaderNodeMath'); a2.operation = 'MULTIPLY'
    nt.links.new(a.outputs[0], a2.inputs[0]); nt.links.new(tail.outputs[0], a2.inputs[1])
    fac = nt.nodes.new('ShaderNodeMath'); fac.operation = 'MULTIPLY'; fac.inputs[1].default_value = 0.55
    nt.links.new(a2.outputs[0], fac.inputs[0])
    nt.links.new(fac.outputs[0], mix.inputs[0])
    st = nt.nodes.new('ShaderNodeMath'); st.operation = 'MULTIPLY'; st.inputs[1].default_value = 2.2
    nt.links.new(a2.outputs[0], st.inputs[0])
    nt.links.new(st.outputs[0], em.inputs['Strength'])
    m.surface_render_method = 'BLENDED'
    return m


def plastic(name, color, alpha, rough=0.25, emit=None):
    m, nt = new_mat(name)
    if nt is None:
        return m
    b, out = principled(nt)
    b.inputs['Base Color'].default_value = srgb(color)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Coat Weight'].default_value = 0.5
    b.inputs['Coat Roughness'].default_value = 0.08
    if alpha < 1.0:
        b.inputs['Alpha'].default_value = alpha
        m.surface_render_method = 'BLENDED'
    if emit:
        b.inputs['Emission Color'].default_value = srgb(emit)
        b.inputs['Emission Strength'].default_value = 0.0
    return m


# ---------------------------------------------------------------- geometry

def tent(x, y, bumps):
    """height of a film / tape laid over the bumps [(segment a, b in (x, y), radius, top)] near (x, y)"""
    h = 0.0
    for (ax, ay), (bx, by), r, top in bumps:
        dx, dy = bx - ax, by - ay
        L2 = dx * dx + dy * dy
        u = max(0.0, min(1.0, ((x - ax) * dx + (y - ay) * dy) / L2)) if L2 else 0.0
        d = math.hypot(x - ax - u * dx, y - ay - u * dy)
        if d < r * 0.5:
            k = 1.0
        elif d < r + 0.005:
            k = 0.5 + 0.5 * math.cos(math.pi * (d - r * 0.5) / (r * 0.5 + 0.005))
        else:
            k = 0.0
        h = max(h, top * k)
    return h


def skin_object(name, surf, verts_xy, faces, off, mat, col, rig, uv=None, bumps=()):
    """a mesh lying on the skin (each (x, y) projected onto the arm, raised by off + tent height), bound to the rig
    with the skin's own weights at that spot, coordinates un-posed to the rest pose"""
    skin = surf.skin
    me = bpy.data.meshes.new(name)
    rest, ws = [], []
    for x, y in verts_xy:
        p, n, w = surf.at(x, y)
        q = p + n * (off + tent(x, y, bumps))
        rest.append(skin.unpose(q, w))
        ws.append(w)
    me.from_pydata([tuple(v) for v in rest], [], faces)
    if uv:
        lay = me.uv_layers.new(name='UVMap')
        for poly in me.polygons:
            for li in poly.loop_indices:
                lay.data[li].uv = uv[me.loops[li].vertex_index]
    me.materials.append(mat)
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    ob.parent = rig
    groups = {}
    for i, w in enumerate(ws):
        for b, x in w.items():
            if x < 1e-3:
                continue
            if b not in groups:
                groups[b] = ob.vertex_groups.new(name=b)
            groups[b].add([i], x, 'REPLACE')
    md = ob.modifiers.new('Armature', 'ARMATURE')
    md.object = rig
    return ob


def grid(x0, x1, y0, y1, nx, ny):
    verts, uv, faces = [], [], []
    for j in range(ny + 1):
        for i in range(nx + 1):
            u, v = i / nx, j / ny
            verts.append((x0 + (x1 - x0) * u, y0 + (y1 - y0) * v))
            uv.append((u, v))
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    return verts, faces, uv


def disc(cx, cy, r, rings=6, segs=24):
    verts, uv, faces = [(cx, cy)], [(0.5, 0.5)], []
    for k in range(1, rings + 1):
        for s in range(segs):
            a = 2 * math.pi * s / segs
            verts.append((cx + r * k / rings * math.cos(a), cy + r * k / rings * math.sin(a)))
            uv.append((0.5 + 0.5 * k / rings * math.cos(a), 0.5 + 0.5 * k / rings * math.sin(a)))
    for s in range(segs):
        faces.append((0, 1 + s, 1 + (s + 1) % segs))
    for k in range(1, rings):
        b0, b1 = 1 + (k - 1) * segs, 1 + k * segs
        for s in range(segs):
            faces.append((b0 + s, b1 + s, b1 + (s + 1) % segs, b0 + (s + 1) % segs))
    return verts, faces, uv


def rigid(name, bm, mat, frame, col):
    me = bpy.data.meshes.new(name)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    me.materials.append(mat)
    me.shade_smooth()
    ob = bpy.data.objects.new(name, me)
    col.objects.link(ob)
    ob.parent = frame
    return ob


def tube_bm(path, radii, segs=16, cap=True):
    """a swept tube through local points with per-point radii (frames by parallel transport)"""
    bm = bmesh.new()
    rings = []
    prev_n = None
    for i, (p, r) in enumerate(zip(path, radii)):
        t = (path[min(i + 1, len(path) - 1)] - path[max(i - 1, 0)]).normalized()
        if prev_n is None:
            prev_n = t.orthogonal().normalized()
        n = (prev_n - t * prev_n.dot(t)).normalized()
        prev_n = n
        b = t.cross(n)
        rings.append([bm.verts.new(p + (n * math.cos(a) + b * math.sin(a)) * r)
                      for a in (2 * math.pi * s / segs for s in range(segs))])
    for ra, rb in zip(rings, rings[1:]):
        for s in range(segs):
            bm.faces.new((ra[s], ra[(s + 1) % segs], rb[(s + 1) % segs], rb[s]))
    if cap:
        bm.faces.new(rings[0][::-1])
        bm.faces.new(rings[-1])
    return bm


def wing_bm(surf, side, frame_inv):
    """one flat wing of the cannula, bent to the arm: a rounded tab beside the hub, 0.8 mm thick"""
    bm = bmesh.new()
    pts = []
    for k in range(13):                                        # outline: x from the hub out, y along it
        a = math.pi * k / 12
        pts.append((side * (0.0035 + 0.0105 * math.sin(a) ** 0.6), -0.0105 + 0.0052 * math.cos(a)))
    pts = [(side * 0.0025, -0.0035)] + pts + [(side * 0.0025, -0.0175)]
    top, low = [], []
    for x, y in pts:
        p, n, w = surf.at(x, y)
        top.append(bm.verts.new(frame_inv @ (p + n * 0.0011)))
        low.append(bm.verts.new(frame_inv @ (p + n * 0.0003)))
    bm.faces.new(top if side > 0 else top[::-1])
    bm.faces.new(low[::-1] if side > 0 else low)
    m = len(pts)
    for i in range(m):
        a, b = i, (i + 1) % m
        bm.faces.new((low[a], low[b], top[b], top[a]) if side > 0 else (top[a], top[b], low[b], low[a]))
    return bm


# ---------------------------------------------------------------- build

def setup(rig, body, root, col, frame, cam_root):
    """build at `frame` (the catheter close-up); cam_root: the close-up camera (root-local). Returns a dict:
    frame (the empty the plastic rides on), tail (root-local tube points from the lift-off to the hub),
    hub_root (root-local point for the camera), mats to key."""
    scene = bpy.context.scene
    scene.frame_set(frame)
    dg = bpy.context.evaluated_depsgraph_get()
    skin = Skin(rig, body, dg)
    to_rig = rig.matrix_world.inverted() @ root.matrix_world
    surf = ArmSurface(skin, rig, to_rig @ cam_root)
    F = surf.frame
    Fi = F.inverted()
    side = 1.0 if (F.inverted().to_3x3() @ (to_rig @ cam_root - surf.p0)).x > 0 else -1.0    # loop toward the lens

    # the empty the rigid plastic rides on: vertex-parented to a skin-bound triangle round the insertion
    tri = skin_object('IV_Anchor', surf, [(-0.012, 0.010), (0.012, 0.010), (0.0, -0.016)], [(0, 1, 2)], 0.0,
                      plastic('IVAnchorHidden', (0, 0, 0), 1.0), col, rig)
    for attr in ('visible_camera', 'visible_shadow', 'visible_diffuse', 'visible_glossy', 'visible_transmission',
                 'visible_volume_scatter'):
        setattr(tri, attr, False)        # invisible, but still evaluated: the frame hangs off its vertices
    tri.display_type = 'WIRE'
    scene.frame_set(frame)
    fe = bpy.data.objects.new('IV_CatheterFrame', None)
    fe.empty_display_size = 0.01
    col.objects.link(fe)
    fe.parent = tri
    fe.parent_type = 'VERTEX_3'
    fe.parent_vertices = (0, 1, 2)
    # the matrix_world setter can't see the triangle's deformed vertices: read the parent matrix the depsgraph
    # solves (identity basis) and set the basis against it
    bpy.context.view_layer.update()
    pm = fe.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.copy()
    fe.matrix_basis = pm.inverted() @ rig.matrix_world @ F
    bpy.context.view_layer.update()
    err = (fe.evaluated_get(bpy.context.evaluated_depsgraph_get()).matrix_world.translation
           - rig.matrix_world @ F.translation).length
    assert err < 1e-4, ('catheter frame off by', err)

    # rigid parts in the frame (x across, y up the arm, z out of the skin; the cannula enters at the origin)
    hub_m = plastic('IVHubClear', (0.92, 0.93, 0.95), 0.35, 0.12)
    wing_m = plastic('IVWingOrange', (0.95, 0.47, 0.20), 1.0, 0.35)
    cap_m = plastic('IVCapOrange', (0.96, 0.45, 0.16), 1.0, 0.3)
    luer_m = plastic('IVLuer', (0.94, 0.94, 0.92), 0.75, 0.3)
    cann_m = plastic('IVCannula', (0.95, 0.80, 0.70), 0.6, 0.2)
    liq_m = plastic('IVHubLiquid', (0.55, 0.10, 0.03), 0.9, 0.05, emit=(1.0, 0.24, 0.05))
    V = Vector
    skin_z = lambda x, y: (Fi @ surf.at(x, y)[0]).z
    zf, zr = skin_z(0.0, -0.010) + 0.0025, skin_z(0.0, -0.031) + 0.0036      # hub axis: front / rear end
    zh = lambda y: zf + (zr - zf) * (-0.010 - y) / 0.021
    rigid('IV_Cannula', tube_bm([V((0, -0.0085, zh(-0.0085) - 0.0012)), V((0, 0.0, 0.0002)),
                                 V((0, 0.004, skin_z(0.0, 0.004) - 0.0014)), V((0, 0.011, skin_z(0.0, 0.011) - 0.0032))],
                                [0.00062, 0.00058, 0.00052, 0.00045], 10), cann_m, fe, col)
    hub_path = [V((0, -0.0085, zh(-0.0085) - 0.0011)), V((0, -0.010, zh(-0.010) - 0.0005)), V((0, -0.016, zh(-0.016))),
                V((0, -0.024, zh(-0.024))), V((0, -0.031, zh(-0.031)))]
    rigid('IV_Hub', tube_bm(hub_path, [0.0013, 0.0022, 0.0027, 0.0031, 0.0033], 20), hub_m, fe, col)
    rigid('IV_HubLiquid', tube_bm(hub_path[1:], [0.0012, 0.0016, 0.0019, 0.0021], 12), liq_m, fe, col)
    for s in (1, -1):
        rigid(f'IV_Wing{"R" if s > 0 else "L"}', wing_bm(surf, s, Fi), wing_m, fe, col)
    zp = zh(-0.0205)
    rigid('IV_Port', tube_bm([V((0, -0.0205, zp)), V((0, -0.0205, zp + 0.0047))], [0.0027, 0.0025], 18), hub_m, fe, col)
    rigid('IV_PortCap', tube_bm([V((0, -0.0205, zp + 0.0045)), V((0, -0.0205, zp + 0.0066))], [0.0036, 0.0035], 20),
          cap_m, fe, col)
    rigid('IV_CapHinge', tube_bm([V((0, -0.0245, zp + 0.0037)), V((0, -0.0275, zp + 0.0015)),
                                  V((0, -0.0285, zh(-0.0285) + 0.002))], [0.0012, 0.0011, 0.001], 8), cap_m, fe, col)
    zl = lambda y: zr + (zr - zf) * (-0.031 - y) / 0.021
    luer = [V((0, y, zl(y))) for y in (-0.031, -0.0335, -0.0345, -0.037, -0.0385, -0.0415)]
    rigid('IV_Luer', tube_bm(luer, [0.0034, 0.0036, 0.0033, 0.0036, 0.0033, 0.0026], 16), luer_m, fe, col)

    # the tube: out of the luer down the forearm in a slack S toward the lens, taped twice, then off the skin
    def on_skin(x, y, lift=0.0):
        p, n, w = surf.at(x, y)
        return p + n * (TUBE_R + 0.0005 + lift)
    loop_xy = [(side * 0.0015, -0.050), (side * 0.0065, -0.061), (side * 0.0105, -0.073), (side * 0.011, -0.086),
               (side * 0.009, -0.098)]
    tail_rig = [F @ luer[-1]] + [on_skin(x, y) for x, y in loop_xy] + \
               [on_skin(side * 0.008, LIFT_Y, 0.003), on_skin(side * 0.008, LIFT_Y - 0.016, 0.018)]
    from_rig = root.matrix_world.inverted() @ rig.matrix_world
    tail = [from_rig @ p for p in reversed(tail_rig)]          # in the tube's direction: lift-off .. luer

    # film dressing over the insertion and the wings, tented over the hub; tapes over the loop
    tube_bumps = [((x0, y0), (x1, y1), TUBE_R, 2 * TUBE_R + 0.0006) for (x0, y0), (x1, y1) in
                  zip([(0.0, -0.0415)] + loop_xy, loop_xy)]
    hub_bumps = [((0.0, -0.007), (0.0, -0.031), 0.0031, 0.0066), ((0.0, 0.002), (0.0, -0.008), 0.0008, 0.0025),
                 ((-0.0135, -0.0105), (0.0135, -0.0105), 0.0055, 0.0012)]
    luer_bump = [((0.0, -0.031), (0.0, -0.0415), 0.0036, 0.0075)]
    v, f, uv = grid(-0.0185, 0.0185, -0.017, 0.029, 38, 46)
    skin_object('IV_Film', surf, v, f, 0.0007, film_mat(), col, rig, uv, hub_bumps)
    tape = tape_mat()
    x0, x1 = sorted((-side * 0.013, side * 0.021))
    v, f, uv = grid(x0, x1, -0.058, -0.039, 44, 20)
    skin_object('IV_Tape1', surf, v, f, 0.0010, tape, col, rig, uv, tube_bumps + hub_bumps[:1] + luer_bump)
    x0, x1 = sorted((-side * 0.004, side * 0.025))
    v, f, uv = grid(x0, x1, -0.097, -0.079, 38, 20)
    skin_object('IV_Tape2', surf, v, f, 0.0010, tape, col, rig, uv, tube_bumps)

    # marks: a dot of blood at the insertion, an older yellow-green bruise, a fresh one, track marks up the vein
    v, f, uv = disc(0.0, 0.0006, 0.0018, 3, 16)
    skin_object('IV_Blood', surf, v, f, 0.0003, decal_mat('IVBloodDot', (0.32, 0.03, 0.02), (0.45, 0.08, 0.05), 0.85,
                                                             0.6), col, rig, uv)
    for nm, (cx, cy, r), inner, outer, a in (
            ('IV_Bruise1', (-side * 0.004, 0.044, 0.011), (0.33, 0.20, 0.32), (0.55, 0.45, 0.30), 0.55),
            ('IV_Bruise2', (-side * 0.019, -0.068, 0.009), (0.55, 0.50, 0.25), (0.62, 0.52, 0.38), 0.4)):
        v, f, uv = disc(cx, cy, r, 6, 28)
        skin_object(nm, surf, v, f, 0.00035 if nm.endswith('1') else 0.0004, decal_mat(nm.replace('IV_', 'IV'), inner, outer, a), col, rig, uv)
    marks = decal_mat('IVTrackMark', (0.28, 0.06, 0.05), (0.45, 0.22, 0.18), 0.8, 0.7)
    for k, (cx, cy) in enumerate(((0.0015, 0.050), (-0.0025, 0.061), (0.003, 0.069), (-0.001, 0.078))):
        v, f, uv = disc(cx, cy, 0.0011, 3, 12)
        skin_object(f'IV_Mark{k}', surf, v, f, 0.00045, marks, col, rig, uv)

    # the vein the drug climbs: a wandering strip from the cannula tip up through the crook
    nx, ny = 4, 52
    verts, uvs, faces = [], [], []
    for j in range(ny + 1):
        yy = 0.010 + 0.062 * j / ny
        cx = 0.0018 * math.sin(yy * 70) - 0.0012 * math.sin(yy * 170)
        for i in range(nx + 1):
            verts.append((cx + (i / nx - 0.5) * 0.0055, yy))
            uvs.append((i / nx, j / ny))
    for j in range(ny):
        for i in range(nx):
            a = j * (nx + 1) + i
            faces.append((a, a + 1, a + nx + 2, a + nx + 1))
    vein = skin_object('IV_VeinGlow', surf, verts, faces, 0.0005, vein_mat(), col, rig, uvs)
    for ob in col.objects:
        if ob.name.startswith(('IV_Film', 'IV_Blood', 'IV_Bruise', 'IV_Mark', 'IV_VeinGlow')):
            ob.visible_shadow = False
    return dict(frame=fe, tail=tail, hub_root=from_rig @ (F @ HUB_C), hub_rig=F @ HUB_C, skin=skin,
                hub_liquid=liq_m, vein=vein.data.materials[0])


def bind_tube(ob, cath, rig, on=0.0065, off=0.04, reach=(0.16, 0.30)):
    """the IV tube rides on the arm where it lies on it: each vertex near the skin takes the skin's weights at the
    closest skin point, fully within `on` of the skin, fading out by `off` (the modifier's mask group), and only
    within `reach` of the hub. Rest positions are solved from the pose the catheter was built at, so call this with
    the tube in its built place; the skin's pose is the one stored in cath['skin']."""
    skin = cath['skin']
    bpy.context.view_layer.update()     # a just-parented object's matrix_world is stale till then (the liquid stayed unbound)
    to_rig = rig.matrix_world.inverted() @ ob.matrix_world
    from_rig = to_rig.inverted()
    mask = ob.vertex_groups.new(name='IVSkin')
    groups = {}
    smooth = lambda u: u * u * (3 - 2 * u)
    for v in ob.data.vertices:
        p = to_rig @ v.co
        k = smooth(min(1.0, max(0.0, (reach[1] - (p - cath['hub_rig']).length) / (reach[1] - reach[0]))))
        if k <= 0:
            continue
        q, n, w, d = skin.nearest(p)
        k *= smooth(min(1.0, max(0.0, (off - d) / (off - on))))
        if k <= 1e-3:
            continue
        v.co = from_rig @ skin.unpose(p, w, k)
        mask.add([v.index], k, 'REPLACE')
        for b, x in w.items():
            if x >= 1e-3:
                if b not in groups:
                    groups[b] = ob.vertex_groups.new(name=b)
                groups[b].add([v.index], x, 'REPLACE')
    md = ob.modifiers.new('IVSkin', 'ARMATURE')
    md.object = rig
    md.vertex_group = 'IVSkin'
    return md
