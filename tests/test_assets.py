"""Static checks against the live build 42 data.

Catches the failure mode that costs the most time in game: a sprite or item id
that looks plausible, silently resolves to nothing, and leaves the cabin
half-dressed with no error anywhere in the log.

    python tests/test_assets.py
"""
import glob, json, re, struct, sys, os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CATALOG = os.path.join(ROOT, "tools", "_catalog")
MOD = os.path.join(ROOT, "TrekShuttle", "42")
PZ = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media"

tiles = set(json.load(open(os.path.join(CATALOG, "tiles.json")))["tiles"])
items = set(json.load(open(os.path.join(CATALOG, "items.json")))["Base"])

# The mod's own tiles (the Adirondack's): known when the tiledef defines them
# **and** the texture pack has a picture for them **and** mod.info loads both.
# A sprite with properties and no picture draws nothing; one with a picture
# and no properties is a decal; a pack mod.info does not name is never read.
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_adirondack_pack as _PACK  # noqa: E402
_info = open(os.path.join(MOD, "mod.info"), encoding="utf-8").read()
mod_tile_problems = []
for _tiles in glob.glob(os.path.join(MOD, "media", "*.tiles")):
    _name = os.path.splitext(os.path.basename(_tiles))[0]
    _pack = os.path.join(MOD, "media", "texturepacks", _name + ".pack")
    if not re.search(r"^tiledef=%s \d+\s*$" % re.escape(_name), _info, re.M):
        mod_tile_problems.append("mod.info has no tiledef= line for %s.tiles" % _name)
    if not os.path.isfile(_pack) or not re.search(r"^pack=%s\s*$" % re.escape(_name), _info, re.M):
        mod_tile_problems.append("%s.tiles has no texture pack loaded by mod.info" % _name)
        continue
    _drawn = {e[0] for pg in _PACK.read_pack(_pack) for e in pg["entries"]}
    for _sheet, _ts in _PACK.read_tiledefs(_tiles).items():
        for _i, _props in enumerate(_ts["tiles"]):
            _sprite = "%s_%d" % (_sheet, _i)
            if _props and _sprite in _drawn:
                tiles.add(_sprite)
            elif _props or _sprite in _drawn:
                mod_tile_problems.append("%s: %s" % (_sprite, "no picture" if _props else "no properties"))

# a tile sprite looks like  some_tileset_name_01_42
SPRITE = re.compile(r"^[a-z][a-z0-9]*(?:_[a-z0-9]+)*_\d+$")
ITEM = re.compile(r"^Base\.([A-Za-z0-9_]+)$")
MOD_ITEM = re.compile(r"^TrekShuttle\.([A-Za-z0-9_]+)$")

# The mod's own items, declared in media/scripts/trekshuttle.txt. A Lua
# reference to one that is not declared there resolves to nothing, exactly as
# silently as a bad Base id does.
# Both item/model script files, concatenated. trekweapons.txt exists because
# weapon models have to be declared in `module Base` -- WeaponSprite does not
# resolve within the mod's own module the way StaticModel does -- and no
# vanilla file declares two modules, so it could not simply live in the other
# file. Anything checking "does this name resolve" has to see both or it will
# report a model that is really there as missing.
script = "".join(
    open(os.path.join(MOD, "media", "scripts", fn), encoding="utf-8").read()
    for fn in ("trekshuttle.txt", "trekweapons.txt", "trekfarming.txt")
    if os.path.isfile(os.path.join(MOD, "media", "scripts", fn)))
# Anchored to the end of the line, as the model and fluid patterns are: a real
# declaration is "item Foo" and nothing else, so prose in a comment that
# happens to say "item blocks" is not mistaken for one.
mod_items = set(re.findall(r"^\s*item\s+([A-Za-z0-9_]+)\s*$", script, re.M))
mod_models = set(re.findall(r"^\s*model\s+([A-Za-z0-9_]+)", script, re.M))
mod_icons = set(re.findall(r"^\s*Icon\s*=\s*([A-Za-z0-9_]+)\s*,", script, re.M))

# Somewhere to sit: every chair, sofa and bed of ours has a seating entry,
# in common/media -- the only folder SeatingManager.init() reads a mod's from.
_seating = os.path.join(ROOT, "TrekShuttle", "common", "media", "seating.txt")
if os.path.isdir(os.path.join(MOD, "media")) and glob.glob(os.path.join(MOD, "media", "*.tiles")):
    if not os.path.isfile(_seating):
        mod_tile_problems.append("no common/media/seating.txt: every chair sits you on the floor beside it")
    else:
        _seats = _PACK.vanilla_seats(_seating).get("trek_adirondack_02", {})
        _index = json.load(open(os.path.join(ROOT, "design", "tiles", "trek_adirondack_02.json")))
        for _piece, _rec in _index.items():
            _use = _rec.get("use", {})
            if _use.get("seat") or "bed" in _use:
                for _sq in _rec["facings"].values():
                    for _x, _y, _i in _sq:
                        if _i not in _seats:
                            mod_tile_problems.append("seating.txt has no entry for %s (trek_adirondack_02_%d)" % (_piece, _i))
failures, checked_sprites, checked_items = list(mod_tile_problems), 0, 0

# The mod's vehicle scripts. "Base.TrekShuttleCraft" is a vehicle, not an item.
mod_vehicles = set()
for dp, _, fns in os.walk(os.path.join(MOD, "media", "scripts")):
    for fn in fns:
        if fn.endswith(".txt"):
            mod_vehicles |= set(re.findall(r"^\s*vehicle\s+(\w+)",
                                           open(os.path.join(dp, fn), encoding="utf-8").read(),
                                           re.M))

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
# An icon may also be *borrowed* from vanilla, the way the phaser borrows
# vanilla models -- which cannot be checked against the filesystem, because
# vanilla's item icons live inside media/texturepacks/*.pack and are not loose
# files. What is checkable is the name: a borrowed icon has to be one a vanilla
# item script actually declares. A typo'd borrow draws a blank square and
# reports nothing, exactly like a missing file.
VANILLA_ICONS = set()
for dp, _, fns in os.walk(os.path.join(PZ, "scripts")):
    for fn in fns:
        if fn.endswith(".txt"):
            VANILLA_ICONS |= set(re.findall(
                r"^\s*Icon\s*=\s*([A-Za-z0-9_]+)\s*,",
                open(os.path.join(dp, fn), encoding="utf-8", errors="replace").read(),
                re.M))
# Both sides of a lookup need a floor: an empty vanilla set would make every
# borrow "valid" for as long as the path stayed wrong.
if len(VANILLA_ICONS) < 200:
    failures.append(f"only {len(VANILLA_ICONS)} vanilla icon names were read out "
                    f"of the game's scripts, so the borrowed-icon check is not "
                    f"checking anything")
    VANILLA_ICONS = set()

for icon in sorted(mod_icons):
    candidates = [os.path.join(MOD, "media", "textures", f"Item_{icon}.png"),
                  os.path.join(MOD, "media", "ui", f"{icon}.png")]
    if icon in VANILLA_ICONS:
        continue
    if not any(os.path.exists(p) for p in candidates):
        failures.append(f"trekshuttle.txt: Icon = {icon} is neither the mod's own "
                        f"nor an icon any vanilla item declares; expected "
                        f"media/textures/Item_{icon}.png")



# --- the tape shelf ----------------------------------------------------
# A tape is two generated files that have to agree: the RecMedia table names
# translation keys and Recorded_Media.json holds the text. Both come out of
# tools/gen_tapes.py, so what this really checks is that the generator was run
# after the last edit -- and each failure below is a thing the player sees or
# silently does not get.
TAPES_LUA = os.path.join(MOD, "media", "lua", "shared", "TREK", "TREK_Tapes.lua")
TAPES_JSON = os.path.join(MOD, "media", "lua", "shared", "Translate", "EN",
                          "Recorded_Media.json")
if not os.path.isfile(TAPES_LUA):
    failures.append("TREK_Tapes.lua is missing; run tools/gen_tapes.py")
