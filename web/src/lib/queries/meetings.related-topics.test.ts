import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocked = vi.hoisted(() => ({
  from: vi.fn(),
  getOfficials: vi.fn(),
}))

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return { ...actual, cache: <T extends (...args: never[]) => unknown>(loader: T) => loader }
})

vi.mock('./_shared', () => ({
  supabase: { from: mocked.from },
  RICHMOND_FIPS: '0660620',
  warnIfEmpty: vi.fn(),
  nameToSlug: vi.fn((value: string) => value),
  isGovernmentEntity: vi.fn(() => false),
  filterGovernmentEntityFlags: vi.fn((value: unknown) => value),
  COLS_MEETING_LIST: 'id',
  COLS_MEETING_BANNER: 'id',
  COLS_RELATED_TOPIC_ITEM: 'id',
  COLS_PUBLIC_RECORD_LIST: 'id',
}))

vi.mock('./council', () => ({ getOfficials: mocked.getOfficials }))

import { getAgendaItemDetail } from './meetings'

const TIMEOUT_FIXTURE_MEETING_ID = '5065ce72-b5df-4e4c-b4f6-c6966aa1610f'
const TIMEOUT_FIXTURE_ITEM_ID = '736aaece-c05d-4d14-9ec6-814350496448'
const TIMEOUT_FIXTURE_TOPIC = 'Wastewater Treatment'
const TIMEOUT_FIXTURE_CATEGORY = 'infrastructure'

type QueryError = { code: string; message: string }
type QueryResult = { data: unknown; error: QueryError | null }

interface QueryCalls {
  eq: Array<[string, unknown]>
  limit: number[]
  or: string[]
}

function queryBuilder(result: QueryResult, calls: QueryCalls) {
  const builder: Record<string, unknown> = {}
  const chain = () => builder

  for (const method of ['select', 'is', 'ilike', 'single', 'order', 'neq', 'in']) {
    builder[method] = vi.fn(chain)
  }
  builder.eq = vi.fn((column: string, value: unknown) => {
    calls.eq.push([column, value])
    return builder
  })
  builder.limit = vi.fn((value: number) => {
    calls.limit.push(value)
    return builder
  })
  builder.or = vi.fn((value: string) => {
    calls.or.push(value)
    return builder
  })
  builder.then = (
    onFulfilled: (value: QueryResult) => unknown,
    onRejected?: (reason: unknown) => unknown,
  ) => Promise.resolve(result).then(onFulfilled, onRejected)

  return builder
}

function meetingRow(id: string, date: string, overrides: Record<string, unknown> = {}) {
  return {
    id,
    meeting_id: TIMEOUT_FIXTURE_MEETING_ID,
    item_number: id,
    title: `Item ${id}`,
    summary_headline: null,
    topic_label: TIMEOUT_FIXTURE_TOPIC,
    category: TIMEOUT_FIXTURE_CATEGORY,
    financial_amount: null,
    public_comment_count: 0,
    meetings: { meeting_date: date, minutes_url: 'https://example.test/minutes' },
    ...overrides,
  }
}

function installResponses(responses: Record<string, QueryResult[]>) {
  const callsByTable = new Map<string, QueryCalls[]>()
  mocked.from.mockImplementation((table: string) => {
    const result = responses[table]?.shift()
    if (!result) throw new Error(`Unexpected query for ${table}`)

    const calls: QueryCalls = { eq: [], limit: [], or: [] }
    const existing = callsByTable.get(table) ?? []
    existing.push(calls)
    callsByTable.set(table, existing)
    return queryBuilder(result, calls)
  })
  return callsByTable
}

function baseResponses(
  relatedAgendaItems: QueryResult[],
  baseItemOverrides: Record<string, unknown> = {},
): Record<string, QueryResult[]> {
  return {
    agenda_items: [
      {
        data: {
          ...meetingRow('base', '2026-08-18'),
          ...baseItemOverrides,
          id: TIMEOUT_FIXTURE_ITEM_ID,
          item_number: 'STUDY-1',
          continued_from: null,
          continued_to: null,
          meetings: {
            meeting_date: '2026-08-18',
            meeting_type: 'Regular',
            agenda_url: 'https://example.test/agenda',
            minutes_url: 'https://example.test/minutes',
          },
        },
        error: null,
      },
      { data: [{ item_number: 'STUDY-1', summary_headline: null, title: 'Base item' }], error: null },
      ...relatedAgendaItems,
    ],
    motions: [{ data: [], error: null }],
    public_comments: [{ data: [], error: null }],
    item_theme_narratives: [{ data: [], error: null }],
  }
}

