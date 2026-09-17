"""Writes the Shuttlecraft's void map: empty map cells around the cabin.

The cabin is built at runtime in cell 96,40, well off the vanilla map. Left
unmapped, that cell is filled by build 42's world generator -- grass, trees and
zombies -- and clearing it at runtime never fully works: the view reaches
further than any clearing, chunks stream in late, and zombies wander in.

A *mapped* cell is never generated. A map cell with no tiles in it is nothing
at all, and renders black. So the mod ships a tiny map whose cells are empty:
the same thing the Fifth-Wheel RV interior does (its map folder, RV_B, was
decoded to learn the format; nothing is copied from it).

Formats, build 42, for a cell with no tiles, 8x8-square chunks, one level:

  X_Y.lotheader        "LOTH", version 1, tile count 1, "invisible_01_0\\n",
                       chunk width 8, height 8, min level 0, max level 0,
                       0 rooms, 0 buildings, 32x32 zombie-density bytes (all 0)
  world_X_Y.lotpack    "LOTP", version 1, chunk count 1024, 1024 int64 offsets,
                       then per chunk the record (-1, 64): "skip 64 squares"
  chunkdata_X_Y.bin    00 01, then 1024 zero bytes

All little-endian. tests/test_assets.py reads the files back.

    python tools/gen_void_map.py
"""
import struct
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAP_NAME = "TrekShuttle"
OUT = ROOT / "TrekShuttle" / "42" / "media" / "maps" / MAP_NAME

# The cabin's cell and two rings of cells around it, 5x5. One ring was not
# enough: the cabin is four floors up, and from that height the camera shows
# ground well past the neighbouring cells -- trees were visible to the north in
# game. The Fifth-Wheel RV covers 5x5 around its interior for the same reason.
# Must agree with C.InteriorCell in TREK_Config.lua (tests/test_assets.py checks).
INTERIOR_CELL = (96, 40)
RING = 2
CELLS = [(INTERIOR_CELL[0] + dx, INTERIOR_CELL[1] + dy)
         for dx in range(-RING, RING + 1) for dy in range(-RING, RING + 1)]

CHUNKS_PER_SIDE = 32          # 256 squares / 8
CHUNK_SQUARES = 8 * 8         # one level
CHUNK_COUNT = CHUNKS_PER_SIDE * CHUNKS_PER_SIDE


def lotheader():
    out = bytearray(b"LOTH")
    out += struct.pack("<ii", 1, 1)
    out += b"invisible_01_0\n"
    out += struct.pack("<iiii", 8, 8, 0, 0)       # chunk size, level range
    out += struct.pack("<ii", 0, 0)               # rooms, buildings
    out += bytes(CHUNK_COUNT)                     # zombie density: none
    return bytes(out)


def lotpack():
    header = b"LOTP" + struct.pack("<ii", 1, CHUNK_COUNT)
    table_end = len(header) + 8 * CHUNK_COUNT
    offsets = [table_end + 8 * i for i in range(CHUNK_COUNT)]
    body = struct.pack("<ii", -1, CHUNK_SQUARES) * CHUNK_COUNT
    return header + struct.pack("<%dq" % CHUNK_COUNT, *offsets) + body


def chunkdata():
    return b"\x00\x01" + bytes(CHUNK_COUNT)


MAP_INFO = """title=Shuttlecraft void
lots=Muldraugh, KY
fixed2x=true
description=Empty cells around the Shuttlecraft cabin, so the space outside it is black.
"""


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    for old in OUT.iterdir():
        old.unlink()
    (OUT / "map.info").write_text(MAP_INFO, encoding="utf-8", newline="\n")
    (OUT / "objects.lua").write_text("objects = {}\n", encoding="utf-8", newline="\n")
    for x, y in CELLS:
        (OUT / f"{x}_{y}.lotheader").write_bytes(lotheader())
        (OUT / f"world_{x}_{y}.lotpack").write_bytes(lotpack())
        (OUT / f"chunkdata_{x}_{y}.bin").write_bytes(chunkdata())
    print(f"wrote {len(CELLS)} empty cells to {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
