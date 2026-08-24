import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocked = vi.hoisted(() => ({ from: vi.fn() }))

vi.mock('react', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react')>()
  return { ...actual, cache: <T extends (...args: never[]) => unknown>(loader: T) => loader }
})

vi.mock('./_shared', () => ({
  supabase: { from: mocked.from },
  RICHMOND_FIPS: '0660620',
  COLS_ELECTION_FRONT_DOOR: 'election_projection',
  COLS_MEETING_FRONT_DOOR: 'meeting_projection',
  COLS_FRONT_DOOR_SOURCE_DOCUMENT: 'ingested_at, source_url, credibility_tier',
}))

import { getFrontDoorElection, getFrontDoorMeeting } from './front-door'

afterEach(() => {
  vi.useRealTimers()
})

type QueryError = { code: string; message: string }
type QueryResult = { data: unknown; error: QueryError | null }

interface QueryCalls {
  select: string[]
  eq: Array<[string, unknown]>
  is: Array<[string, unknown]>
  not: Array<[string, string, unknown]>
  neq: Array<[string, unknown]>
  contains: Array<[string, unknown]>
  gte: Array<[string, unknown]>
  lt: Array<[string, unknown]>
  limit: number[]
}

function queryBuilder(result: QueryResult, calls: QueryCalls) {
  const builder: Record<string, unknown> = {}
  const chain = () => builder

  builder.select = vi.fn((projection: string) => {
    calls.select.push(projection)
    return builder
  })
  builder.eq = vi.fn((column: string, value: unknown) => {
    calls.eq.push([column, value])
    return builder
  })
  builder.is = vi.fn((column: string, value: unknown) => {
    calls.is.push([column, value])
    return builder
  })
  builder.not = vi.fn((column: string, operator: string, value: unknown) => {
    calls.not.push([column, operator, value])
    return builder
  })
  builder.neq = vi.fn((column: string, value: unknown) => {
    calls.neq.push([column, value])
    return builder
  })
  builder.contains = vi.fn((column: string, value: unknown) => {
    calls.contains.push([column, value])
    return builder
  })
  builder.gte = vi.fn((column: string, value: unknown) => {
    calls.gte.push([column, value])
    return builder
  })
  builder.lt = vi.fn((column: string, value: unknown) => {
    calls.lt.push([column, value])
    return builder
  })
  builder.limit = vi.fn((value: number) => {
    calls.limit.push(value)
    return builder
  })
  for (const method of ['order', 'abortSignal']) builder[method] = vi.fn(chain)
  builder.maybeSingle = vi.fn(async () => result)

  return builder
}

function installResponses(responses: Record<string, QueryResult[]>) {
  const callsByTable = new Map<string, QueryCalls[]>()
  mocked.from.mockImplementation((table: string) => {
    const result = responses[table]?.shift()
    if (!result) throw new Error(`Unexpected query for ${table}`)

    const calls: QueryCalls = {
      select: [],
      eq: [],
      is: [],
      not: [],
      neq: [],
      contains: [],
      gte: [],
      lt: [],
      limit: [],
    }
    callsByTable.set(table, [...(callsByTable.get(table) ?? []), calls])
    return queryBuilder(result, calls)
  })
  return callsByTable
}

function election(overrides: Record<string, unknown> = {}) {
  return {
    id: 'election-1',
    city_fips: '0660620',
    election_date: '2099-11-03',
    election_name: '2099 General Election',
    election_type: 'general',
    filing_deadline: null,
    jurisdiction: 'Richmond, California',
    notes: null,
    source: 'City of Richmond',
    source_tier: 1,
    source_url: 'https://example.test/election',
    created_at: '2099-01-01T00:00:00Z',
    updated_at: '2099-08-01T00:00:00Z',
    ...overrides,
  }
}

function meeting() {
  return {
    id: 'meeting-1',
    meeting_date: '2099-08-18',
    meeting_type: 'regular',
    agenda_url: 'https://example.test/meeting',
    source_meeting_guid: 'meeting-guid-1',
    bodies: { name: 'Richmond City Council' },
  }
}

