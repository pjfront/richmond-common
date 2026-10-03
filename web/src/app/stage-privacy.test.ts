import { afterEach, describe, expect, it, vi } from 'vitest'
import robots from './robots'
import sitemap from './sitemap'

afterEach(() => { vi.unstubAllEnvs() })

describe('private relaunch discovery', () => {
  it('disallows crawling without advertising a production sitemap in read-only stage mode', () => {
    vi.stubEnv('RICHMOND_READ_ONLY_STAGE', 'true')
    expect(robots()).toEqual({ rules: { userAgent: '*', disallow: '/' } })
  })

  it('does not enumerate any public record URLs for a staged sitemap', async () => {
    vi.stubEnv('RICHMOND_READ_ONLY_STAGE', 'true')
    await expect(sitemap()).resolves.toEqual([])
  })
})
