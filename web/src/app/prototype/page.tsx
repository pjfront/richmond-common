import Link from 'next/link'

export const metadata = { title: 'Prototypes' }

export default function PrototypeIndex() {
  return (
    <div className="max-w-[640px] mx-auto px-5 py-16" style={{ fontFamily: 'Georgia, "Times New Roman", serif' }}>
      <h1 className="text-3xl font-bold text-neutral-900 mb-2">Design Prototypes</h1>
      <p className="text-neutral-500 text-lg mb-12">
        Radically different approaches to presenting civic information.
      </p>

      <div className="space-y-8">
        <Link href="/prototype/record" className="block group">
          <h2 className="text-xl font-semibold text-neutral-900 group-hover:text-neutral-600 transition-colors">
            The Record
          </h2>
          <p className="text-neutral-500 mt-1">
            Editorial voice meets minimal feed. One story told well, then a compact timeline of civic events. Serif type, generous space, no badges.
          </p>
        </Link>

        <div className="border-t border-neutral-100" />

        <div className="text-sm text-neutral-400">
          <p>Each prototype reimagines the homepage, a meeting page, and a council member page.</p>
          <p className="mt-1">All use real data. Nothing is mocked.</p>
        </div>
      </div>
    </div>
  )
}
