"""The Adirondack channel's generator and the files it writes (COMMS.md 3).

tools/gen_comms.py refuses to write a tree that fails its checks. That is
only worth anything if each check actually refuses what it says it does, so
this feeds it broken trees one fault at a time and asserts each is refused
**for that reason** -- COMMS.md 7's mutations, done at the generator where
they belong:

  * an orphan goto, a silence to nowhere, a route with no way out;
  * a timed node with no silence branch;
  * a node nobody can reach, and a node that can never end the call;
  * a flag required and set by nothing, and a tape watched that does not
    exist;
  * a line over the length a screen can hold;
  * an incoming thread that would ring on the first minute of every world,
    and a repeatable one with nothing to wait on.

And then that what is on disk is what the generator writes now -- a tree
edited and never regenerated is the two-files-disagree failure the generator
exists to make impossible -- and that the Lua names exactly the system flags
the generator believes the code raises.

    python tests/test_comms.py
"""
import copy
import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import gen_comms  # noqa: E402
from comms_vocab import say, opt, branch, node, thread  # noqa: E402

failures = []


def fail(msg):
    failures.append(msg)


TAPES = gen_comms.tape_ids()


def good():
    """A small tree that passes, to be broken one way at a time."""
    return [thread("T", "Test", "incoming", day=1, nodes=[
        node("01", say("shepard", "Hello."),
             options=[opt("Hi.", "02"), opt("...", "03", requires=["met"])],
             timeout=30, silence="03"),
        node("02", say("shepard", "Good."), sets=["met"]),
        node("03", say("shepard", "Quiet one.")),
    ])]


def refused(threads, why, label):
    try:
        gen_comms.validate(threads, TAPES)
    except gen_comms.Refused as exc:
        if why not in str(exc):
            fail(f"{label}: refused, but not for '{why}': {exc}")
        return
    fail(f"{label}: the generator wrote a tree that should have been refused")


