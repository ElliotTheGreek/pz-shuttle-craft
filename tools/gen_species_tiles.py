"""The cabin in another people's hands: the Klingon and the Vulcan sets of the shuttle's tiles.

    python tools/gen_species_tiles.py [klingon|vulcan]     # then: python tools/gen_adirondack_pack.py
    python tools/gen_species_tiles.py fronts               # every mesh with each end as its front
        design/tiles/2x/trek_klingon_01.png, _02.png     the structure and the furniture, Klingon
        design/tiles/2x/trek_vulcan_01.png, _02.png      and Vulcan
        design/art/species/<people>_sheet.png            every piece in every facing
        design/art/shuttle_interior/cabin_<people>.png   LOOK AT THESE: the cabin, built of the set

**Each piece is that people's own**, made as the Adirondack's are (ADIRONDACK.md 7): a concept
from an image model, a mesh from the concept, and tiles from the mesh, every facing a turn of the
one model (tools/species_objects.py is the list and how each was asked for; tools/species_jobs.py
the ledger). Their bulkheads and decks are flat materials an image model painted, cut to the
game's own wall and floor by tools/gen_adirondack_tiles.py's routines, as Starfleet's are. (The
first attempt at this, 2026-10-11, was Starfleet's own tiles in other colours: "so its just a
tint? doesnt seem very good". It was, and it is gone.)

**A style is a sheet's name** (TREK_Interiors.lua): a fitting of the cabin is
`trek_adirondack_02_80` in Starfleet's and `trek_klingon_02_80` in a Klingon's. So each piece
here is rendered at the size of the Starfleet piece it stands in for and put in **that piece's
cells**, facing for facing and square for square, and tools/gen_adirondack_pack.py gives each
cell that tile's properties: a sink is a sink and a locker a locker whoever built it.

**Which way a mesh faces is looked at, never assumed** (FRONT): of twenty meshes, some came back
facing the other way, and a wrong front puts a locker's doors against the bulkhead. `fronts`
draws each with either end as its front. **Not seen in game.**
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_adirondack_furniture as F          # noqa: E402
import gen_adirondack_tiles as T              # noqa: E402
import isorender as iso                       # noqa: E402
import species_jobs as J                      # noqa: E402
import species_objects as S                   # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "design", "tiles", "2x")
CW, CH = 128, 256
S1, S2 = "trek_adirondack_01", "trek_adirondack_02"
with open(os.path.join(ROOT, "design", "tiles", S2 + ".json")) as f:
    INDEX = json.load(f)

# Which of a mesh's own axes looks into the room, for each that is not "+z": read off `fronts`.
# The Klingon biobed came back lying across: its length is its mesh's x, so its foot looks along +x.
FRONT = {"klingon": {"biobed": "+x"}, "vulcan": {}}

WALLS = {0: ("W",), 1: ("N",), 2: ("W", "N"), 3: ("W",)}      # as tools/gen_adirondack_tiles.py lays them


def sheet_names(people):
    return "trek_%s_01" % people, "trek_%s_02" % people


def concept(people, name):
    p = J.concept_path(people, name)
    if not p:
        raise SystemExit("no concept for %s %s: python tools/species_jobs.py fetch" % (people, name))
    return Image.open(p).convert("RGB")


def subject(im, tol=34):
    """A picture cut down to the thing in it: everything that is not its background, which is the
    colour of its corners. An image model fills the frame with a backdrop; a flat is its subject."""
    a = np.asarray(im, np.int32)
    h, w = a.shape[:2]
    k = max(4, w // 40)
    corners = np.concatenate([a[:k, :k].reshape(-1, 3), a[:k, -k:].reshape(-1, 3), a[-k:, :k].reshape(-1, 3), a[-k:, -k:].reshape(-1, 3)])
    back = np.median(corners, axis=0)
    off = np.abs(a - back).max(axis=2) > tol
    ys, xs = np.where(off)
    if len(xs) < 100:
        return im, np.ones((h, w), bool)
    x0, x1, y0, y1 = xs.min(), xs.max() + 1, ys.min(), ys.max() + 1
    return im.crop((x0, y0, x1, y1)), off[y0:y1, x0:x1]


def inset(tex, keep, mask, side, urange, vrange):
    """tools/gen_adirondack_tiles.py's inset_tile, for a picture with holes in it: a texture
    fitted to a window of one wall face, drawn only where `keep` says it is the thing itself."""
    uvf = T.uv_west if side == "W" else T.uv_north
    m = mask.load()
    u0, u1 = urange
    v0, v1 = vrange
    tw, th = tex.size
    t = T.shade(tex, T.WEST_LIGHT if side == "W" else T.NORTH_LIGHT).load()
    out = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    o = out.load()
    for y in range(CH):
        for x in range(CW):
            if not m[x, y]:
                continue
            u, v = uvf(x, y)
            if not (u0 <= u <= u1 and v0 <= v <= v1):
                continue
            tx = min(tw - 1, max(0, int((u - u0) / (u1 - u0) * tw)))
            ty = min(th - 1, max(0, int((v - v0) / (v1 - v0) * th)))
            if keep[ty, tx]:
                o[x, y] = t[tx, ty] + (255,)
    return out


# A flat whose own middle is as dark as its backdrop: a screen. It is cut to its frame and kept
# whole; cut by colour, its black glass went with the backdrop and only its bezel was drawn.
SCREENS = ("science_display",)


def flat(people, name, facing, urange, vrange):
    """A picture on a wall face, in the window Starfleet's has, kept to its own proportions."""
    tex, keep = subject(concept(people, name))
    if name in SCREENS:
        keep = np.ones_like(keep)
    u0, u1 = urange
    v0, v1 = vrange
    # The window is 72 pixels of wall across and 216 down: fit the picture inside it, centred.
    box_w, box_h = 72.0 * (u1 - u0), 216.0 * (v1 - v0)
    k = min(box_w / tex.width, box_h / tex.height)
    w, h = tex.width * k / 72.0, tex.height * k / 216.0
    uc, vc = (u0 + u1) / 2, (v0 + v1) / 2
    small = tex.resize((max(4, int(tex.width * k)), max(4, int(tex.height * k))), Image.LANCZOS)
    keep = np.asarray(Image.fromarray((keep * 255).astype(np.uint8)).resize(small.size, Image.NEAREST)) > 127
    mask = T.mask_of("industry_01", 0 if facing == "W" else 1)
    return inset(small, keep, mask, facing, (uc - w / 2, uc + w / 2), (vc - h / 2, vc + h / 2))