elif not os.path.isfile(TAPES_JSON):
    failures.append("Translate/EN/Recorded_Media.json is missing; run "
                    "tools/gen_tapes.py")
else:
    tapes_src = open(TAPES_LUA, encoding="utf-8").read()
    tape_text = json.load(open(TAPES_JSON, encoding="utf-8"))
    used = re.findall(r'"(RM_[A-Za-z0-9_]+)"', tapes_src)

    # Both sides need a floor, or an empty read makes everything agree.
    if len(used) < 10 or len(tape_text) < 10:
        failures.append(f"only {len(used)} tape keys and {len(tape_text)} strings "
                        f"were read, so the tape checks are not checking anything")
    else:
        # A key with no text prints itself on screen, in the subtitle, at size.
        for key in sorted(set(used)):
            if key not in tape_text:
                failures.append(f"tape key {key} has no text in "
                                f"Recorded_Media.json, so the key itself is what "
                                f"the player reads")
        for key in sorted(tape_text):
            if key not in used:
                failures.append(f"Recorded_Media.json has {key} and no tape uses "
                                f"it")

        # A line's identity for "has this player heard it" is its key, so two
        # lines sharing one make the second **inert** -- its codes never fire
        # again for that character. The generator derives keys so this cannot
        # happen; the check is here because the consequence is invisible.
        line_keys = re.findall(r'\{ text = "(RM_[A-Za-z0-9_]+)"', tapes_src)
        dupes = sorted({k for k in line_keys if line_keys.count(k) > 1})
        for key in dupes:
            failures.append(f"two tape lines share the key {key}; the second one "
                            f"is silently inert once the first has been heard")

        # Every code has to parse the way ISRadioInteractions parses it: a
        # three-letter name it knows, an operator, a number, and a token longer
        # than four characters. A typo is ignored by the engine in silence.
        INTERACT = os.path.join(PZ, "lua", "shared", "RadioCom",
                                "ISRadioInteractions.lua")
        known = set()
        if os.path.isfile(INTERACT):
            known = set(re.findall(r"^Interactions\.(\w{3})\s*=", 
                                   open(INTERACT, encoding="utf-8").read(), re.M))
        if len(known) < 20:
            failures.append(f"only {len(known)} line-effect codes were read out of "
                            f"the game's ISRadioInteractions.lua, so the code "
                            f"check is not checking anything")
        else:
            known.add("RCP")
            for codes in re.findall(r'codes = "([^"]*)"', tapes_src):
                for token in codes.split(","):
                    if len(token) <= 4:
                        failures.append(f"tape line code {token!r} is four "
                                        f"characters or fewer, and the engine "
                                        f"only parses longer tokens")
                        continue
                    name, op = token[:3], token[3]
                    if name not in known:
                        failures.append(f"tape line code {token!r} names {name}, "
                                        f"which ISRadioInteractions does not know")
                    elif op not in "+-=":
                        failures.append(f"tape line code {token!r} has no +, - or "
                                        f"= where the operator belongs")
                    elif name != "RCP":
                        try:
                            float(token[4:])
                        except ValueError:
                            failures.append(f"tape line code {token!r} has no "
                                            f"number after the operator")

        # A line's time on screen is proportional to its length
        # (DeviceData.updateMediaPlaying: length / 10 * 60, clamped), so a
        # paragraph is one subtitle that sits there for a very long time.
        long_lines = [(k, v) for k, v in tape_text.items()
                      if re.search(r"_\d\d$", k) and len(v) > 75]
        for key, value in sorted(long_lines):
            failures.append(f"tape line {key} is {len(value)} characters; it will "
                            f"sit on screen far too long ({value[:40]}...)")

    print(f"  tapes: {len(set(used))} keys, {len(tape_text)} strings")

# --- the wardrobe ------------------------------------------------------
# A clothing item is a chain of five joins and **every one of them fails
# without a word**:
#
#   item script  ClothingItem = X
#     -> media/clothing/clothingItems/X.xml        (missing: no visual)
#     -> a GUID row in media/fileGuidTable.xml     (missing: no visual)
#     -> m_MaleModel / m_FemaleModel                (missing: no visual)
#     -> textureChoices                             (missing: no visual)
#
# The middle one is the nastiest and is the reason this section exists.
# `OutfitManager.getClothingItem(guid)` calls `getFilePathFromGuid` and
# **returns null at bci 12** when the merged table does not know the id, and
# `ZomboidFileSystem.loadFileGuidTable` wraps each mod's table in a catch that
# only reaches ExceptionLogger. So a uniform whose GUID row is missing or
# malformed still equips, still weighs something, still insulates, still gets
# dirty -- and draws nothing at all. That is the same shape as the unopenable
# locker, the tap with no water and the weapon model one module away: present,
# drawn and inert. See DEV_GUIDE, "The jar is not the API".
CLOTHING_DIR = os.path.join(MOD, "media", "clothing", "clothingItems")
GUID_TABLE = os.path.join(MOD, "media", "fileGuidTable.xml")

mod_clothing = set(re.findall(r"^\s*ClothingItem\s*=\s*([A-Za-z0-9_]+)\s*,",
                              script, re.M))

# Everything the installed game ships, so a mod path or GUID cannot collide
# with one. `FileGuidTable.mergeFrom` is a plain ArrayList.addAll with no
# de-duplication at all, so a clash is resolved by whichever row is found
# first -- which is not a thing to leave to chance.
vanilla_guid_text = ""
_vg = os.path.join(PZ, "fileGuidTable.xml")
if os.path.isfile(_vg):
    vanilla_guid_text = open(_vg, encoding="utf-8", errors="replace").read()
vanilla_guids = {g.lower() for g in
                 re.findall(r"<guid>([^<]+)</guid>", vanilla_guid_text)}
vanilla_guid_paths = {p.strip().lower().replace("\\", "/") for p in
                      re.findall(r"<path>([^<]+)</path>", vanilla_guid_text)}

# Every mesh and texture the game ships, by lowercased extensionless relative
# path, because a clothing XML names them with backslashes, in any case, and
# without an extension.
def _index(root, exts):
    found = set()
    if not os.path.isdir(root):
        return found
    for dp, _, fns in os.walk(root):
        rel = os.path.relpath(dp, root).replace("\\", "/").lower()
        rel = "" if rel == "." else rel + "/"
        for fn in fns:
            stem, ext = os.path.splitext(fn)
            if ext.lower() in exts:
                found.add(rel + stem.lower())
    return found

meshes_available = (_index(os.path.join(PZ, "models_X"), {".x", ".fbx"})
                    | _index(os.path.join(MOD, "media", "models_X"), {".x", ".fbx"}))
textures_available = (_index(os.path.join(PZ, "textures"), {".png"})
                      | _index(os.path.join(MOD, "media", "textures"), {".png"}))

# Both sides of every lookup below get a floor, because a pattern that has
# stopped matching makes an empty set and *everything* is missing from an
# empty set -- which is how the dilithium loot check first ran.
if mod_clothing:
    if len(vanilla_guids) < 1000:
        failures.append(f"only {len(vanilla_guids)} GUIDs were read out of the "
                        f"game's fileGuidTable.xml; the pattern has stopped "
                        f"matching, so the collision check proves nothing")
    if len(meshes_available) < 500:
        failures.append(f"only {len(meshes_available)} meshes were indexed out "
                        f"of models_X; the clothing model check proves nothing")
    if len(textures_available) < 500:
        failures.append(f"only {len(textures_available)} textures were indexed; "
                        f"the clothing texture check proves nothing")

guid_text = ""
if os.path.isfile(GUID_TABLE):
    guid_text = open(GUID_TABLE, encoding="utf-8", errors="replace").read()
elif mod_clothing:
    failures.append("the mod declares clothing but has no "
                    "media/fileGuidTable.xml; every garment would resolve to "
                    "null and draw nothing (python tools/gen_uniform.py)")

guid_rows = re.findall(r"<files>\s*<path>([^<]+)</path>\s*<guid>([^<]+)</guid>",
                       guid_text, re.S)
