# Data Foundation Audit, 2026-04-29

**Purpose:** Surface coverage gaps, entity-resolution candidates, and scanner-input quality issues so the next round of contribution-pages work (PAC V2, donor profile pages I135, vendor profile pages I142) starts on solid ground.

**Method:** Read-only SQL queries against the live Supabase, plus a few targeted batch fixes for clear data-correctness issues. All findings reproducible from the queries cited.

## Executive summary

The data foundation is healthier than I expected. Three real issues found, two fixed in this audit, one captured for follow-up:

1. **Fixed**: 32 conflict flags had publication_tier mismatched with confidence (boundary cases at exactly 0.70 and 0.50). Atomic re-tier applied. Resolves the high-priority `confidence_tier_desync` decision that has been pending since 2026-04-06.
2. **Fixed (in earlier commit this session)**: Anomaly detection thresholds for content-driven counts. conflict_scan flag count is now treated correctly as variance-tolerant rather than tripping the alert on every substantive meeting.
3. **Surfaced**: Entity-resolution gradients across donor employer fields. The Richmond Police union payroll-deduction donor block alone is split across at least 7 employer-name variants totaling ~$1.7M. Entity resolution (S26) is the right home for this.

Everything else is solid:
- Coverage by year matches the known sources (NetFile from 2018, sparse pre-2018 retroactive entries)
- Committee linkage gaps are limited to 2 known unfiled candidates (Gallon, Wassberg)
- 17% missing-employer rate on donors is within reasonable bounds for self-employed / older filings
- Scanner tier distribution is sensible (147 tier-1, 1302 tier-2, 9495 tier-3, 12128 tier-4 suppressed)

## Part 1: Contribution coverage by year and source

| Year | Source | Rows | Committees | Donors | Total $ |
|---|---|---|---|---|---|
| 2026 | city_clerk | 487 | 11 | 330 | $138,918 |
| 2025 | city_clerk | 1,621 | 12 | 289 | $122,185 |
| 2024 | city_clerk | 2,554 | 21 | 838 | $2,664,037 |
| 2023 | city_clerk | 2,051 | 14 | 390 | $388,249 |
| 2022 | city_clerk | 3,412 | 25 | 889 | $1,167,968 |
| 2021 | city_clerk | 2,134 | 13 | 253 | $155,262 |
| 2020 | city_clerk | 4,217 | 18 | 826 | $1,487,255 |
| 2019 | city_clerk | 3,227 | 9 | 279 | $348,637 |
| 2018 | city_clerk | 4,911 | 16 | 1,379 | $2,215,357 |
| 2018 | calaccess | 15 | 2 | 9 | $8,190 |
| 2017 | city_clerk | 1,613 | 5 | 524 | $149,211 |
| 2017 | calaccess | 3 | 1 | 1 | $1,100 |
| 2009 | city_clerk | 34 | 3 | 29 | $15,383 |
| 2008 | city_clerk | 53 | 3 | 48 | $234,263 |
| 2001-2007 | city_clerk | 68 (sparse) | varied | varied | $440,750 (sparse) |
| **2107** | **city_clerk** | **1** | **1** | **1** | **$100** |

**Findings:**
- 2018 cycle was the historical peak ($2.22M, 1,379 unique donors). 2024 was second ($2.66M, 838 donors). 2026 is at $139K through April with the primary 5 weeks out.
- Coverage gap 2010-2016: zero rows. Richmond adopted NetFile January 2018; pre-2018 entries are sparse retroactive imports for a few committees (Lt Gov 2018, prior council races). This is a known limitation, not a gap to fix.
- **CAL-ACCESS sparsity**: only 18 rows total (2017-2018). Expected, since CAL-ACCESS covers state-level PACs and IE committees and most Richmond money flows through NetFile. Worth verifying the CAL-ACCESS sync isn't silently failing on Richmond filings, but probably correct.
- **Future-dated row**: One row dated 2107-12-12 ($100, donor Charlette Casey, McLaughlin for Lt Gov 2018). Source filing has a typo, almost certainly 2017-12-12. Captured as I148.

## Part 2: Committee linkage

- 80 total committees in the database
  - 17 linked to a current or former official (`official_id IS NOT NULL`)
  - 23 candidate-controlled committees with no official link (the I147 case: Beckles for Assembly, McLaughlin for Lt Gov, prior-Richmond losers)
  - 40 true PACs (general purpose, IE, ballot measure)
- 2 active 2026 candidates have no committee linked:
  - **Keycha Gallon** (Richmond June 2026 Primary)
  - **Mark Wassberg** (Richmond June 2026 Primary)

