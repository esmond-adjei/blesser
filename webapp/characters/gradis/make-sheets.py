"""Build page-mascot source sheets for Gradis from webapp/public/gradis-mascot.svg.

The SVG artwork is flat two-colour vector art (navy #0F3061 + gold #FAAC2A) with a
transparent face hole holding separate eye / brow / beak shapes, so gaze direction
is a rigid shift of those face features plus a small whole-bust turn. Everything is
derived from one Chrome render of the SVG -- no image model involved.

Regenerate:  python3 make-sheets.py   (from webapp/, needs the SVG + chrome)
Then build:  python3 <skill>/scripts/mascot.py gradis --skip-generate
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
SVG = os.path.join(HERE, '..', '..', 'public', 'gradis-mascot.svg')
BASE_PNG = os.path.join(HERE, 'base-hires.png')

NAVY = (15, 48, 97, 255)
GOLD = (250, 172, 42, 255)
RED = (229, 72, 77, 255)
PINK = (242, 163, 192, 235)
ZBLUE = (127, 168, 215, 255)
SPIRAL = (143, 180, 221, 255)

CELL = 600          # source-sheet cell size; sheets are 1800x1800
BUST_H = 372        # bust height inside a cell
TOP_MARGIN = 100    # cap tip sits this far below the cell top
FACE_DX, FACE_DY = 55, 35   # gaze travel in bust (@2x) px
BODY_DX, BODY_DY = 14, 10
TURN_DEG = 1.5


def render_base():
    if os.path.exists(BASE_PNG):
        return Image.open(BASE_PNG).convert('RGBA')
    import subprocess
    import tempfile
    fd, tmp = tempfile.mkstemp(suffix='.png')
    os.close(fd)
    subprocess.run(['google-chrome', '--headless', '--disable-gpu', '--no-sandbox',
                    '--default-background-color=00000000',
                    '--force-device-scale-factor=2', '--window-size=800,1000',
                    f'--screenshot={tmp}', f'file://{os.path.abspath(SVG)}'],
                   check=True, capture_output=True)
    im = Image.open(tmp).convert('RGBA')
    os.remove(tmp)
    im.save(BASE_PNG)
    return im


def segment(base):
    """Find the movable face features. Returns dict of name -> (mask, bbox)."""
    px = np.array(base).astype(int)
    R, G, B, A = px[:, :, 0], px[:, :, 1], px[:, :, 2], px[:, :, 3]
    op = A > 128
    gold = op & (R > 200) & (G > 140) & (B < 100)
    navy = op & (R < 80) & (G < 110) & (B > 60)

    def blobs(mask):
        lab, n = ndimage.label(mask)
        out = []
        for i in range(1, n + 1):
            ys, xs = np.where(lab == i)
            out.append({'size': len(xs), 'bbox': (xs.min(), ys.min(), xs.max(), ys.max()),
                        'cx': float(xs.mean()), 'cy': float(ys.mean()), 'mask': lab == i})
        return sorted(out, key=lambda b: -b['size'])

    navy_blobs = blobs(navy)
    body = navy_blobs[0]          # main head+torso silhouette
    # Eyes: mid-size navy discs inside the face hole (x 300-1200, y 550-1050)
    eyes = [b for b in navy_blobs[1:]
            if 300 < b['cx'] < 1200 and 550 < b['cy'] < 1050 and b['size'] > 8000]
    assert len(eyes) == 2, f'expected 2 eyes, found {len(eyes)}'
    eyes.sort(key=lambda b: b['cx'])
    # Brows: small navy slashes just above the eyes
    brows = [b for b in navy_blobs[1:]
             if 300 < b['cx'] < 1200 and 450 < b['cy'] < 750 and 1500 < b['size'] < 8000]
    assert len(brows) == 2, f'expected 2 brows, found {len(brows)}'
    brows.sort(key=lambda b: b['cx'])
    # Beak: gold blob in the face hole below the eyes
    gold_blobs = blobs(gold)
    beaks = [b for b in gold_blobs
             if 500 < b['cx'] < 1050 and 750 < b['cy'] < 1100 and b['size'] > 5000]
    assert len(beaks) == 1, f'expected 1 beak, found {len(beaks)}'
    return {'body': body, 'eye_l': eyes[0], 'eye_r': eyes[1],
            'brow_l': brows[0], 'brow_r': brows[1], 'beak': beaks[0]}


def clear_mask(layer, feat):
    a = np.array(layer)
    m = feat['mask']
    a[m] = (0, 0, 0, 0)
    return Image.fromarray(a, 'RGBA')


def stamp(layer, base, feat, dx, dy):
    """Copy a feature's pixels from base to layer, shifted by (dx, dy)."""
    x0, y0, x1, y1 = feat['bbox']
    region = base.crop((x0, y0, x1 + 1, y1 + 1))
    m = feat['mask'][y0:y1 + 1, x0:x1 + 1]
    stamp_img = Image.new('RGBA', region.size, (0, 0, 0, 0))
    stamp_img.paste(region, (0, 0), Image.fromarray((m * 255).astype(np.uint8), 'L'))
    layer.alpha_composite(stamp_img, (round(x0 + dx), round(y0 + dy)))
    return layer