describe('getFrontDoorElection', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
  })

  it('returns one projected Tier 1-2 election with an exact source URL', async () => {
    const calls = installResponses({ elections: [{ data: election(), error: null }] })

    await expect(getFrontDoorElection()).resolves.toMatchObject({
      state: 'ready',
      data: {
        source_url: 'https://example.test/election',
        extracted_at: '2099-01-01T00:00:00Z',
        source_tier: 1,
        confidence_score: 1,
      },
    })
    expect(calls.get('elections')![0].select).toEqual(['election_projection'])
    expect(calls.get('elections')![0].limit).toEqual([1])
  })

  it('queries from Richmond civil today after the UTC date rolls over', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-25T00:30:00Z'))
    const calls = installResponses({ elections: [{ data: election(), error: null }] })

    await getFrontDoorElection()

    expect(calls.get('elections')![0].gte).toContainEqual([
      'election_date',
      '2026-08-24',
    ])
  })

  it.each([
    { source_tier: 3 },
    { source_url: null },
    { source_url: '   ' },
    { created_at: '' },
  ])('treats an ineligible public election as genuinely empty: %o', async (override) => {
    installResponses({ elections: [{ data: election(override), error: null }] })

    await expect(getFrontDoorElection()).resolves.toEqual({ state: 'empty', data: null })
  })

  it('distinguishes a query failure from no upcoming election', async () => {
    installResponses({
      elections: [{ data: null, error: { code: '57014', message: 'timed out' } }],
    })

    await expect(getFrontDoorElection()).resolves.toEqual({ state: 'error', data: null })
  })
})

describe('getFrontDoorMeeting', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
  })

  it('returns complete public provenance from the active Tier 1 source observation', async () => {
    const calls = installResponses({
      meetings: [{ data: meeting(), error: null }],
      documents: [{
        data: {
          ingested_at: '2099-08-12T12:00:00Z',
          source_url: 'https://example.test/exact-agenda',
          credibility_tier: 1,
        },
        error: null,
      }],
    })

    await expect(getFrontDoorMeeting()).resolves.toEqual({
      state: 'ready',
      data: {
        id: 'meeting-1',
        meeting_date: '2099-08-18',
        meeting_type: 'regular',
        source_url: 'https://example.test/exact-agenda',
        extracted_at: '2099-08-12T12:00:00Z',
        source_tier: 1,
        confidence_score: 1,
        body_name: 'Richmond City Council',
      },
    })

    const meetingCalls = calls.get('meetings')![0]
    expect(meetingCalls.select).toEqual(['meeting_projection'])
    expect(meetingCalls.is).toContainEqual(['source_cancelled_at', null])
    expect(meetingCalls.neq).toContainEqual(['agenda_url', ''])
    expect(meetingCalls.limit).toEqual([1])

    const sourceCalls = calls.get('documents')![0]
    expect(sourceCalls.select).toEqual(['ingested_at, source_url, credibility_tier'])
    expect(sourceCalls.eq).toContainEqual(['credibility_tier', 1])
    expect(sourceCalls.contains).toEqual([
      ['metadata', {
        source_observation_state: 'complete_agenda',
        meeting_guid: 'meeting-guid-1',
      }],
    ])
    expect(sourceCalls.limit).toEqual([1])
  })

  it('queries from Richmond civil today after the UTC date rolls over', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-25T00:30:00Z'))
    const calls = installResponses({
      meetings: [{ data: meeting(), error: null }],
      documents: [{
        data: {
          ingested_at: '2099-08-12T12:00:00Z',
          source_url: 'https://example.test/exact-agenda',
          credibility_tier: 1,
        },
        error: null,
      }],
    })

    await getFrontDoorMeeting()

    expect(calls.get('meetings')![0].gte).toContainEqual([
      'meeting_date',
      '2026-08-24',
    ])
  })

  it('falls back to one bounded past meeting when no future meeting exists', async () => {
    const calls = installResponses({
      meetings: [
        { data: null, error: null },
        { data: meeting(), error: null },
      ],
      documents: [{
        data: {
          ingested_at: '2099-08-12T12:00:00Z',
          source_url: null,
          credibility_tier: 1,
        },
        error: null,
      }],
    })

    const result = await getFrontDoorMeeting()

    expect(result.state).toBe('ready')
    expect(calls.get('meetings')).toHaveLength(2)
    expect(calls.get('meetings')![1].lt).toHaveLength(1)
    expect(calls.get('meetings')![1].limit).toEqual([1])
  })

  it('fails to the static card unless the source row proves Tier 1 provenance', async () => {
    installResponses({
      meetings: [{ data: meeting(), error: null }],
      documents: [{
        data: {
          ingested_at: '2099-08-12T12:00:00Z',
          source_url: 'https://example.test/exact-agenda',
          credibility_tier: 2,
        },
        error: null,
      }],
    })

    await expect(getFrontDoorMeeting()).resolves.toEqual({ state: 'empty', data: null })
  })

  it('returns empty only when both bounded meeting reads are empty', async () => {
    installResponses({
      meetings: [
        { data: null, error: null },
        { data: null, error: null },
      ],
    })

    await expect(getFrontDoorMeeting()).resolves.toEqual({ state: 'empty', data: null })
  })

  it('distinguishes meeting and source-observation failures from empty data', async () => {
    installResponses({
      meetings: [{ data: meeting(), error: null }],
      documents: [{ data: null, error: { code: '57014', message: 'timed out' } }],
    })

    await expect(getFrontDoorMeeting()).resolves.toEqual({ state: 'error', data: null })
  })
})
