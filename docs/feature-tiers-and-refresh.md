# Reversible feature tiers and deterministic refresh

October 4, 2026. The shared control file is `web/src/data/feature-tiers.json`; the web consumer and Python workers read the same feature/capability switches. Changing visibility never deletes the archive. Source records, downloaded originals, saved generated explanations, and the verified recovery dump remain separately retained. Public basic is a compact projection, not the canonical recovery copy.

## Profiles and current capabilities

| Profile | Visible records | Initially enabled work | Initially disabled work |
|---|---|---|---|
| `basic_public` (public default) | Search, meetings/items, topic tags within records, preserved votes, money/source links, public exports | Explicit deterministic agenda, keyword tags, electronic finance refresh | Expanded archive pages, generated explanations, semantic/related retrieval, inference, embeddings, OCR, email, resident accounts |
| `local_archive` (explicit localhost default) | Core plus restored deep records, analysis pages, saved summaries/reports, local tool directory | Same deterministic refreshes against the isolated local restore | All new inference, embeddings, OCR, email/accounts; similar discussions until a compatible index exists |
| `local_ai` | Same restored archive | Deterministic refresh only at present | A local provider adapter and verified model/index compatibility must be implemented before optional AI can run |
| `cloud_ai` | Core and saved explanations | Deterministic refresh only at present | All provider capabilities remain false; provider configuration and enforced positive budgets are additional prerequisites |

`allowPaid` describes eligibility, not a running service. All four profiles start with `inference`, `embeddings`, `ocr`, `email`, and `accounts` false. An explicitly configured `RICHMOND_FEATURE_PROFILE` also gates legacy `LLMClient`, budget reservation, and embedding generation before provider requests. Without that variable, legacy callers retain their existing provider and budget behavior. The existing hard API budget lock remains independent and must remain `true` for basic/local operation.

Future AI activation requires an actual provider adapter, credentials or a local model process, capability/provider guards, and (for retrieval) compatible embedding dimensions and an index built with the same model. A JSON toggle alone does not create those services. The restored PostgreSQL 17 archive does not currently have pgvector available; similar discussions stay off. Operator/site authentication is separate from optional resident accounts; feature visibility never grants operator access.

## Feature catalog

| Group | Features and existing entry points |
|---|---|
| Record core | Search `/search`, exact `/api/commons/search` and `/api/search`; meetings `/meetings`; items `/meetings/*/items/*`; recorded votes and source links embedded in those records; money `/money`; finance export `/api/finance/export` |
| Local core extensions | Topic browse `/topics`; legacy donor profiles `/donors`. These are `localRoutes`, not exposed merely because basic topic/finance flags are true. |
| Deep records | Council `/council`; elections `/elections`; commissions `/commissions`; public requests `/public-records`; organizations `/orgs`, `/pac`, `/unions`, `/corporations`; reviewed stories `/stories` |
| Archived source datasets | Contracts, expenditures, permits, payroll, neighborhoods, Form 700 and behested-payment records remain archived; standalone routes for these datasets are not implemented. |
| Analysis | `/council/analytics`, `/meetings/most-discussed`, `/influence`, `/financial-connections`, `/data-quality`, private `/operator`; associated local read APIs are explicitly listed in `localRoutes`. |
| Saved AI | Local `/reports` and `/updates` read saved artifacts; semantic search and similar discussions are separate initially disabled features. |
| Communication | `/subscribe` and email APIs are optional and off; resident account UI is not implemented. |

Route checks use the longest matching route, so `/council/analytics` cannot borrow `/council` rights and `/meetings/most-discussed` cannot borrow `/meetings` rights. APIs are exact endpoints; suffixes do not inherit access. Authentication and per-route protections remain in force.

## Inspect or refresh locally

Installed Python requirements and the restored current schema/seeds are required. A plan performs no network/database requests, reads no production dotenv and does not open runtime credentials:

```powershell
python src/basic_refresh.py --plan
python scripts/local-runtime/refresh_local.py --plan
```

The local wrapper hands the existing restricted runtime PostgreSQL password directly to a child environment and never prints a URI/password. It accepts only the configured loopback restore, sets the local profile and budget lock, and passes no inherited provider credentials. Start the local runtime first, then explicitly apply a bounded refresh:

```powershell
python scripts/local-runtime/refresh_local.py --apply --steps agenda tags --agenda-mode source-links --agenda-limit 10 --tag-limit 2000
python scripts/local-runtime/refresh_local.py --apply --steps finance --year 2026 --through 2026-11-03
```

