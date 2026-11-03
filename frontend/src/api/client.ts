import { extractTextInBrowser, INLINE_UPLOAD_LIMIT } from '../lib/extractText';
import type {
  Project,
  ProjectCategory,
  ScreenerQuestion,
  ExpertCard,
  ExpertProfileFull,
  LinkedInOutreachItem,
  OutreachCampaign,
} from '../types';

/**
 * Every call in this file goes to our own serverless API.
 *
 * The browser holds no database credential. Reads and writes that used to run
 * against Supabase directly now go through /api/data, which authenticates with
 * a server-only service-role key.
 */

const API_BASE = import.meta.env.VITE_API_URL || '';

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  });

  if (!res.ok) {
    // The API returns { error } for everything it can describe; fall back to
    // raw text for anything that escaped the handler (gateway errors, HTML).
    let detail = '';
    try {
      const payload = await res.json();
      detail = payload?.error || JSON.stringify(payload);
    } catch {
      detail = (await res.text().catch(() => '')) || res.statusText;
    }
    throw new Error(`API error ${res.status}: ${detail}`);
  }

  if (res.status === 204) return undefined as T;
  return res.json() as Promise<T>;
}

const get = <T>(path: string) => request<T>(path);

const send = <T>(path: string, method: 'POST' | 'PATCH', payload?: unknown) =>
  request<T>(path, {
    method,
    body: JSON.stringify(payload ?? {}),
  });

const DATA = '/api/data';

// ─── PROJECTS ───────────────────────────────────────────────────────────────

export const projectsApi = {
  list: (): Promise<Project[]> => get(`${DATA}/projects`),
  get: (id: string): Promise<Project> => get(`${DATA}/projects/${id}`),
};

// ─── EXPERT NETWORK ─────────────────────────────────────────────────────────

/** Readable size that never rounds to look equal to the limit it exceeds. */
export function humanSize(bytes: number): string {
  if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
  return `${Math.max(1, Math.round(bytes / 1024))} KB`;
}

/** Largest document accepted, by either path. */
export const MAX_UPLOAD_BYTES = 20 * 1024 * 1024;
export const ACCEPTED_EXTENSIONS = ['.pdf', '.docx', '.txt', '.md', '.markdown', '.csv', '.json', '.rtf'];
export { INLINE_UPLOAD_LIMIT };

/** Reads a File as base64, without the data: prefix. */
function fileToBase64(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
    reader.onload = () => {
      const result = String(reader.result || '');
      const comma = result.indexOf(',');
      resolve(comma === -1 ? result : result.slice(comma + 1));
    };
    reader.readAsDataURL(file);
  });
}

