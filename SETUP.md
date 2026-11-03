# Setup — connecting the app to Supabase

The app is a React/Vite frontend plus nine Vercel serverless functions. The
browser holds **no** database credential: every read and write goes through
`/api/data`, which authenticates with a server-only service-role key.

There are three steps. They take about five minutes.

---

## 1. Create the schema

Open your Supabase project → **SQL Editor** → **New query**, paste the entire
contents of [`db/supabase_schema.sql`](db/supabase_schema.sql), and run it.

It creates 11 tables and then locks the database down:

| Table | Holds |
|---|---|
| `project_briefs` | one row per research project |
| `project_categories` | the expert segments within a project |
| `screener_questions` | qualification questions per project |
| `candidates` | people sourced from Apollo |
| `expert_profiles` | a candidate's AI-written profile *for a given project* |
| `expert_activities` | timeline events per expert |
| `linkedin_outreach` | per-expert LinkedIn connection state |
| `outreach_campaigns` | a campaign (LinkedIn / email / Reddit) |
| `outreach_leads` | one lead per campaign, with its full message sequence |
| `message_drafts` | email drafts awaiting review |
| `rejection_learnings` | rejected drafts, kept so future copy improves |

The script is safe to re-run — every table uses `CREATE TABLE IF NOT EXISTS`.

### About the lockdown

The last block enables row-level security on all 11 tables and creates **no
policies**, then revokes the default grants from the `anon` and `authenticated`
roles. The effect:

- the browser-facing roles are denied on every row and every operation
- `service_role` — which the `/api` functions use — is unaffected

This is deliberate. If you ever point a browser client at this database again,
it will read nothing until you add explicit policies.

---

## 2. Set the environment variables in Vercel

In Supabase: **Project Settings → API**. Copy the Project URL and the
`service_role` secret.

In Vercel: project **moderated-interviews-automated** → **Settings →
Environment Variables**. Add these to *Production, Preview and Development*:

| Name | Value | Required |
|---|---|---|
| `SUPABASE_URL` | `https://<project-ref>.supabase.co` | **yes** |
| `SUPABASE_SERVICE_ROLE_KEY` | the `service_role` secret | **yes** |
| `ANTHROPIC_API_KEY` | `sk-ant-…` | yes — document parsing, profiles, campaign copy |
| `APOLLO_API_KEY` | Apollo key | yes — sourcing experts |
| `EXA_API_KEY` | Exa key | optional — adds web research to profiles |
| `HEYREACH_API_KEY` | HeyReach key | optional — pushing campaigns to LinkedIn |
| `CRON_SECRET` | any long random string | optional — if set, the daily keep-alive requires it |

> **The service-role key bypasses row-level security.** Never name it with a
> `VITE_` prefix and never put it in `frontend/.env`: anything `VITE_*` is
> compiled into the public JavaScript bundle.

`VITE_API_URL` should be left **unset** in production — the frontend and the
functions share an origin, so relative `/api/*` paths resolve on their own.

---

## 3. Verify

```bash
SUPABASE_URL=https://<ref>.supabase.co \
SUPABASE_SERVICE_ROLE_KEY=<service-role-key> \
SUPABASE_ANON_KEY=<anon-key> \
node scripts/verify-setup.mjs
```

This checks that all 11 tables exist, that the foreign keys the app joins on
resolve, and — if you pass `SUPABASE_ANON_KEY` — that the browser-facing role is
genuinely denied. Add `DEPLOY_URL=https://…` to also probe the live API.

It exits non-zero on failure, so it works in CI.

---

## The health check and the keep-alive

`GET /api/health` reports whether the app is wired up correctly:

| Response | Meaning |
|---|---|
| `200 {"status":"ok"}` | configured, and the database answered |
| `503 {"status":"misconfigured"}` | a required variable is missing — it names which |
| `503 {"status":"schema-missing"}` | connected, but step 1 hasn't been run |
| `503 {"status":"database-unreachable"}` | wrong key, or the project is paused |

It lists which variables are **set**, never their values.

`vercel.json` also runs this endpoint once a day via Vercel Cron. That is
deliberate: free-tier Supabase projects pause after about a week of inactivity,
and that is exactly what took the previous backend down. A daily read keeps the
project awake, so an app you only use now and then does not quietly die between
campaigns.

If you set `CRON_SECRET`, the cron request must present it. Leave it unset and
the endpoint stays open — it is read-only and already behind Vercel's
deployment protection.

> Vercel's Hobby plan allows cron jobs to run **once per day**. If you are on
> Hobby, leave the schedule as it is; a more frequent schedule is rejected.

---

## How the app hangs together

```
Browser ──fetch──► /api/data/*            ─► Supabase (service role)
                   /api/projects/from-document ─► Claude  ─► Supabase
                   /api/sourcing/*              ─► Apollo  ─► Supabase
                   /api/profiles/generate       ─► Exa + Claude ─► Supabase
                   /api/outreach/create-campaign ─► Claude ─► Supabase
                   /api/outreach/push-to-heyreach ─► HeyReach
```

The normal run of work:

1. **Create a project** — paste a requirements document on the dashboard.
   Claude extracts the industry, expert categories and screener questions.
2. **Source experts** — *Source All Categories* queries Apollo per category and
   writes candidates plus expert profiles.
3. **Generate profiles** — Exa researches each person, Claude writes the
   overview, relevance score, rate and screener answers.
4. **Create a campaign** — Claude writes a connection note, three follow-ups and
   an InMail per lead, capped at one lead per company so you don't hit the same
   employer repeatedly.
5. **Send** — push to HeyReach, or export the campaign as JSON.

## Troubleshooting

**Something is wrong but you don't know what.**
Open `/api/health` on the deployment. It will tell you whether the variables
are set, whether the database answers, and whether the schema exists.

**Calls return 503 naming a missing variable.**
That variable is not set on the deployment, or was added after the last build.
Add it and redeploy — environment variables are read at runtime, but a
deployment created before the variable existed will not see it until it is
rebuilt.

**Supabase says the project is paused.**
Free-tier projects pause after about a week of inactivity, which is what broke
the previous backend. Resume it from the dashboard. The daily cron described
above is there to stop it recurring — if it keeps happening, check that the
cron is actually running (Vercel → the project → *Cron Jobs*).

**The deployed URL asks you to log in.**
Vercel SSO protection is on for this project (Settings → Deployment Protection).
That is why the data is safe on a `.vercel.app` URL — leave it on unless you
attach a custom domain you intend to be public.
