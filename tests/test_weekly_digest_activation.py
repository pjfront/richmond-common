"""Execute the real workflow shell with jq and a network-free curl fixture."""

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys

import pytest
import yaml


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = yaml.load(
    (ROOT / ".github/workflows/subscriber-weekly-digest.yml").read_text(encoding="utf-8"),
    Loader=yaml.BaseLoader,
)
TRUSTED = {
    "repository": "pjfront/richmond-common",
    "ref": "refs/heads/main",
    "event_name": "schedule",
    "event.schedule": "30 16 * * 1",
    "event.action": "",
    "actor": "scheduler-editor",
    "repository_owner": "pjfront",
    "run_attempt": 1,
}
CAPABILITY = {
    "capability": "subscriber-weekly-digest-v1",
    "canary_ready": True,
    "broadcast_ready": True,
}
COMPLETE = {
    "mode": "broadcast",
    "sent": 2,
    "already_sent": 1,
    "failed": 0,
    "deferred": 0,
    "manual_review": 0,
    "total_subscribers": 3,
    "fully_delivered": True,
}
PERIOD = {"start": "2026-08-31", "end": "2026-09-06", "contentKey": "week:2026-08-31"}
CANARY = {"mode": "canary", "sent": 1, "provider_confirmed": True}


def _condition_matches(job: str, context: dict) -> bool:
    """Interpret only the actual workflow's conjunction of equality clauses."""
    for clause in WORKFLOW["jobs"][job]["if"].split("&&"):
        match = re.fullmatch(r"\s*github\.([a-z_.]+) == (?:'([^']*)'|github\.([a-z_.]+)|(\d+))\s*", clause)
        assert match, f"Review a changed authorization expression: {clause}"
        left, string, other, number = match.groups()
        right = context[other] if other else int(number) if number else string
        if context[left] != right:
            return False
    return True


def test_schedule_authorization_does_not_depend_on_the_last_cron_editor() -> None:
    assert WORKFLOW["on"]["schedule"] == [{"cron": "30 16 * * 1"}]
    assert WORKFLOW["on"]["repository_dispatch"] == {"types": ["subscriber-digest-canary"]}
    assert set(WORKFLOW["on"]) == {"schedule", "repository_dispatch"}
    assert _condition_matches("broadcast", TRUSTED)
    assert not _condition_matches("deliver", TRUSTED)


@pytest.mark.parametrize("change", [
    {"repository": "fork/richmond-common"},
    {"ref": "refs/heads/feature"},
    {"event_name": "workflow_dispatch"},
    {"event_name": "repository_dispatch", "event.action": "subscriber-digest-canary", "actor": "pjfront"},
    {"event.schedule": "31 16 * * 1"},
    {"run_attempt": 2},
])
def test_broadcast_rejects_forks_other_refs_manual_events_wrong_cron_and_reruns(change) -> None:
    assert not _condition_matches("broadcast", {**TRUSTED, **change})


def test_manual_owner_event_can_only_reach_canary() -> None:
    event = {**TRUSTED, "event_name": "repository_dispatch", "event.action": "subscriber-digest-canary", "actor": "pjfront"}
    assert _condition_matches("deliver", event)
    assert not _condition_matches("broadcast", event)
    assert not _condition_matches("deliver", {**event, "actor": "collaborator"})
    assert not _condition_matches("deliver", {**event, "repository": "fork/richmond-common"})


def test_shared_concurrency_and_bounded_single_requests() -> None:
    assert WORKFLOW["concurrency"] == {"group": "weekly-subscriber-digest", "cancel-in-progress": "false"}
    assert WORKFLOW["permissions"] == {"contents": "read"}
    for name, job in WORKFLOW["jobs"].items():
        assert job["timeout-minutes"] == "3"
        text = "\n".join(step["run"] for step in job["steps"])
        assert text.count("HTTP_CODE=$(curl ") == 2
        assert text.count("--data-binary") == 1
        assert '--data-binary \'{"mode":"' + ("canary" if name == "deliver" else "broadcast") + '"}\'' in text
        assert text.count("--max-filesize 65536") == 2
        assert text.count("--connect-timeout 10") == 2
        assert "--retry" not in text and "--location" not in text
        assert "curl -L" not in text and "set -x" not in text
        assert text.count('"https://richmondcommons.org/api/email/send-digest"') == 2


