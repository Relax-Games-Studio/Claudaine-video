"""The basement workstation, built in DESK_ROOT local space (floor under the seat centre, person faces +Y):
desk, six monitors on a pole mount, keyboard, mouse, gaming chair, syringes, glowing puddles, IV stand, junk."""
import bpy, bmesh, math, random
from mathutils import Vector, Matrix, Euler
from lib_build import *
import keyboard_layout as KL

RNG = random.Random(11)
# The human (human.blend, Typing pose) is placed at HUMAN_OFFSET so its home-row fingertips land on the
# keyboard and its back clears the chair; EYE / ELBOW_L are human_report.json values shifted by it.
HUMAN_OFFSET = Vector((0.0, 0.05, -0.033))
EYE = Vector((-0.052, 0.059, 1.2815)) + HUMAN_OFFSET
ELBOW_L = Vector((-0.2825, 0.061, 0.934)) + HUMAN_OFFSET
ELBOW_L_N = Vector((0.6186, 0.7139, 0.3281))
SEAT_DROP = 0.065                     # chair seat lowered so its top meets the human's seat contact
DESK_TOP = 0.76
DESK_FRONT = 0.35
DESK_DEPTH = 0.8
# the half-full syringe by the keyboard, lying with its needle out over the front edge (drop.py drips from its tip)
SYR_DESK_LOC = Vector((-0.415, DESK_FRONT + 0.0235, DESK_TOP + 0.0085))
SYR_DESK_YAW = math.radians(196)
SYR_NEEDLE_TIP = 0.041           # barrel mouth to needle point, along the syringe's -Z
DESK_W = 2.4
SCREEN_W, SCREEN_H = 0.597, 0.336
# keyboard frame: origin on the plate under the centre of the F key (under the left index finger), tilted 3 deg;
# its front feet stand on the desk mat (top at DESK_TOP + 0.003)
KEYBOARD = Vector((-0.158, 0.52, 0.7776))
KB_TILT = math.radians(3)
MOUSE = Vector((0.312, 0.565, DESK_TOP + 0.0031))   # mouse home: centre of its footprint on the mat, pointing +Y
MOUSE_SCALE = 1.15          # the MPFB hand is large: a big gaming mouse (140 x 76 x 45 mm) sits under it right
IV_BASE = Vector((-0.8, 1.4, 0.0))


# ---------------------------------------------------------------- materials

def leather(name, color, rough=0.42):
    m, nt = new_mat(name)
    if nt is None:
        return m
    b, out = principled(nt)
    b.inputs['Base Color'].default_value = srgb(color)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Coat Weight'].default_value = 0.15
    b.inputs['Sheen Weight'].default_value = 0.2
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 400
    nz.inputs['Detail'].default_value = 4
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.15
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    return m


def glow_liquid(name='GlowLiquid', strength=7.0, mottle=0.0):
    """Fluorescent Claude-orange liquid: emissive, glossy, slightly brighter at grazing angles.
    Emission stays deeply saturated: AgX bleaches anything much brighter than ~1 to pastel.
    mottle > 0 breaks the emission up with noise (thin film vs. pooled liquid)."""
    m, nt = new_mat(name)
    if nt is None:
        return m
    b, out = principled(nt)
    b.inputs['Base Color'].default_value = (0.35, 0.06, 0.015, 1) if not mottle else (0.03, 0.006, 0.002, 1)
    b.inputs['Roughness'].default_value = 0.04
    b.inputs['Coat Weight'].default_value = 0.8 if not mottle else 0.25
    b.inputs['Coat Roughness'].default_value = 0.02
    b.inputs['Emission Color'].default_value = (1.0, 0.22, 0.045, 1) if not mottle else (1.0, 0.17, 0.03, 1)
    lw = nt.nodes.new('ShaderNodeLayerWeight')
    lw.inputs['Blend'].default_value = 0.4
    mth = nt.nodes.new('ShaderNodeMath')
    mth.operation = 'MULTIPLY_ADD'
    mth.inputs[1].default_value = strength * 0.8
    mth.inputs[2].default_value = strength * 0.6
    nt.links.new(lw.outputs['Facing'], mth.inputs[0])
    if mottle:
        tc = nt.nodes.new('ShaderNodeTexCoord')
        nz = nt.nodes.new('ShaderNodeTexNoise')
        nz.inputs['Scale'].default_value = 14.0
        nz.inputs['Detail'].default_value = 3.0
        mr = nt.nodes.new('ShaderNodeMapRange')
        mr.inputs['From Min'].default_value = 0.35
        mr.inputs['From Max'].default_value = 0.65
        mr.inputs['To Min'].default_value = 1.0 - mottle
        mr.inputs['To Max'].default_value = 1.0
        mul = nt.nodes.new('ShaderNodeMath')
        mul.operation = 'MULTIPLY'
        nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
        nt.links.new(nz.outputs['Fac'], mr.inputs['Value'])
        # 'thick' (per-vertex, 0 at the rim .. 1 in the pool) dims the thin meniscus edge
        th = nt.nodes.new('ShaderNodeAttribute')
        th.attribute_name = 'thick'
        mul2 = nt.nodes.new('ShaderNodeMath')
        mul2.operation = 'MULTIPLY'
        nt.links.new(mth.outputs[0], mul.inputs[0])
        nt.links.new(mr.outputs[0], mul.inputs[1])
        nt.links.new(mul.outputs[0], mul2.inputs[0])
        nt.links.new(th.outputs['Fac'], mul2.inputs[1])
        nt.links.new(mul2.outputs[0], b.inputs['Emission Strength'])
    else:
        nt.links.new(mth.outputs[0], b.inputs['Emission Strength'])
    return m


def mats():
    M = {}
    M['leather'] = leather('ChairLeather', (0.025, 0.025, 0.028))
    M['leather_or'] = leather('ChairOrange', ORANGE, 0.6)
    M['chair_base'] = flat('ChairBase', (0.02, 0.02, 0.02), rough=0.3, metal=0.6)
    M['caster'] = flat('Caster', (0.01, 0.01, 0.01), rough=0.5)
    M['chrome'] = flat('Chrome', (0.8, 0.8, 0.8), rough=0.12, metal=1.0)
    M['desk'] = grunge(flat('DeskTop', (0.03, 0.03, 0.032), rough=0.32, coat=0.3), 0.5, 18.0, 0.55)
    M['desk_leg'] = flat('DeskLeg', (0.02, 0.02, 0.02), rough=0.35, metal=0.8)
    M['mat'] = grunge(flat('DeskMat', (0.02, 0.02, 0.022), rough=0.85), 0.6, 9.0, 0.5)
    M['mon'] = flat('MonitorPlastic', (0.012, 0.012, 0.013), rough=0.38)
    M['mon_back'] = flat('MonitorBack', (0.02, 0.02, 0.022), rough=0.55)
    M['pole'] = flat('PoleMount', (0.05, 0.05, 0.055), rough=0.3, metal=0.9)
    M['key'] = flat('Keycap', (0.02, 0.02, 0.022), rough=0.55)
    M['key_or'] = flat('KeycapOrange', ORANGE, rough=0.5)
    M['kb_glow'] = emission_mat('KeyboardUnderglow', ORANGE, 2.0)
    M['kb_case'] = flat('KeyboardCase', (0.03, 0.03, 0.03), rough=0.3, metal=0.7)
    M['syr_glass'] = flat('SyringeBarrel', (0.92, 0.93, 0.95), rough=0.06, spec=0.9, alpha=0.2)
    M['rubber'] = flat('Rubber', (0.01, 0.01, 0.01), rough=0.6)
    M['needle'] = flat('Needle', (0.85, 0.85, 0.86), rough=0.15, metal=1.0)
    M['hub'] = flat('NeedleHub', (0.85, 0.42, 0.25), rough=0.3, alpha=0.7)
    M['plunger'] = flat('PlungerPlastic', (0.9, 0.9, 0.88), rough=0.35, alpha=0.75)
    M['liquid'] = glow_liquid('GlowLiquid', 0.35)
    M['puddle'] = glow_liquid('GlowPuddle', 0.2, mottle=0.35)
    M['bag'] = flat('IVBag', (0.95, 0.95, 0.96), rough=0.15, spec=0.8, alpha=0.25)
    M['tube'] = flat('IVTube', (0.95, 0.95, 0.96), rough=0.1, spec=0.8, alpha=0.3)
    M['tape'] = flat('MedicalTapeSkin', (0.85, 0.82, 0.75), rough=0.8)
    M['cable'] = flat('Cable', (0.01, 0.01, 0.01), rough=0.45)
    M['can_a'] = flat('CanPaintA', (0.05, 0.05, 0.05), rough=0.25, metal=0.9)
    M['can_b'] = flat('CanPaintB', (0.70, 0.75, 0.80), rough=0.2, metal=1.0)
    M['can_c'] = flat('CanPaintC', ORANGE, rough=0.25, metal=0.8)
    M['cardboard'] = grunge(flat('PizzaBox', (0.55, 0.42, 0.28), rough=0.85), 0.7, 6.0, 0.45)
    M['screen'] = emission_mat('ScreenPlaceholder', (0.35, 0.40, 0.45), 1.0)
    return M


