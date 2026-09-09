import type { ReactElement } from 'react'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import CommissionDetailPage from './page'

const query = vi.hoisted(() => ({ getCommission: vi.fn(), getCommissionMeetings: vi.fn() }))
vi.mock('@/lib/queries', () => query)

const commission = {
  id: 'commission-1', name: 'Planning Commission', commission_type: 'commission',
  num_seats: 7, website_roster_url: 'https://www.richmondca.gov/roster',
  last_website_scrape: '2026-09-01T12:00:00Z',
}
const members = Array.from({ length: 5 }, (_, index) => ({
  id: `member-${index}`, name: `Member ${index + 1}`, role: 'member', is_current: true,
  term_end: index < 4 ? '2020-06-30' : null, appointed_by: null,
}))

async function renderPage() {
  const wrapper = await CommissionDetailPage({ params: Promise.resolve({ id: commission.id }) })
  const content = wrapper.type as (props: typeof wrapper.props) => Promise<ReactElement>
  return renderToStaticMarkup(await content(wrapper.props))
}

describe('commission roster source scope', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    query.getCommission.mockResolvedValue({ commission, members })
    query.getCommissionMeetings.mockResolvedValue([])
  })

  it('shows five listed records and their recorded dates instead of inferring six vacancies or four holdovers', async () => {
    const html = await renderPage()
    expect(html).toContain('5 listed current members')
    expect(html).toContain('4 with past recorded term dates')
    expect(html).toContain('Recorded term dates alone do not establish who is serving today')
    expect(html).toContain('Recorded term end')
    expect(html).toContain('Jun 2020')
    expect(html).toContain('href="https://www.richmondca.gov/roster"')
    expect(html).toContain('Last roster check: September 1, 2026')
    expect(html).not.toMatch(/1\/7|6 vacant|holdover|\(expired\)/i)
    expect(query.getCommission).toHaveBeenCalledOnce()
    expect(query.getCommissionMeetings).toHaveBeenCalledWith(commission.id)
  })

  it('does not infer vacancies from an empty roster or invent a check date', async () => {
    query.getCommission.mockResolvedValue({ commission: { ...commission,
      website_roster_url: null, last_website_scrape: null }, members: [] })
    const html = await renderPage()
    expect(html).toContain('0 listed current members')
    expect(html).toContain('No members listed.')
    expect(html).not.toContain('7 vacant')
    expect(html).not.toContain('Last roster check:')
    expect(html).not.toContain('Official roster source')
  })
})
