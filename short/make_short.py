#!/usr/bin/env python3
"""CLAUDAINE: a 19.2 s vertical YouTube Short (1080x1920, 24 fps), cut from the finished clip with ffmpeg only.

The idea it has to sell in a second: Claude is a drug.

Every cut point is in clip seconds (clip timeline == song timeline, see docs/SPEC.md), and every crop is a fraction
of the source frame, so the same edit re-cuts from any render of the clip at any resolution:

    python3 make_short.py --src ../renders/<new 4K render>.mp4

Loop: the Short is 461 frames = 19.2083 s (32 beats at 0.6 s, rounded up to a whole frame).
  * Audio = song [A0, A0 + 19.2083 s): chorus 1 from the "Clau-DAINE!" pickup (stop-time) up to just before
    the tag "CLAUDAINE!" that ends the chorus, so on the wrap the opening "Clau-DAINE!" takes the tag's place.
    The last XFADE seconds of the file are a 100 ms equal-power crossfade into song [A0 - XFADE, A0), i.e. the
    audio that precedes the first sample of the file, so the waveform runs on continuously when a player wraps.
  * Picture: the Short ends on the push-in on the mummy's face (glasses full of code) and starts on the same
    camera move 9 frames later, when the Claude logos ignite in his glasses. Same crop at both ends, so the
    loop reads as a match cut on the face rather than as a restart.

Writes <out>.mp4, contact.jpg (two frames per piece) and seam.jpg (the two frames on each side of the loop
seam), then checks the spec with ffprobe and measures the loop seam (picture difference and a 2x-concatenation
audio check). Intermediates live in short/_build and are deleted at the end (use --keep-build to keep them).
Needs only ffmpeg/ffprobe and python3 with PIL.
"""
import argparse, array, json, math, os, shutil, statistics, subprocess, sys, time
from PIL import Image, ImageDraw, ImageFilter, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
CLIP = os.path.dirname(HERE)
FFMPEG = os.environ.get('FFMPEG', 'ffmpeg')
FFPROBE = os.environ.get('FFPROBE', 'ffprobe')
THREADS = '4'
DEFAULT_SRC = os.path.join(CLIP, 'renders', 'Claudaine_clip.mp4')
SONG = os.path.join(CLIP, 'Claudaine.mp3')           # fallback if --src has no audio
FONT_T = os.path.join(CLIP, 'assets', 'fonts', 'UnifrakturCook-Bold.ttf')    # title face, as in post.py
FONT_C = '/System/Library/Fonts/Menlo.ttc'                                   # CLI face, as in post.py
ORANGE = (217, 119, 87)                                                      # #D97757

from edit import FPS, OW, OH, SR, NFRAMES, A0, XFADE, BEAT0, BEAT, PIECES, TITLE, CLI, crop_centre   # the edit
sys.path.append(os.path.join(CLIP, 'scripts'))
from look import rgb, flash, slices                                          # the clip's glitch timing


def run(cmd, **kw):
    r = subprocess.run(cmd, **kw)
    if r.returncode:
        sys.exit(f'command failed ({r.returncode}): ' + ' '.join(cmd))
    return r


def probe(path):
    out = run([FFPROBE, '-v', 'error', '-print_format', 'json', '-show_streams', '-show_format', path],
              capture_output=True, text=True).stdout
    return json.loads(out)


def frac(s):
    a, b = s.split('/')
    return float(a) / float(b) if float(b) else 0.0


# ---------------------------------------------------------------- pieces

def lerp_expr(keys):
    """Piecewise-linear expression of the frame number n through [(n_k, v_k)], held outside the range."""
    expr = f'{keys[-1][1]:.5f}'
    for (n0, v0), (n1, v1) in reversed(list(zip(keys, keys[1:]))):
        seg = f'{v1:.5f}' if n1 - n0 < 1e-6 else f'({v0:.5f}+({v1 - v0:.5f})*(n-{n0:.3f})/{n1 - n0:.3f})'
        expr = f'if(lt(n,{n1:.3f}),{seg},{expr})'
    return f'if(lt(n,{keys[0][0]:.3f}),{keys[0][1]:.5f},{expr})'


