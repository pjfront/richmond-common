"""Fail-closed tests for the exact-SHA production deploy wrapper.

Every integration test runs the real shell wrapper in a temporary Git
repository with fake GitHub and pinned-npx/Vercel commands. No test can make a
network request or a Vercel deployment.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import shutil
import subprocess

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE_SCRIPT = REPO_ROOT / "web" / "scripts" / "deploy-prod.sh"
POWERSHELL_LAUNCHER = REPO_ROOT / "web" / "scripts" / "deploy-prod.ps1"
VERCEL_IGNORE = REPO_ROOT / ".vercelignore"
JUDGMENT_CATALOG = REPO_ROOT / ".claude" / "rules" / "judgment-boundaries.md"
WEB_GUIDANCE = REPO_ROOT / "web" / "CLAUDE.md"
BUILD_CHECK_WORKFLOW = REPO_ROOT / ".github" / "workflows" / "build-check.yml"
CANONICAL_REPOSITORY = "pjfront/richmond-common"
VERCEL_ORG_ID = "team_EZvKrao9Jh9nwoKNX648v4qy"
VERCEL_PROJECT_ID = "prj_Y0sIBsC2DKkl4lsoKbS11Y3cFTz4"
PREVIOUS_DEPLOYMENT_ID = "dpl_PreviousProduction123"
NEW_DEPLOYMENT_ID = "dpl_NewProduction456"
DEPLOYMENT_URL = "https://rtp-exact-sha-test.vercel.app"


def _bash_path() -> str:
    if os.name == "nt":
        candidate = Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / (
            "Git/bin/bash.exe"
        )
        if candidate.exists():
            return str(candidate)
    bash = shutil.which("bash")
    if bash:
        return bash
    pytest.skip("Bash is required for deploy wrapper tests")


def _git(cwd: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=cwd, text=True, capture_output=True, check=False
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.strip()


def _write_lf(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="\n") as handle:
        handle.write(text.replace("\r\n", "\n"))
    path.chmod(0o755)


@dataclass
class DeployHarness:
    repo: Path
    origin: Path
    script: Path
    fake_bin: Path
    sha: str

    def run(
        self,
        approved_sha: str | None = None,
        *,
        canonical_sha: str | None = None,
        ci_output: str | None = None,
        gh_api_exit: int = 0,
        gh_ci_exit: int = 0,
        dirty_on_ci_call: int = 0,
        advance_main_on_ci_call: int = 0,
        advanced_canonical_sha: str | None = None,
        inspect_fail_on_call: int = 0,
        vercel_api_fail_on_call: int = 0,
        previous_json: str | None = None,
        previous_api_json: str | None = None,
        deployment_json: str | None = None,
        alias_json: str | None = None,
        alias_api_json: str | None = None,
        deploy_exit: int = 0,
        deploy_url: str = DEPLOYMENT_URL,
        extra_env: dict[str, str] | None = None,
        windows_launcher: bool = False,
    ) -> subprocess.CompletedProcess[str]:
        expected_sha = approved_sha or self.sha
        if ci_output is None:
            ci_output = f"completed|success|{expected_sha}|push|4242"
        if deployment_json is None:
            deployment_json = (
                '{"uid":"'
                + NEW_DEPLOYMENT_ID
                + '","projectId":"'
                + VERCEL_PROJECT_ID
                + '","url":"rtp-exact-sha-test.vercel.app",'
                + '"target":"production","readyState":"READY","meta":'
                + '{"githubCommitSha":"'
                + expected_sha
                + '","githubCommitRef":"main","githubDeployment":"1"}}'
            )
        if previous_json is None:
            previous_json = (
                '{"id":"'
                + PREVIOUS_DEPLOYMENT_ID
                + '","target":"production","readyState":"READY"}'
            )
        if previous_api_json is None:
            previous_api_json = (
                '{"uid":"'
                + PREVIOUS_DEPLOYMENT_ID
                + '","projectId":"'
                + VERCEL_PROJECT_ID
                + '","url":"rtp-previous.vercel.app",'
                + '"target":"production","readyState":"READY"}'
            )
        if alias_json is None:
            alias_json = (
                '{"id":"'
                + NEW_DEPLOYMENT_ID
                + '","target":"production","readyState":"READY"}'
            )
        if alias_api_json is None:
            alias_api_json = (
                '{"uid":"'
                + NEW_DEPLOYMENT_ID
                + '","projectId":"'
                + VERCEL_PROJECT_ID
                + '","url":"rtp-exact-sha-test.vercel.app",'
                + '"target":"production","readyState":"READY"}'
            )

        env = os.environ.copy()
        env.pop("VERCEL_ORG_ID", None)
        env.pop("VERCEL_PROJECT_ID", None)
        env.update(
            {
                "PATH": f"{self.fake_bin}{os.pathsep}{env.get('PATH', '')}",
                "FAKE_CANONICAL_MAIN_SHA": canonical_sha or expected_sha,
                "FAKE_ADVANCED_CANONICAL_SHA": advanced_canonical_sha
                or ("1" * 40),
                "FAKE_GH_API_EXIT": str(gh_api_exit),
                "FAKE_GH_CI_EXIT": str(gh_ci_exit),
                "FAKE_GH_CI_OUTPUT": ci_output,
                "FAKE_GH_DIRTY_ON_CI_CALL": str(dirty_on_ci_call),
                "FAKE_GH_ADVANCE_MAIN_ON_CI_CALL": str(
                    advance_main_on_ci_call
                ),
                "FAKE_INSPECT_FAIL_ON_CALL": str(inspect_fail_on_call),
                "FAKE_VERCEL_API_FAIL_ON_CALL": str(vercel_api_fail_on_call),
                "FAKE_PREVIOUS_JSON": previous_json,
                "FAKE_PREVIOUS_API_JSON": previous_api_json,
                "FAKE_DEPLOYMENT_JSON": deployment_json,
                "FAKE_ALIAS_JSON": alias_json,
                "FAKE_ALIAS_API_JSON": alias_api_json,
                "FAKE_DEPLOY_EXIT": str(deploy_exit),
                "FAKE_DEPLOY_URL": deploy_url,
            }
        )
        if extra_env:
            env.update(extra_env)
        if windows_launcher:
            powershell = shutil.which("powershell.exe")
            if powershell is None:
                pytest.skip("Windows PowerShell is required for launcher test")
            command = [
                powershell,
                "-NoProfile",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                str(self.script.with_suffix(".ps1")),
                expected_sha,
            ]
        else:
            command = [_bash_path(), str(self.script), expected_sha]
        return subprocess.run(
            command,
            cwd=self.repo,
            env=env,
            text=True,
            capture_output=True,
            check=False,
        )

    @property
    def npx_calls(self) -> list[str]:
        path = self.repo / "npx-calls.log"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    @property
    def artifact_snapshot(self) -> dict[str, str]:
        path = self.repo / "vercel-artifact.log"
        if not path.exists():
            return {}
        return dict(
            line.split("=", 1)
            for line in path.read_text(encoding="utf-8").splitlines()
        )

    @property
    def gh_calls(self) -> list[str]:
        path = self.repo / "gh-calls.log"
        return path.read_text(encoding="utf-8").splitlines() if path.exists() else []

    def commit(self, message: str) -> str:
        _git(self.repo, "add", "-A")
        _git(self.repo, "commit", "-m", message)
        self.sha = _git(self.repo, "rev-parse", "HEAD")
        return self.sha


@pytest.fixture
def deploy_harness(tmp_path: Path) -> DeployHarness:
    repo = tmp_path / "checkout"
    origin = tmp_path / "origin.git"
    fake_bin = tmp_path / "fake-bin"
    repo.mkdir()
    fake_bin.mkdir()

    _git(tmp_path, "init", "--bare", str(origin))
    _git(repo, "init", "--initial-branch=main")
    _git(repo, "config", "user.email", "deploy-test@example.invalid")
    _git(repo, "config", "user.name", "Deploy Test")

    script = repo / "web" / "scripts" / "deploy-prod.sh"
    _write_lf(script, SOURCE_SCRIPT.read_text(encoding="utf-8"))
    _write_lf(
        script.with_suffix(".ps1"),
        POWERSHELL_LAUNCHER.read_text(encoding="utf-8"),
    )
    _write_lf(
        repo / ".gitignore",
        ".env*\n.vercel/\n.gh-*\n.npx-*\ngh-calls.log\nignored-local.txt\n"
        "npx-calls.log\nvercel-artifact.log\nunexpected-ignored.txt\n",
    )
    _write_lf(repo / "web" / "fixture.txt", "verified deploy source\n")
    _git(repo, "add", ".gitignore", "web")
    _git(repo, "commit", "-m", "test fixture")

    github_url = "https://github.com/pjfront/richmond-common.git"
    _git(repo, "config", f"url.{origin.as_uri()}.insteadOf", github_url)
    _git(repo, "remote", "add", "origin", github_url)
    _git(repo, "push", "--set-upstream", "origin", "main")
    sha = _git(repo, "rev-parse", "HEAD")

    _write_lf(
        fake_bin / "gh",
        """#!/usr/bin/env bash
