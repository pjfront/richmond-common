# tests/test_form700_sync_scanner.py
"""Tests for Form 700 sync integration and conflict scanner DB mode enhancements.

Tests cover:
- sync_form700() registration in SYNC_SOURCES
- sync_form700() dispatch through run_sync()
- sync_form700() incremental filtering (skip existing filings)
- sync_form700() error handling (individual filing failures don't stop batch)
- Conflict scanner DB mode: real property with filing period join
- Conflict scanner DB mode: income/investment cross-referencing
- Conflict scanner DB mode: source URL in evidence
"""
import json
import sys
import uuid
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))


# ── SYNC_SOURCES Registry ──────────────────────────────────────

class TestForm700Registry:
    """Verify form700 is properly registered in SYNC_SOURCES."""

    def test_form700_registered(self):
        from data_sync import SYNC_SOURCES
        assert "form700" in SYNC_SOURCES

    def test_form700_is_callable(self):
        from data_sync import SYNC_SOURCES
        assert callable(SYNC_SOURCES["form700"])

    def test_all_sources_still_registered(self):
        """Adding form700 didn't accidentally remove other sources."""
        from data_sync import SYNC_SOURCES
        expected = {"netfile", "calaccess", "escribemeetings", "nextrequest", "archive_center", "form700", "minutes_extraction", "socrata_payroll", "socrata_expenditures", "socrata_permits", "socrata_licenses", "socrata_code_cases", "socrata_service_requests", "socrata_projects", "courts", "propublica"}
        assert set(SYNC_SOURCES.keys()) == expected


# ── run_sync dispatch for form700 ──────────────────────────────

class TestForm700Dispatch:
    """Test form700 dispatch through run_sync orchestrator."""

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_form700_dispatches(
        self, mock_complete, mock_create, mock_conn,
    ):
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(return_value={
            "records_fetched": 15, "records_new": 12, "records_updated": 0,
            "filings_discovered": 15, "interests_loaded": 45, "errors": 3,
        })

        with patch.dict(SYNC_SOURCES, {"form700": fake_sync}):
            result = run_sync(source="form700")

        fake_sync.assert_called_once()
        assert result["status"] == "completed"
        assert result["records_fetched"] == 15
        assert result["records_new"] == 12

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_form700_failure_returns_error(
        self, mock_complete, mock_create, mock_conn,
    ):
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(side_effect=RuntimeError("NetFile portal down"))

        with patch.dict(SYNC_SOURCES, {"form700": fake_sync}):
            result = run_sync(source="form700")

        assert result["status"] == "failed"
        assert "NetFile portal down" in result["error"]

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_form700_extra_fields_in_result(
        self, mock_complete, mock_create, mock_conn,
    ):
        """Form 700 sync returns extra fields (filings_discovered, interests_loaded)."""
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(return_value={
            "records_fetched": 10, "records_new": 8, "records_updated": 0,
            "filings_discovered": 10, "interests_loaded": 32, "errors": 2,
        })

        with patch.dict(SYNC_SOURCES, {"form700": fake_sync}):
            result = run_sync(source="form700")

        assert result["filings_discovered"] == 10
        assert result["interests_loaded"] == 32
        assert result["errors"] == 2


# ── sync_form700 direct tests ─────────────────────────────────
#
# sync_form700 uses lazy imports (from form700_scraper import ...)
# inside the function body. Patch at source module level using
# @patch decorators to ensure patches are active when imports run.

