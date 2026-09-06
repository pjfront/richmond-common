# Supabase Preview Branch Runbook

Use this path when a pull request needs a live Vercel preview backed by its
own Supabase schema. It is explicit rather than automatic because each open
Supabase branch consumes billable compute. The controller permits at most one
Richmond Preview branch total and never replaces it. Lifecycle and 90-minute
expiry jobs share one non-cancelling concurrency group with `queue: max`, which
serializes their control-plane mutations while retaining up to 100 pending runs
instead of silently replacing GitHub's default single pending run. Bootstrap
proves the singleton both before and after creation. A separate completed-run
watchdog deliberately does not join that concurrency group or write commit
statuses. PR-close cleanup, the trusted 90-minute sweep, and the independent
110-minute watchdog are the automatic hard-delete layers.

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

No human timer is the normal-operation cost boundary. Supabase's native
`DELETE ...?force=false` is intentionally forbidden for an active Preview:
the one-hour soft-deletion grace period makes the project inactive immediately,
so API-key access and CLI type generation fail even though hard deletion is
deferred. After clean-room proof, the controller instead re-reads the same
immutable UUID/ref until the authoritative `preview_project_status` is
`ACTIVE_HEALTHY`; it never uses the deprecated top-level `status` as service
health. Replacement, timeout, or an unsafe record fails closed and invokes
exact hard cleanup before Vercel state is written.

A fresh database can restart after its first successful `SELECT 1`. Subsequent
Management API read-only queries retry only the API's explicit connection
termination message or leading PostgreSQL `FATAL` codes `57P01` and `57P03`.
They use at most four requests with 2/4/8-second delays, and no retry starts
after 30 seconds. An in-flight HTTP request retains its existing 120-second
timeout. Writes, permission/syntax errors, malformed responses, and unrelated
transport failures are not retried. Exhaustion preserves the original error
and enters the existing exact-branch cleanup path.

A trusted-main scheduled sweep runs every five minutes and hard-deletes only
exact non-persistent, non-default `pr-<N>-preview` branches at least 90 minutes
old. Independently, `Supabase Preview Watchdog` starts only from a completed
bootstrap run, validates the exact run title and GitHub API identity before
credentials enter a step, and snapshots the sole immutable branch whose
`created_at` lies inside that run's start/completion window. It waits only until
no earlier than `created_at + 110 minutes`, then hard-deletes that exact UUID/ref.
The shell timer adds a one-second integer cushion because its epoch conversion
truncates fractional timestamps; ordinary shell scheduling may run slightly
later, and the Python cleanup still enforces the precise lower bound. Missing
state is a successful no-op; a replacement is never deleted.
These layers make the
approved two-hour lifetime the intended normal-operation ceiling. A vendor-wide
GitHub Actions outage can stop both timers, so this is not a mathematical
guarantee during that external outage; PR-close/manual cleanup remains available.

A retained H0 is eligible to enter the type-only H1 path only while it is less
than 70 minutes old, and the controller rechecks that same ceiling immediately
before any H1 Vercel rebind or deployment request. The lifecycle job itself has
a 35-minute timeout. The 70-minute admission ceiling therefore reserves 40
minutes before the independent 110-minute watchdog: the entire job must end at
least five minutes before that watchdog can delete the branch. The 90-minute
expiry sweep shares lifecycle concurrency and queues behind an admitted H1; the
watchdog remains independent without overlapping a legitimately admitted H1.

Send the typed repository event for an open same-repository PR. Unlike a
branch-selectable `workflow_dispatch`, `repository_dispatch` always runs the
workflow at the default-branch SHA/ref, so an older or edited feature-branch
workflow cannot reach these credentials. Use an authenticated GitHub CLI login
with write access to this repository:

```powershell
$prNumber = 123 # replace with the PR number
$sourceHeadSha = '<EXACT_CURRENT_H0_SHA>'
gh api --method POST repos/pjfront/richmond-common/dispatches `
  -f event_type=supabase-preview-lifecycle `
  -f 'client_payload[action]=bootstrap' `
  -F "client_payload[pr_number]=$prNumber" `
  -f "client_payload[source_head_sha]=$sourceHeadSha"
```

