# Meetings Page Category Snapshot — Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Move the category breakdown from council profiles to the meetings page, add date filtering and procedural item handling, per the approved design at `docs/plans/2026-02-26-meetings-category-snapshot-design.md`.

**Architecture:** Client-side filtering on pre-fetched meeting data. Server component fetches all meetings with full category data, passes to a client component that handles date filtering, category aggregation, and procedural toggling. ~24 meetings/year makes client-side filtering appropriate.

**Tech Stack:** Next.js 16 (app router), React 19, TypeScript strict, Tailwind CSS v4, Supabase queries.

**Vibe-coding time estimate:** ~2-3 hours total (human+AI pair)

---

## Task 1: Add `procedural` to Backend Enum

**Files:**
- Modify: `src/models.py:32-45`

**Step 1: Add PROCEDURAL to AgendaCategory enum**

In `src/models.py`, add `PROCEDURAL = "procedural"` after `APPOINTMENTS`:

```python
class AgendaCategory(str, Enum):
    ZONING = "zoning"
    BUDGET = "budget"
    HOUSING = "housing"
    PUBLIC_SAFETY = "public_safety"
    ENVIRONMENT = "environment"
    INFRASTRUCTURE = "infrastructure"
    PERSONNEL = "personnel"
    CONTRACTS = "contracts"
    GOVERNANCE = "governance"
    PROCLAMATION = "proclamation"
    LITIGATION = "litigation"
    OTHER = "other"
    APPOINTMENTS = "appointments"
    PROCEDURAL = "procedural"
```

**Step 2: Run existing tests to confirm nothing breaks**

Run: `python3 -m pytest tests/ -q --tb=short`
Expected: All tests pass (no test references the enum values directly in a way that would break)

**Step 3: Commit**

```bash
git add src/models.py
git commit -m "feat: add procedural category to AgendaCategory enum"
```

---

## Task 2: Add `procedural` to Extraction Prompts

**Files:**
- Modify: `src/extraction.py:130-137` (consent calendar items category enum)
- Modify: `src/extraction.py:159-167` (action items category enum)
- Modify: `src/extract_agenda.py:42` (pipe-separated category list)

**Step 1: Update extraction.py consent calendar enum (lines 130-137)**

Add `"procedural"` to the enum array:

```python
                            "category": {
                                "type": "string",
                                "enum": [
                                    "zoning", "budget", "housing", "public_safety",
                                    "environment", "infrastructure", "personnel",
                                    "contracts", "governance", "proclamation",
                                    "litigation", "other", "appointments",
                                    "procedural"
                                ]
                            },
```

**Step 2: Update extraction.py action items enum (lines 159-167)**

Same change, add `"procedural"` to the second enum array:

```python
                    "category": {
                        "type": "string",
                        "enum": [
                            "zoning", "budget", "housing", "public_safety",
                            "environment", "infrastructure", "personnel",
                            "contracts", "governance", "proclamation",
                            "litigation", "other", "appointments",
                            "procedural"
                        ]
                    },
```

**Step 3: Update extract_agenda.py (line 42)**

Add `|procedural` to the pipe-separated category string:

```python
            "category": "zoning|budget|housing|public_safety|environment|infrastructure|personnel|contracts|governance|proclamation|litigation|other|procedural",
```

**Step 4: Run tests**

Run: `python3 -m pytest tests/ -q --tb=short`
Expected: All pass

**Step 5: Commit**

```bash
git add src/extraction.py src/extract_agenda.py
git commit -m "feat: add procedural category to LLM extraction schemas"
```

---

## Task 3: Add `procedural` to Keyword Classifiers

**Files:**
- Modify: `src/escribemeetings_to_agenda.py:29-55`
- Modify: `src/run_pipeline.py:80-101`

**Step 1: Add procedural keywords to escribemeetings_to_agenda.py**

Insert a new check *before* the final `return "other"` at line 55. The procedural check must come early (before `governance`) because some procedural items contain words like "minutes" that currently match `governance`:

