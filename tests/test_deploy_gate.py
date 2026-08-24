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
PREVIEW_IGNORE_GATE = (
    REPO_ROOT / "web" / "scripts" / "should-ignore-vercel-build.mjs"
)
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


def test_vercel_json_does_not_disable_branches_before_the_ignore_gate():
    """Branch policy stays centralized in the tested Ignored Build Step."""
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


def test_vercel_ignore_command_uses_approval_gate():
    """The ignored-build command delegates to the tested approval gate."""
    config = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))
    command = config.get("ignoreCommand", "")
    assert command == "node scripts/should-ignore-vercel-build.mjs"
    assert PREVIEW_IGNORE_GATE.exists()
    gate_text = PREVIEW_IGNORE_GATE.read_text(encoding="utf-8")
    assert "VERCEL_GIT_COMMIT_REF" in gate_text
    assert "RICHMOND_PREVIEW_GIT_BRANCH" in gate_text
    assert "heartbeat" in gate_text
    assert "automation/" in gate_text


def _run_preview_ignore_gate(**updates: str) -> subprocess.CompletedProcess[str]:
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js is not available on PATH")
    env = os.environ.copy()
    for key in (
        "VERCEL_ENV",
        "VERCEL_GIT_COMMIT_REF",
        "RICHMOND_PREVIEW_GIT_BRANCH",
    ):
        env.pop(key, None)
    env.update(updates)
    return subprocess.run(
        [node, str(PREVIEW_IGNORE_GATE)],
        cwd=PREVIEW_IGNORE_GATE.parent.parent,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def test_preview_ignore_gate_behavior_matrix():
    """Exit 0 skips; non-zero builds only production or an approved branch."""
    production = _run_preview_ignore_gate(
        VERCEL_ENV="production",
        VERCEL_GIT_COMMIT_REF="main",
    )
    assert production.returncode != 0, production.stdout

    approved = _run_preview_ignore_gate(
        VERCEL_ENV="preview",
        VERCEL_GIT_COMMIT_REF="codex/approved-preview",
        RICHMOND_PREVIEW_GIT_BRANCH="codex/approved-preview",
    )
    assert approved.returncode != 0, approved.stdout

    missing_approval = _run_preview_ignore_gate(
        VERCEL_ENV="preview",
        VERCEL_GIT_COMMIT_REF="codex/unapproved-preview",
    )
    assert missing_approval.returncode == 0, missing_approval.stdout
    assert "skipped unapproved Preview branch" in missing_approval.stdout

    wrong_branch = _run_preview_ignore_gate(
        VERCEL_ENV="preview",
        VERCEL_GIT_COMMIT_REF="codex/one-preview",
        RICHMOND_PREVIEW_GIT_BRANCH="codex/other-preview",
    )
    assert wrong_branch.returncode == 0, wrong_branch.stdout

    unknown_environment = _run_preview_ignore_gate(
        VERCEL_GIT_COMMIT_REF="codex/approved-preview",
        RICHMOND_PREVIEW_GIT_BRANCH="codex/approved-preview",
    )
    assert unknown_environment.returncode == 0, unknown_environment.stdout

    for branch in ("heartbeat", "automation/daily", "automation-daily"):
        automation = _run_preview_ignore_gate(
            VERCEL_ENV="preview",
            VERCEL_GIT_COMMIT_REF=branch,
            RICHMOND_PREVIEW_GIT_BRANCH=branch,
        )
        assert automation.returncode == 0, branch


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
    assert "RICHMOND_PREVIEW_GIT_BRANCH" in guard_text
    assert "RICHMOND_PREVIEW_SUPABASE_REF" in guard_text
    assert "VERCEL_GIT_COMMIT_REF" in guard_text
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
        "VERCEL_GIT_COMMIT_REF": "codex/example-preview",
        "RICHMOND_PREVIEW_GIT_BRANCH": "codex/example-preview",
        "RICHMOND_PREVIEW_SUPABASE_REF": "abcdefghijklmnopqrst",
        "NEXT_PUBLIC_SUPABASE_URL": "https://abcdefghijklmnopqrst.supabase.co",
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

    wrong_git_branch = _run_preview_guard(
        **{
            **valid_preview,
            "RICHMOND_PREVIEW_GIT_BRANCH": "codex/someone-elses-preview",
        },
    )
    assert wrong_git_branch.returncode != 0
    assert "wrong branch scope" in wrong_git_branch.stderr

    wrong_supabase_ref = _run_preview_guard(
        **{
            **valid_preview,
            "RICHMOND_PREVIEW_SUPABASE_REF": "zyxwvutsrqponmlkjihg",
        },
    )
    assert wrong_supabase_ref.returncode != 0
    assert "branch ref mismatch" in wrong_supabase_ref.stderr

    elevated_key = _run_preview_guard(
        **{
            **valid_preview,
            "NEXT_PUBLIC_SUPABASE_ANON_KEY": "sb_secret_must-never-be-public",
        },
    )
    assert elevated_key.returncode != 0
    assert "not a public key" in elevated_key.stderr

    for key in FORBIDDEN_PREVIEW_KEYS:
        blocked = _run_preview_guard(**valid_preview, **{key: "test-value"})
        assert blocked.returncode != 0, f"preview guard allowed {key}"

    production = _run_preview_guard(
        VERCEL_ENV="production",
        DATABASE_URL="production-value",
    )
    assert production.returncode == 0, production.stderr
