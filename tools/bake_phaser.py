"""Bakes the phaser's image-to-3D source into the mesh and texture gen_phaser.py uses.

Run once per new source, not on every build:

    python tools/bake_phaser.py

It is the only step that reads the 18 MB raw GLB, and the only one that needs
`trimesh`, `fast_simplification`, `networkx`, `scipy` and `scikit-image`
(all pip). Its two outputs are small and are what is vendored:

    tools/assets/trek_phaser/phaser_baked.json   the mesh, with UVs
    tools/assets/trek_phaser/phaser_baked.png    its texture

so a normal build needs neither the network nor any of those packages -- the
rule the Doctor's pipeline set (EMH.md, *Replacing the Doctor source*).

The steps, and the fault each one exists for (PHASERS.md 4, *How the model
was made*, has the story with the review sheets):

1. **Orient into vanilla's pistol frame.** TRELLIS writes glTF, Y-up, muzzle
   toward +Z. A PZ firearm mesh runs its barrel along +Y with the top toward
   -Z and the grip toward +Z -- vanilla's M9 (`weapons/firearm/M9_Pistol`,
   the mesh behind `Handgun03`) does. In that frame vanilla's own
   `Bip01_Prop2` and `world` offsets fit the phaser as they fit the M9, where
   otherwise a hand offset can only be found by trial in game.
2. **Fit the grip to the M9's grip**, not the length to a guess: the hand
   closes on the grip. And slim it across (`ACROSS`), because true to the
   concept it is twice as wide as any pistol the game ships.
3. **Rebuild the surface from volume.** The source is a hollow shell -- an
   outer skin and a dark inner one a millimetre inside it -- plus a thousand
   loose scraps. Decimated as it stood, the inner skin poked through and the
   phaser came out covered in black triangles.
4. **Decimate** to ~2.6k triangles (vanilla's M9 is 323 vertices), and
   re-orient every face outward: the decimator flips some.
5. **Unwrap by facing** into six planar charts. The phaser is a profile, so
   the two side charts hold nearly everything anybody sees, as two large
   contiguous regions -- which keeps colours coherent in the small mip
   levels the game draws a held weapon from. (xatlas would be the general
   answer; it has no build for this Python.)
6. **Bake the texture per texel**, snapped to the concept's palette. The
   source's texture is darker than the concept and carries baked lighting,
   and TRELLIS invented a dark emitter and an orange patch on the back; so
   texels are *classified* by the source's brightness and *painted* in the
   concept's colours, the emitter is found by geometry, black is allowed
   only on the grip, and a mode filter takes the speckle out.
"""
import json, os

import numpy as np
import trimesh

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "assets", "trek_phaser", "trellis2_raw.glb")
OUT = os.path.join(HERE, "assets", "trek_phaser", "phaser_baked.json")
OUT_TEX = os.path.join(HERE, "assets", "trek_phaser", "phaser_baked.png")

FACES = 2600          # target triangle count after decimation
LENGTH = 0.150        # muzzle to heel; the M9 is 0.151
# Across, as a fraction of the source's own proportion. True to the concept
# it came out 0.041 across, twice the M9 and wider than any pistol build 42
# ships (the widest, Handgun_RedDot, is 0.031). A fist closes round it, so it
# is slimmed into vanilla's bracket. At 20 px nobody sees the lens go oval.
ACROSS = 0.75
PITCH = 0.0007        # remesh voxel: ~215 across the length
TEX = 512             # texture side
TEXELS_PER_M = 1380   # chart scale: the layout below fills 512 across

# Where the M9's grip is, from its own mesh (M9_Pistol.x, measured
# 2026-09-24): the slide's underside sits at z = -0.014, and half way down
# the grip its fore-and-aft centre is y = 0.041.
M9_SLIDE_BOTTOM_Z = -0.014
M9_GRIP_CENTRE_Y = 0.041

