#!/usr/bin/env bash
# web/scripts/deploy-prod.sh
#
# Deploy one operator-approved main commit to Richmond Commons production.
# The approval is external to this script and is valid only for the full SHA
# passed as the sole argument. This wrapper then fails closed unless:
#   - the local checkout is clean branch main at that SHA;
#   - canonical GitHub main and exact required CI are at that SHA;
#   - the upload is an immutable, bounded git archive of that SHA; and
#   - the pinned Vercel CLI, account, and project all target Richmond Commons.
#
# Vercel authentication remains per-user state. Log in only through the pinned
# official origins documented in web/CLAUDE.md. Non-secret project IDs are
# pinned below; no .env or mutable .vercel link is trusted for routing.
#
# Usage from Windows PowerShell in the clean main checkout:
#   powershell.exe -NoProfile -ExecutionPolicy Bypass -File \
#     .\web\scripts\deploy-prod.ps1 <operator-approved-40-character-sha>
# Direct Git Bash use remains supported; do not use Windows' bare `bash`,
# which can resolve to an unconfigured WSL installation.
#
# Boundary note: per .claude/rules/judgment-boundaries.md, command execution is
# AI-delegable only AFTER the operator approves a decision packet naming this
# exact SHA and its complete included-change list. The script proves technical
# state, not human approval. See web/CLAUDE.md "Deployment Gating".

set -euo pipefail

readonly CANONICAL_REPOSITORY="pjfront/richmond-common"
readonly CANONICAL_ORIGIN_HTTPS="https://github.com/pjfront/richmond-common.git"
readonly CANONICAL_ORIGIN_SSH="git@github.com:pjfront/richmond-common.git"
readonly EXPECTED_VERCEL_ORG_ID="team_EZvKrao9Jh9nwoKNX648v4qy"
readonly EXPECTED_VERCEL_PROJECT_ID="prj_Y0sIBsC2DKkl4lsoKbS11Y3cFTz4"
readonly EXPECTED_VERCEL_SCOPE="phillips-projects-1f180556"
readonly VERCEL_CLI_VERSION="59.1.4"
readonly NPM_REGISTRY_ORIGIN="https://registry.npmjs.org/"
readonly VERCEL_API_ORIGIN="https://api.vercel.com"
readonly PRODUCTION_DOMAIN="richmondcommons.org"

if [[ "$#" -ne 1 ]]; then
  echo "ERROR: expected exactly one operator-approved full commit SHA." >&2
  echo "       Usage: bash web/scripts/deploy-prod.sh <40-character-sha>" >&2
  exit 1
fi

readonly APPROVED_SHA="$1"
if [[ ! "$APPROVED_SHA" =~ ^[0-9a-f]{40}$ ]]; then
  echo "ERROR: approved commit must be exactly 40 lowercase hexadecimal characters." >&2
  echo "       Copy the full SHA from the approved production decision packet; short SHAs are refused." >&2
  exit 1
fi

# Refuse caller-controlled Git indirection before running any Git command.
# These variables can redirect refs, worktrees, objects, config, or namespaces
# outside the checkout named in the approval packet. Values are never printed
# because some config paths may contain credentials.
readonly FORBIDDEN_GIT_ENVIRONMENT=(
  GIT_DIR
  GIT_WORK_TREE
  GIT_INDEX_FILE
  GIT_OBJECT_DIRECTORY
  GIT_ALTERNATE_OBJECT_DIRECTORIES
  GIT_COMMON_DIR
  GIT_NAMESPACE
  GIT_SHALLOW_FILE
  GIT_QUARANTINE_PATH
  GIT_CONFIG
  GIT_CONFIG_GLOBAL
  GIT_CONFIG_SYSTEM
  GIT_CONFIG_PARAMETERS
  GIT_CONFIG_COUNT
  GIT_CONFIG_NOSYSTEM
  GIT_ATTR_NOSYSTEM
  GIT_NO_REPLACE_OBJECTS
)
for forbidden_git_variable in "${FORBIDDEN_GIT_ENVIRONMENT[@]}"; do
  if [[ -n "${!forbidden_git_variable+x}" ]]; then
    echo "ERROR: forbidden Git environment override is set: $forbidden_git_variable." >&2
    echo "       ACTION: clear that variable, return to the clean approved checkout, and rerun." >&2
    exit 1
  fi
