"""What every small craft's hull is made with: paint, weather, glass, and the pictures it is judged on.

This is the Mechs mod's recipe (pz-mechs ART.md 6.5, tools/gen_mule.py and gen_mammoth.py,
PLAYED there), carried here whole so that the shuttle and whatever small craft come after her are
made one way:

  * **one mesh, many skins.** A skin is a sheet; the vehicle script lists them and the engine
    keeps which one a vehicle wears. A skin is a *livery* and a *state* of wear;
  * **the paint is one raw, tinted** (design/art/hull/paint_raw.jpg: a painted panel in neutral
    grey). A livery's colour is laid over it by the raw's own light and dark, and what is much
    darker than the paint (a chip) is left as the primer it is;
  * **the weather is arithmetic over the paint, and a state is four numbers**: how far the
    colour has faded, how much dirt has climbed from the bottom and run down in streaks, how
    much of the noise is corrosion, how much dust is on the glass. Every state of a sheet reads
    the same noise, so `worn` is where `derelict` began: one ship going, not three ships;
  * **the glass and the lamps go on after the weather**, which is for paint;
  * **a mesh built with MeshBuilder.place() is a mirror**: `wound` refuses a face wound the
    other way from the rest, and a vehicle's hull is then turned whole for the vehicle shader
    (`for_vehicle`), which throws faces away by their winding. The pictures here draw both sides
    of a face and cannot see one that is wrong.

The raws are the Mechs mod's own (copied 2026-10-11): generating them again gives different
pictures, so they are kept.
"""
import os

import numpy as np
from PIL import Image

from pngwrite import FONT

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAWS = os.path.join(ROOT, "design", "art", "hull")
STOREY = 2.4494900703430176                # a level, in squares (PILOTING.md 5)

BLACK, DARK, STEEL = (26, 26, 28), (46, 48, 52), (92, 96, 100)
DIRT = (88, 76, 58)

#            fade  dirt  corrosion over  glass dust
STATES = {
    "kept":     (0.00, 0.22, 1.02, 0.06),
    "worn":     (0.22, 0.55, 0.80, 0.24),
    "derelict": (0.42, 0.80, 0.60, 0.50),
}

_raws = {}


def raw(name):
    if name not in _raws:
        path = os.path.join(RAWS, name + "_raw.jpg")
        if not os.path.exists(path):
            raise SystemExit("no raw for '%s' in design/art/hull" % name)
        _raws[name] = Image.open(path).convert("RGB")
    return _raws[name]


def tone(colour, k):
    return tuple(max(0, min(255, int(c * k))) for c in colour[:3])


def text(draw, s, x, y, colour, px):
    """Lettering in the mod's 5x7 font, `px` pixels to a dot."""
    for i, ch in enumerate(s.upper()):
        for r, row in enumerate(FONT.get(ch, "00000 " * 7).split()):
            for c, bit in enumerate(row):
                if bit == '1':
                    draw.rectangle([x + (i * 6 + c) * px, y + r * px, x + (i * 6 + c + 1) * px - 1, y + (r + 1) * px - 1], fill=colour)


def text_width(s, px):
    return (len(s) * 6 - 1) * px


