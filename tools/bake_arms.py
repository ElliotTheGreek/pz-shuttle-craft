"""Bakes the armoury's image-to-3D sources into the meshes gen_arms.py uses.

Run once per new source, not on every build:

    python tools/bake_arms.py --probe            # side views with a ruler, to set GRIP/PROBE
    python tools/bake_arms.py                    # every weapon
    python tools/bake_arms.py klingon_pistol     # one

It is `tools/bake_phaser.py` generalised to six weapons from four cultures,
and it keeps that bake's rules (PHASERS.md 4; ARMOURY.md 5): turn the raw into
vanilla's frame, fit the grip to vanilla's grip, rebuild the surface from a
filled volume, decimate, unwrap into six planar charts, and **repaint** the
texture per texel. What changes is where the numbers come from:

* **The frame is vanilla's, per kind.** A pistol goes into the M9's frame
  (`weapons/firearm/M9_Pistol`, the mesh behind Handgun03): barrel along +Y,
  top toward -Z, grip hanging toward +Z, so Handgun03's hand and ground
  attachments fit it, as they fit the phaser. A rifle goes into the M16's
  (`M16_Rifle`, behind AssaultRifle): barrel along +Y, top toward **+Z**, the
  grip hanging toward -Z, and **no hand attachment at all** -- the engine puts
  the mesh's origin in the fist, so the origin must be on the pistol grip.
  Measured off the meshes on 2026-09-27: the M16's grip is centred fore and
  aft at y = -0.007, and it leaves the receiver at z = -0.012.
* **The turn is read off a picture, never guessed.** TRELLIS returns each
  model in its own orientation (the Klingon pistol came back lying on its
  side), so each entry names which glTF axis its muzzle and its top point
  along, set from `--probe`'s axis views.
* **The grip is found near a hint.** Where a rifle has a stock, a pistol grip
  and a forward grip all hanging down, "the thing that hangs down" is three
  things. `grip` is where the pistol grip is, as a fraction of the length from
  the heel, read off `--probe`'s ruler; `probe` is a place where there is only
  body, where its underside is measured.
* **The palette is the concept's own.** The phaser's six colours were picked
  by hand. Here the concept image is clustered (k-means, its white background
  dropped), the source's colours are moved onto the concept's statistics --
  TRELLIS textures come back darker and lit, and the Romulan's came back grey
  -- and every texel is snapped to the nearest concept colour, then the mode
  filter takes the speckle out.
* **The emitter is found by its glow**, in the front of the weapon, in the
  source's own texture -- a Klingon disruptor's emitter sits between two
  prongs, not on the muzzle face, so the phaser's lens-by-geometry would
  paint the prong tips. Geometry is the fallback.

Outputs, one pair per weapon, which is what is vendored (the raws are 17-20 MB
each and are not; `design/art/weapons/jobs.json` has their URLs):

    tools/assets/trek_arms/<name>_baked.json
    tools/assets/trek_arms/<name>_baked.png
"""
import json
import os
import sys

import numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
ASSETS = os.path.join(HERE, "assets", "trek_arms")
CONCEPTS = os.path.join(REPO, "design", "art", "weapons")

TEX = 512

# Vanilla's grips, from their meshes (see the docstring).
FRAMES = {
    # grip centre y, where the grip leaves the body (z), which way is down
    "pistol": {"grip_y": 0.041, "join_z": -0.014, "down": +1},
    "rifle":  {"grip_y": -0.007, "join_z": -0.012, "down": -1},
}

