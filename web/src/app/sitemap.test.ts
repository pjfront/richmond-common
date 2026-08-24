import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const queryMocks = vi.hoisted(() => ({
  getMeetings: vi.fn(),
  getOfficials: vi.fn(),
  getRecentAgendaItemSlugs: vi.fn(),
}))

vi.mock('@/lib/queries', () => queryMocks)

import {
  agendaItemSitemapCutoffUtc,
  buildSitemap,
} from './sitemap'

describe('bounded agenda-item sitemap', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    queryMocks.getMeetings.mockResolvedValue([])
    queryMocks.getOfficials.mockResolvedValue([])
    queryMocks.getRecentAgendaItemSlugs.mockResolvedValue([])
  })

  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('uses an injected UTC date for the inclusive rolling 24-month cutoff', async () => {
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

  it('assembles stable and returned recent agenda-item routes', async () => {
    queryMocks.getMeetings.mockResolvedValue([
      { id: 'meeting-1', meeting_date: '2026-08-01' },
    ])
    queryMocks.getOfficials.mockResolvedValue([{ name: 'Example Member' }])
    queryMocks.getRecentAgendaItemSlugs.mockResolvedValue([
      {
        meeting_id: 'meeting-1',
        item_number: 'CC-1',
        meeting_date: '2026-08-01',
      },
    ])

    const urls = (await buildSitemap(new Date('2026-08-18T00:00:00Z')))
      .map((entry) => entry.url)

    expect(urls).toContain('https://richmondcommons.org')
    expect(urls).toContain('https://richmondcommons.org/meetings/meeting-1')
    expect(urls).toContain(
      'https://richmondcommons.org/meetings/meeting-1/items/cc-1',
    )
    expect(urls).toContain('https://richmondcommons.org/council/example-member')
  })

  it('uses stable routes only when the explicitly inert build cannot query items', async () => {
    vi.stubEnv('RICHMOND_BUILD_USES_PRODUCTION_DATA', 'false')
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    queryMocks.getRecentAgendaItemSlugs.mockRejectedValue(
      new Error('inert database'),
    )

    const urls = (await buildSitemap(new Date('2026-08-18T00:00:00Z')))
      .map((entry) => entry.url)

    expect(urls).toEqual([
      'https://richmondcommons.org',
      'https://richmondcommons.org/meetings',
      'https://richmondcommons.org/council',
      'https://richmondcommons.org/about',
    ])
  })

  it('does not replace the production sitemap after a transient item-query failure', async () => {
    vi.stubEnv('RICHMOND_BUILD_USES_PRODUCTION_DATA', 'true')
    queryMocks.getRecentAgendaItemSlugs.mockRejectedValue(
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
