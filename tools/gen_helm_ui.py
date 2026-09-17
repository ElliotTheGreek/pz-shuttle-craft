"""Writes the geometric primitives the LCARS helm console is drawn from.

LCARS is flat colour and rounded ends, and nothing else. Rather than baking
the whole console into one image -- which would blur when the panel is sized
and could never show a pressed button -- TREK_Helm.lua builds it from solid
rectangles plus two white shapes tinted at draw time:

    TREK_LcarsDot.png          a disc: rounded button ends and outer elbows
    TREK_LcarsNotchTop.png     a square with a quarter-disc bitten out of its
                               bottom-right: the inner curve where the
                               sidebar meets the top bar
    TREK_LcarsNotchBottom.png  the same bite from the top-right, for the
                               bottom bar

The artwork -- the backdrop and the emblem -- is generated and vetted through
the FlowDot Gemini Image toolkit (see ROADMAP.md, "How art gets made"); these
are geometry, where exactness matters more than style.

    python tools/gen_helm_ui.py TrekShuttle/42
"""
import math
import os
import sys

from pngwrite import Image

SIZE = 64
SAMPLES = 4  # per axis: 16 samples a pixel is plenty for a clean edge


def coverage(inside, x, y):
    """Fraction of pixel (x, y) for which inside(px, py) is true."""
    hit = 0
    for sy in range(SAMPLES):
        for sx in range(SAMPLES):
            if inside(x + (sx + 0.5) / SAMPLES, y + (sy + 0.5) / SAMPLES):
                hit += 1
    return hit / (SAMPLES * SAMPLES)


def shape(inside):
    img = Image(SIZE, SIZE)
    for y in range(SIZE):
        for x in range(SIZE):
            a = coverage(inside, x, y)
            if a > 0:
                img.set(x, y, (255, 255, 255, int(round(a * 255))))
    return img


def main():
    mod = sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42"
    out = os.path.join(mod, "media", "ui")
    os.makedirs(out, exist_ok=True)
    r = SIZE / 2

    dot = shape(lambda px, py: math.hypot(px - r, py - r) <= r)
    notch_top = shape(lambda px, py: math.hypot(px - SIZE, py - SIZE) >= SIZE)
    notch_bottom = shape(lambda px, py: math.hypot(px - SIZE, py) >= SIZE)

    for name, img in (("TREK_LcarsDot.png", dot),
                      ("TREK_LcarsNotchTop.png", notch_top),
                      ("TREK_LcarsNotchBottom.png", notch_bottom)):
        path = os.path.join(out, name)
        img.save(path)
        print("wrote", path)


if __name__ == "__main__":
    main()
