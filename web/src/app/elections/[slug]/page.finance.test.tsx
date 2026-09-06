import { renderToReadableStream } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CandidateFinanceCoverageById } from '@/components/CandidateCard'

const state = vi.hoisted(() => ({ candidates: [] as { id: string; candidate_name: string; office_sought: string }[] }))
vi.mock('@/lib/queries', () => ({
  getElectionBySlug: async () => ({ id: 'election', election_name: 'Primary', election_date: '2026-06-02', election_type: 'primary', source_url: null }),
  getElectionWithCandidates: async () => ({ candidates: state.candidates }),
  getCandidateFundraisingDetails: async () => state.candidates,
}))
vi.mock('@/components/NovemberElection', () => ({ default: () => <div>November guide</div> }))
vi.mock('@/components/RaceSection', () => ({
  default: ({ office, financeCoverage }: { office: string; financeCoverage: CandidateFinanceCoverageById }) => (
    <div data-office={office}>{JSON.stringify(financeCoverage)}</div>
  ),
}))
vi.mock('@/lib/s29-release-phase', () => ({ S29_PUBLIC_TREATMENT_ENABLED: false }))

import ElectionPage from './page'

async function renderPage(slug: string) {
  const stream = await renderToReadableStream(await ElectionPage({ params: Promise.resolve({ slug }) }))
  return new Response(stream).text()
}

describe('primary finance-summary identity scope', () => {
  beforeEach(() => { state.candidates = [] })

  it.each(['Ahmad J. Anderson', 'Ahmad Anderson'])('routes the exact verified mayor spelling %s to the dated summary', async (name) => {
    state.candidates = [{ id: 'anderson', candidate_name: name, office_sought: 'Mayor' }]
    const html = await renderPage('2026-primary')
    expect(html).toContain('/elections/2026-general/money/ahmad-anderson')
    expect(html).toContain('not primary-only totals')
    expect(html).not.toMatch(/73,300|54,303/)
  })

  it('does not assign the override by surname alone or to another office or election', async () => {
    state.candidates = [{ id: 'other-anderson', candidate_name: 'Other Anderson', office_sought: 'Mayor' },
      { id: 'other-office', candidate_name: 'Ahmad Anderson', office_sought: 'City Council District 3' }]
    expect(await renderPage('2026-primary')).not.toContain('/money/ahmad-anderson')
    state.candidates = [{ id: 'anderson', candidate_name: 'Ahmad Anderson', office_sought: 'Mayor' }]
    expect(await renderPage('2024-primary')).not.toContain('/money/ahmad-anderson')
  })
})
