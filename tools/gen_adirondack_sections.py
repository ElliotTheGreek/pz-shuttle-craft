"""The Adirondack's sections, drafted as BuildingEd files for the author to take on.

    python tools/gen_adirondack_sections.py            # every section
    python tools/gen_adirondack_sections.py bridge     # just one

Each section is a small spec below: rooms as rectangles, doors on edges, and
furniture placed by name and facing. From it this writes

  design/buildinged/Adirondack_<Section>.tbx     for BuildingEd
  design/art/adirondack/sections/<section>.png   an iso render of it, made of
                                                 the real tiles, to vet first

and refuses a spec that does not hold together: furniture off the floor or
across two rooms, two pieces on one square, a door that is not on a wall, or a
wall-hung piece with no wall behind it.

**These are drafts, and once the author has opened one in BuildingEd it is
theirs.** Running this again overwrites the .tbx, so it refuses to touch a file
BuildingEd has saved since (it checks for the marker property it writes) --
pass --force to replace it anyway.

Coordinates: x runs east, y south, (0,0) is the north-west square. Walls only
exist on the north and west edges of a square (the engine's rule), so anything
backed onto a wall stands against a north or a west one, as vanilla's own
furniture does. Facings are the furniture sheet's: W and N back onto a wall,
E and S face west and north. A door `("N", x, y)` sits on the north edge of
square (x, y); `("W", x, y)` on its west edge.
"""
import json
import os
import sys
from xml.sax.saxutils import quoteattr

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TILES = os.path.join(ROOT, "design", "tiles", "2x")
BED = os.path.join(ROOT, "design", "buildinged")
OUT = os.path.join(ROOT, "design", "art", "adirondack", "sections")
S1, S2 = "trek_adirondack_01", "trek_adirondack_02"
MARKER = "gen_adirondack_sections"
CW, CH = 128, 256

CARPET, DECK = 3, 4          # tile_entry indices below (1-based, as BuildingEd counts)


def room(name, internal, floor, x0, y0, x1, y1, color):
    """A room covering x0..x1, y0..y1 inclusive."""
    return dict(name=name, internal=internal, floor=floor, rect=(x0, y0, x1, y1), color=color)


# --- the sections ------------------------------------------------------------------

SECTIONS = {}

SECTIONS["transporter"] = dict(
    title="Transporter Room", size=(8, 7),
    rooms=[room("Transporter Room", "trektransporter", DECK, 0, 0, 7, 6, "150 170 200")],
    doors=[("W", 0, 5)],
    furniture=[
        ("transporter_pad", "N", 2, 0),
        ("transporter_console", "S", 3, 4),
        ("wall_sconce", "N", 1, 0), ("wall_sconce", "N", 6, 0),
        ("plaque", "N", 5, 0),
        ("turbolift_panel", "W", 0, 4),
        ("plant", "W", 7, 6),
    ])

