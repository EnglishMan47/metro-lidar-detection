#!/usr/bin/env python3
"""Create a reproducible provisional annotation for doubleT_obstacle.

The supplied archive has no official frame/object labels. This script encodes
the manually reviewed spatial regions and extracts per-frame tracks so that
the assumptions remain auditable instead of being hidden in detector code.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path
from typing import Any

import numpy as np

from inspect_pointcloud_bag import decode_pointcloud2, sqlite_uri


def connected_components(points: np.ndarray, radius: float) -> list[np.ndarray]:
    """Return Euclidean components using a small spatial hash."""
    if points.size == 0:
        return []
    parent = np.arange(len(points))
    cells: dict[tuple[int, int, int], list[int]] = {}
    keys = np.floor(points / radius).astype(np.int32)

    def find(index: int) -> int:
        while parent[index] != index:
            parent[index] = parent[parent[index]]
            index = int(parent[index])
        return index

    for index, key in enumerate(keys):
        cells.setdefault(tuple(int(value) for value in key), []).append(index)
    for index, key in enumerate(keys):
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for dz in (-1, 0, 1):
                    neighbor_key = (int(key[0] + dx), int(key[1] + dy), int(key[2] + dz))
                    for other in cells.get(neighbor_key, []):
                        if other <= index:
                            continue
                        if np.sum((points[index] - points[other]) ** 2) <= radius**2:
                            left, right = find(index), find(other)
                            if left != right:
                                parent[right] = left
    groups: dict[int, list[int]] = {}
    for index in range(len(points)):
        groups.setdefault(find(index), []).append(index)
    return [np.asarray(group) for group in sorted(groups.values(), key=len, reverse=True)]


def cloud_points(payload: bytes) -> np.ndarray:
    cloud = decode_pointcloud2(payload)
    raw = cloud.numpy_points()
    points = np.column_stack((raw["x"], -raw["y"], raw["z"])).astype(np.float64)
    valid = np.all(np.isfinite(points), axis=1) & np.any(points != 0, axis=1)
    return points[valid]


def bbox(points: np.ndarray) -> dict[str, Any]:
    low = np.min(points, axis=0)
    high = np.max(points, axis=0)
    center = np.median(points, axis=0)
    return {
        "point_count": int(len(points)),
        "center_m": {"x": float(center[0]), "forward": float(center[1]), "z": float(center[2])},
        "min_m": {"x": float(low[0]), "forward": float(low[1]), "z": float(low[2])},
        "max_m": {"x": float(high[0]), "forward": float(high[1]), "z": float(high[2])},
    }


def largest_component(
    points: np.ndarray,
    limits: tuple[float, float, float, float, float, float],
    radius: float,
    min_points: int,
) -> np.ndarray | None:
    xmin, xmax, fmin, fmax, zmin, zmax = limits
    selected = points[
        (points[:, 0] >= xmin)
        & (points[:, 0] <= xmax)
        & (points[:, 1] >= fmin)
        & (points[:, 1] <= fmax)
        & (points[:, 2] >= zmin)
        & (points[:, 2] <= zmax)
    ]
    components = connected_components(selected, radius)
    if not components or len(components[0]) < min_points:
        return None
    return selected[components[0]]


def intervals(frames: list[dict[str, Any]], key: str, expected: bool) -> list[dict[str, Any]]:
    result = []
    start = None
    for position, frame in enumerate(frames + [{key: not expected}]):
        matches = frame.get(key) is expected
        if matches and start is None:
            start = position
        elif not matches and start is not None:
            first = frames[start]
            last = frames[position - 1]
            result.append(
                {
                    "first_frame": first["frame"],
                    "last_frame": last["frame"],
                    "start_s": first["time_offset_s"],
                    "end_s": last["time_offset_s"],
                }
            )
            start = None
    return result


def smooth_binary(values: list[bool], radius: int = 2) -> list[bool]:
    """Remove isolated boundary jitter with a centered majority window."""
    result = []
    for index in range(len(values)):
        window = values[max(0, index - radius) : min(len(values), index + radius + 1)]
        result.append(sum(window) * 2 >= len(window))
    return result


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("database", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--gauge-center-x", type=float, default=-0.2)
    parser.add_argument("--gauge-width", type=float, default=2.2)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    gauge_min = args.gauge_center_x - args.gauge_width / 2
    gauge_max = args.gauge_center_x + args.gauge_width / 2
    connection = sqlite3.connect(sqlite_uri(args.database), uri=True)
    try:
        messages = connection.execute("SELECT timestamp, data FROM messages ORDER BY id").fetchall()
    finally:
        connection.close()
    if not messages:
        raise SystemExit("bag has no messages")

    # cloud_points removes invalid points, so index-wise comparison needs the
    # unfiltered representation. Decode it separately for the second person.
    reference_raw = decode_pointcloud2(messages[100][1]).numpy_points()
    reference_xyz = np.column_stack(
        (reference_raw["x"], -reference_raw["y"], reference_raw["z"])
    ).astype(np.float64)
    reference_raw_ranges = np.linalg.norm(reference_xyz, axis=1)

    first_timestamp = int(messages[0][0])
    primary_frames: list[dict[str, Any]] = []
    object_frames: list[dict[str, Any]] = []
    secondary_frames: list[dict[str, Any]] = []

    for frame_index, (timestamp, payload) in enumerate(messages):
        points = cloud_points(payload)
        time_offset = (int(timestamp) - first_timestamp) / 1_000_000_000

        primary = largest_component(
            points,
            (-2.5, 2.5, 50.0, 60.0, -2.35, -0.8),
            radius=0.30,
            min_points=15,
        )
        if primary is not None:
            item = {"frame": frame_index, "time_offset_s": time_offset, **bbox(primary)}
            center_x = item["center_m"]["x"]
            item["inside_gauge"] = gauge_min <= center_x <= gauge_max
            primary_frames.append(item)

        fixed_object = largest_component(
            points,
            (-0.8, 0.2, 76.1, 77.1, -2.35, -0.9),
            radius=0.35,
            min_points=15,
        )
        if fixed_object is not None:
            object_frames.append(
                {"frame": frame_index, "time_offset_s": time_offset, **bbox(fixed_object)}
            )

        raw = decode_pointcloud2(payload).numpy_points()
        current_xyz = np.column_stack((raw["x"], -raw["y"], raw["z"])).astype(np.float64)
        current_ranges = np.linalg.norm(current_xyz, axis=1)
        foreground = (
            np.all(np.isfinite(current_xyz), axis=1)
            & np.all(np.isfinite(reference_xyz), axis=1)
            & (current_ranges > 0)
            & (reference_raw_ranges > 0)
            & (current_ranges < reference_raw_ranges - 0.5)
            & (current_xyz[:, 0] >= 1.3)
            & (current_xyz[:, 0] <= 2.8)
            & (current_xyz[:, 1] >= 0.5)
            & (current_xyz[:, 1] <= 20.0)
            & (current_xyz[:, 2] >= -2.35)
            & (current_xyz[:, 2] <= 1.5)
        )
        candidate = current_xyz[foreground]
        if len(candidate):
            x_edges = np.arange(1.3, 2.8001, 0.1)
            f_edges = np.arange(0.5, 20.0001, 0.25)
            histogram, _, _ = np.histogram2d(candidate[:, 0], candidate[:, 1], bins=(x_edges, f_edges))
            peak_x, peak_f = np.unravel_index(np.argmax(histogram), histogram.shape)
            peak_count = int(histogram[peak_x, peak_f])
            if peak_count >= 40:
                x_center = (x_edges[peak_x] + x_edges[peak_x + 1]) / 2
                f_center = (f_edges[peak_f] + f_edges[peak_f + 1]) / 2
                person_points = candidate[
                    (np.abs(candidate[:, 0] - x_center) <= 0.55)
                    & (np.abs(candidate[:, 1] - f_center) <= 0.8)
                ]
                if len(person_points) >= 40:
                    secondary_frames.append(
                        {
                            "frame": frame_index,
                            "time_offset_s": time_offset,
                            "peak_points": peak_count,
                            **bbox(person_points),
                        }
                    )

    if len(primary_frames) != len(messages):
        raise SystemExit(f"primary person track is incomplete: {len(primary_frames)}/{len(messages)}")
    if len(object_frames) != len(messages):
        raise SystemExit(f"fixed object track is incomplete: {len(object_frames)}/{len(messages)}")

    raw_inside = [item["inside_gauge"] for item in primary_frames]
    for item, smoothed in zip(primary_frames, smooth_binary(raw_inside), strict=True):
        item["inside_gauge_raw"] = item["inside_gauge"]
        item["inside_gauge"] = smoothed

    object_centers = np.asarray(
        [[item["center_m"][key] for key in ("x", "forward", "z")] for item in object_frames]
    )
    report = {
        "format": "provisional-pointcloud-annotation-v1",
        "source_bag": args.database.parent.name,
        "frame_count": len(messages),
        "coordinate_convention": {"x": "lateral", "forward": "-Y", "z": "vertical"},
        "gauge": {
            "status": "provisional",
            "center_x_m": args.gauge_center_x,
            "width_m": args.gauge_width,
            "min_x_m": gauge_min,
            "max_x_m": gauge_max,
            "reason": "center estimated from visible rails; Q&A gives width 2.1-2.2 m",
        },
        "labels": {
            "primary_person": {
                "class": "person",
                "status": "manually identified, algorithmically tracked",
                "visible_interval": {
                    "first_frame": 0,
                    "last_frame": len(messages) - 1,
                    "start_s": 0.0,
                    "end_s": primary_frames[-1]["time_offset_s"],
                },
                "inside_gauge_intervals": intervals(primary_frames, "inside_gauge", True),
                "outside_gauge_intervals": intervals(primary_frames, "inside_gauge", False),
                "frames": primary_frames,
            },
            "object_on_rails": {
                "class": "unknown_object",
                "status": "manually identified, persistent compact cluster",
                "visible_interval": {
                    "first_frame": 0,
                    "last_frame": len(messages) - 1,
                    "start_s": 0.0,
                    "end_s": object_frames[-1]["time_offset_s"],
                },
                "median_center_m": {
                    "x": float(np.median(object_centers[:, 0])),
                    "forward": float(np.median(object_centers[:, 1])),
                    "z": float(np.median(object_centers[:, 2])),
                },
                "frames": object_frames,
            },
            "secondary_person": {
                "class": "person",
                "status": "manually identified, temporal foreground track; outside provisional gauge",
                "visible_interval": (
                    {
                        "first_frame": secondary_frames[0]["frame"],
                        "last_frame": secondary_frames[-1]["frame"],
                        "start_s": secondary_frames[0]["time_offset_s"],
                        "end_s": secondary_frames[-1]["time_offset_s"],
                    }
                    if secondary_frames
                    else None
                ),
                "frames": secondary_frames,
            },
        },
        "limitations": [
            "The organizer supplied no official per-frame or 3D-box ground truth.",
            "Gauge center is inferred from the rails and must be confirmed in RViz/calibration.",
            "Boxes describe visible lidar returns, not full physical object dimensions.",
            "The object-on-rails label is a reviewed geometric hypothesis and should not be used as hidden-test truth.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {args.output}")
    print(f"Primary person: {len(primary_frames)}/{len(messages)} frames")
    print(f"Object on rails: {len(object_frames)}/{len(messages)} frames")
    print(f"Secondary person: {len(secondary_frames)}/{len(messages)} frames")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
