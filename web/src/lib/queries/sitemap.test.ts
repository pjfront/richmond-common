import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocked = vi.hoisted(() => ({
  from: vi.fn(),
}))

vi.mock('./_shared', () => ({
  RICHMOND_FIPS: '0660620',
  supabase: { from: mocked.from },
}))

import {
  getRecentAgendaItemSlugs,
  getSitemapDonorSlugs,
  getSitemapMeetings,
  getSitemapOfficials,
  getSitemapOrganizationSlugs,
} from './sitemap'

type QueryResult = {
  data: unknown[] | null
  error: { code: string; message: string } | null
  count: number | null
}

interface QueryCalls {
  select: unknown[][]
  is: unknown[][]
  eq: unknown[][]
  gte: unknown[][]
  gt: unknown[][]
  in: unknown[][]
  not: unknown[][]
  limit: unknown[][]
  order: unknown[][]
}

function installResult(result: QueryResult): QueryCalls {
  const calls: QueryCalls = {
    select: [],
    is: [],
    eq: [],
    gte: [],
    gt: [],
    in: [],
    not: [],
    limit: [],
    order: [],
  }
  const builder = {
    select: vi.fn((...args: unknown[]) => {
      calls.select.push(args)
      return builder
    }),
    is: vi.fn((...args: unknown[]) => {
      calls.is.push(args)
      return builder
    }),
    eq: vi.fn((...args: unknown[]) => {
      calls.eq.push(args)
      return builder
    }),
    gte: vi.fn((...args: unknown[]) => {
      calls.gte.push(args)
      return builder
    }),
    gt: vi.fn((...args: unknown[]) => {
      calls.gt.push(args)
      return builder
    }),
    in: vi.fn((...args: unknown[]) => {
      calls.in.push(args)
      return builder
    }),
    not: vi.fn((...args: unknown[]) => {
      calls.not.push(args)
      return builder
    }),
    limit: vi.fn((...args: unknown[]) => {
      calls.limit.push(args)
      return builder
    }),
    order: vi.fn((...args: unknown[]) => {
      calls.order.push(args)
      return Promise.resolve(result)
    }),
  }
  mocked.from.mockReturnValue(builder)
  return calls
}

describe('recent agenda-item sitemap query', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('applies the approved active-row, meeting, and 24-month filters', async () => {
    const calls = installResult({
      data: [{
        meeting_id: 'meeting-1',
        item_number: 'CC-1',
        meetings: { meeting_date: '2026-08-01' },
      }],
      error: null,
      count: 1,
    })

    await expect(getRecentAgendaItemSlugs('2024-08-18')).resolves.toEqual([{
      meeting_id: 'meeting-1',
      item_number: 'CC-1',
      meeting_date: '2026-08-01',
    }])

    expect(mocked.from).toHaveBeenCalledWith('agenda_items')
    expect(calls.select[0]?.[1]).toEqual({ count: 'exact' })
    expect(calls.is).toContainEqual(['agenda_source_retired_at', null])
    expect(calls.is).toContainEqual(['meetings.source_cancelled_at', null])
    expect(calls.eq).toContainEqual(['meetings.city_fips', '0660620'])
    expect(calls.gte).toEqual([['meetings.meeting_date', '2024-08-18']])
    expect(calls.order).toEqual([['id']])
  })

  it('fails closed at the 10,000-row boundary', async () => {
    installResult({
      data: [],
      error: null,
      count: 10_000,
    })

    await expect(getRecentAgendaItemSlugs('2024-08-18'))
      .rejects.toThrow('reached 10,000 rows')
  })

  it('accepts a complete result strictly below the 10,000-row boundary', async () => {
    const row = {
      meeting_id: 'meeting-1',
      item_number: 'CC-1',
      meetings: { meeting_date: '2026-08-01' },
    }
    installResult({
      data: Array.from({ length: 9_999 }, () => row),
      error: null,
      count: 9_999,
    })

    await expect(getRecentAgendaItemSlugs('2024-08-18'))
      .resolves.toHaveLength(9_999)
  })

  it('retains scheduled upcoming items under the approved lower-cutoff policy', async () => {
    installResult({
      data: [{
        meeting_id: 'future-meeting',
        item_number: 'CC-2',
        meetings: { meeting_date: '2026-09-01' },
      }],
      error: null,
      count: 1,
    })

    await expect(getRecentAgendaItemSlugs('2024-08-18')).resolves.toEqual([{
      meeting_id: 'future-meeting',
      item_number: 'CC-2',
      meeting_date: '2026-09-01',
    }])
  })

  it('fails closed when Supabase omits or truncates the exact result', async () => {
    installResult({ data: [], error: null, count: null })
    await expect(getRecentAgendaItemSlugs('2024-08-18'))
      .rejects.toThrow('did not return an exact row count')

    installResult({
      data: [{
        meeting_id: 'meeting-1',
        item_number: 'CC-1',
        meetings: { meeting_date: '2026-08-01' },
      }],
      error: null,
      count: 2,
    })
    await expect(getRecentAgendaItemSlugs('2024-08-18'))
      .rejects.toThrow('returned 1 of 2 rows')
  })

  it('propagates query failures so ISR keeps the prior complete sitemap', async () => {
    const failure = { code: '57014', message: 'query timed out' }
    installResult({ data: null, error: failure, count: null })
    vi.spyOn(console, 'error').mockImplementation(() => undefined)

    await expect(getRecentAgendaItemSlugs('2024-08-18'))
      .rejects.toBe(failure)
  })
})

