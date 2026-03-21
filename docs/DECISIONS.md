# Decisions Log — Richmond Common

*Record key decisions and rationale so future-you doesn't wonder "why did I do it this way?"*

---

## 2025-02-15: Use FIPS codes for city disambiguation from day one
**Decision:** Every record includes `city_fips` (e.g., Richmond CA = 0660620, Richmond VA = 5167000). Every web search includes "Richmond, California" not just "Richmond."
**Rationale:** Cheap to implement now, catastrophically expensive to retrofit at city #50. Prevents data corruption when scaling horizontally.

## 2025-02-15: PostgreSQL + pgvector, no separate vector DB
**Decision:** Use pgvector extension in PostgreSQL for embeddings instead of Pinecone/Weaviate/etc.
**Rationale:** Single query can combine vector similarity with SQL filtering. One database to manage. Good enough performance for our scale. Reduces infrastructure complexity and cost.

## 2025-02-15: Three-layer database architecture
**Decision:** Document Lake (raw, flexible) → Structured Core (normalized, fast) → Embedding Index (semantic search).
**Rationale:** Preserves raw data for re-extraction as prompts improve. Structured layer enables fast cross-referencing (the conflict scanner needs JOINs, not embeddings). Embedding layer handles natural language search.

## 2025-02-15: "Sunlight not surveillance" positioning
**Decision:** Frame as governance assistant that helps cities work better, not adversarial watchdog tool.
**Rationale:** Phillip's Personnel Board seat requires collaborative framing. City staff adoption more likely if not perceived as hostile. Accountability is natural consequence of transparency — doesn't need to be the pitch.

## 2025-02-15: Don't file entity yet
**Decision:** Build prototype as individual. Fiscal sponsorship + LLC later.
**Rationale:** Entity structure depends on traction — startup path (C-corp/PBC), mission path (501c3), or both (Mozilla model). Filing prematurely locks in structure before data informs the choice.

## 2025-02-15: Four-tier source credibility hierarchy
**Decision:** Tier 1 (official records) > Tier 2 (independent journalism) > Tier 3 (stakeholder comms, disclosed bias) > Tier 4 (community/social, context only).
**Rationale:** RAG retrieval must weight sources appropriately. Richmond Standard (Chevron-funded) can't have same weight as certified council minutes. Tom Butt's blog is invaluable context but not neutral fact. Always disclose bias.

## 2025-02-15: Free for Richmond, revenue from scaling
**Decision:** Richmond pilot is free. Revenue comes from other cities, professional tiers, and grants.
**Rationale:** Real deployment validates product. Richmond becomes the case study. 280 subscribers at $5/month covers all Richmond costs (0.24% of population) if self-sustaining model needed later.

## 2026-02-16: Conflict scanner works in both JSON and DB modes
**Decision:** Build the conflict scanner with two modes — JSON mode (works with raw extraction output + contribution lists) and DB mode (queries Layer 2 tables). Both produce identical `ScanResult` objects.
**Rationale:** JSON mode lets us test and demo without a database. DB mode scales with data. The scanner is the core intelligence — it needs to work reliably before we add more data sources. Entity name matching uses normalized text comparison with employer cross-referencing (not just exact match).

## 2026-02-16: Store both raw names and normalized names in schema
**Decision:** Officials and donors tables have both `name` (display) and `normalized_name` (lowercase, stripped, for matching). Votes table stores `official_name` (raw from extraction) plus optional `official_id` FK.
**Rationale:** Extraction produces slightly different name formats across meetings. Normalized names enable fuzzy matching. Keeping raw names preserves the original record. `official_id` can be NULL in votes if we haven't resolved the name yet — don't block data loading on entity resolution.

## 2026-02-16: Coalition analysis from split votes only
**Decision:** Council member voting coalitions are calculated only from split (non-unanimous) votes, excluding absent/abstain positions.
**Rationale:** Unanimous votes tell us nothing about political dynamics. The interesting signal is in 4-3 and 5-2 votes. Abstentions and absences are excluded because they don't indicate alignment. Even from a single meeting (Sept 23, 2025), we can see clear coalition patterns: Jimenez+Wilson voted identically on all split votes, while Brown and Zepeda never agreed with them.

## 2026-02-16: Comment generator delegates to conflict scanner
**Decision:** `comment_generator.py` delegates all conflict detection to `conflict_scanner.py` and only handles document completeness checks and comment formatting/submission. Missing document detection stays in comment_generator.
**Rationale:** Separation of concerns — the scanner handles financial conflict analysis (campaign contributions, Form 700 interests), while the comment generator handles presentation (template rendering, email submission) and document completeness (resolutions without linked text, policies referenced for revision without current version). This prevents code duplication and ensures both the scanner report and the public comment use the same detection logic.

## 2026-02-16: Land-use detection excludes commission/board appointments
**Decision:** The Form 700 real property cross-reference skips agenda items that are commission/board appointments, even if they contain words like "development" (e.g., "Economic Development Commission").
**Rationale:** Broad keywords like "development" in the zoning detector were causing false positives on appointment items (O.5.b "Economic Development Commission", O.5.g "Workforce Development Board"). These are administrative appointments, not land-use decisions that could affect property values. The fix checks for appointment-related keywords and suppresses the property flag when found. Reduced false positives from 14 to 6 flags in testing.

## 2026-02-16: CAL-ACCESS contains PAC/IE data only — council candidates file locally
**Decision:** CAL-ACCESS is used for PAC, independent expenditure committee, ballot measure, and statewide candidate data. Individual Richmond city council candidate committees file with the City Clerk, not the state. A separate City Clerk e-filing scraper is needed for direct candidate contributions.
**Rationale:** Discovered empirically: searching CVR_CAMPAIGN_DISCLOSURE_CD for council member names (Martinez, Zepeda, Bana, etc.) returned 0 results. California cities with populations under a certain threshold have candidates file locally. CAL-ACCESS still has high-value data — PACs like SEIU Local 1021 ($1.2M+ to Richmond committees), ChevronTexaco ($137K), Richmond Police Officers Association ($184K). These are the big-money players that matter for conflict detection. The client now uses a two-step lookup: CVR_CAMPAIGN_DISCLOSURE_CD (find Richmond filing IDs) → RCPT_CD (match contributions by FILING_ID, not FILER_ID).

## 2026-02-16: RCPT_CD joins on FILING_ID, not FILER_ID
**Decision:** Contributions in `RCPT_CD` must be looked up by `FILING_ID`, not `FILER_ID`. The join path is: `CVR_CAMPAIGN_DISCLOSURE_CD` → `FILING_ID` → `RCPT_CD`.
**Rationale:** `RCPT_CD` does not have a `FILER_ID` column at all. Initial implementation tried `FILER_ID` → `FILER_FILINGS_CD` → `FILING_ID` → `RCPT_CD`, but `FILER_FILINGS_CD` only returned Form F410 (Statement of Organization) filings, which have no contribution data. Going through `CVR_CAMPAIGN_DISCLOSURE_CD` directly yields F460 filings (campaign finance disclosures) with actual contribution records. Found 4,892 contributions ≥ $100 totaling $7.5M+ using this approach.

## 2026-02-17: eSCRIBE attachment text integration uses pre-enrichment pattern
**Decision:** Integrate eSCRIBE staff report text into the conflict scanner by enriching the meeting_data dict *before* it reaches `scan_meeting_json()`, rather than modifying the scanner's API. A new module (`escribemeetings_enricher.py`) matches eSCRIBE items to extracted agenda items by title similarity (Jaccard word-overlap), then appends up to 10K chars of attachment text per item to the description field.
**Rationale:** The scanner's `scan_meeting_json()` is stable and tested. Modifying its signature to accept optional attachment text would thread complexity through the entire call chain. Pre-enrichment is additive — the scanner receives the same data structure with richer descriptions. Title-based matching (not item number mapping) is necessary because eSCRIBE uses Roman numeral sections ("V.1") while Claude extraction uses letter prefixes ("C.1"). Titles are specific enough ("Purchase of Three Fleet Vehicles from National Auto Fleet Group") to match unambiguously. The 10K char cap per item prevents excessive false-positive substring matches from very long staff reports while capturing the vendor names, contract parties, and dollar amounts that typically appear in the first few pages.

## 2026-02-17: Platform profile metadata for multi-city scaling
**Decision:** Record eSCRIBE URL patterns, API endpoints, and HTML selectors as a structured `ESCRIBEMEETINGS_PLATFORM_PROFILE` dict in the enricher module.
**Rationale:** eSCRIBE (OnBoard/Diligent) is used by hundreds of cities with identical URL patterns (`Meeting.aspx?Id=`, `filestream.ashx?DocumentId=`, `GetCalendarMeetings` AJAX API). Capturing this as structured data means future city onboarding can check platform compatibility automatically. This is the beginning of platform-affinity-based horizontal scaling — instead of researching all 19,000 cities, roll out to other eSCRIBE cities first where the scraper works with only a base URL change.

## 2026-02-18: Bias audit instrumentation baked into matching pipeline from Day 1
**Decision:** All entity matching decisions logged to `matching_decisions` table with structural risk signals (compound surname, diacritics, name length, surname frequency tier from Census 2010 data). Per-scan aggregate statistics logged to `scan_audit_summary` with filter-stage funnel counts broken down by surname frequency. Ground truth populated organically through manual flag review during the public comment workflow. Confidence thresholds pre-registered before seeing bias results. Periodic audit at 100+ ground-truthed decisions.
**Rationale:** The conflict scanner has structural properties that could produce disparate false positive/false negative rates across demographic groups: 12-char substring threshold disadvantages short names, common surnames produce more spurious matches, hyphenation stripping affects compound names. Richmond's diverse demographics (majority Latino, significant Black and Asian communities) make this a real risk, not hypothetical. Instrumentation is cheap now; retrofitting audit infrastructure later is expensive. Bias signals use structural string properties, NOT demographic inference. Full spec: `docs/specs/bias-audit-spec.md`.

## 2026-02-16: Text extraction validated at 100% for actual meeting minutes
**Decision:** PyMuPDF text extraction is production-ready for Richmond council minutes. No OCR pipeline needed for current data.
**Rationale:** Validated 25 downloaded documents. All 21 actual meeting minutes scored 100/100 on quality checks (council member names, roll call votes, agenda items, meeting dates, dollar amounts, resolutions). The remaining 4 documents (Jan–Feb 2026) are public comment compilations, not minutes — the actual minutes for those meetings haven't been published yet. Vote format `Ayes (N): Councilmember...` is consistent across all meetings. One older meeting (ADID 17234, Jan 6, 2026) has partial Type3 font garbling but is a comment compilation, not minutes.

