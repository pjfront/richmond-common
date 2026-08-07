"""Focused liveness tests for durable detector source-change events."""
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import data_sync
from db.source_change_jobs import (
    claim_source_change_job,
    continue_source_change_job,
    retry_source_change_job,
)


def _connection():
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    conn.cursor.return_value.__exit__.return_value = False
    return conn, cursor


def _configure_event(monkeypatch, *, base_completed=False):
    conn = MagicMock()
    monkeypatch.setattr(data_sync, "get_connection", lambda: conn)
    monkeypatch.setattr(
        data_sync,
        "claim_source_change_job",
        MagicMock(return_value={
            "change_id": "a" * 64,
            "source": "netfile",
            "status": "running",
            "dispatch_generation": 1,
            "base_completed_at": (
                datetime.now(timezone.utc) if base_completed else None
            ),
        }),
    )
    monkeypatch.setattr(data_sync, "get_source_change_job", MagicMock())
    monkeypatch.setattr(
        data_sync,
        "mark_source_change_base_completed",
        MagicMock(return_value={"status": "running", "base_completed_at": "now"}),
    )
    monkeypatch.setattr(
        data_sync,
        "complete_source_change_job",
        MagicMock(return_value={"status": "succeeded"}),
    )
    monkeypatch.setattr(
        data_sync,
        "retry_source_change_job",
        MagicMock(return_value={"status": "retry_wait", "attempt_count": 1}),
    )
    monkeypatch.setattr(
        data_sync,
        "continue_source_change_job",
        MagicMock(return_value={"status": "retry_wait", "attempt_count": 0}),
    )
    monkeypatch.setattr(data_sync, "get_change_sync_log", MagicMock())
    monkeypatch.setattr(data_sync, "revalidate_frontend", MagicMock())
    return conn


def _run_change_event(**kwargs):
    return data_sync.run_change_event(dispatch_generation=1, **kwargs)


def test_success_ack_waits_for_base_and_all_enrichments(monkeypatch):
    _configure_event(monkeypatch)
    base = MagicMock(return_value={"status": "completed", "records_new": 2})
    downstream = MagicMock(return_value=[
        {"enrichment": "donor_classification", "status": "completed"},
        {"enrichment": "donor_dedup", "status": "completed"},
    ])
    monkeypatch.setattr(data_sync, "run_sync", base)
    monkeypatch.setattr(data_sync, "run_downstream", downstream)

    result = _run_change_event(
        source="netfile", change_id="a" * 64, enrich=True,
    )

    assert result["status"] == "completed"
    data_sync.mark_source_change_base_completed.assert_called_once()
    data_sync.complete_source_change_job.assert_called_once()
    data_sync.retry_source_change_job.assert_not_called()


def test_enrichment_failure_is_retryable_and_not_acknowledged(monkeypatch):
    _configure_event(monkeypatch)
    monkeypatch.setattr(
        data_sync,
        "run_sync",
        MagicMock(return_value={"status": "completed"}),
    )
    monkeypatch.setattr(
        data_sync,
        "run_downstream",
        MagicMock(return_value=[{
            "enrichment": "donor_classification",
            "status": "failed",
            "error": "provider timeout",
        }]),
    )

    result = _run_change_event(
        source="netfile", change_id="a" * 64, enrich=True,
    )

    assert result["status"] == "failed"
    assert result["phase"] == "enrichment"
    data_sync.retry_source_change_job.assert_called_once()
    data_sync.complete_source_change_job.assert_not_called()


def test_completed_but_incomplete_source_is_retryable_and_not_acknowledged(
    monkeypatch,
):
    _configure_event(monkeypatch)
    downstream = MagicMock()
    monkeypatch.setattr(
        data_sync,
        "run_sync",
        MagicMock(return_value={
            "status": "completed",
            "retryable_incomplete": True,
            "incomplete_count": 1,
            "incomplete_reasons": ["one eSCRIBE meeting failed"],
        }),
    )
    monkeypatch.setattr(data_sync, "run_downstream", downstream)

    result = _run_change_event(
        source="netfile", change_id="a" * 64, enrich=True,
    )

    assert result["status"] == "failed"
    assert result["phase"] == "source"
    assert "one eSCRIBE meeting failed" in result["error"]
    data_sync.retry_source_change_job.assert_called_once()
    data_sync.mark_source_change_base_completed.assert_not_called()
    data_sync.complete_source_change_job.assert_not_called()
    downstream.assert_not_called()


