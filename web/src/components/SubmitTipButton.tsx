'use client'

import { useFeedbackModal } from './FeedbackModal'

export default function SubmitTipButton() {
  const { openModal } = useFeedbackModal()
  return (
    <button
      onClick={openModal}
      className="hover:text-white transition-colors"
    >
      Submit a Tip
    </button>
  )
}
