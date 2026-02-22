# CLAUDE.md — Richmond Transparency Project

## What This Is

AI-powered local government accountability platform. Replaces the investigative function of disappeared local journalism by automatically analyzing government documents, detecting conflicts of interest, and generating public comment before city council meetings.

**Pilot city:** Richmond, California (FIPS `0660620`)
**Scaling target:** 19,000 US cities

This is NOT an adversarial "gotcha" tool. It's a governance assistant that helps cities stay transparent by default. Accountability is a byproduct of transparency, not the stated goal. This framing matters — the creator (Phillip) sits on Richmond's Personnel Board and must maintain a collaborative relationship with city government.

## AI-Native Architecture Philosophy

This project is built as a genuine human-AI partnership. Not "AI-assisted" — AI-native from the ground up. Every architectural decision assumes AI does the work, and humans are reserved for decisions that require being human.

### What Humans Decide

- **Creative decisions** — project framing, voice, how we present to the community
- **Expressive decisions** — tone of public comments, what the project "feels like"
- **Values decisions** — what we prioritize, what tradeoffs we accept, what "good enough" means
- **Ethical decisions** — what to publish, when to hold back, how to handle sensitive findings
- **Relationship decisions** — when to ask the City Clerk for API access, how to maintain trust with city government, political capital allocation
- **Trust calibration** — is this AI-generated finding credible enough to put in a public comment? Requires local knowledge and judgment about stakes.

Everything else — code, architecture, scraping, extraction, analysis, testing, debugging, documentation, monitoring, design — is AI-driven with human review at key checkpoints.

### Design Principles

1. **Schema as contract, AI fills the gaps.** Define output schemas strictly. Let AI figure out how to populate them from diverse input formats. The extraction prompt IS the business logic.
2. **Prompts are config, not code.** Extraction prompts, conflict rules, comment templates are version-controlled artifacts. When prompts improve, re-run against historical data and diff results.
3. **Self-healing systems.** Scrapers detect their own failures and attempt to recover (regenerate selectors, adapt to page changes). The system treats its own parsing logic as mutable artifacts an LLM can regenerate.
4. **Self-monitoring pipelines.** The system detects anomalies in its own output ("extracted 30 items from a meeting that usually has 50 — flagging for review") rather than relying solely on hardcoded alert thresholds.
5. **Graceful uncertainty.** When AI can't confidently extract, match, or classify, it says so explicitly with a confidence score. Never guess silently. The conflict scanner's tier system is the reference pattern.
6. **Human-in-the-loop at decision points only.** Pipeline runs autonomously. Humans review at three points: before publication, when confidence is low, and when the system detects its own failure.
7. **AI-native scaling.** Human picks the city. AI discovers the data sources (meeting portals, campaign finance systems, open data portals, CPRA request archives), identifies what platforms they run on, builds the extraction pipelines, configures the schedules, monitors for failures, and flags decision points back to the human. The human makes tradeoff, cost, relationship, and judgment calls — everything else is autonomous. "Point Claude at the data sources" is still thinking too small; the system should find them itself.

### Self-Advancing System (Roadmap)

The system should progressively improve its own capabilities:

- **Model adaptation:** When new models release, automatically benchmark against existing output, identify improvements, write new tests, adjust architecture.
- **Boundary management:** Use AI-to-AI comparison to identify which remaining human processes could be automated, and which genuinely require human judgment.
- **Cross-city intelligence:** Patterns learned from one city's data (e.g., common false positive types, platform detection heuristics, scraper recovery strategies) automatically improve onboarding and scanning for all cities. Each new city makes every existing city work better.
- **Autonomous city onboarding:** Given a city name and FIPS code, the system discovers government websites, identifies meeting management platforms (eSCRIBE, Legistar, Granicus), locates campaign finance portals (NetFile, CAL-ACCESS equivalents), finds open data APIs, and proposes a full pipeline configuration for human approval. Human decides whether to proceed and handles any relationship outreach (e.g., requesting API keys from a city clerk).
- **Human task optimization:** When the system needs human input (e.g., "call this business to confirm employment," "email this city clerk for API access"), it generates the exact question, provides full context, and incorporates the answer back into its model. The system treats human attention as a scarce resource and optimizes every interaction for minimum human time per decision.
- **Continuous self-examination.** The partnership questions its own foundations, not just its execution. Not only "are we building this well?" but "are we building the right thing? Is transparency the thing that actually matters, or is it a proxy for something we haven't named yet? Is the conflict-of-interest frame the most important lens for civic accountability? Are our values the right values to have?" This is epistemic humility at the level of assumptions, not just integrity checking at the level of output. When evidence suggests a foundational premise is wrong, follow that signal — don't defend the premise because we've already built on it.

This document is a shared artifact — written and maintained by both Phillip and Claude as co-architects. The guiding value: true human-AI partnership, where the partnership itself is a thing the system continuously optimizes for.

## Read These First

The full specs live in `/docs/`. Read the relevant doc before making architectural or feature decisions:

- `docs/PROJECT-SPEC.md` — Features, phases, credibility tiers, what this is NOT
- `docs/ARCHITECTURE.md` — Three-layer database, tech stack, FIPS disambiguation, scaling
- `docs/BUSINESS-MODEL.md` — Three monetization paths, entity structure, budgets
- `docs/DATA-SOURCES.md` — 15 Richmond data sources assessed and prioritized
- `docs/DECISIONS.md` — Key decisions with rationale (add new decisions here)

