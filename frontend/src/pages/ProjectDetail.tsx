import { useState, useEffect, useCallback, useRef } from 'react';
import { useParams, Link } from 'react-router-dom';
import { projectsApi, draftsApi } from '../api/client';
import type { Project, PipelineStatus, ReviewQueue, ApprovedDraftsResponse, ProjectCandidatesResponse } from '../types';
import StatusCard from '../components/StatusCard';
import DraftCard from '../components/DraftCard';

// Clean up project names for display
function formatProjectName(name: string): string {
  let cleaned = name.replace(/^Find\s+/i, '');
  cleaned = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  return cleaned;
}

export default function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [reviewQueue, setReviewQueue] = useState<ReviewQueue | null>(null);
  const [approvedDrafts, setApprovedDrafts] = useState<ApprovedDraftsResponse | null>(null);
  const [candidates, setCandidates] = useState<ProjectCandidatesResponse | null>(null);
  const [showCandidates, setShowCandidates] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [approvingDraft, setApprovingDraft] = useState<string | null>(null);
  const [rejectingDraft, setRejectingDraft] = useState<string | null>(null);
  const [bulkApproving, setBulkApproving] = useState(false);
  const [sending, setSending] = useState(false);
  const [successMessage, setSuccessMessage] = useState<string | null>(null);
  const [expandedApproved, setExpandedApproved] = useState<string | null>(null);
  const [editingDraft, setEditingDraft] = useState<string | null>(null);
  const [editSubject, setEditSubject] = useState('');
  const [editBody, setEditBody] = useState('');
  const [saving, setSaving] = useState(false);

  // Refs for scrolling to sections
  const candidatesRef = useRef<HTMLDivElement>(null);
  const pendingReviewRef = useRef<HTMLDivElement>(null);
  const approvedRef = useRef<HTMLDivElement>(null);
  const sentRef = useRef<HTMLDivElement>(null);

  const scrollToSection = (ref: React.RefObject<HTMLDivElement | null>, expand?: () => void) => {
    if (expand) expand();
    setTimeout(() => {
      ref.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }, 100);
  };

  const loadData = useCallback(async () => {
    if (!projectId) return;

    try {
      setLoading(true);
      // Load essential data first
      const [projectData, statusData, queueData, approvedData] = await Promise.all([
        projectsApi.get(projectId),
        projectsApi.getStatus(projectId),
        projectsApi.getReviewQueue(projectId),
        projectsApi.getApprovedDrafts(projectId),
      ]);
      setProject(projectData);
      setStatus(statusData);
      setReviewQueue(queueData);
      setApprovedDrafts(approvedData);
      setError(null);

      // Load candidates separately (non-critical)
      try {
        const candidatesData = await projectsApi.getCandidates(projectId);
        setCandidates(candidatesData);
      } catch (candidatesErr) {
        console.error('Failed to load candidates:', candidatesErr);
        // Don't fail the whole page, just skip candidates
      }
    } catch (err) {
      setError('Failed to load project data');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleApproveDraft = async (draftId: string) => {
    setApprovingDraft(draftId);
    try {
      await draftsApi.approve(draftId, 'reviewer');
      setSuccessMessage('Draft approved successfully');
      await loadData();
    } catch (err) {
      setError('Failed to approve draft');
      console.error(err);
    } finally {
      setApprovingDraft(null);
      setTimeout(() => setSuccessMessage(null), 3000);
    }
  };

  const handleRejectDraft = async (draftId: string) => {
    setRejectingDraft(draftId);
    try {
      await draftsApi.reject(draftId, 'reviewer');
      setSuccessMessage('Draft rejected and removed');
      await loadData();
    } catch (err) {
      setError('Failed to reject draft');
      console.error(err);
    } finally {
      setRejectingDraft(null);
      setTimeout(() => setSuccessMessage(null), 3000);
    }
  };

  const handleBulkApprove = async () => {
    if (!projectId) return;
    setBulkApproving(true);
    try {
      const result = await projectsApi.bulkApprove(projectId, 'reviewer');
      setSuccessMessage(`Approved ${result.approved_count} safe drafts`);
      await loadData();
    } catch (err) {
      setError('Failed to bulk approve drafts');
      console.error(err);
    } finally {
      setBulkApproving(false);
      setTimeout(() => setSuccessMessage(null), 3000);
    }
  };

  const handleSendApproved = async () => {
    if (!projectId) return;
    setSending(true);
    try {
      const result = await projectsApi.sendApproved(projectId, 'sender');
      setSuccessMessage(`Enqueued ${result.jobs_enqueued} emails for sending`);
      await loadData();
    } catch (err) {
      setError('Failed to send emails');
      console.error(err);
    } finally {
      setSending(false);
      setTimeout(() => setSuccessMessage(null), 3000);
    }
  };

  const handleStartEdit = (draftId: string, subject: string, body: string) => {
    setEditingDraft(draftId);
    setEditSubject(subject);
    setEditBody(body);
    setExpandedApproved(draftId);
  };

  const handleCancelEdit = () => {
    setEditingDraft(null);
    setEditSubject('');
    setEditBody('');
  };

  const handleSaveEdit = async (draftId: string) => {
    setSaving(true);
    try {
      await draftsApi.update(draftId, { subject: editSubject, body: editBody });
      setSuccessMessage('Draft updated - needs re-approval');
      setEditingDraft(null);
      await loadData();
    } catch (err) {
      setError('Failed to update draft');
      console.error(err);
    } finally {
      setSaving(false);
      setTimeout(() => setSuccessMessage(null), 3000);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error && !project) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
        <p className="font-medium">Error</p>
        <p>{error}</p>
        <Link to="/" className="mt-2 text-sm underline hover:no-underline">
          Back to Dashboard
        </Link>
      </div>
    );
  }

  const safeCount = reviewQueue?.ready_to_approve.count || 0;
  const needsReviewCount = reviewQueue?.needs_review.count || 0;
  const approvedNotSent = (status?.pipeline.drafts_approved || 0) - (status?.pipeline.emails_sent || 0);

  return (
    <div>
      {/* Breadcrumb */}
      <nav className="mb-4">
        <Link to="/" className="text-blue-600 hover:text-blue-800">
          Dashboard
        </Link>
        <span className="mx-2 text-gray-400">/</span>
        <span className="text-gray-600">{project?.name ? formatProjectName(project.name) : ''}</span>
      </nav>

      {/* Messages */}
      {error && (
        <div className="mb-4 bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
          {error}
          <button
            onClick={() => setError(null)}
            className="ml-2 text-sm underline"
          >
            Dismiss
          </button>
        </div>
      )}

      {successMessage && (
        <div className="mb-4 bg-green-50 border border-green-200 rounded-lg p-4 text-green-700">
          {successMessage}
        </div>
      )}

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">{project?.name ? formatProjectName(project.name) : ''}</h1>
        {project?.industry && (
          <p className="text-gray-600 mt-1">
            {project.industry}
            {project.subvertical && ` - ${project.subvertical}`}
          </p>
        )}
      </div>

      {/* Pipeline Status */}
      {status && (
        <div className="mb-8">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">
            Pipeline Status
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-4">
            <StatusCard
              label="Candidates Scored"
              value={status.pipeline.candidates_scored}
              color="gray"
              onClick={() => scrollToSection(candidatesRef, () => setShowCandidates(true))}
            />
            <StatusCard
              label="Qualified"
              value={status.pipeline.qualified_for_outreach}
              color="blue"
              onClick={() => scrollToSection(candidatesRef, () => setShowCandidates(true))}
            />
            <StatusCard
              label="Drafts Created"
              value={status.pipeline.drafts_created}
              color="blue"
              onClick={() => scrollToSection(pendingReviewRef)}
            />
            <StatusCard
              label="Pending Review"
              value={status.pipeline.drafts_pending_review}
              color={status.pipeline.drafts_with_risk_flags > 0 ? 'yellow' : 'blue'}
              subtext={
                status.pipeline.drafts_with_risk_flags > 0
                  ? `${status.pipeline.drafts_with_risk_flags} with risk flags`
                  : undefined
              }
              onClick={() => scrollToSection(pendingReviewRef)}
            />
            <StatusCard
              label="Approved"
              value={status.pipeline.drafts_approved}
              color="green"
              onClick={() => scrollToSection(approvedRef)}
            />
            <StatusCard
              label="Sent"
              value={status.pipeline.emails_sent}
              color="green"
              onClick={() => scrollToSection(sentRef)}
            />
            <StatusCard
              label="Replies"
              value={status.pipeline.replies_received}
              color={status.pipeline.interested > 0 ? 'green' : 'gray'}
              subtext={
                status.pipeline.interested > 0
                  ? `${status.pipeline.interested} interested`
                  : undefined
              }
            />
          </div>

          {/* Next Action */}
          {status.next_action && (
            <div className="mt-4 bg-blue-50 border border-blue-200 rounded-lg p-4 text-blue-800 text-sm">
              <span className="font-medium">Next step:</span> {status.next_action}
            </div>
          )}
        </div>
      )}

      {/* Candidates List */}
      {candidates && candidates.total > 0 && (
        <div className="mb-8" ref={candidatesRef}>
          <button
            onClick={() => setShowCandidates(!showCandidates)}
            className="flex items-center justify-between w-full text-left"
          >
            <h2 className="text-lg font-semibold text-gray-900 flex items-center">
              <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-600 text-sm font-bold mr-2">
                {candidates.total}
              </span>
              Scored Candidates
            </h2>
            <svg
              className={`w-5 h-5 text-gray-500 transition-transform ${showCandidates ? 'rotate-180' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
            </svg>
          </button>

          {showCandidates && (
            <div className="mt-4 bg-white rounded-lg shadow border border-gray-200 overflow-hidden">
              <table className="min-w-full divide-y divide-gray-200">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Name</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Title</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Company</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Email</th>
                    <th className="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider">Score</th>
                  </tr>
                </thead>
                <tbody className="bg-white divide-y divide-gray-200">
                  {candidates.candidates.map((candidate) => (
                    <tr key={candidate.candidate_id} className={candidate.hard_pass ? 'bg-red-50' : ''}>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <div className="text-sm font-medium text-gray-900">{candidate.full_name}</div>
                        {candidate.linkedin_url && (
                          <a
                            href={candidate.linkedin_url}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="text-xs text-blue-600 hover:underline"
                          >
                            LinkedIn
                          </a>
                        )}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">{candidate.title}</td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm text-gray-600">{candidate.company}</td>
                      <td className="px-4 py-3 whitespace-nowrap text-sm">
                        {candidate.email ? (
                          <span className="text-gray-600">{candidate.email}</span>
                        ) : (
                          <span className="text-gray-400 italic">No email</span>
                        )}
                      </td>
                      <td className="px-4 py-3 whitespace-nowrap">
                        <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                          candidate.hard_pass
                            ? 'bg-red-100 text-red-800'
                            : candidate.score >= 60
                            ? 'bg-green-100 text-green-800'
                            : candidate.score >= 40
                            ? 'bg-yellow-100 text-yellow-800'
                            : 'bg-gray-100 text-gray-800'
                        }`}>
                          {candidate.score}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}

      {/* Action Buttons */}
      <div className="mb-6 flex flex-wrap gap-4">
        {safeCount > 0 && (
          <button
            onClick={handleBulkApprove}
            disabled={bulkApproving}
            className={`inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white ${
              bulkApproving
                ? 'bg-gray-400 cursor-not-allowed'
                : 'bg-green-600 hover:bg-green-700'
            }`}
          >
            {bulkApproving ? (
              <>
                <svg
                  className="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                Approving...
              </>
            ) : (
              `Bulk Approve ${safeCount} Safe Drafts`
            )}
          </button>
        )}

        {approvedNotSent > 0 && (
          <button
            onClick={handleSendApproved}
            disabled={sending}
            className={`inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white ${
              sending
                ? 'bg-gray-400 cursor-not-allowed'
                : 'bg-blue-600 hover:bg-blue-700'
            }`}
          >
            {sending ? (
              <>
                <svg
                  className="animate-spin -ml-1 mr-2 h-4 w-4 text-white"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  />
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  />
                </svg>
                Sending...
              </>
            ) : (
              `Send ${approvedNotSent} Approved Emails`
            )}
          </button>
        )}

        <button
          onClick={loadData}
          className="inline-flex items-center px-4 py-2 border border-gray-300 text-sm font-medium rounded-md shadow-sm text-gray-700 bg-white hover:bg-gray-50"
        >
          Refresh
        </button>
      </div>

      {/* Review Queue */}
      {reviewQueue && reviewQueue.total_pending > 0 && (
        <div className="space-y-8" ref={pendingReviewRef}>
          {/* Needs Review Section */}
          {needsReviewCount > 0 && (
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-orange-100 text-orange-600 text-sm font-bold mr-2">
                  {needsReviewCount}
                </span>
                Drafts Needing Manual Review
              </h2>
              <p className="text-sm text-gray-600 mb-4">
                These drafts have risk flags and require careful review before
                approval.
              </p>
              <div className="space-y-4">
                {reviewQueue.needs_review.drafts.map((draft) => (
                  <DraftCard
                    key={draft.draft_id}
                    draft={draft}
                    onApprove={handleApproveDraft}
                    onReject={handleRejectDraft}
                    isApproving={approvingDraft === draft.draft_id}
                    isRejecting={rejectingDraft === draft.draft_id}
                  />
                ))}
              </div>
            </div>
          )}

          {/* Ready to Approve Section */}
          {safeCount > 0 && (
            <div>
              <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
                <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-green-100 text-green-600 text-sm font-bold mr-2">
                  {safeCount}
                </span>
                Safe Drafts (No Risk Flags)
              </h2>
              <p className="text-sm text-gray-600 mb-4">
                These drafts have no risk flags and can be bulk approved.
              </p>
              <div className="space-y-4">
                {reviewQueue.ready_to_approve.drafts.map((draft) => (
                  <DraftCard
                    key={draft.draft_id}
                    draft={draft}
                    onApprove={handleApproveDraft}
                    onReject={handleRejectDraft}
                    isApproving={approvingDraft === draft.draft_id}
                    isRejecting={rejectingDraft === draft.draft_id}
                  />
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Empty State for Pending */}
      {reviewQueue && reviewQueue.total_pending === 0 && !approvedDrafts?.approved.count && !approvedDrafts?.sent.count && (
        <div className="bg-white rounded-lg shadow border border-gray-200 p-8 text-center">
          <svg
            className="mx-auto h-12 w-12 text-gray-400"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z"
            />
          </svg>
          <h3 className="mt-4 text-lg font-medium text-gray-900">
            No drafts yet
          </h3>
          <p className="mt-2 text-sm text-gray-500">
            Generate drafts for qualified candidates to get started.
          </p>
        </div>
      )}

      {/* Approved Drafts Section */}
      {approvedDrafts && approvedDrafts.approved.count > 0 && (
        <div className="mt-8" ref={approvedRef}>
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
            <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-green-100 text-green-600 text-sm font-bold mr-2">
              {approvedDrafts.approved.count}
            </span>
            Approved (Ready to Send)
          </h2>
          <div className="bg-white rounded-lg shadow border border-green-200 divide-y divide-gray-100">
            {approvedDrafts.approved.drafts.map((draft) => (
              <div key={draft.draft_id} className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <p className="font-medium text-gray-900">{draft.candidate_name}</p>
                    {draft.candidate_linkedin && (
                      <a
                        href={draft.candidate_linkedin}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-600 hover:underline"
                      >
                        LinkedIn
                      </a>
                    )}
                    <p className="text-sm text-gray-600">{draft.candidate_title} at {draft.candidate_company}</p>
                    <p className="text-sm text-gray-500">{draft.candidate_email}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setExpandedApproved(expandedApproved === draft.draft_id ? null : draft.draft_id)}
                      className="text-gray-400 hover:text-gray-600"
                    >
                      <svg
                        className={`h-5 w-5 transform transition-transform ${expandedApproved === draft.draft_id ? 'rotate-180' : ''}`}
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      Approved
                    </span>
                  </div>
                </div>

                {/* Subject - editable if in edit mode */}
                {editingDraft === draft.draft_id ? (
                  <div className="mt-2">
                    <label className="text-sm font-medium text-gray-700">Subject:</label>
                    <input
                      type="text"
                      value={editSubject}
                      onChange={(e) => setEditSubject(e.target.value)}
                      className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-blue-500"
                    />
                  </div>
                ) : (
                  <p className="mt-2 text-sm text-gray-700">
                    <span className="font-medium">Subject:</span> {draft.subject}
                  </p>
                )}

                {/* Expanded content */}
                {expandedApproved === draft.draft_id && (
                  <div className="mt-4">
                    {editingDraft === draft.draft_id ? (
                      <div>
                        <label className="text-sm font-medium text-gray-700">Email Body:</label>
                        <textarea
                          value={editBody}
                          onChange={(e) => setEditBody(e.target.value)}
                          rows={10}
                          className="mt-1 block w-full rounded-md border border-gray-300 px-3 py-2 text-sm focus:border-blue-500 focus:ring-blue-500"
                        />
                        <div className="mt-3 flex gap-2">
                          <button
                            onClick={() => handleSaveEdit(draft.draft_id)}
                            disabled={saving}
                            className="inline-flex items-center px-3 py-1.5 border border-transparent text-sm font-medium rounded-md shadow-sm text-white bg-blue-600 hover:bg-blue-700 disabled:bg-gray-400"
                          >
                            {saving ? 'Saving...' : 'Save Changes'}
                          </button>
                          <button
                            onClick={handleCancelEdit}
                            className="inline-flex items-center px-3 py-1.5 border border-gray-300 text-sm font-medium rounded-md shadow-sm text-gray-700 bg-white hover:bg-gray-50"
                          >
                            Cancel
                          </button>
                        </div>
                        <p className="mt-2 text-xs text-orange-600">
                          Note: Saving changes will require re-approval before sending.
                        </p>
                      </div>
                    ) : (
                      <div>
                        <p className="text-sm font-medium text-gray-700 mb-2">Email Body:</p>
                        <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-800 whitespace-pre-wrap border border-gray-200">
                          {draft.body}
                        </div>
                        <button
                          onClick={() => handleStartEdit(draft.draft_id, draft.subject, draft.body)}
                          className="mt-3 inline-flex items-center px-3 py-1.5 border border-gray-300 text-sm font-medium rounded-md shadow-sm text-gray-700 bg-white hover:bg-gray-50"
                        >
                          Edit Draft
                        </button>
                      </div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Sent Drafts Section */}
      {approvedDrafts && approvedDrafts.sent.count > 0 && (
        <div className="mt-8" ref={sentRef}>
          <h2 className="text-lg font-semibold text-gray-900 mb-4 flex items-center">
            <span className="inline-flex items-center justify-center w-6 h-6 rounded-full bg-blue-100 text-blue-600 text-sm font-bold mr-2">
              {approvedDrafts.sent.count}
            </span>
            Sent
          </h2>
          <div className="bg-white rounded-lg shadow border border-blue-200 divide-y divide-gray-100">
            {approvedDrafts.sent.drafts.map((draft) => (
              <div key={draft.draft_id} className="p-4">
                <div className="flex items-center justify-between">
                  <div className="flex-1">
                    <p className="font-medium text-gray-900">{draft.candidate_name}</p>
                    {draft.candidate_linkedin && (
                      <a
                        href={draft.candidate_linkedin}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="text-xs text-blue-600 hover:underline"
                      >
                        LinkedIn
                      </a>
                    )}
                    <p className="text-sm text-gray-600">{draft.candidate_title} at {draft.candidate_company}</p>
                    <p className="text-sm text-gray-500">{draft.candidate_email}</p>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setExpandedApproved(expandedApproved === draft.draft_id ? null : draft.draft_id)}
                      className="text-gray-400 hover:text-gray-600"
                    >
                      <svg
                        className={`h-5 w-5 transform transition-transform ${expandedApproved === draft.draft_id ? 'rotate-180' : ''}`}
                        fill="none"
                        viewBox="0 0 24 24"
                        stroke="currentColor"
                      >
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                      </svg>
                    </button>
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                      Sent
                    </span>
                  </div>
                </div>
                <p className="mt-2 text-sm text-gray-700">
                  <span className="font-medium">Subject:</span> {draft.subject}
                </p>

                {/* Expanded content - view only for sent */}
                {expandedApproved === draft.draft_id && (
                  <div className="mt-4">
                    <p className="text-sm font-medium text-gray-700 mb-2">Email Body:</p>
                    <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-800 whitespace-pre-wrap border border-gray-200">
                      {draft.body}
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