In `classify_category()`, add this block right after the function signature and `text = ...` line (before the first `if`):

```python
    if any(w in text for w in ["roll call", "pledge of allegiance", "pledge to the flag",
                                "approval of minutes", "approve minutes", "approval of the agenda",
                                "approve the agenda", "agenda reorder", "adjournment", "adjourned",
                                "recess"]):
        return "procedural"
```

**Step 2: Add procedural keywords to run_pipeline.py**

Insert a `("procedural", [...])` tuple at the *beginning* of the `categories` list in `categorize_item()` (before `"housing"`), so procedural items are matched first:

```python
    categories = [
        ("procedural", ["roll call", "pledge of allegiance", "pledge to the flag",
                        "approval of minutes", "approve minutes", "approval of the agenda",
                        "approve the agenda", "agenda reorder", "adjournment", "adjourned",
                        "recess"]),
        ("housing", ["housing", "affordable", "homeless", "tenant", "rent", "homekey"]),
        # ... rest unchanged
    ]
```

**Step 3: Run tests**

Run: `python3 -m pytest tests/ -q --tb=short`
Expected: All pass

**Step 4: Commit**

```bash
git add src/escribemeetings_to_agenda.py src/run_pipeline.py
git commit -m "feat: add procedural keywords to category classifiers"
```

---

## Task 4: Add `procedural` to Frontend CategoryBadge

**Files:**
- Modify: `web/src/components/CategoryBadge.tsx:1-24`

**Step 1: Add procedural color to categoryColors map**

Add `procedural` entry after `ceremonial` (line 23). Use a muted gray to visually signal "process, not substance":

```typescript
  ceremonial: 'bg-violet-100 text-violet-800',
  procedural: 'bg-gray-100 text-gray-500',
```

**Step 2: Verify the dev server renders it**

Run: `cd web && npx next build`
Expected: Build succeeds with no type errors

**Step 3: Commit**

```bash
git add web/src/components/CategoryBadge.tsx
git commit -m "feat: add procedural color to CategoryBadge"
```

---

## Task 5: Update Query to Return All Categories Per Meeting

**Files:**
- Modify: `web/src/lib/queries.ts:95-114`
- Modify: `web/src/lib/types.ts:190-194`

The current `getMeetingsWithCounts()` truncates categories to top 4 per meeting (line 113: `.slice(0, 4)`). For the meetings page aggregate view, we need all categories. Rather than changing the existing behavior (MeetingCards still want top 4), we add a new field.

**Step 1: Add `all_categories` to MeetingWithCounts type**

In `web/src/lib/types.ts`, add `all_categories` to the `MeetingWithCounts` interface:

```typescript
export interface MeetingWithCounts extends Meeting {
  agenda_item_count: number
  vote_count: number
  top_categories: CategoryCount[]
  all_categories: CategoryCount[]
}
```

**Step 2: Return all_categories in getMeetingsWithCounts()**

In `web/src/lib/queries.ts`, modify the return mapping (lines 106-114) to include the untruncated list:

```typescript
  return meetings.map((m) => ({
    ...m,
    agenda_item_count: itemCountMap.get(m.id) ?? 0,
    vote_count: voteCountMap.get(m.id) ?? 0,
    top_categories: Array.from(categoryMap.get(m.id)?.entries() ?? [])
      .map(([category, count]) => ({ category, count }))
      .sort((a, b) => b.count - a.count)
      .slice(0, 4),
    all_categories: Array.from(categoryMap.get(m.id)?.entries() ?? [])
      .map(([category, count]) => ({ category, count }))
      .sort((a, b) => b.count - a.count),
  }))
```

**Step 3: Build to verify**

Run: `cd web && npx next build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add web/src/lib/types.ts web/src/lib/queries.ts
git commit -m "feat: add all_categories field to MeetingsWithCounts"
```

---

## Task 6: Build the Date Filter Bar Component

**Files:**
- Create: `web/src/components/DateFilterBar.tsx`

