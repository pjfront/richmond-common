'use client'

import { useEffect, useState } from 'react'
import type { EconomicInterest, Form700Filing } from '@/lib/types'
import EconomicInterestsSection from './EconomicInterestsSection'

interface OperatorCouncilContext {
  interests: EconomicInterest[]
  filings: Form700Filing[]
}

export default function OperatorCouncilSections({
  officialId,
  officialName,
}: {
  officialId: string
  officialName: string
}) {
  const [context, setContext] = useState<OperatorCouncilContext | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    const controller = new AbortController()
    fetch(`/api/operator/council-context?official_id=${encodeURIComponent(officialId)}`, {
      credentials: 'same-origin',
      cache: 'no-store',
      signal: controller.signal,
    })
      .then((response) => {
        if (!response.ok) throw new Error('Operator council context request failed')
        return response.json() as Promise<OperatorCouncilContext>
      })
      .then(setContext)
      .catch((requestError: unknown) => {
        if (requestError instanceof DOMException && requestError.name === 'AbortError') return
        setError(true)
      })

    return () => controller.abort()
  }, [officialId])

  if (error) {
    return <p role="alert" className="text-sm text-red-700 mb-6">Financial disclosures could not be loaded.</p>
  }
  if (!context) {
    return <p aria-live="polite" className="text-sm text-slate-500 mb-6">Loading financial disclosures…</p>
  }

  return (
    <EconomicInterestsSection
      filings={context.filings}
      interests={context.interests}
      officialName={officialName}
    />
  )
}