# name, rgb: the colours the texture is PAINTED in, from the concept image.
PALETTE = [
    ("shell",   (222, 220, 212)),   # off-white composite panels
    ("hull",    (130, 122, 112)),   # warm grey upper body and grip frame
    ("grip",    (36, 36, 39)),      # satin black grip
    ("seam",    (58, 58, 62)),      # the flank seam, the control, the ring
    ("emitter", (255, 166, 74)),    # the lens: only ever set by geometry
    ("led",     (90, 180, 255)),    # the indicator lights
]
IDX = {name: i for i, (name, _) in enumerate(PALETTE)}

# Luminance bands over the SOURCE texture, from its area-weighted colour
# clusters (2026-09-24): grip ~30, a transition shade ~67, the grey body ~91,
# the panels 161-188.
DARK, LIGHT = 48.0, 128.0

# glTF (x, y up, z muzzle) -> PZ weapon (x, y muzzle, z down). A proper
# rotation (determinant +1): the model is turned, not mirrored.
ROT = np.array([[1, 0, 0], [0, 0, 1], [0, -1, 0]], dtype=float)


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------
def fit(points):
    """Scale and shift that put the phaser's grip where the M9's is."""
    lo, hi = points.min(0), points.max(0)
    # The grip hangs furthest down (+z). It must be at the rear, or the
    # muzzle is the wrong way round.
    low = points[points[:, 2] > hi[2] - 0.1 * (hi[2] - lo[2])]
    if low[:, 1].mean() > (lo[1] + hi[1]) / 2:
        raise SystemExit("the grip is forward of centre: the source's muzzle "
                         "is not at +Z -- turn it before baking")
    scale = LENGTH / (hi[1] - lo[1])
    p = points * scale * np.array([ACROSS, 1.0, 1.0])
    lo, hi = p.min(0), p.max(0)
    height = hi[2] - lo[2]
    # The body's underside at the grip. Scan down from a tenth of the way
    # below the top; the first band that no longer reaches the front third of
    # the length is below the body and in the grip.
    front = hi[1] - 0.33 * (hi[1] - lo[1])
    z_join = None
    for k in range(10, 100):
        z = lo[2] + height * k / 100.0
        band = p[np.abs(p[:, 2] - z) < height * 0.015]
        if len(band) and band[:, 1].max() < front:
            z_join = z
            break
    if z_join is None:
        raise SystemExit("never found where the grip leaves the body")
    # Half way down the grip: its fore-and-aft centre.
    z_mid = (z_join + hi[2]) / 2
    band = p[np.abs(p[:, 2] - z_mid) < height * 0.03]
    y_mid = (band[:, 1].min() + band[:, 1].max()) / 2
    shift = np.array([-(lo[0] + hi[0]) / 2,
                      M9_GRIP_CENTRE_Y - y_mid,
                      M9_SLIDE_BOTTOM_Z - z_join])
    print(f"  fit     scale {scale:.4f} (x {ACROSS} across); body "
          f"{z_join - lo[2]:.4f} deep, grip {hi[2] - z_join:.4f} long")
    return np.array([scale * ACROSS, scale, scale]), shift


def remesh(pts, faces):
    """One closed outer skin from the source's surface, via a filled volume.

    Two cheaper fixes were tried first and both failed on the review sheet:
    dropping the loose scraps (the inner skin joins the outer at the
    openings, so it is not a separate body), and re-orienting the decimated
    faces (a hollow shell has two honest "outsides"). Filling the volume
    makes one surface by construction.
    """
    from scipy import ndimage
    from skimage import measure
    surface = trimesh.Trimesh(vertices=pts, faces=faces, process=False)
    samples, _ = trimesh.sample.sample_surface(surface, 3_000_000, seed=1701)
    lo = pts.min(0) - 4 * PITCH
    shape = np.ceil((pts.max(0) + 4 * PITCH - lo) / PITCH).astype(int) + 1
    grid = np.zeros(shape, dtype=bool)
    ijk = np.floor((samples - lo) / PITCH).astype(int)
    grid[ijk[:, 0], ijk[:, 1], ijk[:, 2]] = True
    # Close the gap between the two skins and any pinholes, then fill.
    grid = ndimage.binary_closing(grid, iterations=2)
    grid = ndimage.binary_fill_holes(grid)
    labels, count = ndimage.label(grid)
    if count > 1:
        sizes = ndimage.sum(grid, labels, range(1, count + 1))
        grid = labels == (int(np.argmax(sizes)) + 1)
    field = ndimage.gaussian_filter(grid.astype(float), sigma=0.9)
    verts, tris, _, _ = measure.marching_cubes(field, level=0.5)
    mesh = trimesh.Trimesh(vertices=verts * PITCH + lo, faces=tris,
                           process=True)
    if mesh.volume < 0:          # checked, not assumed
        mesh.invert()
    return mesh


