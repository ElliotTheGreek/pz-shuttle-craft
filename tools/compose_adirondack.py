"""Compose the whole U.S.S. Adirondack from its sections: one building, a floor per deck.

    python tools/compose_adirondack.py

Reads the section files in design/buildinged/ (Adirondack_*.tbx -- whatever the
author last saved in BuildingEd, or the drafts gen_adirondack_sections.py
wrote), lays them out deck by deck per DECKS below, adds a spine corridor and a
turbolift car on every deck, and writes

  design/buildinged/Adirondack_Ship.tbx         the whole ship; do not edit it,
                                                edit a section and compose again
  design/art/adirondack/decks/deck<N>.png       a dollhouse render of each deck
  design/tiles/adirondack_layout.json           where the game code finds
                                                things: the turbolift on each
                                                deck, the transporter pad

Why one building: WorldEd places lots, and a lot is one map; a BuildingEd
building can hold several floors. So the ship is a single lot with a floor per
deck, and the sections stay separate files the author can rework one at a time.

**The turbolifts line up by construction.** Every deck's car is the same 3x3
room at the same squares (x 0..2, y 0..2), so moving between decks changes only
the floor: the destination is in the same chunk column and already loaded --
the problem the transporter spent a release on does not arise.

Each section sits east of its deck's spine (x from 3), stacked north to south,
and must have a door on its west wall where the spine can meet it; the composer
checks that.

The game code finds a turbolift by its room's InternalName, `trekturbolift`,
and the transporter room by `trektransporter`, so nothing in Lua depends on a
coordinate a later edit could move -- except the arrival pad, which a beam has
to know before the ship's chunks exist, and which is written to the layout file.
"""
import json
import os
import sys
import xml.etree.ElementTree as ET
from xml.sax.saxutils import quoteattr

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_adirondack_sections as SEC  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BED = os.path.join(ROOT, "design", "buildinged")
OUT_TBX = os.path.join(BED, "Adirondack_Ship.tbx")
OUT_ART = os.path.join(ROOT, "design", "art", "adirondack", "decks")
OUT_LAYOUT = os.path.join(ROOT, "design", "tiles", "adirondack_layout.json")
VANILLA = os.environ.get("PZ_TILES",
                         r"D:/SteamLibrary/steamapps/common/Project Zomboid Modding Tools/Tiles/2x")

SPINE_X = 3                      # sections start here; the spine is x 0..2
LIFT = (0, 0, 2, 2)              # the turbolift car, identical on every deck

# Top deck last: BuildingEd numbers floors from the ground up.
DECKS = [
    (0, "Deck 4", "Main Engineering", ["Adirondack_MainEngineering.tbx"]),
    (1, "Deck 3", "Transporter Room, Sickbay", ["Adirondack_TransporterRoom.tbx", "Adirondack_Sickbay.tbx"]),
    (2, "Deck 2", "Lounge, Habitat", ["Adirondack_Lounge_Galley.tbx", "Adirondack_HabitatDeck.tbx"]),
    (3, "Deck 1", "Bridge", ["Adirondack_Bridge_ReadyRoom.tbx"]),
    (4, "Deck 5", "Hydroponics", ["Adirondack_Hydroponics.tbx"]),
]

# Attributes of an object that name a tile_entry (1-based) or a furniture (0-based).
ENTRY_ATTRS = ("Tile", "FrameTile", "CurtainsTile", "ShuttersTile", "InteriorTile",
               "ExteriorTrim", "InteriorTrim", "CapTiles", "SlopeTiles", "TopTiles")
ROOM_ATTRS = ("InteriorWall", "InteriorWallTrim", "Floor", "GrimeFloor", "GrimeWall")


# --- reading a .tbx ------------------------------------------------------------------

