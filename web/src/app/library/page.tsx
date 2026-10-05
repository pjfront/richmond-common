import Link from 'next/link'
import { notFound } from 'next/navigation'
import { featureCatalog, featureEnabled, isLocalArchive } from '@/lib/feature-policy'
import type { Feature } from '@/lib/feature-policy'

export const dynamic = 'force-dynamic'

export default function LocalLibrary() {
  if (!isLocalArchive()) notFound()
  const tools = Object.entries(featureCatalog).flatMap(([id, feature]) => {
    if (!featureEnabled(id as Feature)) return []
    const routes = [...feature.routes, ...('localRoutes' in feature ? feature.localRoutes : [])]
    const href = id === 'operator_tools' ? '/operator/decisions'
      : id === 'stored_ai_content' ? '/operator/recaps'
        : routes.find(path => !path.startsWith('/api/') && !path.includes('*'))
    return href ? [{ id, feature, href }] : []
  })
  return <div className="mx-auto max-w-6xl px-4 py-10 sm:px-6">
    <h1 className="text-3xl font-bold text-civic-navy">Your local records and tools</h1>
    <p className="mt-4 max-w-3xl leading-relaxed text-slate-700">This edition reads the records backed up on October 4, 2026. Search, browsing, saved explanations, and existing analysis use your local database. Refreshing the archive is a separate action; this page does not claim the sources have been checked since that backup.</p>
    <p className="mt-3 max-w-3xl leading-relaxed text-slate-700">Paid AI, vector search, email, and data changes are disabled. Operator tools keep their password requirement. Original documents remain in the local backup.</p>
    <ul className="mt-8 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {tools.map(({ id, feature, href }) => <li key={id} className="rounded-lg border border-slate-200 bg-white p-5">
        <Link className="inline-flex min-h-11 items-center text-lg font-semibold text-civic-navy underline" href={href}>{feature.label}</Link>
        <p className="mt-2 leading-relaxed text-slate-600">{feature.description}</p>
      </li>)}
    </ul>
    <p className="mt-8 text-slate-700">Features that need new extraction or a local model can be enabled after their dependencies are installed and checked. Changing the browsing tier never deletes stored records.</p>
  </div>
}
