"""Builds the trait and profession icons (TRAITS.md).

    python tools/gen_trait_icons.py TrekShuttle/42

Three kinds:

  * **Generated art** -- the species, the anyone-can-take traits and the seven
    professions -- from Gemini raws in design/art/traits/, keyed off magenta
    by tools/key_icon.py. A trait icon is **18x18** (every vanilla one is) and
    a profession icon **64x64** (profession_tailor.png is), each into the
    folder the engine looks in: media/ui/Traits/trait_<path>.png and
    media/textures/profession_trek_<path>.png.
  * **Rank pips**, drawn here: gold for a full pip, a dark hollow for a half,
    one to three of them, the way the collar of a duty uniform reads.
  * **Division badges**, drawn here: the division's colour from UNIFORMS.md
    (command red, operations gold, sciences teal) under one white glyph.

The pips and badges are drawn at eight times the size and brought down, so
the edges are smooth without being mush. An 18-pixel icon is five pips wide
at most; anything finer than that is not there when the game draws it.

A raw the model wrapped in a white frame -- it does that -- is cropped to its
magenta first. key_icon samples its key off the border ring, and a white ring
would be read as the backdrop.
"""
import os
import sys
import tempfile

from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import key_icon  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = os.path.join(ROOT, "design", "art", "traits")

GENERATED = ["vulcan", "klingon", "andorian", "betazoid", "trill", "bajoran",
             "talaxian", "orion", "android", "exborg", "transporterphobia",
             "realfoodonly", "spacesick", "starfleetacademy", "holohistorian", "turboliftphobia"]
PROFESSIONS = ["starfleet_command", "starfleet_helm", "starfleet_engineer",
               "starfleet_security", "starfleet_medical", "starfleet_science",
               "survey_specialist"]

# UNIFORMS.md's division colours.
RED, GOLD, TEAL = (170, 30, 35), (205, 160, 40), (30, 140, 150)
DIVISIONS = {
    "sf_command": (RED, "chevron"), "sf_helm": (RED, "arrow"),
    "sf_engineering": (GOLD, "wrench"), "sf_security": (GOLD, "shield"),
    "sf_medical": (TEAL, "cross"), "sf_science": (TEAL, "atom"),
    "sf_survey": (TEAL, "eye"),
}
# (full pips, half pips): ensign one, j.g. one and a half, and so on.
RANKS = {"rank_ensign": (1, 0), "rank_ltjg": (1, 1), "rank_lt": (2, 0),
         "rank_ltcmdr": (2, 1), "rank_cmdr": (3, 0)}

SS = 8           # supersampling factor for the drawn icons
TRAIT = 18
PROF = 64


def magenta_crop(path):
    """The raw cropped to its magenta, if the model framed it in something
    else. Returns a path to key."""
    img = Image.open(path).convert("RGB")
    w, h = img.size
    px = img.load()

    def is_key(p):
        r, g, b = p
        return r > 150 and b > 150 and g < 110

    xs, ys = [], []
    step = 4
    for y in range(0, h, step):
        for x in range(0, w, step):
            if is_key(px[x, y]):
                xs.append(x)
                ys.append(y)
    if not xs:
        return path
    box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
    if box[0] <= 8 and box[1] <= 8 and box[2] >= w - 8 and box[3] >= h - 8:
        return path
    # Scattered magenta-ish pixels in the art itself are not a backdrop.
    if (box[2] - box[0]) < w * 0.3 or (box[3] - box[1]) < h * 0.3:
        return path
    # Shave a few pixels so the frame's antialiased edge is not in the ring.
    box = (box[0] + 6, box[1] + 6, box[2] - 6, box[3] - 6)
    out = os.path.join(tempfile.gettempdir(), "trek_crop_" + os.path.basename(path) + ".png")
    img.crop(box).save(out)
    print(f"  {os.path.basename(path)}: framed; cropped to {box}")
    return out


def from_raw(name, size, out):
    raw = os.path.join(RAW, f"{name}_raw.jpg")
    if not os.path.isfile(raw):
        raise SystemExit(f"missing raw art: {raw}")
    tmp = os.path.join(tempfile.gettempdir(), f"trek_icon_{name}.png")
    key_icon.key(magenta_crop(raw), tmp)
    img = Image.open(tmp).convert("RGBA")
    if img.size != (size, size):
        img = img.resize((size, size), Image.LANCZOS)
        if size <= 32:
            # Brought down that far, an outline goes soft; a touch of
            # sharpening puts the silhouette back.
            img = img.filter(ImageFilter.UnsharpMask(radius=1, percent=60, threshold=2))
    img.save(out, optimize=True)


