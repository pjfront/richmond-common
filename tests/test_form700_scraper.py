"""Tests for the Form 700 (SEI) scraper.

Parsing tests use static HTML fixtures — no Playwright or network needed.
Covers: date parsing, statement type normalization, filing year extraction,
grid HTML parsing, PDF URL attachment, config resolution, statistics output.
"""
import asyncio
import pytest
from unittest.mock import patch, MagicMock, AsyncMock


# ── HTML fixtures ─────────────────────────────────────────────

# NetFile SEI portal uses Telerik RadGrid — standard HTML table
# with a .rgMasterTable class. The actual portal renders filing
# data in columns: Name, Department, Title, Type, Filing Date, Period.
SAMPLE_FILING_GRID_HTML = """
<html><body>
<div class="RadGrid">
<table class="rgMasterTable">
  <thead>
    <tr>
      <th>Filer Name</th>
      <th>Department</th>
      <th>Title/Position</th>
      <th>Statement Type</th>
      <th>Filing Date</th>
      <th>Period</th>
    </tr>
  </thead>
  <tbody>
    <tr>
      <td>Eduardo Martinez</td>
      <td>City Council</td>
      <td>Mayor</td>
      <td>Annual Statement</td>
      <td>03/15/2024</td>
      <td>1/1/2023 - 12/31/2023</td>
    </tr>
    <tr>
      <td>Cesar Zepeda</td>
      <td>City Council</td>
      <td>Vice Mayor</td>
      <td>Assuming Office Statement</td>
      <td>01/10/2023</td>
      <td>1/1/2023 - 12/31/2023</td>
    </tr>
    <tr>
      <td><a href="https://netfile.com/Connect2/api/public/image/abc123">Sue Wilson</a></td>
      <td>City Council</td>
      <td>Council Member</td>
      <td>Annual</td>
      <td>04/01/2024</td>
      <td>1/1/2023 - 12/31/2023</td>
    </tr>
    <tr>
      <td>Lisa Campbell</td>
      <td>Finance Department</td>
      <td>Finance Director</td>
      <td>Leaving Office Statement</td>
      <td>06/15/2024</td>
      <td>1/1/2024 - 6/15/2024</td>
    </tr>
  </tbody>
</table>
</div>
</body></html>
"""

# Some portals render the grid without RadGrid class — just a plain table
PLAIN_TABLE_GRID_HTML = """
<html><body>
<table>
  <tr>
    <th>Name</th>
    <th>Dept</th>
    <th>Position</th>
    <th>Type</th>
    <th>Date Filed</th>
    <th>Period</th>
  </tr>
  <tr>
    <td>Tom Butt</td>
    <td>City Council</td>
    <td>Mayor</td>
    <td>Annual</td>
    <td>03/20/2020</td>
    <td>1/1/2019 - 12/31/2019</td>
  </tr>
</table>
</body></html>
"""

# Table with a View/Document link in a separate cell
TABLE_WITH_VIEW_LINKS_HTML = """
<html><body>
<table class="rgMasterTable">
  <tr>
    <th>Filer Name</th>
    <th>Department</th>
    <th>Statement Type</th>
    <th>Filing Date</th>
    <th>Period</th>
    <th>View</th>
  </tr>
  <tr>
    <td>Doria Robinson</td>
    <td>City Council</td>
    <td>Annual</td>
    <td>04/01/2024</td>
    <td>1/1/2023 - 12/31/2023</td>
    <td><a href="/api/public/image/xyz789">View Document</a></td>
  </tr>
</table>
</body></html>
"""

EMPTY_GRID_HTML = """
<html><body>
<div class="RadGrid">
<table class="rgMasterTable">
  <thead>
    <tr><th>Filer Name</th><th>Department</th></tr>
  </thead>
  <tbody></tbody>
</table>
</div>
</body></html>
"""

NO_TABLE_HTML = """
<html><body>
<div class="content">
  <p>No filings available.</p>
</div>
</body></html>
"""