printf '%s\n' "$*" >> "$PWD/gh-calls.log"
if [[ "${1:-}" == "api" ]]; then
  if [[ "$*" != "api --hostname github.com repos/pjfront/richmond-common/git/ref/heads/main --jq .object.sha" ]]; then
    printf '%s\n' 'fake gh rejects unpinned canonical-main query' >&2
    exit 99
  fi
  if [[ "${FAKE_GH_API_EXIT:-0}" != "0" ]]; then
    exit "$FAKE_GH_API_EXIT"
  fi
  if [[ -f "$PWD/.gh-main-advanced" ]]; then
    printf '%s\n' "$FAKE_ADVANCED_CANONICAL_SHA"
  else
    printf '%s\n' "$FAKE_CANONICAL_MAIN_SHA"
  fi
  exit 0
fi
if [[ "${1:-}" != "run" || "${2:-}" != "list" ]]; then
  printf '%s\n' 'unexpected fake gh command' >&2
  exit 98
fi
if [[ "${FAKE_GH_CI_EXIT:-0}" != "0" ]]; then
  exit "$FAKE_GH_CI_EXIT"
fi
call_count=0
if [[ -f "$PWD/.gh-ci-call-count" ]]; then
  read -r call_count < "$PWD/.gh-ci-call-count"