Bootstrap refuses any other exact controller-owned `pr-<N>-preview` branch and
refuses an existing branch for that PR; it never replaces, resets, or retries
branch creation. The public CLI intentionally has no `--replace` option. This
enforces the one-Micro-branch cost approval and also
prevents a stale PR-named environment from being silently rebound. The controller
creates a non-persistent, data-less
branch with `with_data=false` and `desired_instance_size=micro`, waits for the database itself to answer, restores
the reviewed Preview baseline, applies only the contiguous post-baseline
migration suffix that is genuinely absent, and verifies exact ledger parity.
Supabase may finish cloning already-live post-baseline schema and ledger rows
after the baseline transaction. The controller re-reads the ledger before
every migration, accepts that race only for exact versions already proven in
trusted production, and never replays those inherited migrations.
After the final security inventory and immutable identity re-read, it polls the
same UUID/ref until `preview_project_status=ACTIVE_HEALTHY` before reading API
keys or writing Vercel state. A same-name replacement never satisfies that poll.

The controller comes from trusted `main`. The PR checkout is separate and is
never executed; only `preview-head/supabase/migrations/*.sql` is read as input.
Fork PRs are rejected before either control-plane token enters a step. The
current Supabase Management API accepts `desired_instance_size` on create, but
its documented branch create/list/read response schemas do not expose compute
size. The controller therefore sends Micro explicitly and rejects any explicit
future response field that reports a different size; absence is the documented
API limitation, not evidence of a larger size.
If any create/list/read response explicitly reports `with_data=true` (or an
invalid `with_data` state), the controller never restores or deploys it. It
keeps the immutable identity only long enough to hard-delete that exact branch;
a later response omitting the field cannot erase the explicit violation.

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
types from both the verified clean-room branch and production. Preview is
authoritative for every schema/type byte; production is authoritative only for
the hosted `__InternalSupabase.PostgrestVersion` value used by the eventual
public runtime. The trusted controller requires one exact, canonical metadata
header in each generated file, requires matching PostgREST major versions, and
composes the Preview schema with only production's version literal. It then
compares that canonical file byte-for-byte with exact head H0. A matching H0
receives success and the trusted controller requests its exact-SHA REST API
Preview. A real schema mismatch uploads the canonical file as a seven-day
H0-SHA-named artifact, leaves failure on H0, does not request a Vercel
deployment, and retains that same immutable branch only for the bounded
type-only follow-up. Missing, duplicate, malformed, differently formatted, or
major-incompatible metadata is not retainable and cleans immediately, as does
every validation, bootstrap, type-generation, size/path, artifact, or
deployment-request failure.

Both H0 and H1 use the same trusted generators and compositor. Preview typegen
retries for at most 120 seconds only when the CLI's complete error is exactly
`Project must be active and healthy`. The production metadata generation is one
read-only, hard-coded call with no mutation path and no retry. For bootstrap it
runs before the bootstrap can create a billable branch, so a production read failure
cannot consume an approved Preview. HTTP 401/403,
credential failures, CLI failures, malformed metadata, and every unrelated
response fail immediately. Composition asserts mechanically that no Preview
byte outside the single quoted version span changed. An H1 mismatch is diffed
with bounded output; after cleanup completes, its canonical diagnostic artifact
is retained for seven days when available.

Download the H0-bound artifact, replace only
`web/src/lib/database.types.ts`, and create H1 as one normal, one-parent commit
directly on H0. Do not amend, merge, rebase, or change migrations/baseline files.
Then send the trusted typed event:

```powershell
$prNumber = 123 # replace with the PR number
$sourceHeadSha = '<H0_SHA>'
gh api --method POST repos/pjfront/richmond-common/dispatches `
  -f event_type=supabase-preview-lifecycle `
  -f 'client_payload[action]=verify-types' `
  -F "client_payload[pr_number]=$prNumber" `
  -f "client_payload[source_head_sha]=$sourceHeadSha"
```

