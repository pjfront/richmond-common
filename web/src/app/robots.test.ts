import { describe, expect, it } from 'vitest'

import robots from './robots'

describe('robots metadata', () => {
  it('preserves the public defaults and scopes deep agenda-item containment to Amazonbot', () => {
    expect(robots()).toEqual({
      rules: [
        {
          userAgent: '*',
          allow: '/',
          disallow: ['/api/', '/operator/'],
        },
        {
          userAgent: 'Amazonbot',
          allow: '/',
          disallow: ['/api/', '/operator/', '/meetings/*/items/'],
        },
      ],
      sitemap: 'https://richmondcommons.org/sitemap.xml',
    })
  })

  it('does not apply the agenda-item exclusion to other Amazon crawlers', () => {
    const { rules } = robots()

    expect(Array.isArray(rules)).toBe(true)
    if (!Array.isArray(rules)) throw new Error('Expected separate robots rule groups')

    const userAgents = rules.flatMap((rule) =>
      Array.isArray(rule.userAgent) ? rule.userAgent : [rule.userAgent],
    )

    expect(userAgents).not.toContain('Amzn-SearchBot')
    expect(userAgents).not.toContain('Amzn-User')
  })
})
