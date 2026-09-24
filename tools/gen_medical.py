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


def dermal_hum(duration=0.85):
    """The regenerator: a soft rising hum that settles, not a beep.

    Deliberately the least eventful sound of the three. A hypospray is a
    single event and a tricorder is asking a question, but a regenerator is
    held against the skin and *runs* -- so this swells, holds, and fades,
    with two detuned partials beating slowly against each other to keep it
    from sounding like a sine tone.
    """
    out = []
    n = int(RATE * duration)
    pa = pb = pc = 0.0
    for i in range(n):
        t = i / RATE
        progress = t / duration

        # swell in over the first fifth, hold, fade over the last third
        rise = min(1.0, t / (duration * 0.2))
        fall = min(1.0, (1.0 - progress) / 0.33)
        envelope = rise * fall

        # the pitch lifts a little as it works, then settles back
        lift = 1.0 + 0.06 * math.sin(math.pi * progress)
        pa += 2 * math.pi * 330.0 * lift / RATE
        pb += 2 * math.pi * 333.5 * lift / RATE     # detuned: a slow beat
        pc += 2 * math.pi * 660.0 * lift / RATE

        tone = 0.34 * math.sin(pa) + 0.30 * math.sin(pb) + 0.12 * math.sin(pc)
        # a faint shimmer on top so it reads as an instrument rather than an organ
        shimmer = 0.05 * math.sin(pc * 2.0 + 1.5 * math.sin(pa))
        out.append((tone + shimmer) * envelope)
    return out


def combadge_chirp(duration=0.24):
    """The downed ensign's combadge (ENSIGN.md): two bright rising blips.

    Short and high on purpose. It is played every few seconds at the square
    the ensign sits on, as a thing to home in on across a street, so it has
    to cut through and then get out of the way -- a longer or lower sound
    repeated that often would be the thing the player remembers the mission
    for, and not fondly.
    """
    out = []
    n = int(RATE * duration)
    phase = 0.0
    blips = ((0.000, 0.060, 1320.0, 1760.0),
             (0.090, 0.180, 1980.0, 2640.0))
    for i in range(n):
        t = i / RATE
        freq, level = 0.0, 0.0
        for start, end, f0, f1 in blips:
            if start <= t < end:
                k = (t - start) / (end - start)
                freq = f0 + (f1 - f0) * k
                level = min(1.0, k / 0.08) * (1.0 - k) ** 0.6
                break
        phase += 2 * math.pi * max(freq, 1.0) / RATE
        tone = 0.55 * math.sin(phase) + 0.18 * math.sin(3 * phase)
        out.append(tone * level)
    return out


def distress_call(duration=1.2):
    """A distress call arriving: a two-tone warble, three times over.

    Alternating tones rather than a rising sweep so it cannot be mistaken for
    the tricorder, and a slow tremolo so it reads as a signal coming in from
    somewhere rather than a button being pressed.
    """
    out = []
    n = int(RATE * duration)
    phase = 0.0
    for i in range(n):
        t = i / RATE
        freq = 880.0 if int(t / 0.1) % 2 == 0 else 660.0
        phase += 2 * math.pi * freq / RATE
        cycle = (t % 0.4) / 0.4
        gate = 1.0 if cycle < 0.8 else 0.0
        env = min(1.0, t / 0.02) * min(1.0, (duration - t) / 0.15)
        tremolo = 0.75 + 0.25 * math.sin(2 * math.pi * 7.0 * t)
        tone = 0.5 * math.sin(phase) + 0.14 * math.sin(2 * phase)
        out.append(tone * gate * env * tremolo)
    return out


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42"
    sound = os.path.join(root, "media", "sound")
    write(os.path.join(sound, "TREK_HypoHiss.wav"), hypo_hiss())
    write(os.path.join(sound, "TREK_TricorderChirp.wav"), tricorder_chirp())
    write(os.path.join(sound, "TREK_DermalHum.wav"), dermal_hum())
    # Not medical, but the same oscillators and the same writer: the downed
    # ensign's two sounds (ENSIGN.md).
    write(os.path.join(sound, "TREK_CombadgeChirp.wav"), combadge_chirp())
    write(os.path.join(sound, "TREK_DistressCall.wav"), distress_call())
    print("medical sounds written")
