import type { VercelRequest, VercelResponse } from '@vercel/node';
import * as repo from './_lib/repo';
import { checkPassword, issueToken, sessionCookie, clearCookie, isAuthenticated } from './_lib/auth';

/**
 * Single entry point for all database reads and writes.
 *
 * This is a plain function, not a [...path] catch-all. Vercel's catch-all in
 * the api/ directory only ever matched one segment here, so /api/data/experts/<id>
 * 404'd at the edge while /api/data/experts resolved. vercel.json rewrites
 * /api/data/(.*) to this file with the rest of the path as ?path=, which is
 * deterministic and does not depend on dynamic-route resolution.
 *
 * The browser used to query Supabase directly with a public anon key. Every
 * one of those calls now lands here, where the service-role key never leaves
 * the server. Routing is done in-process rather than as one file per route so
 * the project stays far under Vercel's serverless function limit.
 *
 * Routes (all relative to /api/data):
 *   GET   projects
 *   GET   projects/:id
 *   GET   projects/:id/categories
 *   GET   projects/:id/screener-questions
 *   GET   projects/:id/experts            ?category_id=
 *   GET   projects/:id/campaigns
 *   GET   projects/:id/linkedin-outreach
 *   GET   experts/:id
 *   PATCH experts/:id                     { status }
 *   POST  experts/:id/schedule-call
 *   PATCH drafts/:id                      { subject?, body? }
 *   POST  drafts/:id/approve              { approved_by }
 *   POST  drafts/:id/reject               { rejected_by, reason? }
 */

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

class HttpError extends Error {
  statusCode: number;
  constructor(statusCode: number, message: string) {
    super(message);
    this.statusCode = statusCode;
  }
}

function requireId(value: string | undefined, label: string): string {
  if (!value || !UUID_RE.test(value)) {
    throw new HttpError(400, `${label} must be a valid UUID`);
  }
  return value;
}

function body(req: VercelRequest): Record<string, any> {
  const b = req.body;
  if (!b) return {};
  if (typeof b === 'string') {
    try {
      return JSON.parse(b);
    } catch {
      throw new HttpError(400, 'Request body is not valid JSON');
    }
  }
  return b as Record<string, any>;
}

function firstQuery(req: VercelRequest, key: string): string | undefined {
  const v = req.query[key];
  if (Array.isArray(v)) return v[0];
  return v as string | undefined;
}

/**
 * The path segments this request is for.
 *
 * Vercel normally fills req.query.path for a [...path] catch-all, but that
 * depends on its dynamic-route param injection, which does not always fire
 * when the project also declares explicit rewrites. The URL is the source of
 * truth either way, so fall back to parsing it rather than 404-ing on a
 * request that plainly names a resource.
 */
function pathSegments(req: VercelRequest): string[] {
  const raw = req.query?.path;
  // The rewrite delivers the remainder as one string ("experts/<id>"), while a
  // dynamic route would deliver an array. Accept either, and split on slashes.
  const fromQuery = (Array.isArray(raw) ? raw : raw ? [raw] : [])
    .flatMap((v) => String(v).split('/'))
    .filter(Boolean);
  if (fromQuery.length) return fromQuery.map(decodeSegment);

  const url = req.url || '';
  const pathname = url.split('?')[0];
  const marker = '/api/data';
  const i = pathname.indexOf(marker);
  if (i === -1) return [];

  return pathname
    .slice(i + marker.length)
    .split('/')
    .filter(Boolean)
    .map(decodeSegment);
}

function decodeSegment(s: string): string {
  try {
    return decodeURIComponent(s);
  } catch {
    return s;
  }
}

