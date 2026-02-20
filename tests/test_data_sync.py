"""Tests for the unified data source sync module."""
import json
import uuid
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
            result = run_sync(source="netfile")

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
    def test_skips_existing_meetings(
        self, mock_ingest, mock_scrape, mock_discover, mock_session,
    ):
        """Meetings already in documents table are skipped."""
        from data_sync import sync_escribemeetings

        mock_session.return_value = MagicMock()
        mock_discover.return_value = [
            {"meeting_date": "2026-03-03", "ID": "abc"},
            {"meeting_date": "2026-03-10", "ID": "def"},
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
    def test_scrape_error_continues(
        self, mock_ingest, mock_scrape, mock_discover, mock_session,
    ):
        """Scrape errors for one meeting don't stop processing others."""
        from data_sync import sync_escribemeetings

        mock_session.return_value = MagicMock()
        mock_discover.return_value = [
            {"meeting_date": "2026-03-03", "ID": "abc"},
            {"meeting_date": "2026-03-10", "ID": "def"},
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
