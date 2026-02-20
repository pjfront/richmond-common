'use client'

import {
  createContext,
  useContext,
  useState,
  useCallback,
  useEffect,
  type ReactNode,
} from 'react'
import { useFeedback } from '@/lib/useFeedback'
import type { FeedbackType } from '@/lib/types'

// ─── Context ────────────────────────────────────────────────

interface FeedbackModalContextValue {
  openModal: () => void
}

const FeedbackModalContext = createContext<FeedbackModalContextValue>({
  openModal: () => {},
})

export function useFeedbackModal() {
  return useContext(FeedbackModalContext)
}

// ─── Provider ───────────────────────────────────────────────

export function FeedbackModalProvider({ children }: { children: ReactNode }) {
  const [isOpen, setIsOpen] = useState(false)
  const openModal = useCallback(() => setIsOpen(true), [])
  const closeModal = useCallback(() => setIsOpen(false), [])

  return (
    <FeedbackModalContext.Provider value={{ openModal }}>
      {children}
      {isOpen && <FeedbackModalContent onClose={closeModal} />}
    </FeedbackModalContext.Provider>
  )
}

// ─── Modal Content ──────────────────────────────────────────

const TYPE_OPTIONS: { value: FeedbackType; label: string }[] = [
  { value: 'general', label: 'General feedback about the site' },
  { value: 'data_correction', label: 'I spotted an error in the data' },
  { value: 'missing_conflict', label: 'I know about a conflict not shown' },
  { value: 'tip', label: 'I have a tip or lead' },
]

function FeedbackModalContent({ onClose }: { onClose: () => void }) {
  const { loading, success, referenceId, error, submit, reset } = useFeedback()
  const [feedbackType, setFeedbackType] = useState<FeedbackType>('general')
  const [description, setDescription] = useState('')
  const [email, setEmail] = useState('')
  const [officialName, setOfficialName] = useState('')
  const [conflictNature, setConflictNature] = useState('')

  // Close on Escape key
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') onClose()
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [onClose])

  function handleClose() {
    reset()
    onClose()
  }

  if (success) {
    return (
      <ModalOverlay onClose={handleClose}>
        <div className="text-center py-6">
          <div className="text-3xl mb-3 text-vote-aye">&#10003;</div>
          <h3 className="text-lg font-semibold text-civic-navy">Thank you!</h3>
          <p className="text-sm text-slate-600 mt-2">
            Your feedback has been received.
          </p>
          <p className="text-xs text-slate-400 mt-1">
            Reference: {referenceId}
          </p>
          <p className="text-xs text-slate-500 mt-3">
            We review all submissions. Verified corrections are applied within 7 days.
          </p>
          <button
            onClick={handleClose}
            className="mt-4 px-4 py-2 bg-civic-navy text-white text-sm rounded hover:bg-civic-navy-light transition-colors"
          >
            Close
          </button>
        </div>
      </ModalOverlay>
    )
  }

  async function handleSubmit() {
    await submit({
      feedback_type: feedbackType,
      description,
      submitter_email: email || undefined,
      official_name: feedbackType === 'missing_conflict' ? officialName || undefined : undefined,
      conflict_nature: feedbackType === 'missing_conflict' ? conflictNature || undefined : undefined,
    })
  }

  return (
    <ModalOverlay onClose={handleClose}>
      <h2 className="text-lg font-semibold text-civic-navy mb-4">Submit Feedback</h2>

      <label className="block text-sm text-slate-600 mb-1">What kind of feedback?</label>
      <div className="space-y-2 mb-4">
        {TYPE_OPTIONS.map((opt) => (
          <label key={opt.value} className="flex items-center gap-2 text-sm cursor-pointer">
            <input
              type="radio"
              name="feedbackType"
              value={opt.value}
              checked={feedbackType === opt.value}
              onChange={() => setFeedbackType(opt.value)}
              className="accent-civic-navy"
            />
            {opt.label}
          </label>
        ))}
      </div>

      {feedbackType === 'missing_conflict' && (
        <>
          <label className="block text-sm text-slate-600 mb-1">Official involved</label>
          <input
            type="text"
            value={officialName}
            onChange={(e) => setOfficialName(e.target.value)}
            placeholder="Council member or official name"
            className="w-full border border-slate-200 rounded p-2 text-sm mb-3 focus:outline-none focus:ring-1 focus:ring-civic-navy-light"
          />
          <label className="block text-sm text-slate-600 mb-1">Nature of conflict</label>
          <select
            value={conflictNature}
            onChange={(e) => setConflictNature(e.target.value)}
            className="w-full border border-slate-200 rounded p-2 text-sm mb-3 focus:outline-none focus:ring-1 focus:ring-civic-navy-light"
          >
            <option value="">Select...</option>
            <option value="contribution">Campaign contribution</option>
            <option value="property">Property interest</option>
            <option value="business">Business relationship</option>
            <option value="family">Family tie</option>
            <option value="other">Other</option>
          </select>
        </>
      )}

      <label className="block text-sm text-slate-600 mb-1">Tell us more</label>
      <textarea
        value={description}
        onChange={(e) => setDescription(e.target.value)}
        placeholder="Provide details (minimum 10 characters)"
        className="w-full border border-slate-200 rounded p-2 text-sm h-28 resize-none mb-3 focus:outline-none focus:ring-1 focus:ring-civic-navy-light"
        maxLength={5000}
      />

      <label className="block text-sm text-slate-600 mb-1">
        Email (optional, for follow-up)
      </label>
      <input
        type="email"
        value={email}
        onChange={(e) => setEmail(e.target.value)}
        placeholder="your@email.com"
        className="w-full border border-slate-200 rounded p-2 text-sm mb-3 focus:outline-none focus:ring-1 focus:ring-civic-navy-light"
      />

      <p className="text-xs text-slate-400 mb-4">
        Submissions are anonymous by default. Your email is never shared.
      </p>

      {error && <p className="text-sm text-vote-nay mb-3">{error}</p>}

      <div className="flex justify-end gap-2">
        <button
          onClick={handleClose}
          className="px-4 py-2 text-sm text-slate-500 hover:text-slate-700 transition-colors"
        >
          Cancel
        </button>
        <button
          onClick={handleSubmit}
          disabled={loading || description.length < 10}
          className="px-4 py-2 bg-civic-navy text-white text-sm rounded hover:bg-civic-navy-light disabled:opacity-50 transition-colors"
        >
          {loading ? 'Submitting...' : 'Submit'}
        </button>
      </div>
    </ModalOverlay>
  )
}

// ─── Overlay ────────────────────────────────────────────────

function ModalOverlay({ onClose, children }: { onClose: () => void; children: ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div
        className="absolute inset-0 bg-black/40"
        onClick={onClose}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        className="relative bg-white rounded-lg shadow-xl max-w-md w-full mx-4 p-6 max-h-[90vh] overflow-y-auto"
      >
        {children}
      </div>
    </div>
  )
}
