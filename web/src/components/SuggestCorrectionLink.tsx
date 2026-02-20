'use client'

import { useFeedbackModal } from './FeedbackModal'

export default function SuggestCorrectionLink() {
  const { openModal } = useFeedbackModal()
  return (
    <button
      onClick={openModal}
      className="text-xs text-slate-400 hover:text-civic-navy-light transition-colors"
    >
      See something wrong? Suggest a correction
    </button>
  )
}
