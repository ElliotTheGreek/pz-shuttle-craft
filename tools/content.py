"""The mod's writing, read from content/ (content/README.md).

Every word a player reads in a tape or on the Adirondack channel lives in
content/, one JSON file per tape and one per thread, beside the structure it
belongs to -- voices, effect codes, where an option goes. The generators
(gen_tapes.py, gen_comms.py) read it through here and nothing else; the text
is not in any Python file.

`dump` writes a file back in the house layout -- one line of dialogue per line
of file -- so a diff of a rewrite is a diff of sentences.
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTENT = ROOT / "content"
TAPES_DIR = CONTENT / "tapes"
COMMS_DIR = CONTENT / "comms"


# ---------------------------------------------------------------------------
# Reading
# ---------------------------------------------------------------------------
def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def tape_files():
    return sorted(TAPES_DIR.glob("*.json"))


def thread_files():
    return sorted(COMMS_DIR.glob("*.json"))


def load_tapes():
    """Every tape, in shelf order, in the shape gen_tapes.py has always used."""
    docs = [read(p) for p in tape_files()]
    orders = [d["order"] for d in docs]
    if len(set(orders)) != len(orders):
        raise SystemExit("content/tapes: two tapes share an order number")
    tapes = []
    for d in sorted(docs, key=lambda d: d["order"]):
        t = {k: d.get(k) for k in ("id", "display", "title", "subtitle",
                                   "author", "extra")}
        t["spawning"] = d.get("spawning", 0)
        if d.get("issued"):
            t["issued"] = True
        t["lines"] = [{"voice": ln["voice"], "text": ln["text"],
                       "codes": ln.get("codes"), "key": ln.get("key")}
                      for ln in d["lines"]]
        tapes.append(t)
    return tapes


def load_threads():
    """Every thread, in priority order, in comms_vocab's shape."""
    from comms_vocab import say, opt, branch, node, thread
    docs = [read(p) for p in thread_files()]
    prios = [d["priority"] for d in docs]
    if len(set(prios)) != len(prios):
        raise SystemExit("content/comms: two threads share a priority")
    out = []
    for d in sorted(docs, key=lambda d: d["priority"]):
        nodes = []
        for n in d["nodes"]:
            lines = [say(l["voice"], l["text"]) for l in n.get("lines", [])]
            options = [opt(o["text"], o["go"], o.get("requires", ()), o.get("forbids", ()),
                           o.get("sets", ()), o.get("clears", ()))
                       for o in n.get("options", [])]
            route = None
            if "route" in n:
                route = [branch(a["go"], a.get("requires", ()), a.get("forbids", ()))
                         for a in n["route"]]
            nodes.append(node(n["id"], *lines, options=options,
                              timeout=n.get("timeout"), silence=n.get("silence"),
                              route=route, sets=n.get("sets", ()),
                              clears=n.get("clears", ()), issue=n.get("issue", ()),
                              convert=n.get("convert", False)))
        after = d.get("after")
        out.append(thread(d["id"], d["title"], d["kind"], nodes,
                          entries=d.get("entries"), day=d.get("day"),
                          after=(after["thread"], after["hours"]) if after else None,
                          requires=d.get("requires", ()), forbids=d.get("forbids", ()),
                          retry=d.get("retry", True), repeatable=d.get("repeatable", False),
                          cooldown=d.get("cooldown")))
    return out


# ---------------------------------------------------------------------------
# Writing, in the house layout
# ---------------------------------------------------------------------------
def _one(v):
    return json.dumps(v, ensure_ascii=False)


def _obj_line(d):
    return "{ " + ", ".join(f"{_one(k)}: {_one(v)}" for k, v in d.items()) + " }"


def dump(doc):
    """A content file as text: plain fields one per line, `notes` as a list
    of lines, and every line of dialogue, option and route arm on one line."""
    out = ["{"]
    keys = list(doc.keys())
    for i, k in enumerate(keys):
        v = doc[k]
        comma = "," if i < len(keys) - 1 else ""
        if k == "notes":
            out.append(f'  "notes": [')
            for j, n in enumerate(v):
                out.append("    " + _one(n) + ("," if j < len(v) - 1 else ""))
            out.append("  ]" + comma)
        elif k == "lines" and isinstance(v, list):
            out.append('  "lines": [')
            for j, ln in enumerate(v):
                out.append("    " + _obj_line(ln) + ("," if j < len(v) - 1 else ""))
            out.append("  ]" + comma)
        elif k == "nodes":
            out.append('  "nodes": [')
            for j, n in enumerate(v):
                out.append("    {")
                nk = list(n.keys())
                for m, key in enumerate(nk):
                    val = n[key]
                    c2 = "," if m < len(nk) - 1 else ""
                    if key in ("lines", "options", "route"):
                        out.append(f"      {_one(key)}: [")
                        for q, row in enumerate(val):
                            out.append("        " + _obj_line(row)
                                       + ("," if q < len(val) - 1 else ""))
                        out.append("      ]" + c2)
                    else:
                        out.append(f"      {_one(key)}: {_one(val)}{c2}")
                out.append("    }" + ("," if j < len(v) - 1 else ""))
            out.append("  ]" + comma)
        else:
            out.append(f"  {_one(k)}: {_one(v)}{comma}")
    out.append("}")
    return "\n".join(out) + "\n"


def write(path, doc):
    text = dump(doc)
    json.loads(text)          # the layout must still be JSON
    Path(path).write_text(text, encoding="utf-8")
