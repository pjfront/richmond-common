import { beforeEach, describe, expect, it, vi } from 'vitest'
const mocks = vi.hoisted(() => ({ requireOperatorPage: vi.fn(), getDivergentMotions: vi.fn(),
  getCategoryStats: vi.fn(), getControversialItems: vi.fn(), getCrossMeetingPatterns: vi.fn() }))
vi.mock('@/lib/operator-page', () => ({ requireOperatorPage: mocks.requireOperatorPage }))
vi.mock('@/lib/queries', () => mocks)
import Page from './page'

describe('public analytics authorization boundary', () => {
  beforeEach(() => vi.clearAllMocks())
  it.each(['stats', 'patterns'])('authorizes %s before queries or server-rendered private children', async tab => {
    const denied = new Error('not authorized')
    mocks.requireOperatorPage.mockRejectedValueOnce(denied)
    await expect(Page({ searchParams: Promise.resolve({ tab }) })).rejects.toBe(denied)
    expect(mocks.getCategoryStats).not.toHaveBeenCalled()
    expect(mocks.getControversialItems).not.toHaveBeenCalled()
    expect(mocks.getCrossMeetingPatterns).not.toHaveBeenCalled()
  })
  it('keeps the source record page public without querying private analyses', async () => {
    expect(await Page({ searchParams: Promise.resolve({}) })).toBeTruthy()
    expect(mocks.requireOperatorPage).not.toHaveBeenCalled()
    expect(mocks.getCategoryStats).not.toHaveBeenCalled()
    expect(mocks.getCrossMeetingPatterns).not.toHaveBeenCalled()
  })
})
