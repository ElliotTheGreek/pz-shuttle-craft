"""Generates the Emergency Medical Hologram: mesh, texture, portrait, renders.

    python tools/gen_emh.py TrekShuttle/42

**The figure is vendored, not generated here.** `tools/assets/trek_emh/`
holds the GLB that the fal.ai image-to-3D toolkit made from the concept image
in `design/art/emh/`, with `SOURCE.txt` beside it naming the model, the date
and the prompt. That is the convention `tools/assets/type6_shuttle/` set and
`import_quaternius.py`'s header gives the reason: **regenerating the mod must
not require network access, Blender or a third-party package.** Re-running fal
gives a *different* figure, not the same one again, so the GLB is the raw.

What this script does own is everything after the import, and the important
half of it is the recolour.

---------------------------------------------------------------------
What makes him a hologram rather than a mannequin
---------------------------------------------------------------------
The mesh is a person in a uniform, and left with its own photographic diffuse
it would read as a shop dummy standing in the sick bay. Three passes over the
texture fix that, and every one of them is deterministic -- no randomness
anywhere -- so re-running this writes a byte-identical file and a regenerated
asset is never a silent diff. That rule is in `gen_warpcore.py`'s header and
it applies here.

  * **his own colours, cooled.** The source diffuse survives and a TINT of
    the LCARS blue (`H.P.blue`, 0.60 0.80 1.00) is mixed over it. The first
    figure was mapped wholly onto the blue ramp and read as a blue ghost; the
    Doctor everybody remembers is a solid man in black and teal, and it is
    the scanlines, not the hue, that make him projected;
  * **scanlines.** Bands across him at a fixed height, dimmed. That is what
    says "projected" in a still image, and the game's camera only ever gives
    it a still image;
  * **a lifted floor**, so the darkest parts glow rather than going black
    against a dark deck.

---------------------------------------------------------------------
Size
---------------------------------------------------------------------
`C.EmhHeight` tiles, fitted by **height** -- which is the whole reason
`import_glb` grew a `target_height` parameter. A hull is fitted into a parking
space; a person is fitted under a deckhead, and scaling a standing figure by
its footprint makes its size an accident of how wide its shoulders are.

The number to trust is the **bounding box this prints**, not the constant, and
that is the bat'leth's lesson: `SPAN = 0.46` drew 0.531 across.

---------------------------------------------------------------------
Why the scanlines are not texture rows
---------------------------------------------------------------------
The obvious scanline is one texel row in four, and it was written that way
first. **It renders as wood grain.** An image-to-3D model's UVs are an atlas
of islands lying at whatever angle packed best, so a row of the texture is not
a horizontal line on the figure -- it is a different diagonal on every patch
of him, and at 1024 texels over a model 1.25 tiles tall the pitch aliases into
moire as well. The first render showed a man in a fingerprint.

So the bands are laid in **world height** instead: the mesh's own UVs are
rasterised once to give every texel the height of the surface it lands on, and
a texel is dimmed when that height falls inside a band. The result is level
lines across him wherever they happen to fall in the atlas, at a pitch chosen
against the size he is actually drawn at.

It cost a render to find and it is invisible in the source, which is the
lesson this file is the fourth in the project to learn.
"""
import math
import os
import struct
import sys
import wave

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pngwrite import Image
from preview_model import read_png_rgba, parse_x
from import_gltf import import_glb
from meshbuild import MeshBuilder

SOURCE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      "assets", "trek_emh", "trek_emh.glb")

# Tiles. The warp core is 1.30 and stands in a passage the crew walk down; a
# person is a shade shorter than the ship's power plant. Kept in step by hand
# with C.EmhHeight in TREK_Config.lua, which is what the game reads.
EMH_HEIGHT = 1.25

# The mesh name written into the .x file. Not "TREKShuttle", which is what
# import_glb hardcoded before the EMH needed it.
MESH_NAME = "TREKEMH"

