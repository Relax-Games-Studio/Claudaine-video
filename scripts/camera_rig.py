"""The clip camera: a shot list (keys of time / position / look-at target / lens) evaluated per frame with
monotone Hermite splines, plus "beast" handheld noise, stair steps and beat shakes. Cuts are shot borders.
World coords W(...); workstation coords L(...) (DESK_ROOT: floor under the seat, person faces +Y)."""
import bpy, math
from mathutils import Vector, Matrix, Euler, Quaternion, noise
from lib_build import *
from desk import ELBOW_L, EYE, HUMAN_OFFSET
import screens_rig, drop

FPS = 24
FRAMES = 5254
BEAT0, BEAT = 0.496, 0.600            # beat grid of the song (100 BPM)
ROOT_LOC, ROOT_ROT = Vector((-3.0, 2.4, -2.1)), math.pi


def W(x, y, z):
    return Vector((x, y, z))


def L(x, y, z):
    """DESK_ROOT local -> world (root is rotated 180 deg about Z)."""
    return ROOT_LOC + Vector((-x, -y, z))


FACE = L(-0.052, 0.059 + HUMAN_OFFSET.y, 1.25)
LENS_MID = L(-0.053, 0.131, 1.236)
ELB = L(*ELBOW_L)


def stair_z(x):
    """Tread height of the basement stair at world x (top x=-0.88 z=0.6 -> bottom x=-4.02 z=-2.1)."""
    x = min(-0.88, max(-4.02, x))
    k = int((-0.88 - x) / 0.2415)          # 13 treads
    return 0.6 - k * (2.7 / 13)


