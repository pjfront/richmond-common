"""Structural enforcement for every Richmond-owned operator notification."""
from pathlib import Path
import hashlib
import re
import sys

import yaml


ROOT = Path(__file__).parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"

# Manual/event-driven workflows need an explicit failure-notification policy.
# Supabase Preview is wrapped only because typed repository dispatch executes
# default-branch code and the wrapper separately admits trusted PR-close cleanup.
OPERATOR_CRITICAL_EVENT_WORKFLOW_POLICY = {
    "Operational failure alerts": "self-monitoring",
    "S29 analytics checkpoint": "wrapped",
    "Supabase Preview": "wrapped",
}

# Every run step that sends directly to OPERATOR_EMAIL through Resend must be
# named here. The per-step policy below prevents one compliant email elsewhere
# in the same workflow from masking a new noncompliant send path.
DIRECT_OPERATOR_SEND_POLICIES = {
    (
        "alerting.yml",
        "alert",
        "Send alert email (Resend REST, fail-loud)",
    ): "generated-alert-body",
    (
        "operational-failure-alert.yml",
        "channel-test",
        "Send a novice-readable channel test",
    ): "inline-direct-action",
    (
        "operational-failure-alert.yml",
        "notify",
        "Send the actionable failure email once per open incident",
    ): "linked-technical-notice",
    (
        "s29-analytics-checkpoint.yml",
        "capture-and-email",
        "Email private packet once",
    ): "inline-technical-action",
}


def _workflow_text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _workflow_paths() -> list[Path]:
    return sorted((*WORKFLOWS.glob("*.yml"), *WORKFLOWS.glob("*.yaml")))


def _workflow_data(path: Path) -> dict:
    data = yaml.load(
        path.read_text(encoding="utf-8-sig"),
        Loader=yaml.BaseLoader,
    )
    assert isinstance(data, dict), f"workflow {path.name} is not a mapping"
    return data


def _workflow_name(path: Path, text: str) -> str:
    match = re.search(r"(?m)^name:\s*([^\r\n]+)", text)
    assert match, f"workflow {path.name} has no top-level name"
    return match.group(1).strip().strip("'\"")


def _main_push_workflow_names() -> set[str]:
    names = set()
    for path in _workflow_paths():
        text = path.read_text(encoding="utf-8-sig")
        workflow = _workflow_data(path)
        triggers = workflow.get("on") if isinstance(workflow, dict) else None
        push = triggers.get("push") if isinstance(triggers, dict) else None
        branches = push.get("branches") if isinstance(push, dict) else None
        if isinstance(branches, str):
            branches = [branches]
        if isinstance(branches, list) and "main" in branches:
            names.add(_workflow_name(path, text))
    return names


def _scheduled_workflow_names() -> set[str]:
    names = set()
    for path in _workflow_paths():
        text = path.read_text(encoding="utf-8-sig")
        workflow = _workflow_data(path)
        triggers = workflow.get("on")
        if isinstance(triggers, dict) and "schedule" in triggers:
            names.add(_workflow_name(path, text))
    return names


def _wrapped_workflow_names() -> list[str]:
    path = WORKFLOWS / "operational-failure-alert.yml"
    workflow = _workflow_data(path)
    triggers = workflow.get("on")
    workflow_run = (
        triggers.get("workflow_run") if isinstance(triggers, dict) else None
    )
    wrapped = (
        workflow_run.get("workflows")
        if isinstance(workflow_run, dict)
        else None
    )
    assert isinstance(
        wrapped, list
    ), "failure wrapper has no workflow_run.workflows list"
    return [str(name) for name in wrapped]


def _job_if(workflow_name: str, job_id: str) -> str:
    workflow = _workflow_data(WORKFLOWS / workflow_name)
    jobs = workflow.get("jobs")
    assert isinstance(jobs, dict), f"{workflow_name} has no jobs"
    job = jobs.get(job_id)
    assert isinstance(job, dict), f"{workflow_name} has no {job_id} job"
    return " ".join(str(job.get("if") or "").split())


