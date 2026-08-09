"""Static regression guards for unattended CI/deployment cost containment."""

from pathlib import Path


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
    assert "queue: max" in text
    assert "if: github.ref == 'refs/heads/main'" in text
    assert "GITHUB_TOKEN: ${{ github.token }}" in text
    assert "secrets.DISPATCH_TOKEN" not in text
    assert 'SOURCE_ARG="--source ${{' not in text
    assert '"${{ github.event.inputs.dry_run }}"' not in text
    assert 'ARGS+=(--source "$INPUT_SOURCE")' in text


def test_data_sync_rejects_branch_and_untrusted_dispatches():
    text = _workflow("data-sync.yml")
    assert "github.ref == 'refs/heads/main'" in text
    assert "github.event.client_payload.trigger_source == 'change_detector'" in text
    assert "repository_dispatch source is not allowlisted" in text
    assert "Derive the per-event cap here rather than trusting caller input" in text
    assert 'SOURCE="$INPUT_SOURCE"' in text
    assert 'SOURCE="${{ github.event' not in text
    assert "github.event.client_payload.event_budget_usd" not in text
    assert "REVALIDATION_SECRET: ${{ secrets.REVALIDATION_SECRET }}" in text
    assert "NEXT_PUBLIC_SITE_URL: ${{ vars.NEXT_PUBLIC_SITE_URL" in text
    assert '[[ "$LIMIT" =~ ^[0-9]+$ ]]' in text
    assert 'LIMIT=""' in text
    assert "change_id must be 64 lowercase hex characters" in text
    assert 'ARGS+=(--change-id "$SYNC_CHANGE_ID")' in text
    assert 'SYNC_LIMIT: ${{ steps.inputs.outputs.limit }}' in text
    assert 'python data_sync.py "${ARGS[@]}"' in text
    assert "LIMIT_ARG=" not in text
    assert "queue: max" in text
    assert text.count("MOONSHOT_API_KEY: ${{ secrets.MOONSHOT_API_KEY }}") == 4
    assert "AI_GATEWAY_API_KEY" not in text
    assert "needs: daily-nextrequest" in text
    assert "needs: daily-escribemeetings" in text


def test_alert_mode_is_env_bound_before_shell_use():
    text = _workflow("alerting.yml")
    assert "ALERT_MODE: ${{ github.event.inputs.mode || 'auto' }}" in text
    assert '--mode "$ALERT_MODE"' in text
    assert '--mode "${{' not in text


def test_production_secret_workflows_reject_branch_runs_and_bind_inputs():
    cloud = _workflow("cloud-pipeline.yml")
    recap = _workflow("post-meeting-recap.yml")
    quality = _workflow("data-quality.yml")

    for text in (cloud, recap, quality):
        assert "if: github.ref == 'refs/heads/main'" in text

    assert 'MEETING_DATE="$INPUT_MEETING_DATE"' in cloud
    assert 'SCAN_MODE="$INPUT_SCAN_MODE"' in cloud
    assert '--date "$PIPELINE_MEETING_DATE"' in cloud
    assert 'MEETING_DATE="${{ github.event' not in cloud
    assert "scan_mode must be prospective or retrospective" in cloud

    assert 'OVERRIDE="$INPUT_MEETING_DATE"' in recap
    assert 'ARGS+=(--video-id "$INPUT_VIDEO_ID")' in recap
    assert 'python post_meeting_recap.py "${ARGS[@]}"' in recap
    assert 'VIDEO_ID_FLAG="--video-id ${{' not in recap

    assert 'if [ "$INPUT_CITY_FIPS" != "0660620" ]' in quality
    assert 'python data_quality_checks.py "${ARGS[@]}"' in quality
    assert 'FIPS="${{ github.event.inputs' not in quality
    assert 'EVENT_SCHEDULE: ${{ github.event.schedule' in quality
    assert "timeout-minutes: 10" in quality


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
