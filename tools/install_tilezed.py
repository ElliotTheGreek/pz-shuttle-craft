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
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SHEET = "trek_adirondack_01"
SRC = os.path.join(ROOT, "design", "tiles", "2x", SHEET + ".png")
TOOLS = os.environ.get(
    "PZ_MODDING_TOOLS",
    r"D:/SteamLibrary/steamapps/common/Project Zomboid Modding Tools")
TILES = os.path.join(TOOLS, "Tiles", "2x")
CONF = os.path.join(os.path.expanduser("~"), ".TileZed")


def t(i):
    return "%s_%03d" % (SHEET, i)


TILESET = """tileset
{
    file = %s
    size = 8,8
    tile
    {
        xy = 0,4
        meta-enum = DoorW
    }
    tile
    {
        xy = 1,4
        meta-enum = DoorN
    }
}
""" % SHEET


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
FURNITURE = ("group\n{\n    label = Starfleet - Adirondack\n"
             + wall_piece("WallFurniture", 40, 41)
             + wall_piece("Walls", 16, 17)
             + "}\n")
GROUP_RE = re.compile(r"group\n\{\n    label = Starfleet - Adirondack\n.*?\n\}\n", re.S)


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
    for p in (SRC, TILES, CONF):
        if not os.path.exists(p):
            sys.exit("missing: %s" % p)
    report = []

    dst = os.path.join(TILES, SHEET + ".png")
    report.append("png: %s" % ("would copy" if check else "copied") + " -> " + dst)
    if not check:
        shutil.copy2(SRC, dst)

    path = os.path.join(CONF, "Tilesets.txt")
    text = read(path)
    if "file = %s\n" % SHEET in text:
        report.append("Tilesets.txt: already has %s" % SHEET)
    else:
        report.append("Tilesets.txt: adding %s" % SHEET)
        if not check:
            backup(path)
            write(path, text.rstrip("\n") + "\n" + TILESET)

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
