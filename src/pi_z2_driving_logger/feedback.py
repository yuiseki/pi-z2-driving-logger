"""Buzzer and LED feedback patterns for Maker pHAT."""

from __future__ import annotations

import logging
import threading
import time
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .phat import MakerPHAT

logger = logging.getLogger(__name__)


class BuzzerController:
    """Controls the active buzzer with named patterns."""

    def __init__(self, buzzer, long_ms: int = 500, short_ms: int = 100):
        self._buzzer = buzzer
        self._long_s = long_ms / 1000.0
        self._short_s = short_ms / 1000.0

    def long_beep(self) -> None:
        self._buzzer.on()
        time.sleep(self._long_s)
        self._buzzer.off()

    def short_beep(self) -> None:
        self._buzzer.on()
        time.sleep(self._short_s)
        self._buzzer.off()

    def _beep_pattern(self, pattern: list) -> None:
        """Execute a beep pattern.

        pattern: list of ('long'|'short'|'pause', duration_s)
        """
        for kind, dur in pattern:
            if kind == "long":
                self._buzzer.on()
                time.sleep(dur)
                self._buzzer.off()
            elif kind == "short":
                self._buzzer.on()
                time.sleep(dur)
                self._buzzer.off()
            elif kind == "pause":
                time.sleep(dur)

    def beep_startup(self) -> None:
        """short×2"""
        self.short_beep()
        time.sleep(0.1)
        self.short_beep()

    def beep_shutdown(self) -> None:
        """long + short"""
        self.long_beep()
        time.sleep(0.1)
        self.short_beep()

    def beep_self_start(self) -> None:
        """short, short, long (ピピピー) — switched to self (I am driving)"""
        self.short_beep()
        time.sleep(0.08)
        self.short_beep()
        time.sleep(0.08)
        self.long_beep()

    def beep_other_start(self) -> None:
        """short, short snappy (ピピッ) — switched to other"""
        self.short_beep()
        time.sleep(0.05)
        self.short_beep()

    def beep_no_fix_warning(self) -> None:
        """short×3 — no GPS fix"""
        for _ in range(3):
            self.short_beep()
            time.sleep(0.1)

    def beep_duplicate_warning(self) -> None:
        """short×3 — duplicate state transition"""
        for _ in range(3):
            self.short_beep()
            time.sleep(0.1)


