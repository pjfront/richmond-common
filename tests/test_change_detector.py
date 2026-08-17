"""Regression tests for change-detector dispatch accounting.

All network and Supabase state operations are mocked. These tests never touch
the live Richmond Commons project.
"""

from unittest.mock import MagicMock
import urllib.error

import pytest

import change_detector


_REAL_CLAIM_DUE_CHANGE_JOBS = change_detector.claim_due_change_jobs


@pytest.fixture(autouse=True)
def _durable_outbox(monkeypatch):
    """Keep detector tests offline while preserving enqueue-before-claim flow."""
    queued = {}
    claimed = set()

    def _enqueue(**job):
        queued[job["change_id"]] = job

    def _claim(change_id=None, **_kwargs):
        if change_id is None or change_id not in queued or change_id in claimed:
            return []
        claimed.add(change_id)
        job = queued[change_id]
        return [{
            "change_id": change_id,
            "source": job["source"],
            "status": "dispatched",
            "attempt_count": 1,
            "dispatch_generation": 1,
        }]

    monkeypatch.setattr(change_detector, "enqueue_change_job", _enqueue)
    monkeypatch.setattr(change_detector, "claim_due_change_jobs", _claim)
    monkeypatch.setattr(
        change_detector,
        "release_change_job_for_retry",
        lambda *_args, **_kwargs: {"status": "retry_wait", "attempt_count": 1},
    )


def test_trigger_dispatch_returns_false_for_401(monkeypatch):
    monkeypatch.setattr(change_detector, "GITHUB_TOKEN", "test-token")
    error = urllib.error.HTTPError(
        "https://api.github.test/dispatches",
        401,
        "Unauthorized",
        hdrs=None,
        fp=None,
    )
    monkeypatch.setattr(change_detector.urllib.request, "urlopen", MagicMock(side_effect=error))

    assert change_detector.trigger_dispatch("nextrequest") is False


def test_trigger_dispatch_returns_false_without_token(monkeypatch):
    monkeypatch.setattr(change_detector, "GITHUB_TOKEN", "")
    urlopen = MagicMock()
    monkeypatch.setattr(change_detector.urllib.request, "urlopen", urlopen)

    assert change_detector.trigger_dispatch("nextrequest") is False
    urlopen.assert_not_called()


def test_trigger_dispatch_returns_true_when_github_accepts(monkeypatch):
    monkeypatch.setattr(change_detector, "GITHUB_TOKEN", "test-token")
    response = MagicMock()
    response.__enter__.return_value = response
    urlopen = MagicMock(return_value=response)
    monkeypatch.setattr(change_detector.urllib.request, "urlopen", urlopen)

    change_id = "a" * 64
    assert change_detector.trigger_dispatch(
        "nextrequest",
        change_id=change_id,
        dispatch_generation=1,
    ) is True
    payload = __import__("json").loads(urlopen.call_args.args[0].data)
    assert payload["client_payload"]["change_id"] == change_id
    assert payload["client_payload"]["dispatch_generation"] == 1


def test_change_id_is_deterministic_and_source_scoped():
    fingerprint = {"b": 2, "a": 1}
    first = change_detector.make_change_id("nextrequest", fingerprint)
    assert first == change_detector.make_change_id(
        "nextrequest", {"a": 1, "b": 2}
    )
    assert first != change_detector.make_change_id("netfile", fingerprint)
    assert first != change_detector.make_change_id(
        "nextrequest", fingerprint, "next-generation",
    )
    assert len(first) == 64


def test_outbox_is_persisted_before_github_dispatch(monkeypatch):
    _configure_single_changed_source(monkeypatch)
    events = []
    queued = {}

    def _enqueue(**job):
        events.append("enqueue")
        queued[job["change_id"]] = job

    def _claim(change_id=None, **_kwargs):
        events.append("claim")
        if change_id is None:
            return []
        return [{
            "change_id": change_id,
            "source": queued[change_id]["source"],
            "status": "dispatched",
            "attempt_count": 1,
            "dispatch_generation": 1,
        }]

    def _dispatch(*_args, **_kwargs):
        events.append("dispatch")
        return True

    monkeypatch.setattr(change_detector, "enqueue_change_job", _enqueue)
    monkeypatch.setattr(change_detector, "claim_due_change_jobs", _claim)
    monkeypatch.setattr(change_detector, "trigger_dispatch", _dispatch)
    monkeypatch.setattr(change_detector, "write_state", MagicMock())

    summary = change_detector.check_all()

    assert summary["dispatched"] == 1
    assert events.index("enqueue") < events.index("dispatch")


