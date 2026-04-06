import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { expertNetworkApi } from '../api/client';
import type { ExpertProfileFull, ScreenerQuestion } from '../types';
import StatusBadge from '../components/StatusBadge';
import ScreenerPanel from '../components/ScreenerPanel';

export default function ExpertProfile() {
  const { projectId, expertId } = useParams<{ projectId: string; expertId: string }>();
  const [profile, setProfile] = useState<ExpertProfileFull | null>(null);
  const [questions, setQuestions] = useState<ScreenerQuestion[]>([]);
  const [showScreener, setShowScreener] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!expertId || !projectId) return;
    Promise.all([
      expertNetworkApi.getExpertProfile(expertId),
      expertNetworkApi.getScreenerQuestions(projectId),
    ]).then(([p, q]) => {
      setProfile(p);
      setQuestions(q);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, [expertId, projectId]);

  if (loading) return <div className="p-8 text-gray-500">Loading profile...</div>;
  if (!profile) return <div className="p-8 text-red-500">Expert not found</div>;

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Back link */}
      <div className="max-w-6xl mx-auto px-6 pt-4">
        <Link to={`/projects/${projectId}`} className="text-sm text-blue-600 hover:text-blue-800">
          ← Back to Project
        </Link>
      </div>

      {/* AI Generated badge */}
      <div className="max-w-6xl mx-auto px-6 pt-4">
        <span className="inline-flex items-center gap-1 text-xs text-blue-600 bg-blue-50 px-2 py-1 rounded">
          <svg className="w-3 h-3" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" /></svg>
          AI-Generated
        </span>
      </div>

      {/* Header */}
      <div className="max-w-6xl mx-auto px-6 py-4">
        <div className="flex items-start justify-between">
          <div>
            <h1 className="text-2xl font-bold text-gray-900">
              {profile.title ? `${profile.title}` : 'Expert'}
              {profile.company && ` at ${profile.company}`}
            </h1>
            <p className="text-lg text-gray-600 mt-1">{profile.full_name}</p>
            <div className="flex items-center gap-4 mt-2 text-sm text-gray-500">
              {profile.region && (
                <span className="flex items-center gap-1">
                  <svg className="w-4 h-4 text-blue-500" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M17.657 16.657L13.414 20.9a1.998 1.998 0 01-2.827 0l-4.244-4.243a8 8 0 1111.314 0z" /></svg>
                  {profile.region}
                </span>
              )}
              {profile.rate_per_hour && (
                <span className="flex items-center gap-1">
                  <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8c-1.657 0-3 .895-3 2s1.343 2 3 2 3 .895 3 2-1.343 2-3 2m0-8c1.11 0 2.08.402 2.599 1M12 8V7m0 1v8m0 0v1m0-1c-1.11 0-2.08-.402-2.599-1" /></svg>
                  Rate: USD ${profile.rate_per_hour}/hour
                </span>
              )}
            </div>
          </div>

          {/* Action buttons */}
          <div className="flex items-center gap-3">
            <button
              onClick={() => setShowScreener(true)}
              className="flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-sm font-medium text-gray-700 hover:bg-gray-50"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" /></svg>
              View Screeners
            </button>
            <button
              onClick={() => expertNetworkApi.scheduleCall(profile.id)}
              className="flex items-center gap-2 px-4 py-2 bg-slate-800 text-white rounded-lg text-sm font-medium hover:bg-slate-700"
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5a2 2 0 012-2h3.28a1 1 0 01.948.684l1.498 4.493a1 1 0 01-.502 1.21l-2.257 1.13a11.042 11.042 0 005.516 5.516l1.13-2.257a1 1 0 011.21-.502l4.493 1.498a1 1 0 01.684.949V19a2 2 0 01-2 2h-1C9.716 21 3 14.284 3 6V5z" /></svg>
              Schedule Call
            </button>
          </div>
        </div>
      </div>

      {/* Content Grid */}
      <div className="max-w-6xl mx-auto px-6 pb-12 grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* Overview Card */}
        <div className="bg-white rounded-lg border p-6">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-base font-semibold text-gray-900">Overview</h2>
            <StatusBadge status={profile.status} />
          </div>
          <div className="text-sm text-gray-600 leading-relaxed whitespace-pre-line">
            {profile.ai_overview || 'No AI overview generated yet.'}
          </div>
        </div>

        {/* Project Expertise Card */}
        <div className="bg-white rounded-lg border p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">Project Expertise</h2>
          {profile.project_expertise.length > 0 ? (
            <ul className="space-y-3">
              {profile.project_expertise.map((item, i) => (
                <li key={i} className="flex items-start gap-2 text-sm text-gray-600">
                  <span className="text-gray-400 mt-1 flex-shrink-0">•</span>
                  {item}
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-sm text-gray-400 italic">No expertise data generated yet.</p>
          )}
        </div>

        {/* Activity Card */}
        <div className="bg-white rounded-lg border p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">Activity</h2>
          {profile.activities.length > 0 ? (
            <div className="space-y-3">
              {profile.activities.map((activity) => (
                <div key={activity.id} className="flex items-start gap-3">
                  <div className="w-2 h-2 rounded-full bg-gray-300 mt-2 flex-shrink-0" />
                  <div>
                    <p className="text-sm text-gray-700">{activity.description}</p>
                    <p className="text-xs text-gray-400">
                      {new Date(activity.created_at).toLocaleDateString('en-US', { month: 'short', day: 'numeric', year: 'numeric' })}
                    </p>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-sm text-gray-400 italic">No activity yet.</p>
          )}
        </div>

        {/* Work Experience Card */}
        <div className="bg-white rounded-lg border p-6">
          <h2 className="text-base font-semibold text-gray-900 mb-4">Work Experience</h2>
          {profile.work_experience.length > 0 ? (
            <table className="w-full text-sm">
              <tbody>
                {profile.work_experience.map((exp, i) => (
                  <tr key={i} className="border-b last:border-0">
                    <td className="py-2 pr-4 text-gray-500 whitespace-nowrap align-top">{exp.date_range}</td>
                    <td className="py-2 text-gray-700">
                      <span className="font-medium">{exp.title}</span>
                      {exp.company && <span className="text-gray-500"> at {exp.company}</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-gray-400 italic">No work experience data available.</p>
          )}
        </div>

        {/* LinkedIn & Contact Card */}
        <div className="bg-white rounded-lg border p-6 lg:col-span-2">
          <h2 className="text-base font-semibold text-gray-900 mb-4">Contact & Links</h2>
          <div className="flex flex-wrap gap-4">
            {profile.linkedin_url && (
              <a
                href={profile.linkedin_url}
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-2 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm hover:bg-blue-700"
              >
                <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/></svg>
                View LinkedIn Profile
              </a>
            )}
            {profile.email && (
              <a
                href={`mailto:${profile.email}`}
                className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 rounded-lg text-sm text-gray-700 hover:bg-gray-50"
              >
                <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" /></svg>
                {profile.email}
              </a>
            )}
            {profile.linkedin_outreach && (
              <div className="flex items-center gap-2 px-4 py-2 bg-gray-50 rounded-lg text-sm text-gray-600">
                LinkedIn Outreach: <StatusBadge status={profile.linkedin_outreach.status} />
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Screener Panel Overlay */}
      {showScreener && (
        <>
          <div className="fixed inset-0 bg-black/30 z-40" onClick={() => setShowScreener(false)} />
          <ScreenerPanel
            expertName={profile.full_name}
            questions={questions}
            responses={profile.screener_responses}
            onClose={() => setShowScreener(false)}
          />
        </>
      )}
    </div>
  );
}
