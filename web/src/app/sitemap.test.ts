import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const queryMocks = vi.hoisted(() => ({
  getSitemapMeetings: vi.fn(),
  getRecentAgendaItemSlugs: vi.fn(),
  getSitemapOfficials: vi.fn(),
  getSitemapElections: vi.fn(),
  getSitemapCommissions: vi.fn(),
  getSitemapDonorSlugs: vi.fn(),
  getSitemapOrganizationSlugs: vi.fn(),
  electionToSlug: vi.fn((election: { election_date: string; election_type: string }) => (
    `${election.election_date.slice(0, 4)}-${election.election_type}`
  )),
}))

vi.mock('@/lib/queries/elections', () => ({
  electionToSlug: queryMocks.electionToSlug,
}))

vi.mock('@/lib/queries/sitemap', () => ({
  getSitemapMeetings: queryMocks.getSitemapMeetings,
  getRecentAgendaItemSlugs: queryMocks.getRecentAgendaItemSlugs,
  getSitemapOfficials: queryMocks.getSitemapOfficials,
  getSitemapElections: queryMocks.getSitemapElections,
  getSitemapCommissions: queryMocks.getSitemapCommissions,
  getSitemapDonorSlugs: queryMocks.getSitemapDonorSlugs,
  getSitemapOrganizationSlugs: queryMocks.getSitemapOrganizationSlugs,
}))

import {
  PUBLIC_STATIC_PATHS,
  agendaItemSitemapCutoffUtc,
  buildSitemap,
} from './sitemap'

