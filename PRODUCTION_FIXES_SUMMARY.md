# Production Fixes Summary

## Issues Fixed

### ISSUE 1: SendGrid Event Name Mismatch
**Problem:** Webhook handler expected `spam_report` but SendGrid commonly sends `spamreport` (no underscore).

**Fix:**
- Normalized all event names to lowercase
- Map both `spam_report` and `spamreport` to `spamreport` for consistency
- Added `blocked` to hard-failure suppression list
- Update candidate status to `DO_NOT_CONTACT` when suppression occurs
- Update outbound_event status to `BOUNCED` when `sg_message_id` matches

**Files Changed:**
- `backend/app/routers/webhooks.py` - Updated `receive_sendgrid_events()` function

### ISSUE 2: Idempotency Key Includes Actor
**Problem:** Idempotency key `f"{draft_id}-{actor}"` allowed duplicates when different actors sent the same draft.

**Fix:**
- Changed idempotency key to `f"draft:{draft_id}"` (stable per draft, not per actor)
- Moved rate limit check AFTER idempotency check but BEFORE sending (bonus safety)
- Ensured rate-limited attempts don't create duplicate events
- Actor is still stored in metadata for audit purposes

**Files Changed:**
- `backend/app/workers/jobs.py` - Updated `send_job()` function

### Documentation Updates
- `README.md` - Updated SendGrid Event Webhook section to document spamreport alias handling
- `README.md` - Updated Idempotency section with new key format

---

## File Changes

### 1. backend/app/routers/webhooks.py

**Key Changes:**
- Lines 119-164: Complete rewrite of `receive_sendgrid_events()` function
- Added event name normalization (lowercase)
- Map `spam_report` → `spamreport`
- Added `blocked` to hard-failure events
- Update candidate status to `DO_NOT_CONTACT` for all suppression events
- Returns normalized event names in response

**Critical Code:**
```python
# Normalize event type to lowercase and handle aliases
event_type = raw_event_type.lower()
if event_type == "spam_report":
    event_type = "spamreport"

# Hard failures: bounce, dropped, blocked, spamreport
if event_type in ["bounce", "dropped", "blocked", "spamreport"]:
    # Update outbound_event if sg_message_id matches
    # Add to do_not_contact
    # Update candidate status to DO_NOT_CONTACT
```

### 2. backend/app/workers/jobs.py

**Key Changes:**
- Line 224: Changed idempotency key from `f"{draft_id}-{actor}"` to `f"draft:{draft_id}"`
- Lines 214-221: Moved rate limit check to AFTER idempotency check
- Added rollback when rate limited to avoid creating duplicate events

**Critical Code:**
```python
# Generate idempotency key (stable per draft, not per actor)
idempotency_key = f"draft:{draft_id}"

# Get or create event with lock (proper idempotency)
outbound_event, is_new = crud.get_or_create_outbound_event_with_lock(...)

# If already sent, return early (idempotent)
if outbound_event.status == models.OutboundEventStatus.SENT:
    db.rollback()
    return {"message": "Already sent (idempotent)", ...}

# Check rate limit AFTER idempotency check but BEFORE sending
if not RateLimiter.can_send_to_domain(domain):
    db.rollback()  # Release lock without creating duplicate events
    return {"error": f"Rate limit exceeded...", "status": "rate_limited"}
```

### 3. backend/tests/test_sendgrid_events.py (NEW)

**Test Coverage:**
- `test_spamreport_no_underscore` - Verifies `spamreport` is handled correctly
- `test_spam_report_with_underscore` - Verifies `spam_report` normalizes to `spamreport`
- `test_bounce_event` - Verifies bounce handling and outbound_event update
- `test_dropped_event` - Verifies dropped events trigger suppression
- `test_blocked_event` - Verifies blocked events trigger suppression
- `test_unsubscribe_event` - Verifies unsubscribe handling
- `test_mixed_case_event_normalization` - Verifies case normalization
- `test_batch_events` - Verifies batch processing

**Total Tests:** 8 tests

### 4. backend/tests/test_idempotency.py (NEW)

**Test Coverage:**
- `test_idempotency_different_actors_single_send` - Main test: different actors = 1 send
- `test_idempotency_same_actor_multiple_calls` - Same actor multiple times = 1 send
- `test_idempotency_key_format` - Verifies `draft:{draft_id}` format
- `test_concurrent_sends_with_different_actors` - Verifies locking works
- `test_rate_limited_does_not_create_duplicate_events` - Verifies rate limit safety
- `test_actor_stored_in_metadata` - Verifies actor is still audited

**Total Tests:** 6 tests

### 5. README.md

**Section Updates:**
- **SendGrid Event Webhook** (lines 213-239):
  - Added documentation for spamreport/spam_report alias handling
  - Listed all suppression events (bounce, dropped, blocked, spamreport, unsubscribe)
  - Updated example to show `spamreport` format

- **Idempotency** (lines 351-358):
  - Updated key format from `{draft_id}-{actor}` to `draft:{draft_id}`
  - Added explanation that actor is not in key
  - Noted actor is still stored in metadata for audit

---

## How to Run Tests

