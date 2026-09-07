import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { JIMENEZ_FINANCE } from '@/lib/jimenez-finance'

const mocks = vi.hoisted(() => ({
  official: vi.fn(), contributions: vi.fn(), coverage: vi.fn(), comparative: vi.fn(), electionDates: vi.fn(),
}))
vi.mock('@/lib/queries', () => ({
  getOfficialBySlug: mocks.official,
  getOfficialWithStats: async () => null,
  getOfficialVotingRecord: async () => [],
  getOfficialContributions: mocks.contributions,
  getOfficialElectionHistory: async () => [],
  getOfficialComparativeStats: mocks.comparative,
  getPastElectionDates: mocks.electionDates,
}))
vi.mock('@/lib/queries/candidate-filing-coverage', () => ({ getJimenezFilingCoverage: mocks.coverage }))
vi.mock('@/components/BioSummary', () => ({ default: () => null }))
vi.mock('@/components/VotingRecordTable', () => ({ default: () => null }))
vi.mock('@/components/OperatorGate', () => ({ default: () => null }))
vi.mock('@/components/SuggestCorrectionLink', () => ({ default: () => null }))

import CouncilMemberPage from './page'

describe('council profile campaign identity and date boundaries', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.official.mockResolvedValue({ id: JIMENEZ_FINANCE.identity.official_id, name: 'Claudia Jimenez', role: 'councilmember', is_current: true })
    mocks.coverage.mockResolvedValue(undefined)
    mocks.contributions.mockResolvedValue([
      { donor_name: 'Paul Moore', donor_employer: null, donor_pattern: null, amount: 335, contribution_date: '2025-01-05', source: 'city_clerk' },
    ])
  })

  it('shows checked mayoral finances separately from dated council receipts even without election-history rows', async () => {
    const html = renderToStaticMarkup(await CouncilMemberPage({ params: Promise.resolve({ slug: 'claudia-jimenez' }) }))
    expect(html).toContain('2026 campaign for mayor')
    expect(html).toContain('$60,365')
    expect(html).toContain('Jan 1–Jun 30, 2026')
    expect(html).toContain('Council campaign donation records')
    expect(html).toContain('$335')
    expect(html).toContain('Jan 5, 2025')
    expect(html).not.toContain('2026 Election')
    expect(html).not.toContain('ranked')
    expect(mocks.coverage).toHaveBeenCalledOnce()
    expect(mocks.comparative).not.toHaveBeenCalled()
    expect(mocks.electionDates).not.toHaveBeenCalled()
  })

  it('does not assign mayoral money by a similar name or fetch its source coverage for another official', async () => {
    mocks.official.mockResolvedValue({ id: 'different-official', name: 'Claudia Jimenez', role: 'councilmember', is_current: false })
    const html = renderToStaticMarkup(await CouncilMemberPage({ params: Promise.resolve({ slug: 'similar-name' }) }))
    expect(html).not.toContain('Jimenez campaign finances')
    expect(html).not.toContain('$60,365')
    expect(mocks.coverage).not.toHaveBeenCalled()
  })
})
