"""The writing in content/, one sentence at a time, out and back in.

    python tools/text_units.py export units.jsonl [--only tapes|comms] [--file ID]
    python tools/text_units.py import units.jsonl [--dry-run]

**export** writes one JSON object per line -- a *unit* -- for every piece of
text a player reads: each tape line, channel line and option, and the titles
around them. A unit carries what a rewriter needs and nothing it could break:

    id       stable address, e.g. "comms/FIRST#nodes/3/lines/1"
    file     the content file it came from
    kind     tape-line | comms-line | option | title
    voice    who says it (card, shepard, tucker ...)
    max      the longest it may be
    tokens   %1 / %2 it contains -- a rewrite must keep exactly these
    before   the line before it, for context (same scene)
    after    the line after it
    text     the line as it is

**import** reads the same file back. A unit with a `new` field is a rewrite:
it is applied only if it is non-empty, one line, within `max`, and carries
exactly the same tokens; anything else is refused and listed, and nothing is
written for a file with a refused unit unless `--partial` is given. The files
are written back in the house layout (tools/content.py), so a diff of a pass is
a diff of sentences. Run the generators afterwards (content/README.md).
"""
import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import content  # noqa: E402

LINE_MAX = 70
OPTION_MAX = 60
TOKEN = re.compile(r"%\d")


def tokens(text):
    return sorted(TOKEN.findall(text or ""))


def units_for_tape(path):
    d = content.read(path)
    rel = f"tapes/{path.stem}"
    out = []
    for f in ("display", "title", "subtitle", "author", "extra"):
        if d.get(f):
            out.append({"id": f"{rel}#{f}", "file": str(path.relative_to(ROOT)),
                        "path": [f], "kind": "title", "voice": None, "max": 80,
                        "tokens": tokens(d[f]), "text": d[f]})
    lines = d["lines"]
    for i, ln in enumerate(lines):
        out.append({"id": f"{rel}#lines/{i}", "file": str(path.relative_to(ROOT)),
                    "path": ["lines", i, "text"], "kind": "tape-line",
                    "voice": ln["voice"], "max": LINE_MAX, "tokens": tokens(ln["text"]),
                    "before": lines[i - 1]["text"] if i > 0 else None,
                    "after": lines[i + 1]["text"] if i + 1 < len(lines) else None,
                    "text": ln["text"]})
    return out


def units_for_thread(path):
    d = content.read(path)
    rel = f"comms/{path.stem}"
    f = str(path.relative_to(ROOT))
    out = [{"id": f"{rel}#title", "file": f, "path": ["title"], "kind": "title",
            "voice": None, "max": 40, "tokens": tokens(d["title"]), "text": d["title"]}]
    for ni, n in enumerate(d["nodes"]):
        lines = n.get("lines", [])
        for li, ln in enumerate(lines):
            out.append({"id": f"{rel}#nodes/{ni}/lines/{li}", "file": f,
                        "path": ["nodes", ni, "lines", li, "text"], "kind": "comms-line",
                        "node": n["id"], "voice": ln["voice"], "max": LINE_MAX,
                        "tokens": tokens(ln["text"]),
                        "before": lines[li - 1]["text"] if li > 0 else None,
                        "after": lines[li + 1]["text"] if li + 1 < len(lines) else None,
                        "text": ln["text"]})
        last = lines[-1]["text"] if lines else None
        for oi, o in enumerate(n.get("options", [])):
            out.append({"id": f"{rel}#nodes/{ni}/options/{oi}", "file": f,
                        "path": ["nodes", ni, "options", oi, "text"], "kind": "option",
                        "node": n["id"], "voice": "you", "max": OPTION_MAX,
                        "tokens": tokens(o["text"]), "before": last, "after": None,
                        "text": o["text"]})
    return out


def export(args):
    units = []
    if args.only in (None, "tapes"):
        for p in content.tape_files():
            if args.file in (None, p.stem):
                units += units_for_tape(p)
    if args.only in (None, "comms"):
        for p in content.thread_files():
            if args.file in (None, p.stem):
                units += units_for_thread(p)
    with open(args.path, "w", encoding="utf-8") as fh:
        for u in units:
            fh.write(json.dumps(u, ensure_ascii=False) + "\n")
    print(f"{len(units)} units -> {args.path}")


def check(unit, new):
    """Why a rewrite may not go in, or None."""
    if not isinstance(new, str) or not new.strip():
        return "empty"
    if "\n" in new or "\r" in new:
        return "more than one line"
    if len(new) > unit["max"]:
        return f"{len(new)} characters, over {unit['max']}"
    if tokens(new) != unit["tokens"]:
        return f"tokens {tokens(new)} where the line had {unit['tokens']}"
    return None


def set_path(doc, path, value):
    cur = doc
    for k in path[:-1]:
        cur = cur[k]
    old = cur[path[-1]]
    cur[path[-1]] = value
    return old


def get_path(doc, path):
    cur = doc
    for k in path:
        cur = cur[k]
    return cur


def do_import(args):
    by_file = {}
    refused, applied, stale = [], 0, []
    with open(args.path, encoding="utf-8") as fh:
        for n, raw in enumerate(fh, 1):
            if not raw.strip():
                continue
            u = json.loads(raw)
            if "new" not in u or u["new"] == u["text"]:
                continue
            why = check(u, u["new"])
            if why:
                refused.append((u["id"], why, u["new"]))
                by_file.setdefault(u["file"], {"bad": True, "units": []})["bad"] = True
                continue
            by_file.setdefault(u["file"], {"bad": False, "units": []})["units"].append(u)

    for f, job in sorted(by_file.items()):
        if job["bad"] and not args.partial:
            continue
        path = ROOT / f
        doc = content.read(path)
        for u in job["units"]:
            # The file must still say what was exported, or the rewrite is of
            # a line that has since been changed by somebody else.
            if get_path(doc, u["path"]) != u["text"]:
                stale.append(u["id"])
                continue
            set_path(doc, u["path"], u["new"])
            applied += 1
        if not args.dry_run:
            content.write(path, doc)

    for uid, why, new in refused:
        print(f"REFUSED {uid}: {why}\n        {new!r}")
    for uid in stale:
        print(f"STALE   {uid}: the file no longer says what was exported")
    skipped = [f for f, j in by_file.items() if j["bad"] and not args.partial]
    for f in skipped:
        print(f"SKIPPED {f}: it has a refused unit (use --partial to apply the rest)")
    verb = "would apply" if args.dry_run else "applied"
    print(f"{verb} {applied} rewrite(s); {len(refused)} refused, {len(stale)} stale")
    if not args.dry_run and applied:
        print("now: python tools/gen_tapes.py TrekShuttle/42 && "
              "python tools/gen_comms.py TrekShuttle/42")
    return 1 if refused or stale else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    e = sub.add_parser("export")
    e.add_argument("path")
    e.add_argument("--only", choices=("tapes", "comms"))
    e.add_argument("--file")
    i = sub.add_parser("import")
    i.add_argument("path")
    i.add_argument("--dry-run", action="store_true")
    i.add_argument("--partial", action="store_true")
    args = ap.parse_args()
    if args.cmd == "export":
        export(args)
        return 0
    return do_import(args)


if __name__ == "__main__":
    raise SystemExit(main())
