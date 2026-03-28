"""
Pipeline Journal — Append-only observation log (Autonomy Zones Phase A).

Instruments pipeline runs with structured journal entries for self-assessment.
Entries are never deleted or modified. All writes are non-fatal: failures
print a warning but never raise. Pipeline behavior is unchanged even if the
journal table is missing.

Usage:
    from pipeline_journal import PipelineJournal

    journal = PipelineJournal(conn, city_fips="0660620")
    journal.log_run_start("cloud_pipeline", scan_run_id, "Pipeline for 2026-03-10")

    journal.log_step("scrape_escribemeetings", "Scraped 15 items", {
        "items_found": 15, "execution_seconds": 3.2,
    })

    journal.log_run_end("cloud_pipeline", scan_run_id, "completed",
        "Pipeline complete", {"total_flags": 5})
"""

from __future__ import annotations

import uuid
from typing import Any

from db import write_journal_entry, get_recent_step_metrics


class PipelineJournal:
    """Append-only journal writer for pipeline self-assessment.

    All writes are non-fatal: failures print a warning but never raise.
    Pipeline behavior is unchanged even if the journal table is missing.
    """

    def __init__(
        self,
        conn,
        city_fips: str,
        session_id: uuid.UUID | None = None,
    ):
        self.conn = conn
        self.city_fips = city_fips
        self.session_id = session_id or uuid.uuid4()

    def log_step(
        self,
        step_name: str,
        description: str,
        metrics: dict[str, Any] | None = None,
        *,
        entry_type: str = "step_completed",
    ) -> None:
        """Record a pipeline step completion (or failure) in the journal."""
        self._write_entry(
            entry_type=entry_type,
            target_artifact=step_name,
            description=description,
            metrics=metrics,
        )

    def log_anomaly(
        self,
        target_artifact: str,
        description: str,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        """Record an anomaly detection."""
        self._write_entry(
            entry_type="anomaly_detected",
            target_artifact=target_artifact,
            description=description,
            metrics=metrics,
        )

    def log_run_start(
        self,
        run_type: str,
        run_id: str,
        description: str,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        """Record the start of a pipeline or sync run."""
        merged = {"run_type": run_type, "run_id": run_id, **(metrics or {})}
        self._write_entry(
            entry_type="run_started",
            target_artifact=run_type,
            description=description,
            metrics=merged,
        )

    def log_run_end(
        self,
        run_type: str,
        run_id: str,
        status: str,
        description: str,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        """Record the end of a pipeline or sync run."""
        entry_type = "run_completed" if status == "completed" else "run_failed"
        merged = {"run_type": run_type, "run_id": run_id, "status": status, **(metrics or {})}
        self._write_entry(
            entry_type=entry_type,
            target_artifact=run_type,
            description=description,
            metrics=merged,
        )

    def log_assessment(
        self,
        assessment: dict[str, Any],
        token_usage: dict[str, Any] | None = None,
    ) -> None:
        """Record a self-assessment result with LLM cost tracking."""
        metrics = {
            "assessment": assessment,
            **({"token_usage": token_usage} if token_usage else {}),
        }
        self._write_entry(
            entry_type="assessment",
            target_artifact="self_assessment",
            description=f"Pipeline health: {assessment.get('overall_health', 'unknown')}",
            metrics=metrics,
        )

    def _write_entry(
        self,
        entry_type: str,
        description: str,
        target_artifact: str | None = None,
        metrics: dict[str, Any] | None = None,
    ) -> None:
        """Internal: write one row to pipeline_journal. Never raises."""
        try:
            write_journal_entry(
                self.conn,
                city_fips=self.city_fips,
                session_id=self.session_id,
                entry_type=entry_type,
                description=description,
                zone="observation",
                target_artifact=target_artifact,
                metrics=metrics,
            )
        except Exception as e:
            print(f"  [journal] Warning: failed to write entry: {e}")


# ── Anomaly Detection ────────────────────────────────────────


def detect_count_anomaly(
    current_count: int,
    step_name: str,
    recent_counts: list[int],
    threshold_pct: float = 0.5,
) -> dict[str, Any] | None:
    """Detect if current_count deviates significantly from recent history.

    Returns anomaly dict if deviation exceeds threshold_pct (default 50%),
    None otherwise. Requires at least 3 recent data points.
    """
    # Filter out None values
    valid = [c for c in recent_counts if c is not None]
    if len(valid) < 3:
        return None

    # Use median — robust to outliers and baseline shifts (e.g., post-dedup)
    sorted_valid = sorted(valid)
    mid = len(sorted_valid) // 2
    baseline = (
        sorted_valid[mid]
        if len(sorted_valid) % 2
        else (sorted_valid[mid - 1] + sorted_valid[mid]) / 2
    )

    if baseline == 0:
        # Can't compute deviation from zero baseline
        return None if current_count == 0 else {
            "step_name": step_name,
            "description": f"{step_name}: count is {current_count} but recent baseline is 0",
            "current": current_count,
            "baseline": 0,
            "deviation_pct": None,
            "severity": "medium",
        }

    deviation = abs(current_count - baseline) / baseline

    if deviation <= threshold_pct:
        return None

    direction = "below" if current_count < baseline else "above"
    severity = "high" if deviation > 1.0 else "medium"

    return {
        "step_name": step_name,
        "description": (
            f"{step_name}: count {current_count} is {deviation:.0%} {direction} "
            f"recent baseline of {baseline:.0f}"
        ),
        "current": current_count,
        "baseline": round(baseline, 1),
        "deviation_pct": round(deviation * 100, 1),
        "direction": direction,
        "severity": severity,
    }


def detect_timing_anomaly(
    current_seconds: float,
    step_name: str,
    recent_timings: list[float],
    threshold_multiplier: float = 3.0,
) -> dict[str, Any] | None:
    """Detect if step took significantly longer than recent history.

    Flags when current_seconds exceeds threshold_multiplier * average.
    Only flags slowdowns (not speedups). Requires at least 3 data points.
    """
    valid = [t for t in recent_timings if t is not None and t > 0]
    if len(valid) < 3:
        return None

    avg = sum(valid) / len(valid)
    if avg == 0:
        return None

    ratio = current_seconds / avg
    if ratio <= threshold_multiplier:
        return None

    return {
        "step_name": step_name,
        "description": (
            f"{step_name}: took {current_seconds:.1f}s, "
            f"which is {ratio:.1f}x the recent average of {avg:.1f}s"
        ),
        "current_seconds": round(current_seconds, 2),
        "average_seconds": round(avg, 2),
        "ratio": round(ratio, 1),
        "severity": "high" if ratio > 5.0 else "medium",
    }


def check_anomalies(
    journal: PipelineJournal,
    conn,
    city_fips: str,
    step_name: str,
    current_count: int | None = None,
    current_seconds: float | None = None,
    count_metric_key: str = "items_found",
) -> None:
    """Check for count and timing anomalies, log any found.

    Convenience function that queries recent history and runs both
    anomaly detectors. Call after each pipeline step.
    """
    try:
        recent = get_recent_step_metrics(conn, city_fips, step_name, limit=10)
        if not recent:
            return

        if current_count is not None:
            recent_counts = [
                r["metrics"].get(count_metric_key)
                for r in recent if r.get("metrics")
            ]
            anomaly = detect_count_anomaly(current_count, step_name, recent_counts)
            if anomaly:
                journal.log_anomaly(step_name, anomaly["description"], anomaly)

        if current_seconds is not None:
            recent_timings = [
                r["metrics"].get("execution_seconds")
                for r in recent if r.get("metrics")
            ]
            anomaly = detect_timing_anomaly(current_seconds, step_name, recent_timings)
            if anomaly:
                journal.log_anomaly(step_name, anomaly["description"], anomaly)

    except Exception as e:
        print(f"  [journal] Warning: anomaly check failed: {e}")
