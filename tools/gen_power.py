"""Generates the ship's two power sounds (ENERGY.md 8.5).

    python tools/gen_power.py TrekShuttle/42

  TREK_PowerUp    about 3.5 s: a low warp-core hum swelling up from nothing, a
                  slow rising sweep over it, and a three-note major chime as
                  the lights come on, landing on a warm sustained chord that
                  fades into the core's idle hum. The one the author asked to
                  be *super pleasant*: it is the payoff of the cold start.
  TREK_PowerDown  about 1 s: a falling whine and a thud. Deliberately
                  unpleasant, and short.

In the house style of gen_medical.py: synthesized from the standard library,
deterministically -- the noise uses its own seeded generator, so a re-run
writes byte-identical files and a regenerated asset is never a silent diff.
Neither is copied franchise audio.

**Vetted by listening**, the way the icons are vetted by looking: numbers can
say it is not clipping and not silent, and nothing but an ear can say it is
pleasant. The script also writes a waveform strip of each to design/art/power/
so the shape can be looked at, and prints each sound's peak and length.
"""
import math
import os
import struct
import sys
import wave

RATE = 44100


class Noise:
    """A tiny LCG, so the thud's grit is the same on every machine and run."""

    def __init__(self, seed=20260924):
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
    top = max(abs(s) for s in samples)
    print(f"  {os.path.basename(path)}  {len(samples) / RATE:.2f}s  peak {top:.2f}")


def normalise(samples, to=0.92):
    top = max(abs(s) for s in samples) or 1.0
    return [s * to / top for s in samples]


def smooth(x):
    """0..1 -> 0..1, eased at both ends."""
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def bell(t, freq, decay):
    """A soft struck bell: a sine, a quieter octave and a faint fifth above
    it, each decaying a little faster than the one below, and a 6 ms attack so
    it never clicks."""
    if t < 0:
        return 0.0
    attack = min(1.0, t / 0.006)
    env = attack * math.exp(-t / decay)
    return env * (math.sin(2 * math.pi * freq * t)
                  + 0.35 * math.exp(-t / (decay * 0.6)) * math.sin(2 * math.pi * freq * 2 * t)
                  + 0.12 * math.exp(-t / (decay * 0.4)) * math.sin(2 * math.pi * freq * 3 * t))


def power_up(duration=3.6):
    """The lights coming on.

    Four layers, each with its own envelope:

      * the **core hum**, 55 Hz with its second and third harmonics and a slow
        3 Hz shimmer, swelling from silence over two seconds and settling to
        a quieter idle rather than stopping;
      * the **sweep**, two slightly detuned sines gliding 180 -> 720 Hz on an
        eased curve, so it rises like a machine spinning up rather than a
        siren;
      * the **chime**, C5 E5 G5 a quarter-second apart, as the sweep arrives;
      * the **chord**, C major around middle C, swelling in under the chime
        and fading out over the last second into the idle hum.
    """
    n = int(RATE * duration)
    out = []
    sweep_phase_a = sweep_phase_b = 0.0
    chime_at = (2.05, 2.30, 2.55)
    chime_f = (523.25, 659.25, 783.99)
    chord_f = (261.63, 329.63, 392.00, 523.25)
    for i in range(n):
        t = i / RATE

        # Core hum: swell, then idle.
        swell = smooth(t / 2.1)
        idle = 0.55 + 0.45 * (1 - smooth((t - 2.4) / 1.0))
        tail = 1 - smooth((t - (duration - 0.5)) / 0.5)
        shimmer = 1 + 0.08 * math.sin(2 * math.pi * 3.0 * t)
        hum = (math.sin(2 * math.pi * 55 * t)
               + 0.5 * math.sin(2 * math.pi * 110 * t)
               + 0.18 * math.sin(2 * math.pi * 165 * t)) * shimmer
        s = 0.30 * hum * swell * idle * tail

        # The sweep: in from 0.25 s, arriving at 2.05 s, gone by 2.6 s.
        if 0.25 <= t <= 2.7:
            k = smooth((t - 0.25) / 1.8)
            f = 180 + (720 - 180) * k
            sweep_phase_a += 2 * math.pi * f / RATE
            sweep_phase_b += 2 * math.pi * f * 1.004 / RATE
            env = smooth((t - 0.25) / 0.6) * (1 - smooth((t - 2.05) / 0.55))
            s += 0.13 * env * (math.sin(sweep_phase_a) + math.sin(sweep_phase_b))

        # The chime.
        for at, f in zip(chime_at, chime_f):
            s += 0.30 * bell(t - at, f, 0.9)

        # The chord, swelling under the last note and fading to the end.
        if t >= 2.4:
            c_env = smooth((t - 2.4) / 0.35) * (1 - smooth((t - 2.9) / (duration - 2.9)))
            chord = sum(math.sin(2 * math.pi * f * t) + 0.25 * math.sin(2 * math.pi * f * 2 * t)
                        for f in chord_f)
            s += 0.07 * c_env * chord
        out.append(s)
    return normalise(out)


def power_down(duration=1.05):
    """The lights going out: a whine falling away on an exponential curve,
    roughened by a little odd-harmonic content, then a low thud with a burst
    of low-passed grit under it."""
    noise = Noise()
    n = int(RATE * duration)
    out = []
    phase = 0.0
    lp = 0.0
    for i in range(n):
        t = i / RATE
        s = 0.0
        if t < 0.82:
            k = t / 0.82
            f = 80 + (950 - 80) * math.exp(-3.2 * k)
            phase += 2 * math.pi * f / RATE
            env = min(1.0, t / 0.02) * (1 - k) ** 1.4
            s += 0.55 * env * (math.sin(phase) + 0.3 * math.sin(3 * phase)
                               + 0.12 * math.sin(5 * phase))
        if t >= 0.80:
            u = t - 0.80
            thud = math.exp(-u / 0.07) * math.sin(2 * math.pi * (48 + 30 * math.exp(-u / 0.03)) * u)
            lp += 0.08 * (noise.next() - lp)
            s += 0.9 * thud + 1.6 * lp * math.exp(-u / 0.05)
        out.append(s)
    return normalise(out, 0.9)


def strip(path, samples, width=900, height=120):
    """A waveform strip, for looking at the shape (design/art/power/)."""
    try:
        from PIL import Image, ImageDraw
    except ImportError:
        return
    img = Image.new("RGB", (width, height), (8, 10, 18))
    d = ImageDraw.Draw(img)
    per = max(1, len(samples) // width)
    mid = height / 2
    for x in range(width):
        chunk = samples[x * per:(x + 1) * per] or [0.0]
        top, bot = max(chunk), min(chunk)
        d.line([(x, mid - top * mid * 0.95), (x, mid - bot * mid * 0.95)], fill=(255, 204, 102))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    img.save(path)


def main():
    if len(sys.argv) < 2:
        raise SystemExit("usage: python tools/gen_power.py TrekShuttle/42")
    base = sys.argv[1]
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    sound = os.path.join(base, "media", "sound")
    up, down = power_up(), power_down()
    write(os.path.join(sound, "TREK_PowerUp.wav"), up)
    write(os.path.join(sound, "TREK_PowerDown.wav"), down, peak=24000)
    art = os.path.join(root, "design", "art", "power")
    strip(os.path.join(art, "power_up_wave.png"), up)
    strip(os.path.join(art, "power_down_wave.png"), down)


if __name__ == "__main__":
    main()