# Each shot: t0, t1, keys [(t, pos, target, lens)], and look/feel parameters.
#   noise=(deg, metres, Hz) handheld drift; shake=deg per kick; fstop (None = no DOF); steps=True: stair gait
def shot_list():
    S = []

    def shot(t0, t1, keys, noise=(0.6, 0.006, 0.3), shake=0.0, fstop=None, steps=False, roll=0.0, ease=(True, True)):
        S.append(dict(t0=t0, t1=t1, keys=keys, noise=noise, shake=shake, fstop=fstop, steps=steps, roll=roll, ease=ease))

    # ---- 0 - 45.9  ONER: street -> lawn -> porch -> dog flap -> hall -> basement door -> stairs
    shot(0.0, 45.9, [
        (0.0, W(-30.0, -17.6, 0.30), W(-18.0, -16.4, 0.55), 24),
        (2.6, W(-18.0, -17.2, 0.34), W(-7.0, -14.2, 0.9), 24),
        (4.2, W(-9.0, -16.75, 0.34), W(-2.5, -9.0, 1.0), 24),
        (5.3, W(-6.0, -15.6, 0.36), W(-1.5, -6.0, 1.0), 24),
        (6.8, W(-4.7, -13.3, 0.42), W(-1.0, -4.0, 0.9), 24),
        (8.6, W(-3.4, -10.6, 0.45), W(-2.2, -1.0, 0.55), 24),
        (11.5, W(-2.0, -7.0, 0.45), W(0.0, 0.0, 0.95), 24),
        (12.0, W(-1.85, -6.6, 0.45), W(0.0, 0.0, 0.95), 24),     # scream: speed ramp
        (13.2, W(-0.55, -3.75, 0.50), W(0.0, 0.0, 0.9), 22),
        (14.6, W(-0.25, -3.25, 0.50), W(0.0, 0.0, 0.9), 22),
        (16.5, W(-0.10, -2.60, 0.72), W(0.0, 0.0, 0.88), 22),     # up the porch steps
        (18.0, W(0.0, -1.60, 0.90), W(0.0, 0.1, 0.86), 22),
        (19.8, W(0.0, -0.55, 0.87), W(0.0, 0.6, 0.87), 22),
        (20.35, W(0.0, -0.12, 0.87), W(0.0, 1.2, 0.87), 22),      # through the flap
        (20.6, W(0.0, 0.30, 0.87), W(0.0, 2.2, 0.88), 22),
        (22.1, W(0.0, 0.95, 0.92), W(-0.1, 6.0, 1.0), 20),
        (24.0, W(0.05, 2.0, 0.95), W(-0.8, 2.75, 1.75), 20),      # the family photos
        (25.6, W(0.10, 3.2, 0.95), W(-0.8, 3.85, 1.6), 20),
        (27.2, W(0.15, 4.4, 0.95), W(-0.8, 5.0, 0.95), 20),       # turn to the basement door
        (28.8, W(0.10, 4.95, 0.95), W(-1.6, 4.95, 0.6), 20),
        (30.0, W(-0.30, 4.95, 0.97), W(-2.0, 4.95, 0.2), 20),
        (30.9, W(-0.85, 4.95, 0.98), W(-2.6, 4.95, -0.5), 20),
        (33.0, W(-1.40, 4.95, stair_z(-1.40) + 0.5), W(-3.2, 4.8, -1.3), 20),
        (35.5, W(-2.00, 4.90, stair_z(-2.00) + 0.5), W(-3.0, 3.6, -1.2), 20),
        (38.5, W(-2.60, 4.85, stair_z(-2.60) + 0.5), W(-3.0, 2.6, -1.05), 22),
        (42.0, W(-3.30, 4.80, stair_z(-3.30) + 0.5), W(-3.0, 2.4, -1.12), 24),
        (45.9, W(-3.75, 4.55, stair_z(-3.75) + 0.48), W(-3.0, 2.4, -1.15), 24),
    ], noise=(1.1, 0.012, 0.35), steps=True)

    # ---- 45.9 - 60  pre-chorus 1: orbit behind the chair, close-ups
    shot(45.9, 50.7, [(45.9, L(-1.25, -1.55, 1.05), L(0, 0.5, 1.0), 28),
                      (50.7, L(0.9, -1.5, 1.05), L(0, 0.5, 1.0), 28)], noise=(0.5, 0.004, 0.25))
    shot(50.7, 53.1, [(50.7, L(0.50, 0.42, 0.87), L(0.02, 0.57, 0.81), 65),
                      (53.1, L(0.47, 0.49, 0.86), L(0.0, 0.57, 0.81), 65)], noise=(0.35, 0.002, 0.3), fstop=2.0)
    shot(53.1, 55.5, [(53.1, L(-0.66, 0.18, 0.80), L(-0.41, 0.36, 0.765), 50),
                      (55.5, L(-0.62, 0.21, 0.79), L(-0.40, 0.355, 0.765), 55)], noise=(0.3, 0.001, 0.3), fstop=1.8)
    shot(55.5, 60.0, [(55.5, L(-1.2, -0.9, 0.12), L(-0.2, -0.2, 0.04), 24),
                      (58.8, L(0.1, -1.2, 0.14), L(0.1, -0.2, 0.05), 24),
                      (60.0, L(0.15, -1.25, 0.2), L(0.0, 0.9, 1.15), 20)], noise=(0.6, 0.004, 0.3))

    # ---- 60 - 80  chorus 1: the band assembles, prices pop
    shot(60.0, 66.0, [(60.0, L(0, -1.85, 1.3), L(0, 0.9, 1.15), 24),
                      (66.0, L(0.05, -1.3, 1.35), L(0, 0.9, 1.15), 24)], noise=(0.5, 0.004, 0.4), shake=0.9)
    shot(66.0, 72.0, [(66.0, L(0.0, -1.25, 1.95), L(0, 0.95, 0.95), 24),
                      (72.0, L(0.15, -1.0, 1.9), L(0, 0.95, 0.95), 24)], noise=(0.5, 0.004, 0.4), shake=0.9)
    shot(72.0, 76.4, [(72.0, L(-0.85, -0.75, 1.55), L(-0.75, 0.85, 1.42), 30),      # beside / over the chair
                      (74.6, L(0.1, -0.85, 1.62), L(0.75, 0.85, 1.42), 30),
                      (76.4, L(0.85, -0.75, 1.55), L(0.4, 0.85, 1.3), 28)], noise=(0.5, 0.004, 0.4), shake=0.9)
    shot(76.4, 80.0, [(76.4, L(0, -1.2, 1.3), L(0, 0.9, 1.15), 22),
                      (80.0, L(0, -1.85, 1.2), L(0, 0.9, 1.15), 22)], noise=(0.5, 0.004, 0.4), shake=1.2)

    # ---- 80 - 101.2  verse 2: escalation, the phone, "You're absolutely right!"
    shot(80.0, 88.4, [(80.0, L(0.9, -1.2, 0.9), L(-0.2, 0.9, 1.0), 26),
                      (88.4, L(0.7, -1.45, 1.0), L(-0.2, 0.9, 1.05), 26)], noise=(0.5, 0.004, 0.25))
    shot(88.4, 96.2, [(88.4, L(0.55, -0.45, 1.3), L(-0.05, 0.56, 0.85), 35),          # over the right shoulder
                      (96.2, L(0.45, -0.3, 1.28), L(-0.05, 0.56, 0.85), 35)], noise=(0.4, 0.003, 0.25), fstop=2.8)
    shot(96.2, 100.0, [(96.2, L(0.88, 0.22, 0.93), L(0.62, 0.42, 0.765), 50),
                       (100.0, L(0.82, 0.27, 0.9), L(0.62, 0.42, 0.765), 55)], noise=(0.3, 0.002, 0.3), fstop=2.2)
    shot(100.0, 101.2, [(100.0, L(0, -1.85, 1.35), L(0, 0.9, 1.2), 18),
                        (101.2, L(0, -1.6, 1.33), L(0, 0.9, 1.2), 26)], noise=(0.4, 0.003, 0.5), shake=1.5)

    # ---- 101.2 - 110.3  pre-chorus 2: along the puddles, the drop falls (slow-mo)
    shot(101.2, 105.0, [(101.2, L(-1.25, -0.55, 0.06), L(-0.4, 0.3, 0.02), 24),
                        (105.0, L(-0.78, -0.02, 0.07), L(-0.4, 0.3, 0.05), 28)], noise=(0.4, 0.002, 0.25), fstop=2.8)
    # macro on the needle tip while the drop swells, then the lens rides down with it to the floor
    side = Vector((-0.80, -0.55, 0.12)).normalized()                # from the drop toward the lens
    at = lambda t: Vector((drop.AXIS.x, drop.AXIS.y, drop.z_at(t)))
    fall = [(105.0, L(*(at(105.0) + side * 0.11)), L(*at(105.0)), 100),
            (drop.T_PINCH, L(*(at(drop.T_PINCH) + side * 0.085)), L(*at(drop.T_PINCH)), 100)]
    for k in range(1, 13):
        t = drop.T_PINCH + (drop.T_LAND - drop.T_PINCH) * k / 12
        fall.append((t, L(*(at(t) + side * (0.085 + 0.085 * k / 12))), L(*at(t)), 100 - 3 * k))
    floor = Vector((drop.AXIS.x, drop.AXIS.y, 0.002))
    fall.append((110.3, L(*(floor + side * 0.26 + Vector((0, 0, 0.03)))), L(*floor), 50))
    shot(105.0, 110.3, fall, noise=(0.25, 0.0008, 0.3), fstop=11.0)

    # ---- 110.3 - 132.5  chorus 2: the creatures come out
    # (the stair occupies root-local y < -1.95 behind the chair: cameras stay in front of it)
    shot(110.3, 115.0, [(110.3, L(0.9, -1.5, 0.45), L(-0.5, 0.6, 1.25), 18),           # warrok streams out of mon2
                        (115.0, L(0.75, -1.35, 0.5), L(-1.5, 0.3, 1.35), 18)], noise=(0.6, 0.005, 0.4), shake=1.0)
    shot(115.0, 119.9, [(115.0, L(-1.65, -1.3, 0.35), L(-2.75, 0.2, 1.55), 18),      # low hero angle: the roar
                        (119.9, L(-1.55, -1.2, 0.4), L(-2.75, 0.2, 1.65), 18)], noise=(0.6, 0.005, 0.4), shake=1.0)
    shot(119.9, 124.5, [(119.9, L(-0.9, -1.5, 0.7), L(0.9, 0.5, 1.4), 20),             # maw out of mon5
                        (124.5, L(-0.8, -1.35, 0.75), L(1.9, -0.1, 1.4), 20)], noise=(0.6, 0.005, 0.4), shake=1.0)
    shot(124.5, 130.4, [(124.5, L(-1.2, -1.75, 1.0), L(-1.4, 0.5, 1.3), 18),           # pan from the warrok to the maw
                        (130.4, L(1.2, -1.75, 1.2), L(1.4, 0.5, 1.3), 18)], noise=(0.6, 0.005, 0.4), shake=1.1)
    shot(130.4, 132.5, [(130.4, L(0, -1.55, 1.6), L(0, 0.9, 1.2), 24),
                        (132.5, L(0, -1.35, 1.55), L(0, 0.9, 1.2), 24)], noise=(0.4, 0.003, 0.3))

    # ---- 132.5 - 149.6  bridge "usage limit reached" + withdrawal
    shot(132.5, 139.1, [(132.5, L(-0.35, -1.6, 1.35), L(0, 0.95, 1.2), 28),
                        (139.1, L(-0.2, -0.75, 1.42), L(0, 0.95, 1.2), 28)], noise=(0.4, 0.003, 0.25))
    shot(139.1, 144.0, [(139.1, L(0.30, 0.80, 0.93), L(-0.05, 0.45, 0.84), 70),       # from the monitors back at the hands
                        (144.0, L(0.24, 0.76, 0.92), L(-0.05, 0.45, 0.84), 70)], noise=(0.9, 0.003, 0.9), fstop=2.8)
    shot(144.0, 149.896, [(144.0, L(0.2, -1.5, 1.4), L(0, 0.95, 1.2), 26),
                          (149.896, L(0.0, -1.1, 1.45), L(0, 0.95, 1.2), 26)], noise=(0.6, 0.004, 0.5))

    # ---- 149.9 - 156.5  "RE-SET!" breakdown: a hard cut on every second beat
    cuts = [149.896, 151.096, 152.296, 153.496, 154.696, 155.896, 156.5]
    angles = [(L(0, -0.4, 2.12), L(0, 0.9, 0.9), 20), (L(0.5, -0.9, 0.1), L(0, 0.9, 1.2), 16),
              (L(-1.6, -1.2, 1.2), L(0, 0.9, 1.1), 20), (L(1.6, -1.2, 1.2), L(0, 0.9, 1.1), 20),
              (L(0.35, 0.5, 1.55), L(0.67, 0.83, 1.39), 35), (L(0, -1.85, 1.3), L(0, 0.9, 1.15), 22)]
    for (a, b), (p, t, lens) in zip(zip(cuts, cuts[1:]), angles):
        d = (t - p).normalized() * 0.12
        shot(a, b, [(a, p, t, lens), (b, p + d, t, lens)], noise=(0.5, 0.003, 0.6), shake=3.0)

    # ---- 156.5 - 168  darkness, then follow the glowing IV line up to the bag
    shot(156.5, 159.3, [(156.5, L(-0.9, -1.5, 1.7), L(-0.3, 0.6, 0.6), 22),
                        (159.3, L(-0.88, -1.45, 1.68), L(-0.3, 0.6, 0.62), 22)], noise=(0.3, 0.002, 0.2))
    shot(159.3, 168.0, [(159.3, L(-0.88, 0.22, 0.95), L(-0.75, 0.48, 0.77), 35),
                        (162.5, L(-1.05, 0.75, 1.15), L(-0.78, 1.15, 1.05), 35),
                        (165.5, L(-1.05, 1.0, 1.45), L(-0.72, 1.35, 1.45), 40),
                        (168.0, L(-0.9, 1.08, 1.72), L(-0.69, 1.4, 1.62), 45)], noise=(0.4, 0.002, 0.25), fstop=2.8)

    # ---- 168 - 188.1  final chorus: the bag fills, the flow runs down to the elbow, everything looms
    shot(168.0, 172.0, [(168.0, L(-0.9, 1.08, 1.72), L(-0.69, 1.4, 1.66), 40),
                        (172.0, L(-0.98, 1.0, 1.55), L(-0.7, 1.35, 1.45), 35)], noise=(0.5, 0.003, 0.4), shake=0.7, fstop=2.8)
    shot(172.0, 177.0, [(172.0, L(-1.0, 1.0, 1.4), L(-0.72, 1.25, 1.2), 35),
                        (174.0, L(-1.05, 0.5, 1.0), L(-0.8, 0.6, 0.78), 35),
                        (176.0, L(-0.62, 0.02, 1.05), ELB, 40),
                        (177.0, L(-0.55, 0.06, 1.02), ELB, 40)], noise=(0.5, 0.003, 0.4), shake=0.6, fstop=2.8)
    shot(177.0, 180.4, [(177.0, L(-0.48, 0.32, 1.02), ELB, 60),
                        (180.4, L(-0.44, 0.28, 1.0), ELB, 65)], noise=(0.35, 0.001, 0.4), shake=0.5, fstop=2.0)
    shot(180.4, 188.1, [(180.4, L(-1.1, -1.4, 1.0), L(-1.2, 0.6, 1.3), 20),
                        (188.1, L(1.1, -1.4, 1.25), L(1.2, 0.6, 1.3), 20)], noise=(0.6, 0.005, 0.4), shake=1.2)

    # ---- 188.1 - 214.24  outro (Cycles): around the chair to the face, the logos in the glasses, last scream
    shot(188.1, 198.0, [(188.1, L(-0.75, -0.9, 1.3), FACE, 32),
                        (191.0, L(-0.98, -0.25, 1.3), FACE, 34),
                        (194.5, L(-0.85, 0.38, 1.28), FACE, 38),
                        (198.0, L(-0.42, 0.56, 1.27), FACE, 40)], noise=(0.25, 0.002, 0.2), fstop=2.8)
    shot(198.0, 206.3, [(198.0, L(-0.42, 0.56, 1.27), LENS_MID, 40),
                        (206.3, L(-0.07, 0.42, 1.25), LENS_MID, 50)], noise=(0.2, 0.001, 0.2), fstop=2.8)
    shot(206.3, FRAMES / FPS, [(206.3, L(-0.07, 0.42, 1.25), LENS_MID, 50),
                               (214.24, L(-0.055, 0.30, 1.245), LENS_MID, 35),
                               (FRAMES / FPS, L(-0.055, 0.30, 1.245), LENS_MID, 35)], noise=(0.8, 0.003, 0.8), shake=2.0, fstop=2.8)
    return S


