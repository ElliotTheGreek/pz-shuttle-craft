"""Put the Adirondack tileset where the Project Zomboid Modding Tools can use it.

    python tools/install_tilezed.py            # install / refresh
    python tools/install_tilezed.py --check    # report only, change nothing

Close TileZed and BuildingEd first: both read these files when they start and
may write them back when they close, over the top of anything added meanwhile.

What it does, and nothing else:

1. copies design/tiles/2x/<sheet>.png into the tools' Tiles/2x folder, which is
   where TileZed looks for every tileset (the TilesDirectory in its settings);
2. adds the sheet to ~/.TileZed/Tilesets.txt, with DoorW/DoorN meta-enums on
   the two closed doors exactly as vanilla marks fixtures_doors_01;
3. adds BuildingEd entries to ~/.TileZed/BuildingTiles.txt -- the bulkhead and
   the viewport wall under both interior and exterior walls, the carpet and the
   deck under floors, the sliding door under doors;
4. adds a "Starfleet - Adirondack" group to ~/.TileZed/BuildingFurniture.txt
   with the wall display, on the WallFurniture layer as vanilla's wall-hung
   shop signs are.

It is idempotent: an entry already present is left alone, so running it again
after regenerating the art only refreshes the PNG. The first run keeps a copy
of each config file as <name>.pretrek.
"""
import os
import json
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET = "trek_adirondack_01"          # structure: walls, floors, doors
FURN = "trek_adirondack_02"           # furniture, rendered from models
SHEETS = (SHEET, FURN)
SRCDIR = os.path.join(ROOT, "design", "tiles", "2x")
TOOLS = os.environ.get(
    "PZ_MODDING_TOOLS",
    r"D:/SteamLibrary/steamapps/common/Project Zomboid Modding Tools")
TILES = os.path.join(TOOLS, "Tiles", "2x")
CONF = os.path.join(os.path.expanduser("~"), ".TileZed")


def t(i):
    return "%s_%03d" % (SHEET, i)


def f(i):
    return "%s_%03d" % (FURN, i)


def rows_of(sheet):
    from PIL import Image
    return Image.open(os.path.join(SRCDIR, sheet + ".png")).size[1] // 256


def tileset_block(sheet):
    """A sheet's Tilesets.txt entry. Its size follows the PNG, which grows."""
    extra = DOOR_ENUMS if sheet == SHEET else ""
    return "tileset\n{\n    file = %s\n    size = 8,%d\n%s}\n" % (sheet, rows_of(sheet), extra)


DOOR_ENUMS = """    tile
    {
        xy = 0,4
        meta-enum = DoorW
    }
    tile
    {
        xy = 1,4
        meta-enum = DoorN
    }
"""


def wall_entry(w, n, nw, se):
    return (
        "    entry\n    {\n"
        "        West = %s\n        North = %s\n        NorthWest = %s\n"
        "        SouthEast = %s\n        WestWindow = \n        NorthWindow = \n"
        "        WestDoor = %s\n        NorthDoor = %s\n    }\n"
        % (t(w), t(n), t(nw), t(se), t(10), t(11)))


BUILDING = {
    "exterior_walls": wall_entry(0, 1, 2, 3) + wall_entry(16, 17, 18, 19),
    "interior_walls": wall_entry(0, 1, 2, 3) + wall_entry(16, 17, 18, 19),
    "floors": "".join("    entry\n    {\n        Floor = %s\n    }\n" % t(i) for i in (24, 25)),
    "doors": ("    entry\n    {\n        West = %s\n        North = %s\n"
              "        WestOpen = %s\n        NorthOpen = %s\n    }\n"
              % (t(32), t(33), t(34), t(35))),
}

def wall_piece(layer, w, n):
    return ("    furniture\n    {\n        layer = %s\n"
            "        entry\n        {\n            orient = W\n            0,0 = %s\n        }\n"
            "        entry\n        {\n            orient = N\n            0,0 = %s\n        }\n"
            "    }\n" % (layer, t(w), t(n)))


# The wall display hangs on a wall; the viewport replaces one, which is what
# vanilla's `layer = Walls` furniture does (a wall section drawn in the wall's
# own slot), so a viewport can go anywhere along a bulkhead.
AREAS = [("quarters", "Quarters"), ("lounge", "Lounge and Galley"), ("bridge", "Bridge"),
         ("sickbay", "Sickbay"), ("engineering", "Engineering"),
         ("transporter", "Transporter Room"), ("hydroponics", "Hydroponics"),
         ("galley", "Galley"), ("any", "Wall Art")]


