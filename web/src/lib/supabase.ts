import { createClient, SupabaseClient } from '@supabase/supabase-js'

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

let _client: SupabaseClient | null = null

function getClient(): SupabaseClient {
  if (_client) return _client
  if (!supabaseUrl || !supabaseAnonKey) {
    throw new Error(
      'Missing Supabase environment variables. ' +
      'Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.'
    )
  }
  _client = createClient(supabaseUrl, supabaseAnonKey)
  return _client
}

/**
 * Lazy-initialized Supabase client.
 * Uses a Proxy so that importing this module doesn't throw —
 * the error only happens when you actually call a method (e.g. supabase.from()).
 * This unblocks local dev without env vars for layout/component verification.
 */
export const supabase: SupabaseClient = new Proxy({} as SupabaseClient, {
  get(_target, prop) {
    const client = getClient()
    const value = Reflect.get(client, prop)
    if (typeof value === 'function') {
      return value.bind(client)
    }
    return value
  },
})
