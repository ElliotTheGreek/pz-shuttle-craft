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
        for rel in ("media/lua/shared/TREK/TREK_CommsTree.lua",
                    "media/lua/shared/Translate/EN/Print_Text.json"):
            want = (base / rel).read_text(encoding="utf-8")
            have = (ROOT / "TrekShuttle/42" / rel).read_text(encoding="utf-8")
            if want != have:
                fail(f"{rel} is not what tools/gen_comms.py writes now -- run it")

    # --- every key the tree names has text, and nothing is orphaned ---------
    lua = (ROOT / "TrekShuttle/42/media/lua/shared/TREK/TREK_CommsTree.lua").read_text(
        encoding="utf-8")
    text = json.loads((ROOT / "TrekShuttle/42/media/lua/shared/Translate/EN/"
                                "Print_Text.json").read_text(encoding="utf-8"))
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

    if failures:
        print(f"{len(failures)} PROBLEM(S):")
        for f in failures:
            print("  " + f)
        sys.exit(1)
    nodes = sum(len(t["nodes"]) for t in gen_comms.THREADS)
    print(f"comms: 14 broken trees refused for the right reason; the mod's "
          f"{len(gen_comms.THREADS)} threads and {nodes} nodes pass and match "
          f"what is on disk; {len(used)} keys all have text; the system flags agree")


if __name__ == "__main__":
    main()
