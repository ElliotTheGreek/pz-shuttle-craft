"""Render a model of boxes straight into Project Zomboid 2x iso tiles.

The Adirondack's furniture is modelled rather than drawn, because an image
model cannot paint the same bed twice from two directions. A model rendered
from each facing is the same bed by construction.

Coordinates are in squares: x runs east (down-right on screen), y runs south
(down-left), z is up, one storey is `STOREY` units. The projection is the one
vanilla's tiles are cut to (ADIRONDACK.md, gen_adirondack_tiles.py):

    screen x = 64 * (x - y)
    screen y = 32 * (x + y) - H * z          H = 192 px a storey

and in its own 128x256 cell, a square's north-west corner sits at (64, 192).

Only the three faces the game's camera can see are drawn -- top, east-facing
and south-facing -- and they are lit the way vanilla lights walls: a face that
looks east (the inside of a west wall) at 0.84 of one that looks south.

Every pixel belongs to the square its surface point stands over, so an object
two squares long comes out as two tiles that reassemble exactly when the engine
draws them side by side.
"""
import numpy as np
from PIL import Image

CW, CH = 128, 256
STOREY = 2.449          # world units a storey (the vehicle code's level height)
H = 192.0 / STOREY      # screen px per world unit of height
SS = 4                  # supersampling
LIGHT = {"top": 1.06, "east": 0.84, "south": 1.0}


class Box:
    """An axis-aligned box. `color` is an (r,g,b) or a dict per face; `tex` a
    PIL image (or a dict per face) stretched across each face."""

    def __init__(self, x0, y0, z0, x1, y1, z1, color=(200, 200, 200), tex=None,
                 grain=0.0):
        self.a = (min(x0, x1), min(y0, y1), min(z0, z1))
        self.b = (max(x0, x1), max(y0, y1), max(z0, z1))
        self.color = color
        self.tex = tex
        self.grain = grain

    def face_color(self, face):
        c = self.color
        return c[face] if isinstance(c, dict) else c

    def face_tex(self, face):
        t = self.tex
        if isinstance(t, dict):
            return t.get(face)
        return t

    def rotated(self, turns):
        """Quarter turns about the vertical, keeping the model in +x/+y."""
        box = self
        for _ in range(turns % 4):
            (x0, y0, z0), (x1, y1, z1) = box.a, box.b
            # (x, y) -> (-y, x), then shifted back into positive space by the
            # caller's footprint; see `rotate_scene`.
            box = Box(-y1, x0, z0, -y0, x1, z1, box.color, box.tex, box.grain)
        return box


def rotate_scene(boxes, turns, footprint):
    """Rotate a whole model in quarter turns and move it back onto its squares."""
    out = [b.rotated(turns) for b in boxes]
    fx, fy = footprint
    if turns % 2:
        fx, fy = fy, fx
    minx = min(b.a[0] for b in out)
    miny = min(b.a[1] for b in out)
    sx = -np.floor(minx + 1e-9)
    sy = -np.floor(miny + 1e-9)
    moved = []
    for b in out:
        nb = Box(b.a[0] + sx, b.a[1] + sy, b.a[2], b.b[0] + sx, b.b[1] + sy, b.b[2],
                 b.color, b.tex, b.grain)
        moved.append(nb)
    return moved, (fx, fy)


def _sample(tex, u, v):
    arr = np.asarray(tex.convert("RGB"), dtype=np.float32)
    h, w = arr.shape[:2]
    tx = np.clip((u * w).astype(int), 0, w - 1)
    ty = np.clip((v * h).astype(int), 0, h - 1)
    return arr[ty, tx]


