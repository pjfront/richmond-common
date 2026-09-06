'use client'

import { useFeedbackModal } from './FeedbackModal'

export default function SuggestCorrectionLink() {
  const { openModal } = useFeedbackModal()
  return (
    <button
      onClick={openModal}
      type="button"
      className="min-h-11 rounded-sm text-sm text-slate-600 underline underline-offset-4 hover:text-civic-navy transition-colors"
    >
      See something wrong? Suggest a correction
    </button>
  )
}