The full local agenda writer retains original documents and requires every declared attachment download before accepting a revision. A failed attachment download preserves prior structured records; it does not establish an empty agenda. The October 4 bounded check encountered four incomplete attachment sets and correctly refused those revisions. Do not interpret that attempted source check as a successful agenda refresh. The compact source-link writer does not depend on binary downloads.

The explicit local source-link pass succeeded on October 4: five official meetings observed, 139 agenda item writes, zero retired items, one minutes-owned row preserved, and one pending source observation. Two thousand recent keyword rows were then reconciled with 80 assignment writes. A replay after the final completeness guards observed the same five meetings and made zero agenda item writes. The bounded electronic finance pass succeeded with 1,551 assertions, 1,424 current events and 15 Form 496 source PDFs, zero model calls, through the reviewed November 3 query horizon. These are bounded source-check results, not proof of complete votes/papers. Archived binaries/attachments/votes and the original dump were retained. `/library` is a directory of restored tools; a local PDF browser is not implemented. Original files remain in the separately verified backup directories.

The optional `--agenda-mode archive-full` uses only `sync_escribemeetings(..., sync_type='incremental', limit=...)`, not the mixed `data_sync` enrichment DAG. Both modes check the past-60/next-14-day window. Keyword tagging is bounded to the configured recent item count; only keyword-owned projections are reconciled. Manual/generated tags and un-attributed saved labels remain preserved; subsequent labels proven to be created by this writer can be updated deterministically. Finance uses the bounded transport adapter around `finance_sync.acquire_snapshot` and requires `model_calls=0` before the archive writer persists a complete acquisition. Numeric paper extraction, transcripts, new vote extraction, enrichment, embeddings, OCR, email and source-change dispatch are outside this runner. Counts/date horizons are included in safe aggregate reports; the original recovery dump is untouched.

## Compact public updater

`src/basic_core_refresh.py` uses the existing pure portal parser with a bounded calendar response (4 MB), bounded HTML responses (2 MB each), at most 20 meetings and 250 items per meeting, and an 8 MB normalized batch limit. It never fetches or stores agenda PDFs, attachment text, raw assertion JSON or vectors. Official portal URLs retain access to source attachments. Oversized/ambiguous inventories fail rather than silently truncating successful coverage.

The writer preserves imported UUIDs, rejects identity collisions, protects minutes-owned/legacy rows, and tombstones only proven agenda-owned withdrawals. Empty portal stubs/unpublished unknown agendas never erase prior records. Existing votes are retained; new vote extraction is not implied. Keyword tags preserve non-keyword provenance. Status records distinguish pending/unmapped sources from a successful source-window check.

The compact database must be a separate target with the reviewed `scripts/basic-core/public-core.sql` schema, imported seeds and records. It refuses a full document-lake database. Before source fetching it checks schema and whole-database size. Before writes it reserves at least 50 MB of headroom within the 500 MB ceiling (and eight times normalized payload size); afterward unexpected size growth rolls back. Provider-managed catalogs and update bloat count toward that ceiling. Storage checks are operational bounds, not a guarantee that vacuum/index/catalog growth can never fill a database.