# ---------------------------------------------------------------- helpers

class Builder:
    def __init__(self, root, col):
        self.root, self.col = root, col

    def adopt(self, ob, parent=None):
        ob.parent = parent or self.root
        return ob

    def box(self, name, size, loc, mat, rot=(0, 0, 0), bevel=0.0, subsurf=0, parent=None):
        ob = box(name, size, loc, self.col, mat, rot)
        if bevel:
            m = bev(ob, bevel, 3)
            m.limit_method = 'NONE'
        if subsurf:
            s = ob.modifiers.new('Subsurf', 'SUBSURF')
            s.levels = s.render_levels = subsurf
        if bevel or subsurf:
            ob.data.shade_smooth()
        return self.adopt(ob, parent)

    def cyl(self, name, r, h, loc, mat, rot=(0, 0, 0), seg=24, r2=None, bottom=False, parent=None):
        ob = cyl(name, r, h, loc, self.col, mat, rot, seg, r2, bottom)
        return self.adopt(ob, parent)

    def sphere(self, name, r, loc, mat, scale=(1, 1, 1), seg=24, parent=None):
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=r)
        bmesh.ops.scale(bm, vec=scale, verts=bm.verts)
        ob = obj_from_bm(name, bm, self.col, [mat], loc, smooth=True)
        return self.adopt(ob, parent)

    def empty(self, name, loc=(0, 0, 0), rot=(0, 0, 0), parent=None):
        e = bpy.data.objects.new(name, None)
        e.empty_display_size = 0.1
        self.col.objects.link(e)
        e.location, e.rotation_euler = loc, rot
        return self.adopt(e, parent)

    def curve(self, name, pts, r, mat, parent=None, res=12, handles='AUTO'):
        cu = bpy.data.curves.new(name, 'CURVE')
        cu.dimensions = '3D'
        cu.bevel_depth = r
        cu.bevel_resolution = 3
        cu.resolution_u = res
        cu.use_fill_caps = True
        sp = cu.splines.new('BEZIER')
        sp.bezier_points.add(len(pts) - 1)
        for bp, p in zip(sp.bezier_points, pts):
            bp.co = p
            bp.handle_left_type = bp.handle_right_type = handles
        cu.materials.append(mat)
        ob = bpy.data.objects.new(name, cu)
        self.col.objects.link(ob)
        return self.adopt(ob, parent)


# ---------------------------------------------------------------- desk + monitors + peripherals

def monitor_layout():
    """[(index, centre, euler)] for the 6 monitors. Numbering per SPEC: 1-3 bottom L-C-R, 4-6 top L-C-R."""
    out = []
    phi = math.radians(32)
    yc = EYE.y + 0.85
    hw = SCREEN_W / 2 + 0.012
    for row, zc in ((0, 1.0), (1, 1.0 + SCREEN_H + 0.05)):
        beta = -math.atan2(EYE.z - zc, 0.85)          # tilt so the screen faces the eye
        for c, side in ((0, -1), (1, 0), (2, 1)):
            if side == 0:
                ctr, alpha = Vector((0, yc, zc)), 0.0
            else:
                ctr = Vector((side * (hw + 0.006 + hw * math.cos(phi)), yc - hw * math.sin(phi), zc))
                alpha = -side * phi
            out.append((row * 3 + c + 1, ctr, Euler((beta, 0, alpha))))
    return out


def build_desk(B, M):
    top = B.box('Desk_Top', (DESK_W, DESK_DEPTH, 0.035), (0, DESK_FRONT + DESK_DEPTH / 2, DESK_TOP - 0.0175), M['desk'], bevel=0.004)
    for sx in (-1, 1):
        x = sx * (DESK_W / 2 - 0.12)
        B.box(f'Desk_Leg_{sx}', (0.06, 0.06, DESK_TOP - 0.035), (x, DESK_FRONT + 0.4, (DESK_TOP - 0.035) / 2), M['desk_leg'])
        B.box(f'Desk_Foot_{sx}', (0.07, 0.7, 0.03), (x, DESK_FRONT + 0.4, 0.015), M['desk_leg'])
    B.box('Desk_Crossbar', (DESK_W - 0.24, 0.04, 0.06), (0, DESK_FRONT + 0.72, DESK_TOP - 0.1), M['desk_leg'])
    B.box('Desk_Mat', (0.95, 0.42, 0.003), (0.12, 0.57, DESK_TOP + 0.0015), M['mat'], bevel=0.002)


def build_monitors(B, M):
    screens = {}
    pole_x, pole_y = 0.0, DESK_FRONT + DESK_DEPTH - 0.06
    B.cyl('Pole', 0.022, 1.0, (pole_x, pole_y, DESK_TOP), M['pole'], bottom=True)
    B.box('Pole_Clamp', (0.08, 0.1, 0.06), (pole_x, pole_y + 0.01, DESK_TOP - 0.03), M['pole'])
    for idx, ctr, eul in monitor_layout():
        mon = B.empty(f'Monitor{idx}', ctr, eul)
        bz = 0.009
        B.box(f'Monitor{idx}_Bezel', (SCREEN_W + 2 * bz, 0.016, SCREEN_H + 2 * bz + 0.006), (0, 0.008, -0.003), M['mon'], bevel=0.002, parent=mon)
        B.box(f'Monitor{idx}_Back', (SCREEN_W * 0.8, 0.03, SCREEN_H * 0.75), (0, 0.03, -0.01), M['mon_back'], bevel=0.012, parent=mon)
        B.box(f'Monitor{idx}_Vesa', (0.11, 0.025, 0.11), (0, 0.055, 0), M['pole'], parent=mon)
        bm = bmesh.new()
        bmesh.ops.create_grid(bm, x_segments=1, y_segments=1, size=0.5)
        bmesh.ops.scale(bm, vec=(SCREEN_W, SCREEN_H, 1), verts=bm.verts)
        bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'X'), verts=bm.verts)
        me = bpy.data.meshes.new(f'Screen{idx}')
        bm.to_mesh(me)
        bm.free()
        uv = me.uv_layers.new(name='UVMap')
        for li, l in enumerate(me.loops):
            co = me.vertices[l.vertex_index].co
            uv.data[li].uv = (co.x / SCREEN_W + 0.5, co.z / SCREEN_H + 0.5)
        me.materials.append(M['screen'])
        scr = bpy.data.objects.new(f'Screen{idx}', me)
        B.col.objects.link(scr)
        scr.location = (0, -0.0006, 0)
        B.adopt(scr, mon)
        screens[idx] = scr
        # arm from the monitor back to the pole
        bpy.context.view_layer.update()
        a = mon.matrix_local @ Vector((0, 0.07, 0))
        b = Vector((pole_x, pole_y, ctr.z))
        d = b - a
        B.cyl(f'Monitor{idx}_Arm', 0.012, d.length, (a + b) / 2, M['pole'],
              d.to_track_quat('Z', 'Y').to_euler(), 12)
    return screens


