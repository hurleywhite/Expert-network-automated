#!/usr/bin/env node
/**
 * Route-level tests for api/data/[...path].ts.
 *
 *   node scripts/test-router.cjs
 *
 * Compiles the API with tsc into a temp directory, then drives the handler
 * with a stubbed repo layer. No database and no network required, so this is
 * safe to run in CI. Exits non-zero on failure.
 */
const { execFileSync } = require('child_process');
const fs = require('fs');
const os = require('os');
const path = require('path');

const ROOT = path.join(__dirname, '..');
const OUT = fs.mkdtempSync(path.join(os.tmpdir(), 'api-router-'));

try {
  execFileSync('npx', ['tsc', '--outDir', OUT], { cwd: ROOT, stdio: 'pipe' });
} catch (e) {
  console.error('TypeScript compilation failed:\n' + (e.stdout || e.message));
  process.exit(2);
}
process.on('exit', () => fs.rmSync(OUT, { recursive: true, force: true }));

const Module = require('module');

const BUILD = path.join(OUT, 'api');
const repoPath = require.resolve(path.join(BUILD, '_lib', 'repo.js'));

let called = null;
const spy = (name) => (...args) => { called = { name, args }; return Promise.resolve({ ok: name }); };

// Pre-seed the module cache so the handler picks up stubs instead of the real repo.
const stub = {};
for (const fn of ['listProjects','getProject','listCategories','listScreenerQuestions','listExperts',
                  'getExpertProfile','updateExpertStatus','scheduleCall','getOutreachStatus',
                  'listCampaigns','approveDraft','rejectDraft','updateDraft']) stub[fn] = spy(fn);
const m = new Module(repoPath, null);
m.exports = stub; m.loaded = true; m.filename = repoPath;
require.cache[repoPath] = m;

const handler = require(path.join(BUILD, 'data', '[...path].js')).default;

function run(method, segments, { query = {}, body = undefined } = {}) {
  called = null;
  const req = { method, query: { ...query, path: segments }, body };
  let status = 200, payload;
  const res = { status(c) { status = c; return this; }, json(p) { payload = p; return this; } };
  return handler(req, res).then(() => ({ status, payload, called }));
}

const U = '11111111-2222-3333-4444-555555555555';
const C = 'aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee';

const cases = [
  ['GET  /projects',                       ['GET',    ['projects']],                              200, 'listProjects'],
  ['GET  /projects/:id',                   ['GET',    ['projects', U]],                           200, 'getProject'],
  ['GET  /projects/:id/categories',        ['GET',    ['projects', U, 'categories']],             200, 'listCategories'],
  ['GET  /projects/:id/screener-questions',['GET',    ['projects', U, 'screener-questions']],     200, 'listScreenerQuestions'],
  ['GET  /projects/:id/experts',           ['GET',    ['projects', U, 'experts']],                200, 'listExperts'],
  ['GET  /projects/:id/campaigns',         ['GET',    ['projects', U, 'campaigns']],              200, 'listCampaigns'],
  ['GET  /projects/:id/linkedin-outreach', ['GET',    ['projects', U, 'linkedin-outreach']],      200, 'getOutreachStatus'],
  ['GET  /experts/:id',                    ['GET',    ['experts', U]],                            200, 'getExpertProfile'],
  ['POST /experts/:id/schedule-call',      ['POST',   ['experts', U, 'schedule-call']],           200, 'scheduleCall'],
];

