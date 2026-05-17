"""Tests for T0.4: sync anomaly hold gate.

The motivating incident (2026-05-16): a contributions sync reported
records_new=1591 as "verified live end-to-end" when the rolling baseline
was ~6. The data turned out to be correct (a backlog caught up), but
the AI presented the spike to the operator as a normal sync. With the
T0.4 gate in place, a P0 decision_queue row appears at the top of the
SessionStart brief and the operator reviews before downstream consumers
(ISR pages, journalist-visible profiles) treat the spike as routine.

Test approach:
  - Unit tests with mocks for the routing logic and the 1591/6 detection
  - Opt-in live-DB test (RICHMOND_RUN_DB_TESTS=1) for the end-to-end
    create_decision happy path against the real decision_queue table
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT / "src"))

from pipeline_journal import (
    check_anomalies,
    detect_count_anomaly,
)
from data_sync import _route_anomalies_to_decision_queue


# ── 1591/6 scenario — the load-bearing regression test ────────────


def test_1591_vs_6_baseline_detected_as_high_severity_count_anomaly():
    """detect_count_anomaly must flag the motivating-incident case.

    Baseline of 6 with current=1591 is a ~26000% deviation. The "high"
    severity threshold is deviation > 100% (1.0), so this MUST come out
    severity=high. If a future tuning change demotes this to "medium",
    the hold gate stops firing and we regress to the original bug.
    """
    recent_counts = [4, 5, 6, 7, 8]  # median 6
    anomaly = detect_count_anomaly(
        current_count=1591,
        step_name="sync_netfile",
        recent_counts=recent_counts,
    )
    assert anomaly is not None, "1591 vs baseline 6 must be detected"
    assert anomaly["severity"] == "high", (
        f"Expected severity=high (deviation > 100%); got {anomaly['severity']}. "
        f"Demoting this to medium would stop the hold gate from firing."
    )
    assert anomaly["current"] == 1591
    assert anomaly["baseline"] == 6.0
    # Sanity on direction wording — used in the operator-facing title
    assert anomaly["direction"] == "above"


def test_check_anomalies_returns_detected_list_for_1591_vs_6():
    """check_anomalies must RETURN the anomaly (not just journal it).

    Before T0.4 the function returned None — the caller had no way to
    know an anomaly fired. The new contract returns a list so run_sync
    can route high-severity entries into decision_queue.
    """
    journal = MagicMock()
    conn = MagicMock()

    # Simulate 5 prior runs with counts 4-8 (median 6)
    fake_recent = [
        {"metrics": {"records_fetched": n, "execution_seconds": 1.0}}
        for n in [4, 5, 6, 7, 8]
    ]

    with patch(
        "pipeline_journal.get_recent_step_metrics", return_value=fake_recent
    ):
        anomalies = check_anomalies(
            journal, conn, "0660620", "sync_netfile",
            current_count=1591,
            current_seconds=10.0,
            count_metric_key="records_fetched",
        )

    # Returned list contains the count anomaly
    assert isinstance(anomalies, list)
    assert len(anomalies) >= 1
    count_anom = next(
        (a for a in anomalies if "deviation_pct" in a), None
    )
    assert count_anom is not None
    assert count_anom["severity"] == "high"
    # And the journal was still notified (backward compat)
    journal.log_anomaly.assert_called()


def test_check_anomalies_returns_empty_list_below_threshold():
    """No anomalies → empty list, not None. Caller can iterate safely."""
    journal = MagicMock()
    conn = MagicMock()
    fake_recent = [
        {"metrics": {"records_fetched": n, "execution_seconds": 1.0}}
        for n in [50, 51, 52, 53, 49]
    ]
    with patch(
        "pipeline_journal.get_recent_step_metrics", return_value=fake_recent
    ):
        anomalies = check_anomalies(
            journal, conn, "0660620", "sync_test",
            current_count=51,  # well within baseline
            current_seconds=1.0,
            count_metric_key="records_fetched",
        )
    assert anomalies == []


def test_check_anomalies_returns_empty_list_on_no_history():
    """Empty recent history → empty list (no false alarms on first run)."""
    journal = MagicMock()
    conn = MagicMock()
    with patch(
        "pipeline_journal.get_recent_step_metrics", return_value=[]
    ):
        anomalies = check_anomalies(
            journal, conn, "0660620", "sync_test",
            current_count=1591,
            current_seconds=10.0,
        )
    assert anomalies == []


# ── _route_anomalies_to_decision_queue routing logic ──────────────


def test_route_creates_decision_for_high_severity_count_anomaly():
    """High-severity count anomaly produces ONE create_decision call."""
    conn = MagicMock()
    anomalies = [{
        "step_name": "sync_netfile",
        "description": "sync_netfile: count 1591 is 26483% above baseline of 6",
        "current": 1591,
        "baseline": 6.0,
        "deviation_pct": 26483.3,
        "direction": "above",
        "severity": "high",
    }]

    with patch("decision_queue.create_decision") as mock_create:
        # Mock returns a UUID-like value to simulate a non-deduped insert
        mock_create.return_value = "fake-uuid-1234"
        created = _route_anomalies_to_decision_queue(
            conn, "0660620", "netfile", anomalies
        )

    assert created == 1, "Exactly one hold row for one high-severity anomaly"
    assert mock_create.call_count == 1
    call_kwargs = mock_create.call_args.kwargs
    assert call_kwargs["decision_type"] == "anomaly"
    # Sync anomaly is P0 — visible at the top of SessionStart brief
    assert call_kwargs["severity"] == "critical"
    # dedup_key shape lets repeated runs dedupe to one pending row
    assert call_kwargs["dedup_key"] == "sync_anomaly:netfile:sync_netfile"
    # Title includes the values the operator needs to assess
    assert "1591" in call_kwargs["title"]
    assert "6" in call_kwargs["title"] or "6.0" in call_kwargs["title"]
    # Evidence is the full anomaly dict for later inspection
    assert call_kwargs["evidence"] == anomalies[0]


def test_route_ignores_medium_severity():
    """Medium-severity anomalies stay journal-only. No decision_queue row.

    Rationale: a 30% spike is interesting but not actionable in the same
    way a 1591-vs-6 deviation is. Routing every medium anomaly to the
    queue would drown the P0 signal. Tighten by adding 'medium' to
    _ANOMALY_HOLD_SEVERITIES if the operator wants finer granularity.
    """
    conn = MagicMock()
    anomalies = [{
        "step_name": "sync_test",
        "current": 80,
        "baseline": 60.0,
        "deviation_pct": 33.3,
        "severity": "medium",
    }]
    with patch("decision_queue.create_decision") as mock_create:
        created = _route_anomalies_to_decision_queue(
            conn, "0660620", "test", anomalies
        )
    assert created == 0
    mock_create.assert_not_called()


def test_route_handles_create_decision_failure_silently():
    """A DB error in create_decision must NOT kill the sync.

    The sync data is already committed. Decision queue is a secondary
    surface — its failure should warn but not propagate.
    """
    conn = MagicMock()
    anomalies = [{
        "step_name": "sync_test",
        "severity": "high",
        "current": 1591,
        "baseline": 6.0,
        "deviation_pct": 26483.0,
    }]
    with patch(
        "decision_queue.create_decision",
        side_effect=RuntimeError("DB connection lost"),
    ):
        # Must NOT raise
        created = _route_anomalies_to_decision_queue(
            conn, "0660620", "test", anomalies
        )
    assert created == 0


def test_route_handles_timing_anomaly_with_ratio_field():
    """Timing anomalies use different fields (ratio vs deviation_pct).

    detect_timing_anomaly returns {ratio, current_seconds, average_seconds},
    not {deviation_pct, current, baseline}. Routing must handle both
    shapes without KeyError.
    """
    conn = MagicMock()
    anomalies = [{
        "step_name": "sync_test",
        "description": "sync_test took 60s, 10x recent avg",
        "current_seconds": 60.0,
        "average_seconds": 6.0,
        "ratio": 10.0,
        "severity": "high",
    }]
    with patch("decision_queue.create_decision") as mock_create:
        mock_create.return_value = "fake-uuid-5678"
        created = _route_anomalies_to_decision_queue(
            conn, "0660620", "test", anomalies
        )
    assert created == 1
    call_kwargs = mock_create.call_args.kwargs
    assert "10.0x" in call_kwargs["title"] or "10x" in call_kwargs["title"]


def test_route_creates_multiple_decisions_for_multiple_high_anomalies():
    """Count + timing both high → two decision rows, one per anomaly."""
    conn = MagicMock()
    anomalies = [
        {
            "step_name": "sync_test",
            "severity": "high",
            "current": 1591,
            "baseline": 6.0,
            "deviation_pct": 26483.0,
        },
        {
            "step_name": "sync_test",
            "severity": "high",
            "current_seconds": 60.0,
            "average_seconds": 6.0,
            "ratio": 10.0,
        },
    ]
    with patch("decision_queue.create_decision") as mock_create:
        mock_create.return_value = "fake-uuid"
        created = _route_anomalies_to_decision_queue(
            conn, "0660620", "test", anomalies
        )
    assert created == 2
    assert mock_create.call_count == 2


# ── Opt-in live-DB end-to-end ─────────────────────────────────────


_HAS_DB = bool(os.getenv("DATABASE_URL")) and "test" not in (os.getenv("DATABASE_URL") or "")
_RUN_DB_TESTS = os.getenv("RICHMOND_RUN_DB_TESTS") == "1"


@pytest.mark.skipif(
    not (_HAS_DB and _RUN_DB_TESTS),
    reason="Live-DB test; set RICHMOND_RUN_DB_TESTS=1 to opt in.",
)
def test_route_creates_real_decision_queue_row_end_to_end():
    """End-to-end: simulated 1591/6 anomaly creates a real decision_queue
    row, visible via get_pending().

    Cleans up the test row at the end so the operator doesn't see it
    in subsequent SessionStart briefs.
    """
    from db import get_connection
    from decision_queue import get_pending, resolve_decision

    conn = get_connection()
    try:
        anomalies = [{
            "step_name": "sync_test_t04",
            "description": "T0.4 end-to-end test — 1591 vs baseline 6",
            "current": 1591,
            "baseline": 6.0,
            "deviation_pct": 26483.3,
            "direction": "above",
            "severity": "high",
        }]
        created = _route_anomalies_to_decision_queue(
            conn, "0660620", "test_t04", anomalies
        )
        assert created == 1

        # Verify the row exists and looks right
        pending = get_pending(conn, "0660620", decision_type="anomaly")
        test_rows = [
            p for p in pending
            if p.get("source") == "data_sync.check_anomalies"
            and "test_t04" in (p.get("title") or "")
        ]
        assert len(test_rows) == 1, (
            f"Expected exactly 1 test_t04 row in decision_queue; "
            f"found {len(test_rows)}."
        )
        row = test_rows[0]
        assert row["severity"] == "critical"
        assert row["decision_type"] == "anomaly"
        # Cleanup
        resolve_decision(
            conn, row["id"], verdict="rejected",
            note="cleanup from test_sync_anomaly_hold.py end-to-end test",
        )
    finally:
        conn.close()
