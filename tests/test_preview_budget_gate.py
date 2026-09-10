"""New paid Previews fail closed without disabling retained-state cleanup."""

import os
from pathlib import Path
import shutil
import subprocess

import pytest
import yaml


ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"
BUDGET_VARIABLE = "RICHMOND_ALLOW_PAID_PREVIEW_BOOTSTRAP"


def _workflow(name: str = "supabase-preview.yml") -> dict:
    return yaml.load((WORKFLOWS / name).read_text(encoding="utf-8"), Loader=yaml.BaseLoader)


def _gate() -> dict:
    return next(step for step in _workflow()["jobs"]["lifecycle"]["steps"]
                if step.get("id") == "preview_budget")


def test_paid_bootstrap_gate_precedes_all_provider_access_and_defaults_off():
    job = _workflow()["jobs"]["lifecycle"]
    steps = job["steps"]
    gate = _gate()
    assert steps[0] == gate
    assert gate["if"] == "env.PREVIEW_OPERATION == 'bootstrap'"
    assert gate["env"] == {
        "ALLOW_PAID_PREVIEW_BOOTSTRAP": "${{ vars.RICHMOND_ALLOW_PAID_PREVIEW_BOOTSTRAP || 'false' }}",
    }
    assert "continue-on-error" not in gate
    assert "secrets." not in str(gate)
    assert "client_payload" not in str(gate)
    assert BUDGET_VARIABLE not in job.get("if", "")
    bootstrap = next(step for step in steps if step.get("id") == "bootstrap")
    assert bootstrap["if"] == (
        "env.PREVIEW_OPERATION == 'bootstrap' && steps.preview_budget.outcome == 'success'"
    )
    assert "continue-on-error" not in bootstrap


@pytest.mark.parametrize("value,allowed", [
    (None, False), ("", False), ("false", False), ("False", False),
    ("TRUE", False), ("1", False), ("yes", False), ("true ", False),
    (" true", False), ("true", True),
])
def test_actual_budget_script_accepts_only_explicit_true(value, allowed):
    # Execute the workflow's actual shell body; never call a provider or controller.
    # Git Bash avoids Windows' unrelated WSL launcher when running locally.
    git_bash = Path(os.environ.get("ProgramFiles", "C:/Program Files")) / "Git/bin/bash.exe"
    bash = str(git_bash) if os.name == "nt" and git_bash.is_file() else shutil.which("bash")
    assert bash, "A Bash runtime is required for the hosted-runner budget contract"
    env = os.environ.copy()
    env.pop("ALLOW_PAID_PREVIEW_BOOTSTRAP", None)
    # An absent repository variable resolves to the workflow's literal false default.
    env["ALLOW_PAID_PREVIEW_BOOTSTRAP"] = "false" if value is None else value
    result = subprocess.run(
        [bash, "--noprofile", "--norc", "-c", _gate()["run"]],
        env=env, capture_output=True, text=True, timeout=10,
    )
    assert (result.returncode == 0) is allowed, result.stderr
    if not allowed:
        assert "No branch was created" in result.stdout
        assert "requires an explicit new user budget" in result.stdout


def test_budget_switch_does_not_gate_verification_or_any_cleanup_layer():
    job = _workflow()["jobs"]["lifecycle"]
    steps = job["steps"]
    for step in steps:
        if step.get("id") in {"preview_budget", "bootstrap"}:
            continue
        assert "preview_budget" not in step.get("if", "")
        assert BUDGET_VARIABLE not in str(step)
    verify = next(step for step in steps if step.get("id") == "retained")
    assert "env.PREVIEW_OPERATION == 'verify-types'" in verify["if"]
    cleanups = [step for step in steps if "python src/supabase_preview.py cleanup" in step.get("run", "")]
    assert cleanups
    assert all("always()" in step["if"] or step["if"] == "env.PREVIEW_OPERATION == 'cleanup'"
               for step in cleanups)
    assert _workflow()["on"]["pull_request_target"]["types"] == ["closed"]
    for name in ("supabase-preview-expiry.yml", "supabase-preview-watchdog.yml"):
        text = (WORKFLOWS / name).read_text(encoding="utf-8")
        assert BUDGET_VARIABLE not in text
        assert "preview_budget" not in text
    assert "schedule" in _workflow("supabase-preview-expiry.yml")["on"]
    assert "workflow_run" in _workflow("supabase-preview-watchdog.yml")["on"]
