import { Resend } from 'resend'

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
}

export async function sendEmail({ to, subject, html, text }: SendEmailOptions): Promise<{ success: boolean; error?: string }> {
  try {
    const resend = getResend()
    const { error } = await resend.emails.send({
      from: 'Richmond Commons <updates@richmondcommons.org>',
      to,
      subject,
      html,
      text,
    })
    if (error) {
      console.error('Resend error:', error)
      return { success: false, error: error.message }
    }
    return { success: true }
  } catch (err) {
    console.error('Email send failed:', err)
    return { success: false, error: 'Failed to send email' }
  }
}

// ─── Meeting Recap Email ────────────────────────────────────

interface RecapEmailData {
  meetingDate: string       // e.g. "April 7, 2026"
  meetingType: string       // e.g. "Regular Meeting"
  meetingId: string         // UUID for link
  recap: string             // The 4-6 paragraph meeting recap text
  itemCount: number         // Number of agenda items
  voteCount: number         // Number of recorded votes
  commentCount: number      // Number of public comments
}

/** Format meeting recap paragraphs as HTML. Handles markdown-style bold (**text**). */
function recapToHtml(recap: string): string {
  return recap
    .split('\n\n')
    .filter((p) => p.trim())
    .map((p) => {
      const escaped = p.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      const styled = escaped.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
      return `<p style="font-size: 16px; line-height: 1.7; margin-bottom: 16px; color: #475569;">${styled}</p>`
    })
    .join('\n')
}

/** Build a meeting recap email for subscribers. */
export function buildRecapEmail(
  data: RecapEmailData,
  subscriberName: string | null,
  unsubscribeUrl: string,
  manageUrl: string,
): { subject: string; html: string; text: string } {
  const { meetingDate, meetingType, meetingId, recap, itemCount, voteCount, commentCount } = data
  const greeting = subscriberName ? `Hi ${subscriberName},` : 'Hi,'
  const subject = `Richmond City Council recap — ${meetingDate}`
  const meetingUrl = `https://richmondcommons.org/meetings/${meetingId}`

  const stats: string[] = []
  if (itemCount > 0) stats.push(`${itemCount} agenda item${itemCount !== 1 ? 's' : ''}`)
  if (voteCount > 0) stats.push(`${voteCount} recorded vote${voteCount !== 1 ? 's' : ''}`)
  if (commentCount > 0) stats.push(`${commentCount} public comment${commentCount !== 1 ? 's' : ''}`)
  const statsLine = stats.length > 0 ? stats.join(' · ') : ''

  const html = `
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; color: #475569;">
      <div style="border-bottom: 3px solid #1e3a5f; padding-bottom: 16px; margin-bottom: 24px;">
        <h1 style="color: #1e3a5f; font-size: 22px; margin: 0;">Richmond Commons</h1>
      </div>

      <p style="font-size: 16px; line-height: 1.6;">${greeting}</p>

      <p style="font-size: 16px; line-height: 1.6;">
        Here's what happened at the <strong>${meetingType}</strong> on <strong>${meetingDate}</strong>.
      </p>

      ${statsLine ? `<p style="font-size: 14px; color: #64748b; margin-bottom: 24px;">${statsLine}</p>` : ''}

      <div style="border-left: 3px solid #e2e8f0; padding-left: 20px; margin-bottom: 24px;">
        ${recapToHtml(recap)}
      </div>

      <div style="text-align: center; margin: 32px 0;">
        <a href="${meetingUrl}" style="display: inline-block; background: #1e3a5f; color: #ffffff; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-size: 15px; font-weight: 600;">
          View full meeting details
        </a>
      </div>

      <p style="font-size: 14px; color: #94a3b8; margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px;">
        You're receiving this because you subscribed at richmondcommons.org.<br/>
        <a href="${manageUrl}" style="color: #94a3b8;">Manage preferences</a> · <a href="${unsubscribeUrl}" style="color: #94a3b8;">Unsubscribe</a>
      </p>
    </div>
  `

  const text = `${greeting}

Here's what happened at the ${meetingType} on ${meetingDate}.

${statsLine ? statsLine + '\n\n' : ''}${recap}

View full meeting details: ${meetingUrl}

---
You're receiving this because you subscribed at richmondcommons.org.
Manage preferences: ${manageUrl}
Unsubscribe: ${unsubscribeUrl}`

  return { subject, html, text }
}

// ─── Weekly Digest Email ────────────────────────────────────

interface DigestMeetingSummary {
  meetingDate: string
  meetingType: string
  meetingId: string
  recap: string
  itemCount: number
}

