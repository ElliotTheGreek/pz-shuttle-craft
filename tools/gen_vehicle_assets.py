"""Writes the assets the shuttle needs as a vehicle.

    media/models_X/TREK_Empty.x              a vanishingly small mesh, for the
                                             tyres: the vehicle needs wheels to
                                             drive, the shuttle must not show them
    media/textures/TREK_Shuttle_mask.png     the vehicle shader's damage/blood
                                             mask, all black -- no zones marked
    media/ui/vehicles/seatui/trekshuttle_base_small.png
                                             the seat chart: the hull seen from
                                             above, behind the seat markers
    media/ui/vehicles/mechanic overlay/trekshuttle_base.png
                                             the same silhouette for the
                                             mechanics screen

The silhouette is *projected from the hull mesh* rather than drawn, so the
seat markers -- which vanilla places from the seat positions in the vehicle
script, scaled by the vehicle's length -- land on the actual cockpit.

ISVehicleSeatUI draws the vehicle 350 px long (0.7 of its 500 px panel), nose
up, +X (left) to the left of the screen, and centres the image at its original
size. So the image is exactly 350 px along the hull's length, and the vehicle
script's extents length must equal the mesh length (C.VehicleLength, checked by
tests/test_assets.py).

    python tools/gen_vehicle_assets.py
"""
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from pngwrite import Image                       # noqa: E402
from preview_model import read_png_rgba          # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MEDIA = os.path.join(ROOT, "TrekShuttle", "42", "media")
HULL = os.path.join(MEDIA, "models_X", "TREK_Shuttle.x")

SEAT_UI_LENGTH_PX = 350          # 0.7 * 500, ISVehicleSeatUI:render


def read_mesh(path):
    text = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r"Mesh\s*\w*\s*\{\s*(\d+);(.*?);;\s*(\d+);(.*?);;", text, re.S)
    verts = [tuple(map(float, t)) for t in re.findall(
        r"(-?\d+\.?\d*(?:e-?\d+)?);(-?\d+\.?\d*(?:e-?\d+)?);(-?\d+\.?\d*(?:e-?\d+)?);",
        m.group(2))]
    faces = [tuple(map(int, f.split(","))) for f in re.findall(r"3;([\d,]+);", m.group(4))]
    return verts, faces


def silhouette(verts, faces, length_px, pad=6):
    """The hull from above, nose up, as a filled grey shape with a light rim."""
    xs = [v[0] for v in verts]
    zs = [v[2] for v in verts]
    min_x, max_x, min_z, max_z = min(xs), max(xs), min(zs), max(zs)
    scale = length_px / (max_z - min_z)
    w = int(round((max_x - min_x) * scale)) + pad * 2
    h = length_px + pad * 2
    mask = [[False] * w for _ in range(h)]

    def to_px(v):
        # +X (vehicle left) draws to the screen's left, +Z (nose) to the top,
        # the way ISVehicleSeatUI places seats: x = cx - offX, y = cy - offZ.
        return (pad + (max_x - v[0]) * scale, pad + (max_z - v[2]) * scale)

    for f in faces:
        (ax, ay), (bx, by), (cx, cy) = (to_px(verts[i]) for i in f)
        x0, x1 = int(max(0, min(ax, bx, cx))), int(min(w - 1, max(ax, bx, cx)) + 1)
        y0, y1 = int(max(0, min(ay, by, cy))), int(min(h - 1, max(ay, by, cy)) + 1)
        area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay)
        if abs(area) < 1e-9:
            continue
        for py in range(y0, y1 + 1):
            for px in range(x0, x1 + 1):
                sx, sy = px + 0.5, py + 0.5
                w0 = (bx - sx) * (cy - sy) - (cx - sx) * (by - sy)
                w1 = (cx - sx) * (ay - sy) - (ax - sx) * (cy - sy)
                w2 = (ax - sx) * (by - sy) - (bx - sx) * (ay - sy)
                if (w0 >= 0 and w1 >= 0 and w2 >= 0) or (w0 <= 0 and w1 <= 0 and w2 <= 0):
                    if 0 <= py < h and 0 <= px < w:
                        mask[py][px] = True

    img = Image(w, h)
    fill, rim = (70, 76, 88, 235), (200, 208, 220, 255)
    for y in range(h):
        for x in range(w):
            if not mask[y][x]:
                continue
            edge = any(not (0 <= y + dy < h and 0 <= x + dx < w and mask[y + dy][x + dx])
                       for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
            img.set(x, y, rim if edge else fill)
    return img


EMPTY_X = """xof 0303txt 0032

Frame Root {
 FrameTransformMatrix {
  1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0,0.0,0.0,0.0,0.0,1.0;;
 }
 Mesh TREK_Empty {
  3;
  0.0;0.0;0.0;,
  0.0001;0.0;0.0;,
  0.0;0.0001;0.0;;
  1;
  3;0,1,2;;
  MeshNormals {
   1;
   0.0;0.0;1.0;;
   1;
   3;0,0,0;;
  }
  MeshTextureCoords {
   3;
   0.0;0.0;,
   0.0;0.0;,
   0.0;0.0;;
  }
 }
}
"""


def main():
    verts, faces = read_mesh(HULL)
    art = silhouette(verts, faces, SEAT_UI_LENGTH_PX)
    for rel in ("ui/vehicles/seatui/trekshuttle_base_small.png",
                "ui/vehicles/mechanic overlay/trekshuttle_base.png"):
        path = os.path.join(MEDIA, *rel.split("/"))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        art.save(path)

    with open(os.path.join(MEDIA, "models_X", "TREK_Empty.x"), "w", newline="\n") as f:
        f.write(EMPTY_X)

    tw, th, _ = read_png_rgba(os.path.join(MEDIA, "textures", "TREK_Shuttle.png"))
    Image(tw, th, (0, 0, 0, 255)).save(os.path.join(MEDIA, "textures", "TREK_Shuttle_mask.png"))

    xs = [v[0] for v in verts]
    zs = [v[2] for v in verts]
    ys = [v[1] for v in verts]
    print(f"seat chart {art.w}x{art.h}px; hull {max(xs) - min(xs):.2f} wide, "
          f"{max(ys) - min(ys):.2f} tall, {max(zs) - min(zs):.2f} long; "
          f"{len(faces)} faces projected")


if __name__ == "__main__":
    main()
