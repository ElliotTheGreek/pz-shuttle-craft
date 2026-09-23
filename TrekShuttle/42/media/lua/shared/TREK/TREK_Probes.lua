--[[ Shuttlecraft -- long-range probes and the contacts they report.

    Contacts are shared ship knowledge, but they do not live in ship state.
    That table is transmitted whole whenever the moving shuttle commits; a
    growing survey history belongs under its own global mod-data key, exactly
    as the replicator's pattern set does.

    This module owns only persistent data and pure state transitions. The
    authority in TREK_Server validates players, spends power and advances the
    active probe. Clients receive a read-only copy and use listeners to redraw
    their UI.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"

TREK = TREK or {}
local C = TREK.Config
local U = TREK.Util

local P = {}
TREK.Probes = P

P.listeners = {}

--- The contact store:
---   serial                    next persistent id source
---   active | nil              one logical probe in flight
---   contacts { ... }          bounded shared reports
---   launches                  lifetime launch count
function P.store()
    local data = ModData.getOrCreate(C.ContactKey)
    data.contacts = data.contacts or {}
    data.serial = tonumber(data.serial) or 0
    data.launches = tonumber(data.launches) or 0
    return data
end

function P.onChange(fn)
    table.insert(P.listeners, fn)
end

function P.notify()
    for _, fn in ipairs(P.listeners) do U.try("probeListener", fn) end
end

--- Publishes contacts after an authority-side change.
function P.publish()
    if isClient() then
        U.warnOnce("contactsOnClient", "a client tried to publish probe contacts; ignored")
        return
    end
    if isServer() then
        U.try("transmitContacts", function() ModData.transmit(C.ContactKey) end)
    end
    P.notify()
end

function P.active()
    return P.store().active
end

function P.contacts()
    return P.store().contacts
end

--- True for a status that is finished with. The set is named once in
--- C.ContactResolved and read here, rather than two string comparisons
--- repeated at each call site -- which is what this function used to be, and
--- is how a fifth status would have been quietly treated as live everywhere.
function P.isResolved(status)
    return C.ContactResolved[status] == true
end

function P.unresolved()
    local out = {}
    for _, contact in ipairs(P.contacts()) do
        if not P.isResolved(contact.status) then
            table.insert(out, contact)
        end
    end
    return out
end

--- One contact by id, or nil.
function P.byId(id)
    if type(id) ~= "string" then return nil end
    for _, contact in ipairs(P.contacts()) do
        if contact.id == id then return contact end
    end
    return nil
end

local function nextId(prefix)
    local data = P.store()
    data.serial = data.serial + 1
    return tostring(prefix or "contact") .. ":" .. tostring(data.serial)
end

--- Starts one persisted logical flight. Authority only.
function P.begin(originX, originY, bearing, distance, ticks)
    if isClient() then return nil end
    local data = P.store()
    if data.active then return nil end

    local dx = math.cos(bearing) * distance
    local dy = math.sin(bearing) * distance
    local active = {
        id = nextId("probe"),
        x0 = math.floor(originX),
        y0 = math.floor(originY),
        bearing = bearing,
        distance = math.floor(distance),
        x = math.floor(originX + dx),
        y = math.floor(originY + dy),
        progress = 0,
        ticks = math.max(1, math.floor(ticks or C.ProbeFlightTicks)),
    }
    data.active = active
    data.launches = data.launches + 1
    return active
end

--- Drops the oldest resolved record, or nil when there is none to drop.
local function dropOldestResolved(data)
    for i, row in ipairs(data.contacts) do
        if P.isResolved(row.status) then
            table.remove(data.contacts, i)
            return row
        end
    end
    return nil
end

--- Adds a report and enforces a bounded history. Authority only.
---
--- `kind` is checked against C.ContactKinds. A contact of a kind nothing
--- knows about would be stored, transmitted, drawn with a nil symbol and
--- never matched by anything looking for a type -- which is a silent failure
--- with a persistent store behind it, so it is refused loudly instead.
function P.addContact(kind, x, y, z, probeId, approximate)
    if isClient() then return nil end
    if not C.ContactKinds[kind] then
        U.log("WARN contact of unknown kind %s refused", tostring(kind))
        return nil
    end
    local data = P.store()
    local contact = {
        id = nextId(kind),
        kind = kind,
        x = math.floor(x),
        y = math.floor(y),
        z = math.floor(z or 0),
        probe = probeId,
        status = "reported",
        approximate = approximate == true,
    }
    table.insert(data.contacts, contact)
    P.prune()
    return contact
end

--- Enforces the two bounds. Authority only, and idempotent.
---
--- **Two bounds, and they are not the same bound.** ROADMAP2: "Keep
--- unresolved contacts, retain only a bounded number of resolved records."
--- So the resolved history is trimmed to C.MaxResolvedContacts whatever the
--- total is -- a crew who have recovered forty crystals do not need forty
--- records saying so -- and only then does the overall cap apply.
---
--- This is called from **setStatus as well as addContact**, and that is the
--- whole point of it being its own function. Pruning only on add is pruning
--- at the wrong moment: a contact becomes resolved when its status changes,
--- which is after the add that last swept the history, so the resolved list
--- grew one past its cap and stayed there. The bound is on a property that
--- setStatus is the only thing that changes.
function P.prune()
    if isClient() then return end
    local data = P.store()
    local resolved = 0
    for _, row in ipairs(data.contacts) do
        if P.isResolved(row.status) then resolved = resolved + 1 end
    end
    while resolved > C.MaxResolvedContacts and dropOldestResolved(data) do
        resolved = resolved - 1
    end

    -- The overall cap drops resolved records first, and falls back to the
    -- oldest of any kind so a save cannot grow for ever on live contacts
    -- alone. Losing a live contact is bad; an unbounded table published to
    -- every client is worse.
    while #data.contacts > C.MaxContacts do
        if not dropOldestResolved(data) then
            table.remove(data.contacts, 1)
        end
    end
end

--- Advances the active flight. Returns the completed probe once, or nil.
function P.advance(work)
    if isClient() then return nil end
    local data = P.store()
    local active = data.active
    if not active then return nil end
    active.progress = math.min(active.ticks, active.progress + math.max(1, work or 1))
    if active.progress < active.ticks then return nil end
    data.active = nil
    return active
end

--- Moves a contact along the lifecycle. Authority only.
---
--- The status is checked against C.ContactStatuses for the reason the kind
--- is: a typo here would set a status nothing recognises, and since nothing
--- recognises it the contact would read as neither live nor resolved --
--- never drawn, never pruned, and there for the life of the save.
---
--- Does **not** publish. The caller does, because a pass that moves several
--- contacts should transmit once.
function P.setStatus(id, status)
    if isClient() or type(id) ~= "string" then return false end
    if not C.ContactStatuses[status] then
        U.log("WARN contact status %s is not one this mod declares", tostring(status))
        return false
    end
    local contact = P.byId(id)
    if not contact then return false end
    contact.status = status
    -- The status is what decides whether a record is history, so the history
    -- bound has to be applied here and not only where records are created.
    P.prune()
    return true
end

-- A client asks for the bounded store when its world starts and keeps the
-- copy the authority returns. Receiving global mod data does not store it by
-- itself in build 42.
Events.OnInitGlobalModData.Add(function()
    if not isClient() then return end
    U.try("requestContacts", function() ModData.request(C.ContactKey) end)
end)

Events.OnReceiveGlobalModData.Add(function(key, data)
    if key ~= C.ContactKey then return end
    if not isClient() or type(data) ~= "table" then return end
    ModData.add(key, data)
    P.notify()
end)

return P
