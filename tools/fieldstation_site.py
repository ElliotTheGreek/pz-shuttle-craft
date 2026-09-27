"""Reads the vanilla map round the field station's site, and prints it.

    python tools/fieldstation_site.py            # the stockroom, square by square
    python tools/fieldstation_site.py --shops    # every shop room in Muldraugh

The field station hides behind a breaker box on a stockroom wall
(FIELD_STATION.md 3). Which wall was chosen by reading the map, not by walking
it: this parses the two files every map cell is made of --

  <x>_<y>.lotheader      "LOTH", int version, the tile names used (one per
                         line), int width, height, min and max level, then
                         the rooms (name, level, rectangles, objects) and the
                         buildings (lists of room indices)
  world_<x>_<y>.lotpack  "LOTP", int version, int chunk count, then a table of
                         8-byte chunk offsets; per chunk, per level, per square
                         (x outer, y inner): an int count, -1 and a skip, or a
                         room id and count-1 tile indices

-- both read out of IsoMetaGrid$MetaGridLoaderThread.loadCell and
IsoLot.load (tools/javadis.py), not guessed. Cells are 256 squares, chunks 8.

It prints each square of C.FieldStation's room with every tile on it, marks
which carry a solid wall on their west or north edge (WallW / WallN from the
tile catalogue) and nothing else, and says whether the configured square is one
of them -- the same rules the server applies in the game
(TREK_FieldStationServer.checkSquare), which is the check that matters.
"""
import json
import os
import re
import struct
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MAP = os.environ.get("PZ_MAP", r"C:/Program Files (x86)/Steam/steamapps/common/ProjectZomboid/media/maps/Muldraugh, KY")
CATALOG = os.path.join(ROOT, "tools", "_catalog", "tiles.json")
CONFIG = os.path.join(ROOT, "TrekShuttle", "42", "media", "lua", "shared", "TREK", "TREK_Config.lua")
CELL = 256


def header(cx, cy):
    b = open(os.path.join(MAP, "%d_%d.lotheader" % (cx, cy)), "rb").read()
    if b[:4] != b"LOTH":
        raise SystemExit("%d_%d.lotheader is not a version-1 header" % (cx, cy))
    p = 8
    n = struct.unpack_from("<i", b, p)[0]
    p += 4
    tiles = []
    for _ in range(n):
        e = b.index(b"\n", p)
        tiles.append(b[p:e].decode("latin1").strip())
        p = e + 1
    _w, _h, lo, hi = struct.unpack_from("<iiii", b, p)
    p += 16

    def i32():
        nonlocal p
        v = struct.unpack_from("<i", b, p)[0]
        p += 4
        return v

    def line():
        nonlocal p
        e = b.index(b"\n", p)
        v = b[p:e].decode("latin1")
        p = e + 1
        return v

    rooms = []
    for _ in range(i32()):
        name, level = line(), i32()
        rects = [(i32() + cx * CELL, i32() + cy * CELL, i32(), i32()) for _ in range(i32())]
        for _ in range(i32()):
            i32(), i32(), i32()
        rooms.append((name, level, rects))
    buildings = [[rooms[i32()] for _ in range(i32())] for _ in range(i32())]
    return tiles, lo, hi, rooms, buildings


def squares(cx, cy, x0, y0, x1, y1, z=0):
    tiles, lo, hi, _, _ = header(cx, cy)
    b = open(os.path.join(MAP, "world_%d_%d.lotpack" % (cx, cy)), "rb").read()
    base = 8 if b[:4] == b"LOTP" else 0
    out = {}
    for wx in range(x0 // 8, x1 // 8 + 1):
        for wy in range(y0 // 8, y1 // 8 + 1):
            idx = (wx - cx * 32) * 32 + (wy - cy * 32)
            p = struct.unpack_from("<i", b, base + 4 + idx * 8)[0]
            skip = 0
            for lz in range(max(lo, -32), min(hi, 31) + 1):
                for i in range(8):
                    for j in range(8):
                        if skip > 0:
                            skip -= 1
                            continue
                        c = struct.unpack_from("<i", b, p)[0]
                        p += 4
                        if c == -1:
                            skip = struct.unpack_from("<i", b, p)[0] - 1
                            p += 4
                            continue
                        if c > 1:
                            p += 4
                            ts = [tiles[struct.unpack_from("<i", b, p + 4 * k)[0]] for k in range(c - 1)]
                            p += 4 * (c - 1)
                            if lz == z:
                                out[(wx * 8 + i, wy * 8 + j)] = ts
    return out


def site():
    s = open(CONFIG, encoding="utf-8").read()
    m = re.search(r"C\.FieldStation = \{\s*x = (\d+), y = (\d+), z = (\d+), edge = \"(\w)\",\s*"
                  r"room = \"(\w+)\"", s)
    if not m:
        raise SystemExit("C.FieldStation not found in TREK_Config.lua")
    return int(m[1]), int(m[2]), int(m[3]), m[4], m[5]


def verdict(ts, edge, props):
    """The server's rule, on the catalogue's properties: None when it passes."""
    wall = False
    for t in ts:
        p = props.get(t, {})
        if t.startswith("floors_"):
            continue
        if any(k in p for k in (("WindowN", "windowN", "DoorWallN", "doorN") if edge == "N"
                                else ("WindowW", "windowW", "DoorWallW", "doorW"))):
            return "opening"
        if any(k in p for k in (("WallN", "WallNW") if edge == "N" else ("WallW", "WallNW"))):
            wall = True
            continue
        if t.startswith("overlay_") or "WallOverlay" in p:
            continue
        if t.startswith("walls_") and "attachedW" not in p and "attachedN" not in p:
            continue
        return "occupied (%s)" % t
    return None if wall else "no wall"


def main():
    x, y, z, edge, room = site()
    cx, cy = x // CELL, y // CELL
    _, _, _, rooms, _ = header(cx, cy)
    if "--shops" in sys.argv:
        for name, level, rects in rooms:
            if level == 0 and re.search("store|shop|storage", name):
                print("%-24s %s" % (name, rects))
        return
    mine = [r for r in rooms if r[0] == room and any(rx <= x < rx + w and ry <= y < ry + h
                                                     for rx, ry, w, h in r[2])]
    if not mine:
        raise SystemExit("%d,%d is not in a room called %s" % (x, y, room))
    props = json.load(open(CATALOG))["tiles"]
    rects = mine[0][2]
    x0 = min(r[0] for r in rects)
    y0 = min(r[1] for r in rects)
    x1 = max(r[0] + r[2] for r in rects) - 1
    y1 = max(r[1] + r[3] for r in rects) - 1
    sq = squares(cx, cy, x0, y0, x1, y1, z)
    passing = []
    for yy in range(y0, y1 + 1):
        for xx in range(x0, x1 + 1):
            ts = sq.get((xx, yy), [])
            for e in "WN":
                if verdict(ts, e, props) is None:
                    passing.append((xx, yy, e))
            print("%d,%d  %s" % (xx, yy, " ".join(t for t in ts if not t.startswith("overlay_"))))
    print()
    print("squares a box may hang on:", passing or "none")
    why = verdict(sq.get((x, y), []), edge, props)
    print("the configured square %d,%d (%s wall): %s" % (x, y, edge, why or "passes"))
    if why:
        sys.exit(1)


if __name__ == "__main__":
    main()
