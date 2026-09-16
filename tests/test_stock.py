"""Runs TREK_Util under a real Lua VM with the engine globals stubbed.

Guards two bugs that both end with a container that looks wrong in game and
says nothing in the log:

  * Every container starting at the top of its list, so a cabin of lockers all
    hold the same handful and most of the list never reaches the world.
  * Containers stocked by item count rather than by how full they end up. A
    locker holds 40 units and a microwave 5; "eight items" heaps the microwave
    and leaves the locker at a fifth, and the fix -- U.fill -- is worth
    testing because the alternative is counting tins in game.

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

    -- What build 42 actually provides. InventoryItemFactory is deliberately
    -- absent: the class is in the jar, the Lua global is null, and assuming
    -- otherwise is what left every container in the cabin empty twice.
    _G.instanceItem = function(id)
        return { getFullType = function() return id end }
    end
    _G.InventoryItemFactory = nil
""")
lua.execute('require "TREK/TREK_Config"')
lua.execute('require "TREK/TREK_Util"')

# A Build 42-style container that stores concrete InventoryItem objects and
# exposes the inventory size used by U.addVerified.
#
# `capacity` and `each` make it weigh things the way the engine does:
# getCapacity() is the tile's ContainerCapacity and getContentsWeight() the
# load against it. A capacity of 0 stands for a container type that does not
# declare one, which U.fill has to cope with rather than skip.
lua.execute("""
    function makeLocker(capacity, each)
        local held = {}
        local objects = {}
        local items = {
            size = function() return #held end,
            get = function(self, index) return objects[index + 1] end,
        }
        local container = {
            -- The engine takes either an item or an id here, and U.addVerified
            -- has a strategy for each, so the stub has to accept both.
            AddItem = function(self, item)
                if type(item) == "string" then
                    table.insert(held, item)
                    return { getFullType = function() return item end }
                end
                table.insert(held, item:getFullType())
                return item
            end,
            getItems = function() return items end,
            getCapacity = function() return capacity or 0 end,
            getContentsWeight = function() return #held * (each or 0.8) end,
            setExplored = function() end,
            setDirty = function() end,
            setDrawDirty = function() end,
        }
        local obj = { getContainer = function() return container end }
        return obj, held
    end
""")

U = lua.globals().TREK.Util
C = lua.globals().TREK.Config
make = lua.globals().makeLocker

FRACTION = float(C.FillFraction)
ITEM_CAP = int(C.FillItemCap)

failures = []

LIST_LEN, PER, LOCKERS = 24, 8, 30
lua.execute("stock_list = {}")
stock_list = lua.globals().stock_list
for i in range(1, LIST_LEN + 1):
    stock_list[i] = f"Base.Item{i}"

# --- items can actually be created --------------------------------------
# This is the bug that survived two attempts and reached the game twice: the
# containers were built correctly and every item handed to them failed to
# exist. It is worth testing first and on its own, because with item creation
# broken every other check below still passes on an empty container.
U.resetItemStrategy()
U.resetStockCursors()
obj, held = make(40, 0.8)
added, _ = U.fill(obj, stock_list, None, None)
print(f"item creation: {added} items added with instanceItem")
if added == 0:
    failures.append("no items could be created at all -- the very bug this "
                    "file exists to catch")

# The fallbacks have to work too, or the primary path going away in a future
# build puts us straight back here.
for name, setup in (
    ("instanceItem missing", "_G.instanceItem = nil"),
    ("only InventoryItemFactory", """
        _G.instanceItem = nil
        _G.InventoryItemFactory = {
            CreateItem = function(id)
                return { getFullType = function() return id end }
            end
        }
    """),
):
    lua.execute(setup)
    U.resetItemStrategy()
    U.resetStockCursors()
    obj, held = make(40, 0.8)
    added, _ = U.fill(obj, stock_list, None, None)
    print(f"  fallback, {name}: {added} items")
    if added == 0:
        failures.append(f"nothing could be stocked with {name}")

# And with every path gone it must give up rather than hang or throw.
lua.execute("_G.instanceItem = nil; _G.InventoryItemFactory = nil")
U.resetItemStrategy()
U.resetStockCursors()
obj, held = make(40, 0.8)
obj_broken = lua.eval("""
    (function()
        local container = {
            AddItem = function() return nil end,
            getItems = function() return { size = function() return 0 end } end,
            getCapacity = function() return 40 end,
            getContentsWeight = function() return 0 end,
            setExplored = function() end,
            setDirty = function() end,
            setDrawDirty = function() end,
        }
        return { getContainer = function() return container end }
    end)()
""")
added, _ = U.fill(obj_broken, stock_list, None, None)
print(f"  no path available: {added} items (must be 0, and must not hang)")
if added != 0:
    failures.append("a container with no working add path reported items")

