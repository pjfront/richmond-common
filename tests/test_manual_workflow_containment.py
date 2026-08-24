"""Structural guards for trusted-main manual production workflows."""

import json
import os
import re
import subprocess
import sys
from pathlib import Path

import pytest
import yaml


ROOT = Path(__file__).parent.parent
WORKFLOWS = ROOT / ".github" / "workflows"

CONTAINED = {
    "operational-failure-alert.yml": "operator-alert-channel-test",
    "db-backup.yml": "operator-db-backup",
    "post-meeting-recap.yml": "operator-post-meeting-recap",
    "cloud-pipeline.yml": "operator-cloud-pipeline",
    "data-quality.yml": "operator-data-quality-check",
    "s29-analytics-checkpoint.yml": "operator-s29-analytics-checkpoint",
    "subscriber-weekly-digest.yml": "subscriber-digest-canary",
}


def _text(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _data(name: str) -> dict:
    value = yaml.load(_text(name), Loader=yaml.BaseLoader)
    assert isinstance(value, dict)
    return value


def test_secret_bearing_manual_workflows_have_no_branch_selectable_dispatch():
    for name, event_type in CONTAINED.items():
        text = _text(name)
        workflow = _data(name)
        triggers = workflow["on"]

        assert "workflow_dispatch" not in triggers, name
        assert triggers["repository_dispatch"]["types"] == [event_type], name
        assert f"github.event.action == '{event_type}'" in text, name
        assert "github.ref == 'refs/heads/main'" in text, name
        assert "ref: ${{" not in text, name


def test_typed_operator_jobs_require_the_repository_owner():
    for name, event_type in CONTAINED.items():
        jobs = _data(name)["jobs"]
        operator_conditions = [
            str(job.get("if") or "")
            for job in jobs.values()
            if event_type in str(job.get("if") or "")
        ]

        assert operator_conditions, name
        for condition in operator_conditions:
            assert "github.event_name == 'repository_dispatch'" in condition, name
            assert f"github.event.action == '{event_type}'" in condition, name
            assert "github.actor == github.repository_owner" in condition, name


def test_payloads_are_rejected_before_any_production_secret_is_bound():
    validation_names = {
        "operational-failure-alert.yml": "Validate the empty channel-test request before secrets",
        "db-backup.yml": "Validate the empty backup request before secrets",
        "post-meeting-recap.yml": "Validate the bounded recap request before secrets",
        "cloud-pipeline.yml": "Resolve inputs",
        "data-quality.yml": "Validate the empty read-only request before secrets",
        "s29-analytics-checkpoint.yml": "Validate the single checkpoint before secrets",
        "subscriber-weekly-digest.yml": "Validate the empty canary request before secrets",
    }

    for name, step_name in validation_names.items():
        text = _text(name)
        assert text.index(step_name) < text.index("${{ secrets."), name
        assert "CLIENT_PAYLOAD: ${{ toJSON(github.event.client_payload) }}" in text


def test_manual_payload_allowlists_stay_bounded_and_noncorrective():
    empty_payload_workflows = (
        "operational-failure-alert.yml",
        "db-backup.yml",
        "data-quality.yml",
        "subscriber-weekly-digest.yml",
    )
    for name in empty_payload_workflows:
        assert 'type == "object" and length == 0' in _text(name), name

    recap = _text("post-meeting-recap.yml")
    assert 'keys - ["meeting_date", "video_id"]' in recap
    assert "--force" not in recap
    assert "client_payload.force" not in recap

    cloud = _text("cloud-pipeline.yml")
    assert 'keys - ["meeting_date"]' in cloud
    assert "client_payload.scan_mode" not in cloud
    assert "client_payload.trigger_source" not in cloud
    assert 'SCAN_MODE="prospective"' in cloud
    assert 'EVENT_SCHEDULE: ${{ github.event.schedule || \'\' }}' in cloud
    assert 'EVENT_SCHEDULE" = "0 8 1 1,4,7,10 *"' in cloud

    checkpoint = _text("s29-analytics-checkpoint.yml")
    assert 'keys == ["checkpoint"]' in checkpoint
    for value in ("B7", "B14", "T7", "T14"):
        assert f'.checkpoint == "{value}"' in checkpoint


def test_recap_values_are_fully_validated_before_any_secret_is_bound():
    recap = _text("post-meeting-recap.yml")
    validator = recap.split(
        "- name: Validate the bounded recap request before secrets", 1
    )[1].split("\n      - name:", 1)[0]

    assert 'has("meeting_date") and .meeting_date != null' in validator
    assert '"$MEETING_DATE" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$' in validator
    assert 'date -u -d "$MEETING_DATE" +%F' in validator
    assert 'has("video_id") and .video_id != null' in validator
    assert '"$VIDEO_ID" =~ ^[A-Za-z0-9_-]{11}$' in validator
    assert recap.index(validator) < recap.index("${{ secrets.")


@pytest.mark.skipif(
    sys.platform == "win32",
    reason="The hosted Ubuntu runner supplies jq and GNU date for this contract",
)
def test_recap_validator_executes_real_date_and_video_id_checks_on_ubuntu():
    workflow = _data("post-meeting-recap.yml")
    validator = next(
        step
        for step in workflow["jobs"]["check-meeting"]["steps"]
        if step.get("name") == "Validate the bounded recap request before secrets"
    )["run"]

    cases = (
        ({}, True),
        (
            {"meeting_date": "2026-02-28", "video_id": "Abc_def-123"},
            True,
        ),
        ({"meeting_date": "2026-02-30"}, False),
        ({"meeting_date": ""}, False),
        ({"video_id": "https://youtu.be/Abc_def-123"}, False),
        ({"video_id": ""}, False),
        ({"unexpected": "field"}, False),
    )
    for payload, expected_success in cases:
        result = subprocess.run(
            ["bash", "-c", validator],
            env={**os.environ, "CLIENT_PAYLOAD": json.dumps(payload)},
            capture_output=True,
            text=True,
            check=False,
        )
        assert (result.returncode == 0) is expected_success, (
            payload,
            result.stdout,
            result.stderr,
        )
        if not expected_success:
            assert "::error::ACTION:" in result.stdout


def test_channel_test_monitor_secret_is_bound_only_after_a_valid_failed_email():
    wrapper = _text("operational-failure-alert.yml")
    monitor = wrapper.split(
        "- name: Signal the independent monitor if the channel test failed", 1
    )[1].split("\n      - name:", 1)[0]

    assert "steps.request.outcome == 'success'" in monitor
    assert "steps.test_email.outcome == 'failure'" in monitor
    assert "steps.request.outcome == 'failure'" not in monitor
    assert (
        "HEALTHCHECKS_PING_URL: ${{ secrets.HEALTHCHECKS_PING_URL }}" in monitor
    )


def test_typed_manual_alert_incidents_are_always_run_specific():
    wrapper = _text("operational-failure-alert.yml")
    manual_scope = (
        '[ "$EVENT" = "workflow_dispatch" ] || '
        '[ "$EVENT" = "repository_dispatch" ]'
    )

    # Lookup, recovery marker, audit fallback, and successful-run handling must
    # all agree that typed manual events cannot share or close another run's issue.
    assert wrapper.count(manual_scope) == 4
    assert 'INCIDENT_KEY="run-$RUN_ID"' in wrapper
    assert 'RECOVERY_KEY="run-$RUN_ID"' in wrapper
    recovery = wrapper.split("id: close_incident", 1)[1]
    assert manual_scope in recovery
    assert "Manual run scope is not provable" in recovery


def test_touched_workflow_annotations_always_tell_the_operator_what_to_do():
    annotation = re.compile(r"::(error|warning|notice)(?: [^:]*)?::(.*)")
    for name in CONTAINED:
        annotations = [
            (match.group(1), match.group(2), line.strip())
            for line in _text(name).splitlines()
            if (match := annotation.search(line))
        ]
        assert annotations, name
        for kind, message, line in annotations:
            assert message.startswith("ACTION:"), f"{name} {kind}: {line}"


def test_manual_data_quality_path_skips_self_assessment_and_decision_writes():
    quality = _text("data-quality.yml")
    self_assessment = quality.split(
        "- name: Scheduled self-assessment and decision queue", 1
    )[1]

    assert "if: always() && github.event_name == 'schedule'" in self_assessment
    assert "repository_dispatch" not in self_assessment
    assert 'ARGS=(--days "$DAYS" --create-decisions)' in self_assessment


def test_schedules_and_automatic_failure_wrapping_are_preserved():
    expected_crons = {
        "db-backup.yml": ["0 9 * * 0"],
        "post-meeting-recap.yml": ["17 15 * * *"],
        "cloud-pipeline.yml": ["0 6 * * 1", "0 8 1 1,4,7,10 *"],
        "data-quality.yml": ["0 7 * * *", "0 12 * * 5"],
    }
    for name, expected in expected_crons.items():
        schedules = _data(name)["on"]["schedule"]
        assert [item["cron"] for item in schedules] == expected

    wrapper = _data("operational-failure-alert.yml")["on"]["workflow_run"]
    assert wrapper["types"] == ["completed"]
    assert set(wrapper["workflows"]) >= {
        "Cloud Pipeline",
        "Data Quality Checks",
        "DB Backup",
        "Post-Meeting Recap",
        "S29 analytics checkpoint",
        "Weekly subscriber digest",
    }


def test_manifest_and_operator_commands_describe_typed_events():
    manifest = yaml.safe_load(
        (ROOT / "docs" / "pipeline-manifest.yaml").read_text(encoding="utf-8")
    )
    for name in ("cloud-pipeline.yml", "data-quality.yml", "post-meeting-recap.yml"):
        trigger_types = {
            trigger["type"] for trigger in manifest["schedules"][name]["triggers"]
        }
        assert "repository_dispatch" in trigger_types
        assert "workflow_dispatch" not in trigger_types

    playbook = (ROOT / "docs" / "operator-alert-playbook.md").read_text(
        encoding="utf-8"
    )
    channel_test_command = re.search(
        r"^\s*'(?P<payload>\{.*\})' \| gh api --method POST "
        r"repos/pjfront/richmond-common/dispatches --input -\s*$",
        playbook,
        re.MULTILINE,
    )
    assert channel_test_command is not None
    assert json.loads(channel_test_command.group("payload")) == {
        "event_type": "operator-alert-channel-test",
        "client_payload": {},
    }
    assert "repository owner (`pjfront`)" in playbook
    checkpoint_runbook = (
        ROOT / "docs" / "plans" / "2026-08-15-s29-analytics-baseline-release-runbook.md"
    ).read_text(encoding="utf-8")
    assert "event_type=operator-s29-analytics-checkpoint" in checkpoint_runbook
    assert 'client_payload[checkpoint]=B7' in checkpoint_runbook
    assert "repository owner (`pjfront`)" in checkpoint_runbook

    parking_lot = (ROOT / "docs" / "PARKING-LOT.md").read_text(encoding="utf-8")
    recap_row = next(
        line for line in parking_lot.splitlines() if line.startswith("| S24.20b |")
    )
    assert "workflow_dispatch" not in recap_row
    assert (
        "owner-only `operator-post-meeting-recap` typed repository event" in recap_row
    )
    assert "11-character `video_id` payload" in recap_row
