"""Generates the phaser: its in-hand model, its icon and its sounds.

    python tools/gen_phaser.py TrekShuttle/42

Everything here is generated rather than hand-authored, so the mod stays
reproducible from source (PHASERS.md 4 and 6).

**The model** is `tools/assets/trek_phaser/phaser_baked.json` and `.png`,
which `tools/bake_phaser.py` makes once from the image-to-3D source; that
file says why the mesh sits in vanilla's M9 frame and how its texture is
painted. This one only turns the bake into what the game reads -- a `.x`
mesh, its texture, the icon rendered from that same mesh, and a review
sheet -- so it needs nothing beyond PIL and numpy.

**The review sheet**, `design/art/weapons/phaser/phaser_sheet.png`, is the
point of the exercise and is written on every run, so it cannot go stale
(DEV_GUIDE.md, *Source art lives in design/art/*): four views with vanilla's
M9 outlined over the side view in the same frame -- the grip has to sit
inside the M9's grip, because that is where the hand closes -- then the
phaser and the M9 at the size a character holds them, over the ground
colours the game draws, and the icon at 64 and 32. **Look at it** before
believing any number the build prints.

**The sounds** are synthesised with the standard library, not copied
franchise audio.
"""
import json, math, os, shutil, struct, sys, wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from meshbuild import MeshBuilder

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
BAKED = os.path.join(HERE, "assets", "trek_phaser", "phaser_baked.json")
SHEET_DIR = os.path.join(REPO, "design", "art", "weapons", "phaser")
M9 = ("C:/Program Files (x86)/Steam/steamapps/common/ProjectZomboid/"
      "media/models_X/weapons/firearm/M9_Pistol.x")


# ---------------------------------------------------------------------------
# The model
# ---------------------------------------------------------------------------
def load_baked():
    data = json.load(open(BAKED))
    data["faces"] = [tuple(f) for f in data["faces"]]
    data["texture_path"] = os.path.join(os.path.dirname(BAKED), data["texture"])
    return data


def face_normal(pa, pb, pc):
    u = [pb[i] - pa[i] for i in range(3)]
    w = [pc[i] - pa[i] for i in range(3)]
    return (u[1] * w[2] - u[2] * w[1], u[2] * w[0] - u[0] * w[2],
            u[0] * w[1] - u[1] * w[0])


def smooth_normals(verts, faces):
    acc = [[0.0, 0.0, 0.0] for _ in verts]
    for a, b, c in faces:
        n = face_normal(verts[a], verts[b], verts[c])      # area-weighted
        for k in (a, b, c):
            for i in range(3):
                acc[k][i] += n[i]
    out = []
    for n in acc:
        length = math.sqrt(sum(x * x for x in n)) or 1.0
        out.append(tuple(x / length for x in n))
    return out


def build_mesh(path, texture_file, model):
    """One output vertex per (vertex, UV) pair.

    Normals are smoothed over the whole surface, including across chart
    seams, so a seam is a place the texture changes and never a crease in
    the lighting.
    """
    verts, faces, uvs = model["verts"], model["faces"], model["uvs"]
    normals = smooth_normals(verts, faces)
    m = MeshBuilder(model["tex_size"], model["tex_size"], up_axis="y")
    index = {}
    for f, corner_uvs in zip(faces, uvs):
        tri = []
        for k, uv in zip(f, corner_uvs):
            key = (k, uv[0], uv[1])
            if key not in index:
                index[key] = len(m.verts)
                m.verts.append(tuple(verts[k]))
                m.norms.append(normals[k])
                m.uvs.append((uv[0], uv[1]))
            tri.append(index[key])
        m.faces.append(tuple(tri))
    return m.emit(path, "TREKPhaser", texture_file)


