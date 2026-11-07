"""Build page-mascot source sheets for Gradis from the penguin reference PNG.

Source: characters/gradis/penguin-ref.png ("Graduation Penguin with Compass",
1254x1254 RGBA, flat navy/gold/white vector style with real alpha).

Pipeline (no image model involved):
  1. Remove the hand-held compass. It overlaps the lower-right cheek, so a
     rectangular bust crop cannot exclude it. The compass blobs (gold ring,
     inner white, navy needle) are filled with a mirror of the left side of
     the face about the eye midline -- the art is near-symmetric there, and
     mirroring also reproduces transparent background outside the head edge.
  2. Crop a head-plus-upper-shoulders bust (chin + a short torso sliver, cut
     above the compass handle / wings / feet -- mascot framing is bust only,
     no held props).
  3. Same rigid-gaze + expression-overlay technique as make-sheets.py:
     segment eyes / brows / beak by colour blobs, shift them for the nine
     head directions, draw the nine expression overlays.

Regenerate:  /tmp/opencode/mascot-venv/bin/python make-sheets-penguin.py  (from webapp/)
Then build:  python <skill>/scripts/mascot.py gradis --skip-generate
"""
import math
import os

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, 'penguin-ref.png')

NAVY = (15, 48, 97, 255)
GOLD = (250, 172, 42, 255)
RED = (229, 72, 77, 255)
PINK = (242, 163, 192, 235)
ZBLUE = (127, 168, 215, 255)
SPIRAL = (143, 180, 221, 255)

# Bust crop in source pixels: full head + cap + torso sliver, compass-free.
CROP = (150, 60, 1150, 800)   # -> 1000 x 740
CELL = 600
BUST_H = 372
TOP_MARGIN = 100
MIDX = 662.0                  # eye midline: mirror axis for compass removal
# Compass removal zone in source pixels: the whole hand-held compass
# (ring + inner + needle + its low-alpha fringe) is filled with a mirror of
# the left side about MIDX. Rectangular on purpose: the ring's antialiased
# fringe extends past the opaque blobs, and mirroring also reproduces clean
# background / head-edge pixels outside the head.
COMPASS_RECT = (770, 640, 1160, 800)   # x0, y0, x1, y1; bottom == CROP bottom
FACE_DX, FACE_DY = 36, 24     # gaze travel in bust px
BODY_DX, BODY_DY = 9, 7
TURN_DEG = 1.5


def load_source():
    return Image.open(SRC).convert('RGBA')


def clean_halo(img, thresh=128):
    """Defringe the source's low-alpha halo.

    The PNG carries a wide halo of near-transparent junk pixels (red /
    yellow / grey) around the art. Non-premultiplied downscales mix their
    RGB into the visible edges, so repaint them with the nearest opaque
    colour. Alpha is untouched -- only the invisible RGB is repaired.
    """
    a = np.array(img)
    rgb, alpha = a[..., :3], a[..., 3]
    faint = alpha <= thresh
    print(f'halo pixels (alpha<={thresh}): {int(faint.sum())}')
    if not faint.any():
        return img
    _, idx = ndimage.distance_transform_edt(~(alpha > thresh),
                                            return_indices=True)
    filled = rgb[tuple(idx)]
    a[..., :3] = np.where(faint[..., None], filled, rgb)
    return Image.fromarray(a, 'RGBA')


def remove_compass(img, fmask):
    """Fill the compass rect with mirrored left-side pixels.

    Two protections: destination pixels belonging to face features (the
    right eye dips into the rect's top rows) are never overwritten, and
    source pixels belonging to face features (the left eye mirrors into
    the rect) are replaced with white -- every such destination is
    white face in the original.
    """
    x0, y0, x1, y1 = COMPASS_RECT
    out = np.array(img)
    H, W = out.shape[:2]
    orig_alpha = out[:, :, 3]
    ys, xs = np.mgrid[y0:y1, x0:x1]
    sx = np.round(2 * MIDX - xs).astype(int)
    # Pixels that were already (near-)transparent stay transparent: this
    # keeps mirrored head-edge pixels from floating off the silhouette.
    # The 32 cut keeps stronger fringe (replaced with mirrored content
    # below) while dropping only imperceptible dust.
    ok = (sx >= 0) & (sx < W) & ~fmask[ys, xs] & (orig_alpha[ys, xs] > 32)
    src_feat = fmask[ys, sx.clip(0, W - 1)]
    plain = ok & ~src_feat
    out[ys[plain], xs[plain]] = out[ys[plain], sx[plain]]
    white = ok & src_feat
    out[ys[white], xs[white]] = (255, 255, 255, 255)
    print(f'compass rect x[{x0},{x1}] y[{y0},{y1}] mirrored about {MIDX}')
    return Image.fromarray(out, 'RGBA')


