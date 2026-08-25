import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocked = vi.hoisted(() => ({
  findSimilarItems: vi.fn(),
}))

vi.mock('@/lib/queries', () => mocked)

import SimilarDiscussions from './SimilarDiscussions'

describe('SimilarDiscussions', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('renders no empty related-content block when there are no semantic neighbors', async () => {
    mocked.findSimilarItems.mockResolvedValue([])

    await expect(SimilarDiscussions({ itemId: 'item-1' })).resolves.toBeNull()
    expect(mocked.findSimilarItems).toHaveBeenCalledWith('item-1', { limit: 5 })
  })
})
