"""Guard the novice-readable steady-state operator contract."""

from pathlib import Path
import re


ROOT = Path(__file__).parent.parent
UPKEEP = ROOT / "docs" / "operator-upkeep.md"
PLAYBOOK = ROOT / "docs" / "operator-alert-playbook.md"
EVIDENCE = ROOT / "docs" / "audits" / "2026-08-24-contained-operations-evidence.md"
SUPPRESSIONS = ROOT / "docs" / "alerting-suppressions.yaml"
ALERTING_WORKFLOW = ROOT / ".github" / "workflows" / "alerting.yml"
WORKFLOWS = ROOT / ".github" / "workflows"
ALERTING_SOURCE = ROOT / "src" / "alerting.py"


def _text() -> str:
    return UPKEEP.read_text(encoding="utf-8")


def test_alert_playbook_links_the_short_owner_manual():
    assert "[operator-upkeep.md](operator-upkeep.md)" in PLAYBOOK.read_text(
        encoding="utf-8"
    )


def test_every_one_time_setup_item_has_a_literal_action_line():
    text = _text()
    setup = text.split("## Remaining one-time setup", 1)[1].split(
        "## Routine upkeep after setup", 1
    )[0]
    items = re.split(r"(?m)^### \d+\. ", setup)[1:]

    assert len(items) == 7
    for item in items:
        assert "**ACTION:**" in item, item.splitlines()[0]


def test_upkeep_contract_has_novice_routine_and_technical_handoff():
    text = _text()
    collapsed = " ".join(text.split())
    for expected in (
        "**Daily:** none",
        "**Weekly:**",
        "**Monthly:**",
        "COPY/PASTE MESSAGE FOR YOUR CODING ASSISTANT",
        "APPROVE PRODUCTION BATCH: <full SHA>",
        "Merging is not deploying",
        "Vercel → rtp → Usage",
        "Supabase → Organization → Usage",
        "CANARY ADDRESS SET",
        "APPROVE DIGEST CANARY DISPATCH",
        "APPROVE RICHMOND 101 GRADUATION",
        "labels it **BASELINE** or **TREATMENT**",
        "14 complete untreated UTC days",
        "Pre-A0 traffic is never relabeled as baseline",
    ):
        assert expected in collapsed


def test_upkeep_contract_preserves_current_boundaries_without_private_addresses():
    text = _text()
    collapsed = " ".join(text.split())
    for expected in (
        "Supabase Pro",
        "DeepSeek-first with only the two benchmarked Luna exceptions",
        "AGPL-3.0",
        "D2=0.50",
        "migration 136 live",
        "migration 134 HARD NO-GO",
        "no broad S26/S28 expansion",
        "unbounded sync",
        "production-data correction",
    ):
        assert expected in collapsed

    assert "pjfront+" not in text
    assert "remains visible in Git history" in text
    assert "not a durable exactly-once ledger" in text


def test_firewall_draft_is_read_before_the_operator_only_publish():
    text = _text()
    collapsed = " ".join(text.split())
    diff = "vercel@59.1.4 firewall diff"
    publish = "vercel@59.1.4 firewall publish"
    assert text.index(diff) < text.index(publish)
    assert text.count("vercel@59.1.4 firewall rules inspect") == 2
    assert text.index("firewall rules inspect") < text.index(diff)
    assert "--expand" not in text
    assert "Environment equals production" in text
    assert "Environment equals preview" in text
    assert "Action: Log" in text
    assert "Action: Deny" in text
    assert "^/meetings/[^/]+/items/[^/]+/?$" in text
    assert "Amazonbot/0.1" in text
    assert 'Added rule "S29 Amazonbot production observation"' in text
    assert "Log → Deny" in text
    assert "anything differs, stop before publishing" in text
    assert "seven complete UTC days of production Log observation" in collapsed
    assert "Every production Firewall publish remains operator-only" in collapsed
    assert "Do not reuse today's command, output, or approval" in collapsed
    assert "NO_UPDATE_NOTIFIER" in text
    assert "NPM_CONFIG_REGISTRY" in text
    assert "prj_Y0sIBsC2DKkl4lsoKbS11Y3cFTz4" in text


