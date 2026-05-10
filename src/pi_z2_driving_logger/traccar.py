"""Traccar OsmAnd protocol payload builder and config."""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urlencode

from .gps import GPSState


# ---------------------------------------------------------------------------
# Conversion helpers
# ---------------------------------------------------------------------------

def knots_to_kmh(knots: float) -> float:
    """Convert speed from knots to km/h."""
    return knots * 1.852


def estimate_accuracy(hdop: Optional[float]) -> float:
    """Estimate position accuracy in metres from HDOP. Returns 50.0 if unknown."""
    if hdop is None:
        return 50.0
    return hdop * 5.0


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class TraccarConfig:
    """Traccar integration settings, readable from environment variables."""

    enabled: bool = False
    endpoint: str = "http://100.107.123.105:30055/"
    device_id: str = "pi-z2-wh"
    send_interval_s: float = 10.0
    queue_dir: str = "/home/yuiseki/pi-z2-driving-logs/traccar-queue"
    timeout_s: float = 5.0
    max_retry_per_flush: int = 50

    @classmethod
    def from_env(cls) -> "TraccarConfig":
        """Build config from environment variables."""
        return cls(
            enabled=os.environ.get("TRACCAR_ENABLED", "false").lower()
            in ("true", "1", "yes"),
            endpoint=os.environ.get(
                "TRACCAR_ENDPOINT", "http://100.107.123.105:30055/"
            ),
            device_id=os.environ.get("TRACCAR_DEVICE_ID", "pi-z2-wh"),
            send_interval_s=float(
                os.environ.get("TRACCAR_SEND_INTERVAL_SECONDS", "10")
            ),
            queue_dir=os.environ.get(
                "TRACCAR_QUEUE_DIR",
                "/home/yuiseki/pi-z2-driving-logs/traccar-queue",
            ),
            timeout_s=float(os.environ.get("TRACCAR_TIMEOUT_SECONDS", "5")),
            max_retry_per_flush=int(
                os.environ.get("TRACCAR_MAX_RETRY_PER_FLUSH", "50")
            ),
        )


# ---------------------------------------------------------------------------
# Payload builders
# ---------------------------------------------------------------------------

def build_position_payload(
    gps: GPSState,
    driver_state: str,
    session_id: str,
) -> Optional[dict]:
    """Build a Traccar position payload dict.

    Returns None when GPS fix is not valid or coordinates are absent.
    """
    if not gps.fix_valid or gps.lat is None or gps.lon is None:
        return None

    speed_kmh = knots_to_kmh(gps.speed_knots) if gps.speed_knots is not None else 0.0
    accuracy = estimate_accuracy(gps.hdop)

    return {
        "kind": "position",
        "lat": gps.lat,
        "lon": gps.lon,
        "timestamp": int(time.time()),
        "speed": round(speed_kmh, 2),
        "bearing": gps.course or 0.0,
        "altitude": 0.0,
        "accuracy": round(accuracy, 2),
        "hdop": gps.hdop,
        "driver_state": driver_state,
        "source": "pi_z2_driving_logger",
        "session_id": session_id,
        "fix_quality": gps.fix_quality,
        "satellites_used": gps.satellites_used,
    }


def build_event_payload(
    event_type: str,
    gps: GPSState,
    driver_state: str,
    session_id: str,
    source: str = "pi_z2_driving_logger",
) -> Optional[dict]:
    """Build a Traccar event payload dict.

    Returns None when GPS fix is not valid or coordinates are absent.
    """
    if not gps.fix_valid or gps.lat is None or gps.lon is None:
        return None

    speed_kmh = knots_to_kmh(gps.speed_knots) if gps.speed_knots is not None else 0.0
    accuracy = estimate_accuracy(gps.hdop)

    return {
        "kind": "event",
        "lat": gps.lat,
        "lon": gps.lon,
        "timestamp": int(time.time()),
        "speed": round(speed_kmh, 2),
        "bearing": gps.course or 0.0,
        "altitude": 0.0,
        "accuracy": round(accuracy, 2),
        "hdop": gps.hdop,
        "driver_state": driver_state,
        "event_type": event_type,
        "source": source,
        "session_id": session_id,
        "fix_quality": gps.fix_quality,
        "satellites_used": gps.satellites_used,
    }


# ---------------------------------------------------------------------------
# URL builder
# ---------------------------------------------------------------------------

def payload_to_url(endpoint: str, device_id: str, payload: dict) -> str:
    """Convert a payload dict to a Traccar OsmAnd HTTP GET URL."""
    params: dict = {
        "id": device_id,
        "lat": payload["lat"],
        "lon": payload["lon"],
        "timestamp": payload["timestamp"],
        "speed": payload.get("speed", 0.0),
        "bearing": payload.get("bearing", 0.0),
        "altitude": payload.get("altitude", 0.0),
        "accuracy": payload.get("accuracy", 50.0),
    }
    for key in (
        "hdop",
        "driver_state",
        "event_type",
        "source",
        "session_id",
        "fix_quality",
        "satellites_used",
    ):
        val = payload.get(key)
        if val is not None:
            params[key] = val

    query = urlencode(params)
    base = endpoint.rstrip("/")
    return f"{base}/?{query}"
