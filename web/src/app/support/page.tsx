import type { Metadata } from 'next'
import Link from 'next/link'

export const metadata: Metadata = {
  title: 'Support Richmond Commons',
  description: 'Help keep Richmond’s public records, election explanations, and source-linked civic information free to everyone.',
}

export default function SupportPage() {
  return <article className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
    <h1 className="text-3xl font-bold text-civic-navy">Keep Richmond&apos;s public record public.</h1>
    <p className="mt-6 text-lg leading-relaxed text-slate-700">Richmond Commons turns council records and campaign filings into something residents can use: what changed, where the money was reported, and where to read the original evidence.</p>
    <p className="mt-4 leading-relaxed text-slate-700">Voluntary support helps with hosting, document processing, and maintenance. The public records, civic explanations, and source links stay free. Support does not buy favorable coverage or influence over which findings appear.</p>
    <a href="https://ko-fi.com/richmondcommon" className="mt-6 inline-flex min-h-11 items-center rounded-md bg-civic-navy px-5 py-3 font-medium text-white">Support Richmond Commons on Ko-fi</a>
    <p className="mt-3 text-sm text-slate-600">Ko-fi is the project&apos;s existing support service. Payment terms and any fees are shown there. Richmond Commons does not represent contributions as tax-deductible.</p>
    <section className="mt-10 border-t border-slate-200 pt-7">
      <h2 className="text-xl font-semibold text-civic-navy">Useful to a newsroom or civic organization?</h2>
      <p className="mt-4 leading-relaxed text-slate-700">Use the source-linked money ledger and its CSV exports in your own research. Cite the original filing alongside Richmond Commons. These tools are available now without a subscription.</p>
      <Link href="/elections/2026-general/money" className="mt-3 inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">Open the campaign money ledger →</Link>
    </section>
    <section className="mt-8">
      <h2 className="text-xl font-semibold text-civic-navy">Help without spending money</h2>
      <p className="mt-4 leading-relaxed text-slate-700">Point out a missing source or incorrect explanation using “Suggest a correction.” Share a source-linked page with someone who needs the context. Useful, accurate information is the reason this project exists.</p>
    </section>
  </article>
}