# forward / up: the glTF axis the muzzle and the top point along, from
# --probe's axis views. length: heel to muzzle in metres (M9 0.151, M16
# 0.546). across: the widest it may be; slimmed to it if the source is wider,
# as the phaser was. grip / probe: fractions of the length from the heel.
# emitter: the colour painted there; glow: the source's own emitter hue in
# degrees, to find it by. faces: the decimation target. k: concept colours.
# tall: the deepest a rifle may be (the M16 is 0.141). lens: the emitter's
# radius when it has to be found by geometry.
WEAPONS = {
    "phaser_rifle": dict(
        kind="rifle", forward=(0, 0, 1), up=(0, 1, 0), length=0.60, across=0.040, tall=0.17, lens=0.016,
        grip=0.24, probe=0.42, emitter=(255, 166, 74), glow=28, faces=4200, k=5),
    "klingon_pistol": dict(
        kind="pistol", forward=(0, 0, -1), up=(1, 0, 0), length=0.185, across=0.030,
        grip=0.13, probe=0.40, emitter=(80, 255, 120), glow=130, faces=3000, k=6),
    "klingon_rifle": dict(
        kind="rifle", forward=(1, 0, 0), up=(0, 1, 0), length=0.62, across=0.045, tall=0.18,
        grip=0.25, probe=0.42, emitter=(80, 255, 120), glow=130, faces=4800, k=6),
    "romulan_pistol": dict(
        kind="pistol", forward=(0, 0, 1), up=(0, 1, 0), length=0.160, across=0.030,
        grip=0.13, probe=0.55, emitter=(90, 255, 140), glow=200, faces=2600, k=4),
    "jemhadar_rifle": dict(
        kind="rifle", forward=(0, 0, 1), up=(0, 1, 0), length=0.58, across=0.045, tall=0.17,
        grip=0.25, probe=0.55, emitter=(200, 235, 255), glow=200, faces=4800, k=5),
    "cardassian_pistol": dict(
        kind="pistol", forward=(0, 0, -1), up=(0, 1, 0), length=0.150, across=0.030,
        grip=0.30, probe=0.70, emitter=(255, 200, 60), glow=45, faces=2600, k=5),
}


# ---------------------------------------------------------------------------
# Turning and fitting
# ---------------------------------------------------------------------------
def rotation(spec):
    """glTF -> the weapon frame: forward to +Y, up to -Z (pistol) or +Z (rifle).

    A proper rotation, determinant +1: the model is turned, never mirrored.
    """
    fwd = np.array(spec["forward"], dtype=float)
    up = np.array(spec["up"], dtype=float)
    e_y = fwd
    e_z = -up if spec["kind"] == "pistol" else up
    e_x = np.cross(e_y, e_z)
    R = np.array([e_x, e_y, e_z])
    assert abs(np.linalg.det(R) - 1.0) < 1e-6, "not a proper rotation"
    return R


def fit(p, spec):
    """Scale to length, slim to `across`, and put the grip on vanilla's grip."""
    frame = FRAMES[spec["kind"]]
    down = frame["down"]
    lo, hi = p.min(0), p.max(0)
    scale = spec["length"] / (hi[1] - lo[1])
    p = p * scale
    width = p[:, 0].max() - p[:, 0].min()
    slim = min(1.0, spec["across"] / width)
    p[:, 0] *= slim
    # And squat to `tall`, for a concept drawn deeper than any rifle the game
    # holds: the phaser rifle came out 0.25 tall at its length, against the
    # M16's 0.14. At the size a rifle is drawn nobody sees the lens go oval.
    height = p[:, 2].max() - p[:, 2].min()
    squat = min(1.0, spec.get("tall", 1.0) / height)
    p[:, 2] *= squat
    if squat < 1.0:
        print(f"  squat   x{squat:.2f} to {height * squat:.3f} tall")
    lo, hi = p.min(0), p.max(0)
    L = hi[1] - lo[1]

    def at(frac, half):
        y = lo[1] + frac * L
        return p[np.abs(p[:, 1] - y) < half * L]

    # The underside of the body where there is only body.
    body = at(spec["probe"], 0.03)
    z_join = body[:, 2].max() if down > 0 else body[:, 2].min()
    # The grip: what hangs below that, near the hint.
    near = at(spec["grip"], 0.08)
    below = near[(near[:, 2] - z_join) * down > 0.25 * abs(hi[2] - lo[2]) * 0.2]
    if len(below) < 20:
        raise SystemExit(f"  no grip below the body near {spec['grip']} -- "
                         f"look at the probe sheet and move `grip`")
    deep = below[(below[:, 2] - z_join) * down > 0.4 *
                 ((below[:, 2] - z_join) * down).max()]
    y_mid = (deep[:, 1].min() + deep[:, 1].max()) / 2
    # Where the grip meets the body: walk up from the grip's foot, and the
    # first slice that is suddenly much longer fore and aft than the grip is
    # thick is the body. The probe's underside is only a first guess -- on
    # the Klingon pistol it landed on the trigger guard and hung the whole
    # weapon above the hand.
    foot = below[:, 2].max() if down > 0 else below[:, 2].min()
    H = hi[2] - lo[2]
    wide = p[np.abs(p[:, 1] - y_mid) < 0.25 * L]
    step = 0.02 * H
    extents, z = [], foot
    for _ in range(60):
        z -= down * step
        band = wide[np.abs(wide[:, 2] - z) < step]
        ext = band[:, 1].max() - band[:, 1].min() if len(band) > 3 else 0.0
        if len(extents) >= 3 and ext > 1.8 * np.median(extents[:3]) + 0.02 * L:
            z_join = z + down * step
            break
        extents.append(ext)
    shift = np.array([-(p[:, 0].min() + p[:, 0].max()) / 2,
                      frame["grip_y"] - y_mid,
                      frame["join_z"] - z_join])
    print(f"  fit     scale {scale:.4f}, slimmed x{slim:.2f} to "
          f"{width * slim:.3f} across; grip centre {(y_mid - lo[1]) / L:.2f} "
          f"of the length, body underside there {z_join:.4f}")
    return p + shift, scale, slim


