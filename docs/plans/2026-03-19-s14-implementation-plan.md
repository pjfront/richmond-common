# S14 Implementation Plan: Influence Map + Meetings Redesign

**Created:** 2026-03-19
**Spec:** `docs/specs/influence-map-meetings-redesign-spec.md`
**Research synthesis:** `docs/research/s14-research-synthesis.md`

## Architecture Summary

S14 is a **frontend + query engineering sprint**. No new database tables or migrations needed. All data exists: conflict_flags (S9), contributions/donors (S5+), Form 700 (S5), organizations/entity_links (S13), categories (extraction pipeline), votes/motions (core schema).

**Phases A and B** are pure frontend — zero new backend work. Start immediately.
**Phase C** requires 5 new queries (JOINs/aggregations on existing tables).
**Phase D** restructures existing components + adds 1 new page.
**Phase E** is polish and navigation infrastructure.

## Dependencies & Sequencing

```
Phase A (meeting detail) ──────────────────────────┐
  ↓ (AgendaItemCard, CategoryBadge, MeetingTypeBadge) │
Phase B (meeting discovery) ────────────────────────┤
  ↓ (page structure, card components)                  │
Phase C (influence map — item center) ─────────────┤
  ↓ (sentence templates, disclaimer, queries)          │
Phase D (influence map — official center + index) ──┤
  ↓ (nav restructure, profile changes)                 │
Phase E (polish + cross-linking) ──────────────────┘
```

Phases A and B can run in parallel — no dependencies between them. C depends on A (card components). D depends on C (sentence templates, disclaimer system). E depends on C+D.

## Session Plan

### Session 1: Design System Foundation (A6, A7)

**Goal:** Build the two new design system components that propagate everywhere.

**New components:**
- `web/src/components/MeetingTypeBadge.tsx` — 3-channel meeting type encoding (color + shape + text)
  - Props: `meetingType: 'regular' | 'special' | 'closed_session' | 'joint'`
  - Renders: colored badge with shape icon + border accent + text label
  - Colors: Blue/Orange/Purple/Teal (spec A6)

- `web/src/components/EntityTypeIndicator.tsx` — Entity type color/icon system
  - Props: `entityType: 'agenda_item' | 'official' | 'donor' | 'meeting'`
  - Renders: small icon + color accent (Green/Blue/Orange/Gray per spec A7)
  - Used inline with entity names across all influence map pages

**Modify:**
- `web/src/lib/types.ts` — Add `MeetingType` type alias, `EntityType` type

**Tests:** Visual component, minimal logic. Storybook-style spot check.

**Est:** Small session (~1 hour)

---

### Session 2: Meeting Detail Redesign — Topic Board (A1, A2, A5)

**Goal:** Restructure `/meetings/[id]` from sequential list to category-grouped topic board.

**New components:**
- `web/src/components/TopicBoard.tsx` — Main layout: groups items by category, renders sections
  - Input: `AgendaItemWithMotions[]` (existing type, no new queries)
  - Logic: group by `item.category`, sort sections by item count DESC, filter empty categories
  - Renders: CategorySection components

- `web/src/components/CategorySection.tsx` — Single category group
  - Header: category name + item count ("Housing (4 items)") → links to `/meetings/category/{slug}`
  - Children: AgendaItemCard instances with significance-based sizing

- `web/src/components/ConsentCalendarSection.tsx` — Compact consent calendar section
  - One-line per item (title only, no expansion)
  - Separate from TopicBoard sections

- `web/src/components/ProceduralStrip.tsx` — Near-invisible timeline of procedural items
  - Call to order, roll call, adjournment — minimal visual weight

**Modify:**
- `web/src/components/AgendaItemCard.tsx` — Add significance-based sizing
  - New prop: `significance: 'hero' | 'split' | 'pulled' | 'financial' | 'standard' | 'consent' | 'procedural'`
  - Split votes → large card, prominent border
  - Pulled from consent → highlighted background
  - Dollar amounts → visual anchor text
  - Campaign finance records → subtle indicator ("3 contribution records >")
  - Standard → current size
  - Absorbs S12.4: add WHEREAS/RESOLVED detection, paragraph breaks in official text

