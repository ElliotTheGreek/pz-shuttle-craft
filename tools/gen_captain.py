#!/usr/bin/env python3
"""Captain Titus: writes her conversation tree and the text it points at.

    python tools/gen_captain.py TrekShuttle/42

CAPTAIN.md section 5 is the design. The pattern is gen_comms.py's, for the same
reason: **two files have to agree, so one program writes both.**

  media/lua/shared/TREK/TREK_CaptainTree.lua        the tree the server walks
  media/lua/shared/Translate/EN/Print_Text.json     her lines, under TREK_CAPT_

Print_Text.json has three writers now, each owning one prefix: the channel
(TREK_COMM_), the crew's talk (TREK_CREW_) and this (TREK_CAPT_). Each replaces
only its own keys.

**The shape.** A hub and spokes. `content/captain/HUB.json` is how a
conversation opens, comes back to the topics and ends; every other file is one
topic on her list. A node's option goes to a node of the same file, to `HUB`
(back to the topics) or to `BYE` (goodbye). A topic node always has a way back
to the topics in the panel, whatever its options say.

**Tiers.** Each topic declares its tiers, each with the conditions that open it,
and every topic node belongs to one. The server never shows a node whose tier
is shut, and a topic is marked NEW on the hub while it has an open tier this
player has not heard. That is the recap (CAPTAIN.md 5.3).

**Conditions** are the channel's own words (gen_comms.DYNAMIC, the flags its
threads set, its system flags) plus the few only a conversation in person can
ask (CAPTAIN_DYNAMIC below), and `me:<mark>` for what this player has told her.

The validation is generator-time; a tree that fails it is not written:

  * every go resolves, every node is reachable, every route ends unconditionally;
  * every topic node has a tier the topic declares;
  * every condition is one the server can answer, and every mark is set somewhere;
  * a line or option that names the Changeling is in a tier that waits on
    `truth`, and one that names Tucker Gold in a tier that waits on `goldDone`
    -- the one mistake in this feature that spoils the story (CAPTAIN.md 2);
  * no line over LINE_MAX, no option over OPTION_MAX, no hub title over
    TITLE_MAX, and options and titles in ASCII -- a button upper-cases its
    label a byte at a time (DEV_GUIDE.md, *A string that gets upper-cased*);
  * tokens: %1 (how she addresses you) and %2 (your rank) in her lines, %3
    (your name) in your own options only.
"""
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import gen_comms  # noqa: E402
import content  # noqa: E402

CAPTAIN_DIR = ROOT / "content" / "captain"
PREFIX = "Print_Text_TREK_CAPT_"

LINE_MAX = gen_comms.LINE_MAX
OPTION_MAX = gen_comms.OPTION_MAX
# A topic's button on the hub is half the panel wide.
TITLE_MAX = 32

VOICES = {
    # Captain Imogen Titus. Command gold: the one colour no other voice in the
    # mod uses, so a line of hers read anywhere is hers.
    "captain": ("Captain Titus", (0.96, 0.80, 0.42)),
    # What she does rather than says: a look, a pause, a padd put down.
    "note":    ("", (0.62, 0.62, 0.68)),
    # The player's own half, as the channel draws it.
    "you":     ("You", (0.80, 0.80, 0.80)),
}

# Asked of the person in front of her, at the moment of asking, on the server.
# TREK_Captain.check answers exactly these; tests/test_comms.py holds the two
# lists together.
CAPTAIN_DYNAMIC = [
    re.compile(r"^truth$"),               # she will say what her people think (sandbox)
    re.compile(r"^promotionDue$"),        # rescues have earned a rank not yet given
    re.compile(r"^ranked$"),              # this player holds any rank
    re.compile(r"^uniform$"),             # wearing a Starfleet uniform
    re.compile(r"^shipDark$"),            # the shuttle is dark or never commissioned
    re.compile(r"^distressLive$"),        # a distress call or a rescue is live
    re.compile(r"^probed$"),              # the shuttle has launched a probe
    re.compile(r"^myRescues>=\d+$"),      # rescues credited to this player
]

