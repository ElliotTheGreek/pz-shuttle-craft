#!/usr/bin/env python3
"""The tape shelf: writes the RecMedia table and the text it points at.

    python tools/gen_tapes.py TrekShuttle/42

Build 42's recorded-media system takes its content from a global Lua table
called `RecMedia`, which vanilla's own `shared/RecordedMedia/ISRecordedMedia.lua`
registers on the `OnInitRecordedMedia` event. Every string in that table is a
*translation key*, and the text lives in `Translate/EN/Recorded_Media.json`.

So a tape is two files that have to agree, which is exactly the join
`gen_uniform.py` exists to make unbreakable -- and the failure mode here is
worse than it looks. A line's identity for "has this player already heard it"
is its translation **key** (`MediaLineData.getTextGuid()`), so:

  * a key that is in the Lua and not in the JSON prints the key on screen;
  * a key used by two different lines makes the second one **inert** -- the
    engine has already marked it heard, so its codes never fire again, for
    that character, for the life of the save.

Both are designed out rather than tested for: the keys are *derived* from the
tape id and the line's index, so a duplicate is not expressible. A line that
deliberately repeats (a refrain, a title card that comes round again) passes
`key=` and says so out loud.

Writes, from the one list below:

    media/lua/shared/TREK/TREK_Tapes.lua
    media/lua/shared/Translate/EN/Recorded_Media.json

`LORE.md` is the design: what each tape is, why it is in the shelf, and the
engine facts underneath all of this.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# The mod's own media category. RecordedMedia.getMediaTypeForCategory is four
# instructions long -- "cds" is media type 0 and *everything else* is type 1,
# the tape type -- so this name only has to be ours and not vanilla's, and the
# cabin's television (Base.TvWideScreen, AcceptMediaType = 1) accepts it.
CATEGORY = "Trek-VHS"

# The present, and every tape does its arithmetic against this.
#
# Pinned by the arc rather than chosen: Section 31 deployed the Founder virus
# around 2375, and the Changeling who took it worked in isolation for "nearly
# sixty years" before finding this outpost. That puts now at about 2435, which
# is also two generations after TNG/DS9/Voyager as the canon requires.
#
# It is here because it has already caught one error: the talent night tape
# said "fifty-eight years old" when stardate 44390.7 is about 2367, and the
# answer is sixty-eight. A date in a comment is not a thing anybody checks.
NOW_YEAR = 2435

# Per-speaker line colour. addLine takes r, g, b per line and vanilla uses it
# to tell voices apart; these are four of vanilla's own values, so a Trek tape
# and a vanilla tape look like they came off the same shelf.
#
# Four is the ceiling. A fifth voice is soup at subtitle size.
VOICES = {
    "card": (1.00, 1.00, 1.00),   # on-screen text, title cards
    "dub":  (1.00, 0.75, 0.00),   # the pilot, talking over her own copy
    "mc":   (0.00, 0.69, 0.31),   # whoever is running the room
    "room": (0.00, 0.69, 0.94),   # everybody else in it
    "note": (0.44, 0.19, 0.63),   # what the camera sees and nobody says
    # One person talking straight down the lens. It shares the MC's green
    # deliberately: the name is for whoever is writing the tape, the colour is
    # what ships, and no tape has ever needed both a compere and a diarist.
    "solo": (0.00, 0.69, 0.31),
    # The pilot recording her own log. Deliberately the same amber as `dub`:
    # by the time a player reaches a ship's log they have already heard that
    # colour talking over the talent night tape, and recognising whose voice
    # this is should cost them nothing.
    "pilot": (1.00, 0.75, 0.00),
    # A voice on the other end of a comm link. Shares `room`'s blue: it is
    # still "somebody who is not the person holding the recorder", and the
    # player has already learned that colour means exactly that.
    "comms": (0.00, 0.69, 0.94),
    # The EMH, who is in the room rather than on a channel. Green, like every
    # other second party this shelf has had: he is the one talking back.
    "emh": (0.00, 0.69, 0.31),
    # Tucker Gold, on his own holo fragments (LORE.md 1c). The fragments'
    # cyan -- the emitter's lit face, the map's hexagon -- so the man and the
    # object he left read as one thing. His tapes carry no other speaker but
    # the camera and Shepard's dub, so it is never a fifth colour on a tape.
    "tucker": (0.60, 0.90, 1.00),
}

# The house effect: every line of every tape relieves boredom, the way every
# line of every vanilla tape does. Anything else a tape does is declared on
# the line that does it.
#
# Note on direction, because it is easy to get backwards: vanilla's warm media
# uses BOR-1, STS-n and UHP-n. `MOR` (morale) exists in ISRadioInteractions and
# no vanilla recorded line uses it, so its sign here is unproven and it is
# deliberately not used. Warmth is UHP-1.
HOUSE = "BOR-1"


def line(voice, text, codes=None, key=None):
    return {"voice": voice, "text": text, "codes": codes, "key": key}


# ---------------------------------------------------------------------------
# The tapes
# ---------------------------------------------------------------------------
# Era: the mod is set two generations after TNG/DS9/Voyager, so every Starfleet
# tape in the shelf is a fifty-to-sixty-year-old recording and the pilot who
# collected them is a historian by temperament. Nothing aboard is contemporary
# with the people in it. See LORE.md, "The canon".

# Every tape is in content/tapes/, one JSON file each, with its writing notes
# beside it (content/README.md). This file is only the machinery.
import content  # noqa: E402

TAPES = content.load_tapes()


# ---------------------------------------------------------------------------
# Writing it out
# ---------------------------------------------------------------------------

def key_for(tape, index, explicit):
    """A line's translation key, and therefore its learning identity.

    Derived rather than chosen, so two lines cannot collide by accident. An
    explicit key is a deliberate repeat and is the caller's problem.
    """
    if explicit:
        return "RM_%s" % explicit
    return "RM_%s_%02d" % (tape["id"], index)


def build():
    text = {}
    entries = []

    for tape in TAPES:
        ident = tape["id"]
        fields = {}
        for field, suffix in (("display", "name"), ("title", "title"),
                              ("subtitle", "sub"), ("author", "author"),
                              ("extra", "extra")):
            value = tape.get(field)
            if not value:
                fields[field] = None
                continue
            key = "RM_%s_%s" % (ident, suffix)
            fields[field] = key
            text[key] = value

        lines = []
        for index, entry in enumerate(tape["lines"], start=1):
            voice = entry["voice"]
            if voice not in VOICES:
                raise SystemExit("tape %s line %d: unknown voice %r"
                                 % (ident, index, voice))
            key = key_for(tape, index, entry["key"])
            if key in text and text[key] != entry["text"]:
                raise SystemExit("tape %s line %d: key %s already means "
                                 "something else" % (ident, index, key))
            text[key] = entry["text"]
            codes = HOUSE if not entry["codes"] else "%s,%s" % (HOUSE, entry["codes"])
            r, g, b = VOICES[voice]
            lines.append((key, r, g, b, codes))

        entries.append((tape, fields, lines))

    return entries, text


def lua_string(value):
    return "nil" if value is None else '"%s"' % value


def write_lua(path, entries):
    out = []
    out.append("-- GENERATED by tools/gen_tapes.py -- do not edit by hand.")
    out.append("--")
    out.append("-- The ship's tape shelf. Every string here is a translation key;")
    out.append("-- the text is in Translate/EN/Recorded_Media.json and both files")
    out.append("-- come out of the generator together, because a key that does not")
    out.append("-- resolve prints itself on screen and a key used twice makes the")
    out.append("-- second line silently inert. See LORE.md.")
    out.append("")
    out.append("-- Vanilla's shared/RecordedMedia/ISRecordedMedia.lua registers")
    out.append("-- everything in this table on OnInitRecordedMedia, so adding to it")
    out.append("-- is the whole of the integration. The handler at the bottom is")
    out.append("-- insurance against a load order where our table is filled after")
    out.append("-- vanilla has already walked it, and it registers only what the")
    out.append("-- engine does not already have -- registering an id twice is not")
    out.append("-- something the engine is known to survive.")
    out.append("RecMedia = RecMedia or {}")
    out.append("")

    ids, shelf = [], []
    for tape, fields, lines in entries:
        ids.append(tape["id"])
        # An `issued` tape is registered like any other and is not on the
        # shelf from the first build: the channel hands it to the ship when
        # the story gets there (COMMS.md 4, LORE.md 6), and TREK_Build puts it
        # on the shelf then.
        if not tape.get("issued"):
            shelf.append(tape["id"])
        out.append('-- %s' % tape["title"])
        out.append('RecMedia["%s"] = {' % tape["id"])
        out.append("    itemDisplayName = %s," % lua_string(fields["display"]))
        out.append("    title = %s," % lua_string(fields["title"]))
        out.append("    subtitle = %s," % lua_string(fields["subtitle"]))
        out.append("    author = %s," % lua_string(fields["author"]))
        out.append("    extra = %s," % lua_string(fields["extra"]))
        out.append("    spawning = %d," % tape.get("spawning", 0))
        out.append('    category = "%s",' % CATEGORY)
        out.append("    lines = {")
        for key, r, g, b, codes in lines:
            out.append('        { text = "%s", r = %.2f, g = %.2f, b = %.2f, codes = "%s" },'
                       % (key, r, g, b, codes))
        out.append("    },")
        out.append("}")
        out.append("")

    out.append("-- The ids the ship is issued with, in shelf order. TREK_Build")
    out.append("-- reads this to stock the tape shelf, so a tape added above")
    out.append("-- reaches the shelf without a second list to keep in step.")
    out.append("TREK_TapeIds = {")
    for ident in shelf:
        out.append('    "%s",' % ident)
    out.append("}")
    out.append("")
    out.append("-- Every tape this mod registers, the issued ones included: the")
    out.append("-- registration below has to cover a tape that is not on the shelf")
    out.append("-- yet, or it arrives blank.")
    out.append("TREK_AllTapeIds = {")
    for ident in ids:
        out.append('    "%s",' % ident)
    out.append("}")
    out.append("")
    out.append("Events.OnInitRecordedMedia.Add(function(rc)")
    out.append("    if not rc then return end")
    out.append("    for _, id in ipairs(TREK_AllTapeIds) do")
    out.append("        local known = nil")
    out.append("        local ok = pcall(function() known = rc:getMediaData(id) end)")
    out.append("        if ok and not known then")
    out.append("            local v = RecMedia[id]")
    out.append("            if v then")
    out.append("                local data = rc:register(v.category, id,")
    out.append("                                         v.itemDisplayName, v.spawning or 0)")
    out.append("                if data then")
    out.append("                    if v.title then data:setTitle(v.title) end")
    out.append("                    if v.subtitle then data:setSubtitle(v.subtitle) end")
    out.append("                    if v.author then data:setAuthor(v.author) end")
    out.append("                    if v.extra then data:setExtra(v.extra) end")
    out.append("                    for _, j in ipairs(v.lines) do")
    out.append("                        data:addLine(j.text, j.r, j.g, j.b, j.codes)")
    out.append("                    end")
    out.append("                end")
    out.append("            end")
    out.append("        end")
    out.append("    end")
    out.append("end)")
    out.append("")

    path.write_text("\n".join(out), encoding="utf-8")


def write_text(path, text):
    body = json.dumps(text, indent=4, ensure_ascii=True, sort_keys=True)
    path.write_text(body + "\n", encoding="utf-8")


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    base = Path(sys.argv[1])
    if not base.is_absolute():
        base = ROOT / base

    entries, text = build()

    lua = base / "media/lua/shared/TREK/TREK_Tapes.lua"
    json_path = base / "media/lua/shared/Translate/EN/Recorded_Media.json"
    lua.parent.mkdir(parents=True, exist_ok=True)
    json_path.parent.mkdir(parents=True, exist_ok=True)
    write_lua(lua, entries)
    write_text(json_path, text)

    total = sum(len(lines) for _, _, lines in entries)
    longest = max((len(e["text"]), e["text"]) for t in TAPES for e in t["lines"])
    print("%d tape(s), %d lines, %d keys" % (len(entries), total, len(text)))
    print("longest line %d chars: %s" % longest)
    # Printed relative to the repo when it is inside it, absolute otherwise:
    # generating into a scratch directory to diff against the committed output
    # is the only way to answer "has the generator been run since the last
    # edit", and `relative_to` throws for a path outside ROOT.
    def show(path):
        try:
            return str(path.relative_to(ROOT))
        except ValueError:
            return str(path)

    print("wrote %s" % show(lua))
    print("wrote %s" % show(json_path))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
