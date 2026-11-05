import { completeJson } from './llm';

/**
 * Decides whether a screener respondent qualifies for a project.
 *
 * Two passes, deliberately in this order:
 *
 *  1. Declarative rules on the question itself (qualifying_answers /
 *     disqualifying_answers). Deterministic, free, and instant — and for
 *     multiple-choice and yes/no questions, which carry most screening
 *     criteria, they are the whole answer.
 *  2. A model pass, only for free-text answers that still need judgement.
 *
 * Doing it this way means a respondent who fails a hard criterion is rejected
 * without an API call, and the model is never asked to re-litigate a rule that
 * was already decided.
 */

export interface ScreenerQuestion {
  id: string;
  question_text: string;
  question_type: 'multiple_choice' | 'free_text' | 'yes_no' | 'scale';
  options: string[];
  qualifying_answers: string[];
  disqualifying_answers: string[];
  is_required: boolean;
}

export interface QualificationResult {
  qualified: boolean;
  score: number;                 // 0-100
  reasons: { question_id: string; verdict: 'pass' | 'fail' | 'unscored'; detail: string }[];
}

const norm = (v: unknown) => String(v ?? '').trim().toLowerCase();

export async function qualify(
  questions: ScreenerQuestion[],
  answers: Record<string, unknown>,
): Promise<QualificationResult> {
  const reasons: QualificationResult['reasons'] = [];
  let hardFail = false;
  const needsJudgement: ScreenerQuestion[] = [];

  for (const q of questions) {
    const raw = answers[q.id];
    const given = norm(raw);

    if (!given) {
      if (q.is_required) {
        hardFail = true;
        reasons.push({ question_id: q.id, verdict: 'fail', detail: 'Required question not answered' });
      } else {
        reasons.push({ question_id: q.id, verdict: 'unscored', detail: 'Skipped (optional)' });
      }
      continue;
    }

    const disq = (q.disqualifying_answers || []).map(norm);
    const qual = (q.qualifying_answers || []).map(norm);

    if (disq.length && disq.includes(given)) {
      hardFail = true;
      reasons.push({ question_id: q.id, verdict: 'fail', detail: `Disqualifying answer: "${raw}"` });
      continue;
    }

    if (qual.length) {
      if (qual.includes(given)) {
        reasons.push({ question_id: q.id, verdict: 'pass', detail: `Qualifying answer: "${raw}"` });
      } else {
        hardFail = true;
        reasons.push({ question_id: q.id, verdict: 'fail', detail: `Answer not in qualifying set: "${raw}"` });
      }
      continue;
    }

    // No rule on this question. Free text may still carry a criterion worth
    // judging; anything else simply has nothing to check against.
    if (q.question_type === 'free_text') needsJudgement.push(q);
    else reasons.push({ question_id: q.id, verdict: 'unscored', detail: 'No rule defined' });
  }

  // A hard fail is final: do not spend a model call confirming it.
  if (hardFail) {
    for (const q of needsJudgement) {
      reasons.push({ question_id: q.id, verdict: 'unscored', detail: 'Not evaluated (already disqualified)' });
    }
    return { qualified: false, score: 0, reasons };
  }

  if (needsJudgement.length && process.env.OPENAI_API_KEY) {
    try {
      const judged = await judgeFreeText(needsJudgement, answers);
      for (const q of needsJudgement) {
        const v = judged[q.id];
        reasons.push({
          question_id: q.id,
          verdict: v?.pass === false ? 'fail' : v?.pass === true ? 'pass' : 'unscored',
          detail: v?.reason || 'No judgement returned',
        });
      }
    } catch {
      // A model outage must not reject a real respondent. Leave these unscored
      // and let a human look; losing a qualified participant is the costlier error.
      for (const q of needsJudgement) {
        reasons.push({ question_id: q.id, verdict: 'unscored', detail: 'Automatic review unavailable' });
      }
    }
  } else {
    for (const q of needsJudgement) {
      reasons.push({ question_id: q.id, verdict: 'unscored', detail: 'Free text, needs human review' });
    }
  }

  const scored = reasons.filter((r) => r.verdict !== 'unscored');
  const passed = scored.filter((r) => r.verdict === 'pass').length;
  const score = scored.length ? Math.round((passed / scored.length) * 100) : 50;

  return { qualified: !reasons.some((r) => r.verdict === 'fail'), score, reasons };
}

async function judgeFreeText(
  questions: ScreenerQuestion[],
  answers: Record<string, unknown>,
): Promise<Record<string, { pass: boolean; reason: string }>> {
  const block = questions
    .map((q) => `id: ${q.id}\nquestion: ${q.question_text}\nanswer: ${String(answers[q.id] ?? '')}`)
    .join('\n\n');

  const parsed = await completeJson({
    maxOutputTokens: 1024,
    prompt: `You are screening respondents for a paid research interview. For each answer below, decide whether it is a genuine, on-topic, substantive response from someone who plausibly belongs in the study.

Fail an answer only if it is empty, nonsense, obviously automated, contradicts the question, or shows the person does not match what the question is screening for. Do not fail an answer for being brief.

${block}

Return ONLY a JSON object keyed by the exact id strings above:
{"<id>": {"pass": true, "reason": "short reason"}}`,
  });

  return parsed || {};
}
