"""The Adirondack's first tileset: walls, floors, a door, a viewport, a panel.

    python tools/gen_adirondack_tiles.py

Writes design/tiles/2x/trek_adirondack_01.png -- a 2x tilesheet, 8 columns of
128x256 cells, laid out the way vanilla's own wall sheets are -- and a render of
a small room built from it, design/art/adirondack/room_preview.png, to judge it
by before it goes anywhere near an editor.

How a tile is made, and why:

* The SURFACES are Gemini's (design/art/adirondack/*_raw.jpg): flat,
  front-on textures of a carpet, a deck plate, a bulkhead, a door, a panel and
  a viewport. An image model is good at what a material looks like.
* The GEOMETRY is ours. Each texture is projected onto the exact iso face a
  vanilla tile uses -- a floor is the 128x64 diamond at the foot of the cell,
  a west wall stands on the edge from (0,224) to (64,192) and a north wall on
  the edge from (64,192) to (128,224), both 192 px tall. An image model cannot
  hit those to the pixel, and a wall that misses its neighbour by two pixels
  shows as a crack along every corridor.
* The SILHOUETTES are vanilla's. Every wall, doorway and door takes its alpha
  from the matching industry_01 / fixtures_doors_01 tile, so the thickness,
  the top cap and the door opening are the engine's own shapes, not a guess.
  Pixels inside the silhouette and off the face (the cap, the wall's end) are
  painted in the bulkhead's cornice colour.
* North faces are lit about 1.2x west faces in vanilla (measured: industry_01
  west 160, north 194), so the same factor is applied here.

The sheet's layout mirrors industry_01 so the BuildingEd entries read the same:
  0 W  1 N  2 NW  3 SE      walls
 10 W-door  11 N-door       walls with a doorway
 16..19                     the viewport wall, W N NW SE
 24 carpet  25 deck         floors
 32 door W  33 door N  34 W open  35 N open     (sliding: open is the frame)
 40 panel on a W wall  41 panel on a N wall

and the Jefferies tubes (JEFFERIES.md), from their own raws
(design/art/adirondack/tube_*_raw.jpg):
  4 W  5 N  6 NW  7 SE      the tube's walls
 12 W-door  13 N-door       tube walls with a doorway
 26                         the crawlway grating
 36 hatch W  37 N  38 W open  39 N open    (open: the leaf gone, the dark tube behind)
 48..63                     space: sixteen star fields, the void map's ground
                            (tools/gen_void_map.py scatters them)
"""
import math
import os
import random
import sys

from PIL import Image, ImageDraw, ImageStat

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "design", "art", "adirondack")
OUT = os.path.join(ROOT, "design", "tiles", "2x")
SHEET = "trek_adirondack_01"
VANILLA = os.environ.get(
    "PZ_TILES",
    r"D:/SteamLibrary/steamapps/common/Project Zomboid Modding Tools/Tiles/2x")

CW, CH = 128, 256           # a 2x cell
COLS, ROWS = 8, 8
WEST_LIGHT, NORTH_LIGHT = 0.84, 1.0


def vanilla_cell(sheet, index):
    im = Image.open(os.path.join(VANILLA, sheet + ".png")).convert("RGBA")
    c, r = index % 8, index // 8
    return im.crop((c * CW, r * CH, c * CW + CW, r * CH + CH))


def mask_of(sheet, index):
    return vanilla_cell(sheet, index).split()[3].point(lambda a: 255 if a > 96 else 0)


def raw(name):
    return Image.open(os.path.join(ART, name + "_raw.jpg")).convert("RGB")


def crop_frac(im, f):
    w, h = im.size
    return im.crop((int(w * f), int(h * f), int(w * (1 - f)), int(h * (1 - f))))


# --- face coordinates -------------------------------------------------------

def uv_west(x, y):
    return x / 64.0, (y - 32 + x / 2.0) / 192.0


def uv_north(x, y):
    return (x - 64) / 64.0, (y - (x - 64) / 2.0) / 192.0


def project(tex, side):
    """The texture laid across the whole face of one side, in a full cell."""
    tw, th = tex.size
    if side == "W":
        data = (tw / 64.0, 0, 0, th / 384.0, th / 192.0, -32 * th / 192.0)
    else:
        data = (tw / 64.0, 0, -tw, -th / 384.0, th / 192.0, 32 * th / 192.0)
    return tex.transform((CW, CH), Image.AFFINE, data, resample=Image.BICUBIC)


def shade(im, k):
    return im.point(lambda v: max(0, min(255, int(v * k))))


