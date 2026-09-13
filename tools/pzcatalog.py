"""Builds and queries catalogues of build 42 sprites and item ids.

Every sprite name and item id the mod uses has to exist in the installed
build, and a wrong one fails silently -- the shelf is simply empty and no
error appears anywhere. Look names up here before putting them in the config,
and tests/test_assets.py then keeps them honest.

    python tools/pzcatalog.py build                  # (re)build the catalogues
    python tools/pzcatalog.py sprites container shelves
    python tools/pzcatalog.py sprites name furniture_bedding
    python tools/pzcatalog.py items Book
    python tools/pzcatalog.py check Base.Hammer,Base.Pills
"""
import json, os, re, sys, collections

PZ = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_catalog")


def build():
    os.makedirs(OUT, exist_ok=True)

    # --- tiles ---------------------------------------------------------
    src = open(os.path.join(PZ, "newtiledefinitions.tiles.txt"),
               encoding="utf-8", errors="replace").read().splitlines()
    tiles, byfile = {}, collections.defaultdict(list)
    cur_file, pending, i, n = None, None, 0, len(src)
    while i < n:
        line = src[i].strip()
        if line.startswith("file ="):
            cur_file = line.split("=", 1)[1].strip()
        elif line.startswith("//"):
            pending = line[2:].strip()
        elif line == "tile":
            j = i + 1
            if j < n and src[j].strip() == "{":
                j += 1
                props = {}
                while j < n and src[j].strip() != "}":
                    l = src[j].strip()
                    if "=" in l:
                        k, v = l.split("=", 1)
                        props[k.strip()] = v.strip()
                    j += 1
                if pending and " " not in pending:
                    tiles[pending] = props
                    byfile[cur_file].append(pending)
                pending, i = None, j
        i += 1
    json.dump({"tiles": tiles, "byfile": dict(byfile)},
              open(os.path.join(OUT, "tiles.json"), "w"), indent=0)

    # --- items ---------------------------------------------------------
    items = collections.defaultdict(list)
    mod_re, item_re = re.compile(r"^\s*module\s+(\w+)"), re.compile(r"^\s*item\s+([\w.]+)")
    for dp, _, fns in os.walk(os.path.join(PZ, "scripts")):
        for fn in fns:
            if not fn.endswith(".txt"):
                continue
            mod = None
            for line in open(os.path.join(dp, fn), encoding="utf-8",
                             errors="replace").read().splitlines():
                m = mod_re.match(line)
                if m:
                    mod = m.group(1); continue
                m = item_re.match(line)
                if m and mod:
                    items[mod].append(m.group(1))
    json.dump({k: sorted(set(v)) for k, v in items.items()},
              open(os.path.join(OUT, "items.json"), "w"), indent=0)
    print(f"catalogued {len(tiles)} sprites and "
          f"{sum(len(v) for v in items.values())} items -> {OUT}")


def load(name):
    path = os.path.join(OUT, name)
    if not os.path.exists(path):
        sys.exit("catalogue missing; run: python tools/pzcatalog.py build")
    return json.load(open(path))


KEEP = ("container", "ContainerCapacity", "CustomName", "GroupName", "Facing",
        "bed", "BedType", "lightswitch", "IsTable", "IsLow", "Surface",
        "wall", "WallN", "WallW", "solidfloor", "exterior", "waterAmount")


def sprites(mode, needle, limit=30):
    tiles = load("tiles.json")["tiles"]
    hits = []
    for n, p in tiles.items():
        if mode == "name" and needle in n:
            hits.append((n, p))
        elif mode != "name" and p.get(mode) == needle:
            hits.append((n, p))
    print(f"{len(hits)} match")
    for n, p in sorted(hits)[:limit]:
        print(" ", n, "|", {k: v for k, v in p.items() if k in KEEP})


if __name__ == "__main__":
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    cmd = sys.argv[1]
    if cmd == "build":
        build()
    elif cmd == "sprites":
        sprites(sys.argv[2], sys.argv[3],
                int(sys.argv[4]) if len(sys.argv) > 4 else 30)
    elif cmd == "items":
        names = load("items.json")["Base"]
        pat = re.compile(sys.argv[2], re.I)
        hits = [n for n in names if pat.search(n)]
        print(f"{len(hits)} match")
        print(" ".join(hits[:int(sys.argv[3]) if len(sys.argv) > 3 else 60]))
    elif cmd == "check":
        names = set(load("items.json")["Base"])
        missing = [w for w in sys.argv[2].split(",")
                   if w.replace("Base.", "") not in names]
        print("MISSING:", missing if missing else "none")
    else:
        sys.exit(__doc__)
