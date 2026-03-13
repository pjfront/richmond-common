# Financial Connections Page Freeze — Debugging Plan

**Date:** 2026-03-12
**Branch:** `fix-financial-connections-freeze`
**Status:** In progress. TanStack removal committed, not yet deployed/tested.

## The Bug

The `/financial-connections` page (operator-only) freezes Chrome for 60+ seconds on ANY interaction: clicking rows, changing filters, etc. Chrome shows "Page Unresponsive" dialog. Confirmed on multiple machines by Phillip. Cannot reproduce locally (dev mode shows ~64ms long tasks vs 60+ seconds in production).

## What's Been Tried (all deployed, none fixed it)

| Attempt | Commit | Result |
|---------|--------|--------|
| Progressive row rendering (requestIdleCallback) | `1f5f6f5` | **Caused** infinite render loop (worse) |
| Fix infinite render loop | `eaf7915` | Fixed the loop but freeze remained |
| Move data client-side (eliminate 167KB RSC payload) | `0e148c3` | RSC payload now 5KB, freeze unchanged |
| **Remove TanStack Table entirely** | `6929b9c` | **Not yet tested** — current attempt |

## What's Been Verified

- **API is fast:** `/api/flag-details?all=1` returns 150KB JSON in 67ms
- **RSC payload is small:** Down from 167KB to ~5KB after client-side data move
- **JS bundles are normal:** Largest is 224KB (framework), TanStack was 51KB
- **All sub-components are simple:** VoteBadge, ConfidenceBadge, CategoryBadge, SortableHeader — all trivially stateless
- **OperatorGate is not the cause:** Just a conditional render based on cookie
- **Local dev works fine:** ~750ms expand, ~600ms filter, 64ms long task

## Current Strategy: Isolation by Elimination

The commit on this branch (`6929b9c`) replaces TanStack Table with a plain HTML table + manual sorting. Same visual output, same filters, same expand/collapse, but zero TanStack code.

### If the freeze is FIXED after deploying this:
- **Root cause:** TanStack Table in production builds (minification, tree-shaking, or React 19 interaction)
- **Action:** Keep the plain HTML table. TanStack is not needed for ~150 rows with simple sorting.

### If the freeze PERSISTS:
- TanStack is ruled out
- **Next suspects (in order):**
  1. **OperatorGate hydration storm** — Server renders fallback, client swaps in full content. Could trigger massive re-render of the entire page tree. Test: temporarily remove OperatorGate wrapper.
  2. **Page structure** — The page has 7 summary cards + "By Official" grid + the table. Maybe the combined re-render is the issue. Test: render ONLY the table, nothing else.
  3. **Next.js production optimizations** — Something in the production build (RSC streaming, partial hydration, route segment config) behaves differently. Test: compare `next build && next start` locally vs Vercel.
  4. **CSS/layout thrashing** — The `overflow-x-auto` container or `line-clamp-2` could trigger expensive layout recalculations. Test: strip all dynamic CSS.

## Version Indicator

Added `BUILD_VERSION` constant showing the date at the bottom of the table component so Phillip can verify deployments without asking.

## Next Steps for New Session

1. Merge branch to `main` and push (triggers Vercel deploy)
2. Wait for deploy, verify version indicator shows on page
3. Test interactions. Does it freeze?
4. If yes, proceed to suspect #1 (OperatorGate) from the list above
5. If no, done! Clean up and commit.

## Also Pending (Not This Session)

- B.49: Consent Calendar Sub-Item Attribution
