"""Build the environment: suburban street, the house (exterior + hallway + basement stairs + basement shell).
Run: Blender -b --factory-startup --python scripts/build_env.py  ->  blend/env.blend"""
import bpy, bmesh, math, sys, os
from mathutils import Vector, Matrix, Euler
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from lib_build import *

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene

# ------------------------------------------------------------------ layout constants (metres)
T = 0.2            # exterior wall thickness
GF = 0.6           # ground-floor level (top of floor)
CEIL = 3.2         # ground-floor ceiling
SF = 3.4           # second-floor level
EAVE = 6.2         # top of walls
RIDGE = 9.3
BF = -2.1          # basement floor
JOIST_TOP = 0.54   # underside of subfloor
JOIST_BOT = 0.3    # basement ceiling (joist bottoms)
BWZ = (-0.12, 0.26)  # front basement windows (below grade, in window wells)
HX0, HX1, HY0, HY1 = -6.0, 6.0, 0.0, 9.0          # house outer footprint
STAIR = dict(x0=-4.6, x1=-0.8, y0=4.35, y1=5.55)    # stair-well opening (basement stair runs west)

C_EXT = coll('EXTERIOR')
C_STREET = coll('STREET', C_EXT)
C_HOUSE = coll('HOUSE', C_EXT)
C_INT = coll('INTERIOR')
C_BASE = coll('BASEMENT')
C_LIGHT = coll('LIGHTS')
C_CAM = coll('TESTCAMS')
C_LIB = bpy.data.collections.new('LIB_INSTANCES')   # not linked to the scene: source for collection instances

# ------------------------------------------------------------------ materials
M = {}
M['siding'] = pbr('Siding_Main', 'white_planks_clean', tile=1.8, rot90=True, tint=(0.78, 0.82, 0.86), ao=0.8)
M['siding_n'] = pbr('Siding_Neighbor', 'white_planks_clean', tile=1.8, rot90=True, tint=(0.86, 0.80, 0.70), ao=0.8)
M['siding_n2'] = pbr('Siding_Neighbor2', 'white_planks_clean', tile=1.8, rot90=True, tint=(0.62, 0.70, 0.66), ao=0.8)
M['found'] = pbr('Foundation', 'painted_concrete', tile=2.5, sat=0.0, bright=0.55, ao=0.8)
M['block'] = pbr('BasementBlock', 'concrete_block_wall', tile=2.4, ao=1.0, bright=0.9)
M['bfloor'] = pbr('BasementFloor', 'concrete_floor_worn_001', tile=3.0, ao=1.0, rough_mul=0.8)
M['roof'] = pbr('Roof', 'grey_roof_01', tile=2.2, ao=1.0, bright=0.8)
M['asphalt'] = pbr('Asphalt', 'asphalt_02', tile=4.0, ao=0.8, rough_mul=0.9)
M['pave'] = pbr('Sidewalk', 'concrete_pavement', tile=2.0, ao=1.0)
M['grass'] = pbr('Lawn', 'sparse_grass', tile=2.5, ao=1.0, sat=0.8, bright=0.75)
M['dirty'] = pbr('DirtyConcrete', 'dirty_concrete', tile=3.0, ao=1.0, sat=0.4)
M['wood'] = pbr('WoodFloor', 'wood_floor', tile=2.0, ao=0.6, rough_mul=0.8)
M['plaster'] = pbr('Plaster', 'plastered_wall', tile=2.5, tint=(0.80, 0.76, 0.68), ao=0.5)
M['stairwood'] = pbr('StairPlanks', 'stair_planks', tile=1.5, rot90=True, ao=0.6, sat=0.7, bright=0.75)
M['peel'] = pbr('PeelingPaint', 'wood_peeling_paint_weathered', tile=1.2, ao=0.6)
M['trim'] = grunge(flat('Trim', (0.86, 0.86, 0.83), rough=0.45), 0.3, 2.0)
M['trim_in'] = grunge(flat('TrimInterior', (0.82, 0.80, 0.75), rough=0.4), 0.25, 3.0)
M['glass'] = flat('WindowGlass', (0.01, 0.012, 0.015), rough=0.03, spec=0.9)
M['glass_dirty'] = grunge(flat('WindowGlassDirty', (0.10, 0.10, 0.09), rough=0.25, spec=0.7, alpha=0.45), 0.6, 6.0, 0.3)
M['curtain'] = flat('Curtain', (0.32, 0.29, 0.25), rough=0.9)
M['blind'] = flat('Blinds', (0.55, 0.53, 0.49), rough=0.6)
M['shutter'] = grunge(flat('Shutter', (0.05, 0.07, 0.06), rough=0.55), 0.4, 2.0)
M['door_red'] = grunge(flat('FrontDoor', (0.30, 0.05, 0.04), rough=0.35, coat=0.3), 0.35, 3.0)
M['brass'] = flat('Brass', (0.75, 0.56, 0.28), rough=0.3, metal=1.0)
M['flap_frame'] = flat('FlapFrame', (0.70, 0.70, 0.68), rough=0.5)
M['flap'] = flat('FlapPlastic', (0.18, 0.12, 0.07), rough=0.25, alpha=0.82)
M['metal_dark'] = flat('MetalDark', (0.05, 0.05, 0.05), rough=0.4, metal=1.0)
M['steel'] = grunge(flat('SteelRusty', (0.25, 0.24, 0.23), rough=0.55, metal=1.0), 0.6, 4.0, 0.35)
M['osb'] = grunge(flat('Subfloor', (0.48, 0.36, 0.22), rough=0.8), 0.5, 4.0)
M['joist'] = grunge(flat('Joist', (0.55, 0.42, 0.27), rough=0.75), 0.4, 2.0)
M['gutter'] = flat('Gutter', (0.80, 0.80, 0.78), rough=0.35, metal=0.3)
M['white_door'] = grunge(flat('BasementDoorPaint', (0.78, 0.76, 0.70), rough=0.5), 0.55, 3.0, 0.45)
M['lamp_glass'] = emission_mat('PorchLampGlow', (1.0, 0.72, 0.42), 6.0)
M['basement_glow'] = emission_mat('BasementWindowGlow', ORANGE, 2.5)
M['paper'] = flat('NewspaperBag', (0.55, 0.52, 0.45), rough=0.3, spec=0.6)
M['mailbox'] = flat('MailboxBlack', (0.03, 0.03, 0.03), rough=0.35, metal=0.6)
M['flag_red'] = flat('MailFlag', (0.6, 0.03, 0.02), rough=0.4)
M['drywall'] = pbr('Drywall', 'plastered_wall', tile=2.0, tint=(0.62, 0.60, 0.56), ao=0.6)
M['well'] = grunge(flat('WindowWellMetal', (0.55, 0.56, 0.56), rough=0.4, metal=1.0), 0.6, 5.0, 0.4)
M['gravel'] = grunge(flat('Gravel', (0.30, 0.29, 0.27), rough=0.9), 0.8, 40.0, 0.3)
M['mulch'] = grunge(flat('Mulch', (0.12, 0.07, 0.04), rough=0.95), 0.7, 25.0, 0.4)
M['door_int'] = grunge(flat('InteriorDoor', (0.80, 0.78, 0.72), rough=0.45), 0.3, 3.0)


