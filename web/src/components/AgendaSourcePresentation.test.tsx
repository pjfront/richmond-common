import { beforeEach, describe, expect, it, vi } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import type { AgendaItemWithMotions } from '@/lib/types'
import AgendaItemCard from './AgendaItemCard'
import ConsentCalendarSection from './ConsentCalendarSection'
import CategoryPage from '@/app/meetings/category/[slug]/page'
import AgendaItemDetailPage from '@/app/meetings/[id]/items/[itemNumber]/page'

const query = vi.hoisted(() => ({ getAgendaItemsByCategory: vi.fn(), getAgendaItemDetail: vi.fn() }))
vi.mock('@/lib/queries', () => query)
vi.mock('@/components/OperatorGate', () => ({ default: () => null }))
vi.mock('@/components/OperatorAgendaItemSections', () => ({ default: () => null }))
vi.mock('@/components/SimilarDiscussions', () => ({ default: () => null }))

const item: AgendaItemWithMotions = {
  id: 'entry-1', meeting_id: 'meeting-1', item_number: 'V.1',
  title: 'First recorded agenda entry', category: 'contracts',
  summary_headline: null, plain_language_summary: 'This proposal discusses a $25,000 contract.',
  description: 'Original agenda description.', financial_amount: '$350,000 per contract over three years',
  motions: [], is_consent_calendar: true, was_pulled_from_consent: false,
  agenda_source_authority: 'current', agenda_source_retired_at: null,
  agenda_source_revision_sha256: null, ai_comment_summary: null,
  continued_from: null, continued_to: null, created_at: '2026-07-20T12:00:00Z',
  department: null, discussion_duration_minutes: null, legal_framework: null,
  legal_framework_classified_at: null, legal_framework_source: null, party_entities: null,
  plain_language_generated_at: null, plain_language_model: null,
  plain_language_summary_provenance: null, proceeding_classification_attempts: 0,
  proceeding_classification_claim_expires_at: null, proceeding_classification_claim_token: null,
  proceeding_classification_dead_lettered_at: null, proceeding_classification_last_attempted_at: null,
  proceeding_classification_last_error: null, proceeding_type: null,
  public_comment_count: null, resolution_number: null, staff_contact: null, topic_label: null,
}

describe('source-based agenda presentation', () => {
  beforeEach(() => vi.clearAllMocks())

  it('removes isolated AI amount badges from collapsed and expanded agenda cards, preserving labeled prose and detail access', () => {
    for (const forceExpanded of [false, true]) {
      const html = renderToStaticMarkup(<AgendaItemCard item={item} forceExpanded={forceExpanded} />)
      expect(html).not.toContain('$350,000')
      expect(html).toContain(item.title)
      if (forceExpanded) {
        expect(html).toContain('$25,000')
        expect(html).toContain('Auto-generated summary. Source: official agenda documents.')
        expect(html).toContain('/meetings/meeting-1/items/v.1')
      }
    }
  })

  it('keeps incoming consent order without summing mixed financial snippets or claiming automatic approval', () => {
    const entries = [item, { ...item, id: 'entry-2', item_number: 'V.2',
      title: 'Second recorded agenda entry', financial_amount: '$90 million over several years' }]
    const collapsed = renderToStaticMarkup(<ConsentCalendarSection items={entries} />)
    expect(collapsed).toContain('aria-expanded="false"')
    expect(collapsed).toContain('min-h-11 min-w-11')
    expect(collapsed).toMatch(/<h2><button[^>]*>/)
    const expanded = renderToStaticMarkup(<ConsentCalendarSection items={entries} forceExpanded />)
    expect(expanded).toContain('aria-expanded="true"')
    expect(expanded.indexOf(item.title)).toBeLessThan(expanded.indexOf(entries[1].title))
    for (const html of [collapsed, expanded]) {
      expect(html).toContain('Listed on the consent calendar.')
      expect(html).toContain('2 agenda entries')
      expect(html).not.toMatch(/\$350,000|\$90|contracts &amp; approvals|Biggest items|Approved as a group/)
    }
    expect(entries.map(entry => entry.id)).toEqual(['entry-1', 'entry-2'])
  })

  it('still opens a consent entry requested through the table of contents, and renders no empty group', () => {
    expect(renderToStaticMarkup(<ConsentCalendarSection items={[]} />)).toBe('')
    const html = renderToStaticMarkup(<ConsentCalendarSection items={[item]} expandedItemIds={new Set([item.id])} />)
    expect(html).toContain('aria-expanded="true"')
    expect(html).toContain('Show official agenda text')
    expect(html).toContain('Collapse details')
  })

  it('keeps category entries and labeled AI summaries without the separate unverified amount', async () => {
    query.getAgendaItemsByCategory.mockResolvedValue([{ ...item, meeting_date: '2026-07-28', meeting_type: 'regular' }])
    const html = renderToStaticMarkup(await CategoryPage({ params: Promise.resolve({ slug: 'contracts' }) }))
    expect(html).not.toContain('$350,000')
    expect(html).toContain('$25,000')
    expect(html).toContain('Categories and summaries are assigned by AI.')
    expect(html).toContain('1 agenda entry in this archive')
    expect(html).toContain('/meetings/meeting-1/items/v.1')
  })

  it('keeps the original agenda link and labeled prose on item detail while removing the standalone amount', async () => {
    query.getAgendaItemDetail.mockResolvedValue({ ...item, meeting_date: '2026-07-28', comments: [],
      theme_narratives: [], meeting_agenda_url: 'https://www.richmondca.gov/agenda.pdf' })
    const html = renderToStaticMarkup(await AgendaItemDetailPage({ params: Promise.resolve({ id: 'meeting-1', itemNumber: 'V.1' }) }))
    expect(html).not.toContain('$350,000')
    expect(html).toContain('$25,000')
    expect(html).toContain('Auto-generated summary. Source: official agenda documents.')
    expect(html).toContain('href="https://www.richmondca.gov/agenda.pdf"')
    expect(html).toContain('View official agenda')
  })

  it('uses the same source-meeting fallback for legacy item links in cards, categories, and adjacent-item navigation', async () => {
    const legacy = { ...item, item_number: '<unknown>', meeting_date: '2009-10-06', meeting_type: 'regular' }
    const card = renderToStaticMarkup(<AgendaItemCard item={legacy} forceExpanded />)
    query.getAgendaItemsByCategory.mockResolvedValue([legacy])
    const category = renderToStaticMarkup(await CategoryPage({ params: Promise.resolve({ slug: 'contracts' }) }))
    query.getAgendaItemDetail.mockResolvedValue({ ...item, meeting_date: '2026-07-28', comments: [],
      prev_item: { id: 'legacy', item_number: '<unknown>', title: 'Earlier record', summary_headline: null } })
    const detail = renderToStaticMarkup(await AgendaItemDetailPage({ params: Promise.resolve({ id: 'meeting-1', itemNumber: 'V.1' }) }))
    for (const html of [card, category, detail]) {
      expect(html).toContain('href="/meetings/meeting-1"')
      expect(html).not.toContain('/items/%3Cunknown%3E')
    }
    expect(detail).toContain('Earlier record')
  })
})
