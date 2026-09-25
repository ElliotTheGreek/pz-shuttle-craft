"""The ledger for the Adirondack's generated art: every concept and mesh job.

    python tools/adirondack_jobs.py set <object> <key> <value> [<key> <value>...]
    python tools/adirondack_jobs.py show [missing-concept|missing-mesh]
    python tools/adirondack_jobs.py fetch            # download what is recorded

Keys used: concept_url, concept_by (gemini|flux), mesh_status_url,
mesh_response_url, mesh_url, mesh_request. Images and meshes download to
design/art/adirondack/objects/<object>_concept.<ext> and
tools/assets/adirondack/<object>.glb -- the raws are vendored, as the EMH's
is, because generating again gives a different object, not the same one.
"""
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER = os.path.join(ROOT, "design", "art", "adirondack", "objects", "jobs.json")
CONCEPTS = os.path.dirname(LEDGER)
MESHES = os.path.join(ROOT, "tools", "assets", "adirondack")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import adirondack_objects as A  # noqa: E402


def load():
    if os.path.exists(LEDGER):
        with open(LEDGER) as f:
            return json.load(f)
    return {}


def save(d):
    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    with open(LEDGER, "w") as f:
        json.dump(d, f, indent=1, sort_keys=True)


def fetch(d):
    os.makedirs(MESHES, exist_ok=True)
    for name, rec in sorted(d.items()):
        url = rec.get("concept_url")
        if url:
            ext = os.path.splitext(url.split("?")[0])[1] or ".png"
            out = os.path.join(CONCEPTS, name + "_concept" + ext)
            if not os.path.exists(out):
                urllib.request.urlretrieve(url, out)
                print("concept", name)
        url = rec.get("mesh_url")
        if url:
            out = os.path.join(MESHES, name + ".glb")
            if not os.path.exists(out):
                urllib.request.urlretrieve(url, out)
                print("mesh", name)


def main():
    d = load()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "set":
        name = sys.argv[2]
        if name not in A.by_name():
            sys.exit("not in the manifest: " + name)
        kv = sys.argv[3:]
        rec = d.setdefault(name, {})
        for k, v in zip(kv[::2], kv[1::2]):
            rec[k] = v
        save(d)
    elif cmd == "fetch":
        fetch(d)
    else:
        want = sys.argv[2] if len(sys.argv) > 2 else None
        for o in A.OBJECTS:
            rec = d.get(o["name"], {})
            if o["kind"] == "reuse":
                continue
            if want == "missing-concept" and rec.get("concept_url"):
                continue
            if want == "missing-mesh" and (o["kind"] != "model" or rec.get("mesh_url")):
                continue
            print("%-20s %-6s concept=%s mesh=%s" % (
                o["name"], o["kind"], "yes" if rec.get("concept_url") else "-",
                "yes" if rec.get("mesh_url") else ("queued" if rec.get("mesh_status_url") else "-")))


if __name__ == "__main__":
    main()
