"""Reads the vanilla map round the six marooned sites, and says whether the
shuttle can come down at each.

    python tools/maroon_sites.py            # check C.Maroon.sites
    python tools/maroon_sites.py --find     # look for open ground by each town

A marooned world (MAROONED.md) puts the ship at one of six points in the
county and sets her down on the nearest clear ground to it. A point in the
middle of a wood, a lake or a building is a ship nobody can ever find, so the
points were chosen by reading the map rather than by remembering it, and
tests/test_assets.py runs the check below against the installed map: a game
update that builds on one of these fields fails at the desk.

**What is checked is the map as shipped.** Trees and bushes that grow in over
a save's months are not in these files; that is why the server searches a
ring round the point (C.Maroon.placeMax) instead of trusting the point. The
check asks for room that is generous to make up for it: a block NEED squares
on a side, every square of it open floor, inside that ring.

The map's two file formats are read by tools/fieldstation_site.py, which has
the description.
"""
import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import fieldstation_site as F

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG = os.path.join(ROOT, "TrekShuttle", "42", "media", "lua", "shared", "TREK", "TREK_Config.lua")
MAPS = os.path.dirname(F.MAP)

# A square side of clear ground: the hull is three by five, and this is that
# with a margin on every side.
NEED = 9

# Tile properties that stop a square being ground a ship can stand on.
BLOCKS = ("solid", "solidtrans", "tree", "WallN", "WallW", "WallNW", "collideN", "collideW",
          "HoppableN", "HoppableW", "water", "DoorWallN", "DoorWallW", "WindowN", "WindowW")

_cells = {}


def cell(cx, cy):
    if (cx, cy) not in _cells:
        try:
            _cells[(cx, cy)] = F.squares(cx, cy, cx * F.CELL, cy * F.CELL,
                                         cx * F.CELL + F.CELL - 1, cy * F.CELL + F.CELL - 1)
        except (OSError, ValueError):
            _cells[(cx, cy)] = None
    return _cells[(cx, cy)]


def open_ground(tiles, x, y):
    """True when a square has a floor on it and nothing that blocks."""
    c = cell(x // F.CELL, y // F.CELL)
    if c is None:
        return False
    here = c.get((x, y), [])
    if not here:
        return False
    for name in here:
        props = tiles.get(name)
        if props is None or any(b in props for b in BLOCKS):
            return False
        if name.startswith(("vegetation", "f_bushes")):
            return False
    return "solidfloor" in (tiles.get(here[0]) or {})


def block_clear(tiles, x0, y0, n=NEED):
    return all(open_ground(tiles, x0 + i, y0 + j) for i in range(n) for j in range(n))


def config():
    """The sites and the ring, out of TREK_Config.lua."""
    src = open(CONFIG, encoding="utf-8").read()
    block = re.search(r"C\.Maroon\s*=\s*\{(.*?)\n\}", src, re.S)
    if not block:
        raise SystemExit("no C.Maroon block in TREK_Config.lua")
    sites = [(m.group(1), int(m.group(2)), int(m.group(3)))
             for m in re.finditer(r'id\s*=\s*"(\w+)",\s*x\s*=\s*(\d+),\s*y\s*=\s*(\d+)', block.group(1))]
    ring = re.search(r"placeMax\s*=\s*(\d+)", block.group(1))
    if not sites or not ring:
        raise SystemExit("C.Maroon: no sites, or no placeMax, were read out of TREK_Config.lua")
    return sites, int(ring.group(1))


def room_at(tiles, x, y, ring):
    """How many NEED-square blocks of open ground lie wholly inside the ring."""
    n = 0
    for x0 in range(x - ring, x + ring - NEED + 2):
        for y0 in range(y - ring, y + ring - NEED + 2):
            if block_clear(tiles, x0, y0):
                n += 1
    return n


def check():
    """One line per site: (id, x, y, blocks of room). Zero is a failure."""
    tiles = json.load(open(F.CATALOG))["tiles"]
    sites, ring = config()
    return [(sid, x, y, room_at(tiles, x, y, ring)) for sid, x, y in sites]


def find():
    """Prints open ground near each town's spawn points, nearest first."""
    tiles = json.load(open(F.CATALOG))["tiles"]
    n = 17
    for town in sorted(os.listdir(MAPS)):
        path = os.path.join(MAPS, town, "spawnpoints.lua")
        if not os.path.isfile(path):
            continue
        pts = [(int(a), int(b)) for a, b in
               re.findall(r"posX *= *(\d+), *posY *= *(\d+)", open(path).read())]
        if not pts:
            continue
        cx, cy = sum(p[0] for p in pts) // len(pts), sum(p[1] for p in pts) // len(pts)
        found = []
        for r in range(48, 400, 8):
            for dx in range(-r, r + 1, 8):
                for dy in range(-r, r + 1, 8):
                    if max(abs(dx), abs(dy)) == r and block_clear(tiles, cx + dx, cy + dy, n):
                        found.append((cx + dx + n // 2, cy + dy + n // 2, r))
            if len(found) >= 6:
                break
        print("%-20s middle %d,%d" % (town, cx, cy))
        for x, y, r in found[:6]:
            print("    %d, %d   (%d squares out)" % (x, y, r))


def main():
    if not os.path.isdir(F.MAP):
        raise SystemExit("no vanilla map at " + F.MAP)
    if "--find" in sys.argv:
        return find()
    bad = 0
    for sid, x, y, room in check():
        print("%-14s %5d,%-5d  %4d places to set her down" % (sid, x, y, room))
        bad += room == 0
    if bad:
        raise SystemExit("%d site(s) have no room for the shuttle on the map as shipped" % bad)


if __name__ == "__main__":
    main()