# ---------------------------------------------------------------------------
# Unwrapping: six planar charts, by which way a face looks
# ---------------------------------------------------------------------------
# chart: (name, axis, sign, u = (axis, flip), v = (axis, flip))
# Every chart is drawn as seen from outside, upright (top of the phaser at
# the top of the chart), so a texture read by a person reads the right way.
CHARTS = [
    ("left",   0, -1, (1, False), (2, False)),   # seen from -X: muzzle left
    ("right",  0, +1, (1, True),  (2, False)),   # seen from +X: muzzle right
    ("top",    2, -1, (1, False), (0, False)),
    ("bottom", 2, +1, (1, False), (0, True)),
    ("front",  1, +1, (0, False), (2, False)),
    ("back",   1, -1, (0, True),  (2, False)),
]


def unwrap(v, f, normals):
    """Per-corner UVs (in texels) and which chart each face went to."""
    chart_of = np.zeros(len(f), dtype=int)
    for fi, n in enumerate(normals):
        axis = int(np.argmax(np.abs(n)))
        sign = 1 if n[axis] > 0 else -1
        chart_of[fi] = next(i for i, c in enumerate(CHARTS)
                            if c[1] == axis and c[2] == sign)
    # Layout, in metres before scaling: the two sides across the top, the
    # top and bottom strips under them, the ends to the right of those.
    lo, hi = v.min(0), v.max(0)
    ext = hi - lo
    gap = 6.0 / TEXELS_PER_M
    x_len, x_h = ext[1], ext[2]        # a side: length by height
    z_len, z_w = ext[1], ext[0]        # top/bottom: length by width
    y_w, y_h = ext[0], ext[2]          # an end: width by height
    origin = {
        "left":   (gap, gap),
        "right":  (2 * gap + x_len, gap),
        "top":    (gap, 2 * gap + x_h),
        "bottom": (2 * gap + z_len, 2 * gap + x_h),
        "front":  (3 * gap + 2 * z_len, 2 * gap + x_h),
        "back":   (4 * gap + 2 * z_len + y_w, 2 * gap + x_h),
    }
    need_w = 3 * gap + 2 * x_len
    need_h = 3 * gap + x_h + max(z_w, y_h)
    if max(need_w, need_h) * TEXELS_PER_M > TEX:
        raise SystemExit(f"charts need {need_w * TEXELS_PER_M:.0f} x "
                         f"{need_h * TEXELS_PER_M:.0f} texels; TEX is {TEX}")
    uvs = np.zeros((len(f), 3, 2))
    for fi, face in enumerate(f):
        name, _, _, (ua, uf), (va, vf) = CHARTS[chart_of[fi]]
        ox, oy = origin[name]
        for c, k in enumerate(face):
            p = v[k] - lo
            u = (ext[ua] - p[ua]) if uf else p[ua]
            w = (ext[va] - p[va]) if vf else p[va]
            uvs[fi, c] = ((ox + u) * TEXELS_PER_M, (oy + w) * TEXELS_PER_M)
    return uvs, chart_of


# ---------------------------------------------------------------------------
# Baking the texture
# ---------------------------------------------------------------------------
def rasterise(v, f, uvs):
    """For every covered texel: the 3D point under it and its face."""
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


def classify(src_col, points, in_grip):
    """Palette index for each sampled source colour."""
    lum = src_col.mean(1)
    out = np.full(len(src_col), IDX["hull"])
    out[lum >= LIGHT] = IDX["shell"]
    dark = lum < DARK
    out[dark & in_grip] = IDX["grip"]
    # Dark on the body is the flank seam or the control on top, and is drawn
    # as the seam's grey. Painted grip-black it read as damage.
    out[dark & ~in_grip] = IDX["seam"]
    blue = (src_col[:, 2] > src_col[:, 0] + 40) & (src_col[:, 2] > 110)
    out[blue] = IDX["led"]
    return out