def rrect(hx, hy, r, kx, ky, cs=4):
    """Rounded-rectangle outline (CCW seen from +Z): corners of radius r, straight sides split into kx (along X)
    / ky (along Y) spans. The point count depends only on (kx, ky, cs), so rings of one shape can be bridged."""
    r = min(r, hx * 0.999, hy * 0.999)
    corners = ((hx - r, hy - r, 0), (-hx + r, hy - r, 90), (-hx + r, -hy + r, 180), (hx - r, -hy + r, 270))
    pts = []
    for i, (cx, cy, a0) in enumerate(corners):
        for j in range(cs + 1):
            a = math.radians(a0 + 90 * j / cs)
            pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
        nx, ny, na = corners[(i + 1) % 4]
        p0, p1 = pts[-1], (nx + r * math.cos(math.radians(na)), ny + r * math.sin(math.radians(na)))
        k = kx if i % 2 == 0 else ky
        for m in range(1, k):
            pts.append((p0[0] + (p1[0] - p0[0]) * m / k, p0[1] + (p1[1] - p0[1]) * m / k))
    return pts


def bridge(bm, a, b):
    """quads between two equal-length closed vertex rings (a below / outside b, both CCW)"""
    n = len(a)
    return [bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i])) for i in range(n)]


def bm_box(bm, size, loc):
    vs = bmesh.ops.create_cube(bm, size=1.0)['verts']
    bmesh.ops.scale(bm, vec=size, verts=vs)
    bmesh.ops.translate(bm, vec=loc, verts=vs)


def socket(node, name, kind):
    return next(s for s in node.inputs if s.name == name and s.type == kind)


CAP_Z0, CAP_H, CAP_DISH = 0.0035, 0.0065, 0.0007     # switch housing showing under the cap, cap height, dish depth
ROW_DZ = (0.0006, 0.0005, 0.0002, 0.0, 0.0001, 0.0003)   # sculpted rows (F row .. space row)
ROW_SLOPE = (0.10, 0.09, 0.04, 0.0, -0.03, -0.05)        # top-face tilt dz/dy per row
ACCENT_KEYS = {'Esc', 'Enter'}                            # orange caps (the main Enter only, not the numpad one)


def key_centre(i):
    """centre of key i on the plate, keyboard frame (origin under the F key)"""
    lab, x, r, w, h = KL.KEYS[i]
    yc = KL.row_y(r) - (h - 1) / 2
    return Vector(((x + w / 2 - KL.HOME_F[0]) * KL.U, (yc - KL.row_y(KL.HOME_F[1])) * KL.U, 0.0))


def keycap(bm, uvl, i, mat_index):
    """One sculpted cap: rounded skirt, tapered wall, filleted edge and a cylindrically dished, row-tilted top
    whose UVs land on the key's legend in the atlas (walls sample the legend's empty border)."""
    lab, kx, row, w, h = KL.KEYS[i]
    c = key_centre(i)
    bx, by = (w * KL.U - KL.CAP_GAP) / 2, (h * KL.U - KL.CAP_GAP) / 2
    tx, ty = KL.top_half(w, h)
    zc, slope = CAP_Z0 + CAP_H + ROW_DZ[row], ROW_SLOPE[row]
    across_x = w <= 1.5 or h > 1          # dish curves across the width; front-to-back on long keys

    def top_z(x, y):
        u = x / tx if across_x else y / ty
        return zc - CAP_DISH * max(0.0, 1 - u * u) + slope * y

    nx, ny = max(2, round(w * 3)), max(2, round(h * 3))
    F, T, s45 = KL.CAP_FIL, KL.CAP_TAPER, math.sqrt(0.5)
    rings = []
    for inset, rad, zf in ((0.0, 0.0010, lambda x, y: CAP_Z0),
                           (T * 0.5, 0.0014, lambda x, y: CAP_Z0 + 0.5 * (top_z(x, y) - F - CAP_Z0)),
                           (T, 0.0018, lambda x, y: top_z(x, y) - F),
                           (T + F * (1 - s45), 0.0020, lambda x, y: top_z(x, y) - F * (1 - s45))):
        rings.append([(x, y, zf(x, y)) for x, y in rrect(bx - inset, by - inset, rad, nx, ny)])
    top = rrect(tx, ty, 0.0022, nx, ny)
    for s in (1.0, 0.8, 0.56, 0.3):
        rings.append([(x * s, y * s, top_z(x * s, y * s)) for x, y in top])
    vr = [[bm.verts.new(c + Vector(p)) for p in ring] for ring in rings]
    faces = []
    for a, b in zip(vr, vr[1:]):
        faces += bridge(bm, a, b)
    faces.append(bm.faces.new(vr[-1]))
    for f in faces:
        f.material_index = mat_index
        f.smooth = True
        for lp in f.loops:
            p = lp.vert.co - c
            lp[uvl].uv = KL.top_uv(i, max(-tx, min(tx, p.x)), max(-ty, min(ty, p.y)))


def keycap_mat(name, base, legend, glow):
    """PBT cap: the atlas mask mixes the legend colour over the base; glow > 0 makes legends shine through."""
    m, nt = new_mat(name)
    if nt is None:
        return m
    b, out = principled(nt)
    b.inputs['Roughness'].default_value = 0.52
    tex = nt.nodes.new('ShaderNodeTexImage')
    tex.image = img(f'{CLIP}/assets/keycaps_atlas.png', True)
    mix = nt.nodes.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    nt.links.new(tex.outputs['Color'], mix.inputs['Factor'])
    socket(mix, 'A', 'RGBA').default_value = srgb(base)
    socket(mix, 'B', 'RGBA').default_value = srgb(legend)
    nt.links.new(mix.outputs['Result'], b.inputs['Base Color'])
    if glow:
        b.inputs['Emission Color'].default_value = (1.0, 0.55, 0.3, 1)
        mul = nt.nodes.new('ShaderNodeMath')
        mul.operation = 'MULTIPLY'
        mul.inputs[1].default_value = glow
        nt.links.new(tex.outputs['Color'], mul.inputs[0])
        nt.links.new(mul.outputs[0], b.inputs['Emission Strength'])
    tc = nt.nodes.new('ShaderNodeTexCoord')          # PBT grain
    nz = nt.nodes.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 2500
    bump = nt.nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.06
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs['Normal'], b.inputs['Normal'])
    return m


