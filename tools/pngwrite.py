"""Minimal RGBA PNG writer plus a 5x7 bitmap font. No third-party deps.

The font carries digits as well as letters: a hull registry is mostly numbers.
"""
import zlib, struct

class Image:
    def __init__(self, w, h, bg=(0, 0, 0, 0)):
        self.w, self.h = w, h
        self.px = bytearray(w * h * 4)
        for i in range(w * h):
            self.px[i*4:i*4+4] = bytes(bg)

    def set(self, x, y, c):
        if 0 <= x < self.w and 0 <= y < self.h:
            i = (y * self.w + x) * 4
            self.px[i:i+4] = bytes(c)

    def get(self, x, y):
        i = (y * self.w + x) * 4
        return tuple(self.px[i:i+4])

    def rect(self, x0, y0, x1, y1, c):
        for y in range(max(0, y0), min(self.h, y1)):
            for x in range(max(0, x0), min(self.w, x1)):
                self.set(x, y, c)

    def frame(self, x0, y0, x1, y1, c, t=1):
        self.rect(x0, y0, x1, y0 + t, c)
        self.rect(x0, y1 - t, x1, y1, c)
        self.rect(x0, y0, x0 + t, y1, c)
        self.rect(x1 - t, y0, x1, y1, c)

    def save(self, path):
        raw = bytearray()
        for y in range(self.h):
            raw.append(0)
            raw += self.px[y*self.w*4:(y+1)*self.w*4]
        def chunk(tag, data):
            c = struct.pack(">I", len(data)) + tag + data
            return c + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        png = b"\x89PNG\r\n\x1a\n"
        png += chunk(b"IHDR", struct.pack(">IIBBBBB", self.w, self.h, 8, 6, 0, 0, 0))
        png += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        png += chunk(b"IEND", b"")
        open(path, "wb").write(png)

# 5x7 font, one string of 7 rows per glyph, '#' = ink.
FONT = {
 'A':"01110 10001 10001 11111 10001 10001 10001",
 'B':"11110 10001 10001 11110 10001 10001 11110",
 'C':"01110 10001 10000 10000 10000 10001 01110",
 'D':"11110 10001 10001 10001 10001 10001 11110",
 'E':"11111 10000 10000 11110 10000 10000 11111",
 'F':"11111 10000 10000 11110 10000 10000 10000",
 'G':"01110 10001 10000 10111 10001 10001 01111",
 'H':"10001 10001 10001 11111 10001 10001 10001",
 'I':"11111 00100 00100 00100 00100 00100 11111",
 'J':"00111 00010 00010 00010 00010 10010 01100",
 'K':"10001 10010 10100 11000 10100 10010 10001",
 'L':"10000 10000 10000 10000 10000 10000 11111",
 'M':"10001 11011 10101 10101 10001 10001 10001",
 'N':"10001 11001 10101 10011 10001 10001 10001",
 'O':"01110 10001 10001 10001 10001 10001 01110",
 'P':"11110 10001 10001 11110 10000 10000 10000",
 'Q':"01110 10001 10001 10001 10101 10010 01101",
 'R':"11110 10001 10001 11110 10100 10010 10001",
 'S':"01111 10000 10000 01110 00001 00001 11110",
 'T':"11111 00100 00100 00100 00100 00100 00100",
 'U':"10001 10001 10001 10001 10001 10001 01110",
 'V':"10001 10001 10001 10001 10001 01010 00100",
 'W':"10001 10001 10001 10101 10101 11011 10001",
 'X':"10001 10001 01010 00100 01010 10001 10001",
 'Y':"10001 10001 01010 00100 00100 00100 00100",
 'Z':"11111 00001 00010 00100 01000 10000 11111",
 '0':"01110 10001 10011 10101 11001 10001 01110",
 '1':"00100 01100 00100 00100 00100 00100 01110",
 '2':"01110 10001 00001 00010 00100 01000 11111",
 '3':"11111 00010 00100 00010 00001 10001 01110",
 '4':"00010 00110 01010 10010 11111 00010 00010",
 '5':"11111 10000 11110 00001 00001 10001 01110",
 '6':"00110 01000 10000 11110 10001 10001 01110",
 '7':"11111 00001 00010 00100 01000 01000 01000",
 '8':"01110 10001 10001 01110 10001 10001 01110",
 '9':"01110 10001 10001 01111 00001 00010 01100",
 '/':"00001 00010 00010 00100 01000 01000 10000",
 ':':"00000 01100 01100 00000 01100 01100 00000",
 '_':"00000 00000 00000 00000 00000 00000 11111",
 ' ':"00000 00000 00000 00000 00000 00000 00000",
 '.':"00000 00000 00000 00000 00000 01100 01100",
 '-':"00000 00000 00000 11111 00000 00000 00000",
}

def text_width(s, scale=1, spacing=1):
    return len(s) * (5 * scale + spacing * scale) - spacing * scale

def draw_text(img, s, x, y, c, scale=1, spacing=1):
    """Top-left anchored text. Returns width drawn."""
    cx = x
    for ch in s.upper():
        rows = FONT.get(ch, FONT[' ']).split()
        for ry, row in enumerate(rows):
            for rx, bit in enumerate(row):
                if bit == '1':
                    img.rect(cx + rx * scale, y + ry * scale,
                             cx + (rx + 1) * scale, y + (ry + 1) * scale, c)
        cx += (5 + spacing) * scale
    return cx - x

def draw_text_centered(img, s, cx, y, c, scale=1, spacing=1):
    w = text_width(s, scale, spacing)
    draw_text(img, s, int(cx - w / 2), y, c, scale, spacing)
