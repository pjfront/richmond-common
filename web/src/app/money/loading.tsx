export default function MoneyLoading() {
  return (
    <div className="mx-auto max-w-5xl px-4 py-10 sm:px-6 lg:px-8" aria-busy="true" aria-live="polite">
      <p className="mb-6 text-lg text-slate-700">Loading campaign records…</p>
      <div aria-hidden="true" className="h-40 rounded-xl border border-slate-200 bg-white" />
      <div aria-hidden="true" className="mt-8 h-48 rounded-xl border border-slate-200 bg-white" />
    </div>
  )
}
