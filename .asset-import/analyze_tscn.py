import re
import struct
from pathlib import Path

path = Path('.asset-import/candidates/dispatcher_base.tscn')
text = path.read_text(encoding='utf-8')

def byte_array(name):
    match = re.search(r'"%s": PoolByteArray\( (.*?) \)' % name, text, re.S)
    if not match:
        raise SystemExit('missing ' + name)
    return bytes(int(value) for value in match.group(1).split(', '))

vertices = byte_array('array_data')
indices = byte_array('array_index_data')
vertex_count = int(re.search(r'"vertex_count": (\d+)', text).group(1))
index_count = int(re.search(r'"index_count": (\d+)', text).group(1))
format_code = int(re.search(r'"format": (\d+)', text).group(1))
print('format', format_code, hex(format_code))
print('vertices', len(vertices), 'count', vertex_count, 'stride', len(vertices) / vertex_count)
print('indices', len(indices), 'count', index_count, 'stride', len(indices) / index_count)
for stride in (32, 36, 40, 44, 48):
    if len(vertices) % stride == 0:
        print('candidate stride', stride, 'records', len(vertices) // stride)
for offset in range(0, min(48, len(vertices) - 4), 4):
    print(offset, struct.unpack_from('<f', vertices, offset)[0], vertices[offset:offset+4].hex())

# Godot 3 compressed ArrayMesh layout: float32 XYZ, octahedral normal and
# tangent (4 bytes each), then IEEE-754 half-float UV.
uvs = [struct.unpack_from('<ee', vertices, i * 24 + 20) for i in range(vertex_count)]
positions = [struct.unpack_from('<fff', vertices, i * 24) for i in range(vertex_count)]
print('bounds', tuple((min(p[a] for p in positions), max(p[a] for p in positions)) for a in range(3)))
print('uv bounds', tuple((min(uv[a] for uv in uvs), max(uv[a] for uv in uvs)) for a in range(2)))
try:
    from PIL import Image
    with Image.open('.asset-import/candidates/Dispatcher_Blue.png') as image:
        print('texture', image.size, image.mode)
except Exception as error:
    print('texture inspection failed:', error)
