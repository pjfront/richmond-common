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
    expect(copy).toMatch(/listed as donors in Richmond campaign-finance records/i)
  })

  it('does not reconnect dense comparison UI to public PAC profiles', () => {
    const profile = source('../app/pac/[slug]/page.tsx')
    const index = source('../app/pac/page.tsx')

    expect(profile).not.toMatch(/PACFlowMatrix|CycleBarsTimeline|getPACFlowMatrix/)
    expect(index).not.toMatch(/CycleBarsSparkline/)
  })

  it('does not add unbenchmarked dollar totals to campaign-entity indexes', () => {
    const listRows = [
      source('../app/pac/PACRow.tsx'),
      source('../components/OrgList.tsx'),
    ].join('\n')
    const pacIndex = source('../app/pac/page.tsx')

    expect(listRows).toMatch(/Public campaign records show/)
    expect(listRows).not.toMatch(/Intl\.NumberFormat|toLocaleString|function fmt/)
    expect(listRows).not.toMatch(/\$\s*\{?fmt|\$\d/)
    expect(listRows).not.toMatch(/all time|raised <strong>|contributed <strong>/i)
    expect(pacIndex).not.toMatch(/\{pacs\.length\}/)
    expect(pacIndex).not.toMatch(/Every Richmond political action committee/)

    const profileMetadata = [
      source('../app/pac/[slug]/page.tsx'),
      source('../app/orgs/[slug]/page.tsx'),
    ].join('\n')
    expect(profileMetadata).not.toMatch(/description:.*\$\$\{/)
  })

  it('keeps the public company label consistent', () => {
    const companyIndex = source('../app/corporations/page.tsx')

    expect(companyIndex).toMatch(/heading="Companies"/)
    expect(companyIndex).not.toMatch(/heading="Corporations"/)
  })

  it('removes unsupported campaign filing freshness claims', () => {
    const publicCopy = [
      source('../app/pac/page.tsx'),
      source('../app/unions/page.tsx'),
      source('../app/corporations/page.tsx'),
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
      expect(table).not.toMatch(/SortableHeader from '@\/components\/SortableHeader'/)
      expect(table).not.toMatch(/overflow-x-auto/)
    }
  })
})
