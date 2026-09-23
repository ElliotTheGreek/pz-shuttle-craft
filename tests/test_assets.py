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
    for fn in ("trekshuttle.txt", "trekweapons.txt")
    if os.path.isfile(os.path.join(MOD, "media", "scripts", fn)))
# Anchored to the end of the line, as the model and fluid patterns are: a real
# declaration is "item Foo" and nothing else, so prose in a comment that
# happens to say "item blocks" is not mistaken for one.
mod_items = set(re.findall(r"^\s*item\s+([A-Za-z0-9_]+)\s*$", script, re.M))
mod_models = set(re.findall(r"^\s*model\s+([A-Za-z0-9_]+)", script, re.M))
mod_icons = set(re.findall(r"^\s*Icon\s*=\s*([A-Za-z0-9_]+)\s*,", script, re.M))

failures, checked_sprites, checked_items = [], 0, 0

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
for icon in sorted(mod_icons):
    candidates = [os.path.join(MOD, "media", "textures", f"Item_{icon}.png"),
                  os.path.join(MOD, "media", "ui", f"{icon}.png")]
    if not any(os.path.exists(p) for p in candidates):
        failures.append(f"trekshuttle.txt: Icon = {icon} has no texture; "
                        f"expected media/textures/Item_{icon}.png")


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
    sprite = re.search(r"WeaponSprite\s*=\s*(\w+)\s*,", body)
    if sprite and not re.search(r"model\s+%s\s*\n?\s*\{" % sprite.group(1),
                                vanilla):
        failures.append(f"phaser WeaponSprite {sprite.group(1)} is not a "
                        f"vanilla weapon model")
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
    # Two rings: from the cabin's height one ring left trees in view.
    for dx in range(-2, 3):
        for dy in range(-2, 3):
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
