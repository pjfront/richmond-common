'use client'

import { useCallback, useEffect, useRef, useState } from 'react'
import OperatorGate from '@/components/OperatorGate'
import {
  availableReviewActions, evidenceLabel, reviewErrorMessage, safeEvidenceLink,
  type ReviewAction, type ReviewDecision, type ReviewHistoryEntry, type ReviewQueueData,
} from '@/lib/decision-review'

const ACTION_LABELS: Record<ReviewAction, string> = {
  approve: 'Approve', reject: 'Reject', defer: 'Defer', reopen: 'Reopen',
  edit_note: 'Save note', withdraw: 'Withdraw published brief',
}

function EvidenceValue({ value, depth = 0 }: { value: unknown; depth?: number }) {
  if (value === null || value === undefined) return <span className="text-slate-600">Not recorded</span>
  if (Array.isArray(value)) return <ul className="space-y-2 pl-4 list-disc">{value.map((entry, index) => <li key={index}><EvidenceValue value={entry} depth={depth + 1} /></li>)}</ul>
  if (typeof value === 'object') {
    const record = value as Record<string, unknown>
    const link = safeEvidenceLink(record.url ?? record.source_url)
    return <div className="space-y-2">
      {link && <a href={link} target="_blank" rel="noopener noreferrer" className="text-civic-navy underline break-words">{typeof record.title === 'string' ? record.title : 'Open source record'}</a>}
      <dl className="space-y-2">{Object.entries(record).filter(([key]) => !(link && ['url', 'source_url', 'title'].includes(key))).map(([key, entry]) => (
        <div key={key} className={depth < 2 ? 'border-l-2 border-slate-200 pl-3' : ''}>
          <dt className="font-medium text-slate-800">{evidenceLabel(key)}</dt>
          <dd className="mt-1 break-words"><EvidenceValue value={entry} depth={depth + 1} /></dd>
        </div>
      ))}</dl>
    </div>
  }
  const link = safeEvidenceLink(value)
  return link ? <a href={link} target="_blank" rel="noopener noreferrer" className="text-civic-navy underline break-words">{String(value)}</a>
    : <span className="whitespace-pre-wrap break-words">{String(value)}</span>
}

