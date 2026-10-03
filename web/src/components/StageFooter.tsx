'use client'

import { useState } from 'react'

export default function StageFooter() {
  const [copyStatus, setCopyStatus] = useState('')

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(window.location.href)
      setCopyStatus('Link copied. Access to this preview is still private.')
    } catch {
      setCopyStatus('Copy the link from your browser’s address bar.')
    }
  }

  return (
    <footer className="mt-auto border-t border-slate-200 bg-white">
      <div className="mx-auto max-w-6xl px-4 py-6 sm:px-6 lg:px-8">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="max-w-2xl">
            <p className="font-semibold text-civic-navy">Richmond Commons · Private preview</p>
            <p className="mt-2 leading-relaxed text-slate-600">Sources and retrieval dates appear with each record. Missing results do not establish that no decision, vote, or contribution occurred.</p>
          </div>
          <button type="button" onClick={copyLink} className="min-h-11 rounded-md border border-slate-300 px-4 font-medium text-civic-navy hover:bg-slate-50">Copy page link</button>
        </div>
        <p role="status" className="mt-2 text-sm text-slate-600">{copyStatus}</p>
      </div>
    </footer>
  )
}