## 2026-02-19: Bias audit instrumentation (JSON sidecar pre-database)
**Decision:** Instrument `scan_meeting_json()` with `ScanAuditLogger` that records every matching decision (flags and near-misses) plus per-scan filter funnel statistics. Uses JSON sidecar files as pre-database storage (`scan_audit.py`). Structural risk signals (`bias_signals.py`) are auto-computed for each donor name: compound surname, diacritics, token count, surname frequency tier from Census 2010. `ScanResult` gains `scan_run_id` (UUID) and `audit_log` (ScanAuditLogger) fields.
**Rationale:** The conflict scanner's matching logic (substring thresholds, stop word lists, generic employer filters) has structural bias surfaces identified in `docs/specs/bias-audit-spec.md`. Short-name thresholds may disadvantage East Asian names; common-surname false positives disproportionately affect Hispanic/Latino donors; diacritics loss impacts non-English names. Instrumentation logs the filter funnel so we can later run disparity analysis (are Tier 1 surnames over-flagged vs. Tier 4?) without modifying the scanning logic itself. Pre-database JSON sidecar approach avoids schema migration during Phase 1.

## 2026-02-19: Census surname frequency data stored under src/data/census/
**Decision:** Census 2010 surname frequency data processed into `src/data/census/surname_freq.json` (162,254 surnames, 2.3MB). Raw CSV and ZIP gitignored; processed JSON committed.
**Rationale:** Consistent with all other pipeline data paths under `src/data/`. Processed JSON is small enough to commit (avoids requiring download step). Raw data is large (12.8MB ZIP → 91MB CSV) and reproducible via `python prepare_census_data.py`.

## 2026-02-19: Audit sidecars use UUID filenames in src/data/audit_runs/
**Decision:** Each scan produces a sidecar file named `{scan_run_id}.json` (UUID4) in `src/data/audit_runs/`. Multiple scans of the same meeting date produce separate files. Directory gitignored (files are large, ~33MB each with 26K+ contributions).
**Rationale:** UUID filenames prevent collisions when re-running the pipeline during development or testing. Sidecar files contain all matching decisions (matched and unmatched) plus filter funnel summary — they're the raw audit trail. Too large to commit (~33MB per scan with full contribution comparisons), but the data structure is self-describing JSON that can be inspected with any tool.

## 2026-02-19: Ground truth review is interactive CLI, not batch file
**Decision:** `python conflict_scanner.py --review --latest` opens an interactive terminal for labeling flags as T(rue positive), F(alse positive), S(kip), or N(otes + verdict). Verdicts written back to the same sidecar file.
**Rationale:** With 1-4 flags per typical meeting, an interactive CLI is more natural than maintaining a separate CSV or spreadsheet. The reviewer sees full context (donor, employer, agenda item, match type, confidence, bias signals) before deciding. Batch file approach would require copying data to another format and back. The CLI approach keeps everything in one place.

## 2026-02-19: Periodic bias audit requires 100+ ground-truthed decisions
**Decision:** `bias_audit.py` requires `--min-decisions 100` (pre-registered threshold from spec) before computing disparity statistics. Override with `--min-decisions N` for testing.
**Rationale:** Statistical significance requires sufficient sample size. With ~4 flags per meeting and 24 meetings/year, reaching 100 decisions takes roughly a year of ground truth review. This is intentional — the threshold was pre-registered in the spec before seeing any bias results, preventing cherry-picking. The 100-decision minimum means early reports will show "insufficient data" rather than noisy estimates.

## 2026-02-18: Three-tier publication system for public comment findings
**Decision:** ConflictFlag gets a `publication_tier` field (1–3). Tier 1 (sitting member + confidence ≥ 0.6) → "Potential Conflicts of Interest" section. Tier 2 (sitting member + confidence ≥ 0.4) → "Additional Financial Connections" section. Tier 3 (non-sitting candidate, low confidence, or PAC-only) → suppressed from public comment, tracked internally. Comment template redesigned from code-output style to narrative format readable by council members and the public.
**Rationale:** The first real comment (Feb 17, 2026 meeting) exposed credibility risks: 4 flags were published including low-confidence PAC matches (40% confidence firefighter union donations to a fire department budget item) and donations to non-sitting former candidates. Publishing weak matches undermines the project's credibility with the very audience (city council, clerk's office) whose cooperation we need. The tier system fails closed — `publication_tier` defaults to 3 (suppressed), so new flag types must explicitly opt in to publication. Suppressed count is disclosed in methodology ("Additional matches tracked internally: N") for transparency without publishing the weak evidence. Template redesign removes raw confidence scores, evidence bullet lists, and code-style formatting — reads like investigative journalism instead of debug output. Bug fixes included: empty "Recipient:" field for PAC contributions (now shows committee name), "(n/a)" employer display cleaned.

## 2026-02-19: Census data stored under src/data/census/, not repo root
**Decision:** Census 2010 surname frequency data lives at `src/data/census/surname_freq.json` (derived, checked in) with raw files (`Names_2010Census.csv`, `names.zip`) gitignored. The download script is `src/prepare_census_data.py`.
**Rationale:** All other pipeline data lives under `src/data/`. Keeping Census data consistent avoids confusion. The processed JSON (2.3MB, 162,254 entries) is small enough to check in and avoids requiring Census.gov download on every fresh clone. Raw CSV/ZIP are large and redundant once processed.

## 2026-02-19: Audit sidecars use UUID filenames, gitignored
**Decision:** Audit sidecar files are named `{scan_run_id}.json` (UUID4) in `src/data/audit_runs/` and gitignored. Multiple scans of the same meeting date produce separate sidecars with no filename collisions.
**Rationale:** UUIDs avoid filename conflicts when re-scanning. Sidecars can be 20MB+ (21,118 decisions for a single meeting scan = 27 items × ~780 contributions each), making them impractical for git. They're runtime artifacts — the pipeline regenerates them on each run. Ground truth verdicts accumulate in the sidecars over time as the reviewer works through flags.

## 2026-02-19: Ground truth review is interactive CLI, not batch file
**Decision:** Ground truth is populated via interactive CLI (`conflict_scanner.py --review --latest`) that presents one flag at a time with full context (donor, employer, agenda item, match type, confidence, bias signals). Reviewer assigns T/F/S/N verdicts saved directly to the sidecar JSON.
**Rationale:** Richmond produces 1–4 flags per meeting — batch file editing would be overkill. Interactive CLI lets the reviewer see context in a natural flow. Verdicts are timestamped (`manual_review_YYYY-MM-DD`) for audit trail. This naturally integrates into the pre-meeting comment workflow: run pipeline → review flags → submit comment.

## 2026-02-19: Periodic bias audit requires 100+ ground-truthed decisions
**Decision:** `bias_audit.py` refuses to report results until 100+ ground-truthed decisions (matched flags with T/F verdicts) are accumulated. This threshold is pre-registered and documented in the spec before any bias data is seen.
**Rationale:** Small samples produce misleading statistics. With 1–4 flags per meeting and ~24 meetings/year, reaching 100 decisions takes roughly 1–2 years of regular scanning. Pre-registering the threshold prevents cherry-picking a sample size that produces a desired result — a standard practice in statistical research. The `--min-decisions` flag allows override for testing but the default enforces rigor.

## 2026-02-21: Retrospective re-scans on simple cron, no conditional gating
**Decision:** Workflow 4 (retrospective re-scan) runs on a simple twice-monthly cron (1st and 15th) without checking whether new contributions arrived first. Three nodes: cron → get latest meeting → trigger retrospective pipeline.
**Rationale:** At Richmond's scale (~$0.07/scan, 24 meetings/year), the conditional check (query Supabase for `records_new > 0`) saves ~$0.50/year while adding 2 nodes of complexity. Redundant scans produce identical flags — the supersession logic handles this gracefully. Simplicity wins for a vibecoded solo project. Can add gating later if scaling to multiple cities makes the cost meaningful.

## 2026-02-21: AI-native architecture as foundational project doctrine
**Decision:** Establish AI-native architecture as a core design philosophy, documented in CLAUDE.md. The project is built as a genuine human-AI partnership — not "AI-assisted," but AI-native from the ground up. Humans are reserved for creative, expressive, values, ethical, relationship, and trust-calibration decisions. Everything else (code, testing, scraping, extraction, analysis, monitoring, design) is AI-driven with human review at key checkpoints.
**Rationale:** The project is vibecoded end-to-end but with craft and intentionality. Up-front investment in AI-native design pays compound returns: self-healing scrapers reduce maintenance, self-monitoring pipelines catch anomalies, prompts-as-config enables re-extraction when models improve, and schema-as-contract lets AI figure out extraction from diverse input formats. The self-advancing roadmap (auto-benchmark new models, AI-to-AI boundary management, cross-city intelligence) positions the system to improve autonomously over time. This isn't aspirational — it's how we've already been building (extraction prompts, conflict scanner confidence tiers, bias audit instrumentation). Making it explicit doctrine ensures consistency as the project scales. See CLAUDE.md "AI-Native Architecture Philosophy" section.

## 2026-02-21: Phase D approach — Playwright scraper + API key pursuit in parallel
**Decision:** Build a Playwright-based NextRequest scraper now while simultaneously pursuing official API access from the City Clerk. Abstract behind a `NextRequestClient` interface so the backend can swap between Playwright scraper and REST API transparently.
**Rationale:** NextRequest has an official REST API v2 at `/api/v2/` (confirmed by 401 response, not 404 — the API exists but requires authentication). API keys require Admin role on the NextRequest portal, which the City Clerk's office likely holds. CivicPlus (which acquired NextRequest) issues keys through their Support channel. However, getting API access could take weeks or months. Playwright scraping is viable because NextRequest is a SaaS platform — identical UI across all cities means one scraper works everywhere. Self-healing selectors (Tier 1) built in from day one using LLM-based selector regeneration when page structure changes. The interface abstraction means API access, if obtained, is a drop-in replacement with zero pipeline changes.