# put the real engine back for everything below
lua.execute("""
    _G.instanceItem = function(id)
        return { getFullType = function() return id end }
    end
    _G.InventoryItemFactory = nil
""")
U.resetItemStrategy()

# --- the rolling cursor spreads a list across containers ---------------
U.resetStockCursors()
seen, firsts = set(), []
for _ in range(LOCKERS):
    obj, held = make(0, 0.8)
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
obj, held = make(0, 0.8)
U.stock(obj, stock_list, PER)
if held[1] != firsts[0]:
    failures.append("reset does not reproduce the original layout")

print(f"{LOCKERS} lockers x {PER} items over a {LIST_LEN}-item list")
print(f"distinct items placed: {len(seen)}/{LIST_LEN}")
print(f"first item in lockers 1-6: {firsts[:6]}")

# --- U.fill reaches the target whatever size the container is ----------
# The real spread: a locker, an oven, a microwave. The same call has to leave
# all three looking stocked, which is the whole reason it works in weight.
print(f"\nfilling to {FRACTION:.0%} of capacity, item cap {ITEM_CAP}:")
for name, capacity, each in (("locker", 40, 0.8), ("oven", 15, 0.8),
                             ("microwave", 5, 0.8), ("counter", 10, 0.8)):
    U.resetStockCursors()
    obj, held = make(capacity, each)
    added, level = U.fill(obj, stock_list, None, None)
    level = float(level)
    print(f"  {name:10s} capacity {capacity:2d}  {added:2d} items  "
          f"{level:.0%} full")
    if level < FRACTION:
        failures.append(f"{name} filled to {level:.0%}, under the "
                        f"{FRACTION:.0%} target")
    # One item past the line is expected; a lot past it is a runaway loop.
    if level > FRACTION + (each / capacity) + 0.001:
        failures.append(f"{name} overshot to {level:.0%}")

# --- a list of very light items stops at the item cap ------------------
# Half a locker of bandages at 0.1 each is two hundred bandages: full by
# weight and absurd to look at. The cap is meant to bind first here.
U.resetStockCursors()
obj, held = make(40, 0.1)
added, level = U.fill(obj, stock_list, None, None)
print(f"\nlight items (0.1 each) in a 40-unit locker: {added} items, "
      f"{float(level):.0%} full")
if added != ITEM_CAP:
    failures.append(f"a light list put {added} items in, not the "
                    f"{ITEM_CAP}-item cap")

# --- a container that will not report a capacity is still stocked ------
U.resetStockCursors()
obj, held = make(0, 0.8)
added, level = U.fill(obj, stock_list, None, None)
print(f"no capacity reported: {added} items (falls back to the item cap)")
if added != ITEM_CAP:
    failures.append(f"a container with no capacity got {added} items, "
                    f"not the {ITEM_CAP}-item cap")

# --- fill keeps spreading the list across containers -------------------
U.resetStockCursors()
firsts = []
for _ in range(4):
    obj, held = make(40, 0.8)
    U.fill(obj, stock_list, None, None)
    firsts.append(held[1])
if len(set(firsts)) == 1:
    failures.append("every filled locker starts on the same item")

# --- a per-entry override is honoured ----------------------------------
U.resetStockCursors()
obj, held = make(40, 0.8)
added, level = U.fill(obj, stock_list, 0.25, None)
if float(level) < 0.25 or float(level) > 0.30:
    failures.append(f"an explicit 25% fill reached {float(level):.0%}")

# --- the real lists have to be long enough to be worth spreading -------
print()
for name in ("medical", "food", "fresh", "cookware", "tools", "linen",
             "weapons", "survival"):
    lst = C.Loot[name]
    if lst is None:
        failures.append(f"C.Loot.{name} does not exist")
        continue
    n = len(lst)
    print(f"  C.Loot.{name:9s} {n:3d} entries")
    if n < 3:
        failures.append(f"C.Loot.{name} has only {n} entries")

if failures:
    print("\nFAIL:")
    for f in failures:
        print("  " + f)
    sys.exit(1)
print("\nloot distribution covers the whole list and fills to capacity")
