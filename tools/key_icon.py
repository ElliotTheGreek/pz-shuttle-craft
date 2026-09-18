"""Turns a generated icon on a flat magenta background into a PZ item icon.

Image models paint backgrounds rather than emit alpha, so every icon is
generated on solid #FF00FF -- a colour no food, tool or weapon is -- and keyed
out here:

  * alpha from the distance to the background colour, soft between two
    thresholds so the edge is antialiased rather than a hard stair-step
  * de-spill: anything that is still magenta-tinted (an antialiased edge, a
    wisp of steam the model coloured pink) has the tint pulled back toward
    neutral, or it shows as a pink fringe on PZ's dark inventory
  * cropped to the drawn content, padded square, resized to 64x64 -- the size
    of the mod's existing Item_ icons

    python tools/key_icon.py in.png TrekShuttle/42/media/textures/Item_X.png

**The key colour is measured, not assumed.** Asking for #FF00FF does not get
#FF00FF: the drinks came back on a dusty raspberry around (206, 34, 137),
roughly 130 away from real magenta, which the old fixed-key version read as
foreground. Every icon kept its background as an opaque dark red square and
looked, at a glance, like art that had simply come out muddy -- the silent
half-failure this project keeps paying for. So the background is sampled from
a border ring and reported, and the result is checked before it is written.

Measured on four generated icons, the distance histogram has a clean gap:
63-79% of pixels sit within 20 of the sampled background, essentially nothing
falls between 20 and 80, and real content starts past 80. The thresholds below
sit in that gap.
"""
import sys

from PIL import Image

MAGENTA = (255, 0, 255)
# Thresholds for a background sampled off the image. The gap above is wide, so
# these are deliberately tight rather than generous.
SOFT_LO, SOFT_HI = 35.0, 85.0
# A near-perfect magenta gets the original, wider ramp, so an icon generated
# before the key was measured re-keys byte-for-byte the way it did then.
CLEAN_LO, CLEAN_HI = 70.0, 170.0
CLEAN_KEY = 40.0                  # within this of #FF00FF counts as clean
RING = 4                          # border thickness sampled for the key
MIN_CLEARED = 0.25                # at least this much must key out, or stop
SIZE = 64
MARGIN = 0.06


def sample_key(px, w, h):
    """The background colour, as the median of a border ring.

    A ring rather than the four corners: a bottle that runs off the bottom of
    the frame takes two corners with it, and the median survives that.
    """
    vals = []
    for y in range(h):
        edge_row = y < RING or y >= h - RING
        for x in range(w):
            if edge_row or x < RING or x >= w - RING:
                vals.append(px[x, y])
    reds = sorted(v[0] for v in vals)
    greens = sorted(v[1] for v in vals)
    blues = sorted(v[2] for v in vals)
    mid = len(vals) // 2
    return (reds[mid], greens[mid], blues[mid])


def key(path, out):
    src = Image.open(path).convert("RGB")
    w, h = src.size
    px = src.load()

    found = sample_key(px, w, h)
    off = sum((a - b) ** 2 for a, b in zip(found, MAGENTA)) ** 0.5
    clean = off <= CLEAN_KEY
    lo, hi = (CLEAN_LO, CLEAN_HI) if clean else (SOFT_LO, SOFT_HI)
    print(f"  key {found} ({'clean magenta' if clean else f'{off:.0f} off magenta'}), "
          f"ramp {lo:.0f}-{hi:.0f}")

    img = Image.new("RGBA", (w, h))
    op = img.load()
    cleared = 0
    for y in range(h):
        for x in range(w):
            r, g, b = px[x, y]
            d = ((r - found[0]) ** 2 + (g - found[1]) ** 2
                 + (b - found[2]) ** 2) ** 0.5
            a = (d - lo) / (hi - lo)
            a = 0.0 if a < 0 else 1.0 if a > 1 else a
            if a == 0.0:
                cleared += 1
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

    # Count the result back rather than trusting the key. Every way this fails
    # -- a background the model drifted off, a subject that fills the frame, a
    # photo with no flat backdrop at all -- produces a plausible-looking file
    # with an opaque square behind the art, and that is only ever noticed by
    # eye, late.
    share = cleared / float(w * h)
    if share < MIN_CLEARED:
        raise SystemExit(
            f"  FAILED: only {share:.1%} of {path} keyed out (wanted "
            f"{MIN_CLEARED:.0%}+). The sampled background was {found}; if that "
            f"is not the backdrop colour, the image has no flat backdrop and "
            f"nothing was written.")
    print(f"  cleared {share:.1%} of the frame")

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
