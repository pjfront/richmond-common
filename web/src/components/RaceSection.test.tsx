import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'
import type { CandidateFundraisingDetail } from '@/lib/types'
import { emptyMatrix } from '@/lib/contributionBuckets'

vi.mock('./OperatorGate', () => ({ default: ({ fallback = null }: { fallback?: ReactNode }) => fallback }))
vi.mock('@/lib/queries/_shared', () => ({ officialToSlug: (name: string) => name.toLowerCase().replace(/\s+/g, '-') }))
vi.mock('./CandidateContributionBuckets', () => ({ default: () => null }))

import RaceSection from './RaceSection'

function candidate(name: string, raised: number): CandidateFundraisingDetail {
  return {
    id: name, candidate_name: name, office_sought: 'Mayor', is_incumbent: false,
    status: 'qualified', total_raised: raised, donor_count: raised === 73300 ? 161 : 90,
    contribution_count: 198, avg_contribution: 370, largest_contribution: 9140,
    smallest_contribution: 1, committee_id: null, official_id: null, top_donors: [],
    contribution_matrix: emptyMatrix(), bucket_grid_consistent: true,
    earliest_contribution: null, latest_contribution: null, lifetime_raised: raised,
  }
}

const coverage = { kind: 'source-checked-summary' as const,
  href: '/elections/2026-general/money/ahmad-anderson',
  scopeNote: 'The dated summary includes reports after this primary. Its figures are not primary-only totals.' }

describe('race coverage replacement', () => {
  it('replaces both roster and card values and removes the race fundraising ranking', () => {
    const disputed = candidate('Zed candidate', 73300)
    const other = candidate('Amy candidate', 60365)
    const html = renderToStaticMarkup(<RaceSection id="mayor" office="Mayor" isHeroRace
      candidates={[disputed, other]} financeCoverage={{ [disputed.id]: coverage }} electionSlug="2026-primary" />)
    expect(html).toContain('Zed candidate')
    expect(html).toContain('Amy candidate')
    expect(html).toContain('60,365')
    expect(html).toContain('not primary-only totals')
    expect(html.match(/href="\/elections\/2026-general\/money\/ahmad-anderson"/g)).toHaveLength(2)
    expect(html).not.toMatch(/73,300|161 donors|has raised|follows with/)
    const roster = html.slice(html.indexOf('<ul'), html.indexOf('</ul>'))
    expect(roster.indexOf('Amy candidate')).toBeLessThan(roster.indexOf('Zed candidate'))
    const cards = html.slice(html.indexOf('<article'))
    expect(cards.indexOf('Amy candidate')).toBeLessThan(cards.indexOf('Zed candidate'))
  })

  it('also suppresses an unopposed candidate total while retaining the source summary', () => {
    const disputed = candidate('Ahmad J. Anderson', 73300)
    const html = renderToStaticMarkup(<RaceSection id="mayor" office="Mayor" candidates={[disputed]}
      financeCoverage={{ [disputed.id]: coverage }} />)
    expect(html).toContain('running unopposed')
    expect(html).toContain('dated campaign-money summary')
    expect(html).not.toMatch(/73,300|161 donors|Committee has raised/)
  })
})