done

# Disable local replacement refs for every Git proof and for git archive.
# Otherwise .git/refs/replace could make a named commit yield another tree.
export GIT_NO_REPLACE_OBJECTS=1
export GH_HOST=github.com
export NO_COLOR=1
export NO_UPDATE_NOTIFIER=1
export VERCEL_TELEMETRY_DISABLED=1
export VERCEL_CLI_USE_NATIVE_BINARY=0

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$WEB_DIR")"

for required_command in git gh node npx mktemp tar find awk wc rm; do
  if ! command -v "$required_command" &>/dev/null; then
    echo "ERROR: $required_command is required by the production deploy gate." >&2
    exit 1
  fi
done

validate_canonical_origin() {
  local origin_url
  origin_url="$(
    git -C "$REPO_ROOT" config --local --get remote.origin.url 2>/dev/null || true
  )"
  if [[ "$origin_url" != "$CANONICAL_ORIGIN_HTTPS" &&
    "$origin_url" != "$CANONICAL_ORIGIN_SSH" ]]; then
    echo "ERROR: origin must be the canonical $CANONICAL_REPOSITORY repository." >&2
    echo "       Refusing a missing, credentialed, fork, or alternate URL; the configured value is intentionally redacted." >&2
    exit 1
  fi
}

CANONICAL_MAIN_SHA=""

refresh_canonical_main() {
  local queried_sha
  echo "→ Querying canonical GitHub main..."
  if ! queried_sha="$(
    gh api --hostname github.com \
      "repos/$CANONICAL_REPOSITORY/git/ref/heads/main" \
      --jq '.object.sha'
  )"; then
    echo "ERROR: could not query canonical GitHub main; refusing stale Git state." >&2
    exit 1
  fi
  if [[ ! "$queried_sha" =~ ^[0-9a-f]{40}$ ]]; then
    echo "ERROR: canonical GitHub main returned an invalid SHA '${queried_sha:-missing}'." >&2
    exit 1
  fi
  CANONICAL_MAIN_SHA="$queried_sha"
}

verify_checkout() {
  local branch head_sha dirty

  validate_canonical_origin
  branch="$(git -C "$REPO_ROOT" symbolic-ref --quiet --short HEAD 2>/dev/null || true)"
  if [[ "$branch" != "main" ]]; then
    echo "ERROR: production deploy checkout must be branch main; found '${branch:-detached HEAD}'." >&2
    exit 1
  fi

  head_sha="$(git -C "$REPO_ROOT" rev-parse --verify HEAD 2>/dev/null || true)"
  if [[ "$head_sha" != "$APPROVED_SHA" ]]; then
    echo "ERROR: checkout HEAD $head_sha does not equal approved SHA $APPROVED_SHA." >&2
    exit 1
  fi

  if [[ "$CANONICAL_MAIN_SHA" != "$APPROVED_SHA" ]]; then
    echo "ERROR: canonical GitHub main $CANONICAL_MAIN_SHA does not equal approved SHA $APPROVED_SHA." >&2
    echo "       Main advanced, or the approved commit is not current main; obtain a new decision packet and approval." >&2
    exit 1
  fi

  dirty="$(
    git -C "$REPO_ROOT" status --porcelain=v1 --untracked-files=all \
      --ignore-submodules=none
  )"
  if [[ -n "$dirty" ]]; then
    echo "ERROR: production deploy checkout is not clean; refusing local changes." >&2
    printf '%s\n' "$dirty" >&2
    exit 1
  fi
}

