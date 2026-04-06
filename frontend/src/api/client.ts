import { supabase } from '../lib/supabase';
import type {
  Project,
  ProjectCategory,
  ScreenerQuestion,
  ExpertCard,
  ExpertProfileFull,
  LinkedInOutreachItem,
} from '../types';

// ─── HELPER: Call Vercel serverless API routes for AI-heavy ops ─────────────
const API_BASE = import.meta.env.VITE_API_URL || '';

async function apiCall(path: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });
  if (!res.ok) {
    const err = await res.text();
    throw new Error(`API error ${res.status}: ${err}`);
  }
  return res.json();
}

// ─── PROJECTS (Supabase direct) ─────────────────────────────────────────────

export const projectsApi = {
  list: async (): Promise<Project[]> => {
    const { data, error } = await supabase
      .from('project_briefs')
      .select('*')
      .order('created_at', { ascending: false });
    if (error) throw error;
    return data || [];
  },

  get: async (id: string): Promise<Project> => {
    const { data, error } = await supabase
      .from('project_briefs')
      .select('*')
      .eq('id', id)
      .single();
    if (error) throw error;
    return data;
  },
};

// ─── GLG-STYLE EXPERT NETWORK API ──────────────────────────────────────────

export const expertNetworkApi = {
  // ── AI-powered: Create project from document (Vercel serverless) ──
  createFromDocument: async (documentText: string): Promise<any> => {
    return apiCall('/api/projects/from-document', {
      method: 'POST',
      body: JSON.stringify({ document_text: documentText }),
    });
  },

  // ── Categories (Supabase direct) ──
  getCategories: async (projectId: string): Promise<ProjectCategory[]> => {
    const { data, error } = await supabase
      .from('project_categories')
      .select('*')
      .eq('project_id', projectId)
      .order('sort_order');
    if (error) throw error;

    // Add expert_count to each category
    const categories = data || [];
    for (const cat of categories) {
      const { count } = await supabase
        .from('expert_profiles')
        .select('*', { count: 'exact', head: true })
        .eq('category_id', cat.id);
      (cat as any).expert_count = count || 0;
    }
    return categories;
  },

  // ── Experts list (Supabase direct with joins) ──
  getExperts: async (projectId: string, categoryId?: string): Promise<{ project_id: string; total: number; experts: ExpertCard[] }> => {
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
        candidates!inner (
          full_name,
          title,
          company,
          region,
          linkedin_url,
          headline,
          photo_url,
          email
        ),
        project_categories (
          id,
          name
        )
      `)
      .eq('project_id', projectId);

    if (categoryId) {
      query = query.eq('category_id', categoryId);
    }

    const { data, error } = await query.order('relevance_score', { ascending: false, nullsFirst: false });
    if (error) throw error;

    const experts: ExpertCard[] = (data || []).map((row: any) => ({
      id: row.id,
      candidate_id: row.candidate_id,
      full_name: row.candidates?.full_name || '',
      title: row.candidates?.title || null,
      company: row.candidates?.company || null,
      region: row.candidates?.region || null,
      linkedin_url: row.candidates?.linkedin_url || null,
      headline: row.candidates?.headline || null,
      photo_url: row.candidates?.photo_url || null,
      email: row.candidates?.email || null,
      rate_per_hour: row.rate_per_hour ? parseFloat(row.rate_per_hour) : null,
      relevance_score: row.relevance_score,
      status: row.status,
      category: row.project_categories ? { id: row.project_categories.id, name: row.project_categories.name } : null,
      ai_overview_snippet: row.ai_overview ? row.ai_overview.substring(0, 200) + '...' : null,
      project_expertise: row.project_expertise || [],
      activity_count: 0,
    }));

    return { project_id: projectId, total: experts.length, experts };
  },

  // ── Expert profile detail (Supabase direct with joins) ──
  getExpertProfile: async (expertId: string): Promise<ExpertProfileFull> => {
    const { data, error } = await supabase
      .from('expert_profiles')
      .select(`
        *,
        candidates!inner (
          full_name,
          title,
          company,
          region,
          linkedin_url,
          headline,
          photo_url,
          email
        ),
        project_categories (
          id,
          name
        ),
        expert_activities (
          id,
          activity_type,
          description,
          created_at
        ),
        linkedin_outreach (
          status,
          connection_note,
          sent_at
        )
      `)
      .eq('id', expertId)
      .single();

    if (error) throw error;

    return {
      id: data.id,
      candidate_id: data.candidate_id,
      full_name: data.candidates?.full_name || '',
      title: data.candidates?.title || null,
      company: data.candidates?.company || null,
      region: data.candidates?.region || null,
      linkedin_url: data.candidates?.linkedin_url || null,
      headline: data.candidates?.headline || null,
      photo_url: data.candidates?.photo_url || null,
      email: data.candidates?.email || null,
      rate_per_hour: data.rate_per_hour ? parseFloat(data.rate_per_hour) : null,
      relevance_score: data.relevance_score,
      status: data.status,
      category: data.project_categories ? { id: data.project_categories.id, name: data.project_categories.name } : null,
      ai_overview: data.ai_overview,
      project_expertise: data.project_expertise || [],
      work_experience: data.work_experience || [],
      screener_responses: data.screener_responses || {},
      exa_research: data.exa_research || {},
      activities: (data.expert_activities || []).map((a: any) => ({
        id: a.id,
        type: a.activity_type,
        description: a.description,
        created_at: a.created_at,
      })),
      linkedin_outreach: data.linkedin_outreach?.[0] ? {
        status: data.linkedin_outreach[0].status,
        connection_note: data.linkedin_outreach[0].connection_note,
        sent_at: data.linkedin_outreach[0].sent_at,
      } : null,
      created_at: data.created_at,
    };
  },

  // ── Screener questions (Supabase direct) ──
  getScreenerQuestions: async (projectId: string): Promise<ScreenerQuestion[]> => {
    const { data, error } = await supabase
      .from('screener_questions')
      .select('*')
      .eq('project_id', projectId)
      .order('sort_order');
    if (error) throw error;
    return data || [];
  },

  // ── AI-powered: Generate profiles (Vercel serverless) ──
  generateProfiles: async (projectId: string, limit?: number): Promise<any> => {
    return apiCall(`/api/profiles/generate`, {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, limit }),
    });
  },

  // ── Schedule call (Supabase direct — insert activity) ──
  scheduleCall: async (expertId: string): Promise<any> => {
    const { error } = await supabase
      .from('expert_activities')
      .insert({
        expert_profile_id: expertId,
        activity_type: 'call_requested',
        description: 'Call requested via expert profile page',
      });
    if (error) throw error;

    // Update expert status to scheduled
    await supabase
      .from('expert_profiles')
      .update({ status: 'scheduled', updated_at: new Date().toISOString() })
      .eq('id', expertId);

    return { status: 'ok' };
  },

  // ── Update status (Supabase direct) ──
  updateExpertStatus: async (expertId: string, status: string): Promise<any> => {
    const { error } = await supabase
      .from('expert_profiles')
      .update({ status, updated_at: new Date().toISOString() })
      .eq('id', expertId);
    if (error) throw error;
    return { status: 'ok' };
  },

  // ── AI-powered: Source by category (Vercel serverless → Apollo) ──
  sourceByCategory: async (projectId: string, categoryId: string, maxResults?: number): Promise<any> => {
    return apiCall(`/api/sourcing/by-category`, {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, category_id: categoryId, max_results: maxResults }),
    });
  },

  // ── AI-powered: Source all categories (Vercel serverless → Apollo) ──
  sourceAllCategories: async (projectId: string, maxPerCategory?: number): Promise<any> => {
    return apiCall(`/api/sourcing/all-categories`, {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, max_per_category: maxPerCategory }),
    });
  },
};

// ─── LINKEDIN API ───────────────────────────────────────────────────────────

export const linkedInApi = {
  // ── AI-powered: Generate outreach messages (Vercel serverless → Claude) ──
  generateOutreach: async (projectId: string, options?: { min_relevance_score?: number; limit?: number; sender_name?: string }): Promise<any> => {
    return apiCall(`/api/linkedin/generate-outreach`, {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, ...options }),
    });
  },

  // ── Outreach status (Supabase direct) ──
  getOutreachStatus: async (projectId: string): Promise<{ project_id: string; total: number; status_breakdown: Record<string, number>; outreach: LinkedInOutreachItem[] }> => {
    // Get expert profiles for this project with their linkedin outreach
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
          candidates!inner (
            full_name,
            title,
            company
          )
        )
      `)
      .eq('expert_profiles.project_id', projectId);

    if (error) throw error;

    const outreach: LinkedInOutreachItem[] = (data || []).map((row: any) => ({
      id: row.id,
      expert_id: row.expert_profiles?.id || '',
      full_name: row.expert_profiles?.candidates?.full_name || '',
      title: row.expert_profiles?.candidates?.title || null,
      company: row.expert_profiles?.candidates?.company || null,
      linkedin_url: row.linkedin_url,
      connection_note: row.connection_note || '',
      follow_up_message: row.follow_up_message || '',
      status: row.status,
      sent_at: row.sent_at,
      connected_at: row.connected_at,
      error_message: row.error_message,
    }));

    // Build status breakdown
    const statusBreakdown: Record<string, number> = {};
    for (const item of outreach) {
      statusBreakdown[item.status] = (statusBreakdown[item.status] || 0) + 1;
    }

    return { project_id: projectId, total: outreach.length, status_breakdown: statusBreakdown, outreach };
  },

  sendConnection: async (expertId: string, _sessionCookie?: string): Promise<any> => {
    return apiCall(`/api/linkedin/send-connection`, {
      method: 'POST',
      body: JSON.stringify({ expert_id: expertId }),
    });
  },

  sendBatch: async (projectId: string, limit?: number): Promise<any> => {
    return apiCall(`/api/linkedin/send-batch`, {
      method: 'POST',
      body: JSON.stringify({ project_id: projectId, limit }),
    });
  },
};