describe('agenda item related-topic reads', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocked.getOfficials.mockResolvedValue([])
  })

  it('escapes a PostgREST timeout instead of turning it into a cached empty section', async () => {
    const timeout = { code: '57014', message: 'canceling statement due to statement timeout' }
    const calls = installResponses(baseResponses([
      { data: null, error: timeout },
    ]))

    await expect(getAgendaItemDetail(
      TIMEOUT_FIXTURE_MEETING_ID,
      'STUDY-1',
    )).rejects.toBe(timeout)

    const relatedCalls = calls.get('agenda_items')!.slice(2)
    expect(relatedCalls).toHaveLength(1)
    expect(relatedCalls.flatMap((entry) => entry.eq).map(([column]) => column))
      .not.toContain('meetings.city_fips')
    expect(relatedCalls.flatMap((entry) => entry.or)).toEqual([
      `topic_label.eq."${TIMEOUT_FIXTURE_TOPIC}",category.eq."${TIMEOUT_FIXTURE_CATEGORY}"`,
    ])
    expect(relatedCalls.map((entry) => entry.limit)).toEqual([[30]])
  })

  it('does not treat descriptive continuation labels as agenda item numbers', async () => {
    const calls = installResponses(baseResponses(
      [{ data: [], error: null }],
      {
        continued_from: 'August 19, 2025',
        continued_to: 'future meeting',
      },
    ))

    const item = await getAgendaItemDetail(
      TIMEOUT_FIXTURE_MEETING_ID,
      'STUDY-1',
    )

    expect(item?.continued_from_item).toBeNull()
    expect(item?.continued_to_item).toBeNull()
    // Base item + siblings + related-topic result. Continuation labels must
    // not add impossible agenda_items lookups (which previously returned 406).
    expect(calls.get('agenda_items')).toHaveLength(3)
  })

  it('preserves topic-before-category relevance for the bounded OR result', async () => {
    const shared = meetingRow('shared', '2026-08-17')
    const topicOnly = meetingRow('topic-only', '2026-08-15', { category: 'planning' })
    const categoryOnly = meetingRow('category-only', '2026-08-16', { topic_label: 'Budget' })
    const responses = baseResponses([
      { data: [shared, categoryOnly, topicOnly], error: null },
    ])
    responses.motions.push({
      data: [{ agenda_item_id: 'shared', result: 'Approved' }],
      error: null,
    })
    installResponses(responses)

    const item = await getAgendaItemDetail(
      TIMEOUT_FIXTURE_MEETING_ID,
      'STUDY-1',
    )

    expect(item?.related_topic_items.map(({ id, match_tier }) => ({ id, match_tier }))).toEqual([
      { id: 'shared', match_tier: 1 },
      { id: 'topic-only', match_tier: 2 },
      { id: 'category-only', match_tier: 3 },
    ])
    expect(item?.related_topic_items[0].vote_outcome).toBe('passed')
  })

  it('quotes reserved punctuation in the raw PostgREST OR grammar', async () => {
    const calls = installResponses(baseResponses(
      [{ data: [], error: null }],
      { topic_label: 'Pastor Kellis B. Love, Sr.', category: 'proclamation' },
    ))

    await getAgendaItemDetail(TIMEOUT_FIXTURE_MEETING_ID, 'STUDY-1')

    expect(calls.get('agenda_items')![2].or).toEqual([
      'topic_label.eq."Pastor Kellis B. Love, Sr.",category.eq."proclamation"',
    ])
  })

  it('escapes quotes and backslashes inside PostgREST literals', async () => {
    const calls = installResponses(baseResponses(
      [{ data: [], error: null }],
      { topic_label: 'Quote: "A\\B", Test', category: 'proclamation' },
    ))

    await getAgendaItemDetail(TIMEOUT_FIXTURE_MEETING_ID, 'STUDY-1')

    expect(calls.get('agenda_items')![2].or).toEqual([
      'topic_label.eq."Quote: \\"A\\\\B\\", Test",category.eq."proclamation"',
    ])
  })

  it('escapes a related-motion failure rather than caching incorrect outcomes', async () => {
    const failure = { code: '57014', message: 'motion lookup timed out' }
    const responses = baseResponses([
      { data: [meetingRow('related', '2026-08-17')], error: null },
    ])
    responses.motions.push({ data: null, error: failure })
    installResponses(responses)

    await expect(getAgendaItemDetail(
      TIMEOUT_FIXTURE_MEETING_ID,
      'STUDY-1',
    )).rejects.toBe(failure)
  })
})
