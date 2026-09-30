"""Every tile the mod places, vanilla's and ours, by sprite name.

    import tilecatalog
    props = tilecatalog.tiles()["trek_adirondack_02_207"]

tools/_catalog/tiles.json is vanilla's tileset (tools/pzcatalog.py build).
The shuttle's cabin is built from the Adirondack's sheets as well since the
Starfleet refit (INTERIOR_REFIT.md), and a check that looked only at vanilla
would find every one of those sprites missing -- or worse, find nothing and
pass. So this reads the mod's own tiledef, the file the game loads
(TrekShuttle/42/media/trek_adirondack.tiles, written by
tools/gen_adirondack_pack.py), with the reader that parses vanilla's
newtiledefinitions.tiles end to end, and puts both in one table.

Names are the engine's, unpadded (`trek_adirondack_02_207`, never `_207` with
zeros -- BuildingEd pads, the engine does not).
"""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VANILLA = os.path.join(ROOT, "tools", "_catalog", "tiles.json")
OURS = os.path.join(ROOT, "TrekShuttle", "42", "media", "trek_adirondack.tiles")

_cache = None


def ours():
    """The mod's own tiles: sprite -> properties."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import gen_adirondack_pack as P
    out = {}
    for sheet, ts in P.read_tiledefs(OURS).items():
        for i, props in enumerate(ts["tiles"]):
            if props:
                out["%s_%d" % (sheet, i)] = dict(props)
    if len(out) < 100:
        raise SystemExit("tilecatalog: only %d tiles read out of %s -- the reader "
                         "has stopped matching" % (len(out), OURS))
    return out


def tiles():
    global _cache
    if _cache is None:
        with open(VANILLA, encoding="utf-8") as f:
            _cache = dict(json.load(f)["tiles"])
        _cache.update(ours())
    return _cache
