"""Tests for Traccar API client (traccar_client.py)."""

import json
import os
from datetime import datetime, timezone
from io import BytesIO

import pytest

from pi_z2_driving_logger.traccar_client import (
    TraccarClient,
    TraccarClientConfig,
    _parse_traccar_time,
)


# ---------------------------------------------------------------------------
# Config from env
# ---------------------------------------------------------------------------

def test_config_from_env_defaults(monkeypatch):
    for k in ("TRACCAR_BASE_URL", "TRACCAR_USER", "TRACCAR_PASSWORD",
              "TRACCAR_TEACHER_DEVICE_UNIQUE_ID"):
        monkeypatch.delenv(k, raising=False)
    cfg = TraccarClientConfig.from_env()
    assert cfg.base_url == ""
    assert cfg.user == ""
    assert cfg.password == ""
    assert cfg.teacher_device_unique_id == ""


def test_config_from_env_reads_values(monkeypatch):
    monkeypatch.setenv("TRACCAR_BASE_URL", "http://example.com:8082")
    monkeypatch.setenv("TRACCAR_USER", "admin@example.com")
    monkeypatch.setenv("TRACCAR_PASSWORD", "secret")
    monkeypatch.setenv("TRACCAR_TEACHER_DEVICE_UNIQUE_ID", "my-device")
    cfg = TraccarClientConfig.from_env()
    assert cfg.base_url == "http://example.com:8082"
    assert cfg.user == "admin@example.com"
    assert cfg.password == "secret"
    assert cfg.teacher_device_unique_id == "my-device"


# ---------------------------------------------------------------------------
# _parse_traccar_time
# ---------------------------------------------------------------------------

def test_parse_traccar_time_iso_with_offset():
    dt = _parse_traccar_time("2026-05-10T01:28:27.000+00:00")
    assert dt.tzinfo is not None
    assert dt.year == 2026
    assert dt.hour == 1
    assert dt.minute == 28


def test_parse_traccar_time_z_suffix():
    dt = _parse_traccar_time("2026-05-10T03:25:27.839Z")
    assert dt.tzinfo is not None
    assert dt.year == 2026
    assert dt.hour == 3
    assert dt.minute == 25
    assert dt.second == 27


def test_parse_traccar_time_jst_offset():
    # +09:00 should be converted to UTC
    dt = _parse_traccar_time("2026-05-10T10:28:26.511+09:00")
    assert dt.tzinfo is not None
    assert dt.hour == 1   # 10:28 JST = 01:28 UTC
    assert dt.minute == 28


def test_parse_traccar_time_empty_returns_datetime():
    dt = _parse_traccar_time("")
    assert isinstance(dt, datetime)
    assert dt.tzinfo is not None


def test_parse_traccar_time_none_returns_datetime():
    dt = _parse_traccar_time(None)
    assert isinstance(dt, datetime)


# ---------------------------------------------------------------------------
# _parse_position (via TraccarClient static method)
# ---------------------------------------------------------------------------

def test_parse_position_basic():
    raw = {
        "deviceId": 2,
        "fixTime": "2026-05-10T03:25:27.839+00:00",
        "serverTime": "2026-05-10T03:25:28.105+00:00",
        "latitude": 35.725756,
        "longitude": 139.790950,
        "altitude": 0.0,
        "speed": 0.0,
        "course": 0.0,
        "accuracy": 0.0,
        "protocol": "osmand",
        "attributes": {"hdop": 12.287, "source": "osmand"},
    }
    pos = TraccarClient._parse_position(raw)
    assert pos.device_id == 2
    assert pos.latitude == pytest.approx(35.725756)
    assert pos.longitude == pytest.approx(139.790950)
    assert pos.protocol == "osmand"
    assert pos.attributes["source"] == "osmand"
    assert pos.fix_time.year == 2026


def test_parse_position_fixtime_fallback_to_servertime():
    raw = {
        "deviceId": 1,
        "fixTime": None,
        "deviceTime": None,
        "serverTime": "2026-05-10T03:25:28.105+00:00",
        "latitude": 35.0,
        "longitude": 139.0,
        "altitude": 0.0,
        "speed": 0.0,
        "course": 0.0,
        "accuracy": 0.0,
        "protocol": "osmand",
        "attributes": {},
    }
    pos = TraccarClient._parse_position(raw)
    assert pos.fix_time.year == 2026


# ---------------------------------------------------------------------------
# find_device_by_unique_id (mocked)
# ---------------------------------------------------------------------------

class _FakeOpener:
    """Minimal fake opener that returns preset JSON responses."""
    def __init__(self, responses: dict):
        self._responses = responses  # url_substring -> dict

    def open(self, req, *args, **kwargs):
        url = req.full_url if hasattr(req, "full_url") else str(req)
        for key, data in self._responses.items():
            if key in url:
                return _FakeResponse(json.dumps(data).encode())
        raise RuntimeError(f"No mock for URL: {url}")


class _FakeResponse:
    def __init__(self, data: bytes):
        self._data = data
        self.status = 200

    def read(self):
        return self._data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass


def _make_client_with_mock(responses: dict) -> TraccarClient:
    client = TraccarClient("http://mock", "user", "pass")
    client._opener = _FakeOpener(responses)
    return client


def test_find_device_by_unique_id_found():
    devices = [
        {"id": 1, "uniqueId": "pi-z2-wh", "name": "pi-z2-wh"},
        {"id": 2, "uniqueId": "osmand-yui-redmi-12-5g", "name": "osmand-yui-redmi-12-5g"},
    ]
    client = _make_client_with_mock({"/api/devices": devices})
    result = client.find_device_by_unique_id("osmand-yui-redmi-12-5g")
    assert result is not None
    assert result["id"] == 2


def test_find_device_by_unique_id_not_found():
    devices = [{"id": 1, "uniqueId": "pi-z2-wh", "name": "pi-z2-wh"}]
    client = _make_client_with_mock({"/api/devices": devices})
    result = client.find_device_by_unique_id("nonexistent")
    assert result is None


def test_get_positions_parses_list():
    raw_positions = [
        {
            "deviceId": 2,
            "fixTime": "2026-05-10T03:25:27.000+00:00",
            "serverTime": "2026-05-10T03:25:28.000+00:00",
            "deviceTime": "2026-05-10T03:25:27.000+00:00",
            "latitude": 35.725756,
            "longitude": 139.790950,
            "altitude": 0.0,
            "speed": 0.0,
            "course": 0.0,
            "accuracy": 0.0,
            "protocol": "osmand",
            "attributes": {},
        }
    ]
    client = _make_client_with_mock({"/api/positions": raw_positions})
    positions = client.get_positions(device_id=2)
    assert len(positions) == 1
    assert positions[0].latitude == pytest.approx(35.725756)
