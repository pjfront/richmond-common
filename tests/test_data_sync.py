"""Tests for the unified data source sync module."""
import json
import uuid
from datetime import datetime

import pytest
from unittest.mock import patch, MagicMock, call


# ── run_sync orchestration ───────────────────────────────────
#
# run_sync() dispatches via SYNC_SOURCES dict, which holds direct
# function references. Patching "data_sync.sync_netfile" replaces the
# module attribute but NOT the dict entry. Use patch.dict to swap
# entries in SYNC_SOURCES for clean orchestration tests.

class TestRunSync:
    """Test the sync orchestrator: logging, dispatch, error handling."""

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_successful_sync_returns_completed(
        self, mock_complete, mock_create, mock_conn,
    ):
        """Successful sync returns status='completed' with record counts."""
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        log_id = uuid.uuid4()
        mock_create.return_value = log_id

        fake_sync = MagicMock(return_value={
            "records_fetched": 100,
            "records_new": 10,
            "records_updated": 0,
            "donors_created": 5,
            "committees_created": 2,
            "skipped": 3,
        })

        with patch.dict(SYNC_SOURCES, {"netfile": fake_sync}):
            result = run_sync(source="netfile", sync_type="incremental", triggered_by="test")

        assert result["status"] == "completed"
        assert result["records_fetched"] == 100
        assert result["records_new"] == 10
        assert result["sync_log_id"] == str(log_id)

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_failed_sync_returns_error(
        self, mock_complete, mock_create, mock_conn,
    ):
        """Failed sync returns status='failed' with error message."""
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        log_id = uuid.uuid4()
        mock_create.return_value = log_id

        fake_sync = MagicMock(side_effect=ConnectionError("API down"))

        with patch.dict(SYNC_SOURCES, {"netfile": fake_sync}):
            result = run_sync(source="netfile", max_retries=0)  # No retries

        assert result["status"] == "failed"
        assert "API down" in result["error"]
        mock_complete.assert_called_once()
        call_kwargs = mock_complete.call_args[1]
        assert call_kwargs["error_message"] == "API down"

    def test_unknown_source_raises(self):
        """Unknown source name raises ValueError."""
        from data_sync import run_sync

        with pytest.raises(ValueError, match="Unknown source"):
            run_sync(source="nonexistent_source")

    @patch("data_sync.time.sleep")  # Don't actually sleep in tests
    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_retry_on_transient_failure_then_success(
        self, mock_complete, mock_create, mock_conn, mock_sleep,
    ):
        """Transient errors retry and succeed on subsequent attempt."""
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()

        # Fail once with ConnectionError, then succeed
        fake_sync = MagicMock(side_effect=[
            ConnectionError("Connection reset"),
            {"records_fetched": 50, "records_new": 5, "records_updated": 0},
        ])

        with patch.dict(SYNC_SOURCES, {"netfile": fake_sync}):
            result = run_sync(source="netfile", max_retries=2)

        assert result["status"] == "completed"
        assert result["records_fetched"] == 50
        assert fake_sync.call_count == 2  # First attempt failed, second succeeded
        mock_sleep.assert_called_once_with(30)  # 30s backoff on first retry

    @patch("data_sync.time.sleep")
    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_non_transient_error_fails_immediately(
        self, mock_complete, mock_create, mock_conn, mock_sleep,
    ):
        """Non-transient errors (e.g., config errors) fail without retry."""
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()

        fake_sync = MagicMock(side_effect=ValueError("Bad config"))

        with patch.dict(SYNC_SOURCES, {"netfile": fake_sync}):
            result = run_sync(source="netfile", max_retries=2)

        assert result["status"] == "failed"
        assert "Bad config" in result["error"]
        assert fake_sync.call_count == 1  # No retries
        mock_sleep.assert_not_called()

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_calaccess_source_dispatches(
        self, mock_complete, mock_create, mock_conn,
    ):
        """Calaccess source calls the calaccess sync function."""
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(return_value={
            "records_fetched": 50, "records_new": 5, "records_updated": 0,
        })

        with patch.dict(SYNC_SOURCES, {"calaccess": fake_sync}):
            result = run_sync(source="calaccess")

        fake_sync.assert_called_once()
        assert result["status"] == "completed"

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_escribemeetings_source_dispatches(
        self, mock_complete, mock_create, mock_conn,
    ):
        """Escribemeetings source calls the escribemeetings sync function."""
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(return_value={
            "records_fetched": 3, "records_new": 1, "records_updated": 0,
        })

        with patch.dict(SYNC_SOURCES, {"escribemeetings": fake_sync}):
            result = run_sync(source="escribemeetings")

        fake_sync.assert_called_once()
        assert result["status"] == "completed"

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_escribemeetings_minutes_source_dispatches(
        self, mock_complete, mock_create, mock_conn,
    ):
        """Escribemeetings_minutes source calls the minutes sync function."""
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(return_value={
            "records_fetched": 5, "records_new": 3, "records_updated": 0,
        })

        with patch.dict(SYNC_SOURCES, {"escribemeetings_minutes": fake_sync}):
            result = run_sync(source="escribemeetings_minutes")

        fake_sync.assert_called_once()
        assert result["status"] == "completed"

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_sync_log_lifecycle(
        self, mock_complete, mock_create, mock_conn,
    ):
        """Sync creates log at start and updates on completion."""
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn_instance = MagicMock()
        mock_conn.return_value = mock_conn_instance
        log_id = uuid.uuid4()
        mock_create.return_value = log_id
        fake_sync = MagicMock(return_value={"records_fetched": 5, "records_new": 1, "records_updated": 0})

        with patch.dict(SYNC_SOURCES, {"netfile": fake_sync}):
            run_sync(source="netfile", triggered_by="n8n", pipeline_run_id="run-123")

        mock_create.assert_called_once()
        create_kwargs = mock_create.call_args[1]
        assert create_kwargs["source"] == "netfile"
        assert create_kwargs["triggered_by"] == "n8n"
        assert create_kwargs["pipeline_run_id"] == "run-123"
        mock_complete.assert_called_once()

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_conn_always_closed(
        self, mock_complete, mock_create, mock_conn,
    ):
        """Connection is closed even when sync fails."""
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn_instance = MagicMock()
        mock_conn.return_value = mock_conn_instance
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(side_effect=RuntimeError("boom"))

        with patch.dict(SYNC_SOURCES, {"netfile": fake_sync}):
            run_sync(source="netfile")

        mock_conn_instance.close.assert_called_once()

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_pipeline_run_id_passed_through(
        self, mock_complete, mock_create, mock_conn,
    ):
        """Pipeline run ID flows from CLI to sync log."""
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(return_value={"records_fetched": 0, "records_new": 0, "records_updated": 0})

        with patch.dict(SYNC_SOURCES, {"netfile": fake_sync}):
            run_sync(source="netfile", pipeline_run_id="gh-actions-12345")

        create_kwargs = mock_create.call_args[1]
        assert create_kwargs["pipeline_run_id"] == "gh-actions-12345"


