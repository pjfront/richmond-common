# AI Parking Lot

_Ideas, research topics, and improvement suggestions captured by the AI during implementation sessions. AI has full autonomy over this file. Periodically reviewed and prioritized with the operator for integration into the roadmap._

_Convention: Every session adds observations here. Items stay until promoted to the sprint backlog or explicitly discarded during a review._

---

## Promoted to Phase 3

_Items from this parking lot that have been promoted to Phase 3 sprints (S22-S25). Kept here for reference; active tracking in `docs/PARKING-LOT.md`._

- ~~I71~~ Semantic similarity & controversy discovery → **S22**
- ~~I60~~ Lightweight topic timeline using existing categories → **S23.1**
- ~~I80~~ Topic landing pages (per-topic summary, timeline, related issues) → **S23.1**
- ~~I68~~ AI-generated comment summaries per agenda item → **S23.5**
- ~~I84~~ Email digest / subscription notifications → **S23.3**
- ~~I45~~ Proceeding type classification for existing agenda items → **S22.4**
- ~~I62~~ CONTRIBUTING.md and issue templates for public repo → **S25.1**
- ~~I63~~ GitHub repo metadata for discoverability → **S25.1**
- ~~I83~~ "How to Use This Site" guide page → **S25.3**
- ~~I87~~ Council member photos from city website → **S25.4**
- ~~I82~~ Inline search overlay (command palette pattern) → **S25.5**
- ~~I90~~ Voting record — show topic labels on mobile → **S25.5**
- ~~I92~~ Voting record — topic filter redesign → **S25.5**
- ~~I93~~ Meeting detail — quick text filter for agenda items → **S25.5**
- ~~R4~~ Search query analytics before RAG investment → **S22.5**

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

### I97. Written Comment Extraction Pipeline (S21 Phase E)
**Origin:** Operator decision blocking S21 graduation (2026-04-03) | **Priority:** High (blocks "Themes From Comments" graduation)

Written public comments (emails, eComments) submitted before meetings appear as attachments in eSCRIBE agenda packets. The scraper already downloads these PDFs but doesn't identify or separately extract the comment content. Pipeline needed:
1. **Classify attachments** — distinguish public comment compilations from staff reports, contracts, etc. (by filename pattern, attachment position, or Claude classification)
2. **Extract individual comments** — parse multi-comment PDFs into individual speaker records with name, method (email/ecomment), and full text
3. **Write to `public_comments`** — with `comment_type='written'`, `method='email'/'ecomment'`, `source='escribemeetings_attachment'`
4. **Feed into theme extractor** — written comments join spoken comments in theme analysis

The schema already supports this (`method` includes 'email'/'ecomment', `comment_type` includes 'written'). Only the extraction pipeline is missing.
