"""Measures the bounding box of a DirectX .x mesh -- ours or the game's.

    python tools/meshbbox.py <file.x> [...]
    python tools/meshbbox.py --vanilla              # every weapon the game ships
    python tools/meshbbox.py --vanilla spear knife  # ...matching these words

**This exists because "how big should it be" was answered from memory twice
and wrong both times.** The bat'leth shipped at roughly twice its proper size,
and the note that eventually fixed it -- "a machete is 0.009 wide by 0.335
long, the widest mesh in the arsenal is the canoe paddle at 0.123 across" --
came from a one-off script nobody kept. So it is kept now: the bracket a new
weapon has to sit in is a measurement, not a remembered number.

Two things the numbers mean, both learned the hard way:

  * **The mesh's own dimensions are its size in game.** `WeaponLength` is a
    reach stat and scales nothing. Whatever comes out of here is what the
    player sees in a fist.
  * **Judge the bounding box, not the constant you set.** A curved blade
    bulges past its own chord -- the bat'leth asked for 0.46 and drew 0.531 --
    so the number in the source is not the number the engine uses.

Weapon meshes are Y-up, so for almost everything here the long axis is Y and
a healthy weapon reads as a thin vertical line: small X and Z, larger Y.
"""
import os
import re
import sys

VANILLA = (r"C:\Program Files (x86)\Steam\steamapps\common"
           r"\ProjectZomboid\media\models_X\weapons")


def bbox(path):
    """(dx, dy, dz, nverts) for a .x file, or None if it holds no mesh.

    The .x files here are the text flavour: a Mesh block opens with a vertex
    count and then that many `x;y;z;` triples. Parsed with a regex rather than
    properly, because the only question being asked is how big the thing is --
    a full parser would be a bigger lie about its own accuracy.
    """
    try:
        with open(path, "r", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return None

    m = re.search(r"Mesh\s*\w*\s*\{\s*(\d+)\s*;", text)
    if not m:
        return None
    count = int(m.group(1))
    rest = text[m.end():]

    nums = re.findall(r"(-?\d+\.\d+)\s*;\s*(-?\d+\.\d+)\s*;\s*(-?\d+\.\d+)\s*;",
                      rest[:count * 80 + 4096])
    if not nums:
        return None
    pts = [(float(a), float(b), float(c)) for a, b, c in nums[:count]]
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    zs = [p[2] for p in pts]
    return (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs), len(pts))


def report(paths, label=None):
    rows = []
    for p in paths:
        b = bbox(p)
        if b:
            rows.append((os.path.basename(p), b))
    if not rows:
        print("  nothing measurable")
        return rows
    rows.sort(key=lambda r: -max(r[1][0], r[1][1], r[1][2]))
    if label:
        print(label)
    print(f"  {'mesh':44} {'X':>8} {'Y':>8} {'Z':>8} {'verts':>7}")
    for name, (dx, dy, dz, n) in rows:
        print(f"  {name[:44]:44} {dx:8.3f} {dy:8.3f} {dz:8.3f} {n:7d}")
    return rows


def main(argv):
    if argv and argv[0] == "--vanilla":
        words = [w.lower() for w in argv[1:]]
        paths = []
        for root, _, files in os.walk(VANILLA):
            for f in files:
                if not f.lower().endswith(".x"):
                    continue
                if words and not any(w in f.lower() for w in words):
                    continue
                paths.append(os.path.join(root, f))
        rows = report(paths, f"{len(paths)} vanilla weapon mesh(es):")
        if rows:
            widest = max(rows, key=lambda r: max(r[1][0], r[1][2]))
            longest = max(rows, key=lambda r: r[1][1])
            print()
            print(f"  widest across  {widest[0]} "
                  f"({max(widest[1][0], widest[1][2]):.3f})")
            print(f"  longest        {longest[0]} ({longest[1][1]:.3f})")
        return 0

    if not argv:
        print(__doc__)
        return 1
    report(argv)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
