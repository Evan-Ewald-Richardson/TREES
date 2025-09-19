"""GPX parsing and timing helpers."""

from __future__ import annotations

import json
import math
from datetime import datetime
from typing import Any, Dict, List, Optional

import gpxpy


def parse_gpx_to_tracks(text: str) -> List[Dict[str, Any]]:
    """Parse GPX text and extract track/route data."""

    gpx = gpxpy.parse(text)
    tracks_out: List[Dict[str, Any]] = []

    if gpx.tracks:
        for idx, track in enumerate(gpx.tracks):
            name = track.name or f"Track {idx + 1}"
            points: List[Dict[str, Any]] = []
            for segment in track.segments or []:
                for point in segment.points or []:
                    points.append(
                        {
                            "lat": point.latitude,
                            "lon": point.longitude,
                            "ele": point.elevation if point.elevation is not None else None,
                            "time": point.time.isoformat() if point.time else None,
                        }
                    )
            if points:
                tracks_out.append({"name": name, "points": points})

    if not tracks_out and gpx.routes:
        for idx, route in enumerate(gpx.routes):
            name = route.name or f"Route {idx + 1}"
            points: List[Dict[str, Any]] = []
            for point in route.points or []:
                points.append(
                    {
                        "lat": point.latitude,
                        "lon": point.longitude,
                        "ele": point.elevation if point.elevation is not None else None,
                        "time": point.time.isoformat() if point.time else None,
                    }
                )
            if points:
                tracks_out.append({"name": name, "points": points})

    return tracks_out


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in meters using the Haversine formula."""

    earth_radius_m = 6_371_000.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(d_lon / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return earth_radius_m * c


def points_near_with_time(
    points: List[Dict[str, Any]], target: Dict[str, float], radius_m: int
) -> List[Dict[str, float]]:
    """Return indices/timestamps of points within radius of target that have time."""

    hits: List[Dict[str, float]] = []
    for idx, point in enumerate(points):
        raw_time = point.get("time")
        if not raw_time:
            continue
        try:
            parsed = datetime.fromisoformat(str(raw_time).replace("Z", "+00:00"))
        except ValueError:
            continue
        if haversine_m(point["lat"], point["lon"], target["lat"], target["lon"]) <= radius_m:
            hits.append({"index": idx, "tMs": parsed.timestamp() * 1000})
    return hits


def point_within_radius(
    point: Dict[str, Any], target: Dict[str, float], radius_m: int
) -> bool:
    """Check whether point is within radius of the target coordinate."""

    return (
        haversine_m(point["lat"], point["lon"], target["lat"], target["lon"])
        <= radius_m
    )


def pass_through_target_between(
    points: List[Dict[str, Any]],
    target: Dict[str, float],
    index_start: int,
    index_end: int,
    radius_m: int,
) -> bool:
    """Check whether the line between two indices crosses the target radius."""

    for idx in range(index_start, index_end + 1):
        if point_within_radius(points[idx], target, radius_m):
            return True
    return False


def checkpoints_valid_between(
    points: List[Dict[str, Any]],
    checkpoints: List[Dict[str, float]],
    index_start: int,
    index_end: int,
    radius_m: int,
) -> bool:
    """Ensure each checkpoint is crossed between start and end indices."""

    if not checkpoints:
        return True
    for checkpoint in checkpoints:
        if not pass_through_target_between(
            points, checkpoint, index_start, index_end, radius_m
        ):
            return False
    return True


def compute_segment_times(
    points: List[Dict[str, Any]], gates: List[Dict[str, Any]], buffer_m: int
) -> List[Dict[str, Any]]:
    """Compute segment times for given points and gates."""

    output: List[Dict[str, Any]] = []
    for gate in gates:
        name = gate.get("name") or f"Pair {gate['pairId']}"
        checkpoints = gate.get("checkpoints") or []

        starts = points_near_with_time(points, gate["start"], buffer_m)
        ends = points_near_with_time(points, gate["end"], buffer_m)

        if not starts or not ends:
            output.append({"segment": name, "timeSec": "N/A", "valid": False})
            continue

        best_seconds = math.inf
        best_pair: Optional[tuple[int, int]] = None

        for start_hit in starts:
            start_index = int(start_hit["index"])
            start_ms = float(start_hit["tMs"])
            for end_hit in ends:
                end_index = int(end_hit["index"])
                if end_index <= start_index:
                    continue
                delta = (float(end_hit["tMs"]) - start_ms) / 1000.0
                if delta <= 0 or delta >= best_seconds:
                    continue
                best_seconds = delta
                best_pair = (start_index, end_index)

        if best_pair is None:
            output.append({"segment": name, "timeSec": "N/A", "valid": False})
            continue

        start_index, end_index = best_pair
        is_valid = checkpoints_valid_between(
            points, checkpoints, start_index, end_index, buffer_m
        )
        output.append(
            {
                "segment": name,
                "timeSec": int(round(best_seconds)),
                "valid": is_valid,
            }
        )

    return output


__all__ = [
    "checkpoints_valid_between",
    "compute_segment_times",
    "haversine_m",
    "parse_gpx_to_tracks",
    "point_within_radius",
    "points_near_with_time",
    "pass_through_target_between",
]