def render(boxes, footprint, seed=1):
    """Return {(i, j): 128x256 RGBA PIL image} for each square the model covers."""
    nx, ny = footprint
    margin_top = 256
    W = (64 * (nx + ny) + 128) * SS
    Hh = (32 * (nx + ny) + margin_top + 64) * SS
    ox = (64 * ny + 64) * SS
    oy = margin_top * SS
    rgb = np.zeros((Hh, W, 3), np.float32)
    depth = np.full((Hh, W), -1e9, np.float32)
    owner = np.full((Hh, W, 2), -1, np.int32)
    rng = np.random.default_rng(seed)

    ys, xs = np.mgrid[0:Hh, 0:W]
    sxw = (xs - ox + 0.5) / (64.0 * SS)       # = x - y
    syw = (ys - oy + 0.5) / (32.0 * SS)       # = x + y - (H/32) z

    for box in boxes:
        (x0, y0, z0), (x1, y1, z1) = box.a, box.b
        for face in ("top", "east", "south"):
            if face == "top":
                s = syw + (H / 32.0) * z1
                x = (s + sxw) / 2.0
                y = (s - sxw) / 2.0
                z = np.full_like(x, z1)
                m = (x >= x0) & (x <= x1) & (y >= y0) & (y <= y1)
                u = (x - x0) / max(1e-6, x1 - x0)
                v = (y - y0) / max(1e-6, y1 - y0)
                ox_, oy_ = x, y
            elif face == "east":
                x = np.full_like(sxw, x1)
                y = x1 - sxw
                z = ((x1 + y) - syw) * (32.0 / H)
                m = (y >= y0) & (y <= y1) & (z >= z0) & (z <= z1)
                u = (y - y0) / max(1e-6, y1 - y0)
                v = 1.0 - (z - z0) / max(1e-6, z1 - z0)
                ox_, oy_ = x - 1e-4, y
            else:
                y = np.full_like(sxw, y1)
                x = y1 + sxw
                z = ((x + y1) - syw) * (32.0 / H)
                m = (x >= x0) & (x <= x1) & (z >= z0) & (z <= z1)
                u = (x - x0) / max(1e-6, x1 - x0)
                v = 1.0 - (z - z0) / max(1e-6, z1 - z0)
                ox_, oy_ = x, y - 1e-4
            if not m.any():
                continue
            d = x + y + (64.0 / H) * z
            m &= d > depth
            if not m.any():
                continue
            tex = box.face_tex(face)
            if tex is not None:
                col = _sample(tex, u[m], v[m])
            else:
                col = np.tile(np.array(box.face_color(face), np.float32), (m.sum(), 1))
            if box.grain:
                col = col * (1.0 + box.grain * rng.standard_normal((m.sum(), 1)).astype(np.float32))
            col = col * LIGHT[face]
            rgb[m] = col
            depth[m] = d[m]
            owner[m, 0] = np.floor(ox_[m]).astype(np.int32)
            owner[m, 1] = np.floor(oy_[m]).astype(np.int32)

    return _extract(rgb, owner, footprint, ox, oy)


def _canvas(footprint):
    nx, ny = footprint
    margin_top = 320
    W = (64 * (nx + ny) + 128) * SS
    Hh = (32 * (nx + ny) + margin_top + 64) * SS
    ox = (64 * ny + 64) * SS
    oy = margin_top * SS
    return W, Hh, ox, oy


def _extract(rgb, owner, footprint, ox, oy):
    nx, ny = footprint
    tiles = {}
    for i in range(nx):
        for j in range(ny):
            mine = (owner[..., 0] == i) & (owner[..., 1] == j)
            cx = ox + (64 * (i - j) - 64) * SS
            cy = oy + (32 * (i + j) - 192) * SS
            sub = np.s_[cy:cy + CH * SS, cx:cx + CW * SS]
            a = mine[sub].astype(np.float32)
            c = rgb[sub] * a[..., None]
            # box-filter down to 1x, premultiplied
            a1 = a.reshape(CH, SS, CW, SS).mean(axis=(1, 3))
            c1 = c.reshape(CH, SS, CW, SS, 3).mean(axis=(1, 3))
            with np.errstate(invalid="ignore", divide="ignore"):
                c1 = np.where(a1[..., None] > 0, c1 / a1[..., None], 0)
            img = np.dstack([np.clip(c1, 0, 255), np.clip(a1 * 255, 0, 255)]).astype(np.uint8)
            tiles[(i, j)] = Image.fromarray(img, "RGBA")
    return tiles


# --- triangle meshes ---------------------------------------------------------

def _shade(normals):
    """Vanilla's wall lighting spread over any normal: a face looking east
    (+x) gets 0.84, south (+y) 1.0, up (+z) 1.06, blended by how much it looks
    each way; faces turned from the camera are only ever seen at glancing
    angles and take 0.8."""
    n = normals / np.maximum(1e-9, np.linalg.norm(normals, axis=1, keepdims=True))
    pos = np.clip(n, 0, None) ** 2
    neg = np.clip(-n, 0, None) ** 2
    return pos[:, 0] * LIGHT["east"] + pos[:, 1] * LIGHT["south"] + pos[:, 2] * LIGHT["top"] \
        + neg.sum(axis=1) * 0.8


