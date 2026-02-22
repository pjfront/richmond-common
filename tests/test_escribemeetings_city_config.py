"""Tests for eSCRIBE scraper city config integration."""
import pytest
from unittest.mock import patch, MagicMock
from escribemeetings_scraper import _resolve_escribemeetings_config


def test_resolve_defaults_without_fips():
    """Without city_fips, should return module-level Richmond constants."""
    base, cal, meet, doc, fips = _resolve_escribemeetings_config()
    assert base == "https://pub-richmond.escribemeetings.com"
    assert "GetCalendarMeetings" in cal
    assert "Meeting.aspx" in meet
    assert "filestream.ashx" in doc
    assert fips == "0660620"


def test_resolve_from_registry_with_fips():
    """With city_fips, should load config from city_config registry."""
    base, cal, meet, doc, fips = _resolve_escribemeetings_config("0660620")
    assert base == "https://pub-richmond.escribemeetings.com"
    assert cal == "https://pub-richmond.escribemeetings.com/MeetingsCalendarView.aspx/GetCalendarMeetings"
    assert "Meeting.aspx" in meet
    assert "filestream.ashx" in doc
    assert fips == "0660620"


def test_resolve_unknown_city_raises():
    """Unknown city should raise CityNotConfiguredError."""
    from city_config import CityNotConfiguredError
    with pytest.raises(CityNotConfiguredError):
        _resolve_escribemeetings_config("9999999")


def test_resolve_city_without_escribemeetings_raises():
    """City with no eSCRIBE source should raise CityNotConfiguredError."""
    from city_config import CityNotConfiguredError, CITY_REGISTRY

    # Temporarily add a city without escribemeetings
    fake_fips = "0000001"
    CITY_REGISTRY[fake_fips] = {
        "fips_code": fake_fips,
        "name": "TestCity",
        "state": "XX",
        "data_sources": {},
    }
    try:
        with pytest.raises(CityNotConfiguredError, match="no 'escribemeetings'"):
            _resolve_escribemeetings_config(fake_fips)
    finally:
        del CITY_REGISTRY[fake_fips]


def test_scraper_result_includes_city_fips():
    """scrape_meeting dry_run result should carry city_fips from config."""
    from escribemeetings_scraper import scrape_meeting

    fake_meeting = {
        "ID": "test-guid-1234",
        "MeetingName": "City Council",
        "StartDate": "2026-01-01 18:00",
    }

    session = MagicMock()
    result = scrape_meeting(
        session, fake_meeting,
        download_attachments=False,
        dry_run=True,
        city_fips="0660620",
    )

    assert result["city_fips"] == "0660620"
    assert result["dry_run"] is True
    assert result["guid"] == "test-guid-1234"