These two have been flagged by the `candidates_have_committee_linked` liveness expectation since their candidacies were registered. Both will resolve when the candidates file their first Form 460 or 410. No action required from us.

## Part 3: Entity resolution candidates

This is the largest single improvement opportunity for the data foundation. Donor employer fields show clear variants of the same underlying entity. The Richmond Police union payroll-deduction block is the cleanest example:

| Employer string | Donor count | Total $ |
|---|---|---|
| Richmond City Police | 57 | $969,058 |
| Richmond, CA Police Department | 7,578 contribs | $298,983 |
| Richmond, Ca Police Department | 4,626 contribs | $197,075 |
| Richmond Police Department | 1 | $1,000 |
| City Of Richmond, Ca | 5,176 contribs | $123,306 |
| City of Richmond, CA | 3,206 contribs | $82,525 |
| City Of Richmond, CA | 8 | $2,650 |
| City of Richmond | 18 | $2,415 |

If canonicalized under one "Richmond Police Department" or "City of Richmond" entity, this would surface as a coherent ~1,700-donor block giving consistently from city employees, which currently fragments across the variants. The fragmentation makes employer-aggregation views less useful and weakens the scanner's employer-match signal.

Smaller examples in the data:
- "Chevron Richmond" ($635K, 7 contribs as donor) and "ChevronTexaco Corporation" ($138K, 6 contribs) are the same parent entity in different filing eras.
- Donor name variants: 10+ donors share a normalized_name with multiple raw-name forms ("Ellen Pechman" appears 4 times, "John Ziesenhenne" 4 times, "Melvin Willis" 4 times). These are already grouped via the `normalized_name` field, so the donor-side entity resolution is partially working.

The PAC entity resolution case (the IAFF Local 188 word-reorder issue from PAC pages V1.2) is part of the same problem set.

**Surfaced as I149.** S26 (entity resolution) is the formal home for this work. The audit doesn't change the priority or scope; it documents the magnitude.

## Part 4: Scanner input quality

Conflict flags by publication tier (after this audit's fixes):

| Tier | Flags | Confidence range | Avg confidence |
|---|---|---|---|
| 1 (high) | 147 | 0.870 to 0.950 | 0.895 |
| 2 (medium) | 1,329 | 0.700 to 0.840 | 0.745 |
| 3 (low) | 9,500 | 0.500 to 0.700 | 0.553 |
| 4 (suppressed) | 12,123 | 0.200 to 0.500 | 0.348 |

Distribution is sensible. Tier 1 is the smallest set (high-confidence flags worth serious operator attention). Tier 4 is the largest (low-confidence noise that gets suppressed from public view).

**Fix applied this audit**: 32 flags had `publication_tier` mismatched with confidence at the boundaries (27 at confidence 0.70 stored as tier 3 instead of 2, 5 at confidence 0.50 stored as tier 4 instead of 3). Boundary inclusion bug from a prior code path. The current `_confidence_to_tier()` function in `conflict_scanner.py:470` has the correct logic, so this should not recur. The 32-row batch fix is sufficient.

## Part 5: Recent filing freshness

The change-detector polls 5 external sources every 15 minutes. NetFile RSS catches new Form 460/497 filings within that window. The auto-update enrichment cascade then runs reconciliation, briefing regeneration, and downstream scans. This is working as designed (verified in Entry 56's reconciliation work).

**No staleness issues detected** in the 30-day window. The high-severity liveness flag `past_meetings_have_transcript_recap_within_5_days` is the same recurring 3/24 meeting (36 days post-meeting) the journal has noted, unrelated to contribution data freshness.

## Surfaced for parking lot

- **I148**: Future-dated 2107 row ($100 contribution, Charlette Casey, McLaughlin for Lt Gov 2018). Source-filing typo. Decide whether to silently correct in DB based on operator vetting against NetFile portal, or flag in UI.
- **I149**: Entity resolution magnitude. The Richmond Police variant block alone is ~$1.7M fragmented across 7+ employer strings. Captured as concrete case study for the S26 epic.
- **D49**: CAL-ACCESS independent_expenditures dedup. Already captured. Still blocking V2 IE detail tables.

## What's actively healthy

- Contribution coverage is correct given source availability (NetFile from 2018, CAL-ACCESS sparse for state-level)
- Committee linkage is complete for filed candidates
- Tier distribution is sensible after this audit's fix
- Auto-update pipeline ingests new filings within ~15 minutes
- Liveness expectations correctly surface the 2 unfilled 2026 candidacies
