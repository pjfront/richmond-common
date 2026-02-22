"""Tests for the CivicPlus Archive Center discovery engine.

Tests use HTML fixtures — no network requests needed.
"""
import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path


# ── HTML fixtures ─────────────────────────────────────────────

SAMPLE_ARCHIVE_MODULE_HTML = """
<html>
<head><title>Archive Center - City Council Resolutions</title></head>
<body>
<div id="ArchiveCenter">
  <h1>City Council Resolutions</h1>
  <table class="archiveTable">
    <tr>
      <td><a href="/Archive.aspx?ADID=12345">Resolution 2026-001</a></td>
      <td>01/15/2026</td>
    </tr>
    <tr>
      <td><a href="/Archive.aspx?ADID=12346">Resolution 2026-002</a></td>
      <td>01/22/2026</td>
    </tr>
    <tr>
      <td><a href="/Archive.aspx?ADID=12347">Resolution 2026-003</a></td>
      <td>02/05/2026</td>
    </tr>
  </table>
</div>
</body>
</html>
"""

EMPTY_ARCHIVE_MODULE_HTML = """
<html>
<head><title>Archive Center</title></head>
<body>
<div id="ArchiveCenter">
  <h1>Neighborhood Council - North Richmond</h1>
  <p>No documents found.</p>
</div>
</body>
</html>
"""

INVALID_AMID_HTML = """
<html>
<head><title>Archive Center</title></head>
<body>
<div id="ArchiveCenter">
  <p>The archive you are looking for does not exist.</p>
</div>
</body>
</html>
"""


# ── Parsing tests ─────────────────────────────────────────────

class TestParseArchiveModule:
    """Test archive module HTML parsing."""

    def test_parses_module_name(self):
        from archive_center_discovery import _parse_archive_module
        result = _parse_archive_module(SAMPLE_ARCHIVE_MODULE_HTML, 67)
        assert result["name"] == "City Council Resolutions"

    def test_parses_document_count(self):
        from archive_center_discovery import _parse_archive_module
        result = _parse_archive_module(SAMPLE_ARCHIVE_MODULE_HTML, 67)
        assert result["document_count"] == 3

    def test_empty_module_returns_zero_docs(self):
        from archive_center_discovery import _parse_archive_module
        result = _parse_archive_module(EMPTY_ARCHIVE_MODULE_HTML, 94)
        assert result["document_count"] == 0
        assert result["name"] == "Neighborhood Council - North Richmond"

    def test_invalid_amid_returns_none(self):
        from archive_center_discovery import _parse_archive_module
        result = _parse_archive_module(INVALID_AMID_HTML, 999)
        assert result is None


class TestParseDocumentList:
    """Test document listing extraction from archive module HTML."""

    def test_extracts_documents(self):
        from archive_center_discovery import _parse_document_list
        docs = _parse_document_list(SAMPLE_ARCHIVE_MODULE_HTML)
        assert len(docs) == 3
        assert docs[0]["adid"] == "12345"
        assert docs[0]["title"] == "Resolution 2026-001"

    def test_extracts_dates(self):
        from archive_center_discovery import _parse_document_list
        docs = _parse_document_list(SAMPLE_ARCHIVE_MODULE_HTML)
        assert docs[0]["date"] == "2026-01-15"
        assert docs[2]["date"] == "2026-02-05"

    def test_empty_module_returns_empty(self):
        from archive_center_discovery import _parse_document_list
        docs = _parse_document_list(EMPTY_ARCHIVE_MODULE_HTML)
        assert docs == []


# ── Priority tier assignment ──────────────────────────────────

class TestPriorityTiers:
    """Test AMID priority tier classification."""

    def test_tier1_resolutions(self):
        from archive_center_discovery import get_download_tier
        assert get_download_tier(67) == 1  # Resolutions

    def test_tier1_ordinances(self):
        from archive_center_discovery import get_download_tier
        assert get_download_tier(66) == 1  # Ordinances

    def test_tier1_cm_reports(self):
        from archive_center_discovery import get_download_tier
        assert get_download_tier(87) == 1  # CM Weekly Reports

    def test_tier2_rent_board(self):
        from archive_center_discovery import get_download_tier
        assert get_download_tier(168) == 2  # Rent Board

    def test_tier3_unknown(self):
        from archive_center_discovery import get_download_tier
        assert get_download_tier(999) == 3  # Default


# ── Platform profile ──────────────────────────────────────────

class TestCivicPlusPlatformProfile:
    """Test platform profile constants."""

    def test_profile_fields(self):
        from archive_center_discovery import CIVICPLUS_PLATFORM_PROFILE
        assert "platform" in CIVICPLUS_PLATFORM_PROFILE
        assert CIVICPLUS_PLATFORM_PROFILE["uses_javascript_rendering"] is False

    def test_url_patterns(self):
        from archive_center_discovery import CIVICPLUS_BASE_URL
        assert "ci.richmond.ca.us" in CIVICPLUS_BASE_URL
