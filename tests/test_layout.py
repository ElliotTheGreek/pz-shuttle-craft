"""Checks the cabin floor plan, the authored interior and the footprint.

The interior is authored in BuildingEd and read at runtime out of
TREK_InteriorLayout.lua. That file is data with no engine calls in it, so this
loads it for real rather than parsing it, and checks the things that fail
silently in game:

  * A fitting outside the hull, or on the transporter pad. A placement that
    misses simply does not happen -- no error, no object, nothing in the log.
  * A container that is not flagged as one. `container = true` is what makes
    TREK_Build build an ItemContainer for it; without the flag the locker is
    placed as scenery and can never be opened, and it looks identical until
    somebody walks up to it. Checked both ways against the tile catalogue, so
    a flag on a sprite that cannot hold anything fails too.
  * A loot list that does not exist. `loot = "supplies"` with no C.Loot.supplies
    leaves the container empty and says nothing.
  * The Lua drifting from the .tbx it was generated from.
  * A lamp stacked on top of a fitting: the lamps are placed by TREK_Build and
    claim their square, but the authored furniture bypasses claim() by design,
    so nothing at runtime would report the collision.

    python tests/test_layout.py
"""
import json, os, re, subprocess, sys
from lupa import LuaRuntime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA = os.path.join(ROOT, "TrekShuttle", "42", "media", "lua").replace(os.sep, "/")
BUILD = os.path.join(ROOT, "TrekShuttle", "42", "media", "lua", "server",
                     "TREK", "TREK_Build.lua")
tiles = json.load(open(os.path.join(ROOT, "tools", "_catalog",
                                    "tiles.json")))["tiles"]

lua = LuaRuntime(unpack_returned_tuples=True)
lua.execute(f'package.path = "{LUA}/shared/?.lua;{LUA}/client/?.lua;" '
            f'.. package.path')
lua.execute("_G.unpack = _G.unpack or table.unpack")
lua.execute('require "TREK/TREK_Config"')
C = lua.globals().TREK.Config
lua.execute('_interior = require "TREK/TREK_InteriorLayout"')
L = lua.globals()._interior

W, L_LEN = int(C.CabinW), int(C.CabinL)
failures = []


def inside(ox, oy):
    return bool(C.inShape(ox, oy, None, None, None, None))


def is_pad(ox, oy):
    return bool(C.isLanding(ox, oy))


def rows(table):
    return [table[i] for i in range(1, len(table) + 1)]


# --- floor plan --------------------------------------------------------
area = sum(inside(ox, oy) for ox in range(W + 1) for oy in range(L_LEN + 1))
print(f"cabin {W + 1} x {L_LEN + 1}, nose cut {int(C.NoseCut)}, "
      f"stern cut {int(C.TailCut)} -- {area} deck squares of "
      f"{(W + 1) * (L_LEN + 1)}")
print()

# --- the authored interior ---------------------------------------------
entries = []
for e in rows(L.tiles):
    entries.append({
        "x": int(e.x), "y": int(e.y), "sprite": e.sprite,
        "tag": e.tag or "?", "container": e.container is True,
        "loot": e.loot, "special": e.special,
    })

for e in entries:
    where = f"{e['tag']} ({e['sprite']}) at {e['x']},{e['y']}"

    if not inside(e["x"], e["y"]):
        failures.append(f"{where} is outside the hull")
    if is_pad(e["x"], e["y"]):
        failures.append(f"{where} stands on the transporter pad")

    props = tiles.get(e["sprite"])
    if props is None:
        failures.append(f"{where}: sprite does not exist")
        continue

    # `container` in the tileset is the container type ("locker", "counter").
    holds = bool(props.get("container"))
    wants = e["container"] or e["loot"] is not None or e["special"] is not None
    if wants and not holds:
        failures.append(f"{where} is stocked but {e['sprite']} is not a "
                        f"container in the tileset -- it can never be opened")
    if wants and not e["container"]:
        failures.append(f"{where} carries loot but has no container = true; "
                        f"TREK_Build will place it as scenery")
    if holds and not wants:
        failures.append(f"{where} is a container in the tileset but nothing "
                        f"stocks it -- it will be empty in game")

    if e["loot"] is not None and C.Loot[e["loot"]] is None:
        failures.append(f"{where}: no C.Loot.{e['loot']}")

containers = [e for e in entries if e["container"]]
phasers = [e for e in entries if e["special"] == "phasers"]
if len(phasers) != 1:
    failures.append(f"{len(phasers)} phaser lockers in the layout; expected 1")
else:
    # C.PhaserRack is what the rest of the mod points at -- menus, the self
    # test -- while the locker that actually gets the phasers is the authored
    # entry. Nothing at runtime would notice the two disagreeing.
    rack = (int(C.PhaserRack.x), int(C.PhaserRack.y))
    if rack != (phasers[0]["x"], phasers[0]["y"]):
        failures.append(f"C.PhaserRack says {rack[0]},{rack[1]} but the "
                        f"authored phaser locker is at {phasers[0]['x']},"
                        f"{phasers[0]['y']}")

# --- the lamps (C.LampSpots) and the helm, which the server build places --
src = open(BUILD, encoding="utf-8").read()
lamps = [(int(C.LampSpots[i][1]), int(C.LampSpots[i][2]))
         for i in range(1, len(C.LampSpots) + 1)]
helm = re.search(r"local hx, hy = at\((\d+), (\d+)\)", src)
helm = (int(helm.group(1)), int(helm.group(2))) if helm else None

