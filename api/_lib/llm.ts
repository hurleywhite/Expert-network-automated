import OpenAI from 'openai';
import { ConfigError } from './supabase';

/**
 * The single place this app talks to a model.
 *
 * Every endpoint here asks the model for one JSON object and then acts on it,
 * so the shared concerns — picking the model, attaching a PDF, pulling the
 * text back out, and parsing JSON out of a reply that may be wrapped in prose
 * or a code fence — live here rather than being repeated four times.
 */

/**
 * Default model. Overridable with OPENAI_MODEL so the id can be changed
 * without a redeploy when a newer GPT-6 variant is preferred
 * (gpt-6-sol, gpt-6-luna, gpt-6.1-sol, gpt-6.1-terra).
 */
const DEFAULT_MODEL = 'gpt-6-astra';

export function modelName(): string {
  return process.env.OPENAI_MODEL || DEFAULT_MODEL;
}

let cached: OpenAI | null = null;

function client(): OpenAI {
  if (cached) return cached;
  const apiKey = process.env.OPENAI_API_KEY;
  if (!apiKey) {
    throw new ConfigError(
      'Missing OPENAI_API_KEY. Set it in the Vercel project settings, then redeploy. See SETUP.md.',
    );
  }
  cached = new OpenAI({ apiKey });
  return cached;
}

export interface PdfAttachment {
  filename: string;
  /** Raw base64, without a data: prefix. */
  base64: string;
}

/**
 * Pulls a JSON object out of a model reply.
 *
 * Models wrap JSON in prose or a ```json fence often enough that requiring a
 * bare object would make this brittle. The fence is stripped first, then the
 * outermost braces are taken.
 */
export function extractJson(text: string): any {
  if (!text?.trim()) throw new Error('The model returned an empty response.');

  const fenced = text.match(/```(?:json)?\s*([\s\S]*?)```/i);
  const candidate = fenced ? fenced[1] : text;

  const start = candidate.indexOf('{');
  const end = candidate.lastIndexOf('}');
  if (start === -1 || end === -1 || end < start) {
    throw new Error('The model response contained no JSON object.');
  }

  return JSON.parse(candidate.slice(start, end + 1));
}

/**
 * Sends one prompt (optionally with a PDF) and returns the parsed JSON object.
 *
 * PDFs are passed to the model as a file rather than being text-extracted
 * first, so it reads the real layout and tables and headings survive.
 */
export async function completeJson(opts: {
  prompt: string;
  pdf?: PdfAttachment;
  maxOutputTokens?: number;
}): Promise<any> {
  const text = await completeText(opts);
  return extractJson(text);
}

/** As completeJson, but returns the raw text. */
export async function completeText(opts: {
  prompt: string;
  pdf?: PdfAttachment;
  maxOutputTokens?: number;
}): Promise<string> {
  const content: any[] = [];

  if (opts.pdf) {
    content.push({
      type: 'input_file',
      filename: opts.pdf.filename,
      file_data: `data:application/pdf;base64,${opts.pdf.base64}`,
    });
  }
  content.push({ type: 'input_text', text: opts.prompt });

  const response = await client().responses.create({
    model: modelName(),
    input: [{ role: 'user', content }],
    ...(opts.maxOutputTokens ? { max_output_tokens: opts.maxOutputTokens } : {}),
  });

  return response.output_text || '';
}

/**
 * Maps an OpenAI failure onto an HTTP status and a message safe to show.
 * Returns null for anything that is not recognisably an API error, so the
 * caller falls back to a generic 500 rather than echoing internals.
 */
export function describeOpenAiError(err: any): { status: number; error: string } | null {
  const status = err?.status;

  if (status === 401 || status === 403) {
    return { status: 503, error: 'OpenAI rejected the request. Check OPENAI_API_KEY in the Vercel project settings.' };
  }
  if (status === 429) {
    return { status: 429, error: 'Rate limited by OpenAI, or the account is out of quota. Try again shortly.' };
  }
  if (status === 404 && /model/i.test(err?.message || '')) {
    return {
      status: 503,
      error:
        `The model "${modelName()}" is not available to this account. ` +
        'Set OPENAI_MODEL in the Vercel project settings to one your account can use.',
    };
  }
  if (status === 400 && /model/i.test(err?.message || '')) {
    return { status: 400, error: `OpenAI rejected the request for model "${modelName()}": ${err?.message}` };
  }
  return null;
}
