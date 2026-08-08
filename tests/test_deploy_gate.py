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
import os
from pathlib import Path
import shutil
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
VERCEL_JSON = REPO_ROOT / "web" / "vercel.json"
PREVIEW_GUARD = REPO_ROOT / "web" / "scripts" / "assert-preview-env.mjs"
FORBIDDEN_PREVIEW_KEYS = [
    "AI_GATEWAY_API_KEY",
    "ANTHROPIC_API_KEY",
    "APIFY_API_TOKEN",
    "API_SECRET",
    "CLOUDFLARE_API_TOKEN",
    "CRON_SECRET",
    "DATABASE_URL",
    "DB_BACKUP_PASSPHRASE",
    "DEEPSEEK_API_KEY",
    "DIRECT_URL",
    "DISPATCH_TOKEN",
    "EMAIL_SIGNING_SECRET",
    "IRON_SESSION_PASSWORD",
    "JWT_SECRET",
    "MOONSHOT_API_KEY",
    "OPENAI_API_KEY",
    "OPENCORPORATES_API_TOKEN",
    "OPERATOR_PASSWORD",
    "POSTGRES_URL",
    "RESEND_API_KEY",
    "REVALIDATION_SECRET",
    "SMTP_PASSWORD",
    "SOCRATA_APP_TOKEN",
    "SUPABASE_ANON_KEY",
    "SUPABASE_ACCESS_TOKEN",
    "SUPABASE_DB_PASSWORD",
    "SUPABASE_SECRET_KEY",
    "SUPABASE_SERVICE_KEY",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_URL",
]


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
    allowed_disabled_branches = {
        "main",           # production remains an explicit CLI deploy
        "heartbeat",      # daily keepalive is not application code
        "automation/**",  # reserved non-product automation branches
        "automation-*",
    }
    for branch, enabled in deployment_enabled.items():
        assert enabled is not False or branch in allowed_disabled_branches, (
            f"vercel.json disables deploys for branch '{branch}'. "
            f"If intentional, document why in web/CLAUDE.md."
        )

    # A catch-all false value would also disable intentional PR previews.
    assert deployment_enabled.get("*") is not False
    assert deployment_enabled.get("**") is not False


def test_vercel_json_blocks_heartbeat_and_automation_deployments():
    """Keepalive/automation pushes must never create preview deployments."""
    config = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))
    deployment_enabled = config["git"]["deploymentEnabled"]
    assert deployment_enabled.get("heartbeat") is False
    assert deployment_enabled.get("automation/**") is False
    assert deployment_enabled.get("automation-*") is False


def test_vercel_ignore_command_defends_heartbeat_branch():
    """The ignored-build command is a second guard for the live incident."""
    config = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))
    command = config.get("ignoreCommand", "")
    assert "VERCEL_GIT_COMMIT_REF" in command
    assert "heartbeat" in command
    assert "automation/" in command


def test_vercel_build_runs_preview_environment_guard():
    """Preview credential scoping is enforced before the Next.js build."""
    config = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))
    command = config.get("buildCommand", "")
    assert command.startswith("node scripts/assert-preview-env.mjs &&")
    assert PREVIEW_GUARD.exists()
    guard_text = PREVIEW_GUARD.read_text(encoding="utf-8")
    assert "VERCEL_ENV !== 'preview'" in guard_text
    assert "ahrwvmizzykyyfavdvfv.supabase.co" in guard_text
    assert "SUPABASE_SERVICE_ROLE_KEY" in guard_text
    assert "DATABASE_URL" in guard_text
    assert "DEEPSEEK_API_KEY" in guard_text
    assert "MOONSHOT_API_KEY" in guard_text
    assert "AI_GATEWAY_API_KEY" in guard_text
    assert "ANTHROPIC_API_KEY" in guard_text
    for key in FORBIDDEN_PREVIEW_KEYS:
        assert f"'{key}'" in guard_text


def _run_preview_guard(**updates: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not available on PATH")
    env = os.environ.copy()
    for key in FORBIDDEN_PREVIEW_KEYS:
        env.pop(key, None)
    env.pop("NEXT_PUBLIC_SUPABASE_URL", None)
    env.pop("NEXT_PUBLIC_SUPABASE_ANON_KEY", None)
    env.update(updates)
    return subprocess.run(
        [node, str(PREVIEW_GUARD)],
        cwd=PREVIEW_GUARD.parent.parent,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_preview_guard_behavior_matrix():
    valid_preview = {
        "VERCEL_ENV": "preview",
        "NEXT_PUBLIC_SUPABASE_URL": "https://staging-project.supabase.co",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY": "sb_publishable_test-value",
    }
    clean = _run_preview_guard(
        **valid_preview,
    )
    assert clean.returncode == 0, clean.stderr

    missing_url = _run_preview_guard(
        **{**valid_preview, "NEXT_PUBLIC_SUPABASE_URL": "  "},
    )
    assert missing_url.returncode != 0
    assert "NEXT_PUBLIC_SUPABASE_URL (missing)" in missing_url.stderr

    missing_key = _run_preview_guard(
        **{**valid_preview, "NEXT_PUBLIC_SUPABASE_ANON_KEY": "  "},
    )
    assert missing_key.returncode != 0
    assert "NEXT_PUBLIC_SUPABASE_ANON_KEY (missing)" in missing_key.stderr

    production_url = _run_preview_guard(
        **{
            **valid_preview,
            "NEXT_PUBLIC_SUPABASE_URL": "https://ahrwvmizzykyyfavdvfv.supabase.co",
        },
    )
    assert production_url.returncode != 0

    for key in FORBIDDEN_PREVIEW_KEYS:
        blocked = _run_preview_guard(**valid_preview, **{key: "test-value"})
        assert blocked.returncode != 0, f"preview guard allowed {key}"

    production = _run_preview_guard(
        VERCEL_ENV="production",
        DATABASE_URL="production-value",
    )
    assert production.returncode == 0, production.stderr