def read_tbx(path):
    root = ET.parse(path).getroot()
    W, H = int(root.get("width")), int(root.get("height"))
    entries = []
    for te in root.findall("tile_entry"):
        entries.append((te.get("category"),
                        tuple((t.get("enum"), t.get("tile") or "") for t in te.findall("tile"))))
    furniture = []
    for fu in root.findall("furniture"):
        furniture.append(dict(
            layer=fu.get("layer"), corners=fu.get("corners"),
            entries=[(e.get("orient"), [(int(t.get("x")), int(t.get("y")), t.get("name"))
                                        for t in e.findall("tile")]) for e in fu.findall("entry")]))
    rooms = [dict(r.attrib) for r in root.findall("room")]
    floors = []
    for fl in root.findall("floor"):
        vals = [int(v) for v in (fl.findtext("rooms") or "").replace("\n", "").split(",") if v.strip()]
        grid = [vals[y * W:(y + 1) * W] for y in range(H)] if len(vals) >= W * H else [[0] * W for _ in range(H)]
        floors.append(dict(grid=grid, objects=[dict(o.attrib) for o in fl.findall("object")]))
    return dict(W=W, H=H, attrs=dict(root.attrib), entries=entries, furniture=furniture,
                rooms=rooms, floors=floors, path=path)


# --- composing ---------------------------------------------------------------------------

class Ship:
    def __init__(self):
        self.entries, self.entry_key = [], {}
        self.furniture, self.furn_key = [], {}
        self.rooms = []
        self.floors = {}

    def entry(self, category, tiles):
        key = (category, tuple(tiles))
        if key not in self.entry_key:
            self.entries.append(key)
            self.entry_key[key] = len(self.entries)          # 1-based
        return self.entry_key[key]

    def furn(self, f):
        key = json.dumps([f["layer"], f["corners"], f["entries"]])
        if key not in self.furn_key:
            self.furniture.append(f)
            self.furn_key[key] = len(self.furniture) - 1      # 0-based
        return self.furn_key[key]

    def room(self, attrs):
        self.rooms.append(attrs)
        return len(self.rooms)

    def floor(self, z):
        return self.floors.setdefault(z, dict(cells={}, objects=[]))


def walls_entry(ship, category):
    t1 = SEC.t1
    return ship.entry(category, [("West", t1(0)), ("North", t1(1)), ("NorthWest", t1(2)),
                                 ("SouthEast", t1(3)), ("WestWindow", ""), ("NorthWindow", ""),
                                 ("WestDoor", t1(10)), ("NorthDoor", t1(11))])


def add_section(ship, sec, z0, ox, oy):
    emap = {k + 1: ship.entry(*e) for k, e in enumerate(sec["entries"])}
    fmap = {k: ship.furn(f) for k, f in enumerate(sec["furniture"])}
    rmap = {}
    for k, r in enumerate(sec["rooms"], start=1):
        r = dict(r)
        for a in ROOM_ATTRS:
            if a in r and r[a] not in ("0", ""):
                r[a] = str(emap.get(int(r[a]), 0))
        rmap[k] = ship.room(r)
    for level, fl in enumerate(sec["floors"]):
        f = ship.floor(z0 + level)
        for y, row in enumerate(fl["grid"]):
            for x, v in enumerate(row):
                if v:
                    key = (ox + x, oy + y)
                    if key in f["cells"]:
                        raise SystemExit("%s overlaps something at %s on floor %d"
                                         % (os.path.basename(sec["path"]), key, z0 + level))
                    f["cells"][key] = rmap[v]
        for o in fl["objects"]:
            o = dict(o)
            o["x"] = str(int(o["x"]) + ox)
            o["y"] = str(int(o["y"]) + oy)
            for a in ENTRY_ATTRS:
                if a in o and o[a] not in ("0", ""):
                    o[a] = str(emap.get(int(o[a]), 0))
            if "FurnitureTiles" in o:
                o["FurnitureTiles"] = str(fmap[int(o["FurnitureTiles"])])
            f["objects"].append(o)


