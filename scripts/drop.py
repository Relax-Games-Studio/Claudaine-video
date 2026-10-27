"""The drop from the desk syringe, in slow motion. It hangs as a bead on the needle tip, swells from T_SWELL, necks
and pinches off at T_PINCH, falls wobbling past the desk edge with a satellite droplet behind it and splashes on the
floor at T_LAND (a crown, flung droplets), where the glowing puddle spreads. TIP: the needle tip (DESK_ROOT space);
z_at(t): the drop's centre height, shared with the camera that follows it down. build_scene calls build()."""
import bmesh, math, random
from mathutils import Vector
from lib_build import srgb, new_mat, principled, obj_from_bm, light
import desk, screens_rig

FPS, FRAMES = 24, 5254
T_SWELL, T_PINCH, T_LAND = 105.0, 106.6, 109.05
R_DROP = 0.0017                 # what a needle this size lets go of: ~20 microlitres
R_SAT = 0.00042
DIR = Vector((-math.sin(desk.SYR_DESK_YAW), math.cos(desk.SYR_DESK_YAW), 0.0))   # along the needle, to its tip
TIP = desk.SYR_DESK_LOC + DIR * desk.SYR_NEEDLE_TIP
AXIS = TIP + DIR * 0.0001       # the hanging drop's vertical axis, just past the needle's end
STAGES = (0.0, 0.1, 0.25, 0.42, 0.58, 0.72, 0.84, 0.93, 1.0)    # growth of the hanging drop; 0.1 is the resting bead
S_REST = 0.1
SEG, RINGS = 32, 30
G = 2 * (TIP.z - R_DROP) / (T_LAND - T_PINCH) ** 2               # slow-motion gravity (~0.25 m/s^2)


def bulb(s):
    """radius and centre height (below the needle axis) of the hanging drop's bulb at growth s"""
    rb = 0.00062 + (R_DROP * 1.08 - 0.00062) * s
    zc = -(0.00015 + rb * (0.45 + 0.85 * s) + 0.0006 * max(0.0, s - 0.75) / 0.25)
    return rb, zc


def profile(s):
    """(r, z) from the top pole to the bottom pole: a cap wetting the needle's end, the bulb below it and, late in
    the growth, a thinning neck between them, blended as a smooth union"""
    rb, zc = bulb(s)
    rc = 0.00062
    neck = 0.00058 - (0.00058 - 0.0001) * (max(0.0, s - 0.7) / 0.3) ** 1.5
    top, bot = rc, zc - rb
    out = []
    for i in range(RINGS + 1):
        z = top + (bot - top) * (1 - math.cos(math.pi * i / RINGS)) / 2
        sph = lambda c, r: math.sqrt(max(0.0, r * r - (z - c) ** 2))
        bridge = neck if zc <= z <= 0.0 else 0.0
        out.append(((sph(0.0, rc) ** 8 + sph(zc, rb) ** 8 + bridge ** 8) ** 0.125, z))
    return out


def ring_coords(s):
    co = []
    for i, (r, z) in enumerate(profile(s)):
        if i in (0, RINGS):
            co.append(Vector((0.0, 0.0, z)))
            continue
        for j in range(SEG):
            a = 2 * math.pi * j / SEG
            co.append(Vector((r * math.cos(a), r * math.sin(a), z)))
    return co


def growth(t):
    """the hanging drop's growth s over time: resting bead, swelling, and after the pinch a smaller bead that
    recoils and settles"""
    if t < T_SWELL:
        return S_REST
    if t < T_PINCH:
        return S_REST + (1 - S_REST) * ((t - T_SWELL) / (T_PINCH - T_SWELL)) ** 1.25
    tau = t - T_PINCH
    return S_REST - S_REST * math.exp(-tau / 0.25) * math.cos(2 * math.pi * 2.5 * tau)


def z_at(t):
    """height of the drop's centre: the swelling bulb, then the fall, then the floor"""
    if t < T_PINCH:
        return TIP.z + bulb(growth(t))[1]
    z0 = TIP.z + bulb(1.0)[1]
    u = min(1.0, (t - T_PINCH) / (T_LAND - T_PINCH))
    return z0 - (z0 - R_DROP) * u * u


