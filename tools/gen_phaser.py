"""Generates the phaser inventory icon and original firing sound.

Like every other asset here they are generated rather than hand-authored, so
the mod stays reproducible from source. The firing sound is a brief electronic
chirp synthesized with the Python standard library, not copied franchise audio.

    python tools/gen_phaser.py TrekShuttle/42
"""
import sys, os, math, struct, wave
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pngwrite import Image

SHELL      = (206, 208, 214, 255)     # Starfleet off-white casing
SHELL_LITE = (238, 240, 245, 255)
SHELL_DARK = (152, 156, 166, 255)
SHELL_DEEP = (96, 100, 112, 255)
GRIP       = (44, 46, 54, 255)
GRIP_LITE  = (82, 86, 98, 255)
TRIM       = (46, 74, 122, 255)
EMIT       = (236, 96, 52, 255)
EMIT_CORE  = (255, 226, 190, 255)
LED        = (96, 176, 240, 255)
HALO_RGB   = (255, 122, 64)


def halo(img, cx, cy, rx, ry, peak=140):
    """A soft round glow at the emitter.

    pngwrite does not blend, so this goes down before anything solid and the
    body is painted straight over the middle of it. Drawn per pixel: a
    rectangular halo reads as a box behind the weapon.
    """
    for y in range(int(cy - ry), int(cy + ry) + 1):
        for x in range(int(cx - rx), int(cx + rx) + 1):
            d = math.hypot((x - cx) / rx, (y - cy) / ry)
            if d >= 1.0:
                continue
            a = int(peak * (1.0 - d) ** 2)
            if a > 0:
                img.set(x, y, HALO_RGB + (a,))


def body_row(img, y, x0, x1):
    """One scanline of the casing: lit along the top edge, shaded below."""
    img.rect(x0, y, x1, y + 1, SHELL)
    img.rect(x0, y, x0 + 2, y + 1, SHELL_LITE)
    img.rect(x1 - 2, y, x1, y + 1, SHELL_DARK)


def build_icon(path):
    """64x64: the phaser lying muzzle-left, three-quarters on."""
    img = Image(64, 64, (0, 0, 0, 0))

    # the glow at the aperture, laid down first
    halo(img, 9, 26, 14, 12, peak=126)

    # --- body: a wedge that tapers toward the muzzle --------------------
    for i, y in enumerate(range(18, 34)):
        t = i / 15.0
        left = int(8 + 4 * (1.0 - t))
        body_row(img, y, left, 50)
    img.rect(8, 24, 50, 26, TRIM)                 # the trim seam
    img.rect(8, 18, 50, 19, SHELL_LITE)
    img.rect(8, 32, 50, 34, SHELL_DEEP)

    # --- emitter aperture, forward --------------------------------------
    img.rect(4, 22, 12, 30, SHELL_DEEP)
    img.rect(5, 23, 11, 29, EMIT)
    img.rect(6, 25, 10, 28, EMIT_CORE)

    # --- the power/level strip on the flank ------------------------------
    for i in range(5):
        c = LED if i < 4 else SHELL_DARK
        img.rect(20 + i * 5, 28, 23 + i * 5, 31, c)

    # --- grip, squared off under the aft end -----------------------------
    img.rect(36, 34, 50, 52, GRIP)
    img.rect(36, 34, 39, 52, GRIP_LITE)
    for y in range(37, 51, 4):                    # finger ridges
        img.rect(39, y, 48, y + 1, GRIP_LITE)
    img.rect(36, 50, 50, 52, SHELL_DEEP)

    # --- the thumb control on the spine ----------------------------------
    img.rect(30, 19, 40, 23, SHELL_DARK)
    img.rect(32, 20, 38, 22, LED)

    # --- aft cap ----------------------------------------------------------
    img.rect(50, 18, 55, 34, SHELL_DARK)
    img.rect(53, 18, 55, 34, SHELL_DEEP)

    img.save(path)
    return img


def build_sound(path):
    """Write a short mono energy pulse using deterministic oscillators."""
    rate = 44100
    duration = 0.28
    frames = []
    phase_a = 0.0
    phase_b = 0.0

    for i in range(int(rate * duration)):
        t = i / rate
        progress = t / duration
        attack = min(1.0, t / 0.006)
        envelope = attack * math.exp(-10.5 * progress)
        freq_a = 1000.0 - 580.0 * progress
        freq_b = 1500.0 - 850.0 * progress
        phase_a += 2.0 * math.pi * freq_a / rate
        phase_b += 2.0 * math.pi * freq_b / rate
        carrier = 0.62 * math.sin(phase_a) + 0.25 * math.sin(phase_b)
        shimmer = 0.13 * math.sin(2.0 * phase_a + 0.35 * math.sin(phase_b))
        sample = max(-1.0, min(1.0, (carrier + shimmer) * envelope))
        frames.append(struct.pack("<h", int(sample * 28500)))

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"".join(frames))


if __name__ == "__main__":
    root = sys.argv[1]
    build_icon(os.path.join(root, "media", "ui", "TREK_Phaser.png"))
    build_icon(os.path.join(root, "media", "textures", "Item_TREK_Phaser.png"))
    build_sound(os.path.join(root, "media", "sound", "TREK_PhaserPulse.wav"))
    print("phaser icon and firing sound written")
