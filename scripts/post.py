"""Final pass over the rendered frames with ffmpeg: RGB-split glitches and white flashes on the hits,
glitch slices, film grain, vignette, black + title card after the last kick, then the song.
The title card is drawn with PIL (this ffmpeg build has no drawtext) and overlaid.
Run: python3 scripts/post.py [frames_dir] [out.mp4]"""
import os, subprocess, sys
from PIL import Image, ImageDraw, ImageFilter, ImageFont
from look import rgb, flash, slices      # glitch timing, shared with the Short

CLIP = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
FFMPEG = os.environ.get('FFMPEG', 'ffmpeg')
FRAMES = sys.argv[1] if len(sys.argv) > 1 else os.path.join(CLIP, 'renders', 'frames')
OUT = sys.argv[2] if len(sys.argv) > 2 else os.path.join(CLIP, 'renders', 'Claudaine_clip.mp4')
EXT = 'jpg' if os.path.exists(os.path.join(FRAMES, 'f_0001.jpg')) else 'png'
W, H = Image.open(os.path.join(FRAMES, f'f_0001.{EXT}')).size
S = H / 1080                  # everything below is laid out for 1080p and scaled to the frames' size
TITLE_DIR = os.path.join(CLIP, 'renders', 'title' if H == 1080 else f'title_{H}p')
SONG = os.path.join(CLIP, 'Claudaine.mp3')
FONT_T = os.path.join(CLIP, 'assets', 'fonts', 'UnifrakturCook-Bold.ttf')
FONT_C = '/System/Library/Fonts/Menlo.ttc'
FPS, NFRAMES = 24, 5254
END = 214.24                  # the last kick: hard black, then the title card

TITLE_IN = END + 0.6
CLI_IN = END + 1.6
CLI = 'Your limit will reset at 3 A.M.'
TYPE_CPS = 22.0


def win(spans):
    return '+'.join(f'between(t,{a:.3f},{b:.3f})' for a, b in spans)


def title_frames():
    """RGBA frames from END to the last frame: blood-orange blackletter title, then the CLI line typed out."""
    os.makedirs(TITLE_DIR, exist_ok=True)
    ft, fc = ImageFont.truetype(FONT_T, round(200 * S)), ImageFont.truetype(FONT_C, round(38 * S))
    base = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(base)
    bb = d.textbbox((0, 0), 'Claudaine', font=ft)
    tx, ty = (W - (bb[2] - bb[0])) // 2 - bb[0], H // 2 - round(60 * S) - (bb[3] - bb[1]) // 2 - bb[1]
    d.text((tx, ty), 'Claudaine', font=ft, fill=(217, 119, 87, 255))
    glow = base.filter(ImageFilter.GaussianBlur(18 * S))
    title = Image.alpha_composite(glow, base)
    cw = fc.getlength('M')
    cx, cy = int((W - cw * (len(CLI) + 2)) / 2), H // 2 + round(110 * S)
    f0 = int(round(END * FPS))
    for k, f in enumerate(range(f0, NFRAMES)):
        t = f / FPS
        im = Image.new('RGBA', (W, H), (0, 0, 0, 255))
        if t >= TITLE_IN:
            a = min(1.0, (t - TITLE_IN) / 0.4)
            tt = title.copy()
            tt.putalpha(tt.getchannel('A').point(lambda v: int(v * a)))
            im = Image.alpha_composite(im, tt)
        if t >= CLI_IN:
            n = min(len(CLI), int((t - CLI_IN) * TYPE_CPS))
            dd = ImageDraw.Draw(im)
            dd.text((cx, cy), '> ' + CLI[:n], font=fc, fill=(191, 191, 191, 255))
            done = CLI_IN + len(CLI) / TYPE_CPS
            if t < done or (t - done) % 1.0 < 0.5:
                x = cx + cw * (n + 2)
                dd.rectangle((x, cy - 2 * S, x + cw, cy + 46 * S), fill=(191, 191, 191, 230))
        im.save(os.path.join(TITLE_DIR, f't_{k:04d}.png'))
    return f0


vf = (
    f"[0:v]rgbashift=rh={-round(9 * S)}:bh={round(9 * S)}:rv={round(2 * S)}:bv={-round(2 * S)}:enable='{win(rgb)}',"
    f"eq=brightness=0.35:contrast=1.4:saturation=0.6:enable='{win(flash)}',"
    "split=3[a][b][c];"
    # glitch slices: two bands of the frame jump sideways for a few frames
    f"[b]crop=iw:ih*0.09:0:ih*0.31,hue=h=20[b1];[c]crop=iw:ih*0.05:0:ih*0.64[c1];"
    f"[a][b1]overlay=x='{-60 * S:.0f}+{40 * S:.0f}*sin(n*7)':y=H*0.31:enable='{win(slices)}'[ab];"
    f"[ab][c1]overlay=x='{90 * S:.0f}*sin(n*13)':y=H*0.64:enable='{win(slices)}'[g];"
    f"[1:v]setpts=PTS+{END}/TB[tc];"
    f"[g][tc]overlay=eof_action=pass:enable='gte(t,{END})',"
    "noise=alls=7:allf=t,vignette=angle=PI/4.8[v]"
)
if __name__ == '__main__':
    title_frames()
    cmd = [FFMPEG, '-y', '-framerate', '24', '-i', os.path.join(FRAMES, f'f_%04d.{EXT}'),
           '-framerate', '24', '-i', os.path.join(TITLE_DIR, 't_%04d.png'), '-i', SONG,
           '-filter_complex', vf, '-map', '[v]', '-map', '2:a', '-c:v', 'libx264', '-preset', 'slow', '-crf', '16',
           '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '320k', '-shortest', '-movflags', '+faststart', OUT]
    print(' '.join(cmd))
    subprocess.run(cmd, check=True)