- `web/src/components/MeetingAgendaSection.tsx` — Replace with TopicBoard (may deprecate)

- `web/src/app/meetings/[id]/page.tsx` — Swap MeetingAgendaSection for TopicBoard + sequential view toggle
  - Add MeetingTypeBadge to header
  - Add sequential view toggle (A5) — state variable, renders flat list when active

**Data:** No new queries. `getMeeting()` already returns all items with category, motions, votes. Grouping and significance detection are client-side.

**Significance detection logic (client-side):**
```typescript
function getSignificance(item: AgendaItemWithMotions, flags: ConflictFlag[]): Significance {
  if (item.motions?.some(m => parseVoteTally(m.vote_tally).nays > 0)) return 'split'
  if (item.was_pulled_from_consent) return 'pulled'
  if (flags.some(f => f.agenda_item_id === item.id)) return 'financial'
  if (item.is_consent_calendar) return 'consent'
  if (isProcedural(item)) return 'procedural'
  return 'standard'
}
```

**Est:** Medium session (~2-3 hours)

---

### Session 3: Hero Item + Local Issue Filter (A3, A4)

**Goal:** Add hero item pattern and local issue filter bar to meeting detail.

**New components:**
- `web/src/components/HeroItem.tsx` — Featured contested item at top of meeting page
  - Input: `AgendaItemWithMotions` (the selected hero) + `ConflictFlag[]`
  - Selection logic: spec A3 criteria (split votes by margin, then pulled-from-consent, then financial flags)
  - Renders: narrative card ("The most contested item: Council voted 4-3 on [title].")
  - Links to influence map when available (Phase C)
  - Returns null if no qualifying item exists

