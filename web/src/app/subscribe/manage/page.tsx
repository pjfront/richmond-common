import type { Metadata } from 'next'
import Link from 'next/link'
import { getSupabaseAdmin } from '@/lib/supabase-admin'
import { getOfficials, getUpcomingElection, getElectionWithCandidates } from '@/lib/queries'
import PreferencesPanel from '@/components/PreferencesPanel'
import type { EmailSubscriber, EmailPreference } from '@/lib/types'
import { groupSubscriptionPreferences } from '@/lib/subscription-preferences'
import { SUBJECT_FOLLOW_ROLLOUT } from '@/lib/subscription-subjects'

export const metadata: Metadata = {
  title: 'Your Richmond Briefing',
  robots: { index: false }, // Token-parameterized page
  referrer: 'no-referrer',
}

const BASE_URL = process.env.NEXT_PUBLIC_SITE_URL || 'https://richmondcommons.org'

export default async function ManagePreferencesPage(
  props: { searchParams: Promise<{ token?: string }> },
) {
  const { token } = await props.searchParams

  if (!token) {
    return <ErrorCard title="Missing link" message="This page requires a link from your email." />
  }

  // Authenticate subscriber
  const supabase = getSupabaseAdmin()
  const { data: subscriber } = await supabase
    .from('email_subscribers')
    .select('id, name, status, unsubscribe_token, receive_council_updates')
    .eq('unsubscribe_token', token)
    .single() as { data: (Pick<EmailSubscriber, 'id' | 'name' | 'status' | 'unsubscribe_token'> & { receive_council_updates: boolean }) | null; error: unknown }

  if (!subscriber) {
    return <ErrorCard title="Link not found" message="This link is invalid or has expired." />
  }

  if (subscriber.status === 'unsubscribed') {
    return (
      <div className="max-w-lg mx-auto px-4 sm:px-6 py-12 text-center">
        <h1 className="text-2xl font-bold text-civic-navy mb-3">You&apos;re unsubscribed</h1>
        <p className="text-slate-600">
          You&apos;ve previously unsubscribed from Richmond Commons updates.
        </p>
        <p className="text-slate-600 mt-2">
          Want to re-subscribe?{' '}
          <Link href="/subscribe" className="text-civic-navy-light hover:text-civic-navy underline">
            Sign up again
          </Link>
        </p>
      </div>
    )
  }

  // Load preferences, council members, and candidates in parallel
  const prefsQuery = supabase
    .from('email_preferences')
    .select('preference_type,preference_value')
    .eq('subscriber_id', subscriber.id)

  const [prefsResult, officials, election] = await Promise.all([
    prefsQuery as unknown as Promise<{ data: EmailPreference[] | null; error: unknown }>,
    getOfficials(undefined, { currentOnly: true, councilOnly: true }),
    getUpcomingElection(),
  ])

  if (prefsResult.error) return <ErrorCard title="Preferences unavailable" message="Your saved choices could not be loaded. Please try again before changing them." />
  const prefs = groupSubscriptionPreferences(prefsResult.data ?? [], subscriber.receive_council_updates)

  // Map officials to district → name for DistrictSelector
  const councilMembers = officials
    .filter((o) => o.seat?.startsWith('District'))
    .map((o) => ({
      district: o.seat!.replace('District ', ''),
      name: o.name,
    }))

  // Load candidates if there's an upcoming election
  let candidates: Array<{ id: string; name: string; office: string; isIncumbent: boolean; status: string }> = []
  if (election) {
    const electionDetail = await getElectionWithCandidates(election.id)
    if (electionDetail) {
      candidates = electionDetail.candidates.map((c) => ({
        id: c.id,
        name: c.candidate_name,
        office: c.office_sought,
        isIncumbent: c.is_incumbent,
        status: c.status,
      }))
    }
  }

  const unsubscribeUrl = `${BASE_URL}/api/subscribe?token=${subscriber.unsubscribe_token}`

  return (
    <div className="max-w-lg mx-auto px-4 sm:px-6 py-12">
      <header className="mb-8">
        <h1 className="text-2xl font-bold text-civic-navy">Your Richmond briefing</h1>
        <p className="text-sm text-slate-600 mt-2">
          Choose story and election follows, and whether to receive general council emails.
          {subscriber.name && (
            <span className="text-slate-400"> Signed in as {subscriber.name}.</span>
          )}
        </p>
      </header>

      <div className="bg-white border border-slate-200 rounded-lg p-6 shadow-sm">
        <PreferencesPanel
          token={token}
          initialPreferences={prefs}
          candidates={candidates}
          councilMembers={councilMembers}
        />
      </div>

      <footer className="mt-8 pt-6 border-t border-slate-200 text-center">
        <p className="text-xs text-slate-400">
          {SUBJECT_FOLLOW_ROLLOUT}
        </p>
        <p className="text-xs text-slate-400 mt-2">
          <a href={unsubscribeUrl} className="hover:text-slate-600 underline">
            Unsubscribe
          </a>
        </p>
      </footer>
    </div>
  )
}

function ErrorCard({ title, message }: { title: string; message: string }) {
  return (
    <div className="max-w-lg mx-auto px-4 sm:px-6 py-12 text-center">
      <h1 className="text-2xl font-bold text-civic-navy mb-3">{title}</h1>
      <p className="text-slate-600">{message}</p>
      <p className="mt-4">
        <Link href="/subscribe" className="text-civic-navy-light hover:text-civic-navy underline">
          Subscribe to Richmond Commons
        </Link>
      </p>
    </div>
  )
}
