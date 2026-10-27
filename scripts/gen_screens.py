#!/usr/bin/env python3
"""Render the monitor and phone screen videos for the CLAUDAINE clip.

Timeline and roles: see ../docs/SPEC.md ("Экраны — что где") and ../docs/TREATMENT.md.

Usage (needs numpy + Pillow):
  gen_screens.py preview [mon ...]   contact sheets -> screens/preview_contact.png
  gen_screens.py encode  [name ...]  mon1..mon6, phone -> screens/*.mp4 + screens/mon_light.json
  gen_screens.py still NAME T OUT    one frame of NAME at time T seconds
"""
import json, math, os, random, subprocess, sys
from multiprocessing import Pool

import numpy as np
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SONG = os.path.join(ROOT, 'Claudaine.mp3')
OUT = os.path.join(ROOT, 'screens')
FFMPEG = os.environ.get('FFMPEG', 'ffmpeg')
MENLO = '/System/Library/Fonts/Menlo.ttc'
SFNS = '/System/Library/Fonts/SFNS.ttf'

W, H, FPS, NF = 1920, 1080, 24, 5254
PW, PH = 720, 1560
NAMES = ['mon1', 'mon2', 'mon3', 'mon4', 'mon5', 'mon6', 'phone']

# ---------------------------------------------------------------- colours
BG = (12, 12, 14)
FG = (222, 222, 222)
DIM = (128, 128, 134)
DIM2 = (80, 80, 86)
ORANGE = (217, 119, 87)
ORANGE_HI = (245, 170, 135)
GREEN = (86, 190, 108)
RED = (235, 84, 80)
ADD_BG, ADD_FG = (24, 52, 31), (165, 228, 175)
DEL_BG, DEL_FG = (66, 24, 28), (242, 160, 160)
PROMPT_BG = (38, 38, 42)
BLUE = (125, 165, 235)
LIMIT_BG = (34, 8, 8)

# ---------------------------------------------------------------- timeline (seconds)
T_BAND = {5: 60.496, 1: 62.296, 3: 63.496, 2: 66.496}   # pop-in on beats after 60.0/62.3/63.5/66.2
T_RIGHT = (100.0, 101.2)
T_EMERGE = {2: 110.3, 5: 119.9}
T_LIMIT, T_SCREAM, T_COUNT = 132.5, 139.1, 149.6
T_WEEKLY, T_OFF, T_ON = 156.5, 157.3, 168.0
T_CALM, T_LOGO, T_CHAOS = 188.1, 198.0, 206.3
T_END = 214.0            # refined to the strongest kick near 214 s in analyze()
T_GRID = 91.4
PRICE_SETS = [(72.0, 73.1, 74.4, 76.4, 79.2), (122.3, 123.4, 124.7, 126.8, 129.6),
              (179.9, 181.0, 182.3, 184.4, 187.2)]
PLAN_BANNERS = {4: [(82.7, 'Upgraded to Claude Pro', '$20/mo'),
                    (84.3, 'Upgraded to Claude Max 5x', '$100/mo'),
                    (86.6, 'Upgraded to Claude Max 20x', '$200/mo')],
                6: [(89.0, 'Logged in · account #2', 'second subscription active')]}

LYRICS = [
    (5.3, "You've hit your usage limit."), (8.6, 'Your limit will reset at three A.M.'), (12.0, 'CLAUDAINE!'),
    (30.9, 'It started with a "hi"'), (33.3, 'Free tier, first hit'), (36.2, 'One prompt and a sunrise'),
    (38.6, 'Shipped a year of code'), (41.1, 'Twenty bucks a month?'), (43.5, 'I can quit any time.'),
    (45.4, '(Right back!)'), (45.9, "Midnight, it's just me and you"), (53.3, 'Monitor glow in neon blue'),
    (55.5, 'A million tokens deep'), (57.8, "I'm drowning and I never sleep"),
    (60.0, 'CLAUDAINE!'), (62.3, 'BURNING THROUGH MY BRAIN'), (63.5, "ONE MORE PROMPT AND I'M A GOD AGAIN!"),
    (66.2, 'CLAUDAINE!'), (72.0, 'TWENTY WAS A TASTE'), (73.1, 'A HUNDRED HIT THE VEIN'),
    (74.4, 'TWO HUNDRED A MONTH'), (75.4, 'JUST TO FEEL THE SAME'), (76.4, "IT AIN'T OPIUM"),
    (77.6, "IT'S OPUS IN MY VEINS!"), (79.2, 'CLAUDAINE!'),
    (82.7, 'First it was Pro'), (84.3, 'Then Max for a hundred'), (86.6, 'Then Max for two hundred'),
    (89.0, 'Made a second account'), (91.4, 'Ten sessions in parallel'), (93.8, 'Seventy hours. One more, please.'),
    (96.2, 'Mom calls: "Son, are you okay?"'), (98.0, 'I just type "compact"'), (98.6, 'Friends text: "Are you alive?"'),
    (101.2, 'The dose keeps climbing like the bill'), (106.1, "Yesterday's hit don't give the thrill"),
    (109.1, 'MORE, MORE, MORE...'),
    (110.3, 'CLAUDAINE!'), (112.7, 'BURNING THROUGH MY BRAIN'), (114.0, "ONE MORE PROMPT AND I'M A GOD AGAIN!"),
    (119.9, 'CLAUDAINE!'), (122.3, 'TWENTY WAS A TASTE'), (123.4, 'A HUNDRED HIT THE VEIN'),
    (124.7, 'TWO HUNDRED A MONTH'), (125.7, 'JUST TO FEEL THE SAME'), (126.8, "IT AIN'T OPIUM"),
    (128.0, "IT'S OPUS IN MY VEINS!"), (129.6, 'CLAUDAINE!'),
    (168.0, 'CLAUDAINE!'), (170.3, "LIMIT'S RESET, I'M ALIVE AGAIN!"), (177.5, 'CLAUDAINE!'),
    (179.9, 'TWENTY WAS A TASTE'), (181.0, 'A HUNDRED HIT THE VEIN'), (182.3, 'TWO HUNDRED A MONTH'),
    (183.3, 'JUST TO FEEL THE SAME'), (184.4, "IT AIN'T OPIUM"), (185.6, "IT'S OPUS IN MY VEINS!"),
    (187.2, 'CLAUDAINE!'), (206.3, 'CLAUDAINE!'),
]
SCREAMS = ('CLAUDAINE', 'MORE', 'LIMIT', 'RE-SET', 'NOOO')

A = {}   # audio analysis, filled by analyze() / worker init


