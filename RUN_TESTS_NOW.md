# Run Tests Now - Quick Guide

## What Was Fixed

✅ **ISSUE 1:** SendGrid webhook now handles both `spamreport` and `spam_report` identically
✅ **ISSUE 2:** Idempotency key changed from `{draft_id}-{actor}` to `draft:{draft_id}`
✅ **BONUS:** Rate limit check moved to prevent duplicate events when rate limited

## Run These Commands

Copy and paste these commands into your terminal:

```bash
# Navigate to project
cd /Users/hurleywhite/expert-outreach

# Step 1: Build and start services
docker compose up -d --build

# Step 2: Wait for services
sleep 10

# Step 3: Run migrations
docker compose exec backend alembic upgrade head

# Step 4: Run all tests (quick check)
docker compose exec backend pytest -q

# Step 5: Run specific fix tests (verbose)
docker compose exec backend pytest -v tests/test_sendgrid_events.py tests/test_idempotency.py
```

## Expected Test Output

You should see **14 tests PASS**:

```
tests/test_sendgrid_events.py::test_spamreport_no_underscore PASSED          [  7%]
tests/test_sendgrid_events.py::test_spam_report_with_underscore PASSED      [ 14%]
tests/test_sendgrid_events.py::test_bounce_event PASSED                     [ 21%]
tests/test_sendgrid_events.py::test_dropped_event PASSED                    [ 28%]
tests/test_sendgrid_events.py::test_blocked_event PASSED                    [ 35%]
tests/test_sendgrid_events.py::test_unsubscribe_event PASSED                [ 42%]
tests/test_sendgrid_events.py::test_mixed_case_event_normalization PASSED   [ 50%]
tests/test_sendgrid_events.py::test_batch_events PASSED                     [ 57%]
tests/test_idempotency.py::test_idempotency_different_actors_single_send PASSED [ 64%]
tests/test_idempotency.py::test_idempotency_same_actor_multiple_calls PASSED    [ 71%]
tests/test_idempotency.py::test_idempotency_key_format PASSED               [ 78%]
tests/test_idempotency.py::test_concurrent_sends_with_different_actors PASSED   [ 85%]
tests/test_idempotency.py::test_rate_limited_does_not_create_duplicate_events PASSED [ 92%]
tests/test_idempotency.py::test_actor_stored_in_metadata PASSED             [100%]

============================== 14 passed in X.XXs ==============================
```

## Files Changed

1. **backend/app/routers/webhooks.py** - Fixed event name normalization
2. **backend/app/workers/jobs.py** - Fixed idempotency key
3. **backend/tests/test_sendgrid_events.py** - NEW (8 tests)
4. **backend/tests/test_idempotency.py** - NEW (6 tests)
5. **README.md** - Updated documentation

## View Changes

- **See all diffs:** Open `CHANGES_DIFF.md`
- **See detailed summary:** Open `PRODUCTION_FIXES_SUMMARY.md`

## If Tests Fail

1. Check Docker is running: `docker info`
2. Check logs: `docker compose logs backend`
3. Restart services: `docker compose restart backend`
4. Check database: `docker compose exec postgres psql -U postgres -d expert_outreach -c '\dt'`

## Alternative: Use Script

If you prefer, just run:

```bash
cd /Users/hurleywhite/expert-outreach
./run-tests.sh
```

---

**That's it! Run the commands above and paste the test output to confirm all fixes work.**