MARK = re.compile(r"^me:([a-z][A-Za-z]*)$")

# Words that give the story away, and the gate each needs (CAPTAIN.md 2).
SPOILERS = {
    "truth": ["Changeling", "Great Link", "the Link", "Founder", "nanoprobe",
              "Collective"],
    "goldDone": ["Tucker", "Douwd"],
}

TOKENS_HERS = {"%1", "%2"}
TOKENS_YOURS = {"%3"}


class Refused(Exception):
    pass


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def arms(raw):
    out = []
    for a in raw or []:
        go = a["go"]
        out.append({"go": go if isinstance(go, list) else [go],
                    "requires": list(a.get("requires", [])),
                    "forbids": list(a.get("forbids", []))})
    return out


def read_doc(d):
    nodes = []
    for n in d.get("nodes", []):
        nodes.append({
            "id": n["id"],
            "tier": n.get("tier"),
            "lines": [{"voice": ln.get("voice", "captain"), "text": ln["text"]}
                      for ln in n.get("lines", [])],
            "options": [{"text": o["text"], "go": o["go"],
                         "requires": list(o.get("requires", [])),
                         "forbids": list(o.get("forbids", [])),
                         "mark": list(o.get("mark", []))}
                        for o in n.get("options", [])],
            "mark": list(n.get("mark", [])),
            "promote": bool(n.get("promote", False)),
        })
    return {
        "id": d["id"],
        "order": d.get("order", 0),
        "title": d.get("title", ""),
        "requires": list(d.get("requires", [])),
        "forbids": list(d.get("forbids", [])),
        "tiers": [{"id": str(t["id"]), "requires": list(t.get("requires", [])),
                   "forbids": list(t.get("forbids", []))}
                  for t in d.get("tiers", [])],
        "entry": arms(d.get("entry")),
        "home": arms(d.get("home")),
        "bye": arms(d.get("bye")),
        "nodes": nodes,
    }


def load(folder=CAPTAIN_DIR):
    """(hub, topics), topics in hub order."""
    docs = [read_doc(content.read(p)) for p in sorted(Path(folder).glob("*.json"))]
    hub = [d for d in docs if d["id"] == "HUB"]
    topics = sorted([d for d in docs if d["id"] != "HUB"], key=lambda d: d["order"])
    return (hub[0] if hub else None), topics


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------
def comms_flags():
    """Every flag the channel's threads or its code can set."""
    out = set(gen_comms.SYSTEM_FLAGS)
    for t in gen_comms.THREADS:
        for n in t["nodes"]:
            out.update(n["sets"])
            for o in n["options"]:
                out.update(o["sets"])
    return out


def is_dynamic(cond):
    return gen_comms.is_dynamic(cond) or any(p.match(cond) for p in CAPTAIN_DYNAMIC)


