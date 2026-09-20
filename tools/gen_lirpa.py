"""The lirpa: the Vulcan ritual polearm, blade one end, weight the other.

    python tools/gen_lirpa.py TrekShuttle/42

A lirpa is a pole with a heavy fan-shaped blade at one end and a blunt weighted
bludgeon at the other. That double-ended asymmetry is the whole identity: from
across a room it is the only weapon in the game with a *different heavy thing
on each end*, and if both ends read the same it is a shovel.

Unlike the mek'leth this is not one continuous silhouette, so it is built as
two flat parts -- the head and the counterweight -- with a square-section shaft
joining them. A pole rendered as a flat ribbon vanishes edge-on from half the
angles, which the extruder alone cannot avoid.

**Size** against vanilla (`tools/meshbbox.py --vanilla spear`):

    SpearCrafted       0.017 x 0.771 x 0.018
    Spear_Forged_Hand  0.023 x 0.871 x 0.058
    Plunger_Spear      0.112 x 0.920 x 0.112   (the widest spear in the game)

Spears run 0.72 to 0.92 long. 0.80 puts the lirpa mid-bracket, and its head is
allowed to be broad because the plunger spear proves the engine draws a wide
head at this length without it reading as a barge pole.

`MinRange = 0.98` and the rest of the reach numbers come off `SpearCrafted`,
per the roadmap -- those are gameplay stats and have nothing to do with the
size of the mesh.
"""
import math
import sys

import bladekit as B

LENGTH = 0.80
THICK = 0.014
SHAFT_HALF = 0.010              # square shaft, half-width and half-depth
                                # (vanilla spear shafts run 0.016-0.023 across;
                                #  0.020 sits in that band and survives 32px)

HEAD_BOTTOM = 0.60              # where the blade fans out from
WEIGHT_TOP = 0.15               # where the counterweight ends


def head():
    """The blade: a fan that widens from the shaft and is ground across the top.

    Curved on the cutting side and flat-backed, so it reads as a cleaver on a
    pole rather than as a spear point -- a lirpa chops, it does not stab, and
    a symmetrical point would make it one more spear in a game that has
    twenty-six of them.
    """
    s = []
    s.append((HEAD_BOTTOM, -0.009, 0.009, B.R_EDGE, B.R_EDGE))
    s.append((HEAD_BOTTOM + 0.010, -0.014, 0.016, B.R_BLADE, B.R_EDGE))

    top = LENGTH
    span = top - (HEAD_BOTTOM + 0.010)
    for i in range(1, 10):
        f = i / 9.0
        y = HEAD_BOTTOM + 0.010 + span * f
        # **The back is straight and the edge does all the work.** The first
        # draft curved both and the render came back a leaf on a stick --
        # which is a spear, and this game has twenty-six of those. A flat
        # spine with everything swept to one side is what makes it a blade on
        # a pole instead.
        back = -0.014 - 0.006 * f
        edge = 0.016 + 0.062 * (f ** 0.72)
        if f > 0.90:                       # cut the crown off square
            k = (f - 0.90) / 0.10
            edge -= 0.016 * k
        s.append((y, back, edge, B.R_BLADE, B.R_EDGE))
    return s


def weight():
    """The counterweight: a blunt, slightly barrelled block of blued metal.

    Deliberately not a sphere. A ball reads as a mace, and a mace is a
    different weapon; the show's prop is a flattened drum.

    It stays on R_DARK -- blued metal. The first pass recoloured that strip to
    wood to make the shaft a pole, and turned the counterweight into a lump of
    timber with it, which is what a shared texture sheet costs if you recolour
    a region rather than pick a different one. The shaft uses the wrapped
    strip instead, which a ritual polearm can carry anyway.
    """
    s = []
    s.append((0.000, -0.020, 0.020, B.R_DARK, B.R_DARK))
    s.append((0.014, -0.026, 0.026, B.R_DARK, B.R_DARK))
    s.append((0.055, -0.028, 0.028, B.R_DARK, B.R_DARK))
    s.append((0.095, -0.026, 0.026, B.R_DARK, B.R_DARK))
    s.append((WEIGHT_TOP, -0.014, 0.014, B.R_DARK, B.R_DARK))
    return s


def shaft(m):
    """The pole, overlapping both heads slightly so no seam shows."""
    B.bar(m, WEIGHT_TOP - 0.010, HEAD_BOTTOM + 0.014,
          SHAFT_HALF, SHAFT_HALF, B.R_GRIP)


def main(root):
    B.emit(root, "TREK_Lirpa", "TREKLirpa",
           parts=[weight(), head()], thick=THICK, extra=shaft,
           shaft="gunmetal", hand="2handed", tilt=45.0, note="lirpa")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42")
