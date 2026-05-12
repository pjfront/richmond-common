"""
Belt-and-suspenders kill switch for Anthropic API spend.

The primary kill switch is the GitHub Actions workflow disable (see the
KILL SWITCH comments in .github/workflows/*.yml). This module is the
secondary defense: even if a workflow is manually triggered via
workflow_dispatch while the audit is in progress, setting the env var
``RICHMOND_API_BUDGET_LOCK=true`` causes every Anthropic ``messages.create``
call to raise immediately, before a single token is billed.

Usage from a CI entry point:

    import anthropic_budget_lock  # registers the gate at import time
    # ... rest of the script ...

The gate is process-wide and applied via monkey-patch on the SDK's
``Messages.create`` method. Once imported, the patch persists for the
life of the process. Unset (or leave unset) the env var to disable the
gate.

Why monkey-patch and not a wrapper function? Because there are 30+
Anthropic client constructors across 24 files. Wrapping every one is
mechanical busywork that's easy to miss; patching the single SDK method
every caller funnels through catches everything, present and future.

The gate also emits a brief, structured warning at import time noting
whether the lock is active, so CI logs make it obvious which mode the
job is running in.
"""
from __future__ import annotations

import os
import sys

_LOCK_ENV_VAR = "RICHMOND_API_BUDGET_LOCK"
_TRUTHY = {"1", "true", "yes", "on"}


class AnthropicBudgetLockError(RuntimeError):
    """Raised when an Anthropic API call is attempted under the budget lock.

    The intent is to be loud and unmissable: an exception, not a log line,
    so any caller that swallowed errors silently in the past now blocks
    instead of leaking spend.
    """


def is_locked() -> bool:
    return os.environ.get(_LOCK_ENV_VAR, "").strip().lower() in _TRUTHY


def _install_gate() -> None:
    try:
        import anthropic
        from anthropic.resources.messages import Messages
    except ImportError:
        # No SDK installed in this environment — nothing to gate.
        return

    if getattr(Messages.create, "_richmond_budget_locked", False):
        return  # already patched (idempotent re-import)

    _orig_create = Messages.create

    def _gated_create(self, *args, **kwargs):
        if is_locked():
            raise AnthropicBudgetLockError(
                f"Anthropic API call refused: env var {_LOCK_ENV_VAR}=true is set. "
                "The Richmond Commons budget lock is engaged while the API-cost "
                "audit is in progress. Unset the env var only after the audit "
                "lands and the journal can attribute spend per call site. "
                "See branch claude/fix-api-billing-gFC3C and .github/workflows/*.yml "
                "for context."
            )
        return _orig_create(self, *args, **kwargs)

    _gated_create._richmond_budget_locked = True  # type: ignore[attr-defined]
    Messages.create = _gated_create  # type: ignore[assignment]

    # Also gate the batch.create path (Anthropic Batch API) — same surface.
    try:
        from anthropic.resources.messages.batches import Batches

        if not getattr(Batches.create, "_richmond_budget_locked", False):
            _orig_batch = Batches.create

            def _gated_batch_create(self, *args, **kwargs):
                if is_locked():
                    raise AnthropicBudgetLockError(
                        f"Anthropic batch API call refused: {_LOCK_ENV_VAR}=true."
                    )
                return _orig_batch(self, *args, **kwargs)

            _gated_batch_create._richmond_budget_locked = True  # type: ignore[attr-defined]
            Batches.create = _gated_batch_create  # type: ignore[assignment]
    except ImportError:
        pass  # older SDK without Batches namespace — nothing to patch.


_install_gate()

if is_locked():
    print(
        f"[anthropic_budget_lock] ACTIVE — {_LOCK_ENV_VAR} is set. "
        "All Anthropic API calls will raise.",
        file=sys.stderr,
    )
