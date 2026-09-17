"""Turns a generated icon on a flat magenta background into a PZ item icon.

Image models paint backgrounds rather than emit alpha, so every icon is
generated on solid #FF00FF -- a colour no food, tool or weapon is -- and keyed
out here:

  * alpha from the distance to magenta, soft between two thresholds so the
    edge is antialiased rather than a hard stair-step
  * de-spill: anything that is still magenta-tinted (an antialiased edge, a
    wisp of steam the model coloured pink) has the tint pulled back toward
    neutral, or it shows as a pink fringe on PZ's dark inventory
  * cropped to the drawn content, padded square, resized to 64x64 -- the size
    of the mod's existing Item_ icons

    python tools/key_icon.py in.jpg TrekShuttle/42/media/textures/Item_X.png
"""
import sys

from PIL import Image

KEY = (255, 0, 255)
SOFT_LO, SOFT_HI = 70.0, 170.0    # distance to magenta: transparent -> opaque
SIZE = 64
MARGIN = 0.06


def key(path, out):
    src = Image.open(path).convert("RGB")
    w, h = src.size
    px = src.load()
    img = Image.new("RGBA", (w, h))
    op = img.load()
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            d = ((r - KEY[0]) ** 2 + (g - KEY[1]) ** 2 + (b - KEY[2]) ** 2) ** 0.5
            a = (d - SOFT_LO) / (SOFT_HI - SOFT_LO)
            a = 0.0 if a < 0 else 1.0 if a > 1 else a
            # De-spill: magenta is red and blue both above green. That shared
            # excess is removed entirely, not just at the edge -- a model asked
            # for a magenta background tints whole translucent features pink
            # (the stew's steam came back lilac), and no icon in this mod is
            # meant to be pink or purple. An icon that genuinely needs purple
            # should be generated on a different key colour instead.
            excess = min(r, b) - g
            if excess > 0:
                r = int(r - excess)
                b = int(b - excess)
            op[x, y] = (max(0, r), g, max(0, b), int(round(a * 255)))

    bbox = img.getchannel("A").point(lambda v: 255 if v > 24 else 0).getbbox()
    img = img.crop(bbox)
    side = int(max(img.size) * (1 + MARGIN * 2))
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(img, ((side - img.size[0]) // 2, (side - img.size[1]) // 2))
    sq = sq.resize((SIZE, SIZE), Image.LANCZOS)
    sq.save(out, optimize=True)
    return sq


if __name__ == "__main__":
    key(sys.argv[1], sys.argv[2])
    print("wrote", sys.argv[2])