class MB:
    """Accumulate primitive parts (with material indices) into one mesh."""
    def __init__(self):
        self.bm = bmesh.new()

    def _tag(self, vs, mi):
        for f in {f for v in vs for f in v.link_faces}:
            f.material_index = mi

    def box(self, size, center, mi=0, rot=None):
        vs = bmesh.ops.create_cube(self.bm, size=1.0)['verts']
        bmesh.ops.scale(self.bm, vec=size, verts=vs)
        if rot is not None:
            bmesh.ops.rotate(self.bm, cent=(0, 0, 0), matrix=rot, verts=vs)
        bmesh.ops.translate(self.bm, vec=center, verts=vs)
        self._tag(vs, mi)
        return vs

    def cyl(self, r, h, center, mi=0, rot=None, seg=16, r2=None):
        vs = bmesh.ops.create_cone(self.bm, cap_ends=True, segments=seg, radius1=r,
                                   radius2=r if r2 is None else r2, depth=h)['verts']
        if rot is not None:
            bmesh.ops.rotate(self.bm, cent=(0, 0, 0), matrix=rot, verts=vs)
        bmesh.ops.translate(self.bm, vec=center, verts=vs)
        self._tag(vs, mi)
        return vs

    def prism(self, pts2d, depth, mi=0):
        """Extrude a polygon in the XZ plane along +Y by depth (for gables)."""
        vs = [self.bm.verts.new((x, 0, z)) for x, z in pts2d]
        f = self.bm.faces.new(vs)
        r = bmesh.ops.extrude_face_region(self.bm, geom=[f])
        top = [e for e in r['geom'] if isinstance(e, bmesh.types.BMVert)]
        bmesh.ops.translate(self.bm, vec=(0, depth, 0), verts=top)
        bmesh.ops.recalc_face_normals(self.bm, faces=self.bm.faces)
        self._tag(vs + top, mi)

    def done(self, name, col, mats, matrix=None, swap_uv=False):
        if matrix is not None:
            bmesh.ops.transform(self.bm, matrix=matrix, verts=self.bm.verts)
        me = bpy.data.meshes.new(name)
        self.bm.normal_update()
        self.bm.to_mesh(me)
        self.bm.free()
        cube_uv(me, swap_uv)
        for m in mats:
            me.materials.append(m)
        ob = bpy.data.objects.new(name, me)
        col.objects.link(ob)
        return ob


def facade_matrix(side):
    """Map facade-local frame (x along facade, z up, -y = outward) to world for each side."""
    if side == 'front':
        return Matrix.Translation((0, HY0, 0))
    if side == 'back':
        return Matrix.Translation((0, HY1, 0)) @ Matrix.Rotation(math.pi, 4, 'Z')
    if side == 'west':
        return Matrix.Translation((HX0, 0, 0)) @ Matrix.Rotation(-math.pi / 2, 4, 'Z')
    if side == 'east':
        return Matrix.Translation((HX1, 0, 0)) @ Matrix.Rotation(math.pi / 2, 4, 'Z')


def window(col, side, cx, z0, z1, w, inside='blinds', shutters=True, basement=False, name='Win'):
    """Window in facade-local coords (outer wall face at y=0, wall interior at y=T)."""
    mb = MB()
    h = z1 - z0
    t = 0.09  # casing width
    # exterior casing
    mb.box((w + 2 * t, 0.03, t), (cx, -0.015, z1 + t / 2), 0)
    mb.box((t, 0.03, h), (cx - w / 2 - t / 2, -0.015, (z0 + z1) / 2), 0)
    mb.box((t, 0.03, h), (cx + w / 2 + t / 2, -0.015, (z0 + z1) / 2), 0)
    mb.box((w + 2 * t + 0.06, 0.07, 0.045), (cx, -0.02, z0 - 0.022), 0)          # sill
    # jamb liners (reveal) inside the opening
    mb.box((w, T, 0.02), (cx, T / 2, z1 - 0.01), 0)
    mb.box((w, T, 0.02), (cx, T / 2, z0 + 0.01), 0)
    mb.box((0.02, T, h), (cx - w / 2 + 0.01, T / 2, (z0 + z1) / 2), 0)
    mb.box((0.02, T, h), (cx + w / 2 - 0.01, T / 2, (z0 + z1) / 2), 0)
    gy = 0.07  # glass plane depth
    if basement:
        mb.box((w - 0.04, 0.006, h - 0.04), (cx, gy, (z0 + z1) / 2), 2)
        mb.box((0.03, 0.03, h - 0.04), (cx, gy, (z0 + z1) / 2), 0)
    else:
        # two sashes (double hung) with 6-over-6 grilles
        for zs0, zs1, yo in ((z0 + 0.02, (z0 + z1) / 2 + 0.02, gy + 0.03), ((z0 + z1) / 2 - 0.02, z1 - 0.02, gy)):
            sh = zs1 - zs0
            mb.box((w - 0.04, 0.006, sh - 0.06), (cx, yo, (zs0 + zs1) / 2), 1)
            for zz in (zs0 + 0.025, zs1 - 0.025):
                mb.box((w - 0.04, 0.04, 0.05), (cx, yo, zz), 0)
            for xx in (cx - w / 2 + 0.045, cx + w / 2 - 0.045):
                mb.box((0.05, 0.04, sh), (cx + (xx - cx), yo, (zs0 + zs1) / 2), 0)
            for k in (1, 2):
                mb.box((0.018, 0.012, sh - 0.05), (cx - w / 2 + 0.02 + k * (w - 0.04) / 3, yo - 0.01, (zs0 + zs1) / 2), 0)
            mb.box((w - 0.04, 0.012, 0.018), (cx, yo - 0.01, (zs0 + zs1) / 2), 0)
    if inside == 'blinds':
        mb.box((w - 0.03, 0.01, h - 0.05), (cx, T - 0.02, (z0 + z1) / 2), 3)
    elif inside == 'curtain':
        for s in (-1, 1):
            mb.box((w * 0.42, 0.04, h + 0.3), (cx + s * w * 0.33, T + 0.05, (z0 + z1) / 2 + 0.05), 4)
    elif inside == 'glow':
        # separate object: the camera script hides it once the camera is inside the house
        g = MB()
        g.box((w - 0.04, 0.005, h - 0.04), (cx, gy + 0.04, (z0 + z1) / 2), 0)
        g.done(name + '_Glow', col, [M['basement_glow']], facade_matrix(side))
    if shutters and not basement:
        for s in (-1, 1):
            mb.box((0.42, 0.035, h + 0.08), (cx + s * (w / 2 + t + 0.23), -0.03, (z0 + z1) / 2), 6)
    mats = [M['trim'], M['glass'], M['glass_dirty'], M['blind'], M['curtain'], M['basement_glow'], M['shutter']]
    return mb.done(name, col, mats, facade_matrix(side))


# ------------------------------------------------------------------ house
FRONT_GF = [-4.3, -2.3, 2.3, 4.3]
FRONT_SF = [-4.3, -2.3, 0.0, 2.3, 4.3]


