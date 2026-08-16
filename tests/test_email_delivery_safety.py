"""Static guards for the bounded S29 subscriber-email cutover."""
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE_MIGRATION = ROOT / "src" / "migrations" / "141_email_deliveries.sql"
SUPABASE_MIGRATION = (
    ROOT / "supabase" / "migrations" / "20260816014100_email_deliveries.sql"
)
SOURCE_HARDENING = (
    ROOT / "src" / "migrations" / "142_tighten_email_delivery_grants.sql"
)
SUPABASE_HARDENING = (
    ROOT
    / "supabase"
    / "migrations"
    / "20260816014200_tighten_email_delivery_grants.sql"
)


def test_email_delivery_migration_mirrors_are_identical():
    assert SOURCE_MIGRATION.read_bytes() == SUPABASE_MIGRATION.read_bytes()


def test_email_delivery_privilege_hardening_is_mirrored_and_bounded():
    assert SOURCE_HARDENING.read_bytes() == SUPABASE_HARDENING.read_bytes()
    migration = SOURCE_HARDENING.read_text(encoding="utf-8")

    sql = "\n".join(
        line for line in migration.splitlines()
        if not line.lstrip().startswith("--")
    )
    statements = [
        " ".join(statement.split())
        for statement in sql.split(";")
        if statement.strip()
    ]
    assert statements == [
        "REVOKE ALL PRIVILEGES ON TABLE public.email_deliveries "
        "FROM PUBLIC, anon, authenticated, service_role",
        "GRANT SELECT, INSERT, UPDATE ON TABLE public.email_deliveries "
        "TO service_role",
        "REVOKE ALL PRIVILEGES ON FUNCTION "
        "public.record_subscription_activation_intent() "
        "FROM PUBLIC, anon, authenticated, service_role",
    ]

    assert (
        "REVOKE ALL PRIVILEGES ON TABLE public.email_deliveries\n"
        "    FROM PUBLIC, anon, authenticated, service_role;"
    ) in migration
    assert (
        "GRANT SELECT, INSERT, UPDATE ON TABLE public.email_deliveries\n"
        "    TO service_role;"
    ) in migration
    assert (
        "REVOKE ALL PRIVILEGES ON FUNCTION "
        "public.record_subscription_activation_intent()\n"
        "    FROM PUBLIC, anon, authenticated, service_role;"
    ) in migration
    for forbidden in (
        "DELETE FROM public.email_deliveries",
        "UPDATE public.email_deliveries",
        "INSERT INTO public.email_deliveries",
        "GRANT DELETE",
        "GRANT EXECUTE",
    ):
        assert forbidden not in migration


def test_email_delivery_retry_policy_is_bounded_and_payload_stable():
    migration = SOURCE_MIGRATION.read_text(encoding="utf-8")

    assert "attempt_count BETWEEN 0 AND 3" in migration
    assert "INTERVAL '23 hours'" in migration
    assert "INTERVAL '5 minutes'" in migration
    assert "INTERVAL '30 minutes'" in migration
    assert "payload_sha256" in migration
    assert "payload_changed" in migration
    assert "provider_ambiguous" in migration
    assert "manual_review" in migration
    assert "COALESCE(payload_sha256 ~ '^[0-9a-f]{64}$', FALSE)" in migration
    assert "status IN ('pending', 'cancelled')" in migration
    assert "SET payload_sha256 = p_payload_sha256" in migration


def test_cutover_preserves_legacy_markers_without_a_data_backfill():
    migration = SOURCE_MIGRATION.read_text(encoding="utf-8")
    route = (
        ROOT
        / "web"
        / "src"
        / "app"
        / "api"
        / "email"
        / "send-orientation"
        / "route.ts"
    ).read_text(encoding="utf-8")

    # The migration defines delivery mechanics only: it does not infer or
    # rewrite historical sends from production data.
    assert "INSERT INTO email_deliveries SELECT" not in migration
    assert "INSERT INTO subscription_activations SELECT" not in migration
    assert "UPDATE meetings SET orientation_emailed_at" not in migration
    assert "UPDATE email_subscribers SET last_orientation_meeting_id" not in migration

    # Runtime cutover continues honoring both legacy authorities.
    assert ".is('orientation_emailed_at', null)" in route
    assert ".limit(1)" in route
    assert "subscriber.last_orientation_meeting_id !== meeting.id" in route
    assert "legacy meeting delivery marker is already set" in route