def bust_layer(base, seg, fdx, fdy, turn=0.0, bdx=0.0, bdy=0.0, brow_dy=0.0):
    """Bust with the face shifted by (fdx, fdy) and the whole bust turned."""
    layer = base.copy()
    for name in ('eye_l', 'eye_r', 'brow_l', 'brow_r', 'beak'):
        layer = clear_mask(layer, seg[name])
    for name in ('eye_l', 'eye_r', 'beak'):
        layer = stamp(layer, base, seg[name], fdx, fdy)
    for name in ('brow_l', 'brow_r'):
        layer = stamp(layer, base, seg[name], fdx, fdy + brow_dy)
    if turn or bdx or bdy:
        neck = (seg['eye_l']['cx'] + seg['eye_r']['cx']) / 2, 1250.0
        layer = layer.rotate(turn, resample=Image.BICUBIC, center=neck)
        out = Image.new('RGBA', layer.size, (0, 0, 0, 0))
        out.alpha_composite(layer, (round(bdx), round(bdy)))
        return out
    return layer


# --- overlay drawing helpers (all in cell coordinates) -----------------------

def arc(draw, cx, cy, w, sag, width, fill):
    draw.arc([cx - w / 2, cy - sag, cx + w / 2, cy + sag],
             start=15, end=165, fill=fill, width=width)


def star5(draw, cx, cy, r_out, r_in, fill):
    pts = []
    for i in range(10):
        r = r_out if i % 2 == 0 else r_in
        a = -math.pi / 2 + i * math.pi / 5
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    draw.polygon(pts, fill=fill)


def sparkle(draw, cx, cy, r, fill):
    k = 0.18
    draw.polygon([(cx, cy - r), (cx + r * k, cy - r * k), (cx + r, cy),
                  (cx + r * k, cy + r * k), (cx, cy + r), (cx - r * k, cy + r * k),
                  (cx - r, cy), (cx - r * k, cy - r * k)], fill=fill)


def heart(draw, cx, cy, s, fill):
    r = s * 0.28
    for sx in (-1, 1):
        draw.ellipse([cx + sx * s * 0.26 - r, cy - s * 0.30 - r,
                      cx + sx * s * 0.26 + r, cy - s * 0.30 + r], fill=fill)
    draw.polygon([(cx - s * 0.52, cy - s * 0.02), (cx + s * 0.52, cy - s * 0.02),
                  (cx, cy + s * 0.52)], fill=fill)


def zletter(draw, x, y, w, h, width, fill):
    draw.line([(x, y), (x + w, y), (x, y + h), (x + w, y + h)], fill=fill, width=width)


def spiral(draw, cx, cy, r_max, width, fill):
    pts = []
    th = 0.0
    while th < 6 * math.pi:
        r = 4 + (r_max - 4) * th / (6 * math.pi)
        pts.append((cx + r * math.cos(th), cy + r * math.sin(th)))
        th += 0.08
    draw.line(pts, fill=fill, width=width, joint='curve')


