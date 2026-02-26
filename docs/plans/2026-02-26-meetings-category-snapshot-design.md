# Design: Meetings Page Category Snapshot

**Date:** 2026-02-26
**Sprint:** S2 (Vote Intelligence)
**Status:** Approved
**Origin:** Category breakdown on council profiles shows citywide agenda composition, not individual behavior. Moving it to the meetings page where it semantically belongs, with date filtering and procedural item handling.

---

## Decisions Made

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Location | Meetings page, not council profiles | Categories describe what the council discusses, not what an individual member chooses. Every member votes on the same agenda. |
| Visualization | Horizontal bars (adapt existing `CategoryBreakdown`) | Easiest chart type for humans to compare accurately (Cleveland & McGill, 1984). Already built, scales to any number of categories. |
| Date filtering | Date range picker with quick-select shortcuts | Backfilling historical records makes arbitrary presets insufficient. Picker handles specific windows; shortcuts (`This year`, `Last year`, `All time`) cover the lazy-click case. |
| Filtering mode | Snapshot (point-in-time), not trend | Answers "what did the council focus on in this period?" No time-series charts needed. |
| Page layout | Category snapshot above meeting list | Top-down information hierarchy: summary first, details second. Single-column layout preserved. |
| Procedural items | Hidden by default, inline text toggle | Procedural items (roll call, pledge, minutes approval) are noise that dilutes signal. Toggle is discoverable but not competing for attention. |
| Procedural category name | `procedural` | Standard parliamentary procedure term. Immediately signals "process, not substance." |
| Ceremonial items | Remain `other` | Don't over-engineer categories. The system distinguishes substantive policy areas from each other. Everything non-substantive and non-procedural is `other`. |
| Profile replacement | Remove now, replace later (separate design) | Personal voting summary (dissent patterns, majority alignment) is the right replacement but needs its own design work. |

---

## Implementation 1: Meetings Page Category Snapshot

### Page Flow (top to bottom)

1. **Page header** ("City Council Meetings")
2. **Date filter bar** -- Date range picker (start/end) with quick-select shortcuts: `This year`, `Last year`, `All time`. Default: current year.
3. **Topic Overview** -- Horizontal bar chart showing aggregate category distribution across all meetings in the selected date range. Ranked by frequency. Below the bars: procedural toggle.
4. **Meeting cards** -- Existing `MeetingCard` list, filtered to the same date range. Grouped by year.

### Key Behaviors

- Date filter controls both the category snapshot AND the meeting list. One filter, two views.
- Procedural items excluded from category bars by default.
- Client-side filtering (dataset is small: ~24 meetings/year even with backfill).
- Empty state when no meetings match the date range.

### Procedural Category

**Items classified as procedural:**
- Roll call
- Pledge of Allegiance
- Minutes approval
- Agenda approval / reordering
- Adjournment
- Recess

**NOT procedural:**
- Proclamations, commendations, ceremonial items (remain `other`)
- Consent calendar items (keep their substantive categories)

**Implementation:**
- Add `procedural` to backend `AgendaCategory` enum and frontend `CategoryBadge` color map
- Update extraction prompt to classify these items going forward
- One-time backfill query for existing items matching procedural patterns

**Toggle UX:**

Default state:
> **14 substantive items** . 5 procedural hidden . [show]

Toggled on:
> **19 total items** . [hide procedural]

Inline text link. No checkbox, no switch, no panel.

### Data Flow

- `getMeetingsWithCounts()` already fetches all meetings with category data
- Date filtering and procedural exclusion happen client-side
- `CategoryBreakdown` component adapted to accept aggregated cross-meeting data instead of per-official data

### Council Profile Changes

- Remove `CategoryBreakdown` render from `/council/[slug]` page
- Keep the component file (reused for meetings page)
- Keep `getOfficialCategoryBreakdown()` query (useful for future personal voting summary)

**Profile retains:** Stats bar, bio layers, transparency flags, top donors, voting record table (which has its own category filter).

---

## Implementation 2: Personal Voting Summary (Separate Design, Same Sprint)

Scoped as a follow-up design within S2, sequenced after Implementation 1 ships.

**Concept:** Replace the removed category breakdown on council profiles with genuinely individual metrics:

| Metric | What it tells a citizen |
|--------|------------------------|
| Majority alignment rate | "Votes with the majority X% of the time" |
| Dissenting vote count | How often they're in the minority |
| Most frequent dissent categories | What topics they break from the group on |

**Why separate:** Requires careful thought on what "dissenting" means, how unanimous votes affect alignment rate, and what thresholds are meaningful. This is a design problem, not just an implementation task.

**Parking lot reference:** This is the interesting individual data the profile should show. "Councilmember X votes with the majority 91% of the time, but dissents most often on housing and budget items."

---

## Publication Tiers

| Feature | Tier | Reasoning |
|---------|------|-----------|
| Date-filtered meeting list | Public | Factual, no inference, extends existing public page |
| Category snapshot visualization | Graduated | New visualization, aggregation logic should be validated |
| Procedural filtering | Public | Data quality improvement, no inference |
| Profile category removal | Public | Removing misleading data is a quality improvement |

---

## Out of Scope

- Trend/time-series visualization (revisit in H.10 design philosophy work)
- Changes to individual meeting detail pages
- Personal voting summary (Implementation 2, separate design)
- Sidebar layout or collapsible panels
- Server-side date filtering (client-side sufficient for this dataset)
