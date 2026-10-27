"""Real hair for the typist: ~95k strands as a hair Curves object riding on the head bone (the scalp moves rigidly
with it). Built at the rest pose on the body as it renders (shape keys on): roots scattered over the 'scalp' group
the MakeHuman cap left, guide strands grown out from a crown whorl, combed down the head by gravity and hugging it a
few millimetres up, falling free once they pass the hairline; the other strands clump onto the guides like
unwashed hair, a few fly away. Replaces the cap mesh and the particle strands.
build_scene calls build() once the human is in."""
import bpy, math, random
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree
from mathutils.kdtree import KDTree
from lib_build import srgb, new_mat

HEAD = 'mixamorig:Head'
N_GUIDE, N_CHILD, PTS = 3000, 92000, 12
R_ROOT, R_TIP = 0.00006, 0.000024
SHADOW_STRIDE, SHADOW_RMUL = 6, 2.5       # EEVEE's shadow-only stand-in: every 6th strand, thicker


def smooth(a, b, x):
    u = min(1.0, max(0.0, (x - a) / (b - a)))
    return u * u * (3 - 2 * u)


class Scalp:
    """the body at the rest pose in armature space: BVH over its triangles, smooth normals, the scalp weight"""
    def __init__(self, rig, body):
        rig.data.pose_position = 'REST'
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        masks = [(body.vertex_groups[m.vertex_group].index, m.invert_vertex_group, m.threshold)
                 for m in body.modifiers if m.type == 'MASK' and m.show_viewport]
        gs = body.vertex_groups['scalp'].index
        orig_w = []
        for v in body.data.vertices:
            w = {g.group: g.weight for g in v.groups}
            if all((w.get(gi, 0.0) > th) != iv for gi, iv, th in masks):
                orig_w.append(w.get(gs, 0.0))
        ev = body.evaluated_get(dg)
        me = ev.to_mesh()
        assert len(me.vertices) == len(orig_w), (len(me.vertices), len(orig_w))
        to_arm = rig.matrix_world.inverted() @ body.matrix_world
        R = to_arm.to_3x3()
        self.co = [to_arm @ v.co for v in me.vertices]
        self.no = [(R @ v.normal).normalized() for v in me.vertices]
        me.calc_loop_triangles()
        self.tris = [tuple(t.vertices) for t in me.loop_triangles]
        ev.to_mesh_clear()
        inv = rig.matrix_world.inverted()
        self.eye = Vector()
        for n in ('Lens_L', 'Lens_R'):                               # lens centres: where the eyes are
            lo = bpy.data.objects[n]
            self.eye += inv @ lo.matrix_world @ (sum((Vector(c) for c in lo.bound_box), Vector()) / 8) / 2
        rig.data.pose_position = 'POSE'
        bpy.context.view_layer.update()
        self.w = orig_w
        self.bvh = BVHTree.FromPolygons(self.co, self.tris)

    def weight(self, fi):
        a, b, c = self.tris[fi]
        return (self.w[a] + self.w[b] + self.w[c]) / 3

    def nearest(self, p):
        hit, n, fi, d = self.bvh.find_nearest(p)
        a, b, c = self.tris[fi]
        nn = (self.no[a] + self.no[b] + self.no[c]).normalized()
        return hit, nn, fi

    def roots(self, n, rng):
        """n points over the scalp, denser where the weight is high (a thinning hairline): (point, normal)"""
        cum, tot = [], 0.0
        for a, b, c in self.tris:
            w = (self.w[a] + self.w[b] + self.w[c]) / 3
            if w > 0.05:
                tot += ((self.co[b] - self.co[a]).cross(self.co[c] - self.co[a])).length * 0.5 * w ** 1.3
            cum.append(tot)
        out = []
        for i in rng.choices(range(len(self.tris)), cum_weights=cum, k=n):
            a, b, c = self.tris[i]
            r1, r2 = rng.random(), rng.random()
            s = math.sqrt(r1)
            u, v, w = 1 - s, s * (1 - r2), s * r2
            p = self.co[a] * u + self.co[b] * v + self.co[c] * w
            nn = (self.no[a] * u + self.no[b] * v + self.no[c] * w).normalized()
            out.append((p, nn))
        return out


