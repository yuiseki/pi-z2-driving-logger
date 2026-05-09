"""Main entry point for pi-z2-driving-logger."""

from __future__ import annotations

import argparse
import logging
import signal
import sys
import threading
import time
from typing import Optional

from .config import Config, GPS_DEVICE_PRIMARY, GPS_DEVICE_FALLBACK, LOG_DIR_DEFAULT
from .gps import GPSReader, GPSState
from .nmea import parse_nmea_sentence
from .phat import MakerPHAT
from .feedback import FeedbackController
from .state_machine import DriverStateMachine
from .storage import StorageManager

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("pi_z2_driving_logger.main")


# ---------------------------------------------------------------------------
# Button logic helpers
# ---------------------------------------------------------------------------

class ButtonHandler:
    """Manages chord and double-click detection for Maker pHAT buttons.

    Center + Right chord (held 1s) → driver_state = self
    Right double-click (within 600ms window) → driver_state = other
    Left button → log POI (reserved)
    """

    def __init__(self, phat: MakerPHAT, config: Config, on_self_cb, on_other_cb, on_left_cb):
        self._phat = phat
        self._cfg = config
        self._on_self = on_self_cb
        self._on_other = on_other_cb
        self._on_left = on_left_cb

        # Chord state
        self._chord_lock = threading.Lock()
        self._center_pressed_at: Optional[float] = None
        self._right_pressed_at: Optional[float] = None
        self._chord_candidate = False
        self._chord_thread: Optional[threading.Thread] = None

        # Double-click state
        self._dclick_lock = threading.Lock()
        self._first_click_at: Optional[float] = None
        self._dclick_timer: Optional[threading.Timer] = None

        self._stop_event = threading.Event()
        self._poll_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start polling buttons (fallback when callbacks not available on mock)."""
        self._install_callbacks()
        # Also start a polling thread for robustness / mock support
        self._poll_thread = threading.Thread(
            target=self._poll_loop, daemon=True, name="btn-poll"
        )
        self._poll_thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._poll_thread:
            self._poll_thread.join(timeout=2.0)
        if self._dclick_timer:
            self._dclick_timer.cancel()

    def _install_callbacks(self) -> None:
        """Install gpiozero callbacks if available."""
        btn_center = self._phat.btn_center
        btn_right = self._phat.btn_right
        btn_left = self._phat.btn_left

        if self._phat.is_gpio_available():
            btn_center.when_pressed = self._center_pressed
            btn_center.when_released = self._center_released
            btn_right.when_pressed = self._right_pressed
            btn_right.when_released = self._right_released
            btn_left.when_pressed = self._left_pressed
        # On mock, we rely entirely on the polling thread

    def _poll_loop(self) -> None:
        """Poll button states when running on mock GPIO."""
        if self._phat.is_gpio_available():
            # Callbacks are installed; polling not needed
            while not self._stop_event.is_set():
                self._stop_event.wait(1.0)
            return

        # On mock GPIO we cannot simulate button presses, so just idle
        while not self._stop_event.is_set():
            self._stop_event.wait(0.05)

    # -----------------------------------------------------------------------
    # Center button events
    # -----------------------------------------------------------------------

    def _center_pressed(self) -> None:
        with self._chord_lock:
            self._center_pressed_at = time.monotonic()
            self._check_chord_candidate()

    def _center_released(self) -> None:
        with self._chord_lock:
            self._center_pressed_at = None
            self._chord_candidate = False

    # -----------------------------------------------------------------------
    # Right button events
    # -----------------------------------------------------------------------

    def _right_pressed(self) -> None:
        now = time.monotonic()
        with self._chord_lock:
            self._right_pressed_at = now
            self._check_chord_candidate()

        # Double-click detection runs independently
        self._handle_right_click(now)

    def _right_released(self) -> None:
        with self._chord_lock:
            self._right_pressed_at = None
            self._chord_candidate = False

    def _handle_right_click(self, now: float) -> None:
        with self._dclick_lock:
            if self._first_click_at is None:
                # First click
                self._first_click_at = now
                # Start timer to reset if no second click
                self._dclick_timer = threading.Timer(
                    self._cfg.double_click_max_s, self._dclick_timeout
                )
                self._dclick_timer.start()
            else:
                # Potential second click
                gap = now - self._first_click_at
                if self._cfg.double_click_min_s <= gap <= self._cfg.double_click_max_s:
                    # Confirmed double-click
                    if self._dclick_timer:
                        self._dclick_timer.cancel()
                    self._first_click_at = None
                    self._dclick_timer = None
                    threading.Thread(target=self._on_other, daemon=True).start()
                else:
                    # Too fast or too slow; treat as new first click
                    if self._dclick_timer:
                        self._dclick_timer.cancel()
                    self._first_click_at = now
                    self._dclick_timer = threading.Timer(
                        self._cfg.double_click_max_s, self._dclick_timeout
                    )
                    self._dclick_timer.start()

    def _dclick_timeout(self) -> None:
        with self._dclick_lock:
            self._first_click_at = None
            self._dclick_timer = None

    # -----------------------------------------------------------------------
    # Left button
    # -----------------------------------------------------------------------

    def _left_pressed(self) -> None:
        threading.Thread(target=self._on_left, daemon=True).start()

    # -----------------------------------------------------------------------
    # Chord detection
    # -----------------------------------------------------------------------

    def _check_chord_candidate(self) -> None:
        """Called under _chord_lock. Check if a chord candidate should be started."""
        if self._chord_candidate:
            return
        if self._center_pressed_at is None or self._right_pressed_at is None:
            return
        gap = abs(self._center_pressed_at - self._right_pressed_at)
        if gap <= self._cfg.chord_window_s:
            self._chord_candidate = True
            t = threading.Thread(target=self._chord_hold_check, daemon=True, name="chord-check")
            t.start()

    def _chord_hold_check(self) -> None:
        """Wait for chord to be held for chord_hold_s seconds."""
        deadline = time.monotonic() + self._cfg.chord_hold_s
        while time.monotonic() < deadline:
            with self._chord_lock:
                if not self._chord_candidate:
                    return  # Released too early
                if self._center_pressed_at is None or self._right_pressed_at is None:
                    self._chord_candidate = False
                    return
            time.sleep(0.02)

        # If chord_candidate still True after hold duration, confirm
        with self._chord_lock:
            if self._chord_candidate:
                self._chord_candidate = False

        threading.Thread(target=self._on_self, daemon=True).start()


# ---------------------------------------------------------------------------
# Main application
# ---------------------------------------------------------------------------

class DrivingLogger:
    """Top-level application controller."""

    def __init__(self, config: Config):
        self._cfg = config
        self._shutdown = threading.Event()
        self._storage: Optional[StorageManager] = None
        self._gps: Optional[GPSReader] = None
        self._phat: Optional[MakerPHAT] = None
        self._feedback: Optional[FeedbackController] = None
        self._state_machine: Optional[DriverStateMachine] = None
        self._btn_handler: Optional[ButtonHandler] = None

    def run(self) -> None:
        """Initialize all components and enter the main loop."""
        logger.info("=== pi-z2-driving-logger starting ===")

        # Storage
        self._storage = StorageManager(
            self._cfg.log_dir,
            gpx_flush_interval_s=self._cfg.gpx_flush_interval_s,
        )
        logger.info("Session: %s", self._storage.session_dir)

        # GPS
        self._gps = GPSReader(
            device_path=self._cfg.gps_device,
            baud_rate=self._cfg.gps_baud_rate,
            raw_nmea_path=self._storage.raw_nmea_path,
            fallback_device=GPS_DEVICE_FALLBACK,
        )
        self._gps.start()

        # Hardware
        self._phat = MakerPHAT(
            gpio_btn_left=self._cfg.gpio_btn_left,
            gpio_btn_center=self._cfg.gpio_btn_center,
            gpio_btn_right=self._cfg.gpio_btn_right,
            gpio_buzzer=self._cfg.gpio_buzzer,
            gpio_leds=self._cfg.gpio_leds,
        )
        self._feedback = FeedbackController(self._phat, self._cfg)

        # State machine
        self._state_machine = DriverStateMachine(self._cfg.initial_driver_state)

        # Button handler
        self._btn_handler = ButtonHandler(
            phat=self._phat,
            config=self._cfg,
            on_self_cb=self._handle_switch_to_self,
            on_other_cb=self._handle_switch_to_other,
            on_left_cb=self._handle_left_button,
        )
        self._btn_handler.start()

        # Install signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)

        # Startup feedback
        self._feedback.startup(self._cfg.initial_driver_state)

        logger.info(
            "Running. Initial driver state: %r. Waiting for events...",
            self._cfg.initial_driver_state,
        )

        # Write initial state.json
        self._flush_state()

        # Main loop
        try:
            while not self._shutdown.is_set():
                gps = self._gps.get_state()
                if gps.lat is not None and gps.lon is not None:
                    self._storage.add_track_point(gps.lat, gps.lon, gps.timestamp)
                self._shutdown.wait(1.0)
        finally:
            self._teardown()

    def _handle_switch_to_self(self) -> None:
        gps = self._gps.get_state() if self._gps else GPSState()
        if not gps.fix_valid:
            logger.warning("No GPS fix when switching to self")
            self._feedback.on_no_fix_warning()
        event = self._state_machine.transition("self", gps, source="maker_phat")
        self._storage.write_event(event)
        self._flush_state()
        if event["type"] == "driver_state_changed_to_self":
            self._feedback.on_switch_to_self()
            if gps.lat is not None and gps.lon is not None:
                self._storage.add_waypoint(gps.lat, gps.lon, "driver:self", gps.timestamp)
        elif "ignored_duplicate" in event["type"]:
            self._feedback.on_duplicate_warning()

    def _handle_switch_to_other(self) -> None:
        gps = self._gps.get_state() if self._gps else GPSState()
        if not gps.fix_valid:
            logger.warning("No GPS fix when switching to other")
            self._feedback.on_no_fix_warning()
        event = self._state_machine.transition("other", gps, source="maker_phat")
        self._storage.write_event(event)
        self._flush_state()
        if event["type"] == "driver_state_changed_to_other":
            self._feedback.on_switch_to_other()
            if gps.lat is not None and gps.lon is not None:
                self._storage.add_waypoint(gps.lat, gps.lon, "driver:other", gps.timestamp)
        elif "ignored_duplicate" in event["type"]:
            self._feedback.on_duplicate_warning()

    def _handle_left_button(self) -> None:
        logger.info("Left button pressed (reserved for future POI)")
        gps = self._gps.get_state() if self._gps else GPSState()
        event = {
            "type": "left_button_pressed",
            "system_time": __import__("datetime").datetime.now().astimezone().isoformat(),
            "lat": gps.lat,
            "lon": gps.lon,
            "fix_valid": gps.fix_valid,
            "nmea_time": gps.timestamp,
            "note": "reserved for future POI",
        }
        self._storage.write_event(event)

    def _flush_state(self) -> None:
        gps = self._gps.get_state() if self._gps else GPSState()
        state_data = {
            "driver_state": self._state_machine.state,
            "gps": {
                "timestamp": gps.timestamp,
                "lat": gps.lat,
                "lon": gps.lon,
                "fix_valid": gps.fix_valid,
                "fix_quality": gps.fix_quality,
                "satellites_used": gps.satellites_used,
                "hdop": gps.hdop,
            },
        }
        self._storage.write_state(state_data)

    def _signal_handler(self, signum, frame) -> None:
        logger.info("Signal %s received; shutting down...", signum)
        self._shutdown.set()

    def _teardown(self) -> None:
        logger.info("Shutting down...")

        if self._btn_handler:
            self._btn_handler.stop()

        # Final GPX write
        if self._storage:
            gps = self._gps.get_state() if self._gps else GPSState()
            summary = {
                "driver_state": self._state_machine.state if self._state_machine else "unknown",
                "session_dir": self._storage.session_dir,
                "final_gps": {
                    "lat": gps.lat,
                    "lon": gps.lon,
                    "fix_valid": gps.fix_valid,
                },
            }
            self._storage.write_summary(summary)
            self._storage.close()

        if self._gps:
            self._gps.stop()

        if self._feedback:
            self._feedback.shutdown()

        if self._phat:
            self._phat.close()

        logger.info("=== pi-z2-driving-logger stopped ===")


def parse_args(argv=None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="GPS driving logger for Raspberry Pi Zero 2 WH with Maker pHAT"
    )
    parser.add_argument(
        "--gps-device",
        default=GPS_DEVICE_PRIMARY,
        help=f"GPS serial device path (default: {GPS_DEVICE_PRIMARY})",
    )
    parser.add_argument(
        "--log-dir",
        default=LOG_DIR_DEFAULT,
        help=f"Log base directory (default: {LOG_DIR_DEFAULT})",
    )
    parser.add_argument(
        "--initial-driver-state",
        default="other",
        choices=["self", "other"],
        help="Initial driver state (default: other)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Enable debug logging",
    )
    return parser.parse_args(argv)


def main(argv=None) -> None:
    args = parse_args(argv)
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    config = Config(
        gps_device=args.gps_device,
        log_dir=args.log_dir,
        initial_driver_state=args.initial_driver_state,
    )

    app = DrivingLogger(config)
    app.run()


if __name__ == "__main__":
    main()
