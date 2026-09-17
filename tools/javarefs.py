"""Shows what a Project Zomboid Java method actually touches.

tools/pzapi.py answers "does this method exist, and is it public". This answers
"what does it do": for each matching method it lists every field read or
written and every method called in its bytecode, with descriptors.

That is how the flight bugs were found. setGodMod turned out to call
Role.hasCapability(ToggleGodModHimself) before doing anything -- silently
refused for an ordinary player -- and setGodModCheat reaches
PlayerCheats.set(CheatType, boolean), which checks Core.debug. Neither fact is
visible from a method's name or signature.

    python tools/javarefs.py zombie.characters.IsoGameCharacter "setGodMod("
    python tools/javarefs.py zombie.characters.IsoZombie @isZombiesDontAttack

A pattern matches method names and signatures; a pattern starting with @
matches methods whose bytecode *references* it (who calls this, who reads
that field). References are listed in bytecode order, which is not control
flow: branches are not shown, so read the list as "may", not "does".
"""
import struct, sys, zipfile
JAR = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\projectzomboid.jar"
def parse(data):
    p = 8; n = struct.unpack_from(">H", data, p)[0]; p += 2
    cp = [None]*n; i = 1
    while i < n:
        t = data[p]; p += 1
        if t == 1:
            l = struct.unpack_from(">H", data, p)[0]; p += 2; cp[i] = ("utf8", data[p:p+l].decode("utf-8","replace")); p += l
        elif t in (7, 8, 16, 19, 20):
            cp[i] = (t, struct.unpack_from(">H", data, p)[0]); p += 2
        elif t == 15: cp[i] = (t,); p += 3
        elif t in (9, 10, 11, 12, 17, 18):
            a, b = struct.unpack_from(">HH", data, p); cp[i] = (t, a, b); p += 4
        elif t in (3, 4): cp[i] = (t,); p += 4
        elif t in (5, 6): cp[i] = (t,); p += 8; i += 1
        i += 1
    def utf(k): return cp[k][1]
    def ref(k):
        e = cp[k]
        if not e or e[0] not in (9, 10, 11): return None
        cls = utf(cp[e[1]][1]); nt = cp[e[2]]
        return f"{cls.split('/')[-1]}.{utf(nt[1])}{utf(nt[2])}"
    p += 6; ic = struct.unpack_from(">H", data, p)[0]; p += 2 + 2*ic
    def skip_members():
        nonlocal p
        c = struct.unpack_from(">H", data, p)[0]; p += 2
        for _ in range(c):
            p += 6; ac = struct.unpack_from(">H", data, p)[0]; p += 2
            for _ in range(ac):
                l = struct.unpack_from(">I", data, p+2)[0]; p += 6 + l
    skip_members()
    out = {}
    c = struct.unpack_from(">H", data, p)[0]; p += 2
    for _ in range(c):
        acc, ni, di = struct.unpack_from(">HHH", data, p); p += 6
        ac = struct.unpack_from(">H", data, p)[0]; p += 2
        name = utf(ni) + utf(di)
        for _ in range(ac):
            an, l = struct.unpack_from(">HI", data, p)
            if utf(an) == "Code":
                clen = struct.unpack_from(">I", data, p+10)[0]
                code = data[p+14:p+14+clen]
                refs = []
                for j in range(len(code)-2):
                    if code[j] in (0xb2,0xb3,0xb4,0xb5,0xb6,0xb7,0xb8,0xb9):
                        k = struct.unpack_from(">H", code, j+1)[0]
                        if 0 < k < len(cp):
                            r = ref(k)
                            if r and r not in refs: refs.append(r)
                out.setdefault(name, []).extend(refs)
            p += 6 + l
    return out

def main():
    if len(sys.argv) < 3:
        print(__doc__)
        return 1
    cls, pats = sys.argv[1], sys.argv[2:]
    with zipfile.ZipFile(JAR) as z:
        m = parse(z.read(cls.replace(".", "/") + ".class"))
    for name, refs in m.items():
        by_name = any((not pt.startswith("@")) and pt in name for pt in pats)
        by_ref = any(pt.startswith("@") and any(pt[1:] in r for r in refs) for pt in pats)
        if by_name or by_ref:
            print(name)
            for r in refs:
                print("    " + r)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
