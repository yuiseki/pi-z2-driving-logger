"""Tests for state_machine.py — DriverStateMachine."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from pi_z2_driving_logger.state_machine import DriverStateMachine
from pi_z2_driving_logger.gps import GPSState


def make_gps_state(
    lat=35.0,
    lon=139.0,
    fix_valid=True,
    fix_quality=1,
    satellites_used=7,
    hdop=1.96,
    timestamp="073000.00",
) -> GPSState:
    return GPSState(
        timestamp=timestamp,
        lat=lat,
        lon=lon,
        fix_valid=fix_valid,
        fix_quality=fix_quality,
        satellites_used=satellites_used,
        hdop=hdop,
    )


class TestInitialState:
    def test_initial_state_is_other(self):
        sm = DriverStateMachine()
        assert sm.state == "other"

    def test_initial_state_can_be_self(self):
        sm = DriverStateMachine(initial_state="self")
        assert sm.state == "self"

    def test_invalid_initial_state_raises(self):
        with pytest.raises(ValueError):
            DriverStateMachine(initial_state="unknown")


class TestTransitionOtherToSelf:
    def test_other_to_self_returns_event(self):
        sm = DriverStateMachine(initial_state="other")
        gps = make_gps_state()
        event = sm.transition("self", gps, source="maker_phat")
        assert event is not None
        assert isinstance(event, dict)

    def test_other_to_self_event_type(self):
        sm = DriverStateMachine(initial_state="other")
        event = sm.transition("self", make_gps_state(), source="maker_phat")
        assert event["type"] == "driver_state_changed_to_self"

    def test_other_to_self_state_before_after(self):
        sm = DriverStateMachine(initial_state="other")
        event = sm.transition("self", make_gps_state(), source="maker_phat")
        assert event["driver_state_before"] == "other"
        assert event["driver_state_after"] == "self"

    def test_state_changes_after_transition(self):
        sm = DriverStateMachine(initial_state="other")
        sm.transition("self", make_gps_state())
        assert sm.state == "self"

    def test_other_to_self_event_has_gps_data(self):
        sm = DriverStateMachine(initial_state="other")
        gps = make_gps_state(lat=35.123, lon=139.456, fix_valid=True, fix_quality=1)
        event = sm.transition("self", gps, source="maker_phat")
        assert abs(event["lat"] - 35.123) < 1e-6
        assert abs(event["lon"] - 139.456) < 1e-6
        assert event["fix_valid"] is True

    def test_other_to_self_event_has_required_fields(self):
        sm = DriverStateMachine(initial_state="other")
        gps = make_gps_state()
        event = sm.transition("self", gps, source="maker_phat")
        required = [
            "type", "system_time", "driver_state_before", "driver_state_after",
            "lat", "lon", "fix_valid", "source",
        ]
        for field in required:
            assert field in event, f"Missing field: {field}"

    def test_other_to_self_source(self):
        sm = DriverStateMachine(initial_state="other")
        event = sm.transition("self", make_gps_state(), source="maker_phat")
        assert event["source"] == "maker_phat"


class TestTransitionSelfToOther:
    def test_self_to_other_event_type(self):
        sm = DriverStateMachine(initial_state="self")
        event = sm.transition("other", make_gps_state(), source="maker_phat")
        assert event["type"] == "driver_state_changed_to_other"

    def test_self_to_other_state_before_after(self):
        sm = DriverStateMachine(initial_state="self")
        event = sm.transition("other", make_gps_state(), source="maker_phat")
        assert event["driver_state_before"] == "self"
        assert event["driver_state_after"] == "other"

    def test_state_changes_to_other(self):
        sm = DriverStateMachine(initial_state="self")
        sm.transition("other", make_gps_state())
        assert sm.state == "other"


class TestDuplicateTransitions:
    def test_duplicate_self_to_self(self):
        sm = DriverStateMachine(initial_state="self")
        event = sm.transition("self", make_gps_state(), source="maker_phat")
        assert event["type"] == "ignored_duplicate_self"

    def test_duplicate_other_to_other(self):
        sm = DriverStateMachine(initial_state="other")
        event = sm.transition("other", make_gps_state(), source="maker_phat")
        assert event["type"] == "ignored_duplicate_other"

    def test_duplicate_does_not_change_state(self):
        sm = DriverStateMachine(initial_state="self")
        sm.transition("self", make_gps_state())
        assert sm.state == "self"

    def test_duplicate_event_has_same_before_after(self):
        sm = DriverStateMachine(initial_state="self")
        event = sm.transition("self", make_gps_state(), source="maker_phat")
        assert event["driver_state_before"] == "self"
        assert event["driver_state_after"] == "self"

    def test_duplicate_event_has_required_fields(self):
        sm = DriverStateMachine(initial_state="other")
        gps = make_gps_state()
        event = sm.transition("other", gps, source="maker_phat")
        required = [
            "type", "system_time", "driver_state_before", "driver_state_after",
            "lat", "lon", "fix_valid", "source",
        ]
        for field in required:
            assert field in event, f"Missing field: {field}"


class TestEventFields:
    def test_event_contains_fix_quality(self):
        sm = DriverStateMachine(initial_state="other")
        gps = make_gps_state(fix_quality=2)
        event = sm.transition("self", gps)
        assert event["fix_quality"] == 2

    def test_event_contains_satellites_used(self):
        sm = DriverStateMachine(initial_state="other")
        gps = make_gps_state(satellites_used=9)
        event = sm.transition("self", gps)
        assert event["satellites_used"] == 9

    def test_event_contains_hdop(self):
        sm = DriverStateMachine(initial_state="other")
        gps = make_gps_state(hdop=1.5)
        event = sm.transition("self", gps)
        assert event["hdop"] is not None
        assert abs(event["hdop"] - 1.5) < 1e-6

    def test_event_contains_nmea_time(self):
        sm = DriverStateMachine(initial_state="other")
        gps = make_gps_state(timestamp="123456.00")
        event = sm.transition("self", gps)
        assert event["nmea_time"] == "123456.00"

    def test_event_system_time_is_string(self):
        sm = DriverStateMachine(initial_state="other")
        event = sm.transition("self", make_gps_state())
        assert isinstance(event["system_time"], str)
        assert len(event["system_time"]) > 0

    def test_event_system_time_has_timezone(self):
        sm = DriverStateMachine(initial_state="other")
        event = sm.transition("self", make_gps_state())
        # ISO 8601 with timezone contains + or Z
        ts = event["system_time"]
        assert "+" in ts or "Z" in ts or "-" in ts[10:], f"No timezone in {ts!r}"

    def test_transition_with_no_fix(self):
        sm = DriverStateMachine(initial_state="other")
        gps = make_gps_state(fix_valid=False, fix_quality=0, lat=None, lon=None)
        event = sm.transition("self", gps)
        assert event["fix_valid"] is False
        assert event["lat"] is None
        assert event["lon"] is None

    def test_invalid_new_state_raises(self):
        sm = DriverStateMachine(initial_state="other")
        with pytest.raises(ValueError):
            sm.transition("invalid_state", make_gps_state())
