"""Tests for Traccar payload builder (traccar.py)."""

import pytest
from pi_z2_driving_logger.gps import GPSState
from pi_z2_driving_logger.traccar import (
    knots_to_kmh,
    estimate_accuracy,
    build_position_payload,
    build_event_payload,
    payload_to_url,
    TraccarConfig,
)


# ---------------------------------------------------------------------------
# Unit: conversion helpers
# ---------------------------------------------------------------------------

def test_knots_to_kmh_zero():
    assert knots_to_kmh(0.0) == pytest.approx(0.0)


def test_knots_to_kmh_one():
    assert knots_to_kmh(1.0) == pytest.approx(1.852)


def test_knots_to_kmh_typical():
    # 10 knots ≈ 18.52 km/h
    assert knots_to_kmh(10.0) == pytest.approx(18.52)


def test_estimate_accuracy_from_hdop():
    assert estimate_accuracy(2.0) == pytest.approx(10.0)


def test_estimate_accuracy_none_returns_default():
    # When hdop is unknown, return a large fallback
    val = estimate_accuracy(None)
    assert val > 0


# ---------------------------------------------------------------------------
# Unit: build_position_payload
# ---------------------------------------------------------------------------

def _valid_gps() -> GPSState:
    g = GPSState()
    g.lat = 35.681236
    g.lon = 139.767125
    g.fix_valid = True
    g.fix_quality = 1
    g.satellites_used = 7
    g.hdop = 1.96
    g.speed_knots = 5.0
    g.course = 270.0
    g.timestamp = "093000"
    return g


def test_position_payload_required_fields():
    payload = build_position_payload(_valid_gps(), "self", "20260510-093000")
    assert payload is not None
    assert "lat" in payload
    assert "lon" in payload
    assert "timestamp" in payload


def test_position_payload_kind_is_position():
    payload = build_position_payload(_valid_gps(), "self", "20260510-093000")
    assert payload["kind"] == "position"


def test_position_payload_speed_converted_to_kmh():
    gps = _valid_gps()
    gps.speed_knots = 10.0
    payload = build_position_payload(gps, "self", "20260510-093000")
    assert payload["speed"] == pytest.approx(18.52)


def test_position_payload_accuracy_estimated_from_hdop():
    gps = _valid_gps()
    gps.hdop = 2.0
    payload = build_position_payload(gps, "self", "20260510-093000")
    assert payload["accuracy"] == pytest.approx(10.0)


def test_position_payload_includes_driver_state():
    payload = build_position_payload(_valid_gps(), "other", "20260510-093000")
    assert payload["driver_state"] == "other"


def test_position_payload_includes_session_id():
    payload = build_position_payload(_valid_gps(), "self", "20260510-093000")
    assert payload["session_id"] == "20260510-093000"


def test_position_payload_includes_source():
    payload = build_position_payload(_valid_gps(), "self", "20260510-093000")
    assert "source" in payload


def test_position_payload_includes_fix_quality_and_satellites():
    gps = _valid_gps()
    gps.fix_quality = 2
    gps.satellites_used = 9
    payload = build_position_payload(gps, "self", "20260510-093000")
    assert payload["fix_quality"] == 2
    assert payload["satellites_used"] == 9


def test_position_payload_includes_hdop():
    payload = build_position_payload(_valid_gps(), "self", "20260510-093000")
    assert payload["hdop"] is not None


def test_position_payload_fix_invalid_returns_none():
    gps = GPSState()
    gps.fix_valid = False
    gps.lat = 35.0
    gps.lon = 139.0
    assert build_position_payload(gps, "self", "20260510-093000") is None


def test_position_payload_no_lat_returns_none():
    gps = GPSState()
    gps.fix_valid = True
    gps.lat = None
    gps.lon = 139.0
    assert build_position_payload(gps, "self", "20260510-093000") is None


# ---------------------------------------------------------------------------
# Unit: build_event_payload
# ---------------------------------------------------------------------------