# ── Date parsing tests ────────────────────────────────────────

class TestParseDate:
    """Test _parse_date with various date formats from portal."""

    def test_us_date_format(self):
        from form700_scraper import _parse_date
        assert _parse_date("03/15/2024") == "2024-03-15"

    def test_iso_format(self):
        from form700_scraper import _parse_date
        assert _parse_date("2024-03-15") == "2024-03-15"

    def test_long_month_format(self):
        from form700_scraper import _parse_date
        assert _parse_date("March 15, 2024") == "2024-03-15"

    def test_short_month_format(self):
        from form700_scraper import _parse_date
        assert _parse_date("Mar 15, 2024") == "2024-03-15"

    def test_us_date_with_time(self):
        from form700_scraper import _parse_date
        assert _parse_date("03/15/2024 02:30:00 PM") == "2024-03-15"

    def test_us_date_with_24h_time(self):
        from form700_scraper import _parse_date
        assert _parse_date("03/15/2024 14:30:00") == "2024-03-15"

    def test_none_returns_none(self):
        from form700_scraper import _parse_date
        assert _parse_date(None) is None

    def test_empty_string_returns_none(self):
        from form700_scraper import _parse_date
        assert _parse_date("") is None

    def test_whitespace_only_returns_none(self):
        from form700_scraper import _parse_date
        assert _parse_date("   ") is None

    def test_unparseable_returns_none(self):
        from form700_scraper import _parse_date
        assert _parse_date("not-a-date") is None

    def test_strips_whitespace(self):
        from form700_scraper import _parse_date
        assert _parse_date("  03/15/2024  ") == "2024-03-15"


# ── Statement type normalization ──────────────────────────────

class TestNormalizeStatementType:
    """Test _normalize_statement_type mapping from portal labels to schema values."""

    def test_annual(self):
        from form700_scraper import _normalize_statement_type
        assert _normalize_statement_type("Annual") == "annual"

    def test_annual_statement(self):
        from form700_scraper import _normalize_statement_type
        assert _normalize_statement_type("Annual Statement") == "annual"

    def test_assuming_office(self):
        from form700_scraper import _normalize_statement_type
        assert _normalize_statement_type("Assuming Office") == "assuming_office"

    def test_assuming_office_statement(self):
        from form700_scraper import _normalize_statement_type
        assert _normalize_statement_type("Assuming Office Statement") == "assuming_office"

    def test_leaving_office(self):
        from form700_scraper import _normalize_statement_type
        assert _normalize_statement_type("Leaving Office") == "leaving_office"

    def test_leaving_office_statement(self):
        from form700_scraper import _normalize_statement_type
        assert _normalize_statement_type("Leaving Office Statement") == "leaving_office"

    def test_candidate(self):
        from form700_scraper import _normalize_statement_type
        assert _normalize_statement_type("Candidate") == "candidate"

    def test_amendment(self):
        from form700_scraper import _normalize_statement_type
        assert _normalize_statement_type("Amendment") == "amendment"

    def test_case_insensitive(self):
        from form700_scraper import _normalize_statement_type
        assert _normalize_statement_type("ANNUAL STATEMENT") == "annual"

    def test_strips_whitespace(self):
        from form700_scraper import _normalize_statement_type
        assert _normalize_statement_type("  Annual  ") == "annual"

    def test_empty_defaults_to_annual(self):
        from form700_scraper import _normalize_statement_type
        assert _normalize_statement_type("") == "annual"

    def test_unknown_defaults_to_annual(self):
        from form700_scraper import _normalize_statement_type
        assert _normalize_statement_type("Something New") == "annual"


# ── Filing year extraction ────────────────────────────────────

