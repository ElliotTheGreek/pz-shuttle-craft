"""Writes the Shuttlecraft's void map: space around the cabin and the Adirondack.

The cabin is built at runtime in cell 96,40, well off the vanilla map, and the
U.S.S. Adirondack east of it. Left unmapped, those cells are filled by build
42's world generator -- grass, trees and zombies -- and clearing it at runtime
never fully works: the view reaches further than any clearing, chunks stream
in late, and zombies wander in.

A *mapped* cell is never generated. So the mod ships a small map of its own:
the same thing the Fifth-Wheel RV interior does (its map folder, RV_B, was
decoded to learn the format; nothing is copied from it). Its ground is space:
every square the crew could ever see from either ship carries one of sixteen
star-field floor tiles (trek_adirondack_01_48..63, gen_adirondack_tiles.py),
scattered at random; everything further out is an empty square, which the
engine draws as black. The ships stand four storeys above it.

**It lives in common/media/maps, never 42/media/maps.** MapGroups.createGroups
(bci 60-90) looks for a mod's `<common>/media/maps` first and, when that
folder does not exist, goes straight on to the next mod without looking in
the version folder at all. For as long as this map sat in 42/media/maps it was
never loaded by a single-player game: every save's mods.txt said `maps { }`
and the server's log said the map was not loaded.

Formats, build 42, 8x8-square chunks, one level (z 0):

  X_Y.lotheader        "LOTH", version 1, tile count N, N names each ending
                       "\\n", chunk width 8, height 8, min level 0, max level 0,
                       0 rooms, 0 buildings, 32x32 zombie-density bytes (all 0)
  world_X_Y.lotpack    "LOTP", version 1, chunk count 1024, 1024 int64 offsets
                       (chunk index = chunk x * 32 + chunk y, IsoLot.load bci
                       266-302), then per chunk its squares, x outer and y
                       inner (bci 412-433): (-1, n) skips n squares, and
                       (count, room, tile...) is a square with count-1 tiles
                       and room -1 for none
  chunkdata_X_Y.bin    00 01, then 1024 zero bytes

All little-endian. tests/test_assets.py reads the files back.

    python tools/gen_void_map.py
"""
import random
import re
import shutil
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP_NAME = "TrekShuttle"
OUT = ROOT / "TrekShuttle" / "common" / "media" / "maps" / MAP_NAME
# Where the map used to be, and was never read from. Removed on every run.
OLD = ROOT / "TrekShuttle" / "42" / "media" / "maps" / MAP_NAME
LUA = ROOT / "TrekShuttle" / "42" / "media" / "lua" / "shared" / "TREK"

CELL = 256
CHUNKS_PER_SIDE = 32          # 256 squares / 8
CHUNK_SQUARES = 8 * 8         # one level
CHUNK_COUNT = CHUNKS_PER_SIDE * CHUNKS_PER_SIDE
STARS = ["trek_adirondack_01_%d" % i for i in range(48, 64)]
# How far past either ship the stars reach. The engine loads 19 chunks of 8
# around a player at most (IsoChunkMap.CalcChunkWidth), 76 squares either way,
# and draws nothing it has not loaded; the ground four storeys down is drawn a
# dozen squares offset from the deck above it. So 110 is past anything a crew
# member can see, from anywhere aboard either ship.
VIEW = 110


def lua_number(path, pattern):
    m = re.search(pattern, path.read_text(encoding="utf-8"))
    if not m:
        raise SystemExit("%s: %s not found" % (path.name, pattern))
    return [int(g) for g in m.groups()]


def ships():
    """The squares the cabin and the Adirondack stand on: (x0, y0, x1, y1)."""
    cfg = LUA / "TREK_Config.lua"
    cx, cy = lua_number(cfg, r"C\.InteriorCell\s*=\s*\{\s*x\s*=\s*(\d+),\s*y\s*=\s*(\d+)")
    (off,) = lua_number(cfg, r"C\.RoomOffset\s*=\s*(\d+)")
    cabin = (cx * CELL + off, cy * CELL + off, cx * CELL + off + 16, cy * CELL + off + 16)
    adk = LUA / "TREK_Adirondack.lua"
    ax, ay = lua_number(adk, r"A\.Cell\s*=\s*\{\s*x\s*=\s*(\d+),\s*y\s*=\s*(\d+)")
    (aoff,) = lua_number(adk, r"A\.Offset\s*=\s*(\d+)")
    lay = LUA / "TREK_AdirondackLayout.lua"
    # Her decks and the Jefferies tubes between them (gen_adirondack_lua.py).
    sx0, sy0, sx1, sy1 = [int(v) for v in re.search(
        r"L\.span = \{ x0 = (-?\d+), y0 = (-?\d+), x1 = (-?\d+), y1 = (-?\d+) \}",
        lay.read_text(encoding="utf-8")).groups()]
    x0, y0 = ax * CELL + aoff, ay * CELL + aoff
    ship = (x0 + sx0, y0 + sy0, x0 + sx1, y0 + sy1)
    return cabin, ship


