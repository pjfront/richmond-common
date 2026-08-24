import { permanentRedirect } from 'next/navigation'

interface PageProps {
  params: Promise<{ slug: string }>
}

/** Preserve old bookmarks while consolidating election funding on the election page. */
export default async function MayorFundingPage({ params }: PageProps) {
  const { slug } = await params
  permanentRedirect(`/elections/${slug}`)
}
