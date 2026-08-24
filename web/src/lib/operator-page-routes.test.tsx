import type { ReactNode } from 'react'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const PAGE_NOT_FOUND = new Error('NEXT_HTTP_ERROR_FALLBACK;404')

const mocks = vi.hoisted(() => ({
  requireOperatorPage: vi.fn(),
  getElectionBySlug: vi.fn(),
  getElectionWithCandidates: vi.fn(),
  getAllFinancialConnectionSummaries: vi.fn(),
  getCandidateFundraisingDetails: vi.fn(),
  getOfficialWithStats: vi.fn(),
  getFullCandidateDonors: vi.fn(),
  getMostCommentedVotes: vi.fn(),
  getFilingPeriodBriefing: vi.fn(),
  computeAlignmentStats: vi.fn(),
  getElections: vi.fn(),
  getElectionFundraisingSummary: vi.fn(),
}))

vi.mock('@/lib/operator-page', () => ({
  requireOperatorPage: mocks.requireOperatorPage,
}))

vi.mock('@/lib/queries', () => ({
  getElectionBySlug: mocks.getElectionBySlug,
  getElectionWithCandidates: mocks.getElectionWithCandidates,
  getAllFinancialConnectionSummaries: mocks.getAllFinancialConnectionSummaries,
  getCandidateFundraisingDetails: mocks.getCandidateFundraisingDetails,
  getOfficialWithStats: mocks.getOfficialWithStats,
  getFullCandidateDonors: mocks.getFullCandidateDonors,
  getMostCommentedVotes: mocks.getMostCommentedVotes,
  getFilingPeriodBriefing: mocks.getFilingPeriodBriefing,
  computeAlignmentStats: mocks.computeAlignmentStats,
  officialToSlug: (name: string) => name.toLowerCase().replace(/\s+/g, '-'),
  getElections: mocks.getElections,
  getElectionFundraisingSummary: mocks.getElectionFundraisingSummary,
}))

vi.mock('@/components/OperatorGate', () => ({
  default: ({ children }: { children: ReactNode }) => children,
}))

vi.mock('@/components/FinancialConnectionsAllTable', () => ({
  default: () => null,
}))

vi.mock('@/components/FilingPeriodBriefingSection', () => ({
  default: () => null,
}))

vi.mock('@/components/SuggestCorrectionLink', () => ({
  default: () => null,
}))

vi.mock('@/app/elections/[slug]/candidates/[candidateSlug]/DonorSection', () => ({
  default: () => null,
}))

vi.mock('@/app/elections/[slug]/candidates/[candidateSlug]/VotedItemCard', () => ({
  default: () => null,
}))

import FinancialConnectionsPage from '@/app/financial-connections/page'
import CandidateProfilePage, {
  generateMetadata as generateCandidateMetadata,
} from '@/app/elections/[slug]/candidates/[candidateSlug]/page'
import InfluenceIndexPage from '@/app/influence/page'
import InfluenceElectionsIndexPage from '@/app/influence/elections/page'
import InfluenceElectionDetailPage, {
  generateMetadata as generateInfluenceElectionMetadata,
} from '@/app/influence/elections/[id]/page'

const candidatePageProps = {
  params: Promise.resolve({
    slug: '2026-primary',
    candidateSlug: 'claudia-jimenez',
  }),
}

const influenceElectionProps = {
  params: Promise.resolve({ id: 'election-1' }),
}

