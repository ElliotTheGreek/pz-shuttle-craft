#!/usr/bin/env python3
"""The Adirondack channel: writes the dialogue tree and the text it points at.

    python tools/gen_comms.py TrekShuttle/42

COMMS.md section 3 is the design. This is `gen_tapes.py`'s pattern again, for
the same reason: **two files have to agree, so one program writes both.**

  media/lua/shared/TREK/TREK_CommsTree.lua         the tree the server walks
  media/lua/shared/Translate/EN/Print_Text.json    every line, option and name

Every key is derived from the thread, the node and the index of the line or
option, so a duplicate key is not expressible rather than tested for.

**Why Print_Text.** Build 42's Translator routes a key to a category by its
prefix (`Translator.getTextInternal`: "IGUI_" to IG_UI, "RM_" to Recorded
Media, "Print_Text_" to Print_Text ...), and the list of categories is fixed
(`Translator.BY_NAME`) -- a mod cannot add a "Comms" file. Print_Text is the
category vanilla keeps printed text in, text meant to be read, and this mod
shipped no Print_Text.json before the channel: so this generator owns that file
outright, the way gen_tapes.py owns Recorded_Media.json. One writer per file.

The validation below is **generator-time**: a tree that fails it is not
written. Every one of these was a way for a call to go silent in a game with
nothing in any log:

  * every goto resolves to a node in the same thread;
  * every node is reachable from one of its thread's entries;
  * every node can reach an end -- no conversation loops for ever;
  * a flag that anything requires is set by something (or by the code);
  * a dynamic condition is one the server knows how to answer;
  * a node with a timeout has a silence branch;
  * a node with options always has at least one the holder can take;
  * a route's last branch is unconditional;
  * no line is longer than LINE_MAX, no option longer than OPTION_MAX.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

PREFIX = "Print_Text_TREK_COMM_"

# COMMS.md 3: a line is a shot. The tapes' own upper bound, because it is the
# same reader in the same chair.
LINE_MAX = 70
# An option is a button on a Steam Deck. PADD.md 12.5.
OPTION_MAX = 60

# Colour is the speaker (COMMS.md 3). The first two are the tapes' own, so a
# player who has watched the logs already knows whose voice amber is.
VOICES = {
    # Title cards and the channel's own status lines.
    "card":    ("Channel", (1.00, 1.00, 1.00)),
    # Lt. Lucy Shepard -- the pilot's amber, off every log on the shelf.
    "shepard": ("Shepard", (1.00, 0.75, 0.00)),
    # The Doctor -- the tapes' green for the one talking back.
    "emh":     ("The Doctor", (0.00, 0.69, 0.31)),
    # The Section 31 officer. The camera's violet on the tapes: somebody the
    # room is watching.
    "officer": ("Cmdr. Okafor", (0.62, 0.45, 0.85)),
    # Anybody else aboard the Adirondack. One colour for all of them,
    # told apart by name in the text (COMMS.md 8: four is soup).
    "crew":    ("Adirondack", (0.00, 0.69, 0.94)),
    # The player's own half. Never a character's colour.
    "you":     ("You", (0.80, 0.80, 0.80)),
}

# Flags the Lua sets on its own, from things that happen outside a call.
# TREK_Comms.lua names exactly these; tests/test_comms.py checks both lists
# agree, so a flag the story waits on that no code ever raises fails here.
SYSTEM_FLAGS = {
    "thanksDue",     # an ensign was rescued since the last thank-you
    "lostDue",       # an ensign was lost since the last word about it
    "clueSeen",      # a probe has reported a clue site
    "commissioned",  # day zero has happened
}

# Conditions answered by the server at the moment they are asked, never
# stored. The patterns are exactly what TREK_Comms.check understands.
DYNAMIC = [
    re.compile(r"^emh$"),                   # the Doctor is up
    re.compile(r"^rescued>=\d+$"),          # ensigns brought up, ever
    re.compile(r"^lost>=\d+$"),             # ensigns whose signal stopped
    re.compile(r"^day>=\d+$"),              # days since day zero
    re.compile(r"^watched:TREK_\w+$"),      # the holder has seen all of a tape
    re.compile(r"^carrying:[1-6]$"),        # the holder has fragment N on them
    re.compile(r"^carrying$"),              # ... any unconverted fragment
    re.compile(r"^converted:[1-6]$"),       # fragment N is on the shelf
    re.compile(r"^converted>=\d$"),         # this many are
]


def is_dynamic(cond):
    return any(p.match(cond) for p in DYNAMIC)


from comms_vocab import say, opt, branch, node, thread  # noqa: E402,F401


# ---------------------------------------------------------------------------
# The threads
# ---------------------------------------------------------------------------
# Every thread is in content/comms/, one JSON file each (content/README.md).
import content  # noqa: E402

THREADS = content.load_threads()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
class Refused(Exception):
    pass


def validate(threads, tape_ids):
    problems = []

    def bad(msg):
        problems.append(msg)

    seen_threads = set()
    set_somewhere = set(SYSTEM_FLAGS)
    required = []   # (where, cond)

    for t in threads:
        tid = t["id"]
        if not re.match(r"^[A-Z][A-Z0-9]*$", tid):
            bad(f"thread id {tid!r} must be upper case letters and digits")
        if tid in seen_threads:
            bad(f"thread {tid} is declared twice")
        seen_threads.add(tid)
        if t["kind"] not in ("incoming", "hail"):
            bad(f"{tid}: kind {t['kind']!r} is neither incoming nor hail")
        if t["kind"] == "incoming" and t["day"] is None and t["after"] is None \
                and not t["requires"]:
            bad(f"{tid}: an incoming thread with no day, no after and no "
                f"requires would ring on the first minute of every world")
        if t["repeatable"] and t["kind"] == "incoming" and not t["requires"]:
            bad(f"{tid}: a repeatable incoming thread must wait on a flag, or "
                f"it rings for ever")
        if t["repeatable"] and t["kind"] == "hail" and not t["cooldown"]:
            bad(f"{tid}: a repeatable hail needs a cooldown, or she picks up "
                f"every time and 'nobody answers' never happens")
        for c in t["requires"] + t["forbids"]:
            required.append((f"{tid} trigger", c))

        ids = {}
        for n in t["nodes"]:
            nid = n["id"]
            if not re.match(r"^[0-9A-Z]+$", nid):
                bad(f"{tid}_{nid}: node ids are digits and capitals")
            if nid in ids:
                bad(f"{tid}_{nid} is declared twice")
            ids[nid] = n
        for e in t["entries"]:
            if e not in ids:
                bad(f"{tid}: entry {e} is not a node")

        for n in t["nodes"]:
            where = f"{tid}_{n['id']}"
            for f in n["sets"]:
                set_somewhere.add(f)
            for o in n["options"]:
                set_somewhere.update(o["sets"])
            if n["route"] is not None:
                if n["lines"] or n["options"]:
                    bad(f"{where}: a route node shows nothing and offers "
                        f"nothing; it only chooses")
                if not n["route"]:
                    bad(f"{where}: a route with no arms")
                for i, arm in enumerate(n["route"]):
                    if arm["go"] not in ids:
                        bad(f"{where}: route arm {i + 1} goes to {arm['go']}, "
                            f"which is not a node of {tid}")
                    for c in arm["requires"] + arm["forbids"]:
                        required.append((where, c))
                last = n["route"][-1] if n["route"] else None
                if last and (last["requires"] or last["forbids"]):
                    bad(f"{where}: a route's last arm must be unconditional, "
                        f"or a call can arrive at a node with nowhere to go")
                continue
            if not n["lines"]:
                bad(f"{where}: a node with nothing said")
            for i, ln in enumerate(n["lines"], 1):
                if ln["voice"] not in VOICES:
                    bad(f"{where} line {i}: voice {ln['voice']!r} is not declared")
                if len(ln["text"]) > LINE_MAX:
                    bad(f"{where} line {i} is {len(ln['text'])} characters, "
                        f"over {LINE_MAX}: {ln['text']!r}")
                if "--" in ln["text"] and ln["voice"] != "card":
                    pass
            open_option = False
            for i, o in enumerate(n["options"], 1):
                if o["go"] not in ids:
                    bad(f"{where} option {i} goes to {o['go']}, which is not a "
                        f"node of {tid}")
                if len(o["text"]) > OPTION_MAX:
                    bad(f"{where} option {i} is {len(o['text'])} characters, "
                        f"over {OPTION_MAX}: {o['text']!r}")
                for c in o["requires"] + o["forbids"]:
                    required.append((where, c))
                if not o["requires"] and not o["forbids"]:
                    open_option = True
            if n["options"] and not open_option and not n["silence"]:
                bad(f"{where}: every option is conditional and there is no "
                    f"silence branch, so a holder can arrive with nothing to "
                    f"press")
            if n["timeout"] is not None and not n["silence"]:
                bad(f"{where}: a timed node with no silence branch")
            if n["silence"] and n["timeout"] is None:
                bad(f"{where}: a silence branch with no timeout is never taken")
            if n["silence"] and n["silence"] not in ids:
                bad(f"{where}: silence goes to {n['silence']}, not a node of {tid}")
            if n["silence"] and not n["options"]:
                bad(f"{where}: a silence branch on a node with nothing to answer")
            if n["convert"] and not (1 <= int(n["convert"]) <= 6):
                bad(f"{where}: converts fragment {n['convert']}; there are six")
            for tape in n["issue"]:
                if tape not in tape_ids:
                    bad(f"{where}: issues {tape}, which gen_tapes.py does not make")

        # Reachability from the entries.
        def exits(n):
            out = [o["go"] for o in n["options"]]
            if n["silence"]:
                out.append(n["silence"])
            if n["route"]:
                out += [a["go"] for a in n["route"]]
            return out

        reached, stack = set(), list(t["entries"])
        while stack:
            cur = stack.pop()
            if cur in reached or cur not in ids:
                continue
            reached.add(cur)
            stack.extend(exits(ids[cur]))
        for nid in ids:
            if nid not in reached:
                bad(f"{tid}_{nid} cannot be reached from any entry of {tid}")

        # Every node can reach an end.
        ends = {nid for nid, n in ids.items()
                if not n["options"] and not n["route"]}
        if not ends:
            bad(f"{tid}: no node ends the call")
        can_end = set(ends)
        changed = True
        while changed:
            changed = False
            for nid, n in ids.items():
                if nid not in can_end and any(x in can_end for x in exits(n)):
                    can_end.add(nid)
                    changed = True
        for nid in ids:
            if nid not in can_end:
                bad(f"{tid}_{nid} can never reach the end of the call")

    for t in threads:
        if t["after"] is not None:
            other = t["after"][0]
            if other not in seen_threads:
                bad(f"{t['id']}: after {other}, which is not a thread")

    for where, cond in required:
        if is_dynamic(cond):
            m = re.match(r"^watched:(TREK_\w+)$", cond)
            if m and m.group(1) not in tape_ids:
                bad(f"{where}: waits on watching {m.group(1)}, which is not a tape")
            continue
        if cond not in set_somewhere:
            bad(f"{where}: requires the flag {cond!r}, which nothing sets")

    if problems:
        raise Refused("\n".join(problems))


# ---------------------------------------------------------------------------
# Keys and output
# ---------------------------------------------------------------------------
def voice_key(v):
    return f"{PREFIX}Voice_{v}"


def title_key(tid):
    return f"{PREFIX}{tid}_Title"


def line_key(tid, nid, i):
    return f"{PREFIX}{tid}_{nid}_L{i}"


def option_key(tid, nid, i):
    return f"{PREFIX}{tid}_{nid}_O{i}"


def build(threads):
    text = {}
    for v, (name, _) in VOICES.items():
        text[voice_key(v)] = name
    for t in threads:
        text[title_key(t["id"])] = t["title"]
        for n in t["nodes"]:
            for i, ln in enumerate(n["lines"], 1):
                text[line_key(t["id"], n["id"], i)] = ln["text"]
            for i, o in enumerate(n["options"], 1):
                text[option_key(t["id"], n["id"], i)] = o["text"]
    return text


def lua_str(s):
    return json.dumps(s)


def lua_list(items):
    return "{ " + ", ".join(lua_str(x) for x in items) + " }" if items else "{}"


def write_lua(path, threads):
    out = []
    w = out.append
    w("-- GENERATED by tools/gen_comms.py -- do not edit by hand.")
    w("--")
    w("-- The Adirondack channel's dialogue tree (COMMS.md 3). Every string")
    w("-- here is a translation key into Translate/EN/Print_Text.json, and")
    w("-- both files come out of the generator together. The server walks")
    w("-- this; the PADD renders history from it, so a line fixed here is")
    w("-- fixed in every player's transcript (PADD.md 12.2).")
    w("")
    w("TREK_CommsTree = {}")
    w("local T = TREK_CommsTree")
    w("")
    w("T.voices = {")
    for v, (_, (r, g, b)) in VOICES.items():
        w(f'    {v} = {{ name = {lua_str(voice_key(v))}, r = {r:.2f}, g = {g:.2f}, b = {b:.2f} }},')
    w("}")
    w("")
    w("-- The order threads are considered in, which is their priority.")
    w("T.order = { " + ", ".join(lua_str(t["id"]) for t in threads) + " }")
    w("")
    w("T.systemFlags = " + lua_list(sorted(SYSTEM_FLAGS)))
    w("")
    w("T.threads = {")
    for t in threads:
        tid = t["id"]
        fields = [f"title = {lua_str(title_key(tid))}",
                  f"kind = {lua_str(t['kind'])}",
                  "entries = " + lua_list(f"{tid}_{e}" for e in t["entries"]),
                  "requires = " + lua_list(t["requires"]),
                  "forbids = " + lua_list(t["forbids"]),
                  f"retry = {'true' if t['retry'] else 'false'}",
                  f"repeatable = {'true' if t['repeatable'] else 'false'}"]
        if t["day"] is not None:
            fields.append(f"day = {int(t['day'])}")
        if t["after"] is not None:
            fields.append(f"after = {lua_str(t['after'][0])}, "
                          f"afterHours = {int(t['after'][1])}")
        if t["cooldown"] is not None:
            fields.append(f"cooldown = {int(t['cooldown'])}")
        w(f"    {tid} = {{ " + ", ".join(fields) + " },")
    w("}")
    w("")
    w("T.nodes = {")
    for t in threads:
        tid = t["id"]
        for n in t["nodes"]:
            nid = f"{tid}_{n['id']}"
            parts = [f"thread = {lua_str(tid)}"]
            if n["lines"]:
                ls = ", ".join(
                    f"{{ v = {lua_str(ln['voice'])}, k = {lua_str(line_key(tid, n['id'], i))} }}"
                    for i, ln in enumerate(n["lines"], 1))
                parts.append(f"lines = {{ {ls} }}")
            if n["options"]:
                os_ = []
                for i, o in enumerate(n["options"], 1):
                    f = [f"k = {lua_str(option_key(tid, n['id'], i))}",
                         f"go = {lua_str(tid + '_' + o['go'])}"]
                    if o["requires"]:
                        f.append("requires = " + lua_list(o["requires"]))
                    if o["forbids"]:
                        f.append("forbids = " + lua_list(o["forbids"]))
                    if o["sets"]:
                        f.append("sets = " + lua_list(o["sets"]))
                    if o["clears"]:
                        f.append("clears = " + lua_list(o["clears"]))
                    os_.append("{ " + ", ".join(f) + " }")
                parts.append("options = {\n        " + ",\n        ".join(os_) + ",\n    }")
            if n["route"]:
                arms = []
                for a in n["route"]:
                    f = [f"go = {lua_str(tid + '_' + a['go'])}"]
                    if a["requires"]:
                        f.append("requires = " + lua_list(a["requires"]))
                    if a["forbids"]:
                        f.append("forbids = " + lua_list(a["forbids"]))
                    arms.append("{ " + ", ".join(f) + " }")
                parts.append("route = { " + ", ".join(arms) + " }")
            if n["timeout"] is not None:
                parts.append(f"timeout = {int(n['timeout'])}")
                parts.append(f"silence = {lua_str(tid + '_' + n['silence'])}")
            if n["sets"]:
                parts.append("sets = " + lua_list(n["sets"]))
            if n["clears"]:
                parts.append("clears = " + lua_list(n["clears"]))
            if n["issue"]:
                parts.append("issue = " + lua_list(n["issue"]))
            if n["convert"]:
                parts.append(f"convert = {int(n['convert'])}")
            if not n["options"] and not n["route"]:
                parts.append("terminal = true")
            w(f"    [{lua_str(nid)}] = {{ " + ", ".join(parts) + " },")
    w("}")
    w("")
    w("return T")
    w("")
    path.write_text("\n".join(out), encoding="utf-8")


def write_text(path, text):
    body = json.dumps(text, indent=4, ensure_ascii=True, sort_keys=True)
    path.write_text(body + "\n", encoding="utf-8")


def tape_ids():
    """Every tape gen_tapes.py makes, so a node that issues one or waits on
    one being watched names something that exists."""
    import gen_tapes
    return {t["id"] for t in gen_tapes.TAPES}


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    base = Path(sys.argv[1])
    if not base.is_absolute():
        base = ROOT / base
    try:
        validate(THREADS, tape_ids())
    except Refused as exc:
        print("REFUSED -- the tree was not written:")
        print(exc)
        return 2
    text = build(THREADS)
    lua = base / "media/lua/shared/TREK/TREK_CommsTree.lua"
    json_path = base / "media/lua/shared/Translate/EN/Print_Text.json"
    write_lua(lua, THREADS)
    write_text(json_path, text)
    nodes = sum(len(t["nodes"]) for t in THREADS)
    lines = sum(len(n["lines"]) for t in THREADS for n in t["nodes"])
    print(f"{len(THREADS)} thread(s), {nodes} nodes, {lines} lines, {len(text)} keys")
    for p in (lua, json_path):
        try:
            print("wrote %s" % p.relative_to(ROOT))
        except ValueError:
            print("wrote %s" % p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