# ── SYNC_SOURCES registry ────────────────────────────────────

class TestSyncSourcesRegistry:
    """Verify the sync source registry is correct."""

    def test_all_sources_registered(self):
        from data_sync import SYNC_SOURCES
        assert "netfile" in SYNC_SOURCES
        assert "calaccess" in SYNC_SOURCES
        assert "escribemeetings" in SYNC_SOURCES
        assert "minutes_extraction" in SYNC_SOURCES
        assert "socrata_payroll" in SYNC_SOURCES
        assert "socrata_expenditures" in SYNC_SOURCES

    def test_sources_are_callable(self):
        from data_sync import SYNC_SOURCES
        for name, fn in SYNC_SOURCES.items():
            assert callable(fn), f"{name} is not callable"


# ── sync_escribemeetings logic ────────────────────────────────
#
# sync_escribemeetings uses lazy imports (from escribemeetings_scraper
# import ...) inside the function body, so we must patch the actual
# source modules at their origin.

class TestSyncEscribemeetings:
    """Test escribemeetings sync function directly."""

    @patch("escribemeetings_scraper.create_session")
    @patch("escribemeetings_scraper.discover_meetings")
    @patch("escribemeetings_scraper.scrape_meeting")
    @patch("db.ingest_document")
    @patch("db.load_meeting_to_db")
    @patch("db.resolve_body_id", return_value=None)
    def test_skips_existing_meetings(
        self, mock_resolve_body, mock_load_meeting, mock_ingest, mock_scrape, mock_discover, mock_session,
    ):
        """Meetings already in documents table are skipped."""
        from data_sync import sync_escribemeetings

        from factories import make_escribemeetings_raw

        mock_session.return_value = MagicMock()
        mock_discover.return_value = [
            make_escribemeetings_raw(date="2026/03/03", guid="abc"),
            make_escribemeetings_raw(date="2026/03/10", guid="def"),
        ]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # First meeting exists, second doesn't
        mock_cursor.fetchone.side_effect = [("existing-id",), None]
        mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_scrape.return_value = {
            "meeting_date": "2026-03-10",
            "meeting_name": "City Council",
            "meeting_url": "https://example.com",
            "items": [],
        }
        mock_ingest.return_value = uuid.uuid4()

        result = sync_escribemeetings(
            conn=mock_conn,
            city_fips="0660620",
            sync_type="full",
        )

        assert mock_scrape.call_count == 1
        assert result["records_fetched"] == 2
        assert result["records_new"] == 1

    @patch("escribemeetings_scraper.create_session")
    @patch("escribemeetings_scraper.discover_meetings")
    @patch("escribemeetings_scraper.scrape_meeting")
    @patch("db.ingest_document")
    @patch("db.load_meeting_to_db")
    @patch("db.resolve_body_id", return_value=None)
    def test_scrape_error_continues(
        self, mock_resolve_body, mock_load_meeting, mock_ingest, mock_scrape, mock_discover, mock_session,
    ):
        """Scrape errors for one meeting don't stop processing others."""
        from data_sync import sync_escribemeetings
        from factories import make_escribemeetings_raw

        mock_session.return_value = MagicMock()
        mock_discover.return_value = [
            make_escribemeetings_raw(date="2026/03/03", guid="abc"),
            make_escribemeetings_raw(date="2026/03/10", guid="def"),
        ]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None  # No existing meetings
        mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_scrape.side_effect = [
            RuntimeError("scrape failed"),
            {"meeting_date": "2026-03-10", "meeting_name": "CC",
             "meeting_url": "https://x.com", "items": []},
        ]
        mock_ingest.return_value = uuid.uuid4()

        result = sync_escribemeetings(
            conn=mock_conn,
            city_fips="0660620",
            sync_type="full",
        )

        assert result["records_fetched"] == 2
        assert result["records_new"] == 1

    @patch("escribemeetings_scraper.create_session")
    @patch("escribemeetings_scraper.discover_meetings")
    @patch("escribemeetings_scraper.scrape_meeting")
    @patch("db.ingest_document")
    @patch("db.load_meeting_to_db")
    def test_incremental_filters_by_start_date(
        self, mock_load_meeting, mock_ingest, mock_scrape, mock_discover, mock_session,
    ):
        """Incremental sync filters raw API results using StartDate field."""
        from data_sync import sync_escribemeetings
        from factories import make_escribemeetings_raw

        mock_session.return_value = MagicMock()

        # today's meeting should be included, old one should not
        today = datetime.now().strftime("%Y/%m/%d")
        mock_discover.return_value = [
            make_escribemeetings_raw(date="2024/01/15", guid="old"),
            make_escribemeetings_raw(date=today, guid="new"),
        ]

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchone.return_value = None
        mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        mock_scrape.return_value = {
            "meeting_date": today.replace("/", "-"),
            "meeting_name": "City Council",
            "meeting_url": "https://example.com",
            "items": [],
        }
        mock_ingest.return_value = uuid.uuid4()

        result = sync_escribemeetings(
            conn=mock_conn,
            city_fips="0660620",
            sync_type="incremental",
        )

        # Only today's meeting passes the 14-day filter
        assert result["records_fetched"] == 1
        assert result["records_new"] == 1
        assert mock_scrape.call_count == 1


