"""The Adirondack channel, as written (COMMS.md 6).

The machinery is in tools/gen_comms.py; this file is only the conversation.
Run the generator after any edit here -- it refuses to write a tree that
fails its checks, and says which node and why.

House rules, from COMMS.md 3 and LORE.md 4, because they are the whole of the
style:

  * **A line is a shot.** Thirty to seventy characters. A speech is several
    lines, not one long one.
  * **Colour is the speaker.** Shepard amber, the Doctor green, the officer
    violet, anybody else aboard blue, the player grey.
  * **The player's options are characterisation, not a quiz.** No option is
    correct. At least one in every node is what a tired, frightened person
    actually says, which is usually shorter and ruder than the others.
  * **Write for the player who has not watched the logs, and let the one who
    has enjoy being ahead** (COMMS.md 4). Never a call that is nothing but a
    log read aloud.
  * **Nothing here confirms who the player is** (COMMS.md 6.1). She believes
    them or she does not, and the dialogue carries both for ever.

Tokens: %1 is the holder's first name, %2 the ensign most recently brought up
(or lost). Only use %1 in a line after the player has given it -- the flag
`named` -- or in the player's own options.
"""
from comms_vocab import say, opt, branch, node, thread

S, E, O, K, Y, CARD = "shepard", "emh", "officer", "crew", "you", "card"


