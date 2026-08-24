import type { PACWithCycleBars } from '@/lib/queries/pacs'

function currentCycleActivity(pac: PACWithCycleBars): number {
  return pac.current_cycle_in + pac.current_cycle_out
}

function lastActiveCycle(pac: PACWithCycleBars): number {
  let latest = 0
  for (const cycle of pac.cycle_bars) {
    if (
      cycle.cycle > latest &&
      (cycle.in_total > 0 || cycle.out_total > 0)
    ) {
      latest = cycle.cycle
    }
  }
  return latest
}

/** Keep the cut-down index relevant now, then deterministic for quiet PACs. */
export function orderPACsForIndex(
  pacs: PACWithCycleBars[],
): PACWithCycleBars[] {
  return pacs.toSorted((a, b) => {
    const currentDifference = currentCycleActivity(b) - currentCycleActivity(a)
    if (currentDifference !== 0) return currentDifference

    const lastActiveDifference = lastActiveCycle(b) - lastActiveCycle(a)
    if (lastActiveDifference !== 0) return lastActiveDifference

    const allTimeDifference = b.total_raised - a.total_raised
    if (allTimeDifference !== 0) return allTimeDifference

    return a.name.localeCompare(b.name)
  })
}
