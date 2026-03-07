"""Tests for pipeline journal writer and anomaly detection."""

import uuid
from unittest.mock import MagicMock, patch, call

import pytest

from pipeline_journal import (
    PipelineJournal,
    detect_count_anomaly,
    detect_timing_anomaly,
    check_anomalies,
)


# ── Helpers ──────────────────────────────────────────────────


def _mock_conn():
    """Create a mock DB connection with cursor context manager."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__ = lambda self: cursor
    conn.cursor.return_value.__exit__ = MagicMock(return_value=False)
    return conn, cursor


# ── PipelineJournal Tests ────────────────────────────────────


class TestPipelineJournal:
    """PipelineJournal writes append-only entries without blocking the pipeline."""

    @patch("pipeline_journal.write_journal_entry")
    def test_log_step_writes_entry(self, mock_write):
        conn, _ = _mock_conn()
        mock_write.return_value = uuid.uuid4()

        journal = PipelineJournal(conn, city_fips="0660620")
        journal.log_step("scrape_escribemeetings", "Scraped 15 items", {
            "items_found": 15,
            "execution_seconds": 3.2,
        })

        mock_write.assert_called_once()
        args = mock_write.call_args
        assert args.kwargs["entry_type"] == "step_completed"
        assert args.kwargs["target_artifact"] == "scrape_escribemeetings"
        assert args.kwargs["description"] == "Scraped 15 items"
        assert args.kwargs["metrics"]["items_found"] == 15
        assert args.kwargs["zone"] == "observation"

    @patch("pipeline_journal.write_journal_entry")
    def test_log_step_custom_entry_type(self, mock_write):
        conn, _ = _mock_conn()
        mock_write.return_value = uuid.uuid4()

        journal = PipelineJournal(conn, city_fips="0660620")
        journal.log_step("conflict_scan", "Scan failed", entry_type="step_failed")

        args = mock_write.call_args
        assert args.kwargs["entry_type"] == "step_failed"

    @patch("pipeline_journal.write_journal_entry")
    def test_log_anomaly_writes_entry(self, mock_write):
        conn, _ = _mock_conn()
        mock_write.return_value = uuid.uuid4()

        journal = PipelineJournal(conn, city_fips="0660620")
        journal.log_anomaly("scrape_escribemeetings", "Low item count", {
            "current": 5, "average": 25, "deviation_pct": 80.0,
        })

        args = mock_write.call_args
        assert args.kwargs["entry_type"] == "anomaly_detected"
        assert args.kwargs["target_artifact"] == "scrape_escribemeetings"

    @patch("pipeline_journal.write_journal_entry")
    def test_log_run_start_and_end(self, mock_write):
        conn, _ = _mock_conn()
        mock_write.return_value = uuid.uuid4()
        run_id = str(uuid.uuid4())

        journal = PipelineJournal(conn, city_fips="0660620")
        journal.log_run_start("cloud_pipeline", run_id, "Pipeline for 2026-03-10")
        journal.log_run_end("cloud_pipeline", run_id, "completed", "Done")

        assert mock_write.call_count == 2
        start_call = mock_write.call_args_list[0]
        end_call = mock_write.call_args_list[1]

        assert start_call.kwargs["entry_type"] == "run_started"
        assert end_call.kwargs["entry_type"] == "run_completed"
        assert start_call.kwargs["metrics"]["run_id"] == run_id
        assert end_call.kwargs["metrics"]["status"] == "completed"

    @patch("pipeline_journal.write_journal_entry")
    def test_log_run_end_failed(self, mock_write):
        conn, _ = _mock_conn()
        mock_write.return_value = uuid.uuid4()

        journal = PipelineJournal(conn, city_fips="0660620")
        journal.log_run_end("cloud_pipeline", "run-1", "failed", "Timeout error")

        args = mock_write.call_args
        assert args.kwargs["entry_type"] == "run_failed"
        assert args.kwargs["metrics"]["status"] == "failed"

    @patch("pipeline_journal.write_journal_entry")
    def test_session_id_groups_entries(self, mock_write):
        conn, _ = _mock_conn()
        mock_write.return_value = uuid.uuid4()

        session = uuid.uuid4()
        journal = PipelineJournal(conn, city_fips="0660620", session_id=session)
        journal.log_step("step1", "First step")
        journal.log_step("step2", "Second step")

        session_ids = [
            c.kwargs["session_id"] for c in mock_write.call_args_list
        ]
        assert all(s == session for s in session_ids)

    @patch("pipeline_journal.write_journal_entry")
    def test_auto_generates_session_id(self, mock_write):
        conn, _ = _mock_conn()
        mock_write.return_value = uuid.uuid4()

        journal = PipelineJournal(conn, city_fips="0660620")
        assert journal.session_id is not None
        assert isinstance(journal.session_id, uuid.UUID)

    @patch("pipeline_journal.write_journal_entry")
    def test_write_entry_never_raises(self, mock_write):
        """_write_entry swallows all exceptions."""
        conn, _ = _mock_conn()
        mock_write.side_effect = Exception("DB connection lost")

        journal = PipelineJournal(conn, city_fips="0660620")
        # Should not raise
        journal.log_step("some_step", "Some description")

    @patch("pipeline_journal.write_journal_entry")
    def test_log_assessment_includes_token_usage(self, mock_write):
        conn, _ = _mock_conn()
        mock_write.return_value = uuid.uuid4()

        journal = PipelineJournal(conn, city_fips="0660620")
        journal.log_assessment(
            {"overall_health": "healthy", "findings": []},
            token_usage={"input_tokens": 1800, "output_tokens": 700},
        )

        args = mock_write.call_args
        assert args.kwargs["entry_type"] == "assessment"
        assert args.kwargs["metrics"]["token_usage"]["input_tokens"] == 1800
        assert "healthy" in args.kwargs["description"]


# ── Anomaly Detection Tests ──────────────────────────────────


class TestCountAnomalyDetection:
    """detect_count_anomaly flags significant deviations from baseline."""

    def test_no_anomaly_within_threshold(self):
        result = detect_count_anomaly(22, "scrape", [20, 25, 23, 21, 24])
        assert result is None

    def test_anomaly_detected_below_threshold(self):
        """Count 60% below average triggers anomaly."""
        result = detect_count_anomaly(8, "scrape", [20, 25, 23, 21, 24])
        assert result is not None
        assert result["direction"] == "below"
        assert result["severity"] in ("medium", "high")

    def test_anomaly_detected_above_threshold(self):
        """Count 200% above average triggers anomaly."""
        result = detect_count_anomaly(60, "scrape", [20, 25, 23, 21, 24])
        assert result is not None
        assert result["direction"] == "above"

    def test_no_history_returns_none(self):
        """Too few data points means no anomaly detection."""
        result = detect_count_anomaly(10, "scrape", [20, 25])
        assert result is None

    def test_empty_history_returns_none(self):
        result = detect_count_anomaly(10, "scrape", [])
        assert result is None

    def test_zero_baseline_nonzero_current(self):
        """Non-zero count against zero baseline is flagged."""
        result = detect_count_anomaly(5, "scrape", [0, 0, 0, 0])
        assert result is not None

    def test_zero_baseline_zero_current(self):
        result = detect_count_anomaly(0, "scrape", [0, 0, 0, 0])
        assert result is None

    def test_custom_threshold(self):
        """Lower threshold catches smaller deviations."""
        # 15 vs avg of 22.6 = 33% below, which is within 50% but beyond 25%
        result_default = detect_count_anomaly(15, "scrape", [20, 25, 23, 21, 24])
        result_strict = detect_count_anomaly(15, "scrape", [20, 25, 23, 21, 24], threshold_pct=0.25)
        assert result_default is None
        assert result_strict is not None

    def test_none_values_filtered(self):
        """None values in history are ignored."""
        result = detect_count_anomaly(22, "scrape", [20, None, 25, None, 23, 21, 24])
        assert result is None

    def test_high_severity_for_large_deviation(self):
        """Deviation > 100% is high severity."""
        # avg ~22.6, count=60 is ~165% above = high severity
        result = detect_count_anomaly(60, "scrape", [20, 25, 23, 21, 24])
        assert result is not None
        assert result["severity"] == "high"


class TestTimingAnomalyDetection:
    """detect_timing_anomaly flags significant slowdowns."""

    def test_no_anomaly_within_range(self):
        result = detect_timing_anomaly(4.5, "scrape", [3.0, 3.5, 4.0, 3.2, 3.8])
        assert result is None

    def test_timing_anomaly_detected(self):
        """Step taking 5x average is flagged."""
        result = detect_timing_anomaly(15.0, "scrape", [3.0, 3.5, 4.0, 3.2])
        assert result is not None
        assert result["ratio"] > 3.0

    def test_speedup_not_flagged(self):
        """Faster than normal is not an anomaly."""
        result = detect_timing_anomaly(0.5, "scrape", [3.0, 3.5, 4.0, 3.2])
        assert result is None

    def test_no_history_returns_none(self):
        result = detect_timing_anomaly(5.0, "scrape", [3.0])
        assert result is None

    def test_high_severity_for_extreme_slowdown(self):
        """Ratio > 5x is high severity."""
        result = detect_timing_anomaly(30.0, "scrape", [3.0, 3.5, 4.0, 3.2])
        assert result is not None
        assert result["severity"] == "high"

    def test_none_and_zero_filtered(self):
        """None and zero values in history are ignored."""
        result = detect_timing_anomaly(4.0, "scrape", [3.0, None, 0, 3.5, 4.0, 3.2])
        assert result is None


# ── check_anomalies Integration ──────────────────────────────


class TestCheckAnomalies:
    """check_anomalies is a convenience wrapper that queries history and logs."""

    @patch("pipeline_journal.get_recent_step_metrics")
    @patch("pipeline_journal.write_journal_entry")
    def test_logs_count_anomaly(self, mock_write, mock_metrics):
        mock_write.return_value = uuid.uuid4()
        mock_metrics.return_value = [
            {"metrics": {"items_found": 20, "execution_seconds": 3.0}, "created_at": "2026-03-01"},
            {"metrics": {"items_found": 25, "execution_seconds": 3.5}, "created_at": "2026-03-02"},
            {"metrics": {"items_found": 23, "execution_seconds": 4.0}, "created_at": "2026-03-03"},
        ]

        conn, _ = _mock_conn()
        journal = PipelineJournal(conn, city_fips="0660620")
        check_anomalies(journal, conn, "0660620", "scrape", current_count=5)

        # Should have logged an anomaly
        assert mock_write.call_count >= 1
        anomaly_calls = [
            c for c in mock_write.call_args_list
            if c.kwargs.get("entry_type") == "anomaly_detected"
        ]
        assert len(anomaly_calls) == 1

    @patch("pipeline_journal.get_recent_step_metrics")
    @patch("pipeline_journal.write_journal_entry")
    def test_no_anomaly_when_normal(self, mock_write, mock_metrics):
        mock_write.return_value = uuid.uuid4()
        mock_metrics.return_value = [
            {"metrics": {"items_found": 20, "execution_seconds": 3.0}, "created_at": "2026-03-01"},
            {"metrics": {"items_found": 25, "execution_seconds": 3.5}, "created_at": "2026-03-02"},
            {"metrics": {"items_found": 23, "execution_seconds": 4.0}, "created_at": "2026-03-03"},
        ]

        conn, _ = _mock_conn()
        journal = PipelineJournal(conn, city_fips="0660620")
        check_anomalies(journal, conn, "0660620", "scrape", current_count=22)

        # No anomaly entries
        anomaly_calls = [
            c for c in mock_write.call_args_list
            if c.kwargs.get("entry_type") == "anomaly_detected"
        ]
        assert len(anomaly_calls) == 0

    @patch("pipeline_journal.get_recent_step_metrics")
    @patch("pipeline_journal.write_journal_entry")
    def test_never_raises_on_error(self, mock_write, mock_metrics):
        """check_anomalies swallows all exceptions."""
        mock_metrics.side_effect = Exception("DB error")
        conn, _ = _mock_conn()
        journal = PipelineJournal(conn, city_fips="0660620")
        # Should not raise
        check_anomalies(journal, conn, "0660620", "scrape", current_count=5)