SECTIONS["habitat"] = dict(
    title="Habitat Deck", size=(17, 14),
    rooms=[
        room("Quarters 1", "bedroom", CARPET, 0, 0, 8, 5, "72 96 160"),
        room("Quarters 1 Bath", "bathroom", DECK, 6, 0, 8, 1, "120 160 190"),
        room("Quarters 2", "bedroom", CARPET, 9, 0, 16, 5, "80 104 168"),
        room("Quarters 2 Bath", "bathroom", DECK, 14, 0, 16, 1, "120 160 190"),
        room("Corridor", "hall", DECK, 0, 6, 16, 7, "160 150 120"),
        room("Junior Quarters 3", "bedroom", CARPET, 0, 8, 8, 13, "88 88 150"),
        room("Junior Quarters 4", "bedroom", CARPET, 9, 8, 16, 13, "96 96 158"),
    ],
    doors=[("N", 2, 6), ("N", 7, 2), ("N", 11, 6), ("N", 15, 2),
           ("N", 4, 8), ("N", 11, 8), ("W", 0, 6)],
    furniture=[
        # quarters 1
        ("bed_double", "N", 1, 0), ("nightstand", "N", 0, 0), ("nightstand", "N", 3, 0),
        ("desk", "N", 4, 0), ("desk_chair", "N", 4, 1),
        ("wardrobe", "W", 0, 3), ("display_shelf", "W", 0, 4), ("replicator", "W", 0, 5),
        ("sofa", "S", 3, 5), ("coffee_table", "W", 4, 4), ("armchair", "E", 6, 4),
        ("plant", "W", 8, 5), ("painting_nebula", "W", 0, 2),
        ("sonic_shower", "N", 8, 0), ("toilet", "N", 7, 0), ("wash_basin", "W", 6, 1),
        # quarters 2
        ("bed_double", "N", 10, 0), ("nightstand", "N", 9, 0), ("nightstand", "N", 12, 0),
        ("wardrobe", "N", 13, 0), ("display_shelf", "W", 9, 2),
        ("desk", "W", 9, 3), ("desk_chair", "E", 10, 3), ("replicator", "W", 9, 5),
        ("armchair", "S", 12, 5), ("coffee_table", "W", 13, 4), ("plant", "W", 16, 5),
        ("sonic_shower", "N", 16, 0), ("toilet", "N", 15, 0), ("wash_basin", "W", 14, 1),
        # corridor
        ("wall_sconce", "N", 4, 6), ("turbolift_panel", "N", 8, 6),
        ("wall_sconce", "N", 13, 6), ("painting_ship", "N", 6, 6),
        # junior quarters 3: two bunks
        ("bunk", "W", 0, 9), ("bunk", "W", 0, 11),
        ("desk", "N", 1, 8), ("desk_chair", "N", 1, 9),
        ("wardrobe", "N", 6, 8), ("wardrobe", "N", 7, 8), ("display_shelf", "N", 8, 8),
        ("coffee_table", "W", 4, 11), ("armchair", "E", 5, 11),
        ("replicator", "W", 0, 13), ("plant", "W", 8, 13),
        # junior quarters 4: two singles
        ("bed", "W", 9, 9), ("nightstand", "W", 9, 10), ("bed", "W", 9, 12),
        ("nightstand", "W", 9, 11),
        ("desk", "N", 12, 8), ("desk_chair", "N", 12, 9),
        ("wardrobe", "N", 15, 8), ("wardrobe", "N", 16, 8), ("replicator", "N", 14, 8),
        ("plant", "W", 16, 13),
    ])

SECTIONS["lounge"] = dict(
    title="Lounge and Galley", size=(16, 11),
    rooms=[
        room("Lounge", "livingroom", CARPET, 0, 0, 10, 10, "90 110 170"),
        room("Galley", "kitchen", DECK, 11, 0, 15, 10, "170 160 130"),
    ],
    doors=[("W", 11, 5), ("W", 0, 6)],
    furniture=(
        [("viewport", "N", x, 0) for x in (1, 3, 5, 7, 9)]
        + [f for tx in (2, 5, 8) for ty in (3, 6)
           for f in (("lounge_table", "W", tx, ty), ("lounge_chair", "W", tx - 1, ty),
                     ("lounge_chair", "E", tx + 1, ty))]
        + [("bar_straight", "S", x, 9) for x in (2, 4, 6)]
        + [("bar_stool", "W", x, 8) for x in (2, 3, 4, 5, 6, 7)]
        + [("bottle_shelf", "W", 0, 8), ("bottle_shelf", "W", 0, 9),
           ("plant", "W", 0, 1), ("plant", "W", 10, 1), ("painting_ship", "W", 0, 4),
           ("wall_sconce", "W", 0, 2),
           # galley
           ("galley_counter", "N", 12, 0), ("galley_sink", "N", 14, 0),
           ("stasis_unit", "N", 15, 0), ("replicator", "W", 11, 1),
           ("galley_counter", "W", 11, 2),
           ("galley_counter", "N", 13, 4), ("galley_counter", "S", 13, 5),
           ("stasis_unit", "W", 11, 8), ("stasis_unit", "W", 11, 9),
           ("replicator", "N", 15, 0) if False else ("cargo_crate", "N", 15, 10),
           # A real stove (FARMING.md 3), against the east bulkhead.
           ("galley_range", "E", 15, 3)]))

