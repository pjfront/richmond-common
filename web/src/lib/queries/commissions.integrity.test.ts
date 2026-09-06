import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ from: vi.fn() }))
vi.mock('./meetings', () => ({ fetchMeetingCounts: vi.fn(), applyMeetingCounts: vi.fn() }))
vi.mock('./_shared', () => ({ supabase: { from: mocks.from }, RICHMOND_FIPS: '0660620', warnIfEmpty: vi.fn(), COLS_COMMISSION: 'id,name,num_seats', COLS_CURRENT_COMMISSION_MEMBER: 'id,commission_id,term_end', COLS_COMMISSION_MEMBER: 'id,name,commission_id' }))
import { getCommissions, getCommission } from './commissions'
function query(data: object | null, count: number | null = null, error: object | null = null) {
  const q = { select: vi.fn(), eq: vi.fn(), in: vi.fn(), order: vi.fn(), limit: vi.fn(), maybeSingle: vi.fn(),
    then: (resolve: (v: object) => unknown) => Promise.resolve({ data, count, error }).then(resolve) }
  for (const method of [q.select, q.eq, q.in, q.order, q.limit, q.maybeSingle]) method.mockReturnValue(q)
  mocks.from.mockReturnValueOnce(q)
  return q
}
describe('commission roster completeness', () => {
  beforeEach(() => mocks.from.mockReset())
  it.each(['error', 'missing-count', 'partial'])('fails unavailable membership without inventing an empty roster: %s', async cause => {
    query([{ id: 'one', num_seats: 7 }], 1)
    query(cause === 'error' ? null : [], cause === 'missing-count' ? null : 2, cause === 'error' ? { code: '08006' } : null)
    await expect(getCommissions()).rejects.toThrow('membership')
  })
  it('rejects a capped commission list before querying membership', async () => {
    query([{ id: 'one' }], 2)
    await expect(getCommissions()).rejects.toThrow('roster')
    expect(mocks.from).toHaveBeenCalledTimes(1)
  })
  it('retains source-listed members regardless of expired recorded terms', async () => {
    query([{ id: 'one', num_seats: 7 }], 1)
    query([{ id: 'a', commission_id: 'one', term_end: null }, { id: 'b', commission_id: 'one', term_end: '2020-01-01' }], 2)
    expect(await getCommissions()).toEqual([expect.objectContaining({ member_count: 1, holdover_count: 1 })])
  })
  it('detail lookup distinguishes missing commission from read failure', async () => {
    query(null, null, { code: '08006' })
    await expect(getCommission('one')).rejects.toThrow('details unavailable')
    query(null)
    expect(await getCommission('one')).toBeNull()
  })
  it('detail member failure does not masquerade as zero current members', async () => {
    query({ id: 'one' })
    query(null, null, { code: '57014' })
    await expect(getCommission('one')).rejects.toThrow('membership')
  })
})
