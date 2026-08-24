import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./OperatorModeProvider', () => ({
  useOperatorMode: () => ({ isOperator: false }),
}))

import Nav from './Nav'

describe('Nav', () => {
  it('uses a static Elections link without a global data dependency', () => {
    const html = renderToStaticMarkup(<Nav />)

    expect(html).toContain('href="/elections"')
    expect(html).toContain('>Elections</a>')
    expect(html).not.toContain('role="alert"')
  })
})
