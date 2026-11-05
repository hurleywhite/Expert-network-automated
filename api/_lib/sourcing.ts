import { getSupabaseAdmin } from './supabase';

/**
 * Apollo sourcing for one category.
 *
 * Two Apollo calls per batch, because the search endpoint alone no longer
 * returns usable records:
 *
 *   1. mixed_people/api_search   finds matches. Returns ids, titles and
 *      companies, but obfuscated surnames and no email or LinkedIn URL.
 *   2. people/bulk_match         enriches up to 10 of those ids at a time
 *      into full records. This is the step that costs credits.
 *
 * The old code called /v1/mixed_people/search, which Apollo now rejects with
 * a 422 telling callers to move to api_search, and it asked for page 1 every
 * time, so even before the deprecation it re-read the same people and added
 * nobody after the first run. Each category now remembers how far it has been
 * read.
 */

const APOLLO_BASE = 'https://api.apollo.io/api/v1';
const APOLLO_MAX_PER_PAGE = 100;
const ENRICH_BATCH = 10;          // Apollo's documented maximum per bulk_match call
const MAX_PAGES_PER_RUN = 3;      // keeps a run inside the 60s function budget

export interface SourceOutcome {
  category_id: string;
  category_name: string;
  sourced: number;
  already_present: number;
  enriched: number;            // people sent through bulk_match, i.e. credits spent
  pages_read: number;
  next_page: number;
  exhausted: boolean;
  total_available?: number;
  error?: string;
}

function apolloHeaders() {
  return {
    'Content-Type': 'application/json',
    'Cache-Control': 'no-cache',
    'x-api-key': process.env.APOLLO_API_KEY as string,
  };
}

/** api_search takes its filters as query-string params, not a JSON body. */
function searchUrl(criteria: any, page: number, perPage: number): string {
  const qs = new URLSearchParams();
  qs.set('page', String(page));
  qs.set('per_page', String(perPage));

  for (const title of criteria.titles || []) qs.append('person_titles[]', title);
  if (criteria.keywords?.length) qs.set('q_keywords', criteria.keywords.join(' '));
  for (const loc of criteria.locations || []) qs.append('person_locations[]', loc);

  return `${APOLLO_BASE}/mixed_people/api_search?${qs.toString()}`;
}

async function search(criteria: any, page: number, perPage: number) {
  const res = await fetch(searchUrl(criteria, page, perPage), {
    method: 'POST',
    headers: apolloHeaders(),
  });
  if (!res.ok) {
    throw new Error(`Apollo search returned ${res.status}: ${(await res.text()).slice(0, 200)}`);
  }
  return res.json();
}

/** Turns search hits into full records. This is the credit-consuming step. */
async function enrich(ids: string[]): Promise<any[]> {
  const out: any[] = [];
  for (let i = 0; i < ids.length; i += ENRICH_BATCH) {
    const batch = ids.slice(i, i + ENRICH_BATCH);
    const res = await fetch(`${APOLLO_BASE}/people/bulk_match`, {
      method: 'POST',
      headers: apolloHeaders(),
      body: JSON.stringify({ details: batch.map((id) => ({ id })) }),
    });
    if (!res.ok) {
      // A failed enrichment should not lose the whole run; keep what we have.
      console.error(`Apollo bulk_match ${res.status}: ${(await res.text()).slice(0, 200)}`);
      continue;
    }
    const data = await res.json();
    for (const m of data.matches || data.people || []) if (m) out.push(m);
  }
  return out;
}

export async function sourceCategory(
  category: any,
  projectId: string,
  wanted: number,
): Promise<SourceOutcome> {
  const supabase = getSupabaseAdmin();
  const criteria = category.search_criteria || {};

  const outcome: SourceOutcome = {
    category_id: category.id,
    category_name: category.name,
    sourced: 0,
    already_present: 0,
    enriched: 0,
    pages_read: 0,
    next_page: (category.last_sourced_page || 0) + 1,
    exhausted: false,
  };

  const perPage = Math.min(Math.max(wanted, 1), APOLLO_MAX_PER_PAGE);
  let page = outcome.next_page;

  try {
    while (outcome.sourced < wanted && outcome.pages_read < MAX_PAGES_PER_RUN) {
      const data = await search(criteria, page, perPage);
      const people = data.people || [];
      outcome.total_available = data.total_entries;
      outcome.pages_read++;
      page++;

      if (people.length === 0) {
        outcome.exhausted = true;
        break;
      }

      // Skip anyone already on this project before spending a credit on them.
      const fresh: string[] = [];
      for (const p of people) {
        if (!p?.id) continue;
        const { data: seen } = await supabase
          .from('candidates')
          .select('id')
          .eq('apollo_id', p.id)
          .maybeSingle();
        if (seen) {
          const { data: onProject } = await supabase
            .from('expert_profiles')
            .select('id')
            .eq('candidate_id', seen.id)
            .eq('project_id', projectId)
            .maybeSingle();
          if (onProject) {
            outcome.already_present++;
            continue;
          }
        }
        fresh.push(p.id);
        if (fresh.length >= wanted - outcome.sourced) break;
      }

      if (fresh.length) {
        const enriched = await enrich(fresh);
        outcome.enriched += enriched.length;
        for (const person of enriched) {
          if (outcome.sourced >= wanted) break;
          const r = await importPerson(person, projectId, category);
          if (r === 'created') outcome.sourced++;
          else if (r === 'existing') outcome.already_present++;
        }
      }

      if (people.length < perPage) {
        outcome.exhausted = true;
        break;
      }
    }
  } catch (err: any) {
    outcome.error = err?.message || 'Unknown Apollo error';
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

  const fullName = `${person.first_name || ''} ${person.last_name || ''}`.trim();
  if (!fullName) return 'failed';

  const candidateData = {
    apollo_id: person.id || null,
    first_name: person.first_name || '',
    last_name: person.last_name || '',
    full_name: fullName,
    title: person.title || null,
    company: person.organization?.name || person.account?.name || null,
    company_employee_count: person.organization?.estimated_num_employees || null,
    region: [person.city, person.state, person.country].filter(Boolean).join(', ') || null,
    linkedin_url: person.linkedin_url || null,
    headline: person.headline || null,
    photo_url: person.photo_url || null,
    email: person.email || null,
    email_verified: person.email_status === 'verified',
  };

  // Match on Apollo's own id first: it is stable even when the email changes.
  let candidateId: string | null = null;
  for (const [col, val] of [
    ['apollo_id', candidateData.apollo_id],
    ['email', candidateData.email],
    ['linkedin_url', candidateData.linkedin_url],
  ] as const) {
    if (!val) continue;
    const { data } = await supabase.from('candidates').select('id').eq(col, val).maybeSingle();
    if (data) { candidateId = data.id; break; }
  }

  if (!candidateId) {
    const { data, error } = await supabase.from('candidates').insert(candidateData).select('id').single();
    if (error || !data) return 'failed';
    candidateId = data.id;
  } else {
    // Backfill anything the earlier record was missing.
    await supabase.from('candidates').update(candidateData).eq('id', candidateId);
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
    .insert({ candidate_id: candidateId, project_id: projectId, category_id: category.id, status: 'sourced' })
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
