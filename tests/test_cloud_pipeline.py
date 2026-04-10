"""Tests for the cloud pipeline orchestrator (Supabase-native)."""
import json
import time
import uuid
import pytest
from datetime import date
from unittest.mock import patch, MagicMock, ANY, call

from conflict_scanner import ConflictFlag


# ── Helper: mock scan result ────────────────────────────────

def _make_flag(tier=3, confidence=0.4, donor="Test Donor",
               amount=500, committee="Some PAC") -> ConflictFlag:
    """Create a real ConflictFlag for testing. Uses the actual dataclass
    so tests break if the attribute contract changes."""
    return ConflictFlag(
        agenda_item_number="V.1",
        agenda_item_title=f"Item involving {committee}",
        council_member="Test Member",
        flag_type="campaign_contribution",
        description=f"Match: {donor} donated ${amount}",
        evidence=[f"{donor} donated ${amount} to {committee}"],
        confidence=confidence,
        legal_reference="FPPC Reg. 18702.5",
        financial_amount=f"${amount}",
        publication_tier=tier,
        confidence_factors={"signal_count": 1, "max_signal": confidence},
        scanner_version=3,
    )


class _FakeScanResult:
    def __init__(self, flags=None, clean_items=None):
        self.flags = flags or []
        self.clean_items = clean_items or [
            {"item_number": "V.1.a", "title": "Some consent item"}
        ]
        self.enriched_items = []
        self.audit_log = None


# ── Contribution source counting ────────────────────────────

from cloud_pipeline import _contribution_source_counts


class TestContributionSourceCounts:
    """Count contributions by source for scan_runs metadata."""

    def test_empty_list(self):
        assert _contribution_source_counts([]) == {}

    def test_single_source(self):
        contribs = [{"source": "netfile"}, {"source": "netfile"}]
        assert _contribution_source_counts(contribs) == {"netfile": 2}

    def test_multiple_sources(self):
        contribs = [
            {"source": "netfile"},
            {"source": "calaccess"},
            {"source": "netfile"},
            {"source": "calaccess"},
            {"source": "calaccess"},
        ]
        result = _contribution_source_counts(contribs)
        assert result == {"netfile": 2, "calaccess": 3}

    def test_missing_source_key(self):
        """Records without 'source' key get counted as 'unknown'."""
        contribs = [{"amount": 100}, {"source": "netfile"}]
        result = _contribution_source_counts(contribs)
        assert result == {"unknown": 1, "netfile": 1}


# ── Scanner version detection ────────────────────────────────

from cloud_pipeline import _get_scanner_version


class TestGetScannerVersion:
    """Get git SHA for pipeline versioning."""

    @patch("cloud_pipeline.subprocess.run")
    def test_returns_git_sha(self, mock_run):
        mock_run.return_value = MagicMock(returncode=0, stdout="abc1234\n")
        assert _get_scanner_version() == "abc1234"

    @patch("cloud_pipeline.subprocess.run")
    def test_fallback_on_failure(self, mock_run):
        mock_run.return_value = MagicMock(returncode=1, stdout="")
        assert _get_scanner_version() == "unknown"

    @patch("cloud_pipeline.subprocess.run", side_effect=Exception("no git"))
    def test_fallback_on_exception(self, mock_run):
        assert _get_scanner_version() == "unknown"


# ── Full pipeline orchestration ──────────────────────────────

ESCRIBEMEETINGS_DATA = {
    "city_fips": "0660620",
    "meeting_date": "2026-03-03",
    "meeting_name": "City Council Regular Meeting",
    "meeting_url": "https://pub-richmond.escribemeetings.com/Meeting.aspx?Id=abc123",
    "items": [
        {
            "item_number": "V.1.a",
            "title": "Approve Contract with TestCo",
            "description": "APPROVE contract with TestCo for $50,000",
            "attachments": [],
        },
        {
            "item_number": "VI.1",
            "title": "Public Hearing on Rezoning",
            "description": "Conduct public hearing on proposed rezoning of 123 Main St",
            "attachments": [],
        },
    ],
    "stats": {"total_items": 2},
}


