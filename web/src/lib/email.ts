import { Resend } from 'resend'
import type { Provenance } from './types'
import { digestBriefHref, type DigestBrief } from './digest-selection'
import { SUBJECT_FOLLOW_ROLLOUT } from './subscription-subjects'
import {
  recapAttributionText,
  orientationAttributionText,
  digestAttributionText,
} from './provenance'

let _resend: Resend | null = null

function getResend(): Resend {
  if (_resend) return _resend
  const apiKey = process.env.RESEND_API_KEY
  if (!apiKey) {
    throw new Error('Missing RESEND_API_KEY environment variable.')
  }
  _resend = new Resend(apiKey)
  return _resend
}

interface SendEmailOptions {
  to: string
  subject: string
  html: string
  text?: string
  idempotencyKey?: string
}

export async function sendEmail({ to, subject, html, text, idempotencyKey }: SendEmailOptions): Promise<{
  success: boolean
  error?: string
  providerId?: string
  /** True when the provider may have accepted the request before transport failed. */
  ambiguous?: boolean
}> {
  try {
    const resend = getResend()
    const { data, error } = await resend.emails.send(
      {
        from: 'Richmond Commons <updates@richmondcommons.org>',
        to,
        subject,
        html,
        text,
      },
      idempotencyKey ? { idempotencyKey } : undefined,
    )
    if (error) {
      console.error('Resend error:', error)
      return { success: false, error: error.message }
    }
    return { success: true, providerId: data?.id }
  } catch (err) {
    console.error('Email send failed:', err)
    return {
      success: false,
      error: 'Email provider response was not confirmed',
      ambiguous: true,
    }
  }
}

/** Welcome email sent on new subscription. */
export function buildWelcomeEmail(name: string | null, unsubscribeUrl: string, manageUrl?: string): { subject: string; html: string; text: string } {
  const greeting = name ? `Hi ${name},` : 'Hi,'
  const welcomeSummary = `Your choices are saved. Council previews and recaps are sent only when general council emails are enabled. Use your private management link to review your selections. ${SUBJECT_FOLLOW_ROLLOUT}`
  const subject = 'Welcome to Richmond Commons'

  const html = `
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; color: #475569;">
      <div style="border-bottom: 3px solid #1e3a5f; padding-bottom: 16px; margin-bottom: 24px;">
        <h1 style="color: #1e3a5f; font-size: 22px; margin: 0;">Richmond Commons</h1>
      </div>

      <p style="font-size: 16px; line-height: 1.6;">${escapeEmailHtml(greeting)}</p>

      <p style="font-size: 16px; line-height: 1.6;">
        ${welcomeSummary}
      </p>

      <p style="font-size: 16px; line-height: 1.6;">
        Browse meeting records going back to 2005, including agendas, votes, and public comments where available.
      </p>

      <p style="font-size: 15px; line-height: 1.6; font-weight: 600; color: #1e3a5f; margin-bottom: 4px;">
        Try searching for things like:
      </p>
      <ul style="font-size: 15px; line-height: 1.8; padding-left: 20px; margin-top: 0;">
        <li><a href="https://richmondcommons.org/search?q=Chevron+community+benefits+agreement" style="color: #2d5a8e;">Chevron community benefits agreement</a></li>
        <li><a href="https://richmondcommons.org/search?q=rent+control+exemptions" style="color: #2d5a8e;">rent control exemptions</a></li>
        <li><a href="https://richmondcommons.org/search?q=Point+Molate+development" style="color: #2d5a8e;">Point Molate development</a></li>
        <li><a href="https://richmondcommons.org/search?q=police+oversight+use+of+force" style="color: #2d5a8e;">police oversight use of force</a></li>
      </ul>

      <p style="font-size: 15px; line-height: 1.6;">
        Or browse by section:
      </p>
      <ul style="font-size: 15px; line-height: 1.8; padding-left: 20px;">
        <li><a href="https://richmondcommons.org/meetings" style="color: #2d5a8e;">Meetings</a>: agenda items, votes, and public comments</li>
        <li><a href="https://richmondcommons.org/council" style="color: #2d5a8e;">Council profiles</a>: voting records and campaign finance</li>
        <li><a href="https://richmondcommons.org/elections" style="color: #2d5a8e;">Elections</a>: candidates and fundraising for the November election</li>
      </ul>

      <p style="font-size: 14px; color: #94a3b8; margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px;">
        You're receiving this because you signed up at richmondcommons.org.<br/>
        ${manageUrl ? `<a href="${manageUrl}" style="color: #64748b;">Choose your topics</a> &middot; ` : ''}
        <a href="${unsubscribeUrl}" style="color: #94a3b8;">Unsubscribe</a>
      </p>
    </div>
  `

  const text = `${greeting}

${welcomeSummary}

Browse meeting records going back to 2005, including agendas, votes, and public comments where available.

Try searching for things like:
- Chevron community benefits agreement: https://richmondcommons.org/search?q=Chevron+community+benefits+agreement
- rent control exemptions: https://richmondcommons.org/search?q=rent+control+exemptions
- Point Molate development: https://richmondcommons.org/search?q=Point+Molate+development
- police oversight use of force: https://richmondcommons.org/search?q=police+oversight+use+of+force

Or browse by section:
- Meetings: https://richmondcommons.org/meetings
- Council profiles: https://richmondcommons.org/council
- Elections: candidates and fundraising for the November election: https://richmondcommons.org/elections
---
You're receiving this because you signed up at richmondcommons.org.
${manageUrl ? `Choose your topics: ${manageUrl}\n` : ''}Unsubscribe: ${unsubscribeUrl}`

  return { subject, html, text }
}

