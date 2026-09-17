"""Static checks against the live build 42 data.

Catches the failure mode that costs the most time in game: a sprite or item id
that looks plausible, silently resolves to nothing, and leaves the cabin
half-dressed with no error anywhere in the log.

    python tests/test_assets.py
"""
import json, re, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "tools", "_catalog")
MOD = os.path.join(ROOT, "TrekShuttle", "42")
PZ = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media"

tiles = set(json.load(open(os.path.join(CATALOG, "tiles.json")))["tiles"])
items = set(json.load(open(os.path.join(CATALOG, "items.json")))["Base"])

# a tile sprite looks like  some_tileset_name_01_42
SPRITE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*_\d+$")
ITEM = re.compile(r"^Base\.([A-Za-z0-9_]+)$")
MOD_ITEM = re.compile(r"^TrekShuttle\.([A-Za-z0-9_]+)$")

# The mod's own items, declared in media/scripts/trekshuttle.txt. A Lua
# reference to one that is not declared there resolves to nothing, exactly as
# silently as a bad Base id does.
script = open(os.path.join(MOD, "media", "scripts", "trekshuttle.txt"),
              encoding="utf-8").read()
mod_items = set(re.findall(r"^\s*item\s+([A-Za-z0-9_]+)", script, re.M))
mod_models = set(re.findall(r"^\s*model\s+([A-Za-z0-9_]+)", script, re.M))
mod_icons = set(re.findall(r"^\s*Icon\s*=\s*([A-Za-z0-9_]+)\s*,", script, re.M))

failures, checked_sprites, checked_items = [], 0, 0

# --- the mod's own meshes and textures ---------------------------------
# A model naming a mesh that is not on disk loads as nothing and draws as
# nothing, with no error.
for block in re.finditer(r"model\s+\w+\s*\{(.*?)\}", script, re.S):
    body = block.group(1)
    mesh = re.search(r"mesh\s*=\s*([\w/]+)\s*,", body)
    tex = re.search(r"texture\s*=\s*([\w/]+)\s*,", body)
    if mesh and not os.path.exists(
            os.path.join(MOD, "media", "models_X", mesh.group(1) + ".x")):
        failures.append(f"model mesh {mesh.group(1)}.x is not in media/models_X")
    if tex and not os.path.exists(
            os.path.join(MOD, "media", "textures", tex.group(1) + ".png")):
        failures.append(f"model texture {tex.group(1)}.png is not in media/textures")

# Every icon a mod item names has to exist as a file. A missing one shows as a
# blank square in the inventory and reports nothing anywhere.
for icon in sorted(mod_icons):
    candidates = [os.path.join(MOD, "media", "textures", f"Item_{icon}.png"),
                  os.path.join(MOD, "media", "ui", f"{icon}.png")]
    if not any(os.path.exists(p) for p in candidates):
        failures.append(f"trekshuttle.txt: Icon = {icon} has no texture; "
                        f"expected media/textures/Item_{icon}.png")

# --- the phaser's borrowed vanilla references --------------------------
# The phaser leans on vanilla for its AmmoType, its in-hand model and its
# sounds, all of which resolve in Java rather than through any script the mod
# ships. A typo in one of them is silent, so they are checked against the
# game's own scripts here.
vanilla = ""
for dp, _, fns in os.walk(os.path.join(PZ, "scripts")):
    for fn in fns:
        if fn.endswith(".txt"):
            vanilla += open(os.path.join(dp, fn), encoding="utf-8",
                            errors="replace").read()

# Every WorldStaticModel / StaticModel must name a model: the mod's own, or a
# vanilla one it borrows. The galley food borrows vanilla bowls and bars, and a
# borrowed name that is misspelt draws nothing, silently.
vanilla_models = set(re.findall(r"^\s*model\s+([A-Za-z0-9_]+)\s*$", vanilla, re.M))
for ref in re.findall(r"^\s*(?:World)?StaticModel\s*=\s*([A-Za-z0-9_]+)\s*,",
                      script, re.M):
    if ref not in mod_models and ref not in vanilla_models:
        failures.append(f"trekshuttle.txt: StaticModel = {ref} is neither a mod "
                        f"model nor a vanilla one")

# ReplaceOnUse hands the player an item back -- the empty bowl. A bad id means
# the bowl simply vanishes when the food is eaten.
for ref in re.findall(r"^\s*ReplaceOnUse\s*=\s*Base\.([A-Za-z0-9_]+)\s*,", script, re.M):
    if ref not in items:
        failures.append(f"trekshuttle.txt: ReplaceOnUse = Base.{ref} is not a vanilla item")

