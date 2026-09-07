import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ from: vi.fn() }))
vi.mock('next/cache', () => ({ unstable_cache: (fn: unknown) => fn }))
vi.mock('./_shared', async (importOriginal) => ({
  ...await importOriginal<typeof import('./_shared')>(),
  supabase: { from: mocks.from },
}))

import { getOfficialContributions } from './council'

function builder(result: object) {
  const query = {
    select: vi.fn(), eq: vi.fn(), in: vi.fn(), order: vi.fn(), range: vi.fn(), limit: vi.fn(),
    then: (resolve: (value: object) => unknown) => Promise.resolve(result).then(resolve),
  }
  for (const method of [query.select, query.eq, query.in, query.order, query.range, query.limit]) method.mockReturnValue(query)
  return query
}

const committee = { id: 'historical-council', name: 'Claudia Jimenez for District 6 Richmond City Council 2024', filer_id: '1467767' }
function row(id: string, overrides = {}) {
  return { id, committee_id: committee.id, amount: 50, contribution_date: '2025-01-09',
    contribution_type: 'monetary', filing_id: '214610872', source: 'city_clerk',
    donors: { name: `Donor ${id}`, employer: null, donor_pattern: null }, ...overrides }
}
function committees(result = { data: [committee], count: 1, error: null } as object) {
  const query = builder(result)
  mocks.from.mockReturnValueOnce(query)
  return query
}
function page(rows: object[], count = rows.length, error: object | null = null) {
  const query = builder({ data: rows, count, error })
  mocks.from.mockReturnValueOnce(query)
  return query
}

describe('complete historical council contribution reads', () => {
  beforeEach(() => { mocks.from.mockReset() })

  it('keeps direct historical linkage and provides source committee/report identity', async () => {
    const committeeQuery = committees()
    const contributionsQuery = page([row('one', { amount: '335.00', contribution_date: '2025-01-05' })])
    const result = await getOfficialContributions('official-id')
    expect(committeeQuery.eq).toHaveBeenCalledWith('official_id', 'official-id')
    expect(committeeQuery.select).toHaveBeenCalledWith('id, name, filer_id', { count: 'exact' })
    expect(contributionsQuery.in).toHaveBeenCalledWith('committee_id', ['historical-council'])
    expect(mocks.from.mock.calls.map(([table]) => table)).toEqual(['committees', 'contributions'])
    expect(result[0]).toMatchObject({ amount: 335, contribution_date: '2025-01-05', committee_name: committee.name,
      committee_fppc_id: '1467767', contribution_type: 'monetary', filing_id: '214610872',
      source_url: 'https://netfile.com/Connect2/api/public/image/214610872' })
    expect(contributionsQuery.select.mock.calls[0][0]).not.toContain('*')
    expect(contributionsQuery.order.mock.calls).toEqual([
      ['contribution_date', { ascending: true }], ['id', { ascending: true }],
    ])
  })

  it('paginates beyond the server default without losing dated records', async () => {
    committees()
    const first = page(Array.from({ length: 1000 }, (_, index) => row(String(index))), 1001)
    const second = page([row('1000', { amount: 335 })], 1001)
    const result = await getOfficialContributions('official-id')
    expect(first.range).toHaveBeenCalledWith(0, 999)
    expect(second.range).toHaveBeenCalledWith(1000, 1999)
    expect(result).toHaveLength(1001)
    expect(result.at(-1)?.amount).toBe(335)
  })

  it('advances by actual returned rows if the server applies a smaller page cap', async () => {
    committees()
    page([row('one'), row('two')], 3)
    const second = page([row('three')], 3)
    expect(await getOfficialContributions('official-id')).toHaveLength(3)
    expect(second.range).toHaveBeenCalledWith(2, 1001)
  })

  it('only returns empty after successful complete zero-count reads', async () => {
    committees({ data: [], count: 0, error: null })
    await expect(getOfficialContributions('official-id')).resolves.toEqual([])
    expect(mocks.from).toHaveBeenCalledTimes(1)
    mocks.from.mockReset()
    committees()
    page([], 0)
    await expect(getOfficialContributions('official-id')).resolves.toEqual([])
  })

  it.each([
    { data: null, count: null, error: { code: '08006' } },
    { data: [committee], count: 2, error: null },
    { data: [committee], count: null, error: null },
    { data: [committee], count: 101, error: null },
  ])('fails committee lookup instead of caching a misleading empty result: %j', async (response) => {
    committees(response)
    await expect(getOfficialContributions('official-id')).rejects.toMatchObject({ readPath: 'Historical contribution committees' })
    expect(mocks.from).toHaveBeenCalledTimes(1)
  })

  it('rejects a later query failure instead of returning the first page subtotal', async () => {
    committees()
    page([row('one')], 2)
    page([], 2, { code: '57014' })
    await expect(getOfficialContributions('official-id')).rejects.toMatchObject({ readPath: 'Historical contributions' })
  })

  it.each(['missing-count', 'changed-count', 'empty-page', 'duplicate', 'over-bound'])('rejects incomplete page evidence: %s', async (failure) => {
    committees()
    if (failure === 'over-bound') page([row('one')], 10001)
    else if (failure === 'missing-count') mocks.from.mockReturnValueOnce(builder({ data: [row('one')], count: null, error: null }))
    else {
      page([row('one')], 2)
      if (failure === 'changed-count') page([row('two')], 3)
      if (failure === 'empty-page') page([], 2)
      if (failure === 'duplicate') page([row('one')], 2)
    }
    await expect(getOfficialContributions('official-id')).rejects.toMatchObject({ readPath: 'Historical contributions' })
  })

  it('bounds request count even when a server returns only one row per page', async () => {
    committees()
    for (let index = 0; index < 20; index++) page([row(String(index))], 21)
    await expect(getOfficialContributions('official-id')).rejects.toThrow('Historical contributions')
    expect(mocks.from).toHaveBeenCalledTimes(21) // Committee plus 20 contribution requests.
  })

  it.each(['https://evil.test', '../214610872', '214610872?x=1', '12', '1234567890123'])('does not invent a report link for invalid filing identity %s', async (filing_id) => {
    committees()
    page([row('one', { filing_id })])
    const [result] = await getOfficialContributions('official-id')
    expect(result.filing_id).toBeNull()
    expect(result.source_url).toBeNull()
  })

  it('does not reinterpret another source system numeric ID as a NetFile report', async () => {
    committees()
    page([row('one', { source: 'other_agency' })])
    expect((await getOfficialContributions('official-id'))[0].source_url).toBeNull()
  })

  it('preserves signed/noncash classification and the existing government exclusion', async () => {
    committees()
    page([row('one', { amount: -25, contribution_type: 'nonmonetary' }),
      row('two', { donors: { name: 'City of Richmond', employer: null, donor_pattern: null } })])
    const result = await getOfficialContributions('official-id')
    expect(result).toHaveLength(1)
    expect(result[0]).toMatchObject({ amount: -25, contribution_type: 'nonmonetary' })
  })
})
