"""The ushaan-tor: the Andorian ice-miner's blade.

    python tools/gen_ushaantor.py TrekShuttle/42

An ushaan-tor is a short, broad, hooked blade -- a mining tool that ritual
combat turned into a weapon. The read is **stubby and top-heavy**: almost no
reach, a blade nearly as wide as it is long, and a hook curling off the end
that no other small blade in this game has.

That matters more here than on the other two. Build 42 ships a *lot* of small
blades -- hunting knives, letter openers, scalpels, screwdrivers, penknives --
and at 32 pixels they are all the same thin vertical line. Anything that reads
as "small pointed thing" is invisible in that crowd. So this one is drawn
deliberately wrong-looking for a knife: wide, blunt-backed, and hooked.

**Size** against vanilla (`tools/meshbbox.py`):

    HuntingKnife       0.017 x 0.276 x 0.047
    Machete            0.009 x 0.335 x 0.057

The roadmap names `HuntingKnife` as the template, so 0.26 -- a shade under it,
because an ushaan-tor is a fist-weapon rather than a belt knife. It is wider
than any of them on purpose; that is the whole point of the silhouette. But
only so far: the widest mesh in the entire vanilla arsenal is the canoe
paddle at 0.123 and that is two-handed, so a one-handed weapon has no business
near it. The belly and the hook travel are tuned to land this around 0.085
across -- broad enough to be unmistakable, narrower than anything vanilla
swings in one hand.
"""
import math
import sys

import bladekit as B

LENGTH = 0.26
GRIP = 0.085
THICK = 0.011


def sections():
    """Bottom (pommel) to top (hook), in metres.

    Positive x is the cutting edge and the side the hook curls toward.
    """
    s = []

    # A short grip with a pronounced guard at both ends -- this is held in a
    # fist during a duel and the prop has a knuckle bar, which at this scale
    # is best said with a flare rather than modelled.
    s.append((0.000, -0.019, 0.019, B.R_DARK, B.R_DARK))
    s.append((0.010, -0.013, 0.013, B.R_GRIP, B.R_GRIP))
    s.append((GRIP - 0.012, -0.013, 0.013, B.R_GRIP, B.R_GRIP))
    s.append((GRIP, -0.024, 0.026, B.R_DARK, B.R_DARK))

    # The blade and the hook are one curve, not a blade with a hook stuck on
    # the end. **The first draft built the hook by tilting the back edge over
    # the top two sections, and it rendered as a meat cleaver with a chamfer**
    # -- because angling one edge cuts a corner off, it does not curl anything.
    #
    # What makes a hook is the *centreline* swinging to one side while the
    # blade gets thinner: the metal goes somewhere, and it goes sideways. So
    # below, `mid` is where the blade's middle has travelled to and `half` is
    # how much blade is left there, and the shape falls out of the two.
    blade0 = GRIP + 0.006
    span = LENGTH - blade0
    for i in range(0, 13):
        f = i / 12.0

        # The belly: widest at a third, because a mining tool carries its mass
        # near the hand rather than out at the tip.
        half = 0.015 + 0.021 * math.sin(math.pi * min(f * 1.15, 1.0) ** 0.8)

        # The curl. Nothing for the first half -- a hook that starts at the
        # guard is a sickle -- then hard over.
        if f < 0.45:
            mid = 0.004 * f
        else:
            k = (f - 0.45) / 0.55
            mid = 0.002 + 0.046 * (k ** 1.5)
            half *= (1 - 0.72 * (k ** 1.3))     # and thins as it goes

        y = blade0 + span * f
        # The back stays blunt while there is blade to be blunt about.
        back = mid - half * (1.0 if f < 0.45 else 0.85)
        edge = mid + half
        s.append((y, back, edge, B.R_BLADE, B.R_EDGE))
    return s


def main(root):
    B.emit(root, "TREK_UshaanTor", "TREKUshaanTor",
           sections=sections(), thick=THICK, hand="1handed",
           tilt=40.0, note="ushaan-tor")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42")
