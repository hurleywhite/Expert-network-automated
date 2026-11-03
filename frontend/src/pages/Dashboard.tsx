import { useState, useEffect, useRef } from 'react';
import { Link } from 'react-router-dom';
import { projectsApi, expertNetworkApi, ACCEPTED_EXTENSIONS, MAX_UPLOAD_BYTES, humanSize } from '../api/client';
import type { Project } from '../types';

export default function Dashboard() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreate, setShowCreate] = useState(false);
  const [docText, setDocText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const fileInputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    projectsApi.list().then((data) => {
      setProjects(data);
      setLoading(false);
    }).catch(() => setLoading(false));
  }, []);

  const reset = () => {
    setShowCreate(false);
    setDocText('');
    setFile(null);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = '';
  };

  const selectFile = (candidate: File | undefined) => {
    setError(null);
    if (!candidate) return;

    const ext = candidate.name.slice(candidate.name.lastIndexOf('.')).toLowerCase();
    if (!ACCEPTED_EXTENSIONS.includes(ext)) {
      setError(
        `"${candidate.name}" isn't a supported file type. Supported: ${ACCEPTED_EXTENSIONS.join(', ')}.`,
      );
      return;
    }
    if (candidate.size > MAX_UPLOAD_BYTES) {
      setError(`That file is ${humanSize(candidate.size)}, over the 3 MB limit — paste the relevant section below instead.`);
      return;
    }
    setFile(candidate);
  };

  const handleCreate = async () => {
    if (!file && !docText.trim()) return;
    setCreating(true);
    setError(null);
    try {
      if (file) await expertNetworkApi.createFromFile(file);
      else await expertNetworkApi.createFromDocument(docText);

      const updated = await projectsApi.list();
      setProjects(updated);
      reset();
    } catch (err: any) {
      // Surface the API's own message: it explains bad uploads, missing keys
      // and unreadable scans specifically.
      setError(String(err?.message || err).replace(/^API error \d+:\s*/, ''));
    }
    setCreating(false);
  };

  return (
    <div className="min-h-screen bg-gray-50">
      {/* Nav Header */}
      <nav className="bg-[#1fa0dc] text-white">
        <div className="max-w-7xl mx-auto px-6 py-3 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <div className="flex items-center gap-2">
              <img src="/arcticblue-logo.png" alt="ArcticBlue" className="h-8 w-auto" />
              <span className="text-lg font-bold tracking-tight">ExpertNetwork Outreach</span>
            </div>
            <div className="flex items-center gap-4 text-sm">
              <span className="text-white font-medium border-b-2 border-white pb-1">My Projects</span>
            </div>
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
              Upload your project requirements, research brief, or expert sourcing criteria —
              or paste the text. AI will extract categories, screener questions, and search
              criteria automatically.
            </p>

            {/* Upload */}
            <div
              onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
              onDragLeave={() => setDragging(false)}
              onDrop={(e) => {
                e.preventDefault();
                setDragging(false);
                selectFile(e.dataTransfer.files?.[0]);
              }}
              onClick={() => fileInputRef.current?.click()}
              role="button"
              tabIndex={0}
              onKeyDown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  fileInputRef.current?.click();
                }
              }}
              className={`border-2 border-dashed rounded-lg p-6 text-center cursor-pointer transition-colors ${
                dragging
                  ? 'border-blue-500 bg-blue-50'
                  : file
                  ? 'border-green-400 bg-green-50'
                  : 'border-gray-300 hover:border-gray-400 bg-gray-50'
              }`}
            >
              <input
                ref={fileInputRef}
                type="file"
                className="hidden"
                accept={ACCEPTED_EXTENSIONS.join(',')}
                onChange={(e) => selectFile(e.target.files?.[0])}
              />
              {file ? (
                <div className="flex items-center justify-center gap-3 text-sm">
                  <span className="font-medium text-gray-900">{file.name}</span>
                  <span className="text-gray-500">{humanSize(file.size)}</span>
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      setFile(null);
                      setError(null);
                      if (fileInputRef.current) fileInputRef.current.value = '';
                    }}
                    className="text-gray-400 hover:text-red-600 font-medium"
                    aria-label="Remove file"
                  >
                    Remove
                  </button>
                </div>
              ) : (
                <>
                  <p className="text-sm text-gray-700 font-medium">
                    Drop a document here, or <span className="text-blue-600 underline">browse</span>
                  </p>
                  <p className="text-xs text-gray-400 mt-1">
                    PDF, Word (.docx), Markdown, text, CSV or JSON — up to 3 MB
                  </p>
                </>
              )}
            </div>

            {/* Paste alternative */}
            <div className="flex items-center gap-3 my-4">
              <div className="h-px bg-gray-200 flex-1" />
              <span className="text-xs text-gray-400 uppercase tracking-wide">or paste text</span>
              <div className="h-px bg-gray-200 flex-1" />
            </div>

            <textarea
              value={docText}
              onChange={(e) => { setDocText(e.target.value); setError(null); }}
              disabled={!!file}
              placeholder={file ? 'Using the uploaded file above.' : 'Paste your requirements document here...'}
              className="w-full h-40 border rounded-lg p-4 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-50 disabled:text-gray-400"
            />

            {error && (
              <p className="mt-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">
                {error}
              </p>
            )}

            <div className="flex justify-end gap-3 mt-4">
              <button
                onClick={reset}
                className="px-4 py-2 text-sm text-gray-600 hover:text-gray-800"
              >
                Cancel
              </button>
              <button
                onClick={handleCreate}
                disabled={creating || (!file && !docText.trim())}
                className="px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
              >
                {creating ? (file ? 'Reading document...' : 'Creating...') : 'Create Project'}
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
