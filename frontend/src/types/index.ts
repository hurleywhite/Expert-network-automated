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
  candidate_linkedin?: string;
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
  candidate_linkedin?: string | null;
  subject: string;
  body: string;
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

export interface ScoredCandidate {
  candidate_id: string;
  full_name: string;
  title: string;
  company: string;
  email: string | null;
  linkedin_url: string | null;
  region: string | null;
  score: number;
  hard_pass: boolean;
  reasons: string[];
}

export interface ProjectCandidatesResponse {
  project_id: string;
  total: number;
  candidates: ScoredCandidate[];
}

// Interview Types
export type InterviewType = 'follow_up' | 'qualification' | 'deep_dive';
export type InterviewStatus = 'scheduled' | 'in_progress' | 'completed' | 'cancelled' | 'failed';
export type MessageType = 'ai_question' | 'human_response' | 'system';

export interface InterviewTemplate {
  id: string;
  name: string;
  description?: string;
  interview_type: InterviewType;
  estimated_duration_minutes: number;
  created_at: string;
}

export interface InterviewSession {
  id: string;
  candidate_id: string;
  project_id: string;
  template_id: string;
  status: InterviewStatus;
  scheduled_for?: string;
  started_at?: string;
  completed_at?: string;
  duration_seconds?: number;
  meet_link?: string;
  summary?: string;
  qualification_score?: number;
  candidate?: {
    full_name: string;
    title: string;
    company: string;
    email: string;
  };
  template?: InterviewTemplate;
}

export interface InterviewMessage {
  id: string;
  message_type: MessageType;
  text_content?: string;
  audio_url?: string;
  timestamp_seconds: number;
  sentiment_score?: number;
  emotion_detected?: string;
}

export interface CreateInterviewSessionRequest {
  candidate_id: string;
  project_id: string;
  template_id: string;
  scheduled_for: string;
  timezone?: string;
  video_enabled?: boolean;
  ai_voice_id?: string;
}

export interface HumanResponseRequest {
  text: string;
  timestamp_seconds: number;
  audio_url?: string;
}

export interface InterviewStartResponse {
  session_id: string;
  status: string;
  opening_message: {
    id: string;
    text: string;
    audio_url?: string;
  };
  meet_link: string;
}

export interface InterviewResponseResult {
  ai_response: {
    id?: string;
    text?: string;
    audio_url?: string;
  };
  session_status: string;
}
