"""A small software renderer for posed characters: body, clothes, attachments.

    from figure_render import Figure, render

The game draws a character as a skinned body with every worn item on it:
skinned garments that bend with the body, and static pieces pinned to one
bone (a watch on a forearm, bunny ears on the head). This puts all three
together at one frame of one of the game's own animations, so a look can be
judged -- close up and at the size the game really draws it -- before
anybody starts the game.

Conventions are xskin's (Direct3D, row vectors, Y up, a character facing -Z).
A static piece's vertices are in its bone's own frame; the game draws them at
``v * boneWorld``, which is what ``Figure.static`` does, and what
``tools/gen_borg.py`` checks against vanilla's own vambrace and bunny ears
before it trusts it with anything of ours.

The camera is orthographic: yaw about the vertical, then a pitch down, which
is the game's isometric view at pitch 30.
"""
import math
import os

import numpy as np
from PIL import Image

import xskin

PZ = r"C:\Program Files (x86)\Steam\steamapps\common\ProjectZomboid\media"
SKINNED = os.path.join(PZ, "models_X", "Skinned")
ANIMS = os.path.join(PZ, "anims_X", "Bob")
ROOT_BONES = ("Dummy01", "Bip01", "Translation_Data")


def load_texture(path_or_img):
    img = path_or_img if isinstance(path_or_img, Image.Image) else Image.open(path_or_img)
    return np.asarray(img.convert("RGBA"), dtype=np.float32) / 255.0


class Pose:
    """One body (M or F) at one moment of one animation (None = bind pose)."""

    def __init__(self, sex, anim=None, at=0.5):
        self.sex = sex
        self.nodes = xskin.parse(os.path.join(SKINNED, "MaleBody.x" if sex == "M" else "FemaleBody.x"))
        self.skeleton = xskin.Skeleton(self.nodes)
        self.body = xskin.meshes(self.nodes)[0]
        if anim is None:
            self.world = self.skeleton.world()
            return
        own = xskin.Animation(self.nodes)
        conjugate, plain, conj = xskin.quaternion_convention(self.skeleton, own)
        if conjugate is None:
            raise SystemExit(f"{sex}: no quaternion reading reproduces the frame "
                             f"matrices ({plain:.4f} / {conj:.4f}); refusing to guess")
        a = xskin.Animation(xskin.parse(os.path.join(ANIMS, anim)))
        keep = ()
        if sex == "F":
            # Bob's animation on Kate's bones: her lengths, his rotations.
            keep = tuple(b for b in self.skeleton.order if b not in ROOT_BONES)
        self.world = self.skeleton.world(a.local(self.skeleton, a.length * at, conjugate, keep))


class Figure:
    """Parts to draw: each (positions Nx3, faces Mx3, uvs Nx2, texture HxWx4)."""

    def __init__(self, pose):
        self.pose = pose
        self.parts = []

    def skinned(self, mesh, texture, keep_face=None):
        pos = np.array(mesh.skin(self.pose.world), dtype=np.float64)
        faces = np.array([f for f in mesh.faces if keep_face is None or keep_face(f)], dtype=np.int64)
        self.parts.append((pos, faces, np.array(mesh.uvs, dtype=np.float64), load_texture(texture)))

    def body(self, texture):
        self.skinned(self.pose.body, texture)

    def garment(self, xpath, texture):
        mesh = xskin.meshes(xskin.parse(xpath))[0]
        self.skinned(mesh, texture)

    def static(self, verts, faces, uvs, texture, bone):
        m = self.pose.world[bone]
        pos = np.array([xskin.transform(v, m) for v in verts], dtype=np.float64)
        self.parts.append((pos, np.array(faces, dtype=np.int64),
                           np.array(uvs, dtype=np.float64), load_texture(texture)))

    def bounds(self):
        allp = np.concatenate([p for p, *_ in self.parts])
        return allp.min(axis=0), allp.max(axis=0)


def _vertex_normals(pos, faces):
    n = np.zeros_like(pos)
    a, b, c = pos[faces[:, 0]], pos[faces[:, 1]], pos[faces[:, 2]]
    fn = np.cross(b - a, c - a)
    for k in range(3):
        np.add.at(n, faces[:, k], fn)
    ln = np.linalg.norm(n, axis=1, keepdims=True)
    ln[ln == 0] = 1
    return n / ln


CHARACTER_HEIGHT = 0.97     # the bind-pose body, crown to heel, in model units