def house(col, siding, interior):
    """Exterior shell (+ optional interior). Front faces -Y, outer footprint HX0..HX1, HY0..HY1."""
    parts = []
    W = HX1 - HX0
    D = HY1 - HY0
    door = (-0.52, 0.52, GF, 2.75)
    gfw = [(c - 0.48, c + 0.48, 1.45, 2.95) for c in FRONT_GF]
    sfw = [(c - 0.45, c + 0.45, 4.25, 5.6) for c in FRONT_SF]
    bw_front = [(-3.7, -2.9) + BWZ, (2.9, 3.7) + BWZ]
    side_gf = [(2.0, 3.0, 1.45, 2.95), (6.0, 7.0, 1.45, 2.95)]
    side_sf = [(2.0, 3.0, 4.25, 5.6), (6.0, 7.0, 4.25, 5.6)]
    side_b = [(4.1, 4.9, 0.0, 0.28)]
    mi = M['plaster'] if interior else None
    zf0 = BF if interior else -0.2
    # front
    parts.append(wall('Wall_Front', HX0, HX1, GF, EAVE, T, [door] + gfw, col, siding, mi, 'X', HY0 + T / 2, -1))
    parts.append(wall('Wall_Front_F', HX0, HX1, zf0, GF, T, bw_front, col, M['found'], M['block'] if interior else None, 'X', HY0 + T / 2, -1))
    # back
    parts.append(wall('Wall_Back', HX0, HX1, GF, EAVE, T, [(c - 0.48, c + 0.48, 1.45, 2.95) for c in (-4.3, -1.0, 2.3)] +
                      [(c - 0.45, c + 0.45, 4.25, 5.6) for c in (-4.3, -1.0, 2.3, 4.3)] + [(3.6, 4.5, GF, 2.7)],
                      col, siding, mi, 'X', HY1 - T / 2, 1))
    parts.append(wall('Wall_Back_F', HX0, HX1, zf0, GF, T, [], col, M['found'], M['block'] if interior else None, 'X', HY1 - T / 2, 1))
    # sides (run along Y between the front/back walls)
    for nm, x, f in (('West', HX0 + T / 2, -1), ('East', HX1 - T / 2, 1)):
        parts.append(wall(f'Wall_{nm}', HY0 + T, HY1 - T, GF, EAVE, T, side_gf + side_sf, col, siding, mi, 'Y', x, f))
        parts.append(wall(f'Wall_{nm}_F', HY0 + T, HY1 - T, zf0, GF, T, side_b, col, M['found'], M['block'] if interior else None, 'Y', x, f))
    # gables (triangles above the eaves at both ends)
    for nm, x in (('W', HX0), ('E', HX1 - T)):
        mb = MB()
        mb.prism([(HY0 - 0.02, EAVE), (HY1 + 0.02, EAVE), ((HY0 + HY1) / 2, RIDGE - 0.15)], T)
        g = mb.done(f'Gable_{nm}', col, [siding], Matrix.Translation((x + T, 0, 0)) @ Matrix.Rotation(math.pi / 2, 4, 'Z'))
        parts.append(g)
    # roof slabs
    ov, ovg = 0.45, 0.3
    run = D / 2 + ov
    rise = (RIDGE - EAVE) * run / (D / 2)
    ang = math.atan2(RIDGE - EAVE, D / 2)
    L = math.hypot(run, rise)
    mb = MB()
    for s in (-1, 1):
        rot = Matrix.Rotation(s * ang, 3, 'X')
        cy = (HY0 + HY1) / 2 - s * run / 2
        cz = RIDGE - rise / 2 + 0.06
        mb.box((W + 2 * ovg, L, 0.12), (0, cy, cz), 0, rot)
        # fascia board along the eave
        mb.box((W + 2 * ovg, 0.04, 0.22), (0, (HY0 + HY1) / 2 - s * (run + 0.0), EAVE - 0.3 * (0) - (rise - (RIDGE - EAVE)) - 0.02), 1)
    mb.box((W + 2 * ovg + 0.02, 0.18, 0.06), (0, (HY0 + HY1) / 2, RIDGE + 0.1), 0)  # ridge cap
    parts.append(mb.done('Roof', col, [M['roof'], M['trim']]))
    # rake boards + soffit + gutters + downspouts
    mb = MB()
    for x in (HX0 - ovg + 0.02, HX1 + ovg - 0.02):
        for s in (-1, 1):
            rot = Matrix.Rotation(s * ang, 3, 'X')
            mb.box((0.04, L, 0.2), (x, (HY0 + HY1) / 2 - s * run / 2, RIDGE - rise / 2 - 0.05), 0, rot)
    eave_z = RIDGE - rise
    for y in (HY0 - ov + 0.06, HY1 + ov - 0.06):
        mb.box((W + 2 * ovg, abs(ov) + 0.05, 0.02), (0, y + (0.2 if y < 4 else -0.2), eave_z - 0.04), 0)
        mb.cyl(0.06, W + 2 * ovg, (0, y - (0.04 if y < 4 else -0.04), eave_z - 0.03), 1, Matrix.Rotation(math.pi / 2, 3, 'Y'), 12)
    for x, y in ((HX0 + 0.1, HY0 - 0.08), (HX1 - 0.1, HY0 - 0.08), (HX0 + 0.1, HY1 + 0.08), (HX1 - 0.1, HY1 + 0.08)):
        mb.box((0.07, 0.05, eave_z), (x, y, eave_z / 2), 1)
    parts.append(mb.done('RoofTrim', col, [M['trim'], M['gutter']]))
    # corner boards + band between floors
    mb = MB()
    for x in (HX0 - 0.02, HX1 + 0.02):
        for y in (HY0 - 0.02, HY1 + 0.02):
            mb.box((0.14, 0.14, EAVE - GF + 0.05), (x, y, (EAVE + GF) / 2), 0)
    for y in (HY0 - 0.015, HY1 + 0.015):
        mb.box((W + 0.06, 0.03, 0.18), (0, y, SF - 0.05), 0)
        mb.box((W + 0.06, 0.05, 0.12), (0, y, GF + 0.02), 0)
    for x in (HX0 - 0.015, HX1 + 0.015):
        mb.box((0.03, D, 0.18), (x, (HY0 + HY1) / 2, SF - 0.05), 0)
        mb.box((0.05, D, 0.12), (x, (HY0 + HY1) / 2, GF + 0.02), 0)
    parts.append(mb.done('CornerBoards', col, [M['trim']]))
    # windows
    for i, c in enumerate(FRONT_GF):
        ins = 'curtain' if (interior and c > 0) else 'blinds'
        parts.append(window(col, 'front', c, 1.45, 2.95, 0.96, ins, True, name=f'Win_F_GF{i}'))
    for i, c in enumerate(FRONT_SF):
        parts.append(window(col, 'front', c, 4.25, 5.6, 0.9, 'blinds', True, name=f'Win_F_SF{i}'))
    for i, (a, b, z0, z1) in enumerate(bw_front):
        glow = interior and a < 0
        parts.append(window(col, 'front', (a + b) / 2, z0, z1, b - a, 'glow' if glow else 'none', False, True, name=f'Win_F_B{i}'))
    for side in ('west', 'east'):
        for i, (a, b, z0, z1) in enumerate(side_gf + side_sf):
            # facade-local x for side walls: west maps local x -> -world y, east local x -> world y
            cx = -(a + b) / 2 if side == 'west' else (a + b) / 2
            parts.append(window(col, side, cx, z0, z1, b - a, 'blinds', False, name=f'Win_{side}_{i}'))
        a, b, z0, z1 = side_b[0]
        cx = -(a + b) / 2 if side == 'west' else (a + b) / 2
        parts.append(window(col, side, cx, z0, z1, b - a, 'none', False, True, name=f'Win_{side}_B'))
    for i, c in enumerate((-4.3, -1.0, 2.3)):
        parts.append(window(col, 'back', -c, 1.45, 2.95, 0.96, 'blinds', False, name=f'Win_B_GF{i}'))
    for i, c in enumerate((-4.3, -1.0, 2.3, 4.3)):
        parts.append(window(col, 'back', -c, 4.25, 5.6, 0.9, 'blinds', False, name=f'Win_B_SF{i}'))
    box('BackDoor', (0.9, 0.05, 2.08), (4.05, HY1 - 0.1, GF + 1.04), col, M['shutter'])
    # window wells for the below-grade front basement windows (corrugated half-rings + gravel)
    mb = MB()
    for a, b, z0, z1 in bw_front:
        cx = (a + b) / 2
        for k in range(14):
            ang = math.pi * (k + 0.5) / 14
            r = 0.62
            tang = math.atan2(-math.cos(ang), -math.sin(ang))
            mb.box((r * math.pi / 14 + 0.01, 0.012, 0.5), (cx + r * math.cos(ang), -r * math.sin(ang), -0.15), 0,
                   Matrix.Rotation(tang, 3, 'Z'))
        mb.box((1.24, 0.62, 0.04), (cx, -0.31, -0.3), 1)
    parts.append(mb.done('WindowWells', col, [M['well'], M['gravel']]))
    return parts


