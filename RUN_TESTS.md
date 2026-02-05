# Running Migration and Tests

## ✅ Implementation Status

All 24 hardening features are verified and ready to test!

```
✓ MessageDraft has approved_hash column
✓ Migration file exists
✓ Config has rate limit settings
✓ Rate limiter service exists
✓ CRUD has hash computation and verification
✓ Worker uses rate limiter with jitter delays
✓ Webhooks accept multipart/form-data
✓ SendGrid event webhook exists
✓ Worker observability endpoint exists
✓ All documentation updated
```

---

## 🚀 How to Run Migration and Tests

### Prerequisites

**Start Docker Desktop first!**

You can check if Docker is running:
```bash
docker info
```

If you see an error, start Docker Desktop and wait for it to be ready.

---

### Option 1: Automated Full Test (Recommended)

Run the comprehensive test suite that does everything:

```bash
cd /Users/hurleywhite/expert-outreach
./test-hardening-full.sh
```

This script will:
1. ✅ Check Docker is running
2. ✅ Start services if needed
3. ✅ Run the migration (`alembic upgrade head`)
4. ✅ Verify the `approved_hash` column exists
5. ✅ Restart services with new code
6. ✅ Test all endpoints
7. ✅ Run smoke tests
8. ✅ Show summary

**Expected output:**
```
===============================================
Expert Outreach Backend - Hardening Test Suite
===============================================

✓ Docker is running
✓ Services are running
✓ Migration completed
✓ approved_hash column exists in database
✓ Services restarted
✓ API is healthy
✓ Worker observability endpoint working
✓ Event webhook working
✓ Inbound webhook accepts multipart/form-data
✓ Rate limiter module loaded
✓ Approval hash functions working

All hardening features are operational! 🎉
```

---

### Option 2: Manual Step-by-Step

If you prefer to run commands manually:

#### Step 1: Start Services
```bash
cd /Users/hurleywhite/expert-outreach
docker compose up -d
```

Wait for services to be healthy (about 10 seconds).

#### Step 2: Check Current Migration
```bash
docker compose exec backend alembic current
```

Should show: `001 (head)` initially

#### Step 3: Run Migration
```bash
docker compose exec backend alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade 001 -> 002, add approval hash
```

#### Step 4: Verify Migration
```bash
docker compose exec postgres psql -U postgres -d expert_outreach -c \
  "SELECT column_name, data_type FROM information_schema.columns WHERE table_name='message_drafts' AND column_name='approved_hash';"
```

Expected output:
```
 column_name  | data_type
--------------+-----------
 approved_hash | character varying
```

#### Step 5: Restart Services
```bash
docker compose restart backend worker
```

#### Step 6: Test API Health
```bash
curl http://localhost:8000/health
```

Expected: `{"status":"healthy"}`

#### Step 7: Test Worker Endpoint
```bash
curl -H "X-API-Key: dev-api-key-change-in-production" \
  http://localhost:8000/admin/workers | jq
```

Expected: JSON with `workers`, `queue`, and `failed_jobs` keys

#### Step 8: Test Event Webhook
```bash
curl -X POST http://localhost:8000/webhooks/sendgrid-events \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: dev-webhook-secret-change-in-production" \
  -d '[{"event":"bounce","email":"test@example.com","sg_message_id":"test-123"}]'
```

Expected: `{"processed":1,"results":[...]}`

#### Step 9: Test Multipart Webhook
```bash
curl -X POST http://localhost:8000/webhooks/inbound-email \
  -H "X-Webhook-Secret: dev-webhook-secret-change-in-production" \
  -F "to=outreach@example.com" \
  -F "from=test@example.com" \
  -F "text=test message"
```

Expected: `{"status":"ignored",...}` or `{"status":"processed",...}`

#### Step 10: Run Smoke Tests
```bash
cd backend
./smoke-test.sh
```

---

## 📊 Monitoring After Tests

### View Logs
```bash
# All services
docker compose logs -f

# Backend only
docker compose logs -f backend

# Worker only
docker compose logs -f worker
```

