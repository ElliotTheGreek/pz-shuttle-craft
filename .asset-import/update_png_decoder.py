from pathlib import Path

path = Path("tools/preview_model.py")
text = path.read_text(encoding="utf-8")
start = text.index("def read_png_rgba(path):")
end = text.index("def parse_x(path):", start)
replacement = '''def read_png_rgba(path):
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
            pixels[target:target + 4] = line[source:source + 3] + b"\\xff"
    return width, height, pixels

'''
path.write_text(text[:start] + replacement + text[end:], encoding="utf-8")
print("updated RGB/RGBA PNG decoder")
