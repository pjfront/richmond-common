# Scanner v3: Signal-Based Architecture

**Implements:** B.45 (cross-referencing), B.47 (influence pattern taxonomy + confidence model)
**Parks:** B.46 (entity resolution, needs CA SOS API), B.48 (property transactions, needs county data)
**Source research:** `docs/research/political-influence-tracing.md`, user's Compass artifact

## Problem

Scanner produces 20,950 flags, 99.9% medium confidence (0.6-0.8), only 6 high-confidence. Single-dimension scoring (base + amount boost + generic penalty) clusters everything in the same band. The flags are too undifferentiated to be useful for either operators or citizens.

## Architecture Change

**Current:** Monolithic scan with inline matching. Temporal correlation is a separate function. Confidence is single-dimension.

**Proposed:** Signal-based detection where each cross-reference type is an independent detector producing `RawSignal` objects. A composite confidence calculator combines signals from multiple independent sources.

```
scan_meeting (JSON or DB mode)
  -> for each agenda item:
      -> entity extraction (shared)
      -> signal_campaign_contribution()       -> list[RawSignal]
      -> signal_form700_interest()            -> list[RawSignal]
      -> signal_donor_vendor_expenditure()    -> list[RawSignal]  [NEW]
      -> signal_temporal_correlation()        -> list[RawSignal]  [INTEGRATED]
  -> for each (official, item) pair with signals:
      -> composite_confidence(signals)        -> ConflictFlag
```

## New Dataclass: RawSignal

```python
@dataclass
class RawSignal:
    signal_type: str           # 'campaign_contribution', 'donor_vendor_expenditure',
                               # 'form700_property', 'form700_income', 'temporal_correlation'
    match_strength: float      # 0.0-1.0, how precise the entity/name match
    temporal_factor: float     # 0.0-1.0, time proximity (1.0 = within 90 days)
    financial_factor: float    # 0.0-1.0, materiality of amounts
    description: str           # Factual language description
    evidence: list[str]        # Source citations
    legal_reference: str
    financial_amount: str | None
    match_details: dict        # Signal-specific metadata for audit
```

## Multi-Factor Confidence Model

Replaces single-dimension scoring. Four weighted factors + corroboration boost.

```
composite = sitting_multiplier * weighted_avg(
    match_strength    * 0.35,
    temporal_factor   * 0.25,
    financial_factor  * 0.20,
    anomaly_factor    * 0.20
) * corroboration_boost
```

| Factor | 0.0 (weakest) | 0.5 (moderate) | 1.0 (strongest) |
|--------|---------------|-----------------|-------------------|
| match_strength | Loose word overlap | Employer substring | Exact name match |
| temporal_factor | >2 years apart | 6-12 months | Within 90 days |
| financial_factor | <$100 | $500-$5000 | >$5000 or >$100K contract |
| anomaly_factor | Common pattern | Above-median | Statistical outlier |

- **corroboration_boost**: 1 signal = 1.0x, 2 independent signals = 1.15x, 3+ = 1.30x
- **sitting_multiplier**: 1.0 (sitting member), 0.6 (non-sitting)
- **anomaly_factor**: Stub at 0.5 (neutral) initially. Full implementation needs baseline stats.

### Publication Tier Mapping (JUDGMENT CALL: threshold values)

| Tier | Confidence | Label | Visibility |
|------|-----------|-------|------------|
| Tier 1 | >= 0.85 | "High-Confidence Pattern" | Public |
| Tier 2 | >= 0.70 | "Medium-Confidence Pattern" | Public |
| Tier 3 | >= 0.50 | "Low-Confidence Pattern" | Public |
| Internal | < 0.50 | Not shown | Stored for audit |

**Expected impact:** The multi-factor model will spread scores across a wider range. Flags with only a name match but no temporal/financial signal will score 0.3-0.5. Flags with name match + temporal proximity + significant amounts will reach 0.7-0.9. Cross-source corroboration (donor + vendor + expenditure) can break into 0.85+.

## New Cross-Reference: Donor-to-Vendor/Expenditure (Research Priority #1)

The `city_expenditures` table exists (migration 023), `sync_socrata_expenditures` is operational, `v_vendor_spending_summary` view is pre-built.

