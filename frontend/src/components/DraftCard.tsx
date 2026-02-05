import { useState } from 'react';
import type { Draft } from '../types';
import RiskBadge from './RiskBadge';
import ScoreBadge from './ScoreBadge';

interface DraftCardProps {
  draft: Draft;
  onApprove: (draftId: string) => Promise<void>;
  onReject: (draftId: string) => Promise<void>;
  isApproving?: boolean;
  isRejecting?: boolean;
}

export default function DraftCard({ draft, onApprove, onReject, isApproving, isRejecting }: DraftCardProps) {
  const [expanded, setExpanded] = useState(false);

  const hasRiskFlags = draft.risk_flags && draft.risk_flags.length > 0;

  return (
    <div
      className={`bg-white rounded-lg shadow border ${
        hasRiskFlags ? 'border-orange-200' : 'border-gray-200'
      }`}
    >
      <div className="p-4">
        {/* Header */}
        <div className="flex items-start justify-between">
          <div className="flex-1">
            <div className="flex items-center gap-2 flex-wrap">
              <h3 className="text-lg font-semibold text-gray-900">
                {draft.candidate_name}
              </h3>
              <ScoreBadge score={draft.score} />
              {hasRiskFlags && (
                <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-800">
                  Needs Review
                </span>
              )}
            </div>
            <p className="text-sm text-gray-600 mt-1">
              {draft.candidate_title} at {draft.candidate_company}
            </p>
            <p className="text-sm text-gray-500">{draft.candidate_email}</p>
          </div>
          <button
            onClick={() => setExpanded(!expanded)}
            className="ml-4 text-gray-400 hover:text-gray-600"
          >
            <svg
              className={`h-5 w-5 transform transition-transform ${
                expanded ? 'rotate-180' : ''
              }`}
              fill="none"
              viewBox="0 0 24 24"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth={2}
                d="M19 9l-7 7-7-7"
              />
            </svg>
          </button>
        </div>

        {/* Risk Flags */}
        {hasRiskFlags && (
          <div className="mt-3 flex flex-wrap gap-2">
            {draft.risk_flags.map((flag, index) => (
              <RiskBadge key={index} flag={flag} />
            ))}
          </div>
        )}

        {/* Subject Preview */}
        <div className="mt-3">
          <p className="text-sm font-medium text-gray-700">Subject:</p>
          <p className="text-sm text-gray-900">{draft.subject}</p>
        </div>

        {/* Expanded Content */}
        {expanded && (
          <div className="mt-4 space-y-4">
            {/* Full Body */}
            <div>
              <p className="text-sm font-medium text-gray-700 mb-2">Email Body:</p>
              <div className="bg-gray-50 rounded-lg p-4 text-sm text-gray-800 whitespace-pre-wrap border border-gray-200">
                {draft.body}
              </div>
            </div>

            {/* Facts Used */}
            {draft.facts_used && draft.facts_used.length > 0 && (
              <div>
                <p className="text-sm font-medium text-gray-700 mb-2">
                  Facts Used:
                </p>
                <div className="flex flex-wrap gap-2">
                  {draft.facts_used.map((fact, index) => (
                    <span
                      key={index}
                      className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800"
                    >
                      {fact}
                    </span>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}

        {/* Actions */}
        <div className="mt-4 flex items-center justify-between border-t border-gray-100 pt-4">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-sm text-blue-600 hover:text-blue-800"
          >
            {expanded ? 'Show Less' : 'Show Full Draft'}
          </button>
          <div className="flex gap-2">
            <button
              onClick={() => onReject(draft.draft_id)}
              disabled={isRejecting || isApproving}
              className={`inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white ${
                isRejecting || isApproving
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-red-600 hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-red-500'
              }`}
            >
              {isRejecting ? (
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
                  Rejecting...
                </>
              ) : (
                'Reject'
              )}
            </button>
            <button
              onClick={() => onApprove(draft.draft_id)}
              disabled={isApproving || isRejecting}
              className={`inline-flex items-center px-4 py-2 border border-transparent text-sm font-medium rounded-md shadow-sm text-white ${
                isApproving || isRejecting
                  ? 'bg-gray-400 cursor-not-allowed'
                  : 'bg-green-600 hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-offset-2 focus:ring-green-500'
              }`}
            >
              {isApproving ? (
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
                'Approve'
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
