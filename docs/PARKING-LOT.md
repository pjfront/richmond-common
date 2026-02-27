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

### S1.1 Feature Gating System (NEW)
- **Paths:** A, B
- **Description:** Operator-only toggle that lets Phillip see WIP features on the frontend before public release. Implements the publication tier system in code: Public (everyone), Operator-only (Phillip), Graduated (starts operator-only, promoted after review).
- **Implementation:** Cookie or URL-param based toggle + React context (`<OperatorGate>`). Simple enough for beta. Real Supabase Auth can replace it later without changing component structure.
- **Publication:** Public infrastructure (the gating mechanism itself is invisible to citizens).
- **Unlocks:** Every subsequent sprint can immediately expose features to the operator.

### S1.2 Table Sorting/Filtering on All Views [was 4.1]
- **Paths:** A, B
- **Scope:** Pure frontend. One afternoon with TanStack Table or similar.
- **Publication:** Public.

### S1.3 Commission Pages [was 4.4]
- **Paths:** A, B
- **Description:** Frontend pages for commission/board data. Member lists, appointment tracking, vacancy alerts. Commission meeting history when scraping is ready.
- **Prerequisites met:** Migration 005 done. Roster scraper built. Appointment extractor built. eSCRIBE commission meeting types discovered.
- **Publication:** Public (factual roster data). Graduated (staleness findings, vacancy alerts).

### S1.4 Archive Center Expansion [was 5.6]
- **Paths:** B, C
- **Description:** Expand from AMID=31 (council minutes only) to all 149 active archive modules. Download PDFs for high-priority AMIDs (resolutions, ordinances, commission minutes, Personnel Board, Rent Board, City Manager reports) into Layer 1. Defer Claude extraction until RAG search or specific cross-referencing needs.
- **Scope:** ~30 min. Extend existing `batch_extract.py` patterns.
- **Value:** 9,000+ documents in the lake at zero marginal cost. Feeds vote categorization (resolutions), Form 700 (contract text), RAG search (everything), and model testing (diverse document types).
- **Already decided:** See DECISIONS.md 2026-02-22 entry.

### S1.5 CI/CD: Vercel Auto-Deploy + GitHub Actions Tests [was 0.1]
- **Problem:** Vercel deploys are manual (`npx vercel --prod`). Tests don't run on PRs.
- **Fix:** Connect Vercel to GitHub repo (auto-deploy on push to main, PR previews). Add `.github/workflows/test.yml` (pytest on PR). Add branch protection.
- **Scope:** ~10 min Vercel dashboard + 1 workflow file.

---

## Sprint 2 — Vote Intelligence

*The highest-leverage unlock: categorized votes enable coalition analysis, time-spent stats, trend tracking, and meaningful cross-meeting pattern detection.*

**Why second:** Vote categorization [2.1] is prerequisite for S6 (coalition analysis, patterns, time-spent). It's triple-path (A+B+C). With archive data from S1, the categorizer can cross-reference votes against the resolutions/ordinances they produce.

### S2.1 Vote Categorization Taxonomy & Classifier [was 2.1]
- **Paths:** A, B, C
- **Description:** Taxonomy of vote categories (land use, public safety, budget, contracts, personnel, etc.). LLM classifier prompt to tag each agenda item/vote. `category` field on `agenda_items` and `votes`.
- **Prerequisite for:** S6.1 (coalition), S6.2 (patterns), S6.3 (time-spent).
- **Publication:** Public (categories are factual).

### S2.2 Category Display Components (NEW)
- **Paths:** A
- **Description:** Frontend components showing vote categories on meeting pages and council profiles. Category breakdowns, filter-by-category. Visible immediately behind operator gate, promoted to public once categorization is validated.
- **Publication:** Graduated.
- **Next session (2026-02-26):** Add click-to-filter on meeting detail pages. Category badges on `AgendaItemCard` should filter the agenda list when clicked (show only items in that category). Natural extension of the `MeetingAgendaSection` procedural toggle pattern. Origin: follow-up item 5.

