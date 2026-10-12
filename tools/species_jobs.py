"""The ledger for the Klingon and Vulcan cabins' generated art: every concept and mesh.

    python tools/species_jobs.py set <people> <piece> <key> <value> [<key> <value>...]
    python tools/species_jobs.py show [missing-concept|missing-mesh]
    python tools/species_jobs.py fetch            # download what is recorded

Keys: concept_url, concept_by, mesh_request, mesh_response_url, mesh_url. Concepts download to
design/art/species/<people>/<piece>_concept.<ext> and meshes to
tools/assets/species/<people>/<piece>.glb. tools/adirondack_jobs.py is Starfleet's.
"""
import json
import os
import sys
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ART = os.path.join(ROOT, "design", "art", "species")
LEDGER = os.path.join(ART, "jobs.json")
MESHES = os.path.join(ROOT, "tools", "assets", "species")
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import species_objects as S  # noqa: E402


def load():
    if os.path.exists(LEDGER):
        with open(LEDGER) as f:
            return json.load(f)
    return {}


def save(d):
    os.makedirs(ART, exist_ok=True)
    with open(LEDGER, "w") as f:
        json.dump(d, f, indent=1, sort_keys=True)


def concept_path(people, name):
    for ext in (".png", ".jpg"):
        p = os.path.join(ART, people, name + "_concept" + ext)
        if os.path.exists(p):
            return p
    return None


def mesh_path(people, name):
    return os.path.join(MESHES, people, name + ".glb")


def get(url, out):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req) as r, open(out, "wb") as f:
        f.write(r.read())


def fetch(d):
    for people, recs in sorted(d.items()):
        os.makedirs(os.path.join(ART, people), exist_ok=True)
        os.makedirs(os.path.join(MESHES, people), exist_ok=True)
        for name, rec in sorted(recs.items()):
            url = rec.get("concept_url")
            if url and not concept_path(people, name):
                ext = os.path.splitext(url.split("?")[0])[1] or ".png"
                get(url, os.path.join(ART, people, name + "_concept" + ext))
                print("concept", people, name)
            url = rec.get("mesh_url")
            if url and not os.path.exists(mesh_path(people, name)):
                get(url, mesh_path(people, name))
                print("mesh", people, name)


def main():
    d = load()
    cmd = sys.argv[1] if len(sys.argv) > 1 else "show"
    if cmd == "set":
        people, name = sys.argv[2], sys.argv[3]
        if name not in S.PIECES.get(people, {}):
            sys.exit("not in the manifest: %s %s" % (people, name))
        rec = d.setdefault(people, {}).setdefault(name, {})
        kv = sys.argv[4:]
        for k, v in zip(kv[::2], kv[1::2]):
            rec[k] = v
        save(d)
    elif cmd == "fetch":
        fetch(d)
    else:
        want = sys.argv[2] if len(sys.argv) > 2 else None
        for people in S.PIECES:
            for name, (kind, _) in S.PIECES[people].items():
                rec = d.get(people, {}).get(name, {})
                has_c = bool(rec.get("concept_url")) or bool(concept_path(people, name))
                has_m = bool(rec.get("mesh_url")) or os.path.exists(mesh_path(people, name))
                if want == "missing-concept" and has_c:
                    continue
                if want == "missing-mesh" and (kind != "model" or has_m):
                    continue
                print("%-8s %-16s %-7s concept=%s mesh=%s" % (people, name, kind, "yes" if has_c else "-",
                                                             "yes" if has_m else ("queued" if rec.get("mesh_response_url") else "-")))


if __name__ == "__main__":
    main()
