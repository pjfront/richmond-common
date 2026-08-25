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
  COLS_PUBLIC_RECORD_LIST: 'id',
}))

vi.mock('./council', () => ({ getOfficials: mocked.getOfficials }))

import { getAgendaItemDetail } from './meetings'

const MEETING_ID = '5065ce72-b5df-4e4c-b4f6-c6966aa1610f'
const ITEM_ID = '736aaece-c05d-4d14-9ec6-814350496448'

type QueryResult = { data: unknown; error: null }

interface QueryCalls {
  or: string[]
}

function queryBuilder(result: QueryResult, calls: QueryCalls) {
  const builder: Record<string, unknown> = {}
  const chain = () => builder

  for (const method of ['select', 'is', 'ilike', 'single', 'order', 'neq', 'in', 'eq', 'limit']) {
    builder[method] = vi.fn(chain)
  }
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

function installItemDetailResponses() {
  const responses: Record<string, QueryResult[]> = {
    agenda_items: [
      {
        data: {
          id: ITEM_ID,
          meeting_id: MEETING_ID,
          item_number: 'STUDY-1',
          title: 'Wastewater study',
          topic_label: 'Wastewater Treatment',
          category: 'infrastructure',
          public_comment_count: 0,
          continued_from: 'August 19, 2025',
          continued_to: 'future meeting',
          meetings: {
            meeting_date: '2026-08-18',
            meeting_type: 'Regular',
            agenda_url: 'https://example.test/agenda',
            minutes_url: 'https://example.test/minutes',
          },
        },
        error: null,
      },
      {
        data: [{ item_number: 'STUDY-1', summary_headline: null, title: 'Wastewater study' }],
        error: null,
      },
    ],
    motions: [{ data: [], error: null }],
    public_comments: [{ data: [], error: null }],
    item_theme_narratives: [{ data: [], error: null }],
  }
  const callsByTable = new Map<string, QueryCalls[]>()

  mocked.from.mockImplementation((table: string) => {
    const result = responses[table]?.shift()
    if (!result) throw new Error(`Unexpected query for ${table}`)

    const calls: QueryCalls = { or: [] }
    callsByTable.set(table, [...(callsByTable.get(table) ?? []), calls])
    return queryBuilder(result, calls)
  })

  return callsByTable
}

describe('agenda item detail read containment', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocked.getOfficials.mockResolvedValue([])
  })

  it('does not issue legacy topic/category or related-motion lookups', async () => {
    const calls = installItemDetailResponses()

    const item = await getAgendaItemDetail(MEETING_ID, 'STUDY-1')

    expect(item).not.toBeNull()
    expect(item?.continued_from_item).toBeNull()
    expect(item?.continued_to_item).toBeNull()
    expect(item).not.toHaveProperty('related_topic_items')
    expect(mocked.from.mock.calls.filter(([table]) => table === 'agenda_items')).toHaveLength(2)
    expect(mocked.from.mock.calls.filter(([table]) => table === 'motions')).toHaveLength(1)
    expect([...calls.values()].flat().flatMap((entry) => entry.or)).toEqual([])
  })
})