def porch(col):
    mb = MB()
    mb.box((3.8, 2.2, GF), (0, -1.1, GF / 2), 0)                 # slab
    for i in range(2):                                         # steps (3 risers of 0.2)
        top = GF - 0.2 * (i + 1)
        mb.box((1.9, 0.32, top), (0, -2.2 - 0.16 - 0.32 * i, top / 2), 0)
    for x in (-1.7, 1.7):                                      # columns
        mb.box((0.2, 0.2, 2.55), (x, -1.95, GF + 1.275), 1)
        mb.box((0.28, 0.28, 0.08), (x, -1.95, GF + 0.04), 1)
        mb.box((0.28, 0.28, 0.08), (x, -1.95, GF + 2.51), 1)
    mb.box((3.8, 0.2, 0.25), (0, -1.95, GF + 2.66), 1)          # beam
    mb.box((3.8, 2.2, 0.04), (0, -1.05, GF + 2.56), 1)           # porch ceiling
    ob = mb.done('Porch', col, [M['dirty'], M['trim']])
    # porch roof (shed) with shingles
    mb = MB()
    ang = math.radians(18)
    mb.box((4.2, 2.6, 0.1), (0, -1.1, GF + 3.05), 0, Matrix.Rotation(ang, 3, 'X'))
    mb.box((4.2, 0.04, 0.2), (0, -2.35, GF + 2.7), 1)
    mb.cyl(0.055, 4.2, (0, -2.42, GF + 2.72), 2, Matrix.Rotation(math.pi / 2, 3, 'Y'), 12)
    mb.done('PorchRoof', col, [M['roof'], M['trim'], M['gutter']])
    return ob


def front_door(col):
    """Door frame, slab with the dog flap, and the flap (separate, hinged object)."""
    mb = MB()
    # frame / casing
    mb.box((0.12, 0.05, 2.25), (-0.58, -0.02, GF + 1.1), 0)
    mb.box((0.12, 0.05, 2.25), (0.58, -0.02, GF + 1.1), 0)
    mb.box((1.3, 0.05, 0.16), (0, -0.02, 2.83), 0)
    mb.box((1.04, T, 0.02), (0, T / 2, 2.74), 0)
    mb.box((0.02, T, 2.15), (-0.51, T / 2, GF + 1.07), 0)
    mb.box((0.02, T, 2.15), (0.51, T / 2, GF + 1.07), 0)
    mb.box((1.04, 0.24, 0.025), (0, 0.06, GF + 0.012), 1)  # threshold
    mb.done('FrontDoorFrame', col, [M['trim'], M['brass']])
    # slab: built like a wall with a hole for the flap
    fx0, fx1, fz0, fz1 = -0.165, 0.165, GF + 0.07, GF + 0.47
    slab = wall('FrontDoorSlab', -0.5, 0.5, GF + 0.02, 2.73, 0.045, [(fx0, fx1, fz0, fz1)], col, M['door_red'], None, 'X', 0.1)
    mb = MB()
    # raised panels on both faces
    for yo in (0.1 - 0.027, 0.1 + 0.027):
        for x0, x1, z0, z1 in ((-0.38, -0.05, GF + 1.25, GF + 2.0), (0.05, 0.38, GF + 1.25, GF + 2.0),
                               (-0.38, -0.05, GF + 0.62, GF + 1.05), (0.05, 0.38, GF + 0.62, GF + 1.05)):
            mb.box((x1 - x0, 0.012, z1 - z0), ((x0 + x1) / 2, yo, (z0 + z1) / 2), 0)
    # knob + deadbolt + kick plate + flap frame (both sides)
    for yo, s in ((0.1 - 0.035, -1), (0.1 + 0.035, 1)):
        mb.cyl(0.03, 0.06, (0.38, yo + s * 0.01, GF + 0.98), 1, Matrix.Rotation(math.pi / 2, 3, 'X'), 16)
        mb.cyl(0.02, 0.02, (0.38, yo, GF + 1.12), 1, Matrix.Rotation(math.pi / 2, 3, 'X'), 16)
        mb.box((0.9, 0.003, 0.2), (0, yo - s * 0.008, GF + 0.12), 1)
        for x0, x1, z0, z1 in ((fx0 - 0.045, fx1 + 0.045, fz1, fz1 + 0.045), (fx0 - 0.045, fx1 + 0.045, fz0 - 0.03, fz0),
                               (fx0 - 0.045, fx0, fz0, fz1), (fx1, fx1 + 0.045, fz0, fz1)):
            mb.box((x1 - x0, 0.012, z1 - z0), ((x0 + x1) / 2, yo + s * 0.004, (z0 + z1) / 2), 2)
    mb.done('FrontDoorHardware', col, [M['door_red'], M['brass'], M['flap_frame']])
    # the flap, origin at hinge (top edge) so rotation X swings it
    bm = bmesh.new()
    vs = bmesh.ops.create_cube(bm, size=1.0)['verts']
    bmesh.ops.scale(bm, vec=(fx1 - fx0 - 0.01, 0.005, fz1 - fz0 - 0.01), verts=vs)
    bmesh.ops.translate(bm, vec=(0, 0, -(fz1 - fz0) / 2), verts=vs)
    flap = obj_from_bm('DogFlap', bm, col, [M['flap']], (0, 0.1, fz1 - 0.005))
    return slab, flap


def lantern(col, name, loc, energy):
    mb = MB()
    mb.box((0.14, 0.06, 0.22), (0, 0.03, 0), 1)
    mb.box((0.18, 0.18, 0.03), (0, -0.09, 0.14), 1)
    mb.box((0.15, 0.15, 0.2), (0, -0.09, 0.02), 0)
    mb.cyl(0.02, 0.06, (0, -0.09, 0.155), 1)
    ob = mb.done(name, col, [M['lamp_glass'], M['metal_dark']])
    ob.location = loc
    ob.visible_shadow = False  # the bulb light sits inside the glass box
    l = light(name + '_L', 'POINT', (loc[0], loc[1] - 0.1, loc[2] + 0.02), energy, (1.0, 0.70, 0.42), C_LIGHT, 0.05)
    return ob, l


# ------------------------------------------------------------------ build: main house
house(C_HOUSE, M['siding'], True)
porch(C_HOUSE)
slab, flap = front_door(C_HOUSE)
lantern(C_HOUSE, 'PorchLamp', (0.85, -0.04, 2.15), 45)

# neighbor template (exterior only) in a library collection
C_NB = bpy.data.collections.new('NEIGHBOR_HOUSE')
C_LIB.children.link(C_NB)
house(C_NB, M['siding_n'], False)
porch(C_NB)
mb = MB()
mb.box((1.0, 0.06, 2.12), (0, 0.06, GF + 1.06), 0)
mb.done('NB_Door', C_NB, [M['shutter']])

# garage (main)
def garage(col, siding):
    gx0, gx1, gy0, gy1, gh = 6.0, 12.2, 0.8, 7.4, 3.0
    parts = []
    parts.append(wall('Garage_Front', gx0, gx1, 0, gh, T, [(6.6, 11.6, 0.0, 2.3)], col, siding, None, 'X', gy0 + T / 2))
    parts.append(wall('Garage_Back', gx0, gx1, 0, gh, T, [], col, siding, None, 'X', gy1 - T / 2))
    parts.append(wall('Garage_East', gy0 + T, gy1 - T, 0, gh, T, [(3.5, 4.5, 1.2, 2.2)], col, siding, None, 'Y', gx1 - T / 2))
    mb = MB()
    for i in range(4):  # sectional garage door panels
        mb.box((5.0, 0.05, 0.56), ((6.6 + 11.6) / 2, gy0 + 0.12, 0.29 + i * 0.575), 0)
    mb.box((5.3, 0.04, 0.1), ((6.6 + 11.6) / 2, gy0 - 0.02, 2.35), 1)
    mb.box((0.1, 0.04, 2.35), (6.55, gy0 - 0.02, 1.17), 1)
    mb.box((0.1, 0.04, 2.35), (11.65, gy0 - 0.02, 1.17), 1)
    mb.done('GarageDoor', col, [grunge(flat('GarageDoorPaint', (0.75, 0.75, 0.72), rough=0.45), 0.5, 2.0), M['trim']])
    ang = math.atan2(1.6, (gy1 - gy0) / 2)
    run = (gy1 - gy0) / 2 + 0.35
    L = run / math.cos(ang)
    mb = MB()
    for s in (-1, 1):
        mb.box((gx1 - gx0 + 0.5, L, 0.1), ((gx0 + gx1) / 2, (gy0 + gy1) / 2 - s * run / 2, gh + 1.6 - run * math.tan(ang) / 2 + 0.05), 0,
               Matrix.Rotation(s * ang, 3, 'X'))
    mb.done('GarageRoof', col, [M['roof']])
    return parts

