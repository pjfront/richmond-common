# S9.3 Observations and Improvement Ideas

Captured during S9.3 implementation (2026-03-10).

## Entity Extraction Gap (Medium Priority)

**Observation:** `extract_entity_names()` struggles with short company names embedded in longer phrases. "Acme Corp" inside "Approve contract with Acme Corp" gets returned as the full phrase, not the isolated company name. `names_match()` then fails because it compares "Approve contract with Acme Corp" against "Acme Corp" and sees them as different.

**Impact:** The donor-vendor-expenditure detector works when entities are clean (direct function call with pre-extracted entities), but may miss matches when running through `scan_meeting_json()` where entity extraction produces noisy output.

**Research needed:** What entity extraction approach would work better for civic agenda item text? Options:
1. Named Entity Recognition (NER) via spaCy or similar
2. LLM-based entity extraction (expensive but accurate)
3. Improving the regex-based `extract_entity_names()` to better isolate company names
4. Using the vendor name list itself as a gazetteer for matching (match vendor names directly against item text, bypassing entity extraction entirely)

**Recommendation:** Option 4 (gazetteer approach) is lowest-cost and highest-impact. We already have `city_expenditures.normalized_vendor` as a clean entity list. Match those directly against item text with `name_in_text()` instead of extracting entities first. This inverts the lookup direction.

## Corroboration Model Behavior (Observation)

**Current behavior:** `_signals_to_flags()` groups signals by council_member and applies corroboration boost. All signals for the same official on the same item get the same composite confidence score (the max of each factor across all signals, times the corroboration multiplier).

**Implication:** If an official has a campaign_contribution signal (match_strength=0.6) AND a temporal_correlation signal (match_strength=0.8), the composite uses 0.8 for match_strength. This means the temporal signal's high match quality "lifts" the campaign contribution signal's confidence too.

**Is this correct?** Arguably yes: corroboration means the overall pattern is more credible. But it also means each individual flag's confidence doesn't reflect its own signal quality. A future refinement could show per-flag confidence alongside group confidence. Parked for now.

## Temporal Correlation Dual Existence

**Current state:** Both `scan_temporal_correlations()` (standalone, returns ConflictFlag) and `signal_temporal_correlation()` (integrated, returns RawSignal) exist. The standalone version is used by `cloud_pipeline.py` and the CLI. The integrated version runs inside `scan_meeting_json()`.

**Risk:** Temporal flags could be double-counted if both paths run for the same meeting. The cloud pipeline calls `scan_temporal_correlations()` separately (Step 5b) and also calls `scan_meeting_json()` which now includes temporal signals.

**Action needed (S9.4):** When updating cloud_pipeline.py for DB mode parity, either:
1. Remove the separate Step 5b call and rely on the integrated detector, OR
2. Skip temporal signals in `scan_meeting_json()` when called from cloud_pipeline (add a flag parameter)

Option 1 is cleaner. The integrated version participates in corroboration, which is the whole point.

## Expenditure Data Quality Questions

**Unknown:** How clean is the `city_expenditures.normalized_vendor` data? Vendor normalization quality directly affects false positive/negative rates for the donor-vendor detector.

**Research needed:**
- How many unique normalized_vendor values exist?
- What's the distribution of vendor name lengths? (Very short names = false positive risk)
- Are there obvious normalization issues (e.g., "ACME CORP" vs "Acme Corporation" as separate vendors)?
- What percentage of vendors have only a single transaction? (Low-frequency vendors are lower signal)

**How to check:** Run a Supabase query on `city_expenditures` to get vendor distribution stats.

## Confidence Distribution Prediction

**Expected after S9.5 batch rescan:**
- Form700-only flags (currently 86% of output at 0.40 confidence) should remain at 0.3-0.5
- Flags that now pick up temporal + campaign contribution signals should jump to 0.5-0.8
- Flags with temporal + campaign + donor-vendor-expenditure (triple corroboration) should break 0.85

**Key validation metric:** What percentage of flags score above 0.50 (public visibility threshold) before and after?

## Other Ideas

- **Gazetteer-based vendor matching in scan loop:** Instead of running `extract_entity_names()` and matching against vendors, match the vendor list directly against item text using `name_in_text()`. This would catch "Acme Corp" in "Approve contract with Acme Corp" where entity extraction fails.
- **Expenditure amount as item financial_amount enrichment:** When a vendor matches an agenda item, the expenditure amount could supplement the item's `financial_amount` field (which is often empty for non-consent items).
- **Vendor-official voting pattern:** Beyond just flagging, track whether officials consistently vote Aye on items involving their donors' vendors. This is a coalition-level pattern, not a single-flag signal.
