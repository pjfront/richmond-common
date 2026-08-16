import { afterEach, describe, expect, it, vi } from 'vitest'
import { getOperatorSessionOptions } from './operator-session'

describe('getOperatorSessionOptions', () => {
  afterEach(() => {
    vi.unstubAllEnvs()
  })

  it('fails closed when the production secret is missing', () => {
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('IRON_SESSION_PASSWORD', '')

    expect(() => getOperatorSessionOptions()).toThrow(
      /IRON_SESSION_PASSWORD is required in production/,
    )
  })

  it('allows the development fallback only outside production', () => {
    vi.stubEnv('NODE_ENV', 'development')
    vi.stubEnv('IRON_SESSION_PASSWORD', '')

    const options = getOperatorSessionOptions()

    expect(options.password).toMatch(/^dev-only-/)
    expect(options.cookieOptions?.secure).toBe(false)
  })

  it('uses the configured production secret and secure cookie', () => {
    const secret = 'production-test-secret-at-least-32-characters-long'
    vi.stubEnv('NODE_ENV', 'production')
    vi.stubEnv('IRON_SESSION_PASSWORD', secret)

    const options = getOperatorSessionOptions()

    expect(options.password).toBe(secret)
    expect(options.cookieOptions?.secure).toBe(true)
  })
})