- `web/src/components/LocalIssueFilterBar.tsx` — Row of filter pills above topic board
  - Input: `AgendaItemWithMotions[]`
  - Runs `detectLocalIssues()` on each item title
  - Renders pills with match counts: `[Chevron · 2] [Point Molate · 1]`
  - Click → filters TopicBoard to matching items only
  - Click again → clears filter
  - Single-select (one active filter at a time)
  - Implementation note: use individual Radix Toggle.Root primitives in `role="group"` wrapper (resolved decision #8)
  - `role="status"` live region for filter result announcements (Research F)

**Modify:**
- `web/src/app/meetings/[id]/page.tsx` — Add HeroItem above TopicBoard, LocalIssueFilterBar between them
- Pass filter state from LocalIssueFilterBar down to TopicBoard

**Data:** No new queries. `detectLocalIssues()` already exists. Hero selection is client-side logic.

**Est:** Medium session (~2 hours)

---

### Session 4: Meeting Discovery — Agenda List + Next Meeting (B1, B2, B4)

**Goal:** Redesign `/meetings` index with agenda list primary view.

**New components:**
- `web/src/components/NextMeetingCard.tsx` — Persistent "next meeting" card
  - Input: `Meeting` (first future meeting)
  - Renders: MeetingTypeBadge, date/time, item count, hero item teaser, campaign finance count
  - Link to meeting detail page
  - Only renders if a future meeting exists

- `web/src/components/MeetingAgendaList.tsx` — Month-grouped accordion list (replaces MeetingsPageClient)
  - Input: `Meeting[]` (all meetings)
  - Groups by month, renders collapsible month sections
  - Most recent month expanded by default
  - "Today" anchor scrolls to current month
  - Uses Radix Collapsible for month accordion
  - Each meeting renders as expandable card (B4)

- `web/src/components/MeetingListCard.tsx` — Single meeting in the agenda list
  - Replaces MeetingCard with richer content
  - Shows: date, MeetingTypeBadge, item count, hero item teaser, campaign finance indicator
  - Expandable (Radix Collapsible) → shows B4 inline expansion content
  - Link to full meeting detail

**Modify:**
- `web/src/app/meetings/page.tsx` — Replace current page with NextMeetingCard + MeetingAgendaList
  - URL state: `?month=2024-03` via nuqs for shareable views
  - ISR revalidation preserved

- `web/src/components/MeetingsPageClient.tsx` — Deprecate (replaced by MeetingAgendaList)

**Data:** Existing `getMeetingsWithCounts()` provides everything needed. `getMeetingsWithFlags()` adds campaign finance indicators. Both queries already exist.

**New dependency:** `nuqs` package for URL state sync.

**Est:** Medium-large session (~3 hours)

---

### Session 5: Mini-Calendar + Grid Toggle + Category Drill-Through (B3, B5, B6)

**Goal:** Add mini-calendar navigation and category pages.

**New components:**
- `web/src/components/MiniCalendar.tsx` — Compact month grid navigation
  - CSS Grid (7 columns), custom build with date-fns
  - Meeting dates show dot indicators (MeetingTypeBadge colors)
  - Non-meeting dates dimmed
  - Click meeting date → scrolls agenda list to that meeting
  - Month navigation arrows
  - Desktop: sidebar alongside MeetingAgendaList
  - Mobile: collapsible top strip (responds to breakpoint)

- `web/src/components/CalendarGrid.tsx` — Full monthly grid (toggle view, not default)
  - 7-column CSS Grid with day cells
  - Meeting cells show MeetingTypeBadge + meeting title
  - Click → inline expansion below row
  - Toggle button switches between list and grid view

**New page:**
- `web/src/app/meetings/category/[slug]/page.tsx` — Category drill-through
  - ISR with 1hr revalidation
  - Data: new query `getAgendaItemsByCategory(category, cityFips)`
  - Reuses AgendaItemCard (significance-based sizing)
  - Each card shows meeting date + link
  - LocalIssueFilterBar applies here too (spec A4)

**New query:**
- `getAgendaItemsByCategory(category: string, cityFips: string)` in queries.ts
  - SELECT from agenda_items JOIN meetings
  - WHERE category = $1 AND city_fips = $2
  - ORDER BY meeting_date DESC
  - Include: vote result (via motions), campaign finance indicator (via conflict_flags count)

**Modify:**
- `web/src/app/meetings/page.tsx` — Add MiniCalendar + grid toggle
- `web/src/app/council/stats/page.tsx` — Make category rows clickable → `/meetings/category/{slug}`

**Est:** Medium-large session (~3 hours)

---

### Session 6: Influence Map Queries (C prerequisites)

**Goal:** Build all new queries needed for Phase C before touching frontend.

**New queries in `web/src/lib/queries.ts`:**

1. **`getContributionRecordsForItem(agendaItemId, cityFips)`**
   - All contribution records relevant to officials who voted on this item
   - JOINs: conflict_flags → officials → committees → contributions → donors
   - Returns: official name/slug, vote_choice, donor_name, total_amount, contribution_count, date_range, flag confidence, evidence
   - Filter: is_current = TRUE, confidence >= CONFIDENCE_PUBLISHED

2. **`getContributionAsPercentage(officialId, donorName, cityFips)`**
   - SUM(contributions WHERE official) for total fundraising
   - SUM(contributions WHERE official AND donor matches) for this donor
   - Returns: { donor_total, campaign_total, percentage }

3. **`getOtherMembersVoteSameWay(agendaItemId, officialId, donorName, cityFips)`**
   - For the same agenda item: which other officials voted the same way?
   - Of those, how many received NO contributions from this donor?
   - Returns: { same_vote_count, same_vote_without_contribution_count, official_names }

4. **`getOfficialVotesAgainstDonor(officialId, donorName, cityFips)`**
   - Agenda items where this official received contributions from this donor but voted against the item
   - Returns: { count, items: [{title, date, vote_choice}] }
   - Limited to last 5 years of data

5. **`getRelatedAgendaItems(agendaItemId, cityFips)`**
   - Other agenda items involving the same donors/vendors/organizations
   - Match on donor_name overlap in conflict_flags evidence
   - Returns: [{agenda_item_id, title, meeting_date, shared_entity_name}]

**New types in `web/src/lib/types.ts`:**
```typescript
ContributionRecord {
  official_id: string
  official_name: string
  official_slug: string
  vote_choice: 'aye' | 'nay' | 'abstain' | 'absent' | null
  donor_name: string
  total_amount: number
  contribution_count: number
  date_range: { start: string; end: string }
  percentage_of_fundraising: number
  other_members_same_vote: number
  other_members_same_vote_no_contribution: number
  confidence: number
  evidence: Record<string, unknown>[]
  source: string
  source_tier: number
}

ContributionContext {
  record: ContributionRecord
  counter_examples: { count: number; items: { title: string; date: string }[] }
}
```

**Est:** Medium session (~2-3 hours, mostly query engineering)

---

### Session 7: Influence Map — Item Center Page (C1, C2, C3)

**Goal:** Build `/influence/item/[id]` — the core new page.

**New components:**
- `web/src/components/ContributionRecordCard.tsx` — Single contribution record as narrative sentence
  - Input: `ContributionContext`
  - Renders the spec's sentence template (contribution first, vote second)
  - Includes: % of fundraising, other members' votes, confidence badge, source badge
  - Expandable evidence details (Radix Collapsible, per Research F)
  - "View filing" → `<a href>` to original filing
  - "Provide context" → Radix Dialog trigger (button)
  - Per-connection disclaimer in tooltip (info icon)
  - `<article>` in `<ul>` structure per Research F

- `web/src/components/ContributionRecordList.tsx` — List of contribution record cards
  - Input: `ContributionContext[]`
  - Renders `<ul>` of ContributionRecordCard articles
  - Filter by confidence tier (strong/moderate/low)

- `web/src/components/DisclaimerBox.tsx` — Reusable disclaimer component
  - Input: `variant: 'global' | 'confidence'`
  - Global: "About this data" + "A campaign contribution does not imply wrongdoing" (spec C4)
  - Confidence: "What confidence scores mean" explanation (spec C4)
  - Rendered above contribution records on every influence map page

**New page:**
- `web/src/app/influence/item/[id]/page.tsx`
  - ISR with 1hr revalidation
  - Data: `getContributionRecordsForItem()` + `getMeeting()` + agenda item details
  - Page structure per spec C2:
    1. Navigation bar (back link + canonical breadcrumb)
    2. Item identity (EntityTypeIndicator + title + summary + SourceBadge)
    3. The Decision (vote result narrative + CategoryBadge)
    4. Campaign Finance Context (DisclaimerBox + ContributionRecordList)
    5. Public Speakers (existing speaker data)
    6. Related Decisions (from `getRelatedAgendaItems()`)
    7. About This Data (link to methodology page)

**Modify:**
- `web/src/components/AgendaItemCard.tsx` — Add "N contribution records >" link to influence map page (entry point C3)
- `web/src/components/HeroItem.tsx` — Add "View influence map >" link

**Est:** Large session (~4 hours)

---

### Session 8: Influence Map — Official Center + Index (D1, D2, D3)

**Goal:** Restructure council profile + build influence index + restructure nav.

**New components:**
- `web/src/components/OfficialInfluenceSection.tsx` — Narrative influence section for council profiles
  - Input: `FinancialConnectionFlag[]` (existing type, existing query)
  - Renders contribution-first sentences linking to item influence maps
  - DisclaimerBox (global variant)
  - "Show N more records" progressive disclosure
  - Replaces FinancialConnectionsSummary + FinancialConnectionsTable on profile page

**New page:**
- `web/src/app/influence/page.tsx` — Influence map index
  - Replaces `/financial-connections`
  - Data: `getAllFinancialConnectionSummaries()` (existing query)
  - Summary stats (3 cards max per U3): total records, officials with records, confidence breakdown
  - Per-official cards linking to council profiles
  - DisclaimerBox

**Modify:**
- `web/src/app/council/[slug]/page.tsx` — Replace FinancialConnectionsSummary/Table sections with OfficialInfluenceSection
- `web/src/components/Nav.tsx` — Restructure:
  - "Money" → "Influence"
  - "Financial Connections" → "Influence Map" (→ `/influence`)
  - Remove "Transparency Reports" link
- `web/src/app/financial-connections/page.tsx` — 301 redirect to `/influence`
- `web/src/app/reports/[meetingId]/page.tsx` — 301 redirect to `/meetings/[meetingId]`
- `web/src/app/reports/page.tsx` — 301 redirect to `/meetings`

**Est:** Large session (~3-4 hours)

---

### Session 9: Polish + Cross-Linking (E1–E5)

**Goal:** Wire everything together. Navigation infrastructure.

**New components:**
- `web/src/components/RecentlyVisited.tsx` — Last 5-8 visited entities
  - Client-side state (localStorage or React context)
  - Desktop: sidebar panel
  - Mobile: expandable icon
  - EntityTypeIndicator on each entry
  - Click → navigate to entity page

- `web/src/components/CanonicalBreadcrumb.tsx` — Fixed-hierarchy breadcrumb
  - Input: entity path segments
  - Always shows canonical location regardless of how user arrived
  - Paired with contextual back link ("← Back to [Previous]")

**New page:**
- `web/src/app/influence/methodology/page.tsx` — Methodology page (spec C5)
  - Static content: data sources, matching algorithms, confidence scores, corrections
  - Linked from every influence map page footer

**Modify:**
- `web/src/app/influence/item/[id]/page.tsx` — Add RecentlyVisited sidebar, CanonicalBreadcrumb
- `web/src/app/council/[slug]/page.tsx` — Add RecentlyVisited sidebar, CanonicalBreadcrumb on influence section
- `web/src/app/influence/page.tsx` — Add RecentlyVisited sidebar
- `web/src/components/MeetingListCard.tsx` — Add campaign finance indicators in inline expansion (E1)
- All entity name links: add EntityTypeIndicator + rich link labels (name + type + key fact) for information scent

**Est:** Medium-large session (~3 hours)

---

### Session 10: S12.3 Summary Regeneration (standalone)

**Goal:** Complete the only remaining S12 work item.

**Tasks:**
- Run regeneration of all summaries with new 13-rule prompt (~$40-60 Batch API)
- Add `textstat` readability validation to pipeline
- Verify readability scores meet plain language standards (S12.1 research)

**This session is independent of S14 phases and can run anytime.** The improved summaries will be used as input for S14's narrative sentences.

**Est:** Small session (~1-2 hours + Batch API wait time)

---

## New Files Summary

| File | Phase | Type |
|---|---|---|
| `web/src/components/MeetingTypeBadge.tsx` | A6 | Design system |
| `web/src/components/EntityTypeIndicator.tsx` | A7 | Design system |
| `web/src/components/TopicBoard.tsx` | A1 | Layout |
| `web/src/components/CategorySection.tsx` | A1 | Layout |
| `web/src/components/ConsentCalendarSection.tsx` | A1 | Layout |
| `web/src/components/ProceduralStrip.tsx` | A1 | Layout |
| `web/src/components/HeroItem.tsx` | A3 | Feature |
| `web/src/components/LocalIssueFilterBar.tsx` | A4 | Feature |
| `web/src/components/NextMeetingCard.tsx` | B1 | Feature |
| `web/src/components/MeetingAgendaList.tsx` | B2 | Layout |
| `web/src/components/MeetingListCard.tsx` | B2 | Card |
| `web/src/components/MiniCalendar.tsx` | B3 | Navigation |
| `web/src/components/CalendarGrid.tsx` | B5 | Navigation |
| `web/src/app/meetings/category/[slug]/page.tsx` | B6 | Page |
| `web/src/components/ContributionRecordCard.tsx` | C1 | Feature |
| `web/src/components/ContributionRecordList.tsx` | C1 | Layout |
| `web/src/components/DisclaimerBox.tsx` | C4 | Design system |
| `web/src/app/influence/item/[id]/page.tsx` | C | Page |
| `web/src/components/OfficialInfluenceSection.tsx` | D1 | Feature |
| `web/src/app/influence/page.tsx` | D2 | Page |
| `web/src/components/RecentlyVisited.tsx` | E3 | Navigation |
| `web/src/components/CanonicalBreadcrumb.tsx` | E | Navigation |
| `web/src/app/influence/methodology/page.tsx` | E5 | Page |

## Modified Files Summary

| File | Sessions | Changes |
|---|---|---|
| `web/src/lib/queries.ts` | 5, 6 | +6 new queries |
| `web/src/lib/types.ts` | 1, 6 | +MeetingType, EntityType, ContributionRecord, ContributionContext |
| `web/src/app/meetings/[id]/page.tsx` | 2, 3 | TopicBoard, HeroItem, LocalIssueFilterBar, MeetingTypeBadge |
| `web/src/app/meetings/page.tsx` | 4, 5 | NextMeetingCard, MeetingAgendaList, MiniCalendar, nuqs |
| `web/src/components/AgendaItemCard.tsx` | 2, 7 | Significance sizing, contribution record link, S12.4 text formatting |
| `web/src/app/council/[slug]/page.tsx` | 8, 9 | OfficialInfluenceSection, RecentlyVisited, breadcrumbs |
| `web/src/components/Nav.tsx` | 8 | Money → Influence, remove Transparency Reports |
| `web/src/app/council/stats/page.tsx` | 5 | Clickable category rows |
| `web/src/app/financial-connections/page.tsx` | 8 | 301 redirect |
| `web/src/app/reports/page.tsx` | 8 | 301 redirect |
| `web/src/app/reports/[meetingId]/page.tsx` | 8 | 301 redirect |

## Deprecated/Removed

| File | Reason |
|---|---|
| `web/src/components/MeetingsPageClient.tsx` | Replaced by MeetingAgendaList |
| `web/src/components/FinancialConnectionsSummary.tsx` | Replaced by OfficialInfluenceSection |
| `web/src/components/FinancialConnectionsTable.tsx` | Replaced by ContributionRecordList |
| `web/src/components/FinancialConnectionsAllTable.tsx` | Replaced by influence index page |

## New Dependencies

| Package | Purpose | Size |
|---|---|---|
| `nuqs` | URL state sync for calendar month navigation | ~6KB |
| `date-fns` | Date math for mini-calendar | ~6KB (tree-shaken) |

Check if date-fns is already installed before adding.

## Risk Factors

1. **Query performance** — The contextual data queries (% of fundraising, counter-examples) involve multi-table JOINs. May need PostgreSQL RPC functions if PostgREST performance is insufficient. Monitor query times during Session 6.
2. **Component count** — 23 new components is significant. Maintain design system discipline — each component should be self-contained with clear props interfaces.
3. **S12.3 dependency** — The improved summaries feed into S14's narrative sentences. Session 10 (regeneration) can run anytime but should complete before S14 goes to operator review.

## Parallel Session Opportunities

Sessions that can run simultaneously in separate worktrees:

- **Sessions 2+4** (meeting detail + meeting discovery) — independent pages
- **Sessions 3+5** (hero/filter + calendar/categories) — independent features
- **Session 6** (queries) can overlap with any frontend session
- **Session 10** (S12.3 regeneration) is fully independent
