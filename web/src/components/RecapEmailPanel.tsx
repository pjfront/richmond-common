'use client'

import { useState, useEffect, useCallback } from 'react'

interface RecapEmailPanelProps {
  meetingId: string
  hasRecap: boolean
  hasOrientation: boolean
  recapEmailedAt: string | null
}

type PanelState = 'idle' | 'loading' | 'ready' | 'preview' | 'confirming' | 'sending' | 'sent' | 'error'
type TestState = 'idle' | 'sending' | 'sent' | 'error'

interface RecapStatus {
  has_recap: boolean
  recap_html: string | null
  subscriber_count: number
  recap_emailed_at: string | null
}

type EmailType = 'recap' | 'orientation'

function testLabel(type: EmailType): string {
  return type === 'recap' ? 'recap' : 'orientation'
}

function TestEmailForm({ meetingId, emailType }: { meetingId: string; emailType: EmailType }) {
  const [testEmail, setTestEmail] = useState('')
  const [testState, setTestState] = useState<TestState>('idle')
  const [testResult, setTestResult] = useState<{ type: string } | null>(null)
  const [testError, setTestError] = useState<string | null>(null)

  const handleSendTest = async () => {
    if (!testEmail) return
    setTestState('sending')
    setTestError(null)
    try {
      const res = await fetch('/api/operator/send-recap', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ meeting_id: meetingId, test_email: testEmail }),
      })
      if (!res.ok) {
        const data = await res.json() as { error?: string }
        setTestError(data.error ?? 'Send failed')
        setTestState('error')
        return
      }
      const data = await res.json() as { sent: number; type: string; test: boolean }
      setTestResult({ type: data.type })
      setTestState('sent')
    } catch {
      setTestError('Failed to connect')
      setTestState('error')
    }
  }

  if (testState === 'sent' && testResult) {
    const label = testResult.type === 'recap' ? 'recap' : 'orientation'
    return (
      <div className="flex items-center gap-2 text-sm">
        <span className="text-emerald-700">
          Test {label} email sent to {testEmail}
        </span>
        <button
          onClick={() => { setTestState('idle'); setTestResult(null) }}
          className="text-slate-500 hover:text-slate-700 cursor-pointer"
        >
          Send another
        </button>
      </div>
    )
  }

  return (
    <div className="flex items-center gap-2">
      <input
        type="email"
        placeholder="your@email.com"
        value={testEmail}
        onChange={(e) => setTestEmail(e.target.value)}
        onKeyDown={(e) => { if (e.key === 'Enter') handleSendTest() }}
        className="px-2 py-1 text-sm border border-slate-300 rounded w-48 focus:outline-none focus:ring-1 focus:ring-civic-navy"
      />
      <button
        onClick={handleSendTest}
        disabled={!testEmail || testState === 'sending'}
        className="px-3 py-1 text-sm font-medium text-civic-navy border border-civic-navy rounded hover:bg-civic-navy hover:text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer"
      >
        {testState === 'sending' ? 'Sending...' : `Send test ${testLabel(emailType)}`}
      </button>
      {testState === 'error' && testError && (
        <span className="text-sm text-red-600">{testError}</span>
      )}
    </div>
  )
}