class TestExtractFilingYear:
    """Test _extract_filing_year from period strings and filing dates."""

    def test_period_range(self):
        from form700_scraper import _extract_filing_year
        assert _extract_filing_year("1/1/2023 - 12/31/2023", None) == 2023

    def test_period_range_uses_end_year(self):
        """When period spans years, use the end year."""
        from form700_scraper import _extract_filing_year
        assert _extract_filing_year("7/1/2022 - 6/30/2023", None) == 2023

    def test_bare_year(self):
        from form700_scraper import _extract_filing_year
        assert _extract_filing_year("2024", None) == 2024

    def test_filing_date_fallback(self):
        from form700_scraper import _extract_filing_year
        assert _extract_filing_year(None, "03/15/2024") == 2024

    def test_period_takes_precedence(self):
        from form700_scraper import _extract_filing_year
        # Period says 2023, filing date says 2024 — period wins
        assert _extract_filing_year("1/1/2023 - 12/31/2023", "03/15/2024") == 2023

    def test_no_data_returns_none(self):
        from form700_scraper import _extract_filing_year
        assert _extract_filing_year(None, None) is None

    def test_empty_strings(self):
        from form700_scraper import _extract_filing_year
        assert _extract_filing_year("", "") is None

    def test_no_year_in_string(self):
        from form700_scraper import _extract_filing_year
        assert _extract_filing_year("no year here", None) is None


# ── Period date extraction ────────────────────────────────────

class TestExtractPeriodDates:
    """Test _extract_period_dates splitting period strings into start/end."""

    def test_standard_range(self):
        from form700_scraper import _extract_period_dates
        start, end = _extract_period_dates("1/1/2023 - 12/31/2023")
        assert start == "2023-01-01"
        assert end == "2023-12-31"

    def test_no_spaces_around_dash(self):
        from form700_scraper import _extract_period_dates
        start, end = _extract_period_dates("01/01/2024-12/31/2024")
        assert start == "2024-01-01"
        assert end == "2024-12-31"

    def test_en_dash(self):
        from form700_scraper import _extract_period_dates
        start, end = _extract_period_dates("1/1/2024 \u2013 12/31/2024")
        assert start == "2024-01-01"
        assert end == "2024-12-31"

    def test_partial_year_period(self):
        from form700_scraper import _extract_period_dates
        start, end = _extract_period_dates("1/1/2024 - 6/15/2024")
        assert start == "2024-01-01"
        assert end == "2024-06-15"

    def test_none_returns_none_tuple(self):
        from form700_scraper import _extract_period_dates
        assert _extract_period_dates(None) == (None, None)

    def test_empty_returns_none_tuple(self):
        from form700_scraper import _extract_period_dates
        assert _extract_period_dates("") == (None, None)

    def test_single_date_returns_none_tuple(self):
        """A period with no dash can't be split into start/end."""
        from form700_scraper import _extract_period_dates
        assert _extract_period_dates("03/15/2024") == (None, None)


# ── Grid parsing tests ────────────────────────────────────────

