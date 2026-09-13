"""Syntax-checks Lua sources with lupa. Not a PZ runtime, just a parser."""
import sys, glob, os
from lupa import LuaRuntime
L = LuaRuntime()
paths = []
for a in sys.argv[1:]:
    if os.path.isdir(a):
        for dp, _, fns in os.walk(a):
            paths += [os.path.join(dp, f) for f in fns if f.endswith(".lua")]
    else:
        paths += glob.glob(a)
bad = 0
for p in sorted(paths):
    src = open(p, encoding="utf-8").read()
    try:
        L.compile(src)
        print(f"  ok    {p}")
    except Exception as e:
        bad += 1
        print(f"  FAIL  {p}\n        {e}")
print(f"\n{len(paths)-bad}/{len(paths)} files parse cleanly")
sys.exit(1 if bad else 0)