class TestRunCloudPipeline:
    """Test the cloud pipeline orchestrator with mocked externals."""

    def _build_patches(self):
        """Return a dict of common mocks for the pipeline."""
        return {
            "cloud_pipeline.get_connection": MagicMock,
            "cloud_pipeline.create_session": MagicMock,
            "cloud_pipeline.discover_meetings": lambda: [{"ID": "abc123"}],
            "cloud_pipeline.find_meeting_by_date": lambda meetings, d: {"ID": "abc123", "StartDate": "2026/03/03"},
            "cloud_pipeline.scrape_meeting": lambda session, meeting: ESCRIBEMEETINGS_DATA,
            "cloud_pipeline.ingest_document": lambda *a, **kw: uuid.uuid4(),
            "cloud_pipeline.create_scan_run": lambda *a, **kw: uuid.uuid4(),
            "cloud_pipeline.complete_scan_run": lambda *a, **kw: None,
            "cloud_pipeline.fail_scan_run": lambda *a, **kw: None,
            "cloud_pipeline.load_meeting_to_db": lambda *a, **kw: uuid.uuid4(),
            "cloud_pipeline.supersede_flags_for_meeting": lambda *a, **kw: 0,
            "cloud_pipeline.save_conflict_flag": lambda *a, **kw: uuid.uuid4(),
            "cloud_pipeline.scan_meeting_json": lambda m, c, f: _FakeScanResult(),
            "cloud_pipeline.generate_comment_from_scan": lambda *a, **kw: "Test comment",
            "cloud_pipeline.detect_missing_documents": lambda m: [],
            "cloud_pipeline.enrich_meeting_data": lambda m, p: (m, ["V.1.a"]),
        }

    @patch("cloud_pipeline.get_connection")
    @patch("cloud_pipeline.create_session")
    @patch("cloud_pipeline.discover_meetings")
    @patch("cloud_pipeline.find_meeting_by_date")
    @patch("cloud_pipeline.scrape_meeting")
    @patch("cloud_pipeline.ingest_document")
    @patch("cloud_pipeline.create_scan_run")
    @patch("cloud_pipeline.complete_scan_run")
    @patch("cloud_pipeline.load_meeting_to_db")
    @patch("cloud_pipeline.supersede_flags_for_meeting")
    @patch("cloud_pipeline.save_conflict_flag")
    @patch("cloud_pipeline.scan_meeting_json")
    @patch("cloud_pipeline.generate_comment_from_scan")
    @patch("cloud_pipeline.detect_missing_documents")
    @patch("cloud_pipeline.enrich_meeting_data")
    def test_successful_pipeline_returns_completed(
        self,
        mock_enrich, mock_missing, mock_gen, mock_scan, mock_save_flag,
        mock_supersede, mock_load_meeting, mock_complete_run,
        mock_create_run, mock_ingest, mock_scrape, mock_find,
        mock_discover, mock_session, mock_conn,
    ):
        """Successful pipeline returns status='completed' with summary data."""
        from cloud_pipeline import run_cloud_pipeline

        # Setup mocks
        mock_conn_instance = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("contributor_name",), ("contributor_employer",), ("amount",), ("contribution_date",), ("committee",), ("source",)]
        mock_cursor.fetchall.return_value = []
        mock_conn_instance.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn_instance.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_conn_instance

        scan_run_id = uuid.uuid4()
        mock_create_run.return_value = scan_run_id
        mock_session.return_value = MagicMock()
        mock_discover.return_value = [{"ID": "abc123"}]
        mock_find.return_value = {"ID": "abc123", "StartDate": "2026/03/03"}
        mock_scrape.return_value = ESCRIBEMEETINGS_DATA
        mock_ingest.return_value = uuid.uuid4()
        mock_load_meeting.return_value = uuid.uuid4()
        mock_supersede.return_value = 0
        mock_scan.return_value = _FakeScanResult()
        mock_gen.return_value = "Test comment"
        mock_missing.return_value = []
        mock_enrich.return_value = ({"meeting_date": "2026-03-03", "consent_calendar": {"items": []}, "action_items": [], "housing_authority_items": []}, ["V.1.a"])

        result = run_cloud_pipeline(
            date_str="2026-03-03",
            scan_mode="prospective",
            triggered_by="test",
        )

        assert result["status"] == "completed"
        assert result["meeting_date"] == "2026-03-03"
        assert result["scan_mode"] == "prospective"
        assert "flags" in result
        assert "scan_run_id" in result
        assert result["execution_seconds"] >= 0

    @patch("cloud_pipeline.get_connection")
    @patch("cloud_pipeline.create_session")
    @patch("cloud_pipeline.discover_meetings")
    @patch("cloud_pipeline.find_meeting_by_date")
    @patch("cloud_pipeline.create_scan_run")
    @patch("cloud_pipeline.complete_scan_run")
    def test_no_meeting_found_returns_skipped(
        self, mock_complete, mock_create_run, mock_find,
        mock_discover, mock_session, mock_conn,
    ):
        """Pipeline returns status='skipped' when no meeting found (not a failure)."""
        from cloud_pipeline import run_cloud_pipeline

        mock_conn.return_value = MagicMock()
        mock_create_run.return_value = uuid.uuid4()
        mock_session.return_value = MagicMock()
        mock_discover.return_value = []
        mock_find.return_value = None

        result = run_cloud_pipeline(
            date_str="2026-12-25",
            scan_mode="prospective",
        )

        assert result["status"] == "skipped"
        assert result["reason"] == "no_meeting"
        mock_complete.assert_called_once()

    @patch("cloud_pipeline.get_connection")
    @patch("cloud_pipeline.create_session")
    @patch("cloud_pipeline.discover_meetings")
    @patch("cloud_pipeline.find_meeting_by_date")
    @patch("cloud_pipeline.scrape_meeting")
    @patch("cloud_pipeline.ingest_document")
    @patch("cloud_pipeline.create_scan_run")
    @patch("cloud_pipeline.complete_scan_run")
    @patch("cloud_pipeline.load_meeting_to_db")
    @patch("cloud_pipeline.supersede_flags_for_meeting")
    @patch("cloud_pipeline.save_conflict_flag")
    @patch("cloud_pipeline.scan_meeting_json")
    @patch("cloud_pipeline.generate_comment_from_scan")
    @patch("cloud_pipeline.detect_missing_documents")
    @patch("cloud_pipeline.enrich_meeting_data")
    def test_prospective_mode_sets_data_cutoff(
        self,
        mock_enrich, mock_missing, mock_gen, mock_scan, mock_save_flag,
        mock_supersede, mock_load_meeting, mock_complete_run,
        mock_create_run, mock_ingest, mock_scrape, mock_find,
        mock_discover, mock_session, mock_conn,
    ):
        """Prospective mode passes data_cutoff_date to scan_run."""
        from cloud_pipeline import run_cloud_pipeline

        mock_conn_instance = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("contributor_name",), ("contributor_employer",), ("amount",), ("contribution_date",), ("committee",), ("source",)]
        mock_cursor.fetchall.return_value = []
        mock_conn_instance.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn_instance.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_conn_instance

        mock_create_run.return_value = uuid.uuid4()
        mock_session.return_value = MagicMock()
        mock_discover.return_value = [{"ID": "abc123"}]
        mock_find.return_value = {"ID": "abc123", "StartDate": "2026/03/03"}
        mock_scrape.return_value = ESCRIBEMEETINGS_DATA
        mock_ingest.return_value = uuid.uuid4()
        mock_load_meeting.return_value = uuid.uuid4()
        mock_supersede.return_value = 0
        mock_scan.return_value = _FakeScanResult()
        mock_gen.return_value = "Test comment"
        mock_missing.return_value = []
        mock_enrich.return_value = ({"meeting_date": "2026-03-03", "consent_calendar": {"items": []}, "action_items": [], "housing_authority_items": []}, [])

        run_cloud_pipeline(date_str="2026-03-03", scan_mode="prospective")

        # Verify create_scan_run was called with data_cutoff_date
        call_kwargs = mock_create_run.call_args
        assert call_kwargs[1]["scan_mode"] == "prospective"
        assert call_kwargs[1]["data_cutoff_date"] == date(2026, 3, 3)

    @patch("cloud_pipeline.get_connection")
    @patch("cloud_pipeline.create_session")
    @patch("cloud_pipeline.discover_meetings")
    @patch("cloud_pipeline.find_meeting_by_date")
    @patch("cloud_pipeline.scrape_meeting")
    @patch("cloud_pipeline.ingest_document")
    @patch("cloud_pipeline.create_scan_run")
    @patch("cloud_pipeline.complete_scan_run")
    @patch("cloud_pipeline.load_meeting_to_db")
    @patch("cloud_pipeline.supersede_flags_for_meeting")
    @patch("cloud_pipeline.save_conflict_flag")
    @patch("cloud_pipeline.scan_meeting_json")
    @patch("cloud_pipeline.generate_comment_from_scan")
    @patch("cloud_pipeline.detect_missing_documents")
    @patch("cloud_pipeline.enrich_meeting_data")
    def test_retrospective_mode_no_cutoff(
        self,
        mock_enrich, mock_missing, mock_gen, mock_scan, mock_save_flag,
        mock_supersede, mock_load_meeting, mock_complete_run,
        mock_create_run, mock_ingest, mock_scrape, mock_find,
        mock_discover, mock_session, mock_conn,
    ):
        """Retrospective mode does not set data_cutoff_date."""
        from cloud_pipeline import run_cloud_pipeline

        mock_conn_instance = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("contributor_name",), ("contributor_employer",), ("amount",), ("contribution_date",), ("committee",), ("source",)]
        mock_cursor.fetchall.return_value = []
        mock_conn_instance.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn_instance.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_conn_instance

        mock_create_run.return_value = uuid.uuid4()
        mock_session.return_value = MagicMock()
        mock_discover.return_value = [{"ID": "abc123"}]
        mock_find.return_value = {"ID": "abc123", "StartDate": "2026/03/03"}
        mock_scrape.return_value = ESCRIBEMEETINGS_DATA
        mock_ingest.return_value = uuid.uuid4()
        mock_load_meeting.return_value = uuid.uuid4()
        mock_supersede.return_value = 0
        mock_scan.return_value = _FakeScanResult()
        mock_gen.return_value = "Test comment"
        mock_missing.return_value = []
        mock_enrich.return_value = ({"meeting_date": "2026-03-03", "consent_calendar": {"items": []}, "action_items": [], "housing_authority_items": []}, [])

        run_cloud_pipeline(date_str="2026-03-03", scan_mode="retrospective")

        call_kwargs = mock_create_run.call_args
        assert call_kwargs[1]["scan_mode"] == "retrospective"
        assert call_kwargs[1]["data_cutoff_date"] is None

    @patch("cloud_pipeline.get_connection")
    @patch("cloud_pipeline.create_session")
    @patch("cloud_pipeline.discover_meetings")
    @patch("cloud_pipeline.find_meeting_by_date")
    @patch("cloud_pipeline.scrape_meeting")
    @patch("cloud_pipeline.ingest_document")
    @patch("cloud_pipeline.create_scan_run")
    @patch("cloud_pipeline.complete_scan_run")
    @patch("cloud_pipeline.load_meeting_to_db")
    @patch("cloud_pipeline.supersede_flags_for_meeting")
    @patch("cloud_pipeline.save_conflict_flag")
    @patch("cloud_pipeline.scan_meeting_json")
    @patch("cloud_pipeline.generate_comment_from_scan")
    @patch("cloud_pipeline.detect_missing_documents")
    @patch("cloud_pipeline.enrich_meeting_data")
    def test_flags_saved_to_database(
        self,
        mock_enrich, mock_missing, mock_gen, mock_scan, mock_save_flag,
        mock_supersede, mock_load_meeting, mock_complete_run,
        mock_create_run, mock_ingest, mock_scrape, mock_find,
        mock_discover, mock_session, mock_conn,
    ):
        """Conflict flags are saved via save_conflict_flag."""
        from cloud_pipeline import run_cloud_pipeline

        mock_conn_instance = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("contributor_name",), ("contributor_employer",), ("amount",), ("contribution_date",), ("committee",), ("source",)]
        mock_cursor.fetchall.return_value = []
        mock_conn_instance.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn_instance.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_conn_instance

        mock_create_run.return_value = uuid.uuid4()
        mock_session.return_value = MagicMock()
        mock_discover.return_value = [{"ID": "abc123"}]
        mock_find.return_value = {"ID": "abc123", "StartDate": "2026/03/03"}
        mock_scrape.return_value = ESCRIBEMEETINGS_DATA
        mock_ingest.return_value = uuid.uuid4()
        mock_load_meeting.return_value = uuid.uuid4()
        mock_supersede.return_value = 0

        # Two flags found
        flags = [_make_flag(tier=2, donor="Big Donor", amount=5000), _make_flag(tier=3)]
        mock_scan.return_value = _FakeScanResult(flags=flags)
        mock_gen.return_value = "Test comment"
        mock_missing.return_value = []
        mock_enrich.return_value = ({"meeting_date": "2026-03-03", "consent_calendar": {"items": []}, "action_items": [], "housing_authority_items": []}, [])

        result = run_cloud_pipeline(date_str="2026-03-03")

        assert result["flags"]["total"] == 2
        assert result["flags"]["tier2"] == 1
        assert result["flags"]["tier3"] == 1
        assert mock_save_flag.call_count == 2

    @patch("cloud_pipeline.get_connection")
    @patch("cloud_pipeline.create_session")
    @patch("cloud_pipeline.discover_meetings")
    @patch("cloud_pipeline.find_meeting_by_date")
    @patch("cloud_pipeline.scrape_meeting")
    @patch("cloud_pipeline.ingest_document")
    @patch("cloud_pipeline.create_scan_run")
    @patch("cloud_pipeline.complete_scan_run")
    @patch("cloud_pipeline.load_meeting_to_db")
    @patch("cloud_pipeline.supersede_flags_for_meeting")
    @patch("cloud_pipeline.save_conflict_flag")
    @patch("cloud_pipeline.scan_meeting_json")
    @patch("cloud_pipeline.generate_comment_from_scan")
    @patch("cloud_pipeline.detect_missing_documents")
    @patch("cloud_pipeline.enrich_meeting_data")
    def test_prospective_supersedes_old_flags(
        self,
        mock_enrich, mock_missing, mock_gen, mock_scan, mock_save_flag,
        mock_supersede, mock_load_meeting, mock_complete_run,
        mock_create_run, mock_ingest, mock_scrape, mock_find,
        mock_discover, mock_session, mock_conn,
    ):
        """Prospective mode calls supersede_flags_for_meeting."""
        from cloud_pipeline import run_cloud_pipeline

        mock_conn_instance = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("contributor_name",), ("contributor_employer",), ("amount",), ("contribution_date",), ("committee",), ("source",)]
        mock_cursor.fetchall.return_value = []
        mock_conn_instance.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn_instance.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_conn_instance

        mock_create_run.return_value = uuid.uuid4()
        mock_session.return_value = MagicMock()
        mock_discover.return_value = [{"ID": "abc123"}]
        mock_find.return_value = {"ID": "abc123", "StartDate": "2026/03/03"}
        mock_scrape.return_value = ESCRIBEMEETINGS_DATA
        mock_ingest.return_value = uuid.uuid4()
        mock_load_meeting.return_value = uuid.uuid4()
        mock_supersede.return_value = 3
        mock_scan.return_value = _FakeScanResult()
        mock_gen.return_value = "Test comment"
        mock_missing.return_value = []
        mock_enrich.return_value = ({"meeting_date": "2026-03-03", "consent_calendar": {"items": []}, "action_items": [], "housing_authority_items": []}, [])

        run_cloud_pipeline(date_str="2026-03-03", scan_mode="prospective")

        mock_supersede.assert_called_once()

    @patch("cloud_pipeline.get_connection")
    @patch("cloud_pipeline.create_scan_run")
    @patch("cloud_pipeline.fail_scan_run")
    @patch("cloud_pipeline.create_session", side_effect=ConnectionError("eSCRIBE down"))
    def test_scrape_failure_records_error(
        self, mock_session, mock_fail, mock_create_run, mock_conn,
    ):
        """Pipeline failure is recorded via fail_scan_run."""
        from cloud_pipeline import run_cloud_pipeline

        mock_conn.return_value = MagicMock()
        mock_create_run.return_value = uuid.uuid4()

        result = run_cloud_pipeline(date_str="2026-03-03")

        assert result["status"] == "failed"
        mock_fail.assert_called_once()
        error_arg = mock_fail.call_args[0][2]  # positional: conn, id, error_message
        assert "eSCRIBE down" in error_arg

    @patch("cloud_pipeline.get_connection")
    @patch("cloud_pipeline.create_session")
    @patch("cloud_pipeline.discover_meetings")
    @patch("cloud_pipeline.find_meeting_by_date")
    @patch("cloud_pipeline.scrape_meeting")
    @patch("cloud_pipeline.ingest_document")
    @patch("cloud_pipeline.create_scan_run")
    @patch("cloud_pipeline.complete_scan_run")
    @patch("cloud_pipeline.load_meeting_to_db")
    @patch("cloud_pipeline.supersede_flags_for_meeting")
    @patch("cloud_pipeline.save_conflict_flag")
    @patch("cloud_pipeline.scan_meeting_json")
    @patch("cloud_pipeline.generate_comment_from_scan")
    @patch("cloud_pipeline.detect_missing_documents")
    @patch("cloud_pipeline.enrich_meeting_data")
    def test_conn_closed_on_success(
        self,
        mock_enrich, mock_missing, mock_gen, mock_scan, mock_save_flag,
        mock_supersede, mock_load_meeting, mock_complete_run,
        mock_create_run, mock_ingest, mock_scrape, mock_find,
        mock_discover, mock_session, mock_conn,
    ):
        """Connection is always closed (via finally block)."""
        from cloud_pipeline import run_cloud_pipeline

        mock_conn_instance = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("contributor_name",), ("contributor_employer",), ("amount",), ("contribution_date",), ("committee",), ("source",)]
        mock_cursor.fetchall.return_value = []
        mock_conn_instance.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn_instance.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_conn_instance

        mock_create_run.return_value = uuid.uuid4()
        mock_session.return_value = MagicMock()
        mock_discover.return_value = [{"ID": "abc123"}]
        mock_find.return_value = {"ID": "abc123", "StartDate": "2026/03/03"}
        mock_scrape.return_value = ESCRIBEMEETINGS_DATA
        mock_ingest.return_value = uuid.uuid4()
        mock_load_meeting.return_value = uuid.uuid4()
        mock_supersede.return_value = 0
        mock_scan.return_value = _FakeScanResult()
        mock_gen.return_value = "Test comment"
        mock_missing.return_value = []
        mock_enrich.return_value = ({"meeting_date": "2026-03-03", "consent_calendar": {"items": []}, "action_items": [], "housing_authority_items": []}, [])

        run_cloud_pipeline(date_str="2026-03-03")

        mock_conn_instance.close.assert_called_once()

    @patch("cloud_pipeline.get_connection")
    @patch("cloud_pipeline.create_scan_run")
    @patch("cloud_pipeline.fail_scan_run")
    @patch("cloud_pipeline.create_session", side_effect=Exception("boom"))
    def test_conn_closed_on_failure(
        self, mock_session, mock_fail, mock_create_run, mock_conn,
    ):
        """Connection is closed even when pipeline fails."""
        from cloud_pipeline import run_cloud_pipeline

        mock_conn_instance = MagicMock()
        mock_conn.return_value = mock_conn_instance
        mock_create_run.return_value = uuid.uuid4()

        run_cloud_pipeline(date_str="2026-03-03")

        mock_conn_instance.close.assert_called_once()