### S2.3 AI-Generated Council Member Bios [was 2.6]
- **Paths:** A, B, C
- **Description:** Synthesis prompt combining voting record, campaign filings, committee assignments. "Sunlight not surveillance" framing critical.
- **Publication:** Graduated. Operator-only until framing validated.

---

## Sprint 3 — Citizen Clarity

*Make government decisions understandable to non-experts.*

**Why third:** Plain language summaries are the single most citizen-friendly feature. "Explain This Vote" builds on summaries + categories from S2. Both are public-ready and demonstrate immediate value.

### S3.1 Plain Language Agenda Summaries [was 2.4]
- **Paths:** A, B, C
- **Description:** `plain_language_summary` field on `agenda_items`. Dedicated prompt template file. Validate on 3-5 pilot meetings before public release.
- **Frontend:** Progressive disclosure on meeting detail pages. Official title visible by default; plain English summary expands on click. Preserves accuracy/searchability while making content accessible to laypeople.
- **Publication:** Public (after validation).

### S3.2 "Explain This Vote" Lite [was 4.2]
- **Paths:** A, B
- **Description:** Per-vote explainer: "What was this about? Why did it matter? How did each member vote and why might they have voted that way?" Generated from agenda item + staff report + vote breakdown + historical context.
- **Publication:** Graduated. Inference about motives requires careful framing.
- **Depends on:** S2.1 (categories) and S3.1 (summaries) for richer context.

---

## Sprint 4 — Data Quality & Integrity

*Fix the foundation. Prevent the Jamelia Brown class of bugs from ever happening silently again.*

**Why here (not earlier):** Data quality doesn't block feature development, but it protects the features we've built. After S1-S3, there's enough visible output that data quality issues become user-facing problems worth solving systematically.

### S4.1 Fuzzy Duplicate Official Detection (NEW) [from DECISIONS.md 2026-02-23]
- **Paths:** B, C
- **Description:** Add fuzzy matching to `ensure_official()` or a post-load validation step. When a new official name is within Levenshtein distance 2 of an existing official, warn (or merge if confidence is high). Wire up `aliases` field from `officials.json` into lookup.
- **Origin:** Jamelia Brown silent data split. April 15, 2025 minutes misspelled name, created phantom record with 0 votes.
- **Publication:** Operator-only (data quality alerts).

### S4.2 Data Freshness & Completeness Monitoring (NEW)
- **Paths:** A, B, C
- **Description:** Automated checks: Are meetings loading on schedule? Are vote counts reasonable? Are all expected council members appearing? Document completeness tracking (missing minutes, late agenda packets). Alerts to operator when anomalies detected.
- **Publication:** Operator-only (alerts). Public (document completeness dashboard, was 4.8).

### S4.3 Alias Wiring for Conflict Scanner [from DECISIONS.md 2026-02-22]
- **Paths:** A, C
- **Description:** Update `conflict_scanner.py` to load aliases from `officials.json` and include them in donor/entity name matching. First case: Shasa Curl (legal name "Kinshasa Curl" in campaign filings).
- **Scope:** Small. Expand the name set during entity resolution.

---

## Sprint 5 — Financial Intelligence

*The highest-value conflict detection signals. Form 700 is the crown jewel.*

**Why here:** Form 700 research is done (`docs/research/form-700-research.md`). Commission pipeline is stable (prerequisite met). Archive data from S1 provides contract/resolution context. This is where the project's core accountability value deepens significantly.

### S5.1 Form 700 Ingestion [was 2.5]
- **Paths:** A, B, C
- **Description:** Parse FPPC Form 700 PDFs for economic interest disclosures. Cross-reference against agenda items for council AND commission members. Highest-value conflict detection signal.
- **Research:** `docs/research/form-700-research.md`
- **Publication:** Graduated (financial interest disclosures require careful framing).