describe('lightweight public sitemap queries', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('requires a complete exact meeting result', async () => {
    const calls = installResult({
      data: [{ id: 'meeting-1' }],
      error: null,
      count: 1,
    })

    await expect(getSitemapMeetings()).resolves.toEqual([
      { id: 'meeting-1' },
    ])
    expect(mocked.from).toHaveBeenCalledWith('meetings')
    expect(calls.select[0]?.[1]).toEqual({ count: 'exact' })
    expect(calls.eq).toContainEqual(['city_fips', '0660620'])
    expect(calls.limit).toEqual([[10_000]])
    expect(calls.order).toEqual([['id']])

    installResult({
      data: [{ id: 'meeting-1' }],
      error: null,
      count: 2,
    })
    await expect(getSitemapMeetings()).rejects.toThrow('returned 1 of 2 rows')
  })

  it('limits council discovery to current council roles', async () => {
    const calls = installResult({
      data: [{ name: 'Example Member' }],
      error: null,
      count: 1,
    })

    await expect(getSitemapOfficials()).resolves.toEqual([
      { name: 'Example Member' },
    ])
    expect(calls.eq).toContainEqual(['is_current', true])
    expect(calls.limit).toEqual([[10_000]])
    expect(calls.in).toContainEqual([
      'role',
      [
        'mayor',
        'vice_mayor',
        'councilmember',
        'council_member',
        'City/Town Council Member',
      ],
    ])
  })

  it('matches the graduated individual and organization profile filters', async () => {
    const donorCalls = installResult({
      data: [{ entity_slug: 'example-donor', created_at: '2026-01-01' }],
      error: null,
      count: 1,
    })
    await expect(getSitemapDonorSlugs()).resolves.toEqual([{
      slug: 'example-donor',
      created_at: '2026-01-01',
    }])
    expect(donorCalls.eq).toContainEqual(['entity_type', 'person'])
    expect(donorCalls.gte).toContainEqual(['total_contributed', 5_000])
    expect(donorCalls.not).toContainEqual(['entity_slug', 'is', null])

    const orgCalls = installResult({
      data: [
        { entity_slug: 'example-union', created_at: '2026-01-01' },
        { entity_slug: 'example-union', created_at: '2026-01-02' },
      ],
      error: null,
      count: 2,
    })
    await expect(getSitemapOrganizationSlugs()).resolves.toEqual([{
      slug: 'example-union',
      created_at: '2026-01-02',
    }])
    expect(orgCalls.in).toContainEqual([
      'entity_type',
      ['union', 'corporation'],
    ])
    expect(orgCalls.gt).toContainEqual(['total_contributed', 0])
  })

  it('fails closed at the shared 10,000-row guard and on query errors', async () => {
    installResult({ data: [], error: null, count: 10_000 })
    await expect(getSitemapMeetings()).rejects.toThrow('reached 10,000 rows')

    const failure = { code: '57014', message: 'sitemap query timed out' }
    installResult({ data: null, error: failure, count: null })
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    await expect(getSitemapMeetings()).rejects.toBe(failure)
  })
})
