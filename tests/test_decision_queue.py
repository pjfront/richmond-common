"""Tests for the operator decision queue (S7)."""

import uuid
from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock, patch, call

import psycopg2.errors
import pytest

from decision_queue import (
    create_decision,
    resolve_decision,
    get_pending,
    get_recently_resolved,
    get_decision_summary,
    get_decision_briefing,
    VALID_TYPES,
    VALID_SEVERITIES,
    VALID_VERDICTS,
    _format_age,
)


# ── Helpers ──────────────────────────────────────────────────


def _mock_conn():
    """Create a mock DB connection with cursor context manager."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = lambda self: cursor
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


def _sample_decision(**overrides) -> dict:
    """Build a sample decision dict."""
    base = {
        "id": str(uuid.uuid4()),
        "city_fips": "0660620",
        "decision_type": "staleness_alert",
        "severity": "medium",
        "title": "NetFile data is 21 days stale",
        "description": "Last sync 21 days ago, threshold is 14 days.",
        "evidence": {"days_since_sync": 21, "threshold_days": 14},
        "source": "staleness_monitor",
        "entity_type": None,
        "entity_id": None,
        "link": "https://rtp-gray.vercel.app/data-quality",
        "dedup_key": "staleness:netfile",
        "status": "pending",
        "created_at": datetime.now(timezone.utc) - timedelta(days=3),
        "updated_at": datetime.now(timezone.utc) - timedelta(days=3),
    }
    base.update(overrides)
    return base


# ── Validation Tests ─────────────────────────────────────────


class TestValidation:
    """Validate inputs before DB calls."""

    @patch("decision_queue.insert_pending_decision")
    def test_invalid_decision_type_raises(self, mock_insert):
        conn, _ = _mock_conn()
        with pytest.raises(ValueError, match="Invalid decision_type"):
            create_decision(
                conn, city_fips="0660620",
                decision_type="bad_type",
                severity="medium",
                title="Test",
                description="Test",
                source="test",
            )
        mock_insert.assert_not_called()

    @patch("decision_queue.insert_pending_decision")
    def test_invalid_severity_raises(self, mock_insert):
        conn, _ = _mock_conn()
        with pytest.raises(ValueError, match="Invalid severity"):
            create_decision(
                conn, city_fips="0660620",
                decision_type="general",
                severity="extreme",
                title="Test",
                description="Test",
                source="test",
            )
        mock_insert.assert_not_called()

    @patch("decision_queue.update_decision_status")
    def test_invalid_verdict_raises(self, mock_update):
        conn, _ = _mock_conn()
        with pytest.raises(ValueError, match="Invalid verdict"):
            resolve_decision(conn, str(uuid.uuid4()), verdict="maybe")
        mock_update.assert_not_called()


# ── Create Tests ─────────────────────────────────────────────


class TestCreateDecision:
    """create_decision delegates to db layer with validation."""

    @patch("decision_queue.insert_pending_decision")
    def test_create_returns_uuid(self, mock_insert):
        expected_id = uuid.uuid4()
        mock_insert.return_value = expected_id
        conn, _ = _mock_conn()

        result = create_decision(
            conn, city_fips="0660620",
            decision_type="staleness_alert",
            severity="medium",
            title="NetFile stale",
            description="21 days since last sync",
            source="staleness_monitor",
            dedup_key="staleness:netfile",
        )

        assert result == expected_id
        mock_insert.assert_called_once()
        call_kwargs = mock_insert.call_args.kwargs
        assert call_kwargs["decision_type"] == "staleness_alert"
        assert call_kwargs["severity"] == "medium"
        assert call_kwargs["dedup_key"] == "staleness:netfile"

    @patch("decision_queue.insert_pending_decision")
    def test_create_dedup_returns_none(self, mock_insert):
        mock_insert.return_value = None  # deduped
        conn, _ = _mock_conn()

        result = create_decision(
            conn, city_fips="0660620",
            decision_type="staleness_alert",
            severity="medium",
            title="NetFile stale",
            description="Duplicate",
            source="staleness_monitor",
            dedup_key="staleness:netfile",
        )

        assert result is None

    @patch("decision_queue.insert_pending_decision")
    def test_create_without_dedup_key(self, mock_insert):
        expected_id = uuid.uuid4()
        mock_insert.return_value = expected_id
        conn, _ = _mock_conn()

        result = create_decision(
            conn, city_fips="0660620",
            decision_type="general",
            severity="info",
            title="Manual note",
            description="Something to track",
            source="manual",
        )

        assert result == expected_id
        call_kwargs = mock_insert.call_args.kwargs
        assert call_kwargs["dedup_key"] is None

    @patch("decision_queue.insert_pending_decision")
    def test_create_passes_all_fields(self, mock_insert):
        mock_insert.return_value = uuid.uuid4()
        conn, _ = _mock_conn()

        create_decision(
            conn, city_fips="0660620",
            decision_type="anomaly",
            severity="high",
            title="Low item count",
            description="5 items vs average 25",
            source="completeness_monitor",
            evidence={"current": 5, "average": 25},
            entity_type="meeting",
            entity_id="abc-123",
            link="https://rtp-gray.vercel.app/meetings/abc-123",
            dedup_key="anomaly:abc-123:low_item_count",
        )

        call_kwargs = mock_insert.call_args.kwargs
        assert call_kwargs["entity_type"] == "meeting"
        assert call_kwargs["entity_id"] == "abc-123"
        assert call_kwargs["evidence"] == {"current": 5, "average": 25}
        assert call_kwargs["link"] == "https://rtp-gray.vercel.app/meetings/abc-123"


# ── Resolve Tests ────────────────────────────────────────────


class TestResolveDecision:
    """resolve_decision updates status with verdict."""

    @patch("decision_queue.update_decision_status")
    def test_resolve_approved(self, mock_update):
        mock_update.return_value = True
        conn, _ = _mock_conn()

        result = resolve_decision(
            conn, str(uuid.uuid4()), verdict="approved",
            note="Triggered manual sync",
        )

        assert result is True
        call_kwargs = mock_update.call_args.kwargs
        assert call_kwargs["status"] == "approved"
        assert call_kwargs["resolved_by"] == "operator"
        assert call_kwargs["resolution_note"] == "Triggered manual sync"

    @patch("decision_queue.update_decision_status")
    def test_resolve_rejected(self, mock_update):
        mock_update.return_value = True
        conn, _ = _mock_conn()

        result = resolve_decision(conn, str(uuid.uuid4()), verdict="rejected")
        assert result is True

    @patch("decision_queue.update_decision_status")
    def test_resolve_deferred(self, mock_update):
        mock_update.return_value = True
        conn, _ = _mock_conn()

        result = resolve_decision(
            conn, str(uuid.uuid4()), verdict="deferred",
            note="Will revisit next week",
        )
        assert result is True

    @patch("decision_queue.update_decision_status")
    def test_resolve_nonexistent_returns_false(self, mock_update):
        mock_update.return_value = False
        conn, _ = _mock_conn()

        result = resolve_decision(conn, str(uuid.uuid4()), verdict="approved")
        assert result is False

    @patch("decision_queue.update_decision_status")
    def test_resolve_accepts_string_uuid(self, mock_update):
        """String UUIDs are converted to uuid.UUID."""
        mock_update.return_value = True
        conn, _ = _mock_conn()
        id_str = str(uuid.uuid4())

        resolve_decision(conn, id_str, verdict="approved")

        call_kwargs = mock_update.call_args.kwargs
        assert isinstance(call_kwargs["decision_id"], uuid.UUID)


# ── Query Tests ──────────────────────────────────────────────


class TestQueryDecisions:
    """get_pending and get_recently_resolved query the DB layer."""

    @patch("decision_queue.query_pending_decisions")
    def test_get_pending_delegates(self, mock_query):
        mock_query.return_value = [_sample_decision()]
        conn, _ = _mock_conn()

        result = get_pending(conn, "0660620")
        assert len(result) == 1
        mock_query.assert_called_once_with(
            conn, "0660620", decision_type=None, severity=None,
        )

    @patch("decision_queue.query_pending_decisions")
    def test_get_pending_with_filters(self, mock_query):
        mock_query.return_value = []
        conn, _ = _mock_conn()

        get_pending(conn, "0660620", decision_type="anomaly", severity="high")
        mock_query.assert_called_once_with(
            conn, "0660620", decision_type="anomaly", severity="high",
        )

    @patch("decision_queue.query_resolved_decisions")
    def test_get_recently_resolved(self, mock_query):
        mock_query.return_value = []
        conn, _ = _mock_conn()

        get_recently_resolved(conn, "0660620", days=14, limit=10)
        mock_query.assert_called_once_with(
            conn, "0660620", days=14, limit=10,
        )


# ── Summary Tests ────────────────────────────────────────────


class TestDecisionSummary:

    @patch("decision_queue.count_decisions_by_severity")
    def test_summary_counts(self, mock_count):
        mock_count.return_value = {
            "critical": 0, "high": 1, "medium": 2, "low": 0, "info": 0,
        }
        conn, _ = _mock_conn()

        summary = get_decision_summary(conn, "0660620")
        assert summary["total_pending"] == 3
        assert summary["counts"]["high"] == 1
        assert summary["counts"]["medium"] == 2

    @patch("decision_queue.count_decisions_by_severity")
    def test_summary_empty(self, mock_count):
        mock_count.return_value = {
            "critical": 0, "high": 0, "medium": 0, "low": 0, "info": 0,
        }
        conn, _ = _mock_conn()

        summary = get_decision_summary(conn, "0660620")
        assert summary["total_pending"] == 0


# ── Briefing Formatter Tests ─────────────────────────────────


class TestDecisionBriefing:

    @patch("decision_queue.get_pending")
    @patch("decision_queue.get_decision_summary")
    def test_briefing_empty(self, mock_summary, mock_pending):
        mock_summary.return_value = {"total_pending": 0, "counts": {}}
        mock_pending.return_value = []
        conn, _ = _mock_conn()

        briefing = get_decision_briefing(conn, "0660620")
        assert "No pending decisions" in briefing

    @patch("decision_queue.get_pending")
    @patch("decision_queue.get_decision_summary")
    def test_briefing_with_decisions(self, mock_summary, mock_pending):
        mock_summary.return_value = {
            "total_pending": 2,
            "counts": {"high": 1, "medium": 1, "critical": 0, "low": 0, "info": 0},
        }
        mock_pending.return_value = [
            _sample_decision(severity="high", title="Critical alert"),
            _sample_decision(severity="medium", title="Minor issue"),
        ]
        conn, _ = _mock_conn()

        briefing = get_decision_briefing(conn, "0660620")
        assert "Pending: 2" in briefing
        assert "Critical alert" in briefing
        assert "Minor issue" in briefing
        assert "HIGH" in briefing
        assert "MEDIUM" in briefing

    @patch("decision_queue.get_pending")
    @patch("decision_queue.get_decision_summary")
    def test_briefing_includes_link(self, mock_summary, mock_pending):
        mock_summary.return_value = {
            "total_pending": 1,
            "counts": {"medium": 1, "critical": 0, "high": 0, "low": 0, "info": 0},
        }
        mock_pending.return_value = [
            _sample_decision(link="https://rtp-gray.vercel.app/data-quality"),
        ]
        conn, _ = _mock_conn()

        briefing = get_decision_briefing(conn, "0660620")
        assert "https://rtp-gray.vercel.app/data-quality" in briefing

    @patch("decision_queue.get_recently_resolved")
    @patch("decision_queue.get_pending")
    @patch("decision_queue.get_decision_summary")
    def test_briefing_with_resolved(self, mock_summary, mock_pending, mock_resolved):
        mock_summary.return_value = {
            "total_pending": 1,
            "counts": {"info": 1, "critical": 0, "high": 0, "medium": 0, "low": 0},
        }
        mock_pending.return_value = [_sample_decision(severity="info")]
        mock_resolved.return_value = [
            _sample_decision(
                status="approved",
                resolved_at=datetime.now(timezone.utc),
                resolution_note="Fixed it",
            ),
        ]
        conn, _ = _mock_conn()

        briefing = get_decision_briefing(conn, "0660620", include_resolved=True)
        assert "RECENTLY RESOLVED" in briefing
        assert "Fixed it" in briefing

    @patch("decision_queue.get_pending")
    @patch("decision_queue.get_decision_summary")
    def test_briefing_truncates_long_description(self, mock_summary, mock_pending):
        mock_summary.return_value = {
            "total_pending": 1,
            "counts": {"medium": 1, "critical": 0, "high": 0, "low": 0, "info": 0},
        }
        long_desc = "A" * 200
        mock_pending.return_value = [_sample_decision(description=long_desc)]
        conn, _ = _mock_conn()

        briefing = get_decision_briefing(conn, "0660620")
        assert "..." in briefing
        assert "A" * 200 not in briefing


# ── Age Formatting Tests ─────────────────────────────────────


class TestFormatAge:

    def test_days_ago(self):
        ts = datetime.now(timezone.utc) - timedelta(days=3)
        assert _format_age(ts) == "3 days ago"

    def test_one_day_ago(self):
        ts = datetime.now(timezone.utc) - timedelta(days=1, hours=2)
        assert _format_age(ts) == "1 day ago"

    def test_hours_ago(self):
        ts = datetime.now(timezone.utc) - timedelta(hours=5)
        assert _format_age(ts) == "5 hours ago"

    def test_just_now(self):
        ts = datetime.now(timezone.utc) - timedelta(minutes=30)
        assert _format_age(ts) == "just now"

    def test_string_input(self):
        ts = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
        assert "2 days ago" in _format_age(ts)

    def test_naive_datetime(self):
        ts = datetime.now() - timedelta(days=1, hours=2)
        assert _format_age(ts) == "1 day ago"
