"""Renders a .x mesh to a PNG so geometry and UVs can be checked offline."""
import sys, os, re, zlib, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pngwrite import Image

def read_png_rgba(path):
    data = open(path, "rb").read()
    pos, idat, w = 8, b"", 0
    while pos < len(data):
        ln = struct.unpack(">I", data[pos:pos+4])[0]
        tag = data[pos+4:pos+8]
        body = data[pos+8:pos+8+ln]
        if tag == b"IHDR":
            w, h, depth, ctype = struct.unpack(">IIBB", body[:10])
            assert depth == 8 and ctype == 6, (depth, ctype)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + ln
    raw = zlib.decompress(idat)
    px = bytearray(w * h * 4)
    stride = w * 4
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p+stride]); p += stride
        for i in range(stride):
            a = line[i - 4] if i >= 4 else 0
            b = prev[i]
            c = prev[i - 4] if i >= 4 else 0
            if f == 1: line[i] = (line[i] + a) & 255
            elif f == 2: line[i] = (line[i] + b) & 255
            elif f == 3: line[i] = (line[i] + (a + b) // 2) & 255
            elif f == 4:
                pp = a + b - c
                pa, pb, pc = abs(pp-a), abs(pp-b), abs(pp-c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 255
        px[y*stride:(y+1)*stride] = line
        prev = line
    return w, h, px

def parse_x(path):
    src = open(path).read()
    src = src[src.index("Mesh "):]
    nums = lambda s: [float(x) for x in re.findall(r"-?\d+\.\d+", s)]
    mv = re.search(r"Mesh\s+\w+\s*\{\s*(\d+);(.*?);;\s*(\d+);(.*?);;\s*MeshNormals", src, re.S)
    nv = int(mv.group(1))
    vs = re.findall(r"(-?\d+\.\d+);(-?\d+\.\d+);(-?\d+\.\d+);", mv.group(2))
    verts = [tuple(float(c) for c in v) for v in vs][:nv]
    fs = re.findall(r"3;(\d+),(\d+),(\d+);", mv.group(4))
    faces = [tuple(int(c) for c in f) for f in fs]
    mt = re.search(r"MeshTextureCoords\s*\{\s*(\d+);(.*?);;\s*\}", src, re.S)
    uvs = [(float(a), float(b)) for a, b in
           re.findall(r"(-?\d+\.\d+);(-?\d+\.\d+);", mt.group(2))][:nv]
    return verts, faces, uvs

def render(xpath, texpath, outpath, size=400, up_axis="y", yaw_deg=-35):
    """Draws the mesh at roughly the game's camera angle.

    The frame auto-fits the model's bounding box, so a 5-tile shuttle and a
    1-tile police box both fill it. Without that a model larger than a tile
    simply ran off every edge and could not be judged at all.
    """
    verts, faces, uvs = parse_x(xpath)
    if up_axis == "y":
        # the projection below is written for Z-up; swap the axes back
        verts = [(x, z, y) for (x, y, z) in verts]
    tw, th, tex = read_png_rgba(texpath)
    img = Image(size, size, (28, 30, 36, 255))
    zbuf = [[1e9] * size for _ in range(size)]

    # camera: PZ-like isometric, looking down at the south-east corner
    import math
    yaw, pitch = math.radians(yaw_deg), math.radians(30)
    cy, sy = math.cos(yaw), math.sin(yaw)
    cp, sp = math.cos(pitch), math.sin(pitch)

    def rotate(p):
        x, y, z = p
        xr = x * cy - y * sy
        yr = x * sy + y * cy
        return xr, yr * cp - z * sp, yr * sp + z * cp   # right, depth, up

    # Fit the rotated silhouette into the frame with a small margin, so the
    # scale follows the model instead of assuming it is one tile across.
    flat = [rotate(p) for p in verts]
    xs = [f[0] for f in flat]
    us = [f[2] for f in flat]
    span = max(max(xs) - min(xs), max(us) - min(us)) or 1.0
    scale = size * 0.86 / span
    cx = (max(xs) + min(xs)) / 2
    cu = (max(us) + min(us)) / 2

    def project(p):
        xr, depth, up = rotate(p)
        return (size / 2 + (xr - cx) * scale,
                size / 2 - (up - cu) * scale, depth)

    def sample(u, v):
        px = int(u * tw) % tw
        py = int(v * th) % th
        i = (py * tw + px) * 4
        return tuple(tex[i:i+4])

    for (a, b, c) in faces:
        pa, pb, pc = project(verts[a]), project(verts[b]), project(verts[c])
        ua, ub, uc = uvs[a], uvs[b], uvs[c]
        minx = max(0, int(min(pa[0], pb[0], pc[0])))
        maxx = min(size - 1, int(max(pa[0], pb[0], pc[0])) + 1)
        miny = max(0, int(min(pa[1], pb[1], pc[1])))
        maxy = min(size - 1, int(max(pa[1], pb[1], pc[1])) + 1)
        d = ((pb[1]-pc[1])*(pa[0]-pc[0]) + (pc[0]-pb[0])*(pa[1]-pc[1]))
        if abs(d) < 1e-9: continue
        for py in range(miny, maxy + 1):
            for px in range(minx, maxx + 1):
                l1 = ((pb[1]-pc[1])*(px-pc[0]) + (pc[0]-pb[0])*(py-pc[1])) / d
                l2 = ((pc[1]-pa[1])*(px-pc[0]) + (pa[0]-pc[0])*(py-pc[1])) / d
                l3 = 1 - l1 - l2
                if l1 < -0.002 or l2 < -0.002 or l3 < -0.002: continue
                z = l1*pa[2] + l2*pb[2] + l3*pc[2]
                if z >= zbuf[py][px]: continue
                zbuf[py][px] = z
                u = l1*ua[0] + l2*ub[0] + l3*uc[0]
                v = l1*ua[1] + l2*ub[1] + l3*uc[1]
                img.set(px, py, sample(u, v))
    img.save(outpath)
    print("preview ->", outpath)

if __name__ == "__main__":
    yaw = float(sys.argv[4]) if len(sys.argv) > 4 else -35.0
    render(sys.argv[1], sys.argv[2], sys.argv[3], yaw_deg=yaw)
