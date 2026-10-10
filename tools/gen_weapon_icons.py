"""The radial menu's three weapon icons: generated raws to 64x64 wheel slices.

    python tools/gen_weapon_icons.py     # writes TrekShuttle/42/media/ui/TREK_Weapon_*.png

Each weapon has its own slice on the vehicle wheel (TREK_VehicleMenu), so
each has its own picture. The raws are in design/art/wheel/<weapon>_raw.jpg:
flat emblems drawn by FlowDot's Gemini Image toolkit (`generate-image`,
gemini-3-pro-image-preview) on a flat key colour the emblem does not use,
green for the red torpedo and the amber phasers, magenta for the blue tractor
beam (ROADMAP.md, "How art gets made").

Not tools/key_icon.py, though it is the same idea. That one crops to
everything that is not background, and a wide raw off a JPEG has a few
off-key pixels at its edges: the torpedo came out a tenth of its frame, with
the whole 1408-pixel width taken for content. Here the crop is to the
**solid** part of the emblem (rows and columns with a real run of opaque
pixels), which a speck cannot move.

  1. the key colour is measured from a border ring, never assumed;
  2. alpha ramps by distance from it, and what is left of the key's tint on
     an edge pixel is pulled back, or it shows as a bright fringe on the
     wheel's dark ring;
  3. cropped to the emblem, padded square with a small margin, cut to 64.

It writes design/art/wheel/weapon_wheel_sheet.png: the three beside the
wheel's other slices on the game's dark grey, at 128, 48 and 32. Look at it.
"""
import os

from PIL import Image

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "design", "art", "wheel")
OUT = os.path.join(ROOT, "TrekShuttle", "42", "media", "ui")

WEAPONS = ["torpedo", "phaser", "tractor"]
NEIGHBOURS = ["TREK_Aboard", "TREK_Ascend", "TREK_Land"]

SIZE = 64
RING = 6            # border thickness sampled for the key colour
LO, HI = 60.0, 130.0  # distance from the key: clear below, solid above
MIN_CLEARED = 0.25  # at least this much must key out, or stop
MIN_RUN = 0.01      # a row or column is the emblem's with this much of it solid
MARGIN = 0.05


def median(values):
    values = sorted(values)
    return values[len(values) // 2]


def key_of(img):
    w, h = img.size
    px = img.load()
    ring = [px[x, y] for y in range(h) for x in range(w)
            if x < RING or y < RING or x >= w - RING or y >= h - RING]
    return tuple(median([p[c] for p in ring]) for c in range(3))


def keyed(path):
    src = Image.open(path).convert("RGB")
    w, h = src.size
    key = key_of(src)
    out = Image.new("RGBA", (w, h))
    sp, op = src.load(), out.load()
    cleared = 0
    strongest = max(range(3), key=lambda c: key[c])
    for y in range(h):
        for x in range(w):
            r, g, b = sp[x, y]
            d = ((r - key[0]) ** 2 + (g - key[1]) ** 2 + (b - key[2]) ** 2) ** 0.5
            if d <= LO:
                cleared += 1
                continue
            a = 1.0 if d >= HI else (d - LO) / (HI - LO)
            rgb = [r, g, b]
            if a < 1.0:
                # An edge pixel is part key: take the key's own channel back
                # to what the other two say.
                others = [rgb[c] for c in range(3) if c != strongest]
                rgb[strongest] = min(rgb[strongest], max(others))
            op[x, y] = (rgb[0], rgb[1], rgb[2], int(a * 255 + 0.5))
    frac = cleared / float(w * h)
    if frac < MIN_CLEARED:
        raise SystemExit("%s: only %.0f%% keyed out against %s; the background "
                         "is not the flat key that was asked for" % (path, frac * 100, key))
    return out, key, frac


def solid_box(img):
    """The emblem's box: rows and columns with a real run of opaque pixels."""
    w, h = img.size
    alpha = img.getchannel("A").point(lambda v: 255 if v >= 128 else 0)
    cols = alpha.resize((w, 1), Image.BOX).load()
    rows = alpha.resize((1, h), Image.BOX).load()
    xs = [x for x in range(w) if cols[x, 0] / 255.0 >= MIN_RUN]
    ys = [y for y in range(h) if rows[0, y] / 255.0 >= MIN_RUN]
    if not xs or not ys:
        raise SystemExit("nothing solid left after keying")
    return xs[0], ys[0], xs[-1] + 1, ys[-1] + 1


def icon(name):
    img, key, frac = keyed(os.path.join(RAW, name + "_raw.jpg"))
    box = solid_box(img)
    img = img.crop(box)
    side = int(max(img.size) * (1 + MARGIN * 2))
    sq = Image.new("RGBA", (side, side))
    sq.paste(img, ((side - img.size[0]) // 2, (side - img.size[1]) // 2))
    sq = sq.resize((SIZE, SIZE), Image.LANCZOS)
    fill = sum(1 for p in sq.getdata() if p[3] >= 128) / float(SIZE * SIZE)
    path = os.path.join(OUT, "TREK_Weapon_%s.png" % name)
    sq.save(path)
    print("%-8s key %s, %.0f%% keyed out, emblem %dx%d, fills %.0f%% of its frame"
          % (name, key, frac * 100, box[2] - box[0], box[3] - box[1], fill * 100))
    if fill < 0.15:
        raise SystemExit("%s fills %.0f%% of its frame: a speck on the wheel" % (name, fill * 100))
    return sq


def sheet(icons):
    names = list(icons) + NEIGHBOURS
    out = Image.new("RGBA", (len(names) * 140 + 20, 260), (38, 38, 42, 255))
    for i, n in enumerate(names):
        im = icons.get(n) or Image.open(os.path.join(OUT, n + ".png")).convert("RGBA")
        out.alpha_composite(im.resize((128, 128), Image.NEAREST), (20 + i * 140, 10))
        out.alpha_composite(im.resize((48, 48), Image.LANCZOS), (60 + i * 140, 150))
        out.alpha_composite(im.resize((32, 32), Image.LANCZOS), (68 + i * 140, 210))
    path = os.path.join(RAW, "weapon_wheel_sheet.png")
    out.save(path)
    print("sheet:", path)


def main():
    icons = {}
    for w in WEAPONS:
        icons[w] = icon(w)
    sheet(icons)


if __name__ == "__main__":
    main()
