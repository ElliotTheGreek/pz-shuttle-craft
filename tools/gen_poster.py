"""Generates the mod poster shown in the Project Zomboid mods screen.

Renders the shuttle mesh over a starfield with the mod's name under it, using
the same software renderer the model previews go through. Nothing here is
hand-authored, so the poster is regenerated whenever the hull changes.

    python tools/gen_poster.py TrekShuttle/42
"""
import sys, os, math
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pngwrite import Image, draw_text_centered, text_width
from preview_model import parse_x, read_png_rgba

W, H = 480, 320
SPACE = (10, 12, 20, 255)
STAR = (206, 214, 236, 255)
STAR_DIM = (108, 118, 148, 255)
TITLE = (226, 232, 242, 255)
SUB = (128, 150, 190, 255)
RULE = (46, 74, 122, 255)


def starfield(img, seed=20250901):
    """A deterministic scatter of stars -- no random module, so the poster is
    byte-identical every time it is regenerated."""
    img.rect(0, 0, W, H, SPACE)
    v = seed
    for _ in range(260):
        v = (v * 1103515245 + 12345) & 0x7FFFFFFF
        x = v % W
        v = (v * 1103515245 + 12345) & 0x7FFFFFFF
        y = v % H
        v = (v * 1103515245 + 12345) & 0x7FFFFFFF
        bright = (v >> 8) % 10
        if bright > 7:
            img.rect(x, y, x + 2, y + 2, STAR)
        else:
            img.set(x, y, STAR_DIM if bright < 4 else STAR)


def draw_mesh(img, xpath, texpath, cx, cy, size):
    """The preview renderer's projection, drawn into an existing image rather
    than a fresh one so the starfield shows through around the hull."""
    verts, faces, uvs = parse_x(xpath)
    verts = [(x, z, y) for (x, y, z) in verts]      # PZ models are Y-up
    tw, th, tex = read_png_rgba(texpath)

    yaw, pitch = math.radians(-38), math.radians(26)
    cyw, syw = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)

    def rotate(p):
        x, y, z = p
        xr = x * cyw - y * syw
        yr = x * syw + y * cyw
        return xr, yr * cp - z * sp, yr * sp + z * cp

    flat = [rotate(p) for p in verts]
    xs = [f[0] for f in flat]
    us = [f[2] for f in flat]
    span = max(max(xs) - min(xs), max(us) - min(us)) or 1.0
    scale = size / span
    mx = (max(xs) + min(xs)) / 2
    mu = (max(us) + min(us)) / 2

    def project(p):
        xr, depth, up = rotate(p)
        return (cx + (xr - mx) * scale, cy - (up - mu) * scale, depth)

    zbuf = {}
    for (a, b, c) in faces:
        pa, pb, pc = project(verts[a]), project(verts[b]), project(verts[c])
        ua, ub, uc = uvs[a], uvs[b], uvs[c]
        minx = max(0, int(min(pa[0], pb[0], pc[0])))
        maxx = min(W - 1, int(max(pa[0], pb[0], pc[0])) + 1)
        miny = max(0, int(min(pa[1], pb[1], pc[1])))
        maxy = min(H - 1, int(max(pa[1], pb[1], pc[1])) + 1)
        d = ((pb[1] - pc[1]) * (pa[0] - pc[0]) + (pc[0] - pb[0]) * (pa[1] - pc[1]))
        if abs(d) < 1e-9:
            continue
        for py in range(miny, maxy + 1):
            for px in range(minx, maxx + 1):
                l1 = ((pb[1] - pc[1]) * (px - pc[0]) + (pc[0] - pb[0]) * (py - pc[1])) / d
                l2 = ((pc[1] - pa[1]) * (px - pc[0]) + (pa[0] - pc[0]) * (py - pc[1])) / d
                l3 = 1 - l1 - l2
                if l1 < -0.002 or l2 < -0.002 or l3 < -0.002:
                    continue
                z = l1 * pa[2] + l2 * pb[2] + l3 * pc[2]
                if z >= zbuf.get((px, py), 1e9):
                    continue
                zbuf[(px, py)] = z
                u = l1 * ua[0] + l2 * ub[0] + l3 * uc[0]
                v = l1 * ua[1] + l2 * ub[1] + l3 * uc[1]
                i = ((int(v * th) % th) * tw + (int(u * tw) % tw)) * 4
                img.set(px, py, tuple(tex[i:i + 4]))


def build(root, out):
    img = Image(W, H, SPACE)
    starfield(img)
    draw_mesh(img,
              os.path.join(root, "media", "models_X", "TREK_Shuttle.x"),
              os.path.join(root, "media", "textures", "TREK_Shuttle.png"),
              cx=W / 2, cy=H * 0.44, size=W * 0.62)

    img.rect(W // 2 - 110, H - 84, W // 2 + 110, H - 82, RULE)
    draw_text_centered(img, "SHUTTLECRAFT", W / 2, H - 72, TITLE, scale=3, spacing=2)
    draw_text_centered(img, "NCC-1701/7", W / 2, H - 40, SUB, scale=1, spacing=2)
    img.save(out)
    print("poster ->", out)


if __name__ == "__main__":
    root = sys.argv[1]
    build(root, os.path.join(root, "poster.png"))
