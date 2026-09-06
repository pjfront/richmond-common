import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { CIVIC_STORIES } from '@/data/civic-stories'
import type { ResidentSnapshot } from '@/lib/queries/civic-stories'

const mocks = vi.hoisted(() => ({ snapshot: vi.fn() }))
vi.mock('@/lib/queries/civic-stories', () => ({ getResidentSnapshot: mocks.snapshot }))
vi.mock('@/components/SuggestCorrectionLink', () => ({ default: () => <button>Suggest a correction</button> }))
import HomePage from '@/app/page'
import StoryPage from '@/app/stories/[slug]/page'
import { StoryAgenda } from './CivicStory'

const unavailable: ResidentSnapshot = { status: 'unavailable', fetchedAt: null, recent: [], upcoming: [], entries: {}, itemLimitReached: false }

describe('resident journeys', () => {
  beforeEach(() => { mocks.snapshot.mockResolvedValue(unavailable) })

  it('keeps the homepage useful during an agenda outage, with election and story paths', async () => {
    const html = renderToStaticMarkup(await HomePage())
    for (const story of CIVIC_STORIES) expect(html).toContain(`/stories/${story.slug}`)
    expect(html).toContain('href="/elections/2026-general"')
    expect(html).toContain('The local calendar could not be loaded')
    expect(html).toContain('AI-written explanations')
    expect(html).toContain('Español')
    expect(html).toContain('ADID=17785')
    expect(html).toContain('ADID=17838')
    expect(html).not.toContain('fundraising total')
  })

  it('shows the exact Flock action and primary minutes while keeping later implementation open', async () => {
    const html = renderToStaticMarkup(await StoryPage({ params: Promise.resolve({ slug: CIVIC_STORIES[2].slug }) }))
    expect(html).toContain('4–3 to direct negotiations')
    expect(html).toContain('do not prove a final contract was signed')
    expect(html).toContain('ArchiveCenter/ViewFile/Item/17557#page=10')
    expect(html).toContain('Tier 1')
    expect(html).toContain('source-coverage gap')
  })

  it('distinguishes successful no-match discovery from failed discovery', () => {
    const html = renderToStaticMarkup(<StoryAgenda story={CIVIC_STORIES[0]} snapshot={{ ...unavailable, status: 'available', fetchedAt: '2026-09-06T20:00:00Z' }} />)
    expect(html).toContain('No matching titles were found')
    expect(html).toContain('Related action may appear under another title')
    expect(html).not.toContain('could not be loaded')
  })
})