def test_provider_capacity_threshold_is_consistently_early_warning():
    upkeep = _text()
    collapsed_upkeep = " ".join(upkeep.split())
    playbook = PLAYBOOK.read_text(encoding="utf-8")
    assert "below 75%" in upkeep
    assert "at or above 75%" in playbook
    assert "below 75%" in playbook
    assert "below 80%" not in playbook
    source = ALERTING_SOURCE.read_text(encoding="utf-8")
    provider_copy = source.split("PROVIDER USAGE AND LIMITS", 1)[1]
    assert "at or above 75%" in provider_copy
    assert "below 75%" in provider_copy
    assert "below 80%" not in provider_copy
    assert collapsed_upkeep.count("fewer than 180 rolling") == 2
    assert "at most 180" not in collapsed_upkeep


def test_manual_alert_dispatch_is_owner_only_and_exactly_typed():
    workflow = ALERTING_WORKFLOW.read_text(encoding="utf-8")
    playbook = PLAYBOOK.read_text(encoding="utf-8")
    assert "github.actor == github.repository_owner" in workflow
    assert '(keys == ["mode"])' in workflow
    assert '(.mode == "auto"' in workflow
    assert '"client_payload":{"mode":"auto"}' in playbook
    assert '"client_payload":{"mode":"monthly"}' in playbook
    assert "--raw-field" not in playbook
    assert "gh auth status" in playbook
    assert "active account is pjfront" in playbook
    assert "skipped job or no new run is a failure" in playbook
    maintenance = workflow.split(
        "- name: Monthly DB maintenance (superseded-flag prune + VACUUM)", 1
    )[1].split("- name:", 1)[0]
    assert "steps.checks.outputs.mode == 'monthly'" in maintenance
    assert "github.event_name == 'schedule'" in maintenance
    assert "repository_dispatch" not in maintenance


def test_every_operator_visible_workflow_annotation_starts_with_an_action():
    annotation = re.compile(r"::(?:error|warning|notice)(?: [^:]*)?::(.*)")
    seen = 0
    for path in sorted(WORKFLOWS.glob("*.yml")):
        for line_number, line in enumerate(
            path.read_text(encoding="utf-8").splitlines(), start=1,
        ):
            match = annotation.search(line)
            if not match:
                continue
            seen += 1
            message = match.group(1)
            assert message.startswith("ACTION:"), (
                f"{path.name}:{line_number} lacks a literal ACTION prefix: "
                f"{line.strip()}"
            )
    assert seen


def test_time_sensitive_snapshot_is_dated_and_not_presented_as_live():
    text = _text()
    assert "audits/2026-08-24-contained-operations-evidence.md" in text
    evidence = EVIDENCE.read_text(encoding="utf-8")
    collapsed = " ".join(evidence.split())
    assert "not a live dashboard" in collapsed
    assert "must not be copied forward as a current monthly check" in collapsed
    assert "Observability Plus" in evidence
    assert "476.9" in evidence
    assert "no HTTP 500s" in evidence
    assert "pjfront+" not in evidence


def test_expired_recap_hold_is_not_silently_renewed_or_replayed():
    suppressions = SUPPRESSIONS.read_text(encoding="utf-8")
    recap = suppressions.split(
        "- id: past_meetings_have_transcript_recap_within_5_days", 1
    )[1].split("- id:", 1)[0]
    assert "expires: 2026-08-15" in recap
    assert "do not renew it" in recap
    assert "do not renew it or replay production meetings" in recap
    assert "post_expiry: monitor_exact_meeting_dates_until_pass" in recap
    for meeting_date in ("2026-07-07", "2026-07-21", "2026-07-28"):
        assert meeting_date in recap
