import { Link } from 'react-router-dom';
import type { ExpertCard } from '../types';
import StatusBadge from './StatusBadge';

interface Props {
  expert: ExpertCard;
  projectId: string;
}

export default function ExpertCardComponent({ expert, projectId }: Props) {
  return (
    <div className="bg-white border border-gray-200 rounded-lg p-5 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div className="flex-1 min-w-0">
          {/* Title & Company */}
          <div className="flex items-center gap-2 mb-1">
            {expert.photo_url ? (
              <img src={expert.photo_url} alt="" className="w-10 h-10 rounded-full object-cover" />
            ) : (
              <div className="w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center text-white font-semibold text-sm">
                {expert.full_name?.split(' ').map(n => n[0]).join('').slice(0, 2)}
              </div>
            )}
            <div>
              <Link
                to={`/projects/${projectId}/experts/${expert.id}`}
                className="text-sm font-semibold text-gray-900 hover:text-blue-600"
              >
                {expert.title || 'Untitled'} at {expert.company || 'Unknown'}
              </Link>
              <p className="text-sm text-gray-600">{expert.full_name}</p>
            </div>
          </div>

          {/* Location & Rate */}
          <div className="flex items-center gap-3 mt-2 text-xs text-gray-500">
            {expert.region && (
              <span className="flex items-center gap-1">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" /><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" /></svg>
                {expert.region}
              </span>
            )}
            {expert.rate_per_hour && (
              <span className="flex items-center gap-1">
                <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1M21 12a9 9 0 11-18 0 9 9 0 0118 0z" /></svg>
                USD ${expert.rate_per_hour}/hour
              </span>
            )}
          </div>

          {/* Overview snippet */}
          {expert.ai_overview_snippet && (
            <p className="mt-3 text-xs text-gray-600 line-clamp-2">{expert.ai_overview_snippet}</p>
          )}

          {/* Expertise bullets preview */}
          {expert.project_expertise.length > 0 && (
            <ul className="mt-2 space-y-1">
              {expert.project_expertise.slice(0, 2).map((item, i) => (
                <li key={i} className="text-xs text-gray-500 flex items-start gap-1">
                  <span className="text-gray-400 mt-0.5">•</span>
                  <span className="line-clamp-1">{item}</span>
                </li>
              ))}
            </ul>
          )}

          {/* LinkedIn */}
          {expert.linkedin_url && (
            <a
              href={expert.linkedin_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 mt-2 text-xs text-blue-600 hover:text-blue-800"
            >
              <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor"><path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/></svg>
              LinkedIn
            </a>
          )}
        </div>

        {/* Right side: status + actions */}
        <div className="flex flex-col items-end gap-2 ml-4">
          <StatusBadge status={expert.status} />
          {expert.relevance_score != null && (
            <span className={`text-xs font-semibold px-2 py-0.5 rounded ${
              expert.relevance_score >= 80 ? 'bg-green-100 text-green-700' :
              expert.relevance_score >= 60 ? 'bg-yellow-100 text-yellow-700' :
              'bg-gray-100 text-gray-600'
            }`}>
              {Math.round(expert.relevance_score)}%
            </span>
          )}
          <Link
            to={`/projects/${projectId}/experts/${expert.id}`}
            className="text-xs text-blue-600 hover:text-blue-800 font-medium"
          >
            View Profile →
          </Link>
        </div>
      </div>
    </div>
  );
}
