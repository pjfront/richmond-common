import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import CampaignEntityIndex from '@/components/CampaignEntityIndex'
import CampaignEntityIndexClient from '@/components/CampaignEntityIndexClient'
import type { CampaignEntityIndexItem } from '@/components/CampaignEntityIndexClient'

const committee: CampaignEntityIndexItem = {
  id: 'committee-1',
  href: '/pac/example-committee',
  name: 'Example Committee',
  kind: 'committee',
  sponsorDisclosure: 'Sponsored by Richmond Neighbors',
  cycleBars: [
    { cycle: 2018, received: 0, given: 0 },
    { cycle: 2020, received: 0, given: 0 },
    { cycle: 2022, received: 0, given: 0 },
    { cycle: 2024, received: 500, given: 0 },
    { cycle: 2026, received: 125, given: 75 },
  ],
}

const union: CampaignEntityIndexItem = {
  id: 'union-1',
  href: '/orgs/example-workers-union',
  name: 'Example Workers Union',
  kind: 'union',
  sponsorDisclosure: null,
  cycleBars: [
    { cycle: 2018, received: 0, given: 0 },
    { cycle: 2020, received: 0, given: 0 },
    { cycle: 2022, received: 0, given: 0 },
    { cycle: 2024, received: 0, given: 400 },
    { cycle: 2026, received: 0, given: 250 },
  ],
}

describe('shared campaign-entity directory', () => {
  it('uses one time-filter interaction and narrative row grammar', () => {
    const committeeHtml = renderToStaticMarkup(
      <CampaignEntityIndexClient
        items={[committee]}
        currentCycle={2026}
        singularLabel="committee"
        pluralLabel="committees"
      />,
    )
    const unionHtml = renderToStaticMarkup(
      <CampaignEntityIndexClient
        items={[union]}
        currentCycle={2026}
        singularLabel="union"
        pluralLabel="unions"
      />,
    )

    for (const html of [committeeHtml, unionHtml]) {
      expect(html).toContain('Time period')
      expect(html).toContain('2026 cycle')
      expect(html).toContain('2024–2026')
      expect(html).toContain('Last five cycles')
      expect(html).toContain('aria-pressed="true"')
      expect(html).toContain('role="status"')
      expect(html).not.toContain('<svg')
      expect(html).not.toMatch(/all time|lifetime/i)
    }

    expect(committeeHtml).toContain(
      'Reported money received from donors and contributions to other committees in the 2026 cycle.',
    )
    expect(committeeHtml).not.toContain('$125')
    expect(committeeHtml).toContain('href="/pac/example-committee"')
    expect(unionHtml).toContain(
      'Reported contributions to campaign committees in the 2026 cycle.',
    )
    expect(unionHtml).not.toContain('$250')
    expect(unionHtml).toContain('href="/orgs/example-workers-union"')
  })

  it('shares the same source-honest page shell', () => {
    const html = renderToStaticMarkup(
      <CampaignEntityIndex
        heading="Unions"
        description="Filing-based directory description."
        items={[union]}
        currentCycle={2026}
        singularLabel="union"
        pluralLabel="unions"
        sourceNote={<>Classification comes from filing records.</>}
      />,
    )

    expect(html).toContain('<h1')
    expect(html).toContain('Tier 1 sources')
    expect(html).toContain('do not include a reliable direct source link')
    expect(html).toContain('Classification comes from filing records.')
    expect(html).not.toMatch(/within.*15 minutes/i)
  })

  it('does not repeat a sponsor already present in a filed committee name', () => {
    const html = renderToStaticMarkup(
      <CampaignEntityIndexClient
        items={[
          {
            ...committee,
            name: 'Example Committee sponsored by Richmond Neighbors',
          },
        ]}
        currentCycle={2026}
        singularLabel="committee"
        pluralLabel="committees"
      />,
    )

    expect(html.match(/Sponsored by Richmond Neighbors/gi)).toHaveLength(1)
  })
})