verify_required_ci() {
  local status_line check_status check_conclusion check_sha check_event run_id

  echo "→ Checking required Build Check on approved commit ${APPROVED_SHA:0:7}..."
  if ! status_line="$(
    gh run list \
      --repo "$CANONICAL_REPOSITORY" \
      --branch main \
      --workflow build-check.yml \
      --commit "$APPROVED_SHA" \
      --event push \
      --limit 10 \
      --json databaseId,status,conclusion,headSha,event \
      --jq 'if length == 0 then empty else sort_by(.databaseId) | reverse | .[0] | "\(.status)|\(.conclusion // "missing")|\(.headSha)|\(.event)|\(.databaseId)" end'
  )"; then
    echo "ERROR: GitHub CI lookup failed; refusing to deploy without exact CI proof." >&2
    exit 1
  fi

  if [[ -z "$status_line" ]]; then
    echo "ERROR: no Build Check push run exists for approved SHA $APPROVED_SHA." >&2
    echo "       Refusing to reuse a run from another commit." >&2
    exit 1
  fi

  IFS='|' read -r check_status check_conclusion check_sha check_event run_id <<< "$status_line"
  if [[ "$check_sha" != "$APPROVED_SHA" || "$check_event" != "push" ]]; then
    echo "ERROR: Build Check run ${run_id:-unknown} is not an exact main-push proof for $APPROVED_SHA." >&2
    echo "       Reported SHA/event: ${check_sha:-missing}/${check_event:-missing}." >&2
    exit 1
  fi
  if [[ "$check_status" != "completed" ]]; then
    echo "ERROR: Build Check run $run_id on ${APPROVED_SHA:0:7} is ${check_status:-missing}." >&2
    echo "       Wait for it to complete successfully before deploying." >&2
    exit 1
  fi
  if [[ "$check_conclusion" != "success" ]]; then
    echo "ERROR: Build Check run $run_id on ${APPROVED_SHA:0:7} concluded ${check_conclusion:-missing}." >&2
    echo "       Investigate or rerun CI; only success is deployable." >&2
    exit 1
  fi

  echo "  ✓ Build Check run $run_id is green on ${APPROVED_SHA:0:7}"
}

validate_vercel_target() {
  if [[ -n "${VERCEL_ORG_ID:-}" && "$VERCEL_ORG_ID" != "$EXPECTED_VERCEL_ORG_ID" ]]; then
    echo "ERROR: ambient VERCEL_ORG_ID targets the wrong Vercel account." >&2
    echo "       Refusing to override Richmond Commons target binding." >&2
    exit 1
  fi
  if [[ -n "${VERCEL_PROJECT_ID:-}" && "$VERCEL_PROJECT_ID" != "$EXPECTED_VERCEL_PROJECT_ID" ]]; then
    echo "ERROR: ambient VERCEL_PROJECT_ID targets the wrong Vercel project." >&2
    echo "       Refusing to deploy approved Richmond source anywhere else." >&2
    exit 1
  fi
  VERCEL_ORG_ID="$EXPECTED_VERCEL_ORG_ID"
  VERCEL_PROJECT_ID="$EXPECTED_VERCEL_PROJECT_ID"
  export VERCEL_ORG_ID VERCEL_PROJECT_ID
}

VERCEL_CLI_PREPARED=0

prepare_vercel_cli() {
  local version_output

  echo "→ Preparing pinned Vercel CLI $VERCEL_CLI_VERSION before final proofs..."
  if ! version_output="$(
    # Override ambient npm offline/prefer-offline settings so this phase
    # refreshes the exact package from the pinned official registry. Every
    # later Vercel command is deliberately offline.
    npx --registry="$NPM_REGISTRY_ORIGIN" --offline=false --prefer-online --yes \
      "vercel@$VERCEL_CLI_VERSION" --version
  )"; then
    echo "ERROR: could not resolve pinned Vercel CLI $VERCEL_CLI_VERSION." >&2
    exit 1
  fi
  version_output="${version_output//$'\r'/}"
  if [[ "$version_output" != "$VERCEL_CLI_VERSION" &&
    "$version_output" != "Vercel CLI $VERCEL_CLI_VERSION" ]]; then
    echo "ERROR: pinned Vercel CLI reported unexpected version '$version_output'." >&2
    exit 1
  fi
  VERCEL_CLI_PREPARED=1
  echo "  ✓ Vercel CLI $VERCEL_CLI_VERSION is cached and version-proven"
}