@pytest.fixture(scope="module")
def shell_tools() -> tuple[str, str]:
    bash = Path("C:/Program Files/Git/bin/bash.exe") if sys.platform == "win32" else shutil.which("bash")
    jq = os.environ.get("DIGEST_TEST_JQ") or shutil.which("jq")
    if not bash or not Path(bash).exists() or not jq:
        pytest.skip("Requires Bash and jq; Ubuntu CI supplies both, Windows can set DIGEST_TEST_JQ")
    return str(bash), str(Path(jq).resolve()).replace("\\", "/")


# The actual workflow jq programs run unchanged. Only curl is replaced; no
# request can reach an email provider or the production site in these tests.
MOCK_SHELL = r'''
jq() { "$DIGEST_TEST_JQ" "$@"; }
curl() {
  local method=GET output= body= url= arg
  while [ "$#" -gt 0 ]; do
    arg="$1"; shift
    case "$arg" in
      -X) method="$1"; shift ;;
      --output) output="$1"; shift ;;
      --data-binary) body="$1"; shift ;;
      -H|--connect-timeout|--max-time|--max-filesize|--write-out) shift ;;
      https://*) url="$arg" ;;
    esac
  done
  printf '%s|%s|%s\n' "$method" "$body" "$url" >> "$MOCK_CALLS"
  if [ "$method" = GET ]; then
    printf '%s' "$MOCK_GET_RESPONSE" > "$output"
    printf '%s' "$MOCK_GET_HTTP"
    return "$MOCK_GET_EXIT"
  fi
  printf '%s' "$MOCK_POST_RESPONSE" > "$output"
  printf '%s' "$MOCK_POST_HTTP"
  return "$MOCK_POST_EXIT"
}
'''


def _run_job(tmp_path: Path, shell_tools: tuple[str, str], job: str = "broadcast", capability: dict | None = None, response: dict | None = None, **overrides: str) -> tuple[bool, list[str]]:
    bash, jq = shell_tools
    calls = tmp_path / "calls.txt"
    env = {
        **os.environ,
        "DIGEST_TEST_JQ": jq,
        "RUNNER_TEMP": tmp_path.as_posix(),
        "MOCK_CALLS": calls.as_posix(),
        "API_SECRET": "fake-secret-must-never-be-logged",
        "CLIENT_PAYLOAD": "{}",
        "MOCK_GET_RESPONSE": json.dumps(CAPABILITY if capability is None else capability),
        "MOCK_GET_HTTP": "200",
        "MOCK_GET_EXIT": "0",
        "MOCK_POST_RESPONSE": json.dumps(COMPLETE if response is None else response),
        "MOCK_POST_HTTP": "200",
        "MOCK_POST_EXIT": "0",
        **overrides,
    }
    script = MOCK_SHELL + "\n".join(step["run"] for step in WORKFLOW["jobs"][job]["steps"])
    result = subprocess.run([bash, "-c", script], env=env, capture_output=True, text=True, timeout=15)
    if env["API_SECRET"]:
        assert env["API_SECRET"] not in result.stdout + result.stderr
    assert "person@example.test" not in result.stdout + result.stderr
    recorded = calls.read_text().splitlines() if calls.exists() else []
    if result.returncode:
        assert "::error::ACTION:" in result.stdout
    return result.returncode == 0, recorded


@pytest.mark.parametrize("response", [
    COMPLETE,
    {**COMPLETE, "sent": 0, "already_sent": 3},
    {**COMPLETE, "sent": 0, "already_sent": 0, "total_subscribers": 0},
    {"mode": "broadcast", "sent": 0, "period": PERIOD, "reason": "no active subscribers"},
    {"mode": "broadcast", "sent": 0, "period": PERIOD, "reason": "no recaps or reviewed updates in completed week"},
])
def test_real_workflow_accepts_complete_deduplicated_and_empty_results(tmp_path, shell_tools, response) -> None:
    success, calls = _run_job(tmp_path, shell_tools, response=response)
    assert success
    assert calls == [
        "GET||https://richmondcommons.org/api/email/send-digest",
        'POST|{"mode":"broadcast"}|https://richmondcommons.org/api/email/send-digest',
    ]


