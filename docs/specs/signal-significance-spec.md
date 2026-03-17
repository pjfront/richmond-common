# Signal Significance Architecture — Scanner v4

**Sprint:** Backlog (Signal Quality)
**Paths:** A, B, C
**Publication tier:** Graduated (reclassifies what citizens see)
**Depends on:** S9 (Scanner v3, complete), B.46 (entity resolution, in progress)
**Created:** 2026-03-16
**Status:** Draft

## Problem

The current scanner (v3) detects financial connections between officials and entities appearing in agenda items, then scores them on a single confidence axis: "how sure are we this connection exists?" But **confidence ≠ significance**. A high-confidence match on a $150 donation linked to a commission appointment vote is technically correct but meaningless noise — and legally irrelevant, because the FPPC treats commission appointments as employment contracts, exempt from the Levine Act entirely. Meanwhile, a $600 donation from a permit applicant to a council member voting on that permit crosses a legal threshold (Levine Act, $500 as of 2025) — that's qualitatively different, not just quantitatively higher.

The system currently surfaces all connections above a confidence floor (0.50) with Strong/Moderate/Low badges. This creates two problems:

1. **Noise buries signal.** Citizens see a wall of "financial connections" with no way to distinguish routine from significant. A single flag on one commission appointment looks alarming but means nothing. Five flags involving the same donor across multiple meetings tells a real story — but gets lost in the noise.