def test_non_nextrequest_outbox_keeps_five_attempt_budget(monkeypatch):
    assert change_detector._max_change_attempts("nextrequest") == 3
    assert change_detector._max_change_attempts("netfile") == 5


def test_retry_backlog_drains_one_job_per_detector_poll(monkeypatch):
    rpc = MagicMock(return_value=[])
    monkeypatch.setattr(change_detector, "_outbox_rpc", rpc)

    _REAL_CLAIM_DUE_CHANGE_JOBS()

    assert rpc.call_args.args[1]["p_change_id"] is None
    assert rpc.call_args.args[1]["p_limit"] == 1


def test_due_stale_job_is_dispatched_without_new_fingerprint(monkeypatch):
    stale = {
        "change_id": "b" * 64,
        "source": "nextrequest",
        "status": "dispatched",
        "attempt_count": 2,
        "dispatch_generation": 2,
    }
    monkeypatch.setattr(
        change_detector,
        "claim_due_change_jobs",
        lambda change_id=None, **_kwargs: [stale] if change_id is None else [],
    )
    monkeypatch.setattr(
        change_detector,
        "WATCHERS",
        {"nextrequest": (lambda: {"total_count": 1}, "nextrequest")},
    )
    monkeypatch.setattr(
        change_detector,
        "read_state",
        lambda _source: {"fingerprint": {"total_count": 1}},
    )
    monkeypatch.setattr(change_detector, "write_state", MagicMock())
    dispatch = MagicMock(return_value=True)
    monkeypatch.setattr(change_detector, "trigger_dispatch", dispatch)

    summary = change_detector.check_all()

    assert summary["changed"] == 0
    assert summary["dispatched"] == 1
    dispatch.assert_called_once_with(
        "nextrequest",
        change_id="b" * 64,
        dispatch_generation=2,
    )


def test_exhausted_due_job_is_dead_lettered_without_dispatch(monkeypatch):
    dead = {
        "change_id": "c" * 64,
        "source": "netfile",
        "status": "dead_letter",
        "attempt_count": 5,
    }
    summary = {
        "dispatched": 0,
        "errors": 0,
        "dispatch_errors": 0,
        "outbox_errors": 0,
        "dead_lettered": 0,
    }
    dispatch = MagicMock()
    monkeypatch.setattr(change_detector, "trigger_dispatch", dispatch)

    change_detector._dispatch_claimed_jobs([dead], summary)

    assert summary["dead_lettered"] == 1
    assert summary["errors"] == 1
    dispatch.assert_not_called()


def _configure_single_changed_source(monkeypatch):
    monkeypatch.setattr(
        change_detector,
        "WATCHERS",
        {"nextrequest": (lambda: {"total_count": 2}, "nextrequest")},
    )
    monkeypatch.setattr(
        change_detector,
        "read_state",
        lambda _source: {"fingerprint": {"total_count": 1}},
    )


def test_failed_dispatch_is_error_but_durable_state_advances(monkeypatch):
    _configure_single_changed_source(monkeypatch)
    monkeypatch.setattr(change_detector, "trigger_dispatch", lambda *_args, **_kwargs: False)
    write_state = MagicMock()
    monkeypatch.setattr(change_detector, "write_state", write_state)

    summary = change_detector.check_all()

    assert summary == {
        "checked": 1,
        "changed": 1,
        "dispatched": 0,
        "errors": 1,
        "check_errors": 0,
        "dispatch_errors": 1,
        "state_errors": 0,
        "outbox_errors": 0,
        "dead_lettered": 0,
    }
    write_state.assert_called_once_with(
        "nextrequest", {"total_count": 2}, changed=True,
    )


