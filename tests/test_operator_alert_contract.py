"""Structural enforcement for every Richmond-owned operator notification."""
from pathlib import Path
import hashlib
import re
import sys

import yaml


ROOT = Path(__file__).parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"


def _workflow_text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _workflow_name(path: Path, text: str) -> str:
    match = re.search(r"(?m)^name:\s*([^\r\n]+)", text)
    assert match, f"workflow {path.name} has no top-level name"
    return match.group(1).strip().strip("'\"")


def _main_push_workflow_names() -> set[str]:
    names = set()
    for path in WORKFLOWS.glob("*.yml"):
        text = path.read_text(encoding="utf-8-sig")
        workflow = yaml.load(text, Loader=yaml.BaseLoader)
        triggers = workflow.get("on") if isinstance(workflow, dict) else None
        push = triggers.get("push") if isinstance(triggers, dict) else None
        branches = push.get("branches") if isinstance(push, dict) else None
        if isinstance(branches, str):
            branches = [branches]
        if isinstance(branches, list) and "main" in branches:
            names.add(_workflow_name(path, text))
    return names


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
        assert "https://github.com/pjfront/richmond-common" in text
        assert "migration 134" in text


def test_all_production_scheduled_workflows_have_actionable_failure_wrapper():
    wrapper = _workflow_text("operational-failure-alert.yml")
    scheduled = set()
    for path in WORKFLOWS.glob("*.yml"):
        text = path.read_text(encoding="utf-8-sig")
        if not re.search(r"(?m)^  schedule:\s*$", text):
            continue
        scheduled.add(_workflow_name(path, text))
    assert scheduled
    for workflow_name in scheduled | {"S29 analytics checkpoint"}:
        assert f"- {workflow_name}" in wrapper


def test_all_main_push_workflows_have_wrapper_without_pr_noise():
    wrapper = _workflow_text("operational-failure-alert.yml")
    main_push = _main_push_workflow_names()
    assert main_push == {"Build Check", "TypeScript Check"}
    for workflow_name in main_push:
        assert f"- {workflow_name}" in wrapper
    assert "github.event.workflow_run.head_branch == 'main'" in wrapper
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in wrapper


def test_technical_handoffs_reference_tracked_project_rules():
    tracked_context = (
        "CLAUDE.md",
        ".claude/rules/judgment-boundaries.md",
    )
    for relative_path in tracked_context:
        assert (ROOT / relative_path).is_file(), relative_path

    alert_prompt = (ROOT / "src" / "prompts" / "operator_alert_handoff.txt").read_text(
        encoding="utf-8"
    )
    wrapper = _workflow_text("operational-failure-alert.yml")
    for text in (alert_prompt, wrapper):
        for relative_path in tracked_context:
            assert relative_path in text
        assert ".Codex/" not in text
        assert "AGENTS.md" not in text

    checkpoint = _workflow_text("s29-analytics-checkpoint.yml")
    assert "https://richmondcommons.org" in checkpoint
    assert "https://github.com/pjfront/richmond-common" in checkpoint


def test_operator_impacting_secret_and_quality_failures_do_not_exit_green():
    data_sync = _workflow_text("data-sync.yml")
    cloud = _workflow_text("cloud-pipeline.yml")
    assert "API_SECRET missing; skipping agenda preview send" not in data_sync
    assert data_sync.count("API_SECRET is missing; agenda preview delivery cannot run") == 2
    assert "data_quality_checks.py --create-decisions || true" not in cloud


def test_active_calendar_items_define_full_operator_contract():
    data = yaml.safe_load(
        (ROOT / "docs" / "scheduled_civic_events.yaml").read_text(encoding="utf-8")
    )
    active = [
        event for event in data["events"] if not event.get("completed_on")
    ] + data["recurring_events"]
    assert active
    for event in active:
        assert str(event.get("action") or "").strip(), event["id"]
        assert event.get("response_mode") in {"direct", "decision", "llm"}, event["id"]
        assert str(event.get("source_url") or "").startswith("https://"), event["id"]


def test_calendar_contains_verified_november_dates_and_small_annual_rules():
    data = yaml.safe_load(
        (ROOT / "docs" / "scheduled_civic_events.yaml").read_text(encoding="utf-8")
    )
    events = {event["id"]: event for event in data["events"]}
    assert str(events["nov-2026-form-460-first-preelection"]["due_date"]) == (
        "2026-09-24"
    )
    assert str(events["nov-2026-form-460-second-preelection"]["due_date"]) == (
        "2026-10-22"
    )
    assert str(events["nov-2026-form-460-third-preelection"]["due_date"]) == (
        "2026-10-29"
    )
    form_497 = events["nov-2026-form-497-monitoring-window"]
    assert str(form_497["window_start"]) == "2026-08-05"
    assert str(form_497["due_date"]) == "2026-11-03"
    assert form_497["lead_days"] == 90
    assert "24-hour" in form_497["action"]
    assert "48-hour" in form_497["action"]

    domain = events["richmondcommons-domain-renewal"]
    assert str(domain["due_date"]) == "2027-03-27"
    assert domain["lead_days"] == 45
    assert domain["response_mode"] == "direct"
    assert domain["source_url"] == (
        "https://rdap.publicinterestregistry.org/rdap/domain/"
        "richmondcommons.org"
    )
    assert "Domain Registration" in domain["action"]
    assert "auto-renew is On" in domain["action"]
    assert "never put payment details" in domain["action"]

    recurring = {event["id"]: event for event in data["recurring_events"]}
    assert recurring["form-700-annual-review"]["rule"] == {
        "frequency": "annual", "month": 4, "day": 1,
    }
    assert recurring["form-460-july-semiannual-review"]["rule"] == {
        "frequency": "annual", "month": 7, "day": 31,
        "start_year": 2027,
    }
    january = recurring["form-460-january-semiannual-review"]["rule"]
    assert (january["frequency"], january["month"], january["day"]) == (
        "annual", 1, 31,
    )
    assert str(january["overrides"]["2026"]) == "2026-02-02"
    assert str(january["overrides"]["2027"]) == "2027-02-01"


