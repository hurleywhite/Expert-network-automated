import type { VercelRequest, VercelResponse } from '@vercel/node';
import { getSupabaseAdmin, ConfigError } from './_lib/supabase';

/**
 * Health check, and the target of the daily cron in vercel.json.
 *
 * It serves two purposes:
 *
 *  1. Diagnosis. It reports which environment variables are present and
 *     whether the database actually answers, so a misconfigured deploy can be
 *     told apart from a broken one without reading the function logs.
 *
 *  2. Keeping the database awake. Free-tier Supabase projects pause after
 *     about a week with no activity, which is what took the previous backend
 *     down. A daily query is enough to stop that happening again.
 *
 * It reports only whether a variable is SET, never its value.
 */

const REQUIRED = ['SUPABASE_URL', 'SUPABASE_SERVICE_ROLE_KEY'] as const;
const OPTIONAL = ['OPENAI_API_KEY', 'OPENAI_MODEL', 'APOLLO_API_KEY', 'EXA_API_KEY', 'HEYREACH_API_KEY'] as const;

export default async function handler(req: VercelRequest, res: VercelResponse) {
  // Vercel cron invocations carry this header when CRON_SECRET is configured.
  // If the secret is set we require it; if it isn't, the route stays open
  // (it is read-only and behind Vercel's deployment protection).
  const cronSecret = process.env.CRON_SECRET;
  if (cronSecret && req.headers['user-agent']?.includes('vercel-cron')) {
    if (req.headers.authorization !== `Bearer ${cronSecret}`) {
      return res.status(401).json({ error: 'Unauthorized' });
    }
  }

  const env: Record<string, boolean> = {};
  for (const k of [...REQUIRED, ...OPTIONAL]) env[k] = Boolean(process.env[k]);

  const missingRequired = REQUIRED.filter((k) => !process.env[k]);

  if (missingRequired.length) {
    return res.status(503).json({
      status: 'misconfigured',
      error: `Missing ${missingRequired.join(' and ')}. Set these in the Vercel project settings, then redeploy. See SETUP.md.`,
      env,
    });
  }

  // Probe the REST gateway directly first. supabase-js collapses "wrong host",
  // "paused project" and "bad key" into one opaque failure, and those need
  // three different fixes, so distinguish them by HTTP status before querying.
  const supabaseUrl = process.env.SUPABASE_URL as string;
  let host = '';
  try {
    host = new URL(supabaseUrl).host;
  } catch {
    return res.status(503).json({
      status: 'misconfigured',
      error: `SUPABASE_URL is not a valid URL. It should look like https://<project-ref>.supabase.co`,
      env,
    });
  }

  let gatewayStatus: number | null = null;
  try {
    const probe = await fetch(`${supabaseUrl.replace(/\/$/, '')}/rest/v1/`, {
      method: 'GET',
      headers: { apikey: process.env.SUPABASE_SERVICE_ROLE_KEY as string },
    });
    gatewayStatus = probe.status;
  } catch {
    // Could not connect at all: the project behind this URL is gone or asleep.
    return res.status(503).json({
      status: 'database-unreachable',
      error:
        `Nothing is answering at ${host}. That Supabase project has been deleted, or is paused. ` +
        'If you created a new project, SUPABASE_URL still points at the old one.',
      supabase_host: host,
      env,
      checked_at: new Date().toISOString(),
    });
  }

  if (gatewayStatus === 401 || gatewayStatus === 403) {
    return res.status(503).json({
      status: 'bad-key',
      error:
        `${host} is reachable but rejected the key. SUPABASE_SERVICE_ROLE_KEY does not belong to ` +
        'this project — copy the service_role key from this project\'s Settings → API.',
      supabase_host: host,
      env,
      checked_at: new Date().toISOString(),
    });
  }

  const startedAt = Date.now();
  try {
    const supabase = getSupabaseAdmin();

    // Cheapest possible round trip that still proves the database is awake
    // and the service-role key is accepted: a HEAD count on one small table.
    const { error } = await supabase
      .from('project_briefs')
      .select('id', { count: 'exact', head: true });

    if (error) throw error;

    return res.status(200).json({
      status: 'ok',
      database: 'reachable',
      supabase_host: host,
      latency_ms: Date.now() - startedAt,
      env,
      checked_at: new Date().toISOString(),
    });
  } catch (err: any) {
    if (err instanceof ConfigError) {
      return res.status(503).json({ status: 'misconfigured', error: err.message, env });
    }

    console.error('[api/health] database check failed:', err);

    // PGRST205 = table missing: the schema has not been applied yet. That is a
    // setup state worth naming rather than a generic failure.
    const schemaMissing = err?.code === 'PGRST205' || /does not exist/i.test(err?.message || '');

    return res.status(503).json({
      status: schemaMissing ? 'schema-missing' : 'database-unreachable',
      error: schemaMissing
        ? `Connected to ${host} and the key works, but the tables are missing. ` +
          'Apply db/supabase_schema.sql in that project\'s SQL Editor.'
        : `Connected to ${host} but the query failed.`,
      supabase_host: host,
      env,
      checked_at: new Date().toISOString(),
    });
  }
}
