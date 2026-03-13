# AI Parking Lot

_Ideas, research topics, and improvement suggestions captured by the AI during implementation sessions. AI has full autonomy over this file. Periodically reviewed and prioritized with the operator for integration into the roadmap._

_Convention: Every session adds observations here. Items stay until promoted to the sprint backlog or explicitly discarded during a review._

---

## Research Topics

### R1. Entity Extraction for Civic Text ➜ Promoted to S9.5
**Origin:** S9.3 (2026-03-10) | **Promoted:** 2026-03-11 to S9.5 pre-rescan cleanup

`extract_entity_names()` returns noisy phrases ("Approve contract with Acme Corp") instead of clean entity names ("Acme Corp"). This causes `names_match()` failures in the donor-vendor detector when entities aren't pre-extracted.

**Recommended approach:** Gazetteer-based matching. Use `city_expenditures.normalized_vendor` as a clean entity list and match vendor names directly against item text with `name_in_text()`, bypassing entity extraction entirely. Inverts the lookup direction. Lowest cost, highest impact.

**Alternative approaches:** NER via spaCy, LLM-based extraction (expensive), regex improvements.

### R2. Expenditure Data Quality Profile ➜ Promoted to S9.5
**Origin:** S9.3 (2026-03-10) | **Promoted:** 2026-03-11 to S9.5 (pre-check for R1/I1)

Unknown: how clean is `city_expenditures.normalized_vendor`? Vendor normalization quality directly affects false positive/negative rates.

**Questions to answer:**
- How many unique normalized_vendor values exist?
- Vendor name length distribution (short names = false positive risk)
- Obvious normalization issues ("ACME CORP" vs "Acme Corporation" as separate vendors)?
- Percentage of single-transaction vendors (low-frequency = lower signal)

**How to check:** Supabase query on `city_expenditures` for vendor distribution stats.

### R3. Per-Signal vs. Group Confidence Display ➜ ✅ Done in S9.6
**Origin:** S9.3 (2026-03-10) | **Promoted:** 2026-03-11 to S9.6 | **Completed:** 2026-03-12

Implemented as factor breakdown display in expandable rows. Shows Name Match, Time Proximity, Financial Materiality, and Statistical Anomaly as colored progress bars alongside signal count and corroboration boost.

---

## Improvement Suggestions

### I1. Gazetteer-Based Vendor Matching in Scan Loop ➜ Promoted to S9.5
**Origin:** S9.3 (2026-03-10) | **Promoted:** 2026-03-11 to S9.5 pre-rescan cleanup

Instead of `extract_entity_names()` -> match against vendors, match the vendor list directly against item text using `name_in_text()`. Catches "Acme Corp" in "Approve contract with Acme Corp" where entity extraction fails. Direct implementation of R1's recommended approach.

### I2. Expenditure Amount as Financial Amount Enrichment
**Origin:** S9.3 (2026-03-10) | **Priority estimate:** Low

When a vendor matches an agenda item, the expenditure amount could supplement the item's `financial_amount` field (often empty for non-consent items). Would improve financial_factor scoring for items that don't have explicit dollar amounts.

### I3. Vendor-Official Voting Pattern Detection
**Origin:** S9.3 (2026-03-10) | **Priority estimate:** Low (coalition-level, future sprint)

Track whether officials consistently vote Aye on items involving their donors' vendors. This is a coalition-level pattern, not a single-flag signal. Extends beyond current per-item conflict detection into longitudinal behavioral analysis.

### I4. Scan Results Sorted/Grouped by Agenda Item ➜ ✅ Done in S9.6
**Origin:** S9.5 discussion (2026-03-11) | **Promoted:** 2026-03-11 to S9.6 | **Completed:** 2026-03-12

Implemented as "Group by item" toggle in `FinancialConnectionsAllTable`. When enabled, rows are grouped by agenda item with headers showing item number, title, date, and signal count badge (e.g., "3 signals"). Makes corroboration visually obvious. CLI output grouping deferred to future work.

### I5. CAL-ACCESS Independent Expenditure Parsing ➜ Promoted to S9.5
**Origin:** S9.5 discussion (2026-03-11) | **Promoted:** 2026-03-11 to S9.5 (pre-rescan, new signal source)

