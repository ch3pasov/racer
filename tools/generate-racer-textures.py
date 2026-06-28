#!/usr/bin/env python3
import json
import math
import struct
import zlib
from pathlib import Path

WIDTH = 1024
HEIGHT = 1024
OUT_DIR = Path("assets/racer/textures")
PNG_PATH = OUT_DIR / "racer-sprites-v2.png"
JSON_PATH = OUT_DIR / "racer-sprites-v2.json"

pixels = bytearray(WIDTH * HEIGHT * 4)


def put(x, y, color):
    if x < 0 or x >= WIDTH or y < 0 or y >= HEIGHT:
        return
    offset = (y * WIDTH + x) * 4
    pixels[offset : offset + 4] = bytes(color)


def rect(x, y, w, h, color):
    for yy in range(max(0, y), min(HEIGHT, y + h)):
        row = (yy * WIDTH + max(0, x)) * 4
        for _ in range(max(0, x), min(WIDTH, x + w)):
            pixels[row : row + 4] = bytes(color)
            row += 4


def ellipse(cx, cy, rx, ry, color):
    if rx <= 0 or ry <= 0:
        return
    for y in range(math.floor(cy - ry), math.ceil(cy + ry) + 1):
        dy = (y - cy) / ry
        span = rx * math.sqrt(max(0, 1 - dy * dy))
        for x in range(math.floor(cx - span), math.ceil(cx + span) + 1):
            put(x, y, color)


def polygon(points, color):
    min_y = max(0, math.floor(min(y for _, y in points)))
    max_y = min(HEIGHT - 1, math.ceil(max(y for _, y in points)))
    for y in range(min_y, max_y + 1):
        hits = []
        for index, (x1, y1) in enumerate(points):
            x2, y2 = points[(index + 1) % len(points)]
            if y1 == y2:
                continue
            if (y >= min(y1, y2)) and (y < max(y1, y2)):
                hits.append(x1 + (y - y1) * (x2 - x1) / (y2 - y1))
        hits.sort()
        for left, right in zip(hits[0::2], hits[1::2]):
            rect(math.floor(left), y, math.ceil(right) - math.floor(left), 1, color)


def line(x1, y1, x2, y2, width, color):
    steps = int(max(abs(x2 - x1), abs(y2 - y1), 1))
    radius = max(1, width // 2)
    for step in range(steps + 1):
        t = step / steps
        x = round(x1 + (x2 - x1) * t)
        y = round(y1 + (y2 - y1) * t)
        ellipse(x, y, radius, radius, color)


def color_shift(color, amount):
    return tuple(
        max(0, min(255, channel + amount)) if index < 3 else channel
        for index, channel in enumerate(color)
    )


def inset_rect(x, y, w, h, inset, color):
    rect(round(x + w * inset), round(y + h * inset), round(w * (1 - inset * 2)), round(h * (1 - inset * 2)), color)


def png_write(path):
    def chunk(kind, data):
        return (
            struct.pack(">I", len(data))
            + kind
            + data
            + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)
        )

    raw = bytearray()
    for y in range(HEIGHT):
        raw.append(0)
        start = y * WIDTH * 4
        raw.extend(pixels[start : start + WIDTH * 4])
    data = b"\x89PNG\r\n\x1a\n"
    data += chunk(b"IHDR", struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 6, 0, 0, 0))
    data += chunk(b"IDAT", zlib.compress(bytes(raw), 9))
    data += chunk(b"IEND", b"")
    path.write_bytes(data)


sprites = {}


def sprite(name, x, y, w, h, draw):
	sprites[name] = {"x": x, "y": y, "w": w, "h": h}
	draw(x, y, w, h)


def bounds_of(x, y, w, h):
	min_x = w
	min_y = h
	max_x = -1
	max_y = -1
	for yy in range(y, y + h):
		for xx in range(x, x + w):
			alpha = pixels[(yy * WIDTH + xx) * 4 + 3]
			if alpha == 0:
				continue
			min_x = min(min_x, xx - x)
			min_y = min(min_y, yy - y)
			max_x = max(max_x, xx - x)
			max_y = max(max_y, yy - y)
	return None if max_x < 0 else (min_x, min_y, max_x, max_y)


