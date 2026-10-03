import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ from: vi.fn(), searchSite: vi.fn(), finance: vi.fn() }))
vi.mock('./_shared', () => ({ supabase: { from: mocks.from }, RICHMOND_FIPS: '0660620' }))
vi.mock('./search', () => ({ searchSite: mocks.searchSite }))
vi.mock('./finance-public', () => ({ getPublicFinanceSnapshot: mocks.finance }))
import { searchCommons } from './commons-search'
import { planCommonsSearch } from '../commons-search'

function page(data: object[] | null, count: number | null = data?.length ?? null, error: unknown = null) {
  const query = { select: vi.fn(), eq: vi.fn(), is: vi.fn(), in: vi.fn(), order: vi.fn(), range: vi.fn(), returns: vi.fn(), gte: vi.fn(), lte: vi.fn(),
    then: (resolve: (value: object) => unknown) => Promise.resolve({ data, count, error }).then(resolve) }
  for (const method of [query.select, query.eq, query.is, query.in, query.order, query.range, query.returns, query.gte, query.lte]) method.mockReturnValue(query)
  mocks.from.mockReturnValueOnce(query)
  return query
}
const request = (value: string) => planCommonsSearch(new URLSearchParams(value))
const agenda = { id: 'item-1', meeting_id: 'meeting-1', item_number: 'H.3', title: 'Housing services', topic_label: 'Housing', category: 'housing', created_at: '2026-08-02T00:00:00Z', agenda_source_retired_at: null,
  meetings: { id: 'meeting-1', city_fips: '0660620', meeting_date: '2026-08-01', agenda_url: 'https://example.gov/agenda.pdf', minutes_url: 'https://example.gov/minutes.pdf', video_url: null, source_cancelled_at: null } }
const event = { event_key: 'event-1', scope_key: '0660620:calendar-2026', event_kind: 'receipt', donor_name: 'A Contributor', recipient_name: 'Jimenez committee', donor_fppc_id: null, recipient_fppc_id: '1234567', reporting_filer_name: 'Jimenez committee', reporting_filer_fppc_id: '1234567', amount: 100, amount_kind: 'cash', activity_date: '2026-08-01', support_oppose: null, candidate_name: null, measure_name: null, election_date: null, filing_ids: ['1'], source_urls: ['https://example.gov/filing.pdf'], source_url: 'https://example.gov/filing.pdf', extracted_at: '2026-08-02T00:00:00Z', source_tier: 1, reconciliation_status: 'source_reported' }