async function route(req: VercelRequest): Promise<unknown> {
  const segments = pathSegments(req);
  const method = (req.method || 'GET').toUpperCase();

  const [resource, id, action] = segments;

  if (!resource) throw new HttpError(404, 'No resource specified');

  // ── session (the only route reachable without a session) ──────────────────
  if (resource === 'session') {
    if (method === 'GET') return { authenticated: isAuthenticated(req) };
    if (method === 'DELETE') return { ok: true };
    if (method !== 'POST') throw new HttpError(405, `${method} not allowed on /session`);

    const { password } = body(req);
    if (!checkPassword(password)) {
      // Deliberately vague: distinguishing "no password set" from "wrong
      // password" tells an attacker which deployment to keep trying.
      throw new HttpError(401, 'Incorrect password');
    }
    return { ok: true, token: issueToken() };
  }

  // ── projects ──────────────────────────────────────────────────────────────
  if (resource === 'projects') {
    if (method !== 'GET') throw new HttpError(405, `${method} not allowed on /projects`);

    if (!id) return repo.listProjects();

    const projectId = requireId(id, 'project id');

    switch (action) {
      case undefined:
        return repo.getProject(projectId);
      case 'categories':
        return repo.listCategories(projectId);
      case 'screener-questions':
        return repo.listScreenerQuestions(projectId);
      case 'experts': {
        const categoryId = firstQuery(req, 'category_id');
        if (categoryId) requireId(categoryId, 'category_id');
        return repo.listExperts(projectId, categoryId);
      }
      case 'campaigns':
        return repo.listCampaigns(projectId);
      case 'linkedin-outreach':
        return repo.getOutreachStatus(projectId);
      default:
        throw new HttpError(404, `Unknown project sub-resource "${action}"`);
    }
  }

  // ── experts ───────────────────────────────────────────────────────────────
  if (resource === 'experts') {
    const expertId = requireId(id, 'expert id');

    if (!action) {
      if (method === 'GET') return repo.getExpertProfile(expertId);
      if (method === 'PATCH' || method === 'POST') {
        const { status } = body(req);
        if (!status) throw new HttpError(400, 'status is required');
        return repo.updateExpertStatus(expertId, String(status));
      }
      throw new HttpError(405, `${method} not allowed on /experts/:id`);
    }

    if (action === 'schedule-call') {
      if (method !== 'POST') throw new HttpError(405, `${method} not allowed on /experts/:id/schedule-call`);
      return repo.scheduleCall(expertId);
    }

    throw new HttpError(404, `Unknown expert sub-resource "${action}"`);
  }

  // ── drafts ────────────────────────────────────────────────────────────────
  if (resource === 'drafts') {
    const draftId = requireId(id, 'draft id');

    if (!action) {
      if (method !== 'PATCH' && method !== 'PUT') {
        throw new HttpError(405, `${method} not allowed on /drafts/:id`);
      }
      const { subject, body: draftBody } = body(req);
      return repo.updateDraft(draftId, { subject, body: draftBody });
    }

    if (method !== 'POST') throw new HttpError(405, `${method} not allowed on /drafts/:id/${action}`);

    if (action === 'approve') {
      const { approved_by } = body(req);
      if (!approved_by) throw new HttpError(400, 'approved_by is required');
      return repo.approveDraft(draftId, String(approved_by));
    }

    if (action === 'reject') {
      const { rejected_by, reason } = body(req);
      if (!rejected_by) throw new HttpError(400, 'rejected_by is required');
      return repo.rejectDraft(draftId, String(rejected_by), reason);
    }

    throw new HttpError(404, `Unknown draft action "${action}"`);
  }

  throw new HttpError(404, `Unknown resource "${resource}"`);
}

export default async function handler(req: VercelRequest, res: VercelResponse) {
  try {
    // Which resource is being asked for, before any auth decision. Derived the
    // same way the router derives it, so the session carve-out cannot drift
    // from the route it is meant to exempt.
    const isSessionRoute = pathSegments(req)[0] === 'session';

    // Everything but the session route needs a valid session. Fail closed when
    // APP_PASSWORD is unset: serving candidate data to anonymous callers is a
    // worse outcome than the admin UI being unavailable.
    if (!isSessionRoute) {
      if (!process.env.APP_PASSWORD) {
        return res.status(503).json({
          error:
            'Missing APP_PASSWORD. The admin API is disabled until it is set, because without it this ' +
            'deployment would serve candidate data to anyone with the URL. Set it in the Vercel project ' +
            'settings and redeploy. See SETUP.md.',
        });
      }
      if (!isAuthenticated(req)) {
        return res.status(401).json({ error: 'Authentication required' });
      }
    }

    const result: any = await route(req);

    // Hand back the session cookie on a successful login, and drop it on logout.
    if (isSessionRoute) {
      if ((req.method || '').toUpperCase() === 'POST' && result?.token) {
        res.setHeader('Set-Cookie', sessionCookie(result.token));
        return res.status(200).json({ ok: true });
      }
      if ((req.method || '').toUpperCase() === 'DELETE') {
        res.setHeader('Set-Cookie', clearCookie());
        return res.status(200).json({ ok: true });
      }
    }

    return res.status(200).json(result);
  } catch (err: any) {
    const status = err?.statusCode || err?.status || 500;

    // Supabase "no rows returned" -> 404 rather than a generic failure.
    if (err?.code === 'PGRST116') {
      return res.status(404).json({ error: 'Not found' });
    }

    // A missing environment variable is the one server-side failure worth
    // naming: the variable names are not secret, and without them a
    // misconfigured deploy is indistinguishable from a broken one.
    if (err?.name === 'ConfigError') {
      console.error('[api/data] configuration error:', err.message);
      return res.status(503).json({ error: err.message });
    }

    if (status >= 500) {
      console.error('[api/data] error:', err);
      // Never leak connection strings or key material to the client.
      return res.status(500).json({ error: 'Internal server error' });
    }

    return res.status(status).json({ error: err?.message || 'Request failed' });
  }
}