The trusted-main controller resolves the same-repository open PR's exact H1,
requires H1's only parent to be H0, requires the GitHub H0..H1 file list to be
exactly one non-renamed modification of `web/src/lib/database.types.ts`, and
independently requires byte-identical migration and Preview-baseline path/blob
inventories in inert H0/H1 checkouts. It rejects symlinks, reparse points, path
escape, and files over 2 MB. It then proves that the retained branch and exact
Vercel variable set are still non-default/non-persistent, `ACTIVE_HEALTHY`,
bound to H0, and less than 70 minutes old. Supabase verification is read-only except for type
generation: it never creates/replaces a branch or applies a migration. Failure
cleans and writes failure only to H1. On success, the controller writes success
only to H1, rebinds the
five exact-branch Vercel identity variables from H0 to the verified H1 SHA, and
requests that exact H1 through Vercel's REST API. The Supabase branch remains
read-only and is retained solely for browser verification until explicit,
90-minute sweep, or 110-minute watchdog cleanup. Unknown
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
identify, parent-attest, and age the exact state even after lifecycle cleanup
has already removed the branch. Immediately after Vercel accepts the
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
controller omits the deployment `target` in the REST request so Vercel creates
its built-in Preview environment, while sending the exact branch and SHA in
`gitSource`. Vercel's returned deployment must contain explicit `target: null`,
the canonical built-in Preview value; missing and non-null targets fail closed.
Branch-scoped environment variables separately retain their `target=preview`
scope. The controller polls the immutable deployment to terminal `READY` and
requires the returned project ID, Preview target, GitHub owner/repository/ref/
full SHA metadata, Git source, and a creation time inside the current request
window to match before persisting its ID. Missing, stale, future, or mismatched
fields are reconciled by one bounded exact-identity list read without replaying
the POST. Failure or timeout cancels and deletes only a fully attested deployment.

## Cleanup

Merging or closing a PR triggers cleanup through `pull_request_target` using
the trusted `main` controller. Manual cleanup is also available:

```powershell
$prNumber = 123 # replace with the PR number
gh api --method POST repos/pjfront/richmond-common/dispatches `
  -f event_type=supabase-preview-lifecycle `
  -f 'client_payload[action]=cleanup' `
  -F "client_payload[pr_number]=$prNumber"
```

Run it earlier after browser verification. A successful `verify-types` result
does not reset or extend the immutable creation time. The scheduled 90-minute
sweep and independent completed-bootstrap watchdog remain anchored to the
original branch `created_at`.

Cleanup validates the expected parent, PR name, Git branch, `persistent=false`,
and `is_default=false`. When deployment state exists, it first re-attests and
cancels/deletes that exact Vercel deployment. It then removes exact Vercel
branch targets by immutable environment-variable ID and deletes the Supabase
branch by its immutable project ref, verifying that the original UUID/ref
disappears.

The expiry sweep and watchdog carry the selected Supabase UUID/project ref and
an immutable snapshot of every Vercel environment-variable ID and lifecycle
marker through the mutation boundary. They re-read both immediately before cleanup. If either
was removed or replaced after inventory, the sweep mutates neither replacement;
the next freshly inventoried pass decides whether the new state is actually stale.
The immutable checks remain a second safety boundary in case control-plane state
is replaced outside the serialized trusted workflows. Any lifecycle/expiry
cancellation is therefore exceptional and remains operator-actionable.

The order is deliberate: Vercel routing is removed first so a concurrent build
fails closed instead of targeting a branch during deletion. Supabase deletion
still runs if Vercel cleanup fails or the Vercel credential/IDs are absent, so
an expired or missing Vercel token cannot leave billable branch compute running.
The workflow then fails with an `ACTION:` line until the stale Vercel rows are
cleaned. This delete-first fail-safe applies to both the 90-minute expiry sweep
and the independent 110-minute watchdog.

## Known control-plane quirks covered

- A controller-created branch can retain Supabase's top-level
  `status=MIGRATIONS_FAILED` after the platform's built-in migration action
  fails on Richmond's pre-ledger history, even though the database later reports
  `preview_project_status=ACTIVE_HEALTHY` and the controller's clean-room restore
  succeeds. Supabase's deployment workflow treats service health and migration
  execution as separate steps. The deprecated top-level field is ignored;
  `preview_project_status=ACTIVE_HEALTHY` is required, but never accepted by
  itself without the clean-room schema/security and immutable-identity proofs.
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
  postcondition or identity read-back fails, the controller rejects and cleans
  only the exact immutable Preview state. Any later bootstrap is a separate,
  explicitly approved action; this controller never replaces a branch.
- The `workflow_run` watchdog can act only when the trusted title and GitHub API
  prove the bootstrap PR and the branch creation time falls inside that exact
  run window. If GitHub cannot supply those proofs, it fails closed without
  credentials or mutation and the 90-minute cron remains authoritative. A
  vendor-wide Actions outage can delay both automatic layers; use exact manual
  cleanup after service returns rather than claiming a hard external guarantee.
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
