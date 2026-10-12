"""Two more small craft, each a hull of its own on the shuttle's vehicle: a Klingon raider and a Vulcan ring ship.

    python tools/gen_craft.py            # both
    python tools/gen_craft.py raider     # one
        TrekShuttle/42/media/models_X/TREK_Raider.x, TREK_Vulcan.x     each hull, as a vehicle draws it
        TrekShuttle/42/media/textures/TREK_Raider*.png, TREK_Vulcan*.png   a sheet for each skin, and the mask
        TrekShuttle/42/media/scripts/vehicles/trekraider_vehicle.txt, trekvulcan_vehicle.txt
        TrekShuttle/42/media/ui/vehicles/...                            the seat chart's art
        design/art/raider/, design/art/vulcan/                          LOOK AT THESE: <name>_skins.png,
                                                                        <name>_a.png, <name>_b.png, <name>_turn.png

**A kind of ship is a hull and nothing else** (DESIGN.md, *The hull*). Each of these is the
shuttle's vehicle script, character for character but for its names and its skin blocks
(tools/hullkit.py, vehicle_from): her chassis, her wheels nobody sees, her four doorless seats.
So everything that is true of the shuttle as a vehicle is true of them (sat in, flown, set down
on the same fifteen squares), and what a ship *is* (C.Hulls, `s.hull`) is which script she is
set down as. Her cabin is the shuttle's.

What that asks of a hull:

  * **it stands round the shuttle's seats**: four of them, 0.55 either side of her middle, a
    quarter of a square up, 0.1 and 1.3 ahead of her middle. A hull that is thin there has its
    crew sitting in the open air beside it (pz-mechs ART.md 6.10). `seats_inside` holds each to it;
  * **3 wide by 5 long at most**, standing on y = 0, centred: the room the world is asked for;
  * its liveries are C.Hulls' for it, in order, and tests/test_assets.py holds the two together.

**Not seen in game.**
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import hullkit as kit                                               # noqa: E402
from hullkit import BLACK, DARK, STEEL, STATES, tone                # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(ROOT, "TrekShuttle", "42", "media")
SHUTTLE = os.path.join(MEDIA, "scripts", "vehicles", "trekshuttle_vehicle.txt")
TEX = 512
SEATS = [(e, n) for e in (0.55, -0.55) for n in (0.1, 1.3)]         # trekshuttle_vehicle.txt, position inside


def seats_inside(hull, name):
    """Refuses a body that does not stand round every seat, from the seat's foot to a sitter's head."""
    for e, n in SEATS:
        for (na, *a), (nb, *b) in zip(hull.stations, hull.stations[1:]):
            if na <= n <= nb:
                t = (n - na) / (nb - na)
                waist = a[1][0] + (b[1][0] - a[1][0]) * t
                belly = a[0][1] + (b[0][1] - a[0][1]) * t
                shoulder = a[2][1] + (b[2][1] - a[2][1]) * t
                if waist < abs(e) + 0.25 or belly > 0.6 or shoulder < 1.15:
                    raise SystemExit("%s does not stand round the seat at %.2f, %.2f: its crew would sit outside it" % (name, e, n))


def frames(hull, d, w, h, base, mirror, at):
    """What every flank has: a line at each frame, at its waist and its shoulder, and an edge."""
    line, lite = tone(base, 0.68), tone(base, 1.08)
    for n in at:
        x = hull.fx(n)
        x = w - 1 - x if mirror else x
        d.line([(x, 0), (x, h - 1)], fill=line)
    d.rectangle([0, 0, w - 1, h - 1], outline=line)
    return line, lite


def mirrored(w, mirror):
    def box(a, b):
        return (w - 1 - b, w - 1 - a) if mirror else (a, b)
    return box


# ------------------------------------------------------------------------------ the raider
RAIDER_LIVERIES = {
    "house": dict(base=(92, 108, 76), trim=(150, 42, 34)),         # a great house's green
    "blood": dict(base=(112, 50, 42), trim=(196, 164, 72)),        # blood red, and gold
    "night": dict(base=(58, 62, 66), trim=(150, 42, 34)),          # a raider nobody is meant to see
}
RAIDER_R = {
    "flank_s": (0, 0, 360, 110), "flank_p": (0, 114, 360, 224), "top": (0, 228, 360, 370),
    "stern": (364, 0, 460, 60), "nose": (364, 64, 420, 90), "plain": (364, 94, 512, 150), "dark": (364, 154, 440, 206),
    "wing": (0, 374, 200, 512), "cannon": (204, 374, 404, 398), "glow": (408, 374, 444, 410),
}
RAIDER_STATIONS = [
    (-2.5, (0.45, 0.80), (0.62, 0.95), (0.62, 1.35), (0.40, 1.55)),     # her engines' end
    (-1.0, (0.50, 0.70), (0.70, 0.90), (0.70, 1.45), (0.45, 1.75)),
    (-0.6, (0.80, 0.45), (0.98, 0.75), (0.98, 1.45), (0.70, 1.95)),     # her cabin: it stands round the seats
    (1.4,  (0.80, 0.45), (0.98, 0.75), (0.98, 1.40), (0.66, 1.85)),
    (2.0,  (0.55, 0.55), (0.70, 0.80), (0.70, 1.15), (0.45, 1.35)),
    (2.5,  (0.22, 0.75), (0.30, 0.85), (0.30, 1.00), (0.20, 1.08)),     # her prow
]
RAIDER_PAINTED = {"flank_s": True, "flank_p": True, "stern": True, "plain": True, "top": False, "nose": False,
                  "wing": False, "cannon": False}


def raider_hull():
    H = kit.Hull(TEX, RAIDER_R)
    H.loft(RAIDER_STATIONS)
    seats_inside(H, "the raider")
    # A wing from each shoulder, swept back and down to a cannon at its tip.
    t = 0.10
    for s in (1, -1):
        rf, ra = (s * 0.92, 0.9, 1.34), (s * 0.92, -0.6, 1.34)
        tf, ta = (s * 1.44, -1.2, 0.26), (s * 1.44, -2.3, 0.26)

        def low(p):
            return (p[0], p[1], p[2] - t)
        H.face([ra, rf, tf, ta], H.rect("wing", flip=s < 0), (s * 0.6, 0, 0.8))
        H.face([low(ra), low(rf), low(tf), low(ta)], H.rect("dark"), (-s * 0.6, 0, -0.8))
        H.face([rf, tf, low(tf), low(rf)], H.rect("plain"), (s * 0.4, 0.9, 0.1))
        H.face([ra, ta, low(ta), low(ra)], H.rect("plain"), (0, -1, 0))
        e0, e1 = (1.38, 1.50) if s > 0 else (-1.50, -1.38)
        H.box(e0, -2.4, e1, -0.5, 0.0, 0.26, "cannon", top="cannon", front="glow", back="dark")
    return H


def raider_sheet(H):
    def build(livery, state):
        L = RAIDER_LIVERIES[livery]
        base, trim = L["base"], L["trim"]
        colours = {k: base for k in RAIDER_R if k not in ("dark", "glow")}
        colours["top"], colours["wing"], colours["cannon"] = tone(base, 0.88), tone(base, 0.94), (70, 72, 76)

        def flank(mirror):
            def painter(d, w, h):
                line, lite = frames(H, d, w, h, base, mirror, (-1.0, -0.6, 0.4, 1.4, 2.0))
                box = mirrored(w, mirror)
                for y in (H.fy(1.42), H.fy(0.78)):
                    d.line([(0, y), (w - 1, y)], fill=line)
                d.rectangle([0, H.fy(0.78) + 2, w - 1, h - 1], fill=tone(base, 0.70))        # her keel
                a, b = box(H.fx(-0.6), H.fx(2.0))
                d.rectangle([a, H.fy(1.42) + 3, b, H.fy(1.42) + 9], fill=trim)               # a band under her shoulder
                for n in (-0.3, 0.1, 0.5, 0.9, 1.3):                                         # armour, in plates
                    a, b = box(H.fx(n), H.fx(n) + 1)
                    d.rectangle([a, H.fy(1.30), b, H.fy(0.84)], fill=line)
                for y in range(H.fy(1.38), H.fy(0.98), 5):                                   # her engines breathe
                    a, b = box(H.fx(-2.3), H.fx(-1.3))
                    d.line([(a, y), (b, y)], fill=tone(base, 0.45))
            return painter

        def top(d, w, h):
            line = tone(base, 0.62)
            for n in (-1.0, -0.6, 0.4, 1.4, 2.0):
                d.line([(H.fx(n, "top"), 0), (H.fx(n, "top"), h - 1)], fill=line)
            d.rectangle([0, H.ty(0) - 7, w - 1, H.ty(0) + 6], fill=tone(base, 0.72))         # her spine
            d.rectangle([H.fx(-0.6, "top"), H.ty(0) - 2, H.fx(2.3, "top"), H.ty(0) + 1], fill=trim)
            d.rectangle([0, 0, w - 1, h - 1], outline=line)

        def wing(d, w, h):
            # Feathers: rows across the wing, each split where the row before it was not.
            line, dark = tone(base, 0.55), tone(base, 0.80)
            rows = 7
            for r in range(rows):
                y0, y1 = h * r // rows, h * (r + 1) // rows
                if r % 2:
                    d.rectangle([0, y0, w - 1, y1 - 1], fill=dark)
                d.line([(0, y0), (w - 1, y0)], fill=line)
                for x in range((r % 2) * 14, w, 28):
                    d.line([(x, y0), (x, y1)], fill=line)
            d.rectangle([0, h - 9, w - 1, h - 4], fill=trim)                                 # at her shoulder
            d.rectangle([0, 0, w - 1, h - 1], outline=line)

        def stern(d, w, h):
            d.rectangle([0, 0, w - 1, h - 1], outline=tone(base, 0.6))

        def cannon(d, w, h):
            d.rectangle([0, 0, w - 1, h - 1], outline=BLACK)
            for x in range(20, w, 30):
                d.line([(x, 0), (x, h - 1)], fill=BLACK)

        painters = {"flank_s": flank(False), "flank_p": flank(True), "top": top, "wing": wing, "stern": stern, "cannon": cannon,
                    "plain": lambda d, w, h: d.rectangle([0, 0, w - 1, h - 1], outline=tone(base, 0.6))}
        w = RAIDER_R["flank_s"][2]
        slits = [(H.fx(n), H.fy(1.66), H.fx(n) + 22, H.fy(1.66) + 6) for n in (-0.2, 0.3, 0.8)]
        red = (214, 60, 40)
        lamps = ([("flank_s", s, red) for s in slits] + [("flank_p", (w - s[2], s[1], w - s[0], s[3]), red) for s in slits]
                 + [("top", (H.fx(1.45, "top"), H.ty(-0.4), H.fx(1.6, "top"), H.ty(0.4)), red),                # her bridge's slit
                    ("stern", (10, 14, 40, 44), (232, 96, 44)), ("stern", (56, 14, 86, 44), (232, 96, 44)),   # her engines
                    ("nose", (18, 6, 38, 20), red),                                                           # her torpedo tube
                    ("glow", (0, 0, 36, 36), DARK), ("glow", (8, 8, 28, 28), (120, 220, 110))])               # a disruptor's mouth
        return kit.sheet(TEX, RAIDER_R, colours, painters, RAIDER_PAINTED, state, 3100, scorch=0.45, lamps=lamps)
    return build


# ------------------------------------------------------------------------------ the ring ship
VULCAN_LIVERIES = {
    "bronze": dict(base=(152, 98, 64), trim=(74, 42, 30)),         # the red-brown of every Vulcan hull
    "sand":   dict(base=(192, 164, 122), trim=(124, 62, 40)),      # a survey ship's, for the Forge
    "slate":  dict(base=(112, 114, 120), trim=(168, 104, 60)),     # the Science Directorate's
}
VULCAN_R = {
    "flank_s": (0, 0, 360, 110), "flank_p": (0, 114, 360, 224), "top": (0, 228, 360, 365),
    "stern": (364, 0, 400, 30), "nose": (364, 34, 420, 60), "plain": (364, 64, 512, 120), "dark": (364, 124, 440, 176),
    "ring": (0, 369, 256, 409), "ringface": (0, 413, 256, 440), "ringin": (0, 444, 256, 470), "strut": (260, 369, 300, 449),
}
VULCAN_STATIONS = [
    (-2.5, (0.10, 1.20), (0.15, 1.25), (0.15, 1.35), (0.10, 1.40)),     # the end of her boom
    (-1.2, (0.22, 1.05), (0.32, 1.15), (0.32, 1.45), (0.22, 1.55)),
    (-0.6, (0.75, 0.50), (0.95, 0.80), (0.95, 1.45), (0.65, 1.90)),     # her cabin: it stands round the seats
    (1.4,  (0.75, 0.45), (0.95, 0.80), (0.95, 1.40), (0.62, 1.85)),
    (2.0,  (0.48, 0.60), (0.64, 0.85), (0.64, 1.18), (0.40, 1.42)),
    (2.5,  (0.15, 0.90), (0.22, 0.98), (0.22, 1.10), (0.15, 1.18)),     # her nose
]
RING = dict(up=1.30, out=1.30, inner=1.06, n0=-2.30, n1=-1.50, sides=16)    # her warp ring: its middle, its two radii, where along her
VULCAN_PAINTED = {"flank_s": True, "flank_p": True, "plain": True, "top": False, "nose": False, "stern": False,
                  "ring": False, "ringface": False, "strut": False}


def vulcan_hull():
    H = kit.Hull(TEX, VULCAN_R)
    H.loft(VULCAN_STATIONS)
    seats_inside(H, "the ring ship")
    up, ro, ri, n0, n1, sides = (RING[k] for k in ("up", "out", "inner", "n0", "n1", "sides"))
    for i in range(sides):
        a0, a1 = 2 * math.pi * i / sides, 2 * math.pi * (i + 1) / sides
        am = (a0 + a1) / 2
        c, s = math.cos(am), math.sin(am)

        def at(r, a, n):
            return (r * math.cos(a), n, up + r * math.sin(a))
        part = ((i % 4) / 4.0, (i % 4 + 1) / 4.0)                                # each picture goes a quarter of the way round
        H.face([at(ro, a0, n0), at(ro, a1, n0), at(ro, a1, n1), at(ro, a0, n1)], H.rect("ring", part=part), (c, 0, s))
        H.face([at(ri, a0, n0), at(ri, a1, n0), at(ri, a1, n1), at(ri, a0, n1)], H.rect("ringin", part=part), (-c, 0, -s))
        H.face([at(ri, a0, n1), at(ri, a1, n1), at(ro, a1, n1), at(ro, a0, n1)], H.rect("ringface", part=part), (0, 1, 0))
        H.face([at(ri, a0, n0), at(ri, a1, n0), at(ro, a1, n0), at(ro, a0, n0)], H.rect("ringface", part=part), (0, -1, 0))
    # Four struts from her boom to her ring.
    s0, s1 = n0 + 0.2, n1 - 0.2
    H.box(-0.07, s0, 0.07, s1, up + 0.18, up + ri + 0.03, "strut")
    H.box(-0.07, s0, 0.07, s1, up - ri - 0.03, up - 0.18, "strut")
    H.box(0.20, s0, ri + 0.03, s1, up - 0.07, up + 0.07, "strut")
    H.box(-ri - 0.03, s0, -0.20, s1, up - 0.07, up + 0.07, "strut")
    return H


def vulcan_sheet(H):
    def build(livery, state):
        L = VULCAN_LIVERIES[livery]
        base, trim = L["base"], L["trim"]
        colours = {k: base for k in VULCAN_R if k != "dark"}
        colours["top"], colours["ring"], colours["ringface"], colours["ringin"] = tone(base, 0.90), tone(base, 0.84), tone(base, 0.84), None
        colours["strut"] = tone(base, 0.70)

        def flank(mirror):
            def painter(d, w, h):
                line, lite = frames(H, d, w, h, base, mirror, (-1.2, -0.6, 0.4, 1.4, 2.0))
                box = mirrored(w, mirror)
                for y in (H.fy(1.43), H.fy(0.80)):
                    d.line([(0, y), (w - 1, y)], fill=line)
                    d.line([(0, y + 1), (w - 1, y + 1)], fill=lite)
                a, b = box(H.fx(-0.6), H.fx(2.3))
                d.rectangle([a, H.fy(0.80) - 9, b, H.fy(0.80) - 3], fill=trim)               # a band over her waist
                d.rectangle([0, H.fy(0.80) + 2, w - 1, h - 1], fill=tone(base, 0.76))        # her keel
                a, b = box(H.fx(-0.45), H.fx(0.15))
                d.rectangle([a, H.fy(1.40), b, H.fy(0.92)], outline=BLACK)                   # her hatch
                for i, n in enumerate((0.45, 0.62, 0.79)):                                   # three marks of her script, as paint
                    a, b = box(H.fx(n), H.fx(n) + 7)
                    d.arc([a, H.fy(1.20), b, H.fy(1.20) + 14], 40 + 90 * i, 300 + 90 * i, fill=trim, width=2)
            return painter

        def top(d, w, h):
            line = tone(base, 0.66)
            for n in (-1.2, -0.6, 0.4, 1.4, 2.0):
                d.line([(H.fx(n, "top"), 0), (H.fx(n, "top"), h - 1)], fill=line)
            d.rectangle([H.fx(-2.5, "top"), H.ty(0) - 3, H.fx(-0.6, "top"), H.ty(0) + 2], fill=trim)   # along her boom
            d.rectangle([0, 0, w - 1, h - 1], outline=line)

        def ring(d, w, h):
            line = tone(base, 0.55)
            for x in range(0, w, 16):
                d.line([(x, 0), (x, h - 1)], fill=line)
            d.rectangle([0, 0, w - 1, 3], fill=trim)
            d.rectangle([0, h - 4, w - 1, h - 1], fill=trim)

        def ringface(d, w, h):
            for x in range(0, w, 16):
                d.line([(x, 0), (x, h - 1)], fill=tone(base, 0.55))

        painters = {"flank_s": flank(False), "flank_p": flank(True), "top": top, "ring": ring, "ringface": ringface,
                    "plain": lambda d, w, h: d.rectangle([0, 0, w - 1, h - 1], outline=tone(base, 0.6)),
                    "strut": lambda d, w, h: d.rectangle([0, 0, w - 1, h - 1], outline=BLACK)}
        w = VULCAN_R["flank_s"][2]
        panes = [(H.fx(-0.35), H.fy(1.78), H.fx(0.25), H.fy(1.52)), (H.fx(0.40), H.fy(1.76), H.fx(1.00), H.fy(1.50)),
                 (H.fx(1.45), H.fy(1.62), H.fx(1.95), H.fy(1.24))]
        glass = ([("flank_s", p) for p in panes] + [("flank_p", (w - p[2], p[1], w - p[0], p[3])) for p in panes]
                 + [("top", (H.fx(1.45, "top"), H.ty(-0.52) + 46 * i, H.fx(1.98, "top"), H.ty(-0.52) + 46 * i + 42)) for i in range(3)])
        cyan = (150, 214, 236)
        lamps = [("ring", (0, 14, 256, 26), cyan), ("ringin", (0, 0, 256, 26), DARK), ("ringin", (0, 6, 256, 20), cyan),
                 ("nose", (12, 6, 26, 18), (236, 222, 170)), ("nose", (30, 6, 44, 18), (236, 222, 170)),
                 ("stern", (10, 8, 26, 22), (232, 150, 70))]
        return kit.sheet(TEX, VULCAN_R, colours, painters, VULCAN_PAINTED, state, 4100, scorch=0.3, glass=glass, lamps=lamps,
                         cracked=(0, 7))
    return build


# ------------------------------------------------------------------------------ both
CRAFT = {
    "raider": dict(hull=raider_hull, sheet=raider_sheet, liveries=RAIDER_LIVERIES, mesh="TREK_Raider", vehicle="TrekRaider",
                   prefix="trekraider_", what="A Klingon raider"),
    "vulcan": dict(hull=vulcan_hull, sheet=vulcan_sheet, liveries=VULCAN_LIVERIES, mesh="TREK_Vulcan", vehicle="TrekVulcan",
                   prefix="trekvulcan_", what="A Vulcan ring ship"),
}


def skins_of(name):
    return [(livery, state) for livery in CRAFT[name]["liveries"] for state in STATES]


def skin_name(name, i):
    livery, state = skins_of(name)[i]
    mesh = CRAFT[name]["mesh"]
    return mesh if i == 0 else "%s_%s_%s" % (mesh, livery, state)


def build(name):
    K = CRAFT[name]
    H = K["hull"]()
    skins = skins_of(name)
    size = kit.publish(H, name, K["mesh"], K["prefix"], skins, lambda i: skin_name(name, i), K["sheet"](H),
                       MEDIA, os.path.join(ROOT, "design", "art", name))
    if size[0] > 3.001 or abs(size[2] - 5.0) > 0.001:
        raise SystemExit("%s is not 5 long and 3 wide at most: the room she is given to land in would be wrong" % name)
    head = ("/*  GENERATED by tools/gen_craft.py from trekshuttle_vehicle.txt. Do not edit.\n\n"
            "    %s as a vehicle (DESIGN.md, *The hull*). **It is the shuttle's script, character for\n"
            "    character**, with the names changed and a skin block for each livery and state: her\n"
            "    chassis, her wheels nobody sees and her four doorless seats, in a hull of its own that\n"
            "    stands round them. Which ship is set down as this is C.Hulls and `s.hull`.\n*/\n\n" % K["what"])
    kit.vehicle_from(SHUTTLE, os.path.join(MEDIA, "scripts", "vehicles", K["prefix"].rstrip("_") + "_vehicle.txt"),
                     "TrekShuttleCraft", K["vehicle"], "TREK_Shuttle", K["mesh"],
                     [skin_name(name, i) for i in range(len(skins))], head)
    print("%d skins; look at design/art/%s/%s_skins.png, _a.png, _b.png and _turn.png" % (len(skins), name, name))


if __name__ == "__main__":
    for which in (sys.argv[1:] or list(CRAFT)):
        build(which)
