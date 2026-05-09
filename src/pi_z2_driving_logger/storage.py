"""Session storage manager for GPS driving logger."""

from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

GPX_HEADER = """<?xml version="1.0" encoding="UTF-8"?>
<gpx version="1.1"
     creator="pi-z2-driving-logger"
     xmlns="http://www.topografix.com/GPX/1/1"
     xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
     xsi:schemaLocation="http://www.topografix.com/GPX/1/1 http://www.topografix.com/GPX/1/1/gpx.xsd">
"""

GPX_FOOTER = "</gpx>\n"


def _format_gpx_time(ts: str) -> str:
    """Return ISO8601 UTC time string (best effort from NMEA hhmmss.ss).

    TODO: NMEA provides only hhmmss without date; use system time for now.
    Proper fix: combine GPRMC date+time fields to construct correct UTC timestamp.
    """
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")


class StorageManager:
    """Manages all file writes for a single session.

    Directory structure::

        <session_dir>/
            raw.nmea
            events.jsonl
            track.gpx
            waypoints.gpx
            summary.json
            state.json
    """

    def __init__(self, base_log_dir: str, gpx_flush_interval_s: float = 60.0):
        session_name = datetime.now().strftime("%Y%m%d-%H%M%S")
        self._session_dir = os.path.join(base_log_dir, "sessions", session_name)
        self._gpx_flush_interval_s = gpx_flush_interval_s

        os.makedirs(self._session_dir, exist_ok=True)
        logger.info("Session directory: %s", self._session_dir)

        self._raw_nmea_path = os.path.join(self._session_dir, "raw.nmea")
        self._events_path = os.path.join(self._session_dir, "events.jsonl")
        self._track_gpx_path = os.path.join(self._session_dir, "track.gpx")
        self._waypoints_gpx_path = os.path.join(self._session_dir, "waypoints.gpx")
        self._summary_path = os.path.join(self._session_dir, "summary.json")
        self._state_path = os.path.join(self._session_dir, "state.json")

        self._track_points: list[dict] = []
        self._waypoints: list[dict] = []
        self._lock = threading.Lock()

        self._flush_stop = threading.Event()
        self._flush_thread = threading.Thread(
            target=self._periodic_flush, daemon=True, name="gpx-flush"
        )
        self._flush_thread.start()

    @property
    def session_dir(self) -> str:
        return self._session_dir

    @property
    def raw_nmea_path(self) -> str:
        return self._raw_nmea_path

    # -----------------------------------------------------------------------
    # Public write methods
    # -----------------------------------------------------------------------

    def write_raw_nmea(self, line: str) -> None:
        """Append a raw NMEA sentence line to raw.nmea."""
        self._append_line(self._raw_nmea_path, line)

    def write_event(self, event_dict: dict) -> None:
        """Append an event as a JSON line to events.jsonl."""
        try:
            json_line = json.dumps(event_dict, ensure_ascii=False)
            self._append_line(self._events_path, json_line)
        except (TypeError, ValueError) as exc:
            logger.error("Failed to serialize event: %s", exc)

    def add_track_point(self, lat: float, lon: float, nmea_time: str = "") -> None:
        """Add a track point (buffered; flushed periodically or on close)."""
        with self._lock:
            self._track_points.append({"lat": lat, "lon": lon, "time": nmea_time})

    def add_waypoint(self, lat: float, lon: float, name: str, nmea_time: str = "") -> None:
        """Add a waypoint (e.g., driver state change location)."""
        with self._lock:
            self._waypoints.append({"lat": lat, "lon": lon, "name": name, "time": nmea_time})

    def write_track_gpx(self, track_points: Optional[list] = None) -> None:
        """Write track.gpx from buffered or provided points."""
        with self._lock:
            points = track_points if track_points is not None else list(self._track_points)
        self._write_gpx_track(self._track_gpx_path, points)

    def write_waypoints_gpx(self, waypoints: Optional[list] = None) -> None:
        """Write waypoints.gpx from buffered or provided waypoints."""
        with self._lock:
            wps = waypoints if waypoints is not None else list(self._waypoints)
        self._write_gpx_waypoints(self._waypoints_gpx_path, wps)

    def write_summary(self, data: dict) -> None:
        """Write summary.json (overwrites)."""
        self._write_json(self._summary_path, data)

    def write_state(self, data: dict) -> None:
        """Write state.json (overwrites)."""
        self._write_json(self._state_path, data)

    def flush(self) -> None:
        """Flush both GPX files immediately."""
        self.write_track_gpx()
        self.write_waypoints_gpx()

    def close(self) -> None:
        """Flush and stop background threads."""
        self._flush_stop.set()
        self._flush_thread.join(timeout=5.0)
        self.flush()

    # -----------------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------------

    def _append_line(self, path: str, line: str) -> None:
        try:
            with open(path, "a", encoding="utf-8") as f:
                f.write(line.rstrip("\n") + "\n")
        except OSError as exc:
            logger.error("Write error %s: %s", path, exc)

    def _write_json(self, path: str, data: dict) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except (OSError, TypeError, ValueError) as exc:
            logger.error("Write error %s: %s", path, exc)

    def _write_gpx_track(self, path: str, points: list) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(GPX_HEADER)
                f.write("  <trk>\n")
                f.write("    <name>Driving Track</name>\n")
                f.write("    <trkseg>\n")
                for pt in points:
                    lat = pt.get("lat", 0.0)
                    lon = pt.get("lon", 0.0)
                    ts = _format_gpx_time(pt.get("time", ""))
                    f.write(f'      <trkpt lat="{lat:.8f}" lon="{lon:.8f}">\n')
                    f.write(f"        <time>{ts}</time>\n")
                    f.write("      </trkpt>\n")
                f.write("    </trkseg>\n")
                f.write("  </trk>\n")
                f.write(GPX_FOOTER)
        except OSError as exc:
            logger.error("GPX track write error %s: %s", path, exc)

    def _write_gpx_waypoints(self, path: str, waypoints: list) -> None:
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(GPX_HEADER)
                for wp in waypoints:
                    lat = wp.get("lat", 0.0)
                    lon = wp.get("lon", 0.0)
                    name = wp.get("name", "")
                    ts = _format_gpx_time(wp.get("time", ""))
                    f.write(f'  <wpt lat="{lat:.8f}" lon="{lon:.8f}">\n')
                    f.write(f"    <name>{name}</name>\n")
                    f.write(f"    <time>{ts}</time>\n")
                    f.write("  </wpt>\n")
                f.write(GPX_FOOTER)
        except OSError as exc:
            logger.error("GPX waypoints write error %s: %s", path, exc)

    def _periodic_flush(self) -> None:
        """Flush GPX files every N seconds."""
        while not self._flush_stop.is_set():
            self._flush_stop.wait(self._gpx_flush_interval_s)
            if not self._flush_stop.is_set():
                logger.debug("Periodic GPX flush")
                self.flush()