def piece_filter(p, W, H, src_fps):
    z = p.get('z', 1.0)
    ch = min(H, int(round(H / z / 2)) * 2)
    cw = min(W, int(round(ch * OW / OH / 2)) * 2)
    y = max(0, min(H - ch, int(round(p.get('cy', 0.5) * H - ch / 2))))
    keys = [((t - p['src']) * FPS, cx) for t, cx in p['keys']]
    x = f"clip(({lerp_expr(keys)})*{W}-{cw / 2:.1f},0,{W - cw})"
    vf = [] if abs(src_fps - FPS) < 1e-3 else [f'fps={FPS}']
    vf += [f"crop=w={cw}:h={ch}:x='{x}':y={y}", f'scale={OW}:{OH}:flags=lanczos', 'setsar=1']
    if p.get('eq'):
        vf.append('eq=' + p['eq'])
    vf.append('format=yuv420p')
    return ','.join(vf), (cw, ch, y)


def render_piece(p, k, src, W, H, src_fps, build):
    out = os.path.join(build, f'p_{k:02d}.mp4')
    vf, geo = piece_filter(p, W, H, src_fps)
    ss = max(0.0, p['src'] - 0.5 / src_fps)      # input seek is frame-accurate when transcoding
    run([FFMPEG, '-v', 'error', '-y', '-threads', THREADS, '-ss', f'{ss:.4f}', '-i', src, '-an', '-sn', '-dn',
         '-vf', vf, '-frames:v', str(p['n']), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '10',
         '-pix_fmt', 'yuv420p', '-r', str(FPS), '-threads', THREADS, out])
    got = int(probe_frames(out))
    if got != p['n']:
        sys.exit(f"piece {p['id']}: got {got} frames, wanted {p['n']} (source too short?)")
    return out, geo


def look_filter(p):
    """Filter graph for piece p rendered in 9:16 (render_short_src.py): the clip's look, which a crop of the clip
    came with baked in. post.py's glitches that fall inside the piece, moved to its own clock and scaled to the
    crop (output px per px of the 1080p clip), then its grain and its vignette as it showed inside the crop."""
    t0, t1 = p['src'], p['src'] + p['n'] / FPS
    s = OH * p.get('z', 1.0) / 1080
    _, y, _, h = crop_centre(p, 0)

    def win(spans):
        return '+'.join(f'between(t,{max(a, t0) - t0:.3f},{min(b, t1) - t0:.3f})' for a, b in spans
                        if a < t1 and b > t0)

    vf = [f'scale={OW}:{OH}:flags=lanczos', 'setsar=1'] + (['eq=' + p['eq']] if p.get('eq') else [])
    if win(rgb):
        vf.append(f"rgbashift=rh={-round(9 * s)}:bh={round(9 * s)}:rv={round(2 * s)}:bv={-round(2 * s)}"
                  f":enable='{win(rgb)}'")
    if win(flash):
        vf.append(f"eq=brightness=0.35:contrast=1.4:saturation=0.6:enable='{win(flash)}'")
    g = '[0:v]' + ','.join(vf)
    if win(slices):
        b1, b2 = ((row - (y - h / 2)) / h for row in (0.31, 0.64))          # post.py's bands, in this crop
        g += (f",split=3[a][b][c];[b]crop=iw:ih*{0.09 / h:.4f}:0:ih*{b1:.4f},hue=h=20[b1];"
              f"[c]crop=iw:ih*{0.05 / h:.4f}:0:ih*{b2:.4f}[c1];"
              f"[a][b1]overlay=x='{-60 * s:.0f}+{40 * s:.0f}*sin(n*7)':y=H*{b1:.4f}:enable='{win(slices)}'[ab];"
              f"[ab][c1]overlay=x='{90 * s:.0f}*sin(n*13)':y=H*{b2:.4f}:enable='{win(slices)}'")
    return g + ',noise=alls=7:allf=t,vignette=angle=PI/8,format=yuv420p[v]'


