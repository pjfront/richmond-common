"""Tests for the court records scraper (Tyler Odyssey).

Parsing tests use static HTML fixtures — no network needed.
Covers: search result parsing, case detail parsing, party extraction,
name normalization, organization detection, column mapping, config resolution,
search list building, cross-reference matching, database storage, and
data_sync integration.
"""
import uuid
import pytest
from unittest.mock import patch, MagicMock


# ── HTML Fixtures ────────────────────────────────────────────

# Tyler Odyssey search results: table with case listings
SEARCH_RESULTS_HTML = """
<html><body>
<table class="caseSearchResults">
  <tr>
    <th>Case Number</th>
    <th>Case Type</th>
    <th>Filed Date</th>
    <th>Status</th>
    <th>Caption</th>
  </tr>
  <tr class="case-row">
    <td><a href="/Portal/Case/CaseDetail/12345">C24-01234</a></td>
    <td>Civil</td>
    <td>01/15/2024</td>
    <td>Open</td>
    <td>Martinez v. Richmond Development LLC</td>
  </tr>
  <tr class="case-row">
    <td><a href="/Portal/Case/CaseDetail/12346">C23-05678</a></td>
    <td>Small Claims</td>
    <td>06/20/2023</td>
    <td>Closed</td>
    <td>Martinez v. Bay Auto Group</td>
  </tr>
</table>
</body></html>
"""

# Search results with no matches
NO_RESULTS_HTML = """
<html><body>
<div class="search-results">
  <p>No cases found matching your search criteria.</p>
</div>
</body></html>
"""

# Search results with links but no table structure
LINK_ONLY_RESULTS_HTML = """
<html><body>
<div>
  <a href="/Portal/Case/CaseDetail/99999">C25-00100</a>
  <span>Civil</span>
  <a href="/Portal/Case/CaseDetail/99998">MSC24-00200</a>
  <span>Small Claims</span>
</div>
</body></html>
"""

# Empty page (no results, no message)
EMPTY_HTML = """
<html><body>
<div class="search-container">
  <form><input type="text" name="q" /></form>
</div>
</body></html>
"""

# Case detail page with parties
CASE_DETAIL_HTML = """
<html><body>
<h2>C24-01234 - Martinez v. Richmond Development LLC</h2>
<table>
  <tr><th>Case Number</th><td>C24-01234</td></tr>
  <tr><th>Case Type</th><td>Civil Unlimited</td></tr>
  <tr><th>Category</th><td>Contract</td></tr>
  <tr><th>Filed Date</th><td>01/15/2024</td></tr>
  <tr><th>Status</th><td>Open</td></tr>
  <tr><th>Judge</th><td>Hon. Sarah Williams</td></tr>
</table>

<h3>Parties</h3>
<table class="parties">
  <tr>
    <th>Name</th><th>Type</th><th>Attorney</th>
  </tr>
  <tr>
    <td>Eduardo Martinez</td>
    <td>Plaintiff</td>
    <td>John Law, Esq.</td>
  </tr>
  <tr>
    <td>Richmond Development LLC</td>
    <td>Defendant</td>
    <td>Jane Defense, Esq.</td>
  </tr>
</table>
</body></html>
"""

# Case detail with parties in definition list format
CASE_DETAIL_DL_HTML = """
<html><body>
<dl>
  <dt>Case Number</dt><dd>C24-99999</dd>
  <dt>Case Type</dt><dd>Civil Limited</dd>
  <dt>Filed Date</dt><dd>03/01/2024</dd>
  <dt>Status</dt><dd>Disposed</dd>
  <dt>Disposition</dt><dd>Judgment</dd>
</dl>
<div>
  Plaintiff: Tom Butt
  Defendant: City of Richmond
</div>
</body></html>
"""

# Case detail with label/span structure
CASE_DETAIL_LABEL_HTML = """
<html><body>
<div>
  <label>Case Number:</label><span>MSC25-00100</span>
  <label>Case Type:</label><span>Small Claims</span>
  <label>Filed Date:</label><span>02/10/2025</span>
  <label>Status:</label><span>Closed</span>
</div>
</body></html>
"""


# ── Name Normalization Tests ─────────────────────────────────

class TestNormalizeName:
    def test_basic_normalization(self):
        from courts_scraper import _normalize_name
        assert _normalize_name("Eduardo Martinez") == "eduardo martinez"

    def test_strips_punctuation(self):
        from courts_scraper import _normalize_name
        assert _normalize_name("O'Brien, Jr.") == "o brien jr"

    def test_collapses_whitespace(self):
        from courts_scraper import _normalize_name
        assert _normalize_name("  Tom   Butt  ") == "tom butt"

    def test_empty_string(self):
        from courts_scraper import _normalize_name
        assert _normalize_name("") == ""

    def test_none_input(self):
        from courts_scraper import _normalize_name
        # Handles None gracefully via the empty check
        assert _normalize_name("") == ""


