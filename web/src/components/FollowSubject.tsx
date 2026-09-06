import Link from 'next/link'
import { isSubscriptionSubject, SUBJECT_FOLLOW_ROLLOUT } from '@/lib/subscription-subjects'

export default function FollowSubject({ subject }: { subject: string }) {
  if (!isSubscriptionSubject(subject)) return null
  return <aside className="mt-8 rounded-lg border border-slate-200 bg-slate-50 p-5">
    <h2 className="text-lg font-semibold text-civic-navy">Keep following this story</h2>
    <p className="mt-2 text-slate-700">Choose this subject for reviewed updates in a weekly email when there is something new.</p>
    <p className="mt-2 text-sm text-slate-600">{SUBJECT_FOLLOW_ROLLOUT}</p>
    <Link href={`/subscribe?follow=${subject}`} className="mt-3 inline-flex min-h-11 items-center text-civic-navy underline underline-offset-4">Choose this follow →</Link>
  </aside>
}
