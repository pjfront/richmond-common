'use client'

import { useState } from 'react'
import type { SubscribeResponse } from '@/lib/types'

interface SubscribeFormProps {
  /** Compact mode for inline CTAs (no name field, smaller text). */
  compact?: boolean
}

export default function SubscribeForm({ compact = false }: SubscribeFormProps) {
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')

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
        }),
      })

      const data = (await res.json()) as SubscribeResponse

      if (data.success) {
        setStatus('success')
        setMessage(data.message)
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
        <p className={`font-medium text-green-700 ${compact ? 'text-sm' : 'text-base'}`}>
          {message}
        </p>
      </div>
    )
  }

  return (
    <form onSubmit={handleSubmit} className={compact ? 'space-y-2' : 'space-y-3'}>
      {!compact && (
        <div>
          <label htmlFor="subscribe-name" className="block text-sm font-medium text-civic-slate mb-1">
            Name <span className="text-slate-400 font-normal">(optional)</span>
          </label>
          <input
            id="subscribe-name"
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="First name"
            maxLength={200}
            className="w-full px-3 py-2 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-civic-navy/30 focus:border-civic-navy"
          />
        </div>
      )}

      <div className={compact ? 'flex gap-2' : ''}>
        <div className={compact ? 'flex-1' : ''}>
          {!compact && (
            <label htmlFor="subscribe-email" className="block text-sm font-medium text-civic-slate mb-1">
              Email
            </label>
          )}
          <input
            id={compact ? 'subscribe-email-compact' : 'subscribe-email'}
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            maxLength={255}
            className={`w-full px-3 border border-slate-300 rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-civic-navy/30 focus:border-civic-navy ${compact ? 'py-1.5' : 'py-2'}`}
          />
        </div>
        {compact && (
          <button
            type="submit"
            disabled={status === 'submitting'}
            className="px-4 py-1.5 bg-civic-navy text-white text-sm font-medium rounded-md hover:bg-civic-navy-light transition-colors disabled:opacity-50 whitespace-nowrap"
          >
            {status === 'submitting' ? 'Signing up...' : 'Stay informed'}
          </button>
        )}
      </div>

      {!compact && (
        <button
          type="submit"
          disabled={status === 'submitting'}
          className="w-full px-4 py-2.5 bg-civic-navy text-white font-medium rounded-md hover:bg-civic-navy-light transition-colors disabled:opacity-50"
        >
          {status === 'submitting' ? 'Signing up...' : 'Subscribe'}
        </button>
      )}

      {status === 'error' && (
        <p className="text-sm text-red-600">{message}</p>
      )}

      <p className="text-xs text-slate-400">
        No spam. Unsubscribe anytime.
      </p>
    </form>
  )
}
