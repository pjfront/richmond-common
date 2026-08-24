import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import CampaignEntityFinancialDetails from '@/components/CampaignEntityFinancialDetails'
import CampaignEntityProfile from '@/components/CampaignEntityProfile'

const incoming = [
  {
    donor_name: 'Richmond Resident',
    donor_employer: null,
    amount: 125,
    contribution_date: '2026-08-01',
    contribution_type: 'MON',
    filing_id: 'filing-in',
  },
  {
    donor_name: 'Richmond Neighbor',
    donor_employer: null,
    amount: 75,
    contribution_date: '2026-08-02',
    contribution_type: 'MON',
    filing_id: 'filing-in-2',
  },
]

const outgoing = [
  {
    recipient_committee_name: 'Neighbors for Richmond',
    recipient_committee_id: 'committee-1',
    recipient_candidate_name: 'Pat Example',
    amount: 250,
    contribution_date: '2026-08-02',
    contribution_type: 'MON',
    filing_id: 'filing-out',
  },
]

const independentExpenditures = [
  {
    candidate_name: 'Pat Example',
    support_or_oppose: 'S' as const,
    amount: 500,
    expenditure_date: '2026-08-03',
    payee_name: 'Richmond Print Shop',
    description: 'Mailer',
    expenditure_code: 'LIT',
    filing_id: 'filing-ie',
  },
]

describe('shared campaign-entity profile', () => {
  it('uses one sentence-first shell for each public entity type', () => {
    const html = renderToStaticMarkup(
      <CampaignEntityProfile
        backHref="/unions"
        backLabel="All unions"
        name="Example Workers Union"
        typeLabel="Union"
        summary={<>The filing summary leads the page.</>}
        sourceNote={<>Classification comes from filing records.</>}
      >
        <p>Receipt detail follows.</p>
      </CampaignEntityProfile>,
    )

    expect(html).toContain('What the filings show')
    expect(html).toContain('The filing summary leads the page.')
    expect(html).toContain('Receipt detail follows.')
    expect(html.indexOf('What the filings show')).toBeLessThan(
      html.indexOf('Receipt detail follows.'),
    )
    expect(html).toContain('Tier 1 official sources')
    expect(html).toContain('checks the filing systems for new records')
    expect(html).not.toMatch(/within about 15 minutes/i)
  })

  it('preserves committee money-in, money-out, and independent-spending receipts', () => {
    const html = renderToStaticMarkup(
      <CampaignEntityFinancialDetails
        incoming={incoming}
        outgoing={outgoing}
        independentExpenditures={independentExpenditures}
        entityDisplay="Example Committee"
        entityNoun="committee"
        entityUrlMap={null}
      />,
    )

    expect(html).toContain('Money received')
    expect(html).toContain('Richmond Resident')
    expect(html).toContain('Richmond Neighbor')
    expect(html).toContain('2 named donors')
    expect(html).not.toContain('$200')
    expect(html).toContain('Money given')
    expect(html).toContain('Neighbors for Richmond')
    expect(html).toContain('Independent spending')
    expect(html).toContain('Pat Example')
    expect(html).not.toContain('How donor money reaches candidates')
    expect(html).not.toContain('Last two cycles')
  })

  it('uses the same receipt pattern for unions without inventing money-in data', () => {
    const html = renderToStaticMarkup(
      <CampaignEntityFinancialDetails
        outgoing={outgoing}
        independentExpenditures={independentExpenditures}
        entityDisplay="Example Workers Union"
        entityNoun="organization"
        entityUrlMap={null}
      />,
    )

    expect(html).not.toContain('Money received')
    expect(html).toContain('Money given')
    expect(html).toContain('Independent spending')
  })
})
