"""The Adirondack crew's talk, compiled: design/crew/*.txt -> Lua tree + text.

    python tools/gen_crew_talk.py            # check and write
    python tools/gen_crew_talk.py --check    # check only
    python tools/gen_crew_talk.py --stats    # how long every scene runs
    python tools/gen_crew_talk.py --check --stats sickbay.txt   # one file

Reads every design/crew/*.txt (the format is CREW.md section 4) and writes

  TrekShuttle/42/media/lua/shared/TREK/TREK_CrewTalk.lua     the tree the server walks
  TrekShuttle/42/media/lua/shared/Translate/EN/Print_Text.json   the words, as
                                        Print_Text_TREK_CREW_* keys, merged with
                                        the comms channel's (gen_comms.py)

**A broken tree is refused, never written** (CREW.md 4.4): a player standing
in sickbay waiting for a line that points at a node that is not there would
simply see two people stop talking, and nothing would ever say why.

Keys are `Print_Text_TREK_CREW_<scene>_<node>_<line>_<variant>` and
`Print_Text_TREK_CREW_BARK_<category>_<n>_<variant>`. A line's key is its
position, so rewording a line keeps its key and moving one renumbers it --
which is fine: nothing but this tree ever names them.
"""
import glob
import json
import os
import random
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "design", "crew")
LUA = os.path.join(ROOT, "TrekShuttle", "42", "media", "lua", "shared", "TREK", "TREK_CrewTalk.lua")
TEXT = os.path.join(ROOT, "TrekShuttle", "42", "media", "lua", "shared", "Translate", "EN", "Print_Text.json")
PREFIX = "Print_Text_TREK_CREW_"

PLACES = {"bridge", "readyroom", "lounge", "galley", "quarters", "habitat", "transporter", "hydroponics",
          "sickbay", "engineering", "corridor", "lift", "any"}
REQUIREMENTS = {"any", "command", "operations", "sciences", "medical", "engineer", "security", "helm"}
BARKS = {"hello", "outfit", "thanks", "idle", "arrive", "leave"}
SPECIES = {"klingon", "vulcan", "betazoid", "bajoran", "trill", "andorian", "talaxian", "exborg"}
TAGS = {"lore", "rare"}
MAX_LINE = 80
NAME = re.compile(r"^[a-z][a-z0-9_]*$")

# Pacing, the same numbers the server uses (CREW.md 5): seconds per line.
BEAT_SECS = 3.0


def line_secs(text):
    return 2.5 + 0.06 * len(text)


class Refused(Exception):
    pass


