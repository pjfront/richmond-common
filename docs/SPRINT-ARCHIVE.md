# Sprint Archive — Phase 2: Build the Engine (S1-S20)

> Completed sprints moved from PARKING-LOT.md during the Phase 3 restructure (2026-03-27).
> For the active roadmap, see [PARKING-LOT.md](PARKING-LOT.md).
>
> **Scoring:** Paths **A** = Freemium Platform, **B** = Horizontal Scaling, **C** = Data Infrastructure.
> **Publication tiers:** Public · Operator-only · Graduated.

---

## Sprint 1 — Visibility + Data Foundation

*Make progress visible. Lay the data groundwork everything else builds on.*

**Why first:** Feature gating unlocks the ability to see every subsequent sprint's output. Archive expansion fills the Document Lake that vote categorization, Form 700, and RAG search all need. Quick frontend wins (table sorting, commission pages) show citizens the platform is alive. CI/CD stops manual deploys.

### ✅ S1.1 Feature Gating System (NEW)
- **Paths:** A, B
- **Status:** Complete. Cookie-based `OperatorModeProvider` + `OperatorGate` component. URL-param activation, 30-day cookie persistence. Wired into root layout. Real Supabase Auth can replace it later without changing component structure.
- **Publication:** Public infrastructure (the gating mechanism itself is invisible to citizens).

### ✅ S1.2 Table Sorting/Filtering on All Views [was 4.1]
- **Paths:** A, B
- **Status:** Complete. TanStack React Table v8 on all data tables (DonorTable, VotingRecordTable, CommissionRosterTable, MeetingCompletenessTable). Reusable `SortableHeader` component.
- **Publication:** Public.

### ✅ S1.3 Commission Pages [was 4.4]
- **Paths:** A, B
- **Status:** Complete and **Public** (split graduation). Commission index and detail pages with rosters, appointment tracking, vacancy counts. Nav link visible to all users.
- **Publication:** → Public (roster data, vacancy counts, appointment info — graduated 2026-03-01). Staleness alerts remain operator-only via inline `OperatorGate`.

### ✅ S1.4 Archive Center Expansion [was 5.6]
- **Paths:** B, C
- **Status:** Complete. `archive_center_discovery.py` with tiered AMID support (Tier 1: resolutions, ordinances, Personnel Board; Tier 2: Rent Board, Design Review, Planning). `batch_extract.py --archive-download` with `--archive-tiers` flag. Multi-city config-aware.
- **Publication:** Infrastructure (feeds Document Lake for downstream features).

### ✅ S1.5 CI/CD: Vercel Auto-Deploy + GitHub Actions Tests [was 0.1]
- **Paths:** B
- **Status:** Complete. Vercel auto-deploys on push to main. `test.yml` runs pytest on PRs. `cloud-pipeline.yml` orchestrates scheduled + manual pipeline runs with artifact uploads.

---

## Sprint 2 — Vote Intelligence

*The highest-leverage unlock: categorized votes enable coalition analysis, time-spent stats, trend tracking, and meaningful cross-meeting pattern detection.*

**Why second:** Vote categorization [2.1] is prerequisite for S6 (coalition analysis, patterns, time-spent). It's triple-path (A+B+C). With archive data from S1, the categorizer can cross-reference votes against the resolutions/ordinances they produce.

### ✅ S2.1 Vote Categorization Taxonomy & Classifier [was 2.1]
- **Paths:** A, B, C
- **Status:** Complete and **Public**. 14-category enum in `models.py` (zoning, budget, housing, public_safety, environment, infrastructure, personnel, contracts, governance, proclamation, litigation, other, appointments, procedural). LLM classification during extraction. Migration 006 backfill for historical data. `category` field on `agenda_items` with index.
- **Prerequisite for:** S6.1 (coalition), S6.2 (patterns), S6.3 (time-spent).
- **Publication:** Public (categories are factual).

### ✅ S2.2 Category Display Components (NEW)
- **Paths:** A
- **Status:** Complete and **Public**. `CategoryBadge` (color-coded, 25 category colors), `CategoryBreakdown` (topic distribution bar chart), `TopicOverview` (expandable per-meeting breakdown). Click-to-filter on meetings page and `VotingRecordTable`. Category dropdown filter + clickable badges with active state highlighting.
- **Publication:** Public.

### S2.3 AI-Generated Council Member Bios [was 2.6] ✅
- **Paths:** A, B, C
- **Status:** Complete and **Public**. Two-layer system: Layer 1 factual profile (public from launch), Layer 2 AI-synthesized narrative (graduated to Public 2026-03-01 after operator framing review). Constrained prompt: no ideology, no value judgments, no comparisons. Transparency disclaimer retained.
- **Description:** Synthesis prompt combining voting record, campaign filings, committee assignments. "Sunlight not surveillance" framing critical.
- **Publication:** ~~Graduated~~ → Public (graduated 2026-03-01).

---

## Sprint 3 — Citizen Clarity

*Make government decisions understandable to non-experts.*

**Why third:** Plain language summaries are the single most citizen-friendly feature. "Explain This Vote" builds on summaries + categories from S2. Both are public-ready and demonstrate immediate value.

### S3.1 Plain Language Agenda Summaries [was 2.4] ✅
- **Paths:** A, B, C
- **Status:** Complete and **Public**. Migration 007, prompt templates in `src/prompts/`, summarizer module, CLI runner, frontend display. 12 tests. Summaries generated for all meetings. Graduated to Public 2026-03-01 after operator framing review.
- **Description:** `plain_language_summary` field on `agenda_items`. Dedicated prompt template file. Validate on 3-5 pilot meetings before public release.
- **Frontend:** Progressive disclosure on meeting detail pages. Official title visible by default; plain English summary expands on click. Preserves accuracy/searchability while making content accessible to laypeople.
- **Publication:** Graduated (operator-only until pilot validation). See H.14 for UX iteration, H.15 for meeting-level summaries.

### S3.2 "Explain This Vote" Lite [was 4.2] ✅
- **Paths:** A, B
- **Status:** Complete and **Public**. Migration 008, prompt templates in `src/prompts/`, explainer module (`vote_explainer.py`), CLI runner (`generate_vote_explainers.py`), frontend display in `VoteBreakdown.tsx`. 37 tests. Scope: Option B (contextual framing: what was decided, why it matters, whether contentious). Option C (historical voting patterns) parked as H.16. Graduated to Public 2026-03-01 after operator framing review.
- **Description:** Per-vote explainer generated from agenda item context + vote breakdown. 3-5 sentences of plain English. Skips procedural items and unanimous consent calendar votes. Names dissenters on split votes. No motive inference.
- **Publication:** Graduated. Operator-only until framing validated.
- **Depends on:** S2.1 (categories) and S3.1 (summaries) for richer context.

---

## Sprint 4 — Data Quality & Integrity

*Fix the foundation. Prevent the Jamelia Brown class of bugs from ever happening silently again.*

**Why here (not earlier):** Data quality doesn't block feature development, but it protects the features we've built. After S1-S3, there's enough visible output that data quality issues become user-facing problems worth solving systematically.

### S4.1 Fuzzy Duplicate Official Detection ✅
- **Paths:** B, C
- **Description:** Add fuzzy matching to `ensure_official()` or a post-load validation step. When a new official name is within Levenshtein distance 2 of an existing official, warn (or merge if confidence is high). Wire up `aliases` field from `officials.json` into lookup.
- **Origin:** Jamelia Brown silent data split. April 15, 2025 minutes misspelled name, created phantom record with 0 votes.
- **Publication:** Operator-only (data quality alerts).
- **Done:** 697b893

### S4.2 Data Freshness & Completeness Monitoring ✅
- **Paths:** A, B, C
- **Description:** Automated checks: Are meetings loading on schedule? Are vote counts reasonable? Are all expected council members appearing? Document completeness tracking (missing minutes, late agenda packets). Alerts to operator when anomalies detected.
- **Publication:** Operator-only (alerts and dashboard).
- **Done:** Python `completeness_monitor.py` (23 tests), API `/api/data-quality`, operator-only `/data-quality` dashboard with freshness, coverage, anomalies, and meeting completeness table.

### S4.3 Alias Wiring for Conflict Scanner ✅
- **Paths:** A, C
- **Description:** Update `conflict_scanner.py` to load aliases from `officials.json` and include them in donor/entity name matching. First case: Shasa Curl (legal name "Kinshasa Curl" in campaign filings).
- **Scope:** Small. Expand the name set during entity resolution.
- **Done:** 697b893

---

## Sprint 5 — Financial Intelligence

*The highest-value conflict detection signals. Form 700 is the crown jewel.*

**Why here:** Form 700 research is done (`docs/research/form-700-research.md`). Commission pipeline is stable (prerequisite met). Archive data from S1 provides contract/resolution context. This is where the project's core accountability value deepens significantly.

### S5.1 Form 700 Ingestion [was 2.5] ✅
- **Paths:** A, B, C
- **Status:** Complete and **Public**. Scraper (requests-based), extractor (PyMuPDF), `economic_interests` table (migration 009), conflict scanner integration, filing period context. Frontend `EconomicInterestsTable` component with year tabs, schedule grouping, source links. Graduated to Public 2026-03-01 after operator accuracy + framing review.
- **Description:** Parse FPPC Form 700 PDFs for economic interest disclosures. Cross-reference against agenda items for council AND commission members. Highest-value conflict detection signal.
- **Research:** `docs/research/form-700-research.md`
- **Publication:** ~~Graduated~~ → Public (graduated 2026-03-01).

### ✅ S5.2 Contribution Context Intelligence [was 3.2]
- **Paths:** A, B, C
- **Status:** Complete. Contribution enricher (`contribution_enricher.py`), `donor_pattern_badges` table, rule-based classification (PAC, mega, grassroots, targeted, regular), scanner enrichment. Frontend donor pattern badges on council profiles.
- **Description:** Enrich each contribution flag with context: is this donor's $500 one of many small donations (grassroots) or their only political contribution (targeted)? Employer donation pattern detection. Context transforms raw flags into intelligence.
- **Publication:** Split (decided 2026-03-01). PAC badge → **Public** (factual entity-type label). Behavioral pattern badges (Major, Grassroots, Targeted) → **Operator-only** pending empirical threshold validation against Richmond contribution distribution. Graduation trigger: validate $75K mega threshold, $250 grassroots avg, $1K targeted avg against actual data distribution.

---

## Sprint 6 — Pattern Detection

*Cross-referencing that finds what single-meeting analysis can't see.*

**Why here:** Requires vote categorization (S2) and financial intelligence (S5). Coalition analysis and cross-meeting patterns are the "wow" features, but they need the data foundation beneath them.

### S6.1 Coalition/Voting Pattern Analysis [was 2.2] ✅
- **Paths:** A, B, C
- **Status:** Complete. `/council/coalitions` page with pairwise alignment matrix (21 pairs from 7 members), voting bloc detection (brute-force clique finding), category divergence table. Category filter buttons on heatmap. Framing: no ideology labels, no motive inference, always show data behind numbers. 926 votes analyzed, public_safety identified as primary wedge issue.
- **Depends on:** S2.1 (vote categorization).
- **Publication:** Graduated. Coalition framing is politically sensitive.

