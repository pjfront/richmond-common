import type { Metadata } from 'next'
import Link from 'next/link'
import { getPublishedCivicBriefVersion } from '@/lib/queries/civic-briefs'
import { SUBSCRIPTION_SUBJECTS } from '@/lib/subscription-subjects'
import { formatCivicDate } from '@/lib/november-election'
import FollowSubject from '@/components/FollowSubject'

// These links identify a publication from an email, including one no longer in
// the short story feed. Check current publication status on every request.
export const dynamic = 'force-dynamic'
export const metadata: Metadata = { title: 'Reviewed update', robots: { index: false } }

export default async function PublishedUpdatePage({ params, searchParams }: {
  params: Promise<{ id: string }>
  searchParams: Promise<{ version?: string | string[]; published?: string | string[] }>
}) {
  const [{ id }, { version, published }] = await Promise.all([params, searchParams])
  let brief
  try { brief = await getPublishedCivicBriefVersion(id, version, published) } catch {
    return <UpdateUnavailable temporary />
  }
  const subject = SUBSCRIPTION_SUBJECTS.find(row => row.id === brief?.subject_key)
  if (!brief || !subject) return <UpdateUnavailable />
  return <div className="mx-auto max-w-3xl px-4 py-8 sm:px-6 sm:py-12">
    <Link href={subject.href} className="inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">Back to {subject.label}</Link>
    <article id={`brief-${brief.id}-v${brief.content_version}`} className="mt-6">
      <h1 className="text-3xl font-semibold leading-tight text-civic-navy sm:text-4xl">{brief.title}</h1>
      <p className="mt-4 text-sm text-slate-600">AI-written, operator-reviewed · published {formatCivicDate(brief.published_at)} · version {brief.content_version}</p>
      <p className="mt-6 whitespace-pre-line text-lg leading-8 text-slate-700">{brief.body}</p>
      <h2 className="mt-8 text-xl font-semibold text-civic-navy">Sources for this update</h2>
      <ul className="mt-3 space-y-2">{brief.sources.map((source, index) => <li key={`${source.url}-${index}`} className="text-sm text-slate-600">
        <a href={source.url} className="inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">{source.title}</a> · {source.source_tier === 1 ? 'Official record' : 'Independent journalism'}{source.source_date ? ` · ${formatCivicDate(source.source_date)}` : ' · source date not supplied'}
      </li>)}</ul>
    </article>
    <div className="mt-10"><FollowSubject subject={subject.id} /></div>
  </div>
}

function UpdateUnavailable({ temporary = false }: { temporary?: boolean }) {
  return <div className="mx-auto max-w-3xl px-4 py-12 sm:px-6">
    <h1 className="text-3xl font-semibold text-civic-navy">Update unavailable</h1>
    <p role="status" className="mt-4 leading-7 text-slate-700">{temporary
      ? 'This update could not be loaded. Please try again shortly.'
      : 'This exact publication is no longer available. It may have been withdrawn or replaced, or the link may be incomplete. The original sources remain linked in your email.'}</p>
    <Link href="/stories" className="mt-4 inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">Browse the current stories</Link>
    <Link href="/elections/2026-general" className="mt-4 ml-6 inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">See the November choices</Link>
  </div>
}
