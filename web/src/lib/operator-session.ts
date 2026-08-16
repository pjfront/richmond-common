import type { SessionOptions } from 'iron-session'

export interface OperatorSession {
  isOperator: boolean
  loginAt: number
}

// Resolved at request time (NOT at module load) so `next build` doesn't
// crash when IRON_SESSION_PASSWORD isn't present. iron-session itself
// will throw on a bad/missing password at first use.
const DEV_FALLBACK = 'dev-only-password-must-be-at-least-32-chars-long-xxxx'

export function getOperatorSessionOptions(): SessionOptions {
  const password = process.env.IRON_SESSION_PASSWORD
  if (!password && process.env.NODE_ENV === 'production') {
    throw new Error(
      'IRON_SESSION_PASSWORD is required in production; refusing to use the development fallback.',
    )
  }
  return {
    password: password || DEV_FALLBACK,
    cookieName: 'rtp_operator',
    cookieOptions: {
      httpOnly: true,
      secure: process.env.NODE_ENV === 'production',
      sameSite: 'strict',
      path: '/',
      maxAge: 60 * 60 * 24 * 30,
    },
  }
}
