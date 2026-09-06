import { describe, expect, it, vi } from 'vitest'
import type { SupabaseClient } from '@supabase/supabase-js'
import { createHash } from 'node:crypto'
import { loadPublishedDigestBriefs, selectSubscriberDigest, type DigestBrief } from './digest-selection'
import { buildDigestEmail } from './email'

const brief: DigestBrief = { id: '11111111-1111-4111-8111-111111111111', subject_key: '2026-general', title: 'An exact reviewed update', body: 'A proposal is on the agenda; this does not establish adoption.', sources: [{ url: 'https://www.richmondca.gov/Archive.aspx?ADID=17785', title: 'Official record', source_tier: 1, source_date: '2026-07-21' }], content_version: 1, published_at: '2026-09-01T12:00:00Z' }
const period = { start: '2026-08-31', end: '2026-09-06', contentKey: 'week:2026-08-31' }
const meetings = [{ id: 'housing' }, { id: 'refinery' }]
const topics = new Map([['housing', new Set(['Housing'])], ['refinery', new Set(['Chevron'])]])
const labels = new Map([['housing', 'Housing'], ['chevron', 'Chevron']])

describe('one weekly digest selection contract', () => {
  it('preserves general subscribers with no preferences, without opting them into new subjects', () => {
    expect(selectSubscriberDigest(meetings, [brief], { id: 'resident', receive_council_updates: true }, [], topics, labels)).toEqual({ meetings, briefs: [] })
  })
  it('selects only followed subjects for a subject-only subscriber, even with empty topics', () => {
    const preferences = [{ subscriber_id: 'resident', preference_type: 'subject', preference_value: '2026-general' }]
    expect(selectSubscriberDigest(meetings, [brief, { ...brief, id: 'unfollowed', subject_key: 'fire-stations-and-emergency-response' }], { id: 'resident', receive_council_updates: false }, preferences, topics, labels)).toEqual({ meetings: [], briefs: [brief] })
  })
  it('intersects topic recaps and subject briefs independently and ignores another subscriber choices', () => {
    const preferences = [{ subscriber_id: 'resident', preference_type: 'topic', preference_value: 'housing' }, { subscriber_id: 'other', preference_type: 'subject', preference_value: '2026-general' }]
    expect(selectSubscriberDigest(meetings, [brief], { id: 'resident', receive_council_updates: true }, preferences, topics, labels)).toEqual({ meetings: [{ id: 'housing' }], briefs: [] })
    expect(selectSubscriberDigest(meetings, [brief], { id: 'resident', receive_council_updates: false }, [], topics, labels)).toEqual({ meetings: [], briefs: [] })
  })
  it('includes exact approved text, source links and version identity in both email formats and their payload hash', () => {
    const original = buildDigestEmail([], '/unsubscribe', '/manage', { briefs: [brief] })
    expect(original.subject).toContain('1 reviewed update')
    for (const text of [original.html, original.text]) {
      expect(text).toContain('does not establish adoption')
      expect(text).toContain('version 1')
      expect(text).toContain('#brief-11111111-1111-4111-8111-111111111111-v1')
      expect(text).toContain(brief.sources[0].url)
      expect(text).toContain('AI-written; checked against linked sources')
      expect(text).not.toMatch(/operator-reviewed|human-reviewed/)
    }
    const fingerprint = (version: number) => createHash('sha256').update(JSON.stringify(buildDigestEmail([], '/unsubscribe', '/manage', { briefs: [{ ...brief, content_version: version }] }))).digest('hex')
    expect(fingerprint(1)).not.toBe(fingerprint(2))
    expect(buildDigestEmail([], '/unsubscribe', '/manage', { briefs: [{ ...brief, title: '<script>bad</script>', body: '<img onerror="bad">' }] }).html).not.toContain('<script>')
  })
})

describe('published brief source windows', () => {
  function client(rows: unknown[], error: unknown = null) {
    const query = { select: vi.fn(), eq: vi.fn(), in: vi.fn(), or: vi.fn(), order: vi.fn(), limit: vi.fn(), then: (resolve: (value: unknown) => unknown) => Promise.resolve({ data: rows, error }).then(resolve) }
    for (const method of [query.select, query.eq, query.in, query.or, query.order, query.limit]) method.mockReturnValue(query)
    return { query, supabase: { from: vi.fn(() => query) } as unknown as SupabaseClient }
  }
  it('uses published versions and excludes midnight at the following week with offset-form timestamps', async () => {
    const { query, supabase } = client([brief, { ...brief, published_at: '2026-09-07T00:00:00+00:00' }])
    expect((await loadPublishedDigestBriefs(supabase, [period])).get(period.contentKey)).toEqual([brief])
    expect(query.eq).toHaveBeenCalledWith('status', 'published')
    expect(query.select).toHaveBeenCalledWith(expect.stringContaining('content_version,published_at'))
    expect(query.or).toHaveBeenCalledWith(expect.stringContaining('published_at.lt.2026-09-07T00:00:00.000Z'))
    expect(query.limit).toHaveBeenCalledWith(201)
  })
  it('treats unavailable or unbounded source reads as a failure, never an empty successful week', async () => {
    await expect(loadPublishedDigestBriefs(client([], { code: 'timeout' }).supabase, [period])).rejects.toThrow('could not be loaded')
    await expect(loadPublishedDigestBriefs(client(Array(201).fill(brief)).supabase, [period])).rejects.toThrow('source cap')
    await expect(loadPublishedDigestBriefs(client(Array(41).fill(brief)).supabase, [period])).rejects.toThrow('weekly cap')
    await expect(loadPublishedDigestBriefs(client([{ ...brief, sources: [] }]).supabase, [period])).rejects.toThrow('review provenance')
    await expect(loadPublishedDigestBriefs(client([{ ...brief, published_at: 'invalid' }]).supabase, [period])).rejects.toThrow('review provenance')
  })
})