**Step 1: Create DateFilterBar component**

This is a client component with date range inputs and quick-select shortcuts. Default: current year (Jan 1 to Dec 31).

```tsx
'use client'

import { useState, useCallback } from 'react'

interface DateFilterBarProps {
  onChange: (range: { start: string; end: string }) => void
  defaultStart: string
  defaultEnd: string
}

function getYearRange(year: number) {
  return { start: `${year}-01-01`, end: `${year}-12-31` }
}

export default function DateFilterBar({ onChange, defaultStart, defaultEnd }: DateFilterBarProps) {
  const [start, setStart] = useState(defaultStart)
  const [end, setEnd] = useState(defaultEnd)
  const [activeShortcut, setActiveShortcut] = useState<string>('this_year')

  const currentYear = new Date().getFullYear()

  const applyRange = useCallback(
    (s: string, e: string, shortcut: string) => {
      setStart(s)
      setEnd(e)
      setActiveShortcut(shortcut)
      onChange({ start: s, end: e })
    },
    [onChange]
  )

  const shortcuts = [
    { label: 'This year', key: 'this_year', range: getYearRange(currentYear) },
    { label: 'Last year', key: 'last_year', range: getYearRange(currentYear - 1) },
    { label: 'All time', key: 'all_time', range: { start: '2000-01-01', end: `${currentYear}-12-31` } },
  ]

  return (
    <div className="flex flex-wrap items-center gap-3 py-4">
      <div className="flex items-center gap-2 text-sm">
        <label htmlFor="date-start" className="text-slate-500">From</label>
        <input
          id="date-start"
          type="date"
          value={start}
          onChange={(e) => {
            setStart(e.target.value)
            setActiveShortcut('')
            onChange({ start: e.target.value, end })
          }}
          className="border border-slate-300 rounded px-2 py-1 text-sm text-slate-700"
        />
        <label htmlFor="date-end" className="text-slate-500">to</label>
        <input
          id="date-end"
          type="date"
          value={end}
          onChange={(e) => {
            setEnd(e.target.value)
            setActiveShortcut('')
            onChange({ start, end: e.target.value })
          }}
          className="border border-slate-300 rounded px-2 py-1 text-sm text-slate-700"
        />
      </div>
      <div className="flex gap-1.5">
        {shortcuts.map((sc) => (
          <button
            key={sc.key}
            onClick={() => applyRange(sc.range.start, sc.range.end, sc.key)}
            className={`text-xs px-2.5 py-1 rounded-full transition-colors ${
              activeShortcut === sc.key
                ? 'bg-civic-navy text-white'
                : 'bg-slate-100 text-slate-600 hover:bg-slate-200'
            }`}
          >
            {sc.label}
          </button>
        ))}
      </div>
    </div>
  )
}
```

**Step 2: Build to verify**

Run: `cd web && npx next build`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add web/src/components/DateFilterBar.tsx
git commit -m "feat: add DateFilterBar component with quick-select shortcuts"
```

---

## Task 7: Build the Topic Overview Component

**Files:**
- Create: `web/src/components/TopicOverview.tsx`

This adapts the horizontal bar pattern from `CategoryBreakdown` but adds the procedural toggle and accepts aggregated cross-meeting data. It's a new component rather than modifying `CategoryBreakdown` because the data shape, heading, and toggle behavior differ.

**Step 1: Create TopicOverview component**

```tsx
'use client'

import { useState, useMemo } from 'react'
import CategoryBadge from './CategoryBadge'

interface CategoryCount {
  category: string
  count: number
}

interface TopicOverviewProps {
  categories: CategoryCount[]
}

const PROCEDURAL = 'procedural'