**Logic:**
1. For each agenda item, extract entity names (existing `extract_entity_names()`)
2. Match entities against `city_expenditures.normalized_vendor`
3. Match entities against `contributions.donor_name` / `donor_employer`
4. If SAME entity appears in BOTH expenditures AND contributions: high corroboration signal
5. Temporal filtering: contribution within 24 months of expenditure

**New flag_type:** `donor_vendor_expenditure`

Research says this single cross-reference reduces false positives from 30-45% to 10-20%.

## Temporal Correlation Integration

Move `scan_temporal_correlations()` from standalone function into the main scan loop as `signal_temporal_correlation()`. Post-vote donation patterns corroborate campaign contribution flags rather than producing separate flags.

Keep `scan_temporal_correlations()` as a thin backward-compat wrapper for `cloud_pipeline.py`.

## Language Framework

Standardize all flag descriptions on research Tier 1 (factual) language:

**Template:** `"Public records show that {entity} contributed ${amount} to {official}'s campaign committee ({committee}) {temporal_context}. {entity} {action_context} in agenda item {item_number}."`

**Blocklist (never include):** "corruption", "illegal", "bribery", "kickback", "scandal", "suspicious"

**Always include when confidence < 0.85:** "Other explanations may exist."

## Files to Modify

| File | Change |
|------|--------|
| `src/conflict_scanner.py` | Major refactor: extract signal detectors, add RawSignal, composite confidence, donor-vendor signal, integrate temporal, language framework |
| `src/db.py` | Store `confidence_factors` dict in evidence JSONB |
| `src/cloud_pipeline.py` | Remove separate Step 5b temporal call (now integrated) |
| `src/migrations/024_scanner_v3_columns.sql` | Add `confidence_factors` JSONB + `scanner_version` to conflict_flags, indexes |
| Tests | New: `test_composite_confidence.py`, `test_signal_detectors.py`, `test_donor_vendor_signal.py`. Update existing scanner tests. |
| `web/lib/types.ts` | Add optional `confidence_factors` to ConflictFlag |

## Execution Steps

1. **Foundation** (~1 session): Add `RawSignal` dataclass, `compute_composite_confidence()`, language constants. Write `test_composite_confidence.py`. No behavior change yet.

2. **Extract signal detectors** (~1 session): Refactor `scan_meeting_json()` inline code into `signal_campaign_contribution()`, `signal_form700_property()`, `signal_form700_income()`. Each returns `list[RawSignal]`. Conversion layer to `ConflictFlag`. Update existing tests.

3. **Integrate temporal + add donor-vendor** (~1 session): Create `signal_temporal_correlation()`, create `signal_donor_vendor_expenditure()`. Write new tests. Migration 024.

4. **DB mode parity** (~0.5 session): Mirror signal architecture into `scan_meeting_db()`.

5. **Batch rescan + validation** (~0.5 session): Run migration, dry-run scan, compare distributions, full rescan.

6. **Frontend labels** (~0.5 session): Update confidence badge labels, optional factor breakdown display.

**Total: ~4-5 sessions**

## Judgment Calls — RESOLVED (2026-03-09)

1. **Publication tier threshold values** (0.85/0.70/0.50): **Public.** All tiers visible to citizens.
2. **Publication tier for `donor_vendor_expenditure`** flag type: **Public.**
3. **Confidence badge label text**: **"High-Confidence Pattern"** (>=0.85), **"Medium-Confidence Pattern"** (>=0.70), **"Low-Confidence Pattern"** (>=0.50). Consistent noun, confidence qualifier does the work. Below 0.50: hidden (stored internally).
4. **Language framework templates**: **Approved.** Factual template ("Public records show that..."), blocklist (never "corruption", "illegal", "bribery", "kickback", "scandal", "suspicious"), hedge clause ("Other explanations may exist." when confidence < 0.85).

## Parked

- B.46: Entity Resolution (CA SOS API, CSLB, ProPublica) -- structural fix for matching precision, multi-sprint
- B.48: Property Transaction Timing -- needs county recorder data
- LLC ownership chain detection -- needs SOS bulk data
- Full anomaly_factor implementation -- needs baseline spending stats
