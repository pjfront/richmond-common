"""Central LLM budget rails and conservative token-cost accounting.

Synchronous calls enter through :mod:`llm_client`.  Model pricing is exact and
fail-closed: an unknown model never inherits a cheaper fallback price.  Cache
discounts are counted only when the provider reports cache-read tokens; all
unclassified input is priced as a cache miss.
"""
from __future__ import annotations

import math
import os
import sys
import threading
import time
import uuid
import warnings
from typing import Any

_LOCK_ENV_VAR = "RICHMOND_API_BUDGET_LOCK"
_MONTHLY_CAP_ENV_VAR = "RICHMOND_API_MONTHLY_CAP_USD"
_EVENT_BUDGET_ENV_VAR = "RICHMOND_EVENT_BUDGET_USD"
_EVENT_TYPE_ENV_VAR = "RICHMOND_EVENT_TYPE"
_DEFAULT_MONTHLY_CAP = 5.0
_TRUTHY = {"1", "true", "yes", "on"}

_MTD_CACHE_TTL_SECONDS = 90

# USD per million tokens: (cache-hit input, cache-miss input, output).
# Verified 2026-08-07 against official provider/model pages.  Gateway prices
# use the standard listed route rather than a temporarily cheaper provider.
_MODEL_PRICING: dict[str, tuple[float, float, float]] = {
    "deepseek-v4-flash": (0.0028, 0.14, 0.28),
    "deepseek-v4-pro": (0.003625, 0.435, 0.87),
    "kimi-k2.6": (0.16, 0.95, 4.00),
    # Gateway may select a costlier eligible provider than direct Moonshot;
    # use the highest currently eligible route for conservative accounting.
    "moonshotai/kimi-k2.6": (0.20, 1.20, 4.50),
    "kimi-k3": (0.30, 3.00, 15.00),
    "moonshotai/kimi-k3": (0.30, 3.00, 15.00),
    # Explicit benchmark routes only. They are never silent fallbacks.
    "gpt-5.6-luna": (0.02, 0.20, 1.20),
}

# GPT-5.6 uses a higher rate for the full request above 272K prompt tokens.
# Keep this in the shared accounting path so both the preflight reservation and
# the settled ledger use the same published tier instead of undercounting a
# long-context benchmark.
_LONG_CONTEXT_THRESHOLD_TOKENS = 272_000
_LONG_CONTEXT_PRICING: dict[str, tuple[float, float, float]] = {
    "gpt-5.6-luna": (0.04, 0.40, 1.80),
}

# Some providers distinguish cache writes from ordinary cache-miss input.
# Unlisted models price reported write tokens at their normal miss rate.
_CACHE_WRITE_PRICING: dict[str, float] = {
    "gpt-5.6-luna": 0.25,
}
_LONG_CONTEXT_CACHE_WRITE_PRICING: dict[str, float] = {
    "gpt-5.6-luna": 0.50,
}

_process_spend_lock = threading.Lock()
_process_spend_usd = 0.0
_process_spend_reservations: dict[uuid.UUID, float] = {}
_mtd_cache_lock = threading.Lock()
_mtd_cache: dict[str, Any] = {
    "value": None,
    "fetched_at": 0.0,
    "poisoned": False,
}


class LLMBudgetLockError(RuntimeError):
    """Raised when the hard LLM kill switch is enabled."""


class LLMMonthlyCapError(RuntimeError):
    """Raised when a request would reach or exceed the monthly cap."""


class LLMEventCapError(RuntimeError):
    """Raised when a request would reach or exceed the current event cap."""


class LLMUnknownPricingError(RuntimeError):
    """Raised when a selected model lacks verified pricing."""


class LLMBudgetAccountingError(RuntimeError):
    """Raised when the monthly ledger cannot be read safely."""


class LLMBudgetConfigurationError(RuntimeError):
    """Raised when a configured cap is malformed or non-finite."""


# Compatibility exports for existing exception handlers.
AnthropicBudgetLockError = LLMBudgetLockError
AnthropicMonthlyCapError = LLMMonthlyCapError
AnthropicEventCapError = LLMEventCapError


def is_locked() -> bool:
    return os.environ.get(_LOCK_ENV_VAR, "").strip().lower() in _TRUTHY


def _assert_api_unlocked() -> None:
    """Fail before any provider-bound preflight or billable request."""
    if is_locked():
        raise LLMBudgetLockError(
            f"LLM API call refused: {_LOCK_ENV_VAR}=true is set."
        )


