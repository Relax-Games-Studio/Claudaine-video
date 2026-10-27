"""Cover for the Claudaine Short (1080x1920): the frame where the Claude logos ignite in the mummy's glasses,
lifted and pushed in, with a two-line hook. Run: python3 upload/make_cover.py [variant]"""
import os, sys
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont
HERE = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
IMPACT = '/System/Library/Fonts/Supplemental/Impact.ttf'
BLACK = os.path.join(HERE, '..', 'assets', 'fonts', 'UnifrakturCook-Bold.ttf')
ORANGE = (217, 119, 87)
HOOKS = {'drug': ('CLAUDE IS', 'MY DRUG'), 'opus': ("IT AIN'T OPIUM", "IT'S OPUS")}
W, H = 1080, 1920

src = Image.open(f'{HERE}/frames916/A/f_016.png').convert('RGB')
z = 1.12                                                   # push in on the glasses
cw, ch = W / z, H / z
cx, cy = W * 0.53, H * 0.50
im = src.crop((int(cx - cw / 2), int(cy - ch / 2), int(cx + cw / 2), int(cy + ch / 2))).resize((W, H), Image.LANCZOS)
im = ImageEnhance.Brightness(im).enhance(1.45)
im = ImageEnhance.Contrast(im).enhance(1.18)
glow = im.point(lambda v: max(0, v - 150) * 3).filter(ImageFilter.GaussianBlur(28))   # bloom on the logos
im = ImageChops.add(im, glow)
shade = Image.new('L', (W, H))                              # dark top and bottom for the type
d = ImageDraw.Draw(shade)
for y in range(H):
    a = max(0, 1 - y / 760) * 205 if y < 760 else max(0, (y - 1500) / 420) * 190
    d.line((0, y, W, y), fill=int(a))
im = Image.composite(Image.new('RGB', (W, H)), im, shade)


def line(img, text, font, y, fill, glow_col, stroke=10):
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    dd = ImageDraw.Draw(lay)
    bb = dd.textbbox((0, 0), text, font=font, stroke_width=stroke)
    x = (W - (bb[2] - bb[0])) // 2 - bb[0]
    g = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(g).text((x, y), text, font=font, fill=glow_col + (255,), stroke_width=stroke + 8, stroke_fill=glow_col + (255,))
    g = g.filter(ImageFilter.GaussianBlur(26))
    dd.text((x, y), text, font=font, fill=fill + (255,), stroke_width=stroke, stroke_fill=(10, 6, 4, 255))
    return Image.alpha_composite(Image.alpha_composite(img, g), lay)


def fit(text, size, width):
    while ImageFont.truetype(IMPACT, size).getlength(text) > width:
        size -= 4
    return ImageFont.truetype(IMPACT, size)


v = sys.argv[1] if len(sys.argv) > 1 else 'drug'
l1, l2 = HOOKS[v]
out = im.convert('RGBA')
out = line(out, l1, fit(l1, 230, W * 0.9), 150, (255, 255, 255), (0, 0, 0))
out = line(out, l2, fit(l2, 300, W * 0.92), 400, ORANGE, ORANGE)
bf = ImageFont.truetype(BLACK, 170)
out = line(out, 'Claudaine', bf, 1660, ORANGE, ORANGE, stroke=4)
out.convert('RGB').save(f'{HERE}/upload/cover_{v}.jpg', quality=92)
print('ok', v)
