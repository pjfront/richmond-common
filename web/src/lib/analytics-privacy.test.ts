import { describe, expect, it } from 'vitest'
import { sanitizeAnalyticsEvent } from './analytics-privacy'

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

  it('excludes subscription-management tokens', () => {
    expect(sanitizeAnalyticsEvent({
      type: 'pageview',
      url: 'https://richmondcommons.org/subscribe/manage?token=secret',
    })).toBeNull()
  })

  it('does not exclude similarly prefixed public routes', () => {
    expect(sanitizeAnalyticsEvent({
      type: 'pageview',
      url: 'https://richmondcommons.org/operator-guide?ref=home',
    })).toEqual({
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
})