# Deck 5 (FARMING.md 5): the hydroponics bay under its grow lights, the botany
# lab, and the serpent tank room. Three rows of seven trays with an aisle
# either side of every row, so every tray can be reached.
SECTIONS["hydroponics"] = dict(
    title="Hydroponics", size=(16, 14),
    rooms=[
        room("Hydroponics Bay", "hydroponics", DECK, 0, 0, 10, 13, "90 150 90"),
        room("Botany Lab", "hydroponics", DECK, 11, 0, 15, 6, "120 170 120"),
        room("Serpent Tank Room", "hydroponics", DECK, 11, 7, 15, 13, "140 90 90"),
    ],
    doors=[("W", 0, 8), ("W", 11, 5), ("W", 11, 8)],
    furniture=(
        [("hydro_tray", "W", x, y) for y in (2, 6, 10) for x in range(2, 9)]
        + [("grow_light", "N", x, 0) for x in (2, 4, 6, 8)]
        + [("grow_light", "W", 0, y) for y in (7, 11)]
        + [("wash_basin", "W", 0, 1), ("potting_bench", "N", 9, 0),
           ("arboretum_tree", "W", 10, 12), ("alien_shrub", "W", 9, 13),
           ("alien_shrub", "W", 0, 13), ("lounge_chair", "S", 10, 10),
           ("wall_sconce", "W", 0, 4)]
        # the botany lab
        + [("seed_locker", "N", 12, 0), ("seed_locker", "N", 13, 0),
           ("dehydrator", "N", 14, 0), ("replicator", "N", 15, 0),
           ("potting_bench", "W", 11, 1), ("desk", "W", 11, 3), ("desk_chair", "E", 12, 3),
           ("science_display", "N", 13, 0)]
        # the serpent tanks
        + [("worm_tank", "N", 12, 7), ("worm_tank", "W", 11, 10),
           ("wall_sconce", "N", 14, 7), ("cargo_crate", "N", 15, 13)]
    ))

SECTIONS["bridge"] = dict(
    title="Bridge and Ready Room", size=(15, 12),
    rooms=[
        room("Bridge", "office", CARPET, 0, 0, 10, 11, "150 60 60"),
        room("Ready Room", "office", CARPET, 11, 0, 14, 6, "120 70 70"),
    ],
    doors=[("W", 11, 3), ("W", 0, 9)],
    furniture=[
        ("viewport", "N", 4, 0), ("viewport", "N", 5, 0), ("viewport", "N", 6, 0),
        ("science_display", "N", 2, 0), ("science_display", "N", 8, 0),
        ("science_station", "N", 1, 0), ("science_station", "N", 9, 0),
        ("science_station", "W", 0, 2), ("science_station", "W", 0, 4),
        ("helm_console", "N", 4, 3), ("helm_console", "N", 6, 3),
        ("bridge_chair", "S", 4, 4), ("bridge_chair", "S", 6, 4),
        ("captain_chair", "S", 5, 6), ("bridge_chair", "S", 4, 6), ("bridge_chair", "S", 6, 6),
        ("railing", "N", 2, 8), ("railing", "N", 3, 8), ("railing", "N", 7, 8), ("railing", "N", 8, 8),
        ("tactical_rail", "S", 4, 9),
        ("turbolift_panel", "W", 0, 8), ("plant", "W", 10, 11),
        ("wall_sconce", "N", 3, 0), ("wall_sconce", "N", 7, 0),
        # ready room
        ("ready_room_desk", "N", 12, 2), ("desk_chair", "N", 12, 1),
        ("lounge_chair", "S", 12, 4), ("lounge_chair", "S", 13, 4),
        ("display_shelf", "N", 14, 0), ("painting_ship", "N", 13, 0),
        ("replicator", "W", 11, 6), ("plant", "W", 14, 6),
    ])

SECTIONS["sickbay"] = dict(
    title="Sickbay", size=(13, 9),
    rooms=[
        room("Sickbay", "medical", DECK, 0, 0, 8, 8, "200 200 210"),
        room("Chief Medical Officer", "office", CARPET, 9, 0, 12, 4, "150 170 200"),
        room("Medical Lab", "medical", DECK, 9, 5, 12, 8, "180 200 210"),
    ],
    doors=[("W", 9, 2), ("W", 9, 6), ("W", 0, 8)],
    furniture=[
        ("biobed", "N", 1, 0), ("biobed", "N", 3, 0), ("biobed", "N", 5, 0), ("biobed", "N", 7, 0),
        ("emh_station", "W", 0, 4), ("medical_cabinet", "W", 0, 5), ("medical_cabinet", "W", 0, 6),
        ("surgical_bed", "W", 3, 5), ("medical_cart", "S", 5, 5), ("medical_cart", "E", 6, 3),
        ("wall_sconce", "N", 0, 0), ("plant", "W", 8, 8),
        # office
        ("desk", "N", 10, 1), ("desk_chair", "N", 10, 0), ("display_shelf", "N", 12, 0),
        ("armchair", "S", 11, 3), ("plant", "W", 12, 4), ("painting_nebula", "N", 9, 0),
        # lab
        ("medical_cabinet", "N", 10, 5), ("medical_cabinet", "N", 11, 5), ("medical_cabinet", "N", 12, 5),
        ("medical_cart", "E", 12, 7), ("cargo_crate", "W", 12, 8),
    ])

