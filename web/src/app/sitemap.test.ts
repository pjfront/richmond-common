import { beforeEach, describe, expect, it, vi } from 'vitest'

const queryMocks = vi.hoisted(() => ({
  getMeetings: vi.fn(),
  getAgendaItemSlugs: vi.fn(),
  getOfficials: vi.fn(),
  getElections: vi.fn(),
  getPromotedTopics: vi.fn(),
}))

vi.mock('@/lib/queries', () => ({
  ...queryMocks,
  electionToSlug: (election: { election_date: string; election_type: string }) =>
    `${election.election_date.slice(0, 4)}-${election.election_type}`,
}))

import sitemap, { PUBLIC_STATIC_PATHS } from './sitemap'

describe('public sitemap', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryMocks.getMeetings.mockResolvedValue([
      { id: 'meeting-1', meeting_date: '2026-08-01' },
    ])
    queryMocks.getAgendaItemSlugs.mockResolvedValue([
      { meeting_id: 'meeting-1', item_number: 'CC-1', meeting_date: '2026-08-01' },
    ])
    queryMocks.getOfficials.mockResolvedValue([{ name: 'Example Member' }])
    queryMocks.getElections.mockResolvedValue([{
      election_date: '2026-11-03',
      election_type: 'general',
      updated_at: '2026-08-02T00:00:00Z',
    }])
    queryMocks.getPromotedTopics.mockResolvedValue([{
      slug: 'housing',
      latest_meeting_date: '2026-08-03',
    }])
  })

  it('includes stable public indexes and their bounded dynamic pages', async () => {
    const urls = (await sitemap()).map((entry) => entry.url)

    for (const path of PUBLIC_STATIC_PATHS) {
      expect(urls).toContain(
        path === '/'
          ? 'https://richmondcommons.org'
          : `https://richmondcommons.org${path}`,
      )
    }
    expect(urls).toContain('https://richmondcommons.org/meetings/meeting-1')
    expect(urls).toContain('https://richmondcommons.org/meetings/meeting-1/items/cc-1')
    expect(urls).toContain('https://richmondcommons.org/council/example-member')
    expect(urls).toContain('https://richmondcommons.org/elections/2026-general')
    expect(urls).toContain('https://richmondcommons.org/topics/housing')
  })

  it('does not expose gated, tokenized, search, redirect, or unpublished routes', async () => {
    const urls = (await sitemap()).map((entry) => new URL(entry.url).pathname)
    const excludedTrees = [
      '/search',
      '/operator',
      '/subscribe/manage',
      '/commissions',
      '/public-records',
      '/council/analytics',
      '/influence',
      '/richmond-101',
    ]

    for (const path of excludedTrees) {
      expect(urls.some((url) => url === path || url.startsWith(`${path}/`))).toBe(false)
    }
    expect(urls).not.toContain('/elections')
  })
})