def drop_mat():
    """the drug as a liquid: clear orange, refracting, a faint glow of its own so it reads in the dark"""
    m, nt = new_mat('DropLiquid')
    if nt is None:
        return m
    b, out = principled(nt)
    b.inputs['Base Color'].default_value = srgb((1.0, 0.46, 0.14))
    b.inputs['Roughness'].default_value = 0.01
    b.inputs['IOR'].default_value = 1.36
    b.inputs['Transmission Weight'].default_value = 1.0
    b.inputs['Emission Color'].default_value = srgb((1.0, 0.32, 0.07))
    b.inputs['Emission Strength'].default_value = 0.35
    m.surface_render_method = 'DITHERED'
    m.use_raytrace_refraction = True
    m.thickness_mode = 'SPHERE'
    return m


def sphere(name, r, mat, col, seg=32):
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=seg, v_segments=seg // 2, radius=r)
    return obj_from_bm(name, bm, col, [mat], uv=False, smooth=True)


# ---------------------------------------------------------------- the splash crown
# A milk-drop coronet on the thin film the drop spreads into: a thin sheet rises out of the impact leaning outwards,
# its rim gathers into a bulging rim that breaks up into uneven fingers with beads on their tips; beads let go and
# fly, the fingers draw back and the wall sinks into the spreading film. Every frame of it is its own shape key
# (same topology), so the sheet really grows, opens and collapses instead of one shape being scaled.
T_CROWN = 0.8                   # life of the crown after impact (s, slow motion)
C_AROUND, C_FINGERS = 360, 19
SMOOTH = lambda a, b, x: 0.0 if x <= a else 1.0 if x >= b else (lambda u: u * u * (3 - 2 * u))((x - a) / (b - a))


def crown_plan(rng):
    """the random make-up of this splash: fingers (angle, length, timing, bead, launch) and slow rim waviness"""
    ph = rng.uniform(0, 2 * math.pi)
    fingers = []
    for i in range(C_FINGERS):
        det = rng.random() < 0.6
        fingers.append(dict(a=ph + 2 * math.pi * (i + rng.uniform(-0.32, 0.32)) / C_FINGERS,
                            L=rng.uniform(0.3, 1.0) ** 1.4, t_on=rng.uniform(0.05, 0.13), grow=rng.uniform(0.1, 0.18),
                            t_det=rng.uniform(0.24, 0.46) if det else None, bead=rng.uniform(1.15, 1.6),
                            vh=rng.uniform(0.02, 0.05), vz=rng.uniform(0.035, 0.07)))
    waves = [(k, rng.uniform(0, 2 * math.pi), rng.uniform(0.03, 0.08)) for k in (2, 3, 5, 7)]
    return fingers, waves


def crown_state(tau):
    """crown radius at the foot, wall height, outward lean, sheet thickness at foot and top, rim radius, film"""
    f = (1 - math.exp(-tau / 0.05)) * (1 - SMOOTH(0.3, 0.72, tau))
    R = 0.0019 + 0.0034 * (1 - math.exp(-tau / 0.17))
    return dict(f=f, R=R, H=0.0036 * f, lean=math.radians(6 + 24 * min(1.0, tau / 0.4)),
                t0=0.00042, t1=0.00011, rho=0.00016 + 0.00012 * min(1.0, tau / 0.3),
                film=0.00028 * (1 - 0.5 * tau / T_CROWN), rf=R + 0.0014 + 0.0035 * tau / T_CROWN)


def finger_len(fg, tau):
    L = 0.0024 * fg['L'] * SMOOTH(fg['t_on'], fg['t_on'] + fg['grow'], tau) * (1 - SMOOTH(0.34, 0.68, tau))
    if fg['t_det'] is not None and tau > fg['t_det']:
        L *= math.exp(-(tau - fg['t_det']) / 0.045)            # the finger snaps back once its bead is gone
    return L


