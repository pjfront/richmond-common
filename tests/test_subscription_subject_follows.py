"""Release and schema guardrails alongside the executable PGlite scenarios."""
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]


def test_subject_migration_is_mirrored_and_preserves_consent_defaults():
    source = ROOT / "src/migrations/150_subscription_subject_follows.sql"
    mirror = ROOT / "supabase/migrations/20260906015000_subscription_subject_follows.sql"
    assert source.read_bytes() == mirror.read_bytes()
    sql = source.read_text(encoding="utf-8")
    assert "receive_council_updates boolean NOT NULL DEFAULT true" in sql
    assert "claim_email_delivery_v141" in sql
    assert "FROM PUBLIC,anon,authenticated,service_role" in sql
    for subject in ("chevron-settlement-and-city-budget", "fire-stations-and-emergency-response", "flock-cameras-and-data-privacy", "2026-general"):
        assert subject in sql


def test_weekly_activation_pairs_the_code_gate_with_monday_schedule_and_truthful_copy():
    route = (ROOT / "web/src/app/api/email/send-digest/route.ts").read_text(encoding="utf-8")
    rollout = (ROOT / "web/src/lib/subscription-subjects.ts").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/subscriber-weekly-digest.yml").read_text(encoding="utf-8")
    assert "const DIGEST_BROADCAST_ENABLED = true" in route
    assert "Mondays at 9:30 a.m. PDT / 8:30 a.m. PST" in rollout
    assert "only when a story or election you follow has a newly published update" in rollout
    assert "has not started" not in rollout
    # GitHub schedules use UTC; this is 09:30 PDT / 08:30 PST year-round.
    events = yaml.load(workflow, Loader=yaml.BaseLoader)["on"]
    assert events["schedule"] == [{"cron": "30 16 * * 1"}]
    assert events["repository_dispatch"]["types"] == ["subscriber-digest-canary"]
    assert "workflow_dispatch" not in events
    assert "github.ref == 'refs/heads/main'" in workflow
    assert 'mode === \'broadcast\' && !DIGEST_BROADCAST_ENABLED' in route
    assert "selectSubscriberDigest(" in route
    assert "selectSubscriberDigest(" in (ROOT / "web/src/lib/email-delivery.ts").read_text(encoding="utf-8")
    assert "subscription_subject_follows.integration.mjs" in (ROOT / ".github/workflows/web-tests.yml").read_text(encoding="utf-8")
