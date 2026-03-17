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

### I5. CAL-ACCESS Independent Expenditure Parsing ➜ ✅ Complete
**Origin:** S9.5 discussion (2026-03-11) | **Promoted:** 2026-03-11 to S9.5 | **Completed:** 2026-03-13

Extraction (`get_richmond_expenditures`), DB schema (migration 029), and loading (`load_expenditures_to_db`) were already built. Final step: wired expenditure parsing into `sync_calaccess()` in `data_sync.py` so the monthly sync now processes both RCPT_CD (contributions) and EXPN_CD (independent expenditures) in a single pass. Return stats include `expenditures_fetched` and `expenditures_loaded`.

### I6. Automated Data Quality Regression Suite ➜ Promoted to S10 ✅ Complete
**Origin:** Data quality audit (2026-03-11) | **Promoted:** 2026-03-11 to S10 (alongside search infrastructure) | **Completed:** 2026-03-13

Implemented as S10.4. 9 SQL-based checks in `src/data_quality_checks.py`, dual GitHub Actions integration (standalone daily cron + post-pipeline step), decision queue alerting, canonical `TIER_THRESHOLDS` constants. 33 tests.

### I7. Dual `extract_financial_amount` Consolidation ➜ ✅ Fixed
**Origin:** Data quality audit (2026-03-11) | **Fixed:** 2026-03-13

Extracted to `src/text_utils.py` (canonical version with billion support). Both `escribemeetings_to_agenda.py` and `run_pipeline.py` now re-export from the shared module. Bonus: `run_pipeline.py` gains billion-dollar pattern matching it previously lacked.

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

### I11. Dedicated Project Email Before Public Launch
**Origin:** H.12 session (2026-03-15) | **Priority estimate:** Low (pre-launch hygiene)

About page currently uses personal email (pjfront@gmail.com). Before public launch, consider setting up a dedicated project email (e.g., richmondcommon@gmail.com) with auto-forwarding. Separates public-facing contact from personal inbox, looks more professional, and allows future team members to share access without sharing personal credentials. Gmail alias with forwarding is zero-cost.

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
**Origin:** S10.3 verification (2026-03-13) | **Fixed:** 2026-03-13

Replaced eager module-level `createClient()` with a Proxy that defers initialization to first use. `import { supabase } from './supabase'` no longer throws — the error only fires when `supabase.from()` is called. Zero changes to 53 call sites in queries.ts or 6 API routes. Module evaluation chain eliminated (call stack dropped from 50 to 22 frames).

### D7. Tier Threshold Single Source of Truth ➜ ✅ Fixed
**Origin:** S10.4 implementation (2026-03-13) | **Fixed:** 2026-03-13

Added `TIER_THRESHOLDS_BY_NUMBER` to `conflict_scanner.py` (derived from `V3_TIER_THRESHOLDS`). Both `batch_scan.py` and `data_quality_checks.py` now import from the scanner instead of defining their own copies. **Found a real bug:** `data_quality_checks.py` had stale v2 values (0.6/0.4/0.0) instead of v3 values (0.85/0.70/0.50). The tier sync quality check was comparing against wrong thresholds. Fixed tests to assert against scanner canonical values.

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
**Origin:** S7.4 completion (2026-03-13) | **Done:** 2026-03-13

Added second cron (`0 12 * * 5` — Friday noon UTC) to `self-assessment.yml` with `--days 7`. Uses `github.event.schedule` to distinguish Friday runs from daily runs. Also added `--create-decisions` to all runs so findings go to the decision queue.

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

### D9. `convert_escribemeetings_to_scanner_format` Missed Header Skip
**Origin:** B.49 (2026-03-13) | **Status:** ✅ Fixed

`escribemeetings_to_agenda.py:127` had the `"." not in item_num` skip for section headers, but `run_pipeline.py`'s `convert_escribemeetings_to_scanner_format()` — which the cloud pipeline actually uses — did not. Classic "two code paths doing the same thing differently" bug. Root cause of 77+48 uninformative scanner flags on "CITY COUNCIL CONSENT CALENDAR" and "CLOSED SESSION".