guid_by_path = {p.strip().replace("\\", "/"): g.strip() for p, g in guid_rows}
if guid_text and len(guid_rows) != guid_text.count("<files>"):
    failures.append(f"media/fileGuidTable.xml has {guid_text.count('<files>')} "
                    f"<files> blocks but only {len(guid_rows)} parsed as a "
                    f"path/guid pair; the table is malformed and the engine "
                    f"swallows the exception")

seen_guids = {}
for name in sorted(mod_clothing):
    xml_path = os.path.join(CLOTHING_DIR, name + ".xml")
    if not os.path.isfile(xml_path):
        failures.append(f"ClothingItem = {name} has no "
                        f"media/clothing/clothingItems/{name}.xml, so the "
                        f"garment equips and draws nothing")
        continue
    body = open(xml_path, encoding="utf-8-sig", errors="replace").read()

    guid = re.search(r"<m_GUID>([^<]+)</m_GUID>", body)
    if not guid:
        failures.append(f"{name}.xml has no m_GUID")
        continue
    guid = guid.group(1).strip()

    rel = f"media/clothing/clothingItems/{name}.xml"
    if rel not in guid_by_path:
        failures.append(f"media/fileGuidTable.xml has no row for {rel}. "
                        f"getClothingItem returns null for an id the table "
                        f"does not know, and the garment draws nothing with "
                        f"no warning anywhere")
    elif guid_by_path[rel].lower() != guid.lower():
        failures.append(f"{name}.xml declares GUID {guid} and the table says "
                        f"{guid_by_path[rel]}; they must match exactly")

    if guid.lower() in vanilla_guids:
        failures.append(f"{name}.xml uses GUID {guid}, which the game already "
                        f"ships. mergeFrom does not de-duplicate, so one of "
                        f"the two garments would resolve to the other")
    if guid.lower() in seen_guids:
        failures.append(f"{name}.xml and {seen_guids[guid.lower()]}.xml share "
                        f"GUID {guid}")
    seen_guids[guid.lower()] = name
    if rel.lower() in vanilla_guid_paths:
        failures.append(f"{rel} is also a path in the game's own GUID table")

    # A garment needs BOTH bodies, or it is invisible on one of them -- and
    # that is a character the author may simply never have made.
    male = re.search(r"<m_MaleModel>([^<]*)</m_MaleModel>", body)
    female = re.search(r"<m_FemaleModel>([^<]*)</m_FemaleModel>", body)
    male = (male.group(1) if male else "").strip()
    female = (female.group(1) if female else "").strip()
    textures = re.findall(r"<textureChoices>([^<]+)</textureChoices>", body)
    base_tex = re.findall(r"<m_BaseTextures>([^<]+)</m_BaseTextures>", body)

    if bool(male) != bool(female):
        failures.append(f"{name}.xml names a model for one sex and not the "
                        f"other; it would draw on one body and vanish on the "
                        f"other")
    if not male and not textures and not base_tex:
        failures.append(f"{name}.xml names neither a model nor a texture")

    def _norm(ref):
        ref = ref.strip().lower().replace("\\", "/")
        for prefix in ("media/models_x/", "media/textures/", "x:"):
            if ref.startswith(prefix):
                ref = ref[len(prefix):]
        return os.path.splitext(ref)[0]

    for ref in (m for m in (male, female) if m):
        if _norm(ref) not in meshes_available:
            failures.append(f"{name}.xml names model {ref}, which is not in "
                            f"models_X; the garment draws nothing")
    for ref in textures + base_tex:
        if _norm(ref) not in textures_available:
            failures.append(f"{name}.xml names texture {ref}, which is not on "
                            f"disk; the garment draws untextured")
    for folder in re.findall(r"<m_(?:Underlay)?MasksFolder>([^<]+)</m_(?:Underlay)?MasksFolder>",
                             body):
        rel_folder = folder.strip().replace("\\", "/")
        for root in (PZ, os.path.join(MOD, "media")):
            candidate = os.path.join(root, *rel_folder.split("/")[1:]) \
                if rel_folder.startswith("media/") else os.path.join(root, rel_folder)
            if os.path.isdir(candidate):
                break
        else:
            failures.append(f"{name}.xml names masks folder {folder}, which "
                            f"is not a directory")

# A GUID row for a file that is not there is the mirror of the above, and just
# as quiet.
for rel in sorted(guid_by_path):
    if not os.path.isfile(os.path.join(MOD, *rel.split("/"))):
        failures.append(f"media/fileGuidTable.xml has a row for {rel}, which "
                        f"does not exist")

# Every mod clothing item must sit in a body location the game declares, or it
# can never be equipped at all.
BODY_LOC = os.path.join(PZ, "lua", "shared", "NPCs", "BodyLocations.lua")
if os.path.isfile(BODY_LOC):
    loc_src = open(BODY_LOC, encoding="utf-8", errors="replace").read()
    known_locs = {m.lower() for m in
                  re.findall(r"ItemBodyLocation\.([A-Z_0-9]+)", loc_src)}
    if len(known_locs) < 20:
        failures.append("BodyLocations.lua parsed fewer than 20 locations; "
                        "the check proves nothing")
    else:
        for loc in re.findall(r"^\s*BodyLocation\s*=\s*base:([A-Za-z0-9_]+)\s*,",
                              script, re.M):
            if loc.lower().replace("_", "") not in {k.replace("_", "")
                                                    for k in known_locs}:
                failures.append(f"BodyLocation = base:{loc} is not a location "
                                f"the game declares; the garment cannot be "
                                f"worn")

# ROADMAP2 1.4: "no arbitrary stat bonus or armour-like protection". Vanilla's
# Boilersuit -- the block the duty uniform was copied from -- carries
# ScratchDefense = 10, and a defence stat that rides along because it was in
# the source block is exactly the "better than intended" item DEV_GUIDE warns
# about in "A convenience method is a bundle of writes somebody else chose".
# Insulation is not armour and is deliberately allowed.
_cl_chunks = re.split(r"^\s*item\s+([A-Za-z0-9_]+)\s*$", script, flags=re.M)
for _name, _body in zip(_cl_chunks[1::2], _cl_chunks[2::2]):
    if not re.search(r"^\s*ClothingItem\s*=", _body, re.M):
        continue
    for stat in ("ScratchDefense", "BiteDefense", "BulletDefense",
                 "NeckProtectionModifier"):
        if re.search(rf"^\s*{stat}\s*=", _body, re.M):
            failures.append(
                f"{_name} sets {stat}. ROADMAP2 1.4 says the uniform carries "
                f"no armour-like protection; vanilla's Boilersuit has "
                f"ScratchDefense = 10 and it must not be copied across.")


# --- the world-map symbols --------------------------------------------
# A contact is drawn with a symbol id, and `addTexture` on an id that nothing
# registered draws **nothing at all** -- no warning, no placeholder, an empty
# map and a contact the crew cannot see. Three files have to agree: the kind
# in C.ContactSymbols, the registration in shared/Definitions/TrekMapSymbols
# .lua, and the PNG on disk. All three are generated by tools/gen_map_symbols
# .py, and this is what holds them together.
cfg_src = open(os.path.join(MOD, "media", "lua", "shared", "TREK",
                            "TREK_Config.lua"), encoding="utf-8").read()
_sym_block = re.search(r"C\.ContactSymbols\s*=\s*\{(.*?)\}", cfg_src, re.S)
contact_symbols = dict(re.findall(r"(\w+)\s*=\s*\"([\w]+)\"",
                                  _sym_block.group(1))) if _sym_block else {}

SYMBOL_DEFS = os.path.join(MOD, "media", "lua", "shared", "Definitions",
                           "TrekMapSymbols.lua")
registered = {}
if os.path.isfile(SYMBOL_DEFS):
    registered = dict(re.findall(
        r'addTexture\(\s*"([\w]+)"\s*,\s*"([^"]+)"',
        open(SYMBOL_DEFS, encoding="utf-8").read()))