## 2026-02-22: Archive Center expansion — CivicPlus document discovery engine
**Decision:** Expand Archive Center scraping from AMID=31 (council minutes only) to an automatic AMID enumerator that discovers all 149 active archive modules across any CivicPlus site. Download PDFs for high-priority AMIDs (resolutions, ordinances, commission minutes) into Layer 1. Defer Claude extraction until RAG search or specific cross-referencing needs.
**Rationale:** Richmond's Archive Center has 9,000+ documents across 149 AMIDs that we're leaving untouched. The build cost is ~30 minutes (extend existing `batch_extract.py` patterns). Key archives: 2,844 resolutions (AMID=67), 537 ordinances (AMID=66), 769 City Manager weekly reports (AMID=87), Personnel Board docs (AMID=132/133), Rent Board (AMID=168/169), Design Review Board (AMID=61/77). CivicPlus powers ~3,000+ city websites with identical URL patterns — this becomes a generic document discovery engine for horizontal scaling. Documents sit in Layer 1 at zero marginal cost, ready for extraction when RAG search is built.

## 2026-02-22: NextRequest full extraction depth (Option 3)
**Decision:** NextRequest/CPRA scraper downloads metadata, PDFs, extracts text, AND runs Claude extraction on document contents. Not just metadata.
**Rationale:** Trade-off analysis showed: metadata-only costs $0/mo but gives only compliance analytics. Full extraction adds ~$8/mo (80 docs × $0.10) but enables cross-referencing CPRA documents with agenda items and campaign contributions — e.g., "this contract released via CPRA mentions the same vendor that donated to Councilmember X." The upgrade path from metadata-only to full extraction is purely additive (zero rework), but the investigative cross-referencing value justifies building it from the start. Each option layers on the previous: metadata → PDF download ($0 incremental) → extraction ($8/mo). All three combined cost less than a single coffee.

## 2026-02-22: Decision-making framework — always present investment/payoff/upgrade analysis
**Decision:** For every feature decision in this project, present: (1) vibe-coding build time per option, (2) monthly run cost, (3) payoff/revenue relevance, (4) one-time cost to upgrade from each option to the next, (5) monthly cost delta at each level. This is the standard decision framework.
**Rationale:** Established during Phase D design when Phillip asked for comparative upgrade economics rather than just build costs. The insight: for a vibe-coded project, the real currency is Phillip's attention/session time, not engineering hours. Monthly costs are almost always trivial ($0-10/mo). The important question is "how much does it cost to upgrade later if I start smaller?" — which is often "trivially little" because options are additive, not replacements. This framework prevents both over-building (spending sessions on features that could wait) and under-building (false economy of starting small when the upgrade cost exceeds the savings).

## 2026-02-22: Future product line — civic website modernization platform
**Decision:** Log as a future product direction, not current scope. The idea: use the city scraping framework to generate modern, accessible city websites. Offer for free, host on clean domains. Business model: license cities to redirect/adopt the modern frontend as their official site, or sell organized data access to journalists.
**Rationale:** City government websites are universally poor UX (CivicPlus sites are better than most but still stuck in 2012 design). RTP is already scraping and structuring this data — the gap between "structured civic data" and "beautiful civic website" is just a frontend. The free-tier version is a Craigslist-kills-classifieds play: publish a better version, then cities want to officially adopt it. Journalist data access is Path C (data infrastructure). However: this is a different product with a different buyer (city IT/communications vs. citizens), government sales cycles are 6-18 months, and it requires the data pipeline to be rock-solid and multi-city first. The architecture being built now (CivicPlus document discovery, platform profiles, FIPS-based multi-city) is exactly the foundation this product needs. Revisit when 5-10 cities are running.

## 2026-02-22: Future feature — stakeholder mapping and coalition graph
**Decision:** Log as a future capability. The idea: a data structure that maps stakeholders (organizations, individuals, community groups) to their positions on categories, initiatives, and specific agenda items — including nuanced positions like "supports the goal but opposes this specific implementation." This enables: (1) Nay-vote donation correlation (who benefits from something NOT passing), (2) coalition analysis beyond voting blocs (who aligns with whom on what issues), (3) richer conflict detection ("this donor opposed the project that this official voted down").
**Rationale:** Currently, the conflict scanner can only correlate Aye votes with post-vote donations because the beneficiary of a passed item is named in the agenda text. For Nay votes, the beneficiary of a blocked item is NOT in the agenda — it requires knowing the opposition landscape. This is a graph problem: entities have positions on issues, and those positions can be partial/conditional ("supports affordable housing but not at this density"). The stakeholder map would be populated from public comments, news coverage, and meeting transcripts over time. Prerequisite: RAG search layer (for entity extraction from unstructured text) and likely Form 700 data (for financial interest mapping). Revisit after temporal correlation v1 ships and RAG search is operational.

## 2026-02-22: Future feature — City Charter as governance metadata layer
**Decision:** Log as a future capability. The idea: ingest the City Charter (and municipal code) as structured metadata — a declarative spec of how governance *should* work — then continuously diff reality against it. Examples: "Charter says Planning Commission shall meet monthly; no meeting in 90 days." "Charter requires 5 Rent Board seats; only 3 filled." "Ordinance requires public hearing before zoning variance; none found in meeting records." The Charter becomes the city's `CLAUDE.md` — the institutional source of truth against which all observations become compliance findings.
**Rationale:** Every other feature (commissions, employees, conflicts, document completeness) generates *observations*. A Charter-as-metadata layer turns observations into *discrepancies* — the difference between a transparency dashboard and a governance compliance engine. Every US city has a charter or municipal code with remarkably similar structure (commissions, officers, meeting requirements, appointment procedures, budget processes). This scales horizontally via the same FIPS-based multi-city framework. The commissions feature (being built now) is a natural first consumer — commission seat counts, term lengths, and meeting schedules come directly from the Charter. Prerequisites: commissions + city employees features (to have entities to check against), RAG search (for natural language Charter queries). Revisit after commissions and Form 700 ship.

## 2026-02-22: Commission roster scraper uses table-based parsing, not Playwright
**Decision:** Parse commission roster HTML with BeautifulSoup table extraction rather than Playwright browser automation. Handle CivicPlus quirks (empty `<thead>`, styled `<td>` header rows, section header rows like "2 SEATS APPOINTED BY ELECTION:") with heuristic filtering.
**Rationale:** Richmond's CivicPlus pages serve full HTML without JS rendering (same pattern as eSCRIBE meeting pages). Table-based parsing is faster, cheaper, and more reliable than headless browser. The heuristic filters (header row detection via background-color style or `<strong>` text, VACANT/section-header name patterns) handle all 17 Richmond commissions tested. If a future city uses a JS-rendered roster, the scraper architecture supports adding a Playwright fallback per-city.

## 2026-02-22: Appointment extractor uses Claude API for commission membership mining
**Decision:** Use Claude Sonnet API to extract appointment/reappointment/resignation/removal actions from already-extracted council meeting JSONs, rather than regex or keyword matching.
**Rationale:** Appointment actions appear in diverse formats across consent calendar and action items ("APPROVE the reappointment of...", "CONFIRM the appointment of...", "ACCEPT the resignation of..."). LLM extraction handles this variation naturally at ~$0.02/meeting (~$0.50 for 21 meetings). The structured JSON output schema (person_name, commission_name, action, appointed_by, term_end, confidence) feeds directly into the staleness comparison against website rosters. This is the same pattern as the agenda extractor — prompts are config, not code.

## 2026-02-22: Commission meeting type discovery via eSCRIBE calendar API
**Decision:** Add `--discover-types` to the eSCRIBE scraper to catalog all unique `MeetingName` values with counts and date ranges. Store the canonical→eSCRIBE name mapping in `city_config.py` as `commissions_escribemeetings`.
**Rationale:** eSCRIBE's calendar API returns meetings for ALL body types (City Council, Planning Commission, Rent Board, etc.). Before scraping commission agendas, we need to know exactly which `MeetingName` strings the portal uses. This is a one-time discovery step per city, and the mapping goes into the city config registry so it scales with multi-city onboarding. The `--discover-types` CLI flag makes this discoverable and repeatable.

## 2026-02-22: Staleness comparison is pure Python, no API calls
**Decision:** The `compare_with_website()` function that checks minutes-derived appointments against the website roster is a pure in-memory comparison, not an API call or database query.
**Rationale:** Staleness detection compares two local data structures (appointment records from Claude extraction vs. website roster from HTML scraping). Making this a pure function makes it fast, testable without mocks, and composable — it can run after any combination of data sources. Only appoint/reappoint/confirm actions generate staleness findings; resignations and removals don't (a resigned member disappearing from the website is expected, not stale).

## 2026-02-21: Future feature — temporal correlation analysis (post-vote donations)
**Decision:** Log this as a planned feature, NOT a current scanner capability. The conflict scanner currently detects pre-vote donations (prospective) and all-time donations (retrospective). It does NOT detect the pattern: "donation filed X days/months AFTER a favorable vote." This requires a fundamentally different analysis — correlation detection rather than lookup — and a periodic historical refresh cadence.
**Rationale:** Post-vote donations are among the highest-value findings for accountability journalism. Examples: a developer donates to a council member's next campaign 6 months after that member voted to approve their project; a contractor donates after winning a bid. These patterns require: (1) a "correlated donation" flag type distinct from "pre-existing relationship," (2) configurable lookback windows (90 days, 6 months, 1 year, multi-year), (3) periodic full-history re-scans (annual refresh of all meetings in trailing 12 months, eventual deeper lookback as budget allows), (4) clear labeling distinguishing "donated before vote" from "donated after vote" in the UI. The framing matters — post-vote donations aren't necessarily corrupt (donors support officials whose values align with theirs), but the temporal pattern is newsworthy and the public deserves to see it. See Phase 2 item in CLAUDE.md.

