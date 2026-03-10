# AI Parking Lot

_Ideas, research topics, and improvement suggestions captured by the AI during implementation sessions. AI has full autonomy over this file. Periodically reviewed and prioritized with the operator for integration into the roadmap._

_Convention: Every session adds observations here. Items stay until promoted to the sprint backlog or explicitly discarded during a review._

---

## Research Topics

### R1. Entity Extraction for Civic Text
**Origin:** S9.3 (2026-03-10) | **Priority estimate:** Medium-High

`extract_entity_names()` returns noisy phrases ("Approve contract with Acme Corp") instead of clean entity names ("Acme Corp"). This causes `names_match()` failures in the donor-vendor detector when entities aren't pre-extracted.

**Recommended approach:** Gazetteer-based matching. Use `city_expenditures.normalized_vendor` as a clean entity list and match vendor names directly against item text with `name_in_text()`, bypassing entity extraction entirely. Inverts the lookup direction. Lowest cost, highest impact.

**Alternative approaches:** NER via spaCy, LLM-based extraction (expensive), regex improvements.

### R2. Expenditure Data Quality Profile
**Origin:** S9.3 (2026-03-10) | **Priority estimate:** Medium

Unknown: how clean is `city_expenditures.normalized_vendor`? Vendor normalization quality directly affects false positive/negative rates.

**Questions to answer:**
- How many unique normalized_vendor values exist?
- Vendor name length distribution (short names = false positive risk)
- Obvious normalization issues ("ACME CORP" vs "Acme Corporation" as separate vendors)?
- Percentage of single-transaction vendors (low-frequency = lower signal)

**How to check:** Supabase query on `city_expenditures` for vendor distribution stats.

### R3. Per-Signal vs. Group Confidence Display
**Origin:** S9.3 (2026-03-10) | **Priority estimate:** Low

Current corroboration model gives all signals for the same official the same composite confidence (max of each factor across signals, times corroboration multiplier). A temporal signal's high match_strength "lifts" a weaker campaign contribution signal.

**Question:** Should the frontend show per-signal confidence alongside group confidence? Current behavior is defensible (corroboration means the overall pattern is more credible), but individual signal quality is hidden.

---

## Improvement Suggestions

### I1. Gazetteer-Based Vendor Matching in Scan Loop
**Origin:** S9.3 (2026-03-10) | **Blocks on:** R1

Instead of `extract_entity_names()` -> match against vendors, match the vendor list directly against item text using `name_in_text()`. Catches "Acme Corp" in "Approve contract with Acme Corp" where entity extraction fails. Direct implementation of R1's recommended approach.

### I2. Expenditure Amount as Financial Amount Enrichment
**Origin:** S9.3 (2026-03-10) | **Priority estimate:** Low

When a vendor matches an agenda item, the expenditure amount could supplement the item's `financial_amount` field (often empty for non-consent items). Would improve financial_factor scoring for items that don't have explicit dollar amounts.

### I3. Vendor-Official Voting Pattern Detection
**Origin:** S9.3 (2026-03-10) | **Priority estimate:** Low (coalition-level, future sprint)

Track whether officials consistently vote Aye on items involving their donors' vendors. This is a coalition-level pattern, not a single-flag signal. Extends beyond current per-item conflict detection into longitudinal behavioral analysis.

---

## Technical Debt / Cleanup

### D1. Temporal Correlation Dual Existence
**Origin:** S9.3 (2026-03-10) | **Target:** S9.5

Both `scan_temporal_correlations()` (standalone, returns ConflictFlag) and `signal_temporal_correlation()` (integrated, returns RawSignal) exist. Cloud pipeline calls both paths, risking double-counted temporal flags.

**Resolution:** Remove the separate Step 5b call in `cloud_pipeline.py` and rely on the integrated detector. The integrated version participates in corroboration, which is the whole point. Was targeted for S9.4, but S9.4 turned out to be purely the expenditure wiring. Clean up during S9.5 batch rescan when the cloud pipeline path gets exercised.

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