# ---------------------------------------------------------------- evaluation

def _tangents(ts, vs):
    """Monotone-ish Hermite tangents: Catmull-Rom (non-uniform), clamped against both neighbouring chords."""
    n = len(ts)
    ms = []
    for i in range(n):
        if i == 0 or i == n - 1:
            ms.append(vs[0] * 0.0)
            continue
        m = (vs[i + 1] - vs[i - 1]) / (ts[i + 1] - ts[i - 1])
        lim = min(2.0 * (vs[i] - vs[i - 1]).length / (ts[i] - ts[i - 1]),
                  2.0 * (vs[i + 1] - vs[i]).length / (ts[i + 1] - ts[i]))
        if m.length > lim:
            m = m * (lim / max(m.length, 1e-9))
        ms.append(m)
    return ms


def _hermite(ts, vs, ms, t):
    if t <= ts[0]:
        return vs[0].copy()
    if t >= ts[-1]:
        return vs[-1].copy()
    i = max(k for k in range(len(ts) - 1) if ts[k] <= t)
    h = ts[i + 1] - ts[i]
    u = (t - ts[i]) / h
    h00, h10 = 2 * u ** 3 - 3 * u ** 2 + 1, u ** 3 - 2 * u ** 2 + u
    h01, h11 = -2 * u ** 3 + 3 * u ** 2, u ** 3 - u ** 2
    return vs[i] * h00 + ms[i] * (h10 * h) + vs[i + 1] * h01 + ms[i + 1] * (h11 * h)


