"""Prints the real method signatures of a Project Zomboid Java class.

The game ships no javap, and guessing at engine method names has cost this
project two broken sessions -- `UnSet` instead of `unset` threw once per
square and froze the build. Check the name here before calling it from Lua.

    python tools/pzapi.py zombie.iso.IsoGridSquare stairs
    python tools/pzapi.py zombie.iso.IsoObject container
"""
import sys, zipfile, struct
JAR = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\projectzomboid.jar"

def parse(data):
    p = 8  # magic + minor + major
    cp_count = struct.unpack_from(">H", data, p)[0]; p += 2
    cp = {}
    i = 1
    while i < cp_count:
        tag = data[p]; p += 1
        if tag == 1:
            ln = struct.unpack_from(">H", data, p)[0]; p += 2
            cp[i] = data[p:p+ln].decode("utf-8", "replace"); p += ln
        elif tag in (7, 8, 16, 19, 20):
            p += 2
        elif tag == 15:
            p += 3
        elif tag in (3, 4, 9, 10, 11, 12, 17, 18):
            p += 4
        elif tag in (5, 6):
            p += 8; i += 1
        else:
            raise ValueError(f"tag {tag}")
        i += 1
    p += 6  # access, this, super
    ifc = struct.unpack_from(">H", data, p)[0]; p += 2 + ifc*2
    def members():
        nonlocal p
        cnt = struct.unpack_from(">H", data, p)[0]; p += 2
        out = []
        for _ in range(cnt):
            acc, ni, di = struct.unpack_from(">HHH", data, p); p += 6
            ac = struct.unpack_from(">H", data, p)[0]; p += 2
            for _ in range(ac):
                al = struct.unpack_from(">I", data, p+2)[0]; p += 6 + al
            out.append((acc, cp.get(ni), cp.get(di)))
        return out
    fields = members()
    methods = members()
    return fields, methods

cls = sys.argv[1].replace(".", "/") + ".class"
pat = sys.argv[2].lower() if len(sys.argv) > 2 else None
with zipfile.ZipFile(JAR) as z:
    data = z.read(cls)
f, m = parse(data)
for acc, n, d in m:
    line = f"{n}{d}"
    if pat is None or pat in line.lower():
        print(("static " if acc & 8 else "") + line)