def validate(hub, topics, tape_ids):
    problems = []
    bad = problems.append
    flags = comms_flags()
    marks_set = set()
    conds = []   # (where, cond)

    if hub is None:
        raise Refused("content/captain has no HUB.json")
    for key in ("entry", "home", "bye"):
        if not hub[key]:
            bad(f"HUB: no {key} route")

    docs = [hub] + topics
    seen = set()
    orders = set()
    for d in docs:
        did = d["id"]
        if not re.match(r"^[A-Z][A-Z0-9]*$", did):
            bad(f"{did!r}: ids are capitals and digits")
        if did in seen:
            bad(f"{did} is declared twice")
        seen.add(did)
        is_hub = did == "HUB"
        if not is_hub:
            if not d["title"]:
                bad(f"{did}: no title for the hub")
            if not d["title"].isascii():
                bad(f"{did}: the title is upper-cased on its button and must be ASCII")
            if len(d["title"]) > TITLE_MAX:
                bad(f"{did}: title is {len(d['title'])} characters, over {TITLE_MAX}: "
                    f"{d['title']!r}")
            if d["order"] in orders:
                bad(f"{did}: order {d['order']} is taken")
            orders.add(d["order"])
            if not d["entry"]:
                bad(f"{did}: no entry route")
            if not d["tiers"]:
                bad(f"{did}: no tiers")
        for c in d["requires"] + d["forbids"]:
            conds.append((f"{did} offer", c))
        tier_ids = {t["id"]: t for t in d["tiers"]}
        for t in d["tiers"]:
            for c in t["requires"] + t["forbids"]:
                conds.append((f"{did} tier {t['id']}", c))

        ids = {}
        for n in d["nodes"]:
            if not re.match(r"^[0-9A-Z]+$", n["id"]):
                bad(f"{did}_{n['id']}: node ids are digits and capitals")
            if n["id"] in ids:
                bad(f"{did}_{n['id']} is declared twice")
            if n["id"] in ("HUB", "BYE"):
                bad(f"{did}_{n['id']}: HUB and BYE are where an option goes, not node ids")
            ids[n["id"]] = n

        def target_ok(where, go):
            if go in ("HUB", "BYE"):
                if is_hub and go == "HUB":
                    return True
                return True
            if go not in ids:
                bad(f"{where}: goes to {go}, which is not a node of {did}")
                return False
            return True

        routes = [("entry", d["entry"])]
        if is_hub:
            routes += [("home", d["home"]), ("bye", d["bye"])]
        starts = []
        for rname, route in routes:
            for i, a in enumerate(route, 1):
                for go in a["go"]:
                    if go in ("HUB", "BYE"):
                        bad(f"{did} {rname} arm {i}: a route must name a node")
                    elif target_ok(f"{did} {rname} arm {i}", go):
                        starts.append(go)
                for c in a["requires"] + a["forbids"]:
                    conds.append((f"{did} {rname}", c))
            if route and (route[-1]["requires"] or route[-1]["forbids"]):
                bad(f"{did} {rname}: the last arm must be unconditional")

        for n in d["nodes"]:
            where = f"{did}_{n['id']}"
            marks_set.update(n["mark"])
            if not n["lines"]:
                bad(f"{where}: a node with nothing said")
            tier = None
            if is_hub:
                if n["tier"]:
                    bad(f"{where}: hub nodes have no tier")
            else:
                if not n["tier"]:
                    bad(f"{where}: a topic node needs a tier")
                elif n["tier"] not in tier_ids:
                    bad(f"{where}: tier {n['tier']} is not one {did} declares")
                else:
                    tier = tier_ids[n["tier"]]
            for i, ln in enumerate(n["lines"], 1):
                if ln["voice"] not in VOICES or ln["voice"] == "you":
                    bad(f"{where} line {i}: voice {ln['voice']!r} is not hers")
                if len(ln["text"]) > LINE_MAX:
                    bad(f"{where} line {i} is {len(ln['text'])} characters, over "
                        f"{LINE_MAX}: {ln['text']!r}")
                for tok in set(re.findall(r"%\d", ln["text"])) - TOKENS_HERS:
                    bad(f"{where} line {i}: token {tok} is not one she may use")
            open_option = not n["options"]
            for i, o in enumerate(n["options"], 1):
                target_ok(f"{where} option {i}", o["go"])
                marks_set.update(o["mark"])
                if not o["text"].isascii():
                    bad(f"{where} option {i} is upper-cased on its button and must be ASCII")
                if len(o["text"]) > OPTION_MAX:
                    bad(f"{where} option {i} is {len(o['text'])} characters, over "
                        f"{OPTION_MAX}: {o['text']!r}")
                for tok in set(re.findall(r"%\d", o["text"])) - TOKENS_YOURS:
                    bad(f"{where} option {i}: token {tok} is hers, not yours")
                for c in o["requires"] + o["forbids"]:
                    conds.append((where, c))
                if not o["requires"] and not o["forbids"]:
                    open_option = True
            if is_hub and n["options"] and not open_option:
                bad(f"{where}: every option is conditional, and a hub node has no "
                    f"back button to fall back on")

            # The spoilers (CAPTAIN.md 2). A hub node has no tier, so it may
            # carry none; a topic node's tier has to wait on the gate.
            gates = set(tier["requires"]) if tier else set()
            texts = [ln["text"] for ln in n["lines"]] + [o["text"] for o in n["options"]]
            for gate, words in SPOILERS.items():
                for w in words:
                    if any(w in t for t in texts) and gate not in gates:
                        bad(f"{where}: says {w!r} in a tier that does not wait on "
                            f"{gate!r}")

        # Reachability, from the routes and every option.
        reached, stack = set(), list(starts)
        while stack:
            cur = stack.pop()
            if cur in reached or cur not in ids:
                continue
            reached.add(cur)
            stack.extend(o["go"] for o in ids[cur]["options"])
        for nid in ids:
            if nid not in reached:
                bad(f"{did}_{nid} cannot be reached")

    for where, c in conds:
        m = MARK.match(c)
        if m:
            if m.group(1) not in marks_set:
                bad(f"{where}: waits on {c!r}, which no node or option marks")
            continue
        if is_dynamic(c):
            w = re.match(r"^watched:(TREK_\w+)$", c)
            if w and w.group(1) not in tape_ids:
                bad(f"{where}: waits on watching {w.group(1)}, which is not a tape")
            continue
        if c not in flags:
            bad(f"{where}: waits on {c!r}, which neither she nor the channel knows")
    for m in marks_set:
        if not re.match(r"^[a-z][A-Za-z]*$", m):
            bad(f"a mark {m!r} must be a lower-case word")

    if problems:
        raise Refused("\n".join(problems))