# ---------------------------------------------------------------------------
# The surface
# ---------------------------------------------------------------------------
def remesh(pts, faces, pitch):
    """One closed outer skin via a filled volume (bake_phaser.py, remesh)."""
    import trimesh
    from scipy import ndimage
    from skimage import measure
    surface = trimesh.Trimesh(vertices=pts, faces=faces, process=False)
    samples, _ = trimesh.sample.sample_surface(surface, 4_000_000, seed=1701)
    lo = pts.min(0) - 4 * pitch
    shape = np.ceil((pts.max(0) + 4 * pitch - lo) / pitch).astype(int) + 1
    grid = np.zeros(shape, dtype=bool)
    ijk = np.floor((samples - lo) / pitch).astype(int)
    grid[ijk[:, 0], ijk[:, 1], ijk[:, 2]] = True
    grid = ndimage.binary_closing(grid, iterations=2)
    grid = ndimage.binary_fill_holes(grid)
    labels, count = ndimage.label(grid)
    if count > 1:
        sizes = ndimage.sum(grid, labels, range(1, count + 1))
        grid = labels == (int(np.argmax(sizes)) + 1)
    field = ndimage.gaussian_filter(grid.astype(float), sigma=0.9)
    verts, tris, _, _ = measure.marching_cubes(field, level=0.5)
    mesh = trimesh.Trimesh(vertices=verts * pitch + lo, faces=tris, process=True)
    if mesh.volume < 0:
        mesh.invert()
    return mesh


CHARTS = [
    ("left",   0, -1, (1, False), (2, False)),
    ("right",  0, +1, (1, True),  (2, False)),
    ("top",    2, -1, (1, False), (0, False)),
    ("bottom", 2, +1, (1, False), (0, True)),
    ("front",  1, +1, (0, False), (2, False)),
    ("back",   1, -1, (0, True),  (2, False)),
]


