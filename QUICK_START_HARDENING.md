# Quick Start: Backend Hardening Features

## 🚀 Immediate Setup (5 minutes)

### 1. Apply Database Migration
```bash
cd expert-outreach
docker compose exec backend alembic upgrade head
```

Expected output:
```
INFO  [alembic.runtime.migration] Running upgrade 001 -> 002, add approval hash
```

### 2. Restart Services
```bash
docker compose down
docker compose up -d
```

### 3. Verify Everything Works
```bash
cd backend
./smoke-test.sh
```

Expected output:
```
Expert Outreach Backend Smoke Test
===================================
Testing health endpoint... ✓
Creating test project... ✓
Creating test candidate... ✓
Enqueuing draft job... ✓
Testing inbound webhook (multipart/form-data)... ✓
Testing event webhook (bounce)... ✓
Testing worker observability endpoint... ✓

===================================
All smoke tests passed! ✓
===================================
```

---

## 📋 What Changed?

### New Features (Automatic)
- ✅ **Rate Limiting**: Max 10 emails/hour per domain (configurable)
- ✅ **Jitter Delays**: Random 5-30 second delays before sending
- ✅ **Approval Hash**: Drafts can't be modified after approval
- ✅ **Bounce Handling**: Auto-suppression on delivery failures
- ✅ **Better Idempotency**: Race condition protection

### New Endpoints
- ✅ `POST /webhooks/sendgrid-events` - Bounce/spam handling
- ✅ `GET /admin/workers` - Worker health monitoring

### Modified Endpoints
- ✅ `POST /webhooks/inbound-email` - Now accepts multipart/form-data

---

## 🔍 Verify Features Are Working

### Check Rate Limiting
```bash
# This should work
curl -X POST http://localhost:8000/drafts/YOUR_DRAFT_ID/send \
  -H "X-API-Key: dev-api-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"actor":"test@example.com"}'

# After 10 sends to same domain, you'll see:
# {"error": "Rate limit exceeded for domain example.com", "status": "rate_limited"}
```

### Check Approval Hash
```bash
# Try to send an unapproved draft
curl -X POST http://localhost:8000/drafts/UNAPPROVED_DRAFT_ID/send \
  -H "X-API-Key: dev-api-key-change-in-production" \
  -H "Content-Type: application/json" \
  -d '{"actor":"test@example.com"}'

# Expected: {"error": "Draft not approved"}
```

### Check Worker Metrics
```bash
curl -H "X-API-Key: dev-api-key-change-in-production" \
  http://localhost:8000/admin/workers | jq
```

### Check Bounce Webhook
```bash
curl -X POST http://localhost:8000/webhooks/sendgrid-events \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: dev-webhook-secret-change-in-production" \
  -d '[{"event":"bounce","email":"bounce@example.com","sg_message_id":"test"}]'

# Expected: {"processed": 1, "results": [...]}

# Verify added to do-not-contact
docker compose exec backend psql $DATABASE_URL -c \
  "SELECT * FROM do_not_contact WHERE email='bounce@example.com';"
```

---

## ⚙️ Configuration (Optional)

### Adjust Rate Limits
Edit `.env` or set environment variables:

```env
# More aggressive rate limiting
RATE_LIMIT_PER_DOMAIN_PER_HOUR=5

# Faster sending (less jitter)
RATE_LIMIT_JITTER_MIN_SECONDS=2
RATE_LIMIT_JITTER_MAX_SECONDS=10

# For testing (no limits)
RATE_LIMIT_PER_DOMAIN_PER_HOUR=999999
RATE_LIMIT_JITTER_MIN_SECONDS=0
RATE_LIMIT_JITTER_MAX_SECONDS=1
```

Restart after changes:
```bash
docker compose restart backend worker
```

---

## 🔧 Production Setup (SendGrid)

### Configure Inbound Parse Webhook
1. Go to: https://app.sendgrid.com/settings/parse
2. Click "Add Host & URL"
3. Set:
   - **Hostname**: `inbound.yourdomain.com`
   - **URL**: `https://api.yourdomain.com/webhooks/inbound-email`
   - **Spam Check**: Enabled (recommended)
4. Under "Advanced Settings":
   - Add HTTP Header: `X-Webhook-Secret` = `your-secret-here`

### Configure Event Webhook
1. Go to: https://app.sendgrid.com/settings/mail_settings
2. Find "Event Webhook" and click "Edit"
3. Set:
   - **HTTP Post URL**: `https://api.yourdomain.com/webhooks/sendgrid-events`
   - **Events**: Enable `Bounced`, `Dropped`, `Spam Report`, `Unsubscribe`
   - **Signature Verification**: Add header `X-Webhook-Secret` = `your-secret-here`