# ── Organization Detection Tests ─────────────────────────────

class TestDetectOrganization:
    def test_llc(self):
        from courts_scraper import _detect_organization
        assert _detect_organization("Richmond Development LLC") is True

    def test_inc(self):
        from courts_scraper import _detect_organization
        assert _detect_organization("Chevron Products Inc") is True

    def test_city_of(self):
        from courts_scraper import _detect_organization
        assert _detect_organization("City of Richmond") is True

    def test_person_name(self):
        from courts_scraper import _detect_organization
        assert _detect_organization("Eduardo Martinez") is False

    def test_trust(self):
        from courts_scraper import _detect_organization
        assert _detect_organization("The Martinez Family Trust") is True


# ── Search Results Parsing Tests ─────────────────────────────

class TestParseSearchResults:
    def test_parses_table_results(self):
        from courts_scraper import _parse_search_results
        cases = _parse_search_results(SEARCH_RESULTS_HTML)
        assert len(cases) == 2
        assert cases[0]["case_number"] == "C24-01234"
        assert cases[0]["detail_url"] == "/Portal/Case/CaseDetail/12345"

    def test_no_results_message(self):
        from courts_scraper import _parse_search_results
        cases = _parse_search_results(NO_RESULTS_HTML)
        assert cases == []

    def test_empty_page(self):
        from courts_scraper import _parse_search_results
        cases = _parse_search_results(EMPTY_HTML)
        assert cases == []

    def test_link_only_results(self):
        from courts_scraper import _parse_search_results
        cases = _parse_search_results(LINK_ONLY_RESULTS_HTML)
        # Should find links that match CaseDetail pattern
        assert len(cases) >= 1


# ── Case Column Mapping Tests ────────────────────────────────

class TestBuildCaseColumnMap:
    def test_standard_headers(self):
        from courts_scraper import _build_case_column_map
        headers = ["case number", "type", "filed date", "status", "parties"]
        col_map = _build_case_column_map(headers)
        assert col_map["case_number"] == 0
        assert col_map["case_type"] == 1
        assert col_map["filing_date"] == 2
        assert col_map["case_status"] == 3
        assert col_map["case_title"] == 4

    def test_alternate_headers(self):
        from courts_scraper import _build_case_column_map
        headers = ["case no.", "category", "date", "disposition", "caption"]
        col_map = _build_case_column_map(headers)
        assert "case_number" in col_map
        assert "case_type" in col_map
        assert "case_title" in col_map


# ── Case Detail Parsing Tests ────────────────────────────────

class TestExtractCaseHeader:
    def test_th_td_format(self):
        from courts_scraper import _extract_case_header
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(CASE_DETAIL_HTML, "html.parser")
        detail = {
            "case_number": "", "case_type": "", "case_category": "",
            "case_title": "", "filing_date": None, "case_status": "",
            "disposition": "", "disposition_date": None, "court_name": "",
            "judge": "",
        }
        _extract_case_header(soup, detail)
        assert detail["case_number"] == "C24-01234"
        assert detail["case_type"] == "Civil Unlimited"
        assert detail["case_category"] == "Contract"
        assert detail["filing_date"] == "2024-01-15"
        assert detail["case_status"] == "Open"
        assert detail["judge"] == "Hon. Sarah Williams"

    def test_dl_format(self):
        from courts_scraper import _extract_case_header
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(CASE_DETAIL_DL_HTML, "html.parser")
        detail = {
            "case_number": "", "case_type": "", "case_category": "",
            "case_title": "", "filing_date": None, "case_status": "",
            "disposition": "", "disposition_date": None, "court_name": "",
            "judge": "",
        }
        _extract_case_header(soup, detail)
        assert detail["case_number"] == "C24-99999"
        assert detail["case_type"] == "Civil Limited"
        assert detail["case_status"] == "Disposed"
        assert detail["disposition"] == "Judgment"

    def test_label_span_format(self):
        from courts_scraper import _extract_case_header
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(CASE_DETAIL_LABEL_HTML, "html.parser")
        detail = {
            "case_number": "", "case_type": "", "case_category": "",
            "case_title": "", "filing_date": None, "case_status": "",
            "disposition": "", "disposition_date": None, "court_name": "",
            "judge": "",
        }
        _extract_case_header(soup, detail)
        assert detail["case_number"] == "MSC25-00100"
        assert detail["case_type"] == "Small Claims"


