import { describe, expect, it } from 'vitest'
import { buildDigestEmail, buildRecapEmail, buildWelcomeEmail } from './email'
import type { Provenance } from './types'

function recap(id: string, provenance: Provenance | null) {
  return {
    id,
    meeting_date: '2026-08-05',
    meeting_type: 'regular',
    meeting_recap: 'Council discussed the agenda item.',
    minutes_url: null,
    meeting_recap_provenance: provenance,
  }
}

const kcrt: Provenance = {
  kind: 'meeting_recording',
  channel: 'kcrt',
  as_of: '2026-08-05T23:00:00Z',
}
const granicus: Provenance = {
  kind: 'meeting_recording',
  channel: 'granicus',
  as_of: '2026-08-05T23:00:00Z',
}

describe('email recap provenance disclosures', () => {
  it('keeps the welcome cadence factual before weekly digest activation', () => {
    const { html, text } = buildWelcomeEmail(
      null,
      'https://example.test/unsubscribe',
      'https://example.test/preferences',
    )

    for (const content of [html, text]) {
      const normalized = content.replace(/\s+/g, ' ')
      expect(normalized).toContain('only when general council emails are enabled')
      expect(normalized).toContain('has not started')
      expect(normalized).not.toContain('Before and after each')
      expect(normalized).not.toContain('weekly recap')
      expect(normalized).toContain('where available')
      expect(normalized).toContain('November election')
      expect(normalized).not.toContain('June primary')
    }
  })

  it('labels a KCRT-only digest from its persisted channel', () => {
    const { text } = buildDigestEmail(
      [recap('11111111-1111-4111-8111-111111111111', kcrt)],
      'https://example.test/unsubscribe',
    )

    expect(text).toContain('KCRT meeting recordings')
    expect(text).not.toContain('Granicus meeting recordings')
  })

  it('labels a Granicus-only digest without claiming KCRT', () => {
    const { text } = buildDigestEmail(
      [recap('22222222-2222-4222-8222-222222222222', granicus)],
      'https://example.test/unsubscribe',
    )

    expect(text).toContain('Granicus meeting recordings')
    expect(text).not.toContain('KCRT meeting recordings')
  })

  it('names both persisted channels in a mixed recording digest', () => {
    const { text } = buildDigestEmail(
      [
        recap('33333333-3333-4333-8333-333333333333', kcrt),
        recap('44444444-4444-4444-8444-444444444444', granicus),
      ],
      'https://example.test/unsubscribe',
    )

    expect(text).toContain('KCRT and Granicus meeting recordings')
  })

  it('uses a channel-neutral disclosure when any persisted source is missing', () => {
    const { text } = buildDigestEmail(
      [
        recap('55555555-5555-4555-8555-555555555555', kcrt),
        recap('66666666-6666-4666-8666-666666666666', null),
      ],
      'https://example.test/unsubscribe',
    )

    expect(text).toContain('Some source details are unavailable')
    expect(text).not.toContain('KCRT meeting recordings')
    expect(text).not.toContain('Granicus meeting recordings')
  })

  it('marks a digest canary without subscriber-management claims', () => {
    const { subject, html, text } = buildDigestEmail(
      [recap('88888888-8888-4888-8888-888888888888', kcrt)],
      'https://example.test/unused',
      undefined,
      { canary: true },
    )

    expect(subject).toMatch(/^\[CANARY\]/)
    expect(html).toContain('CANARY TEST')
    expect(text).toContain('No subscriber delivery was recorded')
    expect(html).not.toContain('Unsubscribe')
    expect(text).not.toContain('Unsubscribe')
  })

  it('does not infer KCRT for a legacy transcript recap with missing provenance', () => {
    const { text } = buildRecapEmail(
      recap('77777777-7777-4777-8777-777777777777', null),
      'https://example.test/unsubscribe',
      'transcript',
    )

    expect(text).toContain('from a meeting recording')
    expect(text).not.toContain('KCRT')
  })
})
