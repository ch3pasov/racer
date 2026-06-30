#!/usr/bin/env python3
from pathlib import Path
import json
import struct
import sys
import zlib


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ATLAS = ROOT / "assets/racer/textures/racer-sprites-v3.png"
DEFAULT_META = ROOT / "assets/racer/textures/racer-sprites-v3.json"
DEFAULT_OUT = ROOT / "build/racer-sprites-v3-contact-sheet.png"


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
    for _ in range(height):
        filter_type = raw[cursor]
        cursor += 1
        row = bytearray(raw[cursor : cursor + stride])
        cursor += stride
        if filter_type != 0:
            raise SystemExit(f"{path} must use unfiltered scanlines")
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
    if x < 0 or y < 0 or y >= len(rows) or x >= width:
        return
    offset = x * 4
    rows[y][offset : offset + 4] = bytes(color)


def rect(rows, width: int, x: int, y: int, w: int, h: int, color):
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            put(rows, width, xx, yy, color)


def main():
    atlas = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_ATLAS
    meta_path = Path(sys.argv[2]) if len(sys.argv) > 2 else DEFAULT_META
    out = Path(sys.argv[3]) if len(sys.argv) > 3 else DEFAULT_OUT
    atlas_width, atlas_height, atlas_rows = read_png_rgba(atlas)
    meta = json.loads(meta_path.read_text())
    sprites = meta["sprites"]
    names = list(sprites)
    scale = 2
    columns = 6
    cell_w = max(sprite["w"] for sprite in sprites.values()) * scale + 16
    cell_h = max(sprite["h"] for sprite in sprites.values()) * scale + 24
    gap = 8
    width = columns * cell_w + (columns + 1) * gap
    rows_count = (len(names) + columns - 1) // columns
    height = rows_count * cell_h + (rows_count + 1) * gap
    rows = [bytearray([18, 22, 30, 255] * width) for _ in range(height)]

    for index, name in enumerate(names):
        sprite = sprites[name]
        sx, sy, sw, sh = sprite["x"], sprite["y"], sprite["w"], sprite["h"]
        if sx + sw > atlas_width or sy + sh > atlas_height:
            raise SystemExit(f"{name} rect outside atlas")
        col = index % columns
        row = index // columns
        ox = gap + col * (cell_w + gap)
        oy = gap + row * (cell_h + gap)
        rect(rows, width, ox, oy, cell_w, cell_h, (28, 34, 44, 255))
        target_w = sw * scale
        target_h = sh * scale
        tx = ox + (cell_w - target_w) // 2
        ty = oy + 4
        for yy in range(sh):
            source = atlas_rows[sy + yy]
            for xx in range(sw):
                src = (sx + xx) * 4
                pixel = source[src : src + 4]
                alpha = pixel[3]
                if alpha == 0:
                    continue
                for dy in range(scale):
                    for dx in range(scale):
                        put(rows, width, tx + xx * scale + dx, ty + yy * scale + dy, pixel)
        rect(rows, width, tx, ty + target_h - 1, target_w, 1, (255, 56, 56, 255))

    write_png(out, width, height, rows)
    print(out)


if __name__ == "__main__":
    main()
