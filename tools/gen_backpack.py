"""Generates the Starfleet field pack: texture, icon, clothing XMLs and the sheet.

    python tools/gen_backpack.py TrekShuttle/42

One bag, on a **vanilla rig**, the uniforms' route (`gen_uniform.py`): a worn
backpack in build 42 is an item script, a clothing XML, a GUID row and a
256x256 PNG. Nothing here is modelled, rigged or skinned.

The rig is vanilla's hiking bag (`Bag_NormalHikingBag`): worn
`skinned\\backpacks\\m_hikingbag` / `f_hikingbag`, carried
`HikingBag_RHand` / `_LHand`, and on the ground `HikingBag_Ground`, which
names no texture of its own and so wears whatever the item's clothing does.
It was picked from renders of every vanilla pack the previewer can read
(design/art/backpack/): the plainest outer face, one front pocket, a lid.

Why the texture is recoloured rather than painted
-------------------------------------------------
The uniforms are painted from the mesh because vanilla's boilersuit texture
carried the boilersuit's pockets and zip, and a uniform must not have them
(DEV_GUIDE, *One texture on two bodies*). A backpack's pockets, buckles and
webbing are the backpack -- so here the vanilla sheet's own shading is kept
and only its colours are replaced. Its texels come in two classes that a
single test separates: the blue fabric and everything else (grey webbing,
the lid, buckles, the dark mesh). Each class is mapped to its Starfleet
colour and keeps its own luminance, so folds, stitching and the mesh survive.

The delta is placed in world space
----------------------------------
The one thing that is not in the vanilla sheet is the Starfleet delta, and a
badge placed by eye in an auto-packed atlas lands on a strap (the EMH's
scanlines, the uniforms' combadge). Every texel is given the world position
it lands on (`gen_uniform.surface_map`), and the delta is drawn on the texels
**visible from behind** -- the outermost surface along +Z, which is the pack's
outer face (the rig's front is -Z, `gen_uniform.py`). Both bodies share the
one texture, so the delta is measured on the female rig as well and the
generator refuses if the two disagree about where it is.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from PIL import Image
from gen_uniform import surface_map, clothing_guid
from preview_model import render

PZ = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid"
PACKS = os.path.join(PZ, "media", "models_X", "Skinned", "BackPacks")
VANILLA_TEX = os.path.join(PZ, "media", "textures", "clothes", "bag",
                           "HikingBagBlue.png")
RIGS = ("M_HikingBag.X", "F_HikingBag.x")
HANDS = ("HikingBag_RHand.X", "HikingBag_LHand.X")

SIZE = 256            # every vanilla clothing texture
ICON = 64             # no AttachmentType, so 64 (DEV_GUIDE, the hotbar)

ITEM = "TrekBackpack"
TEXTURE = "clothes\\trek\\backpack"   # as the clothing XML names it

# --- colours -----------------------------------------------------------
# Charcoal body and Starfleet grey trim: the two-tone of the field kit, and
# deliberately lighter than the uniform's BLACK (31,31,37) so the pack reads
# against the back it is worn on rather than vanishing into it.
FABRIC = (52, 54, 63)
TRIM = (122, 126, 137)
GOLD = (216, 178, 76)       # gen_uniform.BADGE_GOLD: one gold in the mod
RIM = (38, 30, 14)          # the delta's edge, so it holds against the grey

# --- the delta, in world units on the rig --------------------------------
# On the lid's outer face, where the isometric camera looks at the pack most:
# from above and behind. Measured off design/art/backpack/grid.png, the rig
# rendered with its own world coordinates painted on. The main compartment
# below it carries the centre buckle strap, which would cut the badge in two.
DELTA_X = 0.0
DELTA_Y = 0.827
DELTA_W = 0.046       # base, full width
DELTA_H = 0.052
RIM_SCALE = 1.22      # the rim is the same shape, this much larger

# A texel is on the outer face when nothing covered lies behind it in +Z, to
# within this much. Binned over x and y at VIS_BIN.
VIS_BIN = 0.003
VIS_EPS = 0.012


def in_delta(x, y, scale=1.0):
    """True when (x, y) is inside the Starfleet delta, grown by `scale`.

    An arrowhead: straight sides from the apex to the base corners, and a
    concave notch cut up from the middle of the base.
    """
    hw = DELTA_W * 0.5 * scale
    h = DELTA_H * scale
    base = DELTA_Y - DELTA_H * 0.5 - (h - DELTA_H) * 0.5
    u = (x - DELTA_X) / hw          # -1 .. 1 across
    v = (y - base) / h              # 0 at the base, 1 at the apex
    if v < 0.0 or v > 1.0 or abs(u) > 1.0:
        return False
    if abs(u) > 1.0 - v:            # outside the sides
        return False
    notch = 0.42 * (1.0 - abs(u)) ** 1.6
    return v >= notch


def visible_from_behind(pos, covered):
    """Per texel, True when it is the outermost surface along +Z."""
    front = {}
    for i, c in enumerate(covered):
        if not c:
            continue
        x, y, z = pos[i]
        key = (int(math.floor(x / VIS_BIN)), int(math.floor(y / VIS_BIN)))
        if z > front.get(key, -1e9):
            front[key] = z
    vis = bytearray(len(covered))
    for i, c in enumerate(covered):
        if not c:
            continue
        x, y, z = pos[i]
        key = (int(math.floor(x / VIS_BIN)), int(math.floor(y / VIS_BIN)))
        vis[i] = 1 if z >= front[key] - VIS_EPS else 0
    return vis


def badge_map(rig):
    """{texel: 'gold' | 'rim'} for one rig."""
    pos, covered = surface_map(os.path.join(PACKS, rig), SIZE, SIZE)
    vis = visible_from_behind(pos, covered)
    out = {}
    for i in range(SIZE * SIZE):
        if not vis[i]:
            continue
        x, y, _z = pos[i]
        if in_delta(x, y):
            out[i] = "gold"
        elif in_delta(x, y, RIM_SCALE):
            out[i] = "rim"
    return out, sum(covered)


def recolour(src):
    """The vanilla sheet in Starfleet colours, keeping its own shading."""
    px = src.load()
    blue, grey = [], []
    for y in range(SIZE):
        for x in range(SIZE):
            r, g, b, a = px[x, y]
            if a == 0:
                continue
            lum = 0.30 * r + 0.59 * g + 0.11 * b
            (blue if b > max(r, g) + 20 else grey).append(lum)
    if len(blue) < 5000 or len(grey) < 5000:
        raise SystemExit(
            f"the vanilla sheet split into {len(blue)} fabric and {len(grey)} "
            f"trim texels; the colour test no longer matches it, and the pack "
            f"would come out one flat colour")
    # The mean of the brighter half, so the mesh and the shadows (which are
    # dark on purpose) do not drag the reference down and wash the rest out.
    def ref(values):
        values = sorted(values)
        top = values[len(values) // 2:]
        return sum(top) / len(top)
    ref_blue, ref_grey = ref(blue), ref(grey)

    out = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    po = out.load()
    for y in range(SIZE):
        for x in range(SIZE):
            r, g, b, a = px[x, y]
            if a == 0:
                po[x, y] = (r, g, b, 0)
                continue
            lum = 0.30 * r + 0.59 * g + 0.11 * b
            if b > max(r, g) + 20:
                base, f = FABRIC, lum / ref_blue
            else:
                base, f = TRIM, lum / ref_grey
            po[x, y] = tuple(max(0, min(255, int(round(c * f)))) for c in base) + (a,)
    return out, len(blue), len(grey)


def paint(tex_out):
    src = Image.open(VANILLA_TEX).convert("RGBA")
    if src.size != (SIZE, SIZE):
        raise SystemExit(f"{VANILLA_TEX} is {src.size}, not {SIZE}x{SIZE}")
    img, n_fabric, n_trim = recolour(src)

    maps = []
    for rig in RIGS:
        m, covered = badge_map(rig)
        if covered < 20000:
            raise SystemExit(
                f"{rig}: only {covered} texels are covered by the mesh -- the "
                f"UVs are not being read, so the delta check proves nothing "
                f"(DEV_GUIDE: a check against an empty set is not a check)")
        maps.append(m)
    male, female = maps
    gold_m = {i for i, k in male.items() if k == "gold"}
    gold_f = {i for i, k in female.items() if k == "gold"}
    if len(gold_m) < 60:
        raise SystemExit(
            f"the delta covers {len(gold_m)} texels on the male rig; it is not "
            f"on the pack's outer face any more (DELTA_Y {DELTA_Y}), and the "
            f"pack would ship without its badge")
    agree = len(gold_m & gold_f) / float(len(gold_m | gold_f))
    print(f"  fabric {n_fabric} texels, trim {n_trim}; delta {len(gold_m)} "
          f"texels (M) / {len(gold_f)} (F), {agree * 100:.0f}% the same")
    if agree < 0.6:
        raise SystemExit(
            f"the delta lands on different texels on the two bodies "
            f"({agree * 100:.0f}% shared). They wear one texture, so one of "
            f"them would carry a scrambled badge.")

    # The male rig decides; the female's own rim fills in where hers is wider.
    po = img.load()
    for i, kind in list(female.items()) + list(male.items()):
        x, y = i % SIZE, i // SIZE
        a = po[x, y][3]
        po[x, y] = (GOLD if kind == "gold" else RIM) + (a,)
    img.save(tex_out)
    return len(gold_m)


def icon(mesh, texture, out_path, scratch, yaw):
    """The icon rendered from the worn rig, trimmed and box-filtered.

    Keyed by exact match on the previewer's backdrop, as gen_uniform.py does:
    a colour ramp would eat the charcoal.
    """
    big = os.path.join(scratch, "backpack_icon_big.png")
    render(mesh, texture, big, size=ICON * 6, yaw_deg=yaw)
    im = Image.open(big).convert("RGB")
    w, h = im.size
    px = im.load()
    bg = (28, 30, 36)
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            if px[x, y] != bg:
                xs.append(x)
                ys.append(y)
    if not xs:
        raise SystemExit(f"{out_path}: the render is empty")
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    side = max(maxx - minx + 1, maxy - miny + 1)
    ox = minx - (side - (maxx - minx + 1)) // 2
    oy = miny - (side - (maxy - miny + 1)) // 2
    step = side / float(ICON)
    out = Image.new("RGBA", (ICON, ICON), (0, 0, 0, 0))
    po = out.load()
    filled = 0
    for y in range(ICON):
        for x in range(ICON):
            r = g = b = n = 0
            for sy in range(int(y * step), int((y + 1) * step)):
                for sx in range(int(x * step), int((x + 1) * step)):
                    X, Y = ox + sx, oy + sy
                    if 0 <= X < w and 0 <= Y < h and px[X, Y] != bg:
                        c = px[X, Y]
                        r, g, b, n = r + c[0], g + c[1], b + c[2], n + 1
            if n:
                po[x, y] = (r // n, g // n, b // n, 255)
                filled += 1
    out.save(out_path)
    return filled / float(ICON * ICON)


# --- the clothing XMLs --------------------------------------------------
# Three, because vanilla's bag is three: worn, and one for each hand it is
# carried in (ReplaceInPrimaryHand / ReplaceInSecondHand). Pointing the hands
# at vanilla's Bag_HikingBag_RHand would carry a blue hiking bag.
CLOTHING = (
    (ITEM, "skinned\\backpacks\\m_hikingbag", "skinned\\backpacks\\f_hikingbag"),
    (ITEM + "_RHand", "media\\models_X\\Skinned\\BackPacks\\HikingBag_RHand.X",
     "media\\models_X\\Skinned\\BackPacks\\HikingBag_RHand.X"),
    (ITEM + "_LHand", "media\\models_X\\Skinned\\BackPacks\\HikingBag_LHand.X",
     "media\\models_X\\Skinned\\BackPacks\\HikingBag_LHand.X"),
)


def write_clothing(root):
    out_dir = os.path.join(root, "media", "clothing", "clothingItems")
    os.makedirs(out_dir, exist_ok=True)
    rows = []
    for stem, male, female in CLOTHING:
        guid = clothing_guid(stem)
        lines = ['<?xml version="1.0" encoding="utf-8"?>',
                 "<clothingItem>",
                 f"\t<m_MaleModel>{male}</m_MaleModel>",
                 f"\t<m_FemaleModel>{female}</m_FemaleModel>",
                 f"\t<m_GUID>{guid}</m_GUID>",
                 "\t<m_Static>false</m_Static>",
                 "\t<m_AllowRandomHue>false</m_AllowRandomHue>",
                 # Starfleet issue: no random tint on the ship's own kit.
                 "\t<m_AllowRandomTint>false</m_AllowRandomTint>",
                 "\t<m_AttachBone></m_AttachBone>",
                 f"\t<textureChoices>{TEXTURE}</textureChoices>",
                 "</clothingItem>"]
        with open(os.path.join(out_dir, stem + ".xml"), "w",
                  encoding="utf-8", newline="\r\n") as fh:
            fh.write("\n".join(lines) + "\n")
        rows.append((f"media/clothing/clothingItems/{stem}.xml", guid))
    merge_guid_table(root, rows)
    print(f"  {len(rows)} clothing XMLs and their rows in media/fileGuidTable.xml")


def merge_guid_table(root, rows):
    """Adds or replaces these rows, keeping every other: gen_uniform.py and
    gen_species.py write the same file, and none may orphan another's."""
    import re
    path = os.path.join(root, "media", "fileGuidTable.xml")
    existing = []
    if os.path.isfile(path):
        existing = re.findall(r"<path>(.*?)</path>\s*<guid>(.*?)</guid>",
                              open(path, encoding="utf-8").read(), re.S)
    mine = {p for p, _ in rows}
    keep = [(p, g) for p, g in existing if p not in mine]
    table = ['<?xml version="1.0" encoding="utf-8"?>', "<fileGuidTable>"]
    for p, g in keep + list(rows):
        table += ["\t<files>", f"\t\t<path>{p}</path>",
                  f"\t\t<guid>{g}</guid>", "\t</files>"]
    table.append("</fileGuidTable>")
    with open(path, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write("\n".join(table) + "\n")


def sheet(tex, art, scratch):
    """Both bodies from behind and three-quarter, and a hand: the vet."""
    cells = []
    for rig in RIGS:
        for yaw in (180, 145, 0):
            out = os.path.join(scratch, f"pack_{rig.split('.')[0]}_{yaw}.png")
            render(os.path.join(PACKS, rig), tex, out, size=300, yaw_deg=yaw)
            cells.append(out)
    out = os.path.join(scratch, "pack_hand.png")
    render(os.path.join(PACKS, HANDS[0]), tex, out, size=300, yaw_deg=145)
    cells.append(out)
    cols, pad = 4, 6
    rows = (len(cells) + cols - 1) // cols
    W = Image.new("RGB", (pad + cols * (300 + pad), pad + rows * (300 + pad)),
                  (28, 30, 36))
    for i, p in enumerate(cells):
        r, c = divmod(i, cols)
        W.paste(Image.open(p).convert("RGB"), (pad + c * (300 + pad),
                                               pad + r * (300 + pad)))
    dest = os.path.join(art, "backpack_sheet.png")
    W.save(dest)
    print(f"  sheet {dest}")


def build(root, scratch):
    tex_dir = os.path.join(root, "media", "textures", "clothes", "trek")
    art = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "design", "art", "backpack")
    for d in (tex_dir, art, scratch):
        os.makedirs(d, exist_ok=True)
    tex = os.path.join(tex_dir, "backpack.png")
    paint(tex)
    fill = icon(os.path.join(PACKS, RIGS[0]), tex,
                os.path.join(root, "media", "textures", "Item_TREK_Backpack.png"),
                scratch, yaw=150)
    print(f"  icon Item_TREK_Backpack.png {fill * 100:.0f}% filled")
    write_clothing(root)
    sheet(tex, art, scratch)


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42"
    scratch = os.environ.get("TREK_SCRATCH") or os.path.join(root, "_scratch")
    os.makedirs(scratch, exist_ok=True)
    print("backpack:")
    build(root, scratch)
