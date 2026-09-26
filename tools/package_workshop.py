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

# The published Steam Workshop item.
#
# This one line is the whole difference between updating the mod and
# publishing a second copy of it. The in-game uploader has no other way to
# know which item it is looking at: the id lives in workshop.txt and nowhere
# else. Upload without it and Steam makes a *new* item with a new id, no
# subscribers and no ratings, while the original sits there with the old
# files in it -- and there is no undo.
#
# It used to live only in ~/Zomboid/Workshop/TrekShuttle/workshop.txt, which
# --install deletes and rewrites. It is kept here so the repo owns it.
WORKSHOP_ID = "3801178990"

# Public, because the item already is. Writing visibility=private into an
# update hides a mod people are subscribed to. Set this to "private" only for
# a genuinely unpublished first upload.
VISIBILITY = "public"

# What the 256x256 Workshop thumbnail is cut from. The in-game uploader takes
# this one image and no other -- the gallery is added on the Steam web page
# afterwards -- so it is worth naming here rather than leaving to a default.
# Set to None to fall back to the generated mods-screen poster.
PREVIEW_SOURCE = ROOT / "screen_shots" / "ShuttleLanded.png"

# Shift the square crop, in source pixels: positive x moves it right,
# positive y moves it down. Zero centres it.
PREVIEW_OFFSET = (0, 0)

# The franchise name leads the title because Steam Workshop search matches
# titles strongly and description text weakly: without it, "Star Trek"
# does not find this item at all.
TITLE = "Star Trek: Starfleet Shuttlecraft (Build 42)"
# The listing text lives in workshop/description.txt, one paragraph line per
# line, so it can be edited without touching this script.
DESCRIPTION = (ROOT / "workshop" / "description.txt").read_text(
    encoding="utf-8").splitlines()


def png_dimensions(path):
    with path.open("rb") as stream:
        if stream.read(8) != b"\x89PNG\r\n\x1a\n":
            raise ValueError("not a PNG: " + str(path))
        length = struct.unpack(">I", stream.read(4))[0]
        if stream.read(4) != b"IHDR" or length < 8:
            raise ValueError("PNG has no IHDR: " + str(path))
        return struct.unpack(">II", stream.read(8))


def square_preview(source, output, size=256, offset_x=0, offset_y=0):
    """Center-crop and box-filter the preview source down to `size`.

    The source used to be the generated pixel-art poster, where a
    nearest-neighbour pick was not just adequate but correct: sampling a
    pixel-art image is supposed to keep hard edges. PREVIEW_SOURCE is now a
    gameplay screenshot, and the same pick aliases it badly -- 705 down to 256
    throws away five pixels in six and whichever one it lands on becomes the
    whole square. Averaging the footprint instead is the difference between a
    hull and a handful of noise.

    offset_x/offset_y shift the crop window in source pixels, because the
    subject of a screenshot is rarely in the exact middle of the frame. They
    are clamped so the window cannot run off the edge.
    """
    width, height, pixels = read_png_rgba(str(source))
    crop = min(width, height)
    left = max(0, min(width - crop, (width - crop) // 2 + offset_x))
    top = max(0, min(height - crop, (height - crop) // 2 + offset_y))
    image = Image(size, size)
    for y in range(size):
        y0 = top + y * crop // size
        y1 = max(y0 + 1, top + (y + 1) * crop // size)
        for x in range(size):
            x0 = left + x * crop // size
            x1 = max(x0 + 1, left + (x + 1) * crop // size)
            r = g = b = a = 0
            count = 0
            for sy in range(y0, y1):
                row = sy * width
                for sx in range(x0, x1):
                    i = (row + sx) * 4
                    r += pixels[i]
                    g += pixels[i + 1]
                    b += pixels[i + 2]
                    a += pixels[i + 3]
                    count += 1
            image.set(x, y, (r // count, g // count, b // count, a // count))
    image.save(str(output))


def workshop_text():
    lines = ["version=1"]
    if WORKSHOP_ID:
        lines.append("id=" + WORKSHOP_ID)
    lines.append("title=" + TITLE)
    lines.extend("description=" + line for line in DESCRIPTION)
    lines.extend(["tags=Build 42", "visibility=" + VISIBILITY])
    return "\n".join(lines) + "\n"


def published_id(text):
    """The id= from a workshop.txt, or None."""
    for line in text.splitlines():
        if line.startswith("id="):
            return line[3:].strip()
    return None


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
    staged = published_id(text)
    if WORKSHOP_ID and staged != WORKSHOP_ID:
        raise SystemExit("workshop.txt does not carry id=" + WORKSHOP_ID +
                         "; uploading it would publish a new item")
    count = sum(1 for path in package.rglob("*") if path.is_file())
    print("validated", count, "Workshop package files")
    print("preview", png_dimensions(preview))
    print("workshop item", staged or "UNPUBLISHED (a new item will be created)")
    print("visibility", VISIBILITY)


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
    source = PREVIEW_SOURCE if PREVIEW_SOURCE else MOD / "42" / "poster.png"
    if not source.is_file():
        raise SystemExit("preview source is missing: " + str(source))
    square_preview(source, BUILD / "preview.png", offset_x=PREVIEW_OFFSET[0],
                   offset_y=PREVIEW_OFFSET[1])
    print("preview cut from", source.name)
    validate(BUILD)
    print("package ->", BUILD)

    if args.install:
        # --install wipes the staging folder, which is where the published id
        # used to be the only copy. Read it back first and refuse to point the
        # uploader at a different item than the one already staged: silently
        # retargeting an upload is not a recoverable mistake.
        existing = INSTALLED / "workshop.txt"
        if existing.is_file():
            staged = published_id(existing.read_text(encoding="utf-8"))
            if staged and staged != WORKSHOP_ID:
                raise SystemExit(
                    f"{INSTALLED} is staged as Workshop item {staged} but this "
                    f"package is {WORKSHOP_ID}. Fix WORKSHOP_ID before "
                    f"installing; uploading the wrong one cannot be undone.")
            if staged:
                print("updating staged Workshop item", staged)

        if INSTALLED.exists():
            shutil.rmtree(INSTALLED)
        INSTALLED.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(BUILD, INSTALLED)
        validate(INSTALLED)
        print("uploader staging ->", INSTALLED)


if __name__ == "__main__":
    main()
