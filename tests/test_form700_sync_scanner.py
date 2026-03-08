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
        expected = {"netfile", "calaccess", "escribemeetings", "nextrequest", "archive_center", "form700", "minutes_extraction", "socrata_payroll", "socrata_expenditures", "courts"}
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

    These tests verify:
    1. Real property query joins form700_filings for period context
    2. Income/investment cross-referencing works in DB mode
    3. is_current filter prevents flagging former officials
    4. Filing source URL appears in evidence
    """

    def _build_cursor(self, meeting_row, items, fetchall_sequence):
        """Build a mock conn+cursor with scripted fetchall responses.

        scan_meeting_db calls:
          fetchone: meeting info
          fetchall: agenda items
          fetchall[n]: per-entity contribution queries, real property, income queries
        """
        conn = MagicMock()
        cursor = MagicMock()
        cursor.fetchone = MagicMock(return_value=meeting_row)
        # Pad with empty results to handle any additional queries
        all_fetchall = [items] + fetchall_sequence + [[] for _ in range(50)]
        cursor.fetchall = MagicMock(side_effect=all_fetchall)
        cursor.__enter__ = lambda self: cursor
        cursor.__exit__ = MagicMock(return_value=False)
        conn.cursor.return_value = cursor
        return conn

    @patch("conflict_scanner.extract_entity_names", return_value=[])
    def test_real_property_flag_includes_filing_period(self, mock_entities):
        """Real property flag includes period_end from form700_filings join."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        meeting_row = (date(2026, 3, 1), "Regular Meeting")
        items = [
            (str(uuid.uuid4()), "H-1", "Rezoning Application for 123 Main Street",
             "Request to rezone from residential to commercial", "Zoning",
             "$0", False),
        ]

        # With no entities extracted, query sequence after items is:
        # 1. Real property interests (land-use item triggers this)
        real_property_results = [
            ("Sue Wilson", "123 Main St, Richmond CA 94804", 2024,
             "Richmond, CA", date(2024, 1, 1), date(2024, 12, 31),
             "https://netfile.com/filing/123"),
        ]

        conn = self._build_cursor(meeting_row, items, [real_property_results])
        result = scan_meeting_db(conn, meeting_id, "0660620")

        rp_flags = [f for f in result.flags if f.flag_type == "form700_real_property"]
        assert len(rp_flags) >= 1

        flag = rp_flags[0]
        assert flag.council_member == "Sue Wilson"
        assert "Schedule B" in flag.evidence[0]
        assert "period ending 2024-12-31" in flag.description
        assert flag.confidence == 0.4

    @patch("conflict_scanner.extract_entity_names", return_value=[])
    def test_real_property_flag_without_filing_period(self, mock_entities):
        """Real property flag works even without filing period data (NULL join)."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        meeting_row = (date(2026, 3, 1), "Regular Meeting")
        items = [
            (str(uuid.uuid4()), "H-1", "Variance for 456 Oak Ave Development",
             "Request for height variance", "Planning",
             None, False),
        ]

        # Interest without filing period (period_start, period_end, source_url are NULL)
        real_property_results = [
            ("Eduardo Martinez", "456 Oak Ave, Richmond", 2023,
             "Richmond, CA", None, None, None),
        ]

        conn = self._build_cursor(meeting_row, items, [real_property_results])
        result = scan_meeting_db(conn, meeting_id, "0660620")

        rp_flags = [f for f in result.flags if f.flag_type == "form700_real_property"]
        assert len(rp_flags) >= 1

        flag = rp_flags[0]
        assert flag.council_member == "Eduardo Martinez"
        assert "period ending" not in flag.description
        assert "FPPC/NetFile" in flag.evidence[1]

    @patch("conflict_scanner.extract_entity_names", return_value=["Chevron Corporation"])
    def test_income_investment_cross_reference(self, mock_entities):
        """Income/investment interests match entity names in agenda items."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        meeting_row = (date(2026, 3, 1), "Regular Meeting")
        items = [
            (str(uuid.uuid4()), "I-1", "Chevron Refinery Modernization Project",
             "Environmental review for Chevron facility upgrades", "Environment",
             "$500,000", False),
        ]

        # With 1 entity ("Chevron Corporation"), the fetchall sequence is:
        # 1. Contribution query for "Chevron Corporation" → empty
        # 2. Income/investment query for "Chevron Corporation"
        income_results = [
            ("Soheila Bana", "income", "Chevron Corporation - consulting",
             2024, date(2024, 1, 1), date(2024, 12, 31),
             "https://netfile.com/filing/456"),
        ]

        conn = self._build_cursor(meeting_row, items, [
            [],              # contribution query for "Chevron Corporation"
            income_results,  # income/investment query for "Chevron Corporation"
        ])
        result = scan_meeting_db(conn, meeting_id, "0660620")

        income_flags = [f for f in result.flags if f.flag_type == "form700_income"]
        assert len(income_flags) >= 1

        flag = income_flags[0]
        assert flag.council_member == "Soheila Bana"
        assert "income" in flag.description.lower()
        assert "Chevron" in flag.description
        assert flag.confidence == 0.5
        assert "period ending 2024-12-31" in flag.description
        assert "Schedule C" in flag.evidence[0]

    @patch("conflict_scanner.extract_entity_names", return_value=[])
    def test_no_flags_for_non_land_use_items(self, mock_entities):
        """Non-land-use agenda items don't trigger real property checks."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        meeting_row = (date(2026, 3, 1), "Regular Meeting")
        items = [
            (str(uuid.uuid4()), "C-1", "Approve Minutes of Previous Meeting",
             "Consent calendar item", "Consent",
             None, True),
        ]

        # No entities, no land-use keywords → no Form 700 queries at all
        conn = self._build_cursor(meeting_row, items, [])
        result = scan_meeting_db(conn, meeting_id, "0660620")

        rp_flags = [f for f in result.flags if f.flag_type == "form700_real_property"]
        assert len(rp_flags) == 0

    @patch("conflict_scanner.extract_entity_names", return_value=[])
    def test_form700_flags_include_source_url(self, mock_entities):
        """Form 700 flags include the filing source URL in evidence."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        meeting_row = (date(2026, 3, 1), "Regular Meeting")
        items = [
            (str(uuid.uuid4()), "H-1", "General Plan Amendment - Downtown Rezoning",
             "Rezone downtown area", "Planning",
             None, False),
        ]

        real_property_results = [
            ("Jamelia Brown", "Downtown property", 2024,
             "Richmond, CA", date(2024, 1, 1), date(2024, 12, 31),
             "https://public.netfile.com/pub/?AID=RICH&filing=789"),
        ]

        conn = self._build_cursor(meeting_row, items, [real_property_results])
        result = scan_meeting_db(conn, meeting_id, "0660620")

        rp_flags = [f for f in result.flags if f.flag_type == "form700_real_property"]
        assert len(rp_flags) >= 1

        evidence_text = " ".join(rp_flags[0].evidence)
        assert "netfile.com" in evidence_text

    @patch("conflict_scanner.extract_entity_names", return_value=[])
    def test_real_property_legal_reference(self, mock_entities):
        """Real property flags cite the correct legal reference."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        meeting_row = (date(2026, 3, 1), "Regular Meeting")
        items = [
            (str(uuid.uuid4()), "H-1", "Zoning Variance Application",
             "Height variance request", "Planning",
             None, False),
        ]

        real_property_results = [
            ("Claudia Jimenez", "Residential property", 2024,
             "Richmond, CA", None, None, None),
        ]

        conn = self._build_cursor(meeting_row, items, [real_property_results])
        result = scan_meeting_db(conn, meeting_id, "0660620")

        rp_flags = [f for f in result.flags if f.flag_type == "form700_real_property"]
        assert len(rp_flags) >= 1
        assert "87100" in rp_flags[0].legal_reference
        assert "18702.2" in rp_flags[0].legal_reference
        assert "500 feet" in rp_flags[0].legal_reference

    @patch("conflict_scanner.extract_entity_names", return_value=["Acme Development"])
    def test_investment_flag_type(self, mock_entities):
        """Investment interests produce form700_investment flag type.

        Entity name must be >= 10 chars normalized for names_match substring
        matching (e.g., "acme development" = 16 chars). Short names like
        "acme corp" (9 chars) fall below the threshold.
        """
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        meeting_row = (date(2026, 3, 1), "Regular Meeting")
        items = [
            (str(uuid.uuid4()), "F-1", "Contract with Acme Development for services",
             "Professional services agreement", "Finance",
             "$50,000", False),
        ]

        investment_results = [
            ("Eduardo Martinez", "investment", "Acme Development - stock holdings",
             2024, date(2024, 1, 1), date(2024, 12, 31),
             "https://netfile.com/filing/999"),
        ]

        conn = self._build_cursor(meeting_row, items, [
            [],                  # contribution query for "Acme Development"
            investment_results,  # income/investment query for "Acme Development"
        ])
        result = scan_meeting_db(conn, meeting_id, "0660620")

        inv_flags = [f for f in result.flags if f.flag_type == "form700_investment"]
        assert len(inv_flags) >= 1
        assert inv_flags[0].council_member == "Eduardo Martinez"
        assert "period ending 2024-12-31" in inv_flags[0].description
        assert "Schedule D" in inv_flags[0].evidence[0]

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

    @patch("conflict_scanner.extract_entity_names", return_value=[])
    def test_appointment_item_skips_real_property(self, mock_entities):
        """Items with both zoning and appointment keywords skip real property check."""
        from conflict_scanner import scan_meeting_db

        meeting_id = str(uuid.uuid4())
        meeting_row = (date(2026, 3, 1), "Regular Meeting")
        # Contains both "zoning" (land-use) and "commission" + "appointment" keywords
        items = [
            (str(uuid.uuid4()), "J-1",
             "Appointment to Planning Commission - Zoning Committee",
             "Reappointment of commissioner", "Appointments",
             None, False),
        ]

        # If appointment keywords suppress real property check,
        # no real property query should fire
        conn = self._build_cursor(meeting_row, items, [])
        result = scan_meeting_db(conn, meeting_id, "0660620")

        rp_flags = [f for f in result.flags if f.flag_type == "form700_real_property"]
        assert len(rp_flags) == 0
