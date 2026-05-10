"""Semantic join: match Pi events.jsonl to Traccar teacher positions."""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from .traccar_client import Position

logger = logging.getLogger(__name__)

CONFIDENCE_HIGH = "high"
CONFIDENCE_MEDIUM = "medium"
CONFIDENCE_LOW = "low"
CONFIDENCE_MISSING = "missing_or_stale"

POI_TYPES = frozenset({"walk_poi", "walk_poi_important", "walk_poi_double"})
DRIVER_CHANGE_TYPES = frozenset({
    "driver_state_changed_to_self",
    "driver_state_changed_to_other",
    "ignored_duplicate_self",
    "ignored_duplicate_other",
})


# ---------------------------------------------------------------------------
# Time helpers
# ---------------------------------------------------------------------------

def parse_event_time(event: dict) -> datetime:
    """Parse system_time from a Pi event dict to UTC-aware datetime."""
    ts = event.get("system_time", "")
    try:
        dt = datetime.fromisoformat(str(ts))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except (ValueError, TypeError):
        return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Nearest position lookup
# ---------------------------------------------------------------------------

def nearest_position_at(
    positions: list, event_time: datetime
) -> tuple:
    """Find the position closest in time to event_time.

    Returns (Position | None, delta_seconds).
    delta_seconds is float('inf') when positions is empty.
    """
    if not positions:
        return None, float("inf")

    best = min(positions, key=lambda p: abs((p.fix_time - event_time).total_seconds()))
    delta = abs((best.fix_time - event_time).total_seconds())
    return best, delta


def confidence_from_delta(delta_s: float) -> str:
    if delta_s <= 3.0:
        return CONFIDENCE_HIGH
    elif delta_s <= 10.0:
        return CONFIDENCE_MEDIUM
    elif delta_s <= 30.0:
        return CONFIDENCE_LOW
    else:
        return CONFIDENCE_MISSING


# ---------------------------------------------------------------------------
# Distance calculation
# ---------------------------------------------------------------------------

def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate great-circle distance in metres between two WGS84 points."""
    R = 6_371_000.0
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = (
        math.sin(dphi / 2) ** 2
        + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    )
    return 2 * R * math.asin(math.sqrt(a))


# ---------------------------------------------------------------------------
# Driver interval model
# ---------------------------------------------------------------------------

@dataclass
class DriverInterval:
    driver: str                     # "self" or "other"
    start: datetime
    end: Optional[datetime]         # None = session still open
    start_event: dict
    end_event: Optional[dict]
    teacher_positions: list = field(default_factory=list)

    def contains_time(self, t: datetime) -> bool:
        if t < self.start:
            return False
        if self.end is not None and t > self.end:
            return False
        return True


def build_driver_intervals(events: list) -> list:
    """Build self-driving intervals from the Pi event stream.

    Initial state is 'other'. Returns only 'self' intervals.
    """
    intervals: list[DriverInterval] = []
    current_state = "other"
    current_start: Optional[datetime] = None
    current_start_event: Optional[dict] = None

    for event in sorted(events, key=parse_event_time):
        etype = event.get("type", "")
        etime = parse_event_time(event)

        if etype == "driver_state_changed_to_self" and current_state != "self":
            current_state = "self"
            current_start = etime
            current_start_event = event

        elif etype == "driver_state_changed_to_other" and current_state == "self":
            if current_start is not None:
                intervals.append(DriverInterval(
                    driver="self",
                    start=current_start,
                    end=etime,
                    start_event=current_start_event or {},
                    end_event=event,
                ))
            current_state = "other"
            current_start = None
            current_start_event = None

    # Close any open interval (session end or teacher track end)
    if current_state == "self" and current_start is not None:
        intervals.append(DriverInterval(
            driver="self",
            start=current_start,
            end=None,
            start_event=current_start_event or {},
            end_event=None,
        ))

    return intervals


def assign_teacher_positions(intervals: list, positions: list) -> None:
    """Assign teacher positions to each DriverInterval in-place."""
    for interval in intervals:
        interval.teacher_positions = [
            p for p in positions if interval.contains_time(p.fix_time)
        ]


# ---------------------------------------------------------------------------
# Event loader
# ---------------------------------------------------------------------------

def load_events(events_jsonl_path: str) -> list:
    """Load Pi events from events.jsonl. Skips malformed lines."""
    events: list[dict] = []
    try:
        with open(events_jsonl_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    events.append(json.loads(line))
                except json.JSONDecodeError:
                    logger.warning("Skipping malformed event line: %.80s", line)
    except OSError as exc:
        logger.error("Cannot read events file %s: %s", events_jsonl_path, exc)
    return events