2. **Legal thresholds aren't encoded.** California law creates specific, objective obligations at specific dollar amounts for specific proceeding types. The scanner doesn't distinguish between quasi-judicial proceedings (where the Levine Act sets a $500 recusal threshold as of 2025), legislative proceedings (where different materiality thresholds apply under the PRA), and exempt proceedings like commission appointments (where the Levine Act doesn't apply at all). Every connection is treated the same regardless of the legal framework that governs it.

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
- **Tier A flags** get specific legal citations: "Levine Act (Gov. Code § 84308) — $600 contribution exceeds $500 threshold for entitlement proceedings. Disclosure and recusal required."
- **Tier B flags** show the pattern evidence: "Donor X appears in 5 agenda items across 3 meetings (2024-2026). Total contributions: $4,200."
- **Tier C connections** are not visible on public pages. Available to the operator for review and audit.

### What changes for the operator

- All three tiers visible with clear labels
- Tier C connections available for pattern review and potential escalation
- Dashboard showing Tier C connections that are approaching Tier A thresholds or Tier B pattern criteria

## 1. Agenda Item Classification

**New capability:** Classify each agenda item by proceeding type.

This is the key unlock — it determines which legal framework applies to financial connections on a given item. Research confirmed four distinct categories (see `docs/research/california-ethics-laws.md`):

### Entitlement for use (Levine Act § 84308 applies)

Items involving a "license, permit, or other entitlement for use" for a specific party:
- Permit decisions ("conditional use permit," "variance," "use permit," "building permit")
- License approvals ("business license," "franchise," "cannabis license")
- Land-use entitlements ("subdivision," "tentative map," "planned development")
- Non-competitively-bid contract awards ("award contract to," "professional services agreement with")
- Franchise grants
- Site-specific rezoning (specific parcel at owner's request)
- Appeals and hearings on the above ("appeal," "public hearing on application")

### Legislative (Levine Act does NOT apply; PRA § 87100 still applies)

Items involving general policy, budgets, or laws where interests affected are "many and diverse":
- Ordinance adoption ("ordinance," "amend municipal code")
- Budget and appropriations ("budget," "appropriation," "fiscal year")
- General policy ("policy," "resolution establishing," "master plan")
- General plan amendments
- Area-wide rezoning (district-level, not parcel-specific)
- Tax rate setting

### Contract (§ 1090 applies — strictest regime)

Contract awards deserve special handling because § 1090 is far more severe than the Levine Act:
- Contracts are **void ab initio** if an official has any financial interest (not just voidable)
- Recusal does NOT fix it — if one board member has a conflict, the entire board is prohibited
- Willful violation is a felony with lifetime office ban
- Keywords: "contract," "agreement," "professional services," "award to," "vendor"

Note: Non-competitively-bid contracts are ALSO entitlements for use (Levine Act applies too). Competitively bid contracts are exempt from the Levine Act but still subject to § 1090.

### Exempt proceedings (Levine Act does NOT apply)

- Commission/board appointments ("appoint," "nomination," "vacancy") — FPPC treats these as employment contracts, explicitly excluded from "entitlement for use"
- Personal employment contracts
- Labor contracts
- Competitively bid contracts (exempt from Levine Act, but § 1090 still applies)

### Classification approach

**Option A — Keyword-based heuristic:** Pattern-match against item title and description text. Low cost, fast, ~85% accuracy based on Richmond's consistent eSCRIBE formatting.

**Option B — LLM classification:** Add a classification field to the extraction prompt. Higher accuracy (~95%), but adds API cost per item and requires re-extraction or a separate classification pass.

**Recommended: Option A with LLM fallback.** Keyword matching handles the clear cases (appointments, permits, contracts). Ambiguous items get an LLM classification call. Store the result as a new field on `agenda_items`:

```sql
ALTER TABLE agenda_items ADD COLUMN IF NOT EXISTS proceeding_type TEXT;
-- Values: 'entitlement', 'legislative', 'contract', 'appointment', 'uncertain'
-- NULL = not yet classified
```

## 2. Legal Threshold Detection (Tier A)

Three distinct legal frameworks, each with different thresholds and consequences. Research source: `docs/research/california-ethics-laws.md`.

### 2a. Levine Act (Gov. Code § 84308)

**Applies to:** Entitlement for use proceedings only (NOT appointments, NOT competitively bid contracts)
**Threshold:** >$500 cumulative from a party/participant to an officer (raised from $250 effective Jan 1, 2025 by SB 1243)
**Lookback:** 12 months preceding the decision (confirmed)
**Obligation:** Disclose on the record and recuse from voting
**Cure:** Return amount exceeding $500 within 30 days (extended from 14 days by 2025 amendments), if acceptance was not knowing/willful

**Critical:** The Act also applies to the **appointing body** (city council) when it exercises authority or budgetary control over the decision-making body. Example: developer donates to council member → Planning Commission permit hearing → council member must still recuse if council has authority over the Commission.

**Detection logic:**
```
IF item.proceeding_type == 'entitlement'
AND sum(contributions from party/participant to official within 12 months) > 500
AND contributor is a "party" or "participant" in the proceeding
  (permit applicant, license applicant, non-competitive contract awardee, franchise applicant)
AND recipient is a sitting council member or commission member
THEN → Tier A flag with Levine Act citation
```

**"Party" vs "Participant" identification:**
- **Party:** Person who files an application for, or is the subject of, the proceeding
- **Participant:** Not a party, but actively supports/opposes AND has a financial interest. Must have lobbied, testified, or acted to influence.
- **Agent:** Paid representative — contributions tracked but NO LONGER aggregated with principal's (2025 change via SB 1243)
- For permits/licenses: the applicant (individual or business entity)
- For non-competitive contracts: the vendor being awarded
- Entity resolution (B.46) critical here — must match donor to party via name, employer, and business registry

**What is NOT flagged under Levine Act:**
- Commission/board appointments (employment contract exemption)
- Competitively bid contracts
- Legislative proceedings (ordinances, budgets, general policy)
- Contributions ≤$500

**Historical threshold handling:** For meetings before Jan 1, 2025, the threshold was $250. The scanner must apply the threshold that was in effect at the time of the meeting.

### 2b. PRA Financial Interest (Gov. Code § 87100-87105)

**Applies to:** ALL governmental decisions (quasi-judicial AND legislative — broadest scope)
**Triggers and thresholds (confirmed via FPPC regulations):**

| Interest Type | Threshold | Materiality Standard |
|---------------|-----------|---------------------|
| Real property | $2,000+ interest value | Within 500 ft: **presumed material** (rebuttable only by clear and convincing evidence). 500-1000 ft: material if affects market value, development potential, traffic, noise, etc. Beyond 1000 ft: generally not material. |
| Investment | $2,000+ | Material if decision affects entity's value |
| Business position | Any (director, officer, partner, trustee, employee) | Material if decision affects the entity |
| Income source | $500+ in prior 12 months | Material if decision affects source's income by $1,000+ |
| Gifts | $630+ per source per calendar year (2025-2026) | Potential conflict |

**Recusal procedure (§ 87105):** Public identification of interest → recuse from discussion and vote → **leave the room** until after disposition. No cure — must recuse.

**Detection logic:** Leverages existing Form 700 signal detectors. Elevated to Tier A when:
- Form 700 property match + land-use item within 500 ft = Tier A (presumed material)
- Form 700 income source ($500+) + item directly affecting that source = Tier A
- Form 700 investment ($2,000+) + item affecting that entity = Tier A

### 2c. Gov. Code § 1090 (Financial Interest in Contracts)

**Applies to:** Contract awards specifically
**Threshold:** ANY financial interest (no minimum dollar amount)
**Severity:** Most severe of all three frameworks

**Key distinctions from Levine Act and PRA:**
- Contracts made in violation are **void ab initio** (automatically void, not just voidable — no court action needed)
- **Recusal does NOT fix it.** If one board member has a § 1090 conflict, the **entire board** is prohibited from acting on the contract
- Willful violation is a **felony** punishable by state prison
- **Lifetime bar from holding public office** in California
- "Remote interest" exception (§ 1091): official discloses interest, it's noted in official records, and official abstains — contract may proceed

**Detection logic:**

Campaign contributions alone don't create a § 1090 financial interest — the question is whether the official has a direct financial stake in the contract. Tier A requires a stronger signal than just a donation:

```
IF item.proceeding_type == 'contract'
AND official has a DIRECT financial interest in the contracting entity:
  - Form 700 income source from the entity ($500+ in 12 months)
  - Form 700 investment in the entity ($2,000+)
  - Business position (director, officer, partner, employee)
  - Real property interest affected by the contract
THEN → Tier A flag with § 1090 citation
  Label: "Section 1090 — Financial interest in contracts. Recusal alone does not resolve.
  If any member has a conflict, the entire board may be prohibited from acting."
```

A campaign contribution from a contract vendor is a **Tier C connection** (operator-only) unless it co-occurs with one of the above direct interests, in which case the combination elevates to Tier A. The contribution is relevant context but not sufficient for § 1090 on its own.

## 2d. Party Identification — Critical Path

Tier A (Levine Act) detection is only as good as our ability to answer: **"Who is the party to this proceeding, and did they donate?"** This is the hardest part of the system and the one most likely to produce false positives or miss real violations.

### The problem

The Levine Act doesn't flag *any* donor who appears in an agenda item. It flags donors who are **parties or participants** in the specific proceeding. A developer who donated $1,000 to a council member is only a Levine Act issue if that developer is the applicant on the permit being decided — not just because their name appears somewhere in the item text.

The current scanner (v3) matches donor names against item text broadly. That's fine for Tier C connections, but Tier A requires knowing the **role** the entity plays in the proceeding.

### What we need to extract

For each entitlement/contract agenda item, identify:
- **The applicant/party:** Who filed the application, who is requesting the permit/license/contract?
- **The property/subject:** What address, parcel, or project is this about?
- **The vendor:** For contracts, who is being awarded the contract?

### Extraction approaches

**Approach 1 — Structured extraction from agenda item text (recommended first step)**

Richmond's eSCRIBE agenda items follow patterns:
- Permits: "Application by [PARTY] for [TYPE] at [ADDRESS]"
- Contracts: "Award contract to [VENDOR] for [DESCRIPTION]"
- Licenses: "[APPLICANT] requests [LICENSE TYPE]"

Add a `party_entities` JSONB field to `agenda_items`:
```sql
ALTER TABLE agenda_items ADD COLUMN IF NOT EXISTS party_entities JSONB;
-- Structure: [{"name": "...", "role": "applicant|vendor|licensee", "raw_text": "..."}]
```

For existing items, a targeted extraction pass (keyword-based or LLM) can populate this. For new items, add it to the extraction prompt.

**Approach 2 — Cross-reference with permits/licenses database**

The city_permits and city_licenses tables already have applicant names. When an agenda item references a permit number or address, join against these tables to identify the party programmatically. This is higher-confidence than text extraction because it's structured data.

```
agenda_item mentions permit #12345
  → city_permits WHERE permit_number = '12345'
  → applicant = "ABC Development LLC"
  → contributions WHERE donor matches "ABC Development" (via entity resolution B.46)
  → if sum > $500 within 12 months → Tier A
```

**Approach 3 — Entity resolution as the bridge (B.46)**

The entity registry (B.46, in progress) is the connective tissue. It resolves:
- Donor "John Smith" → entity_id
- Permit applicant "Smith Construction" → entity_id (if officer relationship known)
- Form 700 income source "Smith Construction" → entity_id

Without reliable entity resolution, party-to-donor matching will have both false positives (name collisions) and false negatives (same entity under different names).

### Confidence by approach

| Approach | Confidence | False positive risk | False negative risk |
|----------|------------|--------------------|--------------------|
| Text matching (current) | Low | High (name appears ≠ party) | Medium |
| Structured extraction | Medium | Low (role identified) | Medium (depends on text quality) |
| Permit/license DB join | High | Very low (structured data) | High (not all items have permit numbers) |
| Entity resolution bridge | High | Low | Low (when registry is complete) |

**Recommended: Layer all three.** Use permit/license DB joins when available (highest confidence). Fall back to structured extraction for items without permit numbers. Use entity resolution to bridge donor ↔ party matching. Text matching alone is insufficient for Tier A — it's fine for Tier C connections but not for legal threshold claims.

### Evaluation and improvement loop

This is not a "build and done" capability. Party identification accuracy directly determines whether Tier A flags are trustworthy. Plan for:

1. **Baseline measurement:** After initial implementation, manually review 50 Tier A flags against actual agenda packets. Calculate precision (what % of Tier A flags are correct?) and recall (what % of real Levine Act situations did we catch?).
2. **Ongoing audit:** Each quarter, sample 20 flags across all tiers. Track precision/recall trends.
3. **Error taxonomy:** Categorize misses — was it a name matching failure? Missing permit data? Entity resolution gap? Wrong proceeding type classification?
4. **Threshold tuning:** If precision is low, tighten requirements (e.g., require DB join, not just text match, for Tier A). If recall is low, expand entity resolution coverage.

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
- **All financial connections on commission/board appointments** — Levine Act doesn't apply, but useful context for operator pattern review (e.g., "appointee donated to all 4 council members who voted for their appointment" is not illegal but worth knowing)
- **Campaign contributions from contract vendors** without a direct financial interest — the donation alone doesn't trigger § 1090, but the operator should see it
- **Contribution limit violations** (donations exceeding Richmond's local limit or the $5,900/election state default) — these are campaign finance violations, not conflict-of-interest issues, but surface to operator for awareness. If we ever find one in Richmond, we'll figure out the right response then.

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

### Resolved by research (2026-03-16)
1. ~~**Levine Act lookback period:**~~ Confirmed 12 months preceding the decision.
2. ~~**Cumulative vs. single contribution:**~~ Confirmed cumulative (>$500 aggregate per candidate).
3. ~~**Commission appointments as quasi-judicial:**~~ **They are exempt.** FPPC treats appointments as employment contracts, excluded from "entitlement for use." This validates the original design instinct.
4. ~~**Levine Act threshold:**~~ $500 as of Jan 1, 2025 (raised from $250 by SB 1243). Historical data must use the threshold in effect at the meeting date.

### Resolved by design decisions (2026-03-16)
5. ~~**AB 571 contribution limits as Tier A:**~~ No. These are campaign finance violations, not conflict-of-interest issues. Surface to operator as Tier C. If we find an actual violation in Richmond, figure out the right response then.
6. ~~**§ 1090 detection scope:**~~ Campaign contributions alone are insufficient for Tier A § 1090 flags. Require a direct financial interest (Form 700 income/investment, business position). Contributions from contract vendors are Tier C (operator-only).
7. ~~**Appointment connections:**~~ Tier C (operator-only). Exempt from Levine Act but valuable for pattern recognition across many votes.

### Resolved by follow-up research (2026-03-16)
8. ~~**Richmond's local contribution limit:**~~ **$2,500 per person per election cycle** (Sec. 2.42.050). Significantly lower than state default ($5,900). No local pay-to-play restrictions — Levine Act is the controlling law for proceeding-related contributions.

### Still open
9. **Pattern thresholds:** The "3+ meetings" and "15% concentration" numbers are initial proposals. Need validation against real Richmond data to calibrate.
10. **Agent identification:** How to programmatically identify "agents" (lobbyists, consultants, attorneys) in contribution data. Currently no structured field for this.
11. **Historical threshold transition:** For the batch reclassification of 784 meetings, need to apply $250 threshold for pre-2025 meetings and $500 for post-2025. The scanner needs a threshold-by-date function.
12. **Party identification accuracy target:** What precision/recall is acceptable for Tier A flags before graduating to public? Proposed: 95% precision minimum (1 in 20 false positives max), 70% recall acceptable initially (missing some is better than false accusations).

## Parked (Future)

- **Predictive alerts:** "Upcoming meeting has an item likely to trigger Tier A for Council Member X" — pre-meeting notification to operator
- **Pattern decay:** Patterns should weaken over time if the entity stops appearing. Decay function TBD.
- **Cross-city pattern comparison:** When multi-city, compare pattern prevalence across cities of similar size/composition
- **Public comment integration:** Tier A flags could auto-generate public comment language citing the specific statute
- **FPPC complaint template:** For clear Levine Act violations, generate a template for filing with the FPPC (operator-only, extreme caution)
