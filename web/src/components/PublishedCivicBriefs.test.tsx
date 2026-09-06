import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
const mocked = vi.hoisted(() => ({ getPublishedCivicBriefs: vi.fn() }))
vi.mock('@/lib/queries/civic-briefs', () => mocked)
import PublishedCivicBriefs from './PublishedCivicBriefs'

describe('public review attribution', () => {
  it('describes source checking without asserting human review or exposing actor metadata', async () => {
    mocked.getPublishedCivicBriefs.mockResolvedValue([{
      id: '11111111-1111-4111-8111-111111111111', title: 'A reviewed update', body: 'A source-linked explanation.',
      published_at: '2026-09-01T12:00:00Z', content_version: 2,
      sources: [{ url: 'https://www.richmondca.gov/Archive.aspx?ADID=17785', title: 'Official resolution', source_tier: 1, source_date: '2026-07-21' }],
      published_by: 'private-test-actor',
    }])
    const html = renderToStaticMarkup(await PublishedCivicBriefs({ subjectKey: '2026-general' }))
    expect(html).toContain('AI-written; checked against linked sources')
    expect(html).toContain('version 2')
    expect(html).toContain('https://www.richmondca.gov/Archive.aspx?ADID=17785')
    expect(html).not.toMatch(/operator-reviewed|human-reviewed|private-test-actor/)
  })
})
