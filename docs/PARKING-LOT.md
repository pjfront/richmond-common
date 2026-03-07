# Parking Lot — Execution Sprints & Backlog

> **Restructured 2026-02-23** from thematic groups to dependency-ordered execution sprints. Old group IDs (e.g., "2.1") preserved in brackets for cross-reference with DECISIONS.md.
>
> **Scoring:** Paths **A** = Freemium Platform, **B** = Horizontal Scaling, **C** = Data Infrastructure. Three paths = highest priority. Zero = scope creep.
>
> **Publication tiers:** Public (citizens see it), Operator-only (Phillip validates first), Graduated (starts operator-only, promoted after review).
>
> **Execution rhythm:** Each sprint produces both pipeline capability AND a visible frontend feature. Pipeline work is immediately manifested on the frontend behind the operator gate where appropriate.

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

*Tools that make Phillip's decision-making faster and more systematic.*

**Why last of the numbered sprints:** Not blocking any citizen-facing features. The operator layer becomes more valuable as more features exist to manage. After S1-S6, there are enough graduated features, data quality signals, and decision points to warrant a proper operator dashboard.

### S7.1 Operator Decision Queue [was 1.1]
- **Paths:** A, B
- **Description:** Dashboard showing everything that needs human decision: flags to review, findings to graduate from operator-only to public, data quality alerts, staleness findings. Pre-digested packets presenting minimum information for fastest correct decision.
- **Publication:** Operator-only.

### S7.2 Pre-Digested Decision Packets [was 1.2]
- **Paths:** A, B
- **Description:** For each decision point, the system assembles: the finding, all evidence, comparable past decisions, confidence assessment, and a recommended action.
- **Publication:** Operator-only.

### S7.3 Judgment-Boundary Audit [was 1.4]
- **Paths:** B
- **Description:** System reviews all processes marked as judgment calls and challenges each one. Also reviews AI-delegable processes for ones that should have human oversight. Bidirectional per tenet #2.
- **Publication:** Operator-only. Feeds roadmap.
- **Cadence:** Quarterly.

### S7.4 Autonomy Zones Phase A: Pipeline Journal + Self-Assessment (NEW)
- **Paths:** A, B, C
- **Description:** Append-only pipeline journal (`pipeline_journal` table) logging every run's metrics, confidence scores, error counts, and anomalies. Scheduled self-assessment cycle (LLM reads journal, produces structured health report as decision packet). No self-modification. Observation only. Feeds S7.1 (decision queue) and S7.2 (decision packets). Foundation for Phase B (free-zone self-modification) and Phase C (proposal zone). Full spec: `docs/specs/autonomy-zones-spec.md`.
- **Publication:** Operator-only (infrastructure).
- **Depends on:** Running pipeline with enough data to assess.
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

### S8.1 Socrata Sync Wiring (Payroll + Expenditures)
- **Paths:** A, B, C
- **Description:** Wire existing `socrata_client.py` query functions into `data_sync.py` as registered sync sources (`sync_socrata_payroll`, `sync_socrata_expenditures`). The client code exists with `get_recent_expenditures()`, `get_vendor_payments()`, `get_department_budget()`. The `payroll_ingester.py` has ingestion logic for `city_employees`. Currently these show as "never synced" on the data quality dashboard because they're monitored but have no sync functions. Hygiene-level work.
- **Publication:** Infrastructure (feeds existing operator dashboard).

### S8.2 Court Records / Tyler Odyssey [was B.10]
- **Paths:** A, B, C
- **Description:** Research and build scraper for Contra Costa County court records via the Tyler Odyssey portal (cc-courts.org). Cross-reference court cases involving city officials, contractors, and entities flagged in conflict scans. Research first: confirm Odyssey for Contra Costa County, assess scrapeability, define extraction schema.
- **Depends on:** S5.1 (Form 700 for entity cross-referencing).
- **Publication:** Graduated (legal data requires careful framing).

### S8.3 Commission/Board Meeting Agendas & Minutes [was B.36]
- **Paths:** A, B, C
- **Description:** Extend eSCRIBE scraper to pull non-council meeting types (Planning Commission, Design Review Board, etc.). Extend extraction prompts for commission-style agendas. Add frontend meeting history to commission detail pages. Archive Center has commission minutes across multiple AMIDs. Requires B.22 (`body_id` on meetings) for clean data modeling. Commissions make recommendations that become council votes; tracking the full decision chain starts here.
- **Depends on:** B.22 (bodies table), S1.4 (archive expansion), S1.3 (commission pages).
- **Publication:** Graduated (new data source, validate extraction quality first).

