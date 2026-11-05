import { createHmac, timingSafeEqual, randomBytes } from 'crypto';
import type { VercelRequest, VercelResponse } from '@vercel/node';
import { ConfigError } from './supabase';

/**
 * Admin authentication for everything except the public screener.
 *
 * The deployment is reachable without credentials — Vercel's SSO protection is
 * set to "all except custom domains", and the production alias counts as a
 * custom domain — so /api/data was serving candidate names, emails and
 * LinkedIn URLs to anyone with the URL. That is not acceptable on its own, and
 * is untenable once a screener link is posted publicly, which hands out the
 * host.
 *
 * A password is checked server-side against APP_PASSWORD and exchanged for an
 * HMAC-signed, HttpOnly cookie. No secret reaches the browser: only the
 * password the operator types, and then an opaque signed token.
 */

const COOKIE = 'enw_session';
const TTL_MS = 30 * 24 * 60 * 60 * 1000; // 30 days

export class AuthError extends Error {
  statusCode = 401;
  constructor(message = 'Authentication required') {
    super(message);
    this.name = 'AuthError';
  }
}

function secret(): string {
  const s = process.env.APP_PASSWORD;
  if (!s) {
    throw new ConfigError(
      'Missing APP_PASSWORD. Set it in the Vercel project settings to protect the admin API, then redeploy. See SETUP.md.',
    );
  }
  return s;
}

function sign(payload: string): string {
  return createHmac('sha256', secret()).update(payload).digest('hex');
}

/** Constant-time compare that never throws on length mismatch. */
function safeEqual(a: string, b: string): boolean {
  const ab = Buffer.from(a);
  const bb = Buffer.from(b);
  if (ab.length !== bb.length) return false;
  return timingSafeEqual(ab, bb);
}

export function issueToken(): string {
  const expires = Date.now() + TTL_MS;
  const nonce = randomBytes(8).toString('hex');
  const payload = `${expires}.${nonce}`;
  return `${payload}.${sign(payload)}`;
}

export function verifyToken(token: string | undefined): boolean {
  if (!token) return false;
  const parts = token.split('.');
  if (parts.length !== 3) return false;

  const [expires, nonce, mac] = parts;
  if (!safeEqual(mac, sign(`${expires}.${nonce}`))) return false;

  const expiresAt = Number(expires);
  return Number.isFinite(expiresAt) && expiresAt > Date.now();
}

export function checkPassword(candidate: unknown): boolean {
  if (typeof candidate !== 'string' || !candidate) return false;
  return safeEqual(candidate, secret());
}

export function sessionCookie(token: string): string {
  const maxAge = Math.floor(TTL_MS / 1000);
  // HttpOnly so script cannot read it; SameSite=Lax so it survives normal
  // navigation but is not sent on cross-site POSTs.
  return `${COOKIE}=${token}; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=${maxAge}`;
}

export function clearCookie(): string {
  return `${COOKIE}=; HttpOnly; Secure; SameSite=Lax; Path=/; Max-Age=0`;
}

function tokenFrom(req: VercelRequest): string | undefined {
  const header = req.headers.cookie || '';
  for (const part of header.split(';')) {
    const [k, ...rest] = part.trim().split('=');
    if (k === COOKIE) return rest.join('=');
  }
  // Also accept a bearer token, so scripts and cron can authenticate without a cookie jar.
  const auth = req.headers.authorization;
  if (auth?.startsWith('Bearer ')) return auth.slice(7);
  return undefined;
}

export function isAuthenticated(req: VercelRequest): boolean {
  try {
    return verifyToken(tokenFrom(req));
  } catch {
    // A missing APP_PASSWORD must read as "not authenticated", never as "allowed".
    return false;
  }
}

/** Throws AuthError unless the request carries a valid session. */
export function requireAdmin(req: VercelRequest): void {
  if (!isAuthenticated(req)) throw new AuthError();
}

/**
 * Wraps a handler so it is reachable only with a valid session.
 * Fails closed: if APP_PASSWORD is unset, nothing is served rather than
 * everything, because the failure mode of the alternative is a data leak.
 */
export function withAdmin(
  handler: (req: VercelRequest, res: VercelResponse) => Promise<unknown>,
) {
  return async (req: VercelRequest, res: VercelResponse) => {
    if (!process.env.APP_PASSWORD) {
      return res.status(503).json({
        error:
          'Missing APP_PASSWORD. The admin API is disabled until it is set, because without it this ' +
          'deployment would serve candidate data to anyone. Set it in the Vercel project settings and redeploy.',
      });
    }
    if (!isAuthenticated(req)) {
      return res.status(401).json({ error: 'Authentication required' });
    }
    return handler(req, res);
  };
}