class TestParseFilingGrid:
    """Test _parse_filing_grid with HTML fixtures."""

    def test_parses_four_filings(self):
        from form700_scraper import _parse_filing_grid
        filings = _parse_filing_grid(SAMPLE_FILING_GRID_HTML)
        assert len(filings) == 4

    def test_first_filing_fields(self):
        from form700_scraper import _parse_filing_grid
        filings = _parse_filing_grid(SAMPLE_FILING_GRID_HTML)
        f = filings[0]
        assert f["filer_name"] == "Eduardo Martinez"
        assert f["department"] == "City Council"
        assert f["position"] == "Mayor"
        assert f["statement_type"] == "annual"
        assert f["filing_date"] == "2024-03-15"
        assert f["filing_year"] == 2023
        assert f["period_start"] == "2023-01-01"
        assert f["period_end"] == "2023-12-31"

    def test_assuming_office_type(self):
        from form700_scraper import _parse_filing_grid
        filings = _parse_filing_grid(SAMPLE_FILING_GRID_HTML)
        f = filings[1]  # Cesar Zepeda
        assert f["filer_name"] == "Cesar Zepeda"
        assert f["statement_type"] == "assuming_office"

    def test_leaving_office_type(self):
        from form700_scraper import _parse_filing_grid
        filings = _parse_filing_grid(SAMPLE_FILING_GRID_HTML)
        f = filings[3]  # Lisa Campbell
        assert f["statement_type"] == "leaving_office"
        assert f["department"] == "Finance Department"

    def test_inline_pdf_link_detected(self):
        """When a filer name is a link to Connect2 image API, capture it."""
        from form700_scraper import _parse_filing_grid
        filings = _parse_filing_grid(SAMPLE_FILING_GRID_HTML)
        sue = filings[2]
        assert sue["filer_name"] == "Sue Wilson"
        assert sue["detail_url"] is not None
        assert "Connect2/api/public/image/abc123" in sue["detail_url"]

    def test_view_column_link_detected(self):
        """When PDF link is in a separate 'View' column, capture it."""
        from form700_scraper import _parse_filing_grid
        filings = _parse_filing_grid(TABLE_WITH_VIEW_LINKS_HTML)
        assert len(filings) == 1
        f = filings[0]
        assert f["filer_name"] == "Doria Robinson"
        assert f["detail_url"] is not None
        assert "image/xyz789" in f["detail_url"]

    def test_row_index_assigned(self):
        from form700_scraper import _parse_filing_grid
        filings = _parse_filing_grid(SAMPLE_FILING_GRID_HTML)
        assert filings[0]["row_index"] == 1
        assert filings[1]["row_index"] == 2
        assert filings[3]["row_index"] == 4

    def test_plain_table_fallback(self):
        """When no RadGrid class, falls back to largest table."""
        from form700_scraper import _parse_filing_grid
        filings = _parse_filing_grid(PLAIN_TABLE_GRID_HTML)
        assert len(filings) == 1
        assert filings[0]["filer_name"] == "Tom Butt"
        assert filings[0]["filing_year"] == 2019

    def test_empty_grid_returns_empty(self):
        from form700_scraper import _parse_filing_grid
        filings = _parse_filing_grid(EMPTY_GRID_HTML)
        assert filings == []

    def test_no_table_returns_empty(self):
        from form700_scraper import _parse_filing_grid
        filings = _parse_filing_grid(NO_TABLE_HTML)
        assert filings == []

    def test_garbled_html_returns_empty(self):
        from form700_scraper import _parse_filing_grid
        filings = _parse_filing_grid("<html><body>garbage</body></html>")
        assert filings == []


# ── PDF URL attachment ────────────────────────────────────────

class TestAttachPdfUrls:
    """Test _attach_pdf_urls matching logic."""

    def test_attaches_by_name_match(self):
        from form700_scraper import _attach_pdf_urls
        filings = [
            {"filer_name": "Eduardo Martinez", "detail_url": None},
            {"filer_name": "Cesar Zepeda", "detail_url": None},
        ]
        pdf_links = [
            {"href": "https://netfile.com/image/abc", "text": "View", "row_text": "Eduardo Martinez City Council Annual"},
            {"href": "https://netfile.com/image/def", "text": "View", "row_text": "Cesar Zepeda City Council Assuming Office"},
        ]
        _attach_pdf_urls(filings, pdf_links)
        assert filings[0]["detail_url"] == "https://netfile.com/image/abc"
        assert filings[1]["detail_url"] == "https://netfile.com/image/def"

    def test_skips_if_url_already_set(self):
        from form700_scraper import _attach_pdf_urls
        filings = [
            {"filer_name": "Eduardo Martinez", "detail_url": "https://existing.com/pdf"},
        ]
        pdf_links = [
            {"href": "https://netfile.com/image/new", "text": "View", "row_text": "Eduardo Martinez"},
        ]
        _attach_pdf_urls(filings, pdf_links)
        assert filings[0]["detail_url"] == "https://existing.com/pdf"

    def test_case_insensitive_name_match(self):
        from form700_scraper import _attach_pdf_urls
        filings = [
            {"filer_name": "Eduardo Martinez", "detail_url": None},
        ]
        pdf_links = [
            {"href": "https://netfile.com/image/abc", "text": "View", "row_text": "EDUARDO MARTINEZ ANNUAL"},
        ]
        _attach_pdf_urls(filings, pdf_links)
        assert filings[0]["detail_url"] == "https://netfile.com/image/abc"

    def test_no_match_leaves_none(self):
        from form700_scraper import _attach_pdf_urls
        filings = [
            {"filer_name": "Nobody Here", "detail_url": None},
        ]
        pdf_links = [
            {"href": "https://netfile.com/image/abc", "text": "View", "row_text": "Eduardo Martinez Annual"},
        ]
        _attach_pdf_urls(filings, pdf_links)
        assert filings[0]["detail_url"] is None

    def test_empty_pdf_links(self):
        from form700_scraper import _attach_pdf_urls
        filings = [{"filer_name": "Test Person", "detail_url": None}]
        _attach_pdf_urls(filings, [])
        assert filings[0]["detail_url"] is None


