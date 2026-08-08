"""Tests for src/llm_budget_lock.py — the centralized LLM API rails."""
from __future__ import annotations

import os
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

SRC = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(SRC))

import llm_budget_lock as gate  # noqa: E402


@pytest.fixture(autouse=True)
def reset_state(monkeypatch):
    """Each test starts from a known-clean state."""
    monkeypatch.delenv("RICHMOND_API_BUDGET_LOCK", raising=False)
    monkeypatch.delenv("RICHMOND_API_MONTHLY_CAP_USD", raising=False)
    monkeypatch.delenv("RICHMOND_EVENT_BUDGET_USD", raising=False)
    monkeypatch.delenv("RICHMOND_EVENT_TYPE", raising=False)
    gate._mtd_cache["value"] = None
    gate._mtd_cache["fetched_at"] = 0.0
    gate._mtd_cache["poisoned"] = False
    with gate._process_spend_lock:
        gate._process_spend_usd = 0.0
        gate._process_spend_reservations.clear()
    yield


class TestPricing:
    def test_deepseek_v4_flash(self):
        assert gate._price_for_model("deepseek-v4-flash") == (0.0028, 0.14, 0.28)

    def test_deepseek_v4_pro(self):
        assert gate._price_for_model("deepseek-v4-pro") == (0.003625, 0.435, 0.87)

    def test_kimi_routes(self):
        assert gate._price_for_model("kimi-k2.6") == (0.16, 0.95, 4.00)
        assert gate._price_for_model("moonshotai/kimi-k2.6") == (0.20, 1.20, 4.50)
        assert gate._price_for_model("kimi-k3") == (0.30, 3.00, 15.00)
        assert gate._price_for_model("moonshotai/kimi-k3") == (0.30, 3.00, 15.00)

    def test_openai_benchmark_routes(self):
        assert gate._price_for_model("gpt-5.6-luna") == (0.02, 0.20, 1.20)

    def test_unknown_fails_closed(self):
        with pytest.raises(gate.LLMUnknownPricingError):
            gate._price_for_model("future-model-x")

    def test_approx_cost_deepseek_pro_all_cache_miss(self):
        assert gate._approx_cost("deepseek-v4-pro", 1_000_000, 1_000_000) == pytest.approx(1.305)

    def test_approx_cost_small(self):
        assert gate._approx_cost("deepseek-v4-pro", 10_000, 5_000) == pytest.approx(0.0087)

    def test_cache_discount_only_applies_to_reported_hits(self):
        cost = gate._approx_cost(
            "deepseek-v4-flash",
            1_000_000,
            0,
            cache_read_input_tokens=250_000,
        )
        assert cost == pytest.approx(0.25 * 0.0028 + 0.75 * 0.14)

    def test_luna_cache_writes_use_published_premium(self):
        cost = gate._approx_cost(
            "gpt-5.6-luna",
            200_000,
            0,
            cache_read_input_tokens=40_000,
            cache_write_input_tokens=60_000,
        )
        assert cost == pytest.approx(
            0.04 * 0.02 + 0.06 * 0.25 + 0.10 * 0.20
        )

    def test_luna_long_context_uses_full_request_rates(self):
        cost = gate._approx_cost(
            "gpt-5.6-luna",
            272_001,
            100_000,
            cache_read_input_tokens=100_000,
            cache_write_input_tokens=50_000,
        )
        assert cost == pytest.approx(
            (100_000 / 1_000_000) * 0.04
            + (50_000 / 1_000_000) * 0.50
            + (122_001 / 1_000_000) * 0.40
            + (100_000 / 1_000_000) * 1.80
        )

    def test_cache_partitions_cannot_exceed_input(self):
        with pytest.raises(ValueError, match="cache read/write"):
            gate._approx_cost(
                "gpt-5.6-luna",
                100,
                0,
                cache_read_input_tokens=80,
                cache_write_input_tokens=30,
            )

    def test_negative_tokens_rejected(self):
        with pytest.raises(ValueError):
            gate._approx_cost("deepseek-v4-flash", -1, 0)