class TestSyncForm700:
    """Test the sync_form700 function directly with mocked dependencies."""

    @patch("db.load_form700_to_db")
    @patch("form700_extractor.extract_form700")
    @patch("form700_extractor.extract_text_from_pdf")
    @patch("db.ingest_document")
    @patch("form700_scraper.download_filing_pdf")
    @patch("asyncio.run")
    def test_full_sync_processes_all_filings(
        self, mock_asyncio, mock_download, mock_ingest,
        mock_extract_text, mock_extract, mock_load,
    ):
        """Full sync processes all discovered filings."""
        from data_sync import sync_form700

        discovered = [
            {"filer_name": "Eduardo Martinez", "filing_year": 2024,
             "statement_type": "annual", "detail_url": "https://example.com/1.pdf",
             "department": "City Council"},
        ]
        # asyncio.run is called twice: once for _discover(), once for download_filing_pdf()
        mock_asyncio.side_effect = [discovered, "/tmp/test.pdf"]
        mock_ingest.return_value = uuid.uuid4()
        mock_extract_text.return_value = "STATEMENT OF ECONOMIC INTERESTS..."
        mock_extract.return_value = {
            "filer_name": "Eduardo Martinez",
            "interests": [{"schedule": "B", "interest_type": "real_property"}],
            "extraction_confidence": 0.9,
        }
        mock_load.return_value = {
            "filing_id": str(uuid.uuid4()),
            "official_id": str(uuid.uuid4()),
            "interests_count": 1,
            "matched_official": True,
            "filer_name": "Eduardo Martinez",
        }

        conn = MagicMock()
        result = sync_form700(conn, "0660620", "full")

        assert result["records_fetched"] == 1
        assert result["records_new"] == 1
        assert result["interests_loaded"] == 1
        assert result["errors"] == 0
        mock_download.assert_called_once()
        mock_extract.assert_called_once()
        mock_load.assert_called_once()

    @patch("db.load_form700_to_db")
    @patch("form700_extractor.extract_form700")
    @patch("form700_extractor.extract_text_from_pdf")
    @patch("db.ingest_document")
    @patch("form700_scraper.download_filing_pdf")
    @patch("asyncio.run")
    def test_incremental_skips_existing(
        self, mock_asyncio, mock_download, mock_ingest,
        mock_extract_text, mock_extract, mock_load,
    ):
        """Incremental sync skips filings already in form700_filings table."""
        from data_sync import sync_form700

        discovered = [
            {"filer_name": "Eduardo Martinez", "filing_year": 2024,
             "statement_type": "annual", "detail_url": "https://example.com/1.pdf"},
            {"filer_name": "Sue Wilson", "filing_year": 2024,
             "statement_type": "annual", "detail_url": "https://example.com/2.pdf"},
            {"filer_name": "Cesar Zepeda", "filing_year": 2024,
             "statement_type": "annual", "detail_url": "https://example.com/3.pdf"},
        ]
        # asyncio.run called twice: discover, then download for the 1 new filing
        mock_asyncio.side_effect = [discovered, "/tmp/test.pdf"]

        # 2 existing filings in DB
        existing = [
            ("Eduardo Martinez", 2024, "annual", "netfile_sei"),
            ("Sue Wilson", 2024, "annual", "netfile_sei"),
        ]

        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = existing
        cursor.__enter__ = lambda self: cursor
        cursor.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor

        mock_download.return_value = "/tmp/test.pdf"
        mock_ingest.return_value = uuid.uuid4()
        mock_extract_text.return_value = "Form 700 text..."
        mock_extract.return_value = {
            "filer_name": "Cesar Zepeda",
            "interests": [],
            "extraction_confidence": 0.9,
        }
        mock_load.return_value = {
            "filing_id": str(uuid.uuid4()),
            "official_id": str(uuid.uuid4()),
            "interests_count": 0,
            "matched_official": True,
            "filer_name": "Cesar Zepeda",
        }

        result = sync_form700(conn, "0660620", "incremental")

        # Should only process 1 new filing (Zepeda)
        assert result["records_new"] == 1
        assert mock_download.call_count == 1

    @patch("db.load_form700_to_db")
    @patch("form700_extractor.extract_form700")
    @patch("form700_extractor.extract_text_from_pdf")
    @patch("db.ingest_document")
    @patch("form700_scraper.download_filing_pdf")
    @patch("asyncio.run")
    def test_download_failure_increments_errors(
        self, mock_asyncio, mock_download, mock_ingest,
        mock_extract_text, mock_extract, mock_load,
    ):
        """Download failure for one filing doesn't stop the batch."""
        from data_sync import sync_form700

        discovered = [
            {"filer_name": "Eduardo Martinez", "filing_year": 2024,
             "statement_type": "annual", "detail_url": "https://example.com/1.pdf"},
            {"filer_name": "Sue Wilson", "filing_year": 2024,
             "statement_type": "annual", "detail_url": "https://example.com/2.pdf"},
        ]
        # asyncio.run called 3x: discover, download#1 (fail), download#2 (success)
        mock_asyncio.side_effect = [discovered, None, "/tmp/test.pdf"]
        mock_ingest.return_value = uuid.uuid4()
        mock_extract_text.return_value = "Form 700 text..."
        mock_extract.return_value = {
            "filer_name": "Sue Wilson",
            "interests": [{"schedule": "B", "interest_type": "real_property",
                          "description": "123 Main St"}],
            "extraction_confidence": 0.85,
        }
        mock_load.return_value = {
            "filing_id": str(uuid.uuid4()),
            "official_id": str(uuid.uuid4()),
            "interests_count": 1,
            "matched_official": True,
            "filer_name": "Sue Wilson",
        }

        conn = MagicMock()
        result = sync_form700(conn, "0660620", "full")

        assert result["records_new"] == 1
        assert result["errors"] == 1

    @patch("form700_extractor.extract_text_from_pdf")
    @patch("db.ingest_document")
    @patch("form700_scraper.download_filing_pdf")
    @patch("asyncio.run")
    def test_empty_pdf_text_skipped(
        self, mock_asyncio, mock_download, mock_ingest, mock_extract_text,
    ):
        """Filing with empty PDF text (scanned, no OCR) is skipped."""
        from data_sync import sync_form700

        discovered = [
            {"filer_name": "Eduardo Martinez", "filing_year": 2024,
             "statement_type": "annual", "detail_url": "https://example.com/1.pdf"},
        ]
        # asyncio.run called twice: discover, then download
        mock_asyncio.side_effect = [discovered, "/tmp/test.pdf"]
        mock_ingest.return_value = uuid.uuid4()
        mock_extract_text.return_value = "   "  # Empty after strip

        conn = MagicMock()
        result = sync_form700(conn, "0660620", "full")

        assert result["records_new"] == 0
        assert result["errors"] == 1

    @patch("asyncio.run")
    def test_no_detail_url_skipped(self, mock_asyncio):
        """Filing without detail_url is skipped."""
        from data_sync import sync_form700

        discovered = [
            {"filer_name": "Eduardo Martinez", "filing_year": 2024,
             "statement_type": "annual", "detail_url": ""},
        ]
        mock_asyncio.return_value = discovered

        conn = MagicMock()
        result = sync_form700(conn, "0660620", "full")

        assert result["records_new"] == 0
        assert result["errors"] == 1

    @patch("db.load_form700_to_db")
    @patch("form700_extractor.extract_form700")
    @patch("form700_extractor.extract_text_from_pdf")
    @patch("db.ingest_document")
    @patch("form700_scraper.download_filing_pdf")
    @patch("asyncio.run")
    def test_extraction_error_increments_errors(
        self, mock_asyncio, mock_download, mock_ingest,
        mock_extract_text, mock_extract, mock_load,
    ):
        """Claude API extraction error for one filing doesn't stop batch."""
        from data_sync import sync_form700

        discovered = [
            {"filer_name": "Eduardo Martinez", "filing_year": 2024,
             "statement_type": "annual", "detail_url": "https://example.com/1.pdf"},
        ]
        # asyncio.run called twice: discover, then download
        mock_asyncio.side_effect = [discovered, "/tmp/test.pdf"]
        mock_ingest.return_value = uuid.uuid4()
        mock_extract_text.return_value = "Form 700 text..."
        mock_extract.side_effect = RuntimeError("API error")

        conn = MagicMock()
        result = sync_form700(conn, "0660620", "full")

        assert result["records_new"] == 0
        assert result["errors"] == 1

    @patch("asyncio.run")
    def test_empty_discovery_returns_zeros(self, mock_asyncio):
        """No filings discovered returns zero counts."""
        from data_sync import sync_form700

        mock_asyncio.return_value = []
        conn = MagicMock()
        result = sync_form700(conn, "0660620", "full")

        assert result["records_fetched"] == 0
        assert result["records_new"] == 0
        assert result["filings_discovered"] == 0


