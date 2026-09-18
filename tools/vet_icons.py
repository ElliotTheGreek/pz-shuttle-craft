"""Contact sheet of item icons at the size the game actually draws them.

    python tools/vet_icons.py design/art/food/drinks_sheet.png Raktajino EarlGrey
    python tools/vet_icons.py design/art/all_icons.png           # every Item_TREK_

Each icon is drawn twice on PZ's dark inventory grey: once at 64, once at
**32**, which is the size that decides whether it works. Detail that sells an
image at 1024 is mush at 32 -- the first gagh was a lovely bowl of worms and
read as chili -- so the small row is the one to look at, and the sheet is
nearest-neighbour upscaled so it can be looked at without squinting.

Pair it with the Gemini toolkit's `analyze-image` (ROADMAP.md, "How art gets
made"): render the sheet, then ask for a critique of the small row. That pass
is what caught the bloodwine bottle vanishing into the background and the
raktajino reading as an empty dark hole rather than a full mug.

The background here is #272727, close to the inventory panel's. An icon that
needs a bright rim to survive it is an icon that needs redrawing, not a
brighter backdrop.
"""
import glob
import os
import sys

from PIL import Image

TEX = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                   "TrekShuttle", "42", "media", "textures")
BG = (39, 39, 39)
SIZES = (64, 32)
PAD = 10
ZOOM = 3


def sheet(out, names):
    paths = []
    for n in names:
        p = n if os.path.isfile(n) else os.path.join(TEX, f"Item_TREK_{n}.png")
        if not os.path.isfile(p):
            raise SystemExit(f"no icon for {n!r} (looked for {p})")
        paths.append((os.path.basename(p), p))

    cell = max(SIZES) + PAD * 2
    rows = len(SIZES)
    img = Image.new("RGB", (cell * len(paths), cell * rows), BG)
    for col, (_, p) in enumerate(paths):
        src = Image.open(p).convert("RGBA")
        for row, size in enumerate(SIZES):
            s = src.resize((size, size), Image.LANCZOS)
            box = Image.new("RGBA", (size, size), BG + (255,))
            box.alpha_composite(s)
            img.paste(box.convert("RGB"),
                      (col * cell + (cell - size) // 2,
                       row * cell + (cell - size) // 2))

    img = img.resize((img.width * ZOOM, img.height * ZOOM), Image.NEAREST)
    os.makedirs(os.path.dirname(os.path.abspath(out)), exist_ok=True)
    img.save(out)
    print(f"{len(paths)} icon(s) at {' and '.join(str(s) for s in SIZES)}px "
          f"-> {out}")
    for name, _ in paths:
        print(f"  {name}")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    out = sys.argv[1]
    names = sys.argv[2:]
    if not names:
        names = sorted(glob.glob(os.path.join(TEX, "Item_TREK_*.png")))
    sheet(out, names)
