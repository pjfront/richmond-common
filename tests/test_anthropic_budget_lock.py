"""Tests for src/anthropic_budget_lock.py — the centralized Anthropic API rails."""
from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

import anthropic_budget_lock as gate  # noqa: E402


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    """Each test starts from a known-clean state."""
    monkeypatch.delenv("RICHMOND_API_BUDGET_LOCK", raising=False)
    monkeypatch.delenv("RICHMOND_API_MONTHLY_CAP_USD", raising=False)
    monkeypatch.delenv("RICHMOND_EVENT_BUDGET_USD", raising=False)
    monkeypatch.delenv("RICHMOND_EVENT_TYPE", raising=False)
    gate._mtd_cache["value"] = None
    gate._mtd_cache["fetched_at"] = 0.0
    with gate._process_spend_lock:
        gate._process_spend_usd = 0.0
    yield


class TestPricing:
    def test_sonnet_45(self):
        assert gate._price_for_model("claude-sonnet-4-5") == (3.0, 15.0)

    def test_sonnet_4_dated(self):
        assert gate._price_for_model("claude-sonnet-4-20250514") == (3.0, 15.0)

    def test_haiku(self):
        # Corrected 2026-07: Haiku 4.5 is $1/$5 per MTok (the old 0.80/4.0
        # values undercounted, violating the map's conservative contract).
        assert gate._price_for_model("claude-haiku-4-5") == (1.0, 5.0)

    def test_sonnet_5(self):
        assert gate._price_for_model("claude-sonnet-5") == (3.0, 15.0)

    def test_opus(self):
        assert gate._price_for_model("claude-opus-4") == (15.0, 75.0)

    def test_unknown_uses_fallback(self):
        assert gate._price_for_model("future-model-x") == gate._FALLBACK_PRICING

    def test_approx_cost_sonnet(self):
        # 1M input + 1M output on Sonnet 4.5 = $18
        assert gate._approx_cost("claude-sonnet-4-5", 1_000_000, 1_000_000) == pytest.approx(18.0)

    def test_approx_cost_small(self):
        # 10k input + 5k output on Sonnet = $0.03 + $0.075 = $0.105
        assert gate._approx_cost("claude-sonnet-4-5", 10_000, 5_000) == pytest.approx(0.105)