def _monthly_cap_usd() -> float:
    raw = os.environ.get(_MONTHLY_CAP_ENV_VAR, "").strip()
    if not raw:
        return _DEFAULT_MONTHLY_CAP
    try:
        value = float(raw)
    except ValueError as exc:
        raise LLMBudgetConfigurationError(
            f"{_MONTHLY_CAP_ENV_VAR} must be a finite non-negative number."
        ) from exc
    if not math.isfinite(value) or value < 0:
        raise LLMBudgetConfigurationError(
            f"{_MONTHLY_CAP_ENV_VAR} must be a finite non-negative number."
        )
    return value


def _event_cap_usd() -> float | None:
    raw = os.environ.get(_EVENT_BUDGET_ENV_VAR, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError as exc:
        raise LLMBudgetConfigurationError(
            f"{_EVENT_BUDGET_ENV_VAR} must be a finite non-negative number."
        ) from exc
    if not math.isfinite(value) or value < 0:
        raise LLMBudgetConfigurationError(
            f"{_EVENT_BUDGET_ENV_VAR} must be a finite non-negative number."
        )
    return value


def _price_for_model(model: str) -> tuple[float, float, float]:
    """Return exact verified pricing; never guess for an unknown model."""
    model_id = (model or "").strip().lower()
    try:
        return _MODEL_PRICING[model_id]
    except KeyError as exc:
        raise LLMUnknownPricingError(
            f"No verified price is configured for model {model!r}; refusing to "
            "estimate or spend with a fallback rate."
        ) from exc


def _approx_cost(
    model: str,
    input_tokens: int,
    output_tokens: int,
    *,
    cache_read_input_tokens: int = 0,
    cache_write_input_tokens: int = 0,
) -> float:
    """Calculate conservative cost from reported usage.

    Cache-hit pricing applies only to the reported cache-read subset.  Missing
    cache metadata therefore prices every input token at the cache-miss rate.
    """
    if (
        input_tokens < 0
        or output_tokens < 0
        or cache_read_input_tokens < 0
        or cache_write_input_tokens < 0
    ):
        raise ValueError("Token counts cannot be negative.")
    model_id = (model or "").strip().lower()
    long_context = (
        input_tokens > _LONG_CONTEXT_THRESHOLD_TOKENS
        and model_id in _LONG_CONTEXT_PRICING
    )
    if long_context:
        cache_hit, cache_miss, output = _LONG_CONTEXT_PRICING[model_id]
        cache_write = _LONG_CONTEXT_CACHE_WRITE_PRICING.get(
            model_id, cache_miss
        )
    else:
        cache_hit, cache_miss, output = _price_for_model(model_id)
        cache_write = _CACHE_WRITE_PRICING.get(model_id, cache_miss)

    if cache_read_input_tokens + cache_write_input_tokens > input_tokens:
        raise ValueError("Reported cache read/write tokens exceed input tokens.")
    hit_tokens = cache_read_input_tokens
    write_tokens = cache_write_input_tokens
    miss_tokens = input_tokens - hit_tokens - write_tokens
    return (
        (hit_tokens / 1_000_000.0) * cache_hit
        + (write_tokens / 1_000_000.0) * cache_write
        + (miss_tokens / 1_000_000.0) * cache_miss
        + (output_tokens / 1_000_000.0) * output
    )


def _month_to_date_spend_usd() -> float:
    now = time.time()
    _assert_accounting_not_poisoned()
    with _mtd_cache_lock:
        cached = _mtd_cache.get("value")
        fetched_at = float(_mtd_cache.get("fetched_at") or 0.0)
        if cached is not None and now - fetched_at < _MTD_CACHE_TTL_SECONDS:
            return float(cached)

    value = _query_mtd_spend()
    if value is None:
        raise LLMBudgetAccountingError(
            "Cannot read the month-to-date LLM ledger; refusing a new paid call. "
            "Restore database access or set RICHMOND_API_BUDGET_LOCK=true."
        )
    with _mtd_cache_lock:
        _mtd_cache["value"] = value
        _mtd_cache["fetched_at"] = now
    return value


def _assert_accounting_not_poisoned() -> None:
    """Stop spend after this process observes any accounting uncertainty."""
    with _mtd_cache_lock:
        if _mtd_cache.get("poisoned"):
            raise LLMBudgetAccountingError(
                "A prior LLM cost could not be persisted in this process; "
                "refusing further paid calls until the process restarts."
            )


def _add_cached_mtd_spend(amount: float) -> None:
    """Keep a fresh in-process MTD cache current after a persisted write."""
    if amount <= 0:
        return
    with _mtd_cache_lock:
        if _mtd_cache.get("value") is not None:
            _mtd_cache["value"] = float(_mtd_cache["value"]) + amount


def _invalidate_mtd_cache(*, poison: bool = False) -> None:
    """Discard cached ledger state and optionally stop this process spending.

    A failed cost INSERT means a later database read would undercount actual
    spend.  Poisoning converts that uncertainty into a fail-closed process
    state instead of allowing the stale or incomplete total to authorize more
    paid requests.
    """
    with _mtd_cache_lock:
        _mtd_cache["value"] = None
        _mtd_cache["fetched_at"] = 0.0
        if poison:
            _mtd_cache["poisoned"] = True


def _query_mtd_spend() -> float | None:
    """Return authoritative month spend including open reservations.

    Journal rows created before migration 129 have no reservation_id and are
    included directly.  New calls are counted from ``llm_cost_reservations``
    (projected while open, actual once settled), so their matching journal row
    is intentionally excluded and cannot double-count.
    """
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
                """SELECT
                     COALESCE((
                       SELECT SUM((metrics->>'approx_cost')::numeric)
                       FROM pipeline_journal
                       WHERE entry_type = 'api_cost'
                         AND NULLIF(metrics->>'reservation_id', '') IS NULL
                         AND date_trunc('month', created_at) =
                             date_trunc('month', NOW())
                     ), 0)
                     +
                     COALESCE((
                       SELECT SUM(
                         CASE WHEN status = 'settled'
                              THEN actual_cost
                              ELSE projected_cost
                         END
                       )
                       FROM llm_cost_reservations
                       WHERE date_trunc('month', created_at) =
                             date_trunc('month', NOW())
                     ), 0)"""
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


def _reserve_process_spend(reservation_id: uuid.UUID, projected_cost: float) -> None:
    """Count a paid-call ceiling against this event before the provider call.

    A timeout is ambiguous: the provider may have completed and billed the
    generation even though no usage reached us.  Keeping the ceiling in the
    process total makes every explicit retry pass through the event cap.
    """
    if not math.isfinite(projected_cost) or projected_cost < 0:
        raise LLMBudgetAccountingError(
            "Cannot reserve a non-finite or negative process-spend ceiling."
        )
    global _process_spend_usd
    with _process_spend_lock:
        if reservation_id in _process_spend_reservations:
            raise LLMBudgetAccountingError(
                f"Process-spend reservation {reservation_id} already exists."
            )
        _process_spend_reservations[reservation_id] = projected_cost
        _process_spend_usd += projected_cost


def _settle_process_spend(reservation_id: uuid.UUID, actual_cost: float) -> None:
    """Replace one event ceiling with actual cost after durable accounting.

    Call this only after both the cross-process reservation settlement and the
    journal write succeed.  On any ambiguous failure, leave the conservative
    ceiling in place.
    """
    if not math.isfinite(actual_cost) or actual_cost < 0:
        raise LLMBudgetAccountingError(
            "Cannot settle process spend to a non-finite or negative amount."
        )
    global _process_spend_usd
    with _process_spend_lock:
        projected = _process_spend_reservations.pop(reservation_id, None)
        if projected is None:
            raise LLMBudgetAccountingError(
                f"Unknown process-spend reservation {reservation_id}."
            )
        _process_spend_usd += actual_cost - projected


def _reserve_monthly_budget(
    model: str,
    projected_cost: float,
    monthly_cap: float,
    *,
    caller: str,
) -> uuid.UUID:
    """Atomically reserve one request ceiling across every runner.

    The advisory transaction lock serializes authorization for the current
    month.  Open reservations are never silently expired: a process that dies
    after reaching the provider may still have incurred cost, so its full
    ceiling remains counted until an operator reconciles it or the month rolls.
    """
    reservation_id = uuid.uuid4()
    try:
        from db import get_connection
    except Exception as exc:
        raise LLMBudgetAccountingError(
            "Cannot load the database client for an atomic LLM reservation."
        ) from exc
    try:
        conn = get_connection()
    except Exception as exc:
        raise LLMBudgetAccountingError(
            "Cannot connect to the database for an atomic LLM reservation."
        ) from exc

    try:
        with conn.cursor() as cur:
            # Two-int advisory locks are transaction scoped.  The first key is
            # the control-plane namespace; the second separates calendar
            # months without relying on a process-local mutex.
            cur.execute(
                """SELECT pg_advisory_xact_lock(
                         hashtext('richmond-commons-llm-budget'),
                         hashtext(to_char(NOW(), 'YYYY-MM'))
                       )"""
            )
            cur.execute(
                """SELECT
                     COALESCE((
                       SELECT SUM((metrics->>'approx_cost')::numeric)
                       FROM pipeline_journal
                       WHERE entry_type = 'api_cost'
                         AND NULLIF(metrics->>'reservation_id', '') IS NULL
                         AND date_trunc('month', created_at) =
                             date_trunc('month', NOW())
                     ), 0)
                     +
                     COALESCE((
                       SELECT SUM(
                         CASE WHEN status = 'settled'
                              THEN actual_cost
                              ELSE projected_cost
                         END
                       )
                       FROM llm_cost_reservations
                       WHERE date_trunc('month', created_at) =
                             date_trunc('month', NOW())
                     ), 0)"""
            )
            row = cur.fetchone()
            committed = float(row[0]) if row and row[0] is not None else 0.0
            if committed >= monthly_cap or committed + projected_cost > monthly_cap:
                raise LLMMonthlyCapError(
                    f"LLM monthly cap would be exceeded: committed/reserved "
                    f"${committed:.4f} + request ceiling ${projected_cost:.4f} "
                    f"> ${monthly_cap:.4f}. Cap controlled by "
                    f"{_MONTHLY_CAP_ENV_VAR}."
                )
            cur.execute(
                """INSERT INTO llm_cost_reservations
                     (id, city_fips, model, caller, event_type,
                      projected_cost, status, metadata)
                   VALUES (%s, '0660620', %s, %s, %s, %s, 'reserved', %s::jsonb)""",
                (
                    reservation_id,
                    model,
                    caller,
                    os.environ.get(_EVENT_TYPE_ENV_VAR) or None,
                    projected_cost,
                    "{}",
                ),
            )
        conn.commit()
    except LLMMonthlyCapError:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        raise LLMBudgetAccountingError(
            "Atomic LLM budget reservation failed; refusing the paid call. "
            "Apply migration 129 and restore database write access."
        ) from exc
    finally:
        try:
            conn.close()
        except Exception:
            pass

    _invalidate_mtd_cache()
    return reservation_id


def _settle_cost_reservation(
    reservation_id: uuid.UUID,
    actual_cost: float,
    *,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Replace a conservative reservation with provider-reported actual cost."""
    try:
        from db import get_connection
    except Exception:
        return False
    try:
        conn = get_connection()
    except Exception:
        return False
    try:
        import json

        with conn.cursor() as cur:
            cur.execute(
                """UPDATE llm_cost_reservations
                   SET status = 'settled',
                       actual_cost = %s,
                       settled_at = NOW(),
                       metadata = metadata || %s::jsonb
                   WHERE id = %s AND status = 'reserved'""",
                (actual_cost, json.dumps(metadata or {}), reservation_id),
            )
            updated = cur.rowcount == 1
        if updated:
            conn.commit()
        else:
            conn.rollback()
        return updated
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _detect_caller() -> str:
    """Walk the call stack to attribute API cost to a pipeline module."""
    frame = sys._getframe(1)
    while frame is not None:
        modname = frame.f_globals.get("__name__", "")
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
) -> bool:
    """Persist one cost record and report whether persistence succeeded."""
    try:
        from db import get_connection, write_journal_entry
    except Exception:
        return False
    try:
        conn = get_connection()
    except Exception:
        return False
    try:
        merged_extra: dict[str, Any] = {
            "event_type": os.environ.get(_EVENT_TYPE_ENV_VAR) or None,
        }
        if extra:
            merged_extra.update(extra)
        metrics = {
            "model": model,
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "approx_cost": cost,
            **merged_extra,
        }
        # Use the strict low-level writer. PipelineJournal deliberately
        # swallows failures for general observability, which is unsafe for a
        # ledger used to authorize future paid calls.
        write_journal_entry(
            conn,
            city_fips="0660620",
            session_id=uuid.uuid4(),
            entry_type="api_cost",
            description=f"{caller}: ${cost:.4f}",
            zone="observation",
            target_artifact=caller,
            metrics=metrics,
        )
        return True
    except Exception:
        return False
    finally:
        try:
            conn.close()
        except Exception:
            pass


def _reserve_projected_spend_pre_call(
    model: str,
    projected_cost: float,
    *,
    caller: str | None = None,
) -> uuid.UUID:
    """Authorize and count one paid-call ceiling atomically in this process."""
    global _process_spend_usd
    _assert_accounting_not_poisoned()
    _assert_api_unlocked()
    if not math.isfinite(projected_cost) or projected_cost < 0:
        raise LLMBudgetAccountingError(
            "Cannot authorize a non-finite or negative request ceiling."
        )
    event_cap = _event_cap_usd()
    # Serialize local authorization through reservation.  Otherwise two
    # threads could both observe the same event total, reserve independently,
    # and jointly cross the cap before either ceiling was counted.
    with _process_spend_lock:
        spent = _process_spend_usd
        if event_cap is not None and (
            spent >= event_cap or spent + projected_cost > event_cap
        ):
            event_type = os.environ.get(_EVENT_TYPE_ENV_VAR, "unscoped")
            raise LLMEventCapError(
                f"Per-event budget would be exceeded for {event_type}: current "
                f"${spent:.4f} + request ceiling ${projected_cost:.4f} > "
                f"${event_cap:.4f}."
            )
        reservation_id = _reserve_monthly_budget(
            model,
            projected_cost,
            _monthly_cap_usd(),
            caller=caller or _detect_caller(),
        )
        _process_spend_reservations[reservation_id] = projected_cost
        _process_spend_usd += projected_cost
        return reservation_id


def _enforce_caps_pre_call(
    model_hint: str,
    *,
    estimated_input_tokens: int = 0,
    max_output_tokens: int = 0,
) -> uuid.UUID:
    """Reject an unsafe call and atomically reserve its conservative ceiling."""
    projected_request = _approx_cost(
        model_hint,
        estimated_input_tokens,
        max_output_tokens,
        cache_read_input_tokens=0,
    )
    return _reserve_projected_spend_pre_call(
        model_hint,
        projected_request,
        caller=_detect_caller(),
    )


# Batch execution is currently quarantined in llm_client.  These helpers retain
# conservative historical-result accounting without assuming any discount.
_BATCH_DISCOUNT = 1.0


def log_batch_cost(
    *,
    model: str,
    input_tokens: int,
    output_tokens: int,
    caller: str | None = None,
    batch_id: str | None = None,
    discount: float = _BATCH_DISCOUNT,
) -> float:
    if not 0 < discount <= 1:
        raise ValueError("Batch discount multiplier must be in (0, 1].")
    if caller is None:
        caller = _detect_caller()
    cost = _approx_cost(model, input_tokens, output_tokens) * discount
    _add_process_spend(cost)
    logged = _log_cost(
        model,
        input_tokens,
        output_tokens,
        cost,
        caller,
        extra={"batch": True, "batch_id": batch_id, "discount": discount},
    )
    if logged:
        _add_cached_mtd_spend(cost)
    else:
        _invalidate_mtd_cache(poison=True)
        warnings.warn(
            f"Batch LLM cost ${cost:.6f} could not be persisted.",
            RuntimeWarning,
            stacklevel=2,
        )
    return cost


def log_batch_results_cost(
    result_dicts: Any,
    *,
    caller: str | None = None,
    batch_id: str | None = None,
    discount: float = _BATCH_DISCOUNT,
) -> float:
    if caller is None:
        caller = _detect_caller()
    total_in = 0
    total_out = 0
    model = ""
    for item in result_dicts:
        row = (
            item
            if isinstance(item, dict)
            else item.model_dump()
            if hasattr(item, "model_dump")
            else {}
        )
        result = row.get("result") or {}
        if result.get("type") != "succeeded":
            continue
        message = result.get("message") or {}
        usage = message.get("usage") or {}
        total_in += int(usage.get("input_tokens") or 0)
        total_out += int(usage.get("output_tokens") or 0)
        model = message.get("model") or model
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


if is_locked():
    print(f"[llm_budget_lock] ACTIVE - {_LOCK_ENV_VAR} is set.", file=sys.stderr)
