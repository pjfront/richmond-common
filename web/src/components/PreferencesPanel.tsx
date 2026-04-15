'use client'

import { useState } from 'react'
import TopicPreferences from './TopicPreferences'
import DistrictSelector from './DistrictSelector'
import CandidatePreferences from './CandidatePreferences'
import type { SubscriptionPreferences, PreferencesResponse } from '@/lib/types'
import type { LocalIssue } from '@/lib/local-issues'

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
  /** Topic taxonomy fetched by the server parent via getTopicTaxonomy(). */
  topicTaxonomy: LocalIssue[]
}

export default function PreferencesPanel({
  token,
  initialPreferences,
  candidates,
  councilMembers,
  topicTaxonomy,
}: PreferencesPanelProps) {
  const [topics, setTopics] = useState<string[]>(initialPreferences?.topics ?? [])
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

  const hasSelections = topics.length > 0 || districts.length > 0 || selectedCandidates.length > 0

  return (
    <div className="space-y-6">
      <TopicPreferences selectedTopics={topics} onChange={setTopics} topics={topicTaxonomy} />

      <div className="border-t border-slate-200 pt-6">
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
            className="px-5 py-2 bg-civic-navy text-white font-medium rounded-md hover:bg-civic-navy-light transition-colors disabled:opacity-50"
          >
            {status === 'saving' ? 'Saving...' : 'Save preferences'}
          </button>

          {status === 'saved' && (
            <span className="text-sm text-green-700 font-medium">
              Preferences saved
            </span>
          )}
          {status === 'error' && (
            <span className="text-sm text-red-600">{errorMessage}</span>
          )}
        </div>

        {!hasSelections && status === 'idle' && (
          <p className="text-xs text-slate-400 mt-2">
            No preferences selected — you&apos;ll get updates on everything.
          </p>
        )}
      </div>
    </div>
  )
}
