"""The Adirondack's tiles, made into what the game loads: a texture pack and a tiledef.

    python tools/gen_adirondack_pack.py

Writes, from design/tiles/2x/trek_adirondack_01.png and _02.png,

  TrekShuttle/42/media/texturepacks/trek_adirondack.pack   PZPK version 1
  TrekShuttle/42/media/trek_adirondack.tiles              tdef version 1

and mod.info must carry `pack=trek_adirondack` and
`tiledef=trek_adirondack 7461` (tests/test_assets.py checks both).

Both formats were read out of real files before a byte was written -- Bandits
Week One's and Horse Mod's, and vanilla's newtiledefinitions.tiles -- and both
readers in this file parse those end to end:

  .pack   "PZPK", int version=1, int pages; per page: str name, int entries,
          int mask(1); per entry: str name, int x, y, w, h (in the page),
          int ox, oy (trim offset in the full cell), int fullW, fullH; then
          int length and that many bytes of PNG. Strings are int length + bytes.
  .tiles  "tdef", int version=1, int tilesets; per tileset: name\\n,
          image\\n, int cols, rows, id, count; per tile (every cell, empty
          ones too): int n, then n pairs of key\\n value\\n.

A sprite in the game is `<sheet>_<index>` with no zero padding -- BuildingEd
pads (`_000`), the engine does not.

**Properties are copied from a vanilla tile doing the same job**, then named
and grouped as ours: walls from industry_01 (the hull's own wall set), floors
from floors_interior_tilesandwood_01, doors from fixtures_doors_01 (whose
closed/open layout, W N W-open N-open, ours already follows), wall panels from
security_01's monitors, beds from furniture_bedding_01, and so on. What a
vanilla tile says is what the engine is known to act on.

Two properties are deliberately never copied: `lightswitch` (DEV_GUIDE: a
sprite carrying it is rebuilt as a real IsoLightSwitch on the next load) and
`CustomItem` (it would name a vanilla item as what you get for picking ours up).

`Facing` is the direction the front looks, not the wall it backs onto: our
W-backed pieces face E, as vanilla's W-backed bed does.
"""
import io
import json
import os
import re
import struct
import sys

from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "design", "tiles", "2x")
MEDIA = os.path.join(ROOT, "TrekShuttle", "42", "media")
PACK = os.path.join(MEDIA, "texturepacks", "trek_adirondack.pack")
TILES = os.path.join(MEDIA, "trek_adirondack.tiles")
VANILLA_DEFS = os.environ.get(
    "PZ_TILEDEFS",
    r"C:/Program Files (x86)/Steam/steamapps/common/ProjectZomboid/media/newtiledefinitions.tiles")
SHEETS = ["trek_adirondack_01", "trek_adirondack_02", "trek_adirondack_03"]
TILEDEF_NUMBER = 7461
PAGE = 2048
CW, CH = 128, 256
NEVER = {"lightswitch", "streetlight", "CustomItem", "PaintingType", "IsPaintable"}


# --- the formats -----------------------------------------------------------------------------

def read_tiledefs(path):
    b = open(path, "rb").read()
    o = 12
    n = struct.unpack_from("<i", b, 8)[0]
    out = {}

    def i32():
        nonlocal o
        v = struct.unpack_from("<i", b, o)[0]
        o += 4
        return v

    def line():
        nonlocal o
        e = b.index(b"\n", o)
        v = b[o:e].decode("latin1")
        o = e + 1
        return v

    for _ in range(n):
        name, img = line(), line()
        cols, rows, tid, count = i32(), i32(), i32(), i32()
        tiles = []
        for _ in range(count):
            k = i32()
            tiles.append(dict((line(), line()) for _ in range(k)))
        out[name] = dict(image=img, cols=cols, rows=rows, id=tid, tiles=tiles)
    if o != len(b):
        raise SystemExit("%s: read %d of %d bytes" % (path, o, len(b)))
    return out