vercel_cli() {
  if [[ "$VERCEL_CLI_PREPARED" != "1" ]]; then
    echo "ERROR: internal gate error: Vercel CLI used before pinned prefetch." >&2
    return 1
  fi
  # Strict offline mode prevents registry/package resolution from widening the
  # final canonical-main-to-deploy window. A missing cache fails closed.
  npx --registry="$NPM_REGISTRY_ORIGIN" --offline --yes \
    "vercel@$VERCEL_CLI_VERSION" \
    --api "$VERCEL_API_ORIGIN" --scope "$EXPECTED_VERCEL_SCOPE" "$@"
}

DEPLOY_TEMP_ROOT=""
DEPLOY_DIR=""

cleanup_deploy_artifact() {
  if [[ -z "$DEPLOY_DIR" || ! -d "$DEPLOY_DIR" ]]; then
    return
  fi

  case "$DEPLOY_DIR" in
    "$DEPLOY_TEMP_ROOT"/richmond-prod-deploy.*)
      rm -rf -- "$DEPLOY_DIR"
      ;;
    *)
      echo "WARNING: refused unsafe deploy-artifact cleanup target '$DEPLOY_DIR'." >&2
      ;;
  esac
  DEPLOY_DIR=""
}

create_deploy_artifact() {
  local requested_root forbidden_env_file forbidden_symlink info_attributes

  requested_root="${TMPDIR:-/tmp}"
  if ! DEPLOY_TEMP_ROOT="$(cd "$requested_root" 2>/dev/null && pwd -P)"; then
    echo "ERROR: could not resolve temporary directory '$requested_root'." >&2
    exit 1
  fi
  if ! DEPLOY_DIR="$(mktemp -d "$DEPLOY_TEMP_ROOT/richmond-prod-deploy.XXXXXXXX")"; then
    echo "ERROR: could not create immutable production deploy directory." >&2
    exit 1
  fi
  DEPLOY_DIR="$(cd "$DEPLOY_DIR" && pwd -P)"
  case "$DEPLOY_DIR" in
    "$DEPLOY_TEMP_ROOT"/richmond-prod-deploy.*) ;;
    *)
      echo "ERROR: temporary deploy directory escaped the resolved temp root." >&2
      DEPLOY_DIR=""
      exit 1
      ;;
  esac
  trap cleanup_deploy_artifact EXIT

  if ! info_attributes="$(
    git -C "$REPO_ROOT" rev-parse --path-format=absolute \
      --git-path info/attributes 2>/dev/null
  )"; then
    echo "ERROR: could not resolve repository-local Git archive attributes." >&2
    exit 1
  fi
  if [[ -e "$info_attributes" || -L "$info_attributes" ]]; then
    echo "ERROR: repository-local Git archive attributes are forbidden." >&2
    echo "       ACTION: remove .git/info/attributes, verify the clean approved checkout, and rerun." >&2
    exit 1
  fi

  echo "→ Creating immutable deploy artifact from ${APPROVED_SHA:0:7}..."
  # Scope attribute/config overrides to archive only. Applying them to status
  # could reinterpret a normal Windows checkout's line endings.
  if ! GIT_ATTR_NOSYSTEM=1 GIT_CONFIG_NOSYSTEM=1 \
    GIT_CONFIG_GLOBAL=/dev/null git -C "$REPO_ROOT" \
    -c core.attributesFile=/dev/null -c tar.umask=0000 \
    archive --format=tar "$APPROVED_SHA" |
    tar -xf - -C "$DEPLOY_DIR"; then
    echo "ERROR: could not create deploy artifact from approved SHA $APPROVED_SHA." >&2
    exit 1
  fi

  forbidden_symlink="$(find "$DEPLOY_DIR" -type l -print -quit)"
  if [[ -n "$forbidden_symlink" ]]; then
    echo "ERROR: immutable artifact contains forbidden symlink '$forbidden_symlink'." >&2
    echo "       Symlinks could make uploaded bytes come from outside the approved commit." >&2
    exit 1
  fi

  forbidden_env_file="$(
    find "$DEPLOY_DIR" -type f \( -name '.env' -o -name '.env.*' \) \
      ! -name '*.example' -print -quit
  )"
  if [[ -n "$forbidden_env_file" ]]; then
    echo "ERROR: immutable artifact contains forbidden environment file '$forbidden_env_file'." >&2
    echo "       Remove it from Git history before any production deploy." >&2
    exit 1
  fi
}

