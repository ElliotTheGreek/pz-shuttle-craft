"""Runs a list of mutations against chosen test sections, one at a time.

    python tools/mutate.py SPEC.py                 # every mutation in SPEC
    python tools/mutate.py SPEC.py 3 7             # only those numbers

SPEC is a Python file defining

    SECTIONS  = "rules,rules_multiplayer"          # TREK_ONLY for test_multiplayer.py
    COMMAND   = [...]                              # optional: another check to run
    MUTATIONS = [(file, old, new, what), ...]      # paths from the repo's root

Each mutation is applied, **asserted to have changed the file** (DEV_GUIDE:
*A mutation that does not apply proves nothing*), run, and taken back out in
a `finally`. A mutation the checks do not catch is reported MISSED. `old`
must match exactly once: a text found twice mutates the first, which may be
the wrong line (SENTRY.md).

One pass at a time. Two passes share the files they edit, and the second
restores the first's mutation as if it were the original (DEV_GUIDE).
"""
import os
import runpy
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    spec = runpy.run_path(sys.argv[1])
    only = [int(a) for a in sys.argv[2:]]
    env = dict(os.environ, TREK_ONLY=spec.get("SECTIONS", ""))
    command = spec.get("COMMAND") or [sys.executable, os.path.join(ROOT, "tests", "test_multiplayer.py")]
    missed, bad = [], []
    for i, (rel, old, new, what) in enumerate(spec["MUTATIONS"], 1):
        if only and i not in only:
            continue
        path = os.path.join(ROOT, rel)
        raw = open(path, "rb").read()
        text = raw.decode("utf-8")
        crlf = "\r\n" in text
        body = text.replace("\r\n", "\n")
        if body.count(old) != 1:
            print("%2d  DID NOT APPLY (%d matches)  %s" % (i, body.count(old), what))
            bad.append(i)
            continue
        mutated = body.replace(old, new)
        assert mutated != body, "mutation %d changed nothing" % i
        if crlf:
            mutated = mutated.replace("\n", "\r\n")
        try:
            open(path, "wb").write(mutated.encode("utf-8"))
            run = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True)
        finally:
            open(path, "wb").write(raw)
        caught = run.returncode != 0
        print("%2d  %s  %s" % (i, "caught" if caught else "MISSED", what))
        if not caught:
            missed.append(i)
    print("\n%d mutation(s): %d missed %s, %d did not apply %s"
          % (len(spec["MUTATIONS"]) if not only else len(only), len(missed), missed, len(bad), bad))
    sys.exit(1 if missed or bad else 0)


main()
