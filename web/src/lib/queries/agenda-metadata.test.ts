import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ from: vi.fn(), rpc: vi.fn(), cache: vi.fn((fn: unknown) => fn) }))
vi.mock('next/cache', () => ({ unstable_cache: mocks.cache }))
vi.mock('react', () => ({ cache: (fn: unknown) => fn }))
vi.mock('./_shared', async original => ({ ...await original<typeof import('./_shared')>(), supabase: { from: mocks.from, rpc: mocks.rpc } }))
import { getAgendaMetadata, meetingCards } from './agenda-metadata'
import { AGENDA_METADATA_CACHE_TAG } from '../read-path-cache'
const meeting = (id: string, date = '2026-06-02') => ({ id, city_fips: '0660620', body_id: 'council',
  meeting_date: date, meeting_type: 'regular', presiding_officer: null, agenda_url: 'https://example.test/agenda',
  minutes_url: null, created_at: '2026-06-03T00:00:00Z', source_cancelled_at: null })
const row = (id: string, meetingId = 'one', category: string | null = 'housing', label: string | null = 'Housing', date = '2026-06-02') => ({
  id, meeting_id: meetingId, category, topic_label: label, agenda_source_retired_at: null,
  meetings: { meeting_date: date, city_fips: '0660620', source_cancelled_at: null },
})
function page(data: object[] | null, count: number | null = data?.length ?? 0, error: object | null = null) {
  const q = { select: vi.fn(), eq: vi.fn(), is: vi.fn(), order: vi.fn(), range: vi.fn(),
    then: (resolve: (value: object) => unknown) => Promise.resolve({ data, count, error }).then(resolve) }
  for (const method of [q.select, q.eq, q.is, q.order, q.range]) method.mockReturnValue(q)
  mocks.from.mockReturnValueOnce(q); return q
}
beforeEach(() => { mocks.from.mockReset(); mocks.rpc.mockReset() })