measure_deploy_artifact() {
  local upload_bytes upload_file_count upload_kb max_bytes max_files

  echo "→ Estimating upload size (post-.vercelignore)..."
  upload_bytes="$(cd "$DEPLOY_DIR" && find . -type f \
    -not -path './.git/*' \
    -not -path './src/*' \
    -not -path './data/*' \
    -not -path './supabase/*' \
    -not -path './tmp/*' \
    -not -path './.sfdx/*' \
    -not -path './.claude/*' \
    -not -path './node_modules/*' \
    -not -path './tests/*' \
    -not -path './docs/*' \
    -not -path './mcp/*' \
    -not -path './scripts/*' \
    -not -path './.vercel/*' \
    -not -path './.env*' \
    -not -path './web/.env*' \
    -not -path '*/node_modules/*' \
    -not -path '*/.next/*' \
    -not -name '*.pyc' -not -name '*.log' \
    -printf '%s\n' | awk '{s+=$1} END{print s+0}')"

  upload_file_count="$(cd "$DEPLOY_DIR" && find . -type f \
    -not -path './.git/*' \
    -not -path './src/*' \
    -not -path './data/*' \
    -not -path './supabase/*' \
    -not -path './tmp/*' \
    -not -path './.sfdx/*' \
    -not -path './.claude/*' \
    -not -path './node_modules/*' \
    -not -path './tests/*' \
    -not -path './docs/*' \
    -not -path './mcp/*' \
    -not -path './scripts/*' \
    -not -path './.vercel/*' \
    -not -path './.env*' \
    -not -path './web/.env*' \
    -not -path '*/node_modules/*' \
    -not -path '*/.next/*' \
    -not -name '*.pyc' -not -name '*.log' | wc -l)"

  max_bytes=$((50 * 1024 * 1024))
  max_files=2000
  if (( upload_bytes > max_bytes )); then
    echo "ERROR: estimated upload size $((upload_bytes / 1024 / 1024))MB exceeds $((max_bytes / 1024 / 1024))MB cap." >&2
    echo "       Check .vercelignore; refusing to spend Vercel upload quota." >&2
    exit 1
  fi
  if (( upload_file_count > max_files )); then
    echo "ERROR: estimated file count $upload_file_count exceeds $max_files cap." >&2
    echo "       Check .vercelignore; refusing to start Vercel." >&2
    exit 1
  fi

  upload_kb=$((upload_bytes / 1024))
  echo "  ✓ Estimated upload: ${upload_kb}KB across ${upload_file_count} files (caps: 50MB / 2000 files)"
}

