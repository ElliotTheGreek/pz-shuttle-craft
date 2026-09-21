"""Deterministic GLB-to-Project-Zomboid world-model importer.

Supports the glTF 2.0 features used by the vendored Type 6 shuttle: embedded
buffers/images, scene-node matrices, indexed triangles, float positions/UVs,
and one diffuse texture. No Blender or third-party package is required.
"""
import json
import math
import struct

from meshbuild import MeshBuilder

_COMPONENTS = {5121: ("B", 1), 5123: ("H", 2),
               5125: ("I", 4), 5126: ("f", 4)}
_TYPE_COUNTS = {"SCALAR": 1, "VEC2": 2, "VEC3": 3, "VEC4": 4}


def _load_glb(path):
    data = open(path, "rb").read()
    magic, version, length = struct.unpack_from("<4sII", data, 0)
    if magic != b"glTF" or version != 2 or length != len(data):
        raise ValueError("expected a complete glTF 2.0 binary file")
    chunks, offset = {}, 12
    while offset < len(data):
        size, kind = struct.unpack_from("<II", data, offset)
        offset += 8
        chunks[kind] = data[offset:offset + size]
        offset += size
    document = json.loads(chunks[0x4E4F534A].rstrip(b" \0"))
    return document, chunks[0x004E4942]


def _accessor(document, binary, index):
    accessor = document["accessors"][index]
    view = document["bufferViews"][accessor["bufferView"]]
    code, component_size = _COMPONENTS[accessor["componentType"]]
    count = _TYPE_COUNTS[accessor["type"]]
    record_size = component_size * count
    stride = view.get("byteStride", record_size)
    start = view.get("byteOffset", 0) + accessor.get("byteOffset", 0)
    fmt = "<" + code * count
    return [struct.unpack_from(fmt, binary, start + item * stride)
            for item in range(accessor["count"])]


def _identity():
    return (1.0, 0.0, 0.0, 0.0,
            0.0, 1.0, 0.0, 0.0,
            0.0, 0.0, 1.0, 0.0,
            0.0, 0.0, 0.0, 1.0)


def _multiply(a, b):
    """Multiply column-major glTF matrices."""
    return tuple(sum(a[row + k * 4] * b[k + col * 4] for k in range(4))
                 for col in range(4) for row in range(4))


def _node_matrix(node):
    if "matrix" in node:
        return tuple(node["matrix"])
    tx, ty, tz = node.get("translation", (0.0, 0.0, 0.0))
    sx, sy, sz = node.get("scale", (1.0, 1.0, 1.0))
    x, y, z, w = node.get("rotation", (0.0, 0.0, 0.0, 1.0))
    rotation = (
        1-2*y*y-2*z*z, 2*x*y+2*z*w, 2*x*z-2*y*w, 0,
        2*x*y-2*z*w, 1-2*x*x-2*z*z, 2*y*z+2*x*w, 0,
        2*x*z+2*y*w, 2*y*z-2*x*w, 1-2*x*x-2*y*y, 0,
        0, 0, 0, 1)
    scale = (sx, 0, 0, 0, 0, sy, 0, 0, 0, 0, sz, 0, 0, 0, 0, 1)
    translation = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0,
                   tx, ty, tz, 1)
    return _multiply(translation, _multiply(rotation, scale))


def _point(matrix, point):
    x, y, z = point
    return (matrix[0]*x + matrix[4]*y + matrix[8]*z + matrix[12],
            matrix[1]*x + matrix[5]*y + matrix[9]*z + matrix[13],
            matrix[2]*x + matrix[6]*y + matrix[10]*z + matrix[14])


def _smooth_normals(vertices, faces):
    sums = [[0.0, 0.0, 0.0] for _ in vertices]
    for ia, ib, ic in faces:
        a, b, c = vertices[ia], vertices[ib], vertices[ic]
        ab = (b[0]-a[0], b[1]-a[1], b[2]-a[2])
        ac = (c[0]-a[0], c[1]-a[1], c[2]-a[2])
        normal = (ab[1]*ac[2]-ab[2]*ac[1],
                  ab[2]*ac[0]-ab[0]*ac[2],
                  ab[0]*ac[1]-ab[1]*ac[0])
        for vertex in (ia, ib, ic):
            for axis in range(3):
                sums[vertex][axis] += normal[axis]
    result = []
    for x, y, z in sums:
        length = math.sqrt(x*x + y*y + z*z)
        result.append((x/length, y/length, z/length)
                      if length else (0.0, 1.0, 0.0))
    return result


