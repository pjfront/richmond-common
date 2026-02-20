"""Tests for the new db.py cloud pipeline helper functions.

These test the function signatures and SQL generation logic
by mocking the database connection/cursor.
"""
import json
import uuid
from datetime import date
from unittest.mock import patch, MagicMock, call

import pytest

from db import (
    create_scan_run,
    complete_scan_run,
    fail_scan_run,
    create_sync_log,
    complete_sync_log,
    save_conflict_flag,
    supersede_flags_for_meeting,
    run_migration,
)


# ── Helpers ──────────────────────────────────────────────────

def _make_conn():
    """Create a mock connection with cursor context manager."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = lambda self: cursor
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


# ── create_scan_run ──────────────────────────────────────────

class TestCreateScanRun:
    """Create a scan_runs row at pipeline start."""

    def test_returns_uuid(self):
        conn, cur = _make_conn()
        result = create_scan_run(conn, city_fips="0660620")
        assert isinstance(result, uuid.UUID)

    def test_inserts_with_correct_params(self):
        conn, cur = _make_conn()
        cutoff = date(2026, 3, 3)
        create_scan_run(
            conn,
            city_fips="0660620",
            scan_mode="prospective",
            data_cutoff_date=cutoff,
            triggered_by="n8n",
            pipeline_run_id="run-123",
            scanner_version="abc1234",
        )
        cur.execute.assert_called_once()
        sql = cur.execute.call_args[0][0]
        params = cur.execute.call_args[0][1]

        assert "INSERT INTO scan_runs" in sql
        assert params[1] == "0660620"  # city_fips
        assert params[3] == "prospective"  # scan_mode
        assert params[4] == cutoff  # data_cutoff_date
        assert params[8] == "n8n"  # triggered_by
        assert params[9] == "run-123"  # pipeline_run_id
        assert params[10] == "abc1234"  # scanner_version

    def test_commits_after_insert(self):
        conn, cur = _make_conn()
        create_scan_run(conn, city_fips="0660620")
        conn.commit.assert_called_once()

    def test_default_scan_mode_is_prospective(self):
        conn, cur = _make_conn()
        create_scan_run(conn, city_fips="0660620")
        params = cur.execute.call_args[0][1]
        assert params[3] == "prospective"


# ── complete_scan_run ────────────────────────────────────────

class TestCompleteScanRun:
    """Mark a scan_run as completed with results."""

    def test_updates_with_completed_status(self):
        conn, cur = _make_conn()
        run_id = uuid.uuid4()
        complete_scan_run(
            conn,
            scan_run_id=run_id,
            flags_found=3,
            flags_by_tier={"tier1": 0, "tier2": 1, "tier3": 2},
            clean_items_count=15,
            execution_time_seconds=12.5,
        )
        sql = cur.execute.call_args[0][0]
        params = cur.execute.call_args[0][1]

        assert "UPDATE scan_runs" in sql
        assert params[0] == 3  # flags_found
        assert json.loads(params[1]) == {"tier1": 0, "tier2": 1, "tier3": 2}
        assert params[2] == 15  # clean_items_count
        assert "completed" in params  # status

    def test_sets_failed_when_error_message(self):
        conn, cur = _make_conn()
        complete_scan_run(
            conn,
            scan_run_id=uuid.uuid4(),
            flags_found=0,
            flags_by_tier={},
            clean_items_count=0,
            error_message="something broke",
        )
        params = cur.execute.call_args[0][1]
        assert "failed" in params


# ── fail_scan_run ────────────────────────────────────────────

class TestFailScanRun:
    """Mark a scan_run as failed."""

    def test_sets_failed_status(self):
        conn, cur = _make_conn()
        run_id = uuid.uuid4()
        fail_scan_run(conn, run_id, "timeout exceeded")

        sql = cur.execute.call_args[0][0]
        params = cur.execute.call_args[0][1]
        assert "UPDATE scan_runs" in sql
        assert "failed" in sql
        assert params[0] == "timeout exceeded"
        assert params[1] == run_id

    def test_commits(self):
        conn, cur = _make_conn()
        fail_scan_run(conn, uuid.uuid4(), "error")
        conn.commit.assert_called_once()


# ── create_sync_log ──────────────────────────────────────────

class TestCreateSyncLog:
    """Create a data_sync_log row."""

    def test_returns_uuid(self):
        conn, cur = _make_conn()
        result = create_sync_log(conn, city_fips="0660620", source="netfile")
        assert isinstance(result, uuid.UUID)

    def test_inserts_correct_source(self):
        conn, cur = _make_conn()
        create_sync_log(
            conn,
            city_fips="0660620",
            source="calaccess",
            sync_type="full",
            triggered_by="github_actions",
            pipeline_run_id="run-456",
        )
        params = cur.execute.call_args[0][1]
        assert params[1] == "0660620"  # city_fips
        assert params[2] == "calaccess"  # source
        assert params[3] == "full"  # sync_type
        assert params[4] == "github_actions"  # triggered_by
        assert params[5] == "run-456"  # pipeline_run_id


# ── complete_sync_log ────────────────────────────────────────

class TestCompleteSyncLog:
    """Mark a sync log as completed or failed."""

    def test_completed_status(self):
        conn, cur = _make_conn()
        complete_sync_log(
            conn,
            sync_log_id=uuid.uuid4(),
            records_fetched=100,
            records_new=10,
            records_updated=5,
        )
        params = cur.execute.call_args[0][1]
        assert 100 in params  # records_fetched
        assert "completed" in params

    def test_failed_status_with_error(self):
        conn, cur = _make_conn()
        complete_sync_log(
            conn,
            sync_log_id=uuid.uuid4(),
            error_message="API returned 500",
        )
        params = cur.execute.call_args[0][1]
        assert "failed" in params
        assert "API returned 500" in params

    def test_metadata_serialized(self):
        conn, cur = _make_conn()
        complete_sync_log(
            conn,
            sync_log_id=uuid.uuid4(),
            metadata={"execution_seconds": 12.5, "extra": "data"},
        )
        params = cur.execute.call_args[0][1]
        # Find the JSON string in params
        json_params = [p for p in params if isinstance(p, str) and "execution_seconds" in p]
        assert len(json_params) == 1
        parsed = json.loads(json_params[0])
        assert parsed["execution_seconds"] == 12.5


# ── save_conflict_flag ───────────────────────────────────────

class TestSaveConflictFlag:
    """Insert a conflict_flag linked to a scan_run."""

    def test_returns_uuid(self):
        conn, cur = _make_conn()
        result = save_conflict_flag(
            conn,
            city_fips="0660620",
            meeting_id=uuid.uuid4(),
            scan_run_id=uuid.uuid4(),
            flag_type="campaign_contribution",
            description="Test flag",
            evidence=[{"amount": 500}],
            confidence=0.8,
        )
        assert isinstance(result, uuid.UUID)

    def test_inserts_with_is_current_true(self):
        conn, cur = _make_conn()
        save_conflict_flag(
            conn,
            city_fips="0660620",
            meeting_id=uuid.uuid4(),
            scan_run_id=uuid.uuid4(),
            flag_type="campaign_contribution",
            description="Flag desc",
            evidence=[],
            confidence=0.5,
            scan_mode="prospective",
            data_cutoff_date=date(2026, 3, 3),
        )
        sql = cur.execute.call_args[0][0]
        assert "is_current" in sql
        assert "TRUE" in sql

    def test_evidence_serialized_as_json(self):
        conn, cur = _make_conn()
        evidence = [{"donor": "Jane", "amount": 1000}]
        save_conflict_flag(
            conn,
            city_fips="0660620",
            meeting_id=uuid.uuid4(),
            scan_run_id=uuid.uuid4(),
            flag_type="campaign_contribution",
            description="Test",
            evidence=evidence,
            confidence=0.7,
        )
        params = cur.execute.call_args[0][1]
        # evidence is serialized via json.dumps
        json_params = [p for p in params if isinstance(p, str) and "donor" in p]
        assert len(json_params) == 1
        assert json.loads(json_params[0]) == evidence


# ── supersede_flags_for_meeting ──────────────────────────────

class TestSupersedeFlags:
    """Mark old flags as superseded by a new scan."""

    def test_returns_count_of_superseded(self):
        conn, cur = _make_conn()
        cur.rowcount = 5

        count = supersede_flags_for_meeting(
            conn,
            meeting_id=uuid.uuid4(),
            new_scan_run_id=uuid.uuid4(),
            scan_mode="prospective",
        )
        assert count == 5

    def test_only_supersedes_current_flags(self):
        conn, cur = _make_conn()
        cur.rowcount = 0

        supersede_flags_for_meeting(
            conn,
            meeting_id=uuid.uuid4(),
            new_scan_run_id=uuid.uuid4(),
        )
        sql = cur.execute.call_args[0][0]
        assert "is_current = TRUE" in sql
        assert "is_current = FALSE" in sql

    def test_excludes_current_scan_run(self):
        """New scan's own flags are NOT superseded."""
        conn, cur = _make_conn()
        cur.rowcount = 0
        new_id = uuid.uuid4()

        supersede_flags_for_meeting(conn, uuid.uuid4(), new_id)

        params = cur.execute.call_args[0][1]
        assert new_id in params


# ── run_migration ────────────────────────────────────────────

class TestRunMigration:
    """Run a SQL migration file."""

    def test_reads_and_executes_sql(self, tmp_path):
        conn, cur = _make_conn()
        migration = tmp_path / "001_test.sql"
        migration.write_text("CREATE TABLE test (id INT);")

        run_migration(conn, str(migration))

        cur.execute.assert_called_once_with("CREATE TABLE test (id INT);")
        conn.commit.assert_called_once()

    def test_handles_multi_statement_sql(self, tmp_path):
        conn, cur = _make_conn()
        migration = tmp_path / "002_multi.sql"
        sql = "CREATE TABLE a (id INT);\nCREATE TABLE b (id INT);"
        migration.write_text(sql)

        run_migration(conn, str(migration))

        cur.execute.assert_called_once_with(sql)