read_current_production_id() {
  local summary_json deployment_id endpoint deployment_json verified_id

  if ! summary_json="$(vercel_cli inspect "$PRODUCTION_DOMAIN" --format=json)"; then
    return 1
  fi
  if ! deployment_id="$(
    printf '%s' "$summary_json" | node -e '
      let input = "";
      process.stdin.setEncoding("utf8");
      process.stdin.on("data", (chunk) => { input += chunk; });
      process.stdin.on("end", () => {
        try {
          const value = JSON.parse(input);
          const readyState = value.readyState ?? value.state;
          if (
            !/^dpl_[A-Za-z0-9]+$/.test(value.id ?? "") ||
            value.target !== "production" ||
            readyState !== "READY"
          ) process.exit(2);
          process.stdout.write(value.id);
        } catch { process.exit(2); }
      });
    '
  )"; then
    return 1
  fi

  # The CLI summary omits projectId. Bind the resolved deployment to the pinned
  # Richmond project with the authenticated full-detail endpoint before using
  # it as either rollback evidence or alias attestation.
  endpoint="/v13/deployments/$deployment_id?teamId=$EXPECTED_VERCEL_ORG_ID"
  if ! deployment_json="$(vercel_cli api "$endpoint")"; then
    return 1
  fi
  if ! verified_id="$(
    printf '%s' "$deployment_json" |
      EXPECTED_DEPLOY_ID="$deployment_id" \
      EXPECTED_DEPLOY_PROJECT="$EXPECTED_VERCEL_PROJECT_ID" node -e '
        let input = "";
        process.stdin.setEncoding("utf8");
        process.stdin.on("data", (chunk) => { input += chunk; });
        process.stdin.on("end", () => {
          try {
            const value = JSON.parse(input);
            const readyState = value.readyState ?? value.state;
            const id = value.uid ?? value.id;
            if (
              id !== process.env.EXPECTED_DEPLOY_ID ||
              value.projectId !== process.env.EXPECTED_DEPLOY_PROJECT ||
              value.target !== "production" ||
              readyState !== "READY"
            ) process.exit(2);
            process.stdout.write(id);
          } catch { process.exit(2); }
        });
      '
  )"; then
    return 1
  fi
  printf '%s\n' "$verified_id"
}

read_attested_deployment_id() {
  local locator="$1" deployment_host endpoint deployment_json deployment_id

  deployment_host="${locator#https://}"
  deployment_host="${deployment_host%/}"
  endpoint="/v13/deployments/$deployment_host?teamId=$EXPECTED_VERCEL_ORG_ID"
  # `vercel inspect --format=json` intentionally emits only a summary and omits
  # metadata. The authenticated GET deployment endpoint exposes meta + projectId.
  if ! deployment_json="$(vercel_cli api "$endpoint")"; then
    return 1
  fi
  if ! deployment_id="$(
    printf '%s' "$deployment_json" |
      EXPECTED_DEPLOY_SHA="$APPROVED_SHA" \
      EXPECTED_DEPLOY_PROJECT="$EXPECTED_VERCEL_PROJECT_ID" \
      EXPECTED_DEPLOY_HOST="$deployment_host" node -e '
        let input = "";
        process.stdin.setEncoding("utf8");
        process.stdin.on("data", (chunk) => { input += chunk; });
        process.stdin.on("end", () => {
          try {
            const value = JSON.parse(input);
            const readyState = value.readyState ?? value.state;
            const deploymentId = value.uid ?? value.id;
            if (
              !/^dpl_[A-Za-z0-9]+$/.test(deploymentId ?? "") ||
              value.target !== "production" ||
              readyState !== "READY" ||
              value.projectId !== process.env.EXPECTED_DEPLOY_PROJECT ||
              value.url !== process.env.EXPECTED_DEPLOY_HOST ||
              value.meta?.githubCommitSha !== process.env.EXPECTED_DEPLOY_SHA ||
              value.meta?.githubCommitRef !== "main" ||
              value.meta?.githubDeployment !== "1"
            ) process.exit(2);
            process.stdout.write(deploymentId);
          } catch { process.exit(2); }
        });
      '
  )"; then
    return 1
  fi
  printf '%s\n' "$deployment_id"
}

PREVIOUS_PRODUCTION_ID=""

