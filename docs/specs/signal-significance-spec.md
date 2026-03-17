# Signal Significance Architecture — Scanner v4

**Sprint:** Backlog (Signal Quality)
**Paths:** A, B, C
**Publication tier:** Graduated (reclassifies what citizens see)
**Depends on:** S9 (Scanner v3, complete), B.46 (entity resolution, in progress)
**Created:** 2026-03-16
**Status:** Draft

## Problem

The current scanner (v3) detects financial connections between officials and entities appearing in agenda items, then scores them on a single confidence axis: "how sure are we this connection exists?" But **confidence ≠ significance**. A high-confidence match on a $150 donation linked to a commission appointment vote is technically correct but meaningless noise. A $300 donation to a council member voting on that same appointment crosses a legal threshold (Levine Act) — that's qualitatively different, not just quantitatively higher.

The system currently surfaces all connections above a confidence floor (0.50) with Strong/Moderate/Low badges. This creates two problems:

1. **Noise buries signal.** Citizens see a wall of "financial connections" with no way to distinguish routine from significant. A single flag on one commission appointment looks alarming but means nothing. Five flags involving the same donor across multiple meetings tells a real story — but gets lost in the noise.

2. **Legal thresholds aren't encoded.** California law creates specific, objective obligations at specific dollar amounts for specific proceeding types. The scanner doesn't distinguish between quasi-judicial proceedings (where the Levine Act sets a $250 recusal threshold) and legislative proceedings (where higher materiality thresholds apply). Every connection is treated the same regardless of the legal framework that governs it.

## Solution

Replace the single confidence axis with a **two-dimensional model: confidence × significance**. Confidence answers "does this connection exist?" Significance answers "should anyone care?"

Three significance tiers:

| Tier | Name | What it means | Who sees it |
|------|------|---------------|-------------|
| **A** | Legal Threshold | A specific California law creates an obligation at this amount for this proceeding type | Public (always) |
| **B** | Pattern | Cross-meeting aggregation reveals recurring entity-official connections | Public (when pattern confidence is sufficient) |
| **C** | Connection | A factual financial link exists but crosses no legal threshold and forms no pattern | Operator only |

### What changes for citizens

- **Summary counts** ("3 conflicts flagged") include only Tier A + Tier B
- **Tier A flags** get specific legal citations: "Levine Act (Gov. Code § 84308) — $300 contribution exceeds $250 threshold for quasi-judicial proceedings. Disclosure and recusal required."
- **Tier B flags** show the pattern evidence: "Donor X appears in 5 agenda items across 3 meetings (2024-2026). Total contributions: $4,200."
- **Tier C connections** are not visible on public pages. Available to the operator for review and audit.

### What changes for the operator

- All three tiers visible with clear labels
- Tier C connections available for pattern review and potential escalation
- Dashboard showing Tier C connections that are approaching Tier A thresholds or Tier B pattern criteria

## 1. Agenda Item Classification

**New capability:** Classify each agenda item as quasi-judicial or legislative.

This is the key unlock — it determines which legal framework applies to financial connections on a given item.

### Quasi-judicial indicators (Levine Act applies)

Items involving individual rights, entitlements, or adjudicative decisions:
- Commission/board appointments ("appoint," "nomination," "vacancy")
- Permit decisions ("conditional use permit," "variance," "use permit," "building permit")
- License approvals ("business license," "franchise," "cannabis license")
- Land-use entitlements ("subdivision," "tentative map," "planned development")
- Contract awards to specific vendors ("award contract to," "professional services agreement with")
- Appeals and hearings ("appeal," "public hearing on application")
- Enforcement actions against specific parties

### Legislative indicators (Levine Act does NOT apply)

Items involving general policy, budgets, or laws:
- Ordinance adoption ("ordinance," "amend municipal code")
- Budget and appropriations ("budget," "appropriation," "fiscal year")
- General policy ("policy," "resolution establishing," "master plan")
- Zoning changes applying generally (area-wide rezoning vs. individual parcel)
- Tax rate setting

### Classification approach

**Option A — Keyword-based heuristic:** Pattern-match against item title and description text. Low cost, fast, ~85% accuracy based on Richmond's consistent eSCRIBE formatting.

**Option B — LLM classification:** Add a classification field to the extraction prompt. Higher accuracy (~95%), but adds API cost per item and requires re-extraction or a separate classification pass.

**Recommended: Option A with LLM fallback.** Keyword matching handles the clear cases (appointments, permits). Ambiguous items get an LLM classification call. Store the result as a new field on `agenda_items`:

```sql
ALTER TABLE agenda_items ADD COLUMN IF NOT EXISTS proceeding_type TEXT;
-- Values: 'quasi_judicial', 'legislative', 'uncertain'
-- NULL = not yet classified
```

