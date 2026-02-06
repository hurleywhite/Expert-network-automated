import axios from 'axios';
import type {
  Project,
  PipelineStatus,
  ReviewQueue,
  ApprovalResponse,
  BulkApproveResponse,
  SendResponse,
  ApprovedDraftsResponse,
  ProjectCandidatesResponse,
  FollowupQueueResponse,
  FollowupDraftsResponse,
} from '../types';

// API configuration
const API_URL = import.meta.env.VITE_API_URL || 'http://localhost:8000';
const API_KEY = import.meta.env.VITE_API_KEY || 'dev-api-key-change-in-production';

const api = axios.create({
  baseURL: API_URL,
  headers: {
    'Content-Type': 'application/json',
    'X-API-Key': API_KEY,
  },
});

export const projectsApi = {
  list: async (): Promise<Project[]> => {
    const response = await api.get('/projects/');
    return response.data;
  },

  get: async (id: string): Promise<Project> => {
    const response = await api.get(`/projects/${id}`);
    return response.data;
  },

  getStatus: async (id: string): Promise<PipelineStatus> => {
    const response = await api.get(`/projects/${id}/status`);
    return response.data;
  },

  getReviewQueue: async (id: string): Promise<ReviewQueue> => {
    const response = await api.get(`/projects/${id}/review-queue`);
    return response.data;
  },

  bulkApprove: async (id: string, approvedBy: string): Promise<BulkApproveResponse> => {
    const response = await api.post(`/projects/${id}/bulk-approve`, {
      approved_by: approvedBy,
    });
    return response.data;
  },

  sendApproved: async (id: string, actor: string, limit?: number): Promise<SendResponse> => {
    const response = await api.post(`/projects/${id}/send-approved`, {
      actor,
      limit,
    });
    return response.data;
  },

  getApprovedDrafts: async (id: string): Promise<ApprovedDraftsResponse> => {
    const response = await api.get(`/projects/${id}/approved-drafts`);
    return response.data;
  },

  getCandidates: async (id: string): Promise<ProjectCandidatesResponse> => {
    const response = await api.get(`/projects/${id}/candidates`);
    return response.data;
  },

  // Follow-up methods
  getFollowupQueue: async (id: string, daysSinceSent: number = 3): Promise<FollowupQueueResponse> => {
    const response = await api.get(`/projects/${id}/followup-queue`, {
      params: { days_since_sent: daysSinceSent },
    });
    return response.data;
  },

  generateFollowups: async (id: string, context?: {
    research_topic?: string;
    rate_range?: string;
    sender_name?: string;
    limit?: number;
  }): Promise<{ drafted: number; errors: number }> => {
    const response = await api.post(`/projects/${id}/generate-followups`, context || {});
    return response.data;
  },

  getFollowups: async (id: string): Promise<FollowupDraftsResponse> => {
    const response = await api.get(`/projects/${id}/followups`);
    return response.data;
  },

  sendFollowups: async (id: string, actor: string, limit?: number): Promise<SendResponse> => {
    const response = await api.post(`/projects/${id}/send-followups`, {
      actor,
      limit,
    });
    return response.data;
  },
};

export const draftsApi = {
  approve: async (draftId: string, approvedBy: string): Promise<ApprovalResponse> => {
    const response = await api.post(`/drafts/${draftId}/approve`, {
      approved_by: approvedBy,
    });
    return response.data;
  },

  reject: async (draftId: string, rejectedBy: string, reason?: string): Promise<{ status: string; draft_id: string }> => {
    const response = await api.post(`/drafts/${draftId}/reject`, {
      rejected_by: rejectedBy,
      reason,
    });
    return response.data;
  },

  update: async (draftId: string, data: { subject?: string; body?: string }): Promise<ApprovalResponse> => {
    const response = await api.patch(`/drafts/${draftId}`, data);
    return response.data;
  },
};

export default api;
