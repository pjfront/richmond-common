import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import CampaignEntityIndex from '@/components/CampaignEntityIndex'
import {
  CampaignEntityIndexView,
  normalizeTimeWindow,
  timeWindowHref,
} from '@/components/CampaignEntityIndexClient'
import type { CampaignEntityIndexItem } from '@/components/CampaignEntityIndexClient'

function item(
  overrides: Partial<CampaignEntityIndexItem> = {},
): CampaignEntityIndexItem {
  return {
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
    activity_before_tracked_window: false,
    source_url: 'https://public.netfile.com/example',
    extracted_at: '2026-08-24T00:00:00Z',
    source_tier: 1,
    source_label: 'NetFile',
    confidence_score: 0.98,
    ...overrides,
  }
}

function renderDirectory(
  items: CampaignEntityIndexItem[],
  selectedWindow: 'current' | 'last2' | 'tracked' = 'current',
): string {
  return renderToStaticMarkup(
    <CampaignEntityIndexView
      items={items}
      currentCycle={2026}
      singularLabel="committee"
      pluralLabel="committees"
      selectedWindow={selectedWindow}
    />,
  )
}

describe('shared campaign-entity directory', () => {
  it('uses permanent query-string links for every time-filter interaction', () => {
    const html = renderDirectory([item()])

    expect(html).toContain('href="?period=current"')
    expect(html).toContain('href="?period=last2"')
    expect(html).toContain('href="?period=tracked"')
    expect(html).toContain('aria-current="page"')
    expect(timeWindowHref('tracked')).toBe('?period=tracked')
    expect(normalizeTimeWindow('last2')).toBe('last2')
    expect(normalizeTimeWindow('tracked')).toBe('tracked')
    expect(normalizeTimeWindow('unexpected')).toBe('current')
  })

  it('renders one narrative grammar with complete row attribution', () => {
    const committeeHtml = renderDirectory([item()])
    const unionHtml = renderToStaticMarkup(
      <CampaignEntityIndexView
        items={[
          item({
            id: 'union-1',
            href: '/orgs/example-workers-union',
            name: 'Example Workers Union',
            kind: 'union',
            sponsorDisclosure: null,
            cycleBars: [
              { cycle: 2024, received: 0, given: 400 },
              { cycle: 2026, received: 0, given: 250 },
            ],
          }),
        ]}
        currentCycle={2026}
        singularLabel="union"
        pluralLabel="unions"
        selectedWindow="current"
      />,
    )

    for (const html of [committeeHtml, unionHtml]) {
      expect(html).toContain('Time period')
      expect(html).toContain('role="status"')
      expect(html).toContain('href="https://public.netfile.com/example"')
      expect(html).toContain('T1')
      expect(html).toContain('Official Record')
      expect(html).toContain('Verified')
      expect(html).not.toContain('<svg')
      expect(html).not.toMatch(/all time|lifetime/i)
    }

    expect(committeeHtml).toContain(
      'Reported money received from donors and contributions to other committees in the 2026 cycle.',
    )
    expect(committeeHtml).not.toContain('$125')
    expect(unionHtml).toContain(
      'Reported contributions to campaign committees in the 2026 cycle.',
    )
    expect(unionHtml).not.toContain('$250')
  })

  it('sorts alphabetically and keeps older-only rows out of hidden-window counts', () => {
    const current = renderDirectory([
      item({ id: 'z', name: 'Zebra Committee' }),
      item({
        id: 'a',
        name: 'Alpha Committee',
        cycleBars: [{ cycle: 2024, received: 50, given: 0 }],
      }),
      item({
        id: 'old',
        name: 'Old Committee',
        cycleBars: [],
        activity_before_tracked_window: true,
      }),
      item({
        id: 'low',
        name: 'Low Confidence Committee',
        confidence_score: 0.89,
      }),
    ])

    expect(current).toContain('Show 1 more from the last five cycles')
    expect(current).toContain(
      '1 additional committee has reported activity only before the five-cycle view',
    )
    expect(current).not.toContain('Show 3 more')
    expect(current).not.toContain('Low Confidence Committee')
    expect(current).toContain(
      'Entries without complete provenance or at least 90% confidence are withheld',
    )

    const tracked = renderDirectory(
      [
        item({ id: 'z', name: 'Zebra Committee' }),
        item({
          id: 'a',
          name: 'Alpha Committee',
          cycleBars: [{ cycle: 2024, received: 50, given: 0 }],
        }),
      ],
      'tracked',
    )
    expect(tracked.indexOf('Alpha Committee')).toBeLessThan(
      tracked.indexOf('Zebra Committee'),
    )
    expect(tracked).not.toContain('Show 1 more')
    expect(tracked).toContain('across the 2018–2026 tracked cycles')
  })

  it('fails closed for query, truncation, and missing-trust-field states', () => {
    for (const availability of [
      'query-error',
      'incomplete',
      'missing-trust-fields',
    ] as const) {
      const html = renderToStaticMarkup(
        <CampaignEntityIndex
          heading="Unions"
          description="Filing-based directory description."
          items={[]}
          currentCycle={2026}
          singularLabel="union"
          pluralLabel="unions"
          availability={availability}
          sourceNote={<>Classification is inferred from filing names alone.</>}
        />,
      )

      expect(html).toContain('Directory unavailable')
      expect(html).not.toMatch(/No unions have reported activity/i)
      expect(html).toContain('Classification is inferred from filing names alone.')
    }
  })

  it('does not repeat a sponsor already present in a filed committee name', () => {
    const html = renderDirectory([
      item({
        name: 'Example Committee sponsored by Richmond Neighbors',
      }),
    ])

    expect(html.match(/Sponsored by Richmond Neighbors/gi)).toHaveLength(1)
  })
})