export default function RecapEmailPanel({ meetingId, hasRecap, hasOrientation, recapEmailedAt }: RecapEmailPanelProps) {
  const [state, setState] = useState<PanelState>(hasRecap ? 'idle' : 'idle')
  const [status, setStatus] = useState<RecapStatus | null>(null)
  const [sendResult, setSendResult] = useState<{ sent: number; failed: number; emailed_at: string } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [localEmailedAt, setLocalEmailedAt] = useState(recapEmailedAt)

  const fetchStatus = useCallback(async () => {
    setState('loading')
    try {
      const res = await fetch(`/api/operator/send-recap?meeting_id=${meetingId}`)
      if (!res.ok) {
        setError('Failed to load recap status')
        setState('error')
        return
      }
      const data = await res.json() as RecapStatus
      setStatus(data)
      if (data.recap_emailed_at) setLocalEmailedAt(data.recap_emailed_at)
      setState('ready')
    } catch {
      setError('Failed to connect')
      setState('error')
    }
  }, [meetingId])

  useEffect(() => {
    if (hasRecap) {
      fetchStatus()
    }
  }, [hasRecap, fetchStatus])

  const handleSend = async () => {
    setState('sending')
    try {
      const res = await fetch('/api/operator/send-recap', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ meeting_id: meetingId }),
      })
      if (!res.ok) {
        const data = await res.json() as { error?: string }
        setError(data.error ?? 'Send failed')
        setState('error')
        return
      }
      const data = await res.json() as { sent: number; failed: number; emailed_at: string }
      setSendResult(data)
      setLocalEmailedAt(data.emailed_at)
      setState('sent')
    } catch {
      setError('Failed to send emails')
      setState('error')
    }
  }

  if (!hasRecap) {
    return (
      <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 mb-6 space-y-3">
        <p className="text-sm text-slate-500">
          Recap not yet generated. The pipeline will create one after minutes are extracted.
        </p>
        {hasOrientation && (
          <div>
            <p className="text-xs text-slate-400 mb-1.5">Test orientation email for this meeting</p>
            <TestEmailForm meetingId={meetingId} emailType="orientation" />
          </div>
        )}
      </div>
    )
  }

  const subscriberCount = status?.subscriber_count ?? 0
  const formattedEmailedAt = localEmailedAt
    ? new Date(localEmailedAt).toLocaleDateString('en-US', {
        month: 'long', day: 'numeric', hour: 'numeric', minute: '2-digit',
      })
    : null

  return (
    <div className="bg-slate-50 border border-slate-200 rounded-lg p-4 mb-6">
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-semibold text-civic-navy">Email Recap to Subscribers</h3>
        {formattedEmailedAt && state !== 'sent' && (
          <span className="text-xs text-slate-500">
            Last sent {formattedEmailedAt}
          </span>
        )}
      </div>

      {state === 'loading' && (
        <p className="text-sm text-slate-500">Loading...</p>
      )}

      {state === 'error' && (
        <div className="text-sm text-red-600">
          {error}
          <button
            onClick={fetchStatus}
            className="ml-2 text-civic-navy-light hover:text-civic-navy underline cursor-pointer"
          >
            Retry
          </button>
        </div>
      )}

      {state === 'ready' && (
        <div className="space-y-3">
          <p className="text-sm text-slate-600">
            {subscriberCount === 0
              ? 'No active subscribers yet.'
              : `${subscriberCount} active subscriber${subscriberCount !== 1 ? 's' : ''}.`}
          </p>

          <div className="flex items-center gap-3">
            <button
              onClick={() => setState('preview')}
              className="text-sm text-civic-navy-light hover:text-civic-navy underline cursor-pointer"
            >
              Preview email
            </button>
            {subscriberCount > 0 && (
              <button
                onClick={() => setState('confirming')}
                className="px-3 py-1.5 text-sm font-medium text-white bg-civic-navy rounded hover:bg-civic-navy-light transition-colors cursor-pointer"
              >
                Send to {subscriberCount} subscriber{subscriberCount !== 1 ? 's' : ''}
              </button>
            )}
          </div>

          <div className="border-t border-slate-200 pt-3">
            <p className="text-xs text-slate-400 mb-1.5">Send a test to yourself</p>
            <TestEmailForm meetingId={meetingId} emailType="recap" />
          </div>
        </div>
      )}

      {state === 'preview' && status?.recap_html && (
        <div className="space-y-3">
          <div className="border border-slate-300 rounded bg-white overflow-hidden">
            <iframe
              srcDoc={status.recap_html}
              title="Email preview"
              sandbox=""
              className="w-full h-96 border-0"
            />
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setState('ready')}
              className="text-sm text-slate-500 hover:text-slate-700 cursor-pointer"
            >
              Close preview
            </button>
            {subscriberCount > 0 && (
              <button
                onClick={() => setState('confirming')}
                className="px-3 py-1.5 text-sm font-medium text-white bg-civic-navy rounded hover:bg-civic-navy-light transition-colors cursor-pointer"
              >
                Send to {subscriberCount} subscriber{subscriberCount !== 1 ? 's' : ''}
              </button>
            )}
          </div>
        </div>
      )}

      {state === 'confirming' && (
        <div className="bg-amber-50 border border-amber-200 rounded p-3">
          <p className="text-sm text-slate-700 mb-3">
            Send this recap email to <strong>{subscriberCount}</strong> subscriber{subscriberCount !== 1 ? 's' : ''}?
            {formattedEmailedAt && (
              <span className="text-amber-700"> This meeting was already emailed on {formattedEmailedAt}.</span>
            )}
          </p>
          <div className="flex items-center gap-3">
            <button
              onClick={handleSend}
              className="px-3 py-1.5 text-sm font-medium text-white bg-civic-navy rounded hover:bg-civic-navy-light transition-colors cursor-pointer"
            >
              Confirm send
            </button>
            <button
              onClick={() => setState(status?.recap_html ? 'preview' : 'ready')}
              className="text-sm text-slate-500 hover:text-slate-700 cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {state === 'sending' && (
        <p className="text-sm text-slate-600">Sending emails...</p>
      )}

      {state === 'sent' && sendResult && (
        <div className="bg-emerald-50 border border-emerald-200 rounded p-3">
          <p className="text-sm text-emerald-800">
            Sent to {sendResult.sent} subscriber{sendResult.sent !== 1 ? 's' : ''}.
            {sendResult.failed > 0 && (
              <span className="text-red-600"> {sendResult.failed} failed.</span>
            )}
          </p>
          <button
            onClick={fetchStatus}
            className="mt-2 text-xs text-slate-500 hover:text-slate-700 cursor-pointer"
          >
            Done
          </button>
        </div>
      )}
    </div>
  )
}
