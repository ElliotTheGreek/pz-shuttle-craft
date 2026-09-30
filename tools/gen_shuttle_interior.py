"""The shuttle's cabin, Starfleet issue: the deck plan, its .tbx and its picture.

    python tools/gen_shuttle_interior.py

One plan (PLAN below) and three things made from it, so they cannot disagree:

  design/buildinged/TrekShuttle_Interior.tbx     the BuildingEd file, which
                                                  TREK_InteriorLayout.lua is
                                                  checked against
                                                  (tests/test_layout.py)
  design/art/shuttle_interior/cabin.png           the cabin drawn from the real
                                                  tiles, the way the game's
                                                  cutaway shows it
  a reach check                                   every fitting worked from open
                                                  deck, every open square
                                                  joined to the pad

The plan is INTERIOR_REFIT.md 9's. Everything is the Adirondack's (sheets
trek_adirondack_01 and _02) except Lt. Shepard's television, which is
vanilla's and 1993's (LORE.md 1a). The world-model machines -- replicator,
warp core, the Doctor's station -- are placed by TREK_Build at runtime and are
not in the .tbx; they are drawn in the picture from their own meshes, because
a plan judged without them is a plan with three squares missing.

**Once the author saves the .tbx in BuildingEd it is theirs**: this writes a
`Generator` property into it and will not overwrite a file that has lost it
(`--force` does), as tools/gen_adirondack_sections.py does.
"""
import json
import os
import sys
from xml.sax.saxutils import quoteattr

from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_adirondack_tiles as T  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TILES = os.path.join(ROOT, "design", "tiles", "2x")
OUT = os.path.join(ROOT, "design", "art", "shuttle_interior")
TBX = os.path.join(ROOT, "design", "buildinged", "TrekShuttle_Interior.tbx")
MARKER = "tools/gen_shuttle_interior.py"
S1, S2 = "trek_adirondack_01", "trek_adirondack_02"
CW, CH = 128, 256
W, H = 4, 6
PAD = (2, 5)
CARPET, PAD_TILE = 24, 27

with open(os.path.join(ROOT, "design", "tiles", S2 + ".json")) as f:
    INDEX = json.load(f)

# Vanilla's pieces in the plan: Shepard's television, and nothing else.
VANILLA = {
    "television": dict(layer="Furniture",
                       facings={"W": [(0, 0, "appliances_television_01", 0)],
                                "N": [(0, 0, "appliances_television_01", 1)]}),
}
# The Adirondack's wall display lives on the structure sheet.
SHEET01 = {
    "wall_display": dict(layer="WallFurniture",
                         facings={"W": [(0, 0, S1, 40)], "N": [(0, 0, S1, 41)]}),
}


def pieces():
    out = {}
    for name, rec in INDEX.items():
        out[name] = dict(layer=rec["layer"],
                         facings={f: [(x, y, S2, i) for x, y, i in sq]
                                  for f, sq in rec["facings"].items()})
    out.update(VANILLA)
    out.update(SHEET01)
    return out


PIECES = pieces()

# The deck plan. `ox` runs port to starboard, `oy` bow to stern
# (INTERIOR_REFIT.md 2). Facing is the wall a piece backs onto -- "N" against
# the bow bulkhead looking aft, "W" against the port bulkhead -- which is how
# the Adirondack's sheet names it; "S" for the chair is backed to the stern,
# so it faces the bow.
#
#   (piece, facing, x, y, blocks, front)
#
# `blocks`: it stands on its square (a wall object does not). `front`: the
# square it is worked from, which must be open deck; None for a piece worked
# from any open side.
PLAN = [
    ("bunk",            "W", 0, 0, True,  (1, 0)),
    ("tape_rack",       "N", 1, 0, False, (1, 1)),
    ("tv_cabinet",      "N", 2, 0, True,  (2, 1)),
    ("television",      "N", 2, 0, True,  (2, 1)),
    ("science_display", "N", 2, 0, False, None),
    ("arms_locker",     "N", 3, 0, True,  (3, 1)),
    ("stasis_unit",     "W", 0, 1, True,  (1, 1)),
    ("galley_range",    "W", 0, 2, True,  (1, 2)),
    ("wall_display",    "W", 0, 2, False, None),
    ("galley_sink",     "W", 0, 3, True,  (1, 3)),
    ("wall_sconce",     "W", 0, 3, False, None),
    ("medical_cabinet", "W", 0, 4, True,  (1, 4)),
    ("bridge_chair",    "S", 2, 2, True,  (2, 1)),
    ("biobed",          "N", 3, 4, True,  None),
]