def unwrap(v, f, normals):
    """Six planar charts by facing, scaled to fill TEX (bake_phaser.py)."""
    chart_of = np.zeros(len(f), dtype=int)
    for fi, n in enumerate(normals):
        axis = int(np.argmax(np.abs(n)))
        sign = 1 if n[axis] > 0 else -1
        chart_of[fi] = next(i for i, c in enumerate(CHARTS)
                            if c[1] == axis and c[2] == sign)
    lo, hi = v.min(0), v.max(0)
    ext = hi - lo
    x_len, x_h = ext[1], ext[2]
    z_len, z_w = ext[1], ext[0]
    y_w, y_h = ext[0], ext[2]
    # In metres, with a gutter that becomes 6 texels once scaled.
    need_w = 2 * x_len
    need_h = x_h + max(z_w, y_h)
    tpm = (TEX - 30) / max(need_w, need_h + (2 * y_w + 2 * z_len - 2 * x_len
                                              if 2 * z_len + 2 * y_w > need_w else 0))
    # Top/bottom and the ends share the second row; make sure it fits across.
    row2 = 2 * z_len + 2 * y_w
    tpm = min(tpm, (TEX - 30) / max(need_w, row2), (TEX - 30) / need_h)
    gap = 6.0 / tpm
    origin = {
        "left":   (gap, gap),
        "right":  (2 * gap + x_len, gap),
        "top":    (gap, 2 * gap + x_h),
        "bottom": (2 * gap + z_len, 2 * gap + x_h),
        "front":  (3 * gap + 2 * z_len, 2 * gap + x_h),
        "back":   (4 * gap + 2 * z_len + y_w, 2 * gap + x_h),
    }
    uvs = np.zeros((len(f), 3, 2))
    for fi, face in enumerate(f):
        name, _, _, (ua, uf), (va, vf) = CHARTS[chart_of[fi]]
        ox, oy = origin[name]
        for c, k in enumerate(face):
            p = v[k] - lo
            u = (ext[ua] - p[ua]) if uf else p[ua]
            w = (ext[va] - p[va]) if vf else p[va]
            uvs[fi, c] = ((ox + u) * tpm, (oy + w) * tpm)
    if uvs.max() > TEX:
        raise SystemExit(f"charts overflow the texture: {uvs.max():.0f} > {TEX}")
    print(f"  unwrap  {tpm:.0f} texels per metre")
    return uvs, chart_of


def rasterise(v, f, uvs):
    face_at = np.full((TEX, TEX), -1, dtype=int)
    point_at = np.zeros((TEX, TEX, 3))
    for fi, face in enumerate(f):
        (x0, y0), (x1, y1), (x2, y2) = uvs[fi]
        minx, maxx = int(max(0, np.floor(min(x0, x1, x2)))), int(min(TEX - 1, np.ceil(max(x0, x1, x2))))
        miny, maxy = int(max(0, np.floor(min(y0, y1, y2)))), int(min(TEX - 1, np.ceil(max(y0, y1, y2))))
        det = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
        if abs(det) < 1e-12 or minx > maxx or miny > maxy:
            continue
        gx, gy = np.meshgrid(np.arange(minx, maxx + 1) + 0.5,
                             np.arange(miny, maxy + 1) + 0.5)
        l0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / det
        l1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / det
        l2 = 1.0 - l0 - l1
        inside = (l0 >= -0.02) & (l1 >= -0.02) & (l2 >= -0.02)
        p = (l0[..., None] * v[face[0]] + l1[..., None] * v[face[1]]
             + l2[..., None] * v[face[2]])
        fa = face_at[miny:maxy + 1, minx:maxx + 1]
        pa = point_at[miny:maxy + 1, minx:maxx + 1]
        fa[inside] = fi
        pa[inside] = p[inside]
    return face_at, point_at


# ---------------------------------------------------------------------------
# Colour
# ---------------------------------------------------------------------------
def hue_sat(rgb):
    """Hue in degrees and HSV saturation/value, for an (n, 3) array 0..255."""
    c = rgb / 255.0
    mx, mn = c.max(1), c.min(1)
    d = mx - mn + 1e-9
    r, g, b = c[:, 0], c[:, 1], c[:, 2]
    h = np.where(mx == r, (g - b) / d % 6, np.where(mx == g, (b - r) / d + 2,
                                                       (r - g) / d + 4)) * 60
    return h, d / (mx + 1e-9), mx


def hue_near(h, target, width=28):
    return np.abs((h - target + 180) % 360 - 180) < width