# ── NextRequest source tests ──────────────────────────────────

class TestSyncNextrequest:
    """Test NextRequest sync function registration and dispatch."""

    def test_nextrequest_registered(self):
        from data_sync import SYNC_SOURCES
        assert "nextrequest" in SYNC_SOURCES

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_nextrequest_dispatches(
        self, mock_complete, mock_create, mock_conn,
    ):
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(return_value={
            "records_fetched": 25, "records_new": 5, "records_updated": 2,
        })

        with patch.dict(SYNC_SOURCES, {"nextrequest": fake_sync}):
            result = run_sync(source="nextrequest")

        fake_sync.assert_called_once()
        assert result["status"] == "completed"
        assert result["records_fetched"] == 25


# ── Archive Center source tests ───────────────────────────────

class TestSyncArchiveCenter:
    """Test Archive Center sync function registration and dispatch."""

    def test_archive_center_registered(self):
        from data_sync import SYNC_SOURCES
        assert "archive_center" in SYNC_SOURCES

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_archive_center_dispatches(
        self, mock_complete, mock_create, mock_conn,
    ):
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(return_value={
            "records_fetched": 100, "records_new": 50, "records_updated": 0,
        })

        with patch.dict(SYNC_SOURCES, {"archive_center": fake_sync}):
            result = run_sync(source="archive_center")

        fake_sync.assert_called_once()
        assert result["status"] == "completed"


