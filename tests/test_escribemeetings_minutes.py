"""Tests for eSCRIBE Post-Meeting Minutes discovery.

Tests the filename parser for Post-Meeting Minutes documents.
Sync dispatch test lives in test_data_sync.py (shared test infrastructure).
"""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


class TestParseMinutesFilename:
    """Test _parse_minutes_filename for various known filename patterns."""

    def test_regular_meeting(self):
        from escribemeetings_scraper import _parse_minutes_filename

        result = _parse_minutes_filename(
            "Post-Meeting Minutes - CC_Mar03_2026 - English.pdf"
        )
        assert result == {"date": "2026-03-03", "type": "regular"}

    def test_special_meeting(self):
        from escribemeetings_scraper import _parse_minutes_filename

        result = _parse_minutes_filename(
            "Post-Meeting Minutes - Special City Council Meeting_Jul12_2024 - English.pdf"
        )
        assert result == {"date": "2024-07-12", "type": "special"}

    def test_swearing_in(self):
        from escribemeetings_scraper import _parse_minutes_filename

        result = _parse_minutes_filename(
            "Post-Meeting Minutes - Swearing In Ceremony_Jan14_2025 - English.pdf"
        )
        assert result == {"date": "2025-01-14", "type": "special"}

    def test_all_months(self):
        from escribemeetings_scraper import _parse_minutes_filename

        months = [
            ("Jan", "01"), ("Feb", "02"), ("Mar", "03"), ("Apr", "04"),
            ("May", "05"), ("Jun", "06"), ("Jul", "07"), ("Aug", "08"),
            ("Sep", "09"), ("Oct", "10"), ("Nov", "11"), ("Dec", "12"),
        ]
        for abbr, num in months:
            result = _parse_minutes_filename(
                f"Post-Meeting Minutes - CC_{abbr}15_2025 - English.pdf"
            )
            assert result is not None, f"Failed for {abbr}"
            assert result["date"] == f"2025-{num}-15"

    def test_unparseable_returns_none(self):
        from escribemeetings_scraper import _parse_minutes_filename

        assert _parse_minutes_filename("Agenda.Css") is None
        assert _parse_minutes_filename("Some random file.pdf") is None
        assert _parse_minutes_filename("") is None

    def test_draft_minutes_not_matched(self):
        from escribemeetings_scraper import _parse_minutes_filename

        # Draft minutes have a different filename pattern — should not match
        result = _parse_minutes_filename(
            "CC27Jan2026 - Draft - UD.pdf"
        )
        assert result is None
