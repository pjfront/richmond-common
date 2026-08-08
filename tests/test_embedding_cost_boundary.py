"""Focused fail-closed cost-boundary tests for OpenAI embeddings."""
from __future__ import annotations

import sys
import uuid
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

SRC = Path(__file__).parent.parent / "src"
ROOT = SRC.parent
sys.path.insert(0, str(SRC))

import embedding_generator as embeddings  # noqa: E402
import llm_budget_lock as gate  # noqa: E402


@pytest.fixture(autouse=True)
def clean_budget_state(monkeypatch):
    for name in (
        "OPENAI_API_KEY",
        "RICHMOND_API_BUDGET_LOCK",
        "RICHMOND_API_MONTHLY_CAP_USD",
        "RICHMOND_EVENT_BUDGET_USD",
        "RICHMOND_EVENT_TYPE",
    ):
        monkeypatch.delenv(name, raising=False)
    with gate._mtd_cache_lock:
        gate._mtd_cache["value"] = None
        gate._mtd_cache["fetched_at"] = 0.0
        gate._mtd_cache["poisoned"] = False
    with gate._process_spend_lock:
        gate._process_spend_usd = 0.0
        gate._process_spend_reservations.clear()
    yield


def _response(*, total_tokens=100, count=1):
    return SimpleNamespace(
        usage=SimpleNamespace(total_tokens=total_tokens),
        data=[
            SimpleNamespace(embedding=[0.125] * embeddings.DIMENSIONS)
            for _ in range(count)
        ],
    )


def _mock_accounting(monkeypatch, *, reservation_id=None, settled=True, logged=True):
    reservation_id = reservation_id or uuid.uuid4()
    reserve = MagicMock(return_value=reservation_id)
    settle = MagicMock(return_value=settled)
    log = MagicMock(return_value=logged)
    cached = MagicMock()
    monkeypatch.setattr(gate, "_reserve_monthly_budget", reserve)
    monkeypatch.setattr(gate, "_settle_cost_reservation", settle)
    monkeypatch.setattr(gate, "_log_cost", log)
    monkeypatch.setattr(gate, "_add_cached_mtd_spend", cached)
    return SimpleNamespace(
        reservation_id=reservation_id,
        reserve=reserve,
        settle=settle,
        log=log,
        cached=cached,
    )


def test_official_embedding_price_is_two_cents_per_million():
    assert embeddings._embedding_cost(1_000_000) == pytest.approx(0.02)


def test_web_reservation_rpcs_are_atomic_service_role_only_and_mirrored():
    source = SRC / "migrations" / "129_llm_cost_reservations.sql"
    mirror = (
        ROOT
        / "supabase"
        / "migrations"
        / "20260807012900_llm_cost_reservations.sql"
    )
    sql = source.read_text(encoding="utf-8")

    assert source.read_bytes() == mirror.read_bytes()
    assert "pg_advisory_xact_lock" in sql
    assert "CREATE OR REPLACE FUNCTION reserve_llm_cost" in sql
    assert "CREATE OR REPLACE FUNCTION settle_llm_cost_reservation" in sql
    assert "llm_cost_reservations_settlement_shape" in sql
    assert sql.count("\nSECURITY DEFINER\n") == 2
    assert "FROM PUBLIC, anon, authenticated" in sql
    assert sql.count("TO service_role") >= 3
    assert "INSERT INTO pipeline_journal" in sql
    assert "'reservation_id', p_reservation_id::TEXT" in sql
    assert "COALESCE(p_metadata, '{}'::jsonb) || jsonb_build_object" in sql


def test_openai_sdk_retries_are_disabled(monkeypatch):
    constructor = MagicMock(return_value=object())
    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=constructor))
    monkeypatch.setenv("OPENAI_API_KEY", "embedding-key")

    client = embeddings._get_openai_client()

    assert client is constructor.return_value
    constructor.assert_called_once_with(api_key="embedding-key", max_retries=0)