def _preview_wrapper_has_trusted_pr_close_scope() -> bool:
    lifecycle = _workflow_data(WORKFLOWS / "supabase-preview.yml")
    triggers = lifecycle.get("on")
    pr_target = (
        triggers.get("pull_request_target")
        if isinstance(triggers, dict)
        else None
    )
    if not isinstance(pr_target, dict) or pr_target.get("types") != ["closed"]:
        return False
    try:
        lifecycle_guard = _job_if("supabase-preview.yml", "lifecycle")
    except AssertionError:
        return False
    if lifecycle_guard != (
        "github.event_name == 'pull_request_target' || "
        "(github.event_name == 'repository_dispatch' && "
        "github.event.action == 'supabase-preview-lifecycle' && "
        "github.ref == 'refs/heads/main')"
    ):
        return False
    required = (
        "github.event.workflow_run.head_repository.full_name == github.repository",
        "github.event.workflow_run.name == 'Supabase Preview'",
        "github.event.workflow_run.event == 'pull_request_target'",
    )
    wrapper_guards = [
        _job_if("operational-failure-alert.yml", job_id)
        for job_id in ("notify", "close-recovered")
    ]
    return (
        "Supabase Preview" in _wrapped_workflow_names()
        and all(all(term in guard for term in required) for guard in wrapper_guards)
        and all("workflow_run.event == 'workflow_dispatch'" not in guard for guard in wrapper_guards)
        and all("workflow_run.event == 'repository_dispatch'" not in guard for guard in wrapper_guards)
    )


def _direct_operator_send_steps() -> dict[tuple[str, str, str], dict]:
    found = {}
    for path in _workflow_paths():
        workflow = _workflow_data(path)
        jobs = workflow.get("jobs")
        if not isinstance(jobs, dict):
            continue
        for job_id, job in jobs.items():
            if not isinstance(job, dict):
                continue
            steps = job.get("steps")
            if not isinstance(steps, list):
                continue
            for step in steps:
                if not isinstance(step, dict):
                    continue
                run = str(step.get("run") or "")
                if (
                    "OPERATOR_EMAIL" not in run
                    or "api.resend.com/emails" not in run
                ):
                    continue
                name = str(step.get("name") or "")
                assert name, (
                    f"direct operator send in {path.name}/{job_id} has no name"
                )
                key = (path.name, str(job_id), name)
                assert key not in found, f"duplicate direct operator send key: {key}"
                found[key] = {"run": run, "job": job}
    return found


def test_every_direct_operator_email_step_has_its_own_contract_policy():
    sends = _direct_operator_send_steps()
    assert set(sends) == set(DIRECT_OPERATOR_SEND_POLICIES)

    for key, policy in DIRECT_OPERATOR_SEND_POLICIES.items():
        send = sends[key]
        run = send["run"]

        if policy == "generated-alert-body":
            assert "--rawfile text alert_out/email_body.txt" in run
            assert "steps.checks.outputs.subject" in str(send["job"])
            renderer = (ROOT / "src" / "alerting.py").read_text(encoding="utf-8")
            assert 'lines.append("ACTION:' in renderer
            assert "build_llm_handoff(alerts, run_url)" in renderer
        elif policy == "inline-direct-action":
            assert "--arg subject" in run and "ACTION TEST" in run
            assert '--arg text "ACTION:' in run
        elif policy == "linked-technical-notice":
            assert '--rawfile text "$NOTICE_FILE"' in run
            assert "steps.notice.outputs.notice_file" in str(send["job"])
            producer = next(
                step
                for step in send["job"]["steps"]
                if step.get("name")
                == "Build actionable failure notice without external dependencies"
            )
            producer_run = str(producer.get("run") or "")
            assert "ACTION:" in producer_run
            assert "COPY/PASTE MESSAGE FOR YOUR CODING ASSISTANT" in producer_run
            assert "richmondcommons.org" in producer_run
            assert "migration 134" in producer_run
        elif policy == "inline-technical-action":
            assert "--arg subject" in run and "ACTION" in run
            assert "ACTION: $PRIMARY_ACTION" in run
            assert "COPY/PASTE MESSAGE FOR YOUR CODING ASSISTANT" in run
            assert "richmondcommons.org" in run
            assert "migration 134" in run
        else:  # pragma: no cover - a new policy must add an explicit validator
            raise AssertionError(f"unknown direct operator send policy: {policy}")


