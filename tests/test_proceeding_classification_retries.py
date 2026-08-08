"""Bounded retry and starvation tests for proceeding classification."""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from pipelines import enrichments
from llm_budget_lock import LLMEventCapError, LLMUnknownPricingError


def _item(*, attempts: int = 0) -> dict:
    return {
        "id": "item-1",
        "title": "Adopt a public records retention resolution",
        "description": "A sufficiently detailed agenda description.",
        "category": "governance",
        "is_consent_calendar": False,
        "financial_amount": None,
        "resolution_number": "R-1",
        "proceeding_classification_attempts": attempts,
    }


def _connection(
    *,
    pending: int = 1,
    pending_remaining: int = 0,
    items: list[dict] | None = None,
):
    conn = MagicMock()
    cur = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cur
    cur.fetchone.side_effect = [(pending,), (pending_remaining,)]
    cur.fetchall.return_value = items if items is not None else [_item()]
    cur.rowcount = 1
    return conn, cur


def _install_client(monkeypatch, *, response=None, error: Exception | None = None):
    client = MagicMock()
    if error is not None:
        client.messages.create.side_effect = error
    else:
        client.messages.create.return_value = response or SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="resolution")],
        )
    monkeypatch.setitem(
        sys.modules,
        "llm_client",
        SimpleNamespace(LLMClient=lambda: client, ROUTINE_MODEL="deepseek-v4-flash"),
    )
    return client


def test_selection_is_bounded_ordered_and_excludes_dead_letters(monkeypatch):
    conn, cur = _connection()
    _install_client(monkeypatch)

    result = enrichments.sync_proceeding_classification(conn, "0660620")

    claim_sql = [
        call.args[0]
        for call in cur.execute.call_args_list
        if "WITH candidates AS" in call.args[0]
    ][0]
    assert "proceeding_classification_attempts < 3" in claim_sql
    assert "ORDER BY ai.proceeding_classification_attempts ASC" in claim_sql
    assert "m.meeting_date DESC NULLS LAST" in claim_sql
    assert "FOR UPDATE OF ai SKIP LOCKED" in claim_sql
    assert "proceeding_classification_claim_token = %s" in claim_sql
    assert "LIMIT 100" in claim_sql
    success_sql = [
        call.args[0]
        for call in cur.execute.call_args_list
        if "SET proceeding_type = %s" in call.args[0]
    ][0]
    assert "proceeding_classification_claim_token = %s" in success_sql
    assert result["records_new"] == 1
    assert result["records_updated"] == 0
    assert conn.commit.call_count == 2


def test_invalid_label_records_third_attempt_and_dead_letters(monkeypatch):
    conn, cur = _connection(items=[_item(attempts=2)])
    _install_client(
        monkeypatch,
        response=SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text="maybe-resolution")],
        ),
    )

    result = enrichments.sync_proceeding_classification(conn, "0660620")

    failure_calls = [
        call
        for call in cur.execute.call_args_list
        if "proceeding_classification_last_error" in call.args[0]
    ]
    assert len(failure_calls) == 1
    assert "unexpected label" in failure_calls[0].args[1][0]
    assert result["records_new"] == 0
    assert result["records_updated"] == 1
    assert result["dead_lettered"] == 1
    assert conn.commit.call_count == 2


@pytest.mark.parametrize(
    "response",
    [
        SimpleNamespace(stop_reason="max_tokens", content=[]),
        SimpleNamespace(stop_reason="end_turn", content=[]),
    ],
)
def test_truncated_or_empty_response_consumes_one_bounded_attempt(
    monkeypatch, response
):
    conn, _cur = _connection(items=[_item(attempts=0)])
    _install_client(monkeypatch, response=response)

    result = enrichments.sync_proceeding_classification(conn, "0660620")

    assert result["records_updated"] == 1
    assert result["dead_lettered"] == 0