# ---------------------------------------------------------------------------
# 6.1 First contact
# ---------------------------------------------------------------------------
# She is astonished anyone is aboard her shuttle. Three facts: she is alive,
# the ship cannot leave, they can still transport. And the player decides who
# they are, and the mod never says whether that is true.
FIRST = thread(
    "FIRST", "First contact", "incoming",
    day=7, forbids=["quiet"],
    entries=["01", "01M", "01MM"],
    nodes=[
        node("01",
             say(CARD, "INCOMING -- U.S.S. ADIRONDACK"),
             say(S, "Shuttlecraft, this is the Adirondack. Please respond."),
             say(S, "Somebody has been aboard my shuttle. The core says so."),
             say(S, "If you can hear me, say something. Anything at all."),
             options=[
                 opt("I hear you. Who is this?", "02"),
                 opt("Your shuttle? Finders keepers.", "02R"),
                 opt("Is anyone coming to get us?", "02H"),
             ],
             timeout=60, silence="01S"),
        node("01M",
             say(CARD, "INCOMING -- U.S.S. ADIRONDACK -- SECOND ATTEMPT"),
             say(S, "Shuttlecraft, Adirondack. Second time of asking."),
             say(S, "I know somebody is down there. The core keeps count."),
             say(S, "Pick up. Please."),
             options=[
                 opt("Sorry. I'm here. Who is this?", "02"),
                 opt("I was busy staying alive.", "02R"),
                 opt("Is anyone coming to get us?", "02H"),
             ],
             timeout=60, silence="01S"),
        node("01MM",
             say(CARD, "INCOMING -- U.S.S. ADIRONDACK"),
             say(S, "Third time. I'm going to assume you're busy."),
             say(S, "Or dead. I would rather busy. Answer if you can."),
             options=[
                 opt("Busy. Not dead. Go ahead.", "02"),
                 opt("Stop calling me.", "02R"),
             ],
             timeout=45, silence="01S"),
        node("01S",
             say(S, "Nothing. All right. Then I'll talk, and you listen."),
             say(S, "If you're hurt, or scared, that is fine. Just listen."),
             options=[opt("...Go on.", "02")]),
        node("02R",
             say(S, "Ha. No. Mine. Logged item by item, every lamp."),
             say(S, "But you're alive and you found her, so she's yours now."),
             say(S, "Look after her. She's the only one left down there."),
             options=[opt("Who are you?", "02")]),
        node("02H",
             say(S, "No. I'm sorry. Nobody is coming. Not for years."),
             say(S, "I'd rather tell you that now than have you hope."),
             options=[opt("Then who are you?", "02"),
                      opt("Great. Thanks.", "02")]),
        node("02",
             say(S, "Lieutenant Lucy Shepard. Cultural survey. And that"),
             say(S, "is my shuttle you're standing in. My fridge, my oven."),
             say(S, "My chair, which I would quite like back one day."),
             say(S, "I have talked to the same hundred and forty faces"),
             say(S, "since July. You are the first new voice in months."),
             options=[opt("Lucky me.", "03"),
                      opt("What happened to you?", "03"),
                      opt("July? What happened in July?", "03J")]),
        node("03J",
             say(S, "You know what happened in July. You're living in it."),
             say(S, "I meant up here. It's been a long summer in orbit."),
             options=[opt("Right. Sorry.", "03")]),
        node("03",
             say(S, "So. Who am I talking to?"),
             options=[
                 opt("I'm from around here. I found this in a field.", "04N"),
                 opt("Starfleet. Same as you.", "04S"),
                 opt("My name's %1. That's all you get.", "04X",
                     sets=["named"]),
                 opt("Doesn't matter who I am.", "04X"),
             ],
             timeout=60, silence="04Q"),
        node("04N",
             say(S, "A local. Of course you are. Of course you are."),
             say(S, "Then I owe you an apology, and it is a very big one."),
             say(S, "We were up here watching when it happened to you."),
             say(S, "We watched, and we wrote it down, and we did nothing."),
             options=[opt("You couldn't have stopped it.", "05"),
                      opt("Yeah. You did.", "05"),
                      opt("Write down what, exactly?", "05")]),
        node("04S",
             say(S, "Starfleet."),
             say(S, "Nobody told me. Nobody told any of us anything."),
             say(S, "I'll take it. I'm not in any position to check."),
             say(S, "And frankly, I've stopped caring whose side anyone is on."),
             options=[opt("Good. Neither have I.", "05"),
                      opt("I'm not here to argue.", "05")]),
        node("04X",
             say(S, "Fair. I wouldn't tell me either, after this summer."),
             options=[opt("So what do you want?", "05")]),
        node("04Q",
             say(S, "Nothing? All right. I'll call you the shuttle, then."),
             say(S, "Plenty of people up here I'd rather not know better."),
             options=[opt("...Fine.", "05")]),
        node("05",
             say(S, "Three things, and then you can hang up on me."),
             say(S, "One. I'm alive. So are a hundred and forty others."),
             say(S, "Two. The Adirondack cannot leave. No warp. No impulse."),
             say(S, "Three. We can still transport. That is what we kept."),
             options=[opt("Transport what, where?", "06"),
                      opt("Then get me out of here.", "06U"),
                      opt("Why tell me any of this?", "06W")]),
        node("06U",
             say(S, "I would. I can't. Not yet, and it isn't my call."),
             say(S, "The Doctor won't bring anyone up from the surface"),
             say(S, "until he knows how it spreads. Quarantine. Hard stop."),
             say(S, "I'm sorry. I know exactly what I'm asking you to live in."),
             options=[opt("Of course you do.", "06"),
                      opt("I'll hold you to 'not yet'.", "06")]),
        node("06W",
             say(S, "Because you're in my shuttle, and my shuttle works."),
             say(S, "And because there are people down there who are mine."),
             options=[opt("Go on.", "06")]),
        node("06",
             say(S, "Eleven of my crew stayed on the ground. For the work."),
             say(S, "Some of them are still calling. Distress beacons."),
             say(S, "Your shuttle hears them. I can't find them without you."),
             say(S, "Get to one, call it in, and we pull them up from here."),
             options=[opt("I'll see what I can do.", "07"),
                      opt("Why should I risk my neck for your people?", "06Q"),
                      opt("No promises.", "07")]),
        node("06Q",
             say(S, "You shouldn't. I'm not going to pretend otherwise."),
             say(S, "The ship pays for it. Patterns for the replicator,"),
             say(S, "supplies. And they would do it for you. Every one."),
             options=[opt("We'll see.", "07")]),
        node("07",
             say(S, "One more thing, and it's the one that matters to me."),
             say(S, "The tapes by the television. They're mine. Watch them."),
             say(S, "Everything I know about what happened is on those."),
             options=[opt("I have. All six logs.", "07A",
                          requires=["watched:TREK_LogSix"]),
                      opt("I'll get to them.", "08"),
                      opt("Not my kind of television.", "08")]),
        node("07A",
             say(S, "Then you know more than Starfleet does."),
             say(S, "That's a low bar. I'm sorry you had to clear it."),
             say(S, "And you know about the chair. Don't sit in it for me."),
             options=[opt("Too late.", "08"),
                      opt("It's a good chair.", "08")]),
        node("08",
             say(S, "I'll call again. Or you call me, off your PADD."),
             say(S, "Most of the time nobody answers up here. Try anyway."),
             say(S, "Shepard out."),
             sets=["met"]),
    ])


