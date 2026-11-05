import type { VercelRequest, VercelResponse } from '@vercel/node';
import { getSupabaseAdmin } from '../_lib/supabase';
import { withAdmin } from '../_lib/auth';

async function handler(req: VercelRequest, res: VercelResponse) {
  if (req.method !== 'POST') return res.status(405).json({ error: 'Method not allowed' });

  const { project_id, category_id, max_results = 25 } = req.body;
  if (!project_id || !category_id) return res.status(400).json({ error: 'project_id and category_id are required' });

  const apolloKey = process.env.APOLLO_API_KEY;
  if (!apolloKey) return res.status(500).json({ error: 'APOLLO_API_KEY not configured' });

  try {
    const supabase = getSupabaseAdmin();

    const { data: category, error: catError } = await supabase
      .from('project_categories')
      .select('*')
      .eq('id', category_id)
      .single();

    if (catError) throw catError;

    const criteria = category.search_criteria || {};
    const searchParams: any = {
      per_page: max_results,
      page: 1,
    };

    if (criteria.titles?.length) searchParams.person_titles = criteria.titles;
    if (criteria.industries?.length) searchParams.q_organization_keyword_tags = criteria.industries;
    if (criteria.keywords?.length) searchParams.q_keywords = criteria.keywords.join(' ');

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
      const errText = await apolloRes.text();
      throw new Error(`Apollo API error: ${errText}`);
    }

    const apolloData = await apolloRes.json();
    const people = apolloData.people || [];
    let sourced = 0;

    for (const person of people) {
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
          if (insertError) continue;
          candidateId = newCandidate.id;
        }
      } else {
        const { data: newCandidate, error: insertError } = await supabase
          .from('candidates')
          .insert({ ...candidateData, email: null })
          .select('id')
          .single();
        if (insertError) continue;
        candidateId = newCandidate.id;
      }

      const { data: existingProfile } = await supabase
        .from('expert_profiles')
        .select('id')
        .eq('candidate_id', candidateId)
        .eq('project_id', project_id)
        .maybeSingle();

      if (!existingProfile) {
        const { data: newProfile } = await supabase
          .from('expert_profiles')
          .insert({
            candidate_id: candidateId,
            project_id: project_id,
            category_id: category_id,
            status: 'sourced',
          })
          .select('id')
          .single();

        if (newProfile) {
          await supabase.from('expert_activities').insert({
            expert_profile_id: newProfile.id,
            activity_type: 'added',
            description: `Sourced from Apollo via category: ${category.name}`,
          });
        }
        sourced++;
      }
    }

    return res.status(200).json({
      project_id,
      category_id,
      category_name: category.name,
      sourced,
    });

  } catch (error: any) {
    console.error('Error sourcing by category:', error);
    return res.status(500).json({ error: error.message || 'Internal server error' });
  }
}

export default withAdmin(handler);
