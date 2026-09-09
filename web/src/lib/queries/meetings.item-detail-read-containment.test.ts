import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
const mocked = vi.hoisted(() => ({ from: vi.fn() }))
vi.mock('react', async original => ({ ...await original<typeof import('react')>(), cache: (fn: unknown) => fn }))
vi.mock('./_shared', () => ({ supabase: { from: mocked.from }, RICHMOND_FIPS: '0660620',
  filterGovernmentEntityFlags: (value: unknown) => value, COLS_MEETING_LIST: 'id', COLS_MEETING_BANNER: 'id' }))
import { getAgendaItemDetail } from './meetings'
import CommunityVoiceSection, { commentRecordCounts } from '@/components/CommunityVoiceSection'

const MEETING_ID = '5065ce72-b5df-4e4c-b4f6-c6966aa1610f'
const ITEM_ID = '736aaece-c05d-4d14-9ec6-814350496448'
const item = { id: ITEM_ID, meeting_id: MEETING_ID, item_number: 'STUDY-1', title: 'Wastewater study',
  agenda_source_retired_at: null, topic_label: 'Wastewater Treatment', category: 'infrastructure', public_comment_count: 999,
  continued_from: 'August 19, 2025', continued_to: 'future meeting',
  meetings: { id: MEETING_ID, city_fips: '0660620', source_cancelled_at: null, meeting_date: '2026-08-18',
    meeting_type: 'Regular', agenda_url: 'https://example.test/agenda', minutes_url: 'https://example.test/minutes' } }
const sibling = { id: ITEM_ID, meeting_id: MEETING_ID, item_number: 'STUDY-1', summary_headline: null, title: 'Wastewater study' }
const motion = { id: 'motion-1', agenda_item_id: ITEM_ID, motion_text: 'Approve', sequence_number: 1, source: 'minutes' }
const vote = { id: 'vote-1', motion_id: 'motion-1', official_id: 'official-1', official_name: 'Member', vote_choice: 'aye' }
const comment = { id: 'comment-1', agenda_item_id: ITEM_ID, meeting_id: MEETING_ID, speaker_name: 'Resident',
  method: null, comment_type: 'public', summary: 'Source comment', source: 'minutes', extracted_at: '2026-08-19T12:00:00Z' }
