"""Kill switch: when RICHMOND_API_BUDGET_LOCK is set, anthropic.Messages.create raises."""
from __future__ import annotations

import os
import sys

_LOCK_ENV_VAR = "RICHMOND_API_BUDGET_LOCK"
_TRUTHY = {"1", "true", "yes", "on"}


class AnthropicBudgetLockError(RuntimeError):
    pass


def is_locked() -> bool:
    return os.environ.get(_LOCK_ENV_VAR, "").strip().lower() in _TRUTHY


def _install_gate() -> None:
    try:
        from anthropic.resources.messages import Messages
    except ImportError:
        return

    if getattr(Messages.create, "_richmond_budget_locked", False):
        return

    _orig_create = Messages.create

    def _gated_create(self, *args, **kwargs):
        if is_locked():
            raise AnthropicBudgetLockError(
                f"Anthropic API call refused: {_LOCK_ENV_VAR}=true is set."
            )
        return _orig_create(self, *args, **kwargs)

    _gated_create._richmond_budget_locked = True  # type: ignore[attr-defined]
    Messages.create = _gated_create  # type: ignore[assignment]

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
        pass


_install_gate()

if is_locked():
    print(f"[anthropic_budget_lock] ACTIVE — {_LOCK_ENV_VAR} is set.", file=sys.stderr)