(async () => {
  let fail = 0;
  const ok = (m) => console.log(`  \x1b[32mPASS\x1b[0m  ${m}`);
  const bad = (m) => { fail++; console.log(`  \x1b[31mFAIL\x1b[0m  ${m}`); };

  console.log('\n\x1b[1mHappy-path routing\x1b[0m');
  for (const [label, [method, segs], wantStatus, wantFn] of cases) {
    const r = await run(method, segs);
    if (r.status !== wantStatus) bad(`${label} -> status ${r.status}, want ${wantStatus}`);
    else if (r.called?.name !== wantFn) bad(`${label} -> called ${r.called?.name}, want ${wantFn}`);
    else ok(`${label} -> ${wantFn}`);
  }

  console.log('\n\x1b[1mParameter passing\x1b[0m');
  {
    const r = await run('GET', ['projects', U, 'experts'], { query: { category_id: C } });
    r.called?.args?.[1] === C ? ok('category_id query param reaches listExperts')
                              : bad(`category_id not forwarded (got ${r.called?.args?.[1]})`);
  }
  {
    const r = await run('PATCH', ['experts', U], { body: { status: 'shortlisted' } });
    r.called?.name === 'updateExpertStatus' && r.called.args[1] === 'shortlisted'
      ? ok('PATCH /experts/:id forwards status') : bad(`status not forwarded: ${JSON.stringify(r.called)}`);
  }
  {
    const r = await run('PATCH', ['drafts', U], { body: JSON.stringify({ subject: 's', body: 'b' }) });
    r.called?.name === 'updateDraft' && r.called.args[1]?.subject === 's'
      ? ok('string JSON body is parsed') : bad(`string body not parsed: ${JSON.stringify(r.called)}`);
  }
  {
    const r = await run('POST', ['drafts', U, 'reject'], { body: { rejected_by: 'me', reason: 'too long' } });
    r.called?.name === 'rejectDraft' && r.called.args[2] === 'too long'
      ? ok('reject forwards reason') : bad(`reason not forwarded: ${JSON.stringify(r.called)}`);
  }

  console.log('\n\x1b[1mValidation and errors\x1b[0m');
  const errCases = [
    ['bad UUID rejected',            ['GET',    ['projects', 'not-a-uuid']],          400],
    ['unknown sub-resource',         ['GET',    ['projects', U, 'nope']],             404],
    ['unknown resource',             ['GET',    ['widgets']],                         404],
    ['no resource',                  ['GET',    []],                                  404],
    ['wrong method on /projects',    ['DELETE', ['projects']],                        405],
    ['wrong method on schedule-call',['GET',    ['experts', U, 'schedule-call']],     405],
    ['missing approved_by',          ['POST',   ['drafts', U, 'approve']],            400],
    ['missing status on PATCH',      ['PATCH',  ['experts', U]],                      400],
    ['bad category_id',              ['GET',    ['projects', U, 'experts']],          400, { category_id: 'xx' }],
  ];
  for (const [label, [method, segs], want, query] of errCases) {
    const r = await run(method, segs, { query: query || {} });
    r.status === want ? ok(`${label} -> ${want}`) : bad(`${label} -> ${r.status}, want ${want}`);
  }

  console.log('\n\x1b[1mError leakage\x1b[0m');
  const realErr = console.error; console.error = () => {};
  stub.listProjects = () => Promise.reject(new Error('postgres://user:hunter2@db:5432'));
  {
    const r = await run('GET', ['projects']);
    r.status === 500 && r.payload?.error === 'Internal server error'
      ? ok('500 does not echo internal message') : bad(`leaked: ${JSON.stringify(r.payload)}`);
  }
  stub.listCampaigns = () => {
    const e = new Error('Supabase is not configured: missing SUPABASE_URL. See SETUP.md.');
    e.name = 'ConfigError'; e.statusCode = 503;
    return Promise.reject(e);
  };
  {
    const r = await run('GET', ['projects', U, 'campaigns']);
    r.status === 503 && /missing SUPABASE_URL/.test(r.payload?.error || '')
      ? ok('missing env var -> 503 naming the variable')
      : bad(`config error -> ${r.status}: ${JSON.stringify(r.payload)}`);
  }
  stub.getProject = () => Promise.reject({ code: 'PGRST116', message: 'no rows' });
  {
    const r = await run('GET', ['projects', U]);
    r.status === 404 ? ok('PGRST116 maps to 404') : bad(`PGRST116 -> ${r.status}, want 404`);
  }

  // ── health endpoint ──────────────────────────────────────────────────────
  console.log('\n\x1b[1mHealth endpoint\x1b[0m');
  {
    const sbPath = require.resolve(path.join(BUILD, '_lib', 'supabase.js'));
    class ConfigError extends Error {
      constructor(m) { super(m); this.name = 'ConfigError'; this.statusCode = 503; }
    }
    let dbResult = { error: null };
    const sbStub = {
      ConfigError,
      getSupabaseAdmin: () => ({ from: () => ({ select: () => Promise.resolve(dbResult) }) }),
    };
    const sm = new Module(sbPath, null);
    sm.exports = sbStub; sm.loaded = true; sm.filename = sbPath;
    require.cache[sbPath] = sm;

    const health = require(path.join(BUILD, 'health.js')).default;
    const callHealth = () => {
      let status = 200, payload;
      const res = { status(c) { status = c; return this; }, json(p) { payload = p; return this; } };
      return health({ method: 'GET', headers: {}, query: {} }, res).then(() => ({ status, payload }));
    };

    const saved = { ...process.env };
    delete process.env.SUPABASE_URL; delete process.env.SUPABASE_SERVICE_ROLE_KEY;
    let r = await callHealth();
    r.status === 503 && r.payload?.status === 'misconfigured' && /SUPABASE_URL/.test(r.payload.error)
      ? ok('no env vars -> 503 misconfigured, naming them')
      : bad(`misconfigured case -> ${r.status}: ${JSON.stringify(r.payload)}`);

    r.payload?.env && r.payload.env.SUPABASE_SERVICE_ROLE_KEY === false
      ? ok('env report is booleans only (no values)')
      : bad(`env report wrong: ${JSON.stringify(r.payload?.env)}`);

    process.env.SUPABASE_URL = 'https://x.supabase.co';
    process.env.SUPABASE_SERVICE_ROLE_KEY = 'service-role-secret-value';
    dbResult = { error: null };
    r = await callHealth();
    r.status === 200 && r.payload?.status === 'ok' && r.payload?.database === 'reachable'
      ? ok('configured + reachable -> 200 ok') : bad(`ok case -> ${r.status}: ${JSON.stringify(r.payload)}`);

    JSON.stringify(r.payload).includes('service-role-secret-value')
      ? bad('health response leaked the key value') : ok('health response never contains key values');

    console.error = () => {};
    dbResult = { error: { code: 'PGRST205', message: "relation 'project_briefs' does not exist" } };
    r = await callHealth();
    r.status === 503 && r.payload?.status === 'schema-missing'
      ? ok('tables missing -> 503 schema-missing') : bad(`schema case -> ${r.status}: ${JSON.stringify(r.payload)}`);

    dbResult = { error: { code: 'XX000', message: 'connection refused' } };
    r = await callHealth();
    r.status === 503 && r.payload?.status === 'database-unreachable'
      ? ok('db down -> 503 database-unreachable') : bad(`db-down case -> ${r.status}: ${JSON.stringify(r.payload)}`);

    process.env = saved;
  }

  console.error = realErr;
  console.log(fail === 0 ? '\n\x1b[32mAll router checks passed.\x1b[0m\n'
                         : `\n\x1b[31m${fail} check(s) failed.\x1b[0m\n`);
  process.exit(fail ? 1 : 0);
})();
