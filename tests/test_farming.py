"""Hydroponics, statically (FARMING.md): every recipe names items that exist,
every crop names items and sprites that exist, and every name has its text.

    python tests/test_farming.py

The farming loop itself runs in tests/test_multiplayer.py (farming()); this
is the part that no simulation can check -- that a script line refers to
something the game will actually find.
"""
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "TrekShuttle", "42", "media")
PZ = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media"
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_adirondack_pack as PACK  # noqa: E402

failures = []


def fail(msg):
    failures.append(msg)


vanilla = set(json.load(open(os.path.join(ROOT, "tools", "_catalog", "items.json")))["Base"])
scripts = "".join(open(p, encoding="utf-8").read() for p in glob.glob(os.path.join(MOD, "scripts", "*.txt")))
mod_items = set(re.findall(r"^\s*item\s+([A-Za-z0-9_]+)\s*$", scripts, re.M))
farm = open(os.path.join(MOD, "scripts", "trekfarming.txt"), encoding="utf-8").read()
vanilla_scripts = "".join(open(p, encoding="utf-8", errors="ignore").read()
                          for p in glob.glob(os.path.join(PZ, "scripts", "**", "*.txt"), recursive=True))


def resolves(full):
    mod, _, name = full.partition(".")
    if mod == "TrekShuttle":
        return name in mod_items
    if mod == "Base":
        return name in vanilla
    return False


# --- every item a recipe names --------------------------------------------------------
recipes = re.findall(r"craftRecipe\s+(\w+)\s*\{(.*?)\n    \}", farm, re.S)
if len(recipes) < 15:
    fail("only %d recipes found in trekfarming.txt: the pattern has stopped matching" % len(recipes))
for name, body in recipes:
    for group in re.findall(r"\[([^\]]+)\]", body):
        for full in group.split(";"):
            full = full.strip()
            if "." in full and not full.startswith("base:") and not resolves(full):
                fail("%s names %s, which is no item" % (name, full))
    for full in re.findall(r"item \S+ ([A-Za-z]+\.[A-Za-z0-9_]+)", body):
        if not resolves(full):
            fail("%s makes %s, which is no item" % (name, full))
    for tag in re.findall(r"tags\[([^\]]+)\]", body):
        for t in tag.split(";"):
            if t not in vanilla_scripts:
                fail("%s wants tag %s, which no vanilla item carries" % (name, t))
# Every OnCreate a recipe names is a function somewhere in the mod's Lua.
all_lua = "".join(open(p, encoding="utf-8").read()
                  for p in glob.glob(os.path.join(MOD, "lua", "**", "*.lua"), recursive=True))
for fn in set(re.findall(r"OnCreate = (\w+)", farm)):
    if not re.search(r"function %s\(" % fn, all_lua):
        fail("a recipe calls OnCreate %s, and no Lua defines it" % fn)
recipe_text = json.load(open(os.path.join(MOD, "lua", "shared", "Translate", "EN", "Recipes.json"), encoding="utf-8"))
for name, _ in recipes:
    if name not in recipe_text:
        fail("Recipes.json has no name for %s" % name)

# --- every crop ------------------------------------------------------------------------
lua = open(os.path.join(MOD, "lua", "shared", "TREK", "TREK_FarmCrops.lua"), encoding="utf-8").read()
crop_rows = re.findall(r"(Trek\w+) = \{ seed = \"([\w.]+)\",[^}]*?veg = \"([\w.]+)\"", lua, re.S)
if len(crop_rows) != 7:
    fail("expected 7 crops in TREK_Farm.lua, found %d" % len(crop_rows))
farming_text = json.load(open(os.path.join(MOD, "lua", "shared", "Translate", "EN", "Farming.json"), encoding="utf-8"))
for crop, seed, veg in crop_rows:
    for full in (seed, veg):
        if not resolves(full):
            fail("crop %s names %s, which is no item" % (crop, full))
    if "Farming_" + crop not in farming_text:
        fail("Farming.json has no name for %s" % crop)

# --- every sprite a crop grows through is in the pack -----------------------------------
sprites_lua = open(os.path.join(MOD, "lua", "shared", "TREK", "TREK_FarmSprites.lua"), encoding="utf-8").read()
names = set(re.findall(r'"(trek_adirondack_03_\d+)"', sprites_lua))
drawn = {e[0] for pg in PACK.read_pack(PACK.PACK) for e in pg["entries"]}
missing = sorted(n for n in names if n not in drawn)
if len(names) < 7 * 8:
    fail("only %d crop sprites named" % len(names))
if missing:
    fail("crop sprites with no picture in the pack: %s" % ", ".join(missing[:8]))
for crop, _, _ in crop_rows:
    block = re.search(r"%s = \{(.*?)\n    \}," % crop, sprites_lua, re.S)
    if not block:
        fail("TREK_FarmSprites.lua has no tables for %s" % crop)
        continue
    for table in ("sprite", "unhealthy", "dying", "dead", "trampled"):
        row = re.search(r"%s = \{([^}]*)\}" % table, block.group(1))
        if not row or len(re.findall(r'"', row.group(1))) != 16:
            fail("%s's %s table is not eight sprites long" % (crop, table))

if failures:
    print("%d PROBLEM(S):" % len(failures))
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("farming: %d recipes name only real items and tags, 7 crops name real seeds, produce and "
      "%d sprites, and every name has its text" % (len(recipes), len(names)))
