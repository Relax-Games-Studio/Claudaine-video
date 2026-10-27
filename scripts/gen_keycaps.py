"""Keycap legend atlas for the keyboard: white legends on black, one cell (or a run of cells for wide keys)
per key, laid out as keyboard_layout.CELLS. Run with the system python3 (PIL):
    python3 scripts/gen_keycaps.py   -> assets/keycaps_atlas.png"""
import os, sys
from PIL import Image, ImageDraw, ImageFont
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from keyboard_layout import KEYS, CELLS, ATLAS_COLS, ATLAS_ROWS, CELL, LEG_M, top_half

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'assets', 'keycaps_atlas.png')
SFNS = '/System/Library/Fonts/SFNS.ttf'
SYM = '/System/Library/Fonts/Apple Symbols.ttf'

im = Image.new('L', (ATLAS_COLS * CELL, ATLAS_ROWS * CELL), 0)
big = ImageFont.truetype(SFNS, int(CELL * 0.30))
mid = ImageFont.truetype(SFNS, int(CELL * 0.22))
small = ImageFont.truetype(SFNS, int(CELL * 0.17))
arrows = ImageFont.truetype(SYM, int(CELL * 0.34))
INSET = int(CELL * 0.10)        # legend corner ~1.5 mm in from the edge of the cap's top face


for (lab, x, r, w, h), (cx, cy, n) in zip(KEYS, CELLS):
    if not lab:
        continue
    # the key's own region (n cells wide), drawn unsquashed; 2u-tall keys are squashed into one cell row after
    tw, th = n * CELL, int(CELL * h)
    tile = Image.new('L', (tw, th), 0)
    dr = ImageDraw.Draw(tile)
    hx, hy = top_half(w, h)
    cxp, cyp = tw / 2, th / 2
    lx, ty = cxp - hx / LEG_M * CELL + INSET, cyp - hy / LEG_M * CELL + INSET
    if '\n' in lab:             # shifted symbol over the base one
        top, bot = lab.split('\n')
        dr.text((lx, ty - 4), top, fill=255, font=mid)
        dr.text((lx, cyp + int(CELL * 0.02)), bot, fill=255, font=mid)
    elif lab in '←↑→↓':
        dr.text((cxp, cyp), lab, fill=255, font=arrows, anchor='mm')
    elif len(lab) == 1:
        dr.text((lx, ty - 6), lab, fill=255, font=big)
    else:                       # modifiers / F keys / nav: small word legend, top-left
        dr.text((lx, ty), lab, fill=255, font=small if len(lab) > 3 else mid)
    if h > 1:
        tile = tile.resize((tw, CELL), Image.LANCZOS)
    im.paste(tile, (cx * CELL, cy * CELL))
im.save(OUT)
print('saved', OUT, im.size)
