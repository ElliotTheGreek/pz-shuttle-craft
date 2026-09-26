"""The Adirondack's furniture: every object in the manifest, rendered into tiles.

    python tools/gen_adirondack_furniture.py [name ...]

Reads tools/adirondack_objects.py (what exists, how big, which ways it faces)
and the meshes the ledger downloaded (tools/assets/adirondack/*.glb), and
writes

  design/tiles/2x/trek_adirondack_02.png    the furniture sheet, 8 columns
  design/tiles/trek_adirondack_02.json      what is where: object, facing,
                                            square -> sheet index, its layer
  design/art/adirondack/furniture_sheet.png every object in every facing, the
                                            sheet to judge them on

How each kind is made:

* model   an image-to-3D mesh (glTF, Y up, front toward +Z), fitted UNIFORMLY
          into its w x d x h box -- proportions kept, so a chair stays a chair
          -- pushed back against the wall it faces from, and rendered from
          each facing by tools/isorender.py. A facing is a turn, never a
          mirror, so what is on an object's right stays on its right.
* reuse   one of the mod's own .x meshes (the replicator, the EMH station, the
          warp core), the same way; `front` says which of its axes looks into
          the room and `z0` lifts a wall-hung one off the floor.
* flat    a picture laid on a wall face in the u/v window the manifest gives,
          exactly as the wall display in sheet 01 is.
* box     the single bed, modelled in boxes (the first proof, kept).

Vanilla's own rule is followed for facings: things that back onto a wall come
in W and N (the two walls the camera sees); things that turn come in all four.
"""
import json
import os
import sys

import numpy as np
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import isorender as iso  # noqa: E402
import adirondack_objects as A  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "design", "art", "adirondack")
OBJ = os.path.join(ART, "objects")
MESHES = os.path.join(ROOT, "tools", "assets", "adirondack")
TILES = os.path.join(ROOT, "design", "tiles", "2x")
SHEET = "trek_adirondack_02"
INDEX = os.path.join(ROOT, "design", "tiles", SHEET + ".json")
CW, CH = iso.CW, iso.CH

# The reused meshes: which of their own axes faces into the room, and where
# they sit. The replicator and the warp core stand on the deck; the EMH's
# projector is a shallow wall unit above head height.
#
# A .x mesh here is (east, height, north) -- MeshBuilder's place() with Y up --
# so its fronts come from the generators, not from the pixels: gen_replicator.py
# says "the face looks east" (+x), and the EMH's station hangs on an east
# bulkhead looking west (-x). Reading the front off the texture was tried and
# was wrong: the replicator's LCARS strips are on several faces, and DirectX
# winding turns every computed normal round. It put the niche against the wall.
# (A TRELLIS mesh faces +z; checked by rendering the desk, the wardrobe and the
# captain's chair straight on from each axis.)
REUSE = {
    "replicator": dict(front="+x", z0=0.0),
    "emh_station": dict(front="-x", z0=1.05),
    "warp_core": dict(front="+z", z0=0.0),
}


# --- the single bed, in boxes -------------------------------------------------

def bed_boxes():
    P = dict(PLINTH=(58, 60, 66), FRAME=(148, 144, 138), MATTRESS=(224, 216, 198),
             DUVET=(68, 84, 118), FOLD=(98, 116, 152), PILLOW=(234, 230, 222),
             HEAD=(184, 174, 158), STRIP=(255, 214, 156))
    return [
        (0.12, 1.90, 0.14, 0.86, 0.00, 0.12, P["PLINTH"], 0.0),
        (0.06, 1.96, 0.06, 0.94, 0.12, 0.34, P["FRAME"], 0.02),
        (0.10, 1.92, 0.10, 0.90, 0.34, 0.50, P["MATTRESS"], 0.02),
        (0.72, 1.94, 0.08, 0.92, 0.44, 0.54, P["DUVET"], 0.05),
        (0.72, 0.88, 0.08, 0.92, 0.44, 0.565, P["FOLD"], 0.04),
        (0.16, 0.52, 0.20, 0.80, 0.50, 0.61, P["PILLOW"], 0.02),
        (0.00, 0.08, 0.02, 0.98, 0.00, 1.15, P["HEAD"], 0.015),
        (0.08, 0.095, 0.10, 0.90, 0.82, 0.86, P["STRIP"], 0.0),
    ]


def render_bed(facing):
    boxes = []
    for l0, l1, w0, w1, z0, z1, col, grain in bed_boxes():
        if facing == "W":
            boxes.append(iso.Box(l0, w0, z0, l1, w1, z1, col, grain=grain))
        else:
            boxes.append(iso.Box(w0, l0, z0, w1, l1, z1, col, grain=grain))
    return iso.render(boxes, (2, 1) if facing == "W" else (1, 2))


