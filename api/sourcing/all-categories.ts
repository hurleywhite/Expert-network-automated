import type { VercelRequest, VercelResponse } from '@vercel/node';
import { getSupabaseAdmin } from '../_lib/supabase';
import { withAdmin } from '../_lib/auth';

async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { project_id, max_per_category = 25 } = req.body;
  if (!project_id) return res.status(400).json({ error: 'project_id is required' });

  const apolloKey = process.env.APOLLO_API_KEY;
  if (!apolloKey) return res.status(500).json({ error: 'APOLLO_API_KEY not configured' });

  try {
    const supabase = getSupabaseAdmin();

    // Get all categories for this project
    const { data: categories, error: catError } = await supabase
      .from('project_categories')
      .select('*')
      .eq('project_id', project_id)
      .order('sort_order');

    if (catError) throw catError;
    if (!categories?.length) return res.status(400).json({ error: 'No categories found for this project' });

    let totalSourced = 0;

    for (const category of categories) {
      const criteria = category.search_criteria || {};
      const titles = criteria.titles || [];
      const industries = criteria.industries || [];
      const keywords = criteria.keywords || [];

      // Build Apollo search params
      const searchParams: any = {
        per_page: max_per_category,
        page: 1,
      };

      if (titles.length > 0) searchParams.person_titles = titles;
      if (industries.length > 0) searchParams.q_organization_keyword_tags = industries;
      if (keywords.length > 0) searchParams.q_keywords = keywords.join(' ');

      // Search Apollo
      const apolloRes = await fetch('https://api.apollo.io/v1/mixed_people/search', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Cache-Control': 'no-cache',
          'X-Api-Key': apolloKey,
        },
        body: JSON.stringify(searchParams),
      });

      if (!apolloRes.ok) {
        console.error(`Apollo API error for category ${category.name}:`, await apolloRes.text());
        continue;
      }

      const apolloData = await apolloRes.json();
      const people = apolloData.people || [];

      for (const person of people) {
        // Upsert candidate
        const candidateData = {
          first_name: person.first_name || '',
          last_name: person.last_name || '',
          full_name: `${person.first_name || ''} ${person.last_name || ''}`.trim(),
          title: person.title || null,
          company: person.organization?.name || null,
          company_employee_count: person.organization?.estimated_num_employees || null,
          region: [person.city, person.state, person.country].filter(Boolean).join(', ') || null,
          linkedin_url: person.linkedin_url || null,
          headline: person.headline || null,
          photo_url: person.photo_url || null,
          email: person.email || null,
          email_verified: person.email_status === 'verified',
        };

        let candidateId: string;

        // Check if candidate already exists by email or linkedin_url
        if (candidateData.email) {
          const { data: existing } = await supabase
            .from('candidates')
            .select('id')
            .eq('email', candidateData.email)
            .maybeSingle();

          if (existing) {
            candidateId = existing.id;
          } else {
            const { data: newCandidate, error: insertError } = await supabase
              .from('candidates')
              .insert(candidateData)
              .select('id')
              .single();
            if (insertError) {
              console.error('Failed to insert candidate:', insertError);
              continue;
            }
            candidateId = newCandidate.id;
          }
        } else {
          const { data: newCandidate, error: insertError } = await supabase
            .from('candidates')
            .insert({ ...candidateData, email: null })
            .select('id')
            .single();
          if (insertError) {
            console.error('Failed to insert candidate:', insertError);
            continue;
          }
          candidateId = newCandidate.id;
        }

        // Check if expert profile already exists
        const { data: existingProfile } = await supabase
          .from('expert_profiles')
          .select('id')
          .eq('candidate_id', candidateId)
          .eq('project_id', project_id)
          .maybeSingle();

        if (!existingProfile) {
          // Create expert profile
          await supabase.from('expert_profiles').insert({
            candidate_id: candidateId,
            project_id: project_id,
            category_id: category.id,
            status: 'sourced',
          });

          // Log activity
          const { data: newProfile } = await supabase
            .from('expert_profiles')
            .select('id')
            .eq('candidate_id', candidateId)
            .eq('project_id', project_id)
            .single();

          if (newProfile) {
            await supabase.from('expert_activities').insert({
              expert_profile_id: newProfile.id,
              activity_type: 'added',
              description: `Sourced from Apollo via category: ${category.name}`,
            });
          }

          totalSourced++;
        }
      }
    }

    return res.status(200).json({
      project_id,
      categories_searched: categories.length,
      total_sourced: totalSourced,
    });

  } catch (error: any) {
    console.error('Error sourcing candidates:', error);
    return res.status(500).json({ error: error.message || 'Internal server error' });
  }
}

export default withAdmin(handler);