def test_successful_dispatch_counts_and_advances_state(monkeypatch):
    _configure_single_changed_source(monkeypatch)
    monkeypatch.setattr(change_detector, "trigger_dispatch", lambda *_args, **_kwargs: True)
    write_state = MagicMock()
    monkeypatch.setattr(change_detector, "write_state", write_state)

    summary = change_detector.check_all()

    assert summary["dispatched"] == 1
    assert summary["dispatch_errors"] == 0
    assert summary["errors"] == 0
    write_state.assert_called_once_with(
        "nextrequest", {"total_count": 2}, changed=True,
    )


def test_dry_run_does_not_mutate_watcher_state(monkeypatch):
    _configure_single_changed_source(monkeypatch)
    monkeypatch.setattr(change_detector, "trigger_dispatch", lambda *_args, **_kwargs: True)
    write_state = MagicMock()
    monkeypatch.setattr(change_detector, "write_state", write_state)

    summary = change_detector.check_all(dry_run=True)

    assert summary["dispatched"] == 1
    write_state.assert_not_called()


def test_state_read_failure_never_seeds_or_dispatches(monkeypatch):
    monkeypatch.setattr(
        change_detector,
        "WATCHERS",
        {"nextrequest": (lambda: {"total_count": 2}, "nextrequest")},
    )
    monkeypatch.setattr(
        change_detector,
        "read_state",
        MagicMock(side_effect=change_detector.StateStoreError("database down")),
    )
    dispatch = MagicMock()
    write_state = MagicMock()
    monkeypatch.setattr(change_detector, "trigger_dispatch", dispatch)
    monkeypatch.setattr(change_detector, "write_state", write_state)

    summary = change_detector.check_all()

    assert summary["state_errors"] == 1
    assert summary["errors"] == 1
    dispatch.assert_not_called()
    write_state.assert_not_called()


def test_dispatch_ack_failure_is_actionable_and_reuses_change_id(monkeypatch):
    _configure_single_changed_source(monkeypatch)
    seen_ids = []
    enqueue_attempts = []
    queued = {}

    def _dispatch(_source, **kwargs):
        seen_ids.append(kwargs["change_id"])
        return True

    def _enqueue(**job):
        enqueue_attempts.append(job["change_id"])
        queued.setdefault(job["change_id"], job)

    claimed = set()

    def _claim(change_id=None, **_kwargs):
        if change_id is None or change_id in claimed:
            return []
        claimed.add(change_id)
        return [{
            "change_id": change_id,
            "source": queued[change_id]["source"],
            "status": "dispatched",
            "attempt_count": 1,
            "dispatch_generation": 1,
        }]

    monkeypatch.setattr(change_detector, "trigger_dispatch", _dispatch)
    monkeypatch.setattr(change_detector, "enqueue_change_job", _enqueue)
    monkeypatch.setattr(change_detector, "claim_due_change_jobs", _claim)
    monkeypatch.setattr(
        change_detector,
        "write_state",
        MagicMock(side_effect=change_detector.StateStoreError("ack failed")),
    )

    first = change_detector.check_all()
    second = change_detector.check_all()

    assert first["dispatched"] == 1 and first["state_errors"] == 1
    assert second["dispatched"] == 0 and second["state_errors"] == 1
    assert len(queued) == 1
    assert enqueue_attempts[0] == enqueue_attempts[1]
    assert seen_ids == [next(iter(queued))]