def main():
    try:
        gen_comms.validate(good(), TAPES)
    except gen_comms.Refused as exc:
        fail(f"the good tree is refused: {exc}")

    t = good()
    t[0]["nodes"][0]["options"][0]["go"] = "99"
    refused(t, "not a node of T", "an orphan goto")

    t = good()
    t[0]["nodes"][0]["silence"] = "99"
    refused(t, "silence goes to 99", "a silence branch to nowhere")

    t = good()
    t[0]["nodes"][0]["silence"] = None
    refused(t, "a timed node with no silence branch", "a timed node without silence")

    t = good()
    t[0]["nodes"].append(node("04", say("shepard", "Nobody hears this.")))
    refused(t, "cannot be reached", "an unreachable node")

    t = good()
    t[0]["nodes"][1] = node("02", say("shepard", "Round again."),
                            options=[opt("Again.", "02")])
    refused(t, "can never reach the end", "a loop with no exit")

    t = good()
    t[0]["nodes"][1]["sets"] = []
    refused(t, "requires the flag 'met', which nothing sets", "a dropped sets")

    t = good()
    t[0]["nodes"][0]["options"][1]["requires"] = ["watched:TREK_NoSuchTape"]
    refused(t, "not a tape", "a tape nobody made")

    t = good()
    t[0]["nodes"][1]["lines"][0]["text"] = "x" * 71
    refused(t, "over 70", "a line too long for the screen")

    t = good()
    t[0]["nodes"][0]["options"][0]["text"] = "x" * 61
    refused(t, "over 60", "an option too long for its button")

    t = good()
    t[0]["day"] = None
    refused(t, "first minute of every world", "a thread with no trigger")

    t = good()
    t[0]["repeatable"] = True
    refused(t, "must wait on a flag", "a repeatable thread with nothing to wait on")

    t = good()
    t[0]["nodes"][0]["options"] = [opt("...", "03", requires=["met"])]
    t[0]["nodes"][0]["timeout"] = None
    t[0]["nodes"][0]["silence"] = None
    refused(t, "every option is conditional", "a node that can offer nothing")

    t = good()
    t[0]["nodes"][0] = node("01", route=[branch("02", requires=["met"])])
    t[0]["nodes"][2]["sets"] = ["met"]
    refused(t, "last arm must be unconditional", "a route with no way out")

    hail = [thread("H", "Hail", "hail", repeatable=True, requires=[], nodes=[
        node("01", say("shepard", "Hi."))])]
    refused(hail, "needs a cooldown", "a repeatable hail she always answers")

    # --- the real tree passes, and what is on disk is what it writes -------
    try:
        gen_comms.validate(gen_comms.THREADS, TAPES)
    except gen_comms.Refused as exc:
        fail(f"the mod's own tree is refused: {exc}")

    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "media/lua/shared/TREK").mkdir(parents=True)
        (base / "media/lua/shared/Translate/EN").mkdir(parents=True)
        gen_comms.write_lua(base / "media/lua/shared/TREK/TREK_CommsTree.lua",
                            gen_comms.THREADS)
        gen_comms.write_text(base / "media/lua/shared/Translate/EN/Print_Text.json",
                             gen_comms.build(gen_comms.THREADS))
        rel = "media/lua/shared/TREK/TREK_CommsTree.lua"
        if (base / rel).read_text(encoding="utf-8") != (ROOT / "TrekShuttle/42" / rel).read_text(encoding="utf-8"):
            fail(f"{rel} is not what tools/gen_comms.py writes now -- run it")
        # Print_Text.json is shared with the crew's talk: compare the
        # channel's own keys, which are all this generator writes.
        rel = "media/lua/shared/Translate/EN/Print_Text.json"
        def comm(path):
            return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items()
                    if k.startswith("Print_Text_TREK_COMM")}
        if comm(base / rel) != comm(ROOT / "TrekShuttle/42" / rel):
            fail(f"{rel} is not what tools/gen_comms.py writes now -- run it")

    # --- every key the tree names has text, and nothing is orphaned ---------
    lua = (ROOT / "TrekShuttle/42/media/lua/shared/TREK/TREK_CommsTree.lua").read_text(
        encoding="utf-8")
    text = {k: v for k, v in json.loads((ROOT / "TrekShuttle/42/media/lua/shared/Translate/EN/"
                                "Print_Text.json").read_text(encoding="utf-8")).items()
            if k.startswith("Print_Text_TREK_COMM")}
    used = set(re.findall(r'"(Print_Text_TREK_COMM_[A-Za-z0-9_]+)"', lua))
    if len(used) < 100 or len(text) < 100:
        fail(f"only {len(used)} keys in the tree and {len(text)} in the text: "
             f"the pattern has stopped matching, and an empty set passes anything")
    for k in sorted(used - set(text)):
        fail(f"the tree names {k} and Print_Text.json has no text for it")
    for k in sorted(set(text) - used):
        fail(f"Print_Text.json has {k} and the tree never names it")

    # --- the system flags the generator trusts are the ones the code raises -
    code = (ROOT / "TrekShuttle/42/media/lua/server/TREK/TREK_CommsServer.lua").read_text(
        encoding="utf-8")
    raised = set(re.findall(r"d\.flags\.(\w+)\s*=\s*true", code))
    for f in sorted(gen_comms.SYSTEM_FLAGS - raised):
        fail(f"gen_comms.py trusts the code to raise '{f}' and nothing in "
             f"TREK_CommsServer.lua does")
    for f in sorted(raised - gen_comms.SYSTEM_FLAGS):
        fail(f"TREK_CommsServer.lua raises '{f}' and the generator does not "
             f"know it can be waited on")

    # --- the writing is in content/, in the house layout ---------------------
    # tools/text_units.py and a reviewer's diff both rely on one line of
    # dialogue per line of file; a hand edit that reflowed a file would turn a
    # one-sentence rewrite into a whole-file diff.
    import content
    files = content.tape_files() + content.thread_files() + content.captain_files()
    if len(files) < 30:
        fail(f"only {len(files)} files in content/: the loader is looking in the wrong place")
    for p in files:
        if p.read_text(encoding="utf-8") != content.dump(content.read(p)):
            fail(f"{p.relative_to(ROOT)} is not in the house layout -- load and "
                 f"content.write() it")
    for py in (ROOT / "tools").glob("*.py"):
        if re.search(r'^\s*line\(\s*"(tucker|pilot|solo|dub)"', py.read_text(encoding="utf-8"), re.M):
            fail(f"{py.name} has tape lines written in it; the writing belongs in content/")

    # --- the tapes the Lua issues exist, and are held back from the shelf ----
    import gen_tapes
    by_id = {t["id"]: t for t in gen_tapes.TAPES}
    cfg = (ROOT / "TrekShuttle/42/media/lua/shared/TREK/TREK_Config.lua").read_text(
        encoding="utf-8")
    frag = re.search(r"C\.FragmentTapes = \{(.*?)\}", cfg, re.S)
    ensign = re.search(r'C\.EnsignTape = "(\w+)"', cfg)
    issued = re.findall(r'"(TREK_\w+)"', frag.group(1)) if frag else []
    if ensign:
        issued.append(ensign.group(1))
    if len(issued) != 7:
        fail(f"found {len(issued)} issued tape ids in TREK_Config.lua, not 7: the "
             f"pattern has stopped matching")
    for t in issued:
        if t not in by_id:
            fail(f"the Lua issues {t} and gen_tapes.py does not make it")
        elif not by_id[t].get("issued"):
            fail(f"{t} is issued by the story and also stocked on the shelf "
                 f"from the first build -- a fragment on day one gives the chain away")

    captain_checks()

    if failures:
        print(f"{len(failures)} PROBLEM(S):")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    nodes = sum(len(t["nodes"]) for t in gen_comms.THREADS)
    print(f"comms: 14 broken trees refused for the right reason; the mod's "
          f"{len(gen_comms.THREADS)} threads and {nodes} nodes pass and match "
          f"what is on disk; {len(used)} keys all have text; the system flags agree")
    print(f"captain: {CAPTAIN_REFUSALS} broken trees refused for the right reason; her "
          f"{len(CAPT_TOPICS)} topics pass, gate their spoilers and match what is on disk; "
          f"her conditions agree with TREK_Captain.lua")


