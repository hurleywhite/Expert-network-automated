import { useState, useEffect } from 'react';
import { Link } from 'react-router-dom';
import { projectsApi } from '../api/client';
import type { Project, PipelineStatus } from '../types';

interface ProjectWithStatus extends Project {
  status?: PipelineStatus;
}

// Clean up project names for display
function formatProjectName(name: string): string {
  // Remove "Find" prefix
  let cleaned = name.replace(/^Find\s+/i, '');
  // Capitalize first letter
  cleaned = cleaned.charAt(0).toUpperCase() + cleaned.slice(1);
  return cleaned;
}

export default function Dashboard() {
  const [projects, setProjects] = useState<ProjectWithStatus[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    loadProjects();
  }, []);

  const loadProjects = async () => {
    try {
      setLoading(true);
      const projectList = await projectsApi.list();

      // Load status for each project
      const projectsWithStatus = await Promise.all(
        projectList.map(async (project) => {
          try {
            const status = await projectsApi.getStatus(project.id);
            return { ...project, status };
          } catch {
            return project;
          }
        })
      );

      setProjects(projectsWithStatus);
      setError(null);
    } catch (err) {
      setError('Failed to load projects. Is the backend running?');
      console.error(err);
    } finally {
      setLoading(false);
    }
  };

  if (loading) {
    return (
      <div className="flex justify-center items-center h-64">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600"></div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
        <p className="font-medium">Error</p>
        <p>{error}</p>
        <button
          onClick={loadProjects}
          className="mt-2 text-sm underline hover:no-underline"
        >
          Retry
        </button>
      </div>
    );
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Projects</h1>
        <p className="text-gray-600 mt-1">
          Select a project to review and approve outreach drafts
        </p>
      </div>

      {projects.length === 0 ? (
        <div className="bg-white rounded-lg shadow border border-gray-200 p-8 text-center">
          <p className="text-gray-500">No projects found</p>
          <p className="text-sm text-gray-400 mt-2">
            Create a project using the API to get started
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {projects.map((project) => (
            <Link
              key={project.id}
              to={`/projects/${project.id}`}
              className="block bg-white rounded-lg shadow border border-gray-200 p-5 hover:shadow-md transition-shadow"
            >
              <h2 className="text-lg font-semibold text-gray-900 truncate">
                {formatProjectName(project.name)}
              </h2>

              {project.industry && (
                <p className="text-sm text-gray-500 mt-1">
                  {project.industry}
                  {project.subvertical && ` - ${project.subvertical}`}
                </p>
              )}

              {project.status && (
                <div className="mt-4 grid grid-cols-3 gap-2 text-center">
                  <div className="bg-gray-50 rounded p-2">
                    <p className="text-lg font-bold text-gray-900">
                      {project.status.pipeline.drafts_pending_review}
                    </p>
                    <p className="text-xs text-gray-500">Pending</p>
                  </div>
                  <div className="bg-green-50 rounded p-2">
                    <p className="text-lg font-bold text-green-700">
                      {project.status.pipeline.drafts_approved}
                    </p>
                    <p className="text-xs text-gray-500">Approved</p>
                  </div>
                  <div className="bg-blue-50 rounded p-2">
                    <p className="text-lg font-bold text-blue-700">
                      {project.status.pipeline.emails_sent}
                    </p>
                    <p className="text-xs text-gray-500">Sent</p>
                  </div>
                </div>
              )}

              {project.status && project.status.pipeline.drafts_with_risk_flags > 0 && (
                <div className="mt-3 flex items-center text-orange-600 text-sm">
                  <svg
                    className="h-4 w-4 mr-1"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z"
                    />
                  </svg>
                  {project.status.pipeline.drafts_with_risk_flags} drafts need manual review
                </div>
              )}

              <div className="mt-4 text-sm text-blue-600 font-medium">
                View Details &rarr;
              </div>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