type Result = { data: unknown; error: object | null; count?: number | null }
const page = (data: object[] | null, count: number | null = data?.length ?? null, error: object | null = null): Result => ({ data, count, error })
function queryBuilder(result: Result) {
  const query = { select: vi.fn(), is: vi.fn(), ilike: vi.fn(), maybeSingle: vi.fn(), order: vi.fn(), in: vi.fn(), eq: vi.fn(), range: vi.fn() }
  for (const fn of Object.values(query)) fn.mockReturnValue(query)
  return Object.assign(query, { then: (resolve: (value: Result) => unknown) => Promise.resolve(result).then(resolve) })
}
function install(overrides: Record<string, Result[]> = {}) {
  const responses: Record<string, Result[]> = {
    agenda_items: [{ data: item, error: null }, page([sibling])],
    motions: [page([])], public_comments: [page([])], votes: [page([])], ...overrides,
  }
  const calls = new Map<string, ReturnType<typeof queryBuilder>[]>()
  mocked.from.mockImplementation((table: string) => {
    const response = responses[table]?.shift()
    if (!response) throw new Error(`Unexpected query for ${table}`)
    const query = queryBuilder(response)
    calls.set(table, [...calls.get(table) ?? [], query])
    return query
  })
  return calls
}
describe('complete agenda item source records', () => {
  beforeEach(() => vi.clearAllMocks())
  it('uses only source records and avoids descriptive continuation, theme or name-matched identity lookups', async () => {
    const calls = install()
    const result = await getAgendaItemDetail(MEETING_ID, 'STUDY-1')
    expect(result).toMatchObject({ comments: [], motions: [], theme_narratives: [], continued_from_item: null, continued_to_item: null })
    expect(result?.comment_summary).toBeUndefined()
    expect(result?.public_comment_count).toBe(999) // Unpromoted legacy estimate, never the record count.
    expect(result).not.toHaveProperty('related_topic_items')
    expect([...calls.keys()].sort()).toEqual(['agenda_items', 'motions', 'public_comments'])
    expect(calls.get('agenda_items')).toHaveLength(2)
    expect(calls.get('agenda_items')?.[0].maybeSingle).toHaveBeenCalled()
    expect(calls.get('agenda_items')?.[0].is).toHaveBeenCalledWith('meetings.source_cancelled_at', null)
  })
  it('distinguishes invalid/missing identity from a read failure or ambiguous item', async () => {
    expect(await getAgendaItemDetail('invalid', 'STUDY-1')).toBeNull()
    expect(mocked.from).not.toHaveBeenCalled()
    install({ agenda_items: [{ data: null, error: null }] })
    expect(await getAgendaItemDetail(MEETING_ID, 'missing')).toBeNull()
    for (const error of [{ code: '57014' }, { code: 'PGRST116' }]) {
      install({ agenda_items: [{ data: null, error }] })
      await expect(getAgendaItemDetail(MEETING_ID, 'STUDY-1')).rejects.toThrow('Agenda item is temporarily unavailable')
    }
  })
  it('reads motions, comments, votes and navigation beyond a lower response cap', async () => {
    const motions = [motion, { ...motion, id: 'motion-2' }]
    const comments = [comment, { ...comment, id: 'comment-2' }, { ...comment, id: 'comment-3' }]
    const siblings = [{ ...sibling, id: 'previous', item_number: 'A.1' }, sibling, { ...sibling, id: 'next', item_number: 'Z.1' }]
    const votes = [vote, { ...vote, id: 'vote-2' }, { ...vote, id: 'vote-3', motion_id: 'motion-2' }]
    const calls = install({ motions: [page(motions.slice(0, 1), 2), page(motions.slice(1), 2)],
      public_comments: [page(comments.slice(0, 2), 3), page(comments.slice(2), 3)],
      agenda_items: [{ data: item, error: null }, page(siblings.slice(0, 2), 3), page(siblings.slice(2), 3)],
      votes: [page(votes.slice(0, 2), 3), page(votes.slice(2), 3)] })
    const result = await getAgendaItemDetail(MEETING_ID, 'STUDY-1')
    expect(result?.motions.map(m => m.votes.length)).toEqual([2, 1])
    expect(result?.comments).toHaveLength(3)
    expect(result?.prev_item?.item_number).toBe('A.1')
    expect(result?.next_item?.item_number).toBe('Z.1')
    expect(calls.get('motions')?.map(q => q.range.mock.calls[0])).toEqual([[0, 499], [1, 500]])
    expect(calls.get('votes')?.map(q => q.range.mock.calls[0])).toEqual([[0, 499], [2, 501]])
  })
  it.each(['motions', 'public_comments', 'votes', 'agenda_items'])('does not render a failed child read as a complete empty list: %s', async table => {
    const failure = page(null, null, { code: '57014' })
    const overrides = { motions: [page([motion])], [table]: table === 'agenda_items' ? [{ data: item, error: null }, failure] : [failure] }
    install(overrides)
    await expect(getAgendaItemDetail(MEETING_ID, 'STUDY-1')).rejects.toThrow('temporarily unavailable')
  })
  it.each([
    page([comment], null), page([comment], 10001), page([comment, comment], 2), page([], 1),
  ])('rejects missing counts, excessive sets, repeated IDs or premature empty pages', async result => {
    install({ public_comments: [result] })
    await expect(getAgendaItemDetail(MEETING_ID, 'STUDY-1')).rejects.toThrow('Agenda item comment records is temporarily unavailable')
  })
  it('does not call unknown/conflicting channels spoken or count one resident only once', async () => {
    install({ public_comments: [page([
      comment, { ...comment, id: 'written', method: 'email' }, { ...comment, id: 'spoken', method: 'in_person' },
      { ...comment, id: 'conflicting', method: 'zoom', comment_type: 'written' },
    ])] })
    const result = (await getAgendaItemDetail(MEETING_ID, 'STUDY-1'))!
    expect(result).toMatchObject({ spoken_comment_count: 1, written_comment_count: 1 })
    expect(result.comments.every(c => !c.is_notable && !c.notable_role)).toBe(true)
    expect(commentRecordCounts(result.comments)).toEqual({ total: 4, spoken: 1, written: 1, unknown: 2 })
    const html = renderToStaticMarkup(CommunityVoiceSection({ comments: result.comments, themeNarratives: [],
      spokenCount: result.spoken_comment_count, writtenCount: result.written_comment_count,
      commentSource: result.comment_source, commentExtractedAt: result.comment_extracted_at }))
    expect(html).toContain('4 comment records')
    expect(html).toContain('2 with channel not established')
    expect(html).not.toContain('999')
  })
  it('does not assign first-record provenance to mixed sources or extraction times', async () => {
    install({ public_comments: [page([comment, { ...comment, id: 'other', source: 'youtube_transcript', extracted_at: '2026-08-20T12:00:00Z' }])] })
    expect(await getAgendaItemDetail(MEETING_ID, 'STUDY-1')).toMatchObject({ comment_source: null, comment_extracted_at: null })
  })
  it.each(['item', 'meeting', 'city', 'motion', 'comment', 'vote', 'sibling'])('rejects a mismatched source identity: %s', async kind => {
    const changed = structuredClone(item)
    const overrides: Record<string, Result[]> = {}
    if (kind === 'item') changed.item_number = 'OTHER'
    if (kind === 'meeting') changed.meetings.id = 'other'
    if (kind === 'city') changed.meetings.city_fips = 'elsewhere'
    if (['item', 'meeting', 'city'].includes(kind)) overrides.agenda_items = [{ data: changed, error: null }]
    if (kind === 'motion') overrides.motions = [page([{ ...motion, agenda_item_id: 'other' }])]
    if (kind === 'comment') overrides.public_comments = [page([{ ...comment, meeting_id: 'other' }])]
    if (kind === 'vote') { overrides.motions = [page([motion])]; overrides.votes = [page([{ ...vote, motion_id: 'other' }])] }
    if (kind === 'sibling') overrides.agenda_items = [{ data: item, error: null }, page([])]
    install(overrides)
    await expect(getAgendaItemDetail(MEETING_ID, 'STUDY-1')).rejects.toThrow('temporarily unavailable')
  })
  it('treats wildcard characters in an item number literally', async () => {
    const calls = install({ agenda_items: [{ data: { ...item, item_number: 'A_%' }, error: null }, page([{ ...sibling, item_number: 'A_%' }])] })
    expect(await getAgendaItemDetail(MEETING_ID, 'A_%')).not.toBeNull()
    expect(calls.get('agenda_items')?.[0].ilike).toHaveBeenCalledWith('item_number', 'A\\_\\%')
  })
})