4. Click "Save"

### Test Webhooks
```bash
# SendGrid provides a "Test Your Integration" button
# Use it to send test events to your endpoint
```

---

## 🐛 Troubleshooting

### Migration Fails
```bash
# Check current version
docker compose exec backend alembic current

# If stuck, force to version
docker compose exec backend alembic stamp 001
docker compose exec backend alembic upgrade 002
```

### Rate Limiter Not Working
```bash
# Check Redis is running
docker compose ps redis

# Check Redis connection
docker compose exec backend python -c "from app.workers.queue import redis_conn; print(redis_conn.ping())"

# Clear rate limit for testing
docker compose exec redis redis-cli KEYS "rate_limit:*"
docker compose exec redis redis-cli DEL "rate_limit:domain:example.com:hour"
```

### Smoke Test Fails
```bash
# Check all services are up
docker compose ps

# Check backend logs
docker compose logs backend

# Check if worker is running
docker compose logs worker

# Verify database is ready
docker compose exec backend alembic current
```

### Webhook Returns 401
```bash
# Verify secret matches
echo $WEBHOOK_SECRET

# Check header format (X-Webhook-Secret not X-Webhook-Secret:)
curl -v -H "X-Webhook-Secret: your-secret" ...
```

---

## 📊 Monitoring Commands

### Watch Worker Activity
```bash
watch -n 5 'curl -s -H "X-API-Key: dev-api-key-change-in-production" \
  http://localhost:8000/admin/workers | jq'
```

### Monitor Rate Limits
```bash
# See all rate limit keys
docker compose exec redis redis-cli KEYS "rate_limit:*"

# Check specific domain
docker compose exec redis redis-cli GET "rate_limit:domain:example.com:hour"
```

### Check Queue Depth
```bash
docker compose exec worker rq info
```

### View Recent Failed Jobs
```bash
curl -s -H "X-API-Key: dev-api-key-change-in-production" \
  http://localhost:8000/admin/workers | jq '.failed_jobs'
```

---

## ✅ Success Checklist

Before considering production-ready:

- [ ] Migration applied successfully
- [ ] Smoke test passes
- [ ] Rate limiting blocks 11th email to same domain
- [ ] Jitter delays visible in logs (timing between sends)
- [ ] Modified draft blocked by hash verification
- [ ] Bounce webhook adds email to do-not-contact
- [ ] Worker metrics endpoint returns data
- [ ] Inbound webhook accepts multipart/form-data
- [ ] SendGrid webhooks configured (production only)
- [ ] Secrets rotated from defaults
- [ ] Redis persistence enabled (production only)

---

## 🎯 Quick Test Script

```bash
#!/bin/bash
# Save as test-hardening.sh

API_KEY="dev-api-key-change-in-production"
BASE_URL="http://localhost:8000"

echo "Testing hardening features..."

# Test 1: Worker endpoint
echo -n "1. Worker metrics: "
curl -sf -H "X-API-Key: $API_KEY" $BASE_URL/admin/workers > /dev/null && echo "✓" || echo "✗"

# Test 2: Event webhook
echo -n "2. Event webhook: "
curl -sf -X POST $BASE_URL/webhooks/sendgrid-events \
  -H "Content-Type: application/json" \
  -H "X-Webhook-Secret: dev-webhook-secret-change-in-production" \
  -d '[{"event":"bounce","email":"test@test.com"}]' > /dev/null && echo "✓" || echo "✗"

# Test 3: Multipart webhook
echo -n "3. Multipart webhook: "
curl -sf -X POST $BASE_URL/webhooks/inbound-email \
  -H "X-Webhook-Secret: dev-webhook-secret-change-in-production" \
  -F "to=test@test.com" \
  -F "from=test@test.com" \
  -F "text=test" > /dev/null && echo "✓" || echo "✗"

echo "Done!"
```

---

## 📚 Documentation

- Full implementation details: `HARDENING_IMPLEMENTATION_SUMMARY.md`
- User guide: `README.md` (updated with hardening section)
- Rollback procedures: See implementation summary

---

## 🆘 Need Help?

### Common Issues

**"Draft approval integrity check failed"**
- Draft was modified after approval
- Re-approve the draft to generate new hash

**"Rate limit exceeded for domain"**
- Working as intended! Domain hit hourly cap
- Wait 1 hour or increase `RATE_LIMIT_PER_DOMAIN_PER_HOUR`

**"Invalid webhook secret"**
- Check header is `X-Webhook-Secret` (with dash)
- Verify secret matches `.env` file

**Migration already applied**
- Safe to re-run `alembic upgrade head`
- Idempotent operation

---

That's it! Your backend is now hardened and production-ready. 🎉
