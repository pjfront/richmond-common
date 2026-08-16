import { describe, expect, it, vi } from 'vitest'
import { reloadIntoOperatorSession, safeOperatorDestination } from './operator-navigation'

describe('safeOperatorDestination', () => {
  it('keeps an internal operator destination', () => {
    expect(safeOperatorDestination('/operator/decisions?from=login')).toBe(
      '/operator/decisions?from=login',
    )
  })

  it.each([
    null,
    '/',
    '/meetings',
    '//evil.example/operator/settings',
    '/operator/../meetings',
    '/operator\\settings',
  ])('falls back for an unsafe destination: %s', (candidate) => {
    expect(safeOperatorDestination(candidate)).toBe('/operator/settings')
  })
})

describe('reloadIntoOperatorSession', () => {
  it('forces a full document navigation after login', () => {
    const assign = vi.fn()

    reloadIntoOperatorSession('/operator/decisions', { assign } as unknown as Location)

    expect(assign).toHaveBeenCalledWith('/operator/decisions')
  })
})