# ── Generator helper tests ─────────────────────────────────

from cloud_pipeline import _generate_meeting_summaries, _generate_meeting_explainers


class TestGenerateMeetingSummaries:
    """Step 8: Generate plain language summaries for a meeting."""

    @patch("cloud_pipeline.generate_summary_for_item")
    @patch("cloud_pipeline.get_items_needing_summaries")
    def test_generates_summaries_for_meeting(self, mock_get, mock_gen):
        """Generates summaries for items returned by the query."""
        mock_get.return_value = [
            {"id": "1", "title": "Contract A", "category": "contracts"},
            {"id": "2", "title": "Rezoning B", "category": "zoning"},
        ]
        mock_gen.return_value = {"skipped": False, "summary": "A plain summary"}

        conn = MagicMock()
        meeting_id = uuid.uuid4()
        result = _generate_meeting_summaries(conn, meeting_id, "0660620")

        assert result["generated"] == 2
        assert result["skipped"] == 0
        assert result["errors"] == 0
        assert result["total"] == 2
        assert mock_gen.call_count == 2

    @patch("cloud_pipeline.get_items_needing_summaries")
    def test_no_items_returns_zeros(self, mock_get):
        """Returns zero stats when no items need summaries."""
        mock_get.return_value = []

        result = _generate_meeting_summaries(MagicMock(), uuid.uuid4(), "0660620")

        assert result["generated"] == 0
        assert result["total"] == 0

    @patch("cloud_pipeline.generate_summary_for_item")
    @patch("cloud_pipeline.get_items_needing_summaries")
    def test_skipped_items_counted(self, mock_get, mock_gen):
        """Procedural items are counted as skipped."""
        mock_get.return_value = [
            {"id": "1", "title": "Roll Call", "category": "procedural"},
        ]
        mock_gen.return_value = {"skipped": True, "reason": "procedural"}

        result = _generate_meeting_summaries(MagicMock(), uuid.uuid4(), "0660620")

        assert result["generated"] == 0
        assert result["skipped"] == 1

    @patch("cloud_pipeline.generate_summary_for_item", side_effect=Exception("API error"))
    @patch("cloud_pipeline.get_items_needing_summaries")
    def test_individual_errors_dont_stop_batch(self, mock_get, mock_gen):
        """One item's API error doesn't stop processing others."""
        mock_get.return_value = [
            {"id": "1", "title": "Item A", "category": "contracts"},
            {"id": "2", "title": "Item B", "category": "zoning"},
        ]

        result = _generate_meeting_summaries(MagicMock(), uuid.uuid4(), "0660620")

        assert result["errors"] == 2
        assert result["generated"] == 0

    @patch("cloud_pipeline.get_items_needing_summaries", side_effect=Exception("DB down"))
    def test_query_failure_returns_error_stats(self, mock_get):
        """Database failure returns error stats, never raises."""
        result = _generate_meeting_summaries(MagicMock(), uuid.uuid4(), "0660620")

        assert result["errors"] == 1
        assert "error" in result