elif contact_symbols:
    failures.append("C.ContactSymbols names symbols but "
                    "shared/Definitions/TrekMapSymbols.lua is missing "
                    "(python tools/gen_map_symbols.py)")

if not contact_symbols:
    failures.append("no C.ContactSymbols entries were parsed out of "
                    "TREK_Config.lua; the pattern has stopped matching, so "
                    "this check proves nothing")

for kind, symbol_id in sorted(contact_symbols.items()):
    if symbol_id not in registered:
        failures.append(f"contact kind {kind!r} draws with symbol "
                        f"{symbol_id!r}, which TrekMapSymbols.lua does not "
                        f"register; the map would show nothing at all")
    elif not os.path.isfile(os.path.join(MOD, *registered[symbol_id].split("/"))):
        failures.append(f"map symbol {symbol_id!r} is registered as "
                        f"{registered[symbol_id]}, which is not on disk")
_lab = re.search(r"C\.ContactLabels\s*=\s*\{(.*?)\}", cfg_src, re.S)
contact_labels = dict(re.findall(r"(\w+)\s*=\s*\"([\w]+)\"",
                                 _lab.group(1))) if _lab else {}
_kinds = re.search(r"C\.ContactKinds\s*=\s*\{(.*?)\}", cfg_src, re.S)
kinds = set(re.findall(r"(\w+)\s*=\s*true", _kinds.group(1))) if _kinds else set()
if len(kinds) < 2:
    failures.append(f"only {len(kinds)} contact kinds parsed; the pattern has "
                    f"stopped matching")
for kind in sorted(kinds):
    if kind not in contact_symbols:
        failures.append(f"contact kind {kind!r} has no entry in "
                        f"C.ContactSymbols, so it would draw nothing on the map")
    if kind not in contact_labels:
        failures.append(f"contact kind {kind!r} has no entry in "
                        f"C.ContactLabels, so the sensor menu would show it "
                        f"as a raw translation key")

# **A map symbol category of our own crashes the world map.** Vanilla's symbol
# palette lays a category out at eight buttons a row and then does
#
#   ISWorldMapSymbols.lua:1226  tab.joypadIndexY = floor(#tab.joypadButtonsY / 2)
#                        :1227  tab.joypadButtons = tab.joypadButtonsY[...]
#                        :1228  tab.joypadIndex   = ceil(#tab.joypadButtons / 2)
#
# so a category with one row of buttons indexes [0], gets nil, and `#nil`
# throws. A category needs **nine** symbols before it can be laid out at all.
# Two Starfleet symbols in a "Starfleet" category made opening the map throw,
# with an error naming neither the mod nor the symbol.
#
# The mod's symbols therefore join one of vanilla's categories, and this holds
# them there: the category must be one vanilla declares, and vanilla's own
# count in it must already clear the row threshold.
VANILLA_SYMBOLS = os.path.join(PZ, "lua", "shared", "Definitions",
                               "MapSymbolDefinitions.lua")
SYMBOL_COLUMNS = 8
if registered and os.path.isfile(VANILLA_SYMBOLS):
    vanilla_cats = {}
    for _id, _path, _cat in re.findall(
            r'addTexture\(\s*"([^"]+)"\s*,\s*"([^"]+)"\s*,\s*"([^"]+)"\s*\)',
            open(VANILLA_SYMBOLS, encoding="utf-8").read()):
        vanilla_cats[_cat] = vanilla_cats.get(_cat, 0) + 1
    if not vanilla_cats:
        failures.append("no categories were parsed out of vanilla's "
                        "MapSymbolDefinitions.lua; this check proves nothing")
    mod_cats = set(re.findall(
        r'addTexture\(\s*"[^"]+"\s*,\s*"[^"]+"\s*,\s*"([^"]+)"\s*\)',
        open(SYMBOL_DEFS, encoding="utf-8").read()))
    for cat in sorted(mod_cats):
        total = vanilla_cats.get(cat, 0)
        if cat not in vanilla_cats:
            failures.append(
                f"TrekMapSymbols.lua puts symbols in a category {cat!r} that "
                f"vanilla does not have. A category with {SYMBOL_COLUMNS} or "
                f"fewer symbols makes ISWorldMapSymbols index joypadButtonsY"
                f"[0], and opening the world map throws.")
        elif total <= SYMBOL_COLUMNS:
            failures.append(
                f"category {cat!r} holds only {total} vanilla symbols, at or "
                f"under the {SYMBOL_COLUMNS}-per-row threshold where "
                f"ISWorldMapSymbols throws")

for symbol_id in sorted(registered):
    if symbol_id not in contact_symbols.values():
        failures.append(f"TrekMapSymbols.lua registers {symbol_id!r} and no "
                        f"contact kind uses it")

# Every contact kind must also have a status vocabulary behind it, and the
# resolved set must be a subset of the statuses -- a "resolved" status that is
# not a status at all would make a contact neither live nor prunable.
_stat = re.search(r"C\.ContactStatuses\s*=\s*\{(.*?)\}", cfg_src, re.S)
_res = re.search(r"C\.ContactResolved\s*=\s*\{(.*?)\}", cfg_src, re.S)
statuses = set(re.findall(r"(\w+)\s*=\s*true", _stat.group(1))) if _stat else set()
resolved = set(re.findall(r"(\w+)\s*=\s*true", _res.group(1))) if _res else set()
if len(statuses) < 4:
    failures.append(f"only {len(statuses)} contact statuses parsed; the "
                    f"pattern has stopped matching")
for name in sorted(resolved - statuses):
    failures.append(f"C.ContactResolved lists {name!r}, which is not in "
                    f"C.ContactStatuses")
if not resolved:
    failures.append("C.ContactResolved is empty; nothing would ever be "
                    "pruned and the store would grow for the life of the save")


# --- the mod's own sounds ----------------------------------------------
# `playSoundLocal("TREK_HypoHiss")` on a name no script declares, or a script
# naming a .wav that is not on disk, both do exactly nothing and say exactly
# nothing. An instrument that works in silence is the shape of half the bugs
# in DEV_GUIDE.md, and the mod already relies on a sound to prove a scan
# happened at all.
declared_sounds = set()
for block in re.finditer(r"sound\s+(\w+)\s*\{(.*?)\n    \}", script, re.S):
    name, body = block.group(1), block.group(2)
    declared_sounds.add(name)
    for clip in re.findall(r"file\s*=\s*([\w/]+\.wav)\s*,", body):
        if not os.path.exists(os.path.join(MOD, clip)):
            failures.append(f"sound {name} names {clip}, which is not on disk")
if len(declared_sounds) < 4:
    failures.append(f"only {len(declared_sounds)} sound blocks were found in "
                    f"trekshuttle.txt; the pattern has stopped matching")

played = set()
for dp, _, fns in os.walk(os.path.join(MOD, "media", "lua")):
    for fn in fns:
        if fn.endswith(".lua"):
            body = open(os.path.join(dp, fn), encoding="utf-8").read()
            played |= set(re.findall(r'playSound(?:Local)?\(\s*"(\w+)"', body))
for name in sorted(played):
    # Vanilla's own sounds are fair game; only the mod's need declaring here.
    if name.startswith("TREK_") and name not in declared_sounds:
        failures.append(f"the Lua plays {name}, which no sound block declares")


# --- an attachable item's icon has to be 32x32 -------------------------
# An item with an `AttachmentType` is the only kind vanilla's hotbar ever
# draws, and the hotbar assumes a 32x32 icon. `ISHotbar.lua:52`:
#
#     self:drawTexture(tex, slotX + (tex:getWidth() / 2),
#                           (self.height - tex:getHeight()) / 2, 1,1,1,1)
#
# The y is a real centring expression. The x is the slot's left edge plus
# *half the texture's own width*, which only lands centred when the texture is
# half the slot -- and `slotWidth` is 60. So a 32px icon occupies 16..48 of its
# slot, centred as every vanilla icon is, and a 64px icon occupies 32..96:
# it starts at the middle of its own slot and runs 36px into the next one.
# Three lines above, vanilla centres the slot's label with the formula this
# line should have used, `slotX + (self.slotWidth - textWid) / 2`.
#
# The bat'leth did exactly that in game, overlapping the belt beside it, and
# three rounds of shrinking the drawing *inside* a 64px frame (94%, 81%, 78%)
# could not fix it, because the frame was the problem and not the drawing.
#
# Every other icon in this mod is 64x64 and right: nothing else attaches, so
# nothing else is ever drawn by that line.
def png_size(path):
    with open(path, "rb") as fh:
        head = fh.read(24)
    if head[:8] != b"\x89PNG\r\n\x1a\n":
        return None
    return struct.unpack(">II", head[16:24])