def beats_between(a, b):
    k0 = math.ceil((a - BEAT0) / BEAT)
    t = BEAT0 + k0 * BEAT
    while t < b:
        yield t
        t += BEAT


def kick(t, amp, t0):
    """Decaying shake from every beat since the shot start (downbeats of the bar hit harder)."""
    out = Vector((0, 0, 0))
    for b in beats_between(max(t0, t - 0.5), t + 1e-6):
        d = t - b
        k = round((b - BEAT0) / BEAT)
        a = amp * (1.0 if k % 2 == 0 else 0.55) * math.exp(-d / 0.11)
        out += Vector((math.sin(d * 2 * math.pi * 7.0), math.sin(d * 2 * math.pi * 5.3 + 1.0) * 0.6,
                       math.sin(d * 2 * math.pi * 6.1 + 2.0) * 0.35)) * math.radians(a)
    return out


def evaluate(S):
    """Per-frame (location, quaternion, lens, focus distance, fstop)."""
    out = []
    prepared = []
    for s in S:
        ts = [k[0] for k in s['keys']]
        P = [k[1] for k in s['keys']]
        T = [k[2] for k in s['keys']]
        F = [Vector((k[3], 0, 0)) for k in s['keys']]
        prepared.append((s, ts, P, _tangents(ts, P), T, _tangents(ts, T), F, _tangents(ts, F)))
    for f in range(1, FRAMES + 1):
        t = (f - 1) / FPS
        sh = next((p for p in prepared if p[0]['t0'] <= t < p[0]['t1']), prepared[-1])
        s, ts, P, PM, T, TM, F, FM = sh
        pos = _hermite(ts, P, PM, t)
        tgt = _hermite(ts, T, TM, t)
        lens = _hermite(ts, F, FM, t).x
        deg, metres, hz = s['noise']
        seed = s['t0'] * 3.7
        n = lambda o: noise.noise(Vector((t * hz, seed + o, o * 1.3)))
        pos = pos + Vector((n(1), n(2), n(3))) * metres * 2.0
        if s['steps']:
            # four-legged creep: a soft dip on every beat, deeper on the stairs (once inside the hall)
            ph = ((t - BEAT0) / BEAT) % 1.0
            dip = 0.010 if t < 30.9 else 0.022
            pos.z -= dip * (0.5 - 0.5 * math.cos(2 * math.pi * ph))
        d = tgt - pos
        q = d.to_track_quat('-Z', 'Y')
        rx, ry, rz = n(4) * deg, n(5) * deg * 0.6, n(6) * deg * 0.5
        rot = Vector((math.radians(rx), math.radians(ry), math.radians(rz) + math.radians(s['roll'])))
        if s['shake']:
            rot += kick(t, s['shake'], s['t0'])
        q = q @ Euler((rot.x, rot.y, rot.z)).to_quaternion()
        out.append((pos, q, lens, d.length, s['fstop']))
    return out