def import_glb(source, mesh_output, texture_output, texture_file,
               target_length=5.0, target_width=3.0, target_height=None,
               name="TREKShuttle", yaw=0):
    """Imports a GLB as a Project Zomboid world model.

    Three of the parameters exist for the EMH and are additive, so the hull's
    call site behaves exactly as it did:

    `target_height` fits the model by **height** instead of by footprint. A
    hull is a thing you fit into a parking space and a person is a thing you
    fit under a deckhead, and scaling a standing figure by
    min(width/xspan, length/zspan) makes its size an accident of how wide its
    shoulders happen to be. Fitting by height also skips the axis swap below,
    which exists to put a vehicle's long axis fore-and-aft and would only turn
    a figure sideways.

    `name` is the mesh name written into the .x file, which was hardcoded to
    the hull's.

    `yaw` turns the model about the up axis, in whole degrees, before it is
    fitted. **A figure has a front and a hull does not** -- the hull's heading
    is decided by the footprint swap above, while a person imported as drawn
    faces whichever way the camera that generated him was pointing, which for
    an image-to-3D model is +Z, or due north in this engine. A world model
    standing in the cabin at north is a man with his back to everyone in it.
    Seen in the first render; invisible in the source.
    """
    document, binary = _load_glb(source)
    vertices, uvs, faces = [], [], []

    def visit(node_index, parent):
        node = document["nodes"][node_index]
        world = _multiply(parent, _node_matrix(node))
        if "mesh" in node:
            for primitive in document["meshes"][node["mesh"]]["primitives"]:
                if primitive.get("mode", 4) != 4:
                    raise ValueError("only triangle primitives are supported")
                base = len(vertices)
                positions = _accessor(document, binary,
                                      primitive["attributes"]["POSITION"])
                texcoords = _accessor(document, binary,
                                      primitive["attributes"]["TEXCOORD_0"])
                index_records = _accessor(document, binary,
                                          primitive["indices"])
                vertices.extend(_point(world, position)
                                for position in positions)
                uvs.extend((float(uv[0]), float(uv[1])) for uv in texcoords)
                indices = [record[0] for record in index_records]
                faces.extend((base+indices[i], base+indices[i+1],
                              base+indices[i+2])
                             for i in range(0, len(indices), 3))
        for child in node.get("children", []):
            visit(child, world)

    scene = document["scenes"][document.get("scene", 0)]
    for node_index in scene["nodes"]:
        visit(node_index, _identity())
    if not vertices or not faces:
        raise ValueError("GLB contains no indexed triangle mesh")

    # glTF is Y-up. Put the longest horizontal axis fore/aft on Z -- for a
    # hull, whose length is the thing that has to line up with the road. A
    # figure has no long horizontal axis worth naming, and this would simply
    # stand him at right angles to the way he was drawn.
    if target_height is None:
        xspan = max(v[0] for v in vertices) - min(v[0] for v in vertices)
        zspan = max(v[2] for v in vertices) - min(v[2] for v in vertices)
        if xspan > zspan:
            vertices = [(-z, y, x) for x, y, z in vertices]

    if yaw:
        angle = math.radians(yaw)
        cos, sin = math.cos(angle), math.sin(angle)
        vertices = [(x * cos + z * sin, y, -x * sin + z * cos)
                    for x, y, z in vertices]

    xmin, xmax = min(v[0] for v in vertices), max(v[0] for v in vertices)
    ymin, ymax = min(v[1] for v in vertices), max(v[1] for v in vertices)
    zmin, zmax = min(v[2] for v in vertices), max(v[2] for v in vertices)
    if target_height is not None:
        scale = target_height/(ymax-ymin)
    else:
        scale = min(target_width/(xmax-xmin), target_length/(zmax-zmin))
    xcenter, zcenter = (xmin+xmax)/2, (zmin+zmax)/2
    vertices = [((x-xcenter)*scale, (y-ymin)*scale, (z-zcenter)*scale)
                for x, y, z in vertices]

    material_index = document["meshes"][0]["primitives"][0].get("material", 0)
    material = document["materials"][material_index]
    extension = material.get("extensions", {}).get(
        "KHR_materials_pbrSpecularGlossiness", {})
    texture_index = extension.get("diffuseTexture", {}).get("index")
    if texture_index is None:
        texture_index = material.get("pbrMetallicRoughness", {}).get(
            "baseColorTexture", {}).get("index")
    if texture_index is None:
        raise ValueError("material has no diffuse/base-color texture")
    image_index = document["textures"][texture_index]["source"]
    image = document["images"][image_index]
    view = document["bufferViews"][image["bufferView"]]
    start = view.get("byteOffset", 0)
    texture = binary[start:start + view["byteLength"]]
    if image.get("mimeType") != "image/png" or not texture.startswith(b"\x89PNG"):
        raise ValueError("diffuse texture is not an embedded PNG")
    # glTF pads a bufferView out to a four-byte boundary, so the slice can end
    # with a byte or three of nothing. Written straight out that is a PNG with
    # rubbish stuck to it: every image viewer shrugs and a strict reader --
    # including this project's own read_png_rgba -- walks off the end of the
    # last chunk and throws. Cut it at the end of IEND.
    end = texture.rfind(b"IEND")
    if end != -1:
        texture = texture[:end + 8]
    open(texture_output, "wb").write(texture)

    mesh = MeshBuilder(up_axis="y")
    mesh.verts = vertices
    mesh.faces = faces
    mesh.norms = _smooth_normals(vertices, faces)
    mesh.uvs = uvs
    nv, nf = mesh.emit(mesh_output, name, texture_file)
    width = max(v[0] for v in vertices) - min(v[0] for v in vertices)
    length = max(v[2] for v in vertices) - min(v[2] for v in vertices)
    height = max(v[1] for v in vertices)
    return nv, nf, width, length, height