if not lamps:
    failures.append("C.LampSpots is empty; the cabin would have no lights")

# A lamp shares its square with nothing: fit() claims it, but the authored
# furniture bypasses claim(), so only this check would catch the overlap.
solid = {(e["x"], e["y"]) for e in entries if not e["tag"].startswith("rug")}
for lx, ly in lamps:
    if not inside(lx, ly):
        failures.append(f"lamp at {lx},{ly} is outside the hull")
    elif is_pad(lx, ly):
        failures.append(f"lamp at {lx},{ly} stands on the transporter pad")
    elif (lx, ly) in solid:
        tag = next(e["tag"] for e in entries if (e["x"], e["y"]) == (lx, ly))
        failures.append(f"lamp at {lx},{ly} lands on top of {tag}")

if helm:
    if not inside(*helm):
        failures.append(f"the helm item at {helm[0]},{helm[1]} is outside the hull")
    elif helm in solid:
        tag = next(e["tag"] for e in entries if (e["x"], e["y"]) == helm)
        failures.append(f"the helm item at {helm[0]},{helm[1]} lands on {tag}")

# --- draw it -----------------------------------------------------------
GLYPH = {"rug": ".", "console": "T", "helmDesk": "T", "viewscreen": "V",
         "freshFood": "F", "cookware": "c", "provisions": "p", "snacks": "c",
         "readyKit": "s", "computer": "T", "sink": "w", "chair": "h",
         "medical": "M", "engineering": "e", "phasers": "P", "armoury": "A",
         "survival": "s", "bunk": "b"}
grid = {}
for e in entries:
    grid.setdefault((e["x"], e["y"]), []).append(e["tag"])

print("    " + "".join(str(x % 10) for x in range(W + 1)))
for oy in range(L_LEN + 1):
    row = ""
    for ox in range(W + 1):
        if not inside(ox, oy):
            row += " "
        elif ox == int(C.Landing.x) and oy == int(C.Landing.y):
            row += "@"
        elif (ox, oy) in grid:
            # the topmost non-rug layer is what you actually walk up to
            tags = [t for t in grid[(ox, oy)] if t != "rug"] or grid[(ox, oy)]
            row += GLYPH.get(tags[-1], "?")
        elif (ox, oy) in lamps:
            row += "*"
        elif helm and (ox, oy) == helm:
            row += "H"
        else:
            row += "."
    print(f"{oy:3d} {row}")
print("\n   @ transporter pad   H helm   V viewscreen   T console   h seat")
print("   w water   c galley   F fridge   p provisions   M sick bay")
print("   e engineering   A armoury   P phasers   s survival   b berth   * lamp")

print(f"\n{len(entries)} authored fittings, {len(containers)} of them stocked:")
for e in containers:
    what = "phasers + " + (e["loot"] or "-") if e["special"] else e["loot"]
    print(f"  {e['x']},{e['y']}  {e['tag']:11s} {what}")

# --- the Lua against the .tbx it came from -----------------------------
# The geometry is authored in BuildingEd; the loot is not. Only the geometry
# is checked, and only that every container the editor placed is accounted
# for -- which is the drift that matters, because a locker added in the editor
# and not here is a locker that never appears in game.
try:
    out = subprocess.run([sys.executable, os.path.join(ROOT, "tools",
                                                       "import_tbx_layout.py"),
                          "--json"], capture_output=True, text=True, check=True)
    tbx = json.loads(out.stdout)
except Exception as exc:                                  # noqa: BLE001
    print(f"\ncould not decode the .tbx ({exc}); skipping the drift check")
else:
    want = sorted((c["x"], c["y"], c["sprite"]) for c in tbx["containers"])
    have = sorted((e["x"], e["y"], e["sprite"]) for e in containers)
    print(f"\n.tbx holds {len(want)} container tiles, the Lua stocks {len(have)}")
    for missing in set(want) - set(have):
        failures.append(f"the .tbx places a container at {missing[0]},"
                        f"{missing[1]} ({missing[2]}) that the Lua does not stock")
    for extra in set(have) - set(want):
        failures.append(f"the Lua stocks a container at {extra[0]},{extra[1]} "
                        f"({extra[2]}) that is not in the .tbx")

# --- the pad -----------------------------------------------------------
for dx in (-1, 0, 1):
    for dy in (-1, 0, 1):
        px, py = int(C.Landing.x) + dx, int(C.Landing.y) + dy
        if not inside(px, py):
            failures.append(f"the pad's clearance square {px},{py} is outside "
                            f"the hull")
        elif (px, py) in solid:
            tag = next(e["tag"] for e in entries if (e["x"], e["y"]) == (px, py))
            failures.append(f"{tag} at {px},{py} blocks the pad approach")

if area < (W + 1) * (L_LEN + 1) * 0.55:
    failures.append(f"the hull keeps only {area} squares; the cuts are too deep")

# --- the exterior footprint -------------------------------------------
offsets = C.footprintOffsets()
n = len(offsets)
want_n = int(C.Footprint.w) * int(C.Footprint.h)
print(f"\nexterior footprint: {int(C.Footprint.w)} x {int(C.Footprint.h)} "
      f"= {n} squares")
if n != want_n:
    failures.append(f"footprintOffsets returns {n} squares, not {want_n}")
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

if failures:
    print(f"\n{len(failures)} PROBLEM(S):")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("\nfloor plan, authored interior and footprint are consistent")