### S5.2 Contribution Context Intelligence [was 3.2]
- **Paths:** A, B, C
- **Description:** Enrich each contribution flag with context: is this donor's $500 one of many small donations (grassroots) or their only political contribution (targeted)? Employer donation pattern detection. Context transforms raw flags into intelligence.
- **Publication:** Graduated.

---

## Sprint 6 — Pattern Detection

*Cross-referencing that finds what single-meeting analysis can't see.*

**Why here:** Requires vote categorization (S2) and financial intelligence (S5). Coalition analysis and cross-meeting patterns are the "wow" features, but they need the data foundation beneath them.

### S6.1 Coalition/Voting Pattern Analysis [was 2.2]
- **Paths:** A, B, C
- **Description:** SQL aggregation on categorized votes. Who votes together on what issues, progressive vs. business-aligned blocs, historical alignment shifts.
- **Depends on:** S2.1 (vote categorization).
- **Publication:** Graduated. Coalition framing is politically sensitive.

### S6.2 Cross-Meeting Pattern Detection [was 3.1]
- **Paths:** A, B, C
- **Description:** "Same donor appears in 3 meetings in 6 months, always on infrastructure items." Time-series analysis over the structured core.
- **Depends on:** S2.1 (categories for meaningful pattern grouping).
- **Publication:** Graduated.

### S6.3 Council Time-Spent Stats v1 [was 2.3]
- **Paths:** A, B, C
- **Description:** Category distribution, vote counts by category, controversy score (split vs. unanimous). Just SQL on categorized data.
- **Depends on:** S2.1.
- **Schema ready:** `discussion_duration_minutes` and `public_comment_count` nullable fields on `agenda_items`.
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

---

## Backlog — Data Foundation & Scale

*Items without sprint assignment. Ordered by likely execution sequence. Pulled into sprints during weekly/milestone reviews.*

### Data Foundation

| ID | Item | Paths | Depends On | Notes |
|----|------|-------|------------|-------|
| B.1 | RAG Search (pgvector) [was 4.3] | A, B, C | S1.4 (archive data) | Embedding pipeline + search UI. Prerequisite for Charter compliance, stakeholder mapping. |
| B.2 | Board/Commission Member Profiles [was 4.5] | A, B, C | S1.3 (commission pages) | Extend `officials` profiles beyond council. 30+ commissions. |
| B.3 | Website Change Monitoring [was 5.1] | B, C | — | Periodic snapshots, diff detection, alert on changes. Start with commission rosters, policy pages. |
| B.4 | News Integration & Article Linking [was 5.4] | A, B, C | B.6 (media registry) | Associate agenda items with news coverage. |
| B.5 | Media Source Research Pipeline [was 5.2] | B, C | — | Automated discovery of local media sources per city. |
| B.6 | Per-City Media Source Registry [was 5.3] | B, C | B.5 | Structured `media_sources` table with credibility tiers. |
| B.7 | Local Media Monitoring [was 5.5] | A, B, C | B.4, B.6 | Auto-assemble context when local news breaks. |
| B.8 | Video Transcription Backfill [was 5.7] | A, C | — | Granicus archive 2006-2021. Budget-dependent. |
| B.9 | Email Alert Subscriptions [was 4.6] | A, B | B.1 (RAG) | Requires user accounts. |
| B.22 | `bodies` Table + body_id on Meetings/Votes | A, B, C | S1.3 (commission pages) | Formalize governing body model. All meeting/vote/attendance records get `body_id` FK. Schema accommodation for unified decision index. Source: FUTURE_IDEAS-2. |
| B.23 | Civic Role History (`civic_roles` table) | A, B, C | S2.3 (bios) | Track full public service trajectory per person: elected, appointed, employee, candidate. Enriches bios, closes loop when commissioner runs for council. Source: FUTURE_IDEAS-2. |

### Deep Intelligence