# Which way he faces, in degrees about the up axis.
#
# An image-to-3D figure comes out facing the camera that made him, which is
# +Z -- due north in this engine, so he stood in the sick bay with his back to
# the whole cabin. Turned to face **south**, which is the facing every sprite
# set in C.Sprites falls back to and the one the game's isometric camera
# actually shows the front of.
#
# The first render is what caught it. From the source it looked finished.
EMH_YAW = 180

# The LCARS blue the panel, the light and the helm all use: H.P.blue.
BLUE = (0.60, 0.80, 1.00)

# How much of the LCARS blue is mixed into his own colours, 0..1.
#
# **He is the Doctor, not a ghost.** The first figure was mapped wholly onto
# the blue ramp, and in game he read as a blue mannequin: the thing everybody
# remembers about the EMH is that he looks like a solid man in a black-and-teal
# uniform, and the shimmer is only how he arrives. So his own diffuse -- skin,
# teal yoke, grey collar, gold badge -- survives, with a cool cast over it that
# says "projected" without repainting him.
TINT = 0.18

# How far off black the darkest texel is allowed to sit, 0..1. A black
# uniform at zero loses its legs against the dark deck at the game's camera
# distance; a hologram is light, so nothing on him is quite unlit.
FLOOR = 0.10

# The scanlines, in world height rather than in texture rows -- see the
# header. SCAN_PITCH is the distance between bands in tiles, SCAN_DUTY the
# fraction of each band that is dimmed, and SCAN_DIM how far it is dimmed.
#
# **Fine and faint, not bold.** At 0.08 tiles and a quarter off, the first
# render was a man in a striped prison jumper -- the bands were reading as the
# garment rather than as light on it. A hologram's scanlines are a sheen you
# notice second, so the pitch is a third of that and the dimming an eighth,
# which at the size he is actually drawn is a horizontal grain over the
# uniform and nothing you could mistake for cloth.
SCAN_PITCH = 0.028
SCAN_DUTY = 0.38
SCAN_DIM = 0.92

# The panel portrait, square, at the size TREKEMHWindow draws it.
PORTRAIT = 96

# preview_model draws on this exact flat colour with no antialiasing, so the
# portrait keys it by **exact match** rather than through key_icon.py's colour
# ramp -- the ramp treats anything near the backdrop as backdrop, and a blue
# hologram on a blue-grey field is exactly the case that eats.
PREVIEW_BG = (28, 30, 36)


def height_map(mesh, w, h):
    """Every texel's height on the model, and whether anything lands on it.

    The mesh's own UVs, rasterised once. Each triangle is drawn into texture
    space and its three vertices' heights interpolated across it, which is the
    only way to know where on a *figure* a given texel of an atlas ends up --
    and therefore the only way to draw a line that is level on him rather than
    level on the texture sheet.
    """
    verts, faces, uvs = parse_x(mesh)
    heights = [0.0] * (w * h)
    covered = bytearray(w * h)

    for (ia, ib, ic) in faces:
        # Texture space, with v flipped the way the sampler reads it.
        pts = []
        for i in (ia, ib, ic):
            u, v = uvs[i]
            pts.append((u * w, v * h, verts[i][1]))
        (ax, ay, ah), (bx, by, bh), (cx, cy, ch) = pts
        minx = max(0, int(min(ax, bx, cx)))
        maxx = min(w - 1, int(max(ax, bx, cx)) + 1)
        miny = max(0, int(min(ay, by, cy)))
        maxy = min(h - 1, int(max(ay, by, cy)) + 1)
        d = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(d) < 1e-12:
            continue
        for py in range(miny, maxy + 1):
            for px in range(minx, maxx + 1):
                l1 = ((by - cy) * (px - cx) + (cx - bx) * (py - cy)) / d
                l2 = ((cy - ay) * (px - cx) + (ax - cx) * (py - cy)) / d
                l3 = 1.0 - l1 - l2
                # A whole texel of slack, so the gutter between islands is
                # banded with the island beside it rather than left unlit.
                if l1 < -0.05 or l2 < -0.05 or l3 < -0.05:
                    continue
                k = py * w + px
                heights[k] = l1 * ah + l2 * bh + l3 * ch
                covered[k] = 1
    return heights, covered


