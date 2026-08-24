import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

function source(relativeUrl: string): string {
  return readFileSync(fileURLToPath(new URL(relativeUrl, import.meta.url)), 'utf8')
}

describe('bounded entity UX cut', () => {
  it('does not reconnect dense comparison UI to public PAC profiles', () => {
    const profile = source('../app/pac/[slug]/page.tsx')

    expect(profile).not.toMatch(/PACFlowMatrix|CycleBarsTimeline|getPACFlowMatrix/)
  })

  it('removes unsupported campaign filing freshness claims', () => {
    const publicCopy = [
      source('../app/pac/[slug]/page.tsx'),
      source('../app/orgs/[slug]/page.tsx'),
      source('../components/CampaignEntityProfile.tsx'),
    ].join('\n')

    expect(publicCopy).not.toMatch(/within.*15 minutes|updated after.*checks/i)
  })

  it('keeps campaign entity tables accessible and exportable', () => {
    const tables = [
      source('../app/pac/[slug]/PACDonorTable.tsx'),
      source('../app/pac/[slug]/PACOutgoingTable.tsx'),
      source('../app/pac/[slug]/PACIndependentExpendituresTable.tsx'),
    ]

    for (const table of tables) {
      expect(table).toMatch(/<caption/)
      expect(table).toMatch(/CsvDownloadButton/)
      expect(table).toMatch(/CampaignEntitySortableHeader/)
      expect(table).toMatch(/aria-sort=/)
      expect(table).toMatch(/filing_id/)
      expect(table).not.toMatch(/SortableHeader from '@\/components\/SortableHeader'/)
      expect(table).not.toMatch(/overflow-x-auto/)
    }

    expect(tables[1]).toMatch(/recipient_committee_id/)
  })

  it('defines the stable campaign CSV fields linked from each toolbar', () => {
    const methodology = source('../app/elections/methodology/page.tsx')

    expect(methodology).toMatch(/id="campaign-record-csv-field-guide"/)
    expect(methodology).toMatch(/support_or_oppose/)
    expect(methodology).toMatch(/S means support, O means oppose/)
    expect(methodology).toMatch(/recipient_committee_id/)
    expect(methodology).toMatch(/not a committee registration number/)
    expect(methodology).toMatch(/filing_id/)
  })
})
