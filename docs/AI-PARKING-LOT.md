# AI Parking Lot

_Ideas, research topics, and improvement suggestions captured by the AI during implementation sessions. AI has full autonomy over this file. Periodically reviewed and prioritized with the operator for integration into the roadmap._

_Convention: Every session adds observations here. Items stay until promoted to the sprint backlog or explicitly discarded during a review._

---

## Sprint Number Mapping (2026-04-08)

> **Roadmap reorganization:** S21.5 promoted to S22. Old S22/S24/S25 renumbered to S25/S26/S27. See `docs/PARKING-LOT.md` Sprint Number Mapping table for full details. Historical references in this file use original numbers.

## Promoted to Phase 3

_Items from this parking lot that have been promoted to Phase 3 sprints. Kept here for reference; active tracking in `docs/PARKING-LOT.md`._

**Promoted 2026-04-08 (roadmap reorg):**
- ~~I104~~ Pipeline post-sync ISR revalidation hook --> **S24.12**
- ~~I108~~ Preference-filtered email delivery (digest v2) --> **S24.10**
- ~~I114~~ Dedicated neighborhoods page --> **S24.5**
- ~~I116~~ Subscriber cultivation strategy --> **S24.8**
- ~~I117~~ RPC single-point-of-failure audit --> **S24.11**
- ~~I118~~ Comment summary backfill --> **S24.7**

**Earlier promotions:**
- ~~I71~~ Semantic similarity & controversy discovery --> **S25** (was S22)
- ~~I60~~ Lightweight topic timeline using existing categories --> **S23.1**
- ~~I80~~ Topic landing pages (per-topic summary, timeline, related issues) --> **S23.3**
- ~~I68~~ AI-generated comment summaries per agenda item --> **S23.5**
- ~~I84~~ Email digest / subscription notifications --> **S23.2**
- ~~I45~~ Proceeding type classification for existing agenda items --> **S25** (was S22.4)
- ~~I62~~ CONTRIBUTING.md and issue templates for public repo --> **S27.1** (was S25.1)
- ~~I63~~ GitHub repo metadata for discoverability --> **S27.1** (was S25.1)
- ~~I83~~ "How to Use This Site" guide page --> **S27.3** (was S25.3)
- ~~I87~~ Council member photos from city website --> **S27.4** (was S25.4)
- ~~I82~~ Inline search overlay (command palette pattern) --> **S27.5** (was S25.5)
- ~~I90~~ Voting record -- show topic labels on mobile --> **S27.5** (was S25.5)
- ~~I92~~ Voting record -- topic filter redesign --> **S27.5** (was S25.5)
- ~~I93~~ Meeting detail -- quick text filter for agenda items --> **S27.5** (was S25.5)
- ~~R4~~ Search query analytics before RAG investment --> **S25** (was S22.5)

---

## Research Topics

### R1. Entity Extraction for Civic Text ➜ Promoted to S9.5
Gazetteer-based matching replaced noisy `extract_entity_names()`. Uses `city_expenditures.normalized_vendor` directly.

### R2. Expenditure Data Quality Profile ➜ Promoted to S9.5
Vendor normalization quality profiled as pre-check for R1/I1 gazetteer matching.

### R3. Per-Signal vs. Group Confidence Display ➜ ✅ Done in S9.6
Implemented as factor breakdown display in expandable rows (Name Match, Time Proximity, Financial Materiality, Statistical Anomaly).

---

## Improvement Suggestions

### I1. Gazetteer-Based Vendor Matching in Scan Loop ➜ Promoted to S9.5
Direct implementation of R1 — match vendor list against item text using `name_in_text()`.

### I2. Expenditure Amount as Financial Amount Enrichment
**Origin:** S9.3 (2026-03-10) | **Priority estimate:** Low

When a vendor matches an agenda item, the expenditure amount could supplement the item's `financial_amount` field (often empty for non-consent items). Would improve financial_factor scoring for items that don't have explicit dollar amounts.

### I3. Vendor-Official Voting Pattern Detection
**Origin:** S9.3 (2026-03-10) | **Priority estimate:** Low (coalition-level, future sprint)

Track whether officials consistently vote Aye on items involving their donors' vendors. This is a coalition-level pattern, not a single-flag signal. Extends beyond current per-item conflict detection into longitudinal behavioral analysis.

### I4. Scan Results Sorted/Grouped by Agenda Item ➜ ✅ Done in S9.6
"Group by item" toggle in `FinancialConnectionsAllTable` with corroboration-visible grouping.

### I5. CAL-ACCESS Independent Expenditure Parsing ➜ ✅ Complete
Wired expenditure parsing into `sync_calaccess()` — monthly sync processes both RCPT_CD and EXPN_CD.

### I6. Automated Data Quality Regression Suite ➜ Promoted to S10 ✅ Complete
9 SQL-based checks in `src/data_quality_checks.py`, GitHub Actions CI, decision queue alerting, 33 tests.

### I7. Dual `extract_financial_amount` Consolidation ➜ ✅ Fixed
Extracted to `src/text_utils.py` (canonical version with billion support). Both modules re-export.

### I8. Public Comment Data Gap — Counts Without Substance
**Origin:** S21 design session (2026-03-27) | **Priority estimate:** High (blocks Community Voice)

The S20 YouTube/Granicus transcript pipelines extract only speaker **counts** per agenda item (`agenda_items.public_comment_count`). They create NO individual `public_comments` rows — no speaker names, no summaries, no methods per person. The `public_comments` table schema supports this data but is essentially empty for transcript-sourced meetings. The enhanced extraction in S21 Phase A addresses this by re-processing all 80 existing transcripts to extract individual speaker records. This is the single biggest data gap blocking meaningful public comment display.

### I9. Nuance-Preserving Comment Classification
**Origin:** S21 design session (2026-03-27) | **Priority estimate:** Context note

The operator explicitly rejected sentiment classification (support/oppose/neutral) for public comments because it destroys nuance — the same reductive dynamics as social media. The replacement approach (theme extraction by substantive point raised) preserves nuance by allowing speakers to appear under multiple themes and using narrative descriptions instead of position labels. If sentiment analysis is ever reconsidered, it should be as a secondary dimension within themes, never as the primary grouping.

---

## Technical Debt / Cleanup

### D50. Anderson filing 216695016 has $1,030 unitemized reconciliation gap ✅ FIXED 2026-05-16 (T0.3)

**Root cause (different from the 4 hypothesized in the original entry):** the form summary cache lived in `src/data/form_summaries.json`, gitignored AND on ephemeral GitHub Actions runners. Each cloud run started with an empty cache and tried to rebuild it from the NetFile RSS feed — but the RSS is a rolling 15-day window. Once Form 460s aged out of RSS (after the April 30 semi-annual deadline), the cache could not be rebuilt. `discover_and_extract_all_form460_summaries` found ZERO 460s in RSS and silently produced an empty cache. `paper_filing_reconciliation` reported `records_fetched: 0` for every run since 2026-05-16 07:00 UTC. Effect: NOT just Anderson — every paper filer's reconciliation was silently dead.

**Fix:** migration 114 + load_paper_filings.py changes (commit on `tier0-anderson-recon` branch).
- New table `form_summary_cache` (filing_id PK, committee, summary JSONB, extracted_at, updated_at)
- `_load_form_summary_cache()` reads from DB, falls back to file for local-only dev
- `_save_form_summary_cache()` writes to DB primary, file as backup
- One-time backfill from operator's local file populated 24 entries spanning 13 committees

**Verification (2026-05-16):**
- Reconciliation re-run: 24 filings examined, 18 UNI rows synthesized, $7,305.85 total
- Anderson 216695016: $1,030 unitemized synthesized; DB period total = $21,605, matches Form 460 Line 5 exactly
- `test_paper_filing_dbtotal_matches_form_460_cover` passes against live DB
- 2 new regression tests added (DB cache table + loader)

### D56. Jimenez + Zepeda cache duplication (Bug A) — ✅ RESOLVED 2026-05-17 (migration 115)
**Origin:** T0.3 reconciliation run, 2026-05-16 | **Resolved:** 2026-05-17 (Bug A); Bug B re-scoped to D56b

The original framing ("two filings each exceed Form 460 by $1,468 from cross-filing dup") was partially wrong. Investigation surfaced two distinct issues with different fix shapes:

**Bug A — Cache duplication (RESOLVED).** `form_summary_cache` was PK'd on `filing_id`, so an amendment filing's PDF (different `filing_id`, same underlying Form 460) was cached as a sibling of the original instead of replacing it. Affected Jimenez 2026 mayor (filings 216686471 + 216693965) and Cesar Zepeda 2026 council (filings 211803297 + 214593276), both with identical extracted_at timestamps to the microsecond. **Fix:** migration 115 cleans up existing dups + adds unique expression index on `(committee, period_start, period_end)`; loader (`src/load_paper_filings.py:_save_form_summary_cache`) changed to DELETE-then-INSERT so amendments cleanly replace originals. New tests `test_no_duplicate_form_summary_cache_per_period` and `test_form_summary_cache_committee_period_unique_index_exists` enforce the invariant going forward.

**Bug B — Form 460 + Form 497 aggregation policy → see D56b below.** The remaining $1,468 monetary excess for Jimenez is NOT a structural DB bug; it's an interpretation question about how to aggregate across Form 460 (periodic) and Form 497 (24-hour late-contribution notification) filings.

**Verification (2026-05-17):**
- Pre-fix: 2 dup groups in `form_summary_cache`. Post-migration: 0 groups; 24 → 22 cache rows.
- Unique index `form_summary_cache_committee_period_uniq` created and verified.
- All 15 tests in `tests/test_filing_period_briefing.py` pass under `RICHMOND_RUN_DB_TESTS=1`.
- Full suite: 2,259 pass / 0 fail / 36 skipped (+2 new opt-in DB tests skipped without the env var).

### D56b. Form 460 + Form 497 aggregation policy → ✅ RESOLVED 2026-05-17 (Option 1 shipped); silent-failure follow-up 2026-05-18
**Origin:** D56 diagnosis, 2026-05-17 | **Resolved:** 2026-05-17 (Option 1) + 2026-05-18 (RLS fix, migration 116)

**Follow-up bug caught 2026-05-18 (post-deploy spot-check):** Option 1 was shipped 2026-05-17 with the loader + queries change but `form_summary_cache` RLS only granted access to `service_role`, not `anon`. The public-facing pages (which use the anon client) silently fell back to summing DB rows. Live site showed Anderson at $47,602 instead of $40,602 for ~24 hours until the operator spot-checked richmondcommons.org. Migration 116 grants `anon, authenticated` SELECT on `form_summary_cache` (data is public Form 460 cover extractions, no PII). Added `form_summary_cache` to `tests/test_anon_visibility.py::PUBLIC_TABLES` — the existing test pattern would have caught this if I'd updated it when D56b introduced the new query path. Lesson: every commit that adds a `.from('newtable')` call in `web/src/lib/queries/*.ts` must also update PUBLIC_TABLES. **Enforcement landed 2026-05-18:** `tests/test_anon_visibility_coverage.py` is a pure static-analysis test that scans `web/src/lib/queries/*.ts` for `.from('X')` references and asserts every X is in PUBLIC_TABLES, EXEMPT (server-side only), or KNOWN_COVERAGE_GAPS (transitional debt). The transitional set captures 14 already-queried tables not yet in PUBLIC_TABLES — locked so it can shrink but cannot grow. Each entry there is real D56b-shape risk to retire over time by adding the table to PUBLIC_TABLES and running `RICHMOND_RUN_DB_TESTS=1` against live Supabase to confirm anon SELECT works.

**Decision:** Trust each candidate's own Form 460 cycle-to-date total for the headline number. Form 497 late-contribution disclosures stay visible in the donor list but don't bump the headline.

**Implementation:** `web/src/lib/queries/elections.ts::getLatestForm460Total` looks up the latest `form_summary_cache` row per committee and returns its `monetary_cycle_to_date`. `getCandidateFundraisingDetails` and `getElectionFundraisingSummary` both use this when available, fall back to sum-of-DB-rows when not. Test: `tests/test_filing_period_briefing.py::test_option1_displayed_total_matches_form_460_cycle_to_date` asserts the data-layer values match expected displays for Jimenez, Anderson, Johnson, Robinson, Evans, Pursell.

**Impact across candidates** (current display → Option 1 display):
| Candidate | Current | Option 1 | Change |
|---|---|---|---|
| Anderson | $20,575 | $40,602 | +$20,027 (under-count fix; almost 2x) |
| Wilson 2024 | (varies) | $49,822 | Full 2024 cycle from latest Form 460 |
| Jimenez | $32,958 | $31,490 | -$1,468 (the original D56 over-count) |
| Doria Robinson | $18,528 | $19,243 | +$715 |
| Johnson | $4,050 | $4,564 | +$514 |
| Pursell | $9,150 | $9,266 | +$116 |
| Evans | $4,215 | $4,389 | +$174 |
| Zepeda 2026 | $2,674 | $174 | -$2,500 (correct: pre-2026-cycle money excluded) |
| Martinez | $5,929 | $4,967 | -$962 (cycle_to_date < this_period — see D56c below) |

**Why Option 1 over Option 5** (sum of Form 460 + Form 497 supplemental): chose deference over custom methodology during election week. The Form 460 cover is the candidate's own legal certification. Defending a custom "we add Form 497 to Form 460" calculation creates a vector for the platform itself to become the story. Option 5 is more transparent in the abstract but more contentious in practice.

**Verified CA campaign finance facts** (from research agent 2026-05-17, FPPC primary sources; full URLs in research output):
- **$100 cumulative per source per calendar year** — itemization threshold AND occupation/employer disclosure threshold (FPPC Manual 2 Ch. 3).
- **$250** — SB 1439 / Gov Code §84308 pay-to-play threshold (since Jan 1, 2023). A local elected official cannot accept $250+ from anyone with pending business before their agency; if accepted, must be returned within 14 days or the official must recuse.
- **$1,000** — Form 497 (24-hour late-contribution report) trigger when received in the 90 days before an election or on election day. Same threshold for Form 496 (24-hour IE report).
- **$10,000 cumulative per calendar year** — Form 461 major donor filer threshold.
- **AB 571 state default contribution cap: $5,900 per election** for 2025-2026.
- **Richmond per-cycle cap: $2,500** (Richmond Municipal Code 2.42.050(a)(1), verified by operator from primary source 2026-05-17). NOTE: Richmond's limit is per **election CYCLE**, not per election like the state default — methodology page must distinguish these. Same Section 2.42.050 also confirms: $100 anonymous-contribution limit (a)(2) and $100 record-keeping threshold (a)(3), both reinforcing the $100 itemization line.

**Side findings during D56b resolution:**
- Anderson's true Form-460-reported cycle-to-date ($40,602) is roughly 2x what we'd been displaying ($20,575). The site was substantially under-reporting his fundraising. Option 1 corrects this automatically.
- Zepeda's display drops from $2,674 to $174 — also correct, because his pre-2026 race money was incorrectly leaking into his 2026 cycle display. Option 1 uses each filing's own cycle_to_date which handles cycle resets.

### D56c. Martinez Form 460 reports cycle_to_date LESS than this_period (data quality flag)
**Origin:** D56b research, 2026-05-17 | **Priority:** Low-medium (visible: Martinez display drops from $5,929 to $4,967)

Eduardo Martinez's Form 460 cache row has `monetary_this_period = $6,104` but `monetary_cycle_to_date = $4,967`. That's structurally impossible (cycle_to_date should be ≥ this_period for a single filing). Possible causes: (1) Vision OCR misread one of the two numbers, (2) candidate filed an amendment with refunds that reduced cycle_to_date below this_period, (3) the form genuinely shows this and reflects a $1,137 net refund/correction. Worth a quick PDF inspection to determine which.

Won't block Option 1 (Martinez's display under Option 1 just reflects what cache currently says). Investigation:
1. Pull filing 216686659's Form 460 PDF from `data/paper_filings/martinez_mayor_2026.json` or NetFile
2. Read Schedule A Summary Page Line 1 (Column A monetary this period) and the cycle-to-date column on the cover
3. If Vision misread, re-extract; if the form actually says this, document and leave alone

**Coverage hole the fix should also close:** The existing `test_paper_filing_dbtotal_matches_form_460_cover` only iterates Form 460s persisted as JSON sidecars in `src/data/paper_filings/*.json`. Form 460s discovered via the NetFile RSS feed and persisted only in the `form_summary_cache` DB table (the post-T0.3 path) are NOT covered. Jimenez has only a Form 410 in her JSON sidecar; her Form 460 lives only in `form_summary_cache` DB. **Implementation step 1 for D56b:** extend the test to also iterate `form_summary_cache` DB rows. The test will then fail for Jimenez (and possibly Zepeda) until the policy decision lands — mark `pytest.mark.xfail(reason="D56b pending operator decision")` until resolution per the load-bearing "no red tests, use xfail" rule.

**Why this matters now:** Public site over-reports Jimenez's total by ≈4.7% during election week. A journalist or opponent could screenshot the discrepancy against her own filing.

### D57. Wilson filing 212165365 exceeds Form 460 by $34 (minor rounding, low priority)
**Origin:** T0.3 reconciliation run, 2026-05-16 | **Priority:** Low (historic filing, small)

Sue Wilson's 2024 Form 460 for period 2024-07-01 to 2024-09-21 reports $18,666 monetary. DB sums $18,700 in the same period — excess $34. Most likely Vision OCR rounding error or a single $34 contribution mis-dated by a day. Not visible to users (the cycle-to-date sums still match closely), but flagged for completeness.

### D1. Temporal Correlation Dual Existence ➜ Promoted to S9.5
Removed separate Step 5b call in `cloud_pipeline.py`; integrated detector handles corroboration.

### D3. eSCRIBE Scraper Missing `.AgendaItemCounter` Fragility
**Origin:** Data quality audit (2026-03-11) | **Priority estimate:** Low

Closed session items lack the `.AgendaItemCounter` CSS class, so `item_number` stays empty. The fallback regex extraction (added in this session) handles the `C.1`, `C.2.a` pattern, but the scraper's reliance on specific CSS classes means any HTML structure change could silently break extraction. The broader pattern: eSCRIBE HTML is not a stable API. The self-healing selector approach used in the NextRequest scraper could be adapted here.

### D4. Migration FK Cascade Checklist
**Origin:** Migration 028 runtime failures (2026-03-11) | **Priority estimate:** Process improvement

Migration 028 failed twice in production: first missing `conflict_flags` cleanup, then missing `public_comments` cleanup before deleting `agenda_items`. The April 15 section of the *same migration* handled cascades correctly by manually listing all child tables. The Dec 2 section used a targeted subquery and missed two of three FK dependents.

**Process fix:** Any future migration that DELETEs parent rows should start by querying `information_schema.table_constraints` for all FK references to the target table, then delete from all child tables first. This query should be run *before writing the migration*, not after it fails. Consider adding a comment template at the top of migration files as a reminder.

### D2. DB Mode Fetch Pattern Could Use a Shared Helper ➜ Update: Now 6 fetch functions
**Origin:** S9.4 (2026-03-10) | **Updated:** 2026-03-20 (S13.1/S13.3 added 2 more) | **Priority estimate:** Low→Medium

The six `_fetch_*_from_db()` functions (contributions, form700, expenditures, independent_expenditures, permits, licenses + now behested_payments, lobbyist_registrations) follow the same pattern: execute query, map rows to dicts. A shared `_fetch_rows(conn, query, params, row_mapper)` helper would reduce ~200 lines of boilerplate. With 8 fetch functions now, the pattern is clearly established and the helper is worth building.

### D5. FPPC Behested Payments API Endpoint ➜ Resolved
Resolved via FPPC bulk Excel download (`BehestedPayments.xls`). 39 Richmond records loaded. Gap: local officials (Mayor/Council) may file Form 803 separately — disclosed on methodology page. See `docs/research/behested-payment-absence-detection.md`.

### D6. Richmond Lobbyist Registry — Data Found, Pipeline Fix Needed ➜ RESOLVED
Document Center has 26 lobbyist docs (2000-2025). Solution: direct PDF download by Document ID + Claude Vision extraction. ~29 entities registered 2014-2025. Key docs: Doc 75427 (2014-2025 list), Doc 27460 (2000-2013 list).

### ~~I11. Dedicated Project Email Before Public Launch~~ ✅ DONE
Switched to `hello@richmondcommons.org` across about page, comment generator, and tests.

### D7. Manual YouTube Transcript Paste Fallback Utility
**Origin:** 4/28/26 meeting post-session workflow (Entry 57) | **Priority estimate:** Low

When KCRT YouTube fetch is blocked (cloud-IP block, cookie/auth fragility), the operator falls back to copy-pasting the transcript pane into a markdown file on disk. The text format is YouTube-UI-export style: per-line `{H:MM(:SS)?}{spelled-out time ending in "seconds"}{text}` with no separators between fields. A one-off Python cleaner converted it to the existing `[H:MM:SS]`-block format that 79+ persisted clean transcripts use. Worth promoting that cleaner to a real utility (`src/clean_youtube_paste.py`) so the fallback is one command rather than session-specific code. Inputs: paste path. Outputs: `data/transcripts/{date}_clean.txt` in standard format. From there, the existing `post_meeting_recap.py --only-transcript-recap` and `extract_transcript_votes.py` work unchanged. Total elapsed time when polished: under five minutes from paste to revalidated meeting page.

---

## Predictions / Validation Checkpoints

### V1. Confidence Distribution After Batch Rescan
**Origin:** S9.3 (2026-03-10) | **Validate at:** S9.5

Expected distribution shift:
- Form700-only flags: stay at 0.3-0.5
- Temporal + campaign contribution: jump to 0.5-0.8
- Triple corroboration (temporal + campaign + donor-vendor): break 0.85

**Key metric:** Percentage of flags scoring above 0.50 (public visibility threshold), before vs. after.

### V2. Financial Amount Extraction Coverage
**Origin:** Data quality audit (2026-03-11) | **Validate at:** Next pipeline run

After the `extract_financial_amount` fix, spot-check that "$X.X million" patterns now produce correct values across all meetings. Query: `SELECT financial_amount, title FROM agenda_items WHERE financial_amount IS NOT NULL ORDER BY meeting_id DESC LIMIT 50`. Look for any remaining suspicious values (single digits, very small amounts for large contracts).

### V3. Batch Performance Stability Under Load
**Origin:** S9.5 batch performance (2026-03-11) | **Validate at:** Next full rescan

The 33x speedup (412s for 785 meetings with 8 workers) was measured on a single machine. Validate that:
- Worker count scaling is roughly linear up to CPU count (diminishing returns expected beyond that due to pickle serialization overhead)
- Memory usage stays stable (22K contributions × 8 workers = ~40-80MB duplicated data via pickle)
- No race conditions on DB writes in batch scan mode (main process handles all writes sequentially)
- `--workers 1` fallback produces identical results to parallel mode

### I8. Contribution Word Index Skew Detection
**Origin:** S9.5 batch performance (2026-03-11) | **Priority estimate:** Low

The word index (O2) maps 4+ char words to contribution indices. If a common word (e.g., "richmond", "california") appears in thousands of contributions, the index degrades toward linear scan for items containing that word. Current mitigation: the 4-char minimum filters stopwords. Future mitigation: track index cardinality and skip high-frequency words (>1000 contributions) during lookup, falling back to the word-overlap pre-screen for those candidates only.

### I9. Spec-Driven Development as Rebuild Insurance
**Origin:** S9.5 git stash incident (2026-03-11) | **Priority estimate:** Process observation

The O1-O5 rebuild took roughly half the time of the original implementation because the spec (`docs/specs/scanner-batch-performance-spec.md`) captured all design decisions, interface changes, and implementation details. The spec absorbed the hard thinking; the second implementation was mechanical transcription. This validates the "think before you task" process: detailed specs aren't just planning artifacts, they're recovery insurance. For any optimization or refactoring work that touches multiple files, a spec with concrete code snippets pays for itself if anything goes wrong.

**Implication for project process:** The spec template could include a "recovery checklist" section: which files change, what the key integration points are, and what test would break first. This session's test breakage (alias exclusion test needing donor name in item text for word index compatibility) was predictable from the spec but not explicitly called out.

### I10. Background Task Output Persistence Across Sessions
**Origin:** S9.5 session continuation (2026-03-11) | **Priority estimate:** Low (workflow observation)

When a Claude Code session runs out of context and continues via compaction, background task output files (`/private/tmp/claude-*/tasks/*.output`) are cleaned up. The benchmark results (412s, 1369 flags, 33.2x speedup) were only available because they were recorded in the conversation summary. For long-running benchmarks, the results should be written to a project file (e.g., `docs/benchmarks/`) rather than relying on task output persistence.

### I11. AI-Generated Connection Phrases for Conflict Flags (Option B)
**Origin:** 2026-03-15 session (connection context improvement) | **Priority estimate:** Medium (UX upgrade, defer until Option A evaluated in production)

Option A (template-based connection clauses via `_build_connection_clause()`) was implemented to explain why a donor was flagged on a specific agenda item. Option B would replace the template with a lightweight Claude API call to generate natural-language connection phrases like "before this vote to reappoint him to the Economic Development Board" instead of the mechanical "Gliksohn is named in this agenda item: Reappoint members to Economic Development Board."

**When to revisit:** After seeing Option A across several meetings. If connection phrases feel too mechanical or users don't understand the connection despite the item title, upgrade to Option B.

**Key concerns:** ~$0.01/signal cost, hallucination risk on relationship characterization (must stay factual-only per design rules D5 and language blocklist), makes rescan slower. Consider batch processing and caching. Would need careful prompt engineering to stay within factual-language guardrails.

### I11. TanStack Table May Be Overkill for Simple Data Tables
**Origin:** Financial connections freeze debug (2026-03-12) | **Priority estimate:** Medium

The financial connections table used TanStack Table for ~150 rows with basic sorting, filtering, and expand/collapse. TanStack adds 51KB of JS and significant abstraction (row models, column helpers, controlled state machines) for functionality achievable with ~50 lines of plain JS (sort an array, toggle a Set). The replacement plain HTML table is simpler to debug, has zero library overhead, and the same visual output.

**Broader question:** Are other tables in the app using TanStack where plain HTML would suffice? 11 components still use it: DivergenceTable, DonorCategoryTable, DonorOverlapTable, DonorTable, FinancialConnectionsTable, MeetingCompletenessTable, VotingRecordTable, CategoryStatsTable, CommissionRosterTable, ControversyLeaderboard, SortableHeader. TanStack earns its keep for virtualization (1000+ rows), column resizing, or complex grouping. For <200 rows with simple sorting, it's overhead.

### I12. Production-Only Bug Testing Strategy
**Origin:** Financial connections freeze debug (2026-03-12) | **Priority estimate:** Process improvement

Four consecutive "fixes" were deployed for the financial connections freeze, none of which resolved it. The core issue: the bug cannot be reproduced locally (64ms local vs 60+ seconds production). This means the standard dev-test-deploy cycle doesn't catch the actual problem.

**Possible approaches:**
- `next build && next start` locally to test production-optimized builds before deploying
- Vercel preview deployments on feature branches (already available, not used)
- Chrome DevTools Performance recording on production (user could share the trace)
- Production-specific instrumentation: `performance.mark()` / `performance.measure()` around key operations, logged to console

### D5. SortableHeader Component TanStack Dependency
**Origin:** Financial connections freeze debug (2026-03-12) | **Priority estimate:** Low

`SortableHeader.tsx` imports from `@tanstack/react-table` for its `Column` type. After removing TanStack from the financial connections table, this component is only used by other tables that still use TanStack. If those tables also migrate to plain HTML (see I11), SortableHeader becomes dead code. Not urgent, just tracking.

---

## Session Notes (2026-03-13)

### R4. Search Query Analytics Before RAG Investment
**Origin:** S10.1 implementation (2026-03-13) | **Priority estimate:** Medium

S10.1 is live with basic PostgreSQL full-text search. Before investing in S10.2 (pgvector RAG), instrument what people actually search for. The API route already logs to console on error, but successful queries aren't tracked. A lightweight `search_queries` table (query text, result count, type filter, timestamp — no PII) would reveal: what terms return zero results (RAG candidates), what entity types get filtered most, whether queries are navigational ("tom butt") vs. topical ("housing policy"). This data should drive S10.2 scope, not assumptions.

### I13. Search Snippet XSS Surface Area
**Origin:** S10.1 code review (2026-03-13) | **Priority estimate:** Low (mitigated)

`SearchResultCard` uses `dangerouslySetInnerHTML` to render `ts_headline` output (which wraps matches in `<b>` tags). The input flows: user query → `plainto_tsquery` (sanitized by PostgreSQL) → `ts_headline` (PostgreSQL-generated HTML with only `StartSel`/`StopSel` tags). The XSS risk is low because `ts_headline` generates the HTML server-side from database content (not from user input), and `plainto_tsquery` strips special characters. However, if any database content itself contains `<script>` tags (e.g., from a scraped description), `ts_headline` would pass them through. Consider adding a `ts_headline` option: `HighlightAll=false` or sanitizing the snippet client-side.

### I14. Search Result URL Fragility for Officials
**Origin:** S10.1 implementation (2026-03-13) | **Priority estimate:** Medium

The `search_site` RPC generates official URLs using `lower(regexp_replace(regexp_replace(name, '\s+', '-', 'g'), '[^a-z0-9-]', '', 'g'))` to match the frontend slug formula. This means the slug logic exists in two places: the SQL function and the frontend `council/[slug]/page.tsx`. If either changes, search results link to 404s. A `slug` column on the `officials` table (computed or stored) would be the single source of truth. Low urgency since the formula is stable, but worth noting for multi-city scaling where name formats may vary.

### V4. Search Relevance Quality Baseline
**Origin:** S10.1 launch (2026-03-13) | **Validate at:** After 1-2 weeks of operator use

