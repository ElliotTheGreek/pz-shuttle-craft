"""Generates the mod's world-map symbols.

    python tools/gen_map_symbols.py TrekShuttle/42

Three 64x64 glyphs, the size and shape of vanilla's own (`media/ui/
LootableMaps/map_*.png`, ninety-two of them, all 64x64):

    TrekContactDilithium   a crystal      -- what the probes are looking for
    TrekContactPersonnel   a Starfleet delta -- 1.7's downed ensign
    TrekContactClue        a hexagon       -- a holo fragment (LORE.md 1c)

They are registered from `media/lua/shared/Definitions/TrekMapSymbols.lua`,
which is how vanilla registers its own -- `MapSymbolDefinitions.getInstance()
:addTexture(id, path, category)` in a plain shared Lua file. A symbol id that
nothing registered draws **nothing at all**, so `tests/test_assets.py` checks
that every id in `C.ContactSymbols` is both registered and on disk.

**These are read at map zoom, not in an inventory**, which is a different
problem from the item icons. A map symbol sits on a pale paper-textured
background among street names and other symbols, at perhaps twenty pixels, and
it is competing for attention rather than being looked at. So: one bold
silhouette, a dark outline so it survives a light background, and a colour
nothing else on the map uses. No interior detail -- at twenty pixels the
inside of a glyph is one colour whatever is drawn there.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pngwrite import Image

SIZE = 64

# The crystal's palette is the dilithium icon's, so the thing on the map and
# the thing in your hands are recognisably the same object.
CRYSTAL_FILL = (198, 132, 246, 255)
CRYSTAL_CORE = (238, 220, 255, 255)
CRYSTAL_RIM = (96, 226, 255, 255)

# Starfleet delta: LCARS amber, which nothing else on a Kentucky map is.
DELTA_FILL = (240, 176, 64, 255)
DELTA_CORE = (255, 228, 168, 255)

OUTLINE = (18, 14, 30, 255)


def fill_polygon(img, pts, colour):
    """Even-odd scanline fill, which is the whole reason the delta is a delta.

    The first version filled from the leftmost crossing to the rightmost,
    which is correct for a convex glyph and silently wrong for a concave one:
    the Starfleet arrowhead's swept-back trailing edge was filled straight
    across and it rendered as a plain triangle. The comment on that version
    said "the glyphs are convex" while sitting directly above one that was
    not.

    Filling between *pairs* of crossings costs one sort and handles both.
    `DEV_GUIDE.md`, *A blade is its silhouette*: the source looked right and
    one render settled it.
    """
    ys = [p[1] for p in pts]
    for y in range(max(0, int(min(ys))), min(SIZE, int(max(ys)) + 1)):
        xs = []
        for i in range(len(pts)):
            (x0, y0), (x1, y1) = pts[i], pts[(i + 1) % len(pts)]
            if y0 == y1:
                continue
            if min(y0, y1) <= y < max(y0, y1):
                xs.append(x0 + (x1 - x0) * (y - y0) / float(y1 - y0))
        if len(xs) < 2:
            continue
        xs.sort()
        for i in range(0, len(xs) - 1, 2):
            for x in range(max(0, int(xs[i])), min(SIZE, int(xs[i + 1]) + 1)):
                img.set(x, y, colour)


def outline(img, thickness=2):
    """Puts a dark rim around whatever has been drawn.

    A map symbol lands on paper, on grass, on a road and on another symbol,
    and a glyph with no rim disappears against at least one of those. Vanilla's
    own symbols all carry one.
    """
    for _ in range(thickness):
        edge = []
        for y in range(SIZE):
            for x in range(SIZE):
                if img.get(x, y)[3] != 0:
                    continue
                for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    nx, ny = x + dx, y + dy
                    if 0 <= nx < SIZE and 0 <= ny < SIZE:
                        c = img.get(nx, ny)
                        if c[3] != 0 and c != OUTLINE:
                            edge.append((x, y))
                            break
        for x, y in edge:
            img.set(x, y, OUTLINE)


def crystal():
    """A vertical bipyramid, the dilithium icon's silhouette flattened."""
    img = Image(SIZE, SIZE, (0, 0, 0, 0))
    cx = SIZE / 2.0
    top, shoulder, bottom, half = 8, 24, 56, 15
    fill_polygon(img, [(cx, top), (cx + half, shoulder),
                       (cx, bottom), (cx - half, shoulder)], CRYSTAL_FILL)
    # One bright facet down the middle, which is what stops it reading as a
    # plain diamond -- the one shape a map is already full of.
    fill_polygon(img, [(cx, top + 2), (cx + half * 0.34, shoulder),
                       (cx, bottom - 3), (cx - half * 0.34, shoulder)],
                 CRYSTAL_CORE)
    for y in range(top, bottom + 1):
        t = (y - top) / float(shoulder - top) if y <= shoulder \
            else (bottom - y) / float(bottom - shoulder)
        w = half * max(0.0, min(1.0, t))
        if w >= 1:
            img.set(int(round(cx - w)), y, CRYSTAL_RIM)
            img.set(int(round(cx + w)), y, CRYSTAL_RIM)
    outline(img)
    return img