def segment(bust, ox, oy):
    """Find movable face features. (ox, oy) maps bust -> source coords."""
    px = np.array(bust).astype(int)
    R, G, B, A = px[:, :, 0], px[:, :, 1], px[:, :, 2], px[:, :, 3]
    op = A > 128
    navy = op & (R < 110) & (G < 130) & (B > 60)
    gold = op & (R > 200) & (G > 140) & (B < 100)

    def blobs(mask):
        lab, n = ndimage.label(mask)
        out = []
        for i in range(1, n + 1):
            ys, xs = np.where(lab == i)
            out.append({'size': len(xs), 'bbox': (xs.min(), ys.min(), xs.max(), ys.max()),
                        'cx': float(xs.mean()), 'cy': float(ys.mean()), 'mask': lab == i})
        return sorted(out, key=lambda b: -b['size'])

    navy_blobs = blobs(navy)
    body = navy_blobs[0]
    # Eyes: mid-size navy discs on the white face (source x 350-960, y 480-700)
    eyes = [b for b in navy_blobs[1:]
            if 350 < b['cx'] + ox < 960 and 480 < b['cy'] + oy < 700 and b['size'] > 3000]
    assert len(eyes) == 2, f'expected 2 eyes, found {len(eyes)}'
    eyes.sort(key=lambda b: b['cx'])
    # Brows: small navy slashes above the eyes
    brows = [b for b in navy_blobs[1:]
             if 350 < b['cx'] + ox < 960 and 400 < b['cy'] + oy < 540
             and 500 < b['size'] < 5000]
    assert len(brows) == 2, f'expected 2 brows, found {len(brows)}'
    brows.sort(key=lambda b: b['cx'])
    # Beak: gold triangle on the face below the eyes
    beaks = [b for b in blobs(gold)
             if 500 < b['cx'] + ox < 800 and 550 < b['cy'] + oy < 720 and b['size'] > 2000]
    assert len(beaks) == 1, f'expected 1 beak, found {len(beaks)}'
    return {'body': body, 'eye_l': eyes[0], 'eye_r': eyes[1],
            'brow_l': brows[0], 'brow_r': brows[1], 'beak': beaks[0]}


def clear_mask(layer, base, feat):
    """Clear a feature's pixels, back-filling the hole with the local
    background (median of the bbox perimeter in base).

    Back-fill matters: shifting a cutout leaves a trailing strip of the
    cleared hole uncovered, and on this art the face behind the features is
    opaque white, so an unfilled hole would read as a transparent slit.
    (The previous SVG art had a transparent face hole, where the slit was
    invisible -- this fix is required for the new opaque face.)
    """
    a = np.array(layer)
    m = feat['mask']
    x0, y0, x1, y1 = feat['bbox']
    ring = np.array(base)[y0:y1 + 1, x0:x1 + 1].reshape(-1, 4)
    edge = np.concatenate([ring[:x1 - x0 + 1], ring[-(x1 - x0 + 1):]])
    op = edge[edge[:, 3] > 128][:, :3]
    bg = np.median(op, axis=0) if len(op) else np.array([255, 255, 255])
    a[m] = (int(bg[0]), int(bg[1]), int(bg[2]), 255)
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


def resize_premultiplied(layer, size):
    """BICUBIC downscale in premultiplied alpha, so the RGB of transparent
    pixels cannot bleed into the visible edges."""
    a = np.array(layer).astype(np.float32)
    rgb, alpha = a[..., :3], a[..., 3:4] / 255.0
    pre = np.dstack([rgb * alpha, a[..., 3]])
    small = np.array(Image.fromarray(pre.astype(np.uint8), 'RGBA'
                                     ).resize(size, Image.BICUBIC)).astype(np.float32)
    s_rgb, s_a = small[..., :3], small[..., 3:4]
    out = np.zeros_like(small)
    m = s_a[..., 0] > 0
    out[..., :3][m] = np.clip(s_rgb[m] * 255.0 / np.maximum(s_a[m], 1e-6), 0, 255)
    out[..., 3] = s_a[..., 0]
    # Kill sub-visible residue: un-premultiplying amplifies uint8 rounding
    # in near-zero pixels into saturated specks, and BICUBIC leaves a long
    # alpha-1 tail around hard edges. Nothing real lives under alpha 16.
    tiny = out[..., 3] < 16
    out[tiny] = (0, 0, 0, 0)
    return Image.fromarray(out.astype(np.uint8), 'RGBA')