def mode_filter(labels, mask, passes=2):
    """3x3 majority over covered texels: speckle out, edges straightened."""
    for _ in range(passes):
        counts = np.zeros((len(PALETTE),) + labels.shape)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                shifted = np.roll(np.roll(labels, dy, 0), dx, 1)
                smask = np.roll(np.roll(mask, dy, 0), dx, 1)
                for i in range(len(PALETTE)):
                    counts[i] += (shifted == i) & smask
        counts[labels, np.arange(labels.shape[0])[:, None],
               np.arange(labels.shape[1])[None, :]] += 0.5   # ties: keep
        best = counts.argmax(0)
        labels = np.where(mask, best, labels)
    return labels


def bake(v, f, normals, uvs, source, pts_src, faces_src):
    from scipy.spatial import cKDTree
    face_at, point_at = rasterise(v, f, uvs)
    mask = face_at >= 0
    ys, xs = np.nonzero(mask)
    points = point_at[ys, xs]
    fnorm = normals[face_at[ys, xs]]
    print(f"  bake    {len(points)} texels covered of {TEX * TEX}")

    # The source's colour per face, and a tree over its face centres.
    material = source.visual.material
    image = getattr(material, "baseColorTexture", None) or material.image
    img = np.asarray(image.convert("RGB")).astype(float)
    h, w = img.shape[:2]
    uv = np.asarray(source.visual.uv)[faces_src].mean(1)
    src_col = img[np.clip(((1.0 - uv[:, 1] % 1.0) * h).astype(int), 0, h - 1),
                  np.clip(((uv[:, 0] % 1.0) * w).astype(int), 0, w - 1)]
    src_n = np.asarray(source.face_normals) @ ROT.T
    tree = cKDTree(pts_src[faces_src].mean(1))
    _, near = tree.query(points, k=16)
    # Only a source face turned the same way counts: the inner skin a
    # millimetre inside is turned the other way, and is dark.
    agree = np.einsum("nkj,nj->nk", src_n[near], fnorm) > 0.3
    pick = np.where(agree.any(1), near[np.arange(len(near)), agree.argmax(1)],
                    near[:, 0])
    in_grip = points[:, 2] > M9_SLIDE_BOTTOM_Z + 0.002
    labels = np.full((TEX, TEX), IDX["hull"])
    labels[ys, xs] = classify(src_col[pick], points, in_grip)
    labels = mode_filter(labels, mask)
    # The mode filter is right for speckle and wrong for a line one or two
    # texels thick: it broke the flank seam into dashes (sheet, 2026-09-24).
    # The seam runs along the length, which is u on every chart that shows
    # it, so it is closed along u only -- a gap in a line is bridged and
    # nothing is thickened across it.
    from scipy import ndimage
    seam = ndimage.binary_closing(labels == IDX["seam"],
                                  structure=np.ones((1, 7), dtype=bool))
    labels[seam & mask & (labels != IDX["grip"])] = IDX["seam"]

    # The emitter, by geometry, after the filter so it is never eroded: the
    # round lens on the muzzle face, on the body's own centre line there.
    ymax = v[:, 1].max()
    nose_faces = v[f].mean(1)[:, 1] > ymax - 0.02
    axis_z = float(np.median(v[f].mean(1)[nose_faces, 2]))
    radial = np.hypot(points[:, 0], points[:, 2] - axis_z)
    front = (points[:, 1] > ymax - 0.02) & (fnorm[:, 1] > 0.35)
    lens = front & (radial < 0.0105)
    ring = front & (radial >= 0.0105) & (radial < 0.0135)
    labels[ys[ring], xs[ring]] = IDX["seam"]
    labels[ys[lens], xs[lens]] = IDX["emitter"]

    # Paint, then bleed every chart into its gutter so a mip level or a
    # filtered edge never reaches the black between charts.
    colours = np.array([rgb for _, rgb in PALETTE], dtype=np.uint8)
    rgb = np.zeros((TEX, TEX, 3), dtype=np.uint8)
    rgb[mask] = colours[labels[mask]]
    filled = mask.copy()
    for _ in range(8):
        grow = np.zeros_like(filled)
        acc = np.zeros((TEX, TEX, 3), dtype=float)
        cnt = np.zeros((TEX, TEX))
        for dy, dx in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            src = np.roll(np.roll(filled, dy, 0), dx, 1)
            col = np.roll(np.roll(rgb, dy, 0), dx, 1)
            take = src & ~filled
            acc[take] += col[take]
            cnt[take] += 1
            grow |= take
        rgb[grow] = (acc[grow] / cnt[grow, None]).astype(np.uint8)
        filled |= grow
    counts = {n: int((labels[mask] == i).sum()) for i, (n, _) in enumerate(PALETTE)}
    print("  paint  ", counts)
    if counts["emitter"] < 20:
        raise SystemExit("found no emitter on the muzzle face -- the lens "
                         "radius or the orientation is wrong")
    return rgb, (0.0, float(ymax), axis_z)