describe('one complete active agenda metadata projection', () => {
  it('counts the actual full cohort, including a lower-cap final page and genuine empty meeting', async () => {
    const firstMeeting = page([{ ...meeting('one'), agenda_item_count: 999, meeting_summary: 'unused', vote_count: 88 }], 2)
    const secondMeeting = page([meeting('empty')], 2)
    const firstAgenda = page([row('a'), row('b')], 3)
    const lastAgenda = page([row('c', 'one', 'procedural', 'Housing')], 3)
    const snapshot = await getAgendaMetadata('0660620')
    expect(snapshot.meetings.find(m => m.id === 'one')).toMatchObject({ agenda_item_count: 3,
      all_categories: [{ category: 'housing', count: 2 }, { category: 'procedural', count: 1 }], all_topic_labels: [{ label: 'Housing', count: 2 }] })
    expect(snapshot.meetings.find(m => m.id === 'empty')).toMatchObject({ agenda_item_count: 0, all_categories: [], all_topic_labels: [] })
    expect(snapshot.topics).toEqual([{ topic_label: 'Housing', item_count: 3, meeting_count: 1, latest_meeting_date: '2026-06-02' }])
    expect(firstMeeting.select.mock.calls[0][0]).not.toMatch(/agenda_item_count|meeting_summary|votes/)
    expect(secondMeeting.range).toHaveBeenCalledWith(1, 500)
    expect(firstAgenda.is).toHaveBeenCalledWith('agenda_source_retired_at', null)
    expect(firstAgenda.is).toHaveBeenCalledWith('meetings.source_cancelled_at', null)
    expect(lastAgenda.range).toHaveBeenCalledWith(2, 501)
    expect(mocks.rpc).not.toHaveBeenCalled()
    expect(JSON.stringify(snapshot)).not.toMatch(/vote_count|meeting_summary|top_categories|top_topic_labels/)
    expect(meetingCards(snapshot).find(m => m.id === 'one')?.top_topic_labels).toEqual([{ label: 'Housing', count: 2 }])
  })
  it('uses actual distinct meeting IDs, not dates, for recurrence and keeps unlabeled entries in item counts', async () => {
    page([meeting('one'), meeting('two'), meeting('three', '2026-06-09')])
    page([row('a'), row('b'), row('c', 'two'), row('d', 'three', null, 'Housing', '2026-06-09'), row('e', 'three', null, null, '2026-06-09')])
    const snapshot = await getAgendaMetadata('0660620')
    expect(snapshot.topics).toEqual([{ topic_label: 'Housing', item_count: 4, meeting_count: 3, latest_meeting_date: '2026-06-09' }])
    expect(snapshot.meetings[0]).toMatchObject({ id: 'three', agenda_item_count: 2, all_categories: [], all_topic_labels: [] })
  })
  it('keeps the full source corpus outside a one-hour compact persistent cache', () => {
    expect(mocks.cache).toHaveBeenCalledWith(expect.any(Function), ['complete-active-agenda-metadata-v1'],
      { revalidate: 3600, tags: [AGENDA_METADATA_CACHE_TAG] })
  })
  it.each(['missing-parent', 'changed-date', 'wrong-city', 'cancelled', 'retired', 'missing-relation', 'bad-category', 'bad-label'])('rejects inconsistent agenda metadata: %s', async cause => {
    page([meeting('one')])
    const original = row('a')
    const changes: Record<string, object> = {
      'missing-parent': { meeting_id: 'absent' }, 'changed-date': { meetings: { ...original.meetings, meeting_date: '2026-06-09' } },
      'wrong-city': { meetings: { ...original.meetings, city_fips: 'other' } },
      cancelled: { meetings: { ...original.meetings, source_cancelled_at: '2026-06-01' } },
      retired: { agenda_source_retired_at: '2026-06-01' }, 'missing-relation': { meetings: null },
      'bad-category': { category: '' }, 'bad-label': { topic_label: 2 },
    }
    page([{ ...original, ...changes[cause] }])
    await expect(getAgendaMetadata('0660620')).rejects.toThrow('temporarily unavailable')
  })
  it('preserves an unknown body without withholding its source agenda records', async () => {
    page([{ ...meeting('one'), body_id: null }]); page([row('a')])
    expect((await getAgendaMetadata('0660620')).meetings[0]).toMatchObject({ id: 'one', body_id: null, agenda_item_count: 1 })
  })
  it.each([{ city_fips: 'other' }, { body_id: '' }, { source_cancelled_at: '2026-01-01' }, { meeting_date: null }])('rejects invalid visible meeting inventory %j', async override => {
    page([{ ...meeting('one'), ...override }])
    await expect(getAgendaMetadata('0660620')).rejects.toThrow('temporarily unavailable')
    expect(mocks.from).toHaveBeenCalledTimes(1)
  })
  it.each(['error', 'missing-count', 'changed-count', 'duplicate', 'empty-later', 'over-bound', 'null-data'])('withholds partial aggregates when an agenda page is incomplete: %s', async cause => {
    page([meeting('one')])
    if (cause === 'error') page(null, null, { code: '57014' })
    else if (cause === 'missing-count') page([row('a')], null)
    else if (cause === 'over-bound') page([row('a')], 20001)
    else if (cause === 'null-data') page(null, 0)
    else { page([row('a')], 2); page(cause === 'empty-later' ? [] : [row(cause === 'duplicate' ? 'a' : 'b')], cause === 'changed-count' ? 3 : 2) }
    await expect(getAgendaMetadata('0660620')).rejects.toThrow('temporarily unavailable')
  })
  it('does not invent a zero for an agenda parent missing from a genuinely empty inventory', async () => {
    page([], 0); page([row('a')])
    await expect(getAgendaMetadata('0660620')).rejects.toThrow('temporarily unavailable')
    page([], 0); page([], 0)
    expect(await getAgendaMetadata('0660620')).toEqual({ meetings: [], topics: [] })
  })
  it('rejects an oversized compact result instead of silently truncating or caching a huge payload', async () => {
    page([meeting('one')]); page([row('a', 'one', 'housing', 'x'.repeat(900000))])
    await expect(getAgendaMetadata('0660620')).rejects.toThrow('temporarily unavailable')
  })
})
