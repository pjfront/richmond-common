'use client'

import { useEffect, useState } from 'react'

interface RecapMeeting {
  id: string
  date: string
  type: string
  hasTranscriptRecap: boolean
  hasMeetingRecap: boolean
  hasSummary: boolean
  hasMinutes: boolean
  daysAgo: number
}

function statusBadge(ok: boolean, label: string) {
  return (
    <span
      className={`text-xs font-medium px-1.5 py-0.5 rounded ${
        ok ? 'bg-green-50 text-green-700' : 'bg-red-50 text-red-600'
      }`}
    >
      {ok ? label : `no ${label}`}
    </span>
  )
}

export default function RecapStatePanel() {
  const [meetings, setMeetings] = useState<RecapMeeting[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    fetch('/api/operator/recap-state')
      .then((r) => r.json())
      .then((data) => {
        if (data.error) setError(data.error)
        else setMeetings(data.meetings)
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  if (loading) return <p className="text-slate-500 p-4">Loading recap state...</p>
  if (error) return <p className="text-red-600 p-4">Error: {error}</p>

  const missing = meetings.filter(
    (m) => m.daysAgo > 5 && (!m.hasTranscriptRecap || !m.hasMeetingRecap)
  )
  const ok = meetings.filter(
    (m) => m.daysAgo <= 5 || (m.hasTranscriptRecap && m.hasMeetingRecap)
  )

  return (
    <div>
      <div className="mb-4 flex gap-4 text-sm">
        <span className="text-slate-500">
          {ok.length} current, {missing.length} need attention
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs uppercase text-slate-400">
              <th className="py-2 pr-4">Date</th>
              <th className="py-2 pr-4">Type</th>
              <th className="py-2 pr-4">Days ago</th>
              <th className="py-2 pr-4">Transcript recap</th>
              <th className="py-2 pr-4">Meeting recap</th>
              <th className="py-2 pr-4">Summary</th>
              <th className="py-2">Minutes</th>
            </tr>
          </thead>
          <tbody>
            {meetings.map((m) => {
              const needsAttention = m.daysAgo > 5 && (!m.hasTranscriptRecap || !m.hasMeetingRecap)
              return (
                <tr
                  key={m.id}
                  className={`border-b border-slate-100 ${
                    needsAttention ? 'bg-amber-50' : ''
                  }`}
                >
                  <td className="py-2 pr-4 font-medium">{m.date}</td>
                  <td className="py-2 pr-4 capitalize">{m.type}</td>
                  <td className="py-2 pr-4">{m.daysAgo}d</td>
                  <td className="py-2 pr-4">{statusBadge(m.hasTranscriptRecap, 'recap')}</td>
                  <td className="py-2 pr-4">{statusBadge(m.hasMeetingRecap, 'recap')}</td>
                  <td className="py-2 pr-4">{statusBadge(m.hasSummary, 'summary')}</td>
                  <td className="py-2">{statusBadge(m.hasMinutes, 'minutes')}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </div>
  )
}