# ── Config resolution ─────────────────────────────────────────

class TestResolveConfig:
    """Test _resolve_form700_config with and without city registry."""

    def test_default_returns_richmond(self):
        from form700_scraper import _resolve_form700_config, NETFILE_SEI_URL, CITY_FIPS
        url, fips = _resolve_form700_config(None)
        assert url == NETFILE_SEI_URL
        assert fips == CITY_FIPS

    def test_explicit_fips_uses_registry(self):
        from form700_scraper import _resolve_form700_config
        url, fips = _resolve_form700_config("0660620")
        assert "netfile.com" in url
        assert fips == "0660620"

    def test_invalid_fips_raises(self):
        from form700_scraper import _resolve_form700_config
        from city_config import CityNotConfiguredError
        with pytest.raises(CityNotConfiguredError):
            _resolve_form700_config("9999999")


# ── Constants and module-level checks ─────────────────────────

class TestModuleConstants:
    """Verify module-level constants match project conventions."""

    def test_city_fips_is_richmond(self):
        from form700_scraper import CITY_FIPS
        assert CITY_FIPS == "0660620"

    def test_statement_types_covers_all_form_types(self):
        from form700_scraper import STATEMENT_TYPES
        values = set(STATEMENT_TYPES.values())
        expected = {"annual", "assuming_office", "leaving_office", "candidate", "amendment"}
        assert expected == values

    def test_netfile_url_is_richmond(self):
        from form700_scraper import NETFILE_SEI_URL
        assert "RICH" in NETFILE_SEI_URL
        assert "netfile.com" in NETFILE_SEI_URL


# ── Statistics output ─────────────────────────────────────────

class TestPrintFilingStats:
    """Test print_filing_stats output formatting."""

    def test_stats_with_data(self, capsys):
        from form700_scraper import print_filing_stats
        filings = [
            {"filer_name": "Eduardo Martinez", "department": "City Council",
             "filing_year": 2023, "statement_type": "annual", "detail_url": "http://example.com/pdf"},
            {"filer_name": "Cesar Zepeda", "department": "City Council",
             "filing_year": 2023, "statement_type": "assuming_office", "detail_url": None},
            {"filer_name": "Eduardo Martinez", "department": "City Council",
             "filing_year": 2022, "statement_type": "annual", "detail_url": "http://example.com/pdf2"},
        ]
        print_filing_stats(filings)
        output = capsys.readouterr().out
        assert "Total filings:    3" in output
        assert "With PDF URLs:    2" in output
        assert "Unique filers:    2" in output
        assert "City Council" in output
        assert "2023" in output
        assert "2022" in output

    def test_stats_empty(self, capsys):
        from form700_scraper import print_filing_stats
        print_filing_stats([])
        output = capsys.readouterr().out
        assert "No filings found" in output

    def test_stats_unknown_department(self, capsys):
        from form700_scraper import print_filing_stats
        filings = [
            {"filer_name": "Test", "department": None,
             "filing_year": None, "statement_type": None, "detail_url": None},
        ]
        print_filing_stats(filings)
        output = capsys.readouterr().out
        assert "Unknown" in output

    def test_stats_many_departments_truncated(self, capsys):
        """When >15 departments, output should indicate truncation."""
        from form700_scraper import print_filing_stats
        filings = [
            {"filer_name": f"Person {i}", "department": f"Dept {i}",
             "filing_year": 2023, "statement_type": "annual", "detail_url": None}
            for i in range(20)
        ]
        print_filing_stats(filings)
        output = capsys.readouterr().out
        assert "... and" in output


