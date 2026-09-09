import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ from: vi.fn() }))
vi.mock('react', async original => ({ ...await original<typeof import('react')>(), cache: (fn: unknown) => fn }))
vi.mock('./_shared', async original => ({ ...await original<typeof import('./_shared')>(), supabase: mocks }))
import { getMeeting } from './meetings'

const meetingId = '5065ce72-b5df-4e4c-b4f6-c6966aa1610f'
type Result = { data: unknown; count?: number | null; error: unknown }
function builder(result: Result) {
  const q = { select: vi.fn(), eq: vi.fn(), is: vi.fn(), in: vi.fn(), order: vi.fn(), range: vi.fn(), maybeSingle: vi.fn(),
    then: (resolve: (value: Result) => unknown) => Promise.resolve(result).then(resolve) }
  for (const fn of [q.select, q.eq, q.is, q.in, q.order, q.range, q.maybeSingle]) fn.mockReturnValue(q)
  return q
}
function install(overrides: Record<string, Result[]> = {}) {
  const responses: Record<string, Result[]> = {
    meetings: [{ data: { id: meetingId, city_fips: '0660620', bodies: null }, error: null }],
    agenda_items: [{ data: [{ id: 'item-1', public_comment_count: null }], count: 1, error: null }],
    meeting_attendance: [{ data: [], count: 0, error: null }],
    closed_session_items: [{ data: [], count: 0, error: null }],
    public_comments: [{ data: [], count: 0, error: null }],
    motions: [{ data: [], count: 0, error: null }],
    ...overrides,
  }
  mocks.from.mockImplementation((table: string) => {
    const result = responses[table]?.shift()
    if (!result) throw new Error(`Unexpected query: ${table}`)
    return builder(result)
  })
}

describe('meeting source record integrity', () => {
  beforeEach(() => { mocks.from.mockReset() })
  it('retains unknown estimates and does not fetch a competing theme/people count', async () => {
    install()
    const result = await getMeeting(meetingId)
    expect(result?.agenda_items[0].public_comment_count).toBeNull()
    expect(result?.total_public_comments).toBe(0)
    expect(mocks.from.mock.calls.map(call => call[0])).not.toContain('item_theme_narratives')
  })
  it('continues past a lower server cap before supplying agenda and comment counts', async () => {
    install({ agenda_items: [
      { data: [{ id: 'item-1' }], count: 2, error: null },
      { data: [{ id: 'item-2' }], count: 2, error: null },
    ], public_comments: [{ data: [{ id: 'comment-1' }, { id: 'comment-2' }], count: 2, error: null }] })
    const result = await getMeeting(meetingId)
    expect(result?.agenda_items).toHaveLength(2)
    expect(result?.total_public_comments).toBe(2)
  })
  it.each(['agenda_items', 'public_comments', 'meeting_attendance', 'closed_session_items', 'motions'])
    ('rejects failed %s reads instead of reporting none', async table => {
      install({ [table]: [{ data: null, count: null, error: new Error('offline') }] })
      await expect(getMeeting(meetingId)).rejects.toThrow('temporarily unavailable')
    })
  it('rejects partial vote reads before rendering a tally', async () => {
    install({ motions: [{ data: [{ id: 'motion-1', agenda_item_id: 'item-1' }], count: 1, error: null }],
      votes: [{ data: [], count: 1, error: null }] })
    await expect(getMeeting(meetingId)).rejects.toThrow('temporarily unavailable')
  })
})