HOTBAR_ICON = 32
# [prefix, name, body, name, body, ...]
_chunks = re.split(r"^\s*item\s+([A-Za-z0-9_]+)\s*$", script, flags=re.M)
for _name, _body in zip(_chunks[1::2], _chunks[2::2]):
    if not re.search(r"^\s*AttachmentType\s*=\s*\w+\s*,", _body, re.M):
        continue
    _icon = re.search(r"^\s*Icon\s*=\s*([A-Za-z0-9_]+)\s*,", _body, re.M)
    if not _icon:
        continue
    _path = os.path.join(MOD, "media", "textures", f"Item_{_icon.group(1)}.png")
    _size = png_size(_path) if os.path.exists(_path) else None
    if _size and _size != (HOTBAR_ICON, HOTBAR_ICON):
        failures.append(
            f"{_name} has an AttachmentType, so vanilla's hotbar draws its "
            f"icon, and Item_{_icon.group(1)}.png is {_size[0]}x{_size[1]} "
            f"rather than {HOTBAR_ICON}x{HOTBAR_ICON}. ISHotbar.lua:52 draws "
            f"it at slotX + width/2 in a 60px slot, so it will start at the "
            f"middle of its own slot and spill "
            f"{_size[0] // 2 + _size[0] - 60}px into the next one")

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
    # The phaser used to borrow vanilla's Handgun03 and this demanded a
    # vanilla model. It has its own now (PHASERS.md 4); every WeaponSprite,
    # the phaser's included, goes through the general check below -- a mod
    # model in `module Base`, or a vanilla one.
    for key in ("SwingAnim", "RunAnim"):
        if not re.search(key + r"\s*=", body):
            failures.append(f"phaser has no {key}; it will not animate")

# --- weapons that borrow from the engine by name -----------------------
# A weapon model is a plain static mesh, and the two names that reach it are
# resolved by string at load: WeaponSprite must name a `model` block, and
# SwingAnim must name one of the animations the game itself ships. Neither
# failure says anything -- a bad WeaponSprite draws an empty hand, a bad
# SwingAnim just does not animate -- so both are checked here.
# Which module each of the mod's own models is declared in. WeaponSprite does
# NOT resolve inside the mod's own module the way StaticModel does: the
# bat'leth declared in `module TrekShuttle` drew nothing in hand, and the only
# sign was one line -- MeshAssetManager failing to load an asset named after
# the *model block*, which is what the engine falls back to when the name
# resolved to no ModelScript at all. Every vanilla weapon model, and the one
# Workshop mod shipping custom in-hand blades, declares them in `module Base`.
model_module = {}
for fn in ("trekshuttle.txt", "trekweapons.txt"):
    path = os.path.join(MOD, "media", "scripts", fn)
    if not os.path.isfile(path):
        continue
    body = open(path, encoding="utf-8").read()
    current = None
    for line in body.splitlines():
        mod_m = re.match(r"^module\s+(\w+)", line)
        if mod_m:
            current = mod_m.group(1)
        mdl = re.match(r"^\s*model\s+([A-Za-z0-9_]+)\s*$", line)
        if mdl:
            model_module[mdl.group(1)] = current

for ref in re.findall(r"^\s*WeaponSprite\s*=\s*([A-Za-z0-9_]+)\s*,", script, re.M):
    if ref in mod_models:
        where = model_module.get(ref)
        if where != "Base":
            failures.append(
                f"WeaponSprite = {ref} names a model declared in module "
                f"{where!r}. Weapon models must be in `module Base` or the "
                f"engine finds no ModelScript and the weapon draws nothing in "
                f"hand -- the only symptom is one MeshAssetManager warning.")
    elif not re.search(r"model\s+%s\s*\n?\s*\{" % ref, vanilla):
        failures.append(f"WeaponSprite = {ref} is neither a mod model nor a "
                        f"vanilla one; the weapon draws nothing in hand")

# The animation set is global and closed: a mod borrows a name or gets nothing.
SWING_ANIMS = set(re.findall(r"^\s*SwingAnim\s*=\s*(\w+)\s*,", vanilla, re.M))
for ref in re.findall(r"^\s*SwingAnim\s*=\s*(\w+)\s*,", script, re.M):
    if ref not in SWING_ANIMS:
        failures.append(f"trekshuttle.txt: SwingAnim = {ref} is not an animation "
                        f"vanilla uses ({', '.join(sorted(SWING_ANIMS))})")

# --- the galley's fluids -----------------------------------------------
# A drink is a fluid plus a vessel, and every join between the two can fail on
# a name: a whitelist naming a fluid that does not exist, a DisplayName with no
# translation, a fluid mask with no texture. Most look like "the drink is there
# but wrong" in game -- but ColorReference does not, it takes the whole world
# down with it. See below.
mod_fluids = set(re.findall(r"^\s*fluid\s+([A-Za-z0-9_]+)\s*$", script, re.M))

# ColorReference is a name out of zombie.core.Colors, not a hex value, and an
# unknown one is **fatal**: FluidDefinitionScript.getColor throws
# RuntimeException("Cannot find color: X"), which aborts ScriptManager
# .loadScripts, and the world then refuses to load at all with "there are
# script load errors". It is not a cosmetic typo. `ClearBlue` cost a crash.
#
# The list checked against is the set of colours **vanilla's own fluids use**,
# not every string in Colors.class. Scraping the class file is what let
# `ClearBlue` through: a string being present in a class is not the same as it
# being a registered colour name, which is the identical mistake to "the jar is
# not the API" one level down. This set is conservative -- it would reject a
# real colour that no vanilla fluid happens to use -- and that is the right way
# round when being wrong stops the game booting. If you need one that is not
# here, prove it in game first and add it with a note.
VANILLA_FLUIDS = ""
for fn in glob.glob(os.path.join(PZ, "scripts", "generated", "fluids*.txt")):
    VANILLA_FLUIDS += open(fn, encoding="utf-8", errors="replace").read()
colour_names = set(re.findall(r"ColorReference\s*=\s*([A-Za-z0-9_]+)\s*,",
                              VANILLA_FLUIDS))
if not colour_names:
    print("  (skipped the ColorReference check: no vanilla fluid scripts found)")
else:
    for ref in re.findall(r"^\s*ColorReference\s*=\s*([A-Za-z0-9_]+)\s*,", script, re.M):
        if ref not in colour_names:
            failures.append(
                f"trekshuttle.txt: ColorReference = {ref} is not a colour any "
                f"vanilla fluid uses, and an unknown colour is fatal -- the "
                f"world will not load. Known good: "
                f"{', '.join(sorted(colour_names))}")

# A FluidContainer's Fluids block is a whitelist. A name that is not a declared
# fluid means the vessel refuses the drink it exists to hold.
for ref in re.findall(r"^\s*fluid\s*=\s*([A-Za-z0-9_.]+)\s*:", script, re.M):
    bare = ref.split(".")[-1]
    if bare not in mod_fluids:
        failures.append(f"trekshuttle.txt: a FluidContainer whitelists "
                        f"{ref}, which is not a fluid this mod declares")

# IconFluidMask resolves exactly as Icon does: media/textures/Item_<name>.png.
# Without it the vessel draws with no liquid in it at all.
for mask in re.findall(r"^\s*IconFluidMask\s*=\s*([A-Za-z0-9_]+)\s*,", script, re.M):
    if not os.path.exists(os.path.join(MOD, "media", "textures", f"Item_{mask}.png")):
        failures.append(f"trekshuttle.txt: IconFluidMask = {mask} has no texture; "
                        f"expected media/textures/Item_{mask}.png")