def test_failure_wrapper_exactly_covers_classified_operator_workflows():
    scheduled = _scheduled_workflow_names()
    main_push = _main_push_workflow_names()
    available = {
        _workflow_name(path, path.read_text(encoding="utf-8-sig"))
        for path in _workflow_paths()
    }
    explicitly_wrapped = {
        name
        for name, policy in OPERATOR_CRITICAL_EVENT_WORKFLOW_POLICY.items()
        if policy == "wrapped"
    }
    wrapped = _wrapped_workflow_names()

    assert scheduled
    assert main_push == {"Build Check", "TypeScript Check"}
    assert set(OPERATOR_CRITICAL_EVENT_WORKFLOW_POLICY) <= available
    assert set(OPERATOR_CRITICAL_EVENT_WORKFLOW_POLICY.values()) == {
        "self-monitoring",
        "wrapped",
    }
    assert len(wrapped) == len(set(wrapped)), "failure wrapper contains duplicates"
    assert set(wrapped) == scheduled | main_push | explicitly_wrapped

    assert OPERATOR_CRITICAL_EVENT_WORKFLOW_POLICY["Supabase Preview"] == "wrapped"
    assert _preview_wrapper_has_trusted_pr_close_scope()


def test_failure_wrapper_stays_main_scoped_without_pr_noise():
    wrapper = _workflow_text("operational-failure-alert.yml")
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
        "supabase-preview.yml",
        "supabase-preview-expiry.yml",
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


def test_preview_lifecycle_failures_have_trusted_actionable_alert_scope():
    wrapper = _workflow_text("operational-failure-alert.yml")
    lifecycle = _workflow_text("supabase-preview.yml")

    assert "- Supabase Preview" in wrapper
    assert "- Supabase Preview Expiry" in wrapper
    assert "github.event.workflow_run.name == 'Supabase Preview'" in wrapper
    assert "github.event.workflow_run.event == 'pull_request_target'" in wrapper
    assert "github.event.workflow_run.head_repository.full_name == github.repository" in wrapper
    assert "run-name: Supabase Preview | action=" in lifecycle
    assert "github.event.client_payload.pr_number" in lifecycle
    assert _preview_wrapper_has_trusted_pr_close_scope()

    def wrapper_scope_allows(
        *, workflow: str, event: str, head_branch: str, same_repo: bool
    ) -> bool:
        return same_repo and (
            head_branch == "main"
            or (
                workflow == "Supabase Preview"
                and event == "pull_request_target"
            )
        )

    # The trusted PR-close cleanup reports the PR head, not main. Both failure
    # notification and successful recovery must accept that exact scope.
    assert wrapper_scope_allows(
        workflow="Supabase Preview",
        event="pull_request_target",
        head_branch="codex/example-preview",
        same_repo=True,
    )
    assert not wrapper_scope_allows(
        workflow="Supabase Preview",
        event="repository_dispatch",
        head_branch="codex/example-preview",
        same_repo=True,
    )
    assert wrapper_scope_allows(
        workflow="Supabase Preview",
        event="repository_dispatch",
        head_branch="main",
        same_repo=True,
    )
    assert not wrapper_scope_allows(
        workflow="Untrusted PR Workflow",
        event="pull_request_target",
        head_branch="codex/example-preview",
        same_repo=True,
    )
    assert not wrapper_scope_allows(
        workflow="Supabase Preview",
        event="pull_request",
        head_branch="codex/example-preview",
        same_repo=True,
    )
    assert not wrapper_scope_allows(
        workflow="Supabase Preview",
        event="pull_request_target",
        head_branch="codex/example-preview",
        same_repo=False,
    )

    assert wrapper.count(
        '"$WORKFLOW_ID|preview|$LIFECYCLE_ACTION|pr-$PR_NUMBER"'
    ) == 4
    assert wrapper.count('"$WORKFLOW_ID|schedule|expiry-sweep"') == 4
    assert "Cleanup comes first" in wrapper
    assert "exact PR number, exact Git branch" in wrapper
    assert "persisted Vercel deployment ID if present" in wrapper
    assert "If the ID is absent, enumerate only fresh deployments" in wrapper
    assert "do not guess" in wrapper
    assert "Cancel/delete each exact persisted or fully attested candidate first" in wrapper
    assert "Do not create, replace, reset, or retry any Preview branch" in wrapper
    assert "migration 134 as a HARD NO-GO" in wrapper

    recovery = wrapper.split("id: close_incident", 1)[1]
    preview_recovery = recovery.split(
        'if [ "$WORKFLOW" = "Supabase Preview" ]; then', 1
    )[1]
    assert 'LIFECYCLE_ACTION=$(printf' in preview_recovery
    assert 'PR_NUMBER=$(printf' in preview_recovery
    assert 'INCIDENT_KEY="$LIFECYCLE_KEY"' in preview_recovery
    assert "a successful trusted $LIFECYCLE_ACTION run for exact PR #$PR_NUMBER" in preview_recovery
    assert 'elif [ "$WORKFLOW" = "Supabase Preview Expiry" ]; then' in recovery
    assert 'RECOVERY_DETAIL="a successful trusted expiry sweep"' in recovery
    assert recovery.count('INCIDENT_KEY="$LIFECYCLE_KEY"') == 2

    expiry_guard = _job_if("supabase-preview-expiry.yml", "sweep")
    assert expiry_guard == (
        "github.event_name == 'schedule' || "
        "(github.event_name == 'repository_dispatch' && "
        "github.event.action == 'supabase-preview-expiry' && "
        "github.ref == 'refs/heads/main')"
    )
    notify_guard = _job_if("operational-failure-alert.yml", "notify")
    assert "github.event.workflow_run.conclusion == 'cancelled'" in notify_guard
    assert "github.event.workflow_run.name == 'Supabase Preview Expiry'" in notify_guard


