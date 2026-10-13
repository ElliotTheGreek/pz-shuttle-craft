--[[ Shuttlecraft -- every word the mod itself puts on screen (SERVERS.md).

    One function, `Text.get`, and every TREK file that shows text reads it in
    place of the engine's `getText`:

        require "TREK/TREK_Text"
        local getText = TREK.Text.get

    It is the engine's own lookup, in the player's own language, with one
    thing done to the answer: **the name this server gives the ship in
    orbit** (sandbox *Name of the ship in orbit*) is put in wherever the
    text says Adirondack. A server that keeps the name pays for one string
    comparison a line.

    What this does not reach, and cannot: text the engine draws without
    asking Lua -- a tape's subtitles on the television, an item's name and
    tooltip, the creation screen's trait descriptions, the sandbox page. A
    server that wants those changed as well ships a lore pack, which replaces
    the translation files themselves and so reaches everything
    (SERVERS.md, *Your own lore*; tools/make_lore_pack.py).

    The engine's function is looked up when a line is asked for, not kept
    from when this file loaded: nothing here depends on load order, and a
    test can stand a different one in.
]]

require "TREK/TREK_Config"
require "TREK/TREK_Util"
require "TREK/TREK_Rules"

TREK = TREK or {}

local Text = {}
TREK.Text = Text

--- The text for a key, in the player's language, as this server names things.
function Text.get(key, ...)
    return TREK.Rules.named(getText(key, ...))
end

--- A line that is already text -- a crew member's own words, built from
--- parts -- as this server names things.
function Text.named(text)
    return TREK.Rules.named(text)
end

---------------------------------------------------------------------------
-- Wrapping, in any language
---------------------------------------------------------------------------
-- The game's strings are Java's, a character to a place; the tests run a
-- stock Lua, whose strings are bytes. The `utf8` library says which: stock
-- Lua has had it since 5.3 and the game's Kahlua never has. Asked that way
-- rather than by measuring a letter written in this file, because the answer
-- must not depend on how either of them decodes its source.
local BYTES = rawget(_G, "utf8") ~= nil

--- The characters of a word, each one whole.
function Text.chars(word)
    local out = {}
    if BYTES then
        for ch in word:gmatch("[\1-\127\194-\244][\128-\191]*") do out[#out + 1] = ch end
    else
        for i = 1, #word do out[#out + 1] = word:sub(i, i) end
    end
    return out
end

--- True for a mark that is drawn on the letter before it, and so must stay
--- on that letter's line: a combining accent, a Thai vowel or tone mark.
function Text.joins(ch)
    if BYTES then return false end
    local code = string.byte(ch) or 0
    return (code >= 0x0300 and code <= 0x036F) or code == 0x0E31
        or (code >= 0x0E34 and code <= 0x0E3A) or (code >= 0x0E47 and code <= 0x0E4E)
end

--- Splits text into lines no wider than `width` in `font`.
---
--- By word, as every panel here always did -- and **a word wider than the
--- line is broken between its characters**. In English that is a rare long
--- name. In Chinese, Japanese and Thai it is every sentence: they are written
--- without spaces, so the whole line is one "word", and a wrap that only
--- knows about spaces draws it straight out of the side of the panel.
function Text.wrap(text, font, width)
    local tm = getTextManager()
    local function fits(s) return tm:MeasureStringX(font, s) <= width end
    local out, line = {}, ""
    for word in tostring(text or ""):gmatch("%S+") do
        local try = line == "" and word or (line .. " " .. word)
        if fits(try) then
            line = try
        else
            if line ~= "" then
                out[#out + 1] = line
                line = ""
            end
            if fits(word) then
                line = word
            else
                local piece = ""
                for _, ch in ipairs(Text.chars(word)) do
                    if piece ~= "" and not fits(piece .. ch) and not Text.joins(ch) then
                        out[#out + 1] = piece
                        piece = ch
                    else
                        piece = piece .. ch
                    end
                end
                line = piece
            end
        end
    end
    if line ~= "" then out[#out + 1] = line end
    return out
end

return Text