@pytest.mark.parametrize("response", [
    {**COMPLETE, "fully_delivered": False},
    {**COMPLETE, "failed": 1},
    {**COMPLETE, "deferred": 1},
    {**COMPLETE, "manual_review": 1},
    {**COMPLETE, "sent": "2"},
    {**COMPLETE, "sent": -1, "already_sent": 4},
    {**COMPLETE, "sent": 2.5, "already_sent": 0.5},
    {**COMPLETE, "sent": 500, "already_sent": 1, "total_subscribers": 501},
    {**COMPLETE, "total_subscribers": 2},
    {**COMPLETE, "mode": "canary"},
    {**COMPLETE, "error": "contradictory failure"},
    {"mode": "broadcast", "sent": 0, "period": PERIOD, "reason": "source unavailable"},
    {"mode": "broadcast", "sent": 1, "period": PERIOD, "reason": "no active subscribers"},
    {"mode": "broadcast", "sent": 0, "period": PERIOD, "reason": "no active subscribers", "failed": 1},
    {}, [], None,
])
def test_real_workflow_rejects_partial_contradictory_and_malformed_results(tmp_path, shell_tools, response) -> None:
    success, calls = _run_job(tmp_path, shell_tools, MOCK_POST_RESPONSE=json.dumps(response))
    assert not success
    assert len(calls) == 2  # One GET, one POST, and no transport retry.


@pytest.mark.parametrize("overrides", [
    {"MOCK_POST_EXIT": "28"},
    {"MOCK_POST_HTTP": "503"},
    {"MOCK_POST_HTTP": "302"},
    {"MOCK_POST_RESPONSE": 'invalid-json person@example.test fake-secret-must-never-be-logged'},
])
def test_real_workflow_fails_uncertain_or_unreadable_post_without_resending(tmp_path, shell_tools, overrides) -> None:
    success, calls = _run_job(tmp_path, shell_tools, **overrides)
    assert not success
    assert len(calls) == 2


@pytest.mark.parametrize("overrides", [
    {"API_SECRET": ""},
    {"MOCK_GET_EXIT": "28"},
    {"MOCK_GET_HTTP": "401"},
    {"MOCK_GET_RESPONSE": json.dumps({**CAPABILITY, "broadcast_ready": False})},
    {"MOCK_GET_RESPONSE": json.dumps({**CAPABILITY, "broadcast_ready": "true"})},
    {"MOCK_GET_RESPONSE": json.dumps({**CAPABILITY, "capability": "other-api"})},
    {"MOCK_GET_RESPONSE": 'invalid-json person@example.test fake-secret-must-never-be-logged'},
])
def test_real_workflow_never_posts_when_capability_cannot_be_proven(tmp_path, shell_tools, overrides) -> None:
    success, calls = _run_job(tmp_path, shell_tools, **overrides)
    assert not success
    assert all(call.startswith("GET|") for call in calls)


@pytest.mark.parametrize("broadcast_ready", [False, True])
def test_canary_stays_available_before_and_after_activation(tmp_path, shell_tools, broadcast_ready) -> None:
    success, calls = _run_job(tmp_path, shell_tools, job="deliver", capability={**CAPABILITY, "broadcast_ready": broadcast_ready}, response=CANARY)
    assert success
    assert len(calls) == 2
    assert calls[-1] == 'POST|{"mode":"canary"}|https://richmondcommons.org/api/email/send-digest'


@pytest.mark.parametrize("payload", [{"mode": "broadcast"}, {"email": "person@example.test"}, [], None])
def test_canary_payload_cannot_choose_recipients_or_delivery_mode(tmp_path, shell_tools, payload) -> None:
    success, calls = _run_job(tmp_path, shell_tools, job="deliver", CLIENT_PAYLOAD=json.dumps(payload))
    assert not success and calls == []


@pytest.mark.parametrize("response", [
    {"mode": "canary", "sent": 0, "reason": "no recaps or reviewed updates in completed week"},
    {"mode": "canary", "sent": 1, "provider_confirmed": False},
    {"mode": "broadcast", "sent": 1, "provider_confirmed": True},
])
def test_canary_requires_one_confirmed_test_send(tmp_path, shell_tools, response) -> None:
    success, calls = _run_job(tmp_path, shell_tools, job="deliver", response=response)
    assert not success and len(calls) == 2
