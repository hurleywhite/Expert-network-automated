export interface Project {
  id: string;
  name: string;
  industry: string | null;
  subvertical: string | null;
  company_size_min: number | null;
  regions: string[];
  titles_include: string[];
  titles_exclude: string[];
  keywords: string[];
  exclusions: string[];
  created_at: string;
}

export interface PipelineStatus {
  project_id: string;
  project_name: string;
  pipeline: {
    candidates_scored: number;
    qualified_for_outreach: number;
    drafts_created: number;
    drafts_pending_review: number;
    drafts_with_risk_flags: number;
    drafts_approved: number;
    emails_sent: number;
    replies_received: number;
    interested: number;
  };
  next_action: string;
}

export interface Draft {
  draft_id: string;
  candidate_id: string;
  candidate_name: string;
  candidate_title: string;
  candidate_company: string;
  candidate_email: string;
  score: number;
  subject: string;
  body: string;
  facts_used: string[];
  risk_flags: string[];
  created_at: string;
}

export interface ReviewQueue {
  project_id: string;
  total_pending: number;
  ready_to_approve: {
    count: number;
    drafts: Draft[];
  };
  needs_review: {
    count: number;
    drafts: Draft[];
  };
}

export interface ApprovalResponse {
  id: string;
  candidate_id: string;
  project_id: string;
  subject: string;
  body: string;
  facts_used: string[];
  risk_flags: string[];
  approved_at: string;
  approved_by: string;
  created_at: string;
}

export interface BulkApproveResponse {
  project_id: string;
  approved_count: number;
  approved_by: string;
}

export interface SendResponse {
  project_id: string;
  jobs_enqueued: number;
  actor: string;
}

export interface ApprovedDraft {
  draft_id: string;
  candidate_id: string;
  candidate_name: string;
  candidate_title: string;
  candidate_company: string;
  candidate_email: string;
  subject: string;
  approved_at: string | null;
  approved_by: string | null;
  status: 'approved' | 'sent';
}

export interface ApprovedDraftsResponse {
  project_id: string;
  approved: {
    count: number;
    drafts: ApprovedDraft[];
  };
  sent: {
    count: number;
    drafts: ApprovedDraft[];
  };
}
