"""A reader for the game's skinned DirectX .x files, and a pose baker.

Project Zomboid's characters are text-format .x: a frame hierarchy (the
skeleton), one or more skinned meshes with a SkinWeights block per bone, and
animations as per-bone rotation/scale/translation keys. Everything a static
model needs to be a *posed* character is in those three things, so this reads
them and applies linear-blend skinning at one moment of one animation --
which turns a vanilla body in a vanilla garment into a static mesh standing
(or sitting) exactly as the game would draw that frame.

Conventions, all Direct3D's, because the files are:

  * row vectors: a point is transformed as ``p * M``;
  * a bone's world matrix is ``local * parent_world``;
  * a skinned point is ``sum(w_i * p * offset_i * world_i)``;
  * an animation key's local matrix is ``S * R * T``.

The one thing that is *not* settled by the format is which way round the
quaternion in a rotation key is written. Exporters disagree, and a wrong guess
does not throw: it produces a character with every joint bent backwards. So it
is **measured**, not assumed -- ``quaternion_convention`` asks a file whose
animation is known to be its own bind pose which reading reproduces the
frame matrices, and ``tools/gen_ensign.py`` refuses to bake if neither does.
DEV_GUIDE: *ask the asset which way round it is; do not derive it*.
"""

import math
import re

# ---------------------------------------------------------------------------
# Tokenising and the block tree
# ---------------------------------------------------------------------------
_TOKEN = re.compile(r'"[^"]*"|<[^>]*>|[{}]|[;,]|[^\s{};,"<]+')


class Node:
    __slots__ = ("kind", "name", "data", "children", "refs")

    def __init__(self, kind, name):
        self.kind = kind
        self.name = name
        self.data = []          # numbers and strings, in file order
        self.children = []
        self.refs = []          # `{ Name }` references inside the block

    def child(self, kind):
        for c in self.children:
            if c.kind == kind:
                return c
        return None

    def all(self, kind):
        return [c for c in self.children if c.kind == kind]


def _number(tok):
    try:
        if re.fullmatch(r"-?\d+", tok):
            return int(tok)
        return float(tok)
    except ValueError:
        return None


def parse(path):
    """Returns the top-level nodes of a text .x file, templates dropped."""
    src = open(path, encoding="latin-1").read()
    if not src.startswith("xof ") or "txt" not in src[:16]:
        raise ValueError(f"{path}: not a text .x file")
    toks = _TOKEN.findall(src[16:])
    pos = 0
    n = len(toks)

    def block(kind, name):
        nonlocal pos
        node = Node(kind, name)
        while pos < n:
            t = toks[pos]
            if t == "}":
                pos += 1
                return node
            if t in (";", ","):
                pos += 1
                continue
            if t.startswith("<"):
                pos += 1
                continue
            if t.startswith('"'):
                node.data.append(t[1:-1])
                pos += 1
                continue
            if t == "{":
                # `{ Name }` -- a reference to a frame, inside an Animation.
                ref = toks[pos + 1]
                node.refs.append(ref)
                pos += 3
                continue
            num = _number(t)
            if num is not None:
                node.data.append(num)
                pos += 1
                continue
            # An identifier: the start of a child block, `Kind [name] {`.
            if pos + 1 < n and toks[pos + 1] == "{":
                pos += 2
                node.children.append(block(t, None))
                continue
            if pos + 2 < n and toks[pos + 2] == "{":
                name = toks[pos + 1]
                pos += 3
                node.children.append(block(t, name))
                continue
            pos += 1        # a stray word (a template's field name, say)
        return node

    root = block("root", None)
    return [c for c in root.children if c.kind != "template"]


# ---------------------------------------------------------------------------
# Matrices, row-vector
# ---------------------------------------------------------------------------
def mat_mul(a, b):
    return [sum(a[r * 4 + k] * b[k * 4 + c] for k in range(4))
            for r in range(4) for c in range(4)]


IDENTITY = [1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0, 0, 0, 0, 0, 1.0]


def transform(p, m):
    x, y, z = p
    return (x * m[0] + y * m[4] + z * m[8] + m[12],
            x * m[1] + y * m[5] + z * m[9] + m[13],
            x * m[2] + y * m[6] + z * m[10] + m[14])