# Fluid names live in Translate/EN/Fluids.json -- their own category file, like
# every other. A Fluid_Name_ key in the wrong file resolves to nothing.
FLUID_TR = os.path.join(MOD, "media", "lua", "shared", "Translate", "EN", "Fluids.json")
fluid_names = {}
if mod_fluids and not os.path.isfile(FLUID_TR):
    failures.append("the mod declares fluids but has no Translate/EN/Fluids.json")
elif os.path.isfile(FLUID_TR):
    fluid_names = json.load(open(FLUID_TR, encoding="utf-8"))
    for key in fluid_names:
        if not key.startswith("Fluid_Name_"):
            failures.append(f"Fluids.json holds {key}, which is not a Fluid_Name_ key")
for block in re.finditer(r"fluid\s+([A-Za-z0-9_]+)\s*\{(.*?)\n    \}", script, re.S):
    name, body = block.group(1), block.group(2)
    shown = re.search(r"DisplayName\s*=\s*([A-Za-z0-9_]+)\s*,", body)
    if not shown:
        failures.append(f"fluid {name} has no DisplayName; it shows as its id")
    elif shown.group(1) not in fluid_names:
        failures.append(f"Fluids.json has no entry for {shown.group(1)} "
                        f"(fluid {name})")

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
                    if m.group(1) not in items and m.group(1) not in mod_vehicles:
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

# --- the version, in the two places that both claim to hold it ---------
# `modversion` in mod.info is what a subscriber sees on the mods screen and
# what tells them an update arrived; `C.Version` is what the mod logs on every
# world load and writes into the saved ship state. Nothing made them agree, so
# they drifted -- 1.4.0 against 1.3.0 for a whole release -- and the log was
# reporting the version *before* the one the player had installed, which is the
# worst possible way to read a bug report.
info = open(os.path.join(MOD, "mod.info"), encoding="utf-8").read()
declared = re.search(r"^modversion=(.+)$", info, re.M)
config = open(os.path.join(MOD, "media", "lua", "shared", "TREK",
                           "TREK_Config.lua"), encoding="utf-8").read()
coded = re.search(r'^C\.Version\s*=\s*"([^"]+)"', config, re.M)
if not declared or not coded:
    failures.append("cannot find modversion in mod.info or C.Version in "
                    "TREK_Config.lua; this check has stopped matching")
elif declared.group(1).strip() != coded.group(1):
    failures.append(f"mod.info says version {declared.group(1).strip()} and "
                    f"TREK_Config says {coded.group(1)}")

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

# UI.json holds two things. Overrides of vanilla strings -- the intro's "THIS
# IS HOW YOU DIED" becomes "THIS WAS YOUR AWAY MISSION" -- whose key must exist
# in the game's own UI.json, or the override changes nothing and says nothing.
# And the traits' and professions' names, which vanilla keeps in UI.json too:
# exactly the keys trek_traits.txt names, and no others.
TRAITS_TXT = os.path.join(MOD, "media", "scripts", "trek_traits.txt")
traits_script = open(TRAITS_TXT, encoding="utf-8").read() if os.path.isfile(TRAITS_TXT) else ""
trait_ui_keys = set(re.findall(r"^\s*(?:UIName|UIDescription)\s*=\s*(\w+)\s*,",
                               traits_script, re.M))
ui_override = os.path.join(TR, "UI.json")
ui_mod = {}
if os.path.isfile(ui_override):
    vanilla_ui = json.load(open(os.path.join(PZ, "lua", "shared", "Translate", "EN", "UI.json"),
                                encoding="utf-8"))
    ui_mod = json.load(open(ui_override, encoding="utf-8"))
    for key in ui_mod:
        if key not in vanilla_ui and key not in trait_ui_keys:
            failures.append(f"UI.json overrides {key}, which vanilla does not have "
                            f"and no trait or profession names")
for key in sorted(trait_ui_keys):
    if key not in ui_mod:
        failures.append(f"trek_traits.txt names {key}, which UI.json does not have -- "
                        f"the creation screen would show the raw key")

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
# Vanilla's own keys (the vehicle menus reuse a few) resolve from the game.
vanilla_ig = json.load(open(os.path.join(PZ, "lua", "shared", "Translate", "EN", "IG_UI.json"),
                            encoding="utf-8", errors="replace"))
for key in sorted(asked):
    if key.startswith("IGUI_") and key not in ig and key not in vanilla_ig:
        failures.append(f"getText(\"{key}\") has no entry in IG_UI.json")
for item in sorted(mod_items):
    if f"TrekShuttle.{item}" not in names:
        failures.append(f"ItemName.json has no name for TrekShuttle.{item}")
for tip in sorted(re.findall(r"^\s*Tooltip\s*=\s*(\w+)\s*,", script, re.M)):
    if tip not in tips:
        failures.append(f"Tooltip.json has no entry for {tip}")

# --- the sandbox options -----------------------------------------------
# A server owner's settings page is built from two files that have to agree,
# and neither complains when they do not: media/sandbox-options.txt declares
# the option and how many values it has, and Translate/EN/Sandbox.json names
# it and every one of those values. A missing name shows the option's raw id,
# and a missing value name shows "option3" -- in somebody else's server
# settings, which is the one place the author never looks.
SB = os.path.join(MOD, "media", "sandbox-options.txt")
SB_TR = os.path.join(MOD, "media", "lua", "shared", "Translate", "EN", "Sandbox.json")
if os.path.isfile(SB) and os.path.isfile(SB_TR):
    sb = open(SB, encoding="utf-8").read()
    sb_tr = json.load(open(SB_TR, encoding="utf-8"))
    for name, body in re.findall(r"^\s*option\s+([\w.]+)\s*=\s*\{(.*?)\}", sb,
                                 re.M | re.S):
        for key in (f"Sandbox_{name}", f"Sandbox_{name}_tooltip"):
            if key not in sb_tr:
                failures.append(f"Sandbox.json has no {key}; the option shows "
                                f"as its raw id on the settings page")
        page = re.search(r"page\s*=\s*(\w+)", body)
        if page and f"Sandbox_{page.group(1)}" not in sb_tr:
            failures.append(f"Sandbox.json has no Sandbox_{page.group(1)} for "
                            f"the settings page {name} sits on")
        count = re.search(r"numValues\s*=\s*(\d+)", body)
        if count and "valueTranslation" in body:
            for i in range(1, int(count.group(1)) + 1):
                key = f"Sandbox_{name}_option{i}"
                if key not in sb_tr:
                    failures.append(f"Sandbox.json has no {key}; that value "
                                    f"shows as 'option{i}' in the settings")

# --- the shuttle vehicle -----------------------------------------------
# A vehicle whose mesh, texture or wheel model does not resolve loads as
# nothing, silently, and the seat chart art is projected from the mesh at the
# vehicle's length: if the script's length drifts from the mesh, the seat
# markers stop landing on the seats.
vscript_path = os.path.join(MOD, "media", "scripts", "vehicles", "trekshuttle_vehicle.txt")
if not os.path.isfile(vscript_path):
    failures.append("media/scripts/vehicles/trekshuttle_vehicle.txt is missing")
