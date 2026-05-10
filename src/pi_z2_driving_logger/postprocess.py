"""Post-processing CLI: semantic join of Pi events with Traccar teacher track."""

from __future__ import annotations

import argparse
import json
import logging
import os
import statistics
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from .traccar_client import Position, TraccarClient, TraccarClientConfig
from .semantic_join import (
    CONFIDENCE_HIGH, CONFIDENCE_LOW, CONFIDENCE_MEDIUM, CONFIDENCE_MISSING,
    POI_TYPES,
    assign_teacher_positions,
    build_driver_intervals,
    confidence_from_delta,
    haversine_m,
    load_events,
    nearest_position_at,
    parse_event_time,
)

logger = logging.getLogger(__name__)

DEFAULT_TIME_MARGIN_S = 300  # 5 minutes

GPX_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1" creator="pi-z2-driving-logger"
     xmlns="http://www.topografix.com/GPX/1/1">
"""
GPX_FOOTER = "</gpx>\n"


# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

@dataclass
class PostprocessConfig:
    session_id: str
    teacher_device: str
    output_dir: str
    time_margin_s: int = DEFAULT_TIME_MARGIN_S


# ---------------------------------------------------------------------------
# Output generation
# ---------------------------------------------------------------------------

def _pos_to_dict(pos: Optional[Position]) -> Optional[dict]:
    if pos is None:
        return None
    return {
        "fix_time": pos.fix_time.isoformat(),
        "latitude": pos.latitude,
        "longitude": pos.longitude,
        "altitude": pos.altitude,
        "speed": pos.speed,
        "course": pos.course,
        "accuracy": pos.accuracy,
        "protocol": pos.protocol,
        "attributes": pos.attributes,
    }


def _pi_teacher_distance(event: dict, pos: Optional[Position]) -> Optional[float]:
    """Distance in metres between Pi GPS and teacher GPS, or None."""
    if pos is None:
        return None
    if not event.get("fix_valid"):
        return None
    lat = event.get("lat")
    lon = event.get("lon")
    if lat is None or lon is None:
        return None
    return round(haversine_m(lat, lon, pos.latitude, pos.longitude), 2)


def generate_outputs(
    events: list,
    positions: list,
    cfg: PostprocessConfig,
) -> dict:
    """Generate all output files in cfg.output_dir. Returns the report dict."""
    os.makedirs(cfg.output_dir, exist_ok=True)

    # -----------------------------------------------------------------------
    # 1. Driver intervals
    # -----------------------------------------------------------------------
    intervals = build_driver_intervals(events)
    assign_teacher_positions(intervals, positions)

    # -----------------------------------------------------------------------
    # 2. Semantic trace — one line per event
    # -----------------------------------------------------------------------
    trace_lines = []
    confidence_counts = {
        CONFIDENCE_HIGH: 0,
        CONFIDENCE_MEDIUM: 0,
        CONFIDENCE_LOW: 0,
        CONFIDENCE_MISSING: 0,
    }
    poi_confidence_counts = {k: 0 for k in confidence_counts}
    pi_teacher_distances: list[float] = []

    for event in events:
        etime = parse_event_time(event)
        pos, delta = nearest_position_at(positions, etime)
        conf = confidence_from_delta(delta)
        confidence_counts[conf] += 1
        dist = _pi_teacher_distance(event, pos)
        if dist is not None:
            pi_teacher_distances.append(dist)

        entry = {
            "event": event,
            "teacher_position": _pos_to_dict(pos),
            "confidence": conf,
            "time_delta_sec": round(delta, 3) if delta != float("inf") else None,
            "pi_teacher_distance_m": dist,
        }
        trace_lines.append(json.dumps(entry, ensure_ascii=False))

        if event.get("type") in POI_TYPES:
            poi_confidence_counts[conf] += 1

    _write_text(
        os.path.join(cfg.output_dir, "semantic_trace.jsonl"),
        "\n".join(trace_lines) + "\n" if trace_lines else "",
    )

    # -----------------------------------------------------------------------
    # 3. POI GeoJSON
    # -----------------------------------------------------------------------
    poi_features = []
    for event in events:
        if event.get("type") not in POI_TYPES:
            continue
        etime = parse_event_time(event)
        pos, delta = nearest_position_at(positions, etime)
        conf = confidence_from_delta(delta)
        dist = _pi_teacher_distance(event, pos)

        if pos is not None:
            coords = [pos.longitude, pos.latitude]
        elif event.get("lon") is not None:
            coords = [event["lon"], event["lat"]]
        else:
            coords = [0.0, 0.0]

        props = {
            "event_type": event.get("type"),
            "event_time": etime.isoformat(),
            "teacher_device": cfg.teacher_device,
            "teacher_time": pos.fix_time.isoformat() if pos else None,
            "time_delta_sec": round(delta, 3) if delta != float("inf") else None,
            "confidence": conf,
            "pi_lat": event.get("lat"),
            "pi_lon": event.get("lon"),
            "pi_fix_valid": event.get("fix_valid"),
            "pi_hdop": event.get("hdop"),
            "pi_satellites_used": event.get("satellites_used"),
            "pi_teacher_distance_m": dist,
            "source": "semantic_join",
        }
        poi_features.append({
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": coords},
            "properties": props,
        })

    _write_json(
        os.path.join(cfg.output_dir, "semantic_pois.geojson"),
        {"type": "FeatureCollection", "features": poi_features},
    )

    # -----------------------------------------------------------------------
    # 4. Self-driving track GeoJSON + GPX
    # -----------------------------------------------------------------------
    track_features = []
    gpx_trk_segs = []
    self_track_point_count = 0

    for interval in intervals:
        pts = interval.teacher_positions
        if not pts:
            # Still emit an empty-geometry feature so the interval is visible
            track_features.append({
                "type": "Feature",
                "geometry": {"type": "LineString", "coordinates": []},
                "properties": {
                    "driver": interval.driver,
                    "start": interval.start.isoformat(),
                    "end": interval.end.isoformat() if interval.end else None,
                    "point_count": 0,
                    "teacher_device": cfg.teacher_device,
                },
            })
            continue

        coords = [[p.longitude, p.latitude] for p in pts]
        self_track_point_count += len(pts)
        track_features.append({
            "type": "Feature",
            "geometry": {"type": "LineString", "coordinates": coords},
            "properties": {
                "driver": interval.driver,
                "start": interval.start.isoformat(),
                "end": interval.end.isoformat() if interval.end else None,
                "point_count": len(pts),
                "teacher_device": cfg.teacher_device,
            },
        })
        gpx_trk_segs.append(pts)

    _write_json(
        os.path.join(cfg.output_dir, "self_driving_track.geojson"),
        {"type": "FeatureCollection", "features": track_features},
    )
    _write_text(
        os.path.join(cfg.output_dir, "self_driving_track.gpx"),
        _build_gpx(gpx_trk_segs),
    )

    # -----------------------------------------------------------------------
    # 5. Driver intervals JSON
    # -----------------------------------------------------------------------
    intervals_data = []
    for interval in intervals:
        intervals_data.append({
            "type": "driver_interval",
            "driver": interval.driver,
            "start": interval.start.isoformat(),
            "end": interval.end.isoformat() if interval.end else None,
            "teacher_device": cfg.teacher_device,
            "point_count": len(interval.teacher_positions),
        })
    _write_json(
        os.path.join(cfg.output_dir, "driver_intervals.json"), intervals_data
    )

    # -----------------------------------------------------------------------
    # 6. Pi–teacher error GeoJSON
    # -----------------------------------------------------------------------
    error_features = []
    for event in events:
        if not event.get("fix_valid"):
            continue
        pi_lat = event.get("lat")
        pi_lon = event.get("lon")
        if pi_lat is None or pi_lon is None:
            continue
        etime = parse_event_time(event)
        pos, delta = nearest_position_at(positions, etime)
        if pos is None:
            continue
        dist = haversine_m(pi_lat, pi_lon, pos.latitude, pos.longitude)
        # LineString connecting Pi → teacher
        error_features.append({
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": [
                    [pi_lon, pi_lat],
                    [pos.longitude, pos.latitude],
                ],
            },
            "properties": {
                "event_type": event.get("type"),
                "event_time": etime.isoformat(),
                "pi_teacher_distance_m": round(dist, 2),
                "confidence": confidence_from_delta(delta),
                "time_delta_sec": round(delta, 3),
            },
        })

    _write_json(
        os.path.join(cfg.output_dir, "pi_teacher_error.geojson"),
        {"type": "FeatureCollection", "features": error_features},
    )

    # -----------------------------------------------------------------------
    # 7. Report
    # -----------------------------------------------------------------------
    poi_events = [e for e in events if e.get("type") in POI_TYPES]
    driver_transition_events = [
        e for e in events
        if e.get("type") in {"driver_state_changed_to_self", "driver_state_changed_to_other"}
    ]

    dist_stats: dict = {"count": 0, "min": None, "median": None, "mean": None, "max": None}
    if pi_teacher_distances:
        dist_stats = {
            "count": len(pi_teacher_distances),
            "min": round(min(pi_teacher_distances), 2),
            "median": round(statistics.median(pi_teacher_distances), 2),
            "mean": round(statistics.mean(pi_teacher_distances), 2),
            "max": round(max(pi_teacher_distances), 2),
        }

    report = {
        "session_id": cfg.session_id,
        "teacher_device": cfg.teacher_device,
        "event_count": len(events),
        "poi_count": len(poi_events),
        "driver_transition_count": len(driver_transition_events),
        "self_interval_count": len(intervals),
        "self_track_point_count": self_track_point_count,
        "high_confidence_poi_count": poi_confidence_counts[CONFIDENCE_HIGH],
        "medium_confidence_poi_count": poi_confidence_counts[CONFIDENCE_MEDIUM],
        "low_confidence_poi_count": poi_confidence_counts[CONFIDENCE_LOW],
        "missing_or_stale_count": confidence_counts[CONFIDENCE_MISSING],
        "pi_teacher_distance_m": dist_stats,
    }
    _write_json(os.path.join(cfg.output_dir, "report.json"), report)
    _write_text(
        os.path.join(cfg.output_dir, "report.md"),
        _build_report_md(report),
    )

    logger.info(
        "Outputs written to %s — %d events, %d POIs, %d self intervals, %d track points",
        cfg.output_dir,
        len(events),
        len(poi_events),
        len(intervals),
        self_track_point_count,
    )
    return report


# ---------------------------------------------------------------------------
# GPX builder
# ---------------------------------------------------------------------------

def _build_gpx(segments: list) -> str:
    lines = [GPX_HEADER, "  <trk>\n", "    <name>self_driving_track</name>\n"]
    for pts in segments:
        lines.append("    <trkseg>\n")
        for p in pts:
            ts = p.fix_time.strftime("%Y-%m-%dT%H:%M:%SZ")
            lines.append(
                f'      <trkpt lat="{p.latitude:.8f}" lon="{p.longitude:.8f}">\n'
                f"        <time>{ts}</time>\n"
                f"      </trkpt>\n"
            )
        lines.append("    </trkseg>\n")
    lines.extend(["  </trk>\n", GPX_FOOTER])
    return "".join(lines)


# ---------------------------------------------------------------------------
# Report markdown builder
# ---------------------------------------------------------------------------

def _build_report_md(report: dict) -> str:
    d = report.get("pi_teacher_distance_m", {})
    dist_line = (
        f"count={d.get('count',0)}, min={d.get('min')} m, "
        f"median={d.get('median')} m, mean={d.get('mean')} m, max={d.get('max')} m"
    )
    return f"""# Semantic post-processing report

