import { afterEach, describe, expect, it, vi } from 'vitest'
import { capabilityEnabled, featureEnabled, featureProfile, featureRouteAllowed, isLocalArchive, localRequestAllowed } from './feature-policy'

afterEach(() => vi.unstubAllEnvs())

describe('feature tier boundaries', () => {
  it('defaults to free public browsing and refuses paid work even with keys', () => {
    vi.stubEnv('RICHMOND_FEATURE_PROFILE', '')
    vi.stubEnv('RICHMOND_LOCAL_ARCHIVE', '')
    vi.stubEnv('OPENAI_API_KEY', 'fixture')
    expect(featureProfile()).toBe('basic_public')
    expect(featureEnabled('similar_discussions')).toBe(false)
    expect(capabilityEnabled('embeddings')).toBe(false)
    expect(featureRouteAllowed('/money', 'GET')).toBe(true)
    expect(featureRouteAllowed('/operator/settings', 'GET')).toBe(false)
    expect(featureRouteAllowed('/api/email/send-digest', 'GET')).toBe(false)
    expect(featureRouteAllowed('/api/commons/search/extra', 'GET')).toBe(false)
  })
  it('opens retained local record surfaces but blocks every record mutation and email', () => {
    vi.stubEnv('VERCEL', '')
    vi.stubEnv('RICHMOND_LOCAL_ARCHIVE', 'true')
    vi.stubEnv('RICHMOND_FEATURE_PROFILE', 'local_archive')
    for (const path of ['/library', '/council', '/council/analytics', '/api/operator/settings', '/public-records', '/data/richmond-districts.geojson']) expect(featureRouteAllowed(path, 'GET')).toBe(true)
    for (const method of ['POST', 'PUT', 'PATCH', 'DELETE']) {
      expect(featureRouteAllowed('/api/operator/settings', method)).toBe(false)
      expect(featureRouteAllowed('/meetings/id', method)).toBe(false)
    }
    expect(featureRouteAllowed('/api/email/send-digest', 'GET')).toBe(false)
    expect(featureRouteAllowed('/api/operator/login', 'POST')).toBe(true)
    expect(capabilityEnabled('embeddings')).toBe(false)
  })
  it('cannot turn a hosted deployment into a local archive', () => {
    vi.stubEnv('VERCEL', '1')
    vi.stubEnv('RICHMOND_LOCAL_ARCHIVE', 'true')
    vi.stubEnv('RICHMOND_FEATURE_PROFILE', 'local_archive')
    expect(isLocalArchive()).toBe(false)
    expect(featureProfile()).toBe('basic_public')
  })
  it('fails closed for unknown profiles and nonloopback or foreign-origin requests', () => {
    vi.stubEnv('RICHMOND_FEATURE_PROFILE', 'typo')
    expect(featureProfile()).toBe('basic_public')
    expect(localRequestAllowed(new URL('http://127.0.0.1:3100/search'), new Headers({ host: '127.0.0.1:3100' }))).toBe(true)
    const foreignHeaders: Record<string, string>[] = [{ host: 'attacker.example' }, { origin: 'https://attacker.example' }, { origin: 'http://127.0.0.1:9999' }, { 'x-forwarded-host': 'attacker.example' }]
    for (const headers of foreignHeaders) expect(localRequestAllowed(new URL('http://127.0.0.1:3100/'), new Headers(headers))).toBe(false)
    expect(localRequestAllowed(new URL('https://richmondcommons.org/'), new Headers())).toBe(false)
  })
})
