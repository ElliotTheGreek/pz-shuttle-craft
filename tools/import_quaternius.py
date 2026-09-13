"""Import selected Quaternius CC0 Godot 3 ArrayMesh assets.

The source used by TrekShuttle is kept in tools/assets/quaternius_dispatcher so
regenerating the mod does not require Blender, Godot, network access, or a
third-party Python package.  Godot 3 stores this mesh as float32 XYZ followed
by packed normal/tangent data and half-float UV coordinates; normals are
recomputed after scaling so the importer only depends on documented fields.
"""
import math
import re
import struct

from meshbuild import MeshBuilder


VERTEX_STRIDE = 24


def _pool_bytes(text, name):
    match = re.search(r'"%s": PoolByteArray\( (.*?) \)' % name, text, re.S)
    if not match:
        raise ValueError("missing PoolByteArray %s" % name)
    return bytes(int(value) for value in match.group(1).split(", "))


def _field(text, name):
    match = re.search(r'"%s": (\d+)' % name, text)
    if not match:
        raise ValueError("missing ArrayMesh field %s" % name)
    return int(match.group(1))


def _smooth_normals(vertices, faces):
    normals = [[0.0, 0.0, 0.0] for _ in vertices]
    for ia, ib, ic in faces:
        a, b, c = vertices[ia], vertices[ib], vertices[ic]
        ab = (b[0] - a[0], b[1] - a[1], b[2] - a[2])
        ac = (c[0] - a[0], c[1] - a[1], c[2] - a[2])
        normal = (ab[1] * ac[2] - ab[2] * ac[1],
                  ab[2] * ac[0] - ab[0] * ac[2],
                  ab[0] * ac[1] - ab[1] * ac[0])
        for index in (ia, ib, ic):
            normals[index][0] += normal[0]
            normals[index][1] += normal[1]
            normals[index][2] += normal[2]
    result = []
    for x, y, z in normals:
        length = math.sqrt(x * x + y * y + z * z)
        result.append((x / length, y / length, z / length)
                      if length else (0.0, 1.0, 0.0))
    return result


def import_godot3_array_mesh(source, output, texture_file,
                             target_length=5.0, target_width=3.0):
    """Convert one Godot 3 compressed ArrayMesh into a Y-up DirectX mesh.

    Scaling is uniform and length-led to preserve the original silhouette.
    ``target_width`` is a safety bound, not a request to stretch the craft.
    """
    text = open(source, encoding="utf-8").read()
    vertex_data = _pool_bytes(text, "array_data")
    index_data = _pool_bytes(text, "array_index_data")
    vertex_count = _field(text, "vertex_count")
    index_count = _field(text, "index_count")
    if len(vertex_data) != vertex_count * VERTEX_STRIDE:
        raise ValueError("unexpected vertex stride in %s" % source)
    if len(index_data) != index_count * 2 or index_count % 3:
        raise ValueError("expected 16-bit triangle indices in %s" % source)

    raw_vertices = [struct.unpack_from("<fff", vertex_data,
                                      index * VERTEX_STRIDE)
                    for index in range(vertex_count)]
    uvs = [struct.unpack_from("<ee", vertex_data,
                              index * VERTEX_STRIDE + 20)
           for index in range(vertex_count)]
    indices = struct.unpack("<%dH" % index_count, index_data)
    faces = [tuple(indices[index:index + 3])
             for index in range(0, index_count, 3)]

    xmin, xmax = min(v[0] for v in raw_vertices), max(v[0] for v in raw_vertices)
    ymin = min(v[1] for v in raw_vertices)
    zmin, zmax = min(v[2] for v in raw_vertices), max(v[2] for v in raw_vertices)
    source_width, source_length = xmax - xmin, zmax - zmin
    scale = min(target_length / source_length, target_width / source_width)
    xcenter, zcenter = (xmin + xmax) / 2.0, (zmin + zmax) / 2.0

    vertices = [((x - xcenter) * scale,
                 (y - ymin) * scale,
                 (z - zcenter) * scale)
                for x, y, z in raw_vertices]

    mesh = MeshBuilder(up_axis="y")
    mesh.verts = vertices
    mesh.faces = faces
    mesh.norms = _smooth_normals(vertices, faces)
    # Image files and DirectX use a top-left origin; Godot's mesh UVs use the
    # conventional bottom-left origin.
    mesh.uvs = [(float(u), 1.0 - float(v)) for u, v in uvs]
    nv, nf = mesh.emit(output, "TREKShuttle", texture_file)
    width = max(v[0] for v in vertices) - min(v[0] for v in vertices)
    length = max(v[2] for v in vertices) - min(v[2] for v in vertices)
    height = max(v[1] for v in vertices)
    return nv, nf, width, length, height