def parse(path):
    """One file -> (scenes, barks). Scenes are dicts; barks are
    (category, where, variants) tuples."""
    scenes, barks = [], []
    cur = None          # the scene or bark block being read
    node = None
    last_line = None
    fname = os.path.basename(path)

    def err(n, msg):
        raise Refused("%s:%d: %s" % (fname, n, msg))

    for n, raw in enumerate(open(path, encoding="utf-8"), start=1):
        line = raw.rstrip("\n").rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("scene:"):
            cur = dict(kind="scene", id=stripped[6:].strip(), where=None, cast=[], weight=1,
                       tags=set(), nodes={}, order=[], file=fname, line=n)
            if not NAME.match(cur["id"]):
                err(n, "scene id %r must be lowercase letters, digits, _" % cur["id"])
            scenes.append(cur)
            node, last_line = None, None
            continue
        if stripped.startswith("bark:"):
            cat = stripped[5:].strip()
            cur = dict(kind="bark", category=cat, where=None, lines=[], file=fname, line=n)
            ok = cat in BARKS or (cat.startswith("species:") and cat[8:] in SPECIES)
            if not ok:
                err(n, "unknown bark category %r" % cat)
            barks.append(cur)
            node, last_line = None, None
            continue
        if cur is None:
            err(n, "text before any scene: or bark:")

        if node is None and re.match(r"^(where|cast|weight|tags):", stripped):
            key, _, val = stripped.partition(":")
            val = val.strip()
            if key == "where":
                places = [p.strip() for p in val.split(",") if p.strip()]
                for p in places:
                    if p not in PLACES:
                        err(n, "unknown place %r" % p)
                cur["where"] = places
            elif key == "cast" and cur["kind"] == "scene":
                for part in val.split(","):
                    name, _, req = part.strip().partition("=")
                    name, req = name.strip(), (req.strip() or "any")
                    if not NAME.match(name):
                        err(n, "bad role name %r" % name)
                    if req not in REQUIREMENTS:
                        err(n, "unknown cast requirement %r" % req)
                    if any(r["name"] == name for r in cur["cast"]):
                        err(n, "role %r twice" % name)
                    cur["cast"].append(dict(name=name, req=req))
            elif key == "weight" and cur["kind"] == "scene":
                try:
                    cur["weight"] = float(val)
                except ValueError:
                    err(n, "weight must be a number")
            elif key == "tags" and cur["kind"] == "scene":
                for t in [t.strip() for t in val.split(",") if t.strip()]:
                    if t not in TAGS:
                        err(n, "unknown tag %r" % t)
                    cur["tags"].add(t)
            else:
                err(n, "%s: is not allowed here" % key)
            continue

        if cur["kind"] == "bark":
            if stripped.startswith("-"):
                last_line = [v.strip() for v in stripped[1:].split("|") if v.strip()]
                cur["lines"].append(last_line)
            elif stripped.startswith("|") and last_line is not None:
                last_line.extend(v.strip() for v in stripped[1:].split("|") if v.strip())
            else:
                err(n, "a bark line starts with '-'")
            continue

        # scene body
        if stripped.startswith("="):
            name = stripped[1:].strip()
            if not NAME.match(name):
                err(n, "bad node name %r" % name)
            if name in cur["nodes"]:
                err(n, "node %r twice in scene %s" % (name, cur["id"]))
            node = dict(name=name, lines=[], next=None, line=n)
            cur["nodes"][name] = node
            cur["order"].append(name)
            last_line = None
            continue
        if node is None:
            err(n, "a line before the first '= node'")
        if stripped == "...":
            node["lines"].append(dict(beat=True))
            last_line = None
            continue
        if stripped.startswith("->"):
            if node["next"] is not None:
                err(n, "two '->' in node %s" % node["name"])
            body = stripped[2:].strip()
            if body == "end":
                node["next"] = []
            else:
                nxt = []
                for part in body.split(","):
                    bits = part.split()
                    if not bits:
                        err(n, "empty target in '->'")
                    tgt = bits[0]
                    w = 1.0
                    if len(bits) > 1:
                        try:
                            w = float(bits[1])
                        except ValueError:
                            err(n, "weight %r is not a number" % bits[1])
                    nxt.append((tgt, w))
                node["next"] = nxt
            last_line = None
            continue
        if stripped.startswith("|") and last_line is not None:
            last_line["variants"].extend(v.strip() for v in stripped[1:].split("|") if v.strip())
            continue
        m = re.match(r"^([a-z][a-z0-9_]*)\s*:\s*(.+)$", stripped)
        if not m:
            err(n, "not a line, a '->', a '= node' or '...': %r" % stripped)
        last_line = dict(who=m.group(1), variants=[v.strip() for v in m.group(2).split("|") if v.strip()],
                         line=n)
        node["lines"].append(last_line)
    return scenes, barks


