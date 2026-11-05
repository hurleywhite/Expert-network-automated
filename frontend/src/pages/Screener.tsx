import { useState, useEffect } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';

/**
 * The public screener, opened by strangers from a Reddit post or an email.
 *
 * It sits outside AuthGate on purpose: it is the one page that must work with
 * no session. It talks only to /api/screener, which returns nothing but the
 * questions, so no candidate data is reachable from here.
 */

interface Question {
  id: string;
  question_text: string;
  question_type: 'multiple_choice' | 'free_text' | 'yes_no' | 'scale';
  options: string[];
  is_required: boolean;
  help_text: string | null;
}

export default function Screener() {
  const { projectId } = useParams<{ projectId: string }>();
  const [params] = useSearchParams();

  const [project, setProject] = useState<any>(null);
  const [questions, setQuestions] = useState<Question[]>([]);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [contact, setContact] = useState({ full_name: '', email: '', phone: '' });
  const [consent, setConsent] = useState(false);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<{ qualified: boolean; scheduling_url: string | null; message: string } | null>(null);

  useEffect(() => {
    fetch(`/api/screener?project_id=${encodeURIComponent(projectId || '')}`)
      .then(async (r) => {
        const d = await r.json();
        if (!r.ok) throw new Error(d.error || 'This screener is unavailable.');
        setProject(d.project);
        setQuestions(d.questions);
      })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  }, [projectId]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    try {
      const res = await fetch('/api/screener', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          project_id: projectId,
          answers,
          ...contact,
          consent,
          // Set by the link in each post, so we can tell which community worked.
          source_channel: params.get('src') || 'direct',
          source_detail: params.get('from') || null,
        }),
      });
      const d = await res.json();
      if (!res.ok) throw new Error(d.error || 'Something went wrong.');
      setResult(d);
      window.scrollTo({ top: 0, behavior: 'smooth' });
    } catch (e: any) {
      setError(e.message);
    }
    setSubmitting(false);
  };

  if (loading) return <Shell><p className="text-gray-400">Loading…</p></Shell>;

  if (error && !project) return <Shell><p className="text-red-600">{error}</p></Shell>;

  // ── Outcome ───────────────────────────────────────────────────────────────
  if (result) {
    return (
      <Shell>
        {result.qualified ? (
          <div>
            <div className="inline-flex items-center gap-2 bg-green-100 text-green-800 text-sm font-medium px-3 py-1 rounded-full mb-4">
              You qualify
            </div>
            <h1 className="text-2xl font-bold text-gray-900 mb-3">Thanks — you're a fit for this study.</h1>
            {result.scheduling_url ? (
              <>
                <p className="text-gray-600 mb-6">
                  The last step is picking a time that works for you. Your slot isn't reserved
                  until you book.
                </p>
                <a
                  href={result.scheduling_url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="inline-block px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700"
                >
                  Book your interview →
                </a>
              </>
            ) : (
              <p className="text-gray-600">
                We'll email you shortly at <strong>{contact.email}</strong> to arrange a time.
              </p>
            )}
          </div>
        ) : (
          <div>
            <h1 className="text-2xl font-bold text-gray-900 mb-3">Thank you for your time.</h1>
            <p className="text-gray-600">{result.message}</p>
            <p className="text-gray-500 text-sm mt-4">
              We appreciate you answering — we run studies regularly and may be in touch about a
              future one that fits better.
            </p>
          </div>
        )}
      </Shell>
    );
  }

  // ── Form ──────────────────────────────────────────────────────────────────
  return (
    <Shell>
      <h1 className="text-2xl font-bold text-gray-900 mb-2">{project.name}</h1>
      {project.intro && <p className="text-gray-600 mb-4 whitespace-pre-line">{project.intro}</p>}
      {project.incentive && (
        <p className="inline-block bg-blue-50 text-blue-900 text-sm font-medium px-3 py-1.5 rounded-lg mb-6">
          {project.incentive}
        </p>
      )}

      <form onSubmit={submit} className="space-y-6">
        {questions.map((q, i) => (
          <div key={q.id}>
            <label className="block text-sm font-medium text-gray-900 mb-1">
              {i + 1}. {q.question_text}
              {q.is_required && <span className="text-red-500 ml-1">*</span>}
            </label>
            {q.help_text && <p className="text-xs text-gray-500 mb-2">{q.help_text}</p>}
            <QuestionInput
              q={q}
              value={answers[q.id] || ''}
              onChange={(v) => setAnswers((a) => ({ ...a, [q.id]: v }))}
            />
          </div>
        ))}

        <div className="border-t pt-6 space-y-4">
          <p className="text-sm font-medium text-gray-900">How can we reach you?</p>
          <input
            type="text" placeholder="Your name"
            value={contact.full_name}
            onChange={(e) => setContact({ ...contact, full_name: e.target.value })}
            className="w-full border rounded-lg px-3 py-2 text-sm"
          />
          <input
            type="email" required placeholder="Email address *"
            value={contact.email}
            onChange={(e) => setContact({ ...contact, email: e.target.value })}
            className="w-full border rounded-lg px-3 py-2 text-sm"
          />
          <input
            type="tel" placeholder="Phone (optional)"
            value={contact.phone}
            onChange={(e) => setContact({ ...contact, phone: e.target.value })}
            className="w-full border rounded-lg px-3 py-2 text-sm"
          />

          <label className="flex items-start gap-3 text-sm text-gray-600">
            <input
              type="checkbox" checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
              className="mt-0.5"
            />
            <span>
              I consent to being contacted about this study, and understand my answers will be
              used to decide whether I'm eligible. I can withdraw at any time.
            </span>
          </label>
        </div>

        {error && (
          <p className="text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</p>
        )}

        <button
          type="submit"
          disabled={submitting || !consent || !contact.email}
          className="w-full px-6 py-3 bg-blue-600 text-white rounded-lg font-medium hover:bg-blue-700 disabled:opacity-50"
        >
          {submitting ? 'Submitting…' : 'Submit'}
        </button>
      </form>
    </Shell>
  );
}