export default function TopicOverview({ categories }: TopicOverviewProps) {
  const [showProcedural, setShowProcedural] = useState(false)

  const { visible, proceduralCount, substantiveCount } = useMemo(() => {
    const procedural = categories.filter((c) => c.category === PROCEDURAL)
    const substantive = categories.filter((c) => c.category !== PROCEDURAL)
    const pCount = procedural.reduce((sum, c) => sum + c.count, 0)
    const sCount = substantive.reduce((sum, c) => sum + c.count, 0)

    return {
      visible: showProcedural ? categories : substantive,
      proceduralCount: pCount,
      substantiveCount: sCount,
    }
  }, [categories, showProcedural])

  const sorted = useMemo(
    () => [...visible].sort((a, b) => b.count - a.count),
    [visible]
  )

  const totalVisible = sorted.reduce((sum, c) => sum + c.count, 0)

  if (categories.length === 0) return null

  return (
    <section className="mb-8">
      <h2 className="text-xl font-semibold text-slate-800 mb-3">Topic Overview</h2>
      <div className="bg-white rounded-lg border border-slate-200 p-4">
        <div className="space-y-3">
          {sorted.map((cat) => {
            const pct = totalVisible > 0 ? Math.round((cat.count / totalVisible) * 100) : 0
            return (
              <div key={cat.category} className="flex items-center gap-3">
                <div className="w-28 shrink-0">
                  <CategoryBadge category={cat.category} />
                </div>
                <div className="flex-1">
                  <div className="h-2 bg-slate-100 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-civic-navy rounded-full"
                      style={{ width: `${pct}%` }}
                    />
                  </div>
                </div>
                <span className="text-sm text-slate-600 w-16 text-right">
                  {cat.count} ({pct}%)
                </span>
              </div>
            )
          })}
        </div>

        {/* Procedural toggle */}
        <div className="mt-3 text-sm text-slate-500">
          {showProcedural ? (
            <span>
              <strong>{substantiveCount + proceduralCount} total items</strong>
              {' '}&middot;{' '}
              <button
                onClick={() => setShowProcedural(false)}
                className="text-civic-navy hover:underline"
              >
                hide procedural
              </button>
            </span>
          ) : (
            <span>
              <strong>{substantiveCount} substantive items</strong>
              {proceduralCount > 0 && (
                <>
                  {' '}&middot; {proceduralCount} procedural hidden{' '}&middot;{' '}
                  <button
                    onClick={() => setShowProcedural(true)}
                    className="text-civic-navy hover:underline"
                  >
                    show
                  </button>
                </>
              )}
            </span>
          )}
        </div>
      </div>
    </section>
  )
}
```

**Step 2: Build to verify**

Run: `cd web && npx next build`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add web/src/components/TopicOverview.tsx
git commit -m "feat: add TopicOverview component with procedural toggle"
```

---

## Task 8: Rewire the Meetings Page

**Files:**
- Modify: `web/src/app/meetings/page.tsx` (full rewrite)

This is the main integration task. The page splits into a server component (data fetching) and a client component (filtering + rendering). Next.js 16 app router convention: server component fetches, client component handles interactivity.

**Step 1: Create the MeetingsPageClient component**

Create `web/src/components/MeetingsPageClient.tsx`:

