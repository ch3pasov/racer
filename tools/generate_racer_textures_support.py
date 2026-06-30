import math
import struct
import zlib


def png_chunk(kind, payload):
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def read_png_rgba(path):
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise RuntimeError(f"{path} is not a PNG")
    offset = 8
    width = height = bit_depth = color_type = None
    palette = None
    transparency = None
    idat = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, _ = struct.unpack(">IIBBBBB", payload)
        elif kind == b"PLTE":
            palette = payload
        elif kind == b"tRNS":
            transparency = payload
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    if width is None or height is None:
        raise RuntimeError(f"{path} has no PNG header")
    if bit_depth != 8 or color_type not in {2, 3, 6}:
        raise RuntimeError(f"{path} must be 8-bit RGB, indexed, or RGBA PNG")

    channels = {2: 3, 3: 1, 6: 4}[color_type]
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    rows = []
    cursor = 0
    previous = bytearray(stride)
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        bpp = channels
        for index in range(len(row)):
            left = row[index - bpp] if index >= bpp else 0
            up = previous[index]
            upper_left = previous[index - bpp] if index >= bpp else 0
            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + up) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                p = left + up - upper_left
                pa = abs(p - left)
                pb = abs(p - up)
                pc = abs(p - upper_left)
                predictor = left if pa <= pb and pa <= pc else up if pb <= pc else upper_left
                row[index] = (row[index] + predictor) & 0xFF
            elif filter_type != 0:
                raise RuntimeError(f"{path} uses unsupported PNG filter {filter_type}")
        previous = row
        if color_type == 6:
            rows.append(row)
        elif color_type == 2:
            rgba = bytearray()
            for x in range(width):
                rgba.extend(row[x * 3 : x * 3 + 3])
                rgba.append(255)
            rows.append(rgba)
        else:
            if palette is None:
                raise RuntimeError(f"{path} indexed PNG has no palette")
            rgba = bytearray()
            for value in row:
                base = value * 3
                rgba.extend(palette[base : base + 3])
                alpha = transparency[value] if transparency and value < len(transparency) else 255
                rgba.append(alpha)
            rows.append(rgba)
    return width, height, rows


def write_png(path, width, height, rows):
    raw = bytearray()
    for row in rows:
        raw.append(0)
        raw.extend(row)
    data = b"\x89PNG\r\n\x1a\n"
    data += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    data += png_chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    data += png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def pixel(rows, x, y):
    return rows[y][x * 4 : x * 4 + 4]


def remove_chroma(rows, key=None):
    if key is None:
        width = len(rows[0]) // 4
        corners = [pixel(rows, 0, 0), pixel(rows, width - 1, 0), pixel(rows, 0, len(rows) - 1)]
        key = max(corners, key=lambda color: color[1] + color[0] + color[2])[:3]
    for row in rows:
        for x in range(len(row) // 4):
            offset = x * 4
            r, g, b, a = row[offset : offset + 4]
            distance = math.sqrt((r - key[0]) ** 2 + (g - key[1]) ** 2 + (b - key[2]) ** 2)
            transparent_threshold = 90 if key == (255, 0, 255) else 42
            soft_threshold = 180 if key == (255, 0, 255) else 82
            if distance < transparent_threshold:
                row[offset : offset + 4] = b"\x00\x00\x00\x00"
            elif distance < soft_threshold:
                row[offset + 3] = max(
                    0,
                    min(a, round((distance - transparent_threshold) / (soft_threshold - transparent_threshold) * 255)),
                )
    return rows
