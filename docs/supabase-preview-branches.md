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
against a dirty branch. The controller creates a non-persistent branch with
`with_data=false`, waits for the database itself to answer, applies only the
contiguous pending migration suffix, and verifies exact ledger parity.

The controller comes from trusted `main`. The PR checkout is separate and is
never executed; only `preview-head/supabase/migrations/*.sql` is read as input.
Fork PRs are rejected before either control-plane token enters a step.

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

- Supabase CLI 2.112.0 failed parsing branch timestamps containing `+00:00`.
  Lifecycle state therefore comes from the Management API, whose timestamps
  accept both `Z` and explicit UTC offsets.
- Create/delete HTTP failures are ambiguous. Mutations are never blindly
  retried; the controller reconciles the immutable UUID/project ref first.
- Migration ledger versions must be the exact 14-digit timestamp from the
  committed `supabase/migrations/` filename. Numeric aliases such as `134` are
  rejected before any branch is created.
- A migration with its own `BEGIN`/`COMMIT` wrapper is rejected by this direct
  Management API path rather than risking a schema change and ledger insert in
  separate transactions. Review it and remove the redundant wrapper or use a
  pinned CLI path deliberately.

## Local validation (no network)

```bash
python src/supabase_preview.py validate \
  --migrations-dir supabase/migrations
```

The lifecycle commands intentionally do not load `.env`; tokens must be
provided explicitly by the caller. This prevents a local production database
URL or service-role credential from entering the Preview path by ambient
configuration.