Spot-check search quality for these representative queries before considering S10.2:
- **Navigational:** "tom butt", "eduardo martinez" → should return official profiles first
- **Topical:** "housing", "chevron", "police" → should return relevant agenda items
- **Specific:** "ordinance 7-24" → should find the specific resolution
- **Zero-result candidates:** abstract concepts like "transparency", "accountability" → likely zero results with FTS, prime candidates for RAG

If FTS handles 80%+ of real queries well, S10.2 can be deferred in favor of other S10/S11 work.

### I15. Feedback Button and FeedbackModal Consolidation
**Origin:** S10.3 (2026-03-13) | **Priority:** Low

The project now has two feedback entry points: (1) `FeedbackModal` opened from footer/contextual links (supports structured feedback types: flag accuracy, data correction, missing conflict, tips, general), and (2) `FloatingFeedbackButton` as a persistent bottom-right widget (general feedback only). Both use the same `useFeedback` hook and `/api/feedback` endpoint.

Currently separate because they serve different UX goals — the modal is for structured, entity-specific feedback while the floating button is for frictionless general feedback. If user research shows people confuse them or one dominates, consider consolidating into a single entry point with progressive disclosure (start simple, expand to structured types if needed).

### I16. Feedback Submission Analytics
**Origin:** S10.3 (2026-03-13) | **Priority:** Medium

The `user_feedback` table captures `page_url` and `feedback_type` but there's no operator-facing dashboard to review submissions. Before public beta, consider an operator-only `/feedback` page showing pending submissions grouped by type, with page context. Could reuse TanStack Table pattern from other pages. This would close the feedback loop — citizens submit, operator reviews and acts.

### D6. Supabase Client Eager Initialization Blocks Local Dev ➜ ✅ Fixed
Replaced eager `createClient()` with deferred Proxy. Zero changes to 53 call sites.

### D7. Tier Threshold Single Source of Truth ➜ ✅ Fixed (twice)
Canonical `TIER_THRESHOLDS_BY_NUMBER` in `conflict_scanner.py`. Fixed stale v2 values in `data_quality_checks.py` and hardcoded tier logic in legacy `scan_temporal_correlations()`. Lesson: grep ALL call sites when establishing single source of truth.

### I17. Quality Check Coverage Expansion Candidates
**Origin:** S10.4 implementation (2026-03-13) | **Priority:** Low

The current 9 checks cover the anti-patterns from the March 2026 audit. Future checks to consider as new data quality issues are discovered:
- **Stale data detection:** Tables with no new rows in N days (complement to `completeness_monitor.py`'s freshness checks, but at the row level)
- **Vote count sanity:** Meetings where ayes + noes + abstentions != expected council size (accounting for absences)
- **Agenda item financial_amount vs. text amount:** Cross-check extracted dollar amounts against the item title/description
- **Commission member term overlap:** Same person on the same commission with overlapping term dates (data entry error)
- **Contribution amount outliers:** Statistical outlier detection (z-score or IQR) rather than just the hardcoded $100 floor

---

## Session Notes (2026-03-13, S7.4 completion)

### I18. Standalone Weekly Self-Assessment Schedule ➜ ✅ Done
Added Friday weekly cron to `self-assessment.yml` with `--days 7` and `--create-decisions`.

### D8. Self-Assessment `--days 1` May Miss Cross-Day Patterns
**Origin:** S7.4 completion (2026-03-13) | **Priority:** Low

Every GH Actions self-assessment call uses `--days 1`. This means each assessment only sees journal entries from the last 24 hours. Slow trends (gradual extraction quality degradation over weeks, seasonal record count shifts) are invisible to any single assessment. The weekly `--days 7` schedule (I18) would partially address this. A monthly `--days 30` assessment could catch even longer trends, but the cost/noise tradeoff needs validation — 30 days of journal entries may exceed the useful context window for a single Sonnet call.

### V5. Self-Assessment Finding Quality After Pipeline Runs
**Origin:** S7.4 completion (2026-03-13) | **Validate at:** After 2-3 weekly pipeline runs

The self-assessment prompt produces structured JSON findings, but we haven't seen real-world output yet (only test mocks). After 2-3 pipeline runs produce real journal entries, review:
- Are findings actionable or generic? ("Data quality may degrade" vs "NetFile returned 0 records, last 10 runs averaged 847")
- Do severity levels match operator expectations?
- Are dedup keys preventing noise, or are similar findings piling up with different keys?
- Is the assessment context (journal entries) sufficient, or does it need richer metrics?

This is the first real validation of whether Phase A observation produces useful operator decisions.

---

## Session Notes (2026-03-13, Design System Integration)

### I19. CLAUDE.md Discoverability Gap for On-Demand Docs
**Origin:** Design system integration (2026-03-13) | **Priority:** Medium (process observation)

The Documentation Map in root CLAUDE.md lists files, but listing ≠ triggering. When integrating the design system docs, the initial placement (root CLAUDE.md Documentation Map + `docs/design/`) was insufficient — `web/CLAUDE.md` had zero references, meaning frontend work wouldn't be prompted to consult the rules. Fixed by adding a blockquote in `web/CLAUDE.md`'s Design System section.

**Broader pattern:** Any on-demand doc that should be consulted during a specific *type* of work needs a pointer in the CLAUDE.md that loads for that work context, not just in the root Documentation Map. The Documentation Map is an index for humans; the sub-CLAUDE.md pointers are triggers for AI. Future on-demand docs should always ask: "which CLAUDE.md loads when I'd need this?"

### I20. S11.1 Partial Completion Creates Design System Bootstrap
**Origin:** Design system integration (2026-03-13) | **Priority:** Observation

The design philosophy synthesis (done externally) produced the "design principles document" output that S11.1 called for, ahead of the sprint's planned execution. This means S11.1 is no longer a cold start — the remaining deliverables (component hierarchy, navigation rethink, progressive disclosure strategy, page-level redesigns) can build on established rules rather than deriving them. The 34 enforceable rules + 3 seeded debt items + 5-persona validation provide concrete starting points for component audits. The "Rule of Three" growth path (don't split rules into component specs until corrected 3 times) prevents premature abstraction in the design system itself.

---

## Session Notes (2026-03-13, B.49 Consent Calendar Fix)

### D9. `convert_escribemeetings_to_scanner_format` Missed Header Skip ➜ ✅ Fixed
Two code paths diverged on section header skip. Fixed in `run_pipeline.py`. Root cause of 125 uninformative scanner flags.

### D10. `temporal_flags` NameError in Cloud Pipeline Journal Log ➜ ✅ Fixed
Stale variable reference after S9.5 D1 cleanup. Pipeline crashed at journal log step.

### I21. Consent Block Vote Only Attached to First Sub-Item ➜ ✅ Fixed
Consent block vote now attached to ALL non-pulled consent items. Migration 033 backfills. 3 new tests.

### I22. Minutes Extraction May Produce Bare-Letter Item Numbers
**Origin:** B.49 (2026-03-13) | **Priority:** Low

The scanner's bare-letter header skip uses `^[A-Z]+$` regex. Minutes extraction from Archive Center PDFs uses LLM extraction, which might produce item numbers like "H-1" (with hyphens) for legitimate items. The regex correctly allows these through. However, if the LLM ever produces bare-letter items for legitimate content (unlikely but possible), the scanner would silently skip them. Monitor during next batch extraction.

---

## Session Notes (2026-03-14, Cross-Committee Aggregation Fix)

### D11. Scanner Aggregated by Committee Name, Not Candidate ➜ ✅ Fixed
Changed aggregation to (donor, candidate) via `extract_candidate_from_committee()`. Cross-committee donations now merge.

### D12. Cloud Pipeline Flag Save Used Non-Existent v2 Attributes ➜ ✅ Fixed
Latent crash since v3 scanner migration — `cloud_pipeline.py` accessed v2 `ConflictFlag` attributes. Fixed.

### D13. Retrospective Rescans Didn't Supersede Old Flags ➜ ✅ Fixed
`supersede_flags_for_meeting()` was gated on `"prospective"` only. Fixed to supersede for any scan mode.

### I23. CAL-ACCESS Reversed Name Format Not Merging with NetFile
**Origin:** Oct 28 rescan review (2026-03-14) | **Priority:** Low

After the cross-committee fix, Diana Wear's donations to Gayle McLaughlin appear as two separate flags: one from NetFile ("Gayle McLaughlin for Richmond City Council 2020") and one from CAL-ACCESS ("MC LAUGHLIN FOR LIEUTENANT GOVERNOR 2018; GAYLE"). The `extract_candidate_from_committee()` function handles the reversed format, but the extracted names ("Gayle McLaughlin" vs "Gayle Mc Laughlin") don't normalize identically due to the space in "Mc Laughlin". Would need fuzzy candidate matching or an alias table for cross-source candidate dedup.

### I24. Full Batch Rescan Needed for Cross-Committee Fix ➜ Merged into I26
**Origin:** Rescan (2026-03-14) | **Merged:** 2026-03-15

Consolidated into I26 (combined rescan trigger checklist) to avoid running multiple partial rescans.

### D14. Stats Page Queries Do Client-Side Aggregation Over 14K+ Rows ➜ ✅ Fixed
Replaced client-side aggregation with 3 SQL RPC functions (migration 038). ~50 round-trips → 1 query each.

### D15. Audit Other Pages for Unnecessary `force-dynamic` ➜ ✅ Fixed
Audited 18 pages. `/financial-connections` and `/council/patterns` switched to ISR. `/search` kept `force-dynamic` (real-time input).

---

## Session Notes (2026-03-14, CAL-ACCESS First Run + IE Detector Recovery)

### I25. CAL-ACCESS First Production Run ➜ ✅ Complete
First sync: 9,258 records loaded (contributions + independent expenditures). Dashboard "never run" was Vercel CDN cache.

