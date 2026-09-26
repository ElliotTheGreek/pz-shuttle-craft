"""Pictures of the Adirondack's Jefferies tubes, from the generated layout.

    python tools/preview_tubes.py

Writes, to design/art/adirondack/tubes/:

  overview.png     every deck and tube from above, one pixel-block per square:
                   rooms grey, tubes amber, hideouts red, hatches white
  tube<N>.png      an iso render of the stretch of tube N round its hideout
                   (or its middle), drawn from the real tiles over stars

Reads TREK_AdirondackLayout.lua itself (it is pure data), so what is drawn is
what the game builds.
"""
import os
import random
import sys

from lupa import LuaRuntime
from PIL import Image, ImageDraw

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import compose_adirondack as COMP  # noqa: E402

ROOT = COMP.ROOT
LAYOUT = os.path.join(ROOT, "TrekShuttle", "42", "media", "lua", "shared", "TREK",
                      "TREK_AdirondackLayout.lua")
OUT = os.path.join(ROOT, "design", "art", "adirondack", "tubes")


def load():
    lua = LuaRuntime()
    return lua.execute(open(LAYOUT, encoding="utf-8").read())


def lst(t):
    return [t[i] for i in range(1, len(t) + 1)] if t else []


def overview(L, path):
    s = 3
    x0, y0, x1, y1 = L.span.x0, L.span.y0, L.span.x1, L.span.y1
    im = Image.new("RGB", ((x1 - x0 + 1) * s, (y1 - y0 + 1) * s), (4, 4, 10))
    d = ImageDraw.Draw(im)

    def cell(x, y, c):
        d.rectangle([(x - x0) * s, (y - y0) * s, (x - x0) * s + s - 1, (y - y0) * s + s - 1], fill=c)

    for deck in lst(L.decks):
        for y, row in enumerate(lst(deck.grid)):
            for x, v in enumerate(lst(row)):
                if v:
                    cell(deck.ox + x, y, (120, 120, 130))
    for t in lst(L.tubes):
        ox = L.decks[t["from"]].ox
        for p in lst(t.crawl):
            cell(ox + p[1], p[2], (230, 160, 60))
        for p in lst(t.hideout):
            cell(ox + p[1], p[2], (220, 60, 60))
    for k, deck in enumerate(lst(L.decks), start=1):
        for o in lst(deck.objects):
            if o[3] == "trek_adirondack_01_36":
                cell(deck.ox + o[1], o[2], (255, 255, 255))
    im.save(path)


def iso(L, n, path, reach=11):
    t = L.tubes[n]
    ox = 0
    focus = lst(t.hideout) or lst(t.path)[len(lst(t.path)) // 2:len(lst(t.path)) // 2 + 1]
    fx = sum(p[1] for p in focus) // len(focus)
    fy = sum(p[2] for p in focus) // len(focus)
    bx0, by0 = fx - reach, fy - reach
    W = H = 2 * reach + 1
    layers = {}
    for f in lst(t.floors):
        layers.setdefault((f[1], f[2]), []).append((0, f[3]))
    for o in lst(t.objects):
        order = {"w": 1, "dN": 1.5, "dW": 1.5}.get(o[4], 2)
        layers.setdefault((o[1], o[2]), []).append((order, o[3]))
    ox, oy = 64 * H + 64, 220
    canvas = Image.new("RGBA", (64 * (W + H) + 256, 32 * (W + H) + 420), (0, 0, 0, 255))
    rnd = random.Random(3)
    stars = ["trek_adirondack_01_%d" % i for i in range(48, 64)]
    for y in range(H):
        for x in range(W):
            # Space is four storeys down; in the game it is drawn well offset.
            canvas.alpha_composite(COMP.tile_image(rnd.choice(stars)),
                                   (ox + 64 * (x - y) - 64, oy + 32 * (x + y) - 192 + 200))
    for (x, y) in sorted(layers, key=lambda k: (k[0] + k[1], k[0])):
        lx, ly = x - bx0, y - by0
        if not (0 <= lx < W and 0 <= ly < H):
            continue
        for order, name in sorted(layers[(x, y)]):
            if name == "invisible_01_0":
                continue
            canvas.alpha_composite(COMP.tile_image(name), (ox + 64 * (lx - ly) - 64, oy + 32 * (lx + ly) - 192))
    box = canvas.getbbox()
    canvas.crop(box).save(path)


def main():
    L = load()
    os.makedirs(OUT, exist_ok=True)
    overview(L, os.path.join(OUT, "overview.png"))
    for n in range(1, len(lst(L.tubes)) + 1):
        iso(L, n, os.path.join(OUT, "tube%d.png" % n))
    print("wrote overview.png and %d tube renders to %s" % (len(lst(L.tubes)), os.path.relpath(OUT, ROOT)))


if __name__ == "__main__":
    main()
