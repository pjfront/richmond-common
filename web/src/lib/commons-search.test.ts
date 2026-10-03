import { describe, expect, it } from 'vitest'
import { commonsSearchParams, matchesCommonsScope, planCommonsSearch, publicSourceUrl } from './commons-search'

const plan = (query: string) => planCommonsSearch(new URLSearchParams(query))

describe('disclosed staging search grammar and bounds', () => {
  it('separates a topic and year from a simple resident question', () => {
    expect(plan('q=Show+me+housing+decisions+in+2026')).toMatchObject({ mode: 'agenda', keywords: 'housing', from: '2026-01-01', to: '2026-12-31' })
    expect(plan('q=Who+voted+on+Point+Molate%3F')).toMatchObject({ mode: 'votes', keywords: 'Point Molate' })
  })
  it('keeps money direction explicit and never treats a donation phrase as all activity', () => {
    expect(plan('q=Donations+to+Jimenez')).toMatchObject({ mode: 'money', keywords: 'Jimenez', moneyRole: 'recipient', contributionsOnly: true })
    expect(plan('q=Contributions+from+Chevron')).toMatchObject({ mode: 'money', keywords: 'Chevron', moneyRole: 'source', contributionsOnly: true })
    expect(plan('mode=money&q=Chevron')).toMatchObject({ keywords: 'Chevron', moneyRole: '', contributionsOnly: false })
  })
  it('leaves unsupported questions literal instead of inventing a vote-choice or causal answer', () => {
    expect(plan('mode=votes&q=Who+voted+against+housing%3F').keywords).toBe('Who voted against housing')
    expect(plan('q=Did+donations+change+the+vote%3F').keywords).toBe('Did donations change the vote')
  })
  it.each(['from=2026-02-30', 'from=2026-10-01&to=2026-09-01', 'q=housing+in+2026&from=2027-01-01', 'page=-1', 'page=101', 'page=1.5', 'mode=chat', 'mode=money&topic=housing'])('rejects ambiguous or invalid scope: %s', query => {
    expect(() => plan(query)).toThrow()
  })
  it('preserves shareable scope without serializing interpretation or parser internals', () => {
    const params = commonsSearchParams(plan('q=housing+in+2026&topic=Housing&page=2'))
    expect([...params.keys()].sort()).toEqual(['from', 'mode', 'page', 'q', 'to', 'topic'])
    expect(params.get('page')).toBe('2')
    expect(plan(params.toString()).from).toBe('2026-01-01')
  })
  it('applies tags as exact labels and dates inclusively', () => {
    const filters = plan('topic=Housing&from=2026-01-01&to=2026-12-31')
    expect(matchesCommonsScope({ topic: 'Housing', meetingDate: '2026-01-01' }, filters)).toBe(true)
    expect(matchesCommonsScope({ topic: 'Housing policy', meetingDate: '2026-05-01' }, filters)).toBe(false)
    expect(matchesCommonsScope({ topic: 'Housing', meetingDate: '2025-12-31' }, filters)).toBe(false)
  })
  it('allows original public links without accepting executable or credential-bearing URLs', () => {
    expect(publicSourceUrl('https://example.gov/agenda.pdf')).toBe('https://example.gov/agenda.pdf')
    expect(publicSourceUrl('javascript:alert(1)')).toBeNull()
    expect(publicSourceUrl('https://user:password@example.gov/agenda')).toBeNull()
  })
})