### S8.4 Paper-Filed Form 700s [was B.32]
- **Paths:** A, C
- **Description:** Scraper for NetFile's separate paper-filing portal (different URL/form structure from e-filed portal). Paper filing is legal under CA law, so any filer can avoid the e-filed portal while remaining fully compliant. Without this scraper, paper filers are a transparency blind spot. **First step:** cross-reference our 97 e-filers against the official list of designated filers (City Clerk). Any gap = paper filer = build the scraper. Priority escalates if council members or commissioners are in the gap.
- **Depends on:** S5.1 (Form 700 e-filed, complete). Trigger: gap analysis identifies paper filers.
- **Publication:** Graduated (extends existing public Form 700 display).

---

## Sprint 9 — Citizen Discovery

*Make the data findable, not just browsable. Start with basic search, graduate to semantic RAG.*

**Why here:** S1-S6 built a data-dense platform. S8 completes the data source landscape. Citizens can browse meetings, read summaries, see vote patterns, but they can't search. Basic text search ships first as a lightweight, zero-embedding-pipeline capability. RAG search follows with full semantic understanding. H.18 (feedback button) rides along as low-cost, high-signal infrastructure for the public beta.

### S9.1 Basic Site Search (PostgreSQL Full-Text Search) [NEW]
- **Paths:** A, B
- **Description:** PostgreSQL-native full-text search using `tsvector`/`ts_rank` (built into Supabase). Search across agenda item titles, plain language summaries, vote explainers, meeting titles, official names. Search bar in the nav or a dedicated search page with faceted results (filter by date range, category, body). No embedding pipeline needed. Validates search UX (what people search for, how results should display) before investing in RAG. Corresponds to "basic search" in the free tier of the business model. When RAG ships (S9.2), basic search handles exact keyword matches while RAG handles semantic queries.
- **Depends on:** Existing structured data (met).
- **Publication:** Graduated (new interaction paradigm, validate result quality before public).

### S9.2 RAG Search (pgvector) [was S8.1/B.1]
- **Paths:** A, B, C
- **Description:** Embedding pipeline for agenda items, summaries, explainers, and meeting content. pgvector search with SQL filtering (by date, category, council member, body). Semantic search UI augmenting S9.1's keyword search. Prerequisite for Charter compliance engine (B.11), stakeholder mapping (B.12), and cross-city comparison (B.16). Benefits from S8 completing the data source landscape: embedding templates designed once for all document types.
- **Depends on:** S1.4 (archive data in Document Lake), S8 (all data sources assembled).
- **Publication:** Graduated (new interaction paradigm, validate result quality before public).

### S9.3 Natural Language Feedback Button [was S8.2/H.18]
- **Paths:** A
- **Description:** Unobtrusive floating button for submitting ideas, bugs, and feedback in natural language. Submissions auto-routed to a structured parking lot for periodic bundled evaluation. Critical for public beta UX feedback loops. Low build cost, high signal value.
- **Publication:** Public (the mechanism itself; submissions are operator-only).

---

## Sprint 10 — Information Design Overhaul

*How do we present all this data to people who don't follow city council?*

**Why here:** After S8 assembles all data sources and S9 gives citizens a way to find data, S10 makes what they find legible. This is the "data-dense pot" problem: 237 meetings, 6,687 agenda items, 22K+ contributions, coalition matrices, pattern analysis. Powerful for an operator, overwhelming for a citizen. This sprint is about the meta-structure: how information-dense civic data communicates to lay people.

**Note:** This sprint is design-led, not pipeline-led. It may produce a design spec before code. User feedback from S9.3 and private beta informs the work.

### S10.1 Information Design Philosophy & Overarching Redesign [was S9.1/H.10]
- **Paths:** A, B
- **Description:** Holistic review of how info-dense civic data communicates to lay people. Inputs: real user feedback (from S9.3), AI-driven persona testing (H.8), data visualization best practices. Outputs: design principles document, component hierarchy, navigation rethink, progressive disclosure strategy. This is the "how do we present all this" question.
- **Depends on:** Real data in the platform (met), ideally some user feedback (S9.3).
- **Publication:** The design system itself is infrastructure; individual redesigned pages graduate.