def compose():
    ship = Ship()
    ext = walls_entry(ship, "exterior_walls")
    inner = walls_entry(ship, "interior_walls")
    deck = ship.entry("floors", [("Floor", SEC.t1(25))])
    door = ship.entry("doors", [("West", SEC.t1(32)), ("North", SEC.t1(33)),
                                ("WestOpen", SEC.t1(34)), ("NorthOpen", SEC.t1(35))])
    cat = SEC.catalogue()

    def furniture_object(f, name, facing, x, y):
        c = cat[name]
        fdef = dict(layer=None if c["layer"] == "Furniture" else c["layer"], corners=None,
                    entries=[(fc, [list(t) for t in c["facings"][fc]]) for fc in "WNES" if fc in c["facings"]])
        fdef["entries"] = [(o, [tuple(t) for t in ts]) for o, ts in fdef["entries"]]
        f["objects"].append(dict(type="furniture", FurnitureTiles=str(ship.furn(fdef)),
                                 orient=facing, x=str(x), y=str(y)))

    layout = dict(turbolifts=[], decks=[], spine_x=SPINE_X)
    width = height = 0
    for z, deck_name, desc, files in DECKS:
        f = ship.floor(z)
        oy = 0
        entrances = []
        for name in files:
            sec = read_tbx(os.path.join(BED, name))
            add_section(ship, sec, z, SPINE_X, oy)
            doors = [int(o["y"]) for o in sec["floors"][0]["objects"]
                     if o.get("type") == "door" and o.get("dir") == "W" and int(o["x"]) == 0]
            if not doors:
                raise SystemExit("%s has no door on its west wall for the spine to meet" % name)
            entrances += [oy + d for d in doors]
            width = max(width, SPINE_X + sec["W"])
            oy += sec["H"]
        height = max(height, oy)
        corridor_end = max(max(entrances), LIFT[3] + 2)
        lift = ship.room(dict(Name="Turbolift (%s)" % deck_name, InternalName="trekturbolift",
                              Color="200 170 90", InteriorWall=str(inner), InteriorWallTrim="0",
                              Floor=str(deck), GrimeFloor="0", GrimeWall="0"))
        hall = ship.room(dict(Name="%s Corridor" % deck_name, InternalName="hall",
                              Color="160 150 120", InteriorWall=str(inner), InteriorWallTrim="0",
                              Floor=str(deck), GrimeFloor="0", GrimeWall="0"))
        for y in range(LIFT[1], LIFT[3] + 1):
            for x in range(LIFT[0], LIFT[2] + 1):
                f["cells"][(x, y)] = lift
        for y in range(LIFT[3] + 1, corridor_end + 1):
            for x in range(0, SPINE_X):
                f["cells"][(x, y)] = hall
        f["objects"].append(dict(type="door", x="1", y=str(LIFT[3] + 1), dir="N", Tile=str(door), FrameTile="0"))
        furniture_object(f, "turbolift_panel", "W", 0, 1)
        furniture_object(f, "wall_sconce", "N", 1, 0)
        furniture_object(f, "turbolift_panel", "W", 0, LIFT[3] + 2)
        for y in range(LIFT[3] + 5, corridor_end + 1, 4):
            furniture_object(f, "wall_sconce", "W", 0, y)
        # Every deck has water and a Doctor within reach of the lift (asked
        # for after the first walk round her): a basin and an EMH station
        # against the corridor's west wall, leaving two squares to walk by.
        if corridor_end < LIFT[3] + 6:
            raise SystemExit("%s's corridor is too short for its basin and EMH station" % deck_name)
        furniture_object(f, "wash_basin", "W", 0, LIFT[3] + 4)
        furniture_object(f, "emh_station", "W", 0, LIFT[3] + 6)
        layout["turbolifts"].append(dict(deck=deck_name, z=z, x=1, y=1, description=desc))
        layout["decks"].append(dict(deck=deck_name, z=z, sections=files, description=desc))
    return ship, width, height, layout, ext, door


def find_pad(ship, layout):
    """The arrival square: the middle of the transporter platform."""
    cat = SEC.catalogue()
    pad_tiles = {t for fc in cat["transporter_pad"]["facings"].values() for _, _, t in fc}
    for z, f in ship.floors.items():
        for o in f["objects"]:
            if o.get("type") != "furniture":
                continue
            fdef = ship.furniture[int(o["FurnitureTiles"])]
            for orient, tiles in fdef["entries"]:
                if orient == o["orient"] and any(t[2] in pad_tiles for t in tiles):
                    xs = [int(o["x"]) + t[0] for t in tiles]
                    ys = [int(o["y"]) + t[1] for t in tiles]
                    layout["pad"] = dict(z=z, x=round(sum(xs) / len(xs)), y=round(sum(ys) / len(ys)))
                    return
    raise SystemExit("no transporter pad anywhere aboard")


