#!/usr/bin/env python3
import json
import math
import re
import struct
import zlib
from pathlib import Path


WIDTH = 2048
HEIGHT = 2048
OUT_DIR = Path("assets/racer/textures")
SOURCE_DIR = OUT_DIR / "v3-sources"
PNG_PATH = OUT_DIR / "racer-sprites-v3.png"
JSON_PATH = OUT_DIR / "racer-sprites-v3.json"
TEXTURES_LUA = Path("src/racer/shared/RacerTextures.lua")

SPRITE_DIMENSIONS = {
    "PLAYER_STRAIGHT": (80, 41),
    "PLAYER_LEFT": (80, 41),
    "PLAYER_RIGHT": (80, 41),
    "PLAYER_UPHILL_STRAIGHT": (80, 45),
    "PLAYER_UPHILL_LEFT": (80, 45),
    "PLAYER_UPHILL_RIGHT": (80, 45),
    "PLAYER_DOWNHILL_STRAIGHT": (80, 41),
    "PLAYER_DOWNHILL_LEFT": (80, 41),
    "PLAYER_DOWNHILL_RIGHT": (80, 41),
    "CAR01": (80, 56),
    "CAR02": (80, 59),
    "CAR03": (88, 55),
    "CAR04": (80, 57),
    "TRUCK": (100, 78),
    "SEMI": (122, 144),
    "PALM_TREE": (215, 540),
    "TREE1": (360, 360),
    "TREE2": (282, 295),
    "DEAD_TREE1": (135, 332),
    "DEAD_TREE2": (150, 260),
    "BUSH1": (240, 155),
    "BUSH2": (232, 152),
    "CACTUS": (235, 118),
    "STUMP": (195, 140),
    "BOULDER1": (168, 248),
    "BOULDER2": (298, 140),
    "BOULDER3": (320, 220),
    "COLUMN": (200, 315),
    "BILLBOARD01": (300, 170),
    "BILLBOARD02": (215, 220),
    "BILLBOARD03": (230, 220),
    "BILLBOARD04": (268, 170),
    "BILLBOARD05": (298, 190),
    "BILLBOARD06": (298, 190),
    "BILLBOARD07": (298, 190),
    "BILLBOARD08": (385, 265),
    "BILLBOARD09": (328, 282),
}


def texture_scale(name):
    if name.startswith("PLAYER_"):
        return 2.5
    if name in {"CAR01", "CAR02", "CAR03", "CAR04", "TRUCK", "SEMI"}:
        return 2.5
    if name.startswith("BILLBOARD"):
        return 1.5
    if name in {"PALM_TREE", "TREE1", "TREE2"}:
        return 1.25
    if name in {"DEAD_TREE1", "DEAD_TREE2", "COLUMN"}:
        return 1.35
    return 1.45


def texture_dimensions(name):
    base_w, base_h = SPRITE_DIMENSIONS[name]
    scale = texture_scale(name)
    return max(1, round(base_w * scale)), max(1, round(base_h * scale))


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


def blank(width, height):
    return [bytearray([0, 0, 0, 0] * width) for _ in range(height)]


def pixel(rows, x, y):
    offset = x * 4
    return rows[y][offset : offset + 4]


def put(rows, width, x, y, value):
    if x < 0 or y < 0 or y >= len(rows) or x >= width:
        return
    offset = x * 4
    rows[y][offset : offset + 4] = bytes(value)


