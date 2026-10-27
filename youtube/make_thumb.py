"""YouTube thumbnails for the Claudaine clip (1280x720), three variants for the A/B test:
  drug   - the scream with the Claude logos burning in the glasses (frame 4900) + CLAUDE IS MY DRUG
  limit  - the mummy screaming in profile (frame 4840) + USAGE LIMIT REACHED
  quit   - the crab band on the screens with the $200 bill (frame 1818) + I CAN QUIT ANYTIME
Text is kept to 3-4 words and stays off the face; the gothic title sits bottom left (YouTube puts the duration
badge bottom right). Run: python3 youtube/make_thumb.py"""
import os

from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter, ImageFont

CLIP = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
IMPACT = '/System/Library/Fonts/Supplemental/Impact.ttf'
BLACK = f'{CLIP}/assets/fonts/UnifrakturCook-Bold.ttf'
ORANGE = (217, 119, 87)
RED = (235, 45, 40)
WHITE = (255, 255, 255)
W, H = 1280, 720


def frame(n, z, cx, cy, bright, contrast=1.2, bloom=150):
    src = Image.open(f'{CLIP}/renders/frames_4k/f_{n:04d}.jpg').convert('RGB')
    cw, ch = src.width / z, src.height / z
    cx, cy = src.width * cx, src.height * cy
    im = src.crop((int(cx - cw / 2), int(cy - ch / 2), int(cx + cw / 2), int(cy + ch / 2))).resize((W, H), Image.LANCZOS)
    im = ImageEnhance.Brightness(im).enhance(bright)
    im = ImageEnhance.Contrast(im).enhance(contrast)
    glow = im.point(lambda v: max(0, v - bloom) * 3).filter(ImageFilter.GaussianBlur(18))   # bloom on the lights
    return ImageChops.add(im, glow)


def shade(im, fn):
    """Darken where fn(x, y) -> 0..1 says, to seat the text."""
    m = Image.new('L', (W // 8, H // 8))
    m.putdata([int(255 * fn(x * 8 / W, y * 8 / H)) for y in range(H // 8) for x in range(W // 8)])
    return Image.composite(Image.new('RGB', (W, H)), im, m.resize((W, H), Image.BILINEAR))


def text(img, x, y, s, font, fill, glow_col, stroke):
    g = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(g).text((x, y), s, font=font, fill=glow_col + (255,), stroke_width=stroke + 6, stroke_fill=glow_col + (255,))
    lay = Image.new('RGBA', (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(lay).text((x, y), s, font=font, fill=fill + (255,), stroke_width=stroke, stroke_fill=(10, 6, 4, 255))
    return Image.alpha_composite(Image.alpha_composite(img, g.filter(ImageFilter.GaussianBlur(16))), lay)


def title(img):
    g = ImageFont.truetype(BLACK, 84)
    return text(img, 36, H - 118, 'Claudaine', g, ORANGE, (0, 0, 0), 4)


def save(img, name):
    img.convert('RGB').save(f'{CLIP}/youtube/thumb_{name}.jpg', quality=92)


# drug: hook across the top, face and glasses below
im = shade(frame(4900, 1.15, 0.5, 0.56, 1.55), lambda x, y: max(0, 1 - y * H / 300) * 0.85)
out = im.convert('RGBA')
f = ImageFont.truetype(IMPACT, 150)
a, b = 'CLAUDE IS ', 'MY DRUG'
x0 = (W - f.getlength(a) - f.getlength(b)) / 2
out = text(out, x0, 18, a, f, WHITE, (0, 0, 0), 8)
out = text(out, x0 + f.getlength(a), 18, b, f, ORANGE, ORANGE, 8)
save(title(out), 'drug')

# limit: the screaming face on the right, the alert stacked in the dark on the left
im = shade(frame(4840, 1.3, 0.45, 0.6, 1.9), lambda x, y: max(0, 1 - x / 0.5) * 0.8)
out = im.convert('RGBA')
f = ImageFont.truetype(IMPACT, 148)
for i, (s, col, gl) in enumerate([('USAGE', WHITE, (0, 0, 0)), ('LIMIT', WHITE, (0, 0, 0)), ('REACHED', RED, RED)]):
    out = text(out, 40, 14 + i * 160, s, f, col, gl, 8)
save(title(out), 'limit')

# quit: the $200 screens and the crab band, the lie across the top
im = shade(frame(1818, 1.5, 0.47, 0.5, 1.35, bloom=215), lambda x, y: max(0, 1 - y * H / 230) * 0.85)
out = im.convert('RGBA')
f = ImageFont.truetype(IMPACT, 138)
a, b = 'I CAN QUIT ', 'ANYTIME'
x0 = (W - f.getlength(a) - f.getlength(b)) / 2
out = text(out, x0, 22, a, f, WHITE, (0, 0, 0), 8)
out = text(out, x0 + f.getlength(a), 22, b, f, ORANGE, ORANGE, 8)
save(title(out), 'quit')
print('ok')
