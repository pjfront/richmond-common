'use client'

import { useFeedbackModal } from './FeedbackModal'

export default function SubmitTipButton() {
  const { openModal } = useFeedbackModal()
  return (
    <button
      onClick={openModal}
      type="button"
      className="min-h-11 rounded-sm hover:text-white transition-colors cursor-pointer"
    >
      Submit Feedback
    </button>
  )
}
