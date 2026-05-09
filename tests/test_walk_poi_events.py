"""Tests for make_walk_poi_event() helper in left_button module.

These tests verify the event dict structure and field values.
"""

from __future__ import annotations

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pi_z2_driving_logger.left_button import make_walk_poi_event
from pi_z2_driving_logger.gps import GPSState


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_fix_state() -> GPSState:
    s = GPSState()
    s.lat = 35.6895
    s.lon = 139.6917
    s.fix_valid = True
    s.fix_quality = 1
    s.satellites_used = 8
    s.hdop = 1.2
    s.timestamp = "120000.00"
    return s


def _make_nofix_state() -> GPSState:
    s = GPSState()
    s.lat = None
    s.lon = None
    s.fix_valid = False
    s.fix_quality = 0
    s.satellites_used = 0
    s.hdop = None
    s.timestamp = ""
    return s


# ---------------------------------------------------------------------------
# event_type tests
# ---------------------------------------------------------------------------

class TestWalkPoiEventType:
    def test_walk_poi_event_type(self):
        gps = _make_fix_state()
        event = make_walk_poi_event("walk_poi", gps, "other")
        assert event["type"] == "walk_poi"

    def test_walk_poi_important_event_type(self):
        gps = _make_fix_state()
        event = make_walk_poi_event("walk_poi_important", gps, "self")
        assert event["type"] == "walk_poi_important"

    def test_walk_poi_double_event_type(self):
        gps = _make_fix_state()
        event = make_walk_poi_event("walk_poi_double", gps, "other")
        assert event["type"] == "walk_poi_double"


# ---------------------------------------------------------------------------
# driver_state tests
# ---------------------------------------------------------------------------

class TestDriverState:
    def test_event_does_not_change_driver_state(self):
        gps = _make_fix_state()
        original_driver_state = "self"
        event = make_walk_poi_event("walk_poi", gps, original_driver_state)
        assert event["driver_state"] == original_driver_state

    def test_event_driver_state_other(self):
        gps = _make_fix_state()
        event = make_walk_poi_event("walk_poi", gps, "other")
        assert event["driver_state"] == "other"


# ---------------------------------------------------------------------------
# GPS fix / no-fix tests
# ---------------------------------------------------------------------------

class TestEventGPSFields:
    def test_event_with_fix_includes_lat_lon(self):
        gps = _make_fix_state()
        event = make_walk_poi_event("walk_poi", gps, "other")
        assert event["lat"] == 35.6895
        assert event["lon"] == 139.6917

    def test_event_without_fix_lat_lon_is_none(self):
        gps = _make_nofix_state()
        event = make_walk_poi_event("walk_poi", gps, "other")
        assert event["lat"] is None
        assert event["lon"] is None

    def test_event_without_fix_fix_valid_is_false(self):
        gps = _make_nofix_state()
        event = make_walk_poi_event("walk_poi", gps, "other")
        assert event["fix_valid"] is False

    def test_event_with_fix_fix_valid_is_true(self):
        gps = _make_fix_state()
        event = make_walk_poi_event("walk_poi", gps, "other")
        assert event["fix_valid"] is True


# ---------------------------------------------------------------------------
# Required fields
# ---------------------------------------------------------------------------

REQUIRED_FIELDS = {
    "type",
    "system_time",
    "driver_state",
    "lat",
    "lon",
    "fix_valid",
    "fix_quality",
    "satellites_used",
    "hdop",
    "nmea_time",
    "source",
}


class TestRequiredFields:
    def test_event_has_required_fields(self):
        gps = _make_fix_state()
        event = make_walk_poi_event("walk_poi", gps, "other")
        missing = REQUIRED_FIELDS - set(event.keys())
        assert not missing, f"Missing fields: {missing}"

    def test_source_is_maker_phat_left_button(self):
        gps = _make_fix_state()
        event = make_walk_poi_event("walk_poi", gps, "other")
        assert event["source"] == "maker_phat_left_button"

    def test_system_time_is_string(self):
        gps = _make_fix_state()
        event = make_walk_poi_event("walk_poi", gps, "other")
        assert isinstance(event["system_time"], str)
        assert len(event["system_time"]) > 0

    def test_nmea_time_matches_gps_timestamp(self):
        gps = _make_fix_state()
        event = make_walk_poi_event("walk_poi", gps, "other")
        assert event["nmea_time"] == gps.timestamp

    def test_fix_quality_matches_gps(self):
        gps = _make_fix_state()
        event = make_walk_poi_event("walk_poi", gps, "other")
        assert event["fix_quality"] == gps.fix_quality

    def test_satellites_used_matches_gps(self):
        gps = _make_fix_state()
        event = make_walk_poi_event("walk_poi", gps, "other")
        assert event["satellites_used"] == gps.satellites_used

    def test_hdop_matches_gps(self):
        gps = _make_fix_state()
        event = make_walk_poi_event("walk_poi", gps, "other")
        assert event["hdop"] == gps.hdop
