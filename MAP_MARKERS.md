# Map markers: what build 42 actually offers

Research for `ROADMAP2.md` 1.5, which says: *"Research the ordinary-client
Build 42 map-symbol API before committing to an implementation. Confirm
creation, transmission, save/load, and removal semantics, and avoid
admin/debug-only calls."*

This is that research. **Sections 1-5 are the findings; section 6 is now
built** -- the store, its bounds, the map view and two-client publication, all
against synthetic contacts (`TREK_Probes.lua`, `TREK_MapContacts.lua`). What
is not built is anything that *creates* a contact, which is the probe itself.

Everything below was read out of the installed **42.20.4** jar and its own
Lua, using the three tools in the order `DEV_GUIDE.md` prescribes: does the
method exist, may Lua call it, and under what condition.

---

## 1. The answer in one paragraph

There are **two** unrelated systems, and the one with the promising name is
the wrong one. Map *symbols* (the pen-and-stamp annotations on the world map)
are Lua-exposed, take world coordinates, persist, and replicate between
players — but **the parts that make them shared and persistent are not
reachable from Lua**. Map *markers* are Lua-exposed and simple, but transient,
unshared, and their only vanilla Lua call site is a main-menu test branch.

So the mod should **own the contacts itself** — which is what the roadmap
already specifies, a separate bounded mod-data store with a request/receive
handshake — and use the engine's symbols as **presentation only**, rebuilt
from that store whenever the map opens. That costs nothing the roadmap was not
already paying, and it removes every dependency on an engine path this project
cannot verify.

---

## 2. What exists

| System | Class | Where it draws |
|---|---|---|
| Map symbols | `zombie.worldMap.symbols.WorldMapSymbolsV2` | on the world map |
| Map markers | `zombie.worldMap.markers.WorldMapMarkersV1` | on the world map |
| World markers | `zombie.iso.WorldMarkers` | in the world, on the ground |

### Lua exposure

`LuaManager$Exposer.exposeAll` is the definitive list (DEV_GUIDE, *A vehicle's
altitude is a floor*). Within `zombie.worldMap` exactly these register:

```
UIWorldMap                          (called from exposeAll at bci 6746)
  -> WorldMapSymbolsV1 / V2         + their Text and Texture symbol classes
  -> WorldMapMarkersV1              + WorldMapMarkerV1, WorldMapGridSquareMarkerV1
  -> WorldMapStyleV1 / V2, WorldMapStreetsV1, EditStreetsV1
```

**Not exposed, and this is the load-bearing fact:**

```
WorldMapClient          WorldMapServer          WorldMapSymbolNetworkInfo
```

---

## 3. Map symbols — right shape, unreachable half

Reached as `mapUI.mapAPI:getSymbolsAPIv2()`, where `mapAPI` is
`UIWorldMap:getAPIv3()`.

**The good half is genuinely good:**

- `addTexture(symbolId, worldX, worldY)` and `addUntranslatedText(text,
  layerID, worldX, worldY)` — and the coordinates really are **world squares**,
  the same ones the mod already speaks: `ISWorldMapSymbols.lua:131` builds them
  with `mapAPI:uiToWorldX(x, y)` before calling `addTexture`.
- The returned symbol takes `setRGBA(r,g,b,a)` and `setAnchor(0.5, 0.5)`.
- `removeSymbol`, `removeSymbolByIndex`, `getSymbolCount`, `getSymbolByIndex`.
- **A mod may register its own symbol art.** Vanilla declares every one of its
  symbols in a plain shared Lua file,
  `media/lua/shared/Definitions/MapSymbolDefinitions.lua`:
  ```lua
  MapSymbolDefinitions.getInstance():addTexture("ArrowEast",
      "media/ui/LootableMaps/map_arroweast.png", "Locations")
  ```
  so a Starfleet contact glyph is one line in a file of our own.
- The call sites are **ordinary player UI** — `ISWorldMapSymbols.lua` is the
  symbol palette the player uses with the map open, not anything under
  `DebugUIs/` or an editor. That is the provenance check that mattered.

**The unreachable half is the half the roadmap needs:**

| Wanted | Method | Reachable from Lua? |
|---|---|---|
| make it shared | `sendShareSymbol(symbol, WorldMapSymbolNetworkInfo)` | **no** — the second argument's class is not exposed, and **no vanilla Lua calls it at all** |
| who can see it | `setVisibleToEveryone` / `ToFaction` / `ToSafehouse` / `addPlayer` | **no** — all on `WorldMapSymbolNetworkInfo` |
| server persistence | `WorldMapServer.writeSavefile()` → `servermap_symbols.bin` | **no** — `WorldMapServer` is not exposed |

`sendModifySymbol` *is* called from ordinary Lua
(`ISWorldMapSymbols.lua:449`), but it only pushes a change to a symbol that is
already shared; it cannot make one.

So the engine has a complete shared-annotation system and **Lua is given the
drawing end of it and not the sharing end.** Building the mod's contacts on
`sendShareSymbol` would mean calling a method with no vanilla Lua call site,
taking an argument Lua cannot construct — which is precisely the shape
`DEV_GUIDE.md` spends three sections warning about.

---

## 4. Map markers — wrong tool

`mapAPI:getMarkersAPI():addGridSquareMarker(x, y, z, r, g, b, a)`, returning
something with `setBlink(boolean)` and `setMinScreenRadius(int)`.

Attractive — a blinking circle of a chosen screen radius is close to the
"search circle" the roadmap asks for. But:

- **No save or load at all.** The class has `clear()` and nothing else; markers
  are per-`UIWorldMap` and die with the UI.
