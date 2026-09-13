"""Shared DirectX .x text-mesh builder.

Project Zomboid loads .x through assimp. The template block mirrors what
vanilla models ship with so the importer never has to guess at layouts.
"""

TEMPLATES = """template ColorRGBA {
 <35ff44e0-6c7c-11cf-8f52-0040333594a3>
 FLOAT red;
 FLOAT green;
 FLOAT blue;
 FLOAT alpha;
}

template ColorRGB {
 <d3e16e81-7835-11cf-8f52-0040333594a3>
 FLOAT red;
 FLOAT green;
 FLOAT blue;
}

template Material {
 <3d82ab4d-62da-11cf-ab39-0020af71e433>
 ColorRGBA faceColor;
 FLOAT power;
 ColorRGB specularColor;
 ColorRGB emissiveColor;
 [...]
}

template TextureFilename {
 <a42790e1-7810-11cf-8f52-0040333594a3>
 STRING filename;
}

template Frame {
 <3d82ab46-62da-11cf-ab39-0020af71e433>
 [...]
}

template Matrix4x4 {
 <f6f23f45-7686-11cf-8f52-0040333594a3>
 array FLOAT matrix[16];
}

template FrameTransformMatrix {
 <f6f23f41-7686-11cf-8f52-0040333594a3>
 Matrix4x4 frameMatrix;
}

template Vector {
 <3d82ab5e-62da-11cf-ab39-0020af71e433>
 FLOAT x;
 FLOAT y;
 FLOAT z;
}

template MeshFace {
 <3d82ab5f-62da-11cf-ab39-0020af71e433>
 DWORD nFaceVertexIndices;
 array DWORD faceVertexIndices[nFaceVertexIndices];
}

template Mesh {
 <3d82ab44-62da-11cf-ab39-0020af71e433>
 DWORD nVertices;
 array Vector vertices[nVertices];
 DWORD nFaces;
 array MeshFace faces[nFaces];
 [...]
}

template MeshNormals {
 <f6f23f43-7686-11cf-8f52-0040333594a3>
 DWORD nNormals;
 array Vector normals[nNormals];
 DWORD nFaceNormals;
 array MeshFace faceNormals[nFaceNormals];
}

template Coords2d {
 <f6f23f44-7686-11cf-8f52-0040333594a3>
 FLOAT u;
 FLOAT v;
}

template MeshTextureCoords {
 <f6f23f40-7686-11cf-8f52-0040333594a3>
 DWORD nTextureCoords;
 array Coords2d textureCoords[nTextureCoords];
}

template MeshMaterialList {
 <f6f23f42-7686-11cf-8f52-0040333594a3>
 DWORD nMaterials;
 DWORD nFaceIndexes;
 array DWORD faceIndexes[nFaceIndexes];
 [Material]
}
"""


def _joinlist(items, fmt):
    """.x separates list entries with ',' and terminates with ';'."""
    return "".join(fmt(v) + ("," if i < len(items) - 1 else ";") + "\n"
                   for i, v in enumerate(items))