else:
    vs = open(vscript_path, encoding="utf-8").read()
    for mesh in re.findall(r"^\s*mesh\s*=\s*([\w/]+)\s*,", vs, re.M):
        if not os.path.isfile(os.path.join(MOD, "media", "models_X", mesh + ".x")):
            failures.append(f"vehicle mesh {mesh}.x is not in media/models_X "
                            f"(python tools/gen_vehicle_assets.py)")
    for key in ("texture", "textureMask"):
        for tex in re.findall(rf"^\s*{key}\s*=\s*([\w/]+)\s*,", vs, re.M):
            local = os.path.join(MOD, "media", "textures", tex + ".png")
            vanilla_tex = tex.startswith("Vehicles/")
            if not vanilla_tex and not os.path.isfile(local):
                failures.append(f"vehicle {key} {tex}.png is not in media/textures")
    ext = re.search(r"^\s*extents\s*=\s*([\d.]+)\s+([\d.]+)\s+([\d.]+)\s*,", vs, re.M)
    mesh_text = open(os.path.join(MOD, "media", "models_X", "TREK_Shuttle.x"),
                     encoding="utf-8", errors="replace").read()
    zs = [float(z) for z in re.findall(r"-?\d+\.\d+;-?\d+\.\d+;(-?\d+\.\d+);,", mesh_text)]
    if ext and zs and abs(float(ext.group(3)) - (max(zs) - min(zs))) > 0.1:
        failures.append(f"vehicle extents length {ext.group(3)} does not match the hull "
                        f"mesh length {max(zs) - min(zs):.2f}; the seat chart will misalign")
    seats = re.findall(r"^\s*passenger\s+(\w+)", vs, re.M)
    if len(seats) != 4:
        failures.append(f"the shuttle vehicle has {len(seats)} seats, not 4")
    if re.search(r"^\s*door\s*=\s*\w", vs, re.M) or "template = Door" in vs:
        failures.append("the shuttle vehicle has a door: a doored seat can be bitten through")
for art in ("seatui/trekshuttle_base_small.png", "mechanic overlay/trekshuttle_base.png"):
    if not os.path.isfile(os.path.join(MOD, "media", "ui", "vehicles", *art.split("/"))):
        failures.append(f"media/ui/vehicles/{art} is missing (python tools/gen_vehicle_assets.py)")

# --- the void map ------------------------------------------------------
# Mapped cells around the cabin and the Adirondack keep the world generator
# out; their ground is star-field floor, and past that nothing. Each file is
# read back in the build 42 format tools/gen_void_map.py writes; a malformed
# lot fails to load in game and the wilderness comes back, silently.
#
# **And it has to be in common/media/maps.** The engine looks there first and
# skips the mod entirely when that folder is missing (MapGroups.createGroups),
# so a map in 42/media/maps is never loaded -- which is where this one sat,
# unread, for every release before 1.9.
import struct
sys.path.insert(0, os.path.join(ROOT, "tools"))
import gen_void_map as VOID  # noqa: E402
cfg = open(os.path.join(MOD, "media", "lua", "shared", "TREK", "TREK_Config.lua"),
           encoding="utf-8").read()
void = re.search(r'C\.VoidMap\s*=\s*"([^"]+)"', cfg)
common = os.path.join(ROOT, "TrekShuttle", "common")
if not void:
    failures.append("TREK_Config.lua: C.VoidMap not found")
else:
    if os.path.isdir(os.path.join(MOD, "media", "maps")):
        failures.append("media/maps is under 42/: the engine never reads a mod's map from there "
                        "(python tools/gen_void_map.py moves it to common/)")
    mapdir = os.path.join(common, "media", "maps", void.group(1))
    info = os.path.join(mapdir, "map.info")
    if not os.path.isfile(info):
        failures.append(f"common/media/maps/{void.group(1)}/map.info is missing "
                        f"(python tools/gen_void_map.py)")
    elif "lots=Muldraugh, KY" not in open(info, encoding="utf-8").read():
        failures.append("the void map's map.info does not group it with Muldraugh, KY")
    box = VOID.space_box()
    want_cells = VOID.cells(box)
    stars_seen = 0
    for x, y in want_cells:
        try:
            h = open(os.path.join(mapdir, f"{x}_{y}.lotheader"), "rb").read()
            p = open(os.path.join(mapdir, f"world_{x}_{y}.lotpack"), "rb").read()
            c = open(os.path.join(mapdir, f"chunkdata_{x}_{y}.bin"), "rb").read()
        except OSError:
            failures.append(f"void map cell {x},{y} is missing a file (python tools/gen_void_map.py)")
            continue
        names = h[12:].split(b"\n")[:len(VOID.STARS)]
        ok = (h[:4] == b"LOTH" and struct.unpack_from("<ii", h, 4) == (1, len(VOID.STARS))
              and [n.decode() for n in names] == VOID.STARS
              and p[:4] == b"LOTP" and struct.unpack_from("<ii", p, 4) == (1, 1024)
              and c == b"\x00\x01" + bytes(1024))
        if not ok:
            failures.append(f"void map cell {x},{y} has a malformed header")
            continue
        # Walk every chunk: it must account for exactly 64 squares, and every
        # tile it names must be one of the header's.
        offs = struct.unpack_from("<1024q", p, 12)
        for i, o in enumerate(offs):
            end = offs[i + 1] if i + 1 < 1024 else len(p)
            n, at = 0, o
            while at < end:
                count = struct.unpack_from("<i", p, at)[0]
                if count == -1:
                    n += struct.unpack_from("<i", p, at + 4)[0]
                    at += 8
                else:
                    named = struct.unpack_from("<%di" % count, p, at + 4)[1:]
                    if any(not (0 <= t < len(VOID.STARS)) for t in named):
                        failures.append(f"void map cell {x},{y} chunk {i} names a tile it does not have")
                        break
                    stars_seen += 1
                    n += 1
                    at += 4 * (count + 1)
            if n != 64:
                failures.append(f"void map cell {x},{y} chunk {i} holds {n} squares, not 64")
                break
    # Floor, not ceiling: the starfield has to cover both ships and their view.
    area = (box[2] - box[0] + 1) * (box[3] - box[1] + 1)
    if stars_seen != area:
        failures.append(f"the void map has {stars_seen} star squares; its box needs {area}")
    for name in VOID.STARS:
        if name not in tiles:
            failures.append(f"star tile {name} has no picture or no properties in the pack")

# --- the Jefferies tubes' own guard --------------------------------------
# A tube is walled only where it meets something that is not itself, so two
# legs of one tube that touch get no wall between them. The generator refuses
# that; this proves the refusal is there, on a route that doubles back.
import gen_adirondack_tubes as TUBES  # noqa: E402
_grid = [[0] * 4 for _ in range(4)]
_decks = [dict(grid=_grid), dict(grid=_grid)]
_bad = [(-1, -3), (0, -3), (1, -3), (1, -4), (0, -4)]       # (0,-4) beside (0,-3)
_tube = dict(n=0, squares=_bad, open={frozenset(p) for p in zip(_bad, _bad[1:])})
try:
    TUBES.check([_tube], _decks, 100)
    failures.append("gen_adirondack_tubes.check accepted a tube that touches itself")
except SystemExit:
    pass
_good = [(-1, -3), (0, -3), (1, -3), (1, -4), (1, -5)]
try:
    TUBES.check([dict(n=0, squares=_good, open={frozenset(p) for p in zip(_good, _good[1:])})], _decks, 100)
except SystemExit as e:
    failures.append("gen_adirondack_tubes.check refused a sound tube: %s" % e)

# --- the loot tables the crystal is seeded into -------------------------
# server/Items/TrekDilithium.lua names vanilla distribution tables by string.
# A name that was right in build 41 and renamed since does not throw and does
# not warn at build time: the crystal simply never spawns there, the player
# never finds one, and the ship's power system quietly has no fuel. The mod
# reads its own result back at runtime and logs the misses, but that log is
# read after the world is already generated -- this is the check that happens
# first.
dilithium_lua = os.path.join(MOD, "media", "lua", "server", "Items",
                             "TrekDilithium.lua")
