import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ from: vi.fn() }))
vi.mock('./_shared', async (importOriginal) => ({
  ...await importOriginal<typeof import('./_shared')>(), supabase: { from: mocks.from },
}))
import { getDonorList, getDonorOutgoing } from './donors'
function page(data: object[] | null, count: number | null = data?.length ?? 0, error: object | null = null) {
  const result = { data, count, error }
  const query = { select: vi.fn(), eq: vi.fn(), gte: vi.fn(), not: vi.fn(), order: vi.fn(), range: vi.fn(),
    then: (resolve: (value: object) => unknown) => Promise.resolve(result).then(resolve) }
  for (const method of [query.select, query.eq, query.gte, query.not, query.order, query.range]) method.mockReturnValue(query)
  mocks.from.mockReturnValueOnce(query)
  return query
}
const committee = { id: 'committee-id', name: 'Example recipient committee', candidate_name: null, filer_id: '1488504' }
function row(id: string, extra = {}) {
  return { id, amount: '100.00', contribution_date: '2025-05-01', contribution_type: 'monetary', filing_id: '217136864',
    source: 'netfile', committees: committee, ...extra }
}
const person = (id: string, extra = {}) => ({ id, name: `Reported name ${id}`, employer: 'Reported employer', occupation: null, entity_slug: `person-${id}`, ...extra })

beforeEach(() => mocks.from.mockReset())

describe('metadata-only public donor directory', () => {
  it('uses cached threshold only for eligibility and never returns or separately sums money', async () => {
    const query = page([person('one')])
    expect(await getDonorList()).toEqual([{ slug: 'person-one', display_name: 'Reported name one', employer: 'Reported employer', occupation: null, donor_id: 'one' }])
    expect(query.gte).toHaveBeenCalledWith('total_contributed', 5000)
    expect(query.select.mock.calls[0][0]).not.toContain('total_contributed')
    expect(query.select).toHaveBeenCalledWith('id, name, employer, occupation, entity_slug', { count: 'exact' })
    expect(query.order.mock.calls).toEqual([['name'], ['id']])
    expect(mocks.from.mock.calls).toEqual([['donors']])
  })
  it('handles lower server caps and refuses missing counts, duplicate slugs, or directory failures', async () => {
    page([person('one')], 2)
    const next = page([person('two')], 2)
    expect(await getDonorList()).toHaveLength(2)
    expect(next.range).toHaveBeenCalledWith(1, 500)
    page([], null)
    await expect(getDonorList()).rejects.toThrow('temporarily unavailable')
    page([person('one'), person('two', { entity_slug: 'person-one' })])
    await expect(getDonorList()).rejects.toThrow('identity is ambiguous')
    page([], 0, { code: 'timeout' })
    await expect(getDonorList()).rejects.toThrow('temporarily unavailable')
  })
})

describe('source-bearing donor entries', () => {
  it('keeps exact source identity, signed amounts and all types without merging equal entries', async () => {
    page([row('one'), row('two'), row('noncash', { contribution_type: 'nonmonetary' }), row('loan', { contribution_type: 'loan' }),
      row('negative', { amount: '-25.25' }), row('transfer', { contribution_type: 'transfer' })])
    const result = await getDonorOutgoing('donor-id')
    expect(result).toHaveLength(6)
    expect(result[0]).toMatchObject({ record_id: 'one', amount: 100, source: 'netfile', source_url: 'https://netfile.com/Connect2/api/public/image/217136864', recipient_committee_fppc_id: '1488504' })
    expect(result[2].contribution_type).toBe('nonmonetary')
    expect(result[4].amount).toBe(-25.25)
    expect(result[5].contribution_type).toBe('transfer')
  })
  it('does not fabricate local source URLs for unknown or CAL-ACCESS filings', async () => {
    page([row('state', { source: 'cal_access' }), row('unknown', { source: null }), row('unlinked', { filing_id: 'not-numeric' })])
    const result = await getDonorOutgoing('donor-id')
    expect(result.map(entry => entry.source_url)).toEqual([null, null, null])
    expect(result[2].filing_id).toBe('not-numeric')
  })
  it('paginates beyond 1000 and honors lower server caps using exact counts and actual offsets', async () => {
    page(Array.from({ length: 500 }, (_, i) => row(String(i))), 1001)
    page(Array.from({ length: 500 }, (_, i) => row(String(i + 500))), 1001)
    const last = page([row('1000')], 1001)
    expect(await getDonorOutgoing('donor-id')).toHaveLength(1001)
    expect(last.range).toHaveBeenCalledWith(1000, 1499)
    page([row('one')], 2)
    const lower = page([row('two')], 2)
    expect(await getDonorOutgoing('donor-id')).toHaveLength(2)
    expect(lower.range).toHaveBeenCalledWith(1, 500)
  })
  it('fails instead of returning partial records for count drift, repeated pages or exhausted pages', async () => {
    page([row('one')], 2); page([row('two')], 3)
    await expect(getDonorOutgoing('donor-id')).rejects.toThrow('temporarily unavailable')
    page([row('one')], 2); page([row('one')], 2)
    await expect(getDonorOutgoing('donor-id')).rejects.toThrow('temporarily unavailable')
    page([row('one')], 2); page([], 2)
    await expect(getDonorOutgoing('donor-id')).rejects.toThrow('temporarily unavailable')
    for (let i = 0; i < 20; i++) page([row(String(i))], 21)
    await expect(getDonorOutgoing('donor-id')).rejects.toThrow('temporarily unavailable')
  })
  it('distinguishes a complete empty set from unavailable, invalid amount, impossible date or excessive scope', async () => {
    page([], 0)
    expect(await getDonorOutgoing('donor-id')).toEqual([])
    for (const result of [{ data: null, count: 0, error: null }, { data: [], count: null, error: null }, { data: [], count: 0, error: { code: 'timeout' } }, { data: [], count: 10001, error: null }]) {
      page(result.data, result.count, result.error)
      await expect(getDonorOutgoing('donor-id')).rejects.toThrow('temporarily unavailable')
    }
    for (const overrides of [{ amount: null }, { amount: 'NaN' }, { contribution_date: '2025-02-30' }]) {
      page([row('invalid', overrides)])
      await expect(getDonorOutgoing('donor-id')).rejects.toThrow('identity, date or amount')
    }
  })
})