def bust_layer(base, seg, fdx, fdy, turn=0.0, bdx=0.0, bdy=0.0, brow_dy=0.0):
    """Bust with the face shifted by (fdx, fdy) and the whole bust turned."""
    layer = base.copy()
    for name in ('eye_l', 'eye_r', 'brow_l', 'brow_r', 'beak'):
        layer = clear_mask(layer, base, seg[name])
    for name in ('eye_l', 'eye_r', 'beak'):
        layer = stamp(layer, base, seg[name], fdx, fdy)
    for name in ('brow_l', 'brow_r'):
        layer = stamp(layer, base, seg[name], fdx, fdy + brow_dy)
    if turn or bdx or bdy:
        neck = ((seg['eye_l']['cx'] + seg['eye_r']['cx']) / 2, 715.0)
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
    src = clean_halo(load_source())
    # Feature masks first: they constrain the mirror fill (right eye dips
    # into the rect, left eye would contaminate mirror sources).
    pre = segment(src, 0, 0)
    fmask = np.zeros((src.size[1], src.size[0]), bool)
    for name in ('eye_l', 'eye_r', 'brow_l', 'brow_r', 'beak'):
        fmask |= pre[name]['mask']
    fmask = ndimage.binary_dilation(fmask, iterations=2)
    fixed = remove_compass(src, fmask)
    bust = fixed.crop(CROP)
    ox, oy = CROP[0], CROP[1]
    seg = segment(bust, ox, oy)
    for name in ('eye_l', 'eye_r', 'brow_l', 'brow_r', 'beak'):
        f = seg[name]
        print(f'  {name:7s} center ({f["cx"] + ox:.0f},{f["cy"] + oy:.0f}) size {f["size"]}')
    bw, bh = bust.size
    scale = BUST_H / bh
    bw_small = round(bw * scale)

    def place(cell_draw_layer, layer):
        small = resize_premultiplied(layer, (round(layer.size[0] * scale),
                                             round(layer.size[1] * scale)))
        xoff = (CELL - bw_small) // 2
        yoff = TOP_MARGIN
        cell_draw_layer.alpha_composite(small, (xoff, yoff))
        return xoff, yoff

    def cell_xy(xoff, yoff, bx, by):
        return xoff + bx * scale, yoff + by * scale

    dirs = [(-1, -1), (0, -1), (1, -1), (-1, 0), (0, 0), (1, 0), (-1, 1), (0, 1), (1, 1)]
    dsheet = Image.new('RGBA', (CELL * 3, CELL * 3), (0, 0, 0, 0))
    for i, (dx, dy) in enumerate(dirs):
        layer = bust_layer(bust, seg, dx * FACE_DX, dy * FACE_DY,
                           turn=-dx * TURN_DEG, bdx=dx * BODY_DX, bdy=dy * BODY_DY)
        cell = Image.new('RGBA', (CELL, CELL), (0, 0, 0, 0))
        place(cell, layer)
        dsheet.alpha_composite(cell, ((i % 3) * CELL, (i // 3) * CELL))
    dsheet.save(os.path.join(HERE, 'directions.png'))

    def base_cell(brow_dy=0.0, eye_scale=1.0, clear_eyes=False):
        layer = bust_layer(bust, seg, 0, 0, brow_dy=brow_dy)
        if eye_scale != 1.0 or clear_eyes:
            for name in ('eye_l', 'eye_r'):
                f = seg[name]
                layer = clear_mask(layer, bust, f)
                if eye_scale != 1.0:
                    x0, y0, x1, y1 = f['bbox']
                    region = bust.crop((x0, y0, x1 + 1, y1 + 1))
                    w, h = region.size
                    big = region.resize((round(w * eye_scale), round(h * eye_scale)), Image.BICUBIC)
                    layer.alpha_composite(big, (round(f['cx'] - big.size[0] / 2),
                                               round(f['cy'] - big.size[1] / 2)))
        cell = Image.new('RGBA', (CELL, CELL), (0, 0, 0, 0))
        xoff, yoff = place(cell, layer)
        return cell, xoff, yoff

    rx = []
    # 1 blink
    cell, xoff, yoff = base_cell(clear_eyes=True)
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(xoff, yoff, seg[name]['cx'], seg[name]['cy'])
        arc(d, cx, cy + 6, 58, 20, 9, NAVY)
    rx.append(cell)
    # 2 heart
    cell, xoff, yoff = base_cell(clear_eyes=True)
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(xoff, yoff, seg[name]['cx'], seg[name]['cy'])
        arc(d, cx, cy + 6, 58, 20, 9, NAVY)
    heart(d, 300, 48, 62, RED)
    rx.append(cell)
    # 3 sparkle
    cell, xoff, yoff = base_cell(clear_eyes=True)
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(xoff, yoff, seg[name]['cx'], seg[name]['cy'])
        arc(d, cx, cy + 6, 58, 20, 9, NAVY)
    sparkle(d, 222, 54, 24, GOLD)
    sparkle(d, 300, 32, 30, GOLD)
    sparkle(d, 378, 56, 22, GOLD)
    rx.append(cell)
    # 4 surprised: big eyes, raised brows, gold O mouth (beak sits low, so
    # the O is small and tucked just under it to stay inside the face)
    cell, xoff, yoff = base_cell(brow_dy=-30, eye_scale=1.32)
    d = ImageDraw.Draw(cell)
    mx, my = cell_xy(xoff, yoff, seg['beak']['cx'], seg['beak']['cy'] + 80)
    d.ellipse([mx - 15, my - 14, mx + 15, my + 14], outline=GOLD, width=7)
    rx.append(cell)
    # 5 starstruck
    cell, xoff, yoff = base_cell(clear_eyes=True)
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(xoff, yoff, seg[name]['cx'], seg[name]['cy'])
        star5(d, cx, cy, 30, 12, GOLD)
    mx, my = cell_xy(xoff, yoff, seg['beak']['cx'], seg['beak']['cy'] + 105)
    arc(d, mx, my - 20, 64, 26, 9, NAVY)
    rx.append(cell)
    # 6 bashful: arcs + blush (cheeks flank the eyes)
    cell, xoff, yoff = base_cell(clear_eyes=True)
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(xoff, yoff, seg[name]['cx'], seg[name]['cy'])
        arc(d, cx, cy + 6, 58, 20, 9, NAVY)
    for bx, by in ((seg['eye_l']['cx'] - 80, 640), (seg['eye_r']['cx'] + 80, 640)):
        cx, cy = cell_xy(xoff, yoff, bx, by)
        d.ellipse([cx - 30, cy - 16, cx + 30, cy + 16], fill=PINK)
    rx.append(cell)
    # 7 sleepy: droopy arcs + zzz
    cell, xoff, yoff = base_cell(clear_eyes=True)
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(xoff, yoff, seg[name]['cx'], seg[name]['cy'])
        arc(d, cx, cy + 14, 52, 13, 6, NAVY)
    zletter(d, 252, 54, 26, 26, 9, ZBLUE)
    zletter(d, 296, 30, 34, 34, 11, ZBLUE)
    zletter(d, 348, 4, 42, 42, 13, ZBLUE)
    rx.append(cell)
    # 8 dizzy: spirals on the eyes + wavy mouth
    cell, xoff, yoff = base_cell()
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(xoff, yoff, seg[name]['cx'], seg[name]['cy'])
        spiral(d, cx, cy, 23, 5, SPIRAL)
    mx, my = cell_xy(xoff, yoff, seg['beak']['cx'], seg['beak']['cy'] + 105)
    pts = [(mx - 32 + t * 6.4, my + 6 * math.sin(t * 1.1)) for t in range(11)]
    d.line(pts, fill=NAVY, width=7, joint='curve')
    rx.append(cell)
    # 9 delighted: arcs + big grin
    cell, xoff, yoff = base_cell(clear_eyes=True)
    d = ImageDraw.Draw(cell)
    for name in ('eye_l', 'eye_r'):
        cx, cy = cell_xy(xoff, yoff, seg[name]['cx'], seg[name]['cy'])
        arc(d, cx, cy + 6, 58, 20, 9, NAVY)
    mx, my = cell_xy(xoff, yoff, seg['beak']['cx'], seg['beak']['cy'] + 105)
    arc(d, mx, my - 30, 80, 32, 11, NAVY)
    rx.append(cell)

    rsheet = Image.new('RGBA', (CELL * 3, CELL * 3), (0, 0, 0, 0))
    for i, cell in enumerate(rx):
        rsheet.alpha_composite(cell, ((i % 3) * CELL, (i // 3) * CELL))
    rsheet.save(os.path.join(HERE, 'reactions.png'))
    print('wrote directions.png + reactions.png (1800x1800)')


if __name__ == '__main__':
    main()
