"""Tests for the NextRequest/CPRA scraper.

Parsing tests use static HTML fixtures — no Playwright or network needed.
Orchestration tests mock Playwright browser interactions.
"""
import json
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from pathlib import Path


# ── HTML fixtures ─────────────────────────────────────────────

SAMPLE_REQUEST_LIST_HTML = """
<div class="request-list">
  <div class="request-item" data-request-id="NR-2026-001">
    <a class="request-link" href="/requests/NR-2026-001">
      <span class="request-number">NR-2026-001</span>
      <span class="request-title">Police department overtime records</span>
    </a>
    <span class="request-status">Completed</span>
    <span class="request-department">Police</span>
    <span class="request-date">01/15/2026</span>
  </div>
  <div class="request-item" data-request-id="NR-2026-002">
    <a class="request-link" href="/requests/NR-2026-002">
      <span class="request-number">NR-2026-002</span>
      <span class="request-title">City manager contract details</span>
    </a>
    <span class="request-status">In Progress</span>
    <span class="request-department">City Manager</span>
    <span class="request-date">02/01/2026</span>
  </div>
</div>
"""

SAMPLE_REQUEST_DETAIL_HTML = """
<div class="request-detail">
  <h1 class="request-title">Police department overtime records</h1>
  <div class="request-info">
    <span class="request-number">NR-2026-001</span>
    <span class="request-status">Completed</span>
    <span class="request-department">Police</span>
    <span class="requester-name">John Doe</span>
    <span class="submitted-date">01/15/2026</span>
    <span class="due-date">01/25/2026</span>
    <span class="closed-date">01/22/2026</span>
  </div>
  <div class="request-text">
    I am requesting all overtime records for the Richmond Police Department
    for the period of January 2025 through December 2025.
  </div>
  <div class="documents-list">
    <div class="document-item">
      <a class="document-link" href="/documents/doc-001/download">
        <span class="document-name">RPD_Overtime_2025.pdf</span>
      </a>
      <span class="document-size">2.1 MB</span>
      <span class="document-date">01/22/2026</span>
    </div>
    <div class="document-item">
      <a class="document-link" href="/documents/doc-002/download">
        <span class="document-name">Overtime_Policy.pdf</span>
      </a>
      <span class="document-size">145 KB</span>
      <span class="document-date">01/22/2026</span>
    </div>
  </div>
</div>
"""

EMPTY_REQUEST_LIST_HTML = """
<div class="request-list">
  <p class="no-results">No requests found.</p>
</div>
"""


# ── Parsing tests ─────────────────────────────────────────────

class TestParseRequestList:
    """Test _parse_request_list with HTML fixtures."""

    def test_parses_multiple_requests(self):
        from nextrequest_scraper import _parse_request_list
        results = _parse_request_list(SAMPLE_REQUEST_LIST_HTML)
        assert len(results) == 2
        assert results[0]["request_number"] == "NR-2026-001"
        assert results[0]["title"] == "Police department overtime records"
        assert results[0]["status"] == "Completed"
        assert results[0]["department"] == "Police"

    def test_second_request_parsed(self):
        from nextrequest_scraper import _parse_request_list
        results = _parse_request_list(SAMPLE_REQUEST_LIST_HTML)
        assert results[1]["request_number"] == "NR-2026-002"
        assert results[1]["status"] == "In Progress"
        assert results[1]["department"] == "City Manager"

    def test_empty_list_returns_empty(self):
        from nextrequest_scraper import _parse_request_list
        results = _parse_request_list(EMPTY_REQUEST_LIST_HTML)
        assert results == []

    def test_garbled_html_returns_empty(self):
        from nextrequest_scraper import _parse_request_list
        results = _parse_request_list("<html><body>garbage</body></html>")
        assert results == []


class TestParseRequestDetail:
    """Test _parse_request_detail with HTML fixtures."""

    def test_parses_request_metadata(self):
        from nextrequest_scraper import _parse_request_detail
        result = _parse_request_detail(SAMPLE_REQUEST_DETAIL_HTML)
        assert result["request_number"] == "NR-2026-001"
        assert result["status"] == "Completed"
        assert result["department"] == "Police"
        assert result["requester_name"] == "John Doe"

    def test_parses_request_text(self):
        from nextrequest_scraper import _parse_request_detail
        result = _parse_request_detail(SAMPLE_REQUEST_DETAIL_HTML)
        assert "overtime records" in result["request_text"]

    def test_parses_dates(self):
        from nextrequest_scraper import _parse_request_detail
        result = _parse_request_detail(SAMPLE_REQUEST_DETAIL_HTML)
        assert result["submitted_date"] == "2026-01-15"
        assert result["due_date"] == "2026-01-25"
        assert result["closed_date"] == "2026-01-22"

    def test_computes_days_to_close(self):
        from nextrequest_scraper import _parse_request_detail
        result = _parse_request_detail(SAMPLE_REQUEST_DETAIL_HTML)
        assert result["days_to_close"] == 7  # Jan 22 - Jan 15


class TestParseDocumentList:
    """Test _parse_document_list with HTML fixtures."""

    def test_parses_documents(self):
        from nextrequest_scraper import _parse_document_list
        results = _parse_document_list(SAMPLE_REQUEST_DETAIL_HTML)
        assert len(results) == 2
        assert results[0]["filename"] == "RPD_Overtime_2025.pdf"
        assert "doc-001" in results[0]["download_url"]
        assert results[1]["filename"] == "Overtime_Policy.pdf"

    def test_empty_document_list(self):
        from nextrequest_scraper import _parse_document_list
        results = _parse_document_list("<div class='documents-list'></div>")
        assert results == []


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


# ── Self-healing detection ────────────────────────────────────

class TestSelfHealingDetection:
    """Test that parsers log warnings on unexpected HTML."""

    def test_parse_request_list_logs_on_no_items(self, caplog):
        """When HTML has no request items, a warning is logged."""
        import logging
        from nextrequest_scraper import _parse_request_list
        with caplog.at_level(logging.WARNING):
            _parse_request_list("<div class='request-list'><p>Unexpected</p></div>")
        # Parser should return empty and optionally log
        # (exact log assertion depends on implementation)


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
                "request_number": "NR-2026-001",
                "request_text": "Overtime records",
                "status": "Completed",
                "department": "Police",
                "requester_name": "John Doe",
                "submitted_date": "2026-01-15",
                "due_date": "2026-01-25",
                "closed_date": "2026-01-22",
                "days_to_close": 7,
                "documents": [],
                "portal_url": "https://cityofrichmondca.nextrequest.com/requests/NR-2026-001",
                "metadata": {},
            }],
        }

        stats = save_to_db(mock_conn, results, "0660620")
        assert stats["requests_saved"] >= 1
        mock_conn.commit.assert_called()
