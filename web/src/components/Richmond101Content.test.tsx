import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { NextRequest } from 'next/server'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('iron-session', () => ({
  getIronSession: vi.fn(async () => ({ isOperator: false })),
}))

vi.mock('@/lib/operator-session', () => ({
  getOperatorSessionOptions: vi.fn(() => ({})),
}))

import CityGovernmentGuidePage, { metadata } from '@/app/guide/page'
import { middleware } from '@/middleware'
import Richmond101Content from './Richmond101Content'

function source(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8')
}

describe('public city government guide', () => {
  it('identifies the reviewed AI guide and exact checked sources', () => {
    const markup = renderToStaticMarkup(<Richmond101Content />)

    expect(markup).toContain('AI-generated guide · reviewed by Richmond Commons')
    expect(markup).not.toContain('Operator-only')
    expect(markup).not.toContain('voice review required')
    expect(markup).toContain('Source links checked August 24, 2026.')
    expect(markup).toContain('Source link checked August 24, 2026')
    expect(markup).toContain(
      'https://www.ci.richmond.ca.us/DocumentCenter/View/75595/Getting-Started-Now-Guide---2026-elections?bidId=',
    )
    expect(markup).toContain('https://www.ci.richmond.ca.us/867/Charter')
    expect(markup).not.toContain('https://www.ci.richmond.ca.us/29/City-Council')
    expect(markup).not.toContain('https://www.ci.richmond.ca.us/4771/ELECTION-2026')
    expect(markup).toContain('T1 · Official Record')
    expect(markup).toContain('T2 · Independent Media')
    expect(markup).toContain('Richmondside: How Richmond works')
  })

  it('uses the approved title and minimum factual qualifications', () => {
    const markup = renderToStaticMarkup(<Richmond101Content />)

    expect(markup).toContain('How to Follow Richmond City Government')
    expect(markup).toContain(
      'Check the latest official agenda for the current time, location, and ways to',
    )
    expect(markup).toContain('When records are available, Richmond Commons brings')
    expect(markup).toContain('meeting&#x27;s Open Forum period')
  })

  it('keeps a plain heading hierarchy and accessible source links', () => {
    const markup = renderToStaticMarkup(<Richmond101Content />)

    expect(markup.match(/<h1/g)).toHaveLength(1)
    expect(markup.match(/<h2/g)).toHaveLength(6)
    expect(markup).not.toContain('<h3')
    expect(markup).toContain('href="/elections/find-my-district"')
    expect(markup).toContain('href="/meetings"')
    expect(markup).toContain('rel="noopener noreferrer"')
    expect(markup).toContain('(opens in a new tab)')
    expect(markup).not.toContain('&amp;nearr;')
  })

  it('graduates to indexable public metadata and footer-only discovery', () => {
    const footer = source('./Footer.tsx')
    const navigation = source('./Nav.tsx')
    const sitemap = source('../app/sitemap.ts')
    const nextConfig = source('../../next.config.ts')

    expect(renderToStaticMarkup(<CityGovernmentGuidePage />)).toContain(
      'How to Follow Richmond City Government',
    )
    expect(metadata.title).toBe('How to Follow Richmond City Government')
    expect(metadata.robots).toBeUndefined()
    expect(metadata.alternates).toEqual({ canonical: '/guide' })
    expect(footer).toContain('href="/guide"')
    expect(footer).toContain('City Government Guide')
    expect(navigation).not.toContain('href="/guide"')
    expect(sitemap).toContain("'/guide'")
    expect(nextConfig).toContain('source: "/operator/richmond-101"')
    expect(nextConfig).toContain('destination: "/guide"')
  })

  it('allows unauthenticated public guide requests through middleware', async () => {
    const response = await middleware(
      new NextRequest('https://richmondcommons.org/guide'),
    )

    expect(response.status).toBe(200)
    expect(response.headers.get('location')).toBeNull()
    expect(response.headers.get('x-middleware-next')).toBe('1')
  })
})
