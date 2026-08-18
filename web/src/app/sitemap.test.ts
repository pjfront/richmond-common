import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const queryMocks = vi.hoisted(() => ({
  getSitemapMeetingsPage: vi.fn(),
  getSitemapAgendaItemsPage: vi.fn(),
  getSitemapOfficialsPage: vi.fn(),
  getSitemapElectionsPage: vi.fn(),
  getPromotedTopics: vi.fn(),
}))

vi.mock('@/lib/queries', () => ({
  ...queryMocks,
  electionToSlug: (election: { election_date: string; election_type: string }) =>
    `${election.election_date.slice(0, 4)}-${election.election_type}`,
}))

import sitemap, {
  agendaItemSitemapCutoffUtc,
  buildSitemap,
  collectPaginated,
  MAX_AGENDA_ITEM_SITEMAP_ROWS,
  PUBLIC_STATIC_PATHS,
} from './sitemap'

describe('public sitemap', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryMocks.getSitemapMeetingsPage.mockResolvedValue([
      { id: 'meeting-1', meeting_date: '2026-08-01' },
    ])
    queryMocks.getSitemapAgendaItemsPage.mockResolvedValue([
      { meeting_id: 'meeting-1', item_number: 'CC-1', meeting_date: '2026-08-01' },
    ])
    queryMocks.getSitemapOfficialsPage.mockResolvedValue([{ name: 'Example Member' }])
    queryMocks.getSitemapElectionsPage.mockResolvedValue([{
      election_date: '2026-11-03',
      election_type: 'general',
      updated_at: '2026-08-02T00:00:00Z',
    }])
    queryMocks.getPromotedTopics.mockResolvedValue([{
      slug: 'housing',
      latest_meeting_date: '2026-08-03',
    }])
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
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

  it('requests another database page when PostgREST returns a full page', async () => {
    const firstPage = Array.from({ length: 1_000 }, (_, index) => index)
    const loader = vi.fn(async (from: number) => (
      from === 0 ? firstPage : [1_000]
    ))

    const rows = await collectPaginated(loader)

    expect(rows).toHaveLength(1_001)
    expect(loader).toHaveBeenNthCalledWith(1, 0, 999)
    expect(loader).toHaveBeenNthCalledWith(2, 1_000, 1_999)
  })

  it('uses an injected UTC date for the inclusive rolling 24-month item cutoff', async () => {
    await buildSitemap(new Date('2026-08-18T23:30:00-07:00'))

    expect(queryMocks.getSitemapAgendaItemsPage).toHaveBeenCalledWith(
      0,
      999,
      '2024-08-19',
    )
  })

  it('clamps a leap-day cutoff to the last UTC day of the target month', () => {
    expect(agendaItemSitemapCutoffUtc(new Date('2024-02-29T12:00:00Z')))
      .toBe('2022-02-28')
  })

  it('fails closed before a rolling item sitemap can reach 10,000 rows', async () => {
    const fullPage = Array.from({ length: 1_000 }, (_, index) => ({
      meeting_id: `meeting-${index}`,
      item_number: `CC-${index}`,
      meeting_date: '2026-08-01',
    }))
    queryMocks.getSitemapAgendaItemsPage.mockResolvedValue(fullPage)

    await expect(buildSitemap(new Date('2026-08-18T00:00:00Z')))
      .rejects.toThrow(
        `Rolling agenda-item sitemap dataset reached ${MAX_AGENDA_ITEM_SITEMAP_ROWS.toLocaleString('en-US')} rows`,
      )
    expect(queryMocks.getSitemapAgendaItemsPage).toHaveBeenCalledTimes(10)
  })

  it('keeps stable routes when the explicitly inert CI database is unavailable', async () => {
    vi.stubEnv('RICHMOND_BUILD_USES_PRODUCTION_DATA', 'false')
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    queryMocks.getSitemapMeetingsPage.mockRejectedValue(new Error('inert database'))

    const urls = (await sitemap()).map((entry) => entry.url)

    expect(urls).toEqual(PUBLIC_STATIC_PATHS.map((path) => (
      path === '/' ? 'https://richmondcommons.org' : `https://richmondcommons.org${path}`
    )))
  })

  it('does not replace a complete production sitemap after a transient query failure', async () => {
    vi.stubEnv('RICHMOND_BUILD_USES_PRODUCTION_DATA', 'true')
    queryMocks.getSitemapMeetingsPage.mockRejectedValue(new Error('temporary outage'))

    await expect(sitemap()).rejects.toThrow('temporary outage')
  })
})
