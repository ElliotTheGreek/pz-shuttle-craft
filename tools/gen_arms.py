"""Generates the armoury's weapons: in-hand models, icons, sounds, review sheets.

    python tools/gen_arms.py TrekShuttle/42

Everything is built from `tools/assets/trek_arms/<name>_baked.json` and
`.png`, which `tools/bake_arms.py` made once from each image-to-3D raw, so a
build needs PIL and numpy and nothing else -- the phaser's rule
(`tools/gen_phaser.py`, whose renderer and mesh writer this reuses).

**The review sheets** (`design/art/weapons/<name>/<name>_sheet.png`) are the
point, and are written on every run so they cannot go stale. Each shows four
views with vanilla's gun outlined over the side view **in the same frame** --
the M9 for a pistol, the M16 for a rifle -- because the hand closes where the
vanilla grip is, and a grip that misses it is a weapon held by its barrel.
Then the weapon at the size a character holds it, over the ground colours
the game draws, and its icon at 32. **Look at them** before believing any
number printed here.

**Icons are 32x32**, not the phaser's old 64: every weapon here has an
`AttachmentType` so it can be holstered or slung, and vanilla's hotbar draws
an attachable item's icon assuming 32x32 (`tests/test_assets.py` says why).

**The sounds** are synthesised, not copied: the phaser's *zap* recipe
(gen_phaser.pulse) with each culture's own pitch, body and grit.
"""
import json
import math
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import gen_phaser as gp  # noqa: E402
from meshbuild import MeshBuilder  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ASSETS = os.path.join(HERE, "assets", "trek_arms")
SHEETS = os.path.join(REPO, "design", "art", "weapons")
VANILLA = ("C:/Program Files (x86)/Steam/steamapps/common/ProjectZomboid/"
           "media/models_X/weapons/firearm/")

# name -> (mesh/texture/icon file stem, the vanilla gun it is judged against)
ARMS = {
    "phaser_rifle":      ("TREK_PhaserRifle",      "M16_Rifle"),
    "klingon_pistol":    ("TREK_KlingonDisruptor", "M9_Pistol"),
    "klingon_rifle":     ("TREK_KlingonRifle",     "M16_Rifle"),
    "romulan_pistol":    ("TREK_RomulanDisruptor", "M9_Pistol"),
    "jemhadar_rifle":    ("TREK_PolaronRifle",     "M16_Rifle"),
    "cardassian_pistol": ("TREK_CardassianPhaser", "M9_Pistol"),
}


def load(name):
    data = json.load(open(os.path.join(ASSETS, name + "_baked.json")))
    data["faces"] = [tuple(f) for f in data["faces"]]
    data["texture_path"] = os.path.join(ASSETS, data["texture"])
    return data


def shown(model):
    """The verts as gen_phaser's views expect them: z down.

    A rifle is in the M16's frame, top toward +Z, so for looking at it only
    it is turned half round its barrel -- (x, y, z) -> (-x, y, -z), a
    rotation, not a mirror. The mesh the game reads is never touched.
    """
    if model["kind"] == "rifle":
        return [(-x, y, -z) for x, y, z in model["verts"]]
    return model["verts"]


def layer(m, model):
    import numpy as np
    from PIL import Image
    if "texture_array" not in model:
        model["texture_array"] = np.asarray(Image.open(model["texture_path"]).convert("RGB"))
    return {"verts": gp.project(shown(model), m), "faces": model["faces"],
            "uvs": model["uvs"], "texture": model["texture_array"]}


def vanilla_layer(m, model, gun, rgb=None):
    from preview_model import parse_x
    v, f, _ = parse_x(VANILLA + gun + ".x")
    if model["kind"] == "rifle":
        v = [(-x, y, -z) for x, y, z in v]
    lay = {"verts": gp.project(v, m), "faces": f}
    if rgb is not None:
        lay["faces"] = [(a, c, b) for a, b, c in f]
        lay["rgb"] = [rgb] * len(f)
    return lay


def build_mesh(path, frame_name, texture_file, model):
    verts, faces, uvs = model["verts"], model["faces"], model["uvs"]
    normals = gp.smooth_normals(verts, faces)
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
    return m.emit(path, frame_name, texture_file)


