import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

function source(relativeUrl: string): string {
  return readFileSync(fileURLToPath(new URL(relativeUrl, import.meta.url)), 'utf8')
}

describe('bounded entity UX cut', () => {
  it('keeps motive claims out of organization index copy', () => {
    const copy = [
      source('../app/unions/page.tsx'),
      source('../app/corporations/page.tsx'),
    ].join('\n')

    expect(copy).not.toMatch(/labor[- ]friendly/i)
    expect(copy).not.toMatch(/business[- ]friendly/i)
    expect(copy).toMatch(/listed as donors in Richmond campaign-finance filings/i)
  })

  it('does not reconnect dense comparison UI to public PAC profiles', () => {
    const profile = source('../app/pac/[slug]/page.tsx')
    const indexRow = source('../app/pac/PACRow.tsx')

    expect(profile).not.toMatch(/PACFlowMatrix|CycleBarsTimeline|getPACFlowMatrix/)
    expect(indexRow).not.toMatch(/CycleBarsSparkline/)
  })
})
