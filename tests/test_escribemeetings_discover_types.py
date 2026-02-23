# tests/test_escribemeetings_discover_types.py
"""Tests for eSCRIBE meeting type discovery."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from escribemeetings_scraper import discover_meeting_types


# ── Sample meeting data (from discover_meetings) ─────────────
SAMPLE_MEETINGS = [
    {"ID": "guid1", "MeetingName": "City Council", "StartDate": "2025/01/07 18:30:00"},
    {"ID": "guid2", "MeetingName": "City Council", "StartDate": "2025/01/21 18:30:00"},
    {"ID": "guid3", "MeetingName": "Planning Commission", "StartDate": "2025/01/16 18:00:00"},
    {"ID": "guid4", "MeetingName": "Planning Commission", "StartDate": "2025/02/06 18:00:00"},
    {"ID": "guid5", "MeetingName": "Planning Commission", "StartDate": "2025/03/06 18:00:00"},
    {"ID": "guid6", "MeetingName": "Richmond Rent Board", "StartDate": "2025/01/15 17:00:00"},
    {"ID": "guid7", "MeetingName": "Special City Council", "StartDate": "2025/02/03 17:00:00"},
    {"ID": "guid8", "MeetingName": "Design Review Board", "StartDate": "2025/01/22 17:30:00"},
]


class TestDiscoverMeetingTypes:
    def test_counts_by_type(self):
        result = discover_meeting_types(SAMPLE_MEETINGS)
        assert result["City Council"]["count"] == 2
        assert result["Planning Commission"]["count"] == 3

    def test_includes_date_range(self):
        result = discover_meeting_types(SAMPLE_MEETINGS)
        pc = result["Planning Commission"]
        assert pc["first_date"] == "2025-01-16"
        assert pc["last_date"] == "2025-03-06"

    def test_all_types_present(self):
        result = discover_meeting_types(SAMPLE_MEETINGS)
        assert len(result) == 5
        assert "Richmond Rent Board" in result
        assert "Design Review Board" in result

    def test_empty_input(self):
        result = discover_meeting_types([])
        assert result == {}

    def test_single_meeting_type(self):
        result = discover_meeting_types([SAMPLE_MEETINGS[0]])
        assert result["City Council"]["count"] == 1
        assert result["City Council"]["first_date"] == result["City Council"]["last_date"]

    def test_sample_ids_limited_to_three(self):
        result = discover_meeting_types(SAMPLE_MEETINGS)
        assert len(result["Planning Commission"]["sample_ids"]) == 3
        assert len(result["City Council"]["sample_ids"]) == 2  # Only 2 exist

    def test_date_format_normalized(self):
        """eSCRIBE dates come as YYYY/MM/DD — we normalize to YYYY-MM-DD."""
        result = discover_meeting_types(SAMPLE_MEETINGS)
        cc = result["City Council"]
        assert "/" not in cc["first_date"]
        assert "-" in cc["first_date"]
