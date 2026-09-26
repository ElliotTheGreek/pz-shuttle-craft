"""The composed Adirondack, written out as data the game builds from.

    python tools/gen_adirondack_lua.py

Reads design/buildinged/Adirondack_Ship.tbx (compose_adirondack.py's output)
and the tile definitions gen_adirondack_pack.py wrote, and writes

  TrekShuttle/42/media/lua/shared/TREK/TREK_AdirondackLayout.lua

**The decks stand side by side in the game, not stacked.** The tbx has a floor
per deck because that is how BuildingEd holds a building. But a ship raised at
runtime has no RoomDefs, and without them the engine draws every level above
the player over them (TREK_Config, beside CabinZ): Deck 2 would be drawn
across the whole of Deck 3. So every deck is built on the same level, one
beside the next, and the turbolift is a move sideways that looks like a move
up. The lifts still line up (same squares on every deck), so the move is the
same offset every time.

Every piece is resolved here, in Python, where it can be checked: which wall
sprite stands on which edge, which doorway gets a door, which objects hold
things. The Lua only places what it is given. Walls follow BuildingEd's rule --
a wall on every edge between two different rooms or a room and nothing --
exactly as compose_adirondack.preview_deck draws them.
"""
import hashlib
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compose_adirondack as COMP  # noqa: E402
import gen_adirondack_pack as PACK  # noqa: E402

ROOT = COMP.ROOT
OUT = os.path.join(ROOT, "TrekShuttle", "42", "media", "lua", "shared", "TREK",
                   "TREK_AdirondackLayout.lua")
# Squares between one deck's west edge and the next one's. Wide enough that no
# wall of one deck is ever on a square the next one clears.
DECK_PITCH = 32
DECK_FLOOR = "trek_adirondack_01_25"


def unpad(name):
    """BuildingEd pads sprite indices (_025); the engine does not (_25)."""
    sheet, _, i = name.rpartition("_")
    return "%s_%d" % (sheet, int(i))


