"""Generates the medical set's two sounds.

The icons for the hypospray and the two tricorders are **not** made here: they
come from the FlowDot Gemini Image toolkit (ROADMAP.md, "How art gets made"),
are keyed by tools/key_icon.py, and their originals and contact sheet live in
design/art/medical/. This file is only the audio, which has no image model and
is a dozen oscillators.

    python tools/gen_medical.py TrekShuttle/42

Both are synthesized from the standard library, deterministically -- the noise
uses its own seeded generator rather than `random`, so re-running this writes
byte-identical files and a regenerated asset is never a silent diff. Neither is
copied franchise audio.

Kept quiet on purpose. Both of these are played with playSoundLocal, so they
are heard by the person holding the instrument and do not reach the zombies:
an item you are meant to use in a bad situation should not be the reason the
situation gets worse.
"""
import math
import os
import struct
import sys
import wave

RATE = 44100


class Noise:
    """A tiny LCG, so the hiss is the same hiss on every machine and run."""

    def __init__(self, seed=20260920):
        self.state = seed

    def next(self):
        self.state = (self.state * 1103515245 + 12345) & 0x7FFFFFFF
        return self.state / 0x3FFFFFFF - 1.0


def write(path, samples, peak=26000):
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, s)) * peak)) for s in samples)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(frames)
    print(f"  {os.path.basename(path)}  {len(samples) / RATE:.2f}s")


def hypo_hiss(duration=0.38):
    """A pneumatic injector: a hard click, then gas escaping under pressure.

    The hiss is one-pole low-passed noise rather than raw noise -- raw white
    noise at this length reads as static, and what a hypospray sounds like is
    air, which is noise with the top taken off.
    """
    noise = Noise()
    out = []
    lp = 0.0
    n = int(RATE * duration)
    for i in range(n):
        t = i / RATE
        progress = t / duration

        # the solenoid: one short bright transient at the very front
        click = 0.0
        if t < 0.014:
            click = 0.55 * math.sin(2 * math.pi * 1800 * t) * math.exp(-160 * t)

        # the gas: noise that opens fast and tails off
        lp += (noise.next() - lp) * 0.16
        envelope = min(1.0, t / 0.012) * math.exp(-5.2 * progress)
        hiss = 0.85 * lp * envelope

        # a faint pitched carrier so it sits as a device rather than a leak
        carrier = 0.10 * math.sin(2 * math.pi * 640 * t) * envelope
        out.append(click + hiss + carrier)
    return out


def tricorder_chirp(duration=0.62):
    """The scan: three rising warbles over a soft bed, each faster than the last.

    Three rather than one because a single sweep reads as a UI beep. The
    acceleration is the whole character of the sound: it says the instrument
    is working through something rather than acknowledging a button.
    """
    out = []
    n = int(RATE * duration)
    phase = 0.0
    bed = 0.0
    sweeps = ((0.02, 0.17, 620.0, 1650.0),
              (0.22, 0.34, 700.0, 1900.0),
              (0.38, 0.47, 820.0, 2250.0))
    for i in range(n):
        t = i / RATE
        freq, level = 0.0, 0.0
        for start, end, f0, f1 in sweeps:
            if start <= t < end:
                k = (t - start) / (end - start)
                freq = f0 + (f1 - f0) * k
                # fade both ends of each warble or it clicks on and off
                level = math.sin(math.pi * k) ** 0.7
                break
        phase += 2 * math.pi * max(freq, 1.0) / RATE
        warble = 0.62 * math.sin(phase) * level
        warble += 0.16 * math.sin(2 * phase) * level

        # a quiet carrier underneath, running the whole length, so the gaps
        # between warbles are the instrument thinking rather than silence
        bed_env = min(1.0, t / 0.03) * math.exp(-2.4 * (t / duration))
        bed += 2 * math.pi * 210.0 / RATE
        out.append(warble + 0.07 * math.sin(bed) * bed_env)
    return out


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42"
    sound = os.path.join(root, "media", "sound")
    write(os.path.join(sound, "TREK_HypoHiss.wav"), hypo_hiss())
    write(os.path.join(sound, "TREK_TricorderChirp.wav"), tricorder_chirp())
    print("medical sounds written")