session_id: {report['session_id']}
teacher_device: {report['teacher_device']}

## Events
- Total events: {report['event_count']}
- POI events: {report['poi_count']}
- Driver transitions: {report['driver_transition_count']}

## Self-driving
- Self intervals: {report['self_interval_count']}
- Track points: {report['self_track_point_count']}

## Confidence (all events)
- high: {report['high_confidence_poi_count']}
- medium: {report['medium_confidence_poi_count']}
- low: {report['low_confidence_poi_count']}
- missing/stale: {report['missing_or_stale_count']}

## Pi–teacher GPS error
{dist_line}
"""


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def _write_json(path: str, data) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _write_text(path: str, text: str) -> None:
    with open(path, "w", encoding="utf-8") as f:
        f.write(text)


# ---------------------------------------------------------------------------
# CLI argument parsing
# ---------------------------------------------------------------------------

def _parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Semantic post-processor: join Pi events with Traccar teacher track"
    )
    parser.add_argument("--session", required=True, help="Path to Pi session directory")
    parser.add_argument("--output-dir", required=True, help="Output directory")
    parser.add_argument(
        "--traccar-base-url",
        default=None,
        help="Traccar base URL (overrides TRACCAR_BASE_URL)",
    )
    parser.add_argument(
        "--traccar-user",
        default=None,
        help="Traccar username (overrides TRACCAR_USER)",
    )
    parser.add_argument(
        "--traccar-password",
        default=None,
        help="Traccar password (overrides TRACCAR_PASSWORD)",
    )
    parser.add_argument(
        "--teacher-device",
        default=None,
        help="Teacher device uniqueId (overrides TRACCAR_TEACHER_DEVICE_UNIQUE_ID)",
    )
    parser.add_argument(
        "--time-margin-seconds",
        type=int,
        default=DEFAULT_TIME_MARGIN_S,
        help=f"Time margin in seconds around session for fetching positions (default: {DEFAULT_TIME_MARGIN_S})",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main(argv=None) -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
        stream=sys.stdout,
    )

    args = _parse_args(argv)

    # Resolve Traccar credentials (CLI > env)
    env_cfg = TraccarClientConfig.from_env()
    base_url = args.traccar_base_url or env_cfg.base_url
    user = args.traccar_user or env_cfg.user
    password = args.traccar_password or env_cfg.password
    teacher_unique_id = args.teacher_device or env_cfg.teacher_device_unique_id

    if not base_url or not user or not password or not teacher_unique_id:
        logger.error(
            "Missing Traccar credentials. Provide via CLI flags or .traccar.env:\n"
            "  TRACCAR_BASE_URL, TRACCAR_USER, TRACCAR_PASSWORD, "
            "TRACCAR_TEACHER_DEVICE_UNIQUE_ID"
        )
        sys.exit(1)

    session_dir = args.session
    events_path = os.path.join(session_dir, "events.jsonl")
    session_id = os.path.basename(session_dir.rstrip("/"))

    # Load Pi events
    events = load_events(events_path)
    if not events:
        logger.warning("No events found in %s", events_path)

    # Determine time range from events
    event_times = [parse_event_time(e) for e in events]
    margin = timedelta(seconds=args.time_margin_seconds)
    if event_times:
        from_dt = min(event_times) - margin
        to_dt = max(event_times) + margin
    else:
        logger.warning("No events — using current time ±margin for position fetch")
        now = datetime.now(timezone.utc)
        from_dt = now - margin
        to_dt = now + margin

    logger.info(
        "Fetching positions: device=%s, from=%s, to=%s",
        teacher_unique_id,
        from_dt.isoformat(),
        to_dt.isoformat(),
    )

    # Fetch teacher positions
    client = TraccarClient(base_url, user, password)
    client.login()

    device = client.find_device_by_unique_id(teacher_unique_id)
    if device is None:
        logger.error("Teacher device %r not found in Traccar", teacher_unique_id)
        client.logout()
        sys.exit(1)

    device_id = device["id"]
    logger.info("Teacher device: %s (id=%d)", teacher_unique_id, device_id)

    # Use /api/reports/route for historical track data
    positions = client.get_route(device_id, from_dt, to_dt)
    logger.info("Fetched %d teacher positions", len(positions))

    client.logout()

    # Generate outputs
    cfg = PostprocessConfig(
        session_id=session_id,
        teacher_device=teacher_unique_id,
        output_dir=args.output_dir,
        time_margin_s=args.time_margin_seconds,
    )
    report = generate_outputs(events, positions, cfg)

    print(f"\n=== Report: {session_id} ===")
    print(f"  Events: {report['event_count']}  POIs: {report['poi_count']}")
    print(
        f"  Self intervals: {report['self_interval_count']}  "
        f"Track points: {report['self_track_point_count']}"
    )
    print(f"  Outputs: {args.output_dir}")


if __name__ == "__main__":
    main()