def test_manifest_and_current_docs_do_not_claim_retired_pat_or_n8n_paths():
    manifest_text = (ROOT / "docs" / "pipeline-manifest.yaml").read_text(
        encoding="utf-8"
    )
    manifest = yaml.safe_load(manifest_text)
    assert "n8n_workflows" not in manifest
    assert "n8n webhook" not in manifest_text
    cloud_trigger_types = {
        trigger["type"]
        for trigger in manifest["schedules"]["cloud-pipeline.yml"]["triggers"]
    }
    assert cloud_trigger_types == {"cron", "workflow_dispatch"}
    data_dispatch = next(
        trigger
        for trigger in manifest["schedules"]["data-sync.yml"]["triggers"]
        if trigger["type"] == "repository_dispatch"
    )
    assert "GITHUB_TOKEN" in data_dispatch["description"]

    calendar = (ROOT / "docs" / "scheduled_civic_events.yaml").read_text(
        encoding="utf-8"
    )
    assert "DISPATCH_TOKEN" not in calendar
    assert "dispatch-token-rotation" not in calendar
    assert "GitHub Actions + n8n" not in (ROOT / "CLAUDE.md").read_text(
        encoding="utf-8"
    )


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
    assert "PUBLIC_SITE_URL: https://richmondcommons.org/" in workflow
    assert (
        "PUBLIC_HEALTH_URL: https://richmondcommons.org/api/health" in workflow
    )
    assert "recovered_alert_ids.txt" in workflow


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


def test_push_incident_survives_commit_title_changes_and_deduplicates():
    wrapper = _workflow_text("operational-failure-alert.yml")

    # The exact stable push scope is used by initial lookup, audit fallback,
    # delivery-failure recovery, and the recovery job. It intentionally omits
    # displayTitle/head SHA, which change between failing A and successful B.
    assert wrapper.count('"$WORKFLOW_ID|push|main"') == 4
    assert 'INCIDENT_KEY="run-$RUN_ID"' in wrapper
    assert 'RECOVERY_KEY="run-$RUN_ID"' in wrapper
    assert wrapper.count('"$WORKFLOW_ID|$EVENT|$DISPLAY_TITLE"') == 4

    push_scope = re.findall(
        r'printf \'%s\' "(\$WORKFLOW_ID\|push\|main)"', wrapper
    )
    assert len(push_scope) == 4

    def push_marker(workflow_id: str, _display_title: str) -> str:
        scope = push_scope[0].replace("$WORKFLOW_ID", workflow_id)
        digest = hashlib.sha256(scope.encode("utf-8")).hexdigest()
        return f"<!-- richmond-workflow-alert-key:{digest} -->"

    open_incidents: set[str] = set()

    failure_a = push_marker("build-check-id", "Commit A failed")
    first_failure_sends = failure_a not in open_incidents
    open_incidents.add(failure_a)

    repeated_failure = push_marker("build-check-id", "Commit A retry failed")
    repeated_failure_sends = repeated_failure not in open_incidents

    recovery_b = push_marker("build-check-id", "Commit B succeeded")
    open_incidents.discard(recovery_b)

    assert first_failure_sends is True
    assert repeated_failure_sends is False
    assert open_incidents == set()
    assert 'echo "send_email=false"' in wrapper
    assert "gh issue close" in wrapper

    push_recovery = wrapper.split(
        '# Push display titles usually include the commit message', 1
    )[1].split("else", 1)[0]
    assert "--event push --branch main --limit 1" in push_recovery
    assert "displayTitle" not in push_recovery
    assert '.[0].conclusion // ""' in push_recovery
    assert 'LATEST_CONCLUSION" != "success"' in push_recovery


def test_main_push_detection_accepts_multiline_branch_yaml(tmp_path, monkeypatch):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "multiline.yml").write_text(
        "name: Multiline Main\non:\n  push:\n    branches:\n      - main\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "WORKFLOWS", workflows)

    assert _main_push_workflow_names() == {"Multiline Main"}


def test_external_monitor_playbook_has_actionable_names_and_handoffs():
    playbook = (ROOT / "docs" / "operator-alert-playbook.md").read_text(
        encoding="utf-8"
    )
    assert "ACTION: Monitoring needs attention" in playbook
    assert "ACTION: Site unavailable" in playbook
    assert "https://healthchecks.io/checks/" in playbook
    assert "settings/secrets/actions" in playbook
    assert "HEALTHCHECKS_PING_URL" in playbook
    assert "bounded daily probe" in playbook
    assert "nearly 24 hours" in playbook
    assert "Inactive Account Notification" in playbook
    assert "github.com/settings/notifications" in playbook
    assert playbook.count("```text") >= 3