# ---------------------------------------------------------------------------
# Captain Titus (CAPTAIN.md, tools/gen_captain.py)
# ---------------------------------------------------------------------------
import gen_captain  # noqa: E402

CAPT_HUB, CAPT_TOPICS = gen_captain.load()
CAPTAIN_REFUSALS = 0


def capt_good():
    """A hub and one topic that pass, to be broken one way at a time."""
    def ln(t, voice="captain"):
        return {"voice": voice, "text": t}

    def arm(go, requires=(), forbids=()):
        return {"go": go if isinstance(go, list) else [go],
                "requires": list(requires), "forbids": list(forbids)}

    def nd(nid, lines, options=(), tier=None, mark=(), promote=False):
        return {"id": nid, "tier": tier, "lines": lines, "options": list(options),
                "mark": list(mark), "promote": promote}

    def op(text, go, requires=(), forbids=(), mark=()):
        return {"text": text, "go": go, "requires": list(requires),
                "forbids": list(forbids), "mark": list(mark)}

    hub = {"id": "HUB", "order": 0, "title": "", "requires": [], "forbids": [], "tiers": [],
           "entry": [arm("HELLO")], "home": [arm("HELLO")], "bye": [arm("GOODBYE")],
           "nodes": [nd("HELLO", [ln("Hello.")], mark=["introduced"]),
                     nd("GOODBYE", [ln("Goodbye.")])]}
    topic = {"id": "T", "order": 1, "title": "A topic", "requires": [], "forbids": [],
             "tiers": [{"id": "1", "requires": [], "forbids": []},
                       {"id": "T", "requires": ["truth"], "forbids": []}],
             "entry": [arm("01")], "home": [], "bye": [],
             "nodes": [nd("01", [ln("Ask, %1.")], tier="1",
                          options=[op("Tell me.", "02"), op("Who?", "HUB"),
                                   op("Only if introduced.", "02", requires=["me:introduced"])]),
                       nd("02", [ln("A Changeling.")], tier="T")]}
    return hub, [topic]


def capt_refused(hub, topics, why, label):
    global CAPTAIN_REFUSALS
    try:
        gen_captain.validate(hub, topics, TAPES)
    except gen_captain.Refused as exc:
        if why not in str(exc):
            fail(f"captain, {label}: refused, but not for '{why}': {exc}")
        else:
            CAPTAIN_REFUSALS += 1
        return
    fail(f"captain, {label}: the generator wrote a tree that should have been refused")


