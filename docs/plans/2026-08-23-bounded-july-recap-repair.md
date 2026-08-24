# Bounded July 2026 Transcript-Recap Repair Plan

**Status:** Prepared only — not executed

**Publication tier:** Operator-only (production repair handoff)

**Production writes in this change:** None

## Purpose and fixed boundary

Fill the three proven July 2026 transcript-recap gaps after the merged Granicus
fallback/provenance fix. A later, separately authorized session may generate
only the four transcript-recap fields (`transcript_recap`, source, structured
provenance, and generated timestamp) for the three rows below. This plan does
not authorize production execution. The later LLM calls' normal atomic
`llm_cost_reservations` and `pipeline_journal` accounting rows are the only
permitted writes outside those meeting rows.

| Meeting date | Meeting ID | Granicus clip | Granicus document | Expected recap source |
|---|---|---:|---|---|
| 2026-07-07 | `c11d635f-b74f-4208-8fad-376a3791905b` | 6020 | `a6f2bc6d-7aed-11f1-9494-005056a89546` | `granicus` |
| 2026-07-21 | `a166af80-e456-4db2-9b74-215a378956a4` | 6025 | `892134f4-85f3-11f1-bb61-005056a89546` | `granicus` |
| 2026-07-28 | `3de0bb26-8f30-4836-a5bd-a01b6640b676` | 6028 | `15999ea7-8b71-11f1-bb61-005056a89546` | `granicus` |

The Tier 1 source page for each row is
`https://richmond.granicus.com/MinutesViewer.php?view_id=30&clip_id=<clip>&doc_id=<document>`.
Read-only discovery on 2026-08-23 found exactly one transcript for each date
and resolved each viewer page to a PDF. The later executor must prove that
again; this snapshot is not permission to assume the source is unchanged.

## Preconditions for a later execution session

1. Obtain explicit operator approval to execute this named production repair.
   Start from a fresh temporary worktree whose `main` contains the merged
   Granicus fallback/provenance fix (`e2fb698` or a descendant). Record the
   repair start time. Do not reuse transcript artifacts from another run.
2. In a read-only database transaction, select the three meeting IDs above.
   Abort unless there are exactly three rows; every ID, date, and
   `meeting_type='regular'` matches the table; and all four of
   `transcript_recap`, `transcript_recap_source`, and
   `transcript_recap_provenance`, and `transcript_recap_generated_at` are null.
   Also abort if more than one regular meeting exists on any target date.
3. For the current target date, run Granicus discovery read-only. Require
   exactly one date match, the exact clip/document pair above, an HTTPS
   `richmond.granicus.com` viewer URL, a successfully resolved non-empty PDF,
   and extracted non-empty text. If any target-date `*_clean.txt`,
   `*_source.json`, `*_granicus.pdf`, or `*.vtt` artifact already exists before
   the fetch, stop for source review; do not delete, overwrite, or relabel it.
4. Inspect the authoritative `RICHMOND_API_BUDGET_LOCK` setting and pass it
   through unchanged. If it is true, stop; do not locally unset or bypass it.
   Use a fresh worktree with no repository-root `.env` file, because these
   scripts load that file with override semantics. Inject existing credentials
   securely through the process environment instead.
   Set `RICHMOND_API_MONTHLY_CAP_USD=5.00` (never raise the project cap) and
   `RICHMOND_EVENT_BUDGET_USD=0.15` for each separate one-date process. Before
   each paid call, import `post_meeting_recap` and assert the effective runtime
   values are unlocked, `$5.00`, and `$0.15` after dotenv loading. Then run
   `python cost_digest.py --since 2026-08-01 --json` from `src/` and require
   `mtd_total + 0.15 <= min(cap_usd, 5.00)`. If execution occurs after August,
   use the first day of the execution month instead.

## Exact one-date sequence

Use the local transcript-only CLI, not the GitHub workflow. The workflow runs
speaker-count extraction and the agenda recap as well, so it is broader than
this repair. Run one date, complete every verification below, and only then
advance to the next date in chronological order.

From `src/`, with the production database and existing DeepSeek credentials
available to the process:

### 1. July 7

```powershell
$env:RICHMOND_API_MONTHLY_CAP_USD = '5.00'
$env:RICHMOND_EVENT_BUDGET_USD = '0.15'
python -c "import post_meeting_recap; import llm_budget_lock as b; assert not b.is_locked() and b._monthly_cap_usd() == 5.0 and b._event_cap_usd() == 0.15; print('budget rails verified')"
python cost_digest.py --since 2026-08-01 --json
python -c "import sys; from granicus_transcripts import discover_granicus_meetings as d; r=[m for m in d() if m['meeting_date']==sys.argv[1]]; assert len(r)==1 and r[0]['clip_id']==sys.argv[2] and r[0]['doc_id']==sys.argv[3], r; print(r[0])" 2026-07-07 6020 a6f2bc6d-7aed-11f1-9494-005056a89546
python granicus_transcripts.py fetch --meeting-date 2026-07-07
python post_meeting_recap.py --meeting-date 2026-07-07 --only-transcript-recap --transcript-source granicus
```

