"""The Adirondack's doors: the pneumatic shoosh, opening and closing.

    python tools/gen_door_sound.py

Writes TrekShuttle/42/media/sound/TREK_DoorOpen.wav and TREK_DoorClose.wav,
which trekshuttle.txt declares as the sounds TrekDoorOpen and TrekDoorClose.
The door tiles carry `DoorSound = TrekDoor` (gen_adirondack_pack.py), and the
engine plays DoorSound + "Open" / "Close" itself whenever a door is toggled --
on every client, from the sync packet -- so nothing in the Lua plays these.

What makes it read as *that* door rather than a gust: noise through a
low-pass whose cutoff sweeps -- up as the panels part, down as they meet --
under a short falling pneumatic tone, with a soft thump where the panels stop.
Synthesised, like every other sound in the mod, so it is ours.
"""
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gen_medical import Noise, RATE, write  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "TrekShuttle", "42", "media", "sound")


def shoosh(opening, duration=0.62):
    noise = Noise(20260925 if opening else 20260926)
    out = []
    lp1 = lp2 = 0.0
    n = int(RATE * duration)
    for i in range(n):
        t = i / RATE
        p = t / duration
        # The cutoff sweep, as a one-pole coefficient: bright in the middle
        # of the travel, dark at both ends, weighted to the start opening
        # and to the end closing.
        shape = math.sin(math.pi * min(1.0, p * (1.25 if opening else 1.0)))
        k = 0.02 + 0.30 * shape * (1.0 - 0.35 * p if opening else 0.65 + 0.35 * p)
        lp1 += (noise.next() - lp1) * k
        lp2 += (lp1 - lp2) * k
        env = min(1.0, t / 0.03) * (1.0 - p) ** (1.6 if opening else 1.1)
        air = 1.5 * lp2 * env
        # The pneumatics: a short tone that falls away.
        f = (520 if opening else 380) * (1.0 - 0.45 * p)
        tone = 0.12 * math.sin(2 * math.pi * f * t) * math.exp(-7.0 * p)
        # The panels stopping: a low thump near the end of the travel.
        stop = 0.72 if opening else 0.80
        dt = t - stop * duration
        thump = 0.0
        if dt >= 0:
            thump = 0.35 * math.sin(2 * math.pi * 95 * dt) * math.exp(-38 * dt)
        out.append(air + tone + thump)
    return out


def main():
    write(os.path.join(OUT, "TREK_DoorOpen.wav"), shoosh(True), peak=22000)
    write(os.path.join(OUT, "TREK_DoorClose.wav"), shoosh(False), peak=20000)


if __name__ == "__main__":
    main()
