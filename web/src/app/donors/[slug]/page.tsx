import { notFound } from 'next/navigation'
import Link from 'next/link'
import type { Metadata } from 'next'
import { getDonorBySlug, getDonorOutgoing } from '@/lib/queries'
import DonorProfileClient from './DonorProfileClient'

interface PageProps { params: Promise<{ slug: string }> }

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const donor = await getDonorBySlug((await params).slug)
  return donor ? {
    title: `${donor.display_name}: Historical campaign records`,
    description: `Dated campaign records filed under ${donor.display_name}, with reported recipients, amounts and original sources.`,
  } : { title: 'Donor not found' }
}

export default async function DonorProfilePage({ params }: PageProps) {
  const donor = await getDonorBySlug((await params).slug)
  if (!donor) notFound()
  const outgoing = await getDonorOutgoing(donor.donor_id)
  return <article className="mx-auto max-w-4xl px-4 py-8 sm:px-6 lg:px-8">
    <Link href="/donors" className="inline-flex min-h-11 items-center text-civic-navy underline">← Historical donor records</Link>
    <header className="mb-6 mt-4">
      <h1 className="text-3xl font-bold text-civic-navy">{donor.display_name}</h1>
      <p className="mt-3 leading-relaxed text-slate-700">Historical entries filed under this name. Each entry keeps its reported date, receiving committee and kind of activity.</p>
      <p className="mt-2 text-sm leading-relaxed text-slate-600">These imports can include amendments and repeated reports of the same activity. We show individual records without adding them into a lifetime total or assigning them to an election.</p>
      <Link href={`/elections/2026-general/money?q=${encodeURIComponent(donor.display_name)}`} className="mt-2 inline-flex min-h-11 items-center text-civic-navy underline">Search this name in the 2026 money records →</Link>
    </header>
    <DonorProfileClient outgoing={outgoing} donorDisplay={donor.display_name} />
    <footer className="mt-8 border-t border-slate-200 pt-4 text-sm leading-relaxed text-slate-600">
      <Link href="/elections/methodology#historical-records" className="inline-flex min-h-11 items-center text-civic-navy underline">What these records can tell you</Link>
      <p>A name or employer in a filing does not establish a person’s current employment, political views or relationship to other donors.</p>
    </footer>
  </article>
}
