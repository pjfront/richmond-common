"""Structural enforcement for every Richmond-owned operator notification."""
from pathlib import Path
import re

import yaml


ROOT = Path(__file__).parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow_text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_every_direct_operator_email_path_is_contract_covered():
    direct_paths = {
        path.name
        for path in WORKFLOWS.glob("*.yml")
        if "OPERATOR_EMAIL" in path.read_text(encoding="utf-8")
        and "api.resend.com/emails" in path.read_text(encoding="utf-8")
    }
    assert direct_paths == {
        "alerting.yml",
        "operational-failure-alert.yml",
        "s29-analytics-checkpoint.yml",
    }

    # alerting.yml renders the tested src/alerting.py body. Literal workflow
    # notices must carry their own action and technical handoff.
    for name in ("operational-failure-alert.yml", "s29-analytics-checkpoint.yml"):
        text = _workflow_text(name)
        assert "ACTION:" in text
        assert "COPY/PASTE" in text or "copy this message" in text
        assert "richmondcommons.org" in text
        assert "migration 134" in text


def test_all_production_scheduled_workflows_have_actionable_failure_wrapper():
    wrapper = _workflow_text("operational-failure-alert.yml")
    scheduled = set()
    for path in WORKFLOWS.glob("*.yml"):
        text = path.read_text(encoding="utf-8-sig")
        if not re.search(r"(?m)^  schedule:\s*$", text):
            continue
        name = re.search(r"(?m)^name:\s*([^\r\n]+)", text)
        assert name, f"scheduled workflow {path.name} has no top-level name"
        scheduled.add(name.group(1).strip().strip("'\""))
    assert scheduled
    for workflow_name in scheduled | {"S29 analytics checkpoint"}:
        assert f"- {workflow_name}" in wrapper


def test_operator_impacting_secret_and_quality_failures_do_not_exit_green():
    data_sync = _workflow_text("data-sync.yml")
    cloud = _workflow_text("cloud-pipeline.yml")
    assert "API_SECRET missing; skipping agenda preview send" not in data_sync
    assert data_sync.count("API_SECRET is missing; agenda preview delivery cannot run") == 2
    assert "data_quality_checks.py --create-decisions || true" not in cloud


def test_active_calendar_items_define_action_response_mode():
    data = yaml.safe_load(
        (ROOT / "docs" / "scheduled_civic_events.yaml").read_text(encoding="utf-8")
    )
    active = [event for event in data["events"] if not event.get("completed_on")]
    assert active
    for event in active:
        assert str(event.get("action") or "").strip(), event["id"]
        assert event.get("response_mode") in {"direct", "decision", "llm"}, event["id"]


def test_workflow_yaml_is_parseable():
    for name in (
        "alerting.yml",
        "data-sync.yml",
        "cloud-pipeline.yml",
        "operational-failure-alert.yml",
        "s29-analytics-checkpoint.yml",
    ):
        assert yaml.safe_load(_workflow_text(name))


def test_primary_alert_email_precedes_best_effort_issue_mutations():
    workflow = _workflow_text("alerting.yml")
    assert workflow.index("name: Send alert email") < workflow.index(
        "name: File alert issues"
    )
    assert "--open-alert-issues-file" in workflow
    assert "richmond-alert-key:$ID" in workflow
    assert '--title "$TITLE"' in workflow
    assert ".title | contains($id)" not in workflow


def test_failure_wrapper_has_scoped_recovery_and_delivery_fallbacks():
    wrapper = _workflow_text("operational-failure-alert.yml")
    assert "actions: read" in wrapper
    assert "--branch main" in wrapper
    assert "display_title" in wrapper
    assert 'INCIDENT_KEY="run-$RUN_ID"' in wrapper
    assert "delivery-failed-$RUN_ID" in wrapper
    assert "ACTION TEST" in wrapper
    assert "workflow_dispatch:" in wrapper
    assert "HEALTHCHECKS_PING_URL" in wrapper
    assert "/fail" in wrapper
    assert "steps.notice.outcome == 'failure'" in wrapper
    assert "concurrency:" not in wrapper

    assert "run-name:" in _workflow_text("data-sync.yml")
    assert "github.event.client_payload.source" in _workflow_text("data-sync.yml")
    assert "run-name:" in _workflow_text("s29-analytics-checkpoint.yml")


def test_external_monitor_playbook_has_actionable_names_and_handoffs():
    playbook = (ROOT / "docs" / "operator-alert-playbook.md").read_text(
        encoding="utf-8"
    )
    assert "ACTION: Monitoring needs attention" in playbook
    assert "ACTION: Site unavailable" in playbook
    assert "https://healthchecks.io/checks/" in playbook
    assert "settings/secrets/actions" in playbook
    assert "HEALTHCHECKS_PING_URL" in playbook
    assert "github.com/settings/notifications" in playbook
    assert playbook.count("```text") >= 3