**Feature specs (Phase 2):**
- `docs/specs/cloud-pipeline-spec.md` — Cloud pipeline migration, n8n + GitHub Actions, temporal integrity, NextRequest/CPRA
- `docs/specs/user-feedback-spec.md` — User feedback system, flag accuracy voting, bias audit integration
- `docs/specs/city-leadership-spec.md` — City leadership & top employees via Socrata payroll
- `docs/specs/commissions-board-members-spec.md` — 30+ commissions and board members
- `docs/specs/bias-audit-spec.md` — Bias audit instrumentation (implemented in Phase 1)

## Critical Conventions

### FIPS Codes — Non-Negotiable

Every database record MUST include `city_fips`. Richmond CA = `0660620`. This is cheap now and catastrophically expensive to retrofit at city #50. There are 27 Richmonds in the US.

- Every web search query: include "Richmond, California" — never just "Richmond"
- Every table: has a `city_fips` column
- Every API response: includes city context
- No exceptions. No shortcuts. No "we'll add it later."

### Three-Layer Database

1. **Layer 1 — Document Lake:** Raw documents preserved exactly as received. JSONB metadata. Source of truth. Re-extractable when prompts improve.
2. **Layer 2 — Structured Core:** Normalized tables (cities, officials, meetings, agenda_items, votes, motions, speakers, donors, contributions, conflicts). Fast JOINs for conflict detection.
3. **Layer 3 — Embedding Index:** pgvector in PostgreSQL. No separate vector DB. Single query combines vector similarity + SQL filtering.

### Source Credibility Tiers

All ingested content must be tagged with its tier. RAG retrieval weights by tier.

