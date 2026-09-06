import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ from: vi.fn() }))
vi.mock('next/cache', () => ({ unstable_cache: (fn: unknown) => fn }))
vi.mock('react', () => ({ cache: (fn: unknown) => fn }))
vi.mock('./_shared', () => ({ supabase: { from: mocks.from }, RICHMOND_FIPS: '0660620', COLS_TOPIC_COUNTS: 'id,topic_label,meeting_id,meetings!inner(meeting_date,city_fips)' }))
import { getTopicCounts, getPromotedTopics } from './topics'
const row = (id: string, meeting: number) => ({ id, topic_label: 'Housing', meeting_id: `m${meeting}`, meetings: { meeting_date: `2026-09-0${meeting}` } })
function page(data: object[] | null, count: number | null, error: object | null = null) {
  const query = { select: vi.fn(), eq: vi.fn(), is: vi.fn(), not: vi.fn(), order: vi.fn(), range: vi.fn(),
    then: (resolve: (value: object) => unknown) => Promise.resolve({ data, count, error }).then(resolve) }
  for (const method of [query.select, query.eq, query.is, query.not, query.order, query.range]) method.mockReturnValue(query)
  mocks.from.mockReturnValueOnce(query)
  return query
}
describe('complete topic recurrence counts', () => {
  beforeEach(() => mocks.from.mockReset())
  it.each([getTopicCounts, getPromotedTopics])('does not lose the final distinct meeting at a response cap', async read => {
    const first = page([row('1', 1), row('2', 1), row('3', 2), row('4', 2)], 5)
    const second = page([row('5', 3)], 5)
    expect(await read()).toEqual([expect.objectContaining({ item_count: 5, latest_meeting_date: '2026-09-03' })])
    expect(first.is).toHaveBeenCalledWith('agenda_source_retired_at', null)
    expect(first.order).toHaveBeenCalledWith('id', { ascending: true })
    expect(second.range).toHaveBeenCalledWith(4, 503)
  })
  it.each(['error', 'missing-count', 'changed-count', 'repeated-id', 'empty-later', 'over-bound', 'bad-source'])('withholds incomplete aggregate instead of returning partial labels: %s', async cause => {
    if (cause === 'error') page(null, null, { code: '57014' })
    else if (cause === 'missing-count') page([row('1', 1)], null)
    else if (cause === 'over-bound') page([row('1', 1)], 20001)
    else if (cause === 'bad-source') page([{ ...row('1', 1), meetings: null }], 1)
    else {
      page([row('1', 1)], 2)
      page(cause === 'empty-later' ? [] : [row(cause === 'repeated-id' ? '1' : '2', 2)], cause === 'changed-count' ? 3 : 2)
    }
    await expect(getPromotedTopics()).rejects.toThrow()
  })
  it('does not promote a same-meeting cluster or manufacture data for a real empty read', async () => {
    page(Array.from({ length: 8 }, (_, index) => row(String(index), 1)), 8)
    expect(await getPromotedTopics()).toEqual([])
    page([], 0)
    expect(await getTopicCounts()).toEqual([])
  })
})
