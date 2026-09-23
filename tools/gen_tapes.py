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

TAPES = [
    {
        "id": "TREK_TalentNight",
        "display": "Talent Night (dubbed)",
        "title": "Ten Forward Talent Night",
        "subtitle": "U.S.S. Enterprise NCC-1701-D, stardate 44390.7",
        "author": "personal recording, name withheld",
        "extra": "Dubbed from the Archive copy. Fifty-eight years old.",
        "spawning": 0,
        "lines": [
            line("card", "PERSONAL RECORDING -- DO NOT ARCHIVE"),
            line("card", "TEN FORWARD, DECK TEN -- STARDATE 44390.7"),
            line("dub", "The television is a surface artifact. I logged it as one."),
            line("dub", "Then I found out what else it plays, and here we are."),
            line("dub", "Fifty-eight years old, and nobody has watched this."),
            line("note", "The camera is on a table at the back. Nobody adjusts it."),
            line("mc", "Ladies, gentlemen, others: Ten Forward Talent Night."),
            line("mc", "House rules. No phasers, no holograms, no encores."),
            line("note", "Somebody at the bar says NO ENCORES again, louder."),
            line("mc", "First up. Commander Riker, on the trumpet."),
            line("room", "Trombone."),
            line("mc", "On the trombone. Commander Riker."),
            line("note", "Four minutes of trombone. It is genuinely good."),
            line("note", "Seven minutes of trombone. It is still genuinely good."),
            line("note", "Nine. The bar has quietly started serving again."),
            line("room", "Will. Will. There are seventeen acts."),
            line("mc", "Thank you, Commander. Thank you. Commander."),
            line("mc", "Lieutenant Commander Data. Reading his own work."),
            line("note", "He announces eighteen stanzas. He is not joking."),
            line("note", "Stanza four is about the cat's indifference to poetry."),
            line("note", "Stanza eleven is about the cat's indifference to him."),
            line("note", "By fourteen the room has stopped finding it funny."),
            line("note", "By eighteen they are applauding, and they mean it.",
                 codes="STS-0.2"),
            line("mc", "Doctor Crusher. Who has done this professionally."),
            line("note", "She taps. The deck is not sprung. She does not care."),
            line("mc", "Lieutenant Worf has declined to participate."),
            line("room", "He has not declined. He has been entered."),
            line("note", "A long silence. Then forty seconds of Klingon opera."),
            line("note", "Nobody in the room breathes through any of it.",
                 codes="STS-0.2,UHP-1"),
            line("room", "...Mister Worf, that was extraordin--"),
            line("room", "I have declined to participate."),
            line("mc", "Ensign Ruiz. Impressions of the senior staff."),
            line("note", "Engineering, security, medical. Cruel and exact."),
            line("note", "He starts on the captain. He is eleven words in."),
            line("note", "He looks at table six. The captain is at table six."),
            line("room", "Do go on, Ensign."),
            line("note", "He does not go on. He sits down. They are merciless."),
            line("mc", "Lieutenant Barclay is on the list and not in the room."),
            line("card", "-- recording continues --"),
            line("note", "The room empties. Nobody switches the camera off."),
            line("note", "Two people stack chairs and argue about the trombone."),
            line("dub", "That is why I keep these. Somebody stacked the chairs."),
            line("dub", "There are nineteen more. Start with this one.",
                 codes="UHP-1"),
        ],
    },
    {
        # The shelf's namesake, and the tape the whole lore idea started from.
        #
        # **It is a school assignment and it is cheerful the whole way down.**
        # Everything about the subject invites grief and the tape refuses it:
        # there is no anger, nothing rehearsed, and no mention of what was done
        # to him. It is a first-year cadet who got genuinely interested in his
        # own homework and wants to show his working. The sadness is entirely
        # the viewer's, and it arrives about four lines after the kid has
        # cheerfully moved on -- which costs the writing nothing to produce and
        # is the reason this tape works at all.
        #
        # "School assignment" and "the author was in Starfleet" resolve to the
        # **Academy**: a heritage seminar, year one, which is also why a
        # twenty-year-old is addressing a dead ancestor down a lens. The brief
        # asked him to.
        "id": "TREK_Tuvix",
        "display": "Dear Grandpa Tuvix",
        "title": "Dear Grandpa Tuvix",
        "subtitle": "Starfleet Academy heritage seminar, assignment four",
        "author": "first-year cadet, name withheld",
        "extra": "Dubbed from a friend's copy. He got an A minus.",
        "spawning": 0,
        "lines": [
            line("card", "STARFLEET ACADEMY -- HERITAGE SEMINAR, YEAR ONE"),
            line("card", "ASSIGNMENT FOUR: ADDRESS IT TO THEM"),
            line("dub", "A friend sent me this one. I have watched it a lot."),
            line("solo", "Hi. Okay. This is for my heritage assignment."),
            line("solo", "We had to pick an ancestor and talk to them. So."),
            line("solo", "Dear Grandpa Tuvix. That still sounds strange."),
            line("note", "He is reading off a padd and keeps losing his place."),
            line("solo", "I did the research first. The research was the fun part."),
            line("solo", "You go back up the maternal line and it is all names."),
            line("solo", "Names, postings, transfer dates. Hundreds of them."),
            line("solo", "And then there is you, and you are not a name."),
            line("solo", "You are a species with one member and no precedent."),
            line("solo", "I sat there for an hour. Then I changed my subject."),
            line("card", "-- WHAT I FOUND --"),
            line("solo", "Grandma was Betazoid. Lower decks. Voyager."),
            line("solo", "Ensign. Sensor maintenance. Nobody writes about her."),
            line("solo", "She was aboard for all eighteen of your days."),
            line("solo", "The service record says almost nothing. Her letters do."),
            line("solo", "She said you were the easiest person on that ship."),
            line("solo", "Seven years from home, and you were easy to be near."),
            line("note", "Off camera, somebody tells him to sit up straight."),
            line("solo", "So then: my mother. Talaxian, Vulcan and Betazoid."),
            line("solo", "Three ways at once, which the databases hate."),
            line("solo", "She walks into a room and the room settles down."),
            line("solo", "Telepath. Strong enough that we mention it like height.",
                 codes="STS-0.2"),
            line("solo", "She never joined up. She says the galaxy came to her."),
            line("solo", "I joined up. She thinks that is very funny."),
            line("card", "-- THE PART MY INSTRUCTOR DID NOT BELIEVE --"),
            line("solo", "It is a small galaxy. I want to be clear about that."),
            line("solo", "I am seeing someone. Her great-grandfather was Tuvok."),
            line("solo", "Yes. That Tuvok. I know. I know."),
            line("solo", "We worked it out on a third date, on a padd."),
            line("solo", "It took twenty minutes and a great many arrows."),
            line("solo", "Her family, my family, and you in the middle of it."),
            line("solo", "She says that makes us complicated.",),
            line("solo", "I said it makes us close.", codes="UHP-1"),
            line("card", "-- CONCLUSION --"),
            line("solo", "My instructor wants a thesis. Here is my thesis."),
            line("solo", "You existed for eighteen days and you are still arriving."),
            line("solo", "There are nine of us now. We all laugh the same way."),
            line("note", "He has clearly practised this. He is still nervous."),
            line("solo", "I would have liked you. I think you'd have liked us."),
            line("solo", "Anyway. That is the assignment. Thanks, Grandpa Tuvix."),
            line("card", "END OF SUBMISSION -- GRADE WITHHELD PENDING CITATIONS"),
            line("dub", "He got the A minus on appeal. He has never let it go.",
                 codes="UHP-1"),
        ],
    },
]


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

    ids = []
    for tape, fields, lines in entries:
        ids.append(tape["id"])
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
    for ident in ids:
        out.append('    "%s",' % ident)
    out.append("}")
    out.append("")
    out.append("Events.OnInitRecordedMedia.Add(function(rc)")
    out.append("    if not rc then return end")
    out.append("    for _, id in ipairs(TREK_TapeIds) do")
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
    print("wrote %s" % lua.relative_to(ROOT))
    print("wrote %s" % json_path.relative_to(ROOT))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
