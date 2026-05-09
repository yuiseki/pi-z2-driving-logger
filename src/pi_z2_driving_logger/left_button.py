"""Left button gesture detection and walk-POI event helpers.

No hardware imports — safe to import in any environment.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Callable, Optional

from .gps import GPSState


class LeftButtonGestureDetector:
    """Detects single click, long press, and double click on the left button.

    Gesture rules:
    - Long press (held >= long_press_s): fires on_long.  Does NOT fire on_single.
    - Double click (two presses within double_click_min_s..double_click_max_s):
      fires on_double.  Does NOT fire on_single.
    - Single click: short press with no second press within double_click_max_s
      fires on_single (confirmed after the window expires).

    Usage::

        detector = LeftButtonGestureDetector(on_single=..., on_long=..., on_double=...)
        # Wire to hardware:
        button.when_pressed = detector.on_press
        button.when_released = detector.on_release
        # On teardown:
        detector.stop()
    """

    def __init__(
        self,
        on_single: Callable[[], None],
        on_long: Callable[[], None],
        on_double: Callable[[], None],
        long_press_s: float = 1.0,
        double_click_min_s: float = 0.1,
        double_click_max_s: float = 0.6,
        debounce_s: float = 0.05,
    ) -> None:
        self._on_single = on_single
        self._on_long = on_long
        self._on_double = on_double
        self._long_press_s = long_press_s
        self._double_click_min_s = double_click_min_s
        self._double_click_max_s = double_click_max_s
        self._debounce_s = debounce_s

        self._lock = threading.Lock()
        self._stopped = False

        # Long press state
        self._long_press_timer: Optional[threading.Timer] = None
        self._long_consumed = False
        self._pressed_at: Optional[float] = None

        # Click counting state
        self._click_count = 0
        self._first_click_at: Optional[float] = None
        self._double_click_timer: Optional[threading.Timer] = None

    # -----------------------------------------------------------------------
    # Public interface
    # -----------------------------------------------------------------------

    def on_press(self) -> None:
        """Call when the button is pressed."""
        now = time.monotonic()
        with self._lock:
            if self._stopped:
                return

            # Debounce: ignore if already pressed
            if self._pressed_at is not None:
                return

            self._pressed_at = now
            self._long_consumed = False

            # Start long-press timer
            self._long_press_timer = threading.Timer(
                self._long_press_s, self._long_press_fired
            )
            self._long_press_timer.daemon = True
            self._long_press_timer.start()

    def on_release(self) -> None:
        """Call when the button is released."""
        with self._lock:
            if self._stopped:
                return
            if self._pressed_at is None:
                return

            release_time = time.monotonic()
            press_time = self._pressed_at
            self._pressed_at = None

            # Cancel long-press timer
            if self._long_press_timer is not None:
                self._long_press_timer.cancel()
                self._long_press_timer = None

            if self._long_consumed:
                # Long press already handled; ignore this release
                self._long_consumed = False
                return

            # Short press — handle click counting
            self._handle_click(press_time, release_time)

    def stop(self) -> None:
        """Cancel all pending timers and stop accepting events."""
        with self._lock:
            self._stopped = True
            if self._long_press_timer is not None:
                self._long_press_timer.cancel()
                self._long_press_timer = None
            if self._double_click_timer is not None:
                self._double_click_timer.cancel()
                self._double_click_timer = None

    # -----------------------------------------------------------------------
    # Internal handlers
    # -----------------------------------------------------------------------

    def _long_press_fired(self) -> None:
        """Called by threading.Timer when long-press threshold is reached."""
        with self._lock:
            if self._stopped:
                return
            if self._pressed_at is None:
                # Released before timer fired (race); ignore
                return
            self._long_press_timer = None
            self._long_consumed = True
        # Fire callback outside the lock
        self._on_long()

    def _handle_click(self, press_time: float, release_time: float) -> None:
        """Handle a completed short press within the lock.

        Called while holding self._lock.
        """
        now = release_time

        if self._click_count == 0:
            # First click
            self._click_count = 1
            self._first_click_at = now
            # Start double-click window timer
            self._double_click_timer = threading.Timer(
                self._double_click_max_s, self._double_click_window_expired
            )
            self._double_click_timer.daemon = True
            self._double_click_timer.start()
        else:
            # Potential second click
            gap = now - self._first_click_at
            if gap >= self._double_click_min_s:
                # Confirmed double click
                if self._double_click_timer is not None:
                    self._double_click_timer.cancel()
                    self._double_click_timer = None
                self._click_count = 0
                self._first_click_at = None
                # Fire callback outside lock — schedule via thread
                threading.Thread(target=self._on_double, daemon=True).start()
            else:
                # Too fast (debounce) — treat as first click reset
                if self._double_click_timer is not None:
                    self._double_click_timer.cancel()
                self._click_count = 1
                self._first_click_at = now
                self._double_click_timer = threading.Timer(
                    self._double_click_max_s, self._double_click_window_expired
                )
                self._double_click_timer.daemon = True
                self._double_click_timer.start()

    def _double_click_window_expired(self) -> None:
        """Called by timer when the double-click window expires without a second click."""
        should_fire = False
        with self._lock:
            if self._stopped:
                return
            if self._click_count == 1:
                self._click_count = 0
                self._first_click_at = None
                self._double_click_timer = None
                should_fire = True

        if should_fire:
            self._on_single()


# ---------------------------------------------------------------------------
# Walk-POI event factory
# ---------------------------------------------------------------------------

def make_walk_poi_event(event_type: str, gps_state: GPSState, driver_state: str) -> dict:
    """Build a walk-POI event dict from GPS state and driver state.

    The event does NOT modify driver_state; it records the current state.
    """
    return {
        "type": event_type,
        "system_time": datetime.now().astimezone().isoformat(),
        "driver_state": driver_state,
        "lat": gps_state.lat,
        "lon": gps_state.lon,
        "fix_valid": gps_state.fix_valid,
        "fix_quality": gps_state.fix_quality,
        "satellites_used": gps_state.satellites_used,
        "hdop": gps_state.hdop,
        "nmea_time": gps_state.timestamp,
        "source": "maker_phat_left_button",
    }
