import { useState, useEffect } from 'react';
import { useParams, Link } from 'react-router-dom';
import { projectsApi, expertNetworkApi, linkedInApi } from '../api/client';
import type { Project, ProjectCategory, ExpertCard, LinkedInOutreachItem } from '../types';
import CategorySection from '../components/CategorySection';
import StatusBadge from '../components/StatusBadge';

type Tab = 'experts' | 'all-experts' | 'outreach' | 'linkedin';

export default function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>();
  const [project, setProject] = useState<Project | null>(null);
  const [categories, setCategories] = useState<ProjectCategory[]>([]);
  const [expertsByCategory, setExpertsByCategory] = useState<Record<string, ExpertCard[]>>({});
  const [allExperts, setAllExperts] = useState<ExpertCard[]>([]);
  const [linkedInOutreach, setLinkedInOutreach] = useState<LinkedInOutreachItem[]>([]);
  const [activeTab, setActiveTab] = useState<Tab>('experts');
  const [loading, setLoading] = useState(true);
  const [sourcing, setSourcing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [generatingLinkedIn, setGeneratingLinkedIn] = useState(false);

  useEffect(() => {
    if (!projectId) return;
    loadData();
  }, [projectId]);

  const loadData = async () => {
    if (!projectId) return;
    setLoading(true);
    try {
      const [proj, cats, expertsData] = await Promise.all([
        projectsApi.get(projectId),
        expertNetworkApi.getCategories(projectId).catch(() => []),
        expertNetworkApi.getExperts(projectId).catch(() => ({ experts: [] })),
      ]);

      setProject(proj);
      setCategories(cats);
      setAllExperts(expertsData.experts);

      // Group experts by category
      const grouped: Record<string, ExpertCard[]> = {};
      for (const cat of cats) {
        grouped[cat.id] = expertsData.experts.filter(e => e.category?.id === cat.id);
      }
      // Uncategorized
      const uncategorized = expertsData.experts.filter(e => !e.category);
      if (uncategorized.length > 0) {
        grouped['uncategorized'] = uncategorized;
      }
      setExpertsByCategory(grouped);
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  const handleSourceAll = async () => {
    if (!projectId) return;
    setSourcing(true);
    try {
      await expertNetworkApi.sourceAllCategories(projectId, 25);
      await loadData();
    } catch (err) {
      console.error(err);
    }
    setSourcing(false);
  };

  const handleGenerateProfiles = async () => {
    if (!projectId) return;
    setGenerating(true);
    try {
      await expertNetworkApi.generateProfiles(projectId, 50);
      await loadData();
    } catch (err) {
      console.error(err);
    }
    setGenerating(false);
  };

  const handleGenerateLinkedIn = async () => {
    if (!projectId) return;
    setGeneratingLinkedIn(true);
    try {
      await linkedInApi.generateOutreach(projectId, { min_relevance_score: 50, limit: 20 });
      const status = await linkedInApi.getOutreachStatus(projectId);
      setLinkedInOutreach(status.outreach);
      setActiveTab('linkedin');
    } catch (err) {
      console.error(err);
    }
    setGeneratingLinkedIn(false);
  };

  const loadLinkedInStatus = async () => {
    if (!projectId) return;
    try {
      const status = await linkedInApi.getOutreachStatus(projectId);
      setLinkedInOutreach(status.outreach);
    } catch (err) {
      console.error(err);
    }
  };

  if (loading) return <div className="p-8 text-gray-500">Loading project...</div>;
  if (!project) return <div className="p-8 text-red-500">Project not found</div>;

  const tabs: { key: Tab; label: string }[] = [
    { key: 'experts', label: `Experts by Category (${allExperts.length})` },
    { key: 'all-experts', label: 'All Experts' },
    { key: 'outreach', label: 'Email Outreach' },
    { key: 'linkedin', label: 'LinkedIn Outreach' },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Nav */}
      <nav className="bg-slate-900 text-white">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/" className="text-lg font-bold tracking-tight">myExpertNetwork</Link>
          </div>
          <span className="text-sm text-gray-300">ArcticBlue AI</span>
        </div>
      </nav>

      {/* Project Header */}
      <div className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <Link to="/" className="text-sm text-blue-600 hover:text-blue-800 mb-2 inline-block">← All Projects</Link>
          <h1 className="text-2xl font-bold text-gray-900">{project.name}</h1>
          {project.industry && <p className="text-sm text-gray-500 mt-1">Industry: {project.industry}</p>}

          {/* Action buttons */}
          <div className="flex flex-wrap items-center gap-3 mt-4">
            <button
              onClick={handleSourceAll}
              disabled={sourcing || categories.length === 0}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {sourcing ? 'Sourcing...' : 'Source Experts (All Categories)'}
            </button>
            <button
              onClick={handleGenerateProfiles}
              disabled={generating || allExperts.length === 0}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
            >
              {generating ? 'Generating...' : 'Generate AI Profiles'}
            </button>
            <button
              onClick={handleGenerateLinkedIn}
              disabled={generatingLinkedIn || allExperts.length === 0}
              className="px-4 py-2 bg-slate-700 text-white rounded-lg text-sm font-medium hover:bg-slate-600 disabled:opacity-50"
            >
              {generatingLinkedIn ? 'Generating...' : 'Generate LinkedIn Outreach'}
            </button>
          </div>

          {/* Tabs */}
          <div className="flex items-center gap-6 mt-6 border-b -mb-px">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => {
                  setActiveTab(tab.key);
                  if (tab.key === 'linkedin') loadLinkedInStatus();
                }}
                className={`pb-3 text-sm font-medium border-b-2 transition-colors ${
                  activeTab === tab.key
                    ? 'border-blue-600 text-blue-600'
                    : 'border-transparent text-gray-500 hover:text-gray-700'
                }`}
              >
                {tab.label}
              </button>
            ))}
          </div>
        </div>
      </div>

      {/* Tab Content */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        {/* Experts by Category */}
        {activeTab === 'experts' && (
          <div>
            {categories.length === 0 ? (
              <div className="text-center py-16">
                <p className="text-gray-400">No categories defined yet.</p>
                <p className="text-gray-400 text-sm mt-1">Create the project from a requirements document to auto-generate categories.</p>
              </div>
            ) : (
              categories.map((cat) => (
                <CategorySection
                  key={cat.id}
                  category={cat}
                  experts={expertsByCategory[cat.id] || []}
                  projectId={projectId!}
                />
              ))
            )}
            {/* Uncategorized */}
            {expertsByCategory['uncategorized']?.length > 0 && (
              <CategorySection
                category={{ id: 'uncategorized', name: 'Uncategorized', description: '', search_criteria: {}, expert_count: expertsByCategory['uncategorized'].length, sort_order: 999 }}
                experts={expertsByCategory['uncategorized']}
                projectId={projectId!}
              />
            )}
          </div>
        )}

        {/* All Experts flat list */}
        {activeTab === 'all-experts' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">{allExperts.length} Experts</h2>
              <div className="flex items-center gap-2 text-sm text-gray-500">
                <span>Sort by:</span>
                <select className="border rounded px-2 py-1 text-sm">
                  <option>Relevance Score</option>
                  <option>Name</option>
                  <option>Company</option>
                </select>
              </div>
            </div>
            <div className="space-y-3">
              {allExperts.map((expert) => (
                <div key={expert.id} className="bg-white border rounded-lg p-4 flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <div className="w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center text-white font-semibold text-sm">
                      {expert.full_name?.split(' ').map(n => n[0]).join('').slice(0, 2)}
                    </div>
                    <div>
                      <Link to={`/projects/${projectId}/experts/${expert.id}`} className="text-sm font-semibold text-gray-900 hover:text-blue-600">
                        {expert.full_name}
                      </Link>
                      <p className="text-xs text-gray-500">{expert.title} at {expert.company}</p>
                    </div>
                  </div>
                  <div className="flex items-center gap-4">
                    {expert.category && <span className="text-xs text-gray-400">{expert.category.name}</span>}
                    <StatusBadge status={expert.status} />
                    {expert.relevance_score != null && (
                      <span className="text-sm font-semibold text-gray-600">{Math.round(expert.relevance_score)}%</span>
                    )}
                    {expert.linkedin_url && (
                      <a href={expert.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:text-blue-700">
                        <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/></svg>
                      </a>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Email Outreach (existing functionality link) */}
        {activeTab === 'outreach' && (
          <div className="text-center py-16">
            <p className="text-gray-500">Email outreach uses the existing draft review workflow.</p>
            <p className="text-gray-400 text-sm mt-2">Score candidates, generate drafts, review, and send via the API.</p>
          </div>
        )}

        {/* LinkedIn Outreach */}
        {activeTab === 'linkedin' && (
          <div>
            <div className="flex items-center justify-between mb-6">
              <h2 className="text-lg font-semibold text-gray-900">LinkedIn Outreach</h2>
              <button
                onClick={loadLinkedInStatus}
                className="text-sm text-blue-600 hover:text-blue-800"
              >
                Refresh
              </button>
            </div>

            {linkedInOutreach.length === 0 ? (
              <div className="text-center py-16">
                <p className="text-gray-400">No LinkedIn outreach generated yet.</p>
                <p className="text-gray-400 text-sm mt-1">Click "Generate LinkedIn Outreach" above to create personalized connection notes.</p>
              </div>
            ) : (
              <div className="space-y-3">
                {linkedInOutreach.map((item) => (
                  <div key={item.id} className="bg-white border rounded-lg p-4">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="text-sm font-semibold text-gray-900">{item.full_name}</p>
                        <p className="text-xs text-gray-500">{item.title} at {item.company}</p>
                        <div className="mt-2 p-3 bg-gray-50 rounded text-xs text-gray-600">
                          <p className="font-medium text-gray-700 mb-1">Connection Note:</p>
                          <p>{item.connection_note}</p>
                        </div>
                        <a href={item.linkedin_url} target="_blank" rel="noopener noreferrer" className="inline-flex items-center gap-1 mt-2 text-xs text-blue-600 hover:text-blue-800">
                          <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor"><path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/></svg>
                          View Profile
                        </a>
                      </div>
                      <div className="flex flex-col items-end gap-2">
                        <StatusBadge status={item.status} />
                        {item.sent_at && <span className="text-xs text-gray-400">Sent {new Date(item.sent_at).toLocaleDateString()}</span>}
                        {item.error_message && <span className="text-xs text-red-500">{item.error_message}</span>}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