def shift_sprite_pixels(x, y, w, h, dx, dy):
	source = bytearray(w * h * 4)
	for yy in range(h):
		start = ((y + yy) * WIDTH + x) * 4
		source[yy * w * 4 : (yy + 1) * w * 4] = pixels[start : start + w * 4]
		rect(x, y + yy, w, 1, (0, 0, 0, 0))
	for yy in range(h):
		for xx in range(w):
			source_offset = (yy * w + xx) * 4
			alpha = source[source_offset + 3]
			if alpha == 0:
				continue
			put(x + xx + dx, y + yy + dy, source[source_offset : source_offset + 4])


def align_sprite_to_hitbox(name, bottom_padding=0, side_padding=4):
	rect_data = sprites[name]
	x, y, w, h = rect_data["x"], rect_data["y"], rect_data["w"], rect_data["h"]
	bounds = bounds_of(x, y, w, h)
	if not bounds:
		return
	min_x, _, max_x, max_y = bounds
	content_center = (min_x + max_x) / 2
	dx = round(w / 2 - content_center)
	if min_x + dx < side_padding:
		dx = side_padding - min_x
	if max_x + dx > w - 1 - side_padding:
		dx = w - 1 - side_padding - max_x
	dy = h - 1 - bottom_padding - max_y
	shift_sprite_pixels(x, y, w, h, dx, dy)


def car_draw(base, accent, cabin, turn=0, truck=False, semi=False):
    def draw(x, y, w, h):
        cx = x + w / 2
        body_y = y + h * (0.45 if semi else 0.5)
        body_h = h * (0.32 if not semi else 0.38)
        skew = turn * w * 0.12
        outline = (24, 26, 30, 255)
        shade = color_shift(base, -36)
        light = color_shift(base, 34)
        rect(round(x + w * 0.12), round(y + h * 0.86), round(w * 0.76), round(h * 0.08), (10, 12, 14, 90))
        polygon(
            [
                (x + w * 0.13 + skew, body_y - h * 0.02),
                (x + w * 0.87 + skew, body_y - h * 0.02),
                (x + w * 0.98 - skew, body_y + body_h + h * 0.04),
                (x + w * 0.02 - skew, body_y + body_h + h * 0.04),
            ],
            outline,
        )
        polygon(
            [
                (x + w * 0.17 + skew, body_y),
                (x + w * 0.83 + skew, body_y),
                (x + w * 0.93 - skew, body_y + body_h),
                (x + w * 0.07 - skew, body_y + body_h),
            ],
            base,
        )
        polygon(
            [
                (x + w * 0.17 + skew, body_y),
                (x + w * 0.48 + skew, body_y),
                (x + w * 0.36 - skew, body_y + body_h * 0.85),
                (x + w * 0.08 - skew, body_y + body_h),
            ],
            light,
        )
        polygon(
            [
                (x + w * 0.52 + skew, body_y),
                (x + w * 0.83 + skew, body_y),
                (x + w * 0.93 - skew, body_y + body_h),
                (x + w * 0.65 - skew, body_y + body_h * 0.85),
            ],
            shade,
        )
        if semi:
            rect(round(x + w * 0.24 + skew), round(y + h * 0.16), round(w * 0.52), round(h * 0.36), outline)
            rect(round(x + w * 0.28 + skew), round(y + h * 0.19), round(w * 0.44), round(h * 0.3), base)
            rect(round(x + w * 0.34 + skew), round(y + h * 0.25), round(w * 0.32), round(h * 0.14), cabin)
            rect(round(x + w * 0.38 + skew), round(y + h * 0.27), round(w * 0.1), round(h * 0.04), color_shift(cabin, 52))
        elif truck:
            rect(round(x + w * 0.18 + skew), round(y + h * 0.26), round(w * 0.64), round(h * 0.29), outline)
            rect(round(x + w * 0.22 + skew), round(y + h * 0.29), round(w * 0.56), round(h * 0.23), base)
            rect(round(x + w * 0.3 + skew), round(y + h * 0.33), round(w * 0.4), round(h * 0.11), cabin)
        else:
            polygon(
                [
                    (cx - w * 0.27 + skew, y + h * 0.25),
                    (cx + w * 0.27 + skew, y + h * 0.25),
                    (cx + w * 0.37 + skew * 0.4, y + h * 0.52),
                    (cx - w * 0.37 + skew * 0.4, y + h * 0.52),
                ],
                outline,
            )
            polygon(
                [
                    (cx - w * 0.23 + skew, y + h * 0.28),
                    (cx + w * 0.23 + skew, y + h * 0.28),
                    (cx + w * 0.32 + skew * 0.4, y + h * 0.49),
                    (cx - w * 0.32 + skew * 0.4, y + h * 0.49),
                ],
                base,
            )
            rect(round(cx - w * 0.2 + skew), round(y + h * 0.32), round(w * 0.4), round(h * 0.12), cabin)
            rect(round(cx - w * 0.15 + skew), round(y + h * 0.34), round(w * 0.12), max(2, round(h * 0.035)), color_shift(cabin, 54))
        rect(round(x + w * 0.09), round(y + h * 0.71), round(w * 0.15), round(h * 0.24), outline)
        rect(round(x + w * 0.76), round(y + h * 0.71), round(w * 0.15), round(h * 0.24), outline)
        rect(round(x + w * 0.16), round(y + h * 0.79), round(w * 0.15), round(h * 0.1), accent)
        rect(round(x + w * 0.69), round(y + h * 0.79), round(w * 0.15), round(h * 0.1), accent)
        rect(round(x + w * 0.25), round(y + h * 0.63), round(w * 0.5), max(2, round(h * 0.06)), color_shift(accent, -10))
        rect(round(x + w * 0.43), round(y + h * 0.86), round(w * 0.14), max(2, round(h * 0.04)), outline)

    return draw


