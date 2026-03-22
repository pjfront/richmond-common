# Sprint 1 Implementation Plan — Visibility + Data Foundation

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Ship operator toggle, TanStack tables, commission pages, archive expansion, and CI/CD as the foundation for all Phase 2 work.

**Architecture:** Cookie-based operator gating wraps React context. TanStack Table replaces hand-rolled sorting across all data tables. Commission pages query existing Supabase schema (migration 005). Archive Center scraper expands to Tier 1+2 AMIDs. GitHub Actions runs pytest on PRs.

**Tech Stack:** Next.js 16, React 19, TypeScript, Tailwind CSS v4, @tanstack/react-table, Supabase, Python 3.11+, pytest, GitHub Actions

---

## Execution Order

S1.1 (Feature Gating) > S1.2 + S1.3 (parallel) > S1.4 > S1.5

---

## Task 1: S1.1 — OperatorModeProvider Context

**Files:**
- Create: `web/src/components/OperatorModeProvider.tsx`

**Step 1: Create the OperatorModeProvider**

```tsx
'use client'

import { createContext, useContext, useEffect, useState, type ReactNode } from 'react'

interface OperatorModeContextValue {
  isOperator: boolean
}

const OperatorModeContext = createContext<OperatorModeContextValue>({ isOperator: false })

export function useOperatorMode() {
  return useContext(OperatorModeContext)
}

const COOKIE_NAME = 'rtp_operator'

function getCookie(name: string): string | null {
  if (typeof document === 'undefined') return null
  const match = document.cookie.match(new RegExp(`(?:^|; )${name}=([^;]*)`))
  return match ? decodeURIComponent(match[1]) : null
}

function setCookie(name: string, value: string, days: number) {
  const expires = new Date(Date.now() + days * 864e5).toUTCString()
  document.cookie = `${name}=${encodeURIComponent(value)}; expires=${expires}; path=/; SameSite=Lax`
}

function deleteCookie(name: string) {
  document.cookie = `${name}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`
}

export function OperatorModeProvider({ children }: { children: ReactNode }) {
  const [isOperator, setIsOperator] = useState(false)

  useEffect(() => {
    // Check URL params for operator activation/deactivation
    const params = new URLSearchParams(window.location.search)
    const opParam = params.get('op')

    if (opParam === '0') {
      deleteCookie(COOKIE_NAME)
      setIsOperator(false)
      // Clean the URL
      params.delete('op')
      const newUrl = params.toString()
        ? `${window.location.pathname}?${params}`
        : window.location.pathname
      window.history.replaceState({}, '', newUrl)
      return
    }

    if (opParam && opParam === process.env.NEXT_PUBLIC_RTP_OPERATOR_SECRET) {
      setCookie(COOKIE_NAME, 'active', 30)
      setIsOperator(true)
      // Clean the URL
      params.delete('op')
      const newUrl = params.toString()
        ? `${window.location.pathname}?${params}`
        : window.location.pathname
      window.history.replaceState({}, '', newUrl)
      return
    }

    // No URL param — check existing cookie
    const cookie = getCookie(COOKIE_NAME)
    setIsOperator(cookie === 'active')
  }, [])

  return (
    <OperatorModeContext.Provider value={{ isOperator }}>
      {children}
    </OperatorModeContext.Provider>
  )
}
```

**Step 2: Commit**

```bash
git add web/src/components/OperatorModeProvider.tsx
git commit -m "feat(S1.1): add OperatorModeProvider context with cookie + env secret"
```

---

## Task 2: S1.1 — OperatorGate Component

**Files:**
- Create: `web/src/components/OperatorGate.tsx`

**Step 1: Create OperatorGate**

```tsx
'use client'

import { useOperatorMode } from './OperatorModeProvider'
import type { ReactNode } from 'react'

interface OperatorGateProps {
  children: ReactNode
  fallback?: ReactNode
}

export default function OperatorGate({ children, fallback = null }: OperatorGateProps) {
  const { isOperator } = useOperatorMode()
  if (!isOperator) return <>{fallback}</>
  return <>{children}</>
}
```

**Step 2: Commit**

```bash
git add web/src/components/OperatorGate.tsx
git commit -m "feat(S1.1): add OperatorGate conditional wrapper component"
```

---

## Task 3: S1.1 — Wire Provider into Layout + Nav Indicator

**Files:**
- Modify: `web/src/app/layout.tsx` (wrap with OperatorModeProvider)
- Modify: `web/src/components/Nav.tsx` (add "OP" badge)
- Modify: `.env.example` (add RTP_OPERATOR_SECRET placeholder)

**Step 1: Update layout.tsx**

Add import for `OperatorModeProvider` and wrap it around the existing tree. It goes inside `<body>` but outside `FeedbackModalProvider` (so operator mode is available to all providers):

```tsx
// Add to imports:
import { OperatorModeProvider } from "@/components/OperatorModeProvider"

// In the return, wrap the body content:
<body className={`${inter.variable} antialiased flex flex-col min-h-screen`}>
  <OperatorModeProvider>
    <FeedbackModalProvider>
      <Nav />
      <main className="flex-1">{children}</main>
      <Footer />
    </FeedbackModalProvider>
  </OperatorModeProvider>
</body>
```

**Step 2: Update Nav.tsx**

