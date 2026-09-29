"""Bakes the transporter's sparkle frames into the game (BEAM.md).

    python tools/gen_beam.py TrekShuttle/42

The frames were drawn by Gemini through the FlowDot toolkit, each one from the
frame before it so the animation really moves, and every one against the first
frame as a style reference so the look does not drift down the chain
(design/art/beam/, the prompts in BEAM.md 2). This script is everything after
that, and it is the only thing that touches them:

  * **Normalised.** Gemini hands back whatever size it likes -- frame 01 came
    back 848x1264 where the rest are 720x1456 -- and moves the column about.
    Each frame is found by its glow and put in one place at one size: the
    glow's core 0.84 of the frame tall, centred. A faint frame (the fade) has
    too little glow to be found by, so it inherits the placement of the last
    frame that had enough and was the same size -- the frames it was chained
    from.
  * **Black becomes transparent.** They were drawn on black on purpose: a glow
    keyed off magenta would leave a purple fringe everywhere it is soft, and
    here everything is soft. Alpha is the brightest channel, and the colour is
    divided by it, so a pixel drawn over the world is the pixel Gemini drew
    over black.
  * **Edges faded.** A soft margin on all four sides, so nothing a crop cut
    through shows as a line.
  * **128x256**, in media/ui, where getTexture finds it -- twice the size the
    column is drawn at close in, and the whole sheet is well under a megabyte.

It writes design/art/beam/beam_sheet.png every run: each frame over the three
grounds it will be seen on, and the two sequences in the order the game plays
them. The generator and the vet are one command, so the sheet cannot go stale.
"""
import os
import sys

import numpy as np
from PIL import Image, ImageFilter

SRC = os.path.join("design", "art", "beam")
FRAMES = 7                  # frame_00 .. frame_06: four of shimmer, three of fade
W, H = 360, 720             # the working size, 1:2
OUT_W, OUT_H = 128, 256     # the texture
CORE = 0.84                 # the glow's core, as a share of the frame's height
FAINT = 0.35                # a frame whose glow peaks under this share of
                            # frame 00's is placed by the frame before it
BLACK = 6                   # JPEG's black is not quite black; below this is nothing
EDGE = 0.15                 # the soft margin, as a share of each side
LIFT = 0.8                  # alpha ** LIFT: a plain alpha blend of pale blue
                            # over pale ground barely shows, so the glow is
                            # made a little more opaque than Gemini's black says

# The order the game plays them in, for the sheet (TREK_Beam.lua has the times).
OUT_SEQUENCE = [6, 5, 4, 0, 1, 2, 3, 0, 1, 2, 3, 4, 5, 6]
IN_SEQUENCE = [0, 1, 2, 3, 0, 1, 2, 3, 4, 5, 6]


def glow_box(im):
    """The bounding box of the glow's core, and how bright it peaks."""
    lum = im.convert("L").filter(ImageFilter.GaussianBlur(max(im.size) / 60))
    arr = np.asarray(lum, dtype=np.float32)
    peak = float(arr.max())
    ys, xs = np.nonzero(arr > peak * 0.12)
    return (int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1), peak


def crop_for(box):
    """The crop, in the source's pixels, that puts `box` centred at CORE tall."""
    k = H * CORE / (box[3] - box[1])
    cx, cy = (box[0] + box[2]) / 2, (box[1] + box[3]) / 2
    hw, hh = W / 2 / k, H / 2 / k
    return (int(cx - hw), int(cy - hh), int(cx + hw), int(cy + hh))


def normalised():
    """Every frame in place, each with the crop that placed it."""
    out, last, base_peak = [], None, None
    for i in range(FRAMES):
        im = Image.open(os.path.join(SRC, "frame_%02d.jpg" % i)).convert("RGB")
        box, peak = glow_box(im)
        if base_peak is None:
            base_peak = peak
        if peak < base_peak * FAINT and last and last[1] == im.size:
            crop, how = last[0], "inherited"
        else:
            crop, how = crop_for(box), "own glow"
            last = (crop, im.size)
        out.append(im.crop(crop).resize((W, H), Image.LANCZOS))
        print("  frame %02d  %dx%d  peak %3.0f  placed by %s" % (i, im.size[0], im.size[1], peak, how))
    return out


def to_rgba(im):
    """Black to transparent: alpha is the brightest channel, the colour
    divided by it, then the four edges faded."""
    rgb = np.asarray(im, dtype=np.float32)
    a = np.clip((rgb.max(axis=2) - BLACK) / (255.0 - BLACK), 0.0, 1.0)
    lifted = a ** LIFT
    col = np.where(a[..., None] > 0.004, rgb / np.maximum(a[..., None], 0.004), 0.0)
    col = np.clip(col, 0, 255)
    a = lifted
    h, w = a.shape

    def ramp(n, edge):
        t = np.minimum(np.arange(n) + 0.5, n - np.arange(n) - 0.5) / (n * edge)
        t = np.clip(t, 0.0, 1.0)
        return t * t * (3 - 2 * t)
    a = a * ramp(h, EDGE)[:, None] * ramp(w, EDGE)[None, :]
    out = np.dstack([col, a * 255.0]).astype(np.uint8)
    return Image.fromarray(out, "RGBA")


def over(bg, tile, size):
    base = Image.new("RGBA", size, bg + (255,))
    base.alpha_composite(tile.resize(size, Image.LANCZOS))
    return base.convert("RGB")


def sheet(tiles, path):
    """Each frame over the grounds it is seen on, then both sequences."""
    grounds = [(24, 26, 30), (74, 96, 58), (196, 194, 184)]
    fw, fh = 96, 192
    sw, sh = 48, 96
    width = max(len(tiles) * fw, len(OUT_SEQUENCE) * sw)
    img = Image.new("RGB", (width, fh * len(grounds) + sh * 2 + 8), (12, 12, 14))
    for r, bg in enumerate(grounds):
        for i, t in enumerate(tiles):
            img.paste(over(bg, t, (fw, fh)), (i * fw, r * fh))
    y = fh * len(grounds) + 4
    for seq in (OUT_SEQUENCE, IN_SEQUENCE):
        for j, i in enumerate(seq):
            img.paste(over(grounds[1], tiles[i], (sw, sh)), (j * sw, y))
        y += sh
    img.save(path)
    print("  sheet   %s (rows: over dark, grass, pale; then beam out and beam in)" % path)


def main(root):
    ui = os.path.join(root, "media", "ui")
    os.makedirs(ui, exist_ok=True)
    tiles = []
    for i, im in enumerate(normalised()):
        t = to_rgba(im).resize((OUT_W, OUT_H), Image.LANCZOS)
        cover = float(np.asarray(t)[..., 3].mean()) / 255.0
        if i < 4 and cover < 0.02:
            raise SystemExit("  FAILED: frame %02d came out almost empty (%.3f) -- "
                             "the black key has eaten the glow" % (i, cover))
        dst = os.path.join(ui, "TREK_Beam_%02d.png" % i)
        t.save(dst, optimize=True)
        tiles.append(t)
        print("  texture %s  cover %.3f" % (dst, cover))
    sheet(tiles, os.path.join(SRC, "beam_sheet.png"))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42")