// ─── Shared Email Layout ────────────────────────────────────

/** Shared HTML wrapper: civic-navy header, content slot, footer with AI disclosure + unsubscribe. */
function emailLayout(
  bodyHtml: string,
  footerNote: string,
  unsubscribeUrl: string,
  manageUrl?: string,
  canary = false,
): string {
  const deliveryFooter = canary
    ? 'CANARY TEST — this message was sent only to the operator-approved test address. No subscriber delivery was recorded.'
    : `You're receiving this because you subscribed at richmondcommons.org.<br/>
        ${manageUrl ? `<a href="${manageUrl}" style="color: #64748b;">Manage preferences</a> &middot; ` : ''}
        <a href="${unsubscribeUrl}" style="color: #94a3b8;">Unsubscribe</a>`
  return `
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; color: #475569;">
      <div style="border-bottom: 3px solid #1e3a5f; padding-bottom: 16px; margin-bottom: 24px;">
        <h1 style="color: #1e3a5f; font-size: 22px; margin: 0;">Richmond Commons</h1>
      </div>
      ${bodyHtml}
      <p style="font-size: 13px; color: #94a3b8; margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px;">
        ${footerNote}<br/>
        ${deliveryFooter}
      </p>
    </div>
  `
}

/** Convert markdown **bold** to HTML <strong> and split into <p> tags. */
function markdownToHtml(text: string): string {
  return text
    .split('\n\n')
    .filter(Boolean)
    .map((para) => {
      const converted = para.replace(/\*\*([^*]+)\*\*/g, '<strong style="color: #1e3a5f;">$1</strong>')
      return `<p style="font-size: 16px; line-height: 1.6; margin: 0 0 12px 0;">${converted}</p>`
    })
    .join('\n')
}

/** Strip markdown bold markers for plain text. */
function markdownToPlain(text: string): string {
  return text.replace(/\*\*([^*]+)\*\*/g, '$1')
}

// ─── Meeting Orientation Email ─────────────────────────────

interface OrientationMeeting {
  id: string
  meeting_date: string
  orientation_preview: string
  agenda_url: string | null
  // Provenance written by the generator. Optional — buildOrientationEmail
  // synthesizes a default agenda_packet provenance when missing so the
  // attribution line is always present.
  orientation_preview_provenance?: Provenance | null
}