export function DecisionCard({ decision, history, onSaved }: {
  decision: ReviewDecision; history: ReviewHistoryEntry[]; onSaved: (message: string) => Promise<void>
}) {
  const [note, setNote] = useState(decision.resolution_note ?? '')
  const [busy, setBusy] = useState<ReviewAction | null>(null)
  const [error, setError] = useState<string | null>(null)
  const lastRequest = useRef<{ signature: string; key: string } | null>(null)
  const candidate = decision.candidate
  const staleContent = candidate && candidate.content_version !== decision.target_content_version
  const sourceLink = safeEvidenceLink(decision.link)
  const events = history.filter(event => event.decision_id === decision.id)

  async function act(action: ReviewAction) {
    if (action === 'withdraw' && !note.trim()) { setError('Add a note explaining why this published brief should be withdrawn.'); return }
    const payload = { decision_id: decision.id, action, expected_version: decision.review_version, note: note || null }
    const signature = JSON.stringify(payload)
    if (lastRequest.current?.signature !== signature) lastRequest.current = { signature, key: crypto.randomUUID() }
    setBusy(action); setError(null)
    try {
      const response = await fetch('/api/operator/decisions', {
        method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...payload, idempotency_key: lastRequest.current.key }),
      })
      const result = await response.json()
      if (!response.ok || !result.ok) throw new Error(reviewErrorMessage(result.code ?? 'review_failed'))
      const message = result.effect === 'brief_published' ? 'Brief published with its reviewed sources.'
        : result.effect === 'brief_withdrawn' ? 'Brief withdrawn. Its evidence and review history are preserved.'
        : action === 'edit_note' ? 'Note saved.' : action === 'defer' ? 'Decision deferred. It remains available in this inbox.'
        : action === 'reopen' ? 'Decision reopened.' : `Decision ${result.status}.`
      await onSaved(message)
      lastRequest.current = null
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : 'The action could not be saved. Retry with your note below.')
    } finally { setBusy(null) }
  }

  return <article className="rounded-xl border border-slate-200 bg-white p-5 sm:p-6 space-y-4" aria-labelledby={`decision-${decision.id}`}>
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <span className="rounded bg-slate-100 px-2 py-1 font-medium text-slate-800">{decision.review_class === 'editorial' ? 'Editorial judgment' : 'Engineering follow-up'}</span>
      <span className="text-slate-700">{evidenceLabel(decision.severity)} priority · {evidenceLabel(decision.status)}</span>
    </div>
    <div>
      <h3 id={`decision-${decision.id}`} className="text-xl font-semibold text-slate-900">{decision.title}</h3>
      <p className="mt-2 text-base text-slate-700 whitespace-pre-wrap">{decision.description}</p>
      <p className="mt-2 text-sm text-slate-600">From {evidenceLabel(decision.source)} · <time dateTime={decision.created_at}>{new Date(decision.created_at).toLocaleDateString()}</time> · Review version {decision.review_version}</p>
      {sourceLink && <a href={sourceLink} target="_blank" rel="noopener noreferrer" className="inline-flex min-h-11 items-center text-civic-navy underline">Open supporting record</a>}
    </div>
    {decision.action_kind === 'resolve_only' && <p className="rounded-lg bg-slate-50 p-3 text-sm text-slate-700">This action records your decision. Any recommended repair or pipeline run remains a separate operation.</p>}
    {candidate && <section className="rounded-lg border border-slate-300 p-4 space-y-3" aria-label="Exact proposed publication">
      <p className="text-sm text-slate-600">Proposed public brief · {evidenceLabel(candidate.kind)} · Content version {candidate.content_version} · {evidenceLabel(candidate.status)}</p>
      <h4 className="font-semibold text-lg text-slate-900">{candidate.title}</h4>
      <div className="text-base text-slate-800 whitespace-pre-wrap break-words">{candidate.body}</div>
      <div className="border-t border-slate-200 pt-3"><h5 className="font-semibold text-slate-900 mb-2">Sources that will accompany this brief</h5><EvidenceValue value={candidate.sources} /></div>
      {staleContent && <p role="alert" className="text-red-800">The text or sources changed after this review was prepared. A refreshed packet is required before approval.</p>}
    </section>}
    {decision.evidence && Object.keys(decision.evidence).length > 0 && <details className="rounded-lg bg-slate-50 p-3" open={decision.action_kind === 'resolve_only'}>
      <summary className="cursor-pointer min-h-11 font-semibold text-slate-900">Evidence, recommendation, and affected pages</summary>
      <div className="mt-2 text-base text-slate-700"><EvidenceValue value={decision.evidence} /></div>
    </details>}
    <div>
      <label htmlFor={`note-${decision.id}`} className="block font-medium text-slate-800 mb-2">Decision note <span className="font-normal text-slate-600">(optional; required to withdraw)</span></label>
      <textarea id={`note-${decision.id}`} value={note} onChange={event => setNote(event.target.value)} maxLength={4000} rows={3}
        className="w-full rounded-lg border border-slate-300 p-3 text-base text-slate-900 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-civic-navy" />
      {error && <p role="alert" className="mt-2 text-red-800">{error}</p>}
      <div className="flex flex-wrap gap-2 mt-3">{availableReviewActions(decision).map(action => <button key={action} type="button" onClick={() => void act(action)}
        disabled={busy !== null || (action === 'approve' && !!staleContent)}
        className={`min-h-11 rounded-lg border px-4 py-2 text-base font-medium focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-civic-navy disabled:opacity-60 ${action === 'approve' ? 'border-civic-navy bg-civic-navy text-white' : action === 'withdraw' ? 'border-red-300 text-red-800' : 'border-slate-300 text-slate-800 hover:bg-slate-50'}`}>
        {busy === action ? 'Saving…' : action === 'approve' && decision.action_kind === 'publish_brief' ? 'Approve and publish' : ACTION_LABELS[action]}
      </button>)}</div>
      {busy && <p role="status" className="mt-2 text-sm text-slate-600">Saving this review and its audit record…</p>}
    </div>
    {events.length > 0 && <details className="border-t border-slate-200 pt-3"><summary className="min-h-11 cursor-pointer text-slate-700 font-medium">Review history ({events.length})</summary>
      <ol className="space-y-3 text-sm text-slate-700">{events.map(event => <li key={event.id}>
        <span className="font-semibold">{evidenceLabel(event.action)}</span> by {event.actor} · {new Date(event.created_at).toLocaleString()} · reviewed version {event.expected_version}
        {event.note && <p className="mt-1 whitespace-pre-wrap">{event.note}</p>}
      </li>)}</ol>
    </details>}
  </article>
}