# ── sync_minutes_extraction logic ─────────────────────────────
#
# sync_minutes_extraction uses lazy imports for pipeline.extract_with_tool_use,
# db.save_extraction_run, and db.load_meeting_to_db. Patch at source module level.

class TestSyncMinutesExtraction:
    """Test minutes extraction sync function."""

    def test_minutes_extraction_registered(self):
        from data_sync import SYNC_SOURCES
        assert "minutes_extraction" in SYNC_SOURCES

    @patch("data_sync.get_connection")
    @patch("data_sync.create_sync_log")
    @patch("data_sync.complete_sync_log")
    def test_minutes_extraction_dispatches(
        self, mock_complete, mock_create, mock_conn,
    ):
        from data_sync import run_sync, SYNC_SOURCES

        mock_conn.return_value = MagicMock()
        mock_create.return_value = uuid.uuid4()
        fake_sync = MagicMock(return_value={
            "records_fetched": 5, "records_new": 3, "records_updated": 0,
        })

        with patch.dict(SYNC_SOURCES, {"minutes_extraction": fake_sync}):
            result = run_sync(source="minutes_extraction")

        fake_sync.assert_called_once()
        assert result["status"] == "completed"

    def test_incremental_skips_already_extracted(self):
        """Incremental mode returns 0 records when all docs already extracted."""
        from data_sync import sync_minutes_extraction

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = []  # no unextracted docs
        mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = sync_minutes_extraction(mock_conn, "0660620")

        assert result["records_fetched"] == 0
        assert result["records_new"] == 0

    @patch("pipeline.extract_with_tool_use")
    @patch("db.save_extraction_run")
    @patch("db.load_meeting_to_db")
    def test_extracts_and_loads_document(
        self, mock_load, mock_save_run, mock_extract,
    ):
        """Processes a document through extraction and Layer 2 loading."""
        from data_sync import sync_minutes_extraction

        doc_id = uuid.uuid4()
        mock_extract.return_value = (
            {"meeting_date": "2025-01-15", "action_items": [], "consent_calendar": {"items": []}},
            {"input_tokens": 10000, "output_tokens": 8000},
        )
        mock_save_run.return_value = uuid.uuid4()

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (doc_id, {"amid": 31, "date": "2025-01-15", "title": "Council Minutes"}),
        ]
        # Lazy-load of raw_text per document returns a single-row tuple
        mock_cursor.fetchone.return_value = ("ROLL CALL... meeting minutes text",)
        mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = sync_minutes_extraction(mock_conn, "0660620")

        assert result["records_fetched"] == 1
        assert result["records_new"] == 1
        mock_extract.assert_called_once()
        mock_save_run.assert_called_once()
        mock_load.assert_called_once()

        # Verify cost tracking was passed through
        save_call_kwargs = mock_save_run.call_args
        assert save_call_kwargs[1]["input_tokens"] == 10000
        assert save_call_kwargs[1]["output_tokens"] == 8000

    def test_skips_comment_compilations(self):
        """Documents with known comment compilation ADIDs are skipped."""
        from data_sync import sync_minutes_extraction

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        # Return a doc with a known comment compilation ADID
        mock_cursor.fetchall.return_value = [
            (uuid.uuid4(), {"amid": 31, "adid": "17313", "date": "2025-01-15", "title": "Public Comments"}),
        ]
        mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = sync_minutes_extraction(mock_conn, "0660620")

        assert result["records_fetched"] == 0  # filtered out
        assert result["records_new"] == 0

    @patch("pipeline.extract_with_tool_use")
    @patch("db.save_extraction_run")
    @patch("db.load_meeting_to_db")
    def test_extraction_error_continues(
        self, mock_load, mock_save_run, mock_extract,
    ):
        """Extraction errors are counted but don't stop processing."""
        from data_sync import sync_minutes_extraction

        mock_extract.side_effect = Exception("API timeout")

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (uuid.uuid4(), {"amid": 31, "date": "2025-01-15", "title": "Minutes"}),
        ]
        # Lazy-load of raw_text per document
        mock_cursor.fetchone.return_value = ("text",)
        mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = sync_minutes_extraction(mock_conn, "0660620")

        assert result["errors"] == 1
        assert result["records_new"] == 0
        assert "API timeout" in result["error_details"][0]
        mock_load.assert_not_called()


