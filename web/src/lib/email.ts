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
        In the meantime, you can explore what's already on the platform:
      </p>

      <ul style="font-size: 15px; line-height: 1.8; padding-left: 20px;">
        <li><a href="https://richmondcommons.org/meetings" style="color: #2d5a8e;">Recent meetings</a> — agenda items, votes, and public comments</li>
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

Explore the platform:
- Recent meetings: https://richmondcommons.org/meetings
- Council profiles: https://richmondcommons.org/council
- Elections: https://richmondcommons.org/elections

---
You're receiving this because you signed up at richmondcommons.org.
Unsubscribe: ${unsubscribeUrl}`

  return { subject, html, text }
}
