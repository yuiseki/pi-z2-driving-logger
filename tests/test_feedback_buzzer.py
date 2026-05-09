"""Tests for BuzzerController beep patterns.

Each beep = 1 buzzer.on() + 1 buzzer.off() call.
Tests verify exact beep counts regardless of GPS fix status.
"""

from __future__ import annotations

import sys
import os
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pi_z2_driving_logger.feedback import BuzzerController


class _CountingBuzzer:
    """Records on/off calls without sleeping."""
    def __init__(self):
        self.beeps: list[str] = []  # 'on' or 'off'

    def on(self):
        self.beeps.append("on")

    def off(self):
        self.beeps.append("off")

    @property
    def on_count(self) -> int:
        return self.beeps.count("on")

    @property
    def off_count(self) -> int:
        return self.beeps.count("off")

    @property
    def beep_count(self) -> int:
        return self.on_count  # each on() is one beep


def _make_controller(buzzer) -> BuzzerController:
    return BuzzerController(buzzer, long_ms=1, short_ms=1)


# ---------------------------------------------------------------------------
# beep_other_start: must be exactly 2 beeps
# ---------------------------------------------------------------------------

class TestBeepOtherStart:
    def test_produces_exactly_2_beeps(self):
        b = _CountingBuzzer()
        ctrl = _make_controller(b)
        with patch("time.sleep"):
            ctrl.beep_other_start()
        assert b.beep_count == 2, f"expected 2 beeps, got {b.beep_count}"

    def test_pattern_is_on_off_on_off(self):
        b = _CountingBuzzer()
        ctrl = _make_controller(b)
        with patch("time.sleep"):
            ctrl.beep_other_start()
        assert b.beeps == ["on", "off", "on", "off"]

    def test_produces_exactly_2_beeps_regardless_of_fix(self):
        """GPS fix status must not change the beep count."""
        for fix_valid in (True, False):
            b = _CountingBuzzer()
            ctrl = _make_controller(b)
            with patch("time.sleep"):
                ctrl.beep_other_start(fix_valid=fix_valid)
            assert b.beep_count == 2, (
                f"fix_valid={fix_valid}: expected 2 beeps, got {b.beep_count}"
            )


# ---------------------------------------------------------------------------
# beep_self_start: must be exactly 3 beeps (short, short, long)
# ---------------------------------------------------------------------------

class TestBeepSelfStart:
    def test_produces_exactly_3_beeps(self):
        b = _CountingBuzzer()
        ctrl = _make_controller(b)
        with patch("time.sleep"):
            ctrl.beep_self_start()
        assert b.beep_count == 3, f"expected 3 beeps, got {b.beep_count}"

    def test_pattern_is_on_off_x3(self):
        b = _CountingBuzzer()
        ctrl = _make_controller(b)
        with patch("time.sleep"):
            ctrl.beep_self_start()
        assert b.beeps == ["on", "off", "on", "off", "on", "off"]

    def test_produces_exactly_3_beeps_regardless_of_fix(self):
        """GPS fix status must not change the beep count."""
        for fix_valid in (True, False):
            b = _CountingBuzzer()
            ctrl = _make_controller(b)
            with patch("time.sleep"):
                ctrl.beep_self_start(fix_valid=fix_valid)
            assert b.beep_count == 3, (
                f"fix_valid={fix_valid}: expected 3 beeps, got {b.beep_count}"
            )


# ---------------------------------------------------------------------------
# other patterns: sanity checks
# ---------------------------------------------------------------------------

class TestOtherPatterns:
    def test_beep_startup_is_2(self):
        b = _CountingBuzzer()
        ctrl = _make_controller(b)
        with patch("time.sleep"):
            ctrl.beep_startup()
        assert b.beep_count == 2

    def test_beep_shutdown_is_2(self):
        b = _CountingBuzzer()
        ctrl = _make_controller(b)
        with patch("time.sleep"):
            ctrl.beep_shutdown()
        assert b.beep_count == 2

    def test_beep_no_fix_warning_is_3(self):
        b = _CountingBuzzer()
        ctrl = _make_controller(b)
        with patch("time.sleep"):
            ctrl.beep_no_fix_warning()
        assert b.beep_count == 3

    def test_beep_duplicate_warning_is_3(self):
        b = _CountingBuzzer()
        ctrl = _make_controller(b)
        with patch("time.sleep"):
            ctrl.beep_duplicate_warning()
        assert b.beep_count == 3
