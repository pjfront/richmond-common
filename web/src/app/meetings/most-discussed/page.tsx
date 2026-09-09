import { redirect } from 'next/navigation'
import type { Metadata } from 'next'

export const metadata: Metadata = { title: 'Council motion records', robots: { index: false, follow: false } }

/** The former ranking combined unrelated scores and unsupported outcome labels. */
export default function MostDiscussedPage() {
  redirect('/council/analytics')
}