def build_keyboard(B, M):
    """Full-size ANSI mechanical keyboard: anodised case, floating sculpted PBT caps with backlit legends,
    glowing switch housings, orange underglow, Esc/Enter accents and a USB cable to the back of the desk."""
    U = KL.U
    kb = B.empty('Keyboard', KEYBOARD, (KB_TILT, 0, 0))
    cap_dark = keycap_mat('KeycapPBT', (0.035, 0.035, 0.038), (0.75, 0.66, 0.58), 2.5)
    cap_or = keycap_mat('KeycapPBTOrange', ORANGE, (0.08, 0.05, 0.04), 0.0)
    bm = bmesh.new()
    uvl = bm.loops.layers.uv.new('UVMap')
    sw = bmesh.new()
    for i, (lab, x, r, w, h) in enumerate(KL.KEYS):
        keycap(bm, uvl, i, 1 if lab in ACCENT_KEYS and h == 1 else 0)
        c = key_centre(i)
        offs = [(0, 0)]
        if h > 1:
            offs += [(0, 0.0119), (0, -0.0119)]
        elif w >= 6:
            offs += [(0.05, 0), (-0.05, 0)]
        elif w >= 2:
            offs += [(0.0119, 0), (-0.0119, 0)]
        for k, (ox, oy) in enumerate(offs):
            s = (0.0139, 0.0139, CAP_Z0) if k == 0 else (0.006, 0.008, CAP_Z0 * 0.8)
            bm_box(sw, s, (c.x + ox, c.y + oy, s[2] / 2))
    B.adopt(obj_from_bm('Keyboard_Keys', bm, B.col, [cap_dark, cap_or], uv=False), kb)
    sw_mat = flat('KeySwitchGlow', (0.55, 0.45, 0.4), rough=0.3, emit=(1.0, 0.5, 0.3), emit_strength=1.6)
    B.adopt(obj_from_bm('Keyboard_Switches', sw, B.col, [sw_mat], uv=False), kb)
    # case: rounded slab under the plate, chamfered top edge, bevelled foot
    PAD = 0.009
    x0, x1 = -KL.HOME_F[0] * U - PAD, (KL.WIDTH_U - KL.HOME_F[0]) * U + PAD
    y0, y1 = -2.5 * U - PAD, 4.0 * U + PAD
    cx, cy, hx, hy = (x0 + x1) / 2, (y0 + y1) / 2, (x1 - x0) / 2, (y1 - y0) / 2
    cb = bmesh.new()
    rings = [[cb.verts.new((cx + px, cy + py, z)) for px, py in rrect(hx - ins, hy - ins, 0.006 - ins, 1, 1, 6)]
             for ins, z in ((0.0008, -0.011), (0.0, -0.0102), (0.0, -0.0012), (0.0004, -0.0003), (0.0011, 0.0))]
    for a, b in zip(rings, rings[1:]):
        for f in bridge(cb, a, b):
            f.smooth = True
    cb.faces.new(rings[-1])
    cb.faces.new(rings[0][::-1])
    alu = flat('KeyboardAlu', (0.16, 0.16, 0.17), rough=0.33, metal=1.0)
    B.adopt(obj_from_bm('Keyboard_Case', cb, B.col, [alu], uv=False), kb)
    gb = bmesh.new()                                   # underglow strip around the foot of the case
    rings = [[gb.verts.new((cx + px, cy + py, z)) for px, py in rrect(hx + 0.0002, hy + 0.0002, 0.0062, 1, 1, 6)]
             for z in (-0.0113, -0.0101)]
    bridge(gb, *rings)
    B.adopt(obj_from_bm('Keyboard_Glow', gb, B.col, [M['kb_glow']], uv=False), kb)
    rubber = M['rubber']
    for sx in (-1, 1):                                 # flip-out rear feet + front rubber strips reach the mat
        xf = cx + sx * (hx - 0.035)
        B.box(f'Keyboard_FootRear{sx}', (0.035, 0.009, 0.0078), (xf, y1 - 0.012, -0.0146), rubber, bevel=0.0015, parent=kb)
        B.box(f'Keyboard_FootFront{sx}', (0.03, 0.006, 0.0012), (xf, y0 + 0.01, -0.0115), rubber, parent=kb)
    # lock LEDs and a small Claude spark above the numpad
    led_on = emission_mat('KeyboardLedOn', ORANGE, 4.0)
    for k, lit in enumerate((True, False, False)):
        B.box(f'Keyboard_Led{k}', (0.0026, 0.0013, 0.0004), ((19.0 + 0.75 * k - KL.HOME_F[0]) * U, 5.5 * U, 0.0002),
              led_on if lit else M['mon'], parent=kb)
    sp = obj_from_bm('Keyboard_Logo', claude_star('Keyboard_Logo', 0.0045, 0.0009, thick=0.0003), B.col,
                     [emission_mat('KeyboardLogo', ORANGE, 3.0)], ((21.6 - KL.HOME_F[0]) * U, 5.5 * U, 0.0001),
                     (-math.pi / 2, 0, 0), uv=False)
    B.adopt(sp, kb)
    KM = Matrix.Translation(KEYBOARD) @ Matrix.Rotation(KB_TILT, 4, 'X')
    B.curve('Keyboard_Cable', cable_path(KM @ Vector((0.1, y1, -0.005))), CABLE_R, M['cable'], res=4)
    build_mouse(B, M)
    return kb


CABLE_R = 0.0025
MAT_RECT = (0.12 - 0.475, 0.12 + 0.475, 0.57 - 0.21, 0.57 + 0.21)     # Desk_Mat footprint (x0, x1, y0, y1)
MAT_TOP = DESK_TOP + 0.003


def cable_floor(x, y):
    """lowest height the keyboard cable's axis may take at (x, y): lying on the mat, the desk, or over its back edge"""
    back = DESK_FRONT + DESK_DEPTH
    if MAT_RECT[0] <= x <= MAT_RECT[1] and MAT_RECT[2] <= y <= MAT_RECT[3]:
        return MAT_TOP + CABLE_R
    if abs(x) <= DESK_W / 2 and DESK_FRONT <= y <= back:
        return DESK_TOP + CABLE_R
    if abs(x) <= DESK_W / 2 and back < y < back + CABLE_R:
        return DESK_TOP + math.sqrt(CABLE_R ** 2 - (y - back) ** 2)
    return -1.0


def cable_path(st):
    """the keyboard cable from the back of the case, down onto the mat, off it onto the desk, over the desk's back
    edge and down to the floor: a Catmull-Rom through a few waypoints, sampled densely and kept on the surfaces it
    lies on (an AUTO-handle Bezier through sparse points sagged through the mat)"""
    back = DESK_FRONT + DESK_DEPTH
    way = [st, st + Vector((0.003, 0.03, -0.006)), Vector((-0.035, 0.70, 0)), Vector((-0.03, 0.775, 0)),
           Vector((-0.025, 0.80, 0)), Vector((0.05, 1.0, 0)), Vector((0.11, back - 0.02, 0)),
           Vector((0.12, back + 0.004, DESK_TOP - 0.006)), Vector((0.15, back + 0.03, DESK_TOP - 0.12)),
           Vector((0.2, back + 0.07, DESK_TOP - 0.4)), Vector((0.25, back + 0.1, 0.004))]
    for w in way[2:7]:
        w.z = cable_floor(w.x, w.y)
    pts = []
    ext = [way[0] * 2 - way[1]] + way + [way[-1] * 2 - way[-2]]
    for i in range(1, len(ext) - 2):
        p0, p1, p2, p3 = ext[i - 1:i + 3]
        n = max(2, int((p2 - p1).length / 0.012))
        for k in range(n):
            u = k / n
            p = 0.5 * (2 * p1 + (p2 - p0) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (3 * p1 - p0 - 3 * p2 + p3) * u ** 3)
            p.z = max(p.z, cable_floor(p.x, p.y))
            pts.append(p)
    pts.append(way[-1])
    return pts


# ---------------------------------------------------------------- mouse

M_LEN, M_ZB = 0.122, 0.002
M_HALFW = ((0.0, 0.0285), (0.25, 0.0328), (0.42, 0.0330), (0.62, 0.0302), (0.82, 0.0300), (1.0, 0.0288))
M_HEIGHT = ((0.0, 0.020), (0.12, 0.031), (0.28, 0.0375), (0.42, 0.0390), (0.58, 0.0365), (0.75, 0.0310),
            (0.9, 0.0262), (1.0, 0.0235))


def spline(tab, t):
    """cubic Hermite (Catmull-Rom tangents) through [(t, v)]"""
    ts, vs = [a for a, _ in tab], [b for _, b in tab]
    n = len(tab)
    k = next((i for i in range(n - 1) if t <= ts[i + 1]), n - 2)

    def m(i):
        lo, hi = max(0, i - 1), min(n - 1, i + 1)
        return (vs[hi] - vs[lo]) / (ts[hi] - ts[lo])
    h = ts[k + 1] - ts[k]
    s = (t - ts[k]) / h
    return ((2 * s ** 3 - 3 * s ** 2 + 1) * vs[k] + (s ** 3 - 2 * s ** 2 + s) * h * m(k)
            + (-2 * s ** 3 + 3 * s ** 2) * vs[k + 1] + (s ** 3 - s ** 2) * h * m(k + 1))


def mouse_point(t, th):
    """Point on the mouse shell (mouse frame: origin at the centre of the footprint, +Y forward):
    t 0 (rear) .. 1 (front), th 0 (right foot) .. pi/2 (crest) .. pi (left foot)."""
    a = abs(2 * t - 1)
    p, q = (3.2, 7.0) if t < 0.5 else (4.5, 9.0)
    hw = spline(M_HALFW, t) * (1 - a ** p) ** (1 / p)
    h = M_ZB + (spline(M_HEIGHT, t) - M_ZB) * (1 - a ** q) ** (1 / q)
    c, s = math.cos(th), math.sin(th)
    xr = math.copysign(abs(c) ** (2 / 2.8), c)
    g = abs(s) ** (2 / 2.2)                      # 0 at the foot .. 1 on the crest
    x = hw * xr
    thumb = math.exp(-((t - 0.48) / 0.2) ** 2)
    if xr < 0:                                   # thumb side: flared foot and a shallow thumb groove
        x -= 0.0035 * thumb * (1 - g) ** 3
        x += 0.0022 * thumb * math.exp(-((g - 0.45) / 0.18) ** 2)
    else:                                        # ring / pinky side: a slight flare
        x += 0.0015 * thumb * (1 - g) ** 3
    z = M_ZB + (h - M_ZB) * g * (1 - 0.10 * xr)  # the crest leans left, like a right-hand ergonomic shell
    return Vector((x, -M_LEN / 2 + t * M_LEN, z))


