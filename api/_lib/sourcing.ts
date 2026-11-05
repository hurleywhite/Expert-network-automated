import { getSupabaseAdmin } from './supabase';

/**
 * Apollo sourcing for one category.
 *
 * Apollo is paginated and the previous implementation always asked for page 1,
 * so after the first run every result was a duplicate and nothing was added.
 * Each category now remembers how far it has been read and the next run
 * continues from there.
 */

/** Apollo rejects per_page above this. */
const APOLLO_MAX_PER_PAGE = 100;
/** Bounded so one run cannot exceed the function's 60s budget. */
const MAX_PAGES_PER_RUN = 5;

export interface SourceOutcome {
  category_id: string;
  category_name: string;
  sourced: number;        // new expert profiles created
  already_present: number; // returned by Apollo but already in this project
  pages_read: number;
  next_page: number;
  exhausted: boolean;      // Apollo has no more results for this search
  error?: string;
}

export async function sourceCategory(
  category: any,
  projectId: string,
  wanted: number,
): Promise<SourceOutcome> {
  const supabase = getSupabaseAdmin();
  const apolloKey = process.env.APOLLO_API_KEY as string;

  const criteria = category.search_criteria || {};
  const outcome: SourceOutcome = {
    category_id: category.id,
    category_name: category.name,
    sourced: 0,
    already_present: 0,
    pages_read: 0,
    next_page: (category.last_sourced_page || 0) + 1,
    exhausted: false,
  };

  const perPage = Math.min(Math.max(wanted, 1), APOLLO_MAX_PER_PAGE);
  let page = outcome.next_page;

  // Keep reading pages until we have enough NEW people, Apollo runs dry, or we
  // hit the page budget. Without this a run that lands entirely on people we
  // already have would again appear to do nothing.
  while (outcome.sourced < wanted && outcome.pages_read < MAX_PAGES_PER_RUN) {
    const searchParams: any = { per_page: perPage, page };
    if (criteria.titles?.length) searchParams.person_titles = criteria.titles;
    if (criteria.industries?.length) searchParams.q_organization_keyword_tags = criteria.industries;
    if (criteria.keywords?.length) searchParams.q_keywords = criteria.keywords.join(' ');

    const res = await fetch('https://api.apollo.io/v1/mixed_people/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-cache', 'X-Api-Key': apolloKey },
      body: JSON.stringify(searchParams),
    });

    if (!res.ok) {
      const text = await res.text();
      outcome.error = `Apollo returned ${res.status}: ${text.slice(0, 200)}`;
      break;
    }

    const data = await res.json();
    const people = data.people || [];
    outcome.pages_read++;
    page++;

    if (people.length === 0) {
      outcome.exhausted = true;
      break;
    }

    for (const person of people) {
      if (outcome.sourced >= wanted) break;
      const added = await importPerson(person, projectId, category);
      if (added === 'created') outcome.sourced++;
      else if (added === 'existing') outcome.already_present++;
    }

    // A short page means Apollo has nothing further for this search.
    if (people.length < perPage) {
      outcome.exhausted = true;
      break;
    }
  }

  outcome.next_page = page;

  await supabase
    .from('project_categories')
    .update({ last_sourced_page: page - 1, last_sourced_at: new Date().toISOString() })
    .eq('id', category.id);

  return outcome;
}

async function importPerson(
  person: any,
  projectId: string,
  category: any,
): Promise<'created' | 'existing' | 'failed'> {
  const supabase = getSupabaseAdmin();

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

  if (!candidateData.full_name) return 'failed';

  let candidateId: string;

  // Match on email where Apollo gave one, otherwise on the LinkedIn URL, which
  // is the only other stable identifier it returns. Matching on name alone
  // would merge different people who happen to share one.
  const existingQuery = candidateData.email
    ? supabase.from('candidates').select('id').eq('email', candidateData.email)
    : candidateData.linkedin_url
    ? supabase.from('candidates').select('id').eq('linkedin_url', candidateData.linkedin_url)
    : null;

  const existing = existingQuery ? (await existingQuery.maybeSingle()).data : null;

  if (existing) {
    candidateId = existing.id;
  } else {
    const { data: created, error } = await supabase
      .from('candidates')
      .insert(candidateData)
      .select('id')
      .single();
    if (error || !created) return 'failed';
    candidateId = created.id;
  }

  const { data: existingProfile } = await supabase
    .from('expert_profiles')
    .select('id')
    .eq('candidate_id', candidateId)
    .eq('project_id', projectId)
    .maybeSingle();

  if (existingProfile) return 'existing';

  const { data: profile, error: profileError } = await supabase
    .from('expert_profiles')
    .insert({
      candidate_id: candidateId,
      project_id: projectId,
      category_id: category.id,
      status: 'sourced',
    })
    .select('id')
    .single();

  if (profileError || !profile) return 'failed';

  await supabase.from('expert_activities').insert({
    expert_profile_id: profile.id,
    activity_type: 'added',
    description: `Sourced from Apollo via category: ${category.name}`,
  });

  return 'created';
}
