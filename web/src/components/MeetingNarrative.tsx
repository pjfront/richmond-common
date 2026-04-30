'use client'

import { useState } from 'react'
import * as Collapsible from '@radix-ui/react-collapsible'
import type { Provenance } from '@/lib/types'
import { RecapAttribution, OrientationAttribution } from './SourceAttribution'

interface MeetingNarrativeProps {
  orientationPreview: string | null
  meetingRecap: string | null
  transcriptRecap: string | null
  meetingSummary: string | null
  meetingDate: string
  agendaUrl: string | null
  minutesUrl: string | null
  // Provenance for each generated artifact. Written by the Python
  // generator in the same UPDATE as the artifact text (migration 095),
  // so the rendered attribution can never desync from reality. Null
  // means provenance hasn't been backfilled yet — <RecapAttribution>
  // and <OrientationAttribution> render nothing in that case rather
  // than guessing.
  meetingRecapProvenance: Provenance | null
  meetingSummaryProvenance: Provenance | null
  transcriptRecapProvenance: Provenance | null
  orientationProvenance: Provenance | null
}

/**
 * Renders markdown paragraphs with **bold** support.
 * Shared helper that deduplicates the parsing logic previously
 * copy-pasted across orientation, recap, and summary sections.
 */
function NarrativeParagraphs({ text }: { text: string }) {
  return (
    <div className="space-y-3 text-[15px] text-slate-700 leading-relaxed">
      {text.split('\n\n').filter(Boolean).map((para, i) => (
        <p key={i}>
          {para.split(/(\*\*[^*]+\*\*)/).map((chunk, j) =>
            chunk.startsWith('**') && chunk.endsWith('**')
              ? <strong key={j} className="font-semibold text-civic-navy">{chunk.slice(2, -2)}</strong>
              : chunk
          )}
        </p>
      ))}
    </div>
  )
}

/**
 * Meeting narrative component with cascading display logic:
 *
 * 1. recap + orientation → recap primary, orientation collapsible below
 * 2. recap only → recap block
 * 3. summary only → amber bullet list (fallback)
 * 4. orientation only → sky-teal standalone (pre-meeting)
 * 5. nothing → null
 *
 * Source attribution for each block is rendered via <RecapAttribution> /
 * <OrientationAttribution>, which read the artifact's Provenance struct
 * (migration 095). The audit-driven branching that previously lived
 * inline (hasMinutesMotions) is now an artifact-level property —
 * impossible to desync from the actual generator inputs.
 */