### 2. July 21

```powershell
$env:RICHMOND_API_MONTHLY_CAP_USD = '5.00'
$env:RICHMOND_EVENT_BUDGET_USD = '0.15'
python -c "import post_meeting_recap; import llm_budget_lock as b; assert not b.is_locked() and b._monthly_cap_usd() == 5.0 and b._event_cap_usd() == 0.15; print('budget rails verified')"
python cost_digest.py --since 2026-08-01 --json
python -c "import sys; from granicus_transcripts import discover_granicus_meetings as d; r=[m for m in d() if m['meeting_date']==sys.argv[1]]; assert len(r)==1 and r[0]['clip_id']==sys.argv[2] and r[0]['doc_id']==sys.argv[3], r; print(r[0])" 2026-07-21 6025 892134f4-85f3-11f1-bb61-005056a89546
python granicus_transcripts.py fetch --meeting-date 2026-07-21
python post_meeting_recap.py --meeting-date 2026-07-21 --only-transcript-recap --transcript-source granicus
```

### 3. July 28

```powershell
$env:RICHMOND_API_MONTHLY_CAP_USD = '5.00'
$env:RICHMOND_EVENT_BUDGET_USD = '0.15'
python -c "import post_meeting_recap; import llm_budget_lock as b; assert not b.is_locked() and b._monthly_cap_usd() == 5.0 and b._event_cap_usd() == 0.15; print('budget rails verified')"
python cost_digest.py --since 2026-08-01 --json
python -c "import sys; from granicus_transcripts import discover_granicus_meetings as d; r=[m for m in d() if m['meeting_date']==sys.argv[1]]; assert len(r)==1 and r[0]['clip_id']==sys.argv[2] and r[0]['doc_id']==sys.argv[3], r; print(r[0])" 2026-07-28 6028 15999ea7-8b71-11f1-bb61-005056a89546
python granicus_transcripts.py fetch --meeting-date 2026-07-28
python post_meeting_recap.py --meeting-date 2026-07-28 --only-transcript-recap --transcript-source granicus
```

Never add `--force`. Never run `granicus_transcripts.py fetch` without its
single `--meeting-date`. Never run `post_meeting_recap.py` without both
`--only-transcript-recap` and `--transcript-source granicus` for this repair.

## Verification after each date

Before proceeding, query all three allowlisted IDs read-only and require:

- Record a separate UTC step-start time immediately before each recap command.
  The just-completed target's generated timestamp must be at or after that
  step-start; previously completed rows must equal their last verified values;
  and the later targets must remain entirely null.
- The target has a non-empty `transcript_recap`, a non-null
  `transcript_recap_generated_at`, and flat
  `transcript_recap_source='granicus'` — never `youtube`.
- Structured `transcript_recap_provenance` has
  `kind='meeting_recording'`, `channel='granicus'`,
  `generator='post_meeting_recap.py'`, and a non-null `as_of` value.
- `data/transcripts/<date>_source.json` contains the same target date and
  `source='granicus'`; the Granicus PDF and clean transcript exist, and no
  YouTube VTT marker exists for that date.
- The centralized cost journal has exactly one newly settled
  `post_meeting_recap.py` call for the date, its actual cost is no more than
  `$0.15`, and the updated month-to-date total remains at or below `$5.00`.
- A query for any meeting outside the three-ID allowlist with
  `transcript_recap_generated_at >= <repair-start-time>` returns zero rows.

After all three pass, run the read-only recap-generation liveness check. These
three dates must no longer be reported as missing. Record the before/after
rows, provenance objects, costs, and liveness output in the execution report.

## Hard stops

Stop without attempting to compensate, broaden, or retry if:

- the cohort is anything other than the three exact IDs above, a target
  already has a recap/provenance value, or any source/date/clip/document check
  differs;
- source identity is unknown, ambiguous, or conflicts with Granicus; a local
  artifact could be YouTube-derived; or any result would be labeled YouTube;
- discovery returns zero or multiple target-date transcripts, the PDF cannot
  be resolved/extracted, DeepSeek returns no recap, or final verification is
  incomplete;
- the budget lock is on, a reservation/cost journal check fails, the `$0.15`
  event rail would be exceeded, or month-to-date spend plus the next rail would
  exceed `$5.00`;
- a command would use `--force`, the full post-meeting workflow, a broad
  Granicus fetch, historical backfill, unbounded sync, enrichment cascade, or
  touch civic/content production data outside the three-record cohort (normal
  cost-reservation and journal accounting writes remain required); or
- execution appears to require any schema migration (especially migration
  134), production-data correction beyond these three rows' four recap fields,
  or any S26/S28 scope expansion.

Do not apply a migration, alter source records, repair speaker counts, rewrite
agenda recaps, or continue to the next date after a failed verification. The
operator must receive the failure with a clear action line; no silent green
no-op or automatic retry is acceptable.