def main():
    from PIL import Image
    source = trimesh.load(SRC, force="mesh")
    print(f"source  {len(source.faces)} faces, {len(source.vertices)} verts")
    faces = np.asarray(source.faces)
    pts = np.asarray(source.vertices, dtype=float) @ ROT.T
    scale, shift = fit(pts)
    pts = pts * scale + shift

    geo = remesh(pts, faces)
    print(f"  remesh  {len(geo.faces)} faces off the solid")
    low = geo.simplify_quadric_decimation(face_count=FACES)
    low.remove_unreferenced_vertices()
    # The decimator does not keep every face's winding. The engine culls a
    # face turned away, so a flipped one is a hole in game.
    trimesh.repair.fix_normals(low, multibody=False)
    v = np.asarray(low.vertices)
    f = np.asarray(low.faces)
    normals = np.asarray(low.face_normals)
    top = v[f].mean(1)[:, 2] < v[:, 2].min() + 0.004
    up = normals[top][:, 2].mean()
    print(f"decimated to {len(f)} faces, {len(v)} verts, watertight "
          f"{low.is_watertight}; the top faces z {up:+.2f} (outward is -1)")
    if up > -0.5 or not low.is_watertight:
        raise SystemExit("the rebuilt surface is inside out or not closed")

    uvs, chart_of = unwrap(v, f, normals)
    for i, c in enumerate(CHARTS):
        print(f"  chart   {c[0]:<7}{int((chart_of == i).sum()):5d} faces")
    rgb, muzzle = bake(v, f, normals, uvs, source, pts, faces)
    Image.fromarray(rgb, "RGB").save(OUT_TEX, optimize=True)

    lo, hi = v.min(0), v.max(0)
    print(f"  bbox    x {lo[0]:.3f}..{hi[0]:.3f}  y {lo[1]:.3f}..{hi[1]:.3f}"
          f"  z {lo[2]:.3f}..{hi[2]:.3f}")
    print(f"  muzzle  y {muzzle[1]:.4f}, z {muzzle[2]:.4f}")
    json.dump({
        "source": os.path.basename(SRC),
        "texture": os.path.basename(OUT_TEX),
        "tex_size": TEX,
        "palette": [{"name": n, "rgb": list(c)} for n, c in PALETTE],
        "muzzle": [0.0, round(muzzle[1], 4), round(muzzle[2], 4)],
        "verts": [[round(float(c), 5) for c in p] for p in v],
        "faces": f.tolist(),
        # per face, per corner: (u, v) in 0..1, v down from the top
        "uvs": [[[round(float(a) / TEX, 5), round(float(b) / TEX, 5)]
                 for a, b in tri] for tri in uvs],
    }, open(OUT, "w"), separators=(",", ":"))
    print(f"  wrote   {os.path.relpath(OUT, os.path.dirname(HERE))} "
          f"({os.path.getsize(OUT) // 1024} KB) and "
          f"{os.path.relpath(OUT_TEX, os.path.dirname(HERE))} "
          f"({os.path.getsize(OUT_TEX) // 1024} KB)")


if __name__ == "__main__":
    main()