def pips(full, half):
    n = full + half
    s = TRAIT * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    # Three pips have to fit in eighteen pixels with a margin.
    r = int(s * (0.13 if n >= 3 else 0.18))
    gap = int(r * (0.5 if n >= 3 else 0.7))
    width = n * 2 * r + (n - 1) * gap
    x = (s - width) // 2 + r
    y = s // 2
    for i in range(n):
        box = (x - r, y - r, x + r, y + r)
        if i < full:
            d.ellipse(box, fill=(225, 185, 60, 255), outline=(90, 60, 10, 255), width=SS)
        else:
            d.ellipse(box, fill=(35, 30, 25, 255), outline=(225, 185, 60, 255), width=SS)
        x += 2 * r + gap
    return img.resize((TRAIT, TRAIT), Image.LANCZOS)


def badge(colour, glyph):
    s = TRAIT * SS
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    m = SS
    d.rounded_rectangle((m, m, s - m, s - m), radius=4 * SS, fill=colour + (255,),
                        outline=(20, 20, 20, 255), width=SS)
    w = (255, 255, 255, 255)
    c = s // 2
    u = s // 18            # one final pixel, in supersampled units
    if glyph == "chevron":
        d.line([(c - 5 * u, c + 3 * u), (c, c - 3 * u), (c + 5 * u, c + 3 * u)], fill=w, width=2 * u)
    elif glyph == "arrow":
        d.polygon([(c, c - 6 * u), (c + 5 * u, c + 4 * u), (c, c + 1 * u), (c - 5 * u, c + 4 * u)], fill=w)
    elif glyph == "wrench":
        d.line([(c - 4 * u, c + 4 * u), (c + 2 * u, c - 2 * u)], fill=w, width=2 * u)
        d.ellipse((c + 1 * u, c - 6 * u, c + 6 * u, c - 1 * u), outline=w, width=2 * u)
    elif glyph == "shield":
        d.polygon([(c - 5 * u, c - 5 * u), (c + 5 * u, c - 5 * u), (c + 5 * u, c),
                   (c, c + 6 * u), (c - 5 * u, c)], fill=w)
    elif glyph == "cross":
        d.rectangle((c - 1.5 * u, c - 5 * u, c + 1.5 * u, c + 5 * u), fill=w)
        d.rectangle((c - 5 * u, c - 1.5 * u, c + 5 * u, c + 1.5 * u), fill=w)
    elif glyph == "atom":
        d.ellipse((c - 6 * u, c - 2.5 * u, c + 6 * u, c + 2.5 * u), outline=w, width=u)
        d.ellipse((c - 2.5 * u, c - 6 * u, c + 2.5 * u, c + 6 * u), outline=w, width=u)
        d.ellipse((c - 1.5 * u, c - 1.5 * u, c + 1.5 * u, c + 1.5 * u), fill=w)
    elif glyph == "eye":
        d.ellipse((c - 6 * u, c - 3.5 * u, c + 6 * u, c + 3.5 * u), outline=w, width=u)
        d.ellipse((c - 2 * u, c - 2 * u, c + 2 * u, c + 2 * u), fill=w)
    return img.resize((TRAIT, TRAIT), Image.LANCZOS)


def sheet(paths, out):
    """Each icon at 1x and 4x on the inventory grey, for looking at."""
    bg = (39, 39, 39)
    cell = 80
    img = Image.new("RGB", (cell * len(paths), cell), bg)
    for i, p in enumerate(paths):
        ic = Image.open(p).convert("RGBA")
        big = ic.resize((ic.width * 3 if ic.width <= 18 else 54,) * 2, Image.NEAREST)
        box = Image.new("RGBA", big.size, bg + (255,))
        box.alpha_composite(big)
        img.paste(box.convert("RGB"), (i * cell + 4, 4))
        small = Image.new("RGBA", ic.size, bg + (255,))
        small.alpha_composite(ic)
        img.paste(small.convert("RGB"), (i * cell + 60, 58))
    img.save(out)


def main(mod):
    traits_dir = os.path.join(mod, "media", "ui", "Traits")
    tex = os.path.join(mod, "media", "textures")
    os.makedirs(traits_dir, exist_ok=True)
    made = []
    for name in GENERATED:
        out = os.path.join(traits_dir, f"trait_{name}.png")
        from_raw(name, TRAIT, out)
        made.append(out)
    for name, (colour, glyph) in DIVISIONS.items():
        out = os.path.join(traits_dir, f"trait_{name}.png")
        badge(colour, glyph).save(out, optimize=True)
        made.append(out)
    for name, (full, half) in RANKS.items():
        out = os.path.join(traits_dir, f"trait_{name}.png")
        pips(full, half).save(out, optimize=True)
        made.append(out)
    profs = []
    for name in PROFESSIONS:
        out = os.path.join(tex, f"profession_trek_{name}.png")
        from_raw(f"prof_{name}", PROF, out)
        profs.append(out)
    sheet(made, os.path.join(RAW, "traits_sheet.png"))
    sheet(profs, os.path.join(RAW, "professions_sheet.png"))
    print(f"{len(made)} trait icons, {len(profs)} profession icons")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else os.path.join(ROOT, "TrekShuttle", "42"))