## 2026-02-22: Ground truth aliases for name variant matching
**Decision:** Add `aliases` array to `officials.json` entries for people who appear under different names across data sources. First use: Shasa Curl (goes by "Shasa" publicly, legal name "Kinshasa Curl" in campaign finance filings). The conflict scanner does NOT yet read the `aliases` field — this needs to be wired in.
**Rationale:** The same person can appear as different names across Socrata payroll, NetFile/CAL-ACCESS filings, meeting minutes, and city website. Without alias resolution, the conflict scanner will miss matches (e.g., a contribution from "Kinshasa Curl" won't match agenda text referencing "Shasa Curl"). The `aliases` array in ground truth is the lightweight solution — no fuzzy matching needed for known variants, just expand the name set during entity resolution. **TODO:** Update `conflict_scanner.py` to load aliases from `officials.json` and include them in the donor/entity name matching loop. This is a straightforward change — when building the council member name exclusion set or the entity match set, iterate both `name` and `aliases` for each entry.

## 2026-02-22: Process gap — AI should auto-document decisions and TODOs
**Decision:** Parking lot. The current workflow has a gap: when Claude makes architectural choices or introduces new conventions (like the `aliases` array), it doesn't automatically log them in DECISIONS.md or flag deferred work. The human had to catch this. This means documentation quality depends on human vigilance, which defeats the AI-native philosophy.
**Rationale:** CLAUDE.md says "everything else — code, architecture, documentation — is AI-driven with human review at key checkpoints." Documentation of decisions and TODOs should be part of the implementation step, not a separate human-prompted afterthought. Potential solutions: (1) Add a step to the executing-plans skill: "after each task, check if any new conventions, deferred work, or architectural choices were introduced — if so, log in DECISIONS.md before committing." (2) Add a CLAUDE.md convention: "every commit that introduces a new data structure field, convention, or deferred TODO must include a DECISIONS.md entry." (3) Build it into the writing-plans skill so plans include explicit "document X" steps for known decision points. Revisit when refining skills/process.

## 2026-02-22: Four foundational tenets established
**Decision:** Lock four tenets as project doctrine: (1) Scale by default — every feature designed for 19,000 cities. (2) Relentless human-unique boundary optimization — AI does everything except creative, expressive, values, ethical, relationship, and trust-calibration decisions, with bidirectional safety loops. (3) Optimize human decision velocity — pre-digested packets, minimum info for fastest correct decision. (4) Richmond is the ideal — build the absolute best version for Richmond, then figure out how to scale it.
**Rationale:** After 6+ weeks of building, patterns emerged that needed naming. "Scale by default" was already practice (FIPS everywhere, city config registry) but not articulated as a tenet. "Human-unique boundary optimization" captures the bidirectional insight — the system should flag both "this human task could be automated" AND "this automated task needs human review." "Decision velocity" addresses the bottleneck: Phillip's attention is the scarcest resource; the system should optimize every human touchpoint for speed. "Richmond is the ideal" resolves the tension between "build for scale" and "build something great" — Richmond quality wins, then we figure out scale. These tenets inform every feature decision via the parking lot priority groups.

## 2026-02-22: Free public access as core value
**Decision:** Revenue comes from intelligence and scaling, never from paywalling public data. Explicit goal: put predatory for-profit "public info" companies out of business by offering a better free alternative.
**Rationale:** Companies like BeenVerified, Spokeo, and county records aggregators charge $20-40/month for access to public records. This project can provide the same (and better) civic data for free because the marginal cost of serving structured data is near-zero. The revenue model (Path A freemium, Path B horizontal scaling, Path C data infrastructure) doesn't depend on restricting access. This is a values decision AND a business strategy — the Craigslist-kills-classifieds play works because free + better quality is unbeatable. Documented as a core value alongside "sunlight not surveillance."

## 2026-02-22: Three publication tiers for features
**Decision:** Every feature is classified as Public (citizens see it immediately), Operator-only (Phillip validates framing before any citizen sees it), or Graduated (starts operator-only, promoted to public after human review of tone and accuracy). Classification documented in `docs/PARKING-LOT.md` per item.
**Rationale:** Some features are factual and safe to publish automatically (meeting records, vote counts, contribution totals). Others involve inference or framing that could damage credibility or relationships if wrong (coalition analysis, "Explain This Vote" AI-generated explainers, stakeholder mapping). The graduated tier acknowledges that many features need human review initially but should eventually become public as confidence grows. This is tenet #2 (human-unique boundary optimization) applied to publication: the system should flag which outputs need human review before going public, and periodically re-evaluate whether that review is still necessary.

## 2026-02-22: CLAUDE.md restructured into layered hierarchy
**Decision:** Replace the 362-line monolith `CLAUDE.md` with a layered system: root CLAUDE.md (~80 lines, tenets + priorities + documentation map), `.claude/rules/` (3 files: architecture.md, conventions.md, richmond.md — auto-loaded every session), `src/CLAUDE.md` (pipeline knowledge, loaded on-demand), `web/CLAUDE.md` (frontend conventions, loaded on-demand).
**Rationale:** The monolith loaded ~15K tokens of context every session regardless of task. A frontend-only session doesn't need CAL-ACCESS join paths; a pipeline session doesn't need the civic color palette. Claude Code natively supports `.claude/rules/` (auto-loaded) and child directory CLAUDE.md files (loaded on-demand when accessing files in that directory). The restructuring separates strategic guidance (always loaded) from operational knowledge (loaded when needed). Root file focuses on tenets, values, and the documentation map so any session starts with the right framing.

## 2026-02-22: Build now, optimize compute later (AI-native scaling principle)
**Decision:** When building features, prioritize correctness and capability first. Optimize for compute costs (prompt efficiency, token reduction, caching, batching) in a later phase. Don't over-engineer schemas or processes for scale — optimize the prompts.
**Rationale:** In an AI-native system, the primary "code" is prompts, not traditional logic. The compute cost of prompts will decrease over time as models get cheaper and more efficient (Sonnet cost has dropped ~4x in 18 months). Building features now with correct prompts that produce accurate output is more valuable than optimizing token counts. When it's time to scale to 100 cities, that's when prompt optimization, caching, and batching become the leverage point — not during initial feature development for Richmond. This aligns with tenet #4 (Richmond is the ideal): build the best version first, worry about compute efficiency when scaling.

## 2026-02-22: Court records research — Tyler Odyssey platform
**Decision:** Log court records integration as a Group 3 item (Deep Conflict Intelligence). Tyler Technologies' Odyssey platform is the dominant US court case management system. Cross-referencing officials, donors, and contractors against court filings (lawsuits, liens, judgments) is high-value conflict intelligence.
**Rationale:** Court records are public data with enormous accountability value — but they're scattered across county court systems with varying levels of digital access. Tyler Odyssey standardizes this for many jurisdictions. Contra Costa County (Richmond's county) likely uses Odyssey. The implementation pattern matches eSCRIBE: research the platform, build a platform profile, confirm availability for the target jurisdiction, then build a generic scraper that works across all Odyssey jurisdictions. Revisit after media pipeline and Form 700 (higher-priority data sources).

## 2026-02-22: Website change monitoring as data infrastructure
**Decision:** Log as Group 5 (Data Foundation). Monitor city government website pages for changes, cache historical versions, alert on significant modifications. Wayback Machine-style archive for local government.
**Rationale:** City websites are a living data source that changes without notice. Commission rosters are updated, policies are quietly revised, budget documents appear and disappear. The current pipeline takes point-in-time snapshots but doesn't track changes over time. A change monitoring system provides: (1) historical record of what the website said on any date, (2) alerts when high-value pages change (detecting roster updates, policy revisions), (3) evidence preservation for accountability. Start with high-value pages (commission rosters, policy pages, budget documents).

## 2026-02-22: Media source pipeline for multi-city scaling
**Decision:** Log as Group 5 (Data Foundation). Automated discovery and classification of local media sources per city. Richmond's curated source list becomes the template for automated discovery.
**Rationale:** Every city has a local media ecosystem: independent papers, university journalism programs, corporate-funded outlets, council member blogs. Richmond's source credibility tiers (Tier 1-4) are manually curated and well-understood. The challenge is scaling this to 19,000 cities. Current LLM capabilities can discover sources but reliable tier assignment with ownership/bias disclosure still requires editorial judgment. Revisit when second city onboards or LLM source classification improves.

## 2026-02-22: Cross-city policy comparison as future product feature
**Decision:** Log as Group 6 (Future/Scale). A tool to search/compare policies, ordinances, proclamations, and resolutions across cities. "Find other cities that passed similar rent control ordinances."
**Rationale:** This could be the killer feature for horizontal scaling. Individual city transparency is valuable but comparison across cities is transformative — it's what journalists, policy researchers, and progressive council members would actually use. Implementation requires RAG search over multi-city data, document type classification, and semantic similarity matching. It's a Group 6 item because it needs 3+ cities with structured data and operational RAG search. But the architectural decisions being made now (FIPS-based multi-city, document lake, pgvector embeddings) are exactly the foundation this feature needs.

## 2026-02-22: Phase 2 priorities re-evaluated through tenets lens
**Decision:** Reorganize all Phase 2 items into 7 priority groups (Group 0-6) evaluated against the four tenets and three monetization paths. Groups represent thematic clusters with dependency annotations, not strict execution order.
**Rationale:** The previous Phase 2 list was a numbered priority list that grew organically. After establishing the four tenets, every item was re-evaluated: Does it scale by default? Does it optimize human-unique boundaries? Does it improve decision velocity? Is it amazing for Richmond? Items were reorganized into groups that make dependencies explicit. The operator layer (Group 1) was added as a new group recognizing that tools for Phillip's decision-making are themselves high-leverage features. Full breakdown in `docs/PARKING-LOT.md`.

## 2026-02-23: Parking lot restructured from thematic groups to execution sprints
**Decision:** Replace the 7 thematic priority groups (Groups 0-6) with dependency-ordered execution sprints (S1-S7 + Backlog). Each sprint produces both pipeline capability AND a visible frontend feature. Old group IDs preserved in brackets for cross-reference.
**Rationale:** The thematic groups clustered related items (e.g., all "citizen-facing" features together) but didn't reflect execution order or dependency chains. High-priority items were scattered across groups (archive expansion in Group 5 feeding vote categorization in Group 2). The new sprint structure makes three things explicit: (1) what's ready to build right now (prerequisites met), (2) what unblocks the most downstream work, (3) what the operator can see and validate. Key changes: archive expansion moved from Group 5 to Sprint 1 (low-effort, high-leverage data foundation), feature gating system added as S1.1 (enables visibility for all subsequent sprints), operator layer moved to Sprint 7 (not blocking, more valuable after more features exist). Reprioritization cadence established: milestone-triggered + weekly fallback + deep restructure when capabilities shift.

## 2026-02-23: Feature gating system for operator-only visibility
**Decision:** Build a simple feature gating system (S1.1) that implements publication tiers in frontend code. Operator sees WIP features before public release. Cookie/URL-param toggle with React context wrapper. Real Supabase Auth replaces it later without component changes.
**Rationale:** The project has publication tiers defined conceptually (Public, Operator-only, Graduated) but no mechanism to enforce them in the frontend. Every pipeline feature built in S2-S7 should be immediately visible to the operator behind a gate, then graduated to public after validation. Without gating, there's a choice between showing unvalidated features to citizens or having no frontend manifestation of pipeline work. The gating system resolves this by making "build pipeline, see it immediately, release when ready" the default workflow. Implementation is deliberately simple (cookie-based, no auth) because beta has one operator. Supabase Auth is the upgrade path when multi-user operator access is needed.