# ---------------------------------------------------------------------------
# Keys and output
# ---------------------------------------------------------------------------
def voice_key(v):
    return f"{PREFIX}Voice_{v}"


def title_key(tid):
    return f"{PREFIX}{tid}_Title"


def line_key(did, nid, i):
    return f"{PREFIX}{did}_{nid}_L{i}"


def option_key(did, nid, i):
    return f"{PREFIX}{did}_{nid}_O{i}"


def build(hub, topics):
    text = {}
    for v, (name, _) in VOICES.items():
        text[voice_key(v)] = name
    for d in [hub] + topics:
        if d["id"] != "HUB":
            text[title_key(d["id"])] = d["title"]
        for n in d["nodes"]:
            for i, ln in enumerate(n["lines"], 1):
                text[line_key(d["id"], n["id"], i)] = ln["text"]
            for i, o in enumerate(n["options"], 1):
                text[option_key(d["id"], n["id"], i)] = o["text"]
    return text


L = json.dumps


def lua_list(items):
    items = list(items)
    return "{ " + ", ".join(L(x) for x in items) + " }" if items else "{}"


def full(did, go):
    return go if go in ("HUB", "BYE") else f"{did}_{go}"


def lua_route(did, route):
    out = []
    for a in route:
        f = ["go = " + lua_list(full(did, g) for g in a["go"])]
        if a["requires"]:
            f.append("requires = " + lua_list(a["requires"]))
        if a["forbids"]:
            f.append("forbids = " + lua_list(a["forbids"]))
        out.append("{ " + ", ".join(f) + " }")
    return "{ " + ", ".join(out) + " }"