def build(scene, col):
    cd = bpy.data.cameras.new('ClipCam')
    cd.sensor_width = 36.0
    cd.clip_start = 0.01
    cd.clip_end = 400.0
    cam = bpy.data.objects.new('ClipCam', cd)
    col.objects.link(cam)
    cam.rotation_mode = 'XYZ'
    scene.camera = cam
    frames = evaluate(shot_list())
    eul_prev = None
    locs = [[], [], []]
    rots = [[], [], []]
    lens, focus, fst = [], [], []
    for pos, q, ln, fd, fs in frames:
        e = q.to_euler('XYZ', eul_prev) if eul_prev else q.to_euler('XYZ')
        eul_prev = e
        for i in range(3):
            locs[i].append(pos[i])
            rots[i].append(e[i])
        lens.append(ln)
        focus.append(fd)
        fst.append(fs or 22.0)
    for i in range(3):
        screens_rig.key_series(cam, 'location', i, locs[i])
        screens_rig.key_series(cam, 'rotation_euler', i, rots[i])
    screens_rig.key_series(cd, 'lens', -1, lens)
    cd.dof.use_dof = True
    screens_rig.key_series(cd, 'dof.focus_distance', -1, focus)
    screens_rig.key_series(cd, 'dof.aperture_fstop', -1, fst)
    # cuts: constant interpolation into each shot start so nothing interpolates across a cut
    return cam