Add `'use client'` directive and operator badge. The Nav becomes a client component to read the operator context:

```tsx
'use client'

import Link from 'next/link'
import { useOperatorMode } from './OperatorModeProvider'

const navLinks = [
  { href: '/meetings', label: 'Meetings' },
  { href: '/council', label: 'Council' },
  { href: '/public-records', label: 'Public Records' },
  { href: '/reports', label: 'Reports' },
  { href: '/about', label: 'About' },
]

export default function Nav() {
  const { isOperator } = useOperatorMode()

  return (
    <nav className="bg-civic-navy text-white">
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex items-center justify-between h-16">
          <div className="flex items-center gap-2">
            <Link href="/" className="text-lg font-bold tracking-tight hover:text-civic-amber-light">
              Richmond Transparency Project
            </Link>
            {isOperator && (
              <span className="text-[10px] font-mono bg-civic-amber/20 text-civic-amber-light px-1.5 py-0.5 rounded">
                OP
              </span>
            )}
          </div>
          <div className="flex gap-1">
            {navLinks.map(({ href, label }) => (
              <Link
                key={href}
                href={href}
                className="px-3 py-2 rounded text-sm font-medium text-slate-200 hover:text-white hover:bg-civic-navy-light transition-colors"
              >
                {label}
              </Link>
            ))}
          </div>
        </div>
      </div>
    </nav>
  )
}
```

**Step 3: Update .env.example**

Add to the end of the file:

```
# Operator mode secret (URL param ?op=VALUE activates operator features)
NEXT_PUBLIC_RTP_OPERATOR_SECRET=change-me
```

**Step 4: Verify the build compiles**

Run: `cd web && npm run build`
Expected: Build succeeds (no type errors)

**Step 5: Commit**

```bash
git add web/src/app/layout.tsx web/src/components/Nav.tsx .env.example
git commit -m "feat(S1.1): wire OperatorModeProvider into layout, add Nav OP badge"
```

---

## Task 4: S1.2 — Install TanStack Table + Create SortableHeader

**Files:**
- Modify: `web/package.json` (add @tanstack/react-table)
- Create: `web/src/components/SortableHeader.tsx`

**Step 1: Install dependency**

Run: `cd /Users/phillip.front/Projects/MyProjects/RTP/web && npm install @tanstack/react-table`

**Step 2: Create SortableHeader component**

```tsx
import type { Column } from '@tanstack/react-table'

interface SortableHeaderProps<T> {
  column: Column<T, unknown>
  label: string
  className?: string
}

export default function SortableHeader<T>({ column, label, className = '' }: SortableHeaderProps<T>) {
  const sorted = column.getIsSorted()
  return (
    <th
      className={`py-2 pr-3 font-medium text-slate-600 cursor-pointer select-none hover:text-civic-navy ${className}`}
      onClick={column.getToggleSortingHandler()}
    >
      {label}
      {sorted === 'asc' && ' \u2191'}
      {sorted === 'desc' && ' \u2193'}
      {!sorted && ' \u2195'}
    </th>
  )
}
```

**Step 3: Commit**

```bash
git add web/package.json web/package-lock.json web/src/components/SortableHeader.tsx
git commit -m "feat(S1.2): install @tanstack/react-table, add SortableHeader component"
```

---

## Task 5: S1.2 — Refactor DonorTable to TanStack

**Files:**
- Modify: `web/src/components/DonorTable.tsx`

**Step 1: Rewrite DonorTable with TanStack**