def build_icon(model, size=32):
    """From the mesh the hand holds, a flat three-quarter view, outlined.

    Rendered big and shrunk, with the one-pixel dark ring every neighbour in
    the set has. A rifle is long and thin, so it is drawn on the diagonal --
    the way vanilla's own long guns fill their square -- or at 32 px it is a
    line three pixels deep.
    """
    import numpy as np
    from PIL import Image
    big = 256
    img = gp.draw(big, [layer(gp.view_matrix(18, 8), model)], ambient=0.62)
    if model["kind"] == "rifle":
        img = img.rotate(35, resample=Image.BICUBIC, expand=True)
    box = img.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox()
    img = img.crop(box)
    side = int(max(img.size) * 1.08)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(img, ((side - img.size[0]) // 2, (side - img.size[1]) // 2))
    small = sq.resize((size, size), Image.LANCZOS)
    a = np.asarray(small).copy()
    alpha = a[:, :, 3] > 60
    a[:, :, 3] = np.where(alpha, 255, 0)
    grown = alpha.copy()
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        grown |= np.roll(np.roll(alpha, dy, 0), dx, 1)
    a[grown & ~alpha] = (18, 18, 22, 230)
    return Image.fromarray(a, "RGBA")


def build_sheet(path, name, model, gun, icon):
    from PIL import Image, ImageDraw
    cell = 360
    sheet = Image.new("RGBA", (cell * 4, cell + 190), (28, 30, 36, 255))
    d = ImageDraw.Draw(sheet)
    panel = (40, 42, 48, 255)
    side = gp.view_matrix(0, 0)
    me = layer(side, model)
    frame = gp.fit_frame(me["verts"] + vanilla_layer(side, model, gun)["verts"], margin=0.8)
    first = gp.draw(cell, [me], frame=frame, bg=panel)
    first = Image.alpha_composite(
        first, gp.draw(cell, [vanilla_layer(side, model, gun)], frame=frame,
                       outline=(90, 200, 255)))
    views = [(f"side; vanilla {gun} outlined", first)]
    for label, yaw, pitch in (("quarter", 35, 18), ("other side", 180, 12),
                              ("top", 0, 80)):
        views.append((label, gp.draw(cell, [layer(gp.view_matrix(yaw, pitch), model)],
                                     bg=panel)))
    for i, (label, img) in enumerate(views):
        sheet.paste(img, (i * cell, 0))
        d.text((i * cell + 8, 6), label, fill=(210, 210, 210, 255))
    grounds = [("grass", (74, 92, 52)), ("tarmac", (70, 70, 72)),
               ("pale roof", (178, 170, 156)), ("night", (18, 20, 28))]
    q = gp.view_matrix(35, 30)
    held = 26 if model["kind"] == "pistol" else 60
    me_q = layer(q, model)
    van_q = vanilla_layer(q, model, gun, rgb=(96, 96, 100))
    for gi, (label, rgb) in enumerate(grounds):
        x0 = gi * cell
        d.text((x0 + 8, cell + 8), f"{label}: {held}px, and {gun}",
               fill=(210, 210, 210, 255))
        for pi, lay in enumerate((me_q, van_q)):
            small = gp.draw(held, [lay], bg=rgb + (255,), ss=4)
            k = 4 if held < 40 else 2
            sheet.paste(small.resize((held * k, held * k), Image.NEAREST),
                        (x0 + 8 + pi * (held * k + 8), cell + 28))
    inv = Image.new("RGBA", (72, 72), (50, 50, 50, 255))
    inv.alpha_composite(icon.resize((64, 64), Image.NEAREST), (4, 4))
    sheet.paste(inv, (cell * 4 - 150, cell + 110))
    inv2 = Image.new("RGBA", (40, 40), (50, 50, 50, 255))
    inv2.alpha_composite(icon, (4, 4))
    sheet.paste(inv2, (cell * 4 - 60, cell + 130))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    sheet.convert("RGB").save(path, optimize=True)


# Handgun03's own hand and ground placement fit a pistol baked into the M9's
# frame, as they fit the phaser (trekweapons.txt, TrekPhaserModel). A rifle
# baked into the M16's frame takes AssaultRifle's ground placement and, like
# AssaultRifle, no hand attachment: the engine puts the mesh origin in the
# fist, and the bake put the origin on the grip.
ATTACH = {
    "pistol": """        attachment world
        {
            offset = -0.009 0.062 0.0,
            rotate = 0.0 0.0 0.0,
        }
        attachment Bip01_Prop2
        {
            offset = -0.0338 0.0424 0.0,
            rotate = 90.0008 1.1964 -90.0396,
        }""",
    "rifle": """        attachment world
        {
            offset = 0.02 0.13 0.0,
            rotate = 180.0 0.0 180.0,
        }""",
}
MUZZLE_ROTATE = {"pistol": "-90.0 0.0 0.0", "rifle": "-90.0 0.0 -180.0"}


def model_block(stem, model):
    mz = model["muzzle"]
    lines = [f"    model {stem.replace('TREK_', 'Trek')}Model",
             "    {",
             f"        mesh = weapons/firearm/{stem},",
             f"        texture = weapons/firearm/{stem},",
             "        attachment muzzle",
             "        {",
             f"            offset = 0.0 {mz[1]:.4f} {mz[2]:.4f},",
             f"            rotate = {MUZZLE_ROTATE[model['kind']]},",
             "        }",
             ATTACH[model["kind"]],
             "    }"]
    return "\n".join(lines) + "\n"


SCRIPT_HEAD = """/*  GENERATED by tools/gen_arms.py -- do not edit; change the generator.

    The armoury's weapon models (ARMOURY.md 4), in `module Base` for the
    reason trekweapons.txt gives: WeaponSprite finds no ModelScript in the
    mod's own module, and the weapon draws nothing in hand. The items are in
    trekshuttle.txt and name these by bare name.

    Written from the bakes, so the muzzle -- where the flash and the bolt
    leave -- is the emitter the bake found, and cannot drift from the mesh.  */

module Base
{
"""


def build_models(root):
    mesh_dir = os.path.join(root, "media", "models_X", "weapons", "firearm")
    tex_dir = os.path.join(root, "media", "textures", "weapons", "firearm")
    os.makedirs(mesh_dir, exist_ok=True)
    os.makedirs(tex_dir, exist_ok=True)
    import shutil
    blocks = []
    for name, (stem, gun) in ARMS.items():
        model = load(name)
        shutil.copyfile(model["texture_path"], os.path.join(tex_dir, stem + ".png"))
        nv, nf = build_mesh(os.path.join(mesh_dir, stem + ".x"),
                            stem.replace("_", ""), stem + ".png", model)
        xs, ys, zs = zip(*model["verts"])
        mz = model["muzzle"]
        print(f"{name}: {stem}.x, {nv} verts, {nf} faces; "
              f"{max(xs) - min(xs):.3f} x {max(ys) - min(ys):.3f} x "
              f"{max(zs) - min(zs):.3f}; muzzle offset = 0.0 {mz[1]:.4f} {mz[2]:.4f}")
        blocks.append(model_block(stem, model))
        icon = build_icon(model)
        icon.save(os.path.join(root, "media", "textures", "Item_" + stem + ".png"),
                  optimize=True)
        sheet = os.path.join(SHEETS, name, name + "_sheet.png")
        build_sheet(sheet, name, model, gun, icon)
        print(f"  sheet   {os.path.relpath(sheet, REPO)}")
    path = os.path.join(root, "media", "scripts", "trekarms.txt")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(SCRIPT_HEAD + "\n".join(blocks) + "}\n")
    print(f"  script  media/scripts/trekarms.txt ({len(blocks)} models)")


# ---------------------------------------------------------------------------
# The Starfleet holster
# ---------------------------------------------------------------------------
PZ_MEDIA = "C:/Program Files (x86)/Steam/steamapps/common/ProjectZomboid/media/"
HOLSTER_STEM = "TrekHolster"
HOLSTER_GREY = (58, 61, 68)        # Starfleet charcoal
HOLSTER_GOLD = (196, 158, 72)      # the stitch


def build_holster(root):
    """Vanilla's belt holster, recoloured, with its own clothing XML.

    **The model is vanilla's** (`M_/F_HolsterRight.x`, static, on the pelvis):
    a holster is a holster, and the one vanilla draws already sits where
    vanilla's holster animations reach for it. Only the texture is ours --
    vanilla's `holster_black`, remapped by brightness: the leather to
    Starfleet charcoal, its lighter stitching to gold.

    **The GUID row is merged into the table** gen_uniform.py and
    gen_species.py share, the way they merge theirs; without it the holster
    equips and draws nothing (gen_uniform.py, *Every clothing item is reached
    by GUID*).
    """
    import numpy as np
    from PIL import Image
    import gen_species
    import gen_uniform
    src = np.asarray(Image.open(PZ_MEDIA + "textures/Holster_Black.png")
                     .convert("RGB")).astype(float)
    lum = src.mean(2)
    lo, hi = np.percentile(lum, 5), np.percentile(lum, 97)
    k = np.clip((lum - lo) / (hi - lo + 1e-6), 0, 1)
    grey = np.array(HOLSTER_GREY, dtype=float)
    out = grey[None, None] * (0.55 + 0.9 * k[..., None])
    stitch = k > 0.72
    out[stitch] = HOLSTER_GOLD
    tex_dir = os.path.join(root, "media", "textures", "clothes", "trek")
    os.makedirs(tex_dir, exist_ok=True)
    Image.fromarray(np.clip(out, 0, 255).astype(np.uint8), "RGB").save(
        os.path.join(tex_dir, "holster.png"), optimize=True)

    guid = gen_uniform.clothing_guid(HOLSTER_STEM)
    xml_dir = os.path.join(root, "media", "clothing", "clothingItems")
    os.makedirs(xml_dir, exist_ok=True)
    lines = ['<?xml version="1.0" encoding="utf-8"?>', "<clothingItem>",
             f"\t<m_GUID>{guid}</m_GUID>",
             "\t<m_MaleModel>media\\models_X\\Static\\Clothes\\M_HolsterRight.x</m_MaleModel>",
             "\t<m_FemaleModel>media\\models_X\\Static\\Clothes\\F_HolsterRight.x</m_FemaleModel>",
             "\t<m_Static>true</m_Static>",
             "\t<m_AllowRandomHue>false</m_AllowRandomHue>",
             "\t<m_AllowRandomTint>false</m_AllowRandomTint>",
             "\t<m_AttachBone>Bip01_Pelvis</m_AttachBone>",
             "\t<m_MasksFolder>media/textures/Clothes/Hat/Masks</m_MasksFolder>",
             "\t<textureChoices>clothes\\trek\\holster</textureChoices>",
             "</clothingItem>"]
    with open(os.path.join(xml_dir, HOLSTER_STEM + ".xml"), "w", encoding="utf-8",
              newline="\r\n") as fh:
        fh.write("\n".join(lines) + "\n")
    gen_species.merge_guid_table(
        root, [(f"media/clothing/clothingItems/{HOLSTER_STEM}.xml", guid)])

    # The icon: the same mesh, from the side, in the new texture. 64x64 --
    # a holster provides an attachment, it has no AttachmentType of its own,
    # so the hotbar never draws it.
    from preview_model import parse_x
    v, f, uv = parse_x(PZ_MEDIA + "models_X/Static/Clothes/M_HolsterRight.x")
    tex = np.asarray(Image.open(os.path.join(tex_dir, "holster.png")).convert("RGB"))
    # parse_x hands back per-vertex UVs; the renderer wants them per corner.
    uvs = [[uv[a], uv[b], uv[c]] for a, b, c in f]
    # Its broad face. The mesh sits in the pelvis bone's frame, not upright:
    # it is 0.10 along X, 0.07 along Z and only 0.036 along Y, so the pouch
    # is seen looking along Y, with -X up. Chosen from eight renders; the
    # other seven showed an edge, the opening, or the pouch upside down.
    m = [(0, 0, -1), (-1, 0, 0), (0, -1, 0)]
    lay = {"verts": gp.project(v, m), "faces": [(a, c, b) for a, b, c in f],
           "uvs": [[u[0], u[2], u[1]] for u in uvs], "texture": tex}
    img = gp.draw(256, [lay], ambient=0.6)
    box = img.getchannel("A").getbbox()
    if box:
        img = img.crop(box)
    side = int(max(img.size) * 1.12)
    sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    sq.paste(img, ((side - img.size[0]) // 2, (side - img.size[1]) // 2))
    icon = sq.resize((64, 64), Image.LANCZOS)
    a = np.asarray(icon).copy()
    alpha = a[:, :, 3] > 60
    a[:, :, 3] = np.where(alpha, 255, 0)
    grown = alpha.copy()
    for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
        grown |= np.roll(np.roll(alpha, dy, 0), dx, 1)
    a[grown & ~alpha] = (18, 18, 22, 230)
    out_icon = os.path.join(root, "media", "textures", "Item_TREK_Holster.png")
    Image.fromarray(a, "RGBA").save(out_icon, optimize=True)
    print(f"  holster {HOLSTER_STEM}.xml (GUID {guid}), clothes/trek/holster.png, "
          f"Item_TREK_Holster.png")


# ---------------------------------------------------------------------------
# Sounds
# ---------------------------------------------------------------------------
def shot(seed, duration, f0, f1, ratio, thump, grit, buzz=0.0, cutoff=2400,
         rate=44100):
    """gen_phaser.pulse, with its numbers as arguments.

    `f0` -> `f1` is the body's sweep, `ratio` its partial, `thump` the low
    knock's pitch, `grit` the noise burst's level and `buzz` a square-ish
    edge on the body -- a disruptor is rougher than a phaser, and that edge
    is most of the difference to the ear.
    """
    noise = gp.Noise(seed)
    n = int(rate * duration)
    hiss = gp.lowpass([noise.next() for _ in range(n)], cutoff, rate)
    out, pa, pb, pt = [], 0.0, 0.0, 0.0
    for i in range(n):
        t = i / rate
        p = t / duration
        attack = min(1.0, t / 0.004)
        body = attack * math.exp(-7.0 * p)
        fa = f0 + (f1 - f0) * p ** 0.7
        pa += 2.0 * math.pi * fa / rate
        pb += 2.0 * math.pi * fa * ratio / rate
        pt += 2.0 * math.pi * (thump - 0.4 * thump * p) / rate
        s = math.sin(pa)
        edge = math.copysign(abs(s) ** 0.35, s)
        tone = (0.6 - 0.4 * buzz) * s + 0.4 * buzz * edge + 0.22 * math.sin(pb)
        knock = 0.45 * math.sin(pt) * math.exp(-t / 0.05)
        crack = grit * hiss[i] * math.exp(-t / 0.04)
        out.append(body * tone + attack * (knock + crack))
    return out


SOUNDS = {
    # The rifle is the phaser's zap, a fifth lower and longer.
    "TREK_PhaserRiflePulse": dict(seed=1702, duration=0.40, f0=330, f1=150,
                                  ratio=1.5, thump=80, grit=0.55),
    # Klingon: a snarl -- low, buzzing, and dirty.
    "TREK_KlingonDisruptorPulse": dict(seed=1703, duration=0.34, f0=260, f1=110,
                                       ratio=1.26, thump=70, grit=0.8, buzz=0.8,
                                       cutoff=3600),
    # Romulan: thinner and cleaner, a falling whistle over a buzz.
    "TREK_RomulanDisruptorPulse": dict(seed=1704, duration=0.30, f0=620, f1=240,
                                       ratio=2.0, thump=110, grit=0.45, buzz=0.45),
    # Jem'Hadar polaron: a rising whine under a heavy knock.
    "TREK_PolaronPulse": dict(seed=1705, duration=0.38, f0=240, f1=520,
                              ratio=1.5, thump=65, grit=0.6, buzz=0.3),
    # Cardassian: short, bright and hard.
    "TREK_CardassianPhaserPulse": dict(seed=1706, duration=0.24, f0=720, f1=300,
                                       ratio=1.33, thump=120, grit=0.6, buzz=0.2),
}


def build_sounds(root):
    sound = os.path.join(root, "media", "sound")
    for name, args in SOUNDS.items():
        samples = shot(**args)
        gp.write_wav(os.path.join(sound, name + ".wav"), samples, peak=27000)
        print(f"  sound   media/sound/{name}.wav ({len(samples) / 44100:.2f} s)")


if __name__ == "__main__":
    root = sys.argv[1]
    build_models(root)
    build_holster(root)
    build_sounds(root)
