import type { VercelRequest, VercelResponse } from '@vercel/node';
import Anthropic from '@anthropic-ai/sdk';
import { getSupabaseAdmin } from '../_lib/supabase';

export default async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { document_text } = req.body;
  if (!document_text) return res.status(400).json({ error: 'document_text is required' });

  try {
    const anthropic = new Anthropic({ apiKey: process.env.ANTHROPIC_API_KEY });
    const supabase = getSupabaseAdmin();

    // Use Claude to parse the requirements document
    const message = await anthropic.messages.create({
      model: 'claude-sonnet-4-20250514',
      max_tokens: 4096,
      messages: [{
        role: 'user',
        content: `You are an expert network project analyst. Parse this requirements document and extract structured data.

Return a JSON object with exactly these fields:
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
}

Requirements Document:
${document_text}`
      }]
    });

    const responseText = message.content[0].type === 'text' ? message.content[0].text : '';

    // Extract JSON from the response
    const jsonMatch = responseText.match(/\{[\s\S]*\}/);
    if (!jsonMatch) throw new Error('Failed to parse AI response as JSON');

    const parsed = JSON.parse(jsonMatch[0]);

    // Create the project
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

    // Create categories
    if (parsed.categories?.length > 0) {
      const categories = parsed.categories.map((cat: any, i: number) => ({
        project_id: project.id,
        name: cat.name,
        description: cat.description || '',
        search_criteria: cat.search_criteria || {},
        sort_order: i,
      }));

      await supabase.from('project_categories').insert(categories);
    }

    // Create screener questions
    if (parsed.screener_questions?.length > 0) {
      const questions = parsed.screener_questions.map((q: any, i: number) => ({
        project_id: project.id,
        question_text: q.question_text,
        question_type: q.question_type || 'free_text',
        options: q.options || [],
        sort_order: i,
      }));

      await supabase.from('screener_questions').insert(questions);
    }

    return res.status(201).json({
      project_id: project.id,
      project_name: project.name,
      categories_created: parsed.categories?.length || 0,
      screener_questions_created: parsed.screener_questions?.length || 0,
    });

  } catch (error: any) {
    console.error('Error creating project from document:', error);
    return res.status(500).json({ error: error.message || 'Internal server error' });
  }
}