def face_tile(tex, mask, sides, cap):
    """Paint a wall silhouette: the face where the face is, cap colour elsewhere."""
    faces = {s: shade(project(tex, s), WEST_LIGHT if s == "W" else NORTH_LIGHT)
             for s in sides}
    out = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    src = out.load()
    m = mask.load()
    fp = {s: f.load() for s, f in faces.items()}
    top = tuple(min(255, int(c * 1.15)) for c in cap)
    for y in range(CH):
        for x in range(CW):
            if not m[x, y]:
                continue
            side = sides[0] if len(sides) == 1 else ("W" if x < 64 else "N")
            u, v = (uv_west if side == "W" else uv_north)(x, y)
            if 0.0 <= u <= 1.0 and 0.0 <= v <= 1.0:
                r, g, b = fp[side][x, y]
                src[x, y] = (r, g, b, 255)
            elif v < 0.0:
                src[x, y] = top + (255,)
            else:
                src[x, y] = tuple(int(c * 0.8) for c in cap) + (255,)
    return out


def inset_tile(tex, mask, side, urange=None, vrange=None):
    """A texture fitted to the uv bounds of a silhouette on one face."""
    uvf = uv_west if side == "W" else uv_north
    m = mask.load()
    us, vs = [], []
    for y in range(CH):
        for x in range(CW):
            if m[x, y]:
                u, v = uvf(x, y)
                us.append(u)
                vs.append(v)
    u0, u1 = urange or (min(us), max(us))
    v0, v1 = vrange or (min(vs), max(vs))
    tw, th = tex.size
    k = WEST_LIGHT if side == "W" else NORTH_LIGHT
    t = shade(tex, k).load()
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
            r, g, b = t[tx, ty]
            o[x, y] = (r, g, b, 255)
    return out


def floor_tile(tex, mask):
    tw, th = tex.size
    data = (tw / 128.0, tw / 64.0, -3.5 * tw, -th / 128.0, th / 64.0, -2.5 * th)
    f = tex.transform((CW, CH), Image.AFFINE, data, resample=Image.BICUBIC)
    out = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    out.paste(f, (0, 0), mask)
    return out


