import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('./OperatorModeProvider', () => ({
  useOperatorMode: () => ({ isOperator: false }),
}))

import Nav from './Nav'

describe('Nav election read state', () => {
  it('renders a visible error state while preserving the safe Elections fallback', () => {
    const html = renderToStaticMarkup(
      <Nav nextElection={null} electionUnavailable />,
    )

    expect(html).toContain('role="alert"')
    expect(html).toContain('current election shortcut is temporarily unavailable')
    expect(html).toContain('href="/elections/find-my-district"')
  })
})