capture_previous_production() {
  echo "→ Proving current production rollback target..."
  if ! PREVIOUS_PRODUCTION_ID="$(read_current_production_id)"; then
    echo "ERROR: could not prove the current READY production deployment." >&2
    echo "       Refusing to deploy without an exact rollback target." >&2
    exit 1
  fi
  echo "  ✓ Previous production target: $PREVIOUS_PRODUCTION_ID"
}

rollback_command() {
  printf "env NO_UPDATE_NOTIFIER=1 VERCEL_TELEMETRY_DISABLED=1 VERCEL_CLI_USE_NATIVE_BINARY=0 VERCEL_ORG_ID='%s' VERCEL_PROJECT_ID='%s' npx --registry=%s --offline --yes vercel@%s --api %s rollback %s --yes --scope %s" \
    "$EXPECTED_VERCEL_ORG_ID" "$EXPECTED_VERCEL_PROJECT_ID" \
    "$NPM_REGISTRY_ORIGIN" "$VERCEL_CLI_VERSION" "$VERCEL_API_ORIGIN" \
    "$PREVIOUS_PRODUCTION_ID" "$EXPECTED_VERCEL_SCOPE"
}

print_rollback_compatibility_action() {
  local context="${1:-success}" current_source_instruction

  echo "ACTION: Open https://richmondcommons.org and https://richmondcommons.org/api/health. If either is broken, give an LLM the message on the next line before approving any rollback."
  if [[ "$context" == "ambiguity" ]]; then
    echo "ACTION: If both URLs are healthy, do not roll back or retry. Give this entire output to an LLM and ask it to verify the exact Vercel deployment ID, production alias, and SHA/ref metadata, then resolve the attestation ambiguity."
    current_source_instruction="Resolve the actual current production deployment ID and its exact full Git SHA; do not assume current production is approved SHA $APPROVED_SHA."
  else
    echo "ACTION: If both URLs are healthy, no further action is needed; do not roll back or retry."
    current_source_instruction="Current production was attested as approved SHA $APPROVED_SHA."
  fi
  echo "LLM MESSAGE: For Richmond Commons, prepare a bounded production rollback compatibility packet from actual current production to prior Vercel deployment $PREVIOUS_PRODUCTION_ID. $current_source_instruction Resolve the prior deployment to its exact full Git SHA, or explicitly report that you cannot. Enumerate every committed Supabase migration and any explicitly approved schema-contract or manual data-correction operation between the two proven SHAs. Verify the live Supabase migration ledger and schema metadata read-only; never scan, query, or correct production table rows. Exclude ordinary content sync/ingestion. Preserve live migration 136; migration 134 is HARD NO-GO; do not propose production-data correction. Explain whether a code-only rollback is compatible. Immediately before seeking approval, re-check read-only that this deployment is still the immediately previous target and is rollback-eligible on the current Vercel plan; do not recommend a Vercel plan upgrade. After approval, re-check current production and eligibility again immediately before execution. The rollback command must use the already prepared Vercel CLI strictly offline. If its cache is missing, prefetch version $VERCEL_CLI_VERSION from $NPM_REGISTRY_ORIGIN, then repeat the current-production and eligibility proof; if state changed, prepare a new packet and obtain new approval. Any intervening target or control-plane change invalidates the approval and requires a new packet and approval. Vercel rollback changes frontend/runtime code only and never reverses Supabase migrations or data. If actual current source, exact prior source, eligibility, or compatibility cannot be proven, verdict must be UNSAFE/UNKNOWN; do not approve or execute the NOT AUTHORIZED rollback command below."
  echo "       Only if that packet proves compatibility may the operator reply exactly 'APPROVE PRODUCTION ROLLBACK: $PREVIOUS_PRODUCTION_ID'."
  echo "NOT AUTHORIZED — DO NOT RUN before that separate approval: $(rollback_command)"
}