def frame_piece(p, k, frames, build):
    out = os.path.join(build, f'p_{k:02d}.mp4')
    have = len([f for f in os.listdir(os.path.join(frames, p['id'])) if f.endswith('.png')])
    if have < p['n']:
        sys.exit(f"piece {p['id']}: {have} of {p['n']} frames rendered in {frames}")
    run([FFMPEG, '-v', 'error', '-y', '-threads', THREADS, '-framerate', str(FPS),
         '-i', os.path.join(frames, p['id'], 'f_%03d.png'), '-filter_complex', look_filter(p), '-map', '[v]',
         '-frames:v', str(p['n']), '-c:v', 'libx264', '-preset', 'veryfast', '-crf', '10', '-pix_fmt', 'yuv420p',
         '-r', str(FPS), '-threads', THREADS, out])
    got = int(probe_frames(out))
    if got != p['n']:
        sys.exit(f"piece {p['id']}: got {got} frames, wanted {p['n']}")
    return out


def probe_frames(path):
    out = run([FFPROBE, '-v', 'error', '-select_streams', 'v:0', '-count_packets', '-show_entries',
               'stream=nb_read_packets', '-of', 'csv=p=0', path], capture_output=True, text=True).stdout
    return out.strip()


# ---------------------------------------------------------------- text

