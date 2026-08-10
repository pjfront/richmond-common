'use client'

import { useId, useState } from 'react'
import type { SubscribeResponse } from '@/lib/types'

export type SubscriptionSurface =
  | 'homepage'
  | 'nav'
  | 'footer'
  | 'meeting'
  | 'subscribe_page'
  | 'november_election'

interface SubscribeFormProps {
  /** Compact mode for inline CTAs (no name field, smaller text). */
  compact?: boolean
  /** Allowlisted, coarse acquisition surface. Never includes a raw URL. */
  surface?: SubscriptionSurface
}

export default function SubscribeForm({ compact = false, surface = 'subscribe_page' }: SubscribeFormProps) {
  const idPrefix = useId()
  const nameId = `${idPrefix}-name`
  const emailId = `${idPrefix}-email`
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const [manageToken, setManageToken] = useState<string | null>(null)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!email.trim()) return

    setStatus('submitting')

    try {
      const res = await fetch('/api/subscribe', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          email: email.trim(),
          ...(name.trim() ? { name: name.trim() } : {}),
          surface,
        }),
      })

      const data = (await res.json()) as SubscribeResponse

      if (data.success) {
        setStatus('success')
        setMessage(data.message)
        setManageToken(data.token ?? null)
      } else {
        setStatus('error')
        setMessage(data.message)
      }
    } catch {
      setStatus('error')
      setMessage('Something went wrong. Please try again.')
    }
  }

  if (status === 'success') {
    return (
      <div className={compact ? 'py-2' : 'py-4'}>
        <p role="status" aria-live="polite" className={`font-medium text-green-700 ${compact ? 'text-sm' : 'text-base'}`}>
          {message}
        </p>
        {manageToken && (
          <a
            href={`/subscribe/manage?token=${encodeURIComponent(manageToken)}`}
            className="mt-2 inline-flex min-h-11 items-center text-sm font-medium text-civic-navy-light underline hover:text-civic-navy"
          >
            Choose the updates you want
          </a>
        )}
      </div>
    )
  }

  return (
    <form
      onSubmit={handleSubmit}
      aria-busy={status === 'submitting'}
      className={compact ? 'space-y-2' : 'space-y-3'}
    >
      {!compact && (
        <div>
          <label htmlFor={nameId} className="block text-sm font-medium text-civic-slate mb-1">
            Name <span className="text-slate-400 font-normal">(optional)</span>
          </label>
          <input
            id={nameId}
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="First name"
            maxLength={200}
            className="w-full min-h-11 px-3 py-2 border border-slate-300 rounded-md text-base focus:outline-none focus:ring-2 focus:ring-civic-navy/30 focus:border-civic-navy"
          />
        </div>
      )}

      <div className={compact ? 'flex gap-2' : ''}>
        <div className={compact ? 'flex-1' : ''}>
          <label htmlFor={emailId} className={compact ? 'sr-only' : 'block text-sm font-medium text-civic-slate mb-1'}>
            Email address
          </label>
          <input
            id={emailId}
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            maxLength={255}
            className="w-full min-h-11 px-3 py-2 border border-slate-300 rounded-md text-base focus:outline-none focus:ring-2 focus:ring-civic-navy/30 focus:border-civic-navy"
          />
        </div>
        {compact && (
          <button
            type="submit"
            disabled={status === 'submitting'}
            className="min-h-11 px-4 py-2 bg-civic-navy text-white text-sm font-medium rounded-md hover:bg-civic-navy-light transition-colors disabled:opacity-50 cursor-pointer disabled:cursor-wait whitespace-nowrap"
          >
            {status === 'submitting' ? 'Signing up...' : 'Stay informed'}
          </button>
        )}
      </div>

      {!compact && (
        <button
          type="submit"
          disabled={status === 'submitting'}
          className="w-full min-h-11 px-4 py-2.5 bg-civic-navy text-white font-medium rounded-md hover:bg-civic-navy-light transition-colors disabled:opacity-50 cursor-pointer disabled:cursor-wait"
        >
          {status === 'submitting' ? 'Signing up...' : 'Subscribe'}
        </button>
      )}

      {status === 'error' && (
        <p role="alert" className="text-sm text-red-600">{message}</p>
      )}

      <p className="text-xs text-slate-400">
        No spam. Unsubscribe anytime.
      </p>
    </form>
  )
}