def crown_profile(st, top_z, rho):
    """(r, z) across the sheet at one angle: inner film -> inner wall -> rim -> outer wall -> outer film"""
    R, lean, film = st['R'], st['lean'], st['film']
    d, n = (math.sin(lean), math.cos(lean)), (math.cos(lean), -math.sin(lean))
    h = max(top_z - film, 1e-5)
    top = (R + h * math.tan(lean), top_z)
    thick = lambda s: st['t1'] + (st['t0'] - st['t1']) * (1 - s) ** 2 + 0.0011 * (1 - s) ** 10   # flares into the film
    on = lambda s, side: (R + (top[0] - R) * s + side * n[0] * thick(s) / 2,
                          max(0.00004, film + (top_z - film) * s + side * n[1] * thick(s) / 2))
    pts = [(0.00005 + (R - thick(0) / 2 - 0.00005) * (i / 14) ** 0.7, film) for i in range(14)]
    pts += [on((i / 20) ** 0.8 * (1 - 1e-3), -1) for i in range(1, 21)]
    r_cap = max(rho, st['t1'] / 2)
    for i in range(1, 12):                                      # the rim, bulging past the sheet
        a = math.pi * i / 12
        pts.append((top[0] - n[0] * r_cap * math.cos(a) + d[0] * r_cap * 0.9 * math.sin(a),
                    top[1] - n[1] * r_cap * math.cos(a) + d[1] * r_cap * 0.9 * math.sin(a)))
    pts += [on((1 - i / 20) ** 1.25 * (1 - 1e-3), 1) for i in range(1, 21)]
    r0 = pts[-1][0]
    for i in range(1, 11):                                      # the film thinning out to its edge
        u = i / 10
        pts.append((r0 + (st['rf'] - r0) * u, max(0.00002, film * (1 - u) ** 1.5)))
    return pts


def crown_shape(plan, tau):
    """all vertices of the crown at time tau (C_AROUND profiles), plus the fingertips (angle, r, z, rim radius)"""
    fingers, waves = plan
    st = crown_state(tau)
    sig = 0.00042
    co, tips = [], []
    for j in range(C_AROUND):
        th = 2 * math.pi * j / C_AROUND
        r_top = st['R'] + st['H'] * math.tan(st['lean'])
        bump, ext = 0.0, 0.0
        for fg in fingers:
            dth = (th - fg['a'] + math.pi) % (2 * math.pi) - math.pi
            b = math.exp(-(r_top * dth / sig) ** 2)
            L = finger_len(fg, tau)
            ext += L * b
            bump = max(bump, b * min(1.0, L / 0.0004))
        wav = sum(a * math.sin(k * th + p) for k, p, a in waves)
        top_z = st['film'] + st['H'] * (1 + wav) + ext - 0.00018 * st['f'] * (1 - bump)       # cusps between fingers
        rho = st['rho'] * (1 + 0.15 * wav) + 0.00012 * bump
        for r, z in crown_profile(st, top_z, rho):
            co.append((r * math.cos(th), r * math.sin(th), z))
    for fg in fingers:
        L = finger_len(fg, tau)
        h = st['H'] + L
        tips.append((fg['a'], st['R'] + h * math.tan(st['lean']), st['film'] + h, st['rho'] + 0.00012))
    return co, tips


