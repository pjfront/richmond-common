"""Tests for the NextRequest/CPRA scraper.

Transform tests use JSON fixtures matching the client API response format.
No network calls or Playwright needed.
"""
import json
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


# ── JSON fixtures (matching NextRequest client API format) ────

SAMPLE_LIST_ITEM = {
    "request_date": "01/15/2026",
    "staff_cost": "0.0",
    "visibility": "Published",
    "id": "26-042",
    "request_state": "Closed",
    "department_names": "Police Department",
    "due_date": "01/25/2026",
    "poc_name": "Jane Smith",
    "request_path": "/requests/26-042",
    "request_text": "Police department overtime records for 2025",
    "requester_name": None,
}

SAMPLE_LIST_ITEM_2 = {
    "request_date": "02/01/2026",
    "staff_cost": "0.0",
    "visibility": "Published",
    "id": "26-055",
    "request_state": "In Progress",
    "department_names": "City Manager",
    "due_date": "02/11/2026",
    "poc_name": "Bob Jones",
    "request_path": "/requests/26-055",
    "request_text": "City manager contract details",
    "requester_name": None,
}

SAMPLE_DETAIL_RESPONSE = {
    "pretty_id": "26-042",
    "request_text": "<p>I am requesting all overtime records for the Richmond Police Department for the period of January 2025 through December 2025.</p>",
    "request_state": "Closed",
    "visibility": "published",
    "request_visibility": "Published",
    "request_due_date": "January 25, 2026",
    "request_submit_type": None,
    "request_date": "January 15, 2026",
    "department_names": "Police Department",
    "departments": [{"id": 123, "name": "Police Department"}],
    "request_staff_hours": None,
    "request_staff_cost": None,
    "request_field_values": [
        {
            "id": 1,
            "field_id": 1447,
            "field_type": "text",
            "value": "January 2025 - December 2025",
            "display_name": "Date(s) or Date Range(s) of Records",
        },
    ],
    "poc": {"id": 123, "email_or_name": "Jane Smith", "has_tasks": False},
    "requester": {"id": 456, "name": "John Doe", "email": None},
}

SAMPLE_TIMELINE_RESPONSE = {
    "total_count": 3,
    "timeline": [
        {
            "timeline_id": 100001,
            "timeline_name": "Request Published",
            "timeline_byline": "January 15, 2026, 10:00am by Staff",
        },
        {
            "timeline_id": 100002,
            "timeline_name": "Request Closed",
            "timeline_byline": "January 22, 2026,  3:45pm by Staff",
        },
        {
            "timeline_id": 100003,
            "timeline_name": "Request Opened",
            "timeline_byline": "January 15, 2026,  9:30am by the requester",
        },
    ],
    "pinned": [],
}

SAMPLE_DETAIL_NO_DEPT = {
    "pretty_id": "26-100",
    "request_text": "<p>Simple request</p>",
    "request_state": "Open",
    "visibility": "published",
    "request_visibility": "Published",
    "request_due_date": None,
    "request_submit_type": None,
    "request_date": "March 1, 2026",
    "department_names": "None assigned",
    "departments": [],
    "request_staff_hours": None,
    "request_staff_cost": None,
    "request_field_values": [],
    "poc": {"id": 789, "email_or_name": "Staff Member"},
    "requester": {"id": 999, "name": None, "email": None},
}


# ── Transform tests: list items ──────────────────────────────

class TestTransformListItem:
    """Test _transform_list_item with JSON fixtures."""

    def test_transforms_basic_fields(self):
        from nextrequest_scraper import _transform_list_item
        result = _transform_list_item(SAMPLE_LIST_ITEM)
        assert result["request_number"] == "26-042"
        assert result["status"] == "Closed"
        assert result["department"] == "Police Department"
        assert result["submitted_date"] == "2026-01-15"

    def test_transforms_second_item(self):
        from nextrequest_scraper import _transform_list_item
        result = _transform_list_item(SAMPLE_LIST_ITEM_2)
        assert result["request_number"] == "26-055"
        assert result["status"] == "In Progress"
        assert result["department"] == "City Manager"

    def test_transforms_portal_url(self):
        from nextrequest_scraper import _transform_list_item
        result = _transform_list_item(SAMPLE_LIST_ITEM)
        assert result["portal_url"] == "https://cityofrichmondca.nextrequest.com/requests/26-042"

    def test_transforms_due_date(self):
        from nextrequest_scraper import _transform_list_item
        result = _transform_list_item(SAMPLE_LIST_ITEM)
        assert result["due_date"] == "2026-01-25"

    def test_empty_department_becomes_none(self):
        from nextrequest_scraper import _transform_list_item
        item = {**SAMPLE_LIST_ITEM, "department_names": ""}
        result = _transform_list_item(item)
        assert result["department"] is None

    def test_request_text_preserved(self):
        from nextrequest_scraper import _transform_list_item
        result = _transform_list_item(SAMPLE_LIST_ITEM)
        assert "overtime records" in result["request_text"]


# ── Transform tests: detail ──────────────────────────────────

