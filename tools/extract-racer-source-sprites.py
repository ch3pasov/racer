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
    bounds = sorted(component_bounds(rows), key=lambda item: (item[1] // 80, item[0]))
    if len(bounds) != len(names):
        raise SystemExit(f"expected {len(names)} components, found {len(bounds)} in {args.sheet}")
    args.out.mkdir(parents=True, exist_ok=True)
    for name, item in zip(names, bounds):
        width, height, sprite_rows = crop(rows, item)
        out = args.out / f"{name}.png"
        write_png(out, width, height, sprite_rows)
        print(out)


if __name__ == "__main__":
    main()
