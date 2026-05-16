"""Regression guard for the Vercel deploy gate (T0.2 of the audit plan).

`web/vercel.json` must disable auto-deploy from the `main` branch so that
every production release goes through a manual operator promote step.
See `web/CLAUDE.md` -> "Deployment Gating" for the full reasoning.

If this test starts failing, someone removed or weakened the gate. Confirm
the change is intentional in PR review before merging — the most common
cause is an editor auto-formatter or a half-finished migration that
deleted the file without restoring it.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
VERCEL_JSON = REPO_ROOT / "web" / "vercel.json"


def test_vercel_json_exists():
    """web/vercel.json is the deploy gate; it must exist."""
    assert VERCEL_JSON.exists(), (
        f"Expected {VERCEL_JSON} to exist. Deleting it re-enables auto-deploy "
        f"on every main push without an operator manual-promote step. "
        f"See web/CLAUDE.md 'Deployment Gating' for context."
    )


def test_vercel_json_is_valid_json():
    """Vercel rejects malformed config on deploy; catch it pre-merge."""
    raw = VERCEL_JSON.read_text(encoding="utf-8")
    # Will raise json.JSONDecodeError with a useful line/col message
    json.loads(raw)


def test_vercel_json_disables_main_auto_deploy():
    """Core invariant of T0.2: main pushes must NOT auto-promote to prod.

    If this changes (someone wanted to re-enable auto-deploy), the
    accompanying docs change in web/CLAUDE.md is required so the next
    reader understands the new policy.
    """
    config = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))
    main_enabled = (
        config.get("git", {})
        .get("deploymentEnabled", {})
        .get("main")
    )
    assert main_enabled is False, (
        f"vercel.json must set git.deploymentEnabled.main = false. "
        f"Got: {main_enabled!r}. "
        f"If this is intentional, update web/CLAUDE.md 'Deployment Gating' "
        f"section and remove this test."
    )


def test_vercel_json_does_not_silently_disable_pr_builds():
    """If preview deploys for PRs were ever turned off, surface it loudly.

    PR preview deploys are how the operator spot-checks a change before
    promoting to prod. Disabling them would defeat the whole point of
    the gate (you'd be promoting unverified builds).
    """
    config = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))
    deployment_enabled = config.get("git", {}).get("deploymentEnabled", {})
    # Either unset (default = enabled) or explicitly True.
    # If the operator ever wants to disable PR previews, they can update
    # this test in the same change so the intent is auditable.
    for branch, enabled in deployment_enabled.items():
        if branch == "main":
            continue
        assert enabled is not False, (
            f"vercel.json disables deploys for branch '{branch}'. "
            f"If intentional, document why in web/CLAUDE.md."
        )
