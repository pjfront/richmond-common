import { describe, expect, it } from 'vitest'
import { orderPACsForIndex } from '@/lib/pac-index-order'
import type { PACWithCycleBars } from '@/lib/queries/pacs'

function pac({
  name,
  currentIn = 0,
  currentOut = 0,
  lastActive = 0,
  totalRaised = 0,
}: {
  name: string
  currentIn?: number
  currentOut?: number
  lastActive?: number
  totalRaised?: number
}): PACWithCycleBars {
  return {
    id: name,
    member_ids: [name],
    name,
    slug: name.toLowerCase().replaceAll(' ', '-'),
    filer_id: null,
    committee_type: null,
    sponsor_disclosure: null,
    total_raised: totalRaised,
    donor_count: 1,
    contribution_count: 1,
    latest_contribution_date: null,
    earliest_contribution_date: null,
    cycle_bars: [
      {
        cycle: lastActive,
        in_total: lastActive > 0 ? 1 : 0,
        out_total: 0,
      },
    ],
    current_cycle_in: currentIn,
    current_cycle_out: currentOut,
  }
}

describe('PAC index ordering', () => {
  it('prioritizes current activity, then recency, all-time total, and name', () => {
    const ordered = orderPACsForIndex([
      pac({ name: 'Zulu', currentIn: 10, lastActive: 2026, totalRaised: 100 }),
      pac({ name: 'Active', currentOut: 20, lastActive: 2026, totalRaised: 10 }),
      pac({ name: 'Recent', lastActive: 2024, totalRaised: 10 }),
      pac({ name: 'Older Rich', lastActive: 2022, totalRaised: 1_000 }),
      pac({ name: 'Older Small', lastActive: 2022, totalRaised: 100 }),
      pac({ name: 'Bravo', totalRaised: 50 }),
      pac({ name: 'Alpha', totalRaised: 50 }),
    ])

    expect(ordered.map((entry) => entry.name)).toEqual([
      'Active',
      'Zulu',
      'Recent',
      'Older Rich',
      'Older Small',
      'Alpha',
      'Bravo',
    ])
  })

  it('does not mutate the query result', () => {
    const original = [pac({ name: 'Quiet' }), pac({ name: 'Active', currentIn: 1 })]

    const ordered = orderPACsForIndex(original)

    expect(original.map((entry) => entry.name)).toEqual(['Quiet', 'Active'])
    expect(ordered.map((entry) => entry.name)).toEqual(['Active', 'Quiet'])
  })
})
