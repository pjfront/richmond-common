# Supabase Preview Branch Runbook

Use this path when a pull request needs a live Vercel preview backed by its
own Supabase schema. It is explicit rather than automatic because each open
Supabase branch consumes billable compute. One bootstrap creates at most one
branch and never replaces it. Native Supabase deletion is the primary cost
boundary; PR-close cleanup and a trusted 90-minute sweep are backstops.

## One-time GitHub configuration

The `Supabase Preview` workflow requires:

- Actions secret `SUPABASE_ACCESS_TOKEN` — a fine-grained Supabase token with
  branch read/create/delete, project API-key read, and database query access.
- Actions secret `VERCEL_TOKEN` — scoped to the `rtp` Vercel project.
- Repository variable `VERCEL_PROJECT_ID`.
- Repository variable `VERCEL_ORG_ID`.

The Vercel IDs are public identifiers; the two tokens are secrets. Do not add
`DATABASE_URL`, a database password, a service-role/secret key, or any model,
email, operator, or session secret to this workflow.

`web/vercel.json` must remain set to Vercel's
[documented global switch](https://vercel.com/docs/project-configuration/git-configuration#turning-off-all-automatic-deployments)
`"git": { "deploymentEnabled": false }`. It disables every automatic Git
deployment while leaving explicit REST API, CLI, and Deploy Hook deployments
available. This is the control that contains ordinary PR pushes; the similarly
named `gitProviderOptions.createDeployments` setting is not a build-disable
control—the live probe still cloned, installed, and built with it disabled.

## Bootstrap a PR once

An ordinary PR push does not create a Vercel deployment at all because automatic
Git deployments are globally disabled in `web/vercel.json`; it therefore does
not consume a Supabase branch. After bootstrap and the schema/type comparison
succeed, the trusted-main controller requests one Vercel Preview through the
REST API with the exact approved branch and H0 SHA. If H0 needs the permitted
type-only H1, H0 is not deployed: the controller requests exact H1 only after
the separate H1 verification succeeds. The Ignored Build Step and build guard
then provide separate defenses: the ignored-build rule rejects the reserved
automation refs, while the build guard requires the exact branch+SHA marker and
isolated public Supabase values before the requested Preview can build.

The Ignored Build Step is automation-only defense in depth, not an approval or
automatic-deployment boundary. Exact Preview approval lives in the trusted REST
controller; its branch-owned build assertion is an independent last guard.
Vercel counts any deployment canceled by an Ignored Build Step as a full
deployment, and it occupies a concurrent-build slot while the command runs, as
documented in
[Project Settings](https://vercel.com/docs/project-configuration/project-settings#ignored-build-step).
The global Git switch is what prevents ordinary pushes from consuming those
limits.

No human timer is the cost boundary. Immediately after clean-room proof, the
controller requests native soft deletion with `DELETE ...?force=false`, re-reads
the immutable branch UUID/ref, and requires `deletion_scheduled_at` no later
than two hours after `created_at` before any Vercel request. Missing,
unsupported, ambiguous-unproven, or late scheduling fails closed and
hard-deletes the exact branch. A trusted-main scheduled sweep runs every five
minutes and hard-deletes only exact non-persistent, non-default
`pr-<N>-preview` branches at least 90 minutes old as an outage backstop.

Run the workflow for an open same-repository PR:

```bash
gh workflow run supabase-preview.yml \
  -f action=bootstrap \
  -f pr_number=<PR_NUMBER> \
  -f source_head_sha=<EXACT_CURRENT_H0_SHA>
```

Bootstrap refuses an existing branch for that PR; it never replaces, resets,
or retries branch creation. This enforces the one-create cost approval and also
prevents a stale PR-named environment from being silently rebound. The controller
creates a non-persistent, data-less
branch with `with_data=false`, waits for the database itself to answer, restores
the reviewed Preview baseline, applies only the contiguous post-baseline
migration suffix that is genuinely absent, and verifies exact ledger parity.
Supabase may finish cloning already-live post-baseline schema and ledger rows
after the baseline transaction. The controller re-reads the ledger before
every migration, accepts that race only for exact versions already proven in
trusted production, and never replays those inherited migrations.

The controller comes from trusted `main`. The PR checkout is separate and is
never executed; only `preview-head/supabase/migrations/*.sql` is read as input.
Fork PRs are rejected before either control-plane token enters a step.

## Trusted clean-room baseline

Supabase branches do not copy production data, and Richmond's foundational
schema predates its tracked migration ledger. A clean database therefore starts
from the committed, schema-only artifact in `supabase/preview-baseline/`. Its
manifest fixes the production ledger cutoff at `20260807013300`, records the
schema hash and catalog inventory, and records the canonical SHA-256 hash of
every absorbed migration. Canonical text is UTF-8 without a BOM, with CRLF and
bare CR normalized to LF; all other bytes are preserved.

Both the baseline and lifecycle controller come from trusted `main`. Before
creating a branch, the controller requires production's live ledger through the
cutoff to match the manifest exactly, including the two documented historical
ledger-name aliases. It independently requires both trusted-main and PR copies
of all absorbed migrations to match the manifest's filenames and hashes. A PR
can add a migration after the cutoff, but it cannot rewrite the schema history
that the baseline represents.

Restore is allowed only after the controller proves the immutable project is
the expected non-default, non-persistent Preview branch and proves its public
application catalog is empty. In one database transaction it then drops the
empty `public` schema, applies the non-idempotent schema artifact, verifies the
manifest's exact catalog counts and pinned extension versions/schemas, creates
the CLI-compatible migration ledger, and records the absorbed migration prefix.
If any check fails, the transaction rolls back. The mutating endpoint must
execute as `postgres`; the controller also verifies the owners of public
relations, routines, and the exact `ensure_rls` event-trigger definition so
`SECURITY DEFINER` and automatic-RLS behavior cannot drift.

Preview migrations execute as `postgres`. The baseline therefore preserves
all three `postgres`-owned default-privilege rows (sequences, functions, and
tables) and every grant in those groups. Production also has three equivalent
rows owned by `supabase_admin`, but PostgreSQL does not permit `postgres` to
alter another role's default privileges in the branch query endpoint. Those
three groups are the one allowed schema-parity exception: they are omitted from
the executable Preview artifact and recorded exactly in the manifest as a
permission-boundary exception for object types `S`, `f`, and `r`. The loader
rejects any additional or modified parity exception.

The second and only other parity exception is the `vector` extension version.
Production remains on `0.8.0`, while the Supabase branch control plane resolves
an explicitly requested `0.8.0` install to its branch runtime version `0.8.2`.
The executable Preview baseline and post-restore catalog check therefore require
`vector 0.8.2` in the `extensions` schema, and the manifest records production
`0.8.0` versus Preview `0.8.2` with reason `supabase_branch_runtime`.
`pgcrypto 1.3` and `uuid-ossp 1.1` retain exact production parity. The loader
requires these two parity exceptions in order and rejects variants or additions.
Any migration that touches vector types, operator classes, or extension functions
needs a separate production-`0.8.0` compatibility preflight before deployment.

The baseline intentionally uses `CREATE SCHEMA public`, not `IF NOT EXISTS`;
inside the controller's transaction, an existing schema makes the restore fail
and roll back before extension or application DDL runs. Never run the artifact
directly with `psql`: clients without stop-on-error semantics may continue after
an individual statement failure.

Only migrations newer than `20260807013300` are then applied, one atomic
migration-plus-ledger write at a time. Migration 134's
`source_reconciliation_enforcement` plan is explicitly non-replayable; its
name (and reserved `20260807013400` identity) fails before branch creation.
The final ledger must equal the exact PR head's complete timestamp/name
sequence before any Vercel
environment variables are written. The baseline contains structure only—no
production rows, auth users, credentials, or migration-ledger data.

This clean-room branch validates schema and application compatibility. It does
not prove that a data-dependent backfill, cleanup, or new constraint will work
against production rows: `UPDATE` and `DELETE` migrations are no-ops on an
empty branch. Those changes still require synthetic fixtures or a separate
read-only production-data preflight before production approval.

## Schema/type merge gate

`Schema Drift` runs from trusted `main` under `pull_request_target`. It checks
out the exact same-repository PR head into `preview-head/` and treats its SQL
and committed `database.types.ts` only as inert inputs. No PR package script or
controller code runs with production credentials.

The trusted controller compares the exact PR migration history to the read-only
production ledger. When that exact head has no pending migrations, production
type generation remains authoritative and is compared directly with the PR's
committed `web/src/lib/database.types.ts`. When migrations are pending, the
gate requires the `Schema Type Gate` commit status on that exact head SHA.

A successful manual `Supabase Preview` bootstrap generates `public` database
types from the verified clean-room branch and compares them byte-for-byte with
exact head H0. A matching H0 receives success and the trusted controller
requests its exact-SHA REST API Preview. A type mismatch uploads the generated
file as a seven-day H0-SHA-named artifact, leaves failure on H0, does not request
a Vercel deployment, and retains that same immutable branch only for the bounded
type-only follow-up. Every validation, bootstrap, type-generation, size/path,
artifact, or deployment-request failure instead cleans immediately.

Download the H0-bound artifact, replace only
`web/src/lib/database.types.ts`, and create H1 as one normal, one-parent commit
directly on H0. Do not amend, merge, rebase, or change migrations/baseline files.
Then dispatch:

```bash
gh workflow run supabase-preview.yml \
  -f action=verify-types \
  -f pr_number=<PR_NUMBER> \
  -f source_head_sha=<H0_SHA>
```

The trusted-main controller resolves the same-repository open PR's exact H1,
requires H1's only parent to be H0, requires the GitHub H0..H1 file list to be
exactly one non-renamed modification of `web/src/lib/database.types.ts`, and
independently requires byte-identical migration and Preview-baseline path/blob
inventories in inert H0/H1 checkouts. It rejects symlinks, reparse points, path
escape, and files over 2 MB. It then proves that the retained branch and exact
Vercel variable set are still non-default/non-persistent, bound to H0, and no
more than two hours old. Supabase verification is read-only except for type
generation: it never creates/replaces a branch or applies a migration. Failure
cleans and writes failure only to H1. On success, the controller writes success
only to H1, rebinds the
five exact-branch Vercel identity variables from H0 to the verified H1 SHA, and
requests that exact H1 through Vercel's REST API. The Supabase branch remains
read-only and is retained solely for browser verification until native or
explicit cleanup. Unknown
ledger versions, name/hash drift, history holes, security inventory regressions,
and Vercel deployment-request failures remain fail-closed.

### PR #88 handoff

PR #88 must consume this gate only after the infrastructure PR is merged to
`main`; it must not copy controller/workflow changes into its product branch.
At that point, treat PR #88's then-current exact head as H0 and dispatch one
bootstrap with that H0. If H0 fails
only the type comparison, download its H0-SHA artifact and make the very next
commit change only `web/src/lib/database.types.ts`. That commit is H1. Do not
amend, rebase, merge, or push any other file before dispatching `verify-types`
with the recorded H0. After H1 succeeds, complete browser verification and
dispatch cleanup before the timer expires. Any additional product change makes
a new head that cannot reuse this retained environment.

## Preview environment contract

Five identity variables are created with both `target=preview` and the PR's
exact Git branch:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` (a verified publishable or legacy `anon` key)
- `RICHMOND_PREVIEW_GIT_BRANCH`
- `RICHMOND_PREVIEW_SUPABASE_REF`
- `RICHMOND_PREVIEW_SOURCE_HEAD_SHA` (the exact approved deployment SHA: H0 or
  the separately verified type-only H1)

Three controller-owned lifecycle markers are written with the identity set:
`RICHMOND_PREVIEW_PR_NUMBER`, the immutable `RICHMOND_PREVIEW_CREATED_AT`, and
the exact `RICHMOND_PREVIEW_PARENT_REF`. They let the scheduled backstop
identify, parent-attest, and age the exact state even after native Supabase
deletion has already removed the branch. Immediately after Vercel accepts the
request, before polling begins, a fourth state variable is added at the same scope:
`RICHMOND_PREVIEW_DEPLOYMENT_ID`. It lets TTL and PR-close cleanup attest,
cancel when necessary, and delete the exact deployment before environment
state or controller-driven Supabase cleanup.

The controller first lists exact branch+Preview rows, deletes those rows by
immutable Vercel environment-variable ID, and then creates replacements. It
never uses name-only upsert: Production and Preview legitimately have duplicate
key names, so name-only mutation is ambiguous. The Vercel build guard checks
the branch marker, exact Git SHA marker, project-ref marker, URL hostname, and
public-key shape in addition to rejecting every server credential. The trusted
controller sends explicit `target=preview` plus that exact branch and SHA in the
REST API `gitSource`. It polls the immutable deployment to terminal `READY` and
requires the returned project ID, Preview target, GitHub owner/repository/ref/
full SHA metadata, and Git source to match. Missing or mismatched fields fail
closed; failure or timeout cancels and deletes only that attested deployment.

## Cleanup

Merging or closing a PR triggers cleanup through `pull_request_target` using
the trusted `main` controller. Manual cleanup is also available:

```bash
gh workflow run supabase-preview.yml \
  -f action=cleanup \
  -f pr_number=<PR_NUMBER>
```

Run it earlier after browser verification. A successful `verify-types` result
does not cancel or extend Supabase's native deadline. The scheduled 90-minute
sweep is a trusted outage backstop, not a replacement for native deletion.

Cleanup validates the expected parent, PR name, Git branch, `persistent=false`,
and `is_default=false`. When deployment state exists, it first re-attests and
cancels/deletes that exact Vercel deployment. It then removes exact Vercel
branch targets by immutable environment-variable ID and deletes the Supabase
branch by its immutable project ref, verifying that the original UUID/ref
disappears.

The order is deliberate: Vercel routing is removed first so a concurrent build
fails closed instead of targeting a branch during deletion. Supabase deletion
still runs if Vercel cleanup fails, so an expired Vercel token cannot leave
billable branch compute running; the workflow then fails loudly until the stale
Vercel rows are cleaned.

## Known control-plane quirks covered

- A controller-created branch can retain Supabase's top-level
  `status=MIGRATIONS_FAILED` after the platform's built-in migration action
  fails on Richmond's pre-ledger history, even though the database later reports
  `preview_project_status=ACTIVE_HEALTHY` and the controller's clean-room restore
  succeeds. Supabase's deployment workflow treats service health and migration
  execution as separate steps. Neither field is an acceptance signal by itself.
  After the complete migration suffix runs, the controller rechecks exact ledger
  parity plus RLS coverage, object ownership, the `ensure_rls` event trigger,
  default-privilege row count, and pinned extensions. It then re-reads the exact
  immutable ref/UUID and safety flags before publishing any Vercel routing.
  Supabase's [generated API schema](https://github.com/supabase/supabase/blob/master/packages/api-types/types/api.d.ts)
  marks the branch `status` field deprecated. On
  2026-08-08, its documented branch-config status override returned HTTP 200 for
  both the exact project ref and UUID but explicitly returned and retained
  `MIGRATIONS_FAILED`. The controller therefore neither mutates nor gates on that
  historical workflow field. Do not call branch `reset`, `push`, or the ongoing
  action-status endpoint merely to clear the badge: those are different mutation
  workflows and do not replace the controller's verified postconditions. If a
  postcondition or identity read-back fails, the controller rejects and replaces
  the Preview instead.
- Supabase CLI 2.112.0 failed parsing branch timestamps containing `+00:00`.
  Lifecycle state therefore comes from the Management API, whose timestamps
  accept both `Z` and explicit UTC offsets.
- Create/delete HTTP failures are ambiguous. Mutations are never blindly
  retried; the controller reconciles the immutable UUID/project ref first.
- Migration ledger versions must be the exact 14-digit timestamp from the
  committed `supabase/migrations/` filename. Numeric aliases such as `134` are
  rejected before any branch is created.
- The schema baseline and absorbed migration prefix are hash-pinned. Missing,
  edited, reordered, symlinked, oversized, or path-escaping inputs fail before
  any branch mutation.
- Baseline SQL rejects top-level data DML, explicit transaction wrappers, psql
  meta-commands, and credential-shaped strings. DML inside stored function
  bodies is parsed as quoted function code and does not create false positives.
- A migration with its own `BEGIN`/`COMMIT` wrapper is rejected by this direct
  Management API path rather than risking a schema change and ledger insert in
  separate transactions. Review it and remove the redundant wrapper or use a
  pinned CLI path deliberately.

## Local validation (no network)

```bash
python src/supabase_preview.py validate \
  --migrations-dir supabase/migrations \
  --migrations-root . \
  --baseline-dir supabase/preview-baseline
```

The lifecycle commands intentionally do not load `.env`; tokens must be
provided explicitly by the caller. This prevents a local production database
URL or service-role credential from entering the Preview path by ambient
configuration.