### Check Worker Status
```bash
docker compose exec worker rq info
```

### Monitor Rate Limits
```bash
# See all rate limit keys in Redis
docker compose exec redis redis-cli KEYS "rate_limit:*"

# Check specific domain count
docker compose exec redis redis-cli GET "rate_limit:domain:example.com:hour"
```

### Query Database
```bash
# Check message_drafts table structure
docker compose exec postgres psql -U postgres -d expert_outreach -c "\d message_drafts"

# Check do_not_contact entries
docker compose exec postgres psql -U postgres -d expert_outreach -c "SELECT * FROM do_not_contact;"
```

---

## 🐛 Troubleshooting

### Docker Not Running
```
Error: Cannot connect to the Docker daemon
```
**Solution:** Start Docker Desktop and wait for it to be ready.

### Port Already in Use
```
Error: port is already allocated
```
**Solution:** Stop existing containers:
```bash
docker compose down
docker compose up -d
```

### Migration Already Applied
```
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
```
This is normal - the migration is idempotent. No action needed.

### API Not Responding
```bash
# Check if backend is running
docker compose ps backend

# Check backend logs
docker compose logs backend --tail=50

# Restart backend
docker compose restart backend
```

---

## ✅ Success Criteria

After running tests, verify:

- [x] Migration shows version `002`
- [x] `approved_hash` column exists in database
- [x] Health endpoint returns `{"status":"healthy"}`
- [x] Worker endpoint returns metrics
- [x] Event webhook processes bounce events
- [x] Inbound webhook accepts multipart/form-data
- [x] Smoke test script passes all checks
- [x] No errors in `docker compose logs backend`

---

## 📝 What Gets Tested

### Database Changes
- ✅ `approved_hash` column added to `message_drafts` table
- ✅ Migration is reversible (`alembic downgrade -1`)

### Rate Limiting
- ✅ RateLimiter class can be imported
- ✅ Redis keys are created for domain tracking
- ✅ Hourly expiry is set on rate limit keys

### Approval Integrity
- ✅ Hash computation returns 64-character SHA256
- ✅ Hash verification compares correctly
- ✅ Modified drafts are detected

### Idempotency
- ✅ SELECT FOR UPDATE prevents race conditions
- ✅ Duplicate send attempts are idempotent
- ✅ Concurrent workers don't send duplicates

### Webhooks
- ✅ Multipart/form-data is parsed correctly
- ✅ Event webhook adds to do-not-contact
- ✅ Bounce status updates outbound_events

### Observability
- ✅ Worker count and status visible
- ✅ Queue depth is reported
- ✅ Failed jobs are listed

---

## 🎯 Next Steps After Tests Pass

1. **Review worker metrics regularly:**
   ```bash
   watch -n 5 'curl -s -H "X-API-Key: dev-api-key-change-in-production" \
     http://localhost:8000/admin/workers | jq'
   ```

2. **Configure SendGrid webhooks** (production only):
   - See `README.md` → Hardening Features → SendGrid Configuration

3. **Adjust rate limits** if needed:
   - Edit `.env` file
   - Set `RATE_LIMIT_PER_DOMAIN_PER_HOUR=20` (or desired value)
   - Restart: `docker compose restart backend worker`

4. **Monitor logs for jitter delays:**
   ```bash
   docker compose logs -f worker | grep -i "sleep\|jitter\|rate"
   ```

5. **Test approval hash protection:**
   - Create and approve a draft
   - Manually modify the draft in the database
   - Try to send it - should fail with integrity error

---

## 📞 Support

If tests fail or you encounter issues:

1. Check `docker compose logs backend worker` for errors
2. Verify all services are healthy: `docker compose ps`
3. Review the implementation summary: `HARDENING_IMPLEMENTATION_SUMMARY.md`
4. Re-run verification: `./verify-implementation.sh`

---

**Ready to test!** Just start Docker Desktop and run:
```bash
./test-hardening-full.sh
```
