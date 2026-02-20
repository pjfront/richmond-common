'use client'

import { useState } from 'react'
import { useFeedback } from '@/lib/useFeedback'
import type { FlagVerdict } from '@/lib/types'

interface Props {
  flagId: string
  entityType?: string
}

export default function FeedbackButton({ flagId, entityType = 'conflict_flag' }: Props) {
  const { loading, success, referenceId, error, submit, reset } = useFeedback()
  const [activeVerdict, setActiveVerdict] = useState<FlagVerdict | null>(null)
  const [description, setDescription] = useState('')

  if (success) {
    return (
      <div className="flex items-center gap-2 mt-3 pt-2 border-t border-slate-100">
        <span className="text-xs text-vote-aye">
          Thank you! Reference: {referenceId}
        </span>
      </div>
    )
  }

  async function handleConfirm() {
    await submit({
      feedback_type: 'flag_accuracy',
      entity_type: entityType,
      entity_id: flagId,
      flag_verdict: 'confirm',
    })
  }

  async function handleSubmitWithText() {
    if (!activeVerdict || description.length < 10) return
    await submit({
      feedback_type: 'flag_accuracy',
      entity_type: entityType,
      entity_id: flagId,
      flag_verdict: activeVerdict,
      description,
    })
  }

  return (
    <div className="mt-3 pt-2 border-t border-slate-100">
      {!activeVerdict && (
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-xs text-slate-400 mr-1">Is this accurate?</span>
          <button
            onClick={handleConfirm}
            disabled={loading}
            className="text-xs px-2 py-1 rounded border border-vote-aye/30 text-vote-aye hover:bg-vote-aye/10 transition-colors disabled:opacity-50"
          >
            &#10003; Correct
          </button>
          <button
            onClick={() => setActiveVerdict('dispute')}
            className="text-xs px-2 py-1 rounded border border-vote-nay/30 text-vote-nay hover:bg-vote-nay/10 transition-colors"
          >
            &#10007; Incorrect
          </button>
          <button
            onClick={() => setActiveVerdict('add_context')}
            className="text-xs px-2 py-1 rounded border border-civic-amber/30 text-civic-amber hover:bg-civic-amber/10 transition-colors"
          >
            &#128161; I know more
          </button>
        </div>
      )}

      {activeVerdict && (
        <div className="mt-2">
          <textarea
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            placeholder={
              activeVerdict === 'dispute'
                ? 'Why is this incorrect? (min 10 characters)'
                : 'What additional context can you provide? (min 10 characters)'
            }
            className="w-full text-xs border border-slate-200 rounded p-2 h-20 resize-none focus:outline-none focus:ring-1 focus:ring-civic-navy-light"
            maxLength={5000}
          />
          <div className="flex items-center gap-2 mt-1">
            <button
              onClick={handleSubmitWithText}
              disabled={loading || description.length < 10}
              className="text-xs px-3 py-1 rounded bg-civic-navy text-white hover:bg-civic-navy-light disabled:opacity-50 transition-colors"
            >
              {loading ? 'Submitting...' : 'Submit'}
            </button>
            <button
              onClick={() => {
                setActiveVerdict(null)
                setDescription('')
                reset()
              }}
              className="text-xs text-slate-400 hover:text-slate-600"
            >
              Cancel
            </button>
            {error && <span className="text-xs text-vote-nay">{error}</span>}
          </div>
        </div>
      )}

      {error && !activeVerdict && (
        <p className="text-xs text-vote-nay mt-1">{error}</p>
      )}
    </div>
  )
}
