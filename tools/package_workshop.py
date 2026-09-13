"""Build and optionally stage the TrekShuttle Steam Workshop upload.

Creates the Build 42 layout expected by Project Zomboid's in-game uploader:

    TrekShuttle/
      workshop.txt
      preview.png
      Contents/mods/TrekShuttle/42/...

Run from the project root:

    py tools/package_workshop.py
    py tools/package_workshop.py --install
"""
import argparse
from pathlib import Path
import shutil
import struct

from gen_poster import build as build_poster
from pngwrite import Image
from preview_model import read_png_rgba

ROOT = Path(__file__).resolve().parent.parent
MOD = ROOT / "TrekShuttle"
BUILD = ROOT / "workshop" / "TrekShuttle"
INSTALLED = Path.home() / "Zomboid" / "Workshop" / "TrekShuttle"

TITLE = "Starfleet Shuttlecraft (Build 42)"
DESCRIPTION = [
    "A Starfleet Type 6 shuttlecraft for Project Zomboid Build 42.",
    "Beam aboard from anywhere, travel to map coordinates, land on clear ground, and walk through the rear hatch.",
    "Its compact interior includes paired flight stations, a fold-down berth, sink, emergency medical supplies, provisions, mission storage, and rechargeable phasers.",
    "The exterior requires a clear 3x5 landing area.",
    "Type 6 shuttle 3D model by octave767, used under CC BY 4.0: https://sketchfab.com/3d-models/star-trek-type-6-shuttle-e2ca902b9115429ab20293617a9d3317",
    "This is an unofficial fan mod and is not affiliated with or endorsed by Paramount or The Indie Stone.",
]


def png_dimensions(path):
    with path.open("rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError("not a PNG: " + str(path))
        length = struct.unpack(">I", stream.read(4))[0]
        if stream.read(4) != b"IHDR" or length < 8:
            raise ValueError("PNG has no IHDR: " + str(path))
        return struct.unpack(">II", stream.read(8))


def square_preview(source, output, size=256):
    """Center-crop and nearest-neighbor scale the generated poster."""
    width, height, pixels = read_png_rgba(str(source))
    crop = min(width, height)
    left = (width - crop) // 2
    top = (height - crop) // 2
    image = Image(size, size)
    for y in range(size):
        source_y = top + min(crop - 1, y * crop // size)
        for x in range(size):
            source_x = left + min(crop - 1, x * crop // size)
            index = (source_y * width + source_x) * 4
            image.set(x, y, tuple(pixels[index:index + 4]))
    image.save(str(output))


def workshop_text():
    lines = ["version=1", "title=" + TITLE]
    lines.extend("description=" + line for line in DESCRIPTION)
    lines.extend(["tags=Build 42", "visibility=private"])
    return "\n".join(lines) + "\n"


def validate(package):
    preview = package / "preview.png"
    metadata = package / "workshop.txt"
    packaged_mod = package / "Contents" / "mods" / "TrekShuttle"
    required = [
        metadata,
        preview,
        packaged_mod / "42" / "mod.info",
        packaged_mod / "42" / "poster.png",
        packaged_mod / "42" / "media" / "models_X" / "TREK_Shuttle.x",
        packaged_mod / "42" / "media" / "textures" / "TREK_Shuttle.png",
    ]
    missing = [str(path) for path in required if not path.is_file()]
    if missing:
        raise SystemExit("Workshop package is missing:\n  " + "\n  ".join(missing))
    if png_dimensions(preview) != (256, 256):
        raise SystemExit("preview.png must be exactly 256x256")
    text = metadata.read_text(encoding="utf-8")
    for field in ("version=", "title=", "description=", "tags=", "visibility="):
        if field not in text:
            raise SystemExit("workshop.txt is missing " + field)
    count = sum(1 for path in package.rglob("*") if path.is_file())
    print("validated", count, "Workshop package files")
    print("preview", png_dimensions(preview))
    print("visibility private (change after testing on Steam)")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--install", action="store_true",
                        help="also copy to ~/Zomboid/Workshop/TrekShuttle")
    args = parser.parse_args()

    # Keep the mod-screen poster synchronized with the current generated hull.


    if BUILD.exists():
        shutil.rmtree(BUILD)
    packaged_mod = BUILD / "Contents" / "mods" / "TrekShuttle"
    packaged_mod.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(MOD, packaged_mod)
    (BUILD / "workshop.txt").write_text(workshop_text(), encoding="utf-8")
    square_preview(MOD / "42" / "poster.png", BUILD / "preview.png")
    validate(BUILD)
    print("package ->", BUILD)

    if args.install:
        if INSTALLED.exists():
            shutil.rmtree(INSTALLED)
        INSTALLED.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(BUILD, INSTALLED)
        validate(INSTALLED)
        print("uploader staging ->", INSTALLED)


if __name__ == "__main__":
    main()