# --- meshes ---------------------------------------------------------------------

def load_glb(path):
    import trimesh
    scene = trimesh.load(path)
    mesh = scene.to_geometry() if hasattr(scene, "to_geometry") else scene
    v = np.asarray(mesh.vertices, np.float64)
    uv = np.asarray(mesh.visual.uv, np.float64).copy()
    uv[:, 1] = 1.0 - uv[:, 1]                 # trimesh flips glTF's v; undo it
    mat = mesh.visual.material
    img = getattr(mat, "baseColorTexture", None) or getattr(mat, "image", None)
    return drop_floor(v, np.asarray(mesh.faces), uv) + (img,)


def drop_floor(v, faces, uv):
    """Remove a baked-in floor: flat, level faces at the very bottom.

    An image-to-3D model sometimes brings the concept's shadow with it as a
    thin dark slab under the object (the ready-room desk did). The camera
    never sees the underside of anything that stands on the deck, so a level
    face at floor height is either that slab or invisible -- safe to drop.
    Vertices no face uses are dropped too, so the fit sees the object only."""
    y = v[:, 1]
    tri = v[faces]
    n = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    n /= np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)
    low = (tri[:, :, 1] <= y.min() + 0.015 * np.ptp(y)).all(axis=1)
    keep = ~(low & (np.abs(n[:, 1]) > 0.9))
    # And a shadow skirt: the ready-room desk's was a thin dark box in the
    # bottom 5% of its height, 0.56 deep under a desk 0.34 deep. Near the
    # floor, anything outside the footprint of the object above it goes.
    c = tri.mean(axis=1)
    base = y.min() + 0.06 * np.ptp(y)
    body = c[c[:, 1] > y.min() + 0.12 * np.ptp(y)]
    if len(body):
        pad = 0.02 * max(np.ptp(v[:, 0]), np.ptp(v[:, 2]))
        lo_x, hi_x = body[:, 0].min() - pad, body[:, 0].max() + pad
        lo_z, hi_z = body[:, 2].min() - pad, body[:, 2].max() + pad
        outside = (c[:, 0] < lo_x) | (c[:, 0] > hi_x) | (c[:, 2] < lo_z) | (c[:, 2] > hi_z)
        keep &= ~((c[:, 1] < base) & outside)
    faces = faces[keep]
    used = np.unique(faces.ravel())
    remap = -np.ones(len(v), int)
    remap[used] = np.arange(len(used))
    return v[used], remap[faces], uv[used]


def load_x(path):
    import preview_model as pm
    verts, faces, uvs = pm.parse_x(path)
    tex = os.path.splitext(os.path.basename(path))[0] + ".png"
    img = Image.open(os.path.join(ROOT, "TrekShuttle", "42", "media", "textures", tex))
    return np.asarray(verts, np.float64), np.asarray(faces), np.asarray(uvs, np.float64), img


def to_local(v, front):
    """Model axes -> (across, out, up): `out` is the direction the front looks,
    `across` the model's own right as you face it, `up` is Y."""
    x, y, z = v[:, 0], v[:, 1], v[:, 2]
    if front == "+z":
        return x, z, y
    if front == "-z":
        return -x, -z, y
    if front == "+x":
        return -z, x, y
    return z, -x, y                          # "-x"


def place(v, facing, w, d, h, front="+z", z0=0.0, back=True, inset=0.03):
    """Fit uniformly into the object's box and lay it for one facing.

    Returns world vertices and the footprint in squares."""
    across, out, up = to_local(v, front)
    ext = np.array([np.ptp(across), np.ptp(out), np.ptp(up)])
    room = np.array([w - 2 * inset, d - 2 * inset, h])
    s = float(np.min(room / np.maximum(1e-9, ext)))
    a = (across - across.min()) * s
    o = (out - out.min()) * s
    u = (up - up.min()) * s + z0
    a += (w - a.max()) / 2.0                          # centred along the wall
    o += inset if back else (d - o.max()) / 2.0      # against the wall, or centred
    if facing == "W":
        wx, wy, fp = o, a, (d, w)
    elif facing == "N":
        wx, wy, fp = w - a, o, (w, d)
    elif facing == "E":
        wx, wy, fp = d - o, w - a, (d, w)
    else:
        wx, wy, fp = a, d - o, (w, d)
    return np.stack([wx, wy, u], axis=1), (int(round(fp[0])), int(round(fp[1])))


def facings_of(o):
    return {"WN": "WN", "WNES": "WNES", "1": "W"}[o["facings"]]


# --- flats -------------------------------------------------------------------------