# ── Batch extraction ────────────────────────────────────────


class TestBatchExtraction:
    """Tests for the Batch API extraction path."""

    @patch("pipeline.submit_extraction_batch")
    @patch("pipeline.build_batch_request")
    def test_submit_builds_requests_and_submits(
        self, mock_build, mock_submit,
    ):
        """submit_minutes_batch builds a request per doc and submits the batch."""
        from data_sync import submit_minutes_batch

        doc_id = uuid.uuid4()
        mock_build.return_value = {"custom_id": str(doc_id), "params": {}}
        mock_submit.return_value = "msgbatch_test123"

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (doc_id, {"amid": 31, "date": "2025-01-15", "title": "Minutes"}),
        ]
        mock_cursor.fetchone.return_value = ("Meeting text here",)
        mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = submit_minutes_batch(mock_conn, "0660620")

        assert result["batch_id"] == "msgbatch_test123"
        assert result["documents_submitted"] == 1
        mock_build.assert_called_once_with(str(doc_id), "Meeting text here")
        mock_submit.assert_called_once()

    @patch("pipeline.submit_extraction_batch")
    @patch("pipeline.build_batch_request")
    def test_submit_skips_comment_compilations(
        self, mock_build, mock_submit,
    ):
        """Comment compilation ADIDs are filtered out before batch submit."""
        from data_sync import submit_minutes_batch

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_cursor.fetchall.return_value = [
            (uuid.uuid4(), {"amid": 31, "adid": "17313", "date": "2025-01-15", "title": "Comments"}),
        ]
        mock_conn.cursor.return_value.__enter__ = lambda self: mock_cursor
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        result = submit_minutes_batch(mock_conn, "0660620")

        assert result["documents_submitted"] == 0
        assert result["batch_id"] is None
        mock_submit.assert_not_called()

    @patch("pipeline.collect_batch_results")
    @patch("pipeline.check_batch_status")
    @patch("db.load_meeting_to_db")
    @patch("db.save_extraction_run")
    def test_collect_processes_succeeded_results(
        self, mock_save_run, mock_load, mock_status, mock_results,
    ):
        """collect_minutes_batch processes succeeded results into Layer 2."""
        from data_sync import collect_minutes_batch

        doc_id = str(uuid.uuid4())
        mock_status.return_value = {
            "processing_status": "ended",
            "request_counts": {
                "succeeded": 1, "errored": 0, "canceled": 0, "expired": 0,
                "processing": 0,
            },
        }
        mock_results.return_value = iter([
            (doc_id,
             {"meeting_date": "2025-01-15", "action_items": [],
              "consent_calendar": {"items": []}},
             {"input_tokens": 10000, "output_tokens": 8000}),
        ])
        mock_save_run.return_value = uuid.uuid4()

        mock_conn = MagicMock()

        result = collect_minutes_batch(mock_conn, "msgbatch_123", "0660620")

        assert result["records_new"] == 1
        assert result["errors"] == 0
        mock_save_run.assert_called_once()
        mock_load.assert_called_once()

        # Verify batch pricing was used (50% of standard)
        save_kwargs = mock_save_run.call_args[1]
        assert save_kwargs["prompt_version"] == "extraction_v1_batch"

    @patch("pipeline.check_batch_status")
    def test_collect_returns_early_if_not_ended(self, mock_status):
        """collect_minutes_batch returns early if batch is still processing."""
        from data_sync import collect_minutes_batch

        mock_status.return_value = {
            "processing_status": "in_progress",
            "request_counts": {
                "succeeded": 5, "errored": 0, "canceled": 0, "expired": 0,
                "processing": 705,
            },
        }
        mock_conn = MagicMock()

        result = collect_minutes_batch(mock_conn, "msgbatch_123", "0660620")

        assert result["status"] == "in_progress"
        assert "records_new" not in result


