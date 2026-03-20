# Influence Map + Meetings Redesign

**Sprint:** 14 (Discovery & Depth)
**Paths:** A, B, C
**Publication tier:** Graduated (all phases operator-only until validated)
**Depends on:** S9 (conflict scanner v3, complete), S11 (information design, complete), S13 (influence transparency, complete)
**Research:** 6 sessions completed (A–F). Synthesis at `docs/research/s14-research-synthesis.md`. Full research at `docs/research/{civic-design-precedents,calendar-ui-patterns,financial-disclosure-framing,entity-navigation-patterns,local-issue-taxonomy-scaling,accessibility-civic-data}.md`

## Problem

Richmond Common's data surfaces are fragmented. Financial connections, voting records, campaign contributions, Form 700 disclosures, and conflict flags each live on separate pages with separate mental models. A citizen who wants to understand "what's really going on with this vote" has to visit 3-4 pages and mentally stitch relationships together.

The meetings page compounds this: agenda items are listed sequentially by item number, giving equal visual weight to a $2.4M development deal (split 4-3) and a proclamation declaring Arbor Day. There's no visual signal for which items are worth exploring deeper.

## Solution

Two integrated workstreams that form a single user journey:

1. **Discovery layer** (meetings redesign): Calendar navigation, topic-board grouping, significance-based card sizing, hero item pattern
2. **Depth layer** (influence map): Sentence-based narrative pages centered on agenda items or officials, replacing the transparency report and financial connections pages

### Design Principles

- **Sentences, not tables.** Every connection is expressed as a plain-language sentence that carries its own context even when screenshotted or shared out of context. Research confirms ~47% comprehension improvement for non-expert audiences with narrative vs. raw data display. (Extends D6/T7.)
- **Contribution first, vote second.** Sentences lead with the campaign finance record, then the vote — never the reverse. Leading with "voted yes → received $X" structurally implies causation. Leading with "contributed $X → voted yes" presents the factual record. (Research C: defamation by implication risk.)
- **Meeting is navigation, not center.** Meetings are containers; the explosive agenda item is the subject. Meetings are launchpads, not destinations.
- **Two centers.** Agenda Item and Official. Same data, different topology. Each links to the other. Navigation between centers is invisible — just a hyperlink click, not an explicit "pivot" operation. (Research D: non-technical users succeed with links, fail with explicit pivot operations.)
- **Objective hero selection.** Hero items are selected by measurable signals (split votes, pulled-from-consent, campaign finance records), not editorial judgment. This is AI-delegable.
- **Context, not correlation.** Every campaign finance record shown alongside a vote must include contextual data: contribution as % of total fundraising, whether other members voted the same way without contributions, and whether the official voted against this contributor on other occasions. Showing a donation next to a vote without context is the single most criticized pattern in civic transparency. (Research A: MapLight criticism; Research C: cognitive bias amplification.)

### Terminology

**Use:** "campaign contribution record," "campaign finance relationship," "campaign finance context"
**Never use:** "financial connection," "financial ties," "funded by," "bankrolled," "backed by," "paid for"

The word "connection" implies relationships beyond documented campaign contributions. "Contribution record" is precise and legally defensible. This applies to all UI copy, section headings, indicator text, and code comments throughout the project.

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
| Campaign finance records present | Subtle indicator: "3 contribution records >" |
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
3. Items with campaign finance records flagged
4. If no signals: no hero item rendered (not every meeting is dramatic)

### A4: Local Issue Filter Bar

A row of local issue pills above the topic board. Only shows issues with at least one match in the current view (no dead buttons). Each pill shows match count.

```
[Chevron · 2] [Point Molate · 1] [Rent Board · 3] [Housing · 4]
```

Click a pill → categories without matching items collapse, remaining categories show only matching items. Click again to clear. Multiple selection not needed (one filter at a time keeps it simple).

Implementation: `detectLocalIssues()` already runs client-side on each item title. Filter is just a state variable on the topic board component. No new queries needed.

Also applies to the category drill-through page (B6) — if you're on `/meetings/category/housing`, the filter bar shows only local issues that appear within Housing items.