def mouse_frame(t, th, d=1e-3):
    """(point, outward normal, forward tangent) on the shell"""
    p = mouse_point(t, th)
    dt = mouse_point(min(1.0, t + d), th) - mouse_point(max(0.0, t - d), th)
    dth = mouse_point(t, th + d) - mouse_point(t, th - d)
    return p, dth.cross(dt).normalized(), dt.normalized()


def mouse_material():
    """Soft-touch black shell; the button seams (centre split, rear edge, side seams) are cut in by the shader."""
    m, nt = new_mat('MouseShell')
    if nt is None:
        return m
    b, out = principled(nt)
    N, Lk = nt.nodes, nt.links

    def op(kind, *args):
        n = N.new('ShaderNodeMath')
        n.operation = kind
        for k, v in enumerate(args):
            if isinstance(v, (int, float)):
                n.inputs[k].default_value = v
            else:
                Lk.new(v, n.inputs[k])
        return n.outputs[0]

    def seam(d):
        mr = N.new('ShaderNodeMapRange')
        Lk.new(d, mr.inputs['Value'])
        mr.inputs['From Min'].default_value, mr.inputs['From Max'].default_value = 0.0002, 0.0006
        mr.inputs['To Min'].default_value, mr.inputs['To Max'].default_value = 1.0, 0.0
        return mr.outputs[0]

    tc = N.new('ShaderNodeTexCoord')
    sep = N.new('ShaderNodeSeparateXYZ')
    Lk.new(tc.outputs['Object'], sep.inputs[0])
    x, y, z = sep.outputs
    ax = op('ABSOLUTE', x)
    yb = op('MULTIPLY_ADD', op('MULTIPLY', x, x), 6.0, 0.006)        # rear edge of the main buttons
    front = op('GREATER_THAN', y, yb)
    s1 = op('MULTIPLY', op('MULTIPLY', seam(ax), front), op('LESS_THAN', y, 0.056))
    s2 = op('MULTIPLY', seam(op('ABSOLUTE', op('SUBTRACT', y, yb))), op('LESS_THAN', ax, 0.0245))
    s3 = op('MULTIPLY', op('MULTIPLY', seam(op('ABSOLUTE', op('SUBTRACT', ax, 0.0245))), front),
            op('LESS_THAN', y, 0.05))
    S = op('MULTIPLY', op('MAXIMUM', op('MAXIMUM', s1, s2), s3), op('GREATER_THAN', z, 0.014))
    mix = N.new('ShaderNodeMix')
    mix.data_type = 'RGBA'
    Lk.new(S, mix.inputs['Factor'])
    socket(mix, 'A', 'RGBA').default_value = srgb((0.035, 0.035, 0.038))
    socket(mix, 'B', 'RGBA').default_value = (0.002, 0.002, 0.002, 1)
    Lk.new(mix.outputs['Result'], b.inputs['Base Color'])
    Lk.new(op('MULTIPLY_ADD', S, 0.3, 0.46), b.inputs['Roughness'])
    nz = N.new('ShaderNodeTexNoise')
    nz.inputs['Scale'].default_value = 3000
    Lk.new(tc.outputs['Object'], nz.inputs['Vector'])
    grain = N.new('ShaderNodeBump')
    grain.inputs['Strength'].default_value = 0.05
    Lk.new(nz.outputs['Fac'], grain.inputs['Height'])
    cut = N.new('ShaderNodeBump')
    cut.inputs['Strength'].default_value = 0.5
    cut.inputs['Distance'].default_value = 0.0004
    Lk.new(op('MULTIPLY', S, -1.0), cut.inputs['Height'])
    Lk.new(grain.outputs['Normal'], cut.inputs['Normal'])
    Lk.new(cut.outputs['Normal'], b.inputs['Normal'])
    return m