/** Build a pre-meeting orientation email from an orientation_preview narrative. */
export function buildOrientationEmail(
  meeting: OrientationMeeting,
  unsubscribeUrl: string,
  manageUrl?: string,
): { subject: string; html: string; text: string } {
  const date = new Date(meeting.meeting_date + 'T12:00:00')
  const formatted = date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
  const subject = `What's on the agenda for ${formatted}`
  const meetingUrl = `https://richmondcommons.org/meetings/${meeting.id}`

  const bodyHtml = `
    ${markdownToHtml(meeting.orientation_preview)}
    <p style="margin-top: 20px;">
      <a href="${meetingUrl}" style="display: inline-block; padding: 10px 20px; background: #1e3a5f; color: #ffffff; text-decoration: none; border-radius: 6px; font-size: 14px; font-weight: 600;">
        View full agenda details
      </a>
    </p>
  `

  // Orientation is always agenda_packet; synthesize a default if the
  // generator didn't write one (pre-backfill compatibility).
  const provenance: Provenance = meeting.orientation_preview_provenance ?? {
    kind: 'agenda_packet',
    agenda_url: meeting.agenda_url,
    as_of: '',
  }
  const footerNote = orientationAttributionText(provenance)

  const html = emailLayout(bodyHtml, footerNote, unsubscribeUrl, manageUrl)

  const text = `${subject}\n\n${markdownToPlain(meeting.orientation_preview)}\n\nView full agenda details: ${meetingUrl}\n\n---\n${footerNote}\nYou're receiving this because you subscribed at richmondcommons.org.\n${manageUrl ? `Manage preferences: ${manageUrl}\n` : ''}Unsubscribe: ${unsubscribeUrl}`

  return { subject, html, text }
}

// ─── Meeting Recap Email ────────────────────────────────────

interface RecapMeeting {
  id: string
  meeting_date: string
  meeting_type: string
  meeting_recap: string
  minutes_url: string | null
  // Provenance for the recap text. When omitted, falls back to the
  // legacy `source: 'transcript'` parameter (compatibility with callers
  // that haven't been updated yet).
  meeting_recap_provenance?: Provenance | null
}

/**
 * Build a meeting recap email from an existing meeting_recap or
 * transcript_recap narrative.
 *
 * Source attribution comes from meeting.meeting_recap_provenance when
 * present (the canonical post-migration-095 path). The legacy `source`
 * parameter is retained for backward compatibility with callers that
 * still pass `'transcript'` literally. Without persisted provenance it uses
 * a channel-neutral recording disclosure rather than guessing the provider.
 */
export function buildRecapEmail(
  meeting: RecapMeeting,
  unsubscribeUrl: string,
  source?: 'transcript',
  manageUrl?: string,
): { subject: string; html: string; text: string } {
  const date = new Date(meeting.meeting_date + 'T12:00:00')
  const formatted = date.toLocaleDateString('en-US', { month: 'long', day: 'numeric' })
  const subject = `What happened at the ${formatted} meeting`
  const meetingUrl = `https://richmondcommons.org/meetings/${meeting.id}`

  const bodyHtml = `
    ${markdownToHtml(meeting.meeting_recap)}
    <p style="margin-top: 20px;">
      <a href="${meetingUrl}" style="display: inline-block; padding: 10px 20px; background: #1e3a5f; color: #ffffff; text-decoration: none; border-radius: 6px; font-size: 14px; font-weight: 600;">
        View full meeting details
      </a>
    </p>
  `

  // Resolve provenance. Persisted provenance is authoritative. Legacy
  // transcript callers get a channel-neutral disclosure when that persisted
  // metadata is absent; inferring KCRT would mislabel Granicus fallbacks.
  let footerNote: string
  if (meeting.meeting_recap_provenance) {
    footerNote = recapAttributionText(meeting.meeting_recap_provenance)
  } else if (source === 'transcript') {
    footerNote = 'This recap was auto-generated from a meeting recording. Vote outcomes are preliminary until official minutes are published.'
  } else {
    footerNote = recapAttributionText({
      kind: 'official_minutes',
      minutes_url: meeting.minutes_url,
      as_of: '',
    })
  }

  const html = emailLayout(bodyHtml, footerNote, unsubscribeUrl, manageUrl)

  const text = `${subject}\n\n${markdownToPlain(meeting.meeting_recap)}\n\nView full meeting details: ${meetingUrl}\n\n---\n${footerNote}\nYou're receiving this because you subscribed at richmondcommons.org.\n${manageUrl ? `Manage preferences: ${manageUrl}\n` : ''}Unsubscribe: ${unsubscribeUrl}`

  return { subject, html, text }
}

// ─── Weekly Digest Email ────────────────────────────────────

function escapeEmailHtml(value: string): string {
  return value.replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;').replaceAll("'", '&#39;')
}

