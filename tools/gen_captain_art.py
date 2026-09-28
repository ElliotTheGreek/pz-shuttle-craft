#!/usr/bin/env python3
"""Captain Titus's portrait, rendered from the body she is drawn with.

    python tools/gen_captain_art.py TrekShuttle/42

Not drawn separately, for the reason DEV_GUIDE.md gives under *An icon can be
rendered from the model instead of drawn* and CAPTAIN.md 5.6 repeats: the face
in her panel and the woman in the chair are then the same object. Vanilla's
female body at skin 2, the mod's own command duty uniform on the boilersuit
rig it is worn on (UNIFORMS.md), and vanilla's bun in grey -- the fixed look
TREK_Crew.K.Captain gives her body.

Writes media/ui/TREK_CaptainPortrait.png (96 px, the size TREKCaptainWindow
draws it) and keeps the full render it was judged on in design/art/captain/.
"""
import math
import os
import sys

import numpy as np
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import figure_render as FR  # noqa: E402
import xskin  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PZ = FR.PZ
ART = os.path.join(ROOT, "design", "art", "captain")

SKIN = os.path.join(PZ, "textures", "Body", "FemaleBody02.png")
UNIFORM_RIG = os.path.join(PZ, "models_X", "Skinned", "Clothes", "Kate_BoilerSuit.x")
HAIR_RIG = os.path.join(PZ, "models_X", "Skinned", "Hair", "F_Hair_Bun.X")
# The bun is drawn from the white sheet, tinted per character; hers is
# TREK_Crew.K.HairColours[6], grey.
HAIR_TEX = os.path.join(PZ, "textures", "F_Hair_White.png")   # hairStyles.xml, Bun
HAIR_TINT = (0.55, 0.55, 0.55)

PORTRAIT = 96
BG = (20, 22, 30)
YAW, PITCH = -20.0, 4.0


def uniform_texture(base):
    return os.path.join(base, "media", "textures", "clothes", "trek", "duty_command.png")


def figure(base):
    pose = FR.Pose("F", None)
    fig = FR.Figure(pose)
    fig.body(SKIN)
    fig.garment(UNIFORM_RIG, uniform_texture(base))
    hair = Image.open(HAIR_TEX).convert("RGBA")
    a = np.array(hair).astype(np.float32)
    a[..., :3] *= np.array(HAIR_TINT, dtype=np.float32)
    fig.garment(HAIR_RIG, Image.fromarray(a.astype(np.uint8), "RGBA"))
    return fig, pose


def head_frame(pose):
    """The view-space centre of head and shoulders, and how much to show."""
    head = xskin.transform((0.0, 0.0, 0.0), pose.world["Bip01_Head"])
    cy, sy = math.cos(math.radians(YAW)), math.sin(math.radians(YAW))
    cp, sp = math.cos(math.radians(PITCH)), math.sin(math.radians(PITCH))
    R = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]])
    P = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    v = (P @ R) @ np.array(head, dtype=np.float64)
    # The head bone sits at the base of the skull: a little above it frames
    # the face, with the collar and the badge at the bottom edge.
    centre = np.array([v[0], v[1] + 0.035, v[2]])
    return centre, 0.26


def main():
    base = sys.argv[1] if len(sys.argv) > 1 else os.path.join("TrekShuttle", "42")
    if not os.path.isabs(base):
        base = os.path.join(ROOT, base)
    os.makedirs(ART, exist_ok=True)
    fig, pose = figure(base)
    big = FR.render(fig, 480, YAW, PITCH, bg=BG, frame=head_frame(pose), ss=2)
    big.save(os.path.join(ART, "portrait_full.png"))
    whole = FR.render(fig, 480, YAW, PITCH, bg=BG)
    whole.save(os.path.join(ART, "figure_full.png"))
    out = os.path.join(base, "media", "ui", "TREK_CaptainPortrait.png")
    big.resize((PORTRAIT, PORTRAIT), Image.LANCZOS).save(out)
    print(f"wrote {os.path.relpath(out, ROOT)} and design/art/captain/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