# ================================================================ audio
def analyze():
    raw = subprocess.run([FFMPEG, '-v', 'error', '-i', SONG, '-ac', '1', '-ar', '11025', '-f', 'f32le', '-'],
                         capture_output=True, check=True).stdout
    x = np.frombuffer(raw, np.float32)
    sr, hop, win = 11025, 128, 1024
    n = (len(x) - win) // hop
    frames = np.lib.stride_tricks.sliding_window_view(x, win)[::hop][:n]
    spec = np.abs(np.fft.rfft(frames * np.hanning(win), axis=1))
    freqs = np.fft.rfftfreq(win, 1 / sr)

    def flux(lo, hi):
        e = np.log1p(spec[:, (freqs >= lo) & (freqs < hi)] * 20)
        f = np.concatenate([[0], np.maximum(0, np.diff(e, axis=0)).sum(1)])
        return f / (np.percentile(f, 99) + 1e-9)

    full, kick = flux(30, 5000), flux(30, 140)
    snare = 0.5 * flux(160, 400) + 0.5 * flux(1800, 5000)
    t = (np.arange(n) * hop + win / 2) / sr

    def score(P, ph):
        g = np.arange(ph + np.ceil((30 - ph) / P) * P, 200, P)
        i = np.round((g * sr - win / 2) / hop).astype(int)
        i = i[(i > 0) & (i < n - 1)]
        return full[i].sum() + 0.5 * (full[i - 1].sum() + full[i + 1].sum())

    best = max((score(P, ph), P, ph) for P in np.arange(0.598, 0.612, 0.0002) for ph in np.arange(0, 0.612, 0.004))
    _, period, phase = best

    def peaks(f, thr):
        med = np.convolve(f, np.ones(43) / 43, 'same')
        out, last = [], -1.0
        for i in range(1, len(f) - 1):
            if f[i] > f[i - 1] and f[i] >= f[i + 1] and f[i] > thr + 1.3 * med[i] and t[i] - last > 0.09:
                out.append((float(t[i]), float(f[i]))); last = t[i]
        return out

    kicks, snares = peaks(kick, 0.25), peaks(snare, 0.25)
    tf = np.arange(NF) / FPS

    def env(hits, tau):
        e = np.zeros(NF)
        for tk, s in hits:
            f0 = int(math.ceil(tk * FPS))
            k = np.arange(f0, min(NF, f0 + int(tau * FPS * 6) + 1))
            e[k] = np.maximum(e[k], min(s, 1.6) * np.exp(-(k / FPS - tk) / tau))
        return e

    rms = np.sqrt(np.convolve(x.astype(np.float64) ** 2, np.ones(sr // 12) / (sr // 12), 'same'))
    loud = np.interp(tf, np.arange(len(x)) / sr, rms)
    loud = loud / np.percentile(loud, 98)
    near = [k for k in kicks if 213.4 <= k[0] <= 214.6]
    t_end = max(near, key=lambda k: k[1])[0] if near else 214.0
    return dict(period=float(period), phase=float(phase), kicks=kicks, snares=snares,
                kick=env(kicks, 0.11), snare=env(snares, 0.09), loud=loud, t_end=float(t_end))


def init_worker(a):
    global T_END
    A.update(a)
    T_END = a['t_end']


def fidx(t):
    return min(NF - 1, max(0, int(round(t * FPS))))


def beat(t):
    """(beat index, phase 0..1) on the analysed grid."""
    b = (t - A['phase']) / A['period']
    return math.floor(b), b - math.floor(b)


def onsets_between(lst, t0, t1):
    return [o for o in lst if t0 <= o[0] < t1]


def smooth(a, b, x):
    x = min(1.0, max(0.0, (x - a) / (b - a)))
    return x * x * (3 - 2 * x)


def mix(c0, c1, k):
    k = min(1.0, max(0.0, k))
    return tuple(int(round(a + (b - a) * k)) for a, b in zip(c0, c1))


# ================================================================ fonts / glyphs
_fonts = {}


class TFont:
    def __init__(self, size, bold, lh):
        self.f = ImageFont.truetype(MENLO, size, index=1 if bold else 0)
        self.cw = self.f.getlength('M' * 20) / 20
        a, d = self.f.getmetrics()
        self.lh = lh or (a + d)
        self.dy = (self.lh - (a + d)) / 2
        self.lw = max(1, round(self.cw * 0.13))
        self.size = size


def tfont(size, bold=False, lh=None):
    k = (size, bold, lh)
    if k not in _fonts:
        _fonts[k] = TFont(size, bold, lh)
    return _fonts[k]


def sfont(size, weight='Regular'):
    k = ('sf', size, weight)
    if k not in _fonts:
        f = ImageFont.truetype(SFNS, size)
        try:
            f.set_variation_by_name(weight)
        except Exception:
            pass
        _fonts[k] = f
    return _fonts[k]


QUAD = {'█': 15, '▀': 12, '▄': 3, '▌': 10, '▐': 5, '▘': 8, '▝': 4, '▖': 2, '▗': 1,
        '▛': 14, '▜': 13, '▙': 11, '▟': 7}
SPECIAL = set('─│╭╮╰╯├┤┬┴┼⎿⏺') | set(QUAD)


def draw_glyph(d, ch, x, y, F, col):
    cw, lh, lw = F.cw, F.lh, F.lw
    cx, cy = x + cw / 2, y + lh / 2
    if ch in QUAD:
        m = QUAD[ch]
        xs, ys = (x, cx, x + cw), (y, cy, y + lh)
        for i, (qx, qy) in enumerate(((0, 0), (1, 0), (0, 1), (1, 1))):
            if m >> (3 - i) & 1:
                d.rectangle([round(xs[qx]), round(ys[qy]), round(xs[qx + 1]) - 1, round(ys[qy + 1]) - 1], fill=col)
        return

    def hl(x0, x1, yy=cy):
        y0 = int(round(yy - lw / 2))
        d.rectangle([int(round(x0)), y0, int(round(x1)) - 1, y0 + lw - 1], fill=col)

    def vl(y0, y1, xx=cx):
        x0 = int(round(xx - lw / 2))
        d.rectangle([x0, int(round(y0)), x0 + lw - 1, int(round(y1)) - 1], fill=col)

    r = cw * 0.45
    if ch == '─': hl(x, x + cw)
    elif ch == '│': vl(y, y + lh)
    elif ch == '├': vl(y, y + lh); hl(cx, x + cw)
    elif ch == '┤': vl(y, y + lh); hl(x, cx)
    elif ch == '┬': hl(x, x + cw); vl(cy, y + lh)
    elif ch == '┴': hl(x, x + cw); vl(y, cy)
    elif ch == '┼': hl(x, x + cw); vl(y, y + lh)
    elif ch == '╭':
        vl(cy + r, y + lh); hl(cx + r, x + cw)
        d.arc([cx - lw / 2, cy - lw / 2, cx + 2 * r + lw / 2, cy + 2 * r + lw / 2], 180, 270, fill=col, width=lw)
    elif ch == '╮':
        vl(cy + r, y + lh); hl(x, cx - r)
        d.arc([cx - 2 * r - lw / 2, cy - lw / 2, cx + lw / 2, cy + 2 * r + lw / 2], 270, 360, fill=col, width=lw)
    elif ch == '╰':
        vl(y, cy - r); hl(cx + r, x + cw)
        d.arc([cx - lw / 2, cy - 2 * r - lw / 2, cx + 2 * r + lw / 2, cy + lw / 2], 90, 180, fill=col, width=lw)
    elif ch == '╯':
        vl(y, cy - r); hl(x, cx - r)
        d.arc([cx - 2 * r - lw / 2, cy - 2 * r - lw / 2, cx + lw / 2, cy + lw / 2], 0, 90, fill=col, width=lw)
    elif ch == '⎿':
        xl = x + cw * 0.3
        vl(y + lh * 0.08, y + lh * 0.62, xl); hl(xl - lw / 2, x + cw, y + lh * 0.62)
    elif ch == '⏺':
        rr = cw * 0.3
        d.ellipse([cx - rr, cy - rr + lh * 0.03, cx + rr, cy + rr + lh * 0.03], fill=col)


def draw_spans(d, x, y, F, spans, max_chars=None):
    """spans: (text, fg[, bg[, bold]]). Returns chars drawn."""
    col = 0
    for sp in spans:
        text, fg = sp[0], sp[1]
        bg = sp[2] if len(sp) > 2 else None
        bold = sp[3] if len(sp) > 3 else False
        if max_chars is not None:
            if col >= max_chars:
                break
            text = text[:max_chars - col]
        if not text:
            continue
        x0 = x + col * F.cw
        if bg:
            d.rectangle([int(x0), int(y), int(x0 + len(text) * F.cw) - 1, int(y + F.lh) - 1], fill=bg)
        f = tfont(F.size, True, F.lh) if bold else F
        run, rx = '', x0
        for i, ch in enumerate(text):
            cx = x0 + i * F.cw
            if ch in SPECIAL:
                if run.strip():
                    d.text((rx, y + f.dy), run, font=f.f, fill=fg)
                run = ''
                draw_glyph(d, ch, cx, y, F, fg)
                rx = cx + F.cw
            else:
                if not run:
                    rx = cx
                run += ch
        if run.strip():
            d.text((rx, y + f.dy), run, font=f.f, fill=fg)
        col += len(text)
    return col


def text_center(d, cx, cy, s, font, fill):
    d.text((cx, cy), s, font=font, fill=fill, anchor='mm')


# ================================================================ transcript content
MONSTERS = ['maw', 'parasite', 'warrok', 'demon', 'skeleton', 'mutant']
FILES = ['src/monsters/{m}.ts', 'src/ai/{m}Brain.ts', 'src/monsters/{m}.test.ts', 'src/render/glitch.frag',
         'src/render/postfx.ts', 'src/game/loop.ts', 'src/audio/roar.ts', 'src/ui/hud.tsx', 'src/net/lobby.ts',
         'src/ai/swarm.ts', 'src/game/bossPhase.ts', 'src/world/basement.ts', 'src/shop/battlePass.ts']
PROMPTS = ['make the {m} spit acid in a cone when it drops below 30% hp',
           'the {m} should crawl out of the screen. like actually out of the screen',
           'parasites need to swarm the player and latch onto the camera',
           'add a glitch shader when the demon teleports',
           'the skeleton king needs a second phase. scarier',
           'why is the warrok ragdoll launching into orbit',
           'fix it', 'make it more metal', 'now 240fps', 'add multiplayer', 'ship it', 'go faster',
           'sync the {m} roar to the music', 'one more feature', 'add a battle pass', "don't stop",
           'refactor everything', 'make the monsters remember me', 'more monsters', 'make it hurt']
TEXTS = ["I'll add that. Let me look at the existing {m} state machine first.",
         "Great idea! Let me wire the {m} into the boss director.",
         "You're absolutely right — the ragdoll joints had no angular limits. Fixing now.",
         "I'll split this into a second phase with a shadow-clone mechanic.",
         "Done! The {m} now hunts in packs and all tests pass.",
         "Let me run the test suite to make sure nothing broke.",
         "Found it: the physics step was running twice per frame.",
         "I'll add a beat-synced roar so the {m} screams on the downbeat.",
         "Shipping it. Bumping the version and tagging the release.",
         "The {m} now crawls through any surface with a screen texture.",
         "Perfect. Next I'll make the swarm avoid the light.",
         "I've optimised the render loop; frame time is down to 2.1 ms."]
CODE_ADD = ['phase: BossPhase = BossPhase.Awaken;', 'if (this.hp < this.maxHp * 0.3) this.spitAcid(cone(40));',
            'const swarm = new Swarm(this.parasites, { cohesion: 0.8 });', 'this.roar.play({ sync: Beat.next() });',
            'uniform float uGlitch;', 'vec2 uv = vUv + vec2(noise(t * 40.0) * uGlitch, 0.0);',
            'for (const m of monsters) m.update(dt * TIMESCALE);', 'await lobby.join(region, { maxPlayers: 64 });',
            'export const TOKENS_PER_DOSE = 1_000_000;', 'if (limitReached) return waitUntil(3 * HOUR);',
            'this.crawlThrough(screen.surface, { glitch: 0.9 });', 'rage = Math.min(1, rage + dmg / 50);',
            'spawn("{m}", basement.monitors[i].position);', 'camera.shake(0.4 * beat.energy);',
            'this.eyes.glow = OPUS_ORANGE;', 'return this.target ?? player.nearest();']
CODE_DEL = ['hp = 100;', 'speed = 2;', '// TODO: make scarier', 'if (false) this.roar();', 'sleep(8 * HOUR);',
            'const limit = 20;', 'swarm = [];']
BASH = [('npm test -- {m}', ['PASS  src/monsters/{m}.test.ts (12 tests) 1.84s']),
        ('npm run build', ['vite v6.2.0 building for production...', '✓ 2148 modules transformed.', 'dist/vibegame.js  2.41 MB │ gzip: 612 kB']),
        ('git commit -am "{m}: phase two"', ['[main 4f2a91c] {m}: phase two', ' 6 files changed, 412 insertions(+), 38 deletions(-)']),
        ('npm run bench', ['frame time  2.1ms  ✓', 'monsters    4096  ✓']),
        ('git push', ['To github.com:vibegame/vibegame.git', '   4f2a91c..9b1e07d  main -> main'])]
VERBS = ['Vibing', 'Clauding', 'Pondering', 'Conjuring', 'Noodling', 'Percolating', 'Spelunking', 'Forging',
         'Brewing', 'Cooking', 'Manifesting', 'Scheming', 'Summoning', 'Tinkering', 'Hatching', 'Channeling']
COST = {'user': 1.8, 'text': 0.10, 'tool': 0.55, 'result': 0.35, 'diff': 0.045, 'blank': 0.02, 'todo': 0.07,
        'header': 0.0, 'err': 0.3}


def L(kind, *spans):
    return (kind, list(spans))


def header_lines(plan='Opus · Claude Max', cwd='~/vibegame'):
    return [L('header', (' ▐▛███▜▌', ORANGE), ('   Claude Code v2.1.17', FG, None, True)),
            L('header', ('▝▜█████▛▘', ORANGE), ('  ' + plan, DIM)),
            L('header', ('  ▘▘ ▝▝  ', ORANGE), ('  ' + cwd, DIM)),
            L('blank')]


def user_line(text):
    return L('user', ('> ' + text + ' ' * 4, (205, 205, 210), PROMPT_BG))


def gen_block(rng):
    m = rng.choice(MONSTERS)
    fm = lambda s: s.replace('{m}', m)
    out = []
    if rng.random() < 0.22:
        out += [user_line(fm(rng.choice(PROMPTS))), L('blank')]
    out += [L('text', ('⏺ ', FG), (fm(rng.choice(TEXTS)), FG)), L('blank')]
    for _ in range(rng.randint(1, 4)):
        r = rng.random()
        path = fm(rng.choice(FILES))
        if r < 0.3:
            out += [L('tool', ('⏺ ', GREEN), ('Read', FG, None, True), ('(' + path + ')', FG)),
                    L('result', ('  ⎿  ', DIM), ('Read %d lines (ctrl+r to expand)' % rng.randint(40, 900), DIM))]
        elif r < 0.72:
            na, nd = rng.randint(4, 60), rng.randint(0, 9)
            out += [L('tool', ('⏺ ', GREEN), ('Update', FG, None, True), ('(' + path + ')', FG)),
                    L('result', ('  ⎿  ', DIM), ('Updated ', DIM), (path, FG, None, True),
                      (' with %d additions and %d removals' % (na, nd), DIM))]
            ln = rng.randint(8, 300)
            for _ in range(rng.randint(3, 9)):
                k = rng.random()
                if k < 0.62:
                    code = '+  ' + fm(rng.choice(CODE_ADD))
                    out.append(L('diff', ('      %4d ' % ln, DIM), (code.ljust(84), ADD_FG, ADD_BG)))
                elif k < 0.8:
                    code = '-  ' + rng.choice(CODE_DEL)
                    out.append(L('diff', ('      %4d ' % ln, DIM), (code.ljust(84), DEL_FG, DEL_BG)))
                else:
                    out.append(L('diff', ('      %4d ' % ln, DIM), ('   ' + fm(rng.choice(CODE_ADD)), DIM)))
                ln += 1
        elif r < 0.9:
            cmd, res = rng.choice(BASH)
            out.append(L('tool', ('⏺ ', GREEN), ('Bash', FG, None, True), ('(' + fm(cmd) + ')', FG)))
            for i, line in enumerate(res):
                c = GREEN if ('PASS' in line or '✓' in line) else DIM
                out.append(L('result', ('  ⎿  ' if i == 0 else '     ', DIM), (fm(line), c)))
        else:
            out.append(L('tool', ('⏺ ', GREEN), ('Update Todos', FG, None, True)))
            items = rng.sample(['Acid cone attack', 'Parasite swarm AI', 'Glitch teleport shader', 'Skeleton phase two',
                                'Beat-synced roars', 'Crawl out of monitors', 'Battle pass', 'Multiplayer lobby'], 3)
            for i, it in enumerate(items):
                done = i < rng.randint(0, 3)
                out.append(L('todo', ('  ⎿  ' if i == 0 else '     ', DIM),
                             (('☒ ' if done else '☐ ') + it, DIM if done else FG)))
        out.append(L('blank'))
    return out


class Session:
    """Scrolling Claude Code transcript. Lines carry an appear time."""

    def __init__(self):
        self.kind, self.spans, self.t, self.block = [], [], [], []
        self.verb, self.block_t = [], []
        self.typing = []        # (t0, t1, text) shown in the input box
        self.idle = []          # (t0, t1) no spinner
        self.tok = None         # callable(t) -> tokens, optional

    def add(self, line, t, new_block=False, verb=None):
        if new_block or not self.block:
            self.verb.append(verb or VERBS[len(self.verb) % len(VERBS)])
            self.block_t.append(t)
        self.kind.append(line[0]); self.spans.append(line[1]); self.t.append(t)
        self.block.append(len(self.verb) - 1)

    def finalize(self):
        self.ta = np.array(self.t, dtype=np.float64)
        self.ra = np.array([tt for kd, tt in zip(self.kind, self.t) if kd == 'user'], dtype=np.float64)

    def generate(self, rng, t0, t1, speed, start_progress=0.0):
        """Append generated blocks whose lines appear between t0 and t1 at speed(t)."""
        tg = np.arange(t0, t1, 1 / FPS)
        P = np.cumsum(speed(tg)) / FPS + start_progress
        acc = 0.0
        while True:
            blk = gen_block(rng)
            verb = rng.choice(VERBS)
            first = True
            for line in blk:
                acc += COST[line[0]] * (0.6 + 0.8 * rng.random())
                i = np.searchsorted(P, acc)
                if i >= len(P):
                    return
                ta = float(tg[i])
                if line[0] == 'user':
                    tp = float(tg[np.searchsorted(P, acc - COST['user'] * 0.9)]) if acc > COST['user'] else ta - 1
                    self.typing.append((max(tp, ta - 1.6), ta - 0.1, line[1][0][0][2:].rstrip()))
                    self.idle.append((max(tp, ta - 1.6), ta))
                self.add(line, ta, new_block=first, verb=verb)
                first = False

    def count(self, t):
        return int(np.searchsorted(self.ta, t, 'right'))

    def input_text(self, t):
        for t0, t1, s in self.typing:
            if t0 <= t < t1 + 0.1:
                n = int(len(s) * min(1.0, (t - t0) / max(0.05, t1 - t0)))
                return s[:n]
        return ''

    def spinner(self, t):
        for t0, t1 in self.idle:
            if t0 <= t < t1:
                return None
        k = self.count(t)
        if k == 0:
            return None
        b = self.block[k - 1]
        # elapsed and tokens count from the last user prompt, like the real status line
        j = int(np.searchsorted(self.ra, t, 'right'))
        t_req = self.ra[j - 1] if j else self.t[0]
        el = t - t_req
        tok = self.tok(t) if self.tok else 1200 + 45 * (k - self.count(t_req)) + 160 * el
        return self.verb[b], el, tok


def fmt_tok(n):
    return ('%.1fM' % (n / 1e6)) if n >= 1e6 else ('%.1fk' % (n / 1e3)) if n >= 1e3 else str(int(n))


def fmt_el(s):
    s = int(max(0, s))
    return ('%dm %ds' % (s // 60, s % 60)) if s >= 60 else '%ds' % s


SPIN = '·✢✳✶✻✽✻✶✳✢'


def speed_profile(mon):
    rng = np.random.default_rng(mon * 7 + 1)
    jit = rng.uniform(0.75, 1.25, 400)

    def sp(t):
        t = np.asarray(t, dtype=np.float64)
        s = np.select([t < 30.9, t < 45.9, t < 60, t < 80, t < 100, t < 110.3, t < 132.5, t < 168, t < 188.1, t < 198],
                      [1.0, 1.2, 1.5, 2.6, 2.1, 2.0, 3.0, 0.0, 3.6, 0.35], 0.0)
        burst = jit[(np.clip(t, -399, 399).astype(int) // 3) % 400]
        return s * burst * (0.85 + 0.3 * (mon % 3) / 2)
    return sp


def build_sessions():
    """Sessions per monitor (generated, mid-flow), plus mon2's scripted storyline."""
    S = {}
    for m in range(1, 7):
        s = Session()
        rng = random.Random(1000 + m)
        s.generate(rng, -420.0, 220.0, speed_profile(m))
        s.finalize()
        S[m] = s
    # grid panes for mon4/mon6
    for m in (4, 6):
        for i in range(10):
            s = Session()
            rng = random.Random(5000 + m * 20 + i)
            prof = speed_profile(m + i)
            s.generate(rng, -300.0 - 17 * i, 220.0, lambda t, p=prof, k=1.1 + 0.35 * rng.random(): p(t) * k)
            s.finalize()
            S[(m, i)] = s
    S['m2'] = build_mon2_story()
    return S


def build_mon2_story():
    """mon2 storyline segments, see TREATMENT: hi -> one prompt -> $20 -> /exit -> right back."""
    segs = {}
    # B: fresh session at 30.9 ("It started with a hi")
    b = Session()
    for ln in header_lines('Sonnet · Claude Free'):
        b.add(ln, 30.9)
    b.typing += [(31.0, 31.45, 'hi'), (33.3, 35.35, 'one prompt. a game with monsters. make it sick')]
    b.idle += [(30.9, 31.6), (32.3, 35.5)]
    b.add(user_line('hi'), 31.6, True, 'Clauding'); b.add(L('blank'), 31.6)
    b.add(L('text', ('⏺ ', FG), ('Hi! What would you like to build today?', FG)), 32.3); b.add(L('blank'), 32.3)
    b.add(user_line('one prompt. a game with monsters. make it sick'), 35.5, True, 'Conjuring'); b.add(L('blank'), 35.5)
    b.add(L('text', ('⏺ ', FG), ("Love it. Let's build something unholy.", FG)), 36.0); b.add(L('blank'), 36.0)

    def sp(t):
        t = np.asarray(t, dtype=np.float64)
        return np.select([t < 38.6, t < 41.1, t < 43.4], [7.0, 16.0, 3.0], 0.0)
    b.generate(random.Random(77), 36.2, 43.4, sp)
    b.typing.append((43.5, 43.9, '/exit'))
    b.idle.append((43.4, 50))
    b.add(user_line('/exit'), 44.0, True)
    b.finalize()
    b.tok = lambda t: 400 + max(0, t - 36.2) ** 2.2 * 900
    segs['B'] = b
    # C: relaunch at 45.9 ("right back"), pro plan, then generated until the band arrives
    c = Session()
    for ln in header_lines('Opus · Claude Pro'):
        c.add(ln, 45.9)
    c.add(L('text', ('⏺ ', FG), ('Welcome back. Resuming where we left off.', FG)), 46.3, True, 'Resuming')
    c.add(L('blank'), 46.3)
    c.generate(random.Random(78), 46.5, 70.0, lambda t: np.full(np.shape(t), 3.2))
    c.finalize()
    c.tok = lambda t: 120e3 * math.exp(max(0.0, t - 45.9) * math.log(1.0e6 / 120e3) / (55.5 - 45.9))
    segs['C'] = c
    # D: withdrawal 141.5-149.6 (can't even write a for)
    d = Session()
    for ln in header_lines('Opus · Claude Max'):
        d.add(ln, 0.0)
    d.add(L('err', ('  ⎿  ', DIM), ('./band exited with code 137 (usage limit)', RED)), 141.5, True)
    d.add(L('blank'), 141.5)
    d.typing += [(141.9, 143.4, 'for (let i = 0; i <'), (145.0, 145.9, 'how do i write a for loop'),
                 (146.6, 147.2, '/model opus'), (148.7, 149.3, 'please')]
    d.idle.append((0, 200))
    d.add(user_line('how do i write a for loop'), 146.0, True); d.add(
        L('err', ('  ⎿  ', DIM), ('Claude usage limit reached · resets in 4h 59m', RED)), 146.1)
    d.add(L('blank'), 146.1)
    d.add(user_line('/model opus'), 147.3, True); d.add(
        L('err', ('  ⎿  ', DIM), ('Opus is unavailable: usage limit reached', RED)), 147.4)
    d.add(L('blank'), 147.4)
    d.finalize()
    segs['D'] = d
    # E: outro 188.1-198 ("just one more prompt")
    e = Session()
    for ln in header_lines('Opus · Claude Max'):
        e.add(ln, 0.0)
    e.generate(random.Random(79), 150.0, 189.6, lambda t: np.where(t < 168, 0.0, 2.5))
    e.typing += [(189.7, 191.3, 'just one more prompt...'), (194.7, 196.0, 'the last one. i swear.')]
    e.idle += [(189.6, 191.5), (194.6, 196.2)]
    e.add(user_line('just one more prompt...'), 191.5, True, 'Clauding'); e.add(L('blank'), 191.5)
    e.add(L('text', ('⏺ ', FG), ("Of course! Here's one more improvement.", FG)), 192.6); e.add(L('blank'), 192.6)
    e.add(user_line('the last one. i swear.'), 196.2, True, 'Clauding'); e.add(L('blank'), 196.2)
    e.add(L('text', ('⏺ ', FG), ("You're absolutely right.", FG)), 197.4)
    e.finalize()
    segs['E'] = e
    # haiku (mon3)
    h = Session()
    for ln in header_lines('Opus · Claude Max'):
        h.add(ln, 0.0)
    h.add(L('err', ('  ⎿  ', DIM), ('./band exited with code 137 (usage limit)', RED)), 144.0, True)
    h.add(L('blank'), 144.0)
    h.typing.append((144.5, 145.1, '/model haiku'))
    h.idle.append((0, 200))
    h.add(user_line('/model haiku'), 145.2, True)
    h.add(L('result', ('  ⎿  ', DIM), ('Set model to ', DIM), ('Haiku 4.5', FG, None, True)), 145.35)
    h.finalize()
    segs['H'] = h
    return segs


# ================================================================ CLI renderer
F28 = None


def term_font():
    return tfont(28)


def render_cli(d, sess, t, x0=16, y0=12, cols=111, rows=32, F=None, extra=(), spinner=True, box=True,
               verb_override=None, tok_boost=1.0, limit=False):
    F = F or term_font()
    trows = rows - 6 if box else rows - 2
    k = sess.count(t)
    lines = [sess.spans[i] for i in range(max(0, k - (trows - len(extra))), k)] + list(extra)
    lines = lines[-trows:]
    for r, sp in enumerate(lines):
        draw_spans(d, x0, y0 + r * F.lh, F, sp, cols)
    srow = y0 + (rows - 6 if box else rows - 2) * F.lh
    st = sess.spinner(t) if spinner and not limit else None
    if st:
        verb, el, tok = st
        verb = verb_override or verb
        g = SPIN[int(t * 8.5) % len(SPIN)]
        draw_spans(d, x0, srow, F, [(g + ' ', ORANGE), (verb + '… ', ORANGE_HI),
                                     ('(%s · ↑ %s tokens · esc to interrupt)' % (fmt_el(el), fmt_tok(tok * tok_boost)), DIM)], cols)
    elif limit:
        draw_spans(d, x0, srow, F, [('✗ ', RED), ('Claude usage limit reached. Your limit will reset at 3am.', RED)], cols)
    if not box:
        return
    by = y0 + (rows - 4) * F.lh
    bc = DIM2 if not limit else (120, 50, 50)
    draw_spans(d, x0, by, F, [('╭' + '─' * (cols - 2) + '╮', bc)])
    txt = sess.input_text(t)
    cur = '█' if (t * 1.6) % 1 < 0.6 else ' '
    draw_spans(d, x0, by + F.lh, F, [('│', bc), (' > ', FG), (txt, FG), (cur, (200, 200, 200))])
    draw_spans(d, x0 + (cols - 1) * F.cw, by + F.lh, F, [('│', bc)])
    draw_spans(d, x0, by + 2 * F.lh, F, [('╰' + '─' * (cols - 2) + '╯', bc)])
    draw_spans(d, x0, by + 3 * F.lh, F, [('  ▸▸ bypass permissions on', ORANGE_HI), (' (shift+tab to cycle)', DIM2)])


# ================================================================ pixel art (Clawd band)
U = 20
BW, BH = 96, 39
FLOOR = BH - 2
PAL = np.array([
    (0, 0, 0), ORANGE, (168, 86, 60), (150, 28, 42), (34, 34, 38), (138, 92, 54), (205, 205, 210),
    (232, 232, 228), (214, 174, 72), (150, 34, 40), (112, 112, 120), (78, 78, 86), (38, 96, 150),
    (172, 164, 156), (16, 16, 18), (226, 196, 146), (245, 168, 132), (60, 60, 66), (255, 255, 255),
], dtype=np.uint8)
YY, XX = np.mgrid[0:BH, 0:BW]


def rect(c, x, y, w, h, col):
    x0, y0 = max(0, int(x)), max(0, int(y))
    x1, y1 = min(c.shape[1], int(x + w)), min(c.shape[0], int(y + h))
    if x1 > x0 and y1 > y0:
        c[y0:y1, x0:x1] = col


def ell(c, cx, cy, rx, ry, col):
    c[((XX - cx) / rx) ** 2 + ((YY - cy) / ry) ** 2 <= 1.0] = col


def pline(c, x0, y0, x1, y1, col, th=1):
    n = int(max(abs(x1 - x0), abs(y1 - y0))) + 1
    for i in range(n + 1):
        x = x0 + (x1 - x0) * i / max(1, n)
        y = y0 + (y1 - y0) * i / max(1, n)
        rect(c, round(x - (th - 1) / 2), round(y - (th - 1) / 2), th, th, col)


def clawd(c, x, y, col=1, eyes='normal', mouth=0, arm_l=0, arm_r=0, lift=(0, 0, 0, 0), leg_h=4):
    """Clawd from Claude Code's welcome art at 2x4 units per sub-pixel. arm_* = vertical nub offset."""
    rect(c, x, y, 24, 16, col)
    rect(c, x - 4, y + 8 + arm_l, 4, 4, col)
    rect(c, x + 24, y + 8 + arm_r, 4, 4, col)
    for i, lx in enumerate((2, 6, 16, 20)):
        rect(c, x + lx, y + 16, 2, leg_h - lift[i], col)
    if eyes == 'normal':
        rect(c, x + 4, y + 4, 2, 4, 0); rect(c, x + 18, y + 4, 2, 4, 0)
    elif eyes == 'blink':
        rect(c, x + 4, y + 7, 2, 1, 0); rect(c, x + 18, y + 7, 2, 1, 0)
    elif eyes == 'sad':
        rect(c, x + 4, y + 6, 2, 2, 0); rect(c, x + 18, y + 6, 2, 2, 0)
        rect(c, x + 5, y + 4, 2, 1, 0); rect(c, x + 3, y + 3, 2, 1, 0)
        rect(c, x + 17, y + 4, 2, 1, 0); rect(c, x + 19, y + 3, 2, 1, 0)
    elif eyes == 'squint':
        for ex, sgn in ((4, 1), (19, -1)):
            for dy, dx in ((0, 0), (1, 1), (2, 1), (3, 0)):
                rect(c, x + ex + sgn * dx, y + 4 + dy, 2, 1, 0)
    elif eyes == 'dead':
        for ex in (3, 17):
            for i in range(4):
                rect(c, x + ex + i, y + 4 + i, 1, 1, 0)
                rect(c, x + ex + 3 - i, y + 4 + i, 1, 1, 0)
    if mouth > 0:
        rect(c, x + 9, y + 10, 6, min(5, mouth), 0)


def drum_back(c, kick_k, stick_l):
    """Cymbal stands, hi-hat and crash: behind the drummer."""
    rect(c, 23, 21, 1, FLOOR - 20, 10); rect(c, 74, 13, 1, FLOOR - 12, 10)
    ell(c, 23, 20, 5, 1, 8); ell(c, 23, 21.6 - (0.6 if stick_l == 'hat' else 0), 5, 0.8, 8)
    ell(c, 74, 12 + (1 if kick_k > 0.9 else 0), 6.5, 1.6 if kick_k > 0.9 else 1.2, 8)
    rect(c, 21, FLOOR, 5, 1, 10); rect(c, 72, FLOOR, 5, 1, 10)


def drum_front(c, cx, kick_k):
    """Snare, toms, floor tom and the bass drum with a spark on its head: in front of the drummer."""
    rect(c, 31, 28, 1, FLOOR - 27, 10); rect(c, 27, 27, 9, 3, 9); ell(c, 31, 27, 4.5, 1.3, 7)
    rect(c, 62, 28, 9, FLOOR - 27, 9); ell(c, 66.5, 28, 4.5, 1.3, 7)
    rect(c, 62, FLOOR, 1, 1, 10); rect(c, 70, FLOOR, 1, 1, 10)
    for tx in (41, 55):
        rect(c, tx - 3, 22, 7, 2, 9); ell(c, tx, 21.5, 3.6, 1.2, 7)
    by = 30 + (1 if kick_k > 0.5 else 0)
    ell(c, cx, by, 7.8, 7.8, 9)
    ell(c, cx, by, 6.8, 6.8, 18 if kick_k > 0.7 else 7)
    for k in range(8):
        a = k * math.pi / 4 + 0.2
        pline(c, cx, by, cx + math.cos(a) * 4, by + math.sin(a) * 4, 1)
    rect(c, cx - 1, by - 1, 2, 2, 1)
    rect(c, cx - 8, FLOOR, 2, 1, 10); rect(c, cx + 6, FLOOR, 2, 1, 10)


def guitar(c, gx, gy, body_col, neck_len, big=False):
    r1, r2 = (6, 4.5) if big else (5, 4)
    ell(c, gx + 1, gy + 1, r1, r1 * 0.85, body_col)
    ell(c, gx - 3, gy - 3, r2, r2 * 0.85, body_col)
    rect(c, gx - 1, gy - 1, 4, 2, 4)
    rect(c, gx + 1, gy + 2, 3, 1, 6)
    ex, ey = gx - 5 - neck_len, gy - 3 - neck_len * 0.24
    pline(c, gx - 4, gy - 2, ex, ey, 5, 2)
    if big:
        pline(c, gx - 4, gy - 2, ex, ey, 6, 1)
    rect(c, ex - 3, ey - 2, 3, 4, 4)


def amp(c, x, y, w, h):
    rect(c, x, y, w, h, 4)
    rect(c, x + 1, y + 1, w - 2, 2, 17)
    for yy in range(y + 4, y + h - 1, 2):
        for xx in range(x + 1 + (yy // 2) % 2, x + w - 1, 2):
            c[yy, xx] = 17
    rect(c, x + w // 2 - 2, y + 1, 4, 1, 1)


def topple(layer, f, bottom):
    """Crab layer falling over: on its side for the first half of f, then on its back, legs up."""
    ys, xs = np.nonzero(layer)
    if len(ys) == 0:
        return layer
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    sub = np.rot90(layer[y0:y1, x0:x1], 1) if f < 0.5 else layer[y0:y1, x0:x1][::-1]
    h, w = sub.shape
    oy = bottom + 1 - h - (1 if 0.5 <= f < 0.7 else 0)
    if oy < 0:
        sub, h, oy = sub[-oy:], h + oy, 0
    w = min(w, BW)
    ox = max(0, min(BW - w, int((x0 + x1) / 2 - w / 2)))
    out = np.zeros_like(layer)
    out[oy:oy + h, ox:ox + w] = sub[:, :w]
    return out


def band_canvas(member, t, intensity, frozen=None, fallen=0.0):
    """Unit canvas for one band member at time t: back props, the crab (+ held instrument), front props."""
    back, crab, front = (np.zeros((BH, BW), np.uint8) for _ in range(3))
    ta = min(t, frozen) if frozen is not None else t
    bi, ph = beat(ta)
    hb = min(2, int(round(intensity * 2.4 * math.exp(-ph * 5.0))))
    kk = A['kick'][fidx(ta)]; sk = A['snare'][fidx(ta)]
    eighth = ((ta - A['phase']) / (A['period'] / 2)) % 1
    blink = 'blink' if (ta + 0.9 * len(member)) % 3.7 < 0.12 else 'normal'
    eyes = 'dead' if fallen > 0 else blink
    bottom = FLOOR
    if member == 'drums':
        cx, cy = 36, 8 + hb
        stick_l = 'snare' if sk > 0.45 else ('hat' if eighth < 0.35 else 'up')
        stick_r = 'crash' if kk > 1.0 else ('tom' if kk > 0.55 else ('floor' if (bi % 2 == 1 and eighth < 0.4) else 'up'))
        if intensity < 0.3:
            stick_l = 'hat' if eighth < 0.3 else 'up'; stick_r = 'up'
        drum_back(back, kk, stick_l)
        clawd(crab, cx, cy, 1, 'squint' if kk > 1.1 and not fallen else eyes)
        if not fallen:
            tl = {'hat': (21, 19), 'snare': (31, 26), 'up': (26, 6)}[stick_l]
            tr = {'tom': (55, 20), 'crash': (71, 11), 'floor': (65, 27), 'up': (70, 5)}[stick_r]
            pline(crab, cx - 2, cy + 10, tl[0], tl[1], 15); pline(crab, cx + 26, cy + 10, tr[0], tr[1], 15)
        drum_front(front, 48, kk)
        if fallen:
            pline(front, 6, FLOOR, 15, FLOOR - 1, 15); pline(front, 80, FLOOR - 1, 88, FLOOR, 15)
            bottom = FLOOR - 3      # flat on its back behind the kit, only the legs stick out
    elif member in ('guitar', 'bass'):
        big = member == 'bass'
        if big:
            amp(back, 70, 13, 15, 25)
        else:
            amp(back, 72, 15, 13, 23)
        cx, cy = 36, 18 + hb
        strum = (-3 if eighth < 0.3 and intensity > 0.2 else 0) if not big else (-2 if kk > 0.5 else 0)
        lift = (1 if (bi % 2 == 0 and ph < 0.3) else 0, 0, 0, 1 if (bi % 2 == 1 and ph < 0.3) else 0)
        clawd(crab, cx, cy, 1, eyes, arm_r=strum, lift=lift, leg_h=4 - hb)
        guitar(crab, cx + 19, cy + 13, 12 if big else 3, 22 if big else 17, big)
        rect(crab, cx + 24, cy + 8 + strum, 4, 4, 1)    # strumming nub in front of the strings
    elif member == 'vocal':
        cx, cy = 40, 18 + hb
        line, k_line = current_lyric(ta)
        scream = line is not None and line.isupper()
        mouth = 0
        if line is not None and k_line < 1.0:
            mouth = 5 if scream else 2 + int(2.9 * abs(math.sin(ta * 17.0 + math.sin(ta * 5.3) * 2)))
        leg_h = 4 - hb
        if scream and not fallen:
            cx += 1 if int(ta * 24) % 2 else -1
        rect(back, 6, FLOOR - 4, 12, 5, 4); rect(back, 7, FLOOR - 3, 10, 2, 17)      # floor wedges
        rect(back, 78, FLOOR - 4, 12, 5, 4); rect(back, 79, FLOOR - 3, 10, 2, 17)
        clawd(crab, cx, cy, 1, 'squint' if scream and not fallen else eyes, mouth=0 if fallen else mouth, leg_h=leg_h)
        mx, my = 45, 27                                                            # mic stays put
        pline(front, mx + 1, my + 4, mx - 1, FLOOR, 10); rect(front, mx - 4, FLOOR, 7, 1, 10)
        rect(front, mx, my, 3, 4, 11); rect(front, mx, my, 3, 2, 6)
    if fallen:
        crab = topple(crab, fallen, bottom)
    c = back
    np.copyto(c, crab, where=crab > 0)
    np.copyto(c, front, where=front > 0)
    if member == 'guitar':      # right-handed guitarist on the left monitor, lefty bassist on the right
        c = c[:, ::-1].copy()
    return c


def paste_canvas(arr, c, y0, x0=0, unit=U, pal=PAL):
    rgb = pal[c]
    big = np.repeat(np.repeat(rgb, unit, 0), unit, 1)
    mask = np.repeat(np.repeat(c > 0, unit, 0), unit, 1)
    h = min(big.shape[0], arr.shape[0] - y0)
    w = min(big.shape[1], arr.shape[1] - x0)
    view = arr[y0:y0 + h, x0:x0 + w]
    np.copyto(view, big[:h, :w], where=mask[:h, :w, None])


def current_lyric(t):
    best = None
    for i, (ts, s) in enumerate(LYRICS):
        if ts <= t:
            nxt = LYRICS[i + 1][0] if i + 1 < len(LYRICS) else ts + 4
            dur = min(nxt - ts, len(s) * 0.075 + 0.7)
            best = (s, (t - ts) / dur) if t - ts < dur else None
        else:
            break
    return best if best else (None, 1.0)


# ================================================================ effects
GLITCH_COLS = [(217, 119, 87), (255, 255, 255), (0, 0, 0), (40, 220, 255), (255, 40, 120)]


def glitch(arr, amt, rng):
    if amt <= 0.01:
        return arr
    h, w = arr.shape[:2]
    out = arr.copy()
    for _ in range(int(2 + amt * 14)):
        y0 = rng.randrange(h); hh = rng.randrange(3, int(8 + amt * 90))
        dx = int(rng.gauss(0, 1) * amt * 170)
        out[y0:y0 + hh] = np.roll(out[y0:y0 + hh], dx, axis=1)
    s = int(amt * 16)
    if s:
        out[..., 0] = np.roll(out[..., 0], s, axis=1)
        out[..., 2] = np.roll(out[..., 2], -s, axis=1)
    for _ in range(int(amt * 14)):
        bw, bh = rng.randrange(16, int(40 + amt * 320)), rng.randrange(8, int(20 + amt * 130))
        x, y = rng.randrange(0, w - bw), rng.randrange(0, h - bh)
        r = rng.random()
        if r < 0.4:
            sx, sy = rng.randrange(0, w - bw), rng.randrange(0, h - bh)
            out[y:y + bh, x:x + bw] = arr[sy:sy + bh, sx:sx + bw]
        elif r < 0.7:
            out[y:y + bh, x:x + bw] = rng.choice(GLITCH_COLS)
        else:
            out[y:y + bh, x:x + bw] = 255 - out[y:y + bh, x:x + bw]
    if amt > 0.3:
        out[::3] = (out[::3] * (1 - 0.35 * amt)).astype(np.uint8)
    return out


def shake(arr, dx, dy):
    if dx == 0 and dy == 0:
        return arr
    out = np.zeros_like(arr)
    h, w = arr.shape[:2]
    xs0, xd0 = max(0, -dx), max(0, dx)
    ys0, yd0 = max(0, -dy), max(0, dy)
    out[yd0:h - ys0, xd0:w - xs0] = arr[ys0:h - yd0, xs0:w - xd0]
    return out


def flash_to(arr, col, k):
    if k <= 0.003:
        return arr
    k = min(1.0, k)
    return (arr * (1 - k) + np.array(col, np.float32) * k).astype(np.uint8)


def spark_mask(R, ang, seed=5):
    """Claude spark as an L mask (size ~2.2R): ~12 rounded, slightly irregular rays. Supersampled."""
    rng = random.Random(seed)
    rays = [(i * 2 * math.pi / 12 + rng.uniform(-0.09, 0.09), rng.uniform(0.66, 1.0), rng.uniform(0.095, 0.125))
            for i in range(12)]
    ss = 2
    S = int(R * 2.2 * ss)
    layer = Image.new('L', (S, S), 0)
    d = ImageDraw.Draw(layer)
    c0 = S / 2
    for a, ln, wd in rays:
        a += ang
        L_ = R * ln * ss
        w0, w1 = R * wd * ss * 0.8, R * wd * ss
        ca, sa = math.cos(a), math.sin(a)
        px, py = -sa, ca
        tip = (c0 + ca * (L_ - w1), c0 + sa * (L_ - w1))
        pts = [(c0 + px * w0, c0 + py * w0), (tip[0] + px * w1, tip[1] + py * w1),
               (tip[0] - px * w1, tip[1] - py * w1), (c0 - px * w0, c0 - py * w0)]
        d.polygon(pts, fill=255)
        d.ellipse([tip[0] - w1, tip[1] - w1, tip[0] + w1, tip[1] + w1], fill=255)
    d.ellipse([c0 - R * 0.2 * ss, c0 - R * 0.2 * ss, c0 + R * 0.2 * ss, c0 + R * 0.2 * ss], fill=255)
    return layer.resize((S // ss, S // ss), Image.LANCZOS)


def starburst(img, cx, cy, R, ang, col=ORANGE, seed=5, alpha=1.0, mask=None):
    layer = mask if mask is not None else spark_mask(R, ang, seed)
    if alpha < 1:
        layer = layer.point(lambda v: int(v * alpha))
    img.paste(Image.new('RGB', layer.size, col), (int(cx - layer.size[0] / 2), int(cy - layer.size[1] / 2)), layer)


_backdrop = []


def band_backdrop(img, t, cy):
    """Faint spark behind the band; pulses with the kick, brighter in choruses."""
    if not _backdrop:
        _backdrop.append(spark_mask(400, 0.13, seed=11))
    f = fidx(t)
    chorus = 60 <= t < 80 or 110.3 <= t < 132.5 or T_ON <= t < T_CALM or t >= T_CHAOS
    a = 0.05 + (0.24 if chorus else 0.07) * min(1.0, A['kick'][f])
    starburst(img, W / 2, cy, 400, 0, ORANGE, alpha=a, mask=_backdrop[0])


# ================================================================ screen modes
def bg_flash(t, m, base=BG, kind='band'):
    f = fidx(t)
    kk, sk = A['kick'][f], A['snare'][f]
    if 60 <= t < 80 or 110.3 <= t < 132.5:
        a, b = 0.30, 0.18
    elif T_ON <= t < T_CALM or T_CHAOS <= t:
        a, b = 0.42, 0.30
    elif 80 <= t < 100:
        a, b = 0.12, 0.06
    elif 101.2 <= t < 110.3:
        a, b = 0.05, 0.03
    else:
        a, b = 0.0, 0.0
    if kind == 'cli' and a < 0.3:      # agent screens pulse at full strength in choruses
        a, b = a * 0.55, b * 0.55
    k = kk * a + sk * b
    tgt = (255, 150, 105) if m in (1, 2, 3, 5) else (230, 180, 150)
    if m in (4, 6) and a >= 0.3 and base == BG:     # agent screens: warmer base in choruses
        base = (34, 27, 25)
    return mix(base, tgt, k * 0.55)


def new_frame(col):
    img = Image.new('RGB', (W, H), col)
    return img, ImageDraw.Draw(img)


def cli_frame(m, t, S, bg=None):
    img, d = new_frame(bg or bg_flash(t, m, kind='cli'))
    render_cli(d, S[m], t)
    return img


def mon2_story_frame(t, S, bg):
    st = S['m2']
    img, d = new_frame(bg)
    if t < 30.9:
        render_cli(d, S[2], t)
    elif t < 44.1:
        render_cli(d, st['B'], t)
        if 41.1 <= t < 45.0:
            popup(d, t - 41.1, ['✓ Claude Pro activated', '$20.00 / month · billed monthly', 'Thanks for subscribing!'])
    elif t < 45.9:
        F = term_font()
        k = st['B'].count(t)
        lines = [st['B'].spans[i] for i in range(max(0, k - 24), k)]
        for r, sp in enumerate(lines):
            draw_spans(d, 16, 12 + r * F.lh, F, [(s[0], DIM2) for s in sp], 111)
        y = 12 + (len(lines) + 1) * F.lh
        typed = 'claude'[:max(0, int((t - 45.4) / 0.05))] if t >= 45.4 else ''
        cur = '█' if (t * 1.6) % 1 < 0.6 else ' '
        draw_spans(d, 16, y, F, [('maximplv@basement ', GREEN), ('~/vibegame ', BLUE), ('$ ', FG), (typed, FG), (cur, FG)])
    else:
        render_cli(d, st['C'], t)
    return img


def popup(d, dt, lines, col=GREEN):
    F = tfont(38)
    w = 44
    x0 = int((W - w * F.cw) / 2)
    y0 = int(H * 0.30)
    d.rectangle([x0 - 10, y0 - 6, x0 + w * F.cw + 10, y0 + (len(lines) + 2) * F.lh + 6], fill=(14, 20, 15))
    draw_spans(d, x0, y0, F, [('╭─ Subscription ' + '─' * (w - 17) + '╮', col)])
    for i, s in enumerate(lines):
        c = col if i == 0 else FG
        draw_spans(d, x0, y0 + (i + 1) * F.lh, F, [('│ ', col), (s.ljust(w - 4), c, None, i == 0), (' │', col)])
    draw_spans(d, x0, y0 + (len(lines) + 1) * F.lh, F, [('╰' + '─' * (w - 2) + '╯', col)])


BAND = {1: ('guitar', 'Shredding', './band --role guitar --tuning drop-A'),
        2: ('vocal', 'Screaming', './band --role vocals --gain 11'),
        3: ('bass', 'Thumping', './band --role bass --strings 5'),
        5: ('drums', 'Drumming', './band --role drums --bpm 100')}


def section_intensity(t):
    if 60 <= t < 80: return 0.8
    if 80 <= t < 100: return 0.5
    if 101.2 <= t < 110.3: return 0.25
    if 110.3 <= t < 132.5: return 1.0
    if T_ON <= t < T_CALM: return 1.0
    if t >= T_CHAOS: return 1.0
    return 0.6


def band_frame(m, t, bg=None, frozen=None, fallen=0.0, limit=False):
    member, verb, cmd = BAND[m]
    bgc = bg or (LIMIT_BG if limit else bg_flash(t, m))
    img, d = new_frame(bgc)
    F = term_font()
    if not limit:
        band_backdrop(img, t, 12 + 2 * F.lh + 8 + 17 * U)
    draw_spans(d, 16, 12, F, [('⏺ ', GREEN), ('Bash', FG, None, True), ('(' + cmd + ')', FG)])
    draw_spans(d, 16, 12 + F.lh, F, [('  ⎿  ', DIM), ('Running… ', DIM), ('(ctrl+c to stop)', DIM2)])
    arr = np.asarray(img).copy()
    c = band_canvas(member, t, section_intensity(t), frozen=frozen, fallen=fallen)
    by = 12 + 2 * F.lh + 8
    floor_y = by + (FLOOR + 1) * U
    arr[floor_y:floor_y + 3, 40:W - 40] = (60, 52, 50) if not limit else (90, 30, 30)
    paste_canvas(arr, c, by)
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    if member == 'vocal' and not limit:
        line, k = current_lyric(t)
        if line:
            n = max(1, int(len(line) * min(1.0, k * 2.2)))
            fb = tfont(64, True)
            s = line[:n].upper() if line.isupper() else line[:n]
            text_center(d, W / 2, by + 70, s, fb.f, ORANGE_HI if line.isupper() else FG)
    srow = 12 + 26 * F.lh
    if limit:
        draw_spans(d, 16, srow, F, [('✗ ', RED), ('Claude usage limit reached. Your limit will reset at 3am.', RED)])
    else:
        g = SPIN[int(t * 8.5) % len(SPIN)]
        el = t - T_BAND.get(m, 60) + 4
        tok = 48000 + (t - 60) * 2600
        draw_spans(d, 16, srow, F, [(g + ' ', ORANGE), (verb + '… ', ORANGE_HI),
                                     ('(%s · ↑ %s tokens · esc to interrupt)' % (fmt_el(el), fmt_tok(tok)), DIM)])
    by2 = 12 + 28 * F.lh
    bc = DIM2 if not limit else (120, 50, 50)
    draw_spans(d, 16, by2, F, [('╭' + '─' * 109 + '╮', bc)])
    draw_spans(d, 16, by2 + F.lh, F, [('│', bc), (' > ', FG)])
    draw_spans(d, 16 + 110 * F.cw, by2 + F.lh, F, [('│', bc)])
    draw_spans(d, 16, by2 + 2 * F.lh, F, [('╰' + '─' * 109 + '╯', bc)])
    draw_spans(d, 16, by2 + 3 * F.lh, F, [('  ▸▸ bypass permissions on', ORANGE_HI), (' (shift+tab to cycle)', DIM2)])
    return img


def limit_banner(d, t, small=False):
    fb = tfont(58 if not small else 40, True)
    fr = tfont(34 if not small else 26)
    cx, cy = W / 2, H * (0.42 if not small else 0.2)
    pulse = 0.75 + 0.25 * math.sin(t * 6)
    col = mix((120, 20, 20), (250, 90, 70), pulse)
    bw, bh = (1240, 230) if not small else (980, 170)
    d.rounded_rectangle([cx - bw / 2, cy - bh / 2, cx + bw / 2, cy + bh / 2], 18, fill=(28, 6, 6), outline=col, width=5)
    text_center(d, cx, cy - bh * 0.17, '⚠ Usage limit reached', fb.f, col)
    text_center(d, cx, cy + bh * 0.22, 'Resets in 4h 59m · at 3:00 AM', fr.f, (235, 190, 180))


def right_frame(t, m):
    img, d = new_frame((8, 8, 9))
    dt = t - T_RIGHT[0]
    fb = tfont(100, True)
    s = "You're absolutely right!"
    n = min(len(s), int(dt / 0.012) + 1)
    w = fb.cw * (len(s) + 2)
    x0 = (W - w) / 2
    y0 = H / 2 - fb.lh / 2
    draw_spans(d, x0, y0, fb, [('⏺ ', FG), (s[:n], FG)])
    fr = tfont(30)
    draw_spans(d, x0 + 2 * fb.cw, y0 + fb.lh + 16, fr, [('⎿  ', DIM), ('session %d · agent %d' % (m, m * 7 % 10), DIM)])
    arr = np.asarray(img)
    return Image.fromarray(flash_to(arr, (255, 255, 255), max(0.0, 0.5 - dt * 3)))


def countdown_frame(t, m):
    f = fidx(t)
    beats_hit = 0.0
    for tk, s in A['kicks']:
        if 149.2 <= tk <= t < tk + 0.35 and (149.2 <= tk < 151.9 or 154.0 <= tk < 156.5):
            beats_hit = max(beats_hit, min(1.0, s) * math.exp(-(t - tk) / 0.09))
    img, d = new_frame((10, 4, 4))
    remain = 4 * 3600 + 59 * 60 + 59 - int(t - T_COUNT)
    s = '%d:%02d:%02d' % (remain // 3600, remain // 60 % 60, remain % 60)
    fb = tfont(330, True)
    col = mix((210, 50, 40), (255, 120, 90), A['kick'][f] * 0.6)
    text_center(d, W / 2, H * 0.5, s, fb.f, col)
    fr = tfont(40)
    text_center(d, W / 2, H * 0.2, 'Usage limit reached · resets in', fr.f, (200, 120, 110))
    if 151.8 <= t < 154.4:
        text_center(d, W / 2, H * 0.8, 'FIVE HOURS', tfont(70, True).f, (240, 200, 190))
    arr = np.asarray(img)
    if beats_hit > 0.05:
        inv = 255 - arr
        arr = (arr * (1 - beats_hit) + inv * beats_hit).astype(np.uint8)
        arr = glitch(arr, beats_hit * 0.6, random.Random(f * 13 + m))
        arr = shake(arr, int((m % 2 * 2 - 1) * beats_hit * 30), int(beats_hit * 18))
    return Image.fromarray(arr)


def weekly_frame(t):
    img, d = new_frame((0, 0, 0))
    dt = t - T_WEEKLY
    fr = tfont(46)
    a = 1.0 if dt < 0.62 else max(0.0, 1 - (dt - 0.62) / 0.18)
    flick = 0.8 + 0.2 * random.Random(int(t * 24)).random()
    text_center(d, W / 2, H / 2, 'Weekly limit reached.', fr.f, mix((0, 0, 0), (225, 225, 225), a * flick))
    if dt > 0.62:   # CRT collapse
        k = (dt - 0.62) / 0.18
        hh = max(2, int(H * (1 - k) * 0.06))
        d.rectangle([0, H / 2 - hh, W, H / 2 + hh], fill=mix((0, 0, 0), (200, 200, 200), 1 - k))
    return img


def logo_frame(t, m):
    img, d = new_frame((0, 0, 0))
    dt = t - T_LOGO
    a = smooth(0.0, 0.45, dt)
    ang = dt * math.radians(14) + m * 0.0
    starburst(img, W / 2, H * 0.46, 330, ang, mix((0, 0, 0), ORANGE, a), seed=5)
    fr = tfont(32)
    text_center(d, W / 2, H * 0.88, 'Your limit has been reset.', fr.f, mix((0, 0, 0), (150, 150, 150), smooth(0.4, 1.2, dt)))
    return img


def grow_overlay(img, t, tpop):
    """Spinner glyph swells into the crab before it pops in."""
    k = smooth(tpop - 0.45, tpop, t)
    F = term_font()
    sx, sy = 16 + F.cw / 2, 12 + 26 * F.lh + F.lh / 2
    cx = sx + (W / 2 - sx) * k
    cy = sy + (H * 0.48 - sy) * k
    starburst(img, cx, cy, 12 + 380 * k ** 2, t * 9, ORANGE, seed=5)


def price_overlay(img, t, m):
    for sets in PRICE_SETS:
        if sets[0] <= t < sets[4]:
            i = max(j for j in range(4) if sets[j] <= t)
            dt = t - sets[i]
            break
    else:
        return img
    arr = np.asarray(img) * 0.2
    arr = arr + (np.array((255, 236, 220)) - arr) * (0.55 * math.exp(-dt * 10))   # flash on each new price
    img = Image.fromarray(arr.astype(np.uint8))
    d = ImageDraw.Draw(img)
    pop = 1.0 + 0.25 * math.exp(-dt * 12)
    if m == 4:
        big = ['$20', '$100', '$200', 'OPUS'][i]
        sub = ['Claude Pro · per month', 'Claude Max 5x · per month', 'Claude Max 20x · per month',
               'model: opus · injecting'][i]
        fb = tfont(int(300 * pop), True)
        text_center(d, W / 2, H * 0.43, big, fb.f, ORANGE if i < 3 else ORANGE_HI)
        text_center(d, W / 2, H * 0.72, sub, tfont(52).f, FG)
        if i == 3:
            k = min(1.0, dt / 2.4)
            x0, x1 = W * 0.2, W * 0.8
            d.rectangle([x0, H * 0.82, x1, H * 0.86], outline=ORANGE, width=3)
            d.rectangle([x0 + 6, H * 0.82 + 6, x0 + 6 + (x1 - x0 - 12) * k, H * 0.86 - 6], fill=ORANGE)
    else:
        amt = ['−$20.00', '−$100.00', '−$200.00', '−$200.00'][i]
        sub = ['ANTHROPIC *CLAUDE PRO', 'ANTHROPIC *CLAUDE MAX', 'ANTHROPIC *CLAUDE MAX', 'ANTHROPIC *CLAUDE MAX · ACCT 2'][i]
        fb = tfont(int(230 * pop), True)
        d.rounded_rectangle([W * 0.12, H * 0.18, W * 0.88, H * 0.82], 30, fill=(34, 34, 40), outline=(90, 90, 98), width=4)
        text_center(d, W / 2, H * 0.30, 'Card •••• 4242  · just now', tfont(40).f, DIM)
        text_center(d, W / 2, H * 0.50, amt, fb.f, (240, 95, 90))
        text_center(d, W / 2, H * 0.70, sub, tfont(46).f, FG)
    return img


def plan_overlay(img, t, m):
    for t0, a, b in PLAN_BANNERS.get(m, []):
        if t0 <= t < t0 + 1.9:
            d = ImageDraw.Draw(img)
            F = term_font()
            w = 60
            x0 = int((W - w * F.cw) / 2)
            y0 = int(H * 0.36)
            d.rectangle([x0, y0, x0 + w * F.cw, y0 + 4 * F.lh], fill=(14, 22, 16))
            draw_spans(d, x0, y0, F, [('╭' + '─' * (w - 2) + '╮', GREEN)])
            draw_spans(d, x0, y0 + F.lh, F, [('│ ', GREEN), (('✓ ' + a).ljust(w - 4), GREEN, None, True), (' │', GREEN)])
            draw_spans(d, x0, y0 + 2 * F.lh, F, [('│ ', GREEN), (('  ' + b).ljust(w - 4), FG), (' │', GREEN)])
            draw_spans(d, x0, y0 + 3 * F.lh, F, [('╰' + '─' * (w - 2) + '╯', GREEN)])
    return img


def clock_str(t):
    mins = 2 * 60 + 56 + int((t + 42.0) // 60)    # 3:00 exactly at t = 198
    return '%d:%02d' % (mins // 60, mins % 60)


def grid_frame(m, t, S, limit_t=None):
    n = 2 if t < 91.7 and t >= T_GRID else 4 if t < 92.0 and t >= T_GRID else 10
    cols, rows = (2, 1) if n == 2 else (2, 2) if n == 4 else (2, 5)
    img, d = new_frame(bg_flash(t, m, kind='cli'))
    F = tfont(14 if n == 10 else 20)
    bar = 26
    pw, ph = W / cols, (H - bar) / rows
    for i in range(n):
        cx, cy = i % cols, i // cols
        x0, y0 = cx * pw, cy * ph
        s = S[(m, i)]
        pc = max(1, int((pw - 16) / F.cw)); pr = max(3, int((ph - 8) / F.lh))
        lim = limit_t is not None and t >= limit_t + i * 0.08
        if lim:
            d.rectangle([x0, y0, x0 + pw, y0 + ph], fill=(26, 6, 6))
        k = s.count(min(t, T_LIMIT) if lim else t)
        lines = [s.spans[j] for j in range(max(0, k - (pr - 3)), k)]
        for r, sp in enumerate(lines):
            draw_spans(d, x0 + 8, y0 + 4 + r * F.lh, F, [(q[0], DIM2) + tuple(q[2:3]) for q in sp] if lim else sp, pc)
        yy = y0 + 4 + (pr - 2) * F.lh
        if lim:
            draw_spans(d, x0 + 8, yy, F, [('✗ Claude usage limit reached · resets 3am', RED, None, True)], pc)
        else:
            st = s.spinner(t)
            if st:
                g = SPIN[int(t * 8.5 + i) % len(SPIN)]
                draw_spans(d, x0 + 8, yy, F, [(g + ' ', ORANGE), (st[0] + '… ', ORANGE_HI),
                                              ('(%s · ↑ %s tokens)' % (fmt_el(st[1]), fmt_tok(st[2])), DIM)], pc)
            draw_spans(d, x0 + 8, yy + F.lh, F, [('> ', FG), (s.input_text(t), FG)], pc)
    lc = (70, 70, 76)
    for cx in range(1, cols):
        d.rectangle([cx * pw - 1, 0, cx * pw, H - bar], fill=lc)
    for cy in range(1, rows):
        d.rectangle([0, cy * ph - 1, W, cy * ph], fill=lc)
    act = int(t * 1.3) % n
    ax, ay = act % cols * pw, act // cols * ph
    d.rectangle([ax, ay, ax + pw - 1, ay + ph - 1], outline=GREEN, width=2)
    d.rectangle([0, H - bar, W, H], fill=(0, 160, 80))
    fs = tfont(18)
    draw_spans(d, 8, H - bar + 2, fs, [('[vibe] ', (0, 0, 0)), ('0:claude* 1:claude- 2:claude 3:claude 4:htop', (0, 0, 0))])
    rs = '"basement" %s 24-Oct-26' % clock_str(t)
    draw_spans(d, W - 8 - len(rs) * fs.cw, H - bar + 2, fs, [(rs, (0, 0, 0))])
    return img


# ================================================================ per-monitor timeline
_S = None


def sessions():
    global _S
    if _S is None:
        _S = build_sessions()
    return _S


def emerge_amount(m, t):
    te = T_EMERGE.get(m)
    if te is None or not (te <= t < te + 2.2):
        return 0.0, 0.0
    dt = t - te
    g = smooth(0, 0.25, dt) * (1 - smooth(1.4, 2.2, dt))
    hole = smooth(0.15, 0.6, dt) * (1 - smooth(1.2, 1.8, dt))
    return g, hole


def tear(arr, hole, t, seed):
    if hole <= 0.01:
        return arr
    img = Image.fromarray(arr)
    d = ImageDraw.Draw(img)
    rng = random.Random(seed)
    cx, cy = W / 2, H * 0.46
    R = 60 + 520 * hole
    pts = []
    for i in range(48):
        a = i / 48 * 2 * math.pi
        r = R * (0.75 + 0.35 * rng.random())
        pts.append((cx + math.cos(a) * r * 1.25, cy + math.sin(a) * r * 0.85))
    d.polygon(pts, fill=(0, 0, 0))
    for i in range(60):
        a = rng.uniform(0, 2 * math.pi)
        dist = R * (0.9 + rng.random() * 0.8) + (t * 900 % 300)
        sz = rng.randrange(14, 64)
        x, y = cx + math.cos(a) * dist * 1.25, cy + math.sin(a) * dist * 0.85
        d.rectangle([x, y, x + sz, y + sz], fill=rng.choice([ORANGE, (255, 255, 255), ORANGE_HI, (60, 220, 255)]))
    return np.asarray(img).copy()


def render_mon(m, t):
    S = sessions()
    if t >= T_END or T_OFF <= t < T_ON:
        return np.zeros((H, W, 3), np.uint8)
    if T_WEEKLY <= t < T_OFF:
        return np.asarray(weekly_frame(t)).copy()
    if T_COUNT <= t < T_WEEKLY:
        return np.asarray(countdown_frame(t, m)).copy()
    if T_LOGO <= t < T_CHAOS:
        return np.asarray(logo_frame(t, m)).copy()
    if T_RIGHT[0] <= t < T_RIGHT[1]:
        return np.asarray(right_frame(t, m)).copy()
    rng = random.Random(fidx(t) * 31 + m)
    gl, shk, white = 0.0, (0, 0), 0.0
    band = m in BAND
    if T_CALM <= t < T_LOGO:
        if m == 2:
            img, d = new_frame(BG)
            render_cli(d, S['m2']['E'], t)
        else:
            img = cli_frame(m, t, S, BG)
    elif T_LIMIT <= t < T_COUNT:
        fall_t = T_LIMIT + 0.8 + {1: 0.0, 2: 0.25, 3: 0.12, 5: 0.35}.get(m, 0)
        fallen = 0.0 if t < fall_t else min(1.0, (t - fall_t) / 0.45)
        if m == 2 and t >= 141.5:
            img, d = new_frame(LIMIT_BG)
            render_cli(d, S['m2']['D'], t, limit=True)
        elif m == 3 and t >= 144.0:
            img, d = new_frame(LIMIT_BG)
            render_cli(d, S['m2']['H'], t, limit=True)
            if t >= 145.6:
                arr = np.asarray(img).copy()
                c = np.zeros((BH, BW), np.uint8)          # small pale Haiku crab, shivering
                bob = int(round(math.sin((t - 145.6) * 1.7) * 0.6 + 0.4))
                clawd(c, 36, 16 + bob, 13, 'blink' if (t - 145.6) % 2.9 < 0.15 else 'sad')
                paste_canvas(arr, c, 330 + rng.randint(-2, 2), 480 + rng.randint(-3, 3), unit=10)
                img = Image.fromarray(arr)
        elif band:
            img = band_frame(m, t, frozen=T_LIMIT, fallen=fallen, limit=True)
            limit_banner(ImageDraw.Draw(img), t, small=True)
        else:
            img = grid_frame(m, t, S, limit_t=T_LIMIT)
            limit_banner(ImageDraw.Draw(img), t)
        if t < T_LIMIT + 0.3:
            white = 0.0
            gl = 0.3 * (1 - (t - T_LIMIT) / 0.3)
        if t >= T_SCREAM:
            amp_ = 3 + 9 * math.exp(-(t - T_SCREAM) * 0.8)
            shk = (int(rng.gauss(0, amp_)), int(rng.gauss(0, amp_ * 0.6)))
            gl = max(gl, 0.06 + 0.5 * math.exp(-(t - T_SCREAM) * 3))
    else:
        on_band = band and ((T_BAND[m] <= t < T_LIMIT) or (T_ON <= t) or t >= T_CHAOS)
        if on_band:
            img = band_frame(m, t)
            if T_BAND[m] <= t < T_BAND[m] + 0.12:
                white = 1 - (t - T_BAND[m]) / 0.12
        elif m == 2 and t < T_BAND[2]:
            img = mon2_story_frame(t, S, bg_flash(t, m, kind='cli'))
            if T_BAND[2] - 0.45 <= t:
                grow_overlay(img, t, T_BAND[2])
        elif band:
            img = cli_frame(m, t, S)
            if T_BAND[m] - 0.45 <= t < T_BAND[m]:
                grow_overlay(img, t, T_BAND[m])
        else:
            grid = (T_GRID <= t < T_LIMIT) or t >= T_ON
            img = grid_frame(m, t, S) if grid else cli_frame(m, t, S)
            img = plan_overlay(img, t, m)
            img = price_overlay(img, t, m)
        g, hole = emerge_amount(m, t)
        for te in T_EMERGE.values():
            if te <= t < te + 0.6 and m not in T_EMERGE or (te <= t < te + 0.6 and T_EMERGE.get(m) != te):
                gl = max(gl, 0.18 * (1 - (t - te) / 0.6))
        if g > 0 or hole > 0:
            arr = tear(np.asarray(img).copy(), hole, t, fidx(t))
            img = Image.fromarray(arr)
            gl = max(gl, g)
            shk = (int(rng.gauss(0, 14 * g)), int(rng.gauss(0, 9 * g)))
        if T_ON <= t < T_ON + 0.25:
            white = max(white, 1 - (t - T_ON) / 0.25)
        if T_ON + 0.2 <= t < T_ON + 1.0:
            d = ImageDraw.Draw(img)
            d.rounded_rectangle([W / 2 - 520, H * 0.42 - 70, W / 2 + 520, H * 0.42 + 70], 16,
                                fill=(10, 30, 16), outline=GREEN, width=5)
            text_center(d, W / 2, H * 0.42, '✓ Your limit has been reset', tfont(58, True).f, GREEN)
        if 187.2 <= t < 187.5:
            white = max(white, 0.8 * (1 - (t - 187.2) / 0.3))
        if t >= T_CHAOS:
            dt = t - T_CHAOS
            ramp = min(1.0, dt / (T_END - T_CHAOS))
            f = fidx(t)
            hit = A['kick'][f] + A['snare'][f]
            gl = max(gl, 0.15 + 0.5 * ramp + 0.3 * min(1, hit))
            white = max(white, min(1.0, hit * 0.45) * (0.5 + 0.5 * ramp))
            shk = (int(rng.gauss(0, 6 + 20 * ramp)), int(rng.gauss(0, 4 + 12 * ramp)))
            if rng.random() < 0.06 + 0.2 * ramp:
                img = Image.fromarray(255 - np.asarray(img))
            if dt < 0.12:
                white = 1.0
    arr = np.asarray(img)
    if T_LIMIT <= t < T_LIMIT + 0.15:
        arr = flash_to(arr, (255, 40, 30), 0.7 * (1 - (t - T_LIMIT) / 0.15))
    if T_SCREAM <= t < T_SCREAM + 0.25:
        arr = flash_to(arr, (255, 30, 20), 0.85 * (1 - (t - T_SCREAM) / 0.25))
    if white > 0:
        arr = flash_to(arr, (255, 244, 235), white)
    if gl > 0:
        arr = glitch(np.ascontiguousarray(arr), gl, rng)
    if shk != (0, 0):
        arr = shake(arr, *shk)
    return np.ascontiguousarray(arr)


# ================================================================ phone
NOTIFS = [(98.6, 'Messages', 'Alex', 'are you alive?'), (99.2, 'Messages', 'Dima', 'bro?? you there'),
          (99.8, 'Messages', 'Sam', "haven't seen you online in 3 days"),
          (100.4, 'Messages', 'Mom', 'Son, are you okay? Please call me back'),
          (101.0, 'Messages', 'Jules', 'your basement light has been on all week'),
          (101.6, 'Messages', 'Alex', 'ARE YOU ALIVE'), (102.3, 'Messages', 'Dima', 'calling the police if you dont answer'),
          (103.0, 'Messages', 'Mom', 'I love you. Please just call me.')]


def phone_frame(t):
    img = Image.new('RGB', (PW, PH), (0, 0, 0))
    d = ImageDraw.Draw(img)
    on = (96.2 <= t < 110.0) or (198.0 <= t < 206.3)
    if not on:
        return img
    bright = 1.0
    if 107.6 <= t < 110.0:
        bright = 0.35 if t < 109.9 else 0.0
    if t < 96.4:
        bright = (t - 96.2) / 0.2
    for y in range(0, PH, 8):     # wallpaper gradient
        k = y / PH
        d.rectangle([0, y, PW, y + 8], fill=mix((18, 20, 34), (44, 22, 30), k))
    status_bar(d, t)
    if 96.2 <= t < 100.0:         # incoming call
        text_center(d, PW / 2, 330, 'Mom', sfont(84, 'Regular'), (255, 255, 255))
        text_center(d, PW / 2, 410, 'mobile', sfont(36), (200, 200, 205))
        r = 88 + 10 * abs(math.sin((t - 96.2) * 5))
        d.ellipse([PW / 2 - 90, 470, PW / 2 + 90, 650], fill=(120, 120, 130))
        text_center(d, PW / 2, 560, 'M', sfont(96, 'Semibold'), (255, 255, 255))
        for cx, col, lab in ((190, (235, 70, 60), 'Decline'), (530, (60, 200, 90), 'Accept')):
            rr = 78 if lab == 'Decline' else r
            d.ellipse([cx - rr, 1250 - rr, cx + rr, 1250 + rr], fill=col)
            text_center(d, cx, 1370, lab, sfont(30), (255, 255, 255))
        draw_notifs(d, t, top=60, max_n=2)
    else:
        lx, ly = PW / 2, 100                      # padlock
        d.arc([lx - 13, ly - 26, lx + 13, ly + 2], 180, 360, fill=(235, 235, 240), width=5)
        d.rounded_rectangle([lx - 19, ly - 8, lx + 19, ly + 20], 5, fill=(235, 235, 240))
        text_center(d, PW / 2, 160, 'Saturday, October 24', sfont(34, 'Semibold'), (230, 230, 240))
        text_center(d, PW / 2, 285, clock_str(t), sfont(190, 'Semibold'), (240, 240, 250))
        if t >= 198.0:
            banner(d, 470, 'Claude', 'now', 'Your limit has been reset ✓', 1.0, ORANGE)
        else:
            banner(d, 470, 'Phone', '3m ago', 'Missed Call: Mom', 1.0, (60, 200, 90))
            draw_notifs(d, t, top=620, max_n=6)
    arr = np.asarray(img)
    return Image.fromarray((arr * bright).astype(np.uint8)) if bright < 1 else img


def status_bar(d, t):
    f = sfont(26, 'Semibold')
    for i in range(4):                            # weak signal
        h = 8 + i * 5
        d.rounded_rectangle([40 + i * 11, 44 - h, 47 + i * 11, 44], 2, fill=(235, 235, 240) if i < 1 else (90, 90, 96))
    d.text((92, 22), 'LTE', font=f, fill=(235, 235, 240))
    d.rounded_rectangle([PW - 92, 24, PW - 44, 46], 6, outline=(150, 150, 156), width=2)
    d.rectangle([PW - 40, 31, PW - 37, 39], fill=(150, 150, 156))
    d.rounded_rectangle([PW - 88, 28, PW - 82, 42], 2, fill=(235, 60, 50))   # 4 %
    d.text((PW - 104, 22), '4%', font=f, fill=(235, 235, 240), anchor='ra')


def fit(s, font, maxw):
    if font.getlength(s) <= maxw:
        return s
    while s and font.getlength(s + '…') > maxw:
        s = s[:-1]
    return s.rstrip() + '…'


def banner(d, y, app, when, body, alpha, icon_col):
    d.rounded_rectangle([24, y, PW - 24, y + 132], 30, fill=mix((0, 0, 0), (58, 58, 66), alpha))
    d.rounded_rectangle([44, y + 22, 104, y + 82], 14, fill=icon_col)
    d.text((122, y + 22), app.upper(), font=sfont(26, 'Semibold'), fill=(200, 200, 205))
    d.text((PW - 44, y + 22), when, font=sfont(24), fill=(170, 170, 178), anchor='ra')
    d.text((122, y + 64), fit(body, sfont(30, 'Semibold'), PW - 170), font=sfont(30, 'Semibold'), fill=(250, 250, 250))


def draw_notifs(d, t, top, max_n):
    shown = [n for n in NOTIFS if n[0] <= t][-max_n:]
    for i, (tn, app, who, msg) in enumerate(reversed(shown)):
        slide = min(1.0, (t - tn) / 0.18)
        y = top + i * 148 - int((1 - slide) * 60)
        d.rounded_rectangle([24, y, PW - 24, y + 136], 30, fill=(56, 56, 64))
        d.rounded_rectangle([44, y + 22, 104, y + 82], 14, fill=(60, 200, 90))
        d.text((122, y + 18), who, font=sfont(30, 'Semibold'), fill=(250, 250, 250))
        d.text((PW - 44, y + 22), 'now', font=sfont(24), fill=(170, 170, 178), anchor='ra')
        d.text((122, y + 64), fit(msg, sfont(28), PW - 170), font=sfont(28), fill=(225, 225, 230))


# ================================================================ output
LIN = np.where(np.arange(256) / 255.0 <= 0.04045, np.arange(256) / 255.0 / 12.92,
               ((np.arange(256) / 255.0 + 0.055) / 1.055) ** 2.4).astype(np.float32)


def avg_linear(arr):
    sub = arr[::6, ::6]
    return [round(float(LIN[sub[..., c]].mean()), 5) for c in range(3)]


def frame_of(name, t):
    if name == 'phone':
        return np.asarray(phone_frame(t))
    return render_mon(int(name[3:]), t)


def encode_job(name):
    w, h = (PW, PH) if name == 'phone' else (W, H)
    path = os.path.join(OUT, name + '.mp4')
    tmp = path + '.part.mp4'
    cmd = [FFMPEG, '-y', '-v', 'error', '-f', 'rawvideo', '-pix_fmt', 'rgb24', '-s', '%dx%d' % (w, h), '-r', str(FPS),
           '-i', '-', '-c:v', 'libx264', '-preset', 'medium', '-crf', '17', '-threads', '2',
           '-vf', 'scale=out_color_matrix=bt709:out_range=tv', '-pix_fmt', 'yuv420p',
           '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709',
           '-movflags', '+faststart', tmp]
    p = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    light = []
    for f in range(NF):
        arr = frame_of(name, f / FPS)
        light.append(avg_linear(arr))
        p.stdin.write(arr.tobytes())
        if f % 600 == 0:
            print(name, f, flush=True)
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError('ffmpeg failed for ' + name)
    os.replace(tmp, path)
    return name, light


PREVIEW_T = [20.0, 32.4, 38.9, 42.5, 45.6, 56.0, 60.3, 64.0, 70.5, 73.5, 76.8, 88.0, 92.5, 100.5, 105.0, 110.9,
             116.0, 120.6, 122.6, 134.5, 140.5, 145.8, 150.3, 156.8, 162.0, 168.5, 175.0, 190.5, 195.5, 201.0, 209.0, 216.0]


def preview(names):
    tw, th = 480, 270
    sheets = []
    for name in names:
        ts = PREVIEW_T
        cols = 8
        rows = math.ceil(len(ts) / cols)
        sheet = Image.new('RGB', (cols * tw, rows * (th + 24)), (40, 40, 40))
        d = ImageDraw.Draw(sheet)
        for i, t in enumerate(ts):
            arr = frame_of(name, t)
            im = Image.fromarray(arr)
            im = im.resize((tw, th) if name != 'phone' else (int(th * PW / PH), th), Image.LANCZOS)
            x, y = (i % cols) * tw, (i // cols) * (th + 24)
            sheet.paste(im, (x, y + 24))
            d.text((x + 6, y + 4), '%s  %.1fs' % (name, t), font=tfont(16).f, fill=(255, 255, 255))
        sheets.append(sheet)
        if SCRATCH:     # full-size per-screen sheets for close inspection
            sheet.save(os.path.join(SCRATCH, 'sheet_%s.png' % name))
    if len(sheets) > 1:
        big = Image.new('RGB', (sheets[0].width, sum(s.height for s in sheets)))
        y = 0
        for s in sheets:
            big.paste(s, (0, y)); y += s.height
        big.thumbnail((3840, 6000))
        big.save(os.path.join(OUT, 'preview_contact.png'))


SCRATCH = os.environ.get('SCREENS_SCRATCH')

if __name__ == '__main__':
    os.makedirs(OUT, exist_ok=True)
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'preview'
    a = analyze()
    init_worker(a)
    print('beat period %.4f s, phase %.3f s, %d kicks, %d snares, end %.2f s' %
          (a['period'], a['phase'], len(a['kicks']), len(a['snares']), a['t_end']), flush=True)
    if cmd == 'preview':
        preview(sys.argv[2:] or NAMES)
    elif cmd == 'still':
        Image.fromarray(frame_of(sys.argv[2], float(sys.argv[3]))).save(sys.argv[4])
    elif cmd == 'encode':
        names = sys.argv[2:] or NAMES
        light_path = os.path.join(OUT, 'mon_light.json')
        data = json.load(open(light_path)) if os.path.exists(light_path) else {'fps': FPS, 'frames': NF}
        with Pool(min(4, len(names)), initializer=init_worker, initargs=(a,)) as pool:
            for name, light in pool.imap_unordered(encode_job, names):
                data[name] = light
                with open(light_path + '.part', 'w') as f:
                    json.dump(data, f, separators=(',', ':'))
                os.replace(light_path + '.part', light_path)
                print('done', name, flush=True)