describe('operator page query containment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.requireOperatorPage.mockResolvedValue(undefined)
  })

  it('rejects the heavy financial-connections route before its query', async () => {
    mocks.requireOperatorPage.mockRejectedValue(PAGE_NOT_FOUND)

    await expect(FinancialConnectionsPage()).rejects.toBe(PAGE_NOT_FOUND)

    expect(mocks.getAllFinancialConnectionSummaries).not.toHaveBeenCalled()
  })

  it('allows a proven operator to reach the heavy financial-connections query', async () => {
    mocks.getAllFinancialConnectionSummaries.mockResolvedValue([])

    await expect(FinancialConnectionsPage()).resolves.toBeDefined()

    expect(mocks.getAllFinancialConnectionSummaries).toHaveBeenCalledOnce()
    expect(mocks.requireOperatorPage.mock.invocationCallOrder[0]).toBeLessThan(
      mocks.getAllFinancialConnectionSummaries.mock.invocationCallOrder[0],
    )
  })

  it('rejects an anonymous candidate page and metadata before resolution queries', async () => {
    mocks.requireOperatorPage.mockRejectedValue(PAGE_NOT_FOUND)

    await expect(CandidateProfilePage(candidatePageProps)).rejects.toBe(
      PAGE_NOT_FOUND,
    )
    await expect(generateCandidateMetadata(candidatePageProps)).rejects.toBe(
      PAGE_NOT_FOUND,
    )

    expect(mocks.getElectionBySlug).not.toHaveBeenCalled()
    expect(mocks.getCandidateFundraisingDetails).not.toHaveBeenCalled()
    expect(mocks.getOfficialWithStats).not.toHaveBeenCalled()
    expect(mocks.getFullCandidateDonors).not.toHaveBeenCalled()
    expect(mocks.getMostCommentedVotes).not.toHaveBeenCalled()
    expect(mocks.getFilingPeriodBriefing).not.toHaveBeenCalled()
  })

  it('rejects anonymous influence route entry points before their queries', async () => {
    mocks.requireOperatorPage.mockRejectedValue(PAGE_NOT_FOUND)

    await expect(InfluenceIndexPage()).rejects.toBe(PAGE_NOT_FOUND)
    await expect(InfluenceElectionsIndexPage()).rejects.toBe(PAGE_NOT_FOUND)
    await expect(InfluenceElectionDetailPage(influenceElectionProps)).rejects.toBe(
      PAGE_NOT_FOUND,
    )
    await expect(
      generateInfluenceElectionMetadata(influenceElectionProps),
    ).rejects.toBe(PAGE_NOT_FOUND)

    expect(mocks.getAllFinancialConnectionSummaries).not.toHaveBeenCalled()
    expect(mocks.getElections).not.toHaveBeenCalled()
    expect(mocks.getElectionWithCandidates).not.toHaveBeenCalled()
    expect(mocks.getElectionFundraisingSummary).not.toHaveBeenCalled()
  })
})

const containedRoutes = [
  '../app/data-quality/page.tsx',
  '../app/elections/[slug]/candidates/[candidateSlug]/page.tsx',
  '../app/financial-connections/page.tsx',
  '../app/influence/page.tsx',
  '../app/influence/elections/page.tsx',
  '../app/influence/elections/[id]/page.tsx',
]

const metadataQueryRoutes = [
  '../app/elections/[slug]/candidates/[candidateSlug]/page.tsx',
  '../app/influence/elections/[id]/page.tsx',
]

function routeSource(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8')
}

function expectAuthBeforeFirstQuery(source: string): void {
  const authAt = source.indexOf('await requireOperatorPage()')
  const firstQueryAt = source.search(/\bget[A-Z]\w*\s*\(/)

  expect(authAt).toBeGreaterThanOrEqual(0)
  if (firstQueryAt >= 0) expect(authAt).toBeLessThan(firstQueryAt)
}

describe('operator page containment registry', () => {
  it.each(containedRoutes)(
    'guards and noindexes %s before its first page query',
    (relativePath) => {
      const source = routeSource(relativePath)
      const pageSource = source.slice(source.indexOf('export default'))

      expect(source).toContain("import { requireOperatorPage } from '@/lib/operator-page'")
      expect(source).toContain('robots: { index: false, follow: false }')
      expectAuthBeforeFirstQuery(pageSource)
    },
  )

  it.each(metadataQueryRoutes)(
    'guards %s metadata before its first query',
    (relativePath) => {
      const source = routeSource(relativePath)
      const metadataStart = source.indexOf('export async function generateMetadata')
      const pageStart = source.indexOf('export default', metadataStart)
      const metadataSource = source.slice(metadataStart, pageStart)

      expect(metadataStart).toBeGreaterThanOrEqual(0)
      expectAuthBeforeFirstQuery(metadataSource)
    },
  )
})