class TestTransformDetail:
    """Test _transform_detail with JSON fixtures."""

    def test_transforms_basic_metadata(self):
        from nextrequest_scraper import _transform_detail
        result = _transform_detail(SAMPLE_DETAIL_RESPONSE)
        assert result["request_number"] == "26-042"
        assert result["status"] == "Closed"
        assert result["department"] == "Police Department"
        assert result["requester_name"] == "John Doe"

    def test_strips_html_from_request_text(self):
        from nextrequest_scraper import _transform_detail
        result = _transform_detail(SAMPLE_DETAIL_RESPONSE)
        assert "<p>" not in result["request_text"]
        assert "overtime records" in result["request_text"]

    def test_parses_dates(self):
        from nextrequest_scraper import _transform_detail
        result = _transform_detail(SAMPLE_DETAIL_RESPONSE)
        assert result["submitted_date"] == "2026-01-15"
        assert result["due_date"] == "2026-01-25"

    def test_none_assigned_department_becomes_none(self):
        from nextrequest_scraper import _transform_detail
        result = _transform_detail(SAMPLE_DETAIL_NO_DEPT)
        assert result["department"] is None

    def test_poc_name_extracted(self):
        from nextrequest_scraper import _transform_detail
        result = _transform_detail(SAMPLE_DETAIL_RESPONSE)
        assert result["poc_name"] == "Jane Smith"

    def test_metadata_includes_field_values(self):
        from nextrequest_scraper import _transform_detail
        result = _transform_detail(SAMPLE_DETAIL_RESPONSE)
        field_values = result["metadata"]["field_values"]
        assert len(field_values) == 1
        assert field_values[0]["name"] == "Date(s) or Date Range(s) of Records"
        assert field_values[0]["value"] == "January 2025 - December 2025"

    def test_portal_url_generated(self):
        from nextrequest_scraper import _transform_detail
        result = _transform_detail(SAMPLE_DETAIL_RESPONSE)
        assert "26-042" in result["portal_url"]


# ── Timeline tests ───────────────────────────────────────────

class TestExtractClosedDate:
    """Test _extract_closed_date_from_timeline."""

    def test_extracts_closed_date(self):
        from nextrequest_scraper import _extract_closed_date_from_timeline
        result = _extract_closed_date_from_timeline(SAMPLE_TIMELINE_RESPONSE)
        assert result == "2026-01-22"

    def test_returns_none_when_not_closed(self):
        from nextrequest_scraper import _extract_closed_date_from_timeline
        timeline = {"timeline": [
            {"timeline_name": "Request Opened", "timeline_byline": "Jan 15, 2026"},
        ]}
        result = _extract_closed_date_from_timeline(timeline)
        assert result is None

    def test_returns_none_for_empty_timeline(self):
        from nextrequest_scraper import _extract_closed_date_from_timeline
        result = _extract_closed_date_from_timeline({"timeline": []})
        assert result is None


# ── HTML stripping ───────────────────────────────────────────

class TestStripHtml:
    """Test _strip_html utility."""

    def test_strips_simple_tags(self):
        from nextrequest_scraper import _strip_html
        assert _strip_html("<p>Hello world</p>") == "Hello world"

    def test_handles_none(self):
        from nextrequest_scraper import _strip_html
        assert _strip_html(None) == ""

    def test_handles_empty_string(self):
        from nextrequest_scraper import _strip_html
        assert _strip_html("") == ""

    def test_preserves_plain_text(self):
        from nextrequest_scraper import _strip_html
        assert _strip_html("No HTML here") == "No HTML here"


# ── Date parsing ─────────────────────────────────────────────

class TestDateParsing:
    """Test date parsing and days_to_close computation."""

    def test_parse_mm_dd_yyyy(self):
        from nextrequest_scraper import _parse_date
        assert _parse_date("01/15/2026") == "2026-01-15"

    def test_parse_month_dd_yyyy(self):
        from nextrequest_scraper import _parse_date
        assert _parse_date("January 15, 2026") == "2026-01-15"

    def test_parse_iso(self):
        from nextrequest_scraper import _parse_date
        assert _parse_date("2026-01-15") == "2026-01-15"

    def test_parse_none(self):
        from nextrequest_scraper import _parse_date
        assert _parse_date(None) is None

    def test_compute_days_to_close(self):
        from nextrequest_scraper import _compute_days_to_close
        assert _compute_days_to_close("2026-01-15", "2026-01-22") == 7

    def test_compute_days_to_close_none(self):
        from nextrequest_scraper import _compute_days_to_close
        assert _compute_days_to_close(None, "2026-01-22") is None


# ── Platform profile ──────────────────────────────────────────

class TestPlatformProfile:
    """Test that platform profile constants are correct."""

    def test_profile_has_required_fields(self):
        from nextrequest_scraper import NEXTREQUEST_PLATFORM_PROFILE
        assert "platform" in NEXTREQUEST_PLATFORM_PROFILE
        assert "url_pattern" in NEXTREQUEST_PLATFORM_PROFILE
        assert "spa" in NEXTREQUEST_PLATFORM_PROFILE
        assert NEXTREQUEST_PLATFORM_PROFILE["spa"] is True

    def test_base_url_is_richmond(self):
        from nextrequest_scraper import BASE_URL
        assert "richmond" in BASE_URL.lower()
        assert "nextrequest.com" in BASE_URL

    def test_city_fips_is_richmond(self):
        from nextrequest_scraper import CITY_FIPS
        assert CITY_FIPS == "0660620"


# ── Save to DB ────────────────────────────────────────────────

class TestSaveToDb:
    """Test database save/upsert logic."""

    def test_save_creates_request_record(self):
        from nextrequest_scraper import save_to_db
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        # Return a UUID for fetchone (upsert returning id)
        mock_cursor.fetchone.return_value = ("fake-uuid-001",)

        results = {
            "city_fips": "0660620",
            "requests": [{
                "request_number": "26-042",
                "request_text": "Overtime records",
                "status": "Closed",
                "department": "Police Department",
                "requester_name": "John Doe",
                "submitted_date": "2026-01-15",
                "due_date": "2026-01-25",
                "closed_date": "2026-01-22",
                "days_to_close": 7,
                "documents": [],
                "portal_url": "https://cityofrichmondca.nextrequest.com/requests/26-042",
                "metadata": {},
            }],
        }

        stats = save_to_db(mock_conn, results, "0660620")
        assert stats["requests_saved"] >= 1
        mock_conn.commit.assert_called()
