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
        "extra": "Dubbed from the Archive copy. Sixty-eight years old.",
        "spawning": 0,
        "lines": [
            line("card", "PERSONAL RECORDING -- DO NOT ARCHIVE"),
            line("card", "TEN FORWARD, DECK TEN -- STARDATE 44390.7"),
            line("dub", "The television is a surface artifact. I logged it as one."),
            line("dub", "Then I found out what else it plays, and here we are."),
            line("dub", "Sixty-eight years old, and nobody has watched this."),
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
            line("solo", "It is a small galaxy. I want to be clear about that."),
            line("solo", "My closest friend here is Tuvok's great-granddaughter."),
            line("solo", "Yes. That Tuvok. I know. I know."),
            line("solo", "We worked it out in the mess hall, on a padd."),
            line("solo", "Twenty minutes and a great many arrows."),
            line("solo", "Her family, my family, and you in the middle of it."),
            line("solo", "Half of you was her great-grandfather. So we did the sums."),
            line("solo", "We are cousins. Sort of. There is no form for that."),
            line("solo", "She says that makes us complicated."),
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
    {
        # -------------------------------------------------------------------
        # The ship's log, entry one. The mod's premise, in the voice of the
        # person it happened to, and the tape that does the most work of any
        # in the shelf.
        #
        # **It is also the retcon that explains the cabin.** Every vanilla
        # object in this ship -- the fridge, the oven, the counters, the
        # theatre chair, the lamp, the lockers, the television -- has never had
        # an in-fiction reason to be aboard a Starfleet shuttle. Now it does:
        # she collected them. The survey specialist furnished her field station
        # with what she was studying, and her department calls that method. One
        # tape, and twenty-four squares of borrowed PZ furniture stop being a
        # compromise and become a character trait.
        #
        # It ends by planting Section 31 **without naming it**, because the
        # misdirection has to be honestly reasoned rather than a lie: a hidden
        # outpost with no relay and no traffic really is the shape of something
        # deniable, and she is right about that and wrong about who did it.
        # Entry four is where she argues herself into the wrong answer; entry
        # five is the Changeling.
        #
        # On the shelf from the start. No XP: this is the opening, and charging
        # a tutorial in experience points cheapens both.
        "id": "TREK_LogOne",
        "display": "Ship's Log, Entry One",
        "title": "Personal Log -- Entry One",
        "subtitle": "Lt. Lucy Shepard, cultural survey, U.S.S. Adirondack",
        "author": "recorded aboard this shuttle",
        "extra": "Ten February. For whoever is standing in my cabin.",
        "spawning": 0,
        "lines": [
            line("card", "PERSONAL LOG -- LT. LUCY SHEPARD"),
            line("card", "CULTURAL SURVEY DETACHMENT, U.S.S. ADIRONDACK"),
            line("card", "DAY TWO -- TEN FEBRUARY, LOCAL RECKONING"),
            line("pilot", "If you are watching this, you are in my shuttle."),
            line("pilot", "Everything in here is mine. I will explain the fridge."),
            line("pilot", "Start at the beginning. I asked for this posting."),
            line("pilot", "Nobody asks for this posting. I asked for it twice."),
            line("card", "-- THE WORLD --"),
            line("pilot", "A world so like Earth the first survey was recalled."),
            line("pilot", "They logged it as a sensor fault. It was not."),
            line("pilot", "Same continents, near enough. Same century, near enough."),
            line("pilot", "Combustion engines. Magnetic tape. No global network."),
            line("pilot", "They have a Kentucky. I want you to sit with that."),
            line("pilot", "My job was to watch and write it down. That is all."),
            line("card", "-- THE CABIN --"),
            line("pilot", "Which brings me to the fridge. And the oven. And the chair."),
            line("pilot", "You cannot understand a people from orbit. So I furnished."),
            line("pilot", "All of it came up from down there, logged item by item."),
            line("pilot", "The counters. The lockers. The lamp. The television."),
            line("pilot", "I ate what they ate. I sat the way they sit."),
            line("pilot", "My department calls that method. The ship called it clutter."),
            line("pilot", "The television is the best thing I ever carried up."),
            line("pilot", "It plays tape. So I put everything I love onto tape."),
            line("pilot", "Favourite videos. Holos, flattened. Transcripts, read out."),
            line("pilot", "All of it dubbed down onto magnetic tape, like a local."),
            line("pilot", "There is a rack of them by the screen. Any order you like."),
            line("card", "-- THE WORK --"),
            line("pilot", "Beam down at dawn, beam up before dark. Six months of it."),
            line("pilot", "Market days. Radio broadcasts. A couple weddings."),
            line("pilot", "I was going to get a paper out of this. A good one."),
            line("note", "She stops. Something is beeping off camera. She ignores it."),
            line("card", "-- AND THEN THE NINTH --"),
            line("pilot", "On the ninth of February we lost the Adirondack."),
            line("pilot", "Not destroyed. Damaged. She is still up there."),
            line("pilot", "She cannot leave. There might be hope."),
            line("pilot", "A hundred and forty-one of us. She cannot leave.",
                 codes="UHP+1"),
            line("pilot", "Nothing attacked her. Nothing was on sensors at all."),
            line("pilot", "Eleven of us were on the surface. We still are."),
            line("pilot", "So far down there, nothing is wrong."),
            line("pilot", "The markets opened this morning. The radio is playing."),
            line("pilot", "I am stranded above a world having an ordinary week."),
            line("card", "-- ON THE RECORD --"),
            line("pilot", "Starfleet does not know we are here. That was the point."),
            line("pilot", "A hidden outpost. No relay, no traffic, nothing filed."),
            line("pilot", "I used to think that was good tradecraft."),
            line("pilot", "I have had a lot of time to think about who benefits."),
            line("pilot", "I am going to keep recording. Somebody should."),
            line("card", "END OF ENTRY ONE"),
        ],
    },
    {
        # -------------------------------------------------------------------
        # Entry two: the wrong answer, said out loud, and the call that gets
        # answered.
        #
        # Two things this tape has to carry, and both are load-bearing outside
        # the fiction:
        #
        #  * **"We can still transport."** This is where every survivor the
        #    player rescues actually goes. `ROADMAP2.md` 1.7 decided the first
        #    rescue does not need to put the ensign aboard the shuttle -- "a
        #    safe off-screen recovery avoids creating a second persistent
        #    person object" -- and that decision was mechanics looking for a
        #    reason. Now it has one: there is a ship overhead that cannot move
        #    and can still catch a transporter beam.
        #  * **Why Shepard is on the ground and not up there.** She is the only
        #    person in the detachment who spent six months learning how these
        #    people boil water, and on the twelfth of July that stopped being
        #    an academic interest. It also explains why the player inherits a
        #    shuttle rather than a derelict: she chose to stay and use it.
        #
        # The Section 31 accusation is made **outright** here, early, and with
        # her own admission that she has no evidence -- "a shape, and the shape
        # fits". That is what keeps the misdirection honest: she is reasoning
        # from a real Federation precedent, she says so, and she is wrong.
        "id": "TREK_LogTwo",
        "display": "Ship's Log, Entry Two",
        "title": "Personal Log -- Entry Two",
        "subtitle": "Lt. Lucy Shepard, cultural survey, U.S.S. Adirondack",
        "author": "recorded aboard this shuttle",
        "extra": "Day nineteen. Somebody answered.",
        "spawning": 0,
        "lines": [
            line("card", "PERSONAL LOG -- ENTRY TWO"),
            line("card", "DAY NINETEEN -- TWENTY-SEVEN FEBRUARY"),
            line("pilot", "Nineteen days. Talking to myself for nineteen days."),
            line("pilot", "Today somebody answered. I will get to that."),
            line("card", "-- WHAT I THINK THIS IS --"),
            line("pilot", "I want this on record before anyone talks me out of it."),
            line("pilot", "A hidden outpost. No relay. Nothing filed with anyone."),
            line("pilot", "A world nobody has declared, above nobody's jurisdiction."),
            line("pilot", "And then somebody quietly took our engines and our array."),
            line("pilot", "From the inside. Without hurting a single person."),
            line("pilot", "That is not an attack. That is somebody closing a door."),
            line("pilot", "I have read the Dominion War files. The parts left in."),
            line("pilot", "Section 31 has done worse than this, and done it to us."),
            line("pilot", "So I will say it plainly. I think this is Section 31."),
            line("pilot", "I have no evidence. I have a shape, and the shape fits."),
            line("note", "She says the name like somebody testing a door."),
            line("card", "-- THE ADIRONDACK --"),
            line("pilot", "I have called every six hours since the ninth."),
            line("pilot", "Today the carrier came back. Thin, but it came back."),
            line("comms", "--epeat. Adirondack actual. Shepard, is that you?"),
            line("pilot", "I did not say anything for about four seconds.",
                 codes="STS-0.2"),
            line("comms", "We are intact. Hull is sound. Everyone aboard is fed."),
            line("comms", "We are not going anywhere. Warp is gone. Impulse too."),
            line("pilot", "She is a very expensive orbital platform now.",
                 codes="UHP+1"),
            line("comms", "We can still transport. That is the one thing we kept."),
            line("pilot", "Write that down, whoever you are. They can transport."),
            line("pilot", "Anyone you get onto clear ground can go up. Anyone."),
            line("card", "-- THE PLAN --"),
            line("comms", "Lucy. Come up. That is a request, not an order."),
            line("pilot", "No thanks. I can do more down here."),
            line("pilot", "Up there is a corridor, a mess hall and a viewport."),
            line("pilot", "Down here is an intact pre-contact culture, mid-century."),
            line("pilot", "Nobody is coming for years. That is years of fieldwork."),
            line("pilot", "I am not going to spend them in a corridor."),
            line("pilot", "And I am the only one of us who can pass for a local."),
            line("pilot", "Six months of learning how these people live will do that."),
            line("pilot", "So I stay. Ten others stayed. For the work."),
            line("card", "-- ENTRY TWO ENDS --"),
            line("pilot", "Nineteen days, and somebody answered. Good day.",
                 codes="UHP-1,STS-0.2"),
            line("pilot", "I am going to go and be useful."),
        ],
    },
    {
        # Entry three: the attack, reconstructed. The horror entry, and the
        # first tape that describes what the player is standing in.
        #
        # The order is the whole argument: **the ship went first.** Warp, then
        # impulse, then the long-range array -- three systems in the order you
        # would pick if you wanted a witness that could neither leave nor call,
        # and nobody aboard was hurt. She notices that and cannot explain it,
        # which is entry six's answer arriving two hundred days early.
        #
        # "From the inside, with nothing on sensors" is the only clue planted
        # here, and it is planted without comment.
        "id": "TREK_LogThree",
        "display": "Ship's Log, Entry Three",
        "title": "Personal Log -- Entry Three",
        "subtitle": "Lt. Lucy Shepard, cultural survey, U.S.S. Adirondack",
        "author": "recorded aboard this shuttle",
        "extra": "Day one hundred and forty-one. They came back.",
        "spawning": 0,
        "lines": [
            line("card", "PERSONAL LOG -- ENTRY THREE"),
            line("card", "DAY 141 -- TWENTY-NINE JUNE"),
            line("pilot", "I have not recorded since March. There was nothing to say."),
            line("pilot", "For four months this was the best posting in Starfleet."),
            line("pilot", "Then this week. I am going to say it in order."),
            line("card", "-- TWENTY-SEVEN JUNE --"),
            line("pilot", "I was at a market north of the county, beaming up."),
            line("pilot", "Four people on the ground with a fever. Only four."),
            line("pilot", "I logged it as seasonal. I wrote the word seasonal down."),
            line("card", "-- TWENTY-EIGHT JUNE --"),
            line("pilot", "By morning the hospital had queues out of the doors."),
            line("pilot", "By afternoon it had queues and no staff."),
            line("pilot", "By dark the roads were the loudest thing on the continent."),
            line("pilot", "I watched all of it from up here with a log running."),
            line("card", "-- TWENTY-NINE JUNE --"),
            line("pilot", "Quiet. Not empty. Quiet is different, and it is worse."),
            line("pilot", "Every plague I have studied takes weeks. This took two days."),
            line("pilot", "Nothing moves that fast. Nothing natural. Record that."),
            line("card", "-- ALSO --"),
            line("pilot", "In February somebody took our engines and our array."),
            line("pilot", "Warp core, then impulse, then long range. In that order."),
            line("pilot", "Nothing on sensors. The damage came from inside the hull."),
            line("pilot", "Nobody up there was hurt. I never understood that part."),
            line("pilot", "I understand it now. We were never the target."),
            line("pilot", "We were the witnesses. They blinded us and went away.",
                 codes="UHP+1"),
            line("pilot", "Five months. They waited five months to be sure of us."),
            line("card", "-- WHAT I CAN SEE --"),
            line("pilot", "It is this region. As far as I can scan, only this region."),
            line("pilot", "One county, one river valley, a few towns past it."),
            line("pilot", "If this is a test, it was given a boundary on purpose."),
            line("card", "-- OUR PEOPLE --"),
            line("pilot", "Eleven of us stayed on the ground. For the work."),
            line("pilot", "I have reached three of them. I am going to keep going."),
            line("pilot", "If you are watching this: look for them. Some are alive."),
            line("pilot", "Get them onto clear ground. The ship can still transport."),
            line("card", "-- WHAT I KNEW --"),
            line("pilot", "I have eleven months of field notes on these people."),
            line("pilot", "Names. Households. Who argues at the feed store."),
            line("pilot", "A woman sold preserves, two stalls in from the road."),
            line("pilot", "She asked me every week whether I was eating enough."),
            line("pilot", "My notes have her as Subject Fourteen. In writing.",
                 codes="UHP+1"),
            line("note", "The recording stops. What follows is a new session."),
            line("pilot", "Her name was Ruth. I am correcting the file.",
                 codes="UHP+1"),
            line("card", "-- ENTRY THREE ENDS --"),
        ],
    },
    {
        # Entry four: the science, and the sick bay's hologram earning a plot
        # rather than staying a utility.
        #
        # **Their chemistry is correct and only the attribution is wrong**, and
        # that distinction is the whole design of the misdirection. The Doctor
        # says so himself -- he can support the chemistry and not the author --
        # so the tape carries its own correction and a second watch finds it.
        # He is right, she overrules him, and she is the one who is wrong.
        "id": "TREK_LogFour",
        "display": "Ship's Log, Entry Four",
        "title": "Personal Log -- Entry Four",
        "subtitle": "Lt. Lucy Shepard and the Emergency Medical Hologram",
        "author": "recorded aboard this shuttle",
        "extra": "Day 146. What the Doctor found.",
        "spawning": 0,
        "lines": [
            line("card", "PERSONAL LOG -- ENTRY FOUR"),
            line("card", "DAY 146 -- FOUR JULY"),
            line("pilot", "I have been running samples. I am not a physician."),
            line("pilot", "So I turned the EMH on. He has been on ever since."),
            line("emh", "Please state the nature of the-- yes. Hello, Lieutenant."),
            line("pilot", "He does that every time. I stopped asking him not to."),
            line("card", "-- WHAT IT IS --"),
            line("emh", "It is not a virus in the sense you are using the word."),
            line("emh", "It is engineered. I am being careful with that word."),
            line("emh", "Nothing in it is accidental. There is no waste in it."),
            line("pilot", "Explain that part for the recording."),
            line("emh", "Nature is wasteful. This is not. Somebody edited it."),
            line("card", "-- WHAT IS STRANGE --"),
            line("emh", "There are morphogenic markers all through the structure."),
            line("emh", "Shapeshifter biology. Not humanoid. Not viral. Changeling."),
            line("pilot", "Changelings?"),
            line("emh", "The scaffold is a morphogenic pathogen. I am confident."),
            line("emh", "The payload attacks humanoid neural tissue. Also confident."),
            line("emh", "Those two things do not belong in one organism."),
            line("card", "-- WHAT WE THINK IT MEANS --"),
            line("pilot", "There is exactly one morphogenic pathogen on record."),
            line("pilot", "Section 31 built it. They used it on the Founders."),
            line("emh", "Well obviously someone has rebuilt it."),
            line("pilot", "So they kept it. Of course they kept it. And improved it."),
            line("pilot", "Then they found a world with no witnesses and tried it."),
            line("emh", "That is one conclusion. I can only support the chemistry."),
            line("emh", "I cannot support the author.", codes="STS-0.2"),
            line("pilot", "Noted. Recorded. I still think I am right."),
            line("pilot", "If I am wrong about who, I am not wrong about what."),
            line("card", "-- ENTRY FOUR ENDS --"),
            line("emh", "Lieutenant. You have been awake for twenty-six hours."),
            line("pilot", "Goodnight, Doctor."),
            line("emh", "Goodnight, Lucy.", codes="UHP-1"),
        ],
    },
    {
        # Entry five: the misdirection broken by the accused.
        #
        # Section 31 is aboard, and the denial is credible **because they had
        # every reason to lie and did not bother**: "No. But then I would not be
        # calling you." That is a better exit from a wrong theory than the
        # detective spotting her own flaw, and it leaves her with something
        # worse than a villain -- an absence.
        #
        # The Prime Directive argument is the one this shelf was always going to
        # have to hold, and it is deliberately **not resolved**. She refuses to
        # finish the sentence on the record, which is the only honest thing
        # somebody in her position does.
        "id": "TREK_LogFive",
        "display": "Ship's Log, Entry Five",
        "title": "Personal Log -- Entry Five",
        "subtitle": "Lt. Lucy Shepard, cultural survey, U.S.S. Adirondack",
        "author": "recorded aboard this shuttle",
        "extra": "Day 149. Nobody is coming.",
        "spawning": 0,
        "lines": [
            line("card", "PERSONAL LOG -- ENTRY FIVE"),
            line("card", "DAY 149 -- SEVEN JULY"),
            line("pilot", "Ten days since the county died. I am not sleeping much."),
            line("pilot", "This week has been eventful"),
            line("card", "-- THE ARRAY --"),
            line("comms", "Lt Shepard. We owe you something. The long-range array is gone."),
            line("comms", "Not damaged. Gone. It went with the drive in February."),
            line("pilot", "I asked how long they had known. They had always known."),
            line("comms", "We did not want you to stop looking for our people."),
            line("pilot", "I have not stopped. I will not stop. Say the rest."),
            line("comms", "Nobody filed this posting. Nobody expects a report."),
            line("comms", "No relay inside forty light years. Nobody is coming."),
            line("pilot", "I already knew. Hearing it is a different organ.",
                 codes="UHP+1"),
            line("card", "-- THE ARGUMENT UP THERE --"),
            line("pilot", "So the wardroom is arguing about coming down for good."),
            line("pilot", "A hundred and forty-one people, a valley, no way home."),
            line("pilot", "And somebody said: Prime Directive. They are not wrong."),
            line("pilot", "You do not settle a pre-warp world. That is rule one."),
            line("pilot", "Then somebody said: what culture are we contaminating?"),
            line("note", "A long pause on the tape. She does not fill it."),
            line("pilot", "My field notes answer that, and I hate all of them."),
            line("pilot", "The rule was written for a living civilisation. This one--"),
            line("pilot", "I am not finishing that sentence on a recording."),
            line("pilot", "I said not yet. I am staying down. Ask me in a month."),
            line("card", "-- THEN --"),
            line("pilot", "Last night somebody called on a channel I did not know."),
            line("comms", "Lieutenant. You have been using a word on an open log."),
            line("comms", "I am the reason that word is classified. I am aboard."),
            line("pilot", "I will not put a name in this file. They asked."),
            line("comms", "It is not ours. I would know. It is not ours."),
            line("pilot", "I asked if they would tell me if it were."),
            line("comms", "No. But then I would not be calling you."),
            line("note", "She says afterwards that she believed them. She sounds tired."),
            line("pilot", "So: a Federation weapon that is not the Federation's."),
            line("pilot", "Five months angry at the wrong people?"),
            line("pilot", "I would like the wrong people back.", codes="UHP+1"),
            line("card", "-- ENTRY FIVE ENDS --"),
        ],
    },
    {
        # Entry six: the truth, and why the shuttle is standing empty with
        # somebody's tapes still in the rack.
        #
        # The reveal is deliberately not a twist. It is an explanation, and the
        # worst of it is that Shepard -- an anthropologist -- can state the
        # motive in one reasonable sentence and then cannot put it down.
        #
        # **Why she leaves:** a chair moved. Nothing broken, nothing taken, a
        # chair in a different place. That is the theatre chair at 1,2 the
        # player sits in to watch these tapes, which is as close as this shelf
        # comes to reaching out of the screen -- and it gives her a reason to go
        # up that is neither cowardice nor a plot device.
        #
        # She ends by handing the rack over, which closes the loop on entry
        # one's first line.
        "id": "TREK_LogSix",
        "display": "Ship's Log, Entry Six",
        "title": "Personal Log -- Entry Six",
        "subtitle": "Lt. Lucy Shepard -- final entry aboard",
        "author": "recorded aboard this shuttle",
        "extra": "Day 151. The last one.",
        "spawning": 0,
        "lines": [
            line("card", "PERSONAL LOG -- ENTRY SIX"),
            line("card", "DAY 151 -- NINE JULY"),
            line("pilot", "Our exobiologist has not slept in three days. She has it."),
            line("card", "-- WHAT IT IS --"),
            line("comms", "The morphogenic scaffold is not a copy. It is the original."),
            line("comms", "Same lineage. Same lab work. Sixty years of refining."),
            line("pilot", "Say the part you said to me first."),
            line("comms", "Whatever built this was a Changeling, and it worked alone."),
            line("card", "-- WHO --"),
            line("pilot", "One of them left the Link. On purpose. Carrying the file."),
            line("pilot", "Section 31 tried to kill a species and very nearly did."),
            line("pilot", "One of that species walked out of the ocean and kept it."),
            line("pilot", "Sixty years, alone, turning our weapon into theirs."),
            line("card", "-- WHY HERE --"),
            line("pilot", "Because of what this place is. Because of what we made it."),
            line("pilot", "A near-perfect copy of the world that built Section 31."),
            line("pilot", "No treaty. No relay. No record that anybody is here."),
            line("pilot", "We chose this outpost and the Changeling knew we'd find it."),
            line("pilot", "This world was impossible to ignore and the perfect test bed.",
                 codes="UHP+1"),
            line("pilot", "And the ship went first, from the inside, off sensors."),
            line("pilot", "I have stopped wondering how something got aboard."),
            line("card", "-- WHAT I THINK ABOUT IT --"),
            line("pilot", "I am an anthropologist. I can write its motive in a line."),
            line("pilot", "Somebody tried to erase its people. This is the reply."),
            line("pilot", "That sentence is reasonable. That is what I cannot put down.",
                 codes="UHP+1"),
            line("card", "-- WHY I AM GOING UP --"),
            line("pilot", "Two days ago something moved a chair in this cabin."),
            line("pilot", "Nothing is broken. Nothing is missing. A chair moved."),
            line("pilot", "I have been careful, and I think I was careful too late."),
            line("pilot", "It knows where I am. I will not stay to be a data point.",
                 codes="STS+0.2"),
            line("note", "Then, much quieter, and clearly not for the file:"),
            line("pilot", "I was going to write such a good paper about this place.",
                 codes="UHP+1"),
            line("card", "-- FOR WHOEVER IS STANDING HERE --"),
            line("pilot", "The shuttle is yours. I am leaving her where she sits."),
            line("pilot", "If you are Starfleet you already know what to do."),
            line("pilot", "If you are a native I'm sorry your world got destroyed."),
            line("pilot", "The rack by the screen is everything I loved."),
            line("pilot", "Watch them in any order. Somebody should.", codes="UHP-1"),
            line("pilot", "And find our people. Get them onto clear ground."),
            line("pilot", "The Adirondack is still up there. She is still listening."),
            line("pilot", "Maybe we will meet up there."),
            line("pilot", "Shepard out."),
            line("card", "END OF LOG"),
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