class LEDController:
    """Controls LED array with state indicator and event animations.

    The state indicator runs in a background thread and can be paused
    while event animations play.
    """

    def __init__(
        self,
        leds: list,
        state_blink_interval_s: float = 1.0,
        error_blink_interval_s: float = 0.1,
        flow_step_s: float = 0.05,
        bounce_step_s: float = 0.05,
    ):
        self._leds = leds
        self._n = len(leds)
        self._state_blink_s = state_blink_interval_s
        self._error_blink_s = error_blink_interval_s
        self._flow_step_s = flow_step_s
        self._bounce_step_s = bounce_step_s

        self._pause_event = threading.Event()   # set = paused (animation running)
        self._stop_event = threading.Event()
        self._driver_state: str = "other"
        self._indicator_thread: Optional[threading.Thread] = None

    def start_indicator(self, driver_state: str = "other") -> None:
        """Start the background state indicator thread."""
        self._driver_state = driver_state
        self._stop_event.clear()
        self._indicator_thread = threading.Thread(
            target=self._indicator_loop, daemon=True, name="led-indicator"
        )
        self._indicator_thread.start()

    def stop_indicator(self) -> None:
        """Stop the background indicator thread."""
        self._stop_event.set()
        self._pause_event.set()  # unblock if paused
        if self._indicator_thread:
            self._indicator_thread.join(timeout=3.0)
        self.all_off()

    def set_driver_state(self, state: str) -> None:
        """Update the driver state shown by the indicator."""
        self._driver_state = state

    def _indicator_loop(self) -> None:
        while not self._stop_event.is_set():
            # Paused: wait until animation is done
            if self._pause_event.is_set():
                self._stop_event.wait(0.05)
                continue

            if self._driver_state == "self":
                self._blink_led(0, self._state_blink_s)
            else:
                self._blink_led(self._n - 1, self._state_blink_s)

    def _blink_led(self, idx: int, interval_s: float) -> None:
        """Blink a single LED once (on for interval_s/2, off for interval_s/2),
        checking for pause/stop between phases."""
        half = interval_s / 2.0
        self.all_off()
        self._leds[idx].on()
        # Sleep in small chunks to remain responsive
        elapsed = 0.0
        step = 0.05
        while elapsed < half:
            if self._stop_event.is_set() or self._pause_event.is_set():
                self._leds[idx].off()
                return
            time.sleep(min(step, half - elapsed))
            elapsed += step
        self._leds[idx].off()
        elapsed = 0.0
        while elapsed < half:
            if self._stop_event.is_set() or self._pause_event.is_set():
                return
            time.sleep(min(step, half - elapsed))
            elapsed += step

    def _pause_indicator(self) -> None:
        """Pause the indicator (call before running animation)."""
        self._pause_event.set()
        self.all_off()

    def _resume_indicator(self) -> None:
        """Resume the indicator after animation."""
        self._pause_event.clear()

    # -----------------------------------------------------------------------
    # LED primitive operations
    # -----------------------------------------------------------------------

    def all_on(self) -> None:
        for led in self._leds:
            led.on()

    def all_off(self) -> None:
        for led in self._leds:
            led.off()

    def blink_all(self, count: int = 3, interval: float = 0.1) -> None:
        for _ in range(count):
            self.all_on()
            time.sleep(interval)
            self.all_off()
            time.sleep(interval)

    def flow_left_to_right(self) -> None:
        self.all_off()
        for i in range(self._n):
            self._leds[i].on()
            time.sleep(self._flow_step_s)
            self._leds[i].off()

    def flow_right_to_left(self) -> None:
        self.all_off()
        for i in range(self._n - 1, -1, -1):
            self._leds[i].on()
            time.sleep(self._flow_step_s)
            self._leds[i].off()

    def bounce(self) -> None:
        self.all_off()
        for i in list(range(self._n)) + list(range(self._n - 2, 0, -1)):
            self._leds[i].on()
            time.sleep(self._bounce_step_s)
            self._leds[i].off()

    def error_flash(self, count: int = 5) -> None:
        self.blink_all(count=count, interval=self._error_blink_s)

    # -----------------------------------------------------------------------
    # State-change animations (run in a temporary thread, non-blocking)
    # -----------------------------------------------------------------------

    def _run_animation(self, fn, *args, **kwargs) -> None:
        """Pause indicator, run animation fn, resume indicator."""
        def _worker():
            self._pause_indicator()
            try:
                fn(*args, **kwargs)
            finally:
                self._resume_indicator()

        t = threading.Thread(target=_worker, daemon=True, name="led-anim")
        t.start()

    def state_indicator_self(self) -> None:
        """Immediately switch to self indicator (rightmost LED slow blink)."""
        self.set_driver_state("self")

    def state_indicator_other(self) -> None:
        """Immediately switch to other indicator (leftmost LED slow blink)."""
        self.set_driver_state("other")

    def animate_switch_to_self(self) -> None:
        """Non-blocking animation for switching to self."""
        self._run_animation(self.flow_right_to_left)

    def animate_switch_to_other(self) -> None:
        """Non-blocking animation for switching to other."""
        self._run_animation(self.flow_left_to_right)

    def animate_error(self) -> None:
        """Non-blocking error flash animation."""
        self._run_animation(self.error_flash)


class FeedbackController:
    """Combines buzzer and LED feedback for high-level events."""

    def __init__(self, phat: "MakerPHAT", config=None):
        from .config import Config
        cfg = config or Config()
        self.buzzer = BuzzerController(
            phat.buzzer,
            long_ms=cfg.buzzer_long_ms,
            short_ms=cfg.buzzer_short_ms,
        )
        self.leds = LEDController(
            phat.leds,
            state_blink_interval_s=cfg.led_state_blink_interval_s,
            error_blink_interval_s=cfg.led_error_blink_interval_s,
            flow_step_s=cfg.led_flow_step_s,
            bounce_step_s=cfg.led_bounce_step_s,
        )

    def startup(self, driver_state: str = "other") -> None:
        self.buzzer.beep_startup()
        self.leds.start_indicator(driver_state)

    def shutdown(self) -> None:
        self.leds.stop_indicator()
        self.buzzer.beep_shutdown()

    def on_switch_to_self(self) -> None:
        self.leds.state_indicator_self()
        self.leds.animate_switch_to_self()
        threading.Thread(target=self.buzzer.beep_self_start, daemon=True).start()

    def on_switch_to_other(self) -> None:
        self.leds.state_indicator_other()
        self.leds.animate_switch_to_other()
        threading.Thread(target=self.buzzer.beep_other_start, daemon=True).start()

    def on_no_fix_warning(self) -> None:
        self.leds.animate_error()
        threading.Thread(target=self.buzzer.beep_no_fix_warning, daemon=True).start()

    def on_duplicate_warning(self) -> None:
        threading.Thread(target=self.buzzer.beep_duplicate_warning, daemon=True).start()
