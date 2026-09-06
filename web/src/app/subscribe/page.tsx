import type { Metadata } from 'next'
import SubscribeForm from '@/components/SubscribeForm'
import { isSubscriptionSubject, SUBSCRIPTION_SUBJECTS, SUBJECT_FOLLOW_ROLLOUT } from '@/lib/subscription-subjects'

export const metadata: Metadata = {
  title: 'Email updates',
  description:
    'Choose Richmond stories, election updates, or general council emails. Free, plain-language explanations linked to public records.',
}

export default async function SubscribePage({ searchParams }: { searchParams: Promise<{ follow?: string | string[] }> }) {
  const raw = (await searchParams).follow
  const follow = isSubscriptionSubject(raw) ? raw : undefined
  const subject = SUBSCRIPTION_SUBJECTS.find(item => item.id === follow)
  return (
    <div className="max-w-lg mx-auto px-4 sm:px-6 py-12">
      <header className="mb-8 text-center">
        <h1 className="text-3xl font-bold text-civic-navy">{subject ? 'Follow this story' : 'Stay informed'}</h1>
        <p className="text-base text-slate-600 mt-3 leading-relaxed">
          {subject ? subject.label : 'Get general council previews and recaps, with plain-language explanations linked to public records.'}
        </p>
        <p className="mt-4 text-sm leading-relaxed text-slate-600">{SUBJECT_FOLLOW_ROLLOUT}</p>
      </header>

      <div className="bg-white border border-slate-200 rounded-lg p-6 shadow-sm">
        <SubscribeForm follow={follow} surface={follow === '2026-general' ? 'november_election' : 'subscribe_page'} />
      </div>

      <div className="mt-6 space-y-3 text-slate-600">
        {subject && <p>This saves this subject for a weekly email when there are new reviewed updates. General council previews and recaps are off for a new follow-only subscription.</p>}
        <p>Already subscribed? Use “Manage preferences” in an existing Richmond Commons email to add this follow. Entering an active email address here does not change its saved choices.</p>
        <p>The welcome email contains your private management link. Keep that link private; it can change your choices or unsubscribe you.</p>
      </div>

      <footer className="mt-10 pt-6 border-t border-slate-200 text-center">
        <p className="text-xs text-slate-500">
          Explanations link to public records and identified reporting. Richmond Commons is a
          free civic transparency project, not affiliated with the City of
          Richmond.
        </p>
      </footer>
    </div>
  )
}
