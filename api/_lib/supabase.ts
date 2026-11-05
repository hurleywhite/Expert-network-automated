import { createClient, type SupabaseClient } from '@supabase/supabase-js';

/**
 * Thrown when the function is deployed without its Supabase environment.
 * Handlers surface this as a 503 with the variable names, which are not
 * secrets — only their values are. Without this, a missing variable reads as a
 * generic 500 and the cause is invisible outside the Vercel function logs.
 */
export class ConfigError extends Error {
  statusCode = 503;
  constructor(message: string) {
    super(message);
    this.name = 'ConfigError';
  }
}

let cached: SupabaseClient | null = null;

/**
 * Server-side Supabase client using the SERVICE ROLE key.
 *
 * This key bypasses row-level security and must never reach the browser.
 * It is read at call time rather than module load so that a misconfigured
 * deploy produces a clean error from the handler instead of a cold-start
 * crash with no useful message.
 */
export function getSupabaseAdmin(): SupabaseClient {
  if (cached) return cached;

  const url = process.env.SUPABASE_URL || '';
  const key = process.env.SUPABASE_SERVICE_ROLE_KEY || '';

  const missing = [
    !url && 'SUPABASE_URL',
    !key && 'SUPABASE_SERVICE_ROLE_KEY',
  ].filter(Boolean);

  if (missing.length) {
    throw new ConfigError(
      `Supabase is not configured: missing ${missing.join(' and ')}. ` +
        'Set these in the Vercel project settings, then redeploy. See SETUP.md.',
    );
  }

  cached = createClient(url, key, {
    auth: { persistSession: false, autoRefreshToken: false },
  });
  return cached;
}
