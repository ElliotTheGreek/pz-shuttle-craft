"""The vocabulary the Adirondack channel is written in (tools/gen_comms.py).

tools/content.py builds threads from content/comms/ with it, and the generator's
own tests (tests/test_comms.py) write small broken trees in it.
"""


def say(voice, text):
    return {"voice": voice, "text": text}


def opt(text, go, requires=(), forbids=(), sets=(), clears=()):
    return {"text": text, "go": go, "requires": list(requires),
            "forbids": list(forbids), "sets": list(sets), "clears": list(clears)}


def branch(go, requires=(), forbids=()):
    """One arm of a route: an invisible node that goes to the first arm whose
    conditions hold. The last arm must have none."""
    return {"go": go, "requires": list(requires), "forbids": list(forbids)}


def node(nid, *lines, options=(), timeout=None, silence=None, route=None,
         sets=(), clears=(), issue=(), convert=False):
    return {"id": nid, "lines": list(lines), "options": list(options),
            "timeout": timeout, "silence": silence, "route": route,
            "sets": list(sets), "clears": list(clears), "issue": list(issue),
            "convert": convert}


def thread(tid, title, kind, nodes, entries=None, day=None, after=None,
           requires=(), forbids=(), retry=True, repeatable=False,
           cooldown=None):
    """kind: "incoming" (the ship rings) or "hail" (a player calls her).

    entries: the node a call opens on after 0, 1, 2 ... misses; the last one
    repeats. A missed call is not re-run from the top -- it comes back worse.
    after: (thread, hours) -- not before that thread has run and this long
    has passed.
    retry: a missed incoming call rings again. False for the ones whose
    consequence is that you missed them.
    repeatable: fires again whenever its conditions hold again (it should
    clear the flag it waits on, or it will ring for ever).
    """
    return {"id": tid, "title": title, "kind": kind, "nodes": nodes,
            "entries": entries or [nodes[0]["id"]], "day": day, "after": after,
            "requires": list(requires), "forbids": list(forbids),
            "retry": retry, "repeatable": repeatable, "cooldown": cooldown}


