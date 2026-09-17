"""Renders the helm console to a PNG without launching the game.

tests/test_helm.py already drives TREK_Helm.lua against stubbed vanilla UI
and records every draw call. This replays those calls with Pillow, using the
real textures from media/ui, so the layout can be looked at -- and vetted with
the Gemini toolkit's analyze-image -- before anyone opens Project Zomboid.

It is an approximation in two known ways: text is drawn in Pillow's default
font rather than PZ's, and texture filtering differs. Colours, positions,
sizes and the LCARS shapes are exact.

    python tools/preview_helm.py out.png [shields: up|down] [speed step 1-6] [joypad]
"""
import os
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MOD = os.path.join(ROOT, "TrekShuttle", "42")

# Reuse the test harness: same stubs, same Lua, no duplicated setup.
src = open(os.path.join(ROOT, "tests", "test_helm.py"), encoding="utf-8").read()
src = src.rsplit("\nmain()", 1)[0]
harness = {"__file__": os.path.join(ROOT, "tests", "test_helm.py")}
exec(compile(src, "test_helm.py", "exec"), harness)


FONTS = {1: ImageFont.load_default(12), 2: ImageFont.load_default(16)}


def measure(_, font, text):
    f = FONTS.get(int(font or 1), FONTS[1])
    return ImageDraw.Draw(Image.new("L", (1, 1))).textlength(str(text or ""), font=f)


