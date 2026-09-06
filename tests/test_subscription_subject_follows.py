"""Release and schema guardrails alongside the executable PGlite scenarios."""
from pathlib import Path

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


def test_subject_capture_does_not_activate_a_broadcast_or_new_scheduler():
    route = (ROOT / "web/src/app/api/email/send-digest/route.ts").read_text(encoding="utf-8")
    rollout = (ROOT / "web/src/lib/subscription-subjects.ts").read_text(encoding="utf-8")
    workflow = (ROOT / ".github/workflows/subscriber-weekly-digest.yml").read_text(encoding="utf-8")
    assert "const DIGEST_BROADCAST_ENABLED = false" in route
    assert "has not started" in rollout
    assert "schedule:" not in workflow
    assert "selectSubscriberDigest(" in route
    assert "selectSubscriberDigest(" in (ROOT / "web/src/lib/email-delivery.ts").read_text(encoding="utf-8")
    assert "subscription_subject_follows.integration.mjs" in (ROOT / ".github/workflows/web-tests.yml").read_text(encoding="utf-8")
