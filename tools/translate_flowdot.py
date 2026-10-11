#!/usr/bin/env python3
"""Translate the mod with a FlowDot workflow (SERVERS.md, *Languages*).

    python tools/translate_flowdot.py DIR LANG [LANG ...] [--workers 3] [--rounds 3]
    python tools/translate_flowdot.py DIR ALL

For each language: `translations.py export` writes what it still lacks as
chunks under DIR/LANG, every chunk without an answer is sent to the workflow
(one LLM call each, a few at once), and `translations.py import` checks the
answers and merges what passes. What was refused comes out of the next export
alone, so a few rounds close on the lines a model keeps getting wrong.

The workflow is `TrekShuttle translator` on FlowDot: a text input *Payload*
(the chunk, as JSON), one LLM node, and an MCP output `translation`. It is
called through FlowDot's own MCP server, started here the way Claude Code
starts it (`mcpServers.flowdot` in this repo's .mcp.json, which git ignores,
or ~/.claude.json), so the token stays where it is kept and is never read
into this file or printed.

A run is started and then asked after, never waited on in one request: a full
chunk takes about a minute, which is as long as the hub holds a request open.
The hub also runs only a few of one account's executions at a time and
refuses the rest ("Execution failed"), so three workers is the default and a
refused chunk waits and asks again.

An answer is a file beside its chunk until `import` has checked it. Stopping
and starting again loses nothing: answers left by a stopped run are imported
before the next export.
"""
import argparse
import glob
import json
import os
import queue
import re
import subprocess
import sys
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import translations as T  # noqa: E402

WORKFLOW = "hKGeWNX3pJ"
TOOL = os.path.join(HERE, "translations.py")
PRINT = threading.Lock()


def say(*a):
    with PRINT:
        print(*a, flush=True)


def server_spec(name):
    spec = None
    for path in (os.path.join(os.path.dirname(HERE), ".mcp.json"), os.path.expanduser("~/.claude.json")):
        if spec is None and os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                spec = (json.load(f).get("mcpServers") or {}).get(name)
    if spec is None:
        raise RuntimeError("no MCP server named %r in .mcp.json or ~/.claude.json" % name)
    env = dict(os.environ)
    env.update(spec.get("env") or {})
    return [spec["command"]] + list(spec.get("args") or []), env