garage(C_HOUSE, M['siding'])
gab = MB()
gab.prism([(0.8, 3.0), (7.4, 3.0), (4.1, 4.55)], T)
gab.done('Garage_GableE', C_HOUSE, [M['siding']], Matrix.Translation((12.2, 0, 0)) @ Matrix.Rotation(math.pi / 2, 4, 'Z'))

# ------------------------------------------------------------------ interior: ground floor
def slab_with_hole(name, x0, x1, y0, y1, z0, z1, hole, col, mat):
    hx0, hx1, hy0, hy1 = hole
    mb = MB()
    mb.box((x1 - x0, hy0 - y0, z1 - z0), ((x0 + x1) / 2, (y0 + hy0) / 2, (z0 + z1) / 2))
    mb.box((x1 - x0, y1 - hy1, z1 - z0), ((x0 + x1) / 2, (hy1 + y1) / 2, (z0 + z1) / 2))
    mb.box((hx0 - x0, hy1 - hy0, z1 - z0), ((x0 + hx0) / 2, (hy0 + hy1) / 2, (z0 + z1) / 2))
    mb.box((x1 - hx1, hy1 - hy0, z1 - z0), ((hx1 + x1) / 2, (hy0 + hy1) / 2, (z0 + z1) / 2))
    return mb.done(name, col, [mat])

IX0, IX1, IY0, IY1 = HX0 + T, HX1 - T, HY0 + T, HY1 - T
hole = (STAIR['x0'], STAIR['x1'], STAIR['y0'], STAIR['y1'])
slab_with_hole('GF_Floor', IX0, IX1, IY0, IY1, GF - 0.02, GF, hole, C_INT, M['wood'])
slab_with_hole('GF_Subfloor', IX0, IX1, IY0, IY1, JOIST_TOP, GF - 0.02, hole, C_BASE, M['osb'])
box('GF_Ceiling', (IX1 - IX0, IY1 - IY0, 0.1), (0, (IY0 + IY1) / 2, CEIL + 0.05), C_INT, flat('Ceiling', (0.75, 0.73, 0.69), rough=0.8))
box('SF_FloorBlock', (IX1 - IX0, IY1 - IY0, SF - CEIL - 0.1), (0, (IY0 + IY1) / 2, (CEIL + 0.1 + SF) / 2), C_INT, M['osb'])

# hallway partitions (0.12 thick, plaster both sides)
PT = 0.12
HALL_X0, HALL_X1, HALL_Y1 = -0.8, 0.8, 6.6
wall('Hall_Left', IY0, HALL_Y1, GF, CEIL, PT, [(4.55, 5.45, GF, 2.65)], C_INT, M['plaster'], None, 'Y', HALL_X0)
wall('Hall_Right', IY0, HALL_Y1, GF, CEIL, PT, [(1.3, 3.7, GF, 2.8), (5.2, 6.0, GF, 2.65)], C_INT, M['plaster'], None, 'Y', HALL_X1)
wall('Hall_End', HALL_X0 - PT / 2, HALL_X1 + PT / 2, GF, CEIL, PT, [(-0.45, 0.45, GF, 2.65)], C_INT, M['plaster'], None, 'X', HALL_Y1)
wall('Room_Div', HALL_X1, IX1, GF, CEIL, PT, [], C_INT, M['plaster'], None, 'X', 4.3)
# closed doors: hall end (kitchen), right wall (bathroom)
box('Door_HallEnd', (0.88, 0.04, 2.03), (0, HALL_Y1 - 0.03, GF + 1.015), C_INT, M['door_int'])
box('Door_Bath', (0.04, 0.78, 2.03), (HALL_X1 + 0.03, 5.6, GF + 1.015), C_INT, M['door_int'])
mb = MB()
mb.cyl(0.025, 0.07, (0.3, HALL_Y1 - 0.07, GF + 0.98), 0, Matrix.Rotation(math.pi / 2, 3, 'X'), 12)
mb.cyl(0.025, 0.07, (HALL_X1 - 0.02, 5.9, GF + 0.98), 0, Matrix.Rotation(math.pi / 2, 3, 'Y'), 12)
mb.done('DoorKnobs', C_INT, [M['brass']])
# baseboards + door casings in the hall
mb = MB()
for x, s in ((HALL_X0 + PT / 2 + 0.006, 1), (HALL_X1 - PT / 2 - 0.006, -1)):
    for y0, y1 in ((IY0, 4.5 if s > 0 else 1.25), ((5.5, HALL_Y1) if s > 0 else (3.75, 5.15))):
        mb.box((0.012, y1 - y0, 0.12), (x, (y0 + y1) / 2, GF + 0.06), 0)
for y in (4.5, 5.5):
    mb.box((0.03, 0.08, 2.1), (HALL_X0 + PT / 2 + 0.015, y, GF + 1.05), 0)
mb.box((0.03, 1.08, 0.08), (HALL_X0 + PT / 2 + 0.015, 5.0, 2.69), 0)
mb.done('Hall_Trim', C_INT, [M['trim_in']])

# stair-well walls (drywall) and the basement stair
SW = STAIR
wall('Stair_WallS', SW['x0'], SW['x1'] - PT / 2, -0.55, CEIL, PT, [], C_INT, M['drywall'], None, 'X', SW['y0'] - PT / 2)
wall('Stair_WallN', SW['x0'], SW['x1'] - PT / 2, BF, CEIL, PT, [], C_INT, M['drywall'], None, 'X', SW['y1'] + PT / 2)
wall('Stair_WallW', SW['y0'] - PT, SW['y1'] + PT, JOIST_BOT - 0.1, CEIL, PT, [], C_INT, M['drywall'], None, 'Y', SW['x0'] - PT / 2)

NSTEP = 13
RISE = (GF - BF) / NSTEP
RUN = 0.262
mb = MB()
sx_top = HALL_X0 - PT / 2 - 0.02
for i in range(NSTEP - 1):
    ztop = GF - RISE * (i + 1)
    x = sx_top - RUN * (i + 0.5)
    mb.box((RUN + 0.03, SW['y1'] - SW['y0'] - 0.04, 0.035), (x, (SW['y0'] + SW['y1']) / 2, ztop - 0.0175), 0)
    mb.box((0.02, SW['y1'] - SW['y0'] - 0.04, RISE - 0.035), (x + RUN / 2 - 0.01, (SW['y0'] + SW['y1']) / 2, ztop + RISE / 2 - 0.0175), 0)
x_bot = sx_top - RUN * (NSTEP - 1)
# stringers
ang = math.atan2(GF - BF, sx_top - x_bot)
L = math.hypot(GF - BF, sx_top - x_bot)
for y in (SW['y0'] + 0.03, SW['y1'] - 0.03):
    mb.box((L + 0.3, 0.04, 0.28), ((sx_top + x_bot) / 2 - 0.05, y, (GF + BF) / 2 - 0.12), 1, Matrix.Rotation(-ang, 3, 'Y'))
# handrail on the open (south) side: posts where the bulkhead wall stops, rail parallel to the pitch
hr_z = 0.9
def stair_z(x):
    return GF - (sx_top - x) * math.tan(ang)
