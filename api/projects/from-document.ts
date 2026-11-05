import type { VercelRequest, VercelResponse } from '@vercel/node';
import { getSupabaseAdmin, ConfigError } from '../_lib/supabase';
import { completeText, extractJson, describeOpenAiError } from '../_lib/llm';
import { extractDocument, DocumentError, type UploadedFile } from '../_lib/documents';
import { withAdmin } from '../_lib/auth';

/**
 * Creates a project from a requirements document.
 *
 * Accepts either pasted text or an uploaded file:
 *   { document_text: "..." }
 *   { file: { name, data /* base64 *\/, type } }
 *
 * PDFs are passed to GPT-6 as a native file input rather than being
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

async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const body = typeof req.body === 'string' ? safeParse(req.body) : req.body || {};
  const documentText: string | undefined = body.document_text;
  const file: UploadedFile | undefined = body.file;
  // Set when the browser extracted the text itself from a file too large to upload.
  const sourceName: string | undefined = body.source_name;

  if (!documentText?.trim() && !file) {
    return res.status(400).json({ error: 'Provide either document_text or a file.' });
  }

  try {
    // ── Build the prompt, attaching the PDF itself when there is one ────────
    let sourceLabel = 'pasted text';
    let pdf: { filename: string; base64: string } | undefined;
    let prompt = EXTRACTION_PROMPT;

    if (file) {
      const extracted = await extractDocument(file);
      sourceLabel = extracted.source;

      if (extracted.kind === 'pdf') {
        pdf = { filename: extracted.source, base64: extracted.base64 };
      } else {
        prompt = `${EXTRACTION_PROMPT}\n\nRequirements Document (${extracted.source}):\n${extracted.text}`;
      }
    } else {
      if (sourceName) sourceLabel = sourceName;
      const heading = sourceName ? `Requirements Document (${sourceName})` : 'Requirements Document';
      prompt = `${EXTRACTION_PROMPT}\n\n${heading}:\n${documentText}`;
    }

    const supabase = getSupabaseAdmin();
    const responseText = await completeText({ prompt, pdf, maxOutputTokens: 4096 });

    let parsed: any;
    try {
      parsed = extractJson(responseText);
    } catch {
      return res.status(422).json({
        error: `Could not extract project details from ${sourceLabel}. ` +
          'If it is a scanned document, the text may not be readable.',
      });
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
    const openAiError = describeOpenAiError(error);
    if (openAiError) return res.status(openAiError.status).json({ error: openAiError.error });

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

export default withAdmin(handler);
