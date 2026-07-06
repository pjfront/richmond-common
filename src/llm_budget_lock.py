"""Centralized LLM API rails: kill switch, monthly cap, per-event cap, cost logging.

Replaces anthropic_budget_lock.py. No monkey-patching — enforcement is called
directly from llm_client.LLMClient.messages.create() on every invocation.

Batch API spend bypasses the synchronous gate (results arrive asynchronously);
batch collectors must log spend explicitly via log_batch_cost() or
log_batch_results_cost().
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

# DeepSeek pricing — USD per million tokens (input, output).
# Current as of 2026-07: deepseek-chat $0.27/$1.10, deepseek-reasoner $0.55/$2.19.
_MODEL_PRICING: dict[str, tuple[float, float]] = {
    "deepseek-v4-pro": (0.27, 1.10),
    "deepseek-reasoner": (0.55, 2.19),
}
_FALLBACK_PRICING = (0.27, 1.10)

_process_spend_lock = threading.Lock()
_process_spend_usd = 0.0
_mtd_cache: dict[str, Any] = {"value": None, "fetched_at": 0.0}


class LLMBudgetLockError(RuntimeError):
    """Raised when RICHMOND_API_BUDGET_LOCK is set (hard kill switch)."""
    pass


class LLMMonthlyCapError(RuntimeError):
    """Raised when month-to-date spend >= RICHMOND_API_MONTHLY_CAP_USD."""
    pass


class LLMEventCapError(RuntimeError):
    """Raised when per-event spend >= RICHMOND_EVENT_BUDGET_USD."""
    pass


# Re-export the old error names so existing try/except blocks don't break.
AnthropicBudgetLockError = LLMBudgetLockError
AnthropicMonthlyCapError = LLMMonthlyCapError
AnthropicEventCapError = LLMEventCapError


def is_locked() -> bool:
    """Check whether the hard kill switch is active."""
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
    """Walk the call stack to identify which script is making the API call."""
    frame = sys._getframe(1)
    while frame is not None:
        modname = frame.f_globals.get("__name__", "")
        # Skip frames from the OpenAI SDK, our own modules, and stdlib
        if (
            modname
            and not modname.startswith("openai")
            and not modname.startswith("httpx")
            and modname != __name__
            and modname != "llm_client"
        ):
            if modname == "__main__":
                path = frame.f_globals.get("__file__", "")
                if path:
                    return os.path.splitext(os.path.basename(path))[0]
                return "__main__"
            return modname.split(".")[-1] or "unknown"
        frame = frame.f_back
    return "unknown"


def _log_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cost: float,
    caller: str,
    extra: dict[str, Any] | None = None,
) -> None:
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
        merged_extra: dict[str, Any] = {
            "event_type": os.environ.get(_EVENT_TYPE_ENV_VAR) or None,
        }
        if extra:
            merged_extra.update(extra)
        PipelineJournal(conn, "0660620").log_api_cost(
            target_artifact=caller,
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            approx_cost=cost,
            extra=merged_extra,
        )
    except Exception:
        pass
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _enforce_caps_pre_call(model_hint: str) -> None:
    """Check all budget gates. Called by llm_client before every API call."""
    if is_locked():
        raise LLMBudgetLockError(
            f"LLM API call refused: {_LOCK_ENV_VAR}=true is set."
        )
    cap = _monthly_cap_usd()
    mtd = _month_to_date_spend_usd()
    if mtd >= cap:
        raise LLMMonthlyCapError(
            f"LLM monthly cap reached: month-to-date ${mtd:.2f} >= ${cap:.2f}. "
            f"Cap controlled by {_MONTHLY_CAP_ENV_VAR}."
        )
    event_cap = _event_cap_usd()
    if event_cap is not None:
        spent = _process_spend()
        if spent >= event_cap:
            event_type = os.environ.get(_EVENT_TYPE_ENV_VAR, "unscoped")
            raise LLMEventCapError(
                f"Per-event budget reached for {event_type}: "
                f"${spent:.2f} >= ${event_cap:.2f}."
            )


# ── Batch API cost helpers ────────────────────────────────────

_BATCH_DISCOUNT = 0.5  # DeepSeek offers 50% batch discount


def log_batch_cost(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    caller: str | None = None,
    batch_id: str | None = None,
    discount: float = _BATCH_DISCOUNT,
) -> float:
    """Record aggregate cost for one completed batch job.

    Call once per collected batch with the summed token usage across all
    succeeded results. Writes a single entry_type='api_cost' journal row
    tagged batch=true so the MTD cap and the cost digest stay accurate.
    Returns the approx USD cost logged. Never raises.
    """
    try:
        if caller is None:
            caller = _detect_caller()
        cost = _approx_cost(model, input_tokens, output_tokens) * discount
        _add_process_spend(cost)
        _log_cost(
            model, input_tokens, output_tokens, cost, caller,
            extra={"batch": True, "batch_id": batch_id, "discount": discount},
        )
        return cost
    except Exception:
        return 0.0


def log_batch_results_cost(
    result_dicts: Any,
    *,
    caller: str | None = None,
    batch_id: str | None = None,
    discount: float = _BATCH_DISCOUNT,
) -> float:
    """Sum token usage across batch result dicts and log the cost.

    ``result_dicts`` is an iterable of result dicts as returned by
    ``LLMClient.batch_download_results()``. Only ``type == "succeeded"``
    results carry usage and are counted. Returns the approx USD cost logged.
    Never raises — cost logging must never break a data pipeline.
    """
    try:
        if caller is None:
            caller = _detect_caller()
        total_in = 0
        total_out = 0
        model = ""
        for d in result_dicts:
            rd = d if isinstance(d, dict) else (d.model_dump() if hasattr(d, "model_dump") else {})
            res = rd.get("result") or {}
            if res.get("type") != "succeeded":
                continue
            msg = res.get("message") or {}
            usage = msg.get("usage") or {}
            total_in += int(usage.get("input_tokens") or 0)
            total_out += int(usage.get("output_tokens") or 0)
            model = msg.get("model") or model
        if not total_in and not total_out:
            return 0.0
        return log_batch_cost(
            model=model,
            input_tokens=total_in,
            output_tokens=total_out,
            caller=caller,
            batch_id=batch_id,
            discount=discount,
        )
    except Exception:
        return 0.0


# ── Startup notice ─────────────────────────────────────────────

if is_locked():
    print(f"[llm_budget_lock] ACTIVE — {_LOCK_ENV_VAR} is set.", file=sys.stderr)
