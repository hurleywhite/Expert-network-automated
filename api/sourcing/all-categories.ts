import type { VercelRequest, VercelResponse } from '@vercel/node';
import { getSupabaseAdmin, ConfigError } from '../_lib/supabase';
import { withAdmin } from '../_lib/auth';
import { sourceCategory, type SourceOutcome } from '../_lib/sourcing';

async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const body = typeof req.body === 'string' ? JSON.parse(req.body || '{}') : req.body || {};
  const { project_id, max_per_category = 25 } = body;
  if (!project_id) return res.status(400).json({ error: 'project_id is required' });

  if (!process.env.APOLLO_API_KEY) {
    return res.status(503).json({
      error: 'Missing APOLLO_API_KEY. Set it in the Vercel project settings, then redeploy. See SETUP.md.',
    });
  }

  try {
    const supabase = getSupabaseAdmin();

    const { data: categories, error } = await supabase
      .from('project_categories')
      .select('*')
      .eq('project_id', project_id)
      .order('sort_order');

    if (error) throw error;
    if (!categories?.length) {
      return res.status(400).json({
        error: 'This project has no categories, so there is nothing to search Apollo for.',
      });
    }

    const wanted = Math.min(Math.max(Number(max_per_category) || 25, 1), 100);
    const results: SourceOutcome[] = [];

    for (const category of categories) {
      try {
        results.push(await sourceCategory(category, project_id, wanted));
      } catch (err: any) {
        results.push({
          category_id: category.id,
          category_name: category.name,
          sourced: 0,
          already_present: 0,
          enriched: 0,
          pages_read: 0,
          next_page: (category.last_sourced_page || 0) + 1,
          exhausted: false,
          error: err?.message || 'Unknown error',
        });
      }
    }

    const sourced = results.reduce((n, r) => n + r.sourced, 0);
    const alreadyPresent = results.reduce((n, r) => n + r.already_present, 0);
    const enriched = results.reduce((n, r) => n + r.enriched, 0);
    const exhausted = results.every((r) => r.exhausted);

    return res.status(200).json({
      project_id,
      total_sourced: sourced,
      already_present: alreadyPresent,
      categories_searched: categories.length,
      all_exhausted: exhausted,
      // Enrichment is the credit-consuming step, so report it rather than
      // letting Apollo credits drain invisibly.
      enriched,
      // So the UI can say what happened rather than silently doing nothing.
      message: buildMessage(sourced, alreadyPresent, exhausted, results, enriched),
      results,
    });
  } catch (error: any) {
    if (error instanceof ConfigError || error?.name === 'ConfigError') {
      return res.status(503).json({ error: error.message });
    }
    console.error('Error sourcing candidates:', error);
    return res.status(500).json({ error: 'Internal server error' });
  }
}

function buildMessage(
  sourced: number,
  alreadyPresent: number,
  exhausted: boolean,
  results: SourceOutcome[],
  enriched: number,
): string {
  const failed = results.filter((r) => r.error);
  if (sourced > 0) {
    const skipped = alreadyPresent ? ` ${alreadyPresent} were already in the project.` : '';
    const credits = enriched ? ` ${enriched} Apollo enrichment${enriched === 1 ? '' : 's'} used.` : '';
    return `Added ${sourced} new expert${sourced === 1 ? '' : 's'}.${skipped}${credits}`;
  }
  if (failed.length === results.length && failed[0]?.error) {
    return `Apollo could not be reached: ${failed[0].error}`;
  }
  if (exhausted) {
    return 'Apollo has no more matches for these category searches. Broaden the titles or keywords to find more.';
  }
  if (alreadyPresent > 0) {
    return `No new experts — all ${alreadyPresent} people Apollo returned are already in this project.`;
  }
  return 'Apollo returned no results for these category searches.';
}

export default withAdmin(handler);
