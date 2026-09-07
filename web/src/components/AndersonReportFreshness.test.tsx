import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import { VERIFIED_ANDERSON_FILINGS } from '@/data/anderson-paper-filings'
import AndersonFinanceSummary from './AndersonFinanceSummary'
import { ANDERSON_FINANCE } from '@/lib/anderson-finance'

describe('dated candidate finances during source outages or updates', () => {
  it.each(['unavailable', 'stale'] as const)('keeps source links and the actual verification time when %s', status => {
    const html = renderToStaticMarkup(<AndersonFinanceSummary coverage={{ ...VERIFIED_ANDERSON_FILINGS, status }} />)
    expect(html).toContain('role="status"')
    expect(html).toContain('couldn’t check for newer reports')
    expect(html).toContain(`dateTime="${ANDERSON_FINANCE.reviewed_at}"`)
    expect(html).toContain('$54,303')
    expect(html).toContain('$13,423')
    expect(html).toContain('https://netfile.com/Connect2/api/public/image/217352920#page=1')
  })
  it('links the newly discovered donation report, not the unchanged older full report', () => {
    const html = renderToStaticMarkup(<AndersonFinanceSummary coverage={{ ...VERIFIED_ANDERSON_FILINGS,
      recentRapid: [{ ...VERIFIED_ANDERSON_FILINGS.recentRapid[0], id: '999999999', sourceUrl: 'https://netfile.com/Connect2/api/public/image/999999999' }] }} />)
    expect(html).toContain('A newer report is available')
    expect(html).toMatch(/href="https:\/\/netfile.com\/Connect2\/api\/public\/image\/999999999"[^>]*>See the official report/)
    expect(html).toContain('$54,303')
  })
})