### D16. Uncommitted IE Signal Detector Recovered ➜ ✅ Committed
Recovered ~500 lines of uncommitted IE signal detector (signal #6) with 83 tests. Lesson: commit incrementally in long sessions.

### I26. Full Batch Rescan — Combined Trigger Checklist ➜ ✅ Complete
All 4 accumulated improvements (connection clause, cross-committee fix, IE detector, supersede fix) propagated via batch rescan.

---

## Session Notes (2026-03-15, Pipeline Contract Enforcement)

### D17. PyMuPDF NUL Byte Extraction Pattern ➜ ✅ Fixed
Defense in depth: strip `\x00` at extraction AND at DB boundary (`db.py:sanitize_text()`). Covers all PDF extraction paths.

### D18. `_FakeFlag` / `ConflictFlag` Attribute Divergence ➜ ✅ Fixed
Replaced `_FakeFlag` test class with `_make_flag()` factory using real `ConflictFlag` instances. Lesson: never shadow real dataclasses in test fixtures.

### I27. Schema-Contract Tests as Drift Detection ✅ Implemented
`test_schema_contracts.py` validates columns referenced in Python SQL exist in Supabase. 7 tables covered. Maintenance: add new columns to `SCHEMA_CONTRACTS`.

### I28. `sanitize_text()` DB Boundary Defense Pattern ✅ Implemented
`db.py:sanitize_text()` at 5 insertion points. Extend for future encoding issues rather than per-caller fixes.

### D19. Data Quality Checks Cascading Transaction Abort ➜ ✅ Fixed
Isolated check failures with per-check `conn.commit()` / `conn.rollback()`. Pattern: psycopg2 aborts entire transaction on error.

### V6. Pipeline Contract Enforcement Effectiveness
**Origin:** Contract enforcement implementation (2026-03-15) | **Validate at:** Next 3 pipeline runs

Three contract enforcement mechanisms were added this session:
1. **Schema-contract tests** (`test_schema_contracts.py`) — catch column drift at test time
2. **DB CHECK constraint** (migration 036) — catch invalid `decision_type` at write time
3. **`sanitize_text()` boundary** (`db.py`) — catch encoding issues at write time

Monitor whether these prevent future pipeline crashes vs. the pre-enforcement pattern of discovering issues in production. Expected: zero column-name or decision-type crashes. The NUL byte defense should be invisible (silently strips rather than crashing).

---

## Session Notes (2026-03-15, B.44 Socrata Regulatory Data)

### I29. Socrata Text Date Format Fragility
**Origin:** B.44 permit_trak metadata (2026-03-15) | **Priority:** Low

`permit_trak` uses text-type date fields with format `"Jan 14 2013 12:00AM"` while other datasets use ISO `calendar_date`. The `_parse_socrata_date()` parser handles both, but if Socrata ever changes the text format, permit date parsing silently returns `None` instead of crashing. Monitor after first full sync — if many permits have `NULL` applied_date, the text parser needs updating.

### I30. Regulatory Cross-Reference Ready for B.45
**Origin:** B.44 completion (2026-03-15) | **Priority:** Medium

Three high-value cross-reference surfaces are now available:
1. **`city_licenses.normalized_company`** — match against `contributions.donor_name` and `city_expenditures.normalized_vendor` to find businesses that are both licensed in Richmond and donating to campaigns
2. **`city_projects.resolution_no`** — join against `motions.motion_text` or `agenda_items.title` containing the same resolution number to link development projects to council votes
3. **`city_permits.applied_by`** — currently just initials (e.g., "JD", "PH"), not entity names. Less useful for cross-referencing until we determine whether full applicant names are available elsewhere (possibly in the permit documents themselves)

**Implication for B.45:** Items #1 and #2 are immediately actionable. Item #3 needs investigation — the `applied_by` field appears to be staff initials, not external applicants. The actual permit applicant identity may be in linked documents or a different dataset.

### V7. Regulatory Data Volume and Quality After First Sync ✅ Validated
First full sync: 269,751 records (permits 177K, service requests 44K, code cases 37K, licenses 6K, projects 5K). All estimates matched. Idempotent re-run confirmed.

---

## Session Notes (2026-03-15, S8.3 Commission Meeting Extraction)

### D20. Fuzzy Find 3-Column Unpack Bug ➜ ✅ Fixed
`_fuzzy_find_official()` unpacked 2 variables from 3-column query. Latent until commission extraction exercised fuzzy path.

### D21. Per-Document Transaction Isolation in Sync Functions ➜ ✅ Fixed
Same root cause as D19 — single transaction for multi-record sync. Fixed with per-document commit/rollback.

### I31. Commission Extraction Quality Observations
**Origin:** S8.3 extraction review (2026-03-15) | **Priority:** Low

Two minor extraction artifacts observed across 4 commission AMIDs:
1. **Presiding officer field** sometimes captures the mayor's name from the meeting header instead of the actual commission chair. Affects commissions where the header includes "Mayor X" as appointing authority. Low impact since presiding officer is display-only, not used for analysis.
2. **`<UNKNOWN>` attendance entries** appear in some commission meetings where the LLM couldn't parse attendee names from the PDF format. These are harmless (filtered out during official resolution) but could be cleaned up with a post-extraction filter.

### I32. 1,530 Commission Documents Remain for Future Extraction
**Origin:** S8.3 initial sync (2026-03-15), updated 2026-03-16 | **Priority:** Medium

Initial extraction ran 20 documents per AMID. Verified counts (2026-03-16):

**Core 4 AMIDs (~$52):**
- Design Review Board (AMID 61): 316 remaining (of 326)
- Personnel Board (AMID 132): 279 remaining (of 300)
- Planning Commission (AMID 75): 160 remaining (of 182)
- Richmond Rent Board (AMID 168): 118 remaining (of 128)

**Secondary AMIDs (~$39):**
- Design Review packets (AMID 77): 247 remaining (0 extracted)
- Design Review other (AMID 78): 209 remaining (0 extracted)
- Rent Board older (AMID 169): 107 remaining (0 extracted)
- Personnel Board older (AMID 133): 94 remaining (0 extracted)

**Total: 1,530 docs × ~$0.06 = ~$92.** Core 4 only: ~$52. Can be run incrementally per-AMID via `sync_minutes_extraction`. Not all docs are extractable minutes — some are attachments/staff reports that will produce empty results.

**Key finding (2026-03-16):** eSCRIBE does NOT have commission meetings — only City Council (regular, special, swearing in). All commission meeting data comes exclusively from Archive Center PDF minutes. The `commissions_escribemeetings` config is aspirational only. Fixed name mismatches in config and added Richmond Housing Authority to commissions table.

### V8. Commission Meeting Data Quality After Full Extraction
**Origin:** S8.3 (2026-03-15) | **Validate at:** After full extraction run

After running full extraction (no `--limit`), verify:
- Meeting dates distribute correctly across years (no clustering that suggests date parsing issues)
- Presiding officer names are commission-appropriate (not mayor names)
- Agenda item counts are reasonable for commission meetings (typically 5-15, not 50+ like council)
- Body resolution correctly assigns all meetings to the right body (no stray City Council assignments)

## Session Notes (2026-03-15, B.45/B.53 Permit-Donor + License-Donor Cross-Referencing)

### I33. Permit Applicant Name Quality Unknown
**Origin:** B.45 implementation (2026-03-15)

`city_permits.applied_by` quality is unknown. Socrata data may have inconsistent applicant names (individual vs. company, abbreviations). After first permit sync, should profile: (1) How many permits have non-empty `applied_by`? (2) Name length distribution (short = false positive risk, filtered at 10 chars). (3) Overlap with known campaign donors? (4) Are applicants companies or individuals? Affects whether `signal_permit_donor()` produces useful signals or noise.

### I34. Business License DBA Coverage Gap
**Origin:** B.45 implementation (2026-03-15)

`signal_license_donor()` matches both company name and DBA name against agenda text and contributions. But DBA names may not be populated in all Socrata records. After first license sync, check: what percentage of licenses have non-empty `company_dba`? If low, the DBA matching path adds complexity without much value.

### R5. Corroboration Boost Effectiveness After Regulatory Data Sync
**Origin:** B.45 implementation (2026-03-15)

The key hypothesis: adding permit and license signal types will push some findings from tier 2 to tier 1 via the 1.30x corroboration boost (3+ signal types). After running regulatory data sync + batch rescan, measure: (1) How many flags gain a corroboration boost from permit_donor or license_donor signals? (2) Do any single-signal tier-2 flags graduate to tier 1 via cross-referencing? (3) False positive rate for the new signal types.

### V9. Regulatory Cross-Reference Signal Quality
**Trigger:** After first `socrata_permits` + `socrata_licenses` sync AND batch rescan
**Expected:** permit_donor and license_donor signals should be rare but high-signal — most permits are routine and most license holders are not donors.
**Concern:** If Richmond's permits are heavily dominated by a few large contractors who also donate (Chevron, major construction firms), these signals may cluster on the same entities already flagged by `donor_vendor_expenditure`. Corroboration boost is correct in this case (multiple independent signals confirming the connection), but the marginal intelligence gain per new signal type may be low. Track: unique entities flagged ONLY by permit/license signals (not already flagged by other types).

### B.53. Business Suffix Normalization Edge Cases
**Origin:** B.52 implementation (2026-03-15)
**Observation:** The `_BUSINESS_SUFFIX_RE` regex handles common US suffixes (Inc, LLC, Corp, Ltd, LP, LLP, PLLC, PA, NA, PC) but doesn't cover international forms (GmbH, S.A., Pty Ltd, PLC). Richmond data is overwhelmingly US entities, but multi-city scaling may surface international suffixes. Also, "The XYZ Company" pattern isn't stripped — "Company" and "Co" are in the generic words list but not in the suffix regex since they're legitimate business name components (not just legal suffixes).
**Recommendation:** Monitor false negatives in production. If international entities appear, extend the regex. Low priority until multi-city launch.

### I35. Anomaly Factor Calibration After Production Data
**Origin:** B.51 implementation (2026-03-15)
**Observation:** The z-score thresholds (1σ→0.3, 2σ→0.5, 3σ→0.7, 4σ→0.9) and percentile floors (p95→0.7, p99→0.9) were chosen based on statistical convention, not empirical calibration against Richmond contribution data. The temporal boost (+0.1 within 30 days) is a reasonable starting point but the window and magnitude are untested.
**Recommendation:** After the next batch rescan with baselines active, profile the anomaly_factor distribution. If >20% of flags hit 0.9+ or <5% exceed 0.5, the thresholds need adjustment. The 50-contribution minimum for baselines may also be too high for smaller cities — track how many Richmond committees fall below threshold.

### I36. Vote Explainer Historical Context Quality Assessment
**Origin:** H.16 implementation (2026-03-15)
**Observation:** Historical context relies entirely on the `category` field from agenda item extraction. Categories are AI-assigned during extraction, so miscategorized items pollute voting history. A council member's "housing" voting record is only as good as the category labels on their votes. Also, the current implementation counts every motion separately — a single agenda item with an amendment motion and a final passage motion counts as 2 votes, which may inflate totals.
**Recommendation:** After generating 10-20 explainers with historical context, review whether the LLM is using the context well or if it's adding noise. Check whether double-counting from multi-motion items is distorting the stats. Consider deduplicating by agenda_item_id if needed.

### D22. Proportional Specificity Changes Existing Confidence Scores ➜ Resolved via batch rescan
Proportional scoring replaced binary 0.7x penalty. Stale DB values updated in I26 batch rescan.

### R6. ProPublica API Officer Data Gap
**Origin:** B.46 implementation (2026-03-15)

ProPublica Nonprofit Explorer API v2 does NOT expose individual officer names from Form 990 Part VII. The API provides org-level data (EIN, name, financials, filing summaries) but officer extraction requires parsing IRS 990 XML bulk data from AWS S3 (`s3://irs-form-990/`). For entity resolution to include nonprofit officer/board member names, need either: (1) IRS 990 XML parser targeting Part VII Schedule J (compensation data), or (2) Open990 API as intermediary. Current ProPublica integration provides structural confirmation that employer names are real nonprofits — useful for match confidence but not for discovering person→org relationships beyond employment.

### I40. Entity Graph Batch Loading for Batch Scanner
**Origin:** B.46 implementation (2026-03-15)

`scan_meeting_db` auto-loads entity graph per meeting. For batch scans (784+ meetings), this means 784 identical queries. `batch_scan.py` should pre-load entity graph once and pass it to all `scan_meeting_db` calls, same pattern used for contributions and form700_interests. Low effort, high performance impact once entity registry has data.

### V10. Entity Resolution Quality After ProPublica Sync
**Trigger:** After first `python data_sync.py --source propublica --sync-type full`
**Expected:** ProPublica should match employer names for donors who work at nonprofits. Richmond has several prominent nonprofits (SEIU, community foundations, environmental orgs).
**Measure:** (1) How many of the ~4K distinct employer names match ProPublica nonprofits? (2) Match confidence distribution. (3) Do any matches produce new LLC ownership chain signals on batch rescan? (4) False positive rate — are any employers incorrectly matched to nonprofits with similar names?

### D12. Normalize `_normalize_name` Across Modules
**Origin:** B.46 implementation (2026-03-15)

Seven separate `_normalize_name` functions exist across modules (db.py, conflict_scanner.py, council_profiles.py, courts_scraper.py, appointment_extractor.py, payroll_ingester.py, form700_extractor.py). All do essentially the same thing (lowercase + strip + collapse whitespace). Should consolidate into a shared utility in `text_utils.py` or similar. Not urgent but increases maintenance cost and divergence risk.

---

## Plain Language & Citizen Clarity Improvements (2026-03-16)

_Batch of interconnected improvements to how meeting content is presented to citizens. Informed by California Voter Guide principles and plain language research. All items target S10 (Citizen Discovery) or a dedicated plain language sprint._

### R7. California Voter Guide & Plain Language Standards Research ⚡ HIGH PRIORITY
**Origin:** Session discussion (2026-03-16)

Current plain language prompt has 11 informal rules and a grade-6 reading level target. No formal standard referenced. Research needed before prompt rewrite.

**Research targets:**
- California Voter Guide — Legislative Analyst's Office fiscal impact style, Attorney General title conventions
- Federal Plain Language Act (2010) / plainlanguage.gov guidelines
- GOV.UK Content Design style guide (global gold standard, extensively A/B tested)
- Center for Civic Design field guides (ballot-specific plain language)
- Flesch-Kincaid readability scoring — should we measure programmatically?

**Deliverable:** Updated `plain_language_system.txt` prompt grounded in tested standards. Depends on operator running research prompt in Claude Chat.

### I41. Plain English Summaries Expanded by Default, Official Text Collapsed ⚡ HIGH PRIORITY
**Origin:** Session discussion (2026-03-16)

Currently both plain language summary and official description show together when an agenda item is expanded. The useful thing (plain English) should be the default; the reference thing (official text) should be one click away. This is the single biggest UX win for citizen comprehension.

**Implementation:** Add a separate expand/collapse toggle within each agenda item that defaults the official text to collapsed. Plain English summary stays always-visible when item is expanded.

### I42. Better Formatting for Official Agenda Text ⚡ HIGH PRIORITY
**Origin:** Session discussion (2026-03-16)

Official agenda descriptions render as a single `<p>` tag — no paragraph breaks, no bullets, no structure. Government text often has implicit structure (WHEREAS clauses, numbered conditions, financial breakdowns) that gets flattened into a wall of text.

**Options:** (1) Parse line breaks and detect list patterns at render time (frontend). (2) Pre-process during extraction to add markdown/HTML structure (pipeline). (3) Both — structured extraction + smart rendering. Option 3 is best but highest effort.

### I43. Meeting-Level 5-Bullet Summary for Home Page
**Origin:** Session discussion (2026-03-16)

Home page `LatestMeetingCard` currently shows only counts (items, votes, flags). Should show 5 bullet points summarizing the most significant items from the latest meeting.

**Implementation:** New pipeline-time generation step. Runs after all item-level summaries exist, uses them as input (cheaper than re-reading raw agenda text). New column on `meetings` table (e.g., `meeting_summary TEXT`). New generator script `generate_meeting_summaries.py`.

### I44. Yes/No Vote Structure in Plain Language Summaries
**Origin:** Session discussion (2026-03-16)

Current summaries describe items affirmatively, as if they passed ("Approves a $500K contract..."). Should instead describe what the item *does* in a neutral, decision-support format inspired by the California Voter Guide:
- "A 'yes' vote will: [consequences]"
- "A 'no' vote will: [consequences]"

Uses plain "yes/no" (D4 plain language) instead of "aye/nay" (procedural terms reserved for vote breakdown component where CivicTerm tooltip maps to official record).

**Depends on:** R7 (plain language research) completing first to inform prompt rewrite.

### R8. Richmond Municipal Code Chapter 2.42 — Local Campaign Finance Rules ✅ RESOLVED
$2,500/person/cycle (Sec. 2.42.050). Full details in `docs/research/california-ethics-laws.md`.

### I45. Proceeding Type Classification for Existing Agenda Items ⚡ HIGH PRIORITY
**Origin:** Signal significance spec (2026-03-16)

The signal significance architecture (scanner v4) requires classifying every agenda item as entitlement/legislative/contract/appointment. This is the gating capability for Tier A legal threshold detection. Keyword-based heuristic with LLM fallback recommended. Need to run the classifier across all existing agenda items and measure accuracy against a manual sample.

**Depends on:** Signal significance spec finalization.

### I46. Cross-Meeting Pattern Detector Pipeline Step
**Origin:** Signal significance spec (2026-03-16)

New pipeline step that runs after individual meeting scans. Groups flags by (official, entity) pair across all meetings, computes pattern metrics (frequency, financial concentration, temporal cycling, multi-official coordination), and writes to a new `pattern_flags` table. Five pattern types defined in spec. This is the Tier B engine.

**Depends on:** Signal significance spec finalization, I45 (proceeding type classification).

### D23. Scanner v3 $250 Threshold Is Outdated ➜ ✅ Fixed (S19)
Levine Act threshold updated to $500 (SB 1243, effective 2025-01-01). Historical meetings still use $250.

### I47. Pipeline Lineage System ➜ ✅ Complete
Full end-to-end lineage: 16 sources, 39 tables, 100+ field mappings, 20 CI tests, 4-layer enforcement. CLI: `src/pipeline_map.py` (trace, impact, rerun, diagram, validate, field). Future: `stale` command, auto-discovery, multi-city DAG.

### D24. RLS Policy Enforcement Gap ➜ ✅ Resolved
18 tables invisible to frontend (RLS enabled, no SELECT policy). Migration 042 backfills. `test_rls_policy_coverage.py` (5 tests) prevents recurrence via CI.

### D25. Diagnostic Overconfidence — Verify Each Symptom Independently ➜ Process lesson
Three stacked bugs (status case mismatch, missing timeline data, stale alert logic) each required independent fix. Rule: verify each symptom independently.

### I48. NextRequest Timeline Backfill as Standard Pipeline Step
**Origin:** Public records page fix (2026-03-17) | **Status:** Suggested

The initial NextRequest sync only fetches request metadata, not timeline events. `closed_date` and `days_to_close` require a separate incremental sync that fetches each request's timeline. This should be a standard two-phase sync: (1) bulk request list, (2) timeline enrichment pass. Currently requires manual second run. Could be wired into n8n as a chained step.

### I49. "Never Synced" Alert Is Correct — Don't Suppress It
**Origin:** Staleness alert investigation (2026-03-17) | **Status:** Design decision

Four data sources (nextrequest, calaccess, socrata_payroll, socrata_expenditures) had sync functions built but never actually ran. The staleness alert correctly flagged them. The fix was to run the syncs, not suppress the alerts. Lesson: if a source has a sync function and a freshness threshold, it should be synced. Alerts for "never synced" are doing their job — the bug is building pipelines that gather dust.

### I50. Bulk Document Download — NextRequest + Archive Center ⚡ HIGH PRIORITY
**Origin:** Operator request (2026-03-17) | **Status:** Roadmap — ready to build. **Documents API validated (April 2026).**

Download the full Richmond government document corpus for local analysis and potential hosting.

**Corpus size estimates (March 2026):**

| Source | Documents | Est. size | API/access |
|--------|-----------|-----------|------------|
| NextRequest (CPRA responses) | 19,744 | 3–15 GB | `/client/documents` API (discovered, paginated, 50/page). Per-request docs via `/client/request_documents?request_id=X` (includes S3 URLs). No auth required. |
| Archive Center (city website) | ~13,200 | 1–12 GB | Sequential ADIDs 1–17,431 (~76% density). `/Archive.aspx?ADID=X` returns raw files. No auth. |
| **Combined** | **~33,000** | **~8–15 GB realistic** | Fits on a thumb drive |

**NextRequest file type mix:** 32% PDF, 22% DOCX, 20% XLSX, 14% PPTX, misc (zip, msg, mov, pst).

**Download infrastructure needed:**
- Pagination over `/client/documents` (395 pages × 50 docs)
- S3 URL resolution via `/client/request_documents?request_id=X` per request
- ADID iteration 1–17,431 for Archive Center (filter `content-type != text/html`)
- Resume/checkpoint logic (don't restart on interruption)
- Organized storage: `data/raw/nextrequest/{request_id}/` and `data/raw/archive/{amid}/{adid}.pdf`
- 500ms rate limiting (NextRequest), modest rate for Archive Center

**Legality:** Strong. CPRA records are explicitly released public records. Archive Center documents are published government records. Both served to any visitor without auth.

**Validated (April 2026 — request 24-428 proof-of-concept):**
- Documents API endpoint: `GET /client/request_documents?request_id={pretty_id}&page_number=N` (25 docs/page). Discovered by reverse-engineering Vue.js SPA bundle (`api-CqnnFGtv.js`). Now wired into `nextrequest_scraper.py` via `_fetch_request_documents()` and `get_request_detail(include_documents=True)`.
- Each document has `asset_url` pointing to S3 (`nextrequestdev.s3.amazonaws.com/{city_slug}/{request_id}/{uuid}.{ext}`). Direct download, no auth.
- Also has `document_scan` nested object with upload_date (ISO), file_type, visibility, file_size.
- Proof of concept on request 24-428 (Divestment Policy): 115 docs, 68 MB, 108/115 (93%) had extractable text via PyMuPDF. 934K chars across 555 pages. Search tool: `src/search_nextrequest_docs.py`.
- **What's left for bulk:** iterate all ~2,400 requests calling `include_documents=True`, download S3 files, extract text, load to Document Lake. The API and download patterns are proven — remaining work is scale (checkpoint/resume, storage management, DOCX/XLSX extraction).

### R9. Local LLM Triage Layer for Document Analysis
**Origin:** Operator request (2026-03-17) | **Status:** Research/design

Use a local LLM (Ollama) as a first-pass triage layer to classify and score documents before running expensive Claude API extraction. Operator has a 4070 (12GB VRAM) — supports 8B models comfortably, 14B quantized (Q4) at the limit.

**Proposed architecture:**
1. **Download** full corpus (~33K docs, ~8-15 GB) — I50
2. **Text extraction** via PyMuPDF — $0, already built
3. **Local LLM first pass** (Ollama + Qwen 2.5 14B Q4 or Llama 3.1 8B):
   - Document type classification (contract, correspondence, financial, policy, legal, permit, report)
   - Entity extraction (names, organizations, amounts, dates)
   - Relevance scoring (flag high-value docs for deep analysis)
   - Prompt iteration at $0/cycle (vs ~$70/cycle over full corpus via API)
4. **Claude API surgical pass** — only on documents flagged by local triage

**What the local model can handle well (8-14B):**
- Document classification — simple categorization
- Text extraction/cleanup — pattern-based
- Keyword/entity tagging — structured output
- Prompt development iteration — test on 100-doc samples

**What needs Claude API:**
- Nuanced contract analysis, cross-referencing
- Conflict of interest detection across documents
- Long-context reasoning on large PDFs
- Production-quality structured extraction

**Revised cost estimates with triage:**

| Approach | Documents analyzed via API | Est. Claude API cost |
|----------|--------------------------|---------------------|
| No triage (all docs) | ~33,000 | ~$2,000–2,300 |
| Local triage → top 20% | ~6,600 | ~$400–460 |
| Local triage → top 10% | ~3,300 | ~$200–230 |

---

## Session Notes (2026-03-19, Sprint 13 Scoping — Influence Transparency)

### R10. Astroturf Detection Research & Data Source Assessment
**Origin:** 2026-03-19

The operator conducted extensive research on corporate astroturfing detection techniques. Key findings mapped to Richmond Commons:

**Data source readiness:**
- ProPublica Nonprofit Explorer API: ✅ Already integrated (propublica_client.py)
- CA SOS bizfile API: Schema built (Migration 040), API key submitted 2026-03-15 (status: Submitted, CBC API Production)
- FPPC Form 803 (behested payments): No public API found. Options: portal scrape, CPRA request for machine-readable data
- Richmond lobbyist registrations (Chapter 2.54): Paper/PDF filings in Document Center FID=389. Scrape + Claude API extraction viable.
- Cross-jurisdiction speaker data: Oakland (Legistar), SF (SFGOV) — needs investigation

**Key investigative techniques from research:**
- Shared registered agents/addresses = #1 astroturf indicator (requires SOS data)
- Org formation date proximity to procurement decisions
- Cross-jurisdiction speaker deployment (same people at multiple Bay Area councils)
- Fiscal sponsorship chain detection (advocacy groups as "projects" under 501(c)(3)s)
- Domain registration timing + shared Google Analytics codes
- Public comment template analysis (identical language = coordinated campaign)

**Live test case:** Flock Safety / East Bay Alliance for Public Safety / Edward Escobar. Research doc: `E:\Downloadz\compass_artifact_wf-3e811ed7-06fd-4ad4-b113-5244401373fb_text_markdown.md`

### I51. Business Model Refinement: Raw Data Free, Influence Graph is Product
Strategic clarification logged in DECISIONS.md. Raw public data free; cross-referenced influence graph is premium product. Moat = entity resolution intelligence.

### I52. Influence Map — Unified Discovery + Depth UI ➜ ✅ Complete (S14)
Full spec at `docs/specs/influence-map-meetings-redesign-spec.md`. Sentence-based narratives, item + official centers, calendar discovery. Delivered in S14.

### I53. Civic Glossary Seed Data for CivicTerm Integration
Seed data at `web/src/data/civic-glossary.ts`. Next step: DB migration for `civic_glossary` table (full T5 compliance). Bundle with next CivicTerm production use.

### R11. Calendar Component Patterns for Monthly Grid
**Origin:** 2026-03-19

Phase B of the Influence Map spec needs a monthly calendar grid for /meetings. CSS grid, ~35 cells, no heavy library. Research: what patterns work for sparse calendars (2 events/month)? Inline expansion below calendar row on click. URL-encoded month/year for shareability. Consider: how to handle months with 0 meetings (show empty grid vs. skip to next).

### R12. Behested Payment Absence Detection
**Origin:** S13 behested payments research session (2026-03-20) | **Priority estimate:** Medium (novel signal type)

When an official publicly solicits a payment (detectable via meeting minutes text patterns: "I encourage [entity] to donate/fund/support...") but no corresponding FPPC Form 803 filing appears within 30-90 days, the absence is a meaningful signal. Not an allegation — filings may exist in systems we don't monitor, amounts may be below the $5,000 threshold, or filings may be pending.

**Key insight from research:** Three tiers of behested payment patterns exist in the Bay Area — criminal (Nuru/SF, conviction), legal-pattern (Farrell/SF, visible but not prosecutable), and structural-open (Brown/Oakland, fully disclosed). Richmond Commons' value is in surfacing the Farrell/Brown-tier patterns that are legal, open, and still worth mapping.

**Implementation concept:** `signal_behested_absence` detector in S13.5 (astroturf suite). See `docs/research/behested-payment-absence-detection.md` for full research.

**Dependencies:** Local Form 803 filing access (CPRA request needed — see D5), meeting text search (S10, complete).

### R13. Revenue Dependency as Influence Context
**Origin:** S13 behested payments research session (2026-03-20) | **Priority estimate:** Medium (contextual enrichment)

A $50K behested payment from Chevron reads differently when Chevron is also ~24% of Richmond's general fund revenue ($58.8M in taxes and settlement payments). Transactional signals (contributions, behested payments) gain context when paired with structural financial relationships.

**Key framing:** This is not adversarial. The $550M Chevron settlement was good policy — avoided litigation, delivered more money, progressive coalition supported it unanimously. But the structural shape (single entity providing ~24% of revenue) is context citizens deserve alongside transactional disclosures.

**Data source:** Socrata `budgeted_revenues` (wvkf-uk4m) already synced. Needs entity-level revenue attribution analysis. See `docs/research/revenue-dependency-context.md` for full research.

**Display concept:** Contextual annotation on S14 influence maps when an entity is both a transactional signal source AND a major revenue contributor.

### I54. MCP Server Roadmap — Public Data Infrastructure as a Service
**Origin:** 2026-03-20 | **Priority estimate:** Path B+C (horizontal scaling + data infrastructure)

NetFile MCP (`netfile-mcp` v0.1.0) published to PyPI. Any Claude user can query ~220 California agencies' campaign finance data with zero setup. Four more Tier 1 candidates identified — all pure API clients with zero DB coupling, ready to extract:

1. **eSCRIBE Meetings MCP** — council meeting discovery, agenda parsing, attachment download (most novel — no other MCP for this)
2. **ProPublica Nonprofits MCP** — IRS Form 990 lookup, employer→nonprofit resolution (broadest audience)
3. **Socrata Open Data MCP** — query any of 1000+ Socrata portals nationwide (biggest reach)
4. **FPPC Behested Payments MCP** — behested payment lookups by official/city (most niche, unique dataset)

All follow `mcp/{name}/` monorepo pattern with independent `pyproject.toml`. Each is a separate PyPI package.

**Before publishing next MCP:** Scope the PyPI API token to `netfile-mcp` at https://pypi.org/manage/account/token/ (create new scoped token, delete old unscoped one). Then create a new scoped token for the next package. Human action required each time.

### D26. Broken Test Import: `test_nextrequest_city_config.py`
**Origin:** 2026-03-20 (discovered during CI fix investigation) | **Priority:** Low

`tests/test_nextrequest_city_config.py` imports `_parse_document_list` from `nextrequest_scraper`, but that function no longer exists. The test file fails to collect (ImportError), silently reducing test coverage. Not caught by CI because `pytest -k "conflict"` or similar selective runs skip it, and the main CI may not be running this test file.

**Fix:** Either update the import to the current function name, or remove the test if the functionality was refactored away.

### I55. Domain & Brand Registration ✅ Done
Four domains registered on Cloudflare. Brand clearance completed. USPTO trademark deferred to post-launch.

### R14. Dynamic Topic Discovery — Taxonomy Architecture
**Origin:** 2026-03-22 (S14 planning session) | **Priority:** S14 prep work

The current topic system has two static layers: 14-category enum (LLM-assigned at extraction, database-backed) and 7 local issues (hardcoded keyword lists in `local-issues.ts`). Neither captures **emerging topics** — issues that dominate several meetings then fade (Flock Safety cameras, Pt. Molate Hillside Park, Chevron modernization).

**Decision (2026-03-22):** Hybrid approach (Option C) — LLM extraction at ingestion + operator curation.

**Architecture:**
- `topics` table: id, name, slug, description, first_seen, last_seen, item_count, status (proposed/active/merged/archived)
- `item_topics` junction table: agenda_item_id, topic_id, confidence, source (llm/operator/keyword)
- Extraction prompt addition: "Identify the specific civic issue, project, or ongoing saga this item relates to (if any)"
- Operator curation: periodic review of proposed topics, merge duplicates, rename for consistency, promote to active
- Categories remain structural (policy domain). Topics are emergent (specific issues/projects within domains)

**Key questions for implementation:**
- Naming consistency: will the LLM call it "Point Molate" vs "Pt. Molate" vs "Point Molate Development"? Needs normalization or fuzzy matching
- Retroactive assignment: should batch job tag historical items, or only new items going forward? Cost estimate needed
- Local issues migration: should existing 7 local issues become seed topics in the new table?

**Relationship to S14 B6:** Category drill-through pages are the category-level view. Topic pages would be a finer-grained view within categories. Both coexist — `/meetings/category/housing` shows all housing items, `/topics/point-molate` shows only Point Molate items (which happen to be in the housing category).

### I57. Contributor Type Classification ➜ ✅ Complete (S14-P1)
`contributor_classifier.py` with dual-path classification. NetFile uses name-pattern inference; CAL-ACCESS `ENTITY_CD` now preserved. Migration 048. 51 tests.

### I59. AI-Delegated Topic Curation (Multi-City Scaling Dependency)
**Origin:** 2026-03-22 (operator directive during S14-P2 implementation) | **Priority:** Scale-blocking

Topic review, merge, and lifecycle management cannot remain operator-curated beyond Richmond. At 19,000 cities, even one pass per city is impossible manually. This must become an AI-delegable autonomy zone.

**Current state:** Topics are keyword-seeded (14 Richmond issues) with planned LLM extraction. The `topics` table has `status` (active/merged/archived) and `merged_into_id` for merge tracking. But curation — deciding which LLM-discovered topics are real, which are duplicates, which to merge — is implicitly an operator task.

**Required for multi-city:** AI autonomously (1) discovers topics from agenda text via LLM extraction, (2) normalizes naming ("Point Molate" vs "Pt. Molate"), (3) detects and merges duplicates (fuzzy slug matching + semantic similarity), (4) proposes lifecycle changes (promote proposed→active, archive stale topics), (5) adapts keyword lists per city. Operator role shifts from per-topic curation to periodic audit of AI topic decisions (same pattern as Autonomy Zones Phase B).

**Dependency chain:** S14-P2 (done) → LLM topic extraction at ingestion → AI topic normalization/merge → Autonomy Zones Phase B (B.40) for self-modification framework → AI-curated topics as a free-zone. This is a **prerequisite for B.16 (Cross-City Policy Comparison)** and any city beyond Richmond.

**Connects to:** B.40 (Autonomy Zones Phase B), B.16 (Cross-City Comparison), B.20 (Civic SDK — topic taxonomy as a portable abstraction).

### I58. S14 Phase A Components Already ~80% Built ➜ Observation (validated in S14)
S11/S12 pre-built most Phase A components (TopicBoard, HeroItem, AgendaItemCard, significance.ts). S14 was refinement, not greenfield.

### I56. Pipeline Scheduling Infrastructure — No Manual Runs ➜ ✅ Complete (S15)
4-tier scheduling (daily/weekly/monthly/quarterly) for all 18 sources via GitHub Actions cron. Staleness monitor is verification layer. Delivered in S15.

### I59. OpenCorporates Entity Resolution — Demand Analysis & Rate Limit Viability
**Origin:** 2026-03-22 (S13.2 OpenCorporates integration session) | **Priority:** Informational

**Demand analysis from NetFile data:** 91 unique entity-like donor names (LLC/Inc/Corp/etc.) out of 3,406 total donors (2.7%). Total entity contributions: $454K across 126 records. After normalization dedup, ~70-80 unique entities. Top: ChevronTexaco ($138K), Tesoro ($88K), ConocoPhillips ($30K).

**Rate limit viability:** At 50 calls/day (free tier), initial backfill takes ~2 days for search + ~2 days for detail lookups. Monthly budget (200) is sufficient for ongoing resolution of new contributions. This is viable — the demand is small enough for the free tier.

**Known duplicate pairs in NetFile data:** JIA Investments LLC / JIA Investments, LLC; Holistic Healing Collective Inc. / Holistic Healing Collective, Inc.; Richmond Development Company LLC / Richmond Development Company, LLC; Davillier Sloan Inc / Davillier-Sloan, Inc.; AWIN Management Inc. / LE03-AWIN Management Inc (prefix variant).

**Observations:**
- The `&` character should NOT be stripped during normalization — it's meaningful in entity names like "Reed & Davidson, LLP"
- Token-based similarity (Jaccard) handles entity name variants better than edit distance
- CA SOS API key may still arrive — the `resolve_entity()` abstraction works for either source
- ODbL share-alike only constrains the `business_entities` table data, not source code or full DB

### I60. Lightweight Topic Timeline Using Existing Categories
**Origin:** 2026-03-22 (S14-C influence map session) | **Priority:** High

"Evolution of this topic" timeline — show all agenda items in a category or local issue chronologically, with vote outcomes and financial connections overlaid. The full topic-navigation-spec (S14-P) calls for contributor classification first, but a v1 can ship using existing data:

- **Categories** (14 values from vote categorizer) already tag every agenda item
- **Local issues** (`detectLocalIssues()`) provide Richmond-specific topic lenses (Chevron, Point Molate, etc.)
- **`continued_from` / `continued_to`** fields exist on `agenda_items` (may not be populated — check)
- Vote outcomes, flag counts, and split vote data already available

**v1 scope:** `/topics/[category]` page showing chronological timeline of items in that category. Each item: date, meeting link, headline, vote result badge, flag count. No new queries needed beyond a filtered `agenda_items` query with meeting join. Controversy-sorted by default. Financial connections panel uses existing conflict_flags data.

**Why now:** The influence map item center (S14-C) already links to related decisions sorted by controversy. A topic timeline is the same data rotated — "all Housing items over time" instead of "Housing items involving the same officials." The components exist; this is mostly a page + query.

**Depends on:** Nothing (existing data sufficient). Full contributor classification (S14-P Phase 1) enriches it later but isn't blocking.

### I61. Reverse Delegation Audit — Scan for Under-Automation
**Origin:** 2026-03-22 (Supabase CLI adoption session)

The quarterly judgment boundary audit checks for over-prompting (escalating AI-delegable decisions). It doesn't check for under-automation: manual steps documented as "human actions" that could be handled by a CLI, API, or script.

**Proposed addition to Q2 audit:** Scan all items tagged as "human action" in conventions, CLAUDE.md, and memory files. For each, ask: "Does a CLI, API, or automation path exist?" Flag candidates for delegation.

**Concrete examples already found:**
- Supabase SQL Editor → `supabase db push` (fixed 2026-03-22)
- Potential: Vercel deployment verification → `vercel` CLI or API check
- Potential: GitHub Actions manual dispatch → `gh workflow run` from session

**Cost:** Zero — it's an addition to the existing audit checklist.

### I62. CONTRIBUTING.md and Issue Templates for Public Repo
**Origin:** 2026-03-22 (open-source prep session)

Now that the repo is going public, it needs contributor-facing docs: a CONTRIBUTING.md explaining the architecture, how to add a new city, and PR conventions. GitHub issue templates for "Add my city" (most valuable contribution type), bug reports, and feature requests. Low urgency — solo project — but sets expectations.

### I63. GitHub Repo Metadata for Discoverability
**Origin:** 2026-03-22 (open-source prep session)

After flipping to public: add GitHub topics (civic-tech, government-transparency, open-data, local-government, campaign-finance, python, nextjs), a description, and social preview image. These affect discoverability in GitHub search and civic tech directories.

### I64. Grant Research — Civic Tech Funding Sources
**Origin:** 2026-03-22 (open-source prep session)

Research grant programs that fund civic tech nonprofits: Knight Foundation, Mozilla Foundation, Google.org, Code for America, local community foundations (Richmond Community Foundation, East Bay Community Foundation). The nonprofit structure + AGPL license + free public access model aligns well with civic tech grant criteria. Compile eligibility requirements and application timelines.

### D16. agenda_items Schema Assumption Bug Pattern
**Origin:** 2026-03-22

Two independent bugs found in one session: `topic_tagger.py` and migration 049's `v_topic_stats` view both referenced `agenda_items.city_fips` and `agenda_items.meeting_date`, which don't exist. These columns live on `meetings` and require a JOIN.

**Pattern:** Code that queries agenda_items frequently assumes it has meeting-level fields. This is a schema misassumption that will recur.

**Possible fix:** Add a comment to the `agenda_items` table or a note in `src/CLAUDE.md` explicitly listing which fields are NOT on agenda_items (city_fips, meeting_date → join through meetings).

---

## Session Notes (2026-03-23, Public/Operator Split)

### I14. Publication Tier Enforcement as Product Architecture ➜ ✅ Done (Public/Operator Split)
Public nav auto-simplifies via `operatorOnly` flag + single-item group collapse. Government entity employer filter consolidated.

### D17. Retrospective Scanner Path Duplication
Two near-identical retrospective scan code paths (~120 lines duplicated). Recommendation: extract shared `_scan_retrospective_contributions()`. Low priority.

### I56. Topic Labels — Extracted Specific Subjects for Agenda Items ➜ ✅ Delivered (S16)
1-2 word topic labels per agenda item extracted at summary generation time. `topic_label VARCHAR(50)` on `agenda_items`. Category labels fixed on meeting cards.

### D27. Self-Contribution Scanner False Positives ➜ ✅ Fixed (S19)
Self-contribution filter added — suppresses flags where donor name fuzzy-matches the committee's official.

### D28. DECISIONS.md Restructuring (Deferred)
**Origin:** 2026-03-25 (mid-cycle audit refresh) | **Priority:** Low — trigger at ~150 entries or open-source launch

At 92 entries / 499 lines, DECISIONS.md is approaching the threshold where navigability degrades. Currently manageable with grep. Restructure when: (a) entries hit ~150, (b) second city onboarding begins, or (c) open-source launch requires external contributor navigation. Recommended approach: add TOC grouped by domain (Architecture, Scanner, Data Sources, Process, Values/Business), keep chronological order within groups, tag superseded entries rather than archiving.

---

## Session Notes (2026-03-24, Launch Arc Planning)

### I65. Pre-Launch Audit Findings ➜ ✅ All addressed in S17-S18
Public pages launch-ready. Gaps (OG meta, robots.txt, sitemap, 404, security headers) all fixed in S17-S18.

### I66. Topic Labels Supersede Dynamic Topics Architecture ➜ ✅ Delivered (S16)
Operator directive: simple `topic_label VARCHAR(50)` on `agenda_items` instead of R14's taxonomy. Delivered in S16.

### I67. Launch Arc as Pre-Share Sprint Sequence ➜ ✅ Complete (S16-S18)
S16-S18 delivered as public-only polish arc. S18 ended with richmondcommons.org live and version 1.0.0.

### I68. AI-Generated Comment Summaries Per Agenda Item
**Origin:** 2026-03-25 (operator direction — "probably immediately after go-live")

The `public_comments` table stores speaker names, delivery method (in_person/zoom/phone/email/ecomment), and comment type (public/written). The item detail page now displays these individually, but a natural next step is AI-generated comment summaries — a short narrative synthesis of what the public said about each item.

**Approach:** Claude Sonnet extraction pass over the existing comment data (speaker_name + summary fields). Output: 2-3 sentence narrative per item summarizing the sentiment and key concerns raised. Similar to the existing plain_language_summary generation pipeline but operating on public comment data rather than agenda text.

**Cost estimate:** ~$0.02/item (most items have 0-5 comments), only items with comments need processing. Batch API eligible.

**Dependencies:** Item detail page (now built), comment data quality (speaker names + summaries must be consistently extracted).

**Publication tier:** Graduated — AI-generated content needs review before public exposure.

### I71. Semantic Item Similarity & Controversy Discovery
**Origin:** 2026-03-25 (operator brainstorm)

**The problem:** Topic labels and categories connect items by surface content, but miss deeper relationships. A "condemn antisemitism" resolution and a "condemn Islamophobia" resolution have different topic labels but share political dynamics a resident would want to see together. Similarly, there's no way to ask "what's the most fought-over police item in the last 3 years?"

**Approach — three layers, all factual (no hidden editorial tags):**

1. **Embedding similarity (pgvector).** Items with similar description text naturally cluster without explicit labels. "Related items" section adds a "Similar discussions" group powered by vector search. Explainable: "items with similar agenda text." Infrastructure already exists (pgvector in PostgreSQL, Layer 3 of the three-layer DB).

2. **Procedural type classification.** Objective categories: censure motion, proclamation, resolution of support, contract approval, zoning variance, budget amendment. These connect items by what *kind* of action they are, not what they're about. Factual, not editorial.

3. **Controversy-weighted ranking.** The `get_controversial_items()` RPC (migration 038) already computes scores from split votes, comment count, and multiple motions. Use controversy as a **relevance multiplier** in similarity results — when showing related police items, boost the contentious ones over routine consent calendar items.

**Discovery UX options (not mutually exclusive):**
- **Item page "Similar discussions"** — embedding-based related items weighted by controversy. Low-effort extension of the tiered related items just built.
- **Category drill-through pages** — `/meetings/topic/[slug]` showing all items in a topic, sortable by controversy or date. Extends the calendar grid's category drill-through (S14 B5).
- **"Most Debated" standalone page** — top controversial items across all topics, filterable by category/topic. The cross-meeting "Most Discussed" sort, but as its own page.

**Why not hidden editorial tags:** The project's mission is making opaque systems legible. Hidden tags that shape what residents see without being visible themselves create exactly the kind of opaque editorial layer the project is trying to dismantle. Embedding similarity + procedural types + controversy scores achieve the same "vibe matching" with all-factual, all-explainable signals.

**Dependencies:** Topic label quality improvement (some labels are too generic, e.g., "Police & Community Safety" instead of "Flock Safety"). Embedding generation for agenda items (pgvector infrastructure exists but item embeddings may not be populated yet).

**Publication tier:** Public — all signals are factual and explainable.

### I72. Data Blog — Feature Previews & Content Marketing
**Origin:** 2026-03-25 (operator idea)

**Concept:** A blog that surfaces interesting data connections and patterns from the platform, serving dual purposes: content marketing to drive user discovery, and feature validation to test whether residents engage with specific data presentations before building full UI.

**Trigger:** Immediately post-launch — the blog *creates* the user base, not the other way around. Nobody stumbles onto a civic data platform and starts exploring. But "here's what Richmond council actually fought about this month" shared on Nextdoor is a click. The blog is the entry point that shows people how interesting the data is and gets them to explore and find their own stories. Content is generated from existing pipeline data, so production cost is near-zero once the queries exist.

**Example content (drawing from I71 + existing data):**
- "What Richmond debated most in 2025" — controversy-ranked items by category, with links to item pages
- "The Flock Safety saga: every vote, every comment" — topic thread across multiple meetings
- "Where the money flows: campaign contributions and council votes" — narrative version of influence map data
- "Council alliances: who votes together, and when they don't" — pairwise agreement rates filtered by issue area (coalition dashboard data + category filter). The interesting story is where alliances break: "Martinez and Robinson agree 92% overall, but only 60% on police items."

**Blog idea book** (add to this list as ideas come up):
- Which council member speaks the most? Least? On what topics?
- "The consent calendar: what passes without discussion" — percentage of city business that gets zero debate
- Year-over-year trends: is council getting more or less divided?
- "Follow the public comment" — do items with heavy public input get different outcomes?
- "New member effect" — how voting patterns shifted when the current council took office
- The money map: which donors give to multiple council members?
- "What happens after a split vote?" — do contentious items come back? How often does the outcome flip?
- Alliance timelines: how does voting alignment between two members shift over time? Overlay with key events (candidacy announcements, election cycles, major votes). Example: Martinez-Jimenez divergence timed against the mayoral race. **Note: this is editorial narrative, not platform content — exactly the blog/platform separation I72 is built for.**

**Tone — judgment call for the operator:**
Framing matters. "Top 10 most controversial votes" reads as adversarial watchdog. "What Richmond debated most in 2025" reads as civic engagement. Same data, different relationship with the city. The blog is where the operator's editorial voice lives — the platform stays factual, the blog adds context and narrative. This separation keeps the product neutral while giving the project a human voice.

**Editorial philosophy:** "Objective" and "neutral" aren't the same thing. Every number is verifiable from public records — that's objective. Which data to highlight, and why — that's curation, which is inherently not neutral, and that's fine. Transparency about the selection is what matters. Suggested methodology disclosure: "Every number here is verifiable from public records. What we chose to look at, and why, is ours."

**Implementation options (simplest first):**
1. **External newsletter** (Substack/Buttondown) linking back to Richmond Commons item pages. Zero frontend work. Tests content appetite before building anything.
2. **Simple `/blog/[slug]` pages** in Next.js. Markdown files in the repo, statically generated. Minimal build cost.
3. **Full CMS integration** — only if volume justifies it. Premature now.

**Dependencies:** Meaningful user base, I71 similarity engine (for the most interesting content), operator comfort with editorial voice.

**Publication tier:** Public — the blog IS the public-facing editorial layer.

---

## Session Notes (2026-03-25, Mid-Cycle Audit Refresh)

### Audit Refresh Completed
Mid-cycle judgment boundary refresh produced `docs/audits/2026-Q1-midcycle-refresh.md`. Key findings: JC-1 and JC-3 from Q1 audit resolved. JC-2 (confidence_tier_desync) remains open but is now tracked automatically in the decision queue. Two new catalog categories added: boundary promotion/demotion as judgment call, decision queue data quality triage as AI-delegable. Values (justice/representation/stewardship) mapped to each judgment call. AO1-AO7 validated, AO8 (open-source readiness) proposed. D28 logged for DECISIONS.md restructuring (deferred to ~150 entries or open-source launch).

---

## Advisory Opinions (AO#)

_Non-binding reasoned positions the AI forms grounded in the project's values (justice, representation, stewardship), surfaced for operator calibration. Not decisions the AI makes silently (AI-delegable) or options it presents without a recommendation (human judgment calls) — these are the middle zone where the AI develops and articulates a position._

_The purpose: expand the boundary of what the AI can eventually handle autonomously. If the AI's advisory opinions consistently align with the operator's overrides, that's evidence to promote them to AI-delegable in the next quarterly audit. If they consistently diverge, that reveals a values gap worth understanding._

### AO1. Publication Tier Proposals for New Features
**Current boundary:** Judgment call (human decides).
**AI judgment opportunity:** The AI already proposes tiers with reasoning. Formalize this: for each new feature, the AI articulates which of the three values the feature serves, what the publication risk is (credibility damage, city relationship, data accuracy), and recommends a tier with a confidence level. Track operator agreement rate over time. If >90% agreement after 20 proposals, consider promoting to AI-delegable with human veto.

### AO2. Source Tier Assignment for New Data Sources
**Current boundary:** Implicit (follows the tier definitions in richmond.md).
**AI judgment opportunity:** New data sources don't always map cleanly to tiers. Is a city department's social media feed Tier 1 (official) or Tier 3 (stakeholder comms)? The AI should reason about this by analogy to existing assignments, cite the tier definitions, and propose a tier with the reasoning visible. This is values-adjacent: stewardship requires getting credibility right.

### AO3. Framing Sensitivity Detection
**Current boundary:** Judgment call ("content touching the city/community relationship").
**AI judgment opportunity:** The AI can learn to detect when a finding *could* be framed in a way that damages the collaborative relationship. Example: "Council member X voted against housing protections 8 times" is factually accurate but reads as advocacy. The AI could flag the framing risk and propose a neutral alternative ("Council member X voted no on 8 of 12 housing items") alongside the original. Track which framings the operator prefers. The pattern teaches the AI the project's editorial stance without codifying it as a rule.

### AO4. Confidence Threshold Recommendations
**Current boundary:** Judgment call (specific numeric values affecting public visibility).
**AI judgment opportunity:** When the scanner's false positive or false negative rate changes significantly after a data update, the AI could recommend threshold adjustments with statistical evidence. "After the batch rescan, the current 0.75 tier-1 threshold excludes 14 flags that have 3+ corroborating signals. Lowering to 0.70 would include them while adding only 2 false positives based on manual review of similar flags. Recommendation: lower to 0.70. Values alignment: stewardship (accurate representation of financial connections)."

### AO5. Feature Prioritization Reasoning
**Current boundary:** Human decides sprint order.
**AI judgment opportunity:** When multiple backlog items compete for the next sprint, the AI could rank them against the three values with explicit reasoning. "B.50 (Contract Entity Tracking) scores highest on justice (closes a gap in financial accountability) and stewardship (contract data is Tier 1). B.23 (Civic Role History) scores highest on representation (makes appointment patterns visible). Both are triple-path. Recommendation: B.50, because the contract-to-donor cross-reference has no manual workaround, while role history enriches existing profiles." The operator overrides or accepts. Over time, this teaches the AI the operator's implicit prioritization weights.

### AO6. Scanner Signal Credibility Assessment
**Current boundary:** Automated (composite confidence score).
**AI judgment opportunity:** Beyond the mechanical score, some signals *mean* more than their confidence suggests. A 0.65-confidence flag where the donor is a major Chevron-affiliated PAC contributing to a council member who voted on a refinery permit carries more civic weight than a 0.80-confidence flag about a $200 individual donation. The AI could annotate flags with a "civic salience" assessment separate from statistical confidence. This is the hardest variable — it requires the AI to reason about *why* a finding matters, not just whether it's statistically valid.

### AO7. When to Push vs. Collaborate
**Current boundary:** Human judgment (relationship management).
**AI judgment opportunity:** The AI can't manage the relationship, but it can identify when findings cross a threshold where not surfacing them would compromise the justice value. "This pattern of contract awards to the same vendor across 3 years without competitive bidding is strong enough that burying it behind an operator gate indefinitely compromises the platform's credibility. Recommend graduated publication with factual framing." The operator still decides, but the AI is explicitly reasoning about the tension between collaboration and accountability.

### AO8. Open-Source Readiness Assessment (Proposed — activate at open-source launch)
**Current boundary:** Not yet active. Proposed in mid-cycle audit refresh (2026-03-25).
**AI judgment opportunity:** As the project moves toward open-source, the AI should proactively flag: code comments or commit messages that reference internal processes inappropriately, documentation that assumes operator context a contributor wouldn't have, and architecture decisions that would be confusing to external contributors without context. Value: stewardship (sustainable open-source governance). Risk if wrong: over-flagging slows development; under-flagging exposes internal assumptions publicly.

### I69. Public Comment Type Separation — In-Person vs. Written
**Origin:** 2026-03-25 (operator request) | **Priority estimate:** Medium (post-launch, S19+)

The `public_comment_count` field on agenda items is a single integer. Richmond council meetings distinguish between oral public comments (speakers at the podium) and written communications submitted to the clerk. These are different civic participation channels with different accessibility implications.

**Scope:**
- Schema: Add `oral_comment_count` and `written_comment_count` columns (or a `comment_type` enum on a comments table)
- Extraction: Update agenda/minutes extraction prompts to parse "Oral Communications" vs "Written Communications" sections separately
- Frontend: Display both counts on agenda items (e.g., "3 speakers, 5 written")
- Summarizing comment content is a separate, larger effort (post-go-live)

**Why it matters:** Written comments are often submitted by organizations or repeat participants. Oral comments represent people who showed up in person. Distinguishing them tells a richer story about civic engagement on each item.

### I70. Public Election Tracker Page — Candidate Comparison Hub
**Origin:** 2026-03-25 (operator stub idea) | **Priority estimate:** Medium (post-launch, near-future)

The amber "Running for Mayor" / "Running for re-election" badges on council cards currently link to the individual profile. They should link to a public election tracker page that shows all candidates in the upcoming election side-by-side.

**Stub concept:** A `/elections/2026` or `/elections` page showing:
- All declared candidates grouped by race (Mayor, D2, D3, D4)
- Fundraising comparison (already have `getElectionFundraisingSummary`)
- Incumbent vs. challenger framing
- Filing status, committee links

**Design considerations to explore when the time comes:**
- Should this be one page per election or a rolling "upcoming elections" page?
- How to handle primary vs. general (Richmond's first mayoral primary is June 2026)
- Candidate pages for non-incumbents (who don't have council profiles)
- How much fundraising comparison is useful vs. potentially misleading (D6 concern)
- Integration with existing `/influence/elections` operator page — graduate parts of it?

**Why it matters:** Election season is when civic engagement peaks. A clear, neutral comparison page is the most valuable thing the platform could offer during campaign season. The data infrastructure (elections + election_candidates + contributions) already exists.

### I21. Staff Report Enrichment Gap
**Origin:** S18 (2026-03-25)

Only one meeting (March 24, 2026) has eSCRIBE staff report attachment text enriched into agenda item descriptions. All other meetings have shorter eSCRIBE-only recommended action text (300-500 chars avg vs 4,879 avg for enriched). The enrichment pipeline appends text after a `[eSCRIBE Staff Report/Attachment Text]` marker.

**Observation:** The enriched descriptions produce dramatically better context for citizens. The "Statement of the Issue" and "Discussion" sections contain the reasoning behind staff recommendations — exactly the context that makes government decisions legible.

**Recommendation:** Backfill enrichment for all meetings with available staff reports. Estimate cost and track as a batch operation. This directly serves the mission — the recommended action alone doesn't explain *why*.

### D19. PDF Text Formatting Refinements
**Origin:** S18 (2026-03-25)

The `format-agenda-text.ts` parser handles the major patterns (section headers, line rejoining, preamble stripping, bullet lists) but has room for improvement:
- "Programmatic Impact" and "Operational Considerations" sub-headers within Discussion sections aren't detected (they're not uppercase section headers)
- Some bullet patterns from PDFs use non-standard Unicode characters that may not be caught
- "DOCUMENTS ATTACHED:" appears at the end of most reports — could be stripped or styled differently
- "Previous Council Action" dates could be rendered as a timeline rather than a flat list

### I22. Unified Minutes Extraction Gate (Two-Source Problem)
**Origin:** S19 (2026-03-25) | **Priority:** High — recurring operator escalation (3-4 times flagged)

**Problem:** Minutes come from two independent sources (eSCRIBE and Archive Center) that don't coordinate. eSCRIBE minutes get extracted automatically; Archive Center minutes get discovered and linked (`minutes_url` populated) but often never extracted. This leaves gaps — meetings show "no votes" even when minutes exist. The operator has flagged this repeatedly.

**Current state (2026-03-25):**
- ~15 Archive Center minutes from 2025-2026 have `minutes_url` set but zero motions extracted
- eSCRIBE minutes extract reliably through the `escribemeetings_minutes` sync
- Archive Center minutes only extract through `minutes_extraction` which requires a separate manual trigger
- The two pipelines don't know about each other

**Proposed fix: `sync_unextracted_minutes`** — a new sync source that:
1. Queries: `SELECT meetings WHERE minutes_url IS NOT NULL AND zero motions exist`
2. Downloads and extracts each, regardless of which scraper found the URL
3. Runs in the weekly schedule after both `archive_center` and `escribemeetings_minutes`
4. Self-healing chain: scraper finds minutes → unextracted_minutes extracts votes → meeting_summaries generates narrative

**Key insight:** We don't need to unify the scrapers or deduplicate URLs. We need one downstream gate that asks "does this meeting have minutes but no votes?" and acts on it. Same pattern as meeting_summaries checking "votes but no summary."

**Implementation notes:**
- The extraction logic already exists in `minutes_extraction` — this is mostly query + orchestration
- Need to handle both Archive Center PDFs (direct download) and eSCRIBE PDFs (filestream.ashx)
- Cost: ~$0.06/meeting for Claude extraction, ~15 backlog meetings = ~$1
- This should be AI-delegable once built — no judgment calls, pure pipeline automation

### D20. Duplicate Motions in Vote Data
**Origin:** S19 (2026-03-25)

Some agenda items have duplicate motions — identical votes, same result, different motion IDs (e.g., May 20, 2025 Item R.1 had two copies of the same failed motion). Doesn't affect summaries (we pick the final motion by sequence_number) but inflates motion counts. Likely an extraction artifact from PDF parsing.

**Recommendation:** Add dedup in the extraction pipeline: unique constraint on (agenda_item_id, motion_text, result) or post-extraction dedup pass.

### D21. Meeting Summary Generator — Case Sensitivity and Motion Selection Bugs ➜ ✅ Fixed
Three bugs in `generate_meeting_summaries.py`: case mismatch (822 invisible failed motions), cross-motion nay counting, arbitrary motion selection. All fixed.

### I73. Public Comment Sentiment Classification & Vote Alignment
**Origin:** D28 session (2026-03-26) | **Priority:** High — direct Representation value signal | **Promoted to B.61**

Operator insight: public comments are extracted but not classified by stance. Three-tier sentiment (`support`, `oppose`, `neutral`) on each public comment would enable the most direct "representation" metric in the system: how often does the council's vote align with the community's expressed position?

**Three layers:**
1. **Sentiment classification** — LLM classifies each comment (written + verbal). Migration adds `sentiment` column. Batch API backfill (~11K comments, ~$5-10). New comments classified during extraction.
2. **Item-level aggregate** — "12 comments: 8 oppose, 3 support, 1 neutral" displayed alongside vote outcome on meeting detail page.
3. **Vote alignment analysis** — per council member alignment score: % of votes where member's vote matched majority public comment sentiment. Surface items where council voted opposite to overwhelming comment direction.

**Framing is critical:** "Responsiveness to public input" not "defiance of the public." Council members may have excellent reasons to vote against public comment majority (legal advice, budget constraints, broader constituency). The metric surfaces the pattern; the user interprets.

**Connects to:** I68 (AI-generated comment summaries), I69 (in-person vs written comment separation), B.58 (template analysis), B.60 (spend trend + comment cross-reference).

### I74. D28 Category Recategorization — Keyword Categorizer Bugs ➜ ✅ Fixed
Fixed 5 structural ordering bugs in `categorize_item()`. Specific categories now checked before broad ones.

### I75. Public Comment → Agenda Item Linking Gap
**Origin:** 2026-03-26 (operator report: Flock camera item shows 0 comments) | **Priority:** High — affects data credibility

**Problem:** Most public comments have `agenda_item_id = NULL` — they're stored at meeting level but not linked to the specific agenda item they address. March 3 2026 meeting: 13 comments, only 2 linked to any item, 0 linked to the Flock Safety item despite heavy public discussion.

**Root causes:**
1. **Extraction prompt** asks Claude for `related_items` array, but open forum comments often don't reference specific item numbers, and item-specific verbal comments (spoken during agenda discussion) may not be extracted separately from the item itself.
2. **db.py loader** only uses `related_items[0]` — subsequent items are discarded.
3. **`public_comment_count` on `agenda_items`** is NULL for 12,133 of 12,508 items — this field is barely populated. The frontend computes counts from `public_comments` JOIN, but only counts rows where `agenda_item_id IS NOT NULL`.

**Scale:** 11,341 total comments in DB. Unknown what % should be linked but aren't.

**Potential fixes (layered):**
1. **Quick: re-link pass.** Query unlinked comments whose `summary` text mentions identifiable item content. LLM batch: "given this comment summary, which agenda item from this meeting does it relate to?"
2. **Extraction improvement.** Update minutes extraction prompt to distinguish open forum comments from item-specific comments, and to always populate `related_items` for item-specific ones.
3. **Backfill `public_comment_count`.** SQL UPDATE from aggregated `public_comments` table — or deprecate the column entirely in favor of runtime JOINs.

**Connects to:** I68 (comment summaries), I69 (comment type separation), I73/B.61 (comment sentiment + vote alignment).

**S20 Solution (validated 2026-03-26):** YouTube transcript pipeline via KCRT TV channel (`UCJ0TqQHWE4uaC7xI1TkRdRA`). Single Claude API call per meeting transcript (~125K tokens) returns speaker count per item. March 3 prototype: correctly identified 55 speakers on Flock W.1 (minutes had 0), 11 open forum, 2 on V.1, 1 on V.2. Cost: $0.38/meeting, ~$6 for 16 recent meetings. No speaker names needed — just counts per item. See PARKING-LOT.md S20 for full sprint spec.

**Queries.ts disabled (restore in S20.3):**
Per-item comment counts zeroed in `queries.ts` at 3 locations (marked with "Restore with:" comments):
1. `getMeeting()` line ~280: `public_comment_count: 0` → restore `count`, `comment_summary`
2. `getAgendaItemDetail()` line ~3007: `public_comment_count: 0` → restore `comments.length`, `comment_summary`, `comments`, `written_comment_count`, `spoken_comment_count`
3. `getControversialItems()` line ~1575: `public_comment_count: 0` → restore `Number(row.public_comment_count)`

**Frontend removed (restore when data is reliable):**
Per-item comment display was removed from `AgendaItemCard.tsx` in commit `faec954` (2026-03-26). Two elements to restore:

1. **Comment count badge** (was in header badges row, after headline):
```tsx
{item.public_comment_count > 0 && (
  <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-bold bg-civic-navy/10 text-civic-navy border border-civic-navy/20">
    {item.public_comment_count} {item.public_comment_count === 1 ? 'comment' : 'comments'}
  </span>
)}
```

2. **Comment summary section** (was in expanded content, after plain language summary):
```tsx
{item.comment_summary && item.comment_summary.total > 0 && (
  <div className="text-xs text-slate-500 mb-3 pl-1">
    <span className="font-medium">{item.comment_summary.total} public {item.comment_summary.total === 1 ? 'comment' : 'comments'}</span>
    {' — '}
    {item.comment_summary.notable_speakers.length > 0 ? (
      <>
        Residents spoke on this item.{' '}
        {item.comment_summary.notable_speakers.map((s, i) => (
          <span key={s.name}>
            {i > 0 && ', '}
            <span className="font-medium">{s.name}</span>
            {' '}({s.role})
          </span>
        ))}
        {' also commented.'}
      </>
    ) : (
      'Residents spoke on this item.'
    )}
  </div>
)}
```

Also restore `!!item.comment_summary` to the expanded section's condition check (was `hasDescription || hasMotions || hasSummary || !!item.comment_summary`, now just `hasDescription || hasMotions || hasSummary`).

**Data source update (2026-03-26):** Granicus transcripts are now the primary source (81 meetings with transcripts, ~64K tokens each, $0.19/meeting). YouTube/KCRT is fallback. Granicus VTT-in-PDF format parsed via PyMuPDF. See `src/granicus_transcripts.py`.

### ~~I78~~ ✅ `/council/stats` made dynamic to avoid build timeouts (2026-03-26)

### I77. Meeting Outcome Filter (Passed/Failed/Continued)

**Operator request (2026-03-26).** Replace the By Topic / Agenda Order toggle on meeting detail pages with a four-way filter: **All | Passed | Failed | Continued**. All views sorted by controversy by default. Repurposes existing slider UI — no new components needed. Requires vote outcome data on each `AgendaItemWithMotions` (derivable from existing motion result field). Also swap stat boxes to outcome-focused: Items Passed, Items Failed, Public Comments, Consent Calendar (drop Substantive Items and Votes Recorded). The stat box swap is independent and can ship first.

### I76. Granicus Video Timestamp Deep Links

**Operator request (2026-03-26).** Since Granicus transcripts have timestamps for every cue, we can link from the item detail page directly to the video timestamp where that item was discussed. Pattern: `richmond.granicus.com/player/clip/{clip_id}?view_id=30&redirect=true&h=H&m=M&s=S`. The LLM extraction already sees the timestamps — we just need to return the start timestamp for each item's public comment period (or discussion start) alongside the speaker count. Frontend: "Watch discussion" link on item detail page, opens Granicus video at the right moment. Also: "Read transcript excerpt" could show the relevant transcript section inline. Requires: (1) Store clip_id on meetings table or as a mapping. (2) LLM returns timestamp per item. (3) Frontend link component.

### I79. Granicus Transcript Coverage Expansion

**Session observation (2026-03-26).** Only 82 of 928 Granicus meetings have transcript links. The remaining 846 have video but no transcript PDF. Granicus does have a `/videos/{clip_id}/captions.vtt` endpoint but it's empty (40 bytes placeholder) for all checked meetings. Options: (1) Contact Granicus/city to enable captioning for historical videos. (2) Use Whisper or similar ASR on the video files directly (~$0.006/minute via API, ~$2-3/meeting). (3) Accept 82-meeting coverage as sufficient for launch. Option 3 is fine for now — 82 meetings covers Sept 2023 to present, which is the current council's entire tenure.

### D29. LLM Item Number Hallucination in Transcripts

**Session observation (2026-03-26).** ~30% of YouTube-sourced extractions returned wrong item numbers (e.g. "Q1" when DB has "P.1", "K.9" when DB has "N.3.d"). Granicus transcripts are cleaner but the problem persists for some meetings. Root cause: auto-captions mishear letter names (P/T/D/B sound similar). Mitigation options: (1) Include item titles in the prompt alongside numbers so the LLM can match by content, not just number. (2) Post-processing fuzzy match against actual agenda (already implemented with `normalize_item_num` but can't fix completely wrong letters). (3) Ask LLM to return the item title alongside the number for human verification. Current approach (skip unmatched items) is safe but loses data.

### D30. Former Council Members Data Quality Cleanup

**Session observation (2026-03-27).** The "former members" section on the council page shows ~45 entries with significant data quality issues: last-name-only duplicates ("Bates", "Beckles", "Boozé", "Griffin"), accent/apostrophe variants ("Boozé" vs "Booze'" vs "Corky Boozé"), and title-prefixed duplicates ("Choi" vs "Ben Choi"). Root cause: `ensure_official()` fuzzy matching at 0.85 threshold can't match last-name-only strings to full names (e.g., "beckles" vs "jovanka beckles" = 0.594). Fix requires: (1) migration to merge duplicate officials (rewire votes, attendance, committees, conflict_flags, etc. via `merge_official_pair` pattern from migration 020), (2) add missing aliases to `officials.json`, (3) consider improving `ensure_official()` to check if input is a substring of existing normalized names. Former members section hidden from public until cleanup is complete. When restored, re-add "View all →" link to homepage council section (homepage shows current only, /council shows current + former).

### D31. Granicus Transcript PDF Text Extraction Failures (was D30)

**Session observation (2026-03-26).** 2 of 81 Granicus PDFs returned 0 text from PyMuPDF (2025-10-07, 2025-03-04). These are likely image-based or scanned PDFs where text is not extractable. OCR (Tesseract or similar) would recover them. Low priority — 79/81 success rate is acceptable.

### I80. Topic Landing Pages — Per-Topic Summary, Timeline, and Related Issues

**Session observation (2026-03-27).** Post-launch roadmap item combining several related ideas:

- **Per-topic landing page** (`/topics/[slug]`) with: 1–2 sentence plain-language overview of that topic in relation to Richmond (e.g. "Police & Community Safety" → what's the history, what's currently contested), a timeline of related votes and agenda items, and a list of related issues/patterns.
- **Topic tooltips** on category pills throughout the site — same hover pattern as `CivicTerm` — showing the 1–2 sentence overview inline without navigating away.
- **Topic index page** (`/topics`) listing all active topics with item counts and a brief description, functioning as a civic guide to the issues the council is working on.

**Combines:** I59 (AI-Delegated Topic Curation), I60 (Lightweight Topic Timeline), the local issue taxonomy from S11, and topic labels from S16. The topic labels table (`agenda_item_topics`) already provides the association layer — what's missing is the topic metadata table (description, slug, parent category) and the frontend pages.

**Estimated scope:** Medium. DB migration for topic metadata (10–15 rows, hand-curated initially), 2–3 frontend pages, tooltip integration across `CategoryBadge`/`TopicLabel`. AI-delegable except the topic descriptions (judgment call — framing matters for the city relationship).

**Dependency:** Deferred until after go-live (S18). Topic labels regeneration (S16.4, ~$40) should complete first so topic coverage is solid before building discovery on top of it.

### ~~I81~~ ✅ Homepage "How It Works" removed — replaced with live content (latest meeting + council grid).

### I83. "How to Use This Site" Guide Page

**Session observation (2026-03-27).** UX review: before open beta / broader public promotion, the site needs a guided orientation page. Not a FAQ — a walkthrough that shows new visitors what they can do and how to navigate the key features (meetings, council profiles, search, voting records). Could live at `/guide` or `/how-to`. Separate from the About page (which covers mission/methodology). Required before any public outreach push, not required for soft launch.

### I82. Inline Search Overlay (Command Palette Pattern)

**Session observation (2026-03-27).** UX review: navigating to a separate `/search` page for results is disruptive. Better pattern: inline search overlay (command palette style) with quick results that you can click. The full `/search` page remains for advanced filtering/browsing but isn't the default path. Post-launch.

### I84. Subscription Email Notifications

**Session observation (2026-03-27).** User-requested. Email notifications for key civic events: new meetings posted, official minutes published, new campaign finance filings, etc. Requires email collection, subscription preferences, and a notification pipeline triggered by data sync events. Could integrate with the scheduled pipeline (S15) — when a sync detects new data, queue notifications for subscribers who opted into that category. Post-launch, likely requires a dedicated sprint. Consider: Resend or similar transactional email service, unsubscribe compliance (CAN-SPAM), digest vs. real-time options.

### I85. Homepage "Most Discussed" Section (Post-S20)

**Session observation (2026-03-27).** After S20 (Public Comment Pipeline) lands and comment counts are reliable, add a "Most discussed" or "Community engagement" section to the homepage showing recent agenda items with high public comment counts. Answers "what are Richmond residents talking about?" — strong civic engagement signal. Blocked by S20 (comment counts currently disabled due to inaccuracy).

### I86. Homepage Redesign — Dashboard Over Brochure ✅ Done
Removed hero pitch + "How It Works". Homepage now surfaces live content (latest meeting card + council grid).

### I87. Council Member Photos from City Website

**Session observation (2026-03-27).** User-requested. Replace initials avatars with real council member photos on both the listing page (OfficialCard) and profile pages. Source: City of Richmond official website likely has headshots. Implementation: add `photo_url` column to officials table, scrape/download photos, store in Supabase storage or reference city URLs directly. Consider: image optimization (Next.js Image component), fallback to initials when no photo available, photo attribution/licensing from city website.

### I88. Council Profile Page — Remove FactualProfile Stats Box ✅ Done
Removed redundant stats box — narrative summary already contextualizes the same data. FactualProfile component unused.

### ~~I89~~ ✅ Voting Record — Group Motions Under Parent Agenda Item
Pre-grouping `useMemo` in `VotingRecordTable.tsx`. Multiple motions collapsed into one row with badge.

### I90. Voting Record — Show Topic Labels on Mobile
**Origin:** Profile page design review (2026-03-27) | **Priority:** Low

Topic labels are hidden on mobile (`hidden md:table-cell`). They're one of the strongest scanning signals. Consider showing them inline below the item title on small screens rather than hiding the column entirely.

### I91. Council Profile Footer — Pair Correction Link with Provenance Note
**Origin:** Profile page design review (2026-03-27) | **Priority:** Low

The "Suggest a correction" link at page bottom feels isolated. Pairing it with a data provenance note ("Data from City of Richmond certified minutes and campaign finance filings") reinforces trust and fills the sparse footer.

### I92. Voting Record — Topic Filter Redesign
**Origin:** UX polish session (2026-03-27) | **Priority:** Medium

The topic dropdown in the voting record table has too many options (every unique topic label across all votes). Unusable as a dropdown — needs a different UI pattern. Options: searchable combobox, top-N topics with "Other" bucket, or category-level grouping (collapse specific labels into parent categories). Removed from UI until redesigned.

### D29. Consent Calendar Comment Count Attribution
**Origin:** Homepage bug — "Approve minutes" showing 40 comments (2026-03-27) | **Priority:** Medium

The transcript pipeline assigns the entire consent calendar block's speaker count to individual consent items (specifically the first one, typically "City Clerk"). This inflates `public_comment_count` on items that weren't individually discussed. Root cause is in the YouTube/Granicus transcript extraction — speaker counts during consent discussion need to be attributed to the consent block as a whole, not to individual items. Quick fix applied: excluded consent items from homepage "Most Discussed" query.

### I93. Meeting Detail — Quick Text Filter for Agenda Items
**Origin:** Operator request (2026-03-27) | **Priority:** Medium

Add a search/filter text input on the meeting detail page to filter agenda items by keyword as you type. Would complement the topic label filter pills for users looking for specific items in long agendas.

---

## Wonk Board (Operator-Only Analytics Zone)

*The operator's "wonk board" — deep analytics on public comment data. Operator-only; select features may graduate to public over time. Needs improved auth before building (current OperatorGate is cookie-based, not password-protected).*

### I94. Comment Analytics Dashboard
**Origin:** Operator request (2026-04-02) | **Priority:** Medium | **Publication tier:** Permanent operator-only

Full-featured public comment analytics page. Key capabilities:
- **Search by commenter** — find all appearances of a speaker across meetings
- **Read full comments by commenter** — speaker profile page showing every comment they've made, linked to agenda items
- **Read full comments by issue** — browse all comments grouped by agenda item or topic label
- **Comment intensity metrics** — analyze tone/register of public comments. Suggested dimensions:
  - *Emotional intensity* — calm/measured vs. passionate/urgent (not good/bad, just register)
  - *Specificity* — policy-specific arguments vs. general support/opposition
  - *Constructiveness* — proposes alternatives vs. solely objects
  - *Profanity/hostility flags* — for operator awareness, never public
  - *Formality register* — formal testimony vs. conversational
- **Cross-reference with issue tags** — correlate comment intensity/volume with topic labels and categories
- **Temporal patterns** — comment volume and intensity over time. Election-proximity analysis: do comments become more emotional or polarized as elections approach?
- **Template/astroturf detection** — surface coordinated commenting campaigns (extends existing `detectTemplateCount`)

**Design note:** Metrics should characterize *how* people are talking, not *what side* they're on. "Emotional intensity" is a register observation, not a judgment. The operator explicitly rejected sentiment classification (support/oppose) — these analytics should follow the same principle.

### I95. Operator Auth Hardening
**Origin:** Wonk board planning (2026-04-02) | **Priority:** High (blocks I94)

Current OperatorGate is cookie-based — anyone who knows the cookie name can access operator features. Before building the wonk board (which will show individual speaker names and comment details), needs password protection or Supabase Auth. Options:
- Supabase Auth with a single operator account (simplest)
- HTTP Basic Auth via middleware (no DB dependency)
- Magic link via operator email

### I96. Form Letter / Astroturf Detection Analytics
**Origin:** Operator request (2026-04-03) | **Priority:** Medium | **Publication tier:** Permanent operator-only

Deep analysis of coordinated commenting campaigns. Extends the existing `detectTemplateCount()` (which catches identical written comments) into a full analytics layer:
- **Form letter clustering** — group near-identical comments (fuzzy matching, not just exact), surface the template text and count
- **Interest group / PR effort identification** — detect patterns: same employer, same neighborhood, similar phrasing across different meetings, coordinated submission timing
- **Issue-level form letter rates** — which agenda items attract the highest percentage of canned vs. organic comments? What topics trigger organized campaigns?
- **Campaign fingerprinting** — track recurring template patterns across meetings to identify persistent lobbying efforts (e.g., same org mobilizing on multiple items over months)
- **Written vs. spoken comparison** — written comments are more likely to be form letters; compare organic rates between channels

**Design note:** This is about transparency into *organized influence on public comment*, not about discrediting any individual comment. A form letter is still a legitimate expression of support — but knowing that 40 of 50 comments used identical language from an industry group is material context for understanding the public record.

### I97. Written Comment Extraction Pipeline (S21 Phase E) ➜ ✅ Built
**Origin:** Operator decision blocking S21 graduation (2026-04-03) | **Priority:** High (blocks "Themes From Comments" graduation)

**Implemented 2026-04-03.** Two-source approach:
1. **Archive Center emails** — `written_comment_extractor.py` parses email comments from AMID=31 PDFs. Handles both standalone compilations and minutes-with-appendix (ADJOURNMENT-split). Regex-based, $0 API cost. Full email body stored for maximum theme clustering signal.
2. **eSCRIBE eComments** — scraper enhanced with `fetch_ecomments()` AJAX call during `scrape_meeting()`. Saves eComments to `meeting_data.json` per-item. Orchestrator processes both sources.
3. **Shared item resolution** — `normalize_item_number()` and `resolve_item_id()` extracted to `text_utils.py`, shared by community voice and written comment extractors.

40 tests, data_sync integration (`written_comments` source), pipeline manifest updated.

**Remaining:** Backfill extraction across all AMID=31 documents, then re-run theme_extractor on meetings that gain written comments. After backfill, S21 is ready for graduation review.

### I100. City Contracts Tracker — "Wonkboard" for Consent Calendar
**Origin:** S21.5 wave 2 planning (2026-04-05) | **Priority estimate:** Medium-high (S24 scope)

A `city_contracts` table tracking vendor, description, annual cost, approval/expiration dates, and renewals over time. Cross-referenced with campaign contributions (vendor → donor matching) and consent calendar agenda items. Surfaces patterns like: same vendor winning renewals across years, contract amounts increasing, vendors with simultaneous donor activity. The consent calendar is where real money moves and nobody reads it — totalizing it and tracking vendor history over time is the "financial transparency on the boring stuff" edge that no local publication produces. Operator-only initially (wonkboard), graduate after data quality validation. Depends on: S24 entity resolution for vendor normalization.

### I101. Competitive Landscape Research: Local Civic Tech
**Origin:** S21.5 wave 2 planning (2026-04-05) | **Priority estimate:** Reference only

Researched 10+ local publications and civic tech projects for newsletter/orientation format design. Key finding: no one does structured data cross-referencing + plain-language narrative + pre-meeting orientation. Grandview Independent does editorial previews but can't scale; Civic Sunlight AI summaries hallucinate without data backbone; Councilmatic/Agenda Watch serve researchers not residents; FiscalNote's Curate serves lobbyists. Our whitespace: community voice history (15K+ comments), reliability (every meeting, forever), consent calendar financial transparency, participation infrastructure ("If You Go" block). Full research notes in plan file `optimized-whistling-clarke.md`.

### I102. Operator Settings: Human-Readable Decision Framing
**Origin:** Operator settings dashboard session (2026-04-06) | **Priority estimate:** Medium — next settings touch

The settings page currently labels controls with Python variable names ("match_strength", "corroboration_3plus", "anomaly_factor"). These should be reframed as decisions the operator actually makes, not technical parameters they need to understand. Examples:

- "Match strength weight: 0.35" → "How much should name matching matter?" with plain-language description
- "Corroboration 3+: 1.30x" → "How much extra credit for 3+ independent signals?"
- "Anomaly stddev threshold: 2.0" → "How unusual does a meeting need to be before flagging it?"
- "Post-vote penalty: 0.70x" → "How much less should post-vote donations count vs. pre-vote?"
- Tier thresholds could show example scenarios: "At this threshold, a $2K donation 60 days before a vote with a name match would be Tier __"

### D32. RPC Functions as Single Points of Failure
**Origin:** Meeting zero-items bug (2026-04-07) | **Priority estimate:** Medium

The `get_meeting_counts` RPC was the sole source of agenda item/vote counts for all meeting list views. When it failed (dropped during migration, transient error), every meeting silently showed "0 items." Fixed with a direct-query fallback in `fetchMeetingCounts()`. But the pattern exists elsewhere — any `supabase.rpc()` call that silently defaults to empty on failure is a potential invisible data outage. Audit all RPC call sites for similar silent-failure patterns. Candidates: `find_similar_items`, `get_meeting_counts` (fixed), any future RPCs.

### I103. RPC Health Check in /api/health
**Origin:** Meeting zero-items bug (2026-04-07) | **Priority estimate:** Low

The `/api/health` endpoint probes base tables but doesn't verify RPC functions exist and return data. Adding a lightweight RPC probe (call each RPC with a known-good input, verify non-empty response) would catch RPC regressions before users do. Could run as part of the existing health check or as a separate `/api/health/rpc` endpoint.

Design principle D4 applies: plain language is the visible label, technical precision lives in tooltips. The current UI violates this. Each slider should have a ~10-word plain-language label, a subtitle explaining what happens when you move it, and a tooltip with the actual variable name for pipeline debugging.

### I104. Pipeline Post-Sync Revalidation Hook --> Promoted to S24.12
**Origin:** ISR cache staleness after meeting zero-items fix (2026-04-07) | **Priority estimate:** Medium

The `POST /api/revalidate` endpoint now exists but nothing calls it automatically. After every data sync (`sync_escribemeetings`, `sync_netfile`, etc.), the pipeline should POST to `/api/revalidate` with the affected paths. This ensures ISR-cached pages reflect new data within minutes of a sync, not up to an hour later. Implementation: add a `revalidate_paths()` helper in `src/` that the sync functions call at the end of a successful run.

### D33. ISR Staleness as Silent Data Bug
**Origin:** Two meetings showing 0 items despite correct DB data (2026-04-07) | **Priority estimate:** Low (awareness)

ISR's "serve stale on revalidation failure" behavior means a page cached with bad data can persist indefinitely if every subsequent revalidation also fails. For a civic data platform, stale ISR = invisible data regression. The revalidation API helps, but consider: (1) adding a `data-freshness` meta tag to ISR pages showing when data was last fetched, (2) monitoring ISR revalidation success/failure rates in Vercel, (3) alerting when a page hasn't successfully revalidated in >2 hours.

**Follow-up (2026-04-07 evening):** Operator confirmed the 0-items display persisted after the fix was deployed, confirming ISR cache as the remaining cause. The fix (commit 0749972) and revalidation endpoint are both in place — this is purely a cache TTL issue. Validates that I104 (pipeline post-sync revalidation hook) should be prioritized to prevent this class of issue from recurring.

### V10. ISR Cache Invalidation After Data Fix — Manual Verification Needed
**Origin:** Follow-up investigation session (2026-04-07) | **Priority estimate:** Medium

After deploying the `fetchMeetingCounts()` fallback fix, the meetings page still showed "0 items" for April 7 and March 24 meetings due to stale ISR cache. The operator should either wait for the 1-hour TTL to expire, hit `POST /api/revalidate` with `{"paths": ["/meetings"]}`, or trigger a Vercel redeploy to bust the cache. This is a one-time manual action — the underlying data and code are both correct now.

### I106. Email Delivery Idempotency Tracking
**Origin:** S23.1 implementation (2026-04-07) | **Priority estimate:** Low

The send-recap and send-digest endpoints have no deduplication — calling the same endpoint twice for the same meeting sends emails twice. A lightweight `email_sends` table (meeting_id, subscriber_id, email_type, sent_at) with a unique constraint would prevent accidental double-sends. Not urgent for v1 (operator calls manually), but needed before any automation triggers these endpoints.

### I107. Topic Page Query Optimization
**Origin:** S23.3 implementation (2026-04-07) | **Priority estimate:** Low

`getTopicCounts()` fetches all agenda items with topic labels and aggregates in JS. This works fine at current scale (~3K items with labels) but won't scale to 50K+. A Supabase RPC with `GROUP BY topic_label` would be more efficient. Consider adding when multiple cities are active or item counts grow significantly.

### D34. Frontend `comment_summary` Naming Collision
**Origin:** S23.5 type conflict (2026-04-07) | **Priority estimate:** Low (awareness)

The `AgendaItemWithMotions` interface has a computed `comment_summary` field (object with `total` and `notable_speakers`) built in queries.ts from speaker data. The new AI-generated summary column had to be named `ai_comment_summary` in the DB to avoid collision. This naming asymmetry is tech debt — ideally the computed field would be renamed to `comment_stats` or similar, and the AI summary would take the cleaner `comment_summary` name. Low priority since both work correctly.

### I108. Preference-Filtered Email Delivery (S23.2 v2) --> Promoted to S24.10
**Origin:** S23.2 scope decision (2026-04-07) | **Priority estimate:** Medium

v1 digest sends to all subscribers. v2 should filter by `email_preferences` table — subscribers who follow specific topics only receive digest sections matching their preferences. Requires joining through agenda_items.topic_label to match against preference values. The data model exists (migration 080), just needs the join logic in the send-digest endpoint.

### D35. COLS_MEETING_LIST Excluded meeting_summary — Broke Homepage Card --> RESOLVED
**Origin:** Operator bug report (2026-04-07) | **Priority estimate:** Fixed

The egress reduction commit (e48c90c) added `COLS_MEETING_LIST` column projection excluding `meeting_summary` to reduce bandwidth. But `LatestMeetingCard` on the homepage renders `meeting_summary` as bullet points — so the meeting card silently lost its summary content. The field is small (3-5 short lines), not comparable to the `metadata` JSONB or `description` TEXT fields that justified the projection. Fixed by restoring `meeting_summary` to `COLS_MEETING_LIST`.

**Lesson:** Column projection constants need a consumer audit — check all components that consume the query before excluding fields.

### I109. SourceBadge on Single-Tier Pages Adds No Signal
**Origin:** Operator feedback on Find My District page (2026-04-07) | **Priority estimate:** Low (awareness)

The T1 SourceBadge components on the Find My District page were flagged as "pointless artifacts." On a page where every data source is Tier 1 (official government records), the tier badges add visual noise without differentiating anything. SourceBadge is designed for mixed-tier contexts (About/methodology, Reports pages) where distinguishing source credibility matters. On single-tier pages, plain-text attribution is sufficient. Removed from Find My District; worth auditing other pages for similar badge-without-signal patterns.

### I110. "Most Discussed" Query Threshold Was Too Restrictive --> RESOLVED
**Origin:** Operator bug report (2026-04-07) | **Priority estimate:** Fixed

`getMostDiscussedItems()` required `public_comment_count > 3` (4+ speakers) within 60 days. With Richmond's meeting cadence (~2 per month, ~4 in 60 days), this threshold was often unmet, causing the entire "Most Discussed at City Hall" section to silently vanish (`MostDiscussedItems` returns `null` on empty array). Lowered to `> 1` (2+ speakers) and extended lookback to 90 days. The section should now reliably show content as long as any recent meeting had meaningful public participation.

### I111. Automated Recap Email After Pipeline Completion
**Origin:** S23.6 pipeline discussion (2026-04-07) | **Priority estimate:** Medium

The operator currently reviews and sends recap emails manually via the RecapEmailPanel. Once the email format is validated and the feature graduates from operator-only, consider adding a GitHub Actions step after `recap_generation` that auto-calls `/api/email/send-recap` for newly generated recaps. This would close the last-mile gap entirely. Blocked on: publication tier graduation (judgment call).

### I112. Enrichment Cascade DAG Verification Tool
**Origin:** S23.6 pipeline analysis (2026-04-07) | **Priority estimate:** Low

During planning, discovered that `minutes_extraction` being classified as a "source" (not "enrichment") in the pipeline manifest means `run_downstream()` excludes it from the cascade. This is correct behavior but non-obvious. A `pipeline_map.py cascade <source>` subcommand that shows exactly what would run with `--enrich` (including what gets filtered out and why) would help debug future cascade gaps.

### D36. Operator API Routes Lack Server-Side Auth
**Origin:** S23.6 route review (2026-04-07) | **Priority estimate:** Low (awareness)

Existing operator API routes (`/api/operator/decisions`, `/api/operator/settings`, `/api/operator/sync-health`) don't verify the operator cookie server-side — they rely entirely on frontend `OperatorGate` to prevent rendering. The new `/api/operator/send-recap` does verify the cookie. The older routes should be updated to match for defense-in-depth, but since the operator secret is already a URL parameter (not a real auth system), the risk is low.

### I113. Neighborhood Council Officer Scraping — Google Docs Contact List
**Origin:** NC integration session (2026-04-07) | **Priority estimate:** Medium

The city maintains a Google Docs spreadsheet with president/VP/secretary names and contact info for all 31 NCs: `https://docs.google.com/document/d/1fJR4eTJzDSCbD83t5UCpANKfRA5VtoZgY7d9Z5eYxGo/edit`. JS-rendered content makes direct scraping impossible with `requests`; would need either Playwright or the Google Docs export API (tried `/export?format=txt` — redirects to `googleusercontent.com`). The `president` and `vice_president` columns exist in the DB but are empty. Manual entry or a Playwright-based scraper are viable paths. Officers change ~annually.

### I114. Dedicated Neighborhood Councils Page (`/neighborhoods`) --> Promoted to S24.5
**Origin:** NC integration session (2026-04-07) | **Priority estimate:** Medium-High ⚡

The find-my-district page shows one NC at a time based on address lookup, but there's no way to browse all 31 NCs. A `/neighborhoods` index page (similar to `/commissions`) showing all NCs in a card grid — with meeting schedule, active/inactive status, links — would be the natural complement. Data model and query already exist. Would also be a good candidate for the "find my neighborhood council" ArcGIS map embed (`experience.arcgis.com/experience/59a7bd37246744f498b546ecf9e4f28b`).

### I115. Neighborhood Council Meeting Schedule Scraper
**Origin:** NC integration session (2026-04-07) | **Priority estimate:** Low

Meeting schedules are currently seeded from ground truth (scraped once manually). A periodic scraper for the 31 individual NC pages on `ci.richmond.ca.us` would detect schedule changes. Pattern is straightforward — same HTML structure as commission roster scraper (`requests` + BeautifulSoup). Low priority because NC meeting schedules change rarely.

### D37. GeoJSON Neighborhood Code 36 (Greenridge Heights) Has No NC Mapping
**Origin:** NC integration session (2026-04-07) | **Priority estimate:** Low

The `richmond-neighborhoods.geojson` contains a "GREENRIDGE HEIGHTS" polygon (code 36) that doesn't correspond to any neighborhood council on the city website. Addresses in this area will show no NC match. May be part of a larger NC's territory (El Sobrante Hills or Hilltop District based on geography). Worth verifying with the ArcGIS NC boundary map and potentially updating the GeoJSON or NC ground truth.

### R16. Neighborhood Council → District Mapping for Cross-Reference
**Origin:** NC integration session (2026-04-07) | **Priority estimate:** Low

Each neighborhood falls within one or more city council districts. A formal NC-to-district mapping would enable queries like "which NCs are in District 3?" and allow the council profile pages to list the NCs in each district. The GeoJSON polygons overlap — a spatial intersection could compute this automatically, but a simpler approach is manual mapping from the ArcGIS layer.

### I116. Subscriber Cultivation Strategy Before June 2 Primary --> Promoted to S24.8
**Origin:** Planning session (2026-04-07) | **Priority estimate:** High ⚡

Email infrastructure is fully built (subscribers table, Resend integration, `/subscribe` + `/subscribe/manage`, operator send-recap panel) but there are effectively zero subscribers. With the June 2 primary ~8 weeks out, the features only matter if people receive the emails. Need: subscriber acquisition paths (social sharing, SEO landing pages, community outreach), possibly a "Richmond 101" orientation page as an entry point. The pipeline generates content daily; the gap is audience.

### I117. RPC Single-Point-of-Failure Audit --> Promoted to S24.11
**Origin:** Planning session (2026-04-07) | **Priority estimate:** Medium-High ⚡

The zero-items bug fixed on 2026-04-07 revealed that RPC mismatches in list views can silently return empty results. A systematic audit of all RPCs used in listing/card contexts would catch similar issues before they embarrass the platform during the election window when new users are arriving. Related to production stability.

### I118. Comment Summary Backfill -- Ready to Execute --> Promoted to S24.7
**Origin:** Planning session (2026-04-07) | **Priority estimate:** Medium

S23's comment summary pipeline is built but the backfill hasn't been run. Cost: $2-5 of Claude API calls. Reads from `item_theme_narratives` (already quality-checked at 0.7 threshold). Would complete S23's last gap and enrich every agenda item page with synthesized public testimony.

### I119. Amend D1 to cover generated content (post-Entry-52)
**Origin:** Provenance pattern audit (2026-04-27) | **Priority estimate:** Low

D1 currently demands `source_url`, `extracted_at`, `source_tier`, `confidence_score` on every UI-serving API response — but only for *data*. Auto-generated text (recaps, summaries, bios) was the exempt category, and that exemption is what made Entry 50 possible. Migration 095 closed the gap operationally (every artifact now has a sibling `*_provenance` JSONB), but D1 itself still reads as a data-only rule. Suggested amendment: extend D1 to require provenance on derived content too — "every auto-generated text artifact carries a sibling `*_provenance` row whose shape matches the `Provenance` discriminated union, written in the same UPDATE as the artifact."

Once amended, the pipeline-manifest's `generated_artifacts_have_provenance` expectation becomes the enforcement mechanism for the rule. Read `docs/design/DESIGN-RULES-FINAL.md` before editing — D1 wording is judgment-call territory.

### I120. Add `as_of` provenance to motions/votes for true write-time honesty
**Origin:** Provenance pattern audit (2026-04-27) | **Priority estimate:** Low

The `mixed` provenance kind on bios computes `from_minutes`/`from_transcript` *at generation time* — accurate when the bio is written, but stale if a transcript-source vote is later replaced by a minutes-source vote (which happens during the normal minutes-extraction supersession path). Two ways to handle: (a) regenerate bios on motion-source change (simple, costs API calls); (b) compute the breakdown at render time from the current motions table (more honest, but breaks the "provenance as a column" pattern). Probably (a) — fits the existing enrichment cascade in data_sync.py. Worth measuring how often bios go stale before deciding.

### I121. SourceAttribution coverage liveness — strengthen from "exists" to "matches generator"
**Origin:** Provenance pattern audit (2026-04-27) | **Priority estimate:** Low

The new `generated_artifacts_have_provenance` expectation only checks that the JSONB column is non-NULL. A stronger version would check that the `kind` matches what the generator should have written — e.g., `meeting_recap_provenance.kind` must equal `'official_minutes'` because the generator's vote gate enforces that invariant. Catches the case where a generator changes its inputs without updating its provenance builder. Implementable as a second expectation per artifact; not urgent because the first one (existence) catches the common bug.

### R17. Fill competitive intelligence research gaps ✅ Mostly resolved 2026-04-28
**Origin:** Locunity research session (2026-04-27) | **Priority estimate:** Low (intelligence repository, not roadmap-blocking)

Created `docs/research/competitive-intel/` with profiles of 9 civic-AI players + RC self-profile + market landscape, framed as a **negative map** (what NOT to build toward). 2026-04-28 fill-in pass closed most gaps + added [`_focus.md`](research/competitive-intel/_focus.md) (positive framing companion).

**Closed 2026-04-28:**
- **Aware:** Founder = **Alex Zaltsman**, Princeton NJ, founded 2024, $50K pre-seed (Mar 2025) + Microsoft for Startups + NJ AI Hub residency. Tech stack still inferred (likely Azure / OpenAI given Microsoft partnership). Disambiguation note: a separate "awarenow" leadership-training company (Trigubenko/Avunjian, 2017) appears in Tracxn — different company entirely.
- **Hamlet:** Founder = **Sunil Rajaraman** (ex-Scripted.com, sold 2017; Radiance Labs founding team, sold to Bloomreach 2023). Founded 2022, Orinda CA, **$7.5M raised** from Crosslink Capital, Kapor Capital, ANIMO Ventures, Glen Nelson Center, Home Technology Ventures (5 of 7 investors named). 8 employees. Acres.com partnership (Feb 2026) — Hamlet becoming a data layer.
- **HeyGov:** Founders = **Dustin Overbeck (CEO) + Andrei Igna (CTO)**, founded 2021, Madison WI. Payments-first DNA — HeyGov Pay is core; ClerkMinutes is suite extension. $25K disclosed (mostly Wisconsin Governor's Business Plan Contest first-place prize).
- **Next30Days:** Founder = **Clayton (last name not extracted)**, ex-Amazon PM, Seattle. Started Feb 2026. URL = `next30days.org` (verified). Uses **Legistar API** as unified upstream — covers any Legistar city with minimal city-specific code.
- **CivicPlus:** All 6 AI products from Jan 29 2026 launch documented: CivicPlus Agent · CivicPlus Athena · AI Content Advisor (websites) · AI Editing Assistant (websites) · AI Editing Assistant (agenda/meetings — direct ClerkMinutes competitor) · AI-Improved Category Search + Photo Analysis (SeeClickFix 311). Targeting AEO + SEO.
- **Locunity:** HQ corrected — Martinez, CA (SF address is virtual mailbox). Headcount = 3.

**New companion file:** [`_focus.md`](research/competitive-intel/_focus.md) — converts the negative map into positive declarations of what RC focuses on. Each "don't borrow X" anti-pattern flipped to a "do build Y" commitment. Decision framework restated positively.

**Still open:**
- **Locunity:** ASR vendor (proprietary "AI-first stack"), exact LLM, subscriber count, freshness SLA, action-marketplace launch timing.
- **Aware:** ASR vendor + LLM not disclosed. Total funding beyond $50K pre-seed.
- **Hamlet:** Remaining 2 of 7 investors. RVI/RFI methodology specifics. Pricing.
- **HeyGov:** Customer count. Pricing.
- **CivicPlus:** ASR/LLM vendors. AEO tooling depth.
- **Civic Sunlight:** Current subscriber count. Funding source.
- **Next30Days:** Clayton's last name. Long-term monetization plans.

Re-audit periodically for staleness — Locunity's Series A and action-marketplace launch will reshape the field; CivicPlus AI roadmap moves; OpenCouncil's release cadence affects S27 timing.

---

## Session Notes (2026-04-27/28, Liveness Failure Sweep)

After a SessionStart health-check showed 9 failing pipeline-liveness expectations, we cleared 3 in two changes:
- **Manifest fix**: `netfile_recently_synced` was checking `status='success'` but the `data_sync_log` enum is `completed/running/failed`. One-character SQL fix in the expectation. Cleared.
- **Migration 097**: Dedup of 2 candidacy pairs (Cesar Zepeda + Doria Robinson, both 2022 general). Pattern: research-seeded `elected` row (no FPPC, wrong-cycle committee) duplicating an FPPC-synced `filed` row. Migration promotes the FPPC row to `elected` and deletes the seed row. Cleared `no_duplicate_candidacies_per_election` entirely; reduced `candidacy_committee_cycle_matches` from 5 → 3.
- **Bonus**: The HIGH-severity `past_meetings_have_transcript_recap_within_5_days` flipped to PASS in the background (recap generation cron caught up on the 3/24 meeting between snapshot and re-check).

**Generalizable lessons:**
- The `status='success'` typo is a "wrote against an imagined enum" bug. Worth checking all SQL touching `data_sync_log.status` — the canonical values live in `src/data_sync.py` (`completed/running/failed`).
- The duplicate-candidacy pattern (seed row + FPPC row, same person/election, different status + committee_id) is reproducible. A future audit could catch it pre-publication by adding a UNIQUE INDEX or NOT VALID constraint on (city_fips, official_id, election_id) once the existing dupes are cleaned. Surfaced via `no_duplicate_candidacies_per_election` — that expectation should stay forever as a regression backstop.

**Six liveness expectations still failing — staged here for future sessions:**

### D38. Vote Explainer Dollar Amount Hallucinations (20 motions)
**Origin:** Liveness sweep (2026-04-27) | **Priority estimate:** Medium ⚡ | **Owner:** vote_explainer_generation

`vote_explainer_dollar_amounts_traceable_to_motion` flags 20 `motions.vote_explainer` rows that cite specific dollar amounts ($3.75, $13,096, $23,096, $200,000, $10,000, plus 15 more) which appear nowhere in `motion_text`, the agenda item description/title, or `agenda_items.financial_amount`. Classic LLM grounding failure — the explainer prompt let the model invent or transpose numbers.

**Tractable fix path:** Strengthen the vote_explainer prompt to forbid citing dollar amounts unless they appear verbatim in the inputs, then regenerate the 20 affected motions. The list is bounded — query `motions WHERE vote_explainer ~ '\$[\d,]+' AND <amount not in inputs>` to enumerate. Each regen is ~$0.001-0.002, total maybe $0.05. Worth a post-mortem on which inputs were available to the prompt vs. what the model made up — likely the prompt got `motion_text` but not the agenda item financial fields, so the model hallucinated.

**Public-facing impact:** These are visible on `/meetings/[id]` agenda item motion cards. Hallucinated numbers in financial-impact text damage credibility — this is a reputation risk, even at small dollar amounts.

### D39. Minutes URL Backlog (12 meetings >45d post-meeting)
**Origin:** Liveness sweep (2026-04-27) | **Priority estimate:** Medium | **Owner:** escribemeetings_minutes

`past_meetings_have_minutes_within_45_days` flags 12 regular council meetings missing `minutes_url`, ranging 62–90+ days post-meeting. Two possible causes:
1. Archive Center hasn't published the minutes PDFs yet (real upstream gap, not a pipeline bug)
2. The `escribemeetings_minutes` ADID-discovery scraper is missing them

**Tractable diagnostic:** For each missing meeting, manually check the Archive Center (AMID=31) for the date — if a PDF exists with that meeting date in the title, the scraper has a bug. If no PDF exists, this is a real city-side delay (clerk's office hasn't finalized minutes), in which case the expectation's 45-day window may be too aggressive — Richmond's minutes lag has historically been 4–6 weeks but can stretch.

**Decision needed:** If most are real gaps, relax the expectation window to 60 days. If most are scraper misses, investigate the ADID-discovery sequential scan. Look at git blame on `src/refresh_stale_minutes.py` and `src/escribemeetings_to_agenda.py` for recent changes.

### D40. Cycle-Mismatched Committee Links — ✅ MOSTLY RESOLVED 2026-04-29
**Origin:** Liveness sweep (2026-04-27) | **Owner:** candidate_discovery

**2026-04-29 update (public-readiness validation session):**
- ✅ **Bana 2026 primary + general** — fixed in migration 100 (`Soheila Bana for Council 2026` committee was in DB; just hadn't been wired up). Pre-fix she was attributed her 2022 cycle's $60,498 instead of her actual 2026 $8,000.
- ✅ **Eduardo Martinez November 2026 General** — newly discovered same session. Was pointing at "Eduardo Martinez 4 Richmond City Council 2018." Migration 089 fixed his June primary; migration 100 extended the fix to the November general row.
- ⏳ **Willis 2020** — re-linked to no-year-suffix committee (migration 101). The expectation still flags because the committee's `election_id` is anchored to 2024 (it's a single-cycle FK column that can't represent a committee spanning multiple cycles). The data displays correctly because:
  - The candidate page's `getFullCandidateDonors` filters contributions by date window (`cycleStart` to `cycleEnd`).
  - That window now has an upper bound (added 2026-04-29) — previously `cycleStart` had no upper, so Willis 2020 page showed his 2020+2024 contribs combined.
- 🟢 **No further action needed for June 2 primary.** Live expectation drops from 3 failures to 1 (Willis structural). The remaining is a schema limitation (committee.election_id is single-valued) — not worth restructuring before primary.

Lesson for future: structural mismatches don't always mean wrong-display bugs. The expectation flagged Bana + Martinez (real bugs — wrong cycle data displayed) AND Willis (cosmetic — committee anchors don't match candidacy year, but date filter prevents conflation). Future iterations of the expectation could distinguish "wrong committee" from "multi-cycle committee anchored to wrong year."

### D41. Candidates Without Committee Linked (Gallon, Wassberg)
**Origin:** Liveness sweep (2026-04-27) | **Priority estimate:** Low | **Owner:** netfile

`candidates_have_committee_linked` flags Keycha Gallon (City Council District 4) and Mark Wassberg (Mayor) with no `committee_id`. Three possible causes:
1. They haven't filed an FPPC committee yet (independent or pre-filing)
2. Committee was filed but name didn't match in `link_2026_candidate_committees` (migration 089)
3. They're write-in or non-controlled candidates (no committee required)

**Tractable diagnostic:** Manually check the public NetFile portal (https://public.netfile.com/pub2/?AID=RICH) for committees with their names. If found, add to migration 089-style linking. If not found, accept as legitimate no-committee candidates — possibly add a `committee_status` enum to `election_candidates` (`controlled / independent / write_in / unfiled`) so the expectation can ignore non-controlled candidates.

### V11. Stale NextRequest Sync (last update 2026-03-18)
**Origin:** Liveness sweep (2026-04-27) | **Priority estimate:** Low | **Owner:** nextrequest

`nextrequest_recently_synced` says the most recent `nextrequest_requests.updated_at` is 2026-03-18 — over 5 weeks old, well past the 14-day threshold. Should run `python src/data_sync.py --source nextrequest` (or trigger the daily workflow manually) to refresh. If the sync runs and the stale timestamp persists, the underlying NextRequest API may have stopped returning recent updates — investigate the discovery query in `src/nextrequest_scraper.py`.

### V12. One Past Meeting Without Comments or Summary
**Origin:** Liveness sweep (2026-04-27) | **Priority estimate:** Low | **Owner:** theme_extraction

`past_meetings_have_comments_or_summary` flags one meeting >14 days old with neither `public_comments` rows nor `meeting_summary`. Identify with: `SELECT id, meeting_date FROM meetings WHERE city_fips='0660620' AND meeting_date < CURRENT_DATE - INTERVAL '14 days' AND meeting_summary IS NULL AND id NOT IN (SELECT DISTINCT meeting_id FROM public_comments) LIMIT 5`. Then run `meeting_summary_generation` for that meeting (or accept that some special/short meetings legitimately have neither).

---

## Session Notes (2026-04-28, Decision Queue Surfacing)

The session-start briefing showed "Decisions pending: 69 (10 high, 59 medium)" with generic titles like "Assessment finding: failure" × 5 — operator had no idea what they were and had never seen them surface meaningfully. Triaged 66 stale/duplicate/already-fixed entries down to 3 active, fixed the briefing to show `description` not just `title` (commit e515949 → 540abad). The 3 deferred items below are not mechanical fixes — they're design questions that need operator input before implementation.

### D42. self_assessment.py dedup_key encodes date instead of finding identity — PARTIALLY MITIGATED 2026-05-17
**Origin:** Decision queue triage (2026-04-28) | **Priority estimate:** Medium ⚡ | **Owner:** self_assessment

**Update 2026-05-17:** The `run_failed` slice of this bug class is now structurally suppressed at context-build time via `_filter_resolved_failures` in `src/self_assessment.py`. If a `run_failed` entry's source has had a later `run_completed`, the assessor LLM never sees the failure — therefore can't generate a "finding" about it — therefore can't create a stale decision row. 9 unit tests in `tests/test_self_assessment.py::TestFilterResolvedFailures` pin the contract. This won the case that motivated this entry (the 3 stale "Assessment finding: failure" P0 rows from the netfile `_normalize_name` incident, 2026-05-14..05-17). It does NOT fix non-failure findings (perf regressions, coverage warnings, missing env vars without a recovery signal) — those still need the stable finding-identity treatment below.

`src/self_assessment.py:312` builds dedup keys as `f"assessment:{category}:{today}"` — i.e. `assessment:failure:2026-04-08`. Two failures stack:
1. **Prefix is too generic.** Every failure on a given day collides on `assessment:failure:DATE`, so unrelated failures with the same category (e.g. "vote_explainer slow" and "embedding_generation missing API key") can mask each other inside one row.
2. **Suffix is too specific.** Including the date means *the same underlying finding* (embedding_generation needs OPENAI_API_KEY — present every day for 4 weeks) creates a new row every day. We saw 4 such duplicates in the 2026-04-28 triage; the same issue had likely created ~25+ over the month before earlier resolution cycles.

**Why it's not a one-line fix:** The pending_decisions partial unique index is `WHERE status='pending' AND dedup_key IS NOT NULL`. So once a decision is resolved its dedup_key falls out of the unique partition and the next pending one with the same key inserts cleanly — that's the ledger-style behavior. Dropping the date from the key naively would cause new findings to silently fail-insert against old resolved findings; the partial index lets the same key reappear after resolution.

**Real fix:** Have the LLM-driven self_assessment emit a stable *finding identity* per item (e.g. `embedding_generation_missing_api_key`, `vote_explainer_runtime_high`) and use that in `dedup_key=f"assessment:{finding_identity}"`. Same finding within the pending window → silent dedup. Same finding after resolution → new row, correctly. The downstream effect is the assessment prompt needs to commit to a stable taxonomy. Worth a short design doc before implementing.

**Adjacent simpler fix:** As a stopgap, dedup by `f"assessment:{md5(description)[:16]}"` — exact-description match collapses, near-misses don't. Less ideal because LLM output rephrases the same issue across days, but it'd cut today's noise volume by ~50% with zero prompt changes.

### D43. self_assessment.py meta-noise floods the decision queue
**Origin:** Decision queue triage (2026-04-28) | **Priority estimate:** Medium | **Owner:** self_assessment

Of the 66 entries closed in the 2026-04-28 triage, ~17 were the assessment complaining about its own confused state:
> "Self-assessment consistently reports degraded health despite no failures"
> "Multiple self-assessments report degraded pipeline health despite no failures"
> "Self-assessment reports degraded health despite no failed steps or anomalies"

These are not findings about the pipeline — they're findings about the assessment's own output being inconsistent. Roughly: the LLM looks at recent assessments, notices "every recent assessment said 'degraded'", concludes that's itself a finding, and files it. Recursively. Every day.

**Tractable fix paths:**
1. **Drop "self-assessment" findings before pushing to decision queue.** Filter at `src/self_assessment.py:287-313` — if `category == 'anomaly'` or `'performance'` AND the description matches `r'self-assessment(s)?\s+(consistently|repeatedly|persistently)\s+report'`, skip. Mechanical.
2. **Tighten the assessment prompt** to forbid meta-findings about prior assessments. Means the assessment can't notice trends across runs, which loses some signal — but the signal it's currently emitting is not actionable, so net positive.
3. **Stop running self_assessment daily.** Run it weekly or on-demand instead. The daily cadence is what makes the meta-recursion possible (daily assessment sees daily prior assessments). Weekly cadence would dramatically cut volume.

**Coupled with D42:** if D42 lands first (stable finding identity), the meta-noise mostly self-resolves because the same "consistently report degraded" finding would dedup across days instead of accumulating. May be worth doing D42 first and re-evaluating whether D43 is still needed.

### I122. Make /operator/decisions page actionable (resolve buttons)
**Origin:** Decision queue triage (2026-04-28) | **Priority estimate:** Low | **Owner:** frontend

`/operator/decisions` exists at `web/src/app/operator/decisions/` and shows pending decisions with description (line-clamp-2) and evidence (expandable). But it's read-only — `/api/operator/decisions/route.ts` only has GET. Currently the only way to resolve a decision is via Claude Code or direct SQL UPDATE.

That's why decisions accumulate: visiting the page shows you what's pending, but you have to leave the page (open Claude Code, write a UPDATE statement, run it) to actually clear anything. Friction → accumulation → 69 unresolved entries.

**Tractable fix:**
1. Add `PATCH /api/operator/decisions/[id]/route.ts` accepting `{verdict: 'approved'|'rejected'|'deferred', note?: string}`, calling `update_decision_status()` from `db.py`. Need to add operator-auth check — see `OperatorGate` for the cookie pattern.
2. Add a "Resolve" button on each `DecisionCard` opening a modal with three-button choice + optional note textarea.
3. Optimistic update: on success, mark the card `isResolved=true` immediately so it visually moves to the recently-resolved section without page reload.

**Auth note:** the existing OperatorGate is cookie-based for read access. Resolve actions need stronger gating — at minimum, the API route should verify the operator cookie server-side (not trust client). See existing `web/src/lib/auth.ts` if it exists, or treat as a small auth design task.

**Why "low" priority:** Today's triage shows that bulk resolution via Claude Code is fast (60+ entries in one session). A resolve button on the page is a UX upgrade that makes routine ongoing maintenance possible; not blocking anything urgent.

### I122. "Where does the money go?" — vendor/contractor accountability page
**Origin:** Operator request (2026-04-28) | **Priority estimate:** High (Stewardship value, public-facing)

A landing page listing every entity the city is paying money to, with the contract approval that authorized each payment. Per row:
- **Entity** (vendor / contractor / consultant)
- **Approval date** (the meeting where the contract was approved)
- **Vote breakdown** — who voted Aye / Nay / Abstain / Absent, with links to the council members
- **Total approved** (contract value) + **time period** (start → end of the contract)
- **Actual payments to date** (from `city_expenditures`) — the running tally against the approved ceiling

Why this matters: this is the most direct expression of the **Stewardship** value in the public surface. "Did the council approve this? Who voted yes? How much are we paying them, over what period?" One question, one page, full provenance. Closes a transparency gap that local journalism would have covered before the 2,500+ newspaper closures since 2005 — typical resident has no way to assemble this picture today.

**Data already in the DB:**
- `city_expenditures` (Socrata) — vendor, amount, payment date
- `agenda_items` with `legal_framework='contract'` (after migration 098 backfill) — contract awards
- `motions` + `votes` — vote attribution per agenda item
- Migration 098's new `agenda_items.party_entities` JSONB — vendor names structured-extracted from contract items

**The gap that blocks this:**
Entity resolution between expenditure vendor names and agenda contract awards. `city_expenditures.vendor_name` and `agenda_items.party_entities[].name` are both freeform strings — "Chevron" vs "Chevron USA Inc." vs "Chevron Corp" appear as separate vendors today. This is exactly **Sprint 26 / B.46 entity resolution** territory. Without it, the page either has lots of duplicate rows (per-string-variant) or aggressive deduplication that hides real distinctions.

**Suggested build sequence:**
1. **MVP (no entity resolution):** Group `city_expenditures` by `normalized_vendor`. JOIN to `agenda_items` where the agenda item's `legal_framework = 'contract'` AND `party_entities` mentions the same normalized vendor. Show the page with a "vendor matching is string-based — variants like 'X Corp' and 'X' may be separate rows" caveat (mirrors the F3 industry/PAC caveat shipped today).
2. **After B.46 ships:** Replace string-match with entity_id JOIN. Caveat goes away. Duplicates collapse.
3. **Stretch:** "What item authorized this payment?" reverse lookup — every `city_expenditures` row gets linked back to its approving `agenda_items.id` so the vote attribution is one click away.

**Publication tier (proposed):** Graduated — start operator-only because (a) the string-match precision needs operator review on real Richmond data, (b) tying payments to votes is reputational territory (rubric: "Conflict/financial analysis → Graduated or permanent operator-only"), (c) framing matters ("the council approved $X to vendor Y" can read as accusatory when the vote was unanimous and routine; needs careful copy).

**Cross-references:**
- I3 (Vendor-Official Voting Pattern Detection) — same data sources, longitudinal angle. This new feature is the per-vendor view; I3 is the per-official angle.
- Sprint 26 entity resolution — the technical dependency for the non-MVP version.
- Migration 098's `legal_framework` + `party_entities` — gives us the structured contract-side data once the classifier backfill runs.
- The proposed `/elections/[slug]/finance` cross-candidate dashboard (Stream 2) is structurally similar — both are "Layer 2 aggregations rendered as a single landing page." Consider a shared `<EntityList>` component.

**Multi-city note:** This generalizes cleanly. Every California city has Socrata-equivalent expenditure data and eSCRIBE-equivalent agenda data; the entity resolution is the city-agnostic part. Aligns with the project's "Scale by default" tenet — Richmond ships first, but the architecture supports any city.

### I123. Bio summaries are stale — wire `bio_generation` into the enrichment cascade
**Origin:** Operator observation, council/[slug] page (2026-04-28) | **Priority estimate:** Medium-High

Eduardo Martinez's `/council/eduardo-martinez` summary still says "Last updated: 2/28/2026" — the bio narrative ("attended 18 of 21 meetings (86%) and cast 100 votes... voted with the majority 95% of the time and did not cast any sole dissenting votes") was generated against a snapshot two months out of date. New meetings (and their votes) have flowed through the pipeline since, but the bio doesn't know.

**Root cause:** `bio_generation` (`generate_bios.py`) is **not in `SYNC_SOURCES`** in `src/data_sync.py` — there's an explicit comment at line 1087 of `pipeline-manifest.yaml`: `# bio_generation: standalone script (council_profiles.py), not in SYNC_SOURCES`. So when the enrichment cascade runs (`data_sync.py --enrich` after a netfile / minutes_extraction / transcript_vote_extraction run), `pipeline_map.PipelineGraph.trace_downstream()` walks the DAG and dispatches every enrichment that's registered — but bio regeneration never fires because the dispatcher can't see it. The manifest *declares* `bio_generation` as the enrichment for `officials.bio_summary` (line 2240) and `officials.bio_factual` (line 2246), so the static lineage is right; the runtime hookup is the gap.

**What needs to happen after each meeting's votes are tallied:**
- `votes` count changes (cast 100 → cast 102 votes)
- `meeting_attendance` aggregation changes (18/21 → 19/22)
- `majority_alignment_rate` recomputes (95% may shift fractionally)
- `sole_dissent_count` may flip (the most reputationally-sensitive number on the page)

All four numbers appear in the rendered narrative. None of them update without a manual `python generate_bios.py` run.

**Fix path:**
1. **Add `sync_bios()` to `data_sync.py`** following the same contract as `sync_meeting_recaps`, `sync_orientation_previews`, etc. — detect officials whose latest motion/vote `created_at` is newer than `officials.bio_summary_generated_at`, regenerate just those, return stats.
2. **Register in `SYNC_SOURCES`** as `bio_generation: sync_bios`.
3. **Verify cascade trigger** — `pipeline_map.PipelineGraph.trace_downstream('motions')` and `trace_downstream('votes')` should include `bio_generation`. The manifest declares the relationship at line 454/456 (officials.read_by includes bio_generation), but trace order is determined by `reads_from` on the enrichment side — confirm `bio_generation`'s `reads_from` list in the manifest covers `motions`, `votes`, `meeting_attendance`, `meetings`. If not, add them.
4. **Add a liveness expectation** — `bio_summary_recent_for_active_council` — fails when any current council member's `bio_summary_generated_at` is more than N days behind the latest motion `created_at` for that official. Surfaces this exact staleness in the SessionStart health report so it doesn't go unnoticed again.

**Cost:** ~$0.05 per bio regeneration × 7 sitting council members = ~$0.35 per cascade trigger. Cheap. The cascade only fires when there's actually new vote data, so cost is bounded by meeting cadence (~24 meetings/year × $0.35 = ~$8/year for Richmond).

**Related:**
- **I120** (Add `as_of` provenance to motions/votes for true write-time honesty) — different layer of the same problem. I120 is about whether the *attribution count* in the provenance footer reflects the current state of the source. I123 is about whether the *narrative numbers in the body* reflect the current state. Both should be fixed by the same regeneration trigger; I120's "regenerate on motion-source change" approach naturally covers I123 too. Worth resolving them together.
- The same staleness pattern applies to **`meeting_summary`**, **`meeting_recap`**, and **`orientation_preview`** — but those are already in SYNC_SOURCES (`meeting_summary_generation`, `recap_generation`, `orientation_generation`), so they cascade correctly. `bio_generation` is the outlier.

### I124. Article-as-oracle data-quality gaps (Q1 2026 mayor race) — items (1)+(2)+(3)+(4) ✅ shipped 2026-04-28
**Origin:** Ground-truth comparison vs Richmondside article (2026-04-28) | **Priority estimate:** High (election-season credibility)

**Status (2026-04-28 EOD):** Items (1) article-as-oracle fixture, (2) cross-filing 497 dedup, (3) canonical-donor pre-pass, and (4) donor-employer merge have shipped. Cumulative cleanup across full Richmond history: 105 cross-filing duplicate pairs ($21,350) caught by (2); 12 alias-drifted donor rows merged by (3); 493 employer-key donor variants collapsed into 329 keepers + 143 exact-duplicate contributions caught by (4). Article-fixture status after all four: 1 of 5 candidates passing ($0 Wassberg). Jimenez moved from +$2.5K to +$1.5K. Anderson moved further short ($21,675 vs $40,500 article) because (4) revealed $4K of Q1 contributions that were genuinely double-counted under different employer strings — the new gap is firmly real missing data, addressed by item (5) IE audit.

Compared every Richmond mayoral candidate's totals on Richmond Commons against the Richmondside Q1 2026 filing-period briefing (`https://richmondside.org/2026/04/27/richmond-mayoral-candidates-campaign-finance-reports/`, "through April 18, 2026"). Wassberg matches ($0 ✓). Martinez's gap is correct (article includes ~$2,300 carryover from prior campaigns; our cycle window correctly excludes those). The other three diverge:

| Candidate | Article (Apr 18) | DB (Apr 18) | Δ |
|---|---:|---:|---:|
| Anderson  | ~$40,500 | $30,175 | **−$10,325** |
| Jimenez   | ~$31,000 monetary | $35,958 | **+$4,958** |
| Johnson   | ~$7,500 | $4,050 | **−$3,450** |

The $-10K Anderson gap and $+5K Jimenez gap surfaced four distinct data-quality bugs:

**(a) Donor entity-resolution gaps — same person, multiple rows.**
The donor table's natural key is `(normalized_name, employer)` (see `src/db.py` `load_contributions_to_db`), so any string variation in the employer field produces a duplicate donor row. Examples found in Anderson's top donors:
- **Buffy Wicks** — two rows, same date `2026-03-19`, employers `"California"` vs `"California State Assembly"`. Sums to $5,000 in DB; article says one $2,500 gift.
- **Davillier Sloan Inc** — two rows, employers `""` vs `"N/A"`. Sums to $2,200; article says single $1,000.
- **Carl Adams** — two rows, same date `2026-03-20`, employers `"Developer"` vs `""`. Sums to $2,000.
The "(N gifts)" badge introduced 2026-04-28 makes this issue more visible (operator can see donor counted 2x for the same date), but the underlying merge is the real fix.

**(b) Cross-committee 497 duplication — same contribution, two filings.**
California Form 497 (24-hour late report) gets filed twice by design: once by the *giving* committee as Form 497 Part 2, once by the *receiving* committee as Form 497 Part 1. When both filings are extracted, the same contribution lands in the DB twice. Examples:
- Anderson's RPOA contribution shows as $5,000 across two rows (Apr 10, Apr 13) — article says single $2,500. The Apr 10 row's filing_id `216618889` is annotated in `anderson_mayor_2026.json` as "From RPOA PAC Form 497 Part 2 (contribution made to Anderson)"; the Apr 13 row's `216629636` is Anderson's own 497 Part 1 — same dollars, two filings.
- Jimenez's Firefighters Local 188 PAC appears as both `"International Association of Firefighters"` and `"Independent PAC Local 188 International Association of Firefighters"`, each $2,500.

Fix: the loader needs a dedup pass keyed on `(donor_normalized, recipient_committee, contribution_date, amount)` that prefers the receiving-committee filing (which is canonical from the recipient's accounting view). Or: reconcile at extract time by detecting Form 497 Part 2 entries naming a committee we already have a Part 1 for.

**(c) Vision OCR canonical-name drift.**
The new Vision OCR fallback (commit 3dd05b9) reads form text visually. On at least one Anderson 497, RPOA was transcribed as `"Richmond City Police"` with employer `"Richmond City Police"` ($2,500, 2026-04-13). The form's printed text might abbreviate, or the OCR misread a logo or formatted name. This compounds (a) — the same contributor gets a *third* row identity. Adding a canonical-name pre-pass (similar to `prompts/canonical_names.md` for transcript names) on contributor names extracted via Vision would catch this. Common civic donors (RPOA, SEIU 1021, UTR, Chevron, etc.) should have a known-aliases list the extractor consults at write time.

**(d) Real missing data — Anderson is short ~$10K even after deduping.**
After accounting for (a)–(c), Anderson's DB total is still below the article. Article-named donors not yet matched in our DB include Tom Butt's $1,000 (2026-04-15 row exists in DB), Andrew Butt $1,000, Joel Young $1,000 (in DB, 2025-11-01 — outside Q1 window), and various smaller named gifts. Some article totals likely include independent expenditures (East Bay Working Families $4,000 mentioned for Jimenez) that aren't direct contributions to the campaign committee. Worth a row-by-row audit against the article's named donors to identify which are missing entirely versus dated outside Q1 versus simply not surfaced in the top-5.

**Suggested fix path (sequenced):**
1. ✅ **Article-as-oracle test fixture** (commit f163610) — `tests/test_filing_period_briefing.py` pins Richmondside Q1 totals as tolerance-bounded assertions. Currently failing in expected ways for 4 of 5 candidates; tracks convergence as remaining items land.
2. ✅ **Cross-committee 497 dedup at load time** (commit 9d4eb65) — `src/dedup_contributions.py` finds and removes near-date cross-filing dupes (same donor, same recipient, same amount, different filing_id, ±14 day window). Wired into `db.load_contributions_to_db` post-batch. Collapsed Anderson RPOA $2,500 dup and Jimenez IAFF Local 188 $2,500 dup; broader backfill removed $21,350 in pre-2026 NetFile re-extraction artifacts.
3. ✅ **Donor canonical-name pre-pass** (commit 6e0bbcb) — `src/prompts/canonical_donors.md` + `src/canonical_donors.py` resolve OCR/alias drift on entity names (RPOA, IAFF Local 188, SEIU, Chevron, etc.). Applied at `db.load_contributions_to_db` insert time and via `src/backfill_canonical_donors.py` one-shot. Collapsed 12 alias-drifted donor rows.
4. ✅ **Donor-merge migration** for (a) employer-key duplicates — `src/merge_donor_employers.py` collapses same-name donors with near-equivalent employers under three conservative rules: (i) all employers are empty-equivalent (NULL/"N/A"/"None"/"retired"/etc.) → merge into one row; (ii) one specific employer + N empty-equivalent → merge empties into the specific row; (iii) one normalized employer is a substring/word-subset of another (≥4 chars) → merge into the more-specific row. 493 donor rows collapsed into 329 keepers; 1019 contributions re-pointed; 143 exact-duplicate contributions caught and dropped. Wired into `db.load_contributions_to_db` via empty-employer normalization at insert time so future syncs don't reintroduce the fragmentation. Long-term fix for the John-Smith-different-employers case (genuinely different people sharing a name) is B.46 entity_id JOIN.
5. **Independent expenditure audit** for (d) missing data — separate flow. East Bay Working Families and similar IE committees report to CAL-ACCESS, not local NetFile; verify the calaccess sync is capturing 2026 IEs against Richmond candidates. Anderson's −$15K residual gap most likely lives here (article may be including IEs in its candidate-level totals).

**Cross-references:**
- **B.46 / Sprint 26 entity resolution** — the durable fix for (a), (c), and the donor side of (d).
- **I122** ("Where does the money go?" vendor accountability) — same string-variant problem on the expenditure side. Whatever solution lands for donors should generalize to vendors.
- **I3** (Vendor-Official Voting Pattern Detection) — once entity resolution lands, this gets accurate too.

**Why this matters now:** election season is live. The candidate detail pages claim auto-generated provenance from "NetFile + extracted paper filings" — when an operator points to the platform and a journalist points to the article, the numbers visibly disagree. The article is the oracle the public will trust during the primary; we need to either match it or surface the discrepancy honestly. Item (a) and (b) are mechanical fixes that should ship before public graduation of the briefing section.

### I125. Unitemized small-donor contributions are systematically missing from extraction
**Origin:** Anderson $928 gap investigation (2026-04-28) | **Priority estimate:** Medium (election-season credibility, multi-candidate)

California FPPC Form 460 reports two kinds of monetary contributions:
1. **Itemized** (Schedule A) — every contributor of $100 or more in a period named individually with date/amount/employer.
2. **Unitemized** — every contributor under $100 summed into a single line on the Schedule A Summary ("Cash contributions of less than $100 not itemized").

Our paper-filing extractor (`src/netfile_paper_extractor.py`, both text and Vision paths) only captures itemized rows. The unitemized total is reported on the Schedule A Summary page but not extracted as a line item. Result: every paper-filing candidate's `contributions` total is short by their unitemized amount.

Verified for Anderson (Q1 2026 cycle):
- Form 460 Line 5 Total Contributions Received cycle-to-date: **$40,602**
- Our DB cycle-to-date: **$39,572**
- Gap: **$1,030** = $643 unitemized in 2025-H2 + $2,255 unitemized in 2026-Q1 minus $1,868 of overlap that something accounts for (likely the 2025-H2 form's $385 reconciliation between cover-page total and Schedule A summary). Gross unitemized: $643 + $2,255 = $2,898; net missing: ~$1,030.

This is the source of the residual Anderson gap that survived all four I124 (1)-(4) fixes. It's a systematic pattern across every paper filer — Jimenez, Johnson, Martinez and any future paper-filing candidate will all be similarly short by their unitemized total.

**Fix path (Tractable):**
1. **Extract Schedule A Summary line items.** When extracting a Form 460, also read the Schedule A Summary page (typically page 4 of an 8-page form). The Vision OCR path can do this with an additional prompt requesting Lines 1 (itemized), 2 (unitemized < $100), 3 (subtotal). Persist the unitemized number in the JSON alongside individual contributions.

2. **Synthesize a single "unitemized" row at load time.** When `load_paper_filings.py` reads a JSON with a non-zero unitemized total, insert one synthetic contribution row with:
   - `contributor_name = "Unitemized contributions (< $100 each)"`
   - `donor_id = a single shared donor row marked as a synthetic aggregator` (or a per-period row to keep them distinguishable)
   - `amount = the form's unitemized total for that period`
   - `contribution_date = period_end_date` (or the last day of the reporting period)
   - `entity_code = 'UNI'` (a new sentinel value, or use a metadata flag)

   This produces a dollar-accurate cycle-to-date total without falsely implying we have donor identity for the small-dollar gifts.

3. **Frontend renders unitemized rows differently.** Top-donors lists and donor breakdowns should display "Small donations under $100 (aggregated, $X total, count not disclosed by FPPC)" as a separate line. Don't treat the synthetic row as a normal donor.

4. **Article fixture tightens.** Once unitemized rows are loaded, the Anderson gap should drop from $1,030 to <$200. Tighten `TOLERANCE_USD` from $1,500 to $500 — bringing back the original "this should match precisely" assertion.

**Cross-references:**
- I124 items 1-4 — fixed itemized-row data quality. This is the next layer.
- B.24 / Sprint 26 — entity resolution doesn't apply (no entity to resolve for unitemized). This is purely an extraction gap.
- D6 design rule (narrative over numbers) — unitemized aggregations are a perfect place to use narrative ("Small grassroots donations under $100 totaled $X across Y reporting periods") rather than a single dollar number that hides the structure.

**Why "medium" priority:** Anderson's $1,030 unitemized share is ~2.5% of his total. For a candidate with stronger small-dollar fundraising (which is what unitemized represents — coffee-and-pastry events, online petitions, small employee donations), the share could be 10-30%. Without this fix, our public dollar totals systematically understate small-donor support — which is the opposite of what a transparency platform should do. Should ship before the briefing section graduates from operator-only to public.

**2026-04-29 update:** ✅ Fully shipped during the public-readiness validation pass. Form-460 cover-page summary extraction (`parse_form460_summary_with_vision`), persistent cache (`src/data/form_summaries.json`), reconciliation enrichment with monetary-only comparison, and synthetic UNI rows are all live. 4-of-4 mayoral + 4-of-4 district candidates now reconcile within $1 of their Form 460 Line 1 Monetary. Jimenez OVER $1,468 was investigated and confirmed real — IAFF Local 188's 4/10 $2,500 contribution to her appears on IAFF's 497 Part 2 but was not itemized on Jimenez's 460 (likely she'll catch up next quarterly). Not a dedup bug; the reconciliation enrichment correctly flags this as OVER for operator review without silent display.

### I126. Form 460 cover-page OCR transposes `cycle_to_date` and `this_period` for Martinez
**Origin:** Public-readiness validation (2026-04-29) | **Priority estimate:** Low | **Owner:** netfile_paper_extractor

When `parse_form460_summary_with_vision` extracted Eduardo Martinez's Form 460 (filing 216686659, period 2025-06-30 to 2026-04-18), it produced:
- `monetary_cycle_to_date: 4967.39`
- `monetary_this_period: 6103.59`

These are transposed — `this_period` should equal or exceed `cycle_to_date` for an ongoing cycle, not the other way around. The DB monetary total for Martinez ($6,103.59) matches `monetary_this_period`, so the reconciliation enrichment uses the right field; nothing public-facing is broken. But the cached `cycle_to_date` is wrong and could mislead a future consumer (e.g., a "lifetime totals" feature). The Vision prompt likely reads the cover page in an unexpected order for forms where the period_start ≠ Jan 1.

**Tractable diagnostic:** Add a sanity check in `parse_form460_summary_with_vision` — if `monetary_this_period > monetary_cycle_to_date`, swap them OR re-run extraction with a clarifying prompt asking the model to label which value is which. Could also add a unit test on a fixed PDF asserting `cycle_to_date >= this_period`.

### D44. Suspicious inter-committee transfer pattern (Bana/Jimenez ↔ IAFF/RPOA) — DIAGNOSED 2026-04-29
**Origin:** Edge-case audit (2026-04-29) | **Status:** Partially diagnosed — one confirmed bug + two ambiguous cases | **Owner:** netfile

Three 2026 contributions flagged as "candidate committee giving TO a labor PAC":
- Bana 2026 → IAFF Local 188 PAC, $2,500, 4/21 (filing 216663665)
- Bana 2026 → Richmond Police Officers Association PAC, $2,500, 4/15 (filing 216635523)
- Jimenez 2026 → IAFF Local 188 PAC, $2,500 (filing 216618902)

**Diagnostic done 2026-04-29 via NetFile MCP cross-check + DB pattern audit.**

**Confirmed bug (1 of 3):** Filing 216618902 contains BOTH directions of the same $2,500 transaction on the same date (IAFF→Jimenez AND Jimenez→IAFF). NetFile authoritative data (transaction_type=20, F497P1) shows only IAFF→Jimenez on 2026-04-20. The reverse "Jimenez→IAFF" row has no source in NetFile — it's a scraper artifact. Most plausible explanation: when the scraper ingests an F497P2 (Late Contribution Made Report, filed by the donor), it records the filer as `committee` and the named recipient as `donor`, reversing the actual money direction.

**Ambiguous cases (2 of 3):** Filings 216635523 (Bana→RPOA) and 216663665 (Bana→IAFF + Doria→IAFF) do NOT appear in NetFile MCP's F497P1 view. They could be either:
- (a) **Legitimate slate-card payments** from candidate committees to PACs (campaigns pay PACs to be included in slate-card mailers). This is a real recurring pattern — see below.
- (b) **F497P2 ingestion artifacts** like 216618902, where the donor's late-contribution report got direction-flipped.

To confirm, inspect each filing PDF via the public NetFile portal (`https://public.netfile.com/pub2/?AID=RICH&filing={id}`).

**Pattern context (audit query is over-broad):** A pattern audit of all 24 historical "candidate-committee-as-donor" rows shows a clear slate-card cluster: ~$2,500 payments in August-September of even years (2018, 2020, 2022) from multiple candidate committees to IAFF/RPOA/Richmond Sun on the same filing dates. These are legitimate, recurring slate-card payments. Killing all "candidate→PAC" rows would lose that real data. The audit query that flagged D44 needs refinement to disambiguate slate-card payments from F497P2 ingestion artifacts.

**Two follow-up work items:**
1. **Scraper fix (netfile_client / paper_extractor):** Investigate F497P2 ingestion to verify donor/committee field mapping. The hypothesis is that P2 inverts filer-vs-transaction-party roles compared to P1 and the scraper does not handle this. If confirmed, fix and reload the affected 2026 rows.
2. **Audit-query refinement:** The "inter-committee transfer" audit should distinguish (a) same-filing-id reverse-direction duplicates (the 216618902 pattern) from (b) standalone candidate→PAC rows that match slate-card timing (legit). Option a flags the bug class; option b shows real expenditures.

**Why this matters for public-readiness:** Currently OperatorGate'd, so not displayed publicly. The PAC profile pages V2 (just shipped) include outgoing-flow tables that show inter-committee flows — if the F497P2 bug isn't fixed before public graduation, those tables will display the reverse-direction artifacts as if they were real candidate-to-PAC payments.

### I127. FilingPeriodBriefingSection footer overstates "Reconciled to Form 460"
**Origin:** Public-readiness validation (2026-04-29) | **Priority estimate:** Medium (graduation blocker) | **Owner:** filing_period_briefing

Current footer text: "Reconciled to Form 460 Line 1 Monetary (the candidate's own legal filing)."

This overclaims because:
1. The briefing window extends to `filed_through` (most recent filing) which is typically 5-7 days AFTER the most recent Form 460's period_end. Late-contribution Form 497 filings between those dates ARE in the briefing total but NOT on any Form 460.
2. Donor-side 497 Part 2 filings (IAFF Local 188's $2,500 to Jimenez) appear in the DB but not on the recipient's 460 if the recipient hasn't itemized yet. The briefing total includes them; the form 460 doesn't.
3. The F1 totals shown can therefore exceed the candidate's own Form 460 cover-page Total. The reconciliation enrichment flags this as OVER, but the footer still claims "reconciled."

**Honest revised footer:** "Reflects each candidate's official NetFile filings — Form 460 cover-page totals plus any Form 497 late-contribution reports filed through {filed_through}. Reconciliation to Form 460 Line 1 Monetary monitored continuously; discrepancies flagged for operator review before public display."

**Why "medium" priority and graduation blocker:** Per the user's stated values ("I just want to display public data and I want it to be accurate and not misleading"), the current footer text is *technically* accurate for the within-form-period subset but misleading for the full window. Graduation from operator-only to public requires this footer to either:
(a) be updated to the honest version, or
(b) restrict the briefing window to each Form 460's exact period_end (losing the post-form 497 visibility but keeping the "reconciled" claim true).

Option (a) preserves more data and is more honest about the FPPC reporting reality. Option (b) is simpler. Operator judgment.

---

## Phase 4 Workstreams: Follow the Money — Captured 2026-04-29

Vision conversation 2026-04-29 reframed the project around money flow.
The unifying noun is **Contributions** — the menu structure says what
the project is FOR, not what government does. Sub-menu: `Candidates |
Vendors | PACs`. Each surface uses the same design grammar pioneered
by `/council/voting-patterns`:

> **Explore-then-detail.** Playable graphic surface up top (the "huh"
> moment), expandable temporal layer in the middle (change over time),
> sortable detail table below (the receipt). One pattern, five surfaces:
> candidate, council member, donor, vendor, PAC.

Workstream keys for the items below:
- **WS-1** — Information architecture + candidate page redesign
- **WS-2** — Cross-candidate / cross-employer / donor / PAC profiles
- **WS-3** — Vendor / scanner work (the long arc — connects city money OUT to donations IN)
- **WS-4** — Temporal layer + late-contribution coverage
- **WS-5** — Foundation / housekeeping
- **WS-6** — Coalition Fidelity (position taxonomy + member-PAC alignment scoring) — see I154

### I128. Dynamic next-election navigation (WS-1)
**Origin:** Vision 2026-04-29 | **Priority:** High (graduation prerequisite) | **Owner:** web

Replace the static `Elections` index page with a dynamic dropdown that shows ONLY the next upcoming election (queried from `elections WHERE election_date >= today ORDER BY election_date LIMIT 1`). Hides when no election is upcoming. Auto-promotes November 2026 General after June 2 primary without a code change. Remove the `/elections` index route (or 301 to next-election); remove "All elections" link from candidate page header. Past elections remain at their `/elections/[slug]` URLs for archival/SEO purposes but are unpromoted.

### I129. `Contributions` menu rename + sub-routes (WS-1, WS-2)
**Origin:** Vision 2026-04-29 | **Priority:** High (mission framing) | **Owner:** web

New top-level nav: `Contributions` → `Candidates | Vendors | PACs`. Mission-statement-as-IA. Renames the existing `/council` audience model (which currently means "current council members") to fit under `Candidates`, where it joins active 2026 candidates under one umbrella. Sitting council members get the same page format as challengers — what differs is whether the voting-history section renders.

**Path B sequencing in flight 2026-04-29:** PAC profile pages shipped operator-only as V1 (see I134). Menu rename pending until the operator has soaked the surface and validated sponsor disclosure prose. Vendors stays a placeholder until WS-3 (I142) ships entity resolution.

### I130. Shared `<DonorTable>` component (WS-1)
**Origin:** Vision 2026-04-29 | **Priority:** High | **Owner:** web

Sortable, filterable donations table modeled on the DNA of `DivergentMotionsTable.tsx`. Used on candidate pages, donor profile pages, vendor pages (for matched donations), PAC pages. Color cues for "this donor also gave to X." Click-through to donor profile. The unified component avoids re-implementing donor list rendering 5 times across surfaces.

### I131. Same candidate-page format for sitting council + active candidates (WS-1)
**Origin:** Vision 2026-04-29 | **Priority:** High | **Owner:** web

Single component that renders: race header (or current role), voting history (if incumbent), donor table, temporal sparkline. Conditional rendering for whether voting history exists. Once a resident learns to read one of these pages, they can read all of them — pedagogy via consistency.

### I132. Donor concordance v2 — playable visual surface (WS-2)
**Origin:** Vision 2026-04-29 | **Priority:** Medium | **Owner:** web

Existing `/council/patterns` works on the data side but isn't *fun* — too analytical, not invitational. v2: include 2026 candidates in the concordance graph (not just sitting council); make the entry surface a click-to-light-up visual where selecting a donor reveals all their giving across candidates and PACs. Detail table below for the precision reader. **Design exploration territory** — surface 2-3 distinct visual directions before committing.

### I133. Cross-employer concordance ("X employees gave $Y across N candidates") (WS-2)
**Origin:** Vision 2026-04-29 | **Priority:** Medium | **Owner:** web

Aggregation by `donors.employer` across the candidate set. "Chevron employees gave $X across these 4 candidates." Surfaces patterns that single-donor analysis misses. Initial view: top 20 employers by aggregate dollars across all 2026 candidates. Drill-through to see which employees gave to whom.

### I134. PAC profile pages `/pac/[slug]` (WS-2). ✅ V1 SHIPPED 2026-04-29 (operator-only)
**Origin:** Vision 2026-04-29 | **Priority:** High (high-leverage from existing data) | **Owner:** web

Same template family as candidate page. Shows: who funds the PAC (incoming), who the PAC funds (outgoing), what they spend on (independent expenditures), temporal layer. Day-one inputs: the orphan-PAC list audit reveals East Bay Working Families ($2.05M), RPOA PAC ($1.08M), Coalition for Richmond's Future / Chevron-funded ($635K), 45+ others. All currently invisible to the public.

**V1 shipped 2026-04-29:** [`/pac`](web/src/app/pac/page.tsx) and [`/pac/[slug]`](web/src/app/pac/[slug]/page.tsx) routes wrapped in `<OperatorGate>`. 59 PAC profile pages prerendered initially; tightened to ~36 in V1.1 (see below). Surfaces incoming donors and cross-filing outgoing flows (PAC-as-donor on another committee's filing). Sponsor disclosure inferred from name prefix; explicit "Funded by Chevron Richmond" for Coalition for Richmond's Future.

**V1.1 taxonomy fix 2026-04-29:** Operator caught that V1 mixed true PACs (general-purpose committees, IE committees, ballot-measure committees) with candidate-controlled committees for non-current races (Beckles for Assembly, McLaughlin for Lt Gov, Andrew Butt 2020 mayor, etc.). FPPC distinguishes these clearly; "PAC" colloquially conflates them. Fix: tightened `getPACList()` filter from `official_id IS NULL` to `official_id IS NULL AND candidate_name IS NULL`. The 23 orphaned candidate-committees deserve their own surface, captured as I147.

**Deferred from V1:**
- Independent-expenditure detail table (CAL-ACCESS EXPN_CD) — bulk-imported `independent_expenditures` has up to 448x amendment dupes per row. See D46.
- Temporal sparkline — kept simple; will land with I140 once shared component exists.

**Graduation prerequisites:** Hand-vet sponsor disclosure prose for Tier-3 correctness (Chevron, RPOA, IAFF named sponsors). Spot-check outgoing-flows table for normalized-name collision noise. Then promote to public alongside the I129 menu rename.

### I135. Donor profile pages `/donor/[slug]` (WS-2)
**Origin:** Vision 2026-04-29 | **Priority:** Medium | **Owner:** web

For the actual people and entities who give. Most donors aren't interesting — but some give to many candidates over many years, and that pattern is genuinely worth surfacing. Page shows: total given (lifetime + this cycle), recipients table, temporal pattern, employer/address concordance with other donors at the same employer or address. Slug needs entity-resolution work (same person under variant spellings); MVP can use raw `donors.id` until resolution lands.

### I136. Independent-expenditure committee surfacing (WS-2)
**Origin:** Vision 2026-04-29 | **Priority:** Medium | **Owner:** web

Subset of PAC pages: committees that exist to spend on Richmond elections without being controlled by a candidate. Critical for capturing the actual influence shape (e.g., Chevron's "Coalition for Richmond's Future" affects Richmond races without being attached to any candidate). Render as separate top-level item under PACs OR a filter within the PAC index.

### V13. Sitting-council donor data verification — ✅ COMPLETE 2026-04-29 (WS-5)
**Origin:** Vision 2026-04-29 | **Owner:** netfile

The 2026-04-28→29 reconciliation work validated 8 active 2026 candidates against Form 460 Line 1. The two sitting council members NOT running for 2026 (Brown D1, Wilson D5) were validated 2026-04-29 in the V13 pass:

- **Brown $14,532** / sum-of-forms $14,532 — MATCH (4 filings, full 2024 cycle)
- **Wilson $49,822** / sum-of-forms $49,822 — MATCH (4 filings, full 2024 cycle; 2 misclassified 497s evicted from cache)
- **Zepeda $19,550 lifetime** / sum-of-forms $19,550 — MATCH (4 filings 2023-2026 incl. amendment pair handled correctly)
- All other sitting members already validated (Martinez, Robinson, Bana, Jimenez)

Side effect of V13: defensive validation added to `reconcile_paper_filings_to_forms` for malformed period dates (regex check before SQL substitution) — Vision OCR occasionally returns sentinel strings like `<UNKNOWN>` when fed a 497 PDF as a 460. The cache also evicts misclassified 497s rather than reconciling them.

The phrase "Leisa-proof" — after Leisa Johnson (JOURNAL Entry 54). Bar achieved: every sitting council member + active candidate now reconciles to the cent against their actual Form 460 cover Line 1, or has a documented OVER status (only Jimenez's $1,468 IAFF cross-filing).

Graduation prerequisites remaining: I127 (footer honesty), I128 (dynamic next-election nav), I129 (Contributions menu rename).

### I137. "Explore-then-detail" design grammar formalized (WS-1, WS-2, WS-3)
**Origin:** Vision 2026-04-29 | **Priority:** Medium (cross-cutting) | **Owner:** web

Document the pattern explicitly in `docs/design/` so future surfaces (vendor, PAC, donor profile) inherit it without re-inventing. Three layers: (1) playable top surface (graphic, KPIs, network); (2) optional expandable temporal layer (change over time, responsive to selection); (3) sortable detail table (the receipt, drill-throughs).

Reference implementation: `/council/voting-patterns` ([VotingPatternsDashboard.tsx](web/src/app/council/voting-patterns/VotingPatternsDashboard.tsx)). Naming this pattern is itself a design move. Once it's named, "make a [surface] page following Explore-then-detail" becomes an actionable instruction without re-litigating the structure.

**In-flight 2026-04-29:** PAC pages V2 will be the first three-layer implementation. Voting-patterns currently has only top + bottom; PAC profile pages add the temporal middle layer. See [docs/design/PAC-MATRIX-DESIGN.md](docs/design/PAC-MATRIX-DESIGN.md) for the concrete adaptation. Research synthesis landed at [docs/design/INTERACTIVE-DATA-VIZ.md](docs/design/INTERACTIVE-DATA-VIZ.md) (2026-04-29).

**Six structural moves codified (the template definition):**
1. One primary axis of exploration. Not three, not five.
2. Selection has immediate visible consequence. Plain-language context strip rewrites itself.
3. Filters are orthogonal to selection. Each layer combines.
4. Detail table is the receipt, not the headline.
5. Plain language all the way down.
6. **The cycle mirror.** A temporal layer keyed to election cycles, not calendar time, that mirrors the user's current selection from the explore layer above. Answers one question in plain language: "Is what I am looking at right now normal for this entity, or is this cycle unusual?" Cycles because cycles are the natural beat of civic money. Mirrors selection because an unanchored timeline is just a wallpaper. Off for voting-patterns (no meaningful "previous cycle" of the same vote); on by default for money pages.

### I138. Final-stretch coverage page (was "live election") (WS-4)
**Origin:** Vision 2026-04-29 (corrected from initial framing) | **Priority:** Medium | **Owner:** web

Originally framed as "live election day coverage." Corrected: 24-hour 497 filings cluster in the final 14 days before election, NOT on election day itself. Better framing: a `/elections/[slug]/final-stretch` page that's most active May 19 → June 1 for the 2026 primary, with appropriate framing throughout.

Components: countdown to next 24-hour reporting deadline; "since last quarterly" tally per candidate; chronological 497 feed; honest empty-day messaging ("no new $1,000+ contributions reported yesterday"). On election day itself: static "polls close at 8pm" header, final cumulative summary, last contribution received. The drama is the week before, not the day of.

### I139. Late-contribution feed integration into existing pages (WS-4)
**Origin:** Vision 2026-04-29 | **Priority:** Medium | **Owner:** web

Three nesting levels:
1. **Lightweight** — small "Recent contributions" rail on Contributions index page (5 items, click-through).
2. **Medium** — per-candidate badge: "Received $X in the last 7 days (3 contributions ≥$1,000)" with expand-to-see-list.
3. **Heavy** — dedicated final-stretch page (I138).

Show the *gap* between donor-side and recipient-side filings explicitly: "filed via 497 Part 2 — recipient's matching 497 not yet recorded." That's the analytical layer that single-direction contribution lists miss.

### I140. Donation temporal sparkline component (WS-4)
**Origin:** Vision 2026-04-29 | **Priority:** Low-Medium | **Owner:** web

Small per-candidate cumulative-$ chart with markers for filing deadlines. Drops into candidate cards, candidate detail pages, council profile pages. Reusable across surfaces where temporal context adds value to a single dollar number.

### I141. Donations × votes temporal alignment for council members (WS-4)
**Origin:** Vision 2026-04-29 | **Priority:** Medium | **Owner:** web

For sitting council members: an alignment view showing fundraising activity overlaid with their voting record. When did the donations come in relative to contested votes? This is scanner-adjacent — moves toward "did the donations follow the vote" without making the inference explicit.

### I142. Vendor profile pages `/vendor/[slug]` (WS-3)
**Origin:** Vision 2026-04-29 | **Priority:** High (foundational scanner work) | **Owner:** web + scanner

Mirror of candidate/PAC profile for entities receiving city money. Total received, top years, agenda items where the vendor appears (action items they benefit from), council members they donate to, votes those members cast on items affecting them. The fundamental scanner surface: city money OUT × campaign money IN, joined by entity.

### I143. "Donor → Vendor" matched-pairs index page (WS-3)
**Origin:** Vision 2026-04-29 | **Priority:** High (the headline surface) | **Owner:** web + scanner

Top-N ranked list of donor → vendor pairs (entities that both donate to candidates AND receive city money). Ranked by either dollar size or recency. The "X donated $Y to candidate Z whose council voted aye on $W contract for X" pattern made browsable. This is the page that makes the project's unique value visible in 30 seconds.

### D45. Vendor entity resolution backlog (WS-3 prerequisite)
**Origin:** Vision 2026-04-29 | **Priority:** High (blocking I142, I143) | **Owner:** scanner

Same entity-resolution problem as donor side, on the vendor side: "Chevron Corp" / "Chevron USA" / "Chevron Products Co" / "Chevron Richmond" appear as separate vendor variants in `socrata_expenditures`. Without resolution, vendor pages fragment and matched-pairs miss connections. Likely shares infrastructure with donor entity resolution (S26 in PARKING-LOT).

### D46. Skeleton audit — find other silent no-ops (WS-5)
**Origin:** Vision 2026-04-29, generalized from filing_period_briefing skeleton fix (commit a266f50) | **Priority:** Medium | **Owner:** pipeline

The `sync_filing_period_briefings` function returned `{records_new: 0, "note": "skeleton"}` for an unknown duration before being wired up 2026-04-29. No test caught it; no liveness expectation flagged it. The cascade ran "successfully" while doing nothing.

Sweep: grep `data_sync.py` and the rest of `src/` for functions matching the pattern "returns dict with records_new=0 and a 'note' field describing why." Each is a candidate silent failure. Audit each for whether it should be doing real work that's being silently skipped.

Bonus: add a liveness expectation that flags any enrichment whose latest `data_sync_log` row over the last 7 days returned `records_fetched=0` AND has a `note` field — that's the structural shape of "the pipeline calls this thing and it does nothing."

### D47. Test coverage sweep for "untested modules" — quality tools first (WS-5)
**Origin:** Vision 2026-04-29 | **Priority:** Medium | **Owner:** infrastructure

The `audit_committee_mapping.py` script had a column-name bug (`c.fppc_id` → `c.filer_id`) that errored on every run. It's in the SessionStart "untested modules" list along with 47 others.

Pattern: the modules that *check* data quality are themselves untested, so when a column gets renamed they silently break and stop providing the safety net they were built for. First sweep target: the audit/health/verify modules (`audit_committee_mapping`, `verify_donor_data`, `validate_rescan`, `validate_text_quality`, `decision_briefing`). Smoke tests for each that exercise the SQL against the live schema.

### I144. Filing-change alert subscriptions (WS-4)
**Origin:** Vision 2026-04-29 | **Priority:** Medium-High (mobilizes dormant subscriber list) | **Owner:** web + email

Email subscribers can opt in to per-candidate or per-PAC alerts: "notify me when a new filing changes [Jimenez's totals / IAFF Local 188's spending / Chevron-funded committees]." Triggered by the same auto-update cascade that powers the late-contribution feed (I139). Sends within ~17 min of NetFile publishing.

Also: an opt-in "Final stretch alerts" channel for the 90-day pre-election window — curated digest of all 24-hour 497 filings as they hit, ending at polls-close on election day.

The dormant email subscriber list (shipped earlier, currently unused per JOURNAL Entry 54) is the audience for this. Subscribers signed up to be told when Richmond Commons had something for them. The final stretch is exactly that moment.

### I145. Filing-change summaries — what actually changed (WS-4)
**Origin:** Vision 2026-04-29 | **Priority:** Medium | **Owner:** pipeline + web

When a new filing is ingested, generate a structured "what changed" summary:
- Form 460: "Q1 form filed. Total this period: $X. Largest contribution: $Y from Z. Top 3 industries: A, B, C. Reconciliation status: MATCH / OVER $W."
- Form 497: "$X late contribution from Y on date Z. Filed via [donor 497 Part 2 / recipient 497 Part 1]. Brings 7-day total to $W."

These summaries serve two surfaces:
1. **Alert content** (I144) — the subscriber email body.
2. **Page header / "what's new" rail** — passive readers see the same summary in context on the candidate or PAC page.

Generation runs in the same cascade as `filing_period_briefing_generation`. Persists to a `filing_change_summaries` table keyed by filing_id, with `is_current` semantics for filings that get amended.

Format: short paragraph, factual, no advocacy. Same voice as existing recap generators. Subject to the canonical-names rule (no phonetic misspellings) since the source data passes through donor name fields.

### I146. Daily digest alternative for low-volume periods (WS-4)
**Origin:** Vision 2026-04-29 | **Priority:** Low-Medium | **Owner:** email

Subscribers who don't want per-filing alerts (might be many, since most filings are routine) can opt for a daily digest. Single 6pm email summarizing all filings hit in the last 24 hours. During quiet weeks the email simply doesn't send (or sends a "no filings today" no-op). During the final stretch it becomes substantive.

This is the "appropriate cadence for the actual data shape" expression: alerts for the urgent, digest for the ambient, neither for the silent. Avoids the failure mode where a "live" channel fires constantly when there's nothing to say.

### I147. Non-current-race candidate committees surface (WS-2 follow-on)
**Origin:** PAC page taxonomy fix 2026-04-29 | **Priority:** Medium | **Owner:** web

The PAC pages V1 (I134) initially included **23 candidate-controlled committees** mistakenly listed as PACs because the filter was `committees WHERE official_id IS NULL`, which was too loose. The V1.1 fix tightened to `official_id IS NULL AND candidate_name IS NULL`, which is the FPPC-correct definition of a true PAC (general-purpose committee or IE committee, not controlled by any candidate).

But that left **23 orphaned committees with real money flowing through them** with no surface:

- **State-level campaigns funded by Richmond donors:** Jovanka Beckles for Assembly 2018 ($387K, 777 contribs), Beckles for State Senate 2024 ($330K), Gayle McLaughlin for Lt Gov 2018 ($85K). These are interesting because they show Richmond residents funding state-level progressive campaigns.
- **Prior-Richmond losers:** Andrew Butt for City Council ($62K), Shawn Dunning for Mayor 2022 ($54K), Demnlus Johnson III 2018 ($109K), Anderson 2020 ($82K). Historical Richmond races where the candidate isn't a current official.

Both categories deserve surfaces eventually but they don't belong on `/pac`.

Proposed paths:
- **Path A**: Fold into donor profile pages (I135). When you look at a Richmond donor's history, their giving to non-current Richmond races and to state-level campaigns naturally shows up. Don't build a dedicated page; let donor profiles handle it.
- **Path B**: Build `/elections/archive` surface listing prior-cycle Richmond candidate committees. Useful for people researching historical Richmond races that don't have official_id links.
- **Path C**: Build `/non-richmond-candidates` surface for state-level campaigns. Probably too narrow, since state campaigns aren't this site's focus.

Lean Path A. Donor profile pages will surface this organically when they ship.

### D48. Cycle-matching liveness expectation refinement (WS-5)
**Origin:** Vision 2026-04-29, recurring Willis flag | **Priority:** Low | **Owner:** candidate_discovery

The `candidacy_committee_cycle_matches` expectation flags Willis 2020 indefinitely because the no-year-suffix Willis committee genuinely spans 2020 + 2024 cycles, with `committees.election_id` anchored to 2024. Two paths: (a) refine the expectation SQL to compare committee's contribution date range to the candidacy's election year (a multi-cycle committee should pass if it has ANY contributions in the candidacy's cycle); or (b) add a `committees.spans_multiple_cycles` flag and exempt those from the check. Otherwise the SessionStart health report keeps flagging Willis on every session despite the page rendering correctly.

### D49. CAL-ACCESS independent_expenditures dedup. ✅ SHIPPED 2026-04-29
**Origin:** PAC profile pages V1 audit 2026-04-29 | **Owner:** calaccess

Pre-fix: `independent_expenditures` had 122,326 rows for Richmond with up to 504x amendment duplicates per group (mean 54x). EBWF's totals read $147M instead of the real ~$4M of IE spending. The table was unusable for any aggregation.

**Migration 102 shipped 2026-04-29:** dedup by `(committee_name, payee_name, amount, expenditure_date, support_or_oppose, candidate_name)`, keeping the row with the highest filing_id (most recent amendment supersedes earlier copies). Includes a sanity check that aborts the migration if post-count is outside [1500, 5000] range.

Pre/post:
- Total rows: 122,326 → 2,252 (98% reduction)
- Distinct unique expenditures: 2,252 (matches audit prediction exactly)
- EBWF total: now $4.12M across 728 distinct expenditures (real)
- Coalition for Richmond's Future / Chevron data: now $635K-ish (real)

V2 of the PAC profile page can now include "Where the money went, independent expenditures by item" as the third detail table per the original I134 vision.

### D50. ~~Self-assessment status enum mismatch~~. NOT A BUG, REMOVED 2026-04-29
Original entry claimed `self_assessment.py` queries `data_sync_log WHERE status = 'success'` but actual values are `'completed'`. Verified incorrect: production code in `system_health.py:896` correctly uses `status = 'completed'`. The `'success'` typo was in an ad-hoc inline test query I wrote during the anomaly investigation, not in production code. Striking the entry to avoid wasted work.

### D51. Meta-anomaly suppression when underlying anomalies have known dedup_keys (WS-5)
**Origin:** Anomaly investigation 2026-04-29 | **Priority:** Low | **Owner:** infrastructure

The 4/28 anomaly "Persistent anomaly count of 2 detected across all self-assessment entries" is meta-noise. The self-assessment runs every 3 hours and detects the SAME 2 underlying anomalies on every run. The persistent count is the symptom of the underlying anomalies, not an independent finding. When the underlying anomalies have known dedup_keys (which they do), the meta-anomaly should suppress.

Fix: in the meta-anomaly check, look up which specific anomalies are recurring. If all of them have entries already in pending_decisions (matched by dedup_key), suppress the meta-anomaly. If a NEW unknown anomaly is repeating, let the meta-anomaly fire (real signal).

### I148. Future-dated contribution row (data integrity)
**Origin:** DATA-FOUNDATION-AUDIT.md 2026-04-29 | **Priority:** Low | **Owner:** netfile

One row in `contributions` is dated 2107-12-12 ($100, donor Charlette Casey, recipient committee MC LAUGHLIN FOR LIEUTENANT GOVERNOR 2018; GAYLE, source city_clerk, filing_id 2211460). The source filing has a typo, almost certainly meant 2017-12-12 (which would put it in the active fundraising window for the Lt Gov 2018 campaign).

Two paths:
- **Path A**: Verify against the NetFile portal filing 2211460 and silently correct in DB if the source is unambiguous. Quick.
- **Path B**: Add a date-sanity-check enrichment that flags any contribution dated more than 5 years in the future and surfaces for operator review. More general fix that catches future occurrences.

Lean Path A for this row plus Path B for the enrichment. The enrichment is small and runs once at sync time.

### I149. Entity resolution magnitude (Richmond Police variant block)
**Origin:** DATA-FOUNDATION-AUDIT.md 2026-04-29 | **Priority:** High (input to S26 sizing) | **Owner:** scanner

Concrete case study for the S26 entity-resolution epic. The Richmond Police union payroll-deduction donor block is split across at least 7 employer-string variants totaling roughly $1.7M:

- "Richmond City Police": 57 donors, $969,058
- "Richmond, CA Police Department": 7,578 contribs, $298,983
- "Richmond, Ca Police Department": 4,626 contribs, $197,075
- "Richmond Police Department": 1, $1,000
- "City Of Richmond, Ca": 5,176 contribs, $123,306
- "City of Richmond, CA": 3,206 contribs, $82,525
- "City Of Richmond, CA": 8, $2,650
- "City of Richmond": 18, $2,415

If canonicalized under one entity (probably "City of Richmond" with department metadata), this would surface as a coherent ~1,700-donor block currently fragmented across capitalization, comma, and abbreviation variations.

This is the single largest visible entity-resolution payoff in the contributions data. Fixing it would also strengthen the scanner's employer-match signal because flagging a contribution from "Richmond Police" against an item involving the police department would consolidate signals currently spread across the variants.

S26 scope should include both donor-side resolution (this case) and committee-side resolution (the IAFF Local 188 word-reorder case from PAC pages V1.2). They share the same alias-table / fuzzy-match infrastructure.

### D53. PAC index jurisdictional verification (committee_id != Richmond CA filer). ✅ SHIPPED 2026-05-01
**Origin:** Operator audit 2026-05-01 | **Owner:** web

The `committees.city_fips` field has been silently misleading: it just means "ingested via the Richmond pipeline," not "registered with Richmond CA's NetFile agency." Cross-jurisdictional committees (Richmond District Democratic Club is an SF club; Northern CA Carpenters file with state agencies; Tony Thurmond is state-level superintendent; Bay Area Voter Education Project is region-wide) auto-create rows in our committees table when they appear as donors on Richmond filings. Until 2026-05-01 the `/pac` index page promised "Richmond political action committees" while including ~12 such non-Richmond entities.

**Shipped:** `web/src/data/netfile-richmond-filers.json` is the authoritative source-of-truth list of FPPC IDs registered with NetFile's Richmond CA agency 163 (48 IDs as of 2026-05-01, regenerated from `mcp__netfile__get_committee_info(city='Richmond')`). `getPACList` now filters via `isVerifiedRichmondFiler(filer_id)` which keeps committees with a registered FPPC ID, "Pending" (in registration), or null (no NetFile data); excludes filer_ids not in the registry.

**Open follow-up:** this should become a `verified_local_filer BOOLEAN` column on the committees table populated by a sync job, not a hardcoded JSON file. Tracked under WS-5.

### D54. Voting-patterns page anon-role timeout headroom (~1.8s)
**Origin:** Build-failure investigation 2026-05-01 | **Owner:** web

The anon role on Supabase has `statement_timeout = 3s`. The divergent-motions RPC (`get_divergent_motions_detail` with `p_official_ids` filter, post-migration 103) takes ~1.2s in raw SQL. That leaves ~1.8s of headroom for PostgREST serialization, network round-trip, and Next.js processing. From Vercel edge (close to Supabase region) this is comfortable. From slower or higher-latency networks (residential connections, builds run from outside the Vercel region), the round-trip alone can eat the headroom and tip the page over the timeout.

**Symptom:** local `next build` consistently fails on `/council/voting-patterns` with "canceling statement due to statement timeout" even though production loads cleanly. Earlier sessions dismissed this as "just slow local network." It's actually the page running with thin headroom — vulnerable to ANY latency increase, not just mine.

**Why this matters:** the page works in production today, but it's brittle. A future Supabase rebalancing, a CDN issue, or a slightly slower build environment could push production into the same failure mode my local hits. The fragility deserves a fix, not just a known-issue tag.

**Three potential fixes (operator decision):**
1. Optimize the SQL further so it's closer to 200-500ms (more headroom). Likely involves adding/refining indexes on `votes(motion_id, official_id)` and the contestedness re-evaluation step in the new RPC.
2. Bump anon `statement_timeout` to 8s (matching authenticated). Global change, affects every anon query — risky for unrelated regressions.
3. Switch `/council/voting-patterns` from prerender to runtime SSR with longer timeout. Loses static-export benefits but isolates the fragility to one page.

### D52. Orphan run cleanup automation (WS-5). ✅ SHIPPED 2026-04-29
**Origin:** Anomaly investigation 2026-04-29 | **Owner:** infrastructure

Initially captured because run 78b9a448 was stuck in `data_sync_log` with `status=running` for 12+ hours. Re-investigation 2026-04-29 found 61 such orphans across 17 sources (escribemeetings_minutes alone had 27 orphans across 4/21-4/26).

**Shipped:** `cleanup_stale_sync_logs()` function added to `db.py`. Auto-invoked from `create_sync_log()` so every sync startup cleans up orphan rows older than 1 hour. The 61 existing orphans were also cleaned up manually. Future orphans will self-heal.

**Open follow-up (I151):** the underlying cause of orphans (especially the 27 escribemeetings_minutes orphans) is process death before status update, but WHY those processes are dying needs separate investigation. Likely candidates: scraper timeouts, OOM kills, network errors that bypass the exception handler. The auto-cleanup keeps the briefing clean but doesn't fix the underlying instability.

### I150. Pre-merge dedup for entity-resolved donors (S26 follow-on)
**Origin:** duplicate_contributions investigation 2026-04-29 | **Priority:** Medium (recurs on every sync) | **Owner:** netfile + scanner

Same root cause as I149 (entity resolution): when a donor exists as multiple `donor_id` rows due to employer-string variants ("Ellen Pechman" with employers Emp. Consulting / self-employed / Luger Trust / Ellen Pechman), the sync's dedup logic keys on `donor_id` and treats each variant as a separate entity. Result: the same NetFile filing creates duplicate contribution rows, one per donor_id variant.

The 41 dups dropped 2026-04-29 are TRUE duplicates by all criteria (donor name, amount, date, filing_id) but the dedup at sync time can't see them as duplicates because of the donor-row fragmentation upstream.

Two-layer fix needed:
1. **Donor merging at sync time** (S26 territory): when ingesting a contribution, look up canonical donor by normalized_name and use that donor_id rather than creating a new row per employer variant.
2. **Pre-merge dedup at sync time**: if a fully-matching contribution row already exists (donor name, amount, date, filing_id) under any donor_id with the same normalized_name, skip insertion.

#1 is the proper fix and lives in S26. #2 is the pragmatic patch that prevents recurrence until S26 ships. Worth implementing #2 separately if S26 is more than a few weeks out.

### I152. Vote-explainer dollar accuracy (Path B SHIPPED 2026-04-29; Path A still open)
**Origin:** Liveness-check audit 2026-04-29 | **Priority:** Medium (user-facing content) | **Owner:** vote_explainer_generation

After improving the `vote_explainer_dollar_amounts_traceable_to_motion` check (added `plain_language_summary` to source columns plus a $1 rounding tolerance), failures dropped from 20 to 4. The 4 remaining categorize as:

**Genuine errors (2):** ✅ FIXED 2026-04-29 via Path B regen with literal-citation extra-instructions.
- 2026-03-03 STAX Engineering: was "$3.75 million over five years" (extrapolated from $750K × 5), now "$750,000 annually through 2029" (literal from summary).
- 2026-03-03 Intuitive Municipal Solutions: was "adding $200,000" (rounded from summary's $1.8M→$2M framing), now "adding $249,610" (literal from description).

**Borderline (2):** Still flagged. Path A required to address.
- 2026-03-03 Gordon Huether: explainer cites "$225,000" total. Source has two separate contracts ($175K + $50K = $225K). Mathematically valid derivation, helpful for residents.
- 2025-12-02 Lease Agreements: explainer rounds $95,232 (sum of three lease amounts) to "$95,000". 0.24% rounding, exceeds the $1 tolerance.

**Path A still open (operator decision):** tighten the system prompt to forbid arithmetic and extrapolation. Loses helpful context (the "$225K total" framing residents probably appreciate) but eliminates the overreach class. Prompt voice/framing change is a judgment call per `.claude/rules/judgment-boundaries.md`. Defer until more data on whether borderline cases bother readers.

**Infrastructure added:** `generate_vote_explainers.py` now accepts `--motion-id` (repeatable) and `--extra-instructions` flags. The extra-instructions text is appended to the system prompt for that run only, without modifying the persisted prompt file. Reusable for future targeted regenerations.

### I151. escribemeetings_minutes scraper instability (orphan-run pattern)
**Origin:** Orphan-run cleanup 2026-04-29 | **Priority:** Medium | **Owner:** infrastructure

D52's auto-cleanup hides the symptom (orphan rows) but the root cause is real: 27 escribemeetings_minutes runs across 4/21-4/26 died before writing completion. The pattern is one-per-day for 8 consecutive days, suggesting the daily cron is intermittently dying mid-run.

Likely candidates: PDF download timeout, OOM on large meeting packets, scraper exception that bypasses the try/finally that writes the completion record, GitHub Actions runner timeout that hard-kills the process.

Investigation steps: enable verbose logging for the escribemeetings_minutes scraper, add timing instrumentation around each meeting iteration, check whether the daily cron's GitHub Actions runs show timeouts in those windows. The auto-cleanup is sufficient to keep the briefing clean while we investigate.

### I154. Coalition Fidelity: position taxonomy + member-PAC alignment scoring (WS-6)
**Origin:** Operator vision 2026-04-30 | **Priority:** High (direct Representation value signal) | **Owner:** new — needs scoping sprint | **Promotes:** B.25 out of Someday

Operator concept: build a Richmond-specific position taxonomy, infer which positions each PAC holds (above a confidence threshold), infer which positions each agenda item touches, then for each council member compute and display alignment with the predicted preferences of the PACs that funded their election. The user need that finally justifies B.25 (`positions` table, sitting in Someday since S7 with "no clear user need yet").

Distinct from the adjacent alignment families already in the system:
- **I73 (B.61)** — resident-comment-vs-vote alignment. Same alignment mechanic, different signal source. Both ship; they answer different questions ("did the member vote with their funder coalition?" vs "did the member vote with the room?").
- **I141 (WS-4)** — donation × vote temporal alignment. Asks "did money come in around contested votes?" — a temporal signal. I154 is the categorical complement: "does the member vote consistently with their funders' positions?"
- **I132 / I133** — donor / employer concordance. Same WS-2 spine; positions sit on top of donor relationships.

**The four layers:**

1. **Position taxonomy.** Identify the live political positions in Richmond. Positions overlap; they are not mutually exclusive labels. Examples: `expand-tenant-protections`, `redirect-police-funding`, `preserve-port-revenue`, `expand-housing-supply`, `preserve-historic-character`, `cap-environmental-enforcement-fees`. Source-closest artifacts: PAC endorsement letters, IE expenditure messaging, member statements in transcripts, candidate questionnaires. Schema: `positions` (id, slug, title, description, evidence_summary), `position_evidence` (rows tying each position claim back to source documents).

2. **PAC-position mapping.** `pac_positions` (pac_id, position_id, polarity, confidence, evidence_count). Confidence comes from independent-signal corroboration (3 endorsement letters + 2 IE expenditures = high; one tweet = low). Initial seed manual or LLM-assisted from the existing committee endorsement corpus; updated as new endorsement filings arrive.

3. **Item-position mapping.** `agenda_item_positions` (item_id, position_id, polarity, confidence). Most items will be position-neutral (procedural, routine procurement); only assign positions when the item clearly touches one. Inputs: title, description, motion text, transcript discussion window, public comments. LLM-driven extraction with conservative confidence floor.

4. **Member-PAC alignment.** Computed view. For each council member, for each PAC that funded their election (NetFile already has this via `contributions` joined to `committees`), for each item where both a PAC predicted preference (PAC positions × item positions) and a member vote exist: did the member vote with the PAC's predicted preference? Display on member profile pages: per-PAC predicted-alignment record, with confidence per claim and the underlying votes one click away.

**Framing — judgment call territory.** This is alignment scoring; politically charged by nature. Required defaults:
- Graduated tier (operator-only until validated against operator-curated ground truth).
- Tier 3 disclosure mandatory: positions are inferred, not stated by PACs themselves. Every PAC-position assertion shows the evidence that produced it.
- Conservative confidence floor: false-positive alignment claims would damage credibility instantly and give detractors a clean attack surface.
- Narrative-over-numbers (per design rule D6): "Wilson voted with the police union's predicted preferences on 14 of 17 relevant items" beats "82% aligned" — the second invites context-stripping. The first carries its own context.
- Display surface: member profile first, PAC profile second. The PAC profile angle is interesting (RPOA's predicted-preference record across the council) but later.

**Stages (multi-sprint, each with its own publication-tier judgment):**
- **Stage 1: Position taxonomy seed.** Manual or LLM-assisted from existing endorsement corpus. Operator-curated. Operator-only review surface.
- **Stage 2: PAC-position inference + confidence scoring.** Backfill across known PACs. Operator-only.
- **Stage 3: Item-position inference.** Backfill via Batch API across historical agenda items. Operator-only.
- **Stage 4: Alignment computation + member profile display.** Graduated tier. Don't promote any layer to public until validated against ground truth.

**Adjacencies that benefit:**
- The structured 5-field vote_explainer rebuild (in flight 2026-04-30) can use PAC predicted preferences to populate the `the_other_side` field — "the police union and the housing-supply coalition were on opposite sides of this item; Wilson sided with the union" is more useful to a resident than a generic dissent stat.
- B.25 (`positions` schema in PARKING-LOT.md "Someday") is promoted by this entry. PARKING-LOT.md should be updated to reference I154 rather than "no clear user need yet."

## Session Notes (2026-05-01, Industry-Aligned Recusal Patterns)

### I155. Industry-aligned Levine Act recusal detection
**Origin:** Scanner-design note 2026-05-01 (citizen complaint cited Tier 4, underlying records Tier 1) | **Priority:** Medium | **Owner:** scanner

Current `signal_permit_donor` and `signal_license_donor` ([conflict_scanner.py](src/conflict_scanner.py)) fire when a donor's name or employer appears in agenda item text via `cached_name_in_text`. The Levine Act window check is wired in (`get_levine_act_threshold`, $250 pre-2025 / $500 post-SB-1243). Gap: a donor's *industry* — not their personal name — can give them the structural stake the statute targets. Concrete pattern that surfaced this gap: cannabis-industry donor (incumbent dispensary CEO) → council member → vote on a cannabis consent item that does not name them. The donor isn't an applicant; they're an *incumbent operator with a stake in regulating competitors*. Name-match misses it entirely.

Detection criteria:
- Donor entity tagged with industry I (depends on S26 entity resolution for industry classification of LLCs and FPPC-listed employers)
- Agenda item tagged with industry/topic I (we have topic labels; verify cannabis/dispensary item coverage)
- Contribution within the Levine Act window (already implemented)
- Official voted Aye or moved/seconded the motion

Confidence handling: lower than name-match by design. Surface as Tier 2 (Financial Connection), not Tier 1 (Potential Conflict), until corroborated. Industry-stake inference requires reader judgment — present the structural fact, don't assert intent.

Adjacencies: I154 (Coalition Fidelity) covers the alignment-over-time version. I155 is the Levine-Act-statute version: *single-item recusal* under §84308. Both ship; they answer different questions ("did the member systematically vote with their funders?" vs "should this specific Aye vote have been a recusal?"). Topic-domain expansion of I33/I34 (permit/license name quality) is the prerequisite work.

Dependencies: S26 entity resolution for donor industry classification. Topic tagging exists for items. No frontend work — extends `conflict_scanner` output through existing surfaces.

### I156. Donor-side "max-out coalition" signature
**Origin:** Scanner-design note 2026-05-01 | **Priority:** Medium | **Owner:** scanner + web

Pattern: same donor → multiple coalition members → identical (often cap-allowed) amount → across multiple cycles. Structurally distinct from relationship-based giving or from a single transactional donation. The detected shape is "fund the whole coalition at the cap, every cycle" — a strategy, not a relationship. Detectable from existing NetFile data; no new sync.

Detection (all from existing data):
- Group recipients into coalition clusters. Until I154 lands a position-based coalition definition, vote-correlation clusters are a fine proxy.
- For each donor, flag if they gave to N≥3 cluster members across C≥2 cycles at the same dollar amount.
- Surface in donor profile pages (I135 dependency) and PAC profile pages (I134 V1 already shipped) as a "Donor signature" callout: "Donor X has given $A to N members of {coalition} across C cycles. Same amount each time."

Confidence: this is descriptive arithmetic, not inference. The pattern is verifiable. The framing is the judgment call — when does it cross from "active participant" to "signature"? Initial threshold (N≥3, C≥2, identical amounts) is conservative; tune from data.

Adjacencies: I132 (donor concordance) shows who-gave-to-whom; I156 layers a temporal-pattern detector on top. I154 (Coalition Fidelity) measures the *vote-side* alignment downstream of this *donation-side* pattern.

### V8. Audit type-narrowing nullability divergences from Phase 2.5 sweep
**Origin:** Phase 2.5 sweep 2026-05-11 | **Priority:** Low | **Owner:** web

The Phase 2.5 type-anchoring sweep preserved several hand-rolled non-null narrowings on columns the generator reports as nullable. These are fine *if* the DB constraint or query filter actually guarantees non-null. They're a runtime crash waiting to happen *if* the assumption is wrong. Each is flagged at the override site in `web/src/lib/types.ts`. Audit by querying the live DB:

- `EmailSubscriber.metadata` — narrowed to `Record<string, unknown>` non-null; generator says `Json | null`
- `NeighborhoodCouncil.created_at`, `updated_at` — narrowed non-null
- `Motion.source`, `Vote.source` — narrowed `'minutes' | 'transcript'` non-null; comment claims queries filter `source IS NOT NULL` but that's not guaranteed at the type level
- `PendingDecision.evidence` — narrowed `Record<string, unknown>` non-null

For each: query `SELECT COUNT(*) WHERE col IS NULL` against production. If zero, add a NOT NULL constraint via migration and the override stays honest. If non-zero, drop the override (let the type be nullable) and add null-handling at callsites. AI-delegable — one query + one decision per column.

### D8. Vercel build fragility — Supabase statement_timeout under prerender concurrency
**Origin:** Vercel deploy failures 2026-05-12 → 2026-05-13 | **Priority:** Medium | **Owner:** web + db

Recurring production-deploy failures, all the same shape: 3 Vercel build workers prerendering ~54 pages in parallel, all hammering Supabase for heavy multi-table joins. Postgres anon role has a statement_timeout that's tight enough to cancel the slowest worker, Next.js retries 3x, then fails the page → build fails. Pages hit so far: `/council/patterns` (Phase 2.6 redirected this away), `/financial-connections` and `/influence` (Phase 2.6 follow-up `3ecf8c9` marked them `force-dynamic`).

Current workaround pattern: any page that calls `getAllFinancialConnectionSummaries`, `get_coalition_data`, `get_divergent_motions_detail`, or `getCrossMeetingPatterns` → mark page `force-dynamic`. The list will grow with new heavy joins.

Proper fix paths:
- **Phase 2.10 (re-architecture plan):** sidecar `*_embeddings` tables stop bleeding ~6KB of vector per row into list queries; removes the embedding cost from joins that don't need it.
- **RPC tuning:** `get_coalition_data` and `get_divergent_motions_detail` are the dominant timeout victims. Indexes + query rewrite may bring them under the anon budget.
- **Lift the anon statement_timeout** (Supabase dashboard, role-level). Simplest if Supabase config allows; doesn't fix the actual perf problem.
- **Reduce Vercel build concurrency to 1 worker** (`NEXT_BUILD_WORKERS=1` env var or config). Eliminates contention; lengthens build wall time considerably.

Detection: `.github/workflows/build-check.yml` runs `next build` on every PR and push to main, against the real Supabase database, with retry-once to absorb the probabilistic timeout class without masking real bugs. This catches the failure surface that local `next build` can't (missing env, different network path) and the failure surface that `tsc --noEmit` doesn't see (runtime queries). The retry layer is a band-aid; the structural fixes above are still pending.

### R18. Cross-jurisdictional advocacy detection
**Origin:** Scanner-design note 2026-05-01 | **Priority:** Low (parking; out of immediate scope)

Pattern: officials lobbying neighboring jurisdictions on items affecting their funder coalition. Example claim from the same complaint: Richmond council member emailing a neighboring city's councilmembers about a dispensary approval. Not detectable from in-jurisdiction data alone — would require outbound CPRA email scrapes (we have NextRequest infrastructure but it's inbound-only), regional coalition meeting minutes (don't exist), or social-media monitoring (out of scope).

Multi-city scaling unlocks this naturally. If Richmond Commons covers a regional cluster (Bay Area cities), an official's email *to* San Pablo council becomes visible *as inbound* on the San Pablo side. Cross-city as a feature would surface cross-jurisdictional advocacy without new data sources — just FIPS-stratified mention detection across the union of agenda/transcript/correspondence datasets.

Don't build now. Note for multi-city architecture: officials already key by FIPS; a "cross-FIPS-mention" detector running on the union of inbound channels across configured cities would catch this when the city neighbor is also on the platform. Park as a Phase 4 multi-city consideration.

### D55. Build Check workflow on main fails at "Verify required secrets" — DIAGNOSED 2026-05-17, AWAITING OPERATOR ACTION
**Origin:** Surfaced by T0.5 risk-summary on first run, 2026-05-16 | **Priority:** Medium (blocking nothing, but reads as RED on every health check) | **Owner:** operator (cannot be AI-delegated)

**Diagnosis complete:** `gh run view 25976325357 --log-failed` shows the missing secret is `NEXT_PUBLIC_SUPABASE_ANON_KEY`. Confirmed via `gh secret list` — `SUPABASE_URL`, `SUPABASE_SERVICE_KEY`, and other Supabase-related secrets are set, but `NEXT_PUBLIC_SUPABASE_ANON_KEY` was never added when the workflow landed in 6b46246. The build-check has been red since the day it was first added (2026-05-13).

The workflow's "Verify required secrets" step correctly catches this — that's its job. The fix is operational, not code-level.

**Operator action (90 seconds, cannot be AI-delegated):**

1. Open https://vercel.com/dashboard → Richmond project → Settings → Environment Variables
2. Copy the value of `NEXT_PUBLIC_SUPABASE_ANON_KEY` (JWT starting with `eyJ...`)
3. Run locally:
   ```
   gh secret set NEXT_PUBLIC_SUPABASE_ANON_KEY -b '<paste-the-jwt>'
   ```
   Or via web UI: https://github.com/pjfront/richmond-common/settings/secrets/actions/new

Why this is not AI-delegable:
- I cannot retrieve the value from Vercel (no MCP access)
- I cannot retrieve it from the Supabase MCP (`get_publishable_keys` denied)
- The value is not in local `.env` either
- I could in principle run `gh secret set` once I had the value, but the value itself requires operator-level access to Vercel

The anon key is technically public (it's already in every client bundle in production), so there's no security risk in handling it — just no automated way to get it without the operator's hand on it.

**Improvement landed 2026-05-17:** The workflow's error message now includes the exact `gh secret set` command and the Vercel URL where to find the value — next time anyone sees the failure (or if the secret is rotated), the fix is one copy-paste from the error log.

**Why this matters for the audit theme:** the build-check workflow was added (6b46246) to catch Vercel build failures pre-merge. It's been red on main since the day it was added because no one looked at it. The risk-summary refactor (T0.5) immediately surfaced it. This is the loop the audit is meant to close — instrumentation that catches drift even when nobody asks. Once the operator sets the secret, this row will clear from SessionStart.

---

## Session Notes (2026-05-17, Architectural fix for the stale-P0 noise)

The SessionStart brief opened with "3 P0 'Assessment finding: failure' rows" all citing the same `_normalize_name` NameError. Investigation showed:
- **The runtime bug was fixed 36 hours earlier** in commit `234868c` (db/contributions Phase 2.1 split-orphan).
- **Both netfile AND calaccess had successfully run since** (last_success > last_failure for both sources).
- **The P0 rows existed because the self-assessor re-generates them daily** from journal history, which still contains the old `run_failed` entries (the journal is append-only by design).

Two architectural fixes landed in this session:

### D58. AST coverage extended from db/ to all src/ subpackages — RESOLVED 2026-05-17
**Origin:** Discovered during 2026-05-17 audit follow-up | **Owner:** tests

The existing `tests/test_db_module_name_resolution.py` (added 2026-05-15 by commit 234868c) only scans `src/db/*.py`. The same split-orphan bug class can recur in any package split. Extended coverage:
- Extracted AST helpers to `tests/_ast_name_resolution.py` (shared between two test files).
- Added `tests/test_package_module_name_resolution.py` scanning `src/pipelines/` (10 modules) and `src/scanner/signals/` (10 modules) — 22 parametrized cases total.
- Walker is now closure-aware (handles nested functions like `process_row` inside `sync_socrata_permits` that close over `city_fips` from the outer scope).

**The test paid for itself immediately:** the first run surfaced TWO REAL bugs of the same class, both from the 2026-04 Phase 2.3 split:
1. `src/pipelines/enrichments.py:498` — `sync_embedding_generation` called `os.getenv("OPENAI_API_KEY")` without importing `os`. This was the actual cause of "embedding_generation failed: name 'os' is not defined" in the daily journal — the operator had been seeing it as a "P2 Assessment finding" for weeks without anyone tracing the root cause. Fix: one line, `import os`.
2. `src/pipelines/escribemeetings.py:391` — `_is_minutes_content` referenced `_MINUTES_MARKERS` constant. The constant was misplaced in `src/pipelines/form700.py:211` (unused there) during the Phase 2.3 split. Fix: move the constant back to where the consumer lives.

### D59. Self-assessor now filters resolved failures at context-build time — RESOLVED 2026-05-17
**Origin:** 2026-05-17 audit | **Owner:** self_assessment | **Related:** D42 (which it partially mitigates)

`src/self_assessment.py::_filter_resolved_failures` — new helper called from `build_assessment_context`. Rule: a `run_failed` entry for source X is suppressed from the LLM's input if there's any `run_completed` for source X with a later timestamp in the same entry list.

Per-source granularity matters because the netfile/calaccess case had the same root cause but different recovery times. Non-failure entries (assessment, anomaly, step_completed) pass through unchanged. Failures without source metadata are conservatively kept.

9 unit tests in `tests/test_self_assessment.py::TestFilterResolvedFailures` lock down the contract, including the load-bearing 2026-05-15 netfile/calaccess recovery scenario.

This is upstream of D42 (which is about dedup_key shape): if the LLM never sees the resolved failure, it can't generate a finding about it — so dedup_key shape doesn't matter for this case. D42 is still relevant for findings without a structural recovery signal (perf regressions, coverage warnings, missing env vars that won't recover until the operator acts).

**Stale rows cleanup:** The 3 pre-existing P0 rows (`fe61ba07`, `8442137b`, `50f30612`) were resolved via direct SQL with note: "Resolved by recovery-filter fix; netfile last_success > last_failure, calaccess last_success > last_failure. Future assessor runs are gated by `_filter_resolved_failures` so the same stale rows cannot recur."

**Test count:** suite grew from 2,225 to 2,256 passing (31 new tests: 22 AST coverage parametrizations + 9 recovery filter assertions). 0 failures, 33 skipped (opt-in DB tests).

### D60. `community_comments` half-shipped feature — PARTIALLY RESOLVED 2026-05-18 (gated to operator; graduation pending operator review)
**Origin:** Anon-visibility gap shrink (D56b follow-through) | **Severity:** medium (was: feature broken in public view; now: gated, awaiting graduation) | **Owner:** community_voice / S21 graduation

**Found by:** the new `tests/test_anon_visibility_coverage.py` flagging `community_comments` as a queries.ts `.from()` target that wasn't covered by `PUBLIC_TABLES`. Probing as anon (`SET LOCAL ROLE anon; SELECT ... FROM public.community_comments`) returned `relation "public.community_comments" does not exist`. **This is exactly the kind of bug the coverage test was built to surface.**

**Investigation (the rename hypothesis was wrong):**
- "Community Voice" was the S21 codename for the THEME TAGGING features (`comment_themes`, `comment_theme_assignments`, `item_theme_narratives`) — those were created by `src/migrations/068_community_voice.sql` and `069_community_voice_rls.sql`, applied to prod 2026-03-28 / 2026-04-03.
- `community_comments` is an ENTIRELY DIFFERENT feature: user-submitted comments with clerk-submission tracking. Added 2026-03-28 by commit `9341fc1` ("Phase 2: add community comment submission for public record") as `src/migrations/068_community_comments.sql`, alongside `CommunityCommentSection`, the API route, and queries wiring.
- The migration was numbered 068 at a time another 068 was already in `supabase/migrations/` — they collided in `src/migrations/`. Commit `c7b0bd4` (2026-05-11) renumbered `068_community_comments` → `108_community_comments` to resolve the collision after the migration-discipline test was added.
- **But the supabase/migrations/ mirror for community_comments was never created.** Production never received the table. The frontend has been wiring a doomed call for ~7 weeks.

**Why the UX was broken in public view (until this session's fix):**
- `CommunityCommentSection` was rendered unconditionally on every `/meetings/[id]/items/[itemNumber]` page.
- `getCommunityComments` (anon SELECT against the missing table) returned `[]` silently — citizens saw "no comments yet" with a working-looking form.
- `POST /api/community-comments` had NO operator auth wrap — anyone could submit. The INSERT would 500 ("relation does not exist"). Citizens who tried to leave a comment got an error.
- The disclosure copy said "Comments are submitted to the Richmond City Clerk before the meeting" — a fairly weighty claim attached to a broken pipeline.

**Fix shipped this session (gate, not graduate — the conservative AI-delegable move):**
- `web/src/app/meetings/[id]/items/[itemNumber]/page.tsx`: removed the `getCommunityComments` import + call. The section is now wrapped in `<OperatorGate>`. `initialComments={[]}` is passed (the section still mounts for operators but starts empty).
- `web/src/app/api/community-comments/route.ts`: POST handler is now wrapped with `withOperatorAuth`. Defense in depth so non-operators can't submit even by crafting a direct POST.
- `tests/test_anon_visibility_coverage.py`: `community_comments` moved from `KNOWN_COVERAGE_GAPS` to `EXEMPT` with a detailed reason. `KNOWN_COVERAGE_GAPS` is now empty (no untriaged gaps).
- The migration was NOT shipped to production — that's a graduation decision, not a containment fix.

**Operator decisions remaining (genuinely judgment, not AI-delegable):**
1. **Is community comments meant to graduate?** S21 was marked done with graduation pending. If yes:
   - Mirror migration 108 to `supabase/migrations/YYYYMMDDHHMMSS_community_comments.sql` (timestamped) and `supabase db push`.
   - Decide moderation flow: migration 108 currently has `status DEFAULT 'published'` — submissions auto-publish. If graduation requires moderation, this needs a pre-ship change.
   - Decide clerk-submission flow: `clerk_submission_batches` table exists in the migration but no submission automation. Manual batches? Cron? Each agenda item's deadline?
   - Remove the `OperatorGate` wrapper + `withOperatorAuth` after the ship is verified.
2. **Or is community comments deferred indefinitely?** The gate is appropriate for "deferred" — defense in depth keeps it from leaking out via a stray code path. Leave as-is; revisit when bandwidth permits.

**Why the test caught this and the system didn't:** the migration discipline test (`tests/test_migration_discipline.py`) checks src/migrations/ for collisions, but does NOT check that every src/migrations/ file has a supabase/migrations/ mirror. That's the next enforcement gap — surfaced for parking-lot consideration (D61).

### D61. No test enforces that every src/migrations/ entry has a supabase/migrations/ mirror — PROPOSED 2026-05-18
**Origin:** D60 root-cause analysis | **Severity:** low (no current loss; but D60's 7-week silent breakage was enabled by this gap) | **Owner:** migration_discipline test family

The project rule (`.claude/rules/conventions.md`):
> Don't apply migrations to live Supabase without committing the SQL file in the same change. Non-negotiable.

Implicit corollary: every committed `src/migrations/NNN_*.sql` must have a corresponding `supabase/migrations/TIMESTAMP_*.sql` mirror. Without the mirror, `supabase db push` skips the migration entirely — production never receives the schema change, but `src/migrations/` looks like the change shipped.

`tests/test_migration_discipline.py` enforces numeric-prefix uniqueness + filename shape but does NOT enforce mirroring. The D60 finding is the canonical example of the bug shape this would catch.

**Proposed test shape** (one function in `tests/test_migration_discipline.py`):
```python
def test_every_src_migration_has_supabase_mirror():
    """For each src/migrations/NNN_*.sql, assert a matching SQL file
    exists in supabase/migrations/ whose name suffix matches.

    A new src/migrations/ file without a mirror is the D60 shape: the
    SQL is in the repo, the frontend may already be wired, but
    `supabase db push` skips it and production never gets the table.
    """
```

Subtlety: some pre-mirror-discipline migrations may legitimately lack mirrors (early-project schema applied manually). Initial population would include an `allowed_unmirrored` set (similar to `allowed_grandfathered` in `test_d1_provenance.py`) that locks the current state and prevents new gaps. **AI-delegable to implement.** Operator decision: defer or do now? Doing now would have caught D60 at PR review time on 2026-03-28, saving 7 weeks of broken UX.