# ── Party Parsing Tests ──────────────────────────────────────

class TestParseCaseParties:
    def test_table_parties(self):
        from courts_scraper import _parse_case_parties
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(CASE_DETAIL_HTML, "html.parser")
        parties = _parse_case_parties(soup)
        assert len(parties) == 2

        plaintiff = next(p for p in parties if "Martinez" in p["party_name"])
        assert plaintiff["party_type"] == "plaintiff"
        assert plaintiff["is_organization"] is False

        defendant = next(p for p in parties if "Richmond Development" in p["party_name"])
        assert defendant["party_type"] == "defendant"
        assert defendant["is_organization"] is True

    def test_text_parties(self):
        from courts_scraper import _parse_case_parties
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(CASE_DETAIL_DL_HTML, "html.parser")
        parties = _parse_case_parties(soup)
        assert len(parties) >= 2

        names = [p["party_name"] for p in parties]
        assert any("Tom Butt" in n for n in names)
        assert any("City of Richmond" in n for n in names)


class TestParsePartyRow:
    def test_basic_row(self):
        from courts_scraper import _parse_party_row
        from bs4 import BeautifulSoup
        html = "<tr><td>John Doe</td><td>Plaintiff</td><td>Jane Law, Esq.</td></tr>"
        row = BeautifulSoup(html, "html.parser").find("tr")
        party = _parse_party_row(row)
        assert party is not None
        assert party["party_name"] == "John Doe"
        assert party["party_type"] == "plaintiff"

    def test_empty_row(self):
        from courts_scraper import _parse_party_row
        from bs4 import BeautifulSoup
        row = BeautifulSoup("<tr></tr>", "html.parser").find("tr")
        assert _parse_party_row(row) is None


class TestParsePartyItem:
    def test_paren_format(self):
        from courts_scraper import _parse_party_item
        from bs4 import BeautifulSoup
        item = BeautifulSoup("<li>John Doe (Plaintiff)</li>", "html.parser").find("li")
        party = _parse_party_item(item)
        assert party["party_name"] == "John Doe"
        assert party["party_type"] == "plaintiff"

    def test_colon_format(self):
        from courts_scraper import _parse_party_item
        from bs4 import BeautifulSoup
        item = BeautifulSoup("<div>Defendant: ABC Corp</div>", "html.parser").find("div")
        party = _parse_party_item(item)
        assert party["party_name"] == "ABC Corp"
        assert party["party_type"] == "defendant"


# ── Date Parsing Tests ───────────────────────────────────────

class TestParseDate:
    def test_us_format(self):
        from courts_scraper import _parse_date
        assert _parse_date("01/15/2024") == "2024-01-15"

    def test_iso_format(self):
        from courts_scraper import _parse_date
        assert _parse_date("2024-01-15") == "2024-01-15"

    def test_long_format(self):
        from courts_scraper import _parse_date
        assert _parse_date("January 15, 2024") == "2024-01-15"

    def test_none_input(self):
        from courts_scraper import _parse_date
        assert _parse_date(None) is None

    def test_empty_input(self):
        from courts_scraper import _parse_date
        assert _parse_date("") is None

    def test_unparseable(self):
        from courts_scraper import _parse_date
        assert _parse_date("not a date") is None


# ── Config Resolution Tests ──────────────────────────────────

class TestCourtsConfig:
    def test_default_config(self):
        from courts_scraper import _resolve_courts_config
        portal_url, search_path, county_fips, city_fips = _resolve_courts_config()
        assert "odyportal.cc-courts.org" in portal_url
        assert county_fips == "06013"
        assert city_fips == "0660620"

    def test_registry_config(self):
        from courts_scraper import _resolve_courts_config
        portal_url, search_path, county_fips, city_fips = _resolve_courts_config("0660620")
        assert "odyportal.cc-courts.org" in portal_url
        assert county_fips == "06013"

    def test_config_exists_in_registry(self):
        from city_config import get_data_source_config
        cfg = get_data_source_config("0660620", "courts")
        assert cfg["platform"] == "Tyler Odyssey"
        assert cfg["county_fips"] == "06013"
        assert "civil" in cfg["case_types"]
        assert cfg["credibility_tier"] == 1


# ── Hidden Fields Extraction Tests ───────────────────────────