def crown_mesh(plan, tau):
    co, _ = crown_shape(plan, tau)
    m = len(co) // C_AROUND
    bm = bmesh.new()
    vs = [bm.verts.new(c) for c in co]
    for j in range(C_AROUND):
        a, b = vs[j * m:(j + 1) * m], vs[((j + 1) % C_AROUND) * m:((j + 1) % C_AROUND + 1) * m]
        for i in range(m - 1):
            bm.faces.new((a[i], a[i + 1], b[i + 1], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def build(B, M, col, light_col):
    mat = drop_mat()
    T = lambda f: (f - 1) / FPS
    frames = range(1, FRAMES + 1)

    # the hanging drop: one mesh, its growth stages as shape keys (piecewise linear over STAGES)
    bm = bmesh.new()
    vs = [bm.verts.new(c) for c in ring_coords(S_REST)]
    top, bot = vs[0], vs[-1]
    ring = lambda i: vs[1 + (i - 1) * SEG: 1 + i * SEG]
    for j in range(SEG):
        bm.faces.new((top, ring(1)[(j + 1) % SEG], ring(1)[j]))
        bm.faces.new((bot, ring(RINGS - 1)[j], ring(RINGS - 1)[(j + 1) % SEG]))
    for i in range(1, RINGS - 1):
        a, b = ring(i), ring(i + 1)
        for j in range(SEG):
            bm.faces.new((a[j], a[(j + 1) % SEG], b[(j + 1) % SEG], b[j]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    hang = obj_from_bm('Drop_Hanging', bm, col, [mat], tuple(AXIS), uv=False, smooth=True)
    B.adopt(hang)
    hang.shape_key_add(name='Basis')
    for s in STAGES:
        if s == S_REST:
            continue
        kb = hang.shape_key_add(name=f'S{s:.2f}', from_mix=False)
        flat = []
        for c in ring_coords(s):
            flat += c[:]
        kb.data.foreach_set('co', flat)
    sv = [growth(T(f)) for f in frames]
    for i, s in enumerate(STAGES):
        if s == S_REST:
            continue
        lo, hi = STAGES[max(0, i - 1)], STAGES[min(len(STAGES) - 1, i + 1)]
        vals = []
        for x in sv:
            if lo <= x <= s and s > lo:
                vals.append((x - lo) / (s - lo))
            elif s <= x <= hi and hi > s:
                vals.append((hi - x) / (hi - s))
            else:
                vals.append(0.0)
        screens_rig.key_series(hang.data.shape_keys, f'key_blocks["S{s:.2f}"].value', -1, vals)

    # the falling drop: lets go stretched, rings between long and flat as it falls, gone into the floor
    fall = sphere('Drop_Falling', R_DROP, mat, col)
    B.adopt(fall)
    fall.location = (AXIS.x, AXIS.y, z_at(T_PINCH))
    zs, sx, sz = [], [], []
    for f in frames:
        t = T(f)
        zs.append(z_at(t))
        if T_PINCH <= t < T_LAND:
            tau = t - T_PINCH
            k = 1 + 0.32 * math.exp(-tau / 0.55) * math.cos(2 * math.pi * 2.4 * tau)
            sx.append(1 / math.sqrt(k)); sz.append(k)
        else:
            sx.append(0.0); sz.append(0.0)
    screens_rig.key_series(fall, 'location', 2, zs)
    for i, v in ((0, sx), (1, sx), (2, sz)):
        screens_rig.key_series(fall, 'scale', i, v)

    # the satellite: a bead of the snapped neck, a moment behind
    sat = sphere('Drop_Satellite', R_SAT, mat, col, 16)
    B.adopt(sat)
    sat.location = (AXIS.x, AXIS.y, TIP.z)
    ts0, zs0 = T_PINCH + 1.5 / FPS, TIP.z - 0.0009
    zz, ss = [], []
    for f in frames:
        t = T(f)
        z = zs0 - 0.5 * G * max(0.0, t - ts0) ** 2
        zz.append(max(R_SAT, z))
        ss.append(1.0 if t >= ts0 and z > R_SAT else 0.0)
    screens_rig.key_series(sat, 'location', 2, zz)
    for i in range(3):
        screens_rig.key_series(sat, 'scale', i, ss)

    # the splash: the crown, one shape key per frame of its life, and the beads on its fingertips that let go and fly
    plan = crown_plan(random.Random(11))
    life = [f for f in frames if 0.0 <= T(f) - T_LAND < T_CROWN]
    crown = obj_from_bm('Drop_Crown', crown_mesh(plan, T(life[0]) - T_LAND), col, [mat], (AXIS.x, AXIS.y, 0.0),
                        uv=False, smooth=True)
    B.adopt(crown)
    crown.shape_key_add(name='Basis')
    for f in life[1:]:
        kb = crown.shape_key_add(name=f'F{f}', from_mix=False)
        kb.data.foreach_set('co', [c for v in crown_shape(plan, T(f) - T_LAND)[0] for c in v])
        screens_rig.key_series(crown.data.shape_keys, f'key_blocks["F{f}"].value', -1,
                               [1.0 if g == f else 0.0 for g in frames])
    for i in range(3):
        screens_rig.key_series(crown, 'scale', i, [1.0 if g in life else 0.0 for g in frames])
    tips = {f: crown_shape(plan, T(f) - T_LAND)[1] for f in life}
    for k, fg in enumerate(plan[0]):
        rb = 0.00028 * fg['bead']
        d = sphere(f'Drop_Splash{k:02d}', rb, mat, col, 16)
        B.adopt(d)
        launch = None
        px, py, pz, sc = [], [], [], []
        for f in frames:
            tau = T(f) - T_LAND
            if f in tips and (fg['t_det'] is None or tau <= fg['t_det']):
                a, r, z, rho = tips[f][k]
                L = finger_len(fg, tau)
                s = min(1.0, L / 0.0007)                       # the bead gathers as the finger grows out
                pos, scale = (r, z + rho * 0.4), s
                if fg['t_det'] is not None:
                    launch = (r, z + rho * 0.4, tau)
            elif launch and fg['t_det'] is not None and tau > fg['t_det']:
                r0, z0, t0 = launch
                dt = tau - t0
                z = z0 + fg['vz'] * dt - 0.5 * G * dt * dt
                pos, scale = (r0 + fg['vh'] * dt, max(rb, z)), 1.0 if z > rb else 0.0
            else:
                pos, scale = (0.0, 0.0), 0.0
            px.append(AXIS.x + pos[0] * math.cos(fg['a'])); py.append(AXIS.y + pos[0] * math.sin(fg['a']))
            pz.append(pos[1]); sc.append(scale)
        for i, v in ((0, px), (1, py), (2, pz)):
            screens_rig.key_series(d, 'location', i, v)
        for i in range(3):
            screens_rig.key_series(d, 'scale', i, sc)

    # the puddle spreads from the impact
    pbm = desk.puddle_mesh('FallPuddle', 0.05, random.Random(5))
    fp = obj_from_bm('FallPuddle', pbm, col, [M['puddle']], (AXIS.x, AXIS.y, 0.0005), (0, 0, 0.7), uv=False,
                     smooth=True)
    B.adopt(fp)
    ps = []
    for f in frames:
        tau = T(f) - T_LAND - 0.05
        ps.append(0.0 if tau < 0 else min(1.0, 1.02 * (1 - math.exp(-tau / 0.3))))
    for i in range(2):
        screens_rig.key_series(fp, 'scale', i, ps)

    # a cool rim from the side (the desk's front is right behind the drop) and a soft key over the lens, on only for
    # the macro shot, riding down with it and dimmed for the splash so the floor doesn't flare
    lens_side = Vector((-0.80, -0.55, 0.0)).normalized()
    lights = []
    for name, off, energy, color, size in (('DropRim', Vector((0.10, 0.03, 0.012)), 0.05, (0.82, 0.9, 1.0), 0.02),
                                           ('DropKey', lens_side * 0.06 + Vector((0.0, 0.0, 0.05)), 0.03, (1.0, 0.96, 0.9), 0.04)):
        l = light(name, 'AREA', (0, 0, 0), 0.0, color, light_col, size=(size, size))
        B.adopt(l)
        l.rotation_euler = (-off).to_track_quat('-Z', 'Y').to_euler()
        l.data.use_shadow = False
        lx, ly, lz, le = [], [], [], []
        for f in frames:
            t = T(f)
            p = Vector((AXIS.x, AXIS.y, max(0.04, z_at(t)))) + off
            lx.append(p.x); ly.append(p.y); lz.append(p.z)
            dim = 1.0 - 0.7 * min(1.0, max(0.0, (t - T_LAND + 0.35) / 0.4))
            le.append(energy * dim if T_SWELL - 0.1 <= t < 110.35 else 0.0)
        for i, v in ((0, lx), (1, ly), (2, lz)):
            screens_rig.key_series(l, 'location', i, v)
        screens_rig.key_series(l.data, 'energy', -1, le)
        lights.append(l)
    return dict(hanging=hang, falling=fall, crown=crown, puddle=fp, lights=lights)