# ---------------------------------------------------------------------------
# Looking at it
# ---------------------------------------------------------------------------
def view_matrix(yaw, pitch):
    """Gun frame (x side, y muzzle, z down) -> view (right, up, toward us).

    At yaw 0 and pitch 0 it is the side profile with the muzzle to the LEFT,
    the way the old icon and vanilla's pistols lie.
    """
    ya, pa = math.radians(yaw), math.radians(pitch)
    base = [(0, -1, 0), (0, 0, -1), (1, 0, 0)]      # rows: right, up, toward
    cy, sy, cp, sp = math.cos(ya), math.sin(ya), math.cos(pa), math.sin(pa)
    yawm = [(cy, 0, sy), (0, 1, 0), (-sy, 0, cy)]
    pitchm = [(1, 0, 0), (0, cp, -sp), (0, sp, cp)]

    def mul(a, b):
        return [tuple(sum(a[i][k] * b[k][j] for k in range(3))
                      for j in range(3)) for i in range(3)]
    return mul(pitchm, mul(yawm, base))


def project(points, m):
    return [tuple(sum(m[i][k] * p[k] for k in range(3)) for i in range(3))
            for p in points]


def fit_frame(verts, margin=0.86):
    xs = [p[0] for p in verts]
    ys = [p[1] for p in verts]
    span = max(max(xs) - min(xs), max(ys) - min(ys))
    return ((max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2, span / margin)


def draw(size, layers, frame=None, bg=(0, 0, 0, 0), ss=3, outline=None,
         ambient=0.42):
    """A z-buffered software renderer, supersampled, for the sheet and icon.

    **A z-buffer, with back faces culled, on purpose.** The first sheet was
    drawn painter's-style, sorted by each triangle's centre, and could not
    tell a fault in the mesh from a fault in the drawing. This resolves
    depth per pixel and drops faces turned away, as the engine does, so a
    hole or a flipped face shows here the way it would in game.

    Shading is per vertex from smooth normals, interpolated -- the way the
    mesh's own MeshNormals are lit in game. Nothing is drawn unlit: the
    engine has no emissive channel for a weapon, so neither does this.

    A layer is a dict: `verts` (view space), `faces`, and either `rgb` (one
    colour per face), or `uvs` (per face corner) with `texture` (a numpy
    image), or neither to draw its triangle edges in `outline`. `frame`
    fixes the view box so two models can share one scale.
    """
    import numpy as np
    from PIL import Image as PILImage, ImageDraw
    big = size * ss
    cx, cy, span = frame or fit_frame(layers[0]["verts"])
    k = big / span
    colour = np.zeros((big, big, 4), dtype=float)
    colour[:, :] = bg
    zbuf = np.full((big, big), -1e9)
    light = np.array((-0.45, 0.75, 0.5))
    light /= np.linalg.norm(light)
    edges = []

    for layer in layers:
        V = np.array(layer["verts"], dtype=float)
        F = np.array(layer["faces"], dtype=int)
        P = np.stack([big / 2 + (V[:, 0] - cx) * k,
                      big / 2 - (V[:, 1] - cy) * k], axis=1)
        if "rgb" not in layer and "uvs" not in layer:
            edges.extend([tuple(map(tuple, P[f])) for f in F])
            continue
        tex = layer.get("texture")
        uvs = np.array(layer["uvs"]) if "uvs" in layer else None
        fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
        vn = np.zeros_like(V)
        for j in range(3):
            np.add.at(vn, F[:, j], fn)
        vn /= np.linalg.norm(vn, axis=1, keepdims=True) + 1e-12
        diffuse = np.clip(vn @ light, 0.0, None)
        vshade = (ambient + (1.0 - ambient) * diffuse
                  + 0.12 * (1 - np.abs(vn[:, 2])) ** 3)
        for fi, f in enumerate(F):
            if fn[fi, 2] <= 0:
                continue                                   # back face
            (x0, y0), (x1, y1), (x2, y2) = P[f]
            minx = int(max(0, min(x0, x1, x2)))
            maxx = int(min(big - 1, max(x0, x1, x2) + 1))
            miny = int(max(0, min(y0, y1, y2)))
            maxy = int(min(big - 1, max(y0, y1, y2) + 1))
            if minx > maxx or miny > maxy:
                continue
            det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(det) < 1e-12:
                continue
            gx, gy = np.meshgrid(np.arange(minx, maxx + 1) + 0.5,
                                 np.arange(miny, maxy + 1) + 0.5)
            l0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / det
            l1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / det
            l2 = 1.0 - l0 - l1
            inside = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
            if not inside.any():
                continue
            z = l0 * V[f[0], 2] + l1 * V[f[1], 2] + l2 * V[f[2], 2]
            window = zbuf[miny:maxy + 1, minx:maxx + 1]
            win = inside & (z > window)
            if not win.any():
                continue
            window[win] = z[win]
            shade = (l0 * vshade[f[0]] + l1 * vshade[f[1]] + l2 * vshade[f[2]])
            if uvs is not None:
                u = l0 * uvs[fi, 0, 0] + l1 * uvs[fi, 1, 0] + l2 * uvs[fi, 2, 0]
                v = l0 * uvs[fi, 0, 1] + l1 * uvs[fi, 1, 1] + l2 * uvs[fi, 2, 1]
                th, tw = tex.shape[:2]
                tx = np.clip((u * tw).astype(int), 0, tw - 1)
                ty = np.clip((v * th).astype(int), 0, th - 1)
                base = tex[ty, tx, :3].astype(float)
            else:
                base = np.broadcast_to(np.array(layer["rgb"][fi], dtype=float),
                                       shade.shape + (3,))
            out = colour[miny:maxy + 1, minx:maxx + 1]
            out[win, :3] = np.clip(shade[win, None] * base[win], 0, 255)
            out[win, 3] = 255

    img = PILImage.fromarray(colour.astype(np.uint8), "RGBA")
    if edges:
        d = ImageDraw.Draw(img)
        for tri in edges:
            d.polygon(tri, outline=outline + (255,))
    return img.resize((size, size), PILImage.LANCZOS)


def phaser_layer(m, model):
    import numpy as np
    from PIL import Image as PILImage
    if "texture_array" not in model:
        model["texture_array"] = np.asarray(
            PILImage.open(model["texture_path"]).convert("RGB"))
    return {"verts": project(model["verts"], m), "faces": model["faces"],
            "uvs": model["uvs"], "texture": model["texture_array"]}


def m9_layer(m, rgb=None):
    """Vanilla's M9, the mesh behind Handgun03, in the same view.

    For a solid render its faces are reversed: the .x file winds them the
    other way from a glTF import, and this renderer culls by winding, so an
    M9 drawn as it stands is a comparison against its own inside. Seen on
    the first sheet that drew it solid.
    """
    from preview_model import parse_x
    v, f, _ = parse_x(M9)
    layer = {"verts": project(v, m), "faces": f}
    if rgb is not None:
        layer["faces"] = [(a, c, b) for a, b, c in f]
        layer["rgb"] = [rgb] * len(f)
    return layer


def build_icon(model, size=64):
    """The inventory icon, rendered from the mesh the hand holds.

    64x64 on purpose: the phaser has no AttachmentType, so vanilla's hotbar
    never draws it and the blades' 32x32 rule does not apply (DEV_GUIDE.md,
    *A weapon model is a static mesh*).

    Judged against the whole set (tools/vet_icons.py), the first render was
    the dullest icon in it -- mean brightness 72 against the tricorder's 110
    and the hypospray's 174 -- because a three-quarter view from above shows
    the grey top, and grey and black sink into the inventory's dark grey.
    So: a flatter angle that shows the white flank panel, brighter icon
    lighting than the in-game preview, and a one-pixel dark outline, which
    is how every neighbour in the set separates itself from the background.
    """
    import numpy as np
    from PIL import Image as PILImage
    img = draw(size, [phaser_layer(view_matrix(18, 8), model)], ambient=0.62)
    a = np.asarray(img).copy()
    alpha = a[:, :, 3] > 40
    grown = alpha.copy()
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        grown |= np.roll(np.roll(alpha, dy, 0), dx, 1)
    ring = grown & ~alpha
    a[ring] = (18, 18, 22, 230)
    return PILImage.fromarray(a, "RGBA")


def build_sheet(path, model, icon):
    from PIL import Image as PILImage, ImageDraw
    cell = 360
    sheet = PILImage.new("RGBA", (cell * 4, cell + 190), (28, 30, 36, 255))
    d = ImageDraw.Draw(sheet)
    panel = (40, 42, 48, 255)

    # Row 1: side (the M9 outlined in the same frame), quarter, other side, top.
    side = view_matrix(0, 0)
    ph = phaser_layer(side, model)
    frame = fit_frame(ph["verts"], margin=0.8)
    first = draw(cell, [ph], frame=frame, bg=panel)
    first = PILImage.alpha_composite(
        first, draw(cell, [m9_layer(side)], frame=frame, outline=(90, 200, 255)))
    views = [("side; vanilla M9 outlined", first)]
    for label, yaw, pitch in (("quarter", 35, 18), ("other side", 180, 12),
                              ("top", 0, 80)):
        views.append((label, draw(cell, [phaser_layer(
            view_matrix(yaw, pitch), model)], bg=panel)))
    for i, (label, img) in enumerate(views):
        sheet.paste(img, (i * cell, 0))
        d.text((i * cell + 8, 6), label, fill=(210, 210, 210, 255))

    # Row 2: at about the size a character holds it, beside the M9, over the
    # ground colours the game draws, blown up 4x without smoothing.
    grounds = [("grass", (74, 92, 52)), ("tarmac", (70, 70, 72)),
               ("pale roof", (178, 170, 156)), ("night", (18, 20, 28))]
    q = view_matrix(35, 30)
    ph_q = phaser_layer(q, model)
    m9_q = m9_layer(q, rgb=(96, 96, 100))
    for gi, (label, rgb) in enumerate(grounds):
        x0 = gi * cell
        d.text((x0 + 8, cell + 8), f"{label}: phaser 18px, 26px; M9 26px",
               fill=(210, 210, 210, 255))
        for pi, (layer, px_len) in enumerate(((ph_q, 18), (ph_q, 26),
                                              (m9_q, 26))):
            small = draw(px_len, [layer], bg=rgb + (255,), ss=4)
            big = small.resize((px_len * 4, px_len * 4), PILImage.NEAREST)
            sheet.paste(big, (x0 + 8 + pi * 116, cell + 28))

    # The icon at 64 and 32, on the inventory's grey.
    inv = PILImage.new("RGBA", (130, 72), (50, 50, 50, 255))
    inv.alpha_composite(icon, (4, 4))
    inv.alpha_composite(icon.resize((32, 32), PILImage.LANCZOS), (84, 20))
    sheet.paste(inv, (cell * 4 - 140, cell + 110))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.convert("RGB").save(path, optimize=True)


def build_model(root):
    model = load_baked()
    mesh_dir = os.path.join(root, "media", "models_X", "weapons", "firearm")
    tex_dir = os.path.join(root, "media", "textures", "weapons", "firearm")
    os.makedirs(mesh_dir, exist_ok=True)
    os.makedirs(tex_dir, exist_ok=True)
    shutil.copyfile(model["texture_path"], os.path.join(tex_dir, "TREK_Phaser.png"))
    nv, nf = build_mesh(os.path.join(mesh_dir, "TREK_Phaser.x"),
                        "TREK_Phaser.png", model)
    xs, ys, zs = zip(*model["verts"])
    muzzle = model["muzzle"]
    print(f"  mesh    media/models_X/weapons/firearm/TREK_Phaser.x "
          f"({nv} verts, {nf} faces)")
    print(f"  bbox    {max(xs) - min(xs):.3f} across x {max(ys) - min(ys):.3f} "
          f"long x {max(zs) - min(zs):.3f} tall  (M9: 0.020 x 0.151 x 0.100)")
    print(f"  muzzle  offset = 0.0 {muzzle[1]:.4f} {muzzle[2]:.4f}  "
          f"(the model block's muzzle attachment)")
    icon = build_icon(model)
    for out in (os.path.join(root, "media", "textures", "Item_TREK_Phaser.png"),
                os.path.join(root, "media", "ui", "TREK_Phaser.png")):
        icon.save(out, optimize=True)
    print("  icon    media/textures/Item_TREK_Phaser.png (64x64, from the mesh)")
    sheet = os.path.join(SHEET_DIR, "phaser_sheet.png")
    build_sheet(sheet, model, icon)
    print(f"  sheet   {os.path.relpath(sheet, REPO)} -- look at it")


# ---------------------------------------------------------------------------
# The sounds
# ---------------------------------------------------------------------------
class Noise:
    """A seeded LCG, so every run writes byte-identical sounds."""

    def __init__(self, seed=1701):
        self.state = seed

    def next(self):
        self.state = (self.state * 1103515245 + 12345) & 0x7FFFFFFF
        return self.state / 0x3FFFFFFF - 1.0


def write_wav(path, samples, rate=44100, peak=27000, top=None):
    """Normalise to `peak` and write 16-bit mono.

    `top` is the level that maps to `peak`; by default this clip's own
    loudest sample. Pass a shared one to keep several clips at one level.
    """
    top = top or max(1e-9, max(abs(v) for v in samples))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(2)
        output.setframerate(rate)
        output.writeframes(b"".join(
            struct.pack("<h", int(max(-1.0, min(1.0, v / top)) * peak))
            for v in samples))


def lowpass(samples, cutoff, rate=44100):
    """One-pole low-pass: turns white noise into a hiss or a rumble."""
    a = math.exp(-2.0 * math.pi * cutoff / rate)
    out, y = [], 0.0
    for v in samples:
        y = (1.0 - a) * v + a * y
        out.append(y)
    return out


def pulse(rate=44100, duration=0.30):
    """One shot: a *zap*, not a chirp.

    The first version swept 1000 -> 420 Hz with a partial at 1500 and read as
    shrill (the author, 2026-09-24). This one sits an octave and more lower:
    a 480 -> 210 Hz body, a partial at 1.5x rather than 1.5 kHz, a short
    thump underneath and a burst of filtered noise for the crack of the
    discharge.
    """
    noise = Noise(1701)
    n = int(rate * duration)
    hiss = lowpass([noise.next() for _ in range(n)], 2400, rate)
    out, pa, pb, pt = [], 0.0, 0.0, 0.0
    for i in range(n):
        t = i / rate
        p = t / duration
        attack = min(1.0, t / 0.004)
        body = attack * math.exp(-7.5 * p)
        fa = 480.0 - 270.0 * p ** 0.7
        pa += 2.0 * math.pi * fa / rate
        pb += 2.0 * math.pi * fa * 1.5 / rate
        pt += 2.0 * math.pi * (95.0 - 40.0 * p) / rate
        tone = 0.60 * math.sin(pa) + 0.22 * math.sin(pb)             + 0.10 * math.sin(2.0 * pa + 0.6 * math.sin(pb))
        thump = 0.45 * math.sin(pt) * math.exp(-t / 0.045)
        crack = 0.55 * hiss[i] * math.exp(-t / 0.03)
        out.append(body * tone + attack * (thump + crack))
    return out


BEAM_BASE = 196      # Hz; every partial below is a whole number of cycles
BEAM_SECONDS = 1.0   # per loop, which is what makes the loop seamless


def beam_voice(t, phase_shift=0.0):
    """The sustained beam's timbre at time t, periodic in BEAM_SECONDS.

    Every frequency here is a whole number of hertz and the loop is a whole
    second, so each term ends the loop exactly where it began and the wrap is
    silent. Keep that true when changing a number: a 196.5 Hz partial clicks
    once a second for as long as a tree is being cut.
    """
    w = 2.0 * math.pi
    vib = 0.004 * math.sin(w * 3 * t)                      # slow drift
    wobble = 1.0 + 0.16 * math.sin(w * 7 * t) + 0.06 * math.sin(w * 13 * t)
    f = BEAM_BASE
    return wobble * (
        0.55 * math.sin(w * f * t + 40 * vib + phase_shift)
        + 0.25 * math.sin(w * f * 1.5 * t)                 # 294 Hz, whole
        + 0.14 * math.sin(w * f * 2 * t + 0.7 * math.sin(w * 5 * t))
        + 0.08 * math.sin(w * f * 3 * t)
        + 0.22 * math.sin(w * 49 * t))                     # the low growl


def beam_loop(rate=44100):
    """One second of the cutting beam that wraps seamlessly.

    The tone is periodic by construction (beam_voice). The crackle is noise,
    which is not, so it is made periodic by crossfading its own tail into its
    head -- the loop's last sample then leads straight into its first.
    """
    n = int(rate * BEAM_SECONDS)
    fade = int(rate * 0.15)
    noise = Noise(47)
    raw = lowpass([noise.next() for _ in range(n + fade)], 3200, rate)
    crackle = raw[:n]
    for i in range(fade):
        k = i / fade
        crackle[i] = crackle[i] * k + raw[n + i] * (1.0 - k)
    # sparse pops on top of the hiss, placed deterministically
    pops = [0.0] * n
    pn = Noise(99)
    for _ in range(26):
        at = int((pn.next() * 0.5 + 0.5) * (n - 400))
        amp = 0.5 + 0.5 * abs(pn.next())
        for j in range(400):
            pops[at + j] += amp * math.exp(-j / 60.0) * pn.next()
    return [beam_voice(i / rate) + 0.35 * crackle[i] + 0.25 * pops[i]
            for i in range(n)]


def beam_start(rate=44100, duration=0.22):
    """The beam catching: a swell up into the loop's own timbre."""
    n = int(rate * duration)
    noise = Noise(7)
    hiss = lowpass([noise.next() for _ in range(n)], 3000, rate)
    out = []
    for i in range(n):
        t = i / rate
        k = t / duration
        env = k ** 1.6
        bend = math.sin(2.0 * math.pi * (120 + 76 * k) * t)
        out.append(env * (0.6 * beam_voice(t) + 0.4 * bend)
                   + 0.5 * hiss[i] * math.exp(-t / 0.04))
    return out


def beam_end(rate=44100, duration=0.32):
    """The beam letting go: pitch sags and the tone dies away."""
    n = int(rate * duration)
    out, ph = [], 0.0
    for i in range(n):
        t = i / rate
        k = t / duration
        ph += 2.0 * math.pi * (BEAM_BASE - 110 * k) / rate
        env = (1.0 - k) ** 2.2
        out.append(env * (0.6 * math.sin(ph) + 0.3 * math.sin(1.5 * ph)
                          + 0.25 * beam_voice(t) * (1.0 - k)))
    return out


def build_sounds(root):
    sound = os.path.join(root, "media", "sound")
    clips = {
        "TREK_PhaserPulse.wav": pulse(),
        "TREK_PhaserBeam.wav": beam_loop(),
        "TREK_PhaserBeamStart.wav": beam_start(),
        "TREK_PhaserBeamEnd.wav": beam_end(),
    }
    # The loop and its tails are normalised together so the hum does not jump
    # in level when the start hands over to it.
    beam_top = max(abs(v) for name, c in clips.items()
                   if name != "TREK_PhaserPulse.wav" for v in c)
    for name, samples in clips.items():
        if name == "TREK_PhaserPulse.wav":
            write_wav(os.path.join(sound, name), samples, peak=27000)
        else:
            write_wav(os.path.join(sound, name), samples, peak=22000,
                      top=beam_top)
        print(f"  sound   media/sound/{name} ({len(samples) / 44100:.2f} s)")


if __name__ == "__main__":
    root = sys.argv[1]
    build_model(root)
    build_sounds(root)