report_post_deploy_ambiguity() {
  local reason="$1" current_id=""

  current_id="$(read_current_production_id 2>/dev/null || true)"
  echo "ERROR: production deployment could not be fully attested: $reason" >&2
  echo "       Captured previous production: $PREVIOUS_PRODUCTION_ID" >&2
  if [[ -n "$current_id" ]]; then
    echo "       Current production now resolves to: $current_id" >&2
  else
    echo "       Current production target could not be proven." >&2
  fi
  print_rollback_compatibility_action ambiguity >&2
  exit 1
}

validate_canonical_origin
validate_vercel_target

# Initial exact-source and CI proof.
refresh_canonical_main
verify_checkout
verify_required_ci

# Construct and bound the upload before any production mutation. Git replacement
# objects are disabled, and neither ignored checkout bytes nor local env/linkage
# files can enter this artifact.
create_deploy_artifact
measure_deploy_artifact

# Capture rollback evidence before the final main/CI checks. No inspect or other
# network call is allowed between the last canonical-main proof and deploy.
prepare_vercel_cli
capture_previous_production

SHORT_SHA="${APPROVED_SHA:0:7}"
echo "→ Re-proving $SHORT_SHA immediately before production deploy..."
refresh_canonical_main
verify_checkout
verify_required_ci
verify_checkout

# CI is networked, so query canonical main once more. From this point until the
# deploy invocation there is no network call and only one final local proof.
refresh_canonical_main
verify_checkout

# The Vercel project's Root Directory is `web`; the immutable artifact retains
# repo-root layout. `--meta` preserves exact-SHA attestation despite no .git.
echo "→ Deploying immutable $SHORT_SHA artifact with pinned Vercel CLI..."
if ! DEPLOY_OUTPUT="$(
  vercel_cli --cwd "$DEPLOY_DIR" --prod --yes \
    --meta "githubCommitSha=$APPROVED_SHA" \
    --meta "githubCommitRef=main" \
    --meta "githubDeployment=1"
)"; then
  echo "ERROR: Vercel did not complete the production deployment." >&2
  if CURRENT_PRODUCTION_ID="$(read_current_production_id 2>/dev/null)" &&
    [[ "$CURRENT_PRODUCTION_ID" == "$PREVIOUS_PRODUCTION_ID" ]]; then
    echo "       Previous production $PREVIOUS_PRODUCTION_ID remains active." >&2
    echo "ACTION: Do not roll back. Give this output to an LLM to diagnose the build/deploy failure before retrying." >&2
  else
    echo "       Production state could not be proven unchanged; prior target was $PREVIOUS_PRODUCTION_ID." >&2
    print_rollback_compatibility_action ambiguity >&2
    echo "       Do not retry before the state and compatibility packet are resolved." >&2
  fi
  exit 1
fi

DEPLOY_URL="${DEPLOY_OUTPUT//$'\r'/}"
if (( ${#DEPLOY_URL} > 512 )) || [[ "$DEPLOY_URL" == *$'\n'* ]] ||
  [[ ! "$DEPLOY_URL" =~ ^https://[A-Za-z0-9][A-Za-z0-9.-]*\.vercel\.app/?$ ]]; then
  report_post_deploy_ambiguity "pinned CLI returned an invalid or unbounded deployment URL"
fi

if ! DEPLOYMENT_ID="$(read_attested_deployment_id "$DEPLOY_URL")"; then
  report_post_deploy_ambiguity "returned deployment is not READY production with approved SHA/ref metadata"
fi
if ! CURRENT_PRODUCTION_ID="$(read_current_production_id)"; then
  report_post_deploy_ambiguity "$PRODUCTION_DOMAIN does not resolve to a provable READY production deployment"
fi
if [[ "$CURRENT_PRODUCTION_ID" != "$DEPLOYMENT_ID" ]]; then
  report_post_deploy_ambiguity "$PRODUCTION_DOMAIN alias does not resolve to deployed target $DEPLOYMENT_ID"
fi

printf '%s\n' "$DEPLOY_URL"
echo "  ✓ Production attested: $DEPLOYMENT_ID is READY at approved SHA $APPROVED_SHA on main"
echo ""
print_rollback_compatibility_action success