xs = [x for x in (sx_top - 0.3 - k * 0.45 for k in range(9)) if stair_z(x) < -0.45 and x > x_bot + 0.1]
for px in xs:
    mb.box((0.04, 0.04, hr_z), (px, SW['y0'] + 0.03, stair_z(px) + hr_z / 2), 1)
xa, xb = xs[0] + 0.1, xs[-1] - 0.1
pa, pb = Vector((xa, SW['y0'] + 0.03, stair_z(xa) + hr_z)), Vector((xb, SW['y0'] + 0.03, stair_z(xb) + hr_z))
mb.cyl(0.024, (pb - pa).length, (pa + pb) / 2, 1, (pb - pa).to_track_quat('Z', 'Y').to_matrix(), 12)
# doubled headers around the stair opening
for y in (SW['y0'] - 0.05, SW['y1'] + 0.05):
    mb.box((SW['x1'] - SW['x0'], 0.09, JOIST_TOP - JOIST_BOT), ((SW['x0'] + SW['x1']) / 2, y, (JOIST_TOP + JOIST_BOT) / 2), 1)
mb.done('BasementStair', C_BASE, [M['stairwood'], M['joist']])

# basement door: hinged on the NORTH jamb, swings into the hall towards the approaching camera.
# origin at the hinge; the slab extends along local -Y; open = rotation_euler.z ~ +1.6
bm = bmesh.new()
vs = bmesh.ops.create_cube(bm, size=1.0)['verts']
bmesh.ops.scale(bm, vec=(0.04, 0.86, 2.02), verts=vs)
bmesh.ops.translate(bm, vec=(0, -0.43, 1.01), verts=vs)
for zc in (0.55, 1.45):  # panels
    for s in (-1, 1):
        v2 = bmesh.ops.create_cube(bm, size=1.0)['verts']
        bmesh.ops.scale(bm, vec=(0.012, 0.6, 0.62), verts=v2)
        bmesh.ops.translate(bm, vec=(s * 0.024, -0.43, zc), verts=v2)
v3 = bmesh.ops.create_cone(bm, cap_ends=True, segments=12, radius1=0.026, radius2=0.026, depth=0.14)['verts']
bmesh.ops.rotate(bm, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'Y'), verts=v3)
bmesh.ops.translate(bm, vec=(0, -0.78, 0.98), verts=v3)
bdoor = obj_from_bm('BasementDoor', bm, C_INT, [M['white_door']], (HALL_X0, 5.44, GF + 0.01))
bdoor.rotation_euler.z = 1.5  # open for the test renders; the camera script animates it

# ------------------------------------------------------------------ basement shell details
# joists (span Y), skipping the stair opening; steel beam + lally columns
mb = MB()
x = IX0 + 0.2
while x < IX1 - 0.1:
    if SW['x0'] - 0.05 < x < SW['x1'] + 0.05:
        segs = ((IY0, SW['y0']), (SW['y1'], IY1))
    else:
        segs = ((IY0, IY1),)
    for y0, y1 in segs:
        mb.box((0.045, y1 - y0, JOIST_TOP - JOIST_BOT), (x, (y0 + y1) / 2, (JOIST_TOP + JOIST_BOT) / 2), 0)
    x += 0.406
mb.box((IX1 - IX0, 0.13, 0.24), (0, 3.2, JOIST_BOT - 0.12), 1)
for cx in (-1.6, 2.4):
    mb.cyl(0.045, JOIST_BOT - 0.24 - BF, (cx, 3.2, (BF + JOIST_BOT - 0.24) / 2), 1, None, 16)
    mb.box((0.18, 0.18, 0.012), (cx, 3.2, BF + 0.006), 1)
mb.done('Basement_Joists', C_BASE, [M['joist'], M['steel']])
box('Basement_Floor', (IX1 - IX0, IY1 - IY0, 0.1), (0, (IY0 + IY1) / 2, BF - 0.05), C_BASE, M['bfloor'])

# water heater + furnace in the NE corner
cyl('WaterHeater', 0.28, 1.5, (4.9, 7.9, BF), C_BASE, grunge(flat('HeaterWhite', (0.75, 0.74, 0.70), rough=0.4), 0.5, 2.0))
box('Furnace', (0.8, 0.7, 1.4), (3.9, 8.1, BF), C_BASE, grunge(flat('FurnaceGrey', (0.45, 0.45, 0.44), rough=0.5, metal=0.4), 0.5, 3.0), bottom=True)
box('Duct', (0.5, 7.4, 0.3), (3.9, 4.3, JOIST_BOT - 0.15), C_BASE, M['gutter'])

# ------------------------------------------------------------------ Poly Haven props
def put(asset, loc, rot=0.0, col=C_EXT, scale=1.0, **kw):
    root, objs = ph_group(asset, col, **kw)
    place(root, loc, rot, scale)
    return root, objs

def centred(objs):
    """Poly Haven variant sheets lay objects out along X; pull each to the group origin."""
    for o in objs:
        o.location.x = o.location.y = 0.0
    return objs

