import type { Metadata } from 'next'
import SubscribeForm from '@/components/SubscribeForm'

export const metadata: Metadata = {
  title: 'Stay Informed — Richmond Commons',
  description:
    'Get a weekly briefing on what your Richmond City Council is doing — before and after each meeting. Free, plain-language updates from public records.',
}

export default function SubscribePage() {
  return (
    <div className="max-w-lg mx-auto px-4 sm:px-6 py-12">
      <header className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-civic-navy">Stay informed</h1>
        <p className="text-base text-slate-600 mt-3 leading-relaxed">
          Get a weekly briefing on what your City Council is doing — before and
          after each meeting. Plain language, sourced from public records.
        </p>
      </header>

      <div className="bg-white border border-slate-200 rounded-lg p-6 shadow-sm">
        <SubscribeForm />
      </div>

      <div className="mt-8 space-y-4 text-sm text-slate-500">
        <div className="flex gap-3">
          <span className="text-civic-amber text-lg leading-none">&#9670;</span>
          <p>
            <strong className="text-civic-slate">Before the meeting:</strong>{' '}
            a plain-language preview of what&apos;s on the agenda and why it matters.
          </p>
        </div>
        <div className="flex gap-3">
          <span className="text-civic-amber text-lg leading-none">&#9670;</span>
          <p>
            <strong className="text-civic-slate">After the meeting:</strong>{' '}
            what happened — who voted, what passed, and what the public said.
          </p>
        </div>
      </div>

      <footer className="mt-10 pt-6 border-t border-slate-200 text-center">
        <p className="text-xs text-slate-400">
          All data sourced from official public records. Richmond Commons is a
          free civic transparency project — not affiliated with the City of
          Richmond.
        </p>
      </footer>
    </div>
  )
}
