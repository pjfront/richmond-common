#!/usr/bin/env bash
# web/scripts/deploy-prod.sh
#
# Deploy the latest main commit to richmondcommons.org production.
#
# Reads VERCEL_ORG_ID and VERCEL_PROJECT_ID from ../.env (project root)
# so deploys can run from any worktree without per-directory `vercel link`.
# Refuses to deploy if the latest main commit's Build Check workflow is
# not green. Reports the deployment URL when done.
#
# Auth lives in %APPDATA%\com.vercel.cli\auth.json (per-user, machine-
# wide). Set up once via `vercel login`.
#
# Usage (from anywhere in the repo or its worktrees):
#   bash web/scripts/deploy-prod.sh
#
# Or from web/:
#   bash scripts/deploy-prod.sh
#
# Boundary note: per .claude/rules/judgment-boundaries.md, running this
# script is AI-delegable AFTER operator OK on a specific batch. The
# operator decides WHETHER to ship; AI runs the command. See web/CLAUDE.md
# "Deployment Gating" for full workflow.

set -euo pipefail

# Find repo root by walking up from this script's location. Works from
# any cwd; doesn't depend on the caller's directory.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WEB_DIR="$(dirname "$SCRIPT_DIR")"
REPO_ROOT="$(dirname "$WEB_DIR")"
ENV_FILE="$REPO_ROOT/.env"

# ── Load Vercel project linkage from .env ─────────────────────────────
if [[ ! -f "$ENV_FILE" ]]; then
  echo "ERROR: .env not found at $ENV_FILE" >&2
  echo "       Copy .env.example to .env and fill in VERCEL_ORG_ID + VERCEL_PROJECT_ID." >&2
  exit 1
fi

# Extract only the two vars we need (avoid sourcing the whole .env which
# would also export DATABASE_URL etc. into the vercel subprocess).
VERCEL_ORG_ID="$(grep -E '^VERCEL_ORG_ID=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"
VERCEL_PROJECT_ID="$(grep -E '^VERCEL_PROJECT_ID=' "$ENV_FILE" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")"

if [[ -z "$VERCEL_ORG_ID" || -z "$VERCEL_PROJECT_ID" ]]; then
  echo "ERROR: VERCEL_ORG_ID or VERCEL_PROJECT_ID missing from $ENV_FILE" >&2
  echo "       See .env.example for the format. Get values via:" >&2
  echo "         vercel login                       (one-time)" >&2
  echo "         mkdir tmp && cd tmp" >&2
  echo "         vercel link --yes --scope phillips-projects-1f180556 --project rtp" >&2
  echo "         cat .vercel/project.json           (copy projectId + orgId)" >&2
  exit 1
fi

export VERCEL_ORG_ID VERCEL_PROJECT_ID

# ── Pre-flight: Build Check status on latest main ─────────────────────
echo "→ Checking Build Check status on latest main commit..."
LATEST_MAIN="$(git -C "$REPO_ROOT" rev-parse main)"
SHORT_SHA="$(git -C "$REPO_ROOT" rev-parse --short main)"

if ! command -v gh &>/dev/null; then
  echo "  ⚠ gh CLI not found; cannot verify Build Check status pre-flight." >&2
  echo "  ⚠ Proceeding anyway. Install gh to enable this gate." >&2
else
  # Get the most recent Build Check run; check its commit + conclusion.
  STATUS_LINE="$(gh run list \
    --repo "$(git -C "$REPO_ROOT" remote get-url origin | sed -E 's|.*github.com[:/]([^/]+/[^/.]+)(\.git)?$|\1|')" \
    --branch main \
    --workflow build-check.yml \
    --limit 1 \
    --json status,conclusion,headSha \
    --jq '.[0] | "\(.status)|\(.conclusion)|\(.headSha)"' 2>/dev/null || echo "")"

  if [[ -z "$STATUS_LINE" ]]; then
    echo "  ⚠ No Build Check run found on main (the change may not have touched web/)." >&2
    echo "  ⚠ Proceeding without pre-flight verification." >&2
  else
    IFS='|' read -r CHECK_STATUS CHECK_CONCLUSION CHECK_SHA <<< "$STATUS_LINE"
    if [[ "$CHECK_SHA" != "$LATEST_MAIN" ]]; then
      echo "  ⚠ Most recent Build Check is for ${CHECK_SHA:0:7}, not current main $SHORT_SHA." >&2
      echo "  ⚠ A Build Check may still be running, or the latest commit didn't touch web/." >&2
      echo "  ⚠ Proceeding anyway; check https://github.com/$(git -C "$REPO_ROOT" remote get-url origin | sed -E 's|.*github.com[:/]([^/]+/[^/.]+)(\.git)?$|\1|')/actions if you want to confirm first." >&2
    elif [[ "$CHECK_STATUS" != "completed" ]]; then
      echo "ERROR: Build Check on $SHORT_SHA is still $CHECK_STATUS." >&2
      echo "       Wait for it to finish before deploying. Refusing to ship unverified." >&2
      exit 1
    elif [[ "$CHECK_CONCLUSION" != "success" ]]; then
      echo "ERROR: Build Check on $SHORT_SHA concluded as $CHECK_CONCLUSION." >&2
      echo "       Refusing to deploy. Investigate the failure first." >&2
      exit 1
    else
      echo "  ✓ Build Check green on $SHORT_SHA"
    fi
  fi
