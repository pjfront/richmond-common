import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'

const mocks = vi.hoisted(() => ({ getPromotedTopics: vi.fn(), getTopicItems: vi.fn() }))
vi.mock('@/lib/queries', () => mocks)
import Page from './page'

describe('topic record scope', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getPromotedTopics.mockResolvedValue([{ slug: 'housing', label: 'Housing', meeting_count: 80 }])
  })

  it('counts distinct meetings on the same date and discloses the bounded list', async () => {
    mocks.getTopicItems.mockResolvedValue(['m1', 'm1', 'm2'].map((meeting_id, index) => ({
      id: `item-${index}`, meeting_id, meeting_date: '2026-09-01', item_number: String(index),
      title: 'Housing item', category: null, summary_headline: 'Housing summary',
      public_comment_count: 999, financial_amount: '$1 billion',
    })))
    const html = renderToStaticMarkup(await Page({ params: Promise.resolve({ slug: 'housing' }) }))
    expect(html).toContain('Showing 3 tagged agenda entries from 2 recorded meetings.')
    expect(html).toContain('up to 100 of the newest entries')
    expect(html).toContain('Topic tags and summaries are AI-generated')
    expect(html).not.toContain('999')
    expect(html).not.toContain('$1 billion')
    expect(mocks.getTopicItems).toHaveBeenCalledWith('Housing', 100)
  })
})