def test_oscillating_fingerprint_gets_a_new_id_after_each_state_advance(monkeypatch):
    observations = iter([
        {"total_count": 2},
        {"total_count": 1},
        {"total_count": 2},
    ])
    state = {
        "fingerprint": {"total_count": 1},
        "last_checked_at": "generation-0",
    }
    enqueued_ids = []
    generation = 0

    monkeypatch.setattr(
        change_detector,
        "WATCHERS",
        {"nextrequest": (lambda: next(observations), "nextrequest")},
    )
    monkeypatch.setattr(change_detector, "read_state", lambda _source: dict(state))

    def _write(_source, fingerprint, changed=False):
        nonlocal generation
        generation += 1
        state["fingerprint"] = dict(fingerprint)
        state["last_checked_at"] = f"generation-{generation}"

    def _enqueue(**job):
        enqueued_ids.append(job["change_id"])

    monkeypatch.setattr(change_detector, "write_state", _write)
    monkeypatch.setattr(change_detector, "enqueue_change_job", _enqueue)
    monkeypatch.setattr(change_detector, "claim_due_change_jobs", lambda *_args, **_kwargs: [])

    for _ in range(3):
        change_detector.check_all()

    assert len(enqueued_ids) == 3
    assert len(set(enqueued_ids)) == 3
    assert enqueued_ids[0] != enqueued_ids[2]


def test_partial_fingerprint_preserves_unobserved_keys_until_recovery(monkeypatch):
    stored = {
        "fingerprint": {
            "type_0_count": 10,
            "paper_filing_hash": "old-hash",
            "paper_filing_count": 50,
        }
    }
    observations = iter([
        {"type_0_count": 10},
        {
            "type_0_count": 10,
            "paper_filing_hash": "new-hash",
            "paper_filing_count": 51,
        },
    ])
    monkeypatch.setattr(
        change_detector,
        "WATCHERS",
        {"netfile": (lambda: next(observations), "netfile")},
    )
    monkeypatch.setattr(change_detector, "read_state", lambda _source: stored)

    def _write(_source, fingerprint, changed=False):
        stored["fingerprint"] = dict(fingerprint)

    monkeypatch.setattr(change_detector, "write_state", _write)
    dispatch = MagicMock(return_value=True)
    monkeypatch.setattr(change_detector, "trigger_dispatch", dispatch)

    first = change_detector.check_all()
    assert first["dispatched"] == 0
    assert stored["fingerprint"]["paper_filing_hash"] == "old-hash"

    second = change_detector.check_all()
    assert second["dispatched"] == 1
    dispatch.assert_called_once()


def test_socrata_dispatch_failure_keeps_durably_queued_fingerprint(monkeypatch):
    monkeypatch.setattr(
        change_detector,
        "WATCHERS",
        {
            "socrata": (
                lambda: {"expenditures": 2, "payroll": 2},
                None,
            ),
        },
    )
    monkeypatch.setattr(
        change_detector,
        "read_state",
        lambda _source: {"fingerprint": {"expenditures": 1, "payroll": 1}},
    )
    monkeypatch.setattr(
        change_detector,
        "trigger_dispatch",
        lambda source, **_kwargs: source == "socrata_expenditures",
    )
    write_state = MagicMock()
    monkeypatch.setattr(change_detector, "write_state", write_state)

    summary = change_detector.check_all()

    assert summary["dispatched"] == 1
    assert summary["dispatch_errors"] == 1
    assert summary["errors"] == 1
    # Both observations are durably queued before dispatch, so the watcher can
    # acknowledge both even though GitHub rejected one immediate attempt.
    write_state.assert_called_once_with(
        "socrata", {"expenditures": 2, "payroll": 2}, changed=True,
    )


def test_main_exits_nonzero_for_any_dispatch_failure(monkeypatch):
    monkeypatch.setattr(change_detector, "SUPABASE_URL", "https://example.test")
    monkeypatch.setattr(change_detector, "SUPABASE_KEY", "test-key")
    monkeypatch.setattr(
        change_detector,
        "check_all",
        lambda **_kwargs: {
            "checked": 5,
            "changed": 1,
            "dispatched": 0,
            "errors": 1,
            "check_errors": 0,
            "dispatch_errors": 1,
            "state_errors": 0,
            "outbox_errors": 0,
            "dead_lettered": 0,
        },
    )
    monkeypatch.setattr(change_detector.sys, "argv", ["change_detector.py"])

    with pytest.raises(SystemExit) as exc:
        change_detector.main()

    assert exc.value.code == 1
