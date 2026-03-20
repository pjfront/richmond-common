# Research: Behested Payment Absence Detection

**Origin:** S13 behested payments research session (2026-03-20)
**Status:** Research concept — not yet scoped for implementation
**Dependencies:** S13.1 (Form 803 pipeline, complete), S10 (text search, complete)

---

## The Concept

When an elected official publicly solicits a payment — "I encourage Chevron to support the Richmond Promise" — California law requires them to file Form 803 with the FPPC within 30 days if the payment reaches $5,000. The *absence* of an expected filing is itself a meaningful signal.

This is not an allegation of wrongdoing. Officials may solicit below-threshold amounts, payments may flow through systems we don't monitor, or filings may be pending. But the gap between a public solicitation and the absence of a corresponding disclosure is worth surfacing — with appropriate uncertainty language.

## Detection Architecture

### Signal Source: Meeting Minutes Text

Richmond council meeting minutes are highly parseable. Solicitation language follows recognizable patterns:

**High-confidence solicitation patterns:**
- "I encourage [entity] to donate/fund/support..."
- "I request that [entity] contribute to..."
- "I urge [entity] to make a contribution to..."
- "At my request, [entity] has agreed to..."

**Lower-confidence patterns (contextual):**
- "[Official] thanked [entity] for their generous support of..."
- "The Mayor recognized [entity] for their donation to..."
- Discussion of specific nonprofit funding during council communications

### Cross-Reference Logic

```
For each solicitation detected in minutes:
  1. Extract: official_name, target_entity, beneficiary_entity, date
  2. Search Form 803 filings:
     - Same official_name (fuzzy match)
     - Payor matches target_entity
     - Payment date within 30-90 day window after solicitation
  3. If match found: annotate the behested payment with the solicitation context
  4. If no match found: flag as "expected filing not found" with uncertainty
```

### Signal Type Sketch

```python
def signal_behested_absence(
    item_num: str,
    item_title: str,
    item_text: str,
    official_name: str,
    behested_payments: list[dict],
    ctx: "_ScanContext",
) -> list[RawSignal]:
    """Detect solicitation language without a corresponding Form 803 filing."""
    # ... pattern matching + temporal cross-reference
```

**Signal characteristics:**
- `signal_type`: `"behested_filing_gap"`
- `match_strength`: 0.50-0.65 (lower than transactional signals — absence is weaker evidence)
- `temporal_factor`: Decay from solicitation date (strongest within 30 days, weaker at 90)
- `description`: Factual language only — "Official [X] used solicitation language regarding [Entity] on [Date]. No corresponding Form 803 filing was found in FPPC records within 90 days."

## False Positive Risks

1. **Below-threshold payments.** If the requested payment was under $5,000, no Form 803 is required. We can't detect the amount from solicitation language alone.

2. **Local filing systems.** The FPPC bulk XLS covers state-level officials (Assembly, Senate, Governor). Local officials (Mayor, City Council) may file through a separate system not captured in our pipeline. This is the biggest gap — see AI Parking Lot D5.

3. **Informal solicitation.** Most behesting happens outside recorded meetings — phone calls, dinners, fundraiser events. Meeting minutes capture only the most public solicitations.

4. **Pending filings.** The 30-day window means a filing may be legitimately in transit. The signal should only fire after 90 days (3x the legal window) to reduce false positives.

5. **Third-party solicitation.** An official's aide or supporter may solicit on their behalf. This is covered by Gov Code §82015 but harder to detect in minutes text.

## Bay Area Precedent Context

Three tiers of the same mechanism illustrate the spectrum:

**Criminal (Mohammed Nuru, SF 2020):** Used behested payments as de facto bribes through Parks Alliance accounts. Convicted of honest services fraud, 7 years. The payment structure was designed to circumvent gift restrictions.

**Legal-but-sketchy (Mark Farrell, SF 2015-16):** Solicited housing developers to donate to Parks Alliance, then carved out legislative exceptions for those developers. No charges filed. The pattern — donation → legislative outcome → repeat — was visible but not prosecutable.

**Structural-open (Jerry Brown, Oakland charter schools):** $3M/year in behested payments to Oakland charter schools from entities with business before the Governor. The San Pablo Lytton Casino gave $100K while seeking the Governor's approval to expand. All legal, all disclosed on Form 803. The transparency system worked exactly as designed — the question is whether anyone was looking.

Richmond Common's value is in the Farrell/Brown zone: making the pattern visible without alleging a crime. The absence signal adds a new dimension — not just "here's what was disclosed" but "here's what we'd expect to be disclosed based on public statements."

## Implementation Dependencies

- **Official-name resolution** (already built in S13-A scanner context)
- **Meeting text search** (S10 PostgreSQL text search, complete)
- **Form 803 data** (S13.1 pipeline, complete — 39 Richmond-related records)
- **Local Form 803 filings** (gap — requires CPRA request to City Clerk or discovery of local filing portal)

## Recommended Next Steps

1. **CPRA request** for local Form 803 filings through NextRequest (closes the local-official filing gap)
2. **Solicitation language corpus** — manually review 10-20 council meeting minutes for solicitation patterns to build the regex/keyword set
3. **Scope as S13.5 signal detector** — fits naturally alongside the other astroturf pattern detectors
4. **Publication tier: Operator-only** until validation confirms acceptable false positive rate