class TestGenerateMeetingExplainers:
    """Step 9: Generate vote explainers for a meeting."""

    @patch("cloud_pipeline.generate_explainer_for_motion")
    @patch("cloud_pipeline.get_motions_needing_explainers")
    def test_generates_explainers_for_meeting(self, mock_get, mock_gen):
        """Generates explainers for motions returned by the query."""
        mock_get.return_value = [
            {"motion_id": "1", "item_title": "Contract A", "category": "contracts",
             "result": "Approved", "vote_tally": "5-2", "votes": []},
        ]
        mock_gen.return_value = {"skipped": False, "explainer": "An explainer"}

        result = _generate_meeting_explainers(MagicMock(), uuid.uuid4(), "0660620")

        assert result["generated"] == 1
        assert result["errors"] == 0

    @patch("cloud_pipeline.get_motions_needing_explainers")
    def test_no_motions_returns_zeros(self, mock_get):
        """Returns zero stats when no motions need explainers."""
        mock_get.return_value = []

        result = _generate_meeting_explainers(MagicMock(), uuid.uuid4(), "0660620")

        assert result["generated"] == 0
        assert result["total"] == 0

    @patch("cloud_pipeline.generate_explainer_for_motion")
    @patch("cloud_pipeline.get_motions_needing_explainers")
    def test_skipped_motions_counted(self, mock_get, mock_gen):
        """Unanimous consent motions are counted as skipped."""
        mock_get.return_value = [
            {"motion_id": "1", "item_title": "Consent Item", "category": "procedural",
             "result": "Approved", "vote_tally": "7-0", "votes": []},
        ]
        mock_gen.return_value = {"skipped": True, "reason": "unanimous_consent"}

        result = _generate_meeting_explainers(MagicMock(), uuid.uuid4(), "0660620")

        assert result["skipped"] == 1
        assert result["generated"] == 0

    @patch("cloud_pipeline.generate_explainer_for_motion", side_effect=Exception("API error"))
    @patch("cloud_pipeline.get_motions_needing_explainers")
    def test_individual_errors_dont_stop_batch(self, mock_get, mock_gen):
        """One motion's API error doesn't stop processing others."""
        mock_get.return_value = [
            {"motion_id": "1", "item_title": "A", "category": "contracts",
             "result": "Approved", "vote_tally": "5-2", "votes": []},
        ]

        result = _generate_meeting_explainers(MagicMock(), uuid.uuid4(), "0660620")

        assert result["errors"] == 1

    @patch("cloud_pipeline.get_motions_needing_explainers", side_effect=Exception("DB down"))
    def test_query_failure_returns_error_stats(self, mock_get):
        """Database failure returns error stats, never raises."""
        result = _generate_meeting_explainers(MagicMock(), uuid.uuid4(), "0660620")

        assert result["errors"] == 1
        assert "error" in result


