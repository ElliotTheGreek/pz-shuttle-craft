"""The mod's languages, held against its English: checking, and the work of
translating in pieces that can each be checked (SERVERS.md, *Languages*).

    python tools/translations.py check [LANG ...]        # every folder, or these
    python tools/translations.py status                  # what each language has
    python tools/translations.py export LANG DIR [--chars 9000] [--all]
    python tools/translations.py import LANG DIR         # checked, then written
    python tools/translations.py check-pack DIR          # a server's lore pack

English (Translate/EN) is the source. The game falls back to it key by key
(Translator.forLanguageStack: the language, its base, then the default), so a
language may leave a key out and still work. That is how the development
build's own lines stay English, on purpose.

**export** writes what a language still lacks as numbered chunk files, each a
JSON object `{ "lang", "file", "rules", "context", "units": {key: english} }`.
A translator -- a person or a model -- answers each with a file of the same
name plus `.out.json` holding `{key: translation}` and nothing else.
**import** reads those answers, refuses any that break a rule below, and
merges the rest into Translate/LANG/. Refused keys are listed and stay
English; run export again and only they come out.

What a translation has to keep, which `problems()` checks:

  * the same placeholders: `%1`, `%2` (an argument) and `{name}` (who a crew
    member is talking to). Never a literal per-cent sign: the engine reads it
    as the start of a placeholder (DEV_GUIDE, the probe's "16$s%");
  * one line: no line breaks, no tabs;
  * a channel or Captain's **option is a button**: no wider than the English
    limit, counting a Chinese, Japanese or Korean character as two;
  * not empty, and not longer than a line can be read in.
"""
import argparse
import glob
import json
import os
import re
import sys
import unicodedata

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TR = os.path.join(ROOT, "TrekShuttle", "42", "media", "lua", "shared", "Translate")
PZ_TR = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media\lua\shared\Translate"

# Every language build 42 ships, less English and the streamer build's own.
LANGS = ["AR", "CA", "CH", "CN", "CS", "DA", "DE", "ES", "ES_CL", "ES_MX", "FI", "FR", "HU", "ID", "IT",
         "JP", "KO", "NL", "NO", "PL", "PT", "PTBR", "RO", "RU", "TH", "TR", "UA"]

NAMES = {
    "AR": "Spanish (Argentina)", "CA": "Catalan", "CH": "Traditional Chinese", "CN": "Simplified Chinese",
    "CS": "Czech", "DA": "Danish", "DE": "German", "ES": "Spanish (Spain)", "ES_CL": "Spanish (Chile)",
    "ES_MX": "Spanish (Mexico)", "FI": "Finnish", "FR": "French", "HU": "Hungarian", "ID": "Indonesian",
    "IT": "Italian", "JP": "Japanese", "KO": "Korean", "NL": "Dutch", "NO": "Norwegian (Bokmal)",
    "PL": "Polish", "PT": "Portuguese (Portugal)", "PTBR": "Portuguese (Brazil)", "RO": "Romanian",
    "RU": "Russian", "TH": "Thai", "TR": "Turkish", "UA": "Ukrainian",
}

# A regional Spanish starts from Spain's, and Portugal's Portuguese from
# Brazil's or the other way: `export --from` names the language to adapt.
OPTION_MAX = 60        # tools/gen_comms.py: an option is a button
LINE_MAX = 110         # a channel, tape or crew line wraps; this is "something went wrong"
OTHER_FACTOR = 2.2     # any other text, against its English

PLACEHOLDER = re.compile(r"%\d|\{[A-Za-z_][A-Za-z0-9_]*\}")
OPTION_KEY = re.compile(r"^Print_Text_TREK_(COMM|CAPT)_.*_O\d+$")
SPOKEN_KEY = re.compile(r"^(Print_Text_TREK_|RM_TREK_)")


def is_dev(key):
    """The development build's own lines: its menu and what it says. English only."""
    return key.startswith("IGUI_TREK_Dev")


def load(path):
    raw = open(path, "rb").read()
    if raw.startswith(b"\xef\xbb\xbf"):
        raise ValueError("%s starts with a byte-order mark" % path)
    return json.loads(raw.decode("utf-8"))


def english():
    return {os.path.basename(f): load(f) for f in sorted(glob.glob(os.path.join(TR, "EN", "*.json")))}


def placeholders(text):
    return sorted(PLACEHOLDER.findall(text))


