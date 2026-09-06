import { describe, expect, it } from 'vitest'
import { renderToStaticMarkup } from 'react-dom/server'
import { DecisionCard } from '@/app/operator/decisions/OperatorDecisionsPage'
import { availableReviewActions, safeEvidenceLink, type ReviewDecision } from './decision-review'

const decision = {
  id: '11111111-1111-4111-8111-111111111111', title: 'Review a source-backed meeting brief',
  description: 'Check the source before publication.', severity: 'medium', status: 'pending',
  review_class: 'editorial', review_version: 2, action_kind: 'publish_brief', target_content_version: 1,
  created_at: '2026-09-06T10:00:00Z', source: 'meeting_brief_generator', link: 'javascript:alert(1)',
  evidence: { recommendation: 'Approve after checking the vote.', affected_pages: ['/meetings/2026-07-07'], alternatives: ['Keep as a draft.'] },
  candidate: {
    id: 'candidate', kind: 'meeting_brief', title: 'A motion on the July agenda', body: 'Exact proposed text <script>alert(1)</script>',
    content_version: 1, status: 'draft', sources: [{ title: 'Official minutes', url: 'https://www.ci.richmond.ca.us/Archive.aspx?ADID=1', source_tier: 1 }],
  },
} as unknown as ReviewDecision

describe('review packet rendering', () => {
  it('shows exact text, recommendation, alternatives, affected pages, and linked sources', () => {
    const html = renderToStaticMarkup(<DecisionCard decision={decision} history={[]} onSaved={async () => {}} />)
    for (const text of ['Approve and publish', 'Exact proposed text', 'Official minutes', 'Keep as a draft.', '/meetings/2026-07-07', 'Approve after checking the vote.']) expect(html).toContain(text)
    expect(html).not.toContain('<script>')
    expect(html).not.toContain('href="javascript:')
    expect(html).toContain('Decision note')
  })

  it('does not label generic approval as publishing or executing a fix', () => {
    const generic = { ...decision, action_kind: 'resolve_only', candidate: null, review_class: 'engineering' } as ReviewDecision
    const html = renderToStaticMarkup(<DecisionCard decision={generic} history={[]} onSaved={async () => {}} />)
    expect(html).not.toContain('Approve and publish')
    expect(html).toContain('separate operation')
  })

  it('requires explicit withdrawal for published briefs and retains note editing', () => {
    const published = { ...decision, status: 'approved', candidate: { ...decision.candidate!, status: 'published' } } as ReviewDecision
    expect(availableReviewActions(published)).toEqual(['edit_note', 'withdraw'])
  })

  it.each(['javascript:alert(1)', 'data:text/html,hi', '//attacker.invalid', '/\\attacker.invalid', 'https://user:password@example.org'])('never makes unsafe evidence a link: %s', value => {
    expect(safeEvidenceLink(value)).toBeNull()
  })
})
