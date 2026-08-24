import { beforeEach, describe, expect, it, vi } from 'vitest'

const NOT_FOUND = new Error('NEXT_HTTP_ERROR_FALLBACK;404')

const mocks = vi.hoisted(() => ({
  isOperatorAuthenticated: vi.fn(),
  notFound: vi.fn(),
}))

vi.mock('./operator-auth', () => ({
  isOperatorAuthenticated: mocks.isOperatorAuthenticated,
}))

vi.mock('next/navigation', () => ({
  notFound: mocks.notFound,
}))

import { requireOperatorPage } from './operator-page'

describe('requireOperatorPage', () => {
  beforeEach(() => {
    mocks.isOperatorAuthenticated.mockReset()
    mocks.notFound.mockReset()
    mocks.notFound.mockImplementation(() => {
      throw NOT_FOUND
    })
  })

  it('allows only a proven operator session', async () => {
    mocks.isOperatorAuthenticated.mockResolvedValue(true)

    await expect(requireOperatorPage()).resolves.toBeUndefined()
    expect(mocks.notFound).not.toHaveBeenCalled()
  })

  it('fails closed with Next.js notFound semantics for an anonymous session', async () => {
    mocks.isOperatorAuthenticated.mockResolvedValue(false)

    await expect(requireOperatorPage()).rejects.toBe(NOT_FOUND)
    expect(mocks.notFound).toHaveBeenCalledOnce()
  })

  it('does not turn an authentication failure into access', async () => {
    const authFailure = new Error('session unavailable')
    mocks.isOperatorAuthenticated.mockRejectedValue(authFailure)

    await expect(requireOperatorPage()).rejects.toBe(authFailure)
    expect(mocks.notFound).not.toHaveBeenCalled()
  })
})
