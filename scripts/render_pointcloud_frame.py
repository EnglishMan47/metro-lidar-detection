#!/usr/bin/env python3
"""Render three diagnostic PointCloud2 projections to a dependency-free PNG."""

from __future__ import annotations

import argparse
import binascii
import sqlite3
import struct
import zlib
from pathlib import Path

import numpy as np

from inspect_pointcloud_bag import decode_pointcloud2, sqlite_uri


WIDTH = 1600
HEIGHT = 900
MARGIN = 50
GAP = 40
PANEL_WIDTH = (WIDTH - 2 * MARGIN - 2 * GAP) // 3
PANEL_HEIGHT = HEIGHT - 2 * MARGIN


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", binascii.crc32(kind + data))


def write_png(path: Path, image: np.ndarray) -> None:
    height, width, channels = image.shape
    if channels != 3 or image.dtype != np.uint8:
        raise ValueError("expected an RGB uint8 image")
    raw = b"".join(b"\x00" + image[row].tobytes() for row in range(height))
    encoded = b"\x89PNG\r\n\x1a\n"
    encoded += png_chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
    encoded += png_chunk(b"IDAT", zlib.compress(raw, 6))
    encoded += png_chunk(b"IEND", b"")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)


def draw_grid(canvas: np.ndarray, x0: int, y0: int, width: int, height: int) -> None:
    canvas[y0 : y0 + height, x0 : x0 + width] = (248, 250, 252)
    for fraction in np.linspace(0, 1, 7):
        x = x0 + min(width - 1, int(fraction * width))
        y = y0 + min(height - 1, int(fraction * height))
        canvas[y0 : y0 + height, x : x + 1] = (215, 222, 230)
        canvas[y : y + 1, x0 : x0 + width] = (215, 222, 230)
    canvas[y0 : y0 + height, x0 : x0 + 2] = (70, 80, 90)
    canvas[y0 : y0 + height, x0 + width - 2 : x0 + width] = (70, 80, 90)
    canvas[y0 : y0 + 2, x0 : x0 + width] = (70, 80, 90)
    canvas[y0 + height - 2 : y0 + height, x0 : x0 + width] = (70, 80, 90)


def project(
    canvas: np.ndarray,
    horizontal: np.ndarray,
    vertical: np.ndarray,
    forward: np.ndarray,
    panel: int,
    horizontal_range: tuple[float, float],
    vertical_range: tuple[float, float],
) -> int:
    x0 = MARGIN + panel * (PANEL_WIDTH + GAP)
    y0 = MARGIN
    draw_grid(canvas, x0, y0, PANEL_WIDTH, PANEL_HEIGHT)
    mask = (
        np.isfinite(horizontal)
        & np.isfinite(vertical)
        & (horizontal >= horizontal_range[0])
        & (horizontal <= horizontal_range[1])
        & (vertical >= vertical_range[0])
        & (vertical <= vertical_range[1])
    )
    h = horizontal[mask]
    v = vertical[mask]
    d = np.clip(forward[mask], 0, 120) / 120
    px = x0 + ((h - horizontal_range[0]) / (horizontal_range[1] - horizontal_range[0]) * (PANEL_WIDTH - 1)).astype(int)
    py = y0 + ((vertical_range[1] - v) / (vertical_range[1] - vertical_range[0]) * (PANEL_HEIGHT - 1)).astype(int)
    colors = np.stack(
        [
            (235 - 190 * d).astype(np.uint8),
            (90 + 80 * d).astype(np.uint8),
            (35 + 205 * d).astype(np.uint8),
        ],
        axis=1,
    )
    canvas[py, px] = colors
    return int(mask.sum())


def read_frame(db_path: Path, message_index: int) -> tuple[int, bytes]:
    connection = sqlite3.connect(sqlite_uri(db_path), uri=True)
    try:
        topic_id = connection.execute(
            "SELECT id FROM topics WHERE type = 'sensor_msgs/msg/PointCloud2' ORDER BY id LIMIT 1"
        ).fetchone()[0]
        row = connection.execute(
            "SELECT id FROM messages WHERE topic_id = ? ORDER BY id LIMIT 1 OFFSET ?",
            (topic_id, message_index),
        ).fetchone()
        if row is None:
            raise IndexError(f"message index {message_index} is outside the bag")
        timestamp, payload = connection.execute(
            "SELECT timestamp, data FROM messages WHERE id = ?", (row[0],)
        ).fetchone()
        return int(timestamp), payload
    finally:
        connection.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--index", type=int, default=0, help="zero-based PointCloud2 message index")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-points", type=int, default=250_000)
    parser.add_argument("--lateral", type=float, nargs=2, default=(-10, 10), metavar=("MIN", "MAX"))
    parser.add_argument("--forward", type=float, nargs=2, default=(0, 120), metavar=("MIN", "MAX"))
    parser.add_argument("--height", type=float, nargs=2, default=(-5, 8), metavar=("MIN", "MAX"))
    parser.add_argument("--select-lateral", type=float, nargs=2, metavar=("MIN", "MAX"))
    parser.add_argument("--select-forward", type=float, nargs=2, metavar=("MIN", "MAX"))
    parser.add_argument("--select-height", type=float, nargs=2, metavar=("MIN", "MAX"))
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    timestamp, payload = read_frame(args.database, args.index)
    cloud = decode_pointcloud2(payload)
    points = cloud.numpy_points()
    stride = max(1, int(np.ceil(points.size / args.max_points)))
    points = points[::stride]
    x = points["x"].astype(np.float64, copy=False)
    y = points["y"].astype(np.float64, copy=False)
    z = points["z"].astype(np.float64, copy=False)
    finite = np.isfinite(x) & np.isfinite(y) & np.isfinite(z)
    nonzero = (x != 0) | (y != 0) | (z != 0)
    keep = finite & nonzero
    forward_all = -y
    if args.select_lateral:
        keep &= (x >= args.select_lateral[0]) & (x <= args.select_lateral[1])
    if args.select_forward:
        keep &= (forward_all >= args.select_forward[0]) & (forward_all <= args.select_forward[1])
    if args.select_height:
        keep &= (z >= args.select_height[0]) & (z <= args.select_height[1])
    x, y, z = x[keep], y[keep], z[keep]
    forward = -y

    canvas = np.full((HEIGHT, WIDTH, 3), 255, dtype=np.uint8)
    counts = [
        project(canvas, x, forward, forward, 0, tuple(args.lateral), tuple(args.forward)),
        project(canvas, x, z, forward, 1, tuple(args.lateral), tuple(args.height)),
        project(canvas, forward, z, forward, 2, tuple(args.forward), tuple(args.height)),
    ]
    write_png(args.output, canvas)
    print(
        f"Wrote {args.output}; bag_timestamp_ns={timestamp}; frame={cloud.frame_id}; "
        f"points={cloud.point_count}; stride={stride}; plotted={counts}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
