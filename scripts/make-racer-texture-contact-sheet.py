#!/usr/bin/env python3
import json
import struct
import sys
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ATLAS = ROOT / "assets/racer/textures/racer-sprites-v3.png"
DEFAULT_META = ROOT / "assets/racer/textures/racer-sprites-v3.json"
DEFAULT_PREFIX = ROOT / "build/racer-player-car-contact-sheet"
PLAYER_NAMES = [
    "PLAYER_LEFT",
    "PLAYER_STRAIGHT",
    "PLAYER_RIGHT",
    "PLAYER_UPHILL_LEFT",
    "PLAYER_UPHILL_STRAIGHT",
    "PLAYER_UPHILL_RIGHT",
]
BACKGROUNDS = ["checker", "light", "dark", "start", "finish"]


def read_png_rgba(path: Path):
    data = path.read_bytes()
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        raise SystemExit(f"{path} is not a PNG")
    offset = 8
    width = height = None
    idat = bytearray()
    while offset < len(data):
        length = struct.unpack(">I", data[offset : offset + 4])[0]
        kind = data[offset + 4 : offset + 8]
        payload = data[offset + 8 : offset + 8 + length]
        offset += 12 + length
        if kind == b"IHDR":
            width, height, bit_depth, color_type, _, _, _ = struct.unpack(">IIBBBBB", payload)
            if bit_depth != 8 or color_type != 6:
                raise SystemExit(f"{path} must be an 8-bit RGBA PNG")
        elif kind == b"IDAT":
            idat.extend(payload)
        elif kind == b"IEND":
            break
    if width is None or height is None:
        raise SystemExit(f"{path} has no PNG header")
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    rows = []
    cursor = 0
    previous = bytearray(stride)
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        for index in range(stride):
            left = row[index - 4] if index >= 4 else 0
            up = previous[index]
            upper_left = previous[index - 4] if index >= 4 else 0
            if filter_type == 1:
                row[index] = (row[index] + left) & 0xFF
            elif filter_type == 2:
                row[index] = (row[index] + up) & 0xFF
            elif filter_type == 3:
                row[index] = (row[index] + ((left + up) // 2)) & 0xFF
            elif filter_type == 4:
                predictor = left + up - upper_left
                distances = (
                    abs(predictor - left),
                    abs(predictor - up),
                    abs(predictor - upper_left),
                )
                row[index] = (row[index] + (left, up, upper_left)[distances.index(min(distances))]) & 0xFF
            elif filter_type != 0:
                raise SystemExit(f"{path} uses unsupported PNG filter {filter_type}")
        previous = row
        rows.append(row)
    return width, height, rows


def write_png(path: Path, width: int, height: int, rows):
    def chunk(kind, payload):
        return (
            struct.pack(">I", len(payload))
            + kind
            + payload
            + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
        )

    raw = bytearray()
    for row in rows:
        raw.append(0)
        raw.extend(row)
    data = b"\x89PNG\r\n\x1a\n"
    data += chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    data += chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


def put(rows, width: int, x: int, y: int, color):
    if not (0 <= x < width and 0 <= y < len(rows)):
        return
    offset = x * 4
    rows[y][offset : offset + 4] = bytes(color)


def background_pixel(kind, x, y, width, height):
    if kind == "checker":
        value = 196 if (x // 8 + y // 8) % 2 == 0 else 145
        return value, value, value, 255
    if kind == "light":
        return 235, 238, 232, 255
    if kind == "dark":
        return 22, 27, 34, 255
    if kind == "start":
        if height - 16 <= y < height - 8:
            return (244, 244, 238, 255) if (x // 16) % 2 == 0 else (32, 34, 38, 255)
        return 83, 87, 91, 255
    if kind == "finish":
        if y >= height - 24:
            return (244, 244, 238, 255) if (x // 8 + y // 8) % 2 == 0 else (28, 30, 34, 255)
        return 68, 72, 77, 255
    raise ValueError(kind)


def composite(rows, width, x, y, pixel):
    alpha = pixel[3]
    if alpha == 0:
        return
    offset = x * 4
    background = rows[y][offset : offset + 4]
    inverse = 255 - alpha
    rows[y][offset : offset + 4] = bytes(
        [
            round((pixel[channel] * alpha + background[channel] * inverse) / 255)
            for channel in range(3)
        ]
        + [255]
    )


def nearest_enlarge(rows, scale):
    source_width = len(rows[0]) // 4
    target_width = source_width * scale
    enlarged = []
    for source_row in rows:
        row = bytearray()
        for x in range(source_width):
            pixel = source_row[x * 4 : x * 4 + 4]
            row.extend(pixel * scale)
        for _ in range(scale):
            enlarged.append(bytearray(row))
    return target_width, len(enlarged), enlarged


def main():
    atlas = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ATLAS
    meta_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_META
    prefix = Path(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_PREFIX
    if len(sys.argv) > 4:
        raise SystemExit("Usage: make-racer-texture-contact-sheet.py [atlas] [metadata] [output-prefix]")

    atlas_width, atlas_height, atlas_rows = read_png_rgba(atlas)
    sprites = json.loads(meta_path.read_text())["sprites"]
    missing = [name for name in PLAYER_NAMES if name not in sprites]
    if missing:
        raise SystemExit(f"missing player sprites in metadata: {missing}")

    padding = 8
    gap = 4
    sprite_width = max(sprites[name]["w"] for name in PLAYER_NAMES)
    sprite_height = max(sprites[name]["h"] for name in PLAYER_NAMES)
    cell_width = sprite_width + padding * 2
    cell_height = sprite_height + padding * 2
    width = len(PLAYER_NAMES) * cell_width + (len(PLAYER_NAMES) + 1) * gap
    height = len(BACKGROUNDS) * cell_height + (len(BACKGROUNDS) + 1) * gap
    rows = [bytearray([10, 12, 16, 255] * width) for _ in range(height)]

    for background_index, background in enumerate(BACKGROUNDS):
        for sprite_index, name in enumerate(PLAYER_NAMES):
            rect = sprites[name]
            sx, sy, sw, sh = rect["x"], rect["y"], rect["w"], rect["h"]
            if sx + sw > atlas_width or sy + sh > atlas_height:
                raise SystemExit(f"{name} rect outside atlas")
            cell_x = gap + sprite_index * (cell_width + gap)
            cell_y = gap + background_index * (cell_height + gap)
            for y in range(cell_height):
                for x in range(cell_width):
                    put(
                        rows,
                        width,
                        cell_x + x,
                        cell_y + y,
                        background_pixel(background, x, y, cell_width, cell_height),
                    )
            target_x = cell_x + (cell_width - sw) // 2
            target_y = cell_y + cell_height - padding - sh
            for y in range(sh):
                source = atlas_rows[sy + y]
                for x in range(sw):
                    composite(
                        rows,
                        width,
                        target_x + x,
                        target_y + y,
                        source[(sx + x) * 4 : (sx + x) * 4 + 4],
                    )

    native_path = Path(f"{prefix}-native.png")
    nearest_path = Path(f"{prefix}-nearest-4x.png")
    write_png(native_path, width, height, rows)
    enlarged_width, enlarged_height, enlarged = nearest_enlarge(rows, 4)
    write_png(nearest_path, enlarged_width, enlarged_height, enlarged)
    print(native_path)
    print(nearest_path)
    print("Columns: " + ", ".join(PLAYER_NAMES))
    print("Rows: " + ", ".join(BACKGROUNDS))


if __name__ == "__main__":
    main()
