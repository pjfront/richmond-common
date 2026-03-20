# Influence Map + Meetings Redesign

**Sprint:** 14 (Discovery & Depth)
**Paths:** A, B, C
**Publication tier:** Graduated (all phases operator-only until validated)
**Depends on:** S9 (conflict scanner v3, complete), S11 (information design, complete), S13 (influence transparency, complete)

## Problem

Richmond Common's data surfaces are fragmented. Financial connections, voting records, campaign contributions, Form 700 disclosures, and conflict flags each live on separate pages with separate mental models. A citizen who wants to understand "what's really going on with this vote" has to visit 3-4 pages and mentally stitch relationships together.

The meetings page compounds this: agenda items are listed sequentially by item number, giving equal visual weight to a $2.4M development deal (split 4-3) and a proclamation declaring Arbor Day. There's no visual signal for which items are worth exploring deeper.

## Solution

Two integrated workstreams that form a single user journey:

1. **Discovery layer** (meetings redesign): Calendar navigation, topic-board grouping, significance-based card sizing, hero item pattern
2. **Depth layer** (influence map): Sentence-based narrative pages centered on agenda items or officials, replacing the transparency report and financial connections pages

### Design Principles

- **Sentences, not tables.** Every connection is expressed as a plain-language sentence that carries its own context even when screenshotted or shared out of context. (Extends D6/T7.)
- **Meeting is navigation, not center.** Meetings are containers; the explosive agenda item is the subject. Meetings are launchpads, not destinations.
- **Two centers.** Agenda Item and Official. Same data, different topology. Each links to the other.
- **Objective hero selection.** Hero items are selected by measurable signals (split votes, pulled-from-consent, financial connections), not editorial judgment. This is AI-delegable.

---

## Phase A: Meeting Detail Redesign

**Scope:** Restructure `/meetings/[id]` layout. No new pages.

### A1: Topic Board Layout

Replace sequential item list with category-grouped sections.

- Each of the 14 categories (from `AgendaCategory` enum in `src/models.py`) gets a visual section
- Section header: category name + item count (U4: "Housing (4 items)")
- Within sections: compact cards — title + one-line summary + vote result badge
- Empty categories don't render
- Category order: most-items-first (dynamic per meeting)
- Item numbers become metadata (visible on hover/detail), not the organizing principle

### A2: Significance-Based Card Sizing

Variable card treatment based on objective signals:

| Signal | Treatment |
|--------|-----------|
| Split vote (nays > 0) | Large card, prominent placement |
| Pulled from consent | Highlighted border/background |
| Financial amount present | Dollar amount as visual anchor text |
| Financial connections flagged | Subtle indicator: "3 financial connections >" |
| Consent calendar | Own section, compact single-line per item |
| Procedural (call to order, adjournment) | Thin timeline strip, near-invisible |

### A3: Hero Item Pattern

If a meeting has a split vote or pulled-from-consent item, feature it narratively at the top of the page:

```
The most contested item: Council voted 4-3 on [title].
[One-line plain language summary]
[View influence map >]
```

Hero selection criteria (all objective, AI-delegable):
1. Split votes, ordered by margin (4-3 > 5-2 > 6-1)
2. Pulled-from-consent items
3. Items with financial connections flagged
4. If no signals: no hero item rendered (not every meeting is dramatic)

### A4: Local Issue Filter Bar

A row of local issue pills above the topic board. Only shows issues with at least one match in the current view (no dead buttons). Each pill shows match count.

```
[Chevron · 2] [Point Molate · 1] [Rent Board · 3] [Housing · 4]
```

Click a pill → categories without matching items collapse, remaining categories show only matching items. Click again to clear. Multiple selection not needed (one filter at a time keeps it simple).

Implementation: `detectLocalIssues()` already runs client-side on each item title. Filter is just a state variable on the topic board component. No new queries needed.

Also applies to the category drill-through page (B4) — if you're on `/meetings/category/housing`, the filter bar shows only local issues that appear within Housing items.

Local issues are Richmond-specific (each city gets its own taxonomy via `local-issues.ts`). Categories are the universal grouping; local issues are the city-specific lens on top.

### A5: Sequential View Toggle

For the meeting-attender use case (following along during a live meeting), a toggle switches to sequential item-number order. Default is topic board.

### Key Files

