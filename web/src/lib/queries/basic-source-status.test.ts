import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ from: vi.fn(), profile: vi.fn(), local: vi.fn() }))
vi.mock('next/cache', () => ({ unstable_cache: (fn: unknown) => fn }))
vi.mock('@/lib/supabase', () => ({ supabase: { from: mocks.from } }))
vi.mock('@/lib/feature-policy', () => ({ featureProfile: mocks.profile, isLocalArchive: mocks.local }))
import { getBasicSourceRefreshStatus } from './basic-source-status'

function projection(data: object[] | null, count: number | null, error: object | null = null) {
  const query = { select: vi.fn(), in: vi.fn(), order: vi.fn(), limit: vi.fn(), then: (resolve: (value: object) => unknown) => Promise.resolve({ data, count, error }).then(resolve) }
  for (const method of [query.select, query.in, query.order, query.limit]) method.mockReturnValue(query)
  mocks.from.mockReturnValue(query)
  return query
}

beforeEach(() => { mocks.from.mockReset(); mocks.profile.mockReturnValue('basic_public'); mocks.local.mockReturnValue(false) })

describe('anon-only basic source status projection', () => {
  it('queries only the approved metadata columns and two feature identities', async () => {
    const query = projection([{ feature: 'finance', status: 'partial', checked_at: null, source_scope: '0660620:calendar-2026' }], 1)
    const status = await getBasicSourceRefreshStatus()
    expect(mocks.from).toHaveBeenCalledWith('core_projection_status')
    expect(query.select).toHaveBeenCalledWith('feature,status,checked_at,source_scope', { count: 'exact' })
    expect(query.in).toHaveBeenCalledWith('feature', ['agenda_refresh', 'finance'])
    expect(query.limit).toHaveBeenCalledWith(2)
    expect(status?.finance.state).toBe('never_checked')
    expect(status?.agenda_refresh.state).toBe('never_checked')
  })
  it.each(['local_archive', 'reviewed_public', 'paid_public'])('does not query compact refresh metadata for %s', profile => {
    mocks.profile.mockReturnValue(profile)
    return expect(getBasicSourceRefreshStatus()).resolves.toBeNull().then(() => expect(mocks.from).not.toHaveBeenCalled())
  })
  it('does not query when the local archive flag is active even with a basic profile override', async () => {
    mocks.local.mockReturnValue(true)
    expect(await getBasicSourceRefreshStatus()).toBeNull()
    expect(mocks.from).not.toHaveBeenCalled()
  })
  it.each([
    { data: null, count: null, error: { code: '42P01' } },
    { data: [], count: 1, error: null },
    { data: [{ feature: 'private_operator' }], count: 1, error: null },
    { data: [{ feature: 'finance' }, { feature: 'finance' }], count: 2, error: null },
  ])('reports failed or incomplete metadata as unavailable: %j', async ({ data, count, error }) => {
    projection(data, count, error)
    const status = await getBasicSourceRefreshStatus()
    expect(status?.agenda_refresh.state).toBe('unavailable')
    expect(status?.finance.state).toBe('unavailable')
  })
})
