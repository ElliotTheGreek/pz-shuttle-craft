"""The field station's disguise: a 1993 breaker cabinet, drawn.

    python tools/gen_fuse_box.py

Writes design/art/adirondack/objects/fuse_box_concept.png, the picture
tools/gen_adirondack_furniture.py lays on a wall face for the `fuse_box`
flat (tools/adirondack_objects.py, FIELD_STATION.md 3).

Drawn rather than generated: it is a grey steel box with a door, a latch and
a warning triangle, and an image model has nothing to add to one. It fills
the whole frame, because a flat's concept is resized into its u/v window
edge to edge -- a background here would be painted on the stockroom wall.
The warning sign carries a lightning bolt and no words (no text in art).
"""
import os

from PIL import Image, ImageDraw, ImageFilter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "design", "art", "adirondack", "objects", "fuse_box_concept.png")

W, H = 240, 330


def draw():
    im = Image.new("RGB", (W, H), (126, 128, 124))
    d = ImageDraw.Draw(im)
    # The cabinet: a lighter face inside a dark rim, as a pressed-steel box
    # reads at a glance -- lit from the upper left like every tile here.
    d.rectangle([0, 0, W - 1, H - 1], fill=(88, 90, 88))
    d.rectangle([8, 8, W - 9, H - 9], fill=(150, 152, 147))
    d.rectangle([8, 8, W - 9, 14], fill=(176, 178, 172))          # top edge catches light
    d.rectangle([8, 8, 14, H - 9], fill=(168, 170, 164))          # and the left
    d.rectangle([W - 15, 8, W - 9, H - 9], fill=(116, 118, 114))  # the right in shade
    # The door's seam, and its piano hinge down the left.
    d.rectangle([22, 24, W - 23, H - 25], outline=(96, 98, 95), width=3)
    for y in range(34, H - 34, 22):
        d.rectangle([24, y, 30, y + 12], fill=(112, 114, 110))
    # The latch: a dark keyed handle on the right.
    d.rounded_rectangle([W - 56, H // 2 - 34, W - 38, H // 2 + 34], radius=6, fill=(46, 47, 46))
    d.ellipse([W - 53, H // 2 - 8, W - 41, H // 2 + 4], fill=(150, 140, 96))
    # Louvres near the foot, for the heat that a breaker box should not make.
    for y in range(H - 88, H - 44, 11):
        d.rectangle([54, y, W - 80, y + 5], fill=(84, 86, 84))
    # The warning triangle: yellow, black rim, a black bolt. No words.
    cx, top = W // 2 - 10, 58
    tri = [(cx, top), (cx + 52, top + 90), (cx - 52, top + 90)]
    d.polygon(tri, fill=(20, 20, 18))
    inner = [(cx, top + 14), (cx + 40, top + 82), (cx - 40, top + 82)]
    d.polygon(inner, fill=(236, 196, 40))
    bolt = [(cx + 6, top + 26), (cx - 12, top + 58), (cx - 1, top + 58),
            (cx - 8, top + 78), (cx + 13, top + 46), (cx + 2, top + 46), (cx + 10, top + 26)]
    d.polygon(bolt, fill=(20, 20, 18))
    # A strip of masking tape somebody wrote on and the damp has taken.
    d.rectangle([60, 170, 150, 186], fill=(208, 196, 158))
    d.line([66, 178, 140, 176], fill=(150, 138, 110), width=2)
    # Scuffs and grime, so it is a thing that has hung in a stockroom since 1979.
    grime = Image.new("L", (W, H), 0)
    g = ImageDraw.Draw(grime)
    for k in range(40):
        x = (k * 53) % (W - 20) + 10
        y = (k * 97) % (H - 20) + 10
        g.ellipse([x, y, x + 6 + k % 9, y + 4 + k % 5], fill=60 + (k * 13) % 70)
    grime = grime.filter(ImageFilter.GaussianBlur(2))
    dark = Image.new("RGB", (W, H), (60, 58, 50))
    im = Image.composite(dark, im, grime.point(lambda v: v // 3))
    return im


def main():
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    draw().save(OUT)
    print("wrote", os.path.relpath(OUT, ROOT))


if __name__ == "__main__":
    main()