# The machines TREK_Build stands on the deck (C.ReplicatorSpot,
# C.DilithiumSpot, C.EmhStation): drawn, not in the .tbx. The Doctor's square
# under his station is kept clear -- he is projected onto it.
MACHINES = [
    ("TREK_Replicator.x", "W", 0, 5, 1.6, "+x", 0.0, True, (1, 5)),
    ("TREK_WarpCore.x", "W", 2, 3, 2.3, "+z", 0.0, True, None),
    ("TREK_EMHStation.x", "E", 3, 3, 2.2, "-x", 1.05, False, None),
]


def squares_of(name, facing, x, y):
    return [(x + dx, y + dy) for dx, dy, _, _ in PIECES[name]["facings"][facing]]


def check_reach():
    """Every open square joined to the pad, and every fitting worked from one."""
    blocked = set()
    for name, facing, x, y, blocks, _ in PLAN:
        if blocks:
            blocked.update(squares_of(name, facing, x, y))
    for src, facing, x, y, h, front, z0, blocks, _ in MACHINES:
        if blocks:
            blocked.add((x, y))
    open_ = {(x, y) for x in range(W) for y in range(H)} - blocked
    seen, todo = {PAD}, [PAD]
    while todo:
        x, y = todo.pop()
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n in open_ and n not in seen:
                seen.add(n)
                todo.append(n)
    bad = ["%d,%d is open deck nobody can walk to" % s for s in sorted(open_ - seen)]
    worked = [(name, (x, y), front) for name, _, x, y, _, front in PLAN]
    worked += [(src, (x, y), front) for src, _, x, y, _, _, _, _, front in MACHINES]
    for name, at, front in worked:
        if front is not None:
            if front not in seen:
                bad.append("%s at %d,%d: its front %d,%d is not open deck" % ((name,) + at + front))
            continue
        x, y = at
        near = ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))
        if at not in seen and not any(n in seen for n in near):
            bad.append("%s at %d,%d cannot be reached from any side" % ((name,) + at))
    exits = [n for n in ((PAD[0] + 1, PAD[1]), (PAD[0] - 1, PAD[1]), (PAD[0], PAD[1] - 1)) if n in seen]
    if len(exits) < 2:
        bad.append("the pad has %d way(s) off it" % len(exits))
    if bad:
        raise SystemExit("reach:\n  " + "\n  ".join(bad))
    print("reach: every fitting is worked from open deck; %d open squares, all joined to the pad"
          % len(open_))


# --- the .tbx ----------------------------------------------------------------------

def bname(sheet, i):
    """BuildingEd's name for a tile: the index padded to three digits."""
    return "%s_%03d" % (sheet, i)


def tbx():
    used = []
    for name, *_ in PLAN:
        if name not in used:
            used.append(name)
    fidx = {n: k for k, n in enumerate(used)}
    out = ["<?xml version='1.0' encoding='UTF-8'?>",
           '<building version="3" width="%d" height="%d" ExteriorWall="0" ExteriorWallTrim="0" '
           'Door="0" DoorFrame="0" Window="0" Curtains="0" Shutters="0" Stairs="0" RoofCap="0" '
           'RoofSlope="0" RoofTop="0" GrimeWall="0">' % (W, H),
           " <properties>",
           '  <property name="Description" value=%s />' % quoteattr(
               "TrekShuttle runtime cabin design source: the Starfleet refit "
               "(INTERIOR_REFIT.md 9). Drafted by " + MARKER),
           '  <property name="Mod" value="TrekShuttle" />',
           '  <property name="Generator" value="%s" />' % MARKER,
           " </properties>",
           ' <tile_entry category="interior_walls">']
    for enum, i in (("West", 0), ("North", 1), ("NorthWest", 2), ("SouthEast", 3),
                    ("WestWindow", None), ("NorthWindow", None), ("WestDoor", 10), ("NorthDoor", 11)):
        out.append('  <tile enum="%s" tile="%s" />' % (enum, bname(S1, i) if i is not None else ""))
    out.append(" </tile_entry>")
    out.append(' <tile_entry category="floors">\n  <tile enum="Floor" tile="%s" />\n </tile_entry>'
               % bname(S1, CARPET))
    for name in used:
        p = PIECES[name]
        layer = "" if p["layer"] == "Furniture" else ' layer="%s"' % p["layer"]
        out.append(" <furniture%s>" % layer)
        for fc in "WNES":
            if fc in p["facings"]:
                out.append('  <entry orient="%s">' % fc)
                for x, y, sheet, i in p["facings"][fc]:
                    out.append('   <tile x="%d" y="%d" name="%s" />' % (x, y, bname(sheet, i)))
                out.append("  </entry>")
        out.append(" </furniture>")
    out.append(" <user_tiles />")
    out.append(" <used_tiles>1 2</used_tiles>")
    out.append(" <used_furniture>%s</used_furniture>" % " ".join(str(i) for i in range(len(used))))
    out.append(' <room Name="Shuttle Interior" InternalName="livingroom" Color="72 132 160" '
               'InteriorWall="1" InteriorWallTrim="0" Floor="2" GrimeFloor="0" GrimeWall="0" />')
    out.append(" <floor>")
    out.append("  <rooms>")
    out.append(",\n".join(",".join("1" for _ in range(W)) for _ in range(H)))
    out.append("</rooms>")
    for name, facing, x, y, *_ in PLAN:
        out.append('  <object type="furniture" FurnitureTiles="%d" orient="%s" x="%d" y="%d" />'
                   % (fidx[name], facing, x, y))
    out.append(" </floor>")
    out.append("</building>")
    return "\n".join(out) + "\n"