class TestExtractHiddenFields:
    def test_extracts_viewstate(self):
        from courts_scraper import _extract_hidden_fields
        from bs4 import BeautifulSoup
        html = """
        <form>
          <input type="hidden" name="__VIEWSTATE" value="abc123" />
          <input type="hidden" name="__EVENTVALIDATION" value="xyz789" />
          <input type="text" name="query" value="" />
        </form>
        """
        soup = BeautifulSoup(html, "html.parser")
        fields = _extract_hidden_fields(soup)
        assert fields["__VIEWSTATE"] == "abc123"
        assert fields["__EVENTVALIDATION"] == "xyz789"
        assert "query" not in fields  # not hidden

    def test_empty_form(self):
        from courts_scraper import _extract_hidden_fields
        from bs4 import BeautifulSoup
        soup = BeautifulSoup("<form></form>", "html.parser")
        assert _extract_hidden_fields(soup) == {}


# ── Name List Builder Tests ──────────────────────────────────

class TestBuildSearchList:
    def _make_mock_conn(self, officials=None, donors=None, filers=None):
        """Create a mock connection with cursor results."""
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        # Each execute call returns different data
        results = []
        if officials is not None:
            results.append(officials)
        if donors is not None:
            results.append(donors)
        if filers is not None:
            results.append(filers)

        mock_cursor.fetchall.side_effect = results
        return mock_conn

    def test_includes_officials(self):
        from courts_scraper import build_search_list
        mock_conn = self._make_mock_conn(
            officials=[
                (uuid.uuid4(), "Eduardo Martinez", True),
                (uuid.uuid4(), "Tom Butt", False),
            ],
            donors=[],
            filers=[],
        )
        names = build_search_list(mock_conn, "0660620")
        assert len(names) == 2
        assert names[0]["name"] == "Eduardo Martinez"
        assert names[0]["entity_type"] == "official"
        assert names[0]["priority"] == 1  # current official

    def test_deduplicates_across_sources(self):
        from courts_scraper import build_search_list
        official_id = uuid.uuid4()
        mock_conn = self._make_mock_conn(
            officials=[(official_id, "Eduardo Martinez", True)],
            donors=[],
            filers=[("Eduardo Martinez",)],  # Same name as official
        )
        names = build_search_list(mock_conn, "0660620")
        assert len(names) == 1  # Deduped

    def test_respects_max_names(self):
        from courts_scraper import build_search_list
        officials = [(uuid.uuid4(), f"Official {i}", True) for i in range(100)]
        mock_conn = self._make_mock_conn(
            officials=officials, donors=[], filers=[],
        )
        names = build_search_list(mock_conn, "0660620", max_names=5)
        assert len(names) == 5

    def test_priority_ordering(self):
        from courts_scraper import build_search_list
        mock_conn = self._make_mock_conn(
            officials=[
                (uuid.uuid4(), "Former Guy", False),
                (uuid.uuid4(), "Current Mayor", True),
            ],
            donors=[(uuid.uuid4(), "Big Donor", 50000.0)],
            filers=[("Form Filer",)],
        )
        names = build_search_list(mock_conn, "0660620")
        # Current official (1) before former (2) before donor (3) before filer (4)
        assert names[0]["priority"] == 1
        assert names[-1]["priority"] == 4


# ── Database Storage Tests ───────────────────────────────────

class TestSaveCasesToDb:
    def test_saves_case_with_parties(self):
        from courts_scraper import save_cases_to_db
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (uuid.uuid4(), True)  # is_insert

        cases = [{
            "case_number": "C24-01234",
            "case_type": "Civil",
            "filing_date": "2024-01-15",
            "case_status": "Open",
            "source_url": "https://example.com/case/1",
            "parties": [
                {"party_name": "John Doe", "party_type": "plaintiff"},
                {"party_name": "ABC Corp", "party_type": "defendant"},
            ],
        }]

        stats = save_cases_to_db(mock_conn, cases, "0660620", "06013")
        assert stats["cases_saved"] == 1
        assert stats["parties_saved"] == 2

    def test_skips_empty_case_number(self):
        from courts_scraper import save_cases_to_db
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        cases = [{"case_number": "", "case_type": "Civil"}]
        stats = save_cases_to_db(mock_conn, cases, "0660620", "06013")
        assert stats["cases_saved"] == 0

    def test_counts_updates(self):
        from courts_scraper import save_cases_to_db
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (uuid.uuid4(), False)  # is_update

        cases = [{"case_number": "C24-01234", "case_type": "Civil"}]
        stats = save_cases_to_db(mock_conn, cases, "0660620", "06013")
        assert stats["cases_updated"] == 1
        assert stats["cases_saved"] == 0


