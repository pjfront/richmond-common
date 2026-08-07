/**
 * Fail closed when a Vercel Preview deployment can see production resources.
 *
 * Vercel environment-variable scopes live in the project control plane, not
 * in vercel.json. This build guard is the repository-enforced backstop: an
 * accidental Preview scope change fails before Vercel publishes runnable API
 * routes with production credentials.
 */

const PRODUCTION_SUPABASE_HOST = 'ahrwvmizzykyyfavdvfv.supabase.co'

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
if (publicSupabaseUrl) {
  try {
    if (new URL(publicSupabaseUrl).hostname === PRODUCTION_SUPABASE_HOST) {
      violations.push('NEXT_PUBLIC_SUPABASE_URL (production project)')
    }
  } catch {
    violations.push('NEXT_PUBLIC_SUPABASE_URL (invalid URL)')
  }
}

if (violations.length > 0) {
  console.error('Preview deployment blocked: production-capable environment variables are in scope:')
  for (const violation of violations) console.error(`  - ${violation}`)
  console.error(
    'Remove these values from the Vercel Preview scope. Preview deployments may use a separate non-production Supabase project and its public anon key only.',
  )
  process.exit(1)
}

console.log('Preview environment guard passed: no production credentials or production Supabase URL detected.')
