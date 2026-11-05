import { getSupabaseAdmin } from './supabase';

/**
 * All database access for the app lives here and runs server-side only.
 *
 * Previously the browser held a Supabase anon key and issued these queries
 * directly, which published every candidate name, email and LinkedIn URL to
 * anyone who loaded the page. These are faithful ports of those queries.
 */

// ─── helpers ────────────────────────────────────────────────────────────────

const CANDIDATE_FIELDS = `
  full_name,
  title,
  company,
  region,
  linkedin_url,
  headline,
  photo_url,
  email
`;

function num(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null;
  const n = typeof v === 'number' ? v : parseFloat(String(v));
  return Number.isFinite(n) ? n : null;
}

// ─── projects ───────────────────────────────────────────────────────────────

export async function listProjects() {
  const supabase = getSupabaseAdmin();
  const { data, error } = await supabase
    .from('project_briefs')
    .select('*')
    .order('created_at', { ascending: false });
  if (error) throw error;
  return data || [];
}

export async function getProject(id: string) {
  const supabase = getSupabaseAdmin();
  const { data, error } = await supabase
    .from('project_briefs')
    .select('*')
    .eq('id', id)
    .single();
  if (error) throw error;
  return data;
}

// ─── categories ─────────────────────────────────────────────────────────────

/**
 * Categories for a project, each with the number of experts assigned to it.
 *
 * The original client ran one COUNT query per category (N+1). This fetches the
 * project's category_id column once and tallies in memory — a single round trip
 * regardless of how many categories the project has.
 */
export async function listCategories(projectId: string) {
  const supabase = getSupabaseAdmin();

  const [{ data: cats, error: catErr }, { data: profiles, error: profErr }] = await Promise.all([
    supabase
      .from('project_categories')
      .select('*')
      .eq('project_id', projectId)
      .order('sort_order'),
    supabase
      .from('expert_profiles')
      .select('category_id')
      .eq('project_id', projectId),
  ]);

  if (catErr) throw catErr;
  if (profErr) throw profErr;

  const counts = new Map<string, number>();
  for (const row of profiles || []) {
    const cid = (row as { category_id: string | null }).category_id;
    if (cid) counts.set(cid, (counts.get(cid) || 0) + 1);
  }

  return (cats || []).map((c) => ({ ...c, expert_count: counts.get(c.id) || 0 }));
}

// ─── screener questions ─────────────────────────────────────────────────────

export async function listScreenerQuestions(projectId: string) {
  const supabase = getSupabaseAdmin();
  const { data, error } = await supabase
    .from('screener_questions')
    .select('*')
    .eq('project_id', projectId)
    .order('sort_order');
  if (error) throw error;
  return data || [];
}

// ─── experts ────────────────────────────────────────────────────────────────

export async function listExperts(projectId: string, categoryId?: string) {
  const supabase = getSupabaseAdmin();

  let query = supabase
    .from('expert_profiles')
    .select(`
      id,
      candidate_id,
      relevance_score,
      rate_per_hour,
      status,
      ai_overview,
      project_expertise,
      category_id,
      candidates!inner ( ${CANDIDATE_FIELDS} ),
      project_categories ( id, name )
    `)
    .eq('project_id', projectId);

  if (categoryId) query = query.eq('category_id', categoryId);

  const { data, error } = await query.order('relevance_score', {
    ascending: false,
    nullsFirst: false,
  });
  if (error) throw error;

  const experts = (data || []).map((row: any) => ({
    id: row.id,
    candidate_id: row.candidate_id,
    full_name: row.candidates?.full_name || '',
    title: row.candidates?.title ?? null,
    company: row.candidates?.company ?? null,
    region: row.candidates?.region ?? null,
    linkedin_url: row.candidates?.linkedin_url ?? null,
    headline: row.candidates?.headline ?? null,
    photo_url: row.candidates?.photo_url ?? null,
    email: row.candidates?.email ?? null,
    rate_per_hour: num(row.rate_per_hour),
    relevance_score: row.relevance_score,
    status: row.status,
    category: row.project_categories
      ? { id: row.project_categories.id, name: row.project_categories.name }
      : null,
    ai_overview_snippet: row.ai_overview ? row.ai_overview.substring(0, 200) + '...' : null,
    project_expertise: row.project_expertise || [],
    activity_count: 0,
  }));

  return { project_id: projectId, total: experts.length, experts };
}

export async function getExpertProfile(expertId: string) {
  const supabase = getSupabaseAdmin();

  const { data, error } = await supabase
    .from('expert_profiles')
    .select(`
      *,
      candidates!inner ( ${CANDIDATE_FIELDS} ),
      project_categories ( id, name ),
      expert_activities ( id, activity_type, description, created_at ),
      linkedin_outreach ( status, connection_note, sent_at )
    `)
    .eq('id', expertId)
    .single();

  if (error) throw error;
  const row = data as any;

  return {
    id: row.id,
    candidate_id: row.candidate_id,
    full_name: row.candidates?.full_name || '',
    title: row.candidates?.title ?? null,
    company: row.candidates?.company ?? null,
    region: row.candidates?.region ?? null,
    linkedin_url: row.candidates?.linkedin_url ?? null,
    headline: row.candidates?.headline ?? null,
    photo_url: row.candidates?.photo_url ?? null,
    email: row.candidates?.email ?? null,
    rate_per_hour: num(row.rate_per_hour),
    relevance_score: row.relevance_score,
    status: row.status,
    category: row.project_categories
      ? { id: row.project_categories.id, name: row.project_categories.name }
      : null,
    ai_overview: row.ai_overview,
    project_expertise: row.project_expertise || [],
    work_experience: row.work_experience || [],
    screener_responses: row.screener_responses || {},
    exa_research: row.exa_research || {},
    activities: (row.expert_activities || []).map((a: any) => ({
      id: a.id,
      type: a.activity_type,
      description: a.description,
      created_at: a.created_at,
    })),
    linkedin_outreach: row.linkedin_outreach?.[0]
      ? {
          status: row.linkedin_outreach[0].status,
          connection_note: row.linkedin_outreach[0].connection_note,
          sent_at: row.linkedin_outreach[0].sent_at,
        }
      : null,
    created_at: row.created_at,
  };
}