def test_completed_but_incomplete_enrichment_is_not_terminally_acknowledged(
    monkeypatch,
):
    _configure_event(monkeypatch)
    monkeypatch.setattr(
        data_sync,
        "run_sync",
        MagicMock(return_value={"status": "completed"}),
    )
    monkeypatch.setattr(
        data_sync,
        "run_downstream",
        MagicMock(return_value=[{
            "enrichment": "proceeding_classification",
            "status": "completed",
            "retryable_incomplete": True,
            "incomplete_count": 1,
            "incomplete_reasons": ["1 classification remains"],
        }]),
    )

    result = _run_change_event(
        source="netfile", change_id="a" * 64, enrich=True,
    )

    assert result["status"] == "failed"
    assert result["phase"] == "enrichment"
    assert "1 classification remains" in result["error"]
    data_sync.retry_source_change_job.assert_called_once()
    data_sync.complete_source_change_job.assert_not_called()


def test_bounded_progress_uses_continuation_not_failure_retry(monkeypatch):
    _configure_event(monkeypatch, base_completed=True)
    monkeypatch.setattr(data_sync, "run_sync", MagicMock())
    monkeypatch.setattr(
        data_sync,
        "run_downstream",
        MagicMock(return_value=[{
            "enrichment": "proceeding_classification",
            "status": "completed",
            "retryable_incomplete": False,
            "continuation_required": True,
            "continuation_count": 501,
            "continuation_reasons": ["501 classifications remain"],
        }]),
    )

    result = _run_change_event(
        source="netfile", change_id="a" * 64, enrich=True,
    )

    assert result["status"] == "continued"
    assert "501 classifications remain" in result["continuation"]
    data_sync.continue_source_change_job.assert_called_once()
    data_sync.retry_source_change_job.assert_not_called()
    data_sync.complete_source_change_job.assert_not_called()


def test_more_than_500_healthy_rows_cannot_exhaust_failure_attempts(
    monkeypatch,
):
    """Seven 100-row deliveries converge with no slice-limit dead letter."""
    state = {
        "attempt_count": 0,
        "dispatch_generation": 0,
        "remaining": 601,
        "max_seen": 0,
    }
    conn = MagicMock()
    monkeypatch.setattr(data_sync, "get_connection", lambda: conn)

    def claim(*_args, **_kwargs):
        assert _kwargs["dispatch_generation"] == state["dispatch_generation"]
        return {
            "change_id": "a" * 64,
            "source": "netfile",
            "status": "running",
            "base_completed_at": datetime.now(timezone.utc),
            "attempt_count": state["attempt_count"],
            "dispatch_generation": state["dispatch_generation"],
        }

    def continue_job(*_args, **_kwargs):
        assert _kwargs["dispatch_generation"] == state["dispatch_generation"]
        state["attempt_count"] = max(0, state["attempt_count"] - 1)
        return {
            "status": "retry_wait",
            "attempt_count": state["attempt_count"],
        }

    def downstream(**_kwargs):
        state["remaining"] = max(0, state["remaining"] - 100)
        remaining = state["remaining"]
        return [{
            "enrichment": "proceeding_classification",
            "status": "completed",
            "retryable_incomplete": False,
            "continuation_required": remaining > 0,
            "continuation_count": remaining,
            "continuation_reasons": (
                [f"{remaining} classifications remain"] if remaining else []
            ),
        }]

    monkeypatch.setattr(data_sync, "claim_source_change_job", MagicMock(side_effect=claim))
    monkeypatch.setattr(data_sync, "get_source_change_job", MagicMock())
    monkeypatch.setattr(data_sync, "run_sync", MagicMock())
    monkeypatch.setattr(data_sync, "run_downstream", downstream)
    monkeypatch.setattr(
        data_sync,
        "continue_source_change_job",
        MagicMock(side_effect=continue_job),
    )
    monkeypatch.setattr(
        data_sync,
        "retry_source_change_job",
        MagicMock(return_value={"status": "dead_letter"}),
    )
    monkeypatch.setattr(
        data_sync,
        "complete_source_change_job",
        MagicMock(return_value={"status": "succeeded"}),
    )
    monkeypatch.setattr(data_sync, "revalidate_frontend", MagicMock())

    statuses = []
    while state["remaining"]:
        # claim_due_source_change_jobs increments before repository_dispatch.
        state["attempt_count"] += 1
        state["dispatch_generation"] += 1
        state["max_seen"] = max(state["max_seen"], state["attempt_count"])
        assert state["attempt_count"] < 5
        result = data_sync.run_change_event(
            source="netfile",
            change_id="a" * 64,
            dispatch_generation=state["dispatch_generation"],
            enrich=True,
        )
        statuses.append(result["status"])

    assert statuses == ["continued"] * 6 + ["completed"]
    assert state["max_seen"] == 1
    assert data_sync.continue_source_change_job.call_count == 6
    data_sync.retry_source_change_job.assert_not_called()