def build_mouse(B, M):
    """Wireless right-hand ergonomic gaming mouse at MOUSE (empty 'Mouse', +Y forward): sculpted shell with cut
    button seams, glowing scroll wheel, two thumb buttons, an orange Claude spark on the palm rest."""
    mo = B.empty('Mouse', MOUSE)
    mo.scale = (MOUSE_SCALE,) * 3
    NT, NS = 56, 32
    bm = bmesh.new()
    crease = bm.edges.layers.float.new('crease_edge')
    rings = [[bm.verts.new(mouse_point(0.5 - 0.5 * math.cos(math.pi * i / NT), math.pi * j / NS)) for j in range(NS + 1)]
             for i in range(1, NT)]
    bottom = []
    for a, b in zip(rings, rings[1:]):
        for j in range(NS):
            bm.faces.new((a[j], b[j], b[j + 1], a[j + 1])).smooth = True
        bottom.append(bm.faces.new((a[NS], b[NS], b[0], a[0])))
    for ring, t in ((rings[0], 0.0), (rings[-1], 1.0)):          # close the rounded ends with a fan
        pole = bm.verts.new((0.0, -M_LEN / 2 + t * M_LEN, (ring[NS // 2].co.z + M_ZB) / 2))
        for j in range(NS):
            bm.faces.new((pole, ring[j], ring[j + 1])).smooth = True
        bottom.append(bm.faces.new((pole, ring[NS], ring[0])))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bottom:
        f.smooth = False
        for e in f.edges:
            e[crease] = 1.0
    foot = [r[0].co.copy() for r in rings] + [r[NS].co.copy() for r in reversed(rings)]
    shell = obj_from_bm('Mouse_Shell', bm, B.col, [mouse_material()], uv=False)
    ss = shell.modifiers.new('Subsurf', 'SUBSURF')
    ss.levels, ss.render_levels = 1, 2
    B.adopt(shell, mo)
    # base plate under the shell (the PTFE-skated bottom shows as a thin dark line)
    pb = bmesh.new()
    top = [pb.verts.new((p.x * 0.985, p.y * 0.99, M_ZB + 0.0003)) for p in foot]
    low = [pb.verts.new((p.x * 0.95, p.y * 0.96, 0.0)) for p in foot]
    bridge(pb, low[::-1], top[::-1])
    pb.faces.new(top)
    pb.faces.new(low[::-1])
    bmesh.ops.recalc_face_normals(pb, faces=pb.faces)
    B.adopt(obj_from_bm('Mouse_Base', pb, B.col, [M['rubber']], uv=False), mo)
    # scroll wheel in its slot, the orange core glowing out of both sides
    tw = 0.76
    p, n, fwd = mouse_frame(tw, math.pi / 2)
    tilt = math.atan2(fwd.z, fwd.y)
    plastic = flat('MouseGloss', (0.02, 0.02, 0.022), rough=0.18, coat=0.4)
    B.box('Mouse_Slot', (0.0118, 0.027, 0.003), (0, p.y, p.z - 0.0011), M['mon'], (tilt, 0, 0), bevel=0.0012, parent=mo)
    wz = p.z + 0.0022 - 0.0105
    B.cyl('Mouse_Wheel', 0.0105, 0.0075, (0, p.y, wz), flat('MouseWheelRubber', (0.025, 0.025, 0.025), rough=0.75),
          (0, math.pi / 2, 0), 40, bottom=False, parent=mo)
    B.cyl('Mouse_WheelGlow', 0.0096, 0.0095, (0, p.y, wz), emission_mat('MouseWheelGlow', ORANGE, 3.0),
          (0, math.pi / 2, 0), 32, bottom=False, parent=mo)
    for k, t in enumerate((0.56, 0.69)):                          # thumb buttons on the left flank
        p, n, fwd = mouse_frame(t, 2.51)
        rot = (0, math.atan2(-n.z, n.x), math.atan2(-fwd.x, fwd.y))
        B.box(f'Mouse_SideBtn{k}', (0.0028, 0.0155, 0.0052), p + n * 0.0004, plastic, rot, bevel=0.0012, parent=mo)
    p, n, fwd = mouse_frame(0.24, math.pi / 2)
    logo = obj_from_bm('Mouse_Logo', claude_star('Mouse_Logo', 0.007, 0.0014, thick=0.0005), B.col,
                       [emission_mat('MouseLogo', ORANGE, 2.5)], p - n * 0.0002,
                       (math.atan2(fwd.z, fwd.y) - math.pi / 2, 0, 0), uv=False)
    B.adopt(logo, mo)
    return mo


# ---------------------------------------------------------------- gaming chair

def claude_star(name, r_out, r_in, n=12, thick=0.004):
    """The Claude spark: n tapered rays around a small hub, lying in the XZ plane facing -Y."""
    bm = bmesh.new()
    rr = random.Random(3)
    for k in range(n):
        a = 2 * math.pi * k / n + rr.uniform(-0.06, 0.06)
        ro = r_out * rr.uniform(0.82, 1.0)
        w0, w1 = r_out * 0.11, r_out * 0.05
        d = Vector((math.cos(a), 0, math.sin(a)))
        t = Vector((-math.sin(a), 0, math.cos(a)))
        quad = [d * r_in + t * w0, d * ro + t * w1, d * ro - t * w1, d * r_in - t * w0]
        vs = [bm.verts.new(p) for p in quad]
        f = bm.faces.new(vs)
        ext = bmesh.ops.extrude_face_region(bm, geom=[f])
        bmesh.ops.translate(bm, vec=(0, -thick, 0), verts=[e for e in ext['geom'] if isinstance(e, bmesh.types.BMVert)])
    vs = bmesh.ops.create_circle(bm, cap_ends=True, segments=24, radius=r_in * 1.15)['verts']
    bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'X'), verts=vs)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def build_chair(B, M):
    """Tall racing-style gaming chair; the back (with the orange Claude spark) faces -Y, towards the stairs."""
    ch = B.empty('GamingChair')
    L, O = M['leather'], M['leather_or']
    for k in range(5):  # star base + casters
        a = 2 * math.pi * k / 5 + 0.3
        d = Vector((math.cos(a), math.sin(a), 0))
        B.box(f'Chair_Leg{k}', (0.32, 0.05, 0.035), tuple(d * 0.16 + Vector((0, 0, 0.085))), M['chair_base'], (0, 0, a), bevel=0.008, parent=ch)
        B.sphere(f'Chair_Caster{k}', 0.032, tuple(d * 0.31 + Vector((0, 0, 0.032))), M['caster'], parent=ch)
    D = SEAT_DROP
    B.cyl('Chair_Gas', 0.022, 0.32 - D, (0, 0, 0.09), M['chrome'], bottom=True, parent=ch)
    B.cyl('Chair_GasCover', 0.04, 0.16, (0, 0, 0.1), M['chair_base'], r2=0.03, bottom=True, parent=ch)
    B.box('Chair_Mech', (0.26, 0.26, 0.05), (0, 0.0, 0.41 - D), M['chair_base'], bevel=0.01, parent=ch)
    # seat: cushion + side bolsters
    B.box('Chair_Seat', (0.5, 0.52, 0.1), (0, 0.02, 0.48 - D), L, bevel=0.03, subsurf=1, parent=ch)
    for sx in (-1, 1):
        B.box(f'Chair_SeatBolster{sx}', (0.07, 0.48, 0.07), (sx * 0.235, 0.02, 0.535 - D), O if sx else L, (0, sx * 0.25, 0), bevel=0.025, subsurf=1, parent=ch)
    # backrest: nearly upright (reclined 2 degrees, away from the desk), wings, shoulder bolsters, headrest pillow.
    # The hunched typist's skull reaches 2 cm behind the line of his shoulder blades, so the pillow just clears it
    # at his furthest lean back (a back tilted towards the desk put his head through the pillow and the back).
    back = B.empty('Chair_BackPivot', (0, -0.22, 0.5 - D), (math.radians(2), 0, 0), parent=ch)
    B.box('Chair_Back', (0.5, 0.11, 0.98), (0, -0.04, 0.52), L, bevel=0.035, subsurf=1, parent=back)
    for sx in (-1, 1):
        B.box(f'Chair_Wing{sx}', (0.09, 0.14, 0.62), (sx * 0.265, 0.02, 0.36), L, (0, sx * 0.15, sx * 0.35), bevel=0.03, subsurf=1, parent=back)
        B.box(f'Chair_WingStripe{sx}', (0.012, 0.15, 0.55), (sx * 0.305, 0.02, 0.37), O, (0, sx * 0.15, sx * 0.35), bevel=0.004, parent=back)
        B.box(f'Chair_Shoulder{sx}', (0.1, 0.13, 0.22), (sx * 0.22, 0.01, 0.82), L, (0, -sx * 0.2, sx * 0.25), bevel=0.035, subsurf=1, parent=back)
    B.box('Chair_Head', (0.3, 0.12, 0.2), (0, -0.04, 1.0), L, bevel=0.04, subsurf=1, parent=back)
    B.box('Chair_Pillow', (0.24, 0.07, 0.12), (0, 0.04, 0.88), O, bevel=0.03, subsurf=2, parent=back)
    B.box('Chair_Lumbar', (0.28, 0.07, 0.16), (0, 0.015, 0.22), L, bevel=0.03, subsurf=2, parent=back)  # lower back sinks ~1 cm
    # orange spark on the back, facing the camera that comes down the stairs
    bm = claude_star('Chair_Spark', 0.13, 0.025)
    sp = obj_from_bm('Chair_Spark', bm, B.col, [O], (0, -0.098, 0.6), uv=False)
    B.adopt(sp, back)
    # armrests
    for sx in (-1, 1):
        B.box(f'Chair_ArmPost{sx}', (0.04, 0.06, 0.2), (sx * 0.29, 0.0, 0.58 - D), M['chair_base'], bevel=0.01, parent=ch)
        B.box(f'Chair_ArmPad{sx}', (0.085, 0.26, 0.035), (sx * 0.29, 0.03, 0.695 - D), L, bevel=0.015, subsurf=1, parent=ch)
    return ch


# ---------------------------------------------------------------- syringes, drops, puddles

def build_syringe(B, M, name, fill, loc, rot, drop=False, parent=None):
    """5 ml syringe along local +Z (needle at -Z). fill 0..1 of the barrel holds glowing liquid."""
    s = B.empty(name, loc, rot, parent)
    r, L = 0.0068, 0.075
    B.cyl(f'{name}_Barrel', r, L, (0, 0, 0), M['syr_glass'], seg=20, bottom=True, parent=s)
    B.box(f'{name}_Flange', (0.034, 0.012, 0.0016), (0, 0, L), M['plunger'], bevel=0.0007, parent=s)
    B.cyl(f'{name}_Tip', 0.0022, 0.009, (0, 0, -0.009), M['plunger'], seg=12, r2=0.0016, bottom=True, parent=s)
    B.cyl(f'{name}_Hub', 0.0035, 0.008, (0, 0, -0.016), M['hub'], seg=12, r2=0.0028, bottom=True, parent=s)
    nd = B.cyl(f'{name}_Needle', 0.00045, 0.026, (0, 0, -SYR_NEEDLE_TIP), M['needle'], seg=16, bottom=True, parent=s)
    for v in nd.data.vertices:          # the lancet bevel at the point
        if v.co.z < 1e-6:
            v.co.z += 0.0011 * (1 + v.co.x / 0.00045) / 2
    zs = 0.004 + fill * (L - 0.012)                         # stopper position = top of the liquid
    if fill > 0.01:
        B.cyl(f'{name}_Liquid', r * 0.93, zs - 0.002, (0, 0, 0.002), M['liquid'], seg=20, bottom=True, parent=s)
    B.cyl(f'{name}_Stopper', r * 0.95, 0.006, (0, 0, zs), M['rubber'], seg=20, bottom=True, parent=s)
    rod = L + 0.012 - zs
    B.box(f'{name}_Rod', (0.0085, 0.0018, rod), (0, 0, zs + 0.006 + rod / 2), M['plunger'], parent=s)
    B.box(f'{name}_Rod2', (0.0018, 0.0085, rod), (0, 0, zs + 0.006 + rod / 2), M['plunger'], parent=s)
    B.cyl(f'{name}_Thumb', 0.0085, 0.0016, (0, 0, zs + 0.006 + rod), M['plunger'], seg=20, bottom=True, parent=s)
    if drop:
        B.sphere(f'{name}_Drop', 0.0016, (0, 0, -0.0425), M['liquid'], scale=(1, 1, 1.6), seg=12, parent=s)
    return s


def puddle_mesh(name, rad, rng, blobs=6):
    """A pool with a rounded meniscus edge (rings of rising height), an irregular outline and a trail
    of smaller, stretched drops."""
    bm = bmesh.new()
    RINGS = ((1.0, 0.0002), (0.94, 0.0010), (0.82, 0.0015), (0.55, 0.0017), (0.25, 0.0017))
    THICK = (0.12, 0.45, 0.8, 1.0, 1.0)
    thick = {}

    def blob(cx, cy, r, stretch=1.0, rot=0.0, n=56):
        ph = [rng.uniform(0, 6.28) for _ in range(6)]
        amp = [0.16, 0.10, 0.07, 0.05, 0.035, 0.02]
        hz = [2, 3, 5, 7, 11, 17]
        ca, sa = math.cos(rot), math.sin(rot)
        rings = []
        for (s, h), tk in zip(RINGS, THICK):
            ring = []
            for k in range(n):
                a = 2 * math.pi * k / n
                rr = r * s * (1 + sum(am * math.sin(f * a + p) for am, f, p in zip(amp, hz, ph)))
                x, y = rr * math.cos(a) * stretch, rr * math.sin(a)
                ring.append(bm.verts.new((cx + x * ca - y * sa, cy + x * sa + y * ca, h * min(1.0, r / 0.03 + 0.4))))
                thick[ring[-1]] = tk * min(1.0, r / 0.02 + 0.3)
            rings.append(ring)
        for ra, rb in zip(rings, rings[1:]):
            for k in range(n):
                bm.faces.new((ra[k], ra[(k + 1) % n], rb[(k + 1) % n], rb[k]))
        c = bm.verts.new((cx, cy, rings[-1][0].co.z))
        thick[c] = thick[rings[-1][0]]
        for k in range(n):
            bm.faces.new((rings[-1][k], rings[-1][(k + 1) % n], c))

    blob(0, 0, rad)
    ang = rng.uniform(0, 6.28)
    for k in range(blobs):  # splatter trail, drops stretched along the direction they were flung
        a = ang + rng.uniform(-0.45, 0.45)
        d = rad * rng.uniform(1.15, 2.8)
        blob(d * math.cos(a), d * math.sin(a), rad * rng.uniform(0.06, 0.24), rng.uniform(1.0, 2.2), a, 28)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    lay = bm.loops.layers.float_color.new('thick')
    for f in bm.faces:
        for lp in f.loops:
            t = thick[lp.vert]
            lp[lay] = (t, t, t, 1.0)
    return bm


def build_floor_drugs(B, M, light_col):
    """Syringes scattered around the chair; some leaking into glowing puddles."""
    rng = random.Random(21)
    out = []
    # (x, y, fill, drop, lying, puddle radius)
    spots = [(-0.55, -0.35, 0.5, False, True, 0.0), (0.62, -0.2, 0.08, True, True, 0.06),
             (-0.3, -0.75, 0.0, False, True, 0.0), (0.25, -0.62, 0.3, False, True, 0.11),
             (-0.8, 0.1, 0.95, False, True, 0.0), (0.85, 0.35, 0.05, True, True, 0.05),
             (-0.15, 0.32, 0.6, False, True, 0.0), (0.45, 0.22, 0.0, False, True, 0.12),
             (-0.65, -0.95, 0.15, True, True, 0.08), (1.05, -0.6, 0.7, False, True, 0.0),
             (-1.1, -0.3, 0.02, True, True, 0.04), (0.1, -1.05, 0.45, False, True, 0.0)]
    for i, (x, y, fill, drop, lying, pr) in enumerate(spots):
        rz = rng.uniform(0, 6.28)
        rot = (math.pi / 2, 0, rz) if lying else (0, 0, rz)
        z = 0.0085
        s = build_syringe(B, M, f'Syringe{i:02d}', fill, (x, y, z), rot, drop)
        out.append(s)
        if pr:
            # puddle spreads from the needle end (local -Z of the syringe -> lying along the floor)
            tip = Vector((x, y, 0)) + Euler(rot).to_matrix() @ Vector((0, 0, -0.06))
            bm = puddle_mesh(f'Puddle{i:02d}', pr, rng)
            p = obj_from_bm(f'Puddle{i:02d}', bm, B.col, [M['puddle']], (tip.x, tip.y, 0.0005), (0, 0, rng.uniform(0, 6.28)),
                            uv=False, smooth=True)
            B.adopt(p)
            l = light(f'PuddleGlow{i:02d}', 'POINT', (tip.x, tip.y, 0.1), 0.4 + pr * 7, (1.0, 0.38, 0.14), light_col, pr)
            l.data.use_shadow = False
            l.data.specular_factor = 0.0
            B.adopt(l)
    # a fresh one on the desk next to the keyboard, half-full, needle out over the edge (drop.py drips from it)
    out.append(build_syringe(B, M, 'Syringe_Desk', 0.5, tuple(SYR_DESK_LOC), (math.pi / 2, 0, SYR_DESK_YAW)))
    return out


# ---------------------------------------------------------------- IV drip

def build_iv(B, M):
    iv = B.empty('IV_Stand', tuple(IV_BASE))
    for k in range(5):
        a = 2 * math.pi * k / 5
        d = Vector((math.cos(a), math.sin(a), 0))
        B.box(f'IV_Leg{k}', (0.28, 0.025, 0.02), tuple(d * 0.14 + Vector((0, 0, 0.06))), M['chrome'], (0, 0, a), parent=iv)
        B.sphere(f'IV_Caster{k}', 0.022, tuple(d * 0.27 + Vector((0, 0, 0.022))), M['caster'], parent=iv)
    B.cyl('IV_Pole', 0.011, 1.9, (0, 0, 0.06), M['chrome'], bottom=True, parent=iv)
    for sx in (-1, 1):
        B.curve(f'IV_Hook{sx}', [Vector((0, 0, 1.92)), Vector((sx * 0.08, 0, 1.95)), Vector((sx * 0.12, 0, 1.9)),
                                 Vector((sx * 0.11, 0, 1.87))], 0.004, M['chrome'], parent=iv)
    bag = B.empty('IV_Bag', (0.11, 0, 1.84), parent=iv)
    B.box('IV_BagShell', (0.13, 0.035, 0.24), (0, 0, -0.13), M['bag'], bevel=0.012, subsurf=2, parent=bag)
    fill = B.box('IV_BagLiquid', (0.115, 0.025, 0.17), (0, 0, -0.165), M['liquid'], bevel=0.01, subsurf=2, parent=bag)
    B.box('IV_BagLabel', (0.07, 0.002, 0.05), (0, -0.019, -0.09), M['tape'], parent=bag)
    B.cyl('IV_BagPort', 0.005, 0.03, (0, 0, -0.28), M['bag'], bottom=True, parent=bag)
    B.cyl('IV_Chamber', 0.009, 0.06, (0, 0, -0.35), M['bag'], bottom=True, parent=bag)
    B.cyl('IV_ChamberLiquid', 0.0082, 0.018, (0, 0, -0.35), M['liquid'], bottom=True, parent=bag)
    drop = B.sphere('IV_Drop', 0.0028, (0, 0, -0.305), M['liquid'], scale=(1, 1, 1.3), seg=12, parent=bag)
    B.light_anchor = (iv, bag)
    return iv, bag, fill, drop


def build_iv_tube(B, M, start, tail):
    """Tube from the drip chamber (root-local `start`) sagging behind the desk, over the desk's left edge, then
    `tail` (root-local, from where it leaves the arm to the cannula's luer: catheter.setup). Returns (tube,
    liquid) meshes carrying 'along' (0 at the bag .. 1 at the cannula)."""
    s = Vector(start)
    T = DESK_TOP + 0.004
    corner = Vector((-0.52, 0.42, T + 0.035))                          # lifts off the front-left corner
    pts = [s, s + Vector((-0.03, -0.08, -0.29)),
           Vector((-0.88, DESK_FRONT + DESK_DEPTH - 0.07, T + 0.04)),   # drops onto the back-left of the desk
           Vector((-0.82, 0.62, T)),                                  # lies along the desk
           corner, (corner + tail[0]) / 2 + Vector((0.0, 0.0, 0.012))] + [Vector(p) for p in tail]
    tube = along_mesh(B.curve('IV_Tube', pts, 0.0021, M['tube'], res=24))
    liq = along_mesh(B.curve('IV_TubeLiquid', pts, 0.0014, flow_material(), res=24))
    return tube, liq


def along_mesh(ob):
    """Convert a bevelled curve object to a mesh carrying a point attribute 'along' (0 at the first
    control point .. 1 at the last) for shaders that need the position along the tube."""
    vl = bpy.context.view_layer
    cu, r = ob.data, ob.data.bevel_depth
    cu.bevel_depth = 0.0
    vl.update()
    line = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    poly = [v.co.copy() for v in line.vertices]
    bpy.data.meshes.remove(line)
    cu.bevel_depth = r
    vl.update()
    me = bpy.data.meshes.new_from_object(ob.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    cum = [0.0]
    for a, b in zip(poly, poly[1:]):
        cum.append(cum[-1] + (b - a).length)
    vals = []
    for v in me.vertices:
        best, bs = 1e9, 0.0
        for i, (a, b) in enumerate(zip(poly, poly[1:])):
            ab = b - a
            u = max(0.0, min(1.0, (v.co - a).dot(ab) / max(ab.length_squared, 1e-12)))
            d = (a + ab * u - v.co).length_squared
            if d < best:
                best, bs = d, cum[i] + u * ab.length
        vals.append(bs / cum[-1])
    me.attributes.new('along', 'FLOAT', 'POINT').data.foreach_set('value', vals)
    me.shade_smooth()
    name, parent, col = ob.name, ob.parent, ob.users_collection[0]
    bpy.data.objects.remove(ob)
    bpy.data.curves.remove(cu)
    out = bpy.data.objects.new(name, me)
    col.objects.link(out)
    out.parent = parent
    return out


def flow_material():
    """Liquid in the IV line: emissive pulses that travel along the tube (driven by the frame)."""
    m, nt = new_mat('IVFlow')
    if nt is None:
        return m
    b, out = principled(nt)
    b.inputs['Base Color'].default_value = (0.35, 0.06, 0.015, 1)
    b.inputs['Roughness'].default_value = 0.1
    b.inputs['Emission Color'].default_value = (1.0, 0.22, 0.045, 1)
    along = nt.nodes.new('ShaderNodeAttribute')   # 0 at the bag .. 1 at the elbow (see along_mesh)
    along.attribute_name = 'along'
    add = nt.nodes.new('ShaderNodeMath')
    add.operation = 'ADD'
    add.name = 'FlowOffset'
    nt.links.new(along.outputs['Fac'], add.inputs[0])
    fc = add.inputs[1].driver_add('default_value')
    fc.driver.expression = '-frame * 0.006'
    wave = nt.nodes.new('ShaderNodeTexWave')
    wave.wave_type = 'BANDS'
    wave.bands_direction = 'X'
    wave.inputs['Scale'].default_value = 9.0
    wave.inputs['Distortion'].default_value = 2.0
    comb = nt.nodes.new('ShaderNodeCombineXYZ')
    nt.links.new(add.outputs[0], comb.inputs['X'])
    nt.links.new(comb.outputs[0], wave.inputs['Vector'])
    ramp = nt.nodes.new('ShaderNodeMapRange')
    ramp.inputs['To Min'].default_value = 0.35   # pulses peak just past AgX's bleach point: a hot core
    ramp.inputs['To Max'].default_value = 1.6
    nt.links.new(wave.outputs['Fac'], ramp.inputs['Value'])
    gate = nt.nodes.new('ShaderNodeMath')  # front of the bright flow along the tube (0 = bag .. 1 = elbow), animated
    gate.operation = 'LESS_THAN'
    gate.name = 'FlowFill'
    gate.inputs[1].default_value = 1.01
    nt.links.new(along.outputs['Fac'], gate.inputs[0])
    lvl = nt.nodes.new('ShaderNodeMath')   # behind the front: full pulses; ahead of it: a faint thread
    lvl.operation = 'MULTIPLY_ADD'
    lvl.name = 'FlowDim'
    lvl.inputs[1].default_value = 0.85
    lvl.inputs[2].default_value = 0.15
    nt.links.new(gate.outputs[0], lvl.inputs[0])
    mul = nt.nodes.new('ShaderNodeMath')
    mul.operation = 'MULTIPLY'
    nt.links.new(ramp.outputs[0], mul.inputs[0])
    nt.links.new(lvl.outputs[0], mul.inputs[1])
    nt.links.new(mul.outputs[0], b.inputs['Emission Strength'])
    return m


# ---------------------------------------------------------------- junk

def build_junk(B, M):
    rng = random.Random(5)
    # energy cans: standing on the desk, crushed/lying on the floor
    cans = [((0.78, 0.5, DESK_TOP), False, 'can_a'), ((0.86, 0.62, DESK_TOP), False, 'can_c'), ((-0.75, 0.62, DESK_TOP), False, 'can_b'),
            ((1.0, 0.1, 0.033), True, 'can_a'), ((-0.95, 0.5, 0.033), True, 'can_c'), ((0.7, -0.85, 0.033), True, 'can_b'),
            ((-0.4, 1.0, 0.033), True, 'can_a'), ((1.2, 0.7, 0.033), True, 'can_c'), ((0.35, 1.05, 0.0), False, 'can_b')]
    for i, (p, lying, mk) in enumerate(cans):
        rot = (math.pi / 2, 0, rng.uniform(0, 6.28)) if lying else (0, 0, rng.uniform(0, 6.28))
        c = B.empty(f'Can{i}', p, rot)
        zc = -0.0835 if lying else 0
        B.cyl(f'Can{i}_Body', 0.033, 0.155, (0, 0, zc), M[mk], seg=24, bottom=True, parent=c)
        B.cyl(f'Can{i}_Top', 0.028, 0.006, (0, 0, zc + 0.155), M['can_b'], seg=24, bottom=True, parent=c)
    # pizza boxes stacked by the desk leg and one open on the floor
    for i in range(4):
        B.box(f'PizzaBox{i}', (0.36, 0.36, 0.045), (1.35 + rng.uniform(-0.03, 0.03), 0.9 + rng.uniform(-0.03, 0.03), 0.0225 + i * 0.046),
              M['cardboard'], (0, 0, rng.uniform(-0.15, 0.15)), bevel=0.002)
    B.box('PizzaBox_Open', (0.36, 0.36, 0.012), (-1.25, -0.6, 0.006), M['cardboard'], (0, 0, 0.4))
    B.box('PizzaBox_Lid', (0.36, 0.36, 0.008), (-1.25 - 0.17, -0.6 - 0.1, 0.18), M['cardboard'], (0, math.radians(-75), 0.4))
    # cables from the monitors down behind the desk into a power strip
    for k in range(6):
        x = -0.6 + k * 0.24
        B.curve(f'MonCable{k}', [Vector((x * 0.6, DESK_FRONT + DESK_DEPTH - 0.08, DESK_TOP + 0.25)),
                                 Vector((x * 0.7, DESK_FRONT + DESK_DEPTH + 0.06, DESK_TOP - 0.2)),
                                 Vector((x * 0.4 + 0.3, DESK_FRONT + DESK_DEPTH + 0.2, 0.01)),
                                 Vector((0.4 + k * 0.03, DESK_FRONT + DESK_DEPTH + 0.35, 0.01))], 0.003, M['cable'])
    B.box('PowerStrip', (0.3, 0.06, 0.04), (0.5, DESK_FRONT + DESK_DEPTH + 0.37, 0.02), M['mon'], bevel=0.005)


def build_all(root, col, light_col):
    M = mats()
    B = Builder(root, col)
    build_desk(B, M)
    screens = build_monitors(B, M)
    build_keyboard(B, M)
    chair = build_chair(B, M)
    build_floor_drugs(B, M, light_col)
    iv = build_iv(B, M)
    build_junk(B, M)
    return dict(M=M, B=B, screens=screens, chair=chair, iv=iv)
