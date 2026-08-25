import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { renderToStaticMarkup } from 'react-dom/server'
import { describe, expect, it } from 'vitest'
import CivicTerm from './CivicTerm'
import VotingRecordTable from './VotingRecordTable'

const vote = {
  id: 'vote-1',
  vote_choice: 'aye',
  meeting_id: 'meeting-1',
  meeting_date: '2026-08-01',
  meeting_type: 'Regular Meeting',
  item_number: 'A-1',
  item_title: 'Example agenda item',
  category: 'housing',
  motion_result: 'passed',
  has_nay_votes: true,
  is_consent_calendar: false,
}

describe('critical shared accessibility contracts', () => {
  it('keeps every CivicTerm description target in the DOM while the tooltip is closed', () => {
    const html = renderToStaticMarkup(
      <CivicTerm
        term="Campaign Finance Filing"
        category="NetFile"
        definition="A required public report about campaign money."
      >
        donation records
      </CivicTerm>,
    )

    const descriptionId = html.match(/role="term"[^>]*aria-describedby="([^"]+)"/)?.[1]

    expect(descriptionId).toBeDefined()
    expect(html).toContain(`id="${descriptionId}"`)
    expect(html).toContain('Official term: Campaign Finance Filing.')
    expect(html).toContain('Category: NetFile.')
    expect(html).toContain('A required public report about campaign money.')
  })

  it('associates plain-language labels with both council-profile selects', () => {
    const html = renderToStaticMarkup(<VotingRecordTable votes={[vote]} />)

    expect(html).toContain('for="vote-choice-filter"')
    expect(html).toContain('id="vote-choice-filter"')
    expect(html).toContain('Filter votes by choice')
    expect(html).toContain('for="voting-record-sort"')
    expect(html).toContain('id="voting-record-sort"')
    expect(html).toContain('Sort voting record')
    expect(html.match(/<select[^>]*class="[^"]*min-h-11[^"]*"/g) ?? []).toHaveLength(2)
    expect(html).toContain('class="text-xs text-amber-700"')
  })

  it('provides an h2 section before council-member card headings', () => {
    const source = readFileSync(
      fileURLToPath(new URL('../app/council/page.tsx', import.meta.url)),
      'utf8',
    )

    const sectionHeadingAt = source.indexOf('<h2 id="current-council-heading"')
    const cardsAt = source.indexOf('{current.map')

    expect(sectionHeadingAt).toBeGreaterThanOrEqual(0)
    expect(cardsAt).toBeGreaterThan(sectionHeadingAt)
    expect(source).toContain('<section aria-labelledby="current-council-heading">')
  })
})