def render_mesh(verts, faces, uvs, texture, footprint, face_colors=None):
    """Render a textured triangle mesh already placed in world squares.

    verts (n,3) world x, y, z; faces (m,3); uvs (n,2) in glTF convention (v
    down from the top of the image); texture a PIL image. Returns tiles as
    `render` does."""
    W, Hh, ox, oy = _canvas(footprint)
    rgb = np.zeros((Hh, W, 3), np.float32)
    depth = np.full((Hh, W), -1e9, np.float32)
    owner = np.full((Hh, W, 2), -1, np.int32)
    tex = np.asarray(texture.convert("RGB"), dtype=np.float32)
    th, tw = tex.shape[:2]

    sx = ox + 64.0 * SS * (verts[:, 0] - verts[:, 1])
    sy = oy + SS * (32.0 * (verts[:, 0] + verts[:, 1]) - H * verts[:, 2])
    dz = verts[:, 0] + verts[:, 1] + (64.0 / H) * verts[:, 2]
    tri = verts[faces]
    normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    shade = _shade(normals)

    for k, (a, b, c) in enumerate(faces):
        xs = np.array([sx[a], sx[b], sx[c]])
        ys = np.array([sy[a], sy[b], sy[c]])
        x0, x1 = int(max(0, np.floor(xs.min()))), int(min(W - 1, np.ceil(xs.max())))
        y0, y1 = int(max(0, np.floor(ys.min()))), int(min(Hh - 1, np.ceil(ys.max())))
        if x1 < x0 or y1 < y0:
            continue
        den = (ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2])
        if abs(den) < 1e-9:
            continue
        py, px = np.mgrid[y0:y1 + 1, x0:x1 + 1]
        px = px + 0.5
        py = py + 0.5
        w0 = ((ys[1] - ys[2]) * (px - xs[2]) + (xs[2] - xs[1]) * (py - ys[2])) / den
        w1 = ((ys[2] - ys[0]) * (px - xs[2]) + (xs[0] - xs[2]) * (py - ys[2])) / den
        w2 = 1.0 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        d = w0 * dz[a] + w1 * dz[b] + w2 * dz[c]
        region = np.s_[y0:y1 + 1, x0:x1 + 1]
        m = inside & (d > depth[region])
        if not m.any():
            continue
        if face_colors is not None:
            col = np.tile(face_colors[k], (m.sum(), 1))
        else:
            u = w0 * uvs[a, 0] + w1 * uvs[b, 0] + w2 * uvs[c, 0]
            v = w0 * uvs[a, 1] + w1 * uvs[b, 1] + w2 * uvs[c, 1]
            tx = np.clip((u[m] % 1.0) * tw, 0, tw - 1).astype(int)
            ty = np.clip((v[m] % 1.0) * th, 0, th - 1).astype(int)
            col = tex[ty, tx]
        wx = w0 * verts[a, 0] + w1 * verts[b, 0] + w2 * verts[c, 0]
        wy = w0 * verts[a, 1] + w1 * verts[b, 1] + w2 * verts[c, 1]
        sub_rgb = rgb[region]
        sub_rgb[m] = col * shade[k]
        depth[region][m] = d[m]
        sub_own = owner[region]
        sub_own[m, 0] = np.floor(np.clip(wx[m], 0, footprint[0] - 1e-4)).astype(np.int32)
        sub_own[m, 1] = np.floor(np.clip(wy[m], 0, footprint[1] - 1e-4)).astype(np.int32)
    return _extract(rgb, owner, footprint, ox, oy)


def place_glb(path, facing, w, d, h, inset=0.04):
    """Load a glTF mesh (Y up, front toward +Z, as an image-to-3D model comes)
    and lay it in world squares for one facing.

    w: along the wall, d: out from it, h: up. The model is stretched to fill
    that box less `inset`; its back goes against the wall the facing names.
    Handedness is kept -- a facing is a turn, never a mirror -- so a terminal
    on the desk's right is on its right from every side."""
    import trimesh
    scene = trimesh.load(path)
    mesh = scene.to_geometry() if hasattr(scene, "to_geometry") else scene
    v = np.asarray(mesh.vertices, np.float64)
    lo, hi = v.min(axis=0), v.max(axis=0)
    t = (v - lo) / np.maximum(1e-9, hi - lo)          # 0..1 in each glTF axis
    across = inset + t[:, 0] * (w - 2 * inset)         # glTF +x: the model's right
    out = inset + t[:, 2] * (d - 2 * inset)            # glTF +z: toward the room
    up = t[:, 1] * h
    if facing == "W":        # back on the west wall, front looks east
        wx, wy = out, across
        fp = (d, w)
    elif facing == "N":      # back on the north wall, front looks south
        wx, wy = w - across, out
        fp = (w, d)
    elif facing == "E":      # back on the east wall, front looks west
        wx, wy = d - out, w - across
        fp = (d, w)
    else:                    # "S": back on the south wall, front looks north
        wx, wy = across, d - out
        fp = (w, d)
    world = np.stack([wx, wy, up], axis=1)
    uv = np.asarray(mesh.visual.uv, np.float64) if hasattr(mesh.visual, "uv") and mesh.visual.uv is not None else None
    if uv is not None:
        uv = uv.copy()
        uv[:, 1] = 1.0 - uv[:, 1]
        img = mesh.visual.material.baseColorTexture if hasattr(mesh.visual.material, "baseColorTexture") \
            else mesh.visual.material.image
    else:
        uv, img = np.zeros((len(v), 2)), Image.new("RGB", (1, 1), (180, 180, 180))
    return world, np.asarray(mesh.faces), uv, img, (int(round(fp[0])), int(round(fp[1])))