const EXPERT_STATUSES = new Set([
  'sourced', 'screened', 'shortlisted', 'scheduled', 'completed', 'rejected',
]);

export async function updateExpertStatus(expertId: string, status: string) {
  if (!EXPERT_STATUSES.has(status)) {
    const allowed = [...EXPERT_STATUSES].join(', ');
    throw Object.assign(new Error(`Invalid status "${status}". Allowed: ${allowed}`), { statusCode: 400 });
  }

  const supabase = getSupabaseAdmin();
  const { error } = await supabase
    .from('expert_profiles')
    .update({ status, updated_at: new Date().toISOString() })
    .eq('id', expertId);
  if (error) throw error;
  return { status: 'ok' };
}

export async function scheduleCall(expertId: string) {
  const supabase = getSupabaseAdmin();

  const { error: actErr } = await supabase.from('expert_activities').insert({
    expert_profile_id: expertId,
    activity_type: 'call_requested',
    description: 'Call requested via expert profile page',
  });
  if (actErr) throw actErr;

  const { error: updErr } = await supabase
    .from('expert_profiles')
    .update({ status: 'scheduled', updated_at: new Date().toISOString() })
    .eq('id', expertId);
  if (updErr) throw updErr;

  return { status: 'ok' };
}

// ─── linkedin outreach ──────────────────────────────────────────────────────

export async function getOutreachStatus(projectId: string) {
  const supabase = getSupabaseAdmin();

  const { data, error } = await supabase
    .from('linkedin_outreach')
    .select(`
      id,
      linkedin_url,
      connection_note,
      follow_up_message,
      status,
      sent_at,
      connected_at,
      replied_at,
      error_message,
      expert_profiles!inner (
        id,
        candidates!inner ( full_name, title, company )
      )
    `)
    .eq('expert_profiles.project_id', projectId);

  if (error) throw error;

  const outreach = (data || []).map((row: any) => ({
    id: row.id,
    expert_id: row.expert_profiles?.id || '',
    full_name: row.expert_profiles?.candidates?.full_name || '',
    title: row.expert_profiles?.candidates?.title ?? null,
    company: row.expert_profiles?.candidates?.company ?? null,
    linkedin_url: row.linkedin_url,
    connection_note: row.connection_note || '',
    follow_up_message: row.follow_up_message || '',
    status: row.status,
    sent_at: row.sent_at,
    connected_at: row.connected_at,
    error_message: row.error_message,
  }));

  const status_breakdown: Record<string, number> = {};
  for (const item of outreach) {
    status_breakdown[item.status] = (status_breakdown[item.status] || 0) + 1;
  }

  return { project_id: projectId, total: outreach.length, status_breakdown, outreach };
}

// ─── outreach campaigns ─────────────────────────────────────────────────────

export async function listCampaigns(projectId: string) {
  const supabase = getSupabaseAdmin();
  const { data, error } = await supabase
    .from('outreach_campaigns')
    .select('*')
    .eq('project_id', projectId)
    .order('created_at', { ascending: false });
  if (error) throw error;
  return data || [];
}

// ─── drafts ─────────────────────────────────────────────────────────────────

export async function approveDraft(draftId: string, approvedBy: string) {
  const supabase = getSupabaseAdmin();
  const { data, error } = await supabase
    .from('message_drafts')
    .update({ approved_at: new Date().toISOString(), approved_by: approvedBy })
    .eq('id', draftId)
    .select()
    .single();
  if (error) throw error;
  return data;
}

export async function rejectDraft(draftId: string, rejectedBy: string, reason?: string) {
  const supabase = getSupabaseAdmin();

  const { data: draft, error: fetchErr } = await supabase
    .from('message_drafts')
    .select('project_id, subject, body')
    .eq('id', draftId)
    .single();

  // A draft that is already gone is not an error worth failing the request over,
  // but any other lookup failure is.
  if (fetchErr && fetchErr.code !== 'PGRST116') throw fetchErr;

  if (draft) {
    const { error: learnErr } = await supabase.from('rejection_learnings').insert({
      project_id: draft.project_id,
      rejected_subject: draft.subject,
      rejected_body: draft.body,
      inferred_issues: reason ? [reason] : [],
      rejected_by: rejectedBy,
    });
    // Losing the learning record must not block the rejection itself.
    if (learnErr) console.error('Failed to record rejection learning:', learnErr);
  }

  const { error: delErr } = await supabase.from('message_drafts').delete().eq('id', draftId);
  if (delErr) throw delErr;

  return { status: 'rejected', draft_id: draftId };
}

export async function updateDraft(draftId: string, updates: { subject?: string; body?: string }) {
  const patch: Record<string, unknown> = {};
  if (typeof updates.subject === 'string') patch.subject = updates.subject;
  if (typeof updates.body === 'string') patch.body = updates.body;

  if (Object.keys(patch).length === 0) {
    throw Object.assign(new Error('Nothing to update: provide subject and/or body'), { statusCode: 400 });
  }

  const supabase = getSupabaseAdmin();
  const { data, error } = await supabase
    .from('message_drafts')
    .update(patch)
    .eq('id', draftId)
    .select()
    .single();
  if (error) throw error;
  return data;
}