# --- writing ---------------------------------------------------------------------------------

def write_tbx(ship, W, H, ext, door):
    out = ["<?xml version='1.0' encoding='UTF-8'?>",
           '<building version="3" width="%d" height="%d" ExteriorWall="%d" ExteriorWallTrim="0" '
           'Door="%d" DoorFrame="0" Window="0" Curtains="0" Shutters="0" Stairs="0" RoofCap="0" '
           'RoofSlope="0" RoofTop="0" GrimeWall="0">' % (W, H, ext, door),
           " <properties>",
           '  <property name="Description" value="U.S.S. Adirondack, all decks. COMPOSED by '
           'tools/compose_adirondack.py from the section files: edit a section, not this." />',
           '  <property name="Mod" value="TrekShuttle" />',
           " </properties>"]
    for cat, tiles in ship.entries:
        out.append(' <tile_entry category="%s">' % cat)
        for enum, tile in tiles:
            out.append('  <tile enum="%s" tile="%s" />' % (enum, tile))
        out.append(" </tile_entry>")
    for fdef in ship.furniture:
        attrs = ""
        if fdef["layer"]:
            attrs += ' layer="%s"' % fdef["layer"]
        if fdef["corners"]:
            attrs += ' corners="%s"' % fdef["corners"]
        out.append(" <furniture%s>" % attrs)
        for orient, tiles in fdef["entries"]:
            out.append('  <entry orient="%s">' % orient)
            for x, y, name in tiles:
                out.append('   <tile x="%d" y="%d" name="%s" />' % (x, y, name))
            out.append("  </entry>")
        out.append(" </furniture>")
    out.append(" <user_tiles />")
    out.append(" <used_tiles>%s</used_tiles>" % " ".join(str(i + 1) for i in range(len(ship.entries))))
    out.append(" <used_furniture>%s</used_furniture>" % " ".join(str(i) for i in range(len(ship.furniture))))
    for r in ship.rooms:
        out.append(" <room " + " ".join("%s=%s" % (k, quoteattr(v)) for k, v in r.items()) + " />")
    for z in range(max(ship.floors) + 1):
        f = ship.floors.get(z, dict(cells={}, objects=[]))
        out.append(" <floor>")
        out.append("  <rooms>")
        out.append(",\n".join(",".join(str(f["cells"].get((x, y), 0)) for x in range(W)) for y in range(H)))
        out.append("</rooms>")
        for o in f["objects"]:
            out.append("  <object " + " ".join("%s=%s" % (k, quoteattr(v)) for k, v in o.items()) + " />")
        out.append(" </floor>")
    out.append("</building>")
    with open(OUT_TBX, "w", encoding="utf-8", newline="\n") as fh:
        fh.write("\n".join(out) + "\n")


# --- the deck previews ------------------------------------------------------------------------

_SHEETS = {}