### D10. `temporal_flags` NameError in Cloud Pipeline Journal Log
**Origin:** B.49 session (2026-03-13) | **Status:** ✅ Fixed

`cloud_pipeline.py:593` referenced `temporal_flags` variable that was removed during S9.5 D1 cleanup (dual temporal correlation path removal). The journal log tried to `len(temporal_flags)` on a variable that no longer existed. Pipeline would crash at the journal log step after completing all substantive work. Found because the cloud pipeline test finally hit the code path.

### I21. Consent Block Vote Only Attached to First Sub-Item ➜ ✅ Fixed
**Origin:** B.49 (2026-03-13) | **Fixed:** 2026-03-13

Fixed by attaching the consent block vote (motion + individual votes) to ALL non-pulled consent items, not just the first. The block vote genuinely applies to every item that wasn't pulled for separate consideration. Pulled items are excluded (they get their own motion from the action items section). Bare-letter headers are also excluded. Migration 033 backfills existing data. 3 new tests.

### I22. Minutes Extraction May Produce Bare-Letter Item Numbers
**Origin:** B.49 (2026-03-13) | **Priority:** Low

The scanner's bare-letter header skip uses `^[A-Z]+$` regex. Minutes extraction from Archive Center PDFs uses LLM extraction, which might produce item numbers like "H-1" (with hyphens) for legitimate items. The regex correctly allows these through. However, if the LLM ever produces bare-letter items for legitimate content (unlikely but possible), the scanner would silently skip them. Monitor during next batch extraction.

---

## Session Notes (2026-03-14, Cross-Committee Aggregation Fix)

### D11. Scanner Aggregated by Committee Name, Not Candidate
**Origin:** Operator review (2026-03-14) | **Status:** ✅ Fixed

`signal_campaign_contribution()` aggregation key was `f"{norm_donor}||{normalize_text(committee)}"`, so donations to "Cesar Zepeda for City Council 2022" and "...2026" produced separate flags. Changed to resolve the candidate via `extract_candidate_from_committee()` first, aggregating by (donor, candidate) instead of (donor, committee). Reduced Elizabeth Echols/Zepeda from 2 flags to 1, Diana Wear/Jimenez from 2 to 1.

### D12. Cloud Pipeline Flag Save Used Non-Existent v2 Attributes
**Origin:** Rescan failure (2026-03-14) | **Status:** ✅ Fixed

`cloud_pipeline.py` line 474 accessed `flag.donor_name`, `flag.amount`, `flag.committee` — attributes that don't exist on the v3 `ConflictFlag` dataclass. Any cloud pipeline rescan would crash at the flag save step. Latent since the v3 scanner migration. Fixed to use `flag.evidence`, `flag.flag_type`, `flag.confidence_factors`, etc.

### D13. Retrospective Rescans Didn't Supersede Old Flags
**Origin:** Rescan (2026-03-14) | **Status:** ✅ Fixed

`supersede_flags_for_meeting()` was gated behind `if scan_mode == "prospective"`, meaning retrospective rescans would accumulate flags without marking old ones `is_current = FALSE`. The Oct 28 meeting had 13 stale retrospective flags. Fixed to supersede for any scan mode.

### I23. CAL-ACCESS Reversed Name Format Not Merging with NetFile
**Origin:** Oct 28 rescan review (2026-03-14) | **Priority:** Low

After the cross-committee fix, Diana Wear's donations to Gayle McLaughlin appear as two separate flags: one from NetFile ("Gayle McLaughlin for Richmond City Council 2020") and one from CAL-ACCESS ("MC LAUGHLIN FOR LIEUTENANT GOVERNOR 2018; GAYLE"). The `extract_candidate_from_committee()` function handles the reversed format, but the extracted names ("Gayle McLaughlin" vs "Gayle Mc Laughlin") don't normalize identically due to the space in "Mc Laughlin". Would need fuzzy candidate matching or an alias table for cross-source candidate dedup.

### I24. Full Batch Rescan Needed for Cross-Committee Fix ➜ Merged into I26
**Origin:** Rescan (2026-03-14) | **Merged:** 2026-03-15

Consolidated into I26 (combined rescan trigger checklist) to avoid running multiple partial rescans.

