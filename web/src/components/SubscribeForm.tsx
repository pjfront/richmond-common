'use client'

import { useState } from 'react'
import TopicPreferences from './TopicPreferences'
import type { SubscribeResponse, SubscriptionPreferences, PreferencesResponse } from '@/lib/types'

interface SubscribeFormProps {
  /** Compact mode for inline CTAs (no name field, smaller text). */
  compact?: boolean
}

export default function SubscribeForm({ compact = false }: SubscribeFormProps) {
  const [email, setEmail] = useState('')
  const [name, setName] = useState('')
  const [status, setStatus] = useState<'idle' | 'submitting' | 'success' | 'error'>('idle')
  const [message, setMessage] = useState('')
  const [token, setToken] = useState<string | null>(null)
  const [showTopics, setShowTopics] = useState(false)
  const [selectedTopics, setSelectedTopics] = useState<string[]>([])
  const [topicStatus, setTopicStatus] = useState<'idle' | 'saving' | 'saved'>('idle')

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
        if (data.token) setToken(data.token)
      } else {
        setStatus('error')
        setMessage(data.message)
      }
    } catch {
      setStatus('error')
      setMessage('Something went wrong. Please try again.')
    }
  }

  async function handleSaveTopics() {
    if (!token) return
    setTopicStatus('saving')

    try {
      const res = await fetch('/api/subscribe/preferences', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token,
          preferences: {
            topics: selectedTopics,
            districts: [],
            candidates: [],
          } satisfies SubscriptionPreferences,
        }),
      })

      const data = (await res.json()) as PreferencesResponse
      if (data.success) setTopicStatus('saved')
    } catch {
      // Non-critical — preferences can be set later via manage page
      setTopicStatus('saved')
    }
  }

  // ─── Success state ──────────────────────────────────────

  if (status === 'success') {
    // Compact: text only
    if (compact) {
      return (
        <div className="py-2">
          <p className="text-sm font-medium text-green-700">
            Subscribed! Check your email to customize your topics.
          </p>
        </div>
      )
    }

    // Full: saved topics confirmation
    if (topicStatus === 'saved') {
      return (
        <div className="py-4 text-center">
          <p className="font-medium text-green-700">You&apos;re all set!</p>
          <p className="text-sm text-slate-500 mt-1">
            Change your preferences anytime via the link in your email.
          </p>
        </div>
      )
    }

    // Full: topic picker
    if (showTopics && token) {
      return (
        <div className="space-y-4">
          <div>
            <p className="font-medium text-green-700">{message}</p>
            <p className="text-sm text-slate-500 mt-1">
              What Richmond topics do you want to hear about?
            </p>
          </div>

          <div className="border border-slate-200 rounded-lg p-4 bg-white max-h-80 overflow-y-auto">
            <TopicPreferences
              selectedTopics={selectedTopics}
              onChange={setSelectedTopics}
            />
          </div>

          <div className="flex gap-3">
            <button
              type="button"
              onClick={handleSaveTopics}
              disabled={topicStatus === 'saving' || selectedTopics.length === 0}
              className="px-4 py-2 bg-civic-navy text-white text-sm font-medium rounded-md hover:bg-civic-navy-light transition-colors disabled:opacity-50"
            >
              {topicStatus === 'saving' ? 'Saving...' : `Save ${selectedTopics.length > 0 ? `(${selectedTopics.length})` : ''}`}
            </button>
            <button
              type="button"
              onClick={() => setTopicStatus('saved')}
              className="px-4 py-2 text-sm text-slate-500 hover:text-slate-700 transition-colors"
            >
              Skip for now
            </button>
          </div>
        </div>
      )
    }

    // Full: success with customize option
    return (
      <div className="py-4">
        <p className="font-medium text-green-700">{message}</p>
        {token && (
          <button
            type="button"
            onClick={() => setShowTopics(true)}
            className="mt-3 text-sm text-civic-navy-light hover:text-civic-navy font-medium underline underline-offset-2"
          >
            Customize your topics →
          </button>
        )}
        {!token && (
          <p className="text-sm text-slate-500 mt-1">
            Check your email for a link to manage your preferences.
          </p>
        )}
      </div>
    )
  }

  // ─── Form ───────────────────────────────────────────────

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