def main():
    ship = COMP.read_tbx(COMP.OUT_TBX)
    W, H = ship["W"], ship["H"]
    defs = PACK.read_tiledefs(PACK.TILES)
    props = {}
    for sheet, ts in defs.items():
        for i, p in enumerate(ts["tiles"]):
            props["%s_%d" % (sheet, i)] = p

    def entry_tile(idx, enum):
        if not idx:
            return ""
        return dict(ship["entries"][idx - 1][1]).get(enum, "")

    # Which piece of furniture each sprite is part of (bed, replicator,
    # medical_cabinet...): the name the Lua decides behaviour by -- what a
    # container is stocked with, which squares answer as a replicator.
    with open(os.path.join(ROOT, "design", "tiles", "trek_adirondack_02.json")) as f:
        index = COMP.json.load(f)
    piece = {}
    for pname, rec in index.items():
        for squares in rec["facings"].values():
            for _, _, i in squares:
                piece["trek_adirondack_02_%d" % i] = pname

    names = {}
    for z, fl in enumerate(ship["floors"]):
        for rid in {v for row in fl["grid"] for v in row if v}:
            names[rid] = ship["rooms"][rid - 1]["Name"]
    decks = []
    for z, fl in enumerate(ship["floors"]):
        grid = fl["grid"]

        def room(x, y):
            return grid[y][x] if 0 <= x < W and 0 <= y < H else 0

        objs = []
        doors, replaced = {}, set()
        for o in fl["objects"]:
            x, y = int(o["x"]), int(o["y"])
            if o["type"] == "door":
                doors[(x, y, o["dir"])] = int(o.get("Tile", 0))
            elif o["type"] == "furniture":
                fdef = ship["furniture"][int(o["FurnitureTiles"])]
                for orient, tiles in fdef["entries"]:
                    if orient != o["orient"]:
                        continue
                    for dx, dy, name in tiles:
                        sprite = unpad(name)
                        p = props.get(sprite)
                        if p is None:
                            raise SystemExit("%s is not in the tile definitions" % sprite)
                        kind = "f"
                        if fdef["layer"] == "Walls":
                            kind = "w"
                            replaced.add((x + dx, y + dy, orient))
                        elif "container" in p:
                            kind = "c"
                        objs.append((x + dx, y + dy, sprite, kind, piece.get(sprite, "")))

        structure = []
        extra_floor = set()
        for y in range(H + 1):
            for x in range(W + 1):
                here, w_other, n_other = room(x, y), room(x - 1, y), room(x, y - 1)
                west = here != w_other and bool(here or w_other)
                north = here != n_other and bool(here or n_other)
                rid = here or w_other or n_other
                wall_idx = int(ship["rooms"][rid - 1].get("InteriorWall", 0)) if rid else 0
                if (west or north) and not here:
                    extra_floor.add((x, y))
                for d, flag in (("W", west), ("N", north)):
                    if flag and (x, y, d) in doors:
                        structure.append((x, y, unpad(entry_tile(wall_idx, d == "W" and "WestDoor" or "NorthDoor")), "w"))
                        structure.append((x, y, unpad(entry_tile(doors[(x, y, d)], d == "W" and "West" or "North")),
                                          "dW" if d == "W" else "dN"))
                west = west and (x, y, "W") not in doors and (x, y, "W") not in replaced
                north = north and (x, y, "N") not in doors and (x, y, "N") not in replaced
                if west and north:
                    structure.append((x, y, unpad(entry_tile(wall_idx, "NorthWest")), "w"))
                elif west:
                    structure.append((x, y, unpad(entry_tile(wall_idx, "West")), "w"))
                elif north:
                    structure.append((x, y, unpad(entry_tile(wall_idx, "North")), "w"))
                elif (room(x, y - 1) != room(x - 1, y - 1) and (room(x, y - 1) or room(x - 1, y - 1))
                      and room(x - 1, y) != room(x - 1, y - 1) and (room(x - 1, y) or room(x - 1, y - 1))):
                    # The corner post where a wall from the north meets one
                    # from the west and neither carries on across this square.
                    structure.append((x, y, unpad(entry_tile(wall_idx or 2, "SouthEast")), "w"))
        for (x, y, dd) in doors:
            if not any(s[0] == x and s[1] == y and s[3] in ("dW", "dN") for s in structure):
                raise SystemExit("deck z%d: the door at %d,%d %s is on no wall" % (z, x, y, dd))

        floors = {}
        for y in range(H):
            for x in range(W):
                rid = grid[y][x]
                if rid:
                    fl_idx = int(ship["rooms"][rid - 1].get("Floor", 0))
                    floors[(x, y)] = unpad(entry_tile(fl_idx, "Floor")) or DECK_FLOOR
        for xy in extra_floor:
            floors.setdefault(xy, DECK_FLOOR)
        decks.append(dict(z=z, grid=grid, structure=structure, objs=objs, floors=floors))

    layout = COMP.json.load(open(COMP.OUT_LAYOUT))
    by_z = {d["z"]: d for d in layout["decks"]}
    # Deck 1 first: the order the turbolift lists them in, bridge at the top.
    order = sorted(range(len(decks)), key=lambda z: -z)

    # The pad: every square of the platform, and the arrival is the one
    # nearest the room's middle, so nobody materialises against a wall.
    pz = layout["pad"]["z"]
    pad_squares = [(o[0], o[1]) for o in decks[pz]["objs"] if o[4] == "transporter_pad"]
    if not pad_squares:
        raise SystemExit("no transporter pad squares on deck z%d" % pz)
    pad = max(pad_squares, key=lambda p: (p[1], -abs(p[0] - layout["pad"]["x"])))

    lift = layout["turbolifts"][0]
    lift_room = None
    for rid, r in enumerate(ship["rooms"], start=1):
        if r.get("InternalName") == "trekturbolift":
            cells = [(x, y) for d in decks for y, row in enumerate(d["grid"]) for x, v in enumerate(row) if v == rid]
            xs, ys = [c[0] for c in cells], [c[1] for c in cells]
            box = (min(xs), min(ys), max(xs), max(ys))
            if lift_room and box != lift_room:
                raise SystemExit("the turbolift cars do not line up: %s vs %s" % (box, lift_room))
            lift_room = box

    # --- write --------------------------------------------------------------------------
    def q(s):
        return '"%s"' % s.replace("\\", "\\\\").replace('"', '\\"')

    out = []
    out.append("-- GENERATED by tools/gen_adirondack_lua.py from design/buildinged/Adirondack_Ship.tbx.")
    out.append("-- Do not edit: change a section in BuildingEd, compose, and generate again.")
    out.append("local L = {}")
    out.append("L.W, L.H = %d, %d" % (W, H))
    out.append("L.pitch = %d" % DECK_PITCH)
    out.append("L.deckFloor = %s" % q(DECK_FLOOR))
    out.append("L.lift = { x0 = %d, y0 = %d, x1 = %d, y1 = %d, x = %d, y = %d }"
               % (lift_room + (lift["x"], lift["y"])))
    out.append("L.pad = { deck = %d, x = %d, y = %d }" % (order.index(pz) + 1, pad[0], pad[1]))
    # The place each room is, for the crew's talk (CREW.md 4.1): which scenes
    # and barks may play there. By the room's name, which is the author's.
    def place(r):
        name, internal = r["Name"], r.get("InternalName", "")
        if internal == "trekturbolift":
            return "lift"
        for key, tag in (("Bridge", "bridge"), ("Ready Room", "readyroom"), ("Lounge", "lounge"),
                         ("Galley", "galley"), ("Quarters", "quarters"), ("Transporter", "transporter"),
                         ("Sickbay", "sickbay"), ("Medical", "sickbay"), ("Engineering", "engineering")):
            if key in name:
                return tag
        if name == "Corridor":
            return "habitat"
        if "Corridor" in name:
            return "corridor"
        raise SystemExit("room %r has no place tag: add it to place() in gen_adirondack_lua.py" % name)

    out.append("L.rooms = {")
    for rid in range(1, len(ship["rooms"]) + 1):
        r = ship["rooms"][rid - 1]
        out.append("  { name = %s, internal = %s, place = %s }," % (
            q(r["Name"]), q(r.get("InternalName", "")), q(place(r))))
    out.append("}")
    out.append("L.decks = {")
    body = []
    for n, z in enumerate(order, start=1):
        d = decks[z]
        info = by_z.get(z, {})
        body.append("  {")
        body.append("    name = %s, description = %s, ox = %d,"
                    % (q(info.get("deck", "Deck %d" % n)), q(info.get("description", "")), (n - 1) * DECK_PITCH))
        body.append("    -- Room index per square, one row per line: %d rows of %d." % (H, W))
        body.append("    grid = {")
        for row in d["grid"]:
            body.append("      { %s }," % ", ".join(str(v) for v in row))
        body.append("    },")
        body.append("    floors = {")
        for (x, y), s in sorted(d["floors"].items(), key=lambda kv: (kv[0][1], kv[0][0])):
            body.append("      { %d, %d, %s }," % (x, y, q(s)))
        body.append("    },")
        body.append("    -- x, y, sprite, kind (w wall, dW/dN door, f furniture, c container), piece, facing.")
        body.append("    objects = {")
        for o in d["structure"] + d["objs"]:
            x, y, s, k = o[:4]
            what = o[4] if len(o) > 4 and o[4] else None
            # A piece's facing, off its tile: where somebody stands to use it,
            # and which way they sit in it.
            face = props.get(s, {}).get("Facing") if what else None
            tail = ""
            if what:
                tail = ", " + q(what) + ((", " + q(face)) if face else "")
            body.append("      { %d, %d, %s, %s%s }," % (x, y, q(s), q(k), tail))
        body.append("    },")
        body.append("  },")
    out.extend(body)
    out.append("}")
    digest = hashlib.sha1("\n".join(body).encode()).hexdigest()
    out.insert(3, "-- Changes whenever anything placed changes; a deck built by another is brought up to date.")
    out.insert(4, "L.rev = %d" % (int(digest[:7], 16)))
    out.append("return L")
    with open(OUT, "w", newline="\n") as f:
        f.write("\n".join(out) + "\n")
    total = sum(len(d["structure"]) + len(d["objs"]) for d in decks)
    print("wrote %s: %d decks, %d objects, pad deck %d at %d,%d, lift %s"
          % (os.path.relpath(OUT, ROOT), len(decks), total, order.index(pz) + 1, pad[0], pad[1], lift_room))


if __name__ == "__main__":
    main()
