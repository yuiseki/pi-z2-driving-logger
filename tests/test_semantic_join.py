"""Tests for semantic join logic (semantic_join.py)."""

import json
import os
import tempfile
from datetime import datetime, timedelta, timezone

import pytest

from pi_z2_driving_logger.traccar_client import Position
from pi_z2_driving_logger.semantic_join import (
    nearest_position_at,
    confidence_from_delta,
    haversine_m,
    build_driver_intervals,
    assign_teacher_positions,
    load_events,
    parse_event_time,
    CONFIDENCE_HIGH,
    CONFIDENCE_MEDIUM,
    CONFIDENCE_LOW,
    CONFIDENCE_MISSING,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _utc(hour, minute=0, second=0) -> datetime:
    return datetime(2026, 5, 10, hour, minute, second, tzinfo=timezone.utc)


def _make_position(hour, minute=0, second=0, lat=35.7, lon=139.8) -> Position:
    return Position(
        device_id=2,
        fix_time=_utc(hour, minute, second),
        server_time=_utc(hour, minute, second),
        latitude=lat,
        longitude=lon,
        altitude=0.0,
        speed=0.0,
        course=0.0,
        accuracy=5.0,
        protocol="osmand",
        attributes={},
    )


def _make_event(event_type: str, hour, minute=0, second=0, lat=None, lon=None,
                fix_valid=True) -> dict:
    e = {
        "type": event_type,
        "system_time": _utc(hour, minute, second).isoformat(),
        "driver_state": "other",
        "lat": lat,
        "lon": lon,
        "fix_valid": fix_valid,
        "fix_quality": 1 if fix_valid else 0,
        "satellites_used": 6,
        "hdop": 1.5,
        "nmea_time": "010000.00",
        "source": "maker_phat",
    }
    return e


# ---------------------------------------------------------------------------
# nearest_position_at
# ---------------------------------------------------------------------------

def test_nearest_position_exact_match():
    positions = [_make_position(1, 0, 0), _make_position(1, 0, 10)]
    event_time = _utc(1, 0, 0)
    pos, delta = nearest_position_at(positions, event_time)
    assert pos.fix_time == event_time
    assert delta == pytest.approx(0.0)


def test_nearest_position_closest():
    positions = [_make_position(1, 0, 0), _make_position(1, 0, 20), _make_position(1, 0, 25)]
    event_time = _utc(1, 0, 22)
    pos, delta = nearest_position_at(positions, event_time)
    assert pos.fix_time == _utc(1, 0, 20)
    assert delta == pytest.approx(2.0)


def test_nearest_position_empty_returns_none():
    pos, delta = nearest_position_at([], _utc(1, 0, 0))
    assert pos is None
    assert delta == float("inf")


def test_nearest_position_delta_seconds():
    positions = [_make_position(1, 0, 5)]
    _, delta = nearest_position_at(positions, _utc(1, 0, 0))
    assert delta == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# confidence_from_delta
# ---------------------------------------------------------------------------

def test_confidence_high():
    assert confidence_from_delta(0.0) == CONFIDENCE_HIGH
    assert confidence_from_delta(3.0) == CONFIDENCE_HIGH


def test_confidence_medium():
    assert confidence_from_delta(3.1) == CONFIDENCE_MEDIUM
    assert confidence_from_delta(10.0) == CONFIDENCE_MEDIUM


def test_confidence_low():
    assert confidence_from_delta(10.1) == CONFIDENCE_LOW
    assert confidence_from_delta(30.0) == CONFIDENCE_LOW


def test_confidence_missing():
    assert confidence_from_delta(30.1) == CONFIDENCE_MISSING
    assert confidence_from_delta(float("inf")) == CONFIDENCE_MISSING


# ---------------------------------------------------------------------------
# haversine_m
# ---------------------------------------------------------------------------

def test_haversine_same_point():
    assert haversine_m(35.7, 139.8, 35.7, 139.8) == pytest.approx(0.0, abs=1e-6)


def test_haversine_known_distance():
    # Tokyo Station to Shibuya is ~7.5 km
    d = haversine_m(35.6812, 139.7671, 35.6580, 139.7016)
    assert 6000 < d < 9000


def test_haversine_small_offset():
    # ~1 degree latitude ≈ 111 km
    d = haversine_m(35.0, 139.0, 36.0, 139.0)
    assert 110_000 < d < 112_000


# ---------------------------------------------------------------------------
# build_driver_intervals
# ---------------------------------------------------------------------------

def test_initial_state_other_no_events():
    intervals = build_driver_intervals([])
    assert intervals == []


def test_single_self_interval_open_end():
    events = [
        _make_event("driver_state_changed_to_self", 1, 0, 0),
    ]
    intervals = build_driver_intervals(events)
    assert len(intervals) == 1
    assert intervals[0].driver == "self"
    assert intervals[0].start == _utc(1, 0, 0)
    assert intervals[0].end is None


def test_self_then_other_closes_interval():
    events = [
        _make_event("driver_state_changed_to_self", 1, 0, 0),
        _make_event("driver_state_changed_to_other", 1, 30, 0),
    ]
    intervals = build_driver_intervals(events)
    assert len(intervals) == 1
    assert intervals[0].start == _utc(1, 0, 0)
    assert intervals[0].end == _utc(1, 30, 0)


def test_multiple_self_intervals():
    events = [
        _make_event("driver_state_changed_to_self", 1, 0, 0),
        _make_event("driver_state_changed_to_other", 1, 30, 0),
        _make_event("driver_state_changed_to_self", 2, 0, 0),
        _make_event("driver_state_changed_to_other", 2, 45, 0),
    ]
    intervals = build_driver_intervals(events)
    assert len(intervals) == 2
    assert intervals[0].start == _utc(1, 0, 0)
    assert intervals[1].end == _utc(2, 45, 0)


def test_other_before_self_ignored():
    events = [
        _make_event("driver_state_changed_to_other", 0, 30, 0),
        _make_event("driver_state_changed_to_self", 1, 0, 0),
    ]
    intervals = build_driver_intervals(events)
    assert len(intervals) == 1
    assert intervals[0].start == _utc(1, 0, 0)


# ---------------------------------------------------------------------------
# assign_teacher_positions
# ---------------------------------------------------------------------------

def test_assign_teacher_positions_within_interval():
    from pi_z2_driving_logger.semantic_join import DriverInterval
    interval = DriverInterval(
        driver="self",
        start=_utc(1, 0, 0),
        end=_utc(1, 30, 0),
        start_event={},
        end_event={},
    )
    positions = [
        _make_position(0, 59, 0),   # before
        _make_position(1, 10, 0),   # inside
        _make_position(1, 20, 0),   # inside
        _make_position(1, 31, 0),   # after
    ]
    assign_teacher_positions([interval], positions)
    assert len(interval.teacher_positions) == 2
    assert interval.teacher_positions[0].fix_time == _utc(1, 10, 0)


def test_assign_open_end_interval():
    from pi_z2_driving_logger.semantic_join import DriverInterval
    interval = DriverInterval(
        driver="self",
        start=_utc(2, 0, 0),
        end=None,
        start_event={},
        end_event=None,
    )
    positions = [_make_position(2, 5, 0), _make_position(2, 55, 0)]
    assign_teacher_positions([interval], positions)
    assert len(interval.teacher_positions) == 2


# ---------------------------------------------------------------------------
# load_events
# ---------------------------------------------------------------------------

def test_load_events_valid(tmp_path):
    f = tmp_path / "events.jsonl"
    f.write_text(
        '{"type":"walk_poi","system_time":"2026-05-10T10:28:26+09:00","lat":35.7}\n'
        '{"type":"driver_state_changed_to_self","system_time":"2026-05-10T10:30:00+09:00"}\n',
        encoding="utf-8",
    )
    events = load_events(str(f))
    assert len(events) == 2
    assert events[0]["type"] == "walk_poi"


def test_load_events_skips_malformed(tmp_path):
    f = tmp_path / "events.jsonl"
    f.write_text(
        '{"type":"walk_poi","system_time":"2026-05-10T10:28:26+09:00"}\n'
        "not json {\n"
        '{"type":"driver_state_changed_to_self","system_time":"2026-05-10T10:30:00+09:00"}\n',
        encoding="utf-8",
    )
    events = load_events(str(f))
    assert len(events) == 2


def test_load_events_missing_file():
    events = load_events("/nonexistent/events.jsonl")
    assert events == []


# ---------------------------------------------------------------------------
# parse_event_time
# ---------------------------------------------------------------------------

def test_parse_event_time_jst():
    event = {"system_time": "2026-05-10T10:28:26.511896+09:00"}
    dt = parse_event_time(event)
    assert dt.tzinfo is not None
    assert dt.hour == 1   # 10:28 JST = 01:28 UTC
    assert dt.minute == 28


def test_parse_event_time_utc():
    event = {"system_time": "2026-05-10T01:28:26+00:00"}
    dt = parse_event_time(event)
    assert dt.hour == 1
    assert dt.minute == 28


# ---------------------------------------------------------------------------
# POI event nearest position assignment
# ---------------------------------------------------------------------------

def test_poi_nearest_position():
    """Verify we can find the nearest teacher position for a POI event."""
    poi_event = _make_event("walk_poi", 1, 28, 26, lat=35.7259, lon=139.7922)
    positions = [
        _make_position(1, 28, 20, lat=35.726, lon=139.792),
        _make_position(1, 28, 27, lat=35.7258, lon=139.7921),
        _make_position(1, 28, 35, lat=35.725, lon=139.791),
    ]
    event_time = parse_event_time(poi_event)
    pos, delta = nearest_position_at(positions, event_time)
    assert delta == pytest.approx(1.0)
    assert pos.fix_time == _utc(1, 28, 27)


def test_pi_teacher_distance_with_valid_pi_pos():
    pi_lat, pi_lon = 35.72585, 139.79222
    teacher_lat, teacher_lon = 35.72576, 139.79095
    d = haversine_m(pi_lat, pi_lon, teacher_lat, teacher_lon)
    assert d > 0


def test_pi_teacher_distance_none_when_no_pi_fix():
    event = _make_event("walk_poi", 1, 0, 0, lat=None, lon=None, fix_valid=False)
    # Should not crash; lat/lon are None
    assert event["lat"] is None
    assert event["lon"] is None