proc = os.path.join(PZ, "lua", "server", "Items", "ProceduralDistributions.lua")
if os.path.isfile(dilithium_lua) and os.path.isfile(proc):
    src = open(dilithium_lua, encoding="utf-8").read()
    places = re.findall(r'\{\s*"(\w+)"\s*,\s*[\d.]+\s*\}', src)
    # One level in, and vanilla indents with tabs. Anything deeper is a key
    # *inside* a table rather than a table.
    vanilla = set(re.findall(r"^(?:	| {4})(\w+)\s*=\s*\{",
                             open(proc, encoding="utf-8").read(), re.M))
    # Both sides of the comparison get a sanity check, because a regex that
    # has stopped matching would otherwise report the other side as entirely
    # missing -- which is how this check first ran, blaming twelve perfectly
    # good loot tables for a stray \s.
    if len(places) < 5:
        failures.append(f"only {len(places)} dilithium loot tables were found "
                        f"in TrekDilithium.lua -- the pattern that reads them "
                        f"has stopped matching, so this check proves nothing")
    if len(vanilla) < 100:
        failures.append(f"only {len(vanilla)} tables were read out of "
                        f"ProceduralDistributions.lua -- the pattern that "
                        f"reads them has stopped matching, so this check "
                        f"proves nothing")
    for name in places:
        if name not in vanilla:
            failures.append(f"dilithium is seeded into ProceduralDistributions "
                            f"table {name!r}, which the installed game does "
                            f"not have -- crystals will never spawn there")
    checked_dists = len(places)
else:
    checked_dists = 0

# --- traits and professions (TRAITS.md) ----------------------------------
# The registry, the script and the files the engine goes looking for by path.
# Each is a way for a trait to exist on paper and do nothing in game.
REG = os.path.join(MOD, "media", "registries.lua")
reg_src = open(REG, encoding="utf-8").read() if os.path.isfile(REG) else ""
_traits_block = re.search(r"R\.Traits = traits\(\{(.*?)\}\)", reg_src, re.S)
reg_traits = set(re.findall(r'"(\w+)"', _traits_block.group(1))) if _traits_block else set()
_profs_block = re.search(r"for _, path in ipairs\(\{(.*?)\}\) do", reg_src, re.S)
reg_profs = set(re.findall(r'"(\w+)"', _profs_block.group(1))) if _profs_block else set()
script_traits = set(re.findall(r"^\s*character_trait_definition trek:(\w+)\s*$", traits_script, re.M))
script_profs = set(re.findall(r"^\s*character_profession_definition trek:(\w+)\s*$", traits_script, re.M))
# A floor on both sides: a pattern that stopped matching would compare two
# empty sets and pass (DEV_GUIDE: a check against an empty set).
if len(reg_traits) < 20 or len(script_traits) < 20:
    failures.append(f"traits: only {len(reg_traits)} registered and {len(script_traits)} "
                    f"scripted -- a pattern here has stopped matching")
for t in sorted(reg_traits ^ script_traits):
    where = "registries.lua" if t in reg_traits else "trek_traits.txt"
    failures.append(f"traits: trek:{t} is in {where} only -- an unregistered id stops "
                    f"the scripts loading, an unscripted one is a trait nobody can have")
if len(reg_profs) < 5 or len(script_profs) < 5:
    failures.append(f"traits: only {len(reg_profs)} professions registered and "
                    f"{len(script_profs)} scripted -- a pattern stopped matching")
for t in sorted(reg_profs ^ script_profs):
    failures.append(f"traits: profession trek:{t} is registered or scripted but not both")

VAN_TRAITS = open(os.path.join(PZ, "scripts", "generated", "characters", "character_traits.txt"),
                  encoding="utf-8").read()
VAN_PROFS = open(os.path.join(PZ, "scripts", "generated", "characters", "character_professions.txt"),
                 encoding="utf-8").read()
van_trait_ids = set(m.strip() for m in re.findall(r"character_trait_definition base:([\w ]+?)\s*$",
                                                   VAN_TRAITS, re.M))
van_prof_ids = set(re.findall(r"character_profession_definition base:(\w+)", VAN_PROFS))
# The engine drops the namespace for a trait's icon and a profession's
# creation-screen clothing, so a path vanilla uses would borrow vanilla's.
for t in sorted(script_traits & van_trait_ids):
    failures.append(f"traits: trek:{t} shares its path with base:{t} -- the icon lookup "
                    f"(trait_<path>.png) would find vanilla's")
for t in sorted(script_profs & (van_prof_ids | van_trait_ids)):
    failures.append(f"traits: profession trek:{t} shares its path with vanilla -- "
                    f"ClothingSelectionDefinitions[{t}] would be vanilla's")
for ref in re.findall(r"(?:GrantedTraits|MutuallyExclusiveTraits)\s*=\s*([^,\n]+),", traits_script):
    for t in ref.split(";"):
        ns, _, path = t.strip().partition(":")
        if ns == "base" and path not in van_trait_ids:
            failures.append(f"traits: trek_traits.txt names base:{path}, which vanilla does not have")
        elif ns == "trek" and path not in script_traits:
            failures.append(f"traits: trek_traits.txt names trek:{path}, which is not defined")
van_perks = set(re.findall(r"(\w+)=\d", " ".join(re.findall(r"XPBoosts = ([^,\n]+)",
                                                             VAN_TRAITS + VAN_PROFS))))
# And every perk vanilla's own Lua names as Perks.X: LongBlade is a real perk
# no vanilla trait or profession happens to boost.
PERK_REF = re.compile(r"\bPerks\.(\w+)")
for _lua in glob.glob(os.path.join(PZ, "lua", "**", "*.lua"), recursive=True):
    van_perks |= set(PERK_REF.findall(open(_lua, encoding="utf-8", errors="ignore").read()))
if len(van_perks) < 15:
    failures.append(f"traits: only {len(van_perks)} vanilla perks found -- the pattern stopped matching")
for ref in re.findall(r"XPBoosts\s*=\s*([^,\n]+),", traits_script):
    for perk in re.findall(r"(\w+)=\d", ref):
        if perk not in van_perks:
            failures.append(f"traits: XPBoosts names {perk}, which no vanilla trait or "
                            f"profession boosts -- check it is a real perk id")


def png_dims(path):
    with open(path, "rb") as f:
        head = f.read(24)
    return struct.unpack(">II", head[16:24])


for t in sorted(script_traits):
    icon = os.path.join(MOD, "media", "ui", "Traits", f"trait_{t}.png")
    if not os.path.isfile(icon):
        failures.append(f"traits: no media/ui/Traits/trait_{t}.png -- trek:{t} would "
                        f"draw vanilla's generic icon")
    elif png_dims(icon) != (18, 18):
        failures.append(f"traits: trait_{t}.png is {png_dims(icon)}, not vanilla's 18x18")
for name in re.findall(r"IconPathName\s*=\s*(\w+)\s*,", traits_script):
    icon = os.path.join(MOD, "media", "textures", f"{name}.png")
    if not os.path.isfile(icon):
        failures.append(f"traits: no media/textures/{name}.png for a profession's icon")
    elif png_dims(icon) != (64, 64):
        failures.append(f"traits: {name}.png is {png_dims(icon)}, not vanilla's 64x64")

# The uniforms each profession offers must be real items, and every
# profession must offer one.
PC = os.path.join(MOD, "media", "lua", "shared", "Definitions", "TREK_ProfessionClothing.lua")
if os.path.isfile(PC):
    pc = open(PC, encoding="utf-8").read()
    offered = dict(re.findall(r"^\s*(\w+)\s*=\s*\"(Command|Operations|Science)\"", pc, re.M))
    for div in set(offered.values()):
        for kind in ("Duty", "Dress"):
            if f"TrekUniform{kind}{div}" not in mod_items:
                failures.append(f"traits: TREK_ProfessionClothing offers TrekUniform{kind}{div}, "
                                f"which is not a mod item")
    for prof in sorted(script_profs - set(offered)):
        failures.append(f"traits: profession {prof} offers no uniform on the creation screen")
else:
    failures.append("traits: shared/Definitions/TREK_ProfessionClothing.lua is missing")

print(f"checked {checked_sprites} sprite names and {checked_items} item ids, "
      f"{len(mod_items)} mod items, {len(mod_models)} models, "
      f"{len(mod_icons)} icons, {checked_dists} loot tables and "
      f"{len(asked)} translation keys")
if failures:
    print(f"\n{len(failures)} PROBLEM(S):")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("all asset references resolve")