def validate(scenes, barks):
    seen = {}
    for s in scenes:
        where = "%s:%d scene %s" % (s["file"], s["line"], s["id"])
        if s["id"] in seen:
            raise Refused("%s: id already used in %s" % (where, seen[s["id"]]))
        seen[s["id"]] = s["file"]
        if not s["where"]:
            raise Refused("%s: no where:" % where)
        if not 2 <= len(s["cast"]) <= 4:
            raise Refused("%s: a scene has two to four roles" % where)
        if "start" not in s["nodes"]:
            raise Refused("%s: no '= start'" % where)
        roles = {r["name"] for r in s["cast"]}
        for name, node in s["nodes"].items():
            spoken = [ln for ln in node["lines"] if not ln.get("beat")]
            if not spoken:
                raise Refused("%s node %s: nobody says anything" % (where, name))
            for ln in spoken:
                if ln["who"] not in roles:
                    raise Refused("%s node %s: %r is not in the cast" % (where, name, ln["who"]))
                for v in ln["variants"]:
                    if len(v) > MAX_LINE:
                        raise Refused("%s node %s: line over %d characters (%d): %s"
                                      % (where, name, MAX_LINE, len(v), v))
                    for ph in re.findall(r"\{([^}]*)\}", v):
                        if ph not in roles:
                            raise Refused("%s node %s: {%s} is not a role" % (where, name, ph))
            for tgt, _ in node["next"] or []:
                if tgt not in s["nodes"]:
                    raise Refused("%s node %s: '-> %s' goes nowhere" % (where, name, tgt))
        # reachable from start
        reach, stack = set(), ["start"]
        while stack:
            k = stack.pop()
            if k in reach:
                continue
            reach.add(k)
            stack.extend(t for t, _ in s["nodes"][k]["next"] or [])
        lost = [k for k in s["order"] if k not in reach]
        if lost:
            raise Refused("%s: nothing reaches %s" % (where, ", ".join(lost)))
        # every node can reach an end
        ends = {k for k, nd in s["nodes"].items() if not nd["next"]}
        can = set(ends)
        changed = True
        while changed:
            changed = False
            for k, nd in s["nodes"].items():
                if k not in can and any(t in can for t, _ in nd["next"] or []):
                    can.add(k)
                    changed = True
        trapped = [k for k in s["order"] if k not in can]
        if trapped:
            raise Refused("%s: %s can never reach an end" % (where, ", ".join(trapped)))
    for b in barks:
        where = "%s:%d bark %s" % (b["file"], b["line"], b["category"])
        if not b["where"]:
            raise Refused("%s: no where:" % where)
        if not b["lines"]:
            raise Refused("%s: no lines" % where)
        for variants in b["lines"]:
            for v in variants:
                if len(v) > MAX_LINE:
                    raise Refused("%s: line over %d characters: %s" % (where, MAX_LINE, v))
                if "{" in v:
                    raise Refused("%s: a bark has nobody to name: %s" % (where, v))