def test_preview_name_only_wrapper_does_not_satisfy_pr_close_scope(
    tmp_path, monkeypatch
):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "supabase-preview.yml").write_text(
        """\
name: Supabase Preview
on:
  pull_request_target:
    types: [closed]
jobs: {}
""",
        encoding="utf-8",
    )
    (workflows / "operational-failure-alert.yml").write_text(
        """\
name: Operational failure alerts
on:
  workflow_run:
    workflows: [Supabase Preview]
    types: [completed]
jobs:
  notify:
    if: github.event.workflow_run.head_branch == 'main'
  close-recovered:
    if: github.event.workflow_run.head_branch == 'main'
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "WORKFLOWS", workflows)

    assert _wrapped_workflow_names() == ["Supabase Preview"]
    assert not _preview_wrapper_has_trusted_pr_close_scope()


def test_preview_incident_identity_ignores_mutable_pr_title():
    def incident_key(workflow_id: str, action: str, pr_number: int) -> str:
        scope = f"{workflow_id}|preview|{action}|pr-{pr_number}"
        return hashlib.sha256(scope.encode("utf-8")).hexdigest()

    first = incident_key("preview-workflow", "cleanup", 116)
    renamed_pr = incident_key("preview-workflow", "cleanup", 116)
    other_action = incident_key("preview-workflow", "bootstrap", 116)
    other_pr = incident_key("preview-workflow", "cleanup", 117)

    assert first == renamed_pr
    assert len({first, other_action, other_pr}) == 3


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


def test_wrapper_membership_is_parsed_instead_of_matching_comments(
    tmp_path, monkeypatch
):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "operational-failure-alert.yml").write_text(
        """\
name: Operational failure alerts
on:
  workflow_run:
    workflows:
      - Real Workflow
    types: [completed]
# - Comment-only Workflow
jobs: {}
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "WORKFLOWS", workflows)

    assert _wrapped_workflow_names() == ["Real Workflow"]


def test_direct_operator_send_discovery_tracks_each_step(tmp_path, monkeypatch):
    workflows = tmp_path / "workflows"
    workflows.mkdir()
    (workflows / "two-sends.yaml").write_text(
        """\
name: Two sends
on: workflow_dispatch
jobs:
  notify:
    steps:
      - name: First operator send
        run: |
          echo "$OPERATOR_EMAIL"
          curl https://api.resend.com/emails
      - name: Second operator send
        run: |
          echo "$OPERATOR_EMAIL"
          curl https://api.resend.com/emails
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(sys.modules[__name__], "WORKFLOWS", workflows)

    assert set(_direct_operator_send_steps()) == {
        ("two-sends.yaml", "notify", "First operator send"),
        ("two-sends.yaml", "notify", "Second operator send"),
    }


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
    assert "expired-suppression, site-health, and telemetry alerts" in playbook
    assert "Calendar and monitor-setup reminders are email-only" in playbook
    assert playbook.count("```text") >= 3
