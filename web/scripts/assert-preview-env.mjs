/**
 * Fail closed when a Vercel Preview deployment can see production resources.
 *
 * Vercel environment-variable scopes live in the project control plane, not
 * in vercel.json. This build guard is the repository-enforced backstop: an
 * accidental Preview scope change fails before Vercel publishes runnable API
 * routes with production credentials.
 */

const PRODUCTION_SUPABASE_HOST = 'ahrwvmizzykyyfavdvfv.supabase.co'
const SUPABASE_PROJECT_REF_PATTERN = /^[a-z0-9]{20}$/

const SERVER_ONLY_CREDENTIALS = [
  'AI_GATEWAY_API_KEY',
  'ANTHROPIC_API_KEY',
  'APIFY_API_TOKEN',
  'API_SECRET',
  'CLOUDFLARE_API_TOKEN',
  'CRON_SECRET',
  'DATABASE_URL',
  'DB_BACKUP_PASSPHRASE',
  'DEEPSEEK_API_KEY',
  'DIRECT_URL',
  'DISPATCH_TOKEN',
  'EMAIL_SIGNING_SECRET',
  'IRON_SESSION_PASSWORD',
  'JWT_SECRET',
  'MOONSHOT_API_KEY',
  'OPENAI_API_KEY',
  'OPENCORPORATES_API_TOKEN',
  'OPERATOR_PASSWORD',
  'POSTGRES_URL',
  'RESEND_API_KEY',
  'REVALIDATION_SECRET',
  'SMTP_PASSWORD',
  'SOCRATA_APP_TOKEN',
  'SUPABASE_ANON_KEY',
  'SUPABASE_ACCESS_TOKEN',
  'SUPABASE_DB_PASSWORD',
  'SUPABASE_SECRET_KEY',
  'SUPABASE_SERVICE_KEY',
  'SUPABASE_SERVICE_ROLE_KEY',
  'SUPABASE_URL',
]

if (process.env.VERCEL_ENV !== 'preview') {
  console.log('Preview environment guard: non-preview deployment, no restrictions applied.')
  process.exit(0)
}

const violations = SERVER_ONLY_CREDENTIALS.filter(
  (name) => (process.env[name] ?? '').trim().length > 0,
)

const publicSupabaseUrl = (process.env.NEXT_PUBLIC_SUPABASE_URL ?? '').trim()
const expectedGitBranch = (
  process.env.RICHMOND_PREVIEW_GIT_BRANCH ?? ''
).trim()
const actualGitBranch = (process.env.VERCEL_GIT_COMMIT_REF ?? '').trim()
const expectedSupabaseRef = (
  process.env.RICHMOND_PREVIEW_SUPABASE_REF ?? ''
).trim()

if (!actualGitBranch) {
  violations.push('VERCEL_GIT_COMMIT_REF (missing)')
}
if (!expectedGitBranch) {
  violations.push('RICHMOND_PREVIEW_GIT_BRANCH (missing)')
} else if (actualGitBranch && expectedGitBranch !== actualGitBranch) {
  violations.push('RICHMOND_PREVIEW_GIT_BRANCH (wrong branch scope)')
}
if (!SUPABASE_PROJECT_REF_PATTERN.test(expectedSupabaseRef)) {
  violations.push('RICHMOND_PREVIEW_SUPABASE_REF (missing or invalid)')
}

if (!publicSupabaseUrl) {
  violations.push('NEXT_PUBLIC_SUPABASE_URL (missing)')
} else {
  try {
    const parsedUrl = new URL(publicSupabaseUrl)
    if (parsedUrl.protocol !== 'https:') {
      violations.push('NEXT_PUBLIC_SUPABASE_URL (must use HTTPS)')
    }
    if (parsedUrl.hostname === PRODUCTION_SUPABASE_HOST) {
      violations.push('NEXT_PUBLIC_SUPABASE_URL (production project)')
    }
    if (
      SUPABASE_PROJECT_REF_PATTERN.test(expectedSupabaseRef) &&
      parsedUrl.hostname !== `${expectedSupabaseRef}.supabase.co`
    ) {
      violations.push('NEXT_PUBLIC_SUPABASE_URL (branch ref mismatch)')
    }
  } catch {
    violations.push('NEXT_PUBLIC_SUPABASE_URL (invalid URL)')
  }
}

const publicSupabaseAnonKey = (
  process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY ?? ''
).trim()
if (!publicSupabaseAnonKey) {
  violations.push('NEXT_PUBLIC_SUPABASE_ANON_KEY (missing)')
} else if (!isPublicSupabaseKey(publicSupabaseAnonKey)) {
  violations.push('NEXT_PUBLIC_SUPABASE_ANON_KEY (not a public key)')
}

if (violations.length > 0) {
  console.error('Preview deployment blocked: unsafe or incomplete environment configuration:')
  for (const violation of violations) console.error(`  - ${violation}`)
  console.error(
    'Preview deployments require a separate non-production Supabase URL and public anon or publishable key, with all server-only credentials removed.',
  )
  process.exit(1)
}

console.log('Preview environment guard passed: isolated public Supabase configuration is present and no server-only credentials are in scope.')

function isPublicSupabaseKey(value) {
  if (value.startsWith('sb_publishable_')) return true
  const parts = value.split('.')
  if (parts.length !== 3) return false
  try {
    const payload = JSON.parse(
      Buffer.from(parts[1], 'base64url').toString('utf8'),
    )
    return payload.role === 'anon'
  } catch {
    return false
  }
}