# ── Document storage ──────────────────────────────────────────

class TestSaveFilingToDocuments:
    """Test save_filing_to_documents with mocked db.ingest_document."""

    @patch("db.ingest_document")
    def test_saves_pdf_to_layer1(self, mock_ingest):
        """Save filing delegates to db.ingest_document with correct params."""
        # ingest_document is lazily imported inside save_filing_to_documents
        # via `from db import ingest_document`, so we patch at the source (db module)
        from form700_scraper import save_filing_to_documents

        mock_conn = MagicMock()
        mock_ingest.return_value = "fake-uuid-001"

        filing = {
            "filer_name": "Eduardo Martinez",
            "department": "City Council",
            "position": "Mayor",
            "statement_type": "annual",
            "filing_year": 2023,
            "filing_date": "2024-03-15",
            "period": "1/1/2023 - 12/31/2023",
            "detail_url": "https://netfile.com/image/abc123",
        }

        result = save_filing_to_documents(mock_conn, filing, b"%PDF-fake-content")
        assert result == "fake-uuid-001"

        # Verify ingest_document was called with correct arguments
        mock_ingest.assert_called_once()
        call_kwargs = mock_ingest.call_args
        assert call_kwargs[1]["city_fips"] == "0660620"
        assert call_kwargs[1]["source_type"] == "form700"
        assert call_kwargs[1]["credibility_tier"] == 1
        assert call_kwargs[1]["mime_type"] == "application/pdf"
        assert "Eduardo Martinez" in call_kwargs[1]["source_identifier"]

    @patch("db.ingest_document")
    def test_save_failure_returns_none(self, mock_ingest):
        from form700_scraper import save_filing_to_documents

        mock_conn = MagicMock()
        mock_ingest.side_effect = Exception("DB connection failed")

        filing = {
            "filer_name": "Test Person",
            "filing_year": 2023,
            "detail_url": "",
        }

        result = save_filing_to_documents(mock_conn, filing, b"%PDF-content")
        assert result is None


# ── City config integration ───────────────────────────────────

class TestCityConfigIntegration:
    """Verify the form700 config is properly registered in city_config.py."""

    def test_form700_config_exists(self):
        from city_config import get_data_source_config
        cfg = get_data_source_config("0660620", "form700")
        assert cfg is not None

    def test_config_has_netfile_sei_url(self):
        from city_config import get_data_source_config
        cfg = get_data_source_config("0660620", "form700")
        assert "netfile_sei_url" in cfg
        assert "netfile.com" in cfg["netfile_sei_url"]

    def test_config_has_fppc_urls(self):
        from city_config import get_data_source_config
        cfg = get_data_source_config("0660620", "form700")
        assert "fppc_search_url" in cfg
        assert "fppc_agency_name" in cfg

    def test_config_credibility_tier1(self):
        """Form 700 filings are official government records — Tier 1."""
        from city_config import get_data_source_config
        cfg = get_data_source_config("0660620", "form700")
        assert cfg["credibility_tier"] == 1

    def test_config_has_agency_id(self):
        from city_config import get_data_source_config
        cfg = get_data_source_config("0660620", "form700")
        assert cfg["netfile_sei_agency_id"] == "RICH"

    def test_config_platform_string(self):
        from city_config import get_data_source_config
        cfg = get_data_source_config("0660620", "form700")
        assert "NetFile" in cfg["platform"]
        assert "FPPC" in cfg["platform"]


