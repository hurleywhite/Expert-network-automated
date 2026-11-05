import type { VercelRequest, VercelResponse } from '@vercel/node';
import { getSupabaseAdmin, ConfigError } from '../_lib/supabase';
import { withAdmin } from '../_lib/auth';
import { sourceCategory } from '../_lib/sourcing';

async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : req.body || {};
  const { project_id, category_id, max_results = 25 } = body;
  if (!project_id || !category_id) {
    return res.status(400).json({ error: 'project_id and category_id are required' });
  }

  if (!process.env.APOLLO_API_KEY) {
    return res.status(503).json({
      error: 'Missing APOLLO_API_KEY. Set it in the Vercel project settings, then redeploy. See SETUP.md.',
    });
  }

  try {
    const supabase = getSupabaseAdmin();

    const { data: category, error } = await supabase
      .from('project_categories')
      .select('*')
      .eq('id', category_id)
      .single();
    if (error) throw error;

    const wanted = Math.min(Math.max(Number(max_results) || 25, 1), 100);
    const outcome = await sourceCategory(category, project_id, wanted);

    return res.status(200).json({
      project_id,
      ...outcome,
      message: outcome.error
        ? `Apollo could not be reached: ${outcome.error}`
        : outcome.sourced > 0
        ? `Added ${outcome.sourced} new expert${outcome.sourced === 1 ? '' : 's'} to ${outcome.category_name}.`
        : outcome.exhausted
        ? `Apollo has no more matches for ${outcome.category_name}. Broaden its titles or keywords.`
        : `No new experts — everyone Apollo returned for ${outcome.category_name} is already in this project.`,
    });
  } catch (error: any) {
    if (error instanceof ConfigError || error?.name === 'ConfigError') {
      return res.status(503).json({ error: error.message });
    }
    console.error('Error sourcing by category:', error);
    return res.status(500).json({ error: 'Internal server error' });
  }
}

export default withAdmin(handler);