def main():
    base = render_base()
    # Bust crop: full width, cut mid-torso above the feet (feet start ~y1720 @2x).
    bust = base.crop((0, 0, 1451, 1500))
    seg = segment(bust)
    for name in ('eye_l', 'eye_r', 'brow_l', 'brow_r', 'beak'):
        f = seg[name]
        print(f'  {name:7s} center ({f["cx"]:.0f},{f["cy"]:.0f}) size {f["size"]}')
    scale = BUST_H / 1500.0
    bw = round(1451 * scale)

    def place(cell_draw_layer, layer):
        small = layer.resize((round(layer.size[0] * scale), round(layer.size[1] * scale)),
                             Image.BICUBIC)
        ox = (CELL - bw) // 2
        oy = TOP_MARGIN
        cell_draw_layer.alpha_composite(small, (ox, oy))
        return ox, oy

    def cell_xy(ox, oy, bx, by):
        return ox + bx * scale, oy + by * scale

    dirs = [(-1, -1), (0, -1), (1, -1), (-1, 0), (0, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
    dsheet = Image.new('RGBA', (CELL * 3, CELL * 3), (0, 0, 0, 0))
    for i, (dx, dy) in enumerate(dirs):
        layer = bust_layer(bust, seg, dx * FACE_DX, dy * FACE_DY,
                           turn=-dx * TURN_DEG, bdx=dx * BODY_DX, bdy=dy * BODY_DY)
        cell = Image.new('RGBA', (CELL, CELL), (0, 0, 0, 0))
        place(cell, layer)
        dsheet.alpha_composite(cell, ((i % 3) * CELL, (i // 3) * CELL))
    dsheet.save(os.path.join(HERE, 'directions.png'))

    # Reactions: centre gaze, overlays drawn in cell space.
    base_layer = bust_layer(bust, seg, 0, 0)

    def base_cell(brow_dy=0.0, eye_scale=1.0, clear_eyes=False):
        layer = bust_layer(bust, seg, 0, 0, brow_dy=brow_dy)
        if eye_scale != 1.0 or clear_eyes:
            for name in ('eye_l', 'eye_r'):
                f = seg[name]
                layer = clear_mask(layer, f)
                if eye_scale != 1.0:
                    x0, y0, x1, y1 = f['bbox']
                    region = bust.crop((x0, y0, x1 + 1, y1 + 1))
                    w, h = region.size
                    big = region.resize((round(w * eye_scale), round(h * eye_scale)), Image.BICUBIC)
                    layer.alpha_composite(big, (round(f['cx'] - big.size[0] / 2),
                                               round(f['cy'] - big.size[1] / 2)))
        cell = Image.new('RGBA', (CELL, CELL), (0, 0, 0, 0))
        ox, oy = place(cell, layer)
        return cell, ox, oy

    def sym_zone(draw):
        return 300, 52   # centre x, centre y of the symbol zone above the cap

    rx = []
    # 1 blink
    cell, ox, oy = base_cell(clear_eyes=True)
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(ox, oy, seg[name]['cx'], seg[name]['cy'])
        arc(d, cx, cy + 6, 58, 20, 9, NAVY)
    rx.append(cell)
    # 2 heart
    cell, ox, oy = base_cell(clear_eyes=True)
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(ox, oy, seg[name]['cx'], seg[name]['cy'])
        arc(d, cx, cy + 6, 58, 20, 9, NAVY)
    heart(d, 300, 52, 62, RED)
    rx.append(cell)
    # 3 sparkle
    cell, ox, oy = base_cell(clear_eyes=True)
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(ox, oy, seg[name]['cx'], seg[name]['cy'])
        arc(d, cx, cy + 6, 58, 20, 9, NAVY)
    sparkle(d, 222, 58, 24, GOLD)
    sparkle(d, 300, 36, 30, GOLD)
    sparkle(d, 378, 60, 22, GOLD)
    rx.append(cell)
    # 4 surprised: big eyes, raised brows, gold O mouth
    cell, ox, oy = base_cell(brow_dy=-30, eye_scale=1.32)
    d = ImageDraw.Draw(cell)
    mx, my = cell_xy(ox, oy, seg['beak']['cx'], seg['beak']['cy'] + 165)
    d.ellipse([mx - 20, my - 24, mx + 20, my + 24], outline=GOLD, width=8)
    rx.append(cell)
    # 5 starstruck
    cell, ox, oy = base_cell(clear_eyes=True)
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(ox, oy, seg[name]['cx'], seg[name]['cy'])
        star5(d, cx, cy, 30, 12, GOLD)
    mx, my = cell_xy(ox, oy, seg['beak']['cx'], seg['beak']['cy'] + 150)
    arc(d, mx, my - 20, 64, 26, 9, NAVY)
    rx.append(cell)
    # 6 bashful: arcs + blush
    cell, ox, oy = base_cell(clear_eyes=True)
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(ox, oy, seg[name]['cx'], seg[name]['cy'])
        arc(d, cx, cy + 6, 58, 20, 9, NAVY)
    for bx, by in ((390, 1010), (1110, 950)):
        cx, cy = cell_xy(ox, oy, bx, by)
        d.ellipse([cx - 30, cy - 16, cx + 30, cy + 16], fill=PINK)
    rx.append(cell)
    # 7 sleepy: droopy arcs + zzz
    cell, ox, oy = base_cell(clear_eyes=True)
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(ox, oy, seg[name]['cx'], seg[name]['cy'])
        arc(d, cx, cy + 14, 52, 13, 6, NAVY)
    zletter(d, 252, 58, 26, 26, 9, ZBLUE)
    zletter(d, 296, 34, 34, 34, 11, ZBLUE)
    zletter(d, 348, 6, 42, 42, 13, ZBLUE)
    rx.append(cell)
    # 8 dizzy: spirals on the eyes + wavy mouth
    cell, ox, oy = base_cell()
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(ox, oy, seg[name]['cx'], seg[name]['cy'])
        spiral(d, cx, cy, 23, 5, SPIRAL)
    mx, my = cell_xy(ox, oy, seg['beak']['cx'], seg['beak']['cy'] + 155)
    pts = [(mx - 32 + t * 6.4, my + 6 * math.sin(t * 1.1)) for t in range(11)]
    d.line(pts, fill=NAVY, width=7, joint='curve')
    rx.append(cell)
    # 9 delighted: arcs + big grin
    cell, ox, oy = base_cell(clear_eyes=True)
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(ox, oy, seg[name]['cx'], seg[name]['cy'])
        arc(d, cx, cy + 6, 58, 20, 9, NAVY)
    mx, my = cell_xy(ox, oy, seg['beak']['cx'], seg['beak']['cy'] + 150)
    arc(d, mx, my - 30, 80, 32, 11, NAVY)
    rx.append(cell)

    rsheet = Image.new('RGBA', (CELL * 3, CELL * 3), (0, 0, 0, 0))
    for i, cell in enumerate(rx):
        rsheet.alpha_composite(cell, ((i % 3) * CELL, (i // 3) * CELL))
    rsheet.save(os.path.join(HERE, 'reactions.png'))
    print('wrote directions.png + reactions.png (1800x1800)')


if __name__ == '__main__':
    main()
