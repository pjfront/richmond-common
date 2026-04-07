import { createClient, SupabaseClient } from '@supabase/supabase-js'

/**
 * Service-role Supabase client for server-side API routes that need
 * elevated access (e.g., email_subscribers table with service-role-only RLS).
 *
 * NEVER import this in client components or expose the service role key.
 */

let _adminClient: SupabaseClient | null = null

export function getSupabaseAdmin(): SupabaseClient {
  if (_adminClient) return _adminClient

  const url = process.env.NEXT_PUBLIC_SUPABASE_URL
  const serviceRoleKey = process.env.SUPABASE_SERVICE_ROLE_KEY

  if (!url || !serviceRoleKey) {
    throw new Error(
      'Missing SUPABASE_SERVICE_ROLE_KEY. ' +
      'Set it in .env (never expose in NEXT_PUBLIC_ vars).'
    )
  }

  _adminClient = createClient(url, serviceRoleKey, {
    auth: { persistSession: false },
  })
  return _adminClient
}