def hair_mat():
    """dark brown, greasy and a little dusty: Principled Hair (Chiang) in Cycles, a Principled stand-in in EEVEE"""
    m, nt = new_mat('HairStrandsReal')
    if nt is None:
        return m
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    hb = nt.nodes.new('ShaderNodeBsdfHairPrincipled')
    hb.model, hb.parametrization = 'CHIANG', 'MELANIN'
    for k, v in (('Melanin', 0.92), ('Melanin Redness', 0.25), ('Roughness', 0.28), ('Radial Roughness', 0.35),
                 ('Coat', 0.12), ('IOR', 1.55), ('Random Color', 0.18), ('Random Roughness', 0.25)):
        hb.inputs[k].default_value = v
    hb.inputs['Tint'].default_value = srgb((0.88, 0.84, 0.78))
    oc = nt.nodes.new('ShaderNodeOutputMaterial')
    oc.target = 'CYCLES'
    nt.links.new(hb.outputs[0], oc.inputs['Surface'])
    info = nt.nodes.new('ShaderNodeHairInfo')
    ramp = nt.nodes.new('ShaderNodeValToRGB')
    ramp.color_ramp.elements[0].color = srgb((0.030, 0.022, 0.016))
    ramp.color_ramp.elements[1].color = srgb((0.095, 0.072, 0.055))
    nt.links.new(info.outputs['Intercept'], ramp.inputs['Fac'])
    var = nt.nodes.new('ShaderNodeMapRange')
    var.inputs['To Min'].default_value, var.inputs['To Max'].default_value = 0.7, 1.3
    nt.links.new(info.outputs['Random'], var.inputs['Value'])
    sc = nt.nodes.new('ShaderNodeVectorMath')
    sc.operation = 'SCALE'
    nt.links.new(ramp.outputs['Color'], sc.inputs[0])
    nt.links.new(var.outputs[0], sc.inputs['Scale'])
    pb = nt.nodes.new('ShaderNodeBsdfPrincipled')
    nt.links.new(sc.outputs[0], pb.inputs['Base Color'])
    pb.inputs['Roughness'].default_value = 0.55
    pb.inputs['Specular IOR Level'].default_value = 0.3
    oe = nt.nodes.new('ShaderNodeOutputMaterial')
    oe.target = 'EEVEE'
    nt.links.new(pb.outputs[0], oe.inputs['Surface'])
    return m