## 2026-02-23: Alternating visibility loop as execution rhythm
**Decision:** Each sprint produces both pipeline work AND a visible frontend feature. Pipeline capabilities are immediately manifested on the frontend behind the operator gate. This is the "alternating visibility loop" execution pattern.
**Rationale:** With 20x/week Claude Code Max sessions, each session should produce a tangible artifact the operator can inspect. Pure pipeline sprints feel productive but produce nothing visible. Pure frontend sprints without new data feel hollow. The alternating loop ensures constant visible progress while building intelligence depth. It also creates natural validation checkpoints: if the frontend representation of a pipeline feature looks wrong, the pipeline logic gets caught early.

## 2026-02-23: Duplicate official detection needed after name typo caused silent data split
**Decision:** Add fuzzy duplicate detection to `ensure_official()` or as a post-load validation step. Log to DECISIONS.md now, prioritize in upcoming backlog review.
**Rationale:** The April 15, 2025 council minutes misspelled "Jamelia Brown" as "Jameila Brown" (single transposition). `ensure_official()` uses exact normalized name matching, so it silently created a second official record. Result: 100 votes and 20 attendance records accumulated on the correct-spelling record while the misspelled record (shown on the frontend) had 0 votes and 1 attendance. The bug was invisible for months. Fix was a DB merge (reassign attendance, delete duplicate) + source JSON correction. Systemic prevention options: (1) Levenshtein-distance warning on new official creation when a similar name exists, (2) wire up the `aliases` field from `officials.json` into `ensure_official()` lookups. Both are low-effort and scale to all cities — any city's minutes could contain typos. This is a data quality issue, not an extraction issue: the extraction faithfully reproduced what the PDF said.

## 2026-02-23: Feature gating uses cookie + env secret, not Supabase Auth (security upgrade needed for scale)
**Decision:** S1.1 feature gating uses a URL param with a secret value from `.env` (e.g., `?op=SECRET`) that sets a browser cookie. No Supabase Auth. This is visibility obscurity, not real security.
**Rationale:** Beta has one operator (Phillip). Operator mode only reveals WIP features (unfinished UI, graduated content awaiting review). It does not expose admin controls, data modification, or anything destructive. The worst case if someone discovers the secret is seeing unpolished features, which is equivalent to finding a Vercel preview URL. Real Supabase Auth adds 1-2 hours of build cost (auth flow, protected routes, session management) for a threat model that doesn't exist yet. **Security upgrade trigger:** When operator mode gains write capabilities (approving graduated content, modifying data, managing users), or when a second operator is added, replace cookie toggle with Supabase Auth. The component structure (`OperatorModeProvider` context + `<OperatorGate>` wrapper) is designed so the auth source swaps without changing any consuming components.

## 2026-02-25: Post-mortem — S1 feature gating shipped incomplete, process fixes adopted
**Decision:** Adopt three process changes: (1) Publication tier is a required, explicit field in every feature spec, assigned as a judgment call by the human. (2) AI must flag inconsistencies between spec content and project conventions (e.g., spec says "Public" but graduated publication principle says new features default operator-only). (3) Project conventions override Claude Code skill/plugin defaults when they conflict.
**Rationale:** Sprint 1 commission pages shipped with only 1 of 4 entry points gated (staleness alerts on detail page). The nav link, index page, and detail page content were all publicly accessible. Root cause was not architectural (OperatorGate worked fine) but process: the spec said "Public" for commission pages without an explicit publication tier decision checkpoint. AI followed the spec literally instead of flagging the conflict with the graduated publication principle. Fix required 3 files across 4 entry points. Process changes address the S0 level: publication tier rubric added to team-operations.md, skill override rule added to CLAUDE.md, "judgment call" / "AI-delegable" terminology adopted across all CLAUDE.md layers. Entry-point audit checklist parked for private beta.
**Related:** Commit `7b2de32` (the fix), publication tier rubric in `.claude/rules/team-operations.md`.

## 2026-02-25: Adopt "judgment call" / "AI-delegable" terminology
**Decision:** Replace "human-unique" with "judgment call" and name its complement "AI-delegable" across all project documentation.
**Rationale:** "Human-unique" sounds awkward spoken aloud and lacks a clean complement term. "Judgment call" is plain language, accurate, and scales from specs to checklists to conversation. "AI-delegable" clearly names everything that isn't a judgment call. The terminology applies across all CLAUDE.md layers (Layer 1 philosophy, Layer 2 team operations, Layer 3 personal context, project-level). Tenet 2 renamed from "Relentless Human-Unique Boundary Optimization" to "Relentless Judgment-Boundary Optimization."

## 2026-02-25: Commit message framing authority
**Decision:** AI drafts all commit messages. Most are AI-delegable. Commits that change public-facing content, touch community/city relationships, or have multiple defensible framings with strategic weight are judgment calls requiring human review before committing.
**Rationale:** Commit messages are part of the project's public narrative (especially once open-sourced under BSL). Most commits are routine and the message is obvious. But some commits, particularly first commits of new features or changes affecting public-facing content, carry editorial weight in how they frame the change. "Fix: gate commission pages" vs. "Fix: prevent premature public exposure of unvalidated data" tell different stories. The authority boundary ensures routine commits stay fast while catching the ones where framing matters.

## 2026-02-26: Judgment boundary catalog and tool sovereignty
**Decision:** Created `.claude/rules/judgment-boundaries.md` as the single authoritative source for what requires human input and what is AI-delegable. Strengthened Tenet 2's RTP expression to explicitly assert project sovereignty over external tool instructions. Replaced the generic "project conventions override skill/plugin defaults" convention with a direct pointer to the catalog.
**Rationale:** Skills and plugins were prompting the operator for AI-delegable decisions (commit message approval, merge strategy confirmation, branch naming). This violated Tenets 2 and 3 by pulling human attention into decisions already delegated to AI. Root cause: skill instructions load with high force ("MUST," "NON-NEGOTIABLE") and the existing override rule was a principle, not a directive. The catalog provides specific, actionable boundaries that compete at the same level of force as skill instructions. Ordered by frequency of incorrect escalation so the most commonly violated boundaries have the highest primacy in context.

## 2026-02-27: Vercel preview builds must handle missing env vars
**Decision:** Made `web/src/lib/supabase.ts` fall back to a placeholder client when `NEXT_PUBLIC_SUPABASE_URL` is not set, instead of crashing. Preview deployments on Vercel had no Supabase env vars configured, causing ISR prerendering to throw "supabaseUrl is required" and fail the build in 24 seconds.
**Rationale:** Every branch push triggers a Vercel preview deploy. Without this fix, any push to any branch fails the build, creating noise that slows the operator down. The fix is defensive: pages render with empty data on misconfigured deployments instead of crashing. The operator should also add Supabase env vars for the Preview environment in Vercel settings.

## 2026-02-27: Adopt evidence-based cadence evaluation
**Decision:** Use system health reports (`python system_health.py`) as the primary input for cadence and architecture decisions. Reports persist to `src/data/health_reports/` (gitignored) with trend comparison against previous snapshots. Key metrics tracked: documentation benchmark coverage (93% baseline), module test coverage (66% baseline), documentation drift (0 baseline), convention compliance, commit categories, file churn/rework rate.
**Rationale:** Before this, "should we refactor X?" or "is our documentation working?" were vibes-based. Now they're measurable. The trend comparison shows whether each session improved or degraded the system. Specific cadence findings from the first run: (1) Pipeline tasks have 100% doc coverage but only 63% test coverage — we're well-documented but undertested. (2) `city_config` is imported by 11 modules making it the most critical dependency. (3) 19 files qualify as rework candidates (5+ changes in 30 days), most are expected (docs, core frontend) but `escribemeetings_scraper.py` and `staleness_monitor.py` churn suggests instability. (4) Commit category ratio (40% feat, 23% docs, 8.5% phase/meta) suggests the meta-layer work is within healthy bounds but should not grow further.

## 2026-02-27: Risk framework — four threats to project principles
**Decision:** Identified and documented four principal risks to RTP's tenets, ordered by severity: (1) **Navel-gazing risk** — meta-layer work crowding out citizen-facing features (Tenet 4 violation). Signal: % of commits touching `web/src/app/` vs. meta files. (2) **Credibility cliff** — publishing incorrect conflict flags damages the city relationship (Tenet: sunlight not surveillance). Signal: data accuracy spot-checks against ground truth. (3) **Scale-by-default becoming build-for-nobody** — over-abstracting slows Richmond features (Tenet 1 vs Tenet 4 tension). Signal: `city_config` coupling count and time-to-ship for Richmond-specific features. (4) **Unfunded mandate** — amazing for Richmond but no path to city #2. Signal: hours to onboard a second city.
**Rationale:** These risks were implicit but never documented. Making them explicit and measurable means they can be tracked, not just worried about. Each risk has a specific signal that can be checked. The self-assessment system now provides data for signals 1 and 3; signals 2 and 4 are judgment calls that need human evaluation.

## 2026-02-27: Readiness-to-ship signals established
**Decision:** Defined eight signals that gauge whether the project is ready to build and ship citizen-facing features vs. needing more infrastructure: (1) Citizen-facing commit ratio, (2) Data accuracy score, (3) Pages live & validated, (4) Time-to-useful for a new visitor, (5) Sprint velocity, (6) Onboarding friction for city #2, (7) Doc benchmark score, (8) Test coverage. First four are outward-facing (product quality), last four are inward-facing (system health). Current assessment: inward-facing signals are healthy (93% doc coverage, 66% test coverage), outward-facing signals are the bottleneck (no systematic data accuracy measurement, no user testing). Conclusion: the meta-layer is in good shape; energy should shift to S2/S3 (citizen-facing features).
**Rationale:** The operator asked "are we ready to build?" and the answer needs to be evidence-based, not vibes-based. These signals provide a checklist that any session can evaluate. The asymmetry between inward and outward signals confirms the strategic direction: stop investing in meta-infrastructure, start shipping features Richmond residents can see.