def test_coordinator_does_not_guess_incomplete_state_from_local_counters():
    assert data_sync._retryable_incomplete({"errors": 1}) is False
    assert data_sync._retryable_incomplete({"failed": 1}) is False
    assert data_sync._retryable_incomplete({
        "errors": 1,
        "retryable_incomplete": True,
    }) is True


@pytest.mark.parametrize(
    ("enrichment_name", "reason"),
    [
        ("meeting_summary_generation", "meeting summary generation failed"),
        ("orientation_generation", "orientation preview generation failed"),
        ("recap_generation", "meeting recap generation failed"),
        ("comment_summary_generation", "comment summary generation failed"),
        ("transcript_windowing", "transcript windowing failed"),
        ("transcript_vote_extraction", "transcript vote extraction failed"),
        ("summary_generation", "agenda item summary generation failed"),
        ("vote_explainer_generation", "vote explainer generation failed"),
        ("theme_extraction", "theme extraction failed"),
        ("conflict_scanning", "meeting conflict scan failed"),
        ("donor_classification", "donor classification failed"),
        (
            "filing_period_briefing_generation",
            "filing-period briefing failed",
        ),
    ],
)
def test_each_partial_enrichment_contract_blocks_terminal_ack(
    monkeypatch,
    enrichment_name,
    reason,
):
    """Coordinator consumes only the common explicit incomplete contract."""
    _configure_event(monkeypatch, base_completed=True)
    base = MagicMock()
    monkeypatch.setattr(data_sync, "run_sync", base)
    monkeypatch.setattr(
        data_sync,
        "run_downstream",
        MagicMock(return_value=[{
            "enrichment": enrichment_name,
            "status": "completed",
            "errors": 1,
            "retryable_incomplete": True,
            "incomplete_count": 1,
            "incomplete_reasons": [reason],
        }]),
    )

    result = _run_change_event(
        source="netfile", change_id="a" * 64, enrich=True,
    )

    assert result["status"] == "failed"
    assert result["phase"] == "enrichment"
    assert reason in result["error"]
    base.assert_not_called()
    data_sync.retry_source_change_job.assert_called_once()
    data_sync.complete_source_change_job.assert_not_called()


def test_enrichment_retry_resumes_after_completed_base(monkeypatch):
    _configure_event(monkeypatch, base_completed=True)
    base = MagicMock()
    monkeypatch.setattr(data_sync, "run_sync", base)
    monkeypatch.setattr(
        data_sync,
        "run_downstream",
        MagicMock(return_value=[{
            "enrichment": "donor_classification",
            "status": "completed",
        }]),
    )

    result = _run_change_event(
        source="netfile", change_id="a" * 64, enrich=True,
    )

    assert result["status"] == "completed"
    base.assert_not_called()
    data_sync.complete_source_change_job.assert_called_once()


