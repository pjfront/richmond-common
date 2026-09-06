import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { VERIFIED_ANDERSON_FILINGS } from '@/data/anderson-paper-filings'
import CandidatePaperCoverage from './CandidatePaperCoverage'

describe('dated candidate paper filing explanation', () => {
  it.each(['unavailable', 'stale'] as const)('keeps source links and the actual verification time when %s', status => {
    const html = renderToStaticMarkup(<CandidatePaperCoverage coverage={{ ...VERIFIED_ANDERSON_FILINGS, status }} />)
    expect(html).toContain('role="status"')
    expect(html).toContain(status === 'unavailable' ? 'current filing check is unavailable' : 'fresh filing check is pending')
    expect(html).toContain('dateTime="2026-09-06T16:45:39Z"')
    expect(html).toContain('Richmond time')
    expect(html).toContain('Jun 30, 2026')
    for (const filing of VERIFIED_ANDERSON_FILINGS.recentRapid) expect(html).toContain(filing.sourceUrl)
    expect(html).not.toContain('$')
  })
})
