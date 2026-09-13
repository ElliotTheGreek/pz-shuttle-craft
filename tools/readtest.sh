#!/bin/sh
# Pulls the mod's own lines out of the game log after a test run.
#
# console.txt is overwritten every launch, so the header is worth reading:
# reporting a stale log as the current run is an easy mistake to make.
LOG="/c/Users/Arcade/Zomboid/console.txt"
echo "=== log: $(wc -l < "$LOG") lines, modified $(date -r "$LOG" '+%Y-%m-%d %H:%M:%S') ==="
echo
echo "--- self test ---"
grep -E "TREK-TEST" "$LOG" || echo "(no self-test output)"
echo
echo "--- mod runtime log ---"
grep -E "\[TREK\]" "$LOG" || echo "(no runtime log)"
echo
echo "--- errors mentioning the mod ---"
grep -inE "(ERROR|WARN).*(TREK|TrekShuttle)" "$LOG" | head -40 || true