`calaccess_client.py` already downloads the 1.5GB bulk ZIP and parses `RCPT_CD` (contributions). `EXPN_CD` (expenditures) is documented but not yet parsed. IE data connects PACs (e.g., Chevron's "Coalition for Richmond's Future") to the specific candidates they supported or opposed. This is the missing link between corporate PAC money and council members. Same parsing pattern as `get_richmond_contributions()` but reading `EXPN_CD` instead of `RCPT_CD`.

### I6. Automated Data Quality Regression Suite ➜ Promoted to S10 ✅ Complete
**Origin:** Data quality audit (2026-03-11) | **Promoted:** 2026-03-11 to S10 (alongside search infrastructure) | **Completed:** 2026-03-13

Implemented as S10.4. 9 SQL-based checks in `src/data_quality_checks.py`, dual GitHub Actions integration (standalone daily cron + post-pipeline step), decision queue alerting, canonical `TIER_THRESHOLDS` constants. 33 tests.

### I7. Dual `extract_financial_amount` Consolidation
**Origin:** Data quality audit (2026-03-11) | **Priority estimate:** Low

Two independent `extract_financial_amount` functions exist: one in `escribemeetings_to_agenda.py` (eSCRIBE path) and one in `run_pipeline.py` (minutes path). The eSCRIBE version had the $8 million bug; the minutes version was correct. Both now work, but having two copies of the same logic is a maintenance risk. Consider extracting to a shared utility (e.g., `src/text_utils.py`) so fixes apply everywhere. Low priority because both are now correct and tested.

---

## Technical Debt / Cleanup

### D1. Temporal Correlation Dual Existence ➜ Promoted to S9.5
**Origin:** S9.3 (2026-03-10) | **Promoted:** 2026-03-11 to S9.5 pre-rescan cleanup

Both `scan_temporal_correlations()` (standalone, returns ConflictFlag) and `signal_temporal_correlation()` (integrated, returns RawSignal) exist. Cloud pipeline calls both paths, risking double-counted temporal flags.

**Resolution:** Remove the separate Step 5b call in `cloud_pipeline.py` and rely on the integrated detector. The integrated version participates in corroboration, which is the whole point. Was targeted for S9.4, but S9.4 turned out to be purely the expenditure wiring. Clean up during S9.5 batch rescan when the cloud pipeline path gets exercised.

### D3. eSCRIBE Scraper Missing `.AgendaItemCounter` Fragility
**Origin:** Data quality audit (2026-03-11) | **Priority estimate:** Low

Closed session items lack the `.AgendaItemCounter` CSS class, so `item_number` stays empty. The fallback regex extraction (added in this session) handles the `C.1`, `C.2.a` pattern, but the scraper's reliance on specific CSS classes means any HTML structure change could silently break extraction. The broader pattern: eSCRIBE HTML is not a stable API. The self-healing selector approach used in the NextRequest scraper could be adapted here.

### D4. Migration FK Cascade Checklist
**Origin:** Migration 028 runtime failures (2026-03-11) | **Priority estimate:** Process improvement

Migration 028 failed twice in production: first missing `conflict_flags` cleanup, then missing `public_comments` cleanup before deleting `agenda_items`. The April 15 section of the *same migration* handled cascades correctly by manually listing all child tables. The Dec 2 section used a targeted subquery and missed two of three FK dependents.

**Process fix:** Any future migration that DELETEs parent rows should start by querying `information_schema.table_constraints` for all FK references to the target table, then delete from all child tables first. This query should be run *before writing the migration*, not after it fails. Consider adding a comment template at the top of migration files as a reminder.

### D2. DB Mode Fetch Pattern Could Use a Shared Helper
**Origin:** S9.4 (2026-03-10) | **Priority estimate:** Low

The four `_fetch_*_from_db()` functions follow the same pattern: execute query, map rows to dicts. A shared `_fetch_rows(conn, query, params, row_mapper)` helper could reduce the boilerplate, but the current approach is clear and each function has slightly different NULL handling. Not worth abstracting unless we add more fetch functions.

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

### D6. Supabase Client Eager Initialization Blocks Local Dev
**Origin:** S10.3 verification (2026-03-13) | **Priority:** Low

`web/src/lib/supabase.ts` creates the Supabase client at module level and throws if env vars are missing. Since every page imports `queries.ts` → `supabase.ts`, no page can SSR locally without `NEXT_PUBLIC_SUPABASE_URL` and `NEXT_PUBLIC_SUPABASE_ANON_KEY`. This blocks local preview verification for all frontend work.

**Fix:** Lazy client pattern — create the client on first use rather than at import time. Return `null` or a stub when env vars are missing, and let individual queries handle the missing client gracefully. This would allow pages to render locally (with empty data) for layout/component verification. Low priority because Vercel handles this in production and TypeScript catches type errors statically.
