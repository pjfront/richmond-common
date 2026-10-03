"""Regression guard for the Vercel deploy gate (T0.2 of the audit plan).

`web/vercel.json` must disable every automatic Git deployment so that
production and approved Previews use explicit trusted-controller paths.
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
    "SITE_ACCESS_PASSWORD",
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


def test_vercel_json_disables_all_automatic_git_deployments():
    """Only the trusted controllers may create Vercel deployments.

    Vercel documents the global boolean as the control for disabling all
    automatic deployments while retaining CLI, Deploy Hook, and REST API
    deployment paths.
    """
    config = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))
    assert config.get("git", {}).get("deploymentEnabled") is False


def test_vercel_ignore_command_rejects_automation_before_production():
    """The remaining ignored-build rule is automation-only defense in depth."""
    config = json.loads(VERCEL_JSON.read_text(encoding="utf-8"))
    command = config.get("ignoreCommand", "")
    assert command == (
        'case "$VERCEL_GIT_COMMIT_REF" in '
        "heartbeat|automation/*|automation-*) exit 0 ;; *) exit 1 ;; esac"
    )

    if os.name == "nt":
        bash_path = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / (
            "Git/bin/bash.exe"
        )
        bash = str(bash_path) if bash_path.exists() else None
    else:
        bash = shutil.which("bash")
    if not bash:
        pytest.skip("Bash is not available for the Vercel shell-command test")
    for branch in ("heartbeat", "automation/daily", "automation-daily"):
        result = subprocess.run(
            [bash, "-c", command],
            env={
                **os.environ,
                "VERCEL_ENV": "production",
                "VERCEL_GIT_COMMIT_REF": branch,
            },
            text=True,
            capture_output=True,
            check=False,
        )
        assert result.returncode == 0, branch

    production = subprocess.run(
        [bash, "-c", command],
        env={
            **os.environ,
            "VERCEL_ENV": "production",
            "VERCEL_GIT_COMMIT_REF": "main",
        },
        text=True,
        capture_output=True,
        check=False,
    )
    assert production.returncode != 0


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
    assert "RICHMOND_PREVIEW_SOURCE_HEAD_SHA" in guard_text
    assert "VERCEL_GIT_COMMIT_SHA" in guard_text
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
    env.pop("VERCEL_GIT_COMMIT_REF", None)
    env.pop("VERCEL_GIT_COMMIT_SHA", None)
    env.pop("RICHMOND_PREVIEW_GIT_BRANCH", None)
    env.pop("RICHMOND_PREVIEW_SUPABASE_REF", None)
    env.pop("RICHMOND_PREVIEW_SOURCE_HEAD_SHA", None)
    for key in ("RICHMOND_READ_ONLY_STAGE", "SITE_ACCESS_REQUIRED", "SITE_ACCESS_PASSWORD", "RICHMOND_API_BUDGET_LOCK"):
        env.pop(key, None)
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
    approved_sha = "1" * 40
    valid_preview = {
        "VERCEL_ENV": "preview",
        "VERCEL_GIT_COMMIT_REF": "codex/example-preview",
        "VERCEL_GIT_COMMIT_SHA": approved_sha,
        "RICHMOND_PREVIEW_GIT_BRANCH": "codex/example-preview",
        "RICHMOND_PREVIEW_SOURCE_HEAD_SHA": approved_sha,
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

    missing_git_branch = _run_preview_guard(
        **{
            **valid_preview,
            "VERCEL_GIT_COMMIT_REF": "",
        },
    )
    assert missing_git_branch.returncode != 0
    assert "VERCEL_GIT_COMMIT_REF (missing)" in missing_git_branch.stderr

    wrong_git_sha = _run_preview_guard(
        **{
            **valid_preview,
            "VERCEL_GIT_COMMIT_SHA": "2" * 40,
        },
    )
    assert wrong_git_sha.returncode != 0
    assert "wrong commit scope" in wrong_git_sha.stderr

    missing_git_sha = _run_preview_guard(
        **{
            **valid_preview,
            "VERCEL_GIT_COMMIT_SHA": "",
        },
    )
    assert missing_git_sha.returncode != 0
    assert "VERCEL_GIT_COMMIT_SHA (missing or invalid)" in missing_git_sha.stderr

    missing_approved_sha = _run_preview_guard(
        **{
            **valid_preview,
            "RICHMOND_PREVIEW_SOURCE_HEAD_SHA": "",
        },
    )
    assert missing_approved_sha.returncode != 0
    assert (
        "RICHMOND_PREVIEW_SOURCE_HEAD_SHA (missing or invalid)"
        in missing_approved_sha.stderr
    )

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


def _read_only_stage_env() -> dict[str, str]:
    return {
        "VERCEL_ENV": "preview",
        "VERCEL_GIT_COMMIT_REF": "codex/commons-search-stage",
        "RICHMOND_PREVIEW_GIT_BRANCH": "codex/commons-search-stage",
        "VERCEL_GIT_COMMIT_SHA": "3" * 40,
        "RICHMOND_PREVIEW_SOURCE_HEAD_SHA": "3" * 40,
        "RICHMOND_PREVIEW_SUPABASE_REF": "ahrwvmizzykyyfavdvfv",
        "NEXT_PUBLIC_SUPABASE_URL": "https://ahrwvmizzykyyfavdvfv.supabase.co",
        "NEXT_PUBLIC_SUPABASE_ANON_KEY": "sb_publishable_test-value",
        "RICHMOND_READ_ONLY_STAGE": "true",
        "SITE_ACCESS_REQUIRED": "true",
        "SITE_ACCESS_PASSWORD": "test-staging-password-at-least-24-characters",
        "RICHMOND_API_BUDGET_LOCK": "true",
    }


def test_read_only_staging_exception_is_private_and_branch_bound():
    stage = _read_only_stage_env()
    passed = _run_preview_guard(**stage)
    assert passed.returncode == 0, passed.stderr
    for key in FORBIDDEN_PREVIEW_KEYS:
        if key == "SITE_ACCESS_PASSWORD":
            continue
        blocked = _run_preview_guard(**{**stage, key: "must-not-be-available"})
        assert blocked.returncode != 0, key
        assert "SITE_ACCESS_PASSWORD (outside approved read-only staging)" in blocked.stderr


@pytest.mark.parametrize(
    ("changes", "violation"),
    [
        ({"VERCEL_ENV": "production"}, "Private staging cannot be deployed as production"),
        (
            {"VERCEL_GIT_COMMIT_REF": "codex/other", "RICHMOND_PREVIEW_GIT_BRANCH": "codex/other"},
            "RICHMOND_READ_ONLY_STAGE (wrong staging branch)",
        ),
        ({"VERCEL_GIT_COMMIT_REF": ""}, "VERCEL_GIT_COMMIT_REF (missing)"),
        ({"RICHMOND_PREVIEW_GIT_BRANCH": ""}, "RICHMOND_PREVIEW_GIT_BRANCH (missing)"),
        ({"RICHMOND_PREVIEW_GIT_BRANCH": "codex/other"}, "wrong branch scope"),
        ({"VERCEL_GIT_COMMIT_SHA": "4" * 40}, "wrong commit scope"),
        ({"VERCEL_GIT_COMMIT_SHA": ""}, "VERCEL_GIT_COMMIT_SHA (missing or invalid)"),
        ({"VERCEL_GIT_COMMIT_SHA": "3" * 7}, "VERCEL_GIT_COMMIT_SHA (missing or invalid)"),
        ({"RICHMOND_PREVIEW_SOURCE_HEAD_SHA": ""}, "RICHMOND_PREVIEW_SOURCE_HEAD_SHA (missing or invalid)"),
        ({"RICHMOND_PREVIEW_SOURCE_HEAD_SHA": "3" * 7}, "RICHMOND_PREVIEW_SOURCE_HEAD_SHA (missing or invalid)"),
        ({"SITE_ACCESS_REQUIRED": "false"}, "SITE_ACCESS_REQUIRED (staging must be password protected)"),
        ({"SITE_ACCESS_PASSWORD": ""}, "SITE_ACCESS_PASSWORD (staging password missing or invalid length)"),
        ({"SITE_ACCESS_PASSWORD": "x" * 23}, "SITE_ACCESS_PASSWORD (staging password missing or invalid length)"),
        ({"SITE_ACCESS_PASSWORD": " " * 24}, "SITE_ACCESS_PASSWORD (staging password missing or invalid length)"),
        ({"SITE_ACCESS_PASSWORD": "x" * 1025}, "SITE_ACCESS_PASSWORD (staging password missing or invalid length)"),
        ({"RICHMOND_API_BUDGET_LOCK": "false"}, "RICHMOND_API_BUDGET_LOCK (staging paid inference must be locked)"),
        ({"RICHMOND_PREVIEW_SUPABASE_REF": "abcdefghijklmnopqrst"}, "wrong public-data project"),
        ({"NEXT_PUBLIC_SUPABASE_URL": ""}, "NEXT_PUBLIC_SUPABASE_URL (missing)"),
        ({"NEXT_PUBLIC_SUPABASE_URL": "https://user@ahrwvmizzykyyfavdvfv.supabase.co"}, "wrong public-data origin"),
        ({"NEXT_PUBLIC_SUPABASE_URL": "https://ahrwvmizzykyyfavdvfv.supabase.co/path"}, "wrong public-data origin"),
        ({"NEXT_PUBLIC_SUPABASE_URL": "https://ahrwvmizzykyyfavdvfv.supabase.co?key=value"}, "wrong public-data origin"),
        ({"NEXT_PUBLIC_SUPABASE_URL": "https://ahrwvmizzykyyfavdvfv.supabase.co#fragment"}, "wrong public-data origin"),
        ({"NEXT_PUBLIC_SUPABASE_URL": "http://ahrwvmizzykyyfavdvfv.supabase.co"}, "must use HTTPS"),
        ({"NEXT_PUBLIC_SUPABASE_URL": "https://abcdefghijklmnopqrst.supabase.co"}, "wrong public-data origin"),
        ({"NEXT_PUBLIC_SUPABASE_ANON_KEY": ""}, "NEXT_PUBLIC_SUPABASE_ANON_KEY (missing)"),
        ({"NEXT_PUBLIC_SUPABASE_ANON_KEY": "sb_secret_must-never-be-public"}, "not a public key"),
        ({"RICHMOND_READ_ONLY_STAGE": "false"}, "SITE_ACCESS_PASSWORD (outside approved read-only staging)"),
        ({"RICHMOND_READ_ONLY_STAGE": ""}, "SITE_ACCESS_PASSWORD (outside approved read-only staging)"),
    ],
)
def test_read_only_staging_rejects_incomplete_scope(changes: dict[str, str], violation: str):
    stage = {**_read_only_stage_env(), **changes}
    blocked = _run_preview_guard(**stage)
    assert blocked.returncode != 0
    assert violation in blocked.stderr
    if stage["SITE_ACCESS_PASSWORD"]:
        assert stage["SITE_ACCESS_PASSWORD"] not in blocked.stdout + blocked.stderr
    if stage["VERCEL_ENV"] == "preview" and stage["SITE_ACCESS_PASSWORD"].strip():
        assert "SITE_ACCESS_PASSWORD (outside approved read-only staging)" in blocked.stderr


@pytest.mark.parametrize("password_length", [24, 1024])
def test_read_only_staging_accepts_password_length_boundaries(password_length: int):
    stage = {**_read_only_stage_env(), "SITE_ACCESS_PASSWORD": "x" * password_length}
    passed = _run_preview_guard(**stage)
    assert passed.returncode == 0, passed.stderr
    assert stage["SITE_ACCESS_PASSWORD"] not in passed.stdout + passed.stderr