def test_budget_skip_releases_event_and_exits_source_phase(monkeypatch):
    _configure_event(monkeypatch)
    monkeypatch.setattr(
        data_sync,
        "run_sync",
        MagicMock(return_value={
            "status": "skipped",
            "skip_reason": "cap",
            "error": "event budget exhausted",
        }),
    )
    downstream = MagicMock()
    monkeypatch.setattr(data_sync, "run_downstream", downstream)

    result = _run_change_event(
        source="netfile", change_id="a" * 64, enrich=True,
    )

    assert result["status"] == "failed"
    assert result["phase"] == "source"
    data_sync.retry_source_change_job.assert_called_once()
    downstream.assert_not_called()


def test_final_attempt_failure_is_dead_lettered_and_stays_red(monkeypatch, capsys):
    _configure_event(monkeypatch)
    data_sync.retry_source_change_job.return_value = {
        "status": "dead_letter",
        "attempt_count": 5,
    }
    monkeypatch.setattr(
        data_sync,
        "run_sync",
        MagicMock(return_value={"status": "failed", "error": "poison event"}),
    )
    monkeypatch.setattr(data_sync, "run_downstream", MagicMock())

    result = _run_change_event(
        source="netfile", change_id="a" * 64, enrich=True,
    )

    assert result["status"] == "failed"
    assert "dead-lettered" in capsys.readouterr().out
    data_sync.retry_source_change_job.assert_called_once()
    data_sync.complete_source_change_job.assert_not_called()


def test_completed_base_log_recovers_crash_between_phase_acks(monkeypatch):
    _configure_event(monkeypatch)
    monkeypatch.setattr(
        data_sync,
        "run_sync",
        MagicMock(return_value={"status": "duplicate"}),
    )
    data_sync.get_change_sync_log.return_value = {
        "status": "completed",
        "metadata": {"records_new": 1},
    }
    monkeypatch.setattr(data_sync, "run_downstream", MagicMock(return_value=[]))

    result = _run_change_event(
        source="netfile", change_id="a" * 64, enrich=True,
    )

    assert result["status"] == "completed"
    data_sync.mark_source_change_base_completed.assert_called_once()


def test_incomplete_completed_base_log_is_not_crash_recovered_as_success(
    monkeypatch,
):
    _configure_event(monkeypatch)
    monkeypatch.setattr(
        data_sync,
        "run_sync",
        MagicMock(return_value={"status": "duplicate"}),
    )
    data_sync.get_change_sync_log.return_value = {
        "status": "completed",
        "metadata": {"retryable_incomplete": True, "incomplete_count": 1},
    }
    downstream = MagicMock()
    monkeypatch.setattr(data_sync, "run_downstream", downstream)

    result = _run_change_event(
        source="netfile", change_id="a" * 64, enrich=True,
    )

    assert result["status"] == "failed"
    assert result["phase"] == "source"
    data_sync.retry_source_change_job.assert_called_once()
    data_sync.mark_source_change_base_completed.assert_not_called()
    data_sync.complete_source_change_job.assert_not_called()
    downstream.assert_not_called()


def test_active_duplicate_delivery_is_noop(monkeypatch):
    conn = MagicMock()
    monkeypatch.setattr(data_sync, "get_connection", lambda: conn)
    monkeypatch.setattr(data_sync, "claim_source_change_job", MagicMock(return_value=None))
    monkeypatch.setattr(
        data_sync,
        "get_source_change_job",
        MagicMock(return_value={"source": "netfile", "status": "running"}),
    )
    base = MagicMock()
    monkeypatch.setattr(data_sync, "run_sync", base)

    result = _run_change_event(
        source="netfile", change_id="a" * 64, enrich=True,
    )

    assert result["status"] == "duplicate"
    base.assert_not_called()


