"""Renders a .x mesh to a PNG so geometry and UVs can be checked offline."""
import sys, os, re, zlib, struct
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pngwrite import Image

def read_png_rgba(path):
    """Read an unpaletted 8-bit RGB or RGBA PNG as RGBA pixels."""
    data = open(path, "rb").read()
    pos, idat, width = 8, b"", 0
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            width, height, depth, color_type = struct.unpack(">IIBB", body[:10])
            assert depth == 8 and color_type in (2, 6), (depth, color_type)
        elif tag == b"IDAT":
            idat += body
        pos += 12 + length

    channels = 3 if color_type == 2 else 4
    stride = width * channels
    raw = zlib.decompress(idat)
    previous = bytearray(stride)
    rows = []
    offset = 0
    for _ in range(height):
        filter_type = raw[offset]
        offset += 1
        line = bytearray(raw[offset:offset + stride])
        offset += stride
        for index in range(stride):
            left = line[index - channels] if index >= channels else 0
            above = previous[index]
            upper_left = previous[index - channels] if index >= channels else 0
            if filter_type == 1:
                line[index] = (line[index] + left) & 255
            elif filter_type == 2:
                line[index] = (line[index] + above) & 255
            elif filter_type == 3:
                line[index] = (line[index] + (left + above) // 2) & 255
            elif filter_type == 4:
                estimate = left + above - upper_left
                distances = (abs(estimate - left), abs(estimate - above),
                             abs(estimate - upper_left))
                predictor = (left, above, upper_left)[distances.index(min(distances))]
                line[index] = (line[index] + predictor) & 255
            elif filter_type != 0:
                raise ValueError("unsupported PNG filter %d" % filter_type)
        rows.append(line)
        previous = line

    if channels == 4:
        return width, height, bytearray().join(rows)
    pixels = bytearray(width * height * 4)
    for y, line in enumerate(rows):
        for x in range(width):
            source = x * 3
            target = (y * width + x) * 4
            pixels[target:target + 4] = line[source:source + 3] + b"\xff"
    return width, height, pixels

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