def test_budget_error_propagates_instead_of_green_completion(monkeypatch):
    conn, cur = _connection()
    _install_client(monkeypatch, error=LLMEventCapError("event cap"))

    with pytest.raises(LLMEventCapError, match="event cap"):
        enrichments.sync_proceeding_classification(conn, "0660620")

    assert not any(
        "proceeding_classification_last_error" in call.args[0]
        for call in cur.execute.call_args_list
    )
    release_sql = [
        call.args[0]
        for call in cur.execute.call_args_list
        if "WHERE proceeding_classification_claim_token = %s" in call.args[0]
        and "RETURNING" not in call.args[0]
    ]
    assert release_sql
    assert conn.commit.call_count == 2


def test_systemic_pricing_error_releases_claim_without_consuming_attempt(
    monkeypatch,
):
    conn, cur = _connection()
    _install_client(
        monkeypatch,
        error=LLMUnknownPricingError("unknown model pricing"),
    )

    with pytest.raises(LLMUnknownPricingError, match="unknown model"):
        enrichments.sync_proceeding_classification(conn, "0660620")

    assert not any(
        "proceeding_classification_last_error" in call.args[0]
        for call in cur.execute.call_args_list
    )
    assert conn.commit.call_count == 2


def test_second_worker_receiving_no_claim_makes_no_duplicate_paid_call(
    monkeypatch,
):
    first_conn, _ = _connection(items=[_item()])
    second_conn, _ = _connection(pending=1, items=[])
    client = _install_client(monkeypatch)

    first = enrichments.sync_proceeding_classification(first_conn, "0660620")
    second = enrichments.sync_proceeding_classification(second_conn, "0660620")

    assert first["records_new"] == 1
    assert second["records_fetched"] == 0
    assert client.messages.create.call_count == 1


def test_101_rows_require_a_healthy_continuation_before_reporting_complete(
    monkeypatch,
):
    first_slice = [{**_item(), "id": f"item-{index}"} for index in range(100)]
    first_conn, _ = _connection(
        pending=101,
        pending_remaining=1,
        items=first_slice,
    )
    second_conn, _ = _connection(
        pending=1,
        pending_remaining=0,
        items=[{**_item(), "id": "item-101"}],
    )
    client = _install_client(monkeypatch)

    first = enrichments.sync_proceeding_classification(
        first_conn, "0660620",
    )
    second = enrichments.sync_proceeding_classification(
        second_conn, "0660620",
    )

    assert first["records_fetched"] == 100
    assert first["pending_remaining"] == 1
    assert first["retryable_incomplete"] is False
    assert first["continuation_required"] is True
    assert first["continuation_count"] == 1
    assert second["records_fetched"] == 1
    assert second["pending_remaining"] == 0
    assert second["retryable_incomplete"] is False
    assert second["continuation_required"] is False
    assert client.messages.create.call_count == 101


def test_no_eligible_rows_makes_no_client(monkeypatch):
    conn, _cur = _connection(pending=0, items=[])
    client_factory = MagicMock()
    monkeypatch.setitem(
        sys.modules,
        "llm_client",
        SimpleNamespace(LLMClient=client_factory, ROUTINE_MODEL="deepseek-v4-flash"),
    )

    result = enrichments.sync_proceeding_classification(conn, "0660620")

    assert result == {
        "records_fetched": 0,
        "records_new": 0,
        "records_updated": 0,
        "pending_remaining": 0,
        "retryable_incomplete": False,
        "incomplete_count": 0,
        "incomplete_reasons": [],
        "continuation_required": False,
        "continuation_count": 0,
        "continuation_reasons": [],
    }
    client_factory.assert_not_called()


def test_migration_defines_bounded_attempt_state():
    sql = (
        Path(__file__).parent.parent
        / "src"
        / "migrations"
        / "130_proceeding_classification_retries.sql"
    ).read_text(encoding="utf-8")
    assert "proceeding_classification_attempts" in sql
    assert "<= 3" in sql
    assert "WHERE proceeding_type IS NULL" in sql
    assert "proceeding_classification_claim_token" in sql
    assert "proceeding_classification_claim_expires_at" in sql