### S6.2 Cross-Meeting Pattern Detection [was 3.1] ✅
- **Paths:** A, B, C
- **Status:** Complete. `/council/patterns` page with donor-category concentration analysis and cross-official donor overlap table. 275 donors, 39 multi-recipient donors, 1,000 contributions analyzed. Concentration metric (recipients' vote category distribution) found no significant single-issue patterns in Richmond (correct result: council members vote across all categories). v1 defers Pattern 2 (temporal contribution-vote proximity) which requires robust employer fuzzy matching.
- **Depends on:** S2.1 (categories for meaningful pattern grouping).
- **Publication:** Graduated. Most sensitive feature (correlates money and votes).

### S6.3 Council Time-Spent Stats v1 [was 2.3] ✅
- **Paths:** A, B, C
- **Status:** Complete and **Public**. `/council/stats` page with category distribution table (TanStack Table, sortable), controversy leaderboard (composite 0-10 score from vote splits + comments + multiple motions), summary stat cards. Robust multi-format vote tally parser handles all extraction output formats. Migration 011 adds `discussion_duration_minutes`, `public_comment_count` columns and category/result indexes.
- **Description:** Category distribution, vote counts by category, controversy score (split vs. unanimous). Just SQL on categorized data.
- **Depends on:** S2.1.
- **Publication:** Public (factual statistics).

---

## Sprint 7 — Operator Layer

*Tools that make operator decision-making faster and more systematic.*

**Why last of the numbered sprints:** Not blocking any citizen-facing features. The operator layer becomes more valuable as more features exist to manage. After S1-S6, there are enough graduated features, data quality signals, and decision points to warrant a proper operator dashboard.

### S7.1 Operator Decision Queue [was 1.1] ✅
- **Paths:** A, B
- **Status:** Complete. `decision_queue.py` (create/resolve/query API), `pending_decisions` table (migration 016), `/operator/decisions` page with severity badges (critical/high/medium/low/info), expandable evidence cards, resolution workflow. `staleness_monitor.py` and `completeness_monitor.py` auto-create decisions via `--create-decisions` flag. Dedup keys prevent duplicate alerts.
- **Description:** Dashboard showing everything that needs human decision: flags to review, findings to graduate from operator-only to public, data quality alerts, staleness findings. Pre-digested packets presenting minimum information for fastest correct decision.
- **Publication:** Operator-only.

### S7.2 Pre-Digested Decision Packets [was 1.2] ✅
- **Paths:** A, B
- **Status:** Complete. `decision_briefing.py` CLI produces session-start summaries (`--format text/json`, `--include-resolved`, `--check` with exit code 1 on critical/high). Staleness and completeness monitors auto-assemble evidence into decision records. Each decision includes: title, description, source, severity, evidence payload, recommended action. `/api/operator/decisions` endpoint serves pending + recently resolved.
- **Description:** For each decision point, the system assembles: the finding, all evidence, comparable past decisions, confidence assessment, and a recommended action.
- **Publication:** Operator-only.

### S7.3 Judgment-Boundary Audit [was 1.4] ✅
- **Paths:** B
- **Status:** Complete (Q1 2026). 69 decision points inventoried, 88% correctly delegated. +5 judgment calls, +4 AI-delegable items added to catalog. Threshold sync gap identified. Audit report: `docs/audits/2026-Q1-judgment-boundary-audit.md`.
- **Description:** System reviews all processes marked as judgment calls and challenges each one. Also reviews AI-delegable processes for ones that should have human oversight. Bidirectional per tenet #2.
- **Publication:** Operator-only. Feeds roadmap.
- **Cadence:** Quarterly. Next: Q2 2026.

### S7.4 Autonomy Zones Phase A: Pipeline Journal + Self-Assessment (NEW) ✅
- **Paths:** A, B, C
- **Status:** Complete. `pipeline_journal.py` (PipelineJournal class, anomaly detection), `self_assessment.py` (Claude Sonnet health reports, decision packet creation), migration 015 (`pipeline_journal` table). All three GH Actions workflows (cloud-pipeline, data-sync, data-quality) instrumented with `--create-decisions` self-assessment step. `cloud_pipeline.py` and `data_sync.py` log all steps with anomaly checks. 41 tests.
- **Description:** Append-only pipeline journal (`pipeline_journal` table) logging every run's metrics, confidence scores, error counts, and anomalies. Scheduled self-assessment cycle (LLM reads journal, produces structured health report as decision packet). No self-modification. Observation only. Feeds S7.1 (decision queue) and S7.2 (decision packets). Foundation for Phase B (free-zone self-modification) and Phase C (proposal zone). Full spec: `docs/specs/autonomy-zones-spec.md`.
- **Publication:** Operator-only (infrastructure).
- **Inspired by:** [yoyo-evolve](https://github.com/yologdev/yoyo-evolve) self-assessment loop pattern.

### Pre-S7: Generator Automation Patch (NEW) ✅
- **Paths:** A, B
- **Status:** Complete. Steps 8-9 added to `cloud_pipeline.py` (generate summaries + vote explainers after Layer 2 load). Non-critical: generator failures log but don't fail the pipeline. `--skip-generators` CLI flag for cost control. 13 new tests (848 total). Summary and explainer stats included in pipeline output JSON.
- **Description:** Wire `generate_summaries.py` and `generate_vote_explainers.py` into `cloud_pipeline.py` as post-load steps (after Step 6: Load meeting to Layer 2). Previously, new meetings arriving via the weekly cloud pipeline got conflict scans and public comments but no plain language summaries or vote explainers. Citizens saw raw agenda titles for new meetings. This completes S3 (Citizen Clarity) by making it continuous rather than one-shot.
- **Publication:** Infrastructure (feeds existing public features).

---

## Sprint 8 — Data Source Expansion

*Get all data sources assembled before building search or redesigning the UI.*

**Why here:** RAG search requires designing embedding templates per document type. Designing with full knowledge of all document types is better than retrofitting later. The UI overhaul (S10) benefits from knowing the full data landscape. Complete the data foundation first, then make it searchable, then make it beautiful.

### ✅ S8.1 Socrata Sync Wiring (Payroll + Expenditures)
- **Paths:** A, B, C
- **Status:** Complete. Both `sync_socrata_payroll` and `sync_socrata_expenditures` registered in `SYNC_SOURCES`. Payroll sync wraps existing `payroll_ingester.py` pipeline (fetch, aggregate transactions by employee, classify hierarchy, upsert to `city_employees`). Expenditures sync fetches from Socrata `expenditures` dataset with pagination, upserts to new `city_expenditures` table (migration 023). Both support incremental (current FY only) and full (5 years) sync modes. Staleness monitor already had thresholds configured (45 days each). `v_vendor_spending_summary` view enables vendor cross-referencing with conflict scanner. 20 new tests (945 total).
- **Description:** Wire existing `socrata_client.py` query functions into `data_sync.py` as registered sync sources (`sync_socrata_payroll`, `sync_socrata_expenditures`). The client code exists with `get_recent_expenditures()`, `get_vendor_payments()`, `get_department_budget()`. The `payroll_ingester.py` has ingestion logic for `city_employees`. Currently these show as "never synced" on the data quality dashboard because they're monitored but have no sync functions. Hygiene-level work.
- **Publication:** Infrastructure (feeds existing operator dashboard).

### S8.2 Court Records / Tyler Odyssey [was B.10] ✅
- **Paths:** A, B, C
- **Description:** Research and build scraper for Contra Costa County court records via the Tyler Odyssey portal (cc-courts.org). Cross-reference court cases involving city officials, contractors, and entities flagged in conflict scans. Research first: confirm Odyssey for Contra Costa County, assess scrapeability, define extraction schema.
- **Depends on:** S5.1 (Form 700 for entity cross-referencing).
- **Publication:** Graduated (legal data requires careful framing).
- **Status:** ✅ Built, ⏸️ dormant. Infrastructure complete (research doc, migration 024, scraper, data_sync, 52 tests) but **portal requires JavaScript + Google reCAPTCHA v2**, making requests-based scraping impossible. Dormant until: Tyler drops CAPTCHA, CourtListener adds Contra Costa civil cases, or a Playwright+manual-CAPTCHA approach is worth the effort.

### ✅ S8.3 Commission/Board Meeting Agendas & Minutes [was B.36]
- **Paths:** A, B, C
- **Status:** ✅ Complete (2026-03-15). Pipeline + initial sync + frontend. Commission-aware eSCRIBE→scanner converter (non-council items route to action_items). Commission extraction prompt + schema (commission roles: chair/vice_chair/commissioner/member/board_member/alternate; no consent calendar; public_hearing category; recommendation language capture). `extract_with_tool_use()` + `build_batch_request()` accept `body_type` param. `sync_minutes_extraction()` accepts `--amid` + `--body-type` CLI args for commission AMID extraction. `sync_escribemeetings()` resolves body_id from MeetingName→bodies table. Source identifier collision fix (includes meeting name). `backfill_escribemeetings_layer2` body_id-aware. Commission AMIDs mapped in city_config: Personnel Board=132, Richmond Rent Board=168, Design Review Board=61, Planning Commission=75. 28 tests in `test_commission_meetings.py`. **Initial sync results:** 53 commission meetings extracted (19 Planning, 14 Personnel, 10 Design Review, 10 Rent Board) with 164 agenda items, attendance records, and motions. Migration 037: body-aware meeting uniqueness constraint (drops old 3-column, adds 4-column with body_id NOT NULL). Bug fixes: fuzzy official matching 3-column unpack, per-document transaction commit/rollback in extraction. Frontend: `getCommissionMeetings()` query + `CommissionMeetingHistory` component on commission detail pages with show-more pagination. **Ongoing:** More commission meetings can be extracted in future sync runs (700+ documents remain across all AMIDs).
- **Depends on:** ✅ B.22 (bodies table), ✅ S8.5 (body type context), ✅ S1.4 (archive expansion), ✅ S1.3 (commission pages).
- **Publication:** Graduated (new data source, validate extraction quality first).

### S8.4 Paper-Filed Form 700s [was B.32]
- **Paths:** A, C
- **Description:** Scraper for NetFile's separate paper-filing portal (different URL/form structure from e-filed portal). Paper filing is legal under CA law, so any filer can avoid the e-filed portal while remaining fully compliant. Without this scraper, paper filers are a transparency blind spot. **First step:** cross-reference our 97 e-filers against the official list of designated filers (City Clerk). Any gap = paper filer = build the scraper. Priority escalates if council members or commissioners are in the gap.
- **Depends on:** S5.1 (Form 700 e-filed, complete). Trigger: gap analysis identifies paper filers.
- **Publication:** Graduated (extends existing public Form 700 display).

### ✅ S8.5 Meeting Body Type Context in Pipeline
- **Paths:** A, B, C
- **Status:** ✅ Complete (2026-03-15). `load_meeting_to_db()` now accepts `body_id` parameter. Body type → default role mapping: city_council→councilmember, commission→commissioner, board→board_member, authority→board_member, committee→committee_member, joint→member. `body_id` flows through to `meetings` and `meeting_attendance` INSERTs. Helper `resolve_body_id(conn, city_fips, body_name)` for callers to look up body FK. Auto-resolves to City Council when body_id not provided. Migration 037 made body_id NOT NULL (backfilled all existing meetings to City Council body). 22 tests in `test_body_type_context.py`.
- **Depends on:** ✅ B.22 (bodies table, complete).
- **Publication:** Infrastructure (fixes data quality, no new public features).

---

## Sprint 9 — Scanner v3: Signal Architecture

*Fix the core intelligence engine. Zero actionable output without it.*

**Why now:** v2 batch scan (2026-03-09) confirmed the fundamental problem: 9,927 current flags, 88.5% clustered at 0.40-0.49 confidence, zero above 0.60. form700_real_property is 86% of flags at exactly 0.400 confidence. Single-dimension scoring shifts the cluster but can't differentiate real conflicts from noise. Multi-factor scoring with independent signal detectors and cross-source corroboration is the path to useful intelligence. Plan: `docs/plans/2026-03-08-scanner-v3-signal-architecture.md`.

**Judgment calls resolved (2026-03-09):**
1. Publication tier threshold values (0.85/0.70/0.50): **Public**
2. `donor_vendor_expenditure` flag type: **Public**
3. Badge labels: **"High/Medium/Low-Confidence Pattern"**
4. Language framework: **Factual template + blocklist + hedge clause** ("Other explanations may exist." below 0.85)

### ✅ S9.1 RawSignal Dataclass + Composite Confidence Foundation
- **Paths:** A, B, C
- **Status:** Complete. `RawSignal` dataclass with `council_member` and `agenda_item_number` fields, `compute_composite_confidence()` with four weighted factors + corroboration boost + sitting multiplier, language framework constants (factual template, blocklist, hedge clause), `assign_publication_tier()`. 44 tests in `test_composite_confidence.py`.
- **Publication:** Infrastructure.

### ✅ S9.2 Extract Signal Detectors from Monolithic Scan
- **Paths:** A, B, C
- **Status:** Complete. Replaced ~443 lines of inline matching code with three signal detectors: `signal_campaign_contribution()`, `signal_form700_property()`, `signal_form700_income()`. Added helper functions: `_ScanContext` dataclass, `_compute_temporal_factor()`, `_compute_financial_factor()`, `_match_type_to_strength()`. `_signals_to_flags()` conversion maps `RawSignal` → `ConflictFlag` with v3 composite confidence. 39 new tests in `test_signal_detectors.py`. All existing tests updated for v3 confidence model. Key design discovery: single-signal max confidence is 0.8475 (tier 2) with anomaly stub at 0.5. Tier 1 requires corroboration (S9.3) or full anomaly_factor.
- **Publication:** Infrastructure.

### ✅ S9.3 Temporal Integration + Donor-Vendor Cross-Reference
- **Paths:** A, B, C
- **Status:** Complete. `signal_temporal_correlation()` integrates post-vote donation detection into the main scan loop as a RawSignal-producing detector. `signal_donor_vendor_expenditure()` cross-references `city_expenditures.normalized_vendor` against `contributions.donor_name`/`donor_employer`. `_signals_to_flags()` groups signals by (council_member, item) for corroboration boosting (1.15x for 2 types, 1.30x for 3+). Migration 026 adds `confidence_factors` JSONB + `scanner_version` columns. 26 new tests, 1123 total passing. Old `scan_temporal_correlations()` preserved as backward-compat wrapper.
- **Publication:** Public.

### ✅ S9.4 DB Mode Parity
- **Paths:** A, B, C
- **Status:** Complete. Added `_fetch_expenditures_from_db()` to query `city_expenditures` table, wired `expenditures` parameter into `scan_meeting_db()` signature and pass-through to `scan_meeting_json()`. The donor-vendor-expenditure signal detector now fires in DB mode. Pre-loadable for batch operations (same pattern as contributions/form700). 8 new tests (4 DB parity, 4 fetch function). 1131 tests passing.
- **Publication:** Infrastructure.

### ✅ S9.5 Batch Rescan + Validation
- **Paths:** A, B, C
- **Status:** Complete. Batch rescan executed 2026-03-12: 784 meetings, 1,359 flags (93.5% reduction from v2's 20,842 false-positive-heavy flags). 311 published (conf >= 0.50): 26 Tier 2, 285 Tier 3. 0 errors. Validation report confirmed precision improvement. Migration 029 (independent_expenditures) applied to production.
- **Pre-rescan cleanup (from AI Parking Lot):**
  - ✅ **D1:** Removed dual temporal correlation path. `cloud_pipeline.py` no longer imports/calls legacy `scan_temporal_correlations()`. Temporal analysis runs exclusively through v3 `signal_temporal_correlation()` via `scan_meeting_json()`.
  - ✅ **R1/I1:** Replaced entity extraction with gazetteer-based vendor matching. `signal_donor_vendor_expenditure()` now uses `cached_name_in_text()` (contiguous phrase match, 10-char minimum) instead of lossy `names_match()` pattern matching. Vendor gazetteer built from expenditure records in `scan_meeting_json()`.
  - ✅ **I5:** Added `get_richmond_expenditures()` parser for CAL-ACCESS `EXPN_CD` (independent expenditures). Migration 029 creates `independent_expenditures` table. `load_expenditures_to_db()` handles DB loading. CLI `expenditures` action added. 13 new tests.
- ✅ **Batch performance (O1-O5):** 33x speedup (3.8 hours → ~7 minutes). O1: pre-normalize contributions. O2: inverted word index. O3: name_in_text cache. O4: Form 700 pre-filter. O5: ProcessPoolExecutor parallelization. Spec: `docs/specs/scanner-batch-performance-spec.md`.
- ✅ **Validation checkpoint (V1):** `src/validate_rescan.py` compares two scan runs: total flags, above-0.50 percentage, distribution by type/tier, appeared/disappeared/tier-changed flags, top-5 spot-check. Ready for post-rescan comparison.
- **Key finding:** 77 flags on "CITY COUNCIL CONSENT CALENDAR" and 48 on "CLOSED SESSION" reveal that flags attach to parent-level agenda items, not specific sub-items. This makes flag display uninformative and prevents vote correlation (votes are on sub-items). **B.49 pulled to next priority** to fix this.
- **Publication:** Infrastructure.

### S9.6 Frontend Label Updates
- **Paths:** A
- **Status:** ✅ Complete.
- **Description:** Update confidence badge labels and display system for v3 scanner output.
- ✅ **Description display:** Added expandable row detail to `FinancialConnectionsAllTable` showing the full flag description (donor name, amount, recipient) and evidence tags. Rows are click-to-expand.
- ✅ **Three-tier confidence badges:** "Strong" (≥0.85, red), "Moderate" (≥0.70, yellow), "Low" (≥0.50, green). Green-yellow-red color gradient. Tooltip shows exact percentage. Old "Potential Conflict"/"Financial Connection" labels retired.
- ✅ **Factor breakdown display (R3):** Expandable rows show contributing factors (Name Match, Time Proximity, Financial Materiality, Statistical Anomaly) as colored progress bars. Signal count and corroboration boost displayed. Uses `confidence_factors` JSONB from migration 026.
- ✅ **Agenda item grouping (I4):** "Group by item" toggle in `FinancialConnectionsAllTable`. Groups flags by agenda item with headers showing item number, title, date, and signal count. Makes corroboration visually obvious.
- ✅ **Reports page updated:** Three-tier sections (Strong/Moderate/Low Patterns) replace old Tier 1/Tier 2. Methodology text updated.
- ✅ **thresholds.ts synced:** Comments aligned with v3 scanner. Legacy `CONFIDENCE_TIER_1`/`CONFIDENCE_TIER_2` aliases removed.
- **Publication:** Public.

---

## Sprint 10 — Citizen Discovery

*Make the data findable, not just browsable. Start with basic search, graduate to semantic RAG.*

**Why here:** S1-S8 built a data-dense platform with real intelligence (S9 scanner v3). Citizens can browse meetings, read summaries, see vote patterns, but they can't search. Basic text search ships first as a lightweight, zero-embedding-pipeline capability. RAG search follows with full semantic understanding. Feedback button rides along as low-cost, high-signal infrastructure for the public beta.

### ✅ S10.1 Basic Site Search (PostgreSQL Full-Text Search) [was S9.1]
- **Paths:** A, B
- **Description:** PostgreSQL-native full-text search using `tsvector`/`ts_rank` (built into Supabase). Search across agenda item titles, plain language summaries, vote explainers, meeting titles, official names. Search bar in the nav or a dedicated search page with faceted results (filter by date range, category, body). No embedding pipeline needed. Validates search UX (what people search for, how results should display) before investing in RAG. Corresponds to "basic search" in the free tier of the business model. When RAG ships (S9.2), basic search handles exact keyword matches while RAG handles semantic queries.
- **Depends on:** Existing structured data (met).
- **Publication:** Graduated (new interaction paradigm, validate result quality before public).
- **Status:** ✅ Complete. Migration 030 (GIN indexes + `search_site` RPC) applied to production. Dedicated `/search` page with debounced search, type filter pills, paginated results. API route with rate limiting (15/min/IP). Operator-gated via OperatorGate. Searches agenda items, motions (vote explainers), officials, commissions.

### S10.2 RAG Search (pgvector) [was S9.2/S8.1/B.1]
- **Paths:** A, B, C
- **Description:** Embedding pipeline for agenda items, summaries, explainers, and meeting content. pgvector search with SQL filtering (by date, category, council member, body). Semantic search UI augmenting S10.1's keyword search. Prerequisite for Charter compliance engine (B.11), stakeholder mapping (B.12), and cross-city comparison (B.16). Benefits from S8 completing the data source landscape: embedding templates designed once for all document types.
- **Depends on:** S1.4 (archive data in Document Lake), S8 (all data sources assembled).
- **Publication:** Graduated (new interaction paradigm, validate result quality before public).

### ✅ S10.4 Automated Data Quality Regression Suite (from AI Parking Lot, I6)
- **Paths:** A, B, C
- **Status:** ✅ Complete (2026-03-13)
- **Description:** Periodic database quality check that queries for known anti-patterns: sentinel strings in text fields, empty item_numbers with title prefixes matching `^[A-Z]\.\d+`, trailing commas in financial_amount, financial_amount values under $100 (suspicious for government contracts). Runs as a GitHub Action post-pipeline or on a schedule. Alerts when issues are found. Prevents the class of silent data quality regressions found in the March 2026 audit (6 issues accumulating undetected).
- **Implementation:** `src/data_quality_checks.py` with 9 SQL-based checks (sentinel strings, missing item numbers, negative amounts, suspicious low amounts, confidence-tier desync, missing FIPS, orphaned records, empty required fields, duplicate contributions). Canonical tier thresholds declared as `TIER_THRESHOLDS` constants. Standalone workflow (`.github/workflows/data-quality.yml`, daily 7am UTC cron) + post-pipeline step in `cloud-pipeline.yml`. Decision queue integration for issue alerting. 33 tests.
- **Publication:** Operator-only (infrastructure).

### ✅ S10.3 Natural Language Feedback Button [was S9.3/S8.2/H.18]
- **Paths:** A
- **Status:** Complete (2026-03-13)
- **Description:** Unobtrusive floating button for submitting ideas, bugs, and feedback in natural language. Submissions auto-routed to a structured parking lot for periodic bundled evaluation. Critical for public beta UX feedback loops. Low build cost, high signal value.
- **Implementation:** `FloatingFeedbackButton` component — persistent bottom-right chat bubble, inline expandable form (textarea + optional email), reuses existing `useFeedback` hook + `/api/feedback` endpoint with `feedback_type: 'general'`. Captures `page_url` for context. Migration 031 adds `page_url` column.
- **Publication:** Public (the mechanism itself; submissions are operator-only).
- Migration 031 applied to production.

---

## Sprint 11 — Information Design Overhaul

*How do we present all this data to people who don't follow city council?*

**Why here:** After S8 assembles all data sources, S9 fixes the intelligence engine, and S10 gives citizens a way to find data, S11 makes what they find legible. This is the "data-dense pot" problem: 237 meetings, 6,687 agenda items, 22K+ contributions, coalition matrices, pattern analysis. Powerful for an operator, overwhelming for a citizen. This sprint is about the meta-structure: how information-dense civic data communicates to lay people.

**Note:** This sprint is design-led, not pipeline-led. It may produce a design spec before code. User feedback from S10.3 and private beta informs the work.

### ✅ S11.1 Information Design Philosophy & Overarching Redesign [was S10.1/S9.1/H.10]
- **Paths:** A, B
- **Status:** ✅ Complete (2026-03-13). Design rules document (34 enforceable rules), navigation rethink, foundation components, progressive disclosure strategy all shipped. **Navigation:** Redesigned from 13 flat links to 5 grouped categories (Meetings, People, Money, Records, About) with dropdown menus, persistent search bar (C7), and responsive mobile hamburger menu. **Foundation components:** `CivicTerm` (C4: plain language + technical tooltip), `SourceBadge` (C6: tier + freshness + bias disclosure). **Design debt DD-002 resolved** (profile page T6 reorder).
- **Publication:** Infrastructure (design system and navigation).

### ✅ S11.2 Plain English UX Iteration [was S10.2/S9.2/H.14]
- **Paths:** A
- **Status:** ✅ Complete (2026-03-13). Meeting detail page: added quick stats bar (substantive items, consent calendar, votes recorded, split votes) signaling depth before detail (U4). Reports page: added plain English intro paragraph explaining what the reader is looking at, renamed tier headings from jargon ("Strong Patterns") to plain language ("Strongest Connections", "Notable Connections", "Possible Connections"), softened "Flags Found" to "Connections Found" throughout.
- **Publication:** Public (refinement of existing public features).

### ✅ S11.3 Council Bio Rework [was S10.3/S9.3/H.17]
- **Paths:** A
- **Status:** ✅ Complete (2026-03-13). Profile page reordered per T6 (non-adversarial framing): Layer 1 (identity/role context + factual profile) → Layer 2 (activity data: stats bar, voting record, campaign contributions with public records note) → Layer 3 (flagged findings: economic interests, financial connections). Financial connections section moved to bottom with visual separator and explicit "does not imply wrongdoing" framing. Donors section renamed to "Campaign Contributions" with provenance note.
- **Publication:** Public (T6-compliant reorder of existing data).

### ✅ S11.4 Financial Connections Per-Person View [was S10.4]
- **Paths:** A, B, C
- **Status:** Complete, **Operator-only**. Two views shipped: (a) Enhanced "Financial Connections" section on council profile pages (OperatorGate). (b) Standalone `/financial-connections` page (OperatorGate + nav hidden). Cross-references conflict flags with voting outcomes via the `conflict_flags → motions → votes` join path. Confidence thresholds centralized in `thresholds.ts` (Step 0). `is_current` filter bug fixed on existing queries. Gated because batch scan validation showed 21K flags with 1% coverage on actual abstentions. Scanner quality (entity matching precision) must improve before public graduation.
- **Description:** Surface financial connections on council member profile pages and as a standalone cross-member page. Currently conflict flags are organized by meeting (reports page), but the citizen's natural question is per-person ("what are this council member's financial entanglements?"). The data already exists (conflict_flags JOIN agenda_items JOIN votes JOIN officials). This is a view pivot, not new pipeline work.
- **Key metrics per official:** (1) Total financial connections flagged. (2) How many times they voted in favor of the connected party. (3) How many times they abstained on connected items (abstention on a flagged item is itself a signal). (4) Trend detection: are connections increasing, decreasing, or clustering around specific policy categories or time periods? All purely factual. "Councilmember X had 12 financial connections. They voted in favor 11 times, abstained once." No inference needed. The pattern speaks.
- **Two views:** (a) Per-member section on council profile page (this member's connections + voting pattern). (b) Standalone `/financial-connections` page showing all connections across all members (filterable by member, donor, category, vote outcome, time period). The standalone page is the "real signal through the noise" -- the single most important intelligence the system produces, currently buried in meeting-by-meeting reports.
- **Depends on:** Scanner operational with real data (met). S11.1 design philosophy (informs presentation, but a basic version doesn't need this).
- **Publication:** ~~Graduated~~ → ~~Public~~ → Operator-only (reverted 2026-03-07: batch scan validation showed scanner produces high noise / low signal. 21K flags, 1% abstention coverage). Scanner v2 precision improvements shipped 2026-03-07 (name_in_text, employer threshold, specificity scoring). **2026-03-09:** Root cause identified and fixed — `scan_meeting_db()` was a separate implementation missing all v2 precision filters. Rewritten to delegate to `scan_meeting_json()` via three data-fetching functions. DB mode now uses `meeting_attendance` for historical council member detection instead of `is_current=TRUE`. `--validate` mode added to `batch_scan.py` for before/after comparison. Batch rescan needed to validate improvement before re-graduation.
- **Threshold question:** Resolved. Confidence thresholds centralized in `web/src/lib/thresholds.ts`. Scanner intentionally uses different values (defense-in-depth per Q1 audit). Frontend thresholds now imported from single source.
- **Origin:** S7.3 judgment-boundary audit session, 2026-03-07.

### ✅ S11.6 Cross-Official Donor Overlap Interactive Selector [was S10.6]
- **Paths:** A, B
- **Status:** ✅ Complete (2026-03-13). `DonorOverlapSelector` component: pill-based multi-select of council members, instantly filters to donors who contributed to ALL selected officials. Shows shared donor count, total amount, per-recipient distribution. Table with `<caption>` for accessibility (C3). Placed on `/council/patterns` page above the existing full donor overlap table. Uses existing `DonorOverlap` data (no new queries needed).
- **Publication:** Public (on the already-public patterns page). Framing is neutral: "Contributing to multiple officials is common and does not imply coordination."
- **Origin:** Operator idea, 2026-03-07.

### ✅ S11.5 Controversial Votes Filter + Local Issue Categorization [was S10.5]
- **Paths:** A, B, C
- **Status:** ✅ Complete (2026-03-13). Two features shipped: (1) **Split votes filter** on `VotingRecordTable` — "Split votes only" checkbox with count badge. Parses `vote_tally` field (Noes/Abstentions patterns + N-N format) to detect non-unanimous votes. (2) **Local issue taxonomy** — `web/src/lib/local-issues.ts` defines 7 Richmond-specific political fault lines (Point Molate, Chevron, Police, Housing/Rent, Cannabis, Environment, Development) with keyword matching against agenda item titles. Tags appear on `AgendaItemCard` and `ControversyLeaderboard`. Taxonomy is a judgment call (operator-approved).
- **Publication:** Public. Filter is mechanical (non-editorial). Local issue tags are factual keyword matches with no editorializing.
- **Origin:** Design session idea, 2026-03-07.

---

## Sprint 12 — Citizen Experience v2: Plain Language & Comprehension

*Make meeting content actionable, not just available. Citizens should understand what they're reading and what it means for them.*

**Why now:** S3 shipped the initial plain language implementation. S11 redesigned the information architecture. But the *content quality* of summaries and the *display UX* of agenda text need a second pass informed by real standards. This sprint touches every meeting page and the home page — the highest-traffic surfaces. Higher citizen impact than RAG search (S10.2), which helps people who already know what they're looking for. This sprint helps people who are *browsing* — the primary behavior for a platform they've never seen before.

**Research dependency:** R7 (California Voter Guide + plain language standards research) must complete before the prompt rewrite. Operator runs research prompt in Claude Chat, results inform S12.3.

**Execution sequence:** Research → Prompt rewrite → Regenerate summaries → Frontend display improvements → Home page summary.

### ✅ S12.1 Plain Language Standards Research [from AI-PARKING-LOT R7]
- **Paths:** A, B, C
- **Status:** ✅ Complete (2026-03-16). Research synthesized from 5 authoritative frameworks: California Elections Code (§9085, §9051, §9087), Federal Plain Language Act / plainlanguage.gov, GOV.UK Content Design, Center for Civic Design, readability measurement science (SMOG, FK, Coleman-Liau). 14-rule framework produced. Saved to `docs/research/plain-language-standards.md`.
- **Publication:** Infrastructure (informs prompt rewrite).

### ~~S12.2 Plain English Summaries Expanded, Official Text Collapsed~~ [from AI-PARKING-LOT I41] — DROPPED
- **Status:** Dropped (2026-03-19). S14 Phase A completely redesigns AgendaItemCard with topic board layout and significance-based card sizing. The expand/collapse UX will be re-decided in that new context. Building it now is wasted effort.

### ✅ S12.3 Yes/No Vote Structure Prompt Rewrite [from AI-PARKING-LOT I44] — COMPLETE
- **Paths:** A, B, C
- **Status:** ✅ Complete (2026-03-21). R1 executed: 11,687 items regenerated via Batch API. 5 prompt iterations + readability tuning: complementary headline/summary design, infinitive verb headlines (tenseless), "if approved" conditionals, zero-context reader assumption, staff report integration, max 18 words/sentence. FK grade threshold relaxed to flag >14. 9,397 eSCRIBE attachments scraped (148 meetings), 5,275 loaded to DB. Frontend wired: headline as card header, summary in "In Plain English" box, official description under "Official Agenda Text". Item numbers and colored significance borders removed.
- **S14 cohesion (decided 2026-03-20):** R1 regeneration will also produce a `summary_headline` field (~15-20 words, one sentence) alongside the full summary. S14-A needs short-form summaries for compact topic board cards (A1), hero item teasers (A3), and category drill-through cards (B6). Generating both outputs in one pass avoids a separate $20-30 regeneration later.
- **Depends on:** ✅ S12.1 (research).
- **Publication:** Public (updates existing public summaries). Prompt voice/framing change = judgment call per judgment-boundaries.md — **approved 2026-03-16**.

### S12.4 Official Agenda Text Formatting [from AI-PARKING-LOT I42, H.11] — DEFERRED TO S14
- **Paths:** A
- **Description:** Government agenda descriptions currently render as a single `<p>` tag. Add structure: detect paragraph breaks, WHEREAS/RESOLVED clauses, numbered conditions, financial breakdowns. Frontend smart renderer + pipeline-side structured extraction for new meetings.
- **Status:** Deferred into S14 Phase A (2026-03-19). The formatting logic survives but the display component will be built as part of the new topic board card design. Building the component now means rebuilding it in S14.
- **Publication:** Public (formatting improvement on existing public data).

### ~~S12.5 Meeting-Level 5-Bullet Summary for Home Page~~ [from AI-PARKING-LOT I43, H.15] — DROPPED
- **Status:** Dropped (2026-03-19). S14 A3 (hero item pattern) is a better, more targeted replacement — highlights the most contested item by objective signals (split votes, pulled-from-consent, campaign finance records) instead of a generic 5-bullet summary.

### S12.6 "Official Agenda Text" Label ✅
- **Paths:** A
- **Status:** ✅ Complete (2026-03-16). Added "Official Agenda Text" label to `AgendaItemCard.tsx` matching the "In Plain English" label style. Citizens can now distinguish AI summary from official text.
- **Publication:** Public.

---

## Sprint 13 — Influence Transparency

*Make corporate influence in local government visible by cross-referencing public databases that nobody currently wires together. The information exists. Nobody connects the dots. Richmond Commons does.*

**Why now:** The Flock Safety contract vote (2026-03-17) demonstrated live astroturfing in Richmond — out-of-town speakers, suspicious organizations appearing at multiple Bay Area councils, sudden grassroots mobilization coordinated with vendor marketing. The existing conflict scanner (S9) detects donor-vendor relationships; this sprint extends it into a full influence transparency layer that traces funding chains, entity relationships, and coordination patterns across public databases. Promotes and extends B.45, B.46, B.47.

**Framing:** Public layer presents factual connections narratively per D6 ("This organization was registered 12 days before the council vote, shares a registered agent with a PR firm whose client list includes [vendor]"). Interpretive analysis (astroturf pattern flagging) stays operator-only. The platform tells the factual story; editorial interpretation is for journalists and the operator layer.

**Paths:** A, B, C (triple-path — citizen transparency + scales to 19K cities + data infrastructure)

### ✅ S13.1 FPPC Form 803 (Behested Payments) Pipeline
- **Paths:** A, B, C
- **Status:** ✅ Complete (2026-03-20). `fppc_form803_client.py` (API search + HTML scrape fallback), `load_behested_to_db()` in `db.py`, `sync_form803_behested()` in `data_sync.py`, migration 044 (`behested_payments` table + `v_behested_by_official` view), `signal_behested_payment()` scanner detector (triangulation: payor/payee in agenda text × official request chain), staleness monitoring (90-day threshold), city config entry. 40 tests (shared with S13.3). Migration 044 applied. Syncs executed.
- **Description:** Ingest FPPC behested payment disclosures — payments made at the request of elected officials. When a council member "suggests" a vendor donate to a community org, Form 803 captures it. Dual-strategy access: FPPC API search endpoint with HTML scrape fallback. Cross-reference with vendor contracts and council votes via scanner signal detector.
- **Depends on:** B.46 MVP-1 (entity resolution schema — done)
- **Publication:** Graduated (data is Tier 1 official records, but cross-referencing is analytical)

### S13.2 OpenCorporates Entity Resolution (B.46 MVP-2)
- **Paths:** A, B, C
- **Description:** Business entity resolution via OpenCorporates API (aggregates from CA SOS). Replaces blocked CA SOS API with same data through different access path. `opencorporates_client.py`: company search, officer lookup, `resolve_entity()` high-level pipeline. Rate limiter (50/day, 200/month free tier), DB-backed API usage tracking, 90-day cache TTL. Schema: `business_entities` + `business_entity_officers` + `entity_name_matches` bridge table + `opencorporates_api_usage`. 91 entity-like donors identified in NetFile data (~$454K total), initial backfill viable in 2 days at free tier limits. Name normalization with token-based similarity scoring (auto-match ≥0.80, review queue 0.60-0.80). ODbL share-alike applies to entity data only.
- **Depends on:** OpenCorporates API key approval (applied 2026-03-22, ref OCESD-60029)
- **Publication:** Infrastructure (feeds entity graph, conflict scanner signals)
- **Status:** Client + schema + tests built (49 tests). Awaiting API token to activate.

### ✅ S13.3 Richmond Lobbyist Registration Records
- **Paths:** A, B
- **Status:** ✅ Complete (2026-03-21, pipeline rewrite). `lobbyist_client.py` rewritten: PDF download by Document ID + Claude Vision extraction (replaced broken HTML scraper that returned 0 results due to JS-rendered Document Center). 48 lobbyist registrations extracted (27 from 2014-2025 PDF, 21 from 2000-2013 PDF). `load_lobbyists_to_db()` in `db.py`, `sync_lobbyist_registrations()` in `data_sync.py`, migration 044 (`lobbyist_registrations` table + `v_lobbyist_clients` view), `signal_unregistered_lobbyist()` scanner detector, staleness monitoring (90-day threshold), city config with document IDs. 54 tests. Dual data source: local City Clerk PDFs + state SOS. **Human action:** Run `python data_sync.py --source lobbyist_registrations --sync-type full` to load 48 records.
- **Description:** Ingest lobbyist registration data from Richmond Municipal Code Chapter 2.54 ("Regulation of Lobbyists"). Three lobbyist types (contract, business/org, expenditure). Paper/PDF filings in City Clerk Document Center (FID=389). Small dataset, high signal. The *absence* of registration by vendor representatives who are influencing procurement is itself a finding. Cross-reference registered lobbyists against vendor contracts, council meeting speakers, and FPPC filings.
- **Depends on:** None
- **Publication:** Public (registration records are Tier 1)

### S13.4 Cross-Jurisdiction Speaker Tracking
- **Paths:** A, B, C
- **Description:** Track speakers appearing at multiple Bay Area city council meetings on the same topic. Start with Richmond + Oakland (Legistar) + San Francisco (SFGOV). Same person speaking at 4+ councils on surveillance cameras in the same month = coordination signal. Requires speaker name normalization and fuzzy matching across jurisdictions. Extends existing speaker extraction from Richmond minutes.
- **Depends on:** S13.2 (entity resolution for speaker-to-org matching, but can start with name-only)
- **Publication:** Graduated (factual presentation of speaker appearances, but cross-jurisdiction analysis is new)

### S13.5 Influence Scanner: Astroturf Pattern Detectors
- **Paths:** A, B, C
- **Description:** Extend conflict scanner v3's signal architecture with astroturf-specific detectors: (1) `signal_org_formation_timing()` — org registered proximate to procurement decision. (2) `signal_address_clustering()` — entities sharing registered agents or physical addresses with vendors. (3) `signal_cross_jurisdiction_deployment()` — same speakers/orgs at multiple councils. (4) `signal_funding_chain()` — vendor → 501(c)(4) → advocacy org → council speakers. (5) `signal_behested_payment_loop()` — vendor donates to org at official's behest, org mobilizes support for vendor's contract. Each returns `list[RawSignal]`, plugs into composite confidence. Extends B.47 (Influence Pattern Taxonomy).
- **Depends on:** S13.1-S13.4 (data sources), S9 (signal architecture — done)
- **Publication:** Operator-only (interpretive analysis layer)
- **Status:** ✅ `signal_behested_payment_loop()` complete (2026-03-21) — multi-hop influence cycle detector cross-referencing contributions + behested payments + agenda text, with optional lobbyist registration corroboration (4th source). 16 tests. Remaining 4 detectors blocked on S13.2 (CA SOS API key) or S13.4 (cross-jurisdiction speakers).

### ~~S13.6 Influence Transparency Frontend~~ → Absorbed by S14
- **Status:** Dropped (2026-03-21). Entity profile pages, factual narrative connections, and astroturf pattern flags all absorbed into S14's unified influence map frontend (S14-C item center, S14-D official center, S14-F entity center). Same design language (D6 sentence-based narrative), same data sources — building S13.6 separately would create a parallel frontend that S14 immediately replaces. S13 is now a pure pipeline/scanner sprint.

---

## Sprint 14 — Influence Map + Meetings Redesign (Discovery & Depth) ✅

*Unify fragmented data surfaces into a single user journey. Discovery layer (meetings redesign) feeds into depth layer (influence map). Sentence-based narrative replaces tables. Two centers: agenda item and official.*

**Spec:** `docs/specs/influence-map-meetings-redesign-spec.md`
**Research:** 6 sessions completed (A–F). Synthesis at `docs/research/s14-research-synthesis.md`.
**Depends on:** S9 (complete), S11 (complete), S13 (complete)
**Publication tier:** Graduated (all phases operator-only until validated)

**S12 overlap (resolved 2026-03-19):** S12.2 dropped (S14 Phase A redesigns AgendaItemCard). S12.4 deferred into S14 Phase A (formatting logic survives, component rebuilt). S12.5 dropped (S14 A3 hero item pattern is a better replacement). S12.3 regeneration is the only remaining standalone S12 work item.

**S13 overlap (resolved 2026-03-21):** S13.6 (Influence Transparency Frontend) absorbed into S14. Entity profile pages become S14-F (Entity Center) — third center alongside item (S14-C) and official (S14-D). Astroturf pattern flags surface in all three centers behind OperatorGate. S13 is now a pure pipeline/scanner sprint.

**Topic navigation integration (decided 2026-03-22):** Spec from Chat (`docs/specs/topic-navigation-spec.md`) proposes topic-centric browsing with contributor classification and connection density. Integration: Phase 1 (contributor classification via `entity_Cd` mapping) folded into S14 as pipeline prep (S14-P). Phase 2 (topic timeline) enriches B6 (category drill-through) with financial connection overlay. Phase 3 (connection density rankings) deferred — needs framing review before public-tier. **Dynamic topic discovery:** Hybrid approach (Option C) — LLM extraction at ingestion time ("identify the specific civic issue or project") + operator curation. Junction table (`topics` + `item_topics`) for stable IDs, merge/rename, lifecycle tracking. Categories remain the structural taxonomy; topics are the emergent layer on top.

### S14-P: Pipeline Prep (Contributor Classification + Dynamic Topics)
- **Paths:** A, B, C
- **Description:** Two pipeline additions before frontend work. (1) **Contributor type classification:** Map NetFile `entity_Cd` / CAL-ACCESS `ENTITY_CD` to 5-type enum (Corporate, Union, Individual, PAC/IE Committee, Other). New column on contributions or lookup table. Ambiguous classifications (LLCs) get lower confidence, stay operator-only. (2) **Dynamic topic discovery:** Add `topics` + `item_topics` junction table. Extend extraction prompt to identify specific civic issues/projects per agenda item. Operator curation layer for merge/rename/promote. Categories = structural taxonomy, topics = emergent layer.
- **Depends on:** None.
- **Publication:** Infrastructure (feeds B6 financial overlay + future topic pages).
- **Spec:** `docs/specs/topic-navigation-spec.md`
- **Status (S14-P1 — Contributor Classification):** ✅ Complete (2026-03-22). `contributor_classifier.py`: dual-path classification — (1) authoritative from CAL-ACCESS `ENTITY_CD` (IND→individual, COM/PTY/SCC→pac_ie, OTH→name-disambiguated), (2) inferred from name patterns for NetFile (which has no entity type field). Union > PAC > Corporate > Individual priority. `contributor_type`, `contributor_type_source`, `entity_code` columns added to `contributions` (migration 048). `load_contributions_to_db()` classifies on ingest. Backfill regex in migration for existing records. 51 tests. **Finding:** NetFile API has no `entity_Cd` field — spec assumption was wrong. All NetFile classification is name-pattern inference.
- **Status (S14-P2 — Dynamic Topics):** ✅ Complete (2026-03-22). `topics` + `item_topics` junction tables (migration 049). 14 Richmond local issues seeded (matching `web/src/lib/local-issues.ts`). `topic_tagger.py`: keyword-based topic assignment with confidence scoring (1 keyword = 0.8, 2+ = 1.0), multi-topic support, CLI backfill (`python topic_tagger.py [--dry-run] [--limit N]`). DB helpers for loading + querying. `v_topic_stats` view for item counts and date ranges. 29 tests. Topics are the emergent layer on top of categories (structural taxonomy). Future: LLM extraction at ingestion time for discovering topics beyond the keyword list.

### S14-A: Meeting Detail Redesign
- **Paths:** A, B, C
- **Description:** Topic board layout (category-grouped sections), significance-based card sizing (split votes prominent, consent items compact), hero item pattern (most contested item featured at top), local issue filter bar, meeting type 3-channel encoding, entity type visual system. Absorbs S12.4 (agenda text formatting).
- **Depends on:** None (existing data sufficient).
- **Publication:** Graduated.

### S14-B: Meeting Discovery — ✅ COMPLETE
- **Paths:** A, B, C
- **Description:** Redesign `/meetings` index. Grouped agenda list as primary view (not calendar grid — research found grids underperform at 2 meetings/month). Mini-calendar as secondary navigation. "Next Meeting" persistent card. Category drill-through pages. Calendar grid available as toggle.
- **Depends on:** S14-A (reuses AgendaItemCard).
- **Publication:** Graduated.
- **Status (2026-03-22):** All items complete. B1 (NextMeetingCard), B2 (MeetingAgendaList + MeetingListCard month-grouped accordion), B3 (MiniCalendar sidebar with meeting type dots), B4 (inline meeting expansion — Radix Collapsible on MeetingListCard, expanded preview shows full category breakdown, vote summary, campaign finance details, "View full meeting" link), B5 (CalendarGrid toggle), B6 (category drill-through `/meetings/category/[slug]`). Infrastructure: nuqs URL state (`?month=`), date-fns calendar math, NuqsAdapter in root layout, getMeetingFlagCounts() query, getAgendaItemsByCategory() query.

### S14-C: Influence Map — Item Center — ✅ COMPLETE
- **Paths:** A, B, C
- **Description:** New `/influence/item/[id]` page. Sentence-based contribution narrative (contribution first, vote second). Multi-level disclaimer system. Contextual data per record (% of fundraising, vote alignment, counter-examples). Methodology page at `/influence/methodology`. Required contextual data queries add complexity beyond existing conflict scanner output.
- **Depends on:** S14-A (card components), S9 (scanner data).
- **Publication:** Graduated.
- **Status:** ✅ Complete (2026-03-22). Page structure, disclaimers, methodology, entry points, related decisions all complete. **Narrative enrichment fix (2026-03-22):** Root cause was `buildContributionNarratives()` only processing `campaign_contribution` flags (181 = 1.6%), while `donor_vendor_expenditure` (9,912 = 86%) and `llc_ownership_chain` (1,377 = 12%) were excluded. Fix: added all three flag types to the filter, multi-strategy donor matching (exact name → employer groups → substring), employer aggregation for vendor-to-employer matches, vendor expenditure context sentences. Coverage: 1.6% → 100% of published flag types.

### S14-D: Influence Map — Official Center + Index — ✅ D1-D3 COMPLETE
- **Paths:** A, B, C
- **Description:** Restructure council profile campaign finance section to narrative sentences. New `/influence` index replacing `/financial-connections`. Nav restructure (Money → Influence). Transparency reports page eliminated (absorbed into item influence maps).
- **Depends on:** S14-C (sentence templates, disclaimer system).
- **Publication:** Graduated.
- **Status (2026-03-22):** D1-D3 complete. **D1:** Council profile "Financial Connections" table replaced with `OfficialInfluenceSection` — groups flags by agenda item, links to `/influence/item/[id]`, uses `CampaignFinanceDisclaimer`, show-more pagination (5 items default). **D2:** `/influence` index page with summary stats (total records, officials with records, strong confidence count), per-official cards with confidence breakdown badges (strong/moderate/low) and vote pattern summary. **D3:** Nav "Money" → "Influence", `/financial-connections` → `/influence`, "Financial Connections" → "Influence Map". All operator-gated. TypeScript clean (zero errors).

### S14-E: Polish + Cross-Linking — ✅ COMPLETE
- **Paths:** A, B, C
- **Description:** Bidirectional navigation with entity type visual indicators. Recently visited panel. Persistent search bar. Methodology page implementation. CalMatters-style comparative framing on official profiles (percentile rank).
- **Depends on:** S14-C, S14-D.
- **Publication:** Graduated.
- **Status (2026-03-22):** All items complete. E1 (methodology back link fix → /influence), E2 (influence item page breadcrumb → Influence Map link), E3 (influence index: direct item links with confidence badges per official card), E4 (recently visited panel — localStorage-based history tracking with `useRecentlyVisited` hook, `RecordVisit` auto-recorder on meeting/influence/council pages, `RecentlyVisitedPanel` sidebar on influence + council pages), E5 (CalMatters-style comparative framing — `getOfficialComparativeStats` query ranks officials by donor count + total fundraising, `ComparativeContext` component renders percentile sentences on council profiles).

---

## Sprint 15 — Pipeline Autonomy (Scheduled Sync Infrastructure) ✅

*Every data pipeline runs on a cadence. No manual runs. Nothing can rely on a human remembering to sync.*

**Why this sprint:** Manual pipeline execution is a single point of failure. If the operator is busy, data goes stale silently. Every pipeline — from NetFile contributions to lobbyist registrations — needs an automated cadence with failure notifications. The staleness monitor becomes a verification layer, not the primary trigger.

**Paths:** A, B, C (triple-path — citizen freshness + scales to 19K cities + infrastructure)

### ✅ S15.1 GitHub Actions Scheduled Sync Workflows
- **Paths:** A, B, C
- **Status:** ✅ Complete (2026-03-21). Four-tier cadence in `data-sync.yml`: **Daily** (7am UTC): nextrequest (CPRA compliance). **Weekly** (Mon 8am UTC): archive_center, minutes_extraction, escribemeetings, netfile, nextrequest, socrata_expenditures, socrata_payroll. **Monthly** (15th 9am UTC): calaccess + socrata_permits + socrata_licenses + socrata_code_cases + socrata_service_requests + socrata_projects. **Quarterly** (1st Jan/Apr/Jul/Oct 10am UTC): form700, form803_behested, lobbyist_registrations, propublica. All 17 active sources scheduled (courts excluded — dormant/CAPTCHA). Manual dispatch dropdown covers all sources. `if: always()` on each step for failure isolation.
- **Publication:** Infrastructure (operational)

### ✅ S15.2 Sync Health Dashboard (Operator)
- **Paths:** A, B
- **Status:** ✅ Complete (2026-03-21). `/operator/sync-health` page (OperatorGate-protected). Summary cards (total sources, stale count, failures in 30d, total syncs). Per-source table with freshness bars (visual % of threshold), last sync time, status, failure count, records fetched, cadence badge. Expandable rows show recent run history with status dots. Group-by-cadence toggle. API at `/api/operator/sync-health` queries `data_sync_log` for 90 days. Nav links added (desktop + mobile, OP-badged). Staleness monitor gains `propublica` threshold (120 days).
- **Publication:** Operator-only (permanent)

### ✅ S15.3 Failure Recovery & Retry Logic
- **Paths:** B, C
- **Status:** ✅ Complete (2026-03-21). `run_sync()` retries up to `max_retries` (default 2) on transient failures: ConnectionError, TimeoutError, OSError, HTTP 5xx. Exponential backoff (30s, 60s, 120s max). Connection refreshed between retries. Non-transient errors fail immediately. Retry count logged in sync_log metadata + pipeline journal. `--max-retries` CLI arg added. GitHub Actions already sends failure notifications by default. Each scheduled step uses `if: always()` for graceful degradation. 2 new tests.
- **Publication:** Infrastructure

---

## Public/Operator Split — Publication Tier Enforcement ✅

*Clean separation between the public experience and the operator beta. Public site = meetings + council + about. Everything else operator-only until validated.*

### ✅ Public Nav Reduction
- **Paths:** A, B
- **Status:** Complete (2026-03-23). Nav gated: Topics & Trends, Coalitions, Commissions, Influence Map, Donor Patterns, Transparency Reports, Public Records, Data Quality all `operatorOnly: true`. Public users see 3 direct links (Meetings, Council, About) instead of 5 dropdown groups.

### ✅ Page-Level OperatorGate
- **Paths:** A, B
- **Status:** Complete (2026-03-23). 9 pages wrapped in OperatorGate: reports, reports/[meetingId], public-records, commissions, commissions/[id], council/stats, council/coalitions, council/patterns, data-quality. Direct URL access returns empty for non-operators.

### ✅ Scanner Results Gated on Public Pages
- **Paths:** A
- **Status:** Complete (2026-03-23). Meeting detail: conflict flag callout banner, RecordVisit tracking, per-item flag counts, HeroItem campaign finance link — all gated. MeetingsDiscovery passes empty flag counts to public users. AgendaItemCard hides campaign contribution links for non-operators.

### ✅ Design Sweep (Public Pages)
- **Paths:** A
- **Status:** Complete (2026-03-23). Page headings bumped to text-4xl, body text to text-lg, stat cards enlarged with more padding. Split vote count color changed from amber (alarming) to slate-600 (neutral/informational). Consistent py-10 page padding.

### ✅ Government Entity Employer Filter (Scanner)
- **Paths:** A, C
- **Status:** Complete (2026-03-23). Fixed false positives where "city of richmond" as donor employer matched every agenda item. Added `_is_government_entity()` check before employer-to-entity matching in both retrospective scan paths. The prospective path (signal_campaign_contribution) already had an extensive inline employer filter.

---

## Launch Arc — S16 → S17 → S17B → S18

*The final push before sharing. Every item serves the public experience on Meetings, Council, and About. Culminates in richmondcommons.org going live.*

**Context:** Pre-launch audit (2026-03-24) found all public pages functionally complete with no TODOs, placeholder content, or broken components. The gaps are content quality (meeting cards show generic categories, not specific subjects) and launch infrastructure (no OpenGraph, no sitemap, no custom domain). S16 and S17/S17B close those gaps. Only S16.4 (batch topic label generation) and S18 (go-live) remain.

### Sprint 16 — Content That Clicks

*Make every meeting card and detail page tell you what it's actually about.*

**Why this sprint:** "Budget" on a meeting card tells you nothing. "Point Molate" tells you everything. The current category taxonomy says what *type* an item is but not what it's *about*. Topic labels are the single highest-impact content improvement for citizen comprehension.

**Paths:** A, B, C (citizen clarity + scales to 19K cities + data infrastructure)

#### ✅ S16.1 Topic Labels (AI-PARKING-LOT I56)
- **Paths:** A, B, C
- **Status:** ✅ Complete (2026-03-24). Migration 055 adds `topic_label VARCHAR(50)` to `agenda_items`. LLM extracts 1-4 word specific subjects per agenda item (e.g., "Point Molate", "SEIU MOU", "Baxter Creek Restoration"). Seed-based consistency: curated topic names + prior generated labels passed to LLM prompt so it reuses labels for recurring subjects. Pipeline wired for sync (`generate_summaries.py`) and batch (`batch_summarize.py` with `--topic-only` and `--skip-labeled` flags). Display gated by item significance (split votes, hero, pulled, public comments) on AgendaItemCard and HeroItem. 25 tests.
- **Publication:** Public.

#### ✅ S16.2 Plain English Expanded by Default (AI-PARKING-LOT I41)
- **Paths:** A
- **Status:** ✅ Already implemented. `ExpandableOfficialText` defaults to collapsed; plain language summary is the primary visible content when expanded.
- **Publication:** Public.

#### ✅ S16.3 Category Badge Fix
- **Paths:** A
- **Status:** ✅ Complete (2026-03-24). NextMeetingCard now uses `CategoryBadge` components with color-coding instead of plain text.
- **Publication:** Public.

#### S16.4 Topic Label Regeneration
- **Paths:** A, B, C
- **Description:** Batch API pass to extract topic labels for ~12K agenda items. Seed-based: curated topic names seeded into prompt for consistency. `--skip-labeled` to only process items without labels, `--topic-only` to import only topic_label (preserves existing R1 summaries). Estimated ~$40 (Batch API 50% discount), less if curated backfill covers a large fraction.
- **Depends on:** ✅ S16.1 (schema + prompt). Needs migration 055 applied.
- **Publication:** Infrastructure.
- **Human action:** `supabase db push` then run backfill sequence: `python topic_tagger.py tag` → `python topic_tagger.py labels` → `python batch_summarize.py export --skip-labeled` → `submit` → `import --topic-only`.

### Sprint 17 — Experience Polish ✅

*Every surface a first-time visitor touches should feel finished.*

**Paths:** A, B

#### ✅ S17.1 Official Agenda Text Formatting (S12.4)
- **Paths:** A
- **Status:** ✅ Complete. Smart renderer in `web/src/lib/format-agenda-text.ts` (465 lines): detects WHEREAS/RESOLVED clauses, numbered conditions, section headers (FINANCIAL IMPACT, DISCUSSION, BACKGROUND), paragraph breaks. Multi-zone parsing for clean eSCRIBE text vs. messy PDF-extracted staff reports. `ExpandableOfficialText.tsx` renders parsed segments with semantic HTML.
- **Publication:** Public.

#### ✅ S17.2 OpenGraph + Social Meta Tags
- **Paths:** A
- **Status:** ✅ Complete. Root metadata in `layout.tsx` (og:title, og:description, og:url, og:siteName, twitter:card=summary_large_image, metadataBase=richmondcommons.org). Per-page `generateMetadata` on all dynamic routes: council/[slug], meetings/[id], meetings/[id]/items/[itemNumber], commissions/[id], reports/[meetingId], influence/item/[id], influence/elections/[id], meetings/category/[slug].
- **Publication:** Public.

#### ✅ S17.3 SEO Infrastructure
- **Paths:** A, B
- **Status:** ✅ Complete. `web/src/app/robots.ts` (allow all, disallow /api/ and /operator/, sitemap reference). `web/src/app/sitemap.ts` (database-driven: static pages + dynamic meetings/agenda items/council profiles with priority and changeFrequency).
- **Publication:** Public.

#### ✅ S17.4 Custom 404 Page
- **Paths:** A
- **Status:** ✅ Complete. `web/src/app/not-found.tsx` with civic-themed design, "Page not found" heading, three navigation CTAs (home, meetings, council) in civic-navy design system colors.
- **Publication:** Public.

#### ✅ S17.5 Responsive + Search Polish
- **Paths:** A
- **Status:** ✅ Complete. FloatingFeedbackButton `max-w-[calc(100vw-2rem)]` safety. Search quality verified.
- **Publication:** Public.

### Sprint 17B — Election Cycle Accuracy ✅

*Election history, term dates, district display, and candidacy status on council cards and profiles.*

**Paths:** A, B, C

#### S17B.1 Populate election_candidates ✅
- Researched and populated all Richmond district-era elections (2020, 2022, 2024) with winners. Added 2026 candidacies including Claudia Jimenez for Mayor. Term dates set for all 7 current officials.

#### S17B.2 Election history on council cards + profiles ✅
- Council listing cards show district, term end date, and "Running for Mayor" / "Running for re-election" badges. Profile pages show full election history (all races won, upcoming filings). Cross-office candidacy (council → mayor) handled.

#### S17B.3 Category sort fix + comment type scoping ✅
- "Other" renamed to "Miscellaneous" with tiebreaker sort (only sinks when controversy scores are tied). Public comment type separation (in-person vs. written) scoped as I69 for post-launch.


### Sprint 18 — Go Live (richmondcommons.org)

*Point the domains. Final sweep. Ship it.*

**Paths:** A, B, C

#### S18.1 Domain Setup
- **Paths:** A, B
- **Description:** Primary domain: `richmondcommons.org` CNAME → Vercel. All other domains 301 redirect to `.org` (canonical). Email forwarding: `hello@richmondcommons.org` via Cloudflare Email Routing.
- **Domains (all on Cloudflare):**
  - `richmondcommons.org` — **primary**, CNAME to `cname.vercel-dns.com` + add in Vercel dashboard
  - `richmondcommons.com` — 301 redirect to richmondcommons.org (Cloudflare redirect rule)
  - `richmondcommon.org` — 301 redirect (typo protection)
  - `richmondcommon.com` — 301 redirect (typo protection)
  - `civiccommon.org` — 301 redirect (future brand)
  - `civiccommon.com` — 301 redirect (future brand)
  - `citycommons.org` — 301 redirect (future brand)
- **Depends on:** S17.2, S17.3 (meta tags and sitemap reference the domain).
- **Publication:** Infrastructure.
- **Human action:** Cloudflare DNS + redirect rules for all 7 domains, Vercel dashboard domain addition, Cloudflare Email Routing for hello@richmondcommons.org.
- **Status:** ✅ Complete (2026-03-28). DNS configured, site live at richmondcommons.org.

#### S18.2 Security Headers ✅
- **Paths:** A, B, C
- **Description:** Add security headers to `web/next.config.ts`: X-DNS-Prefetch-Control, X-Frame-Options (DENY), X-Content-Type-Options (nosniff), Referrer-Policy (strict-origin-when-cross-origin), Permissions-Policy, Strict-Transport-Security (HSTS with preload).
- **Depends on:** Nothing.
- **Publication:** Infrastructure.

#### S18.3 Social Preview Image ✅
- **Paths:** A
- **Description:** OG image for social shares. Text-based: civic navy gradient, amber accent line, "Richmond Commons" + tagline + topic labels (Council Votes, Campaign Finance, Public Meetings). Next.js edge runtime generation (`opengraph-image.tsx`), 1200x630px, auto-discovered by metadata API.
- **Depends on:** Nothing.
- **Publication:** Public.
- **Status:** ✅ Complete (2026-03-28). Operator approved text-based design.

#### S18.4 Version Bump + Final Sweep ✅
- **Paths:** A
- **Description:** Version bump 0.1.0 → 1.0.0 in package.json. Visual sweep of public pages (homepage, meetings, council, profiles, about) on desktop + mobile. Fixed duplicate Mayor/seat display on profiles.
- **Depends on:** S18.1 (full verification on production domain).
- **Publication:** Public.

---

## Pre-Launch — S19: Content Depth

*Pulled into pre-launch (2026-03-25). Deeper meeting content and scanner improvements.*

| Item | Source | Description |
|------|--------|-------------|
| ✅ Post-Meeting Minutes Discovery | Session | `escribemeetings_minutes` sync source discovers adopted minutes PDFs by scanning eSCRIBE document IDs (sequential HEAD requests on FileStream.ashx). Initial run linked 27 meetings to minutes URLs. Runs weekly in GitHub Actions. |
| ✅ Minutes Extraction Backfill | Session | Originally scoped as 23 meetings; expanded to 104 meetings with minutes URLs but 0 votes. Investigation found: 32 were commission minutes (Rent Board, Design Review, Personnel Board) incorrectly linked to CC meetings — cleaned up (minutes_url cleared). 11 were public comment compilations — cleaned up. 55+ were genuine CC special meetings (closed sessions, swearing-in, joint meetings) that correctly have 0 or minimal votes. 101 PDFs downloaded to Layer 1, 67 extracted (8 comment compilations auto-skipped), ~70 new agenda items + votes added. Cost: ~$2.50. |
| ✅ I43 Meeting-Level Summary | AI-PL | 3-5 bullet narrative summary on LatestMeetingCard + meeting detail "What happened" section. Migration 060 adds `meeting_summary TEXT` on `meetings`. Generator: `generate_meeting_summaries.py` (Claude Sonnet, --limit/--force/--dry-run). Prompt: `prompts/meeting_summary_system.txt`. Frontend: bullets on home page card + detail page with AI-generated disclosure. 8 tests. **Pipeline run (2026-03-25):** 698/840 generated in initial run. 144 remaining generated in S19 backfill session. |
| I45 Proceeding Type Classification | AI-PL | Entitlement/legislative/contract/appointment per agenda item. Gating capability for scanner v4. Not user-facing — deferred to post-launch. |
| ✅ D27 Self-Contribution Filter | AI-PL | Audit logging for self-donation suppressions. Self-donation checks added to both temporal correlation functions (v2 + v3). 4 new tests. |
| ✅ D17 Retrospective Scanner Dedup | AI-PL | `signal_temporal_correlation` now uses shared `get_time_decay_multiplier()` + `TIME_DECAY_WINDOWS` instead of hardcoded factors. Single source of truth for temporal decay logic. |
| ✅ D23 Levine Act Threshold Update | AI-PL | `get_levine_act_threshold()` returns $250 pre-2025, $500 post-2025 (SB 1243). Permit donor signal surfaces correct threshold in legal_reference and match_details. 5 tests. |
| ✅ D28 Category Recategorization Pass | Session | **Complete (2026-03-26).** Root cause: `categorize_item()` keyword matcher had ordering bugs — proclamation was a governance keyword, appointments/litigation/proclamation categories missing from list entirely, "amendment" too broad for contracts. Fix: (1) `categorize_item()` rewritten with correct priority ordering. (2) Full LLM recategorization of 11,645 items via Batch API (`batch_recategorize.py`). 4,460 items changed (38%): governance→proclamation 145, infrastructure→contracts 617, public_safety→contracts 423, other→real categories 770, 5 non-standard categories normalized. 99.98% success rate. Cost: ~$6. |
| S13.2 Entity Resolution | Parking lot | OpenCorporates integration (API key pending). |

---

## Pre-Launch — S20: Public Comment Pipeline (YouTube Transcripts)

*Accurate per-item public comment counts are a pre-launch requirement. The existing minutes-based extraction misses ~80% of item-specific comments because `agenda_item_id` linkage fails. YouTube transcripts provide the ground truth: the chair announces speaker counts and item transitions clearly.*

**✅ No longer blocking S18.** Per-item comment counts were disabled 2026-03-26, restored 2026-03-27 via YouTube + Granicus transcript pipelines. 201 agenda items across 71 meetings now have verified speaker counts.

**Data source:** KCRT TV YouTube channel (`UCJ0TqQHWE4uaC7xI1TkRdRA`). 16 regular council meetings from Oct 2025 – Mar 2026 with auto-generated transcripts. Older meetings available back to 2020 (sporadic).

**Validated approach (2026-03-26 prototype):** Single Sonnet API call per meeting transcript (~125K tokens). Returns JSON: speaker count + methods per agenda item + open forum. March 3 test: correctly identified 55 speakers on Flock item (W.1), 11 open forum, 2 on V.1, 1 on V.2. Cost: $0.38/meeting. Estimated total for 16 recent meetings: ~$6.

### S20.1 YouTube Transcript Pipeline
- **Paths:** A, B, C
- **Description:** `youtube_comments.py` CLI with subcommands: `discover` (find council meeting videos on KCRT channel, match to meetings by date), `fetch` (download auto-generated VTT via yt-dlp, deduplicate progressive cues, output clean timestamped text), `extract` (send transcript + agenda items to Claude API, parse speaker counts per item), `import` (update `public_comment_count` on `agenda_items` + store raw extraction in `public_comments` table or new `comment_counts` table).
- **Depends on:** yt-dlp (pip install). ANTHROPIC_API_KEY in .env.
- **Publication:** Infrastructure (pipeline tool).

### S20.2 Backfill Recent Meetings
- **Paths:** A
- **Description:** Run pipeline on 16 KCRT meetings (Oct 2025 – Mar 2026). Validate counts against minutes-extracted comments where both exist. Write results to `agenda_items.public_comment_count`. Estimated cost: ~$6.
- **Depends on:** S20.1.
- **Publication:** Data (feeds existing frontend components).

### S20.3 Restore Per-Item Comment Display
- **Paths:** A
- **Description:** Un-zero `public_comment_count` in queries.ts (3 locations marked with "Restore with:" comments). HeroItem "Most Discussed" selection, TopicBoard sort, comment badges, item detail page spoken/written breakdown all come back automatically. Verify on March 3 meeting that Flock shows 55 comments.
- **Depends on:** S20.2 (backfill complete and verified).
- **Publication:** Public.
- **Frontend code to restore (queries.ts):**
  - `getMeeting()`: `public_comment_count: count` + `comment_summary: count > 0 ? {...} : undefined`
  - `getAgendaItemDetail()`: `public_comment_count: comments.length` + `comment_summary` + `comments` + `written_comment_count` + `spoken_comment_count`
  - `getControversialItems()`: `public_comment_count: Number(row.public_comment_count)`

### S20.4 Ongoing Sync Integration
- **Paths:** A, B, C
- **Description:** Add `youtube_comments` to `SYNC_SOURCES` in `data_sync.py`. Weekly cron after minutes extraction. Match new videos by meeting date. Only process meetings that have a YouTube URL but no comment counts yet.
- **Depends on:** S20.1.
- **Publication:** Infrastructure.

---

## Post-Launch — S21: Community Voice (Theme-Based Comment Display)

*Quick follow to go-live. Turns comment counts into legible civic participation.*

**Depends on:** S18 (Go Live) + S20 (transcript pipeline). First post-launch feature sprint.
**Spec:** `docs/specs/community-voice-spec.md`

**Design decision (2026-03-27):** Replaced sentiment classification (support/oppose/neutral) with theme-based narrative. Sentiment labels destroy nuance — a resident who raises both safety and privacy concerns is not "mixed," they're saying something that only works as a whole. Themes group by substantive point raised, not position.

**Scope:** Four phases:
1. ✅ **Enhanced transcript extraction** — `community_voice_extractor.py` + `prompts/community_voice_system.txt`. Extracts individual speaker names (LLM-corrected), methods, and 1-3 sentence summaries from transcripts. Migration 068 adds `source`, `confidence`, `name_confidence`, `extracted_at`, `city_fips` to `public_comments` + creates `comment_themes`, `comment_theme_assignments`, `item_theme_narratives` tables. Benchmark: 49/54 speakers extracted from Flock Safety meeting (2026-03-03) with names and summaries. 19 tests. **Remaining:** Backfill 80 meetings (~$8-15 via Batch API or sequential).
2. **Theme extraction pipeline** — Cluster comments by substantive topic (privacy, public safety, cost — NOT support/oppose). Generate 1-2 sentence narrative per theme per item. Theme seed consistency pattern (reuses `topic_tagger.py` approach). ~$2-5 via Batch API.
3. **Frontend "Community Voice" component** — Replaces `CommentBreakdownSection`. Themes with expandable individual comments, verbal/written badges, speaker names, AI labels, source attribution. Graceful degradation: themes → raw comments → count only.
4. **Backfill** — Process 80 meetings. Validate against Flock Safety benchmark. Total cost ~$10-20.

**Publication tier:** Graduated. Theme extraction is AI interpretation of Tier 4 sources. Operator-only until validated.

**Vote alignment (original S21 layer 3):** Deferred. Can be built later using theme data but not in initial scope.


---

## Phase 2 Change Log

- **2026-02-25 intake:** Added B.22-B.30 and future table designs from FUTURE_IDEAS-2 brainstorm (elections, position tracking, municipal code versioning, unified decision index, civic roles, newsletter pipeline, partnerships, B2B API). No sprint reassignments; all parked in backlog with dependency links.
- **2026-02-26 intake:** Parked H.11 (eSCRIBE text block formatting), B.31 (agenda vs. minutes diff). Added next-session note on S2.2 for category click-to-filter on meeting detail pages. Origin: procedural reclassification follow-up session.
- **2026-02-27 review:** Built system health self-assessment module. Established readiness signals and risk register. Assessment: inward-facing signals are healthy, outward-facing signals are the bottleneck. Next sessions should prioritize S2/S3 citizen-facing features over meta-infrastructure.
- **2026-03-01 QA/QC session:** Graduated S2.3 (AI bios), S5.1 (Form 700), S1.3 (commission pages) to public. Parked B.33 (user profiles/auth), B.34 (CLAUDE.md management), B.35 (org-candidate support mapping), H.18 (feedback button). S5.2 contribution badges: PAC badge public, behavioral pattern badges (Major/Grassroots/Targeted) remain operator-only pending threshold validation.
- **2026-03-03 eSCRIBE sync session:** Fixed eSCRIBE sync reliability (newest-first processing, per-meeting timeout). Bridged Layer 1→2 gap so `data_sync.py` auto-hydrates meetings + agenda_items. Backfilled 237 meetings / 6,687 agenda items. Discovered eSCRIBE has only stubs for 2020-2021 (pre-migration). Parked B.38 (Archive Center recurring sync), B.39 (pre-2022 minutes extraction for Tom Butt era).
- **2026-03-03 post-S6 reprioritization:** S1-S6 complete. Phase shift recognized: bottleneck moved from "can we build the data engine" to "can citizens make sense of the data." Decisions: (1) Generator automation patch added as pre-S7 work (cloud pipeline doesn't generate summaries/explainers for new meetings). (2) S7 (Operator Layer) stays next. (3) S8 (Citizen Discovery) created: promotes B.1 (RAG search) and H.18 (feedback button) into a formal sprint. (4) S9 (Information Design Overhaul) created: promotes H.10, H.14, H.17 into a design-led sprint focused on making data-dense civic content legible to non-experts. (5) Historical data backfill (B.38/B.39) stays in backlog, prioritized below citizen-facing width over data depth. No backlog items jumped above S7.
- **2026-03-05 minutes extraction pipeline:** Built `minutes_extraction` sync source bridging Layer 1 → Layer 2 for Archive Center minutes (AMID=31). Key changes: (1) `sync_minutes_extraction` in `data_sync.py` with incremental processing via `extraction_runs` table, (2) `extract_with_tool_use` gains `return_usage` for cost tracking, (3) agenda_items `ON CONFLICT` changed from `DO NOTHING` to `DO UPDATE` with `COALESCE` so minutes data enriches eSCRIBE stubs, (4) weekly cron in GitHub Actions (Monday 7am UTC), (5) AMID 31 promoted to Tier 1. B.38 addressed, B.39 partially addressed (pipeline exists, historical backfill not yet run).
- **2026-03-04 autonomy zones:** New architectural primitive: three-tier code sovereignty (free/proposal/sovereign). Inspired by yoyo-evolve self-modifying agent pattern, adapted for RTP's trust model. S7.4 added (Phase A: pipeline journal + self-assessment, observation only). B.40-B.42 added to backlog (Phases B-D: free-zone self-modification, proposal zone, boundary evolution). B.20 updated to encompass portable "AI-native project OS" extraction. Spec: `docs/specs/autonomy-zones-spec.md`. Open questions (trigger frequency, free-zone scope, LLM cost, enforcement) deferred to S7 start.
- **2026-03-07 sprint reordering:** Strategic resequencing based on operator insight: complete all data sources before building search, build search before UI overhaul. New S8 (Data Source Expansion) created: Socrata wiring (S8.1), court records B.10→S8.2, commission meetings B.36→S8.3, paper filings B.32→S8.4. Old S8 (Citizen Discovery) becomes S9 with new S9.1 (basic PostgreSQL full-text search) added before RAG (S9.2). Old S9 (Information Design) becomes S10. Rationale: RAG embedding templates should be designed with knowledge of all document types, not retrofitted. Basic search validates search UX before RAG investment. UI overhaul benefits from knowing full data landscape. Fixed monitoring mismatch: form700 + minutes_extraction added to FRESHNESS_THRESHOLDS, archive_center threshold standardized to 45 days.
- **2026-03-07 scanner v2 + research integration:** (1) Scanner v2 precision improvements: new `name_in_text()` for contiguous phrase matching (replaces scattered word-overlap on name-to-text paths), employer substring threshold 9→15 chars, entity extraction blocklist + min word count, specificity scoring penalty for generic-word donors. Estimated 50-70% reduction in false positive flags. (2) Research document (`docs/research/political-influence-tracing.md`) integrated: 10 documented influence patterns, 5 ranked cross-references, entity resolution via public registries, temporal filtering validation. New backlog items: B.46 (entity resolution infrastructure), B.47 (influence pattern taxonomy), B.48 (property transaction timing). B.45 updated with research specifics and dependency on B.46. B.46 is the long-term structural fix for scanner precision (corporate ID matching replaces fuzzy text matching). S10.6 added (cross-official donor overlap interactive selector).
- **2026-03-09 scanner roadmap & insights session:** Parked three new items from operator brainstorm: B.49 (consent calendar sub-item attribution — scanner flags specific consent sub-items instead of the block, frontend shows bulleted breakdown, populate `was_pulled_from_consent` field), B.50 (contract & agreement entity tracking — `city_contracts` table accumulated from extraction, entity-level spend view, cross-referenced with conflict scanner). Both feed into B.45 (political influence cross-referencing). `city_contracts` added to future tables list.
- **2026-03-09 roadmap reassessment (post-v2 data):** v2 batch scan results confirmed scanner produces zero actionable intelligence (9,927 flags, 88.5% at 0.40-0.49, zero above 0.60, form700_real_property = 86% of flags). Strategic resequencing: Scanner v3 (signal architecture) promoted from backlog (B.45, B.47) to new S9, ahead of search and design. Old S9 (Citizen Discovery) → S10. Old S10 (Information Design) → S11. Rationale: core intelligence engine must produce useful output before expanding citizen-facing surface area. S10 (search) works over real signal instead of noise. S11 (design) built on known final data shapes. S7.4 (autonomy zones) deferred further. S8.3/S8.4 remain as slot-in items. Four judgment calls resolved: (1) threshold values 0.85/0.70/0.50 public, (2) donor_vendor_expenditure flag type public, (3) badge labels "High/Medium/Low-Confidence Pattern", (4) factual template + blocklist + hedge clause approved.
- **2026-03-10 scanner v3 S9.1+S9.2 complete:** S9.1 (RawSignal + composite confidence foundation) and S9.2 (extract signal detectors) completed. Replaced ~443 lines of monolithic inline matching in `scan_meeting_json()` with three signal detector functions + `_signals_to_flags()` conversion. v3 multi-factor confidence model is now live: match_strength(0.35) + temporal_factor(0.25) + financial_factor(0.20) + anomaly_factor(0.20, stub=0.5) * sitting_multiplier * corroboration_boost. Key design discovery: single-signal max is tier 2 (0.8475 with anomaly stub). Tier 1 requires S9.3 corroboration or full anomaly_factor (B.51). 39 new signal detector tests + 44 composite confidence tests. All 1097 tests passing. New backlog: B.51 (anomaly baselines), B.52 (entity resolution lite), B.53 (signal type expansion). S9.4 (DB mode parity) may be nearly free since `scan_meeting_db` already delegates to `scan_meeting_json`.
- **2026-03-11 AI Parking Lot triage:** Reviewed 19 items across 4 categories. Three promotions: (1) I5 (CAL-ACCESS IE parsing) → S9.5 pre-rescan: parse `EXPN_CD` independent expenditures to connect PAC money to candidates as a new signal source before batch rescan. (2) R3 (per-signal vs group confidence display) → S9.6: show individual signal confidence alongside composite score during frontend label updates. (3) I6 (automated data quality regression suite) → S10.4: periodic DB quality checks as GitHub Action post-pipeline. Twelve items correctly parked (I2, I3, I7, I8, I9, I10, D2, D3, D4 as process items; V1-V3 pending their validation triggers). No roadmap restructuring needed. Sprint ordering (S9→S10→S11) remains sound.
- **2026-03-09 scanner DB mode unification:** Root cause of 21K noisy flags identified: `scan_meeting_db()` was a separate implementation from `scan_meeting_json()`, missing all v2 precision filters (council member suppression, government entity filtering, self-donation filtering, section header skipping, name_in_text matching, specificity scoring, contribution dedup, $100 materiality threshold, publication tier assignment, bias audit logging). Rewrote as thin data-fetching wrapper that delegates to `scan_meeting_json()`. Three new functions: `_fetch_meeting_data_from_db`, `_fetch_contributions_from_db`, `_fetch_form700_interests_from_db`. DB mode now uses `meeting_attendance` records for historical council member detection (covers 2005-2026 meetings correctly). Added `--validate` mode to `batch_scan.py` for before/after comparison with structured reporting. Added tier-level tracking to batch scan output. Updated 9 DB mode tests.
- **2026-03-15 B.45/B.53 permit-donor + license-donor cross-referencing:** Two new signal detectors added to conflict scanner, implementing cross-reference #5 from political influence research (Donor → Permit applicant → Decision, scored 11/15). (1) `signal_permit_donor()` — cross-references `city_permits.applied_by` against campaign contributions; uses job_value for financial factor; cites AB 571 (Gov. Code § 84308). (2) `signal_license_donor()` — cross-references `city_licenses.company` (+ DBA names) against contributions AND expenditure vendors; vendor match boosts match_strength by 1.1x. Both follow v3 signal detector pattern: gazetteer matching → contribution cross-reference → deduplication → RawSignal emission. DB mode: `_fetch_permits_from_db()` + `_fetch_licenses_from_db()`. Scanner now has 8 independent signal detectors (was 6). Corroboration boost automatic when same entity triggers multiple signal types. 27 new tests, 1354 total passing. B.45 now 3/5 cross-references operational (remaining 2 require B.46 entity resolution).
