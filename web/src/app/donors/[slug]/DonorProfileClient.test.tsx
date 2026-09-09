import { describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import DonorProfileClient from './DonorProfileClient'
import type { DonorOutgoingRow } from '@/lib/types'

const csv = vi.hoisted(() => ({ rows: [] as Record<string, unknown>[] }))
vi.mock('@/components/CsvDownloadButton', () => ({ default: ({ rows }: { rows: Record<string, unknown>[] }) => {
  csv.rows = rows
  return <button>Download CSV</button>
} }))
function entry(index: number): DonorOutgoingRow {
  return { record_id: String(index).padStart(5, '0'), recipient_committee_name: `Reported recipient ${index}`,
    recipient_committee_id: `committee-${index}`, recipient_committee_fppc_id: '1488504', recipient_candidate_name: null,
    amount: index === 9999 ? -25.25 : 100, contribution_date: '2025-06-01', contribution_type: index === 9999 ? 'nonmonetary' : 'monetary',
    filing_id: '217136864', source: 'netfile', source_url: 'https://netfile.com/Connect2/api/public/image/217136864' }
}

describe('bounded donor profile display', () => {
  it('renders only twenty entries from the full ten-thousand-row read while exporting every original row', () => {
    const records = Array.from({ length: 10000 }, (_, i) => entry(i))
    const html = renderToStaticMarkup(<DonorProfileClient outgoing={records} donorDisplay="Example name" />)
    expect(html.match(/<li /g)).toHaveLength(20)
    expect(html).toContain('Showing 20 of 10000 matching filing entries')
    expect(html).toContain('Show 20 more entries')
    expect(html).toContain('aria-controls=')
    expect(html).toContain('aria-live="polite"')
    expect(html).not.toContain('Reported recipient 9999')
    expect(csv.rows).toHaveLength(10000)
    expect(csv.rows[9999]).toEqual(records[9999])
    expect(csv.rows[9999]).toMatchObject({ amount: -25.25, contribution_type: 'nonmonetary', source_url: records[9999].source_url })
  })
  it('labels the final smaller batch correctly and omits show-more when every entry is visible', () => {
    const remaining = renderToStaticMarkup(<DonorProfileClient outgoing={Array.from({ length: 23 }, (_, i) => entry(i))} donorDisplay="Example name" />)
    expect(remaining.match(/<li /g)).toHaveLength(20)
    expect(remaining).toContain('Show 3 more entries')
    const complete = renderToStaticMarkup(<DonorProfileClient outgoing={[entry(0)]} donorDisplay="Example name" />)
    expect(complete).toContain('Showing 1 of 1 matching filing entry')
    expect(complete).not.toContain('more entries')
    expect(complete).toContain('2025-06-01')
    expect(complete).toContain('Original filing 217136864')
    expect(complete).toContain('Recorded as monetary')
  })
  it('keeps a confirmed empty view distinct from a zero-dollar claim', () => {
    const html = renderToStaticMarkup(<DonorProfileClient outgoing={[]} donorDisplay="Example name" />)
    expect(html).toContain('Showing 0 of 0 matching filing entries')
    expect(html).not.toContain('more entries')
    expect(html).not.toContain('$0')
    expect(csv.rows).toEqual([])
  })
})
