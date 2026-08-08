# Supabase Preview Branch Runbook

Use this path when a pull request needs a live Vercel preview backed by its
own Supabase schema. It is explicit rather than automatic because each open
Supabase branch consumes billable compute. PR close/merge cleanup is automatic.

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

## Bootstrap or refresh a PR

Run the workflow for an open same-repository PR:

```bash
gh workflow run supabase-preview.yml \
  -f action=bootstrap \
  -f pr_number=<PR_NUMBER>
```

Bootstrap always replaces an older branch for that PR. This is intentional:
editing an already-recorded migration cannot be made reliable by replaying it
against a dirty branch. The controller creates a non-persistent, data-less
branch with `with_data=false`, waits for the database itself to answer, restores
the reviewed Preview baseline, applies only the contiguous post-baseline
migration suffix, and verifies exact ledger parity.

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
migration-plus-ledger write at a time. The final ledger must equal the PR's
complete timestamp/name sequence before any Vercel environment variables are
written. The baseline contains structure only—no production rows, auth users,
credentials, or migration-ledger data.

This clean-room branch validates schema and application compatibility. It does
not prove that a data-dependent backfill, cleanup, or new constraint will work
against production rows: `UPDATE` and `DELETE` migrations are no-ops on an
empty branch. Those changes still require synthetic fixtures or a separate
read-only production-data preflight before production approval.

## Preview environment contract

Exactly four Vercel variables are created with both `target=preview` and the
PR's exact Git branch:

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY` (a verified publishable or legacy `anon` key)
- `RICHMOND_PREVIEW_GIT_BRANCH`
- `RICHMOND_PREVIEW_SUPABASE_REF`

The controller first lists exact branch+Preview rows, deletes those rows by
immutable Vercel environment-variable ID, and then creates replacements. It
never uses name-only upsert: Production and Preview legitimately have duplicate
key names, so name-only mutation is ambiguous. The Vercel build guard checks
the branch marker, project-ref marker, URL hostname, and public-key shape in
addition to rejecting every server credential.

## Cleanup

Merging or closing a PR triggers cleanup through `pull_request_target` using
the trusted `main` controller. Manual cleanup is also available:

```bash
gh workflow run supabase-preview.yml \
  -f action=cleanup \
  -f pr_number=<PR_NUMBER>
```

Cleanup validates the expected parent, PR name, Git branch, `persistent=false`,
and `is_default=false`. It then removes exact Vercel branch targets by immutable
environment-variable ID and deletes the Supabase branch by its immutable
project ref, verifying that the original UUID/ref disappears.

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
  immutable ref/UUID and safety flags before using Supabase's supported
  branch-config override to set only `status=MIGRATIONS_PASSED`. A final read-back
  confirms the immutable identity and exact status without retrying an ambiguous
  mutation. This metadata update does not execute SQL or rewrite the failed
  action-run audit record, and it never asserts `FUNCTIONS_DEPLOYED`. Do not call
  branch `reset`, `push`, or the ongoing-action status endpoint merely to clear a
  badge. If a postcondition or read-back fails, the controller rejects and
  replaces the Preview instead.
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
