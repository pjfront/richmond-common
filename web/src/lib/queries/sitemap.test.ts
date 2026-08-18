import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocked = vi.hoisted(() => ({
  from: vi.fn(),
}))

vi.mock('./_shared', () => ({
  supabase: { from: mocked.from },
  RICHMOND_FIPS: '0660620',
}))

vi.mock('./council', () => ({
  COUNCIL_ROLES: ['council_member'],
}))

import { getSitemapAgendaItemsPage } from './sitemap'

type QueryError = { code: string; message: string }
type QueryResult = { data: unknown; error: QueryError | null }

interface QueryCalls {
  select: string[]
  is: Array<[string, unknown]>
  eq: Array<[string, unknown]>
  gte: Array<[string, unknown]>
  order: string[]
  range: Array<[number, number]>
}

function queryBuilder(result: QueryResult, calls: QueryCalls) {
  const builder: Record<string, unknown> = {}
  const chain = () => builder

  builder.select = vi.fn((columns: string) => {
    calls.select.push(columns)
    return builder
  })
  builder.is = vi.fn((column: string, value: unknown) => {
    calls.is.push([column, value])
    return builder
  })
  builder.eq = vi.fn((column: string, value: unknown) => {
    calls.eq.push([column, value])
    return builder
  })
  builder.gte = vi.fn((column: string, value: unknown) => {
    calls.gte.push([column, value])
    return builder
  })
  builder.order = vi.fn((column: string) => {
    calls.order.push(column)
    return builder
  })
  builder.range = vi.fn((from: number, to: number) => {
    calls.range.push([from, to])
    return Promise.resolve(result)
  })

  for (const method of ['limit']) {
    builder[method] = vi.fn(chain)
  }
  return builder
}

function installResult(result: QueryResult): QueryCalls {
  const calls: QueryCalls = {
    select: [],
    is: [],
    eq: [],
    gte: [],
    order: [],
    range: [],
  }
  mocked.from.mockReturnValue(queryBuilder(result, calls))
  return calls
}

describe('agenda-item sitemap query', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('applies the cutoff and active-row filters in the database query', async () => {
    const calls = installResult({
      data: [{
        id: 'item-1',
        meeting_id: 'meeting-1',
        item_number: 'CC-1',
        meetings: {
          meeting_date: '2026-08-01',
          city_fips: '0660620',
          source_cancelled_at: null,
        },
      }],
      error: null,
    })

    await expect(getSitemapAgendaItemsPage(
      0,
      999,
      '2024-08-18',
      '0660620',
    )).resolves.toEqual([{
      meeting_id: 'meeting-1',
      item_number: 'CC-1',
      meeting_date: '2026-08-01',
    }])

    expect(mocked.from).toHaveBeenCalledWith('agenda_items')
    expect(calls.select[0]).toContain('meetings!inner(meeting_date, city_fips, source_cancelled_at)')
    expect(calls.is).toEqual([
      ['agenda_source_retired_at', null],
      ['meetings.source_cancelled_at', null],
    ])
    expect(calls.eq).toEqual([['meetings.city_fips', '0660620']])
    expect(calls.gte).toEqual([['meetings.meeting_date', '2024-08-18']])
    expect(calls.order).toEqual(['id'])
    expect(calls.range).toEqual([[0, 999]])
  })

  it('propagates query failures so ISR keeps the prior complete sitemap', async () => {
    const failure = { code: '57014', message: 'agenda-item sitemap query timed out' }
    installResult({ data: null, error: failure })
    vi.spyOn(console, 'error').mockImplementation(() => undefined)

    await expect(getSitemapAgendaItemsPage(0, 999, '2024-08-18'))
      .rejects.toBe(failure)
  })
})