| ID | Item | Paths | Depends On | Notes |
|----|------|-------|------------|-------|
| B.10 | Court Records / Tyler Odyssey [was 3.3] | A, B, C | S5.1 (Form 700) | Research first: confirm Odyssey for Contra Costa County. |
| B.11 | City Charter Compliance Engine [was 3.4] | A, B, C | S1.3, B.1 (RAG) | Charter as the city's CLAUDE.md. |
| B.12 | Stakeholder Mapping & Coalition Graph [was 3.5] | A, C | B.1 (RAG), S5.1 | Graph problem: entities have positions on issues. |
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
| B.16 | Cross-City Policy Comparison [was 6.3] | A, B, C | B.1 (RAG), 3+ cities | Killer feature for horizontal scaling. |
| B.17 | Civic Website Modernization [was 6.4] | A, B, C | 5-10 cities running | Different product, different buyer. |
| B.18 | Civic Knowledge Graph [was 6.5] | B, C | B.1, B.10, B.12 | Entity-relationship graph across all data. |
| B.19 | Domain Strategy [was 6.6] | — | Before public launch | .city, .fyi, .ai domain decisions. |
| B.20 | System Definition Portability [was 6.7] | B | Model competition event | CLAUDE.md hierarchy as model-agnostic metadata. |
| B.21 | Open Source with BSL License (NEW) | A, B, C | Before public launch | Make repo public under Business Source License 1.1. Enables free GitHub features (branch protection), aligns with transparency mission, builds civic tech credibility. BSL prevents commercial competition while allowing visibility. Requires: move BUSINESS-MODEL.md to private location, choose Additional Use Grant (non-commercial vs non-production only), set Change Date (3-4 years → Apache 2.0). Moat is data/operations/relationships, not code. See 2026-02-24 session analysis. |
| B.28 | Newsletter Discovery & Ingestion Pipeline | A, B, C | Scale phase | Automated discovery → subscribe → ingest for council member newsletters. Tom Butt E-Forum is Richmond test case (Tier 3). `source_type = 'newsletter'` should be valid from day one. Source: FUTURE_IDEAS-2. |
| B.29 | Cityside/Richmondside Partnership | A, B, C | Post Phase 1 validation | Cityside runs Richmondside, Berkeleyside, The Oaklandside. Mission-aligned hyperlocal nonprofit journalism. Partnership shapes: data provider → funded Bay Area pilot. Research contacts after validation. Source: FUTURE_IDEAS-2. |
| B.30 | Path D: B2B Municipal Data API | B, C | Stable schema, multi-city | Same extraction pipeline, different API consumer (sales teams selling to city governments). B2B revenue subsidizes free civic tier. Don't let B2B feature requests drive extraction priorities. Related to B.14 (External API). Source: FUTURE_IDEAS-2. |

### Hygiene (Weave In As Needed)

Items that aren't sprint-worthy standalone but should be addressed opportunistically:

| ID | Item | Trigger |
|----|------|---------|
| H.1 | Clean up deprecated sync-pipeline.yml [was 0.2] | Next cleanup session |
| H.2 | ~~Architecture Self-Assessment / Tenets Audit [was 0.3]~~ | ✅ Done (2026-02-27). `system_health.py` with doc benchmark, architecture analysis, git metrics, trend comparison. |
| H.3 | Auto-Documentation of Decisions [was 0.4] | Next skill refinement |
| H.4 | Research Session Auto-Persist [was 0.5] | Next pure research session |
| H.5 | System Writes Its Own CLAUDE.md [was 0.6] | After restructuring stabilizes |
| H.6 | Automated Prompt Regression Testing [was 0.7] | Next prompt template change |
| H.7 | Session Continuity Optimization [was 0.8] | Next context-loss incident |
| H.8 | AI-Driven Persona Testing [was 4.7] | After frontend MVP stable |
| H.10 | Information Design Philosophy & Overarching Redesign | After private beta with user feedback. Holistic review of how info-dense civic data communicates to lay people. Inputs: real user feedback, AI-driven persona testing (H.8), data visualization best practices. This is the "how do we present all this" question. Don't attempt before having real data and real users. Source: S2 brainstorming session. |
| H.9 | Gated Feature Entry-Point Audit Checklist (NEW) | Private beta launch. Formalize a checklist for all surfaces a gated feature touches (nav links, routes, direct URLs, API endpoints). Origin: S1 post-mortem. |
| H.11 | eSCRIBE Item 0.2.a Text Block Formatting | Next scraper refinement session. Some agenda items contain large unformatted text blocks from eSCRIBE (entire staff report text inlined). Need readability formatting (paragraph breaks, structured sections). Origin: 2026-02-26 follow-up item 3b. |

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

