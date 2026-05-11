'use client'

import { Suspense, useState, type FormEvent } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'

function OperatorLoginForm() {
  const router = useRouter()
  const params = useSearchParams()
  const next = params.get('next') || '/operator/settings'
  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: FormEvent) {
    e.preventDefault()
    setError(null)
    setSubmitting(true)
    try {
      const res = await fetch('/api/operator/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password }),
      })
      if (!res.ok) {
        const body = await res.json().catch(() => ({}))
        setError(body.error || 'Login failed')
        return
      }
      router.push(next)
      router.refresh()
    } catch {
      setError('Network error')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <main className="mx-auto max-w-sm px-4 py-16">
      <h1 className="text-2xl font-semibold text-civic-navy">Operator sign-in</h1>
      <p className="mt-2 text-sm text-civic-slate">
        Restricted to the project operator. Public visitors do not need this.
      </p>
      <form onSubmit={handleSubmit} className="mt-6 space-y-4">
        <label className="block">
          <span className="block text-sm font-medium text-civic-slate">
            Password
          </span>
          <input
            type="password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            autoComplete="current-password"
            required
            className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-civic-navy focus:outline-none focus:ring-1 focus:ring-civic-navy"
          />
        </label>
        {error && (
          <p className="text-sm text-vote-nay" role="alert">
            {error}
          </p>
        )}
        <button
          type="submit"
          disabled={submitting || !password}
          className="w-full rounded-md bg-civic-navy px-4 py-2 text-sm font-medium text-white hover:bg-civic-navy-light disabled:opacity-50"
        >
          {submitting ? 'Signing in…' : 'Sign in'}
        </button>
      </form>
    </main>
  )
}

export default function OperatorLoginPage() {
  return (
    <Suspense>
      <OperatorLoginForm />
    </Suspense>
  )
}