def test_event_payload_required_fields():
    payload = build_event_payload(
        "walk_poi", _valid_gps(), "other", "20260510-093000", "maker_phat_left_button"
    )
    assert payload is not None
    assert "lat" in payload
    assert "lon" in payload
    assert "timestamp" in payload


def test_event_payload_kind_is_event():
    payload = build_event_payload(
        "walk_poi", _valid_gps(), "other", "20260510-093000"
    )
    assert payload["kind"] == "event"


def test_event_payload_includes_event_type():
    payload = build_event_payload(
        "driver_state_changed_to_self", _valid_gps(), "self", "20260510-093000"
    )
    assert payload["event_type"] == "driver_state_changed_to_self"


def test_event_payload_includes_source():
    payload = build_event_payload(
        "walk_poi", _valid_gps(), "other", "20260510-093000", "maker_phat_left_button"
    )
    assert payload["source"] == "maker_phat_left_button"


def test_event_payload_includes_driver_state_and_session_id():
    payload = build_event_payload(
        "walk_poi_important", _valid_gps(), "self", "20260510-093000"
    )
    assert payload["driver_state"] == "self"
    assert payload["session_id"] == "20260510-093000"


def test_event_payload_fix_invalid_returns_none():
    gps = GPSState()
    gps.fix_valid = False
    gps.lat = 35.0
    gps.lon = 139.0
    assert build_event_payload("walk_poi", gps, "other", "20260510-093000") is None


def test_event_payload_no_lat_returns_none():
    gps = GPSState()
    gps.fix_valid = True
    gps.lat = None
    gps.lon = 139.0
    assert build_event_payload("walk_poi", gps, "other", "20260510-093000") is None


# ---------------------------------------------------------------------------
# Unit: payload_to_url
# ---------------------------------------------------------------------------

def test_payload_to_url_contains_id():
    payload = build_position_payload(_valid_gps(), "self", "20260510-093000")
    url = payload_to_url("http://100.107.123.105:30055/", "pi-z2-wh", payload)
    assert "id=pi-z2-wh" in url


def test_payload_to_url_contains_lat_lon():
    payload = build_position_payload(_valid_gps(), "self", "20260510-093000")
    url = payload_to_url("http://100.107.123.105:30055/", "pi-z2-wh", payload)
    assert "lat=" in url
    assert "lon=" in url


def test_payload_to_url_contains_timestamp():
    payload = build_position_payload(_valid_gps(), "self", "20260510-093000")
    url = payload_to_url("http://100.107.123.105:30055/", "pi-z2-wh", payload)
    assert "timestamp=" in url


def test_payload_to_url_contains_driver_state():
    payload = build_position_payload(_valid_gps(), "other", "20260510-093000")
    url = payload_to_url("http://100.107.123.105:30055/", "pi-z2-wh", payload)
    assert "driver_state=other" in url


def test_payload_to_url_event_contains_event_type():
    payload = build_event_payload("walk_poi", _valid_gps(), "other", "20260510-093000")
    url = payload_to_url("http://100.107.123.105:30055/", "pi-z2-wh", payload)
    assert "event_type=walk_poi" in url


# ---------------------------------------------------------------------------
# Unit: TraccarConfig.from_env
# ---------------------------------------------------------------------------

def test_traccar_config_from_env_defaults(monkeypatch):
    monkeypatch.delenv("TRACCAR_ENABLED", raising=False)
    monkeypatch.delenv("TRACCAR_ENDPOINT", raising=False)
    monkeypatch.delenv("TRACCAR_DEVICE_ID", raising=False)
    cfg = TraccarConfig.from_env()
    assert cfg.enabled is False


def test_traccar_config_from_env_enabled(monkeypatch):
    monkeypatch.setenv("TRACCAR_ENABLED", "true")
    monkeypatch.setenv("TRACCAR_ENDPOINT", "http://example.com:30055/")
    monkeypatch.setenv("TRACCAR_DEVICE_ID", "test-device")
    cfg = TraccarConfig.from_env()
    assert cfg.enabled is True
    assert cfg.endpoint == "http://example.com:30055/"
    assert cfg.device_id == "test-device"
