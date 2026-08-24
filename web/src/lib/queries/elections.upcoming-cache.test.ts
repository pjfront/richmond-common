import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocked = vi.hoisted(() => {
  const cacheCalls: Array<{ keyParts: string[]; revalidate: number }> = []

  return {
    from: vi.fn(),
    select: vi.fn(),
    cacheCalls,
    unstableCache: vi.fn((
      loader: (...args: string[]) => Promise<unknown>,
      keyParts: string[],
      options: { revalidate: number },
    ) => {
      cacheCalls.push({ keyParts, revalidate: options.revalidate })
      const results = new Map<string, Promise<unknown>>()
      return (...args: string[]) => {
        const key = JSON.stringify(args)
        const existing = results.get(key)
        if (existing) return existing
        const pending = loader(...args)
        results.set(key, pending)
        pending.catch(() => {
          if (results.get(key) === pending) results.delete(key)
        })
        return pending
      }
    }),
  }
})

vi.mock('next/cache', () => ({
  unstable_cache: mocked.unstableCache,
}))

vi.mock('./_shared', () => ({
  supabase: { from: mocked.from },
  RICHMOND_FIPS: '0660620',
  warnIfEmpty: vi.fn(),
  nameToSlug: vi.fn((value: string) => value),
  isGovernmentEntity: vi.fn(() => false),
  filterGovernmentEntityFlags: vi.fn((value: unknown) => value),
  COLS_MEETING_LIST: 'id',
  COLS_MEETING_BANNER: 'id',
  COLS_UPCOMING_ELECTION: 'id, election_date, election_type, election_name',
  COLS_FLAG_SUMMARY: 'id',
  COLS_PUBLIC_RECORD_LIST: 'id',
  COLS_CONTRIBUTION_PUBLIC: 'id',
}))

import { getUpcomingElection } from './elections'

function electionQuery(
  result: {
    data: Record<string, unknown> | null
    error: Record<string, unknown> | null
  } = {
    data: {
      id: 'election-1',
      city_fips: '0660620',
      election_date: '2026-11-03',
      election_type: 'general',
    },
    error: null,
  },
) {
  const builder: Record<string, unknown> = {}
  const chain = () => builder
  builder.select = mocked.select.mockImplementation(chain)
  for (const method of ['eq', 'gte', 'order', 'limit', 'maybeSingle']) {
    builder[method] = vi.fn(chain)
  }
  builder.then = (onFulfilled: (value: typeof result) => unknown) => (
    Promise.resolve(result).then(onFulfilled)
  )
  return builder
}

describe('upcoming-election shared read cache', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-08-24T12:00:00Z'))
    mocked.from.mockReset()
    mocked.select.mockReset()
    mocked.from.mockImplementation(() => electionQuery())
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it('deduplicates the navigation query across paths while keying by UTC day', async () => {
    await getUpcomingElection()
    await getUpcomingElection()
    expect(mocked.from).toHaveBeenCalledTimes(1)
    expect(mocked.select).toHaveBeenCalledWith(
      'id, election_date, election_type, election_name',
    )

    vi.setSystemTime(new Date('2026-08-25T00:00:01Z'))
    await getUpcomingElection()
    expect(mocked.from).toHaveBeenCalledTimes(2)

    expect(mocked.cacheCalls).toEqual([{
      keyParts: ['upcoming-election-read-v1'],
      revalidate: 86_400,
    }])
  })

  it('omits the navigation link when the explicitly inert build cannot read elections', async () => {
    vi.stubEnv('RICHMOND_BUILD_USES_PRODUCTION_DATA', 'false')
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    mocked.from.mockImplementation(() => electionQuery({
      data: null,
      error: { message: 'inert database is unreachable' },
    }))

    await expect(getUpcomingElection('inert-fips')).resolves.toBeNull()
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining('explicitly inert CI build'),
    )
  })

  it('omits a failed runtime nav read without caching it, then recovers', async () => {
    vi.stubEnv('RICHMOND_BUILD_USES_PRODUCTION_DATA', 'true')
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    mocked.from
      .mockImplementationOnce(() => electionQuery({
        data: null,
        error: { message: 'statement timeout' },
      }))
      .mockImplementation(() => electionQuery())

    await expect(getUpcomingElection('runtime-fips')).resolves.toBeNull()
    await expect(getUpcomingElection('runtime-fips')).resolves.toMatchObject({
      id: 'election-1',
    })
    expect(mocked.from).toHaveBeenCalledTimes(2)
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining('ACTION: If this warning persists'),
    )
  })
})