describe('public sitemap', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryMocks.getSitemapMeetings.mockResolvedValue([])
    queryMocks.getRecentAgendaItemSlugs.mockResolvedValue([])
    queryMocks.getSitemapOfficials.mockResolvedValue([])
    queryMocks.getSitemapElections.mockResolvedValue([])
    queryMocks.getSitemapCommissions.mockResolvedValue([])
    queryMocks.getSitemapDonorSlugs.mockResolvedValue([])
    queryMocks.getSitemapOrganizationSlugs.mockResolvedValue([])
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it('includes public indexes and lightweight dynamic public routes', async () => {
    queryMocks.getSitemapMeetings.mockResolvedValue([
      { id: 'meeting-1', meeting_date: '2026-08-01' },
    ])
    queryMocks.getRecentAgendaItemSlugs.mockResolvedValue([
      { meeting_id: 'meeting-1', item_number: 'CC-1', meeting_date: '2026-08-01' },
    ])
    queryMocks.getSitemapOfficials.mockResolvedValue([{ name: 'Example Member' }])
    queryMocks.getSitemapElections.mockResolvedValue([{
      election_date: '2026-11-03',
      election_type: 'general',
      updated_at: '2026-08-02T00:00:00Z',
    }])
    queryMocks.getSitemapCommissions.mockResolvedValue([{
      id: 'commission-1',
      last_modified: '2026-08-02T00:00:00Z',
    }])
    queryMocks.getSitemapDonorSlugs.mockResolvedValue([{
      slug: 'example-donor',
      created_at: '2026-08-02T00:00:00Z',
    }])
    queryMocks.getSitemapOrganizationSlugs.mockResolvedValue([{
      slug: 'example-union',
      created_at: '2026-08-02T00:00:00Z',
    }])

    const sitemap = await buildSitemap(new Date('2026-08-18T00:00:00Z'))
    const urls = sitemap.map((entry) => entry.url)

    for (const path of PUBLIC_STATIC_PATHS) {
      expect(urls).toContain(
        path === '/'
          ? 'https://richmondcommons.org'
          : `https://richmondcommons.org${path}`,
      )
    }
    expect(urls).toContain('https://richmondcommons.org/meetings/meeting-1')
    expect(urls).toContain(
      'https://richmondcommons.org/meetings/meeting-1/items/cc-1',
    )
    expect(urls).toContain('https://richmondcommons.org/council/example-member')
    expect(urls).toContain('https://richmondcommons.org/elections/2026-general')
    expect(urls).toContain('https://richmondcommons.org/commissions/commission-1')
    expect(urls).toContain('https://richmondcommons.org/donors/example-donor')
    expect(urls).toContain('https://richmondcommons.org/orgs/example-union')
    expect(urls.every((url) => new URL(url).origin === 'https://richmondcommons.org'))
      .toBe(true)
    expect(sitemap.find((entry) => entry.url.endsWith('/meetings/meeting-1')))
      .not.toHaveProperty('lastModified')
    expect(sitemap.find((entry) => entry.url.endsWith('/items/cc-1')))
      .toHaveProperty('lastModified', '2026-08-01')
  })

  it('excludes redirects, sensitive routes, and every ungraduated/noindex tree', async () => {
    const paths = (await buildSitemap(new Date('2026-08-18T00:00:00Z')))
      .map((entry) => new URL(entry.url).pathname)

    expect(paths).not.toContain('/elections')
    expect(paths).not.toContain('/orgs')
    expect(paths).not.toContain('/search')
    expect(paths).not.toContain('/subscribe/manage')
    expect(paths).not.toContain('/data-quality')
    expect(paths).not.toContain('/financial-connections')
    expect(paths).not.toContain('/influence')
    expect(paths).not.toContain('/influence/elections')
    expect(paths).not.toContain('/elections/2026-primary/mayor/funding')
    expect(paths.some((path) => path.includes('/candidates/'))).toBe(false)
    expect(paths.some((path) => path.startsWith('/operator'))).toBe(false)
    expect(paths.some((path) => path.startsWith('/api'))).toBe(false)
    expect(paths.some((path) => path.startsWith('/reports/'))).toBe(false)
    expect(paths.some((path) => path.startsWith('/pac/'))).toBe(false)
    expect(paths.some((path) => path.startsWith('/meetings/category/'))).toBe(false)
    expect(paths.some((path) => path.startsWith('/topics/'))).toBe(false)
    expect(paths).toContain('/influence/methodology')
  })

  it('does not wire an all-history classification scan into daily sitemap generation', async () => {
    await buildSitemap(new Date('2026-08-18T00:00:00Z'))

    expect(Object.keys(queryMocks)).not.toContain('getSitemapClassifications')
    expect(queryMocks.getRecentAgendaItemSlugs).toHaveBeenCalledOnce()
  })

  it('preserves the injected UTC rolling 24-month agenda-item cutoff', async () => {
    await buildSitemap(new Date('2026-08-18T23:30:00-07:00'))

    expect(queryMocks.getRecentAgendaItemSlugs).toHaveBeenCalledWith(
      '2024-08-19',
    )
  })

  it('clamps a leap-day cutoff to the last UTC day of the target month', () => {
    expect(agendaItemSitemapCutoffUtc(new Date('2024-02-29T12:00:00Z')))
      .toBe('2022-02-28')
  })

  it('rejects an invalid clock instead of widening discovery', () => {
    expect(() => agendaItemSitemapCutoffUtc(new Date('invalid')))
      .toThrow('requires a valid date')
  })

  it('uses stable routes only when the explicitly inert build cannot query', async () => {
    vi.stubEnv('RICHMOND_BUILD_USES_PRODUCTION_DATA', 'false')
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    queryMocks.getSitemapMeetings.mockRejectedValue(new Error('inert database'))

    const urls = (await buildSitemap(new Date('2026-08-18T00:00:00Z')))
      .map((entry) => entry.url)

    expect(urls).toEqual(PUBLIC_STATIC_PATHS.map((path) => (
      path === '/' ? 'https://richmondcommons.org' : `https://richmondcommons.org${path}`
    )))
  })

  it('does not replace a complete production sitemap after a transient failure', async () => {
    vi.stubEnv('RICHMOND_BUILD_USES_PRODUCTION_DATA', 'true')
    queryMocks.getSitemapCommissions.mockRejectedValue(
      new Error('temporary outage'),
    )

    await expect(buildSitemap(new Date('2026-08-18T00:00:00Z')))
      .rejects.toThrow('temporary outage')
  })

  it('fails closed by default when the production-data marker is unset', async () => {
    vi.stubEnv('RICHMOND_BUILD_USES_PRODUCTION_DATA', undefined)
    queryMocks.getRecentAgendaItemSlugs.mockRejectedValue(
      new Error('temporary outage'),
    )

    await expect(buildSitemap(new Date('2026-08-18T00:00:00Z')))
      .rejects.toThrow('temporary outage')
  })
})
