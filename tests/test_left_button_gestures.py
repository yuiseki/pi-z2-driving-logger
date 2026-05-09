"""Tests for LeftButtonGestureDetector gesture recognition.

Uses real threading with very short timings to keep tests fast.
"""

from __future__ import annotations

import sys
import os
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pi_z2_driving_logger.left_button import LeftButtonGestureDetector

# Short timings for tests
LONG_PRESS_S = 0.15
DOUBLE_CLICK_MIN_S = 0.02
DOUBLE_CLICK_MAX_S = 0.10
DEBOUNCE_S = 0.005


def _make_detector(on_single=None, on_long=None, on_double=None):
    singles = []
    longs = []
    doubles = []

    def _single():
        singles.append(1)

    def _long():
        longs.append(1)

    def _double():
        doubles.append(1)

    det = LeftButtonGestureDetector(
        on_single=on_single or _single,
        on_long=on_long or _long,
        on_double=on_double or _double,
        long_press_s=LONG_PRESS_S,
        double_click_min_s=DOUBLE_CLICK_MIN_S,
        double_click_max_s=DOUBLE_CLICK_MAX_S,
        debounce_s=DEBOUNCE_S,
    )
    return det, singles, longs, doubles


class TestShortPressFiresSingle:
    def test_short_press_fires_single(self):
        det, singles, longs, doubles = _make_detector()
        try:
            det.on_press()
            time.sleep(0.01)   # brief hold, less than long_press_s
            det.on_release()
            # Wait for double-click window to expire
            time.sleep(DOUBLE_CLICK_MAX_S + 0.05)
            assert len(singles) == 1, f"expected 1 single, got {len(singles)}"
            assert len(longs) == 0
            assert len(doubles) == 0
        finally:
            det.stop()

    def test_single_confirmed_after_window_expires(self):
        det, singles, longs, doubles = _make_detector()
        try:
            det.on_press()
            time.sleep(0.01)
            det.on_release()
            # Before window expires, no single yet
            time.sleep(DOUBLE_CLICK_MAX_S * 0.5)
            assert len(singles) == 0, "single fired too early"
            # After window expires, single confirmed
            time.sleep(DOUBLE_CLICK_MAX_S + 0.05)
            assert len(singles) == 1
        finally:
            det.stop()


class TestLongPressFiresLong:
    def test_long_press_fires_long(self):
        det, singles, longs, doubles = _make_detector()
        try:
            det.on_press()
            time.sleep(LONG_PRESS_S + 0.05)  # hold past long_press threshold
            det.on_release()
            time.sleep(0.05)
            assert len(longs) == 1, f"expected 1 long, got {len(longs)}"
            assert len(singles) == 0
            assert len(doubles) == 0
        finally:
            det.stop()

    def test_long_press_does_not_fire_single(self):
        det, singles, longs, doubles = _make_detector()
        try:
            det.on_press()
            time.sleep(LONG_PRESS_S + 0.05)
            det.on_release()
            # Wait well past double-click window to ensure no single fires
            time.sleep(DOUBLE_CLICK_MAX_S + 0.1)
            assert len(singles) == 0, f"single should not fire after long press, got {len(singles)}"
            assert len(longs) == 1
        finally:
            det.stop()


class TestDoubleClickFiresDouble:
    def test_double_click_fires_double(self):
        det, singles, longs, doubles = _make_detector()
        try:
            # First press+release
            det.on_press()
            time.sleep(0.01)
            det.on_release()
            # Gap within window
            time.sleep(DOUBLE_CLICK_MIN_S + 0.01)
            # Second press+release
            det.on_press()
            time.sleep(0.01)
            det.on_release()
            time.sleep(0.05)
            assert len(doubles) == 1, f"expected 1 double, got {len(doubles)}"
            assert len(singles) == 0
            assert len(longs) == 0
        finally:
            det.stop()

    def test_double_click_does_not_fire_single(self):
        det, singles, longs, doubles = _make_detector()
        try:
            det.on_press()
            time.sleep(0.01)
            det.on_release()
            time.sleep(DOUBLE_CLICK_MIN_S + 0.01)
            det.on_press()
            time.sleep(0.01)
            det.on_release()
            # Wait past double-click window
            time.sleep(DOUBLE_CLICK_MAX_S + 0.1)
            assert len(singles) == 0, f"single should not fire after double click, got {len(singles)}"
            assert len(doubles) == 1
        finally:
            det.stop()


class TestStopCancelsPendingTimers:
    def test_stop_does_not_raise(self):
        det, singles, longs, doubles = _make_detector()
        det.on_press()
        det.stop()  # should cancel timers cleanly

    def test_stop_prevents_late_callbacks(self):
        det, singles, longs, doubles = _make_detector()
        det.on_press()
        time.sleep(0.01)
        det.on_release()
        det.stop()
        time.sleep(DOUBLE_CLICK_MAX_S + 0.1)
        # After stop, single should not have fired (timer cancelled)
        assert len(singles) == 0
