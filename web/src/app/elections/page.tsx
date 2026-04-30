import { redirect } from 'next/navigation'
import { getUpcomingElection, electionToSlug } from '@/lib/queries'

/**
 * Generic /elections index — redirects to the next upcoming election.
 *
 * Per the I128 design (vision conversation 2026-04-29): residents don't
 * shop for elections; they want the next one. When no upcoming election
 * exists, fall back to /elections/find-my-district which is the most
 * useful evergreen surface in this section.
 */
export default async function ElectionsIndexPage() {
  const election = await getUpcomingElection()
  if (election) {
    redirect(`/elections/${electionToSlug(election)}`)
  }
  redirect('/elections/find-my-district')
}