def quat_matrix(x, y, z, w):
    """D3DXMatrixRotationQuaternion: the row-vector rotation for (x,y,z,w)."""
    xx, yy, zz = x * x, y * y, z * z
    xy, xz, yz = x * y, x * z, y * z
    wx, wy, wz = w * x, w * y, w * z
    return [1 - 2 * (yy + zz), 2 * (xy + wz), 2 * (xz - wy), 0,
            2 * (xy - wz), 1 - 2 * (xx + zz), 2 * (yz + wx), 0,
            2 * (xz + wy), 2 * (yz - wx), 1 - 2 * (xx + yy), 0,
            0, 0, 0, 1.0]


def srt_matrix(s, q, t, conjugate):
    """A key's local matrix. `q` is as the file stores it: (w, x, y, z)."""
    w, x, y, z = q
    if conjugate:
        x, y, z = -x, -y, -z
    r = quat_matrix(x, y, z, w)
    m = [r[0] * s[0], r[1] * s[0], r[2] * s[0], 0,
         r[4] * s[1], r[5] * s[1], r[6] * s[1], 0,
         r[8] * s[2], r[9] * s[2], r[10] * s[2], 0,
         t[0], t[1], t[2], 1.0]
    return m


# ---------------------------------------------------------------------------
# The skeleton, the meshes, the animations
# ---------------------------------------------------------------------------
class Skeleton:
    """Frame name -> (local bind matrix, parent name), in hierarchy order."""

    def __init__(self, nodes):
        self.local = {}
        self.parent = {}
        self.order = []

        def walk(node, parent):
            m = node.child("FrameTransformMatrix")
            self.local[node.name] = list(m.data[:16]) if m else list(IDENTITY)
            self.parent[node.name] = parent
            self.order.append(node.name)
            for c in node.all("Frame"):
                walk(c, node.name)

        for node in nodes:
            if node.kind == "Frame":
                walk(node, None)
        if not self.order:
            raise ValueError("no frame hierarchy in the file")

    def world(self, local=None):
        """World matrices for every frame, from `local` overrides or the bind."""
        local = local or {}
        out = {}
        for name in self.order:
            m = local.get(name, self.local[name])
            p = self.parent[name]
            out[name] = mat_mul(m, out[p]) if p else m
        return out


class SkinnedMesh:
    def __init__(self, node):
        d = node.data
        nv = d[0]
        self.name = node.name
        self.verts = [tuple(d[1 + i * 3:4 + i * 3]) for i in range(nv)]
        k = 1 + nv * 3
        nf = d[k]
        k += 1
        self.faces = []
        for _ in range(nf):
            c = d[k]
            idx = d[k + 1:k + 1 + c]
            k += 1 + c
            # Fan anything wider than a triangle; the game's are all three.
            for i in range(1, c - 1):
                self.faces.append((idx[0], idx[i], idx[i + 1]))
        tc = node.child("MeshTextureCoords")
        if not tc:
            raise ValueError(f"mesh {node.name} has no texture coordinates")
        self.uvs = [tuple(tc.data[1 + i * 2:3 + i * 2]) for i in range(tc.data[0])]
        if len(self.uvs) != nv or len(self.verts) != nv:
            raise ValueError(f"mesh {node.name}: {nv} vertices declared, "
                             f"{len(self.verts)} positions and "
                             f"{len(self.uvs)} uvs parsed")
        self.weights = {}       # bone -> (offset matrix, [(vertex, weight)])
        for sw in node.all("SkinWeights"):
            bone = sw.data[0]
            count = sw.data[1]
            idx = sw.data[2:2 + count]
            wts = sw.data[2 + count:2 + 2 * count]
            offset = list(sw.data[2 + 2 * count:18 + 2 * count])
            if len(offset) != 16:
                raise ValueError(f"mesh {node.name}: bone {bone} has no offset")
            self.weights[bone] = (offset, list(zip(idx, wts)))
        if not self.weights:
            raise ValueError(f"mesh {node.name} has no skin weights")

    def dominant_bones(self):
        """For every vertex, the bone that moves it most."""
        best = [(0.0, None)] * len(self.verts)
        for bone, (_, pairs) in self.weights.items():
            for v, w in pairs:
                if w > best[v][0]:
                    best[v] = (w, bone)
        return [b for _, b in best]

    def skin(self, world):
        """Positions under `world` bone matrices (linear-blend skinning)."""
        acc = [[0.0, 0.0, 0.0, 0.0] for _ in self.verts]
        for bone, (offset, pairs) in self.weights.items():
            if bone not in world:
                raise ValueError(f"mesh {self.name} is skinned to {bone}, "
                                 f"which the skeleton does not have")
            m = mat_mul(offset, world[bone])
            for v, w in pairs:
                x, y, z = transform(self.verts[v], m)
                a = acc[v]
                a[0] += x * w
                a[1] += y * w
                a[2] += z * w
                a[3] += w
        out = []
        for i, a in enumerate(acc):
            if a[3] <= 0:
                out.append(self.verts[i])       # unskinned: leave it be
            else:
                out.append((a[0] / a[3], a[1] / a[3], a[2] / a[3]))
        return out