```tsx
'use client'

import { useState, useMemo, useCallback } from 'react'
import type { MeetingWithCounts, CategoryCount } from '@/lib/types'
import DateFilterBar from './DateFilterBar'
import TopicOverview from './TopicOverview'
import MeetingCard from './MeetingCard'

interface MeetingsPageClientProps {
  meetings: MeetingWithCounts[]
}

function getYearRange() {
  const year = new Date().getFullYear()
  return { start: `${year}-01-01`, end: `${year}-12-31` }
}

export default function MeetingsPageClient({ meetings }: MeetingsPageClientProps) {
  const defaultRange = getYearRange()
  const [dateRange, setDateRange] = useState(defaultRange)

  const handleDateChange = useCallback((range: { start: string; end: string }) => {
    setDateRange(range)
  }, [])

  // Filter meetings by date range
  const filteredMeetings = useMemo(
    () =>
      meetings.filter((m) => m.meeting_date >= dateRange.start && m.meeting_date <= dateRange.end),
    [meetings, dateRange]
  )

  // Aggregate categories across filtered meetings
  const aggregatedCategories = useMemo(() => {
    const catMap = new Map<string, number>()
    for (const m of filteredMeetings) {
      for (const c of m.all_categories) {
        catMap.set(c.category, (catMap.get(c.category) ?? 0) + c.count)
      }
    }
    return Array.from(catMap.entries())
      .map(([category, count]): CategoryCount => ({ category, count }))
      .sort((a, b) => b.count - a.count)
  }, [filteredMeetings])

  // Group filtered meetings by year
  const byYear = useMemo(() => {
    const map = new Map<number, MeetingWithCounts[]>()
    for (const m of filteredMeetings) {
      const year = new Date(m.meeting_date + 'T00:00:00').getFullYear()
      const arr = map.get(year) ?? []
      arr.push(m)
      map.set(year, arr)
    }
    return map
  }, [filteredMeetings])

  const years = useMemo(
    () => Array.from(byYear.keys()).sort((a, b) => b - a),
    [byYear]
  )

  return (
    <>
      <DateFilterBar
        onChange={handleDateChange}
        defaultStart={defaultRange.start}
        defaultEnd={defaultRange.end}
      />

      <TopicOverview categories={aggregatedCategories} />

      {filteredMeetings.length === 0 ? (
        <p className="text-slate-500 mt-8">No meetings in this date range.</p>
      ) : (
        years.map((year) => (
          <section key={year} className="mt-8">
            <h2 className="text-xl font-semibold text-slate-800 mb-4">{year}</h2>
            <div className="space-y-3">
              {(byYear.get(year) ?? []).map((m) => (
                <MeetingCard
                  key={m.id}
                  id={m.id}
                  meetingDate={m.meeting_date}
                  meetingType={m.meeting_type}
                  presidingOfficer={m.presiding_officer}
                  agendaItemCount={m.agenda_item_count}
                  voteCount={m.vote_count}
                  topCategories={m.top_categories}
                />
              ))}
            </div>
          </section>
        ))
      )}
    </>
  )
}
```

**Step 2: Rewrite meetings/page.tsx as a thin server wrapper**

Replace the contents of `web/src/app/meetings/page.tsx`:

```tsx
import type { Metadata } from 'next'
import { getMeetingsWithCounts } from '@/lib/queries'
import MeetingsPageClient from '@/components/MeetingsPageClient'
import LastUpdated from '@/components/LastUpdated'

export const revalidate = 3600

export const metadata: Metadata = {
  title: 'Meetings',
  description: 'Richmond City Council meeting minutes with voting records and attendance.',
}

export default async function MeetingsPage() {
  const meetings = await getMeetingsWithCounts()

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <h1 className="text-3xl font-bold text-civic-navy">Council Meetings</h1>
      <p className="text-slate-600 mt-2">
        Extracted from official city council minutes. Click a meeting to see agenda items, votes, and attendance.
      </p>

      <MeetingsPageClient meetings={meetings} />

      <LastUpdated />
    </div>
  )
}
```

**Step 3: Build to verify**

Run: `cd web && npx next build`
Expected: Build succeeds

**Step 4: Start dev server and visually verify**

Run: `cd web && npm run dev`
Check: `http://localhost:3000/meetings`
Expected:
- Date filter bar with "This year" selected by default
- Topic Overview section with horizontal bars (may show no data if current year has no meetings; switch to "All time" to verify)
- Meeting cards grouped by year below the topic overview
- Switching date range updates both topic overview and meeting list

**Step 5: Commit**

```bash
git add web/src/components/MeetingsPageClient.tsx web/src/app/meetings/page.tsx
git commit -m "feat: rewire meetings page with date filtering and topic overview"
```

---

## Task 9: Remove CategoryBreakdown from Council Profile

**Files:**
- Modify: `web/src/app/council/[slug]/page.tsx:7-19` (imports)
- Modify: `web/src/app/council/[slug]/page.tsx:53-59` (data fetching)
- Modify: `web/src/app/council/[slug]/page.tsx:148-152` (render)