def noise(w, h, seed, coarse=6):
    """Smooth noise in 0..1, w by h: a few octaves of a small random grid, scaled up."""
    rnd = np.random.RandomState(seed)
    out = np.zeros((h, w), np.float32)
    amp, total, cells = 1.0, 0.0, coarse
    for _ in range(4):
        grid = Image.fromarray((rnd.rand(max(2, cells * h // max(w, h) + 1), max(2, cells * w // max(w, h) + 1)) * 255).astype(np.uint8))
        out += amp * np.asarray(grid.resize((w, h), Image.BICUBIC), np.float32) / 255.0
        total += amp
        amp, cells = amp * 0.5, cells * 2
    out /= total
    lo, hi = np.percentile(out, 2), np.percentile(out, 98)
    return np.clip((out - lo) / max(1e-6, hi - lo), 0.0, 1.0)


def paint(w, h, colour, seed):
    """A piece of the painted raw in this colour: the raw's light and dark carried over, and
    its chips left as the dark primer they are. Two of the raw's pixels to one of ours where
    the raw is big enough, fewer where the piece is wider than that."""
    src = raw("paint")
    rnd = np.random.RandomState(seed)
    f = min(2.0, src.width / float(w), src.height / float(h))
    cw, ch = int(w * f), int(h * f)
    x = rnd.randint(0, max(1, src.width - cw + 1))
    y = rnd.randint(0, max(1, src.height - ch + 1))
    a = np.asarray(src.crop((x, y, x + cw, y + ch)).resize((w, h), Image.LANCZOS), np.float32)
    lum = a.mean(axis=2, keepdims=True)
    f = lum / max(1.0, float(np.median(lum)))
    out = np.clip(np.array(colour[:3], np.float32) * f, 0, 255)
    chip = np.clip((0.62 - f) / 0.2, 0.0, 1.0)
    return out * (1 - chip) + a * chip


def glass(w, h):
    """The pane out of its raw: the glass and its gasket, without the frame it was painted in."""
    im = raw("pane")
    a = np.asarray(im, np.float32)
    dark = a.sum(axis=2) < 150
    ys, xs = np.where(dark)
    return im.crop((int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1)).resize((w, h), Image.LANCZOS)


def black_glass(w, h):
    """The pane, smoked until it is black."""
    return np.asarray(glass(w, h), np.float32) * 0.30 + np.array((6, 8, 12), np.float32)


def seams(d, w, h, cols, rows, line, lite):
    for i in range(1, cols):
        d.line([(w * i // cols, 0), (w * i // cols, h - 1)], fill=line)
    for j in range(1, rows):
        y = h * j // rows
        d.line([(0, y), (w - 1, y)], fill=line)
        d.line([(0, y + 1), (w - 1, y + 1)], fill=lite)
    d.rectangle([0, 0, w - 1, h - 1], outline=line)


def weather(img, regions, painted, state, seed0, scorch=0.0):
    """Sun, dirt that climbs from the bottom and runs down in streaks, and corrosion where the
    noise is highest. `painted` says which regions weather as paint does, and whether dirt
    climbs each from its bottom (a roof has no bottom). `scorch` takes the corrosion from
    rust's brown toward burnt black: a hull that was never iron."""
    fade, dirt, over, _ = STATES[state]
    size = img.size[0]
    a = np.asarray(img.convert("RGB"), np.float32).copy()
    rust_src = np.asarray(raw("rust").resize((size, size), Image.LANCZOS), np.float32)
    for seed, (name, box) in enumerate(sorted(regions.items())):
        x0, y0, x1, y1 = box
        w, h = x1 - x0, y1 - y0
        part = a[y0:y1, x0:x1]
        n = noise(w, h, seed0 + seed)
        streak = noise(w, 1, seed0 + 200 + seed, coarse=24).repeat(h, axis=0)
        down = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None].repeat(w, axis=1)
        if name in painted:
            grey = part.mean(axis=2, keepdims=True)
            part[:] = part * (1 - fade) + (grey * 0.85 + 40) * fade
            climb = down ** 2.2 if painted[name] else np.full((h, w), 0.35, np.float32)
            grime = np.clip(dirt * (climb * (0.55 + 0.9 * n) + 0.22 * streak * (0.4 + down)), 0.0, 0.85)[..., None]
            part[:] = part * (1 - grime) + np.array(DIRT, np.float32) * grime
            eat = 0.55 * n + 0.45 * noise(w, h, seed0 + 100 + seed, coarse=28) + (0.16 * down ** 3 if painted[name] else 0.0)
            r = np.clip((eat - over) / 0.035, 0.0, 1.0)[..., None]
            scale = rust_src[y0:y1, x0:x1]
            scale = (scale * 0.6 + scale.mean(axis=2, keepdims=True) * 0.4) * (0.42 + 0.3 * n[..., None])
            if scorch:
                burnt = scale.mean(axis=2, keepdims=True) * np.array((0.50, 0.50, 0.54), np.float32)
                scale = scale * (1 - scorch) + burnt * scorch
            part[:] = part * (1 - r) + scale * r
        else:
            mud = np.clip(dirt * (0.25 + 0.75 * n), 0.0, 0.8)[..., None]
            part[:] = part * (1 - mud) + np.array(DIRT, np.float32) * mud
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8))


def pane(img, box, state, seed, cracked=False):
    """Black glass in a box of the sheet, dusted as its state has it, with a dark gasket."""
    from PIL import ImageDraw
    x0, y0, x1, y1 = box
    w, h = x1 - x0, y1 - y0
    dust = STATES[state][3]
    film = (dust * (0.5 + 0.8 * noise(w, h, seed)))[..., None]
    img.paste(Image.fromarray(np.clip(black_glass(w, h) * (1 - film) + np.array(DIRT, np.float32) * 1.1 * film, 0, 255).astype(np.uint8)), (x0, y0))
    d = ImageDraw.Draw(img)
    d.rectangle([x0, y0, x1 - 1, y1 - 1], outline=BLACK)
    if cracked:
        d.line([(x0 + 3, y1 - 4), (x1 - 4, y0 + 3)], fill=(150, 160, 162))
        d.line([(x0 + w // 2, y0 + 3), (x0 + w // 2 + 5, y1 - 4)], fill=(150, 160, 162))


def lamp(img, box, colour, state):
    """A lamp or a glow: lit, dimmer under dust, and dead on a derelict."""
    from PIL import ImageDraw
    dust = STATES[state][3]
    fill = tone(colour, 1.0 - 0.6 * dust) if state != "derelict" else tone(colour, 0.22)
    ImageDraw.Draw(img).rectangle([box[0], box[1], box[2] - 1, box[3] - 1], fill=fill, outline=BLACK)


# ------------------------------------------------------------------------------ meshes
def wound(m, what):
    """Refuses a mesh with a face wound the other way from the rest. As meshbuild leaves a mesh
    built with place(), every face's own normal, worked out from its corners, points AGAINST
    the normal it was given: that is how a world model is drawn the right way out."""
    v = np.array(m.verts, np.float64)
    wrong = 0
    for a, b, c in m.faces:
        n = np.cross(v[b] - v[a], v[c] - v[a])
        if float(np.dot(n, np.array(m.norms[a], np.float64))) >= 0:
            wrong += 1
    if wrong:
        raise SystemExit("%s: %d of %d faces are wound the other way from the rest: they would be drawn inside out" % (what, wrong, len(m.faces)))


def for_vehicle(m):
    """Turns every face round, for the vehicle shader (pz-mechs DEV_GUIDE.md, "A model built
    with place() is inside out to the vehicle shader": PLAYED there)."""
    m.faces = [(a, c, b) for (a, b, c) in m.faces]
    return m


def seat_chart(m, length_px=350, pad=6):
    """The hull from above, nose up, the vehicle's left at the screen's left: what the seat
    chart and the mechanics screen draw behind their markers (ISVehicleSeatUI draws a vehicle
    350 pixels long, so the vehicle script's extents length has to be the mesh's)."""
    from PIL import ImageDraw
    xs = [v[0] for v in m.verts]
    zs = [v[2] for v in m.verts]
    scale = length_px / (max(zs) - min(zs))
    w, h = int(round((max(xs) - min(xs)) * scale)) + pad * 2, length_px + pad * 2
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for a, b, c in m.faces:
        d.polygon([(pad + (max(xs) - m.verts[i][0]) * scale, pad + (max(zs) - m.verts[i][2]) * scale) for i in (a, b, c)],
                  fill=(70, 76, 88, 235))
    return img


# ------------------------------------------------------------------------------ pictures
def enh(m):
    """A mesh's vertices as (across, along, up)."""
    v = np.array(m.verts, np.float64)
    return np.stack([v[:, 0], v[:, 2], v[:, 1]], axis=1)


def shoot(pieces, size, yaw_deg=-35, frame=None, bg=(28, 30, 36), cull=False):
    """Every piece in one picture, at about the game's angle: (vertices as across, along, up;
    faces; texture coordinates; the sheet). With `cull`, a face seen from behind is not drawn,
    as the engine does it: `pieces` must then be wound as meshbuild leaves them."""
    yaw, pitch = np.radians(yaw_deg), np.radians(30)
    cy, sy, cp, sp = np.cos(yaw), np.sin(yaw), np.cos(pitch), np.sin(pitch)

    def rot(v):
        xr = v[:, 0] * cy - v[:, 1] * sy
        yr = v[:, 0] * sy + v[:, 1] * cy
        return np.stack([xr, yr * cp - v[:, 2] * sp, yr * sp + v[:, 2] * cp], axis=1)

    flat = [rot(p[0]) for p in pieces]
    if frame is None:
        allv = np.concatenate(flat)
        span = max(np.ptp(allv[:, 0]), np.ptp(allv[:, 2])) or 1.0
        frame = ((allv[:, 0].max() + allv[:, 0].min()) / 2, (allv[:, 2].max() + allv[:, 2].min()) / 2, span)
    cx, cu, span = frame
    scale = size * 0.9 / span
    out = np.zeros((size, size, 3), np.uint8)
    out[:] = bg
    zbuf = np.full((size, size), 1e9)
    for (verts, faces, uvs, tex), f in zip(pieces, flat):
        th, tw = tex.shape[:2]
        px = size / 2 + (f[:, 0] - cx) * scale
        py = size / 2 - (f[:, 2] - cu) * scale
        dz = f[:, 1]
        uvs = np.asarray(uvs)
        for a, b, c in faces:
            x0, x1 = int(max(0, np.floor(min(px[a], px[b], px[c])))), int(min(size - 1, np.ceil(max(px[a], px[b], px[c]))))
            y0, y1 = int(max(0, np.floor(min(py[a], py[b], py[c])))), int(min(size - 1, np.ceil(max(py[a], py[b], py[c]))))
            if x1 < x0 or y1 < y0:
                continue
            d = (py[b] - py[c]) * (px[a] - px[c]) + (px[c] - px[b]) * (py[a] - py[c])
            if abs(d) < 1e-9:
                continue
            if cull and np.cross(f[b] - f[a], f[c] - f[a])[1] > 0:
                continue
            gx, gy = np.meshgrid(np.arange(x0, x1 + 1), np.arange(y0, y1 + 1))
            l1 = ((py[b] - py[c]) * (gx - px[c]) + (px[c] - px[b]) * (gy - py[c])) / d
            l2 = ((py[c] - py[a]) * (gx - px[c]) + (px[a] - px[c]) * (gy - py[c])) / d
            l3 = 1 - l1 - l2
            z = l1 * dz[a] + l2 * dz[b] + l3 * dz[c]
            ok = (l1 >= -0.002) & (l2 >= -0.002) & (l3 >= -0.002) & (z < zbuf[y0:y1 + 1, x0:x1 + 1])
            if not ok.any():
                continue
            u = l1 * uvs[a][0] + l2 * uvs[b][0] + l3 * uvs[c][0]
            v = l1 * uvs[a][1] + l2 * uvs[b][1] + l3 * uvs[c][1]
            tx = np.clip((u * tw).astype(int), 0, tw - 1)
            ty = np.clip((v * th).astype(int), 0, th - 1)
            out[y0:y1 + 1, x0:x1 + 1][ok] = tex[ty, tx][ok][:, :3]
            zbuf[y0:y1 + 1, x0:x1 + 1][ok] = z[ok]
    return Image.fromarray(out), frame


def scenery():
    """The road a craft stands on, a person and a car: what it is judged against."""
    from meshbuild import MeshBuilder
    tex = np.zeros((64, 64, 4), np.uint8)
    tex[:32, :32] = (58, 62, 60, 255)
    tex[:32, 31] = (44, 48, 46, 255)
    tex[31, :32] = (44, 48, 46, 255)
    tex[:32, 32:] = (120, 52, 44, 255)            # a car
    tex[32:, :32] = (30, 40, 56, 255)             # its glass
    tex[32:, 32:] = (190, 60, 50, 255)            # a person
    m = MeshBuilder(64, 64, up_axis="y")
    P = m.place
    g, car, pane_, body = (0, 0, 32, 32), (33, 1, 63, 31), (1, 33, 31, 63), (33, 33, 63, 63)
    for x in range(-8, 8):
        for y in range(-6, 6):
            m.quad(P(x, y, 0), P(x + 1, y, 0), P(x + 1, y + 1, 0), P(x, y + 1, 0), g, P(0, 0, 1))

    def block(e0, n0, e1, n1, h0, h, sides, top):
        m.quad(P(e1, n0, h0), P(e1, n1, h0), P(e1, n1, h), P(e1, n0, h), sides, P(1, 0, 0))
        m.quad(P(e0, n1, h0), P(e0, n0, h0), P(e0, n0, h), P(e0, n1, h), sides, P(-1, 0, 0))
        m.quad(P(e0, n0, h0), P(e1, n0, h0), P(e1, n0, h), P(e0, n0, h), sides, P(0, -1, 0))
        m.quad(P(e1, n1, h0), P(e0, n1, h0), P(e0, n1, h), P(e1, n1, h), sides, P(0, 1, 0))
        m.quad(P(e0, n0, h), P(e1, n0, h), P(e1, n1, h), P(e0, n1, h), top, P(0, 0, 1))
    block(-6.4, -2.2, -4.6, 2.2, 0.0, 0.75, car, car)              # a car, 1.8 by 4.4
    block(-6.2, -1.2, -4.8, 0.8, 0.75, 1.35, pane_, car)
    block(3.6, 2.0, 4.1, 2.5, 0.0, 1.25, body, body)                # a person
    return enh(m), m.faces, m.uvs, tex


# ------------------------------------------------------------------------------ a hull, built
class Hull:
    """A hull being built, in (e, n, h): e across (+ is starboard), n along (+ is forward), h up.
    Faces are given as somebody outside sees them and are wound as meshbuild winds its own."""

    def __init__(self, tex, regions, middle_h=1.2):
        from meshbuild import MeshBuilder
        self.m = MeshBuilder(tex, tex, up_axis="y")
        self.tex, self.R = tex, regions
        self.middle = np.array((0.0, 0.0, middle_h))

    def face(self, points, at, outward=None):
        """A flat face from its corners and where each is in the sheet, in pixels. The corners
        are put the way round somebody outside sees them, whichever way they were given."""
        m, P = self.m, self.m.place
        pts = [np.array(p, np.float64) for p in points]
        px = [at(*p) for p in points]
        normal = np.cross(pts[1] - pts[0], pts[2] - pts[0])
        normal /= np.linalg.norm(normal)
        out = np.array(outward, np.float64) if outward is not None else (sum(pts) / len(pts) - self.middle) * (1, 0, 1)
        if np.dot(normal, out) < 0:
            pts, px, normal = pts[::-1], px[::-1], -normal
        first = len(m.verts)
        for p, (u, v) in zip(pts, px):
            m.verts.append(P(*p))
            m.norms.append(P(*normal))
            m.uvs.append((u / self.tex, v / self.tex))
        for i in range(1, len(pts) - 1):
            m.faces.append((first, first + i, first + i + 1))

    def rect(self, name, flip=False, part=None):
        """Corners given bottom left, bottom right, top right, top left wear the whole of a
        region, or the `part` of it between two fractions of its width."""
        x0, y0, x1, y1 = self.R[name]
        if part:
            x0, x1 = x0 + (x1 - x0) * part[0], x0 + (x1 - x0) * part[1]
        if flip:
            x0, x1 = x1, x0
        it = iter([(x0, y1), (x1, y1), (x1, y0), (x0, y0)])
        return lambda e, n, h: next(it)

    def box(self, e0, n0, e1, n1, h0, h1, sides, top=None, front=None, back=None, under="dark"):
        """`sides` has its stern at the left on both flanks."""
        top, front, back = top or sides, front or sides, back or sides
        self.face([(e1, n0, h0), (e1, n1, h0), (e1, n1, h1), (e1, n0, h1)], self.rect(sides), (1, 0, 0))
        self.face([(e0, n1, h0), (e0, n0, h0), (e0, n0, h1), (e0, n1, h1)], self.rect(sides, True), (-1, 0, 0))
        self.face([(e0, n0, h0), (e1, n0, h0), (e1, n0, h1), (e0, n0, h1)], self.rect(back), (0, -1, 0))
        self.face([(e1, n1, h0), (e0, n1, h0), (e0, n1, h1), (e1, n1, h1)], self.rect(front), (0, 1, 0))
        self.face([(e1, n0, h1), (e1, n1, h1), (e0, n1, h1), (e0, n0, h1)], self.rect(top), (0, 0, 1))
        self.face([(e0, n1, h0), (e1, n1, h0), (e1, n0, h0), (e0, n0, h0)], self.rect(under), (0, 0, -1))

    def loft(self, stations):
        """A body from stations, stern to nose: each is where along it, then its belly's edge,
        its waist, its shoulder and its roof's edge, each (how far out, how far up). Three bands
        down each side wear `flank_s` and `flank_p` (each flank's own picture, as somebody
        outside it sees it), the roof wears `top` (from above, stern at the left, port at the
        top), the belly `dark`, and the two ends `stern` and `nose`."""
        self.stations = stations
        self.n0, self.n1 = stations[0][0], stations[-1][0]
        hs = [h for s in stations for _, h in s[1:]]
        self.hb, self.ht = min(hs), max(hs)
        self.ew = max(e for s in stations for e, _ in s[1:])
        R, L = self.R, self.n1 - self.n0

        def flank(side):
            x0, y0, x1, y1 = R["flank_s" if side > 0 else "flank_p"]

            def at(e, n, h):
                along = (n - self.n0) / L if side > 0 else (self.n1 - n) / L
                return (x0 + along * (x1 - x0), y0 + (self.ht - h) / (self.ht - self.hb) * (y1 - y0))
            return at

        def top(e, n, h):
            x0, y0, x1, y1 = R["top"]
            return (x0 + (n - self.n0) / L * (x1 - x0), y0 + (e + self.ew) / (2 * self.ew) * (y1 - y0))

        def dark(e, n, h):
            x0, y0, x1, y1 = R["dark"]
            return ((x0 + x1) / 2 + e * 6, (y0 + y1) / 2 + n * 3)

        for (na, *a), (nb, *b) in zip(stations, stations[1:]):
            for s in (1, -1):
                for k in range(3):
                    self.face([(s * a[k][0], na, a[k][1]), (s * b[k][0], nb, b[k][1]),
                               (s * b[k + 1][0], nb, b[k + 1][1]), (s * a[k + 1][0], na, a[k + 1][1])], flank(s))
            self.face([(a[3][0], na, a[3][1]), (b[3][0], nb, b[3][1]), (-b[3][0], nb, b[3][1]), (-a[3][0], na, a[3][1])], top, (0, 0, 1))
            self.face([(a[0][0], na, a[0][1]), (b[0][0], nb, b[0][1]), (-b[0][0], nb, b[0][1]), (-a[0][0], na, a[0][1])], dark, (0, 0, -1))
        for (n, *o), name, out in ((stations[0], "stern", (0, -1, 0)), (stations[-1], "nose", (0, 1, 0))):
            x0, y0, x1, y1 = R[name]
            ew = max(e for e, _ in o)
            lo, hi = min(h for _, h in o), max(h for _, h in o)
            turn = 1 if name == "stern" else -1          # from behind starboard is at the right; from ahead, at the left

            def cap(e, n_, h, x0=x0, y0=y0, x1=x1, y1=y1, ew=ew, lo=lo, hi=hi, turn=turn):
                return (x0 + (turn * e + ew) / (2 * ew) * (x1 - x0), y0 + (hi - h) / (hi - lo) * (y1 - y0))
            self.face([(e, n, h) for e, h in o] + [(-e, n, h) for e, h in reversed(o)], cap, out)

    # Where a place on the body is in its flank's picture (starboard's; port's is its mirror)
    # and in its top's, in pixels of that region.
    def fx(self, n, region="flank_s"):
        return int(round((n - self.n0) / (self.n1 - self.n0) * (self.R[region][2] - self.R[region][0])))

    def fy(self, h):
        return int(round((self.ht - h) / (self.ht - self.hb) * (self.R["flank_s"][3] - self.R["flank_s"][1])))

    def ty(self, e):
        return int(round((e + self.ew) / (2 * self.ew) * (self.R["top"][3] - self.R["top"][1])))


def sheet(tex, regions, colours, painters, painted, state, seed, scorch=0.0, glass=(), lamps=(), cracked=()):
    """One skin of a hull. `colours` is each region's paint (none: dark); `painters` what is
    drawn on each, in its own pixels; then the weather; then the `glass` (region, box) and the
    `lamps` (region, box, colour), which weather does not touch."""
    from PIL import ImageDraw
    img = Image.new("RGB", (tex, tex), DARK)
    for i, name in enumerate(sorted(regions)):
        x0, y0, x1, y1 = regions[name]
        w, h = x1 - x0, y1 - y0
        colour = colours.get(name)
        tile = Image.fromarray(paint(w, h, colour, seed + i).astype(np.uint8)) if colour else Image.new("RGB", (w, h), DARK)
        if name in painters:
            painters[name](ImageDraw.Draw(tile), w, h)
        img.paste(tile, (x0, y0))
    img = weather(img, regions, painted, state, seed + 500, scorch=scorch)
    for i, (name, box) in enumerate(glass):
        x0, y0 = regions[name][0], regions[name][1]
        pane(img, (x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3]), state, seed + 900 + i,
             cracked=(state == "derelict" and i in cracked))
    for name, box, colour in lamps:
        x0, y0 = regions[name][0], regions[name][1]
        lamp(img, (x0 + box[0], y0 + box[1], x0 + box[2], y0 + box[3]), colour, state)
    return img.convert("RGBA")


def publish(hull, name, mesh_name, prefix, skins, skin_name, build_sheet, media, art, first_state="worn"):
    """Everything a hull needs to be a vehicle's, and what it is judged on: its mesh wound for
    the vehicle shader, a sheet for each skin, its mask, the seat chart's art, and into `art`
    <name>_skins.png (a livery to a row, a state to a column), <name>_a.png and <name>_b.png
    (beside a car and a person, half a square up as the vehicle carries it) and <name>_turn.png."""
    for d in ("models_X", "textures", os.path.join("ui", "vehicles", "seatui"), os.path.join("ui", "vehicles", "mechanic overlay")):
        os.makedirs(os.path.join(media, d), exist_ok=True)
    os.makedirs(art, exist_ok=True)
    m = hull.m
    wound(m, name)
    v, faces = enh(m), list(m.faces)
    xs, ys, zs = zip(*m.verts)
    size = (max(xs) - min(xs), max(ys) - min(ys), max(zs) - min(zs))
    print("%s: %d vertices, %d faces; %.2f wide, %.2f tall, %.2f long; its lowest point %.2f up" % (name, len(m.verts), len(faces), size[0], size[1], size[2], min(ys)))
    if abs(max(zs) + min(zs)) > 0.001 or abs(max(xs) + min(xs)) > 0.001 or abs(min(ys)) > 0.001:
        raise SystemExit("%s is not centred, or does not stand on y = 0" % name)
    chart = seat_chart(m)
    chart.save(os.path.join(media, "ui", "vehicles", "seatui", prefix + "base_small.png"))
    chart.save(os.path.join(media, "ui", "vehicles", "mechanic overlay", prefix + "base.png"))
    Image.new("RGBA", (hull.tex, hull.tex), (0, 0, 0, 255)).save(os.path.join(media, "textures", mesh_name + "_mask.png"))
    for_vehicle(m)
    m.emit(os.path.join(media, "models_X", mesh_name + ".x"), mesh_name.replace("_", ""), mesh_name + ".png")

    states = len(STATES)
    cell = 440
    page = Image.new("RGB", (states * cell, (len(skins) // states) * cell), (28, 30, 36))
    frame, sheets = None, {}
    for i, (livery, state) in enumerate(skins):
        s = build_sheet(livery, state)
        s.save(os.path.join(media, "textures", skin_name(i) + ".png"))
        sheets[i] = np.asarray(s)
        if i == 0:
            s.save(os.path.join(art, name + "_sheet.png"))
        pic, frame = shoot([(v, faces, m.uvs, sheets[i])], cell, yaw_deg=145, frame=frame, cull=True)
        page.paste(pic, ((i % states) * cell, (i // states) * cell))
    page.save(os.path.join(art, name + "_skins.png"))
    scene = [scenery(), (v + (0, 0, 0.5), faces, m.uvs, sheets[0])]
    a, frame = shoot(scene, 900, yaw_deg=145, cull=True)
    a.save(os.path.join(art, name + "_a.png"))
    shoot(scene, 900, yaw_deg=-35, frame=frame, cull=True)[0].save(os.path.join(art, name + "_b.png"))
    turn = Image.new("RGB", (4 * 520, 520), (28, 30, 36))
    worn = list(STATES).index(first_state)
    for i, yaw in enumerate((145, 55, -35, -125)):
        turn.paste(shoot([(v, faces, m.uvs, sheets[worn])], 520, yaw_deg=yaw, cull=True)[0], (i * 520, 0))
    turn.save(os.path.join(art, name + "_turn.png"))
    return size


def vehicle_from(source, path, old, new, old_tex, new_tex, textures, head):
    """A vehicle script written from one that is PLAYED, character for character but for its
    names and its skin blocks (pz-mechs DEV_GUIDE.md, "A working vehicle script is copied
    whole"). `old` and `new` are the vehicle's name, and `old_tex` and `new_tex` its sheet's."""
    import re
    src = open(source, encoding="utf-8").read()
    body = src[src.index("module Base"):]
    blocks = "".join("        skin\n        {\n            texture = %s,\n        }\n\n" % t for t in textures)
    body, n = re.subn(r"(?:        skin\n        \{\n            texture = \w+,\n        \}\n\n)+", lambda _: "@SKINS@", body, count=1)
    if n != 1:
        raise SystemExit("%s has no skin block to follow" % source)
    body = body.replace(old, new).replace(old_tex, new_tex).replace("@SKINS@", blocks)
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(head + body)