def title_png(path):
    im = Image.new('RGBA', (OW, OH), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    size = 200
    while True:
        ft = ImageFont.truetype(FONT_T, size)
        bb = d.textbbox((0, 0), TITLE['text'], font=ft)
        if bb[2] - bb[0] <= OW * 0.84 or size < 60:
            break
        size -= 4
    tx = (OW - (bb[2] - bb[0])) // 2 - bb[0]
    ty = int(OH * 0.135) - (bb[3] - bb[1]) // 2 - bb[1]
    shadow = Image.new('RGBA', (OW, OH), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).text((tx, ty + 6), TITLE['text'], font=ft, fill=(0, 0, 0, 200))
    shadow = shadow.filter(ImageFilter.GaussianBlur(10))
    d.text((tx, ty), TITLE['text'], font=ft, fill=ORANGE + (255,))
    glow = im.filter(ImageFilter.GaussianBlur(16))
    out = Image.alpha_composite(Image.alpha_composite(shadow, glow), im)
    out.save(path)


def cli_frames(build):
    fc = ImageFont.truetype(FONT_C, CLI['size'])
    cw = fc.getlength('M')
    full = CLI['prompt'] + CLI['text']
    x0 = int((OW - cw * (len(full) + 1)) / 2)
    y0 = int(OH * 0.655)
    paths = []
    for k in range(CLI['f1'] - CLI['f0']):
        t = k / FPS
        n = min(len(CLI['text']), int(t * CLI['cps']) + 1)
        im = Image.new('RGBA', (OW, OH), (0, 0, 0, 0))
        sh = Image.new('RGBA', (OW, OH), (0, 0, 0, 0))
        ds = ImageDraw.Draw(sh)
        ds.rectangle((x0 - 24, y0 - 18, x0 + cw * (len(full) + 1) + 24, y0 + CLI['size'] * 1.4), fill=(0, 0, 0, 120))
        sh = sh.filter(ImageFilter.GaussianBlur(14))
        d = ImageDraw.Draw(im)
        d.text((x0, y0), CLI['prompt'], font=fc, fill=ORANGE + (255,))
        d.text((x0 + cw * len(CLI['prompt']), y0), CLI['text'][:n], font=fc, fill=(232, 232, 232, 255))
        done = len(CLI['text']) / CLI['cps']
        if t < done or (t - done) % 0.6 < 0.3:            # cursor blinks on the beat once typed
            cx = x0 + cw * (len(CLI['prompt']) + n)
            d.rectangle((cx + 4, y0 + 2, cx + cw, y0 + int(CLI['size'] * 1.15)), fill=(232, 232, 232, 230))
        p = os.path.join(build, f'cli_{k:03d}.png')
        Image.alpha_composite(sh, im).save(p)
        paths.append(p)
    return os.path.join(build, 'cli_%03d.png')


# ---------------------------------------------------------------- final

def encode(pieces, build, song_wav, out, crf):
    lst = os.path.join(build, 'pieces.txt')
    with open(lst, 'w') as f:
        f.writelines(f"file '{p}'\n" for p in pieces)
    title = os.path.join(build, 'title.png')
    title_png(title)
    cli = cli_frames(build)
    a = int(round(A0 * SR))
    L = NFRAMES * SR // FPS
    x = int(round(XFADE * SR))
    fc = (
        f"[1:v]format=rgba[tt];[0:v][tt]overlay=0:0:eof_action=pass[v1];"
        f"[2:v]format=rgba,setpts=PTS+{CLI['f0']}/{FPS}/TB[cc];[v1][cc]overlay=0:0:eof_action=pass,"
        f"format=yuv420p[v];"
        f"[3:a]asplit=2[s1][s2];"
        f"[s1]atrim=start_sample={a}:end_sample={a + L},asetpts=PTS-STARTPTS[m];"
        f"[s2]atrim=start_sample={a - x}:end_sample={a},asetpts=PTS-STARTPTS[p];"
        f"[m][p]acrossfade=ns={x}:c1=qsin:c2=qsin[aout]"
    )
    run([FFMPEG, '-v', 'error', '-y', '-threads', THREADS,
         '-f', 'concat', '-safe', '0', '-i', lst,
         '-loop', '1', '-framerate', str(FPS), '-t', f'{(TITLE["f1"] - TITLE["f0"]) / FPS:.6f}', '-i', title,
         '-framerate', str(FPS), '-i', cli,
         '-i', song_wav,
         '-filter_complex', fc, '-map', '[v]', '-map', '[aout]',
         '-c:v', 'libx264', '-preset', 'slow', '-crf', str(crf), '-pix_fmt', 'yuv420p', '-r', str(FPS),
         '-profile:v', 'high', '-c:a', 'aac', '-b:a', '256k', '-ar', str(SR), '-ac', '2',
         '-movflags', '+faststart', '-threads', THREADS, out])


# ---------------------------------------------------------------- previews

def grab(path, frames, size, build, tag):
    """Frames by output frame number, returned in the order asked (select emits them in stream order)."""
    uniq = sorted(set(frames))
    sel = '+'.join(f'eq(n\\,{f})' for f in uniq)
    pat = os.path.join(build, f'{tag}_%03d.png')
    run([FFMPEG, '-v', 'error', '-y', '-threads', THREADS, '-i', path, '-vf',
         f"select='{sel}',scale={size[0]}:{size[1]}:flags=lanczos", '-fps_mode', 'passthrough', '-an', pat])
    ims = {f: Image.open(pat % (k + 1)).convert('RGB') for k, f in enumerate(uniq)}
    return [ims[f] for f in frames]


def contact_sheet(out_mp4, starts, build, path):
    tw, th, band, cols = 216, 384, 40, 6
    frames, labels = [], []
    for p, f0 in zip(PIECES, starts):
        for q in (0.2, 0.8):
            k = min(p['n'] - 1, int(p['n'] * q))
            frames.append(f0 + k)
            labels.append((f"{p['id']} {(f0 + k) / FPS:5.2f}s", f"src {p['src'] + k / FPS:7.3f}"))
    tiles = grab(out_mp4, frames, (tw, th), build, 'cs')
    rows = (len(tiles) + cols - 1) // cols
    sheet = Image.new('RGB', (cols * tw, rows * (th + band)), (12, 12, 12))
    d = ImageDraw.Draw(sheet)
    fl = ImageFont.truetype(FONT_C, 15)
    for i, (im, (l1, l2)) in enumerate(zip(tiles, labels)):
        x, y = (i % cols) * tw, (i // cols) * (th + band)
        sheet.paste(im, (x, y))
        d.text((x + 6, y + th + 3), l1, font=fl, fill=ORANGE)
        d.text((x + 6, y + th + 20), l2, font=fl, fill=(200, 200, 200))
    sheet.save(path, quality=88)


def seam_preview(out_mp4, build, path):
    tw, th = 270, 480
    ims = grab(out_mp4, [NFRAMES - 2, NFRAMES - 1, 0, 1], (tw, th), build, 'sm')
    fl = ImageFont.truetype(FONT_C, 16)
    sheet = Image.new('RGB', (4 * tw + 12, th + 28), (12, 12, 12))
    d = ImageDraw.Draw(sheet)
    for i, (im, lab) in enumerate(zip(ims, [f'last-1 (f{NFRAMES - 2})', f'last (f{NFRAMES - 1})',
                                            'first (f0)', 'f1'])):
        x = i * tw + (12 if i >= 2 else 0)
        sheet.paste(im, (x, 0))
        d.text((x + 6, th + 5), lab, font=fl, fill=ORANGE if i in (1, 2) else (200, 200, 200))
    d.rectangle((2 * tw + 2, 0, 2 * tw + 9, th), fill=ORANGE)
    sheet.save(path, quality=88)


# ---------------------------------------------------------------- checks

def faststart(path):
    order = []
    with open(path, 'rb') as f:
        while True:
            h = f.read(8)
            if len(h) < 8:
                break
            size, typ = int.from_bytes(h[:4], 'big'), h[4:8].decode('latin1')
            hdr = 8
            if size == 1:
                size, hdr = int.from_bytes(f.read(8), 'big'), 16
            elif size == 0:
                order.append(typ)
                break
            order.append(typ)
            f.seek(size - hdr, 1)
    return order


def pcm(path, build=None, loops=1):
    """Decoded audio. loops=2 plays the file twice through the concat demuxer, which honours the AAC
    priming/edit list on each pass like a gapless player. (-stream_loop does not: it re-primes the decoder
    and leaves ~5 ms of digital silence at the wrap, which is ffmpeg's artifact, not the file's.)"""
    cmd = [FFMPEG, '-v', 'error', '-threads', THREADS]
    if loops > 1:
        lst = os.path.join(build, 'loop.txt')
        with open(lst, 'w') as f:
            f.writelines(f"file '{os.path.abspath(path)}'\n" for _ in range(loops))
        cmd += ['-f', 'concat', '-safe', '0', '-i', lst]
    else:
        cmd += ['-i', path]
    cmd += ['-vn', '-f', 's16le', '-ac', '2', '-ar', str(SR), '-']
    a = array.array('h')
    a.frombytes(run(cmd, capture_output=True).stdout)
    return a


def db(v):
    return 20 * math.log10(max(v, 1e-9) / 32768.0)


def rms(a, i0, i1):
    s, n = 0.0, 0
    for i in range(max(0, i0), min(len(a) // 2, i1)):
        m = (a[2 * i] + a[2 * i + 1]) * 0.5
        s += m * m
        n += 1
    return math.sqrt(s / max(n, 1))


def check(out_mp4, starts, build):
    ok = True
    info = probe(out_mp4)
    v = next(s for s in info['streams'] if s['codec_type'] == 'video')
    a = next(s for s in info['streams'] if s['codec_type'] == 'audio')
    nfr = int(probe_frames(out_mp4))
    spec = [
        ('video codec h264', v['codec_name'] == 'h264', v['codec_name']),
        ('1080x1920', (v['width'], v['height']) == (OW, OH), f"{v['width']}x{v['height']}"),
        ('yuv420p', v['pix_fmt'] == 'yuv420p', v['pix_fmt']),
        ('24 fps', abs(frac(v['r_frame_rate']) - FPS) < 1e-6, v['r_frame_rate']),
        (f'{NFRAMES} frames', nfr == NFRAMES, nfr),
        ('audio aac', a['codec_name'] == 'aac', a['codec_name']),
        ('48 kHz stereo', (int(a['sample_rate']), a['channels']) == (SR, 2), f"{a['sample_rate']} / {a['channels']}ch"),
        ('duration ~19.2 s', 19.0 < float(info['format']['duration']) < 19.5, info['format']['duration']),
    ]
    atoms = faststart(out_mp4)
    spec.append(('+faststart (moov before mdat)', atoms.index('moov') < atoms.index('mdat'), ' '.join(atoms)))
    print('\nSPEC (ffprobe)')
    for name, good, val in spec:
        ok &= good
        print(f"  {'ok ' if good else 'BAD'}  {name:32s} {val}")
    print(f"  ..   video duration {v.get('duration')} s, audio duration {a.get('duration')} s")

    # picture: difference across the wrap vs inside shots and at hard cuts (90x160 grey)
    raw = run([FFMPEG, '-v', 'error', '-threads', THREADS, '-i', out_mp4, '-vf', 'scale=90:160,format=gray',
               '-f', 'rawvideo', '-'], capture_output=True).stdout
    fs = 90 * 160
    fr = [raw[i * fs:(i + 1) * fs] for i in range(len(raw) // fs)]
    mad = lambda p, q: sum(abs(x - y) for x, y in zip(p, q)) / fs
    cuts = set(starts[1:])
    inshot = [mad(fr[k - 1], fr[k]) for k in range(1, len(fr)) if k not in cuts]
    atcut = [mad(fr[k - 1], fr[k]) for k in sorted(cuts)]
    seam = mad(fr[-1], fr[0])
    print('\nLOOP SEAM, picture (mean abs luma difference, 0..255, at 90x160)')
    print(f'  last -> first frame: {seam:.1f}   | inside shots: median {statistics.median(inshot):.1f}, '
          f'p95 {sorted(inshot)[int(0.95 * len(inshot))]:.1f}   | at the {len(atcut)} hard cuts: median '
          f'{statistics.median(atcut):.1f}')
    luma = lambda p: sum(p) / fs
    print(f'  mean luma: last frame {luma(fr[-1]):.1f}, first frame {luma(fr[0]):.1f}')

    # audio: decode the file looped twice (a real 2x concatenation through the decoder) and look at the seam
    one = pcm(out_mp4)
    two = pcm(out_mp4, build, loops=2)
    N1, N2 = len(one) // 2, len(two) // 2
    print('\nLOOP SEAM, audio')
    print(f'  samples: single {N1} (video {NFRAMES * SR // FPS}), 2x concatenation {N2}')
    if N2 != 2 * N1:
        print('  note: 2x decode length is not exactly twice the single decode')
    seam_i = N1
    steps = []
    for ch in (0, 1):
        d = sorted(abs(one[2 * i + ch] - one[2 * (i - 1) + ch]) for i in range(1, N1))
        steps.append((abs(two[2 * seam_i + ch] - two[2 * (seam_i - 1) + ch]), d[int(0.5 * len(d))],
                      d[int(0.999 * len(d))], d[-1]))
    for ch, (j, med, p999, mx) in zip('LR', steps):
        good = j <= p999
        ok &= good
        print(f"  {'ok ' if good else 'BAD'}  sample step across the seam, {ch}: {j}  (file: median {med}, "
              f"99.9% {p999}, max {mx})")
    win = SR // 100                    # 10 ms windows
    lv = [db(rms(one, i, i + win)) for i in range(0, N1 - win, win)]
    jumps = sorted(abs(b - a_) for a_, b in zip(lv, lv[1:]))
    p99 = jumps[int(0.99 * len(jumps))]
    around = [(k, db(rms(two, seam_i + k * win, seam_i + (k + 1) * win))) for k in range(-12, 12)]
    print('  10 ms RMS (dBFS) around the seam in the 2x file, window start relative to the seam:')
    print('   ' + '  '.join(f'{k * 10:+4d}ms {v_:5.1f}' for k, v_ in around[:12]))
    print('   ' + '  '.join(f'{k * 10:+4d}ms {v_:5.1f}' for k, v_ in around[12:]))
    sj = max(abs(around[i + 1][1] - around[i][1]) for i in range(9, 13))
    good = sj <= p99
    ok &= good
    print(f"  {'ok ' if good else 'BAD'}  largest 10 ms level step at the seam {sj:.1f} dB "
          f"(file: 99% of steps <= {p99:.1f} dB)")
    pre, post = db(rms(two, seam_i - SR // 4, seam_i)), db(rms(two, seam_i, seam_i + SR // 4))
    print(f'  ..   250 ms before / after the seam: {pre:.1f} / {post:.1f} dBFS (end of "Opus in my veins" with '
          f'drums -> stop-time "Clau-DAINE!")')
    print('\nall checks passed' if ok else '\nSOME CHECKS FAILED')
    return ok


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--src', default=DEFAULT_SRC, help='render of the clip (any resolution, clip timeline)')
    ap.add_argument('--frames', default=None, help='instead of cropping --src: the shots rendered in 9:16 by '
                                                   'render_short_src.py (<dir>/<piece id>/f_###.png)')
    ap.add_argument('--audio', default=None, help='audio on the clip timeline (default: the --src audio, or '
                                                  'Claudaine.mp3 if --src has none)')
    ap.add_argument('--out', default=os.path.join(HERE, 'Claudaine_short.mp4'))
    ap.add_argument('--contact', default=os.path.join(HERE, 'contact.jpg'))
    ap.add_argument('--seam', default=os.path.join(HERE, 'seam.jpg'))
    ap.add_argument('--crf', type=int, default=16)
    ap.add_argument('--no-check', action='store_true')
    ap.add_argument('--keep-build', action='store_true')
    args = ap.parse_args()
    t0 = time.time()

    assert sum(p['n'] for p in PIECES) == NFRAMES, 'pieces must add up to NFRAMES'
    if args.frames:
        info = {'streams': []}
        print(f'source {args.frames} (shots rendered in 9:16)')
    else:
        info = probe(args.src)
        v = next(s for s in info['streams'] if s['codec_type'] == 'video')
        W, H, src_fps = int(v['width']), int(v['height']), frac(v['r_frame_rate'])
        dur = float(info['format']['duration'])
        need = max(p['src'] + p['n'] / FPS for p in PIECES)
        if dur < need or dur < A0 + NFRAMES / FPS:
            sys.exit(f'{args.src}: {dur:.2f} s is shorter than the edit needs ({need:.2f} s)')
        print(f'source {args.src}\n  {W}x{H} @ {src_fps:g} fps, {dur:.2f} s')

    build = os.path.join(HERE, '_build')
    shutil.rmtree(build, ignore_errors=True)
    os.makedirs(build)
    song = os.path.join(build, 'song.wav')
    audio = args.audio
    if not audio:
        audio = args.src if any(s['codec_type'] == 'audio' for s in info['streams']) else SONG
    print(f'  audio from {audio}')
    run([FFMPEG, '-v', 'error', '-y', '-threads', THREADS, '-i', audio, '-vn', '-t', '90',
         '-ac', '2', '-ar', str(SR), '-c:a', 'pcm_s16le', song])

    print('\n  #  out frames    out seconds      source seconds      crop (src px)        piece')
    paths, starts, f = [], [], 0
    for k, p in enumerate(PIECES):
        cx = ', '.join(f'{c:.3f}' for _, c in p['keys'])
        if args.frames:
            path, geo = frame_piece(p, k, args.frames, build), f"9:16 z{p.get('z', 1.0):.2f} x@[{cx}]"
        else:
            path, (cw, ch, y) = render_piece(p, k, args.src, W, H, src_fps, build)
            geo = f'{cw}x{ch}+y{y} x@[{cx}]'
        paths.append(path)
        starts.append(f)
        print(f"  {p['id']}  {f:3d}-{f + p['n'] - 1:3d}   {f / FPS:6.3f}-{(f + p['n']) / FPS:6.3f}   "
              f"{p['src']:8.3f}-{p['src'] + p['n'] / FPS:8.3f}   {geo}  {p['name']}")
        f += p['n']

    encode(paths, build, song, args.out, args.crf)
    contact_sheet(args.out, starts, build, args.contact)
    seam_preview(args.out, build, args.seam)
    print(f'\nwrote {args.out}\n      {args.contact}\n      {args.seam}')
    ok = True if args.no_check else check(args.out, starts, build)
    if not args.keep_build:
        shutil.rmtree(build, ignore_errors=True)
    print(f'\ndone in {time.time() - t0:.0f} s')
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