Replace the entire file. Preserves: same columns (Donor, Employer, Total, #, Source), same "Show all N donors" expand behavior, same currency formatting.

```tsx
'use client'

import { useState, useMemo } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table'
import SortableHeader from './SortableHeader'
import type { DonorAggregate } from '@/lib/types'

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: 0,
    maximumFractionDigits: 0,
  }).format(amount)
}

const columnHelper = createColumnHelper<DonorAggregate>()

const columns = [
  columnHelper.accessor('donor_name', {
    header: ({ column }) => <SortableHeader column={column} label="Donor" />,
    cell: (info) => <span className="text-slate-900">{info.getValue()}</span>,
  }),
  columnHelper.accessor('donor_employer', {
    header: 'Employer',
    cell: (info) => info.getValue() ?? '\u2014',
    enableSorting: false,
    meta: { className: 'hidden sm:table-cell' },
  }),
  columnHelper.accessor('total_amount', {
    header: ({ column }) => <SortableHeader column={column} label="Total" className="text-right" />,
    cell: (info) => (
      <span className="font-medium text-slate-900">{formatCurrency(info.getValue())}</span>
    ),
    meta: { className: 'text-right' },
  }),
  columnHelper.accessor('contribution_count', {
    header: ({ column }) => <SortableHeader column={column} label="#" className="text-right" />,
    cell: (info) => <span className="text-slate-500">{info.getValue()}</span>,
    meta: { className: 'text-right' },
  }),
  columnHelper.accessor('source', {
    header: 'Source',
    enableSorting: false,
    cell: (info) => <span className="text-xs text-slate-400">{info.getValue()}</span>,
    meta: { className: 'hidden md:table-cell' },
  }),
]

export default function DonorTable({ donors }: { donors: DonorAggregate[] }) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'total_amount', desc: true },
  ])
  const [showAll, setShowAll] = useState(false)

  const data = useMemo(() => donors, [donors])

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (donors.length === 0) {
    return <p className="text-sm text-slate-500 italic">No contribution data available.</p>
  }

  const allRows = table.getRowModel().rows
  const visibleRows = showAll ? allRows : allRows.slice(0, 10)

  return (
    <div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-slate-200 text-left">
                {headerGroup.headers.map((header) => {
                  const meta = header.column.columnDef.meta as { className?: string } | undefined
                  return (
                    <th key={header.id} className={`py-2 pr-4 font-medium text-slate-600 ${meta?.className ?? ''}`}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  )
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr key={row.id} className="border-b border-slate-100">
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta as { className?: string } | undefined
                  return (
                    <td key={cell.id} className={`py-2 pr-4 ${meta?.className ?? ''}`}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!showAll && allRows.length > 10 && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 text-sm text-civic-navy-light hover:text-civic-navy"
        >
          Show all {allRows.length} donors
        </button>
      )}
    </div>
  )
}
```

**Step 2: Verify the build compiles**

Run: `cd web && npm run build`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add web/src/components/DonorTable.tsx
git commit -m "refactor(S1.2): migrate DonorTable from hand-rolled sorting to TanStack Table"
```

---

## Task 6: S1.2 — Add TanStack Sorting to VotingRecordTable

**Files:**
- Modify: `web/src/components/VotingRecordTable.tsx`

**Step 1: Rewrite VotingRecordTable with TanStack**

Replace entire file. Preserves: all existing filters (category, vote choice, hide consent calendar), the "Show all N votes" expand pattern. Adds: sortable columns for Date, Category, Vote, and Result.

```tsx
'use client'

import { useState, useMemo } from 'react'
import Link from 'next/link'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table'
import SortableHeader from './SortableHeader'
import VoteBadge from './VoteBadge'

interface VoteRecord {
  id: string
  vote_choice: string
  meeting_id: string
  meeting_date: string
  meeting_type: string
  item_number: string
  item_title: string
  category: string | null
  motion_result: string
  is_consent_calendar: boolean
}

function formatDate(dateStr: string): string {
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })
}