class Mcp:
    """One MCP server on stdio, one request at a time."""

    def __init__(self, name):
        cmd, env = server_spec(name)
        self.p = subprocess.Popen(cmd, env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL)
        self.n = 0
        self.ask("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                                "clientInfo": {"name": "trek-translate", "version": "1"}})
        self.tell("notifications/initialized", {})

    def tell(self, method, params):
        msg = {"jsonrpc": "2.0", "method": method, "params": params}
        self.p.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        self.p.stdin.flush()

    def ask(self, method, params):
        self.n += 1
        msg = {"jsonrpc": "2.0", "id": self.n, "method": method, "params": params}
        self.p.stdin.write((json.dumps(msg) + "\n").encode("utf-8"))
        self.p.stdin.flush()
        while True:
            line = self.p.stdout.readline()
            if not line:
                raise RuntimeError("the MCP server went away")
            try:
                reply = json.loads(line.decode("utf-8"))
            except ValueError:
                continue
            if reply.get("id") == self.n:
                if "error" in reply:
                    raise RuntimeError(str(reply["error"])[:300])
                return reply["result"]

    def call(self, tool_name, arguments):
        result = self.ask("tools/call", {"name": tool_name, "arguments": arguments})
        text = "\n".join(c.get("text", "") for c in result.get("content", []) if c.get("type") == "text")
        if result.get("isError"):
            raise RuntimeError(text[:300])
        return text

    def close(self):
        try:
            self.p.kill()
        except OSError:
            pass


def run(mcp, chunk, mode, patience):
    """Start one execution, wait for it, and give its {key: translation}."""
    started = mcp.call("execute_workflow", {
        "workflow_id": WORKFLOW, "mode": mode, "wait_for_completion": False,
        "inputs": {"Payload": json.dumps(chunk, ensure_ascii=False)}})
    m = re.search(r"Execution ID:[*\s]*([0-9a-f-]{36})", started)
    if not m:
        raise RuntimeError("not started: " + started[:300])
    until = time.time() + patience
    while time.time() < until:
        time.sleep(6)
        try:
            text = mcp.call("get_execution_status", {"execution_id": m.group(1)})
        except RuntimeError as e:
            # Started, and not yet on record; or the hub dropped the question.
            # Either way the run is still going: ask again, do not start another.
            if "not found" in str(e).lower() or "fetch failed" in str(e).lower():
                continue
            raise
        status = re.search(r"Execution Status:\s*(\w+)", text)
        status = status.group(1).lower() if status else ""
        if status == "completed":
            return answer_of(text)
        if status in ("failed", "cancelled", "error"):
            raise RuntimeError("the run " + status + ": " + text[-200:])
    raise RuntimeError("no answer in %d seconds" % patience)


def answer_of(text):
    """The {key: translation} object out of a finished run's status."""
    at = text.find("Outputs:")
    if at < 0:
        raise RuntimeError("no outputs: " + text[:300])
    out = json.loads(text[at + len("Outputs:"):]).get("translation")
    if isinstance(out, str):
        if "{" not in out or "}" not in out:
            raise RuntimeError("the answer is not JSON: " + out[:120])
        out = json.loads(out[out.index("{"):out.rindex("}") + 1])
    if not isinstance(out, dict):
        raise RuntimeError("the answer is not an object")
    return out


def worker(jobs, mode, tries, tally):
    mcp = None
    while True:
        try:
            path = jobs.get_nowait()
        except queue.Empty:
            break
        chunk = T.load(path)
        name = os.path.join(os.path.basename(os.path.dirname(path)), os.path.basename(path))
        for attempt in range(1, tries + 1):
            try:
                if mcp is None:
                    mcp = Mcp("flowdot")
                got = run(mcp, chunk, mode, 600)
                kept = {k: v for k, v in got.items() if k in chunk["units"] and isinstance(v, str)}
                if len(kept) * 2 < len(chunk["units"]):
                    raise RuntimeError("only %d of %d keys came back" % (len(kept), len(chunk["units"])))
                with open(path[:-len(".json")] + ".out.json", "w", encoding="utf-8", newline="\n") as f:
                    json.dump(kept, f, ensure_ascii=False, indent=1)
                tally["done"] += 1
                say("  %s: %d of %d" % (name, len(kept), len(chunk["units"])))
                break
            except Exception as e:  # noqa: BLE001 -- a chunk that fails is asked again
                if attempt > 2:
                    say("  %s: try %d failed: %s" % (name, attempt, str(e)[:200]))
                if mcp is not None:
                    mcp.close()
                    mcp = None
                time.sleep(8 * attempt)
        else:
            tally["failed"] += 1
    if mcp is not None:
        mcp.close()


def tool(*args):
    r = subprocess.run([sys.executable, TOOL] + list(args), capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    return (r.stdout or "") + (r.stderr or "")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("dir")
    ap.add_argument("langs", nargs="+")
    ap.add_argument("--workers", type=int, default=3)
    ap.add_argument("--rounds", type=int, default=3)
    ap.add_argument("--chars", type=int, default=9000)
    ap.add_argument("--mode", default="flowdot")
    ap.add_argument("--tries", type=int, default=8)
    a = ap.parse_args()
    langs = sorted(T.LANGS) if a.langs == ["ALL"] else a.langs

    for rnd in range(1, a.rounds + 1):
        jobs = queue.Queue()
        for lang in langs:
            folder = os.path.join(a.dir, lang)
            answers = glob.glob(os.path.join(folder, "*.out.json"))
            if answers:                       # a run that was stopped: keep what it had
                tool("import", lang, folder)
            for old in answers:
                os.remove(old)
            out = tool("export", lang, folder, "--chars", str(a.chars))
            say("round %d: %s" % (rnd, out.strip().splitlines()[-1] if out.strip() else lang))
            for path in sorted(glob.glob(os.path.join(folder, "*.json"))):
                if not path.endswith(".out.json"):
                    jobs.put(path)
        if jobs.empty():
            break
        tally = {"done": 0, "failed": 0}
        threads = [threading.Thread(target=worker, args=(jobs, a.mode, a.tries, tally))
                   for _ in range(min(a.workers, jobs.qsize()))]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        say("round %d: %d chunk(s) answered, %d gave up" % (rnd, tally["done"], tally["failed"]))
        for lang in langs:
            folder = os.path.join(a.dir, lang)
            out = tool("import", lang, folder).strip().splitlines()
            say("round %d: %s" % (rnd, out[-1] if out else lang + ": nothing imported"))
            for old in glob.glob(os.path.join(folder, "*.out.json")):
                os.remove(old)
    say(tool("status"))


if __name__ == "__main__":
    main()