### D14. Stats Page Queries Do Client-Side Aggregation Over 14K+ Rows ➜ ✅ Fixed
**Origin:** Topics & Trends slow load (2026-03-14) | **Fixed:** 2026-03-15

Replaced client-side aggregation (14K+ rows + ~50 sequential public_comments batch requests) with three SQL RPC functions in migration 038:
- `parse_vote_tally(text)` — reusable helper replicating the 4-format TypeScript parser in SQL (IMMUTABLE)
- `get_category_stats(city_fips)` — GROUP BY category with controversy scoring, comment counts via JOIN
- `get_controversial_items(city_fips, limit)` — per-meeting comment normalization + scoring in SQL

`queries.ts` now calls `supabase.rpc()` for both functions. `computeControversyScore()` TypeScript function removed (dead code). `parseVoteTally()` kept (used by other queries). New index on `public_comments(agenda_item_id)` for the JOIN. ~50 round-trips → 1 query each.

### D15. Audit Other Pages for Unnecessary `force-dynamic` ➜ ✅ Fixed
**Origin:** Stats page investigation (2026-03-14) | **Fixed:** 2026-03-15

Audited all 18 pages. 12 already used `revalidate = 3600`. Found 3 using `force-dynamic`:
- **`/financial-connections`** — switched to `revalidate = 3600`. Was semantic ("operator-only") not technical. Same pattern as every other page.
- **`/council/patterns`** — switched to `revalidate = 1800` + `maxDuration = 60`. Heavy pairwise computation but deterministic. 30-min cache avoids redundant 55K+ vote joins.
- **`/search`** — kept `force-dynamic`. Client component with real-time search input; the server cache setting is moot for UX.

---

## Session Notes (2026-03-14, CAL-ACCESS First Run + IE Detector Recovery)

### I25. CAL-ACCESS First Production Run
**Origin:** Session (2026-03-14) | **Status:** Complete

First-ever CAL-ACCESS sync ran successfully: 9,258 records loaded (contributions + independent expenditures). Downstream integration already existed — conflict scanner's campaign contribution and donor-vendor detectors consume this data automatically. No new wiring needed.

Dashboard showed "never run" despite successful `data_sync_log` entry (`status='completed'`, `completed_at=2026-03-15T00:26:59Z`). Root cause: Vercel CDN caching (`s-maxage=3600` on `/api/data-freshness`). Resolves after cache TTL expires. Not a bug — working as designed.

### D16. Uncommitted IE Signal Detector Recovered
**Origin:** Session (2026-03-14) | **Status:** ✅ Committed and pushed

