"""Tests for postprocess CLI output generation (test_postprocess.py)."""

import json
import os
from datetime import datetime, timezone

import pytest

from pi_z2_driving_logger.traccar_client import Position
from pi_z2_driving_logger.postprocess import (
    generate_outputs,
    PostprocessConfig,
)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _utc(hour, minute=0, second=0) -> datetime:
    return datetime(2026, 5, 10, hour, minute, second, tzinfo=timezone.utc)


def _make_pos(hour, minute=0, second=0, lat=35.72, lon=139.79) -> Position:
    return Position(
        device_id=2,
        fix_time=_utc(hour, minute, second),
        server_time=_utc(hour, minute, second),
        latitude=lat,
        longitude=lon,
        altitude=5.0,
        speed=10.0,
        course=90.0,
        accuracy=5.0,
        protocol="osmand",
        attributes={},
    )


SAMPLE_EVENTS = [
    {
        "type": "driver_state_changed_to_self",
        "system_time": "2026-05-10T01:10:00+00:00",
        "driver_state_before": "other",
        "driver_state_after": "self",
        "lat": 35.720,
        "lon": 139.780,
        "fix_valid": True,
        "fix_quality": 1,
        "satellites_used": 7,
        "hdop": 1.5,
        "nmea_time": "011000.00",
        "source": "maker_phat",
    },
    {
        "type": "walk_poi",
        "system_time": "2026-05-10T01:28:26+00:00",
        "driver_state": "self",
        "lat": 35.725,
        "lon": 139.792,
        "fix_valid": True,
        "fix_quality": 1,
        "satellites_used": 6,
        "hdop": 1.69,
        "nmea_time": "012826.00",
        "source": "maker_phat_left_button",
    },
    {
        "type": "driver_state_changed_to_other",
        "system_time": "2026-05-10T01:35:00+00:00",
        "driver_state_before": "self",
        "driver_state_after": "other",
        "lat": 35.726,
        "lon": 139.793,
        "fix_valid": True,
        "fix_quality": 1,
        "satellites_used": 6,
        "hdop": 1.8,
        "nmea_time": "013500.00",
        "source": "maker_phat",
    },
]

SAMPLE_POSITIONS = [
    _make_pos(1, 9, 55, lat=35.720, lon=139.780),
    _make_pos(1, 10, 5, lat=35.720, lon=139.781),
    _make_pos(1, 15, 0, lat=35.722, lon=139.783),
    _make_pos(1, 20, 0, lat=35.723, lon=139.786),
    _make_pos(1, 28, 27, lat=35.7258, lon=139.7921),
    _make_pos(1, 28, 35, lat=35.7256, lon=139.7919),
    _make_pos(1, 35, 5, lat=35.726, lon=139.793),
]


# ---------------------------------------------------------------------------
# generate_outputs
# ---------------------------------------------------------------------------

def test_generate_outputs_creates_files(tmp_path):
    cfg = PostprocessConfig(
        session_id="20260510-011000",
        teacher_device="osmand-yui-redmi-12-5g",
        output_dir=str(tmp_path),
    )
    generate_outputs(SAMPLE_EVENTS, SAMPLE_POSITIONS, cfg)

    assert os.path.exists(tmp_path / "semantic_trace.jsonl")
    assert os.path.exists(tmp_path / "semantic_pois.geojson")
    assert os.path.exists(tmp_path / "self_driving_track.geojson")
    assert os.path.exists(tmp_path / "self_driving_track.gpx")
    assert os.path.exists(tmp_path / "driver_intervals.json")
    assert os.path.exists(tmp_path / "pi_teacher_error.geojson")
    assert os.path.exists(tmp_path / "report.json")
    assert os.path.exists(tmp_path / "report.md")


def test_semantic_trace_jsonl_has_entries(tmp_path):
    cfg = PostprocessConfig("sess", "teacher", str(tmp_path))
    generate_outputs(SAMPLE_EVENTS, SAMPLE_POSITIONS, cfg)

    lines = (tmp_path / "semantic_trace.jsonl").read_text().strip().splitlines()
    assert len(lines) == len(SAMPLE_EVENTS)
    entry = json.loads(lines[0])
    assert "event" in entry
    assert "teacher_position" in entry
    assert "confidence" in entry
    assert "time_delta_sec" in entry


def test_semantic_pois_geojson(tmp_path):
    cfg = PostprocessConfig("sess", "teacher", str(tmp_path))
    generate_outputs(SAMPLE_EVENTS, SAMPLE_POSITIONS, cfg)

    geojson = json.loads((tmp_path / "semantic_pois.geojson").read_text())
    assert geojson["type"] == "FeatureCollection"
    # Only walk_poi events are POIs
    poi_events = [e for e in SAMPLE_EVENTS if "walk_poi" in e["type"]]
    assert len(geojson["features"]) == len(poi_events)
    feat = geojson["features"][0]
    assert feat["geometry"]["type"] == "Point"
    assert feat["properties"]["event_type"] == "walk_poi"
    assert "confidence" in feat["properties"]
    assert "time_delta_sec" in feat["properties"]


def test_self_driving_track_geojson(tmp_path):
    cfg = PostprocessConfig("sess", "teacher", str(tmp_path))
    generate_outputs(SAMPLE_EVENTS, SAMPLE_POSITIONS, cfg)

    geojson = json.loads((tmp_path / "self_driving_track.geojson").read_text())
    assert geojson["type"] == "FeatureCollection"
    assert len(geojson["features"]) >= 1  # at least one self interval


def test_driver_intervals_json(tmp_path):
    cfg = PostprocessConfig("sess", "teacher", str(tmp_path))
    generate_outputs(SAMPLE_EVENTS, SAMPLE_POSITIONS, cfg)

    data = json.loads((tmp_path / "driver_intervals.json").read_text())
    assert isinstance(data, list)
    assert data[0]["driver"] == "self"
    assert "start" in data[0]
    assert "end" in data[0]
    assert "point_count" in data[0]


def test_report_json_fields(tmp_path):
    cfg = PostprocessConfig("sess", "teacher", str(tmp_path))
    generate_outputs(SAMPLE_EVENTS, SAMPLE_POSITIONS, cfg)

    report = json.loads((tmp_path / "report.json").read_text())
    assert report["session_id"] == "sess"
    assert report["teacher_device"] == "teacher"
    assert "event_count" in report
    assert "poi_count" in report
    assert "self_interval_count" in report
    assert "self_track_point_count" in report
    assert "high_confidence_poi_count" in report
    assert "pi_teacher_distance_m" in report


def test_report_md_exists_and_nonempty(tmp_path):
    cfg = PostprocessConfig("sess", "teacher", str(tmp_path))
    generate_outputs(SAMPLE_EVENTS, SAMPLE_POSITIONS, cfg)

    md = (tmp_path / "report.md").read_text()
    assert len(md) > 50
    assert "sess" in md


def test_no_self_intervals_still_generates_files(tmp_path):
    cfg = PostprocessConfig("sess", "teacher", str(tmp_path))
    events_no_self = [e for e in SAMPLE_EVENTS if "driver_state_changed_to_self" not in e["type"]]
    generate_outputs(events_no_self, SAMPLE_POSITIONS, cfg)

    assert os.path.exists(tmp_path / "report.json")
    report = json.loads((tmp_path / "report.json").read_text())
    assert report["self_interval_count"] == 0
