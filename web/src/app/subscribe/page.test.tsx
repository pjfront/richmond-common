import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/components/SubscribeForm', () => ({
  default: () => null,
}))

import SubscribePage, { metadata } from './page'

describe('subscription cadence copy', () => {
  it('promises the approved regular-meeting preview and weekly recap cadence', async () => {
    const html = renderToStaticMarkup(
      await SubscribePage({ searchParams: Promise.resolve({}) }),
    )

    expect(metadata.description).toContain('before regular Richmond City Council meetings')
    expect(html).toContain('Before regular meetings:')
    expect(html).toContain('Weekly recap:')
    expect(html).toContain('a Monday summary of the completed week')
    expect(html).not.toContain('After the meeting:')
    expect(html).not.toContain('before and after each meeting')
  })
})