def holographic(path, mesh):
    """Rewrites a diffuse texture in place as projected blue light.

    Reads the result back and returns (texels touched, how many carry a
    scanline, mean luminance) so the caller can print it: a recolour that
    silently did nothing would leave a flesh-toned mannequin standing in the
    sick bay and look exactly like a working build, and a band pass that
    covered nothing would be the same failure one level down.
    """
    w, h, px = read_png_rgba(path)
    heights, covered = height_map(mesh, w, h)

    img = Image(w, h)
    lit, banded = 0, 0
    total = 0.0
    for y in range(h):
        for x in range(w):
            k = y * w + x
            i = k * 4
            r, g, b, a = px[i], px[i + 1], px[i + 2], px[i + 3]
            # Rec. 601 luminance: the same weighting every other tool here
            # uses to decide what is light and what is dark.
            lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255.0
            # His own colour, lifted off black, with the blue mixed in at
            # the luminance it would have had on the old monochrome ramp.
            rgb = []
            for c, tone in ((r, BLUE[0]), (g, BLUE[1]), (b, BLUE[2])):
                v = FLOOR + (1.0 - FLOOR) * c / 255.0
                rgb.append((1.0 - TINT) * v + TINT * tone * lum)
            scale = 1.0
            if covered[k]:
                phase = (heights[k] / SCAN_PITCH) % 1.0
                if phase < SCAN_DUTY:
                    scale = SCAN_DIM
                    banded += 1
            total += (0.299 * rgb[0] + 0.587 * rgb[1]
                      + 0.114 * rgb[2]) * scale
            img.set(x, y, tuple(min(255, int(v * scale * 255 + 0.5))
                                for v in rgb) + (a,))
            lit += 1
    img.save(path)
    return lit, banded, total / max(1, lit)


