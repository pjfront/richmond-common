'use client'

import { useFeedbackModal } from './FeedbackModal'

export default function SubmitTipButton() {
  const { openModal } = useFeedbackModal()
  return (
    <button
      onClick={openModal}
      className="inline-flex min-h-11 items-center text-left transition-colors hover:text-white cursor-pointer"
    >
      Submit Feedback
    </button>
  )
}