# ---------------------------------------------------------------------------
# The quiet path (COMMS.md 6.2)
# ---------------------------------------------------------------------------
# The player tells her to stop calling, and she does. Cheap, respectful, and a
# mod whose premise is "nobody is coming" should be able to honour somebody
# who would rather it stayed that way.
# Repeatable, with a day's cooldown: the one hail that is always there once
# you have met her, so it is also what "she picks up about once a day" means.
# Not repeatable, a player who said "wrong button" once would lose the quiet
# path for good.
QUIET = thread(
    "QUIET", "Stop calling", "hail",
    requires=["met"], forbids=["quiet"], repeatable=True, cooldown=24,
    nodes=[
        node("01",
             say(CARD, "HAILING -- U.S.S. ADIRONDACK"),
             say(S, "Adirondack. Shepard. Everything all right down there?"),
             options=[opt("I want you to stop calling.", "02"),
                      opt("Nothing. Wrong button.", "09")]),
        node("02",
             say(S, "..."),
             say(S, "All right. I can do that."),
             say(S, "The shuttle will still hear the beacons. That's hers."),
             say(S, "If you ever want me, hail. I'll pick up if I can."),
             options=[opt("Thank you.", "03"),
                      opt("I won't.", "03")]),
        node("03",
             say(S, "Look after yourself. Shepard out."),
             sets=["quiet"]),
        node("09",
             say(S, "Happens. Shepard out."),),
    ])

RESUME = thread(
    "RESUME", "Opening the channel", "hail",
    requires=["quiet"],
    nodes=[
        node("01",
             say(CARD, "HAILING -- U.S.S. ADIRONDACK"),
             say(S, "..."),
             say(S, "Hello, you. I did wonder."),
             options=[opt("You can call again.", "02"),
                      opt("Just checking you're there.", "03")]),
        node("02",
             say(S, "I will, then. Sparingly. I promise."),
             say(S, "Shepard out."),
             clears=["quiet"]),
        node("03",
             say(S, "Still here. Still going nowhere. Shepard out."),),
    ])


# ---------------------------------------------------------------------------
# The eleven, as they come up (COMMS.md 6.2)
# ---------------------------------------------------------------------------
# Distress calls carry random names, so a rescue is not a roster. What she
# can do is say the name back -- which is the thing a counter never does.
THANKS = thread(
    "THANKS", "Somebody came up", "incoming",
    requires=["thanksDue", "met"], forbids=["quiet"],
    repeatable=True, retry=False,
    nodes=[
        node("01",
             say(CARD, "INCOMING -- U.S.S. ADIRONDACK"),
             say(S, "It's Shepard. %2 is aboard. In quarantine, but aboard."),
             route=None,
             options=[opt("How are they?", "02"),
                      opt("Good.", "03")],
             clears=["thanksDue"]),
        node("02",
             say(S, "Thin. Filthy. Asked for coffee before a blanket."),
             say(S, "The Doctor says that's a good sign. I think he's lying."),
             options=[opt("Tell them they owe me one.", "03"),
                      opt("I'm glad.", "03")]),
        node("03",
             say(S, "I'll tell them. Thank you. Really. Shepard out."),),
    ])

LOST = thread(
    "LOST", "A beacon stopped", "incoming",
    requires=["lostDue", "met"], forbids=["quiet"],
    repeatable=True, retry=False,
    nodes=[
        node("01",
             say(CARD, "INCOMING -- U.S.S. ADIRONDACK"),
             say(S, "It's Shepard. %2's beacon stopped an hour ago."),
             say(S, "I'm not calling to blame you. I'm calling so someone"),
             say(S, "hears the name out loud. That's all."),
             options=[opt("I couldn't get there.", "02"),
                      opt("I'm sorry.", "02"),
                      opt("There'll be others.", "03")],
             clears=["lostDue"]),
        node("02",
             say(S, "I know. Nobody could. Shepard out."),),
        node("03",
             say(S, "There will. That's the worst thing anyone's said today."),
             say(S, "It's also true. Shepard out."),),
    ])


THREADS = [FIRST, THANKS, LOST, QUIET, RESUME]