**Step 1: Remove CategoryBreakdown import (line 18)**

Remove this line:
```typescript
import CategoryBreakdown from '@/components/CategoryBreakdown'
```

**Step 2: Remove getOfficialCategoryBreakdown from the import (line 11)**

Change line 11 from:
```typescript
  getOfficialCategoryBreakdown,
```
to remove it. The import block becomes:
```typescript
import {
  getOfficialBySlug,
  getOfficialWithStats,
  getOfficialVotingRecord,
  getTopDonors,
  getConflictFlags,
} from '@/lib/queries'
```

**Step 3: Remove categoryBreakdown from Promise.all (lines 53-59)**

Change the destructuring and Promise.all to remove the category call:

```typescript
  const [stats, rawVotes, donors, flags] = await Promise.all([
    getOfficialWithStats(official.id),
    getOfficialVotingRecord(official.id),
    getTopDonors(official.id),
    getConflictFlags(undefined),
  ])
```

**Step 4: Remove the CategoryBreakdown render (lines 148-152)**

Remove these lines:
```tsx
      {/* Category Breakdown */}
      <CategoryBreakdown
        categories={categoryBreakdown}
        totalVotes={stats?.vote_count ?? 0}
      />
```

**Step 5: Build to verify**

Run: `cd web && npx next build`
Expected: Build succeeds, no unused variable warnings for `categoryBreakdown`

**Step 6: Verify council profile page renders correctly**

Run: `cd web && npm run dev`
Check any council member page (e.g., `http://localhost:3000/council/eduardo-martinez`)
Expected: Page loads, no category breakdown section, all other sections intact (stats bar, bio, transparency flags, donors, voting record)

**Step 7: Commit**

```bash
git add web/src/app/council/[slug]/page.tsx
git commit -m "feat: remove category breakdown from council profiles

Categories describe citywide agenda, not individual behavior.
Moved to meetings page where it semantically belongs.
Component and query retained for future personal voting summary."
```

---

## Task 10: Final Verification and Summary Commit

**Step 1: Run backend tests**

Run: `python3 -m pytest tests/ -q --tb=short`
Expected: All pass

**Step 2: Run frontend build**

Run: `cd web && npx next build`
Expected: Clean build, no errors

**Step 3: Visual verification checklist**

Start dev server (`cd web && npm run dev`) and check:

- [ ] `/meetings` — Date filter bar visible with "This year" active
- [ ] `/meetings` — Topic Overview shows horizontal bars for categories
- [ ] `/meetings` — Switching to "All time" shows all meetings and aggregated categories
- [ ] `/meetings` — Switching to "Last year" filters both bars and meeting list
- [ ] `/meetings` — Custom date range via pickers works
- [ ] `/meetings` — Procedural toggle shows/hides procedural items (may need data with procedural category to test fully)
- [ ] `/meetings` — Empty state when date range has no meetings
- [ ] `/meetings` — Meeting cards still show top category badges
- [ ] `/council/[slug]` — No category breakdown section
- [ ] `/council/[slug]` — All other sections intact

**Step 4: Commit message judgment call**

This is a public-facing change (meetings page redesign + profile section removal). Flag for human review.

**Proposed message:**
```
feat: add topic overview to meetings page with date filtering

Move category visualization from council profiles to meetings page
where it semantically belongs. Categories describe citywide agenda
composition, not individual member choices.

- Date range filter with quick-select shortcuts (This year, Last year, All time)
- Topic overview with horizontal bars, ranked by frequency
- Procedural items hidden by default with inline toggle
- Council profiles retain stats, bios, donors, and voting record
```

**Alternative framing:**
```
feat: meetings page topic overview and date filtering

Add citywide topic breakdown to meetings page with date-range
filtering. Remove per-official category breakdown from council
profiles (categories were misleading as individual metrics).
```

Review both options and confirm which to use, or provide a revision.