@pytest.mark.parametrize(
    ("status", "stored_generation"),
    [("retry_wait", 1), ("dead_letter", 1), ("dispatched", 2)],
)
def test_direct_or_stale_delivery_cannot_claim_or_reverse_attempt(
    monkeypatch,
    status,
    stored_generation,
):
    conn = MagicMock()
    claim = MagicMock(return_value=None)
    continuation = MagicMock()
    retry = MagicMock()
    monkeypatch.setattr(data_sync, "get_connection", lambda: conn)
    monkeypatch.setattr(data_sync, "claim_source_change_job", claim)
    monkeypatch.setattr(
        data_sync,
        "get_source_change_job",
        MagicMock(return_value={
            "source": "netfile",
            "status": status,
            "attempt_count": 4,
            "dispatch_generation": stored_generation,
        }),
    )
    monkeypatch.setattr(data_sync, "continue_source_change_job", continuation)
    monkeypatch.setattr(data_sync, "retry_source_change_job", retry)
    base = MagicMock()
    monkeypatch.setattr(data_sync, "run_sync", base)

    result = _run_change_event(
        source="netfile", change_id="a" * 64, enrich=True,
    )

    assert result["status"] == "failed"
    assert result["phase"] == "claim"
    assert claim.call_args.kwargs["dispatch_generation"] == 1
    base.assert_not_called()
    continuation.assert_not_called()
    retry.assert_not_called()


def test_change_event_cli_exits_nonzero_on_retryable_failure(monkeypatch):
    monkeypatch.setattr(
        data_sync,
        "run_change_event",
        MagicMock(return_value={"status": "failed", "error": "enrichment failed"}),
    )
    monkeypatch.setattr(
        data_sync.sys,
        "argv",
        [
            "data_sync.py", "--source", "netfile", "--change-id", "a" * 64,
            "--dispatch-generation", "1",
            "--enrich",
        ],
    )

    with pytest.raises(SystemExit) as exc:
        data_sync.main()

    assert exc.value.code == 1


def test_database_claim_and_retry_use_atomic_migration_functions():
    conn, cur = _connection()
    cur.fetchone.side_effect = [
        {"change_id": "a" * 64, "status": "running"},
        {"change_id": "a" * 64, "status": "retry_wait"},
        {"change_id": "a" * 64, "status": "retry_wait"},
    ]

    claimed = claim_source_change_job(
        conn,
        change_id="a" * 64,
        source="netfile",
        dispatch_generation=1,
        pipeline_run_id="123",
    )
    continued = continue_source_change_job(
        conn,
        change_id="a" * 64,
        pipeline_run_id="123",
        dispatch_generation=1,
    )
    retried = retry_source_change_job(
        conn,
        change_id="a" * 64,
        error="failed",
        dispatch_generation=1,
    )

    assert claimed["status"] == "running"
    assert continued["status"] == "retry_wait"
    assert retried["status"] == "retry_wait"
    sql_calls = [call.args[0] for call in cur.execute.call_args_list]
    assert any("claim_source_change_job" in sql for sql in sql_calls)
    assert any("continue_source_change_job" in sql for sql in sql_calls)
    assert any("retry_source_change_job" in sql for sql in sql_calls)


def test_migration_has_bounded_private_outbox_state_machine():
    sql = (
        Path(__file__).parents[1]
        / "src" / "migrations" / "127_source_change_jobs.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS source_change_jobs" in sql
    assert "base_completed_at" in sql
    assert "max_attempts INTEGER NOT NULL DEFAULT 5" in sql
    assert "'dead_letter'" in sql
    assert "claim_due_source_change_jobs" in sql
    assert "retry_source_change_job" in sql
    assert "continue_source_change_job" in sql
    assert "TO service_role" in sql
    # Only the exact charged dispatch can start or transition a worker.
    claim_body = sql.split(
        "CREATE OR REPLACE FUNCTION claim_source_change_job", 1
    )[1].split("$$;", 1)[0]
    assert "j.status = 'dispatched'" in claim_body
    assert "j.dispatch_generation = p_dispatch_generation" in claim_body
    assert "j.lease_expires_at > NOW()" in claim_body
    assert "retry_wait" not in claim_body
    assert "dead_letter" not in claim_body
    for function_name in (
        "mark_source_change_base_completed",
        "retry_source_change_job",
        "continue_source_change_job",
        "complete_source_change_job",
    ):
        body = sql.split(
            f"CREATE OR REPLACE FUNCTION {function_name}", 1
        )[1].split("$$;", 1)[0]
        assert "pipeline_run_id IS NOT DISTINCT FROM p_pipeline_run_id" in body
        assert "j.dispatch_generation = p_dispatch_generation" in body
        assert "j.lease_expires_at > NOW()" in body
    assert "attempt_count = GREATEST(j.attempt_count - 1, 0)" in sql
