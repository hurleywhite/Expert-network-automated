import { useState, useEffect } from 'react';
import { useParams, Link, useNavigate } from 'react-router-dom';
import { projectsApi, expertNetworkApi, outreachApi } from '../api/client';
import type { Project, ProjectCategory, ExpertCard, OutreachCampaign } from '../types';
import CategorySection from '../components/CategorySection';
import StatusBadge from '../components/StatusBadge';

type Tab = 'experts' | 'all-experts' | 'campaigns';

export default function ProjectDetail() {
  const { projectId } = useParams<{ projectId: string }>();
  const navigate = useNavigate();
  const [project, setProject] = useState<Project | null>(null);
  const [allProjects, setAllProjects] = useState<Project[]>([]);
  const [projectMenuOpen, setProjectMenuOpen] = useState(false);
  const [categories, setCategories] = useState<ProjectCategory[]>([]);
  const [expertsByCategory, setExpertsByCategory] = useState<Record<string, ExpertCard[]>>({});
  const [allExperts, setAllExperts] = useState<ExpertCard[]>([]);
  const [campaigns, setCampaigns] = useState<OutreachCampaign[]>([]);
  const [selectedCampaign, setSelectedCampaign] = useState<any>(null);
  const [activeTab, setActiveTab] = useState<Tab>('experts');
  const [loading, setLoading] = useState(true);
  const [sourcing, setSourcing] = useState(false);
  const [generating, setGenerating] = useState(false);
  const [creatingCampaign, setCreatingCampaign] = useState(false);
  const [expandedLead, setExpandedLead] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ kind: 'ok' | 'warn' | 'error'; text: string } | null>(null);
  const [sourceCount, setSourceCount] = useState(25);

  useEffect(() => {
    if (!projectId) return;
    loadData();
  }, [projectId]);

  useEffect(() => {
    projectsApi.list().then(setAllProjects).catch(() => {});
  }, []);

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

      const grouped: Record<string, ExpertCard[]> = {};
      for (const cat of cats) {
        grouped[cat.id] = expertsData.experts.filter(e => e.category?.id === cat.id);
      }
      const uncategorized = expertsData.experts.filter(e => !e.category);
      if (uncategorized.length > 0) grouped['uncategorized'] = uncategorized;
      setExpertsByCategory(grouped);
    } catch (err) {
      console.error(err);
    }
    setLoading(false);
  };

  const loadCampaigns = async () => {
    if (!projectId) return;
    try {
      const data = await outreachApi.listCampaigns(projectId);
      setCampaigns(data);
    } catch (err) {
      console.error(err);
    }
  };

  // Each of these used to swallow its error, so "it failed", "it added nobody"
  // and "it worked" were indistinguishable from the outside.
  const report = (err: unknown) =>
    setNotice({ kind: 'error', text: String((err as Error)?.message || err).replace(/^API error \d+:\s*/, '') });

  const handleSourceAll = async () => {
    if (!projectId) return;
    setSourcing(true);
    setNotice(null);
    try {
      const r = await expertNetworkApi.sourceAllCategories(projectId, sourceCount);
      await loadData();
      setNotice({ kind: r.total_sourced > 0 ? 'ok' : 'warn', text: r.message });
    } catch (err) {
      report(err);
    }
    setSourcing(false);
  };

  const handleGenerateProfiles = async () => {
    if (!projectId) return;
    setGenerating(true);
    setNotice(null);
    try {
      const r = await expertNetworkApi.generateProfiles(projectId, 50);
      await loadData();
      setNotice({
        kind: r.profiled > 0 ? 'ok' : 'warn',
        text: r.profiled > 0
          ? `Generated ${r.profiled} profile${r.profiled === 1 ? '' : 's'}.`
          : 'No profiles needed generating — every sourced expert already has one.',
      });
    } catch (err) {
      report(err);
    }
    setGenerating(false);
  };

  const handleCreateCampaign = async () => {
    if (!projectId) return;
    setCreatingCampaign(true);
    try {
      const result = await outreachApi.createCampaign(projectId, {
        min_relevance_score: 50,
        limit: 25,
      });
      // Load the new campaign detail
      if (result.campaign_id) {
        const detail = await outreachApi.getCampaignDetail(result.campaign_id);
        setSelectedCampaign(detail);
      }
      await loadCampaigns();
      setActiveTab('campaigns');
      setNotice({
        kind: result?.leads_created > 0 ? 'ok' : 'warn',
        text: result?.leads_created > 0
          ? `Created a campaign with ${result.leads_created} leads.`
          : result?.message || 'No qualified experts matched. Generate profiles first, or lower the relevance threshold.',
      });
    } catch (err) {
      report(err);
    }
    setCreatingCampaign(false);
  };

  const handleViewCampaign = async (campaignId: string) => {
    try {
      const detail = await outreachApi.getCampaignDetail(campaignId);
      setSelectedCampaign(detail);
    } catch (err) {
      console.error(err);
    }
  };

  if (loading) return <div className="p-8 text-gray-500">Loading project...</div>;
  if (!project) return <div className="p-8 text-red-500">Project not found</div>;

  const tabs: { key: Tab; label: string }[] = [
    { key: 'experts', label: `Experts by Category (${allExperts.length})` },
    { key: 'all-experts', label: 'All Experts' },
    { key: 'campaigns', label: 'Outreach Campaigns' },
  ];

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Nav */}
      <nav className="bg-[#1fa0dc] text-white">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/" className="flex items-center gap-2">
              <img src="/arcticblue-logo.png" alt="ArcticBlue" className="h-8 w-auto" />
              <span className="text-lg font-bold tracking-tight">ExpertNetwork Outreach</span>
            </Link>
          </div>
        </div>
      </nav>

      {/* Project Header */}
      <div className="bg-white border-b">
        <div className="max-w-7xl mx-auto px-6 py-6">
          <Link to="/" className="text-sm text-blue-600 hover:text-blue-800 mb-2 inline-block">&larr; All Projects</Link>
          <div className="relative">
            <button
              onClick={() => setProjectMenuOpen((o) => !o)}
              className="inline-flex items-center gap-2 text-2xl font-bold text-gray-900 hover:text-gray-700"
            >
              {project.name}
              <svg
                className={`w-5 h-5 text-gray-400 transition-transform ${projectMenuOpen ? 'rotate-180' : ''}`}
                fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
              >
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {projectMenuOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setProjectMenuOpen(false)} />
                <div className="absolute left-0 mt-2 w-80 max-h-96 overflow-auto bg-white border border-gray-200 rounded-lg shadow-lg z-20 py-1">
                  {allProjects.map((p) => (
                    <button
                      key={p.id}
                      onClick={() => {
                        setProjectMenuOpen(false);
                        if (p.id !== projectId) navigate(`/projects/${p.id}`);
                      }}
                      className={`w-full text-left px-4 py-2 text-sm hover:bg-gray-50 ${
                        p.id === projectId ? 'bg-blue-50 text-blue-700 font-semibold' : 'text-gray-700'
                      }`}
                    >
                      {p.name}
                      {p.industry && <span className="block text-xs text-gray-400">{p.industry}</span>}
                    </button>
                  ))}
                  {allProjects.length === 0 && (
                    <div className="px-4 py-2 text-sm text-gray-400">No projects found</div>
                  )}
                </div>
              </>
            )}
          </div>
          {project.industry && <p className="text-sm text-gray-500 mt-1">Industry: {project.industry}</p>}

          {/* Action buttons */}
          <div className="flex flex-wrap items-center gap-3 mt-4">
            <button
              onClick={handleSourceAll}
              disabled={sourcing || categories.length === 0}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
            >
              {sourcing ? `Sourcing ${sourceCount}/category…` : `Source ${sourceCount} per Category (Apollo)`}
            </button>
            <select
              value={sourceCount}
              onChange={(e) => setSourceCount(Number(e.target.value))}
              disabled={sourcing}
              aria-label="Experts to source per category"
              className="px-2 py-2 border rounded-lg text-sm text-gray-700 bg-white"
            >
              {[10, 25, 50, 100].map((n) => (
                <option key={n} value={n}>{n} / category</option>
              ))}
            </select>
            <button
              onClick={handleGenerateProfiles}
              disabled={generating || allExperts.length === 0}
              className="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
            >
              {generating ? 'Generating...' : 'Generate AI Profiles'}
            </button>
            <button
              onClick={handleCreateCampaign}
              disabled={creatingCampaign || allExperts.length === 0}
              className="px-4 py-2 bg-emerald-600 text-white rounded-lg text-sm font-medium hover:bg-emerald-700 disabled:opacity-50"
            >
              {creatingCampaign ? 'Creating Campaign...' : 'Create Outreach Campaign'}
            </button>
          </div>

          {notice && (
            <div
              className={`mt-4 text-sm rounded-lg px-3 py-2 border flex items-start justify-between gap-4 ${
                notice.kind === 'ok'
                  ? 'bg-green-50 border-green-200 text-green-800'
                  : notice.kind === 'warn'
                  ? 'bg-amber-50 border-amber-200 text-amber-900'
                  : 'bg-red-50 border-red-200 text-red-700'
              }`}
            >
              <span>{notice.text}</span>
              <button onClick={() => setNotice(null)} className="opacity-60 hover:opacity-100" aria-label="Dismiss">×</button>
            </div>
          )}

          {/* Tabs */}
          <div className="flex items-center gap-6 mt-6 border-b -mb-px">
            {tabs.map((tab) => (
              <button
                key={tab.key}
                onClick={() => {
                  setActiveTab(tab.key);
                  if (tab.key === 'campaigns') loadCampaigns();
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
            {expertsByCategory['uncategorized']?.length > 0 && (
              <CategorySection
                category={{ id: 'uncategorized', name: 'Uncategorized', description: '', search_criteria: {}, expert_count: expertsByCategory['uncategorized'].length, sort_order: 999 }}
                experts={expertsByCategory['uncategorized']}
                projectId={projectId!}
              />
            )}
          </div>
        )}

        {/* All Experts */}
        {activeTab === 'all-experts' && (
          <div>
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-semibold text-gray-900">{allExperts.length} Experts</h2>
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

        {/* Outreach Campaigns */}
        {activeTab === 'campaigns' && (
          <div>
            {/* Campaign list */}
            {!selectedCampaign && (
              <>
                <div className="flex items-center justify-between mb-6">
                  <h2 className="text-lg font-semibold text-gray-900">Outreach Campaigns</h2>
                  <button onClick={loadCampaigns} className="text-sm text-blue-600 hover:text-blue-800">Refresh</button>
                </div>

                {campaigns.length === 0 ? (
                  <div className="text-center py-16">
                    <p className="text-gray-400">No campaigns yet.</p>
                    <p className="text-gray-400 text-sm mt-1">Click "Create Outreach Campaign" to generate personalized LinkedIn sequences for your top experts.</p>
                  </div>
                ) : (
                  <div className="space-y-4">
                    {campaigns.map((camp) => (
                      <div key={camp.id} className="bg-white border rounded-lg p-5 hover:shadow-md transition-shadow cursor-pointer" onClick={() => handleViewCampaign(camp.id)}>
                        <div className="flex items-center justify-between mb-3">
                          <h3 className="text-sm font-semibold text-gray-900">{camp.name}</h3>
                          <StatusBadge status={camp.status} />
                        </div>
                        <div className="grid grid-cols-6 gap-4 text-center">
                          <div>
                            <p className="text-xl font-bold text-gray-900">{camp.total_leads}</p>
                            <p className="text-xs text-gray-500">Leads</p>
                          </div>
                          <div>
                            <p className="text-xl font-bold text-blue-600">{camp.connections_sent}</p>
                            <p className="text-xs text-gray-500">Sent</p>
                          </div>
                          <div>
                            <p className="text-xl font-bold text-green-600">{camp.connections_accepted}</p>
                            <p className="text-xs text-gray-500">Accepted</p>
                          </div>
                          <div>
                            <p className="text-xl font-bold text-indigo-600">{camp.messages_sent}</p>
                            <p className="text-xs text-gray-500">Messages</p>
                          </div>
                          <div>
                            <p className="text-xl font-bold text-amber-600">{camp.replies_received}</p>
                            <p className="text-xs text-gray-500">Replies</p>
                          </div>
                          <div>
                            <p className="text-xl font-bold text-emerald-600">{camp.meetings_booked}</p>
                            <p className="text-xs text-gray-500">Meetings</p>
                          </div>
                        </div>
                        <p className="text-xs text-gray-400 mt-3">Created {new Date(camp.created_at).toLocaleDateString()}</p>
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}

            {/* Campaign detail view */}
            {selectedCampaign && (
              <div>
                <button
                  onClick={() => setSelectedCampaign(null)}
                  className="text-sm text-blue-600 hover:text-blue-800 mb-4 inline-block"
                >
                  &larr; Back to Campaigns
                </button>

                <div className="flex items-center justify-between mb-6">
                  <div>
                    <h2 className="text-lg font-semibold text-gray-900">{selectedCampaign.campaign.name}</h2>
                    <p className="text-sm text-gray-500">{selectedCampaign.stats.total} leads &middot; {selectedCampaign.stats.replied} replies &middot; {selectedCampaign.stats.meetings_booked} meetings</p>
                  </div>
                  <StatusBadge status={selectedCampaign.campaign.status} />
                </div>

                {/* Stats bar */}
                <div className="bg-white border rounded-lg p-4 mb-6">
                  <h3 className="text-sm font-medium text-gray-700 mb-3">Seniority Breakdown</h3>
                  <div className="flex flex-wrap gap-3">
                    {Object.entries(selectedCampaign.stats.by_seniority as Record<string, number>).map(([level, count]) => (
                      <span key={level} className="px-3 py-1 bg-slate-100 rounded-full text-xs font-medium text-slate-700">
                        {level}: {count}
                      </span>
                    ))}
                  </div>
                </div>

                {/* Leads with message sequences */}
                <div className="space-y-4">
                  {(selectedCampaign.leads || []).map((lead: any) => (
                    <div key={lead.id} className="bg-white border rounded-lg overflow-hidden">
                      {/* Lead header */}
                      <div
                        className="p-4 cursor-pointer hover:bg-gray-50 flex items-center justify-between"
                        onClick={() => setExpandedLead(expandedLead === lead.id ? null : lead.id)}
                      >
                        <div className="flex items-center gap-4">
                          <div className="w-10 h-10 rounded-full bg-slate-700 flex items-center justify-center text-white font-semibold text-sm">
                            {lead.full_name?.split(' ').map((n: string) => n[0]).join('').slice(0, 2)}
                          </div>
                          <div>
                            <p className="text-sm font-semibold text-gray-900">{lead.full_name}</p>
                            <p className="text-xs text-gray-500">{lead.title} at {lead.company}</p>
                          </div>
                        </div>
                        <div className="flex items-center gap-3">
                          {lead.seniority_level && (
                            <span className="px-2 py-0.5 bg-blue-50 text-blue-700 rounded text-xs font-medium">{lead.seniority_level}</span>
                          )}
                          {lead.linkedin_url && (
                            <a href={lead.linkedin_url} target="_blank" rel="noopener noreferrer" className="text-blue-500 hover:text-blue-700" onClick={e => e.stopPropagation()}>
                              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="currentColor"><path d="M19 0h-14c-2.761 0-5 2.239-5 5v14c0 2.761 2.239 5 5 5h14c2.762 0 5-2.239 5-5v-14c0-2.761-2.238-5-5-5zm-11 19h-3v-11h3v11zm-1.5-12.268c-.966 0-1.75-.79-1.75-1.764s.784-1.764 1.75-1.764 1.75.79 1.75 1.764-.783 1.764-1.75 1.764zm13.5 12.268h-3v-5.604c0-3.368-4-3.113-4 0v5.604h-3v-11h3v1.765c1.396-2.586 7-2.777 7 2.476v6.759z"/></svg>
                            </a>
                          )}
                          <svg className={`w-4 h-4 text-gray-400 transition-transform ${expandedLead === lead.id ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" /></svg>
                        </div>
                      </div>

                      {/* Expanded message sequence */}
                      {expandedLead === lead.id && (
                        <div className="border-t px-4 pb-4">
                          {/* Personalization context */}
                          {lead.relevance_context?.hook && (
                            <div className="mt-3 p-3 bg-amber-50 rounded-lg text-xs">
                              <p className="font-medium text-amber-800 mb-1">Personalization Hook</p>
                              <p className="text-amber-700">{lead.relevance_context.hook}</p>
                              {lead.relevance_context.angle && <p className="text-amber-600 mt-1">Angle: {lead.relevance_context.angle}</p>}
                            </div>
                          )}

                          {/* Message sequence */}
                          <div className="mt-4 space-y-4">
                            {/* Step 1: Connection */}
                            <div className="border-l-4 border-blue-400 pl-4">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs font-bold text-blue-600 uppercase">Step 1</span>
                                <span className="text-xs text-gray-500">Connection Request</span>
                                <span className="text-xs text-gray-400 ml-auto">{lead.messages.connection_note?.length || 0}/300 chars</span>
                              </div>
                              <p className="text-sm text-gray-700 bg-blue-50 p-3 rounded">{lead.messages.connection_note}</p>
                            </div>

                            {/* Step 2: Follow-up 1 */}
                            <div className="border-l-4 border-green-400 pl-4">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs font-bold text-green-600 uppercase">Step 2</span>
                                <span className="text-xs text-gray-500">Follow-up (Day 3)</span>
                              </div>
                              <p className="text-sm text-gray-700 bg-green-50 p-3 rounded whitespace-pre-line">{lead.messages.follow_up_1}</p>
                            </div>

                            {/* Step 3: Follow-up 2 */}
                            <div className="border-l-4 border-yellow-400 pl-4">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs font-bold text-yellow-600 uppercase">Step 3</span>
                                <span className="text-xs text-gray-500">Follow-up (Day 8)</span>
                              </div>
                              <p className="text-sm text-gray-700 bg-yellow-50 p-3 rounded whitespace-pre-line">{lead.messages.follow_up_2}</p>
                            </div>

                            {/* Step 4: Break-up */}
                            <div className="border-l-4 border-red-300 pl-4">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs font-bold text-red-500 uppercase">Step 4</span>
                                <span className="text-xs text-gray-500">Final (Day 15)</span>
                              </div>
                              <p className="text-sm text-gray-700 bg-red-50 p-3 rounded whitespace-pre-line">{lead.messages.follow_up_3}</p>
                            </div>

                            {/* InMail */}
                            <div className="border-l-4 border-purple-400 pl-4">
                              <div className="flex items-center gap-2 mb-1">
                                <span className="text-xs font-bold text-purple-600 uppercase">InMail</span>
                                <span className="text-xs text-gray-500">If connection not accepted</span>
                              </div>
                              <p className="text-sm text-gray-700 bg-purple-50 p-3 rounded whitespace-pre-line">{lead.messages.inmail}</p>
                            </div>
                          </div>
                        </div>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
