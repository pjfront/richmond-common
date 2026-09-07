import type { ReactNode } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CandidateFundraisingDetail } from '@/lib/types'

const operatorState = vi.hoisted(() => ({ isOperator: false }))

vi.mock('./OperatorGate', () => ({
  default: ({
    children,
    fallback = null,
  }: {
    children: ReactNode
    fallback?: ReactNode
  }) => operatorState.isOperator ? children : fallback,
}))

vi.mock('@/lib/queries/_shared', () => ({
  officialToSlug: (name: string) => name.toLowerCase().replace(/\s+/g, '-'),
}))

vi.mock('./CandidateContributionBuckets', () => ({
  default: () => null,
}))

import CandidateCard from './CandidateCard'

const candidate = {
  id: 'candidate-1',
  candidate_name: 'Claudia Jimenez',
  office_sought: 'Mayor',
  is_incumbent: false,
  status: 'qualified',
  total_raised: 0,
  contribution_count: 0,
  donor_count: 0,
  avg_contribution: 0,
  largest_contribution: 0,
  smallest_contribution: 0,
  committee_id: null,
  official_id: null,
  top_donors: [],
  contribution_matrix: {
    cells: {
      individual: {
        under_100: { count: 0, dollars: 0 },
        between_100_249: { count: 0, dollars: 0 },
        between_250_999: { count: 0, dollars: 0 },
        between_1000_2499: { count: 0, dollars: 0 },
        at_2500_cap: { count: 0, dollars: 0 },
      },
      business: {
        under_100: { count: 0, dollars: 0 },
        between_100_249: { count: 0, dollars: 0 },
        between_250_999: { count: 0, dollars: 0 },
        between_1000_2499: { count: 0, dollars: 0 },
        at_2500_cap: { count: 0, dollars: 0 },
      },
      union: {
        under_100: { count: 0, dollars: 0 },
        between_100_249: { count: 0, dollars: 0 },
        between_250_999: { count: 0, dollars: 0 },
        between_1000_2499: { count: 0, dollars: 0 },
        at_2500_cap: { count: 0, dollars: 0 },
      },
      pac: {
        under_100: { count: 0, dollars: 0 },
        between_100_249: { count: 0, dollars: 0 },
        between_250_999: { count: 0, dollars: 0 },
        between_1000_2499: { count: 0, dollars: 0 },
        at_2500_cap: { count: 0, dollars: 0 },
      },
    },
    total_count: 0,
    total_dollars: 0,
  },
  bucket_grid_consistent: true,
  earliest_contribution: null,
  latest_contribution: null,
  lifetime_raised: 0,
} satisfies CandidateFundraisingDetail

describe('CandidateCard detail link containment', () => {
  beforeEach(() => {
    operatorState.isOperator = false
  })

  it('links residents to the stable candidate anchor on the canonical election page', () => {
    const markup = renderToStaticMarkup(
      <CandidateCard candidate={candidate} electionSlug="2026-primary" />,
    )

    expect(markup).toContain('Claudia Jimenez')
    expect(markup).toContain(
      'href="/elections/2026-primary#claudia-jimenez"',
    )
    expect(markup).toContain(
      'aria-label="Claudia Jimenez on this election page"',
    )
    expect(markup).toContain('id="claudia-jimenez"')
    expect(markup).toContain('aria-labelledby="claudia-jimenez-name"')
    expect(markup).not.toContain('/elections/2026-primary/candidates/claudia-jimenez')
  })

  it('retains the exact candidate-detail link for operators', () => {
    operatorState.isOperator = true

    const markup = renderToStaticMarkup(
      <CandidateCard candidate={candidate} electionSlug="2026-primary" />,
    )

    expect(markup).toContain(
      'href="/elections/2026-primary/candidates/claudia-jimenez"',
    )
    expect(markup).not.toContain(
      'href="/elections/2026-primary#claudia-jimenez"',
    )
    expect(markup).toContain('inline-flex min-h-11 items-center')
    expect(markup).toContain('Claudia Jimenez')
  })

  it.each([false, true])('replaces disputed statistics with the scoped summary (operator: %s)', (isOperator) => {
    operatorState.isOperator = isOperator
    const markup = renderToStaticMarkup(
      <CandidateCard
        candidate={{ ...candidate, candidate_name: 'Ahmad J. Anderson', total_raised: 73300,
          donor_count: 161, contribution_count: 198, avg_contribution: 370,
          largest_contribution: 9140, lifetime_raised: 73300, bucket_grid_consistent: false }}
        electionSlug="2026-primary"
        financeCoverage={{ kind: 'source-checked-summary',
          href: '/elections/2026-general/money/ahmad-anderson',
          scopeNote: 'Includes reports after this primary; not primary-only totals.' }}
      />,
    )
    expect(markup).toContain('Ahmad J. Anderson')
    expect(markup).toContain('reported donations, cash balance and spending')
    expect(markup).toContain('not primary-only totals')
    expect(markup).toContain('href="/elections/2026-general/money/ahmad-anderson"')
    for (const invalidClaim of ['73,300', '161', '198 contributions', '370', '9,140', 'Usually', 'No campaign finance']) {
      expect(markup).not.toContain(invalidClaim)
    }
  })
})
