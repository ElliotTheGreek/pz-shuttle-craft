"""The crew's talk: every file compiles, the compiled tree is what is on disk,
and a broken tree is refused for the right reason.

    python tests/test_crew.py
"""
import json
import os
import re
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_crew_talk as G  # noqa: E402

failures = []


def fail(msg):
    failures.append(msg)


GOOD = """
scene: t_ok
where: sickbay
cast: a=any, b=medical

= start
a: Hello, {b}. | Morning.
-> two 2, three

= two
b: Fine.
...
-> end

= three
b: Also fine.
"""

BROKEN = {
    "no '= start'": "scene: t\nwhere: any\ncast: a=any, b=any\n= one\na: hi\n",
    "goes nowhere": "scene: t\nwhere: any\ncast: a=any, b=any\n= start\na: hi\n-> nope\n",
    "not in the cast": "scene: t\nwhere: any\ncast: a=any, b=any\n= start\nc: hi\n",
    "80 characters": "scene: t\nwhere: any\ncast: a=any, b=any\n= start\na: " + "x" * 81 + "\n",
    "unknown place": "scene: t\nwhere: holodeck\ncast: a=any, b=any\n= start\na: hi\n",
    "unknown cast requirement": "scene: t\nwhere: any\ncast: a=wizard, b=any\n= start\na: hi\n",
    "nothing reaches": "scene: t\nwhere: any\ncast: a=any, b=any\n= start\na: hi\n= lost\nb: hi\n",
    "never reach an end": ("scene: t\nwhere: any\ncast: a=any, b=any\n= start\na: hi\n-> loop\n"
                           "= loop\nb: again\n-> start\n"),
    "is not a role": "scene: t\nwhere: any\ncast: a=any, b=any\n= start\na: hi {c}\n",
    "unknown bark category": "bark: shout\nwhere: any\n- hi\n",
    "a bark has nobody to name": "bark: hello\nwhere: any\n- hi {a}\n",
    "two to four roles": "scene: t\nwhere: any\ncast: a=any\n= start\na: hi\n",
}


def refused_for(text):
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "t.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(text)
        try:
            s, b = G.parse(path)
            G.validate(s, b)
        except G.Refused as exc:
            return str(exc)
    return None


def main():
    # --- the good one compiles, and its variants and beats land ------------
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "good.txt")
        with open(path, "w", encoding="utf-8") as f:
            f.write(GOOD)
        s, b = G.parse(path)
        G.validate(s, b)
        lua, text = G.build(s, b)
        if "Print_Text_TREK_CREW_t_ok_start_1_2" not in text:
            fail("a line's second variant has no key")
        if "{ 0 }" not in lua:
            fail("a beat ('...') did not compile to { 0 }")

    # --- every broken tree is refused, for its own reason -------------------
    for why, text in BROKEN.items():
        got = refused_for(text)
        if got is None:
            fail("accepted a tree with %s" % why)
        elif why not in got:
            fail("refused a tree with %s, but said: %s" % (why, got))

    # --- the real files compile, and what is on disk is what they make -------
    try:
        files, scenes, barks = G.load()
    except G.Refused as exc:
        fail("design/crew does not compile: %s" % exc)
        files, scenes, barks = [], [], []
    if files:
        lua, text = G.build(scenes, barks)
        have = open(G.LUA, encoding="utf-8").read() if os.path.exists(G.LUA) else ""
        if have != lua:
            fail("TREK_CrewTalk.lua is not what tools/gen_crew_talk.py writes now -- run it")
        on_disk = {k: v for k, v in json.load(open(G.TEXT, encoding="utf-8")).items()
                   if k.startswith(G.PREFIX)}
        if on_disk != text:
            fail("Print_Text.json's crew keys are not what the generator writes -- run it")
        used = set(re.findall(r'"(Print_Text_TREK_CREW_[A-Za-z0-9_]+)"', have))
        # every base the tree names has at least its first variant
        for base in used:
            if base + "_1" not in on_disk:
                fail("the tree names %s and there is no text for it" % base)
        places = {p for s in scenes for p in s["where"]}
        for p in ("bridge", "lounge", "sickbay", "engineering", "transporter"):
            if p not in places:
                fail("no scene is written for %s" % p)
        cats = {b["category"] for b in barks}
        for c in ("hello", "outfit", "idle"):
            if c not in cats:
                fail("no %s barks" % c)

    if failures:
        print("%d PROBLEM(S):" % len(failures))
        for f in failures:
            print("  " + f)
        sys.exit(1)
    print("crew talk: %d file(s), %d scenes, %d bark lines compile and match what is on disk; "
          "%d broken trees refused for the right reason"
          % (len(files), len(scenes), sum(len(b["lines"]) for b in barks), len(BROKEN)))


main()