def write_tiledefs(path, tilesets):
    out = io.BytesIO()
    out.write(b"tdef")
    out.write(struct.pack("<ii", 1, len(tilesets)))
    for ts in tilesets:
        out.write((ts["name"] + "\n").encode("latin1"))
        out.write((ts["image"] + "\n").encode("latin1"))
        out.write(struct.pack("<iiii", ts["cols"], ts["rows"], ts["id"], len(ts["tiles"])))
        for props in ts["tiles"]:
            out.write(struct.pack("<i", len(props)))
            for k, v in props:
                out.write(("%s\n%s\n" % (k, v)).encode("latin1"))
    with open(path, "wb") as f:
        f.write(out.getvalue())


def read_pack(path):
    b = open(path, "rb").read()
    o = 4

    def i32():
        nonlocal o
        v = struct.unpack_from("<i", b, o)[0]
        o += 4
        return v

    def s():
        nonlocal o
        n = i32()
        v = b[o:o + n].decode("latin1")
        o += n
        return v

    if b[:4] != b"PZPK" or i32() != 1:
        raise SystemExit("%s is not a PZPK version 1 pack" % path)
    pages = []
    for _ in range(i32()):
        name, n, mask = s(), i32(), i32()
        entries = [(s(), [i32() for _ in range(8)]) for _ in range(n)]
        size = i32()
        png = b[o:o + size]
        o += size
        pages.append(dict(name=name, mask=mask, entries=entries, png=png))
    if o != len(b):
        raise SystemExit("%s: read %d of %d bytes" % (path, o, len(b)))
    return pages


def write_pack(path, pages):
    out = io.BytesIO()
    out.write(b"PZPK")

    def i32(v):
        out.write(struct.pack("<i", v))

    def s(v):
        v = v.encode("latin1")
        i32(len(v))
        out.write(v)

    i32(1)
    i32(len(pages))
    for pg in pages:
        s(pg["name"])
        i32(len(pg["entries"]))
        i32(1)
        for name, vals in pg["entries"]:
            s(name)
            for v in vals:
                i32(v)
        buf = io.BytesIO()
        pg["image"].save(buf, "PNG", optimize=True)
        i32(len(buf.getvalue()))
        out.write(buf.getvalue())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "wb") as f:
        f.write(out.getvalue())


# --- packing the sprites -----------------------------------------------------------------------

