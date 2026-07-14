#!/usr/bin/env python3
import argparse
from pathlib import Path

from generate_racer_textures_support import read_png_rgba, write_png


SOURCE_DIR = Path("assets/racer/textures/v3-sources")
PAINT_SHEET = Path("assets/racer/textures/v3-sheets/player-car-v4-original-template-generated.png")
SCALE = 4

SPRITES = {
    "PLAYER_LEFT": ("original-player_left.png", 80, 41, 2, 0, 0),
    "PLAYER_STRAIGHT": ("original-player_straight.png", 80, 41, 0, 1, 0),
    "PLAYER_RIGHT": ("original-player_right.png", 80, 41, -2, 2, 0),
    "PLAYER_UPHILL_LEFT": ("original-player_uphill_left.png", 80, 45, 1, 0, 1),
    "PLAYER_UPHILL_STRAIGHT": ("original-player_uphill_straight.png", 80, 45, 0, 1, 1),
    "PLAYER_UPHILL_RIGHT": ("original-player_uphill_right.png", 80, 45, -2, 2, 1),
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


def sample_bilinear(rows, width, height, x, y):
    x = max(0, min(width - 1, x))
    y = max(0, min(height - 1, y))
    x0 = int(x)
    y0 = int(y)
    x1 = min(width - 1, x0 + 1)
    y1 = min(height - 1, y0 + 1)
    tx = x - x0
    ty = y - y0
    result = []
    for channel in range(4):
        c00 = rows[y0][x0 * 4 + channel]
        c10 = rows[y0][x1 * 4 + channel]
        c01 = rows[y1][x0 * 4 + channel]
        c11 = rows[y1][x1 * 4 + channel]
        value = (c00 * (1 - tx) + c10 * tx) * (1 - ty) + (c01 * (1 - tx) + c11 * tx) * ty
        result.append(round(value))
    return result


def extract_paint_cell(sheet_rows, sheet_width, sheet_height, column, row_index):
    x0 = round(column * sheet_width / 3)
    x1 = round((column + 1) * sheet_width / 3)
    y0 = round(row_index * sheet_height / 2)
    y1 = round((row_index + 1) * sheet_height / 2)
    cell_width = x1 - x0
    cell_height = y1 - y0
    points = []
    for local_y in range(cell_height):
        for local_x in range(cell_width):
            offset = (x0 + local_x) * 4
            r, g, b, _ = sheet_rows[y0 + local_y][offset : offset + 4]
            baseline = local_y > cell_height - 30 and r > 90 and r > g * 1.5 and r > b * 1.3
            foreground = r > 48 or g > 58 or b > 72 or (r < 16 and g < 16 and b < 20)
            if foreground and not baseline:
                points.append((local_x, local_y))
    if not points:
        raise RuntimeError(f"generated paint cell {column},{row_index} has no car pixels")
    min_x = min(x for x, _ in points)
    max_x = max(x for x, _ in points)
    min_y = min(y for _, y in points)
    max_y = max(y for _, y in points)
    cropped = [
        bytearray(sheet_rows[y0 + y][(x0 + min_x) * 4 : (x0 + max_x + 1) * 4])
        for y in range(min_y, max_y + 1)
    ]
    return max_x - min_x + 1, max_y - min_y + 1, cropped


def paint_template(template_rows, width, height, paint_rows, paint_width, paint_height):
    output_width = width * SCALE
    output_height = height * SCALE
    output = [bytearray(output_width * 4) for _ in range(output_height)]
    for y in range(output_height):
        template_y = (y + 0.5) / SCALE - 0.5
        paint_y = (y + 0.5) * paint_height / output_height - 0.5
        for x in range(output_width):
            template_x = (x + 0.5) / SCALE - 0.5
            paint_x = (x + 0.5) * paint_width / output_width - 0.5
            fallback = sample_bilinear(template_rows, width, height, template_x, template_y)
            alpha = fallback[3]
            if alpha == 0:
                continue
            painted = sample_bilinear(paint_rows, paint_width, paint_height, paint_x, paint_y)
            r, g, b = painted[:3]
            looks_like_sheet_background = b > r * 1.15 and b > g * 1.08 and r < 70
            lower_edge = y > output_height * 0.88
            wheel_corner = x < output_width * 0.18 or x > output_width * 0.82
            looks_like_baseline = y > output_height * 0.92 and r > 90 and r > g * 1.4 and r > b * 1.2
            use_fallback = (
                looks_like_sheet_background or looks_like_baseline or (lower_edge and wheel_corner)
            )
            color = fallback[:3] if use_fallback else painted[:3]
            offset = x * 4
            output[y][offset : offset + 4] = bytes((*color, alpha))
    return output


def prepare(reference_dir, output_dir, paint_sheet):
    sheet_width, sheet_height, sheet_rows = read_png_rgba(paint_sheet)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, (filename, expected_width, expected_height, shift, column, row_index) in SPRITES.items():
        source_path = reference_dir / filename
        width, height, rows = read_png_rgba(source_path)
        if (width, height) != (expected_width, expected_height):
            raise RuntimeError(f"{source_path} must be {expected_width}x{expected_height}, got {width}x{height}")
        recolor_body(rows)
        uphill = name.startswith("PLAYER_UPHILL_")
        empty_cockpit(rows, shift, uphill)
        draw_blank_plate(rows, uphill)
        paint_width, paint_height, paint_rows = extract_paint_cell(
            sheet_rows, sheet_width, sheet_height, column, row_index
        )
        scaled = paint_template(rows, width, height, paint_rows, paint_width, paint_height)
        output_path = output_dir / f"{name}.png"
        write_png(output_path, width * SCALE, height * SCALE, scaled)
        print(output_path)


def main():
    parser = argparse.ArgumentParser(
        description="Repaint the six player sprites on the original Racer pose templates."
    )
    parser.add_argument(
        "reference_dir",
        type=Path,
        help="Directory containing the six original-player_*.png references",
    )
    parser.add_argument("--output-dir", type=Path, default=SOURCE_DIR)
    parser.add_argument("--paint-sheet", type=Path, default=PAINT_SHEET)
    args = parser.parse_args()
    prepare(args.reference_dir, args.output_dir, args.paint_sheet)


if __name__ == "__main__":
    main()