def cornice(tex):
    band = tex.crop((0, 0, tex.width, max(2, tex.height // 30)))
    return tuple(int(c) for c in ImageStat.Stat(band).mean[:3])


# --- the room preview ------------------------------------------------------

def preview(tiles, path):
    """A 5x4 room: carpet, walls on the west and north, a door, a viewport, a panel."""
    W, H = 5, 4
    ox, oy = 64 * H + 32, 40
    canvas = Image.new("RGBA", (64 * (W + H) + 128, 32 * (W + H) + 320), (20, 20, 26, 255))

    def put(t, tx, ty):
        sx = ox + (tx - ty) * 64 - 64
        sy = oy + (tx + ty) * 32
        canvas.alpha_composite(tiles[t], (sx, sy))

    for ty in range(H):
        for tx in range(W):
            put(24 if tx < W - 1 else 25, tx, ty)
    for ty in range(H):
        for tx in range(W):
            if tx == 0 and ty == 0:
                put(2, tx, ty)
            elif ty == 0:
                put(17 if tx == 2 else 1, tx, ty)
            elif tx == 0:
                put(10 if ty == 2 else 0, tx, ty)
                if ty == 2:
                    put(32, tx, ty)
                if ty == 1:
                    put(40, tx, ty)
            if ty == 0 and tx == 4:
                put(41, tx, ty)
    canvas.save(path)


# --- the Jefferies tubes and space -----------------------------------------

TUBE_WALLS = {4: (0, ("W",)), 5: (1, ("N",)), 6: (2, ("W", "N")), 7: (3, ("W",)),
              12: (10, ("W",)), 13: (11, ("N",))}
STARS = range(48, 64)
# Where the hatch's leaf sits in tube_hatch_raw.jpg, as fractions of the
# image: measured off the raw, the recess inside its dark frame.
HATCH_LEAF = (0.20, 0.625, 0.80, 0.935)


def open_hatch(tex):
    """The hatch with its leaf swung away: the dark of the tube behind it,
    lit a little at the top as a tube is by its guide lights."""
    out = tex.copy()
    w, h = out.size
    x0, y0, x1, y1 = (int(HATCH_LEAF[0] * w), int(HATCH_LEAF[1] * h),
                      int(HATCH_LEAF[2] * w), int(HATCH_LEAF[3] * h))
    d = ImageDraw.Draw(out)
    for y in range(y0, y1):
        t = (y - y0) / max(1, y1 - y0)
        v = int(34 - 22 * t)
        d.line([(x0, y), (x1, y)], fill=(v + 6, v + 3, v))
    return out


def star_tile(mask, seed):
    """One square of space: black, with stars scattered inside the floor
    diamond. Drawn in screen space, not projected: a star projected onto the
    ground plane would come out squashed two to one."""
    rnd = random.Random(seed)
    out = Image.new("RGBA", (CW, CH), (0, 0, 0, 0))
    m = mask.load()
    px = out.load()
    for y in range(CH):
        for x in range(CW):
            if m[x, y]:
                px[x, y] = (1, 1, 3, 255)
    inside = [(x, y) for y in range(CH) for x in range(CW) if m[x, y]]
    xs = [p[0] for p in inside]
    ys = [p[1] for p in inside]
    x0, x1, y0, y1 = min(xs), max(xs), min(ys), max(ys)

    def dot(cx, cy, r, colour, peak):
        for y in range(int(cy - r - 2), int(cy + r + 3)):
            for x in range(int(cx - r - 2), int(cx + r + 3)):
                if not (0 <= x < CW and 0 <= y < CH) or not m[x, y]:
                    continue
                d = math.hypot(x - cx, y - cy)
                a = max(0.0, 1.0 - d / (r + 0.8)) ** 1.6 * peak
                if a <= 0.01:
                    continue
                r0, g0, b0, _ = px[x, y]
                px[x, y] = (min(255, int(r0 + colour[0] * a)), min(255, int(g0 + colour[1] * a)),
                            min(255, int(b0 + colour[2] * a)), 255)

    tints = [(255, 255, 255), (200, 215, 255), (255, 236, 200), (255, 210, 190), (190, 230, 255)]
    for _ in range(rnd.randint(5, 11)):
        for _ in range(40):
            cx, cy = rnd.uniform(x0 + 3, x1 - 3), rnd.uniform(y0 + 2, y1 - 2)
            if m[int(cx), int(cy)]:
                break
        roll = rnd.random()
        if roll < 0.7:
            dot(cx, cy, 0.9, rnd.choice(tints), rnd.uniform(0.45, 0.8))
        elif roll < 0.95:
            dot(cx, cy, 1.4, rnd.choice(tints), rnd.uniform(0.8, 1.0))
        else:
            # A bright one, with a short cross of light.
            c = rnd.choice(tints)
            dot(cx, cy, 2.0, c, 1.0)
            for k in range(1, 5):
                for sx, sy in ((k, 0), (-k, 0), (0, k), (0, -k)):
                    dot(cx + sx, cy + sy * 0.6, 0.4, c, 0.5 / k)
    return out


def tube_wall_texture():
    """The tube's wall, turned to run along the tube. The raw was painted as
    a shaft wall -- its circuit strip and panel seams running up and down --
    and a crawlway is horizontal: turned a quarter, the strip and the seams run
    the length of the tube. Scaled to the face's height and cut from the middle,
    every wall section is the same slice, so the horizontal lines meet their
    neighbours' at every joint."""
    turned = raw("tube_wall").transpose(Image.ROTATE_270)
    w = int(turned.width * 216 / turned.height)
    turned = turned.resize((w, 216), Image.LANCZOS)
    x0 = (w - 72) // 2
    return turned.crop((x0, 0, x0 + 72, 216))


def tube_tiles(tiles):
    tube = tube_wall_texture()
    tcap = cornice(raw("tube_wall"))
    for i, (src, sides) in TUBE_WALLS.items():
        tiles[i] = face_tile(tube, mask_of("industry_01", src), sides, tcap)
    floor_mask = mask_of("floors_interior_tilesandwood_01", 18)
    grating = crop_frac(raw("tube_floor"), 0.22).resize((128, 128), Image.LANCZOS)
    tiles[26] = floor_tile(grating, floor_mask)

    hatch = raw("tube_hatch").resize((64, 180), Image.LANCZOS)
    opened = open_hatch(raw("tube_hatch")).resize((64, 180), Image.LANCZOS)
    for side, closed, idx in (("W", 0, 36), ("N", 1, 37)):
        m = mask_of("fixtures_doors_01", closed)
        tiles[idx] = inset_tile(hatch, m, side)
        tiles[idx + 2] = inset_tile(opened, m, side)

    for n, i in enumerate(STARS):
        tiles[i] = star_tile(floor_mask, 1701 + n)


def tube_preview(tiles, path):
    """A stretch of zig-zag tube over a field of stars, as the game stacks
    them: space on the ground, the tube four storeys above it."""
    W, H = 9, 9
    ox, oy = 64 * H + 32, 40
    canvas = Image.new("RGBA", (64 * (W + H) + 128, 32 * (W + H) + 320), (0, 0, 0, 255))

    def put(t, tx, ty):
        canvas.alpha_composite(tiles[t], (ox + (tx - ty) * 64 - 64, oy + (tx + ty) * 32))

    rnd = random.Random(7)
    for ty in range(H):
        for tx in range(W):
            put(rnd.choice(list(STARS)), tx, ty)
    path_sq = [(5, 1), (4, 1), (3, 1), (2, 1), (2, 2), (2, 3), (3, 3), (4, 3), (5, 3), (5, 4), (5, 5)]
    cells = set(path_sq)
    for tx, ty in path_sq:
        put(26, tx, ty)
    for ty in range(H + 1):
        for tx in range(W + 1):
            here = (tx, ty) in cells
            west = here != ((tx - 1, ty) in cells)
            north = here != ((tx, ty - 1) in cells)
            if (tx, ty) == (6, 1) and west:
                put(12, tx, ty)
                put(36, tx, ty)
            elif west and north:
                put(6, tx, ty)
            elif west:
                put(4, tx, ty)
            elif north:
                put(5, tx, ty)
    canvas.save(path)


def main():
    wall = raw("wall").resize((72, 216), Image.LANCZOS)
    view = raw("viewport").resize((72, 216), Image.LANCZOS)
    door = raw("door").resize((64, 180), Image.LANCZOS)
    panel = raw("lcars").resize((72, 96), Image.LANCZOS)
    carpet = crop_frac(raw("carpet"), 0.25).resize((128, 128), Image.LANCZOS)
    deck = crop_frac(raw("deck"), 0.03).resize((128, 128), Image.LANCZOS)

    cap = cornice(raw("wall"))
    walls = {0: ("W",), 1: ("N",), 2: ("W", "N"), 10: ("W",), 11: ("N",)}
    tiles = {}
    for i, sides in walls.items():
        tiles[i] = face_tile(wall, mask_of("industry_01", i), sides, cap)
    tiles[3] = face_tile(wall, mask_of("industry_01", 3), ("W",), cap)
    for off, i in ((16, 0), (17, 1), (18, 2), (19, 3)):
        sides = walls.get(i, ("W",))
        tiles[off] = face_tile(view, mask_of("industry_01", i), sides, cap)

    floor_mask = mask_of("floors_interior_tilesandwood_01", 18)
    tiles[24] = floor_tile(carpet, floor_mask)
    tiles[25] = floor_tile(deck, floor_mask)

    for side, closed, idx in (("W", 0, 32), ("N", 1, 33)):
        m = mask_of("fixtures_doors_01", closed)
        tiles[idx] = inset_tile(door, m, side)
        # Open: the leaves have slid into the frame; what is left is a sliver
        # each side, so the tile is never empty and still reads as a doorway.
        whole = inset_tile(door, m, side)
        uvf = uv_west if side == "W" else uv_north
        o = whole.load()
        us = [uvf(x, y)[0] for y in range(CH) for x in range(CW) if o[x, y][3]]
        lo, hi = min(us), max(us)
        for y in range(CH):
            for x in range(CW):
                if o[x, y][3]:
                    u = uvf(x, y)[0]
                    if lo + 0.07 < u < hi - 0.07:
                        o[x, y] = (0, 0, 0, 0)
        tiles[idx + 2] = whole

    # A wall display at eye height, a little narrower than the wall section.
    # The mask is the whole face (industry_01's plain wall); the u/v window is
    # what sizes it. security_01's monitor silhouette ran floor to ceiling.
    for side, idx, wall_i in (("W", 40, 0), ("N", 41, 1)):
        m = mask_of("industry_01", wall_i)
        tiles[idx] = inset_tile(panel, m, side, urange=(0.2, 0.8), vrange=(0.2, 0.52))

    tube_tiles(tiles)

    sheet = Image.new("RGBA", (CW * COLS, CH * ROWS), (0, 0, 0, 0))
    for i, t in tiles.items():
        sheet.paste(t, ((i % COLS) * CW, (i // COLS) * CH))
    os.makedirs(OUT, exist_ok=True)
    out = os.path.join(OUT, SHEET + ".png")
    sheet.save(out)
    preview(tiles, os.path.join(ART, "room_preview.png"))
    tube_preview(tiles, os.path.join(ART, "tube_preview.png"))
    for i in sorted(tiles):
        bb = tiles[i].split()[3].getbbox()
        if bb is None:
            sys.exit("tile %d came out empty" % i)
    print("wrote %s (%d tiles) and room_preview.png" % (out, len(tiles)))


if __name__ == "__main__":
    main()
