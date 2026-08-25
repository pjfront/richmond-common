"""Static regression guards for unattended CI/deployment cost containment."""

from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parent.parent
WORKFLOWS = REPO_ROOT / ".github" / "workflows"


def _workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def test_heartbeat_commit_is_idempotent_and_non_recursive():
    text = _workflow("alerting.yml")
    assert "github.ref == 'refs/heads/main'" in text
    assert 'HEARTBEAT_DAY="$(date -u +%F)"' in text
    assert "Heartbeat already recorded" in text
    assert "git merge --no-edit origin/main" in text
    assert "fetch-depth: 0" in text
    assert "git diff --cached --quiet" in text
    assert "[skip ci]" in text
    assert "git push --force" not in text


def test_change_detector_uses_scoped_token_and_serializes_polls():
    text = _workflow("change-detector.yml")
    assert "group: source-change-detector" in text
    assert "cancel-in-progress: false" in text
    assert "queue: max" not in text
    assert "durable database outbox" in text
    assert "github.ref == 'refs/heads/main'" in text
    assert "workflow_dispatch:" not in text
    assert "types: [operator-source-change-check]" in text
    assert "github.event.action == 'operator-source-change-check'" in text
    assert "github.actor == github.repository_owner" in text
    assert "github.event_name == 'schedule'" in text
    assert "GITHUB_TOKEN: ${{ github.token }}" in text
    assert "secrets.DISPATCH_TOKEN" not in text
    assert 'SOURCE_ARG="--source ${{' not in text
    assert "github.event.inputs" not in text
    assert "github.event.client_payload.source" in text
    assert "github.event.client_payload.dry_run" in text
    assert 'ARGS+=(--source "$CHECK_SOURCE")' in text
    assert 'operator-source-change-check is read-only' in text
    assert '[ "$EVENT_NAME" = "repository_dispatch" ] && [ "$DRY_RUN" != "true" ]' in text
    assert "Validate trusted trigger payload before credentials" in text
    assert text.index("Validate trusted trigger payload before credentials") < text.index(
        "SUPABASE_SERVICE_KEY: ${{ secrets.SUPABASE_SERVICE_KEY }}"
    )


def test_data_sync_rejects_branch_and_untrusted_dispatches():
    text = _workflow("data-sync.yml")
    assert "github.ref == 'refs/heads/main'" in text
    assert "workflow_dispatch:" not in text
    assert "types: [sync-data, operator-sync-data]" in text
    assert "github.event.action == 'operator-sync-data'" in text
    assert "github.actor == github.repository_owner" in text
    assert 'EVENT_ACTION: ${{ github.event.action || \'\' }}' in text
    assert 'if [ "$EVENT_ACTION" = "sync-data" ]; then' in text
    assert 'elif [ "$EVENT_ACTION" = "operator-sync-data" ]; then' in text
    assert "github.event.inputs" not in text
    assert "github.event.client_payload.trigger_source == 'change_detector'" in text
    assert "repository_dispatch source is not allowlisted" in text
    assert "Derive the per-event cap here rather than trusting caller input" in text
    assert 'SOURCE="$INPUT_SOURCE"' in text
    assert 'SOURCE="${{ github.event' not in text
    assert "github.event.client_payload.event_budget_usd" not in text
    assert "REVALIDATION_SECRET: ${{ secrets.REVALIDATION_SECRET }}" in text
    assert "NEXT_PUBLIC_SITE_URL: ${{ vars.NEXT_PUBLIC_SITE_URL" in text
    assert '[[ "$LIMIT" =~ ^([1-9]|[1-9][0-9]|100)$ ]]' in text
    assert "accepts only incremental syncs" in text
    assert "generic operator-sync-data cannot cascade downstream enrichments" in text
    assert "minutes_extraction and refresh_stale_minutes require an explicit limit" in text
    assert "escribemeetings|escribemeetings_minutes|refresh_stale_minutes|minutes_extraction" in text
    assert "limit is accepted only for minutes_extraction" in text
    assert 'LIMIT=""' in text
    assert "Detail: enrich must be true or false." in text
    assert "Detail: unsupported repository_dispatch action:" in text
    assert "change_id must be 64 lowercase hex characters" in text
    assert 'ARGS+=(--change-id "$SYNC_CHANGE_ID")' in text
    assert 'SYNC_LIMIT: ${{ steps.inputs.outputs.limit }}' in text
    assert 'python data_sync.py "${ARGS[@]}"' in text
    assert "LIMIT_ARG=" not in text
    assert "group: data-sync-write" in text
    assert "cancel-in-progress: false" in text
    assert "queue: max" not in text
    assert text.count("MOONSHOT_API_KEY: ${{ secrets.MOONSHOT_API_KEY }}") == 4
    assert "AI_GATEWAY_API_KEY" not in text
    assert "needs: daily-nextrequest" in text
    assert "needs: daily-escribemeetings" in text
    assert text.index("- name: Resolve inputs") < text.index("actions/checkout@v5")
    assert "CLIENT_PAYLOAD: ${{ toJSON(github.event.client_payload) }}" in text
    assert '(keys - ["enrich", "limit", "source", "sync_type"])' in text

    operator_branch = text.split(
        'elif [ "$EVENT_ACTION" = "operator-sync-data" ]; then', 1
    )[1].split('\n          else\n', 1)[0]
    for forbidden in (
        "netfile",
        "calaccess",
        "nextrequest",
        "archive_center",
        "written_comments",
        "meeting_summaries",
        "form700",
        "form803_behested",
        "lobbyist_registrations",
        "propublica",
        "socrata_",
    ):
        assert forbidden not in operator_branch


