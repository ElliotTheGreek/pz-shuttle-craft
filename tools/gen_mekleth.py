"""The mek'leth: a Klingon short sword, forward-swept and single-edged.

    python tools/gen_mekleth.py TrekShuttle/42

Shape, and why this one and not another: a mek'leth is a short arm-length
blade that widens toward the tip and then sweeps forward into a hook, with a
second smaller spur behind it and a short bound grip. What has to survive in an
isometric sprite about forty pixels tall is the **forward-heavy silhouette** --
narrow at the hand, heavy at the far end -- because that is the one thing that
tells it apart from every machete and cleaver already in this game.

**Size** is measured, not guessed (`tools/meshbbox.py`):

    Machete            0.009 x 0.335 x 0.057
    Sword_Short_*      ~0.44-0.47 long
    Katana             0.043 x 0.627 x 0.063

A mek'leth is a short sword, so it sits at the bottom of the short-sword
bracket: longer than a machete, well short of a katana. 0.44.

This is the number the engine uses. `WeaponLength` is a reach stat and scales
nothing -- the bat'leth shipped at twice its proper size on exactly that
misunderstanding.
"""
import math
import sys

import bladekit as B

LENGTH = 0.44                   # hand to tip
GRIP = 0.10                     # of it, wrapped
THICK = 0.013


def sections():
    """Bottom (pommel) to top (tip), in metres.

    x is across the blade: negative is behind the spine, positive is the
    cutting edge and the direction the blade sweeps.

    **The silhouette is the whole weapon.** The first draft made this a
    straight single-edged blade with a bellied edge, and the render came back
    a machete -- which this game already has four of. What separates a
    mek'leth from every chopper in build 42 is that the blade *leans forward*:
    the whole thing migrates toward the edge side as it rises, the back edge
    goes concave near the top instead of straight, and it finishes in a point
    thrown well forward of the grip. A rear spur sits behind that point.

    So `lean` below is not decoration, it is the identifying feature, and the
    thing to check in a render is whether the tip is clearly forward of the
    hand rather than above it.
    """
    s = []

    def lean(f):
        """How far the blade's centreline has swept forward, 0..1 up its length."""
        return 0.055 * (f ** 1.6)

    # Pommel and grip: narrow, wrapped, with a small flare at the base so the
    # hand has something to stop against.
    s.append((0.000, -0.011, 0.011, B.R_GRIP, B.R_GRIP))
    s.append((0.012, -0.015, 0.015, B.R_GRIP, B.R_GRIP))
    s.append((0.024, -0.010, 0.010, B.R_GRIP, B.R_GRIP))
    s.append((GRIP, -0.010, 0.010, B.R_GRIP, B.R_GRIP))

    # A short canted guard, then the blade proper.
    s.append((GRIP + 0.008, -0.022, 0.024, B.R_DARK, B.R_DARK))

    blade0 = GRIP + 0.018
    span = LENGTH - blade0
    for i in range(0, 11):
        f = i / 10.0
        y = blade0 + span * f
        c = lean(f)
        # The edge bellies out through the middle and closes to the point.
        edge = c + 0.020 + 0.026 * math.sin(math.pi * min(f * 0.92, 1.0))
        # The spine holds, then goes **concave** over the last third: this is
        # the cut that throws the tip forward instead of rounding it off.
        if f < 0.62:
            spine = c - 0.013
        else:
            k = (f - 0.62) / 0.38
            spine = c - 0.013 + 0.030 * (k ** 1.4)
        if f > 0.93:                    # close the point
            edge = c + 0.020 * (1 - f) / 0.07
            spine = min(spine, edge - 0.003)
        s.append((y, spine, edge, B.R_BLADE, B.R_EDGE))

    # The rear spur, behind the concave sweep: a short backward point that
    # stops the upper blade reading as a plain curve. Inserted in order.
    y = blade0 + span * 0.66
    spur = [
        (y - 0.004, lean(0.655) - 0.014, lean(0.655) + 0.043, B.R_BLADE, B.R_EDGE),
        (y + 0.002, lean(0.67) - 0.036, lean(0.67) + 0.043, B.R_BLADE, B.R_EDGE),
        (y + 0.011, lean(0.69) - 0.012, lean(0.69) + 0.042, B.R_BLADE, B.R_EDGE),
    ]
    s.extend(spur)
    s.sort(key=lambda t: t[0])
    return s


def main(root):
    B.emit(root, "TREK_Mekleth", "TREKMekleth",
           sections=sections(), thick=THICK, hand="1handed",
           tilt=45.0, note="mek'leth")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42")