fi
call_count=$((call_count + 1))
printf '%s\n' "$call_count" > "$PWD/.gh-ci-call-count"
if [[ "${FAKE_GH_DIRTY_ON_CI_CALL:-0}" == "$call_count" ]]; then
  printf '%s\n' 'changed during CI lookup' >> "$PWD/web/fixture.txt"
fi
if [[ "${FAKE_GH_ADVANCE_MAIN_ON_CI_CALL:-0}" == "$call_count" ]]; then
  touch "$PWD/.gh-main-advanced"
fi
if [[ -n "${FAKE_GH_CI_OUTPUT:-}" ]]; then
  printf '%s\n' "$FAKE_GH_CI_OUTPUT"
fi
""",
    )
    _write_lf(
        fake_bin / "npx",
        """#!/usr/bin/env bash
printf '%s\n' "$*" >> "$PWD/npx-calls.log"
if [[ "${NO_UPDATE_NOTIFIER:-}" != "1" ]]; then
  printf '%s\n' 'fake npx requires update checks disabled' >&2
  exit 82
fi
if [[ "${VERCEL_TELEMETRY_DISABLED:-}" != "1" ]]; then
  printf '%s\n' 'fake npx requires telemetry disabled' >&2
  exit 81
fi
if [[ "${VERCEL_CLI_USE_NATIVE_BINARY:-}" != "0" ]]; then
  printf '%s\n' 'fake npx requires reviewed JavaScript CLI path' >&2
  exit 80
fi
if [[ "${1:-}" == "--registry=https://registry.npmjs.org/" && \
  "${2:-}" == "--offline=false" && "${3:-}" == "--prefer-online" && \
  "${4:-}" == "--yes" && "${5:-}" == "vercel@59.1.4" && \
  "${6:-}" == "--version" ]]; then
  touch "$PWD/.npx-prefetched"
  printf '%s\n' '59.1.4'
  exit 0
fi
if [[ "${1:-}" != "--registry=https://registry.npmjs.org/" || \
  "${2:-}" != "--offline" || "${3:-}" != "--yes" || \
  "${4:-}" != "vercel@59.1.4" || "${5:-}" != "--api" || \
  "${6:-}" != "https://api.vercel.com" || "${7:-}" != "--scope" || \
  "${8:-}" != "phillips-projects-1f180556" || ! -f "$PWD/.npx-prefetched" ]]; then
  printf '%s\n' 'fake npx requires prepared offline vercel@59.1.4' >&2
  exit 89
fi
if [[ "${VERCEL_ORG_ID:-}" != "team_EZvKrao9Jh9nwoKNX648v4qy" || \
  "${VERCEL_PROJECT_ID:-}" != "prj_Y0sIBsC2DKkl4lsoKbS11Y3cFTz4" ]]; then
  printf '%s\n' 'fake npx detected wrong target binding' >&2
  exit 90
fi
shift 8
if [[ "${1:-}" == "api" ]]; then
  call_count=0
  if [[ -f "$PWD/.npx-api-count" ]]; then
    read -r call_count < "$PWD/.npx-api-count"
  fi
  call_count=$((call_count + 1))
  printf '%s\n' "$call_count" > "$PWD/.npx-api-count"
  if [[ "${FAKE_VERCEL_API_FAIL_ON_CALL:-0}" == "$call_count" ]]; then
    exit 83
  fi
  endpoint="${2:-}"
  if [[ "$endpoint" != *"?teamId=team_EZvKrao9Jh9nwoKNX648v4qy" ]]; then
    printf '%s\n' 'fake Vercel API received wrong deployment endpoint' >&2
    exit 84
  fi
  if [[ "$endpoint" == *"/dpl_PreviousProduction123?"* ]]; then
    printf '%s\n' "$FAKE_PREVIOUS_API_JSON"
  elif [[ "$endpoint" == *"/rtp-exact-sha-test.vercel.app?"* ]]; then
    printf '%s\n' "$FAKE_DEPLOYMENT_JSON"
  else
    printf '%s\n' "$FAKE_ALIAS_API_JSON"
  fi
  exit 0
fi
if [[ "${1:-}" == "inspect" ]]; then
  call_count=0
  if [[ -f "$PWD/.npx-inspect-count" ]]; then
    read -r call_count < "$PWD/.npx-inspect-count"
  fi
  call_count=$((call_count + 1))
  printf '%s\n' "$call_count" > "$PWD/.npx-inspect-count"
  if [[ "${FAKE_INSPECT_FAIL_ON_CALL:-0}" == "$call_count" ]]; then
    exit 88
  fi
  if [[ "$call_count" == "1" || "${FAKE_DEPLOY_EXIT:-0}" != "0" ]]; then
    printf '%s\n' "$FAKE_PREVIOUS_JSON"
  else
    printf '%s\n' "$FAKE_ALIAS_JSON"
  fi
  exit 0