# ── Conflict Scanner DB Mode: Form 700 Enhancements ───────────
#
# scan_meeting_db calls extract_entity_names() (NLP) to find entity
# names, then queries the DB for each. To make tests deterministic,
# we mock extract_entity_names to control the entity list and thus
# the exact cursor query sequence.

class TestScannerDbForm700:
    """Test the enhanced Form 700 cross-referencing in scan_meeting_db.

    scan_meeting_db now delegates to scan_meeting_json via four fetch
    functions. Tests patch _fetch_meeting_data_from_db,
    _fetch_contributions_from_db, _fetch_form700_interests_from_db,
    and _fetch_expenditures_from_db to provide controlled test data.

    These tests verify:
    1. Real property interests are flagged for land-use agenda items
    2. Income/investment cross-referencing matches entity names
    3. Filing period context appears in descriptions
    4. Filing source URL appears in evidence
    """

    def _make_meeting_data(self, meeting_date, meeting_type, items, members_present=None):
        """Build meeting_data dict matching _fetch_meeting_data_from_db output."""
        if members_present is None:
            members_present = []
        action_items = []
        consent_items = []
        for item in items:
            item_dict = {
                "item_number": item[1],
                "title": item[2],
                "description": item[3] or "",
                "financial_amount": item[5] or "",
            }
            if item[6]:  # is_consent
                consent_items.append(item_dict)
            else:
                action_items.append(item_dict)
        return {
            "meeting_date": str(meeting_date),
            "meeting_type": meeting_type,
            "members_present": [{"name": n} for n in members_present],
            "consent_calendar": {"items": consent_items},
            "action_items": action_items,
            "housing_authority_items": [],
        }

    def _make_form700_interests(self, interests):
        """Convert old-format tuples to form700_interests dicts.

        Old format: (official_name, description, filing_year, location,
                     period_start, period_end, source_url)
        or for income: (official_name, interest_type, description,
                       filing_year, period_start, period_end, source_url)
        """
        result = []
        for row in interests:
            if len(row) == 7 and isinstance(row[1], str) and row[1] in (
                "income", "investment", "business_position",
            ):
                result.append({
                    "council_member": row[0],
                    "interest_type": row[1],
                    "description": row[2] or "",
                    "filing_year": row[3],
                    "location": "",
                    "source_url": row[6] or "",
                })
            else:
                result.append({
                    "council_member": row[0],
                    "interest_type": "real_property",
                    "description": row[1] or "",
                    "filing_year": row[2],
                    "location": row[3] or "",
                    "source_url": row[6] or "",
                })
        return result

    def test_real_property_flag_includes_filing_period(self):
        """Real property flag includes filing_year in description."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        items = [
            (str(uuid.uuid4()), "H-1", "Rezoning Application for 123 Main Street",
             "Request to rezone from residential to commercial", "Zoning",
             "$0", False),
        ]
        meeting_data = self._make_meeting_data(date(2026, 3, 1), "Regular Meeting", items)

        form700 = self._make_form700_interests([
            ("Sue Wilson", "123 Main St, Richmond CA 94804", 2024,
             "Richmond, CA", date(2024, 1, 1), date(2024, 12, 31),
             "https://netfile.com/filing/123"),
        ])

        conn = MagicMock()
        with patch("conflict_scanner._fetch_meeting_data_from_db", return_value=meeting_data), \
             patch("conflict_scanner._fetch_contributions_from_db", return_value=[]), \
             patch("conflict_scanner._fetch_form700_interests_from_db", return_value=form700), \
             patch("conflict_scanner._fetch_expenditures_from_db", return_value=[]):
            result = scan_meeting_db(conn, meeting_id, "0660620")

        rp_flags = [f for f in result.flags if f.flag_type == "form700_real_property"]
        assert len(rp_flags) >= 1

        flag = rp_flags[0]
        assert flag.council_member == "Sue Wilson"
        assert "2024" in flag.description
        assert 0.3 < flag.confidence < 0.6  # v3 composite; test focus is filing period metadata

    def test_real_property_flag_without_filing_period(self):
        """Real property flag works even without filing period data."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        items = [
            (str(uuid.uuid4()), "H-1", "Variance for 456 Oak Ave Development",
             "Request for height variance", "Planning",
             None, False),
        ]
        meeting_data = self._make_meeting_data(date(2026, 3, 1), "Regular Meeting", items)

        # No source_url provided — should fall back to 'FPPC' default
        form700 = [{
            "council_member": "Eduardo Martinez",
            "interest_type": "real_property",
            "description": "456 Oak Ave, Richmond",
            "filing_year": 2023,
            "location": "Richmond, CA",
        }]

        conn = MagicMock()
        with patch("conflict_scanner._fetch_meeting_data_from_db", return_value=meeting_data), \
             patch("conflict_scanner._fetch_contributions_from_db", return_value=[]), \
             patch("conflict_scanner._fetch_form700_interests_from_db", return_value=form700), \
             patch("conflict_scanner._fetch_expenditures_from_db", return_value=[]):
            result = scan_meeting_db(conn, meeting_id, "0660620")

        rp_flags = [f for f in result.flags if f.flag_type == "form700_real_property"]
        assert len(rp_flags) >= 1

        flag = rp_flags[0]
        assert flag.council_member == "Eduardo Martinez"
        assert "FPPC" in flag.evidence[1]

    def test_income_investment_cross_reference(self):
        """Income/investment interests match entity names in agenda items.

        The entity name must be extractable by extract_entity_names()
        from the agenda text. Using "contract with X Inc." pattern
        ensures reliable extraction. The Form 700 description must then
        match via names_match() (requires >= 10 chars and shared words).
        """
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        # Use "contract with" pattern so extract_entity_names can find the entity
        items = [
            (str(uuid.uuid4()), "I-1",
             "Contract with Chevron Corporation for Refinery Modernization",
             "Environmental review for facility upgrades", "Environment",
             "$500,000", False),
        ]
        meeting_data = self._make_meeting_data(date(2026, 3, 1), "Regular Meeting", items)

        form700 = self._make_form700_interests([
            ("Soheila Bana", "income", "Chevron Corporation",
             2024, date(2024, 1, 1), date(2024, 12, 31),
             "https://netfile.com/filing/456"),
        ])

        conn = MagicMock()
        with patch("conflict_scanner._fetch_meeting_data_from_db", return_value=meeting_data), \
             patch("conflict_scanner._fetch_contributions_from_db", return_value=[]), \
             patch("conflict_scanner._fetch_form700_interests_from_db", return_value=form700), \
             patch("conflict_scanner._fetch_expenditures_from_db", return_value=[]):
            result = scan_meeting_db(conn, meeting_id, "0660620")

        income_flags = [f for f in result.flags if f.flag_type == "form700_income"]
        assert len(income_flags) >= 1

        flag = income_flags[0]
        assert flag.council_member == "Soheila Bana"
        assert "income" in flag.description.lower()
        assert "Chevron" in flag.description
        assert flag.confidence >= 0.5  # v3 composite with strong entity match

    def test_no_flags_for_non_land_use_items(self):
        """Non-land-use agenda items don't trigger real property checks."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        items = [
            (str(uuid.uuid4()), "C-1", "Approve Minutes of Previous Meeting",
             "Consent calendar item", "Consent",
             None, True),
        ]
        meeting_data = self._make_meeting_data(date(2026, 3, 1), "Regular Meeting", items)

        # Even with real property interests, non-land-use items shouldn't flag
        form700 = self._make_form700_interests([
            ("Sue Wilson", "123 Main St", 2024, "Richmond, CA", None, None, None),
        ])

        conn = MagicMock()
        with patch("conflict_scanner._fetch_meeting_data_from_db", return_value=meeting_data), \
             patch("conflict_scanner._fetch_contributions_from_db", return_value=[]), \
             patch("conflict_scanner._fetch_form700_interests_from_db", return_value=form700), \
             patch("conflict_scanner._fetch_expenditures_from_db", return_value=[]):
            result = scan_meeting_db(conn, meeting_id, "0660620")

        rp_flags_1 = [f for f in result.flags if f.flag_type == "form700_real_property"]
        assert len(rp_flags_1) == 0

    def test_form700_flags_include_source_url(self):
        """Form 700 flags include the filing source URL in evidence."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        items = [
            (str(uuid.uuid4()), "H-1", "General Plan Amendment - Rezoning 500 Harbour Way",
             "Rezone 500 Harbour Way from residential to commercial", "Planning",
             None, False),
        ]
        meeting_data = self._make_meeting_data(date(2026, 3, 1), "Regular Meeting", items)

        form700 = self._make_form700_interests([
            ("Jamelia Brown", "500 Harbour Way, Richmond", 2024,
             "Richmond, CA", date(2024, 1, 1), date(2024, 12, 31),
             "https://public.netfile.com/pub/?AID=RICH&filing=789"),
        ])

        conn = MagicMock()
        with patch("conflict_scanner._fetch_meeting_data_from_db", return_value=meeting_data), \
             patch("conflict_scanner._fetch_contributions_from_db", return_value=[]), \
             patch("conflict_scanner._fetch_form700_interests_from_db", return_value=form700), \
             patch("conflict_scanner._fetch_expenditures_from_db", return_value=[]):
            result = scan_meeting_db(conn, meeting_id, "0660620")

        rp_flags = [f for f in result.flags if f.flag_type == "form700_real_property"]
        assert len(rp_flags) >= 1

        evidence_text = " ".join(rp_flags[0].evidence)
        assert "netfile.com" in evidence_text or "FPPC" in evidence_text

    def test_real_property_legal_reference(self):
        """Real property flags cite the correct legal reference."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        items = [
            (str(uuid.uuid4()), "H-1", "Zoning Variance Application at 220 Barrett Ave",
             "Height variance request for 220 Barrett Ave", "Planning",
             None, False),
        ]
        meeting_data = self._make_meeting_data(date(2026, 3, 1), "Regular Meeting", items)

        form700 = self._make_form700_interests([
            ("Claudia Jimenez", "220 Barrett Ave, Richmond", 2024,
             "Richmond, CA", None, None, None),
        ])

        conn = MagicMock()
        with patch("conflict_scanner._fetch_meeting_data_from_db", return_value=meeting_data), \
             patch("conflict_scanner._fetch_contributions_from_db", return_value=[]), \
             patch("conflict_scanner._fetch_form700_interests_from_db", return_value=form700), \
             patch("conflict_scanner._fetch_expenditures_from_db", return_value=[]):
            result = scan_meeting_db(conn, meeting_id, "0660620")

        rp_flags = [f for f in result.flags if f.flag_type == "form700_real_property"]
        assert len(rp_flags) >= 1
        assert "87100" in rp_flags[0].legal_reference
        assert "18702.2" in rp_flags[0].legal_reference
        assert "500 feet" in rp_flags[0].legal_reference

    def test_investment_flag_type(self):
        """Investment interests produce form700_investment flag type.

        Entity name must be >= 10 chars normalized for names_match substring
        matching (e.g., "acme development" = 16 chars). Short names like
        "acme corp" (9 chars) fall below the threshold.
        """
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        items = [
            (str(uuid.uuid4()), "F-1", "Contract with Acme Development for services",
             "Professional services agreement", "Finance",
             "$50,000", False),
        ]
        meeting_data = self._make_meeting_data(date(2026, 3, 1), "Regular Meeting", items)

        form700 = self._make_form700_interests([
            ("Eduardo Martinez", "investment", "Acme Development - stock holdings",
             2024, date(2024, 1, 1), date(2024, 12, 31),
             "https://netfile.com/filing/999"),
        ])

        conn = MagicMock()
        with patch("conflict_scanner._fetch_meeting_data_from_db", return_value=meeting_data), \
             patch("conflict_scanner._fetch_contributions_from_db", return_value=[]), \
             patch("conflict_scanner._fetch_form700_interests_from_db", return_value=form700), \
             patch("conflict_scanner._fetch_expenditures_from_db", return_value=[]):
            result = scan_meeting_db(conn, meeting_id, "0660620")

        inv_flags = [f for f in result.flags if f.flag_type == "form700_investment"]
        assert len(inv_flags) >= 1
        assert inv_flags[0].council_member == "Eduardo Martinez"

    def test_meeting_not_found_raises(self):
        """scan_meeting_db raises ValueError for unknown meeting ID."""
        from conflict_scanner import scan_meeting_db

        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone = MagicMock(return_value=None)
        cursor.__enter__ = lambda self: cursor
        cursor.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor

        with pytest.raises(ValueError, match="not found"):
            scan_meeting_db(conn, str(uuid.uuid4()), "0660620")

    def test_appointment_item_skips_real_property(self):
        """Items with both zoning and appointment keywords skip real property check."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        items = [
            (str(uuid.uuid4()), "J-1",
             "Appointment to Planning Commission - Zoning Committee",
             "Reappointment of commissioner", "Appointments",
             None, False),
        ]
        meeting_data = self._make_meeting_data(date(2026, 3, 1), "Regular Meeting", items)

        form700 = self._make_form700_interests([
            ("Sue Wilson", "123 Main St", 2024, "Richmond, CA", None, None, None),
        ])

        conn = MagicMock()
        with patch("conflict_scanner._fetch_meeting_data_from_db", return_value=meeting_data), \
             patch("conflict_scanner._fetch_contributions_from_db", return_value=[]), \
             patch("conflict_scanner._fetch_form700_interests_from_db", return_value=form700), \
             patch("conflict_scanner._fetch_expenditures_from_db", return_value=[]):
            result = scan_meeting_db(conn, meeting_id, "0660620")

        rp_flags = [f for f in result.flags if f.flag_type == "form700_real_property"]
        assert len(rp_flags) == 0


