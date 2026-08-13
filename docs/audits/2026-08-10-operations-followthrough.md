# August operations follow-through

**Opened:** 2026-08-10

**Base:** `f57fcfbd10a4012f975a6fa52133a7a70a2b79e9` (merged PR #86)

**Scope:** focused NextRequest repair, read-only attribution of the already
captured 43-hour database growth, RPC cost/grant review, and a forward grant
migration prepared but not applied. This is not a new audit.

## Hard boundaries

- Migration 134 remains byte-identical at SHA-256
  `4fac27264b5b0fe63f03d92e52462db33590457c11de64e795f4daeb4072e7a6`.
  It is a hard no-go: never apply it and never rewrite it in place.
- No migration in this change was applied to production.
- No NextRequest or eSCRIBE sync was run. No unbounded sync is authorized.
- The 42-row contribution cleanup was not run. No row was deleted.
- Every eSCRIBE production replay, correction, rollback, or enforcement action
  remains separately approval-gated and exact-GUID-scoped.

## 1. NextRequest visibility repair

A bounded read-only enumeration of Richmond, California's complete public
request list returned `3,005 / 3,005` unique requests across 31 pages:

| Public list visibility | Rows | Example |
|---|---:|---|
| `Published` | 3,002 | `26-1190` |
| `Published - department only` | 3 | `26-345` |

The other two department-published requests are `25-205` and `23-391`. Each
record is returned by the unauthenticated public list with its public fields.
Its public detail endpoint reports `visibility=department_published` together
with `request_visibility=Published`.

The classifier accepted neither observed spelling. The list therefore aborted
on the first of these three rows with `NextRequest request visibility enum is
unknown`, even though the same record was publicly enumerated. The fix adds
only `Published - department only` and its normalized detail value
`department_published` to the explicit public allowlist. Unknown values,
missing values, and disagreements still fail closed. Focused regression tests
cover both live shapes and the existing unknown/conflict cases.

This repair does not authorize the catch-up sync. Production still contains
2,395 stored requests as recorded in the closeout packet; running the repaired
incremental sync is a separate production action.

## 2. Temporary-file attribution

The closed 43h18m interval remains the canonical measurement:

- temporary files: `+3,345`;
- temporary bytes: `+12,856,490,870`;
- `pg_stat_statements` reset unchanged at
  `2026-04-16T12:04:50.800362Z`.

A focused read-only `pg_stat_statements` query identified the dominant
temporary-block producer: `dedup_contributions.find_cross_filing_duplicates()`.
Its candidate self-join of `contributions` to itself had:

| Metric | Cumulative value at follow-through |
|---|---:|
| Calls | `2,112` |
| Total execution time | `685,757.499 ms` |
| Temporary blocks written | `1,551,660` |
| Temporary bytes at 8 KiB/block | `12,711,198,720` |

That byte volume is 98.87% of the entire 43-hour temporary-byte increase. The
call path explains the multiplier: `load_contributions_to_db()` runs the
whole-city near-duplicate self-join after every committing contribution load,
while its comment calls the pass “Cheap (one query).” The same operation also
exists as a named NetFile enrichment.

Attribution level: **dominant source class identified; exact interval share is
not reproducibly provable.** The 43-hour capture versioned aggregate deltas and
selected RPC deltas, but not a raw baseline for this non-RPC query ID. The
current cumulative block count matching the interval scale is strong evidence,
not a valid subtraction. Fixing that query/call frequency belongs in a focused
performance change; it is not changed here.

The named RPCs explain only a small part of interval temp growth.
`get_divergent_motions_detail` added 1,304 blocks (`10,682,368` bytes); the
other measured RPC deltas added zero temporary blocks.

## 3. Idle-in-transaction attribution

The database counter increased `42,607,764.862 ms` (11h50m07.765s) while both
endpoint snapshots showed no live idle-in-transaction backend. Exact PID/run
attribution cannot be recovered after those sessions end from
`pg_stat_database`; the interval had no continuous `pg_stat_activity` sampler.

The responsible connection-lifetime class is nevertheless visible in code.
`data_sync.run_sync()` opens one database connection before invoking a source
and retains it through source HTTP work, retry backoff, downstream logging, and
anomaly checks, closing it only in `finally`. Any SQL statement that opens a
transaction before external I/O leaves that session idle in transaction until
the source resumes or commits. The interval contained many Data Sync dispatches,
including [run 31315460286](https://github.com/pjfront/richmond-common/actions/runs/31315460286),
which held its source job for 101 minutes while processing 151,558 Socrata
permit updates.

Attribution level: **pipeline connection-lifetime mechanism identified; exact
source/run unproven.** Naming a particular ended workflow as the source of all
11h50m would exceed the evidence. A future exact attribution needs bounded
sampling of application name, transaction age, and pipeline run ID while a
transaction is live, or source functions must split network collection from
short write transactions. Neither operational change is part of this PR.

## 4. RPC cost and anonymous-grant audit

Production exposes 24 public-schema functions. Before the proposed migration,
16 are executable by `anon` and `authenticated`; PostgreSQL's default `PUBLIC`
grant is the reason for most of that surface.

The intended anonymous/authenticated read allowlist is:

- `find_similar_items`, `get_category_stats`, `get_contested_votes`,
  `get_controversial_items`, `get_divergent_motions_detail`;
- `get_meeting_counts`, `get_meeting_flag_counts`, `list_public_tables`;
- `parse_vote_tally` (required by invoker-security `get_category_stats`);
- `search_hybrid` and `search_site`.

The proposed service-only/internal set is:

- `check_and_increment_rate_limit` (the repository caller uses the server-side
  admin client), `cleanup_rate_limit_buckets`, and `merge_official_pair`;
- trigger-only `rls_auto_enable` and `update_meeting_agenda_item_count`, with no
  API-role execution grant.

The remaining eight pipeline/cost-reservation functions were already
service-role-only and are not modified.

The interval cost findings remain:

| RPC | Calls delta | Execution delta | Mean | Temp-block delta |
|---|---:|---:|---:|---:|
| `find_similar_items` | `10,824` | `4,764,561.412 ms` | `440.2 ms` | `0` |
| `get_meeting_counts` | `4` | `8,267.826 ms` | `2,067.0 ms` | `0` |
| `get_contested_votes` | `3` | `6,692.977 ms` | `2,231.0 ms` | `0` |
| `get_divergent_motions_detail` | `3` | `6,733.822 ms` | `2,244.6 ms` | `1,304` |
| `get_meeting_flag_counts` | `3` | `386.686 ms` | `128.9 ms` | `0` |
| `get_controversial_items` | `0` | `0` | n/a | `0` |

The grant migration intentionally does not attempt a performance rewrite. The
missing live `get_meeting_coverage_stats` function also remains a separate
reliability defect; adding a function while narrowing grants would mix scopes.

## 5. Forward migration 138 — prepared, not applied

`138_restrict_rpc_execute_grants.sql` is mirrored byte-for-byte into the
timestamped Supabase migration tree. It:

- revokes default/inherited `PUBLIC`, anonymous, and authenticated execution;
- re-grants the 11 public read/helper functions explicitly;
- keeps three server/operator mutations service-role-only;
- removes direct API-role execution from two trigger-only functions; and
- performs no function redefinition, table/policy change, or data mutation.

Tests lock the mirror, the exact allowlists, privilege-only SQL, and migration
134's byte hash. Applying migration 138 to production still requires a separate
operator approval and post-apply grant checks.

## 6. Exact approval packets held

These packets document the next decision boundary. They are **not approvals**.

### A. Forty-two contribution extras

Exact cohort artifact:
`docs/audits/2026-08-08-duplicate-contribution-cohort.csv`, SHA-256
`ee25a6c4566f7032f15d5f3cc163c53ada90a6ab44142492134bc80412e85fbe`.
It contains 42 keeper/drop pairs: 42 duplicate groups, 42 proposed extra rows,
and `$14,900` of proposed drops. Pending decision
`cc106e5c-8198-403d-95ad-f6bdba638181` remains open.

Exact approval text, if the operator chooses to grant it later:

> Approve one guarded production transaction against project
> `ahrwvmizzykyyfavdvfv` using only the 42 keeper/drop pairs in cohort SHA-256
> `ee25a6c4566f7032f15d5f3cc163c53ada90a6ab44142492134bc80412e85fbe`:
> enrich only those 42 keepers from their paired drops, delete exactly the 42
> drop IDs, require `42 groups / 42 extras` before and `0 / 0` inside the
> transaction, and commit only if all guards pass. Do not merge donors, touch
> any other contribution, or resolve the pending decision in the same action.

No such approval was given in this task.

### B. eSCRIBE production actions

The only already-proven bounded cohort is exactly these three GUIDs, whose
sorted-list SHA-256 is
`d7deee90a38f7788e1df45a34d2b19574f651fb790fc4d5918a30d6b812ae97e`:

- `563b7bf8-ccbf-4021-909e-c8e7721be2b9`;
- `bbd17186-799a-4134-9239-bf37b944459a`;
- `c3c39254-53cc-4461-9b85-041288171803`.

An approval packet must name one action—replay, correction, rollback, or a new
forward enforcement migration—and must state its exact GUIDs, expected row IDs
and field-level mutations, complete pre/post guards, and recovery limits. The
current evidence artifacts explicitly say `mutation_surface_complete=false`
and `restoration_supported=false`, so they are not an approval-ready rollback
packet. Production GUID/full runs are also hard-blocked by the CLI.

Therefore no eSCRIBE production action is currently approval-ready. An
unbounded sync, migration 134, or wording such as “apply the reconciliation
fix” can never satisfy this gate.