- `web/src/app/meetings/[id]/page.tsx` — meeting detail page
- `web/src/components/MeetingAgendaSection.tsx` — current agenda section
- `web/src/components/AgendaItemCard.tsx` — current item card
- `web/src/components/CategoryBadge.tsx` — existing category badges
- `web/src/lib/local-issues.ts` — local issue taxonomy + `detectLocalIssues()`

---

## Phase B: Calendar View

**Scope:** New component replacing the meetings list as default for `/meetings`.

### B1: Monthly Calendar Grid

- CSS grid, no heavy library (~35 cells)
- ~2 meetings/month so density is appropriate for calendar
- Meeting type encoded with color + shape/label (regular, special, closed session, joint). Color paired with shape/label per accessibility rule A2
- "Today" anchor: opens to current month, upcoming meetings visually distinct from past
- URL encodes month/year for shareable views (`/meetings?month=2024-03`)

### B2: Inline Day Expansion

Click a day with a meeting → inline expansion below the calendar row (not page navigation, per U6). Shows:
- Meeting type + item count
- Hero item teaser (one-line, if applicable)
- Financial connection count (if any items have flags)
- Link to full meeting detail

### B3: List View Toggle

List view available as toggle for users who prefer it. Not the default. Preserves current functionality.

### B4: Category Drill-Through Page (`/meetings/category/[slug]`)

All agenda items in a single category across all meetings. Two entry points:

1. **From meeting detail topic board:** Category section header "Housing (4 items)" links to "See all Housing items >"
2. **From Topics & Trends (`/council/stats`):** Each row in the category stats table links to the category page

Page structure:
- Category name as h1, with total item count
- Summary stats: total items, split votes, date range
- Items sorted newest-first, same significance-based card sizing as meeting detail (split votes prominent, consent items compact)
- Each item card shows meeting date + link to meeting, vote result, financial connection indicator
- Items with influence map connections link to `/influence/item/[id]`

This creates two orthogonal browsing dimensions: **time** (calendar → meeting → items that day) and **topic** (category → items across all time). The meeting detail topic board is the intersection of both.

Reuses the same `AgendaItemCard` component from Phase A — same card, different data slice.

### Key Files

- `web/src/app/meetings/page.tsx` — meetings index page
- `web/src/components/MeetingsPageClient.tsx` — current client component
- `web/src/components/MeetingCard.tsx` — current meeting card

---

## Phase C: Influence Map — Item Center

**Scope:** New page type at `/influence/item/[id]`.

### C1: Sentence-Based Connection Narrative

Each financial connection is a plain-language sentence, not a table row:

```
Council Member Eduardo Martinez voted yes.
His campaign received $4,200 from Acme Development PAC
between 2022-2024.

Strong confidence · NetFile (Tier 1) · Mar 2024
[View filing] [Provide context]

> Evidence details (2 records)
```

### C2: Page Structure

Following T6 (no accusatory framing) and the council profile reference pattern:

1. **Breadcrumb** — Meeting date > Item title
2. **Item identity** — Plain language title, AI-generated summary, SourceBadge
3. **The Decision** — Vote result narrative, category badge
4. **Financial Context (N connections)** — Framing prose ("A connection does not imply wrongdoing..."), then connection cards as sentences. Only connections >= 90% confidence in this section (U13).
5. **Public Speakers (N)** — Speaker list with entity resolution flags (S13 lobbyist/cross-jurisdiction data when available)
6. **Related Decisions (N)** — Other agenda items involving the same entities (vendor, donor, organization)
7. **About This Data** — Methodology box (how connections are identified, thresholds, correction process)

Each official name is a link to their influence map (council profile page).

### C3: Entry Points

- Hero item link from meeting detail
- "N financial connections >" indicator on any agenda item card
- Direct URL (shareable)
- Search results (future)

### Required Queries

- Existing: `getConflictFlagsDetailed()`, meeting/agenda item queries
- New: query to fetch all connections for a single agenda item with vote context, donor details, and Form 700 overlaps
- New: query to find related agenda items by shared entities (vendor name matching, donor overlap)

### Key Files

- New: `web/src/app/influence/item/[id]/page.tsx`
- `web/src/lib/queries.ts` — new query functions
- `web/src/lib/types.ts` — new types

---

## Phase D: Influence Map — Official Center + Index

**Scope:** Restructure existing council profile; new index page replacing `/financial-connections`.

### D1: Council Profile Restructure

The financial connections section of `/council/[slug]` becomes narrative sentences linking to specific agenda item influence maps:

```
On the Acme Development agreement (Mar 5, 2024) >
  Council Member Martinez voted yes. His campaign received
  $4,200 from Acme Development PAC.
  Strong confidence.

On the Chevron refinery permit renewal (Jan 8, 2024) >
  Council Member Martinez voted yes. Chevron Richmond
  contributed $15,000 to the Richmond Progressive Alliance
  PAC, which supported his 2022 campaign.
  Moderate confidence.

> Show 5 more connections
```

Each agenda item title is a link to its influence map page (Phase C).

### D2: Influence Map Index (`/influence`)

Replaces `/financial-connections`. Directory of all officials with connection counts, linking to each official's council profile (which now contains their influence map section).

- Summary stats (total connections, officials with connections, confidence breakdown)
- Per-official cards with: name, role, connection count, top flag types
- Link to each official's profile

### D3: Navigation Restructure

```
CURRENT                     NEW
Money                       Influence
  Financial Connections       Influence Map (index → /influence)
  Donor Patterns              Donor Patterns
  Transparency Reports        (eliminated — absorbed into item influence maps)
```

### Key Files

- `web/src/app/council/[slug]/page.tsx` — profile restructure
- New: `web/src/app/influence/page.tsx` — index
- `web/src/components/Nav.tsx` — nav restructure
- Remove: `web/src/app/reports/[meetingId]/page.tsx` (or redirect to meeting detail)

---

## Phase E: Polish + Cross-Linking

**Scope:** Connect the discovery and depth layers.

### E1: Calendar Integration

- Financial connection indicators in calendar inline expansion
- Hero item teaser in calendar links to influence map

### E2: Bidirectional Navigation

- Every official name in an item influence map links to their profile
- Every agenda item in an official's influence section links to the item influence map
- Related items section cross-links between item influence maps
- Back-navigation breadcrumbs on all influence map pages

---

## Pages Affected

| Current Page | Change |
|---|---|
| `/meetings` | Calendar view as default (Phase B) |
| `/meetings/[id]` | Topic board + hero item (Phase A) |
| `/council/[slug]` | Financial section → narrative influence map (Phase D) |
| `/financial-connections` | Replaced by `/influence` index (Phase D) |
| `/reports/[meetingId]` | **Eliminated.** Content absorbed into item influence maps (Phase C). Redirect to meeting detail. |
| `/influence/item/[id]` | **New.** Agenda item influence map (Phase C) |
| `/influence` | **New.** Index of all officials with connections (Phase D) |
| `/meetings/category/[slug]` | **New.** All items in a category across all meetings (Phase B) |
| `/council/stats` | Category rows become clickable, linking to category pages (Phase B) |

## Data Quality Prerequisites

- **Category coverage:** Verified — all 14 categories assigned during LLM extraction. Backfill migration handles historical data. Topic board is safe to build.
- **Financial connection coverage:** 784 meetings rescanned in S9 with 93.5% false-positive reduction. Connection data is production-quality.
- **Hero item signals:** Split votes and consent calendar status are already in the database. No new extraction needed.

## Design Rules Compliance

| Rule | How This Spec Complies |
|---|---|
| D6/T7 (narrative over numbers) | Connections are sentences, not charts or tables |
| T6 (no accusatory framing) | Identity/context first, then activity, then findings. Framing prose on every connection section |
| U3 (max 3 KPIs) | Summary cards on index page capped at 3 |
| U4 (signal depth) | All collapsed sections include counts |
| U13 (low-confidence exclusion) | Only >= 90% connections in Layer 1 summaries |
| U14 (correction mechanisms) | "Provide context" link on every connection card |
| U1 (source attribution) | SourceBadge on every connection |
| U6 (no interstitials) | Calendar expands inline, data loads immediately |

## Open Questions

1. **Agenda item URL slugs.** `/influence/item/[id]` uses database IDs. Should we generate slugs from titles for readability? (AI-delegable: yes, follow the council profile slug pattern.)
2. **Related items algorithm.** How aggressively should we match? Exact vendor name only, or fuzzy entity resolution from S13? (Start exact, graduate to fuzzy.)
3. **Commission agenda items.** Do commission meetings get influence maps? (Yes, same structure — commission members as the official center. But lower priority since commission voting data is limited.)
4. **Redirect strategy for `/reports/[meetingId]`.** 301 to `/meetings/[id]` or keep as alias temporarily? (301 redirect — clean break.)