def render_flat(o, facing):
    import gen_adirondack_tiles as T
    src = None
    for ext in (".jpg", ".png"):
        p = os.path.join(OBJ, o["name"] + "_concept" + ext)
        if os.path.exists(p):
            src = Image.open(p).convert("RGB")
    if src is None:
        raise SystemExit("no concept image for " + o["name"])
    u0, u1 = o["u"]
    v0, v1 = o["v"]
    tw = max(8, int(72 * (u1 - u0)))
    th = max(8, int(216 * (v1 - v0)))
    tex = src.resize((tw, th), Image.LANCZOS)
    m = T.mask_of("industry_01", 0 if facing == "W" else 1)
    return {(0, 0): T.inset_tile(tex, m, facing, urange=(u0, u1), vrange=(v0, v1))}


# --- the run -------------------------------------------------------------------------

def build(only=None):
    tiles, index, rows = [], {}, []

    def add(name, area, layer, facing, out, use):
        entry = index.setdefault(name, {"area": area, "layer": layer, "use": use, "facings": {}})
        squares = []
        for (i, j), t in sorted(out.items()):
            if t.split()[3].getbbox() is None:
                continue
            squares.append([i, j, len(tiles)])
            tiles.append(t)
        if not squares:
            raise SystemExit("%s %s rendered nothing" % (name, facing))
        entry["facings"][facing] = squares
        rows.append((name, facing, out))

    if not only or "bed" in only:
        for f in "WN":
            add("bed", "quarters", "Furniture", f, render_bed(f), {"bed": "goodBed"})

    for o in A.OBJECTS:
        if only and o["name"] not in only:
            continue
        if o["kind"] == "crop":
            continue          # tools/gen_adirondack_crops.py
        if o["kind"] == "flat":
            for f in "WN":
                add(o["name"], o["area"], "WallFurniture", f, render_flat(o, f), o["use"])
            continue
        if o["kind"] == "model":
            path = os.path.join(MESHES, o["name"] + ".glb")
            if not os.path.exists(path):
                print("skipping %s: no mesh yet" % o["name"])
                continue
            v, faces, uv, img = load_glb(path)
            front, z0 = "+z", 0.0
        else:
            v, faces, uv, img = load_x(os.path.join(ROOT, o["source"]))
            front, z0 = REUSE[o["name"]]["front"], REUSE[o["name"]]["z0"]
        back = o["facings"] == "WN"
        for f in facings_of(o):
            world, fp = place(v, f, o["w"], o["d"], o["h"], front=front, z0=z0, back=back)
            out = iso.render_mesh(world, faces, uv, img, fp)
            add(o["name"], o["area"], "Furniture", f, out, o["use"])
        print("rendered", o["name"])
    return tiles, index, rows


def contact_sheet(rows, path):
    cells = []
    for name, facing, out in rows:
        nx = max(i for i, _ in out) + 1
        ny = max(j for _, j in out) + 1
        c = Image.new("RGBA", (64 * (nx + ny) + 128, 32 * (nx + ny) + 280), (44, 46, 54, 255))
        ox, oy = 64 * ny + 64, 236
        for (i, j), t in sorted(out.items(), key=lambda k: (k[0][0] + k[0][1], k[0][0])):
            c.alpha_composite(t, (ox + 64 * (i - j) - 64, oy + 32 * (i + j) - 192))
        ImageDraw.Draw(c).text((6, 6), "%s %s" % (name, facing), fill=(235, 235, 235, 255))
        cells.append(c)
    cols = 8
    cw = max(c.width for c in cells)
    ch = max(c.height for c in cells)
    sheet = Image.new("RGBA", (cols * cw, ((len(cells) + cols - 1) // cols) * ch), (24, 24, 28, 255))
    for k, c in enumerate(cells):
        sheet.alpha_composite(c, ((k % cols) * cw, (k // cols) * ch))
    sheet = sheet.resize((sheet.width // 2, sheet.height // 2), Image.LANCZOS)
    sheet.save(path)


def main():
    only = set(sys.argv[1:]) or None
    tiles, index, rows = build(only)
    rows_n = (len(tiles) + 7) // 8
    sheet = Image.new("RGBA", (CW * 8, CH * rows_n), (0, 0, 0, 0))
    for k, t in enumerate(tiles):
        sheet.paste(t, ((k % 8) * CW, (k // 8) * CH))
    if only:
        sheet.save(os.path.join(ART, "furniture_partial.png"))
        contact_sheet(rows, os.path.join(ART, "furniture_partial_sheet.png"))
        print("partial run: %d tiles, not written to the sheet" % len(tiles))
        return
    sheet.save(os.path.join(TILES, SHEET + ".png"))
    with open(INDEX, "w") as f:
        json.dump(index, f, indent=1, sort_keys=True)
    contact_sheet(rows, os.path.join(ART, "furniture_sheet.png"))
    print("wrote %d tiles for %d objects" % (len(tiles), len(index)))


if __name__ == "__main__":
    main()