def test_timeout_retains_ceiling_and_blocks_retry_at_event_cap(monkeypatch):
    # 1,000 ASCII bytes reserve 1,000 tokens = $0.00002. Two such ceilings
    # would exceed the $0.00003 per-event cap.
    monkeypatch.setenv("RICHMOND_EVENT_BUDGET_USD", "0.00003")
    accounting = _mock_accounting(monkeypatch)
    client = MagicMock()
    client.embeddings.create.side_effect = TimeoutError("ambiguous provider timeout")
    monkeypatch.setattr(embeddings, "_get_openai_client", MagicMock(return_value=client))

    with pytest.raises(TimeoutError, match="ambiguous provider timeout"):
        embeddings.generate_embeddings(["x" * 1_000])

    assert gate._process_spend() == pytest.approx(0.00002)
    assert gate._process_spend_reservations == {
        accounting.reservation_id: pytest.approx(0.00002)
    }

    with pytest.raises(gate.LLMEventCapError):
        embeddings.generate_embeddings(["x" * 1_000])

    assert accounting.reserve.call_count == 1
    assert client.embeddings.create.call_count == 1


def test_success_replaces_projected_ceiling_with_usage_cost(monkeypatch):
    accounting = _mock_accounting(monkeypatch)
    client = MagicMock()
    client.embeddings.create.return_value = _response(total_tokens=100)
    monkeypatch.setattr(embeddings, "_get_openai_client", MagicMock(return_value=client))

    result = embeddings.generate_embeddings(["x" * 1_000])

    assert len(result[0]) == embeddings.DIMENSIONS
    assert gate._process_spend() == pytest.approx(0.000002)
    assert accounting.reservation_id not in gate._process_spend_reservations
    accounting.settle.assert_called_once_with(
        accounting.reservation_id,
        pytest.approx(0.000002),
        metadata=expect_embedding_metadata(100),
    )
    assert accounting.log.call_args.kwargs["extra"]["reservation_id"] == str(
        accounting.reservation_id
    )
    accounting.cached.assert_called_once_with(pytest.approx(0.000002))


def expect_embedding_metadata(tokens: int) -> dict[str, object]:
    return {
        "provider": "openai",
        "input_tokens": tokens,
        "output_tokens": 0,
        "price_per_million_tokens": 0.02,
    }


def test_settlement_failure_retains_ceiling_and_poisons_accounting(monkeypatch):
    accounting = _mock_accounting(monkeypatch, settled=False)
    client = MagicMock()
    client.embeddings.create.return_value = _response(total_tokens=100)
    monkeypatch.setattr(embeddings, "_get_openai_client", MagicMock(return_value=client))

    with pytest.raises(embeddings.EmbeddingAccountingError, match="settlement"):
        embeddings.generate_embeddings(["x" * 1_000])

    assert gate._process_spend() == pytest.approx(0.00002)
    assert accounting.reservation_id in gate._process_spend_reservations
    assert gate._mtd_cache["poisoned"] is True
    accounting.cached.assert_not_called()


@pytest.mark.parametrize("invalid_usage", ["100", 0, -1, True, None])
def test_invalid_usage_retains_ceiling_and_never_settles(
    monkeypatch, invalid_usage
):
    accounting = _mock_accounting(monkeypatch)
    client = MagicMock()
    client.embeddings.create.return_value = _response(total_tokens=invalid_usage)
    monkeypatch.setattr(embeddings, "_get_openai_client", MagicMock(return_value=client))

    with pytest.raises(embeddings.EmbeddingAccountingError, match="usage.total_tokens"):
        embeddings.generate_embeddings(["x" * 1_000])

    assert gate._process_spend() == pytest.approx(0.00002)
    assert accounting.reservation_id in gate._process_spend_reservations
    assert gate._mtd_cache["poisoned"] is True
    accounting.settle.assert_not_called()
    accounting.log.assert_not_called()


def test_reservation_failure_skips_the_paid_provider(monkeypatch):
    client = MagicMock()
    monkeypatch.setattr(embeddings, "_get_openai_client", MagicMock(return_value=client))
    monkeypatch.setattr(
        gate,
        "_reserve_monthly_budget",
        MagicMock(side_effect=gate.LLMMonthlyCapError("cap reached")),
    )

    with pytest.raises(gate.LLMMonthlyCapError, match="cap reached"):
        embeddings.generate_embeddings(["Richmond, California"])

    client.embeddings.create.assert_not_called()


def test_all_empty_inputs_are_free(monkeypatch):
    get_client = MagicMock()
    reserve = MagicMock()
    monkeypatch.setattr(embeddings, "_get_openai_client", get_client)
    monkeypatch.setattr(gate, "_reserve_monthly_budget", reserve)

    result = embeddings.generate_embeddings(["", "   "])

    assert result == [[0.0] * embeddings.DIMENSIONS] * 2
    get_client.assert_not_called()
    reserve.assert_not_called()
