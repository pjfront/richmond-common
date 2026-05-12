"""Centralized Anthropic API rails: kill switch, monthly cap, per-event cap, cost logging.

Monkey-patches anthropic.Messages.create on import. Every Anthropic call across
the codebase passes through the gate without per-site edits. See PR #26 + the
follow-up rails PR.
"""
from __future__ import annotations

import os
import sys
import time
import threading
from typing import Any

_LOCK_ENV_VAR = "RICHMOND_API_BUDGET_LOCK"
_MONTHLY_CAP_ENV_VAR = "RICHMOND_API_MONTHLY_CAP_USD"
_EVENT_BUDGET_ENV_VAR = "RICHMOND_EVENT_BUDGET_USD"
_EVENT_TYPE_ENV_VAR = "RICHMOND_EVENT_TYPE"
_DEFAULT_MONTHLY_CAP = 5.0
_TRUTHY = {"1", "true", "yes", "on"}

_MTD_CACHE_TTL_SECONDS = 90

# Approximate USD per million tokens. Conservative (uses the higher tier
# for each family) so we err on the side of triggering the cap early.
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "claude-opus": (15.0, 75.0),
    "claude-sonnet-4-5": (3.0, 15.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-sonnet": (3.0, 15.0),
    "claude-haiku-4-5": (0.80, 4.0),
    "claude-haiku": (0.80, 4.0),
    "claude-3-5-sonnet": (3.0, 15.0),
    "claude-3-5-haiku": (0.80, 4.0),
    "claude-3-opus": (15.0, 75.0),
}
_FALLBACK_PRICING = (3.0, 15.0)

_process_spend_lock = threading.Lock()
_process_spend_usd = 0.0
_mtd_cache: dict[str, Any] = {"value": None, "fetched_at": 0.0}


class AnthropicBudgetLockError(RuntimeError):
    pass


class AnthropicMonthlyCapError(RuntimeError):
    pass


class AnthropicEventCapError(RuntimeError):
    pass


def is_locked() -> bool:
    return os.environ.get(_LOCK_ENV_VAR, "").strip().lower() in _TRUTHY


def _monthly_cap_usd() -> float:
    raw = os.environ.get(_MONTHLY_CAP_ENV_VAR, "").strip()
    if not raw:
        return _DEFAULT_MONTHLY_CAP
    try:
        return float(raw)
    except ValueError:
        return _DEFAULT_MONTHLY_CAP


def _event_cap_usd() -> float | None:
    raw = os.environ.get(_EVENT_BUDGET_ENV_VAR, "").strip()
    if not raw:
        return None
    try:
        return float(raw)
    except ValueError:
        return None


def _price_for_model(model: str) -> tuple[float, float]:
    model_lc = (model or "").lower()
    for key, pricing in _MODEL_PRICING.items():
        if model_lc.startswith(key):
            return pricing
    return _FALLBACK_PRICING


def _approx_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    inp_per_m, out_per_m = _price_for_model(model)
    return (input_tokens / 1_000_000.0) * inp_per_m + (output_tokens / 1_000_000.0) * out_per_m


def _month_to_date_spend_usd() -> float:
    now = time.time()
    cached = _mtd_cache.get("value")
    if cached is not None and (now - _mtd_cache["fetched_at"]) < _MTD_CACHE_TTL_SECONDS:
        return float(cached)
    value = _query_mtd_spend()
    if value is None:
        # Fail open on DB error so a transient outage doesn't block all calls;
        # the kill switch + per-event cap remain in force.
        return float(cached or 0.0)
    _mtd_cache["value"] = value
    _mtd_cache["fetched_at"] = now
    return value


