#!/usr/bin/env python3
import argparse
import math
from pathlib import Path
from statistics import median

from generate_racer_textures_support import read_png_rgba, write_png


SHEET_PATH = Path("assets/racer/textures/v3-sheets/player-car-v3-original-poses-generated.png")
SOURCE_DIR = Path("assets/racer/textures/v3-sources")

CELLS = {
    "PLAYER_LEFT": (0, 0),
    "PLAYER_STRAIGHT": (1, 0),
    "PLAYER_RIGHT": (2, 0),
    "PLAYER_UPHILL_LEFT": (0, 1),
    "PLAYER_UPHILL_STRAIGHT": (1, 1),
    "PLAYER_UPHILL_RIGHT": (2, 1),
}

BACKGROUND_DISTANCE = 48
EDGE_RADIUS = 3


def key_distance(row, x, key):
    offset = x * 4
    r, g, b = row[offset : offset + 3]
    return math.sqrt((r - key[0]) ** 2 + (g - key[1]) ** 2 + (b - key[2]) ** 2)


def sample_border_key(rows):
    width = len(rows[0]) // 4
    height = len(rows)
    samples = []
    for x in range(width):
        samples.append(rows[0][x * 4 : x * 4 + 3])
        samples.append(rows[height - 1][x * 4 : x * 4 + 3])
    for y in range(height):
        samples.append(rows[y][0:3])
        samples.append(rows[y][(width - 1) * 4 : (width - 1) * 4 + 3])
    return tuple(round(median(sample[channel] for sample in samples)) for channel in range(3))


def channel_alpha(value, key_value):
    if value < key_value and key_value > 0:
        return (key_value - value) / key_value
    if value > key_value and key_value < 255:
        return (value - key_value) / (255 - key_value)
    return 0


def remove_chroma(rows):
    width = len(rows[0]) // 4
    height = len(rows)
    key = sample_border_key(rows)
    visited = [bytearray(width) for _ in range(height)]
    for y, row in enumerate(rows):
        for x in range(width):
            if key_distance(row, x, key) <= BACKGROUND_DISTANCE:
                visited[y][x] = 1

    edge = [bytearray(row) for row in visited]
    frontier = []
    for y in range(height):
        for x in range(width):
            if not visited[y][x]:
                continue
            if (
                (x > 0 and not visited[y][x - 1])
                or (x + 1 < width and not visited[y][x + 1])
                or (y > 0 and not visited[y - 1][x])
                or (y + 1 < height and not visited[y + 1][x])
            ):
                frontier.append((x, y))

    for _ in range(EDGE_RADIUS):
        next_frontier = []
        for x, y in frontier:
            for yy in range(max(0, y - 1), min(height, y + 2)):
                for xx in range(max(0, x - 1), min(width, x + 2)):
                    if edge[yy][xx]:
                        continue
                    edge[yy][xx] = 1
                    next_frontier.append((xx, yy))
        frontier = next_frontier

    for y, row in enumerate(rows):
        for x in range(width):
            if visited[y][x]:
                offset = x * 4
                row[offset : offset + 4] = b"\x00\x00\x00\x00"
                continue
            if not edge[y][x]:
                continue
            offset = x * 4
            r, g, b, source_alpha = row[offset : offset + 4]
            alpha = max(
                channel_alpha(r, key[0]),
                channel_alpha(g, key[1]),
                channel_alpha(b, key[2]),
            )
            matte = min(source_alpha, round(alpha * 255))
            if matte <= 32:
                row[offset : offset + 4] = b"\x00\x00\x00\x00"
                continue
            if matte >= 240:
                continue

            alpha = matte / 255
            foreground = (
                round((r - key[0] * (1 - alpha)) / alpha),
                round((g - key[1] * (1 - alpha)) / alpha),
                round((b - key[2] * (1 - alpha)) / alpha),
            )
            row[offset : offset + 4] = bytes(
                max(0, min(255, channel)) for channel in (*foreground, matte)
            )
    return rows


def neutralize_magenta(rows):
    for row in rows:
        for x in range(len(row) // 4):
            offset = x * 4
            r, g, b, alpha = row[offset : offset + 4]
            if alpha > 0 and r > g + 12 and b > g + 12:
                row[offset : offset + 3] = bytes((g, g, g))
    return rows


def extract_cell(rows, width, height, column, row_index):
    min_x = round(column * width / 3)
    max_x = round((column + 1) * width / 3)
    row_divider = round(height * 0.46)
    min_y = 0 if row_index == 0 else row_divider
    max_y = row_divider if row_index == 0 else height
    cell = [bytearray(row[min_x * 4 : max_x * 4]) for row in rows[min_y:max_y]]
    return max_x - min_x, max_y - min_y, cell


def crop_visible(rows):
    width = len(rows[0]) // 4
    height = len(rows)
    min_x = width
    max_x = -1
    min_y = height
    max_y = -1
    for y, row in enumerate(rows):
        for x in range(width):
            if row[x * 4 + 3] <= 4:
                continue
            min_x = min(min_x, x)
            max_x = max(max_x, x)
            min_y = min(min_y, y)
            max_y = max(max_y, y)

    if max_x < 0:
        raise RuntimeError("generated sprite has no visible pixels")
    cropped = [
        bytearray(row[min_x * 4 : (max_x + 1) * 4])
        for row in rows[min_y : max_y + 1]
    ]
    return max_x - min_x + 1, max_y - min_y + 1, cropped


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("names", nargs="*", choices=CELLS)
    args = parser.parse_args()
    names = args.names or list(CELLS)
    sheet_width, sheet_height, sheet_rows = read_png_rgba(SHEET_PATH)

    for name in names:
        column, row_index = CELLS[name]
        _, _, rows = extract_cell(sheet_rows, sheet_width, sheet_height, column, row_index)
        width, height, cropped = crop_visible(neutralize_magenta(remove_chroma(rows)))
        output = SOURCE_DIR / f"{name}.png"
        write_png(output, width, height, cropped)
        print(f"{name}: {width}x{height} -> {output}")


if __name__ == "__main__":
    main()