export default function MeetingNarrative({
  orientationPreview,
  meetingRecap,
  transcriptRecap,
  meetingSummary,
  meetingDate,
  agendaUrl,
  minutesUrl,
  meetingRecapProvenance,
  meetingSummaryProvenance,
  transcriptRecapProvenance,
  orientationProvenance,
}: MeetingNarrativeProps) {
  const [showOrientation, setShowOrientation] = useState(false)

  // Inject minutes_url / agenda_url into the provenance struct at render
  // time. The generator stored the URL when it knew it, but URLs can
  // arrive after generation (minutes_url especially); pull from the
  // current meeting row to keep the link live.
  const recapP =
    meetingRecapProvenance && meetingRecapProvenance.kind === 'official_minutes'
      ? { ...meetingRecapProvenance, minutes_url: minutesUrl ?? meetingRecapProvenance.minutes_url }
      : meetingRecapProvenance
  const orientationP =
    orientationProvenance && orientationProvenance.kind === 'agenda_packet'
      ? { ...orientationProvenance, agenda_url: agendaUrl ?? orientationProvenance.agenda_url }
      : orientationProvenance

  // ── Case 1 & 2: Recap exists (primary narrative) ──────────
  if (meetingRecap) {
    return (
      <div className="border-l-4 border-emerald-500 bg-emerald-50/60 rounded-r-lg p-6 mb-8">
        <h2 className="text-base font-semibold text-civic-navy mb-3">
          What happened
        </h2>
        <NarrativeParagraphs text={meetingRecap} />

        <div className="flex items-center justify-between mt-4">
          <p className="text-xs text-slate-400">
            <RecapAttribution p={recapP} />
          </p>

          <div className="flex items-center gap-3">
            {agendaUrl && (
              <a
                href={agendaUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-civic-navy-light hover:text-civic-navy hover:underline"
              >
                View agenda
              </a>
            )}
          </div>
        </div>

        {/* Collapsible orientation — only when both exist */}
        {orientationPreview && (
          <Collapsible.Root open={showOrientation} onOpenChange={setShowOrientation}>
            <Collapsible.Trigger asChild>
              <button className="mt-3 text-xs text-civic-navy-light hover:text-civic-navy transition-colors cursor-pointer">
                Agenda preview {showOrientation ? '‹' : '›'}
              </button>
            </Collapsible.Trigger>
            <Collapsible.Content className="collapsible-content overflow-hidden">
              <div className="mt-3 pt-3 border-t border-slate-200">
                <NarrativeParagraphs text={orientationPreview} />
                <p className="text-xs text-slate-400 mt-3">
                  <OrientationAttribution p={orientationP} />
                </p>
              </div>
            </Collapsible.Content>
          </Collapsible.Root>
        )}
      </div>
    )
  }

  // ── Case 2b: Transcript recap (post-meeting, before minutes) ──
  if (transcriptRecap) {
    return (
      <div className="border-l-4 border-violet-400 bg-violet-50/60 rounded-r-lg p-6 mb-8">
        <h2 className="text-base font-semibold text-civic-navy mb-3">
          What happened
        </h2>
        <NarrativeParagraphs text={transcriptRecap} />

        <div className="flex items-center justify-between mt-4">
          <p className="text-xs text-slate-400">
            <RecapAttribution p={transcriptRecapProvenance} />
          </p>

          <div className="flex items-center gap-3">
            {agendaUrl && (
              <a
                href={agendaUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="text-xs text-civic-navy-light hover:text-civic-navy hover:underline"
              >
                View agenda
              </a>
            )}
          </div>
        </div>

        {/* Collapsible orientation — only when both exist */}
        {orientationPreview && (
          <Collapsible.Root open={showOrientation} onOpenChange={setShowOrientation}>
            <Collapsible.Trigger asChild>
              <button className="mt-3 text-xs text-civic-navy-light hover:text-civic-navy transition-colors cursor-pointer">
                Agenda preview {showOrientation ? '‹' : '›'}
              </button>
            </Collapsible.Trigger>
            <Collapsible.Content className="collapsible-content overflow-hidden">
              <div className="mt-3 pt-3 border-t border-slate-200">
                <NarrativeParagraphs text={orientationPreview} />
                <p className="text-xs text-slate-400 mt-3">
                  <OrientationAttribution p={orientationP} />
                </p>
              </div>
            </Collapsible.Content>
          </Collapsible.Root>
        )}
      </div>
    )
  }

  // ── Case 3: Summary bullets (post-meeting, no recap yet) ──
  if (meetingSummary) {
    return (
      <div className="bg-amber-50/60 rounded-lg border border-amber-200/50 p-5 mb-8">
        <h2 className="text-sm font-medium text-civic-navy uppercase tracking-wide mb-3">
          What happened
        </h2>
        <ul className="space-y-1.5 text-sm text-slate-700 leading-relaxed list-disc list-outside ml-4">
          {meetingSummary.split('\n').filter(Boolean).map((bullet, i) => (
            <li key={i}>{bullet.replace(/^[•\-]\s*/, '')}</li>
          ))}
        </ul>
        <div className="flex items-center justify-between mt-3">
          <p className="text-xs text-slate-400">
            <RecapAttribution p={meetingSummaryProvenance} />
          </p>
          {(agendaUrl || minutesUrl) && (
            <span className="text-xs text-civic-navy-light">
              View official:{' '}
              {minutesUrl && (
                <a
                  href={minutesUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-civic-navy hover:underline"
                >
                  Minutes
                </a>
              )}
              {minutesUrl && agendaUrl && (
                <span className="text-slate-400"> | </span>
              )}
              {agendaUrl && (
                <a
                  href={agendaUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-civic-navy hover:underline"
                >
                  Agenda
                </a>
              )}
            </span>
          )}
        </div>
      </div>
    )
  }

  // ── Case 4: Orientation only (pre-meeting) ─────────────────
  if (orientationPreview) {
    const meetingDay = new Date(meetingDate + 'T00:00:00')
      .toLocaleDateString('en-US', { weekday: 'long' })
    const isPast = new Date(meetingDate + 'T23:59:59') < new Date()
    const heading = isPast ? 'Agenda preview' : `${meetingDay}’s agenda`

    return (
      <div className="border-l-4 border-sky-400 bg-sky-50/80 rounded-r-lg p-6 mb-8">
        <h2 className="text-base font-semibold text-civic-navy mb-3">
          {heading}
        </h2>
        <NarrativeParagraphs text={orientationPreview} />
        <p className="text-xs text-slate-400 mt-4">
          <OrientationAttribution p={orientationP} />
        </p>
      </div>
    )
  }

  // ── Case 5: Nothing ────────────────────────────────────────
  return null
}
