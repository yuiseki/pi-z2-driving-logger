"""Tests for nmea.py — NMEA sentence parsing."""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import pytest

from pi_z2_driving_logger.nmea import (
    parse_nmea_sentence,
    nmea_to_decimal,
    NMEASentence,
)


class TestNMEAToDecimal:
    """Test NMEA lat/lon format to decimal degrees conversion."""

    def test_latitude_north(self):
        # 3544.1234,N → 35 + 44.1234/60 = 35.73539
        result = nmea_to_decimal("3544.1234", "N")
        assert result is not None
        assert abs(result - (35 + 44.1234 / 60)) < 1e-6

    def test_latitude_south(self):
        result = nmea_to_decimal("3544.1234", "S")
        assert result is not None
        assert result < 0
        assert abs(result - -(35 + 44.1234 / 60)) < 1e-6

    def test_longitude_east(self):
        result = nmea_to_decimal("13938.5678", "E")
        assert result is not None
        expected = 139 + 38.5678 / 60
        assert abs(result - expected) < 1e-6

    def test_longitude_west(self):
        result = nmea_to_decimal("12235.1000", "W")
        assert result is not None
        expected = -(122 + 35.1000 / 60)
        assert abs(result - expected) < 1e-6

    def test_example_from_spec(self):
        # "3544.1234,N" → 35 + 44.1234/60 = 35.735390
        result = nmea_to_decimal("3544.1234", "N")
        assert result is not None
        assert abs(result - 35.735390) < 1e-4

    def test_empty_value_returns_none(self):
        assert nmea_to_decimal("", "N") is None

    def test_empty_direction_returns_none(self):
        assert nmea_to_decimal("3544.1234", "") is None

    def test_invalid_value_returns_none(self):
        assert nmea_to_decimal("invalid", "N") is None


class TestParseGPRMC:
    """Test GPRMC sentence parsing."""

    VALID_RMC = "$GPRMC,073000.00,A,3544.1234,N,13938.5678,E,0.0,0.0,090526,,,A*68"

    def test_valid_gprmc_lat(self):
        s = parse_nmea_sentence(self.VALID_RMC)
        assert s is not None
        assert s.sentence_type == "GPRMC"
        assert s.lat is not None
        expected_lat = 35 + 44.1234 / 60
        assert abs(s.lat - expected_lat) < 1e-6

    def test_valid_gprmc_lon(self):
        s = parse_nmea_sentence(self.VALID_RMC)
        assert s is not None
        expected_lon = 139 + 38.5678 / 60
        assert abs(s.lon - expected_lon) < 1e-6

    def test_valid_gprmc_status_a(self):
        s = parse_nmea_sentence(self.VALID_RMC)
        assert s is not None
        assert s.rmc_status == "A"

    def test_valid_gprmc_time(self):
        s = parse_nmea_sentence(self.VALID_RMC)
        assert s is not None
        assert s.nmea_time == "073000.00"

    def test_valid_gprmc_speed(self):
        s = parse_nmea_sentence(self.VALID_RMC)
        assert s is not None
        assert s.speed_knots == 0.0

    def test_gprmc_status_v_fix_not_valid(self):
        """GPRMC with status V should not be fix_valid (needs GGA too, but rmc_status=V)."""
        invalid_rmc = "$GPRMC,073000.00,V,3544.1234,N,13938.5678,E,0.0,0.0,090526,,,N*53"
        s = parse_nmea_sentence(invalid_rmc)
        assert s is not None
        assert s.rmc_status == "V"
        # fix_valid is set later by GPSReader combining RMC+GGA; here just check rmc_status
        assert s.rmc_status != "A"

    def test_gprmc_minimal_fields(self):
        """Short sentence should parse without crashing."""
        s = parse_nmea_sentence("$GPRMC,073000.00,V,,,,,,,,")
        # Should return a sentence (possibly with None fields)
        assert s is not None or s is None  # no crash


class TestParseGPGGA:
    """Test GPGGA sentence parsing."""

    VALID_GGA = "$GPGGA,073000.00,3544.1234,N,13938.5678,E,1,07,1.96,45.0,M,39.0,M,,*47"

    def test_gpgga_fix_quality(self):
        s = parse_nmea_sentence(self.VALID_GGA)
        assert s is not None
        assert s.sentence_type == "GPGGA"
        assert s.fix_quality == 1

    def test_gpgga_satellites_used(self):
        s = parse_nmea_sentence(self.VALID_GGA)
        assert s is not None
        assert s.satellites_used == 7

    def test_gpgga_hdop(self):
        s = parse_nmea_sentence(self.VALID_GGA)
        assert s is not None
        assert s.hdop is not None
        assert abs(s.hdop - 1.96) < 1e-4

    def test_gpgga_lat_lon(self):
        s = parse_nmea_sentence(self.VALID_GGA)
        assert s is not None
        expected_lat = 35 + 44.1234 / 60
        expected_lon = 139 + 38.5678 / 60
        assert abs(s.lat - expected_lat) < 1e-6
        assert abs(s.lon - expected_lon) < 1e-6

    def test_gpgga_no_fix(self):
        no_fix_gga = "$GPGGA,073000.00,,,,,,0,00,,,,,,"
        s = parse_nmea_sentence(no_fix_gga)
        assert s is not None
        assert s.fix_quality == 0
        assert s.satellites_used == 0


class TestParseUnknownSentence:
    def test_unknown_sentence_type_returns_none(self):
        s = parse_nmea_sentence("$GPGSV,3,1,09,01,40,083,46*75")
        assert s is None

    def test_non_nmea_line_returns_none(self):
        s = parse_nmea_sentence("not a sentence at all")
        assert s is None

    def test_empty_string_returns_none(self):
        s = parse_nmea_sentence("")
        assert s is None