Public apply requires all three explicit inputs: `RICHMOND_BASIC_READY=true`, `RICHMOND_BASIC_PROJECT_REF` for a dedicated new project, and `RICHMOND_BASIC_DATABASE_URL` for that exact target with TLS. Direct hosts are accepted. GitHub Actions can use an explicitly declared `RICHMOND_BASIC_POOLER_HOST` in the official `aws-…pooler.supabase.com` namespace, session port 5432 and exact `postgres.<new-project-ref>` username. Unknown poolers, transaction port 6543, routing overrides and the original paid project are denied. Session pooling supports IPv4 without the paid IPv4 add-on; see [Supabase network compatibility](https://supabase.com/docs/guides/troubleshooting/supabase--your-network-ipv4-and-ipv6-compatibility-cHe3BP). `DATABASE_URL`/production `.env` are never fallbacks. Missing target/configuration fails before source fetching. No public target has been provisioned or refreshed by these scripts in this task.

```powershell
python src/basic_refresh.py --plan --target public --profile basic_public
# Only after separately reviewed dedicated target validation/configuration:
python src/basic_refresh.py --apply --target public --profile basic_public --year 2026 --through 2026-11-03 --agenda-limit 20
```

Electronic finance publication is exactly `0660620:calendar-2026`, January 1–November 3, 2026. That end date is a query horizon, not evidence that future records have already been filed or all papers are covered. `src/finance_public_projection.py` requires all eight forms, consistent scope/cutoff, complete electronic acquisition, zero model calls, valid source provenance and no duplicate identities. It filters to the reviewed public confidence/status rules. All eight public coverage records remain partial with paper/other-agency limitations.

The writer checks the prior cutoff, takes an advisory transaction lock, checks the cutoff again, and atomically replaces the entire electronic scope plus all eight coverage rows. Failed acquisition/projection leaves the prior snapshot intact. It never appends amended events into stale totals. The current compact scope contains only NetFile electronic rows; adding reviewed paper/other-source events later requires source-aware identity/replacement semantics before reusing this contract. The full archive ledger/original source evidence is not deleted by replacing this derived projection.

The finite finance adapter limits each acquisition before public projection: 64 transaction pages, 10,000 rows, 400 metadata requests, 32 PDF reads; 2 MB per JSON response, 256 KB per metadata response, 4 MB per PDF/24 MB PDF total, 48 MB all responses, 512 HTTP requests and 300 seconds with bounded request timeouts. Limits can only be lowered. It makes no retries/redirects/model calls and stores no raw source files itself. Any inconsistent or incomplete paginated inventory rejects the entire acquisition before writes.

This runner does not refresh all historical finance or roll over election cycles. Public defaults and the prepared schedule pin the reviewed 2026/November 3 horizon instead of silently advancing dates. Late checks can update amendments within that old scope; after November 3 the source status becomes `pending_review` because scope expansion is unreviewed. A new cycle requires explicitly reviewed schema, projection, source scope, frontend and tests. Agenda/tag checks run independently and continue after the finance boundary or a finance failure. Previously published records and last successful check remain visible.

## PC-independent scheduling and honest freshness

Public scheduling is a separate release step. The prepared `.github/workflows/basic-refresh.yml` runs independent narrow agenda/tag and fixed-horizon finance passes; it never invokes the disabled mixed Data Sync workflow. Its apply job requires trusted `main` and `vars.RICHMOND_BASIC_READY == 'true'`, uses only explicitly named basic-target database credentials/project identity/pooler host, sets the basic profile and model lock/cap zero, and exposes no model/email/operator/production secrets. Readiness remains absent/false until the exact free target, privileges, size and HTTP/browser flows have passed verification. Existing jobs remain disabled; no runs were dispatched here.

The prepared `scripts/basic-core/record_refresh_state.py` preserves aggregate automation state on `automation/basic-refresh-state`: per-source `last_attempt`, `last_success`, outcome, reviewed window/cutoff, pending vote/paper flags, and integer write counts only. It is gated to the ready trusted main workflow. A meaningful dated state change records each completed source check; source/person rows, credential URLs, private logs and passwords are never copied. Failure advances `last_attempt` and records a fixed failure category but preserves prior `last_success` and counts. Workflow concurrency allows only one writer per target. This state publisher has fixture guard/privacy tests but no remote writes were performed here.

Basic Core Refresh has an explicit `deferred-free-audit` operator notification policy. External notifications remain off; it does not activate the legacy Resend failure wrapper or require an email secret. Once the guarded workflow is ready, failures produce a failed run and a sanitized job summary showing each source outcome and whether aggregate state publication succeeded. If that publication fails, the prior state branch remains intact and the run summary exposes the audit gap. Stale source status still requires operator review; this policy does not promise automatic email delivery.

Meaningful state commits support the repository-activity audit needed because public GitHub schedules can disable after 60 days of inactivity; see [GitHub schedule behavior](https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows#schedule). Schedules can still be delayed/disabled, so manual dispatch, visible stale thresholds and independent monitoring remain release requirements. The basic home Source checks component reads only allowlisted agenda/finance status rows, displays their last successful checked timestamps and scope/limitations, and does not relabel old votes/paper figures as newly extracted.

## Safe reactivation and rollback

1. Keep the full dump, source originals and private recovery key. Verify the local archive before reducing hosted storage.
2. Select `basic_public` or explicit loopback `local_archive` in the shared catalog/environment. Leave optional capabilities false and model budget locked at zero.
3. Install verified dependencies; restore the full local schema or import the reviewed compact schema into a dedicated empty target. Validate exact identity, reader privileges, source/held-record checks and physical size.
4. Run plan, fixture/guard tests, then a bounded explicit source pass. Verify idempotence, failure preservation, metadata/cutoff honesty and actual rendered/API flows before enabling a narrow schedule.
5. Enable only the reviewed narrow updater after dedicated readiness and credentials are validated; keep the mixed paid workflows off. Record aggregate source-check state, monitor staleness and preserve manual recovery.
6. Optional AI/email/accounts each require their adapter/infrastructure, model/index compatibility where relevant, capability switch, authorization and independent budget/provider guards. Verify them separately before use.

Rollback disables readiness/capabilities/jobs and restores the prior application policy or derived compact snapshot. It does not delete or alter the verified original backup. Any database/provider retirement is separate from these feature switches and must not affect GoodJobber.