## 2026-02-27: System health self-assessment module
**Decision:** Built `src/system_health.py` — a self-monitoring module that evaluates documentation architecture, codebase health, and pipeline instrumentation readiness. Three layers: (1) Documentation Architecture Benchmark mapping 15 common task types to expected context files/keywords (self-retrieval test), (2) Architecture health analysis (module coupling, test coverage, convention compliance, documentation drift), (3) Pipeline instrumentation helpers (timing + token counting decorators for incremental adoption). Publication tier: permanent operator-only.
**Rationale:** The project had solid reactive monitoring (staleness, health endpoints, audit trails) but no proactive self-assessment. We couldn't answer "is our documentation architecture working?" with evidence. The benchmark produces a coverage score (currently 93%) that measures whether the CLAUDE.md tree helps the system find the right context for common tasks. Architecture analysis revealed: 63% module test coverage (13 untested modules), `city_config` as the most depended-upon module (11 importers), `conflict_scanner` as the largest module (1,537 lines), and 3 convention violations. Git analysis identified 19 high-churn files. These are actionable signals for refactoring decisions. The benchmark doubles as a regression test — if someone restructures docs and coverage drops, it's caught. The pipeline instrumentation helpers (`PipelineTimer`, `PipelineMetricsCollector`) are designed for incremental adoption across pipeline stages. This module follows the staleness_monitor.py pattern (CLI with --format text/json, no database dependency, fast to run).

## 2026-02-26: Plugin audit and ralph-loop disable
**Decision:** Audited all 13 installed Claude Code plugins against RTP's operating model. Disabled `ralph-loop`. Kept remaining 12 with documented awareness notes.
**Rationale:** Categorized plugins into three types: connectors (API access, zero risk), workflow skills (on-demand, contained), and behavior modifiers (hooks that silently change AI behavior). ralph-loop installs a Stop hook that intercepts session exit and prevents the operator from leaving, which directly violates Tenet 3 (human decision velocity) and operator control principles. commit-commands `/commit-push-pr` conflicts with "merge locally" convention but is handled by the judgment boundary catalog (never invoke it, `/commit` alone is safe). superpowers' "MUST invoke before ANY response" directive is the exact problem the catalog was built to counter; monitoring whether the catalog is effective. No critical plugin gaps identified for current or near-term sprint work.

## 2026-03-01: Graduate S3.1 (summaries) and S3.2 (explainers) to Public
**Decision:** Remove OperatorGate from plain language summaries (S3.1) and confirm vote explainers (S3.2) are already public. Both features graduate from Graduated to Public.
**Rationale:** Operator reviewed generated summaries and explainers across meetings and signed off on framing. Summaries use measured tone (2-3 sentences, factual, no jargon). Explainers characterize vote margins honestly, name dissenters on split votes, and add context without advocacy. Both include AI-generated attribution lines. S3.2 was already rendering without an OperatorGate wrapper (likely an oversight during implementation, but the content was reviewed through operator mode regardless). 12 tests (summaries) + 37 tests (explainers) passing. Prompt templates version-controlled in `src/prompts/`.

## 2026-03-01: H.9 gated feature entry-point audit findings
**Decision:** Audit found two architectural gaps in the gating system. (1) `/api/data-quality` endpoint has no operator auth check. Anyone can call it directly. Low risk (exposes data quality stats, not sensitive data) but should be addressed before adding write capabilities to operator mode. (2) Summaries and bios use client-side OperatorGate (cookie-based) with server-rendered data. The data is always sent; JS hides it. This is fine for the graduated-to-public workflow (remove gate = make visible) but would be insufficient for permanently operator-only content. No action taken now. Triggers: add API auth when operator mode gains write capabilities; consider server-side gating if permanently operator-only features need real protection.
**Rationale:** The S1 post-mortem (2026-02-25) established that entry-point audits should happen before private beta. This audit confirms the current gating architecture is sufficient for beta (one operator, no write capabilities, worst case = seeing unpolished features) but documents the upgrade triggers explicitly.

## 2026-03-01: Sprint 6 — Pattern Detection architecture decisions

### S6.1 Coalition analysis: client-side computation over server-fetched votes
**Decision:** Compute pairwise alignment, bloc detection, and category divergence in the Next.js query layer (`queries.ts`) rather than SQL views or database functions.
**Rationale:** 7 council members produce only 21 pairs. Brute-force clique finding (all subsets of size 3-7) is O(2^7) = 128 subsets, trivial for client-side. Keeping computation in TypeScript means the alignment matrix, bloc detection thresholds, and divergence gap formula are all version-controlled alongside the UI. SQL views would be premature optimization for a 7-node graph and would split logic across two systems. If Richmond expands to a larger body or multi-city needs arise, this computation can migrate to a materialized view.

### S6.1 Framing guardrails: no ideology labels, no motive inference
**Decision:** Alignment matrix shows percentages only. No "progressive bloc" or "business-aligned" labels. Divergence table shows factual gaps without explaining why. Methodology section explicitly disclaims that alignment does not imply coordination.
**Rationale:** "Sunlight not surveillance" principle. Labeling blocs as ideological is an editorial judgment that belongs in journalism, not a transparency tool. The data speaks: if two members agree 98% of the time, that's a fact. Calling them a "progressive coalition" is an inference. Richmond's political dynamics are complex (progressive coalition, Chevron-adjacent interests, independent voices) and simplistic labels would damage credibility with city government and misserve citizens.

### S6.2 Scope: defer temporal proximity pattern (Pattern 2) from v1
**Decision:** Implement donor-category concentration (Pattern 1) and cross-official donor overlap (Pattern 3). Defer temporal contribution-vote proximity (Pattern 2) which would detect "donor contributes, then official votes favorably within N days."
**Rationale:** Pattern 2 requires robust employer fuzzy matching (many donors share employers, and employer names vary across filings) and a temporal correlation engine. The build cost is 2-3x Patterns 1+3 combined. More importantly, temporal proximity is the most inference-heavy pattern: it implies causation timing that factual tools should not assert. Patterns 1 and 3 are purely structural (who gives to whom, what topics recipients vote on) without temporal causation. Pattern 2 belongs in a later sprint with dedicated framing validation.

### S6.2 Finding: zero donor-category concentration is the correct result
**Decision:** The concentration metric (what % of a donor's recipients' votes fall in their top policy category) found 0 significant patterns. This is displayed honestly as "No significant donor-category concentration patterns found" rather than lowering thresholds to manufacture findings.
**Rationale:** Richmond council members vote on all categories (budget, housing, public safety, etc.) roughly evenly. A donor contributing to 3 council members doesn't create "concentrated" voting because those members vote on everything. This is a meaningful finding: Richmond's contribution landscape doesn't map to single-issue lobbying. Lowering the threshold (currently $1K+ total, 30%+ concentration) would produce false positives and undermine the tool's credibility. The overlap table (39 multi-recipient donors) still provides valuable intelligence.

## 2026-03-04: Autonomy zones — bounded self-modification for pipeline infrastructure

**Decision:** Adopt a three-tier "autonomy zone" model for pipeline code. Free zone (prompts, scraper selectors, operational config): system modifies, validates, and commits autonomously. Proposal zone (thresholds, schema changes, new integrations): system drafts changes, human approves. Sovereign zone (publication logic, content framing, CLAUDE.md, frontend): read-only to self-modification loop. Phase A (pipeline journal + self-assessment, no self-modification) is scoped into S7 as S7.4.