# street lamps both sides: lantern head 3.2..3.7 m; the pole skips shadow casting so the
# point light inside the glass is not blocked
lamp_root, lamp_objs = ph_group('street_lamp_01', C_STREET)
for o in lamp_objs:
    o.visible_shadow = False
    for ms in o.material_slots:
        if ms.material and ms.material.name.startswith('street_lamp_01_bulb'):
            b = [n for n in ms.material.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'][0]
            b.inputs['Emission Color'].default_value = srgb((1.0, 0.62, 0.30))
            b.inputs['Emission Strength'].default_value = 40.0
place(lamp_root, (-12, -12.4, 0.0), math.pi)
LAMPS = [(-12, -12.4, math.pi), (12, -12.4, math.pi), (-36, -12.4, math.pi), (36, -12.4, math.pi),
         (0, -22.6, 0), (-24, -22.6, 0), (24, -22.6, 0)]
for i, (x, y, r) in enumerate(LAMPS[1:]):
    instance_group(lamp_root, lamp_objs, C_STREET, f'street_lamp_{i + 1}', (x, y, 0), r)
for i, (x, y, r) in enumerate(LAMPS):
    l = light(f'StreetLamp_L{i}', 'POINT', (x, y, 3.42), 220, (1.0, 0.62, 0.30), C_LIGHT, 0.08)

_, hyd = put('fire_hydrant', (-7.5, -12.9, 0), 0.3, C_STREET)
for o in hyd:                      # the sheet holds a clean and an aged hydrant side by side: keep one
    if 'aged' in o.name:
        bpy.data.objects.remove(o)
put('water_manhole_cover', (-15, -17.4, -0.11), 0, C_STREET)
put('utility_box_01', (15.5, -11.0, 0.0), 0, C_STREET)
put('covered_car', (-9.0, -15.0, -0.12), math.pi / 2, C_STREET)   # wheels on the asphalt (road top -0.12)
put('metal_trash_can', (12.6, -12.0, 0.0), 0.4, C_STREET)
tb_root, tb = put('trashbag', (13.3, -12.1, 0.0), 1.0, C_STREET)
instance_group(tb_root, tb, C_STREET, 'trashbag_2', (13.0, -11.6, 0.0), 2.1)
instance_group(tb_root, tb, C_STREET, 'trashbag_3', (13.5, -11.5, 0.0), -0.6, 0.85)
put('garden_gnome', (-3.4, -5.2, 0.0), 0.5, C_HOUSE)
put('exterior_aircon_unit', (HX0 - 0.45, 6.5, 0.32), -math.pi / 2, C_HOUSE)
put('planter_box_01', (-1.4, -2.0, GF), 0, C_HOUSE)

# shrubs in the mulch bed along the foundation (one variant each, LOD1)
SHRUBS = []
for v in 'abcd':
    r_, o_ = ph_group('shrub_02', C_HOUSE, names=[f'shrub_02_{v}_LOD1'])
    centred(o_)
    SHRUBS.append((r_, o_))
for i, (x, rz) in enumerate(((-4.9, 0.2), (-1.7, 1.8), (1.6, 3.0), (4.9, 0.7), (-5.4, 2.4), (5.4, 1.1))):
    r_, o_ = SHRUBS[i % 4]
    if i < 4:
        place(r_, (x, -0.55, 0), rz)
    else:
        instance_group(r_, o_, C_HOUSE, f'shrub_{i}', (x, -0.5, 0), rz, 0.8)

# trees: small deciduous on lawns, pines behind houses (LOD reduced)
ts_root, ts_objs = ph_group('tree_small_02', C_EXT, names=['tree_small_02_LOD1'])
centred(ts_objs)
place(ts_root, (-8.5, -6.5, 0), 0.4, 1.6)
for i, (x, y, r, s) in enumerate(((17.0, -6.0, 2.0, 1.4), (-28.0, -5.0, 1.0, 1.7), (30.0, -7.0, 0.3, 1.5),
                                  (-14.0, -30.0, 2.5, 1.6), (10.0, -29.0, 1.2, 1.4))):
    instance_group(ts_root, ts_objs, C_EXT, f'tree_small_{i}', (x, y, 0), r, s)
pine_root, pine_objs = ph_group('pine_tree_01', C_EXT, names=['pine_tree_01_a_LOD2'])
centred(pine_objs)
place(pine_root, (-9.0, 15.0, 0), 0.0, 0.9)
for i, (x, y, r, s) in enumerate(((7.0, 18.0, 1.0, 1.0), (-20.0, 12.0, 2.0, 0.8), (22.0, 14.0, 0.5, 0.9),
                                  (-2.0, 22.0, 1.5, 1.1), (-35.0, 16.0, 0.2, 1.0), (36.0, 18.0, 2.2, 0.95),
                                  (-12.0, -45.0, 1.1, 1.0), (14.0, -46.0, 0.4, 0.9))):
    instance_group(pine_root, pine_objs, C_EXT, f'pine_{i}', (x, y, 0), r, s)

# ------------------------------------------------------------------ ground: road, curbs, sidewalks, lawns, driveway
mb = MB()
mb.box((140, 8.0, 0.1), (0, -17.55, -0.17), 0)                                    # road
for y in (-13.475, -21.625):
    mb.box((140, 0.15, 0.22), (0, y, -0.06), 1)                                  # curbs
for y0, y1 in ((-11.5, -10.0), (-25.1, -23.6)):
    mb.box((140, y1 - y0, 0.06), (0, (y0 + y1) / 2, 0.02), 1)                     # sidewalks
mb.box((1.2, 7.1, 0.05), (0, -6.45, 0.02), 1)                                      # walkway to porch
mb.box((1.6, 0.8, 0.05), (0, -2.75, 0.02), 1)
mb.done('Hardscape', C_STREET, [M['asphalt'], M['pave']])
box('Driveway', (5.2, 12.3, 0.05), (9.1, -5.35, 0.02), C_STREET, M['dirty'])
box('Driveway2', (5.2, 2.0, 0.08), (9.1, -10.75, -0.02), C_STREET, M['dirty'])
mb = MB()
mb.box((140, 12.4, 0.1), (0, -7.2, -0.05), 0)                  # front lawns up to the bed
mb.box((140, 1.9, 0.1), (0, -12.45, -0.05), 0)
mb.box((140, 1.9, 0.1), (0, -22.6, -0.05), 0)
mb.box((140, 30, 0.1), (0, -40.1, -0.05), 0)
mb.box((140, 40, 0.1), (0, 29.0, -0.05), 0)
mb.box((50, 9.0, 0.1), (-31, 4.5, -0.05), 0)
mb.box((56.2, 10.0, 0.1), (34.1, 4.0, -0.05), 0)
for x0, x1 in ((-70, HX0), (HX1, 70)):                          # lawn beside the house front
    mb.box((x1 - x0, 1.0, 0.1), ((x0 + x1) / 2, -0.5, -0.05), 0)
mb.done('Lawns', C_STREET, [M['grass']])
# mulch bed along the front foundation, cut around the two window wells
mb = MB()
cuts = [(-3.3 - 0.64, -3.3 + 0.64), (3.3 - 0.64, 3.3 + 0.64)]
xs_ = [HX0] + [c for ab in cuts for c in ab] + [HX1]
for x0, x1 in zip(xs_[::2], xs_[1::2]):
    mb.box((x1 - x0, 1.0, 0.12), ((x0 + x1) / 2, -0.5, -0.05), 0)
for a, b in cuts:
    mb.box((b - a, 0.36, 0.12), ((a + b) / 2, -0.82, -0.05), 0)
mb.done('MulchBed', C_HOUSE, [M['mulch']])
# road markings: faded double yellow
box('RoadLine', (140, 0.25, 0.005), (0, -17.55, -0.118), C_STREET, flat('RoadPaint', (0.55, 0.45, 0.15), rough=0.6))

# mailbox (flag up, stuffed) + newspapers piled on the walkway/porch: nobody has come out for weeks
mb = MB()
mb.box((0.08, 0.08, 1.1), (0, 0, 0.55), 2)
mb.box((0.2, 0.5, 0.18), (0, 0, 1.18), 0)
mb.cyl(0.1, 0.5, (0, 0, 1.27), 0, Matrix.Rotation(math.pi / 2, 3, 'X'), 16)
mb.box((0.02, 0.03, 0.2), (0.11, 0.1, 1.35), 1)
mb.box((0.02, 0.1, 0.06), (0.11, 0.16, 1.44), 1)
mbx = mb.done('Mailbox', C_STREET, [M['mailbox'], M['flag_red'], M['joist']])
mbx.location = (6.2, -12.2, 0)
mb = MB()
for i in range(9):
    x, y = R.uniform(-1.0, 1.2), R.uniform(-9.5, -2.9)
    z = 0.035 if y < -2.9 else GF + 0.035
    mb.cyl(0.035, 0.30, (x, y, z), 0, Matrix.Rotation(R.uniform(0, 3.14), 3, 'Z') @ Matrix.Rotation(math.pi / 2, 3, 'Y'), 12)
for i in range(5):
    mb.cyl(0.035, 0.30, (R.uniform(-1.2, 1.2), R.uniform(-1.8, -0.4), GF + 0.035), 0,
           Matrix.Rotation(R.uniform(0, 3.14), 3, 'Z') @ Matrix.Rotation(math.pi / 2, 3, 'Y'), 12)
mb.done('Newspapers', C_HOUSE, [M['paper']])

# neighbors via collection instances (different siding colour each side)
def nb(name, loc, rot):
    e = bpy.data.objects.new(name, None)
    e.instance_type = 'COLLECTION'
    e.instance_collection = C_NB
    e.location = loc
    e.rotation_euler = (0, 0, rot)
    C_EXT.objects.link(e)
for i, (x, y, r) in enumerate(((-26, 0, 0), (28, 0, 0), (-52, 0, 0), (-12, -35.2, math.pi), (14, -35.2, math.pi), (40, -35.2, math.pi), (-38, -35.2, math.pi))):
    nb(f'Neighbor_{i}', (x, y, 0), r)

# ------------------------------------------------------------------ interior props (hall + living room)
# family photos on the left hall wall (frames face -Y with the back at y=0 -> rotate +90 deg to face +X)
for i, (a, y, z) in enumerate((('hanging_picture_frame_01', 1.2, 1.5), ('hanging_picture_frame_02', 2.6, 1.6), ('hanging_picture_frame_03', 3.7, 1.45))):
    put(a, (HALL_X0 + PT / 2 + 0.003, y, GF + z), math.pi / 2, C_INT)
put('side_table_tall_01', (HALL_X0 + 0.3, 0.75, GF), 0, C_INT)
put('wall_clock', (HALL_X1 - PT / 2 - 0.005, 4.0, GF + 2.1), -math.pi / 2, C_INT)
put('potted_plant_02', (HALL_X0 + 0.4, 6.15, GF), 0, C_INT)
put('sofa_02', (3.3, 3.3, GF), 0, C_INT)
put('side_table_01', (3.3, 0.6, GF), 0, C_INT)
put('television_02', (3.3, 0.6, GF + 0.55), math.pi, C_INT)
put('potted_plant_01', (5.2, 0.8, GF), 0, C_INT)
put('dining_chair_02', (-3.0, 3.0, GF), 0.4, C_INT)

# basement storage (east side)
put('steel_frame_shelves_01', (5.4, 2.2, BF), -math.pi / 2, C_BASE)
put('steel_frame_shelves_02', (5.4, 3.6, BF), -math.pi / 2, C_BASE)
cb_root, cb = put('cardboard_box_01', (4.7, 1.2, BF + 0.007), 0.2, C_BASE)   # mesh sits 0.163 above its origin
instance_group(cb_root, cb, C_BASE, 'cardboard_box_2', (4.75, 1.25, BF + 0.35), -0.15)
instance_group(cb_root, cb, C_BASE, 'cardboard_box_3', (4.6, 1.85, BF + 0.007), 1.4)
instance_group(cb_root, cb, C_BASE, 'cardboard_box_4', (-5.3, 6.6, BF + 0.007), 0.1)
put('plastic_crate_02', (4.6, 4.4, BF), 0.3, C_BASE)
put('old_tyre', (4.9, 5.6, BF + 0.3), math.pi / 2 - 0.2, C_BASE)
put('wooden_crate_01', (2.0, 7.6, BF), 0.1, C_BASE)
put('metal_jerrycan', (2.8, 7.9, BF), 0.5, C_BASE)
_, pipes = put('modular_pipes', (-5.6, 8.45, BF + 0.27), 0, C_BASE)
bpy.context.view_layer.update()
for o in pipes:                    # the kit sheet is wider than the corner: drop what pokes through walls/ceiling
    ws = [o.matrix_world @ Vector(c) for c in o.bound_box]
    if o.type == 'MESH' and (min(w.x for w in ws) < IX0 or max(w.y for w in ws) > IY1 or max(w.z for w in ws) > JOIST_BOT):
        bpy.data.objects.remove(o)
put('mounted_fluorescent_lights', (1.0, 6.0, JOIST_BOT), 0, C_BASE)
put('pull_chain_light_socket', (-3.0, 3.6, JOIST_BOT), 0, C_BASE)
put('lightbulb_01', (-3.0, 3.6, JOIST_BOT - 0.2), 0, C_BASE)
put('street_rat', (-4.4, 0.6, BF), 0.8, C_BASE)
tr, _ = put('trashbag', (-5.2, 4.2, BF), 0.3, C_BASE)

# ------------------------------------------------------------------ lights + world
lm = light('Moon', 'SUN', (0, 0, 30), 0.5, (0.55, 0.68, 1.0), C_LIGHT)
lm.rotation_euler = (math.radians(55), 0, math.radians(200))
lm.data.angle = math.radians(1.0)

# night sky: the HDRI desaturated and pushed to blue. No world volume: in EEVEE it swallows the
# sky and sun light entirely, so the haze is a bounded volume object instead.
w = bpy.data.worlds.new('NightWorld')
scene.world = w
w.use_nodes = True
nt = w.node_tree
nt.nodes.clear()
tc = nt.nodes.new('ShaderNodeTexCoord')
mp = nt.nodes.new('ShaderNodeMapping')
mp.inputs['Rotation'].default_value = (0, 0, math.radians(120))
env = nt.nodes.new('ShaderNodeTexEnvironment')
env.image = bpy.data.images.load(f'{PH}/hdris/moonless_golf_2k.hdr')
hs = nt.nodes.new('ShaderNodeHueSaturation')
hs.inputs['Saturation'].default_value = 0.3
tint = nt.nodes.new('ShaderNodeMix')
tint.data_type = 'RGBA'
tint.blend_type = 'MULTIPLY'
tint.inputs['Factor'].default_value = 1.0
tint.inputs['B'].default_value = (0.30, 0.42, 0.85, 1)
bg = nt.nodes.new('ShaderNodeBackground')
bg.name = 'Sky'
bg.inputs['Strength'].default_value = 0.22
out = nt.nodes.new('ShaderNodeOutputWorld')
nt.links.new(tc.outputs['Generated'], mp.inputs[0])
nt.links.new(mp.outputs[0], env.inputs[0])
nt.links.new(env.outputs[0], hs.inputs['Color'])
nt.links.new(hs.outputs[0], tint.inputs['A'])
nt.links.new(tint.outputs['Result'], bg.inputs[0])
nt.links.new(bg.outputs[0], out.inputs['Surface'])

fog_m, fnt = new_mat('StreetHaze')
fout = [n for n in fnt.nodes if n.type == 'OUTPUT_MATERIAL'][0]
pv = fnt.nodes.new('ShaderNodeVolumePrincipled')
pv.inputs['Density'].default_value = 0.012
pv.inputs['Anisotropy'].default_value = 0.6
pv.inputs['Color'].default_value = (0.75, 0.8, 0.9, 1)
fnt.links.new(pv.outputs[0], fout.inputs['Volume'])
box('StreetHaze', (130, 80, 14), (0, -14, 6.5), C_EXT, fog_m)

# faint fill so the hallway/basement read in the beast POV (kept very low)
light('Hall_Moonfill', 'AREA', (0.0, 0.5, 2.4), 6, (0.55, 0.65, 1.0), C_LIGHT, size=(1.2, 0.6), rot=(math.radians(60), 0, 0))

# ------------------------------------------------------------------ render settings
scene.render.engine = 'BLENDER_EEVEE'
scene.render.resolution_x, scene.render.resolution_y = 1920, 1080
scene.render.fps = 24
scene.frame_start, scene.frame_end = 1, 5254
ee = scene.eevee
ee.taa_render_samples = 64
ee.use_raytracing = True
ee.use_shadows = True
ee.use_volumetric_shadows = True
ee.volumetric_tile_size = '8'
ee.volumetric_samples = 64
ee.volumetric_end = 90
ee.use_fast_gi = True
scene.view_settings.view_transform = 'AgX'
scene.view_settings.look = 'AgX - Medium High Contrast'
scene.view_settings.exposure = 0.8

# ------------------------------------------------------------------ test cameras
def cam(name, loc, target, lens=24):
    cd = bpy.data.cameras.new(name)
    cd.lens = lens
    cd.clip_start = 0.02
    cd.clip_end = 300
    ob = bpy.data.objects.new(name, cd)
    C_CAM.objects.link(ob)
    ob.location = loc
    look_at(ob, target, 'Y')
    return ob

cam('TC_street', (-16, -17.0, 0.6), (0, 0, 2.5), 24)
cam('TC_lawn', (-1.5, -8.5, 0.5), (0, 0, 1.6), 20)
cam('TC_door', (0.2, -1.6, 0.9), (0, 0, 0.9), 24)
cam('TC_hall', (0.0, 0.5, 0.95), (-0.4, 6.0, 0.95), 18)
cam('TC_stairtop', (-0.5, 4.95, 1.0), (-3.5, 4.95, -1.2), 18)
cam('TC_basement', (-4.2, 4.9, -1.5), (-3.0, 1.6, -1.3), 18)
cam('TC_wide', (-25, -30, 7), (0, 0, 2), 28)
scene.camera = bpy.data.objects['TC_street']

os.makedirs(f'{CLIP}/blend', exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=f'{CLIP}/blend/env.blend', compress=True)
print('ENV SAVED', len(bpy.data.objects), 'objects')
