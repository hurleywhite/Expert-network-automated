#!/usr/bin/env node
/**
 * Verifies that the Supabase backend is correctly provisioned and locked down.
 *
 *   SUPABASE_URL=... SUPABASE_SERVICE_ROLE_KEY=... node scripts/verify-setup.mjs
 *
 * Optional:
 *   SUPABASE_ANON_KEY=...   also asserts the browser-facing role is denied
 *   DEPLOY_URL=https://...  also probes the live /api/data endpoint
 *
 * Exits non-zero if anything is wrong, so it is safe to use in CI.
 */
import { createClient } from '@supabase/supabase-js';

const TABLES = [
  'project_briefs',
  'candidates',
  'project_categories',
  'screener_questions',
  'expert_profiles',
  'expert_activities',
  'linkedin_outreach',
  'outreach_campaigns',
  'outreach_leads',
  'message_drafts',
  'rejection_learnings',
];

const url = process.env.SUPABASE_URL;
const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
const anonKey = process.env.SUPABASE_ANON_KEY;
const deployUrl = process.env.DEPLOY_URL;

let failures = 0;
const ok = (m) => console.log(`  \x1b[32mPASS\x1b[0m  ${m}`);
const bad = (m) => { failures++; console.log(`  \x1b[31mFAIL\x1b[0m  ${m}`); };
const info = (m) => console.log(`\n\x1b[1m${m}\x1b[0m`);

if (!url || !serviceKey) {
  console.error('SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY must be set.');
  process.exit(2);
}

info('1. Service-role connection and schema');
const admin = createClient(url, serviceKey, { auth: { persistSession: false } });

for (const table of TABLES) {
  const { error } = await admin.from(table).select('*', { count: 'exact', head: true });
  if (error) bad(`${table} — ${error.message}`);
  else ok(`${table} is present and readable`);
}

info('2. Foreign keys / nested selects (what the app actually queries)');
{
  const { error } = await admin
    .from('expert_profiles')
    .select('id, candidates!inner(full_name), project_categories(id,name)')
    .limit(1);
  if (error) bad(`expert_profiles -> candidates/project_categories join — ${error.message}`);
  else ok('expert_profiles joins to candidates and project_categories');
}
{
  const { error } = await admin
    .from('linkedin_outreach')
    .select('id, expert_profiles!inner(id, candidates!inner(full_name))')
    .limit(1);
  if (error) bad(`linkedin_outreach -> expert_profiles -> candidates join — ${error.message}`);
  else ok('linkedin_outreach joins through expert_profiles to candidates');
}

info('3. Row-level security (the browser-facing role must be denied)');
if (!anonKey) {
  console.log('  SKIP  set SUPABASE_ANON_KEY to verify the lockdown');
} else {
  const anon = createClient(url, anonKey, { auth: { persistSession: false } });
  let leaked = [];
  for (const table of TABLES) {
    const { data, error } = await anon.from(table).select('*').limit(1);
    // Denied is the goal: either an explicit error, or RLS filtering to nothing.
    if (!error && Array.isArray(data) && data.length > 0) leaked.push(table);
  }
  if (leaked.length) bad(`anon key can still read rows from: ${leaked.join(', ')}`);
  else ok('anon key is denied on every table');

  const { error: writeErr } = await anon
    .from('candidates')
    .insert({ full_name: '__rls_probe__' });
  if (!writeErr) bad('anon key was able to INSERT — RLS is not enforced');
  else ok('anon key cannot write');
}

info('4. Live deployment');
if (!deployUrl) {
  console.log('  SKIP  set DEPLOY_URL to probe the deployed API');
} else {
  try {
    const res = await fetch(`${deployUrl.replace(/\/$/, '')}/api/data/projects`);
    const text = await res.text();
    if (res.ok) {
      const parsed = JSON.parse(text);
      ok(`GET /api/data/projects -> 200 (${Array.isArray(parsed) ? parsed.length : '?'} projects)`);
    } else if (res.status === 401 && text.includes('Authentication Required')) {
      console.log('  SKIP  deployment is behind Vercel SSO; probe it from a browser instead');
    } else {
      bad(`GET /api/data/projects -> ${res.status}: ${text.slice(0, 200)}`);
    }
  } catch (e) {
    bad(`could not reach ${deployUrl}: ${e.message}`);
  }
}

console.log(
  failures === 0
    ? '\n\x1b[32mAll checks passed.\x1b[0m\n'
    : `\n\x1b[31m${failures} check(s) failed.\x1b[0m\n`,
);
process.exit(failures === 0 ? 0 : 1);
