import type { VercelRequest, VercelResponse } from '@vercel/node';
import { createHash } from 'crypto';
import { getSupabaseAdmin, ConfigError } from './_lib/supabase';
import { qualify, type ScreenerQuestion } from './_lib/qualify';

/**
 * The public screener. This is the only endpoint reachable without a session,
 * because its whole purpose is to be opened by strangers who followed a link
 * from a Reddit post or an email.
 *
 *   GET  /api/screener?project_id=<uuid>   -> the questions to render
 *   POST /api/screener                     -> submit answers, get a verdict
 *
 * It deliberately exposes nothing but what a respondent must see: the project
 * name, intro, incentive and questions. No candidate records, no counts, no
 * campaign detail. The qualifying/disqualifying rules are stripped from the
 * payload too — publishing them would tell people exactly what to answer.
 */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const MAX_ANSWER_CHARS = 4000;

function fingerprint(req: VercelRequest): string {
  // Hashed, never stored raw: enough to spot duplicates and floods without
  // keeping an identifier for people who may not end up participating.
  const ip = String(req.headers['x-forwarded-for'] || '').split(',')[0].trim();
  const ua = String(req.headers['user-agent'] || '');
  return createHash('sha256').update(`${ip}|${ua}`).digest('hex').slice(0, 32);
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  // Never let a shared cache hold a screener response.
  res.setHeader('Cache-Control', 'no-store, max-age=0');

  try {
    if (req.method === 'GET') return await getScreener(req, res);
    if (req.method === 'POST') return await submit(req, res);
    return res.status(405).json({ error: 'Method not allowed' });
  } catch (err: any) {
    if (err?.name === 'ConfigError') return res.status(503).json({ error: err.message });
    console.error('[api/screener]', err);
    return res.status(500).json({ error: 'Something went wrong. Please try again.' });
  }
}

async function getScreener(req: VercelRequest, res: VercelResponse) {
  const projectId = String(req.query.project_id || '');
  if (!UUID_RE.test(projectId)) return res.status(400).json({ error: 'Invalid screener link.' });

  const supabase = getSupabaseAdmin();

  const [{ data: project, error: pErr }, { data: questions, error: qErr }] = await Promise.all([
    supabase
      .from('project_briefs')
      .select('id, name, screener_intro, incentive_text, scheduling_url')
      .eq('id', projectId)
      .maybeSingle(),
    supabase
      .from('screener_questions')
      .select('id, question_text, question_type, options, is_required, help_text')
      .eq('project_id', projectId)
      .order('sort_order'),
  ]);

  if (pErr) throw pErr;
  if (qErr) throw qErr;
  if (!project) return res.status(404).json({ error: 'This screener is no longer available.' });

  return res.status(200).json({
    project: {
      id: project.id,
      name: project.name,
      intro: project.screener_intro,
      incentive: project.incentive_text,
    },
    // Note: qualifying/disqualifying answers are intentionally not returned.
    questions: questions || [],
  });
}

async function submit(req: VercelRequest, res: VercelResponse) {
  const body = typeof req.body === 'string' ? safeParse(req.body) : req.body || {};
  const { project_id, answers, full_name, email, phone, consent, source_channel, source_detail } = body;

  if (!UUID_RE.test(String(project_id || ''))) {
    return res.status(400).json({ error: 'Invalid screener link.' });
  }
  if (!consent) {
    return res.status(400).json({ error: 'Please confirm you consent to be contacted about this study.' });
  }
  if (!email || !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(String(email))) {
    return res.status(400).json({ error: 'Please enter a valid email address so we can reach you.' });
  }

  const supabase = getSupabaseAdmin();

  const { data: project } = await supabase
    .from('project_briefs')
    .select('id, name, scheduling_url')
    .eq('id', project_id)
    .maybeSingle();
  if (!project) return res.status(404).json({ error: 'This screener is no longer available.' });

  const { data: questions, error: qErr } = await supabase
    .from('screener_questions')
    .select('id, question_text, question_type, options, qualifying_answers, disqualifying_answers, is_required')
    .eq('project_id', project_id)
    .order('sort_order');
  if (qErr) throw qErr;

  // Keep only answers to this project's questions, truncated. A public form
  // must not let a submitter choose what gets stored.
  const known = new Set((questions || []).map((q: any) => q.id));
  const clean: Record<string, unknown> = {};
  for (const [k, v] of Object.entries(answers || {})) {
    if (known.has(k)) clean[k] = typeof v === 'string' ? v.slice(0, MAX_ANSWER_CHARS) : v;
  }

  // One submission per email per project: a second one updates the first
  // rather than creating a duplicate someone has to reconcile later.
  const { data: existing } = await supabase
    .from('screener_respondents')
    .select('id')
    .eq('project_id', project_id)
    .ilike('email', String(email))
    .maybeSingle();

  const verdict = await qualify((questions || []) as ScreenerQuestion[], clean);

  const row = {
    project_id,
    answers: clean,
    full_name: full_name ? String(full_name).slice(0, 200) : null,
    email: String(email).slice(0, 320),
    phone: phone ? String(phone).slice(0, 50) : null,
    consent_given: true,
    source_channel: source_channel ? String(source_channel).slice(0, 50) : 'direct',
    source_detail: source_detail ? String(source_detail).slice(0, 200) : null,
    status: verdict.qualified ? 'qualified' : 'disqualified',
    qualification_score: verdict.score,
    qualification_reasons: verdict.reasons,
    submitter_fingerprint: fingerprint(req),
    updated_at: new Date().toISOString(),
  };

  if (existing) {
    const { error } = await supabase.from('screener_respondents').update(row).eq('id', existing.id);
    if (error) throw error;
  } else {
    const { error } = await supabase.from('screener_respondents').insert(row);
    if (error) throw error;
  }

  // Only a qualified respondent is sent to the calendar.
  return res.status(200).json({
    qualified: verdict.qualified,
    scheduling_url: verdict.qualified ? project.scheduling_url || null : null,
    message: verdict.qualified
      ? 'You qualify for this study.'
      : "Thank you — based on your answers you aren't a fit for this particular study.",
  });
}

function safeParse(s: string): any {
  try {
    return JSON.parse(s);
  } catch {
    return {};
  }
}