# ── S9.4: DB Mode Expenditure Parity ──────────────────────────
#
# Tests that scan_meeting_db fetches expenditures and passes them
# through to scan_meeting_json, enabling the donor-vendor-expenditure
# signal detector in DB mode.

class TestScannerDbExpenditures:
    """Test expenditure fetch and donor-vendor signal in DB mode."""

    def _make_meeting_data(self, items, members_present=None):
        """Build meeting_data dict matching _fetch_meeting_data_from_db output."""
        if members_present is None:
            members_present = ["Eduardo Martinez"]
        action_items = []
        for item in items:
            item_id, num, title, desc, category, *rest = item
            financial = rest[0] if rest else None
            action_items.append({
                "id": item_id,
                "item_number": num,
                "title": title,
                "description": desc or "",
                "category": category or "",
                "financial_amount": financial,
            })
        return {
            "meeting_date": "2026-01-15",
            "meeting_type": "regular",
            "members_present": [{"name": n} for n in members_present],
            "action_items": action_items,
            "consent_calendar": {"items": []},
            "housing_authority_items": [],
        }

    def test_expenditures_passed_to_json_scanner(self):
        """scan_meeting_db passes expenditures to scan_meeting_json."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        items = [
            (str(uuid.uuid4()), "H-1",
             "Approve contract with Acme Construction for road repair",
             "Professional services agreement with Acme Construction",
             "Public Works", "$150,000"),
        ]
        meeting_data = self._make_meeting_data(items)

        contributions = [
            {
                "donor_name": "Acme Construction",
                "donor_employer": "",
                "council_member": "Eduardo Martinez",
                "committee_name": "Martinez for Richmond 2026",
                "amount": 5000,
                "date": "2025-11-01",
                "filing_id": "FILE-001",
                "source": "netfile",
            },
        ]
        expenditures = [
            {
                "vendor_name": "Acme Construction",
                "normalized_vendor": "Acme Construction",
                "amount": 150000.0,
                "fiscal_year": "2025-2026",
                "department": "Public Works",
                "expenditure_date": "2025-12-01",
            },
        ]

        conn = MagicMock()
        with patch("conflict_scanner._fetch_meeting_data_from_db", return_value=meeting_data), \
             patch("conflict_scanner._fetch_contributions_from_db", return_value=contributions), \
             patch("conflict_scanner._fetch_form700_interests_from_db", return_value=[]), \
             patch("conflict_scanner._fetch_expenditures_from_db", return_value=expenditures):
            result = scan_meeting_db(conn, meeting_id, "0660620")

        dve_flags = [f for f in result.flags if f.flag_type == "donor_vendor_expenditure"]
        assert len(dve_flags) >= 1, (
            "DB mode should produce donor_vendor_expenditure flags when "
            "expenditures are provided"
        )
        assert dve_flags[0].council_member == "Eduardo Martinez"
        assert "Acme Construction" in dve_flags[0].description

    def test_no_vendor_signal_without_expenditures(self):
        """No donor_vendor_expenditure flags when expenditures list is empty."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        items = [
            (str(uuid.uuid4()), "H-1",
             "Approve contract with Acme Construction for road repair",
             "Professional services agreement with Acme Construction",
             "Public Works", "$150,000"),
        ]
        meeting_data = self._make_meeting_data(items)

        contributions = [
            {
                "donor_name": "Acme Construction",
                "donor_employer": "",
                "council_member": "Eduardo Martinez",
                "committee_name": "Martinez for Richmond 2026",
                "amount": 5000,
                "date": "2025-11-01",
                "filing_id": "FILE-001",
                "source": "netfile",
            },
        ]

        conn = MagicMock()
        with patch("conflict_scanner._fetch_meeting_data_from_db", return_value=meeting_data), \
             patch("conflict_scanner._fetch_contributions_from_db", return_value=contributions), \
             patch("conflict_scanner._fetch_form700_interests_from_db", return_value=[]), \
             patch("conflict_scanner._fetch_expenditures_from_db", return_value=[]):
            result = scan_meeting_db(conn, meeting_id, "0660620")

        dve_flags = [f for f in result.flags if f.flag_type == "donor_vendor_expenditure"]
        assert len(dve_flags) == 0

    def test_expenditure_fetch_called_when_none(self):
        """_fetch_expenditures_from_db is called when expenditures=None."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        items = [
            (str(uuid.uuid4()), "C-1", "Approve minutes",
             "Consent item", "Consent", None),
        ]
        meeting_data = self._make_meeting_data(items)

        conn = MagicMock()
        with patch("conflict_scanner._fetch_meeting_data_from_db", return_value=meeting_data), \
             patch("conflict_scanner._fetch_contributions_from_db", return_value=[]), \
             patch("conflict_scanner._fetch_form700_interests_from_db", return_value=[]), \
             patch("conflict_scanner._fetch_expenditures_from_db", return_value=[]) as mock_fetch:
            scan_meeting_db(conn, meeting_id, "0660620")

        mock_fetch.assert_called_once_with(conn, "0660620")

    def test_expenditure_fetch_skipped_when_provided(self):
        """_fetch_expenditures_from_db is NOT called when expenditures passed."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        items = [
            (str(uuid.uuid4()), "C-1", "Approve minutes",
             "Consent item", "Consent", None),
        ]
        meeting_data = self._make_meeting_data(items)

        conn = MagicMock()
        with patch("conflict_scanner._fetch_meeting_data_from_db", return_value=meeting_data), \
             patch("conflict_scanner._fetch_contributions_from_db", return_value=[]), \
             patch("conflict_scanner._fetch_form700_interests_from_db", return_value=[]), \
             patch("conflict_scanner._fetch_expenditures_from_db") as mock_fetch:
            scan_meeting_db(conn, meeting_id, "0660620", expenditures=[])

        mock_fetch.assert_not_called()