function formatCategory(cat: string): string {
  return cat.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

const columnHelper = createColumnHelper<VoteRecord>()

export default function VotingRecordTable({ votes }: { votes: VoteRecord[] }) {
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [choiceFilter, setChoiceFilter] = useState<string>('all')
  const [hideConsent, setHideConsent] = useState(false)
  const [showAll, setShowAll] = useState(false)
  const [sorting, setSorting] = useState<SortingState>([])

  const categories = useMemo(() => {
    const cats = new Set<string>()
    for (const v of votes) {
      if (v.category) cats.add(v.category)
    }
    return Array.from(cats).sort()
  }, [votes])

  const filtered = useMemo(() => {
    return votes.filter((v) => {
      if (categoryFilter !== 'all' && v.category !== categoryFilter) return false
      if (choiceFilter !== 'all' && v.vote_choice.toLowerCase() !== choiceFilter) return false
      if (hideConsent && v.is_consent_calendar) return false
      return true
    })
  }, [votes, categoryFilter, choiceFilter, hideConsent])

  const columns = useMemo(() => [
    columnHelper.accessor('meeting_date', {
      header: ({ column }) => <SortableHeader column={column} label="Date" />,
      cell: (info) => (
        <Link
          href={`/meetings/${info.row.original.meeting_id}`}
          className="text-slate-500 hover:text-civic-navy-light whitespace-nowrap"
        >
          {formatDate(info.getValue())}
        </Link>
      ),
      sortingFn: 'text',
    }),
    columnHelper.display({
      id: 'item',
      header: 'Item',
      cell: (info) => (
        <div className="text-slate-900">
          <span className="text-xs font-mono text-slate-400 mr-1">
            {info.row.original.item_number}
          </span>
          <span className="line-clamp-1">{info.row.original.item_title}</span>
        </div>
      ),
    }),
    columnHelper.accessor('category', {
      header: ({ column }) => (
        <SortableHeader column={column} label="Category" className="hidden md:table-cell" />
      ),
      cell: (info) => info.getValue() ? formatCategory(info.getValue()!) : '\u2014',
      meta: { className: 'hidden md:table-cell text-xs text-slate-500' },
    }),
    columnHelper.accessor('vote_choice', {
      header: ({ column }) => <SortableHeader column={column} label="Vote" />,
      cell: (info) => <VoteBadge choice={info.getValue()} />,
    }),
    columnHelper.accessor('motion_result', {
      header: ({ column }) => (
        <SortableHeader column={column} label="Result" className="hidden sm:table-cell" />
      ),
      cell: (info) => (
        <span className="text-xs text-slate-500 capitalize">{info.getValue()}</span>
      ),
      meta: { className: 'hidden sm:table-cell' },
    }),
  ], [])

  const table = useReactTable({
    data: filtered,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (votes.length === 0) {
    return <p className="text-sm text-slate-500 italic">No voting record available.</p>
  }

  const allRows = table.getRowModel().rows
  const visibleRows = showAll ? allRows : allRows.slice(0, 25)

  return (
    <div>
      {/* Filters */}
      <div className="flex flex-wrap gap-3 mb-4">
        <select
          value={categoryFilter}
          onChange={(e) => setCategoryFilter(e.target.value)}
          className="text-sm border border-slate-200 rounded px-2 py-1 text-slate-700"
        >
          <option value="all">All Categories</option>
          {categories.map((c) => (
            <option key={c} value={c}>
              {formatCategory(c)}
            </option>
          ))}
        </select>
        <select
          value={choiceFilter}
          onChange={(e) => setChoiceFilter(e.target.value)}
          className="text-sm border border-slate-200 rounded px-2 py-1 text-slate-700"
        >
          <option value="all">All Votes</option>
          <option value="aye">Aye</option>
          <option value="nay">Nay</option>
          <option value="abstain">Abstain</option>
          <option value="absent">Absent</option>
        </select>
        <label className="flex items-center gap-1.5 text-sm text-slate-600">
          <input
            type="checkbox"
            checked={hideConsent}
            onChange={(e) => setHideConsent(e.target.checked)}
            className="rounded"
          />
          Hide consent calendar
        </label>
        <span className="text-xs text-slate-400 self-center">
          {filtered.length} of {votes.length} votes
        </span>
      </div>

      {/* Table */}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((headerGroup) => (
              <tr key={headerGroup.id} className="border-b border-slate-200 text-left">
                {headerGroup.headers.map((header) => {
                  const meta = header.column.columnDef.meta as { className?: string } | undefined
                  return (
                    <th key={header.id} className={`py-2 pr-3 font-medium text-slate-600 ${meta?.className ?? ''}`}>
                      {header.isPlaceholder
                        ? null
                        : flexRender(header.column.columnDef.header, header.getContext())}
                    </th>
                  )
                })}
              </tr>
            ))}
          </thead>
          <tbody>
            {visibleRows.map((row) => (
              <tr key={row.id} className="border-b border-slate-100">
                {row.getVisibleCells().map((cell) => {
                  const meta = cell.column.columnDef.meta as { className?: string } | undefined
                  return (
                    <td key={cell.id} className={`py-2 pr-3 ${meta?.className ?? ''}`}>
                      {flexRender(cell.column.columnDef.cell, cell.getContext())}
                    </td>
                  )
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {!showAll && filtered.length > 25 && (
        <button
          onClick={() => setShowAll(true)}
          className="mt-2 text-sm text-civic-navy-light hover:text-civic-navy"
        >
          Show all {filtered.length} votes
        </button>
      )}
    </div>
  )
}
```

**Step 2: Verify the build compiles**

Run: `cd web && npm run build`
Expected: Build succeeds

**Step 3: Commit**

```bash
git add web/src/components/VotingRecordTable.tsx
git commit -m "refactor(S1.2): migrate VotingRecordTable to TanStack Table with sorting"
```

---

## Task 7: S1.3 — Add Commission Types

**Files:**
- Modify: `web/src/lib/types.ts`

**Step 1: Add commission types**

Append to the end of `web/src/lib/types.ts`, before the final line or after the last interface:

```typescript
// ─── Commissions ─────────────────────────────────────────

export interface Commission {
  id: string
  city_fips: string
  name: string
  commission_type: string
  num_seats: number | null
  appointment_authority: string | null
  form700_required: boolean
  term_length_years: number | null
  meeting_schedule: string | null
  escribemeetings_type: string | null
  archive_center_amid: number | null
  website_roster_url: string | null
  last_website_scrape: string | null
  created_at: string
}

export interface CommissionMember {
  id: string
  city_fips: string
  commission_id: string
  name: string
  normalized_name: string
  role: string
  appointed_by: string | null
  appointed_by_official_id: string | null
  term_start: string | null
  term_end: string | null
  is_current: boolean
  source: string
  source_meeting_id: string | null
  website_stale_since: string | null
  created_at: string
  updated_at: string
}

export interface CommissionWithStats extends Commission {
  member_count: number
  vacancy_count: number
}

export interface CommissionStaleness {
  commission_id: string
  city_fips: string
  commission_name: string
  last_website_scrape: string | null
  stale_members: number
  total_current_members: number
  oldest_stale_since: string | null
  max_days_stale: number | null
  stale_member_names: string[] | null
}
```

**Step 2: Commit**

```bash
git add web/src/lib/types.ts
git commit -m "feat(S1.3): add Commission, CommissionMember, and staleness types"
```

---

## Task 8: S1.3 — Add Commission Queries

**Files:**
- Modify: `web/src/lib/queries.ts`

**Step 1: Add commission imports to the existing import block**

Add `Commission`, `CommissionMember`, `CommissionWithStats`, and `CommissionStaleness` to the type import at the top of `queries.ts`.

**Step 2: Add commission queries**

Append to the end of `web/src/lib/queries.ts`:

```typescript
// ─── Commissions ─────────────────────────────────────────

export async function getCommissions(
  cityFips = RICHMOND_FIPS
): Promise<CommissionWithStats[]> {
  const { data: commissions, error } = await supabase
    .from('commissions')
    .select('*')
    .eq('city_fips', cityFips)
    .order('name')

  if (error) throw error

  const commissionIds = (commissions ?? []).map((c) => c.id)
  if (commissionIds.length === 0) return []

  // Count current members per commission
  const { data: members } = await supabase
    .from('commission_members')
    .select('commission_id')
    .in('commission_id', commissionIds)
    .eq('is_current', true)

  const memberCountMap = new Map<string, number>()
  for (const m of members ?? []) {
    memberCountMap.set(m.commission_id, (memberCountMap.get(m.commission_id) ?? 0) + 1)
  }

  return (commissions ?? []).map((c) => {
    const commission = c as Commission
    const memberCount = memberCountMap.get(commission.id) ?? 0
    const vacancyCount = commission.num_seats
      ? Math.max(0, commission.num_seats - memberCount)
      : 0
    return { ...commission, member_count: memberCount, vacancy_count: vacancyCount }
  })
}

export async function getCommission(
  commissionId: string,
  cityFips = RICHMOND_FIPS
): Promise<{ commission: Commission; members: CommissionMember[] } | null> {
  const { data: commission, error } = await supabase
    .from('commissions')
    .select('*')
    .eq('id', commissionId)
    .eq('city_fips', cityFips)
    .single()

  if (error || !commission) return null

  const { data: members } = await supabase
    .from('commission_members')
    .select('*')
    .eq('commission_id', commissionId)
    .eq('is_current', true)
    .order('name')

  return {
    commission: commission as Commission,
    members: (members ?? []) as CommissionMember[],
  }
}

export async function getCommissionStaleness(
  cityFips = RICHMOND_FIPS
): Promise<CommissionStaleness[]> {
  const { data, error } = await supabase
    .from('v_commission_staleness')
    .select('*')
    .eq('city_fips', cityFips)

  if (error) throw error
  return (data ?? []) as CommissionStaleness[]
}
```

**Step 3: Verify the build compiles**

Run: `cd web && npm run build`
Expected: Build succeeds

**Step 4: Commit**

```bash
git add web/src/lib/queries.ts
git commit -m "feat(S1.3): add commission queries (list, detail, staleness)"
```

---

## Task 9: S1.3 — CommissionCard Component

**Files:**
- Create: `web/src/components/CommissionCard.tsx`

**Step 1: Create CommissionCard**

```tsx
import Link from 'next/link'
import type { CommissionWithStats } from '@/lib/types'

function typeBadgeColor(type: string): string {
  switch (type) {
    case 'charter': return 'bg-blue-100 text-blue-800'
    case 'regulatory': return 'bg-purple-100 text-purple-800'
    case 'advisory': return 'bg-slate-100 text-slate-700'
    default: return 'bg-slate-100 text-slate-600'
  }
}

export default function CommissionCard({ commission }: { commission: CommissionWithStats }) {
  const { id, name, commission_type, num_seats, member_count, vacancy_count, form700_required } = commission

  return (
    <Link
      href={`/commissions/${id}`}
      className="block border border-slate-200 rounded-lg p-4 hover:border-civic-navy-light hover:shadow-sm transition-all"
    >
      <div className="flex items-start justify-between gap-2 mb-2">
        <h3 className="font-semibold text-slate-900 leading-tight">{name}</h3>
        <span className={`text-xs font-medium px-2 py-0.5 rounded-full whitespace-nowrap ${typeBadgeColor(commission_type)}`}>
          {commission_type}
        </span>
      </div>
      <div className="flex items-center gap-3 text-sm text-slate-500">
        <span>
          {member_count}{num_seats ? `/${num_seats}` : ''} seats
        </span>
        {vacancy_count > 0 && (
          <span className="text-amber-600 font-medium">
            {vacancy_count} vacant
          </span>
        )}
        {form700_required && (
          <span className="text-xs bg-amber-50 text-amber-700 px-1.5 py-0.5 rounded">
            Form 700
          </span>
        )}
      </div>
    </Link>
  )
}
```

**Step 2: Commit**

```bash
git add web/src/components/CommissionCard.tsx
git commit -m "feat(S1.3): add CommissionCard component for grid display"
```

---

## Task 10: S1.3 — CommissionRosterTable Component

**Files:**
- Create: `web/src/components/CommissionRosterTable.tsx`

**Step 1: Create CommissionRosterTable with TanStack**

```tsx
'use client'

import { useState, useMemo } from 'react'
import {
  useReactTable,
  getCoreRowModel,
  getSortedRowModel,
  flexRender,
  createColumnHelper,
  type SortingState,
} from '@tanstack/react-table'
import SortableHeader from './SortableHeader'
import type { CommissionMember } from '@/lib/types'

function formatDate(dateStr: string | null): string {
  if (!dateStr) return '\u2014'
  const date = new Date(dateStr + 'T00:00:00')
  return date.toLocaleDateString('en-US', { month: 'short', year: 'numeric' })
}

const columnHelper = createColumnHelper<CommissionMember>()

const columns = [
  columnHelper.accessor('name', {
    header: ({ column }) => <SortableHeader column={column} label="Name" />,
    cell: (info) => <span className="font-medium text-slate-900">{info.getValue()}</span>,
  }),
  columnHelper.accessor('role', {
    header: ({ column }) => <SortableHeader column={column} label="Role" />,
    cell: (info) => (
      <span className="text-sm text-slate-600 capitalize">{info.getValue()}</span>
    ),
  }),
  columnHelper.accessor('appointed_by', {
    header: ({ column }) => (
      <SortableHeader column={column} label="Appointed By" className="hidden md:table-cell" />
    ),
    cell: (info) => info.getValue() ?? '\u2014',
    meta: { className: 'hidden md:table-cell text-sm text-slate-500' },
  }),
  columnHelper.accessor('term_end', {
    header: ({ column }) => (
      <SortableHeader column={column} label="Term Ends" className="hidden sm:table-cell" />
    ),
    cell: (info) => {
      const value = info.getValue()
      if (!value) return '\u2014'
      const isExpired = new Date(value) < new Date()
      return (
        <span className={isExpired ? 'text-red-600 font-medium' : 'text-slate-500'}>
          {formatDate(value)}
          {isExpired && ' (expired)'}
        </span>
      )
    },
    meta: { className: 'hidden sm:table-cell text-sm' },
  }),
]

export default function CommissionRosterTable({ members }: { members: CommissionMember[] }) {
  const [sorting, setSorting] = useState<SortingState>([
    { id: 'name', desc: false },
  ])

  const data = useMemo(() => members, [members])

  const table = useReactTable({
    data,
    columns,
    state: { sorting },
    onSortingChange: setSorting,
    getCoreRowModel: getCoreRowModel(),
    getSortedRowModel: getSortedRowModel(),
  })

  if (members.length === 0) {
    return <p className="text-sm text-slate-500 italic">No members listed.</p>
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead>
          {table.getHeaderGroups().map((headerGroup) => (
            <tr key={headerGroup.id} className="border-b border-slate-200 text-left">
              {headerGroup.headers.map((header) => {
                const meta = header.column.columnDef.meta as { className?: string } | undefined
                return (
                  <th key={header.id} className={`py-2 pr-3 font-medium text-slate-600 ${meta?.className ?? ''}`}>
                    {header.isPlaceholder
                      ? null
                      : flexRender(header.column.columnDef.header, header.getContext())}
                  </th>
                )
              })}
            </tr>
          ))}
        </thead>
        <tbody>
          {table.getRowModel().rows.map((row) => (
            <tr key={row.id} className="border-b border-slate-100">
              {row.getVisibleCells().map((cell) => {
                const meta = cell.column.columnDef.meta as { className?: string } | undefined
                return (
                  <td key={cell.id} className={`py-2 pr-3 ${meta?.className ?? ''}`}>
                    {flexRender(cell.column.columnDef.cell, cell.getContext())}
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add web/src/components/CommissionRosterTable.tsx
git commit -m "feat(S1.3): add CommissionRosterTable with TanStack sorting"
```

---

## Task 11: S1.3 — Commissions Index Page

**Files:**
- Create: `web/src/app/commissions/page.tsx`

**Step 1: Create the commissions index page**

```tsx
import { Metadata } from 'next'
import { getCommissions } from '@/lib/queries'
import CommissionCard from '@/components/CommissionCard'

export const metadata: Metadata = {
  title: 'Boards & Commissions',
  description: 'Richmond boards, commissions, and committees with member rosters and appointment tracking.',
}

export const revalidate = 3600

export default async function CommissionsPage() {
  const commissions = await getCommissions()

  const totalSeats = commissions.reduce((sum, c) => sum + (c.num_seats ?? 0), 0)
  const totalFilled = commissions.reduce((sum, c) => sum + c.member_count, 0)
  const totalVacancies = commissions.reduce((sum, c) => sum + c.vacancy_count, 0)
  const form700Count = commissions.filter((c) => c.form700_required).length

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="mb-8">
        <h1 className="text-3xl font-bold text-slate-900 mb-2">Boards & Commissions</h1>
        <p className="text-slate-600">
          Richmond has {commissions.length} boards and commissions with {totalFilled} of {totalSeats} seats filled.
          {totalVacancies > 0 && ` ${totalVacancies} vacancies across all bodies.`}
          {form700Count > 0 && ` ${form700Count} require Form 700 financial disclosure.`}
        </p>
      </div>

      {commissions.length === 0 ? (
        <p className="text-slate-500 italic">No commission data available yet.</p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {commissions.map((c) => (
            <CommissionCard key={c.id} commission={c} />
          ))}
        </div>
      )}
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add web/src/app/commissions/page.tsx
git commit -m "feat(S1.3): add /commissions index page with card grid"
```

---

## Task 12: S1.3 — Commission Detail Page

**Files:**
- Create: `web/src/app/commissions/[id]/page.tsx`

**Step 1: Create the commission detail page**

```tsx
import { Metadata } from 'next'
import { notFound } from 'next/navigation'
import { getCommission, getCommissionStaleness } from '@/lib/queries'
import CommissionRosterTable from '@/components/CommissionRosterTable'
import OperatorGate from '@/components/OperatorGate'

export const revalidate = 3600

interface PageProps {
  params: Promise<{ id: string }>
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { id } = await params
  const result = await getCommission(id)
  if (!result) return { title: 'Commission Not Found' }
  return {
    title: result.commission.name,
    description: `Members and details for the ${result.commission.name}.`,
  }
}

export default async function CommissionDetailPage({ params }: PageProps) {
  const { id } = await params
  const result = await getCommission(id)
  if (!result) notFound()

  const { commission, members } = result
  const staleness = await getCommissionStaleness()
  const thisStaleness = staleness.find((s) => s.commission_id === commission.id)

  const filled = members.length
  const total = commission.num_seats
  const vacancies = total ? Math.max(0, total - filled) : 0

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <div className="flex items-start gap-3 mb-2">
          <h1 className="text-3xl font-bold text-slate-900">{commission.name}</h1>
          <span className="mt-1 text-xs font-medium px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 whitespace-nowrap">
            {commission.commission_type}
          </span>
        </div>

        <div className="flex flex-wrap gap-x-6 gap-y-1 text-sm text-slate-600">
          {total && (
            <span>{filled}/{total} seats filled{vacancies > 0 && ` (${vacancies} vacant)`}</span>
          )}
          {commission.appointment_authority && (
            <span>Appointed by: {commission.appointment_authority}</span>
          )}
          {commission.term_length_years && (
            <span>{commission.term_length_years}-year terms</span>
          )}
          {commission.meeting_schedule && (
            <span>{commission.meeting_schedule}</span>
          )}
          {commission.form700_required && (
            <span className="text-amber-700 font-medium">Form 700 required</span>
          )}
        </div>
      </div>

      {/* Staleness Alert — Operator Only */}
      <OperatorGate>
        {thisStaleness && (
          <div className="mb-6 border border-amber-200 bg-amber-50 rounded-lg p-4">
            <h3 className="font-semibold text-amber-800 mb-1">Roster Staleness Alert</h3>
            <p className="text-sm text-amber-700">
              {thisStaleness.stale_members} of {thisStaleness.total_current_members} members
              have stale website data
              {thisStaleness.max_days_stale && ` (up to ${thisStaleness.max_days_stale} days)`}.
            </p>
            {thisStaleness.stale_member_names && (
              <p className="text-xs text-amber-600 mt-1">
                Affected: {thisStaleness.stale_member_names.join(', ')}
              </p>
            )}
          </div>
        )}
      </OperatorGate>

      {/* Member Roster */}
      <section>
        <h2 className="text-xl font-semibold text-slate-900 mb-4">Current Members</h2>
        <CommissionRosterTable members={members} />
      </section>
    </div>
  )
}
```

**Step 2: Commit**

```bash
git add web/src/app/commissions/\[id\]/page.tsx
git commit -m "feat(S1.3): add /commissions/[id] detail page with roster and staleness alerts"
```

---

## Task 13: S1.3 — Add "Boards" Nav Link

**Files:**
- Modify: `web/src/components/Nav.tsx`

**Step 1: Add "Boards" link between "Council" and "Public Records"**

In Nav.tsx, update the `navLinks` array:

```typescript
const navLinks = [
  { href: '/meetings', label: 'Meetings' },
  { href: '/council', label: 'Council' },
  { href: '/commissions', label: 'Boards' },
  { href: '/public-records', label: 'Public Records' },
  { href: '/reports', label: 'Reports' },
  { href: '/about', label: 'About' },
]
```

**Step 2: Verify the build compiles**

Run: `cd web && npm run build`
Expected: Build succeeds, all pages compile

**Step 3: Commit**

```bash
git add web/src/components/Nav.tsx
git commit -m "feat(S1.3): add Boards link to navigation"
```

---

## Task 14: S1.4 — Archive Center Expansion

**Files:**
- Modify: `src/batch_extract.py`

**Step 1: Add archive download mode for configurable AMIDs**

The current `batch_extract.py` is hardcoded to AMID=31 (council minutes). Add a `--archive-download` flag that downloads documents from configured Tier 1+2 AMIDs in `city_config.py`.

The AMIDs are already configured in `city_config.py` under `data_sources.archive_center`:
- `minutes_amid`: 31 (already done)
- `tier_1_amids`: [67, 66, 87, 132, 133]
- `tier_2_amids`: [168, 169, 61, 77, 78, 75]

Add to `batch_extract.py` after the existing imports:

```python
from city_config import get_data_source_config

DEFAULT_FIPS = "0660620"
```

Add a new function before `main()`:

```python
def download_archive_amids(fips: str = DEFAULT_FIPS, tiers: list[str] | None = None) -> int:
    """Download documents from configured Archive Center AMIDs.

    Args:
        fips: City FIPS code
        tiers: Which tiers to download. Default: all configured tiers.
               Options: ["1", "2"] or ["all"]
    """
    config = get_data_source_config(fips, "archive_center")
    base_url = config["base_url"]
    doc_path = config["document_path"]

    amids_to_download: list[int] = []

    if tiers is None or "all" in tiers:
        tiers = ["1", "2"]

    if "1" in tiers:
        amids_to_download.extend(config.get("tier_1_amids", []))
    if "2" in tiers:
        amids_to_download.extend(config.get("tier_2_amids", []))

    if not amids_to_download:
        print("No AMIDs configured for the requested tiers.")
        return 0

    print(f"Downloading from {len(amids_to_download)} AMIDs: {amids_to_download}")

    total_downloaded = 0
    for amid in amids_to_download:
        archive_dir = DATA_DIR / "archive" / f"amid_{amid}"
        archive_dir.mkdir(parents=True, exist_ok=True)

        # Discover documents for this AMID
        print(f"\n  AMID {amid}: discovering documents...")
        try:
            docs = discover_meeting_minutes_urls(amid=amid, base_url=base_url)
            print(f"  AMID {amid}: found {len(docs)} documents")
        except Exception as e:
            print(f"  AMID {amid}: ERROR discovering - {e}")
            continue

        downloaded = 0
        for doc in docs:
            adid = doc.get("adid", "")
            if not adid:
                continue

            pdf_path = archive_dir / f"adid_{adid}.pdf"
            if pdf_path.exists():
                continue

            url = f"{base_url}{doc_path.format(adid=adid)}"
            try:
                download_document(url, adid, output_dir=str(archive_dir))
                downloaded += 1
                time.sleep(1)  # Be polite
            except Exception as e:
                print(f"    ERROR downloading ADID {adid}: {e}")

        print(f"  AMID {amid}: downloaded {downloaded} new documents")
        total_downloaded += downloaded

    return total_downloaded
```

Add the CLI argument in `main()`, after the existing `--cache-text` argument:

```python
parser.add_argument("--archive-download", action="store_true",
                    help="Download documents from all Tier 1+2 Archive Center AMIDs")
parser.add_argument("--archive-tiers", nargs="+", default=["all"],
                    help="Which tiers to download: 1, 2, or all (default: all)")
```

Add the handler in `main()`, after the `cache-text` block and before the API key check:

```python
if args.archive_download:
    print(f"\nDownloading Archive Center documents (tiers: {args.archive_tiers})...")
    total = download_archive_amids(tiers=args.archive_tiers)
    print(f"\nTotal downloaded: {total} documents")
    return
```

**Note:** The `download_document` function may need an `output_dir` parameter. Check if it accepts one; if not, copy the PDF manually after download. The implementer should verify the `pipeline.download_document` signature and adapt accordingly.

**Step 2: Commit**

```bash
git add src/batch_extract.py
git commit -m "feat(S1.4): add archive download for Tier 1+2 AMIDs from city config"
```

---

## Task 15: S1.5 — GitHub Actions Test Workflow

**Files:**
- Create: `.github/workflows/test.yml`

**Step 1: Create the test workflow**

```yaml
name: Tests

on:
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest

    steps:
      - uses: actions/checkout@v4

      - name: Set up Python 3.11
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install pytest python-dotenv anthropic beautifulsoup4 requests supabase
          # Install any additional test dependencies
          pip install -r requirements.txt 2>/dev/null || true

      - name: Run tests
        run: |
          cd src && python -m pytest ../tests/ -v --tb=short
        env:
          # Tests use mocks, no real API keys needed
          ANTHROPIC_API_KEY: "sk-ant-test-key"
          SUPABASE_URL: "https://test.supabase.co"
          SUPABASE_ANON_KEY: "test-anon-key"
          DATABASE_URL: "postgresql://test:test@localhost:5432/test"
```

**Note:** The implementer should verify which pip packages are needed by running `pytest` locally and checking for import errors. If a `requirements.txt` exists in the repo root, the workflow will use it. Otherwise, the explicit `pip install` line covers the main dependencies.

**Step 2: Commit**

```bash
mkdir -p .github/workflows
git add .github/workflows/test.yml
git commit -m "feat(S1.5): add GitHub Actions pytest workflow for PRs"
```

---

## Task 16: S1.5 — Manual Setup Instructions (No Code)

This task is for the operator to complete manually:

**Vercel Auto-Deploy (~5 min):**
1. Go to vercel.com/dashboard
2. Import or connect the RTP GitHub repository
3. Set root directory to `web/`
4. Set framework to Next.js
5. Add environment variables: `NEXT_PUBLIC_SUPABASE_URL`, `NEXT_PUBLIC_SUPABASE_ANON_KEY`, `NEXT_PUBLIC_RTP_OPERATOR_SECRET`
6. Enable auto-deploy on push to `main` and PR preview deploys

**Branch Protection (~2 min):**
1. Go to GitHub repo Settings > Branches
2. Add branch protection rule for `main`
3. Enable "Require status checks to pass before merging"
4. Select the "Tests" workflow as a required check

---

## Final Verification

After all tasks are complete:

1. Run `cd web && npm run build` to verify the full frontend compiles
2. Run `cd src && python -m pytest ../tests/ -v` to verify all Python tests pass
3. Manually test operator mode: navigate to `/?op=your-secret-value`, verify "OP" badge appears in nav
4. Navigate to `/commissions` to verify the page renders (may show "No commission data" if DB is empty)
5. Verify `/council/[slug]` pages still render correctly with TanStack DonorTable and VotingRecordTable

---

## Summary of All New/Modified Files

| Action | File |
|--------|------|
| Create | `web/src/components/OperatorModeProvider.tsx` |
| Create | `web/src/components/OperatorGate.tsx` |
| Create | `web/src/components/SortableHeader.tsx` |
| Create | `web/src/components/CommissionCard.tsx` |
| Create | `web/src/components/CommissionRosterTable.tsx` |
| Create | `web/src/app/commissions/page.tsx` |
| Create | `web/src/app/commissions/[id]/page.tsx` |
| Create | `.github/workflows/test.yml` |
| Modify | `web/src/app/layout.tsx` |
| Modify | `web/src/components/Nav.tsx` |
| Modify | `web/src/components/DonorTable.tsx` |
| Modify | `web/src/components/VotingRecordTable.tsx` |
| Modify | `web/src/lib/types.ts` |
| Modify | `web/src/lib/queries.ts` |
| Modify | `web/package.json` |
| Modify | `src/batch_extract.py` |
| Modify | `.env.example` |
