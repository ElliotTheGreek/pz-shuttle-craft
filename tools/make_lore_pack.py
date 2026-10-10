"""Makes a *lore pack*: a small mod of your own that replaces the Shuttlecraft
mod's words with yours (SERVERS.md, *Your own lore*).

    python tools/make_lore_pack.py OUT --id MyServerLore --name "My Server: Shuttlecraft lore"
    python tools/make_lore_pack.py OUT --id Saratoga --rename "Adirondack=Saratoga" --rename "Titus=Okonkwo"
    python tools/make_lore_pack.py OUT --id LoreFR --lang FR --what lore
    python tools/translations.py check-pack OUT         # before you publish it

Every word the mod shows is a translation key, and the game reads every
enabled mod's translation files in the order the mods are listed, each key
replacing the one before it (Translator.tryFillMapFromMods: a plain put). So a
mod listed **after** TrekShuttle that carries the same keys wins, key by key,
for everything: the channel, the Captain, the crew, the tapes on the
television, item names, tooltips, the trait descriptions, the sandbox page.
The pack's mod.info requires TrekShuttle, which is what puts it after.

A key you leave out keeps the mod's own text, so delete what you do not mean
to change: a smaller pack survives the mod's updates better.

  --lang   which languages to write (default EN). Each starts from the mod's
           own text in that language, or its English where it has none.
           A player sees their own game language: write the same words into
           every language folder your players use, or `--lang ALL`.
  --what   lore (the channel, the Captain, the crew and the tapes), or all.
  --rename "Old=New", as often as you like: every text with Old in it is
           written with New, capitals kept (ADIRONDACK -> SARATOGA). With
           --rename the pack holds only the lines it changed, unless --full.

What your words have to keep is in tools/translations.py, and `check-pack`
checks it: the same %1 and {name} placeholders, no per-cent sign, one line,
and an option short enough for its button.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import translations as T  # noqa: E402

LORE_FILES = ("Print_Text.json", "Recorded_Media.json")

README = """{name}
{rule}

A lore pack for the Shuttlecraft mod (Workshop 3801178990, Mod ID TrekShuttle).

HOW IT WORKS
  The game reads every enabled mod's translation files in order, and a later
  mod's text replaces an earlier one's, key by key. This mod carries some of
  the Shuttlecraft mod's keys with your own words in them.

WHAT TO DO
  1. Edit the .json files under 42/media/lua/shared/Translate/<LANGUAGE>/.
     Change the text on the right of each line. Never change the key on the
     left. Delete any line you do not mean to change.
  2. Keep, in every line you edit:
       %1 and %2      the game fills these in; keep each one, once
       {{a}} {{doc}} ...  a crew member's name; keep them as they are
       no % sign      write "per cent"
       one line       no line breaks
       a key ending _O1, _O2 is a button: 60 letters at most
  3. Players see their own game language. Put your words in every language
     folder your players use (copy the file across), or they see the
     Shuttlecraft mod's own text in theirs.
  4. Check it:   python tools/translations.py check-pack <this folder>
     (from the Shuttlecraft mod's repository: github.com/ElliotTheGreek)
  5. Publish it to the Workshop (unlisted is fine) and add it to your
     server AFTER TrekShuttle:

       Mods=TrekShuttle;{id}
       WorkshopItems=3801178990;<your item's id>

WHAT THE FILES ARE
  Print_Text.json       the Adirondack channel (COMM), Captain Titus (CAPT)
                        and everything her crew say (CREW)
  Recorded_Media.json   every tape: its label and each line of it
  IG_UI.json            menus, notes, panels
  ItemName.json, Tooltip.json, UI.json, Sandbox.json, ...   as named

  A tape line is one subtitle and a channel line one line of speech. A line
  you make much longer stays on screen longer; one you make empty is refused
  by the check.
"""


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out")
    ap.add_argument("--id", required=True)
    ap.add_argument("--name")
    ap.add_argument("--lang", action="append")
    ap.add_argument("--what", choices=("lore", "all"), default="all")
    ap.add_argument("--rename", action="append", default=[])
    ap.add_argument("--full", action="store_true")
    a = ap.parse_args()

    if not a.id.replace("_", "").isalnum():
        sys.exit("--id is a mod id: letters, digits and underscores only")
    name = a.name or a.id
    langs = a.lang or ["EN"]
    if "ALL" in langs:
        langs = ["EN"] + T.LANGS
    renames = []
    for pair in a.rename:
        if "=" not in pair:
            sys.exit('--rename takes "Old=New"')
        old, new = pair.split("=", 1)
        if not old.strip() or not new.strip():
            sys.exit('--rename takes "Old=New", neither side empty')
        if "%" in new or "{" in new or "}" in new:
            sys.exit("a new name cannot hold a per-cent sign or a brace: the game reads them as placeholders")
        renames.append((old.strip(), new.strip()))

    en = T.english()
    files = [f for f in en if a.what == "all" or f in LORE_FILES]
    root = os.path.join(a.out, a.id)
    written = 0
    for lang in langs:
        folder = os.path.join(root, "42", "media", "lua", "shared", "Translate", lang)
        for fname in files:
            path = os.path.join(T.TR, lang, fname)
            own = T.load(path) if os.path.isfile(path) else {}
            out = {}
            for key, src in en[fname].items():
                if T.fixed(key, src):
                    continue
                text = own.get(key, src)
                new = text
                for old, to in renames:
                    new = new.replace(old, to).replace(old.upper(), to.upper())
                if renames and not a.full and new == text:
                    continue
                out[key] = new
            if not out:
                continue
            os.makedirs(folder, exist_ok=True)
            with open(os.path.join(folder, fname), "w", encoding="utf-8", newline="\n") as f:
                json.dump(out, f, ensure_ascii=False, indent=4)
                f.write("\n")
            written += len(out)

    os.makedirs(os.path.join(root, "42"), exist_ok=True)
    os.makedirs(os.path.join(root, "common"), exist_ok=True)
    with open(os.path.join(root, "common", "readme.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write("Build 42 looks for this folder in every mod. Nothing needs to be in it.\n")
    with open(os.path.join(root, "42", "mod.info"), "w", encoding="utf-8", newline="\n") as f:
        f.write("name=%s\nid=%s\ndescription=Our own words for the Shuttlecraft mod. List it after TrekShuttle.\n"
                "require=\\TrekShuttle\nversionMin=42.0\nmodversion=1.0\n" % (name, a.id))
    with open(os.path.join(root, "README.txt"), "w", encoding="utf-8", newline="\n") as f:
        f.write(README.format(name=name, rule="=" * len(name), id=a.id))

    problems = []
    for lang in langs:
        folder = os.path.join(root, "42", "media", "lua", "shared", "Translate", lang)
        if os.path.isdir(folder):
            problems += T.check_folder(folder, en, False, lang)
    for p in problems[:30]:
        print("  FAIL  " + p)
    print("%s: %d line(s) in %d language(s) under %s%s"
          % (a.id, written, len(langs), root,
             "" if not problems else " -- %d of them break a rule and want shortening" % len(problems)))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
