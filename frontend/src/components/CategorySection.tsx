import { useState } from 'react';
import type { ExpertCard, ProjectCategory } from '../types';
import ExpertCardComponent from './ExpertCardComponent';

interface Props {
  category: ProjectCategory;
  experts: ExpertCard[];
  projectId: string;
}

export default function CategorySection({ category, experts, projectId }: Props) {
  const [expanded, setExpanded] = useState(true);

  return (
    <div className="mb-8">
      {/* Category Header */}
      <div
        className="flex items-center justify-between cursor-pointer mb-4"
        onClick={() => setExpanded(!expanded)}
      >
        <div className="flex items-center gap-3">
          <h3 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">
            Angle: {category.name}
          </h3>
          <span className="text-xs text-gray-400">
            {experts.length} expert{experts.length !== 1 ? 's' : ''}
          </span>
        </div>
        <button className="text-gray-400 hover:text-gray-600">
          {expanded ? (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 15l7-7 7 7" /></svg>
          ) : (
            <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
          )}
        </button>
      </div>

      {/* Expert Cards */}
      {expanded && (
        <div className="space-y-3">
          {experts.length === 0 ? (
            <p className="text-sm text-gray-400 italic py-4">No experts sourced yet for this category.</p>
          ) : (
            experts.map((expert) => (
              <ExpertCardComponent key={expert.id} expert={expert} projectId={projectId} />
            ))
          )}
        </div>
      )}
    </div>
  );
}
