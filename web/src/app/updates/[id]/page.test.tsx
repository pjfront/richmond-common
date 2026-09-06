import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
const mocked = vi.hoisted(() => ({ getPublishedCivicBriefVersion: vi.fn() }))
vi.mock('@/lib/queries/civic-briefs', () => mocked)
import PublishedUpdatePage from './page'

const id = '11111111-1111-4111-8111-111111111111'
const props = { params: Promise.resolve({ id }), searchParams: Promise.resolve({ version: '2', published: '2026-09-01T12:00:00Z' }) }
describe('reviewed update destination', () => {
  beforeEach(() => vi.clearAllMocks())
  it('renders the exact publication and source with a route back to its followed subject', async () => {
    mocked.getPublishedCivicBriefVersion.mockResolvedValue({
      id, subject_key: '2026-general', title: 'A reviewed update', body: 'The source reports a proposal, not adoption.',
      sources: [{ url: 'https://www.richmondca.gov/Archive.aspx?ADID=17785', title: 'Official resolution', source_tier: 1, source_date: '2026-07-21' }],
      content_version: 2, published_at: '2026-09-01T12:00:00Z',
    })
    const html = renderToStaticMarkup(await PublishedUpdatePage(props))
    expect(mocked.getPublishedCivicBriefVersion).toHaveBeenCalledWith(id, '2', '2026-09-01T12:00:00Z')
    expect(html).toContain(`id="brief-${id}-v2"`)
    expect(html).toContain('AI-written; checked against linked sources')
    expect(html).not.toMatch(/operator-reviewed|human-reviewed/)
    expect(html).toContain('proposal, not adoption')
    expect(html).toContain('href="/elections/2026-general"')
    expect(html).toContain('href="https://www.richmondca.gov/Archive.aspx?ADID=17785"')
  })
  it('explains withdrawn or replaced publications without substituting current text', async () => {
    mocked.getPublishedCivicBriefVersion.mockResolvedValue(null)
    const html = renderToStaticMarkup(await PublishedUpdatePage(props))
    expect(html).toContain('This exact publication is no longer available')
    expect(html).toContain('original sources remain linked in your email')
    expect(html).not.toContain('AI-written; checked against linked sources')
  })
  it('distinguishes a temporary source failure from an unavailable publication', async () => {
    mocked.getPublishedCivicBriefVersion.mockRejectedValue(new Error('timeout'))
    const html = renderToStaticMarkup(await PublishedUpdatePage(props))
    expect(html).toContain('could not be loaded')
    expect(html).not.toContain('withdrawn')
  })
})