describe('read-only staging record retrieval', () => {
  afterEach(() => vi.unstubAllEnvs())
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.from.mockReset()
    mocks.searchSite.mockImplementation(async (_q: string, options: { offset: number; resultType: string }) => options.offset === 0 && options.resultType === 'agenda_item' ? [{ id: agenda.id }] : [])
    mocks.finance.mockResolvedValue({ events: [event], coverage: [], truncated: false })
  })
  it('keeps keyword counts limited and creates an exact source item permalink', async () => {
    const projection = page([agenda])
    const result = await searchCommons(request('q=housing&topic=Housing&from=2026-01-01'))
    expect(result.limited).toBe(true)
    expect(result.total).toBe(1)
    expect(result.records[0]).toMatchObject({ title: agenda.title, url: '/meetings/meeting-1/items/h.3', sourceUrl: agenda.meetings.agenda_url })
    expect(result.limitations.join(' ')).toContain('not a complete history')
    expect(projection.is).toHaveBeenCalledWith('agenda_source_retired_at', null)
    expect(projection.is).toHaveBeenCalledWith('meetings.source_cancelled_at', null)
    expect(mocks.searchSite).toHaveBeenCalledTimes(2)
  })
  it('applies browse filters in the database before requesting the result page', async () => {
    const projection = page(Array.from({ length: 20 }, (_, index) => ({ ...agenda, id: `item-${index}` })), 21)
    const result = await searchCommons(request('topic=Housing&from=2026-01-01&to=2026-12-31'))
    expect(projection.eq).toHaveBeenCalledWith('topic_label', 'Housing')
    expect(projection.gte).toHaveBeenCalledWith('meetings.meeting_date', '2026-01-01')
    expect(projection.lte).toHaveBeenCalledWith('meetings.meeting_date', '2026-12-31')
    expect(projection.range).toHaveBeenCalledWith(0, 19)
    expect(result.hasMore).toBe(true)
    expect(mocks.searchSite).not.toHaveBeenCalled()
  })
  it('fills a browse page after a lower server cap without skipping matching records', async () => {
    const first = page([agenda], 2)
    const next = page([{ ...agenda, id: 'item-2' }], 2)
    const result = await searchCommons(request('mode=agenda'))
    expect(first.range).toHaveBeenCalledWith(0, 19)
    expect(next.range).toHaveBeenCalledWith(1, 19)
    expect(result.records.map(row => row.id)).toEqual(['item-1', 'item-2'])
    expect(result.hasMore).toBe(false)
  })
  it('keeps read failures and changed source sets distinct from empty results', async () => {
    page(null, null, { code: 'timeout' })
    await expect(searchCommons(request('mode=agenda'))).rejects.toThrow('temporarily unavailable')
    page([])
    await expect(searchCommons(request('q=housing'))).rejects.toThrow('temporarily unavailable')
  })
  it('rejects retired or mismatched source identities', async () => {
    for (const row of [{ ...agenda, agenda_source_retired_at: '2026-09-01' }, { ...agenda, meeting_id: 'other' }]) {
      page([row])
      await expect(searchCommons(request('q=housing'))).rejects.toThrow('temporarily unavailable')
    }
  })
  it('withholds an unlinked old item without hiding sourced results or claiming a complete count', async () => {
    mocks.searchSite.mockImplementation(async (_q: string, options: { offset: number }) => options.offset === 0 ? [{ id: agenda.id }, { id: 'unlinked' }] : [])
    page([agenda, { ...agenda, id: 'unlinked', meetings: { ...agenda.meetings, agenda_url: null, minutes_url: null } }])
    const result = await searchCommons(request('q=housing'))
    expect(result.records.map(row => row.id)).toEqual([agenda.id])
    expect(result.total).toBeNull()
    expect(result.limitations.join(' ')).toContain('original meeting document link is unavailable')
  })
  it('shows recorded motion choices while preserving unresolved conflicts and tentative source', async () => {
    page([agenda])
    page([{ id: 'motion-1', agenda_item_id: agenda.id, motion_text: 'Approve services', source: 'transcript', result: 'passed', sequence_number: 1, created_at: agenda.created_at }])
    page([{ id: 'vote-1', motion_id: 'motion-1', official_id: 'official-1', official_name: 'Member One', vote_choice: 'aye', source: 'transcript' },
      { id: 'vote-2', motion_id: 'motion-1', official_id: 'official-1', official_name: 'Member One', vote_choice: 'nay', source: 'transcript' }])
    const result = await searchCommons(request('q=housing&mode=votes'))
    expect(result.records[0]).toMatchObject({ kind: 'votes', motions: [{ source: 'transcript', votes: [{ name: 'Member One', choice: 'not-recorded' }] }] })
  })
  it('holds the verified erroneous Point Molate item while preserving ordinary minutes roll calls', async () => {
    vi.stubEnv('RICHMOND_READ_ONLY_STAGE', 'true')
    const held = { ...agenda, id: '9cf375c8-edc1-413c-8ee0-6485348fbc6f', meeting_id: '5f560013-daea-499a-8ecd-ca1a089c8a0c', item_number: 'J-2',
      title: 'Point Molate LDA Extension with Upstream Point Molate LLC', meetings: { ...agenda.meetings, id: '5f560013-daea-499a-8ecd-ca1a089c8a0c', meeting_date: '2010-03-02', agenda_url: null,
        minutes_url: 'https://www.ci.richmond.ca.us/Archive.aspx?ADID=2809' } }
    mocks.searchSite.mockImplementation(async (_q: string, options: { offset: number; resultType: string }) => options.offset === 0 && options.resultType === 'agenda_item' ? [{ id: held.id }, { id: agenda.id }] : [])
    page([held, agenda])
    const motions = page([{ id: 'ordinary-motion', agenda_item_id: agenda.id, motion_text: 'Approve services', source: 'minutes', result: 'passed', sequence_number: 1, created_at: agenda.created_at }])
    page([{ id: 'ordinary-vote', motion_id: 'ordinary-motion', official_id: 'official-1', official_name: 'Member One', vote_choice: 'aye', source: 'minutes' }])
    const result = await searchCommons(request('q=Point+Molate&mode=votes'))
    expect(result.records[0]).toMatchObject({ id: held.id, motions: [], voteSourceReview: { checkedAt: '2026-10-03' },
      url: '/meetings/5f560013-daea-499a-8ecd-ca1a089c8a0c/items/j-2', sourceUrl: 'https://www.ci.richmond.ca.us/ArchiveCenter/ViewFile/Item/2809' })
    expect(result.records[1]).toMatchObject({ motions: [{ result: 'passed', source: 'minutes', votes: [{ name: 'Member One', choice: 'aye' }] }] })
    expect(motions.in).toHaveBeenCalledWith('agenda_item_id', [agenda.id])
    expect(result.total).toBeNull()
    expect(result.limitations.join(' ')).toContain('held for source review')
  })
  it('matches reported recipient direction, preserves signed amounts, and never adds outside spending to donations', async () => {
    mocks.finance.mockResolvedValue({ events: [event, { ...event, event_key: 'wrong-direction', donor_name: 'Jimenez', recipient_name: 'Other committee' },
      { ...event, event_key: 'adjustment', amount: -25, amount_kind: 'negative_adjustment' },
      { ...event, event_key: 'outside', event_kind: 'independent_expenditure', candidate_name: 'Jimenez', amount: 500 }], coverage: [{ status: 'partial' }], truncated: true })
    const result = await searchCommons(request('q=Donations+to+Jimenez&mode=money'))
    expect(result.records.map(record => record.kind === 'money' && record.event.amount)).toEqual([100, -25])
    expect(result.limited).toBe(true)
    expect(result.coverage).toEqual([{ status: 'partial' }])
    expect(mocks.from).not.toHaveBeenCalled()
  })
  it('uses the same inclusive dates and page size for campaign records', async () => {
    mocks.finance.mockResolvedValue({ events: Array.from({ length: 21 }, (_, index) => ({ ...event, event_key: `event-${index}` })), coverage: [], truncated: false })
    const result = await searchCommons(request('mode=money&from=2026-08-01&to=2026-08-01&page=2'))
    expect(result.records).toHaveLength(1)
    expect(result.hasMore).toBe(false)
    expect(result.total).toBe(21)
  })
})
