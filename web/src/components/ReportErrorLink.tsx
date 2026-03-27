'use client'

import { useState } from 'react'
import { useFeedback } from '@/lib/useFeedback'

interface Props {
  entityId: string
  entityType: string
  currentContext?: string
}

export default function ReportErrorLink({ entityId, entityType, currentContext }: Props) {
  const { loading, success, referenceId, error, submit } = useFeedback()
  const [expanded, setExpanded] = useState(false)
  const [fieldName, setFieldName] = useState('')
  const [suggestedValue, setSuggestedValue] = useState('')
  const [evidenceText, setEvidenceText] = useState('')

  if (success) {
    return (
      <span className="text-xs text-vote-aye">
        Reported! Ref: {referenceId}
      </span>
    )
  }

  if (!expanded) {
    return (
      <button
        onClick={() => setExpanded(true)}
        className="text-xs text-slate-400 hover:text-civic-navy-light transition-colors cursor-pointer"
      >
        Report an error
      </button>
    )
  }

  async function handleSubmit() {
    if (!fieldName || !suggestedValue) return
    await submit({
      feedback_type: 'data_correction',
      entity_type: entityType,
      entity_id: entityId,
      field_name: fieldName,
      current_value: currentContext ?? '',
      suggested_value: suggestedValue,
      evidence_text: evidenceText || undefined,
    })
  }

  return (
    <div className="mt-2 p-3 bg-slate-50 rounded border border-slate-200 text-xs">
      <p className="font-medium text-slate-700 mb-2">Report an error</p>

      <label className="block mb-1 text-slate-500">What is wrong?</label>
      <select
        value={fieldName}
        onChange={(e) => setFieldName(e.target.value)}
        className="w-full border border-slate-200 rounded p-1 mb-2 text-xs focus:outline-none focus:ring-1 focus:ring-civic-navy-light"
      >
        <option value="">Select...</option>
        <option value="vote_choice">Vote recorded incorrectly</option>
        <option value="official_name">Official name is wrong</option>
        <option value="motion_text">Motion text is incorrect</option>
        <option value="vote_tally">Vote tally is wrong</option>
        <option value="other">Other</option>
      </select>

      <label className="block mb-1 text-slate-500">What should it be?</label>
      <input
        type="text"
        value={suggestedValue}
        onChange={(e) => setSuggestedValue(e.target.value)}
        placeholder="Correct value"
        className="w-full border border-slate-200 rounded p-1 mb-2 text-xs focus:outline-none focus:ring-1 focus:ring-civic-navy-light"
      />

      <label className="block mb-1 text-slate-500">How do you know? (optional)</label>
      <input
        type="text"
        value={evidenceText}
        onChange={(e) => setEvidenceText(e.target.value)}
        placeholder='e.g., "I was at the meeting" or "minutes page 12"'
        className="w-full border border-slate-200 rounded p-1 mb-2 text-xs focus:outline-none focus:ring-1 focus:ring-civic-navy-light"
      />

      <div className="flex gap-2">
        <button
          onClick={handleSubmit}
          disabled={loading || !fieldName || !suggestedValue}
          className="text-xs px-3 py-1 rounded bg-civic-navy text-white hover:bg-civic-navy-light disabled:opacity-50 transition-colors"
        >
          {loading ? 'Submitting...' : 'Submit'}
        </button>
        <button
          onClick={() => setExpanded(false)}
          className="text-xs text-slate-400 hover:text-slate-600"
        >
          Cancel
        </button>
      </div>
      {error && <p className="text-xs text-vote-nay mt-1">{error}</p>}
    </div>
  )
}
