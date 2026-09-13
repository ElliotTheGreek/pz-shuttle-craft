"""Runs TREK_Util under a real Lua VM with the engine globals stubbed.

Guards the loot-distribution bug: every container starting at the top of its
list means a cabin of medical cabinets all holding the same handful of items,
with most of the list never reaching the world at all.

    python tests/test_stock.py
"""
import os, sys
from lupa import LuaRuntime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LUA = os.path.join(ROOT, "TrekShuttle", "42", "media", "lua")

lua = LuaRuntime(unpack_returned_tuples=True)
lua.execute(f'package.path = "{LUA.replace(os.sep, "/")}/shared/?.lua;" .. package.path')

# Minimal stand-ins for the engine globals the module touches at load time.
lua.execute("""
    -- Project Zomboid runs Kahlua, a Lua 5.1 dialect, where unpack is a
    -- global. Newer Lua moved it to table.unpack, so put it back.
    _G.unpack = _G.unpack or table.unpack
    _G.print = function(...) end
    _G.instanceof = function() return false end
    _G.getCellSizeInSquares = function() return 256 end
    _G.ModData = { getOrCreate = function() return {} end }
    _G.getPlayer = function() return nil end
    _G.getSpecificPlayer = function() return nil end
    _G.getCell = function() return nil end
""")
lua.execute('require "TREK/TREK_Config"')
lua.execute('require "TREK/TREK_Util"')

# A container that just records what it was handed.
lua.execute("""
    function makeLocker()
        local held = {}
        local container = { AddItems = function(self, id, n)
            table.insert(held, id); return {} end }
        local obj = { getContainer = function() return container end }
        return obj, held
    end
""")

U = lua.globals().TREK.Util
C = lua.globals().TREK.Config
make = lua.globals().makeLocker

failures = []

# --- the rolling cursor spreads a list across containers ---------------
LIST_LEN, PER, LOCKERS = 24, 8, 30
lua.execute("stock_list = {}")
stock_list = lua.globals().stock_list
for i in range(1, LIST_LEN + 1):
    stock_list[i] = f"Base.Item{i}"

U.resetStockCursors()
seen, firsts = set(), []
for _ in range(LOCKERS):
    obj, held = make()
    U.stock(obj, stock_list, PER)
    ids = [held[i] for i in range(1, len(held) + 1)]
    if len(ids) != PER:
        failures.append(f"expected {PER} items, got {len(ids)}")
    firsts.append(ids[0])
    seen.update(ids)

if len(seen) != LIST_LEN:
    failures.append(f"only {len(seen)}/{LIST_LEN} distinct items ever placed")
if len(set(firsts[:6])) == 1:
    failures.append("every locker starts on the same item (the original bug)")

# a rebuild must lay things out identically
U.resetStockCursors()
obj, held = make()
U.stock(obj, stock_list, PER)
if held[1] != firsts[0]:
    failures.append("reset does not reproduce the original layout")

print(f"{LOCKERS} lockers x {PER} items over a {LIST_LEN}-item list")
print(f"distinct items placed: {len(seen)}/{LIST_LEN}")
print(f"first item in lockers 1-6: {firsts[:6]}")

# --- the real lists have to be long enough to be worth spreading -------
print()
for name in ("medical", "food", "fresh", "cookware", "tools", "linen"):
    lst = C.Loot[name]
    n = len(lst)
    print(f"  C.Loot.{name:9s} {n:3d} entries")
    if n < 3:
        failures.append(f"C.Loot.{name} has only {n} entries")

if failures:
    print("\nFAIL:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("\nloot distribution covers the whole list")