SECTIONS["engineering"] = dict(
    title="Main Engineering", size=(15, 13),
    rooms=[room("Main Engineering", "storageunit", DECK, 0, 0, 14, 12, "190 150 90")],
    doors=[("W", 0, 11)],
    furniture=[
        ("warp_core", "W", 6, 4),
        ("railing", "S", 5, 6), ("railing", "S", 8, 6), ("railing", "N", 5, 3), ("railing", "N", 8, 3),
        ("master_systems", "W", 6, 8),
        ("engineering_console", "N", 2, 0), ("engineering_console", "N", 4, 0),
        ("engineering_console", "N", 10, 0), ("engineering_console", "N", 12, 0),
        ("engineering_console", "W", 0, 3), ("engineering_console", "W", 0, 5),
        ("engineering_console", "W", 0, 7),
        ("jefferies_hatch", "N", 7, 0), ("jefferies_hatch", "W", 0, 10),
        ("cargo_crate", "N", 12, 10), ("cargo_crate", "E", 13, 10), ("cargo_crate", "S", 12, 11),
        ("cargo_crate", "W", 13, 11), ("cargo_crate", "N", 14, 11),
        ("antigrav_cart", "W", 10, 11),
        ("wall_sconce", "N", 5, 0), ("wall_sconce", "N", 9, 0),
    ])


# --- the furniture the specs can name --------------------------------------------------

def catalogue():
    with open(os.path.join(ROOT, "design", "tiles", S2 + ".json")) as f:
        index = json.load(f)
    cat = {}
    for name, rec in index.items():
        cat[name] = dict(layer=rec["layer"],
                         facings={fc: [(x, y, "%s_%03d" % (S2, i)) for x, y, i in sq]
                                  for fc, sq in rec["facings"].items()})
    # The structural pieces from sheet 01 that stand in for furniture.
    cat["viewport"] = dict(layer="Walls", facings={"W": [(0, 0, "%s_016" % S1)],
                                                   "N": [(0, 0, "%s_017" % S1)]})
    return cat


# --- checking a section ----------------------------------------------------------------

def grid_of(sec):
    W, H = sec["size"]
    g = [[0] * W for _ in range(H)]
    for k, r in enumerate(sec["rooms"], start=1):
        x0, y0, x1, y1 = r["rect"]
        for y in range(y0, y1 + 1):
            for x in range(x0, x1 + 1):
                if not (0 <= x < W and 0 <= y < H):
                    raise SystemExit("%s: room %s leaves the building" % (sec["title"], r["name"]))
                g[y][x] = k
    return g


def at(g, x, y):
    return g[y][x] if 0 <= y < len(g) and 0 <= x < len(g[0]) else 0


def check(key, sec, cat):
    g = grid_of(sec)
    problems, taken = [], {}
    for name, facing, x, y in sec["furniture"]:
        if name not in cat:
            problems.append("%s is not in the furniture sheet" % name)
            continue
        if facing not in cat[name]["facings"]:
            problems.append("%s has no %s facing" % (name, facing))
            continue
        layer = cat[name]["layer"]
        squares = [(x + dx, y + dy) for dx, dy, _ in cat[name]["facings"][facing]]
        rooms = {at(g, sx, sy) for sx, sy in squares}
        if 0 in rooms:
            problems.append("%s %s at %d,%d is off the floor" % (name, facing, x, y))
        elif len(rooms) > 1:
            problems.append("%s %s at %d,%d straddles two rooms" % (name, facing, x, y))
        if layer in ("WallFurniture", "Walls"):
            nx, ny = (x - 1, y) if facing == "W" else (x, y - 1)
            if at(g, nx, ny) == at(g, x, y):
                problems.append("%s %s at %d,%d has no wall behind it" % (name, facing, x, y))
            continue
        for sq in squares:
            if sq in taken:
                problems.append("%s at %d,%d and %s share square %d,%d" % (name, x, y, taken[sq], sq[0], sq[1]))
            taken[sq] = name
    for d, x, y in sec["doors"]:
        a, b = at(g, x, y), (at(g, x - 1, y) if d == "W" else at(g, x, y - 1))
        if a == b:
            problems.append("door %s at %d,%d is not on a wall" % (d, x, y))
        if (x, y) in taken:
            problems.append("door at %d,%d opens onto %s" % (x, y, taken[(x, y)]))
    if problems:
        raise SystemExit("%s:\n  " % key + "\n  ".join(problems))
    return g


