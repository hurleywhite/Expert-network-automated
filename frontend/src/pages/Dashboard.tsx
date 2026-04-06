import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { projectsApi, expertNetworkApi } from '../api/client';
import type { Project } from '../types';

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [docText, setDocText] = useState('');
  const [creating, setCreating] = useState(false);

  useEffect(() => {
    projectsApi.list().then((data) => {
      setProjects(data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const handleCreateFromDoc = async () => {
    if (!docText.trim()) return;
    setCreating(true);
    try {
      await expertNetworkApi.createFromDocument(docText);
      const updated = await projectsApi.list();
      setProjects(updated);
      setShowCreate(false);
      setDocText('');
    } catch (err) {
      console.error('Failed to create project:', err);
    }
    setCreating(false);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Nav Header */}
      <nav className="bg-slate-900 text-white">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <span className="text-lg font-bold tracking-tight">myExpertNetwork</span>
            <div className="flex items-center gap-4 text-sm">
              <span className="text-white font-medium border-b-2 border-white pb-1">My Projects</span>
              <span className="text-gray-400 hover:text-white cursor-pointer">Events & Library</span>
            </div>
          </div>
          <div className="flex items-center gap-4 text-sm">
            <span className="text-gray-300">ArcticBlue AI</span>
          </div>
        </div>
      </nav>

      {/* Content */}
      <div className="max-w-7xl mx-auto px-6 py-8">
        <div className="flex items-center justify-between mb-8">
          <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
          <button
            onClick={() => setShowCreate(!showCreate)}
            className="px-4 py-2 bg-slate-800 text-white rounded-lg text-sm font-medium hover:bg-slate-700"
          >
            + New Project from Document
          </button>
        </div>

        {/* Create from Document Form */}
        {showCreate && (
          <div className="bg-white border rounded-lg p-6 mb-8">
            <h2 className="text-lg font-semibold mb-4">Create Project from Requirements Document</h2>
            <p className="text-sm text-gray-500 mb-4">
              Paste your project requirements, research brief, or expert sourcing criteria below.
              AI will extract categories, screener questions, and search criteria automatically.
            </p>
            <textarea
              value={docText}
              onChange={(e) => setDocText(e.target.value)}
              placeholder="Paste your requirements document here..."
              className="w-full h-48 border rounded-lg p-4 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
            />
            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={() => { setShowCreate(false); setDocText(''); }}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={handleCreateFromDoc}
                disabled={creating || !docText.trim()}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                {creating ? 'Creating...' : 'Create Project'}
              </button>
            </div>
          </div>
        )}

        {/* Project List */}
        {loading ? (
          <p className="text-gray-500">Loading projects...</p>
        ) : projects.length === 0 ? (
          <div className="text-center py-16">
            <p className="text-gray-400 text-lg">No projects yet.</p>
            <p className="text-gray-400 text-sm mt-2">Create one from a requirements document to get started.</p>
          </div>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
            {projects.map((project) => (
              <Link
                key={project.id}
                to={`/projects/${project.id}`}
                className="bg-white border rounded-lg p-5 hover:shadow-md transition-shadow"
              >
                <h3 className="text-base font-semibold text-gray-900 mb-2">{project.name}</h3>
                <div className="text-xs text-gray-500 space-y-1">
                  {project.industry && <p>Industry: {project.industry}</p>}
                  {project.keywords?.length > 0 && (
                    <div className="flex flex-wrap gap-1 mt-2">
                      {project.keywords.slice(0, 5).map((kw) => (
                        <span key={kw} className="bg-gray-100 text-gray-600 px-2 py-0.5 rounded text-xs">{kw}</span>
                      ))}
                    </div>
                  )}
                  <p className="text-gray-400 mt-2">
                    Created {new Date(project.created_at).toLocaleDateString()}
                  </p>
                </div>
              </Link>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
