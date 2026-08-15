from __future__ import annotations

import math
from typing import Iterable


def ratio(raw_left: float, raw_right: float) -> float:
    if raw_left <= 0 or raw_right <= 0:
        raise ValueError("左右光路平均值必须大于 0")
    return raw_left / raw_right


def summarize_samples(samples: Iterable[dict[str, float]]) -> dict[str, float]:
    rows = list(samples)
    if not rows:
        raise ValueError("没有可用的采样数据")
    raw_left = sum(float(row["raw_left"]) for row in rows) / len(rows)
    raw_right = sum(float(row["raw_right"]) for row in rows) / len(rows)
    return {
        "raw_left": raw_left,
        "raw_right": raw_right,
        "r": ratio(raw_left, raw_right),
        "samples": len(rows),
    }


def rotation_angle(r_value: float, r0: float) -> float:
    if r_value <= 0 or r0 <= 0:
        raise ValueError("R 和 R0 必须大于 0")
    return math.atan(math.sqrt(r_value)) - math.atan(math.sqrt(r0))


def linear_fit(points: Iterable[tuple[float, float]]) -> dict[str, float]:
    values = list(points)
    if len(values) < 2:
        raise ValueError("至少需要两个有效磁场点才能拟合")
    x_mean = sum(x for x, _ in values) / len(values)
    y_mean = sum(y for _, y in values) / len(values)
    denominator = sum((x - x_mean) ** 2 for x, _ in values)
    if denominator == 0:
        raise ValueError("磁场点不能全部相同")
    slope = sum((x - x_mean) * (y - y_mean) for x, y in values) / denominator
    intercept = y_mean - slope * x_mean
    residual = sum((y - (slope * x + intercept)) ** 2 for x, y in values)
    total = sum((y - y_mean) ** 2 for _, y in values)
    r_squared = 1.0 if total == 0 and residual == 0 else (0.0 if total == 0 else 1 - residual / total)
    return {"slope": slope, "intercept": intercept, "r_squared": r_squared}


def wavelength_result(points: Iterable[dict[str, float]], length_m: float) -> dict[str, float | list[dict[str, float]]]:
    rows = [dict(point) for point in points if point.get("status") == "complete"]
    if length_m <= 0:
        raise ValueError("样品长度必须大于 0")
    zero_points = [point for point in rows if float(point["magnetic_field_t"]) == 0]
    if len(zero_points) != 1:
        raise ValueError("必须有且只有一个已完成的零场点")
    r0 = float(zero_points[0]["r"])
    for point in rows:
        point["theta_rad"] = 0.0 if float(point["magnetic_field_t"]) == 0 else rotation_angle(float(point["r"]), r0)
    fit = linear_fit((float(point["magnetic_field_t"]), float(point["theta_rad"])) for point in rows)
    return {
        "r0": r0,
        "k_rad_per_t": fit["slope"],
        "intercept_rad": fit["intercept"],
        "r_squared": fit["r_squared"],
        "v_rad_per_t_m": fit["slope"] / length_m,
        "points": rows,
    }