export const expertNetworkApi = {
  // AI: parse a requirements document into a project, categories and screeners
  createFromDocument: (documentText: string): Promise<any> =>
    send('/api/projects/from-document', 'POST', { document_text: documentText }),

  /**
   * Create a project from an uploaded document.
   *
   * Two paths, chosen by size. Vercel caps a function request body at 4.5 MB
   * and base64 inflates by about a third, so only files under ~3 MB can be
   * posted whole. Those are — which is the better path, because the server
   * hands a PDF to Claude natively and it reads the real layout.
   *
   * Anything larger is read in the browser and only its text is sent.
   */
  createFromFile: async (file: File): Promise<any> => {
    if (file.size > MAX_UPLOAD_BYTES) {
      throw new Error(
        `That file is ${humanSize(file.size)}, over the ${humanSize(MAX_UPLOAD_BYTES)} limit — ` +
          'paste the relevant section instead.',
      );
    }

    if (file.size <= INLINE_UPLOAD_LIMIT) {
      const data = await fileToBase64(file);
      return send('/api/projects/from-document', 'POST', {
        file: { name: file.name, type: file.type, data },
      });
    }

    const text = await extractTextInBrowser(file);
    if (!text.trim()) {
      throw new Error(`No text could be read from ${file.name}. Try pasting the requirements instead.`);
    }
    return send('/api/projects/from-document', 'POST', {
      document_text: text,
      source_name: file.name,
    });
  },

  getCategories: (projectId: string): Promise<ProjectCategory[]> =>
    get(`${DATA}/projects/${projectId}/categories`),

  getExperts: (
    projectId: string,
    categoryId?: string,
  ): Promise<{ project_id: string; total: number; experts: ExpertCard[] }> =>
    get(
      `${DATA}/projects/${projectId}/experts` +
        (categoryId ? `?category_id=${encodeURIComponent(categoryId)}` : ''),
    ),

  getExpertProfile: (expertId: string): Promise<ExpertProfileFull> =>
    get(`${DATA}/experts/${expertId}`),

  getScreenerQuestions: (projectId: string): Promise<ScreenerQuestion[]> =>
    get(`${DATA}/projects/${projectId}/screener-questions`),

  // AI: research each sourced expert and write their profile
  generateProfiles: (projectId: string, limit?: number): Promise<any> =>
    send('/api/profiles/generate', 'POST', { project_id: projectId, limit }),

  scheduleCall: (expertId: string): Promise<any> =>
    send(`${DATA}/experts/${expertId}/schedule-call`, 'POST'),

  updateExpertStatus: (expertId: string, status: string): Promise<any> =>
    send(`${DATA}/experts/${expertId}`, 'PATCH', { status }),

  // Apollo sourcing
  sourceByCategory: (projectId: string, categoryId: string, maxResults?: number): Promise<any> =>
    send('/api/sourcing/by-category', 'POST', {
      project_id: projectId,
      category_id: categoryId,
      max_results: maxResults,
    }),

  sourceAllCategories: (projectId: string, maxPerCategory?: number): Promise<any> =>
    send('/api/sourcing/all-categories', 'POST', {
      project_id: projectId,
      max_per_category: maxPerCategory,
    }),
};

// ─── LINKEDIN ───────────────────────────────────────────────────────────────

export const linkedInApi = {
  // AI: write connection notes and follow-ups for qualified experts
  generateOutreach: (
    projectId: string,
    options?: { min_relevance_score?: number; limit?: number; sender_name?: string },
  ): Promise<any> =>
    send('/api/linkedin/generate-outreach', 'POST', { project_id: projectId, ...options }),

  getOutreachStatus: (
    projectId: string,
  ): Promise<{
    project_id: string;
    total: number;
    status_breakdown: Record<string, number>;
    outreach: LinkedInOutreachItem[];
  }> => get(`${DATA}/projects/${projectId}/linkedin-outreach`),
};

// ─── DRAFTS ─────────────────────────────────────────────────────────────────

export const draftsApi = {
  approve: (draftId: string, approvedBy: string) =>
    send(`${DATA}/drafts/${draftId}/approve`, 'POST', { approved_by: approvedBy }),

  reject: (draftId: string, rejectedBy: string, reason?: string) =>
    send(`${DATA}/drafts/${draftId}/reject`, 'POST', { rejected_by: rejectedBy, reason }),

  update: (draftId: string, updates: { subject?: string; body?: string }) =>
    send(`${DATA}/drafts/${draftId}`, 'PATCH', updates),
};

// ─── OUTREACH CAMPAIGNS ─────────────────────────────────────────────────────

export const outreachApi = {
  listCampaigns: (projectId: string): Promise<OutreachCampaign[]> =>
    get(`${DATA}/projects/${projectId}/campaigns`),

  // AI: build a full multi-step sequence per lead
  createCampaign: (
    projectId: string,
    options?: {
      campaign_name?: string;
      min_relevance_score?: number;
      limit?: number;
      max_per_company?: number;
      sender_name?: string;
      sender_title?: string;
      consultation_rate?: string;
      call_duration?: string;
      context_override?: string;
    },
  ): Promise<any> =>
    send('/api/outreach/create-campaign', 'POST', { project_id: projectId, ...options }),

  getCampaignDetail: (campaignId: string): Promise<any> =>
    get(`/api/outreach/export?campaign_id=${encodeURIComponent(campaignId)}`),

  pushToHeyReach: (campaignId: string, linkedinAccountId?: string): Promise<any> =>
    send('/api/outreach/push-to-heyreach', 'POST', {
      campaign_id: campaignId,
      linkedin_account_id: linkedinAccountId,
    }),
};