def player_car_draw(turn=0, slope="level", people=False):
    yellow = (255, 221, 78, 255)
    yellow_light = (255, 235, 118, 255)
    yellow_shadow = (205, 151, 42, 255)
    glass = (26, 48, 68, 255)
    glass_light = (76, 132, 160, 255)
    tire = (20, 20, 24, 255)
    tire_light = (58, 58, 62, 255)
    brake = (229, 51, 53, 255)
    exhaust = (74, 78, 82, 255)

    def px(x, w, value):
        return round(x + w * value)

    def py(y, h, value):
        return round(y + h * value)

    def draw(x, y, w, h):
        lean = turn * 0.075
        yaw = turn * 0.055
        if slope == "uphill":
            top = 0.22
            cabin_top = 0.16
            cabin_bottom = 0.49
            shoulder = 0.18
        elif slope == "downhill":
            top = 0.34
            cabin_top = 0.28
            cabin_bottom = 0.6
            shoulder = 0.25
        else:
            top = 0.29
            cabin_top = 0.22
            cabin_bottom = 0.55
            shoulder = 0.22
        lower = 0.94

        # Rear wheels, drawn first so the body sits on them and the sprite has a
        # clear contact line with the gameplay rectangle.
        outline = (24, 25, 30, 255)
        left_wheel_x = 0.13 + yaw
        right_wheel_x = 0.74 + yaw
        rect(px(x, w, 0.12), py(y, h, 0.93), round(w * 0.76), max(2, round(h * 0.04)), (10, 12, 14, 95))
        rect(px(x, w, left_wheel_x), py(y, h, 0.69), round(w * 0.16), round(h * 0.27), tire)
        rect(px(x, w, right_wheel_x), py(y, h, 0.69), round(w * 0.16), round(h * 0.27), tire)
        rect(px(x, w, left_wheel_x + 0.035), py(y, h, 0.76), round(w * 0.09), round(h * 0.12), tire_light)
        rect(px(x, w, right_wheel_x + 0.035), py(y, h, 0.76), round(w * 0.09), round(h * 0.12), tire_light)

        body = [
            (x + w * (0.22 + lean), y + h * top),
            (x + w * (0.78 + lean), y + h * top),
            (x + w * (0.92 - yaw), y + h * 0.72),
            (x + w * (0.82 - yaw), y + h * lower),
            (x + w * (0.18 - yaw), y + h * lower),
            (x + w * (0.08 - yaw), y + h * 0.72),
        ]
        outline_body = [
            (x + w * (0.2 + lean), y + h * (top - 0.025)),
            (x + w * (0.8 + lean), y + h * (top - 0.025)),
            (x + w * (0.96 - yaw), y + h * 0.73),
            (x + w * (0.84 - yaw), y + h * 0.97),
            (x + w * (0.16 - yaw), y + h * 0.97),
            (x + w * (0.04 - yaw), y + h * 0.73),
        ]
        polygon(outline_body, outline)
        polygon(body, yellow)

        rear_panel = [
            (x + w * (0.19 - yaw), y + h * 0.62),
            (x + w * (0.81 - yaw), y + h * 0.62),
            (x + w * (0.76 - yaw), y + h * 0.86),
            (x + w * (0.24 - yaw), y + h * 0.86),
        ]
        polygon(rear_panel, yellow_shadow)

        cabin = [
            (x + w * (0.34 + lean), y + h * cabin_top),
            (x + w * (0.66 + lean), y + h * cabin_top),
            (x + w * (0.73 + lean * 0.45), y + h * cabin_bottom),
            (x + w * (0.27 + lean * 0.45), y + h * cabin_bottom),
        ]
        polygon(
            [
                (x + w * (0.31 + lean), y + h * (cabin_top - 0.025)),
                (x + w * (0.69 + lean), y + h * (cabin_top - 0.025)),
                (x + w * (0.76 + lean * 0.45), y + h * (cabin_bottom + 0.025)),
                (x + w * (0.24 + lean * 0.45), y + h * (cabin_bottom + 0.025)),
            ],
            outline,
        )
        polygon(cabin, glass)
        rect(px(x, w, 0.39 + lean), py(y, h, cabin_top + 0.07), round(w * 0.18), max(2, round(h * 0.05)), glass_light)

        if people:
            head_y = cabin_top + 0.09
            ellipse(x + w * (0.42 + lean * 0.8), y + h * head_y, w * 0.055, h * 0.07, (228, 177, 132, 255))
            ellipse(x + w * (0.58 + lean * 0.8), y + h * (head_y + 0.005), w * 0.055, h * 0.07, (156, 112, 82, 255))
            rect(px(x, w, 0.38 + lean), py(y, h, head_y + 0.05), round(w * 0.09), round(h * 0.1), (34, 86, 150, 255))
            rect(px(x, w, 0.53 + lean), py(y, h, head_y + 0.055), round(w * 0.09), round(h * 0.1), (120, 62, 150, 255))

        polygon(
            [
                (x + w * (0.16 - yaw), y + h * 0.66),
                (x + w * (0.3 - yaw), y + h * shoulder),
                (x + w * (0.36 - yaw), y + h * 0.64),
            ],
            yellow_light,
        )
        polygon(
            [
                (x + w * (0.84 - yaw), y + h * 0.66),
                (x + w * (0.7 - yaw), y + h * shoulder),
                (x + w * (0.64 - yaw), y + h * 0.64),
            ],
            yellow_shadow,
        )

        rect(px(x, w, 0.26 - yaw), py(y, h, 0.74), round(w * 0.12), round(h * 0.08), brake)
        rect(px(x, w, 0.62 - yaw), py(y, h, 0.74), round(w * 0.12), round(h * 0.08), brake)
        rect(px(x, w, 0.32 - yaw), py(y, h, 0.64), round(w * 0.36), max(2, round(h * 0.035)), yellow_light)
        rect(px(x, w, 0.28 - yaw), py(y, h, 0.86), round(w * 0.44), max(2, round(h * 0.035)), yellow_shadow)
        rect(px(x, w, 0.44 - yaw), py(y, h, 0.82), round(w * 0.12), max(2, round(h * 0.04)), exhaust)
        rect(px(x, w, 0.46 - yaw), py(y, h, 0.9), round(w * 0.08), max(2, round(h * 0.04)), tire)

        if turn:
            inner = 0.2 if turn > 0 else 0.67
            outer = 0.67 if turn > 0 else 0.2
            rect(px(x, w, inner - yaw), py(y, h, 0.86), round(w * 0.18), round(h * 0.05), yellow_light)
            rect(px(x, w, outer - yaw), py(y, h, 0.86), round(w * 0.14), round(h * 0.05), yellow_shadow)

    return draw