### S10.2 Plain English UX Iteration [was S9.2/H.14]
- **Paths:** A
- **Description:** Implement the S10.1 design philosophy on the highest-traffic pages. Click-to-expand vs. always-visible summaries, progressive disclosure tuning, information hierarchy on meeting detail pages. Depends on real user feedback on what people actually want to see first.
- **Publication:** Public (refinement of existing public features).

### S10.3 Council Bio Rework [was S9.3/H.17]
- **Paths:** A
- **Description:** Rethink what objective information to synthesize in elected official profiles. Current bios show vote category percentages, which can be misleading (reps don't control what comes to vote). Starting point: tenure dates, committee assignments, attendance rate, factual voting record summary. Brainstorm needed on what a broad audience finds most useful.
- **Publication:** Graduated (replaces existing public bios, so framing review needed).

---

## Backlog — Data Foundation & Scale

*Items without sprint assignment. Ordered by likely execution sequence. Pulled into sprints during weekly/milestone reviews.*

### Data Foundation

| ID | Item | Paths | Depends On | Notes |
|----|------|-------|------------|-------|
| ~~B.1~~ | ~~RAG Search (pgvector)~~ | — | — | **Promoted to S8.1.** |
| B.2 | Board/Commission Member Profiles [was 4.5] | A, B, C | S1.3 (commission pages) | Extend `officials` profiles beyond council. 30+ commissions. |
| B.3 | Website Change Monitoring [was 5.1] | B, C | — | Periodic snapshots, diff detection, alert on changes. Start with commission rosters, policy pages. |
| B.4 | News Integration & Article Linking [was 5.4] | A, B, C | B.6 (media registry) | Associate agenda items with news coverage. |
| B.5 | Media Source Research Pipeline [was 5.2] | B, C | — | Automated discovery of local media sources per city. |
| B.6 | Per-City Media Source Registry [was 5.3] | B, C | B.5 | Structured `media_sources` table with credibility tiers. |
| B.7 | Local Media Monitoring [was 5.5] | A, B, C | B.4, B.6 | Auto-assemble context when local news breaks. |
| B.8 | Video Transcription Backfill [was 5.7] | A, C | — | Granicus archive 2006-2021. Budget-dependent. |
| B.9 | Email Alert Subscriptions [was 4.6] | A, B | S9.2 (RAG) | Requires user accounts. |
| B.22 | `bodies` Table + body_id on Meetings/Votes | A, B, C | S1.3 (commission pages) | Formalize governing body model. All meeting/vote/attendance records get `body_id` FK. Schema accommodation for unified decision index. Source: FUTURE_IDEAS-2. |
| B.23 | Civic Role History (`civic_roles` table) | A, B, C | S2.3 (bios) | Track full public service trajectory per person: elected, appointed, employee, candidate. Enriches bios, closes loop when commissioner runs for council. Source: FUTURE_IDEAS-2. |
| ~~B.32~~ | ~~NetFile SEI Paper Filings Scraper~~ | — | — | **Promoted to S8.4.** |
| B.38 | ~~Archive Center Recurring Sync + Historical Ingest~~ | A, B, C | S1.4 (archive infra) | **ADDRESSED (2026-03-05).** `minutes_extraction` sync source added to `data_sync.py`. Weekly cron in GitHub Actions (Monday 7am UTC) runs `archive_center` download then `minutes_extraction` sequentially. AMID 31 promoted to Tier 1. Incremental mode via `extraction_runs` table. **Remaining:** full historical ingest across all AMIDs (not just AMID 31) is still manual. |
| B.39 | Pre-2022 Minutes Extraction (Tom Butt Era) | A, C | ~~B.38~~ (now built) | **ADDRESSED (2026-03-06).** Batch API extraction completed: 703 of 706 AMID=31 documents loaded into Layer 2 (99.6% success). Spans Jan 2005 – Mar 2026. Database now has 785 meetings, 14,904 agenda items, 9,919 motions, 55,679 votes, 5,393 attendance records, 21,702 public comments. Cost: $39.00 via Batch API (50% discount). 3 failures: 1 unparseable doc (`<UNKNOWN>` date), 2 varchar overflows on `financial_amount` (pending column widening). Migration 017 widened 5 other columns. **Remaining:** OCR for Type3-font PDFs (if any exist with empty `raw_text`). |

| B.43 | Historical Cohort Filtering for Governing Bodies | A, B, C | B.22 (bodies table), B.23 (civic roles) | When browsing meetings or changing date filters, instantly see the composition of the city council and/or boards/commissions for that period. If a date range spans multiple cohorts (e.g., across an election or appointment change), show distinct cohorts within the range. UX: temporal filter → governing body membership snapshot(s). Requires term/tenure data in `civic_roles` and a body model (`bodies` table). Distinct from B.23 (which tracks individual trajectories); this is the group composition view. Origin: 2026-03-06 batch extraction session. |

### Deep Intelligence

| ID | Item | Paths | Depends On | Notes |
|----|------|-------|------------|-------|
| ~~B.10~~ | ~~Court Records / Tyler Odyssey [was 3.3]~~ | — | — | **Promoted to S8.2.** |
| B.11 | City Charter Compliance Engine [was 3.4] | A, B, C | S1.3, S9.2 (RAG) | Charter as the city's CLAUDE.md. |
| B.12 | Stakeholder Mapping & Coalition Graph [was 3.5] | A, C | S9.2 (RAG), S5.1 | Graph problem: entities have positions on issues. |
| B.13 | "What Are We Not Seeing?" Audit [was 1.3] | A, B, C | 6 months ground truth | Gap analysis of scanner blind spots. |
| B.24 | Election Cycle Tracking | A, B, C | S5 (financial intelligence) | City clerk scraper, county NetFile API (Forms 460/497/501/410). Richmond June 2026 primary is first target. **Schema (empty `elections` + `candidates` tables) created now; pipeline builds with S5.** Source: FUTURE_IDEAS-2. |
| B.25 | Position Ledger + Stance Timeline | A, B, C | S2.1 (categories), S6.1 (coalitions) | Track positions per person over time by issue category. Source types: votes (high confidence), discussion (medium), forums/websites (lower). Contradiction detection as query layer. Source: FUTURE_IDEAS-2. |
| B.26 | Unified Decision Index + Decision Chain Linking | A, B, C | S2.1 (categories), B.22 (bodies) | Single queryable index across all city bodies. Decision chain table links related items (Planning Commission recommendation → Council final vote). Emergent from consistent categorization + body_id. Source: FUTURE_IDEAS-2. |
| B.27 | Municipal Code Versioning & Diff Tracking | A, B, C | Reliable meeting extraction | Periodic snapshots of municipal code (Municode/American Legal), section-level diffs, ordinance linkage. High horizontal scaling value (standardized platforms). Source: FUTURE_IDEAS-2. |
| B.31 | Agenda vs. Minutes Diff | A, B, C | Reliable meeting + agenda extraction | Compare agendized items (from eSCRIBE pre-meeting scrape) to items actually appearing in minutes. Detect pulled items, added items, reordered items, items that disappear without explanation. Transparency signal: "what was planned vs. what happened." Origin: 2026-02-26 follow-up item 4. |

### Scale & Future

| ID | Item | Paths | Depends On | Notes |
|----|------|-------|------------|-------|
| B.14 | External API / MCP Server [was 6.1] | B, C | Stable schema, multi-city | Civic data as infrastructure. |
| B.15 | Speaker Diarization Analytics [was 6.2] | A, B, C | Transcription pipeline | Paid feature candidate (~$0.50-1.00/meeting hour). |
| B.16 | Cross-City Policy Comparison [was 6.3] | A, B, C | S9.2 (RAG), 3+ cities | Killer feature for horizontal scaling. |
| B.17 | Civic Website Modernization [was 6.4] | A, B, C | 5-10 cities running | Different product, different buyer. |
| B.18 | Civic Knowledge Graph [was 6.5] | B, C | S9.2, S8.2, B.12 | Entity-relationship graph across all data. |
| B.19 | Domain Strategy [was 6.6] | — | Before public launch | .city, .fyi, .ai domain decisions. |
| B.20 | Civic Transparency SDK [was 6.7, "System Definition Portability"] | B, C | See phased triggers below | **Five-layer SDK** encoding RTP conventions into reusable, enforceable code. Open-core model: Layers 1-3 open source, 4-5 proprietary. **Phase A (fold into S7-S8):** Formalize conventions inside `src/` with extraction-ready interfaces. `SourceTier` IntEnum, exception hierarchy (`ConventionViolationError` tree), disclosure registry (Chevron, E-Forum), clean document lake signatures, `validate_fips()` extracted from `city_config.py`. Design as public API, implement in `src/`. **Phase B (trigger: after S10, second city, or open-source timing):** Extract to `packages/civic_sdk/` as pip-installable package. Resolve packaging decisions (pydantic vs dataclasses, async, package name, license). **Phase C (future, open source):** Layers 2-3 (pipeline primitives, entity resolution). **Phase D (future, private):** Layers 4-5 (multi-city orchestration, spec language). Also encompasses the "AI-native project OS" extraction (autonomy zones, judgment boundaries, publication tiers, phased development). Validate abstraction against second real project. Specs: `docs/specs/civic-sdk-spec.md`, `docs/specs/civic-sdk-vision.md`. |
| B.40 | Autonomy Zones Phase B: Free Zone Self-Modification | A, B, C | S7.4 (Phase A journal) running 2-3 weeks | Move prompts/selectors/config into `src/mutable/`. Validation framework with baselines. Self-assessment loop attempts fixes in free zone, auto-commits on pass, auto-reverts on fail. Spec: `docs/specs/autonomy-zones-spec.md`. |
| B.41 | Autonomy Zones Phase C: Proposal Zone + Operator Queue | A, B, C | B.40 (Phase B validated) | Staging area for changes outside free zone. System drafts changes + decision packets, operator approves/rejects. Wires into S7.1 decision queue. |
| B.42 | Autonomy Zones Phase D: Boundary Evolution | B, C | B.41 running 1+ months | System reviews its own zone assignments. Proposes promotions (proposal → free) and demotions (free → proposal) based on journal patterns. Zone changes are always judgment calls. Recursive application of Tenet 2. |
| B.21 | Open Source with BSL License (NEW) | A, B, C | Before public launch | Make repo public under Business Source License 1.1. Enables free GitHub features (branch protection), aligns with transparency mission, builds civic tech credibility. BSL prevents commercial competition while allowing visibility. Requires: move BUSINESS-MODEL.md to private location, choose Additional Use Grant (non-commercial vs non-production only), set Change Date (3-4 years → Apache 2.0). Moat is data/operations/relationships, not code. See 2026-02-24 session analysis. |
| B.28 | Newsletter Discovery & Ingestion Pipeline | A, B, C | Scale phase | Automated discovery → subscribe → ingest for council member newsletters. Tom Butt E-Forum is Richmond test case (Tier 3). `source_type = 'newsletter'` should be valid from day one. Source: FUTURE_IDEAS-2. |
| B.29 | Cityside/Richmondside Partnership | A, B, C | Post Phase 1 validation | Cityside runs Richmondside, Berkeleyside, The Oaklandside. Mission-aligned hyperlocal nonprofit journalism. Partnership shapes: data provider → funded Bay Area pilot. Research contacts after validation. Source: FUTURE_IDEAS-2. |
| B.30 | Path D: B2B Municipal Data API | B, C | Stable schema, multi-city | Same extraction pipeline, different API consumer (sales teams selling to city governments). B2B revenue subsidizes free civic tier. Don't let B2B feature requests drive extraction priorities. Related to B.14 (External API). Source: FUTURE_IDEAS-2. |
| B.33 | User Profiles + Access Level Infrastructure | A, B | Before public beta | Authentication (Supabase Auth likely), role-based access controlling gated features. Replaces cookie-based OperatorGate with real auth. Roles: public (default), beta tester, operator, superadmin. AI-native architecture: automated role management with manual superadmin override. Needs deep design session. Key questions: how do access levels interact with publication tiers? Can the system auto-promote beta testers based on engagement? How does this scale to multi-city (per-city operators)? Origin: QA/QC review session, 2026-03-01. |
| B.34 | CLAUDE.md Management + Multi-Level LLM Documentation | B, C | Ongoing | Systematic LLM-centric documentation of the entire app at multiple levels: code, user/UX/usability, architecture/infrastructure, UI, use case. Goal: any AI agent can understand the project at the right level of abstraction for its task. Related to H.5 (system writes its own CLAUDE.md). This is the meta-system: documentation as a first-class product that improves AI collaboration quality. Origin: QA/QC review session, 2026-03-01. |
| B.35 | Organization-Candidate Support Mapping | A, B, C | After S6 coalition analysis | Track non-contribution support relationships: independent expenditures (IEs), endorsements, slate alignment. CAL-ACCESS IE data is the structured starting point (IEs are filed with candidate targets). Endorsement tracking requires a curation layer (org websites, voter guides, news). Distinct from S6 coalition inference: this is *documented* organizational support (RPOA, RPA, Chamber of Commerce, etc.), not inferred alignment from voting patterns. Key Richmond context: RPA endorsement slates and Chevron-aligned IE spending are arguably more important political signals than individual direct contributions. Origin: QA/QC review session, 2026-03-01. |
| ~~B.36~~ | ~~Commission/Board Meeting Agendas & Minutes~~ | — | — | **Promoted to S8.3.** |
| B.37 | Custom Topic Trackers (Paid) | A, B | B.33 (user accounts) | Users subscribe to specific policy topics or keywords. System alerts when matching agenda items appear in upcoming meetings. Tied to user profile/account system. Revenue path: freemium tier boundary (free users see public data, paid users get proactive alerts). Requires notification infrastructure (email or in-app). Origin: 2026-03-01. |

### Hygiene (Weave In As Needed)

Items that aren't sprint-worthy standalone but should be addressed opportunistically:

| ID | Item | Trigger |
|----|------|---------|
| H.1 | ~~Clean up deprecated sync-pipeline.yml [was 0.2]~~ | ✅ Done 2026-03-01. Commit `4e5e5cd`. |
| H.2 | Architecture Self-Assessment / Tenets Audit [was 0.3] | First CI setup or drift detected |
| H.3 | Auto-Documentation of Decisions [was 0.4] | Next skill refinement |
| H.4 | Research Session Auto-Persist [was 0.5] | Next pure research session |
| H.5 | System Writes Its Own CLAUDE.md [was 0.6] | After restructuring stabilizes |
| H.6 | Automated Prompt Regression Testing [was 0.7] | Next prompt template change. Related: H.13 (prompt registry) provides the versioning layer this needs. |
| H.7 | Session Continuity Optimization [was 0.8] | Next context-loss incident |
| H.8 | AI-Driven Persona Testing [was 4.7] | After frontend MVP stable |
| ~~H.10~~ | ~~Information Design Philosophy & Overarching Redesign~~ | **Promoted to S9.1.** |
| H.9 | ~~Gated Feature Entry-Point Audit Checklist~~ | ✅ Done 2026-03-01. Findings logged in DECISIONS.md. Two gaps found: `/api/data-quality` unprotected (low risk), client-side-only gating on summaries/bios (acceptable for beta). |
| H.11 | eSCRIBE Item 0.2.a Text Block Formatting | Next scraper refinement session. Some agenda items contain large unformatted text blocks from eSCRIBE (entire staff report text inlined). Need readability formatting (paragraph breaks, structured sections). Origin: 2026-02-26 follow-up item 3b. |
| H.12 | Contact Info + Tip Jar on About Page | Before public launch. Add a contact form, email, or other way for people to reach out with questions/corrections/tips. Also explore a tip jar or small donation mechanism. Currently the "Contact & Feedback" section just says "reach out" with no actionable contact method. Origin: 2026-02-27 about page content update. |
| H.13 | Prompt Quality System (Registry + Evaluation Loop) | After 2-3 manual prompt iterations on summaries or bios. Three layers: (1) **Prompt registry** — `prompt_versions` table (name, version, content_hash, created_at), `prompt_outputs` table (version_id, input_hash, output, model). Re-run historical data against new prompts with measurable delta. (2) **Operator feedback console** — rapid review UI for real + synthetic outputs, thumbs-up/down + category tags, feeds labeled ground truth. (3) **Model self-evaluation** — double-blind: evaluator model scores outputs without knowing prompt version, disagreements with operator labels surface as calibration data. Full closed loop: operator validates sample, model evaluates rest, boundary tightens over time (Tenet 2 applied to prompt quality). Currently using file-based templates in `src/prompts/`. Related: H.6 (regression testing harness). Origin: S3.1 prompt architecture decision + evaluation workflow discussion, 2026-02-27. |
| ~~H.14~~ | ~~Plain English UX: Click-to-Expand vs. Always-Visible~~ | **Promoted to S9.2.** |
| H.15 | Meeting-Level Plain English Summary | After S3.1 summaries validated on 3-5 meetings. Generate a holistic meeting summary from minutes: what got the most discussion, who pushed for what, key decisions and their significance. Different from per-item summaries (synthesis across items, not translation of individual items). Inputs: all agenda item summaries + vote data + any available minutes text. Publication: Graduated (inference about discussion dynamics requires careful framing). Origin: S3.1 review, 2026-02-28. |
| H.16 | Vote Explainer Historical Context (Option C) | After 2-3 prompt iterations on vote explainers. Enhance S3.2 explainers with historical voting pattern context: "Councilmember X has voted against housing projects 4 of the last 5 times." Requires vote categorization (S2.1) data and a query layer for per-member category voting history. Upgrade path is additive: add a `historical_context` section to the existing prompt template, feed it pre-queried voting pattern data. Deferred because Option B (contextual framing) needs validation first, and the incremental value of historical context depends on having enough categorized meeting data to make patterns meaningful. Origin: S3.2 scope decision, 2026-02-28. |
| ~~H.17~~ | ~~Council Bio Rework~~ | **Promoted to S9.3.** |
| ~~H.18~~ | ~~Natural Language Feedback Button~~ | **Promoted to S9.3** (was S8.2 before sprint reorder). |

---

## Schema Fields to Add Now (Future-proof)

Nullable fields to include in current schema so future features don't need migrations:

| Table | Field | Type | Purpose |
|-------|-------|------|---------|
| `agenda_items` | `discussion_duration_minutes` | INTEGER (nullable) | Time-spent analytics (S6.3) |
| `agenda_items` | `public_comment_count` | INTEGER (nullable) | Controversy signal (S6.3) |
| `agenda_items` | `plain_language_summary` | TEXT (nullable) | Summaries (S3.1) |
| `agenda_items` | `category` | TEXT (nullable) | Vote categorization (S2.1) |
| `speakers` | `speaking_duration_seconds` | INTEGER (nullable) | Speaker analytics (B.15) |
| `officials` | (design for any official type) | — | Board/commission expansion (B.2) |

### Tables to Create Now (Empty, pipeline later)

Create these tables in the next migration. They stay empty until their pipeline sprint arrives, but having the schema avoids future migrations and signals architectural intent. Full DDL in `~/Downloads/FUTURE_IDEAS-2.md`.

| Table | Purpose | Pipeline In |
|-------|---------|-------------|
| `elections` | Election cycles with dates and types | B.24 / S5 |
| `candidates` | Candidate registrations per election, linked to person entity | B.24 / S5 |

### Future Tables (Design When Sprint Dependencies Met)

Schema designs from FUTURE_IDEAS-2 brainstorm. Full DDL in source file (`~/Downloads/FUTURE_IDEAS-2.md`). Design these when their dependent sprint arrives; don't build prematurely.

| Table | Purpose | Depends On |
|-------|---------|------------|
| `bodies` | Governing body registry (council, commissions, boards, authorities) | B.22 |
| `civic_roles` | Person role history (elected, appointed, employee, candidate) | B.23 |
| `positions` | Position ledger: person + issue + stance + source + confidence | B.25 |
| `decision_chains` / `decision_chain_items` | Link related decisions across bodies (recommendation → final vote) | B.26 |
| `code_snapshots` / `code_sections` / `code_diffs` | Municipal code versioning and ordinance linkage | B.27 |

---

## Reprioritization Cadence

- **Milestone-triggered:** After completing any sprint, review the next sprint's items and the backlog before starting.
- **Weekly fallback:** If no milestone in the past 7 days, do a lightweight review of sprint order and backlog.
- **Deep restructure:** When significant new capabilities change what's possible (new model, new data source, architectural shift). This document was created during the first deep restructure on 2026-02-23.
- **2026-02-25 intake:** Added B.22-B.30 and future table designs from FUTURE_IDEAS-2 brainstorm (elections, position tracking, municipal code versioning, unified decision index, civic roles, newsletter pipeline, partnerships, B2B API). No sprint reassignments; all parked in backlog with dependency links.
- **2026-02-26 intake:** Parked H.11 (eSCRIBE text block formatting), B.31 (agenda vs. minutes diff). Added next-session note on S2.2 for category click-to-filter on meeting detail pages. Origin: procedural reclassification follow-up session.
- **2026-03-01 QA/QC session:** Graduated S2.3 (AI bios), S5.1 (Form 700), S1.3 (commission pages) to public. Parked B.33 (user profiles/auth), B.34 (CLAUDE.md management), B.35 (org-candidate support mapping), H.18 (feedback button). S5.2 contribution badges: PAC badge public, behavioral pattern badges (Major/Grassroots/Targeted) remain operator-only pending threshold validation.
- **2026-03-03 eSCRIBE sync session:** Fixed eSCRIBE sync reliability (newest-first processing, per-meeting timeout). Bridged Layer 1→2 gap so `data_sync.py` auto-hydrates meetings + agenda_items. Backfilled 237 meetings / 6,687 agenda items. Discovered eSCRIBE has only stubs for 2020-2021 (pre-migration). Parked B.38 (Archive Center recurring sync), B.39 (pre-2022 minutes extraction for Tom Butt era).
- **2026-03-03 post-S6 reprioritization:** S1-S6 complete. Phase shift recognized: bottleneck moved from "can we build the data engine" to "can citizens make sense of the data." Decisions: (1) Generator automation patch added as pre-S7 work (cloud pipeline doesn't generate summaries/explainers for new meetings). (2) S7 (Operator Layer) stays next. (3) S8 (Citizen Discovery) created: promotes B.1 (RAG search) and H.18 (feedback button) into a formal sprint. (4) S9 (Information Design Overhaul) created: promotes H.10, H.14, H.17 into a design-led sprint focused on making data-dense civic content legible to non-experts. (5) Historical data backfill (B.38/B.39) stays in backlog, prioritized below citizen-facing width over data depth. No backlog items jumped above S7.
- **2026-03-05 minutes extraction pipeline:** Built `minutes_extraction` sync source bridging Layer 1 → Layer 2 for Archive Center minutes (AMID=31). Key changes: (1) `sync_minutes_extraction` in `data_sync.py` with incremental processing via `extraction_runs` table, (2) `extract_with_tool_use` gains `return_usage` for cost tracking, (3) agenda_items `ON CONFLICT` changed from `DO NOTHING` to `DO UPDATE` with `COALESCE` so minutes data enriches eSCRIBE stubs, (4) weekly cron in GitHub Actions (Monday 7am UTC), (5) AMID 31 promoted to Tier 1. B.38 addressed, B.39 partially addressed (pipeline exists, historical backfill not yet run).
- **2026-03-04 autonomy zones:** New architectural primitive: three-tier code sovereignty (free/proposal/sovereign). Inspired by yoyo-evolve self-modifying agent pattern, adapted for RTP's trust model. S7.4 added (Phase A: pipeline journal + self-assessment, observation only). B.40-B.42 added to backlog (Phases B-D: free-zone self-modification, proposal zone, boundary evolution). B.20 updated to encompass portable "AI-native project OS" extraction. Spec: `docs/specs/autonomy-zones-spec.md`. Open questions (trigger frequency, free-zone scope, LLM cost, enforcement) deferred to S7 start.
- **2026-03-07 sprint reordering:** Strategic resequencing based on operator insight: complete all data sources before building search, build search before UI overhaul. New S8 (Data Source Expansion) created: Socrata wiring (S8.1), court records B.10→S8.2, commission meetings B.36→S8.3, paper filings B.32→S8.4. Old S8 (Citizen Discovery) becomes S9 with new S9.1 (basic PostgreSQL full-text search) added before RAG (S9.2). Old S9 (Information Design) becomes S10. Rationale: RAG embedding templates should be designed with knowledge of all document types, not retrofitted. Basic search validates search UX before RAG investment. UI overhaul benefits from knowing full data landscape. Fixed monitoring mismatch: form700 + minutes_extraction added to FRESHNESS_THRESHOLDS, archive_center threshold standardized to 45 days.