### Step 1: Build and Start Services

```bash
cd /Users/hurleywhite/expert-outreach
docker compose up -d --build
```

Wait about 10 seconds for services to be ready.

### Step 2: Run Migrations

```bash
docker compose exec backend alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```

### Step 3: Run All Tests (Quick Check)

```bash
docker compose exec backend pytest -q
```

This runs all tests in quiet mode.

### Step 4: Run Specific Fix Tests (Verbose)

```bash
docker compose exec backend pytest -v tests/test_sendgrid_events.py tests/test_idempotency.py
```

Expected output should show:
```
tests/test_sendgrid_events.py::test_spamreport_no_underscore PASSED
tests/test_sendgrid_events.py::test_spam_report_with_underscore PASSED
tests/test_sendgrid_events.py::test_bounce_event PASSED
tests/test_sendgrid_events.py::test_dropped_event PASSED
tests/test_sendgrid_events.py::test_blocked_event PASSED
tests/test_sendgrid_events.py::test_unsubscribe_event PASSED
tests/test_sendgrid_events.py::test_mixed_case_event_normalization PASSED
tests/test_sendgrid_events.py::test_batch_events PASSED
tests/test_idempotency.py::test_idempotency_different_actors_single_send PASSED
tests/test_idempotency.py::test_idempotency_same_actor_multiple_calls PASSED
tests/test_idempotency.py::test_idempotency_key_format PASSED
tests/test_idempotency.py::test_concurrent_sends_with_different_actors PASSED
tests/test_idempotency.py::test_rate_limited_does_not_create_duplicate_events PASSED
tests/test_idempotency.py::test_actor_stored_in_metadata PASSED

============================== 14 passed in X.XXs ==============================
```

**All 14 tests should PASS.**

---

## Verification Checklist

After running tests, verify:

### Issue 1 - SendGrid Events
- [ ] Both `spamreport` and `spam_report` events are processed identically
- [ ] `blocked` events trigger suppression
- [ ] Do-not-contact entries are created with normalized event names (e.g., `sendgrid_spamreport`)
- [ ] Candidate status is updated to `DO_NOT_CONTACT`
- [ ] Outbound event status is updated to `BOUNCED` when `sg_message_id` matches

### Issue 2 - Idempotency
- [ ] Idempotency key format is `draft:{draft_id}` (not including actor)
- [ ] Sending same draft with different actors results in exactly 1 email send
- [ ] Sending same draft with different actors creates exactly 1 outbound event
- [ ] Second send attempt returns "Already sent (idempotent)"
- [ ] Actor is still stored in outbound_event.meta for audit purposes
- [ ] Rate-limited attempts don't create duplicate outbound events

---

## Quick Test Script

Use the provided script to run all tests:

```bash
cd /Users/hurleywhite/expert-outreach
./run-tests.sh
```

This script will:
1. Build and start services
2. Run migrations
3. Run all tests
4. Run specific fix tests with verbose output

---

## Manual Testing (Optional)

### Test SendGrid Event Normalization

```bash
# Test spamreport (no underscore)
curl -X POST http://localhost:8000/webhooks/sendgrid-events \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: dev-webhook-secret-change-in-production" \
  -d '[{"event":"spamreport","email":"test1@example.com"}]'

# Test spam_report (with underscore) - should behave identically
curl -X POST http://localhost:8000/webhooks/sendgrid-events \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: dev-webhook-secret-change-in-production" \
  -d '[{"event":"spam_report","email":"test2@example.com"}]'

# Check database - both should have "sendgrid_spamreport" reason
docker compose exec postgres psql -U postgres -d expert_outreach -c \
  "SELECT email, reason FROM do_not_contact WHERE email IN ('test1@example.com', 'test2@example.com');"
```

### Test Idempotency

```python
# In a Python shell
from app.workers.jobs import send_job

# Assuming you have a valid approved draft_id
draft_id = "your-draft-id-here"

# Send with actor A
result1 = send_job(draft_id, actor="alice@company.com")
print(result1)  # Should succeed

# Send with actor B
result2 = send_job(draft_id, actor="bob@company.com")
print(result2)  # Should return "Already sent (idempotent)"

# Check database - should have exactly 1 outbound event
```

---

## Rollback Plan

If issues are found:

### Revert Code Changes
```bash
git revert HEAD
docker compose down
docker compose up -d --build
```

### Database Rollback
No database migration was created for these fixes, so no rollback needed.

---

## Summary

✅ **ISSUE 1 FIXED:** SendGrid event webhook now handles both `spamreport` and `spam_report` identically, along with proper normalization and candidate status updates.

✅ **ISSUE 2 FIXED:** Idempotency key is now stable per draft (`draft:{draft_id}`), preventing duplicates regardless of actor.

✅ **BONUS SAFETY:** Rate limit check moved to after idempotency check to avoid creating duplicate events when rate limited.

✅ **14 NEW TESTS:** Comprehensive test coverage for both fixes.

✅ **DOCUMENTATION UPDATED:** README reflects new behavior for both issues.

---

**Ready to test! Run the commands above to verify all fixes work correctly.**
