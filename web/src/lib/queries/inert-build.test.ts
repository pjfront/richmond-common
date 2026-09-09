import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ from: vi.fn() }))
vi.mock('next/cache', () => ({ unstable_cache: (fn: unknown) => fn }))
vi.mock('react', async original => ({ ...await original<typeof import('react')>(), cache: (fn: unknown) => fn }))
vi.mock('./_shared', async original => ({ ...await original<typeof import('./_shared')>(), supabase: mocks }))

import { isInertBuild } from '../read-path-cache'
import { readCompleteRecords } from '../complete-record-read'
import { getCommissions } from './commissions'
import { getElections } from './elections'

const inertEnvironment = {
  RICHMOND_BUILD_USES_PRODUCTION_DATA: 'false',
  NEXT_PUBLIC_SUPABASE_URL: 'http://127.0.0.1:9',
  NEXT_PUBLIC_SUPABASE_ANON_KEY: 'preview-build-inert-anon-key',
}

function setInertEnvironment() {
  for (const [key, value] of Object.entries(inertEnvironment)) vi.stubEnv(key, value)
}

function failingQuery() {
  const q = { select: vi.fn(), eq: vi.fn(), order: vi.fn(), limit: vi.fn(),
    then: (resolve: (value: unknown) => unknown) => Promise.resolve({ data: null, count: null, error: new Error('offline') }).then(resolve) }
  for (const method of [q.select, q.eq, q.order, q.limit]) method.mockReturnValue(q)
  return q
}

describe('isolated PR build read boundary', () => {
  beforeEach(() => { mocks.from.mockReset(); mocks.from.mockImplementation(failingQuery) })
  afterEach(() => vi.unstubAllEnvs())

  it('skips all new strict list reads only for the exact CI placeholder triplet, without making a query', async () => {
    setInertEnvironment()
    const read = vi.fn(async () => ({ data: null, count: null, error: new Error('offline') }))
    expect(isInertBuild()).toBe(true)
    expect(await readCompleteRecords('Records', read)).toEqual([])
    expect(await getCommissions()).toEqual([])
    expect(await getElections()).toEqual([])
    expect(read).not.toHaveBeenCalled()
    expect(mocks.from).not.toHaveBeenCalled()
  })

  it.each([
    ['RICHMOND_BUILD_USES_PRODUCTION_DATA', undefined],
    ['RICHMOND_BUILD_USES_PRODUCTION_DATA', 'true'],
    ['NEXT_PUBLIC_SUPABASE_URL', undefined],
    ['NEXT_PUBLIC_SUPABASE_URL', 'https://example.supabase.co'],
    ['NEXT_PUBLIC_SUPABASE_ANON_KEY', undefined],
    ['NEXT_PUBLIC_SUPABASE_ANON_KEY', 'different-key'],
  ])('retains failures when the triplet is incomplete or mismatched: %s=%s', async (key, value) => {
    setInertEnvironment()
    vi.stubEnv(key, value)
    expect(isInertBuild()).toBe(false)
    const read = vi.fn(async () => ({ data: null, count: null, error: new Error('offline') }))
    await expect(readCompleteRecords('Records', read)).rejects.toThrow('temporarily unavailable')
    await expect(getCommissions()).rejects.toThrow('roster unavailable')
    await expect(getElections()).rejects.toThrow('temporarily unavailable')
    expect(read).toHaveBeenCalledTimes(1)
    expect(mocks.from).toHaveBeenCalledTimes(2)
  })

  it('does not treat NODE_ENV=production alone as an inert build or suppress a production error', async () => {
    vi.stubEnv('NODE_ENV', 'production')
    for (const key of Object.keys(inertEnvironment)) vi.stubEnv(key, undefined)
    expect(isInertBuild()).toBe(false)
    await expect(getElections()).rejects.toThrow('temporarily unavailable')
    expect(mocks.from).toHaveBeenCalledTimes(1)
  })
})