def delta():
    """The Starfleet arrowhead: a person, in the one shape everybody reads."""
    img = Image(SIZE, SIZE, (0, 0, 0, 0))
    cx = SIZE / 2.0
    tip, base, half = 7, 55, 19
    # The outer arrowhead, with the trailing edge swept back up to a waist so
    # it is a delta rather than a triangle.
    fill_polygon(img, [(cx, tip), (cx + half, base),
                       (cx, base - 13), (cx - half, base)], DELTA_FILL)
    fill_polygon(img, [(cx, tip + 9), (cx + half * 0.52, base - 7),
                       (cx, base - 16), (cx - half * 0.52, base - 7)],
                 DELTA_CORE)
    outline(img)
    return img


HOLO_FILL = (80, 214, 240, 255)
HOLO_CORE = (210, 248, 255, 255)


def hexagon():
    """A holo emitter: the fragment's own hexagon (tools/gen_fragment.py), in
    the cyan nothing else on the map uses, with a lit ring inside it."""
    img = Image(SIZE, SIZE, (0, 0, 0, 0))
    cx = cy = SIZE / 2.0

    def ring(r):
        return [(cx + r * math.cos(math.pi / 3 * i + math.pi / 6),
                 cy + r * math.sin(math.pi / 3 * i + math.pi / 6)) for i in range(6)]
    fill_polygon(img, ring(17), HOLO_FILL)
    fill_polygon(img, ring(10), HOLO_CORE)
    fill_polygon(img, ring(5), HOLO_FILL)
    outline(img)
    return img


SYMBOLS = {
    "TrekContactDilithium": crystal,
    "TrekContactPersonnel": delta,
    "TrekContactClue": hexagon,
}

# **Never a category of our own.** These went in a "Starfleet" category and
# opening the world map threw, inside vanilla's symbol palette:
#
#   ISWorldMapSymbols.lua:1226  tab.joypadIndexY = floor(#tab.joypadButtonsY / 2)
#                        :1227  tab.joypadButtons = tab.joypadButtonsY[tab.joypadIndexY]
#                        :1228  tab.joypadIndex = ceil(#tab.joypadButtons / 2)
#
# The palette lays a category out at eight buttons a row, so a category of N
# symbols has ceil(N/8) rows. With one row, `floor(1 / 2)` is **0**,
# `joypadButtonsY[0]` is nil, and `#nil` throws -- "__len not defined for
# operand java.lang.RuntimeException", which names neither the symbol nor the
# mod. A category needs **nine symbols** before vanilla can lay it out at all,
# and every one of vanilla's three has at least twenty-eight.
#
# So the mod's symbols join an existing category. "Locations" is where a place
# on the map belongs anyway.
CATEGORY = "Locations"

# Where the registration file goes, and what it contains. Written by this
# script so the ids, the paths and the art cannot drift apart -- the same
# reason gen_uniform.py writes the clothing XML beside the texture.
DEFINITIONS = """-- Generated by tools/gen_map_symbols.py -- do not edit by hand.
--
-- Registered exactly as vanilla registers its own ninety-two symbols, in
-- media/lua/shared/Definitions/MapSymbolDefinitions.lua. A symbol id that
-- nothing registered draws nothing at all, with no warning anywhere.
{rows}
"""


def build(root):
    tex_dir = os.path.join(root, "media", "ui", "TrekMap")
    def_dir = os.path.join(root, "media", "lua", "shared", "Definitions")
    os.makedirs(tex_dir, exist_ok=True)
    os.makedirs(def_dir, exist_ok=True)

    rows = []
    for name, draw in sorted(SYMBOLS.items()):
        img = draw()
        drawn = sum(1 for y in range(SIZE) for x in range(SIZE)
                    if img.get(x, y)[3] != 0)
        if drawn < SIZE * SIZE * 0.08:
            raise SystemExit(f"{name}: only {drawn} pixels drawn -- the glyph "
                             f"is effectively empty and would read as nothing")
        rel = f"media/ui/TrekMap/{name}.png"
        img.save(os.path.join(root, *rel.split("/")))
        rows.append(f'MapSymbolDefinitions.getInstance():addTexture('
                    f'"{name}", "{rel}", "{CATEGORY}")')
        print(f"  {name:<24} {drawn * 100 // (SIZE * SIZE)}% of the frame")

    out = os.path.join(def_dir, "TrekMapSymbols.lua")
    with open(out, "w", encoding="utf-8", newline="\r\n") as fh:
        fh.write(DEFINITIONS.format(rows="\n".join(rows)))
    print(f"  {out}")


if __name__ == "__main__":
    build(sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42")
