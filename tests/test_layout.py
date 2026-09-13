"""Checks the cabin floor plan, the furnishing offsets and the footprint.

Three things this catches that nothing else does:

  * A fitting placed outside the hull. The bow tapers over six squares and the
    stern over three, so an offset that is fine amidships can be in open space
    forward of oy 6 -- and a placement that misses simply does not happen, with
    no error anywhere. Every fit/line/place call in TREK_Build.lua is parsed
    out and checked against the floor plan.
  * Two fittings on one square. U.addObject only looks for its own sprite, so
    an overlap stacks silently and one of the two becomes unreachable.
  * A multi-tile piece whose halves are declared in the wrong order. The
    tileset says where each half belongs via SpriteGridPos; getting it
    backwards puts the foot of the bed where its head should be.

    python tests/test_layout.py
"""
import json, os, re, sys
from lupa import LuaRuntime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA = os.path.join(ROOT, "TrekShuttle", "42", "media", "lua").replace(os.sep, "/")
BUILD = os.path.join(ROOT, "TrekShuttle", "42", "media", "lua", "client",
                     "TREK", "TREK_Build.lua")
tiles = json.load(open(os.path.join(ROOT, "tools", "_catalog",
                                    "tiles.json")))["tiles"]

lua = LuaRuntime(unpack_returned_tuples=True)
lua.execute(f'package.path = "{LUA}/shared/?.lua;" .. package.path')
lua.execute("_G.unpack = _G.unpack or table.unpack")
lua.execute('require "TREK/TREK_Config"')
C = lua.globals().TREK.Config

W, L = int(C.CabinW), int(C.CabinL)
failures = []


def inside(ox, oy):
    return bool(C.inShape(ox, oy, None, None, None, None))


def is_pad(ox, oy):
    return bool(C.isLanding(ox, oy))


# --- floor plan --------------------------------------------------------
area = sum(inside(ox, oy) for ox in range(W + 1) for oy in range(L + 1))
print(f"cabin {W + 1} x {L + 1}, nose cut {int(C.NoseCut)}, "
      f"stern cut {int(C.TailCut)} -- {area} deck squares of {(W + 1) * (L + 1)}")
print()

# --- parse the layout out of TREK_Build.lua ----------------------------
# The offsets live in the build code rather than the config, because they are
# a layout and not a setting. Reading them back out with a regex is less
# elegant than loading the module, and loading it is not an option: it pulls in
# Events, IsoObject and the rest of the engine.
src = open(BUILD, encoding="utf-8").read()
placements = []          # (ox, oy, label)

for m in re.finditer(r"\bfit\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*"
                     r"[\w.]+\s*,\s*\"([\w.]+)\"", src):
    placements.append((int(m.group(1)), int(m.group(2)), m.group(3)))

for m in re.finditer(r"\bline\(\s*[\w.]+\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*"
                     r"(-?\d+)\s*,\s*(-?\d+)\s*,\s*(\d+)\s*,\s*"
                     r"\{[^}]*tag\s*=\s*\"([\w.]+)\"", src, re.S):
    ox, oy, dx, dy, n = (int(m.group(i)) for i in range(1, 6))
    tag = m.group(6)
    for i in range(n):
        placements.append((ox + dx * i, oy + dy * i, tag))

for m in re.finditer(r'\bplace\(\s*"(\w+)"\s*,\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*'
                     r'"([\w.]+)"', src):
    piece, ox, oy, tag = m.group(1), int(m.group(2)), int(m.group(3)), m.group(4)
    parts = C.Pieces[piece]
    if parts is None:
        failures.append(f"{tag}: no piece named {piece} in C.Pieces")
        continue
    for i in range(1, len(parts) + 1):
        entry = parts[i]
        placements.append((ox + int(entry[2]), oy + int(entry[3]), tag))

for m in re.finditer(r"B\.lampSpots\s*=\s*\{(.*?)\n\}", src, re.S):
    for lx, ly in re.findall(r"\{\s*(-?\d+)\s*,\s*(-?\d+)\s*\}", m.group(1)):
        placements.append((int(lx), int(ly), "lamp"))

# the helm console and the phaser locker are placed by hand
for m in re.finditer(r'claim\(\s*(-?\d+)\s*,\s*(-?\d+)\s*,\s*"(\w+)"\s*\)', src):
    placements.append((int(m.group(1)), int(m.group(2)), m.group(3)))
placements.append((int(C.PhaserRack.x), int(C.PhaserRack.y), "phasers"))

if len(placements) < 18:
    failures.append(f"only {len(placements)} placements parsed out of "
                    f"TREK_Build.lua; the layout regex has probably gone stale")

# --- draw it -----------------------------------------------------------
GLYPH = {"sink": "w", "toilet": "w", "shower": "w", "counter": "c",
         "oven": "c", "microwave": "c", "fridge": "F", "pantry": "p",
         "medbay": "M", "meddrawers": "m", "biobed": "B", "bunk": "b",
         "locker": "l", "cargo.food": "K", "cargo.medical": "K",
         "engineering": "e", "lamp": "*", "chair": "h", "terminal": "T",
         "computer": "T", "viewscreen": "V", "helm": "H", "phasers": "P"}
