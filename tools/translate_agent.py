#!/usr/bin/env python3
"""Translate the mod with FlowDot CLI agents (SERVERS.md, *Languages*).

    python tools/translate_agent.py DIR LANG [LANG ...] [--workers 4] [--rounds 3] [--chars 3000]
    python tools/translate_agent.py DIR ALL

One `flowdot agent` per chunk, several at once. The agent is FlowDot's own
command-line agent, which answers with the model the CLI is signed in to
(`flowdot providers list`; here OpenAI over OAuth). It is given the chunk's
rules and lines in its request and says its answer, one line per key:

    KEY<tab>translation

It uses no tool and writes no file. Asked to write one, the CLI (1.1.13)
wants a prompt answered for a short file, which nobody is there to answer,
and fails to parse its own action for a long one; and JSON for an answer
means a model escaping JSON inside JSON, which drops a quote sooner or later.
This reads the lines out of what the agent said into `NNN_File.out.json`, and
`translations.py import` checks every one before anything reaches Translate/.
What is refused or missing comes out of the next export alone.

DIR is where the chunks live, and it is the agents' working directory: the
CLI's permissions are kept per directory (DIR/.flowdot/policy), so what they
are allowed is allowed there and nowhere else. They need one, once:

    cd DIR
    flowdot permissions allow llm.call 'oauth/openai/<model>'
"""
import argparse
import glob
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import translations as T  # noqa: E402

TOOL = os.path.join(HERE, "translations.py")
PRINT = threading.Lock()


def say(*a):
    with PRINT:
        print(*a, flush=True)


def cli():
    """The CLI as [node, its script]: the .cmd shim would hand the request to
    cmd.exe, which eats per-cent signs and quotes."""
    shim = shutil.which("flowdot") or shutil.which("flowdot.cmd")
    if not shim:
        raise RuntimeError("the flowdot CLI is not installed")
    script = os.path.join(os.path.dirname(shim), "node_modules", "@flowdot.ai", "cli", "dist", "cli", "index.js")
    if not os.path.exists(script):
        raise RuntimeError("no FlowDot CLI script at " + script)
    return [shutil.which("node") or "node", script]


def request(chunk, out_name):
    lines = ["You are a professional game localiser. Translate the lines below from English into %s for a "
             "Project Zomboid mod set in the Star Trek universe: a Starfleet shuttle and its crew stranded over "
             "zombie-outbreak Kentucky in 1993." % chunk["language"],
             "", "RULES (follow every one exactly):"]
    lines += ["- " + r for r in chunk["rules"][:-1]]
    if chunk.get("context"):
        lines += ["", "CONTEXT: " + str(chunk["context"])]
    lines += ["",
              "HOW TO ANSWER: do not call any tool and do not read or write any file. Reply with the "
              "translations themselves as your whole message, plain text and NOT JSON: one line per key, in the "
              "same order, each line being the key, one tab character, then the translation. Every key below "
              "must have a line. No header, no blank lines, no quotation marks around the translation, no "
              "commentary.",
              "", "LINES (key, tab, English):"]
    lines += ["%s\t%s" % (k, v) for k, v in chunk["units"].items()]
    return "\n".join(lines)


def read_answer(text, units):
    """Every `KEY<tab>translation` line in what an agent wrote or said.

    Lenient on purpose. The agent's write_file action is JSON carrying the
    whole answer in one string, and the CLI fails to parse a long one and
    prints it as its reply instead of acting on it: the answer is then all
    there, on one line, with its tabs and line ends still escaped."""
    text = text.replace("\\n", "\n").replace("\\t", "\t").replace('\\"', '"')
    keys = "|".join(re.escape(k) for k in sorted(units, key=len, reverse=True))
    out = {}
    for m in re.finditer(r"(?:^|(?<=[\n\"\s│]))(" + keys + r")\t([^\n]*)", text):
        said = m.group(2).strip()
        if said.endswith('"}}'):
            said = said[:-3].strip()
        if said and m.group(1) not in out:
            out[m.group(1)] = said
    return out


