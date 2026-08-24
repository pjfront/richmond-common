import { beforeEach, describe, expect, it, vi } from 'vitest'

const navigation = vi.hoisted(() => ({
  permanentRedirect: vi.fn(),
}))

vi.mock('next/navigation', () => navigation)

import MayorFundingPage from '@/app/elections/[slug]/mayor/funding/page'

describe('retired Mayor funding route', () => {
  beforeEach(() => {
    navigation.permanentRedirect.mockReset()
    navigation.permanentRedirect.mockImplementation(() => {
      throw new Error('NEXT_PERMANENT_REDIRECT')
    })
  })

  it('permanently redirects old bookmarks to the matching election page', async () => {
    await expect(
      MayorFundingPage({
        params: Promise.resolve({ slug: '2026-primary' }),
      }),
    ).rejects.toThrow('NEXT_PERMANENT_REDIRECT')

    expect(navigation.permanentRedirect).toHaveBeenCalledWith(
      '/elections/2026-primary',
    )
  })
})
