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
}))

vi.mock('@/lib/queries', () => mocked)

vi.mock('next/navigation', () => ({
  notFound: vi.fn(() => {
    throw new Error('NEXT_NOT_FOUND')
  }),
}))

import CouncilMemberPage, {
  dynamic as councilDynamic,
  revalidate as councilRevalidate,
} from '@/app/council/[slug]/page'
import SimilarDiscussions from '@/components/SimilarDiscussions'

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
})