def durations(scene, runs=400, seed=7):
    """(shortest, typical, longest) seconds, by random walks the way the
    server picks: weighted, with every variant at its own length."""
    rnd = random.Random(seed)
    out = []
    for _ in range(runs):
        k, t, steps = "start", 0.0, 0
        while k and steps < 200:
            nd = scene["nodes"][k]
            for ln in nd["lines"]:
                t += BEAT_SECS if ln.get("beat") else line_secs(rnd.choice(ln["variants"]))
            nxt = nd["next"] or []
            if not nxt:
                break
            total = sum(w for _, w in nxt)
            r = rnd.uniform(0, total)
            for tgt, w in nxt:
                r -= w
                if r <= 0:
                    k = tgt
                    break
            steps += 1
        out.append(t)
    out.sort()
    return out[0], out[len(out) // 2], out[-1]


def lua_str(s):
    return json.dumps(s, ensure_ascii=True)


def build(scenes, barks):
    text = {}
    lua = ["-- GENERATED by tools/gen_crew_talk.py from design/crew/*.txt -- do not edit.",
           "-- The Adirondack crew's talk (CREW.md 4). Every line is a translation key",
           "-- base in Print_Text.json; variant v of it is base .. \"_\" .. v.",
           "-- A line is { who, key, variants } -- who indexes the cast -- or { 0 } for a beat.",
           "",
           "TREK_CrewTalk = {}",
           "local T = TREK_CrewTalk",
           "",
           "T.scenes = {"]
    for s in scenes:
        roles = [r["name"] for r in s["cast"]]
        lua.append("    {")
        lua.append("        id = %s, weight = %s, lore = %s, rare = %s," % (
            lua_str(s["id"]), repr(s["weight"]), "true" if "lore" in s["tags"] else "false",
            "true" if "rare" in s["tags"] else "false"))
        lua.append("        where = { %s }," % ", ".join("%s = true" % p for p in s["where"]))
        lua.append("        cast = { %s }," % ", ".join(
            "{ name = %s, req = %s }" % (lua_str(r["name"]), lua_str(r["req"])) for r in s["cast"]))
        lua.append("        nodes = {")
        for name in s["order"]:
            nd = s["nodes"][name]
            lines = []
            i = 0
            for ln in nd["lines"]:
                if ln.get("beat"):
                    lines.append("{ 0 }")
                    continue
                i += 1
                base = "%s%s_%s_%d" % (PREFIX, s["id"], name, i)
                for v, t in enumerate(ln["variants"], start=1):
                    text["%s_%d" % (base, v)] = t
                lines.append("{ %d, %s, %d }" % (roles.index(ln["who"]) + 1, lua_str(base), len(ln["variants"])))
            nxt = ", ".join("{ %s, %s }" % (lua_str(t), repr(w)) for t, w in (nd["next"] or []))
            lua.append("            [%s] = { lines = { %s }, next = { %s } }," % (
                lua_str(name), ", ".join(lines), nxt))
        lua.append("        },")
        lua.append("    },")
    lua.append("}")
    lua.append("")
    lua.append("-- category -> list of { where = {...}, key = base, n = variants }")
    lua.append("T.barks = {")
    cats = {}
    for b in barks:
        cats.setdefault(b["category"], []).append(b)
    for cat in sorted(cats):
        lua.append("    [%s] = {" % lua_str(cat))
        n = 0
        safe = cat.replace(":", "_")
        for b in cats[cat]:
            for variants in b["lines"]:
                n += 1
                base = "%sBARK_%s_%d" % (PREFIX, safe, n)
                for v, t in enumerate(variants, start=1):
                    text["%s_%d" % (base, v)] = t
                lua.append("        { where = { %s }, key = %s, n = %d }," % (
                    ", ".join("%s = true" % p for p in b["where"]), lua_str(base), len(variants)))
        lua.append("    },")
    lua.append("}")
    lua.append("")
    lua.append("return T")
    return "\n".join(lua) + "\n", text


def load(only=None):
    scenes, barks = [], []
    files = sorted(glob.glob(os.path.join(SRC, "*.txt")))
    if only:
        files = [f for f in files if os.path.basename(f) in only]
    for path in files:
        s, b = parse(path)
        scenes += s
        barks += b
    validate(scenes, barks)
    return files, scenes, barks


def write(lua, text):
    with open(LUA, "w", encoding="utf-8", newline="\n") as f:
        f.write(lua)
    merged = {}
    if os.path.exists(TEXT):
        merged = {k: v for k, v in json.load(open(TEXT, encoding="utf-8")).items()
                  if not k.startswith(PREFIX)}
    merged.update(text)
    with open(TEXT, "w", encoding="utf-8", newline="\n") as f:
        f.write(json.dumps(merged, indent=4, ensure_ascii=True, sort_keys=True) + "\n")


def main():
    only = [a for a in sys.argv[1:] if not a.startswith("--")]
    if only and "--check" not in sys.argv:
        print("naming files is for --check; a write always compiles every file")
        return 1
    try:
        files, scenes, barks = load(only)
    except Refused as exc:
        print("REFUSED -- nothing was written:\n  %s" % exc)
        return 2
    lua, text = build(scenes, barks)
    lines = sum(1 for s in scenes for nd in s["nodes"].values() for ln in nd["lines"] if not ln.get("beat"))
    variants = sum(len(ln["variants"]) for s in scenes for nd in s["nodes"].values()
                   for ln in nd["lines"] if not ln.get("beat"))
    bark_lines = sum(len(b["lines"]) for b in barks)
    print("%d file(s): %d scenes, %d nodes, %d lines (%d with variants), %d barks, %d keys"
          % (len(files), len(scenes), sum(len(s["nodes"]) for s in scenes), lines, variants,
             bark_lines, len(text)))
    if "--stats" in sys.argv:
        for s in scenes:
            lo, mid, hi = durations(s)
            print("  %-28s %-24s %2d nodes  %3.0fs / %3.0fs / %3.0fs" % (
                s["id"], ",".join(s["where"]), len(s["nodes"]), lo, mid, hi))
    by_place = {}
    for s in scenes:
        for p in s["where"]:
            by_place[p] = by_place.get(p, 0) + 1
    print("  by place: " + ", ".join("%s %d" % kv for kv in sorted(by_place.items())))
    if "--check" not in sys.argv:
        write(lua, text)
        print("wrote %s and %d keys into Print_Text.json" % (os.path.relpath(LUA, ROOT), len(text)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