## 2. Legal Threshold Detection (Tier A)

### Levine Act (Gov. Code § 84308)

**Applies to:** Quasi-judicial proceedings only
**Threshold:** $250 in contributions from a "party" or "participant" to an officer voting on the proceeding
**Lookback:** 12 months preceding the decision (TODO: confirm via legal research)
**Obligation:** Disclose on the record and recuse from voting

**Detection logic:**
```
IF item.proceeding_type == 'quasi_judicial'
AND contribution.amount >= 250  (cumulative from same source within lookback)
AND contributor is a "party" to the proceeding
  (appointee, permit applicant, contract awardee, license applicant, or their agent/employer)
AND recipient is a sitting council member
THEN → Tier A flag with Levine Act citation
```

**"Party" identification:**
- For appointments: the person being appointed
- For permits/licenses: the applicant (individual or business entity + officers)
- For contracts: the vendor being awarded the contract
- Entity resolution (B.46) critical here — must match donor to party via name, employer, and business registry

### FPPC Financial Interest (Gov. Code § 87100-87105)

**Applies to:** All proceedings (quasi-judicial AND legislative)
**Triggers:**
- Real property interest within 500 feet of property subject to decision
- Income source >$500 in prior 12 months from entity materially affected by decision
- Business position in entity materially affected by decision
- Investment >$2,000 in entity materially affected by decision

**Detection logic:** Leverages existing Form 700 signal detectors. Currently scored by confidence; should be elevated to Tier A when:
- Form 700 property match + land-use item = Tier A
- Form 700 income source match + item directly affecting that source = Tier A

### Gov. Code § 1090 (Financial Interest in Contracts)

**Applies to:** Contract awards specifically
**Threshold:** Any financial interest (no minimum)
**Note:** Stricter than PRA — contracts are voidable if violated

```
IF item involves contract award
AND official has ANY financial connection to the vendor
THEN → Tier A flag with § 1090 citation
```

## 3. Cross-Meeting Pattern Detection (Tier B)

**New pipeline step.** Runs after individual meeting scans. Operates on the full corpus of flags to identify patterns.

### Pipeline architecture

```
Meeting scans (existing) → per-item flags in conflict_flags table
                                    ↓
Pattern detector (NEW)   → reads all flags for each (official, entity) pair
                                    ↓
                         → computes pattern metrics
                                    ↓
                         → writes pattern records to new pattern_flags table
```

### Pattern types

**P1: Recurring donor-vote overlap**
- Same entity appears in items voted on by the same official across 3+ meetings
- Scored by: frequency, time span, financial total, vote alignment

**P2: Financial concentration**
- Single entity's contributions represent >15% of official's total fundraising
- OR cumulative contributions from entity exceed $5,000

**P3: Temporal cycling**
- Donate → favorable vote → donate pattern repeats 2+ times
- Uses existing temporal_correlation signals, elevated when cyclical

**P4: Multi-official coordination**
- Same entity donates to 3+ council members who all vote the same way on items affecting that entity
- Requires cross-official analysis

**P5: Donor-vendor-permit convergence**
- Entity is simultaneously: campaign donor + city vendor + permit/license applicant
- Existing `donor_vendor_expenditure` signal, elevated when persistent across meetings

### Pattern confidence scoring

```
pattern_confidence = base_score(frequency, recency, total_amount)
                   × diversity_boost(signal_type_variety)
                   × consistency_penalty(if pattern has gaps or exceptions)
```

Minimum pattern confidence for public display: 0.70 (same as current Tier 2).

### Storage

```sql
CREATE TABLE IF NOT EXISTS pattern_flags (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    city_fips TEXT NOT NULL DEFAULT '0660620',
    official_id UUID REFERENCES officials(id),
    entity_name TEXT NOT NULL,
    entity_id UUID,  -- from entity registry (B.46) when available
    pattern_type TEXT NOT NULL,  -- 'recurring_overlap', 'financial_concentration', etc.
    confidence NUMERIC(4,3) NOT NULL,
    first_seen DATE NOT NULL,
    last_seen DATE NOT NULL,
    meeting_count INTEGER NOT NULL,
    item_count INTEGER NOT NULL,
    total_amount NUMERIC(12,2),
    evidence JSONB NOT NULL,  -- array of contributing flag IDs + meeting dates
    is_current BOOLEAN DEFAULT true,
    detected_at TIMESTAMPTZ DEFAULT now(),
    scanner_version TEXT DEFAULT 'v4'
);
```

## 4. Tier C: Connection (Operator-Only)

Everything that doesn't meet Tier A or Tier B criteria:

- Single small donation ($100-$500) with no legal threshold crossed
- Old donations (2+ years) with no recurrence
- Employer matches (not direct donations)
- Non-sitting candidates' connections
- Connections on legislative items below materiality thresholds

These remain in the existing `conflict_flags` table with a new field:

```sql
ALTER TABLE conflict_flags ADD COLUMN IF NOT EXISTS significance_tier TEXT;
-- Values: 'legal_threshold', 'pattern', 'connection'
-- NULL = not yet classified (legacy flags)
```

## 5. Frontend Changes

### Public view

**Meeting report page (`/reports/[meetingId]`):**
- "Legal Threshold Flags" section (red) — Tier A only, with statute citations
- "Pattern Flags" section (yellow) — Tier B only, with cross-meeting evidence
- Summary count badge reflects A + B only
- No Tier C visible

**Council profile page:**
- Pattern summary per official: "3 recurring financial patterns detected"
- Link to detail view with full pattern evidence

### Operator view

- All three tiers visible, clearly labeled
- Tier C section collapsible, labeled "Connections (not published)"
- "Approaching threshold" alerts for Tier C connections near Tier A or B criteria

### Badge redesign

| Current | New |
|---------|-----|
| Strong (red, ≥0.85) | Legal Threshold (red, Tier A) |
| Moderate (yellow, ≥0.70) | Pattern (yellow, Tier B) |
| Low (green, ≥0.50) | _Not displayed publicly_ |

## 6. Migration & Reclassification

### Existing flags

All 784 scanned meetings have existing flags in `conflict_flags`. Reclassification:

1. Add `significance_tier` and `proceeding_type` columns
2. Run keyword-based item classification on all existing agenda items
3. Re-evaluate existing flags against Tier A criteria (legal thresholds + proceeding type)
4. Run pattern detector across full flag corpus to generate Tier B records
5. Everything else becomes Tier C

**Expected impact:** Most current flags will become Tier C (connections). A small number will elevate to Tier A (legal thresholds) or Tier B (patterns). The public-facing flag count will decrease significantly. This is correct behavior — the current counts overstate significance.

### Backward compatibility

- `confidence` field remains on all flags (still useful for match quality)
- `significance_tier` is additive, not replacing
- Frontend reads `significance_tier` when present, falls back to confidence-only display for unclassified flags
- API response includes both confidence and significance_tier

## 7. Testing

### Unit tests
- Agenda item classification (keyword matching for quasi-judicial/legislative)
- Levine Act threshold detection (amount, proceeding type, party matching)
- Pattern detector (frequency, financial concentration, temporal cycling)
- Significance tier assignment logic

### Integration tests
- Full scan → flag → classify → pattern pipeline
- Reclassification of existing flags
- Frontend rendering of each tier

### Validation against known cases
- Identify 3-5 real Richmond meetings with known financial connections
- Verify Tier A assignment is correct (legal threshold actually crossed)
- Verify Tier B patterns match manual review
- Verify Tier C demotion doesn't hide anything that should be surfaced

## 8. Dependencies

| Dependency | Status | Impact |
|------------|--------|--------|
| Scanner v3 (S9) | ✅ Complete | Foundation for all signal detection |
| Entity resolution (B.46) | 🔄 In progress | Critical for party-to-donor matching in Tier A |
| Form 700 ingestion (S5) | ✅ Complete | Required for FPPC financial interest detection |
| Socrata expenditure sync (S8) | ✅ Complete | Required for vendor cross-reference |

## 9. Open Questions

1. **Levine Act lookback period:** Is it 12 months? Research pending.
2. **Cumulative vs. single contribution:** Does the $250 Levine Act threshold apply per-contribution or cumulatively from the same source? (Almost certainly cumulative — research pending.)
3. **AB 571 contribution limits:** Should exceeding contribution limits be a Tier A flag? These are campaign finance violations, not conflict-of-interest violations per se.
4. **Pattern thresholds:** The "3+ meetings" and "15% concentration" numbers are initial proposals. Need validation against real Richmond data to calibrate.
5. **Commission appointments as quasi-judicial:** Legal research should confirm this classification. Some FPPC guidance treats appointments differently from permits.

## Parked (Future)

- **Predictive alerts:** "Upcoming meeting has an item likely to trigger Tier A for Council Member X" — pre-meeting notification to operator
- **Pattern decay:** Patterns should weaken over time if the entity stops appearing. Decay function TBD.
- **Cross-city pattern comparison:** When multi-city, compare pattern prevalence across cities of similar size/composition
- **Public comment integration:** Tier A flags could auto-generate public comment language citing the specific statute
- **FPPC complaint template:** For clear Levine Act violations, generate a template for filing with the FPPC (operator-only, extreme caution)
