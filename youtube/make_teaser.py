"""~32 s teaser of the Claudaine clip for X / Reddit (1920x1080, burned-in lyrics for muted autoplay):
  the final chorus from the catheter shot ("CLAUDAINE! ... Twenty was a taste ... Opus in my veins!"), the mummy reveal,
  the Claude logos igniting in the glasses, the last scream, then a hard cut on a beat to the title card.
Source is the graded master renders/Claudaine_clip_4k.mp4, so the grain, flashes and title card are the clip's own.
Timing:
  A0 = 176.875   source second at output t = 0: one frame before beat 294 (176.896), the "Clau" pickup of the final
                 chorus's second "Claudaine!" (found by correlating the vocal-band envelope against chorus 1, whose
                 pickup is beat 98 = 59.296). The shot cut to the catheter is at 177.0, so the first 3 frames hold 177.0.
  CUT = 207.496  beat 345, mid last scream: cut to the title card's last 2 s (216.88-218.88, the scream's tail and
                 "> Your limit will reset at 3 A.M." being typed), audio spliced with a 40 ms crossfade.
Lyric times are the screens' LYRICS table in scripts/gen_screens.py. Run: python3 youtube/make_teaser.py"""
import os
import subprocess
import tempfile

from PIL import Image, ImageDraw, ImageFilter, ImageFont

CLIP = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
SRC = f'{CLIP}/renders/Claudaine_clip_4k.mp4'
OUT = f'{CLIP}/youtube/claudaine_teaser.mp4'
FFMPEG = os.environ.get('FFMPEG', 'ffmpeg')
IMPACT = '/System/Library/Fonts/Supplemental/Impact.ttf'
MONO = '/System/Library/Fonts/Menlo.ttc'
ORANGE = (217, 119, 87)
WHITE = (255, 255, 255)
GREY = (225, 220, 214)
W, H = 1920, 1080

A0, SHOT, CUT = 176.875, 177.0, 207.496
TITLE0, TITLE_LEN = 216.88, 2.0
XF = 0.04
V1 = CUT - A0                 # 30.621 s of the clip
TOTAL = V1 + TITLE_LEN

# (source start, source end, [(text, colour)], style)
LINES = [
    (176.9, 179.9, [('CLAUDAINE!', ORANGE)], 'scream'),
    (179.9, 181.0, [('TWENTY', ORANGE), (' WAS A TASTE', WHITE)], 'sung'),
    (181.0, 182.3, [('A HUNDRED', ORANGE), (' HIT THE VEIN', WHITE)], 'sung'),
    (182.3, 183.3, [('TWO HUNDRED', ORANGE), (' A MONTH', WHITE)], 'sung'),
    (183.3, 184.4, [('JUST TO FEEL THE SAME', WHITE)], 'sung'),
    (184.4, 185.6, [("IT AIN'T OPIUM,", WHITE)], 'sung'),
    (185.6, 186.8, [("IT'S ", WHITE), ('OPUS', ORANGE), (' IN MY VEINS!', WHITE)], 'sung'),
    (186.8, 188.4, [('CLAUDAINE!', ORANGE)], 'scream'),
    (189.7, 193.9, [('> ', ORANGE), ('just one more prompt...', GREY)], 'cli'),
    (194.7, 198.0, [('> ', ORANGE), ('the last one. I swear.', GREY)], 'cli'),
    (198.0, 202.3, [('Your limit has been reset.', GREY)], 'cli'),
    (206.3, CUT, [('CLAUDAINE!', ORANGE)], 'scream'),
]
STYLE = {'sung': (IMPACT, 104, 7), 'scream': (IMPACT, 150, 8), 'cli': (MONO, 66, 4)}   # Menlo Bold (index 1)