def space_box():
    cabin, ship = ships()
    return (min(cabin[0], ship[0]) - VIEW, min(cabin[1], ship[1]) - VIEW,
            max(cabin[2], ship[2]) + VIEW, max(cabin[3], ship[3]) + VIEW)


def cells(box):
    """Every cell the starfield touches, and a ring round them: an unmapped
    cell beside a mapped one is generated as wilderness, and from the edge of
    the stars the next cell's trees would be in view."""
    x0, y0, x1, y1 = box
    return [(x, y) for x in range(x0 // CELL - 1, x1 // CELL + 2)
            for y in range(y0 // CELL - 1, y1 // CELL + 2)]


def lotheader():
    out = bytearray(b"LOTH")
    out += struct.pack("<ii", 1, len(STARS))
    for name in STARS:
        out += name.encode("ascii") + b"\n"
    out += struct.pack("<iiii", 8, 8, 0, 0)       # chunk size, level range
    out += struct.pack("<ii", 0, 0)               # rooms, buildings
    out += bytes(CHUNK_COUNT)                     # zombie density: none
    return bytes(out)


def chunk(wx, wy, box, rnd):
    """One chunk's squares: a star floor where it is in the box, else nothing."""
    x0, y0, x1, y1 = box
    out = bytearray()
    skip = 0
    for sx in range(8):
        for sy in range(8):
            x, y = wx * 8 + sx, wy * 8 + sy
            if x0 <= x <= x1 and y0 <= y <= y1:
                if skip:
                    out += struct.pack("<ii", -1, skip)
                    skip = 0
                out += struct.pack("<iii", 2, -1, rnd.randrange(len(STARS)))
            else:
                skip += 1
    if skip:
        out += struct.pack("<ii", -1, skip)
    return bytes(out)


def lotpack(cx, cy, box):
    rnd = random.Random(cx * 1000 + cy)
    header = b"LOTP" + struct.pack("<ii", 1, CHUNK_COUNT)
    body, offsets = bytearray(), []
    base = len(header) + 8 * CHUNK_COUNT
    for i in range(CHUNK_COUNT):
        lx, ly = divmod(i, CHUNKS_PER_SIDE)
        offsets.append(base + len(body))
        body += chunk(cx * CHUNKS_PER_SIDE + lx, cy * CHUNKS_PER_SIDE + ly, box, rnd)
    return header + struct.pack("<%dq" % CHUNK_COUNT, *offsets) + bytes(body)


def chunkdata():
    return b"\x00\x01" + bytes(CHUNK_COUNT)


MAP_INFO = """title=Shuttlecraft void
lots=Muldraugh, KY
fixed2x=true
description=Space around the Shuttlecraft cabin and the U.S.S. Adirondack: stars below, black beyond.
"""


def main():
    if OLD.exists():
        shutil.rmtree(OLD)
        parent = OLD.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.iterdir():
        old.unlink()
    box = space_box()
    todo = cells(box)
    (OUT / "map.info").write_text(MAP_INFO, encoding="utf-8", newline="\n")
    (OUT / "objects.lua").write_text("objects = {}\n", encoding="utf-8", newline="\n")
    size = 0
    for x, y in todo:
        (OUT / f"{x}_{y}.lotheader").write_bytes(lotheader())
        pack = lotpack(x, y, box)
        size += len(pack)
        (OUT / f"world_{x}_{y}.lotpack").write_bytes(pack)
        (OUT / f"chunkdata_{x}_{y}.bin").write_bytes(chunkdata())
    print(f"wrote {len(todo)} cells to {OUT.relative_to(ROOT)}; stars over x {box[0]}..{box[2]}, "
          f"y {box[1]}..{box[3]}; {size // 1024} KB of lotpack")


if __name__ == "__main__":
    main()
