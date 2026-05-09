"""Driver state machine: tracks whether 'self' or 'other' is driving."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional, TYPE_CHECKING

if TYPE_CHECKING:
    from .gps import GPSState

logger = logging.getLogger(__name__)

VALID_STATES = ("self", "other")


class DriverStateMachine:
    """Simple two-state machine: 'self' or 'other'.

    Args:
        initial_state: Starting state, either 'self' or 'other'.
    """

    def __init__(self, initial_state: str = "other"):
        if initial_state not in VALID_STATES:
            raise ValueError(f"initial_state must be one of {VALID_STATES}, got {initial_state!r}")
        self._state = initial_state
        logger.info("DriverStateMachine initialized with state=%r", self._state)

    @property
    def state(self) -> str:
        return self._state

    def transition(
        self,
        new_state: str,
        gps_state: "GPSState",
        source: str = "maker_phat",
    ) -> dict:
        """Attempt a state transition.

        Args:
            new_state: Target state ('self' or 'other').
            gps_state: Current GPS fix data.
            source: Source of the transition (e.g., 'maker_phat').

        Returns:
            Event dict describing the transition (or a duplicate/ignored event).
        """
        if new_state not in VALID_STATES:
            raise ValueError(f"new_state must be one of {VALID_STATES}, got {new_state!r}")

        system_time = datetime.now().astimezone().isoformat()
        prev_state = self._state

        base_event = {
            "system_time": system_time,
            "driver_state_before": prev_state,
            "driver_state_after": new_state,
            "lat": gps_state.lat,
            "lon": gps_state.lon,
            "fix_valid": gps_state.fix_valid,
            "fix_quality": gps_state.fix_quality,
            "satellites_used": gps_state.satellites_used,
            "hdop": gps_state.hdop,
            "nmea_time": gps_state.timestamp,
            "source": source,
        }

        if prev_state == new_state:
            # Duplicate transition
            event_type = (
                "ignored_duplicate_self"
                if new_state == "self"
                else "ignored_duplicate_other"
            )
            event = {"type": event_type, **base_event}
            logger.warning("Duplicate transition to %r (ignored)", new_state)
            return event

        self._state = new_state
        event_type = (
            "driver_state_changed_to_self"
            if new_state == "self"
            else "driver_state_changed_to_other"
        )
        event = {"type": event_type, **base_event}
        logger.info(
            "State transition: %r → %r (source=%r, fix_valid=%s)",
            prev_state,
            new_state,
            source,
            gps_state.fix_valid,
        )
        return event