def width(text):
    """How wide a line draws, in Latin letters: a wide character is two."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def problems(key, en, text):
    """Why `text` cannot stand in for `en` under `key`, as a list of reasons."""
    out = []
    if not isinstance(text, str) or text.strip() == "":
        return ["is empty"]
    if text != text.strip():
        out.append("has a space at one end")
    if "\n" in text or "\r" in text or "\t" in text:
        out.append("has a line break or a tab in it")
    if placeholders(text) != placeholders(en):
        out.append("has placeholders %s where the English has %s" % (placeholders(text), placeholders(en)))
    if "%" in PLACEHOLDER.sub("", text):
        out.append("has a literal per-cent sign")
    if "{" in PLACEHOLDER.sub("", text) or "}" in PLACEHOLDER.sub("", text):
        out.append("has a brace that is not a {name}")
    w = width(text)
    if OPTION_KEY.match(key):
        if w > OPTION_MAX:
            out.append("is %d wide; an option is a button and holds %d" % (w, OPTION_MAX))
    elif SPOKEN_KEY.match(key):
        if w > LINE_MAX:
            out.append("is %d wide; a spoken line holds %d" % (w, LINE_MAX))
    elif w > max(40, width(en) * OTHER_FACTOR):
        out.append("is %d wide against the English's %d" % (w, width(en)))
    return out


def check_folder(folder, en, complete, label):
    """Problems with one language folder (or one lore pack's), as strings."""
    out = []
    if not os.path.isdir(folder):
        return ["%s: there is no folder %s" % (label, folder)]
    files = sorted(os.path.basename(f) for f in glob.glob(os.path.join(folder, "*")))
    for name in files:
        if name not in en:
            out.append("%s/%s is not a file the English has" % (label, name))
    for name, keys in en.items():
        path = os.path.join(folder, name)
        if not os.path.isfile(path):
            if complete and any(not is_dev(k) for k in keys):
                out.append("%s/%s is missing" % (label, name))
            continue
        try:
            got = load(path)
        except Exception as e:      # noqa: BLE001 -- any way it fails to read is the finding
            out.append("%s/%s does not read as UTF-8 JSON: %s" % (label, name, e))
            continue
        for k in got:
            if k not in keys:
                out.append("%s/%s has %s, which the English does not" % (label, name, k))
            elif is_dev(k):
                out.append("%s/%s translates %s, a development line" % (label, name, k))
        for k, src in keys.items():
            if is_dev(k):
                continue
            if k not in got:
                if complete:
                    out.append("%s/%s has no %s" % (label, name, k))
                continue
            for why in problems(k, src, got[k]):
                out.append("%s/%s %s %s: %r" % (label, name, k, why, got[k]))
    return out


def shipped():
    """The language folders the mod has, in the game's own order."""
    return [lang for lang in LANGS if os.path.isdir(os.path.join(TR, lang))]


def missing(lang, en):
    """file -> {key: english} for what a language has not got."""
    out = {}
    for name, keys in en.items():
        path = os.path.join(TR, lang, name)
        got = load(path) if os.path.isfile(path) else {}
        need = {k: v for k, v in keys.items() if not is_dev(k) and k not in got}
        if need:
            out[name] = need
    return out


RULES = [
    "Translate every value into {language} as it is written for Project Zomboid players. Keep each key exactly.",
    "Keep every placeholder exactly as written and the same number of times: %1, %2 (filled in by the game) "
    "and {{name}} tokens such as {{a}} or {{doc}} (a crew member's name). Do not translate inside braces.",
    "Never write a per-cent sign except as part of %1, %2. Write 'per cent' in words if you need it.",
    "One line each: no line breaks.",
    "A key ending _O1, _O2 ... is a button the player presses: at most 60 letters wide, counting a Chinese, "
    "Japanese or Korean character as two. Shorten it rather than run over.",
    "Lines of dialogue (keys with COMM, CAPT, CREW or RM_TREK) are people talking: tired, dry, specific. "
    "Translate how a person would say it, not word for word. Keep it about as long as the English.",
    "Do not translate proper names: Adirondack, Starfleet, Shepard, Titus, Tucker Gold, Muldraugh, Kentucky, "
    "and names of people. Use the established {language} Star Trek terms (phaser, tricorder, warp core, "
    "replicator, transporter, shields, away team) as the dubbed or subtitled series use them.",
    "ALL CAPS in the English is a title card or a status line: keep it in capitals where the language has them.",
    "Answer with one JSON object mapping each key to its translation, and nothing else.",
]


def export(lang, out_dir, chars, everything, source):
    en = english()
    todo = {name: {k: v for k, v in keys.items() if not is_dev(k)} for name, keys in en.items()} \
        if everything else missing(lang, en)
    os.makedirs(out_dir, exist_ok=True)
    for old in glob.glob(os.path.join(out_dir, "*.json")):
        if not old.endswith(".out.json"):
            os.remove(old)
    base = {}
    if source:
        for name in en:
            path = os.path.join(TR, source, name)
            if os.path.isfile(path):
                base[name] = load(path)
    n = 0
    for name, need in todo.items():
        chunk, size = {}, 0

        def flush():
            nonlocal chunk, size, n
            if not chunk:
                return
            n += 1
            doc = {"lang": lang, "language": NAMES.get(lang, lang), "file": name,
                   "rules": [r.format(language=NAMES.get(lang, lang)) for r in RULES], "units": chunk}
            if source:
                doc["adapt_from"] = NAMES.get(source, source)
                doc["rules"].insert(0, "Each unit is given as [english, %s]. Adapt the %s to %s where the two "
                                       "differ in vocabulary or spelling; keep it where they do not."
                                    % (NAMES.get(source, source), NAMES.get(source, source), NAMES.get(lang, lang)))
            path = os.path.join(out_dir, "%03d_%s.json" % (n, name[:-5]))
            json.dump(doc, open(path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
            chunk, size = {}, 0

        for k, v in need.items():
            unit = [v, base[name][k]] if source and k in base.get(name, {}) else v
            chunk[k] = unit
            size += len(v)
            if size >= chars:
                flush()
        flush()
    total = sum(len(v) for need in todo.values() for v in need.values())
    print("%s: %d chunk(s) in %s, %d key(s), %d characters of English"
          % (lang, n, out_dir, sum(len(x) for x in todo.values()), total))


def write_language(lang, name, data, en_keys):
    """Writes one file in the English's own key order."""
    folder = os.path.join(TR, lang)
    os.makedirs(folder, exist_ok=True)
    ordered = {k: data[k] for k in en_keys if k in data}
    with open(os.path.join(folder, name), "w", encoding="utf-8", newline="\n") as f:
        json.dump(ordered, f, ensure_ascii=False, indent=4)
        f.write("\n")


def import_(lang, in_dir):
    en = english()
    merged = {name: (load(os.path.join(TR, lang, name)) if os.path.isfile(os.path.join(TR, lang, name)) else {})
              for name in en}
    refused, taken = [], 0
    for path in sorted(glob.glob(os.path.join(in_dir, "*.out.json"))):
        asked = load(path[:-len(".out.json")] + ".json")
        name = asked["file"]
        try:
            got = load(path)
        except Exception as e:      # noqa: BLE001
            refused.append("%s does not read as JSON: %s" % (os.path.basename(path), e))
            continue
        for k in asked["units"]:
            if k not in got:
                refused.append("%s: no %s" % (os.path.basename(path), k))
                continue
            why = problems(k, en[name][k], got[k])
            if why:
                refused.append("%s %s: %s: %r" % (name, k, "; ".join(why), got[k]))
                continue
            merged[name][k] = got[k]
            taken += 1
    for name, data in merged.items():
        if data:
            write_language(lang, name, data, list(en[name].keys()))
    left = sum(len(x) for x in missing(lang, en).values())
    print("%s: %d translation(s) taken, %d refused, %d key(s) still English" % (lang, taken, len(refused), left))
    for r in refused[:40]:
        print("  refused  " + r)
    if len(refused) > 40:
        print("  ... and %d more" % (len(refused) - 40))
    return 1 if refused else 0


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check")
    c.add_argument("langs", nargs="*")
    sub.add_parser("status")
    e = sub.add_parser("export")
    e.add_argument("lang")
    e.add_argument("dir")
    e.add_argument("--chars", type=int, default=9000)
    e.add_argument("--all", action="store_true")
    e.add_argument("--from", dest="source")
    i = sub.add_parser("import")
    i.add_argument("lang")
    i.add_argument("dir")
    p = sub.add_parser("check-pack")
    p.add_argument("dir")
    a = ap.parse_args()

    if a.cmd == "status":
        en = english()
        total = sum(1 for keys in en.values() for k in keys if not is_dev(k))
        for lang in LANGS:
            left = sum(len(x) for x in missing(lang, en).values())
            print("%-6s %-24s %5d of %d translated" % (lang, NAMES[lang], total - left, total))
        return 0
    if a.cmd == "export":
        export(a.lang, a.dir, a.chars, a.all, a.source)
        return 0
    if a.cmd == "import":
        return import_(a.lang, a.dir)
    if a.cmd == "check-pack":
        en = english()
        found, out = 0, []
        for folder in sorted(glob.glob(os.path.join(a.dir, "**", "Translate", "*"), recursive=True)):
            if os.path.isdir(folder):
                found += 1
                out += check_folder(folder, en, False, os.path.basename(folder))
        if not found:
            out.append("no Translate/<LANG> folder under %s" % a.dir)
        for line in out:
            print("  FAIL  " + line)
        print("%d language folder(s), %d problem(s)" % (found, len(out)))
        return 1 if out else 0
    en = english()
    out = []
    for lang in (a.langs or shipped()):
        out += check_folder(os.path.join(TR, lang), en, True, lang)
    for line in out[:200]:
        print("  FAIL  " + line)
    print("%d language(s), %d problem(s)" % (len(a.langs or shipped()), len(out)))
    return 1 if out else 0


if __name__ == "__main__":
    sys.exit(main())