Found ~500 lines of uncommitted work in the working tree: a complete independent expenditure signal detector (signal #6) with `extract_backer_from_committee()`, `signal_independent_expenditure()`, DB fetch function, batch scan integration, and 83 passing tests. Origin: likely a previous session that ran out of context before committing.

**Process observation:** This reinforces I10 (background task output persistence) — long sessions should commit incrementally rather than batching all changes to the end. A mid-session commit after completing the detector would have prevented this from sitting uncommitted.

### I26. Full Batch Rescan Now Needed — Combined Trigger Checklist
**Origin:** Session (2026-03-14), updated 2026-03-15 | **Priority:** Medium

A full batch rescan (`python batch_scan.py`) is needed to propagate multiple accumulated improvements. **Run the rescan after the next data source addition** (commission meetings, paper filings, or other S8 backlog items) to avoid rescanning twice.

**Changes waiting on rescan:**
- ✅ Connection clause (`_build_connection_clause()`) — flag descriptions now explain WHY the donor is relevant to the agenda item (2026-03-15)
- ✅ Cross-committee aggregation fix (D11) — donations to same candidate across committees now merge (2026-03-14)
- ✅ Independent expenditure signal detector (#6) + CAL-ACCESS data loaded (D16/I25) — new PAC/IE flags (2026-03-14)
- ✅ Retrospective supersede fix (D13) — old flags will be properly marked `is_current = FALSE` (2026-03-14)

**Trigger:** Run immediately after the next data source lands (commission meetings, paper filings, additional NetFile data, or any new meeting minutes extraction). All four improvements activate in a single pass. If no new data source lands within 2 weeks, run anyway — the description improvement alone is worth it for operator review.

**Post-rescan validation:** Spot-check 3-5 flags to confirm connection clauses read naturally and the agenda item context is clear. Compare flag counts against previous run (1,359 flags from 2026-03-12) to verify cross-committee dedup reduced totals.

---

## Session Notes (2026-03-15, Pipeline Contract Enforcement)

### D17. PyMuPDF NUL Byte Extraction Pattern
**Origin:** Cloud pipeline crash (2026-03-15) | **Status:** ✅ Fixed

PyMuPDF extracts `\x00` bytes from corrupted government PDF fonts. PostgreSQL TEXT columns reject NUL bytes, causing `psycopg2.DatabaseError`. The bug was latent across 3 independent PDF extraction paths (`escribemeetings_scraper.py`, `pipeline.py`, `archive_center_discovery.py`) plus any future extraction code.

**Fix:** Defense in depth — strip at extraction AND at DB boundary (`db.py:sanitize_text()`). The DB boundary defense catches any future extraction path that forgets to strip. Pattern: always sanitize at the system boundary, not just the source.

### D18. `_FakeFlag` / `ConflictFlag` Attribute Divergence
**Origin:** Pre-existing test failure (2026-03-15) | **Status:** ✅ Fixed

`test_cloud_pipeline.py` used a `_FakeFlag` class with 7 attributes + 4 fake-only fields. Real `ConflictFlag` has 13 attributes. The test had been silently broken since the v3 scanner migration. Replaced with `_make_flag()` factory that creates real `ConflictFlag` instances — any future attribute change breaks the test immediately instead of silently diverging.

**Pattern:** Test fixtures that shadow real dataclasses will drift. Always construct real instances (with factory helpers for convenience) instead of reimplementing the shape.

### I27. Schema-Contract Tests as Drift Detection
**Origin:** `extracted_text` column bug (2026-03-15) | **Priority:** Observation (already implemented)

`test_schema_contracts.py` queries `information_schema.columns` against live Supabase to verify that columns referenced in Python SQL strings actually exist. Catches the class of bugs where code references a renamed/removed column (like `documents.extracted_text` when the real column is `raw_text`). 7 tables covered, all 7 pass.

**Maintenance rule:** When Python code references a new column in a SQL string, add it to `SCHEMA_CONTRACTS` in the test file. When a migration renames/removes a column, the test catches the drift automatically.

### I28. `sanitize_text()` DB Boundary Defense Pattern
**Origin:** NUL byte fix (2026-03-15) | **Priority:** Observation (already implemented)

`db.py:sanitize_text()` strips characters PostgreSQL TEXT rejects (`\x00`). Applied at 5 insertion points: `ingest_document()` raw_text, consent/action agenda item title/description, contribution donor_name/employer/occupation. The function is intentionally simple (single `replace`) and applied at the DB boundary rather than in business logic.

**Extension candidates:** If other encoding issues surface (e.g., lone surrogates, BOM markers), extend `sanitize_text()` rather than adding per-caller fixes. The boundary defense pattern means one fix covers all insertion paths.

### D19. Data Quality Checks Cascading Transaction Abort
**Origin:** Pipeline failure chain (2026-03-15) | **Status:** ✅ Fixed

`data_quality_checks.py` ran 9 checks sequentially on a single connection. The first check failure (`extracted_text` column) aborted the transaction, causing all 8 remaining checks to fail with "current transaction is aborted." Fixed by adding `conn.commit()` after each successful check and `conn.rollback()` in the except handler, isolating check failures.

**Pattern:** Any function that runs multiple independent queries on a single psycopg2 connection must handle transaction state between queries. PostgreSQL aborts the entire transaction on any error — there's no "skip and continue" without explicit rollback.

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

### V7. Regulatory Data Volume and Quality After First Sync ✅
**Origin:** B.44 (2026-03-15) | **Validated:** 2026-03-15

First full sync completed successfully. Actual counts vs estimates:
- Permits: 177,431 (matched estimate, 4 batches, 11.6 min)
- Service Requests: 44,054 (matched, 3.6 min)
- Code Cases: 36,764 (matched, 9.4 min)
- Licenses: 6,215 (matched, 29s)
- Projects: 5,287 (matched, 26s)
- **Total: 269,751 records**

No rate limiting issues despite no app token. Dual date format parser (`_parse_socrata_date`) handled both ISO and text formats. ON CONFLICT upsert idempotent on re-run. Migration 039 required one fix: `DATE - DATE` returns INTEGER in PostgreSQL, not INTERVAL (view used `EXTRACT(EPOCH FROM ...)` which failed).

**Still to validate for B.45:** normalized_company quality, resolution_no coverage, applied_by usefulness (known to be staff initials only).

---

## Session Notes (2026-03-15, S8.3 Commission Meeting Extraction)

### D20. Fuzzy Find 3-Column Unpack Bug (Latent Bug Pattern)
**Origin:** S8.3 commission extraction (2026-03-15) | **Status:** ✅ Fixed

`_fuzzy_find_official()` in `db.py` queried 3 columns (`id`, `normalized_name`, `is_current`) but unpacked into 2 variables. This only surfaced during commission extraction because council members were already in the `officials` table (exact-match path), while commission members hit the fuzzy-match path for the first time.

**Pattern:** Latent bugs hide in code paths that aren't exercised by current data. When adding a new data source (commissions, permits, etc.), expect bugs in shared functions that have only been tested with the original data type. The 3-column query was correct; the unpack was stale from before `is_current` was added.

### D21. Per-Document Transaction Isolation in Sync Functions
**Origin:** S8.3 cascade failures (2026-03-15) | **Status:** ✅ Fixed

`sync_minutes_extraction` ran all document extractions in a single transaction. One failed INSERT (constraint violation) aborted psycopg2's transaction state, causing all subsequent documents to fail with "current transaction is aborted." Fixed with `conn.commit()` per successful document and `conn.rollback()` on error.

**Pattern:** Same root cause as D19 (data quality checks cascading abort). Any sync function processing multiple independent records on a single psycopg2 connection must isolate transactions per record. This should be the default pattern for all sync functions — grep for multi-record loops without intermediate commits.

### I31. Commission Extraction Quality Observations
**Origin:** S8.3 extraction review (2026-03-15) | **Priority:** Low

Two minor extraction artifacts observed across 4 commission AMIDs:
1. **Presiding officer field** sometimes captures the mayor's name from the meeting header instead of the actual commission chair. Affects commissions where the header includes "Mayor X" as appointing authority. Low impact since presiding officer is display-only, not used for analysis.
2. **`<UNKNOWN>` attendance entries** appear in some commission meetings where the LLM couldn't parse attendee names from the PDF format. These are harmless (filtered out during official resolution) but could be cleaned up with a post-extraction filter.

### I32. 700+ Commission Documents Remain for Future Extraction
**Origin:** S8.3 initial sync (2026-03-15) | **Priority:** Medium

Initial extraction ran 20 documents per AMID (80 total). Remaining documents across configured AMIDs:
- Planning Commission (AMID 75): ~200 documents
- Personnel Board (AMID 132): ~150 documents
- Richmond Rent Board (AMID 168): ~250 documents
- Design Review Board (AMID 61): ~100 documents

Cost estimate: ~$0.06/document × 700 = ~$42 for full extraction. Could be batched via the existing `sync_minutes_extraction` with `--limit` removed. Consider running during off-peak to avoid Claude API rate limits.

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

### D22. Proportional Specificity Changes Existing Confidence Scores
**Origin:** B.52 implementation (2026-03-15)
**Observation:** Replacing the binary 0.7x specificity penalty with proportional scoring changed the confidence scores of existing flags. "National Auto Fleet Group" went from 0.8475 to 0.7731 because 2/4 words are distinctive (50% → 0.75 multiplier vs old 0.7). This changes publication tier assignments for some existing flags. A batch rescan is needed to update stored confidence values.
**Recommendation:** Include in the next batch rescan cycle (I26). No emergency action needed since the new scoring is more accurate — but stale confidence values in the DB will diverge from what the scanner would produce today until rescan completes.

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