def kmeans(x, k, seed=1701, iters=30):
    rng = np.random.default_rng(seed)
    cent = x[rng.choice(len(x), k, replace=False)]
    for _ in range(iters):
        lab = ((x[:, None, :] - cent[None]) ** 2).sum(2).argmin(1)
        for i in range(k):
            if (lab == i).any():
                cent[i] = x[lab == i].mean(0)
    return cent, lab


def concept_palette(name, spec):
    """The concept's own colours: its object pixels, clustered."""
    from PIL import Image
    img = np.asarray(Image.open(os.path.join(CONCEPTS, name, "concept_34_raw.jpg"))
                     .convert("RGB").resize((256, 256))).reshape(-1, 3).astype(float)
    white = (img > 225).all(1) | (np.abs(img - img.mean(1, keepdims=True)).max(1) < 6) & (img.mean(1) > 200)
    obj = img[~white]
    h, s, v = hue_sat(obj)
    glow = hue_near(h, spec["glow"], 35) & (s > 0.45) & (v > 0.55)
    body = obj[~glow]
    cent, lab = kmeans(body, spec["k"])
    order = np.argsort(-np.bincount(lab, minlength=spec["k"]))
    cent = cent[order]
    return body, cent


def mode_filter(labels, mask, n, passes=2):
    for _ in range(passes):
        counts = np.zeros((n,) + labels.shape)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                shifted = np.roll(np.roll(labels, dy, 0), dx, 1)
                smask = np.roll(np.roll(mask, dy, 0), dx, 1)
                for i in range(n):
                    counts[i] += (shifted == i) & smask
        counts[labels, np.arange(labels.shape[0])[:, None],
               np.arange(labels.shape[1])[None, :]] += 0.5
        labels = np.where(mask, counts.argmax(0), labels)
    return labels