**Rationale:** Layer 1 philosophy already states "parsing logic and selectors are mutable artifacts AI can regenerate" and "self-healing systems detect failures and attempt recovery." The autonomy zone model is the architecture that implements these principles. It extends the judgment boundary catalog from governing decisions to governing code regions: the same "AI-delegable vs. judgment call" distinction, applied spatially to the codebase. Inspired by [yoyo-evolve](https://github.com/yologdev/yoyo-evolve), which demonstrates a fully self-modifying agent loop. RTP adapts the pattern with bounded autonomy: the system has "free will" within defined zones, not over the entire codebase. This preserves the trust model (civic accountability demands human oversight of public-facing output) while enabling self-healing infrastructure. Phase A (observation only) starts with S7 because the pipeline journal is itself an operator decision packet. Full spec: `docs/specs/autonomy-zones-spec.md`.

## 2026-03-07: Sprint reordering — data sources before search before UI

**Decision:** Insert S8 (Data Source Expansion) between S7 (Operator Layer) and what was S8 (Citizen Discovery, now S9). Add S9.1 (Basic Site Search using PostgreSQL full-text search) before RAG (S9.2). Old S9 (Information Design) becomes S10. New sequence: S7 → S8 (Data Source Expansion) → S9 (Citizen Discovery: basic search + RAG + feedback) → S10 (Information Design).

**Rationale:** Operator insight: "I'd rather get all the data in the app before implementing RAG." This is architecturally sound. RAG search requires designing embedding templates per document type (agenda items, minutes, court records, commission meeting notes, etc.). Designing these templates with full knowledge of all document types avoids retrofitting when new data sources arrive. Similarly, the UI overhaul (S10) benefits from knowing the complete data landscape. S8 promotes three backlog items: B.10 (court records), B.36 (commission/board meetings), B.32 (paper-filed Form 700s). Also wires existing Socrata client code into the sync pipeline (hygiene). S9.1 (basic text search) uses PostgreSQL's native `tsvector`/`ts_rank` with zero embedding pipeline. It validates search UX (what people search for, how results display) before the heavier RAG investment. Maps to "basic search" in the free tier of the business model. When RAG ships, the two coexist: keyword search for exact matches, semantic search for natural language queries.

## 2026-03-07: Pipeline monitoring mismatch fix

**Decision:** Added `form700` (90 days) and `minutes_extraction` (14 days) to FRESHNESS_THRESHOLDS in both `staleness_monitor.py` and `web/api/data-quality/route.ts`. Standardized `archive_center` threshold to 45 days (was 60 in frontend, 45 in Python).

**Rationale:** Three places define monitored pipelines (data_sync.py SYNC_SOURCES, staleness_monitor.py FRESHNESS_THRESHOLDS, web API FRESHNESS_THRESHOLDS) and they had drifted apart. form700 and minutes_extraction were built and registered as sync sources but not monitored. The data quality dashboard was missing them. The archive_center threshold disagreed between Python (45) and frontend (60). Standardized to 45 as the canonical value from the Python staleness monitor.

## 2026-03-07: Civic Transparency SDK — phased roadmap, defer standalone package

**Decision:** Adopt a three-phase approach for the Civic SDK (B.20). Phase A: formalize missing conventions inside `src/` with extraction-ready interfaces (fold into S7-S8). Phase B: extract to `packages/civic_sdk/` as pip-installable package (trigger: after S10, second city, or open-source timing). Phase C/D: Layers 2-5 per the five-layer model. Do not build a standalone package now.

**Rationale:** The SDK spec (brainstormed in Claude Chat) proposes a five-layer open-core model encoding RTP conventions into reusable code. ~30% already exists in production (FIPS enforcement, document lake). ~40% would formalize patterns documented but not code-enforced (source tiers, disclosure registry). ~30% would be new (exception hierarchy, prefixed identifiers). Building a standalone package now risks premature abstraction: S7-S10 may reveal new patterns, and there's no second city to validate the generalization. Instead, Phase A implements the missing enforcement code inside `src/` with clean, composable APIs designed for future extraction. The interfaces are the hard part; packaging is mechanical. Open questions (pydantic vs dataclasses, async, package name, license) are packaging decisions that can wait until Phase B. Specs filed at `docs/specs/civic-sdk-spec.md` and `docs/specs/civic-sdk-vision.md`.

## 2026-03-03: Post-S6 reprioritization — citizen comprehension over data depth

**Decision:** After completing S1-S6, prioritize citizen-facing comprehension (S8: RAG search + feedback, S9: information design overhaul) over historical data backfill (B.38 Archive Center automation, B.39 pre-2022 minutes). Sprint order: pre-S7 generator patch, S7 Operator Layer, S8 Citizen Discovery, S9 Information Design Overhaul. Generator automation (summaries + explainers in cloud pipeline) addressed as pre-S7 patch rather than a full sprint. **Note:** S8/S9 renumbered in 2026-03-07 reordering.

**Rationale:** The project crossed an inflection point.

## 2026-03-07: Retroactive official deduplication and is_current correction

**Decision:** Three-layer fix for duplicate officials created by historical data load: (1) comprehensive alias map in `officials.json` for all known council member name variants, (2) migration 020 with reusable `merge_official_pair()` function that merges duplicate official records and sets `is_current` based on ground truth, (3) `ensure_official()` now searches ALL officials (not just `is_current = TRUE`) with preference for current officials via `ORDER BY is_current DESC`.

**Rationale:** S4 built forward-looking dedup (fuzzy matching, alias resolution) but didn't remediate existing duplicates. Historical minutes loaded before S4 created many name variants as separate official records (e.g., "Tom Butt", "Thomas K. Butt", "Mayor Tom Butt"). Additionally, `ensure_official()` defaulted `is_current = TRUE` on all new records regardless of meeting date, and only searched current officials for matches. This meant officials from 2015 meetings appeared as "current" on the council page, and former members' name variants couldn't match against each other. Migration 020 merges known alias clusters, strips title-prefixed duplicates, and corrects `is_current` for all officials. The `is_current = TRUE` filter was the root cause: it created a blind spot where the system couldn't see (and therefore couldn't deduplicate against) the very records it was creating.

**Rationale:** The project crossed an inflection point. S1-S6 proved the data engine works: 237 meetings, 6,687 agenda items, 22K+ contributions, coalition analysis, pattern detection. The bottleneck shifted from "can we build it" to "can a citizen make sense of it." The platform is data-dense ("throw data in a pot, structure it, see what emerges") without a meta-structure for lay audiences. Two gaps: (1) citizens can't search across the data (no RAG), (2) the information architecture wasn't designed for non-experts. Going wider on citizen features (findability, legibility) before deeper on historical data (pre-2022 minutes, Archive Center automation) maximizes Path A (freemium platform value) at the current phase. Historical backfill stays in the backlog, prioritized for the sprint after S9. H.10, H.14, H.17, H.18 promoted from hygiene/backlog into formal sprint slots to signal that design and UX are now first-class deliverables, not afterthoughts.

## 2026-03-07: Former member cleanup and ground truth corrections

**Decision:** Follow-up to migration 020. Migration 021 adds programmatic cleanup for extraction artifacts that survived the initial dedup: compound title prefixes ("Councilmember/Boardmember Bates"), last-name-only entries ("Bates" merged into Nat Bates), cross-contaminated names ("Jim Butt" = Jim Rogers first + Tom Butt last, merged into Tom Butt), and combined entries ("Beckles, Myrick, and Rogers" deleted). Ground truth updated with 10 confirmed former members and 3 removals based on Tier 1-2 research.

**Key corrections:** Ahmad Anderson, Oscar Garcia, and Shawn Dunning were listed as "Former council member" but never served on council (all ran and lost). Removed from former_council_members, added to new notable_non_members section. Tom Butt's mayor term corrected from "2014-2018" to "2015-2022" (re-elected 2018). 10 confirmed former members added with aliases: Irma Anderson (mayor 2001-2006), Jeff Ritterman, Harpreet Sandhu, Ludmyrna Lopez, Maria Viramontes, Mindell Penn, Richard Griffin, John Marquez, Gary Bell, Demnlus Johnson III.

**Design principle:** Vote/attendance count used as *confirming* signal alongside name pattern analysis, never as sole criterion. Prevents accidental deletion of newly sworn-in members who legitimately have few votes. The cross-contamination detector uses a known-member matrix: only flags entries where first name matches member A AND last name matches member B AND the combination isn't a real person.

## 2026-03-07: Former member cleanup pass 2 and new ground truth discoveries

**Decision:** Migration 022 addresses remaining artifacts that migration 021 missed. Root cause: Tony Thurmond (council 2005-2008, now CA Superintendent of Public Instruction) wasn't in the ground truth, so the cross-contamination matrix couldn't detect "[X] Thurmond" or "Tony [X]" artifacts. Ada Recinos (council 2017-2018, appointed to replace Gayle McLaughlin) also discovered as missing from ground truth.

**New ground truth additions:** Tony Thurmond (council 2005-2008, appointed July 2005, elected 2006), Ada Recinos (council 2017-2018, appointed Sept 2017, youngest ever at 26, RPA-affiliated, lost 2018 election). Total former council members in ground truth: 22.

**Artifacts resolved:** 9 Thurmond cross-contaminations (Corky/Gary/John/Jovanka/Lark/Nat/Richard Thurmond + "Thurmond" last-name-only), 4 Tony cross-contaminations (Tony K. Viramontes/Lopez/Marquez/Rogers), Nathaniel Boozé (Bates × Booze), Maria T. Lopez (Viramontes × Lopez), Andres Marquez (not a Richmond council member), Rosemary Corral Lopez (combined entry), Lito Viramontes (unverified), Belcher (unverified). Sequential approach: delete cross-contaminations first, then re-run last-name merges (now unambiguous).

**Parked:** S10.5 Controversial Votes Filter + Local Issue Categorization (from design session).

## 2026-03-07: S7.3 First quarterly judgment-boundary audit

**Decision:** Conducted the first systematic audit of all 69 decision points across the RTP system. Result: 88% correctly delegated. Added 5 new judgment calls and 4 new AI-delegable items to the catalog. Identified 1 critical threshold synchronization gap (scanner assigns Tier 1 at 0.6, frontend displays at 0.7). Established quarterly audit cadence with repeatable process documented in audit report.

**New judgment calls added:** (1) Public-facing label text changes (ConfidenceBadge labels). (2) Comment template framing. (3) Generation prompt voice/framing changes (distinction: running prompts = AI-delegable, modifying voice/framing = judgment call). (4) OperatorGate scope changes (adding = AI-delegable, removing = judgment call). (5) Confidence threshold values affecting public visibility.

**New AI-delegable items added:** (1) Database migration authoring (running in production remains human). (2) Threshold synchronization propagation. (3) Adding OperatorGate protection. (4) Hardcoded data list maintenance (prefer pattern detection over enumeration).

**Publication tier confirmations:** Data Quality, Coalitions, and Patterns pages confirmed as intentionally Public by operator. All were reviewed before shipping. Rationale: site not yet publicly known; operator may re-gate some features after private beta feedback.

**Comment template:** Approved as-is. Submission remains gated behind dry_run=True. Will be re-reviewed before private beta opens.

**Threshold synchronization:** Deferred pending operator review of actual scanner output. Scanner may not have been run against live data yet. Decision will be made after operator sees real conflict flags.

**Rationale:** S7.3 spec calls for a quarterly bidirectional review of the judgment boundary catalog. Bidirectional means challenging both directions: "Is this judgment call actually AI-delegable?" and "Is this AI-delegable task risky enough to need human eyes?" The first audit established the process, produced the template, and validated the existing catalog is well-calibrated. Audit reports live in `docs/audits/`.

## 2026-03-07: Scanner v2 — function specialization for name-to-text matching

**Decision:** Created `name_in_text()` as a purpose-built function for checking if a donor name appears as a contiguous phrase in agenda text. Three call sites in `scan_meeting_json()` switched from `names_match()` to `name_in_text()`. `names_match()` left unchanged for name-to-name comparisons (7 call sites).

**Rationale:** The root cause of the 21K false positive flags (with only 1% abstention coverage) was using `names_match()` for two fundamentally different purposes. Its word-subset matching ("do all words of name A appear somewhere in text B?") is correct for comparing two entity names but produces massive false positives against multi-page staff reports where common words like "development", "services", and "pacific" appear independently. `name_in_text()` requires the words to appear contiguously as a phrase (substring match), which is the actual signal. Additional changes: employer substring threshold raised from 9 to 15 chars, entity extraction blocklist added, specificity scoring penalty for generic-word donors. Combined estimated impact: 50-70% fewer false positive flags.

**Trade-off:** These are interim improvements. Entity resolution via public registries (B.46: CA SOS API, CSLB, ProPublica) will eventually replace fuzzy text matching with corporate ID matching. But the scanner is currently useless for even operator review at 21K flags, so the interim fix makes the operator view functional while infrastructure is built.

## 2026-03-07: Entity resolution as long-term scanner precision strategy

**Decision:** Parked entity resolution infrastructure as B.46 in the backlog, with B.45 (political influence cross-referencing) and B.47 (influence pattern taxonomy) as downstream consumers. Scanner v2 string-matching fixes are the interim solution; entity resolution is the architectural fix.

**Rationale:** Research document (`docs/research/political-influence-tracing.md`) validates that structured entity resolution through public registries (CA SOS 17M+ records, CSLB contractor licenses, ProPublica 1.8M+ nonprofit filings) would fundamentally change matching from fuzzy text to corporate ID comparison. This eliminates the class of false positives that string matching can only reduce. However, this is multi-sprint infrastructure work requiring API integrations, an entity graph schema, and a resolution pipeline. The interim scanner v2 fixes make the existing feature usable while this is built. Research also identifies 10 influence patterns and 5 ranked cross-references that inform B.47's detection rule design.

**Audit report:** `docs/audits/2026-Q1-judgment-boundary-audit.md`

## 2026-03-09: Unified scan_meeting_db via scan_meeting_json delegation

**Decision:** Rewrote `scan_meeting_db()` from a standalone implementation into a thin data-fetching wrapper around `scan_meeting_json()`. Three new functions (`_fetch_meeting_data_from_db`, `_fetch_contributions_from_db`, `_fetch_form700_interests_from_db`) convert DB data to the dict format that `scan_meeting_json()` expects. DB mode now inherits all v2 precision improvements automatically.

**Root cause:** The DB mode scanner (`scan_meeting_db`) was a separate implementation from the JSON mode scanner (`scan_meeting_json`). When v2 precision improvements (name_in_text, employer threshold, specificity scoring, council member suppression, government entity filtering, self-donation filtering, section header skipping, contribution deduplication, $100 materiality threshold, publication tier assignment, bias audit logging) were added to JSON mode, DB mode was left unchanged. This is why the batch scan produced 21K noisy flags — DB mode used broad SQL LIKE queries with no precision filters.

**Additional fix:** DB mode now uses `meeting_attendance` records (ground truth from minutes) to determine who was sitting at each meeting, replacing the `officials.is_current = TRUE` filter. This correctly handles historical meetings (2005-2026) where the council composition was different from today. Form 700 interests are fetched for all officials, not just current ones.

**Validation infrastructure:** Added `--validate` mode to `batch_scan.py` that compares existing DB flags against what v2 would produce, with structured before/after reporting. Added tier-level tracking to batch scan output (`flags_by_tier` now populated, previously always `{}`).

**Trade-off:** Fetching all contributions per meeting (instead of per-entity LIKE queries) increases memory usage but ensures identical precision logic. For Richmond's ~27K contributions this is well within memory limits. Multi-city scaling may need chunked loading.

## 2026-03-09: Scanner v3 promoted to S9, ahead of search and design

**Decision:** Roadmap resequencing based on v2 batch scan data. Scanner v3 signal architecture (was B.45 + B.47 in backlog) becomes S9. Old S9 (Citizen Discovery) becomes S10. Old S10 (Information Design) becomes S11. S7.4 (autonomy zones Phase A) deferred further. S8.3/S8.4 remain as slot-in items.

**Evidence:** v2 batch scan produced 9,927 current flags with 88.5% clustered at 0.40-0.49 confidence, zero above 0.60, and form700_real_property comprising 86% of flags at exactly 0.400. The scanner, the project's most differentiated feature, produces zero actionable intelligence.

**Rationale:** (1) Core intelligence engine must work before expanding citizen-facing surface area. (2) Search (S10) over noise flags has low value; search over differentiated signals is useful. (3) Information design (S11) should be built knowing final data shapes, not redesigned after v3 changes flag output. (4) v3 plan already exists and is well-specced at 4-5 sessions.

**Judgment calls resolved in same session:**
- Publication tier thresholds (0.85/0.70/0.50): Public
- `donor_vendor_expenditure` flag type: Public
- Confidence badge labels: "High/Medium/Low-Confidence Pattern" (consistent noun, confidence qualifier does the work)
- Language framework: Factual template ("Public records show that...") + blocklist (never "corruption", "illegal", etc.) + hedge clause ("Other explanations may exist." below 0.85)

## 2026-03-16: Signal significance architecture — Scanner v4 (confidence × significance)

**Decision:** Replace the scanner's single confidence axis with a two-dimensional model: confidence (does this connection exist?) × significance (should anyone care?). Three significance tiers: A (Legal Threshold — public), B (Pattern — public when confidence sufficient), C (Connection — operator only).

**Evidence:** A single campaign contribution flag on a commission appointment vote is technically correct but meaningless — and after legal research, confirmed legally irrelevant (FPPC treats appointments as employment contracts, exempt from the Levine Act). Meanwhile, the same donation on a permit hearing could cross a legal threshold requiring recusal. The current scanner can't distinguish the two.

**Rationale:**
1. **Confidence ≠ significance.** The scanner's single axis conflates "how sure are we this exists?" with "how much should anyone care?" A high-confidence match on a $150 donation is still noise.
2. **California law provides objective thresholds.** The Levine Act (§ 84308, $500 as of 2025), PRA (§ 87100), and § 1090 (contracts) create specific obligations at specific amounts for specific proceeding types. These should be encoded, not approximated by confidence scores.
3. **Patterns matter more than individual connections.** Five flags involving the same donor across multiple meetings tells a real story. A single flag tells nothing. Requires a new cross-meeting aggregation pipeline step.
4. **Most current flags are noise.** Expected that the majority of 784 meetings' worth of flags will reclassify to Tier C (operator-only). This is correct — the current public flag counts overstate significance.

**Key design decisions made:**
- Commission/board appointments: Tier C (Levine Act exempt, but useful for pattern recognition)
- § 1090 (contracts): Tier A only with direct financial interest (Form 700 income/investment, business position). Campaign contributions alone are insufficient — Tier C.
- Contribution limit violations: Tier C (operator-only). Campaign finance issue, not conflict of interest.
- Party identification: Critical path. Three layered approaches (permit DB join → structured extraction → entity resolution). Text matching alone insufficient for Tier A legal claims.
- Historical threshold handling: Apply $250 for pre-2025 meetings, $500 for post-2025.

**Legal research:** `docs/research/california-ethics-laws.md` — Levine Act, PRA §§ 87100-87105, § 1090, AB 571, FPPC regulations. Key finding: Levine Act threshold raised to $500 (SB 1243, Jan 2025), appointments exempt, agent contributions no longer aggregated (SB 1243).

**Spec:** `docs/specs/signal-significance-spec.md`

## 2026-03-19: Raw public data is free; the influence graph is the product

**Decision:** Richmond Common's business model split: all raw public data (contributions, meetings, filings, entity records) is free and open. The cross-referenced **influence graph** — entity connections, pattern detection, funding chain tracing, astroturf indicators, and narrative summaries — is the premium product (freemium, pay-what-you-wish, or tiered API access).

**Rationale:**
1. **Moat identification.** The code is planned for open source (BSL). The raw data is public by law. Neither is defensible. The moat is the *entity resolution and cross-referencing intelligence* — wiring together databases that nobody else connects at the municipal level (990s + SOS filings + campaign finance + lobbyist registrations + speaker records + FPPC behested payments).
2. **Precedent validation.** Bloomberg doesn't sell stock prices; it sells the terminal. ProPublica gives away 990s; the journalism (connections + narrative) is the impact. Wikipedia and ProPublica both demonstrate that "pay what you wish" works for mission-driven data projects.
3. **Path alignment.** Maps cleanly onto existing three-path model: Path A (freemium — free data, premium connections), Path B (horizontal scaling — influence graph scales across 19K cities because data sources are federal/state), Path C (data infrastructure — entity resolution engine as API product for journalists, researchers, civic tech).
4. **Mission consistency.** Free public data access directly serves the "put predatory for-profit public info companies out of business" goal. Premium intelligence layer funds the mission without paywalling what's legally public.
5. **Motivated by Flock Safety case.** The 2026-03-17 Richmond council vote on surveillance cameras demonstrated live astroturfing — out-of-town speakers, suspicious orgs at multiple Bay Area councils. The platform that automatically connects these dots across public databases changes the economics of corporate astroturfing at the municipal level.

**Supersedes/refines:** 2025-02-15 "Free for Richmond, revenue from scaling" — this decision sharpens *what* is free (raw data) vs. *what* generates revenue (the intelligence layer).

## 2026-03-21: S13.5 — Build loop detector first, defer SOS-dependent detectors

**Decision:** Implement `signal_behested_payment_loop()` as the first S13.5 astroturf pattern detector. Defer the other four detectors (`signal_org_formation_timing`, `signal_address_clustering`, `signal_cross_jurisdiction_deployment`, `signal_funding_chain`) until their data dependencies are available (CA SOS API key for three, cross-jurisdiction speaker data for one).

**Rationale:**
1. **One detector is fully unblocked.** The behested payment loop cross-references three data sources we already have: contributions (NetFile), behested payments (FPPC Form 803), and agenda item text. No external dependency.
2. **Multi-hop detection is novel.** Existing detectors do single-hop matching (entity → agenda). The loop detector closes a three-hop cycle (contribute → behest → agenda), with optional fourth-hop corroboration via lobbyist registrations. This is the same analytical pattern that surfaced the Flock Safety case.
3. **Incremental value.** One working detector in production is more valuable than five designed but unbuilt. The S9 signal architecture makes adding new detectors trivial when data sources come online.

## 2026-03-20: S12/S14 cohesive design — generate `summary_headline` during R1

**Decision:** The R1 regeneration pass (S12.3 new plain-language prompt, ~15K items) will produce two outputs per agenda item: (1) `plain_language_summary` (full, 75 words max, yes/no structure) and (2) `summary_headline` (one sentence, ~15-20 words). New nullable TEXT column on `agenda_items`.

**Rationale:**
1. **S14-A needs short-form summaries.** Topic board compact cards (A1), hero item teasers (A3), and category drill-through cards (B6) all need a one-line version. The full 75-word summary doesn't fit compact UI contexts.
2. **Marginal cost in same pass.** Adding a second output field to the same LLM call during R1 is near-zero marginal cost. A separate regeneration later would be $20-30 + another migration + another batch run.
3. **Prompt-level control > frontend truncation.** First-sentence extraction is brittle — the yes/no structure means sentence 1 is often "The council will decide whether to..." which is informative but not a punchy headline. A dedicated prompt instruction produces better short-form output.
4. **Cohesive design.** Evaluating S12 and S14 together before execution prevents building S12 outputs that S14 immediately needs to work around.

## 2026-03-20: Plain language as primary card interface, official text demoted

**Decision:** AgendaItemCard header shows `summary_headline` (plain language) instead of the official agenda title. Official title and description appear together under "Official Agenda Text" in the expanded section. Item numbers and colored significance borders removed.

**Rationale:**
1. **Information hierarchy should match reader needs.** Residents care about "what is this about" (headline), not "ADOPT a resolution to APPROVE a contract with..." (official title). Plain language first, official text as reference.
2. **Item numbers are clerk jargon.** "I-6", "O-1", "Agenda Addition" mean nothing to residents. The category badge already provides classification.
3. **Colored significance borders were unexplained.** A 4px red or amber left border with no legend requires prior knowledge to interpret. The vote tally badge ("7-1"), "Pulled from consent" text, and campaign contribution links already convey the same information explicitly.
4. **Infinitive verb headlines solve tense ambiguity.** "Hire law firm..." is tenseless — it reads as a proposed action regardless of whether the meeting is upcoming or past. The vote badge handles temporal context.