def remove_chroma(rows, key=None):
    if key is None:
        corners = [pixel(rows, 0, 0), pixel(rows, len(rows[0]) // 4 - 1, 0), pixel(rows, 0, len(rows) - 1)]
        key = max(corners, key=lambda color: color[1] + color[0] + color[2])[:3]
    for y, row in enumerate(rows):
        for x in range(len(row) // 4):
            offset = x * 4
            r, g, b, a = row[offset : offset + 4]
            distance = math.sqrt((r - key[0]) ** 2 + (g - key[1]) ** 2 + (b - key[2]) ** 2)
            if distance < 42:
                row[offset : offset + 4] = b"\x00\x00\x00\x00"
            elif distance < 82:
                alpha = max(0, min(a, round((distance - 42) / 40 * 255)))
                row[offset + 3] = alpha
    return rows


def alpha_bounds(rows):
    width = len(rows[0]) // 4
    min_x = width
    min_y = len(rows)
    max_x = -1
    max_y = -1
    for y, row in enumerate(rows):
        for x in range(width):
            if row[x * 4 + 3] == 0:
                continue
            min_x = min(min_x, x)
            min_y = min(min_y, y)
            max_x = max(max_x, x)
            max_y = max(max_y, y)
    return None if max_x < 0 else (min_x, min_y, max_x, max_y)


def crop(rows, bounds):
    min_x, min_y, max_x, max_y = bounds
    width = max_x - min_x + 1
    cropped = []
    for y in range(min_y, max_y + 1):
        row = bytearray()
        for x in range(min_x, max_x + 1):
            row.extend(pixel(rows, x, y))
        cropped.append(row)
    return width, max_y - min_y + 1, cropped


def sample_bilinear(rows, source_w, source_h, x, y):
    x = max(0.0, min(source_w - 1.0, x))
    y = max(0.0, min(source_h - 1.0, y))
    x0 = math.floor(x)
    y0 = math.floor(y)
    x1 = min(source_w - 1, x0 + 1)
    y1 = min(source_h - 1, y0 + 1)
    tx = x - x0
    ty = y - y0
    channels = []
    for channel in range(4):
        c00 = rows[y0][x0 * 4 + channel]
        c10 = rows[y0][x1 * 4 + channel]
        c01 = rows[y1][x0 * 4 + channel]
        c11 = rows[y1][x1 * 4 + channel]
        channels.append(round((c00 * (1 - tx) + c10 * tx) * (1 - ty) + (c01 * (1 - tx) + c11 * tx) * ty))
    return channels


def fit_to_rect(rows, target_w, target_h):
    bounds = alpha_bounds(rows)
    if not bounds:
        raise RuntimeError("source sprite has no visible pixels")
    source_w, source_h, cropped = crop(rows, bounds)
    scale = min(target_w / source_w, target_h / source_h)
    draw_w = max(1, round(source_w * scale))
    draw_h = max(1, round(source_h * scale))
    out = blank(target_w, target_h)
    offset_x = (target_w - draw_w) // 2
    offset_y = target_h - draw_h
    for y in range(draw_h):
        sy = (y + 0.5) / scale - 0.5
        for x in range(draw_w):
            sx = (x + 0.5) / scale - 0.5
            value = sample_bilinear(cropped, source_w, source_h, sx, sy)
            if value[3] > 0:
                put(out, target_w, offset_x + x, offset_y + y, value)
    return out


def pack_sprites(names, padding=16):
    free_rects = [(padding, padding, WIDTH - padding * 2, HEIGHT - padding * 2)]
    packed = {}
    entries = sorted(names, key=lambda name: texture_dimensions(name)[0] * texture_dimensions(name)[1], reverse=True)

    def contains(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return bx >= ax and by >= ay and bx + bw <= ax + aw and by + bh <= ay + ah

    def intersects(a, b):
        ax, ay, aw, ah = a
        bx, by, bw, bh = b
        return ax < bx + bw and ax + aw > bx and ay < by + bh and ay + ah > by

    def split_free_rects(used):
        nonlocal free_rects
        next_free = []
        ux, uy, uw, uh = used
        for rect_data in free_rects:
            fx, fy, fw, fh = rect_data
            if not intersects(rect_data, used):
                next_free.append(rect_data)
                continue
            if ux > fx:
                next_free.append((fx, fy, ux - fx, fh))
            if ux + uw < fx + fw:
                next_free.append((ux + uw, fy, fx + fw - (ux + uw), fh))
            if uy > fy:
                next_free.append((fx, fy, fw, uy - fy))
            if uy + uh < fy + fh:
                next_free.append((fx, uy + uh, fw, fy + fh - (uy + uh)))
        pruned = []
        for rect_data in next_free:
            if rect_data[2] <= 0 or rect_data[3] <= 0:
                continue
            if any(rect_data != other and contains(other, rect_data) for other in next_free):
                continue
            pruned.append(rect_data)
        free_rects = sorted(pruned, key=lambda rect_data: (rect_data[1], rect_data[0]))

    for name in entries:
        w, h = texture_dimensions(name)
        allocation = (w + padding, h + padding)
        candidates = [rect_data for rect_data in free_rects if allocation[0] <= rect_data[2] and allocation[1] <= rect_data[3]]
        if not candidates:
            raise RuntimeError(f"{name} does not fit in {WIDTH}x{HEIGHT} atlas")
        best = min(candidates, key=lambda rect_data: (rect_data[1] + allocation[1], rect_data[0] + allocation[0], rect_data[2] * rect_data[3]))
        x, y, _, _ = best
        packed[name] = {"x": x, "y": y, "w": w, "h": h}
        split_free_rects((x, y, allocation[0], allocation[1]))
    return packed


def paste(atlas_rows, rect_data, sprite_rows):
    for y, row in enumerate(sprite_rows):
        for x in range(rect_data["w"]):
            value = row[x * 4 : x * 4 + 4]
            if value[3] > 0:
                put(atlas_rows, WIDTH, rect_data["x"] + x, rect_data["y"] + y, value)


def alpha_points(rows):
    width = len(rows[0]) // 4
    points = []
    for y, row in enumerate(rows):
        for x in range(width):
            alpha = row[x * 4 + 3]
            if alpha > 0:
                points.append((x, y, alpha))
    return points


def validate_sprite(name, rows):
    width = len(rows[0]) // 4
    height = len(rows)
    points = alpha_points(rows)
    if not points:
        raise RuntimeError(f"{name} has no visible pixels")
    bottom_alpha = sum(1 for x in range(width) if rows[height - 1][x * 4 + 3] > 0)
    if bottom_alpha == 0:
        raise RuntimeError(f"{name} must touch the bottom edge")
    coverage = len(points) / (width * height)
    if coverage < 0.012:
        raise RuntimeError(f"{name} visible coverage is too low: {coverage:.3f}")


def validate_palm(rows):
    width = len(rows[0]) // 4
    height = len(rows)
    points = alpha_points(rows)
    top = [(x, alpha) for x, y, alpha in points if y < height * 0.42]
    lower = [(x, alpha) for x, y, alpha in points if y > height * 0.55]
    if not top or not lower:
        raise RuntimeError("PALM_TREE needs visible crown and trunk pixels")
    top_center = sum(x * alpha for x, alpha in top) / sum(alpha for _, alpha in top)
    lower_center = sum(x * alpha for x, alpha in lower) / sum(alpha for _, alpha in lower)
    left_crown = sum(alpha for x, alpha in top if x < width * 0.5)
    right_crown = sum(alpha for x, alpha in top if x >= width * 0.5)
    if not (top_center < lower_center - width * 0.06 and left_crown > right_crown * 1.08):
        raise RuntimeError(
            f"PALM_TREE must read right-to-left: top={top_center:.1f} lower={lower_center:.1f} left={left_crown} right={right_crown}"
        )


def read_source_sprite(name):
    path = SOURCE_DIR / f"{name}.png"
    if not path.exists():
        raise RuntimeError(f"missing source sprite {path}")
    _, _, rows = read_png_rgba(path)
    key = (0, 255, 0) if name.startswith(("PLAYER_", "CAR", "TRUCK", "SEMI", "BILLBOARD")) else (255, 0, 255)
    rows = remove_chroma(rows, key=key)
    fitted = fit_to_rect(rows, *texture_dimensions(name))
    validate_sprite(name, fitted)
    if name == "PALM_TREE":
        validate_palm(fitted)
    return fitted


def main():
    atlas_rows = blank(WIDTH, HEIGHT)
    sprites = pack_sprites(SPRITE_DIMENSIONS.keys())
    for name in sprites:
        source_rows = read_source_sprite(name)
        paste(atlas_rows, sprites[name], source_rows)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    write_png(PNG_PATH, WIDTH, HEIGHT, atlas_rows)
    JSON_PATH.write_text(json.dumps({"image": PNG_PATH.name, "size": [WIDTH, HEIGHT], "sprites": sprites}, indent=2) + "\n")
    sync_lua(sprites)
    print(PNG_PATH)


def sync_lua(sprites):
    text = TEXTURES_LUA.read_text()
    text = re.sub(r"SheetSize = Vector2\.new\(\d+,\s*\d+\)", f"SheetSize = Vector2.new({WIDTH}, {HEIGHT})", text)
    lines = [
        f"\t\t{name} = {{ x = {rect['x']}, y = {rect['y']}, w = {rect['w']}, h = {rect['h']} }},"
        for name, rect in sprites.items()
    ]
    block = "\n".join(lines)
    text = re.sub(r"\tSprites = \{\n.*?\n\t\},", "\tSprites = {\n" + block + "\n\t},", text, flags=re.S)
    TEXTURES_LUA.write_text(text)


if __name__ == "__main__":
    main()
