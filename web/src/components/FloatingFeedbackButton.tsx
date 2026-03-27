'use client'

import { useState, useEffect, useRef } from 'react'
import { useFeedback } from '@/lib/useFeedback'

export default function FloatingFeedbackButton() {
  const [isOpen, setIsOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [email, setEmail] = useState('')
  const { loading, success, referenceId, error, submit, reset } = useFeedback()
  const panelRef = useRef<HTMLDivElement>(null)

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return
    function handleKeyDown(e: KeyboardEvent) {
      if (e.key === 'Escape') setIsOpen(false)
    }
    document.addEventListener('keydown', handleKeyDown)
    return () => document.removeEventListener('keydown', handleKeyDown)
  }, [isOpen])

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return
    function handleClick(e: MouseEvent) {
      if (panelRef.current && !panelRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    // Delay to avoid closing on the click that opened it
    const timer = setTimeout(() => {
      document.addEventListener('mousedown', handleClick)
    }, 0)
    return () => {
      clearTimeout(timer)
      document.removeEventListener('mousedown', handleClick)
    }
  }, [isOpen])

  function handleOpen() {
    if (success) {
      reset()
      setMessage('')
      setEmail('')
    }
    setIsOpen(!isOpen)
  }

  function handleClose() {
    setIsOpen(false)
    if (success) {
      // Reset state after close so next open is fresh
      setTimeout(() => {
        reset()
        setMessage('')
        setEmail('')
      }, 200)
    }
  }

  async function handleSubmit() {
    await submit({
      feedback_type: 'general',
      description: message,
      submitter_email: email || undefined,
      page_url: typeof window !== 'undefined' ? window.location.pathname : undefined,
    })
  }

  return (
    <div className="fixed bottom-5 right-5 z-40" ref={panelRef}>
      {/* Expanded panel */}
      {isOpen && (
        <div className="absolute bottom-14 right-0 w-80 max-w-[calc(100vw-2.5rem)] bg-white rounded-lg shadow-xl border border-slate-200 overflow-hidden">
          {success ? (
            <div className="p-5 text-center">
              <div className="text-2xl mb-2 text-vote-aye">&#10003;</div>
              <p className="text-sm font-medium text-civic-navy">Thank you!</p>
              <p className="text-xs text-slate-500 mt-1">
                Reference: {referenceId}
              </p>
              <p className="text-xs text-slate-400 mt-2">
                We review all submissions.
              </p>
              <button
                onClick={handleClose}
                className="mt-3 px-3 py-1.5 text-xs bg-civic-navy text-white rounded hover:bg-civic-navy-light transition-colors"
              >
                Close
              </button>
            </div>
          ) : (
            <div className="p-4">
              <div className="flex items-center justify-between mb-3">
                <h3 className="text-sm font-semibold text-civic-navy">
                  Submit Feedback
                </h3>
                <button
                  onClick={handleClose}
                  className="text-slate-400 hover:text-slate-600 text-lg leading-none"
                  aria-label="Close feedback"
                >
                  &times;
                </button>
              </div>

              <textarea
                value={message}
                onChange={(e) => setMessage(e.target.value)}
                placeholder="Ideas, bugs, or anything else..."
                className="w-full border border-slate-200 rounded p-2 text-sm h-24 resize-none focus:outline-none focus:ring-1 focus:ring-civic-navy-light"
                maxLength={5000}
                autoFocus
              />

              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="Email (optional, for follow-up)"
                className="w-full border border-slate-200 rounded p-2 text-sm mt-2 focus:outline-none focus:ring-1 focus:ring-civic-navy-light"
              />

              {error && <p className="text-xs text-vote-nay mt-2">{error}</p>}

              <div className="flex items-center justify-between mt-3">
                <span className="text-xs text-slate-400">Anonymous</span>
                <button
                  onClick={handleSubmit}
                  disabled={loading || message.length < 10}
                  className="px-3 py-1.5 bg-civic-navy text-white text-xs rounded hover:bg-civic-navy-light disabled:opacity-50 transition-colors"
                >
                  {loading ? 'Sending...' : 'Send'}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Floating trigger button */}
      <button
        onClick={handleOpen}
        aria-label="Submit Feedback"
        title="Submit Feedback"
        className="w-11 h-11 rounded-full bg-civic-navy text-white shadow-lg hover:bg-civic-navy-light hover:shadow-xl transition-all flex items-center justify-center cursor-pointer"
      >
        {isOpen ? (
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
            <path d="M6.28 5.22a.75.75 0 00-1.06 1.06L8.94 10l-3.72 3.72a.75.75 0 101.06 1.06L10 11.06l3.72 3.72a.75.75 0 101.06-1.06L11.06 10l3.72-3.72a.75.75 0 00-1.06-1.06L10 8.94 6.28 5.22z" />
          </svg>
        ) : (
          <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor" className="w-5 h-5">
            <path fillRule="evenodd" d="M10 2c-2.236 0-4.43.18-6.57.524C1.993 2.755 1 4.014 1 5.426v5.148c0 1.413.993 2.67 2.43 2.902 1.168.188 2.352.327 3.55.414.28.02.521.18.642.413l1.713 3.293a.75.75 0 001.33 0l1.713-3.293a.783.783 0 01.642-.413 41.102 41.102 0 003.55-.414c1.437-.231 2.43-1.49 2.43-2.902V5.426c0-1.413-.993-2.67-2.43-2.902A41.289 41.289 0 0010 2zM6.75 6a.75.75 0 000 1.5h6.5a.75.75 0 000-1.5h-6.5zm0 2.5a.75.75 0 000 1.5h3.5a.75.75 0 000-1.5h-3.5z" clipRule="evenodd" />
          </svg>
        )}
      </button>
    </div>
  )
}