grid = {}
for ox, oy, tag in placements:
    grid.setdefault((ox, oy), []).append(tag)

print("    " + "".join(str(x % 10) for x in range(W + 1)))
for oy in range(L + 1):
    row = ""
    for ox in range(W + 1):
        if not inside(ox, oy):
            row += " "
        elif (ox, oy) in grid:
            row += GLYPH.get(grid[(ox, oy)][0], "?")
        elif ox == int(C.Landing.x) and oy == int(C.Landing.y):
            row += "@"
        elif is_pad(ox, oy):
            row += "o"
        else:
            row += "."
    print(f"{oy:3d} {row}")
print("\n   @ transporter pad   o kept clear   H helm   V viewscreen   T console")
print("   h seat   w water   c galley   F fridge   p pantry   M/m sick bay")
print("   B biobed   b berth   l locker   K cargo   e stores   P phasers   * lamp")

# --- the checks --------------------------------------------------------
for (ox, oy), tags in sorted(grid.items()):
    if not inside(ox, oy):
        failures.append(f"{'/'.join(tags)} at {ox},{oy} is outside the hull")
    elif is_pad(ox, oy):
        failures.append(f"{'/'.join(tags)} at {ox},{oy} stands on the "
                        f"transporter pad")
    if len(tags) > 1:
        failures.append(f"{ox},{oy} has {len(tags)} things on it: "
                        f"{', '.join(tags)}")

# The pad and its clearance ring must be inside the hull, or arrivals land in
# open space.
for dx in (-1, 0, 1):
    for dy in (-1, 0, 1):
        px, py = int(C.Landing.x) + dx, int(C.Landing.y) + dy
        if not inside(px, py):
            failures.append(f"the pad's clearance square {px},{py} is outside "
                            f"the hull")

if area < (W + 1) * (L + 1) * 0.55:
    failures.append(f"the hull keeps only {area} squares; the cuts are too deep")

# --- the exterior footprint -------------------------------------------
offsets = C.footprintOffsets()
n = len(offsets)
want = int(C.Footprint.w) * int(C.Footprint.h)
print(f"\nexterior footprint: {int(C.Footprint.w)} x {int(C.Footprint.h)} "
      f"= {n} squares")
if n != want:
    failures.append(f"footprintOffsets returns {n} squares, not {want}")
seen = set()
for i in range(1, n + 1):
    d = offsets[i]
    key = (int(d[1]), int(d[2]))
    if key in seen:
        failures.append(f"the footprint lists {key} twice")
    seen.add(key)
if (0, 0) not in seen:
    failures.append("the footprint does not include the square it is anchored on")

# The Lua footprint and the mesh in tools/gen_shuttle.py are kept in step by
# hand, so check they actually are.
gen = open(os.path.join(ROOT, "tools", "gen_shuttle.py"), encoding="utf-8").read()
hull_w = float(re.search(r"^HULL_W\s*=\s*([\d.]+)", gen, re.M).group(1))
hull_l = float(re.search(r"^HULL_L\s*=\s*([\d.]+)", gen, re.M).group(1))
if (hull_w, hull_l) != (float(C.Footprint.w), float(C.Footprint.h)):
    failures.append(f"the mesh is authored {hull_w:.0f}x{hull_l:.0f} tiles but "
                    f"C.Footprint asks for {int(C.Footprint.w)}x"
                    f"{int(C.Footprint.h)}")

# --- multi-tile pieces -------------------------------------------------
print("\nmulti-tile pieces:")
for name in C.Pieces:
    piece = C.Pieces[name]
    parts = [(piece[i][1], int(piece[i][2]), int(piece[i][3]))
             for i in range(1, len(piece) + 1)]
    shown = []
    for sprite, dx, dy in parts:
        props = tiles.get(sprite)
        if props is None:
            failures.append(f"{name}: sprite {sprite} does not exist")
            continue
        grid_pos = props.get("SpriteGridPos")
        if grid_pos is None:
            failures.append(f"{name}: {sprite} has no SpriteGridPos; "
                            f"it is not a multi-tile sprite")
            continue
        gx, gy = (int(v) for v in grid_pos.split(","))
        if (gx, gy) != (dx, dy):
            failures.append(f"{name}: {sprite} declared at offset {dx},{dy} "
                            f"but the tileset puts it at {gx},{gy}")
        shown.append(f"{sprite.rsplit('_', 1)[1]}@{dx},{dy}")
    facings = {tiles[s].get("Facing") for s, _, _ in parts if s in tiles}
    if len(facings) > 1:
        failures.append(f"{name}: halves face different ways {facings}")
    print(f"  {name:10s} {' '.join(shown):22s} "
          f"facing={facings.pop() if facings else '?'}")

print(f"\n{len(placements)} placements checked")
if failures:
    print(f"\n{len(failures)} PROBLEM(S):")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("floor plan, fittings and footprint are consistent")
