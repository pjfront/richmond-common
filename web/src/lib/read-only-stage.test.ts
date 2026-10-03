import { describe, expect, it } from 'vitest'
import { stageRouteAllowed } from './read-only-stage'

describe('private staging capability', () => {
  it('permits source browsing, RSC routes and the single read-only search API', () => {
    for (const path of ['/', '/search', '/money', '/meetings', '/meetings/123/items/4', '/about', '/_next/static/chunks/app.js', '/api/commons/search']) {
      expect(stageRouteAllowed(path, 'GET')).toBe(true)
      expect(stageRouteAllowed(path, 'HEAD')).toBe(true)
    }
  })
  it('rejects every mutation including server actions and GET mutation APIs', () => {
    for (const method of ['POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']) {
      expect(stageRouteAllowed('/', method)).toBe(false)
      expect(stageRouteAllowed('/api/commons/search', method)).toBe(false)
    }
    for (const path of ['/api/search', '/api/operator/session', '/api/email/send-digest', '/api/subscribe', '/api/revalidate', '/operator', '/operator/login', '/api/commons/search/extra']) {
      expect(stageRouteAllowed(path, 'GET')).toBe(false)
    }
  })
  it('admits only the exact password-cookie POST as an authentication mutation', () => {
    expect(stageRouteAllowed('/api/site-access', 'POST')).toBe(true)
    for (const method of ['GET', 'HEAD', 'PUT', 'PATCH', 'DELETE', 'OPTIONS']) {
      expect(stageRouteAllowed('/api/site-access', method)).toBe(false)
    }
    expect(stageRouteAllowed('/api/site-access/extra', 'POST')).toBe(false)
    expect(stageRouteAllowed('/api/site-access/', 'POST')).toBe(false)
  })
})
