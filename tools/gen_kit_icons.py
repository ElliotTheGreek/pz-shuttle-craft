"""The installation kits' icons, rendered from the machines' own tiles.

    python tools/gen_kit_icons.py

Writes TrekShuttle/42/media/textures/Item_TREK_{WarpCoreKit,ReplicatorKit,
EMHKit}.png (64x64) and design/art/installations/kits_sheet.png to vet them on.

Each icon is the machine as it stands in the world -- its tile, or the core's
four -- cropped to its pixels, fitted into the frame, over a small grey crate
corner so it reads as something carried rather than something standing. The
same pictures as the machines they install, so the two cannot drift apart
(DEV_GUIDE: *An icon can be rendered from the model instead of drawn*).
"""
import json
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET = os.path.join(ROOT, "design", "tiles", "2x", "trek_adirondack_02.png")
INDEX = os.path.join(ROOT, "design", "tiles", "trek_adirondack_02.json")
OUT = os.path.join(ROOT, "TrekShuttle", "42", "media", "textures")
ART = os.path.join(ROOT, "design", "art", "installations")
CW, CH = 128, 256

KITS = {"WarpCoreKit": ("warp_core", "W"), "ReplicatorKit": ("replicator", "W"),
        "EMHKit": ("emh_station", "W")}


def tile(sheet, i):
    return sheet.crop(((i % 8) * CW, (i // 8) * CH, (i % 8) * CW + CW, (i // 8) * CH + CH))


def machine(sheet, squares):
    """The machine's tiles composed as the game draws them, trimmed."""
    nx = max(x for x, _, _ in squares) + 1
    ny = max(y for _, y, _ in squares) + 1
    canvas = Image.new("RGBA", (64 * (nx + ny) + 128, 32 * (nx + ny) + 256), (0, 0, 0, 0))
    ox, oy = 64 * ny, 0
    for x, y, i in sorted(squares, key=lambda t: (t[0] + t[1], t[0])):
        canvas.alpha_composite(tile(sheet, i), (ox + 64 * (x - y), oy + 32 * (x + y)))
    return canvas.crop(canvas.getbbox())


def icon(sheet, squares):
    img = machine(sheet, squares)
    out = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(out)
    # The crate it comes in: a grey slab under the machine's feet.
    d.polygon([(6, 50), (32, 38), (58, 50), (32, 62)], fill=(96, 98, 104, 255))
    d.polygon([(6, 50), (32, 62), (32, 64), (6, 52)], fill=(64, 66, 70, 255))
    d.polygon([(58, 50), (32, 62), (32, 64), (58, 52)], fill=(78, 80, 86, 255))
    scale = min(48 / img.width, 56 / img.height)
    img = img.resize((max(1, int(img.width * scale)), max(1, int(img.height * scale))), Image.LANCZOS)
    out.alpha_composite(img, ((64 - img.width) // 2, 56 - img.height))
    return out


def main():
    sheet = Image.open(SHEET).convert("RGBA")
    index = json.load(open(INDEX))
    os.makedirs(ART, exist_ok=True)
    row = Image.new("RGBA", (3 * 64 + 3 * 32 + 16, 72), (44, 46, 54, 255))
    for k, (name, (piece, facing)) in enumerate(KITS.items()):
        im = icon(sheet, index[piece]["facings"][facing])
        im.save(os.path.join(OUT, "Item_TREK_%s.png" % name))
        row.alpha_composite(im, (k * 64, 4))
        row.alpha_composite(im.resize((32, 32), Image.LANCZOS), (3 * 64 + 8 + k * 32, 20))
        print("wrote Item_TREK_%s.png" % name)
    row.save(os.path.join(ART, "kits_sheet.png"))


if __name__ == "__main__":
    main()
