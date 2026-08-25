import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocked = vi.hoisted(() => ({
  findSimilarItems: vi.fn(),
  getOfficialBySlug: vi.fn(),
  getOfficialWithStats: vi.fn(),
  getOfficialVotingRecord: vi.fn(),
  getOfficialContributions: vi.fn(),
  getPastElectionDates: vi.fn(),
  getOfficialComparativeStats: vi.fn(),
  getOfficialElectionHistory: vi.fn(),
  getAgendaItemDetail: vi.fn(),
  getPACListWithCycleBars: vi.fn(),
  getCompleteOrgList: vi.fn(),
}))

vi.mock('@/lib/queries', () => mocked)

vi.mock('next/navigation', () => ({
  useSearchParams: vi.fn(() => new URLSearchParams()),
  notFound: vi.fn(() => {
    throw new Error('NEXT_NOT_FOUND')
  }),
}))

import CouncilMemberPage, {
  dynamic as councilDynamic,
  revalidate as councilRevalidate,
} from '@/app/council/[slug]/page'
import SimilarDiscussions from '@/components/SimilarDiscussions'
import AgendaItemDetailPage, {
  dynamic as agendaItemDynamic,
  revalidate as agendaItemRevalidate,
} from '@/app/meetings/[id]/items/[itemNumber]/page'
import PACIndexPage from '@/app/pac/page'
import UnionsPage from '@/app/unions/page'

describe('force-static read-path error propagation', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocked.getOfficialBySlug.mockResolvedValue({ id: 'official-1' })
    mocked.getOfficialWithStats.mockResolvedValue(null)
    mocked.getOfficialContributions.mockResolvedValue([])
    mocked.getPastElectionDates.mockResolvedValue([])
    mocked.getOfficialComparativeStats.mockResolvedValue(null)
    mocked.getOfficialElectionHistory.mockResolvedValue([])
  })

  it('keeps the council route static while letting voting failures abort the render', async () => {
    const failure = new Error('transient voting timeout')
    mocked.getOfficialVotingRecord.mockRejectedValue(failure)

    await expect(CouncilMemberPage({
      params: Promise.resolve({ slug: 'test-official' }),
    })).rejects.toBe(failure)

    expect(councilDynamic).toBe('force-static')
    expect(councilRevalidate).toBe(86_400)
  })

  it('lets similar-item failures abort the static parent render', async () => {
    const failure = new Error('transient similarity timeout')
    mocked.findSimilarItems.mockRejectedValue(failure)

    await expect(SimilarDiscussions({ itemId: 'item-1' })).rejects.toBe(failure)
  })

  it('keeps the agenda-item route static while letting detail failures abort the render', async () => {
    const failure = new Error('transient related-topic timeout')
    mocked.getAgendaItemDetail.mockRejectedValue(failure)

    await expect(AgendaItemDetailPage({
      params: Promise.resolve({
        id: '11111111-1111-4111-8111-111111111111',
        itemNumber: 'A.1',
      }),
    })).rejects.toBe(failure)

    expect(agendaItemDynamic).toBe('force-static')
    expect(agendaItemRevalidate).toBe(86_400)
  })

  it('lets PAC-directory query failures abort ISR refreshes', async () => {
    const failure = new Error('transient PAC timeout')
    mocked.getPACListWithCycleBars.mockRejectedValue(failure)

    await expect(PACIndexPage()).rejects.toBe(failure)
  })

  it('lets union-directory query failures abort ISR refreshes', async () => {
    const failure = new Error('transient union timeout')
    mocked.getCompleteOrgList.mockRejectedValue(failure)

    await expect(UnionsPage()).rejects.toBe(failure)
  })
})
