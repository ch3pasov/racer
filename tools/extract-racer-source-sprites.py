#!/usr/bin/env python3
import argparse
from collections import deque
from pathlib import Path

from generate_racer_textures_support import read_png_rgba, remove_chroma, write_png


DEFAULT_OUT = Path("assets/racer/textures/v3-sources")


def component_bounds(rows):
    width = len(rows[0]) // 4
    height = len(rows)
    seen = [[False] * width for _ in range(height)]
    bounds = []
    for y in range(height):
        for x in range(width):
            if seen[y][x] or rows[y][x * 4 + 3] == 0:
                continue
            queue = deque([(x, y)])
            seen[y][x] = True
            min_x = max_x = x
            min_y = max_y = y
            area = 0
            while queue:
                cx, cy = queue.popleft()
                area += 1
                min_x = min(min_x, cx)
                min_y = min(min_y, cy)
                max_x = max(max_x, cx)
                max_y = max(max_y, cy)
                for nx, ny in ((cx - 1, cy), (cx + 1, cy), (cx, cy - 1), (cx, cy + 1)):
                    if nx < 0 or ny < 0 or nx >= width or ny >= height or seen[ny][nx]:
                        continue
                    if rows[ny][nx * 4 + 3] == 0:
                        continue
                    seen[ny][nx] = True
                    queue.append((nx, ny))
            if area >= 64:
                bounds.append((min_x, min_y, max_x, max_y, area))
    return bounds


def sort_components(bounds, expected_count):
    if expected_count == 9:
        expected_rows = 3
    elif expected_count in {6, 8}:
        expected_rows = 2
    else:
        expected_rows = 1
    if expected_rows == 1:
        return sorted(bounds, key=lambda item: ((item[0] + item[2]) / 2, (item[1] + item[3]) / 2))

    centers = sorted(((item[1] + item[3]) / 2, index, item) for index, item in enumerate(bounds))
    gaps = [
        (centers[index + 1][0] - centers[index][0], index)
        for index in range(len(centers) - 1)
    ]
    split_after = {index for _, index in sorted(gaps, reverse=True)[: expected_rows - 1]}
    rows = []
    current = []
    for index, (_, _, item) in enumerate(centers):
        current.append(item)
        if index in split_after:
            rows.append(current)
            current = []
    rows.append(current)
    ordered = []
    for row in rows:
        ordered.extend(sorted(row, key=lambda item: (item[0] + item[2]) / 2))
    return ordered


def crop(rows, bounds, pad=6):
    width = len(rows[0]) // 4
    height = len(rows)
    min_x, min_y, max_x, max_y, _ = bounds
    min_x = max(0, min_x - pad)
    min_y = max(0, min_y - pad)
    max_x = min(width - 1, max_x + pad)
    max_y = min(height - 1, max_y + pad)
    out_w = max_x - min_x + 1
    out_rows = []
    for y in range(min_y, max_y + 1):
        row = bytearray()
        for x in range(min_x, max_x + 1):
            row.extend(rows[y][x * 4 : x * 4 + 4])
        out_rows.append(row)
    return out_w, len(out_rows), out_rows


def fix_truck_rear_window(rows):
    width = len(rows[0]) // 4
    height = len(rows)
    top_y = round(height * 0.1)
    bottom_y = round(height * 0.32)
    for y in range(top_y, bottom_y):
        t = (y - top_y) / max(1, bottom_y - top_y)
        left = round(width * (0.25 + (0.18 - 0.25) * t))
        right = round(width * (0.75 + (0.82 - 0.75) * t))
        shade = round(14 + 14 * (1 - t))
        for x in range(left, right):
            offset = x * 4
            r, g, b, a = rows[y][offset : offset + 4]
            greenish = g > 70 and g > r * 1.25 and g > b * 1.25
            if a == 0 or greenish:
                rows[y][offset : offset + 4] = bytes((shade, shade + 24, shade + 20, 255))
    return rows


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("sheet", type=Path)
    parser.add_argument("--names", required=True, help="Comma-separated output sprite names in sheet order")
    parser.add_argument("--key", choices=["green", "magenta"], default="green")
    parser.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = parser.parse_args()

    names = [name.strip() for name in args.names.split(",") if name.strip()]
    _, _, rows = read_png_rgba(args.sheet)
    key = (0, 255, 0) if args.key == "green" else (255, 0, 255)
    rows = remove_chroma(rows, key=key)
    bounds = sort_components(component_bounds(rows), len(names))
    if len(bounds) != len(names):
        raise SystemExit(f"expected {len(names)} components, found {len(bounds)} in {args.sheet}")
    args.out.mkdir(parents=True, exist_ok=True)
    for name, item in zip(names, bounds):
        width, height, sprite_rows = crop(rows, item)
        if name == "TRUCK":
            sprite_rows = fix_truck_rear_window(sprite_rows)
        out = args.out / f"{name}.png"
        write_png(out, width, height, sprite_rows)
        print(out)


if __name__ == "__main__":
    main()
