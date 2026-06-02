-- ============================================================================
-- Supabase schema for the Expert Network / LinkedIn outreach app
-- ----------------------------------------------------------------------------
-- IMPORTANT: This schema was RECONSTRUCTED from the application code on
-- 2026-06-02, because the original Supabase project was auto-paused for >90
-- days and could not be restored, and the schema had never been committed to
-- the repo. It is the authoritative source going forward — keep it in sync
-- with any future schema changes.
--
-- Sources used to reconstruct it:
--   - backend/app/models.py and backend/alembic/versions/d001_add_glg_tables.py
--     (project_briefs, candidates, project_categories, screener_questions,
--      expert_profiles, expert_activities, linkedin_outreach)
--   - api/outreach/*.ts  (outreach_campaigns, outreach_leads — these two tables
--     existed ONLY in the dead database; columns inferred from code usage)
--
-- To apply: run this whole file against a fresh Supabase project
-- (SQL Editor, or `supabase db execute`). It is idempotent-ish: it uses
-- CREATE TABLE IF NOT EXISTS so re-running won't drop data.
--
-- Status fields use TEXT + CHECK constraints (not Postgres ENUMs) to match how
-- the serverless code writes plain strings, and to avoid enum-cast friction
-- with supabase-js.
-- ============================================================================

create extension if not exists pgcrypto;  -- for gen_random_uuid()

-- ─── project_briefs ─────────────────────────────────────────────────────────
create table if not exists public.project_briefs (
  id                uuid primary key default gen_random_uuid(),
  name              text not null,
  industry          text,
  subvertical       text,
  company_size_min  integer,
  regions           jsonb not null default '[]'::jsonb,
  titles_include    jsonb not null default '[]'::jsonb,
  titles_exclude    jsonb not null default '[]'::jsonb,
  keywords          jsonb not null default '[]'::jsonb,
  exclusions        jsonb not null default '[]'::jsonb,
  created_at        timestamptz not null default now()
);

-- ─── candidates ─────────────────────────────────────────────────────────────
create table if not exists public.candidates (
  id                      uuid primary key default gen_random_uuid(),
  first_name              text,
  last_name               text,
  full_name               text not null,
  title                   text,
  company                 text,
  company_employee_count  integer,
  region                  text,
  linkedin_url            text,
  headline                text,
  photo_url               text,
  email                   text,
  email_verified          boolean not null default false,
  status                  text not null default 'new',
  created_at              timestamptz not null default now(),
  updated_at              timestamptz default now(),
  constraint uq_candidate_email unique (email)  -- Postgres allows multiple NULLs
);
create index if not exists ix_candidate_company on public.candidates (company);
create index if not exists ix_candidate_status  on public.candidates (status);

-- ─── project_categories (segments) ──────────────────────────────────────────
create table if not exists public.project_categories (
  id               uuid primary key default gen_random_uuid(),
  project_id       uuid not null references public.project_briefs(id) on delete cascade,
  name             text not null,
  description      text,
  search_criteria  jsonb not null default '{}'::jsonb,  -- { titles[], industries[], keywords[] }
  sort_order       integer not null default 0,
  created_at       timestamptz not null default now()
);
create index if not exists ix_project_categories_project on public.project_categories (project_id);

-- ─── screener_questions ─────────────────────────────────────────────────────
create table if not exists public.screener_questions (
  id             uuid primary key default gen_random_uuid(),
  project_id     uuid not null references public.project_briefs(id) on delete cascade,
  question_text  text not null,
  question_type  text not null default 'free_text'
                   check (question_type in ('multiple_choice','free_text','yes_no','scale')),
  options        jsonb not null default '[]'::jsonb,
  sort_order     integer not null default 0,
  created_at     timestamptz not null default now()
);
create index if not exists ix_screener_questions_project on public.screener_questions (project_id);

-- ─── expert_profiles ────────────────────────────────────────────────────────
create table if not exists public.expert_profiles (
  id                  uuid primary key default gen_random_uuid(),
  candidate_id        uuid not null references public.candidates(id) on delete cascade,
  project_id          uuid not null references public.project_briefs(id) on delete cascade,
  category_id         uuid references public.project_categories(id) on delete set null,
  ai_overview         text,
  project_expertise   jsonb not null default '[]'::jsonb,
  relevance_score     double precision,
  rate_per_hour       numeric(10,2),
  exa_research        jsonb not null default '{}'::jsonb,
  screener_responses  jsonb not null default '{}'::jsonb,
  work_experience     jsonb not null default '[]'::jsonb,
  status              text not null default 'sourced'
                        check (status in ('sourced','screened','shortlisted','scheduled','completed','rejected')),
  created_at          timestamptz not null default now(),
  updated_at          timestamptz default now()
);
create index if not exists ix_expert_profile_candidate_project on public.expert_profiles (candidate_id, project_id);
create index if not exists ix_expert_profile_category on public.expert_profiles (category_id);
create index if not exists ix_expert_profile_project on public.expert_profiles (project_id);

-- ─── expert_activities ──────────────────────────────────────────────────────
create table if not exists public.expert_activities (
  id                 uuid primary key default gen_random_uuid(),
  expert_profile_id  uuid not null references public.expert_profiles(id) on delete cascade,
  activity_type      text not null
                       check (activity_type in ('added','call_requested','call_scheduled','call_completed',
                                                'email_sent','reply_received','linkedin_sent','linkedin_connected')),
  description        text,
  created_at         timestamptz not null default now()
);
create index if not exists ix_expert_activities_profile on public.expert_activities (expert_profile_id);

-- ─── linkedin_outreach ──────────────────────────────────────────────────────
create table if not exists public.linkedin_outreach (
  id                 uuid primary key default gen_random_uuid(),
  expert_profile_id  uuid not null references public.expert_profiles(id) on delete cascade,
  linkedin_url       text not null,
  connection_note    varchar(300),
  follow_up_message  text,
  status             text not null default 'pending'
                       check (status in ('pending','connection_sent','connected','message_sent','replied','failed')),
  sent_at            timestamptz,
  connected_at       timestamptz,
  replied_at         timestamptz,
  error_message      text,
  created_at         timestamptz not null default now()
);
create index if not exists ix_linkedin_outreach_profile on public.linkedin_outreach (expert_profile_id);

-- ─── outreach_campaigns (reconstructed from api/outreach/*.ts) ───────────────
create table if not exists public.outreach_campaigns (
  id                    uuid primary key default gen_random_uuid(),
  project_id            uuid not null references public.project_briefs(id) on delete cascade,
  name                  text not null,
  channel               text not null default 'linkedin'
                          check (channel in ('linkedin','email','reddit')),
  status                text not null default 'draft'
                          check (status in ('draft','active','paused','completed')),
  sender_name           text,
  sender_title          text,
  min_relevance_score   integer default 50,
  target_seniority      jsonb not null default '[]'::jsonb,
  total_leads           integer not null default 0,
  connections_sent      integer not null default 0,
  connections_accepted  integer not null default 0,
  messages_sent         integer not null default 0,
  replies_received      integer not null default 0,
  meetings_booked       integer not null default 0,
  daily_limit           integer not null default 30,
  heyreach_campaign_id  text,
  heyreach_list_id      text,
  created_at            timestamptz not null default now(),
  updated_at            timestamptz default now()
);
create index if not exists ix_outreach_campaigns_project on public.outreach_campaigns (project_id);

-- ─── outreach_leads (reconstructed from api/outreach/*.ts) ───────────────────
create table if not exists public.outreach_leads (
  id                       uuid primary key default gen_random_uuid(),
  campaign_id              uuid not null references public.outreach_campaigns(id) on delete cascade,
  expert_profile_id        uuid references public.expert_profiles(id) on delete set null,
  full_name                text,
  title                    text,
  company                  text,
  linkedin_url             text,
  email                    text,
  seniority_level          text,
  connection_note          text,
  follow_up_1              text,
  follow_up_2              text,
  follow_up_3              text,
  inmail_message           text,
  personalization_context  jsonb not null default '{}'::jsonb,
  current_step             text default 'connection_request',
  heyreach_lead_id         text,
  connection_sent_at       timestamptz,
  connection_accepted_at   timestamptz,
  replied_at               timestamptz,
  reply_sentiment          text,
  meeting_booked_at        timestamptz,
  opted_out                boolean not null default false,
  created_at               timestamptz not null default now()
);
create index if not exists ix_outreach_leads_campaign on public.outreach_leads (campaign_id);
create index if not exists ix_outreach_leads_profile  on public.outreach_leads (expert_profile_id);

-- ============================================================================
-- ROW-LEVEL SECURITY  (READ THIS)
-- ----------------------------------------------------------------------------
-- The frontend talks to Supabase with the ANON key directly (see
-- frontend/src/api/client.ts), while the serverless API routes use the
-- service-role key (which bypasses RLS).
--
-- With RLS DISABLED (the default after CREATE TABLE), anyone holding the anon
-- key — which ships in the frontend bundle and is therefore public — can read
-- and write every row, including candidate names, emails, and LinkedIn URLs.
-- That is an exposure you should not ship to a public URL.
--
-- Recommended (uncomment ONE approach):
--
--   (A) Lock down to logged-in users only. Requires the frontend to use a
--       Supabase auth session instead of the bare anon key.
--
--   do $$ declare t text;
--   begin
--     for t in select unnest(array['project_briefs','candidates','project_categories',
--       'screener_questions','expert_profiles','expert_activities','linkedin_outreach',
--       'outreach_campaigns','outreach_leads']) loop
--       execute format('alter table public.%I enable row level security;', t);
--       execute format($p$create policy "authenticated_all" on public.%I
--         for all to authenticated using (true) with check (true);$p$, t);
--     end loop;
--   end $$;
--
--   (B) Internal-only tool, single operator, NOT on a public URL: you may leave
--       RLS disabled — but treat the deployed URL and anon key as secrets.
-- ============================================================================