def write_lua(path, hub, topics):
    out = []
    w = out.append
    w("-- GENERATED by tools/gen_captain.py -- do not edit by hand.")
    w("--")
    w("-- Captain Titus's conversation (CAPTAIN.md 5). Every string here is a")
    w("-- translation key into Translate/EN/Print_Text.json, written by the same")
    w("-- program, so the two cannot disagree. The server walks this for each")
    w("-- player who talks to her; the panel draws the lines it names.")
    w("")
    w("TREK_CaptainTree = {}")
    w("local T = TREK_CaptainTree")
    w("")
    w("T.voices = {")
    for v, (_, (r, g, b)) in VOICES.items():
        w(f"    {v} = {{ name = {L(voice_key(v))}, r = {r:.2f}, g = {g:.2f}, b = {b:.2f} }},")
    w("}")
    w("")
    w("T.dynamic = " + lua_list(p.pattern for p in CAPTAIN_DYNAMIC))
    w("")
    w("T.hub = { entry = " + lua_route("HUB", hub["entry"]) + ",")
    w("          home = " + lua_route("HUB", hub["home"]) + ",")
    w("          bye = " + lua_route("HUB", hub["bye"]) + " }")
    w("")
    w("-- The topics, in the order the hub lists them.")
    w("T.order = { " + ", ".join(L(t["id"]) for t in topics) + " }")
    w("")
    w("T.topics = {")
    for t in topics:
        tiers = ", ".join(
            f"{{ id = {L(x['id'])}, requires = {lua_list(x['requires'])}, "
            f"forbids = {lua_list(x['forbids'])} }}" for x in t["tiers"])
        w(f"    {t['id']} = {{ title = {L(title_key(t['id']))}, "
          f"requires = {lua_list(t['requires'])}, forbids = {lua_list(t['forbids'])},")
        w(f"        tiers = {{ {tiers} }},")
        w(f"        entry = {lua_route(t['id'], t['entry'])} }},")
    w("}")
    w("")
    w("T.nodes = {")
    for d in [hub] + topics:
        did = d["id"]
        for n in d["nodes"]:
            parts = [f"topic = {L(did)}"]
            if n["tier"]:
                parts.append(f"tier = {L(n['tier'])}")
            ls = ", ".join(f"{{ v = {L(ln['voice'])}, k = {L(line_key(did, n['id'], i))} }}"
                           for i, ln in enumerate(n["lines"], 1))
            parts.append(f"lines = {{ {ls} }}")
            if n["options"]:
                os_ = []
                for i, o in enumerate(n["options"], 1):
                    f = [f"k = {L(option_key(did, n['id'], i))}",
                         f"go = {L(full(did, o['go']))}"]
                    if o["requires"]:
                        f.append("requires = " + lua_list(o["requires"]))
                    if o["forbids"]:
                        f.append("forbids = " + lua_list(o["forbids"]))
                    if o["mark"]:
                        f.append("mark = " + lua_list(o["mark"]))
                    os_.append("{ " + ", ".join(f) + " }")
                parts.append("options = {\n        " + ",\n        ".join(os_) + ",\n    }")
            if n["mark"]:
                parts.append("mark = " + lua_list(n["mark"]))
            if n["promote"]:
                parts.append("promote = true")
            w(f"    [{L(did + '_' + n['id'])}] = {{ " + ", ".join(parts) + " },")
    w("}")
    w("")
    w("return T")
    w("")
    path.write_text("\n".join(out), encoding="utf-8")


def write_text(path, text):
    merged = {}
    if path.exists():
        merged = {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items()
                  if not k.startswith(PREFIX)}
    merged.update(text)
    body = json.dumps(merged, indent=4, ensure_ascii=True, sort_keys=True)
    path.write_text(body + "\n", encoding="utf-8")


def outputs(base):
    return (base / "media/lua/shared/TREK/TREK_CaptainTree.lua",
            base / "media/lua/shared/Translate/EN/Print_Text.json")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    base = Path(sys.argv[1])
    if not base.is_absolute():
        base = ROOT / base
    hub, topics = load()
    try:
        validate(hub, topics, gen_comms.tape_ids())
    except Refused as exc:
        print("REFUSED -- the tree was not written:")
        print(exc)
        return 2
    text = build(hub, topics)
    lua, json_path = outputs(base)
    write_lua(lua, hub, topics)
    write_text(json_path, text)
    nodes = sum(len(d["nodes"]) for d in [hub] + topics)
    lines = sum(len(n["lines"]) for d in [hub] + topics for n in d["nodes"])
    print(f"{len(topics)} topic(s), {nodes} nodes, {lines} lines, {len(text)} keys")
    for p in (lua, json_path):
        try:
            print("wrote %s" % p.relative_to(ROOT))
        except ValueError:
            print("wrote %s" % p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