def card(parts, font, stroke, y, glow=True):
    """Transparent full frame with the parts centred on one line, top at y; orange parts get a glow."""
    img = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    x = (W - sum(font.getlength(s) for s, _ in parts)) / 2
    glo = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    shadow = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    for s, col in parts:
        ImageDraw.Draw(shadow).text((x, y), s, font=font, fill=(0, 0, 0, 200), stroke_width=stroke + 8, stroke_fill=(0, 0, 0, 200))
        if glow and col == ORANGE:
            ImageDraw.Draw(glo).text((x, y), s, font=font, fill=col + (255,), stroke_width=stroke + 6, stroke_fill=col + (255,))
        ImageDraw.Draw(lay).text((x, y), s, font=font, fill=col + (255,), stroke_width=stroke, stroke_fill=(10, 6, 4, 255))
        x += font.getlength(s)
    img = Image.alpha_composite(img, shadow.filter(ImageFilter.GaussianBlur(14)))
    img = Image.alpha_composite(img, glo.filter(ImageFilter.GaussianBlur(18)))
    return Image.alpha_composite(img, lay)


def main():
    tmp = tempfile.mkdtemp(prefix='teaser_')
    overlays = []   # (png, t0, t1) on the output timeline
    for i, (a, b, parts, style) in enumerate(LINES):
        path, size, stroke = STYLE[style]
        font = ImageFont.truetype(path, size, index=1 if path == MONO else 0)
        y = H - 120 - size * (1.25 if style != 'cli' else 1.6)
        p = f'{tmp}/line{i:02d}.png'
        card(parts, font, stroke, y, glow=style != 'cli').save(p)
        overlays.append((p, max(0.0, a - A0), min(V1, b - A0)))
    tag = card([('MADE 100% BY ', WHITE), ('CLAUDE', ORANGE)], ImageFont.truetype(IMPACT, 64), 5, 44)
    tag.save(f'{tmp}/tag.png')
    overlays.append((f'{tmp}/tag.png', 0.0, 4.2))
    url = card([('full video: ', GREY), ('youtu.be/u99amKAGWsE', ORANGE)], ImageFont.truetype(MONO, 48, index=1), 3, int(H * 0.78), glow=False)
    url.save(f'{tmp}/url.png')
    overlays.append((f'{tmp}/url.png', V1, TOTAL))

    cmd = [FFMPEG, '-v', 'error', '-stats', '-y',
           '-ss', f'{SHOT}', '-t', f'{CUT - SHOT}', '-i', SRC,
           '-ss', f'{TITLE0}', '-t', f'{TITLE_LEN}', '-i', SRC,
           '-ss', f'{A0}', '-t', f'{V1 + XF}', '-i', SRC]
    for p, _, _ in overlays:
        cmd += ['-i', p]
    f = [f'[0:v]scale={W}:{H}:flags=lanczos,setpts=PTS-STARTPTS,tpad=start_mode=clone:start_duration={SHOT - A0}[v1]',
         f'[1:v]scale={W}:{H}:flags=lanczos,setpts=PTS-STARTPTS[v2]',
         '[v1][v2]concat=n=2:v=1:a=0[o0]']
    for k, (_, t0, t1) in enumerate(overlays):
        f.append(f"[o{k}][{k + 3}:v]overlay=0:0:enable='between(t,{t0:.3f},{t1:.3f})'[o{k + 1}]")
    f += ['[2:a]asetpts=PTS-STARTPTS[a1]', '[1:a]asetpts=PTS-STARTPTS[a2]',
          f'[a1][a2]acrossfade=d={XF}:c1=tri:c2=tri,afade=t=in:d=0.01,afade=t=out:st={TOTAL - 0.5:.3f}:d=0.5[aout]']
    cmd += ['-filter_complex', ';'.join(f), '-map', f'[o{len(overlays)}]', '-map', '[aout]',
            '-r', '24', '-c:v', 'libx264', '-preset', 'slow', '-crf', '20', '-maxrate', '6500k', '-bufsize', '13000k',
            '-profile:v', 'high', '-level', '4.1', '-pix_fmt', 'yuv420p', '-g', '48',
            '-c:a', 'aac', '-b:a', '192k', '-ar', '48000', '-movflags', '+faststart', '-t', f'{TOTAL:.3f}', OUT]
    subprocess.run(cmd, check=True)
    for p, _, _ in overlays:
        os.remove(p)
    os.rmdir(tmp)
    print(OUT, f'{os.path.getsize(OUT) / 1e6:.1f} MB')


if __name__ == '__main__':
    main()