def render(out, shields="up", step=3, joypad=False):
    lua, _ = harness["make_lua"]()
    # Measure the way this preview draws, so layout computed from string
    # widths (the title gap in the top bar) is judged honestly.
    lua.globals().py_measureX = measure
    # Record the texture, and text colour, which the test does not need.
    lua.execute("""
        local rec = function(el, kind, x, y, w, h, extra)
            table.insert(draws, { own = rawequal(el, win), el = el, kind = kind,
                                  x = x, y = y, w = w, h = h, extra = extra })
        end
        function ISUIElement:drawTextureScaled(t, x, y, w, h, a, r, g, b)
            rec(self, "tex", x, y, w, h, { tex = t, a = a, r = r, g = g, b = b })
        end
        local function text(el, s, x, y, r, g, b, a, font, align)
            rec(el, "text", x, y, 0, 0, { s = s, r = r, g = g, b = b, a = a,
                                          font = font, align = align })
        end
        function ISUIElement:drawText(s, x, y, r, g, b, a, font) text(self, s, x, y, r, g, b, a, font, "left") end
        function ISUIElement:drawTextRight(s, x, y, r, g, b, a, font) text(self, s, x, y, r, g, b, a, font, "right") end
        function ISUIElement:drawTextCentre(s, x, y, r, g, b, a, font) text(self, s, x, y, r, g, b, a, font, "centre") end
        function ISUIElement:drawRect(x, y, w, h, a, r, g, b)
            rec(self, "rect", x, y, w, h, { a = a, r = r, g = g, b = b })
        end
        win = TREKHelmWindow:new(0, 0, player)
        win:createChildren()
        local s = TREK.Util.state()
        s.bookmarks = {
            { name = "Muldraugh water tower", x = 10612, y = 9412, z = 0 },
            { name = "Riverside dock", x = 6500, y = 5400, z = 0 },
            { name = "West Point gas", x = 11900, y = 6900, z = 0 },
        }
        s.destination = { x = 10612, y = 9412, z = 0 }
        win:refresh()
        win.list.selected = 2
    """)
    lua.execute(f"TREK.Util.setShields({'true' if shields == 'up' else 'false'})")
    lua.execute(f"TREK.Util.setFlightStep({int(step)})")
    if joypad:
        lua.execute("win:onGainJoypadFocus({ player = 0, id = 0 })")
    lua.execute("draws = {}; frame(win)")
    # The list rows draw through the list itself.
    lua.execute("""
        local y = 0
        for _, row in ipairs(win.list.items) do
            y = win.drawBookmark(win.list, y, row, false)
        end
    """)

    win = lua.globals().win
    W, H = int(win.width), int(win.height)
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    font = FONTS
    cache = {}

    def texture(path):
        if path not in cache:
            cache[path] = Image.open(os.path.join(MOD, path)).convert("RGBA")
        return cache[path]

    d = lua.globals().draws
    for i in range(1, len(d) + 1):
        c = d[i]
        el = c.el
        ox = 0 if c.own else int(el.x)
        oy = 0 if c.own else int(el.y)
        e = c.extra
        x, y = ox + float(c.x), oy + float(c.y)
        if c.kind == "rect":
            w, h = float(c.w), float(c.h)
            if w <= 0 or h <= 0:
                continue
            col = (int(e.r * 255), int(e.g * 255), int(e.b * 255), int(e.a * 255))
            layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ImageDraw.Draw(layer).rectangle([x, y, x + w - 1, y + h - 1], fill=col)
            img.alpha_composite(layer)
        elif c.kind == "tex":
            w, h = max(1, round(float(c.w))), max(1, round(float(c.h)))
            t = texture(e.tex).resize((w, h), Image.LANCZOS)
            if e.r is not None:
                r, g, b = t.split()[:3]
                a = t.getchannel("A")
                r = r.point(lambda v, k=e.r: int(v * k))
                g = g.point(lambda v, k=e.g: int(v * k))
                b = b.point(lambda v, k=e.b: int(v * k))
                t = Image.merge("RGBA", (r, g, b, a))
            if e.a is not None and float(e.a) < 1:
                t.putalpha(t.getchannel("A").point(lambda v, k=float(e.a): int(v * k)))
            layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            layer.paste(t, (round(x), round(y)))
            img.alpha_composite(layer)
        elif c.kind == "text":
            f = font.get(int(e.font or 1), font[1])
            s = str(e.s)
            tw = ImageDraw.Draw(img).textlength(s, font=f)
            if e.align == "right":
                x -= tw
            elif e.align == "centre":
                x -= tw / 2
            col = (int(e.r * 255), int(e.g * 255), int(e.b * 255), int((e.a or 1) * 255))
            ImageDraw.Draw(img).text((x, y), s, font=f, fill=col)

    # What the stubbed vanilla children would have drawn in game.
    import re as _re
    dr = ImageDraw.Draw(img)
    lst = win.list
    lx, ly, lw, lh = int(lst.x), int(lst.y), int(lst.width), int(lst.height)
    bg = lst.backgroundColor
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ImageDraw.Draw(layer).rectangle([lx, ly, lx + lw - 1, ly + lh - 1],
        fill=(int(bg.r * 255), int(bg.g * 255), int(bg.b * 255), int(bg.a * 255)))
    img.alpha_composite(layer)
    bc = lst.borderColor
    dr = ImageDraw.Draw(img)
    dr.rectangle([lx, ly, lx + lw - 1, ly + lh - 1],
                 outline=(int(bc.r * 255), int(bc.g * 255), int(bc.b * 255)))
    # Re-draw the rows on top of the list background.
    for i in range(1, len(d) + 1):
        c = d[i]
        if c.own or c.el.Type != "ISScrollingListBox" and not (c.el.items is not None and c.el.itemheight is not None):
            continue
        e = c.extra
        x, y = lx + float(c.x), ly + float(c.y)
        if c.kind == "rect":
            layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
            ImageDraw.Draw(layer).rectangle([x, y, x + float(c.w) - 1, y + float(c.h) - 1],
                fill=(int(e.r * 255), int(e.g * 255), int(e.b * 255), int(e.a * 255)))
            img.alpha_composite(layer)
        elif c.kind == "text":
            f = font.get(int(e.font or 1), font[1])
            tw = ImageDraw.Draw(img).textlength(str(e.s), font=f)
            if e.align == "right":
                x -= tw
            ImageDraw.Draw(img).text((x, y), str(e.s), font=f,
                fill=(int(e.r * 255), int(e.g * 255), int(e.b * 255)))
    info = win.info
    ix, iy, iw, ih = int(info.x), int(info.y), int(info.width), int(info.height)
    colour = (200, 220, 255)
    lines, cur = [], ""
    for chunk in _re.split(r"(<[^>]+>)", str(info.text or "")):
        if chunk.startswith("<RGB:"):
            continue
        if chunk == "<LINE>":
            lines.append(cur); cur = ""
            continue
        for word in chunk.split():
            trial = (cur + " " + word).strip()
            if ImageDraw.Draw(img).textlength(trial, font=font[1]) > iw:
                lines.append(cur); cur = word
            else:
                cur = trial
    lines.append(cur)
    dr = ImageDraw.Draw(img)
    for n, line in enumerate(lines):
        ty = iy + n * 15
        if ty + 14 > iy + ih:
            dr.text((ix, ty), "[OVERFLOWS]", font=font[1], fill=(255, 80, 80))
            print("WARNING: navigation prompt overflows its", ih, "px panel")
            break
        dr.text((ix, ty), line, font=font[1], fill=colour)

    img.convert("RGB").save(out)
    print("wrote", out, f"({W}x{H}, shields {shields}, speed step {step})")


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "helm_preview.png"
    render(out, sys.argv[2] if len(sys.argv) > 2 else "up",
           int(sys.argv[3]) if len(sys.argv) > 3 else 3,
           len(sys.argv) > 4 and sys.argv[4] == "joypad")