fi
if [[ "${1:-}" == "rollback" ]]; then
  printf '%s\n' 'deploy wrapper must never auto-rollback' >&2
  exit 87
fi
deploy_cwd=""
all_args="$*"
while [[ "$#" -gt 0 ]]; do
  if [[ "$1" == "--cwd" ]]; then
    deploy_cwd="$2"
    shift 2
    continue
  fi
  shift
done
if [[ -z "$deploy_cwd" || ! -d "$deploy_cwd" ]]; then
  printf '%s\n' 'fake Vercel requires an existing --cwd artifact' >&2
  exit 86
fi
for forbidden in .env .env.production .vercel ignored-local.txt unexpected-ignored.txt; do
  if [[ -e "$deploy_cwd/$forbidden" ]]; then
    printf 'forbidden artifact path: %s\n' "$forbidden" >&2
    exit 85
  fi
done
fixture_content="$(cat "$deploy_cwd/web/fixture.txt")"
printf 'cwd=%s\nfixture=%s\nargs=%s\n' \
  "$deploy_cwd" "$fixture_content" "$all_args" > "$PWD/vercel-artifact.log"
if [[ "${FAKE_DEPLOY_EXIT:-0}" != "0" ]]; then
  exit "$FAKE_DEPLOY_EXIT"