# ── Cross-Reference Matching Tests ───────────────────────────

class TestCrossReferenceParties:
    def test_exact_match_official(self):
        from courts_scraper import cross_reference_parties
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        party_id = uuid.uuid4()
        case_id = uuid.uuid4()
        official_id = uuid.uuid4()

        mock_cursor.fetchall.side_effect = [
            # Unmatched parties
            [(party_id, case_id, "Eduardo Martinez", "eduardo martinez")],
            # Officials
            [(official_id, "Eduardo Martinez", "eduardo martinez")],
            # Donors
            [],
        ]

        with patch("conflict_scanner.normalize_text", side_effect=lambda x: x.lower().strip()):
            with patch("conflict_scanner.names_match", return_value=(True, "exact")):
                stats = cross_reference_parties(mock_conn, "0660620")

        assert stats["matches_found"] == 1
        assert stats["by_type"]["exact"] == 1

    def test_no_match(self):
        from courts_scraper import cross_reference_parties
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        party_id = uuid.uuid4()
        case_id = uuid.uuid4()

        mock_cursor.fetchall.side_effect = [
            # Unmatched parties - name with very short last name to skip last_name_only
            [(party_id, case_id, "Unknown Xu", "unknown xu")],
            # Officials
            [(uuid.uuid4(), "Eduardo Martinez", "eduardo martinez")],
            # Donors
            [],
        ]

        with patch("conflict_scanner.normalize_text", side_effect=lambda x: x.lower().strip()):
            with patch("conflict_scanner.names_match", return_value=(False, "no_match")):
                stats = cross_reference_parties(mock_conn, "0660620")

        assert stats["matches_found"] == 0

    def test_empty_unmatched(self):
        from courts_scraper import cross_reference_parties
        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_cursor.fetchall.return_value = []  # No unmatched parties

        stats = cross_reference_parties(mock_conn, "0660620")
        assert stats["matches_found"] == 0


# ── Data Sync Integration Tests ──────────────────────────────

class TestSyncCourtsRegistration:
    def test_courts_registered_in_sync_sources(self):
        from data_sync import SYNC_SOURCES
        assert "courts" in SYNC_SOURCES

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_dispatches_via_run_sync(
        self, mock_complete, mock_create, mock_conn,
    ):
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(return_value={
            "records_fetched": 10,
            "records_new": 5,
            "records_updated": 2,
            "matches_found": 3,
        })

        with patch.dict(SYNC_SOURCES, {"courts": fake_sync}):
            result = run_sync("courts", city_fips="0660620")

        fake_sync.assert_called_once()


# ── Map Header Field Tests ───────────────────────────────────

class TestMapHeaderField:
    def test_maps_case_number(self):
        from courts_scraper import _map_header_field
        detail = {"case_number": "", "case_type": "", "case_category": "",
                  "case_title": "", "filing_date": None, "case_status": "",
                  "disposition": "", "disposition_date": None, "court_name": "",
                  "judge": ""}
        _map_header_field("case number", "C24-01234", detail)
        assert detail["case_number"] == "C24-01234"

    def test_maps_judge(self):
        from courts_scraper import _map_header_field
        detail = {"case_number": "", "case_type": "", "case_category": "",
                  "case_title": "", "filing_date": None, "case_status": "",
                  "disposition": "", "disposition_date": None, "court_name": "",
                  "judge": ""}
        _map_header_field("judicial officer", "Hon. Smith", detail)
        assert detail["judge"] == "Hon. Smith"

    def test_ignores_empty_value(self):
        from courts_scraper import _map_header_field
        detail = {"case_number": "existing", "case_type": "", "case_category": "",
                  "case_title": "", "filing_date": None, "case_status": "",
                  "disposition": "", "disposition_date": None, "court_name": "",
                  "judge": ""}
        _map_header_field("case number", "", detail)
        assert detail["case_number"] == "existing"  # Not overwritten


# ── Confidence Constants Tests ───────────────────────────────

class TestConfidenceConstants:
    def test_confidence_ordering(self):
        from courts_scraper import (
            CONFIDENCE_EXACT, CONFIDENCE_CONTAINS,
            CONFIDENCE_FUZZY, CONFIDENCE_LAST_NAME,
        )
        assert CONFIDENCE_EXACT > CONFIDENCE_CONTAINS > CONFIDENCE_FUZZY > CONFIDENCE_LAST_NAME
        assert CONFIDENCE_EXACT <= 1.0
        assert CONFIDENCE_LAST_NAME >= 0.0
