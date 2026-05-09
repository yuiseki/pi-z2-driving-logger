"""Tests for LEDController state indicator behavior.

State indicator must use steady-on (not blinking) for both self and other.
"""

from __future__ import annotations

import sys
import os
import time
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pi_z2_driving_logger.feedback import LEDController


class _TrackingLED:
    def __init__(self):
        self.is_active = False
        self.on_count = 0
        self.off_count = 0

    def on(self):
        self.is_active = True
        self.on_count += 1

    def off(self):
        self.is_active = False
        self.off_count += 1

    def close(self):
        pass


def _make_controller(n: int = 8):
    leds = [_TrackingLED() for _ in range(n)]
    ctrl = LEDController(
        leds=leds,
        state_blink_interval_s=0.05,
        error_blink_interval_s=0.05,
        flow_step_s=0.01,
        bounce_step_s=0.01,
    )
    return ctrl, leds


class TestStateIndicatorSteadyOn:
    def test_self_state_lights_leftmost_led(self):
        ctrl, leds = _make_controller()
        ctrl.start_indicator("self")
        time.sleep(0.15)
        ctrl.stop_indicator()
        assert leds[0].is_active or leds[0].on_count > 0

    def test_other_state_lights_rightmost_led(self):
        ctrl, leds = _make_controller()
        ctrl.start_indicator("other")
        time.sleep(0.15)
        ctrl.stop_indicator()
        assert leds[-1].is_active or leds[-1].on_count > 0

    def test_self_indicator_does_not_blink(self):
        """Steady-on: LED should turn on once and stay, not toggle repeatedly."""
        ctrl, leds = _make_controller()
        ctrl.start_indicator("self")
        time.sleep(0.3)
        ctrl.stop_indicator()
        # With steady-on, on_count should be 1 (turned on once per state change)
        # With blinking, on_count would be many (toggles every interval)
        assert leds[0].on_count <= 2, (
            f"LED blinked {leds[0].on_count} times — expected steady-on (≤2)"
        )

    def test_other_indicator_does_not_blink(self):
        """Steady-on: LED should turn on once and stay, not toggle repeatedly."""
        ctrl, leds = _make_controller()
        ctrl.start_indicator("other")
        time.sleep(0.3)
        ctrl.stop_indicator()
        assert leds[-1].on_count <= 2, (
            f"LED blinked {leds[-1].on_count} times — expected steady-on (≤2)"
        )

    def test_state_change_switches_led(self):
        """Switching state should light the new LED and leave the old one off."""
        ctrl, leds = _make_controller()
        ctrl.start_indicator("other")
        time.sleep(0.1)
        ctrl.set_driver_state("self")
        time.sleep(0.1)
        ctrl.stop_indicator()
        # leftmost was turned on after switching to self
        assert leds[0].on_count >= 1
        # rightmost was only lit during 'other' phase; on_count must be exactly 1
        assert leds[-1].on_count == 1