# ── sync_socrata_payroll ──────────────────────────────────────

class TestSyncSocrataPayroll:
    """Test Socrata payroll sync function."""

    def test_registered(self):
        from data_sync import SYNC_SOURCES
        assert "socrata_payroll" in SYNC_SOURCES

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
            "records_fetched": 5000, "records_new": 800, "records_updated": 0,
            "fiscal_years_processed": 1,
        })

        with patch.dict(SYNC_SOURCES, {"socrata_payroll": fake_sync}):
            result = run_sync(source="socrata_payroll")

        fake_sync.assert_called_once()
        assert result["status"] == "completed"
        assert result["records_fetched"] == 5000

    def test_incremental_fetches_current_year(self):
        """Incremental sync processes only the current fiscal year."""
        from data_sync import sync_socrata_payroll

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        sample_rows = [
            {
                "employeeid": "1234", "firstname": "JANE", "lastname": "DOE",
                "position": "CITY MANAGER", "department": "CITY MANAGER",
                "basepay": "15000.00", "totalpay": "18000.00",
                "fiscalyear": "2026", "positiontype": "FULL TIME PERMANENT",
            },
        ]

        with patch("payroll_ingester.fetch_payroll", return_value=sample_rows) as mock_fetch, \
             patch("payroll_ingester.parse_payroll_records") as mock_parse:
            mock_parse.return_value = [{
                "city_fips": "0660620", "name": "Jane Doe",
                "normalized_name": "jane doe", "job_title": "CITY MANAGER",
                "department": "CITY MANAGER", "is_department_head": True,
                "hierarchy_level": 1, "annual_salary": 15000.0,
                "total_compensation": 18000.0, "fiscal_year": "2026",
                "is_current": True, "source": "socrata_payroll",
                "socrata_record_id": "1234",
            }]
            result = sync_socrata_payroll(mock_conn, "0660620", "incremental")

        assert result["records_fetched"] == 1
        assert result["records_new"] == 1
        assert result["fiscal_years_processed"] == 1
        # Incremental = only current year
        mock_fetch.assert_called_once()

    def test_full_sync_fetches_multiple_years(self):
        """Full sync processes multiple fiscal years."""
        from data_sync import sync_socrata_payroll

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("payroll_ingester.fetch_payroll", return_value=[]) as mock_fetch, \
             patch("payroll_ingester.parse_payroll_records", return_value=[]):
            result = sync_socrata_payroll(mock_conn, "0660620", "full")

        assert result["fiscal_years_processed"] == 5
        assert mock_fetch.call_count == 5

    def test_empty_results_returns_zeros(self):
        """Empty Socrata response returns zero counts."""
        from data_sync import sync_socrata_payroll

        mock_conn = MagicMock()

        with patch("payroll_ingester.fetch_payroll", return_value=[]), \
             patch("payroll_ingester.parse_payroll_records", return_value=[]):
            result = sync_socrata_payroll(mock_conn, "0660620", "incremental")

        assert result["records_fetched"] == 0
        assert result["records_new"] == 0


# ── sync_socrata_expenditures ─────────────────────────────────

