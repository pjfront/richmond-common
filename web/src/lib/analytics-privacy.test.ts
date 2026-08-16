import { describe, expect, it } from 'vitest'
import {
  isSensitiveReferrer,
  sanitizeAnalyticsEvent,
  shouldMountAnalytics,
} from './analytics-privacy'

describe('shouldMountAnalytics', () => {
  it('fails closed until the operator session is resolved', () => {
    expect(shouldMountAnalytics(false, false)).toBe(false)
  })

  it('suppresses analytics for a resolved operator session', () => {
    expect(shouldMountAnalytics(true, true)).toBe(false)
  })

  it('allows analytics only for a resolved public session', () => {
    expect(shouldMountAnalytics(true, false)).toBe(true)
  })
})

describe('sanitizeAnalyticsEvent', () => {
  it('removes query strings and fragments from public page views', () => {
    expect(sanitizeAnalyticsEvent({
      type: 'pageview',
      url: 'https://richmondcommons.org/search?q=123+Main+Street#results',
    })).toEqual({
      type: 'pageview',
      url: 'https://richmondcommons.org/search',
    })
  })

  it('excludes operator routes and descendants', () => {
    expect(sanitizeAnalyticsEvent({
      type: 'pageview',
      url: 'https://richmondcommons.org/operator',
    })).toBeNull()
    expect(sanitizeAnalyticsEvent({
      type: 'pageview',
      url: 'https://richmondcommons.org/operator/decisions?next=private',
    })).toBeNull()
  })

  it('excludes subscription-management routes', () => {
    expect(sanitizeAnalyticsEvent({
      type: 'pageview',
      url: 'https://richmondcommons.org/subscribe/manage?token=secret',
    })).toBeNull()
  })

  it('excludes page views reached from private or token-bearing referrers', () => {
    const event = {
      type: 'pageview' as const,
      url: 'https://richmondcommons.org/meetings',
    }

    expect(sanitizeAnalyticsEvent(
      event,
      'https://richmondcommons.org/subscribe/manage?token=secret',
    )).toBeNull()
    expect(sanitizeAnalyticsEvent(
      event,
      'https://example.org/share?access_token=secret',
    )).toBeNull()
  })

  it('does not exclude similarly prefixed public routes or ordinary referrers', () => {
    expect(sanitizeAnalyticsEvent({
      type: 'pageview',
      url: 'https://richmondcommons.org/operator-guide?ref=home',
    }, 'https://example.org/story?id=42')).toEqual({
      type: 'pageview',
      url: 'https://richmondcommons.org/operator-guide',
    })
  })

  it('rejects custom events so measurement stays pageview-only', () => {
    expect(sanitizeAnalyticsEvent({
      type: 'event',
      url: 'https://richmondcommons.org/elections/2026-general?choice=private',
    })).toBeNull()
  })

  it('fails closed for malformed destination URLs and referrers', () => {
    expect(sanitizeAnalyticsEvent({
      type: 'pageview',
      url: 'not-a-url',
    })).toBeNull()
    expect(isSensitiveReferrer('not-a-url')).toBe(true)
  })
})
