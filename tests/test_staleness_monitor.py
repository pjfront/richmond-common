"""Tests for staleness_monitor.py schema health check."""
from unittest.mock import MagicMock

from staleness_monitor import (
    check_schema_health,
    format_schema_report,
    EXPECTED_TABLES,
)


# ── Helpers ──────────────────────────────────────────────────

def _make_conn(existing_tables: set[str]):
    """Create a mock connection that returns specific tables from information_schema."""
    conn = MagicMock()
    cursor = MagicMock()
    cursor.fetchall.return_value = [(t,) for t in existing_tables]
    conn.cursor.return_value.__enter__ = lambda self: cursor
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn


def _all_expected_tables() -> set[str]:
    """Return the full set of expected tables across all migrations."""
    tables = set()
    for group_tables in EXPECTED_TABLES.values():
        tables.update(group_tables)
    return tables


# ── check_schema_health ─────────────────────────────────────

class TestCheckSchemaHealth:
    def test_healthy_when_all_tables_present(self):
        conn = _make_conn(_all_expected_tables())
        result = check_schema_health(conn)

        assert result["status"] == "healthy"
        for group in EXPECTED_TABLES:
            assert result["migrations"][group]["applied"] is True

    def test_degraded_when_migration_tables_missing(self):
        """Core schema present but migration 003 tables missing → degraded."""
        all_tables = _all_expected_tables()
        all_tables.discard("nextrequest_requests")
        all_tables.discard("nextrequest_documents")
        conn = _make_conn(all_tables)

        result = check_schema_health(conn)

        assert result["status"] == "degraded"
        assert result["migrations"]["core_schema"]["applied"] is True
        assert result["migrations"]["003_nextrequest"]["applied"] is False
        assert "nextrequest_requests" in result["migrations"]["003_nextrequest"]["missing"]

    def test_unhealthy_when_core_tables_missing(self):
        """Missing core schema tables → unhealthy."""
        conn = _make_conn({"scan_runs", "data_sync_log"})

        result = check_schema_health(conn)

        assert result["status"] == "unhealthy"
        assert result["migrations"]["core_schema"]["applied"] is False
        assert "cities" in result["migrations"]["core_schema"]["missing"]

    def test_unhealthy_when_no_tables_exist(self):
        conn = _make_conn(set())

        result = check_schema_health(conn)

        assert result["status"] == "unhealthy"
        for group in EXPECTED_TABLES:
            assert result["migrations"][group]["applied"] is False

    def test_partial_migration_reports_both_present_and_missing(self):
        """If only some tables from a migration exist, report both."""
        all_tables = _all_expected_tables()
        all_tables.discard("nextrequest_documents")  # remove one of two 003 tables
        conn = _make_conn(all_tables)

        result = check_schema_health(conn)

        m003 = result["migrations"]["003_nextrequest"]
        assert m003["applied"] is False
        assert "nextrequest_requests" in m003["tables"]
        assert "nextrequest_documents" in m003["missing"]


# ── format_schema_report ─────────────────────────────────────

class TestFormatSchemaReport:
    def test_healthy_report_shows_all_ok(self):
        health = {
            "status": "healthy",
            "migrations": {
                "core_schema": {"applied": True, "tables": ["cities"]},
                "001_cloud_pipeline": {"applied": True, "tables": ["scan_runs"]},
            },
        }
        text = format_schema_report(health)

        assert "Schema Health" in text
        assert "OK" in text
        assert "Overall: healthy" in text

    def test_alert_only_hides_healthy(self):
        health = {
            "status": "healthy",
            "migrations": {
                "core_schema": {"applied": True, "tables": ["cities"]},
            },
        }
        text = format_schema_report(health, alert_only=True)

        assert text == ""

    def test_degraded_report_shows_missing(self):
        health = {
            "status": "degraded",
            "migrations": {
                "core_schema": {"applied": True, "tables": ["cities"]},
                "003_nextrequest": {
                    "applied": False,
                    "missing": ["nextrequest_requests"],
                },
            },
        }
        text = format_schema_report(health)

        assert "MISSING" in text
        assert "nextrequest_requests" in text
        assert "Overall: degraded" in text

    def test_alert_only_shows_only_missing_groups(self):
        health = {
            "status": "degraded",
            "migrations": {
                "core_schema": {"applied": True, "tables": ["cities"]},
                "003_nextrequest": {
                    "applied": False,
                    "missing": ["nextrequest_requests"],
                },
            },
        }
        text = format_schema_report(health, alert_only=True)

        assert "core_schema" not in text
        assert "003_nextrequest" in text


# ── Auto-resolve staleness decisions ────────────────────────

class TestAutoResolveStaleness:
    """Test that staleness decisions are auto-resolved when sources become fresh."""

    def test_auto_resolve_clears_fresh_sources(self):
        """When a source is no longer stale, its pending decision should be resolved."""
        from staleness_monitor import _auto_resolve_staleness

        conn = MagicMock()
        cursor = MagicMock()
        cursor.rowcount = 2
        conn.cursor.return_value.__enter__ = lambda self: cursor
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        resolved = _auto_resolve_staleness(conn, "0660620", ["netfile", "calaccess"])

        assert resolved == 2
        # Verify the SQL was called with correct dedup keys
        call_args = cursor.execute.call_args
        sql = call_args[0][0]
        params = call_args[0][1]
        assert "status = 'approved'" in sql
        assert "resolved_by = 'auto:staleness_monitor'" in sql
        assert "staleness:netfile" in params
        assert "staleness:calaccess" in params
        conn.commit.assert_called_once()

    def test_auto_resolve_no_op_with_empty_list(self):
        """No-op when no fresh sources provided."""
        from staleness_monitor import _auto_resolve_staleness

        conn = MagicMock()
        resolved = _auto_resolve_staleness(conn, "0660620", [])

        assert resolved == 0
        conn.cursor.assert_not_called()

    def test_auto_resolve_returns_zero_when_none_pending(self):
        """Returns 0 when no pending decisions match."""
        from staleness_monitor import _auto_resolve_staleness

        conn = MagicMock()
        cursor = MagicMock()
        cursor.rowcount = 0
        conn.cursor.return_value.__enter__ = lambda self: cursor
        conn.cursor.return_value.__exit__ = MagicMock(return_value=False)

        resolved = _auto_resolve_staleness(conn, "0660620", ["netfile"])

        assert resolved == 0