# --- the .tbx --------------------------------------------------------------------------

def t1(i):
    return "%s_%03d" % (S1, i)


def tbx(key, sec, cat, g):
    W, H = sec["size"]
    used = []
    for name, _, _, _ in sec["furniture"]:
        if name not in used:
            used.append(name)
    fidx = {n: k for k, n in enumerate(used)}
    out = ["<?xml version='1.0' encoding='UTF-8'?>",
           '<building version="3" width="%d" height="%d" ExteriorWall="1" ExteriorWallTrim="0" '
           'Door="5" DoorFrame="0" Window="0" Curtains="0" Shutters="0" Stairs="0" RoofCap="0" '
           'RoofSlope="0" RoofTop="0" GrimeWall="0">' % (W, H),
           " <properties>",
           '  <property name="Description" value=%s />' % quoteattr(
               "U.S.S. Adirondack: %s. Drafted by tools/gen_adirondack_sections.py; see ADIRONDACK.md" % sec["title"]),
           '  <property name="Mod" value="TrekShuttle" />',
           '  <property name="Generator" value="%s" />' % MARKER,
           " </properties>"]
    walls = [("West", 0), ("North", 1), ("NorthWest", 2), ("SouthEast", 3),
             ("WestWindow", None), ("NorthWindow", None), ("WestDoor", 10), ("NorthDoor", 11)]
    for cat_name in ("exterior_walls", "interior_walls"):
        out.append(' <tile_entry category="%s">' % cat_name)
        for enum, i in walls:
            out.append('  <tile enum="%s" tile="%s" />' % (enum, t1(i) if i is not None else ""))
        out.append(" </tile_entry>")
    for i in (24, 25):
        out.append(' <tile_entry category="floors">\n  <tile enum="Floor" tile="%s" />\n </tile_entry>' % t1(i))
    out.append(' <tile_entry category="doors">')
    for enum, i in (("West", 32), ("North", 33), ("WestOpen", 34), ("NorthOpen", 35)):
        out.append('  <tile enum="%s" tile="%s" />' % (enum, t1(i)))
    out.append(" </tile_entry>")
    for name in used:
        c = cat[name]
        layer = "" if c["layer"] == "Furniture" else ' layer="%s"' % c["layer"]
        out.append(" <furniture%s>" % layer)
        for fc in "WNES":
            if fc in c["facings"]:
                out.append('  <entry orient="%s">' % fc)
                for x, y, tile in c["facings"][fc]:
                    out.append('   <tile x="%d" y="%d" name="%s" />' % (x, y, tile))
                out.append("  </entry>")
        out.append(" </furniture>")
    out.append(" <user_tiles />")
    out.append(" <used_tiles>1 2 3 4 5</used_tiles>")
    out.append(" <used_furniture>%s</used_furniture>" % " ".join(str(i) for i in range(len(used))))
    for r in sec["rooms"]:
        out.append(' <room Name=%s InternalName="%s" Color="%s" InteriorWall="2" InteriorWallTrim="0" '
                   'Floor="%d" GrimeFloor="0" GrimeWall="0" />'
                   % (quoteattr(r["name"]), r["internal"], r["color"], r["floor"]))
    out.append(" <floor>")
    out.append("  <rooms>")
    out.append(",\n".join(",".join(str(v) for v in row) for row in g))
    out.append("</rooms>")
    for d, x, y in sec["doors"]:
        out.append('  <object type="door" x="%d" y="%d" dir="%s" Tile="5" FrameTile="0" />' % (x, y, d))
    for name, facing, x, y in sec["furniture"]:
        out.append('  <object type="furniture" FurnitureTiles="%d" orient="%s" x="%d" y="%d" />'
                   % (fidx[name], facing, x, y))
    out.append(" </floor>")
    out.append("</building>")
    return "\n".join(out) + "\n"


# --- the preview -------------------------------------------------------------------------

