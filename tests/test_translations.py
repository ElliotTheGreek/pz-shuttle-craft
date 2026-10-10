"""Every language the mod is translated into, held against the English.

    python tests/test_translations.py            # every language folder
    python tests/test_translations.py DE FR      # only these

English (Translate/EN) is the source, and tools/translations.py is the rule
book: this file runs it, and checks the English against the same rules a
translation is held to -- a source line that breaks one cannot be translated
into one that keeps it.

  * a folder is one of the game's own languages, and holds only files EN has;
  * every file is UTF-8 JSON with no BOM, and holds only keys EN's file has;
  * every key a player can see is translated, and none is empty;
  * none of the development build's keys are (nobody but the author reads
    them);
  * each text has exactly EN's placeholders (%1, {name}) and no literal %;
  * a channel or Captain's option fits its button.

A language in REQUIRED that has no folder fails. One that is merely in the
game and not yet translated is listed and passes: the game falls back to
English key by key, so a missing language is English, not a fault.
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "tools"))

import translations as T  # noqa: E402

# The languages a release must carry. A language taken off this list fails
# the test rather than quietly going missing from a release.
REQUIRED = []

FAILS = []


def check(cond, what):
    if not cond:
        print("  FAIL  " + what)
        FAILS.append(what)
    return cond


def source(en):
    """The English, against the rules its translations must keep."""
    n = 0
    for name, keys in en.items():
        for k, v in keys.items():
            n += 1
            check(isinstance(v, str), "EN/%s %s is not text" % (name, k))
            # Empty on purpose is allowed in the English, and nowhere else:
            # no language translates it (T.fixed).
            check("%" not in T.PLACEHOLDER.sub("", v),
                  "EN/%s %s has a literal per-cent sign: the engine reads it as a placeholder" % (name, k))
            check("\n" not in v and "\t" not in v, "EN/%s %s has a line break or a tab" % (name, k))
            if T.OPTION_KEY.match(k):
                check(T.width(v) <= T.OPTION_MAX, "EN/%s %s is an option wider than its button" % (name, k))
    return n


def rules():
    """The rule book itself: each rule refuses what it is for, and a good
    translation passes them all. A checker that refuses nothing would pass
    every language there is."""
    ok = T.problems("IGUI_X", "Beam %1 up to the %2.", "Beame %1 auf die %2.")
    check(ok == [], "a good translation was refused: %s" % ok)
    cases = [
        ("IGUI_X", "Beam %1 up.", "", "empty"),
        ("IGUI_X", "Beam %1 up.", "Hochbeamen.", "placeholders"),
        ("IGUI_X", "Beam %1 up.", "Beame %1 und %2.", "placeholders"),
        ("IGUI_X", "Power at %1.", "Energie bei %1%.", "per-cent"),
        ("IGUI_X", "Two lines.", "Zwei\nZeilen.", "line break"),
        ("IGUI_X", "Short.", " Kurz.", "space"),
        ("Print_Text_TREK_CREW_a_1", "Morning, {doc}.", "Morgen, {arzt}.", "placeholders"),
        ("Print_Text_TREK_CREW_a_1", "Morning, {doc}.", "Morgen, {doc.", "brace"),
        ("Print_Text_TREK_COMM_X_01_O1", "Yes.", "J" * 61, "button"),
        ("Print_Text_TREK_COMM_X_01_O1", "Yes.", "日" * 31, "button"),
        ("Print_Text_TREK_COMM_X_01_L1", "Yes.", "J" * 111, "spoken line"),
        ("IGUI_X", "Yes.", "J" * 41, "wide against"),
    ]
    for key, en, text, want in cases:
        got = T.problems(key, en, text)
        check(any(want in why for why in got),
              "%r for %r under %s was not refused for its %s (%s)" % (text, en, key, want, got))
    check(T.problems("Print_Text_TREK_COMM_X_01_O1", "Yes.", "日" * 30) == [],
          "thirty wide characters do not fit a sixty-wide button")
    check(T.problems("Print_Text_TREK_COMM_X_01_L1", "Yes.", "J" * 61) == [],
          "a spoken line is held to a button's width")
    check(T.is_dev("IGUI_TREK_DevMap") and not T.is_dev("IGUI_TREK_Name"),
          "the development build's keys are not told from a player's")


def main():
    en = T.english()
    check(len(en) >= 8 and sum(len(k) for k in en.values()) >= 5000,
          "the English is %d file(s): the folder has moved, and everything would pass against nothing" % len(en))
    keys = source(en)
    rules()
    if os.path.isdir(T.PZ_TR):
        for lang in T.LANGS:
            check(os.path.isdir(os.path.join(T.PZ_TR, lang)), "%s is not one of the game's languages" % lang)
    for folder in sorted(os.listdir(T.TR)):
        check(folder == "EN" or folder in T.LANGS,
              "Translate/%s is not a language of the game's: nothing reads it" % folder)
    langs = [a for a in sys.argv[1:]] or T.shipped()
    for lang in REQUIRED:
        check(lang in T.shipped(), "%s is required and has no folder" % lang)
    for lang in langs:
        for why in T.check_folder(os.path.join(T.TR, lang), en, True, lang):
            check(False, why)
    waiting = [lang for lang in T.LANGS if lang not in T.shipped()]
    if FAILS:
        print("\n%d PROBLEM(S)" % len(FAILS))
        sys.exit(1)
    print("translations: %d English keys keep their own rules; %d language(s) complete and checked (%s)%s"
          % (keys, len(langs), ", ".join(langs) or "none yet",
             "; not yet translated, and English in the game: " + ", ".join(waiting) if waiting else ""))


main()