phaser = re.search(r"item TrekPhaser\s*\{(.*?)\n    \}", script, re.S)
if not phaser:
    failures.append("trekshuttle.txt: the TrekPhaser item block was not found")
else:
    body = phaser.group(1)
    ammo = re.search(r"AmmoType\s*=\s*([\w:]+)\s*,", body)
    if ammo and f"AmmoType = {ammo.group(1)}," not in vanilla:
        failures.append(f"phaser AmmoType {ammo.group(1)} is not used by any "
                        f"vanilla weapon, so it probably does not resolve")
    sprite = re.search(r"WeaponSprite\s*=\s*(\w+)\s*,", body)
    if sprite and not re.search(r"model\s+%s\s*\n?\s*\{" % sprite.group(1),
                                vanilla):
        failures.append(f"phaser WeaponSprite {sprite.group(1)} is not a "
                        f"vanilla weapon model")
    for key in ("SwingAnim", "RunAnim"):
        if not re.search(key + r"\s*=", body):
            failures.append(f"phaser has no {key}; it will not animate")

# --- every literal in the Lua ------------------------------------------
for dp, _, fns in os.walk(os.path.join(MOD, "media", "lua")):
    for fn in fns:
        if not fn.endswith(".lua"):
            continue
        path = os.path.join(dp, fn)
        for lineno, ln in enumerate(open(path, encoding="utf-8"), 1):
            if ln.strip().startswith("--"):
                continue
            for lit in re.findall(r'"([^"]+)"', ln):
                m = ITEM.match(lit)
                if m:
                    checked_items += 1
                    if m.group(1) not in items:
                        failures.append(f"{fn}:{lineno} unknown item {lit}")
                    continue
                m = MOD_ITEM.match(lit)
                if m:
                    checked_items += 1
                    if m.group(1) not in mod_items:
                        failures.append(f"{fn}:{lineno} {lit} is not declared "
                                        f"in media/scripts/trekshuttle.txt")
                    continue
                if SPRITE.match(lit) and not lit.startswith("Base"):
                    checked_sprites += 1
                    if lit not in tiles:
                        failures.append(f"{fn}:{lineno} unknown sprite {lit}")

# --- UI textures -------------------------------------------------------
# A getTexture on a file that is not there returns nil, and the helm then
# quietly draws flat rectangles instead of its artwork. Every media/ui file the
# Lua names -- directly or through the helm's load("key", "FILE.png") -- must
# exist.
UI = os.path.join(MOD, "media", "ui")
ui_named = set()
for dp, _, fns in os.walk(os.path.join(MOD, "media", "lua")):
    for fn in fns:
        if fn.endswith(".lua"):
            body = open(os.path.join(dp, fn), encoding="utf-8").read()
            ui_named |= set(re.findall(r'media/ui/([\w.]+\.png)', body))
            ui_named |= set(re.findall(r'load\(\s*"\w+"\s*,\s*"([\w.]+\.png)"', body))
for f in sorted(ui_named):
    if not os.path.isfile(os.path.join(UI, f)):
        failures.append(f"Lua names media/ui/{f}, which does not exist")

# --- translations ------------------------------------------------------
# Build 42 reads media/lua/shared/Translate/EN/<Category>.json and the category
# is part of the *path*, not the key: an "ItemName_x" key inside IG_UI.json
# resolves to nothing at all, silently. Every getText the Lua asks for has to
# be in IG_UI.json, and every mod item wants a name in ItemName.json.
TR = os.path.join(MOD, "media", "lua", "shared", "Translate", "EN")
ig = json.load(open(os.path.join(TR, "IG_UI.json"), encoding="utf-8"))
names = json.load(open(os.path.join(TR, "ItemName.json"), encoding="utf-8"))
tips = json.load(open(os.path.join(TR, "Tooltip.json"), encoding="utf-8"))

# UI.json only overrides vanilla strings -- the intro's "THIS IS HOW YOU DIED"
# becomes "THIS WAS YOUR AWAY MISSION". An override whose key vanilla does not
# have changes nothing and reports nothing, so every key must exist in the
# game's own UI.json.
ui_override = os.path.join(TR, "UI.json")
if os.path.isfile(ui_override):
    vanilla_ui = json.load(open(os.path.join(PZ, "lua", "shared", "Translate", "EN", "UI.json"),
                                encoding="utf-8"))
    for key in json.load(open(ui_override, encoding="utf-8")):
        if key not in vanilla_ui:
            failures.append(f"UI.json overrides {key}, which vanilla does not have")

