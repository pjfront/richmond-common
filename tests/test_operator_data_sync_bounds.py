"""Executable guards for the narrow operator Data Sync payload."""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


ROOT = Path(__file__).parent.parent
WORKFLOW = ROOT / ".github" / "workflows" / "data-sync.yml"


def _resolver_script() -> str:
    workflow = yaml.load(WORKFLOW.read_text(encoding="utf-8"), Loader=yaml.BaseLoader)
    steps = workflow["jobs"]["sync"]["steps"]
    return next(step["run"] for step in steps if step.get("name") == "Resolve inputs")


def _bash() -> str | None:
    if os.name == "nt":
        candidate = Path("C:/Program Files/Git/bin/bash.exe")
        return str(candidate) if candidate.is_file() else None
    return shutil.which("bash")


def _run_operator_payload(tmp_path: Path, payload: dict) -> subprocess.CompletedProcess[str]:
    bash = _bash()
    if not bash or shutil.which("jq") is None:
        pytest.skip("executable workflow contract requires bash and jq")

    def scalar(name: str, default: str = "") -> str:
        value = payload.get(name, default)
        if value is None or value is False:
            return ""
        if value is True:
            return "true"
        return str(value)

    output = tmp_path / "github-output.txt"
    env = os.environ.copy()
    env.update(
        {
            "CLIENT_PAYLOAD": json.dumps(payload, separators=(",", ":")),
            "INPUT_SOURCE": scalar("source"),
            "INPUT_SYNC_TYPE": scalar("sync_type", "incremental"),
            "INPUT_LIMIT": scalar("limit"),
            "INPUT_ENRICH": scalar("enrich"),
            "INPUT_CHANGE_ID": scalar("change_id"),
            "INPUT_DISPATCH_GENERATION": scalar("dispatch_generation"),
            "EVENT_ACTION": "operator-sync-data",
            "GITHUB_OUTPUT": str(output),
        }
    )
    return subprocess.run(
        [bash],
        input=_resolver_script(),
        text=True,
        capture_output=True,
        cwd=ROOT,
        env=env,
        check=False,
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"source": "minutes_extraction"},
        {"source": "refresh_stale_minutes"},
        {"source": "meeting_summaries"},
        {"source": "written_comments"},
        {"source": "escribemeetings", "enrich": True},
        {"source": "escribemeetings", "unexpected": "ignored-before"},
    ],
)
def test_operator_payload_rejects_unbounded_shapes(tmp_path: Path, payload: dict):
    result = _run_operator_payload(tmp_path, payload)

    assert result.returncode != 0, result.stdout + result.stderr
    assert "::error::ACTION:" in result.stdout


@pytest.mark.parametrize(
    "source",
    [
        "netfile",
        "calaccess",
        "nextrequest",
        "archive_center",
        "form700",
        "form803_behested",
        "lobbyist_registrations",
        "propublica",
        "socrata_payroll",
        "socrata_expenditures",
        "socrata_permits",
        "socrata_licenses",
        "socrata_code_cases",
        "socrata_service_requests",
        "socrata_projects",
    ],
)
def test_operator_payload_rejects_bulk_sources(tmp_path: Path, source: str):
    result = _run_operator_payload(tmp_path, {"source": source})

    assert result.returncode != 0, result.stdout + result.stderr
    assert "::error::ACTION:" in result.stdout


@pytest.mark.parametrize(
    "payload",
    [
        {"source": "escribemeetings"},
        {"source": "escribemeetings_minutes", "enrich": False},
        {"source": "minutes_extraction", "limit": "1"},
        {"source": "refresh_stale_minutes", "limit": 100},
    ],
)
def test_operator_payload_accepts_only_bounded_shapes(tmp_path: Path, payload: dict):
    result = _run_operator_payload(tmp_path, payload)

    assert result.returncode == 0, result.stdout + result.stderr
    assert "Trigger: operator" in result.stdout