def sheet_tile(sheets, name):
    s, i = name.rsplit("_", 1)
    im = sheets[s]
    i = int(i)
    return im.crop(((i % 8) * CW, (i // 8) * CH, (i % 8) * CW + CW, (i // 8) * CH + CH))


def preview(key, sec, cat, g, path):
    W, H = sec["size"]
    sheets = {S1: Image.open(os.path.join(TILES, S1 + ".png")).convert("RGBA"),
              S2: Image.open(os.path.join(TILES, S2 + ".png")).convert("RGBA")}
    floor_tile = {CARPET: t1(24), DECK: t1(25)}
    ox, oy = 64 * H + 64, 220
    canvas = Image.new("RGBA", (64 * (W + H) + 256, 32 * (W + H) + 420), (14, 14, 20, 255))
    layers = {}

    def add(x, y, tile, order):
        layers.setdefault((x, y), []).append((order, tile))

    doors = {(x, y, d) for d, x, y in sec["doors"]}
    replaced = set()
    for name, facing, x, y in sec["furniture"]:
        c = cat[name]
        for dx, dy, tile in c["facings"][facing]:
            order = {"Walls": 1, "WallFurniture": 3}.get(c["layer"], 2)
            add(x + dx, y + dy, tile, order)
            if c["layer"] == "Walls":
                replaced.add((x + dx, y + dy, facing))
    for y in range(H + 1):
        for x in range(W + 1):
            here = at(g, x, y)
            west = here != at(g, x - 1, y) and (here or at(g, x - 1, y))
            north = here != at(g, x, y - 1) and (here or at(g, x, y - 1))
            if (x, y, "W") in doors:
                add(x, y, t1(10), 0)
                add(x, y, t1(32), 0.5)
                west = False
            if (x, y, "N") in doors:
                add(x, y, t1(11), 0)
                add(x, y, t1(33), 0.5)
                north = False
            if (x, y, "W") in replaced:
                west = False
            if (x, y, "N") in replaced:
                north = False
            if west and north:
                add(x, y, t1(2), 0)
            elif west:
                add(x, y, t1(0), 0)
            elif north:
                add(x, y, t1(1), 0)
    for y in range(H):
        for x in range(W):
            if g[y][x]:
                canvas.alpha_composite(sheet_tile(sheets, floor_tile[sec["rooms"][g[y][x] - 1]["floor"]]),
                                       (ox + 64 * (x - y) - 64, oy + 32 * (x + y) - 192))
    # A dollhouse view, as the game's cutaway gives: the outer walls on the
    # south and east are left off, and inner walls are drawn see-through, so
    # every room can be judged from one picture.
    for (x, y) in sorted(layers, key=lambda k: (k[0] + k[1], k[0])):
        for order, tile in sorted(layers[(x, y)]):
            if order < 1 and (x == W or y == H):
                continue
            img = sheet_tile(sheets, tile)
            inner = 0 < x < W and 0 < y < H
            if order < 1 and inner:
                a = img.split()[3].point(lambda v: v * 45 // 100)
                img.putalpha(a)
            canvas.alpha_composite(img, (ox + 64 * (x - y) - 64, oy + 32 * (x + y) - 192))
    d = ImageDraw.Draw(canvas)
    d.text((16, 16), "U.S.S. Adirondack -- %s  (%d x %d)" % (sec["title"], W, H), fill=(230, 230, 230, 255))
    save(canvas, path)


def save(img, path):
    """Write via a temporary name and swap it in. On this machine a PNG that
    was just opened elsewhere refuses a direct overwrite (Errno 22), briefly."""
    import time
    tmp = path + ".tmp.png"
    img.save(tmp)
    for _ in range(20):
        try:
            os.replace(tmp, path)
            return
        except OSError:
            time.sleep(0.25)
    raise SystemExit("could not replace %s" % path)


def main():
    force = "--force" in sys.argv
    wanted = [a for a in sys.argv[1:] if not a.startswith("--")] or list(SECTIONS)
    cat = catalogue()
    os.makedirs(OUT, exist_ok=True)
    for key in wanted:
        sec = SECTIONS[key]
        g = check(key, sec, cat)
        path = os.path.join(BED, "Adirondack_%s.tbx" % sec["title"].replace(" and ", "_").replace(" ", ""))
        if os.path.exists(path) and not force:
            with open(path, encoding="utf-8") as f:
                if MARKER not in f.read():
                    print("%s: %s has been saved by BuildingEd -- not overwriting (use --force)"
                          % (key, os.path.basename(path)))
                    preview(key, sec, cat, g, os.path.join(OUT, key + ".png"))
                    continue
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(tbx(key, sec, cat, g))
        preview(key, sec, cat, g, os.path.join(OUT, key + ".png"))
        print("%-12s %-28s %2d rooms, %2d doors, %3d pieces" % (
            key, os.path.basename(path), len(sec["rooms"]), len(sec["doors"]), len(sec["furniture"])))


if __name__ == "__main__":
    main()
