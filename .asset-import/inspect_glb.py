import json
import struct
from pathlib import Path

path = Path("tools/assets/type6_shuttle/type6_shuttle.glb")
data = path.read_bytes()
magic, version, length = struct.unpack_from("<4sII", data, 0)
assert magic == b"glTF" and version == 2 and length == len(data)
offset = 12
chunks = []
while offset < len(data):
    size, kind = struct.unpack_from("<II", data, offset)
    offset += 8
    chunks.append((kind, data[offset:offset + size]))
    offset += size
json_chunk = next(chunk for kind, chunk in chunks if kind == 0x4E4F534A)
doc = json.loads(json_chunk.rstrip(b" \0"))
print("asset", doc.get("asset"))
for key in ("scenes", "nodes", "meshes", "materials", "textures", "images", "accessors", "bufferViews"):
    print(key, len(doc.get(key, [])))
print("\nscenes")
for index, value in enumerate(doc.get("scenes", [])):
    print(index, value)
print("\nnodes")
for index, value in enumerate(doc.get("nodes", [])):
    print(index, value)
print("\nmeshes")
for index, value in enumerate(doc.get("meshes", [])):
    print(index, value)
print("\nmaterials")
for index, value in enumerate(doc.get("materials", [])):
    print(index, value)
print("\ntextures")
for index, value in enumerate(doc.get("textures", [])):
    print(index, value)
print("\nimages")
for index, value in enumerate(doc.get("images", [])):
    print(index, value)
print("\naccessors")
for index, value in enumerate(doc.get("accessors", [])):
    print(index, value)
print("\nbufferViews")
for index, value in enumerate(doc.get("bufferViews", [])):
    print(index, value)