def _query_mtd_spend() -> float | None:
    try:
        from db import get_connection
    except Exception:
        return None
    try:
        conn = get_connection()
    except Exception:
        return None
    try:
        with conn.cursor() as cur:
            cur.execute(
                """SELECT COALESCE(SUM((metrics->>'approx_cost')::numeric), 0)
                   FROM pipeline_journal
                   WHERE entry_type = 'api_cost'
                     AND date_trunc('month', created_at) = date_trunc('month', NOW())"""
            )
            row = cur.fetchone()
            return float(row[0]) if row and row[0] is not None else 0.0
    except Exception:
        return None
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _process_spend() -> float:
    with _process_spend_lock:
        return _process_spend_usd


def _add_process_spend(amount: float) -> None:
    global _process_spend_usd
    with _process_spend_lock:
        _process_spend_usd += amount


def _detect_caller() -> str:
    frame = sys._getframe(1)
    while frame is not None:
        modname = frame.f_globals.get("__name__", "")
        if modname and not modname.startswith("anthropic") and modname != __name__:
            return modname.split(".")[-1] or "unknown"
        frame = frame.f_back
    return "unknown"


def _log_cost(model: str, input_tokens: int, output_tokens: int, cost: float, caller: str) -> None:
    try:
        from db import get_connection
        from pipeline_journal import PipelineJournal
    except Exception:
        return
    try:
        conn = get_connection()
    except Exception:
        return
    try:
        PipelineJournal(conn, "0660620").log_api_cost(
            target_artifact=caller,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            approx_cost=cost,
            extra={
                "event_type": os.environ.get(_EVENT_TYPE_ENV_VAR) or None,
            },
        )
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _enforce_caps_pre_call(model_hint: str) -> None:
    if is_locked():
        raise AnthropicBudgetLockError(
            f"Anthropic API call refused: {_LOCK_ENV_VAR}=true is set."
        )
    cap = _monthly_cap_usd()
    mtd = _month_to_date_spend_usd()
    if mtd >= cap:
        raise AnthropicMonthlyCapError(
            f"Anthropic monthly cap reached: month-to-date ${mtd:.2f} >= ${cap:.2f}. "
            f"Cap controlled by {_MONTHLY_CAP_ENV_VAR}."
        )
    event_cap = _event_cap_usd()
    if event_cap is not None:
        spent = _process_spend()
        if spent >= event_cap:
            event_type = os.environ.get(_EVENT_TYPE_ENV_VAR, "unscoped")
            raise AnthropicEventCapError(
                f"Per-event budget reached for {event_type}: "
                f"${spent:.2f} >= ${event_cap:.2f}."
            )


def _install_gate() -> None:
    try:
        from anthropic.resources.messages import Messages
    except ImportError:
        return

    if getattr(Messages.create, "_richmond_budget_locked", False):
        return

    _orig_create = Messages.create

    def _gated_create(self, *args, **kwargs):
        model = kwargs.get("model", "")
        caller = _detect_caller()
        _enforce_caps_pre_call(model)
        response = _orig_create(self, *args, **kwargs)
        try:
            usage = getattr(response, "usage", None)
            input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
            output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
            cost = _approx_cost(model, input_tokens, output_tokens)
            _add_process_spend(cost)
            _log_cost(model, input_tokens, output_tokens, cost, caller)
        except Exception:
            pass
        return response

    _gated_create._richmond_budget_locked = True  # type: ignore[attr-defined]
    Messages.create = _gated_create  # type: ignore[assignment]

    try:
        from anthropic.resources.messages.batches import Batches

        if not getattr(Batches.create, "_richmond_budget_locked", False):
            _orig_batch = Batches.create

            def _gated_batch_create(self, *args, **kwargs):
                _enforce_caps_pre_call(kwargs.get("model", ""))
                return _orig_batch(self, *args, **kwargs)

            _gated_batch_create._richmond_budget_locked = True  # type: ignore[attr-defined]
            Batches.create = _gated_batch_create  # type: ignore[assignment]
    except ImportError:
        pass


_install_gate()

if is_locked():
    print(f"[anthropic_budget_lock] ACTIVE — {_LOCK_ENV_VAR} is set.", file=sys.stderr)
