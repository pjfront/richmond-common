"""Tests for the cloud pipeline orchestrator (Supabase-native)."""
import json
import uuid
import pytest
from datetime import date
from unittest.mock import patch, MagicMock, ANY


# ── Helper: mock scan result ────────────────────────────────

class _FakeFlag:
    def __init__(self, tier=3, confidence=0.4, donor="Test Donor",
                 amount=500, committee="Some PAC", match_type="substring"):
        self.publication_tier = tier
        self.confidence = confidence
        self.donor_name = donor
        self.amount = amount
        self.committee = committee
        self.match_type = match_type
        self.description = f"Match: {donor} donated ${amount}"


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
    @patch("cloud_pipeline.fail_scan_run")
    def test_no_meeting_found_returns_failed(
        self, mock_fail, mock_create_run, mock_find,
        mock_discover, mock_session, mock_conn,
    ):
        """Pipeline returns status='failed' when no meeting found."""
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

        assert result["status"] == "failed"
        assert "error" in result
        mock_fail.assert_called_once()

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
        flags = [_FakeFlag(tier=2, donor="Big Donor", amount=5000), _FakeFlag(tier=3)]
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
