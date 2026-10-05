import { describe, expect, it } from 'vitest'
import { commonsSearchParams, matchesCommonsScope, planCommonsSearch, publicSourceUrl } from './commons-search'

const plan = (query: string) => planCommonsSearch(new URLSearchParams(query))

describe('disclosed staging search grammar and bounds', () => {
  it.each([
    ['Show me donations to Claudia Jimenez in 2026', { mode: 'money', keywords: 'Claudia Jimenez', moneyRole: 'recipient', contributionsOnly: true, from: '2026-01-01', to: '2026-12-31' }],
    ['Find contributions from Chevron during 2026?', { mode: 'money', keywords: 'Chevron', moneyRole: 'source', contributionsOnly: true, from: '2026-01-01', to: '2026-12-31' }],
    ['List donations to Jimenez', { mode: 'money', keywords: 'Jimenez', moneyRole: 'recipient', contributionsOnly: true }],
    ['Who donated to Jimenez in 2026?', { mode: 'money', keywords: 'Jimenez', moneyRole: 'recipient', contributionsOnly: true, from: '2026-01-01', to: '2026-12-31' }],
    ['Find me who contributed to Jimenez during 2026', { mode: 'money', keywords: 'Jimenez', moneyRole: 'recipient', contributionsOnly: true, from: '2026-01-01', to: '2026-12-31' }],
    ['Show me who voted on Point Molate in 2010?', { mode: 'votes', keywords: 'Point Molate', moneyRole: '', contributionsOnly: false, from: '2010-01-01', to: '2010-12-31' }],
    ['What housing decisions were made in 2026?', { mode: 'agenda', keywords: 'housing', from: '2026-01-01', to: '2026-12-31' }],
    ['What decisions were made about housing during 2026', { mode: 'agenda', keywords: 'housing', from: '2026-01-01', to: '2026-12-31' }],
    ['What climate change decisions were made in 2026', { mode: 'agenda', keywords: 'climate change', from: '2026-01-01', to: '2026-12-31' }],
    ['Donations to Committee to Elect Claudia Jimenez in 2026', { mode: 'money', keywords: 'Committee to Elect Claudia Jimenez', moneyRole: 'recipient', contributionsOnly: true }],
    ['Contributions from Committee to Elect Claudia Jimenez in 2026', { mode: 'money', keywords: 'Committee to Elect Claudia Jimenez', moneyRole: 'source', contributionsOnly: true }],
  ])('recognizes bounded record lookup: %s', (q, expected) => {
    const result = planCommonsSearch(new URLSearchParams({ q }))
    expect(result).toMatchObject(expected)
    expect(result.q).toBe(q)
    expect(result.interpretation[0]).toBe(`Records: ${{ agenda: 'Agenda items', votes: 'Recorded votes', money: 'Campaign money' }[result.mode]}`)
    expect(result.interpretation.join(' ')).not.toContain('this question is not answered')
    if (result.moneyRole) {
      expect(result.interpretation.join(' ')).toContain('name contains:')
      expect(result.interpretation).toContain('Cash contribution records')
    }
  })
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
  it.each([
    ['How many donations did Jimenez receive in 2026?', 'money'],
    ['What is the total donated to Jimenez in 2026?', 'money'],
    ['Did donations change the vote in 2026?', 'votes'],
    ['Why did Jimenez vote for housing in 2026?', 'votes'],
    ['How did Jimenez vote on Point Molate in 2010?', 'votes'],
    ['Who voted against housing in 2026?', 'votes'],
    ['Who voted on Point Molate against the proposal in 2010?', 'votes'],
    ['Who donated to Jimenez and how did they vote in 2026?', 'money'],
    ['Donations to Jimenez from Chevron in 2026', 'money'],
    ['Contributions from Chevron to Jimenez in 2026', 'money'],
    ['Donations to Jimenez and from Chevron in 2026', 'money'],
    ['Donations to Jimenez over $500 in 2026', 'money'],
    ['Donations to Jimenez that changed the vote in 2026', 'money'],
    ['Who voted on Point Molate in 2010 and during 2011?', 'votes'],
    ['Who donated to Jimenez last year?', 'money'],
    ['Housing decisions between 2020 and 2026', 'agenda'],
  ])('keeps unsupported or compound requests as disclosed keywords: %s', (q, mode) => {
    const result = planCommonsSearch(new URLSearchParams({ q, mode }))
    expect(result).toMatchObject({ mode, keywords: q.replace(/\?+$/, ''), moneyRole: '', contributionsOnly: false, from: '', to: '' })
    expect(result.interpretation).toContain('Keyword search only; this question is not answered')
    expect(result.interpretation.join(' ')).not.toMatch(/name contains:|Cash contribution records|(?:Activity|Meeting) dates:/)
    expect(result).not.toHaveProperty('voterName')
    expect(result).not.toHaveProperty('voteChoice')
  })
  it('treats empty Auto mode as unspecified but preserves explicit record modes and the type alias', () => {
    expect(plan('mode=&q=Show+me+donations+to+Jimenez+in+2026')).toMatchObject({ mode: 'money', moneyRole: 'recipient' })
    expect(plan('mode=&type=votes&q=housing')).toMatchObject({ mode: 'votes', keywords: 'housing' })
    expect(plan('mode=agenda&type=money&q=Who+voted+on+Point+Molate+in+2010')).toMatchObject({ mode: 'agenda', keywords: 'Point Molate', moneyRole: '', contributionsOnly: false })
    const override = plan('mode=agenda&q=Show+me+donations+to+Jimenez+in+2026')
    expect(override).toMatchObject({ mode: 'agenda', keywords: 'donations to Jimenez', moneyRole: '', contributionsOnly: false })
    expect(override.interpretation).toContain('Selected agenda mode; question wording is searched as keywords')
  })
  it('fills missing year bounds, keeps raw date overrides, and makes a different explicit period visible', () => {
    const inferred = plan('q=Who+donated+to+Jimenez+in+2026')
    expect(inferred).toMatchObject({ from: '2026-01-01', to: '2026-12-31' })
    expect(inferred.interpretation.join(' ')).not.toContain('Explicit date filters')
    expect(plan('q=Who+donated+to+Jimenez+in+2026&from=2026-07-01')).toMatchObject({ from: '2026-07-01', to: '2026-12-31' })
    expect(plan('q=Who+voted+on+Point+Molate+in+2010&to=2010-03-02')).toMatchObject({ from: '2010-01-01', to: '2010-03-02' })
    const explicit = plan('q=Who+voted+on+Point+Molate+in+2010&from=2011-01-01&to=2011-12-31')
    expect(explicit).toMatchObject({ from: '2011-01-01', to: '2011-12-31', keywords: 'Point Molate' })
    expect(explicit.interpretation).toContain('Explicit date filters take precedence over the year in the question')
    const resolved = plan(commonsSearchParams(inferred).toString())
    expect(resolved.interpretation.join(' ')).not.toContain('Explicit date filters')
  })
  it.each(['from=2026-02-30', 'from=2026-10-01&to=2026-09-01', 'q=housing+in+2026&from=2027-01-01', 'page=-1', 'page=101', 'page=1.5', 'mode=chat', 'mode=auto', 'mode=money&topic=housing', `q=${'x'.repeat(201)}`, `topic=${'x'.repeat(101)}`])('rejects ambiguous or invalid scope: %s', query => {
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