def render(fig, size=400, yaw=-35.0, pitch=0.0, bg=(28, 30, 36), height=None, light=(-0.4, 0.7, -0.6),
           frame=None, ss=1):
    """Draws the figure. `height` fixes how many pixels tall a character
    stands (the game's scale) instead of fitting the frame; `ss` renders that
    many times larger and scales down, which is what the game's own
    filtering does to a character at a distance."""
    if ss > 1:
        big = render(fig, size * ss, yaw, pitch, bg, None if height is None else height * ss, light,
                     frame, 1)
        return big.resize((size, size), Image.LANCZOS)
    cy, sy = math.cos(math.radians(yaw)), math.sin(math.radians(yaw))
    cp, sp = math.cos(math.radians(pitch)), math.sin(math.radians(pitch))
    R = np.array([[cy, 0, sy], [0, 1, 0], [-sy, 0, cy]]) @ np.eye(3)
    P = np.array([[1, 0, 0], [0, cp, -sp], [0, sp, cp]])
    M = P @ R
    L = np.array(light, dtype=np.float64)
    L /= np.linalg.norm(L)

    views = []
    for pos, faces, uvs, tex in fig.parts:
        if len(faces) == 0:
            continue
        v = pos @ M.T
        # Lighting is in model space, so it turns with the character like a
        # lamp fixed in the room, not with the camera.
        views.append((v, faces, uvs, tex, _vertex_normals(pos, faces)))
    allv = np.concatenate([v for v, *_ in views])
    if frame is None:
        lo, hi = allv.min(axis=0), allv.max(axis=0)
        centre = (lo + hi) / 2
        span = max(hi[0] - lo[0], hi[1] - lo[1]) * 1.08
    else:
        centre, span = frame
    scale = size / span if height is None else height / CHARACTER_HEIGHT
    img = np.zeros((size, size, 3), dtype=np.float32)
    img[:] = np.array(bg, dtype=np.float32) / 255.0
    zb = np.full((size, size), np.inf)

    for v, faces, uvs, tex, vn in views:
        th, tw = tex.shape[:2]
        sx = size / 2 + (v[:, 0] - centre[0]) * scale
        sy_ = size / 2 - (v[:, 1] - centre[1]) * scale
        sz = v[:, 2]
        for f in faces:
            x0, x1, x2 = sx[f]
            y0, y1, y2 = sy_[f]
            d = (y1 - y2) * (x0 - x2) + (x2 - x1) * (y0 - y2)
            if abs(d) < 1e-12:
                continue
            xmin, xmax = max(0, int(math.floor(min(x0, x1, x2)))), min(size - 1, int(math.ceil(max(x0, x1, x2))))
            ymin, ymax = max(0, int(math.floor(min(y0, y1, y2)))), min(size - 1, int(math.ceil(max(y0, y1, y2))))
            if xmin > xmax or ymin > ymax:
                continue
            gx, gy = np.meshgrid(np.arange(xmin, xmax + 1) + 0.5, np.arange(ymin, ymax + 1) + 0.5)
            l0 = ((y1 - y2) * (gx - x2) + (x2 - x1) * (gy - y2)) / d
            l1 = ((y2 - y0) * (gx - x2) + (x0 - x2) * (gy - y2)) / d
            l2 = 1 - l0 - l1
            inside = (l0 >= -1e-4) & (l1 >= -1e-4) & (l2 >= -1e-4)
            if not inside.any():
                continue
            z = l0 * sz[f[0]] + l1 * sz[f[1]] + l2 * sz[f[2]]
            sub = zb[ymin:ymax + 1, xmin:xmax + 1]
            ok = inside & (z < sub)
            if not ok.any():
                continue
            u = (l0 * uvs[f[0], 0] + l1 * uvs[f[1], 0] + l2 * uvs[f[2], 0]) % 1.0
            w = (l0 * uvs[f[0], 1] + l1 * uvs[f[1], 1] + l2 * uvs[f[2], 1]) % 1.0
            tx = np.clip((u * tw).astype(int), 0, tw - 1)
            ty = np.clip((w * th).astype(int), 0, th - 1)
            col = tex[ty, tx]
            ok &= col[..., 3] > 0.5
            if not ok.any():
                continue
            nrm = (l0[..., None] * vn[f[0]] + l1[..., None] * vn[f[1]] + l2[..., None] * vn[f[2]])
            nrm /= np.maximum(np.linalg.norm(nrm, axis=-1, keepdims=True), 1e-9)
            shade = 0.45 + 0.55 * np.clip(nrm @ L, 0, 1)
            sub[ok] = z[ok]
            region = img[ymin:ymax + 1, xmin:xmax + 1]
            region[ok] = col[..., :3][ok] * shade[ok][..., None]
    return Image.fromarray((np.clip(img, 0, 1) * 255).astype(np.uint8), "RGB")