class MeshBuilder:
    """Accumulates per-face vertices so UVs and normals stay unshared."""

    def __init__(self, tex_w=256, tex_h=256, up_axis="z"):
        self.verts, self.faces, self.norms, self.uvs = [], [], [], []
        self.tex_w, self.tex_h = tex_w, tex_h
        self.up_axis = up_axis

    # -- coordinate helpers ---------------------------------------------
    def place(self, a, b, c):
        """Model point from (east, north, height)."""
        return (a, b, c) if self.up_axis == "z" else (a, c, b)

    def uv(self, region, fu, fv):
        x0, y0, x1, y1 = region
        return ((x0 + fu * (x1 - x0)) / self.tex_w,
                (y0 + fv * (y1 - y0)) / self.tex_h)

    # -- geometry -------------------------------------------------------
    def quad(self, p0, p1, p2, p3, region, normal, flip_u=False):
        base = len(self.verts)
        for p in (p0, p1, p2, p3):
            self.verts.append(p)
            self.norms.append(normal)
        for (fu, fv) in ((0, 1), (1, 1), (1, 0), (0, 0)):
            self.uvs.append(self.uv(region, 1.0 - fu if flip_u else fu, fv))
        self.faces.append((base, base + 1, base + 2))
        self.faces.append((base, base + 2, base + 3))

    def tri(self, p0, p1, p2, region, normal, uvcoords=None):
        base = len(self.verts)
        for p in (p0, p1, p2):
            self.verts.append(p)
            self.norms.append(normal)
        uvcoords = uvcoords or ((0.5, 0.0), (1.0, 1.0), (0.0, 1.0))
        for (fu, fv) in uvcoords:
            self.uvs.append(self.uv(region, fu, fv))
        self.faces.append((base, base + 1, base + 2))

    def box(self, half, z0, z1, side_regions, top_region=None, bottom_region=None):
        """Axis-aligned box; side_regions is (south, east, north, west)."""
        s, e, n, w = side_regions
        P = self.place
        self.quad(P(-half, -half, z0), P(half, -half, z0),
                  P(half, -half, z1), P(-half, -half, z1), s, P(0, -1, 0))
        self.quad(P(half, -half, z0), P(half, half, z0),
                  P(half, half, z1), P(half, -half, z1), e, P(1, 0, 0))
        self.quad(P(half, half, z0), P(-half, half, z0),
                  P(-half, half, z1), P(half, half, z1), n, P(0, 1, 0))
        self.quad(P(-half, half, z0), P(-half, -half, z0),
                  P(-half, -half, z1), P(-half, half, z1), w, P(-1, 0, 0))
        if top_region:
            self.quad(P(-half, -half, z1), P(half, -half, z1),
                      P(half, half, z1), P(-half, half, z1), top_region, P(0, 0, 1))
        if bottom_region:
            self.quad(P(-half, half, z0), P(half, half, z0),
                      P(half, -half, z0), P(-half, -half, z0),
                      bottom_region, P(0, 0, -1))

    # -- output ---------------------------------------------------------
    def emit(self, path, mesh_name, texture_file, frame_name="Root"):
        """frame_name matters for character models: the vanilla static clothes
        name their Frame and Mesh after the file, and the clothing loader is
        not the same loader world models go through."""
        import math
        n_v, n_f = len(self.verts), len(self.faces)
        out = ["xof 0303txt 0032", "", TEMPLATES, f"Frame {frame_name} {{",
               " FrameTransformMatrix {",
               "  1.000000,0.000000,0.000000,0.000000,",
               "  0.000000,1.000000,0.000000,0.000000,",
               "  0.000000,0.000000,1.000000,0.000000,",
               "  0.000000,0.000000,0.000000,1.000000;;",
               " }",
               f" Mesh {mesh_name} {{",
               f"  {n_v};"]
        out.append(_joinlist(self.verts, lambda v: "  %.6f;%.6f;%.6f;" % v).rstrip("\n"))
        out.append(f"  {n_f};")
        out.append(_joinlist(self.faces, lambda f: "  3;%d,%d,%d;" % f).rstrip("\n"))
        out.append("  MeshNormals {")
        out.append(f"   {n_v};")
        out.append(_joinlist(self.norms, lambda v: "   %.6f;%.6f;%.6f;" % v).rstrip("\n"))
        out.append(f"   {n_f};")
        out.append(_joinlist(self.faces, lambda f: "   3;%d,%d,%d;" % f).rstrip("\n"))
        out.append("  }")
        out.append("  MeshTextureCoords {")
        out.append(f"   {n_v};")
        out.append(_joinlist(self.uvs, lambda v: "   %.6f;%.6f;" % v).rstrip("\n"))
        out.append("  }")
        out.append("  MeshMaterialList {")
        out.append("   1;")
        out.append(f"   {n_f};")
        out.append(_joinlist([0] * n_f, lambda v: "   %d" % v).rstrip("\n"))
        out.append("   Material {")
        out.append("    1.000000;1.000000;1.000000;1.000000;;")
        out.append("    0.000000;")
        out.append("    0.000000;0.000000;0.000000;;")
        out.append("    0.000000;0.000000;0.000000;;")
        out.append("    TextureFilename {")
        out.append(f'     "{texture_file}";')
        out.append("    }")
        out.append("   }")
        out.append("  }")
        out.append(" }")
        out.append("}")
        open(path, "w").write("\n".join(out) + "\n")
        return n_v, n_f