function DecisionsDashboard() {
  const [data, setData] = useState<ReviewQueueData | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState('')
  const [filter, setFilter] = useState('all')
  const noticeRef = useRef<HTMLParagraphElement>(null)
  const load = useCallback(async () => {
    const response = await fetch('/api/operator/decisions', { cache: 'no-store', credentials: 'same-origin' })
    if (!response.ok) throw new Error('The inbox is unavailable. Try refreshing in a moment.')
    setData(await response.json()); setError(null)
  }, [])
  useEffect(() => { void load().catch(reason => setError(reason.message)) }, [load])
  useEffect(() => { if (notice) noticeRef.current?.focus() }, [notice])
  async function saved(message: string) {
    try { await load(); setNotice(message) } catch { setNotice(`${message} Refresh to load the latest inbox.`) }
  }
  const visible = (items: ReviewDecision[]) => items.filter(item => filter === 'all' || item.review_class === filter)
  return <div className="space-y-6">
    {notice && <p role="status" tabIndex={-1} ref={noticeRef} className="rounded-lg bg-green-50 border border-green-200 p-4 text-green-900 focus-visible:outline-2">{notice}</p>}
    <div className="flex flex-wrap gap-3 items-end justify-between"><div>
      <label htmlFor="review-filter" className="block text-sm font-medium text-slate-700 mb-1">Show</label>
      <select id="review-filter" value={filter} onChange={event => setFilter(event.target.value)} className="min-h-11 rounded-lg border border-slate-300 p-2 text-base text-slate-800">
        <option value="all">All decisions</option><option value="editorial">Editorial judgments</option><option value="engineering">Engineering follow-ups</option>
      </select>
    </div><button type="button" onClick={() => void load().catch(reason => setError(reason.message))} className="min-h-11 rounded-lg border border-slate-300 px-4 text-slate-800">Refresh inbox</button></div>
    {error && <p role="alert" className="text-red-800">{error}</p>}
    {!data && !error && <p role="status" className="text-slate-700">Loading decisions and supporting evidence…</p>}
    {data && <>
      <section aria-labelledby="ready-decisions" className="space-y-4"><h2 id="ready-decisions" className="text-xl font-semibold text-slate-900">Ready for review ({visible(data.pending).length})</h2>
        {data.limited && <p className="text-slate-700">Showing the oldest 100 open decisions. More appear as these are resolved.</p>}
        {visible(data.pending).length === 0 && <p className="text-slate-700">No decisions waiting in this view.</p>}
        {visible(data.pending).map(decision => <DecisionCard key={`${decision.id}:${decision.review_version}`} decision={decision} history={data.history} onSaved={saved} />)}
      </section>
      {data.deferred.length > 0 && <section aria-labelledby="deferred-decisions" className="space-y-4"><h2 id="deferred-decisions" className="text-xl font-semibold text-slate-900">Deferred ({visible(data.deferred).length})</h2>
        {visible(data.deferred).map(decision => <DecisionCard key={`${decision.id}:${decision.review_version}`} decision={decision} history={data.history} onSaved={saved} />)}
      </section>}
      {data.recently_resolved.length > 0 && <details className="space-y-4"><summary className="min-h-11 cursor-pointer font-semibold text-lg text-slate-800">Recent decisions ({visible(data.recently_resolved).length})</summary>
        {visible(data.recently_resolved).map(decision => <DecisionCard key={`${decision.id}:${decision.review_version}`} decision={decision} history={data.history} onSaved={saved} />)}
      </details>}
    </>}
  </div>
}

export default function OperatorDecisionsPage() {
  return <OperatorGate fallback={<p className="max-w-4xl mx-auto px-4 py-12 text-slate-700">Sign in as the operator to review decisions.</p>}>
    <div className="max-w-4xl mx-auto px-4 sm:px-6 py-8"><header className="mb-8">
      <h1 className="text-3xl font-semibold text-slate-900">Review inbox</h1>
      <p className="text-base text-slate-700 mt-3">Read the evidence, record your judgment, and publish prepared briefs when they are ready. Every action keeps a review history.</p>
    </header><DecisionsDashboard /></div>
  </OperatorGate>
}