fi

# Run from REPO ROOT, not from web/. The Vercel project's "Root Directory"
# setting is configured as `web` in the dashboard — running from web/ would
# resolve the source path to <repo>/web/web/ which doesn't exist. Running
# from the repo root lets Vercel's project setting handle the subdirectory.
cd "$REPO_ROOT"

# ── Pre-flight: refuse if estimated upload exceeds size/count caps ────
# Vercel CLI uploads everything from cwd that isn't ignored by .vercelignore
# (or .gitignore as a fallback). A missing/incomplete .vercelignore + this
# repo's 19GB src/data/ cache once caused a ~17.6GB upload that hit Vercel
# API errors AND burned ~17.6GB of the operator's I/O quota before failing.
# This guard prevents recurrence: it estimates upload size using the same
# exclusion patterns as the repo-root .vercelignore, and refuses to launch
# vercel CLI if the estimate exceeds the cap.
#
# If you intentionally need a larger deploy, raise MAX_BYTES with comment
# explaining why. Don't disable this check — the failure mode it prevents
# is expensive (quota burn) AND silent (vercel CLI doesn't tell you the
# upload size until it's too late).
#
# Exclusions MUST be kept in sync with /.vercelignore — that file is what
# vercel CLI actually reads; the find expression below is just the
# pre-flight estimator. If you add a new top-level dir, update both.
echo "→ Estimating upload size (post-.vercelignore)..."
UPLOAD_BYTES=$(find . -type f \
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
  -not -path '*/node_modules/*' \
  -not -path '*/.next/*' \
  -not -name '*.pyc' -not -name '*.log' \
  -printf '%s\n' 2>/dev/null | awk '{s+=$1} END{print s+0}')

UPLOAD_FILE_COUNT=$(find . -type f \
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
  -not -path '*/node_modules/*' \
  -not -path '*/.next/*' \
  -not -name '*.pyc' -not -name '*.log' \
  2>/dev/null | wc -l)

MAX_BYTES=$((50 * 1024 * 1024))   # 50 MB cap — current web/ tree is ~3.5MB
MAX_FILES=2000                    # Soft cap; web/ has ~300 files

if (( UPLOAD_BYTES > MAX_BYTES )); then
  UPLOAD_MB=$((UPLOAD_BYTES / 1024 / 1024))
  CAP_MB=$((MAX_BYTES / 1024 / 1024))
  echo "ERROR: estimated upload size ${UPLOAD_MB}MB exceeds ${CAP_MB}MB cap." >&2
  echo "       Check .vercelignore at the repo root — likely missing or" >&2
  echo "       a large new top-level directory needs to be added to the ignore." >&2
  echo "       Refusing to deploy. This cap exists to prevent burning Vercel" >&2
  echo "       I/O quota on accidentally-included artifacts (data/, src/data/," >&2
  echo "       etc.). Origin: 17.6GB accidental upload on 2026-05-22." >&2
  exit 1
fi

if (( UPLOAD_FILE_COUNT > MAX_FILES )); then
  echo "ERROR: estimated file count $UPLOAD_FILE_COUNT exceeds $MAX_FILES cap." >&2
  echo "       Same diagnosis as the size cap — check .vercelignore." >&2
  exit 1
fi

UPLOAD_KB=$((UPLOAD_BYTES / 1024))
echo "  ✓ Estimated upload: ${UPLOAD_KB}KB across ${UPLOAD_FILE_COUNT} files (caps: 50MB / 2000 files)"

# ── Deploy ────────────────────────────────────────────────────────────
echo "→ Deploying $SHORT_SHA to production via vercel CLI..."

# --yes: skip the "set up new project?" prompt (we have project linkage
# via env vars, so this should never fire — but if vercel doesn't
# recognize the link for some reason, fail fast instead of hanging).
vercel --prod --yes

echo ""
echo "→ Deploy complete. Spot-check richmondcommons.org and a recently-changed page."
