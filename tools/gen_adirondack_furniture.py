"""The Adirondack's furniture, modelled and rendered into tiles.

    python tools/gen_adirondack_furniture.py

Writes design/tiles/2x/trek_adirondack_02.png (the furniture sheet) and
design/art/adirondack/furniture_preview.png: the pieces standing in a room made
of trek_adirondack_01, both facings side by side, to judge before installing.

Each piece is a list of boxes in its own coordinates -- `l` along its length
from the wall it stands against, `w` across it, `z` up -- and `place()` lays it
along x (facing W: its back to the west wall) or along y (facing N). Both
facings come from the one model, so they are the same object.

Vanilla beds have exactly two facings, W and N -- the head against one of the
two walls the camera sees -- and a single bed is two squares, head then foot
(furniture_bedding_01_002/003, _001/000). Ours follows that.

SHEET LAYOUT (8 columns; the index is what BuildingFurniture.txt names)
  0 bed W head   1 bed W foot   2 bed N head   3 bed N foot
"""
import os
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isorender as iso  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "design", "art", "adirondack")
TILES = os.path.join(ROOT, "design", "tiles", "2x")
SHEET = "trek_adirondack_02"
CW, CH = iso.CW, iso.CH

# The palette, kept to the bulkhead's and the carpet's so a room reads as one.
PLINTH = (58, 60, 66)
FRAME = (148, 144, 138)
MATTRESS = (224, 216, 198)
DUVET = (68, 84, 118)
FOLD = (98, 116, 152)
PILLOW = (234, 230, 222)
HEAD = (184, 174, 158)
STRIP = (255, 214, 156)


def bed():
    """A single bed, two squares long, head at l = 0."""
    return [
        (0.12, 1.90, 0.14, 0.86, 0.00, 0.12, PLINTH, 0.0),
        (0.06, 1.96, 0.06, 0.94, 0.12, 0.34, FRAME, 0.02),
        (0.10, 1.92, 0.10, 0.90, 0.34, 0.50, MATTRESS, 0.02),
        (0.72, 1.94, 0.08, 0.92, 0.44, 0.54, DUVET, 0.05),
        (0.72, 0.88, 0.08, 0.92, 0.44, 0.565, FOLD, 0.04),
        (0.16, 0.52, 0.20, 0.80, 0.50, 0.61, PILLOW, 0.02),
        (0.00, 0.08, 0.02, 0.98, 0.00, 1.15, HEAD, 0.015),
        (0.08, 0.095, 0.10, 0.90, 0.82, 0.86, STRIP, 0.0),
    ]


def place(parts, facing):
    """Lay a model along x (facing W) or y (facing N)."""
    out = []
    for l0, l1, w0, w1, z0, z1, col, grain in parts:
        if facing == "W":
            out.append(iso.Box(l0, w0, z0, l1, w1, z1, col, grain=grain))
        else:
            out.append(iso.Box(w0, l0, z0, w1, l1, z1, col, grain=grain))
    return out


# name, model, length in squares, {facing: [sheet index per square along its length]}
PIECES = [
    ("bed", bed, 2, {"W": [0, 1], "N": [2, 3]}),
]


def build():
    tiles = {}
    for name, model, length, facings in PIECES:
        for facing, idxs in facings.items():
            fp = (length, 1) if facing == "W" else (1, length)
            out = iso.render(place(model(), facing), fp)
            for k, idx in enumerate(idxs):
                sq = (k, 0) if facing == "W" else (0, k)
                t = out[sq]
                if t.split()[3].getbbox() is None:
                    sys.exit("%s %s square %d came out empty" % (name, facing, k))
                tiles[idx] = t
    return tiles


def preview(tiles):
    """Both bed facings in a 5x5 room of sheet-01 tiles."""
    s1 = Image.open(os.path.join(TILES, "trek_adirondack_01.png")).convert("RGBA")

    def s1t(i):
        return s1.crop(((i % 8) * CW, (i // 8) * CH, (i % 8) * CW + CW, (i // 8) * CH + CH))

    W = H = 5
    ox, oy = 64 * H + 32, 40
    canvas = Image.new("RGBA", (64 * (W + H) + 128, 32 * (W + H) + 320), (20, 20, 26, 255))

    def put(img, tx, ty):
        canvas.alpha_composite(img, (ox + (tx - ty) * 64 - 64, oy + (tx + ty) * 32))

    for ty in range(H):
        for tx in range(W):
            put(s1t(24), tx, ty)
    order = {}
    for ty in range(H):
        for tx in range(W):
            layers = []
            if tx == 0 and ty == 0:
                layers.append(s1t(2))
            elif ty == 0:
                layers.append(s1t(1))
            elif tx == 0:
                layers.append(s1t(0))
            order[(tx, ty)] = layers
    order[(0, 3)] += [tiles[0]]          # a bed facing W, head on the west wall
    order[(1, 3)] += [tiles[1]]
    order[(3, 0)] += [tiles[2]]          # a bed facing N, head on the north wall
    order[(3, 1)] += [tiles[3]]
    for key in sorted(order, key=lambda k: (k[0] + k[1], k[0])):
        for img in order[key]:
            put(img, *key)
    canvas.save(os.path.join(ART, "furniture_preview.png"))


def main():
    tiles = build()
    rows = max(tiles) // 8 + 1
    sheet = Image.new("RGBA", (CW * 8, CH * max(rows, 1)), (0, 0, 0, 0))
    for i, t in tiles.items():
        sheet.paste(t, ((i % 8) * CW, (i // 8) * CH))
    os.makedirs(TILES, exist_ok=True)
    sheet.save(os.path.join(TILES, SHEET + ".png"))
    preview(tiles)
    for i in sorted(tiles):
        print("tile %d bbox %s" % (i, tiles[i].split()[3].getbbox()))


if __name__ == "__main__":
    main()