def build(rig, body, col, seed=7):
    rng = random.Random(seed)
    sc = Scalp(rig, body)
    bone = rig.data.bones[HEAD]
    U = Vector((0, 0, 1))
    hc = bone.head_local.lerp(bone.tail_local, 0.55)                 # middle of the skull
    F = sc.eye - hc
    F.z = 0.0
    F.normalize()                                                    # the way the face looks
    X = F.cross(U)
    whorl = sc.nearest(hc + U * 0.09 - F * 0.05)[0]
    brow_z = sc.eye.z + 0.024
    print(f'HAIR eye {sc.eye} brow {brow_z:.3f} face {F}')

    def face(p, lift):
        """in front of the face below the brows (lower at the temples, where sideburns may go)"""
        r = p - hc
        return r.dot(F) > 0.05 and p.z < brow_z + lift - 0.032 * smooth(0.035, 0.065, abs(r.dot(X)))

    def trim(pts):
        """cut a strand where it would hang into the face and spread its points over what is left"""
        lift = rng.uniform(-0.004, 0.004)
        cum = [0.0]
        for k in range(1, PTS):
            cum.append(cum[-1] + (pts[k] - pts[k - 1]).length)
        end = cum[-1]
        for k in range(1, PTS):
            if face(pts[k], lift):
                lo, hi = 0.0, 1.0
                for _ in range(8):
                    m = (lo + hi) / 2
                    lo, hi = (lo, m) if face(pts[k - 1].lerp(pts[k], m), lift) else (m, hi)
                end = max(0.006, cum[k - 1] + lo * (cum[k] - cum[k - 1]))
                break
        if end >= cum[-1]:
            return pts
        out, j = [], 0
        for i in range(PTS):
            s_ = end * i / (PTS - 1)
            while j < PTS - 2 and cum[j + 1] < s_:
                j += 1
            f = (s_ - cum[j]) / max(1e-9, cum[j + 1] - cum[j])
            out.append(pts[j].lerp(pts[j + 1], min(1.0, f)))
        return out

    def grow(root, n0):
        rel = root - hc
        zr, fr = rel.dot(U), rel.dot(F)
        L = (0.032 + 0.05 * smooth(-0.02, 0.07, zr)) * rng.uniform(0.6, 1.2)
        if fr < -0.02 and zr < 0.02:
            L = min(L, rng.uniform(0.028, 0.042))                    # short at the nape
        Hs = 0.0015 + 0.008 * rng.random() ** 1.5 * smooth(-0.03, 0.06, zr)
        d = root - whorl
        d -= n0 * d.dot(n0)
        dist = d.length
        d = d.normalized() if dist > 1e-4 else F.copy()
        d = Matrix.Rotation(0.9 * math.exp(-dist / 0.03) + rng.gauss(0, 0.3), 3, n0) @ d     # swirl + mess
        flick = rng.gauss(0, 0.35)                                   # the end kicks out or round a little
        seg = L / (PTS - 1)
        pts = [root - n0 * 0.0008]
        p, n, free = root, n0, False
        for k in range(1, PTS):
            t = k / (PTS - 1)
            d = d - U * (0.08 + 0.3 * t) + Vector((rng.gauss(0, 0.05), rng.gauss(0, 0.05), rng.gauss(0, 0.05)))
            if not free:
                d -= n * d.dot(n)
            if t > 0.6:
                d = Matrix.Rotation(flick * (t - 0.6), 3, n.cross(d)) @ d
            d.normalize()
            q = p + d * seg
            hit, nn, fi = sc.nearest(q)
            h = 0.0006 + Hs * (1 - (1 - t) ** 2)
            if not free and sc.weight(fi) < 0.12:
                free = True                                          # past the hairline: the end hangs free
            if not free:
                q = hit + nn * h
                n = nn
            elif (q - hit).dot(nn) < 0.5 * h:
                q = hit + nn * 0.5 * h
            pts.append(q)
            p = q
        return pts

    guides = [grow(p, n) for p, n in sc.roots(N_GUIDE, rng)]
    clump = [rng.uniform(0.45, 0.85) for _ in guides]
    kd = KDTree(len(guides))
    for i, g in enumerate(guides):
        kd.insert(g[0], i)
    kd.balance()
    strands = list(guides)
    for r, n0 in sc.roots(N_CHILD, rng):
        gi = kd.find(r)[1]
        G = guides[gi]
        off = r - n0 * 0.0008 - G[0]
        cl, lenf = clump[gi], rng.uniform(0.75, 1.04)
        a = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))) * 0.0009
        b = Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))) * 0.0006
        ph = rng.uniform(0, 6.28)
        fly = rng.random() < 0.03
        lift = (n0 * 0.006 + Vector((rng.gauss(0, 1), rng.gauss(0, 1), rng.gauss(0, 1))) * 0.003) if fly else None
        pts = []
        for k in range(PTS):
            t = k / (PTS - 1)
            u = t * lenf * (PTS - 1)
            i0 = min(int(u), PTS - 2)
            p = G[i0].lerp(G[i0 + 1], u - i0) + off * (1 - cl * t ** 1.3) + (a * math.sin(t * 4.1 + ph) + b) * t
            if lift is not None:
                p += lift * t * t
            if k:
                hit, nn, fi = sc.nearest(p)
                if (p - hit).dot(nn) < 0.0004:
                    p = hit + nn * 0.0004
            pts.append(p)
        strands.append(pts)

    strands = [trim(p) for p in strands]
    hcd = bpy.data.hair_curves.new('HairCurves')
    hcd.add_curves([PTS] * len(strands))
    flat, rad = [], []
    for pts in strands:
        for k, p in enumerate(pts):
            flat += p[:]
            rad.append(R_ROOT + (R_TIP - R_ROOT) * k / (PTS - 1))
    hcd.position_data.foreach_set('vector', flat)
    ra = hcd.attributes.get('radius') or hcd.attributes.new('radius', 'FLOAT', 'POINT')
    ra.data.foreach_set('value', rad)
    mat = hair_mat()
    hcd.materials.append(mat)
    ob = bpy.data.objects.new('HairCurves', hcd)

    # EEVEE redraws the shadow maps of six monitor lights every sample, and all 95k strands in them cost ~35 s a
    # frame: there the full hair casts none and every 6th strand, 2.5x thicker and invisible, casts them instead
    # (looks the same, ~3 s). cycles_setup.use_cycles swaps back to the full hair's own shadows.
    pcd = bpy.data.hair_curves.new('HairShadowProxy')
    keep = range(0, len(strands), SHADOW_STRIDE)
    pcd.add_curves([PTS] * len(keep))
    pcd.position_data.foreach_set('vector', [c for i in keep for c in flat[i * PTS * 3:(i + 1) * PTS * 3]])
    pcd.attributes.new('radius', 'FLOAT', 'POINT').data.foreach_set(
        'value', [r * SHADOW_RMUL for i in keep for r in rad[i * PTS:(i + 1) * PTS]])
    pcd.materials.append(mat)
    proxy = bpy.data.objects.new('HairShadowProxy', pcd)
    proxy.visible_camera = False
    ob.visible_shadow = False
    for o in (ob, proxy):
        col.objects.link(o)
        o.parent = rig
        o.parent_type = 'BONE'
        o.parent_bone = HEAD
        o.matrix_parent_inverse = (bone.matrix_local @ Matrix.Translation((0, bone.length, 0))).inverted()
        o.matrix_basis = Matrix.Identity(4)

    # the old cap and particle strands go
    for m in body.modifiers:
        if m.type == 'PARTICLE_SYSTEM' and m.name == 'HairStrands':
            m.show_render = m.show_viewport = False
    cap = bpy.data.objects.get('Hair')
    if cap:
        cap.hide_render = cap.hide_viewport = True
    return ob
