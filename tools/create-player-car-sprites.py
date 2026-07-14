#!/usr/bin/env python3
"""Create the six definitive Racer player-car source sprites.

The artwork is authored directly on the required source canvases. The atlas
packer is responsible for the only resize that follows.
"""

import math
import struct
import zlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "assets/racer/textures/v3-sources"
WIDTH = 320

TRANSPARENT = (0, 0, 0, 0)
OUTLINE = (16, 17, 22, 255)
TIRE = (20, 21, 26, 255)
TIRE_LIGHT = (53, 55, 61, 255)
INTERIOR = (31, 36, 43, 255)
INTERIOR_LIGHT = (63, 69, 76, 255)
BODY_SHADOW = (137, 88, 0, 255)
BODY_DARK = (196, 132, 0, 255)
BODY = (255, 210, 42, 255)
BODY_LIGHT = (255, 235, 91, 255)
BODY_GLINT = (255, 250, 190, 255)
TAIL_DARK = (112, 20, 14, 255)
TAIL_RED = (224, 45, 29, 255)
TAIL_ORANGE = (255, 112, 36, 255)
TAIL_WHITE = (255, 224, 133, 255)
METAL_DARK = (57, 60, 64, 255)
METAL = (170, 176, 178, 255)
METAL_LIGHT = (236, 239, 232, 255)


def png_chunk(kind, payload):
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


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


def canvas(height):
    return [bytearray(TRANSPARENT * WIDTH) for _ in range(height)]


def put(rows, x, y, color):
    if 0 <= x < WIDTH and 0 <= y < len(rows):
        offset = x * 4
        rows[y][offset : offset + 4] = bytes(color)


def polygon(rows, points, color):
    if len(points) < 3:
        return
    min_y = max(0, math.floor(min(point[1] for point in points)))
    max_y = min(len(rows) - 1, math.ceil(max(point[1] for point in points)))
    for y in range(min_y, max_y + 1):
        sample_y = y + 0.5
        crossings = []
        for index, (x1, y1) in enumerate(points):
            x2, y2 = points[(index + 1) % len(points)]
            if (y1 <= sample_y < y2) or (y2 <= sample_y < y1):
                crossings.append(x1 + (sample_y - y1) * (x2 - x1) / (y2 - y1))
        crossings.sort()
        for index in range(0, len(crossings) - 1, 2):
            start = max(0, math.ceil(crossings[index] - 0.5))
            end = min(WIDTH - 1, math.floor(crossings[index + 1] - 0.5))
            for x in range(start, end + 1):
                put(rows, x, y, color)


def ellipse_points(x1, y1, x2, y2, steps=40):
    center_x = (x1 + x2) / 2
    center_y = (y1 + y2) / 2
    radius_x = (x2 - x1) / 2
    radius_y = (y2 - y1) / 2
    return [
        (
            center_x + math.cos(index * math.tau / steps) * radius_x,
            center_y + math.sin(index * math.tau / steps) * radius_y,
        )
        for index in range(steps)
    ]


def transformed(steer, uphill):
    height = 180 if uphill else 164
    top = 8 if uphill else 12
    bottom = height - 1

    def point(value):
        x, y = value
        if steer == 0:
            return x, y
        vertical = max(0.0, min(1.0, (bottom - y) / (bottom - top)))
        shift = steer * 26 * vertical**1.35
        tilt = steer * (x - WIDTH / 2) * (0.055 if uphill else 0.06)
        # Center the authored left-turn source after the perspective shear. The
        # matching right turn is mirrored from it, preserving equal margins.
        return x + shift + 4, y + tilt

    return point


def draw_shape(rows, point, points, color):
    polygon(rows, [point(value) for value in points], color)


def draw_box(rows, point, x1, y1, x2, y2, color):
    draw_shape(rows, point, [(x1, y1), (x2, y1), (x2, y2), (x1, y2)], color)


def draw_ellipse(rows, point, x1, y1, x2, y2, color, steps=40):
    draw_shape(rows, point, ellipse_points(x1, y1, x2, y2, steps), color)


def draw_wheel(rows, point, x1, y1, x2, bottom):
    draw_ellipse(rows, point, x1, y1, x2, bottom, OUTLINE)
    draw_ellipse(rows, point, x1 + 5, y1 + 6, x2 - 5, bottom + 3, TIRE)
    draw_shape(
        rows,
        point,
        [(x1 + 8, bottom - 9), (x2 - 8, bottom - 9), (x2 - 11, bottom), (x1 + 11, bottom)],
        TIRE,
    )
    draw_box(rows, point, x1 + 8, y1 + 14, x1 + 13, bottom - 8, TIRE_LIGHT)


def draw_lamp_cluster(rows, point, x1, y1, x2, y2, mirror=False):
    draw_box(rows, point, x1 - 3, y1 - 3, x2 + 3, y2 + 3, OUTLINE)
    width = x2 - x1
    split1 = x1 + width * 0.34
    split2 = x1 + width * 0.68
    colors = [TAIL_RED, TAIL_ORANGE, TAIL_WHITE]
    if mirror:
        colors.reverse()
    for left, right, color in zip([x1, split1, split2], [split1, split2, x2], colors):
        draw_box(rows, point, left, y1, right, y2, color)
        draw_box(rows, point, left + 2, y1 + 2, right - 1, y1 + 5, BODY_GLINT)


