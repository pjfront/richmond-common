# Decisions Log — Richmond Transparency Project

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
