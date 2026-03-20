# Research: Revenue Dependency as Influence Context

**Origin:** S13 behested payments research session (2026-03-20)
**Status:** Research concept — not yet scoped for implementation
**Dependencies:** S8.1 (Socrata sync, complete), S14-C/D (influence maps, in progress)

---

## The Insight

A $50,000 behested payment from Chevron reads differently when you know Chevron is also the source of approximately 24% of Richmond's general fund revenue. Transactional influence signals (campaign contributions, behested payments, lobbyist registrations) gain context when paired with structural financial relationships.

This is not an adversarial framing. The $550M tax settlement between Richmond and Chevron was good policy — it avoided years of litigation and delivered more money to the city than the ballot measure likely would have. The progressive coalition supported it unanimously. But the structural shape of that relationship — a single entity providing nearly a quarter of city revenue — is context that citizens deserve to see alongside transactional disclosures.

As the Chat research conversation put it: *"Influence operates through structures that are legal, open, and rational from everyone's perspective, and still worth mapping."*

## Data Available

### Socrata Revenue Data

**Dataset:** `budgeted_revenues` (wvkf-uk4m) on transparentrichmond.org
**Status:** Synced via `data_sync.py` → `sync_socrata_expenditures()` (S8.1, complete)
**Fields:** fund, department, revenue category, budgeted amount, actual amount, fiscal year

### What We Can Compute

1. **Top revenue sources by entity** — Aggregate revenue line items by source entity (requires normalization of entity names across Socrata categories)
2. **Dependency percentage** — Entity's total contribution as % of general fund revenue
3. **Year-over-year trends** — Is the dependency growing, stable, or declining?

### What We Can't Compute (Yet)

1. **Chevron-specific line items** — Socrata revenue data may categorize by revenue *type* (Utility User Tax, Property Tax) rather than by *payer*. Chevron's contribution is estimated from public reporting, not necessarily line-itemized in the budget.
2. **Settlement vs. ongoing revenue** — The $550M settlement is a discrete event; ongoing tax payments are structural. These should be distinguished.
3. **Indirect revenue** — Chevron employees' income taxes, property values near the refinery, economic multiplier effects. These are real but not computable from available data.

## Display Concept

### Contextual Annotation on Influence Maps

When an entity appears on an influence map (S14-C item center or S14-D official center) AND that entity is also a major revenue source, add a contextual line:

```
[After behested payment or contribution narrative]

Context: Chevron is also a major source of city revenue, contributing
an estimated 24% of Richmond's general fund through utility user taxes
and property taxes ($58.8M in taxes and settlement payments as of 2023).
Source: Richmond city budget data, US News & World Report reporting.
```

### Methodology Page Section

The `/influence/methodology` page (S14 C5) should include a "Structural Financial Relationships" section explaining:

- What revenue dependency means and why it's shown
- How the percentage is calculated (or estimated, with source citations)
- That structural dependency is not corruption — it's a feature of Richmond's economic geography
- That the platform shows this context so citizens can form their own judgment

## Framing Challenge (Judgment Call)

**"Structural dependency" vs. "revenue context"** — The accurate term is "structural dependency" (a single entity providing a large share of revenue creates structural incentives). But "dependency" can read as adversarial. "Revenue context" is neutral but vague.

Proposed approach: use "revenue context" in the UI label, "structural financial relationship" in the methodology explanation, and avoid "dependency" in citizen-facing text. The methodology page can explain the concept fully.

**The $550M settlement framing** — This is a particularly interesting case. It was:
- Legal (negotiated settlement)
- Open (unanimous public council vote)
- Supported by the progressive coalition
- Good policy by most measures (avoided litigation risk, delivered more money)
- AND structurally identical to a behested payment at massive scale

The platform should present this as context, not as a finding. It's an example of why structural relationships matter — not because they're wrong, but because they're load-bearing for understanding city governance.

## Known Limitations

1. **Entity name normalization** — Socrata uses different entity names than FPPC filings. "Chevron Products Company" vs. "Chevron Corporation" vs. "ChevronTexaco" need to resolve to the same entity.
2. **Revenue attribution precision** — Budget data may not attribute revenue to specific companies. Estimates from news reporting (US News, Richmondside) are Tier 2 sources, not Tier 1.
3. **Temporal alignment** — Budget data is annual; influence map signals are per-meeting. The revenue context should use the most recent complete fiscal year.

## Recommended Next Steps

1. **Query Socrata revenue data** for Chevron-attributable line items (Utility User Tax is the most directly attributable)
2. **Research the $58.8M figure** cited in US News reporting — verify against budget data
3. **Design entity-level metadata** in structured core for "major revenue source" annotations
4. **Scope as S14-C/D contextual enrichment** — display alongside transactional signals, not as a separate signal type
5. **Framing review** (judgment call) — operator reviews the specific language before any citizen-facing display
