import type { VercelRequest, VercelResponse } from '@vercel/node';
import Anthropic from '@anthropic-ai/sdk';
import { getSupabaseAdmin, ConfigError } from '../_lib/supabase';
import { extractDocument, DocumentError, type UploadedFile } from '../_lib/documents';

/**
 * Creates a project from a requirements document.
 *
 * Accepts either pasted text or an uploaded file:
 *   { document_text: "..." }
 *   { file: { name, data /* base64 *\/, type } }
 *
 * PDFs are passed to Claude as a native document block rather than being
 * text-extracted first, so it reads the real layout. Everything else arrives
 * as text.
 */

const EXTRACTION_PROMPT = `You are an expert network project analyst. Parse this requirements document and extract structured data.

Return ONLY a JSON object with exactly these fields, and no prose around it:
{
  "title": "Project title",
  "industry": "Primary industry",
  "subvertical": "Subvertical if applicable",
  "keywords": ["keyword1", "keyword2"],
  "categories": [
    {
      "name": "Category Name",
      "description": "What type of expert fits here",
      "search_criteria": {
        "titles": ["VP of Sales", "Director of Marketing"],
        "industries": ["SaaS", "Technology"],
        "keywords": ["specific", "search", "terms"]
      }
    }
  ],
  "screener_questions": [
    {
      "question_text": "The question to ask",
      "question_type": "multiple_choice|free_text|yes_no|scale",
      "options": ["Option A", "Option B"]
    }
  ]
}`;

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const body = typeof req.body === 'string' ? safeParse(req.body) : req.body || {};
  const documentText: string | undefined = body.document_text;
  const file: UploadedFile | undefined = body.file;

  if (!documentText?.trim() && !file) {
    return res.status(400).json({ error: 'Provide either document_text or a file.' });
  }

  try {
    // ── Build the message content ────────────────────────────────────────────
    const content: Anthropic.MessageParam['content'] = [];
    let sourceLabel = 'pasted text';

    if (file) {
      const extracted = await extractDocument(file);
      sourceLabel = extracted.source;

      if (extracted.kind === 'pdf') {
        content.push({
          type: 'document',
          source: { type: 'base64', media_type: 'application/pdf', data: extracted.base64 },
        });
        content.push({ type: 'text', text: EXTRACTION_PROMPT });
      } else {
        content.push({
          type: 'text',
          text: `${EXTRACTION_PROMPT}\n\nRequirements Document (${extracted.source}):\n${extracted.text}`,
        });
      }
    } else {
      content.push({
        type: 'text',
        text: `${EXTRACTION_PROMPT}\n\nRequirements Document:\n${documentText}`,
      });
    }

    if (!process.env.ANTHROPIC_API_KEY) {
      throw new ConfigError(
        'Missing ANTHROPIC_API_KEY. Set it in the Vercel project settings, then redeploy. See SETUP.md.',
      );
    }

    const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
    const supabase = getSupabaseAdmin();

    const message = await anthropic.messages.create({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 4096,
      messages: [{ role: 'user', content }],
    });

    const responseText = message.content[0]?.type === 'text' ? message.content[0].text : '';
    const jsonMatch = responseText.match(/\{[\s\S]*\}/);
    if (!jsonMatch) {
      return res.status(422).json({
        error: `Could not extract project details from ${sourceLabel}. ` +
          'If it is a scanned document, the text may not be readable.',
      });
    }

    let parsed: any;
    try {
      parsed = JSON.parse(jsonMatch[0]);
    } catch {
      return res.status(422).json({ error: `Could not parse the project details from ${sourceLabel}.` });
    }

    // ── Persist ──────────────────────────────────────────────────────────────
    const { data: project, error: projectError } = await supabase
      .from('project_briefs')
      .insert({
        name: parsed.title || 'Untitled Project',
        industry: parsed.industry || null,
        subvertical: parsed.subvertical || null,
        keywords: parsed.keywords || [],
      })
      .select()
      .single();

    if (projectError) throw projectError;

    if (parsed.categories?.length > 0) {
      const categories = parsed.categories.map((cat: any, i: number) => ({
        project_id: project.id,
        name: cat.name,
        description: cat.description || '',
        search_criteria: cat.search_criteria || {},
        sort_order: i,
      }));
      const { error } = await supabase.from('project_categories').insert(categories);
      if (error) throw error;
    }

    if (parsed.screener_questions?.length > 0) {
      const questions = parsed.screener_questions.map((q: any, i: number) => ({
        project_id: project.id,
        question_text: q.question_text,
        question_type: q.question_type || 'free_text',
        options: q.options || [],
        sort_order: i,
      }));
      const { error } = await supabase.from('screener_questions').insert(questions);
      if (error) throw error;
    }

    return res.status(201).json({
      project_id: project.id,
      project_name: project.name,
      source: sourceLabel,
      categories_created: parsed.categories?.length || 0,
      screener_questions_created: parsed.screener_questions?.length || 0,
    });
  } catch (error: any) {
    // A bad upload is the user's to fix, so say exactly what is wrong with it.
    if (error instanceof DocumentError || error?.name === 'DocumentError') {
      return res.status(400).json({ error: error.message });
    }
    if (error instanceof ConfigError || error?.name === 'ConfigError') {
      return res.status(503).json({ error: error.message });
    }
    if (error?.status === 401 || error?.status === 403) {
      return res.status(503).json({ error: 'The Anthropic API rejected the request. Check ANTHROPIC_API_KEY.' });
    }
    if (error?.status === 429) {
      return res.status(429).json({ error: 'Rate limited by the Anthropic API. Try again shortly.' });
    }

    console.error('Error creating project from document:', error);
    return res.status(500).json({ error: 'Internal server error' });
  }
}

function safeParse(s: string): any {
  try {
    return JSON.parse(s);
  } catch {
    return {};
  }
}
