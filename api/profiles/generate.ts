import type { VercelRequest, VercelResponse } from '@vercel/node';
import { getSupabaseAdmin } from '../_lib/supabase';
import { completeText, extractJson, describeOpenAiError } from '../_lib/llm';
import { withAdmin } from '../_lib/auth';

async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { project_id, limit = 10 } = req.body;
  if (!project_id) return res.status(400).json({ error: 'project_id is required' });

  try {
    const supabase = getSupabaseAdmin();

    // Get project info
    const { data: project } = await supabase
      .from('project_briefs')
      .select('*')
      .eq('id', project_id)
      .single();

    if (!project) return res.status(404).json({ error: 'Project not found' });

    // Get screener questions
    const { data: questions } = await supabase
      .from('screener_questions')
      .select('*')
      .eq('project_id', project_id)
      .order('sort_order');

    // Get expert profiles that need profiling (no ai_overview yet)
    const { data: profiles } = await supabase
      .from('expert_profiles')
      .select(`
        id,
        candidate_id,
        category_id,
        candidates!inner (
          full_name,
          title,
          company,
          headline,
          linkedin_url,
          region
        ),
        project_categories (
          name,
          description
        )
      `)
      .eq('project_id', project_id)
      .is('ai_overview', null)
      .limit(limit);

    if (!profiles?.length) {
      return res.status(200).json({ project_id, profiled: 0, message: 'No profiles need generation' });
    }

    let profiled = 0;
    const exaKey = process.env.EXA_API_KEY;

    for (const profile of profiles) {
      const candidate = (profile as any).candidates;
      const category = (profile as any).project_categories;

      // Optional: Exa AI web research
      let exaResearch: any = {};
      if (exaKey && candidate.full_name) {
        try {
          const searchQuery = `${candidate.full_name} ${candidate.company || ''} ${candidate.title || ''}`;
          const exaRes = await fetch('https://api.exa.ai/search', {
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'x-api-key': exaKey,
            },
            body: JSON.stringify({
              query: searchQuery,
              num_results: 5,
              use_autoprompt: true,
              type: 'neural',
            }),
          });

          if (exaRes.ok) {
            const exaData = await exaRes.json();
            exaResearch = {
              results: (exaData.results || []).map((r: any) => ({
                title: r.title,
                url: r.url,
                snippet: r.text?.substring(0, 300),
              })),
              searched_at: new Date().toISOString(),
            };
          }
        } catch (exaErr) {
          console.error('Exa research error:', exaErr);
        }
      }

      // Build the prompt for expert profiling
      const screenerQuestionsText = (questions || [])
        .map((q: any, i: number) => `${i + 1}. ${q.question_text} (${q.question_type})${q.options?.length ? ` Options: ${q.options.join(', ')}` : ''}`)
        .join('\n');

      const researchContext = exaResearch.results?.length
        ? `\n\nWeb Research Results:\n${exaResearch.results.map((r: any) => `- ${r.title}: ${r.snippet}`).join('\n')}`
        : '';

      const message = await completeText({ prompt: `You are generating an expert network profile. Create a comprehensive profile for this expert based on available data.

Expert:
- Name: ${candidate.full_name}
- Title: ${candidate.title || 'Unknown'}
- Company: ${candidate.company || 'Unknown'}
- Headline: ${candidate.headline || 'N/A'}
- Region: ${candidate.region || 'N/A'}
- Category: ${category?.name || 'General'}
- Category Focus: ${category?.description || 'N/A'}

Project: ${project.name}
Industry: ${project.industry || 'N/A'}
Keywords: ${(project.keywords || []).join(', ')}
${researchContext}

Return a JSON object with exactly these fields:
{
  "ai_overview": "A 2-3 paragraph expert overview highlighting why this person is relevant to the project. Write in third person professional tone.",
  "project_expertise": ["Bullet point 1 about specific relevant expertise", "Bullet point 2", "Bullet point 3", "Bullet point 4"],
  "relevance_score": 75,
  "rate_per_hour": 250,
  "work_experience": [
    {"date_range": "2020–Present", "title": "Current Title", "company": "Current Company", "is_current": true},
    {"date_range": "2017–2020", "title": "Previous Title", "company": "Previous Company"}
  ],
  "screener_responses": {
    ${(questions || []).map((q: any) => `"${q.id}": {"answer": "Best estimate answer", "confidence": "medium", "reasoning": "Why this answer"}`).join(',\n    ')}
  }
}

Screener Questions:
${screenerQuestionsText || 'None defined'}

Important:
- relevance_score should be 0-100 based on how well the expert matches the project needs
- rate_per_hour should be a realistic USD hourly rate for this expert's seniority/domain
- For screener_responses, make your best estimate based on the expert's profile; mark confidence accordingly`, maxOutputTokens: 2048 });

      const responseText = message;
      const jsonMatch = responseText.match(/\{[\s\S]*\}/);

      if (jsonMatch) {
        try {
          const parsed = JSON.parse(jsonMatch[0]);

          await supabase
            .from('expert_profiles')
            .update({
              ai_overview: parsed.ai_overview || '',
              project_expertise: parsed.project_expertise || [],
              relevance_score: parsed.relevance_score || null,
              rate_per_hour: parsed.rate_per_hour || null,
              work_experience: parsed.work_experience || [],
              screener_responses: parsed.screener_responses || {},
              exa_research: exaResearch,
              status: 'screened',
              updated_at: new Date().toISOString(),
            })
            .eq('id', profile.id);

          profiled++;
        } catch (parseErr) {
          console.error(`Failed to parse profile for ${candidate.full_name}:`, parseErr);
        }
      }
    }

    return res.status(200).json({
      project_id,
      profiled,
      remaining: (profiles?.length || 0) - profiled,
    });

  } catch (error: any) {
    if (error?.name === 'ConfigError') return res.status(503).json({ error: error.message });
    const openAiError = describeOpenAiError(error);
    if (openAiError) return res.status(openAiError.status).json({ error: openAiError.error });

    console.error('Error generating profiles:', error);
    return res.status(500).json({ error: error.message || 'Internal server error' });
  }
}

export default withAdmin(handler);
