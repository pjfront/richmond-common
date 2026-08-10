'use client'

import { useFeedbackModal } from './FeedbackModal'

export default function SubmitTipButton() {
  const { openModal } = useFeedbackModal()
  return (
    <button
      onClick={openModal}
      className="inline-flex min-h-11 items-center text-left hover:text-white transition-colors cursor-pointer"
    >
      Submit Feedback
    </button>
  )
}
