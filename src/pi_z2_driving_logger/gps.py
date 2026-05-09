"""GPS reader thread for u-blox 7 / VFAN UG-353."""

from __future__ import annotations

import logging
import os
import threading
from dataclasses import dataclass
from typing import Optional

from .nmea import NMEASentence, parse_nmea_sentence

logger = logging.getLogger(__name__)


@dataclass
class GPSState:
    """Current GPS fix state, updated by the reader thread."""

    timestamp: str = ""           # NMEA time string hhmmss.ss
    lat: Optional[float] = None
    lon: Optional[float] = None
    speed_knots: Optional[float] = None
    course: Optional[float] = None
    fix_quality: int = 0
    satellites_used: int = 0
    hdop: Optional[float] = None
    fix_valid: bool = False        # RMC status A AND fix_quality >= 1


class GPSReader:
    """Reads NMEA sentences from GPS serial port in a background thread.

    Usage::

        reader = GPSReader(device_path="/dev/ttyACM0", raw_nmea_path="/tmp/raw.nmea")
        reader.start()
        state = reader.get_state()
        reader.stop()
    """

    def __init__(
        self,
        device_path: str,
        baud_rate: int = 9600,
        raw_nmea_path: Optional[str] = None,
        fallback_device: str = "/dev/ttyACM0",
    ):
        self._device_path = device_path
        self._fallback_device = fallback_device
        self._baud_rate = baud_rate
        self._raw_nmea_path = raw_nmea_path

        self._state = GPSState()
        self._rmc_status = "V"
        self._lock = threading.Lock()
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        """Start the reader thread."""
        self._thread = threading.Thread(target=self._run, daemon=True, name="gps-reader")
        self._thread.start()

    def stop(self) -> None:
        """Signal the reader thread to stop and wait for it."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)

    def get_state(self) -> GPSState:
        """Return a snapshot of the current GPS state (thread-safe)."""
        with self._lock:
            import copy
            return copy.copy(self._state)

    def _open_serial(self):
        """Try to open the GPS serial port, fallback if needed."""
        import serial  # type: ignore

        for path in [self._device_path, self._fallback_device]:
            if not os.path.exists(path):
                logger.warning("GPS device not found: %s", path)
                continue
            try:
                ser = serial.Serial(path, self._baud_rate, timeout=1.0)
                logger.info("Opened GPS device: %s", path)
                return ser
            except serial.SerialException as exc:
                logger.warning("Cannot open %s: %s", path, exc)

        logger.error("No GPS device available; reader will retry.")
        return None

    def _run(self) -> None:
        """Main loop: open serial, read lines, parse NMEA."""
        raw_file = None
        if self._raw_nmea_path:
            try:
                os.makedirs(os.path.dirname(self._raw_nmea_path), exist_ok=True)
                raw_file = open(self._raw_nmea_path, "a", encoding="ascii", errors="replace")
            except OSError as exc:
                logger.warning("Cannot open raw NMEA file %s: %s", self._raw_nmea_path, exc)

        try:
            while not self._stop_event.is_set():
                ser = self._open_serial()
                if ser is None:
                    # Wait before retry
                    self._stop_event.wait(5.0)
                    continue

                try:
                    self._read_loop(ser, raw_file)
                except Exception as exc:
                    logger.error("GPS read error: %s", exc)
                finally:
                    ser.close()

                if not self._stop_event.is_set():
                    logger.info("GPS reconnecting in 2s...")
                    self._stop_event.wait(2.0)
        finally:
            if raw_file:
                raw_file.close()

    def _read_loop(self, ser, raw_file) -> None:
        """Read lines from serial port until stop event."""
        import serial  # type: ignore

        while not self._stop_event.is_set():
            try:
                raw = ser.readline()
            except serial.SerialException as exc:
                logger.warning("Serial read error: %s", exc)
                break

            if not raw:
                continue

            try:
                line = raw.decode("ascii", errors="replace").strip()
            except Exception:
                continue

            if raw_file:
                try:
                    raw_file.write(line + "\n")
                    raw_file.flush()
                except OSError:
                    pass

            sentence = parse_nmea_sentence(line)
            if sentence is None:
                continue

            self._update_state(sentence)

    def _update_state(self, sentence: NMEASentence) -> None:
        """Update internal GPS state from a parsed NMEA sentence."""
        with self._lock:
            if sentence.sentence_type in ("GPRMC", "GNRMC"):
                if sentence.nmea_time:
                    self._state.timestamp = sentence.nmea_time
                if sentence.lat is not None:
                    self._state.lat = sentence.lat
                if sentence.lon is not None:
                    self._state.lon = sentence.lon
                if sentence.speed_knots is not None:
                    self._state.speed_knots = sentence.speed_knots
                if sentence.course is not None:
                    self._state.course = sentence.course
                self._rmc_status = sentence.rmc_status
                self._state.fix_valid = (
                    self._rmc_status == "A" and self._state.fix_quality >= 1
                )

            elif sentence.sentence_type in ("GPGGA", "GNGGA"):
                if sentence.nmea_time:
                    self._state.timestamp = sentence.nmea_time
                if sentence.lat is not None:
                    self._state.lat = sentence.lat
                if sentence.lon is not None:
                    self._state.lon = sentence.lon
                self._state.fix_quality = sentence.fix_quality
                self._state.satellites_used = sentence.satellites_used
                if sentence.hdop is not None:
                    self._state.hdop = sentence.hdop
                self._state.fix_valid = (
                    self._rmc_status == "A" and self._state.fix_quality >= 1
                )
