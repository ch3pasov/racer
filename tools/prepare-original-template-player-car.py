#!/usr/bin/env python3
import argparse
from pathlib import Path

from generate_racer_textures_support import read_png_rgba, write_png


SOURCE_DIR = Path("assets/racer/textures/v3-sources")
SCALE = 3

SPRITES = {
    "PLAYER_LEFT": ("original-player_left.png", 80, 41, 2),
    "PLAYER_STRAIGHT": ("original-player_straight.png", 80, 41, 0),
    "PLAYER_RIGHT": ("original-player_right.png", 80, 41, -2),
    "PLAYER_UPHILL_LEFT": ("original-player_uphill_left.png", 80, 45, 1),
    "PLAYER_UPHILL_STRAIGHT": ("original-player_uphill_straight.png", 80, 45, 0),
    "PLAYER_UPHILL_RIGHT": ("original-player_uphill_right.png", 80, 45, -2),
}

BODY_PALETTE = {
    (33, 0, 0): (45, 27, 0),
    (66, 0, 0): (91, 53, 0),
    (99, 0, 0): (143, 86, 0),
    (132, 0, 0): (196, 129, 0),
    (165, 0, 0): (239, 177, 0),
    (198, 65, 99): (255, 220, 49),
}

BLACK = (0, 0, 0, 255)
DARK_SEAT = (24, 26, 29, 255)
MID_SEAT = (55, 58, 62, 255)
SEAT_HIGHLIGHT = (91, 94, 99, 255)
PLATE = (165, 162, 165, 255)
PLATE_INSET = (66, 65, 66, 255)
FRAME_DARK = (91, 53, 0, 255)
FRAME_MID = (196, 129, 0, 255)
FRAME_LIGHT = (255, 220, 49, 255)
TRANSPARENT = (0, 0, 0, 0)


def set_pixel(rows, x, y, color):
    if y < 0 or y >= len(rows) or x < 0 or x >= len(rows[0]) // 4:
        return
    rows[y][x * 4 : x * 4 + 4] = bytes(color)


def recolor_body(rows):
    for row in rows:
        for x in range(len(row) // 4):
            offset = x * 4
            rgb = tuple(row[offset : offset + 3])
            replacement = BODY_PALETTE.get(rgb)
            if replacement:
                row[offset : offset + 3] = bytes(replacement)


def clear_rect(rows, x0, y0, x1, y1):
    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            set_pixel(rows, x, y, TRANSPARENT)


def draw_line(rows, x0, y0, x1, y1, color):
    dx = abs(x1 - x0)
    sx = 1 if x0 < x1 else -1
    dy = -abs(y1 - y0)
    sy = 1 if y0 < y1 else -1
    error = dx + dy
    while True:
        set_pixel(rows, x0, y0, color)
        if x0 == x1 and y0 == y1:
            break
        twice_error = 2 * error
        if twice_error >= dy:
            error += dy
            x0 += sx
        if twice_error <= dx:
            error += dx
            y0 += sy


def draw_seat(rows, center_x):
    spans = {
        7: 3,
        8: 4,
        9: 5,
        10: 6,
        11: 7,
        12: 7,
        13: 8,
    }
    for y, radius in spans.items():
        for x in range(center_x - radius, center_x + radius + 1):
            color = BLACK if x in {center_x - radius, center_x + radius} or y in {7, 13} else MID_SEAT
            set_pixel(rows, x, y, color)
    for x in range(center_x - 3, center_x + 4):
        set_pixel(rows, x, 8, SEAT_HIGHLIGHT)
    for x in range(center_x - 5, center_x + 6):
        set_pixel(rows, x, 12, DARK_SEAT)


def draw_blank_plate(rows, uphill):
    if uphill:
        x0, y0, x1, y1 = 33, 37, 47, 41
        emblem_y0, emblem_y1 = 28, 34
    else:
        x0, y0, x1, y1 = 32, 28, 47, 33
        emblem_y0, emblem_y1 = 19, 25

    for y in range(emblem_y0, emblem_y1 + 1):
        for x in range(37, 44):
            set_pixel(rows, x, y, BLACK)

    for y in range(y0, y1 + 1):
        for x in range(x0, x1 + 1):
            border = x in {x0, x1} or y in {y0, y1}
            set_pixel(rows, x, y, PLATE if border else PLATE_INSET)


def empty_cockpit(rows, shift, uphill):
    clear_rect(rows, 14 + shift, 0, 38 + shift, 14)
    clear_rect(rows, 43 + shift, 0, 61 + shift, 14)
    clear_rect(rows, 37 + shift, 3, 43 + shift, 13)

    draw_seat(rows, 28 + shift)
    draw_seat(rows, 52 + shift)

    draw_line(rows, 21 + shift, 1, 59 + shift, 1, FRAME_DARK)
    draw_line(rows, 22 + shift, 2, 58 + shift, 2, FRAME_LIGHT)
    draw_line(rows, 21 + shift, 1, 14 + shift, 13, FRAME_DARK)
    draw_line(rows, 22 + shift, 2, 16 + shift, 13, FRAME_MID)
    draw_line(rows, 59 + shift, 1, 64 + shift, 13, FRAME_DARK)
    draw_line(rows, 58 + shift, 2, 62 + shift, 13, FRAME_MID)
    draw_line(rows, 14 + shift, 13, 64 + shift, 13, FRAME_DARK)

    mirror_y = 5 if uphill else 4
    for y in range(mirror_y, mirror_y + 2):
        for x in range(37 + shift, 43 + shift):
            set_pixel(rows, x, y, PLATE)
    set_pixel(rows, 36 + shift, mirror_y, BLACK)
    set_pixel(rows, 43 + shift, mirror_y, BLACK)


def upscale_nearest(rows, width, height):
    output = [bytearray(width * SCALE * 4) for _ in range(height * SCALE)]
    for y in range(height):
        for x in range(width):
            color = rows[y][x * 4 : x * 4 + 4]
            for yy in range(y * SCALE, (y + 1) * SCALE):
                for xx in range(x * SCALE, (x + 1) * SCALE):
                    output[yy][xx * 4 : xx * 4 + 4] = color
    return output


def prepare(reference_dir, output_dir):
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, (filename, expected_width, expected_height, shift) in SPRITES.items():
        source_path = reference_dir / filename
        width, height, rows = read_png_rgba(source_path)
        if (width, height) != (expected_width, expected_height):
            raise RuntimeError(f"{source_path} must be {expected_width}x{expected_height}, got {width}x{height}")
        recolor_body(rows)
        uphill = name.startswith("PLAYER_UPHILL_")
        empty_cockpit(rows, shift, uphill)
        draw_blank_plate(rows, uphill)
        scaled = upscale_nearest(rows, width, height)
        output_path = output_dir / f"{name}.png"
        write_png(output_path, width * SCALE, height * SCALE, scaled)
        print(output_path)


def main():
    parser = argparse.ArgumentParser(description="Repaint the six player sprites on the original Racer pose templates.")
    parser.add_argument("reference_dir", type=Path, help="Directory containing the six original-player_*.png references")
    parser.add_argument("--output-dir", type=Path, default=SOURCE_DIR)
    args = parser.parse_args()
    prepare(args.reference_dir, args.output_dir)


if __name__ == "__main__":
    main()