def sprites():
    """Every non-empty cell of both sheets, trimmed to its pixels."""
    out = []
    for sheet in SHEETS:
        im = Image.open(os.path.join(SRC, sheet + ".png")).convert("RGBA")
        rows = im.height // CH
        for i in range(rows * 8):
            cell = im.crop(((i % 8) * CW, (i // 8) * CH, (i % 8) * CW + CW, (i // 8) * CH + CH))
            box = cell.split()[3].getbbox()
            if box:
                out.append(("%s_%d" % (sheet, i), cell.crop(box), box[0], box[1]))
    return out


def pack_pages(items):
    """Shelf-pack trimmed sprites, tallest first, into PAGE x PAGE pages."""
    items = sorted(items, key=lambda t: -t[1].height)
    pages, page, x, y, shelf = [], None, 0, 0, 0
    for name, img, ox, oy in items:
        w, h = img.size
        if page is None or x + w > PAGE:
            x, y, shelf = 0, y + shelf, 0
        if page is None or y + h > PAGE:
            page = dict(name="trek_adirondack%d" % len(pages), image=Image.new("RGBA", (PAGE, PAGE)), entries=[])
            pages.append(page)
            x, y, shelf = 0, 0, 0
        page["image"].paste(img, (x, y))
        page["entries"].append((name, [x, y, w, h, ox, oy, CW, CH]))
        x += w + 1
        shelf = max(shelf, h + 1)
    for pg in pages:
        box = pg["image"].getbbox()
        if box:
            pg["image"] = pg["image"].crop((0, 0, PAGE, box[3]))
    return pages


# --- the properties ------------------------------------------------------------------------------

def vanilla(defs, sheet, i):
    return dict(defs[sheet]["tiles"][i])


def ours(props, **extra):
    p = {k: v for k, v in props.items() if k not in NEVER}
    p.update({k: v for k, v in extra.items() if v is not None})
    return sorted(p.items())


FACE = {"W": "E", "N": "S", "E": "W", "S": "N"}


def sheet01_props(defs):
    s01 = "trek_adirondack_01"
    props = {}

    def wall(i, src, name):
        p = vanilla(defs, "industry_01", src)
        if "CornerNorthWall" in p:
            base = i - 2
            p["CornerNorthWall"] = "%s_%d" % (s01, base + 1)
            p["CornerWestWall"] = "%s_%d" % (s01, base)
        props[i] = ours(p, CustomName=name)

    for off, name in ((0, "Bulkhead"), (16, "Viewport")):
        for k in range(4):
            wall(off + k, k, name)
    for i, src in ((10, 10), (11, 11)):
        props[i] = ours(vanilla(defs, "industry_01", src), CustomName="Bulkhead")
    floor = vanilla(defs, "floors_interior_tilesandwood_01", 18)
    for k in ("CanBreak", "IsMoveAble", "PickUpLevel", "PickUpTool", "PickUpWeight", "PlaceTool", "MoveType"):
        floor.pop(k, None)
    props[24] = ours(floor, CustomName="Carpet", Material="Fabric")
    props[25] = ours(floor, CustomName="Deck Plate", Material="Metal")
    for i, src in ((32, 0), (33, 1), (34, 2), (35, 3)):
        p = vanilla(defs, "fixtures_doors_01", src)
        p["Material2"] = "Metal"
        p["MaterialType"] = "Metal_Light"
        # The engine plays DoorSound + Open / Close on a toggle, on every
        # client (sounds in trekshuttle.txt, tools/gen_door_sound.py).
        p["DoorSound"] = "TrekDoor"
        props[i] = ours(p, CustomName="Sliding Door")
    for i, src in ((40, 5), (41, 4)):
        p = vanilla(defs, "security_01", src)
        props[i] = ours(p, CustomName="Wall Display", GroupName="Starfleet")
    return props


def sheet02_props(defs, index):
    bed = vanilla(defs, "furniture_bedding_01", 2)
    locker = vanilla(defs, "furniture_storage_02", 11)
    chair = vanilla(defs, "carpentry_01", 36)
    table = vanilla(defs, "carpentry_01", 24)
    wallthing = vanilla(defs, "security_01", 4)
    for p in (bed, locker, chair, table, wallthing):
        for k in ("SpriteGridPos", "Facing", "GroupName", "CustomName", "chairS", "ForceSingleItem"):
            p.pop(k, None)
    props = {}
    for name, rec in index.items():
        use = rec.get("use", {})
        pretty = name.replace("_", " ").title()
        for facing, squares in rec["facings"].items():
            multi = len(squares) > 1
            for x, y, i in squares:
                if rec["layer"] in ("WallFurniture", "Walls"):
                    base = dict(wallthing)
                elif "bed" in use:
                    base = dict(bed, BedType=use["bed"])
                elif use.get("seat"):
                    base = dict(chair)
                    base["chair" + FACE[facing]] = ""
                elif use.get("stove"):
                    # A real oven's properties (IsoType IsoStove, container
                    # stove): the galley range is placed as an IsoStove
                    # (FARMING.md 3), so everything vanilla cooks in an oven
                    # works in it.
                    base = vanilla(defs, "appliances_cooking_01", 4)
                    for k in ("GroupName", "CustomName", "Facing", "IsMoveAble", "PickUpLevel",
                              "PickUpTool", "PickUpWeight", "PlaceTool"):
                        base.pop(k, None)
                elif use.get("tray"):
                    # A raised planter a crop grows on (FARMING.md 6.1):
                    # walked round, not sat on or stood on; nothing else may
                    # be placed on it, and never the vegetation flags, which
                    # vanilla farming reads as weeds.
                    base = dict(table)
                    base.pop("IsTable", None)
                    # Not a thing to carry off: taking a tray apart would take
                    # its crop with it (the first play-test offered Disassemble).
                    for k in ("IsMoveAble", "CanScrap", "CanBreak", "PickUpLevel", "PickUpTool",
                              "PickUpWeight", "PlaceTool"):
                        base.pop(k, None)
                elif "container" in use:
                    base = dict(locker, container=use["container"])
                else:
                    base = dict(table)
                    base.pop("IsTable", None)
                if name == "transporter_pad":
                    # You arrive standing on it: a raised dais, not an obstacle.
                    for k in ("solidtrans", "solid", "BlocksPlacement"):
                        base.pop(k, None)
                props[i] = ours(base, CustomName=pretty, GroupName="Starfleet " + rec["area"].title(),
                                Facing=FACE[facing],
                                SpriteGridPos=("%d,%d" % (x, y)) if multi else None)
    return props


def sheet03_props(index):
    """The crop growth sprites: what vanilla's own stage tiles carry, minus
    attachedFloor -- ours stand up in a tray, not flat on the ground."""
    props = {}
    for crop, tables in index.items():
        if crop == "_soil":
            # The primed tray's soil: something to see, nothing to block.
            props[tables] = [("CustomName", "Growing Medium")]
            continue
        for table in tables.values():
            for i in table:
                props[i] = [("BlocksPlacement", "")]
    return props


# --- sitting and lying down ----------------------------------------------------------

SEATING = os.path.join(ROOT, "TrekShuttle", "common", "media", "seating.txt")
VANILLA_SEATING = os.environ.get(
    "PZ_SEATING",
    r"C:/Program Files (x86)/Steam/steamapps/common/ProjectZomboid/media/seating.txt")

# Where a character sits on a piece is not a tile property: build 42 reads it
# from seating.txt (zombie.seating.SeatingManager), by tileset and column/row.
# A piece with no entry is one the game walks you *beside* and sits you on the
# floor (ISWorldObjectContextMenu.onRestPathFailed) -- what the first play-test
# found. SeatingManager.init() reads it from each mod's **common/media**, never
# from 42/media, so that is where this goes.
#
# Each of ours copies the entry of the vanilla tile it stands in for, matched
# by the tiledef's Facing and SpriteGridPos: the same shape of piece, facing
# the same way, the same square of it. Tuned vanilla numbers, not guesses.
SEAT_ANALOGS = {
    # hard chairs
    "desk_chair": ("carpentry_01", range(36, 40)),
    "bridge_chair": ("carpentry_01", range(36, 40)),
    "bar_stool": ("carpentry_01", range(36, 40)),
    # upholstered
    "armchair": ("furniture_seating_indoor_01", range(8, 12)),
    "lounge_chair": ("furniture_seating_indoor_01", range(8, 12)),
    "captain_chair": ("furniture_seating_indoor_01", range(8, 12)),
    "sofa": ("furniture_seating_indoor_01", range(0, 8)),
    # beds: the single and double frames, every facing
    "bed": ("furniture_bedding_01", range(64, 72)),
    "biobed": ("furniture_bedding_01", range(64, 72)),
    "bed_double": ("furniture_bedding_01", list(range(4, 8)) + list(range(12, 24))),
    # one square: sit on the edge as you would on the head of a single bed
    "bunk": ("furniture_bedding_01", range(64, 72)),
}


def vanilla_seats(path=VANILLA_SEATING):
    """tileset -> index -> the text of that tile's position blocks."""
    src = open(path, encoding="utf-8").read()
    out = {}
    for m in re.finditer(r"tileset\s*\{\s*name\s*=\s*([\w]+),", src):
        name = m.group(1)
        i, depth = src.index("{", m.start()), 0
        j = i
        while True:
            if src[j] == "{":
                depth += 1
            elif src[j] == "}":
                depth -= 1
                if depth == 0:
                    break
            j += 1
        block = src[i:j]
        tiles = out.setdefault(name, {})
        for t in re.finditer(r"tile\s*\{\s*xy\s*=\s*(\d+)\s+(\d+),", block):
            k, d = block.index("{", t.start()), 0
            e = k
            while True:
                if block[e] == "{":
                    d += 1
                elif block[e] == "}":
                    d -= 1
                    if d == 0:
                        break
                e += 1
            body = block[t.end():e]
            tiles[int(t.group(1)) + 8 * int(t.group(2))] = body.strip("\n")
    return out


def write_seating(defs, index, ours):
    seats = vanilla_seats()
    # The header comment sits inside the block, where vanilla's comments are.
    lines = ["seating", "{", "    VERSION = 3,", "",
             "    /* GENERATED by tools/gen_adirondack_pack.py: each tile copies the",
             "       vanilla tile it stands in for (SEAT_ANALOGS). Do not edit. */",
             "", "    tileset", "    {",
             "        name = trek_adirondack_02,"]
    count, missing = 0, []
    for piece, (vts, candidates) in SEAT_ANALOGS.items():
        rec = index.get(piece)
        if not rec:
            continue
        for squares in rec["facings"].values():
            for _, _, i in squares:
                p = ours[i]
                face, grid = p.get("Facing"), p.get("SpriteGridPos")
                match = None
                for v in candidates:
                    vp = defs[vts]["tiles"][v]
                    if vp.get("Facing") != face or v not in seats.get(vts, {}):
                        continue
                    if grid is None or piece == "bunk":
                        # A one-square piece: the head of the frame.
                        if vp.get("SpriteGridPos") in (None, "0,0"):
                            match = v
                            break
                    elif vp.get("SpriteGridPos") == grid:
                        match = v
                        break
                if match is None:
                    missing.append("%s %d (%s %s)" % (piece, i, face, grid))
                    continue
                lines += ["", "        /* %s: %s_%d */" % (piece, vts, match), "        tile", "        {",
                          "            xy = %d %d," % (i % 8, i // 8)]
                lines += [seats[vts][match].rstrip()]
                lines += ["        }"]
                count += 1
    lines += ["    }", "}", ""]
    if missing:
        raise SystemExit("no vanilla seat to copy for: " + ", ".join(missing))
    os.makedirs(os.path.dirname(SEATING), exist_ok=True)
    with open(SEATING, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines))
    # Read back with the same reader: every tile written is a tile found.
    back = vanilla_seats(SEATING).get("trek_adirondack_02", {})
    if len(back) != count:
        raise SystemExit("seating.txt round trip: wrote %d tiles, read %d" % (count, len(back)))
    return count


def main():
    defs = read_tiledefs(VANILLA_DEFS)
    with open(os.path.join(ROOT, "design", "tiles", "trek_adirondack_02.json")) as f:
        index = json.load(f)
    with open(os.path.join(ROOT, "design", "tiles", "trek_adirondack_03.json")) as f:
        crops = json.load(f)
    per_sheet = {SHEETS[0]: sheet01_props(defs), SHEETS[1]: sheet02_props(defs, index),
                 SHEETS[2]: sheet03_props(crops)}
    tilesets = []
    for k, sheet in enumerate(SHEETS, start=1):
        rows = Image.open(os.path.join(SRC, sheet + ".png")).height // CH
        tiles = [per_sheet[sheet].get(i, []) for i in range(rows * 8)]
        tilesets.append(dict(name=sheet, image=sheet + ".png", cols=8, rows=rows, id=k, tiles=tiles))
    write_tiledefs(TILES, tilesets)

    items = sprites()
    pages = pack_pages(items)
    write_pack(PACK, pages)

    # Read both back with the same readers that parse vanilla's and other
    # mods' files end to end: a file only this writer can read is not proof.
    back = read_tiledefs(TILES)
    got = read_pack(PACK)
    named = sum(len(p["entries"]) for p in got)
    unprops = [e[0] for p in got for e in p["entries"]
               if not back[e[0].rsplit("_", 1)[0]]["tiles"][int(e[0].rsplit("_", 1)[1])]]
    if named != len(items):
        raise SystemExit("pack round trip lost sprites: %d of %d" % (named, len(items)))
    if unprops:
        raise SystemExit("sprites with no properties: %s" % ", ".join(unprops[:10]))
    seats = write_seating(defs, index, back["trek_adirondack_02"]["tiles"])
    print("seating: %d tiles, copied from vanilla's" % seats)
    print("pack: %d sprites on %d page(s), %d KB; tiles: %d tilesets, %d defined"
          % (named, len(got), os.path.getsize(PACK) // 1024, len(back),
             sum(1 for ts in back.values() for t in ts["tiles"] if t)))


if __name__ == "__main__":
    main()
