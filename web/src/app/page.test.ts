import { renderToStaticMarkup } from 'react-dom/server'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocked = vi.hoisted(() => ({
  getFrontDoorMeeting: vi.fn(),
  getFrontDoorElection: vi.fn(),
}))

vi.mock('@/lib/queries', () => ({
  getFrontDoorMeeting: mocked.getFrontDoorMeeting,
  getFrontDoorElection: mocked.getFrontDoorElection,
  electionToSlug: vi.fn(() => '2099-general'),
}))

vi.mock('@/components/SubscribeCTA', () => ({ default: () => null }))

import Home from './page'

describe('homepage front-door read states', () => {
  beforeEach(() => vi.clearAllMocks())

  it('announces a failed dynamic read separately from a true empty state', async () => {
    mocked.getFrontDoorMeeting.mockResolvedValue({ state: 'error', data: null })
    mocked.getFrontDoorElection.mockResolvedValue({ state: 'empty', data: null })

    const html = renderToStaticMarkup(await Home())

    expect(html).toContain('role="alert"')
    expect(html).toContain('current meeting highlight is temporarily unavailable')
  })

  it('uses claim-light fallback cards without an error alert for true empty data', async () => {
    mocked.getFrontDoorMeeting.mockResolvedValue({ state: 'empty', data: null })
    mocked.getFrontDoorElection.mockResolvedValue({ state: 'empty', data: null })

    const html = renderToStaticMarkup(await Home())

    expect(html).not.toContain('role="alert"')
    expect(html).toContain('Meeting records')
    expect(html).toContain('Election information')
  })
})