fi
printf '%s\n' "$FAKE_DEPLOY_URL"
""",
    )

    return DeployHarness(repo, origin, script, fake_bin, sha)


def test_requires_one_full_lowercase_sha(deploy_harness: DeployHarness) -> None:
    env = os.environ.copy()
    env["PATH"] = f"{deploy_harness.fake_bin}{os.pathsep}{env.get('PATH', '')}"
    missing = subprocess.run(
        [_bash_path(), str(deploy_harness.script)],
        cwd=deploy_harness.repo,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )
    short = deploy_harness.run(deploy_harness.sha[:12])
    uppercase = deploy_harness.run(deploy_harness.sha.upper())

    assert missing.returncode != 0
    assert "exactly one operator-approved full commit SHA" in missing.stderr
    assert short.returncode != 0
    assert "exactly 40 lowercase hexadecimal" in short.stderr
    assert uppercase.returncode != 0
    assert deploy_harness.npx_calls == []


@pytest.mark.parametrize("dirty_kind", ["tracked", "untracked"])
def test_refuses_dirty_checkout(
    deploy_harness: DeployHarness, dirty_kind: str
) -> None:
    path = (
        deploy_harness.repo / "web" / "fixture.txt"
        if dirty_kind == "tracked"
        else deploy_harness.repo / "unexpected.txt"
    )
    _write_lf(path, "changed\n")

    result = deploy_harness.run()

    assert result.returncode != 0
    assert "checkout is not clean" in result.stderr
    assert deploy_harness.npx_calls == []


def test_refuses_non_main_branch_even_at_exact_sha(
    deploy_harness: DeployHarness,
) -> None:
    _git(deploy_harness.repo, "switch", "--create", "feature")
    result = deploy_harness.run()
    assert result.returncode != 0
    assert "must be branch main; found 'feature'" in result.stderr
    assert deploy_harness.npx_calls == []


def test_refuses_checkout_head_that_differs_from_approval(
    deploy_harness: DeployHarness,
) -> None:
    old_sha = deploy_harness.sha
    _write_lf(deploy_harness.repo / "web" / "second.txt", "second commit\n")
    deploy_harness.commit("second")
    result = deploy_harness.run(old_sha)
    assert result.returncode != 0
    assert "does not equal approved SHA" in result.stderr
    assert deploy_harness.npx_calls == []


def test_refuses_approval_that_is_no_longer_canonical_main(
    deploy_harness: DeployHarness,
) -> None:
    result = deploy_harness.run(canonical_sha="1" * 40)
    assert result.returncode != 0
    assert "canonical GitHub main" in result.stderr
    assert "does not equal approved SHA" in result.stderr
    assert deploy_harness.npx_calls == []


def test_refuses_fork_origin_before_network_or_vercel(
    deploy_harness: DeployHarness,
) -> None:
    _git(
        deploy_harness.repo,
        "remote",
        "set-url",
        "origin",
        "https://github.com/someone/fork.git",
    )
    result = deploy_harness.run()
    assert result.returncode != 0
    assert "origin must be the canonical" in result.stderr
    assert deploy_harness.gh_calls == []
    assert deploy_harness.npx_calls == []


def test_refuses_credentialed_origin_without_leaking_userinfo(
    deploy_harness: DeployHarness,
) -> None:
    marker = "credential-must-not-appear"
    _git(
        deploy_harness.repo,
        "remote",
        "set-url",
        "origin",
        f"https://{marker}@github.com/pjfront/richmond-common.git",
    )
    result = deploy_harness.run()
    assert result.returncode != 0
    assert "configured value is intentionally redacted" in result.stderr
    assert marker not in result.stdout
    assert marker not in result.stderr
    assert deploy_harness.gh_calls == []
    assert deploy_harness.npx_calls == []


def test_refuses_git_environment_identity_override_without_leaking_value(
    deploy_harness: DeployHarness,
) -> None:
    marker = "git-override-secret-must-not-appear"
    result = deploy_harness.run(extra_env={"GIT_DIR": marker})
    assert result.returncode != 0
    assert "forbidden Git environment override is set: GIT_DIR" in result.stderr
    assert "ACTION: clear that variable" in result.stderr
    assert marker not in result.stdout
    assert marker not in result.stderr
    assert deploy_harness.gh_calls == []
    assert deploy_harness.npx_calls == []


def test_refuses_canonical_main_lookup_failure(
    deploy_harness: DeployHarness,
) -> None:
    result = deploy_harness.run(gh_api_exit=1)
    assert result.returncode != 0
    assert "could not query canonical GitHub main" in result.stderr
    assert deploy_harness.npx_calls == []


def test_refuses_missing_build_check(deploy_harness: DeployHarness) -> None:
    result = deploy_harness.run(ci_output="")
    assert result.returncode != 0
    assert "no Build Check push run exists" in result.stderr
    assert deploy_harness.npx_calls == []


def test_refuses_ci_lookup_failure(deploy_harness: DeployHarness) -> None:
    result = deploy_harness.run(gh_ci_exit=1)
    assert result.returncode != 0
    assert "GitHub CI lookup failed" in result.stderr
    assert deploy_harness.npx_calls == []


def test_refuses_stale_build_check(deploy_harness: DeployHarness) -> None:
    stale_sha = "1" * 40
    result = deploy_harness.run(
        ci_output=f"completed|success|{stale_sha}|push|4242"
    )
    assert result.returncode != 0
    assert "not an exact main-push proof" in result.stderr
    assert deploy_harness.npx_calls == []


@pytest.mark.parametrize(
    ("status", "conclusion", "message"),
    [
        ("in_progress", "missing", "is in_progress"),
        ("completed", "failure", "concluded failure"),
        ("completed", "cancelled", "concluded cancelled"),
    ],
)
def test_refuses_non_green_build_check(
    deploy_harness: DeployHarness,
    status: str,
    conclusion: str,
    message: str,
) -> None:
    result = deploy_harness.run(
        ci_output=f"{status}|{conclusion}|{deploy_harness.sha}|push|4242"
    )
    assert result.returncode != 0
    assert message in result.stderr
    assert deploy_harness.npx_calls == []


def test_rechecks_checkout_after_final_ci_query(
    deploy_harness: DeployHarness,
) -> None:
    result = deploy_harness.run(dirty_on_ci_call=2)
    assert result.returncode != 0
    assert "checkout is not clean" in result.stderr
    assert not any(" --prod " in f" {call} " for call in deploy_harness.npx_calls)


def test_requeries_main_after_final_ci_and_refuses_if_it_advanced(
    deploy_harness: DeployHarness,
) -> None:
    result = deploy_harness.run(advance_main_on_ci_call=2)
    assert result.returncode != 0
    assert "canonical GitHub main" in result.stderr
    assert "does not equal approved SHA" in result.stderr
    assert not any(" --prod " in f" {call} " for call in deploy_harness.npx_calls)


def test_both_ci_queries_are_exactly_scoped(
    deploy_harness: DeployHarness,
) -> None:
    result = deploy_harness.run()
    assert result.returncode == 0, result.stderr
    ci_calls = [call for call in deploy_harness.gh_calls if call.startswith("run list ")]
    assert len(ci_calls) == 2
    expected_parts = [
        f"--repo {CANONICAL_REPOSITORY}",
        "--branch main",
        "--workflow build-check.yml",
        f"--commit {deploy_harness.sha}",
        "--event push",
    ]
    for call in ci_calls:
        for expected in expected_parts:
            assert expected in call
    api_calls = [call for call in deploy_harness.gh_calls if call.startswith("api ")]
    expected_api_call = (
        "api --hostname github.com "
        "repos/pjfront/richmond-common/git/ref/heads/main --jq .object.sha"
    )
    assert api_calls == [expected_api_call] * 3
    assert len(deploy_harness.gh_calls) == 5


def test_deploys_approved_git_archive_not_mutable_checkout(
    deploy_harness: DeployHarness,
) -> None:
    _write_lf(deploy_harness.repo / ".env.production", "SECRET=never-upload\n")
    _write_lf(deploy_harness.repo / "ignored-local.txt", "ignored bytes\n")
    _write_lf(
        deploy_harness.repo / ".vercel" / "project.json",
        '{"projectId":"wrong-local-project"}\n',
    )
    _git(deploy_harness.repo, "update-index", "--assume-unchanged", "web/fixture.txt")
    _write_lf(deploy_harness.repo / "web" / "fixture.txt", "mutable bytes\n")

    result = deploy_harness.run()

    assert result.returncode == 0, result.stderr
    snapshot = deploy_harness.artifact_snapshot
    assert snapshot["fixture"] == "verified deploy source"
    assert snapshot["cwd"] not in {
        str(deploy_harness.repo),
        deploy_harness.repo.as_posix(),
    }
    assert f"githubCommitSha={deploy_harness.sha}" in snapshot["args"]
    assert "githubCommitRef=main" in snapshot["args"]
    assert "githubDeployment=1" in snapshot["args"]


def test_git_replace_cannot_change_archived_commit_bytes(
    deploy_harness: DeployHarness,
) -> None:
    approved_sha = deploy_harness.sha
    _write_lf(deploy_harness.repo / "web" / "fixture.txt", "replacement bytes\n")
    replacement_sha = deploy_harness.commit("replacement tree")
    _git(deploy_harness.repo, "reset", "--hard", approved_sha)
    _git(deploy_harness.repo, "replace", approved_sha, replacement_sha)
    deploy_harness.sha = approved_sha

    result = deploy_harness.run()

    assert result.returncode == 0, result.stderr
    assert deploy_harness.artifact_snapshot["fixture"] == "verified deploy source"
    assert "GIT_NO_REPLACE_OBJECTS=1" in SOURCE_SCRIPT.read_text(encoding="utf-8")


def test_committed_oversized_artifact_never_reaches_vercel(
    deploy_harness: DeployHarness,
) -> None:
    generated = deploy_harness.repo / "web" / "generated"
    for index in range(2001):
        _write_lf(generated / f"file-{index:04d}.txt", "x\n")
    deploy_harness.commit("oversized archive")

    result = deploy_harness.run()

    assert result.returncode != 0
    assert "estimated file count" in result.stderr
    assert "exceeds 2000 cap" in result.stderr
    assert deploy_harness.npx_calls == []


def test_artifact_statically_rejects_symlinks() -> None:
    text = SOURCE_SCRIPT.read_text(encoding="utf-8")
    assert 'find "$DEPLOY_DIR" -type l -print -quit' in text
    assert "immutable artifact contains forbidden symlink" in text


def test_refuses_repository_local_archive_attributes_before_vercel(
    deploy_harness: DeployHarness,
) -> None:
    attributes_path = Path(
        _git(
            deploy_harness.repo,
            "rev-parse",
            "--path-format=absolute",
            "--git-path",
            "info/attributes",
        )
    )
    attributes_path.parent.mkdir(parents=True, exist_ok=True)
    attributes_path.write_text("web/fixture.txt export-ignore\n", encoding="utf-8")

    result = deploy_harness.run()
    assert result.returncode != 0
    assert "repository-local Git archive attributes are forbidden" in result.stderr
    assert "ACTION: remove .git/info/attributes" in result.stderr
    assert not any(" --prod " in f" {call} " for call in deploy_harness.npx_calls)


@pytest.mark.parametrize(
    ("key", "value", "message"),
    [
        ("VERCEL_ORG_ID", "team_wrong", "wrong Vercel account"),
        ("VERCEL_PROJECT_ID", "prj_wrong", "wrong Vercel project"),
    ],
)
def test_refuses_wrong_ambient_vercel_target(
    deploy_harness: DeployHarness, key: str, value: str, message: str
) -> None:
    result = deploy_harness.run(extra_env={key: value})
    assert result.returncode != 0
    assert message in result.stderr
    assert deploy_harness.gh_calls == []
    assert deploy_harness.npx_calls == []


def test_refuses_when_previous_ready_production_cannot_be_proven(
    deploy_harness: DeployHarness,
) -> None:
    result = deploy_harness.run(inspect_fail_on_call=1)
    assert result.returncode != 0
    assert "could not prove the current READY production" in result.stderr
    assert not any(" --prod " in f" {call} " for call in deploy_harness.npx_calls)


def test_deploy_failure_reports_proven_unchanged_prior_target(
    deploy_harness: DeployHarness,
) -> None:
    result = deploy_harness.run(deploy_exit=1)
    assert result.returncode != 0
    assert f"Previous production {PREVIOUS_DEPLOYMENT_ID} remains active" in result.stderr
    assert "ACTION: Do not roll back" in result.stderr
    assert not any(" rollback " in f" {call} " for call in deploy_harness.npx_calls)


def test_invalid_deploy_url_fails_attestation_with_action(
    deploy_harness: DeployHarness,
) -> None:
    result = deploy_harness.run(deploy_url="not-a-production-url")
    assert result.returncode != 0
    assert "invalid or unbounded deployment URL" in result.stderr
    assert f"Captured previous production: {PREVIOUS_DEPLOYMENT_ID}" in result.stderr
    assert "ACTION: Open https://richmondcommons.org" in result.stderr


def test_wrong_deployment_metadata_fails_attestation(
    deploy_harness: DeployHarness,
) -> None:
    wrong = (
        '{"uid":"'
        + NEW_DEPLOYMENT_ID
        + '","projectId":"'
        + VERCEL_PROJECT_ID
        + '","url":"rtp-exact-sha-test.vercel.app",'
        + '"target":"production","readyState":"READY","meta":'
        + '{"githubCommitSha":"'
        + ("1" * 40)
        + '","githubCommitRef":"main","githubDeployment":"1"}}'
    )
    result = deploy_harness.run(deployment_json=wrong)
    assert result.returncode != 0
    assert "not READY production with approved SHA/ref metadata" in result.stderr
    assert f"APPROVE PRODUCTION ROLLBACK: {PREVIOUS_DEPLOYMENT_ID}" in result.stderr


def test_deployment_api_lookup_failure_fails_attestation(
    deploy_harness: DeployHarness,
) -> None:
    result = deploy_harness.run(vercel_api_fail_on_call=2)
    assert result.returncode != 0
    assert "not READY production with approved SHA/ref metadata" in result.stderr
    assert f"APPROVE PRODUCTION ROLLBACK: {PREVIOUS_DEPLOYMENT_ID}" in result.stderr


def test_wrong_deployment_project_fails_attestation(
    deploy_harness: DeployHarness,
) -> None:
    wrong = (
        '{"uid":"'
        + NEW_DEPLOYMENT_ID
        + '","projectId":"prj_wrong","url":"rtp-exact-sha-test.vercel.app",'
        + '"target":"production","readyState":"READY","meta":'
        + '{"githubCommitSha":"'
        + deploy_harness.sha
        + '","githubCommitRef":"main","githubDeployment":"1"}}'
    )
    result = deploy_harness.run(deployment_json=wrong)
    assert result.returncode != 0
    assert "not READY production with approved SHA/ref metadata" in result.stderr


def test_alias_must_resolve_to_new_attested_deployment(
    deploy_harness: DeployHarness,
) -> None:
    alias_json = (
        '{"id":"dpl_OtherProduction999","target":"production",'
        '"readyState":"READY"}'
    )
    alias_api_json = (
        '{"uid":"dpl_OtherProduction999","projectId":"'
        + VERCEL_PROJECT_ID
        + '","url":"other-production.vercel.app","target":"production",'
        + '"readyState":"READY"}'
    )
    result = deploy_harness.run(
        alias_json=alias_json, alias_api_json=alias_api_json
    )
    assert result.returncode != 0
    assert "alias does not resolve to deployed target" in result.stderr
    assert f"APPROVE PRODUCTION ROLLBACK: {PREVIOUS_DEPLOYMENT_ID}" in result.stderr


def test_exact_happy_path_uses_pinned_cli_and_attests_production(
    deploy_harness: DeployHarness,
) -> None:
    result = deploy_harness.run()

    assert result.returncode == 0, result.stderr
    assert result.stdout.count("Build Check run 4242 is green") == 2
    assert result.stdout.count("Querying canonical GitHub main") == 3
    assert f"Production attested: {NEW_DEPLOYMENT_ID}" in result.stdout
    assert "ACTION: Open https://richmondcommons.org" in result.stdout
    assert f"APPROVE PRODUCTION ROLLBACK: {PREVIOUS_DEPLOYMENT_ID}" in result.stdout
    assert len(deploy_harness.npx_calls) == 7
    assert deploy_harness.npx_calls[0] == (
        "--registry=https://registry.npmjs.org/ --offline=false "
        "--prefer-online --yes vercel@59.1.4 --version"
    )
    assert all(
        call.startswith(
            "--registry=https://registry.npmjs.org/ --offline --yes "
            "vercel@59.1.4 --api https://api.vercel.com "
            "--scope phillips-projects-1f180556 "
        )
        for call in deploy_harness.npx_calls[1:]
    )
    deploy_calls = [
        call for call in deploy_harness.npx_calls if " --prod " in f" {call} "
    ]
    assert len(deploy_calls) == 1
    assert "--cwd " in deploy_calls[0]
    assert f"githubCommitSha={deploy_harness.sha}" in deploy_calls[0]
    assert "githubCommitRef=main" in deploy_calls[0]
    assert "githubDeployment=1" in deploy_calls[0]
    assert any(
        "api /v13/deployments/rtp-exact-sha-test.vercel.app?teamId="
        + VERCEL_ORG_ID
        in call
        for call in deploy_harness.npx_calls
    )
    assert not any(" rollback " in f" {call} " for call in deploy_harness.npx_calls)


@pytest.mark.skipif(os.name != "nt", reason="Windows launcher is platform-specific")
def test_windows_launcher_selects_git_bash_and_runs_exact_gate(
    deploy_harness: DeployHarness,
) -> None:
    result = deploy_harness.run(windows_launcher=True)
    assert result.returncode == 0, result.stderr
    assert f"Production attested: {NEW_DEPLOYMENT_ID}" in result.stdout
    assert len(deploy_harness.npx_calls) == 7


def test_windows_launcher_is_pinned_and_propagates_exit_status() -> None:
    text = POWERSHELL_LAUNCHER.read_text(encoding="utf-8")
    assert "$gitBashPath = 'C:\\Program Files\\Git\\bin\\bash.exe'" in text
    assert "& $gitBashPath $deployScriptPath $ApprovedSha" in text
    assert "if ($LASTEXITCODE -ne 0)" in text
    assert "ACTION: Install Git for Windows" in text


def test_vercel_ignore_excludes_all_local_env_families() -> None:
    text = VERCEL_IGNORE.read_text(encoding="utf-8")
    assert "/.env*" in text
    assert "/web/.env*" in text
    assert "\nnode_modules/\n" in text
    assert "\n.next/\n" in text


def test_authoritative_approval_is_bound_to_exact_full_sha() -> None:
    text = JUDGMENT_CATALOG.read_text(encoding="utf-8")
    assert "full 40-character commit SHA" in text
    assert "complete list of included changes" in text
    assert "new decision packet and approval" in text
    assert (
        "powershell.exe -NoProfile -ExecutionPolicy Bypass -File "
        ".\\web\\scripts\\deploy-prod.ps1 <full-sha>" in text
    )
    assert "bare `bash` resolves to unusable WSL" in text


def test_operator_guidance_documents_residual_concurrency_and_rollback_action() -> None:
    text = WEB_GUIDANCE.read_text(encoding="utf-8")
    assert "full 40-character" in text
    assert (
        "powershell.exe -NoProfile -ExecutionPolicy Bypass -File "
        ".\\web\\scripts\\deploy-prod.ps1" in text
    )
    assert "C:\\Program Files\\Git\\bin\\bash.exe" in text
    assert "main advances" in text
    assert "automatic Vercel Git deployment" in text
    assert "APPROVE PRODUCTION ROLLBACK" in text
    assert "rollback compatibility packet" in text
    assert "never reverses Supabase migrations or data" in text
    assert "migration 136" in text
    assert "migration 134 HARD NO-GO" in text
    assert "ordinary content sync/ingestion is excluded" in text
    assert "live Supabase migration ledger and schema metadata read-only" in text
    assert "never scans, queries, or corrects production table rows" in text
    assert "rollback-eligible on the current Vercel plan" in text
    assert "an upgrade is not a rollback remedy" in text
    assert "re-checks current production and eligibility immediately" in text
    assert "invalidates approval and requires a new packet" in text
    assert "must not assume the approved SHA went live" in text
    assert "actual current source cannot be proven" in text


def test_alert_action_requires_database_compatibility_before_rollback() -> None:
    text = SOURCE_SCRIPT.read_text(encoding="utf-8")
    assert "ACTION: Open https://richmondcommons.org" in text
    assert "LLM MESSAGE: For Richmond Commons" in text
    assert "never reverses Supabase migrations or data" in text
    assert "Preserve live migration 136" in text
    assert "migration 134 is HARD NO-GO" in text
    assert "do not propose production-data correction" in text
    assert "Resolve the prior deployment to its exact full Git SHA" in text
    assert "Resolve the actual current production deployment ID" in text
    assert "do not assume current production is approved SHA" in text
    assert "Exclude ordinary content sync/ingestion" in text
    assert "Verify the live Supabase migration ledger" in text
    assert "never scan, query, or correct production table rows" in text
    assert "actual current source, exact prior source" in text
    assert "UNSAFE/UNKNOWN; do not approve or execute" in text
    assert "NOT AUTHORIZED — DO NOT RUN" in text
    assert "If both URLs are healthy, do not roll back or retry" in text
    assert "still the immediately previous target" in text
    assert "do not recommend a Vercel plan upgrade" in text
    assert "re-check current production and eligibility again immediately" in text
    assert "intervening target or control-plane change invalidates" in text
    assert "must use the already prepared Vercel CLI strictly offline" in text
    assert "If its cache is missing, prefetch version" in text
    assert 'VERCEL_API_ORIGIN="https://api.vercel.com"' in text
    assert 'NPM_REGISTRY_ORIGIN="https://registry.npmjs.org/"' in text
    assert '--api "$VERCEL_API_ORIGIN"' in text
    assert '--scope "$EXPECTED_VERCEL_SCOPE"' in text
    assert "--offline --yes vercel@%s" in text
    assert "export VERCEL_CLI_USE_NATIVE_BINARY=0" in text
    assert "GIT_ATTR_NOSYSTEM=1 GIT_CONFIG_NOSYSTEM=1" in text
    assert "GIT_CONFIG_GLOBAL=/dev/null git" in text
    assert "repository-local Git archive attributes are forbidden" in text
    assert "-c core.attributesFile=/dev/null -c tar.umask=0000" in text


def test_build_check_runs_on_every_main_push_but_prs_remain_path_filtered() -> None:
    text = BUILD_CHECK_WORKFLOW.read_text(encoding="utf-8")
    pull_request_block = text.split("  pull_request:", 1)[1].split(
        "  push:", 1
    )[0]
    push_block = text.split("  push:", 1)[1].split("\n\n", 1)[0]
    assert "branches: [main]" in pull_request_block
    assert "paths:" in pull_request_block
    assert "branches: [main]" in push_block
    assert "paths:" not in push_block
