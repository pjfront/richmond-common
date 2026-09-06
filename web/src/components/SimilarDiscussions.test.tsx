import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

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

  it('does not publish aggregated item outcomes or turn similarity into a confidence percentage', async () => {
    mocked.findSimilarItems.mockResolvedValue([{ id: 'neighbor-1', meeting_id: 'meeting-2', item_number: 'O.1', meeting_date: '2026-06-23', title: 'Consider the operating budget', summary_headline: 'Budget was defeated', vote_outcome: 'failed', similarity: 0.89, public_comment_count: 3 }])
    const html = renderToStaticMarkup((await SimilarDiscussions({ itemId: 'item-1' }))!)
    expect(html).toContain('Consider the operating budget')
    expect(html).toContain('/meetings/meeting-2/items/o.1')
    expect(html).toContain('each motion’s outcome')
    expect(html).not.toContain('Failed')
    expect(html).not.toContain('Budget was defeated')
    expect(html).not.toContain('89%')
  })
})