def structure(people):
    """Her bulkheads, her deck, her pad and her wall display: sheet 01's cells, cell for cell."""
    wall = concept(people, "wall")
    # One section of bulkhead is three times as tall as it is wide: the middle of the picture.
    w = min(wall.width, wall.height // 3)
    x0 = (wall.width - w) // 2
    wall = wall.crop((x0, 0, x0 + w, min(wall.height, w * 3))).resize((72, 216), Image.LANCZOS)
    cap = T.cornice(concept(people, "wall"))
    deck = T.crop_frac(concept(people, "deck"), 0.2).resize((128, 128), Image.LANCZOS)
    floor_mask = T.mask_of("floors_interior_tilesandwood_01", 18)
    tiles = {i: T.face_tile(wall, T.mask_of("industry_01", i), sides, cap) for i, sides in WALLS.items()}
    tiles[24] = T.floor_tile(deck, floor_mask)
    tiles[27] = T.floor_tile(T.transporter_pad(deck), floor_mask)
    for side, i in (("W", 40), ("N", 41)):
        tiles[i] = flat(people, "science_display", side, (0.2, 0.8), (0.2, 0.52))
    return tiles


STRETCH = 1.7           # how much more one way than another a piece may be made to fill its box


def fill(v, w, d, h, front="+z", inset=0.03):
    """A mesh made nearer the shape of the box it has to stand in. F.place fits a piece evenly,
    so one whose concept came back twice as wide as the square it is for (a counter drawn as a
    whole galley wall) is drawn at half its height: knee-high, and lost beside its neighbours.
    Each way is scaled toward filling its room, and no way more than STRETCH times another."""
    ext = np.maximum(1e-9, np.array([np.ptp(v[:, 0]), np.ptp(v[:, 1]), np.ptp(v[:, 2])]))       # the mesh's x, y (up), z
    across, out = (w - 2 * inset, d - 2 * inset)
    room = np.array([across, h, out]) if front in ("+z", "-z") else np.array([out, h, across])
    want = room / ext
    k = np.minimum(want, want.min() * STRETCH)
    return v * k


def furniture(people, only=None):
    """Every piece in every facing Starfleet's has, each in the cell of Starfleet's same square."""
    tiles, rows = {}, []
    for o in S.pieces(people):
        name = o["name"]
        if o["kind"] == "surface" or (only and name not in only):
            continue
        theirs = INDEX[name]["facings"]
        for facing, squares in sorted(theirs.items()):
            if o["kind"] == "flat":
                out = {(0, 0): flat(people, name, facing, o["u"], o["v"])}
            else:
                path = J.mesh_path(people, name)
                if not os.path.exists(path):
                    raise SystemExit("no mesh for %s %s: python tools/species_jobs.py fetch" % (people, name))
                v, faces, uv, img = F.load_glb(path)
                front = FRONT[people].get(name, "+z")
                v = fill(v, o["w"], o["d"], o["h"], front)
                world, fp = F.place(v, facing, o["w"], o["d"], o["h"], front=front, back=(o["facings"] == "WN"))
                out = iso.render_mesh(world, faces, uv, img, fp)
            cells = {(i, j): k for i, j, k in squares}
            for at, k in cells.items():
                t = out.get(at)
                if t is None or t.split()[3].getbbox() is None:
                    raise SystemExit("%s %s %s drew nothing on square %s, where Starfleet's has a tile" % (people, name, facing, at))
                tiles[k] = t
            extra = [at for at, t in out.items() if at not in cells and t.split()[3].getbbox() is not None]
            if extra:
                print("  %s %s %s: drawn on %s too, where Starfleet's has no tile; left off" % (people, name, facing, extra))
            rows.append(("%s %s" % (name, facing), {at: out[at] for at in cells}))
        print("rendered", people, name)
    return tiles, rows


def write_sheet(name, like, tiles):
    size = Image.open(os.path.join(SRC, like + ".png")).size
    sheet = Image.new("RGBA", size, (0, 0, 0, 0))
    for i, t in tiles.items():
        sheet.paste(t, ((i % 8) * CW, (i // 8) * CH))
    sheet.save(os.path.join(SRC, name + ".png"))


def contact(rows, path, cols=8):
    cells = []
    for label, out in rows:
        nx = max(i for i, _ in out) + 1
        ny = max(j for _, j in out) + 1
        c = Image.new("RGBA", (64 * (nx + ny) + 128, 32 * (nx + ny) + 280), (44, 46, 54, 255))
        ox, oy = 64 * ny + 64, 236
        for (i, j), t in sorted(out.items(), key=lambda k: (k[0][0] + k[0][1], k[0][0])):
            c.alpha_composite(t, (ox + 64 * (i - j) - 64, oy + 32 * (i + j) - 192))
        ImageDraw.Draw(c).text((6, 6), label, fill=(235, 235, 235, 255))
        cells.append(c)
    cw, ch = max(c.width for c in cells), max(c.height for c in cells)
    sheet = Image.new("RGBA", (cols * cw, ((len(cells) + cols - 1) // cols) * ch), (24, 24, 28, 255))
    for k, c in enumerate(cells):
        sheet.alpha_composite(c, ((k % cols) * cw, (k // cols) * ch))
    sheet.save(path)
    print("wrote", path)


def build(people):
    a, b = sheet_names(people)
    write_sheet(a, S1, structure(people))
    tiles, rows = furniture(people)
    write_sheet(b, S2, tiles)
    contact(rows, os.path.join(J.ART, people + "_sheet.png"))
    import gen_shuttle_interior as G
    G.render(os.path.join(G.OUT, "cabin_%s.png" % people), swap={S1: a, S2: b}, title="The shuttle's cabin, %s" % people.title())
    print("%s: %d tiles of structure and %d of furniture" % (people, len(WALLS) + 4, len(tiles)))


def fronts():
    """Every mesh that has been fetched, backed onto a north wall, with each end as its front:
    the camera looks at a north-backed piece's face, so the right one shows its doors."""
    rows = []
    for people in S.PIECES:
        for o in S.pieces(people):
            path = J.mesh_path(people, o["name"])
            if o["kind"] != "model" or not os.path.exists(path):
                continue
            v, faces, uv, img = F.load_glb(path)
            for front in ("+z", "-z", "+x", "-x") if o["d"] > 1 else ("+z", "-z"):
                world, fp = F.place(fill(v, o["w"], o["d"], o["h"], front), "N", o["w"], o["d"], o["h"], front=front, back=True)
                rows.append(("%s %s %s" % (people[0], o["name"], front), iso.render_mesh(world, faces, uv, img, fp)))
    contact(rows, os.path.join(J.ART, "fronts.png"), cols=10)


if __name__ == "__main__":
    args = sys.argv[1:]
    if args == ["fronts"]:
        fronts()
    else:
        for which in (args or list(S.PIECES)):
            build(which)