## Readiness Signals (check before each sprint)

_Added 2026-02-27. These are the signals that tell us we're ready to ship features, not just build infrastructure. Run `cd src && python system_health.py` for the latest._

### Outward-facing (product quality) — the bottleneck as of 2026-02-27

| Signal | Measures | How to check | Status |
|--------|----------|-------------|--------|
| Citizen-facing commit ratio | % of commits touching `web/src/app/` (not api/) | Git log analysis | Not yet tracked |
| Data accuracy score | Do conflict flags match ground truth? | Spot-check 10 flags against manual review | No systematic measurement |
| Pages live & validated | Public pages with validated data | Manual inventory | ~5-6 pages, validation status unclear |
| Time-to-useful for new visitor | Can someone learn something valuable in 60s? | User testing (judgment call) | Needs real user feedback |

### Inward-facing (system health) — healthy as of 2026-02-27

| Signal | Measures | How to check | Baseline |
|--------|----------|-------------|----------|
| Doc benchmark score | Does CLAUDE.md tree find the right context? | `python system_health.py` | 93% |
| Test coverage | Can we ship with confidence? | `python system_health.py` | 66% (13 untested modules) |
| Sprint velocity | Features specced vs shipped | Sprint completion review | S1 complete, S2 in progress |
| City #2 onboarding friction | Hours to add a second city | Estimate from `city_config` coupling | Not tested yet |

### Risk register

| Risk | Tenet threatened | Signal to watch | Current status |
|------|-----------------|----------------|---------------|
| Navel-gazing | T4 (Richmond is the ideal) | Meta-commit ratio > 30% | At boundary — meta work should not grow |
| Credibility cliff | Sunlight not surveillance | Data accuracy on published flags | Unvalidated — highest priority gap |
| Over-abstraction | T1 vs T4 tension | `city_config` coupling count | 11 importers (stable) |
| Unfunded mandate | Revenue model | Time to onboard city #2 | Unknown — needs testing |

## Reprioritization Cadence

- **Milestone-triggered:** After completing any sprint, review the next sprint's items and the backlog before starting.
- **Weekly fallback:** If no milestone in the past 7 days, do a lightweight review of sprint order and backlog.
- **Evidence-based:** Run `python system_health.py` at session start. If trend comparison shows regression, investigate before building new features.
- **Deep restructure:** When significant new capabilities change what's possible (new model, new data source, architectural shift). This document was created during the first deep restructure on 2026-02-23.
- **2026-02-25 intake:** Added B.22-B.30 and future table designs from FUTURE_IDEAS-2 brainstorm (elections, position tracking, municipal code versioning, unified decision index, civic roles, newsletter pipeline, partnerships, B2B API). No sprint reassignments; all parked in backlog with dependency links.
- **2026-02-26 intake:** Parked H.11 (eSCRIBE text block formatting), B.31 (agenda vs. minutes diff). Added next-session note on S2.2 for category click-to-filter on meeting detail pages. Origin: procedural reclassification follow-up session.
- **2026-02-27 review:** Built system health self-assessment module. Established readiness signals and risk register. Assessment: inward-facing signals are healthy, outward-facing signals are the bottleneck. Next sessions should prioritize S2/S3 citizen-facing features over meta-infrastructure.