def write_tbx(force):
    if os.path.exists(TBX) and not force:
        with open(TBX, encoding="utf-8") as f:
            current = f.read()
        if MARKER not in current and "TrekShuttle runtime cabin design source\"" not in current:
            raise SystemExit("%s has been saved in BuildingEd; it is the author's now. "
                             "--force to overwrite it" % TBX)
    with open(TBX, "w", encoding="utf-8", newline="\n") as f:
        f.write(tbx())
    print("wrote", TBX)


# --- the picture ---------------------------------------------------------------------

RENDERED = {}


def machine_tile(src, facing, h, front, z0):
    """One of the shuttle's own .x machines, rendered into one square the way
    the furniture generator renders the Adirondack's."""
    import gen_adirondack_furniture as F
    import isorender as iso
    key = (src, facing)
    if key not in RENDERED:
        v, faces, uv, img = F.load_x(os.path.join(ROOT, "TrekShuttle", "42", "media", "models_X", src))
        world, fp = F.place(v, facing, 1, 1, h, front=front, z0=z0, back=True)
        RENDERED[key] = iso.render_mesh(world, faces, uv, img, fp)[(0, 0)]
    return RENDERED[key]


def cell(sheets, sheet, i):
    if sheet not in sheets:
        path = os.path.join(TILES, sheet + ".png")
        if not os.path.exists(path):
            path = os.path.join(T.VANILLA, sheet + ".png")
        sheets[sheet] = Image.open(path).convert("RGBA")
    im = sheets[sheet]
    c, r = i % 8, i // 8
    return im.crop((c * CW, r * CH, c * CW + CW, r * CH + CH))


def render(path):
    sheets = {}
    ox, oy = 64 * H + 64, 240
    canvas = Image.new("RGBA", (64 * (W + H) + 256, 32 * (W + H) + 440), (0, 0, 0, 255))

    def blit(img, x, y):
        canvas.alpha_composite(img, (ox + 64 * (x - y) - 64, oy + 32 * (x + y) - 192))

    for y in range(H):
        for x in range(W):
            blit(cell(sheets, S1, PAD_TILE if (x, y) == PAD else CARPET), x, y)

    layers = {}
    for y in range(H):
        layers.setdefault((0, y), []).append((0, cell(sheets, S1, 0)))
    for x in range(W):
        layers.setdefault((x, 0), []).append((0, cell(sheets, S1, 1)))
    layers[(0, 0)] = [(0, cell(sheets, S1, 2))]
    for name, facing, x, y, *_ in PLAN:
        p = PIECES[name]
        order = 3 if p["layer"] == "WallFurniture" else (2.5 if name == "television" else 2)
        for dx, dy, sheet, i in p["facings"][facing]:
            layers.setdefault((x + dx, y + dy), []).append((order, cell(sheets, sheet, i)))
    for src, facing, x, y, h, front, z0, _, _ in MACHINES:
        layers.setdefault((x, y), []).append((2, machine_tile(src, facing, h, front, z0)))
    for (x, y) in sorted(layers, key=lambda k: (k[0] + k[1], k[0])):
        for _, img in sorted(layers[(x, y)], key=lambda t: t[0]):
            blit(img, x, y)

    d = ImageDraw.Draw(canvas)
    d.text((16, 16), "The shuttle's cabin, Starfleet issue (INTERIOR_REFIT.md 9)",
           fill=(230, 230, 230, 255))
    os.makedirs(OUT, exist_ok=True)
    import gen_adirondack_sections as G
    G.save(canvas, path)
    print("wrote", path)


if __name__ == "__main__":
    check_reach()
    write_tbx("--force" in sys.argv)
    render(os.path.join(OUT, "cabin.png"))