/** Build a weekly digest email summarizing recent meetings. */
export function buildDigestEmail(
  meetings: RecapMeeting[],
  unsubscribeUrl: string,
  manageUrl?: string,
  options?: { canary?: boolean; briefs?: DigestBrief[] },
): { subject: string; html: string; text: string } {
  const count = meetings.length
  const briefs = options?.briefs ?? []
  const canary = options?.canary === true
  const subject = `${canary ? '[CANARY] ' : ''}This week in Richmond: ${briefs.length ? `${briefs.length} reviewed update${briefs.length === 1 ? '' : 's'}${count ? ` and ${count} meeting${count === 1 ? '' : 's'}` : ''}` : `${count} meeting${count === 1 ? '' : 's'}`}`

  const briefSections = briefs.map(brief => `<div style="margin-bottom:28px;padding-bottom:24px;border-bottom:1px solid #e2e8f0;">
    <h2 style="color:#1e3a5f;font-size:17px;">${escapeEmailHtml(brief.title)}</h2>
    <p>AI-written; checked against linked sources. Published ${escapeEmailHtml(brief.published_at)} · version ${brief.content_version}.</p>
    <p style="white-space:pre-line;">${escapeEmailHtml(brief.body)}</p>
    <a href="${escapeEmailHtml(digestBriefHref(brief))}">Read this update and its continuing story</a>
    <ul>${brief.sources.map(source => `<li><a href="${escapeEmailHtml(source.url)}">${escapeEmailHtml(source.title)}</a> · ${source.source_tier === 1 ? 'Official record' : 'Independent journalism'}${source.source_date ? ` · ${escapeEmailHtml(source.source_date)}` : ' · source date not supplied'}</li>`).join('')}</ul>
  </div>`).join('\n')

  const sectionsHtml = meetings.map((m) => {
    const date = new Date(m.meeting_date + 'T12:00:00')
    const formatted = date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
    const meetingUrl = `https://richmondcommons.org/meetings/${m.id}`
    // First two paragraphs as preview
    const preview = m.meeting_recap.split('\n\n').filter(Boolean).slice(0, 2).join('\n\n')

    return `
      <div style="margin-bottom: 28px; padding-bottom: 24px; border-bottom: 1px solid #e2e8f0;">
        <h2 style="color: #1e3a5f; font-size: 17px; margin: 0 0 12px 0;">${formatted}</h2>
        ${markdownToHtml(preview)}
        <a href="${meetingUrl}" style="color: #2d5a8e; font-size: 14px; font-weight: 500;">Read the full recap &rarr;</a>
      </div>
    `
  }).join('\n')

  // Preserve missing values so one unknown source cannot be hidden by the
  // known sources elsewhere in the same digest.
  const provenances = meetings.map((m) => m.meeting_recap_provenance ?? null)
  const footerNote = [count ? digestAttributionText(provenances) : '', briefs.length ? 'Reviewed updates are AI-written explanations approved against the linked sources. The version and publication date identify the reviewed text.' : ''].filter(Boolean).join(' ')
  const html = emailLayout(briefSections + sectionsHtml, footerNote, unsubscribeUrl, manageUrl, canary)

  const textSections = meetings.map((m) => {
    const date = new Date(m.meeting_date + 'T12:00:00')
    const formatted = date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
    const meetingUrl = `https://richmondcommons.org/meetings/${m.id}`
    const preview = m.meeting_recap.split('\n\n').filter(Boolean).slice(0, 2).join('\n\n')
    return `${formatted}\n\n${markdownToPlain(preview)}\n\nRead the full recap: ${meetingUrl}`
  }).join('\n\n---\n\n')

  const deliveryFooter = canary
    ? 'CANARY TEST — this message was sent only to the operator-approved test address. No subscriber delivery was recorded.'
    : `You're receiving this because you subscribed at richmondcommons.org.\n${manageUrl ? `Manage preferences: ${manageUrl}\n` : ''}Unsubscribe: ${unsubscribeUrl}`
  const briefText = briefs.map(brief => `${brief.title}\nAI-written; checked against linked sources. Published ${brief.published_at} · version ${brief.content_version}.\n\n${brief.body}\n\nRead this update: ${digestBriefHref(brief)}\n${brief.sources.map(source => `${source.title} (${source.source_tier === 1 ? 'Official record' : 'Independent journalism'}; ${source.source_date ?? 'source date not supplied'}): ${source.url}`).join('\n')}`).join('\n\n---\n\n')
  const text = `${subject}\n\n${[briefText, textSections].filter(Boolean).join('\n\n---\n\n')}\n\n---\n${footerNote}\n${deliveryFooter}`

  return { subject, html, text }
}
