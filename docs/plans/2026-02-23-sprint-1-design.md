# Sprint 1 Design — Visibility + Data Foundation

*Created: 2026-02-23*
*Status: Approved*

---

## Overview

Sprint 1 makes progress visible and lays the data groundwork everything else builds on. Five items, all approved:

| Item | Summary |
|------|---------|
| S1.1 Feature Gating | Cookie + env secret operator toggle with React context |
| S1.2 Table Sorting | TanStack Table adoption across all data tables |
| S1.3 Commission Pages | `/commissions` directory + detail pages |
| S1.4 Archive Expansion | Expand from AMID=31 to all Tier 1+2 AMIDs |
| S1.5 CI/CD | GitHub Actions test workflow + Vercel auto-deploy |

**Execution order:** S1.1 > S1.2 + S1.3 (parallel) > S1.4 > S1.5

---

## S1.1 Feature Gating System

**Mechanism:** URL param with secret value from `.env` sets a browser cookie. React context provides `isOperator` boolean. `<OperatorGate>` wraps gated content.

**Details:**
- `?op=SECRET_VALUE` sets `rtp_operator` cookie (read by JS, not HttpOnly)
- `?op=0` clears the cookie
- `OperatorModeProvider` context reads cookie, provides `isOperator`
- `<OperatorGate>` component: renders children only when `isOperator === true`
- Nav shows subtle indicator (small "OP" badge) when operator mode active
- Secret value stored in `.env` as `RTP_OPERATOR_SECRET`

**Security posture:** Obscurity only. Not real auth. Operator mode reveals WIP features, not admin controls. Acceptable for single-operator beta. Security upgrade trigger logged in DECISIONS.md: replace with Supabase Auth when operator mode gains write capabilities or second operator is added.

**New files:**
- `web/src/components/OperatorModeProvider.tsx` (context provider)
- `web/src/components/OperatorGate.tsx` (conditional wrapper)

**Modified files:**
- `web/src/app/layout.tsx` (wrap with provider)
- `web/src/components/Nav.tsx` (operator indicator)
- `.env.example` (add `RTP_OPERATOR_SECRET=change-me`)

---

## S1.2 Table Sorting with TanStack Table

**Decision:** Adopt `@tanstack/react-table` for all data tables. Refactor existing tables + build new ones with TanStack from the start.

**New dependency:** `@tanstack/react-table`

**Tables affected:**

| Table | Current state | Changes |
|-------|--------------|---------|
| DonorTable | Hand-rolled useState sorting | Refactor to TanStack. Same columns, same behavior. |
| VotingRecordTable | Filtering only, no sort | Add TanStack with sorting on: date, category, vote choice, result. Keep existing filter UI. |
| CommissionRosterTable | Does not exist | New TanStack table. Columns: name, role, appointed by, term end. |

**Shared pattern:**
- `SortableHeader` component for consistent click-to-sort UX across all tables
- Headless (TanStack provides logic, Tailwind provides styling)
- Existing "Show all N" expand pattern preserved (no pagination)

**New files:**
- `web/src/components/SortableHeader.tsx`
- `web/src/components/CommissionRosterTable.tsx`

**Modified files:**
- `web/package.json` (add dependency)
- `web/src/components/DonorTable.tsx` (refactor to TanStack)
- `web/src/components/VotingRecordTable.tsx` (add TanStack sorting)

---

## S1.3 Commission Pages

**Pages:**

| Route | Content | Publication tier |
|-------|---------|-----------------|
| `/commissions` | Grid of all commissions. Card per commission: name, type badge, seats filled/total, Form 700 indicator | Public |
| `/commissions/[id]` | Member roster (TanStack), appointment authority, schedule, staleness alerts | Mixed (roster Public, staleness Operator-only) |

**Nav:** Add "Boards" link between "Council" and "Public Records".

**New types** (`web/lib/types.ts`):
- `Commission` — maps to `commissions` table
- `CommissionMember` — maps to `commission_members` table
- `CommissionWithStats` — commission + member count + vacancy count

**New queries** (`web/lib/queries.ts`):
- `getCommissions()` — all active commissions with member counts
- `getCommission(id)` — single commission with full member roster
- Staleness data from `v_commission_staleness` view

**New files:**
- `web/src/app/commissions/page.tsx`
- `web/src/app/commissions/[id]/page.tsx`
- `web/src/components/CommissionCard.tsx`
- `web/src/components/CommissionRosterTable.tsx` (shared with S1.2)

**Modified files:**
- `web/src/components/Nav.tsx` (add "Boards" link)
- `web/src/lib/types.ts` (add commission types)
- `web/src/lib/queries.ts` (add commission queries)

**Not in scope:** Commission meeting history, commissioner profiles, appointment network visualization, Form 700 cross-referencing.

---

## S1.4 Archive Center Expansion

**What:** Expand from AMID=31 (council minutes) to all high-priority AMIDs. Download PDFs into Layer 1. No Claude extraction.

**AMID tiers:**

| Tier | AMIDs | Approx docs | Content |
|------|-------|-------------|---------|
| Tier 1 | 67, 66, 132, 133, 168, 169, 61, 77 | ~4,500 | Resolutions, ordinances, Personnel Board, Rent Board, Design Review Board |
| Tier 2 | 87 (+ 31 already done) | ~1,000 | City Manager reports |
| Tier 3 (defer) | Remaining ~140 AMIDs | ~3,500 | Low-priority until RAG search |

**Implementation:**
- Update `city_config.py`: define `archive_tier_1_amids` and `archive_tier_2_amids` lists
- Extend `batch_extract.py`: loop over configured AMID tiers (currently hardcoded AMID=31)
- Store raw PDFs in document lake with metadata (AMID, title, date, source URL)
- No extraction. Zero marginal compute cost.

**Modified files:**
- `src/city_config.py`
- `src/batch_extract.py`

---

## S1.5 CI/CD

**Three pieces:**

**1. GitHub Actions test workflow** (AI builds)
- `.github/workflows/test.yml`
- Triggers on PR to `main`
- Runs `pytest` (Python 3.11+)
- No Supabase connection needed (tests use mocks)

**2. Vercel auto-deploy** (operator, manual)
- Connect Vercel project to GitHub in dashboard
- Auto-deploy on push to `main`, PR preview deploys
- ~5 min in Vercel dashboard

**3. Branch protection** (operator, manual)
- Require passing checks before merge to `main`
- ~2 min in GitHub Settings

**New files:**
- `.github/workflows/test.yml`

**Not in scope:** Pipeline CI cleanup (H.1 hygiene item).

---

## Key Decisions Made During Design

| Decision | Rationale |
|----------|-----------|
| Cookie + env secret over Supabase Auth | Single-operator beta. Upgrade trigger: write capabilities or second operator. Logged in DECISIONS.md. |
| TanStack Table over hand-rolled sorting | We're touching all 3 tables anyway. Cheapest adoption moment. Breakeven at table #6, but developer ergonomics justify it now. |
| Option B (TanStack) over Option A (native) | +30 min build, saves ~30 min per future table. Bundle size impact: +15-20 KB gzipped. Negligible. |
| "Boards" nav label over "Commissions" | Shorter. Nav space is tight. |
| Tier 1+2 archive download, defer Tier 3 | 5,500 docs covers all S2-S5 needs. Remaining 3,500 wait for RAG search. |