def portrait(mesh, texture, out, size=PORTRAIT):
    """The panel's picture of him, rendered from the model he actually is.

    Not drawn separately, for the reason DEV_GUIDE.md gives under *An icon can
    be rendered from the model instead of drawn*: the portrait and the figure
    standing on the deck are then the same object, from the same mesh and the
    same texture, and the two cannot drift apart.

    Head and shoulders, because at panel size a whole standing figure is a
    blue smudge: the render is cropped to the top of the silhouette and scaled
    down, and the flat backdrop is keyed out by exact match.
    """
    big = size * 5
    tmp = out + ".full.png"
    render_to(mesh, texture, tmp, big, 0.0)
    w, h, px = read_png_rgba(tmp)

    # Where the figure actually is in the frame, so the crop follows the model
    # rather than a guess. Anything that is not the backdrop is him.
    xs, ys = [], []
    for y in range(h):
        for x in range(w):
            i = (y * w + x) * 4
            if (px[i], px[i + 1], px[i + 2]) != PREVIEW_BG:
                xs.append(x)
                ys.append(y)
    if not xs:
        raise ValueError("the render is empty; the mesh or texture is wrong")
    top, bottom = min(ys), max(ys)
    # Head and shoulders is the top quarter of a standing figure, squared off
    # about the centre of the silhouette so he is not off to one side.
    crop = max(1, int((bottom - top) * 0.28))
    cx = (min(xs) + max(xs)) // 2
    x0 = max(0, cx - crop // 2)
    y0 = max(0, top - crop // 12)

    img = Image(size, size, (0, 0, 0, 0))
    for py in range(size):
        for pxx in range(size):
            sx = x0 + int(pxx * crop / size)
            sy = y0 + int(py * crop / size)
            if sx >= w or sy >= h:
                continue
            i = (sy * w + sx) * 4
            c = (px[i], px[i + 1], px[i + 2])
            if c == PREVIEW_BG:
                continue
            img.set(pxx, py, (c[0], c[1], c[2], 255))
    img.save(out)
    os.remove(tmp)
    return size


def render_to(mesh, texture, out, size, yaw):
    """One preview render, through the renderer every other model here uses."""
    tool = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "preview_model.py")
    sys.path.insert(0, os.path.dirname(tool))
    import preview_model
    preview_model.render(mesh, texture, out, size=size, up_axis="y",
                         yaw_deg=yaw)
    return out


def previews(root, mesh, texture):
    """Renders him into design/art/emh/ on every run.

    Yaw 0 looks straight at him and yaw 40 is the three-quarter the game's
    camera actually shows. *Render it and look* is in DEV_GUIDE.md twice and
    it has caught four faults in the hull and three in the replicator; the
    Doctor is the one part of this feature that cannot be fixed later without
    redoing it.
    """
    out = os.path.join("design", "art", "emh")
    os.makedirs(out, exist_ok=True)
    for yaw, name in ((0, "front"), (40, "quarter")):
        render_to(mesh, texture, os.path.join(out, f"preview_emh_{name}.png"),
                  400, float(yaw))
    # **And once at the size he is really drawn.** A 400px render is ten times
    # the figure the game puts on the deck, and judging art at the wrong size
    # is how the first gagh shipped as a bowl of chili: everything reads at
    # 1024 and the question is what survives the shrink. Same rule as
    # tools/vet_icons.py's 32px row.
    render_to(mesh, texture, os.path.join(out, "preview_emh_atsize.png"),
              96, 40.0)
    return out


RATE = 44100


def write_wav(path, samples, peak=24000):
    """A mono 16-bit WAV, the way tools/gen_medical.py writes its three."""
    frames = b"".join(
        struct.pack("<h", int(max(-1.0, min(1.0, s)) * peak)) for s in samples)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with wave.open(path, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(RATE)
        out.writeframes(frames)
    return len(samples) / RATE


def appear_chime(duration=0.70):
    """The sound of the Doctor being projected.

    **A synthesised chime, and there is no speech anywhere in this feature.**
    He is the Emergency Medical Hologram, a descriptive designation rather
    than a named character; his lines are written for this mod and there is
    no imitated voice, because "is it Star Trek without copying a frame of
    the show" is the standard ROADMAP.md sets and this is the feature where
    it bites.

    So: a transporter-adjacent shimmer that resolves into a two-note figure.
    It rises rather than falls, because something is arriving, and it settles
    on a clean interval so it reads as equipment coming on line rather than
    as an alert. Deterministic -- the shimmer is a seeded LCG, not `random`,
    so re-running writes a byte-identical file.
    """
    out = []
    n = int(RATE * duration)
    state = 20260920
    pa = pb = pc = 0.0
    for i in range(n):
        t = i / RATE
        progress = t / duration

        # A short bloom of filtered noise for the first third: the projection
        # forming. Gone by the time the notes are fully in.
        state = (state * 1103515245 + 12345) & 0x7FFFFFFF
        noise = state / 0x3FFFFFFF - 1.0
        shimmer = noise * max(0.0, 1.0 - progress * 3.0) ** 2 * 0.22

        # Two notes, the second fading in under the first: a fifth, which is
        # the least dramatic interval there is.
        rise = min(1.0, t / 0.06)
        fall = min(1.0, (1.0 - progress) / 0.45)
        pa += 2 * math.pi * 523.25 / RATE                  # C5
        pb += 2 * math.pi * 783.99 / RATE                  # G5
        pc += 2 * math.pi * 1046.5 / RATE                  # C6, faint
        second = max(0.0, (progress - 0.25) / 0.25)
        second = min(1.0, second)
        tone = (0.42 * math.sin(pa)
                + 0.30 * math.sin(pb) * second
                + 0.08 * math.sin(pc) * second)
        out.append((tone + shimmer) * rise * fall)
    return out


def measure(path):
    """The mesh's own bounding box, which is its size in game."""
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import meshbbox
    return meshbbox.bbox(path)


# The wall station is generated here with the Doctor because it is one
# fixture: the controls that project him. It replaces industry_01_15, whose
# artwork is unmistakably an air conditioner. The model is shallow, mounted
# above shoulder height on the east bulkhead, and leaves the deck beneath it
# clear for the hologram.
STATION_TEX_W = 128
STATION_TEX_H = 128
STATION_REGIONS = {
    "case":   (0, 0, 64, 64),
    "screen": (64, 0, 128, 64),
    "rail":   (0, 64, 64, 128),
    "edge":   (64, 64, 128, 128),
}


def station_atlas(path):
    """Paints a purpose-built LCARS projector control, not a household unit."""
    dark = (25, 29, 42, 255)
    case = (70, 76, 92, 255)
    edge = (126, 134, 154, 255)
    blue = (76, 158, 232, 255)
    glow = (184, 226, 255, 255)
    amber = (238, 154, 62, 255)
    lilac = (162, 146, 216, 255)
    red = (202, 86, 88, 255)

    img = Image(STATION_TEX_W, STATION_TEX_H, dark)

    x0, y0, x1, y1 = STATION_REGIONS["case"]
    img.rect(x0, y0, x1, y1, case)
    img.rect(x0, y0, x1, y0 + 4, edge)
    img.rect(x0, y1 - 5, x1, y1, dark)
    img.rect(x0 + 5, y0 + 7, x1 - 5, y1 - 8, (48, 53, 69, 255))

    x0, y0, x1, y1 = STATION_REGIONS["screen"]
    img.rect(x0, y0, x1, y1, dark)
    img.rect(x0 + 4, y0 + 4, x1 - 4, y1 - 4, (20, 54, 88, 255))
    img.rect(x0 + 8, y0 + 9, x1 - 8, y0 + 14, glow)
    for i, colour in enumerate((blue, amber, lilac, blue, red)):
        yy = y0 + 20 + i * 7
        width = 39 - (i % 3) * 7
        img.rect(x0 + 9, yy, x0 + 9 + width, yy + 4, colour)
    img.rect(x1 - 12, y0 + 20, x1 - 8, y1 - 9, glow)

    x0, y0, x1, y1 = STATION_REGIONS["rail"]
    img.rect(x0, y0, x1, y1, dark)
    img.rect(x0 + 5, y0 + 5, x1 - 5, y1 - 5, amber)
    img.rect(x0 + 12, y0 + 13, x1 - 5, y0 + 24, lilac)
    img.rect(x0 + 12, y0 + 29, x1 - 16, y0 + 40, blue)
    img.rect(x0 + 12, y0 + 45, x1 - 8, y0 + 54, red)

    x0, y0, x1, y1 = STATION_REGIONS["edge"]
    img.rect(x0, y0, x1, y1, dark)
    img.rect(x0, y0, x1, y0 + 5, edge)
    img.rect(x0, y1 - 6, x1, y1, (12, 14, 22, 255))
    img.save(path)


def station_box(m, e0, n0, h0, e1, n1, h1, region):
    """Adds one axis-aligned box in east/north/height coordinates."""
    p = m.place
    # west/east faces
    m.quad(p(e0, n1, h0), p(e0, n0, h0), p(e0, n0, h1), p(e0, n1, h1),
           region, p(-1, 0, 0))
    m.quad(p(e1, n0, h0), p(e1, n1, h0), p(e1, n1, h1), p(e1, n0, h1),
           region, p(1, 0, 0))
    # north/south faces
    m.quad(p(e0, n0, h0), p(e1, n0, h0), p(e1, n0, h1), p(e0, n0, h1),
           region, p(0, -1, 0))
    m.quad(p(e1, n1, h0), p(e0, n1, h0), p(e0, n1, h1), p(e1, n1, h1),
           region, p(0, 1, 0))
    # bottom/top
    m.quad(p(e0, n1, h0), p(e1, n1, h0), p(e1, n0, h0), p(e0, n0, h0),
           region, p(0, 0, -1))
    m.quad(p(e0, n0, h1), p(e1, n0, h1), p(e1, n1, h1), p(e0, n1, h1),
           region, p(0, 0, 1))


def station_mesh(path):
    """Builds a shallow LCARS station against the east edge of its square."""
    m = MeshBuilder(STATION_TEX_W, STATION_TEX_H, up_axis="y")
    r = STATION_REGIONS

    # The wall is at east +0.5 from a centred world item. The backplate sits
    # just inside it; every control protrudes west, into the room.
    station_box(m, 0.38, -0.34, 0.78, 0.48, 0.34, 1.48, r["case"])
    # Main medical display and a narrower LCARS command rail.
    station_box(m, 0.345, -0.27, 0.90, 0.385, 0.12, 1.39, r["screen"])
    station_box(m, 0.335, 0.15, 0.87, 0.385, 0.28, 1.41, r["rail"])
    # A bright projector lip below the display makes its purpose legible and
    # breaks the rectangular appliance silhouette of the old tile.
    station_box(m, 0.315, -0.23, 0.79, 0.39, 0.24, 0.87, r["edge"])
    return m.emit(path, "TREKEMHStation", "TREK_EMHStation.png")


def station_preview(mesh, texture):
    out = os.path.join("design", "art", "emh", "preview_emh_station.png")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    render_to(mesh, texture, out, 400, 40.0)
    return out


if __name__ == "__main__":
    root = sys.argv[1] if len(sys.argv) > 1 else "TrekShuttle/42"
    texture = os.path.join(root, "media", "textures", "TREK_EMH.png")
    mesh = os.path.join(root, "media", "models_X", "TREK_EMH.x")
    face = os.path.join(root, "media", "ui", "TREK_EmhPortrait.png")
    station_texture = os.path.join(root, "media", "textures",
                                   "TREK_EMHStation.png")
    station_model = os.path.join(root, "media", "models_X",
                                 "TREK_EMHStation.x")
    for path in (texture, mesh, face, station_texture, station_model):
        os.makedirs(os.path.dirname(path), exist_ok=True)

    nv, nf, width, length, height = import_glb(
        SOURCE, mesh, texture, "TREK_EMH.png",
        target_height=EMH_HEIGHT, name=MESH_NAME, yaw=EMH_YAW)

    lit, banded, mean = holographic(texture, mesh)
    print(f"  TREK_EMH.png     {lit} texels recoloured, {banded} carrying a "
          f"scanline, mean luminance {mean:.3f}")
    if banded == 0:
        raise SystemExit("gen_emh: not one texel was banded -- the scanlines "
                         "landed nowhere, and a check against an empty set is "
                         "not a check")
    print(f"  TREK_EMH.x       {nv} verts, {nf} tris, "
          f"{width:.2f}x{length:.2f}x{height:.2f} tiles")

    box = measure(mesh)
    if box:
        dx, dy, dz, n = box
        print(f"  bounding box     {dx:.3f} x {dy:.3f} x {dz:.3f} "
              f"(the warp core is 1.30 tall)")

    chime = os.path.join(root, "media", "sound", "TREK_EmhAppear.wav")
    print(f"  TREK_EmhAppear   {write_wav(chime, appear_chime()):.2f}s")
    print(f"  portrait         {portrait(mesh, texture, face)}px")
    print(f"  renders in {previews(root, mesh, texture)}")

    station_atlas(station_texture)
    station_nv, station_nf = station_mesh(station_model)
    print(f"  TREK_EMHStation.x {station_nv} verts, {station_nf} tris")
    station_box_size = measure(station_model)
    if not station_box_size:
        raise SystemExit("gen_emh: station mesh is not measurable")
    sdx, sdy, sdz, _ = station_box_size
    print(f"  station bounding {sdx:.3f} x {sdy:.3f} x {sdz:.3f} tiles")
    print(f"  station render   {station_preview(station_model, station_texture)}")
    print("EMH model and station written")