def bake(name, spec, v, f, normals, uvs, source, pts_src, faces_src):
    from scipy.spatial import cKDTree
    face_at, point_at = rasterise(v, f, uvs)
    mask = face_at >= 0
    ys, xs = np.nonzero(mask)
    points = point_at[ys, xs]
    fnorm = normals[face_at[ys, xs]]

    material = source.visual.material
    image = getattr(material, "baseColorTexture", None) or material.image
    img = np.asarray(image.convert("RGB")).astype(float)
    h, w = img.shape[:2]
    uv = np.asarray(source.visual.uv)[faces_src].mean(1)
    src_col = img[np.clip(((1.0 - uv[:, 1] % 1.0) * h).astype(int), 0, h - 1),
                  np.clip(((uv[:, 0] % 1.0) * w).astype(int), 0, w - 1)]
    src_n = np.asarray(source.face_normals) @ rotation(spec).T
    tree = cKDTree(pts_src[faces_src].mean(1))
    _, near = tree.query(points, k=16)
    agree = np.einsum("nkj,nj->nk", src_n[near], fnorm) > 0.3
    pick = np.where(agree.any(1), near[np.arange(len(near)), agree.argmax(1)],
                    near[:, 0])
    col = src_col[pick]

    # The emitter, by its glow, in the front third.
    ymin, ymax = v[:, 1].min(), v[:, 1].max()
    front = points[:, 1] > ymax - 0.35 * (ymax - ymin)
    hh, ss, vv = hue_sat(col)
    lit = front & hue_near(hh, spec["glow"]) & (ss > 0.35) & (vv > 0.35)
    if lit.sum() < 12:
        # Fallback: the phaser's lens by geometry, on the muzzle face.
        nose = v[f].mean(1)[:, 1] > ymax - 0.02
        axis_z = float(np.median(v[f].mean(1)[nose, 2]))
        radial = np.hypot(points[:, 0], points[:, 2] - axis_z)
        lit = (points[:, 1] > ymax - 0.02) & (fnorm[:, 1] > 0.35) & (radial < spec.get("lens", 0.0105))
        print("  emitter by geometry (no glow found in the source)")

    # Everything else: moved onto the concept's statistics, snapped to its
    # colours.
    concept_px, palette = concept_palette(name, spec)
    body = col[~lit]
    mu_s, sd_s = body.mean(0), body.std(0) + 1e-6
    mu_c, sd_c = concept_px.mean(0), concept_px.std(0) + 1e-6
    moved = np.clip((col - mu_s) / sd_s * sd_c + mu_c, 0, 255)
    # Blurred over the texture before it is snapped, so the regions come out
    # as panels and not as the source's speckle: TRELLIS's textures are noisy
    # at the texel, and snapping texel by texel painted the Klingon rifle in
    # camouflage. The blur stays inside the charts (a normalised convolution).
    from scipy import ndimage
    field = np.zeros((TEX, TEX, 3))
    field[ys, xs] = moved
    weight = ndimage.gaussian_filter(mask.astype(float), 2.2)
    for ch in range(3):
        field[..., ch] = ndimage.gaussian_filter(field[..., ch], 2.2) / (weight + 1e-6)
    moved = field[ys, xs]
    lab = ((moved[:, None, :] - palette[None]) ** 2).sum(2).argmin(1)
    n = len(palette)
    labels = np.zeros((TEX, TEX), dtype=int)
    labels[ys, xs] = lab
    labels = mode_filter(labels, mask, n, passes=3)
    EMIT = n
    labels[ys[lit], xs[lit]] = EMIT
    colours = np.vstack([palette, np.array(spec["emitter"], dtype=float)]).astype(np.uint8)
    rgb = np.zeros((TEX, TEX, 3), dtype=np.uint8)
    rgb[mask] = colours[labels[mask]]
    filled = mask.copy()
    for _ in range(8):
        grow = np.zeros_like(filled)
        acc = np.zeros((TEX, TEX, 3), dtype=float)
        cnt = np.zeros((TEX, TEX))
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            src = np.roll(np.roll(filled, dy, 0), dx, 1)
            c = np.roll(np.roll(rgb, dy, 0), dx, 1)
            take = src & ~filled
            acc[take] += c[take]
            cnt[take] += 1
            grow |= take
        rgb[grow] = (acc[grow] / cnt[grow, None]).astype(np.uint8)
        filled |= grow
    share = np.bincount(labels[mask], minlength=n + 1) / mask.sum()
    print("  paint   " + ", ".join(f"#{c[0]:02x}{c[1]:02x}{c[2]:02x} {s:.0%}"
                                   for c, s in zip(colours, share)))
    muzzle = points[lit].mean(0) if lit.any() else np.array([0.0, ymax, 0.0])
    return rgb, muzzle, [list(map(int, c)) for c in colours]


# ---------------------------------------------------------------------------
def probe(names):
    """Each raw turned into its frame, from the side, with a ruler."""
    import trimesh
    from PIL import Image, ImageDraw
    W, H = 900, 260
    sheet = Image.new("RGB", (W, H * len(names)), (40, 40, 48))
    d = ImageDraw.Draw(sheet)
    for r, name in enumerate(names):
        spec = WEAPONS[name]
        m = trimesh.load(os.path.join(ASSETS, name + "_raw.glb"), force="mesh")
        p = np.asarray(m.vertices) @ rotation(spec).T
        mat = m.visual.material
        im = (getattr(mat, "baseColorTexture", None) or mat.image).convert("RGB")
        a = np.asarray(im)
        uvv = np.asarray(m.visual.uv)
        c = a[np.clip(((1 - uvv[:, 1] % 1) * a.shape[0]).astype(int), 0, a.shape[0] - 1),
              np.clip(((uvv[:, 0] % 1) * a.shape[1]).astype(int), 0, a.shape[1] - 1)]
        lo, hi = p.min(0), p.max(0)
        L = hi[1] - lo[1]
        k = (W - 60) / L
        down = FRAMES[spec["kind"]]["down"]
        # Side view, muzzle to the right, top up; nearest (-x) drawn last.
        order = np.argsort(-p[:, 0])
        px = (30 + (p[order, 1] - lo[1]) * k).astype(int)
        zc = (lo[2] + hi[2]) / 2
        py = (H / 2 + (p[order, 2] - zc) * k * down).astype(int)
        ok = (py >= 0) & (py < H)
        buf = np.zeros((H, W, 3), np.uint8) + 40
        buf[py[ok], px[ok]] = c[order][ok]
        sheet.paste(Image.fromarray(buf), (0, r * H))
        for t in range(11):
            x = 30 + t * (W - 60) / 10
            d.line([(x, r * H + H - 18), (x, r * H + H - 8)], fill=(255, 255, 0))
            d.text((x - 8, r * H + H - 30), f"{t / 10:.1f}", fill=(255, 255, 0))
        for key, col in (("grip", (0, 255, 255)), ("probe", (255, 80, 80))):
            x = 30 + spec[key] * (W - 60)
            d.line([(x, r * H + 14), (x, r * H + H - 34)], fill=col)
        d.text((6, r * H + 4), f"{name}: heel left, muzzle right, top up; "
               f"cyan = grip, red = probe", fill=(255, 255, 255))
    out = os.path.join(CONCEPTS, "arms_probe.png")
    sheet.save(out)
    print("wrote", os.path.relpath(out, REPO))