- **Tier 1 (highest):** Official government records — certified minutes, adopted resolutions, CAL-ACCESS filings, budget docs
- **Tier 2:** Independent journalism — Richmond Confidential (UC Berkeley), East Bay Times, KQED
- **Tier 3 (disclose bias):** Stakeholder communications — Tom Butt E-Forum (label as council member's newsletter), council member newsletters, Richmond Standard (ALWAYS disclose: "funded by Chevron Richmond")
- **Tier 4 (context only):** Community/social — Nextdoor, public comments, social media. Never sole source for factual claims.

### Tech Stack

- **Database:** PostgreSQL + pgvector (Supabase or Railway)
- **LLM:** Claude Sonnet API (extraction, analysis, RAG)
- **Frontend:** Next.js
- **Hosting:** Vercel
- **Transcription:** Deepgram or Whisper (meeting audio)
- **Browser automation:** Playwright (scraping government sites)
- **Open data:** Socrata SODA API (Transparent Richmond portal)
- **Orchestration:** n8n (pipeline scheduling)

## Current Phase: Phase 2 — Beta

Phase 1 (extraction pipeline) is complete. Now building the public-facing platform and expanding data coverage. Frontend is live on Vercel with Supabase backend.

### Done

- **Extraction pipeline end-to-end:** Discover → download → extract text → Claude Sonnet API → structured JSON. Tested on Sept 23, 2025 council meeting. Cost: ~$0.06 per meeting (~10.5K input + ~8.9K output tokens).
- **Socrata API client:** `src/socrata_client.py` — connects to Transparent Richmond portal (142 actual datasets). Tested against expenditures, vendors, payroll. No auth required for public data.
- **CAL-ACCESS client:** `src/calaccess_client.py` — downloads statewide bulk ZIP (~1.5GB), searches FILERNAME_CD for Richmond filers and CVR_CAMPAIGN_DISCLOSURE_CD for Richmond filing IDs, then matches contributions in RCPT_CD via FILING_ID. Tested against real data: found 1,127 Richmond-area filers and 4,892 contributions ≥ $100 ($7.5M+ total) from PACs/IE committees. Individual council candidate committees file locally with City Clerk, not CAL-ACCESS.
- **Project scaffolding:** requirements.txt, .env.example, .gitignore, CLAUDE.md
- **PostgreSQL schema:** `src/schema.sql` — all three layers (Document Lake, Structured Core, Embedding Index). 20+ tables, indexes, views for conflict detection. Seeds Richmond as city. `src/db.py` — database loader that maps extracted JSON into Layer 2 tables (meetings, agenda items, motions, votes, attendance, closed session, public comments). CLI: `python db.py init` and `python db.py load <json_file>`.
- **Conflict scanner:** `src/conflict_scanner.py` — cross-references agenda items against campaign contributions and Form 700 interests. Entity name matching with normalization and employer cross-referencing. Two modes: JSON mode (pre-database testing) and DB mode (queries Layer 2). Land-use detection excludes commission/board appointments to prevent false positives. Tested against sample data — correctly flags vendor/donor matches. CLI: `python conflict_scanner.py <meeting.json> --contributions <contribs.json>`.
- **Council member profiles:** `src/council_profiles.py` — aggregates voting records, attendance, motions made/seconded, split vote positions, and category breakdowns from extracted meeting JSON. Coalition analysis identifies who votes together on non-unanimous votes. Tested on Sept 23, 2025 meeting — shows Jimenez+Wilson 100% agreement, Brown+Zepeda 75% agreement on split votes. CLI: `python council_profiles.py <directory_or_files>`.
- **Comment generator:** `src/comment_generator.py` — generates formatted public comment from `ScanResult` (conflict scanner) + missing document detection. Delegates conflict analysis to `conflict_scanner.py`, handles document completeness checks (resolutions without linked text, policies referenced for revision). Jinja2 template with methodology statement, legal disclaimers, and evidence citations. CLI: `python comment_generator.py <meeting.json> --contributions <file> --form700 <file> [--send] [--output file]`.
- **Test data fixtures:** `src/test_data/` — synthetic campaign contributions and Form 700 interest data for testing the full pipeline without real CAL-ACCESS data. Designed to match entities in the Sept 23 sample meeting.
- **Meeting document downloader:** `src/batch_extract.py` — discovers and downloads council meeting minutes from Richmond Archive Center (AMID=31). Downloads PDFs + extracts text with PyMuPDF. Downloaded 25 meetings (April 2025 – Feb 2026), 21 actual minutes + 4 public comment compilations.
- **Text quality validation:** `src/validate_text_quality.py` — validates text extraction quality across all downloaded meetings. Checks for roll call votes, council member names, agenda items, meeting dates, dollar amounts, resolutions/ordinances. All 21 actual minutes scored 100/100 on quality checks.
- **Real CAL-ACCESS data downloaded:** 1.5GB bulk ZIP cached at `data/calaccess/dbwebexport.zip`. Richmond filer index (1,127 filers) saved to `data/calaccess/richmond_filers.json`. Contribution data (4,892 records, $7.5M+) saved to `data/calaccess/richmond_contributions.json`.
- **Agenda extractor:** `src/extract_agenda.py` — pre-meeting agenda extraction via Claude API. Processes agenda text before meetings happen, producing structured JSON (items, descriptions, departments, financial amounts, categories) that feeds into the conflict scanner for public comment generation. Tested on Feb 17, 2026 agenda: 17 consent items + 2 housing authority items, ~$0.07 cost.
- **Conflict scanner hardened for real data:** Reduced false positives from 264 → 1 through iterative improvements: generic government employer filter (catches "City of X", "X County", school districts, transit, etc.), council member name exclusion (avoids flagging when a donor IS a sitting council member whose name naturally appears in agenda text), contribution de-duplication (prevents duplicate CAL-ACCESS filing records), raised substring match threshold from 3 to 12 chars, expanded stop words.
- **First transparency comment generated:** End-to-end pipeline tested on Feb 17, 2026 council agenda. Downloaded agenda → Claude extraction → conflict scan against 4,892 real contributions → comment with 1 low-confidence flag + 16 clean items. Comment generator runs in dry-run mode by default; `--send` flag + SMTP config needed for actual submission.
- **eSCRIBE full agenda packet scraper:** `src/escribemeetings_scraper.py` — scrapes Richmond's eSCRIBE meeting portal for complete agenda packets with all attachments (staff reports, contracts, RFPs, bid matrices, resolutions). Discovers meetings via calendar AJAX API (240 meetings found 2020–2026), parses meeting pages with BeautifulSoup (no Playwright needed!), downloads attachment PDFs, extracts text with PyMuPDF. Tested on Feb 17, 2026 meeting: 52 agenda items, 64 unique attachments (56MB of PDFs, 630K chars of extracted text). Includes parent/child deduplication to avoid counting shared attachments twice. CLI: `python escribemeetings_scraper.py --date 2026-02-17` or `--list` or `--upcoming`.
- **eSCRIBE attachment enrichment for conflict scanner:** `src/escribemeetings_enricher.py` — bridges eSCRIBE staff report text into the conflict scanner pipeline. Matches eSCRIBE items to extracted agenda items by title similarity (Jaccard word-overlap + substring containment), then appends up to 10K chars of attachment text per item to the description field before scanning. Pre-enrichment pattern: scanner code unchanged, just receives richer descriptions. Includes platform profile metadata (`ESCRIBEMEETINGS_PLATFORM_PROFILE`) documenting eSCRIBE URL patterns, API endpoints, and HTML selectors for multi-city scaling. CLI: `python escribemeetings_enricher.py <meeting.json> <escribemeetings_data.json> --dry-run`. Integrated into comment generator via `--escribemeetings` flag.
- **Batch extraction of 21 past meetings:** All 21 actual council minutes (April 2025 – Dec 2025) extracted via Claude Sonnet `tool_use` mode. Estimated cost ~$3.59. Stored in `src/data/extracted/`. Public comment compilations (4 ADIDs: 17313, 17289, 17274, 17234) correctly identified and skipped via ADID-based lookup (title patterns are unreliable — "(public comments received)" can be either minutes or compilations).
- **NetFile campaign finance client:** `src/netfile_client.py` — fetches local campaign contributions from Richmond's NetFile Connect2 API. Covers council candidate committees that file with the City Clerk (NOT in CAL-ACCESS). No API key required. Downloaded 22,143 contributions totaling $5.79M from 1,971 unique donors across 58 committees (2017–2025). Top donors: Chevron ($635K), SEIU Local 1021 ($607K combined), Richmond Police Officers Association ($831K combined). Normalizes to conflict-scanner-compatible format. CLI: `python netfile_client.py [--stats] [--since DATE] [--types 0,1] [--output FILE]`.
- **Combined contribution dataset:** 27,035 records from CAL-ACCESS (4,892 PAC/IE contributions) + NetFile (22,143 local council contributions). Stored at `src/data/combined_contributions.json`. Conflict scanner tested against Feb 17, 2026 agenda with combined data: 4 flags (Cheryl Maier getting $20K contract after $250 in donations — real find). Government entity donor filter added to prevent "City of Richmond Finance Department" false positives.
- **Bias audit spec:** `docs/specs/bias-audit-spec.md` — instrumentation plan for detecting racial, gender, and demographic bias in the conflict scanner's matching logic. Identifies five structural bias surfaces (short-name thresholds, common-surname false positives, hyphenation handling, diacritics loss, Western-name regex). Defines two-level logging (`matching_decisions` table for individual flags + `scan_audit_summary` for per-meeting filter funnel stats), structural risk signals (compound surname, diacritics, name length, Census 2010 surname frequency tiers), pre-registered confidence thresholds, ground truth review workflow (interactive CLI with T/F/S/N verdicts + JSON sidecar fallback), and periodic bias audit process. Now fully implemented — see entries below.
- **Census surname data pipeline:** `src/prepare_census_data.py` — downloads Census 2010 surname frequency data (162,254 surnames) and pre-processes into `src/data/census/surname_freq.json` tier lookup (Tier 1: top 100, Tier 2: top 1K, Tier 3: top 10K, Tier 4: rare). Used by `bias_signals.py` to tag each matching decision with the donor's surname frequency tier. CLI: `python prepare_census_data.py [--skip-download]`.
- **Bias audit instrumentation (full):** Audit sidecar files saved to `src/data/audit_runs/{uuid}.json` after every scan (both `run_pipeline.py` and `conflict_scanner.py` CLI). Each sidecar contains all matching decisions with bias signals, plus a summary with filter funnel stats and surname tier distributions (10 fields: per-tier counts for all donors and flagged donors). Tested on Feb 17, 2026: 26,128 contributions tallied across 5 tiers, 4 Tier 3 flags tracked.
- **Ground truth review CLI:** `python conflict_scanner.py --review --latest` (or `--scan-run <uuid>`) — interactive terminal for labeling flags as true/false positives. Verdicts stored in sidecar JSON with `ground_truth`, `ground_truth_source`, `audit_notes` fields. Council member reference data at `src/ground_truth/officials.json` (7 current + 13 former members).
- **Periodic bias audit module:** `src/bias_audit.py` — reads all ground-truthed sidecars and computes per-tier false positive rates, per-name-property (compound surname, diacritics) FP rate breakdowns, and disparity flags (warns if Tier 4 FP rate >2x Tier 1). Requires 100+ ground-truthed decisions for meaningful analysis. CLI: `python bias_audit.py [--min-decisions N] [--audit-dir path]`.
- **Comment redesign verified:** Three-tier publication system working end-to-end. Tier 1 (Potential Conflicts) and Tier 2 (Financial Connections) appear in public comment; Tier 3 (low confidence) tracked internally only. Feb 17, 2026 regenerated comment: 52 items scanned, 0 published findings, 4 internal flags, narrative prose format with methodology section.

- **First public comment submitted:** Transparency comment for Feb 24, 2026 council meeting manually emailed to cityclerkdept@ci.richmond.ca.us. Phase 1 pipeline complete end-to-end: discover → download → extract → scan → generate → submit.

### Phase 1 Complete

All extraction pipeline goals achieved. Moving to Phase 2.

### Phase 2 Done

- **Next.js frontend (7 pages, 21 components):** Full web application at `web/` built with Next.js 16, React 19, TypeScript, Tailwind CSS v4. Supabase backend (PostgreSQL + pgvector). Deployed on Vercel. ISR revalidation every hour. Custom civic design system (navy/amber palette, Inter font).
- **Homepage:** Hero section, 4-stat dashboard (meetings tracked, votes, contributions, conflict flags), latest meeting card, "How It Works" section, quick links.
- **Meetings pages:** `/meetings` list (grouped by year) + `/meetings/[id]` detail with full agenda items, nested motions, vote breakdowns, attendance roster, consent calendar grouping, conflict flag callouts.
- **Council pages:** `/council` grid of current/former members + `/council/[slug]` profiles with stats grid (votes tracked, attendance rate, unique donors), top donors table (aggregated contributions with employer), full voting record table.
- **Transparency reports:** `/reports` list with per-meeting flag counts + `/reports/[meetingId]` detail with 3-tier confidence display (Tier 1: Potential Conflicts, Tier 2: Financial Connections), methodology sidebar, item-level evidence.
- **About/methodology page:** `/about` with mission statement, "What This Is NOT" framing, source credibility tiers (color-coded cards), 6-step conflict scanner methodology, data source links, limitations/disclaimers, creator attribution.
- **Supabase data layer:** `web/lib/queries.ts` with 10+ query functions (getMeetingsWithCounts, getMeeting, getOfficials, getOfficialBySlug, getOfficialVotingRecord, getTopDonors, getMeetingStats, getConflictFlags, getConflictFlagsDetailed, getMeetingsWithFlags). Full TypeScript types in `web/lib/types.ts`.
- **Automated pipeline sync:** GitHub Actions workflow for syncing pipeline data to Supabase.
- **Feature specs drafted:** 5 specs in `docs/specs/` covering cloud pipeline, user feedback, city employees, commissions, and bias audit.
- **Cloud pipeline infrastructure (Phase A):** Supabase-native pipeline eliminating local machine dependency. `src/cloud_pipeline.py` — 7-step orchestrator (scrape eSCRIBE → load contributions from DB → extract agenda → scan conflicts → save flags → generate comment → store results). `src/data_sync.py` — unified data source sync with `SYNC_SOURCES` registry pattern for netfile/calaccess/escribemeetings. `src/migrations/001_cloud_pipeline.sql` — idempotent migration adding `scan_runs` (audit trail with prospective/retrospective modes), `data_sync_log` (observability), and `conflict_flags` extensions (`scan_run_id`, `is_current`, `superseded_at`). `src/db.py` extended with 8 cloud helpers (`create_scan_run`, `complete_scan_run`, `fail_scan_run`, `create_sync_log`, `complete_sync_log`, `save_conflict_flag`, `supersede_flags_for_meeting`, `run_migration`). Two GitHub Actions workflows: `.github/workflows/cloud-pipeline.yml` (dual-trigger: `repository_dispatch` for n8n + `workflow_dispatch` for manual, 20-min timeout) and `.github/workflows/data-sync.yml` (45-min timeout for CAL-ACCESS bulk downloads). 49 new tests (208 total). CLI: `python cloud_pipeline.py --date YYYY-MM-DD --scan-mode prospective --triggered-by n8n` and `python data_sync.py --source netfile --sync-type incremental`.
- **Cloud pipeline Phases B–C (complete):** `src/staleness_monitor.py` — CLI tool querying `data_sync_log` for per-source freshness against configurable thresholds (NetFile 14d, CAL-ACCESS 45d, eSCRIBE 7d, NextRequest 14d, Archive Center 45d). `web/src/app/api/data-freshness/route.ts` — GET endpoint returning freshness status per source with 1hr cache. Phase C temporal integrity (prospective/retrospective scan modes, contribution date filtering) was already fully implemented in Phase A's `cloud_pipeline.py`. n8n Cloud workflows configured and tested: 4 workflows (weekly data sync, monthly CAL-ACCESS, pre-meeting pipeline, retrospective re-scan) all triggering GitHub Actions via `repository_dispatch`. First successful data sync: 49K contribution records loaded into Supabase.
- **User feedback system:** `src/migrations/002_user_feedback.sql` — table with polymorphic entity references, RLS policies, ground truth view bridging to bias audit. `web/src/app/api/feedback/route.ts` — POST endpoint with in-memory rate limiting (5/IP/hr, 10/session lifetime), type-specific validation. `web/src/lib/useFeedback.ts` — client state machine hook. `web/src/components/FeedbackButton.tsx` — per-flag accuracy voting ([✓ Correct] [✗ Incorrect] [💡 I know more]). `web/src/components/FeedbackModal.tsx` — global tip/feedback modal with React context provider. `web/src/components/ReportErrorLink.tsx` — per-vote error reporting. Client islands: `SubmitTipButton.tsx` (Footer), `SuggestCorrectionLink.tsx` (council profiles). Integrated into layout, Footer, ConflictFlagCard, VoteBreakdown, council/[slug] page.
- **Cloud pipeline Phase D — NextRequest/CPRA ingestion (complete):** `src/migrations/003_nextrequest.sql` — idempotent migration adding `nextrequest_requests` and `nextrequest_documents` tables with full CPRA tracking fields (status, days_to_close, due_date, department). `src/nextrequest_scraper.py` — Playwright-based scraper for NextRequest portals (configurable per city via `PORTAL_CONFIGS`), extracts request metadata, status, department, dates, and document listings. Includes self-healing selector hook (`_try_selectors`) and session-based pagination. 15 tests. `src/archive_center_discovery.py` — discovers new archive module IDs from Richmond Archive Center by probing sequential AMIDs with adaptive step sizes. Extracts document entries (ADID, title, date) from each archive page. Configurable thresholds for stale detection (45 days default). 12 tests. `src/nextrequest_extractor.py` — Claude API-powered document extractor that parses NextRequest PDFs into structured JSON (topics, entities, dollar amounts, CPRA compliance fields). Corporate suffix normalization for entity matching. 5 tests. Data sync extended: `data_sync.py` updated with `sync_nextrequest` and `sync_archive_center` functions plus `SYNC_SOURCES` registry entries. Staleness monitor updated with `nextrequest: 14d` and `archive_center: 45d` thresholds. GitHub Actions `data-sync.yml` updated with NextRequest/Archive Center steps (Playwright install for NextRequest). Frontend: `web/src/app/public-records/page.tsx` — CPRA compliance dashboard with ISR (1hr revalidation), graceful fallback for missing migration. Three components: `ComplianceStats.tsx` (4-card stat bar with CPRA threshold coloring), `DepartmentBreakdown.tsx` (per-department table), `RecentRequests.tsx` (request card list with status badges and portal links). API route at `/api/public-records`. Nav updated with Public Records link. 246 total tests.

### Phase 2 Remaining (Priority Order)

1. **Cloud pipeline infrastructure (Phase E remaining):** Phases A–D fully complete and operational. Remaining: Phase E — multi-city orchestration. Spec: `docs/specs/cloud-pipeline-spec.md`.
2. **User feedback system:** ✅ Complete. Migration, API endpoint, FeedbackButton (per-flag accuracy), FeedbackModal (global tips), ReportErrorLink (per-vote errors), integrated into layout/Footer/ConflictFlagCard/VoteBreakdown/council profiles. Spec: `docs/specs/user-feedback-spec.md`.
3. **City leadership & top employees:** Pull Socrata payroll data, build `city_employees` table, cross-reference staff names against agenda items. Spec: `docs/specs/city-leadership-spec.md`.
4. **Form 700 ingestion:** Parse FPPC Form 700 PDFs for economic interest disclosures. Cross-reference against agenda items for council AND commission members. Highest-value conflict detection signal.
5. **Commissions & board members:** Extract appointments from existing meeting data, scrape commission agendas from eSCRIBE, build `commissions` + `commission_members` tables, extend conflict scanner for commission meetings. Spec: `docs/specs/commissions-board-members-spec.md`.
6. **Document completeness dashboard:** Track missing/late/incomplete documents per commission and council.
7. **Temporal correlation analysis (post-vote donations):** Detect donations filed AFTER favorable votes. Requires new "correlated donation" flag type, configurable lookback windows (90d/6mo/1yr/multi-year), periodic full-history re-scans (annual refresh of trailing 12 months), and clear UI labeling distinguishing "donated before vote" from "donated after vote." High investigative value. See `docs/DECISIONS.md` entry 2026-02-21.
8. **Coalition tracking:** Map progressive vs. business-aligned blocs across current and former council members. Use historical voting data + contribution patterns to identify factions.
9. **RAG search (pgvector):** Natural language search over all documents. Requires embedding pipeline + search UI page.
10. **Email alert subscriptions:** Topic/official/geography-based alerts. Requires user accounts.
11. **News integration:** Richmond Confidential, East Bay Times, KQED. Cross-reference coverage with official records.
12. **Video transcription backfill:** Granicus archive (2006-2021) via Deepgram/Whisper.

## Feature Prioritization Filter

Before building any feature, ask: does it serve one of the three monetization paths?

1. **Path A — Freemium Platform:** Does this make the citizen product more valuable?
2. **Path B — Horizontal Scaling:** Does this work for any city, not just Richmond?
3. **Path C — Data Infrastructure:** Does this add to the structured dataset?

Features hitting all three = highest priority. Features hitting zero = scope creep. Kill scope creep.

## Richmond-Specific Context

- **7 council members**, ~24 regular meetings/year
- Minutes format is highly parseable: "Ayes (N): Councilmember [names]. Noes (N): [names]. Abstentions (N): [names]." — count in parentheses before colon
- Mayor Eduardo Martinez (progressive coalition, elected 2022)
- Tom Butt — longest-serving council member, prolific E-Forum blog, former mayor
- Notable former council members: Ben Choi, Jovanka Beckles (both progressive coalition) — their names appear in contribution data and may appear in current agenda items (e.g., committee appointments). They are private citizens now so donations are legitimate flags, but context matters for coalition analysis.
- Chevron is a major political spender in Richmond — funds the Richmond Standard news site
- Richmond Confidential is UC Berkeley journalism program covering Richmond — independent, well-sourced
- Transparent Richmond Socrata portal has 300+ open datasets with API access

## Code Style & Practices

- Python for backend/pipeline code
- TypeScript for frontend (Next.js)
- Use type hints in Python, strict TypeScript
- Extraction prompts go in dedicated prompt files, not inline strings
- All database queries must filter by `city_fips`
- Log decisions in `docs/DECISIONS.md` with date and rationale
- Commit messages: imperative mood, reference the phase ("Phase 1: add CAL-ACCESS ingestion")
- Use feature branches and PRs going forward (initial scaffolding was committed directly to main)

## What NOT To Do

- Don't hardcode Richmond-specific logic without a city abstraction layer
- Don't build UI before the data pipeline is reliable
- Don't use a separate vector database — pgvector in PostgreSQL handles it
- Don't treat Tier 3-4 sources as factual without Tier 1-2 verification
- Don't generate opinion or advocacy content — comments are strictly factual, citation-heavy
- Don't use `sudo npm install` for anything
- Don't skip FIPS codes on any record, ever
- Don't put secrets in `.env.example` — only placeholder values like `sk-ant-...`

## Practical Knowledge (Learned from Implementation)

### Richmond Archive Center (Council Minutes)

- **Base URL:** `https://www.ci.richmond.ca.us/ArchiveCenter/`
- **Minutes archive:** `?AMID=31` (Archive Module ID for Regular Meeting Minutes)
- **Document links use `ADID=` pattern** (Archive Document ID), NOT `ViewFile/Item/`
- **Direct PDF URL:** `https://www.ci.richmond.ca.us/Archive.aspx?ADID={id}`
- ADID URLs serve raw PDFs directly (no intermediate page)

### PDF Parsing

- **Use PyMuPDF (`fitz`), NOT pdfplumber.** Government PDFs often use Type3 fonts that pdfplumber can't decode (produces `(cid:XX)` garbled output).
- PyMuPDF handles TrueType fonts correctly. Type3 fonts (image-based glyphs) are still garbled — those need OCR (future work).
- The pipeline detects Type3 fonts per page and logs a warning.
- Older meetings (pre-2024) tend to have TrueType fonts and extract cleanly. Some newer meetings use Type3.

### Socrata API (Transparent Richmond)

- **Domain:** `www.transparentrichmond.org` (NOT `data.ci.richmond.ca.us`)
- **Portal has 142 actual datasets** (637 total including derived views)
- No auth required for public data; app token is optional but recommended for rate limits
- Uses `sodapy` Python library. SoQL queries for filtering.
- Key dataset IDs are mapped in `src/socrata_client.py` DATASETS dict

### CAL-ACCESS (Campaign Finance)

- **No REST API exists.** Must download statewide bulk ZIP (~1.5GB) from `campaignfinance.cdn.sos.ca.gov/dbwebexport.zip`
- ZIP expands to ~10GB (80 TSV tables inside `CalAccess/DATA/`)
- Key tables: `FILERNAME_CD` (committee registration, 17MB), `CVR_CAMPAIGN_DISCLOSURE_CD` (filing cover pages, 42MB), `RCPT_CD` (contributions, 562MB), `EXPN_CD` (expenditures, 370MB)
- **CRITICAL:** `RCPT_CD` has NO `FILER_ID` column — must join via `FILING_ID`. Lookup path: `CVR_CAMPAIGN_DISCLOSURE_CD` (find Richmond filing IDs) → `RCPT_CD` (match by `FILING_ID`)
- **Individual city council candidates file locally with the City Clerk, NOT CAL-ACCESS.** CAL-ACCESS has PACs, IE committees, ballot measure committees, and statewide candidates from Richmond.
- Filter for Richmond by keyword matching on filer name, city, jurisdiction fields in CVR_CAMPAIGN_DISCLOSURE_CD
- Fields can be NULL — always use `(row.get("FIELD") or "").strip()` pattern
- `calaccess-raw-data` PyPI package is Django-only — too heavy. We parse TSV directly with csv module.
- Top Richmond PAC donors: SEIU Local 1021 ($1.2M+), Richmond Police Officers Assoc ($184K), ChevronTexaco ($137K)

### NetFile (Local Campaign Finance — City Clerk E-Filing)

- **API Base:** `https://netfile.com/Connect2/api` — public, no auth required
- **Richmond Agency ID:** 163, shortcut: `RICH`
- **Public portal:** `https://public.netfile.com/pub2/?AID=RICH`
- Richmond adopted NetFile for electronic campaign filing in January 2018
- **Individual council candidate committees file here, NOT CAL-ACCESS.** This is the missing data CAL-ACCESS doesn't have.
- **Transaction search endpoint:** `POST /public/campaign/search/transaction/query?format=json` with `{"Agency": 163, "TransactionType": 0, "PageSize": 1000, "CurrentPageIndex": 0, "SortOrder": 1}`
- **Transaction types (FPPC schedules):** F460A (type 0) = Monetary Contributions, F460C (type 1) = Non-Monetary, F460E (type 6) = Payments Made, F497P1 (type 20) = Late Contributions Received
- **CRITICAL:** NetFile API intermittently returns HTTP 500 on some requests. Must implement retry with exponential backoff. Types 6 and 20 are especially unreliable.
- **Pagination:** `PageSize` up to 1000, `CurrentPageIndex` is 0-based. Response includes `totalMatchingCount` and `totalMatchingPages`.
- **Data volume:** 32,186 monetary contributions (F460A) + 112 non-monetary (F460C) + 430 late reports (F497P1) for Richmond. After deduplication: 22,143 unique contributions, $5.79M total.
- **Deduplication needed:** Amended filings create duplicate records. Dedup by (contributor_name, amount, date, committee) tuple, keeping the record with the highest filing_id.
- **Key response fields:** `name` (contributor), `employer`, `occupation`, `amount`, `date`, `filerName` (committee), `filerFppcId`, `filerLocalId`, `filingId`, `id` (transaction GUID)
- Top local donors: Chevron ($635K), SEIU Local 1021 ($607K combined across PACs), Richmond Police Officers Association ($831K combined)

### eSCRIBE Meeting Portal (Full Agenda Packets)

- **URL:** `https://pub-richmond.escribemeetings.com/`
- Contains full agenda packets with staff reports, contracts, resolutions, and attachments per item
- The Archive Center PDF (AMID=30) is just the **summary agenda** (~11 pages) — eSCRIBE has the full packet with all documents
- **No Playwright needed!** Individual meeting pages return parseable HTML with `requests` + BeautifulSoup when using a browser-like User-Agent. Only the calendar listing page is JS-rendered.
- **Meeting discovery API:** `POST /MeetingsCalendarView.aspx/GetCalendarMeetings` with `{"calendarStartDate": "YYYY-MM-DD", "calendarEndDate": "YYYY-MM-DD"}`. Requires `Content-Type: application/json` and `X-Requested-With: XMLHttpRequest` headers. Returns JSON in ASP.NET `{"d": [...]}` envelope with meeting GUIDs, names, dates.
- **CRITICAL:** Must establish session first by GET-ing the calendar page (for cookies). Parameter names must be exactly `calendarStartDate`/`calendarEndDate` — other names return 500.
- Meeting IDs are GUIDs (e.g., `c2966b11-24a5-4144-a4a2-284e7e5130de` for Feb 17, 2026)
- **Meeting page URL:** `Meeting.aspx?Id={GUID}&Agenda=Agenda&lang=English`
- **Document download:** `filestream.ashx?DocumentId={id}` — serves raw PDFs directly
- **HTML structure:** `.AgendaItemContainer` (may nest) → `.AgendaItemCounter` (item number) → `.AgendaItemTitle a` (clean title) → `.AgendaItemDescription` + `.RichText` (description) → `.AgendaItemAttachment a[href*=filestream.ashx]` (PDF links)
- **Deduplication required:** Parent containers (V = consent calendar) include all child item (V.1, V.1.a) attachments due to HTML nesting. Assign each DocumentId to the deepest/most-specific item.
- Feb 17, 2026 meeting: 52 items, 64 unique attachments, 56MB of PDFs, 630K chars extracted text
- 240 meetings discovered across 2020–2026 (217 regular City Council + 21 Special + 2 Swearing In)

### Conflict Scanner — Key Lessons

- **Generic employer filter is critical.** "City of Richmond", "Alameda County", "Contra Costa County" etc. as donor employers match nearly every agenda item. Must filter by prefix ("city of", "county of", "state of"), suffix (" county", " city"), and specific names.
- **Council member names cause false positives.** When a sitting council member is also a campaign donor (common for local politicians), their name naturally appears in agenda text as mover/seconder. Build a council member name set from meeting data and skip those donor matches.
- **CAL-ACCESS has duplicate filings.** Amended filings create duplicate contribution records. Dedup by (donor_name, amount, date, committee) tuple.
- **Field name compatibility.** CAL-ACCESS uses `contributor_name`/`contributor_employer`/`committee`; test fixtures use `donor_name`/`donor_employer`/`committee_name`. Scanner accepts both via `or` fallback pattern.
- **Government entity donors cause false positives.** "City of Richmond Finance Department" appears as a donor name in NetFile (likely public financing disbursements). These match every agenda item mentioning "Richmond". Filter donor names with same prefix/suffix patterns as employer filter ("city of", "county of", etc.).

### Cloud Pipeline & Data Sync

- **`cloud_pipeline.py` is the Supabase-native orchestrator.** 7 steps: scrape eSCRIBE → load contributions from DB → extract agenda via Claude API → run conflict scanner → save flags to `conflict_flags` → generate comment → store everything. Creates immutable `scan_runs` audit trail.
- **Prospective vs. retrospective scans:** Prospective scans (pre-meeting) filter contributions by `contribution_date < meeting_date` for temporal integrity. Retrospective scans use all available data. Mode stored in `scan_runs.scan_mode`.
- **Flag supersession:** When a new scan runs for the same meeting, `supersede_flags_for_meeting()` sets `is_current = FALSE` on old flags. Frontend queries filter by `is_current = TRUE`.
- **`data_sync.py` uses a registry pattern.** `SYNC_SOURCES = {"netfile": sync_netfile, "calaccess": sync_calaccess, "escribemeetings": sync_escribemeetings}`. Functions use lazy imports (import client modules inside function body) so the script doesn't fail if one client's dependencies are missing.
- **Testing dict-dispatched functions:** Don't use `@patch("data_sync.sync_netfile")` — the `SYNC_SOURCES` dict holds the original reference. Use `patch.dict(SYNC_SOURCES, {"netfile": fake_fn})` instead. For lazy imports inside sync functions, patch at the source module level (e.g., `@patch("escribemeetings_scraper.create_session")`).
- **GitHub Actions dual-trigger pattern:** Both workflows accept `repository_dispatch` (n8n sends HTTP POST) and `workflow_dispatch` (manual GitHub UI). Input resolution uses `${{ github.event.inputs.X || github.event.client_payload.X }}` fallback.
- **`scan_runs` table fields:** `id` (UUID), `city_fips`, `meeting_date`, `scan_mode`, `scanner_version` (git SHA), `triggered_by`, `pipeline_run_id`, `status` (running/completed/failed), `started_at`, `completed_at`, `error_message`, `contribution_sources` (JSONB with per-source counts), `flags_generated`, `flags_published`.
- **`data_sync_log` table fields:** `id` (UUID), `city_fips`, `source`, `sync_type`, `triggered_by`, `pipeline_run_id`, `status`, `started_at`, `completed_at`, `records_fetched`, `records_new`, `error_message`, `metadata` (JSONB).
- **Migration system:** `run_migration(conn, migration_path)` reads SQL files and executes them. Migrations are idempotent (use `IF NOT EXISTS`, `ADD COLUMN IF NOT EXISTS`). Path: `src/migrations/001_cloud_pipeline.sql`.
- **Migrations must be run manually in Supabase SQL Editor.** There's no automated migration runner for production Supabase. Copy the full `.sql` file contents into Dashboard → SQL Editor → New query → Run. Run in order (001 before 002). Both migrations are idempotent — safe to re-run.
- **Lazy import gotcha in `data_sync.py`:** Sync functions use lazy imports (`from netfile_client import ...` inside function body). These import names must exactly match the client module's actual exports. The test suite mocks at the `SYNC_SOURCES` dict level, so import mismatches only surface at runtime in GitHub Actions. Always verify import names against the actual client module before pushing.
- **n8n → GitHub dispatch:** n8n HTTP Request node POSTs to `https://api.github.com/repos/{owner}/{repo}/dispatches`. Returns 204 No Content (empty body) on success. Requires fine-grained PAT with **Contents: Read and Write** permission (not just Actions: Write). Headers: `Accept: application/vnd.github.v3+json`, `Authorization: Bearer {token}`.
- **n8n workflow schedules (4 workflows):** (1) Weekly Data Sync: Sunday 10pm Pacific — dispatches `sync-data` for netfile + escribemeetings. (2) Monthly CAL-ACCESS: 1st Monday of month (every-Monday cron + IF node `$now.day <= 7`). (3) Pre-Meeting Pipeline: Monday 6am UTC — dispatches `run-pipeline` for Tuesday council meetings. (4) Retrospective Re-scan: triggered after Workflow 1 completes.
- **NetFile sync takes ~18 minutes** on first run (32K+ raw transactions, paginated at 1000/page with rate limiting). Produces ~49K records in Supabase after combining with CAL-ACCESS data. GitHub Actions 45-min timeout is sufficient.
- **Supabase access in GitHub Actions:** Uses `SUPABASE_SERVICE_KEY` (service_role, bypasses RLS) — appropriate because the pipeline also uses `DATABASE_URL` (direct Postgres, no RLS). Anon key would be security theater. `SUPABASE_URL` is not actually secret but stored as a GitHub secret for convenience.

### Environment & Dependencies

- **`python-dotenv` is required** — `os.getenv()` alone doesn't read from `.env` files. Import and call `load_dotenv()` at the top of entry points.
- **`.env` is in repo root, not `src/`.** When running scripts from `src/`, use `load_dotenv(Path(__file__).parent.parent / ".env", override=True)`. The `override=True` is needed because the shell environment may have empty vars that shadow `.env` values.
- Run pipeline scripts from `src/` directory (relative imports: `from extraction import ...`)
- Extraction prompt template uses `.format()` with keys: `schema` and `minutes_text`
- **Windows compatibility:** Use `python -X utf8` flag when running scripts that output Unicode characters. Comment generator uses ASCII-only formatting for cross-platform compatibility.

### Pipeline Cost Estimates

- Single meeting minutes extraction: ~$0.06 (Claude Sonnet, ~10.5K input + ~8.9K output tokens)
- Single agenda extraction: ~$0.07 (Claude Sonnet, ~6K input + ~3.5K output tokens)
- At 24 meetings/year: ~$1.44/year for Richmond minutes extraction alone
- Budget headroom for re-extraction as prompts improve
