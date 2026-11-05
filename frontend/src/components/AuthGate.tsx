import { useState, useEffect, type ReactNode } from 'react';
import { sessionApi } from '../api/client';

/**
 * Password gate for the admin UI.
 *
 * The deployment is reachable without credentials, so the API now requires a
 * session for anything that touches candidate data. This is the matching
 * front door. The password is posted once and exchanged for an HttpOnly
 * cookie — it is never stored in the bundle or in local storage.
 */
export default function AuthGate({ children }: { children: ReactNode }) {
  const [state, setState] = useState<'checking' | 'in' | 'out'>('checking');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    sessionApi
      .check()
      .then((r) => setState(r.authenticated ? 'in' : 'out'))
      .catch(() => setState('out'));
  }, []);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await sessionApi.login(password);
      setPassword('');
      setState('in');
    } catch (err: any) {
      setError(String(err?.message || err).replace(/^API error \d+:\s*/, ''));
    }
    setBusy(false);
  };

  if (state === 'checking') {
    return <div className="min-h-screen bg-gray-50 flex items-center justify-center text-gray-400">Loading…</div>;
  }

  if (state === 'in') return <>{children}</>;

  return (
    <div className="min-h-screen bg-gray-50 flex items-center justify-center px-4">
      <form onSubmit={submit} className="bg-white border rounded-lg p-8 w-full max-w-sm shadow-sm">
        <div className="flex items-center gap-2 mb-6">
          <img src="/arcticblue-logo.png" alt="" className="h-8 w-auto" />
          <span className="text-lg font-bold text-gray-900">ExpertNetwork Outreach</span>
        </div>

        <label htmlFor="pw" className="block text-sm font-medium text-gray-700 mb-2">
          Password
        </label>
        <input
          id="pw"
          type="password"
          autoFocus
          autoComplete="current-password"
          value={password}
          onChange={(e) => { setPassword(e.target.value); setError(null); }}
          className="w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500"
        />

        {error && <p className="mt-3 text-sm text-red-600">{error}</p>}

        <button
          type="submit"
          disabled={busy || !password}
          className="mt-5 w-full px-4 py-2 bg-blue-600 text-white rounded-lg text-sm font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {busy ? 'Signing in…' : 'Sign in'}
        </button>

        <p className="mt-5 text-xs text-gray-400 leading-relaxed">
          This protects candidate names, emails and LinkedIn URLs. The screener
          link you share publicly does not sit behind this.
        </p>
      </form>
    </div>
  );
}
