"""Tests for self-assessment module."""

import json
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from self_assessment import (
    build_assessment_context,
    _filter_resolved_failures,
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
    @patch("self_assessment.LLMClient")
    @patch("pipeline_journal.write_journal_entry")
    def test_runs_assessment(self, mock_write, mock_llm, mock_get):
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
        mock_llm.return_value = mock_client

        conn, _ = _mock_conn()
        result = run_self_assessment(conn, "0660620", days=7)

        assert result["assessment"]["overall_health"] == "degraded"
        assert result["token_usage"]["input_tokens"] == 1800
        assert len(result["assessment"]["findings"]) == 1

        request = mock_client.messages.create.call_args.kwargs
        assert request["max_tokens"] == 4000
        assert request["thinking"] == {"type": "enabled"}
        assert request["reasoning_effort"] == "high"
        assert request["response_format"] == {"type": "json_object"}

        # Verify it was stored in journal
        assert mock_write.call_count >= 1
        assessment_calls = [
            c for c in mock_write.call_args_list
            if c.kwargs.get("entry_type") == "assessment"
        ]
        assert len(assessment_calls) == 1

    @patch("self_assessment.get_journal_entries")
    @patch("self_assessment.LLMClient")
    @patch("pipeline_journal.write_journal_entry")
    def test_handles_json_parse_failure(self, mock_write, mock_llm, mock_get):
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
        mock_llm.return_value = mock_client

        conn, _ = _mock_conn()
        result = run_self_assessment(conn, "0660620", days=7)

        assert result["assessment"]["overall_health"] == "unknown"
        assert "Failed to parse" in result["assessment"]["summary"]

    @patch("self_assessment.get_journal_entries")
    @patch("self_assessment.LLMClient")
    @patch("pipeline_journal.write_journal_entry")
    def test_handles_markdown_fenced_json(self, mock_write, mock_llm, mock_get):
        """LLM wrapping JSON in ```js fences should be handled gracefully."""
        mock_write.return_value = uuid.uuid4()
        mock_get.return_value = _sample_entries()

        valid_json = json.dumps({
            "overall_health": "healthy",
            "summary": "All systems operational",
            "findings": [],
            "metrics": {"runs_analyzed": 1, "steps_completed": 1, "steps_failed": 0,
                        "anomalies_detected": 0, "avg_execution_seconds": 2.0},
            "recommendation": None,
        })
        # Wrap in markdown fences like the LLM sometimes does
        mock_response = MagicMock()
        mock_response.content = [MagicMock()]
        mock_response.content[0].text = f"```js\n{valid_json}\n```"
        mock_response.usage.input_tokens = 900
        mock_response.usage.output_tokens = 200

        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_llm.return_value = mock_client

        conn, _ = _mock_conn()
        result = run_self_assessment(conn, "0660620", days=1)

        assert result["assessment"]["overall_health"] == "healthy"
        assert result["assessment"]["summary"] == "All systems operational"

    def test_raises_without_llm_client(self):
        conn, _ = _mock_conn()
        with patch("self_assessment.LLMClient", None):
            with pytest.raises(TypeError):
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


# ── Recovery filter (regression for 2026-05-14..05-17 stale-P0 noise) ──


def _failure_entry(source: str, when: datetime, error: str = "boom") -> dict:
    return {
        "id": str(uuid.uuid4()),
        "city_fips": "0660620",
        "session_id": str(uuid.uuid4()),
        "entry_type": "run_failed",
        "zone": "observation",
        "target_artifact": "data_sync",
        "description": f"Sync {source} failed: {error}",
        "metrics": {"source": source, "error": error, "run_id": str(uuid.uuid4())},
        "created_at": when,
    }


def _success_entry(source: str, when: datetime) -> dict:
    return {
        "id": str(uuid.uuid4()),
        "city_fips": "0660620",
        "session_id": str(uuid.uuid4()),
        "entry_type": "run_completed",
        "zone": "observation",
        "target_artifact": "data_sync",
        "description": f"Sync {source} completed",
        "metrics": {"source": source, "run_id": str(uuid.uuid4())},
        "created_at": when,
    }


class TestFilterResolvedFailures:
    """Recovery filter — load-bearing for the stale-P0 prevention.

    Without this filter, every daily assessor run flags fixed bugs as
    new P0 decisions (the 2026-05-14..05-17 _normalize_name incident).
    """

    def test_failure_only_kept(self):
        """Failure with no later success → kept (the bug is still live)."""
        t = datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)
        entries = [_failure_entry("netfile", t)]
        out = _filter_resolved_failures(entries)
        assert len(out) == 1
        assert out[0]["entry_type"] == "run_failed"

    def test_failure_then_success_dropped(self):
        """Motivating case — failure at T1, success at T2 → failure dropped."""
        t1 = datetime(2026, 5, 15, 17, 11, tzinfo=timezone.utc)  # the real netfile failure
        t2 = datetime(2026, 5, 16, 19, 35, tzinfo=timezone.utc)  # the real recovery
        entries = [_failure_entry("netfile", t1), _success_entry("netfile", t2)]
        out = _filter_resolved_failures(entries)
        # Success kept, failure dropped
        assert len(out) == 1
        assert out[0]["entry_type"] == "run_completed"

    def test_success_then_failure_kept(self):
        """Success at T1, failure at T2 → failure kept (more recent than recovery)."""
        t1 = datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)
        entries = [_success_entry("netfile", t1), _failure_entry("netfile", t2)]
        out = _filter_resolved_failures(entries)
        # Both kept — newer failure is still active
        assert len(out) == 2
        assert {e["entry_type"] for e in out} == {"run_completed", "run_failed"}

    def test_per_source_independence(self):
        """netfile recovery does NOT resolve calaccess failure (or vice versa).

        Real-world case: both failed for the same root cause on 2026-05-15,
        but they're separate sources and the filter must not conflate them.
        """
        t1 = datetime(2026, 5, 15, 10, 0, tzinfo=timezone.utc)
        t2 = datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)
        entries = [
            _failure_entry("netfile", t1),
            _failure_entry("calaccess", t1),
            _success_entry("netfile", t2),
            # No calaccess success!
        ]
        out = _filter_resolved_failures(entries)
        # netfile failure dropped (recovered), calaccess failure kept (not recovered)
        types_with_sources = [
            (e["entry_type"], (e.get("metrics") or {}).get("source"))
            for e in out
        ]
        assert ("run_failed", "calaccess") in types_with_sources
        assert ("run_failed", "netfile") not in types_with_sources
        assert ("run_completed", "netfile") in types_with_sources

    def test_failure_without_source_kept(self):
        """Failure entry missing source metadata → kept (can't prove recovery)."""
        t = datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)
        entry = _failure_entry("netfile", t)
        # Strip the source field
        entry["metrics"] = {"error": "boom"}
        entries = [entry, _success_entry("netfile", t)]  # success with source — irrelevant
        out = _filter_resolved_failures(entries)
        assert any(e["entry_type"] == "run_failed" for e in out)

    def test_non_failure_entries_pass_through(self):
        """assessment / step_completed / anomaly_detected entries unchanged."""
        t = datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)
        entries = [
            {
                "id": str(uuid.uuid4()), "city_fips": "0660620",
                "session_id": str(uuid.uuid4()), "entry_type": "assessment",
                "zone": "observation", "target_artifact": "self_assessment",
                "description": "Health: degraded",
                "metrics": {"overall_health": "degraded"}, "created_at": t,
            },
            {
                "id": str(uuid.uuid4()), "city_fips": "0660620",
                "session_id": str(uuid.uuid4()), "entry_type": "anomaly_detected",
                "zone": "observation", "target_artifact": "netfile",
                "description": "1591 vs baseline 6",
                "metrics": {"severity": "high"}, "created_at": t,
            },
        ]
        out = _filter_resolved_failures(entries)
        assert len(out) == 2
        assert {e["entry_type"] for e in out} == {"assessment", "anomaly_detected"}

    def test_multiple_failures_single_recovery(self):
        """5 consecutive failures, then 1 success → all 5 failures dropped.

        Mirrors the actual incident shape: netfile failed every hour for
        2 days, then 234868c landed and recovery happened once.
        """
        base = datetime(2026, 5, 15, 0, 0, tzinfo=timezone.utc)
        entries = []
        for hour in (1, 4, 7, 10, 13):
            entries.append(_failure_entry("netfile", base.replace(hour=hour)))
        entries.append(_success_entry("netfile", base.replace(hour=20)))
        out = _filter_resolved_failures(entries)
        # All failures dropped, success kept
        assert len(out) == 1
        assert out[0]["entry_type"] == "run_completed"

    def test_filter_preserves_order(self):
        """Output preserves input order for retained entries."""
        t = datetime(2026, 5, 16, 10, 0, tzinfo=timezone.utc)
        entries = [
            _success_entry("netfile", t.replace(hour=8)),
            _failure_entry("netfile", t.replace(hour=10)),  # kept (latest)
            _success_entry("calaccess", t.replace(hour=9)),
        ]
        out = _filter_resolved_failures(entries)
        assert len(out) == 3
        assert [e["entry_type"] for e in out] == [
            "run_completed", "run_failed", "run_completed",
        ]

    def test_build_assessment_context_reports_filter_count(self):
        """build_assessment_context exposes how many entries were filtered.

        Operator should see when the filter is doing meaningful work
        (high count = real bugs being fixed in the window).
        """
        t1 = datetime(2026, 5, 15, 17, 11, tzinfo=timezone.utc)
        t2 = datetime(2026, 5, 16, 19, 35, tzinfo=timezone.utc)
        raw = [_failure_entry("netfile", t1), _success_entry("netfile", t2)]

        conn = MagicMock()
        with patch(
            "self_assessment.get_journal_entries", return_value=raw
        ):
            ctx = build_assessment_context(conn, "0660620", days=2)

        assert ctx["resolved_failures_filtered"] == 1
        # And the stats reflect the FILTERED list, not the raw one
        assert ctx["failed_runs"] == 0
        assert ctx["completed_runs"] == 1