// ─── DRAFTS API (Supabase direct) ───────────────────────────────────────────

export const draftsApi = {
  approve: async (draftId: string, approvedBy: string) => {
    const { data, error } = await supabase
      .from('message_drafts')
      .update({ approved_at: new Date().toISOString(), approved_by: approvedBy })
      .eq('id', draftId)
      .select()
      .single();
    if (error) throw error;
    return data;
  },

  reject: async (draftId: string, rejectedBy: string, reason?: string) => {
    // Insert rejection learning
    const { data: draft } = await supabase
      .from('message_drafts')
      .select('project_id, subject, body')
      .eq('id', draftId)
      .single();

    if (draft) {
      await supabase.from('rejection_learnings').insert({
        project_id: draft.project_id,
        rejected_subject: draft.subject,
        rejected_body: draft.body,
        inferred_issues: reason ? [reason] : [],
        rejected_by: rejectedBy,
      });
    }

    // Delete the draft
    await supabase.from('message_drafts').delete().eq('id', draftId);
    return { status: 'rejected', draft_id: draftId };
  },

  update: async (draftId: string, updates: { subject?: string; body?: string }) => {
    const { data, error } = await supabase
      .from('message_drafts')
      .update(updates)
      .eq('id', draftId)
      .select()
      .single();
    if (error) throw error;
    return data;
  },
};

export default supabase;