def captain_checks():
    try:
        gen_captain.validate(*capt_good(), TAPES)
    except gen_captain.Refused as exc:
        fail(f"captain: the good tree is refused: {exc}")

    def broken(fn, why, label):
        hub, topics = capt_good()
        fn(hub, topics)
        capt_refused(hub, topics, why, label)

    # The spoiler gate: the one mistake that gives the story away.
    broken(lambda h, t: t[0]["tiers"][1].update(requires=[]),
           "does not wait on 'truth'", "the Changeling named in an ungated tier")
    broken(lambda h, t: t[0]["nodes"][0]["options"].append(
               {"text": "Was it Tucker?", "go": "02", "requires": [], "forbids": [], "mark": []}),
           "does not wait on 'goldDone'", "Tucker Gold named in an option")
    broken(lambda h, t: t[0]["nodes"][0]["options"][0].update(go="99"),
           "not a node of T", "an orphan go")
    broken(lambda h, t: t[0]["nodes"].append(
               {"id": "03", "tier": "1", "lines": [{"voice": "captain", "text": "Alone."}],
                "options": [], "mark": [], "promote": False}),
           "cannot be reached", "a node nobody reaches")
    broken(lambda h, t: t[0]["nodes"][0].update(tier=None),
           "needs a tier", "a topic node with no tier")
    broken(lambda h, t: t[0]["nodes"][0].update(tier="9"),
           "is not one T declares", "a tier the topic does not declare")
    broken(lambda h, t: t[0]["nodes"][0]["options"][0].update(requires=["nothingSetsThis"]),
           "neither she nor the channel knows", "a condition nobody answers")
    broken(lambda h, t: t[0]["nodes"][0]["options"][2].update(requires=["me:neverMarked"]),
           "which no node or option marks", "a mark nothing sets")
    broken(lambda h, t: t[0].update(title="An extremely long topic title for a button"),
           "over 32", "a title too wide for its button")
    broken(lambda h, t: t[0]["nodes"][0]["options"][0].update(text="Tell me \u2014 now."),
           "must be ASCII", "an option that will not upper-case")
    broken(lambda h, t: t[0]["nodes"][0]["lines"][0].update(text="Ask, %3."),
           "is not one she may use", "her line using your name token")
    broken(lambda h, t: t[0]["nodes"][0]["options"][0].update(text="Tell me, %1."),
           "is hers, not yours", "your option using her token")
    broken(lambda h, t: h["bye"][0].update(requires=["truth"]),
           "must be unconditional", "a goodbye that can fail")
    broken(lambda h, t: h["nodes"][1].update(id="BYE"),
           "not node ids", "a node named like a target")
    broken(lambda h, t: t[0]["nodes"][0]["lines"][0].update(text="x" * 71),
           "over 70", "a line too long for the panel")

    # What is on disk is what the generator writes now.
    try:
        gen_captain.validate(CAPT_HUB, CAPT_TOPICS, TAPES)
    except gen_captain.Refused as exc:
        fail(f"captain: the mod's own tree is refused: {exc}")
        return
    if len(CAPT_TOPICS) < 10:
        fail(f"captain: only {len(CAPT_TOPICS)} topics came out of content/captain")

    def capt(path):
        return {k: v for k, v in json.loads(path.read_text(encoding="utf-8")).items()
                if k.startswith(gen_captain.PREFIX)}

    real_lua, real_js = gen_captain.outputs(ROOT / "TrekShuttle/42")
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp)
        (base / "media/lua/shared/TREK").mkdir(parents=True)
        (base / "media/lua/shared/Translate/EN").mkdir(parents=True)
        lua, js = gen_captain.outputs(base)
        gen_captain.write_lua(lua, CAPT_HUB, CAPT_TOPICS)
        gen_captain.write_text(js, gen_captain.build(CAPT_HUB, CAPT_TOPICS))
        if lua.read_text(encoding="utf-8") != real_lua.read_text(encoding="utf-8"):
            fail("captain: TREK_CaptainTree.lua is not what tools/gen_captain.py writes now -- run it")
        if capt(js) != capt(real_js):
            fail("captain: Print_Text.json is not what tools/gen_captain.py writes now -- run it")
    tree = real_lua.read_text(encoding="utf-8")
    text = capt(real_js)
    used = set(re.findall(r'"(Print_Text_TREK_CAPT_[A-Za-z0-9_]+)"', tree))
    if len(used) < 200 or len(text) < 200:
        fail(f"captain: only {len(used)} keys in the tree and {len(text)} in the text: "
             f"the pattern has stopped matching")
    for k in sorted(used - set(text)):
        fail(f"captain: the tree names {k} and Print_Text.json has no text for it")
    for k in sorted(set(text) - used):
        fail(f"captain: Print_Text.json has {k} and her tree never names it")

    # The conditions the generator trusts are the ones TREK_Captain.check answers.
    code = (ROOT / "TrekShuttle/42/media/lua/shared/TREK/TREK_Captain.lua").read_text(encoding="utf-8")
    answered = set(re.findall(r'cond == "(\w+)"', code))
    answered |= {m + ">=" for m in re.findall(r'cond:match\("\^(\w+)>=', code)}
    want = set()
    for p in gen_captain.CAPTAIN_DYNAMIC:
        m = re.match(r"^\^(\w+)", p.pattern)
        want.add(m.group(1) + (">=" if ">=" in p.pattern else ""))
    if len(want) < 6 or len(answered) < 6:
        fail(f"captain: {len(want)} conditions in the generator and {len(answered)} in the "
             f"Lua: the pattern has stopped matching")
    for c in sorted(want - answered):
        fail(f"captain: gen_captain.py trusts TREK_Captain.check to answer '{c}' and it does not")
    for c in sorted(answered - want):
        fail(f"captain: TREK_Captain.check answers '{c}' and the generator does not know it")


if __name__ == "__main__":
    main()
