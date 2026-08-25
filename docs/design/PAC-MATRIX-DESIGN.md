# PAC Pages V2: Three-Layer Redesign

> **Detail-profile plan archived 2026-08-23.** The S29 UX cut retired the
> public detail-profile matrix, timeline, and cycle-selector pattern. Political
> committees, unions, and companies now share a sentence-first detail profile
> followed by the underlying money-in, money-out, and
> independent-expenditure receipts. The shipped PAC index V2 remains unchanged.
> Keep the detail-profile proposal below only as design history; do not resume
> it without a new operator decision.

**Status:** Index V2 shipped. Detail-profile V2 superseded by the S29 shared
sentence-first entity profile.
**Date:** 2026-04-29
**Drives:** I134 V2 graduation, I137 (Explore-then-detail formalization), companion to I129 (Contributions menu rename).

## Purpose

V1.1 of `/pac` and `/pac/[slug]` ships as a list-of-committees with a sortable donor table. The operator's V2 ask is to make these pages answer the resident question "how is money shaping this election" first, with totals and tables relegated to detail. This document lays out the three-layer template and how it applies to PAC pages specifically.

## Reference: Voting-Patterns as Template

[`/council/voting-patterns`](https://richmondcommons.org/council/voting-patterns) is the structural template. It executes five moves we want to formalize and reuse:

1. One primary axis of exploration. The alignment matrix is THE thing. Everything else is filter or detail.
2. Selection has immediate visible consequence. Click a matrix cell, the context strip rewrites itself in plain language.
3. Filters are orthogonal to selection. Matrix selection AND filter bar AND search box all combine. Each layer is independent.
4. Detail table is the receipt, not the headline. It sits below, sortable, scannable. Reveals what your top-level play means.
5. Plain language all the way down. No statistical jargon. No FPPC terminology without translation.

These five moves work together. Removing any one degrades the page substantially.

## The Three-Layer Template (Explore, Temporal, Receipt)

Voting-patterns has top (matrix) and bottom (table). The PAC redesign adds a middle layer: an optional, selection-responsive temporal view.

| Layer | Responsibility | PAC index page | PAC profile page |
|---|---|---|---|
| Top: Explore | Playable surface. One axis of exploration. | Rich list of PACs, each row a sentence + sparkline | Donors x candidates matrix, cells = $ flowed through this PAC |
| Middle: Temporal | Cycle-keyed comparison. Optional, responds to selection. | None (sparkline per row covers it) | Cycle-bars showing this PAC's flow per election cycle |
| Bottom: Receipt | Detail table. Sortable. Filtered by selection above. | None (each row drills into profile) | Contribution-level table |

The middle layer is intentionally optional. On the index page, a per-row sparkline absorbs the temporal job at low density, so the dedicated middle layer is unnecessary. On the profile page, after the user has chosen a PAC, the temporal layer earns its place because it answers the comparative question that the matrix alone cannot.

## Index Page Redesign

**Replace** the current dollar-sorted list with a sentence-led list. Each row contains:

1. **Lede sentence** doing orientation work first, data inflection second. Example: "Richmond Police Officers Association PAC, the political arm of the city's police union. Supporting Bana and Jimenez so far this cycle."
2. **Cycle-bars sparkline** showing this PAC's giving across the last 5 election cycles (2018, 2020, 2022, 2024, 2026 to date). Color one bar by current-cycle status. The sparkline is small, ~80px wide, not interactive at the index level.
3. **Click target** the whole row, navigates to `/pac/[slug]`.

**Sort default:** current-cycle activity (descending). Falls back to most-recent-cycle activity for PACs that have not yet given in 2026. PACs with zero activity in the last two cycles drop to the bottom under a collapsible "Inactive" group.

**Empty-state framing for thin current cycle:** A short paragraph above the list. "PAC activity for the 2026 primary will surge in the final two weeks before each election. The 2024 primary saw 73 percent of PAC dollars arrive after May 15. Check back."

This honesty move matters because residents visiting in early May will otherwise see a list that looks dormant and conclude the page is broken.

## Profile Page Redesign

**Replace** the current donor table with the three-layer structure.

### Top: Donors x Candidates Matrix

Rows: top 20 donors to this PAC by total contributed.
Columns: Richmond candidates this PAC has supported across all available cycles.
Cells: dollar amount of this donor's money that flowed through this PAC to that candidate. Color-coded by amount.

Cell click rewrites the context strip ("Showing the $X that ACME Corp's contribution to RPOA helped support Cesar Zepeda") and filters the temporal layer and receipt table below. Row click filters to one donor's full conduit pattern. Column click filters to one candidate's full PAC support.

The conduit framing matters. Residents intuitively wonder how PAC contributions translate into candidate support. The matrix makes the laundering pattern visible without the page editorializing about it.

### Middle: Cycle-Bars Temporal View

Five bars (one per election cycle: 2018, 2020, 2022, 2024, 2026 to date). Bar height = total $ this PAC moved in that cycle. Bar color segments by recipient candidate.

Default state: aggregate (no selection). All cycles, all candidates, full bars.
With selection: dimmed except for the selected slice. If the user clicks a row in the matrix (donor), the bars dim to that donor's contribution history across cycles. If the user clicks a column (candidate), the bars dim to that candidate's PAC support history. If the user clicks a cell (donor-candidate pair via this PAC), the bars dim to that specific conduit's history.

Why cycle-bars and not a continuous timeline. Campaign finance is naturally cycle-keyed. Residents reason in election cycles ("how much did they spend on the 2024 race"), not in continuous time. Bars surface the cycle structure that a line would obscure.

**Honest empty-bar:** The 2026 bar will be visibly small or empty for many PACs in early May. Inline annotation: "2026 spending typically clusters in the final two weeks before each election." Same honesty principle as the index page.

### Bottom: Contribution Detail Table

Sortable, searchable table of individual contributions. Filters down based on matrix selection. Same pattern as the V1 PAC donor table, just always responsive to the matrix above.

## Component Reuse

The voting-patterns components are the right scaffolding. Adapt rather than rebuild:

| voting-patterns component | PAC profile component | Adaptations |
|---|---|---|
| `AlignmentMatrix.tsx` | `PACFlowMatrix.tsx` | Generalize axis labels, change color scale from agreement-rate to dollar-amount, support row and column click in addition to cell click |
| `DivergentMotionsTable.tsx` | `PACContributionsTable.tsx` (the existing V1 table) | Already exists. Wire selection state from the matrix above. |
| `MemberPicker.tsx` | not needed | Index already covers PAC choice |
| (no temporal component yet) | `CycleBarsTimeline.tsx` | New. SVG, ~5 bars, selection-responsive. |

The only genuinely new component is the cycle-bars timeline. Everything else is parameterized adaptation.

## Data Shape Additions

The current `getPACContributions(committeeId)` returns rows of `{donor_name, amount, contribution_date, ...}`. For the matrix, we need to know where each donor's money ended up flowing. New query:

```
getPACFlowMatrix(committeeId): {
  donors: Array<{ name, total }>,         // rows of matrix, top 20 by total
  candidates: Array<{ name, slug }>,      // columns, drawn from outgoing flows
  cells: Array<{ donor, candidate, amount, cycle }>  // cell values
}
```

The "cell amount" computation is approximate. We do not have donor-level attribution of which incoming dollar funded which outgoing dollar (PACs are pooled). The honest model is proportional: if a donor gave 5 percent of the PAC's total intake during a cycle, attribute 5 percent of each outgoing flow that cycle to them. The matrix should disclose this in a methodology note. The first-pass implementation can simplify to "donors and candidates that overlapped in the same cycle, weighted by donor share."

This is a known limitation that could otherwise mislead. Surface it inline rather than burying it.

## Sequencing

1. Index page redesign first. Lower complexity. Higher daily value (every PAC visit starts here). **Shipped 2026-04-29 (90967d2).**
2. Profile page matrix second, after index lands and the operator confirms the new shape feels right.
3. Cycle-bars timeline third (`CycleBarsTimeline.tsx`, distinct from the index sparkline). Reusable across profile pages and eventually candidate pages. Affordances per [docs/design/INTERACTIVE-DATA-VIZ.md](INTERACTIVE-DATA-VIZ.md): selection-responsive redraw, faint "all pairs" baseline behind selection, dollars vs. share-of-cycle toggle, vertical tick at each city election day.

## Open Questions

These will get resolved when the operator weighs in:

- Cycle-bars: stacked-by-candidate or grouped-bars-per-candidate. Stacked is denser; grouped is easier to read at a glance.
- Matrix color scale for dollar amounts: continuous gradient or quantized buckets. Voting-patterns uses quantized for agreement rate. Dollar amounts have wider dynamic range, may want a log scale or buckets keyed to "small / medium / large" thresholds.
- Whether to gate V2 behind a feature flag (`/pac` shows V1, `/pac-v2` shows V2) for an operator-only A/B comparison, or to ship V2 in place behind `<OperatorGate>` and retire V1.
- Whether the proportional attribution model for matrix cells is honest enough to publish. May need an explicit "approximate" badge per cell.

## Anti-Patterns to Avoid

- Animation for animation's sake. Voting-patterns has none. Hold the bar.
- Gradient sparklines or 3D bars. Civic palette is flat by design (`docs/design/DESIGN-RULES-FINAL.md`).
- "Vibe theater": dressing up a basic chart to look exploratory without adding clarity. Test every visual move against "does this make the data more legible to Leisa Johnson, or just prettier."
- Aggregate dollar totals at the top of any page. The operator pushed back on this in V1.1; the rule generalizes.
- Implicit jargon. Cells, bars, and selection state all need plain-language sentence accompaniment when they update.
