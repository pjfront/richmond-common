'use client'

import { useState } from 'react'
import TopicPreferences from './TopicPreferences'
import DistrictSelector from './DistrictSelector'
import CandidatePreferences from './CandidatePreferences'
import type { SubscriptionPreferences, PreferencesResponse } from '@/lib/types'
import { SUBSCRIPTION_SUBJECTS, SUBJECT_FOLLOW_ROLLOUT } from '@/lib/subscription-subjects'

interface CouncilMember {
  district: string
  name: string
}

interface Candidate {
  id: string
  name: string
  office: string
  isIncumbent: boolean
  status: string
}

interface PreferencesPanelProps {
  token: string
  initialPreferences?: SubscriptionPreferences
  candidates: Candidate[]
  councilMembers: CouncilMember[]
}

export default function PreferencesPanel({
  token,
  initialPreferences,
  candidates,
  councilMembers,
}: PreferencesPanelProps) {
  const [topics, setTopics] = useState<string[]>(initialPreferences?.topics ?? [])
  const [subjects, setSubjects] = useState<string[]>(initialPreferences?.subjects ?? [])
  const [receiveCouncilUpdates, setReceiveCouncilUpdates] = useState(initialPreferences?.receiveCouncilUpdates ?? true)
  const [districts, setDistricts] = useState<string[]>(initialPreferences?.districts ?? [])
  const [selectedCandidates, setSelectedCandidates] = useState<string[]>(initialPreferences?.candidates ?? [])
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const [errorMessage, setErrorMessage] = useState('')

  async function handleSave() {
    setStatus('saving')
    setErrorMessage('')

    try {
      const res = await fetch('/api/subscribe/preferences', {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          token,
          preferences: {
            topics,
            subjects,
            receiveCouncilUpdates,
            districts,
            candidates: selectedCandidates,
          } satisfies SubscriptionPreferences,
        }),
      })

      const data = (await res.json()) as PreferencesResponse

      if (data.success) {
        setStatus('saved')
        setTimeout(() => setStatus('idle'), 3000)
      } else {
        setStatus('error')
        setErrorMessage(data.error ?? 'Failed to save.')
      }
    } catch {
      setStatus('error')
      setErrorMessage('Something went wrong. Please try again.')
    }
  }

  return (
    <div className="space-y-6">
      <fieldset>
        <legend className="text-lg font-semibold text-civic-navy">Stories and November choices</legend>
        <p className="mt-2 text-slate-600">Receive reviewed updates for your selections in one weekly email, when there is something new.</p>
        <p className="mt-2 text-sm text-slate-600">{SUBJECT_FOLLOW_ROLLOUT}</p>
        <div className="mt-3 space-y-1">{SUBSCRIPTION_SUBJECTS.map(subject => <label key={subject.id} className="flex min-h-11 items-center gap-3 text-slate-700">
          <input type="checkbox" checked={subjects.includes(subject.id)} onChange={event => setSubjects(current => event.target.checked ? [...current, subject.id] : current.filter(id => id !== subject.id))} className="h-5 w-5 shrink-0 accent-civic-navy" />
          {subject.label}
        </label>)}</div>
      </fieldset>

      <section className="border-t border-slate-200 pt-6" aria-labelledby="council-email-heading">
        <h2 id="council-email-heading" className="text-lg font-semibold text-civic-navy">General council emails</h2>
        <label className="mt-2 flex min-h-11 items-center gap-3 text-slate-700"><input type="checkbox" checked={receiveCouncilUpdates} onChange={event => setReceiveCouncilUpdates(event.target.checked)} className="h-5 w-5 accent-civic-navy" />Include council previews and recaps</label>
        <p className="mt-2 text-sm text-slate-600">This includes council emails outside your followed stories. In the planned weekly digest, topic choices below filter meeting recaps; leaving topics blank includes every available recap. Topics do not filter separate pre-meeting or recap emails.</p>
        {receiveCouncilUpdates && <div className="mt-4"><TopicPreferences selectedTopics={topics} onChange={setTopics} /></div>}
      </section>

      <div className="border-t border-slate-200 pt-6">
        <h2 className="text-lg font-semibold text-civic-navy">Saved local context</h2>
        <p className="my-3 text-sm text-slate-600">District and candidate choices are saved for future features. They do not filter email delivery.</p>
        <DistrictSelector
          selectedDistricts={districts}
          onChange={setDistricts}
          councilMembers={councilMembers}
        />
      </div>

      {candidates.length > 0 && (
        <div className="border-t border-slate-200 pt-6">
          <CandidatePreferences
            candidates={candidates}
            selectedCandidates={selectedCandidates}
            onChange={setSelectedCandidates}
          />
        </div>
      )}

      <div className="border-t border-slate-200 pt-4">
        <div className="flex items-center gap-3">
          <button
            type="button"
            onClick={handleSave}
            disabled={status === 'saving'}
            className="min-h-11 px-5 py-2 bg-civic-navy text-white font-medium rounded-md hover:bg-civic-navy-light transition-colors disabled:opacity-50"
          >
            {status === 'saving' ? 'Saving...' : 'Save preferences'}
          </button>

          {status === 'saved' && (
            <span role="status" className="text-sm text-green-700 font-medium">
              Preferences saved
            </span>
          )}
          {status === 'error' && (
            <span role="alert" className="text-sm text-red-600">{errorMessage}</span>
          )}
        </div>

        {!receiveCouncilUpdates && subjects.length === 0 && status === 'idle' && (
          <p className="text-sm text-slate-600 mt-2">
            No update emails are selected. You can still manage or unsubscribe using this link.
          </p>
        )}
      </div>
    </div>
  )
}
