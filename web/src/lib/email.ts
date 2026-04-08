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
        There's already a lot to explore. The platform has over 800 meetings going back to 2005: every agenda item, every vote, and thousands of public comments, all searchable.
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
        <li><a href="https://richmondcommons.org/elections" style="color: #2d5a8e;">Elections</a>: candidates and fundraising for the June primary</li>
      </ul>

      <p style="font-size: 14px; color: #94a3b8; margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px;">
        You're receiving this because you signed up at richmondcommons.org.<br/>
        <a href="${unsubscribeUrl}" style="color: #94a3b8;">Unsubscribe</a>
      </p>
    </div>
  `

  const text = `${greeting}

You're signed up for updates from Richmond Commons. Before and after each City Council meeting, we'll send you a plain-language briefing on what's being decided and what happened.

There's already a lot to explore. The platform has over 800 meetings going back to 2005: every agenda item, every vote, and thousands of public comments, all searchable.

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

// ─── Shared Email Layout ────────────────────────────────────

/** Shared HTML wrapper: civic-navy header, content slot, footer with AI disclosure + unsubscribe. */
function emailLayout(bodyHtml: string, footerNote: string, unsubscribeUrl: string): string {
  return `
    <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; max-width: 560px; margin: 0 auto; color: #475569;">
      <div style="border-bottom: 3px solid #1e3a5f; padding-bottom: 16px; margin-bottom: 24px;">
        <h1 style="color: #1e3a5f; font-size: 22px; margin: 0;">Richmond Commons</h1>
      </div>
      ${bodyHtml}
      <p style="font-size: 13px; color: #94a3b8; margin-top: 32px; border-top: 1px solid #e2e8f0; padding-top: 16px;">
        ${footerNote}<br/>
        You're receiving this because you subscribed at richmondcommons.org.<br/>
        <a href="${unsubscribeUrl}" style="color: #94a3b8;">Unsubscribe</a>
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

// ─── Meeting Recap Email ────────────────────────────────────

interface RecapMeeting {
  id: string
  meeting_date: string
  meeting_type: string
  meeting_recap: string
  minutes_url: string | null
}

/** Build a meeting recap email from an existing meeting_recap narrative. */
export function buildRecapEmail(
  meeting: RecapMeeting,
  unsubscribeUrl: string,
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

  const footerNote = 'This recap was auto-generated from official minutes and vote records.'

  const html = emailLayout(bodyHtml, footerNote, unsubscribeUrl)

  const text = `${subject}\n\n${markdownToPlain(meeting.meeting_recap)}\n\nView full meeting details: ${meetingUrl}\n\n---\n${footerNote}\nYou're receiving this because you subscribed at richmondcommons.org.\nUnsubscribe: ${unsubscribeUrl}`

  return { subject, html, text }
}

// ─── Weekly Digest Email ────────────────────────────────────

/** Build a weekly digest email summarizing recent meetings. */
export function buildDigestEmail(
  meetings: RecapMeeting[],
  unsubscribeUrl: string,
): { subject: string; html: string; text: string } {
  const count = meetings.length
  const subject = `This week in Richmond: ${count} meeting${count === 1 ? '' : 's'}`

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

  const footerNote = 'Recaps are auto-generated from official minutes and vote records.'
  const html = emailLayout(sectionsHtml, footerNote, unsubscribeUrl)

  const textSections = meetings.map((m) => {
    const date = new Date(m.meeting_date + 'T12:00:00')
    const formatted = date.toLocaleDateString('en-US', { weekday: 'long', month: 'long', day: 'numeric' })
    const meetingUrl = `https://richmondcommons.org/meetings/${m.id}`
    const preview = m.meeting_recap.split('\n\n').filter(Boolean).slice(0, 2).join('\n\n')
    return `${formatted}\n\n${markdownToPlain(preview)}\n\nRead the full recap: ${meetingUrl}`
  }).join('\n\n---\n\n')

  const text = `${subject}\n\n${textSections}\n\n---\n${footerNote}\nYou're receiving this because you subscribed at richmondcommons.org.\nUnsubscribe: ${unsubscribeUrl}`

  return { subject, html, text }
}