def tree_draw(leaf, trunk, palm=False, dead=False):
    def draw(x, y, w, h):
        leaf_dark = color_shift(leaf, -34)
        leaf_light = color_shift(leaf, 32)
        trunk_dark = color_shift(trunk, -28)
        trunk_light = color_shift(trunk, 24)
        if palm:
            ellipse(x + w * 0.5, y + h * 0.97, w * 0.22, h * 0.045, (9, 12, 10, 90))
            line(x + w * 0.5, y + h * 0.95, x + w * 0.55, y + h * 0.22, max(3, w // 12), trunk)
            line(x + w * 0.47, y + h * 0.92, x + w * 0.52, y + h * 0.28, max(2, w // 22), trunk_light)
            for angle in [-70, -40, -10, 25, 55, 90]:
                rad = math.radians(angle)
                line(
                    x + w * 0.54,
                    y + h * 0.24,
                    x + w * (0.54 + math.cos(rad) * 0.42),
                    y + h * (0.24 + math.sin(rad) * 0.24),
                    max(3, w // 16),
                    leaf,
                )
            for angle in [-54, -20, 42, 76]:
                rad = math.radians(angle)
                line(
                    x + w * 0.54,
                    y + h * 0.24,
                    x + w * (0.54 + math.cos(rad) * 0.3),
                    y + h * (0.24 + math.sin(rad) * 0.18),
                    max(2, w // 24),
                    leaf_light,
                )
        elif dead:
            line(x + w * 0.5, y + h * 0.95, x + w * 0.48, y + h * 0.2, max(3, w // 12), trunk)
            line(x + w * 0.54, y + h * 0.9, x + w * 0.51, y + h * 0.23, max(2, w // 20), trunk_dark)
            for sx, sy, ex, ey in [(0.48, 0.45, 0.25, 0.28), (0.5, 0.58, 0.75, 0.42), (0.49, 0.32, 0.62, 0.18)]:
                line(x + w * sx, y + h * sy, x + w * ex, y + h * ey, max(2, w // 20), trunk)
        else:
            ellipse(x + w * 0.5, y + h * 0.94, w * 0.28, h * 0.05, (9, 12, 10, 90))
            rect(round(x + w * 0.44), round(y + h * 0.5), round(w * 0.12), round(h * 0.42), trunk)
            rect(round(x + w * 0.51), round(y + h * 0.52), round(w * 0.035), round(h * 0.36), trunk_dark)
            rect(round(x + w * 0.46), round(y + h * 0.53), round(w * 0.03), round(h * 0.3), trunk_light)
            ellipse(x + w * 0.5, y + h * 0.36, w * 0.4, h * 0.31, leaf_dark)
            ellipse(x + w * 0.5, y + h * 0.34, w * 0.36, h * 0.28, leaf)
            ellipse(x + w * 0.35, y + h * 0.46, w * 0.26, h * 0.2, leaf)
            ellipse(x + w * 0.66, y + h * 0.48, w * 0.25, h * 0.18, leaf)
            ellipse(x + w * 0.42, y + h * 0.27, w * 0.14, h * 0.09, leaf_light)
            ellipse(x + w * 0.62, y + h * 0.34, w * 0.12, h * 0.08, leaf_light)

    return draw


def billboard_draw(color, accent):
    def draw(x, y, w, h):
        frame = (34, 39, 45, 255)
        rect(round(x + w * 0.06), round(y + h * 0.16), round(w * 0.88), round(h * 0.58), frame)
        rect(round(x + w * 0.08), round(y + h * 0.18), round(w * 0.84), round(h * 0.54), color)
        inset_rect(x + w * 0.08, y + h * 0.18, w * 0.84, h * 0.54, 0.04, color_shift(color, 18))
        rect(round(x + w * 0.12), round(y + h * 0.24), round(w * 0.76), round(h * 0.1), accent)
        rect(round(x + w * 0.16), round(y + h * 0.38), round(w * 0.3), round(h * 0.055), color_shift(accent, -30))
        rect(round(x + w * 0.54), round(y + h * 0.57), round(w * 0.26), round(h * 0.05), color_shift(accent, -18))
        ellipse(x + w * 0.32, y + h * 0.5, w * 0.12, h * 0.12, accent)
        polygon(
            [
                (x + w * 0.52, y + h * 0.42),
                (x + w * 0.78, y + h * 0.3),
                (x + w * 0.74, y + h * 0.62),
            ],
            accent,
        )
        rect(round(x + w * 0.22), round(y + h * 0.72), round(w * 0.08), round(h * 0.2), frame)
        rect(round(x + w * 0.7), round(y + h * 0.72), round(w * 0.08), round(h * 0.2), frame)

    return draw


def rock_draw(color):
    def draw(x, y, w, h):
        dark = color_shift(color, -28)
        light = color_shift(color, 28)
        polygon(
            [
                (x + w * 0.12, y + h * 0.78),
                (x + w * 0.24, y + h * 0.4),
                (x + w * 0.48, y + h * 0.26),
                (x + w * 0.78, y + h * 0.36),
                (x + w * 0.92, y + h * 0.78),
            ],
            dark,
        )
        polygon(
            [
                (x + w * 0.16, y + h * 0.76),
                (x + w * 0.27, y + h * 0.43),
                (x + w * 0.49, y + h * 0.3),
                (x + w * 0.75, y + h * 0.39),
                (x + w * 0.88, y + h * 0.76),
            ],
            color,
        )
        polygon(
            [
                (x + w * 0.48, y + h * 0.26),
                (x + w * 0.78, y + h * 0.36),
                (x + w * 0.62, y + h * 0.62),
            ],
            light,
        )
        line(x + w * 0.26, y + h * 0.62, x + w * 0.43, y + h * 0.5, 2, dark)

    return draw


def bush_draw(color):
    def draw(x, y, w, h):
        dark = color_shift(color, -28)
        light = color_shift(color, 28)
        ellipse(x + w * 0.5, y + h * 0.78, w * 0.38, h * 0.06, (9, 12, 10, 80))
        ellipse(x + w * 0.28, y + h * 0.65, w * 0.23, h * 0.22, dark)
        ellipse(x + w * 0.72, y + h * 0.67, w * 0.23, h * 0.2, dark)
        ellipse(x + w * 0.28, y + h * 0.62, w * 0.2, h * 0.2, color)
        ellipse(x + w * 0.5, y + h * 0.52, w * 0.28, h * 0.26, color)
        ellipse(x + w * 0.72, y + h * 0.64, w * 0.2, h * 0.18, color)
        ellipse(x + w * 0.45, y + h * 0.45, w * 0.12, h * 0.09, light)

    return draw


def cactus_draw(x, y, w, h):
    green = (34, 151, 86, 255)
    dark = color_shift(green, -28)
    light = color_shift(green, 35)
    ellipse(x + w * 0.5, y + h * 0.87, w * 0.28, h * 0.045, (9, 12, 10, 80))
    rect(round(x + w * 0.44), round(y + h * 0.22), round(w * 0.14), round(h * 0.62), green)
    rect(round(x + w * 0.53), round(y + h * 0.26), round(w * 0.03), round(h * 0.54), dark)
    rect(round(x + w * 0.46), round(y + h * 0.27), round(w * 0.025), round(h * 0.48), light)
    rect(round(x + w * 0.24), round(y + h * 0.44), round(w * 0.14), round(h * 0.28), green)
    rect(round(x + w * 0.62), round(y + h * 0.36), round(w * 0.14), round(h * 0.32), green)
    ellipse(x + w * 0.51, y + h * 0.22, w * 0.07, h * 0.08, green)


def stump_draw(x, y, w, h):
    rect(round(x + w * 0.3), round(y + h * 0.72), round(w * 0.4), round(h * 0.08), (9, 12, 10, 80))
    rect(round(x + w * 0.32), round(y + h * 0.35), round(w * 0.36), round(h * 0.45), (126, 88, 56, 255))
    rect(round(x + w * 0.56), round(y + h * 0.4), round(w * 0.08), round(h * 0.34), (92, 62, 42, 255))
    ellipse(x + w * 0.5, y + h * 0.35, w * 0.18, h * 0.1, (168, 120, 78, 255))
    line(x + w * 0.35, y + h * 0.5, x + w * 0.65, y + h * 0.44, 2, (92, 62, 42, 255))


def column_draw(x, y, w, h):
    stone = (222, 218, 198, 255)
    shade = (184, 180, 164, 255)
    rect(round(x + w * 0.23), round(y + h * 0.88), round(w * 0.54), round(h * 0.04), (9, 12, 10, 70))
    rect(round(x + w * 0.28), round(y + h * 0.18), round(w * 0.44), round(h * 0.12), stone)
    rect(round(x + w * 0.34), round(y + h * 0.3), round(w * 0.32), round(h * 0.5), stone)
    rect(round(x + w * 0.39), round(y + h * 0.32), round(w * 0.04), round(h * 0.44), color_shift(stone, 18))
    rect(round(x + w * 0.24), round(y + h * 0.8), round(w * 0.52), round(h * 0.1), stone)
    rect(round(x + w * 0.58), round(y + h * 0.3), round(w * 0.08), round(h * 0.5), shade)


def atlas():
    colors = {
        "red": (226, 72, 72, 255),
        "yellow": (255, 218, 71, 255),
        "blue": (78, 158, 231, 255),
        "green": (84, 210, 142, 255),
        "orange": (238, 126, 66, 255),
        "white": (236, 236, 230, 255),
        "glass": (32, 55, 74, 255),
        "light": (250, 246, 210, 255),
    }
    cell = 128
    names = [
        ("PLAYER_STRAIGHT", player_car_draw(people=True)),
        ("PLAYER_LEFT", player_car_draw(-1, people=True)),
        ("PLAYER_RIGHT", player_car_draw(1, people=True)),
        ("PLAYER_UPHILL_STRAIGHT", player_car_draw(slope="uphill", people=True)),
        ("PLAYER_UPHILL_LEFT", player_car_draw(-1, slope="uphill", people=True)),
        ("PLAYER_UPHILL_RIGHT", player_car_draw(1, slope="uphill", people=True)),
        ("PLAYER_DOWNHILL_STRAIGHT", player_car_draw(slope="downhill", people=True)),
        ("PLAYER_DOWNHILL_LEFT", player_car_draw(-1, slope="downhill", people=True)),
        ("PLAYER_DOWNHILL_RIGHT", player_car_draw(1, slope="downhill", people=True)),
        ("CAR01", car_draw(colors["red"], colors["light"], colors["glass"])),
        ("CAR02", car_draw(colors["yellow"], colors["light"], colors["glass"])),
        ("CAR03", car_draw(colors["blue"], colors["light"], colors["glass"])),
        ("CAR04", car_draw(colors["green"], colors["light"], colors["glass"])),
        ("TRUCK", car_draw(colors["orange"], colors["light"], colors["glass"], truck=True)),
        ("SEMI", car_draw(colors["white"], colors["light"], colors["glass"], semi=True)),
    ]
    for i, (name, draw) in enumerate(names):
        sprite(name, (i % 8) * cell, (i // 8) * cell, cell, cell, draw)
        align_sprite_to_hitbox(name)

    objects = [
        ("PALM_TREE", tree_draw((31, 125, 39, 255), (128, 92, 52, 255), palm=True)),
        ("TREE1", tree_draw((20, 112, 36, 255), (110, 78, 46, 255))),
        ("TREE2", tree_draw((24, 132, 44, 255), (116, 82, 48, 255))),
        ("DEAD_TREE1", tree_draw((0, 0, 0, 0), (112, 96, 72, 255), dead=True)),
        ("DEAD_TREE2", tree_draw((0, 0, 0, 0), (122, 105, 78, 255), dead=True)),
        ("BUSH1", bush_draw((18, 116, 38, 255))),
        ("BUSH2", bush_draw((26, 140, 44, 255))),
        ("CACTUS", cactus_draw),
        ("STUMP", stump_draw),
        ("BOULDER1", rock_draw((116, 116, 108, 255))),
        ("BOULDER2", rock_draw((132, 132, 124, 255))),
        ("BOULDER3", rock_draw((124, 124, 116, 255))),
        ("COLUMN", column_draw),
    ]
    for i, (name, draw) in enumerate(objects):
        sprite(name, (i % 6) * cell, 256 + (i // 6) * cell, cell, cell, draw)
        align_sprite_to_hitbox(name)

    billboard_colors = [
        ((236, 236, 230, 255), (226, 72, 72, 255)),
        ((108, 221, 205, 255), (255, 213, 75, 255)),
        ((122, 148, 255, 255), (236, 236, 230, 255)),
        ((255, 213, 75, 255), (80, 156, 230, 255)),
        ((226, 72, 72, 255), (236, 236, 230, 255)),
        ((80, 156, 230, 255), (255, 213, 75, 255)),
        ((84, 210, 142, 255), (122, 148, 255, 255)),
        ((250, 225, 96, 255), (238, 126, 66, 255)),
        ((238, 126, 66, 255), (108, 221, 205, 255)),
    ]
    for i, pair in enumerate(billboard_colors, start=1):
        name = f"BILLBOARD{i:02d}"
        sprite(name, ((i - 1) % 3) * 192, 640 + ((i - 1) // 3) * 96, 192, 96, billboard_draw(*pair))
        align_sprite_to_hitbox(name)


OUT_DIR.mkdir(parents=True, exist_ok=True)
atlas()
png_write(PNG_PATH)
JSON_PATH.write_text(json.dumps({"image": PNG_PATH.name, "size": [WIDTH, HEIGHT], "sprites": sprites}, indent=2) + "\n")
print(PNG_PATH)