def furniture_blocks(names, index):
    """BuildingEd furniture from the render's index: one `furniture` per
    object, one `entry` per facing, one `x,y = tile` per square it covers --
    the layout vanilla's own multi-square pieces use."""
    out = []
    for name in names:
        rec = index[name]
        lines = ["    furniture\n    {\n"]
        if rec["layer"] != "Furniture":
            lines.append("        layer = %s\n" % rec["layer"])
        for facing in "WNES":
            squares = rec["facings"].get(facing)
            if not squares:
                continue
            lines.append("        entry\n        {\n            orient = %s\n" % facing)
            for x, y, idx in squares:
                lines.append("            %d,%d = %s\n" % (x, y, f(idx)))
            lines.append("        }\n")
        lines.append("    }\n")
        out.append("".join(lines))
    return "".join(out)


def furniture_groups():
    """The structural pieces, then a group per area of the ship."""
    text = ("group\n{\n    label = Starfleet - Adirondack\n"
            + wall_piece("WallFurniture", 40, 41)
            + wall_piece("Walls", 16, 17)
            + "}\n")
    path = os.path.join(ROOT, "design", "tiles", FURN + ".json")
    with open(path) as fh:
        index = json.load(fh)
    for area, label in AREAS:
        names = [n for n in sorted(index) if index[n]["area"] == area]
        if names:
            text += ("group\n{\n    label = Starfleet - %s\n" % label
                     + furniture_blocks(names, index) + "}\n")
    return text


FURNITURE = furniture_groups()
# Every group whose label starts "Starfleet - " is ours, and all of them are
# replaced together, so a renamed or emptied group does not linger.
GROUP_RE = re.compile(r"group\n\{\n    label = Starfleet - [^\n]*\n.*?\n\}\n", re.S)


def backup(path):
    b = path + ".pretrek"
    if not os.path.exists(b):
        shutil.copy2(path, b)


def read(path):
    with open(path, "r", newline="") as f:
        return f.read()


def write(path, text):
    with open(path, "w", newline="") as f:
        f.write(text)


def main():
    check = "--check" in sys.argv
    if not check and os.name == "nt":
        import subprocess
        running = subprocess.run(["tasklist"], capture_output=True, text=True).stdout
        if "TileZed.exe" in running:
            sys.exit("TileZed is running: close it (and BuildingEd) first, or it may "
                     "write its own copy of the config back over this one on exit.")
    for p in [os.path.join(SRCDIR, s + ".png") for s in SHEETS] + [TILES, CONF]:
        if not os.path.exists(p):
            sys.exit("missing: %s" % p)
    report = []

    for sheet in SHEETS:
        dst = os.path.join(TILES, sheet + ".png")
        report.append("png: %s -> %s" % ("would copy" if check else "copied", dst))
        if not check:
            shutil.copy2(os.path.join(SRCDIR, sheet + ".png"), dst)

    # Our tileset entries are ours outright: replaced, so a sheet that has grown
    # a row reaches the editor with its new size.
    path = os.path.join(CONF, "Tilesets.txt")
    text = orig = read(path)
    for sheet in SHEETS:
        block = tileset_block(sheet)
        rx = re.compile(r"tileset\n\{\n    file = %s\n.*?\n\}\n" % re.escape(sheet), re.S)
        if block in text:
            report.append("Tilesets.txt: %s up to date" % sheet)
            continue
        report.append("Tilesets.txt: %s %s" % ("refreshing" if rx.search(text) else "adding", sheet))
        text = rx.sub("", text).rstrip("\n") + "\n" + block
    if text != orig and not check:
        backup(path)
        write(path, text)

    path = os.path.join(CONF, "BuildingTiles.txt")
    text = read(path)
    changed = False
    for cat, block in BUILDING.items():
        m = re.search(r"\n    name = %s\n" % cat, text)
        if not m:
            sys.exit("BuildingTiles.txt has no category %s" % cat)
        end = text.find("\n}\n", m.end())
        if SHEET in text[m.end():end]:
            report.append("BuildingTiles.txt: %s already has ours" % cat)
            continue
        report.append("BuildingTiles.txt: adding to %s" % cat)
        text = text[:m.end()] + block + text[m.end():]
        changed = True
    if changed and not check:
        backup(path)
        write(path, text)

    path = os.path.join(CONF, "BuildingFurniture.txt")
    text = read(path)
    # This group is ours outright, so it is replaced rather than added to:
    # a new piece of furniture reaches the editor on the next run.
    if FURNITURE in text:
        report.append("BuildingFurniture.txt: group up to date")
    else:
        had = GROUP_RE.search(text)
        report.append("BuildingFurniture.txt: %s the Starfleet group"
                      % ("refreshing" if had else "adding"))
        if not check:
            backup(path)
            text = GROUP_RE.sub("", text).rstrip("\n") + "\n" + FURNITURE
            write(path, text)

    print("\n".join(report))


if __name__ == "__main__":
    main()