class TestSyncSocrataExpenditures:
    """Test Socrata expenditures sync function."""

    def test_registered(self):
        from data_sync import SYNC_SOURCES
        assert "socrata_expenditures" in SYNC_SOURCES

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
            "records_fetched": 10000, "records_new": 10000,
            "records_updated": 0, "fiscal_years_processed": 1,
        })

        with patch.dict(SYNC_SOURCES, {"socrata_expenditures": fake_sync}):
            result = run_sync(source="socrata_expenditures")

        fake_sync.assert_called_once()
        assert result["status"] == "completed"
        assert result["records_fetched"] == 10000

    def test_incremental_fetches_current_year(self):
        """Incremental sync processes only the current fiscal year."""
        from data_sync import sync_socrata_expenditures

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        sample_rows = [
            {
                ":id": "row-abc-123",
                "vendorname": "ACME SUPPLIES",
                "actual": "5000.00",
                "description": "Office supplies",
                "organization": "PUBLIC WORKS",
                "date": "2026-03-01T00:00:00.000",
                "fund": "GENERAL FUND",
                "fiscalyear": "2026",
            },
        ]

        mock_cursor.fetchone.return_value = (True,)  # inserted

        with patch("socrata_client.query_dataset", return_value=sample_rows) as mock_query:
            result = sync_socrata_expenditures(mock_conn, "0660620", "incremental")

        assert result["records_fetched"] == 1
        assert result["records_new"] == 1
        assert result["records_updated"] == 0
        assert result["fiscal_years_processed"] == 1

    def test_full_sync_fetches_multiple_years(self):
        """Full sync processes multiple fiscal years."""
        from data_sync import sync_socrata_expenditures

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        with patch("socrata_client.query_dataset", return_value=[]) as mock_query:
            result = sync_socrata_expenditures(mock_conn, "0660620", "full")

        assert result["fiscal_years_processed"] == 5
        # 5 fiscal years, each with one empty call
        assert mock_query.call_count == 5

    def test_empty_results_returns_zeros(self):
        """Empty Socrata response returns zero counts."""
        from data_sync import sync_socrata_expenditures

        mock_conn = MagicMock()

        with patch("socrata_client.query_dataset", return_value=[]):
            result = sync_socrata_expenditures(mock_conn, "0660620", "incremental")

        assert result["records_fetched"] == 0
        assert result["records_new"] == 0
        assert result["records_updated"] == 0

    def test_pagination_loops(self):
        """Handles Socrata pagination when results exceed batch size."""
        from data_sync import sync_socrata_expenditures

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (True,)

        # First call returns full batch, second returns partial (end of data)
        batch_1 = [{":id": f"row-{i}", "vendorname": f"V{i}", "actual": "100",
                     "description": "", "organization": "", "date": None,
                     "fund": "", "fiscalyear": "2026"} for i in range(50000)]
        batch_2 = [{":id": "row-final", "vendorname": "LAST", "actual": "50",
                     "description": "", "organization": "", "date": None,
                     "fund": "", "fiscalyear": "2026"}]

        with patch("socrata_client.query_dataset", side_effect=[batch_1, batch_2]):
            result = sync_socrata_expenditures(mock_conn, "0660620", "incremental")

        assert result["records_fetched"] == 50001
        assert result["records_new"] == 50001

    def test_synthetic_row_id_fallback(self):
        """Uses synthetic ID when Socrata :id is missing."""
        from data_sync import sync_socrata_expenditures

        mock_conn = MagicMock()
        mock_cursor = MagicMock()
        mock_conn.cursor.return_value.__enter__ = MagicMock(return_value=mock_cursor)
        mock_conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
        mock_cursor.fetchone.return_value = (True,)

        row_without_id = {
            "vendorname": "TEST VENDOR", "actual": "999.99",
            "description": "Test", "organization": "FINANCE",
            "date": "2026-01-15T00:00:00.000", "fund": "GENERAL",
            "fiscalyear": "2026",
        }

        with patch("socrata_client.query_dataset", return_value=[row_without_id]):
            result = sync_socrata_expenditures(mock_conn, "0660620", "incremental")

        assert result["records_new"] == 1
        # Verify the synthetic ID was constructed
        insert_call = mock_cursor.execute.call_args
        params = insert_call[0][1]
        socrata_row_id = params[-1]  # last param
        assert "2026:" in socrata_row_id
        assert "TEST VENDOR" in socrata_row_id


# ── _normalize_vendor_name ────────────────────────────────────

class TestNormalizeVendorName:
    """Test vendor name normalization."""

    def test_basic_normalization(self):
        from data_sync import _normalize_vendor_name
        assert _normalize_vendor_name("ACME  SUPPLIES  INC") == "acme supplies inc"

    def test_empty_string(self):
        from data_sync import _normalize_vendor_name
        assert _normalize_vendor_name("") == ""

    def test_none_returns_empty(self):
        from data_sync import _normalize_vendor_name
        assert _normalize_vendor_name(None) == ""

    def test_preserves_content(self):
        from data_sync import _normalize_vendor_name
        assert _normalize_vendor_name("O'Reilly & Associates") == "o'reilly & associates"
