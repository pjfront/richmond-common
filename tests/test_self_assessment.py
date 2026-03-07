"""Tests for self-assessment module."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from self_assessment import (
    build_assessment_context,
    _format_entries_for_prompt,
    run_self_assessment,
    format_decision_packet,
)


# ── Helpers ──────────────────────────────────────────────────


def _mock_conn():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = lambda self: cursor
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


def _sample_entries():
    """Return a realistic set of journal entries for testing."""
    now = datetime(2026, 3, 10, 14, 0, 0, tzinfo=timezone.utc)
    return [
        {
            "id": str(uuid.uuid4()),
            "city_fips": "0660620",
            "session_id": str(uuid.uuid4()),
            "entry_type": "run_started",
            "zone": "observation",
            "target_artifact": "cloud_pipeline",
            "description": "Pipeline for 2026-03-10",
            "metrics": {"run_id": "run-1", "scan_mode": "prospective"},
            "created_at": now,
        },
        {
            "id": str(uuid.uuid4()),
            "city_fips": "0660620",
            "session_id": str(uuid.uuid4()),
            "entry_type": "step_completed",
            "zone": "observation",
            "target_artifact": "scrape_escribemeetings",
            "description": "Scraped 15 agenda items",
            "metrics": {"items_found": 15, "execution_seconds": 3.2},
            "created_at": now,
        },
        {
            "id": str(uuid.uuid4()),
            "city_fips": "0660620",
            "session_id": str(uuid.uuid4()),
            "entry_type": "step_completed",
            "zone": "observation",
            "target_artifact": "conflict_scan",
            "description": "Found 5 flags, 10 clean",
            "metrics": {"total_flags": 5, "execution_seconds": 1.5},
            "created_at": now,
        },
        {
            "id": str(uuid.uuid4()),
            "city_fips": "0660620",
            "session_id": str(uuid.uuid4()),
            "entry_type": "anomaly_detected",
            "zone": "observation",
            "target_artifact": "scrape_escribemeetings",
            "description": "Low item count",
            "metrics": {"current": 5, "average": 25, "deviation_pct": 80.0},
            "created_at": now,
        },
        {
            "id": str(uuid.uuid4()),
            "city_fips": "0660620",
            "session_id": str(uuid.uuid4()),
            "entry_type": "run_completed",
            "zone": "observation",
            "target_artifact": "cloud_pipeline",
            "description": "Pipeline complete",
            "metrics": {"status": "completed", "execution_seconds": 45.3},
            "created_at": now,
        },
    ]


# ── Context Builder Tests ────────────────────────────────────


class TestBuildAssessmentContext:
    """build_assessment_context gathers and summarizes journal entries."""

    @patch("self_assessment.get_journal_entries")
    def test_computes_summary_stats(self, mock_get):
        entries = _sample_entries()
        mock_get.return_value = entries
        conn, _ = _mock_conn()

        ctx = build_assessment_context(conn, "0660620", days=7)

        assert ctx["total_runs"] == 1
        assert ctx["completed_runs"] == 1
        assert ctx["failed_runs"] == 0
        assert ctx["anomaly_count"] == 1
        assert ctx["step_count"] == 2
        assert ctx["days"] == 7
        assert len(ctx["entries"]) == 5

    @patch("self_assessment.get_journal_entries")
    def test_empty_entries(self, mock_get):
        mock_get.return_value = []
        conn, _ = _mock_conn()

        ctx = build_assessment_context(conn, "0660620", days=7)

        assert ctx["total_runs"] == 0
        assert ctx["completed_runs"] == 0
        assert ctx["anomaly_count"] == 0
        assert len(ctx["entries"]) == 0

    @patch("self_assessment.get_journal_entries")
    def test_counts_failures(self, mock_get):
        mock_get.return_value = [
            {"entry_type": "run_started", "description": "test", "created_at": datetime.now()},
            {"entry_type": "run_failed", "description": "failed", "metrics": {"error": "timeout"},
             "created_at": datetime.now()},
        ]
        conn, _ = _mock_conn()

        ctx = build_assessment_context(conn, "0660620", days=1)

        assert ctx["total_runs"] == 1
        assert ctx["failed_runs"] == 1
        assert ctx["completed_runs"] == 0


# ── Entry Formatting Tests ───────────────────────────────────


class TestFormatEntries:
    """_format_entries_for_prompt produces readable text for the LLM."""

    def test_formats_entries(self):
        entries = _sample_entries()
        text = _format_entries_for_prompt(entries)

        assert "run_started" in text
        assert "step_completed" in text
        assert "anomaly_detected" in text
        assert "scrape_escribemeetings" in text

    def test_empty_entries(self):
        text = _format_entries_for_prompt([])
        assert "No journal entries" in text

    def test_truncates_long_metrics(self):
        entries = [{
            "entry_type": "step_completed",
            "target_artifact": "test",
            "description": "test",
            "metrics": {"data": "x" * 300},
            "created_at": datetime.now(),
        }]
        text = _format_entries_for_prompt(entries)
        assert "..." in text


# ── Assessment Runner Tests ──────────────────────────────────


class TestRunSelfAssessment:
    """run_self_assessment calls the LLM and stores results."""

    @patch("self_assessment.get_journal_entries")
    @patch("self_assessment.anthropic")
    @patch("pipeline_journal.write_journal_entry")
    def test_runs_assessment(self, mock_write, mock_anthropic, mock_get):
        mock_write.return_value = uuid.uuid4()
        mock_get.return_value = _sample_entries()

        # Mock the Anthropic client
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = json.dumps({
            "overall_health": "degraded",
            "summary": "Pipeline completed but with anomaly",
            "findings": [{"category": "anomaly", "severity": "medium",
                          "description": "Low scrape count", "evidence": "5 vs 25 avg"}],
            "metrics": {"runs_analyzed": 1, "steps_completed": 2, "steps_failed": 0,
                        "anomalies_detected": 1, "avg_execution_seconds": 45.3},
            "recommendation": "Monitor scrape counts",
        })
        mock_response.usage.input_tokens = 1800
        mock_response.usage.output_tokens = 700

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.Anthropic.return_value = mock_client

        conn, _ = _mock_conn()
        result = run_self_assessment(conn, "0660620", days=7)

        assert result["assessment"]["overall_health"] == "degraded"
        assert result["token_usage"]["input_tokens"] == 1800
        assert len(result["assessment"]["findings"]) == 1

        # Verify it was stored in journal
        assert mock_write.call_count >= 1
        assessment_calls = [
            c for c in mock_write.call_args_list
            if c.kwargs.get("entry_type") == "assessment"
        ]
        assert len(assessment_calls) == 1

    @patch("self_assessment.get_journal_entries")
    @patch("self_assessment.anthropic")
    @patch("pipeline_journal.write_journal_entry")
    def test_handles_json_parse_failure(self, mock_write, mock_anthropic, mock_get):
        mock_write.return_value = uuid.uuid4()
        mock_get.return_value = _sample_entries()

        # Return invalid JSON
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = "This is not valid JSON"
        mock_response.usage.input_tokens = 1000
        mock_response.usage.output_tokens = 50

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_anthropic.Anthropic.return_value = mock_client

        conn, _ = _mock_conn()
        result = run_self_assessment(conn, "0660620", days=7)

        assert result["assessment"]["overall_health"] == "unknown"
        assert "Failed to parse" in result["assessment"]["summary"]

    def test_raises_without_anthropic(self):
        conn, _ = _mock_conn()
        with patch("self_assessment.anthropic", None):
            with pytest.raises(ImportError, match="anthropic"):
                run_self_assessment(conn, "0660620")


# ── Decision Packet Formatter Tests ──────────────────────────


class TestFormatDecisionPacket:
    """format_decision_packet produces readable operator output."""

    def test_healthy_assessment(self):
        result = {
            "assessment": {
                "overall_health": "healthy",
                "summary": "All systems normal",
                "findings": [],
                "metrics": {"runs_analyzed": 3, "steps_completed": 30,
                            "steps_failed": 0, "anomalies_detected": 0,
                            "avg_execution_seconds": 42.5},
                "recommendation": None,
            },
            "token_usage": {"input_tokens": 1800, "output_tokens": 700},
            "context": {"days": 7, "total_entries": 35, "total_runs": 3},
        }

        output = format_decision_packet(result)

        assert "[OK]" in output
        assert "HEALTHY" in output
        assert "All systems normal" in output
        assert "$" in output  # cost estimate

    def test_degraded_with_findings(self):
        result = {
            "assessment": {
                "overall_health": "degraded",
                "summary": "Pipeline running but with issues",
                "findings": [
                    {"category": "anomaly", "severity": "medium",
                     "description": "Low scrape count", "evidence": "5 vs 25"},
                    {"category": "performance", "severity": "low",
                     "description": "Step 3 slower than usual", "evidence": "12s vs 3s avg"},
                ],
                "metrics": {"runs_analyzed": 1, "steps_completed": 10,
                            "steps_failed": 0, "anomalies_detected": 1,
                            "avg_execution_seconds": 55.0},
                "recommendation": "Monitor scrape counts for next run",
            },
            "token_usage": {"input_tokens": 2000, "output_tokens": 800},
            "context": {"days": 1, "total_entries": 12, "total_runs": 1},
        }

        output = format_decision_packet(result)

        assert "[WARN]" in output
        assert "DEGRADED" in output
        assert "Low scrape count" in output
        assert "Monitor scrape counts" in output
        assert "1." in output and "2." in output

    def test_unhealthy_assessment(self):
        result = {
            "assessment": {
                "overall_health": "unhealthy",
                "summary": "Pipeline failed to complete",
                "findings": [
                    {"category": "failure", "severity": "high",
                     "description": "Pipeline crashed", "evidence": "Timeout after 600s"},
                ],
                "metrics": {"runs_analyzed": 1, "steps_completed": 3,
                            "steps_failed": 1, "anomalies_detected": 0,
                            "avg_execution_seconds": None},
                "recommendation": "Investigate timeout cause",
            },
            "token_usage": {"input_tokens": 1500, "output_tokens": 500},
            "context": {"days": 1, "total_entries": 5, "total_runs": 1},
        }

        output = format_decision_packet(result)

        assert "[FAIL]" in output
        assert "UNHEALTHY" in output
        assert "Pipeline crashed" in output

    def test_no_token_usage(self):
        result = {
            "assessment": {"overall_health": "healthy", "summary": "OK", "findings": [],
                           "metrics": {}, "recommendation": None},
            "context": {"days": 7, "total_entries": 0, "total_runs": 0},
        }

        output = format_decision_packet(result)
        assert "[OK]" in output
        # Should not crash without token_usage
