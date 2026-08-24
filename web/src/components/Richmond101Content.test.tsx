import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'

import OperatorRichmond101Page, {
  metadata,
} from '@/app/operator/richmond-101/page'
import Richmond101Content from './Richmond101Content'

function source(relativePath: string): string {
  return readFileSync(fileURLToPath(new URL(relativePath, import.meta.url)), 'utf8')
}

describe('Richmond 101 operator draft', () => {
  it('visibly identifies draft, AI, review, and source-check status', () => {
    const markup = renderToStaticMarkup(<Richmond101Content />)

    expect(markup).toContain('Operator-only · AI-generated draft · voice review required')
    expect(markup).toContain('Source links checked August 10, 2026.')
    expect(markup).toContain('Source link checked August 10, 2026')
    expect(markup).not.toContain('weeks ago')
    expect(markup).toContain('T1 · Official Record')
    expect(markup).toContain('T2 · Independent Media')
    expect(markup).toContain('Richmondside: How Richmond works')
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

  it('inherits operator containment and adds strict route metadata', () => {
    expect(renderToStaticMarkup(<OperatorRichmond101Page />)).toContain('Richmond 101')
    expect(metadata.robots).toEqual({
      index: false,
      follow: false,
      noarchive: true,
      nosnippet: true,
    })

    const middleware = source('../middleware.ts')
    const operatorLayout = source('../app/operator/layout.tsx')
    const navigation = source('./Nav.tsx')
    const sitemap = source('../app/sitemap.ts')

    expect(middleware).toContain("matcher: ['/operator/:path*']")
    expect(operatorLayout).toContain('robots: { index: false, follow: false }')
    expect(navigation).not.toContain('richmond-101')
    expect(sitemap).not.toContain('richmond-101')
  })
})