/** Build a weekly digest email covering multiple meetings. */
export function buildDigestEmail(
  meetings: DigestMeetingSummary[],
  weekLabel: string,
  subscriberName: string | null,
  unsubscribeUrl: string,
  manageUrl: string,
): { subject: string; html: string; text: string } {
  const greeting = subscriberName ? `Hi ${subscriberName},` : 'Hi,'
  const subject = `Your Richmond briefing — ${weekLabel}`

  const meetingSectionsHtml = meetings.map((m) => {
    const meetingUrl = `https://richmondcommons.org/meetings/${m.meetingId}`
    return `
      <div style="margin-bottom: 28px;">
        <h2 style="color: #1e3a5f; font-size: 17px; margin-bottom: 4px;">
          <a href="${meetingUrl}" style="color: #1e3a5f; text-decoration: none;">${m.meetingType} — ${m.meetingDate}</a>
        </h2>
        ${m.itemCount > 0 ? `<p style="font-size: 13px; color: #64748b; margin: 0 0 12px 0;">${m.itemCount} agenda item${m.itemCount !== 1 ? 's' : ''}</p>` : ''}
        <div style="border-left: 3px solid #e2e8f0; padding-left: 16px;">
          ${recapToHtml(m.recap)}
        </div>
      </div>
    `
  }).join('\n')

  const meetingSectionsText = meetings.map((m) => {
    const meetingUrl = `https://richmondcommons.org/meetings/${m.meetingId}`
    return `## ${m.meetingType} — ${m.meetingDate}\n${m.itemCount > 0 ? `${m.itemCount} agenda items\n` : ''}\n${m.recap}\n\nFull details: ${meetingUrl}`
  }).join('\n\n---\n\n')

  const html = `
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 600px; margin: 0 auto; color: #475569;">
      <div style="border-bottom: 3px solid #1e3a5f; padding-bottom: 16px; margin-bottom: 24px;">
        <h1 style="color: #1e3a5f; font-size: 22px; margin: 0;">Richmond Commons</h1>
        <p style="font-size: 14px; color: #64748b; margin: 4px 0 0 0;">Weekly Briefing — ${weekLabel}</p>
      </div>

      <p style="font-size: 16px; line-height: 1.6;">${greeting}</p>

      <p style="font-size: 16px; line-height: 1.6;">
        Here's what happened in Richmond city government this week.
      </p>

      ${meetingSectionsHtml}

      <div style="text-align: center; margin: 32px 0;">
        <a href="https://richmondcommons.org/meetings" style="display: inline-block; background: #1e3a5f; color: #ffffff; padding: 12px 28px; text-decoration: none; border-radius: 6px; font-size: 15px; font-weight: 600;">
          Browse all meetings
        </a>
      </div>

      <p style="font-size: 14px; color: #94a3b8; margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px;">
        You're receiving this because you subscribed at richmondcommons.org.<br/>
        <a href="${manageUrl}" style="color: #94a3b8;">Manage preferences</a> · <a href="${unsubscribeUrl}" style="color: #94a3b8;">Unsubscribe</a>
      </p>
    </div>
  `

  const text = `${greeting}

Here's what happened in Richmond city government this week.

${meetingSectionsText}

---
Browse all meetings: https://richmondcommons.org/meetings

You're receiving this because you subscribed at richmondcommons.org.
Manage preferences: ${manageUrl}
Unsubscribe: ${unsubscribeUrl}`

  return { subject, html, text }
}

/** Welcome email sent on new subscription. */
export function buildWelcomeEmail(name: string | null, unsubscribeUrl: string): { subject: string; html: string; text: string } {
  const greeting = name ? `Hi ${name},` : 'Hi,'
  const subject = 'Welcome to Richmond Commons'

  const html = `
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; color: #475569;">
      <div style="border-bottom: 3px solid #1e3a5f; padding-bottom: 16px; margin-bottom: 24px;">
        <h1 style="color: #1e3a5f; font-size: 22px; margin: 0;">Richmond Commons</h1>
      </div>

      <p style="font-size: 16px; line-height: 1.6;">${greeting}</p>

      <p style="font-size: 16px; line-height: 1.6;">
        You're signed up for updates from Richmond Commons. Before and after each City Council meeting,
        we'll send you a plain-language briefing on what's being decided and what happened.
      </p>

      <p style="font-size: 16px; line-height: 1.6;">
        There's already a lot to explore. The platform has over 800 meetings going back to 2005 — every agenda item, every vote, and thousands of public comments, all searchable.
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
        <li><a href="https://richmondcommons.org/meetings" style="color: #2d5a8e;">Meetings</a> — agenda items, votes, and public comments</li>
        <li><a href="https://richmondcommons.org/council" style="color: #2d5a8e;">Council profiles</a> — voting records and campaign finance</li>
        <li><a href="https://richmondcommons.org/elections" style="color: #2d5a8e;">Elections</a> — candidates and fundraising for the June primary</li>
      </ul>

      <p style="font-size: 14px; color: #94a3b8; margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px;">
        You're receiving this because you signed up at richmondcommons.org.<br/>
        <a href="${unsubscribeUrl}" style="color: #94a3b8;">Unsubscribe</a>
      </p>
    </div>
  `

  const text = `${greeting}

You're signed up for updates from Richmond Commons. Before and after each City Council meeting, we'll send you a plain-language briefing on what's being decided and what happened.

There's already a lot to explore. The platform has over 800 meetings going back to 2005 — every agenda item, every vote, and thousands of public comments, all searchable.

Try searching for things like:
- Chevron community benefits agreement: https://richmondcommons.org/search?q=Chevron+community+benefits+agreement
- rent control exemptions: https://richmondcommons.org/search?q=rent+control+exemptions
- Point Molate development: https://richmondcommons.org/search?q=Point+Molate+development
- police oversight use of force: https://richmondcommons.org/search?q=police+oversight+use+of+force

Or browse by section:
- Meetings: https://richmondcommons.org/meetings
- Council profiles: https://richmondcommons.org/council
- Elections: https://richmondcommons.org/elections
---
You're receiving this because you signed up at richmondcommons.org.
Unsubscribe: ${unsubscribeUrl}`

  return { subject, html, text }
}