def meshes(nodes):
    found = []

    def walk(node):
        for c in node.children:
            if c.kind == "Mesh":
                found.append(SkinnedMesh(c))
            walk(c)

    for node in nodes:
        if node.kind == "Mesh":
            found.append(SkinnedMesh(node))
        walk(node)
    return found


class Animation:
    """Per-bone keys: bone -> {'R': [(t, (w,x,y,z))], 'S': [...], 'T': [...]}"""

    KIND = {0: "R", 1: "S", 2: "T"}

    def __init__(self, nodes, name=None):
        sets = [n for n in nodes if n.kind == "AnimationSet"]
        if not sets:
            raise ValueError("no AnimationSet in the file")
        chosen = sets[0]
        if name:
            chosen = next((s for s in sets if s.name == name), None)
            if not chosen:
                raise ValueError(f"no AnimationSet named {name}")
        self.name = chosen.name
        self.bones = {}
        self.length = 0
        for a in chosen.all("Animation"):
            if not a.refs:
                continue
            bone = a.refs[0]
            keys = {}
            for k in a.all("AnimationKey"):
                kind = self.KIND.get(k.data[0])
                if not kind:
                    continue
                n = k.data[1]
                rows, i = [], 2
                for _ in range(n):
                    t, cnt = k.data[i], k.data[i + 1]
                    rows.append((t, tuple(k.data[i + 2:i + 2 + cnt])))
                    i += 2 + cnt
                    self.length = max(self.length, t)
                keys[kind] = rows
            self.bones[bone] = keys

    @staticmethod
    def _sample(rows, t):
        if len(rows) == 1 or t <= rows[0][0]:
            return rows[0][1]
        for (t0, a), (t1, b) in zip(rows, rows[1:]):
            if t0 <= t <= t1:
                f = 0.0 if t1 == t0 else (t - t0) / (t1 - t0)
                if len(a) == 4:
                    # nlerp, taking the short way round
                    dot = sum(p * q for p, q in zip(a, b))
                    if dot < 0:
                        b = tuple(-q for q in b)
                    v = [p + (q - p) * f for p, q in zip(a, b)]
                    n = math.sqrt(sum(c * c for c in v)) or 1.0
                    return tuple(c / n for c in v)
                return tuple(p + (q - p) * f for p, q in zip(a, b))
        return rows[-1][1]

    def local(self, skeleton, t, conjugate, keep_translation=()):
        """Local matrices at time `t` for every bone the animation drives.

        `keep_translation` names bones whose translation comes from the
        *skeleton* rather than the key: retargeting one body's animation onto
        another's bones keeps each bone's own length, so a female skeleton
        driven by a male animation is still her proportions.
        """
        out = {}
        for bone, keys in self.bones.items():
            if bone not in skeleton.local or "R" not in keys:
                continue
            s = self._sample(keys["S"], t) if "S" in keys else (1.0, 1.0, 1.0)
            q = self._sample(keys["R"], t)
            if "T" in keys and bone not in keep_translation:
                tr = self._sample(keys["T"], t)
            else:
                b = skeleton.local[bone]
                tr = (b[12], b[13], b[14])
            out[bone] = srt_matrix(s, q, tr, conjugate)
        return out


def quaternion_convention(skeleton, anim):
    """Which way the file writes its rotation keys: False, True, or None.

    Compares every driven bone's key at t=0 with the skeleton's own frame
    matrix, which a model file's embedded animation reproduces. The reading
    that agrees is the file's convention; if neither agrees the question has
    no answer from this pair and the caller must not guess.
    """
    def err(conj):
        local = anim.local(skeleton, 0, conj)
        worst = 0.0
        for bone, m in local.items():
            b = skeleton.local[bone]
            worst = max(worst, max(abs(p - q) for p, q in zip(m[:12], b[:12])))
        return worst

    plain, conj = err(False), err(True)
    if min(plain, conj) > 0.02:
        return None, plain, conj
    return (conj < plain), plain, conj