def draw_car(steer, uphill):
    height = 180 if uphill else 164
    rows = canvas(height)
    point = transformed(steer, uphill)
    bottom = height - 1

    if uphill:
        wheel_top = 126
        body_top = 63
        face_top = 91
        face_bottom = 143
        bumper_top = 137
        cabin_top = 8
        cabin_bottom = 75
        deck_back = 104
    else:
        wheel_top = 107
        body_top = 59
        face_top = 78
        face_bottom = 133
        bumper_top = 127
        cabin_top = 12
        cabin_bottom = 67
        deck_back = 88

    # Only the rear axle is drawn. Each tire overlaps the body so the silhouette
    # remains a single connected component and lands on the source bottom row.
    near_bias = 7 if steer else 0
    draw_wheel(rows, point, 21 - near_bias, wheel_top, 79 + near_bias, bottom)
    draw_wheel(rows, point, 241 - near_bias, wheel_top, 299 + near_bias, bottom)

    body_outline = [
        (43, body_top),
        (23, body_top + 10),
        (9, face_top + 18),
        (5, face_bottom - 2),
        (18, face_bottom + 16),
        (53, face_bottom + 20),
        (267, face_bottom + 20),
        (302, face_bottom + 16),
        (315, face_bottom - 2),
        (311, face_top + 18),
        (297, body_top + 10),
        (277, body_top),
    ]
    draw_shape(rows, point, body_outline, OUTLINE)
    draw_shape(
        rows,
        point,
        [
            (45, body_top + 5),
            (28, body_top + 14),
            (15, face_top + 20),
            (12, face_bottom - 4),
            (24, face_bottom + 10),
            (55, face_bottom + 14),
            (265, face_bottom + 14),
            (296, face_bottom + 10),
            (308, face_bottom - 4),
            (305, face_top + 20),
            (292, body_top + 14),
            (275, body_top + 5),
        ],
        BODY_DARK,
    )

    # Opaque rollbar and cockpit. Dark pixels are interior paint, not alpha.
    draw_shape(
        rows,
        point,
        [
            (65, cabin_bottom + 7),
            (77, cabin_top + 17),
            (92, cabin_top),
            (228, cabin_top),
            (243, cabin_top + 17),
            (255, cabin_bottom + 7),
        ],
        OUTLINE,
    )
    draw_shape(
        rows,
        point,
        [
            (73, cabin_bottom + 4),
            (84, cabin_top + 20),
            (97, cabin_top + 7),
            (223, cabin_top + 7),
            (236, cabin_top + 20),
            (247, cabin_bottom + 4),
        ],
        BODY,
    )
    draw_shape(
        rows,
        point,
        [
            (84, cabin_bottom),
            (94, cabin_top + 23),
            (103, cabin_top + 15),
            (217, cabin_top + 15),
            (226, cabin_top + 23),
            (236, cabin_bottom),
        ],
        INTERIOR,
    )
    draw_shape(
        rows,
        point,
        [(90, cabin_top + 25), (230, cabin_top + 25), (224, cabin_top + 31), (96, cabin_top + 31)],
        INTERIOR_LIGHT,
    )

    seat_top = cabin_top + (34 if uphill else 32)
    seat_bottom = cabin_bottom + 4
    draw_ellipse(rows, point, 99, seat_top, 137, seat_bottom + 10, OUTLINE)
    draw_ellipse(rows, point, 105, seat_top + 5, 132, seat_bottom + 7, INTERIOR_LIGHT)
    draw_ellipse(rows, point, 183, seat_top, 221, seat_bottom + 10, OUTLINE)
    draw_ellipse(rows, point, 188, seat_top + 5, 215, seat_bottom + 7, INTERIOR_LIGHT)
    draw_box(rows, point, 136, cabin_bottom - 8, 184, cabin_bottom + 7, INTERIOR)

    # Mirrors overlap the rollbar/body; there are no floating accessories.
    mirror_y = cabin_bottom - 14
    draw_shape(rows, point, [(56, mirror_y), (72, mirror_y + 3), (76, mirror_y + 12), (55, mirror_y + 13), (48, mirror_y + 8)], OUTLINE)
    draw_shape(rows, point, [(55, mirror_y + 3), (70, mirror_y + 5), (71, mirror_y + 9), (56, mirror_y + 10), (52, mirror_y + 7)], METAL)
    draw_shape(rows, point, [(264, mirror_y + 3), (280, mirror_y), (272, mirror_y + 13), (251, mirror_y + 12), (255, mirror_y + 3)], OUTLINE)
    draw_shape(rows, point, [(265, mirror_y + 5), (279, mirror_y + 3), (274, mirror_y + 9), (258, mirror_y + 10), (257, mirror_y + 6)], METAL)

    # Rear deck changes substantially on uphill frames, creating pitch rather
    # than a scale-only variant.
    draw_shape(
        rows,
        point,
        [(42, body_top + 3), (73, cabin_bottom - 2), (247, cabin_bottom - 2), (278, body_top + 3), (286, deck_back), (34, deck_back)],
        OUTLINE,
    )
    draw_shape(
        rows,
        point,
        [(48, body_top + 8), (78, cabin_bottom + 3), (242, cabin_bottom + 3), (272, body_top + 8), (278, deck_back - 5), (42, deck_back - 5)],
        BODY,
    )
    draw_shape(
        rows,
        point,
        [(61, body_top + 11), (87, cabin_bottom + 8), (233, cabin_bottom + 8), (259, body_top + 11), (267, body_top + 18), (53, body_top + 18)],
        BODY_LIGHT,
    )
    if uphill:
        draw_shape(rows, point, [(53, 80), (267, 80), (278, 98), (42, 98)], BODY_SHADOW)
        draw_shape(rows, point, [(69, 82), (251, 82), (259, 89), (61, 89)], BODY_LIGHT)

    draw_shape(
        rows,
        point,
        [(18, face_top), (302, face_top), (307, face_bottom), (13, face_bottom)],
        OUTLINE,
    )
    draw_shape(
        rows,
        point,
        [(25, face_top + 6), (295, face_top + 6), (299, face_bottom - 6), (21, face_bottom - 6)],
        BODY,
    )
    draw_shape(rows, point, [(29, face_top + 9), (291, face_top + 9), (286, face_top + 17), (34, face_top + 17)], BODY_LIGHT)
    draw_shape(rows, point, [(24, face_bottom - 15), (296, face_bottom - 15), (298, face_bottom - 6), (22, face_bottom - 6)], BODY_SHADOW)

    lamp_y1 = face_top + 19
    lamp_y2 = face_top + 39
    draw_lamp_cluster(rows, point, 36, lamp_y1, 105, lamp_y2)
    draw_lamp_cluster(rows, point, 215, lamp_y1, 284, lamp_y2, mirror=True)

    draw_box(rows, point, 126, face_top + 17, 194, face_top + 44, OUTLINE)
    draw_box(rows, point, 133, face_top + 23, 187, face_top + 39, INTERIOR)
    draw_box(rows, point, 138, face_top + 25, 182, face_top + 28, METAL_DARK)

    draw_box(rows, point, 18, bumper_top - 3, 302, bumper_top + 18, OUTLINE)
    draw_box(rows, point, 25, bumper_top + 2, 295, bumper_top + 12, METAL)
    draw_box(rows, point, 31, bumper_top + 3, 289, bumper_top + 6, METAL_LIGHT)
    draw_box(rows, point, 40, bumper_top + 12, 280, bumper_top + 18, METAL_DARK)
    draw_box(rows, point, 43, bumper_top + 17, 277, face_bottom + 17, OUTLINE)

    # Attached exhaust tips sit below the bumper without becoming fragments.
    exhaust_y = face_bottom + 10
    for x1, x2 in [(131, 151), (154, 174)]:
        draw_box(rows, point, x1 + 6, face_bottom + 4, x2 - 6, exhaust_y + 2, OUTLINE)
        draw_ellipse(rows, point, x1, exhaust_y, x2, exhaust_y + 18, OUTLINE, 24)
        draw_ellipse(rows, point, x1 + 4, exhaust_y + 4, x2 - 4, exhaust_y + 14, METAL_LIGHT, 24)
        draw_ellipse(rows, point, x1 + 7, exhaust_y + 6, x2 - 6, exhaust_y + 13, INTERIOR, 20)

    # Crisp shared highlights echo the NPC palette and remain attached to body.
    draw_shape(rows, point, [(54, body_top + 8), (120, body_top + 4), (118, body_top + 8), (58, body_top + 13)], BODY_GLINT)
    draw_shape(rows, point, [(202, face_top + 8), (276, face_top + 11), (272, face_top + 15), (205, face_top + 12)], BODY_LIGHT)

    return rows


def mirror(rows):
    mirrored = canvas(len(rows))
    for y, row in enumerate(rows):
        for x in range(WIDTH):
            source = x * 4
            target = (WIDTH - 1 - x) * 4
            mirrored[y][target : target + 4] = row[source : source + 4]
    return mirrored


def main():
    normal_left = draw_car(-1, False)
    uphill_left = draw_car(-1, True)
    sprites = {
        "PLAYER_LEFT": normal_left,
        "PLAYER_STRAIGHT": draw_car(0, False),
        "PLAYER_RIGHT": mirror(normal_left),
        "PLAYER_UPHILL_LEFT": uphill_left,
        "PLAYER_UPHILL_STRAIGHT": draw_car(0, True),
        "PLAYER_UPHILL_RIGHT": mirror(uphill_left),
    }
    for name, rows in sprites.items():
        write_png(OUT_DIR / f"{name}.png", WIDTH, len(rows), rows)
    print(f"Wrote {len(sprites)} player-car source sprites to {OUT_DIR}")


if __name__ == "__main__":
    main()
