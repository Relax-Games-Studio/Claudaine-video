"""The Short's edit: timing, pieces, crops and text. Plain Python (no PIL) so that both make_short.py (ffmpeg) and
render_short_src.py (inside Blender) read the same numbers."""

FPS = 24
OW, OH = 1080, 1920
SR = 48000
NFRAMES = 461                 # 19.2083 s; 32 beats = 460.8 frames
A0 = 59.28                    # song second at output t = 0. Beat 98 (59.296) = "Clau" pickup lands 16 ms in,
                              # and the file's last sample (78.488) stays clear of the beat-130 kick at 78.496
XFADE = 0.100                 # seam crossfade (s), well under one beat (0.6 s)
BEAT0, BEAT = 0.496, 0.600    # song beat grid (measured; no drift)
SRC_ASPECT = 16 / 9           # the clip's frame

# The edit. Output cuts sit on beats of the output grid (beat j = frame round(14.4 j)), except the G->H cut,
# which is the render's own cut at 72.0: H is placed "in sync" (source second = A0 + output second) so the
# price cards pop on the lyrics "Twenty / a hundred / two hundred" exactly as they do in the clip.
#   src   first source frame, clip seconds (= frame / 24 of the clip render)
#   n     length in output frames
#   keys  crop-centre keyframes [(clip second, centre x as a fraction of the source width)], linear in
#         between; two keys less than a frame apart make a jump (a reframe on a beat)
#   cy    crop-centre y (fraction of height); only matters when z > 1
#   z     zoom: 1.0 = full source height (a 9:16 slice 0.316 of a 16:9 frame wide)
#   eq    optional ffmpeg eq= options (lift for shots that go to mud on a phone)
PIECES = [
    dict(id='A', name='logos ignite', src=198.375, n=29, z=1.10, cy=0.50,
         keys=[(198.375, 0.510), (199.583, 0.515)],
         why='HOOK. Claude logos ignite in the mummy\'s glasses, on "Clau-DAINE!" (stop-time)'),
    dict(id='B', name='IV bag', src=168.000, n=72, z=1.00,
         keys=[(168.0, 0.480), (169.2, 0.475), (170.4, 0.480), (171.0, 0.485)],
         why='white flash on the bass/kick slam, the bag fills orange, tilt down the drip to the glowing line; '
             '"(Claudaine!) Burning through my brain"'),
    dict(id='C', name='hands typing', src=50.917, n=43, z=1.00, eq='gamma=1.30:brightness=0.015',
         keys=[(50.917, 0.335), (52.667, 0.320)],
         why='withered fingers on the keys under "One more prompt and I\'m a god again" (+ CLI text)'),
    dict(id='D', name='drop on the needle', src=105.417, n=43, z=1.15, cy=0.45,
         keys=[(105.417, 0.470), (107.167, 0.475)],
         why='an orange dose swells on the needle tip, pinches off, camera rides it down; on "Claudaine!"'),
    dict(id='E', name='splash', src=109.000, n=15, z=1.00,
         keys=[(109.0, 0.490)],
         why='the drop lands on the beat and splashes into an orange puddle'),
    dict(id='F', name='loaded syringe', src=53.125, n=57, z=1.00,
         keys=[(53.125, 0.375), (54.3, 0.355), (55.458, 0.328)],
         why='orange-loaded syringe on the desk, a drop on the needle tip, slow dolly'),
    dict(id='G', name='glowing IV line', src=174.208, n=46, z=1.00,
         keys=[(174.208, 0.400), (174.8, 0.420), (175.5, 0.550), (176.125, 0.500)],
         why='down the glowing line past the orange syringes to the taped arm: the dose on its way in'),
    dict(id='H', name='paying for Claude Max', src=72.000, n=69, z=1.12, cy=0.53,
         keys=[(72.0, 0.580), (72.6, 0.475), (73.2, 0.270), (73.5, 0.160), (73.700, 0.160),
               (73.708, 0.660), (73.85, 0.615), (74.1, 0.545), (74.4, 0.460), (74.6, 0.435), (74.833, 0.420)],
         why='in sync with the lyric: $20 on "Twenty was a taste", $100 on "a hundred hit the vein", jump on the '
             'beat to "-$100.00 ANTHROPIC *CLAUDE MAX", then "-$200.00" on "Two hundred a month"'),
    dict(id='I', name='usage limit reached', src=149.917, n=29, z=1.00,
         keys=[(149.917, 0.495)],
         why='top-down, six monitors frozen at 4:59:59 "Usage limit reached", white flash on the cut; '
             '"just to feel the same"'),
    dict(id='J', name='catheter', src=177.917, n=29, z=1.00,
         keys=[(177.917, 0.480)],
         why='the orange line pulsing into the catheter in his elbow; "It ain\'t opium..."'),
    dict(id='K', name='face, before the logos', src=196.792, n=29, z=1.10, cy=0.50,
         keys=[(196.792, 0.495), (197.958, 0.505)],
         why='"...it\'s Opus in my veins": push-in on the mummy\'s face, code in the glasses; the same move '
             'continues into A (skips the 9-frame black dip), so the wrap is a match cut on the face'),
]

TITLE = dict(text='Claudaine', f0=0, f1=29)                        # over the hook
CLI = dict(prompt='> ', text='one more prompt', f0=101, f1=144, cps=22.0, size=62)   # over C, typed as he sings it


def crop_centre(p, k):
    """Centre (x, y) and size (w, h) of piece p's crop in its k-th frame, as fractions of the 16:9 source frame:
    the same numbers make_short's ffmpeg crop uses (keys held outside their range, a jump between two keys
    less than a frame apart, the crop kept inside the frame)."""
    keys = [((t - p['src']) * FPS, cx) for t, cx in p['keys']]
    if k < keys[0][0]:
        cx = keys[0][1]
    else:
        cx = keys[-1][1]
        for (n0, v0), (n1, v1) in zip(keys, keys[1:]):
            if k < n1:
                cx = v1 if n1 - n0 < 1e-6 else v0 + (v1 - v0) * (k - n0) / (n1 - n0)
                break
    z = p.get('z', 1.0)
    h = min(1.0, 1.0 / z)
    w = min(1.0, h * (OW / OH) / SRC_ASPECT)
    x = min(max(cx, w / 2), 1 - w / 2)
    y = min(max(p.get('cy', 0.5), h / 2), 1 - h / 2)
    return x, y, w, h