# ── Download function ─────────────────────────────────────────

class TestDownloadFilingPdf:
    """Test download_filing_pdf with mocked HTTP requests.

    These are async functions tested synchronously via asyncio.run().
    The download function uses a lazy `import requests` inside the
    function body, so we patch at the source: `requests.get`.
    """

    @patch("requests.get")
    def test_downloads_valid_pdf(self, mock_get, tmp_path):
        from form700_scraper import download_filing_pdf

        mock_resp = MagicMock()
        mock_resp.content = b"%PDF-1.4 fake pdf content"
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        result = asyncio.run(download_filing_pdf(
            "https://netfile.com/image/abc",
            dest_dir=tmp_path,
            filer_name="Eduardo Martinez",
            filing_year=2023,
        ))
        assert result is not None
        assert result.exists()
        assert "eduardo_martinez" in result.name
        assert "2023" in result.name

    @patch("requests.get")
    def test_rejects_non_pdf_response(self, mock_get, tmp_path):
        from form700_scraper import download_filing_pdf

        mock_resp = MagicMock()
        mock_resp.content = b"<html>Not a PDF</html>"
        mock_resp.status_code = 200
        mock_get.return_value = mock_resp

        result = asyncio.run(download_filing_pdf(
            "https://netfile.com/image/abc",
            dest_dir=tmp_path,
            filer_name="Test Person",
            filing_year=2023,
        ))
        assert result is None

    @patch("requests.get")
    def test_skips_if_already_downloaded(self, mock_get, tmp_path):
        from form700_scraper import download_filing_pdf

        # Pre-create the file
        filepath = tmp_path / "test_person_2023.pdf"
        filepath.write_bytes(b"%PDF-existing")

        result = asyncio.run(download_filing_pdf(
            "https://netfile.com/image/abc",
            dest_dir=tmp_path,
            filer_name="Test Person",
            filing_year=2023,
        ))
        assert result is not None
        # Should not have made a request
        mock_get.assert_not_called()

    @patch("requests.get")
    def test_handles_request_failure(self, mock_get, tmp_path):
        from form700_scraper import download_filing_pdf

        mock_get.side_effect = Exception("Network error")

        result = asyncio.run(download_filing_pdf(
            "https://netfile.com/image/abc",
            dest_dir=tmp_path,
            filer_name="Test Person",
            filing_year=2023,
        ))
        assert result is None


# ── Download all filings ──────────────────────────────────────

class TestDownloadAllFilings:
    """Test download_all_filings orchestration logic."""

    @patch("form700_scraper.download_filing_pdf", new_callable=AsyncMock)
    def test_filters_by_year(self, mock_download):
        from form700_scraper import download_all_filings

        mock_download.return_value = None

        filings = [
            {"filer_name": "Person A", "filing_year": 2023, "detail_url": "http://a.com"},
            {"filer_name": "Person B", "filing_year": 2024, "detail_url": "http://b.com"},
            {"filer_name": "Person C", "filing_year": 2023, "detail_url": "http://c.com"},
        ]

        asyncio.run(download_all_filings(filings, filing_year=2023))
        # Should only attempt Person A and Person C (2023)
        assert mock_download.call_count == 2

    @patch("form700_scraper.download_filing_pdf", new_callable=AsyncMock)
    def test_skips_filings_without_url(self, mock_download):
        from form700_scraper import download_all_filings

        mock_download.return_value = None

        filings = [
            {"filer_name": "Has URL", "filing_year": 2023, "detail_url": "http://a.com"},
            {"filer_name": "No URL", "filing_year": 2023, "detail_url": None},
            {"filer_name": "Empty URL", "filing_year": 2023},
        ]

        asyncio.run(download_all_filings(filings))
        # Only the first has a URL
        assert mock_download.call_count == 1