class TestPipelineGeneratorIntegration:
    """Verify generators are wired into the full pipeline flow."""

    @patch("cloud_pipeline._generate_meeting_explainers")
    @patch("cloud_pipeline._generate_meeting_summaries")
    @patch("cloud_pipeline.get_connection")
    @patch("cloud_pipeline.create_session")
    @patch("cloud_pipeline.discover_meetings")
    @patch("cloud_pipeline.find_meeting_by_date")
    @patch("cloud_pipeline.scrape_meeting")
    @patch("cloud_pipeline.ingest_document")
    @patch("cloud_pipeline.create_scan_run")
    @patch("cloud_pipeline.complete_scan_run")
    @patch("cloud_pipeline.load_meeting_to_db")
    @patch("cloud_pipeline.supersede_flags_for_meeting")
    @patch("cloud_pipeline.save_conflict_flag")
    @patch("cloud_pipeline.scan_meeting_json")
    @patch("cloud_pipeline.generate_comment_from_scan")
    @patch("cloud_pipeline.detect_missing_documents")
    @patch("cloud_pipeline.enrich_meeting_data")
    def test_generators_called_after_meeting_load(
        self,
        mock_enrich, mock_missing, mock_gen_comment, mock_scan, mock_save_flag,
        mock_supersede, mock_load_meeting, mock_complete_run,
        mock_create_run, mock_ingest, mock_scrape, mock_find,
        mock_discover, mock_session, mock_conn,
        mock_summaries, mock_explainers,
    ):
        """Generators are called with meeting_id after Layer 2 load."""
        from cloud_pipeline import run_cloud_pipeline

        mock_conn_instance = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("contributor_name",), ("contributor_employer",), ("amount",), ("contribution_date",), ("committee",), ("source",)]
        mock_cursor.fetchall.return_value = []
        mock_conn_instance.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn_instance.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_conn_instance

        meeting_id = uuid.uuid4()
        mock_create_run.return_value = uuid.uuid4()
        mock_session.return_value = MagicMock()
        mock_discover.return_value = [{"ID": "abc123"}]
        mock_find.return_value = {"ID": "abc123", "StartDate": "2026/03/03"}
        mock_scrape.return_value = ESCRIBEMEETINGS_DATA
        mock_ingest.return_value = uuid.uuid4()
        mock_load_meeting.return_value = meeting_id
        mock_supersede.return_value = 0
        mock_scan.return_value = _FakeScanResult()
        mock_gen_comment.return_value = "Test comment"
        mock_missing.return_value = []
        mock_enrich.return_value = ({"meeting_date": "2026-03-03", "consent_calendar": {"items": []}, "action_items": [], "housing_authority_items": []}, [])
        mock_summaries.return_value = {"generated": 3, "skipped": 1, "errors": 0, "total": 4}
        mock_explainers.return_value = {"generated": 2, "skipped": 0, "errors": 0, "total": 2}

        result = run_cloud_pipeline(date_str="2026-03-03")

        # Generators called with the loaded meeting_id
        mock_summaries.assert_called_once_with(mock_conn_instance, meeting_id, "0660620")
        mock_explainers.assert_called_once_with(mock_conn_instance, meeting_id, "0660620")

        # Stats included in result
        assert result["summaries"]["generated"] == 3
        assert result["explainers"]["generated"] == 2

    @patch("cloud_pipeline._generate_meeting_explainers")
    @patch("cloud_pipeline._generate_meeting_summaries")
    @patch("cloud_pipeline.get_connection")
    @patch("cloud_pipeline.create_session")
    @patch("cloud_pipeline.discover_meetings")
    @patch("cloud_pipeline.find_meeting_by_date")
    @patch("cloud_pipeline.scrape_meeting")
    @patch("cloud_pipeline.ingest_document")
    @patch("cloud_pipeline.create_scan_run")
    @patch("cloud_pipeline.complete_scan_run")
    @patch("cloud_pipeline.load_meeting_to_db")
    @patch("cloud_pipeline.supersede_flags_for_meeting")
    @patch("cloud_pipeline.save_conflict_flag")
    @patch("cloud_pipeline.scan_meeting_json")
    @patch("cloud_pipeline.generate_comment_from_scan")
    @patch("cloud_pipeline.detect_missing_documents")
    @patch("cloud_pipeline.enrich_meeting_data")
    def test_skip_generators_flag(
        self,
        mock_enrich, mock_missing, mock_gen_comment, mock_scan, mock_save_flag,
        mock_supersede, mock_load_meeting, mock_complete_run,
        mock_create_run, mock_ingest, mock_scrape, mock_find,
        mock_discover, mock_session, mock_conn,
        mock_summaries, mock_explainers,
    ):
        """--skip-generators prevents generator calls."""
        from cloud_pipeline import run_cloud_pipeline

        mock_conn_instance = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.description = [("contributor_name",), ("contributor_employer",), ("amount",), ("contribution_date",), ("committee",), ("source",)]
        mock_cursor.fetchall.return_value = []
        mock_conn_instance.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn_instance.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.return_value = mock_conn_instance

        mock_create_run.return_value = uuid.uuid4()
        mock_session.return_value = MagicMock()
        mock_discover.return_value = [{"ID": "abc123"}]
        mock_find.return_value = {"ID": "abc123", "StartDate": "2026/03/03"}
        mock_scrape.return_value = ESCRIBEMEETINGS_DATA
        mock_ingest.return_value = uuid.uuid4()
        mock_load_meeting.return_value = uuid.uuid4()
        mock_supersede.return_value = 0
        mock_scan.return_value = _FakeScanResult()
        mock_gen_comment.return_value = "Test comment"
        mock_missing.return_value = []
        mock_enrich.return_value = ({"meeting_date": "2026-03-03", "consent_calendar": {"items": []}, "action_items": [], "housing_authority_items": []}, [])

        result = run_cloud_pipeline(date_str="2026-03-03", skip_generators=True)

        mock_summaries.assert_not_called()
        mock_explainers.assert_not_called()
        assert result["summaries"]["generated"] == 0
        assert result["explainers"]["generated"] == 0
        assert result["status"] == "completed"