function QuestionInput({ q, value, onChange }: { q: Question; value: string; onChange: (v: string) => void }) {
  const base = 'w-full border rounded-lg px-3 py-2 text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500';

  if (q.question_type === 'yes_no') {
    return (
      <div className="flex gap-3">
        {['Yes', 'No'].map((o) => (
          <button
            key={o} type="button" onClick={() => onChange(o)}
            className={`px-5 py-2 rounded-lg text-sm border ${
              value === o ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700 hover:border-gray-400'
            }`}
          >
            {o}
          </button>
        ))}
      </div>
    );
  }

  if (q.question_type === 'multiple_choice' && q.options?.length) {
    return (
      <div className="space-y-2">
        {q.options.map((o) => (
          <label key={o} className="flex items-center gap-2 text-sm text-gray-700">
            <input type="radio" name={q.id} checked={value === o} onChange={() => onChange(o)} />
            {o}
          </label>
        ))}
      </div>
    );
  }

  if (q.question_type === 'scale') {
    return (
      <div className="flex gap-2">
        {[1, 2, 3, 4, 5].map((n) => (
          <button
            key={n} type="button" onClick={() => onChange(String(n))}
            className={`w-10 h-10 rounded-lg text-sm border ${
              value === String(n) ? 'bg-blue-600 text-white border-blue-600' : 'bg-white text-gray-700 hover:border-gray-400'
            }`}
          >
            {n}
          </button>
        ))}
      </div>
    );
  }

  return <textarea value={value} onChange={(e) => onChange(e.target.value)} rows={3} className={base} />;
}

function Shell({ children }: { children: React.ReactNode }) {
  return (
    <div className="min-h-screen bg-gray-50">
      <nav className="bg-[#1fa0dc] text-white">
        <div className="max-w-2xl mx-auto px-6 py-3 flex items-center gap-2">
          <img src="/arcticblue-logo.png" alt="" className="h-7 w-auto" />
          <span className="font-bold">Research Screener</span>
        </div>
      </nav>
      <div className="max-w-2xl mx-auto px-6 py-10">
        <div className="bg-white border rounded-lg p-8">{children}</div>
        <p className="text-xs text-gray-400 mt-6 text-center">
          Your answers are used only to assess eligibility for this study.
        </p>
      </div>
    </div>
  );
}