def reply_of(stdout):
    """What the agent said, without the echo of what it was asked."""
    at = stdout.find("Max iterations")
    at = stdout.find("Response", at if at >= 0 else 0)
    return stdout[at:] if at >= 0 else ""


def worker(jobs, root, timeout, tries, tally):
    base = cli()
    while True:
        try:
            path = jobs.get_nowait()
        except queue.Empty:
            break
        chunk = T.load(path)
        rel = os.path.relpath(path, root).replace("\\", "/")
        raw = rel[:-len(".json")] + ".answer.txt"
        raw_path = os.path.join(root, raw)
        for attempt in range(1, tries + 1):
            try:
                if os.path.exists(raw_path):
                    os.remove(raw_path)
                r = subprocess.run(base + ["agent", "--no-web-search", "--no-code-analysis", "--max-iterations", "2",
                                           "--timeout", str(timeout), request(chunk, raw)],
                                   cwd=root, stdin=subprocess.DEVNULL, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace", timeout=timeout * 60 + 60)
                said = reply_of(r.stdout or "")
                if "Permission DENIED" in said:
                    raise RuntimeError("permission denied -- see this file's docstring")
                if os.path.exists(raw_path):
                    with open(raw_path, encoding="utf-8", errors="replace") as f:
                        said += "\n" + f.read()
                    os.remove(raw_path)
                got = read_answer(said, chunk["units"])
                if len(got) * 2 < len(chunk["units"]):
                    raise RuntimeError("only %d of %d keys came back" % (len(got), len(chunk["units"])))
                with open(path[:-len(".json")] + ".out.json", "w", encoding="utf-8", newline="\n") as f:
                    json.dump(got, f, ensure_ascii=False, indent=1)
                tally["done"] += 1
                say("  %s: %d of %d" % (rel, len(got), len(chunk["units"])))
                break
            except Exception as e:  # noqa: BLE001 -- a chunk that fails is asked again
                say("  %s: try %d failed: %s" % (rel, attempt, str(e)[:220]))
                time.sleep(5 * attempt)
        else:
            tally["failed"] += 1


def tool(*args):
    r = subprocess.run([sys.executable, TOOL] + list(args), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir")
    ap.add_argument("langs", nargs="+")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--chars", type=int, default=3000)
    ap.add_argument("--timeout", type=int, default=8, help="minutes an agent may take")
    ap.add_argument("--tries", type=int, default=3)
    ap.add_argument("--limit", type=int, default=0, help="at most this many chunks a round (a trial)")
    a = ap.parse_args()
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    root = os.path.abspath(a.dir)
    langs = sorted(T.LANGS) if a.langs == ["ALL"] else a.langs

    for rnd in range(1, a.rounds + 1):
        jobs = queue.Queue()
        for lang in langs:
            folder = os.path.join(root, lang)
            answers = glob.glob(os.path.join(folder, "*.out.json"))
            if answers:                       # a run that was stopped: keep what it had
                tool("import", lang, folder)
            for old in answers:
                os.remove(old)
            out = tool("export", lang, folder, "--chars", str(a.chars))
            say("round %d: %s" % (rnd, out.strip().splitlines()[-1] if out.strip() else lang))
            for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
                if not path.endswith(".out.json") and (not a.limit or jobs.qsize() < a.limit):
                    jobs.put(path)
        if jobs.empty():
            break
        tally = {"done": 0, "failed": 0}
        threads = [threading.Thread(target=worker, args=(jobs, root, a.timeout, a.tries, tally))
                   for _ in range(min(a.workers, jobs.qsize()))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        say("round %d: %d chunk(s) answered, %d gave up" % (rnd, tally["done"], tally["failed"]))
        for lang in langs:
            folder = os.path.join(root, lang)
            out = tool("import", lang, folder).strip().splitlines()
            say("round %d: %s" % (rnd, out[-1] if out else lang + ": nothing imported"))
            for old in glob.glob(os.path.join(folder, "*.out.json")):
                os.remove(old)
    say(tool("status"))


if __name__ == "__main__":
    main()
