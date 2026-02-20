'use client'

import { useState, useCallback } from 'react'
import type { FeedbackSubmission, FeedbackResponse } from './types'

interface FeedbackState {
  loading: boolean
  success: boolean
  referenceId: string | null
  error: string | null
}

const INITIAL_STATE: FeedbackState = {
  loading: false,
  success: false,
  referenceId: null,
  error: null,
}

export function useFeedback() {
  const [state, setState] = useState<FeedbackState>(INITIAL_STATE)

  const submit = useCallback(async (submission: FeedbackSubmission) => {
    setState({ loading: true, success: false, referenceId: null, error: null })

    try {
      const res = await fetch('/api/feedback', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(submission),
      })

      const data: FeedbackResponse = await res.json()

      if (data.success) {
        setState({ loading: false, success: true, referenceId: data.reference_id, error: null })
      } else {
        setState({ loading: false, success: false, referenceId: null, error: data.error ?? 'Submission failed.' })
      }
    } catch {
      setState({ loading: false, success: false, referenceId: null, error: 'Network error. Please try again.' })
    }
  }, [])

  const reset = useCallback(() => {
    setState(INITIAL_STATE)
  }, [])

  return { ...state, submit, reset }
}