class TestCaps:
    def test_default_monthly_cap(self):
        assert gate._monthly_cap_usd() == 5.0

    def test_monthly_cap_from_env(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_API_MONTHLY_CAP_USD", "12.50")
        assert gate._monthly_cap_usd() == 12.5

    def test_monthly_cap_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_API_MONTHLY_CAP_USD", "not-a-number")
        assert gate._monthly_cap_usd() == 5.0

    def test_event_cap_unset(self):
        assert gate._event_cap_usd() is None

    def test_event_cap_from_env(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_EVENT_BUDGET_USD", "0.50")
        assert gate._event_cap_usd() == 0.50


class TestEnforcement:
    def test_kill_switch_raises(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_API_BUDGET_LOCK", "true")
        with pytest.raises(gate.AnthropicBudgetLockError):
            gate._enforce_caps_pre_call("claude-sonnet-4-5")

    def test_monthly_cap_raises_when_exceeded(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_API_MONTHLY_CAP_USD", "1.00")
        with patch.object(gate, "_month_to_date_spend_usd", return_value=1.50):
            with pytest.raises(gate.AnthropicMonthlyCapError):
                gate._enforce_caps_pre_call("claude-sonnet-4-5")

    def test_monthly_cap_passes_when_under(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_API_MONTHLY_CAP_USD", "5.00")
        with patch.object(gate, "_month_to_date_spend_usd", return_value=2.50):
            gate._enforce_caps_pre_call("claude-sonnet-4-5")  # should not raise

    def test_event_cap_raises_when_exceeded(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_EVENT_BUDGET_USD", "1.00")
        gate._add_process_spend(1.50)
        with patch.object(gate, "_month_to_date_spend_usd", return_value=0.0):
            with pytest.raises(gate.AnthropicEventCapError):
                gate._enforce_caps_pre_call("claude-sonnet-4-5")

    def test_event_cap_unset_does_not_check(self, monkeypatch):
        gate._add_process_spend(100.0)  # would blow any per-event cap
        with patch.object(gate, "_month_to_date_spend_usd", return_value=0.0):
            gate._enforce_caps_pre_call("claude-sonnet-4-5")  # no event cap → no raise


class TestProcessSpend:
    def test_starts_at_zero(self):
        assert gate._process_spend() == 0.0

    def test_add_accumulates(self):
        gate._add_process_spend(0.10)
        gate._add_process_spend(0.25)
        assert gate._process_spend() == pytest.approx(0.35)


class TestCallerDetection:
    def test_returns_module_name(self):
        # Called from this test module; _detect_caller should walk past
        # anthropic_budget_lock and land here.
        caller = gate._detect_caller()
        assert "test_anthropic_budget_lock" in caller or caller != "unknown"


class TestBatchCostLogging:
    """Batch spend bypasses the synchronous Messages.create gate (async
    results), so it must be logged explicitly by batch collectors. These
    tests cover the log_batch_cost / log_batch_results_cost helpers."""

    def test_log_batch_cost_applies_discount(self):
        # 1M in + 1M out on Sonnet = $18 list; batch is 50% off → $9.
        logged = {}

        def _capture(model, i, o, cost, caller, extra=None):
            logged.update(
                model=model, i=i, o=o, cost=cost, caller=caller, extra=extra
            )

        with patch.object(gate, "_log_cost", _capture):
            cost = gate.log_batch_cost(
                model="claude-sonnet-4-5",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
                caller="minutes_extraction",
                batch_id="batch_abc",
            )
        assert cost == pytest.approx(9.0)
        assert logged["cost"] == pytest.approx(9.0)
        assert logged["caller"] == "minutes_extraction"
        assert logged["extra"]["batch"] is True
        assert logged["extra"]["batch_id"] == "batch_abc"

    def test_log_batch_cost_adds_process_spend(self):
        with patch.object(gate, "_log_cost"):
            gate.log_batch_cost(
                model="claude-sonnet-4-5",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            )
        # $9 batch cost should accumulate toward the per-event cap.
        assert gate._process_spend() == pytest.approx(9.0)

    def test_log_batch_results_cost_sums_succeeded_only(self):
        results = [
            {"result": {"type": "succeeded", "message": {
                "model": "claude-sonnet-4-5",
                "usage": {"input_tokens": 1_000_000, "output_tokens": 0}}}},
            {"result": {"type": "errored", "message": {
                "model": "claude-sonnet-4-5",
                "usage": {"input_tokens": 9_000_000, "output_tokens": 0}}}},
            {"result": {"type": "succeeded", "message": {
                "model": "claude-sonnet-4-5",
                "usage": {"input_tokens": 1_000_000, "output_tokens": 0}}}},
        ]
        with patch.object(gate, "_log_cost"):
            cost = gate.log_batch_results_cost(results, batch_id="b1")
        # Only the 2 succeeded rows count: 2M input on Sonnet = $6 list,
        # halved for batch = $3. The errored 9M is excluded.
        assert cost == pytest.approx(3.0)

    def test_log_batch_results_cost_empty_is_zero(self):
        with patch.object(gate, "_log_cost") as mock_log:
            cost = gate.log_batch_results_cost([], batch_id="b0")
        assert cost == 0.0
        mock_log.assert_not_called()

    def test_log_batch_results_cost_never_raises_on_bad_input(self):
        # Malformed rows must not break the data pipeline.
        with patch.object(gate, "_log_cost"):
            cost = gate.log_batch_results_cost(
                [{"garbage": True}, None], batch_id="bx"
            )
        assert cost == 0.0


class TestCallerDetectionMain:
    def test_main_resolves_to_filename(self):
        """A frame whose __name__ is '__main__' should attribute to the
        script's filename, not the unhelpful '__main__' bucket."""
        import types

        fake_frame = types.SimpleNamespace(
            f_globals={"__name__": "__main__", "__file__": "/x/y/netfile_paper_extractor.py"},
            f_back=None,
        )
        with patch.object(gate.sys, "_getframe", return_value=fake_frame):
            assert gate._detect_caller() == "netfile_paper_extractor"


class TestMTDCache:
    def test_cache_hit_skips_query(self):
        gate._mtd_cache["value"] = 2.5
        gate._mtd_cache["fetched_at"] = __import__("time").time()
        with patch.object(gate, "_query_mtd_spend") as mock_query:
            value = gate._month_to_date_spend_usd()
        mock_query.assert_not_called()
        assert value == 2.5

    def test_cache_miss_queries(self):
        gate._mtd_cache["value"] = None
        gate._mtd_cache["fetched_at"] = 0.0
        with patch.object(gate, "_query_mtd_spend", return_value=1.25) as mock_query:
            value = gate._month_to_date_spend_usd()
        mock_query.assert_called_once()
        assert value == 1.25

    def test_db_error_returns_last_cached(self):
        gate._mtd_cache["value"] = 3.0
        gate._mtd_cache["fetched_at"] = 0.0  # expired
        with patch.object(gate, "_query_mtd_spend", return_value=None):
            value = gate._month_to_date_spend_usd()
        assert value == 3.0
