"""Traccar REST API client using stdlib urllib.request + http.cookiejar."""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from http.cookiejar import CookieJar
from typing import Optional
from urllib.parse import urlencode, urljoin
from urllib.request import HTTPCookieProcessor, Request, build_opener

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

@dataclass
class TraccarClientConfig:
    """Traccar connection settings, readable from environment variables."""

    base_url: str = ""
    user: str = ""
    password: str = ""
    teacher_device_unique_id: str = ""

    @classmethod
    def from_env(cls) -> "TraccarClientConfig":
        return cls(
            base_url=os.environ.get("TRACCAR_BASE_URL", ""),
            user=os.environ.get("TRACCAR_USER", ""),
            password=os.environ.get("TRACCAR_PASSWORD", ""),
            teacher_device_unique_id=os.environ.get(
                "TRACCAR_TEACHER_DEVICE_UNIQUE_ID", ""
            ),
        )


# ---------------------------------------------------------------------------
# Position dataclass
# ---------------------------------------------------------------------------

@dataclass
class Position:
    """Normalized Traccar position record."""

    device_id: int
    fix_time: datetime
    server_time: datetime
    latitude: float
    longitude: float
    altitude: float
    speed: float      # Traccar stores speed in knots internally
    course: float
    accuracy: float
    protocol: str
    attributes: dict


# ---------------------------------------------------------------------------
# Timestamp parsing
# ---------------------------------------------------------------------------

def _parse_traccar_time(ts: Optional[str]) -> datetime:
    """Parse a Traccar ISO-8601 timestamp string to a UTC-aware datetime.

    Falls back to now(UTC) if the string is missing or unparseable.
    """
    if not ts:
        return datetime.now(timezone.utc)
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        logger.warning("Cannot parse Traccar timestamp: %r", ts)
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class TraccarClient:
    """Minimal Traccar API client (cookie-session auth, stdlib only)."""

    def __init__(self, base_url: str, user: str, password: str) -> None:
        self._base_url = base_url.rstrip("/")
        self._user = user
        self._password = password
        self._cj = CookieJar()
        self._opener = build_opener(HTTPCookieProcessor(self._cj))

    # -----------------------------------------------------------------------
    # Auth
    # -----------------------------------------------------------------------

    def login(self) -> None:
        """Authenticate and store session cookie."""
        url = f"{self._base_url}/api/session"
        data = urlencode(
            {"email": self._user, "password": self._password}
        ).encode()
        req = Request(
            url,
            data=data,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        with self._opener.open(req) as resp:
            body = json.loads(resp.read())
            logger.info(
                "Traccar login OK: %s (id=%s)", body.get("name"), body.get("id")
            )

    def logout(self) -> None:
        """Delete the session (best-effort)."""
        url = f"{self._base_url}/api/session"
        req = Request(url, method="DELETE")
        try:
            with self._opener.open(req):
                pass
        except Exception as exc:
            logger.debug("Traccar logout error (ignored): %s", exc)

    # -----------------------------------------------------------------------
    # Devices
    # -----------------------------------------------------------------------

    def get_devices(self) -> list:
        """Return all visible devices."""
        url = f"{self._base_url}/api/devices"
        with self._opener.open(Request(url)) as resp:
            return json.loads(resp.read())

    def find_device_by_unique_id(self, unique_id: str) -> Optional[dict]:
        """Return the device dict whose uniqueId matches, or None."""
        for device in self.get_devices():
            if device.get("uniqueId") == unique_id:
                return device
        return None

    # -----------------------------------------------------------------------
    # Positions
    # -----------------------------------------------------------------------

    def get_positions(
        self,
        device_id: int,
        from_dt: Optional[datetime] = None,
        to_dt: Optional[datetime] = None,
    ) -> list:
        """Fetch positions for a device with optional time filter.

        Note: /api/positions without from/to returns only the latest position
        per device. Provide from_dt / to_dt to get historical track data.
        Time range queries require /api/reports/route (see get_route).
        """
        params: dict = {"deviceId": device_id}
        if from_dt:
            params["from"] = from_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        if to_dt:
            params["to"] = to_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        url = f"{self._base_url}/api/positions?{urlencode(params)}"
        with self._opener.open(Request(url)) as resp:
            raw_list = json.loads(resp.read())

        return [self._parse_position(p) for p in raw_list]

    def get_route(
        self,
        device_id: int,
        from_dt: datetime,
        to_dt: datetime,
    ) -> list:
        """Fetch historical route via /api/reports/route (time-range query)."""
        params = {
            "deviceId": device_id,
            "from": from_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "to": to_dt.strftime("%Y-%m-%dT%H:%M:%SZ"),
        }
        url = f"{self._base_url}/api/reports/route?{urlencode(params)}"
        req = Request(url, headers={"Accept": "application/json"})
        with self._opener.open(req) as resp:
            raw_list = json.loads(resp.read())

        return [self._parse_position(p) for p in raw_list]

    # -----------------------------------------------------------------------
    # Internal
    # -----------------------------------------------------------------------

    @staticmethod
    def _parse_position(raw: dict) -> "Position":
        """Convert a raw Traccar position dict to a Position dataclass."""
        fix_time = _parse_traccar_time(
            raw.get("fixTime") or raw.get("deviceTime") or raw.get("serverTime")
        )
        server_time = _parse_traccar_time(raw.get("serverTime", ""))
        return Position(
            device_id=raw.get("deviceId", 0),
            fix_time=fix_time,
            server_time=server_time,
            latitude=raw.get("latitude", 0.0),
            longitude=raw.get("longitude", 0.0),
            altitude=raw.get("altitude", 0.0),
            speed=raw.get("speed", 0.0),
            course=raw.get("course", 0.0),
            accuracy=raw.get("accuracy", 0.0),
            protocol=raw.get("protocol", ""),
            attributes=raw.get("attributes") or {},
        )