def main_one(name):
    import trimesh
    from PIL import Image
    spec = WEAPONS[name]
    print(name)
    source = trimesh.load(os.path.join(ASSETS, name + "_raw.glb"), force="mesh")
    faces = np.asarray(source.faces)
    R = rotation(spec)
    pts = np.asarray(source.vertices, dtype=float) @ R.T
    pts, scale, slim = fit(pts, spec)
    pitch = spec["length"] / (320 if spec["kind"] == "rifle" else 215)
    geo = remesh(pts, faces, pitch)
    low = geo.simplify_quadric_decimation(face_count=spec["faces"])
    low.remove_unreferenced_vertices()
    trimesh.repair.fix_normals(low, multibody=False)
    v = np.asarray(low.vertices)
    f = np.asarray(low.faces)
    normals = np.asarray(low.face_normals)
    print(f"  mesh    {len(f)} faces, {len(v)} verts, watertight {low.is_watertight}")
    # The remesh is closed by construction; the decimator can open a seam on
    # a thin part (the Klingon pistol's prongs). The engine does not need a
    # closed mesh -- it needs faces turned outward, which a hole does not
    # change and the sheet shows. Inside out is still refused.
    if not low.is_watertight:
        print("  WARNING the decimated surface is not closed -- look at the sheet")
    if geo.volume <= 0:
        raise SystemExit("  the rebuilt surface is inside out")
    uvs, _ = unwrap(v, f, normals)
    rgb, muzzle, colours = bake(name, spec, v, f, normals, uvs, source, pts, faces)
    tex = os.path.join(ASSETS, name + "_baked.png")
    Image.fromarray(rgb, "RGB").save(tex, optimize=True)
    lo, hi = v.min(0), v.max(0)
    print(f"  bbox    x {lo[0]:.3f}..{hi[0]:.3f}  y {lo[1]:.3f}..{hi[1]:.3f}  "
          f"z {lo[2]:.3f}..{hi[2]:.3f}")
    print(f"  muzzle  {muzzle.round(4).tolist()}")
    out = os.path.join(ASSETS, name + "_baked.json")
    json.dump({
        "source": name + "_raw.glb", "texture": os.path.basename(tex),
        "kind": spec["kind"], "tex_size": TEX, "palette": colours,
        "muzzle": [round(float(c), 4) for c in muzzle],
        "verts": [[round(float(c), 5) for c in p] for p in v],
        "faces": f.tolist(),
        "uvs": [[[round(float(a) / TEX, 5), round(float(b) / TEX, 5)]
                 for a, b in tri] for tri in uvs],
    }, open(out, "w"), separators=(",", ":"))
    print(f"  wrote   {os.path.relpath(out, REPO)} ({os.path.getsize(out) // 1024} KB)")


def main():
    args = sys.argv[1:]
    if args and args[0] == "--probe":
        probe(args[1:] or list(WEAPONS))
        return
    for name in args or list(WEAPONS):
        main_one(name)


if __name__ == "__main__":
    main()
