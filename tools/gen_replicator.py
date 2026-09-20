"""Generates the replicator's materialisation sound.

    python tools/gen_replicator.py TrekShuttle/42

One sound, synthesized from the standard library and deterministic -- the
sparkle runs off its own seeded generator rather than `random`, so re-running
this writes a byte-identical file and a regenerated asset is never a silent
diff. It is not copied franchise audio: it is three oscillator banks and an
envelope, built to the same recipe as tools/gen_medical.py's three.

Played with playSoundLocal, like the medical set's: it belongs to whoever is
standing at the machine, it does not travel, and -- the half that matters --
it does not put a noise on the map for the dead to walk towards. A galley
appliance that called a horde would be a strange thing to build into a ship.

The shape of it is the shape of the effect: a field builds (a rising hum), the
pattern resolves (a shimmer of high partials beating against each other), and
the thing is there (a short bell). Deliberately under a second -- it plays on
every item, and a long sound is charming once and tiresome at the tenth.
"""
import math
import os
import struct
import sys
import wave

RATE = 44100


class Noise:
    """A tiny LCG, so the sparkle is the same sparkle on every machine."""

    def __init__(self, seed=20260921):
        self.state = seed

    def next(self):
        self.state = (self.state * 1103515245 + 12345) & 0x7FFFFFFF
        return self.state / 0x3FFFFFFF - 1.0


def write(path, samples, peak=25000):
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, s)) * peak)) for s in samples)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(frames)
    print(f"  {os.path.basename(path)}  {len(samples) / RATE:.2f}s")


def materialise(duration=0.78):
    """The field, the shimmer and the bell, in that order and overlapping.

    The three layers are what keeps it from reading as a UI beep:

      * the **field** is a low pair of detuned oscillators that rise about a
        fifth over the first half and then hold -- the machine committing;
      * the **shimmer** is five high partials, each amplitude-modulated at its
        own rate, so they beat against each other instead of forming a chord.
        That interference *is* the transporter-ish character; a single high
        sine sounds like a microwave finishing;
      * the **bell** is one short struck partial at the end, which is the only
        part a player consciously hears: it says the thing is in the tray.
    """
    noise = Noise()
    out = []
    n = int(RATE * duration)
    field_a = field_b = 0.0
    shimmer_phase = [0.0] * 5
    bell_phase = 0.0
    bell_at = duration * 0.62

    # Five partials, none of them a whole-number multiple of another: whole
    # multiples would lock into a chord and stop shimmering.
    partials = ((1840.0, 6.1), (2270.0, 7.7), (2910.0, 4.3),
                (3480.0, 9.2), (4130.0, 5.6))

    for i in range(n):
        t = i / RATE
        progress = t / duration

        # --- the field ---------------------------------------------------
        rise = min(1.0, t / (duration * 0.30))
        fall = min(1.0, (1.0 - progress) / 0.30)
        field_env = rise * fall
        lift = 1.0 + 0.48 * min(1.0, progress / 0.5)
        field_a += 2 * math.pi * 180.0 * lift / RATE
        field_b += 2 * math.pi * 181.7 * lift / RATE       # detuned: a slow beat
        field = (0.22 * math.sin(field_a) + 0.20 * math.sin(field_b)) * field_env

        # --- the shimmer -------------------------------------------------
        shimmer = 0.0
        shimmer_env = (min(1.0, t / 0.06) * math.exp(-2.0 * progress)
                       * (0.55 + 0.45 * math.sin(math.pi * progress)))
        for k, (freq, rate) in enumerate(partials):
            shimmer_phase[k] += 2 * math.pi * freq / RATE
            am = 0.5 + 0.5 * math.sin(2 * math.pi * rate * t + k)
            shimmer += math.sin(shimmer_phase[k]) * am
        shimmer *= 0.075 * shimmer_env
        # a whisper of noise under it, so the partials are not naked sines
        shimmer += 0.018 * noise.next() * shimmer_env

        # --- the bell ------------------------------------------------------
        bell = 0.0
        if t >= bell_at:
            bt = t - bell_at
            bell_phase += 2 * math.pi * 1240.0 / RATE
            bell = (0.30 * math.sin(bell_phase)
                    + 0.10 * math.sin(bell_phase * 2.01)) * math.exp(-7.5 * bt)

        out.append(field + shimmer + bell)
    return out


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42"
    sound = os.path.join(root, "media", "sound")
    write(os.path.join(sound, "TREK_Replicate.wav"), materialise())
    print("replicator sound written")
