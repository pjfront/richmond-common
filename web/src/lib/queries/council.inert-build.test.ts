import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const query = vi.hoisted(() => ({
  from: vi.fn(),
  select: vi.fn(),
  eq: vi.fn(),
  order: vi.fn(),
}))

vi.mock('next/cache', () => ({
  unstable_cache: (loader: (...args: unknown[]) => unknown) => loader,
}))

vi.mock('./_shared', async (importOriginal) => ({
  ...await importOriginal<typeof import('./_shared')>(),
  supabase: { from: query.from },
}))

import { getOfficials } from './council'

describe('getOfficials inert-build boundary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    query.from.mockReturnValue(query)
    query.select.mockReturnValue(query)
    query.eq.mockReturnValue(query)
    query.order.mockResolvedValue({
      data: null,
      error: { message: 'inert database is unreachable' },
    })
    vi.spyOn(console, 'error').mockImplementation(() => undefined)
    vi.spyOn(console, 'warn').mockImplementation(() => undefined)
  })

  afterEach(() => {
    vi.unstubAllEnvs()
    vi.restoreAllMocks()
  })

  it('uses an empty deterministic fallback only for the explicit inert CI build', async () => {
    vi.stubEnv('RICHMOND_BUILD_USES_PRODUCTION_DATA', 'false')

    await expect(getOfficials()).resolves.toEqual([])
    expect(console.warn).toHaveBeenCalledWith(
      expect.stringContaining('explicitly inert CI build'),
    )
  })

  it.each([
    ['production integration build', 'true'],
    ['normal runtime with no build override', undefined],
  ])('fails closed in a %s', async (_context, boundary) => {
    vi.stubEnv('RICHMOND_BUILD_USES_PRODUCTION_DATA', boundary)

    await expect(getOfficials()).rejects.toMatchObject({
      name: 'ReadPathUnavailableError',
      readPath: 'Officials',
    })
    expect(console.warn).not.toHaveBeenCalled()
  })
})
