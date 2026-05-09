"""NMEA sentence parser for GPRMC and GPGGA."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class NMEASentence:
    """Parsed NMEA sentence data."""

    sentence_type: str = ""

    # GPRMC fields
    nmea_time: str = ""          # hhmmss.ss
    rmc_status: str = ""         # A=valid, V=invalid
    lat: Optional[float] = None  # decimal degrees
    lon: Optional[float] = None  # decimal degrees
    speed_knots: Optional[float] = None
    course: Optional[float] = None
    nmea_date: str = ""

    # GPGGA fields
    fix_quality: int = 0
    satellites_used: int = 0
    hdop: Optional[float] = None

    # Derived
    fix_valid: bool = False      # RMC status A AND fix_quality >= 1


def _nmea_to_decimal(value: str, direction: str) -> Optional[float]:
    """Convert NMEA lat/lon format DDMM.MMMM to decimal degrees.

    Args:
        value: NMEA coordinate string like "3544.1234" (DDMM.MMMM)
        direction: One of N, S, E, W

    Returns:
        Decimal degrees (float), or None if parsing fails.
    """
    if not value or not direction:
        return None
    try:
        # Find the decimal point position to split degrees from minutes
        dot_pos = value.index(".")
        # degrees are everything up to (dot_pos - 2)
        deg_str = value[: dot_pos - 2]
        min_str = value[dot_pos - 2 :]
        degrees = float(deg_str) + float(min_str) / 60.0
        if direction in ("S", "W"):
            degrees = -degrees
        return degrees
    except (ValueError, IndexError) as exc:
        logger.debug("NMEA coord parse error value=%r dir=%r: %s", value, direction, exc)
        return None


def _safe_float(s: str) -> Optional[float]:
    if not s:
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _safe_int(s: str) -> Optional[int]:
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


def _strip_checksum(sentence: str) -> str:
    """Remove the *XX checksum suffix if present."""
    if "*" in sentence:
        return sentence[: sentence.index("*")]
    return sentence


def parse_gprmc(fields: list[str]) -> NMEASentence:
    """Parse a GPRMC sentence.

    Expected fields (0-indexed, after stripping sentence type):
    0: time (hhmmss.ss)
    1: status (A/V)
    2: latitude (DDMM.MMMM)
    3: N/S
    4: longitude (DDDMM.MMMM)
    5: E/W
    6: speed over ground (knots)
    7: course over ground (degrees)
    8: date (ddmmyy)
    """
    s = NMEASentence(sentence_type="GPRMC")
    if len(fields) < 9:
        return s
    s.nmea_time = fields[0]
    s.rmc_status = fields[1]
    s.lat = _nmea_to_decimal(fields[2], fields[3])
    s.lon = _nmea_to_decimal(fields[4], fields[5])
    s.speed_knots = _safe_float(fields[6])
    s.course = _safe_float(fields[7])
    s.nmea_date = fields[8]
    return s


def parse_gpgga(fields: list[str]) -> NMEASentence:
    """Parse a GPGGA sentence.

    Expected fields (0-indexed, after stripping sentence type):
    0: time
    1: latitude
    2: N/S
    3: longitude
    4: E/W
    5: fix quality
    6: satellites used
    7: HDOP
    8: altitude
    ...
    """
    s = NMEASentence(sentence_type="GPGGA")
    if len(fields) < 8:
        return s
    s.nmea_time = fields[0]
    s.lat = _nmea_to_decimal(fields[1], fields[2])
    s.lon = _nmea_to_decimal(fields[3], fields[4])
    fq = _safe_int(fields[5])
    s.fix_quality = fq if fq is not None else 0
    su = _safe_int(fields[6])
    s.satellites_used = su if su is not None else 0
    s.hdop = _safe_float(fields[7])
    return s


def parse_nmea_sentence(raw_line: str) -> Optional[NMEASentence]:
    """Parse a raw NMEA sentence string.

    Returns NMEASentence on success, None on unknown/malformed input.
    """
    line = raw_line.strip()
    if not line.startswith("$"):
        return None

    # Strip checksum
    line = _strip_checksum(line)
    # Remove leading $
    line = line.lstrip("$")

    parts = line.split(",")
    if not parts:
        return None

    sentence_type = parts[0].upper()
    data_fields = parts[1:]

    try:
        if sentence_type in ("GPRMC", "GNRMC"):
            return parse_gprmc(data_fields)
        elif sentence_type in ("GPGGA", "GNGGA"):
            return parse_gpgga(data_fields)
        else:
            return None
    except Exception as exc:
        logger.debug("NMEA parse exception for %r: %s", raw_line, exc)
        return None


def nmea_to_decimal(value: str, direction: str) -> Optional[float]:
    """Public wrapper for NMEA coordinate conversion (exposed for testing)."""
    return _nmea_to_decimal(value, direction)
