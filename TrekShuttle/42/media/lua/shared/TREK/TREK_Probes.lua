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

function P.unresolved()
    local out = {}
    for _, contact in ipairs(P.contacts()) do
        if contact.status == "reported" or contact.status == "investigated" then
            table.insert(out, contact)
        end
    end
    return out
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

--- Adds a report and enforces a bounded history. Authority only.
function P.addContact(kind, x, y, z, probeId, approximate)
    if isClient() then return nil end
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

    -- Prefer dropping old resolved records. If every record is unresolved,
    -- drop the oldest rather than allowing global mod data to grow forever.
    while #data.contacts > C.MaxContacts do
        local remove = nil
        for i, row in ipairs(data.contacts) do
            if row.status ~= "reported" and row.status ~= "investigated" then
                remove = i
                break
            end
        end
        table.remove(data.contacts, remove or 1)
    end
    return contact
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

function P.setStatus(id, status)
    if isClient() or type(id) ~= "string" then return false end
    for _, contact in ipairs(P.contacts()) do
        if contact.id == id then
            contact.status = status
            return true
        end
    end
    return false
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