def tile_image(name):
    sheet, i = name.rsplit("_", 1)
    if sheet not in _SHEETS:
        local = os.path.join(SEC.TILES, sheet + ".png")
        path = local if os.path.exists(local) else os.path.join(VANILLA, sheet + ".png")
        _SHEETS[sheet] = Image.open(path).convert("RGBA")
    im, i = _SHEETS[sheet], int(i)
    return im.crop(((i % 8) * 128, (i // 8) * 256, (i % 8) * 128 + 128, (i // 8) * 256 + 256))


def preview_deck(ship, W, H, z, title, path):
    f = ship.floors[z]
    cells = f["cells"]
    ox, oy = 64 * H + 64, 220
    canvas = Image.new("RGBA", (64 * (W + H) + 256, 32 * (W + H) + 420), (14, 14, 20, 255))
    layers = {}

    def add(x, y, name, order):
        layers.setdefault((x, y), []).append((order, name))

    def entry_tile(idx, enum):
        if not idx:
            return ""
        return dict(ship.entries[idx - 1][1]).get(enum, "")

    doors = {}
    replaced = set()
    for o in f["objects"]:
        x, y = int(o["x"]), int(o["y"])
        if o.get("type") == "door":
            doors[(x, y, o["dir"])] = int(o.get("Tile", 0))
        elif o.get("type") == "furniture":
            fdef = ship.furniture[int(o["FurnitureTiles"])]
            for orient, tiles in fdef["entries"]:
                if orient != o["orient"]:
                    continue
                for dx, dy, name in tiles:
                    order = {"Walls": 1, "WallFurniture": 3}.get(fdef["layer"], 2)
                    add(x + dx, y + dy, name, order)
                    if fdef["layer"] == "Walls":
                        replaced.add((x + dx, y + dy, orient))
    for y in range(H + 1):
        for x in range(W + 1):
            here = cells.get((x, y), 0)
            w_other, n_other = cells.get((x - 1, y), 0), cells.get((x, y - 1), 0)
            west = here != w_other and (here or w_other)
            north = here != n_other and (here or n_other)
            r = ship.rooms[(here or w_other or n_other) - 1] if (here or w_other or n_other) else None
            wall_idx = int(r.get("InteriorWall", 0)) if r else 0
            for d, flag in (("W", west), ("N", north)):
                if (x, y, d) in doors:
                    add(x, y, entry_tile(wall_idx, "WestDoor" if d == "W" else "NorthDoor"), 0)
                    add(x, y, entry_tile(doors[(x, y, d)], "West" if d == "W" else "North"), 0.5)
            west = west and (x, y, "W") not in doors and (x, y, "W") not in replaced
            north = north and (x, y, "N") not in doors and (x, y, "N") not in replaced
            if west and north:
                add(x, y, entry_tile(wall_idx, "NorthWest"), 0)
            elif west:
                add(x, y, entry_tile(wall_idx, "West"), 0)
            elif north:
                add(x, y, entry_tile(wall_idx, "North"), 0)
    for (x, y), rid in cells.items():
        fl = int(ship.rooms[rid - 1].get("Floor", 0))
        name = entry_tile(fl, "Floor")
        if name:
            canvas.alpha_composite(tile_image(name), (ox + 64 * (x - y) - 64, oy + 32 * (x + y) - 192))
    for (x, y) in sorted(layers, key=lambda k: (k[0] + k[1], k[0])):
        for order, name in sorted(layers[(x, y)]):
            if not name or (order < 1 and (x == W or y == H)):
                continue
            img = tile_image(name)
            if order < 1 and 0 < x < W and 0 < y < H:
                img.putalpha(img.split()[3].point(lambda v: v * 45 // 100))
            canvas.alpha_composite(img, (ox + 64 * (x - y) - 64, oy + 32 * (x + y) - 192))
    ImageDraw.Draw(canvas).text((16, 16), "U.S.S. Adirondack -- %s" % title, fill=(230, 230, 230, 255))
    bbox = canvas.getbbox()
    SEC.save(canvas.crop(bbox) if bbox else canvas, path)


def main():
    ship, W, H, layout, ext, door = compose()
    find_pad(ship, layout)
    layout["size"] = [W, H]
    layout["floors"] = max(ship.floors) + 1
    write_tbx(ship, W, H, ext, door)
    os.makedirs(OUT_ART, exist_ok=True)
    for z, deck_name, desc, _ in DECKS:
        preview_deck(ship, W, H, z, "%s (floor %d): %s" % (deck_name, z, desc),
                     os.path.join(OUT_ART, "deck%s.png" % deck_name.split()[-1]))
    with open(OUT_LAYOUT, "w") as fh:
        json.dump(layout, fh, indent=1)
    print("ship %d x %d, %d floors, %d rooms, %d furniture kinds; pad at %s"
          % (W, H, layout["floors"], len(ship.rooms), len(ship.furniture), layout["pad"]))


if __name__ == "__main__":
    main()