for key in ig:
    if not key.startswith("IGUI_"):
        failures.append(f"IG_UI.json holds {key}, which is not an IGUI_ key")
asked = set()
for dp, _, fns in os.walk(os.path.join(MOD, "media", "lua")):
    for fn in fns:
        if fn.endswith(".lua"):
            body = open(os.path.join(dp, fn), encoding="utf-8").read()
            asked |= set(re.findall(r'getText\(\s*"([^"]+)"', body))
            # Keys are not always the first argument of getText: the helm picks
            # one with `up and "A" or "B"` and hands others to a helper. Any
            # IGUI_TREK_ literal anywhere in the Lua is a key it will ask for.
            asked |= set(re.findall(r'"(IGUI_TREK_[A-Za-z0-9_]+)"', body))
for key in sorted(asked):
    if key.startswith("IGUI_") and key not in ig:
        failures.append(f"getText(\"{key}\") has no entry in IG_UI.json")
for item in sorted(mod_items):
    if f"TrekShuttle.{item}" not in names:
        failures.append(f"ItemName.json has no name for TrekShuttle.{item}")
for tip in sorted(re.findall(r"^\s*Tooltip\s*=\s*(\w+)\s*,", script, re.M)):
    if tip not in tips:
        failures.append(f"Tooltip.json has no entry for {tip}")

# --- the void map ------------------------------------------------------
# Empty map cells around the interior cell keep the world generator out, so
# the space outside the cabin is black. Each file is read back in the build 42
# format tools/gen_void_map.py writes; a malformed lot fails to load in game
# and the wilderness comes back, silently.
import struct
cfg = open(os.path.join(MOD, "media", "lua", "shared", "TREK", "TREK_Config.lua"),
           encoding="utf-8").read()
cell = re.search(r"C\.InteriorCell\s*=\s*\{\s*x\s*=\s*(\d+),\s*y\s*=\s*(\d+)", cfg)
void = re.search(r'C\.VoidMap\s*=\s*"([^"]+)"', cfg)
if not cell or not void:
    failures.append("TREK_Config.lua: C.InteriorCell or C.VoidMap not found")
else:
    cx, cy = int(cell.group(1)), int(cell.group(2))
    mapdir = os.path.join(MOD, "media", "maps", void.group(1))
    info = os.path.join(mapdir, "map.info")
    if not os.path.isfile(info):
        failures.append(f"media/maps/{void.group(1)}/map.info is missing "
                        f"(python tools/gen_void_map.py)")
    elif "lots=Muldraugh, KY" not in open(info, encoding="utf-8").read():
        failures.append("the void map's map.info does not group it with Muldraugh, KY")
    for dx in (-1, 0, 1):
        for dy in (-1, 0, 1):
            x, y = cx + dx, cy + dy
            try:
                h = open(os.path.join(mapdir, f"{x}_{y}.lotheader"), "rb").read()
                p = open(os.path.join(mapdir, f"world_{x}_{y}.lotpack"), "rb").read()
                c = open(os.path.join(mapdir, f"chunkdata_{x}_{y}.bin"), "rb").read()
            except OSError:
                failures.append(f"void map cell {x},{y} is missing a file")
                continue
            ok = (h[:4] == b"LOTH" and struct.unpack_from("<ii", h, 4) == (1, 1)
                  and len(h) == 12 + len(b"invisible_01_0\n") + 24 + 1024
                  and p[:4] == b"LOTP" and struct.unpack_from("<ii", p, 4) == (1, 1024)
                  and len(p) == 12 + 8 * 1024 + 8 * 1024
                  and struct.unpack_from("<q", p, 12)[0] == 12 + 8 * 1024
                  and struct.unpack_from("<ii", p, 12 + 8 * 1024) == (-1, 64)
                  and c == b"\x00\x01" + bytes(1024))
            if not ok:
                failures.append(f"void map cell {x},{y} is not a well-formed empty cell")

print(f"checked {checked_sprites} sprite names and {checked_items} item ids, "
      f"{len(mod_items)} mod items, {len(mod_models)} models, "
      f"{len(mod_icons)} icons and {len(asked)} translation keys")
if failures:
    print(f"\n{len(failures)} PROBLEM(S):")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("all asset references resolve")