class TestFetchExpendituresFromDb:
    """Test _fetch_expenditures_from_db SQL fetch and row mapping."""

    def test_returns_correct_dict_keys(self):
        """Fetched expenditure dicts have the keys signal detector expects."""
        from conflict_scanner import _fetch_expenditures_from_db

        mock_rows = [
            ("Acme Construction", "Acme Construction", 150000.00,
             "2025-2026", "Public Works", date(2025, 12, 1)),
        ]
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = mock_rows
        cursor.__enter__ = lambda self: cursor
        cursor.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor

        result = _fetch_expenditures_from_db(conn, "0660620")

        assert len(result) == 1
        exp = result[0]
        assert exp["vendor_name"] == "Acme Construction"
        assert exp["normalized_vendor"] == "Acme Construction"
        assert exp["amount"] == 150000.0
        assert exp["fiscal_year"] == "2025-2026"
        assert exp["department"] == "Public Works"
        assert exp["expenditure_date"] == "2025-12-01"

    def test_handles_null_values(self):
        """NULL columns are handled gracefully (empty string / 0.0)."""
        from conflict_scanner import _fetch_expenditures_from_db

        mock_rows = [
            (None, None, None, None, None, None),
        ]
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = mock_rows
        cursor.__enter__ = lambda self: cursor
        cursor.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor

        result = _fetch_expenditures_from_db(conn, "0660620")

        assert len(result) == 1
        exp = result[0]
        assert exp["vendor_name"] == ""
        assert exp["normalized_vendor"] == ""
        assert exp["amount"] == 0.0
        assert exp["fiscal_year"] == ""
        assert exp["department"] == ""
        assert exp["expenditure_date"] == ""

    def test_passes_city_fips_to_query(self):
        """Query filters by city_fips."""
        from conflict_scanner import _fetch_expenditures_from_db

        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        cursor.__enter__ = lambda self: cursor
        cursor.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor

        _fetch_expenditures_from_db(conn, "0660620")

        cursor.execute.assert_called_once()
        args = cursor.execute.call_args
        assert args[0][1] == ("0660620",)

    def test_empty_table_returns_empty_list(self):
        """No rows -> empty list (not an error)."""
        from conflict_scanner import _fetch_expenditures_from_db

        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        cursor.__enter__ = lambda self: cursor
        cursor.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor

        result = _fetch_expenditures_from_db(conn, "0660620")
        assert result == []