def test_daily_archive_center_timeout_has_bounded_runtime_headroom():
    workflow = yaml.safe_load(_workflow("data-sync.yml"))
    timeout_minutes = workflow["jobs"]["daily-archive-center"].get(
        "timeout-minutes"
    )

    # Run 32704817567 completed both substantive steps at 19m59s. Keep an
    # explicit 30-minute ceiling: enough cleanup headroom without broadening
    # the job's data or API-cost scope.
    assert timeout_minutes == 30


def test_touched_data_workflow_annotations_always_include_novice_action():
    for workflow in ("change-detector.yml", "data-sync.yml"):
        for line in _workflow(workflow).splitlines():
            for level in ("error", "warning", "notice"):
                marker = f"::{level}::"
                if marker in line:
                    assert f"{marker}ACTION:" in line, (
                        f"{workflow}: {line.strip()}"
                    )


def test_alert_mode_is_env_bound_before_shell_use():
    text = _workflow("alerting.yml")
    assert "repository_dispatch:" in text
    assert "types: [alerting-run]" in text
    assert "  workflow_dispatch:" not in text
    assert "github.event.action == 'alerting-run'" in text
    assert "Validate trusted trigger payload before credentials" in text
    assert 'auto|daily|weekly|monthly)' in text
    assert "ALERT_MODE: ${{ steps.trigger.outputs.mode }}" in text
    assert '--mode "$ALERT_MODE"' in text
    assert '--mode "${{' not in text


def test_production_secret_workflows_reject_branch_runs_and_bind_inputs():
    cloud = _workflow("cloud-pipeline.yml")
    recap = _workflow("post-meeting-recap.yml")
    quality = _workflow("data-quality.yml")

    for text in (cloud, recap, quality):
        assert "github.ref == 'refs/heads/main'" in text
        assert "workflow_dispatch:" not in text
        assert "repository_dispatch:" in text

    assert 'MEETING_DATE="$INPUT_MEETING_DATE"' in cloud
    assert 'SCAN_MODE="prospective"' in cloud
    assert '--date "$PIPELINE_MEETING_DATE"' in cloud
    assert 'MEETING_DATE="${{ github.event' not in cloud
    assert "client_payload.scan_mode" not in cloud
    assert "client_payload.trigger_source" not in cloud
    assert "Only the trusted quarterly schedule may select retrospective mode" in cloud

    assert 'OVERRIDE="$INPUT_MEETING_DATE"' in recap
    assert 'ARGS+=(--video-id "$INPUT_VIDEO_ID")' in recap
    assert 'python post_meeting_recap.py "${ARGS[@]}"' in recap
    assert 'VIDEO_ID_FLAG="--video-id ${{' not in recap
    assert "--force" not in recap

    assert 'if [ "$INPUT_CITY_FIPS" != "0660620" ]' in quality
    assert 'python data_quality_checks.py "${ARGS[@]}"' in quality
    assert 'FIPS="${{ github.event.inputs' not in quality
    assert 'EVENT_SCHEDULE: ${{ github.event.schedule' in quality
    assert "github.event.inputs" not in quality
    assert 'ARGS=(--days "$DAYS" --create-decisions)' in quality
    assert 'python self_assessment.py "${ARGS[@]}"' in quality
    assert "python self_assessment.py --days $DAYS --create-decisions" not in quality
    assert "timeout-minutes: 10" in quality


def test_data_quality_self_assessment_decision_writes_are_explicit():
    quality = _workflow("data-quality.yml")
    self_assessment = quality.split(
        "- name: Scheduled self-assessment and decision queue", 1
    )[1]

    assert "if: always() && github.event_name == 'schedule'" in self_assessment
    assert "repository_dispatch" not in self_assessment
    assert self_assessment.count("--create-decisions") == 1


def test_pr_build_never_materializes_production_supabase_secrets():
    text = _workflow("build-check.yml")
    assert "Configure isolated PR build environment" in text
    assert "NEXT_PUBLIC_SUPABASE_URL=http://127.0.0.1:9" in text
    assert "RICHMOND_BUILD_USES_PRODUCTION_DATA=false" in text
    assert "Configure main production integration build" in text
    assert "if: github.event_name == 'push' && github.ref == 'refs/heads/main'" in text
    assert "RICHMOND_BUILD_USES_PRODUCTION_DATA=true" in text
    assert "isolated-pr" in text
    assert "prod-integration" in text