class TestCaps:
    def test_default_monthly_cap(self):
        assert gate._monthly_cap_usd() == 5.0

    def test_monthly_cap_from_env(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_API_MONTHLY_CAP_USD", "12.50")
        assert gate._monthly_cap_usd() == 12.5

    def test_monthly_cap_invalid_fails_closed(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_API_MONTHLY_CAP_USD", "not-a-number")
        with pytest.raises(gate.LLMBudgetConfigurationError):
            gate._monthly_cap_usd()

    @pytest.mark.parametrize("value", ["-1", "inf", "-inf", "nan"])
    def test_monthly_cap_nonfinite_or_negative_fails_closed(
        self, value, monkeypatch
    ):
        monkeypatch.setenv("RICHMOND_API_MONTHLY_CAP_USD", value)
        with pytest.raises(gate.LLMBudgetConfigurationError):
            gate._monthly_cap_usd()

    def test_event_cap_unset(self):
        assert gate._event_cap_usd() is None

    def test_event_cap_from_env(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_EVENT_BUDGET_USD", "0.50")
        assert gate._event_cap_usd() == 0.50

    @pytest.mark.parametrize("value", ["nope", "-1", "inf", "-inf", "nan"])
    def test_event_cap_invalid_fails_closed(self, value, monkeypatch):
        monkeypatch.setenv("RICHMOND_EVENT_BUDGET_USD", value)
        with pytest.raises(gate.LLMBudgetConfigurationError):
            gate._event_cap_usd()


class TestEnforcement:
    def test_kill_switch_raises(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_API_BUDGET_LOCK", "true")
        with pytest.raises(gate.LLMBudgetLockError):
            gate._enforce_caps_pre_call("deepseek-v4-pro")

    def test_poisoned_accounting_blocks_before_reservation(self):
        gate._invalidate_mtd_cache(poison=True)
        with patch.object(gate, "_reserve_monthly_budget") as reserve:
            with pytest.raises(gate.LLMBudgetAccountingError, match="prior LLM cost"):
                gate._enforce_caps_pre_call("deepseek-v4-pro")
        reserve.assert_not_called()

    def test_monthly_cap_raises_when_exceeded(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_API_MONTHLY_CAP_USD", "1.00")
        with patch.object(
            gate,
            "_reserve_monthly_budget",
            side_effect=gate.LLMMonthlyCapError("cap"),
        ):
            with pytest.raises(gate.LLMMonthlyCapError):
                gate._enforce_caps_pre_call("deepseek-v4-pro")

    def test_monthly_cap_passes_when_under(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_API_MONTHLY_CAP_USD", "5.00")
        reservation_id = uuid.uuid4()
        with patch.object(
            gate, "_reserve_monthly_budget", return_value=reservation_id
        ) as reserve:
            assert gate._enforce_caps_pre_call("deepseek-v4-pro") == reservation_id
        assert reserve.call_args.args[:3] == ("deepseek-v4-pro", 0.0, 5.0)

    def test_event_cap_raises_when_exceeded(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_EVENT_BUDGET_USD", "1.00")
        gate._add_process_spend(1.50)
        with patch.object(gate, "_reserve_monthly_budget") as reserve:
            with pytest.raises(gate.LLMEventCapError):
                gate._enforce_caps_pre_call("deepseek-v4-pro")
        reserve.assert_not_called()

    def test_event_cap_unset_does_not_check(self, monkeypatch):
        gate._add_process_spend(100.0)  # would blow any per-event cap
        with patch.object(
            gate, "_reserve_monthly_budget", return_value=uuid.uuid4()
        ):
            gate._enforce_caps_pre_call("deepseek-v4-pro")  # no event cap → no raise

    def test_projected_request_is_reserved_at_conservative_ceiling(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_API_MONTHLY_CAP_USD", "1.00")
        with patch.object(
            gate, "_reserve_monthly_budget", return_value=uuid.uuid4()
        ) as reserve:
            gate._enforce_caps_pre_call(
                "moonshotai/kimi-k3",
                estimated_input_tokens=10_000,
                max_output_tokens=1_000,
            )
        assert reserve.call_args.args[1] == pytest.approx(0.045)
        assert reserve.call_args.args[2] == 1.0
        assert gate._process_spend() == pytest.approx(0.045)

    def test_ambiguous_provider_timeout_ceiling_blocks_retry(self, monkeypatch):
        monkeypatch.setenv("RICHMOND_EVENT_BUDGET_USD", "0.0005")
        reservations = [uuid.uuid4(), uuid.uuid4()]
        with patch.object(
            gate, "_reserve_monthly_budget", side_effect=reservations
        ) as reserve:
            gate._enforce_caps_pre_call(
                "deepseek-v4-flash",
                estimated_input_tokens=1_000,
                max_output_tokens=1_000,
            )
            # A timeout leaves the first ceiling in place. The explicit retry
            # must pass the event rail rather than silently sharing one charge.
            with pytest.raises(gate.LLMEventCapError):
                gate._enforce_caps_pre_call(
                    "deepseek-v4-flash",
                    estimated_input_tokens=1_000,
                    max_output_tokens=1_000,
                )
        assert reserve.call_count == 1
        assert gate._process_spend() == pytest.approx(0.00042)


class TestAtomicReservations:
    @staticmethod
    def _db(committed: float = 0.0):
        conn = MagicMock()
        cur = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cur
        cur.fetchone.return_value = (committed,)
        return conn, cur

    def test_reservation_holds_advisory_lock_and_inserts_atomically(self):
        conn, cur = self._db(committed=1.25)
        with patch("db.get_connection", return_value=conn):
            reservation_id = gate._reserve_monthly_budget(
                "deepseek-v4-pro", 0.25, 5.0, caller="unit_test"
            )

        assert isinstance(reservation_id, uuid.UUID)
        sql_calls = [call.args[0] for call in cur.execute.call_args_list]
        assert "pg_advisory_xact_lock" in sql_calls[0]
        assert any("INSERT INTO llm_cost_reservations" in sql for sql in sql_calls)
        conn.commit.assert_called_once()
        conn.close.assert_called_once()

    def test_concurrent_committed_total_cannot_overshoot_cap(self):
        conn, cur = self._db(committed=0.99)
        with patch("db.get_connection", return_value=conn):
            with pytest.raises(gate.LLMMonthlyCapError, match="would be exceeded"):
                gate._reserve_monthly_budget(
                    "deepseek-v4-pro", 0.02, 1.0, caller="unit_test"
                )

        assert not any(
            "INSERT INTO llm_cost_reservations" in call.args[0]
            for call in cur.execute.call_args_list
        )
        conn.rollback.assert_called_once()

    def test_database_failure_refuses_paid_call(self):
        with patch("db.get_connection", side_effect=RuntimeError("offline")):
            with pytest.raises(gate.LLMBudgetAccountingError, match="Cannot connect"):
                gate._reserve_monthly_budget(
                    "deepseek-v4-flash", 0.01, 5.0, caller="unit_test"
                )

    def test_settlement_replaces_open_ceiling_with_actual_cost(self):
        conn, cur = self._db()
        cur.rowcount = 1
        reservation_id = uuid.uuid4()
        with patch("db.get_connection", return_value=conn):
            assert gate._settle_cost_reservation(
                reservation_id,
                0.001,
                metadata={"provider": "deepseek"},
            )
        sql, params = cur.execute.call_args.args
        assert "status = 'settled'" in sql
        assert params[2] == reservation_id
        conn.commit.assert_called_once()


class TestProcessSpend:
    def test_starts_at_zero(self):
        assert gate._process_spend() == 0.0

    def test_add_accumulates(self):
        gate._add_process_spend(0.10)
        gate._add_process_spend(0.25)
        assert gate._process_spend() == pytest.approx(0.35)

    def test_successful_settlement_releases_projected_delta(self):
        reservation_id = uuid.uuid4()
        gate._reserve_process_spend(reservation_id, 0.50)
        gate._settle_process_spend(reservation_id, 0.05)
        assert gate._process_spend() == pytest.approx(0.05)

    def test_unknown_process_settlement_fails_closed(self):
        with pytest.raises(gate.LLMBudgetAccountingError, match="Unknown"):
            gate._settle_process_spend(uuid.uuid4(), 0.05)


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

    def test_log_batch_cost_uses_full_price_by_default(self):
        # Batch execution is quarantined, so historical accounting assumes no discount.
        logged = {}

        def _capture(model, i, o, cost, caller, extra=None):
            logged.update(
                model=model, i=i, o=o, cost=cost, caller=caller, extra=extra
            )
            return True

        with patch.object(gate, "_log_cost", _capture):
            cost = gate.log_batch_cost(
                model="deepseek-v4-pro",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
                caller="minutes_extraction",
                batch_id="batch_abc",
            )
        assert cost == pytest.approx(1.305)
        assert logged["cost"] == pytest.approx(1.305)
        assert logged["caller"] == "minutes_extraction"
        assert logged["extra"]["batch"] is True
        assert logged["extra"]["batch_id"] == "batch_abc"

    def test_log_batch_cost_adds_process_spend(self):
        with patch.object(gate, "_log_cost"):
            gate.log_batch_cost(
                model="deepseek-v4-pro",
                input_tokens=1_000_000,
                output_tokens=1_000_000,
            )
        assert gate._process_spend() == pytest.approx(1.305)

    def test_log_batch_results_cost_sums_succeeded_only(self):
        results = [
            {"result": {"type": "succeeded", "message": {
                "model": "deepseek-v4-pro",
                "usage": {"input_tokens": 1_000_000, "output_tokens": 0}}}},
            {"result": {"type": "errored", "message": {
                "model": "deepseek-v4-pro",
                "usage": {"input_tokens": 9_000_000, "output_tokens": 0}}}},
            {"result": {"type": "succeeded", "message": {
                "model": "deepseek-v4-pro",
                "usage": {"input_tokens": 1_000_000, "output_tokens": 0}}}},
        ]
        with patch.object(gate, "_log_cost"):
            cost = gate.log_batch_results_cost(results, batch_id="b1")
        # Only the 2 succeeded rows count: 2M cache-miss input at $0.435/M.
        assert cost == pytest.approx(0.87)

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

    def test_db_error_fails_closed_even_with_stale_cache(self):
        gate._mtd_cache["value"] = 3.0
        gate._mtd_cache["fetched_at"] = 0.0  # expired
        with patch.object(gate, "_query_mtd_spend", return_value=None):
            with pytest.raises(gate.LLMBudgetAccountingError):
                gate._month_to_date_spend_usd()

    def test_persisted_cost_updates_fresh_cache(self):
        gate._mtd_cache["value"] = 2.0
        gate._mtd_cache["fetched_at"] = __import__("time").time()
        gate._add_cached_mtd_spend(0.25)
        assert gate._mtd_cache["value"] == pytest.approx(2.25)

    def test_poisoned_cache_refuses_further_paid_calls(self):
        gate._invalidate_mtd_cache(poison=True)
        with pytest.raises(gate.LLMBudgetAccountingError, match="prior LLM cost"):
            gate._month_to_date_spend_usd()


class TestStrictCostLedger:
    def test_low_level_writer_failure_is_reported(self):
        conn = MagicMock()
        with patch("db.get_connection", return_value=conn), patch(
            "db.write_journal_entry", side_effect=RuntimeError("insert failed")
        ):
            assert gate._log_cost(
                "deepseek-v4-flash", 10, 2, 0.001, "unit_test"
            ) is False
        conn.close.assert_called_once()

    def test_success_uses_strict_low_level_writer(self):
        conn = MagicMock()
        with patch("db.get_connection", return_value=conn), patch(
            "db.write_journal_entry"
        ) as write:
            assert gate._log_cost(
                "deepseek-v4-flash",
                10,
                2,
                0.001,
                "unit_test",
                extra={"provider": "deepseek"},
            ) is True
        metrics = write.call_args.kwargs["metrics"]
        assert metrics["model"] == "deepseek-v4-flash"
        assert metrics["approx_cost"] == 0.001
        assert metrics["provider"] == "deepseek"