- **No networking.** Nothing in `zombie.worldMap.network` touches them.
- **Its only vanilla Lua call site is a test branch.** `ISWorldMap.lua:1457`
  sits in the `else` of `if MainScreen.instance.inGame then` — under a comment
  reading `-- TEST in main menu`. That is the `AdminPanel/` shape one more
  time: real, reachable, and not evidence that anybody ships it.

Useful later as a *transient* highlight — "show me where this contact is" from
the probe console — and not as the contact record.

---

## 5. World markers — the tricorder's half

`getWorldMarkers()` is a global, `zombie.iso.WorldMarkers` is exposed, and the
**Tutorial** uses it (`client/Tutorial/Steps.lua:55`) — ordinary shipped code,
the same provenance that made `ignoreAutoVault` safe.

```
addPlayerHomingPoint(player, x, y, texture, r, g, b, a, bool, int)
addDirectionArrow(player, x, y, z, texture, r, g, b, a)
removeAllHomingPoints(player)
```

Per-player, client-side, transient, on the ground rather than on the map. That
is a very good match for the roadmap's *"Long-range systems locate the region;
the tricorder locates the person"* — and it needs no persistence, because the
mod owns the contact.

---

## 6. Recommended design

**The mod owns contacts; the engine draws them.**

1. **The store.** Contacts live in their own bounded mod-data key with a
   request/receive handshake, exactly as `ROADMAP2.md` *Separate bounded
   stores* specifies and exactly as `C.PatternKey` already works. The server
   owns it, commits it, and transmits it when it changes — never inside the
   ship table, which is published whole on every move.
2. **The map.** When the world map opens, the mod walks its own contact list
   and calls `addTexture(...)` once per contact; when it closes, it removes
   the ones it added. Symbols become a *view* of the store, held for the life
   of the map screen only.
3. **Sharing comes free.** Every client rebuilds from the same server-owned
   store, so all crew see the same contacts without touching
   `sendShareSymbol`, and without the mod's contacts ever entering the
   player's own saved annotations.
4. **The close-range half** is `getWorldMarkers():addPlayerHomingPoint(...)`
   from the tricorder, removed when the contact is resolved.
5. **Focus** is `ISWorldMap.ShowWorldMap(playerNum, centerX, centerY, zoom)` —
   the signature already takes a centre, which is the roadmap's *map focus*
   control for nothing.

Why this is better than the alternative rather than merely safer:

- The mod needs a contact **record** anyway — id, type, status, discovery
  time, mission id. An engine symbol cannot hold any of that, so the store
  exists in either design; building on symbols would mean keeping two copies
  in step.
- It cannot be damaged from outside. A shared engine symbol can be deleted by
  its author, hidden with `setAuthorHidden`, or wiped for a whole user by the
  server command `RemoveMapSymbolsForUserCommand`. A contact the ship knows
  about should not vanish because somebody tidied their map.
- It keeps the authority where `MULTIPLAYER.md` demands it. The server decides
  what exists; the client draws what it is told.

### Uncertainty, honestly

The roadmap asks that a broad probe result "show uncertainty honestly — such
as a search circle or corridor — rather than pretending to identify the exact
cupboard." Symbols are point glyphs, so the options are: several symbols laid
out around the contact to suggest an area; one symbol plus a text label giving
a radius; or a transient `addGridSquareMarker` with `setMinScreenRadius` when
the player asks the console to show a contact. The first two persist across
the map being reopened; the third is prettier and vanishes. Worth deciding
with a picture rather than in advance.

---

## 7. Still unverified — needs a game

**There is nothing to look at in a world yet**, and that is worth saying
plainly: contacts are created by probes, probes are step 4, so a fresh world
today has an empty contact log and therefore an empty map. The list below is
what to check the moment the first probe reports, not before.

In the order that matters:

1. **That a mod-added symbol appears at all**, and at the right square. World
   coordinates are confirmed from vanilla's own call site, not from a test.
2. **Whether the world map's symbols persist in single player.** The only
   symbol save files found are `servermap_symbols.bin` (server) and the
   per-item annotations inside `MapItem`; no single-player world-map symbol
   file turned up. If they *do* persist, adding on open and removing on close
   is still correct and prevents duplicates — this is the *"Two shuttles"*
   failure shape, and the mitigation is the same either way.
3. **Whether `MapSymbolDefinitions:addTexture` from a mod's own
   `shared/Definitions/` file is picked up**, and when in load order.
4. **Whether symbols survive the map being closed and reopened** within one
   session, which decides whether the rebuild is per-open or once.
5. **Two clients**, to confirm that rebuilding from the shared store really
   does give both crew the same picture.

---

## 8. Decisions this settles, and one it does not

**Settled:** probes will not use `sendShareSymbol`, `WorldMapSymbolNetworkInfo`
or `WorldMapServer`. Contacts are the mod's own data. Map symbols and world
markers are presentation, rebuilt from it.

**Also settled, by the author, 2026-09-23:** probes get a **separate console**
rather than a page on the helm. That means a new fitting in the interior,
which is a change to `design/buildinged/TrekShuttle_Interior.tbx` in
BuildingEd — geometry belongs to the `.tbx`, not to the Lua (`DEV_GUIDE.md`,
*The interior is authored in BuildingEd*). The cabin is 4x6 with twenty-four
deck squares and no free wall on the port side, so **where it goes is the open
question**, and it is a layout question rather than a code one.

**Not settled:** how a corridor or a search circle should read on the map. See
§6, *Uncertainty, honestly* — that one wants a render and a look.
