"""Full-size ANSI layout shared by the legend atlas (gen_keycaps.py, PIL) and the keyboard model (desk.py).
KEYS = [(legend, x, row, w, h)]: x = left edge in key units from the left edge of the key field, row 0 = F row,
1 = number row .. 5 = space row; h > 1 keys grow downwards (numpad + and Enter)."""

import math

U = 0.01905                 # one key unit, metres
ATLAS_COLS, ATLAS_ROWS, CELL = 16, 10, 192
CAP_GAP, CAP_TAPER, CAP_FIL = 0.0013, 0.0016, 0.0006     # cap skirt inset, wall taper, top-edge fillet (m)
LEG_M = U * 0.82            # metres of cap top per atlas cell: every legend keeps one scale
BLANK_UV = (0.995, 0.005)   # an always-empty atlas corner


def _layout():
    keys = []

    def row(r, x, items):
        for it in items:
            lab, w = it if isinstance(it, tuple) else (it, 1.0)
            if lab is not None:
                keys.append((lab, x, r, w, 1.0))
            x += w

    row(0, 0.0, ['Esc', (None, 1.0), 'F1', 'F2', 'F3', 'F4', (None, 0.5), 'F5', 'F6', 'F7', 'F8', (None, 0.5),
                 'F9', 'F10', 'F11', 'F12', (None, 0.25), 'PrtSc', 'ScrLk', 'Pause'])
    row(1, 0.0, ['~\n`', '!\n1', '@\n2', '#\n3', '$\n4', '%\n5', '^\n6', '&\n7', '*\n8', '(\n9', ')\n0', '_\n-', '+\n=',
                 ('Backspace', 2.0), (None, 0.25), 'Ins', 'Home', 'PgUp', (None, 0.25), 'Num', '/', '*', '-'])
    row(2, 0.0, [('Tab', 1.5), 'Q', 'W', 'E', 'R', 'T', 'Y', 'U', 'I', 'O', 'P', '{\n[', '}\n]', ('|\n\\', 1.5),
                 (None, 0.25), 'Del', 'End', 'PgDn', (None, 0.25), '7', '8', '9'])
    row(3, 0.0, [('Caps', 1.75), 'A', 'S', 'D', 'F', 'G', 'H', 'J', 'K', 'L', ':\n;', '"\n\'', ('Enter', 2.25),
                 (None, 3.5), '4', '5', '6'])
    row(4, 0.0, [('Shift', 2.25), 'Z', 'X', 'C', 'V', 'B', 'N', 'M', '<\n,', '>\n.', '?\n/', ('Shift', 2.75),
                 (None, 1.25), '↑', (None, 1.25), '1', '2', '3'])
    row(5, 0.0, [('Ctrl', 1.25), ('Win', 1.25), ('Alt', 1.25), ('', 6.25), ('Alt', 1.25), ('Fn', 1.25),
                 ('Menu', 1.25), ('Ctrl', 1.25), (None, 0.25), '←', '↓', '→', (None, 0.25), ('0', 2.0), '.'])
    keys.append(('+', 21.5, 2, 1.0, 2.0))
    keys.append(('Enter', 21.5, 4, 1.0, 2.0))
    return keys


KEYS = _layout()
WIDTH_U = 22.5
HOME_F = (5.25, 3)          # centre of the F key (x in units, row)


def row_y(r):
    """key-centre y of a row in units, number row = 0 (+y = away from the typist); the F row sits half a unit apart"""
    return -(r - 1) if r >= 1 else 1.5


def _cells():
    """atlas rectangle per key, in cells: (col, row, ncols). A key w units wide gets ceil(w) cells side by side so
    its legend keeps the scale of a 1u key; 2u-tall keys share one cell row (their legend is drawn squashed)."""
    out, cx, cy = [], 0, 0
    for lab, x, r, w, h in KEYS:
        n = math.ceil(w - 1e-6)
        if cx + n > ATLAS_COLS:
            cx, cy = 0, cy + 1
        out.append((cx, cy, n))
        cx += n
    assert cy < ATLAS_ROWS
    return out


CELLS = _cells()


def top_half(w, h):
    """half extents (m) of the top face of a w x h key"""
    return (w * U - CAP_GAP) / 2 - CAP_TAPER - CAP_FIL, (h * U - CAP_GAP) / 2 - CAP_TAPER - CAP_FIL


def top_centre(i):
    """atlas point (cells from the image's top-left) under the centre of key i's top, and the vertical squash
    (2u-tall keys share one cell row, so their legend is drawn at half height)"""
    lab, x, r, w, h = KEYS[i]
    cx, cy, n = CELLS[i]
    return cx + n / 2, cy + 0.5, h


def top_uv(i, x, y):
    """UV (v grows upwards) of the point (x, y) metres from the centre of key i's top, +y away from the typist"""
    if not KEYS[i][0]:
        return BLANK_UV
    ccx, ccy, sq = top_centre(i)
    return (ccx + x / LEG_M) / ATLAS_COLS, 1 - (ccy - y / (LEG_M * sq)) / ATLAS_ROWS