Local issues are Richmond-specific (each city gets its own taxonomy via `local-issues.ts`). Categories are the universal grouping; local issues are the city-specific lens on top.

### A5: Sequential View Toggle

For the meeting-attender use case (following along during a live meeting), a toggle switches to sequential item-number order. Default is topic board.

### A6: Meeting Type Encoding (3-Channel Accessible)

Meeting type badges use color + shape + text for triple redundancy (Research B, F). Blue/orange is the most universally distinguishable pair across color vision deficiencies.

| Type | Color | Shape | Border | Badge text |
|---|---|---|---|---|
| Regular | Blue (#0066CC) | ● Circle | Solid left accent | "Regular" |
| Special | Orange (#CC6600) | ★ Star | Dashed left accent | "Special" |
| Closed Session | Purple (#663399) | ■ Square / 🔒 | Dotted left accent | "Closed" |
| Joint Meeting | Teal (#008080) | ◆ Diamond | Double left accent | "Joint" |

Used on meeting cards (Phase A), calendar items (Phase B), and meeting headers. Becomes a design system component alongside CivicTerm/SourceBadge.

### A7: Entity Type Visual Differentiation

Distinct colors and icons per entity type reduce disorientation during cross-entity navigation (Research D). Design as a system component used across all influence map pages.

| Entity type | Color | Icon | Used on |
|---|---|---|---|
| Agenda item | Green | Document | Item influence maps, item cards |
| Official | Blue | Person | Council profiles, official mentions |
| Donor/Organization | Orange | Building/dollar | Contribution records, entity mentions |
| Meeting | Gray | Calendar | Meeting cards, calendar entries |

### Key Files

- `web/src/app/meetings/[id]/page.tsx` — meeting detail page
- `web/src/components/MeetingAgendaSection.tsx` — current agenda section
- `web/src/components/AgendaItemCard.tsx` — current item card
- `web/src/components/CategoryBadge.tsx` — existing category badges
- `web/src/lib/local-issues.ts` — local issue taxonomy + `detectLocalIssues()`

---

## Phase B: Meeting Discovery

**Scope:** Redesign `/meetings` index. Research B found grid calendars underperform list views when density drops below ~1 event/week — at 2 meetings/month, 95% of grid cells are empty. TheyWorkForYou, Councilmatic, and court docket systems all use lists. Invert the default.

### B1: Next Meeting Card

Persistent card above all other content answering the dominant user question: "When is the next meeting?"

- Meeting type badge (A6 encoding), date, time, location
- Agenda item count + hero item teaser (if available)
- Campaign finance record count (if any items have flags)
- Link to full meeting detail
- Only shows when a future meeting exists in the database

### B2: Grouped Agenda List (Primary View)

Month-grouped, accordion-expandable list of meetings. Default view.

- Grouped by month (accordion-expandable, most recent first)
- Each meeting card: date, type badge (A6), item count, hero item teaser
- Meetings with campaign finance records show a subtle indicator
- "Today" anchor: scrolls to current month, upcoming meetings visually distinct from past
- URL encodes month/year for shareable views (`/meetings?month=2024-03`)
- Dates without meetings don't render (no empty state — list is always dense)

### B3: Mini-Calendar Navigation (Secondary)

Compact month grid as a navigation aid, not the primary content display.

- Desktop: sidebar alongside the agenda list
- Mobile: collapsible top strip
- CSS grid, no heavy library (~35 cells) — custom build with date-fns (~6KB)
- Meeting dates show dot indicators (A6 color encoding). Non-meeting dates dimmed/non-interactive.
- Click a date with a meeting → scrolls the agenda list to that meeting
- Month navigation with `nuqs` URL state sync (`/meetings?month=2024-03`)

### B4: Inline Meeting Expansion

Click a meeting in the agenda list → inline expansion below the card (not page navigation, per U6). Shows:
- Meeting type + item count
- Hero item teaser (one-line, if applicable)
- Campaign finance record count (if any items have flags)
- Link to full meeting detail

### B5: Calendar Grid Toggle

Full monthly grid available as toggle for users who prefer it. Not the default. Uses A6 meeting type encoding with 3-channel accessibility.

### B6: Category Drill-Through Page (`/meetings/category/[slug]`)

All agenda items in a single category across all meetings. Two entry points:

1. **From meeting detail topic board:** Category section header "Housing (4 items)" links to "See all Housing items >"
2. **From Topics & Trends (`/council/stats`):** Each row in the category stats table links to the category page

Page structure:
- Category name as h1, with total item count
- Summary stats: total items, split votes, date range
- Items sorted newest-first, same significance-based card sizing as meeting detail (split votes prominent, consent items compact)
- Each item card shows meeting date + link to meeting, vote result, campaign finance indicator
- Items with influence map data link to `/influence/item/[id]`

This creates two orthogonal browsing dimensions: **time** (calendar → meeting → items that day) and **topic** (category → items across all time). The meeting detail topic board is the intersection of both.

Reuses the same `AgendaItemCard` component from Phase A — same card, different data slice.

### Key Files

- `web/src/app/meetings/page.tsx` — meetings index page
- `web/src/components/MeetingsPageClient.tsx` — current client component
- `web/src/components/MeetingCard.tsx` — current meeting card

---

## Phase C: Influence Map — Item Center

**Scope:** New page type at `/influence/item/[id]`.

### C1: Sentence-Based Contribution Narrative

Each campaign contribution record is a plain-language sentence. **Lead with the contribution, then the vote** (see Design Principles: contribution first, vote second).

```
According to NetFile filings, Acme Development PAC made
3 contributions totaling $4,200 to the Martinez campaign
committee between 2022-2024 (2.1% of total fundraising).
Council Member Martinez voted yes on this item.
4 other council members also voted yes.

Strong confidence · NetFile (Tier 1) · Mar 2024
[View filing] [Provide context]

> Evidence details (2 records)
```

**Required contextual data per connection** (Research A, C — MapLight criticism):
- Contribution as percentage of official's total campaign fundraising
- Whether other council members who received no contributions from this source voted the same way
- Whether the official voted against this contributor's apparent interest on other occasions (when data exists)
- Total number of contributions to this official from all sources during the same period

Omitting this context is not acceptable — it is the single most criticized pattern in civic transparency tools.

#### Behested Payment Narrative (S13.1)

Behested payments use a distinct sentence template because the financial relationship is structurally different — the money flows from a payor to a third-party payee at the official's request, not to the official's campaign. **Lead with the request relationship, then the vote.**

```
According to FPPC Form 803 filings, Council Member Martinez
requested that Chevron Corporation make a $50,000 payment to
the Richmond Promise scholarship fund on January 15, 2026.
Chevron Corporation also contributed $15,000 to Martinez's
campaign committee (see above).
Council Member Martinez voted yes on this item.

Strong confidence · FPPC Form 803 (Tier 1) · Jan 2026
[View filing]
```

**Required contextual data per behested payment connection:**
- Whether the payor is also a campaign contributor to this official (cross-reference)
- Whether the payor has matters pending before the council (agenda item match)
- Whether the payee organization has a relationship to the agenda item
- Total behested payment amount from this payor to all payees at this official's request

### C2: Page Structure

Following T6 (no accusatory framing) and the council profile reference pattern:

1. **Navigation bar** — Contextual back link ("← Back to [Meeting Date]") + canonical breadcrumb (`Home > Meetings > Jan 15 Meeting > Budget Amendment`). Research D: traditional path-based breadcrumbs break for graph-like traversal; canonical breadcrumbs show fixed location regardless of how the user arrived.
2. **Item identity** — Entity type indicator (green/document icon), plain language title, AI-generated summary, SourceBadge
3. **The Decision** — Vote result narrative, category badge
4. **Campaign Finance Context (N records)** — Disclaimer prose (see C4 below), then contribution record cards as sentences. Only records >= 90% confidence in this section (U13).
5. **Behested Payment Context (N records)** — Separate section with its own disclaimer (see C4 below). Behested payments are structurally different from campaign contributions (third-party payment at official's request vs. direct campaign donation) and must not be conflated. Only shown when behested payment signals exist for this item's entities.
6. **Public Speakers (N)** — Speaker list with entity resolution flags (S13 lobbyist/cross-jurisdiction data when available)
7. **Related Decisions (N)** — Other agenda items involving the same entities (vendor, donor, organization)
8. **About This Data** — Link to methodology page (see C5)

Each official name is a link to their council profile (entity type indicator: blue/person icon).

### C3: Entry Points

- Hero item link from meeting detail
- "N contribution records >" indicator on any agenda item card
- Direct URL (shareable)
- Search results (future)

### C4: Disclaimer System

Multi-level disclaimer placement (Research C). Not optional.

**Global disclaimer (above section 4 on every item influence map page):**

> **About this data**: Richmond Common presents campaign finance information compiled from official public records filed with NetFile (City of Richmond), CAL-ACCESS (California Secretary of State), and the FPPC. All source data is public under California Government Code §81008.
>
> **A campaign contribution does not imply wrongdoing.** Showing that a contributor gave to a council member's campaign alongside that member's voting record identifies a publicly documented financial relationship — it does not suggest the contribution caused or influenced the vote. Campaign contributions are one of many factors in legislative decisions.

**Per-connection disclaimer (tooltip/expandable on each connection card):**

> This information comes from public campaign finance filings. A contribution to a campaign does not imply that the contributor influenced the officeholder's decisions. [View original filing →]

**Behested payment global disclaimer (above section 5 on every item influence map page):**

> **About behested payments**: A behested payment is a payment made to a third party (usually a nonprofit or community organization) at the request of an elected official. California law (Government Code §82015) requires officials to disclose these requests when the total reaches $5,000 or more.
>
> **A behested payment disclosure does not imply wrongdoing.** It documents that an official directed funds toward a specific cause or organization. The official does not personally receive the payment. Behested payments are one of many ways elected officials support community organizations and programs.

**Per-connection behested payment disclaimer (tooltip/expandable on each behested payment card):**

> This information comes from FPPC Form 803 filings, which are official public records. A behested payment means the official requested that someone make a payment to a third party. It does not mean the official received money or that the payment influenced any government decision. [View original filing →]

**Confidence score explanation (once per page, linked from every confidence badge):**

> **What confidence scores mean**: Our confidence score reflects how certain we are that we have correctly matched public records to the right person or entity. A score of 90%+ means the match is highly reliable based on name, address, and ID number matching. The score does *not* measure the likelihood that a contribution influenced a decision.

### C5: Methodology Page (`/influence/methodology`)

Linked from every influence map page. Covers:
- Data sources (NetFile, CAL-ACCESS, FPPC) with freshness timestamps
- Entity matching algorithm and confidence score calculation
- Known limitations and data gaps
- Correction process (how to report errors)
- Source credibility tier system explanation

#### Behested Payments Section (S13.1)

The methodology page must include a dedicated section explaining behested payments:

**What they are (plain language, ~grade 6):**
> When an elected official asks a company or person to donate money to a specific cause or organization, California law requires them to report it. These are called "behested payments." The money goes to the organization, not to the official. Officials file Form 803 with the state's Fair Political Practices Commission (FPPC) to disclose these requests.

**Why we show them:**
> Behested payments reveal a different kind of relationship than campaign contributions. They show which organizations and causes officials actively direct resources toward, and which companies and individuals respond to those requests. This is public information that helps citizens understand the full picture of how money flows around government decisions.

**Data source and known gaps:**
> - Source: FPPC bulk data download (Tier 1, official government filings)
> - Coverage: State-level officials (Assembly, Senate, Governor). Local officials (Mayor, City Council) may file through separate systems not yet captured in our data.
> - Threshold: Only payments of $5,000+ per year are required to be disclosed
> - Absence of a filing does not confirm absence of behesting. Officials may request payments below the disclosure threshold or through channels we don't monitor.

#### Known Data Gaps Section

The methodology page must include a consolidated "Known Data Gaps" section. Current gaps:

1. **Local Form 803 filings**: FPPC bulk data covers state-level officials only. Local officials may file separately through a system not yet integrated.
2. **Lobbyist registry**: Richmond requires lobbyist registration under Municipal Code Chapter 2.54, but filings are paper/PDF only (Document Center folder FID=389). No machine-readable format or searchable database exists. Richmond Common cannot programmatically verify registration status.
3. **Charitable giving disclosure**: Companies without an associated nonprofit overseeing their giving are not required to disclose charitable donations. This creates a gap where significant community investment may exist without public disclosure.

### Required Queries

- Existing: `getConflictFlagsDetailed()`, meeting/agenda item queries
- New: query to fetch all contribution records for a single agenda item with vote context, donor details, and Form 700 overlaps
- New: query to find related agenda items by shared entities (vendor name matching, donor overlap)
- New: **contextual data queries** — per-official total fundraising (for % calculation), vote alignment across meetings with same contributor, other members' votes on same item without contributions from this source
- New: query to fetch behested payment records for entities appearing in an agenda item (payor/payee name matching against item text), with cross-reference to campaign contributions from the same payor

### Key Files

- New: `web/src/app/influence/item/[id]/page.tsx`
- `web/src/lib/queries.ts` — new query functions
- `web/src/lib/types.ts` — new types

---

## Phase D: Influence Map — Official Center + Index

**Scope:** Restructure existing council profile; new index page replacing `/financial-connections`.

### D1: Council Profile Restructure

The campaign finance section of `/council/[slug]` becomes narrative sentences linking to specific agenda item influence maps. Same "contribution first, vote second" framing as Phase C:

```
On the Acme Development agreement (Mar 5, 2024) >
  According to NetFile filings, Acme Development PAC
  contributed $4,200 to Martinez's campaign committee.
  Council Member Martinez voted yes on this item.
  Strong confidence.

On the Chevron refinery permit renewal (Jan 8, 2024) >
  Chevron Richmond contributed $15,000 to the Richmond
  Progressive Alliance PAC, which supported Martinez's
  2022 campaign. Council Member Martinez voted yes.
  Moderate confidence.

> Show 5 more records
```

Each agenda item title is a link to its influence map page (Phase C). Same disclaimer system as C4 applies here.

### D2: Influence Map Index (`/influence`)

Replaces `/financial-connections`. Directory of all officials with campaign finance record counts, linking to each official's council profile (which now contains their influence map section).

- Summary stats (total records, officials with records, confidence breakdown)
- Per-official cards with: name, role, record count, top flag types
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

**Scope:** Connect the discovery and depth layers. Implement the composite navigation strategy from Research D.

### E1: Meeting Discovery Integration

- Campaign finance record indicators in meeting list inline expansion
- Hero item teaser in meeting cards links to influence map

### E2: Bidirectional Navigation

- Every official name in an item influence map links to their profile (blue/person entity indicator)
- Every agenda item in an official's influence section links to the item influence map (green/document entity indicator)
- Related items section cross-links between item influence maps
- Entity type visual differentiation (A7) applied consistently across all cross-links
- Navigation between centers is invisible — just hyperlink clicks with rich link labels (name + type + key fact) to maintain information scent (Research D: information foraging theory)

### E3: Recently Visited Panel

Compact navigation aid showing the last 5–8 visited entities with type icons (A7 colors). Research D: users can hold only 3–5 context chunks; externalizing navigation history through a visible panel prevents disorientation.

- Desktop: sidebar panel
- Mobile: expandable history icon
- Non-sequential backtracking (jump back 3 entities without hitting "back" 3 times)

### E4: Persistent Search Bar

Universal escape hatch across all influence map pages. Research D: 43% of users go to search first when disoriented.

### E5: Methodology Page

Implement `/influence/methodology` (spec'd in C5). Link from every influence map page footer.

---

## Pages Affected

| Current Page | Change |
|---|---|
| `/meetings` | Agenda list as default + mini-calendar navigation (Phase B) |
| `/meetings/[id]` | Topic board + hero item + meeting type encoding (Phase A) |
| `/council/[slug]` | Campaign finance section → narrative influence map (Phase D) |
| `/financial-connections` | Replaced by `/influence` index (Phase D) |
| `/reports/[meetingId]` | **Eliminated.** Content absorbed into item influence maps (Phase C). 301 redirect to meeting detail. |
| `/influence/item/[id]` | **New.** Agenda item influence map (Phase C) |
| `/influence` | **New.** Index of all officials with campaign finance records (Phase D) |
| `/influence/methodology` | **New.** Data sources, matching algorithms, confidence scores, corrections (Phase C/E) |
| `/meetings/category/[slug]` | **New.** All items in a category across all meetings (Phase B) |
| `/council/stats` | Category rows become clickable, linking to category pages (Phase B) |

## Data Quality Prerequisites

- **Category coverage:** Verified — all 14 categories assigned during LLM extraction. Backfill migration handles historical data. Topic board is safe to build.
- **Campaign finance record coverage:** 784 meetings rescanned in S9 with 93.5% false-positive reduction. Record data is production-quality.
- **Hero item signals:** Split votes and consent calendar status are already in the database. No new extraction needed.

## Design Rules Compliance

| Rule | How This Spec Complies |
|---|---|
| D3 (shadcn/ui + Radix) | Collapsible for card expand, ToggleGroup for filter pills, Dialog for "Provide context" (Research F) |
| D6/T7 (narrative over numbers) | Records are sentences, not charts or tables. Research validates ~47% comprehension improvement. |
| T6 (no accusatory framing) | Contribution first, vote second. Multi-level disclaimer system. Contextual data per record. |
| U3 (max 3 KPIs) | Summary cards on index page capped at 3 |
| U4 (signal depth) | All collapsed sections include counts |
| U13 (low-confidence exclusion) | Only >= 90% records in Layer 1 summaries |
| U14 (correction mechanisms) | "Provide context" link on every contribution record card |
| U1 (source attribution) | SourceBadge on every record + source links to original filings |
| U6 (no interstitials) | Meeting list expands inline, data loads immediately |
| A2 (color + non-color) | Meeting type 3-channel encoding (A6). Entity type visual system (A7). Badge triple redundancy (Research F). |
| WCAG 2.1 AA | California ADA Title II deadline April 2026. `<article>` in `<ul>` card structure, Collapsible disclosure, `aria-pressed` toggle pills, `role="status"` for filter announcements (Research F). |

## Resolved Questions

1. **Agenda item URL slugs.** Yes, generate slugs from titles — follow the council profile slug pattern. (AI-delegable.)
2. **Related items algorithm.** Start exact, graduate to fuzzy. (AI-delegable.)
3. **Commission agenda items.** Yes, same structure — commission members as the official center. Lower priority since commission voting data is limited. (AI-delegable.)
4. **Redirect strategy for `/reports/[meetingId]`.** 301 redirect to `/meetings/[id]`. Clean break. (AI-delegable.)
5. **Calendar default.** Agenda list primary, grid secondary. Research B unanimous. (AI-delegable.)
6. **Breadcrumb strategy.** Canonical location breadcrumb + contextual back link. No path-based breadcrumbs. (Research D.) (AI-delegable.)
7. **Navigation depth.** Unlimited. Invest in wayfinding (information scent, recently visited panel) rather than capping hops. 3-click rule is debunked. (Research D.) (AI-delegable.)

## Open Questions (Judgment Calls)

_None remaining. All resolved — see below._

## Resolved Design Decisions (from Research)

_Judgment calls resolved during research synthesis (2026-03-19):_

8. **Filter pill implementation.** Use individual Radix Toggle.Root primitives in a custom `role="group"` wrapper with single-select state management — not ToggleGroup. ToggleGroup has a known ARIA role violation in `type="single"` mode (GitHub #3188) and its radio semantics don't support click-to-deselect. Individual Toggles use `aria-pressed` natively (the correct semantic) and avoid fighting Radix's internal role assignments. ~15 lines of state management, more correct, more durable against Radix updates.
9. **Comparative framing.** Yes, but deferred to Phase E. Per-record: keep "% of total fundraising" in the sentence template (already spec'd in C1) + add percentile rank as secondary indicator ("This is more than 95% of individual contributions to this campaign"). Per-official (Phase D profile page): add cross-member comparative context ("received more from real estate interests than 6 of 7 council members"). The "3.2× average" framing applies at the profile level, not the individual record level.
10. **Confidence badge colors.** Keep current green/yellow/red palette. Text labels ("Strong," "Moderate," "Low") already satisfy WCAG 1.4.1. Palette redesign would be churn for a solved problem. Icon differentiation (checkmark/warning/X) is optional future polish, not a blocker.