def test_activation_history_and_welcome_intent_are_atomic_without_backfill():
    migration = SOURCE_MIGRATION.read_text(encoding="utf-8")
    subscribe_route = (
        ROOT / "web" / "src" / "app" / "api" / "subscribe" / "route.ts"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE IF NOT EXISTS subscription_activations" in migration
    assert "current_activation_id UUID" in migration
    assert "record_subscription_activation_intent_trigger" in migration
    assert "INSERT INTO subscription_activations" in migration
    assert "subscription_activation_id" in migration
    assert "'welcome:' || NEW.current_activation_id::TEXT" in migration
    assert "'pending', 0, NULL" in migration
    assert "'november_election'" in migration
    assert "ADD CONSTRAINT email_subscribers_activation_marker_check" in migration
    assert "Reactivation requires a fresh activation marker" in migration
    assert "current_activation_id: activationId" in subscribe_route
    assert "current_activation_surface: acquisitionSurface" in subscribe_route
    assert "acquisition_surface:" not in subscribe_route
    assert "unsubscribe_token: rotatedUnsubscribeToken" in subscribe_route
    assert "unsubscribeToken = reactivated.unsubscribe_token" in subscribe_route
    assert "return subscribeSuccessResponse()" in subscribe_route
    assert "already_subscribed" not in subscribe_route


def test_activation_history_is_automatically_pruned_after_90_days():
    migration = SOURCE_MIGRATION.read_text(encoding="utf-8")
    retry_route = (
        ROOT / "web" / "src" / "app" / "api" / "email"
        / "retry-deliveries" / "route.ts"
    ).read_text(encoding="utf-8")

    assert "CREATE OR REPLACE FUNCTION prune_subscription_activations()" in migration
    assert "DELETE FROM public.subscription_activations" in migration
    assert "INTERVAL '90 days'" in migration
    assert "GRANT EXECUTE ON FUNCTION prune_subscription_activations()" in migration
    assert "DELETE FROM public.email_subscribers" not in migration
    assert "prune_subscription_activations" in retry_route
    assert "Failed to enforce activation retention" in retry_route


def test_workflow_surfaces_partial_delivery_and_recovers_due_recipient_rows():
    workflow = (ROOT / ".github" / "workflows" / "data-sync.yml").read_text(
        encoding="utf-8"
    )
    retry_workflow = (
        ROOT / ".github" / "workflows" / "email-delivery.yml"
    ).read_text(encoding="utf-8")
    orientation_route = (
        ROOT
        / "web"
        / "src"
        / "app"
        / "api"
        / "email"
        / "send-orientation"
        / "route.ts"
    ).read_text(encoding="utf-8")
    retry_route = (
        ROOT / "web" / "src" / "app" / "api" / "email"
        / "retry-deliveries" / "route.ts"
    ).read_text(encoding="utf-8")
    manifest = (ROOT / "docs" / "pipeline-manifest.yaml").read_text(
        encoding="utf-8"
    )

    assert "retryPendingEmailDeliveries" not in orientation_route
    assert "welcome_retries_only" not in orientation_route
    assert "retryPendingEmailDeliveries" in retry_route
    assert "Agenda preview send failed (non-fatal" not in workflow
    assert "--fail-with-body" in workflow
    assert "cron: '17 */4 * * *'" in retry_workflow
    assert "/api/email/retry-deliveries" in retry_workflow
    assert "/api/email/retry-welcomes" not in retry_workflow
    assert "welcome_retries_only" not in retry_workflow
    assert "--fail-with-body" in retry_workflow
    assert "at most 50 total due welcome and orientation deliveries" in manifest
    assert "through the existing orientation endpoint" not in manifest


def test_orientation_recovery_is_bounded_and_terminalizes_stale_rows_safely():
    delivery = (
        ROOT / "web" / "src" / "lib" / "email-delivery.ts"
    ).read_text(encoding="utf-8")
    migration = SOURCE_MIGRATION.read_text(encoding="utf-8")
    subscribe_route = (
        ROOT / "web" / "src" / "app" / "api" / "subscribe" / "route.ts"
    ).read_text(encoding="utf-8")

    assert "MAX_DELIVERY_RETRIES_PER_REQUEST = 50" in delivery
    assert ".in('delivery_kind', ['welcome', 'orientation'])" in delivery
    assert "orientationMeetingId(row.content_key)" in delivery
    assert "orientation_preview_provenance" in delivery
    assert (
        ".select('id, meeting_date, orientation_preview, "
        "orientation_preview_provenance, agenda_url')"
    ) in subscribe_route
    assert "orientation_preview_provenance:" in subscribe_route
    assert "meeting.meeting_date < today" in delivery
    assert "meeting.source_cancelled_at" in delivery
    assert "meeting.orientation_emailed_at" not in delivery
    assert "terminalize_retryable_email_delivery" in delivery
    assert "CREATE OR REPLACE FUNCTION terminalize_retryable_email_delivery" in migration
    assert "lease_expires_at <= NOW()" in migration
    assert "invalid_content_key" in migration
    assert "recipient_inactive" in migration
    assert "source_unavailable" in migration


def test_recap_cutover_checks_both_legacy_markers():
    api_route = (
        ROOT / "web" / "src" / "app" / "api" / "email"
        / "send-recap" / "route.ts"
    ).read_text(encoding="utf-8")
    operator_route = (
        ROOT / "web" / "src" / "app" / "api" / "operator"
        / "send-recap" / "route.ts"
    ).read_text(encoding="utf-8")

    for route in (api_route, operator_route):
        assert "recap_emailed_at" in route
        assert "transcript_recap_emailed_at" in route
        assert "legacy recap delivery marker is already set" in route
